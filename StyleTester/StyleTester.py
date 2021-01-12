import os
import unittest
import logging
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

#
# StyleTester
#

class StyleTester(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "StyleTester"  # TODO: make this more human readable by adding spaces
    self.parent.categories = ["Developer Tools"]  # TODO: set categories (folders where the module shows up in the module selector)
    self.parent.dependencies = []  # TODO: add here list of module names that this module requires
    self.parent.contributors = ["Sam Horvath (Kitware, Inc"]  # TODO: replace with "Firstname Lastname (Organization)"
    # TODO: update with short description of the module and a link to online module documentation
    self.parent.helpText = """
This is a utility module for editing/testing QSS styling with 3D Slicer.
You can find the details for QSS <a href="https://doc.qt.io/Qt-5/stylesheet.html">on the Qt website</a>.
<br><br>
Load - load an existing .qss file into the editor <br>
Save - save the contents of the editor to a .qss file <br>
Apply - apply the stylesheet in the editor to the selected target (examples or all of Slicer) <br>
Clear - clear the stylesheet from the selected target <br>
<br>
The examples section includes the most widely used widgets, each with a checkbox that controls
the enabled/disabled state, allowing testing of state-based styling. <br>
<br>
When testing stylesheets, check the Slicer error log for Qt related messages if things go wrong. <br>
"""
    # TODO: replace with organization, grant and thanks
    self.parent.acknowledgementText = """
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
"""

    



#
# StyleTesterWidget
#

class StyleTesterWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
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

  def setup(self):
    """
    Called when the user opens the module the first time and the widget is initialized.
    """
    ScriptedLoadableModuleWidget.setup(self)

    # Load widget from .ui file (created by Qt Designer).
    # Additional widgets can be instantiated manually and added to self.layout.
    uiWidget = slicer.util.loadUI(self.resourcePath('UI/StyleTester.ui'))
    self.layout.addWidget(uiWidget)
    self.ui = slicer.util.childWidgetVariables(uiWidget)

    # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
    # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
    # "setMRMLScene(vtkMRMLScene*)" slot.
    uiWidget.setMRMLScene(slicer.mrmlScene)

    # Create logic class. Logic implements all computations that should be possible to run
    # in batch mode, without a graphical user interface.
    self.logic = StyleTesterLogic()

    # Connections
    self.ui.applyButton.clicked.connect(self.onApply)
    self.ui.clearButton.clicked.connect(self.onClear)
    self.ui.loadButton.clicked.connect(self.onLoad)
    self.ui.saveButton.clicked.connect(self.onSave)

  def onLoad(self):
    fileDialog = qt.QFileDialog(self.parent)
    fileDialog.options = fileDialog.DontUseNativeDialog
    fileDialog.acceptMode = fileDialog.AcceptOpen
    fileDialog.fileMode = fileDialog.ExistingFile    
    fileDialog.defaultSuffix = "qss"
    fileDialog.setNameFilter("Qt Style Sheet (*.qss)")
    fileDialog.connect("fileSelected(QString)", self.onLoadFileSelected)
    fileDialog.show()

  def onSave(self):
    saveDialog = qt.QFileDialog(self.parent)
    saveDialog.options = saveDialog.DontUseNativeDialog
    saveDialog.acceptMode = saveDialog.AcceptSave
    saveDialog.defaultSuffix = "qss"
    saveDialog.setNameFilter("Qt Style Sheet (*.qss)")
    saveDialog.connect("fileSelected(QString)", self.onSaveFileSelected)
    saveDialog.show()
    
  
  def onLoadFileSelected(self, stylesheetfile):
    with open(stylesheetfile,"r") as fh:
      self.ui.plainTextEdit.plainText = fh.read()

  def onSaveFileSelected(self, stylesheetfile):
    with open(stylesheetfile,"w") as fh:
      fh.write( self.ui.plainTextEdit.plainText)
  
  def onApply(self):
    styleSheet = self.ui.plainTextEdit.plainText
    if self.ui.slicerRadio.isChecked():
      slicer.app.styleSheet = styleSheet
    else:
      self.ui.Examples.setStyleSheet(styleSheet)

  def onClear(self):
    if self.ui.slicerRadio.isChecked():
      slicer.app.styleSheet = ""
    else:
      self.ui.Examples.setStyleSheet("")
  
  def cleanup(self):
    """
    Called when the application closes and the module widget is destroyed.
    """
    self.removeObservers()

  def enter(self):
    """
    Called each time the user opens this module.
    """
    pass
  def exit(self):
    """
    Called each time the user opens a different module.
    """
    pass

  def onSceneStartClose(self, caller, event):
    """
    Called just before the scene is closed.
    """
    pass

  def onSceneEndClose(self, caller, event):
    """
    Called just after the scene is closed.
    """
    pass

  


#
# StyleTesterLogic
#

class StyleTesterLogic(ScriptedLoadableModuleLogic):
  """This class should implement all the actual
  computation done by your module.  The interface
  should be such that other python code can import
  this class and make use of the functionality without
  requiring an instance of the Widget.
  Uses ScriptedLoadableModuleLogic base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self):
    """
    Called when the logic class is instantiated. Can be used for initializing member variables.
    """
    ScriptedLoadableModuleLogic.__init__(self)

 

#
# StyleTesterTest
#

class StyleTesterTest(ScriptedLoadableModuleTest):
  """
  This is the test case for your scripted module.
  Uses ScriptedLoadableModuleTest base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def setUp(self):
    """ Do whatever is needed to reset the state - typically a scene clear will be enough.
    """
    slicer.mrmlScene.Clear()

  def runTest(self):
    """Run as few or as many tests as needed here.
    """
    self.setUp()
    self.test_StyleTester1()

  def test_StyleTester1(self):
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

    

    self.delayDisplay('Test passed')
