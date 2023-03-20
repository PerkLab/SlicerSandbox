import os
import unittest
import logging
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

#
# VolumeRenderingSpecialEffects
#

class VolumeRenderingSpecialEffects(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Volume Rendering Special Effects"
    self.parent.categories = ["Utilities"]
    self.parent.dependencies = []
    self.parent.contributors = ["Simon Drouin (BWH)", "Steve Pieper (Isomics)", "Andras Lasso (PerkLab)"]
    self.parent.helpText = """
This module demonstrate usage of custom shaders to create special effects in volume rendering.
"""
    self.parent.acknowledgementText = """
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
"""

#
# VolumeRenderingSpecialEffectsWidget
#

class VolumeRenderingSpecialEffectsWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
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
    uiWidget = slicer.util.loadUI(self.resourcePath('UI/VolumeRenderingSpecialEffects.ui'))
    self.layout.addWidget(uiWidget)
    self.ui = slicer.util.childWidgetVariables(uiWidget)

    #self.ui.inputMarkupsSelector.tableWidget().hide()
    self.ui.inputMarkupsSelector.setJumpToSliceEnabled(True)
    self.ui.inputMarkupsSelector.setDefaultNodeColor(qt.QColor.fromRgbF(1, 0, 0))

    # Set scene in MRML widgets. Make sure that in Qt designer
    # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
    # "setMRMLScene(vtkMRMLScene*)" slot.
    uiWidget.setMRMLScene(slicer.mrmlScene)

    # Create a new parameterNode
    # This parameterNode stores all user choices in parameter values, node selections, etc.
    # so that when the scene is saved and reloaded, these settings are restored.
    self.logic = VolumeRenderingSpecialEffectsLogic()
    self.ui.parameterNodeSelector.addAttribute("vtkMRMLScriptedModuleNode", "ModuleName", self.moduleName)
    self.setParameterNode(self.logic.getParameterNode())

    # Connections
    self.ui.parameterNodeSelector.connect('currentNodeChanged(vtkMRMLNode*)', self.setParameterNode)

    # These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
    # (in the selected parameter node).
    self.ui.inputVolumeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
    self.ui.noneModeButton.connect("toggled(bool)", self.modeButtonToggled)
    self.ui.sphereCropModeButton.connect("toggled(bool)", self.modeButtonToggled)
    self.ui.wedgeCropModeButton.connect("toggled(bool)", self.modeButtonToggled) 
    self.ui.inputMarkupsSelector.connect("markupsNodeChanged()", self.updateParameterNodeFromGUI)
    self.ui.radiusSliderWidget.connect("valueChanged(double)", self.updateParameterNodeFromGUI)

    # Initial GUI update
    self.updateGUIFromParameterNode()

  def cleanup(self):
    """
    Called when the application closes and the module widget is destroyed.
    """
    self.logic.setParameterNode(None)
    self.removeObservers()

  def setParameterNode(self, inputParameterNode):
    """
    Adds observers to the selected parameter node. Observation is needed because when the
    parameter node is changed then the GUI must be updated immediately.
    """

    if inputParameterNode:
      self.logic.setDefaultParameters(inputParameterNode)
      if not inputParameterNode.GetNodeReference("InputMarkups"):
        newMarkupsNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", "C")
        newMarkupsNode.CreateDefaultDisplayNodes()
        newMarkupsNode.GetDisplayNode().SetPointLabelsVisibility(False)
        inputParameterNode.SetAndObserveNodeReferenceID("InputMarkups", newMarkupsNode.GetID())

    # Set parameter node in the parameter node selector widget
    wasBlocked = self.ui.parameterNodeSelector.blockSignals(True)
    self.ui.parameterNodeSelector.setCurrentNode(inputParameterNode)
    self.ui.parameterNodeSelector.blockSignals(wasBlocked)

    self.logic.setParameterNode(inputParameterNode)

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

  def modeButtonToggled(self, toggled):
    if toggled:
      self.updateParameterNodeFromGUI()

  def updateGUIFromParameterNode(self, caller=None, event=None):
    """
    This method is called whenever parameter node is changed.
    The module GUI is updated to show the current state of the parameter node.
    """

    # Disable all sections if no parameter node is selected
    self.ui.basicCollapsibleButton.enabled = self._parameterNode is not None
    self.ui.advancedCollapsibleButton.enabled = self._parameterNode is not None
    if self._parameterNode is None:
      return

    # Update each widget from parameter node
    # Need to temporarily block signals to prevent infinite recursion (MRML node update triggers
    # GUI update, which triggers MRML node update, which triggers GUI update, ...)

    wasBlocked = self.ui.inputVolumeSelector.blockSignals(True)
    self.ui.inputVolumeSelector.setCurrentNode(self._parameterNode.GetNodeReference("InputVolume"))
    self.ui.inputVolumeSelector.blockSignals(wasBlocked)

    wasBlocked = self.ui.inputMarkupsSelector.blockSignals(True)
    self.ui.inputMarkupsSelector.setCurrentNode(self._parameterNode.GetNodeReference("InputMarkups"))
    self.ui.inputMarkupsSelector.blockSignals(wasBlocked)

    wasBlocked = self.ui.radiusSliderWidget.blockSignals(True)
    self.ui.radiusSliderWidget.value = float(self._parameterNode.GetParameter("Radius")) if self._parameterNode.GetParameter("Radius") else 50.0
    self.ui.radiusSliderWidget.blockSignals(wasBlocked)

    mode = self._parameterNode.GetParameter("Mode")
    
    wasBlocked = self.ui.noneModeButton.blockSignals(True)
    self.ui.noneModeButton.checked = (mode == "None")
    self.ui.noneModeButton.blockSignals(wasBlocked)

    wasBlocked = self.ui.sphereCropModeButton.blockSignals(True)
    self.ui.sphereCropModeButton.checked = (mode == "SphereCrop")
    self.ui.sphereCropModeButton.blockSignals(wasBlocked)

    wasBlocked = self.ui.wedgeCropModeButton.blockSignals(True)
    self.ui.wedgeCropModeButton.checked = (mode == "WedgeCrop")
    self.ui.wedgeCropModeButton.blockSignals(wasBlocked)


  def updateParameterNodeFromGUI(self, caller=None, event=None):
    """
    This method is called when the user makes any change in the GUI.
    The changes are saved into the parameter node (so that they are restored when the scene is saved and loaded).
    """

    if self._parameterNode is None:
      return

    wasModified = self._parameterNode.StartModify()
    self._parameterNode.SetNodeReferenceID("InputVolume", self.ui.inputVolumeSelector.currentNodeID)
    self._parameterNode.SetNodeReferenceID("InputMarkups", self.ui.inputMarkupsSelector.currentNode().GetID() if self.ui.inputMarkupsSelector.currentNode() else None)
    self._parameterNode.SetParameter("Radius", str(self.ui.radiusSliderWidget.value))

    mode = "None"
    if self.ui.sphereCropModeButton.checked:
      mode = "SphereCrop"
    elif self.ui.wedgeCropModeButton.checked:
      mode = "WedgeCrop"
    self._parameterNode.SetParameter("Mode", mode)

    self._parameterNode.EndModify(wasModified)

#
# VolumeRenderingSpecialEffectsLogic
#

class VolumeRenderingSpecialEffectsLogic(ScriptedLoadableModuleLogic, VTKObservationMixin):
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
    VTKObservationMixin.__init__(self)  # needed for parameter node observation
    self._parameterNode = None
    self._volumeNode = None
    self._markupsNode = None
    self._mode = "None"

  def setDefaultParameters(self, parameterNode):
    """
    Initialize parameter node with default settings.
    """
    if not parameterNode.GetParameter("Radius"):
      parameterNode.SetParameter("Radius", "50.0")

  def setParameterNode(self, inputParameterNode):
    """
    Adds observers to the selected parameter node.
    """

    if inputParameterNode == self._parameterNode:
      # No change
      return

    # Unobserve previusly selected parameter node and add an observer to the newly selected.
    if self._parameterNode is not None:
      self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.parameterNodeModified)
    if inputParameterNode is not None:
      self.addObserver(inputParameterNode, vtk.vtkCommand.ModifiedEvent, self.parameterNodeModified)
    self._parameterNode = inputParameterNode

    # Initial update
    self.parameterNodeModified()

  def parameterNodeModified(self, caller=None, event=None):
    markupsNode = self._parameterNode.GetNodeReference("InputMarkups") if self._parameterNode else None
    if self._markupsNode != markupsNode:
      if self._markupsNode is not None:
        self.removeObserver(self._markupsNode, slicer.vtkMRMLMarkupsNode.PointModifiedEvent, self.markupsNodeModified)
        self.removeObserver(self._markupsNode, slicer.vtkMRMLTransformableNode.TransformModifiedEvent, self.markupsNodeModified)
      if markupsNode is not None:
        self.addObserver(markupsNode, slicer.vtkMRMLMarkupsNode.PointModifiedEvent, self.markupsNodeModified)
        self.addObserver(markupsNode, slicer.vtkMRMLTransformableNode.TransformModifiedEvent, self.markupsNodeModified)
      self._markupsNode = markupsNode
      customShaderUpdateNeeded = True

    self.updateCustomShader()

  def markupsNodeModified(self, caller=None, event=None):
    self.updateCustomShader()

  def updateCustomShader(self):
    if not self._parameterNode:
      return
    volumeNode = self._parameterNode.GetNodeReference("InputVolume")
    if not volumeNode:
      return
    vrLogic = slicer.modules.volumerendering.logic()
    vrDisplayNode = vrLogic.GetFirstVolumeRenderingDisplayNode(volumeNode)
    if not vrDisplayNode:
      vrDisplayNode = vrLogic.CreateDefaultVolumeRenderingNodes(volumeNode)
      slicer.mrmlScene.AddNode(vrDisplayNode)
      vrDisplayNode.SetVisibility(True)
      volumeNode.AddAndObserveDisplayNodeID(vrDisplayNode.GetID())

    mode = self._parameterNode.GetParameter("Mode")
    markupsNode = self._parameterNode.GetNodeReference("InputMarkups")
    radius = float(self._parameterNode.GetParameter("Radius")) if self._parameterNode.GetParameter("Radius") else 50.0

    shaderPropNode = vrDisplayNode.GetOrCreateShaderPropertyNode(slicer.mrmlScene)
    shaderProp = shaderPropNode.GetShaderProperty()
    volumePropertyNode = vrDisplayNode.GetVolumePropertyNode()
    volumeProperty = volumePropertyNode.GetVolumeProperty()
    shaderUniforms = shaderPropNode.GetFragmentUniforms()

    if mode == "None":
      if mode != self._mode:
        shaderUniforms.RemoveAllUniforms()
        shaderProp.ClearAllFragmentShaderReplacements()

    elif mode == "WedgeCrop":
      if not markupsNode or markupsNode.GetNumberOfDefinedControlPoints() < 2:
        mode = "None"
      if mode != self._mode:
        shaderUniforms.RemoveAllUniforms()
        shaderProp.ClearAllFragmentShaderReplacements()
      if mode != "None":
        centerPoint = [0.0, 0.0, 0.0]
        markupsNode.GetNthControlPointPositionWorld(0, centerPoint)
        viewPoint = [0.0, 0.0, 0.0]
        markupsNode.GetNthControlPointPositionWorld(1, viewPoint)
        shaderUniforms.SetUniform3f("centerPoint",centerPoint)
        shaderUniforms.SetUniform3f("viewPoint",viewPoint)
        from math import sqrt, cos, atan
        dist = sqrt(vtk.vtkMath.Distance2BetweenPoints(centerPoint, viewPoint))
        viewAngleRad = atan(radius/dist)
        shaderUniforms.SetUniformf("coneCutoff", cos(viewAngleRad))
        if mode != self._mode:
          croppingImplShaderCode = """
              vec4 texCoordRAS = in_volumeMatrix[0] * in_textureDatasetMatrix[0]  * vec4(g_dataPos, 1.);
              vec3 samplePoint = texCoordRAS.xyz;
              vec3 toSample = normalize(samplePoint - centerPoint);
              vec3 toEnd = normalize(viewPoint - centerPoint);
              float onLine = dot(toEnd, toSample);
              g_skip = (onLine > coneCutoff);
          """
          shaderProp.AddFragmentShaderReplacement("//VTK::Cropping::Impl", True, croppingImplShaderCode, False)

    elif mode == "SphereCrop":
      if not markupsNode or markupsNode.GetNumberOfDefinedControlPoints() < 1:
        mode = "None"
      if mode != self._mode:
        shaderUniforms.RemoveAllUniforms()
        shaderProp.ClearAllFragmentShaderReplacements()
      if mode != "None":
        centerPoint = [0.0, 0.0, 0.0]
        markupsNode.GetNthControlPointPositionWorld(0, centerPoint)
        shaderUniforms.SetUniform3f("centerPoint",centerPoint)
        shaderUniforms.SetUniformf("radius", radius)
        if mode != self._mode:
          croppingImplShaderCode = """
              vec4 texCoordRAS = in_volumeMatrix[0] * in_textureDatasetMatrix[0]  * vec4(g_dataPos, 1.);
              g_skip = length(texCoordRAS.xyz - centerPoint) < radius;
          """
          shaderProp.AddFragmentShaderReplacement("//VTK::Cropping::Impl", True, croppingImplShaderCode, False)

    self._mode = mode


