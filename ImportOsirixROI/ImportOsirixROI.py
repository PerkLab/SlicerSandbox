import os
import unittest
import logging
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

#
# ImportOsirixROI
#

class ImportOsirixROI(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Import OsiriX ROI"
    self.parent.categories = ["Utilities"]
    self.parent.dependencies = []
    self.parent.contributors = ["Andras Lasso (Queen's, PerkLab)"]
    self.parent.helpText = """
Import Osirix ROI files to Slicer segmentation.
"""
    self.parent.helpText += self.getDefaultModuleDocumentationLink()  # TODO: verify that the default URL is correct or change it to the actual documentation
    self.parent.acknowledgementText = """
This file was originally developed by Andras Lasso, PerkLab.
"""

#
# ImportOsirixROIWidget
#

class ImportOsirixROIWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
  """Uses ScriptedLoadableModuleWidget base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent=None):
    """
    Called when the user opens the module the first time and the widget is initialized.
    """
    ScriptedLoadableModuleWidget.__init__(self, parent)
    VTKObservationMixin.__init__(self)  # needed for parameter node observation
    self.logic = None
    self._parameterNode = None

  def setup(self):
    """
    Called when the user opens the module the first time and the widget is initialized.
    """
    ScriptedLoadableModuleWidget.setup(self)

    # Load widget from .ui file (created by Qt Designer)
    uiWidget = slicer.util.loadUI(self.resourcePath('UI/ImportOsirixROI.ui'))
    self.layout.addWidget(uiWidget)
    self.ui = slicer.util.childWidgetVariables(uiWidget)

    # Set scene in MRML widgets. Make sure that in Qt designer
    # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
    # "setMRMLScene(vtkMRMLScene*)" slot.
    uiWidget.setMRMLScene(slicer.mrmlScene)

    # Create a new parameterNode
    # This parameterNode stores all user choices in parameter values, node selections, etc.
    # so that when the scene is saved and reloaded, these settings are restored.
    self.logic = ImportOsirixROILogic()
    self.ui.parameterNodeSelector.addAttribute("vtkMRMLScriptedModuleNode", "ModuleName", self.moduleName)
    self.setParameterNode(self.logic.getParameterNode())

    # Connections
    self.ui.parameterNodeSelector.connect('currentNodeChanged(vtkMRMLNode*)', self.setParameterNode)
    self.ui.applyButton.connect('clicked(bool)', self.onApplyButton)

    # These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
    # (in the selected parameter node).
    
    self.ui.inputRoiPathLineEdit.connect("currentPathChanged(QString)", self.updateParameterNodeFromGUI)
    self.ui.outputSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)

    # Initial GUI update
    self.updateGUIFromParameterNode()

  def cleanup(self):
    """
    Called when the application closes and the module widget is destroyed.
    """
    self.removeObservers()

  def setParameterNode(self, inputParameterNode):
    """
    Adds observers to the selected parameter node. Observation is needed because when the
    parameter node is changed then the GUI must be updated immediately.
    """

    if inputParameterNode:
      self.logic.setDefaultParameters(inputParameterNode)

    # Set parameter node in the parameter node selector widget
    wasBlocked = self.ui.parameterNodeSelector.blockSignals(True)
    self.ui.parameterNodeSelector.setCurrentNode(inputParameterNode)
    self.ui.parameterNodeSelector.blockSignals(wasBlocked)

    if inputParameterNode == self._parameterNode:
      # No change
      return

    # Unobserve previusly selected parameter node and add an observer to the newly selected.
    # Changes of parameter node are observed so that whenever parameters are changed by a script or any other module
    # those are reflected immediately in the GUI.
    if self._parameterNode is not None:
      self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
    if inputParameterNode is not None:
      self.addObserver(inputParameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
    self._parameterNode = inputParameterNode

    # Initial GUI update
    self.updateGUIFromParameterNode()

  def updateGUIFromParameterNode(self, caller=None, event=None):
    """
    This method is called whenever parameter node is changed.
    The module GUI is updated to show the current state of the parameter node.
    """

    # Disable all sections if no parameter node is selected
    self.ui.basicCollapsibleButton.enabled = self._parameterNode is not None
    if self._parameterNode is None:
      return

    # Update each widget from parameter node
    # Need to temporarily block signals to prevent infinite recursion (MRML node update triggers
    # GUI update, which triggers MRML node update, which triggers GUI update, ...)

    wasBlocked = self.ui.inputRoiPathLineEdit.blockSignals(True)
    self.ui.inputRoiPathLineEdit.currentPath = self._parameterNode.GetParameter("InputRoiFilePath")
    self.ui.inputRoiPathLineEdit.blockSignals(wasBlocked)

    wasBlocked = self.ui.outputSelector.blockSignals(True)
    self.ui.outputSelector.setCurrentNode(self._parameterNode.GetNodeReference("OutputSegmentation"))
    self.ui.outputSelector.blockSignals(wasBlocked)

    # Update buttons states and tooltips
    if self._parameterNode.GetParameter("InputRoiFilePath") and self._parameterNode.GetNodeReference("OutputSegmentation"):
      self.ui.applyButton.toolTip = "Convert"
      self.ui.applyButton.enabled = True
    else:
      self.ui.applyButton.toolTip = "Select input and output files"
      self.ui.applyButton.enabled = False

  def updateParameterNodeFromGUI(self, caller=None, event=None):
    """
    This method is called when the user makes any change in the GUI.
    The changes are saved into the parameter node (so that they are restored when the scene is saved and loaded).
    """

    if self._parameterNode is None:
      return

    self._parameterNode.SetParameter("InputRoiFilePath", self.ui.inputRoiPathLineEdit.currentPath)
    self._parameterNode.SetNodeReferenceID("OutputSegmentation", self.ui.outputSelector.currentNodeID)

  def onApplyButton(self):
    """
    Run processing when user clicks "Apply" button.
    """
    self.ui.inputRoiPathLineEdit.addCurrentPathToHistory()
    try:
      self.logic.importOsirixRoiFileToSegmentation(self.ui.inputRoiPathLineEdit.currentPath, self._parameterNode.GetNodeReference("OutputSegmentation"))
    except Exception as e:
      slicer.util.errorDisplay("Import failed: "+str(e))
      import traceback
      traceback.print_exc()


#
# ImportOsirixROILogic
#

class ImportOsirixROILogic(ScriptedLoadableModuleLogic):
  """This class should implement all the actual
  computation done by your module.  The interface
  should be such that other python code can import
  this class and make use of the functionality without
  requiring an instance of the Widget.
  Uses ScriptedLoadableModuleLogic base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def setDefaultParameters(self, parameterNode):
    """
    Initialize parameter node with default settings.
    """
    pass

  def importOsirixRoiFileToSegmentation(self, inputRoiFilePath, outputSegmentationNode):
    """
    Run the processing algorithm.
    Can be used without GUI widget.
    :param inputRoiFilePath: input OsiriX ROI file
    :param outputSegmentation: output segmentation node
    """

    if not inputRoiFilePath or not outputSegmentationNode:
      raise ValueError("Input file or output segmentation node is invalid")

    logging.info('Processing started')

    import json
    with open(inputRoiFilePath) as f:
      inputRoi = json.load(f)

    outputSegmentationNode.CreateDefaultDisplayNodes()
    segmentation = outputSegmentationNode.GetSegmentation()
    segmentation.SetMasterRepresentationName(slicer.vtkSegmentationConverter.GetPlanarContourRepresentationName())

    roiContourPoints = vtk.vtkPoints()
    roiContourCells = vtk.vtkCellArray()
    for contour in inputRoi:
      roiPoints = contour["ROI3DPoints"]
      cellPointIds = []
      for roiPoint in roiPoints:
        roiPointStrList = roiPoint.strip('[]').split(',')
        cellPointIds.append(roiContourPoints.InsertNextPoint(-float(roiPointStrList[0]), -float(roiPointStrList[1]), float(roiPointStrList[2])))
      contourIndex = roiContourCells.InsertNextCell(len(cellPointIds)+1)
      for cellPointId in cellPointIds:
        roiContourCells.InsertCellPoint(cellPointId)
      roiContourCells.InsertCellPoint(cellPointIds[0])  # close the contour

    roiPolyData = vtk.vtkPolyData()
    roiPolyData.SetPoints(roiContourPoints)
    roiPolyData.SetLines(roiContourCells)

    color = [ 1.0, 0.0, 0.0 ]
    name = inputRoi[0]["Name"]

    segment = slicer.vtkSegment()
    segment.SetName(name)
    segment.SetColor(color)
    segment.AddRepresentation(slicer.vtkSegmentationConverter.GetPlanarContourRepresentationName(), roiPolyData)

    segmentation.AddSegment(segment)

    outputSegmentationNode.CreateBinaryLabelmapRepresentation()
    outputSegmentationNode.CreateClosedSurfaceRepresentation()
    outputSegmentationNode.GetDisplayNode().SetPreferredDisplayRepresentationName2D(slicer.vtkSegmentationConverter.GetBinaryLabelmapRepresentationName())
    outputSegmentationNode.GetDisplayNode().SetPreferredDisplayRepresentationName3D(slicer.vtkSegmentationConverter.GetClosedSurfaceRepresentationName())

    logging.info('Processing completed')

#
# ImportOsirixROITest
#

class ImportOsirixROITest(ScriptedLoadableModuleTest):
  """
  This is the test case for your scripted module.
  Uses ScriptedLoadableModuleTest base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def setUp(self):
    """ Do whatever is needed to reset the state - typically a scene clear will be enough.
    """
    slicer.mrmlScene.Clear(0)

  def runTest(self):
    """Run as few or as many tests as needed here.
    """
    self.setUp()
    self.test_ImportOsirixROI1()

  def test_ImportOsirixROI1(self):
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
    inputVolume = SampleData.downloadFromURL(
      nodeNames='OsirixTestROI_1',
      fileNames='MR-Head.nrrd',
      loadFileTypes='TextFile',
      uris='https://github.com/Slicer/SlicerTestingData/releases/download/MD5/39b01631b7b38232a220007230624c8e',
      checksums='MD5:39b01631b7b38232a220007230624c8e')[0]
    self.delayDisplay('Finished with download and loading')

    inputScalarRange = inputVolume.GetImageData().GetScalarRange()
    self.assertEqual(inputScalarRange[0], 0)
    self.assertEqual(inputScalarRange[1], 279)

    outputVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
    threshold = 50

    # Test the module logic

    logic = ImportOsirixROILogic()

    # Test algorithm with non-inverted threshold
    logic.run(inputVolume, outputVolume, threshold, True)
    outputScalarRange = outputVolume.GetImageData().GetScalarRange()
    self.assertEqual(outputScalarRange[0], inputScalarRange[0])
    self.assertEqual(outputScalarRange[1], threshold)

    # Test algorithm with inverted threshold
    logic.run(inputVolume, outputVolume, threshold, False)
    outputScalarRange = outputVolume.GetImageData().GetScalarRange()
    self.assertEqual(outputScalarRange[0], inputScalarRange[0])
    self.assertEqual(outputScalarRange[1], inputScalarRange[1])

    self.delayDisplay('Test passed')
