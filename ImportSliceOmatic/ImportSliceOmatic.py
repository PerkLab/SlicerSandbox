import os
import unittest
import logging
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *

#
# ImportSliceOmatic
#

class ImportSliceOmatic(ScriptedLoadableModule):
  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "ImportSliceOmatic"
    self.parent.categories = ["Informatics"]
    self.parent.dependencies = []
    self.parent.contributors = ["Andras Lasso (PerkLab)"]
    self.parent.helpText = """Load segmentation from tag file created by SliceOmatic"""
    self.parent.acknowledgementText = """This file was originally developed by Andras Lasso, PerkLab."""
    # don't show this module - it is only for registering a reader
    parent.hidden = True 

#
# Reader plugin
# (identified by its special name <moduleName>FileReader)
#

class ImportSliceOmaticFileReader(object):

  def __init__(self, parent):
    self.parent = parent

  def description(self):
    return 'SliceOmatic tag'

  def fileType(self):
    return 'SliceOmaticTag'

  def extensions(self):
    return ['SliceOmatic tag file (*.tag)']

  def canLoadFile(self, filePath):
    try:
      headerInfo = ImportSliceOmaticFileReader.readHeader(filePath)
      if not headerInfo:
        return False
      dims = headerInfo['dims']
      if dims[0] == 0 or dims[2] == 0 or dims[2] == 0:
        return False
    except Exception as e:
      return False
    return True

  def load(self, properties):
    try:
      filePath = properties['fileName']
      headerInfo = ImportSliceOmaticFileReader.readHeader(filePath)

      scalarType = vtk.VTK_CHAR
      numberOfComponents = 1
      sliceSize = headerInfo['dims'][0] * headerInfo['dims'][1] * vtk.vtkDataArray.GetDataTypeSize(scalarType) * numberOfComponents
      headerSize = headerInfo['headerSize']
      totalFilesize = os.path.getsize(filePath)
      voxelDataSize = totalFilesize - headerSize
      maxNumberOfSlices = int(voxelDataSize/sliceSize)
      if headerInfo['dims'][2] > maxNumberOfSlices:
        logging.error(f"Tag file is expected to contain {headerInfo['dims'][2]} slices but it has only {maxNumberOfSlices}")
        return False

      reader = vtk.vtkImageReader2()
      reader.SetFileName(filePath)
      reader.SetFileDimensionality(3)
      reader.SetDataExtent(0, headerInfo['dims'][0]-1, 0, headerInfo['dims'][1]-1, 0, headerInfo['dims'][2]-1)
      # reader.SetDataByteOrderToLittleEndian()
      reader.SetDataScalarType(scalarType)
      reader.SetNumberOfScalarComponents(numberOfComponents)
      reader.SetHeaderSize(headerSize)
      reader.SetFileLowerLeft(True) # to match input from NRRD reader
      reader.Update()

      tempLabelmapNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLLabelMapVolumeNode', 'Segment')

      tempLabelmapNode.SetImageDataConnection(reader.GetOutputPort())
      # We assume file is in LPS and invert first and second axes
      # to get volume in RAS.

      import numpy as np
      axisX = headerInfo['axisX']
      axisY = headerInfo['axisY']
      axisZ = np.cross(axisX, axisY)
      spacing = headerInfo['spacing']
      origin = headerInfo['origin']

      ijkToLps = np.eye(4)
      for row in range(3):
        ijkToLps[row, 0] = axisX[row] * spacing[0]
        ijkToLps[row, 1] = axisY[row] * spacing[1]
        ijkToLps[row, 2] = axisZ[row] * spacing[2]
        ijkToLps[row, 3] = origin[row]
      lpsToRas = np.diag([-1.0, -1.0, 1.0, 1.0])
      ijkToRas = np.dot(lpsToRas, ijkToLps)
      ijkToRasVtk = slicer.util.vtkMatrixFromArray(ijkToRas)
      tempLabelmapNode.SetIJKToRASMatrix(ijkToRasVtk)
      tempLabelmapNode.Modified()

      # Get node base name from filename
      if 'name' in properties.keys():
        baseName = properties['name']
      else:
        baseName = os.path.splitext(os.path.basename(filePath))[0]
        baseName = slicer.mrmlScene.GenerateUniqueName(baseName)

      loadedSegmentationNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLSegmentationNode', baseName)
      slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(tempLabelmapNode, loadedSegmentationNode)
      slicer.mrmlScene.RemoveNode(tempLabelmapNode)

    except Exception as e:
      logging.error('Failed to load file: '+str(e))
      import traceback
      traceback.print_exc()
      return False

    self.parent.loadedNodes = [loadedSegmentationNode.GetID()]
    return True


  @staticmethod
  def readHeader(filename):
    """Read tag file header.
    File format description: https://www.tomovision.com/SliceO_Help/index.htm?context=700
    """

    endOfHeaderChar = '\x0c'
    with open(filename) as f:
      text = f.read(1000)  # header is just a few hundred bytes, 1000 should be able to include the complete header

    if not endOfHeaderChar in text:
      # end of header character is not found, it is not a valid tag file
      return None

    header = text.split(endOfHeaderChar)[0]

    import re
    fields = re.split('[\n\t\r ]+', header)

    dims = [0, 0, 0]
    origin = [0.0, 0.0, 0.0]
    spacing = [1.0, 1.0, 1.0]
    axisX = [1.0, 0.0, 0.0]
    axisY = [0.0, 1.0, 0.0]

    for field in fields:
      if not field:
        continue
      name, value = field.split(':')
      if name == 'x':
        dims[0] = int(value)
      elif name == 'y':
        dims[1] = int(value)
      elif name == 'z':
        dims[2] = int(value)
      elif name == 'org_x':
        origin[0] = float(value)
      elif name == 'org_y':
        origin[1] = float(value)
      elif name == 'org_z':
        origin[2] = float(value)
      elif name == 'inc_x':
        spacing[0] = float(value)
      elif name == 'inc_y':
        spacing[1] = float(value)
      elif name == 'epais':
        spacing[2] = float(value)
      elif name == 'dir_h_x':
        axisX[0] = float(value)
      elif name == 'dir_h_y':
        axisX[1] = float(value)
      elif name == 'dir_h_z':
        axisX[2] = float(value)
      elif name == 'dir_v_x':
        axisY[0] = float(value)
      elif name == 'dir_v_y':
        axisY[1] = float(value)
      elif name == 'dir_v_z':
        axisY[2] = float(value)
      elif name == 'type':
        # type is BYTE in tag files
        if value != 'BYTE':
          logging.warning('Voxel type in tag file is expected to be BYTE')
      elif name == 'uid':
        # not used
        pass
      elif name == 'chksum':
        # not used
        pass
      else:
        if name[0] != '*':
          # unknown field that is not a comment
          return None

    headerInfo = {
      'dims': dims,
      'origin': origin,
      'spacing': spacing,
      'axisX': axisX,
      'axisY': axisY,
      'headerSize': len(header)+1
      }

    return headerInfo


#
# ImportSliceOmaticTest
#

class ImportSliceOmaticTest(ScriptedLoadableModuleTest):

  def setUp(self):
    slicer.mrmlScene.Clear()

  def runTest(self):
    self.setUp()
    self.test_ImportSliceOmatic1()

  def test_ImportSliceOmatic1(self):

    self.delayDisplay("Loading test image as segmentation")
    testDataPath = os.path.join(os.path.dirname(__file__), 'Resources')
    tagFilePath = os.path.join(testDataPath, 'test01.dcm.tag')
    node = slicer.util.loadNodeFromFile(tagFilePath, 'SliceOmaticTag')
    self.assertIsNotNone(node)

    self.delayDisplay('Checking loaded segmentation')
    self.assertEqual(node.GetSegmentation().GetNumberOfSegments(), 1)

    self.delayDisplay('Test passed')