#
# VolumeRenderingSpecialEffectsTest
#

class VolumeRenderingSpecialEffectsTest(ScriptedLoadableModuleTest):
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
    self.test_VolumeRenderingSpecialEffects1()

  def test_VolumeRenderingSpecialEffects1(self):
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
    volumeNode = SampleData.downloadFromURL(
      nodeNames='MRHead',
      fileNames='MR-Head.nrrd',
      uris='https://github.com/Slicer/SlicerTestingData/releases/download/MD5/39b01631b7b38232a220007230624c8e',
      checksums='MD5:39b01631b7b38232a220007230624c8e')[0]
    self.delayDisplay('Finished with download and loading')

    markupsNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode")
    markupsNode.CreateDefaultDisplayNodes()

    parameterNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScriptedModuleNode")
    parameterNode.SetModuleName("VolumeRenderingSpecialEffects")
    parameterNode.SetAttribute("ModuleName", "VolumeRenderingSpecialEffects")
    parameterNode.SetNodeReferenceID("InputVolume", volumeNode.GetID())
    parameterNode.SetNodeReferenceID("InputMarkups", markupsNode.GetID())
    parameterNode.SetParameter("Radius", "60.0")
    parameterNode.SetParameter("Mode", "None")

    # Test the module logic

    self.delayDisplay('No special effect')
    logic = VolumeRenderingSpecialEffectsLogic()
    logic.setParameterNode(parameterNode)

    self.delayDisplay('Sphere crop')
    markupsNode.AddControlPointWorld(vtk.vtkVector3d(-3,67,45))
    parameterNode.SetParameter("Mode", "SphereCrop")

    self.delayDisplay('Wedge crop')
    markupsNode.RemoveAllControlPoints()
    markupsNode.AddControlPointWorld(vtk.vtkVector3d(1,30,-20))
    markupsNode.AddControlPointWorld(vtk.vtkVector3d(30,97,20))
    parameterNode.SetParameter("Mode", "WedgeCrop")

    self.delayDisplay('Test passed')

