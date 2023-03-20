import logging
import os

import vtk

import slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin


#
# RemoveCtTable
#

class RemoveCtTable(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Remove CT table"
    self.parent.categories = ["Segmentation"]
    self.parent.dependencies = []
    self.parent.contributors = ["Andras Lasso (PerkLab)"]
    self.parent.helpText = """
This module removes the patient table from CT images.
See more information in <a href="https://github.com/PerkLab/SlicerSandbox#remove-ct-table">module documentation</a>.
"""
    self.parent.acknowledgementText = """
"""

#
# RemoveCtTableWidget
#

class RemoveCtTableWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
  """Uses ScriptedLoadableModuleWidget base class, available at:
  https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent=None):
    """
    Called when the user opens the module the first time and the widget is initialized.
    """
    ScriptedLoadableModuleWidget.__init__(self, parent)
    VTKObservationMixin.__init__(self)  # needed for parameter node observation
    self.logic = None
    self._parameterNode = None
    self._updatingGUIFromParameterNode = False

  def setup(self):
    """
    Called when the user opens the module the first time and the widget is initialized.
    """
    ScriptedLoadableModuleWidget.setup(self)

    # Load widget from .ui file (created by Qt Designer).
    # Additional widgets can be instantiated manually and added to self.layout.
    uiWidget = slicer.util.loadUI(self.resourcePath('UI/RemoveCtTable.ui'))
    self.layout.addWidget(uiWidget)
    self.ui = slicer.util.childWidgetVariables(uiWidget)

    # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
    # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
    # "setMRMLScene(vtkMRMLScene*)" slot.
    uiWidget.setMRMLScene(slicer.mrmlScene)

    # Create logic class. Logic implements all computations that should be possible to run
    # in batch mode, without a graphical user interface.
    self.logic = RemoveCtTableLogic()

    # Connections

    # These connections ensure that we update parameter node when scene is closed
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

    # These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
    # (in the selected parameter node).
    self.ui.inputSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
    self.ui.outputSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
    self.ui.imageThresholdSliderWidget.connect("valueChanged(double)", self.updateParameterNodeFromGUI)
    self.ui.paddingSliderWidget.connect("valueChanged(double)", self.updateParameterNodeFromGUI)
    self.ui.accuracySliderWidget.connect("valueChanged(double)", self.updateParameterNodeFromGUI)

    # Buttons
    self.ui.applyButton.connect('clicked(bool)', self.onApplyButton)

    # Make sure parameter node is initialized (needed for module reload)
    self.initializeParameterNode()

  def cleanup(self):
    """
    Called when the application closes and the module widget is destroyed.
    """
    self.removeObservers()

  def enter(self):
    """
    Called each time the user opens this module.
    """
    # Make sure parameter node exists and observed
    self.initializeParameterNode()

  def exit(self):
    """
    Called each time the user opens a different module.
    """
    # Do not react to parameter node changes (GUI wlil be updated when the user enters into the module)
    self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

  def onSceneStartClose(self, caller, event):
    """
    Called just before the scene is closed.
    """
    # Parameter node will be reset, do not use it anymore
    self.setParameterNode(None)

  def onSceneEndClose(self, caller, event):
    """
    Called just after the scene is closed.
    """
    # If this module is shown while the scene is closed then recreate a new parameter node immediately
    if self.parent.isEntered:
      self.initializeParameterNode()

  def initializeParameterNode(self):
    """
    Ensure parameter node exists and observed.
    """
    # Parameter node stores all user choices in parameter values, node selections, etc.
    # so that when the scene is saved and reloaded, these settings are restored.

    self.setParameterNode(self.logic.getParameterNode())

    # Select default input nodes if nothing is selected yet to save a few clicks for the user
    if not self._parameterNode.GetNodeReference("InputVolume"):
      firstVolumeNode = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLScalarVolumeNode")
      if firstVolumeNode:
        self._parameterNode.SetNodeReferenceID("InputVolume", firstVolumeNode.GetID())

  def setParameterNode(self, inputParameterNode):
    """
    Set and observe parameter node.
    Observation is needed because when the parameter node is changed then the GUI must be updated immediately.
    """

    if inputParameterNode:
      self.logic.setDefaultParameters(inputParameterNode)

    # Unobserve previously selected parameter node and add an observer to the newly selected.
    # Changes of parameter node are observed so that whenever parameters are changed by a script or any other module
    # those are reflected immediately in the GUI.
    if self._parameterNode is not None:
      self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
    self._parameterNode = inputParameterNode
    if self._parameterNode is not None:
      self.addObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

    # Initial GUI update
    self.updateGUIFromParameterNode()

  def updateGUIFromParameterNode(self, caller=None, event=None):
    """
    This method is called whenever parameter node is changed.
    The module GUI is updated to show the current state of the parameter node.
    """

    if self._parameterNode is None or self._updatingGUIFromParameterNode:
      return

    # Make sure GUI changes do not call updateParameterNodeFromGUI (it could cause infinite loop)
    self._updatingGUIFromParameterNode = True

    # Update node selectors and sliders
    self.ui.inputSelector.setCurrentNode(self._parameterNode.GetNodeReference("InputVolume"))
    self.ui.outputSelector.setCurrentNode(self._parameterNode.GetNodeReference("OutputVolume"))

    # Update buttons states and tooltips
    if self._parameterNode.GetNodeReference("InputVolume") and self._parameterNode.GetNodeReference("OutputVolume"):
      self.ui.applyButton.toolTip = "Compute output volume"
      self.ui.applyButton.enabled = True
    else:
      self.ui.applyButton.toolTip = "Select input and output volume nodes"
      self.ui.applyButton.enabled = False

    # All the GUI updates are done
    self._updatingGUIFromParameterNode = False

  def updateParameterNodeFromGUI(self, caller=None, event=None):
    """
    This method is called when the user makes any change in the GUI.
    The changes are saved into the parameter node (so that they are restored when the scene is saved and loaded).
    """

    if self._parameterNode is None or self._updatingGUIFromParameterNode:
      return

    wasModified = self._parameterNode.StartModify()  # Modify all properties in a single batch

    self._parameterNode.SetNodeReferenceID("InputVolume", self.ui.inputSelector.currentNodeID)
    self._parameterNode.SetNodeReferenceID("OutputVolume", self.ui.outputSelector.currentNodeID)
    self._parameterNode.SetParameter("Threshold", str(self.ui.imageThresholdSliderWidget.value))
    self._parameterNode.SetParameter("Padding", str(self.ui.paddingSliderWidget.value))
    self._parameterNode.SetParameter("Accuracy", str(self.ui.accuracySliderWidget.value))

    self._parameterNode.EndModify(wasModified)

  def onApplyButton(self):
    """
    Run processing when user clicks "Apply" button.
    """
    with slicer.util.tryWithErrorDisplay("Failed to compute results.", waitCursor=True):

      # Compute output
      self.logic.process(self.ui.inputSelector.currentNode(), self.ui.outputSelector.currentNode(),
        threshold = self.ui.imageThresholdSliderWidget.value,
        padding = self.ui.paddingSliderWidget.value,
        accuracy = self.ui.accuracySliderWidget.value
        )


#
# RemoveCtTableLogic
#

class RemoveCtTableLogic(ScriptedLoadableModuleLogic):
  """This class should implement all the actual
  computation done by your module.  The interface
  should be such that other python code can import
  this class and make use of the functionality without
  requiring an instance of the Widget.
  Uses ScriptedLoadableModuleLogic base class, available at:
  https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self):
    """
    Called when the logic class is instantiated. Can be used for initializing member variables.
    """
    ScriptedLoadableModuleLogic.__init__(self)

  def setDefaultParameters(self, parameterNode):
    """
    Initialize parameter node with default settings.
    """
    if not parameterNode.GetParameter("Threshold"):
      parameterNode.SetParameter("Threshold", "-50.0")

  def process(self, inputVolume, outputVolume, threshold, fillValue=None, padding=None, accuracy=None, showResult=True):
    """
    This script automatically removes table from a CT volume
    :param inputVolume: volume to be thresholded
    :param outputVolume: same as input image but patient table blanked out
    :param imageThreshold: patient table voxel value must be below this threshold
    :param showResult: show output volume in slice viewers
    :param fillValue: this value will be used to blank out the table. By default it is set to -1000 (HU of air)
    :param padding: add a fixed amount of margin around the extracted region of interest.
      Increase the value if relevant regions are blanked out in the output. By default it is set to 0.
    :param accuracy: smaller accuracy factor will make the algorithm faster but less accurate. Default is 0.3.
    """

    if not inputVolume or not outputVolume:
      raise ValueError("Input or output volume is invalid")

    import time
    startTime = time.time()
    logging.info('Processing started')


    # Process
    ################################################

    # Create segmentation
    segmentationNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode", "__temp_RemoveCtTableSegmentation")
    segmentationNode.CreateDefaultDisplayNodes() # only needed for display
    segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(inputVolume)

    # Create segment editor to get access to effects
    #slicer.app.processEvents()
    segmentEditorWidget = slicer.qMRMLSegmentEditorWidget()

    # Check if Wrap Solidify extension is installed
    if not segmentEditorWidget.effectByName("Wrap Solidify"):
      raise ValueError("Please install 'SurfaceWrapSolidify' extension using Extension Manager.")

    # To show segment editor widget (useful for debugging): segmentEditorWidget.show()
    segmentEditorWidget.setMRMLScene(slicer.mrmlScene)
    segmentEditorNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentEditorNode", "__temp_RemoveCtTableSegmentEditor")
    segmentEditorWidget.setMRMLSegmentEditorNode(segmentEditorNode)
    segmentEditorWidget.setSegmentationNode(segmentationNode)
    segmentEditorWidget.setSourceVolumeNode(inputVolume)

    # Check that required extensions are installed


    # Create object of interest segment by thresholding
    slicer.app.processEvents()
    volumeScalarRange = inputVolume.GetImageData().GetScalarRange()
    objectSegmentID = segmentationNode.GetSegmentation().AddEmptySegment()
    segmentEditorNode.SetSelectedSegmentID(objectSegmentID)
    segmentEditorWidget.setActiveEffectByName("Threshold")
    effect = segmentEditorWidget.activeEffect()
    effect.setParameter("MinimumThreshold",str(threshold))
    effect.setParameter("MaximumThreshold",str(volumeScalarRange[1]))
    effect.self().onApply()

    # Find largest object, remove all other regions from the segment
    slicer.app.processEvents()
    segmentEditorWidget.setActiveEffectByName("Islands")
    effect = segmentEditorWidget.activeEffect()
    effect.setParameterDefault("Operation", "KEEP_LARGEST_ISLAND")
    effect.self().onApply()

    # Fill holes in the segment to create a solid region of interest
    slicer.app.processEvents()
    segmentEditorWidget.setActiveEffectByName("Wrap Solidify")
    effect = segmentEditorWidget.activeEffect()
    effect.setParameter("region", "outerSurface")
    effect.setParameter("outputType", "segment")
    if accuracy is None:
      accuracy = 0.3
    effect.setParameter("remeshOversampling", accuracy)  # speed up solidification by lowering resolution
    effect.self().onApply()

    if padding is not None:
      slicer.app.processEvents()
      segmentEditorWidget.setActiveEffectByName("Margin")
      effect = segmentEditorWidget.activeEffect()
      effect.setParameter("MarginSizeMm", str(padding))
      effect.self().onApply()

    import SegmentEditorEffects
    maskVolumeWithSegment = SegmentEditorEffects.SegmentEditorMaskVolumeEffect.maskVolumeWithSegment

    # Blank out the volume outside the object segment
    if fillValue is None:
      fillValue = -1000  # density of air in CT images
    maskVolumeWithSegment(segmentationNode, objectSegmentID, "FILL_OUTSIDE", [fillValue], inputVolume, outputVolume)

    # Remove temporary nodes and widget
    segmentEditorWidget = None
    slicer.mrmlScene.RemoveNode(segmentEditorNode)
    slicer.mrmlScene.RemoveNode(segmentationNode)

    # Show masked volume
    if showResult:
      # maskedVolume = slicer.mrmlScene.GetFirstNodeByName(inputVolume.GetName()+" masked")
      slicer.util.setSliceViewerLayers(background=outputVolume)

    stopTime = time.time()
    logging.info(f'Processing completed in {stopTime-startTime:.2f} seconds')


