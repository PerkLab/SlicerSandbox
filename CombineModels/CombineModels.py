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
This module can perform Boolean operations on model nodes (surface meshes).</a>.
The default backend is kigumi, which computes exact results; vtkbool can be selected in the Advanced section.
"""
    # TODO: replace with organization, grant and thanks
    self.parent.acknowledgementText = """
The module uses https://github.com/unageek/kigumi and https://github.com/zippy84/vtkbool for processing.
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

    for backend in self.logic.availableBackends():
      self.ui.backendComboBox.addItem(backend)
    self.ui.backendComboBox.currentTextChanged.connect(self.updateParameterNodeFromGUI)

    # Spin Boxes
    self.ui.numberOfRetriesSpinBox.valueChanged.connect(self.updateParameterNodeFromGUI)
    self.ui.randomTranslationMagnitudeSpinBox.valueChanged.connect(self.updateParameterNodeFromGUI)

    # Further steps
    self.ui.addStepButton.connect('clicked(bool)', self.onAddStepButton)
    if "kigumi" not in self.logic.availableBackends():
      self.ui.addStepButton.enabled = False
      self.ui.addStepButton.toolTip = "Further steps require the kigumi backend, which is not available in this build"

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
    elif numberOfSteps > 0 and self._parameterNode.GetParameter("Backend") != "kigumi":
      self.ui.applyButton.toolTip = "Further steps require the kigumi backend (see Advanced section)"
      self.ui.applyButton.enabled = False
    else:
      self.ui.applyButton.toolTip = "Compute output model"
      self.ui.applyButton.enabled = True

    self.ui.toggleVisibilityButton.enabled = (self._parameterNode.GetNodeReference("OutputModel") is not None)

    # translate randomly order of magnitude (value is negative by default)
    randomTranslationMagnitude = int(float(self._parameterNode.GetParameter("randomTranslationMagnitude")))
    self.ui.randomTranslationMagnitudeSpinBox.value = randomTranslationMagnitude

    numberOfRetries = int(self._parameterNode.GetParameter("numberOfRetries"))
    self.ui.numberOfRetriesSpinBox.value = numberOfRetries
    self.ui.numberOfRetriesSpinBox.enabled = numberOfSteps == 0
    if numberOfSteps > 0:
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

    for stepIndex, stepWidgets in enumerate(self._stepWidgets):
      self._parameterNode.SetParameter(f"StepOperation{stepIndex}", stepWidgets["operation"].currentData)
      self._parameterNode.SetNodeReferenceID(f"StepModel{stepIndex}", stepWidgets["model"].currentNodeID)

    self._parameterNode.EndModify(wasModified)

  def _numberOfSteps(self):
    return int(self._parameterNode.GetParameter("NumberOfAdditionalSteps") or 0)

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
          self._parameterNode.GetParameter("triangulateInputs") == "True"
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
        self._parameterNode.GetParameter("Backend")
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
    return backends

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
      backend = None
    ):
    """
    Run the processing algorithm.
    Can be used without GUI widget.
    :param inputModelA: first input model node
    :param inputModelB: second input model node
    :param outputModel: result model node, if empty then a new output node will be created
    :param operation: union, intersection, difference, difference2
    :param numberOfRetries: number of retries if operation fails
    :param randomTranslationMagnitude: order of magnitude of the random translation
    :param triangulateInputs: triangulate input models before boolean operation
    :param backend: kigumi or vtkbool, if None then the default backend (kigumi) is used
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

  def processSteps(self, inputModels, operations, outputModel, triangulateInputs = False):
    """
    Combine several models in order: the result is
    (((inputModels[0] operations[0] inputModels[1]) operations[1] inputModels[2]) ...).
    Intermediate results are computed exactly and only the final result is rounded,
    which requires the kigumi backend.
    Can be used without GUI widget.
    :param inputModels: list of at least two input model nodes
    :param operations: list of len(inputModels)-1 operations, each of them union, intersection,
      difference (result of the previous steps minus the model), or difference2 (the model minus the result)
    :param outputModel: result model node
    :param triangulateInputs: triangulate input models before boolean operation
    """

    if len(inputModels) < 2 or not all(inputModels) or not outputModel:
      raise ValueError("Input or output model nodes are invalid")
    if len(operations) != len(inputModels) - 1:
      raise ValueError(f"Expected {len(inputModels) - 1} operations for {len(inputModels)} input models, got {len(operations)}")
    if "kigumi" not in self.availableBackends():
      raise ValueError("Multi-step operations require the kigumi backend, which is not available in this build")

    import vtkSlicerCombineModelsModuleLogicPython as logicModule
    operModes = {
      "union": logicModule.vtkKigumiBooleanFilter.OPER_UNION,
      "intersection": logicModule.vtkKigumiBooleanFilter.OPER_INTERSECTION,
      "difference": logicModule.vtkKigumiBooleanFilter.OPER_DIFFERENCE,
      "difference2": logicModule.vtkKigumiBooleanFilter.OPER_DIFFERENCE2,
    }
    for operation in operations:
      if operation not in operModes:
        raise ValueError("Invalid operation: "+str(operation))

    import time
    startTime = time.time()
    logging.info(f'Processing started (backend: kigumi, {len(operations)} steps)')

    combine = logicModule.vtkKigumiBooleanSequenceFilter()
    for index, operation in enumerate(operations):
      combine.SetOperation(index + 1, operModes[operation])
    for inputModel in inputModels:
      combine.AddInputData(self._polyDataInOutputCoordinates(inputModel, outputModel, triangulateInputs))

    # Report errors of the filter (e.g., self-intersecting inputs) as an exception
    errors = []
    @vtk.calldata_type(vtk.VTK_STRING)
    def onError(caller, event, message):
      errors.append(message)
    errorObserver = combine.AddObserver(vtk.vtkCommand.ErrorEvent, onError)
    combine.Update()
    combine.RemoveObserver(errorObserver)
    if errors:
      # Keep only the text after "vtkKigumiBooleanSequenceFilter (0x...): "
      raise RuntimeError(errors[0].strip().splitlines()[-1].split("): ", 1)[-1])

    self._setOutputPolyData(outputModel, combine.GetOutput())

    stopTime = time.time()
    logging.info('Processing completed in {0:.2f} seconds'.format(stopTime-startTime))

  def _polyDataInOutputCoordinates(self, inputModel, outputModel, triangulateInputs):
    """
    Return the polydata of inputModel in the coordinate system of outputModel, triangulated if requested.
    """
    transformToOutput = vtk.vtkGeneralTransform()
    slicer.vtkMRMLTransformNode.GetTransformBetweenNodes(inputModel.GetParentTransformNode(), outputModel.GetParentTransformNode(), transformToOutput)
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

    self.delayDisplay('Multi-step test passed')
