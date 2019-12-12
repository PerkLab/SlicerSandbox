import os
import unittest
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
import logging
from slicer.util import VTKObservationMixin, NodeModify
import math
import time

#
# AutoSave
#

class AutoSave(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Auto Save"
    self.parent.categories = ["Utilities"]
    self.parent.dependencies = []
    self.parent.contributors = ["Kyle Sunderland (Perk Lab, Queen's University)"]
    self.parent.helpText = """
This is a module that can automatically save the Slicer scene.
"""
    self.parent.helpText += self.getDefaultModuleDocumentationLink()
    self.parent.acknowledgementText = """
This file was originally developed by Kyle Sunderland (Perk Lab, Queen's University), and was partially funded by CANARIE's Research Software Program, OpenAnatomy, and Brigham and Women's Hospital through NIH grant R01MH112748
"""

#
# AutoSaveWidget
#

class AutoSaveWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
  """Uses ScriptedLoadableModuleWidget base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModuleWidget.__init__(self, parent)
    VTKObservationMixin.__init__(self)

  def setup(self):
    ScriptedLoadableModuleWidget.setup(self)

    # Load widget from .ui file (created by Qt Designer)
    uiWidget = slicer.util.loadUI(self.resourcePath('UI/AutoSave.ui'))
    self.layout.addWidget(uiWidget)
    self.ui = slicer.util.childWidgetVariables(uiWidget)

    # Add vertical spacer
    self.layout.addStretch(1)

    # Connect observers to scene events
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndImportEvent, self.onSceneEndImport)

    self.logic = AutoSaveLogic()
    self.ui.enabledCheckBox.stateChanged.connect(self.updateMRMLFromWidget)
    self.ui.hoursSpinBox.valueChanged.connect(self.updateMRMLFromWidget)
    self.ui.minutesSpinBox.valueChanged.connect(self.updateMRMLFromWidget)
    self.ui.secondsSpinBox.valueChanged.connect(self.updateMRMLFromWidget)
    self.ui.directoryButton.directoryChanged.connect(self.updateMRMLFromWidget)
    self.updateParameterNode()

  def onSceneEndClose(self, caller, event):
    self.updateParameterNode()

  def onSceneEndImport(self, caller, event):
    self.updateParameterNode()

  def updateParameterNode(self):
    parameterNode = self.logic.getParameterNode()
    if self.hasObserver(parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateWidgetFromMRML):
      return
    self.addObserver(parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateWidgetFromMRML)
    self.updateWidgetFromMRML()

  @vtk.calldata_type(vtk.VTK_OBJECT)
  def updateWidgetFromMRML(self, caller=None, eventId=None, callData=None):
    wasBlocking = self.ui.enabledCheckBox.blockSignals(True)
    self.ui.enabledCheckBox.checked = self.logic.getAutoSaveEnabled()
    self.ui.enabledCheckBox.blockSignals(wasBlocking)

    intervalSeconds = self.logic.getIntervalSeconds()
    wasBlocking = self.ui.secondsSpinBox.blockSignals(True)
    self.ui.secondsSpinBox.value = intervalSeconds % 60
    self.ui.secondsSpinBox.blockSignals(wasBlocking)

    intervalMinutes = intervalSeconds / 60
    wasBlocking = self.ui.minutesSpinBox.blockSignals(True)
    self.ui.minutesSpinBox.value = intervalMinutes % 60
    self.ui.minutesSpinBox.blockSignals(wasBlocking)

    intervalHours = intervalMinutes / 60
    wasBlocking = self.ui.hoursSpinBox.blockSignals(True)
    self.ui.hoursSpinBox.value = intervalHours % 60
    self.ui.hoursSpinBox.blockSignals(wasBlocking)

    wasBlocking = self.ui.directoryButton.blockSignals(True)
    self.ui.directoryButton.directory = self.logic.getSaveDirectory()
    self.ui.directoryButton.blockSignals(wasBlocking)

  def updateMRMLFromWidget(self):
    self.logic.setAutoSaveEnabled(self.ui.enabledCheckBox.checked)
    intervalHours = self.ui.hoursSpinBox.value
    intervalMinutes = (60 * intervalHours) + self.ui.minutesSpinBox.value
    intervalSeconds = (60 * intervalMinutes) + self.ui.secondsSpinBox.value
    self.logic.setIntervalSeconds(intervalSeconds)
    self.logic.setSaveDirectory(self.ui.directoryButton.directory)

  def cleanup(self):
    self.removeObservers()
    self.logic.cleanup()

#
# AutoSaveLogic
#

class AutoSaveLogic(ScriptedLoadableModuleLogic, VTKObservationMixin):
  """This class should implement all the actual
  computation done by your module.  The interface
  should be such that other python code can import
  this class and make use of the functionality without
  requiring an instance of the Widget.
  Uses ScriptedLoadableModuleLogic base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  AUTO_SAVE_ENABLED_PARAMETER_NAME = "AutoSaveEnabled"
  AUTO_SAVE_INTERVAL = "AutoSaveInterval"
  AUTO_SAVE_INTERVAL_SECONDS_PARAMETER_NAME = "AutoSaveIntervalSeconds"
  AUTO_SAVE_DIRECTORY_PARAMETER_NAME = "AutoSaveDirectory"


  def __init__(self, parent=None):
    ScriptedLoadableModuleLogic.__init__(self, parent)
    VTKObservationMixin.__init__(self)
    self.autoSaveTimer = qt.QTimer()
    self.autoSaveTimer.timeout.connect(self.onAutoSaveTimeout)

  def cleanup(self):
    self.removeObservers()
    self.autoSaveTimer.stop()

  def getParameterNode(self):
    parameterNode = ScriptedLoadableModuleLogic.getParameterNode(self)
    if parameterNode is None:
      return parameterNode
    if not self.hasObserver(parameterNode, vtk.vtkCommand.ModifiedEvent, self.onParameterNodeModified):
      self.setDefaultParameters(parameterNode)
      self.addObserver(parameterNode, vtk.vtkCommand.ModifiedEvent, self.onParameterNodeModified)
      self.onParameterNodeModified()
    return parameterNode

  @vtk.calldata_type(vtk.VTK_OBJECT)
  def onParameterNodeModified(self, caller=None, eventId=None, callData=None):
    intervalMilliseconds = self.getIntervalSeconds() * 1000
    self.autoSaveTimer.setInterval(intervalMilliseconds)
    if self.autoSaveTimer.active and not self.getAutoSaveEnabled():
      self.autoSaveTimer.stop()
    elif (not self.autoSaveTimer.active) and self.getAutoSaveEnabled():
      self.autoSaveTimer.start()

  def onAutoSaveTimeout(self):
    # Generate file name
    sceneSaveFilename = self.getSaveDirectory() + "/" + time.strftime("%Y%m%d-%H%M%S") + ".mrb"
    print(sceneSaveFilename)
    # Save scene
    if slicer.util.saveScene(sceneSaveFilename):
      logging.info("Scene saved to: {0}".format(sceneSaveFilename))
    else:
      logging.error("Scene saving failed")

  def setDefaultParameters(self, parameterNode):
    if parameterNode is None:
      return
    if not parameterNode.GetParameter(self.AUTO_SAVE_ENABLED_PARAMETER_NAME):
      parameterNode.SetParameter(self.AUTO_SAVE_ENABLED_PARAMETER_NAME, str(False))
    if not parameterNode.GetParameter(self.AUTO_SAVE_INTERVAL_SECONDS_PARAMETER_NAME):
      parameterNode.SetParameter(self.AUTO_SAVE_INTERVAL_SECONDS_PARAMETER_NAME, str(1800))
    if not parameterNode.GetParameter(self.AUTO_SAVE_DIRECTORY_PARAMETER_NAME):
      parameterNode.SetParameter(self.AUTO_SAVE_DIRECTORY_PARAMETER_NAME, slicer.app.temporaryPath+"/AutoSave")

  def getAutoSaveEnabled(self):
    parameterNode = self.getParameterNode()
    if parameterNode is None:
      return False
    return parameterNode.GetParameter(self.AUTO_SAVE_ENABLED_PARAMETER_NAME) == str(True)

  def setAutoSaveEnabled(self, enabled):
    parameterNode = self.getParameterNode()
    if parameterNode is None:
      return
    parameterNode.SetParameter(self.AUTO_SAVE_ENABLED_PARAMETER_NAME, str(enabled))

  def getIntervalSeconds(self):
    parameterNode = self.getParameterNode()
    if parameterNode is None:
      return 0
    return int(parameterNode.GetParameter(self.AUTO_SAVE_INTERVAL_SECONDS_PARAMETER_NAME))

  def setIntervalSeconds(self, seconds):
    parameterNode = self.getParameterNode()
    if parameterNode is None:
      return
    seconds = max(seconds, 1) # Minimum autosave interval is 1 seconds
    parameterNode.SetParameter(self.AUTO_SAVE_INTERVAL_SECONDS_PARAMETER_NAME, str(seconds))

  def setInterval(self, hours, minutes, seconds):
    intervalMinutes = (hours * 60) + minutes
    intervalSeconds = (minutes * 60) + seconds
    self.setIntervalSeconds(seconds)

  def getSaveDirectory(self):
    parameterNode = self.getParameterNode()
    if parameterNode is None:
      return ""
    return str(parameterNode.GetParameter(self.AUTO_SAVE_DIRECTORY_PARAMETER_NAME))

  def setSaveDirectory(self, saveDirectory):
    parameterNode = self.getParameterNode()
    if parameterNode is None:
      return
    parameterNode.SetParameter(self.AUTO_SAVE_DIRECTORY_PARAMETER_NAME, saveDirectory)

class AutoSaveTest(ScriptedLoadableModuleTest):
  """
  This is the test case for your scripted module.
  Uses ScriptedLoadableModuleTest base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def runTest(self):
    """Run as few or as many tests as needed here.
    """
    self.setUp()
