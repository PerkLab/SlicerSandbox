import os
import unittest
import logging
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *

#
# ImportOpenInventor
#

class ImportOpenInventor(ScriptedLoadableModule):
  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "ImportOpenInventor"
    self.parent.categories = ["Informatics"]
    self.parent.dependencies = []
    self.parent.contributors = ["Andras Lasso (PerkLab)"]
    self.parent.helpText = """Load simple triangle mesh from OpenInventor (.iv) VRML 1.0 file"""
    self.parent.acknowledgementText = """This file was originally developed by Andras Lasso, PerkLab."""
    # don't show this module - it is only for registering a reader
    parent.hidden = True

#
# Reader plugin
# (identified by its special name <moduleName>FileReader)
#

class ImportOpenInventorFileReader(object):

  def __init__(self, parent):
    self.parent = parent

  def description(self):
    return 'OpenInventor mesh'

  def fileType(self):
    return 'OpenInventorMesh'

  def extensions(self):
    return ['OpenInventor mesh file (*.iv)']

  def canLoadFile(self, filePath):
    try:
      # Check first if loadable based on file extension
      if not self.parent.supportedNameFilters(filePath):
        return False
    except:
      # Slicer version earlier than 5.3-2023-07-31
      pass

    try:
      with open(filePath) as f:
        firstline = f.readline().rstrip()
    except Exception as e:
      return False
    return "VRML V1.0 ascii" in firstline

  def load(self, properties):
    try:
      filePath = properties['fileName']

      with open(filePath) as file:
          vrml = file.read()

      import re
      match = re.search(r'Separator\s+{\s+Coordinate3\s+{\s+point\s+\[([\s\d.,+-]+)\]\s+}\s+IndexedFaceSet\s+{\s+coordIndex\s+\[([\s\d.,+-]+)\]\s+}\s+}', vrml)

      pointsStr = match.groups()[0]
      trianglesStr = match.groups()[1]

      import numpy as np
      pointsArray = np.array([float(s) for s in re.findall(r'([\d.+-]+)', pointsStr)])
      pointsArray = pointsArray.reshape(int(len(pointsArray)/3), 3)
      trianglesArray = np.array([int(s) for s in re.findall(r'([\d.+-]+)', trianglesStr)])
      trianglesArray = trianglesArray.reshape(int(len(trianglesArray)/4), 4)

      points = vtk.vtkPoints()
      for point in pointsArray:
        points.InsertNextPoint(*point)

      polygons = vtk.vtkCellArray()
      for triangle in trianglesArray:
          polygon = vtk.vtkPolygon()
          polygonPointIds = polygon.GetPointIds()
          polygonPointIds.SetNumberOfIds(3)
          for pointIndex in range(3):
            polygonPointIds.SetId(pointIndex, triangle[pointIndex])
          polygons.InsertNextCell(polygon)

      polyData = vtk.vtkPolyData()
      polyData.SetPoints(points)
      polyData.SetPolys(polygons)

      outputMeshInRAS = vtk.vtkPolyData()
      slicer.vtkMRMLModelStorageNode.ConvertBetweenRASAndLPS(polyData, outputMeshInRAS)
      modelNode = slicer.modules.models.logic().AddModel(outputMeshInRAS)

      # Get node base name from filename
      if 'name' in properties.keys():
        baseName = properties['name']
      else:
        baseName = os.path.splitext(os.path.basename(filePath))[0]
        baseName = slicer.mrmlScene.GenerateUniqueName(baseName)

      modelNode.SetName(slicer.mrmlScene.GenerateUniqueName(baseName))

    except Exception as e:
      logging.error('Failed to load file: '+str(e))
      import traceback
      traceback.print_exc()
      return False

    self.parent.loadedNodes = [modelNode.GetID()]
    return True


#
# ImportOpenInventorTest
#

class ImportOpenInventorTest(ScriptedLoadableModuleTest):

  def setUp(self):
    slicer.mrmlScene.Clear()

  def runTest(self):
    self.setUp()
    self.test_ImportOpenInventor1()

  def test_ImportOpenInventor1(self):

    self.delayDisplay("Loading test image as model")
    testDataPath = os.path.join(os.path.dirname(__file__), 'Resources')
    tagFilePath = os.path.join(testDataPath, '14819_cap_R.iv')
    node = slicer.util.loadNodeFromFile(tagFilePath, 'OpenInventorMesh')
    self.assertIsNotNone(node)

    self.delayDisplay('Checking loaded model')
    self.assertEqual(node.GetPolyData().GetNumberOfPoints(), 11878)
    self.assertEqual(node.GetPolyData().GetNumberOfCells(), 23752)

    self.delayDisplay('Test passed')
