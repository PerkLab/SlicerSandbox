"""Tests for the Qt-free Matplotlib canvas that renders into a VTK render window.

The tests use an offscreen render window and a generic interactor, so they need neither
Qt nor a visible window. Events are injected the way any VTK host delivers them, with
``SetEventInformation`` followed by ``InvokeEvent``. They are skipped when a supported
matplotlib version is not installed, since it is not part of the Slicer distribution.
"""

import gc
import os
import sys
import unittest
import weakref

import vtk

# Make InteractiveMatplotlibLib importable when the module is not loaded by the application.
_moduleDir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _moduleDir not in sys.path:
    sys.path.insert(0, _moduleDir)

try:
    import numpy as np
    from matplotlib.backend_bases import MouseButton
    from matplotlib.figure import Figure

    # Raises ImportError if the installed matplotlib is too old.
    from InteractiveMatplotlibLib.vtkcanvas import FigureCanvasVTK, NavigationToolbar2VTK

    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


def _make_window(width=400, height=300):
    renderWindow = vtk.vtkRenderWindow()
    renderWindow.SetOffScreenRendering(1)
    renderWindow.SetSize(width, height)
    interactor = vtk.vtkGenericRenderWindowInteractor()
    interactor.SetRenderWindow(renderWindow)
    return renderWindow, interactor


def _invoke(interactor, event, x=0, y=0, ctrl=0, shift=0, keycode="\0", repeat=0, keysym=None):
    interactor.SetEventInformation(int(x), int(y), ctrl, shift, keycode, repeat, keysym)
    interactor.InvokeEvent(event)


def _fire(interactor, timer):
    """Deliver the expiry of ``timer`` the way the desktop interactor does."""
    interactor.InvokeEvent("TimerEvent", timer._timer_id)


