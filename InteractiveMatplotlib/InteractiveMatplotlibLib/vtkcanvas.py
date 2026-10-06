"""Qt-free interactive Matplotlib canvas that renders into a VTK render window.

:class:`FigureCanvasVTK` draws a figure with the Agg rasterizer and shows the result as a
2D image in its own ``vtkRenderer``. All input comes from a
``vtkRenderWindowInteractor`` and all timers are interactor timers. The module imports
only ``vtk`` and ``matplotlib``, never ``qt``, so the same canvas can be hosted by any VTK
render window: a ``ctkVTKRenderView`` in the desktop application (see
:class:`InteractiveMatplotlibLib.view.MatplotlibViewWidget`) or a browser canvas in a Qt-free
build of Slicer.

Minimal use with any render window and interactor::

    from matplotlib.figure import Figure
    from InteractiveMatplotlibLib.vtkcanvas import FigureCanvasVTK

    figure = Figure()
    figure.add_subplot().plot([0, 1, 2], [0, 1, 0])
    canvas = FigureCanvasVTK(figure, renderWindow, devicePixelRatio=1.0)
    canvas.draw()

The canvas takes over mouse and keyboard handling of the interactor: the events it
handles are not passed on to the interactor style. Call :meth:`FigureCanvasVTK.destroy`
to detach it from the render window.

Requires Matplotlib 3.10 or later.
"""

import weakref

import numpy as np

from InteractiveMatplotlibLib._common import require_matplotlib, weak_callback

require_matplotlib("InteractiveMatplotlibLib.vtkcanvas")

from matplotlib import backend_tools, cbook
from matplotlib.backend_bases import (
    KeyEvent,
    LocationEvent,
    MouseButton,
    MouseEvent,
    NavigationToolbar2,
    ResizeEvent,
    TimerBase,
)
from matplotlib.backends.backend_agg import FigureCanvasAgg

import vtk
from vtkmodules.util.numpy_support import numpy_to_vtk

__all__ = [
    "FigureCanvasVTK",
    "NavigationToolbar2VTK",
    "TimerVTK",
]


# ---------------------------------------------------------------------------
# Key, button and cursor translation
# ---------------------------------------------------------------------------

# VTK key symbols (X11 names) that do not map onto their character.
SPECIAL_KEYS = {
    "Escape": "escape",
    "Tab": "tab",
    "BackSpace": "backspace",
    "Return": "enter",
    "KP_Enter": "enter",
    "Insert": "insert",
    "Delete": "delete",
    "Pause": "pause",
    "Sys_Req": "sysreq",
    "Clear": "clear",
    "Home": "home",
    "End": "end",
    "Left": "left",
    "Up": "up",
    "Right": "right",
    "Down": "down",
    "Prior": "pageup",
    "Next": "pagedown",
    "Shift_L": "shift",
    "Shift_R": "shift",
    "Control_L": "control",
    "Control_R": "control",
    "Alt_L": "alt",
    "Alt_R": "alt",
    "Caps_Lock": "caps_lock",
    "Super_L": "super",
    "Super_R": "super",
    "Win_L": "super",
    "Win_R": "super",
    **{f"F{index}": f"f{index}" for index in range(1, 13)},
}

_BUTTON_EVENTS = [
    ("LeftButtonPressEvent", "LeftButtonReleaseEvent", MouseButton.LEFT),
    ("MiddleButtonPressEvent", "MiddleButtonReleaseEvent", MouseButton.MIDDLE),
    ("RightButtonPressEvent", "RightButtonReleaseEvent", MouseButton.RIGHT),
    ("Mouse4ButtonPressEvent", "Mouse4ButtonReleaseEvent", MouseButton.BACK),
    ("Mouse5ButtonPressEvent", "Mouse5ButtonReleaseEvent", MouseButton.FORWARD),
]
_BUTTON_EVENTS = [entry for entry in _BUTTON_EVENTS if hasattr(vtk.vtkCommand, entry[0])]

