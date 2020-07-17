import os
import unittest
import logging
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

#
# SegmentCrossSectionArea
#

class SegmentCrossSectionArea(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Segment Cross-Section Area"
    self.parent.categories = ["Quantification"]
    self.parent.dependencies = []
    self.parent.contributors = ["Hollister Herhold (AMNH)", "Andras Lasso (PerkLab)"]
    self.parent.helpText = """This module computes cross-section of segments (created by Segment Editor module) and displays them in a plot.
Write to <a href="https://discourse.slicer.org">Slicer forum</a> if you need help using this module
"""
    self.parent.acknowledgementText = """
This file was originally developed by Hollister Herhold and Andras Lasso.
"""

#
# SegmentCrossSectionAreaWidget
#

class SegmentCrossSectionAreaWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
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
    uiWidget = slicer.util.loadUI(self.resourcePath('UI/SegmentCrossSectionArea.ui'))
    self.layout.addWidget(uiWidget)
    self.ui = slicer.util.childWidgetVariables(uiWidget)

    # Set scene in MRML widgets. Make sure that in Qt designer
    # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget'rowCount.
    # "setMRMLScene(vtkMRMLScene*)" slot.
    uiWidget.setMRMLScene(slicer.mrmlScene)

    # Create a new parameterNode
    # This parameterNode stores all user choices in parameter values, node selections, etc.
    # so that when the scene is saved and reloaded, these settings are restored.
    self.logic = SegmentCrossSectionAreaLogic()
    self.ui.parameterNodeSelector.addAttribute("vtkMRMLScriptedModuleNode", "ModuleName", self.moduleName)
    self.setParameterNode(self.logic.getParameterNode())

    # Connections
    self.ui.parameterNodeSelector.connect('currentNodeChanged(vtkMRMLNode*)', self.setParameterNode)
    self.ui.applyButton.connect('clicked(bool)', self.onApplyButton)
    self.ui.showTablePushButton.connect('clicked(bool)', self.onShowTableButton)
    self.ui.showChartPushButton.connect('clicked(bool)', self.onShowChartButton)

    # These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
    # (in the selected parameter node).
    self.ui.segmentationSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
    self.ui.volumeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
    self.ui.axisSelectorBox.connect("currentIndexChanged(int)", self.updateParameterNodeFromGUI)
    self.ui.tableSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
    self.ui.chartSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)

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
      # TODO: uncomment this when nodeFromIndex method will be available in Python
      # # Select first segmentation node by default
      # if not inputParameterNode.GetNodeReference("Segmentation"):
      #   segmentationNode = self.ui.segmentationSelector.nodeFromIndex(0)
      #   if segmentationNode:
      #     inputParameterNode.SetNodeReferenceID(segmentationNode.GetID())

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

    wasBlocked = self.ui.segmentationSelector.blockSignals(True)
    self.ui.segmentationSelector.setCurrentNode(self._parameterNode.GetNodeReference("Segmentation"))
    self.ui.segmentationSelector.blockSignals(wasBlocked)

    wasBlocked = self.ui.volumeSelector.blockSignals(True)
    self.ui.volumeSelector.setCurrentNode(self._parameterNode.GetNodeReference("Volume"))
    self.ui.volumeSelector.blockSignals(wasBlocked)

    wasBlocked = self.ui.axisSelectorBox.blockSignals(True)
    self.ui.axisSelectorBox.currentText = self._parameterNode.GetParameter("Axis")
    self.ui.axisSelectorBox.blockSignals(wasBlocked)

    wasBlocked = self.ui.tableSelector.blockSignals(True)
    self.ui.tableSelector.setCurrentNode(self._parameterNode.GetNodeReference("ResultsTable"))
    self.ui.tableSelector.blockSignals(wasBlocked)

    wasBlocked = self.ui.axisSelectorBox.blockSignals(True)
    self.ui.chartSelector.setCurrentNode(self._parameterNode.GetNodeReference("ResultsChart"))
    self.ui.axisSelectorBox.blockSignals(wasBlocked)

    # Update buttons states and tooltips
    if self._parameterNode.GetNodeReference("Segmentation"):
      self.ui.applyButton.toolTip = "Compute cross sections"
      self.ui.applyButton.enabled = True
    else:
      self.ui.applyButton.toolTip = "Select input segmentation node"
      self.ui.applyButton.enabled = False

  def updateParameterNodeFromGUI(self, caller=None, event=None):
    """
    This method is called when the user makes any change in the GUI.
    The changes are saved into the parameter node (so that they are restored when the scene is saved and loaded).
    """

    if self._parameterNode is None:
      return

    self._parameterNode.SetNodeReferenceID("Segmentation", self.ui.segmentationSelector.currentNodeID)
    self._parameterNode.SetNodeReferenceID("Volume", self.ui.volumeSelector.currentNodeID)
    self._parameterNode.SetParameter("Axis", self.ui.axisSelectorBox.currentText)

    self._parameterNode.SetNodeReferenceID("ResultsTable", self.ui.tableSelector.currentNodeID)
    self._parameterNode.SetNodeReferenceID("ResultsChart", self.ui.chartSelector.currentNodeID)

  def onApplyButton(self):
    """
    Run processing when user clicks "Apply" button.
    """
    try:

      # Create nodes for results
      tableNode = self.ui.tableSelector.currentNode()
      if not tableNode:
        tableNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLTableNode", "Segment cross-section area table")
        self.ui.tableSelector.setCurrentNode(tableNode)
      plotChartNode = self.ui.chartSelector.currentNode()
      if not plotChartNode:
        plotChartNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLPlotChartNode", "Segment cross-section area plot")
        self.ui.chartSelector.setCurrentNode(plotChartNode)

      self.logic.run(self.ui.segmentationSelector.currentNode(), self.ui.volumeSelector.currentNode(), self.ui.axisSelectorBox.currentText,
                     tableNode, plotChartNode)

      self.logic.showChart(plotChartNode)

    except Exception as e:
      slicer.util.errorDisplay("Failed to compute results: "+str(e))
      import traceback
      traceback.print_exc()

  def onShowTableButton(self):
    tableNode = self.ui.tableSelector.currentNode()
    if not tableNode:
      self.onApplyButton()
    tableNode = self.ui.tableSelector.currentNode()
    if tableNode:
      self.logic.showTable(tableNode)

  def onShowChartButton(self):
    plotChartNode = self.ui.chartSelector.currentNode()
    if not plotChartNode:
      self.onApplyButton()
    plotChartNode = self.ui.chartSelector.currentNode()
    if plotChartNode:
      self.logic.showChart(plotChartNode)

