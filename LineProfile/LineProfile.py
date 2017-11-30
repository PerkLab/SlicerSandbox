import os
import unittest
import math
from __main__ import vtk, qt, ctk, slicer

#
# LineProfile
#

class LineProfile:
  def __init__(self, parent):
    parent.title = "Line Profile" # TODO make this more human readable by adding spaces
    parent.categories = ["Informatics"]
    parent.dependencies = []
    parent.contributors = ["Andras Lasso (PerkLab), Csaba Pinter (PerkLab)"] # replace with "Firstname Lastname (Org)"
    parent.helpText = """
    This module computes the intensity profile in an image along a line
    """
    parent.acknowledgementText = """
    This file was originally developed by Andras Lasso (PerkLab) and was partially funded by CCO ACRU.
""" # replace with organization, grant and thanks.
    self.parent = parent

#
# qLineProfileWidget
#

class LineProfileWidget:
  def __init__(self, parent = None):
    if not parent:
      self.parent = slicer.qMRMLWidget()
      self.parent.setLayout(qt.QVBoxLayout())
      self.parent.setMRMLScene(slicer.mrmlScene)
    else:
      self.parent = parent
    self.layout = self.parent.layout()
    if not parent:
      self.setup()
      self.parent.show()

  def setup(self):
    # Instantiate and connect widgets ...

    #
    # Reload and Test area
    #
    reloadCollapsibleButton = ctk.ctkCollapsibleButton()
    reloadCollapsibleButton.text = "Reload && Test"
    self.layout.addWidget(reloadCollapsibleButton)
    reloadFormLayout = qt.QFormLayout(reloadCollapsibleButton)

    # reload button
    # (use this during development, but remove it when delivering
    #  your module to users)
    self.reloadButton = qt.QPushButton("Reload")
    self.reloadButton.toolTip = "Reload this module."
    self.reloadButton.name = "LineProfile Reload"
    reloadFormLayout.addWidget(self.reloadButton)
    self.reloadButton.connect('clicked()', self.onReload)

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
    self.inputVolumeSelector.nodeTypes = ( ("vtkMRMLScalarVolumeNode"), "" )
    self.inputVolumeSelector.addAttribute( "vtkMRMLScalarVolumeNode", "LabelMap", 0 )
    self.inputVolumeSelector.selectNodeUponCreation = True
    self.inputVolumeSelector.addEnabled = False
    self.inputVolumeSelector.removeEnabled = False
    self.inputVolumeSelector.noneEnabled = False
    self.inputVolumeSelector.showHidden = False
    self.inputVolumeSelector.showChildNodeTypes = False
    self.inputVolumeSelector.setMRMLScene( slicer.mrmlScene )
    self.inputVolumeSelector.setToolTip( "Pick the input to the algorithm which will be sampled along the line." )
    parametersFormLayout.addRow("Input Volume: ", self.inputVolumeSelector)
    
    #
    # ruler creator
    #
    self.rulerCreationButton = slicer.qSlicerMouseModeToolBar()
    self.rulerCreationButton.setApplicationLogic(slicer.app.applicationLogic())
    self.rulerCreationButton.setMRMLScene(slicer.mrmlScene)
    self.rulerCreationButton.setToolTip( "Create ruler (line segment) for line profile" )
    parametersFormLayout.addRow("Create ruler: ", self.rulerCreationButton)
    # switch to place ruler mode
    appLogic = slicer.app.applicationLogic()
    selectionNode = appLogic.GetSelectionNode()
    selectionNode.SetReferenceActivePlaceNodeClassName("vtkMRMLAnnotationRulerNode")

    #
    # input ruler selector
    #
    self.inputRulerSelector = slicer.qMRMLNodeComboBox()
    self.inputRulerSelector.nodeTypes = ( ("vtkMRMLAnnotationRulerNode"), "" )
    self.inputRulerSelector.selectNodeUponCreation = True
    self.inputRulerSelector.addEnabled = False
    self.inputRulerSelector.removeEnabled = False
    self.inputRulerSelector.noneEnabled = False
    self.inputRulerSelector.showHidden = False
    self.inputRulerSelector.showChildNodeTypes = False
    self.inputRulerSelector.setMRMLScene( slicer.mrmlScene )
    self.inputRulerSelector.setToolTip( "Pick the ruler that defines the sampling line." )
    parametersFormLayout.addRow("Input ruler: ", self.inputRulerSelector)

    #
    # output volume selector
    #
    self.outputArraySelector = slicer.qMRMLNodeComboBox()
    self.outputArraySelector.nodeTypes = ( ("vtkMRMLDoubleArrayNode"), "" )
    self.outputArraySelector.addEnabled = True
    self.outputArraySelector.removeEnabled = True
    self.outputArraySelector.noneEnabled = False
    self.outputArraySelector.showHidden = False
    self.outputArraySelector.showChildNodeTypes = False
    self.outputArraySelector.setMRMLScene( slicer.mrmlScene )
    self.outputArraySelector.setToolTip( "Pick the output to the algorithm." )
    parametersFormLayout.addRow("Output array: ", self.outputArraySelector)

    #
    # scale factor for screen shots
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
    self.applyButton = qt.QPushButton("Apply")
    self.applyButton.toolTip = "Run the algorithm."
    self.applyButton.enabled = False
    parametersFormLayout.addRow(self.applyButton)
    self.onSelect()

    # connections
    self.applyButton.connect('clicked(bool)', self.onApplyButton)
    self.inputVolumeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelect)
    self.inputRulerSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelect)
    self.outputArraySelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelect)

    # Add vertical spacer
    self.layout.addStretch(1)

  def cleanup(self):
    pass

  def onSelect(self):
    self.applyButton.enabled = self.inputVolumeSelector.currentNode() and self.inputRulerSelector.currentNode() and self.outputArraySelector.currentNode()
    #self.applyButton.enabled = True
    #print("selected")

  def onApplyButton(self):
    logic = LineProfileLogic()
    lineResolution = int(self.lineResolutionSliderWidget.value)    
    logic.run(self.inputVolumeSelector.currentNode(), self.inputRulerSelector.currentNode(), self.outputArraySelector.currentNode(), lineResolution)

  def onReload(self,moduleName="LineProfile"):
    """Generic reload method for any scripted module.
    ModuleWizard will subsitute correct default moduleName.
    """
    globals()[moduleName] = slicer.util.reloadScriptedModule(moduleName)

  def onReloadAndTest(self,moduleName="LineProfile"):
    try:
      self.onReload()
      evalString = 'globals()["%s"].%sTest()' % (moduleName, moduleName)
      tester = eval(evalString)
      tester.runTest()
    except Exception, e:
      import traceback
      traceback.print_exc()
      qt.QMessageBox.warning(slicer.util.mainWindow(), 
          "Reload and Test", 'Exception!\n\n' + str(e) + "\n\nSee Python Console for Stack Trace")