_CURSOR_MAP = {
    backend_tools.Cursors.MOVE: vtk.VTK_CURSOR_SIZEALL,
    backend_tools.Cursors.HAND: vtk.VTK_CURSOR_HAND,
    backend_tools.Cursors.POINTER: vtk.VTK_CURSOR_ARROW,
    backend_tools.Cursors.SELECT_REGION: vtk.VTK_CURSOR_CROSSHAIR,
    backend_tools.Cursors.RESIZE_HORIZONTAL: vtk.VTK_CURSOR_SIZEWE,
    backend_tools.Cursors.RESIZE_VERTICAL: vtk.VTK_CURSOR_SIZENS,
}


def _modifiers(interactor, exclude=None):
    """Return the Matplotlib names of the modifier keys held during the current event."""
    pressed = [
        ("ctrl", interactor.GetControlKey()),
        ("alt", interactor.GetAltKey()),
        ("shift", interactor.GetShiftKey()),
    ]
    return [name for name, down in pressed if down and name != exclude]


def _mpl_key(interactor):
    """Return the Matplotlib name of the key of the current key event, or ``None``."""
    keysym = interactor.GetKeySym() or ""
    if keysym in SPECIAL_KEYS:
        key = SPECIAL_KEYS[keysym]
        exclude = "ctrl" if key == "control" else key
        return "+".join(_modifiers(interactor, exclude=exclude) + [key])
    keycode = interactor.GetKeyCode()
    character = keycode if isinstance(keycode, str) else chr(keycode or 0)
    if character and (" " <= character < "\x7f" or character >= "\xa0"):
        # The character already carries the effect of shift, as in the Qt backend.
        modifiers = _modifiers(interactor, exclude="shift")
        key = character
    elif len(keysym) == 1:
        # Control combinations produce control characters; fall back to the symbol.
        key = keysym.upper() if interactor.GetShiftKey() else keysym.lower()
        modifiers = _modifiers(interactor, exclude="shift")
    elif keysym:
        modifiers = _modifiers(interactor)
        key = keysym.lower()
    else:
        return None
    return "+".join(modifiers + [key])


# ---------------------------------------------------------------------------
# Timer
# ---------------------------------------------------------------------------

class TimerVTK(TimerBase):
    """`.TimerBase` implementation driven by ``vtkRenderWindowInteractor`` timers."""

    def __init__(self, interactor, *args, **kwargs):
        self._interactor = interactor
        self._timer_id = None
        self._observer = None
        super().__init__(*args, **kwargs)

    def _timer_start(self):
        self._timer_stop()
        interactor = self._interactor
        if interactor is None:
            return
        callback = weak_callback(self._on_vtk_timer, forward_arguments=True)
        # The desktop interactor passes the id of the expired timer as call data.
        callback.CallDataType = vtk.VTK_INT
        self._observer = interactor.AddObserver("TimerEvent", callback)
        interval = max(int(self._interval), 0)
        if self._single:
            self._timer_id = interactor.CreateOneShotTimer(interval)
        else:
            self._timer_id = interactor.CreateRepeatingTimer(interval)

    def _timer_stop(self):
        # Also called from TimerBase.__del__, possibly on a partially constructed object.
        interactor = getattr(self, "_interactor", None)
        timer_id, self._timer_id = getattr(self, "_timer_id", None), None
        observer, self._observer = getattr(self, "_observer", None), None
        if interactor is None:
            return
        if timer_id is not None:
            # Returns 0 if the interactor already removed an expired one-shot timer.
            interactor.DestroyTimer(timer_id)
        if observer is not None:
            interactor.RemoveObserver(observer)

    def _timer_set_interval(self):
        if self._timer_id is not None:
            self._timer_start()

    def _timer_set_single_shot(self):
        if self._timer_id is not None:
            self._timer_start()

    def _on_vtk_timer(self, caller, event, timer_id=None):
        if timer_id is None:
            timer_id = caller.GetTimerEventId()
        if self._timer_id is None or timer_id != self._timer_id:
            return
        if self._single:
            self._timer_stop()
        self._on_timer()


# ---------------------------------------------------------------------------
# Canvas
# ---------------------------------------------------------------------------

def _detach(interactor, observers, renderWindow, renderer):
    """Remove everything a canvas added to its render window and interactor."""
    for target, tag in observers:
        target.RemoveObserver(tag)
    observers.clear()
    if renderWindow is not None and renderer is not None:
        renderWindow.RemoveRenderer(renderer)


