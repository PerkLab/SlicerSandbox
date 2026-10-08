"""Helpers shared by the Matplotlib canvases of InteractiveMatplotlibLib.

This module imports neither ``qt`` nor ``vtk``, so it can be used by both the Qt canvas in
:mod:`InteractiveMatplotlibLib.backend` and the Qt-free canvas in
:mod:`InteractiveMatplotlibLib.vtkcanvas`.
"""

import weakref

import matplotlib

# MouseEvent(buttons=...), used to report the pressed buttons on motion, was added in 3.10.
MINIMUM_MATPLOTLIB_VERSION = (3, 10)


def require_matplotlib(moduleName):
    """Raise ``ImportError`` if the installed matplotlib is too old for ``moduleName``."""
    if tuple(matplotlib.__version_info__[:2]) < MINIMUM_MATPLOTLIB_VERSION:
        raise ImportError(
            "%s requires matplotlib >= %d.%d, but %s is installed. "
            "Upgrade it with slicer.packaging.pip_ensure('matplotlib>=%d.%d') and restart Slicer."
            % (moduleName, *MINIMUM_MATPLOTLIB_VERSION, matplotlib.__version__,
               *MINIMUM_MATPLOTLIB_VERSION))


def weak_callback(method, *args, forward_arguments=False):
    """Return a callable that invokes the bound ``method`` without keeping its object alive.

    Both PythonQt signal connections and VTK observers hold a strong reference to the
    Python callable, and that reference lives on the C++ side where the garbage collector
    cannot see it. Connecting a bound method of an object that also owns the sender
    therefore forms a cycle that is never collected. The returned callable does nothing
    once the object is gone.

    If ``forward_arguments`` is true, the arguments the callable is invoked with (for
    example the caller and event name of a VTK observer) are passed on after ``args``.
    """
    ref = weakref.WeakMethod(method)

    def callback(*callbackArgs):
        target = ref()
        if target is None:
            return None
        if forward_arguments:
            return target(*args, *callbackArgs)
        return target(*args)

    return callback
