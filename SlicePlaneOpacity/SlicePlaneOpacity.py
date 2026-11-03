# Copyright (c) 2026, youyouhdhd
# SPDX-License-Identifier: BSD-3-Clause
# Original project: https://github.com/youyouhdhd/SlicerSlicePlaneOpacity

import os

import ctk
import qt
import slicer
from slicer.ScriptedLoadableModule import (
    ScriptedLoadableModule,
    ScriptedLoadableModuleLogic,
    ScriptedLoadableModuleTest,
    ScriptedLoadableModuleWidget,
)
from slicer.i18n import tr as _
from slicer.i18n import translate


class SlicePlaneOpacity(ScriptedLoadableModule):
    """Module metadata for the Slice Plane Opacity extension."""

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = _("Slice Plane Opacity")
        self.parent.categories = [translate("qSlicerAbstractCoreModule", "Utilities")]
        self.parent.dependencies = []
        self.parent.contributors = ["youyouhdhd"]
        self.parent.helpText = _(
            "Control the opacity and 3D visibility of the Red, Yellow, and Green "
            "slice planes. This module changes only the slice planes rendered in "
            "3D views; it does not change 2D foreground/background compositing. "
            "<br><br>Documentation: "
            "<a href='https://github.com/youyouhdhd/SlicerSlicePlaneOpacity'>"
            "github.com/youyouhdhd/SlicerSlicePlaneOpacity</a>"
        )
        self.parent.acknowledgementText = _(
            "This lightweight extension was created for the 3D Slicer community."
        )

        iconPath = os.path.join(
            os.path.dirname(__file__), "Resources", "Icons", "SlicePlaneOpacity.png"
        )
        if os.path.exists(iconPath):
            self.parent.icon = qt.QIcon(iconPath)


