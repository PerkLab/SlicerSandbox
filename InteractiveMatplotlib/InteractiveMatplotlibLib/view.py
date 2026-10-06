"""Matplotlib figures in Slicer's view layout, displayed through VTK.

The figure is drawn by :class:`InteractiveMatplotlibLib.vtkcanvas.FigureCanvasVTK` into a
``ctkVTKRenderView``, so it is rendered and receives input exactly like any other VTK view
and does not depend on Qt widgets for display. Only the navigation bar above the view uses
Qt. Show a figure next to the slice views with::

    from matplotlib.figure import Figure
    import InteractiveMatplotlibLib.view

    figure = Figure()
    figure.add_subplot().plot([0, 1, 2], [0, 1, 0])
    InteractiveMatplotlibLib.view.showFigure(figure)

The view is provided by a view factory for a custom layout element (``<matplotlibview>`` by
default), so it can be placed in any custom layout. If the current layout does not contain
the element, :func:`showFigure` switches to :data:`FOUR_UP_LAYOUT_ID`, a Four-Up layout with
the figure in place of the 3D view.

To embed a figure in a module panel, use the Qt canvas of :mod:`InteractiveMatplotlibLib.backend`
instead: each VTK view owns an OpenGL context, which is more than a panel widget needs.

Requires Matplotlib 3.10 or later.
"""

import ctk
import qt
import slicer
from matplotlib.backend_bases import key_press_handler

from InteractiveMatplotlibLib.backend import NavigationToolbar2Slicer, _value
from InteractiveMatplotlibLib.vtkcanvas import FigureCanvasVTK

__all__ = [
    "DEFAULT_TAG",
    "FOUR_UP_LAYOUT_ID",
    "MatplotlibViewWidget",
    "fourUpLayoutDescription",
    "registerLayoutView",
    "showFigure",
    "viewWidget",
]

#: Layout element name of the default Matplotlib view.
DEFAULT_TAG = "matplotlibview"

#: ID of the Four-Up layout with the default Matplotlib view, registered by :func:`showFigure`.
#: Built-in layout IDs are all below 100.
FOUR_UP_LAYOUT_ID = 1001


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


_views = {}


def registerLayoutView(tag=DEFAULT_TAG):
    """Make ``<tag>`` usable as a view in layout descriptions and return its widget.

    The :class:`MatplotlibViewWidget` is created once per tag, and the layout manager shows
    it wherever the current layout contains the ``<tag></tag>`` element.
    """
    if tag not in _views:
        widget = MatplotlibViewWidget()
        factory = slicer.qSlicerSingletonViewFactory()
        factory.setTagName(tag)
        factory.setWidget(widget)
        slicer.app.layoutManager().registerViewFactory(factory)
        _views[tag] = (factory, widget)
    return _views[tag][1]


def viewWidget(tag=DEFAULT_TAG):
    """Return the :class:`MatplotlibViewWidget` registered for ``tag``, or ``None``."""
    entry = _views.get(tag)
    return entry[1] if entry is not None else None


def fourUpLayoutDescription(tag=DEFAULT_TAG):
    """Return a Four-Up layout description with ``<tag>`` in place of the 3D view."""
    return f"""
<layout type="vertical">
 <item>
  <layout type="horizontal">
   <item>
    <view class="vtkMRMLSliceNode" singletontag="Red">
     <property name="orientation" action="default">Axial</property>
     <property name="viewlabel" action="default">R</property>
     <property name="viewcolor" action="default">#F34A33</property>
    </view>
   </item>
   <item><{tag}></{tag}></item>
  </layout>
 </item>
 <item>
  <layout type="horizontal">
   <item>
    <view class="vtkMRMLSliceNode" singletontag="Green">
     <property name="orientation" action="default">Coronal</property>
     <property name="viewlabel" action="default">G</property>
     <property name="viewcolor" action="default">#6EB04B</property>
    </view>
   </item>
   <item>
    <view class="vtkMRMLSliceNode" singletontag="Yellow">
     <property name="orientation" action="default">Sagittal</property>
     <property name="viewlabel" action="default">Y</property>
     <property name="viewcolor" action="default">#EDD54C</property>
    </view>
   </item>
  </layout>
 </item>
</layout>
"""


def showFigure(figure, tag=DEFAULT_TAG):
    """Show ``figure`` in the ``<tag>`` view and return its canvas.

    If the current layout has no ``<tag>`` element and ``tag`` is :data:`DEFAULT_TAG`,
    switch to the :data:`FOUR_UP_LAYOUT_ID` layout. For other tags, switch to a layout
    that contains the element yourself.
    """
    widget = registerLayoutView(tag)
    canvas = widget.setFigure(figure)
    layoutManager = slicer.app.layoutManager()
    layoutNode = layoutManager.layoutLogic().GetLayoutNode()
    if f"<{tag}" not in (layoutNode.GetCurrentLayoutDescription() or "") and tag == DEFAULT_TAG:
        if not layoutNode.IsLayoutDescription(FOUR_UP_LAYOUT_ID):
            layoutNode.AddLayoutDescription(FOUR_UP_LAYOUT_ID, fourUpLayoutDescription(tag))
        layoutManager.setLayout(FOUR_UP_LAYOUT_ID)
    return canvas
