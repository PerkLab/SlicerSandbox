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
    self.ui.outputTransformToStraightenedVolumeSelector.setMRMLScene(slicer.mrmlScene)

    self.ui.outputStraightenedVolumeSelector.setMRMLScene(slicer.mrmlScene)
    self.ui.outputProjectedVolumeSelector.setMRMLScene(slicer.mrmlScene)

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
    validInput = (self.ui.inputCurveSelector.currentNode() and self.ui.inputVolumeSelector.currentNode()
      and self.ui.curveResolutionSliderWidget.value > 0 and self.ui.sliceResolutionSliderWidget.value > 0)
    # at least straightened volume or transform must be valid
    validOutput = self.ui.outputStraightenedVolumeSelector.currentNode() or self.ui.outputTransformToStraightenedVolumeSelector.currentNode()
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
    outputTransformToStraightenedNode = self.ui.outputTransformToStraightenedVolumeSelector.currentNode()
    if not logic.straightenVolume(straightenedVolume, curveNode, volumeNode, sliceSizeMm, spacingMm, rotationAngleDeg, outputTransformToStraightenedNode):
      logging.error("CPR straightenVolume failed")
      return

    if self.ui.showOutputCheckBox.checked:
      slicer.util.setSliceViewerLayers(background=straightenedVolume, fit=True, rotateToVolumePlane=True)

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

  def straightenVolume(self, outputStraightenedVolume, curveNode, volumeNode, sliceSizeMm, outputSpacingMm, rotationAngleDeg=0.0, outputTransformToStraightenedNode=None):
    """
    Compute straightened volume (useful for example for visualization of curved vessels)
    """
    resamplingCurveSpacingFactor = 5.0  # There is no need to compute a transform for each slice, we just compute for every 10th
    resamplingCurveSpacing = outputSpacingMm[2] * resamplingCurveSpacingFactor
    originalCurvePoints = curveNode.GetCurvePointsWorld()
    sampledPoints = vtk.vtkPoints()
    if not slicer.vtkMRMLMarkupsCurveNode.ResamplePoints(originalCurvePoints, sampledPoints, resamplingCurveSpacing, False):
      return False

    resampledCurveNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsCurveNode", "CurvedPlanarReformat_resampled_curve_temp")
    resampledCurveNode.SetNumberOfPointsPerInterpolatingSegment(1)
    resampledCurveNode.SetCurveTypeToLinear()
    resampledCurveNode.SetControlPointPositionsWorld(sampledPoints)

    curveLength = resampledCurveNode.GetCurveLengthWorld()
    outputStraightenedVolumeDimensions = [
      int(sliceSizeMm[0]/outputSpacingMm[0]),
      int(sliceSizeMm[1]/outputSpacingMm[1]),
      int(curveLength/outputSpacingMm[2])]

    # Output volume axes
    outputStraightenedVolumeIJKToRASArray = np.eye(4)
    # Z axis (from first curve point to last, this will be the straightened curve long axis)
    curveStartPoint = np.zeros(3)
    curveEndPoint = np.zeros(3)
    resampledCurveNode.GetNthControlPointPositionWorld(0, curveStartPoint)
    resampledCurveNode.GetNthControlPointPositionWorld(resampledCurveNode.GetNumberOfControlPoints()-1, curveEndPoint)
    outputStraightenedVolumeAxisZ = (curveEndPoint-curveStartPoint)/np.linalg.norm(curveEndPoint-curveStartPoint)
    # Y axis
    curveNodePlane = vtk.vtkPlane()
    slicer.modules.markups.logic().GetBestFitPlane(resampledCurveNode, curveNodePlane)
    outputStraightenedVolumeAxisY = np.array(curveNodePlane.GetNormal())
    # X axis
    outputStraightenedVolumeAxisX = np.cross(outputStraightenedVolumeAxisY, outputStraightenedVolumeAxisZ)
    # Set spacing and orientation
    outputStraightenedVolumeIJKToRASArray[0:3,0] = outputStraightenedVolumeAxisX * outputSpacingMm[0]
    outputStraightenedVolumeIJKToRASArray[0:3,1] = outputStraightenedVolumeAxisY * outputSpacingMm[1]
    outputStraightenedVolumeIJKToRASArray[0:3,2] = outputStraightenedVolumeAxisZ * outputSpacingMm[2]
    # Origin
    outputStraightenedVolumeOrigin = np.array(curveNodePlane.GetOrigin())
    outputStraightenedVolumeOrigin -= outputStraightenedVolumeIJKToRASArray[0:3,0] * outputStraightenedVolumeDimensions[0]/2.0
    outputStraightenedVolumeOrigin -= outputStraightenedVolumeIJKToRASArray[0:3,1] * outputStraightenedVolumeDimensions[1]/2.0
    outputStraightenedVolumeOrigin -= outputStraightenedVolumeIJKToRASArray[0:3,2] * outputStraightenedVolumeDimensions[2]/2.0
    outputStraightenedVolumeIJKToRASArray[0:3, 3] = outputStraightenedVolumeOrigin

    outputStraightenedVolumeIJKToRAS = slicer.util.vtkMatrixFromArray(outputStraightenedVolumeIJKToRASArray)

    numberOfSlices = sampledPoints.GetNumberOfPoints()

    temporaryOutputTransformToStraightenedNode = None
    if not outputTransformToStraightenedNode:
      temporaryOutputTransformToStraightenedNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLTransformNode', 'CurvedPlanarReformat_straightening_transform_temp')
      outputTransformToStraightenedNode = temporaryOutputTransformToStraightenedNode

    # Grid transform is not invertible and there is an issue when 
    gridTransform=True
    if gridTransform:
      # Create grid transform
      # Each corner of each slice is mapped from the original volume's reformatted slice
      # to the straightened volume slice.
      # The grid transform contains one vector at the corner of each slice.
      # The transform is in the same space and orientation as the straightened volume.
      gridImage = vtk.vtkImageData()
      gridImage.SetOrigin(outputStraightenedVolumeOrigin)
      gridImage.SetDimensions(2, 2, numberOfSlices)
      gridImage.SetSpacing(sliceSizeMm[0], sliceSizeMm[1], resamplingCurveSpacing)
      gridImage.AllocateScalars(vtk.VTK_DOUBLE, 3)
      transform = slicer.vtkOrientedGridTransform()
      transform.SetDisplacementGridData(gridImage)
      gridDirectionMatrix = vtk.vtkMatrix4x4()
      gridDirectionMatrix.DeepCopy(outputStraightenedVolumeIJKToRAS)
      scale = [1,1,1]
      slicer.vtkAddonMathUtilities.NormalizeOrientationMatrixColumns(gridDirectionMatrix, scale)
      transform.SetGridDirectionMatrix(gridDirectionMatrix)
      outputTransformToStraightenedNode.SetAndObserveTransformFromParent(transform)
      inputToStraightenedDisplacement_RAS = slicer.util.arrayFromGridTransform(outputTransformToStraightenedNode)

      # gridI, gridJ, gridK: IJK axis indices of the grid transform image
      for gridK in range(numberOfSlices):
        curvePointToWorld = vtk.vtkMatrix4x4()
        resampledCurveNode.GetCurvePointToWorldTransformAtPointIndex(resampledCurveNode.GetCurvePointIndexFromControlPointIndex(gridK)-1, curvePointToWorld)

        rotatedCurvePointToWorld = vtk.vtkTransform()
        rotatedCurvePointToWorld.Concatenate(curvePointToWorld)
        rotatedCurvePointToWorld.RotateZ(rotationAngleDeg)
        curvePointToWorldArray = slicer.util.arrayFromVTKMatrix(rotatedCurvePointToWorld.GetMatrix())

        curveAxisX_RAS = curvePointToWorldArray[0:3, 0]
        curveAxisY_RAS = curvePointToWorldArray[0:3, 1]
        curvePoint_RAS = curvePointToWorldArray[0:3, 3]
        for gridJ in range(2):
          for gridI in range(2):
            outputStraightenedVolume_RAS = outputStraightenedVolumeIJKToRAS.MultiplyPoint([
              gridI*(outputStraightenedVolumeDimensions[0]-1),
              gridJ*(outputStraightenedVolumeDimensions[1]-1),
              gridK * resamplingCurveSpacingFactor, 1])[0:3]
            volumeNode_RAS = curvePoint_RAS + (gridI-0.5)*sliceSizeMm[0]*curveAxisX_RAS + (gridJ-0.5)*sliceSizeMm[1]*curveAxisY_RAS
            inputToStraightenedDisplacement_RAS[gridK][gridJ][gridI] = volumeNode_RAS - outputStraightenedVolume_RAS
      slicer.util.arrayFromGridTransformModified(outputTransformToStraightenedNode)

    else:
      # Create thin-plate-spline transform
      # Center and each corner of each slice is mapped from the original volume's reformatted slice
      # to the straightened volume slice.
      targetLandmarkPoints = vtk.vtkPoints()
      sourceLandmarkPoints = vtk.vtkPoints()
      tps = vtk.vtkThinPlateSplineTransform()
      tps.SetBasisToR()
      tps.SetRegularizeBulkTransform(False)
      tps.SetSourceLandmarks(sourceLandmarkPoints)
      tps.SetTargetLandmarks(targetLandmarkPoints)

      # corner points are not added for each centerline point
      # to allow larger weight for centerline points
      cornerPointsSkip = 8
      centerVoxelIndex = [math.floor(outputStraightenedVolumeDimensions[0]/2.0), math.floor(outputStraightenedVolumeDimensions[1]/2.0)]
      for gridK in range(numberOfSlices):
        curvePointToWorld = vtk.vtkMatrix4x4()
        curvePointIndex = resampledCurveNode.GetCurvePointIndexFromControlPointIndex(gridK)-1  # TODO: remove -1 after Slicer core bug is fixed
        resampledCurveNode.GetCurvePointToWorldTransformAtPointIndex(curvePointIndex, curvePointToWorld)

        rotatedCurvePointToWorld = vtk.vtkTransform()
        rotatedCurvePointToWorld.Concatenate(curvePointToWorld)
        rotatedCurvePointToWorld.RotateZ(rotationAngleDeg)
        curvePointToWorldArray = slicer.util.arrayFromVTKMatrix(rotatedCurvePointToWorld.GetMatrix())
        curveAxisX_RAS = curvePointToWorldArray[0:3, 0]
        curveAxisY_RAS = curvePointToWorldArray[0:3, 1]
        curvePoint_RAS = curvePointToWorldArray[0:3, 3]
        outputStraightenedVolume_RAS = outputStraightenedVolumeIJKToRAS.MultiplyPoint([centerVoxelIndex[0], centerVoxelIndex[1], gridK*resamplingCurveSpacingFactor, 1])[0:3]
        #outputStraightenedVolume_RAS = [0.0, 0.0, gridK * resamplingCurveSpacing]
        volumeNode_RAS = curvePoint_RAS
        targetLandmarkPoints.InsertNextPoint(volumeNode_RAS)
        sourceLandmarkPoints.InsertNextPoint(outputStraightenedVolume_RAS)
        # only add corner points at every cornerPointsSkip-th slice, and at the last slice
        if (gridK % cornerPointsSkip != 0) and (gridK != numberOfSlices-1):
          continue
        for gridJ in range(2):
          for gridI in range(2):
            #outputStraightenedVolume_RAS = np.array([
            #  (gridI-0.5)*sliceSizeMm[0],
            #  (gridJ-0.5)*sliceSizeMm[1],
            #  gridK * resamplingCurveSpacing])
            outputStraightenedVolume_RAS = outputStraightenedVolumeIJKToRAS.MultiplyPoint([
              gridI*(outputStraightenedVolumeDimensions[0]-1),
              gridJ*(outputStraightenedVolumeDimensions[1]-1),
              gridK*resamplingCurveSpacingFactor, 1])[0:3]
            volumeNode_RAS = curvePoint_RAS + (gridI-0.5)*sliceSizeMm[0]*curveAxisX_RAS + (gridJ-0.5)*sliceSizeMm[1]*curveAxisY_RAS
            targetLandmarkPoints.InsertNextPoint(volumeNode_RAS)
            sourceLandmarkPoints.InsertNextPoint(outputStraightenedVolume_RAS)

      outputTransformToStraightenedNode.SetAndObserveTransformFromParent(tps)

    slicer.mrmlScene.RemoveNode(resampledCurveNode)  # delete temporary curve

    if outputStraightenedVolume:
      # Initialize straightened volume
      outputStraightenedImageData = vtk.vtkImageData()
      outputStraightenedImageData.SetExtent(0, outputStraightenedVolumeDimensions[0]-1,
        0, outputStraightenedVolumeDimensions[1]-1,
        0, outputStraightenedVolumeDimensions[2]-1)
      outputStraightenedImageData.AllocateScalars(volumeNode.GetImageData().GetScalarType(), volumeNode.GetImageData().GetNumberOfScalarComponents())
      outputStraightenedVolume.SetAndObserveImageData(outputStraightenedImageData)
      outputStraightenedVolume.SetIJKToRASMatrix(outputStraightenedVolumeIJKToRAS)

      # Resample input volume to straightened volume
      parameters = {}
      parameters["inputVolume"] = volumeNode.GetID()
      parameters["outputVolume"] = outputStraightenedVolume.GetID()
      parameters["referenceVolume"] = outputStraightenedVolume.GetID()
      parameters["transformationFile"] = outputTransformToStraightenedNode.GetID()
      resamplerModule = slicer.modules.resamplescalarvectordwivolume
      parameterNode = slicer.cli.runSync(resamplerModule, None, parameters)

      outputStraightenedVolume.CreateDefaultDisplayNodes()
      outputStraightenedVolume.GetDisplayNode().CopyContent(volumeNode.GetDisplayNode())
      slicer.mrmlScene.RemoveNode(parameterNode)

    if temporaryOutputTransformToStraightenedNode:
      slicer.mrmlScene.RemoveNode(temporaryOutputTransformToStraightenedNode)

    return True

  def projectVolume(self, outputProjectedVolume, inputStraightenedVolume, projectionAxisIndex = 0):
    """Create panoramic volume by mean intensity projection along an axis of the straightened volume
    """

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
      outputProjectedVolumeArray[:, :, 0] = inputStraightenedVolumeArray.mean(2-projectionAxisIndex)
    elif projectionAxisIndex == 1:
      outputProjectedVolumeArray[:, 0, :] = inputStraightenedVolumeArray.mean(2-projectionAxisIndex)
    else:
      outputProjectedVolumeArray[0, :, :] = inputStraightenedVolumeArray.mean(2-projectionAxisIndex)

    slicer.util.arrayFromVolumeModified(outputProjectedVolume)

    # Shift projection image into the center of the input image
    ijkToRas = vtk.vtkMatrix4x4()
    inputStraightenedVolume.GetIJKToRASMatrix(ijkToRas)
    curvePointToWorldArray = slicer.util.arrayFromVTKMatrix(ijkToRas)
    origin = curvePointToWorldArray[0:3, 3]
    offsetToCenterDirectionVector = curvePointToWorldArray[0:3, projectionAxisIndex]
    offsetToCenterDirectionLength = inputStraightenedVolume.GetImageData().GetDimensions()[projectionAxisIndex] * inputStraightenedVolume.GetSpacing()[projectionAxisIndex]
    newOrigin = origin + offsetToCenterDirectionVector * offsetToCenterDirectionLength
    ijkToRas.SetElement(0, 3, newOrigin[0])
    ijkToRas.SetElement(1, 3, newOrigin[1])
    ijkToRas.SetElement(2, 3, newOrigin[2])
    outputProjectedVolume.SetIJKToRASMatrix(ijkToRas)
    outputProjectedVolume.CreateDefaultDisplayNodes()

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
    outputTransformToStraightenedNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLTransformNode', 'Straightening transform')
    self.assertTrue(logic.straightenVolume(straightenedVolume, curveNode, volumeNode, [40.0, 40.0], [0.5,0.5,1.0], 0.0, outputTransformToStraightenedNode))

    panoramicVolume = slicer.modules.volumes.logic().CloneVolume(straightenedVolume, straightenedVolume.GetName()+' panoramic')
    self.assertTrue(logic.projectVolume(panoramicVolume, straightenedVolume))

    slicer.mrmlScene.GetNodeByID('vtkMRMLSliceNodeRed').SetOrientationToCoronal()
    slicer.util.setSliceViewerLayers(background=straightenedVolume, fit=True, rotateToVolumePlane=True)

    self.delayDisplay('Test passed!')
