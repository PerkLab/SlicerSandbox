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
  https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
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
    self.logic.logCallback = self.logCallback
    self.ui.parameterNodeSelector.addAttribute("vtkMRMLScriptedModuleNode", "ModuleName", self.moduleName)
    self.setParameterNode(self.logic.getParameterNode())

    # Connections
    self.ui.parameterNodeSelector.connect('currentNodeChanged(vtkMRMLNode*)', self.setParameterNode)
    self.ui.applyButton.connect('clicked(bool)', self.onApplyButton)

    # These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
    # (in the selected parameter node).
    
    self.ui.inputRoiPathLineEdit.connect("currentPathChanged(QString)", self.updateParameterNodeFromGUI)
    self.ui.outputSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
    self.ui.smoothingCheckBox.connect("toggled(bool)", self.updateParameterNodeFromGUI)

    self.ui.progressBar.hide()

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

    # Unobserve previously selected parameter node and add an observer to the newly selected.
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

    wasBlocked = self.ui.smoothingCheckBox.blockSignals(True)
    self.ui.smoothingCheckBox.checked = self._parameterNode.GetParameter("Smoothing") == "true"
    self.ui.smoothingCheckBox.blockSignals(wasBlocked)

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
    self._parameterNode.SetParameter("Smoothing", "true" if self.ui.smoothingCheckBox.checked else "false")

  def onApplyButton(self):
    """
    Run processing when user clicks "Apply" button.
    """

    if not hasattr(slicer.modules, 'dicomrtimportexport'):
      slicer.util.warningDisplay("SlicerRT extension is not installed. Segmentation will be imported as a set of parallel contours. Install SlicerRT extension to create segmentation as a solid object.")

    self.ui.progressBar.value = 0
    self.ui.progressLabel.text = ""
    self.ui.progressBar.show()
    self.ui.inputRoiPathLineEdit.addCurrentPathToHistory()
    try:
      self.logic.importOsirixRoiFileToSegmentation(self.ui.inputRoiPathLineEdit.currentPath,
                                                   self.ui.outputSelector.currentNode(),
                                                   self.ui.smoothingCheckBox.checked)
      self.ui.progressLabel.text = "Import completed."
    except Exception as e:
      slicer.util.errorDisplay("Import failed: "+str(e))
      import traceback
      traceback.print_exc()
      self.ui.progressLabel.text = "Import failed."
    self.ui.progressBar.hide()

  def logCallback(self, message, percentComplete):
    self.ui.progressBar.value = int(percentComplete)
    self.ui.progressLabel.text = message
    slicer.app.processEvents()

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
  https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
  """
  def __init__(self):
    ScriptedLoadableModuleLogic.__init__(self)
    self.logCallback = None

  def log(self, msg, percentComplete):
    if self.logCallback:
      self.logCallback(msg, percentComplete)

  def setDefaultParameters(self, parameterNode):
    """
    Initialize parameter node with default settings.
    """
    parameterNode.SetParameter("Smoothing", "true")

  def _pointCoordinatesFromStringList(self, roiPointsStr, separators):
    # Get points as numpy array in RAS coordinate system
    # from string list in LPS coordinate system
    import numpy as np
    roiPoints = np.zeros([len(roiPointsStr), 3])
    for pointIndex, roiPointStr in enumerate(roiPointsStr):
      roiPointStrList = roiPointStr.strip(separators).split(',')
      roiPoints[pointIndex] = [-float(roiPointStrList[0]), -float(roiPointStrList[1]), float(roiPointStrList[2])]
    return roiPoints

  def _smoothCurve(self, rawPointsArray):
    # Convert numpy array to vtkPoints
    rawPoints = vtk.vtkPoints()
    for rawPoint in rawPointsArray:
      rawPoints.InsertNextPoint(rawPoint)
    # Interpolate
    rawPolyData = vtk.vtkPolyData()
    rawPolyData.SetPoints(rawPoints)
    curveGenerator = slicer.vtkCurveGenerator()
    curveGenerator.SetInputData(rawPolyData)
    curveGenerator.SetCurveTypeToKochanekSpline()
    curveGenerator.CurveIsClosedOn()
    curveGenerator.Update()
    smoothedPolyData = curveGenerator.GetOutput()
    smoothedPoints = smoothedPolyData.GetPoints()
    # Export to numpy array
    numberOfPoints = smoothedPoints.GetNumberOfPoints()
    import numpy as np
    smoothedPointsArray = np.zeros([numberOfPoints, 3])
    for pointIndex in range(numberOfPoints):
      smoothedPointsArray[pointIndex] = smoothedPoints.GetPoint(pointIndex)
    return smoothedPointsArray

  def importOsirixRoiFileToSegmentation(self, inputRoi, outputSegmentationNode, smoothing=True, labelmapOutput=False):
    """
    Run the processing algorithm.
    Can be used without GUI widget.
    :param inputRoi: input OsiriX ROI file path or text node
    :param outputSegmentation: output segmentation node
    """

    if not inputRoi or not outputSegmentationNode:
      raise ValueError("Input file or output segmentation node is invalid")

    logging.info('Processing started')

    inputRoiData = None
    import json
    import plistlib
    if isinstance(inputRoi, str):
      filename, ext = os.path.splitext(inputRoi)
      if ext.lower() == '.json':
        with open(inputRoi) as f:
            inputRoiData = json.load(f)
      else:
        with open(inputRoi, 'rb') as f:  # Open the file in binary mode
            inputRoiData = plistlib.load(f, fmt=None)
    elif isinstance(inputRoi, slicer.vtkMRMLTextNode):
      try:
        inputRoiData = json.loads(inputRoi.GetText(), fmt=None)
      except:
        inputRoiData = plistlib.loads(inputRoi.GetText(), fmt=None)
    else:
      raise TypeError("inputRoi is expected to be a string or vtkMRMLTextNode")

    outputSegmentationNode.CreateDefaultDisplayNodes()
    segmentation = outputSegmentationNode.GetSegmentation()
    segmentation.SetSourceRepresentationName(slicer.vtkSegmentationConverter.GetPlanarContourRepresentationName())

    roiDescriptions = {}  # map from ROI name to RoiDescription

    class RoiDescription(object):
      def __init__(self):
        self.roiContourPoints = vtk.vtkPoints()
        self.roiContourCells = vtk.vtkCellArray()
      def addRoiPoints(self, roiPoints):
        if len(roiPoints) == 0:
          raise ValueError("roiPoints is empty")
        cellPointIds = []
        for roiPoint in roiPoints:
          cellPointIds.append(self.roiContourPoints.InsertNextPoint(roiPoint))
        contourIndex = self.roiContourCells.InsertNextCell(len(cellPointIds)+1)
        for cellPointId in cellPointIds:
          self.roiContourCells.InsertCellPoint(cellPointId)
        self.roiContourCells.InsertCellPoint(cellPointIds[0])

    if "Images" not in inputRoiData:
      for contourIndex, contour in enumerate(inputRoiData):
        # Get/create ROI description
        name = contour["Name"]
        roiPoints = self._pointCoordinatesFromStringList(contour["ROI3DPoints"], '[]')
        if len(roiPoints) == 0:
          logging.warning(f"Contour [{contourIndex}] ({name}) is empty")
          continue
        try:
          roiDescription = roiDescriptions[name]
        except KeyError:
          roiDescription = RoiDescription()
          roiDescriptions[name] = roiDescription
        if smoothing:
          roiPoints = self._smoothCurve(roiPoints)
        roiDescription.addRoiPoints(roiPoints)
        self.log(f"Importing {len(roiDescriptions)} ROIs", 25.0 * contourIndex / len(inputRoiData))
    else:
      # Output of OsiriX "Export ROIs" plugin
      for imageIndex, image in enumerate(inputRoiData['Images']):
        rois = image['ROIs']
        for roiIndex, roi in enumerate(rois):
          name = roi["Name"]
          # Add points
          roiPoints = self._pointCoordinatesFromStringList(roi['Point_mm'], '()')
          if len(roiPoints) == 0:
            logging.warning(f"ROI [{roiIndex}] ({name}) of image {imageIndex} is empty")
            continue
          # Get/create ROI description
          try:
            roiDescription = roiDescriptions[name]
          except KeyError:
            roiDescription = RoiDescription()
            roiDescriptions[name] = roiDescription
          if smoothing:
            roiPoints = self._smoothCurve(roiPoints)
          roiDescription.addRoiPoints(roiPoints)
          self.log(f"Importing {len(roiDescriptions)} ROIs", 25.0 * imageIndex / len(inputRoiData["Images"]))

    colorNode = slicer.mrmlScene.GetNodeByID(slicer.modules.colors.logic().GetDefaultLabelMapColorNodeID())

    for segmentIndex, name in enumerate(roiDescriptions):
      self.log(f"Creating segment {segmentIndex+1} of {len(roiDescriptions)}", 25.0 + 50.0 * segmentIndex / len(roiDescriptions))

      roiDescription = roiDescriptions[name]

      colorRGBA = [0,0,0,0]
      colorNode.GetColor(segmentIndex + 1, colorRGBA)

      roiPolyData = vtk.vtkPolyData()
      roiPolyData.SetPoints(roiDescription.roiContourPoints)
      roiPolyData.SetLines(roiDescription.roiContourCells)

      normals = vtk.vtkPolyDataNormals()
      normals.SetInputData(roiPolyData)
      normals.Update()

      segment = slicer.vtkSegment()
      segment.SetName(name)
      segment.SetColor(colorRGBA[:3])
      segment.AddRepresentation(slicer.vtkSegmentationConverter.GetPlanarContourRepresentationName(), roiPolyData)

      segmentation.AddSegment(segment)

    self.log("Creating representations...", 80)
    if labelmapOutput:
      outputSegmentationNode.CreateBinaryLabelmapRepresentation()
      outputSegmentationNode.CreateClosedSurfaceRepresentation()
      outputSegmentationNode.GetDisplayNode().SetPreferredDisplayRepresentationName2D(slicer.vtkSegmentationConverter.GetBinaryLabelmapRepresentationName())
      outputSegmentationNode.GetDisplayNode().SetPreferredDisplayRepresentationName3D(slicer.vtkSegmentationConverter.GetClosedSurfaceRepresentationName())
    else:
      outputSegmentationNode.CreateClosedSurfaceRepresentation()
      outputSegmentationNode.GetDisplayNode().SetPreferredDisplayRepresentationName2D(
        slicer.vtkSegmentationConverter.GetClosedSurfaceRepresentationName())
      outputSegmentationNode.GetDisplayNode().SetPreferredDisplayRepresentationName3D(
        slicer.vtkSegmentationConverter.GetClosedSurfaceRepresentationName())

    logging.info('Processing completed')

#
# ImportOsirixROITest
#

class ImportOsirixROITest(ScriptedLoadableModuleTest):
  """
  This is the test case for your scripted module.
  Uses ScriptedLoadableModuleTest base class, available at:
  https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
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
    jsonTextNode = SampleData.downloadFromURL(
      nodeNames='OsirixTestROI_1',
      fileNames='OsirixTestROI_1.json',
      loadFileTypes='TextFile',
      uris='https://raw.githubusercontent.com/PerkLab/SlicerSandbox/master/ImportOsirixROI/Testing/Data/OsirixTestROI_1.json',
      checksums='MD5:0ffb20a8802b08884753b5f4c0cb18c9')[0]

    self.delayDisplay('Finished with download and loading')

    outputSegmentation = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode")

    # Test the module logic
    logic = ImportOsirixROILogic()
    logic.importOsirixRoiFileToSegmentation(jsonTextNode, outputSegmentation)
    self.assertEqual(outputSegmentation.GetSegmentation().GetNumberOfSegments(), 1)
    self.assertEqual(outputSegmentation.GetClosedSurfaceInternalRepresentation("Test").GetNumberOfPoints(), 2935)

    self.delayDisplay('Test passed')
