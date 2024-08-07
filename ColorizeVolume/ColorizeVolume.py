import logging
import os
from typing import Annotated, Optional

import vtk
import vtkAddon

import slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
from slicer.parameterNodeWrapper import (
    parameterNodeWrapper,
    WithinRange,
)

from slicer import vtkMRMLScalarVolumeNode, vtkMRMLSegmentationNode, vtkMRMLSequenceBrowserNode, vtkMRMLVectorVolumeNode


#
# ColorizeVolume
#

class ColorizeVolume(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Colorize Volume"
        self.parent.categories = ["Segmentation"]
        self.parent.dependencies = []
        self.parent.contributors = ["Andras Lasso (PerkLab)", "Steve Pieper (Isomics)"]
        self.parent.helpText = """
Colorize a volume using a segmentation.
See more information in <a href="https://github.com/PerkLab/SlicerSandbox">module documentation</a>.
"""
        # TODO: replace with organization, grant and thanks
        self.parent.acknowledgementText = """
This file was originally developed by Steve Pieper, Isomics and Andras Lasso, PerkLab.
"""

        # Additional initialization step after application startup is complete
        slicer.app.connect("startupCompleted()", registerSampleData)


#
# Register sample data sets in Sample Data module
#

def registerSampleData():
    """
    Add data sets to Sample Data module.
    """
    # It is always recommended to provide sample data for users to make it easy to try the module,
    # but if no sample data is available then this method (and associated startupCompeted signal connection) can be removed.

    import SampleData
    iconsPath = os.path.join(os.path.dirname(__file__), 'Resources/Icons')

    # To ensure that the source code repository remains small (can be downloaded and installed quickly)
    # it is recommended to store data sets that are larger than a few MB in a Github release.

    # CardiacAgatstonScoring1
    SampleData.SampleDataLogic.registerCustomSampleDataSource(
        # Category and sample name displayed in Sample Data module
        category='Sandbox',
        sampleName='CTLiverSegmentation',
        # Thumbnail should have size of approximately 260x280 pixels and stored in Resources/Icons folder.
        # It can be created by Screen Capture module, "Capture all views" option enabled, "Number of images" set to "Single".
        thumbnailFileName=os.path.join(iconsPath, 'CTLiverSegmentation.png'),
        # Download URL and target file name
        uris="https://github.com/PerkLab/SlicerSandbox/releases/download/TestingData/CTLiverSegmentation.seg.nrrd",
        fileNames='CTLiverSegmentation.seg.nrrd',
        # Checksum to ensure file integrity. Can be computed by this command:
        #  import hashlib; print(hashlib.sha256(open(filename, "rb").read()).hexdigest())
        checksums='SHA256:ce9a7182a666788a2556f6cf4f59ad5dadd944171cc279e80c164496729a7032',
        # This node name will be used when the data set is loaded
        nodeNames='CTLiverSegmentation'
    )

#
# ColorizeVolumeParameterNode
#

@parameterNodeWrapper
class ColorizeVolumeParameterNode:
    """
    The parameters needed by module.

    inputScalarVolume - The volume to threshold.
    inputSegmentation - The output volume that will contain the inverted thresholded volume.
    outputRgbaVolume - The output volume that will contain the thresholded volume.
    softEdgeThicknessVoxel - Thickness of transition zone at segment edges (in voxels).
    colorBleedThicknessVoxel - How far color bleeds out of the original segmentation.
    backgroundOpacityPercent - Opacity factor for regions outside all segments.
    autoShowVolumeRendering - Automatically display volume rendering after processing is completed.
    """
    inputScalarVolume: vtkMRMLScalarVolumeNode
    inputSegmentation: vtkMRMLSegmentationNode
    outputRgbaVolume: vtkMRMLVectorVolumeNode
    # 3-element list of floats
    backgroundColorRgb: list[float] = [0.1, 0.1, 0.1]
    softEdgeThicknessVoxel: Annotated[float, WithinRange(0, 8)] = 4.0
    colorBleedThicknessVoxel: Annotated[float, WithinRange(0, 8)] = 1.0
    backgroundOpacityPercent: Annotated[float, WithinRange(0, 100)] = 20
    autoShowVolumeRendering: bool = True
    volumeRenderingLevelPercent: Annotated[float, WithinRange(0, 100)] = 50.0
    volumeRenderingWindowPercent: Annotated[float, WithinRange(0.1, 100)] = 25.0
    volumeRenderingOpacityPercent: Annotated[float, WithinRange(0, 100)] = 25.0
    volumeRenderingGradientOpacity: bool = False
    volumeRenderingGradientOpacityLevel: Annotated[float, WithinRange(0, 50)] = 15.0
    volumeRenderingGradientOpacityWindow: Annotated[float, WithinRange(5, 100)] = 20.0

#
# ColorizeVolumeWidget
#

class ColorizeVolumeWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent=None) -> None:
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)  # needed for parameter node observation
        self.logic = None
        self._parameterNode = None
        self._parameterNodeGuiTag = None

    def setup(self) -> None:
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.setup(self)

        if not hasattr(vtkAddon, 'vtkImageLabelDilate3D'):
            slicer.util.errorDisplay("This module requires a more recent version of Slicer. Please download and install latest Slicer Preview Release.")
            return

        # Load widget from .ui file (created by Qt Designer).
        # Additional widgets can be instantiated manually and added to self.layout.
        uiWidget = slicer.util.loadUI(self.resourcePath('UI/ColorizeVolume.ui'))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = ColorizeVolumeLogic()
        self.logic.logCallback = self.log

        # Connections

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

        self.ui.outputRgbaVolumeSelector.connect('currentNodeChanged(vtkMRMLNode*)', self.onOutputRgbaVolumeSelected)

        # Buttons
        self.ui.applyButton.connect('clicked(bool)', self.onApplyButton)
        self.ui.showVolumeRenderingButton.connect('clicked(bool)', self.onShowButton)
        self.ui.resetVolumeRenderingSettingsButton.connect('clicked(bool)', self.onResetVolumeRenderingSettingsButton)
        self.ui.volumeRenderingSettingsButton.connect('clicked(bool)', self.onVolumeRenderingSettingsButton)
        self.ui.resetToDefaultsButton.connect('clicked(bool)', self.onResetToDefaultsButton)
        self.ui.backgroundColorPickerButton.connect('colorChanged(QColor)', self.onBackgroundColorSelected)

        self.ui.volumeRenderingLevelWidget.connect('valueChanged(double)', self.onUpdateVolumeRenderingTransferFunction)
        self.ui.volumeRenderingWindowWidget.connect('valueChanged(double)', self.onUpdateVolumeRenderingTransferFunction)
        self.ui.volumeRenderingOpacityWidget.connect('valueChanged(double)', self.onUpdateVolumeRenderingTransferFunction)
        self.ui.volumeRenderingGradientOpacityCheckBox.connect('toggled(bool)', self.onUpdateVolumeRenderingTransferFunction)
        self.ui.volumeRenderingGradientOpacityLevelWidget.connect('valueChanged(double)', self.onUpdateVolumeRenderingTransferFunction)
        self.ui.volumeRenderingGradientOpacityWindowWidget.connect('valueChanged(double)', self.onUpdateVolumeRenderingTransferFunction)

        # Make sure parameter node is initialized (needed for module reload)
        self.initializeParameterNode()

    def cleanup(self) -> None:
        """
        Called when the application closes and the module widget is destroyed.
        """
        self.removeObservers()

    def enter(self) -> None:
        """
        Called each time the user opens this module.
        """
        # Make sure parameter node exists and observed
        self.initializeParameterNode()

    def exit(self) -> None:
        """
        Called each time the user opens a different module.
        """
        # Do not react to parameter node changes (GUI will be updated when the user enters into the module)
        if self._parameterNode:
            self._parameterNode.disconnectGui(self._parameterNodeGuiTag)
            self._parameterNodeGuiTag = None
            self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self._checkCanApply)

    def onSceneStartClose(self, caller, event) -> None:
        """
        Called just before the scene is closed.
        """
        # Parameter node will be reset, do not use it anymore
        self.setParameterNode(None)

    def onSceneEndClose(self, caller, event) -> None:
        """
        Called just after the scene is closed.
        """
        # If this module is shown while the scene is closed then recreate a new parameter node immediately
        if self.parent.isEntered:
            self.initializeParameterNode()

    def initializeParameterNode(self) -> None:
        """
        Ensure parameter node exists and observed.
        """
        # Parameter node stores all user choices in parameter values, node selections, etc.
        # so that when the scene is saved and reloaded, these settings are restored.

        self.setParameterNode(self.logic.getParameterNode())

        # Select default input nodes if nothing is selected yet to save a few clicks for the user
        if not self._parameterNode.inputScalarVolume:
            firstVolumeNode = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLScalarVolumeNode")
            if firstVolumeNode:
                self._parameterNode.inputScalarVolume = firstVolumeNode
        if not self._parameterNode.inputSegmentation:
            firstSegmentationNode = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLSegmentationNode")
            if firstSegmentationNode:
                self._parameterNode.inputSegmentation = firstSegmentationNode

    def setParameterNode(self, inputParameterNode: Optional[ColorizeVolumeParameterNode]=None) -> None:
        """
        Set and observe parameter node.
        Observation is needed because when the parameter node is changed then the GUI must be updated immediately.
        """

        if self._parameterNode:
            self._parameterNode.disconnectGui(self._parameterNodeGuiTag)
            self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self._checkCanApply)
        self._parameterNode = inputParameterNode
        if self._parameterNode:
            # Note: in the .ui file, a Qt dynamic property called "SlicerParameterName" is set on each
            # ui element that needs connection.
            self._parameterNodeGuiTag = self._parameterNode.connectGui(self.ui)
            self.addObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self._checkCanApply)
            self._checkCanApply()

    def _checkCanApply(self, caller=None, event=None) -> None:
        if self._parameterNode and self._parameterNode.inputScalarVolume and self._parameterNode.inputSegmentation:
            self.ui.applyButton.toolTip = "Compute output volume"
            self.ui.applyButton.enabled = True
        else:
            self.ui.applyButton.toolTip = "Select input volume and segmentation"
            self.ui.applyButton.enabled = False
        # Parameter node modified, make sure color selector is updated
        # (need to update manually because color picker is not supported by parameter node)
        import qt
        self.ui.backgroundColorPickerButton.color = qt.QColor.fromRgbF(*self._parameterNode.backgroundColorRgb)

    def onApplyButton(self) -> None:
        """
        Run processing when user clicks "Apply" button.
        """

        sequenceBrowserNode = slicer.modules.sequences.logic().GetFirstBrowserNodeForProxyNode(self._parameterNode.inputScalarVolume)
        if sequenceBrowserNode:
            if not slicer.util.confirmYesNoDisplay("The input volume you provided are part of a sequence. Do you want to colorize all frames of that sequence?"):
                sequenceBrowserNode = None

        with slicer.util.tryWithErrorDisplay("Failed to compute results.", waitCursor=True):

            if not self._parameterNode.outputRgbaVolume:
                self._parameterNode.outputRgbaVolume = self.logic.AddNewOutputVolume(f"{self._parameterNode.inputScalarVolume.GetName()} colored")

            # Compute output

            import time
            startTime = time.time()

            self.logic._process(
                self._parameterNode.inputScalarVolume,
                self._parameterNode.inputSegmentation,
                self._parameterNode.outputRgbaVolume,
                self._parameterNode.backgroundColorRgb,
                self._parameterNode.backgroundOpacityPercent,
                self._parameterNode.colorBleedThicknessVoxel,
                self._parameterNode.softEdgeThicknessVoxel,
                sequenceBrowserNode)

            stopTime = time.time()
            print(f'Colorize computation has been completed in {stopTime-startTime:.2f} seconds')

            if self._parameterNode.autoShowVolumeRendering:
                self.onShowButton()

    def onShowButton(self) -> None:
        """
        Show output volume using volume rendering.
        """
        self.logic.showVolumeRendering(resetSettings = False)
        self.onOutputRgbaVolumeSelected()

    def onResetVolumeRenderingSettingsButton(self) -> None:
        """
        Show output volume using volume rendering.
        """
        self.logic.showVolumeRendering(resetSettings=True)
        self.onOutputRgbaVolumeSelected()

    def onVolumeRenderingSettingsButton(self) -> None:
        volumeRenderingLogic = slicer.modules.volumerendering.logic()
        vrDisplayNode = volumeRenderingLogic.CreateDefaultVolumeRenderingNodes(self._parameterNode.outputRgbaVolume)
        slicer.app.openNodeModule(vrDisplayNode)

    def onOutputRgbaVolumeSelected(self) -> None:
        volumeNode = self.ui.outputRgbaVolumeSelector.currentNode()
        volumeRenderingDisplayNode = slicer.modules.volumerendering.logic().GetFirstVolumeRenderingDisplayNode(volumeNode) if volumeNode else None
        volumeRenderingPropertyNode = volumeRenderingDisplayNode.GetVolumePropertyNode() if volumeRenderingDisplayNode else None
        self.ui.volumePropertyNodeWidget.enabled = (volumeRenderingPropertyNode is not None)
        if not volumeRenderingPropertyNode:
            return
        self.ui.volumePropertyNodeWidget.setMRMLVolumePropertyNode(volumeRenderingPropertyNode)

    def onBackgroundColorSelected(self, color) -> None:
        self._parameterNode.backgroundColorRgb = [color.redF(), color.greenF(), color.blueF()]

    def onResetToDefaultsButton(self):
        for paramName in ['softEdgeThicknessVoxel', 'colorBleedThicknessVoxel', 'backgroundOpacityPercent']:
            self.logic.getParameterNode().setValue(paramName, self.logic.getParameterNode().default(paramName).value)

    def onUpdateVolumeRenderingTransferFunction(self):
        # This method is called by the GUI and at this point the parameter node may not be up-to-date yet.
        # We call the logic update via a timer to give time for the parameter node to get updated.
        import qt
        qt.QTimer.singleShot(0, self.logic.updateVolumeRenderingOpacityTransferFunctions)
    
    def log(self, message):
        slicer.util.showStatusMessage(message, 1000)
        slicer.app.processEvents()


