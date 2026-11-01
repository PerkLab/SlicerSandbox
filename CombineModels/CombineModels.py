import os
import unittest
import logging
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
from slicer.i18n import tr as _
from slicer.i18n import translate
from slicer.util import VTKObservationMixin

#
# CombineModels
#

class CombineModels(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Combine Models"
    self.parent.categories = ["Surface Models"]
    self.parent.dependencies = []
    self.parent.contributors = ["Andras Lasso (PerkLab)"]
    self.parent.helpText = """
This module can perform Boolean operations on model nodes (surface meshes).
The default backend is kigumi, which computes exact results; vtkbool and octree can be selected in the Advanced section.
Input models must be closed, manifold, consistently oriented surfaces without degenerate or self-intersecting faces.
The Input check section finds such problems before the result is computed, and shows where they are.
The octree backend computes the result on voxels, so it only needs closed inputs, but it rounds sharp edges
and loses features thinner than a voxel. Overlapping parts of one model cancel out with it.
"""
    # TODO: replace with organization, grant and thanks
    self.parent.acknowledgementText = """
The module uses https://github.com/unageek/kigumi and https://github.com/zippy84/vtkbool for processing.
The octree backend uses VTK.
"""

    for subfolder in ['Release', 'Debug', 'RelWithDebInfo', 'MinSizeRel', '.']:
      logicPath = os.path.realpath(os.path.join(os.path.dirname(__file__), '../qt-loadable-modules/'+subfolder)).replace('\\','/')
      if os.path.exists(logicPath):
        import sys
        sys.path.append(logicPath)
        break

#
# CombineModelsWidget
#

class CombineModelsWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
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
    self._updatingGUIFromParameterNode = False
    # Widgets of the further steps, one dict per step
    self._stepWidgets = []
    # Inputs and settings of the last input check, see _checkSettings()
    self._checkedSettings = None

  def setup(self):
    """
    Called when the user opens the module the first time and the widget is initialized.
    """
    ScriptedLoadableModuleWidget.setup(self)

    # Load widget from .ui file (created by Qt Designer).
    # Additional widgets can be instantiated manually and added to self.layout.
    uiWidget = slicer.util.loadUI(self.resourcePath('UI/CombineModels.ui'))
    self.layout.addWidget(uiWidget)
    self.ui = slicer.util.childWidgetVariables(uiWidget)

    # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
    # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
    # "setMRMLScene(vtkMRMLScene*)" slot.
    uiWidget.setMRMLScene(slicer.mrmlScene)

    # Create logic class. Logic implements all computations that should be possible to run
    # in batch mode, without a graphical user interface.
    self.logic = CombineModelsLogic()

    # Connections

    # These connections ensure that we update parameter node when scene is closed
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
    self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

    # These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
    # (in the selected parameter node).
    self.ui.inputModelASelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
    self.ui.inputModelBSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
    self.ui.outputModelSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)

    self.ui.operationUnionRadioButton.connect("toggled(bool)", lambda toggled, op="union": self.operationButtonToggled(op))
    self.ui.operationIntersectionRadioButton.connect("toggled(bool)", lambda toggled, op="intersection": self.operationButtonToggled(op))
    self.ui.operationDifferenceRadioButton.connect("toggled(bool)", lambda toggled, op="difference": self.operationButtonToggled(op))
    self.ui.operationDifference2RadioButton.connect("toggled(bool)", lambda toggled, op="difference2": self.operationButtonToggled(op))

    self.ui.triangulateInputsCheckBox.connect("stateChanged(int)", self.updateParameterNodeFromGUI)

    # Input check
    self.ui.checkInputsBeforeApplyCheckBox.connect("stateChanged(int)", self.updateParameterNodeFromGUI)
    self.ui.showDefectsCheckBox.connect("stateChanged(int)", self.updateParameterNodeFromGUI)
    self.ui.checkInputsButton.connect('clicked(bool)', self.onCheckInputsButton)
    self.ui.checkResultsLabel.visible = False

    for backend in self.logic.availableBackends():
      self.ui.backendComboBox.addItem(backend)
    self.ui.backendComboBox.currentTextChanged.connect(self.updateParameterNodeFromGUI)

    # Spin Boxes
    self.ui.numberOfRetriesSpinBox.valueChanged.connect(self.updateParameterNodeFromGUI)
    self.ui.randomTranslationMagnitudeSpinBox.valueChanged.connect(self.updateParameterNodeFromGUI)
    self.ui.octreeVoxelSizeSpinBox.valueChanged.connect(self.updateParameterNodeFromGUI)
    self.ui.octreeExtraLevelsSpinBox.valueChanged.connect(self.updateParameterNodeFromGUI)

    # Further steps
    self.ui.addStepButton.connect('clicked(bool)', self.onAddStepButton)
    if not self.logic.stepBackends():
      self.ui.addStepButton.enabled = False
      self.ui.addStepButton.toolTip = "Further steps require the kigumi or octree backend, which are not available in this build"

    # Buttons
    self.ui.applyButton.connect('clicked(bool)', self.onApplyButton)
    self.ui.toggleVisibilityButton.connect('clicked(bool)', self.onToggleVisibilityButton)

    # Make sure parameter node is initialized (needed for module reload)
    self.initializeParameterNode()

  def cleanup(self):
    """
    Called when the application closes and the module widget is destroyed.
    """
    self.removeObservers()

  def enter(self):
    """
    Called each time the user opens this module.
    """
    # Make sure parameter node exists and observed
    self.initializeParameterNode()

  def exit(self):
    """
    Called each time the user opens a different module.
    """
    # Do not react to parameter node changes (GUI wlil be updated when the user enters into the module)
    self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

  def onSceneStartClose(self, caller, event):
    """
    Called just before the scene is closed.
    """
    # Parameter node will be reset, do not use it anymore
    self.setParameterNode(None)

  def onSceneEndClose(self, caller, event):
    """
    Called just after the scene is closed.
    """
    # If this module is shown while the scene is closed then recreate a new parameter node immediately
    if self.parent.isEntered:
      self.initializeParameterNode()

  def initializeParameterNode(self):
    """
    Ensure parameter node exists and observed.
    """
    # Parameter node stores all user choices in parameter values, node selections, etc.
    # so that when the scene is saved and reloaded, these settings are restored.

    self.setParameterNode(self.logic.getParameterNode())

  def setParameterNode(self, inputParameterNode):
    """
    Set and observe parameter node.
    Observation is needed because when the parameter node is changed then the GUI must be updated immediately.
    """

    if inputParameterNode:
      self.logic.setDefaultParameters(inputParameterNode)

    # Unobserve previously selected parameter node and add an observer to the newly selected.
    # Changes of parameter node are observed so that whenever parameters are changed by a script or any other module
    # those are reflected immediately in the GUI.
    if self._parameterNode is not None:
      self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
    self._parameterNode = inputParameterNode
    if self._parameterNode is not None:
      self.addObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

    # Initial GUI update
    self.updateGUIFromParameterNode()

  def updateGUIFromParameterNode(self, caller=None, event=None):
    """
    This method is called whenever parameter node is changed.
    The module GUI is updated to show the current state of the parameter node.
    """

    if self._parameterNode is None or self._updatingGUIFromParameterNode:
      return

    # Make sure GUI changes do not call updateParameterNodeFromGUI (it could cause infinite loop)
    self._updatingGUIFromParameterNode = True

    # Update node selectors and sliders
    self.ui.inputModelASelector.setCurrentNode(self._parameterNode.GetNodeReference("InputModelA"))
    self.ui.inputModelBSelector.setCurrentNode(self._parameterNode.GetNodeReference("InputModelB"))
    self.ui.outputModelSelector.setCurrentNode(self._parameterNode.GetNodeReference("OutputModel"))

    operation = self._parameterNode.GetParameter("Operation")
    self.ui.operationUnionRadioButton.checked = (operation == "union")
    self.ui.operationIntersectionRadioButton.checked = (operation == "intersection")
    self.ui.operationDifferenceRadioButton.checked = (operation == "difference")
    self.ui.operationDifference2RadioButton.checked = (operation == "difference2")

    # Update further steps
    numberOfSteps = self._numberOfSteps()
    if len(self._stepWidgets) != numberOfSteps:
      self._createStepWidgets(numberOfSteps)
    for stepIndex, stepWidgets in enumerate(self._stepWidgets):
      operationComboBox = stepWidgets["operation"]
      operationComboBox.setCurrentIndex(max(0, operationComboBox.findData(self._parameterNode.GetParameter(f"StepOperation{stepIndex}"))))
      stepWidgets["model"].setCurrentNode(self._parameterNode.GetNodeReference(f"StepModel{stepIndex}"))
    self.ui.stepsSummaryLabel.text = self._stepsSummary() if numberOfSteps > 0 else ""
    self.ui.stepsSummaryLabel.visible = numberOfSteps > 0

    # Update buttons states and tooltips
    stepModelsSelected = all(self._parameterNode.GetNodeReference(f"StepModel{stepIndex}") for stepIndex in range(numberOfSteps))
    if not (self._parameterNode.GetNodeReference("InputModelA")
      and self._parameterNode.GetNodeReference("InputModelB")
      and stepModelsSelected):
      self.ui.applyButton.toolTip = "Select input model nodes"
      self.ui.applyButton.enabled = False
    elif numberOfSteps > 0 and self._parameterNode.GetParameter("Backend") not in self.logic.stepBackends():
      self.ui.applyButton.toolTip = "Further steps require the kigumi or octree backend (see Advanced section)"
      self.ui.applyButton.enabled = False
    else:
      self.ui.applyButton.toolTip = "Compute output model"
      self.ui.applyButton.enabled = True

    self.ui.toggleVisibilityButton.enabled = (self._parameterNode.GetNodeReference("OutputModel") is not None)

    self.ui.checkInputsButton.enabled = any(self._inputModels())
    self.ui.checkInputsBeforeApplyCheckBox.checked = self._parameterNode.GetParameter("CheckInputsBeforeApply") == "True"
    self.ui.showDefectsCheckBox.checked = self._parameterNode.GetParameter("ShowDefects") == "True"
    # Results of the last input check do not apply after the inputs or settings changed
    if self._checkedSettings != self._checkSettings():
      self.ui.checkResultsLabel.visible = False

    # translate randomly order of magnitude (value is negative by default)
    randomTranslationMagnitude = int(float(self._parameterNode.GetParameter("randomTranslationMagnitude")))
    self.ui.randomTranslationMagnitudeSpinBox.value = randomTranslationMagnitude

    numberOfRetries = int(self._parameterNode.GetParameter("numberOfRetries"))
    self.ui.numberOfRetriesSpinBox.value = numberOfRetries
    octreeBackend = self._parameterNode.GetParameter("Backend") == "octree"
    self.ui.numberOfRetriesSpinBox.enabled = numberOfSteps == 0 and not octreeBackend
    if octreeBackend:
      self.ui.numberOfRetriesSpinBox.toolTip = "Not used by the octree backend, which does not fail on intersecting models"
      self.ui.randomTranslationMagnitudeSpinBox.enabled = False
      self.ui.randomTranslationMagnitudeSpinBox.toolTip = "Not used by the octree backend, which does not fail on intersecting models"
    elif numberOfSteps > 0:
      self.ui.numberOfRetriesSpinBox.toolTip = "Not used with further steps, which are computed exactly"
      self.ui.randomTranslationMagnitudeSpinBox.enabled = False
      self.ui.randomTranslationMagnitudeSpinBox.toolTip = "Not used with further steps, which are computed exactly"
    elif numberOfRetries > 0:
      self.ui.numberOfRetriesSpinBox.toolTip = "Model B will be randomized if operation fails"
      self.ui.randomTranslationMagnitudeSpinBox.enabled = True
      randomTranslationAmount = 10**-randomTranslationMagnitude
      self.ui.randomTranslationMagnitudeSpinBox.toolTip = f"If the operation fails, it will retry with a random translation of {randomTranslationAmount}"
    else:
      self.ui.numberOfRetriesSpinBox.toolTip = "Computation will be attempted only with exact inputs."
      self.ui.randomTranslationMagnitudeSpinBox.enabled = False
      self.ui.randomTranslationMagnitudeSpinBox.toolTip = "Set a number of retries to larger than 0"

    self.ui.triangulateInputsCheckBox.checked = self._parameterNode.GetParameter("triangulateInputs") == "True"

    self.ui.backendComboBox.setCurrentText(self._parameterNode.GetParameter("Backend"))

    self.ui.octreeGroupBox.visible = octreeBackend
    self.ui.octreeVoxelSizeSpinBox.value = float(self._parameterNode.GetParameter("OctreeVoxelSize"))
    self.ui.octreeExtraLevelsSpinBox.value = int(self._parameterNode.GetParameter("OctreeExtraLevels"))

    # All the GUI updates are done
    self._updatingGUIFromParameterNode = False

  def updateParameterNodeFromGUI(self, caller=None, event=None):
    """
    This method is called when the user makes any change in the GUI.
    The changes are saved into the parameter node (so that they are restored when the scene is saved and loaded).
    """

    if self._parameterNode is None or self._updatingGUIFromParameterNode:
      return

    wasModified = self._parameterNode.StartModify()  # Modify all properties in a single batch

    self._parameterNode.SetNodeReferenceID("InputModelA", self.ui.inputModelASelector.currentNodeID)
    self._parameterNode.SetNodeReferenceID("InputModelB", self.ui.inputModelBSelector.currentNodeID)
    self._parameterNode.SetNodeReferenceID("OutputModel", self.ui.outputModelSelector.currentNodeID)

    self._parameterNode.SetParameter("numberOfRetries", str(self.ui.numberOfRetriesSpinBox.value))
    self._parameterNode.SetParameter("randomTranslationMagnitude", str(self.ui.randomTranslationMagnitudeSpinBox.value))

    self._parameterNode.SetParameter("triangulateInputs", "True" if self.ui.triangulateInputsCheckBox.checked else "False")

    self._parameterNode.SetParameter("Backend", self.ui.backendComboBox.currentText)
    self._parameterNode.SetParameter("OctreeVoxelSize", str(self.ui.octreeVoxelSizeSpinBox.value))
    self._parameterNode.SetParameter("OctreeExtraLevels", str(self.ui.octreeExtraLevelsSpinBox.value))

    self._parameterNode.SetParameter("CheckInputsBeforeApply", "True" if self.ui.checkInputsBeforeApplyCheckBox.checked else "False")
    self._parameterNode.SetParameter("ShowDefects", "True" if self.ui.showDefectsCheckBox.checked else "False")

    for stepIndex, stepWidgets in enumerate(self._stepWidgets):
      self._parameterNode.SetParameter(f"StepOperation{stepIndex}", stepWidgets["operation"].currentData)
      self._parameterNode.SetNodeReferenceID(f"StepModel{stepIndex}", stepWidgets["model"].currentNodeID)

    self._parameterNode.EndModify(wasModified)

  def _numberOfSteps(self):
    return int(self._parameterNode.GetParameter("NumberOfAdditionalSteps") or 0)

  def _inputModels(self):
    """Input models A, B and those of the further steps, None where no model is selected."""
    return ([self._parameterNode.GetNodeReference("InputModelA"), self._parameterNode.GetNodeReference("InputModelB")]
      + [self._parameterNode.GetNodeReference(f"StepModel{stepIndex}") for stepIndex in range(self._numberOfSteps())])

  def _checkBackend(self):
    """Backend that computes the result."""
    return self._parameterNode.GetParameter("Backend")

  def _checkSettings(self):
    """Inputs and settings that the results of the input check depend on."""
    return (
      tuple(inputModel.GetID() if inputModel else None for inputModel in self._inputModels()),
      self._parameterNode.GetNodeReferenceID("OutputModel"),
      self._checkBackend(),
      self._parameterNode.GetParameter("triangulateInputs"),
      self._parameterNode.GetParameter("ShowDefects"))

  def _checkInputs(self):
    """Check the selected input models, show the results, and return them."""
    results = self.logic.checkInputs(
      [inputModel for inputModel in self._inputModels() if inputModel],
      self._parameterNode.GetNodeReference("OutputModel"),
      self._checkBackend(),
      self._parameterNode.GetParameter("triangulateInputs") == "True",
      self._parameterNode.GetParameter("ShowDefects") == "True")
    self._checkedSettings = self._checkSettings()
    self.ui.checkResultsLabel.text = self.logic.checkResultsToHtml(results)
    self.ui.checkResultsLabel.visible = True
    return results

  def onCheckInputsButton(self):
    try:
      qt.QApplication.setOverrideCursor(qt.Qt.WaitCursor)
      self._checkInputs()
    except Exception as e:
      slicer.util.errorDisplay("Failed to check inputs: "+str(e))
      import traceback
      traceback.print_exc()
    finally:
      qt.QApplication.restoreOverrideCursor()

  @staticmethod
  def _stepLetter(stepIndex):
    """Name of the model of a further step in the summary: C, D, ..."""
    return chr(ord("C") + stepIndex) if stepIndex < 24 else f"M{stepIndex + 3}"

  def _stepsSummary(self):
    """Text that shows the order in which the operations are applied, e.g. "Result = ((A|B)-C)&&D"."""
    def combined(operation, result, model):
      if operation == "intersection":
        return f"{result}&&{model}"
      elif operation == "difference":
        return f"{result}-{model}"
      elif operation == "difference2":
        return f"{model}-{result}"
      return f"{result}|{model}"
    summary = combined(self._parameterNode.GetParameter("Operation"), "A", "B")
    for stepIndex in range(self._numberOfSteps()):
      summary = combined(self._parameterNode.GetParameter(f"StepOperation{stepIndex}"), f"({summary})", self._stepLetter(stepIndex))
    return "Result = " + summary

  def _createStepWidgets(self, numberOfSteps):
    """Replace the widgets of the further steps with numberOfSteps rows of operation, model and remove button."""
    for stepWidgets in self._stepWidgets:
      stepWidgets["row"].setParent(None)
      stepWidgets["row"].deleteLater()
    self._stepWidgets = []

    for stepIndex in range(numberOfSteps):
      row = qt.QWidget()
      rowLayout = qt.QHBoxLayout(row)
      rowLayout.setContentsMargins(0, 0, 0, 0)

      operationComboBox = qt.QComboBox()
      operationComboBox.addItem("Union", "union")
      operationComboBox.addItem("Intersection", "intersection")
      operationComboBox.addItem("Difference (result-model)", "difference")
      operationComboBox.addItem("Difference (model-result)", "difference2")
      operationComboBox.toolTip = "Operation that combines the result of the previous steps with the model"
      rowLayout.addWidget(operationComboBox)

      rowLayout.addWidget(qt.QLabel(self._stepLetter(stepIndex) + ":"))

      modelSelector = slicer.qMRMLNodeComboBox()
      modelSelector.nodeTypes = ["vtkMRMLModelNode"]
      modelSelector.showChildNodeTypes = False
      modelSelector.addEnabled = False
      modelSelector.removeEnabled = False
      modelSelector.renameEnabled = True
      modelSelector.toolTip = "Model that is combined with the result of the previous steps"
      modelSelector.setMRMLScene(slicer.mrmlScene)
      rowLayout.addWidget(modelSelector, 1)

      removeButton = qt.QToolButton()
      removeButton.text = "Remove"
      removeButton.toolTip = "Remove this step"
      rowLayout.addWidget(removeButton)

      operationComboBox.connect("currentIndexChanged(int)", self.updateParameterNodeFromGUI)
      modelSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
      removeButton.connect("clicked(bool)", lambda checked, stepIndex=stepIndex: self.onRemoveStepButton(stepIndex))

      self.ui.stepsRowsWidget.layout().addWidget(row)
      self._stepWidgets.append({"row": row, "operation": operationComboBox, "model": modelSelector})

  def onAddStepButton(self):
    numberOfSteps = self._numberOfSteps()
    wasModified = self._parameterNode.StartModify()
    self._parameterNode.SetParameter(f"StepOperation{numberOfSteps}", "union")
    self._parameterNode.SetNodeReferenceID(f"StepModel{numberOfSteps}", None)
    self._parameterNode.SetParameter("NumberOfAdditionalSteps", str(numberOfSteps + 1))
    self._parameterNode.EndModify(wasModified)

  def onRemoveStepButton(self, removedStepIndex):
    numberOfSteps = self._numberOfSteps()
    wasModified = self._parameterNode.StartModify()
    # Move the following steps up
    for stepIndex in range(removedStepIndex, numberOfSteps - 1):
      self._parameterNode.SetParameter(f"StepOperation{stepIndex}", self._parameterNode.GetParameter(f"StepOperation{stepIndex + 1}"))
      self._parameterNode.SetNodeReferenceID(f"StepModel{stepIndex}", self._parameterNode.GetNodeReferenceID(f"StepModel{stepIndex + 1}"))
    self._parameterNode.UnsetParameter(f"StepOperation{numberOfSteps - 1}")
    self._parameterNode.RemoveNodeReferenceIDs(f"StepModel{numberOfSteps - 1}")
    self._parameterNode.SetParameter("NumberOfAdditionalSteps", str(numberOfSteps - 1))
    self._parameterNode.EndModify(wasModified)

  def operationButtonToggled(self, operation):
    self._parameterNode.SetParameter("Operation", operation)

  def onApplyButton(self):
    """
    Run processing when user clicks "Apply" button.
    """
    try:
      qt.QApplication.setOverrideCursor(qt.Qt.WaitCursor)

      if self._parameterNode.GetParameter("CheckInputsBeforeApply") == "True":
        results = self._checkInputs()
        if any(result["problems"] for result in results):
          qt.QApplication.restoreOverrideCursor()
          try:
            computeAnyway = slicer.util.confirmYesNoDisplay(
              "Some input models have problems that can make the result invalid:\n\n"
              + self.logic.checkResultsToText(results, problemsOnly=True)
              + "\n\nCompute the result anyway?",
              windowTitle="Input check",
              detailedText=self.logic.checkResultsToText(results))
          finally:
            qt.QApplication.setOverrideCursor(qt.Qt.WaitCursor)
          if not computeAnyway:
            return

      # Add a new node for output, if no output node is selected
      if not self._parameterNode.GetNodeReference("OutputModel"):
        outputModel = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode")
        self._parameterNode.SetNodeReferenceID("OutputModel", outputModel.GetID())

      # Compute output
      numberOfSteps = self._numberOfSteps()
      if numberOfSteps > 0:
        self.logic.processSteps(
          [self._parameterNode.GetNodeReference("InputModelA"), self._parameterNode.GetNodeReference("InputModelB")]
            + [self._parameterNode.GetNodeReference(f"StepModel{stepIndex}") for stepIndex in range(numberOfSteps)],
          [self._parameterNode.GetParameter("Operation")]
            + [self._parameterNode.GetParameter(f"StepOperation{stepIndex}") for stepIndex in range(numberOfSteps)],
          self._parameterNode.GetNodeReference("OutputModel"),
          self._parameterNode.GetParameter("triangulateInputs") == "True",
          self._parameterNode.GetParameter("Backend"),
          float(self._parameterNode.GetParameter("OctreeVoxelSize")),
          int(self._parameterNode.GetParameter("OctreeExtraLevels"))
          )
        return

      self.logic.process(
        self._parameterNode.GetNodeReference("InputModelA"),
        self._parameterNode.GetNodeReference("InputModelB"),
        self._parameterNode.GetNodeReference("OutputModel"),
        self._parameterNode.GetParameter("Operation"),
        int(self._parameterNode.GetParameter("numberOfRetries")),
        int(float(self._parameterNode.GetParameter("randomTranslationMagnitude"))),
        self._parameterNode.GetParameter("triangulateInputs") == "True",
        self._parameterNode.GetParameter("Backend"),
        float(self._parameterNode.GetParameter("OctreeVoxelSize")),
        int(self._parameterNode.GetParameter("OctreeExtraLevels"))
        )

    except Exception as e:
      slicer.util.errorDisplay("Failed to compute results: "+str(e))
      import traceback
      traceback.print_exc()
    finally:
      qt.QApplication.restoreOverrideCursor()

  def onToggleVisibilityButton(self):
    outputModel = self._parameterNode.GetNodeReference("OutputModel")
    inputModelA = self._parameterNode.GetNodeReference("InputModelA")
    inputModelB = self._parameterNode.GetNodeReference("InputModelB")
    if not outputModel:
      return
    outputModel.CreateDefaultDisplayNodes()
    showOutput = not outputModel.GetDisplayNode().GetVisibility()
    inputModels = [inputModelA, inputModelB] + [self._parameterNode.GetNodeReference(f"StepModel{stepIndex}") for stepIndex in range(self._numberOfSteps())]
    for inputModel in inputModels:
      if inputModel and inputModel.GetDisplayNode():
        inputModel.GetDisplayNode().SetVisibility(not showOutput)
    outputModel.GetDisplayNode().SetVisibility(showOutput)


