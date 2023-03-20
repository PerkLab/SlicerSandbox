import os
import unittest
import logging
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

#
# SceneRecorder
#

class SceneRecorder(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Scene Recorder"
    self.parent.categories = ["Developer Tools"]
    self.parent.dependencies = []
    self.parent.contributors = ["Andras Lasso (PerkLab)"]
    # TODO: update with short description of the module and a link to online module documentation
    self.parent.helpText = """
This is a module for recording (and in the future replaying) of MRML scene changes.
"""
    self.parent.acknowledgementText = """
This file was originally developed by Andras Lasso (PerkLab).
"""

#
# SceneRecorderWidget
#

class SceneRecorderWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
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

  def setup(self):
    """
    Called when the user opens the module the first time and the widget is initialized.
    """
    ScriptedLoadableModuleWidget.setup(self)

    # Load widget from .ui file (created by Qt Designer).
    uiWidget = slicer.util.loadUI(self.resourcePath('UI/SceneRecorder.ui'))
    uiWidget.setMRMLScene(slicer.mrmlScene)
    self.layout.addWidget(uiWidget)
    self.ui = slicer.util.childWidgetVariables(uiWidget)

    self.ui.recordingTableWidget.setColumnCount(4)
    self.recordingTableColumnNames = ['Node name', 'Event type', 'Event ID', 'Node ID']
    self.ui.recordingTableWidget.setHorizontalHeaderLabels(self.recordingTableColumnNames)
    self.ui.recordingTableWidget.setSelectionBehavior(qt.QTableView.SelectRows)
    self.ui.recordingTableWidget.horizontalHeader().setSectionResizeMode(qt.QHeaderView.ResizeToContents)
    self.ui.recordingTableWidget.horizontalHeader().setStretchLastSection(True)
    #self.ui.recordingTableWidget.horizontalHeader().setSectionResizeMode(qt.QHeaderView.Stretch)
    #self.horizontalHeader().setSectionResizeMode(0, qt.QHeaderView.Interactive)
    #self.horizontalHeader().setSectionResizeMode(1, qt.QHeaderView.ResizeToContents)
    #self.horizontalHeader().setSectionResizeMode(2, qt.QHeaderView.Stretch)
    #self.horizontalScrollMode = qt.QAbstractItemView.ScrollPerPixel

    # Create logic class. Logic implements all recording operations.
    self.logic = SceneRecorderLogic()

    # Connections
    self.ui.startStopPushButton.connect('toggled(bool)', self.onStartStop)
    self.ui.clearPushButton.connect('clicked()', self.onClear)
    self.ui.recordingTableWidget.connect('itemSelectionChanged()', self.recordingEventSelectionChanged)

  def cleanup(self):
    """
    Called when the application closes and the module widget is destroyed.
    """
    pass

  def onStartStop(self, toggled):
    if toggled:
      self.logic.start()
    else:
      self.logic.stop()
      self.showRecordingResult()

  def onClear(self):
    self.logic.recordedEvents = []

  def showRecordingResult(self):
    import json
    eventCount = len(self.logic.recordedEvents)
    self.ui.recordingTableWidget.setRowCount(eventCount)
    columnNameToEventProperty = [['Node name', 'nodeName'], ['Event type', 'event'], ['Event ID', 'eventId'], ['Node ID', 'nodeId']]
    for rowIndex, eventInfo in enumerate(self.logic.recordedEvents):
      for columnName, eventProperty in columnNameToEventProperty:
        if eventProperty in eventInfo:
          text = str(eventInfo[eventProperty])
        else:
          text = ''
        self.ui.recordingTableWidget.setItem(rowIndex, self.recordingTableColumnNames.index(columnName), qt.QTableWidgetItem(text))

      widget = self.ui.recordingTableWidget.item(rowIndex, 0)
      widget.setData(qt.Qt.UserRole, json.dumps(eventInfo))

  def recordingEventSelectionChanged(self):
    import json
    details = ""
    for rowIndex in range(self.ui.recordingTableWidget.rowCount):
      widget = self.ui.recordingTableWidget.item(rowIndex, 0)
      if widget.isSelected():
        eventInfo = json.loads(widget.data(qt.Qt.UserRole))
        if eventInfo['event'] == 'NodeContentModified':
            details = 'Content changes:\n<ul>\n'
            changes = eventInfo['changes']
            for key in changes:
              details += f'<li>{key}: {changes[key]}</li>\n'
            details += '</ul>\n'
        else:
            details = json.dumps(eventInfo, indent=2)
        break
    
    self.ui.eventDetailsTextEdit.html = details


#
# SceneRecorderLogic
#

class SceneRecorderLogic(ScriptedLoadableModuleLogic):
  """This class should implement all the actual
  computation done by your module.  The interface
  should be such that other python code can import
  this class and make use of the functionality without
  requiring an instance of the Widget.
  Uses ScriptedLoadableModuleLogic base class, available at:
  https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self):
    """
    Called when the logic class is instantiated. Can be used for initializing member variables.
    """
    ScriptedLoadableModuleLogic.__init__(self)
    self.observations = []
    self.recordedEvents = []
    self.nodePreviousState = {}

  def __del__(self):
    self.removeObservers()

  @staticmethod
  def nodeProperties(nodeStr):
      lines = nodeStr.split('\n')
      keys = []
      key = ''
      value = ''
      content = {}
      previousIndentLevel = 0
      for line in lines:
          try:
              if line.lstrip() == '':
                  continue
              currentIndentLevel = len(line)-len(line.lstrip())  # how many leading spaces
              if currentIndentLevel == 0:
                  # first line (contains class name and pointer, not interesting)
                  continue
              if currentIndentLevel>previousIndentLevel:
                  keys.append(key)  # use last key as prefix
                  previousIndentLevel = currentIndentLevel
              elif currentIndentLevel<previousIndentLevel:
                  keys.pop()  # remove last prefix
                  previousIndentLevel = currentIndentLevel
              try:
                  [key, value] = line.split(':', maxsplit=1)
                  key = key.lstrip()
                  value = value.lstrip()
                  content['/'.join(keys+[key])] = value
              except ValueError:
                  # no label it is just content
                  if '/'.join(keys+[key]) in content:
                    content['/'.join(keys+[key])] += '\n' + line.strip()
                  else:
                    content['/'.join(keys + [key])] = line.strip()
          except:
              import traceback
              traceback.print_exc() 
              print(f"Failed to parse line: '{line}'")
      if key:
          content[key] = value
      return content
  
  @staticmethod
  def dictCompare(d1, d2):
      d1_keys = set(d1.keys())
      d2_keys = set(d2.keys())
      shared_keys = d1_keys.intersection(d2_keys)
      added = d1_keys - d2_keys
      removed = d2_keys - d1_keys
      modified = {o : (d1[o], d2[o]) for o in shared_keys if d1[o] != d2[o]}
      same = set(o for o in shared_keys if d1[o] == d2[o])
      for key in ['/MTime', 'Reference Count']:
          if key in shared_keys:
              shared_keys.remove(key)
          if key in added:
              added.remove(key)
          if key in removed:
              removed.remove(key)
          if key in modified:
              del modified[key]
          if key in same:
              same.remove(key)
      return added, removed, modified, same

  @staticmethod
  def nodePropertiesDifference(previousState, currentState):
      added, removed, modified, same = SceneRecorderLogic.dictCompare(currentState, previousState)
      stateChange = {}
      for key in modified:
          stateChange[key] = currentState[key]
      for key in added:
          stateChange[key] = currentState[key]
      for key in removed:
          stateChange[key] = ''
      return stateChange    

  @vtk.calldata_type(vtk.VTK_OBJECT)
  def onNodeAdded(self, node, event, calldata):
      node = calldata
      self.addNodeObserver(node)
      event = {'event': 'NodeAdded', 'nodeId': node.GetID()}
      self.recordedEvents.append(event)
  
  @vtk.calldata_type(vtk.VTK_OBJECT)
  def onNodeRemoved(self, node, event, calldata):
      node = calldata
      self.removeNodeObserver(node)
      event = {'event': 'NodeRemoved', 'nodeId': node.GetID()}
      self.recordedEvents.append(event)

  def onNodeContentModified(self, node, eventId):
      currentState = SceneRecorderLogic.nodeProperties(node.__str__())
      if repr(node) in self.nodePreviousState:
          previousState = self.nodePreviousState[repr(node)]
          changes = SceneRecorderLogic.nodePropertiesDifference(previousState, currentState)
          if not changes:
              # properties did not change (either properties have not been changed or they were just not printed)
              return
          event = {
              'event': 'NodeContentModified',
              'nodeId': node.GetID(),
              'nodeClassName': node.GetClassName(),
              'nodeName': node.GetName(),
              'eventId': eventId,
              'changes': changes}
          self.recordedEvents.append(event)
      self.nodePreviousState[repr(node)] = currentState
  
  def removeObservers(self):
      for observation in self.observations:
          observation[0].RemoveObserver(observation[1])
      self.observations = []

  def addNodeObserver(self, node):
      contentModifiedEvents = node.GetContentModifiedEvents()
      for eventIndex in range(contentModifiedEvents.GetNumberOfValues()):
          eventId = contentModifiedEvents.GetValue(eventIndex)
          self.observations.append(
              [node, node.AddObserver(eventId, lambda node, eventIdStr, eventId=eventId: self.onNodeContentModified(node, eventId))])
  
  def removeNodeObserver(self, node):
      remainingObservations = []
      for observation in self.observations:
          if observation[0] == node:
              observation[0].RemoveObserver(observation[1])
          else:
              remainingObservations.append(observation)
      self.observations = remainingObservations
      
  def addObservers(self):
      self.removeObservers()
      # observe scene events
      self.observations.append([slicer.mrmlScene, slicer.mrmlScene.AddObserver(slicer.vtkMRMLScene.NodeAddedEvent, self.onNodeAdded)])
      self.observations.append([slicer.mrmlScene, slicer.mrmlScene.AddObserver(slicer.vtkMRMLScene.NodeRemovedEvent, self.onNodeAdded)])
      #self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
      #self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)
      #self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndImportEvent, self.onSceneEndImport)
      observedNodes = slicer.util.getNodesByClass('vtkMRMLNode')
      for observedNode in observedNodes:
          self.addNodeObserver(observedNode)

  def start(self):

      # Save current state of all nodes (changes will be recorded relative to this)
      observedNodes = slicer.util.getNodesByClass('vtkMRMLNode')
      for node in observedNodes:
          currentState = SceneRecorderLogic.nodeProperties(node.__str__())
          self.nodePreviousState[repr(node)] = currentState

      self.addObservers()
      
  def stop(self):
      self.removeObservers()

#
# SceneRecorderTest
#

class SceneRecorderTest(ScriptedLoadableModuleTest):
  """
  This is the test case for your scripted module.
  Uses ScriptedLoadableModuleTest base class, available at:
  https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def setUp(self):
    """ Do whatever is needed to reset the state - typically a scene clear will be enough.
    """
    slicer.mrmlScene.Clear()

  def runTest(self):
    """Run as few or as many tests as needed here.
    """
    self.setUp()
    self.test_SceneRecorder1()

  def test_SceneRecorder1(self):
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
    registerSampleData()
    inputVolume = SampleData.downloadSample('SceneRecorder1')
    self.delayDisplay('Loaded test data set')

    inputScalarRange = inputVolume.GetImageData().GetScalarRange()
    self.assertEqual(inputScalarRange[0], 0)
    self.assertEqual(inputScalarRange[1], 695)

    outputVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
    threshold = 100

    # Test the module logic

    logic = SceneRecorderLogic()

    # Test algorithm with non-inverted threshold
    logic.process(inputVolume, outputVolume, threshold, True)
    outputScalarRange = outputVolume.GetImageData().GetScalarRange()
    self.assertEqual(outputScalarRange[0], inputScalarRange[0])
    self.assertEqual(outputScalarRange[1], threshold)

    # Test algorithm with inverted threshold
    logic.process(inputVolume, outputVolume, threshold, False)
    outputScalarRange = outputVolume.GetImageData().GetScalarRange()
    self.assertEqual(outputScalarRange[0], inputScalarRange[0])
    self.assertEqual(outputScalarRange[1], inputScalarRange[1])

    self.delayDisplay('Test passed')
