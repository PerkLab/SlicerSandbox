"""Speed and accuracy benchmark of the octree backend of Combine Models, against kigumi's exact results.

Run one configuration per Slicer process, so that the peak memory is meaningful:

  Slicer --no-main-window --python-script CombineModelsOctreeBenchmark.py -- <case> <backend> [<voxelSize>] [<extraLevels>] [<threads>] [<cacheDirectory>]

case is one of the keys of CASES. backend is one of: octree, kigumi, vtkbool, or prepare, which only builds the
inputs and kigumi's result of the case and caches them in cacheDirectory (default: the temporary directory).
voxelSize is in mm, 0 chooses it automatically. threads 0 uses all threads.
The cases "mandible..." use the sample segmentations of SlicerBoneReconstructionPlanner, which are downloaded.
One line is printed: "BENCHMARK" followed by key=value pairs.
"""
import os
import resource
import statistics
import sys
import tempfile
import time

import numpy as np
import vtk
from vtk.util.numpy_support import numpy_to_vtk, vtk_to_numpy

import slicer

import vtkSlicerCombineModelsModuleLogicPython as logicModule


def triangulated(polyData):
  triangleFilter = vtk.vtkTriangleFilter()
  triangleFilter.SetInputData(polyData)
  triangleFilter.Update()
  return triangleFilter.GetOutput()


def transformed(polyData, transform):
  transformFilter = vtk.vtkTransformPolyDataFilter()
  transformFilter.SetInputData(polyData)
  transformFilter.SetTransform(transform)
  transformFilter.Update()
  return transformFilter.GetOutput()


def rotation(center, angles):
  """Rotation about the X, Y and Z axes through center, angles in degrees."""
  transform = vtk.vtkTransform()
  transform.Translate(center)
  transform.RotateX(angles[0])
  transform.RotateY(angles[1])
  transform.RotateZ(angles[2])
  transform.Translate([-c for c in center])
  return transform


def sphere(center, radius, resolution=200):
  source = vtk.vtkSphereSource()
  source.SetCenter(center)
  source.SetRadius(radius)
  source.SetThetaResolution(resolution)
  source.SetPhiResolution(resolution)
  source.Update()
  return source.GetOutput()


def cylinder(center, radius, height, resolution=200):
  source = vtk.vtkCylinderSource()
  source.SetCenter(center)
  source.SetRadius(radius)
  source.SetHeight(height)
  source.SetResolution(resolution)
  source.Update()
  return triangulated(source.GetOutput())


def box(bounds, angles=(0, 0, 0), center=None):
  """Box with the given bounds, rotated by angles about center (default: its own center)."""
  source = vtk.vtkCubeSource()
  source.SetBounds(bounds)
  source.Update()
  if center is None:
    center = [(bounds[0] + bounds[1]) / 2, (bounds[2] + bounds[3]) / 2, (bounds[4] + bounds[5]) / 2]
  return transformed(triangulated(source.GetOutput()), rotation(center, angles))


def readPolyData(path):
  reader = vtk.vtkXMLPolyDataReader()
  reader.SetFileName(path)
  reader.Update()
  return reader.GetOutput()


def writePolyData(polyData, path):
  writer = vtk.vtkXMLPolyDataWriter()
  writer.SetInputData(polyData)
  writer.SetFileName(path)
  writer.Write()


def kigumiResult(polyDatas, operations):
  combine = logicModule.vtkKigumiBooleanSequenceFilter()
  for index, operation in enumerate(operations):
    combine.SetOperation(index + 1, operMode(logicModule.vtkKigumiBooleanFilter, operation))
  for polyData in polyDatas:
    combine.AddInputData(polyData)
  combine.Update()
  return combine.GetOutput()


def segmentSurface(sampleName, cacheDirectory):
  """Closed surface of the first segment of a sample segmentation of SlicerBoneReconstructionPlanner."""
  path = os.path.join(cacheDirectory, f"{sampleName}.vtp")
  if not os.path.exists(path):
    import SampleData
    fileName = f"{sampleName}Segmentation.seg.nrrd"
    filePath = SampleData.SampleDataLogic().downloadFileIntoCache(
      f"https://github.com/SlicerIGT/SlicerBoneReconstructionPlanner/releases/download/TestingData/{fileName}", fileName)
    segmentationNode = slicer.util.loadSegmentation(filePath)
    segmentationNode.CreateClosedSurfaceRepresentation()
    polyData = vtk.vtkPolyData()
    segmentationNode.GetClosedSurfaceRepresentation(segmentationNode.GetSegmentation().GetNthSegmentID(0), polyData)
    writePolyData(triangulated(polyData), path)
  return readPolyData(path)


def mandibleMinusBox(cacheDirectory):
  """A slab is cut from one side of the mandible, as in a segmental resection."""
  mandible = segmentSurface("Mandible", cacheDirectory)
  b = mandible.GetBounds()
  x = b[0] + 0.25 * (b[1] - b[0])
  cut = box([x - 7.5, x + 7.5, b[2] - 10, b[3] + 10, b[4] - 10, b[5] + 10], (5, 10, 20))
  return [mandible, cut], ["difference"]