@unittest.skipUnless(MATPLOTLIB_AVAILABLE, "matplotlib >= 3.10 is not installed")
class MatplotlibVTKCanvasTest(unittest.TestCase):
    def setUp(self):
        self.renderWindow, self.interactor = _make_window()
        self.figure = Figure(dpi=100)
        self.axes = self.figure.add_subplot()
        t = np.linspace(0, 5, 200)
        self.axes.plot(t, np.cos(2 * np.pi * t) * np.exp(-t))
        self.canvas = FigureCanvasVTK(self.figure, self.renderWindow, self.interactor)
        self.canvas.draw()

    def tearDown(self):
        self.canvas.destroy()
        self.renderWindow.Finalize()

    def _point(self, axes, data):
        return axes.transData.transform(data)

    def test_module_does_not_import_qt(self):
        """The canvas module can run where Qt is not available."""
        import ast
        import inspect

        import InteractiveMatplotlibLib.vtkcanvas

        tree = ast.parse(inspect.getsource(InteractiveMatplotlibLib.vtkcanvas))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertFalse(imported & {"qt", "ctk", "PythonQt", "PyQt5", "PySide2", "PySide6"})

    def test_figure_fills_the_window(self):
        """The figure is sized to the render window."""
        self.assertEqual(self.canvas.get_width_height(physical=True), (400, 300))
        self.assertEqual(self.canvas._image_data.GetDimensions(), (400, 300, 1))

    def test_rendering_reaches_the_window(self):
        """The rendered window shows the figure the right way up."""
        from matplotlib.patches import Rectangle

        figure = Figure(dpi=100, facecolor="white")
        # A red block in the top-left quarter of the figure.
        figure.patches.append(
            Rectangle((0.0, 0.5), 0.5, 0.5, transform=figure.transFigure, color="red"))
        canvas = FigureCanvasVTK(figure, self.renderWindow, self.interactor)
        canvas.draw()
        grabber = vtk.vtkWindowToImageFilter()
        grabber.SetInput(self.renderWindow)
        grabber.ReadFrontBufferOff()
        grabber.Update()
        from vtkmodules.util.numpy_support import vtk_to_numpy

        image = grabber.GetOutput()
        width, height, _ = image.GetDimensions()
        pixels = vtk_to_numpy(image.GetPointData().GetScalars()).reshape(height, width, -1)
        # VTK images start at the bottom row.
        topLeft = pixels[int(height * 0.75), int(width * 0.25), :3]
        bottomLeft = pixels[int(height * 0.25), int(width * 0.25), :3]
        canvas.destroy()
        self.assertGreater(int(topLeft[0]), 200)
        self.assertLess(int(topLeft[1]), 50)
        self.assertGreater(int(bottomLeft[1]), 200)

    def test_resizing_reflows_figure(self):
        """Resizing the render window resizes the figure."""
        self.renderWindow.SetSize(500, 250)
        self.canvas.flush_events()
        self.assertEqual(self.canvas.get_width_height(physical=True), (500, 250))
        self.assertEqual(self.canvas._image_data.GetDimensions(), (500, 250, 1))

    def test_device_pixel_ratio(self):
        """On high-DPI screens the figure uses all physical pixels with scaled fonts."""
        renderWindow, interactor = _make_window(600, 400)
        figure = Figure(dpi=100)
        canvas = FigureCanvasVTK(figure, renderWindow, interactor, devicePixelRatio=2.0)
        canvas.draw()
        self.assertEqual(canvas.get_width_height(physical=True), (600, 400))
        self.assertEqual(canvas.get_width_height(), (300, 200))
        self.assertEqual(figure.dpi, 200)
        canvas.set_device_pixel_ratio(1.0)
        self.assertEqual(figure.dpi, 100)
        self.assertEqual(canvas.get_width_height(physical=True), (600, 400))
        canvas.destroy()
        renderWindow.Finalize()

    def test_interactor_events_are_forwarded_to_matplotlib(self):
        """Interactor events are translated into matplotlib events."""
        received = []
        connect = self.canvas.mpl_connect
        connect("button_press_event", lambda e: received.append(("press", e.button, e.dblclick, e.x, e.y)))
        connect("button_release_event", lambda e: received.append(("release", e.button)))
        connect("motion_notify_event", lambda e: received.append(("motion", frozenset(e.buttons))))
        connect("scroll_event", lambda e: received.append(("scroll", e.step)))
        connect("key_press_event", lambda e: received.append(("key", e.key)))
        connect("figure_enter_event", lambda e: received.append("enter"))
        connect("figure_leave_event", lambda e: received.append("leave"))

        _invoke(self.interactor, "EnterEvent", 100, 100)
        _invoke(self.interactor, "LeftButtonPressEvent", 100, 120)
        _invoke(self.interactor, "MouseMoveEvent", 110, 120)
        _invoke(self.interactor, "LeftButtonReleaseEvent", 110, 120)
        _invoke(self.interactor, "LeftButtonPressEvent", 110, 120, repeat=1)
        _invoke(self.interactor, "RightButtonPressEvent", 110, 120)
        _invoke(self.interactor, "MouseWheelForwardEvent", 110, 120)
        _invoke(self.interactor, "MouseWheelBackwardEvent", 110, 120)
        _invoke(self.interactor, "LeaveEvent", 110, 120)

        self.assertEqual(received[0], "enter")
        self.assertIn(("press", MouseButton.LEFT, False, 100, 120), received)
        self.assertIn(("motion", frozenset({MouseButton.LEFT})), received)
        self.assertIn(("release", MouseButton.LEFT), received)
        self.assertIn(("press", MouseButton.LEFT, True, 110, 120), received)
        self.assertIn(("press", MouseButton.RIGHT, False, 110, 120), received)
        self.assertIn(("scroll", 1), received)
        self.assertIn(("scroll", -1), received)
        self.assertEqual(received[-1], "leave")

    def test_key_names(self):
        """VTK key symbols map onto matplotlib key names."""
        keys = []
        self.canvas.mpl_connect("key_press_event", lambda e: keys.append(e.key))
        _invoke(self.interactor, "KeyPressEvent", keycode="g", keysym="g")
        _invoke(self.interactor, "KeyPressEvent", shift=1, keycode="G", keysym="G")
        _invoke(self.interactor, "KeyPressEvent", ctrl=1, keycode="\x01", keysym="a")
        _invoke(self.interactor, "KeyPressEvent", keycode="\r", keysym="Return")
        _invoke(self.interactor, "KeyPressEvent", shift=1, keysym="Left")
        _invoke(self.interactor, "KeyPressEvent", ctrl=1, keysym="Control_L")
        _invoke(self.interactor, "KeyPressEvent", keycode=" ", keysym="space")
        self.assertEqual(keys, ["g", "G", "ctrl+a", "enter", "shift+left", "control", " "])

    def test_events_do_not_reach_the_interactor_style(self):
        """Handled events are not passed on to lower-priority observers."""
        seen = []
        self.interactor.AddObserver("LeftButtonPressEvent", lambda *a: seen.append(1))
        self.interactor.AddObserver("CharEvent", lambda *a: seen.append(2))
        _invoke(self.interactor, "LeftButtonPressEvent", 10, 10)
        _invoke(self.interactor, "CharEvent", keycode="e", keysym="e")
        self.assertEqual(seen, [])

    def test_picking(self):
        """Clicking on a picker-enabled artist emits a pick event."""
        picked = []
        self.axes.clear()
        self.axes.plot([0, 1, 2, 3], [0, 1, 0, 1], "o-", picker=10)
        self.canvas.mpl_connect("pick_event", lambda e: picked.append(list(e.ind)))
        self.canvas.draw()
        x, y = self._point(self.axes, (1, 1))
        _invoke(self.interactor, "LeftButtonPressEvent", round(x), round(y))
        self.assertTrue(picked)

    def test_interactive_widget(self):
        """matplotlib.widgets receive the forwarded events."""
        from matplotlib.widgets import Slider

        changed = []
        self.figure.subplots_adjust(bottom=0.3)
        sliderAxes = self.figure.add_axes([0.2, 0.1, 0.6, 0.05])
        slider = Slider(sliderAxes, "gain", 0.0, 10.0, valinit=1.0)
        slider.on_changed(changed.append)
        self.canvas.draw()
        x, y = self._point(sliderAxes, (5.0, 0.5))
        _invoke(self.interactor, "LeftButtonPressEvent", round(x), round(y))
        _invoke(self.interactor, "LeftButtonReleaseEvent", round(x), round(y))
        self.assertTrue(changed)
        self.assertAlmostEqual(slider.val, 5.0, places=1)

    def test_zoom_pan_and_home(self):
        """The navigation logic works with the VTK canvas, including the rubberband."""
        toolbar = NavigationToolbar2VTK(self.canvas)
        original = self.axes.get_xlim()

        toolbar.zoom()
        _invoke(self.interactor, "LeftButtonPressEvent", 120, 100)
        _invoke(self.interactor, "MouseMoveEvent", 250, 200)
        self.assertTrue(self.canvas._rubberband_actor.GetVisibility())
        _invoke(self.interactor, "LeftButtonReleaseEvent", 250, 200)
        self.assertFalse(self.canvas._rubberband_actor.GetVisibility())
        toolbar.zoom()
        zoomed = self.axes.get_xlim()
        self.assertNotEqual(zoomed, original)

        toolbar.pan()
        _invoke(self.interactor, "LeftButtonPressEvent", 200, 150)
        _invoke(self.interactor, "MouseMoveEvent", 100, 150)
        _invoke(self.interactor, "LeftButtonReleaseEvent", 100, 150)
        toolbar.pan()
        self.assertNotEqual(self.axes.get_xlim(), zoomed)

        toolbar.home()
        self.assertEqual(self.axes.get_xlim(), original)

        _invoke(self.interactor, "MouseMoveEvent", *self._point(self.axes, (2.5, 0)))
        self.assertIn("2.50", toolbar.message)

    def test_keyboard_shortcuts(self):
        """Matplotlib's default key bindings work without any toolbar widgets."""
        from matplotlib.backend_bases import key_press_handler

        NavigationToolbar2VTK(self.canvas)
        self.canvas.mpl_connect("key_press_event", key_press_handler)
        x, y = self._point(self.axes, (2.5, 0))
        _invoke(self.interactor, "KeyPressEvent", x, y, keycode="k", keysym="k")
        self.assertEqual(self.axes.get_xscale(), "log")

    def test_draw_idle_is_coalesced_on_a_timer(self):
        """draw_idle schedules one interactor timer and draws when it expires."""
        draws = []
        self.canvas.mpl_connect("draw_event", lambda e: draws.append(1))
        self.canvas.draw_idle()
        self.canvas.draw_idle()
        self.assertEqual(draws, [])
        _fire(self.interactor, self.canvas._idle_timer)
        self.assertEqual(draws, [1])

    def test_timer_drives_callbacks(self):
        """Canvas timers fire on interactor timer events and stop cleanly."""
        ticks = []
        timer = self.canvas.new_timer(interval=10)
        timer.add_callback(lambda: ticks.append(1))
        timer.start()
        timerId = timer._timer_id
        self.assertIsNotNone(timerId)
        _fire(self.interactor, timer)
        _fire(self.interactor, timer)
        timer.stop()
        self.interactor.InvokeEvent("TimerEvent", timerId)
        self.assertEqual(ticks, [1, 1])

        single = self.canvas.new_timer(interval=10)
        single.single_shot = True
        single.add_callback(lambda: ticks.append(2))
        single.start()
        _fire(self.interactor, single)
        self.assertIsNone(single._timer_id)
        self.assertEqual(ticks, [1, 1, 2])

    def test_cursor(self):
        """Cursor changes are forwarded to the render window."""
        from matplotlib.backend_tools import Cursors

        self.canvas.set_cursor(Cursors.HAND)
        self.assertEqual(self.renderWindow.GetCurrentCursor(), vtk.VTK_CURSOR_HAND)
        self.canvas.set_cursor(Cursors.POINTER)
        self.assertEqual(self.renderWindow.GetCurrentCursor(), vtk.VTK_CURSOR_ARROW)

    def test_destroy_detaches_from_the_window(self):
        """After destroy() the canvas no longer reacts to the interactor."""
        received = []
        self.canvas.mpl_connect("button_press_event", lambda e: received.append(1))
        self.canvas.destroy()
        _invoke(self.interactor, "LeftButtonPressEvent", 10, 10)
        self.assertEqual(received, [])
        self.assertEqual(self.renderWindow.GetRenderers().GetNumberOfItems(), 0)

    def test_unreferenced_canvas_is_released(self):
        """Observers, timers and the toolbar do not keep the canvas alive, and a released
        canvas removes its renderer from the window.
        """
        renderWindow, interactor = _make_window()
        canvas = FigureCanvasVTK(Figure(), renderWindow, interactor)
        canvas.new_timer(interval=10).start()
        canvas.draw_idle()
        NavigationToolbar2VTK(canvas)
        canvasRef = weakref.ref(canvas)
        del canvas
        gc.collect()
        self.assertIsNone(canvasRef())
        self.assertEqual(renderWindow.GetRenderers().GetNumberOfItems(), 0)
        renderWindow.Finalize()


if __name__ == "__main__":
    unittest.main()