class SlicePlaneOpacityWidget(ScriptedLoadableModuleWidget):
    """User interface for controlling slice-plane opacity in 3D views."""

    SLICE_NAMES = ("Red", "Yellow", "Green")

    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)

        self.logic = SlicePlaneOpacityLogic()
        self._updatingUi = False
        self._layoutManager = None
        self._sliceOpacitySliders = {}
        self._sliceVisibilityCheckBoxes = {}

        descriptionLabel = qt.QLabel(
            _(
                "Adjust the opacity of the standard Red, Yellow, and Green slice "
                "planes as they appear in 3D views."
            )
        )
        descriptionLabel.wordWrap = True
        self.layout.addWidget(descriptionLabel)

        controlsCollapsibleButton = ctk.ctkCollapsibleButton()
        controlsCollapsibleButton.text = _("3D slice plane controls")
        self.layout.addWidget(controlsCollapsibleButton)
        controlsLayout = qt.QVBoxLayout(controlsCollapsibleButton)

        masterFormLayout = qt.QFormLayout()
        controlsLayout.addLayout(masterFormLayout)

        self.masterOpacitySlider = ctk.ctkSliderWidget()
        self._configureOpacitySlider(self.masterOpacitySlider)
        self.masterOpacitySlider.toolTip = _(
            "Drag to set all three slice planes to the same opacity. If individual "
            "axes have different values, this slider shows their average."
        )
        masterFormLayout.addRow(_("All planes:"), self.masterOpacitySlider)
        self.masterOpacitySlider.connect(
            "valueChanged(double)", self.onMasterOpacityChanged
        )

        grid = qt.QGridLayout()
        controlsLayout.addLayout(grid)
        grid.addWidget(qt.QLabel(_("Plane")), 0, 0)
        grid.addWidget(qt.QLabel(_("Show in 3D")), 0, 1)
        grid.addWidget(qt.QLabel(_("Opacity")), 0, 2)

        for row, sliceName in enumerate(self.SLICE_NAMES, start=1):
            nameLabel = qt.QLabel(sliceName)
            nameLabel.toolTip = _("Standard Slicer {} slice view").format(sliceName)
            grid.addWidget(nameLabel, row, 0)

            visibilityCheckBox = qt.QCheckBox()
            visibilityCheckBox.toolTip = _(
                "Show or hide the {} slice plane in 3D views"
            ).format(sliceName)
            grid.addWidget(visibilityCheckBox, row, 1)
            self._sliceVisibilityCheckBoxes[sliceName] = visibilityCheckBox
            visibilityCheckBox.connect(
                "toggled(bool)",
                lambda visible, name=sliceName: self.onSliceVisibilityChanged(
                    name, visible
                ),
            )

            opacitySlider = ctk.ctkSliderWidget()
            self._configureOpacitySlider(opacitySlider)
            opacitySlider.toolTip = _(
                "Opacity of the {} slice plane in 3D views (0 = transparent, "
                "1 = opaque)"
            ).format(sliceName)
            grid.addWidget(opacitySlider, row, 2)
            self._sliceOpacitySliders[sliceName] = opacitySlider
            opacitySlider.connect(
                "valueChanged(double)",
                lambda value, name=sliceName: self.onSliceOpacityChanged(name, value),
            )

        buttonLayout = qt.QHBoxLayout()
        controlsLayout.addLayout(buttonLayout)

        refreshButton = qt.QPushButton(_("Refresh from scene"))
        refreshButton.toolTip = _("Read the current slice-plane settings from Slicer")
        refreshButton.connect("clicked()", self.refreshFromScene)
        buttonLayout.addWidget(refreshButton)

        resetButton = qt.QPushButton(_("Reset opacity"))
        resetButton.toolTip = _("Set Red, Yellow, and Green opacity to 1.0")
        resetButton.connect("clicked()", self.resetOpacity)
        buttonLayout.addWidget(resetButton)

        noteLabel = qt.QLabel(
            _(
                "Tip: a slice plane must be enabled with 'Show in 3D' to be visible. "
                "Opacity 0 is fully transparent; opacity 1 is fully opaque."
            )
        )
        noteLabel.wordWrap = True
        controlsLayout.addWidget(noteLabel)

        self.layout.addStretch(1)

        self._layoutManager = slicer.app.layoutManager()
        if self._layoutManager:
            self._layoutManager.connect("layoutChanged(int)", self.onLayoutChanged)

        self.refreshFromScene()

    def cleanup(self):
        if self._layoutManager:
            try:
                self._layoutManager.disconnect("layoutChanged(int)", self.onLayoutChanged)
            except (RuntimeError, TypeError):
                pass
        self._layoutManager = None

    def enter(self):
        self.refreshFromScene()

    @staticmethod
    def _configureOpacitySlider(slider):
        slider.minimum = 0.0
        slider.maximum = 1.0
        slider.singleStep = 0.01
        slider.decimals = 2
        slider.value = 1.0

    def onMasterOpacityChanged(self, value):
        if self._updatingUi:
            return

        self._updatingUi = True
        try:
            for sliceName in self.SLICE_NAMES:
                slider = self._sliceOpacitySliders[sliceName]
                previous = slider.blockSignals(True)
                slider.value = value
                slider.blockSignals(previous)
                self.logic.setOpacity(sliceName, value)
        finally:
            self._updatingUi = False

    def onSliceOpacityChanged(self, sliceName, value):
        if self._updatingUi:
            return
        self.logic.setOpacity(sliceName, value)
        self._updateMasterSliderFromIndividualValues()

    def onSliceVisibilityChanged(self, sliceName, visible):
        if self._updatingUi:
            return
        self.logic.setSliceVisible(sliceName, visible)

    def onLayoutChanged(self, _layoutId):
        qt.QTimer.singleShot(0, self.refreshFromScene)

    def resetOpacity(self):
        self.masterOpacitySlider.value = 1.0

    def refreshFromScene(self):
        if not hasattr(self, "logic"):
            return

        self._updatingUi = True
        opacityValues = []
        try:
            for sliceName in self.SLICE_NAMES:
                opacity = self.logic.getOpacity(sliceName)
                visible = self.logic.getSliceVisible(sliceName)

                opacitySlider = self._sliceOpacitySliders[sliceName]
                visibilityCheckBox = self._sliceVisibilityCheckBoxes[sliceName]

                controlsAvailable = opacity is not None and visible is not None
                opacitySlider.enabled = opacity is not None
                visibilityCheckBox.enabled = visible is not None

                if opacity is not None:
                    opacityValues.append(opacity)
                    previous = opacitySlider.blockSignals(True)
                    opacitySlider.value = opacity
                    opacitySlider.blockSignals(previous)

                if visible is not None:
                    previous = visibilityCheckBox.blockSignals(True)
                    visibilityCheckBox.checked = bool(visible)
                    visibilityCheckBox.blockSignals(previous)

                if not controlsAvailable:
                    opacitySlider.toolTip = _(
                        "This slice view is not available in the current layout"
                    )

            self.masterOpacitySlider.enabled = bool(opacityValues)
            if opacityValues:
                previous = self.masterOpacitySlider.blockSignals(True)
                self.masterOpacitySlider.value = sum(opacityValues) / len(opacityValues)
                self.masterOpacitySlider.blockSignals(previous)
        finally:
            self._updatingUi = False

    def _updateMasterSliderFromIndividualValues(self):
        values = []
        for sliceName in self.SLICE_NAMES:
            opacity = self.logic.getOpacity(sliceName)
            if opacity is not None:
                values.append(opacity)
        if not values:
            return

        self._updatingUi = True
        try:
            previous = self.masterOpacitySlider.blockSignals(True)
            self.masterOpacitySlider.value = sum(values) / len(values)
            self.masterOpacitySlider.blockSignals(previous)
        finally:
            self._updatingUi = False