class FigureCanvasVTK(FigureCanvasAgg):
    """Agg-rendered Matplotlib canvas displayed in a VTK render window.

    Parameters
    ----------
    figure : `~matplotlib.figure.Figure`, optional
        The figure to display. A new figure is created when omitted.
    renderWindow : vtkRenderWindow
        The render window the figure is displayed in. The canvas adds its own renderer,
        which covers the whole window.
    interactor : vtkRenderWindowInteractor, optional
        Source of mouse, keyboard and timer events. Defaults to the interactor of
        ``renderWindow``. Without an interactor the canvas is display-only.
    devicePixelRatio : float, default: 1.0
        Ratio of physical to logical pixels of the window, used to scale fonts and
        line widths on high-DPI screens. VTK sizes and positions are in physical pixels.
    """

    #: Interactor events translated into Matplotlib events, besides the button events.
    _HANDLED_EVENTS = (
        "MouseMoveEvent",
        "MouseWheelForwardEvent",
        "MouseWheelBackwardEvent",
        "KeyPressEvent",
        "KeyReleaseEvent",
        "CharEvent",
        "EnterEvent",
        "LeaveEvent",
    )

    def __init__(self, figure=None, renderWindow=None, interactor=None, devicePixelRatio=1.0):
        if renderWindow is None:
            raise ValueError("FigureCanvasVTK requires a renderWindow")
        super().__init__(figure=figure)
        self._render_window = renderWindow
        self._interactor = interactor if interactor is not None else renderWindow.GetInteractor()
        self._draw_pending = False
        self._is_drawing = False
        self._pressed_buttons = set()
        self._image_array = None  # Keeps the pixels shown by VTK alive.

        self._renderer = vtk.vtkRenderer()
        self._renderer.SetBackground(1.0, 1.0, 1.0)
        self._renderer.InteractiveOff()
        self._image_data = vtk.vtkImageData()
        mapper = vtk.vtkImageMapper()
        mapper.SetInputData(self._image_data)
        mapper.SetColorWindow(255.0)
        mapper.SetColorLevel(127.5)
        self._image_actor = vtk.vtkActor2D()
        self._image_actor.SetMapper(mapper)
        self._image_actor.VisibilityOff()
        self._renderer.AddActor2D(self._image_actor)
        self._rubberband_points = vtk.vtkPoints()
        self._rubberband_actor = self._make_rubberband_actor(self._rubberband_points)
        self._renderer.AddActor2D(self._rubberband_actor)
        renderWindow.AddRenderer(self._renderer)

        self._observers = []
        self._interactor_tags = {}
        self._observe(renderWindow, "WindowResizeEvent", self._on_window_resize)
        if self._interactor is not None:
            # High priority so that the interactor style, which would otherwise rotate
            # the camera or react to its own keyboard shortcuts, sees nothing.
            events = list(self._HANDLED_EVENTS)
            for press, release, _ in _BUTTON_EVENTS:
                events += [press, release]
            for event in events:
                self._interactor_tags[event] = self._observe(
                    self._interactor, event, self._on_interactor_event, 10.0)
        self._finalizer = weakref.finalize(
            self, _detach, self._interactor, self._observers, renderWindow, self._renderer)

        self._idle_timer = None
        if self._interactor is not None:
            self._idle_timer = TimerVTK(self._interactor, interval=0)
            self._idle_timer.single_shot = True
            self._idle_timer.add_callback(weak_callback(self._draw_idle))

        self._set_device_pixel_ratio(devicePixelRatio)
        self._on_window_resize()

    @staticmethod
    def _make_rubberband_actor(points):
        lines = vtk.vtkCellArray()
        lines.InsertNextCell(5)
        for index in (0, 1, 2, 3, 0):
            lines.InsertCellPoint(index)
        for _ in range(4):
            points.InsertNextPoint(0.0, 0.0, 0.0)
        polydata = vtk.vtkPolyData()
        polydata.SetPoints(points)
        polydata.SetLines(lines)
        mapper = vtk.vtkPolyDataMapper2D()
        mapper.SetInputData(polydata)
        actor = vtk.vtkActor2D()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor(0.0, 0.0, 0.0)
        actor.VisibilityOff()
        return actor

    def _observe(self, target, event, method, priority=0.0):
        tag = target.AddObserver(event, weak_callback(method, forward_arguments=True), priority)
        self._observers.append((target, tag))
        return tag

    # -- public API --------------------------------------------------------
    @property
    def renderWindow(self):
        """The ``vtkRenderWindow`` the figure is displayed in."""
        return self._render_window

    @property
    def vtkRenderer(self):
        """The ``vtkRenderer`` the canvas draws the figure with."""
        return self._renderer

    def set_device_pixel_ratio(self, ratio):
        """Set the ratio of physical to logical pixels and refit the figure."""
        if self._set_device_pixel_ratio(ratio):
            self._on_window_resize()

    def destroy(self):
        """Detach the canvas from its render window and interactor."""
        if self._idle_timer is not None:
            self._idle_timer.stop()
            self._idle_timer._interactor = None
        self._finalizer()
        self._interactor = None
        if self._render_window is not None:
            self._render_window.Render()
        self._render_window = None

    # -- rendering ---------------------------------------------------------
    def draw(self):
        """Render the figure with Agg and show it in the render window."""
        if self._is_drawing:
            return
        with cbook._setattr_cm(self, _is_drawing=True):
            super().draw()
        self._show_buffer()

    def draw_idle(self):
        """Coalesce redraw requests and service them from an interactor timer."""
        if self._draw_pending or self._is_drawing:
            return
        if self._idle_timer is None:
            self.draw()
            return
        self._draw_pending = True
        self._idle_timer.start()

    def _draw_idle(self):
        with self._idle_draw_cntx():
            if not self._draw_pending:
                return
            self._draw_pending = False
            if self._render_window is None:
                return
            try:
                self.draw()
            except Exception:
                # An exception escaping a VTK observer would be swallowed without a trace.
                import traceback
                traceback.print_exc()

    def flush_events(self):
        """Carry out a pending :meth:`draw_idle` immediately."""
        self._draw_idle()

    def blit(self, bbox=None):
        # docstring inherited: the whole buffer is uploaded, which is fast at plot sizes.
        self._show_buffer()

    def _show_buffer(self):
        if self._render_window is None:
            return
        try:
            pixels = np.asarray(self.buffer_rgba())
        except (AttributeError, RuntimeError, ValueError):
            return  # Nothing has been rendered yet.
        if pixels.ndim != 3 or pixels.size == 0:
            return
        height, width = pixels.shape[:2]
        # Agg stores the top row first, VTK the bottom row.
        self._image_array = np.ascontiguousarray(pixels[::-1]).reshape(-1, 4)
        scalars = numpy_to_vtk(self._image_array, deep=False)
        self._image_data.SetDimensions(width, height, 1)
        self._image_data.GetPointData().SetScalars(scalars)
        self._image_data.Modified()
        self._image_actor.VisibilityOn()
        self._render()

    def _render(self):
        if self._render_window is not None:
            self._render_window.Render()

    def drawRectangle(self, rect):
        """Show or hide the zoom-to-rectangle rubberband.

        ``rect`` is ``(x, y, width, height)`` in physical pixels with the origin in the
        top-left corner, as passed by `.NavigationToolbar2.draw_rubberband` overrides.
        """
        if rect is None:
            self._rubberband_actor.VisibilityOff()
        else:
            x0, top, width, height = rect
            window_height = self.figure.bbox.height
            y0 = window_height - top - height
            corners = [(x0, y0), (x0 + width, y0), (x0 + width, y0 + height), (x0, y0 + height)]
            for index, (x, y) in enumerate(corners):
                self._rubberband_points.SetPoint(index, x, y, 0.0)
            self._rubberband_points.Modified()
            self._rubberband_actor.VisibilityOn()
        self._render()

    # -- geometry ----------------------------------------------------------
    def _on_window_resize(self, *args):
        if self._render_window is None or self.figure is None:
            return
        width, height = self._render_window.GetSize()
        if width <= 0 or height <= 0:
            return
        dpi = self.figure.dpi
        if (width, height) == tuple(int(value) for value in self.figure.bbox.size):
            return
        self.figure.set_size_inches(width / dpi, height / dpi, forward=False)
        ResizeEvent("resize_event", self)._process()
        self.draw_idle()

    # -- input -------------------------------------------------------------
    def _event_coords(self):
        x, y = self._interactor.GetEventPosition()
        return x, y

    def _on_interactor_event(self, caller, event):
        if self.figure is None or self._interactor is None:
            return
        handler = getattr(self, "_handle_" + event, None)
        if handler is None:
            for press, release, button in _BUTTON_EVENTS:
                if event == press:
                    self._handle_button(button, pressed=True)
                    break
                if event == release:
                    self._handle_button(button, pressed=False)
                    break
        else:
            handler()
        # Keep the interactor style from also processing the event.
        tag = self._interactor_tags.get(event)
        command = caller.GetCommand(tag) if tag is not None else None
        if command is not None:
            command.SetAbortFlag(1)

    def _handle_button(self, button, pressed):
        interactor = self._interactor
        if pressed:
            self._pressed_buttons.add(button)
            MouseEvent(
                "button_press_event", self, *self._event_coords(), button,
                dblclick=interactor.GetRepeatCount() > 0,
                modifiers=_modifiers(interactor))._process()
        else:
            self._pressed_buttons.discard(button)
            MouseEvent(
                "button_release_event", self, *self._event_coords(), button,
                modifiers=_modifiers(interactor))._process()

    def _handle_MouseMoveEvent(self):
        MouseEvent(
            "motion_notify_event", self, *self._event_coords(),
            buttons=set(self._pressed_buttons),
            modifiers=_modifiers(self._interactor))._process()

    def _forward_scroll(self, step):
        MouseEvent(
            "scroll_event", self, *self._event_coords(), step=step,
            modifiers=_modifiers(self._interactor))._process()

    def _handle_MouseWheelForwardEvent(self):
        self._forward_scroll(1)

    def _handle_MouseWheelBackwardEvent(self):
        self._forward_scroll(-1)

    def _forward_key(self, name):
        key = _mpl_key(self._interactor)
        if key is not None:
            KeyEvent(name, self, key, *self._event_coords())._process()

    def _handle_KeyPressEvent(self):
        self._forward_key("key_press_event")

    def _handle_KeyReleaseEvent(self):
        self._forward_key("key_release_event")

    def _handle_CharEvent(self):
        pass  # Only suppressed: the key press already reported the character.

    def _handle_EnterEvent(self):
        LocationEvent(
            "figure_enter_event", self, *self._event_coords(),
            modifiers=_modifiers(self._interactor))._process()

    def _handle_LeaveEvent(self):
        self._pressed_buttons.clear()
        LocationEvent(
            "figure_leave_event", self, *self._event_coords(),
            modifiers=_modifiers(self._interactor))._process()

    # -- interaction -------------------------------------------------------
    def set_cursor(self, cursor):
        # docstring inherited
        if self._render_window is not None:
            self._render_window.SetCurrentCursor(_CURSOR_MAP.get(cursor, vtk.VTK_CURSOR_DEFAULT))

    def new_timer(self, *args, **kwargs):
        # docstring inherited
        return TimerVTK(self._interactor, *args, **kwargs)


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

class NavigationToolbar2VTK(NavigationToolbar2):
    """Navigation toolbar without a user interface of its own.

    It provides the home/back/forward/pan/zoom/save logic of `.NavigationToolbar2` for any
    canvas that implements ``drawRectangle``, so a host can drive it from its own buttons.
    The keyboard shortcuts of Matplotlib (``h``, ``p``, ``o``, ...) also use it. The latest
    status message, usually the cursor coordinates, is kept in :attr:`message`.
    """

    def __init__(self, canvas):
        self.message = ""
        super().__init__(canvas)

    def set_message(self, s):
        # docstring inherited
        self.message = s

    def draw_rubberband(self, event, x0, y0, x1, y1):
        # docstring inherited
        height = self.canvas.figure.bbox.height
        self.canvas.drawRectangle(
            (min(x0, x1), height - max(y0, y1), abs(x1 - x0), abs(y1 - y0)))

    def remove_rubberband(self):
        # docstring inherited
        self.canvas.drawRectangle(None)
