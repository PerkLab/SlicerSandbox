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
    straighteningTransformNode = self.ui.outputTransformToStraightenedVolumeSelector.currentNode()
    straightenedVolumeNode = self.ui.outputStraightenedVolumeSelector.currentNode()
    projectedVolumeNode = self.ui.outputProjectedVolumeSelector.currentNode()
    spacingAlongCurveMm = self.ui.curveResolutionSliderWidget.value
    sliceResolutionMm = self.ui.sliceResolutionSliderWidget.value
    sliceSizeMm = [float(s) for s in self.ui.sliceSizeCoordinatesWidget.coordinates.split(',')]

    temporaryStraighteningTransformNode = None
    temporaryStraightenedVolumeNode = None

    slicer.app.setOverrideCursor(qt.Qt.WaitCursor)
    try:

      # Create temporary transform node if user does not need to save it
      if not straighteningTransformNode:
        temporaryStraighteningTransformNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLTransformNode', 'CurvedPlanarReformat_straightening_transform_temp')
        straighteningTransformNode = temporaryStraighteningTransformNode

      logic.computeStraighteningTransform(straighteningTransformNode, curveNode, sliceSizeMm, spacingAlongCurveMm)

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
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self):
    ScriptedLoadableModuleLogic.__init__(self)
    # there is no need to compute displacement for each slice,
    # we just compute for every n-th to make computation faster and inverse computation more robust
    # (less contradiction because of there is less overlapping between neighbor slices)
    self.transformSpacingFactor = 5.0

  def computeStraighteningTransform(self, transformToStraightenedNode, curveNode, sliceSizeMm, outputSpacingMm):
    """
    Compute straightened volume (useful for example for visualization of curved vessels)
    resamplingCurveSpacingFactor: 
    """

    # Create a temporary resampled curve
    resamplingCurveSpacing = outputSpacingMm * self.transformSpacingFactor
    originalCurvePoints = curveNode.GetCurvePointsWorld()
    sampledPoints = vtk.vtkPoints()
    if not slicer.vtkMRMLMarkupsCurveNode.ResamplePoints(originalCurvePoints, sampledPoints, resamplingCurveSpacing, False):
      raise("Redampling curve failed")
    resampledCurveNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsCurveNode", "CurvedPlanarReformat_resampled_curve_temp")
    resampledCurveNode.SetNumberOfPointsPerInterpolatingSegment(1)
    resampledCurveNode.SetCurveTypeToLinear()
    resampledCurveNode.SetControlPointPositionsWorld(sampledPoints)
    numberOfSlices = resampledCurveNode.GetNumberOfControlPoints()

    # Z axis (from first curve point to last, this will be the straightened curve long axis)
    curveStartPoint = np.zeros(3)
    curveEndPoint = np.zeros(3)
    resampledCurveNode.GetNthControlPointPositionWorld(0, curveStartPoint)
    resampledCurveNode.GetNthControlPointPositionWorld(resampledCurveNode.GetNumberOfControlPoints()-1, curveEndPoint)
    transformGridAxisZ = (curveEndPoint-curveStartPoint)/np.linalg.norm(curveEndPoint-curveStartPoint)
  
    # X axis = average X axis of curve, to minimize torsion (and so have a simple displacement field, which can be robustly inverted)
    sumCurveAxisX_RAS = np.zeros(3)
    for gridK in range(numberOfSlices):
      curvePointToWorld = vtk.vtkMatrix4x4()
      resampledCurveNode.GetCurvePointToWorldTransformAtPointIndex(resampledCurveNode.GetCurvePointIndexFromControlPointIndex(gridK), curvePointToWorld)
      curvePointToWorldArray = slicer.util.arrayFromVTKMatrix(curvePointToWorld)
      curveAxisX_RAS = curvePointToWorldArray[0:3, 0]
      sumCurveAxisX_RAS += curveAxisX_RAS
    meanCurveAxisX_RAS = sumCurveAxisX_RAS/np.linalg.norm(sumCurveAxisX_RAS)
    transformGridAxisX = meanCurveAxisX_RAS

    # Y axis
    transformGridAxisY = np.cross(transformGridAxisZ, transformGridAxisX)
    transformGridAxisY = transformGridAxisY/np.linalg.norm(transformGridAxisY)

    # Make sure that X axis is orthogonal to Y and Z
    transformGridAxisX = np.cross(transformGridAxisY, transformGridAxisZ)
    transformGridAxisX = transformGridAxisX/np.linalg.norm(transformGridAxisX)

    # Origin (makes the grid centered at the curve)
    curveLength = resampledCurveNode.GetCurveLengthWorld()
    curveNodePlane = vtk.vtkPlane()
    slicer.modules.markups.logic().GetBestFitPlane(resampledCurveNode, curveNodePlane)
    transformGridOrigin = np.array(curveNodePlane.GetOrigin())
    transformGridOrigin -= transformGridAxisX * sliceSizeMm[0]/2.0
    transformGridOrigin -= transformGridAxisY * sliceSizeMm[1]/2.0
    transformGridOrigin -= transformGridAxisZ * curveLength/2.0

    # Create grid transform
    # Each corner of each slice is mapped from the original volume's reformatted slice
    # to the straightened volume slice.
    # The grid transform contains one vector at the corner of each slice.
    # The transform is in the same space and orientation as the straightened volume.

    gridDimensions = [2, 2, numberOfSlices]
    gridSpacing = [sliceSizeMm[0], sliceSizeMm[1], resamplingCurveSpacing]
    gridDirectionMatrixArray = np.eye(4)
    gridDirectionMatrixArray[0:3, 0] = transformGridAxisX
    gridDirectionMatrixArray[0:3, 1] = transformGridAxisY
    gridDirectionMatrixArray[0:3, 2] = transformGridAxisZ
    gridDirectionMatrix = slicer.util.vtkMatrixFromArray(gridDirectionMatrixArray)

    gridImage = vtk.vtkImageData()
    gridImage.SetOrigin(transformGridOrigin)
    gridImage.SetDimensions(gridDimensions)
    gridImage.SetSpacing(gridSpacing)
    gridImage.AllocateScalars(vtk.VTK_DOUBLE, 3)
    transform = slicer.vtkOrientedGridTransform()
    transform.SetDisplacementGridData(gridImage)
    transform.SetGridDirectionMatrix(gridDirectionMatrix)
    transformToStraightenedNode.SetAndObserveTransformFromParent(transform)

    # Compute displacements
    transformDisplacements_RAS = slicer.util.arrayFromGridTransform(transformToStraightenedNode)
    for gridK in range(gridDimensions[2]):
      curvePointToWorld = vtk.vtkMatrix4x4()
      resampledCurveNode.GetCurvePointToWorldTransformAtPointIndex(resampledCurveNode.GetCurvePointIndexFromControlPointIndex(gridK), curvePointToWorld)
      curvePointToWorldArray = slicer.util.arrayFromVTKMatrix(curvePointToWorld)
      curveAxisX_RAS = curvePointToWorldArray[0:3, 0]
      curveAxisY_RAS = curvePointToWorldArray[0:3, 1]
      curvePoint_RAS = curvePointToWorldArray[0:3, 3]
      for gridJ in range(gridDimensions[1]):
        for gridI in range(gridDimensions[0]):
          straightenedVolume_RAS = (transformGridOrigin
            + gridI*gridSpacing[0]*transformGridAxisX
            + gridJ*gridSpacing[1]*transformGridAxisY
            + gridK*gridSpacing[2]*transformGridAxisZ)
          inputVolume_RAS = (curvePoint_RAS
            + (gridI-0.5)*sliceSizeMm[0]*curveAxisX_RAS
            + (gridJ-0.5)*sliceSizeMm[1]*curveAxisY_RAS)
          transformDisplacements_RAS[gridK][gridJ][gridI] = inputVolume_RAS - straightenedVolume_RAS
    slicer.util.arrayFromGridTransformModified(transformToStraightenedNode)

    slicer.mrmlScene.RemoveNode(resampledCurveNode)  # delete temporary curve


  def straightenVolume(self, outputStraightenedVolume, volumeNode, outputStraightenedVolumeSpacing, straighteningTransformNode):
    """
    Compute straightened volume (useful for example for visualization of curved vessels)
    """
    gridTransform = straighteningTransformNode.GetTransformFromParentAs("vtkOrientedGridTransform")
    if not gridTransform:
      raise ValueError("Straightening transform is expected to contain a vtkOrientedGridTransform form parent")

    # Get transformation grid geometry
    gridIjkToRasDirectionMatrix = gridTransform.GetGridDirectionMatrix()
    gridTransformImage = gridTransform.GetDisplacementGrid()
    gridOrigin = gridTransformImage.GetOrigin()
    gridSpacing = gridTransformImage.GetSpacing()
    gridDimensions = gridTransformImage.GetDimensions()
    gridExtentMm = [gridSpacing[0]*(gridDimensions[0]-1), gridSpacing[1]*(gridDimensions[1]-1), gridSpacing[2]*(gridDimensions[2]-1)]

    # Compute IJK to RAS matrix of output volume
    # Get grid axis directions
    straightenedVolumeIJKToRASArray = slicer.util.arrayFromVTKMatrix(gridIjkToRasDirectionMatrix)
    # Apply scaling
    straightenedVolumeIJKToRASArray = np.dot(straightenedVolumeIJKToRASArray,
      np.diag([outputStraightenedVolumeSpacing[0], outputStraightenedVolumeSpacing[1], outputStraightenedVolumeSpacing[2], 1]))
    # Set origin
    straightenedVolumeIJKToRASArray[0:3,3] = gridOrigin 

    outputStraightenedImageData = vtk.vtkImageData()
    outputStraightenedImageData.SetExtent(
      0, int(gridExtentMm[0]/outputStraightenedVolumeSpacing[0])-1,
      0, int(gridExtentMm[1]/outputStraightenedVolumeSpacing[1])-1,
      0, int(gridExtentMm[2]/outputStraightenedVolumeSpacing[2])-1)
    outputStraightenedImageData.AllocateScalars(volumeNode.GetImageData().GetScalarType(), volumeNode.GetImageData().GetNumberOfScalarComponents())
    outputStraightenedVolume.SetAndObserveImageData(outputStraightenedImageData)
    outputStraightenedVolume.SetIJKToRASMatrix(slicer.util.vtkMatrixFromArray(straightenedVolumeIJKToRASArray))

    # Resample input volume to straightened volume
    parameters = {}
    parameters["inputVolume"] = volumeNode.GetID()
    parameters["outputVolume"] = outputStraightenedVolume.GetID()
    parameters["referenceVolume"] = outputStraightenedVolume.GetID()
    parameters["transformationFile"] = straighteningTransformNode.GetID()
    resamplerModule = slicer.modules.resamplescalarvectordwivolume
    parameterNode = slicer.cli.runSync(resamplerModule, None, parameters)

    outputStraightenedVolume.CreateDefaultDisplayNodes()
    outputStraightenedVolume.GetDisplayNode().CopyContent(volumeNode.GetDisplayNode())
    slicer.mrmlScene.RemoveNode(parameterNode)

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