#
# RemoveCtTableTest
#

class RemoveCtTableTest(ScriptedLoadableModuleTest):
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
    self.test_RemoveCtTable1()

  def test_RemoveCtTable1(self):
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

    import SampleData

    # Get input image (in this example, download a sample data set)
    sampleDataLogic = SampleData.SampleDataLogic()
    inputVolume = sampleDataLogic.downloadCTACardio()
    threshold = -44
    fillValue = -1999  # unique value around, just to test if custom fill value is used

    outputVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")

    # Test the module logic

    logic = RemoveCtTableLogic()

    # Test algorithm with non-inverted threshold
    logic.process(inputVolume, outputVolume, threshold, fillValue, padding = 3.0, accuracy = 0.5)

    # Check if table voxel is blanked out
    tableVoxelIndex = (113, 429, 160)
    # Original table value was voxel value was above threshold
    self.assertNotEqual(inputVolume.GetImageData().GetScalarComponentAsDouble(*tableVoxelIndex, 0), fillValue)
    # Original voxel value was above threshold
    self.assertEqual(outputVolume.GetImageData().GetScalarComponentAsDouble(*tableVoxelIndex, 0), fillValue)

    # Check if non-table voxel is left unchanged
    nonTableVoxelIndex = (59, 320, 160)
    self.assertEqual(
      inputVolume.GetImageData().GetScalarComponentAsDouble(*nonTableVoxelIndex, 0),
      outputVolume.GetImageData().GetScalarComponentAsDouble(*nonTableVoxelIndex, 0))

    self.delayDisplay('Test passed')