#
# LineProfileLogic
#

class LineProfileLogic:
  """This class should implement all the actual 
  computation done by your module.  The interface 
  should be such that other python code can import
  this class and make use of the functionality without
  requiring an instance of the Widget
  """
  def __init__(self):
    self.chartNodeID = None
    pass

  def run(self,inputVolume,inputRuler,outputArray,lineResolution=100):
    """
    Run the actual algorithm
    """

    self.updateOutputArray(inputVolume,inputRuler,outputArray,lineResolution)
    name=inputVolume.GetName()
    self.updateChart(outputArray,name,lineResolution)

    return True

  def updateOutputArray(self,inputVolume,inputRuler,outputArray,lineResolution):
  
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
        print ("Cannot handle non-linear transforms - ignoring transform of the input ruler")

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
    if vtk.VTK_MAJOR_VERSION <= 5:
      probeFilter.SetSource(inputVolume.GetImageData())
    else:
      probeFilter.SetSourceData(inputVolume.GetImageData())
    probeFilter.Update()

    probedPoints=probeFilter.GetOutput()

    # Create arrays of data  
    a = outputArray.GetArray()
    a.SetNumberOfTuples(probedPoints.GetNumberOfPoints())
    x = xrange(0, probedPoints.GetNumberOfPoints())
    xStep=rulerLengthMm/(probedPoints.GetNumberOfPoints()-1)
    probedPointScalars=probedPoints.GetPointData().GetScalars()
    for i in range(len(x)):
      a.SetComponent(i, 0, x[i]*xStep)
      a.SetComponent(i, 1, probedPointScalars.GetTuple(i)[0])
      a.SetComponent(i, 2, 0)
      
    probedPoints.GetPointData().GetScalars().Modified()

  def updateChart(self,outputArray,name,lineResolution):
    
    # Change the layout to one that has a chart.  This created the ChartView
    ln = slicer.util.getNode(pattern='vtkMRMLLayoutNode*')
    ln.SetViewArrangement(24)
    # Get the first ChartView node
    cvn = slicer.util.getNode(pattern='vtkMRMLChartViewNode*')

    # If we already created a chart node and it is still exists then reuse that
    cn = None
    if self.chartNodeID:
      cn = slicer.mrmlScene.GetNodeByID(cvn.GetChartNodeID())
    if not cn:
      cn = slicer.mrmlScene.AddNode(slicer.vtkMRMLChartNode())
      self.chartNodeID = cn.GetID()
      # Configure properties of the Chart
      cn.SetProperty('default', 'title', 'Line profile')
      cn.SetProperty('default', 'xAxisLabel', 'Distance (mm)')
      cn.SetProperty('default', 'yAxisLabel', 'Intensity')  
    
    cn.AddArray(name, outputArray.GetID())
    
    # Set the chart to display
    cvn.SetChartNodeID(cn.GetID())
    cvn.Modified()
