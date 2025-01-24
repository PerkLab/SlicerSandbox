import math
import numpy as np
import os
import unittest
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
import logging

#
# CurvedPlanarReformat
#

class CurvedPlanarReformat(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Curved Planar Reformat"
    self.parent.categories = ["Converters"]
    self.parent.dependencies = []
    self.parent.contributors = ["Andras Lasso (PerkLab, Queen's)"]
    self.parent.helpText = """
This is an example of scripted loadable module bundled in an extension.
It performs a simple thresholding on the input volume and optionally captures a screenshot.
"""
    self.parent.helpText += self.getDefaultModuleDocumentationLink()
    self.parent.acknowledgementText = """
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc.
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
""" # replace with organization, grant and thanks.

#
# CurvedPlanarReformatWidget
#

class CurvedPlanarReformatWidget(ScriptedLoadableModuleWidget):
  """Uses ScriptedLoadableModuleWidget base class, available at:
  https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def setup(self):
    ScriptedLoadableModuleWidget.setup(self)

    # Load widget from .ui file (created by Qt Designer)
    uiWidget = slicer.util.loadUI(self.resourcePath('UI/CurvedPlanarReformat.ui'))
    self.layout.addWidget(uiWidget)
    self.ui = slicer.util.childWidgetVariables(uiWidget)

    self.ui.inputCurveSelector.setMRMLScene(slicer.mrmlScene)
    self.ui.markupsPlaceWidget.setMRMLScene(slicer.mrmlScene)
    self.ui.inputVolumeSelector.setMRMLScene(slicer.mrmlScene)
    self.ui.curveResolutionSliderWidget.setMRMLScene(slicer.mrmlScene)
    self.ui.sliceResolutionSliderWidget.setMRMLScene(slicer.mrmlScene)
    self.ui.sliceSizeCoordinatesWidget.setMRMLScene(slicer.mrmlScene)
    self.ui.outputTransformToStraightenedVolumeSelector.setMRMLScene(slicer.mrmlScene)

    self.ui.outputStraightenedVolumeSelector.setMRMLScene(slicer.mrmlScene)
    self.ui.outputProjectedVolumeSelector.setMRMLScene(slicer.mrmlScene)
    self.ui.outputReslicingPlanesModelSelector.setMRMLScene(slicer.mrmlScene)

    # connections
    self.ui.applyButton.connect('clicked(bool)', self.onApplyButton)
    self.ui.inputCurveSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelect)
    self.ui.inputVolumeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelect)
    self.ui.outputStraightenedVolumeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelect)
    self.ui.outputProjectedVolumeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelect)
    self.ui.outputTransformToStraightenedVolumeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelect)

    # Add vertical spacer
    self.layout.addStretch(1)

    # Refresh Apply button state
    self.onSelect()

  def cleanup(self):
    pass

  def onSelect(self):
    validInput = (self.ui.inputCurveSelector.currentNode()
      and self.ui.inputVolumeSelector.currentNode()
      and self.ui.curveResolutionSliderWidget.value > 0 and self.ui.sliceResolutionSliderWidget.value > 0)
    # at least straightened volume or transform must be valid
    validOutput = (self.ui.outputStraightenedVolumeSelector.currentNode()
      or self.ui.outputProjectedVolumeSelector.currentNode()
      or self.ui.outputTransformToStraightenedVolumeSelector.currentNode())
    self.ui.applyButton.enabled = validInput and validOutput

  def onApplyButton(self):
    logic = CurvedPlanarReformatLogic()

    curveNode = self.ui.inputCurveSelector.currentNode()
    volumeNode = self.ui.inputVolumeSelector.currentNode()
    stretching = self.ui.modeComboBox.currentIndex == 1  # items: straightening = 0, stretching = 1
    stretchingRotation = self.ui.rotationSliderWidget.value
    straighteningTransformNode = self.ui.outputTransformToStraightenedVolumeSelector.currentNode()
    straightenedVolumeNode = self.ui.outputStraightenedVolumeSelector.currentNode()
    projectedVolumeNode = self.ui.outputProjectedVolumeSelector.currentNode()
    spacingAlongCurveMm = self.ui.curveResolutionSliderWidget.value
    sliceResolutionMm = self.ui.sliceResolutionSliderWidget.value
    sliceSizeMm = [float(s) for s in self.ui.sliceSizeCoordinatesWidget.coordinates.split(',')]
    reslicingPlanesModelNode = self.ui.outputReslicingPlanesModelSelector.currentNode()

    temporaryStraighteningTransformNode = None
    temporaryStraightenedVolumeNode = None

    slicer.app.setOverrideCursor(qt.Qt.WaitCursor)
    try:

      # Create temporary transform node if user does not need to save it
      if not straighteningTransformNode:
        temporaryStraighteningTransformNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLTransformNode', 'CurvedPlanarReformat_straightening_transform_temp')
        straighteningTransformNode = temporaryStraighteningTransformNode

      logic.computeStraighteningTransform(straighteningTransformNode, curveNode, sliceSizeMm, spacingAlongCurveMm, stretching, stretchingRotation, reslicingPlanesModelNode)

      if straightenedVolumeNode or projectedVolumeNode:

        # Create temporary straightened volume node if user does not need to save it
        if not straightenedVolumeNode:
          temporaryStraightenedVolumeNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLScalarVolumeNode', 'CurvedPlanarReformat_straightened_volume_temp')
          straightenedVolumeNode = temporaryStraightenedVolumeNode

        spacingMm = [sliceResolutionMm, sliceResolutionMm, spacingAlongCurveMm]
        logic.straightenVolume(straightenedVolumeNode, volumeNode, spacingMm, straighteningTransformNode)

        if projectedVolumeNode:
          logic.projectVolume(projectedVolumeNode, straightenedVolumeNode)

        if self.ui.showOutputCheckBox.checked:
          if straightenedVolumeNode:
            volumeToShow = straightenedVolumeNode
          elif projectedVolumeNode:
            volumeToShow = projectedVolumeNode
          else:
            volumeToShow = None
          if volumeToShow:
            slicer.util.setSliceViewerLayers(background=volumeToShow, fit=True, rotateToVolumePlane=True)

    except Exception as e:
      import traceback
      traceback.print_exc()
      errorMessage = "Curved planar reformat failed: " + str(e)
      slicer.util.errorDisplay(errorMessage)
    slicer.app.restoreOverrideCursor()

    if temporaryStraighteningTransformNode:
      slicer.mrmlScene.RemoveNode(temporaryStraighteningTransformNode)
    if temporaryStraightenedVolumeNode:
      slicer.mrmlScene.RemoveNode(temporaryStraightenedVolumeNode)

#
# CurvedPlanarReformatLogic
#

class CurvedPlanarReformatLogic(ScriptedLoadableModuleLogic):
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
    # there is no need to compute displacement for each slice,
    # we just compute for every n-th to make computation faster and inverse computation more robust
    # (less contradiction because of there is less overlapping between neighbor slices)
    appLogic = slicer.app.applicationLogic()
    resamplerName = "ResampleScalarVectorDWIVolume"
    found = appLogic.IsVolumeResamplerRegistered(resamplerName)
    if not found:
      mesg = f"CurvedPlanarReformat: {resamplerName!r} is not registered"
      raise LookupError(mesg)
    collectionOfSliceLogics = appLogic.GetSliceLogics()
    numSliceLogics = collectionOfSliceLogics.GetNumberOfItems()
    if numSliceLogics == 0:
      mesg = "CurvedPlanarReformat: no SliceLogics found"
      raise LookupError(mesg)
    self.sliceLogic = collectionOfSliceLogics.GetItemAsObject(0)
    self.sliceLogic.CurvedPlanarReformationInit()

  def getPointsProjectedToPlane(self, pointsArray, transformWorldToPlane):
    """
    Returns points projected to the plane coordinate system (plane normal = plane Z axis).
    pointsArray contains each point as a column vector.
    """
    pointsArrayOut = vtk.vtkPoints()
    success = self.sliceLogic.CurvedPlanarReformationGetPointsProjectedToPlane(
      pointsArray, transformWorldToPlane, pointsArrayOut
    )
    if not success:
      raise ValueError("getPointsProjectedToPlane failed")
    return pointsArrayOut

  def computeStraighteningTransform(self, transformToStraightenedNode, curveNode, sliceSizeMm, outputSpacingMm, stretching=False, rotationDeg=0.0, reslicingPlanesModelNode=None):
    """
    Compute straightened volume (useful for example for visualization of curved vessels)
    stretching: if True then stretching transform will be computed, otherwise straightening
    """
    return self.sliceLogic.CurvedPlanarReformationComputeStraighteningTransform(
      transformToStraightenedNode,
      curveNode,
      sliceSizeMm,
      outputSpacingMm,
      stretching,
      rotationDeg,
      reslicingPlanesModelNode,
    )

  def straightenVolume(self, outputStraightenedVolume, volumeNode, outputStraightenedVolumeSpacing, straighteningTransformNode):
    """
    Compute straightened volume (useful for example for visualization of curved vessels)
    """
    return self.sliceLogic.CurvedPlanarReformationStraightenVolume(
      outputStraightenedVolume, volumeNode, outputStraightenedVolumeSpacing, straighteningTransformNode
    )

  def projectVolume(self, outputProjectedVolume, inputStraightenedVolume, projectionAxisIndex = 0):
    """Create panoramic volume by mean intensity projection along an axis of the straightened volume
    """
    return self.sliceLogic.CurvedPlanarReformationProjectVolume(
      outputProjectedVolume, inputStraightenedVolume, projectionAxisIndex
    )

class CurvedPlanarReformatTest(ScriptedLoadableModuleTest):
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
    self.test_CurvedPlanarReformat1()

  def test_CurvedPlanarReformat1(self):
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

    # Get a dental CT scan
    import SampleData
    volumeNode = SampleData.SampleDataLogic().downloadDentalSurgery()[1]

    # Define curve
    curveNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLMarkupsCurveNode')
    curveNode.CreateDefaultDisplayNodes()
    curveNode.GetCurveGenerator().SetNumberOfPointsPerInterpolatingSegment(25) # add more curve points between control points than the default 10
    curveNode.AddControlPoint(vtk.vtkVector3d(-45.85526315789473, -104.59210526315789, 74.67105263157896))
    curveNode.AddControlPoint(vtk.vtkVector3d(-50.9078947368421, -90.06578947368418, 66.4605263157895))
    curveNode.AddControlPoint(vtk.vtkVector3d(-62.27631578947368, -78.06578947368419, 60.7763157894737))
    curveNode.AddControlPoint(vtk.vtkVector3d(-71.86705891666716, -58.04403581456746, 57.84679891116521))
    curveNode.AddControlPoint(vtk.vtkVector3d(-74.73084356325877, -48.67611043794342, 57.00664267528636))
    curveNode.AddControlPoint(vtk.vtkVector3d(-88.17105263157895, -35.75, 55.092105263157904))
    curveNode.AddControlPoint(vtk.vtkVector3d(-99.53947368421052, -35.75, 55.092105263157904))
    curveNode.AddControlPoint(vtk.vtkVector3d(-107.75, -43.96052631578948, 55.092105263157904))
    curveNode.AddControlPoint(vtk.vtkVector3d(-112.80263157894736, -59.118421052631575, 56.355263157894754))
    curveNode.AddControlPoint(vtk.vtkVector3d(-115.32894736842104, -73.01315789473684, 60.144736842105274))
    curveNode.AddControlPoint(vtk.vtkVector3d(-125.43421052631578, -83.74999999999999, 60.7763157894737))
    curveNode.AddControlPoint(vtk.vtkVector3d(-132.3815789473684, -91.96052631578947, 63.934210526315795))
    curveNode.AddControlPoint(vtk.vtkVector3d(-137.43421052631578, -103.96052631578947, 67.72368421052633))

    fieldOfView = [40.0, 40.0]
    outputSpacing = [0.5, 0.5, 1.0]

    logic = CurvedPlanarReformatLogic()

    straighteningTransformNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLTransformNode', 'Straightening transform')
    logic.computeStraighteningTransform(straighteningTransformNode, curveNode, fieldOfView, outputSpacing[2])

    straightenedVolume = slicer.modules.volumes.logic().CloneVolume(volumeNode, volumeNode.GetName()+' straightened')
    logic.straightenVolume(straightenedVolume, volumeNode, outputSpacing, straighteningTransformNode)

    panoramicVolume = slicer.modules.volumes.logic().CloneVolume(straightenedVolume, straightenedVolume.GetName()+' panoramic')
    logic.projectVolume(panoramicVolume, straightenedVolume)

    slicer.util.setSliceViewerLayers(background=straightenedVolume, fit=True, rotateToVolumePlane=True)

    self.delayDisplay('Test passed!')
