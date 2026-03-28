import logging
import math
import time

import slicer
from slicer.i18n import tr as _
from slicer.i18n import translate
from slicer.ScriptedLoadableModule import *

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
Controls the 3D view camera using a right Joy-Con controller connected via Bluetooth.
<ul>
  <li>Stick: pan or rotate camera</li>
  <li>ZR: zoom in &nbsp; R: zoom out</li>
  <li>Y: translation mode &nbsp; X: rotation mode</li>
  <li>A: recalibrate stick center</li>
  <li>+: reset view</li>
</ul>
""")
        self.parent.acknowledgementText = ""


#
# JoystickControlWidget
#


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

        self.ui.enableCheckBox.connect("toggled(bool)", self.onEnableToggled)
        self.ui.sensitivitySlider.connect("valueChanged(double)", self.onSensitivityChanged)

        # Configure camera node selector
        self.ui.cameraNodeComboBox.setMRMLScene(slicer.mrmlScene)
        self.ui.cameraNodeComboBox.nodeTypes = ["vtkMRMLCameraNode"]
        self.ui.cameraNodeComboBox.addEnabled = False
        self.ui.cameraNodeComboBox.removeEnabled = False
        self.ui.cameraNodeComboBox.noneEnabled = True
        self.ui.cameraNodeComboBox.noneDisplay = "(first 3D view)"
        self.ui.cameraNodeComboBox.connect("currentNodeChanged(vtkMRMLNode*)", self.onCameraNodeChanged)
        self.logic.cameraNode = self.ui.cameraNodeComboBox.currentNode()

        # Restore saved sensitivity (default 1.0)
        sensitivity = float(slicer.app.settings().value("JoystickControl/sensitivity", 1.0))
        self.ui.sensitivitySlider.value = sensitivity
        self.logic.sensitivity = sensitivity

    def cleanup(self) -> None:
        if self.logic:
            self.logic.stopControl()

    def onEnableToggled(self, checked: bool) -> None:
        if checked:
            try:
                self.logic.startControl()
                side = "Left" if self.logic._is_left else "Right"
                self.ui.statusLabel.text = f"Active ({side} Joy-Con) — Mode: ROTATE"
                self._updateMappingLabel()
            except Exception as e:
                slicer.util.errorDisplay(f"Failed to connect to Joy-Con: {e}")
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


#
# JoystickControlLogic
#


class JoystickControlLogic(ScriptedLoadableModuleLogic):
    # --- Config ---
    POLL_INTERVAL_MS = 10    # ~100 Hz — drain the BT HID buffer faster
    DEADZONE         = 0.15  # tighter deadzone for quicker response
    TRANSLATE_SPEED  = 2.0
    ROTATE_SPEED     = 1.5   # degrees per tick at full deflection
    ZOOM_SPEED       = 0.05
    STICK_MAX        = 1400  # approx half-range of 12-bit stick
    CALIB_SAMPLES    = 30    # samples to average at startup
    CALIB_DELAY      = 0.02  # seconds between calibration samples

    MODE_TRANSLATE = "translate"
    MODE_ROTATE    = "rotate"

    GYRO_SCALE = 0.004  # gyro units → camera movement per tick

    def __init__(self) -> None:
        ScriptedLoadableModuleLogic.__init__(self)
        self._joycon    = None
        self._is_left   = False
        self._timer     = None
        self._centerH   = 0.0
        self._centerV   = 0.0
        self._mode      = self.MODE_ROTATE
        self.sensitivity = 1.0
        self.cameraNode  = None   # vtkMRMLCameraNode; None → use first 3D widget
        self._freehand  = False   # True when gyro (freehand) mode is active
        self._sl_prev   = False   # previous SL button state for edge detection
        self._sr_prev   = False   # previous SR button state for edge detection

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def startControl(self) -> None:
        """Connect to a Joy-Con (right preferred, left as fallback), calibrate, and start polling."""
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
        self._mode     = self.MODE_ROTATE
        self._freehand = False
        self._sl_prev  = False
        self._sr_prev  = False

        self._timer = QtCore.QTimer()
        self._timer.timeout.connect(self._poll)
        self._timer.start(self.POLL_INTERVAL_MS)
        mapping = self.getButtonMapping()
        summary = "  ".join(f"{a}={b}" for a, b in mapping.items())
        logging.info(f"[JoyCon] Active. {summary}")

    def getButtonMapping(self) -> dict:
        """Return a dict of action → button name for the connected controller."""
        if self._is_left:
            return {
                "Pan / rotate":        "Stick",
                "Zoom in":             "ZL",
                "Zoom out":            "L",
                "Translate mode":      "Right arrow",
                "Rotate mode":         "Up arrow",
                "Recalibrate":         "Down arrow",
                "Reset view":          "−  (minus)",
                "Toggle freehand/gyro": "SL",
            }
        else:
            return {
                "Pan / rotate":        "Stick",
                "Zoom in":             "ZR",
                "Zoom out":            "R",
                "Translate mode":      "Y",
                "Rotate mode":         "X",
                "Recalibrate":         "A",
                "Reset view":          "+  (plus)",
                "Toggle freehand/gyro": "SR",
            }

    def stopControl(self) -> None:
        """Stop polling and release the Joy-Con."""
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self._joycon  = None
        self._is_left = False
        logging.info("[JoyCon] Stopped.")

    # ------------------------------------------------------------------
    # Calibration
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
            stick_key = "left" if self._is_left else "right"
            stick = s["analog-sticks"][stick_key]
            h_vals.append(stick["horizontal"])
            v_vals.append(stick["vertical"])
            time.sleep(delay)
        center_h = sum(h_vals) / len(h_vals)
        center_v = sum(v_vals) / len(v_vals)
        logging.info(f"[JoyCon] Center set: h={center_h:.0f}, v={center_v:.0f}")
        return center_h, center_v

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
        """Rotate vector v around axis by angle_deg using Rodrigues' formula."""
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

        # Azimuth: spin around the camera's own up vector
        up  = normalize(up)
        arm = self._rotate_vec(arm, up, -h * self.ROTATE_SPEED * self.sensitivity)

        # Elevation: orbit around the right axis
        right = normalize(cross(up, arm))
        arm   = self._rotate_vec(arm, right, v * self.ROTATE_SPEED * self.sensitivity)

        # Recompute up perpendicular to arm and right (no roll)
        new_up = normalize(cross(arm, right))

        camera.SetPosition(*[foc[i] + arm[i] for i in range(3)])
        camera.SetViewUp(*new_up)

    @staticmethod
    def _apply_zoom(camera, amount) -> None:
        camera.Dolly(1.0 + amount)
        camera.OrthogonalizeViewUp()

    def _read_gyro(self, status):
        """Return (h, v, roll) from gyro, scaled for camera use.

        For a right Joy-Con held in portrait orientation:
          gyro z  → yaw   (horizontal, h)
          gyro x  → pitch (vertical,   v)
          gyro y  → roll along long axis → camera roll around view normal
        For a left Joy-Con the z and y axes are negated.
        """
        gyro = status.get("gyro", {})
        if not gyro:
            return 0.0, 0.0, 0.0
        gz = gyro.get("z", 0)
        gx = gyro.get("x", 0)
        gy = gyro.get("y", 0)
        scale = self.GYRO_SCALE * self.sensitivity
        sign = -1 if self._is_left else 1
        return -sign * gz * scale, -gx * scale, sign * gy * scale

    def _apply_roll(self, camera, roll) -> None:
        """Rotate the camera's up vector around the view direction by roll."""
        pos = list(camera.GetPosition())
        foc = list(camera.GetFocalPoint())
        up  = list(camera.GetViewUp())

        # View direction (normalised) is the roll axis
        view = [foc[i] - pos[i] for i in range(3)]
        length = math.sqrt(sum(x * x for x in view))
        axis = [x / length for x in view]

        new_up = self._rotate_vec(up, axis, roll * self.ROTATE_SPEED * self.sensitivity)
        camera.SetViewUp(*new_up)

    def _deadzone_axis(self, value, center, max_range, threshold):
        normalized = (value - center) / max_range
        normalized = max(-1.0, min(1.0, normalized))
        if abs(normalized) < threshold:
            return 0.0
        sign = 1 if normalized > 0 else -1
        return sign * (abs(normalized) - threshold) / (1.0 - threshold)

    # ------------------------------------------------------------------
    # Poll (called by QTimer)
    # ------------------------------------------------------------------

    def _poll(self) -> None:
        try:
            # Drain any buffered stale HID reports
            for _ in range(4):
                status = self._joycon.get_status()
        except Exception as e:
            logging.warning(f"[JoyCon] Read error: {e}")
            return

        side   = "left" if self._is_left else "right"
        stick  = status["analog-sticks"][side]
        btn    = status["buttons"][side]
        shared = status["buttons"]["shared"]

        # Button name mapping: right Joy-Con → left Joy-Con equivalent
        #   recalibrate : a      → down
        #   translate   : x      → right arrow
        #   rotate      : y      → up
        #   zoom in     : zr     → zl
        #   zoom out    : r      → l
        #   reset       : plus   → minus  (both live in buttons['shared'])
        if self._is_left:
            btn_recal    = "down"
            btn_trans    = "right"
            btn_rot      = "up"
            btn_zoom_in  = "zl"
            btn_zoom_out = "l"
            btn_reset    = "minus"
        else:
            btn_recal    = "a"
            btn_trans    = "y"
            btn_rot      = "x"
            btn_zoom_in  = "zr"
            btn_zoom_out = "r"
            btn_reset    = "plus"

        # SL (left) / SR (right) button — freehand (gyro) mode active while held
        if self._is_left:
            sl_now = bool(btn.get("sl", 0))
            if sl_now != self._sl_prev:
                self._freehand = sl_now
                logging.info(f"[JoyCon] Freehand mode: {'ON' if self._freehand else 'OFF'}")
            self._sl_prev = sl_now
        else:
            sr_now = bool(btn.get("sr", 0))
            if sr_now != self._sr_prev:
                self._freehand = sr_now
                logging.info(f"[JoyCon] Freehand mode: {'ON' if self._freehand else 'OFF'}")
            self._sr_prev = sr_now

        # Recalibrate
        if btn.get(btn_recal, 0):
            self._centerH, self._centerV = self._calibrate(samples=10)
            return

        # Mode switching
        if btn.get(btn_trans, 0):
            if self._mode != self.MODE_TRANSLATE:
                self._mode = self.MODE_TRANSLATE
                logging.info("[JoyCon] Mode: TRANSLATE")
            return
        if btn.get(btn_rot, 0):
            if self._mode != self.MODE_ROTATE:
                self._mode = self.MODE_ROTATE
                logging.info("[JoyCon] Mode: ROTATE")
            return

        stick_key     = "l-stick" if self._is_left else "r-stick"
        stick_pressed = bool(shared.get(stick_key, 0))

        if self._freehand:
            v, roll, h = self._read_gyro(status)
            if self._is_left:
                v = -v  # invert pitch for more intuitive control
                h = -h  # invert yaw to match stick direction
        else:
            roll = 0.0
            h = self._deadzone_axis(stick.get("horizontal", self._centerH), self._centerH, self.STICK_MAX, self.DEADZONE)
            v = self._deadzone_axis(stick.get("vertical",   self._centerV), self._centerV, self.STICK_MAX, self.DEADZONE)

        zoom_in  = btn.get(btn_zoom_in,  0)
        zoom_out = btn.get(btn_zoom_out, 0)
        reset    = shared.get(btn_reset, 0)

        camera = self._get_camera()

        if reset:
            view = self._get_three_d_view()
            view.resetFocalPoint()
            view.renderWindow().Render()
            logging.info("[JoyCon] View reset.")
            return

        if h != 0 or v != 0:
            if self._mode == self.MODE_TRANSLATE:
                self._apply_pan(camera, h, v)
            elif stick_pressed:
                # Stick held down: left/right spins around view normal; up/down still elevates
                if h != 0:
                    self._apply_roll(camera, -h)
                # if v != 0:
                #     self._apply_rotate(camera, 0, v)
            else:
                self._apply_rotate(camera, h, v)

        if roll != 0 and self._freehand and self._mode == self.MODE_ROTATE:
            self._apply_roll(camera, roll)

        if zoom_in:
            self._apply_zoom(camera,  self.ZOOM_SPEED * self.sensitivity)
        elif zoom_out:
            self._apply_zoom(camera, -self.ZOOM_SPEED * self.sensitivity)

        if h != 0 or v != 0 or roll != 0 or zoom_in or zoom_out:
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
        self.delayDisplay("JoyCon hardware tests are not automated.")
        self.delayDisplay("Test passed")
