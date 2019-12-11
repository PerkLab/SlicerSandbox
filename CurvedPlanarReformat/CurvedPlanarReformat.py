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
    self.ui.inputVolumeSelector.setMRMLScene(slicer.mrmlScene)
    self.ui.curveResolutionSliderWidget.setMRMLScene(slicer.mrmlScene)
    self.ui.sliceResolutionSliderWidget.setMRMLScene(slicer.mrmlScene)
    self.ui.sliceSizeCoordinatesWidget.setMRMLScene(slicer.mrmlScene)
    
    self.ui.outputStraightenedVolumeSelector.setMRMLScene(slicer.mrmlScene)
    self.ui.outputProjectedVolumeSelector.setMRMLScene(slicer.mrmlScene)

    # connections
    self.ui.applyButton.connect('clicked(bool)', self.onApplyButton)
    self.ui.inputCurveSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelect)
    self.ui.inputVolumeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelect)
    self.ui.outputStraightenedVolumeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelect)
    self.ui.outputProjectedVolumeSelector.connect("currentNodeChanged(vtkMRMLNode*)", self.onSelect)

    # Add vertical spacer
    self.layout.addStretch(1)

    # Refresh Apply button state
    self.onSelect()

  def cleanup(self):
    pass

  def onSelect(self):
    validInput = (self.ui.inputCurveSelector.currentNode() and self.ui.inputVolumeSelector.currentNode()
      and self.ui.curveResolutionSliderWidget.value > 0 and self.ui.sliceResolutionSliderWidget.value > 0)
    # at least straightened volume must be valid
    validOutput = self.ui.outputStraightenedVolumeSelector.currentNode()
    self.ui.applyButton.enabled = validInput and validOutput

  def onApplyButton(self):
    logic = CurvedPlanarReformatLogic()

    straightenedVolume = self.ui.outputStraightenedVolumeSelector.currentNode()
    curveNode = self.ui.inputCurveSelector.currentNode()
    volumeNode = self.ui.inputVolumeSelector.currentNode()
    rotationAngleDeg = self.ui.rotationAngleSliderWidget.value
    spacingAlongCurveMm = self.ui.curveResolutionSliderWidget.value
    sliceResolutionMm = self.ui.sliceResolutionSliderWidget.value
    sliceSizeMm = [float(s) for s in self.ui.sliceSizeCoordinatesWidget.coordinates.split(',')]
    spacingMm = [sliceResolutionMm, sliceResolutionMm, spacingAlongCurveMm]
    if not logic.straightenVolume(straightenedVolume, curveNode, volumeNode, sliceSizeMm, spacingMm, rotationAngleDeg):
      logging.error("CPR straightenVolume failed")
      return

    projectedVolume = self.ui.outputProjectedVolumeSelector.currentNode()
    if projectedVolume:
      if not logic.projectVolume(projectedVolume, straightenedVolume):
        logging.error("CPR projectVolume failed")

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

  def straightenVolume(self, outputStraightenedVolume, curveNode, volumeNode, sliceSizeMm, outputSpacingMm, rotationAngleDeg=0.0):
    """
    Compute straightened volume (useful for example for visualization of curved vessels)
    """
    originalCurvePoints = curveNode.GetCurvePointsWorld()
    sampledPoints = vtk.vtkPoints()
    if not slicer.vtkMRMLMarkupsCurveNode.ResamplePoints(originalCurvePoints, sampledPoints, outputSpacingMm[2], False):
      return False

    sliceExtent = [int(sliceSizeMm[0]/outputSpacingMm[0]), int(sliceSizeMm[1]/outputSpacingMm[1])]
    inputSpacing = volumeNode.GetSpacing()

    lines = vtk.vtkCellArray()
    lines.InsertNextCell(sampledPoints.GetNumberOfPoints())
    for pointIndex in range(sampledPoints.GetNumberOfPoints()):
      lines.InsertCellPoint(pointIndex)
    sampledCurvePoly = vtk.vtkPolyData()
    sampledCurvePoly.SetPoints(sampledPoints)
    sampledCurvePoly.SetLines(lines)

    # Get physical coordinates from voxel coordinates
    volumeRasToIjkTransformMatrix = vtk.vtkMatrix4x4()
    volumeNode.GetRASToIJKMatrix(volumeRasToIjkTransformMatrix)

    transformWorldToVolumeRas = vtk.vtkMatrix4x4()
    slicer.vtkMRMLTransformNode.GetMatrixTransformBetweenNodes(None, volumeNode.GetParentTransformNode(), transformWorldToVolumeRas)

    transformWorldToIjk = vtk.vtkTransform()
    transformWorldToIjk.Concatenate(transformWorldToVolumeRas)
    transformWorldToIjk.Scale(inputSpacing)
    transformWorldToIjk.Concatenate(volumeRasToIjkTransformMatrix)

    transformPolydataWorldToIjk = vtk.vtkTransformPolyDataFilter()
    transformPolydataWorldToIjk.SetInputData(sampledCurvePoly)
    transformPolydataWorldToIjk.SetTransform(transformWorldToIjk)

    reslicer = vtk.vtkSplineDrivenImageSlicer()
    append = vtk.vtkImageAppend()

    scaledImageData = vtk.vtkImageData()
    scaledImageData.ShallowCopy(volumeNode.GetImageData())
    scaledImageData.SetSpacing(inputSpacing)

    reslicer.SetInputData(scaledImageData)
    reslicer.SetPathConnection(transformPolydataWorldToIjk.GetOutputPort())
    reslicer.SetSliceExtent(*sliceExtent)
    reslicer.SetSliceSpacing(outputSpacingMm[0], outputSpacingMm[1])
    reslicer.SetIncidence(vtk.vtkMath.RadiansFromDegrees(rotationAngleDeg))
   
    nbPoints = sampledPoints.GetNumberOfPoints()
    for ptId in reversed(range(nbPoints)):
      reslicer.SetOffsetPoint(ptId)
      reslicer.Update()
      tempSlice = vtk.vtkImageData()
      tempSlice.DeepCopy(reslicer.GetOutput(0))
      append.AddInputData(tempSlice)

    append.SetAppendAxis(2)
    append.Update()
    straightenedVolumeImageData = append.GetOutput()
    straightenedVolumeImageData.SetOrigin(0,0,0)
    straightenedVolumeImageData.SetSpacing(1.0,1.0,1.0)

    dims = straightenedVolumeImageData.GetDimensions()
    ijkToRas = vtk.vtkMatrix4x4()
    ijkToRas.SetElement(0, 0, 0.0)
    ijkToRas.SetElement(1, 0, 0.0)
    ijkToRas.SetElement(2, 0, -outputSpacingMm[0])
    
    ijkToRas.SetElement(0, 1, 0.0)
    ijkToRas.SetElement(1, 1, outputSpacingMm[1])
    ijkToRas.SetElement(2, 1, 0.0)

    ijkToRas.SetElement(0, 2, outputSpacingMm[2])
    ijkToRas.SetElement(1, 2, 0.0)
    ijkToRas.SetElement(2, 2, 0.0)

    outputStraightenedVolume.SetIJKToRASMatrix(ijkToRas)
    outputStraightenedVolume.SetAndObserveImageData(straightenedVolumeImageData)

    return True

  def projectVolume(self, outputProjectedVolume, inputStraightenedVolume, projectionAxisIndex = 1):
    """Create panoramic volume by mean intensity projection along an axis of the straightened volume
    """

    import numpy as np
    projectedImageData = vtk.vtkImageData()
    outputProjectedVolume.SetAndObserveImageData(projectedImageData)
    straightenedImageData = inputStraightenedVolume.GetImageData()

    outputImageDimensions = list(straightenedImageData.GetDimensions())
    outputImageDimensions[projectionAxisIndex] = 1
    projectedImageData.SetDimensions(outputImageDimensions)

    projectedImageData.AllocateScalars(straightenedImageData.GetScalarType(), straightenedImageData.GetNumberOfScalarComponents())
    outputProjectedVolumeArray = slicer.util.arrayFromVolume(outputProjectedVolume)
    inputStraightenedVolumeArray = slicer.util.arrayFromVolume(inputStraightenedVolume)
    
    if projectionAxisIndex == 0:
      outputProjectedVolumeArray[0, :, :] = inputStraightenedVolumeArray.mean(projectionAxisIndex)
    else:
      outputProjectedVolumeArray[:, 0, :] = inputStraightenedVolumeArray.mean(projectionAxisIndex)

    slicer.util.arrayFromVolumeModified(outputProjectedVolume)
    
    ijkToRas = vtk.vtkMatrix4x4()
    inputStraightenedVolume.GetIJKToRASMatrix(ijkToRas)
    outputProjectedVolume.SetIJKToRASMatrix(ijkToRas)

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

    logic = CurvedPlanarReformatLogic()
    straightenedVolume = slicer.modules.volumes.logic().CloneVolume(volumeNode, volumeNode.GetName()+' straightened')
    self.assertTrue(logic.straightenVolume(straightenedVolume, curveNode, volumeNode, [40.0, 40.0], [0.5,0.5,1.0]))

    panoramicVolume = slicer.modules.volumes.logic().CloneVolume(straightenedVolume, straightenedVolume.GetName()+' panoramic')
    self.assertTrue(logic.projectVolume(panoramicVolume, straightenedVolume))

    slicer.mrmlScene.GetNodeByID('vtkMRMLSliceNodeRed').SetOrientationToCoronal()
    slicer.util.setSliceViewerLayers(background=panoramicVolume, fit=True)

    self.delayDisplay('Test passed!')
