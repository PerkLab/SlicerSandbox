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
This module computes intensity profile of a volume along a ruler line.
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
    # input ruler selector
    #
    self.inputRulerSelector = slicer.qMRMLNodeComboBox()
    self.inputRulerSelector.nodeTypes = ["vtkMRMLAnnotationRulerNode"]
    self.inputRulerSelector.selectNodeUponCreation = True
    self.inputRulerSelector.addEnabled = False
    self.inputRulerSelector.removeEnabled = False
    self.inputRulerSelector.noneEnabled = False
    self.inputRulerSelector.showHidden = False
    self.inputRulerSelector.setMRMLScene( slicer.mrmlScene )
    self.inputRulerSelector.setToolTip("Pick the ruler that defines the sampling line.")
    parametersFormLayout.addRow("Input ruler: ", self.inputRulerSelector)

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
    self.inputRulerSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelectNode)
    self.outputPlotSeriesSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelectNode)
    self.outputTableSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelectNode)
    self.lineResolutionSliderWidget.connect("valueChanged(double)", self.onSetLineResolution)

    # Add vertical spacer
    self.layout.addStretch(1)

    # Refresh Apply button state
    self.onSelectNode()

  def cleanup(self):
    pass

  def onSelectNode(self):
    self.applyButton.enabled = self.inputVolumeSelector.currentNode() and self.inputRulerSelector.currentNode()
    self.logic.inputVolumeNode = self.inputVolumeSelector.currentNode()
    self.logic.inputRulerNode = self.inputRulerSelector.currentNode()
    self.logic.outputTableNode = self.outputTableSelector.currentNode()
    self.logic.outputPlotSeriesNode = self.outputPlotSeriesSelector.currentNode()

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
    self.logic.enableAutoUpdate(toggle)

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
    self.inputRulerNode = None
    self.rulerObservation = None # pair of ruler object and observation ID
    self.lineResolution = 100
    self.outputPlotSeriesNode = None
    self.outputTableNode = None
    self.plotChartNode = None

  def __del__(self):
    self.enableAutoUpdate(False)

  def update(self):
    self.updateOutputTable(self.inputVolumeNode, self.inputRulerNode, self.outputTableNode, self.lineResolution)
    self.updatePlot(self.outputPlotSeriesNode, self.outputTableNode, self.inputVolumeNode.GetName())
    self.showPlot()

  def enableAutoUpdate(self, toggle):
    if self.rulerObservation:
      self.rulerObservation[0].RemoveObserver(self.rulerObservation[1])
      self.rulerObservation = None
    if toggle and (self.inputRulerNode is not None):
      self.rulerObservation = [self.inputRulerNode, self.inputRulerNode.AddObserver(vtk.vtkCommand.ModifiedEvent, self.onRulerModified)]

  def onRulerModified(self, caller=None, event=None):
    self.update()

  def getArrayFromTable(self, outputTable, arrayName):
    distanceArray = outputTable.GetTable().GetColumnByName(arrayName)
    if distanceArray:
      return distanceArray
    newArray = vtk.vtkDoubleArray()
    newArray.SetName(arrayName)
    outputTable.GetTable().AddColumn(newArray)
    return newArray

  def updateOutputTable(self, inputVolume, inputRuler, outputTable, lineResolution):
    import math

    rulerStartPoint_Ruler = [0,0,0]
    rulerEndPoint_Ruler = [0,0,0]
    inputRuler.GetPosition1(rulerStartPoint_Ruler)
    inputRuler.GetPosition2(rulerEndPoint_Ruler)
    rulerStartPoint_Ruler1 = [rulerStartPoint_Ruler[0], rulerStartPoint_Ruler[1], rulerStartPoint_Ruler[2], 1.0]
    rulerEndPoint_Ruler1 = [rulerEndPoint_Ruler[0], rulerEndPoint_Ruler[1], rulerEndPoint_Ruler[2], 1.0]

    rulerToRAS = vtk.vtkMatrix4x4()
    rulerTransformNode = inputRuler.GetParentTransformNode()
    if rulerTransformNode:
      if rulerTransformNode.IsTransformToWorldLinear():
        rulerToRAS.DeepCopy(rulerTransformNode.GetMatrixTransformToParent())
      else:
        logging.warning("Cannot handle non-linear transforms - ignoring transform of the input ruler")

    rulerStartPoint_RAS1 = [0,0,0,1]
    rulerEndPoint_RAS1 = [0,0,0,1]
    rulerToRAS.MultiplyPoint(rulerStartPoint_Ruler1,rulerStartPoint_RAS1)
    rulerToRAS.MultiplyPoint(rulerEndPoint_Ruler1,rulerEndPoint_RAS1)

    rulerLengthMm=math.sqrt(vtk.vtkMath.Distance2BetweenPoints(rulerStartPoint_RAS1[0:3],rulerEndPoint_RAS1[0:3]))

    # Need to get the start/end point of the line in the IJK coordinate system
    # as VTK filters cannot take into account direction cosines
    rasToIJK = vtk.vtkMatrix4x4()
    parentToIJK = vtk.vtkMatrix4x4()
    rasToParent = vtk.vtkMatrix4x4()
    inputVolume.GetRASToIJKMatrix(parentToIJK)
    transformNode = inputVolume.GetParentTransformNode()
    if transformNode:
      if transformNode.IsTransformToWorldLinear():
        rasToParent.DeepCopy(transformNode.GetMatrixTransformToParent())
        rasToParent.Invert()
      else:
        print ("Cannot handle non-linear transforms - ignoring transform of the input volume")
    vtk.vtkMatrix4x4.Multiply4x4(parentToIJK, rasToParent, rasToIJK)

    rulerStartPoint_IJK1 = [0,0,0,1]
    rulerEndPoint_IJK1 = [0,0,0,1]
    rasToIJK.MultiplyPoint(rulerStartPoint_RAS1,rulerStartPoint_IJK1)
    rasToIJK.MultiplyPoint(rulerEndPoint_RAS1,rulerEndPoint_IJK1)

    lineSource=vtk.vtkLineSource()
    lineSource.SetPoint1(rulerStartPoint_IJK1[0],rulerStartPoint_IJK1[1],rulerStartPoint_IJK1[2])
    lineSource.SetPoint2(rulerEndPoint_IJK1[0], rulerEndPoint_IJK1[1], rulerEndPoint_IJK1[2])
    lineSource.SetResolution(lineResolution-1)

    probeFilter=vtk.vtkProbeFilter()
    probeFilter.SetInputConnection(lineSource.GetOutputPort())
    probeFilter.SetSourceData(inputVolume.GetImageData())
    probeFilter.Update()

    probedPoints=probeFilter.GetOutput()

    # Create arrays of data
    distanceArray = self.getArrayFromTable(outputTable, DISTANCE_ARRAY_NAME)
    intensityArray = self.getArrayFromTable(outputTable, INTENSITY_ARRAY_NAME)
    outputTable.GetTable().SetNumberOfRows(probedPoints.GetNumberOfPoints())
    x = range(0, probedPoints.GetNumberOfPoints())
    xStep = rulerLengthMm/(probedPoints.GetNumberOfPoints()-1)
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
