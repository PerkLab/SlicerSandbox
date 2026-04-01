import logging
import math
import time

import slicer
from slicer.i18n import tr as _
from slicer.i18n import translate
from slicer.ScriptedLoadableModule import (
    ScriptedLoadableModule,
    ScriptedLoadableModuleLogic,
    ScriptedLoadableModuleTest,
    ScriptedLoadableModuleWidget,
)

from PythonQt import QtCore


#
# JoystickControl
#


class JoystickControl(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = _("Joystick Control")
        self.parent.categories = [translate("qSlicerAbstractCoreModule", "Utilities")]
        self.parent.dependencies = []
        self.parent.contributors = ["Anras Lasso (PerkLab, Queen's University)"]
        self.parent.helpText = _("""
Controls the 3D view camera using a game controller.
<p><b>Joy-Con (right or left, auto-detected via Bluetooth):</b></p>
<ul>
  <li>Stick: pan or rotate camera</li>
  <li>ZR: zoom in &nbsp; R: zoom out</li>
  <li>Y: translation mode &nbsp; X: rotation mode</li>
  <li>A: recalibrate stick center</li>
  <li>+: reset view</li>
  <li>SR (held): gyro / freehand mode</li>
</ul>
<p><b>Xbox controller:</b></p>
<ul>
  <li>Right stick: pan or rotate camera</li>
  <li>RT: zoom in &nbsp; LT: zoom out</li>
  <li>Y: translation mode &nbsp; X: rotation mode</li>
  <li>Start: reset view</li>
  <li>Right stick click (held): roll mode</li>
</ul>
""")
        self.parent.acknowledgementText = ""


#
# Shared utility
#


def _deadzone_axis(value, center, max_range, threshold):
    """Map a raw axis value to [-1, 1] with a centred deadzone."""
    normalized = (value - center) / max_range
    normalized = max(-1.0, min(1.0, normalized))
    if abs(normalized) < threshold:
        return 0.0
    sign = 1 if normalized > 0 else -1
    return sign * (abs(normalized) - threshold) / (1.0 - threshold)


#
# JoyConController
#


class JoyConController:
    """Nintendo Joy-Con controller (left or right, auto-detected via Bluetooth).

    Implements the controller interface expected by JoystickControlLogic:
      connect() / disconnect() / name / button_mapping() / get_input()

    get_input() returns a normalised dict (see _EMPTY_INPUT) or None to
    signal "skip this frame" (e.g. while recalibrating).
    """

    DEADZONE      = 0.15
    STICK_MAX     = 1400   # approx half-range of the 12-bit Joy-Con stick
    CALIB_SAMPLES = 30
    CALIB_DELAY   = 0.02   # seconds between calibration samples
    GYRO_SCALE    = 0.004  # raw gyro units → normalised movement per tick

    def __init__(self) -> None:
        self._joycon   = None
        self._is_left  = False
        self._centerH  = 0.0
        self._centerV  = 0.0
        self._freehand = False
        self._sl_prev  = False
        self._sr_prev  = False

    @property
    def name(self) -> str:
        return ("Left" if self._is_left else "Right") + " Joy-Con"

    # ------------------------------------------------------------------
    # Interface
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Detect and connect to a Joy-Con; raise RuntimeError if none found."""
        slicer.util.pip_install("joycon-python hidapi pyglm")
        from pyjoycon import JoyCon, get_R_id, get_L_id

        r_id = get_R_id()
        if r_id != (None, None, None):
            self._joycon  = JoyCon(*r_id)
            self._is_left = False
            logging.info("[JoyCon] Connected (right).")
        else:
            l_id = get_L_id()
            if l_id == (None, None, None):
                raise RuntimeError("No Joy-Con found. Make sure one is paired via Bluetooth.")
            self._joycon  = JoyCon(*l_id)
            self._is_left = True
            logging.info("[JoyCon] Connected (left).")

        self._centerH, self._centerV = self._calibrate()
        self._freehand = False
        self._sl_prev  = False
        self._sr_prev  = False

    def disconnect(self) -> None:
        self._joycon  = None
        self._is_left = False

    def button_mapping(self) -> dict:
        if self._is_left:
            return {
                "Pan / rotate":         "Stick",
                "Zoom in":              "ZL",
                "Zoom out":             "L",
                "Translate mode":       "Right arrow",
                "Rotate mode":          "Up arrow",
                "Recalibrate":          "Down arrow",
                "Reset view":           "−  (minus)",
                "Toggle freehand/gyro": "SL",
            }
        return {
            "Pan / rotate":         "Stick",
            "Zoom in":              "ZR",
            "Zoom out":             "R",
            "Translate mode":       "Y",
            "Rotate mode":          "X",
            "Recalibrate":          "A",
            "Reset view":           "+  (plus)",
            "Toggle freehand/gyro": "SR",
        }

    def get_input(self) -> dict:
        """Return normalised input dict, or None to skip this frame."""
        try:
            # Drain any buffered stale HID reports
            for _ in range(4):
                status = self._joycon.get_status()
        except Exception as e:
            logging.warning(f"[JoyCon] Read error: {e}")
            return None

        side   = "left" if self._is_left else "right"
        stick  = status["analog-sticks"][side]
        btn    = status["buttons"][side]
        shared = status["buttons"]["shared"]

        if self._is_left:
            btn_trans    = "right"
            btn_rot      = "up"
            btn_recal    = "down"
            btn_zoom_in  = "zl"
            btn_zoom_out = "l"
            btn_reset    = "minus"
        else:
            btn_trans    = "y"
            btn_rot      = "x"
            btn_recal    = "a"
            btn_zoom_in  = "zr"
            btn_zoom_out = "r"
            btn_reset    = "plus"

        # Freehand (gyro) mode toggle on SL / SR edge
        if self._is_left:
            sl_now = bool(btn.get("sl", 0))
            if sl_now != self._sl_prev:
                self._freehand = sl_now
                logging.info(f"[JoyCon] Freehand: {'ON' if self._freehand else 'OFF'}")
            self._sl_prev = sl_now
        else:
            sr_now = bool(btn.get("sr", 0))
            if sr_now != self._sr_prev:
                self._freehand = sr_now
                logging.info(f"[JoyCon] Freehand: {'ON' if self._freehand else 'OFF'}")
            self._sr_prev = sr_now

        # Recalibrate: handle internally and skip this frame
        if btn.get(btn_recal, 0):
            self._centerH, self._centerV = self._calibrate(samples=10)
            return None

        stick_key     = "l-stick" if self._is_left else "r-stick"
        stick_pressed = bool(shared.get(stick_key, 0))

        if self._freehand:
            h, v, roll = self._read_gyro(status)
        else:
            roll = 0.0
            h = _deadzone_axis(stick.get("horizontal", self._centerH), self._centerH, self.STICK_MAX, self.DEADZONE)
            v = _deadzone_axis(stick.get("vertical",   self._centerV), self._centerV, self.STICK_MAX, self.DEADZONE)

        return {
            "h":              h,
            "v":              v,
            "roll":           roll,
            "zoom_in":        float(bool(btn.get(btn_zoom_in,  0))),
            "zoom_out":       float(bool(btn.get(btn_zoom_out, 0))),
            "mode_translate": bool(btn.get(btn_trans, 0)),
            "mode_rotate":    bool(btn.get(btn_rot,   0)),
            "reset":          bool(shared.get(btn_reset, 0)),
            "roll_mode":      stick_pressed,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _calibrate(self, samples=None, delay=None):
        if samples is None:
            samples = self.CALIB_SAMPLES
        if delay is None:
            delay = self.CALIB_DELAY
        logging.info(f"[JoyCon] Calibrating — keep stick neutral ({samples} samples)...")
        h_vals, v_vals = [], []
        for _ in range(samples):
            s = self._joycon.get_status()
            stick = s["analog-sticks"]["left" if self._is_left else "right"]
            h_vals.append(stick["horizontal"])
            v_vals.append(stick["vertical"])
            time.sleep(delay)
        center_h = sum(h_vals) / len(h_vals)
        center_v = sum(v_vals) / len(v_vals)
        logging.info(f"[JoyCon] Center: h={center_h:.0f} v={center_v:.0f}")
        return center_h, center_v

    def _read_gyro(self, status):
        """Return (h, v, roll) from gyro, normalised to roughly ±1.

        After accounting for left/right orientation corrections the mapping
        simplifies to: h = gy, v = -gz, roll = -gx regardless of side.
        """
        gyro = status.get("gyro", {})
        if not gyro:
            return 0.0, 0.0, 0.0
        s = self.GYRO_SCALE
        return gyro.get("y", 0) * s, -gyro.get("z", 0) * s, -gyro.get("x", 0) * s


#
# XboxController  — Windows XInput via ctypes, no external dependencies
#


class XboxController:
    """Xbox / XInput controller on Windows.

    Implements the same controller interface as JoyConController:
      connect() / disconnect() / name / button_mapping() / get_input()
    """

    # Button bitmasks (wButtons field)
    DPAD_UP        = 0x0001
    DPAD_DOWN      = 0x0002
    DPAD_LEFT      = 0x0004
    DPAD_RIGHT     = 0x0008
    START          = 0x0010
    BACK           = 0x0020
    LEFT_THUMB     = 0x0040
    RIGHT_THUMB    = 0x0080
    LEFT_SHOULDER  = 0x0100
    RIGHT_SHOULDER = 0x0200
    A              = 0x1000
    B              = 0x2000
    X              = 0x4000
    Y              = 0x8000

    DEADZONE     = 0.15
    _THUMB_MAX   = 32767.0
    _TRIGGER_MAX = 255.0

    def __init__(self) -> None:
        self._index  = -1
        self._xinput = None
        self._State  = None

    @property
    def name(self) -> str:
        return "Xbox"

    # ------------------------------------------------------------------
    # Interface
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Load XInput DLL and find the first connected controller."""
        import ctypes
        for dll in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
            try:
                self._xinput = getattr(ctypes.windll, dll)
                break
            except OSError:
                pass
        if self._xinput is None:
            raise RuntimeError("XInput DLL not found. Xbox controller requires Windows with XInput support.")

        class _Gamepad(ctypes.Structure):
            _fields_ = [
                ("wButtons",      ctypes.c_ushort),
                ("bLeftTrigger",  ctypes.c_ubyte),
                ("bRightTrigger", ctypes.c_ubyte),
                ("sThumbLX",      ctypes.c_short),
                ("sThumbLY",      ctypes.c_short),
                ("sThumbRX",      ctypes.c_short),
                ("sThumbRY",      ctypes.c_short),
            ]

        class _State(ctypes.Structure):
            _fields_ = [
                ("dwPacketNumber", ctypes.c_ulong),
                ("Gamepad",        _Gamepad),
            ]

        self._State = _State

        # Find the first connected controller (indices 0–3)
        import ctypes as _ct
        for i in range(4):
            state = _State()
            if self._xinput.XInputGetState(i, _ct.byref(state)) == 0:
                self._index = i
                logging.info(f"[Xbox] Connected (controller index {i}).")
                return
        raise RuntimeError(
            "No Xbox / XInput controller found. "
            "Connect one via USB or Bluetooth and try again."
        )

    def disconnect(self) -> None:
        self._index  = -1
        self._xinput = None
        self._State  = None

    def button_mapping(self) -> dict:
        return {
            "Pan / rotate":   "Right stick",
            "Zoom in":        "RT",
            "Zoom out":       "LT",
            "Translate mode": "Y",
            "Rotate mode":    "X",
            "Reset view":     "Start",
            "Roll (held)":    "Right stick click",
        }

    def get_input(self) -> dict:
        """Return normalised input dict, or None if the controller disconnected."""
        import ctypes
        state = self._State()
        err = self._xinput.XInputGetState(self._index, ctypes.byref(state))
        if err != 0:
            logging.warning(f"[Xbox] Controller {self._index} disconnected (XInput error {err}).")
            return None
        gp = state.Gamepad
        buttons = gp.wButtons

        h = _deadzone_axis(gp.sThumbRX / self._THUMB_MAX, 0.0, 1.0, self.DEADZONE)
        v = _deadzone_axis(gp.sThumbRY / self._THUMB_MAX, 0.0, 1.0, self.DEADZONE)

        return {
            "h":              h,
            "v":              v,
            "roll":           0.0,
            "zoom_in":        gp.bRightTrigger / self._TRIGGER_MAX,
            "zoom_out":       gp.bLeftTrigger  / self._TRIGGER_MAX,
            "mode_translate": bool(buttons & self.Y),
            "mode_rotate":    bool(buttons & self.X),
            "reset":          bool(buttons & self.START),
            "roll_mode":      bool(buttons & self.RIGHT_THUMB),
        }


#
# JoystickControlWidget
#

# Controller type options shown in the combo box (label, logic key)
_CONTROLLER_TYPES = [
    ("Joy-Con (auto-detect)", "joycon"),
    ("Xbox / Gamepad",        "xbox"),
]


class JoystickControlWidget(ScriptedLoadableModuleWidget):
    def __init__(self, parent=None) -> None:
        ScriptedLoadableModuleWidget.__init__(self, parent)
        self.logic = None

    def setup(self) -> None:
        ScriptedLoadableModuleWidget.setup(self)

        uiWidget = slicer.util.loadUI(self.resourcePath("UI/JoystickControl.ui"))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        self.logic = JoystickControlLogic()
        self.logic.modeChangedCallback = self._onModeChanged

        for label, _ in _CONTROLLER_TYPES:
            self.ui.controllerTypeComboBox.addItem(label)

        self.ui.enableCheckBox.connect("toggled(bool)", self.onEnableToggled)
        self.ui.sensitivitySlider.connect("valueChanged(double)", self.onSensitivityChanged)

        self.ui.cameraNodeComboBox.setMRMLScene(slicer.mrmlScene)
        self.ui.cameraNodeComboBox.nodeTypes = ["vtkMRMLCameraNode"]
        self.ui.cameraNodeComboBox.addEnabled = False
        self.ui.cameraNodeComboBox.removeEnabled = False
        self.ui.cameraNodeComboBox.noneEnabled = True
        self.ui.cameraNodeComboBox.noneDisplay = "(first 3D view)"
        self.ui.cameraNodeComboBox.connect("currentNodeChanged(vtkMRMLNode*)", self.onCameraNodeChanged)
        self.logic.cameraNode = self.ui.cameraNodeComboBox.currentNode()

        sensitivity = float(slicer.app.settings().value("JoystickControl/sensitivity", 1.0))
        self.ui.sensitivitySlider.value = sensitivity
        self.logic.sensitivity = sensitivity

    def cleanup(self) -> None:
        if self.logic:
            self.logic.stopControl()

    def onEnableToggled(self, checked: bool) -> None:
        if checked:
            try:
                idx = self.ui.controllerTypeComboBox.currentIndex
                self.logic.controllerType = _CONTROLLER_TYPES[idx][1]
                self.logic.startControl()
                self._setActiveStatusLabel()
                self._updateMappingLabel()
            except Exception as e:
                slicer.util.errorDisplay(f"Failed to connect to controller: {e}")
                self.ui.enableCheckBox.checked = False
                self.ui.statusLabel.text = "Not connected"
        else:
            self.logic.stopControl()
            self.ui.statusLabel.text = "Stopped"
            self.ui.mappingLabel.text = "Connect a controller to see button mapping."

    def onCameraNodeChanged(self, node) -> None:
        self.logic.cameraNode = node

    def onSensitivityChanged(self, value: float) -> None:
        self.logic.sensitivity = value
        slicer.app.settings().setValue("JoystickControl/sensitivity", value)

    def _updateMappingLabel(self) -> None:
        mapping = self.logic.getButtonMapping()
        rows = "".join(
            f"<tr><td style='padding-right:12px'>{action}</td>"
            f"<td><b>{button}</b></td></tr>"
            for action, button in mapping.items()
        )
        self.ui.mappingLabel.text = f"<table>{rows}</table>"

    def _setActiveStatusLabel(self) -> None:
        controllerName = self.logic._controller.name if self.logic._controller else "Controller"
        modeText = self.logic.getModeLabel()
        self.ui.statusLabel.text = f"Active ({controllerName}) - Mode: {modeText}"

    def _onModeChanged(self, _mode: str) -> None:
        if self.ui.enableCheckBox.checked:
            self._setActiveStatusLabel()


#
# JoystickControlLogic
#


class JoystickControlLogic(ScriptedLoadableModuleLogic):
    """Hardware-independent camera control logic.

    Talks to the active controller exclusively through the normalised
    get_input() dict.  All hardware knowledge lives in JoyConController
    and XboxController.
    """

    POLL_INTERVAL_MS = 10    # ~100 Hz
    TRANSLATE_SPEED  = 2.0
    ROTATE_SPEED     = 1.5   # degrees per tick at full deflection
    ZOOM_SPEED       = 0.05

    MODE_TRANSLATE = "translate"
    MODE_ROTATE    = "rotate"

    CONTROLLER_JOYCON = "joycon"
    CONTROLLER_XBOX   = "xbox"

    def __init__(self) -> None:
        ScriptedLoadableModuleLogic.__init__(self)
        self._controller   = None
        self._timer        = None
        self._mode         = self.MODE_ROTATE
        self.sensitivity   = 1.0
        self.cameraNode    = None
        self.controllerType = self.CONTROLLER_JOYCON
        self.modeChangedCallback = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def startControl(self) -> None:
        """Instantiate the right controller, connect it, and start polling."""
        if self.controllerType == self.CONTROLLER_XBOX:
            self._controller = XboxController()
        else:
            self._controller = JoyConController()

        self._controller.connect()
        self._mode = self.MODE_ROTATE

        self._timer = QtCore.QTimer()
        self._timer.timeout.connect(self._poll)
        self._timer.start(self.POLL_INTERVAL_MS)

        mapping = self._controller.button_mapping()
        summary = "  ".join(f"{a}={b}" for a, b in mapping.items())
        logging.info(f"[JoystickControl] Active ({self._controller.name}). {summary}")

    def getButtonMapping(self) -> dict:
        if self._controller is None:
            return {}
        return self._controller.button_mapping()

    def getModeLabel(self) -> str:
        return self._mode.upper()

    def stopControl(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        if self._controller is not None:
            self._controller.disconnect()
            self._controller = None
        logging.info("[JoystickControl] Stopped.")

    # ------------------------------------------------------------------
    # Camera helpers
    # ------------------------------------------------------------------

    def _get_camera(self):
        if self.cameraNode is not None:
            return self.cameraNode.GetCamera()
        threeDWidget = slicer.app.layoutManager().threeDWidget(0)
        return threeDWidget.threeDView().renderWindow().GetRenderers().GetFirstRenderer().GetActiveCamera()

    def _get_three_d_view(self):
        if self.cameraNode is not None:
            layoutName = self.cameraNode.GetLayoutName()
            lm = slicer.app.layoutManager()
            for i in range(lm.threeDViewCount):
                w = lm.threeDWidget(i)
                if w.mrmlViewNode().GetLayoutName() == layoutName:
                    return w.threeDView()
        return slicer.app.layoutManager().threeDWidget(0).threeDView()

    def _apply_pan(self, camera, h, v) -> None:
        pos = list(camera.GetPosition())
        foc = list(camera.GetFocalPoint())
        up  = list(camera.GetViewUp())

        view = [foc[i] - pos[i] for i in range(3)]
        length = math.sqrt(sum(x * x for x in view))
        view = [x / length for x in view]

        right = [
            up[1]*view[2] - up[2]*view[1],
            up[2]*view[0] - up[0]*view[2],
            up[0]*view[1] - up[1]*view[0],
        ]

        dx = [right[i] * h * self.TRANSLATE_SPEED * self.sensitivity for i in range(3)]
        dy = [-up[i]   * v * self.TRANSLATE_SPEED * self.sensitivity for i in range(3)]

        camera.SetPosition(*[pos[i] + dx[i] + dy[i] for i in range(3)])
        camera.SetFocalPoint(*[foc[i] + dx[i] + dy[i] for i in range(3)])

    @staticmethod
    def _rotate_vec(v, axis, angle_deg):
        a = math.radians(angle_deg)
        cos_a, sin_a = math.cos(a), math.sin(a)
        dot = sum(v[i] * axis[i] for i in range(3))
        cross = [
            axis[1]*v[2] - axis[2]*v[1],
            axis[2]*v[0] - axis[0]*v[2],
            axis[0]*v[1] - axis[1]*v[0],
        ]
        return [v[i]*cos_a + cross[i]*sin_a + axis[i]*dot*(1 - cos_a) for i in range(3)]

    def _apply_rotate(self, camera, h, v) -> None:
        pos = list(camera.GetPosition())
        foc = list(camera.GetFocalPoint())
        up  = list(camera.GetViewUp())
        arm = [pos[i] - foc[i] for i in range(3)]

        def cross(a, b):
            return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]

        def normalize(u):
            length = math.sqrt(sum(x * x for x in u))
            return [x / length for x in u] if length > 1e-8 else u

        up  = normalize(up)
        arm = self._rotate_vec(arm, up, -h * self.ROTATE_SPEED * self.sensitivity)

        right = normalize(cross(up, arm))
        arm   = self._rotate_vec(arm, right, v * self.ROTATE_SPEED * self.sensitivity)

        new_up = normalize(cross(arm, right))
        camera.SetPosition(*[foc[i] + arm[i] for i in range(3)])
        camera.SetViewUp(*new_up)

    @staticmethod
    def _apply_zoom(camera, amount) -> None:
        camera.Dolly(1.0 + amount)
        camera.OrthogonalizeViewUp()

    def _apply_roll(self, camera, roll) -> None:
        pos = list(camera.GetPosition())
        foc = list(camera.GetFocalPoint())
        up  = list(camera.GetViewUp())
        view = [foc[i] - pos[i] for i in range(3)]
        length = math.sqrt(sum(x * x for x in view))
        axis = [x / length for x in view]
        new_up = self._rotate_vec(up, axis, roll * self.ROTATE_SPEED * self.sensitivity)
        camera.SetViewUp(*new_up)

    # ------------------------------------------------------------------
    # Poll (called by QTimer) — hardware-independent
    # ------------------------------------------------------------------

    def _poll(self) -> None:
        inp = self._controller.get_input()
        if inp is None:
            return

        h    = inp["h"]
        v    = inp["v"]
        roll = inp["roll"]

        zoom_in  = inp["zoom_in"]
        zoom_out = inp["zoom_out"]

        if inp["mode_translate"]:
            if self._mode != self.MODE_TRANSLATE:
                self._mode = self.MODE_TRANSLATE
                logging.info("[JoystickControl] Mode: TRANSLATE")
                if self.modeChangedCallback:
                    self.modeChangedCallback(self._mode)
            return
        if inp["mode_rotate"]:
            if self._mode != self.MODE_ROTATE:
                self._mode = self.MODE_ROTATE
                logging.info("[JoystickControl] Mode: ROTATE")
                if self.modeChangedCallback:
                    self.modeChangedCallback(self._mode)
            return

        camera = self._get_camera()

        if inp["reset"]:
            view = self._get_three_d_view()
            view.resetFocalPoint()
            view.renderWindow().Render()
            logging.info("[JoystickControl] View reset.")
            return

        if h != 0 or v != 0:
            if self._mode == self.MODE_TRANSLATE:
                self._apply_pan(camera, h, v)
            elif inp["roll_mode"]:
                if h != 0:
                    self._apply_roll(camera, -h)
            else:
                self._apply_rotate(camera, h, v)

        if roll != 0 and self._mode == self.MODE_ROTATE:
            self._apply_roll(camera, roll)

        if zoom_in > 0.05:
            self._apply_zoom(camera,  self.ZOOM_SPEED * self.sensitivity * zoom_in)
        elif zoom_out > 0.05:
            self._apply_zoom(camera, -self.ZOOM_SPEED * self.sensitivity * zoom_out)

        if h != 0 or v != 0 or roll != 0 or zoom_in > 0.05 or zoom_out > 0.05:
            self._get_three_d_view().renderWindow().Render()


#
# JoystickControlTest
#


class JoystickControlTest(ScriptedLoadableModuleTest):
    def setUp(self):
        slicer.mrmlScene.Clear()

    def runTest(self):
        self.setUp()
        self.test_JoystickControl1()

    def test_JoystickControl1(self):
        self.delayDisplay("Controller hardware tests are not automated.")
        self.delayDisplay("Test passed")
