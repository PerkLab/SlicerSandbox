"""SlicerWeb host of the Matplotlib layout view.

Use the platform-independent API of :mod:`InteractiveMatplotlibLib.view` rather than this
module directly.

SlicerWeb, Slicer running in a web browser, has no Qt widgets and no layout view factories.
Its layout manager makes a browser view (``vtkSlicerWebView``) for each slice and 3D view
node of the layout once the page has a ``<canvas>`` for it. The Matplotlib view is therefore
a 3D view node of its own, ``<view class="vtkMRMLViewNode" singletontag="matplotlibview">``.
While a figure is shown, the canvas draws in a renderer above the other renderers of the
view, which stop drawing, and takes over the mouse and keyboard input of the view.

The page makes the browser view after the layout is shown and makes a new one when the
layout changes, so each figure keeps one
:class:`~InteractiveMatplotlibLib.vtkcanvas.FigureCanvasVTK`, which is attached to whichever
view is current.
"""

import qt  # SlicerWeb's Qt compatibility layer: QTimer runs on browser timers.
import slicer
from matplotlib.backend_bases import key_press_handler

from InteractiveMatplotlibLib.vtkcanvas import FigureCanvasVTK, NavigationToolbar2VTK

__all__ = [
    "MatplotlibWebView",
    "createView",
    "layoutElement",
]


def _devicePixelRatio():
    try:
        import js

        return float(js.window.devicePixelRatio or 1.0)
    except Exception:
        return 1.0


class MatplotlibWebView:
    """A Matplotlib figure shown in a SlicerWeb layout view.

    It has the figure API of the desktop
    :class:`~InteractiveMatplotlibLib.qtview.MatplotlibViewWidget`. Navigation uses
    Matplotlib's keyboard shortcuts or the :meth:`toolbar`, which has no user interface
    of its own.
    """

    #: How often to check whether the page has made or replaced the browser view, in ms.
    POLL_INTERVAL_MS = 500

    def __init__(self, tag):
        self._tag = tag
        self._canvas = None
        self._toolbar = None
        self._view = None
        self._hiddenRenderers = []
        # The layout manager announces a new layout once its views exist. The timer also
        # catches views that are made later or made again (for example after the browser
        # lost the WebGL context).
        slicer.app.layoutManager().layoutChanged.connect(self._sync)
        self._timer = qt.QTimer()
        self._timer.setInterval(self.POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._sync)

    def view(self):
        """Return the ``vtkSlicerWebView`` the figure is shown in, or ``None``."""
        return self._view

    def canvas(self):
        """Return the :class:`~InteractiveMatplotlibLib.vtkcanvas.FigureCanvasVTK` of the shown figure."""
        return self._canvas

    def toolbar(self):
        """Return the :class:`~InteractiveMatplotlibLib.vtkcanvas.NavigationToolbar2VTK` of the shown figure."""
        return self._toolbar

    def figure(self):
        """Return the shown figure, or ``None``."""
        return self._canvas.figure if self._canvas is not None else None

    def setFigure(self, figure):
        """Show ``figure`` in the view, replacing the previous one, and return its canvas.

        The canvas exists, and can be connected to, before the page has made the view: it
        draws once it is attached. Pass ``None`` to clear the view.
        """
        self._detach()
        self._canvas = None
        self._toolbar = None
        if figure is None:
            self._timer.stop()
            return None
        self._canvas = FigureCanvasVTK(figure, devicePixelRatio=_devicePixelRatio())
        self._toolbar = NavigationToolbar2VTK(self._canvas)
        # Figure managers normally install Matplotlib's keyboard shortcuts.
        self._canvas.mpl_connect("key_press_event", key_press_handler)
        self._canvas.draw_idle()
        self._sync()
        self._timer.start()
        return self._canvas

    def _sync(self, *args):
        """Attach the canvas to the current browser view of the tag, if it changed."""
        if self._canvas is None:
            return
        view = slicer.app.layoutManager().view(self._tag)
        if view is not None and not view.GetInitialized():
            view = None
        if view is self._view:
            return
        self._detach()
        if view is not None:
            self._attach(view)

    def _attach(self, view):
        renderWindow = view.GetRenderWindow()
        renderers = renderWindow.GetRenderers()
        # The view's own renderers (3D scene, orientation marker, ...) only cost time here.
        self._hiddenRenderers = []
        for index in range(renderers.GetNumberOfItems()):
            renderer = renderers.GetItemAsObject(index)
            if renderer.GetDraw():
                renderer.DrawOff()
                self._hiddenRenderers.append(renderer)
        # Above every layer of the view, and clearing what is below it.
        layer = renderWindow.GetNumberOfLayers()
        self._viewLayers = layer
        renderWindow.SetNumberOfLayers(layer + 1)
        canvasRenderer = self._canvas.vtkRenderer
        canvasRenderer.SetLayer(layer)
        canvasRenderer.PreserveColorBufferOff()
        canvasRenderer.PreserveDepthBufferOff()
        self._view = view
        # Renders are coalesced into the browser's next animation frame by the view.
        self._canvas.attach(renderWindow, view.GetInteractor(), renderCallback=view.ScheduleRender)
        self._canvas.set_device_pixel_ratio(_devicePixelRatio())
        self._canvas.draw_idle()

    def _detach(self):
        view, self._view = self._view, None
        if self._canvas is not None:
            self._canvas.detach()
        for renderer in self._hiddenRenderers:
            renderer.DrawOn()
        self._hiddenRenderers = []
        if view is not None and view.GetInitialized():
            view.GetRenderWindow().SetNumberOfLayers(self._viewLayers)
            view.ScheduleRender()


def createView(tag):
    """Create the :class:`MatplotlibWebView` shown wherever a layout has :func:`layoutElement` of ``tag``."""
    return MatplotlibWebView(tag)


def layoutElement(tag):
    """Return the layout description element of the ``tag`` view: a 3D view node of its own."""
    return (f'<view class="vtkMRMLViewNode" singletontag="{tag}">'
            '<property name="viewlabel" action="default">Plot</property></view>')
