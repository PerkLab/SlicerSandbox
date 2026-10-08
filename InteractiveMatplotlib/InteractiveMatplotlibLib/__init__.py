"""Interactive Matplotlib figures for desktop Slicer and SlicerWeb.

This package imports nothing on its own, so :func:`isSlicerWeb` can be used before
Matplotlib is installed.
"""

import sys


def isSlicerWeb():
    """Return ``True`` in SlicerWeb, Slicer running in a web browser.

    SlicerWeb has no Qt: its ``qt`` and ``ctk`` modules build browser widgets for module
    panels, but there is no ``QWidget`` to draw a canvas into and no layout view factories.
    Only the VTK canvas of :mod:`InteractiveMatplotlibLib.vtkcanvas` works there.
    """
    return sys.platform == "emscripten" or "slicerweb" in sys.modules