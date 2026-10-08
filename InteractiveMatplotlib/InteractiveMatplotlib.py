import os
import re

import ctk
import qt
import slicer
from slicer.ScriptedLoadableModule import *

from InteractiveMatplotlibLib import isSlicerWeb

#
# InteractiveMatplotlib
#

MATPLOTLIB_REQUIREMENT = "matplotlib>=3.10"
SEABORN_REQUIREMENTS = "matplotlib>=3.10 seaborn pandas"
BACKEND_NAME = "module://InteractiveMatplotlibLib.backend"
PYPLOT_BACKEND_SETTING = "InteractiveMatplotlib/UseAsPyplotBackend"


class InteractiveMatplotlib(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Interactive Matplotlib"
        self.parent.categories = ["Utilities"]
        self.parent.dependencies = []
        self.parent.contributors = ["Thomas Kierski"]
        self.parent.helpText = """
Interactive Matplotlib figures in Slicer: a pyplot backend built on Slicer's own Qt binding,
and a Matplotlib view that can be placed in the view layout next to slice views.
In Slicer in the web browser (SlicerWeb) only the layout view is available.
See more information in <a href="https://github.com/PerkLab/SlicerSandbox#interactive-matplotlib">module documentation</a>.
"""
        self.parent.acknowledgementText = """
Developed with feedback from the 3D Slicer community on
<a href="https://github.com/Slicer/Slicer/pull/9441">Slicer/Slicer#9441</a>.
"""
        if not isSlicerWeb():
            slicer.app.connect("startupCompleted()", applyPyplotBackendSetting)


def applyPyplotBackendSetting():
    """Make the Slicer backend the pyplot default if the user enabled it in the module.

    Only the environment variable is set, so Matplotlib is not imported at startup.
    """
    if InteractiveMatplotlibLogic.pyplotBackendAtStartup():
        os.environ.setdefault("MPLBACKEND", BACKEND_NAME)


#
# InteractiveMatplotlibWidget
#

class InteractiveMatplotlibWidget(ScriptedLoadableModuleWidget):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent=None):
        ScriptedLoadableModuleWidget.__init__(self, parent)
        self.logic = None
        self.demo = None

    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)
        self.logic = InteractiveMatplotlibLogic()

        # Matplotlib
        setupSection = ctk.ctkCollapsibleButton()
        setupSection.text = "Matplotlib"
        self.layout.addWidget(setupSection)
        setupLayout = qt.QFormLayout(setupSection)

        self.statusLabel = qt.QLabel()
        self.statusLabel.wordWrap = True
        setupLayout.addRow("Status:", self.statusLabel)

        self.installButton = qt.QPushButton("Install or upgrade Matplotlib")
        self.installButton.toolTip = f"Install {MATPLOTLIB_REQUIREMENT} into Slicer's Python environment."
        setupLayout.addRow(self.installButton)

        # The pyplot backend draws into Qt widgets, which the web browser does not have.
        self.pyplotBackendCheckBox = None
        if not isSlicerWeb():
            self.pyplotBackendCheckBox = qt.QCheckBox("Use as pyplot backend")
            self.pyplotBackendCheckBox.toolTip = (
                "Show pyplot figures (plt.show()) in interactive Slicer windows. "
                "Applies now and at every application startup.")
            self.pyplotBackendCheckBox.checked = InteractiveMatplotlibLogic.pyplotBackendAtStartup()
            setupLayout.addRow(self.pyplotBackendCheckBox)

        # Examples
        examplesSection = ctk.ctkCollapsibleButton()
        examplesSection.text = "Examples"
        self.layout.addWidget(examplesSection)
        examplesLayout = qt.QVBoxLayout(examplesSection)

        self.histogramButton = qt.QPushButton("Slice histogram")
        self.histogramButton.toolTip = (
            "Load MRHead and show a histogram of the red slice view next to the slice views. "
            "Drag over the histogram to set the window/level.")
        examplesLayout.addWidget(self.histogramButton)

        self.statisticsButton = qt.QPushButton("Segment statistics (seaborn)")
        self.statisticsButton.toolTip = (
            "Segment MRHead into three tissue classes and show their statistics with seaborn. "
            "Installs seaborn and pandas if needed.")
        examplesLayout.addWidget(self.statisticsButton)

        self.clearButton = qt.QPushButton("Clear Matplotlib view")
        examplesLayout.addWidget(self.clearButton)

        # The desktop view has a navigation bar of its own; the web view does not.
        self.navigationButtons = []
        if isSlicerWeb():
            navigationSection = ctk.ctkCollapsibleButton()
            navigationSection.text = "Navigation"
            self.layout.addWidget(navigationSection)
            navigationLayout = qt.QHBoxLayout(navigationSection)
            for text, action, toolTip in (
                ("Home", "home", "Reset the original view (h)"),
                ("Back", "back", "Back to the previous view (c)"),
                ("Forward", "forward", "Forward to the next view (v)"),
                ("Pan", "pan", "Left button pans, right button zooms (p)"),
                ("Zoom", "zoom", "Zoom to rectangle (o)"),
            ):
                button = qt.QPushButton(text)
                button.toolTip = toolTip
                button.connect("clicked()", lambda action=action: self.onNavigate(action))
                navigationLayout.addWidget(button)
                self.navigationButtons.append(button)

        self.layout.addStretch(1)

        self.installButton.connect("clicked()", self.onInstall)
        if self.pyplotBackendCheckBox is not None:
            self.pyplotBackendCheckBox.connect("toggled(bool)", self.onPyplotBackendToggled)
        self.histogramButton.connect("clicked()", self.onSliceHistogram)
        self.statisticsButton.connect("clicked()", self.onSegmentStatistics)
        self.clearButton.connect("clicked()", self.onClear)

        self.updateGUI()

    def cleanup(self):
        self._cleanupDemo()

    def updateGUI(self):
        version, supported = InteractiveMatplotlibLogic.matplotlibStatus()
        if version is None:
            self.statusLabel.text = f"Matplotlib is not installed. Click below to install {MATPLOTLIB_REQUIREMENT}."
        elif not supported:
            self.statusLabel.text = f"Matplotlib {version} is too old. Click below to upgrade to {MATPLOTLIB_REQUIREMENT}."
        else:
            self.statusLabel.text = f"Matplotlib {version} is installed."
        self.installButton.enabled = not supported
        for widget in [self.histogramButton, self.statisticsButton, self.clearButton] + self.navigationButtons:
            widget.enabled = supported

    def onInstall(self):
        with slicer.util.tryWithErrorDisplay("Failed to install Matplotlib.", waitCursor=True):
            if not self.logic.installRequirements(MATPLOTLIB_REQUIREMENT):
                self.statusLabel.text = "Matplotlib is being installed. Try again in a moment."
                qt.QTimer.singleShot(3000, self.updateGUI)
                return
        self.updateGUI()

    def onNavigate(self, action):
        import InteractiveMatplotlibLib.view
        view = InteractiveMatplotlibLib.view.viewWidget()
        toolbar = view.toolbar() if view is not None else None
        if toolbar is not None:
            getattr(toolbar, action)()

    def onPyplotBackendToggled(self, enabled):
        InteractiveMatplotlibLogic.setPyplotBackendAtStartup(enabled)
        if enabled and InteractiveMatplotlibLogic.matplotlibStatus()[1]:
            with slicer.util.tryWithErrorDisplay("Failed to select the pyplot backend."):
                import InteractiveMatplotlibLib.backend
                InteractiveMatplotlibLib.backend.enable()

    def _cleanupDemo(self):
        if self.demo is not None:
            self.demo.cleanup()
            self.demo = None

    def onSliceHistogram(self):
        with slicer.util.tryWithErrorDisplay("Failed to show the slice histogram.", waitCursor=True):
            self._cleanupDemo()
            import InteractiveMatplotlibLib.examples
            self.demo = InteractiveMatplotlibLib.examples.showSliceHistogram()

    def onSegmentStatistics(self):
        with slicer.util.tryWithErrorDisplay("Failed to show the segment statistics.", waitCursor=True):
            if not self.logic.installRequirements(SEABORN_REQUIREMENTS):
                slicer.util.infoDisplay("Seaborn and pandas are being installed. Try again in a moment.")
                return
            self._cleanupDemo()
            import InteractiveMatplotlibLib.examples
            self.demo, summary = InteractiveMatplotlibLib.examples.showSegmentStatistics()
            print(summary.to_string(index=False))

    def onClear(self):
        self._cleanupDemo()
        import InteractiveMatplotlibLib.view
        widget = InteractiveMatplotlibLib.view.viewWidget()
        if widget is not None:
            widget.setFigure(None)