#
# ColorizeVolumeLogic
#

class ColorizeVolumeLogic(ScriptedLoadableModuleLogic):
    """This class should implement all the actual
    computation done by your module.  The interface
    should be such that other python code can import
    this class and make use of the functionality without
    requiring an instance of the Widget.
    Uses ScriptedLoadableModuleLogic base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self) -> None:
        """
        Called when the logic class is instantiated. Can be used for initializing member variables.
        """
        ScriptedLoadableModuleLogic.__init__(self)
        self.logCallback = None

    def log(self, message):
        if self.logCallback:
            self.logCallback(message)
        else:
            logging.info(message)

    def getParameterNode(self):
        return ColorizeVolumeParameterNode(super().getParameterNode())

    def AddNewOutputVolume(self, nodeName=None):
        outputRgbaVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLVectorVolumeNode", nodeName if nodeName else "")
        outputRgbaVolume.SetVoxelVectorType(slicer.vtkMRMLVolumeNode.VoxelVectorTypeColorRGBA)
        return outputRgbaVolume

    def _processVolume(
        self,
        volumeNode,
        segmentationNode,
        outputRgbaVolume,
        backgroundColorRgb,
        backgroundColorOpacityPercent,
        colorBleedThicknessVoxel,
        softEdgeThicknessVoxel,
    ):
        """
        Run the processing algorithm on a single volume.
        Can be used without GUI widget.
        :param volumeNode: volume to be thresholded
        :param segmentationNode: segmentation to be used for coloring
        :param outputRgbaVolume: colorized RGBA volume
        :param backgroundColorRgb: color and opacity of voxels that are not segmented (RGBA)
        :param backgroundColorOpacityPercent: opacity of voxels that are not segmented (0-100)
        :oaram colorBleedThicknessVoxel: how far color bleeds out (in voxels)
        :param softEdgeThicknessVoxel: edge smoothing thickness (in voxels)
        """
        import numpy as np
        import time
        import vtk
        import vtk.util.numpy_support
        segmentIds = segmentationNode.GetDisplayNode().GetVisibleSegmentIDs()
        self.log("Exporting segments...")
        labelmapVolumeNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode", "__temp__")
        if not slicer.modules.segmentations.logic().ExportSegmentsToLabelmapNode(segmentationNode, segmentIds, labelmapVolumeNode, volumeNode):
            raise RuntimeError("Export of segment failed.")
        slicer.app.processEvents()
        colorTableNode = labelmapVolumeNode.GetDisplayNode().GetColorNode()

        # Background color
        colorTableNode.SetColor(0, *backgroundColorRgb, backgroundColorOpacityPercent / 100.0)
        for segmentIndex, segmentId in enumerate(segmentIds):
            segment = segmentationNode.GetSegmentation().GetSegment(segmentId)
            color = segment.GetColor()
            opacity = segmentationNode.GetDisplayNode().GetSegmentOpacity3D(segmentId)
            colorTableNode.SetColor(segmentIndex + 1, *color, opacity)

        # Dilate labelmap to avoid edge artifacts
        self.log("Dilating segments...")
        dilate = vtkAddon.vtkImageLabelDilate3D()
        dilate.SetInputData(labelmapVolumeNode.GetImageData())
        dilationKernelSize = int(colorBleedThicknessVoxel + 0.5) * 2 + 1
        dilate.SetKernelSize(dilationKernelSize, dilationKernelSize, dilationKernelSize)
        dilate.SetBackgroundValue(0)
        dilate.Update()
        labelImage = dilate.GetOutput()

        self.log("Generating colorized volume...")

        mapToRGB = vtk.vtkImageMapToColors()
        mapToRGB.ReleaseDataFlagOn()
        mapToRGB.SetOutputFormatToRGBA()
        mapToRGB.SetInputData(labelImage)
        mapToRGB.SetLookupTable(colorTableNode.GetLookupTable())
        mapToRGB.Update()

        outputRgbaVolume.CopyOrientation(volumeNode)
        outputRgbaVolume.SetVoxelVectorType(slicer.vtkMRMLVolumeNode.VoxelVectorTypeColorRGBA)
        outputRgbaVolume.SetAndObserveImageData(mapToRGB.GetOutput())
        outputRgbaVolume.CreateDefaultDisplayNodes()

        shiftScale = vtk.vtkImageShiftScale()
        shiftScale.ReleaseDataFlagOn()
        shiftScale.SetOutputScalarType(vtk.VTK_UNSIGNED_CHAR)

        [rangeMin, rangeMax] = volumeNode.GetImageData().GetScalarRange()

        useDisplayedRange = True
        if useDisplayedRange:
            rangeMin = volumeNode.GetScalarVolumeDisplayNode().GetWindowLevelMin()
            rangeMax = volumeNode.GetScalarVolumeDisplayNode().GetWindowLevelMax()

        shiftScale.SetScale(255 / (rangeMax - rangeMin))
        shiftScale.SetShift(-rangeMin)
        shiftScale.ClampOverflowOn()
        shiftScale.SetInputData(volumeNode.GetImageData())
        shiftScale.Update()

        # Masking
        rgbaVoxels = slicer.util.arrayFromVolume(outputRgbaVolume)
        labelVoxels = slicer.util.arrayFromVolume(labelmapVolumeNode)

        scaledInputImage = shiftScale.GetOutput()
        nshape = tuple(reversed(scaledInputImage.GetDimensions()))
        shiftScaleArray = vtk.util.numpy_support.vtk_to_numpy(scaledInputImage.GetPointData().GetScalars()).reshape(nshape)

        # Soft edge
        if softEdgeThicknessVoxel > 0.0:
            extractAlpha = vtk.vtkImageExtractComponents()
            extractAlpha.SetComponents(3)  # A from RGBA
            extractAlpha.SetInputData(outputRgbaVolume.GetImageData())

            gaussianFilter = vtk.vtkImageGaussianSmooth()
            gaussianFilter.SetInputConnection(extractAlpha.GetOutputPort())
            # Standard deviation is computed so that at "thickness" distance corresponds to 2 sigma
            # because that means 95% of the intensity is inside
            stdev = softEdgeThicknessVoxel / 2.0
            gaussianFilter.SetStandardDeviations(stdev, stdev, stdev)
            # Do not truncate the Gaussian kernel at the default 1.5 sigma,
            # because it would result in edge artifacts.
            # Larger value results in less edge artifact but increased computation time,
            # so 3.0 is a good tradeoff.
            gaussianFilter.SetRadiusFactor(3.0)
            gaussianFilter.Update()
            smoothedAlpha = gaussianFilter.GetOutput()
            nshape = tuple(reversed(smoothedAlpha.GetDimensions()))
            smoothedAlphaArray = vtk.util.numpy_support.vtk_to_numpy(smoothedAlpha.GetPointData().GetScalars()).reshape(nshape)
            rgbaVoxels[:, :, :, 3] = smoothedAlphaArray[:]

        rgbaVoxels[:, :, :, 3] = (
            np.multiply(shiftScaleArray[:].astype(np.float32), rgbaVoxels[:, :, :, 3])
            / 255.0
        ).astype(np.uint8)

        slicer.util.arrayFromVolumeModified(outputRgbaVolume)

        # Remove temporary nodes
        slicer.mrmlScene.RemoveNode(colorTableNode)
        slicer.mrmlScene.RemoveNode(labelmapVolumeNode)

    def _process(self,
                inputScalarVolume: vtkMRMLScalarVolumeNode,
                inputSegmentation: vtkMRMLSegmentationNode,
                outputRgbaVolume: vtkMRMLVectorVolumeNode,
                backgroundColorRgb: list,
                backgroundOpacityPercent: float,
                colorBleedThicknessVoxel: float=1.5,
                softEdgeThicknessVoxel: float=1.5,
                sequenceBrowserNode: Optional[vtkMRMLSequenceBrowserNode]=None,
                ) -> None:
        """
        Run the processing algorithm.
        Can be used without GUI widget.
        :param inputScalarVolume: volume to be thresholded
        :param inputSegmentation: segmentation to be used for coloring
        :param outputRgbaVolume: colorized RGBA volume
        :param backgroundColorRgb: color of voxels that are not segmented (RGB)
        :param backgroundOpacityPercent: opacity of voxels that are not segmented (0-100)
        :oaram colorBleedThicknessVoxel: how far color bleeds out (in voxels)
        :param softEdgeThicknessVoxel: edge smoothing thickness (in voxels)
        :param sequenceBrowserNode: if set to a browser node then all items of the input volume sequence will be processed
        """

        if not inputScalarVolume:
            raise ValueError("Input scalar volume is invalid")
        if not inputSegmentation:
            raise ValueError("Input segmentation is invalid")
        if not outputRgbaVolume:
            raise ValueError("Output RGBA volume is invalid")

        import numpy as np
        import time
        import vtk
        import vtk.util.numpy_support

        startTime = time.time()
        logging.info('Processing started')

        inputScalarVolumeSequence = None
        if sequenceBrowserNode:
            inputScalarVolumeSequence = sequenceBrowserNode.GetSequenceNode(inputScalarVolume)

        if inputScalarVolumeSequence is None:
            # Colorize a single volume
            self._processVolume(
                inputScalarVolume,
                inputSegmentation,
                outputRgbaVolume,
                backgroundColorRgb,
                backgroundOpacityPercent,
                colorBleedThicknessVoxel,
                softEdgeThicknessVoxel,
            )
        else:
            # Colorize a volume sequence

            # If the volume already has a sequence in the current browser node then use that
            outputSequence = sequenceBrowserNode.GetSequenceNode(outputRgbaVolume)
            if not outputSequence:
                outputSequence = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSequenceNode", outputRgbaVolume.GetName())
                sequenceBrowserNode.AddProxyNode(outputRgbaVolume, outputSequence, False)

            selectedItemNumber = sequenceBrowserNode.GetSelectedItemNumber()
            sequenceBrowserNode.PlaybackActiveOff()
            sequenceBrowserNode.SelectFirstItem()
            sequenceBrowserNode.SetRecording(inputScalarVolumeSequence, True)
            sequenceBrowserNode.SetSaveChanges(inputScalarVolumeSequence, True)
            sequenceBrowserNode.SetRecording(outputSequence, True)
            sequenceBrowserNode.SetSaveChanges(outputSequence, True)
            numberOfItems = sequenceBrowserNode.GetNumberOfItems()
            for i in range(numberOfItems):
                logging.info(f"Colorizing item {i+1}/{numberOfItems} of sequence")
                ColorizeVolumeLogic._processVolume(
                    inputScalarVolume,
                    inputSegmentation,
                    outputRgbaVolume,
                    backgroundColorRgb,
                    backgroundOpacityPercent,
                    colorBleedThicknessVoxel,
                    softEdgeThicknessVoxel,
                )
                sequenceBrowserNode.SelectNextItem()
            sequenceBrowserNode.SetSelectedItemNumber(selectedItemNumber)

        stopTime = time.time()
        logging.info(f'Processing completed in {stopTime-startTime:.2f} seconds')

        self.log("Processing completed.")

    def process(self):
        parameterNode = self.getParameterNode()
        self._process(
            parameterNode.inputScalarVolume,
            parameterNode.inputSegmentation,
            parameterNode.outputRgbaVolume,
            parameterNode.backgroundColorRgb,
            parameterNode.backgroundOpacityPercent,
            parameterNode.colorBleedThicknessVoxel,
            parameterNode.softEdgeThicknessVoxel)

    def showVolumeRendering(self, resetSettings = True) -> None:
        """
        Show volume rendering of the given volume node.
        """
        parameterNode = self.getParameterNode()
        volumeNode = parameterNode.outputRgbaVolume

        volumeRenderingLogic = slicer.modules.volumerendering.logic()
        vrDisplayNode = slicer.modules.volumerendering.logic().GetFirstVolumeRenderingDisplayNode(volumeNode)
        if not vrDisplayNode:
            vrDisplayNode = volumeRenderingLogic.CreateDefaultVolumeRenderingNodes(volumeNode)
            resetSettings = True

        vrDisplayNode.SetVisibility(True)

        if resetSettings:
            parameterNamesToReset = [
                'volumeRenderingLevelPercent',
                'volumeRenderingWindowPercent',
                'volumeRenderingOpacityPercent',
                'volumeRenderingGradientOpacityWindow',
                'volumeRenderingGradientOpacityLevel',
                'volumeRenderingGradientOpacity'
                ]
            for paramName in parameterNamesToReset:
                parameterNode.setValue(paramName, parameterNode.default(paramName).value)
            self.updateVolumeRenderingOpacityTransferFunctions()


    def updateVolumeRenderingOpacityTransferFunctions(self):

        parameterNode = self.getParameterNode()

        volumeRenderingLogic = slicer.modules.volumerendering.logic()
        vrDisplayNode = slicer.modules.volumerendering.logic().GetFirstVolumeRenderingDisplayNode(parameterNode.outputRgbaVolume)
        if not vrDisplayNode:
            return
        vrProp = vrDisplayNode.GetVolumePropertyNode()

        # Scalar opacity
        window = parameterNode.volumeRenderingWindowPercent * 255.0 / 100.0
        level = parameterNode.volumeRenderingLevelPercent * 255.0 / 100.0
        opacity = parameterNode.volumeRenderingOpacityPercent / 100.0
        nodes = [
            (0, 0.0),
            (level - window / 2, 0.0),
            (level + window / 2, opacity),
            (255, opacity),
            ]
        opacityTransferFunction = vrProp.GetScalarOpacity()
        if opacityTransferFunction.GetSize() == len(nodes):
            for index, node in enumerate(nodes):
                opacityTransferFunction.SetNodeValue(index, [node[0], node[1], 0.5, 0.0])  # extra values: midpoint, sharpness
        else:
            opacityTransferFunction.RemoveAllPoints()
            for node in nodes:
                opacityTransferFunction.AddPoint(node[0], node[1])

        # Gradient opacity
        if parameterNode.volumeRenderingGradientOpacity:
            level = parameterNode.volumeRenderingGradientOpacityLevel
            window = max(5, parameterNode.volumeRenderingGradientOpacityWindow)
            nodes = [
                (level - window/2 - 10.0, 0.0),
                (level - window/2, 0.0),
                (level + window/2, 1.0),
                (level + window/2 + 10.0, 1.0)
                ]
        else:
            nodes = [
                (-10.0, 1.0),
                (0.0, 1.0),
                (90.0, 1.0),
                (100.0, 1.0)
                ]
        gradientOpacityTransferFunction = vrProp.GetGradientOpacity()
        if gradientOpacityTransferFunction.GetSize() == len(nodes):
            for index, node in enumerate(nodes):
                gradientOpacityTransferFunction.SetNodeValue(index, [node[0], node[1], 0.5, 0.0])  # extra values: midpoint, sharpness
        else:
            gradientOpacityTransferFunction.RemoveAllPoints()
            for node in nodes:
                gradientOpacityTransferFunction.AddPoint(node[0], node[1])


#
# ColorizeVolumeTest
#

class ColorizeVolumeTest(ScriptedLoadableModuleTest):
    """
    This is the test case for your scripted module.
    Uses ScriptedLoadableModuleTest base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def setUp(self):
        """ Do whatever is needed to reset the state - typically a scene clear will be enough.
        """
        slicer.mrmlScene.Clear()

    def runTest(self):
        """Run as few or as many tests as needed here.
        """
        self.setUp()
        self.test_ColorizeVolume1()

    def test_ColorizeVolume1(self):
        """ Ideally you should have several levels of tests.  At the lowest level
        tests should exercise the functionality of the logic with different inputs
        (both valid and invalid).  At higher levels your tests should emulate the
        way the user would interact with your code and confirm that it still works
        the way you intended.
        One of the most important features of the tests is that it should alert other
        developers when their changes will have an impact on the behavior of your
        module.  For example, if a developer removes a feature that you depend on,
        your test should break so they know that the feature is needed.
        """

        self.delayDisplay("Starting the test")

        # Get input data
        import SampleData
        registerSampleData()
        inputScalarVolume = SampleData.downloadSample('CTLiver')
        inputSegmentation = SampleData.downloadSample('CTLiverSegmentation')
        self.delayDisplay('Loaded test data set')

        # Generate colorized volume
        logic = ColorizeVolumeLogic()
        logic.logCallback = lambda msg: self.delayDisplay(msg)
        parameterNode = logic.getParameterNode()
        parameterNode.inputScalarVolume = inputScalarVolume
        parameterNode.inputSegmentation = inputSegmentation
        parameterNode.outputRgbaVolume = logic.AddNewOutputVolume()
        logic.process()

        # Show volume rendering
        logic.showVolumeRendering()
        slicer.app.layoutManager().resetThreeDViews()

        self.delayDisplay('Test passed')