#
# SegmentCrossSectionAreaLogic
#

class SegmentCrossSectionAreaLogic(ScriptedLoadableModuleLogic):
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
    if not parameterNode.GetParameter("Axis"):
      parameterNode.SetParameter("Axis", "slice")

  def run(self, segmentationNode, volumeNode, axis, tableNode, plotChartNode):
    """
    Run the processing algorithm.
    Can be used without GUI widget.
    :param segmentationNode: cross section area will be computed on this
    :param volumeNode: optional reference volume (to determine slice positions and directions)
    :param axis: axis index to compute cross section areas along
    :param tableNode: result table node
    :param plotChartNode: result chart node
    """

    import numpy as np

    logging.info('Processing started')

    if not segmentationNode:
      raise ValueError("Segmentation node is invalid")
    
    # Get visible segment ID list.
    # Get segment ID list
    visibleSegmentIds = vtk.vtkStringArray()
    segmentationNode.GetDisplayNode().GetVisibleSegmentIDs(visibleSegmentIds)
    if visibleSegmentIds.GetNumberOfValues() == 0:
      raise ValueError("SliceAreaPlot will not return any results: there are no visible segments")

    if axis=="row":
      axisIndex = 0
    elif axis=="column":
      axisIndex = 1
    elif axis=="slice":
      axisIndex = 2
    else:
      raise ValueError("Invalid axis name: "+axis)

    #
    # Make a table and set the first column as the slice number. This is used
    # as the X axis for plots.
    #
    tableNode.RemoveAllColumns()
    table = tableNode.GetTable()

    # Make a plot chart node. Plot series nodes will be added to this in the
    # loop below that iterates over each segment.
    plotChartNode.SetTitle('Segment cross-section area ('+axis+')')
    plotChartNode.SetXAxisTitle(axis +" index")
    plotChartNode.SetYAxisTitle('Area in mm^2')  # TODO: use length unit

    #
    # For each segment, get the area and put it in the table in a new column.
    #
    try:
      # Create temporary volume node
      tempSegmentLabelmapVolumeNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLLabelMapVolumeNode', "SegmentCrossSectionAreaTemp")

      for segmentIndex in range(visibleSegmentIds.GetNumberOfValues()):
        segmentID = visibleSegmentIds.GetValue(segmentIndex)

        segmentList = vtk.vtkStringArray()
        segmentList.InsertNextValue(segmentID)
        if not slicer.modules.segmentations.logic().ExportSegmentsToLabelmapNode(segmentationNode, segmentList, tempSegmentLabelmapVolumeNode, volumeNode):
          continue

        if segmentIndex == 0:

          volumeExtents = tempSegmentLabelmapVolumeNode.GetImageData().GetExtent()
          numSlices = volumeExtents[axisIndex*2+1] - volumeExtents[axisIndex*2] + 1
          
          startPosition_Ijk = [
            (volumeExtents[0]+volumeExtents[1])/2.0 if axisIndex!=0 else volumeExtents[0],
            (volumeExtents[2]+volumeExtents[3])/2.0 if axisIndex!=1 else volumeExtents[2],
            (volumeExtents[4]+volumeExtents[5])/2.0 if axisIndex!=2 else volumeExtents[4],
            1
          ]
          endPosition_Ijk = [
            (volumeExtents[0]+volumeExtents[1])/2.0 if axisIndex!=0 else volumeExtents[1],
            (volumeExtents[2]+volumeExtents[3])/2.0 if axisIndex!=1 else volumeExtents[3],
            (volumeExtents[4]+volumeExtents[5])/2.0 if axisIndex!=2 else volumeExtents[5],
            1
          ]
          # Get physical coordinates from voxel coordinates
          volumeIjkToRas = vtk.vtkMatrix4x4()
          tempSegmentLabelmapVolumeNode.GetIJKToRASMatrix(volumeIjkToRas)
          startPosition_Ras = np.array([0.0,0.0,0.0,1.0])
          volumeIjkToRas.MultiplyPoint(startPosition_Ijk, startPosition_Ras)
          endPosition_Ras = np.array([0.0,0.0,0.0,1.0])
          volumeIjkToRas.MultiplyPoint(endPosition_Ijk, endPosition_Ras)
          volumePositionIncrement_Ras = np.array([0,0,0,1])
          if numSlices > 1:
            volumePositionIncrement_Ras = (endPosition_Ras - startPosition_Ras) / (numSlices - 1.0)

          # If volume node is transformed, apply that transform to get volume's RAS coordinates
          transformVolumeRasToRas = vtk.vtkGeneralTransform()
          slicer.vtkMRMLTransformNode.GetTransformBetweenNodes(tempSegmentLabelmapVolumeNode.GetParentTransformNode(), None, transformVolumeRasToRas)

          sliceNumberArray = vtk.vtkIntArray()
          sliceNumberArray.SetName("Index")
          slicePositionArray = vtk.vtkFloatArray()
          slicePositionArray.SetNumberOfComponents(3)
          slicePositionArray.SetComponentName(0, "R")
          slicePositionArray.SetComponentName(1, "A")
          slicePositionArray.SetComponentName(2, "S")
          slicePositionArray.SetName("Position")

          for i in range(numSlices):
            sliceNumberArray.InsertNextValue(i)
            point_VolumeRas = startPosition_Ras + i * volumePositionIncrement_Ras
            point_Ras = transformVolumeRasToRas.TransformPoint(point_VolumeRas[0:3])
            slicePositionArray.InsertNextTuple3(*point_Ras)

          table.AddColumn(sliceNumberArray)
          tableNode.SetColumnDescription(sliceNumberArray.GetName(), "Index of " + axis)
          tableNode.SetColumnUnitLabel(sliceNumberArray.GetName(), "voxel")

          table.AddColumn(slicePositionArray)
          tableNode.SetColumnDescription(slicePositionArray.GetName(), "RAS position of slice center")
          tableNode.SetColumnUnitLabel(slicePositionArray.GetName(), "mm")  # TODO: use length unit

        narray = slicer.util.arrayFromVolume(tempSegmentLabelmapVolumeNode)

        areaArray = vtk.vtkFloatArray()
        segmentName = segmentationNode.GetSegmentation().GetSegment(segmentID).GetName()
        areaArray.SetName(segmentName)

        # Convert number of voxels to area in mm2
        spacing = tempSegmentLabelmapVolumeNode.GetSpacing()
        areaOfPixelMm2 = spacing[0] * spacing[1] * spacing[2] / spacing[axisIndex]

        # Count number of >0 voxels for each slice
        for i in range(numSlices):
          if axisIndex == 0:
            areaBySliceInVoxels = np.count_nonzero(narray[:,:,i])
          elif axisIndex == 1:
            areaBySliceInVoxels = np.count_nonzero(narray[:, i, :])
          elif axisIndex == 2:
            areaBySliceInVoxels = np.count_nonzero(narray[i, :, :])
          areaBySliceInMm2 = areaBySliceInVoxels * areaOfPixelMm2
          areaArray.InsertNextValue(areaBySliceInMm2)

        tableNode.AddColumn(areaArray)
        tableNode.SetColumnUnitLabel(areaArray.GetName(), "mm2")  # TODO: use length unit
        tableNode.SetColumnDescription(areaArray.GetName(), "Cross-section area")

        # Make a plot series node for this column.
        plotSeriesNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLPlotSeriesNode", segmentName)
        plotSeriesNode.SetAndObserveTableNodeID(tableNode.GetID())
        plotSeriesNode.SetXColumnName("Index")
        plotSeriesNode.SetYColumnName(segmentName)
        plotSeriesNode.SetUniqueColor()

        # Add this series to the plot chart node created above.
        plotChartNode.AddAndObservePlotSeriesNodeID(plotSeriesNode.GetID())

    finally:
      # Remove temporary volume node
      colorNode = tempSegmentLabelmapVolumeNode.GetDisplayNode().GetColorNode()
      if colorNode:
        slicer.mrmlScene.RemoveNode(colorNode)
      slicer.mrmlScene.RemoveNode(tempSegmentLabelmapVolumeNode)


    logging.info('Processing completed')

  def showChart(self, plotChartNode):
    # Choose a layout where plots are visible
    layoutManager = slicer.app.layoutManager()
    layoutWithPlot = slicer.modules.plots.logic().GetLayoutWithPlot(layoutManager.layout)
    layoutManager.setLayout(layoutWithPlot)
    # Select chart in plot view
    plotWidget = layoutManager.plotWidget(0)
    plotViewNode = plotWidget.mrmlPlotViewNode()
    plotViewNode.SetPlotChartNodeID(plotChartNode.GetID())

  def showTable(self, tableNode):
    # Choose a layout where plots are visible
    layoutManager = slicer.app.layoutManager()
    layoutWithPlot = slicer.modules.tables.logic().GetLayoutWithTable(layoutManager.layout)
    layoutManager.setLayout(layoutWithPlot)
    # Select chart in plot view
    tableWidget = layoutManager.tableWidget(0)
    tableWidget.tableView().setMRMLTableNode(tableNode)

