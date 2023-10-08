import logging
import os
from typing import Annotated, Optional

import vtk

import slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
from slicer.parameterNodeWrapper import (
    parameterNodeWrapper,
    WithinRange,
)

from slicer import vtkMRMLScalarVolumeNode, vtkMRMLSegmentationNode, vtkMRMLVectorVolumeNode


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


#
# ColorizeVolumeParameterNode
#

@parameterNodeWrapper
class ColorizeVolumeParameterNode:
    """
    The parameters needed by module.

    inputScalarVolume - The volume to threshold.
    inputSegmentation - The output volume that will contain the inverted thresholded volume.
    softEdgeThickness - The value at which to threshold the input volume.
    outputRgbaVolume - The output volume that will contain the thresholded volume.
    maskVolume - If true, will invert the threshold.
    """
    inputScalarVolume: vtkMRMLScalarVolumeNode
    inputSegmentation: vtkMRMLSegmentationNode
    outputRgbaVolume: vtkMRMLVectorVolumeNode
    softEdgeThickness: Annotated[float, WithinRange(0, 10)] = 1.0
    maskVolume: bool = False


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

        # Connections

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

        # Buttons
        self.ui.applyButton.connect('clicked(bool)', self.onApplyButton)

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

    def setParameterNode(self, inputParameterNode: Optional[ColorizeVolumeParameterNode]) -> None:
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

    def onApplyButton(self) -> None:
        """
        Run processing when user clicks "Apply" button.
        """
        with slicer.util.tryWithErrorDisplay("Failed to compute results.", waitCursor=True):

            if not self._parameterNode.outputRgbaVolume:
                self._parameterNode.outputRgbaVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLVectorVolumeNode", f"{self._parameterNode.inputScalarVolume.GetName()} colored")

            # Compute output
            self.logic.process(self._parameterNode.inputScalarVolume, self._parameterNode.inputSegmentation, self._parameterNode.outputRgbaVolume,
                               self._parameterNode.softEdgeThickness, self._parameterNode.maskVolume)


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

    def getParameterNode(self):
        return ColorizeVolumeParameterNode(super().getParameterNode())

    def process(self,
                inputScalarVolume: vtkMRMLScalarVolumeNode,
                inputSegmentation: vtkMRMLSegmentationNode,
                outputRgbaVolume: vtkMRMLVectorVolumeNode,
                softEdgeThickness: float,
                maskVolume: bool = False,
                showResult: bool = True) -> None:
        """
        Run the processing algorithm.
        Can be used without GUI widget.
        :param inputScalarVolume: volume to be thresholded
        :param outputRgbaVolume: thresholding result
        :param softEdgeThickness: edge smoothing physical distance (in mm)
        :param invert: if True then values above the threshold will be set to 0, otherwise values below are set to 0
        :param showResult: show output volume in slice viewers
        """

        if not inputScalarVolume or not inputSegmentation or not outputRgbaVolume:
            raise ValueError("Input or output volume is invalid")

        import time
        startTime = time.time()
        logging.info('Processing started')

        volumeNode = inputScalarVolume
        segmentationNode = inputSegmentation

        volumesLogic = slicer.modules.volumes.logic()

        import vtk
        segmentIds = vtk.vtkStringArray()
        labelmapVolumeNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode", "__temp__")
        if not slicer.modules.segmentations.logic().ExportSegmentsToLabelmapNode(segmentationNode, segmentIds, labelmapVolumeNode, volumeNode):
            raise RuntimeError("Export of segment failed.")
        colorTableNode = labelmapVolumeNode.GetDisplayNode().GetColorNode()

        colorTableNode.SetColor(0,127,127,127)

        mapToRGB = vtk.vtkImageMapToColors()
        mapToRGB.ReleaseDataFlagOn()
        mapToRGB.SetOutputFormatToRGB()
        mapToRGB.SetInputData(labelmapVolumeNode.GetImageData())
        mapToRGB.SetLookupTable(colorTableNode.GetLookupTable())
        mapToRGB.Update()

        shiftScale = vtk.vtkImageShiftScale()
        shiftScale.ReleaseDataFlagOn()
        shiftScale.SetOutputScalarType(vtk.VTK_UNSIGNED_CHAR)
        [rangeMin, rangeMax] = volumeNode.GetImageData().GetScalarRange()
        shiftScale.SetScale(255 / (rangeMax-rangeMin))
        shiftScale.SetShift(-rangeMin)
        shiftScale.ClampOverflowOn()
        shiftScale.SetInputData(volumeNode.GetImageData())
        shiftScale.Update()

        appendComponents = vtk.vtkImageAppendComponents()
        shiftScale.ReleaseDataFlagOn()
        appendComponents.AddInputData(mapToRGB.GetOutput())
        appendComponents.AddInputData(shiftScale.GetOutput())
        appendComponents.Update()

        outputRgbaVolume.CopyOrientation(volumeNode)
        outputRgbaVolume.SetVoxelVectorType(slicer.vtkMRMLVolumeNode.VoxelVectorTypeColorRGBA)
        outputRgbaVolume.SetAndObserveImageData(appendComponents.GetOutput())
        outputRgbaVolume.CreateDefaultDisplayNodes()
        del appendComponents

        # Masking
        rgbaVoxels = slicer.util.arrayFromVolume(outputRgbaVolume)
        labelVoxels = slicer.util.arrayFromVolume(labelmapVolumeNode)
        rgbaVoxels[labelVoxels==0, 0:3] = 255
        if maskVolume:            
            if softEdgeThickness == 0:
                rgbaVoxels[labelVoxels==0, 3] = 0
            else:
                # Soft edge

                scaledInputImage = shiftScale.GetOutput()

                import vtk.util.numpy_support
                nshape = tuple(reversed(scaledInputImage.GetDimensions()))

                gaussianFilter = vtk.vtkImageGaussianSmooth()
                spacing = labelmapVolumeNode.GetSpacing()
                standardDeviationPixel = [1.0, 1.0, 1.0]
                for idx in range(3):
                    standardDeviationPixel[idx] = softEdgeThickness / spacing[idx]
                shiftScaleArray = vtk.util.numpy_support.vtk_to_numpy(scaledInputImage.GetPointData().GetScalars()).reshape(nshape)
                shiftScaleArray[labelVoxels==0] = 0
                gaussianFilter.SetInputData(scaledInputImage)
                gaussianFilter.SetStandardDeviations(*standardDeviationPixel)
                # Do not truncate the Gaussian kernel at the default 1.5 sigma,
                # because it would result in edge artifacts.
                # Larger value results in less edge artifact but increased computation time,
                # so 3.0 is a good tradeoff.
                gaussianFilter.SetRadiusFactor(3.0)
                gaussianFilter.Update()
                smoothedMaskedScaledArray = vtk.util.numpy_support.vtk_to_numpy(gaussianFilter.GetOutput().GetPointData().GetScalars()).reshape(nshape)

                rgbaVoxels[:, :, :, 3] = smoothedMaskedScaledArray[:]
            

        slicer.util.arrayFromVolumeModified(outputRgbaVolume)


        # Remove temporary nodes
        #slicer.mrmlScene.RemoveNode(colorTableNode)
        slicer.mrmlScene.RemoveNode(labelmapVolumeNode)

        stopTime = time.time()
        logging.info(f'Processing completed in {stopTime-startTime:.2f} seconds')


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

        # Get/create input data

        import SampleData
        registerSampleData()
        inputScalarVolume = SampleData.downloadSample('ColorizeVolume1')
        self.delayDisplay('Loaded test data set')

        inputScalarRange = inputScalarVolume.GetImageData().GetScalarRange()
        self.assertEqual(inputScalarRange[0], 0)
        self.assertEqual(inputScalarRange[1], 695)

        outputRgbaVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
        threshold = 100

        # Test the module logic

        logic = ColorizeVolumeLogic()

        # Test algorithm with non-inverted threshold
        logic.process(inputScalarVolume, outputRgbaVolume, threshold, True)
        outputScalarRange = outputRgbaVolume.GetImageData().GetScalarRange()
        self.assertEqual(outputScalarRange[0], inputScalarRange[0])
        self.assertEqual(outputScalarRange[1], threshold)

        # Test algorithm with inverted threshold
        logic.process(inputScalarVolume, outputRgbaVolume, threshold, False)
        outputScalarRange = outputRgbaVolume.GetImageData().GetScalarRange()
        self.assertEqual(outputScalarRange[0], inputScalarRange[0])
        self.assertEqual(outputScalarRange[1], inputScalarRange[1])

        self.delayDisplay('Test passed')


# TODO: use alpha of segments? to allow segments to be more/less visible
# TODO: mask with all segments, with smooth edges
# TODO: expand segmentation to include all voxels that are within a given distance from the surface;
#       using median filter that ignores 0; this would remove the dark halo around the segments