#
# InteractiveMatplotlibLogic
#

class InteractiveMatplotlibLogic(ScriptedLoadableModuleLogic):
    """Installation and settings helpers. The features themselves are in InteractiveMatplotlibLib."""

    @staticmethod
    def matplotlibStatus():
        """Return the installed Matplotlib version (or ``None``) and whether it is supported."""
        from importlib.metadata import PackageNotFoundError, version

        try:
            installed = version("matplotlib")
        except PackageNotFoundError:
            return None, False
        # Not packaging.version, which the web browser may not have loaded.
        major, minor = (int(part) for part in re.findall(r"\d+", installed)[:2])
        return installed, (major, minor) >= (3, 10)

    @staticmethod
    def installRequirements(requirements):
        """Install ``requirements`` unless they are already satisfied.

        Return ``True`` when they are installed. In SlicerWeb the page installs packages in
        the background, so this returns ``False`` until they are there.
        """
        if isSlicerWeb():
            import importlib.util

            import slicerweb.packages

            names = [re.split(r"[<>=!~\[; ]", requirement)[0] for requirement in requirements.split()]
            missing = [name for name in names if importlib.util.find_spec(name) is None]
            for name in missing:
                slicerweb.packages.ensure_in_background(name)
            return not missing

        import slicer.packaging

        slicer.packaging.pip_ensure(requirements)
        return True

    @staticmethod
    def pyplotBackendAtStartup():
        if isSlicerWeb():
            return False
        return slicer.util.toBool(qt.QSettings().value(PYPLOT_BACKEND_SETTING, False))

    @staticmethod
    def setPyplotBackendAtStartup(enabled):
        qt.QSettings().setValue(PYPLOT_BACKEND_SETTING, bool(enabled))


