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
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
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
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def setup(self):
    ScriptedLoadableModuleWidget.setup(self)

    # Load widget from .ui file (created by Qt Designer)
    uiWidget = slicer.util.loadUI(self.resourcePath('UI/CurvedPlanarReformat.ui'))
    self.layout.addWidget(uiWidget)
    self.ui = slicer.util.childWidgetVariables(uiWidget)

    self.ui.inputCurveSelector.setMRMLScene(slicer.mrmlScene)
    self.ui.markupsPlaceWidget.setMRMLScene(slicer.mrmlScene)
    self.ui.inputSliceSelector.setMRMLScene(slicer.mrmlScene)
    self.ui.curveResolutionSliderWidget.setMRMLScene(slicer.mrmlScene)
    self.ui.fieldOfViewSliderWidget.setMRMLScene(slicer.mrmlScene)
    
    self.ui.outputStraightenedVolumeSelector.setMRMLScene(slicer.mrmlScene)
    self.ui.outputProjectedVolumeSelector.setMRMLScene(slicer.mrmlScene)

    # connections
    self.ui.applyButton.connect('clicked(bool)', self.onApplyButton)
    self.ui.inputCurveSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelect)
    self.ui.inputSliceSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelect)
    self.ui.outputStraightenedVolumeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelect)
    self.ui.outputProjectedVolumeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelect)

    # Add vertical spacer
    self.layout.addStretch(1)

    # Refresh Apply button state
    self.onSelect()

  def cleanup(self):
    pass

  def onSelect(self):
    validInput = (self.ui.inputCurveSelector.currentNode() and self.ui.inputSliceSelector.currentNode()
      and self.ui.curveResolutionSliderWidget.value > 0 and self.ui.fieldOfViewSliderWidget.value > 0)
    # at least straightened volume must be valid
    validOutput = self.ui.outputStraightenedVolumeSelector.currentNode()
    self.ui.applyButton.enabled = validInput and validOutput

  def onApplyButton(self):
    logic = CurvedPlanarReformatLogic()

    straightenedVolume = self.ui.outputStraightenedVolumeSelector.currentNode()
    curveNode = self.ui.inputCurveSelector.currentNode()
    sliceNode = self.ui.inputSliceSelector.currentNode()
    rotationAngleDeg = self.ui.rotationAngleSliderWidget.value
    spacingAlongCurve = self.ui.curveResolutionSliderWidget.value
    fieldOfView = self.ui.fieldOfViewSliderWidget.value
    if not logic.straightenVolume(straightenedVolume, curveNode, sliceNode, rotationAngleDeg, fieldOfView, spacingAlongCurve):
      logging.error("CPR straightenVolume failed")
      return

    projectedVolume = self.ui.outputProjectedVolumeSelector.currentNode()
    if not logic.projectVolume(projectedVolume, straightenedVolume):
      logging.error("CPR projectVolume failed")
      return

    #sliceNode.SetOrientationToAxial()
    #slicer.util.setSliceViewerLayers(background=panoramicVolume, fit=True)

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
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def straightenVolume(self, outputStraightenedVolume, curveNode, sliceNode, rotationAngleDeg, fieldOfView, spacingAlongCurve):
    """
    Compute straightened volume (useful for example for visualization of curved vessels)
    """
    originalCurvePoints = curveNode.GetCurvePointsWorld()
    sampledPoints = vtk.vtkPoints()
    if not slicer.vtkMRMLMarkupsCurveNode.ResamplePoints(originalCurvePoints, sampledPoints, spacingAlongCurve, False):
      return False

    resampledCurveNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsCurveNode")
    # add just a few interpolated points between each control point (control points already have full resolution)
    resampledCurveNode.SetNumberOfPointsPerInterpolatingSegment(2)
    resampledCurveNode.SetControlPointPositionsWorld(sampledPoints)

    originalFieldOfView = sliceNode.GetFieldOfView()
    currentFieldOfView = [fieldOfView, originalFieldOfView[1] * fieldOfView / originalFieldOfView[0], originalFieldOfView[2]]
    sliceNode.SetFieldOfView(*currentFieldOfView)

    appLogic = slicer.app.applicationLogic()
    sliceLogic = appLogic.GetSliceLogic(sliceNode)
    sliceLayerLogic = sliceLogic.GetBackgroundLayer()
    reslice = sliceLayerLogic.GetReslice()
    reslicedImage = vtk.vtkImageData()

    # Capture a number of slices orthogonal to the curve and append them into a volume.
    # sliceToWorldTransform = curvePointToWorldTransform * RotateZ(rotationAngleDeg)
    curvePointToWorldTransform = vtk.vtkTransform()
    sliceToWorldTransform = vtk.vtkTransform()
    sliceToWorldTransform.Concatenate(curvePointToWorldTransform)
    sliceToWorldTransform.RotateZ(rotationAngleDeg)
    sliceNode.SetXYZOrigin(0,0,0)
    numberOfControlPoints = resampledCurveNode.GetNumberOfControlPoints()
    append = vtk.vtkImageAppend()

    for controlPointIndex in range(numberOfControlPoints):
        curvePointIndex = resampledCurveNode.GetCurvePointIndexFromControlPointIndex(controlPointIndex)

        curvePointToWorldMatrix = vtk.vtkMatrix4x4()
        resampledCurveNode.GetCurvePointToWorldTransformAtPointIndex(curvePointIndex, curvePointToWorldMatrix)
        curvePointToWorldTransform.SetMatrix(curvePointToWorldMatrix)
        sliceToWorldTransform.Update()
        sliceNode.GetSliceToRAS().DeepCopy(sliceToWorldTransform.GetMatrix())
        sliceNode.UpdateMatrices()
        slicer.app.processEvents()
        tempSlice = vtk.vtkImageData()
        tempSlice.DeepCopy(reslice.GetOutput())
        append.AddInputData(tempSlice)

    append.SetAppendAxis(2)
    append.Update()
    straightenedVolumeImageData = append.GetOutput()

    dims = straightenedVolumeImageData.GetDimensions()
    outputStraightenedVolume.SetSpacing(currentFieldOfView[0]/dims[0], currentFieldOfView[1]/dims[1], spacingAlongCurve)
    outputStraightenedVolume.SetAndObserveImageData(straightenedVolumeImageData)

    slicer.mrmlScene.RemoveNode(resampledCurveNode)
    sliceNode.SetFieldOfView(*originalFieldOfView)

    return True

  def projectVolume(self, outputProjectedVolume, inputStraightenedVolume):
    """Create panoramic volume by mean intensity projection along an axis of the straightened volume
    """

    import numpy as np
    projectedImageData = vtk.vtkImageData()
    outputProjectedVolume.SetAndObserveImageData(projectedImageData)
    straightenedImageData = inputStraightenedVolume.GetImageData()
    projectedImageData.SetDimensions(straightenedImageData.GetDimensions()[2], straightenedImageData.GetDimensions()[1], 1)
    projectedImageData.AllocateScalars(straightenedImageData.GetScalarType(), straightenedImageData.GetNumberOfScalarComponents())
    outputProjectedVolumeArray = slicer.util.arrayFromVolume(outputProjectedVolume)
    inputStraightenedVolumeArray = slicer.util.arrayFromVolume(inputStraightenedVolume)
    outputProjectedVolumeArray[0, :, :] = np.flip(inputStraightenedVolumeArray.mean(2).T)
    slicer.util.arrayFromVolumeModified(outputProjectedVolume)
    straightenedImageSpacing = inputStraightenedVolume.GetSpacing()
    outputProjectedVolume.SetSpacing(straightenedImageSpacing[2], straightenedImageSpacing[1], 1.0)

    return True

class CurvedPlanarReformatTest(ScriptedLoadableModuleTest):
  """
  This is the test case for your scripted module.
  Uses ScriptedLoadableModuleTest base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
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

    sliceNode = slicer.mrmlScene.GetNodeByID('vtkMRMLSliceNodeRed')
    rotationAngleDeg = 180
    fieldOfView = 40.0
    spacingAlongCurve = 0.1

    logic = CurvedPlanarReformatLogic()

    straightenedVolume = slicer.modules.volumes.logic().CloneVolume(volumeNode, volumeNode.GetName()+' straightened')
    self.assertTrue(logic.straightenVolume(straightenedVolume, curveNode, sliceNode, rotationAngleDeg, fieldOfView, spacingAlongCurve))

    panoramicVolume = slicer.modules.volumes.logic().CloneVolume(straightenedVolume, straightenedVolume.GetName()+' panoramic')
    self.assertTrue(logic.projectVolume(panoramicVolume, straightenedVolume))

    sliceNode.SetOrientationToAxial()
    slicer.util.setSliceViewerLayers(background=panoramicVolume, fit=True)

    self.delayDisplay('Test passed!')
