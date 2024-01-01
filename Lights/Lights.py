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
  https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
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
  https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
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

    self.ui.lightKitRadioButton.connect("toggled(bool)", self.onEnableLightKit)

    self.ui.presetSingleLightDefault.connect('clicked(bool)', self.onPresetSingleLightDefault)

    self.ui.presetBalanced.connect('clicked(bool)', self.onPresetBalanced)
    self.ui.presetCeilingLighting.connect('clicked(bool)', self.onPresetCeilingLighting)
    self.ui.presetSideLighting.connect('clicked(bool)', self.onPresetSideLighting)
    self.ui.presetSunset.connect('clicked(bool)', self.onPresetSunset)
    self.ui.presetOpera.connect('clicked(bool)', self.onPresetOpera)

    self.ui.singleLightIntensitySliderWidget.connect('valueChanged(double)', lambda value: self.logic.setSingleLightIntensity(value))
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

    self.ui.shadowsVisibilityCheckBox.connect('toggled(bool)', lambda value: self.logic.setUseSSAO(value))
    self.ui.ambientShadowsSizeScaleSliderWidget.connect('valueChanged(double)', lambda value: self.logic.setAmbientShadowsSizeScale(value))
    self.ui.ambientShadowsVolumeOpacityThresholdPercentSliderWidget.connect('valueChanged(double)', lambda value: self.logic.setAmbientShadowsVolumeOpacityThreshold(value*0.01))

    self.ui.adaptiveRenderingQualityCheckBox.connect('toggled(bool)', self.logic.setAdaptiveRenderingQuality)

    self.ui.imageNone.connect('clicked(bool)', lambda: self.logic.setImageBasedLighting(None))

    # Find more images at https://polyhaven.com
    self.ui.imageHospitalRoom.connect('clicked(bool)', lambda: self.logic.setImageBasedLighting(self.resourcePath('hospital_room.jpg')))

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

  def onEnableLightKit(self, enable):
    self.logic.setUseLightKit(enable)
    self.updateWidgetFromLogic()

  def onPresetSingleLightDefault(self):
    self.logic.setUseLightKit(False)
    self.logic.setSingleLightIntensity(1.0)
    self.updateWidgetFromLogic()

  def onPresetBalanced(self):
    self.logic.setUseLightKit(True)
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
    self.logic.setUseLightKit(True)
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
    self.logic.setUseLightKit(True)
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
    self.logic.setUseLightKit(True)
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
    self.logic.setUseLightKit(True)
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

    self.ui.singleLightIntensitySliderWidget.value = self.logic.singleLightIntensity

    self.ui.adaptiveRenderingQualityCheckBox.checked = self.logic.adaptiveRenderingQuality

    if vtk.vtkVersion().GetVTKMajorVersion()>=9:
      self.ui.shadowsVisibilityCheckBox.checked = self.logic.shadowsVisibility
      self.ui.ambientShadowsSizeScaleSliderWidget.value = self.logic.ambientShadowsSizeScale
      self.ui.ambientShadowsVolumeOpacityThresholdPercentSliderWidget.value = self.logic.ambientShadowsVolumeOpacityThreshold*100
    else:
      self.ui.SSAOCollapsibleButton.hide()

    self.ui.singleLightRadioButton.checked = not self.logic.useLightKit
    self.ui.lightKitRadioButton.checked = self.logic.useLightKit


#
# LightsLogic
#

