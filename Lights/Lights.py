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
    self.parent.helpText = """This module allows setting up multiple lights in 3D views to make general purpose lighting of vtk scenes simple, flexible, and attractive.
Default light in a 3D view is a headlight located at the camera. HeadLights are very simple to use, but they don't show the shape of objects very well, don't give a good sense of "up" and "down",
and don't evenly light the object.<br>
A LightKit consists of three lights, a key light, a fill light, and a headlight. The main light is the key light. The other lights in the kit (the fill light, headlight, and a pair of back lights) are weaker sources that provide extra illumination
to fill in the spots that the key light misses.
<ul>
  <li>
    Key light is usually positioned so that it appears like an overhead light (like the sun, or a ceiling light).
    It is generally positioned to shine down on the scene from about a 45 degree angle vertically and at least a little offset side to side.
    The key light usually at least about twice as bright as the total of all other lights in the scene to provide good modeling of object features.
  </li>
  <li>
    Fill light is usually positioned across from or opposite from the key light (though still on the same side of the object as the camera)
    in order to simulate diffuse reflections from other objects in the scene.
  </li>
  <li>
    Headlight, always located at the position of the camera, reduces the contrast between areas lit by the key and fill light.
  </li>
  <li>
    Two back lights, one on the left of the object as seen from the observer and one on the right, fill on the high-contrast areas behind the object.
    To enforce the relationship between the different lights, the intensity of the fill, back and headlights are set as a ratio to the key light brightness.
    Thus, the brightness of all the lights in the scene can be changed by changing the key light intensity.
  </li>
</ul>
All lights are directional lights (infinitely far away with no falloff). Lights move with the camera.
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
    self.ui.managedViewsCheckableNodeComboBox.setMRMLScene(slicer.mrmlScene)
    self.ui.managedViewsCheckableNodeComboBox.connect('checkedNodesChanged()', self.onUpdateManagedViewList)
    self.ui.selectAllViewsPushButton.connect('clicked(bool)', self.onSelectAllViews)

    self.ui.presetDefault.connect('clicked(bool)', self.onPresetDefault)
    self.ui.presetCeilingLighting.connect('clicked(bool)', self.onPresetCeilingLighting)
    self.ui.presetSideLighting.connect('clicked(bool)', self.onPresetSideLighting)
    self.ui.presetSunset.connect('clicked(bool)', self.onPresetSunset)
    self.ui.presetOpera.connect('clicked(bool)', self.onPresetOpera)

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

    self.ui.ssaoCheckBox.connect('toggled(bool)', lambda value: self.logic.setUseSSAO(value))
    self.ui.ssaoSizeScaleSliderWidget.connect('valueChanged(double)', lambda value: self.logic.setSSAOSizeScaleLog(value))

    self.updateWidgetFromLogic()

    # Add vertical spacer
    self.layout.addStretch(1)

  def cleanup(self):
    pass

  def onUpdateManagedViewList(self):
    checkedNodes = self.ui.managedViewsCheckableNodeComboBox.checkedNodes()
    uncheckedNodes = self.ui.managedViewsCheckableNodeComboBox.uncheckedNodes()
    for viewNode in checkedNodes:
      self.logic.addManagedView(viewNode)
    for viewNode in uncheckedNodes:
      self.logic.removeManagedView(viewNode)

  def onSelectAllViews(self):
    uncheckedNodes = self.ui.managedViewsCheckableNodeComboBox.uncheckedNodes()
    for viewNode in uncheckedNodes:
      self.ui.managedViewsCheckableNodeComboBox.setCheckState(viewNode, qt.Qt.Checked)

  def onPresetDefault(self):
    # Key
    self.logic.lightKit.SetKeyLightIntensity(0.75)
    self.logic.lightKit.SetKeyLightWarmth(0.6)
    self.logic.lightKit.SetKeyLightElevation(50)
    self.logic.lightKit.SetKeyLightAzimuth(10)
    # Head
    self.logic.lightKit.SetKeyToHeadRatio(1.0/0.33)
    self.logic.lightKit.SetHeadLightWarmth(0.5)
    # Fill
    self.logic.lightKit.SetKeyToFillRatio(1.0/0.33)
    self.logic.lightKit.SetFillLightWarmth(0.4)
    self.logic.lightKit.SetFillLightElevation(-75)
    self.logic.lightKit.SetFillLightAzimuth(-10)
    # Back
    self.logic.lightKit.SetKeyToBackRatio(1.0/0.29)
    self.logic.lightKit.SetBackLightWarmth(0.5)
    self.logic.lightKit.SetBackLightElevation(0)
    self.logic.lightKit.SetBackLightAzimuth(90)
    # Update logic and GUI
    self.logic.lightKit.Modified()
    self.updateWidgetFromLogic()

  def onPresetSunset(self):
    # Key
    self.logic.lightKit.SetKeyLightIntensity(1.08)
    self.logic.lightKit.SetKeyLightWarmth(0.7)
    self.logic.lightKit.SetKeyLightElevation(50)
    self.logic.lightKit.SetKeyLightAzimuth(-50)
    # Head
    self.logic.lightKit.SetKeyToHeadRatio(1.0/0.23)
    self.logic.lightKit.SetHeadLightWarmth(0.5)
    # Fill
    self.logic.lightKit.SetKeyToFillRatio(1.0/0.25)
    self.logic.lightKit.SetFillLightWarmth(0.4)
    self.logic.lightKit.SetFillLightElevation(-75)
    self.logic.lightKit.SetFillLightAzimuth(-10)
    # Back
    self.logic.lightKit.SetKeyToBackRatio(1.0/0.05)
    self.logic.lightKit.SetBackLightWarmth(0.5)
    self.logic.lightKit.SetBackLightElevation(0)
    self.logic.lightKit.SetBackLightAzimuth(90)
    # Update logic and GUI
    self.logic.lightKit.Modified()
    self.updateWidgetFromLogic()

  def onPresetOpera(self):
    # Key
    self.logic.lightKit.SetKeyLightIntensity(0.75)
    self.logic.lightKit.SetKeyLightWarmth(0.5)
    self.logic.lightKit.SetKeyLightElevation(10)
    self.logic.lightKit.SetKeyLightAzimuth(10)
    # Head
    self.logic.lightKit.SetKeyToHeadRatio(1.0/1.0)
    self.logic.lightKit.SetHeadLightWarmth(0.5)
    # Fill
    self.logic.lightKit.SetKeyToFillRatio(1.0/0.1)
    self.logic.lightKit.SetFillLightWarmth(0.4)
    self.logic.lightKit.SetFillLightElevation(-75)
    self.logic.lightKit.SetFillLightAzimuth(-10)
    # Back
    self.logic.lightKit.SetKeyToBackRatio(1.0/0.1)
    self.logic.lightKit.SetBackLightWarmth(0.5)
    self.logic.lightKit.SetBackLightElevation(0)
    self.logic.lightKit.SetBackLightAzimuth(90)
    # Update logic and GUI
    self.logic.lightKit.Modified()
    self.updateWidgetFromLogic()

  def onPresetCeilingLighting(self):
    # Key
    self.logic.lightKit.SetKeyLightIntensity(1.5)
    self.logic.lightKit.SetKeyLightWarmth(0.6)
    self.logic.lightKit.SetKeyLightElevation(70)
    self.logic.lightKit.SetKeyLightAzimuth(10)
    # Head
    self.logic.lightKit.SetKeyToHeadRatio(1.0/0.1)
    self.logic.lightKit.SetHeadLightWarmth(0.5)
    # Fill
    self.logic.lightKit.SetKeyToFillRatio(1.0/0.33)
    self.logic.lightKit.SetFillLightWarmth(0.4)
    self.logic.lightKit.SetFillLightElevation(-75)
    self.logic.lightKit.SetFillLightAzimuth(-10)
    # Back
    self.logic.lightKit.SetKeyToBackRatio(1.0/0.29)
    self.logic.lightKit.SetBackLightWarmth(0.5)
    self.logic.lightKit.SetBackLightElevation(0)
    self.logic.lightKit.SetBackLightAzimuth(90)
    # Update logic and GUI
    self.logic.lightKit.Modified()
    self.updateWidgetFromLogic()

  def onPresetSideLighting(self):
    # Key
    self.logic.lightKit.SetKeyLightIntensity(0.9)
    self.logic.lightKit.SetKeyLightWarmth(0.6)
    self.logic.lightKit.SetKeyLightElevation(50)
    self.logic.lightKit.SetKeyLightAzimuth(10)
    # Head
    self.logic.lightKit.SetKeyToHeadRatio(1.0/0.05)
    self.logic.lightKit.SetHeadLightWarmth(0.5)
    # Fill
    self.logic.lightKit.SetKeyToFillRatio(1.0/0.05)
    self.logic.lightKit.SetFillLightWarmth(0.4)
    self.logic.lightKit.SetFillLightElevation(-75)
    self.logic.lightKit.SetFillLightAzimuth(-10)
    # Back
    self.logic.lightKit.SetKeyToBackRatio(1.0/1.2)
    self.logic.lightKit.SetBackLightWarmth(0.7)
    self.logic.lightKit.SetBackLightElevation(0)
    self.logic.lightKit.SetBackLightAzimuth(90)
    # Update logic and GUI
    self.logic.lightKit.Modified()
    self.updateWidgetFromLogic()

  def updateWidgetFromLogic(self):
    lightkit = self.logic.lightKit

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

    if vtk.vtkVersion().GetVTKMajorVersion()>=9:
      self.ui.ssaoCheckBox.checked = self.logic.ssaoEnabled
      self.ui.ssaoSizeScaleSliderWidget.value = self.logic.ssaoSizeScaleLog
    else:
      self.ui.SSAOCollapsibleButton.hide()


#
# LightsLogic
#

class LightsLogic(ScriptedLoadableModuleLogic):

  def __init__(self):
    self.lightKit = vtk.vtkLightKit()
    self.lightKit.MaintainLuminanceOn()
    lightkitObserverTag = self.lightKit.AddObserver(vtk.vtkCommand.ModifiedEvent, self.onLightkitModified)
    self.ssaoEnabled = False
    self.ssaoSizeScaleLog = 0.0
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

  def addManagedView(self, viewNode):
    if viewNode in self.managedViewNodes:
      return
    self.managedViewNodes.append(viewNode)
    renderWindow = self.renderWindowFromViewNode(viewNode)
    renderer = renderWindow.GetRenderers().GetFirstRenderer()
    renderer.RemoveAllLights()
    self.lightKit.AddLightsToRenderer(renderer)

    renderer.SSAOBlurOn()  # reduce noise in SSAO mode
    self.setUseSSAO(self.ssaoEnabled)
    self.setSSAOSizeScaleLog(self.ssaoSizeScaleLog)

    renderWindow.Render()

  def removeManagedView(self, viewNode):
    if viewNode not in self.managedViewNodes:
      return
    self.managedViewNodes.remove(viewNode)
    renderWindow = self.renderWindowFromViewNode(viewNode)
    renderer = renderWindow.GetRenderers().GetFirstRenderer()
    # Make a copy of current lightkit
    currentLightKit = vtk.vtkLightKit()
    currentLightKit.DeepCopy(self.lightKit)
    renderer.RemoveAllLights()
    currentLightKit.AddLightsToRenderer(renderer)

  def setUseSSAO(self, enable):
    self.ssaoEnabled = enable
    for viewNode in self.managedViewNodes:
      renderWindow = self.renderWindowFromViewNode(viewNode)
      renderer = renderWindow.GetRenderers().GetFirstRenderer()
      renderer.SetUseSSAO(self.ssaoEnabled)
      renderWindow.Render()

  def setSSAOSizeScaleLog(self, scaleLog):
    self.ssaoSizeScaleLog = scaleLog
    # ScaleLog = 0.0 corresponds to 100mm scene size
    sceneSize = 100.0 * pow(10, self.ssaoSizeScaleLog)
    # Bias and radius are from example in https://blog.kitware.com/ssao/.
    # These values have been tested on different kind of meshes and found to work well.
    for viewNode in self.managedViewNodes:
      renderWindow = self.renderWindowFromViewNode(viewNode)
      renderer = renderWindow.GetRenderers().GetFirstRenderer()
      renderer.SetSSAORadius(0.1 * sceneSize);  # comparison radius
      renderer.SetSSAOBias(0.001 * sceneSize);  # comparison bias (how much distance difference will be made visible)
      renderWindow.Render()


class LightsTest(ScriptedLoadableModuleTest):

  def setUp(self):
    slicer.mrmlScene.Clear(0)

  def runTest(self):
    self.setUp()
    self.test_Lights1()

  def test_Lights1(self):
    self.delayDisplay('Test passed!')