#
# SegmentCrossSectionAreaTest
#

class SegmentCrossSectionAreaTest(ScriptedLoadableModuleTest):
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
    self.test_SegmentCrossSectionArea1()

  def test_SegmentCrossSectionArea1(self):
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

    # Load master volume
    import SampleData
    sampleDataLogic = SampleData.SampleDataLogic()
    masterVolumeNode = sampleDataLogic.downloadMRBrainTumor1()

    # Create segmentation
    segmentationNode = slicer.vtkMRMLSegmentationNode()
    slicer.mrmlScene.AddNode(segmentationNode)
    segmentationNode.CreateDefaultDisplayNodes()  # only needed for display
    segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(masterVolumeNode)

    # Create a sphere shaped segment
    radius = 20
    tumorSeed = vtk.vtkSphereSource()
    tumorSeed.SetCenter(-6, 30, 28)
    tumorSeed.SetRadius(radius)
    tumorSeed.SetPhiResolution(120)
    tumorSeed.SetThetaResolution(120)
    tumorSeed.Update()
    segmentId = segmentationNode.AddSegmentFromClosedSurfaceRepresentation(tumorSeed.GetOutput(), "Tumor",
                                                                           [1.0, 0.0, 0.0])

    tableNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLTableNode", "Segment cross-section area table")
    plotChartNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLPlotChartNode", "Segment cross-section area plot")

    logic = SegmentCrossSectionAreaLogic()
    logic.run(segmentationNode, masterVolumeNode, "slice", tableNode, plotChartNode)
    logic.showChart(plotChartNode)

    self.assertEqual(tableNode.GetNumberOfColumns(), 3)
    self.assertEqual(tableNode.GetNumberOfColumns(), 3)

    # Compute error
    crossSectionAreas = slicer.util.arrayFromTableColumn(tableNode, "Tumor")
    largestCrossSectionArea = crossSectionAreas.max()
    import math
    expectedlargestCrossSectionArea = radius*radius*math.pi
    logging.info("Largest cross-section area: {0:.2f}".format(largestCrossSectionArea))
    logging.info("Expected largest cross-section area: {0:.2f}".format(expectedlargestCrossSectionArea))
    errorPercent = 100.0 * abs(largestCrossSectionArea - expectedlargestCrossSectionArea) < expectedlargestCrossSectionArea
    logging.info("Largest cross-section area error: {0:.2f}%".format(errorPercent))

    # Error between expected and actual cross section is due to finite resolution of the segmentation.
    # It should not be more than a few percent. The actual error in this case is around 1%, but use 2% to account for
    # numerical differences between different platforms.
    self.assertTrue(errorPercent < 2.0)

    self.delayDisplay('Test passed')
