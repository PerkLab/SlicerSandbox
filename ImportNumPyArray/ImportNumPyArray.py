import os
import textwrap

import vtk

import slicer
from slicer.ScriptedLoadableModule import *


class ImportNumPyArray(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        parent.title = "ImportNumPyArray"
        parent.categories = ["Informatics"]
        parent.dependencies = []
        parent.contributors = ["Dzenan Zukic (Kitware)", "Andras Lasso (Perk Lab, Queen's University)"]
        parent.helpText = textwrap.dedent("""
            Reader for numpy array files (.npy and .npz).
            vtkMRMLScalarVolumeNode (for 1D-3D numpy array), vtkMRMLVectorVolumeNode (for 4D), or vtkMRMLSequenceNode (for 5D)
            is added to the scene. See https://numpy.org/devdocs/reference/generated/numpy.lib.format.html#npy-format
            Axis order for array dimension:
              - 1D: I
              - 2D: J, I
              - 3D: K, J, I
              - 4D: K, J, I, component
              - 5D: time, K, J, I, component
            """)
        parent.acknowledgementText = textwrap.dedent("""
            This module is adapted from work done by Steve Pieper to support loading of NIfTI files.
            """)
        self.parent = parent


class ImportNumPyArrayWidget(ScriptedLoadableModuleWidget):
    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)
        # Default reload&test widgets are enough.
        # Note that reader is not reloaded.


class ImportNumPyArrayFileReader:
    def __init__(self, parent):
        self.parent = parent

    def description(self):
        return "NumPy Array Image"

    def fileType(self):
        return "NumPyArrayImageFile"

    def extensions(self):
        return ["NumPy Array Image (*.npy)", "NumPy Array Image (*.npz)"]

    def canLoadFile(self, filePath):
        ext = filePath[-4:].lower()
        return ext == ".npy" or ext == ".npz"

    def _addSequenceBrowserNode(self, baseName, outputSequenceNode, playbackRateFps):
        # Add a browser node and show the volume in the slice viewer for user convenience
        outputSequenceBrowserNode = slicer.vtkMRMLSequenceBrowserNode()
        outputSequenceBrowserNode.SetName(slicer.mrmlScene.GenerateUniqueName(baseName + " browser"))
        outputSequenceBrowserNode.SetPlaybackRateFps(playbackRateFps)
        slicer.mrmlScene.AddNode(outputSequenceBrowserNode)

        outputSequenceBrowserNode.AddSynchronizedSequenceNode(outputSequenceNode)
        proxyVolumeNode = outputSequenceBrowserNode.GetProxyNode(outputSequenceNode)

        # Show sequence browser toolbar
        slicer.modules.sequences.setToolBarActiveBrowserNode(outputSequenceBrowserNode)
        slicer.modules.sequences.showSequenceBrowser(outputSequenceBrowserNode)

        return outputSequenceBrowserNode

    def load(self, properties):
        """
        uses properties:
            fileName - path to the .npy or .npz file
        """
        try:
            import numpy as np

            filePath = properties["fileName"]

            # Get node base name from filename
            if "name" in properties.keys():
                baseName = properties["name"]
            else:
                baseName = os.path.splitext(os.path.basename(filePath))[0]

            numpyArray = np.load(filePath)

            # npz files may store multiple arrays, use only the first one
            if hasattr(numpyArray, "files"):
                # npz file, get the first array
                if len(numpyArray.files) != 1:
                    raise RuntimeError(f"Input npz file must contain exactly one array, found {len(numpyArray.files)}.")
                numpyArray = numpyArray[numpyArray.files[0]]

            shape = numpyArray.shape
            if len(shape) > 5:
                raise RuntimeError("Arrays larger than 5 dimensions are not supported")
            if len(shape) < 1:
                raise RuntimeError("Zero dimensional arrays are not supported")

            volumeClassName = 'vtkMRMLScalarVolumeNode'
            if len(shape) >= 4 and shape[-1] > 1:
                volumeClassName = 'vtkMRMLVectorVolumeNode'

            if len(shape) < 5:
                volumeNode = slicer.mrmlScene.AddNewNodeByClass(volumeClassName, slicer.mrmlScene.GenerateUniqueName(baseName))
                slicer.util.updateVolumeFromArray(volumeNode, numpyArray)
                volumeNode.CreateDefaultDisplayNodes()
            else:  # 5 dimensions
                # Copy volumes into a sequence
                volumeSequenceNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSequenceNode", slicer.mrmlScene.GenerateUniqueName(baseName + "sequence"))
                volumeNodeTemp = slicer.mrmlScene.AddNewNodeByClass(volumeClassName, "__temp__ImportNumPyArray")
                for volumeIndex in range(shape[0]):
                    if numpyArray.shape[-1] == 1:
                        # Single component
                        slicer.util.updateVolumeFromArray(volumeNodeTemp, numpyArray[volumeIndex, :, :, :, 0])
                    else:
                        # Multiple components
                        slicer.util.updateVolumeFromArray(volumeNodeTemp, numpyArray[volumeIndex, :, :, :, :])
                    volumeSequenceNode.SetDataNodeAtValue(volumeNodeTemp, str(volumeIndex))
                slicer.mrmlScene.RemoveNode(volumeNodeTemp)

                # Create sequence browser node so that the image sequence can be browsed
                volumeSequenceBrowserNode = self._addSequenceBrowserNode(baseName, volumeSequenceNode, 5.0)

                # Use the proxy node of the sequence as output, remove the temporary volume node
                volumeNode = volumeSequenceBrowserNode.GetProxyNode(volumeSequenceBrowserNode.GetMasterSequenceNode())

            # Show the volume
            appLogic = slicer.app.applicationLogic()
            selNode = appLogic.GetSelectionNode()
            selNode.SetReferenceActiveVolumeID(volumeNode.GetID())
            appLogic.PropagateVolumeSelection()
            appLogic.FitSliceToAll()

        except Exception as e:
            import traceback
            traceback.print_exc()
            errorMessage = f"Failed to load numpy array file: {str(e)}"
            self.parent.userMessages().AddMessage(vtk.vtkCommand.ErrorEvent, errorMessage)
            return False

        self.parent.loadedNodes = [volumeNode.GetID()]
        return True