def mandibleUnionFibula(cacheDirectory):
  """A 50 mm piece of the fibula, laid along the left-right axis, is joined to the front of the mandible."""
  mandible = segmentSurface("Mandible", cacheDirectory)
  piecePath = os.path.join(cacheDirectory, "FibulaPiece.vtp")
  if not os.path.exists(piecePath):
    fibula = segmentSurface("Fibula", cacheDirectory)
    b = fibula.GetBounds()
    z = (b[4] + b[5]) / 2
    piece = kigumiResult([fibula, box([b[0] - 1, b[1] + 1, b[2] - 1, b[3] + 1, z - 25, z + 25])], ["intersection"])
    pb = piece.GetBounds()
    pieceCenter = [(pb[0] + pb[1]) / 2, (pb[2] + pb[3]) / 2, (pb[4] + pb[5]) / 2]
    # Most anterior point of the mandible, then 5 mm inwards
    points = vtk_to_numpy(mandible.GetPoints().GetData())
    target = points[np.argmax(points[:, 1])] - [0, 5, 0]
    transform = vtk.vtkTransform()
    transform.Translate(target)
    transform.RotateY(90)
    transform.Translate([-c for c in pieceCenter])
    writePolyData(transformed(piece, transform), piecePath)
  return [mandible, readPolyData(piecePath)], ["union"]


def mandibleSteps(cacheDirectory):
  """Three slabs are cut from the mandible in further steps."""
  mandible = segmentSurface("Mandible", cacheDirectory)
  b = mandible.GetBounds()
  cuts = []
  for fraction, angles in [(0.2, (0, 15, 25)), (0.5, (10, 0, -10)), (0.8, (-5, -10, -25))]:
    x = b[0] + fraction * (b[1] - b[0])
    cuts.append(box([x - 4, x + 4, b[2] - 10, b[3] + 10, b[4] - 10, b[5] + 10], angles))
  return [mandible] + cuts, ["difference", "difference", "difference"]


# Each case returns the input polydata and the operations that combine them, in order
CASES = {
  "sphereMinusCylinder": lambda cache: ([sphere([0, 0, 0], 20), cylinder([10, 0, 0], 8, 60)], ["difference"]),
  "sphereUnionSphere": lambda cache: ([sphere([0, 0, 0], 20), sphere([15, 8, 5], 15)], ["union"]),
  # Sharp edges where the faces of the box meet
  "boxIntersectSphere": lambda cache: ([box([-15, 15, -15, 15, -15, 15], (17, 23, 31)), sphere([0, 0, 0], 20)], ["intersection"]),
  # A 0.3 mm gap, thinner than a voxel
  "thinSlab": lambda cache: ([box([-20, 20, -20, 20, -20, 20], (10, 20, 30)),
    box([-0.15, 0.15, -30, 30, -30, 30], (10, 20, 30), [0, 0, 0])], ["difference"]),
  "mandibleMinusBox": mandibleMinusBox,
  "mandibleUnionFibula": mandibleUnionFibula,
  "mandibleSteps": mandibleSteps,
}


def operMode(filterClass, operation):
  return {
    "union": filterClass.OPER_UNION,
    "intersection": filterClass.OPER_INTERSECTION,
    "difference": filterClass.OPER_DIFFERENCE,
    "difference2": filterClass.OPER_DIFFERENCE2,
  }[operation]


def runBackend(backend, polyDatas, operations, voxelSize, extraLevels, threads):
  """Compute the result. Return the result and, for octree, the voxel size; raise RuntimeError on errors."""
  errors = []

  def update(algorithm):
    observer = algorithm.AddObserver(vtk.vtkCommand.ErrorEvent, lambda caller, event: errors.append(event))
    algorithm.Update()
    algorithm.RemoveObserver(observer)
    if errors:
      raise RuntimeError("filter error")

  if backend == "octree":
    combine = logicModule.vtkOctreeBooleanFilter()
    combine.SetVoxelSize(voxelSize)
    combine.SetExtraLevels(extraLevels)
    for index, operation in enumerate(operations):
      combine.SetOperation(index + 1, operMode(logicModule.vtkOctreeBooleanFilter, operation))
    for polyData in polyDatas:
      combine.AddInputData(polyData)
    update(combine)
    return combine.GetOutput(), combine.GetEffectiveVoxelSize()
  if backend == "kigumi":
    combine = logicModule.vtkKigumiBooleanSequenceFilter()
    combine.SetNumberOfThreads(threads)
    for index, operation in enumerate(operations):
      combine.SetOperation(index + 1, operMode(logicModule.vtkKigumiBooleanFilter, operation))
    for polyData in polyDatas:
      combine.AddInputData(polyData)
    update(combine)
    return combine.GetOutput(), 0.0
  # vtkbool combines two inputs at a time, and returns an empty result when it fails
  result = polyDatas[0]
  for polyData, operation in zip(polyDatas[1:], operations):
    combine = logicModule.vtkPolyDataBooleanFilter()
    combine.SetInputData(0, result)
    combine.SetInputData(1, polyData)
    getattr(combine, {"union": "SetOperModeToUnion", "intersection": "SetOperModeToIntersection",
      "difference": "SetOperModeToDifference", "difference2": "SetOperModeToDifference2"}[operation])()
    combine.Update()
    if combine.GetOutput().GetNumberOfPoints() == 0:
      raise RuntimeError("empty result")
    result = vtk.vtkPolyData()
    result.DeepCopy(combine.GetOutput())
  return result, 0.0