class LightsLogic(ScriptedLoadableModuleLogic):

  def __init__(self):
    self.useLightKit = True

    self.singleLightIntensity = 1.0

    self.lightKit = vtk.vtkLightKit()
    self.lightKit.MaintainLuminanceOn()
    self.lightkitObserverTag = self.lightKit.AddObserver(vtk.vtkCommand.ModifiedEvent, self.onLightkitModified)

    self.slicerCoreSupportsShadows = hasattr(slicer.vtkMRMLViewNode, "SetShadowsVisibility")

    self.shadowsVisibility = True
    self.ambientShadowsSizeScale = 0.3
    self.ambientShadowsVolumeOpacityThreshold = 0.25

    self.adaptiveRenderingQuality = True

    self.managedViewNodes = []
    self.imageBasedLightingImageFile = None

  def __del__(self):
    self.lightKit.RemoveObserver(self.lightkitObserverTag)

  def requestRender(self, viewNode=None):
    lm = slicer.app.layoutManager()
    for widgetIndex in range(lm.threeDViewCount):
      view = lm.threeDWidget(widgetIndex).threeDView()
      if (viewNode is None) or (viewNode == view.mrmlViewNode()):
        view.scheduleRender()
        if viewNode:
          # Update of only one view was requested
          return

  def setUseLightKit(self, useLightKit, viewNode=None):
    if viewNode is None:
      self.useLightKit = useLightKit
      viewNodes = self.managedViewNodes
    else:
      viewNodes = [viewNode]
    for viewNode in viewNodes:
      renderWindow = self.renderWindowFromViewNode(viewNode)
      renderer = renderWindow.GetRenderers().GetFirstRenderer()
      renderer.RemoveAllLights()
      if self.useLightKit:
        self.lightKit.AddLightsToRenderer(renderer)
      else:
        renderer.CreateLight()
        self.setSingleLightIntensity(self.singleLightIntensity, viewNode)
      self.requestRender(viewNode)

  def onLightkitModified(self, caller, event):
    self.requestRender()

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
    self.setUseLightKit(self.useLightKit, viewNode)
    self.setSingleLightIntensity(self.singleLightIntensity, viewNode)
    self.setUseSSAO(self.shadowsVisibility, viewNode)
    self.setAmbientShadowsSizeScale(self.ambientShadowsSizeScale, viewNode)
    self.setAmbientShadowsVolumeOpacityThreshold(self.ambientShadowsVolumeOpacityThreshold, viewNode)
    self.setAdaptiveRenderingQuality(self.adaptiveRenderingQuality, viewNode)
    self.requestRender(viewNode)

  def deepCopyAllLights(self, viewNode):
    """Create independent copy of all lights in the renderer"""
    renderWindow = self.renderWindowFromViewNode(viewNode)
    renderer = renderWindow.GetRenderers().GetFirstRenderer()
    numberOfLights = renderer.GetLights().GetNumberOfItems()
    lightCopies = []
    for i in range(numberOfLights):
      originalLight = renderer.GetLights().GetItemAsObject(i)
      newLight = vtk.vtkLight()
      newLight.DeepCopy(originalLight)
      lightCopies.append(newLight)
    renderer.RemoveAllLights()
    for light in lightCopies:
      renderer.AddLight(light)

  def removeManagedView(self, viewNode):
    if viewNode not in self.managedViewNodes:
      return
    self.managedViewNodes.remove(viewNode)
    # Create an independent copy of all lights so that any changes
    # done by this module will not impact the view anymore.
    self.deepCopyAllLights(viewNode)

  def firstLight(self, viewNode):
    renderWindow = self.renderWindowFromViewNode(viewNode)
    renderer = renderWindow.GetRenderers().GetFirstRenderer()
    return renderer.GetLights().GetItemAsObject(0)

  def setSingleLightIntensity(self, intensity, viewNode=None):
    if self.useLightKit:
      return
    if viewNode is None:
      self.singleLightIntensity = intensity
      viewNodes = self.managedViewNodes
    else:
      viewNodes = [viewNode]
    for viewNode in viewNodes:
      firstLight = self.firstLight(viewNode)
      firstLight.SetIntensity(intensity)
      self.requestRender(viewNode)

  def setUseSSAO(self, enable, viewNode=None):
    if viewNode is None:
      self.shadowsVisibility = enable
      viewNodes = self.managedViewNodes
    else:
      viewNodes = [viewNode]
    for viewNode in viewNodes:
      if self.slicerCoreSupportsShadows:
          viewNode.SetShadowsVisibility(self.shadowsVisibility)
      else:
          # Legacy
          renderWindow = self.renderWindowFromViewNode(viewNode)
          renderer = renderWindow.GetRenderers().GetFirstRenderer()
          renderer.SetUseSSAO(self.shadowsVisibility)
          self.requestRender(viewNode)

  def setAmbientShadowsVolumeOpacityThreshold(self, opacityThreshold, viewNode=None):
    if not self.slicerCoreSupportsShadows:
      # Not supported in older Slicer versions
      return

    if viewNode is None:
      self.ambientShadowsVolumeOpacityThreshold = opacityThreshold
      viewNodes = self.managedViewNodes
    else:
      viewNodes = [viewNode]
    for viewNode in viewNodes:
      viewNode.SetAmbientShadowsVolumeOpacityThreshold(opacityThreshold)

  def setAmbientShadowsSizeScale(self, sizeScaleLog, viewNode=None):
    if viewNode is None:
      self.ambientShadowsSizeScale = sizeScaleLog
      viewNodes = self.managedViewNodes
    else:
      viewNodes = [viewNode]
    for viewNode in viewNodes:
      if self.slicerCoreSupportsShadows:
          viewNode.SetAmbientShadowsSizeScale(sizeScaleLog)
      else:
          # Legacy
          # SizeScaleLog = 0.0 corresponds to 100mm scene size
          sceneSize = 100.0 * pow(10, sizeScaleLog)
          # Bias and radius are from example in https://blog.kitware.com/ssao/.
          # These values have been tested on different kind of meshes and found to work well.
          renderWindow = self.renderWindowFromViewNode(viewNode)
          renderer = renderWindow.GetRenderers().GetFirstRenderer()
          renderer.SetSSAOBias(0.001 * sceneSize);  # how much distance difference will be made visible
          renderer.SetSSAORadius(0.1 * sceneSize);  # determines the spread of shadows cast by ambient occlusion
          renderer.SetSSAOBlur(True)  # reduce noise
          renderer.SetSSAOKernelSize(320)  # larger kernel size reduces noise pattern in the darkened region
          self.requestRender(viewNode)

  def setAdaptiveRenderingQuality(self, enable, viewNode=None):
    if viewNode is None:
      self.adaptiveRenderingQuality = enable
      viewNodes = self.managedViewNodes
    else:
      viewNodes = [viewNode]
    for viewNode in viewNodes:
      if enable:
        viewNode.SetVolumeRenderingQuality(slicer.vtkMRMLViewNode.Adaptive)
        viewNode.SetExpectedFPS(30)
        viewNode.SetVolumeRenderingSurfaceSmoothing(True)
      else:
        viewNode.SetVolumeRenderingQuality(slicer.vtkMRMLViewNode.Normal)

  def setImageBasedLighting(self, imageFilePath):
    self.imageBasedLightingImageFile = imageFilePath

    # Get cubemap
    if self.imageBasedLightingImageFile:
      name, extension = os.path.splitext(self.imageBasedLightingImageFile)
      if extension.lower() == '.jpg':
        reader = vtk.vtkJPEGReader()
      elif extension.lower() == '.hdr':
        reader = vtk.vtkHDRReader()
      else:
        raise ValueError("Only jpg and hdr image is accepted for image-based lighting")
      reader.SetFileName(self.imageBasedLightingImageFile)
      texture = vtk.vtkTexture()
      texture.SetInputConnection(reader.GetOutputPort())
      texture.SetColorModeToDirectScalars()
      texture.MipmapOn()
      texture.InterpolateOn()
      cubemap = vtk.vtkEquirectangularToCubeMapTexture()
      cubemap.SetInputTexture(texture)
      cubemap.MipmapOn()
      cubemap.InterpolateOn()
    else:
      cubemap = None

    for viewNode in self.managedViewNodes:
      renderWindow = self.renderWindowFromViewNode(viewNode)
      renderer = renderWindow.GetRenderers().GetFirstRenderer()
      if cubemap:
        renderer.UseSphericalHarmonicsOff()
        renderer.SetEnvironmentTexture(cubemap)
        renderer.UseImageBasedLightingOn()
      else:
        renderer.UseSphericalHarmonicsOn()
        renderer.SetEnvironmentTexture(None)
        renderer.UseImageBasedLightingOff()
      self.requestRender(viewNode)

    # To display skybox in the view:
    #world = vtk.vtkSkybox()
    #world.SetTexture(cubemap)
    #renderer.AddActor(world)

class LightsTest(ScriptedLoadableModuleTest):

  def setUp(self):
    slicer.mrmlScene.Clear(0)

  def runTest(self):
    self.setUp()
    self.test_Lights1()

  def test_Lights1(self):
    self.delayDisplay('Test passed!')