#
# InteractiveMatplotlibTest
#

class InteractiveMatplotlibTest(ScriptedLoadableModuleTest):
    """Smoke test of the Matplotlib view in the layout.

    The canvases are tested in detail by the tests in Testing/Python.
    """

    def setUp(self):
        slicer.mrmlScene.Clear()

    def runTest(self):
        self.setUp()
        self.test_ShowFigureInLayout()

    def test_ShowFigureInLayout(self):
        if not InteractiveMatplotlibLogic.matplotlibStatus()[1]:
            self.delayDisplay(f"Skipped: {MATPLOTLIB_REQUIREMENT} is not installed")
            return

        from matplotlib.figure import Figure

        import InteractiveMatplotlibLib.view as view

        self.delayDisplay("Starting the test")
        layoutManager = slicer.app.layoutManager()
        originalLayout = layoutManager.layout
        layoutManager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutConventionalView)

        figure = Figure()
        figure.add_subplot().plot([0, 1, 2], [0, 1, 0])
        canvas = view.showFigure(figure)
        slicer.app.processEvents()

        self.assertEqual(layoutManager.layout, view.FOUR_UP_LAYOUT_ID)
        widget = view.viewWidget()
        self.assertIs(widget.figure(), figure)
        self.assertIs(widget.canvas(), canvas)
        canvas.flush_events()
        self.assertGreater(min(canvas.get_width_height()), 0)

        widget.setFigure(None)
        self.assertIsNone(widget.figure())
        layoutManager.setLayout(originalLayout)
        self.delayDisplay("Test passed")