def signedVolume(polyData):
  polyData = triangulated(polyData)
  legacyFaces = vtk.vtkIdTypeArray()
  polyData.GetPolys().ExportLegacyFormat(legacyFaces)
  faces = vtk_to_numpy(legacyFaces).reshape(-1, 4)[:, 1:]
  points = vtk_to_numpy(polyData.GetPoints().GetData()).astype(np.float64)
  points -= points.mean(axis=0)
  return float(np.einsum("ij,ij->", points[faces[:, 0]], np.cross(points[faces[:, 1]], points[faces[:, 2]])) / 6)


def numberOfOpenEdges(polyData):
  """Boundary and non-manifold edges, after merging coincident points (vtkbool does not merge them)."""
  cleaner = vtk.vtkCleanPolyData()
  cleaner.SetInputData(polyData)
  cleaner.ToleranceIsAbsoluteOn()
  cleaner.SetAbsoluteTolerance(0.0)
  cleaner.Update()
  featureEdges = vtk.vtkFeatureEdges()
  featureEdges.SetInputData(cleaner.GetOutput())
  featureEdges.BoundaryEdgesOn()
  featureEdges.NonManifoldEdgesOn()
  featureEdges.FeatureEdgesOff()
  featureEdges.ManifoldEdgesOff()
  featureEdges.Update()
  return featureEdges.GetOutput().GetNumberOfCells()


def distances(polyData, reference, maximumNumberOfPoints=100000):
  """Unsigned distances from (at most maximumNumberOfPoints evenly chosen) points of polyData to reference."""
  points = vtk_to_numpy(polyData.GetPoints().GetData()).astype(np.float64)
  points = points[::max(1, len(points) // maximumNumberOfPoints)]
  distanceFunction = vtk.vtkImplicitPolyDataDistance()
  distanceFunction.SetInput(reference)
  values = vtk.vtkDoubleArray()
  distanceFunction.FunctionValue(numpy_to_vtk(np.ascontiguousarray(points), deep=True), values)
  return np.abs(vtk_to_numpy(values))


def peakMemoryMB():
  return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def main(arguments):
  caseName, backend = arguments[0], arguments[1]
  voxelSize = float(arguments[2]) if len(arguments) > 2 else 0.0
  extraLevels = int(arguments[3]) if len(arguments) > 3 else 2
  threads = int(arguments[4]) if len(arguments) > 4 else 0
  cacheDirectory = arguments[5] if len(arguments) > 5 else os.path.join(tempfile.gettempdir(), "CombineModelsOctreeBenchmark")
  os.makedirs(cacheDirectory, exist_ok=True)

  polyDatas, operations = CASES[caseName](cacheDirectory)
  referencePath = os.path.join(cacheDirectory, f"{caseName}_kigumi.vtp")
  if backend == "prepare":
    if not os.path.exists(referencePath):
      writePolyData(kigumiResult(polyDatas, operations), referencePath)
    print(f"BENCHMARK case={caseName} backend=prepare inputTriangles={sum(p.GetNumberOfPolys() for p in polyDatas)}")
    return

  if threads > 0:
    vtk.vtkSMPTools.Initialize(threads)
  line = f"BENCHMARK case={caseName} backend={backend} threads={threads}"
  if backend == "octree":
    line += f" levels={extraLevels}"
  baselineMB = peakMemoryMB()
  times = []
  try:
    for run in range(3):
      startTime = time.perf_counter()
      result, effectiveVoxelSize = runBackend(backend, polyDatas, operations, voxelSize, extraLevels, threads)
      times.append(time.perf_counter() - startTime)
  except RuntimeError as error:
    print(f"{line} voxelSize={voxelSize} status=failed({error})")
    return
  if backend == "octree":
    line += f" voxelSize={effectiveVoxelSize:.4g}" + ("(auto)" if voxelSize <= 0 else "")
  line += f" seconds={statistics.median(times):.3f} peakMB={peakMemoryMB() - baselineMB:.0f} triangles={result.GetNumberOfPolys()}"

  reference = readPolyData(referencePath)
  referenceVolume = signedVolume(reference)
  if result.GetNumberOfPoints() == 0:
    print(f"{line} status=empty")
    return
  forward = distances(result, reference)
  backward = distances(reference, result)
  volumeError = 100 * (signedVolume(result) - referenceVolume) / referenceVolume
  line += (f" openEdges={numberOfOpenEdges(result)} mean={forward.mean():.4f} p95={np.percentile(forward, 95):.4f}"
    f" hausdorff={max(forward.max(), backward.max()):.3f} volumeError={volumeError:+.3f}% status=ok")
  print(line)


if __name__ == "__main__":
  try:
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
  except Exception:
    import traceback
    traceback.print_exc()
  slicer.util.exit(0)