class SlicePlaneOpacityLogic(ScriptedLoadableModuleLogic):
    """Logic for manipulating Slicer's slice model display nodes."""

    SLICE_NAMES = ("Red", "Yellow", "Green")

    @staticmethod
    def _validateSliceName(sliceName):
        if sliceName not in SlicePlaneOpacityLogic.SLICE_NAMES:
            raise ValueError(
                "sliceName must be one of: {}".format(
                    ", ".join(SlicePlaneOpacityLogic.SLICE_NAMES)
                )
            )

    @staticmethod
    def _sliceLogic(sliceName):
        SlicePlaneOpacityLogic._validateSliceName(sliceName)

        layoutManager = slicer.app.layoutManager()
        if layoutManager:
            sliceWidget = layoutManager.sliceWidget(sliceName)
            if sliceWidget:
                return sliceWidget.sliceLogic()

        applicationLogic = slicer.app.applicationLogic()
        if applicationLogic and hasattr(applicationLogic, "GetSliceLogicByLayoutName"):
            return applicationLogic.GetSliceLogicByLayoutName(sliceName)

        return None

    def getSliceModelDisplayNode(self, sliceName):
        sliceLogic = self._sliceLogic(sliceName)
        if not sliceLogic:
            return None

        sliceModelNode = sliceLogic.GetSliceModelNode()
        if not sliceModelNode:
            return None

        return sliceModelNode.GetDisplayNode()

    def getSliceNode(self, sliceName):
        sliceLogic = self._sliceLogic(sliceName)
        if not sliceLogic:
            return None
        return sliceLogic.GetSliceNode()

    def setOpacity(self, sliceName, opacity):
        displayNode = self.getSliceModelDisplayNode(sliceName)
        if not displayNode:
            return False

        opacity = max(0.0, min(1.0, float(opacity)))
        displayNode.SetOpacity(opacity)
        return True

    def getOpacity(self, sliceName):
        displayNode = self.getSliceModelDisplayNode(sliceName)
        if not displayNode:
            return None
        return float(displayNode.GetOpacity())

    def setSliceVisible(self, sliceName, visible):
        sliceNode = self.getSliceNode(sliceName)
        if not sliceNode:
            return False
        sliceNode.SetSliceVisible(1 if visible else 0)
        return True

    def getSliceVisible(self, sliceName):
        sliceNode = self.getSliceNode(sliceName)
        if not sliceNode:
            return None
        return bool(sliceNode.GetSliceVisible())

    def setAllOpacity(self, opacity):
        results = {}
        for sliceName in self.SLICE_NAMES:
            results[sliceName] = self.setOpacity(sliceName, opacity)
        return results


class SlicePlaneOpacityTest(ScriptedLoadableModuleTest):
    """Basic smoke tests designed to run inside 3D Slicer."""

    def setUp(self):
        pass

    def runTest(self):
        self.setUp()
        self.test_SlicePlaneOpacityLogic()

    def test_SlicePlaneOpacityLogic(self):
        self.delayDisplay("Starting Slice Plane Opacity test")

        logic = SlicePlaneOpacityLogic()
        originalOpacity = logic.getOpacity("Red")
        if originalOpacity is None:
            self.delayDisplay("Red slice view is unavailable; test skipped")
            return

        try:
            self.assertTrue(logic.setOpacity("Red", 0.42))
            self.assertAlmostEqual(logic.getOpacity("Red"), 0.42, places=5)

            self.assertTrue(logic.setOpacity("Red", -1.0))
            self.assertAlmostEqual(logic.getOpacity("Red"), 0.0, places=5)

            self.assertTrue(logic.setOpacity("Red", 2.0))
            self.assertAlmostEqual(logic.getOpacity("Red"), 1.0, places=5)
        finally:
            logic.setOpacity("Red", originalOpacity)

        self.delayDisplay("Slice Plane Opacity test passed")
