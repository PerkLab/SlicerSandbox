import os
import unittest
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
import logging

#
# Lights
#

class Lights(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Lights"
    self.parent.categories = ["Utilities"]
    self.parent.dependencies = []
    self.parent.contributors = ["Andras Lasso (PerkLab)"]
    self.parent.helpText = """This module allows setting up multiple lights in 3D views
"""
    self.parent.helpText += self.getDefaultModuleDocumentationLink()
    self.parent.acknowledgementText = """
This file was originally developed by Andras Lasso.
"""

#
# LightsWidget
#

class LightsWidget(ScriptedLoadableModuleWidget):
  """Uses ScriptedLoadableModuleWidget base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def setup(self):
    ScriptedLoadableModuleWidget.setup(self)

    # Load widget from .ui file (created by Qt Designer)
    uiWidget = slicer.util.loadUI(self.resourcePath('UI/Lights.ui'))
    self.layout.addWidget(uiWidget)
    self.ui = slicer.util.childWidgetVariables(uiWidget)

    self.logic = LightsLogic()

    # connections
    self.ui.viewNodeComboBox.setMRMLScene( slicer.mrmlScene )
    self.ui.setupLightkitButton.connect('clicked(bool)', self.onSetupLighkit)

    self.ui.keyIntensitySliderWidget.connect('valueChanged(double)', lambda value: self.logic.lightKit.SetKeyLightIntensity(value))
    self.ui.keyWarmthSliderWidget.connect('valueChanged(double)', lambda value: self.logic.lightKit.SetKeyLightWarmth(value))
    self.ui.keyElevationSliderWidget.connect('valueChanged(double)', lambda value: self.logic.lightKit.SetKeyLightElevation(value))
    self.ui.keyElevationSliderWidget.connect('valueChanged(double)', lambda value: self.logic.lightKit.Modified())
    self.ui.keyAzimuthSliderWidget.connect('valueChanged(double)', lambda value: self.logic.lightKit.SetKeyLightAzimuth(value))
    self.ui.keyAzimuthSliderWidget.connect('valueChanged(double)', lambda value: self.logic.lightKit.Modified())

    self.ui.headIntensitySliderWidget.connect('valueChanged(double)', lambda value: self.logic.lightKit.SetKeyToHeadRatio(1.0/value))
    self.ui.headWarmthSliderWidget.connect('valueChanged(double)', lambda value: self.logic.lightKit.SetHeadLightWarmth(value))

    self.ui.fillIntensitySliderWidget.connect('valueChanged(double)', lambda value: self.logic.lightKit.SetKeyToFillRatio(1.0/value))
    self.ui.fillWarmthSliderWidget.connect('valueChanged(double)', lambda value: self.logic.lightKit.SetFillLightWarmth(value))
    self.ui.fillElevationSliderWidget.connect('valueChanged(double)', lambda value: self.logic.lightKit.SetFillLightElevation(value))
    self.ui.fillElevationSliderWidget.connect('valueChanged(double)', lambda value: self.logic.lightKit.Modified())
    self.ui.fillAzimuthSliderWidget.connect('valueChanged(double)', lambda value: self.logic.lightKit.SetFillLightAzimuth(value))
    self.ui.fillAzimuthSliderWidget.connect('valueChanged(double)', lambda value: self.logic.lightKit.Modified())

    self.ui.backIntensitySliderWidget.connect('valueChanged(double)', lambda value: self.logic.lightKit.SetKeyToBackRatio(1.0/value))
    self.ui.backWarmthSliderWidget.connect('valueChanged(double)', lambda value: self.logic.lightKit.SetBackLightWarmth(value))
    self.ui.backElevationSliderWidget.connect('valueChanged(double)', lambda value: self.logic.lightKit.SetBackLightElevation(value))
    self.ui.backElevationSliderWidget.connect('valueChanged(double)', lambda value: self.logic.lightKit.Modified())
    self.ui.backAzimuthSliderWidget.connect('valueChanged(double)', lambda value: self.logic.lightKit.SetBackLightAzimuth(value))
    self.ui.backAzimuthSliderWidget.connect('valueChanged(double)', lambda value: self.logic.lightKit.Modified())

    self.updateWidgetFromLightkit(self.logic.lightKit)

    # Add vertical spacer
    self.layout.addStretch(1)

  def cleanup(self):
    pass

  def onSetupLighkit(self):
    self.logic.setLightkitInView(self.ui.viewNodeComboBox.currentNode())

  def updateWidgetFromLightkit(self, lightkit):
    self.ui.keyIntensitySliderWidget.value = lightkit.GetKeyLightIntensity()
    self.ui.keyWarmthSliderWidget.value = lightkit.GetKeyLightWarmth()
    self.ui.keyElevationSliderWidget.value = lightkit.GetKeyLightElevation()
    self.ui.keyAzimuthSliderWidget.value = lightkit.GetKeyLightAzimuth()

    self.ui.headIntensitySliderWidget.value = 1.0/lightkit.GetKeyToHeadRatio()
    self.ui.headWarmthSliderWidget.value = lightkit.GetHeadLightWarmth()

    self.ui.fillIntensitySliderWidget.value = 1.0/lightkit.GetKeyToFillRatio()
    self.ui.fillWarmthSliderWidget.value = lightkit.GetFillLightWarmth()
    self.ui.fillElevationSliderWidget.value = lightkit.GetFillLightElevation()
    self.ui.fillAzimuthSliderWidget.value = lightkit.GetFillLightAzimuth()

    self.ui.backIntensitySliderWidget.value = 1.0/lightkit.GetKeyToBackRatio()
    self.ui.backWarmthSliderWidget.value = lightkit.GetBackLightWarmth()
    self.ui.backElevationSliderWidget.value = lightkit.GetBackLightElevation()
    self.ui.backAzimuthSliderWidget.value = lightkit.GetBackLightAzimuth()


#
# LightsLogic
#

class LightsLogic(ScriptedLoadableModuleLogic):

  def __init__(self):
    self.lightKit = vtk.vtkLightKit()
    self.lightKit.MaintainLuminanceOn()
    lightkitObserverTag = self.lightKit.AddObserver(vtk.vtkCommand.ModifiedEvent, self.onLightkitModified)
    self.managedViewNodes = []

  def __del__(self):
    self.lightKit.RemoveObserver(lightkitObserverTag)

  def onLightkitModified(self, caller, event):
    for viewNode in self.managedViewNodes:
      renderWindow = self.renderWindowFromViewNode(viewNode)
      renderWindow.Render()

  def renderWindowFromViewNode(self, viewNode):
    renderView = None
    lm = slicer.app.layoutManager()
    for widgetIndex in range(lm.threeDViewCount):
      view = lm.threeDWidget(widgetIndex).threeDView()
      if viewNode == view.mrmlViewNode():
        return view.renderWindow()
    raise ValueError('Selected 3D view is not visible in the current layout.')

  def setLightkitInView(self, viewNode):
    if viewNode in self.managedViewNodes:
      return
    self.managedViewNodes.append(viewNode)
    renderWindow = self.renderWindowFromViewNode(viewNode)
    renderer = renderWindow.GetRenderers().GetFirstRenderer()
    renderer.RemoveAllLights()
    self.lightKit.AddLightsToRenderer(renderer)
    renderWindow.Render()


class LightsTest(ScriptedLoadableModuleTest):

  def setUp(self):
    slicer.mrmlScene.Clear(0)

  def runTest(self):
    self.setUp()
    self.test_Lights1()

  def test_Lights1(self):
    self.delayDisplay('Test passed!')
