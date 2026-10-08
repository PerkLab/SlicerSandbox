"""Matplotlib figures in Slicer's view layout, displayed through VTK.

The figure is drawn by :class:`InteractiveMatplotlibLib.vtkcanvas.FigureCanvasVTK` into a VTK
view, so it is rendered and receives input like any other view. The same API works in
desktop Slicer and in SlicerWeb (Slicer in a web browser). Show a figure next to the slice
views with::

    from matplotlib.figure import Figure
    import InteractiveMatplotlibLib.view

    figure = Figure()
    figure.add_subplot().plot([0, 1, 2], [0, 1, 0])
    InteractiveMatplotlibLib.view.showFigure(figure)

If the current layout does not contain the view, :func:`showFigure` switches to
:data:`FOUR_UP_LAYOUT_ID`, a Four-Up layout with the figure in place of the 3D view. To
place the view in a custom layout, use :func:`layoutElement` in its description.

- In desktop Slicer the view is a ``ctkVTKRenderView`` with a Qt navigation bar, provided by
  a view factory for a custom layout element (``<matplotlibview>`` by default). See
  :mod:`InteractiveMatplotlibLib.qtview`.
- In SlicerWeb the view is a browser view of the layout, and navigation uses Matplotlib's
  keyboard shortcuts or the module panel. See :mod:`InteractiveMatplotlibLib.webview`.

To embed a figure in a desktop module panel, use the Qt canvas of
:mod:`InteractiveMatplotlibLib.backend` instead: each VTK view owns an OpenGL context, which
is more than a panel widget needs.

Requires Matplotlib 3.10 or later.
"""

import slicer

from InteractiveMatplotlibLib import isSlicerWeb

if isSlicerWeb():
    from InteractiveMatplotlibLib import webview as _host
else:
    from InteractiveMatplotlibLib import qtview as _host
    from InteractiveMatplotlibLib.qtview import MatplotlibViewWidget  # noqa: F401

__all__ = [
    "DEFAULT_TAG",
    "FOUR_UP_LAYOUT_ID",
    "fourUpLayoutDescription",
    "layoutElement",
    "registerLayoutView",
    "showFigure",
    "viewWidget",
]

#: Name of the default Matplotlib view in layout descriptions.
DEFAULT_TAG = "matplotlibview"

#: ID of the Four-Up layout with the default Matplotlib view, registered by :func:`showFigure`.
#: Built-in layout IDs are all below 100.
FOUR_UP_LAYOUT_ID = 1001

_views = {}


def registerLayoutView(tag=DEFAULT_TAG):
    """Make the ``tag`` view usable in layout descriptions and return it.

    The view is created once per tag and shown wherever the current layout contains
    :func:`layoutElement` of ``tag``. It is a
    :class:`~InteractiveMatplotlibLib.qtview.MatplotlibViewWidget` in desktop Slicer and a
    :class:`~InteractiveMatplotlibLib.webview.MatplotlibWebView` in SlicerWeb. Both have
    ``setFigure()``, ``figure()``, ``canvas()`` and ``toolbar()``.
    """
    if tag not in _views:
        _views[tag] = _host.createView(tag)
    return _views[tag]


def viewWidget(tag=DEFAULT_TAG):
    """Return the view registered for ``tag``, or ``None``."""
    return _views.get(tag)


def layoutElement(tag=DEFAULT_TAG):
    """Return the layout description element that places the ``tag`` view."""
    return _host.layoutElement(tag)


def fourUpLayoutDescription(tag=DEFAULT_TAG):
    """Return a Four-Up layout description with the ``tag`` view in place of the 3D view."""
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
   <item>{layoutElement(tag)}</item>
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
    """Show ``figure`` in the ``tag`` view and return its canvas.

    If the current layout does not contain the view and ``tag`` is :data:`DEFAULT_TAG`,
    switch to the :data:`FOUR_UP_LAYOUT_ID` layout. For other tags, switch to a layout
    that contains the view yourself.
    """
    view = registerLayoutView(tag)
    canvas = view.setFigure(figure)
    layoutManager = slicer.app.layoutManager()
    layoutNode = layoutManager.layoutLogic().GetLayoutNode()
    description = layoutNode.GetCurrentLayoutDescription() or ""
    inLayout = f"<{tag}" in description or f'singletontag="{tag}"' in description
    if not inLayout and tag == DEFAULT_TAG:
        if not layoutNode.IsLayoutDescription(FOUR_UP_LAYOUT_ID):
            layoutNode.AddLayoutDescription(FOUR_UP_LAYOUT_ID, fourUpLayoutDescription(tag))
        layoutManager.setLayout(FOUR_UP_LAYOUT_ID)
    return canvas
