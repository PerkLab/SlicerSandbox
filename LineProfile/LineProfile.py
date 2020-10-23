import os
import unittest
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
import logging

#
# LineProfile
#

class LineProfile(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Line Profile"
    self.parent.categories = ["Quantification"]
    self.parent.dependencies = []
    parent.contributors = ["Andras Lasso (PerkLab)"]
    self.parent.helpText = """
This module computes intensity profile of a volume along a line line.
"""
    self.parent.helpText += self.getDefaultModuleDocumentationLink()
    self.parent.acknowledgementText = """
This file was originally developed by Andras Lasso (PerkLab)  and was partially funded by CCO ACRU.
""" # replace with organization, grant and thanks.

#
# LineProfileWidget
#

class LineProfileWidget(ScriptedLoadableModuleWidget):
  """Uses ScriptedLoadableModuleWidget base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def setup(self):
    ScriptedLoadableModuleWidget.setup(self)

    self.logic = LineProfileLogic()

    # Instantiate and connect widgets ...

    #
    # Parameters Area
    #
    parametersCollapsibleButton = ctk.ctkCollapsibleButton()
    parametersCollapsibleButton.text = "Parameters"
    self.layout.addWidget(parametersCollapsibleButton)

    # Layout within the dummy collapsible button
    parametersFormLayout = qt.QFormLayout(parametersCollapsibleButton)

    #
    # input volume selector
    #
    self.inputVolumeSelector = slicer.qMRMLNodeComboBox()
    self.inputVolumeSelector.nodeTypes = ["vtkMRMLScalarVolumeNode"]
    self.inputVolumeSelector.selectNodeUponCreation = True
    self.inputVolumeSelector.addEnabled = False
    self.inputVolumeSelector.removeEnabled = False
    self.inputVolumeSelector.noneEnabled = False
    self.inputVolumeSelector.showHidden = False
    self.inputVolumeSelector.setMRMLScene(slicer.mrmlScene)
    self.inputVolumeSelector.setToolTip("Pick the input to the algorithm which will be sampled along the line.")
    parametersFormLayout.addRow("Input Volume: ", self.inputVolumeSelector)

    #
    # input line selector
    #
    self.inputLineWidget = slicer.qSlicerSimpleMarkupsWidget()
    self.inputLineSelector = self.inputLineWidget.markupsSelectorComboBox()
    self.inputLineSelector.nodeTypes = ["vtkMRMLMarkupsLineNode", "vtkMRMLMarkupsCurveNode"]
    self.inputLineSelector.selectNodeUponCreation = True
    self.inputLineSelector.addEnabled = True
    self.inputLineSelector.removeEnabled = True
    self.inputLineSelector.noneEnabled = False
    self.inputLineSelector.showHidden = False
    self.inputLineWidget.tableWidget().setVisible(False)
    self.inputLineWidget.setDefaultNodeColor(qt.QColor().fromRgbF(1,1,0))
    self.inputLineWidget.setMRMLScene( slicer.mrmlScene )
    self.inputLineWidget.setToolTip("Pick line or curve to take image samples along.")
    parametersFormLayout.addRow("Input line: ", self.inputLineWidget)

    #
    # output table selector
    #
    self.outputTableSelector = slicer.qMRMLNodeComboBox()
    self.outputTableSelector.nodeTypes = ["vtkMRMLTableNode"]
    self.outputTableSelector.addEnabled = True
    self.outputTableSelector.renameEnabled = True
    self.outputTableSelector.removeEnabled = True
    self.outputTableSelector.noneEnabled = True
    self.outputTableSelector.showHidden = False
    self.outputTableSelector.setMRMLScene( slicer.mrmlScene )
    self.outputTableSelector.setToolTip( "Pick the output table to the algorithm." )
    parametersFormLayout.addRow("Output table: ", self.outputTableSelector)

    #
    # output plot selector
    #
    self.outputPlotSeriesSelector = slicer.qMRMLNodeComboBox()
    self.outputPlotSeriesSelector.nodeTypes = ["vtkMRMLPlotSeriesNode"]
    self.outputPlotSeriesSelector.addEnabled = True
    self.outputPlotSeriesSelector.renameEnabled = True
    self.outputPlotSeriesSelector.removeEnabled = True
    self.outputPlotSeriesSelector.noneEnabled = True
    self.outputPlotSeriesSelector.showHidden = False
    self.outputPlotSeriesSelector.setMRMLScene( slicer.mrmlScene )
    self.outputPlotSeriesSelector.setToolTip( "Pick the output plot series to the algorithm." )
    parametersFormLayout.addRow("Output plot series: ", self.outputPlotSeriesSelector)

    #
    # line resolution
    #
    self.lineResolutionSliderWidget = ctk.ctkSliderWidget()
    self.lineResolutionSliderWidget.singleStep = 1
    self.lineResolutionSliderWidget.minimum = 2
    self.lineResolutionSliderWidget.maximum = 1000
    self.lineResolutionSliderWidget.value = 100
    self.lineResolutionSliderWidget.decimals = 0
    self.lineResolutionSliderWidget.setToolTip("Number of points to sample along the line.")
    parametersFormLayout.addRow("Line resolution", self.lineResolutionSliderWidget)

    #
    # Apply Button
    #
    self.applyButton = ctk.ctkCheckablePushButton()
    self.applyButton.text = "Compute intensity profile"
    self.applyButton.toolTip = "Run the algorithm."
    self.applyButton.enabled = False
    self.applyButton.checkable = False
    parametersFormLayout.addRow(self.applyButton)

    # connections
    self.applyButton.connect('clicked(bool)', self.onApplyButton)
    self.applyButton.connect('checkBoxToggled(bool)', self.onApplyButtonToggled)
    self.inputVolumeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelectNode)
    self.inputLineSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelectNode)
    self.outputPlotSeriesSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelectNode)
    self.outputTableSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelectNode)
    self.lineResolutionSliderWidget.connect("valueChanged(double)", self.onSetLineResolution)

    # Add vertical spacer
    self.layout.addStretch(1)

    # Refresh Apply button state
    self.onSelectNode()

  def cleanup(self):
    self.logic.setEnableAutoUpdate(False)

  def onSelectNode(self):
    self.applyButton.enabled = self.inputVolumeSelector.currentNode() and self.inputLineSelector.currentNode()
    self.logic.setInputVolumeNode(self.inputVolumeSelector.currentNode())
    self.logic.setInputLineNode(self.inputLineSelector.currentNode())
    self.logic.setOutputTableNode(self.outputTableSelector.currentNode())
    self.logic.setOutputPlotSeriesNode(self.outputPlotSeriesSelector.currentNode())

  def onSetLineResolution(self, resolution):
    lineResolution = int(self.lineResolutionSliderWidget.value)
    self.logic.lineResolution = lineResolution

  def createOutputNodes(self):
    if not self.outputTableSelector.currentNode():
      outputTableNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLTableNode")
      self.outputTableSelector.setCurrentNode(outputTableNode)
    if not self.outputPlotSeriesSelector.currentNode():
      outputPlotSeriesNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLPlotSeriesNode")
      self.outputPlotSeriesSelector.setCurrentNode(outputPlotSeriesNode)

  def onApplyButton(self):
    self.createOutputNodes()
    self.logic.update()

  def onApplyButtonToggled(self, toggle):
    if toggle:
      self.createOutputNodes()
    self.logic.setEnableAutoUpdate(toggle)

#
# LineProfileLogic
#

class LineProfileLogic(ScriptedLoadableModuleLogic):
  """This class should implement all the actual
  computation done by your module.  The interface
  should be such that other python code can import
  this class and make use of the functionality without
  requiring an instance of the Widget.
  Uses ScriptedLoadableModuleLogic base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self):
    self.inputVolumeNode = None
    self.inputLineNode = None
    self.lineObservation = None # pair of line object and observation ID
    self.lineResolution = 100
    self.outputPlotSeriesNode = None
    self.outputTableNode = None
    self.plotChartNode = None

  def __del__(self):
    self.setEnableAutoUpdate(False)

  def setInputVolumeNode(self, volumeNode):
    if self.inputVolumeNode == volumeNode:
      return
    self.inputVolumeNode = volumeNode
    if self.getEnableAutoUpdate():
      self.update()

  def setInputLineNode(self, lineNode):
    if self.inputLineNode == lineNode:
      return
    self.inputLineNode = lineNode
    if self.getEnableAutoUpdate():
      self.setEnableAutoUpdate(False) # remove old observers
      self.setEnableAutoUpdate(True) # add new observers
      self.update()

  def setOutputTableNode(self, tableNode):
    if self.outputTableNode == tableNode:
      return
    self.outputTableNode = tableNode
    if self.getEnableAutoUpdate():
      self.update()

  def setOutputPlotSeriesNode(self, plotSeriesNode):
    if self.outputPlotSeriesNode == plotSeriesNode:
      return
    self.outputPlotSeriesNode = plotSeriesNode
    if self.getEnableAutoUpdate():
      self.update()

  def update(self):
    self.updateOutputTable(self.inputVolumeNode, self.inputLineNode, self.outputTableNode, self.lineResolution)
    self.updatePlot(self.outputPlotSeriesNode, self.outputTableNode, self.inputVolumeNode.GetName())
    self.showPlot()

  def getEnableAutoUpdate(self):
    return self.lineObservation is not None

  def setEnableAutoUpdate(self, toggle):
    if self.lineObservation:
      self.lineObservation[0].RemoveObserver(self.lineObservation[1])
      self.lineObservation = None
    if toggle and (self.inputLineNode is not None):
      self.lineObservation = [self.inputLineNode,
        self.inputLineNode.AddObserver(slicer.vtkMRMLMarkupsNode.PointModifiedEvent, self.onLineModified)]

  def onLineModified(self, caller=None, event=None):
    self.update()

  def getArrayFromTable(self, outputTable, arrayName):
    if outputTable is None:
      return None;
    distanceArray = outputTable.GetTable().GetColumnByName(arrayName)
    if distanceArray:
      return distanceArray
    newArray = vtk.vtkDoubleArray()
    newArray.SetName(arrayName)
    outputTable.GetTable().AddColumn(newArray)
    return newArray

  def updateOutputTable(self, inputVolume, inputCurve, outputTable, lineResolution):
    if inputCurve.GetNumberOfDefinedControlPoints() < 2:
      outputTable.GetTable().SetNumberOfRows(0)
      return

    curvePoints_RAS = inputCurve.GetCurvePointsWorld()
    closedCurve = inputCurve.IsA('vtkMRMLClosedCurveNode')
    curveLengthMm = slicer.vtkMRMLMarkupsCurveNode.GetCurveLength(curvePoints_RAS, closedCurve)

    # Need to get the start/end point of the line in the IJK coordinate system
    # as VTK filters cannot take into account direction cosines
    # We transform the curve points from RAS coordinate system (instead of directly from the inputCurve coordinate system)
    # to make sure the curve is transformed to RAS exactly the same way as it is done for display.
    inputVolumeToIJK = vtk.vtkMatrix4x4()
    inputVolume.GetRASToIJKMatrix(inputVolumeToIJK)
    rasToInputVolumeTransform = vtk.vtkGeneralTransform()
    slicer.vtkMRMLTransformNode.GetTransformBetweenNodes(None, inputVolume.GetParentTransformNode(), rasToInputVolumeTransform)
    rasToIJKTransform = vtk.vtkGeneralTransform()  # rasToIJKTransform = inputVolumeToIJK * rasToInputVolumeTransform
    rasToIJKTransform.Concatenate(inputVolumeToIJK)
    rasToIJKTransform.Concatenate(rasToInputVolumeTransform)

    curvePoly_RAS = vtk.vtkPolyData()
    curvePoly_RAS.SetPoints(curvePoints_RAS)

    transformRasToIjk = vtk.vtkTransformPolyDataFilter()
    transformRasToIjk.SetInputData(curvePoly_RAS)
    transformRasToIjk.SetTransform(rasToIJKTransform)
    transformRasToIjk.Update()
    curvePoly_IJK = transformRasToIjk.GetOutput()
    curvePoints_IJK = curvePoly_IJK.GetPoints()

    if curvePoints_IJK.GetNumberOfPoints() < 2:
      # We checked before that there are at least two control points, so it should not happen
      raise ValueError()

    startPointIndex = 0
    endPointIndex = curvePoints_IJK.GetNumberOfPoints() - 1
    lineStartPoint_IJK = curvePoints_IJK.GetPoint(startPointIndex)
    lineEndPoint_IJK = curvePoints_IJK.GetPoint(endPointIndex)

    # Special case: single-slice volume
    # vtkProbeFilter treats vtkImageData as a general data set and it considers its bounds to end
    # in the middle of edge voxels. This makes single-slice volumes to have zero thickness, which
    # can be easily missed by a line that that is drawn on the plane (e.g., they happen to be
    # extremely on the same side of the plane, very slightly off, due to runding errors).
    # We move the start/end points very close to the plane and force them to be on opposite sides of the plane.
    dims = inputVolume.GetImageData().GetDimensions()
    for axisIndex in range(3):
      if dims[axisIndex] == 1:
        if abs(lineStartPoint_IJK[axisIndex]) < 0.5 and abs(lineEndPoint_IJK[axisIndex]) < 0.5:
          # both points are inside the volume plane
          # keep their distance the same (to keep the overall length of the line he same)
          # but make sure the points are on the opposite side of the plane (to ensure probe filter
          # considers the line crossing the image plane)
          pointDistance = max(abs(lineStartPoint_IJK[axisIndex]-lineEndPoint_IJK[axisIndex]), 1e-6)
          lineStartPoint_IJK[axisIndex] = -0.5 * pointDistance
          lineEndPoint_IJK[axisIndex] = 0.5 * pointDistance
          curvePoints_IJK.SetPoint(startPointIndex, lineStartPoint_IJK)
          curvePoints_IJK.SetPoint(endPointIndex, lineEndPoint_IJK)

    sampledCurvePoints_IJK = vtk.vtkPoints()
    samplingDistance = curveLengthMm / lineResolution
    slicer.vtkMRMLMarkupsCurveNode.ResamplePoints(curvePoints_IJK, sampledCurvePoints_IJK, samplingDistance, closedCurve)

    sampledCurvePoly_IJK = vtk.vtkPolyData()
    sampledCurvePoly_IJK.SetPoints(sampledCurvePoints_IJK)

    probeFilter=vtk.vtkProbeFilter()
    probeFilter.SetInputData(sampledCurvePoly_IJK)
    probeFilter.SetSourceData(inputVolume.GetImageData())
    probeFilter.ComputeToleranceOff()
    probeFilter.Update()

    probedPoints=probeFilter.GetOutput()

    # Create arrays of data
    distanceArray = self.getArrayFromTable(outputTable, DISTANCE_ARRAY_NAME)
    intensityArray = self.getArrayFromTable(outputTable, INTENSITY_ARRAY_NAME)
    outputTable.GetTable().SetNumberOfRows(probedPoints.GetNumberOfPoints())
    x = range(0, probedPoints.GetNumberOfPoints())
    xStep = curveLengthMm/(probedPoints.GetNumberOfPoints()-1)
    probedPointScalars = probedPoints.GetPointData().GetScalars()
    for i in range(len(x)):
      distanceArray.SetValue(i, x[i]*xStep)
      intensityArray.SetValue(i, probedPointScalars.GetTuple(i)[0])
    distanceArray.Modified()
    intensityArray.Modified()
    outputTable.GetTable().Modified()

  def updatePlot(self, outputPlotSeries, outputTable, name=None):

    # Create plot
    if name:
      outputPlotSeries.SetName(name)
    outputPlotSeries.SetAndObserveTableNodeID(outputTable.GetID())
    outputPlotSeries.SetXColumnName(DISTANCE_ARRAY_NAME)
    outputPlotSeries.SetYColumnName(INTENSITY_ARRAY_NAME)
    outputPlotSeries.SetPlotType(slicer.vtkMRMLPlotSeriesNode.PlotTypeScatter)
    outputPlotSeries.SetMarkerStyle(slicer.vtkMRMLPlotSeriesNode.MarkerStyleNone)
    outputPlotSeries.SetColor(0, 0.6, 1.0)

  def showPlot(self):

    # Create chart and add plot
    if not self.plotChartNode:
      plotChartNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLPlotChartNode")
      self.plotChartNode = plotChartNode
      self.plotChartNode.SetXAxisTitle(DISTANCE_ARRAY_NAME+" (mm)")
      self.plotChartNode.SetYAxisTitle(INTENSITY_ARRAY_NAME)
      self.plotChartNode.AddAndObservePlotSeriesNodeID(self.outputPlotSeriesNode.GetID())

    # Show plot in layout
    slicer.modules.plots.logic().ShowChartInLayout(self.plotChartNode)
    slicer.app.layoutManager().plotWidget(0).plotView().fitToContent()


class LineProfileTest(ScriptedLoadableModuleTest):
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
    self.test_LineProfile1()

  def test_LineProfile1(self):
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
    #
    # first, get some data
    #
    import SampleData
    sampleDataLogic = SampleData.SampleDataLogic()
    volumeNode = sampleDataLogic.downloadMRHead()

    logic = LineProfileLogic()

    self.delayDisplay('Test passed!')

DISTANCE_ARRAY_NAME = "Distance"
INTENSITY_ARRAY_NAME = "Intensity"
