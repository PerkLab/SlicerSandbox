import os
import unittest
import logging
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *

#
# ImportOCT
#

class ImportOCT(ScriptedLoadableModule):
  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "ImportOCT"
    self.parent.categories = ["Informatics"]
    self.parent.dependencies = []
    self.parent.contributors = ["Andras Lasso (PerkLab)"]
    self.parent.helpText = """Load OCT image volumes"""
    self.parent.acknowledgementText = """This file was originally developed by Andras Lasso, PerkLab."""
    # don't show this module - it is only for registering a reader
    parent.hidden = True 

#
# Reader plugin
# (identified by its special name <moduleName>FileReader)
#

class ImportOCTFileReader(object):

  def __init__(self, parent):
    self.parent = parent

  def description(self):
    return 'OCT image'

  def fileType(self):
    return 'OCTImageFile'

  def extensions(self):
    # TODO: we could expose all file formats that oct-converter Python package supports,
    # but we would need sample data sets to test with
    return ['Topcon OCT image file (*.fda)']

  def checkRequiredPythonPackages(self):
    try:
      import oct_converter
      # Successfully imported
      return True
    except ModuleNotFoundError as e:
      if slicer.util.confirmOkCancelDisplay("Importing of OCT files require 'oct-converter' Python package. Click OK to install it now (it may take several minutes)."):
        # Install converter
        slicer.util.pip_install("oct-converter")
      else:
        # User chose not to install converter
        return False

    # Failed once, but may have been installed successfully since then, test it now
    try:
      import oct_converter
    except ModuleNotFoundError as e:
      slicer.util.errorDisplay("Required 'oct-converter' Python package has not been installed. Cannot import OCT image.")
      return False

    return True

  def canLoadFile(self, filePath):
    if not self.checkRequiredPythonPackages():
      return False

    try:
      from oct_converter.readers import FDA
      fda = FDA(filePath)
      if fda is None:
        return False
    except Exception as e:
      return False
    return True

  def load(self, properties):
    if not self.checkRequiredPythonPackages():
      return False

    try:
      filePath = properties['fileName']

      # TODO: we could expose all file formats that oct-converter Python package supports,
      # but we would need sample data sets to test with

      from oct_converter.readers import FDA
      fda = FDA(filePath)
      octVolume = fda.read_oct_volume_2()
      import numpy as np
      octVolumeArray = np.zeros([octVolume.volume[0].shape[0], octVolume.volume[0].shape[1], len(octVolume.volume)])
      for sliceIndex in range(len(octVolume.volume)):
        octVolumeArray[:, :, sliceIndex] = octVolume.volume[sliceIndex]

      # Get node base name from filename
      if 'name' in properties.keys():
        baseName = properties['name']
      else:
        baseName = os.path.splitext(os.path.basename(filePath))[0]
        baseName = slicer.mrmlScene.GenerateUniqueName(baseName)

      volumeNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode", baseName)
      volumeNode.SetAttribute("oct.laterality", octVolume.laterality)
      volumeNode.SetAttribute("oct.patient_id", octVolume.patient_id)
      volumeNode.SetAttribute("oct.patient_dob", octVolume.DOB)

      # Set up IJK to RAS so that the axis slice shows the usual orientation of the image and the matrix is right-handed.
      # The converter does not provide voxel spacing information, so we just use 1.0 and log a warning message.
      spacingNotSetMessage = "File importer for .fda OCT images does not set voxel size. Length measurement in physical unit will not be accurate."
      try:
        self.parent.userMessages().AddMessage(vtk.vtkCommand.WarningEvent, spacingNotSetMessage)
      except:
        # In Slicer-4.11 and earlier versions userMessages() method was not exposed.
        logging.warning(f"Note for {filePath}: {spacingNotSetMessage}")
      ijkToRasArray = np.array([
        [ 0.0, 1.0, 0.0, 0.0],
        [ 0.0, 0.0,-1.0, 0.0],
        [-1.0, 0.0, 0.0, 0.0],
        [ 0.0, 0.0, 0.0, 1.0]
        ])
      volumeNode.SetIJKToRASMatrix(slicer.util.vtkMatrixFromArray(ijkToRasArray))

      slicer.util.updateVolumeFromArray(volumeNode, octVolumeArray)

    except Exception as e:
      logging.error('Failed to load file: '+str(e))
      import traceback
      traceback.print_exc()
      return False

    # Show volume
    selectionNode = slicer.app.applicationLogic().GetSelectionNode()
    selectionNode.SetActiveVolumeID(volumeNode.GetID())
    slicer.app.applicationLogic().PropagateVolumeSelection()

    self.parent.loadedNodes = [volumeNode.GetID()]
    return True

#
# ImportOCTTest
#

class ImportOCTTest(ScriptedLoadableModuleTest):

  def setUp(self):
    slicer.mrmlScene.Clear()

  def runTest(self):
    self.setUp()
    self.test_ImportOCT1()

  def test_ImportOCT1(self):

    self.delayDisplay("Loading test image as segmentation")

    import SampleData
    testFdaFilePath = SampleData.downloadFromURL(
      fileNames='OS_260397.fda',
      uris='https://github.com/PerkLab/SlicerSandbox/releases/download/TestingData/OS_260397.fda',
      checksums='SHA256:5536006a2bb4d117f5804e49d393ecc1cb7e98c3e5f7924b7b83b8f0e0567e2c')[0]
    volumeNode = slicer.util.loadNodeFromFile(testFdaFilePath, 'OCTImageFile')
    self.assertIsNotNone(volumeNode)

    self.delayDisplay('Checking loaded image')
    self.assertEqual(volumeNode.GetImageData().GetDimensions()[0], 9)
    self.assertEqual(volumeNode.GetImageData().GetDimensions()[1], 320)
    self.assertEqual(volumeNode.GetImageData().GetDimensions()[2], 992)

    self.delayDisplay('Test passed')