class ImportNumPyArrayTest(ScriptedLoadableModuleTest):

    def runTest(self):
        """Run as few or as many tests as needed here."""
        self.setUp()
        self.testWriterReader()
        self.tearDown()
        self.delayDisplay("Testing complete")

    def setUp(self):
        self.tempDir = slicer.util.tempDirectory()
        slicer.mrmlScene.Clear()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tempDir, True)

    def _testWriteReadOne(self, filename, dimension, voxelArray):
        import numpy as np

        shape = voxelArray.shape
        assert len(shape) == dimension

        npArrayPath = os.path.join(self.tempDir, f"TestImportNumPyArray_{filename}")
        if filename.endswith(".npy"):
            np.save(npArrayPath, voxelArray)
        else:
            np.savez(npArrayPath, voxelArray)

        loadedVolumeNode = slicer.util.loadNodeFromFile(npArrayPath, "NumPyArrayImageFile")

        if len(shape) < 5:
            loadedVoxelArray = slicer.util.arrayFromVolume(loadedVolumeNode)
            self.assertTrue(np.allclose(voxelArray, loadedVoxelArray))
        else:
            browserNode = slicer.modules.sequences.logic().GetFirstBrowserNodeForProxyNode(loadedVolumeNode)
            for sequenceItemIndex in [0, 3, 7]:
                browserNode.SetSelectedItemNumber(sequenceItemIndex)
                loadedVoxelArray = slicer.util.arrayFromVolume(loadedVolumeNode)
                self.assertTrue(np.allclose(voxelArray[sequenceItemIndex, :, :, :, 0], loadedVoxelArray))

    def testWriterReader0D(self):
        import numpy as np

        with self.assertRaisesRegex(RuntimeError, "Zero dimensional arrays are not supported"):
            self._testWriteReadOne("0d.npy", 0, np.array(0))

    def testWriterReader6D(self):
        import numpy as np

        with self.assertRaisesRegex(RuntimeError, "Arrays larger than 5 dimensions are not supported"):
            self._testWriteReadOne("6d.npy", 6, np.zeros([3, 5, 2, 5, 2, 6]))

    def testWriterReader1D2D3D(self):
        import numpy as np
        import SampleData

        inputVolume = SampleData.SampleDataLogic().downloadMRHead()
        input3dArray = slicer.util.arrayFromVolume(inputVolume)

        self._testWriteReadOne("3d.npy", 3, input3dArray)
        self._testWriteReadOne("3d.npz", 3, input3dArray)
        self._testWriteReadOne("2d.npy", 2, input3dArray[20, :])
        self._testWriteReadOne("1d.npy", 1, input3dArray[30, 20, :])

    def testWriterReader4D(self):
        import numpy as np
        import SampleData

        inputVolume = SampleData.SampleDataLogic().downloadMRHead()
        input3dArray = slicer.util.arrayFromVolume(inputVolume)

        input4dArray = np.zeros([input3dArray.shape[0], input3dArray.shape[1], input3dArray.shape[2], 3])
        input4dArray[:, :, :, 0] = input3dArray
        input4dArray[:, :, :, 1] = input3dArray + 50
        input4dArray[:, :, :, 2] = input3dArray - 30

        self._testWriteReadOne("4d.npy", 4, input4dArray)

    def testWriterReader5D(self):
        import numpy as np
        import SampleData

        sequenceNode = SampleData.downloadSample('CTCardioSeq')
        sequenceBrowserNode = slicer.modules.sequences.logic().GetFirstBrowserNodeForSequenceNode(sequenceNode)
        sequenceNode = sequenceBrowserNode.GetMasterSequenceNode()

        # Preallocate a 5D numpy array that will hold the entire sequence
        import numpy as np
        dims = slicer.util.arrayFromVolume(sequenceNode.GetNthDataNode(0)).shape
        voxelArray = np.zeros([sequenceNode.GetNumberOfDataNodes(), dims[0], dims[1], dims[2], 1])

        # Fill in the 4D array from the sequence node
        for volumeIndex in range(sequenceNode.GetNumberOfDataNodes()):
            voxelArray[volumeIndex, :, :, :, 0] = slicer.util.arrayFromVolume(sequenceNode.GetNthDataNode(volumeIndex))

        self._testWriteReadOne("5d.npy", 5, voxelArray)
