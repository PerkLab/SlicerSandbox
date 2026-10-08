"""Desktop host of the Matplotlib layout view: a ``ctkVTKRenderView`` with a Qt navigation bar.

Use the platform-independent API of :mod:`InteractiveMatplotlibLib.view` rather than this
module directly. The figure is drawn by
:class:`InteractiveMatplotlibLib.vtkcanvas.FigureCanvasVTK` into the render view, so it is
rendered and receives input like any other VTK view. Only the navigation bar uses Qt. The
view is provided by a ``qSlicerSingletonViewFactory`` for a custom layout element
(``<matplotlibview>`` by default).
"""

import ctk
import qt
import slicer
from matplotlib.backend_bases import key_press_handler

from InteractiveMatplotlibLib.backend import NavigationToolbar2Slicer, _value
from InteractiveMatplotlibLib.vtkcanvas import FigureCanvasVTK

__all__ = [
    "MatplotlibViewWidget",
    "createView",
    "layoutElement",
]

class MatplotlibViewWidget(qt.QWidget):
    """A VTK render view showing a Matplotlib figure, with a navigation bar above it."""

    def __init__(self, parent=None):
        if parent is None:
            qt.QWidget.__init__(self)
        else:
            qt.QWidget.__init__(self, parent)
        self._canvas = None
        self._toolbar = None

        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._controllerBar = qt.QFrame()
        self._controllerBar.setObjectName("MatplotlibViewControllerBar")
        self._controllerLayout = qt.QHBoxLayout(self._controllerBar)
        self._controllerLayout.setContentsMargins(0, 0, 0, 0)
        self._controllerLayout.setSpacing(0)
        layout.addWidget(self._controllerBar)

        self._renderView = ctk.ctkVTKRenderView()
        self._renderView.orientationWidgetVisible = False
        self._renderView.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Expanding)
        # Input goes to the OpenGL widget inside the view, which needs focus for key events.
        for child in self._renderView.findChildren(qt.QWidget):
            child.setFocusPolicy(qt.Qt.StrongFocus)
            child.setMouseTracking(True)
        layout.addWidget(self._renderView)

    def renderView(self):
        """Return the ``ctkVTKRenderView`` the figure is displayed in."""
        return self._renderView

    def canvas(self):
        """Return the :class:`~InteractiveMatplotlibLib.vtkcanvas.FigureCanvasVTK` of the shown figure."""
        return self._canvas

    def toolbar(self):
        """Return the navigation toolbar of the shown figure."""
        return self._toolbar

    def figure(self):
        """Return the shown figure, or ``None``."""
        return self._canvas.figure if self._canvas is not None else None

    def setFigure(self, figure):
        """Show ``figure`` in the view, replacing the previous one.

        The figure gets a new :class:`~InteractiveMatplotlibLib.vtkcanvas.FigureCanvasVTK`, which is
        returned. Pass ``None`` to clear the view.
        """
        self._clear()
        if figure is None:
            self._renderView.renderWindow().Render()
            return None
        renderWindow = self._renderView.renderWindow()
        self._canvas = FigureCanvasVTK(
            figure, renderWindow, renderWindow.GetInteractor(), self._devicePixelRatio())
        self._toolbar = NavigationToolbar2Slicer(self._canvas)
        self._toolbar.get_widget().setIconSize(qt.QSize(16, 16))
        self._controllerLayout.addWidget(self._toolbar.get_widget())
        # Figure managers normally install Matplotlib's keyboard shortcuts.
        self._canvas.mpl_connect("key_press_event", key_press_handler)
        self._canvas.draw_idle()
        return self._canvas

    def _clear(self):
        if self._toolbar is not None:
            toolbarWidget = self._toolbar.get_widget()
            self._controllerLayout.removeWidget(toolbarWidget)
            toolbarWidget.setParent(None)
            toolbarWidget.deleteLater()
            self._toolbar = None
        if self._canvas is not None:
            self._canvas.destroy()
            self._canvas = None

    def _devicePixelRatio(self):
        return float(_value(self, "devicePixelRatioF"))

    def resizeEvent(self, event):
        # The window may have moved to a screen with a different pixel ratio.
        if self._canvas is not None:
            self._canvas.set_device_pixel_ratio(self._devicePixelRatio())


_factories = {}


def createView(tag):
    """Create the :class:`MatplotlibViewWidget` shown wherever a layout has ``<tag>``."""
    widget = MatplotlibViewWidget()
    factory = slicer.qSlicerSingletonViewFactory()
    factory.setTagName(tag)
    factory.setWidget(widget)
    slicer.app.layoutManager().registerViewFactory(factory)
    _factories[tag] = factory
    return widget


def layoutElement(tag):
    """Return the layout description element of the ``tag`` view."""
    return f"<{tag}></{tag}>"