#
# CombineModelsLogic
#

class CombineModelsLogic(ScriptedLoadableModuleLogic):
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
    # Results of checkModel(), keyed by backend and polydata contents, oldest first
    self._checkResults = {}

  # Defects found by the input check: key in the results, label in the results table,
  # and description of the problem
  DEFECT_CHECKS = [
    ("boundaryEdges", "Boundary edges", "not closed (boundary edges)"),
    ("nonManifoldEdges", "Non-manifold edges", "non-manifold edges"),
    ("nonManifoldVertices", "Non-manifold vertices", "non-manifold vertices"),
    ("inconsistentEdges", "Inconsistent edges", "inconsistent orientation (inconsistent edges)"),
    ("degenerateFaces", "Degenerate faces", "degenerate faces"),
    ("selfIntersectingFaces", "Self-intersecting faces", "self-intersections (self-intersecting faces)"),
  ]

  # Libraries that perform the input check: key in the results and name
  CHECK_ENGINES = [("kigumi", "kigumi"), ("vtk", "VTK")]

  # Attribute of the model nodes that show the defects of an input model, which holds its ID
  DEFECTS_OF_ATTRIBUTE = "CombineModels.DefectsOf"

  @staticmethod
  def availableBackends():
    """
    Return the names of the Boolean operation backends in this build, the default one first.
    kigumi is not available if the extension was built with CombineModels_USE_KIGUMI=OFF.
    """
    import vtkSlicerCombineModelsModuleLogicPython as logicModule
    backends = []
    if hasattr(logicModule, "vtkKigumiBooleanFilter"):
      backends.append("kigumi")
    backends.append("vtkbool")
    if hasattr(logicModule, "vtkOctreeBooleanFilter"):
      backends.append("octree")
    return backends

  @classmethod
  def stepBackends(cls):
    """
    Return the names of the available backends that can combine more than two models, the default one first.
    """
    return [backend for backend in cls.availableBackends() if backend in ["kigumi", "octree"]]

  def setDefaultParameters(self, parameterNode):
    """
    Initialize parameter node with default settings.
    """
    if not parameterNode.GetParameter("Operation"):
      parameterNode.SetParameter("Operation", "union")
    if not parameterNode.GetParameter("numberOfRetries"):
      parameterNode.SetParameter("numberOfRetries", "2")
    if not parameterNode.GetParameter("randomTranslationMagnitude"):
      parameterNode.SetParameter("randomTranslationMagnitude", "4")
    if not parameterNode.GetParameter("triangulateInputs"):
      parameterNode.SetParameter("triangulateInputs", "False")
    if not parameterNode.GetParameter("Backend"):
      parameterNode.SetParameter("Backend", self.availableBackends()[0])
    if not parameterNode.GetParameter("OctreeVoxelSize"):
      parameterNode.SetParameter("OctreeVoxelSize", "0.0")
    if not parameterNode.GetParameter("OctreeExtraLevels"):
      parameterNode.SetParameter("OctreeExtraLevels", "2")
    if not parameterNode.GetParameter("CheckInputsBeforeApply"):
      parameterNode.SetParameter("CheckInputsBeforeApply", "True")
    if not parameterNode.GetParameter("ShowDefects"):
      parameterNode.SetParameter("ShowDefects", "True")
    if not parameterNode.GetParameter("NumberOfAdditionalSteps"):
      parameterNode.SetParameter("NumberOfAdditionalSteps", "0")
    for stepIndex in range(int(parameterNode.GetParameter("NumberOfAdditionalSteps"))):
      if not parameterNode.GetParameter(f"StepOperation{stepIndex}"):
        parameterNode.SetParameter(f"StepOperation{stepIndex}", "union")

  def process(
      self, 
      inputModelA, 
      inputModelB, 
      outputModel, 
      operation, 
      numberOfRetries = 2, 
      randomTranslationMagnitude = 4, 
      triangulateInputs = True,
      backend = None,
      voxelSize = 0.0,
      extraLevels = 2
    ):
    """
    Run the processing algorithm.
    Can be used without GUI widget.
    :param inputModelA: first input model node
    :param inputModelB: second input model node
    :param outputModel: result model node, if empty then a new output node will be created
    :param operation: union, intersection, difference, difference2
    :param numberOfRetries: number of retries if operation fails (not used by the octree backend)
    :param randomTranslationMagnitude: order of magnitude of the random translation (not used by the octree backend)
    :param triangulateInputs: triangulate input models before boolean operation
    :param backend: kigumi, vtkbool or octree, if None then the default backend (kigumi) is used
    :param voxelSize: voxel size of the octree backend, 0 to choose it automatically
    :param extraLevels: number of times the octree backend splits voxels near the surfaces
    """

    if not inputModelA or not inputModelB or not outputModel:
      raise ValueError("Input or output model nodes are invalid")

    if not backend:
      backend = self.availableBackends()[0]
    if backend not in self.availableBackends():
      raise ValueError("Backend is not available: "+backend)

    import time
    startTime = time.time()
    logging.info(f'Processing started (backend: {backend})')

    if backend == 'octree':
      if operation not in ['union', 'intersection', 'difference', 'difference2']:
        raise ValueError("Invalid operation: "+operation)
      # The octree backend does not fail on intersecting models, so it needs no retries
      polyDatas = [self._polyDataInOutputCoordinates(inputModel, outputModel, triangulateInputs)
        for inputModel in [inputModelA, inputModelB]]
      self._setOutputPolyData(outputModel, self._octreeBoolean(polyDatas, [operation], voxelSize, extraLevels))
      logging.info('Processing completed in {0:.2f} seconds'.format(time.time()-startTime))
      return

    import vtkSlicerCombineModelsModuleLogicPython as logicModule

    if backend == 'kigumi':
      combine = logicModule.vtkKigumiBooleanFilter()
    else:
      combine = logicModule.vtkPolyDataBooleanFilter()

    if operation == 'union':
      combine.SetOperModeToUnion()
    elif operation == 'intersection':
      combine.SetOperModeToIntersection()
    elif operation == 'difference':
      combine.SetOperModeToDifference()
    elif operation == 'difference2':
      combine.SetOperModeToDifference2()
    else:
      raise ValueError("Invalid operation: "+operation)

    # polydata inputs in "Output" coordinate system
    polydataA = self._polyDataInOutputCoordinates(inputModelA, outputModel, triangulateInputs)
    polydataB = self._polyDataInOutputCoordinates(inputModelB, outputModel, triangulateInputs)

    # First handle cases where inputs are not valid otherwise the boolean filter will crash
    modelAEmpty = polydataA.GetNumberOfPoints() == 0
    modelBEmpty = polydataB.GetNumberOfPoints() == 0
    if modelAEmpty and modelBEmpty:
        # both inputs are empty, output is empty regardless of the operation
        outputModel.SetAndObservePolyData(vtk.vtkPolyData())
        return
    elif modelAEmpty or modelBEmpty:
        # exactly one input is empty
        if operation == "union":
            outputModel.SetAndObservePolyData(polydataA if modelBEmpty else polydataB)
            return
        elif operation == "intersection":
            # if one model is empty then intersection is empty
            outputModel.SetAndObservePolyData(vtk.vtkPolyData())
            return
        elif operation == "difference":
            # A-B
            outputModel.SetAndObservePolyData(polydataA if modelBEmpty else vtk.vtkPolyData())
            return
        elif operation == "difference2":
            # B-A
            outputModel.SetAndObservePolyData(polydataB if modelAEmpty else vtk.vtkPolyData())
            return

    # We need to combine the models
    polydataBOriginal = polydataB
    polydataCombined = vtk.vtkPolyData()
    for attemptIndex in range(numberOfRetries+1):

        if attemptIndex == 0:
            polydataB = polydataBOriginal
        else:
            # Add random translation to model B
            # https://github.com/zippy84/vtkbool/issues/81
            logging.info(f"Retrying boolean operation with random translation (attempt {attemptIndex+1})")
            transform = vtk.vtkTransform()
            unitVector = [vtk.vtkMath.Random()-0.5 for _ in range(3)]
            vtk.vtkMath.Normalize(unitVector)
            import numpy as np
            translationVector = np.array(unitVector) * (10**-randomTranslationMagnitude)
            perturbationTransform = vtk.vtkTransform()
            perturbationTransform.Translate(translationVector)
            perturbationTransformer = vtk.vtkTransformPolyDataFilter()
            perturbationTransformer.SetTransform(perturbationTransform)
            perturbationTransformer.SetInputData(polydataBOriginal)
            perturbationTransformer.Update()
            polydataB = perturbationTransformer.GetOutput()

        # Calculate the result using Boolean operation
        combine.SetInputData(0, polydataA)
        combine.SetInputData(1, polydataB)
        # These parameters might be useful to expose:
        # combine.MergeRegsOn()  # default off
        # combine.DecPolysOff()  # default on
        combine.Update()

        combineFilterSuccessful = combine.GetOutput().GetNumberOfPoints() != 0
        if combineFilterSuccessful:
            polydataCombined = combine.GetOutput()
            break

        # Boolean operation failed, but if the meshes are not intersecting
        # then it may be a special case that we can handle with simpler methods
        collisionDetectionFilter = vtk.vtkCollisionDetectionFilter()
        collisionDetectionFilter.SetInputData(0, polydataA)
        collisionDetectionFilter.SetInputData(1, polydataB)
        identityMatrix = vtk.vtkMatrix4x4()
        collisionDetectionFilter.SetMatrix(0,identityMatrix)
        collisionDetectionFilter.SetMatrix(1,identityMatrix)
        collisionDetectionFilter.SetCollisionModeToFirstContact()
        collisionDetectionFilter.Update()
        intersecting = collisionDetectionFilter.GetNumberOfContacts() > 0
        if intersecting:
            # this is not a trivial case, try again
            continue

        # No intersection, we can do without computing Boolean operation
        if operation == 'union':
            # models do not touch so we can simply append them
            appendFilter = vtk.vtkAppendPolyData()
            appendFilter.AddInputData(polydataA)
            appendFilter.AddInputData(polydataB)
            appendFilter.Update()
            polydataCombined = appendFilter.GetOutput()
            break
        elif operation == 'intersection':
            # models do not touch so we return an empty model
            polydataCombined = vtk.vtkPolyData()
            break
        elif operation == 'difference':  # A-B
            polydataCombined = polydataA
            break
        elif operation == 'difference2':  # B-A
            polydataCombined = polydataB
            break

    self._setOutputPolyData(outputModel, polydataCombined)

    stopTime = time.time()
    logging.info('Processing completed in {0:.2f} seconds'.format(stopTime-startTime))

  def processSteps(self, inputModels, operations, outputModel, triangulateInputs = False, backend = None,
      voxelSize = 0.0, extraLevels = 2):
    """
    Combine several models in order: the result is
    (((inputModels[0] operations[0] inputModels[1]) operations[1] inputModels[2]) ...).
    Intermediate results are not rounded: kigumi computes them exactly, and octree on the same voxels.
    Can be used without GUI widget.
    :param inputModels: list of at least two input model nodes
    :param operations: list of len(inputModels)-1 operations, each of them union, intersection,
      difference (result of the previous steps minus the model), or difference2 (the model minus the result)
    :param outputModel: result model node
    :param triangulateInputs: triangulate input models before boolean operation
    :param backend: kigumi or octree (see stepBackends()), if None then the default one (kigumi) is used
    :param voxelSize: voxel size of the octree backend, 0 to choose it automatically
    :param extraLevels: number of times the octree backend splits voxels near the surfaces
    """

    if len(inputModels) < 2 or not all(inputModels) or not outputModel:
      raise ValueError("Input or output model nodes are invalid")
    if len(operations) != len(inputModels) - 1:
      raise ValueError(f"Expected {len(inputModels) - 1} operations for {len(inputModels)} input models, got {len(operations)}")
    if not self.stepBackends():
      raise ValueError("Multi-step operations require the kigumi or octree backend, which are not available in this build")
    if not backend:
      backend = self.stepBackends()[0]
    if backend not in self.stepBackends():
      raise ValueError(f"Multi-step operations require the kigumi or octree backend, not {backend}")
    for operation in operations:
      if operation not in ["union", "intersection", "difference", "difference2"]:
        raise ValueError("Invalid operation: "+str(operation))

    import time
    startTime = time.time()
    logging.info(f'Processing started (backend: {backend}, {len(operations)} steps)')

    polyDatas = [self._polyDataInOutputCoordinates(inputModel, outputModel, triangulateInputs) for inputModel in inputModels]
    if backend == "octree":
      self._setOutputPolyData(outputModel, self._octreeBoolean(polyDatas, operations, voxelSize, extraLevels))
    else:
      import vtkSlicerCombineModelsModuleLogicPython as logicModule
      combine = logicModule.vtkKigumiBooleanSequenceFilter()
      for index, operation in enumerate(operations):
        combine.SetOperation(index + 1, self._operMode(logicModule.vtkKigumiBooleanFilter, operation))
      for polyData in polyDatas:
        combine.AddInputData(polyData)

      # Report errors of the filter (e.g., self-intersecting inputs) as an exception
      self._updateFilter(combine)

      self._setOutputPolyData(outputModel, combine.GetOutput())

    stopTime = time.time()
    logging.info('Processing completed in {0:.2f} seconds'.format(stopTime-startTime))

  @staticmethod
  def _operMode(filterClass, operation):
    """Operation mode of filterClass (OPER_UNION, ...) that corresponds to operation (union, ...)."""
    return {
      "union": filterClass.OPER_UNION,
      "intersection": filterClass.OPER_INTERSECTION,
      "difference": filterClass.OPER_DIFFERENCE,
      "difference2": filterClass.OPER_DIFFERENCE2,
    }[operation]

  def _octreeBoolean(self, polyDatas, operations, voxelSize, extraLevels):
    """
    Combine polyDatas with the octree backend: the result is
    (((polyDatas[0] operations[0] polyDatas[1]) operations[1] polyDatas[2]) ...).
    :param voxelSize: voxel size, 0 to choose it automatically
    :param extraLevels: number of times the voxels are split near the surfaces
    :return: polydata of the result
    """
    import vtkSlicerCombineModelsModuleLogicPython as logicModule
    combine = logicModule.vtkOctreeBooleanFilter()
    combine.SetVoxelSize(voxelSize)
    combine.SetExtraLevels(extraLevels)
    for index, operation in enumerate(operations):
      combine.SetOperation(index + 1, self._operMode(logicModule.vtkOctreeBooleanFilter, operation))
    for polyData in polyDatas:
      combine.AddInputData(polyData)
    # Report errors of the filter (e.g., too many voxels) as an exception
    self._updateFilter(combine)
    if combine.GetEffectiveVoxelSize() > 0:
      logging.info(f'Octree voxel size: {combine.GetEffectiveVoxelSize():.4g}' + (' (automatic)' if voxelSize <= 0 else ''))
    return combine.GetOutput()

  def checkInputs(self, inputModels, outputModel = None, backend = None, triangulateInputs = False, showDefects = True):
    """
    Check whether the input models are valid inputs for Boolean operations, see checkModel().
    Can be used without GUI widget.
    :param inputModels: list of input model nodes, each of them is checked once
    :param outputModel: result model node, whose coordinate system the inputs are checked in (world if None)
    :param backend: kigumi, vtkbool or octree, if None then the default backend (kigumi) is used
    :param triangulateInputs: triangulate input models before the check, as before the Boolean operation
    :param showDefects: show the defects of each input in a model node, see checkModel()
    :return: list of the results of checkModel(), one per distinct input model
    """
    results = []
    checkedModelIDs = set()
    for inputModel in inputModels:
      if inputModel.GetID() in checkedModelIDs:
        continue
      checkedModelIDs.add(inputModel.GetID())
      results.append(self.checkModel(inputModel, outputModel, backend, triangulateInputs, showDefects))
    return results

  def checkModel(self, inputModel, outputModel = None, backend = None, triangulateInputs = False, showDefects = True):
    """
    Check whether the input model is a valid input for Boolean operations: a closed, manifold and consistently
    outwards oriented surface without degenerate or self-intersecting faces. The octree backend only needs a closed
    surface, so for it the other defects are warnings.
    kigumi finds the defects exactly, if it is available. VTK filters check the mesh as the backend sees it.
    The polydata is checked in the coordinate system of the output, as process() uses it.
    Can be used without GUI widget.
    :param inputModel: input model node
    :param outputModel: result model node, whose coordinate system the input is checked in (world if None)
    :param backend: kigumi, vtkbool or octree, if None then the default backend (kigumi) is used
    :param triangulateInputs: triangulate the input model before the check, as before the Boolean operation
    :param showDefects: show the defects in the model node "<input model name> defects", which is removed if
      there are none to show
    :return: dict with "model" (inputModel), "backend", "problems" and "warnings" (lists of sentences),
      "kigumi" and "vtk" (dicts of the numbers found by each library, None if it did not check the model,
      None values for checks that it cannot perform), "defects" (polydata of the defects, None if not found),
      and "defectsModel" (model node that shows the defects, None if not shown)
    """
    if not backend:
      backend = self.availableBackends()[0]

    if inputModel.GetPolyData():
      polyData = self._polyDataInOutputCoordinates(inputModel, outputModel, triangulateInputs)
    else:
      polyData = vtk.vtkPolyData()

    # Reuse the result if the same mesh was checked before, e.g. by "Check inputs" before "Apply"
    cacheKey = (backend, self._polyDataDigest(polyData))
    if cacheKey not in self._checkResults:
      if len(self._checkResults) >= 20:
        del self._checkResults[next(iter(self._checkResults))]
      self._checkResults[cacheKey] = self._checkPolyData(polyData, backend)

    result = dict(self._checkResults[cacheKey], model=inputModel)
    result["defectsModel"] = self._updateDefectsModel(inputModel, outputModel, result["defects"] if showDefects else None)
    return result

  def checkResultsToText(self, results, problemsOnly = False):
    """
    Describe the results of checkInputs() as plain text.
    :param problemsOnly: describe only the problems of the models that have any
    """
    lines = []
    for result in results:
      if problemsOnly and not result["problems"]:
        continue
      lines.append(result["model"].GetName() + (":" if result["problems"] else ": no problems found"))
      lines += ["  - " + problem for problem in result["problems"]]
      if not problemsOnly:
        lines += ["  - warning: " + warning for warning in result["warnings"]]
    return "\n".join(lines)

  def checkResultsToHtml(self, results):
    """
    Describe the results of checkInputs() as rich text, with a table of the numbers found by each library.
    """
    from html import escape

    def cell(value, isProblem):
      if value is None:
        return '<td align="right">&ndash;</td>'
      text = f"{value:.6g}" if isinstance(value, float) else str(value)
      style = ' style="color:#d00000; font-weight:bold"' if isProblem else ""
      return f'<td align="right"{style}>{text}</td>'

    text = ""
    for result in results:
      if result["problems"]:
        status = f'<span style="color:#d00000">&#10008; {len(result["problems"])} problem(s) found</span>'
      else:
        status = '<span style="color:#008000">&#10004; no problems found</span>'
      text += f'<p><b>{escape(result["model"].GetName())}</b>: {status}</p>'

      if result["vtk"]:
        rows = [(label, key, True) for key, label, description in self.DEFECT_CHECKS]
        rows += [
          ("Sliver faces (vtkbool)", "sliverFaces", result["backend"] == "vtkbool"),
          ("Triangles", "faces", False),
          ("Parts", "parts", False),
          ]
        text += '<table cellspacing="0" cellpadding="2"><tr><th align="left">Check</th>'
        text += "".join(f'<th align="right">{name}</th>' for engine, name in self.CHECK_ENGINES) + "</tr>"
        for label, key, isDefect in rows:
          text += f"<tr><td>{label}</td>"
          for engine, name in self.CHECK_ENGINES:
            value = result[engine].get(key) if result[engine] else None
            text += cell(value, isDefect and bool(value))
          text += "</tr>"
        volume = result["vtk"]["volume"]
        text += f"<tr><td>Volume</td>{cell(None, False)}{cell(volume, volume < 0)}</tr></table>"

      if result["problems"]:
        text += "<ul>" + "".join(f"<li>{escape(problem)}</li>" for problem in result["problems"]) + "</ul>"
      if result["warnings"]:
        text += "<ul>" + "".join(f'<li style="color:#b06000">{escape(warning)}</li>' for warning in result["warnings"]) + "</ul>"
      if result["defectsModel"]:
        text += f'<p>Defects are shown in model &quot;{escape(result["defectsModel"].GetName())}&quot;.</p>'
    return text

  def _checkPolyData(self, polyData, backend):
    """
    Check polyData with kigumi (if available) and VTK filters, see checkModel().
    """
    result = {"backend": backend, "kigumi": None, "vtk": None, "problems": [], "warnings": [], "defects": None}

    numberOfIgnoredCells = polyData.GetNumberOfVerts() + polyData.GetNumberOfLines()
    if numberOfIgnoredCells > 0:
      result["warnings"].append(f"{numberOfIgnoredCells} vertex and line cells are ignored")
    if polyData.GetNumberOfPolys() + polyData.GetNumberOfStrips() == 0:
      result["warnings"].append("no polygons, the model represents the empty set")
      return result

    if "kigumi" in self.availableBackends():
      result["kigumi"], result["defects"] = self._kigumiCheck(polyData)
    else:
      result["warnings"].append("self-intersections and non-manifold vertices are not checked,"
        " because the kigumi backend is not available in this build")
    result["vtk"], vtkDefects = self._vtkCheck(polyData, backend)
    if result["defects"] is None:
      result["defects"] = vtkDefects

    # The octree backend takes the regions that a ray from them crosses the surface of an odd number of times,
    # so it only needs closed surfaces
    for key, label, description in self.DEFECT_CHECKS:
      counts = [f"{result[engine][key]} ({name})" for engine, name in self.CHECK_ENGINES
        if result[engine] and result[engine][key]]
      if not counts:
        continue
      if backend != "octree" or key == "boundaryEdges":
        result["problems"].append(f"{description}: " + ", ".join(counts))
      elif key == "selfIntersectingFaces":
        result["warnings"].append(f"{description}: " + ", ".join(counts)
          + ", the octree backend removes the regions where parts of the model overlap, unite them first to keep them")
      else:
        result["warnings"].append(f"{description}: " + ", ".join(counts) + ", which the octree backend tolerates")

    vtkCounts = result["vtk"]
    if vtkCounts["volume"] < 0 and not any(vtkCounts[key] for key in ["boundaryEdges", "nonManifoldEdges", "inconsistentEdges"]):
      if backend == "octree":
        result["warnings"].append("inside out: the faces are oriented inwards (negative volume), which the octree backend tolerates")
      else:
        result["problems"].append("inside out: the faces are oriented inwards (negative volume)")
    if backend == "vtkbool" and vtkCounts["sliverFaces"] > 0:
      result["warnings"].append(f"{vtkCounts['sliverFaces']} sliver faces (triangle quality below 0.001),"
        " vtkbool may fail where the intersection passes near them")

    return result

  def _kigumiCheck(self, polyData):
    """
    Find the defects of polyData exactly with kigumi.
    :return: dict of the numbers of defects, and polydata of the defects
    """
    import vtkSlicerCombineModelsModuleLogicPython as logicModule
    defectsFilter = logicModule.vtkKigumiMeshDefectsFilter()
    defectsFilter.SetInputData(polyData)
    self._updateFilter(defectsFilter)
    counts = {
      "faces": defectsFilter.GetNumberOfFaces(),
      "boundaryEdges": defectsFilter.GetNumberOfBoundaryEdges(),
      "nonManifoldEdges": defectsFilter.GetNumberOfNonManifoldEdges(),
      "nonManifoldVertices": defectsFilter.GetNumberOfNonManifoldVertices(),
      "inconsistentEdges": defectsFilter.GetNumberOfInconsistentEdges(),
      "degenerateFaces": defectsFilter.GetNumberOfDegenerateFaces(),
      "selfIntersectingFaces": defectsFilter.GetNumberOfSelfIntersectingFaces(),
      }
    return counts, defectsFilter.GetOutput()

  def _vtkCheck(self, polyData, backend):
    """
    Check polyData with VTK filters, after merging its points as the backend does: exactly for kigumi, and with
    the tolerance of vtkbool (1e-6 of the bounding box diagonal) for vtkbool.
    Inconsistent edges, volume and triangle quality are computed as in the tests and the code of vtkbool.
    VTK cannot find non-manifold vertices and self-intersections.
    :return: dict of the numbers found, and polydata of the boundary and non-manifold edges
    """
    import numpy as np
    from vtk.util.numpy_support import vtk_to_numpy

    triangulator = vtk.vtkTriangleFilter()
    triangulator.PassVertsOff()
    triangulator.PassLinesOff()
    triangulator.SetInputData(polyData)
    triangulator.Update()
    cleaner = vtk.vtkCleanPolyData()
    cleaner.SetInputData(triangulator.GetOutput())
    cleaner.ConvertPolysToLinesOff()
    cleaner.ConvertLinesToPointsOff()
    cleaner.ConvertStripsToPolysOff()
    if backend == "vtkbool":
      cleaner.SetTolerance(1e-6)
    else:
      cleaner.ToleranceIsAbsoluteOn()
      cleaner.SetAbsoluteTolerance(0.0)
    cleaner.Update()
    triangles = cleaner.GetOutput()
    # Triangles whose points were merged
    numberOfCollapsedFaces = triangulator.GetOutput().GetNumberOfPolys() - triangles.GetNumberOfPolys()

    def featureEdges(boundaryEdges, nonManifoldEdges):
      featureEdgesFilter = vtk.vtkFeatureEdges()
      featureEdgesFilter.SetInputData(triangles)
      featureEdgesFilter.SetBoundaryEdges(boundaryEdges)
      featureEdgesFilter.SetNonManifoldEdges(nonManifoldEdges)
      featureEdgesFilter.FeatureEdgesOff()
      featureEdgesFilter.ManifoldEdgesOff()
      featureEdgesFilter.ColoringOff()
      featureEdgesFilter.Update()
      return featureEdgesFilter.GetOutput()

    boundaryEdges = featureEdges(True, False)
    nonManifoldEdges = featureEdges(False, True)
    edges = vtk.vtkAppendPolyData()
    edges.AddInputData(boundaryEdges)
    edges.AddInputData(nonManifoldEdges)
    edges.Update()

    connectivity = vtk.vtkPolyDataConnectivityFilter()
    connectivity.SetInputData(triangles)
    connectivity.SetExtractionModeToAllRegions()
    connectivity.Update()

    counts = {
      "faces": triangles.GetNumberOfPolys(),
      "boundaryEdges": boundaryEdges.GetNumberOfLines(),
      "nonManifoldEdges": nonManifoldEdges.GetNumberOfLines(),
      "nonManifoldVertices": None,
      "inconsistentEdges": 0,
      "degenerateFaces": numberOfCollapsedFaces,
      "selfIntersectingFaces": None,
      "sliverFaces": 0,
      "parts": connectivity.GetNumberOfExtractedRegions(),
      "volume": 0.0,
      }
    if triangles.GetNumberOfPolys() == 0:
      return counts, edges.GetOutput()

    legacyFaces = vtk.vtkIdTypeArray()
    triangles.GetPolys().ExportLegacyFormat(legacyFaces)
    # Each face is stored as 3 followed by its point ids
    faces = vtk_to_numpy(legacyFaces).reshape(-1, 4)[:, 1:]
    # Relative to the center of the bounding box, for accuracy
    bounds = triangles.GetBounds()
    center = [(bounds[0] + bounds[1]) / 2, (bounds[2] + bounds[3]) / 2, (bounds[4] + bounds[5]) / 2]
    points = vtk_to_numpy(triangles.GetPoints().GetData()).astype(np.float64) - center
    p0, p1, p2 = points[faces[:, 0]], points[faces[:, 1]], points[faces[:, 2]]

    # Each edge of a closed, consistently oriented mesh is traversed once in each direction
    halfEdges = np.stack([faces, np.roll(faces, -1, axis=1)], axis=2).reshape(-1, 2).astype(np.int64)
    edgeKeys = halfEdges.min(axis=1) * len(points) + halfEdges.max(axis=1)
    directions = np.where(halfEdges[:, 0] < halfEdges[:, 1], 1, -1)
    _, edgeIndices, edgeCounts = np.unique(edgeKeys, return_inverse=True, return_counts=True)
    directionSums = np.bincount(edgeIndices.ravel(), weights=directions, minlength=len(edgeCounts))
    counts["inconsistentEdges"] = int(np.count_nonzero((edgeCounts == 2) & (directionSums != 0)))

    doubleAreas = np.linalg.norm(np.cross(p1 - p0, p2 - p0), axis=1)
    counts["degenerateFaces"] += int(np.count_nonzero(doubleAreas == 0))
    # Triangle quality of vtkbool, which is 1 for equilateral triangles. vtkbool fails at triangles
    # of quality below 0.001 where the intersection passes near them.
    perimeters = np.linalg.norm(p1 - p0, axis=1) + np.linalg.norm(p2 - p1, axis=1) + np.linalg.norm(p0 - p2, axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
      qualities = 6 * np.sqrt(3) * doubleAreas / perimeters**2
    counts["sliverFaces"] = int(np.count_nonzero((doubleAreas > 0) & (qualities < 0.001)))

    counts["volume"] = float(np.einsum("ij,ij->", p0, np.cross(p1, p2)) / 6)
    return counts, edges.GetOutput()

  def _updateDefectsModel(self, inputModel, outputModel, defects):
    """
    Show defects (polydata) in the defects model of inputModel, which is created if needed.
    The defects model is removed if defects is None or empty.
    """
    defectsModel = next((node for node in slicer.util.getNodesByClass("vtkMRMLModelNode")
      if node.GetAttribute(self.DEFECTS_OF_ATTRIBUTE) == inputModel.GetID()), None)
    if defects is None or defects.GetNumberOfCells() == 0:
      if defectsModel:
        slicer.mrmlScene.RemoveNode(defectsModel)
      return None

    if not defectsModel:
      defectsModel = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", inputModel.GetName() + " defects")
      defectsModel.SetAttribute(self.DEFECTS_OF_ATTRIBUTE, inputModel.GetID())
      defectsModel.CreateDefaultDisplayNodes()
      displayNode = defectsModel.GetDisplayNode()
      displayNode.SetColor(1.0, 0.0, 0.0)
      # Show faces as outlines, as the faces of the input model would hide them
      displayNode.SetRepresentation(displayNode.WireframeRepresentation)
      displayNode.SetLineWidth(3)
      displayNode.SetPointSize(8)
      displayNode.SetVisibility2D(True)

    # Copy, as the polydata of the result is reused for later checks
    defectsPolyData = vtk.vtkPolyData()
    defectsPolyData.DeepCopy(defects)
    defectsModel.SetAndObserveTransformNodeID(outputModel.GetTransformNodeID() if outputModel else None)
    defectsModel.SetAndObservePolyData(defectsPolyData)
    defectsModel.GetDisplayNode().SetScalarVisibility(False)
    return defectsModel

  @staticmethod
  def _polyDataDigest(polyData):
    """
    Return a hash of the points and cells of polyData.
    """
    import hashlib
    from vtk.util.numpy_support import vtk_to_numpy
    digest = hashlib.blake2b()
    arrays = [polyData.GetPoints().GetData()] if polyData.GetPoints() else []
    for cells in [polyData.GetVerts(), polyData.GetLines(), polyData.GetPolys(), polyData.GetStrips()]:
      # The legacy format is independent of how the cell array stores its offsets
      legacyCells = vtk.vtkIdTypeArray()
      cells.ExportLegacyFormat(legacyCells)
      arrays.append(legacyCells)
    for array in arrays:
      values = vtk_to_numpy(array)
      digest.update(f"{values.dtype}{values.shape}".encode())
      digest.update(values.tobytes())
    return digest.hexdigest()

  @staticmethod
  def _updateFilter(algorithm):
    """
    Update algorithm and raise its first error as an exception.
    """
    errors = []
    @vtk.calldata_type(vtk.VTK_STRING)
    def onError(caller, event, message):
      errors.append(message)
    errorObserver = algorithm.AddObserver(vtk.vtkCommand.ErrorEvent, onError)
    algorithm.Update()
    algorithm.RemoveObserver(errorObserver)
    if errors:
      # Keep only the text after "vtkKigumiBooleanSequenceFilter (0x...): "
      raise RuntimeError(errors[0].strip().splitlines()[-1].split("): ", 1)[-1])

  def _polyDataInOutputCoordinates(self, inputModel, outputModel, triangulateInputs):
    """
    Return the polydata of inputModel in the coordinate system of outputModel (world if outputModel is None),
    triangulated if requested.
    """
    transformToOutput = vtk.vtkGeneralTransform()
    slicer.vtkMRMLTransformNode.GetTransformBetweenNodes(inputModel.GetParentTransformNode(),
      outputModel.GetParentTransformNode() if outputModel else None, transformToOutput)
    transformerToOutput = vtk.vtkTransformPolyDataFilter()
    transformerToOutput.SetTransform(transformToOutput)
    if triangulateInputs:
      triangulateFilter = vtk.vtkTriangleFilter()
      triangulateFilter.SetInputData(inputModel.GetPolyData())
      triangulateFilter.Update()
      transformerToOutput.SetInputData(triangulateFilter.GetOutput())
    else:
      transformerToOutput.SetInputData(inputModel.GetPolyData())
    transformerToOutput.Update()
    return transformerToOutput.GetOutput()

  def _setOutputPolyData(self, outputModel, polyData):
    outputModel.SetAndObservePolyData(polyData)
    outputModel.CreateDefaultDisplayNodes()
    # The filter creates a few scalars, don't show them by default, as they would be somewhat distracting
    outputModel.GetDisplayNode().SetScalarVisibility(False)

#
# CombineModelsTest
#

class CombineModelsTest(ScriptedLoadableModuleTest):
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
    self.test_CombineModels1()
    self.setUp()
    self.test_CombineModelsMultiStep()
    self.setUp()
    self.test_CombineModelsCheckInputs()
    self.setUp()
    self.test_CombineModelsOctree()

  def test_CombineModels1(self):
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

    sphere = vtk.vtkSphereSource()
    sphere.SetRadius(30)
    inputModelA = slicer.modules.models.logic().AddModel(sphere.GetOutputPort())

    cylinder = vtk.vtkCylinderSource()
    cylinder.SetRadius(20)
    cylinder.SetHeight(75)
    inputModelB = slicer.modules.models.logic().AddModel(cylinder.GetOutputPort())

    # Test the module logic

    logic = CombineModelsLogic()

    self.assertIn("kigumi", logic.availableBackends())

    for backend in logic.availableBackends():
      for operation in ['union', 'intersection', 'difference', 'difference2']:
        outputModel = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", f'Output {operation} ({backend})')
        logic.process(inputModelA, inputModelB, outputModel, operation, backend=backend)
        self.assertTrue(outputModel.GetPolyData().GetNumberOfPoints()>0)

    self.delayDisplay('Test passed')

  def test_CombineModelsMultiStep(self):
    """Test combining more than two models with exact intermediate results."""

    self.delayDisplay("Starting the multi-step test")

    logic = CombineModelsLogic()
    if "kigumi" not in logic.availableBackends():
      self.delayDisplay("kigumi backend is not available, skipping the multi-step test")
      return

    sphere = vtk.vtkSphereSource()
    sphere.SetRadius(30)
    sphere.SetThetaResolution(48)
    sphere.SetPhiResolution(48)
    cylinder = vtk.vtkCylinderSource()
    cylinder.SetRadius(20)
    cylinder.SetHeight(75)
    cylinder.SetResolution(48)
    # The box cuts through the curve where the sphere and the cylinder intersect
    box = vtk.vtkCubeSource()
    box.SetBounds(-40, 40, 10, 40, -10, 10)
    inputModels = [slicer.modules.models.logic().AddModel(source.GetOutputPort()) for source in [sphere, cylinder, box]]

    def volume(polyData):
      massProperties = vtk.vtkMassProperties()
      massProperties.SetInputData(polyData)
      massProperties.Update()
      return massProperties.GetVolume()

    def numberOfBoundaryEdges(polyData):
      featureEdges = vtk.vtkFeatureEdges()
      featureEdges.SetInputData(polyData)
      featureEdges.BoundaryEdgesOn()
      featureEdges.FeatureEdgesOff()
      featureEdges.ManifoldEdgesOff()
      featureEdges.NonManifoldEdgesOff()
      featureEdges.Update()
      return featureEdges.GetOutput().GetNumberOfCells()

    # (A|B)-C computed exactly
    outputModel = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "Output (A|B)-C")
    logic.processSteps(inputModels, ["union", "difference"], outputModel)
    outputPolyData = outputModel.GetPolyData()
    self.assertGreater(outputPolyData.GetNumberOfPoints(), 0)
    self.assertEqual(numberOfBoundaryEdges(outputPolyData), 0)

    # Same result as two separate operations, where the intermediate result is rounded
    intermediateModel = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "Output A|B")
    logic.process(inputModels[0], inputModels[1], intermediateModel, "union", triangulateInputs=False, backend="kigumi")
    chainedModel = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", "Output (A|B)-C chained")
    logic.process(intermediateModel, inputModels[2], chainedModel, "difference", triangulateInputs=False, backend="kigumi")
    chainedVolume = volume(chainedModel.GetPolyData())
    self.assertAlmostEqual(volume(outputPolyData), chainedVolume, delta=1e-6 * chainedVolume)

    # A single step gives the same result as process()
    for operation in ["union", "intersection", "difference", "difference2"]:
      stepsModel = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", f"Output {operation} (steps)")
      logic.processSteps(inputModels[:2], [operation], stepsModel)
      pairModel = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", f"Output {operation} (pair)")
      logic.process(inputModels[0], inputModels[1], pairModel, operation, triangulateInputs=False, backend="kigumi")
      self.assertEqual(stepsModel.GetPolyData().GetNumberOfCells(), pairModel.GetPolyData().GetNumberOfCells())
      self.assertAlmostEqual(volume(stepsModel.GetPolyData()), volume(pairModel.GetPolyData()), places=6)

    # Invalid arguments
    with self.assertRaises(ValueError):
      logic.processSteps(inputModels, ["union"], outputModel)
    with self.assertRaises(ValueError):
      logic.processSteps(inputModels, ["union", "xor"], outputModel)
    with self.assertRaises(ValueError):
      logic.processSteps(inputModels, ["union", "difference"], outputModel, backend="vtkbool")

    self.delayDisplay('Multi-step test passed')

  def test_CombineModelsCheckInputs(self):
    """Test the check of the input models for defects."""

    self.delayDisplay("Starting the input check test")

    logic = CombineModelsLogic()
    kigumiAvailable = "kigumi" in logic.availableBackends()

    def sphere(center=(0, 0, 0), endTheta=360):
      source = vtk.vtkSphereSource()
      source.SetCenter(center)
      source.SetRadius(10)
      source.SetThetaResolution(24)
      source.SetPhiResolution(16)
      source.SetEndTheta(endTheta)
      source.Update()
      return source.GetOutput()

    def addModel(polyData, name):
      model = slicer.modules.models.logic().AddModel(polyData)
      model.SetName(name)
      return model

    def problems(result, text):
      return [problem for problem in result["problems"] if text in problem]

    def defectsModels(inputModel):
      return [node for node in slicer.util.getNodesByClass("vtkMRMLModelNode")
        if node.GetAttribute(logic.DEFECTS_OF_ATTRIBUTE) == inputModel.GetID()]

    # A closed sphere has no problems, and each model is checked once
    closedModel = addModel(sphere(), "Closed")
    for backend in logic.availableBackends():
      results = logic.checkInputs([closedModel, closedModel], backend=backend)
      self.assertEqual(len(results), 1)
      self.assertEqual(results[0]["problems"], [])
      self.assertIsNone(results[0]["defectsModel"])
      self.assertGreater(results[0]["vtk"]["volume"], 0)
      self.assertEqual(results[0]["vtk"]["parts"], 1)

    # Open
    openModel = addModel(sphere(endTheta=270), "Open")
    [result] = logic.checkInputs([openModel])
    self.assertTrue(problems(result, "not closed"))
    self.assertGreater(result["vtk"]["boundaryEdges"], 0)
    self.assertIsNotNone(result["defectsModel"])
    self.assertEqual(defectsModels(openModel), [result["defectsModel"]])
    self.assertGreater(result["defectsModel"].GetPolyData().GetNumberOfLines(), 0)

    # Inside out
    reverseSense = vtk.vtkReverseSense()
    reverseSense.SetInputData(sphere())
    reverseSense.ReverseCellsOn()
    reverseSense.Update()
    insideOutModel = addModel(reverseSense.GetOutput(), "Inside out")
    [result] = logic.checkInputs([insideOutModel])
    self.assertEqual(len(result["problems"]), 1)
    self.assertTrue(problems(result, "inside out"))
    self.assertLess(result["vtk"]["volume"], 0)

    # One face is reversed
    inconsistentPolyData = sphere()
    polys = vtk.vtkCellArray()
    pointIds = vtk.vtkIdList()
    for cellId in range(inconsistentPolyData.GetNumberOfCells()):
      inconsistentPolyData.GetCellPoints(cellId, pointIds)
      ids = [pointIds.GetId(index) for index in range(pointIds.GetNumberOfIds())]
      polys.InsertNextCell(len(ids), ids[::-1] if cellId == 0 else ids)
    inconsistentPolyData.SetPolys(polys)
    inconsistentModel = addModel(inconsistentPolyData, "Inconsistent")
    [result] = logic.checkInputs([inconsistentModel])
    self.assertTrue(problems(result, "inconsistent orientation"))
    self.assertEqual(result["vtk"]["inconsistentEdges"], 3)
    if kigumiAvailable:
      self.assertEqual(result["kigumi"]["inconsistentEdges"], 3)

    # Two overlapping spheres in one model
    append = vtk.vtkAppendPolyData()
    append.AddInputData(sphere())
    append.AddInputData(sphere(center=(5, 0, 0)))
    append.Update()
    selfIntersectingModel = addModel(append.GetOutput(), "Self-intersecting")
    [result] = logic.checkInputs([selfIntersectingModel])
    self.assertEqual(result["vtk"]["parts"], 2)
    if kigumiAvailable:
      import vtkSlicerCombineModelsModuleLogicPython as logicModule
      from vtk.util.numpy_support import vtk_to_numpy
      self.assertGreater(result["kigumi"]["selfIntersectingFaces"], 0)
      self.assertTrue(problems(result, "self-intersections"))
      defectTypes = vtk_to_numpy(result["defectsModel"].GetPolyData().GetCellData().GetArray("DefectType"))
      self.assertIn(logicModule.vtkKigumiMeshDefectsFilter.SELF_INTERSECTING_FACE, defectTypes)
    else:
      self.assertTrue(result["warnings"])

    # Defects are not shown if not requested
    [result] = logic.checkInputs([selfIntersectingModel], showDefects=False)
    self.assertIsNone(result["defectsModel"])
    self.assertEqual(defectsModels(selfIntersectingModel), [])

    # After fixing an input, its defects model is removed
    openModel.SetAndObservePolyData(sphere())
    [result] = logic.checkInputs([openModel])
    self.assertEqual(result["problems"], [])
    self.assertEqual(defectsModels(openModel), [])

    # Descriptions of the results
    results = logic.checkInputs([closedModel, insideOutModel])
    problemsText = logic.checkResultsToText(results, problemsOnly=True)
    self.assertIn("Inside out", problemsText)
    self.assertNotIn("Closed", problemsText)
    self.assertIn("Closed: no problems found", logic.checkResultsToText(results))
    self.assertIn("Inside out", logic.checkResultsToHtml(results))

    # An empty model represents the empty set
    emptyModel = addModel(vtk.vtkPolyData(), "Empty")
    [result] = logic.checkInputs([emptyModel])
    self.assertEqual(result["problems"], [])
    self.assertTrue(result["warnings"])

    # The octree backend only needs closed surfaces
    if "octree" in logic.availableBackends():
      [result] = logic.checkInputs([insideOutModel], backend="octree")
      self.assertEqual(result["problems"], [])
      self.assertTrue([warning for warning in result["warnings"] if "inside out" in warning])
      [result] = logic.checkInputs([selfIntersectingModel], backend="octree")
      self.assertEqual(result["problems"], [])
      self.assertTrue(result["warnings"])
      [result] = logic.checkInputs([addModel(sphere(endTheta=270), "Open octree")], backend="octree")
      self.assertTrue(problems(result, "not closed"))

    self.delayDisplay('Input check test passed')

  def test_CombineModelsOctree(self):
    """Test the octree backend against the exact results of kigumi."""

    self.delayDisplay("Starting the octree test")

    logic = CombineModelsLogic()
    if "octree" not in logic.availableBackends() or "kigumi" not in logic.availableBackends():
      self.delayDisplay("octree or kigumi backend is not available, skipping the octree test")
      return

    import numpy as np
    from vtk.util.numpy_support import vtk_to_numpy
    import vtkSlicerCombineModelsModuleLogicPython as logicModule

    sphere = vtk.vtkSphereSource()
    sphere.SetRadius(20)
    sphere.SetThetaResolution(100)
    sphere.SetPhiResolution(100)
    sphere.Update()
    cylinder = vtk.vtkCylinderSource()
    cylinder.SetCenter(10, 0, 0)
    cylinder.SetRadius(8)
    cylinder.SetHeight(60)
    cylinder.SetResolution(100)
    cylinder.Update()
    # The box cuts through the curve where the sphere and the cylinder intersect
    box = vtk.vtkCubeSource()
    box.SetBounds(-30, 30, 5, 30, -10, 10)
    box.Update()
    inputModels = [slicer.modules.models.logic().AddModel(source.GetOutput()) for source in [sphere, cylinder, box]]

    def addOutputModel(name):
      return slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", name)

    def checkOctreeResult(octreePolyData, kigumiPolyData, voxelSize):
      """The octree result is closed and outwards oriented, and close to the exact result."""
      counts, _ = logic._vtkCheck(octreePolyData, "octree")
      self.assertEqual(counts["boundaryEdges"], 0)
      self.assertEqual(counts["nonManifoldEdges"], 0)
      kigumiVolume = logic._vtkCheck(kigumiPolyData, "kigumi")[0]["volume"]
      self.assertGreater(counts["volume"], 0)
      self.assertAlmostEqual(counts["volume"], kigumiVolume, delta=0.005 * kigumiVolume)
      distanceFilter = vtk.vtkDistancePolyDataFilter()
      distanceFilter.SetInputData(0, octreePolyData)
      distanceFilter.SetInputData(1, kigumiPolyData)
      distanceFilter.SignedDistanceOff()
      distanceFilter.Update()
      distances = vtk_to_numpy(distanceFilter.GetOutput().GetPointData().GetArray("Distance"))
      self.assertLess(np.mean(distances), 0.1 * voxelSize)

    voxelSize = 0.5
    for operation in ["union", "intersection", "difference", "difference2"]:
      octreeModel = addOutputModel(f"Output {operation} (octree)")
      logic.process(inputModels[0], inputModels[1], octreeModel, operation, backend="octree", voxelSize=voxelSize)
      kigumiModel = addOutputModel(f"Output {operation} (kigumi)")
      logic.process(inputModels[0], inputModels[1], kigumiModel, operation, backend="kigumi")
      checkOctreeResult(octreeModel.GetPolyData(), kigumiModel.GetPolyData(), voxelSize)

    # Several steps
    octreeModel = addOutputModel("Output (A|B)-C (octree)")
    logic.processSteps(inputModels, ["union", "difference"], octreeModel, backend="octree", voxelSize=voxelSize)
    kigumiModel = addOutputModel("Output (A|B)-C (kigumi)")
    logic.processSteps(inputModels, ["union", "difference"], kigumiModel, backend="kigumi")
    checkOctreeResult(octreeModel.GetPolyData(), kigumiModel.GetPolyData(), voxelSize)
    with self.assertRaises(ValueError):
      logic.processSteps(inputModels, ["union"], octreeModel, backend="octree")

    # The orientation of the faces does not matter
    reverseSense = vtk.vtkReverseSense()
    reverseSense.SetInputData(sphere.GetOutput())
    reverseSense.ReverseCellsOn()
    reverseSense.Update()
    insideOutModel = slicer.modules.models.logic().AddModel(reverseSense.GetOutput())
    insideOutResultModel = addOutputModel("Output inside out (octree)")
    logic.process(insideOutModel, inputModels[1], insideOutResultModel, "difference", backend="octree", voxelSize=voxelSize)
    resultModel = addOutputModel("Output (octree)")
    logic.process(inputModels[0], inputModels[1], resultModel, "difference", backend="octree", voxelSize=voxelSize)
    np.testing.assert_array_equal(vtk_to_numpy(insideOutResultModel.GetPolyData().GetPoints().GetData()),
      vtk_to_numpy(resultModel.GetPolyData().GetPoints().GetData()))

    # An empty model represents the empty set
    emptyModel = slicer.modules.models.logic().AddModel(vtk.vtkPolyData())
    logic.process(inputModels[0], emptyModel, resultModel, "union", backend="octree", voxelSize=voxelSize)
    self.assertAlmostEqual(logic._vtkCheck(resultModel.GetPolyData(), "octree")[0]["volume"],
      logic._vtkCheck(sphere.GetOutput(), "octree")[0]["volume"], delta=0.005 * 4 / 3 * np.pi * 20**3)
    logic.process(inputModels[0], emptyModel, resultModel, "intersection", backend="octree", voxelSize=voxelSize)
    self.assertEqual(resultModel.GetPolyData().GetNumberOfPoints(), 0)

    # Models that do not intersect
    farSphere = vtk.vtkSphereSource()
    farSphere.SetCenter(100, 0, 0)
    farSphere.SetRadius(5)
    farSphereModel = slicer.modules.models.logic().AddModel(farSphere.GetOutputPort())
    logic.process(inputModels[0], farSphereModel, resultModel, "intersection", backend="octree")
    self.assertEqual(resultModel.GetPolyData().GetNumberOfPoints(), 0)

    # The automatic voxel size gives 256 voxels along the longest side of the bounds of the result
    combine = logicModule.vtkOctreeBooleanFilter()
    combine.AddInputData(sphere.GetOutput())
    combine.AddInputData(box.GetOutput())
    combine.SetOperation(1, combine.OPER_UNION)
    logic._updateFilter(combine)
    bounds = vtk.vtkBoundingBox()
    bounds.AddBounds(sphere.GetOutput().GetBounds())
    bounds.AddBounds(box.GetOutput().GetBounds())
    self.assertAlmostEqual(combine.GetEffectiveVoxelSize(), bounds.GetMaxLength() / 256)

    # Too many voxels
    combine.SetMaximumNumberOfVoxels(1000)
    with self.assertRaises(RuntimeError):
      logic._updateFilter(combine)

    # Invalid coordinates
    invalidPolyData = vtk.vtkPolyData()
    invalidPolyData.DeepCopy(sphere.GetOutput())
    invalidPolyData.GetPoints().SetPoint(0, float("nan"), 0, 0)
    combine = logicModule.vtkOctreeBooleanFilter()
    combine.AddInputData(invalidPolyData)
    combine.AddInputData(box.GetOutput())
    with self.assertRaises(RuntimeError):
      logic._updateFilter(combine)

    self.delayDisplay('Octree test passed')
