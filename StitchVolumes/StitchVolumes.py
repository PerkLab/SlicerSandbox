import os
import unittest
import logging
import vtk, qt, ctk, slicer
import numpy as np
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

#
# StitchVolumes
#


class StitchVolumes(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Stitch Volumes"
        self.parent.categories = ["Utilities"]
        self.parent.dependencies = []
        self.parent.contributors = ["Mike Bindschadler (Seattle Children's Hospital)"]
        self.parent.helpText = """
    This module allows a user to stitch together two or more image volumes.  A set of volumes to stitch, as well
    as a rectangular ROI (to define the output geometry) is supplied, and this module produces an output
    volume which represents all the input volumes cropped, resampled, and stitched together. Areas of overlap
    between original volumes are handled by finding the center of the overlap region, and assigning each half
    of the overlap to the closer original volume.  If all input images are the same resolution and orientation,
    nearest neighbor interpolation is used to avoid resampling; otherwise linear interpolation is used 
    in resampling.
"""
        self.parent.helpText += (
            self.getDefaultModuleDocumentationLink()
        )  # TODO: verify that the default URL is correct or change it to the actual documentation
        self.parent.acknowledgementText = """
    This work was funded by Seattle Children's Hospital.
"""


#
# StitchVolumesWidget
#


class StitchVolumesWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent=None):
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)  # needed for parameter node observation
        self.logic = None
        self._parameterNode = None

    def setup(self):
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.setup(self)

        # Load widget from .ui file (created by Qt Designer)
        uiWidget = slicer.util.loadUI(self.resourcePath("UI/StitchVolumes.ui"))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        # Set scene in MRML widgets. Make sure that in Qt designer
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        # Create a new parameterNode
        # This parameterNode stores all user choices in parameter values, node selections, etc.
        # so that when the scene is saved and reloaded, these settings are restored.
        self.logic = StitchVolumesLogic()
        self.ui.parameterNodeSelector.addAttribute(
            "vtkMRMLScriptedModuleNode", "ModuleName", self.moduleName
        )
        self.setParameterNode(self.logic.getParameterNode())

        # Connections
        self.ui.parameterNodeSelector.connect(
            "currentNodeChanged(vtkMRMLNode*)", self.setParameterNode
        )
        self.ui.applyButton.connect("clicked(bool)", self.onApplyButton)

        # These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
        # (in the selected parameter node).
        self.ui.roiSelector.connect(
            "currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI
        )
        self.ui.volumeSelector1.connect(
            "currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI
        )
        self.ui.volumeSelector2.connect(
            "currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI
        )
        self.ui.volumeSelector3.connect(
            "currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI
        )
        self.ui.volumeSelector4.connect(
            "currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI
        )
        self.ui.volumeSelector5.connect(
            "currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI
        )
        self.ui.outputSelector.connect(
            "currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI
        )

        # Initial GUI update
        self.updateGUIFromParameterNode()

    def cleanup(self):
        """
        Called when the application closes and the module widget is destroyed.
        """
        self.removeObservers()

    def setParameterNode(self, inputParameterNode):
        """
        Adds observers to the selected parameter node. Observation is needed because when the
        parameter node is changed then the GUI must be updated immediately.
        """

        if inputParameterNode:
            self.logic.setDefaultParameters(inputParameterNode)

        # Set parameter node in the parameter node selector widget
        wasBlocked = self.ui.parameterNodeSelector.blockSignals(True)
        self.ui.parameterNodeSelector.setCurrentNode(inputParameterNode)
        self.ui.parameterNodeSelector.blockSignals(wasBlocked)

        if inputParameterNode == self._parameterNode:
            # No change
            return

        # Unobserve previously selected parameter node and add an observer to the newly selected.
        # Changes of parameter node are observed so that whenever parameters are changed by a script or any other module
        # those are reflected immediately in the GUI.
        if self._parameterNode is not None:
            self.removeObserver(
                self._parameterNode,
                vtk.vtkCommand.ModifiedEvent,
                self.updateGUIFromParameterNode,
            )
        if inputParameterNode is not None:
            self.addObserver(
                inputParameterNode,
                vtk.vtkCommand.ModifiedEvent,
                self.updateGUIFromParameterNode,
            )
        self._parameterNode = inputParameterNode

        # Initial GUI update
        self.updateGUIFromParameterNode()

    def updateGUIFromParameterNode(self, caller=None, event=None):
        """
        This method is called whenever parameter node is changed.
        The module GUI is updated to show the current state of the parameter node.
        """

        # Disable all sections if no parameter node is selected
        self.ui.basicCollapsibleButton.enabled = self._parameterNode is not None
        # self.ui.advancedCollapsibleButton.enabled = self._parameterNode is not None
        if self._parameterNode is None:
            return

        # Update each widget from parameter node
        # Need to temporarily block signals to prevent infinite recursion (MRML node update triggers
        # GUI update, which triggers MRML node update, which triggers GUI update, ...)

        wasBlocked = self.ui.roiSelector.blockSignals(True)
        self.ui.roiSelector.setCurrentNode(
            self._parameterNode.GetNodeReference("StitchedVolumeROI")
        )
        self.ui.roiSelector.blockSignals(wasBlocked)
        wasBlocked = self.ui.volumeSelector1.blockSignals(True)
        self.ui.volumeSelector1.setCurrentNode(
            self._parameterNode.GetNodeReference("InputVol1")
        )
        self.ui.volumeSelector1.blockSignals(wasBlocked)
        wasBlocked = self.ui.volumeSelector2.blockSignals(True)
        self.ui.volumeSelector2.setCurrentNode(
            self._parameterNode.GetNodeReference("InputVol2")
        )
        self.ui.volumeSelector2.blockSignals(wasBlocked)
        wasBlocked = self.ui.volumeSelector3.blockSignals(True)
        self.ui.volumeSelector3.setCurrentNode(
            self._parameterNode.GetNodeReference("InputVol3")
        )
        self.ui.volumeSelector3.blockSignals(wasBlocked)
        wasBlocked = self.ui.volumeSelector4.blockSignals(True)
        self.ui.volumeSelector4.setCurrentNode(
            self._parameterNode.GetNodeReference("InputVol4")
        )
        self.ui.volumeSelector4.blockSignals(wasBlocked)
        wasBlocked = self.ui.volumeSelector5.blockSignals(True)
        self.ui.volumeSelector5.setCurrentNode(
            self._parameterNode.GetNodeReference("InputVol5")
        )
        self.ui.volumeSelector5.blockSignals(wasBlocked)

        # What about other values? (current text, e.g.)?  The example code did not update them here

        # Update buttons states and tooltips
        # Enable the Stitch Volumes button if there is an ROI, at least two original volumes
        if (
            self._parameterNode.GetNodeReference("StitchedVolumeROI")
            and self._parameterNode.GetNodeReference("InputVol1")
            and self._parameterNode.GetNodeReference("InputVol2")
            and self._parameterNode.GetParameter("OutputVolName")
        ):
            self.ui.applyButton.toolTip = "Compute stitched volume"
            self.ui.applyButton.enabled = True
        else:
            self.ui.applyButton.toolTip = "Enter inputs to enable stitching"
            self.ui.applyButton.enabled = False

    def updateParameterNodeFromGUI(self, caller=None, event=None):
        """
        This method is called when the user makes any change in the GUI.
        The changes are saved into the parameter node (so that they are restored when the scene is saved and loaded).
        """

        if self._parameterNode is None:
            return

        self._parameterNode.SetNodeReferenceID(
            "StitchedVolumeROI", self.ui.roiSelector.currentNodeID
        )
        self._parameterNode.SetNodeReferenceID(
            "InputVol1", self.ui.volumeSelector1.currentNodeID
        )
        self._parameterNode.SetNodeReferenceID(
            "InputVol2", self.ui.volumeSelector2.currentNodeID
        )
        self._parameterNode.SetNodeReferenceID(
            "InputVol3", self.ui.volumeSelector3.currentNodeID
        )
        self._parameterNode.SetNodeReferenceID(
            "InputVol4", self.ui.volumeSelector4.currentNodeID
        )
        self._parameterNode.SetNodeReferenceID(
            "InputVol5", self.ui.volumeSelector5.currentNodeID
        )
        self._parameterNode.SetNodeReferenceID(
            "OutputVolume", self.ui.outputSelector.currentNodeID
        )

        # self._parameterNode.SetNodeReferenceID("InputVolume", self.ui.inputSelector.currentNodeID)
        # self._parameterNode.SetNodeReferenceID("OutputVolume", self.ui.outputSelector.currentNodeID)
        # self._parameterNode.SetParameter("Threshold", str(self.ui.imageThresholdSliderWidget.value))
        # self._parameterNode.SetParameter("Invert", "true" if self.ui.invertOutputCheckBox.checked else "false")
        # self._parameterNode.SetNodeReferenceID("OutputVolumeInverse", self.invertedOutputSelector.currentNodeID)

    def onApplyButton(self):
        """
        Run processing when user clicks "Stitch Volumes" button.
        """
        try:
            # Gather inputs
            orig_nodes = self.gather_original_nodes()
            roi_node = self.ui.roiSelector.currentNode()
            output_node = self.ui.outputSelector.currentNode()
            # Run the stitching
            self.logic.stitch_volumes(
                orig_nodes, roi_node, output_node, keep_intermediate_volumes=False
            )

        except Exception as e:
            slicer.util.errorDisplay("Failed to compute results: " + str(e))
            import traceback

            traceback.print_exc()

    def gather_original_nodes(self):
        orig_nodes = []
        if self.ui.volumeSelector1.currentNode():
            orig_nodes.append(self.ui.volumeSelector1.currentNode())
        if self.ui.volumeSelector2.currentNode():
            orig_nodes.append(self.ui.volumeSelector2.currentNode())
        if self.ui.volumeSelector3.currentNode():
            orig_nodes.append(self.ui.volumeSelector3.currentNode())
        if self.ui.volumeSelector4.currentNode():
            orig_nodes.append(self.ui.volumeSelector4.currentNode())
        if self.ui.volumeSelector5.currentNode():
            orig_nodes.append(self.ui.volumeSelector5.currentNode())
        return orig_nodes


#
# StitchVolumesLogic
#


class StitchVolumesLogic(ScriptedLoadableModuleLogic):
    """This class should implement all the actual
    computation done by your module.  The interface
    should be such that other python code can import
    this class and make use of the functionality without
    requiring an instance of the Widget.
    Uses ScriptedLoadableModuleLogic base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def setDefaultParameters(self, parameterNode):
        """
        Initialize parameter node with default settings.
        """
        if not parameterNode.GetParameter("OutputVolName"):
            parameterNode.SetParameter("OutputVolName", "S")

    def stitch_volumes(
        self, orig_nodes, roi_node, output_node, keep_intermediate_volumes=False
    ):
        # Stitch together the supplied original volumes, resampling them
        # into the space defined by the supplied roi, putting the stitched
        # output into a volume with the given stitched volume name

        # Crop/Resample first orig node
        ref_vol_node = resample_volume(roi_node, orig_nodes[0], "ReferenceVolume")
        # Resample other nodes
        resamp_vol_nodes = []
        for orig_node in orig_nodes:
            resampled_name = "Resamp_" + orig_node.GetName()
            resamp_node = createOrReplaceNode(resampled_name)
            resamp_vol_nodes.append(resample(orig_node, ref_vol_node, resamp_node))
        imArrays = [
            slicer.util.arrayFromVolume(resamp_vol_node)
            for resamp_vol_node in resamp_vol_nodes
        ]
        if not output_node:
            # Create output volume node to hold stitched image
            output_node_name = slicer.mrmlScene.GenerateUniqueName("Stitched_Volume")
            output_node = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLScalarVolumeNode", output_node_name
            )
        # Copy all image and orientation data from the reference volume to the output volume
        output_node.SetOrigin(ref_vol_node.GetOrigin())
        output_node.SetSpacing(ref_vol_node.GetSpacing())
        imageDirections = vtk.vtkMatrix4x4()
        ref_vol_node.GetIJKToRASDirectionMatrix(imageDirections)
        output_node.SetIJKToRASDirectionMatrix(imageDirections)
        imageData = vtk.vtkImageData()
        imageData.DeepCopy(ref_vol_node.GetImageData())
        output_node.SetAndObserveImageData(imageData)

        # Find the dimension to stitch together (I,J,or K)
        dim_to_stitch = find_dim_to_stitch(orig_nodes, resamp_vol_nodes[0])
        # dim_to_stitch is 0, 1, or 2, depending on whether the dimension to stitch is
        # K,J, or I, respectively (recalling that np arrays are KJI)
        other_dims = tuple({0, 1, 2} - {dim_to_stitch})  # set subtraction
        # We can now sample each resampled volume in along the stitch dimension to
        # figure out where the data starts and
        # stops for each of them.  Then, we can order them by data start value.
        dataSlices = [np.sum(imArray, axis=other_dims) != 0 for imArray in imArrays]
        dataStartIdxs = [np.nonzero(dataSlice)[0][0] for dataSlice in dataSlices]
        dataEndIdxs = [np.nonzero(dataSlice)[0][-1] for dataSlice in dataSlices]
        # Re-order in increasing dataStartIdx order
        ordered = sorted(
            zip(dataStartIdxs, imArrays, dataEndIdxs), key=lambda pair: pair[0]
        )
        orderedDataStartIdxs, orderedImArrays, orderedDataEndIdxs = zip(*ordered)
        imCombined = np.zeros(imArrays[0].shape)
        # We can use the starting and ending indices to determine whether there is overlap
        priorOverlapFlag = False
        for imIdx in range(len(orderedImArrays)):
            imArray = orderedImArrays[imIdx]
            start1 = orderedDataStartIdxs[imIdx]
            end1 = orderedDataEndIdxs[imIdx] + 1  # add 1 because of python indexing
            if imIdx == (len(orderedImArrays) - 1):
                # There is no next volume, just run out to the end of volume
                start2 = end1 + 1
            else:
                # Get the start idx of the next volume
                start2 = orderedDataStartIdxs[imIdx + 1]
            # print('\n---\nstart1:%i\nend1:%i\nstart2:%i\n'%(start1,end1,start2))
            if priorOverlapFlag:
                start1 = nextStartIdx
            # Is there overlap?
            if start2 < end1:
                # There is overlap, the end idx should be shortened
                end1 = np.ceil((end1 + 1 + start2) / 2.0).astype(
                    int
                )  # don't add one, already accounted for
                priorOverlapFlag = True
                nextStartIdx = end1
            else:
                priorOverlapFlag = False
                nextStartIdx = None
            sliceIndexTuple = getSliceIndexTuple(start1, end1, dim_to_stitch)
            imCombined[sliceIndexTuple] = imArray[sliceIndexTuple]
            # print(sliceIndexTuple)

        # Put the result into the stitched volume
        slicer.util.updateVolumeFromArray(output_node, imCombined)
        # Clean up
        if not keep_intermediate_volumes:
            for resamp_vol_node in resamp_vol_nodes:
                slicer.mrmlScene.RemoveNode(resamp_vol_node)
            slicer.mrmlScene.RemoveNode(ref_vol_node)
        # Return stitched volume node
        return output_node


#
# StitchVolumesTest
#


class StitchVolumesTest(ScriptedLoadableModuleTest):
    """
    This is the test case for your scripted module.
    Uses ScriptedLoadableModuleTest base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def setUp(self):
        """Do whatever is needed to reset the state - typically a scene clear will be enough."""
        slicer.mrmlScene.Clear(0)

    def runTest(self):
        """Run as few or as many tests as needed here."""
        self.setUp()
        self.test_StitchVolumes1()

    def test_StitchVolumes1(self):
        """Ideally you should have several levels of tests.  At the lowest level
        tests should exercise the functionality of the logic with different inputs
        (both valid and invalid).  At higher levels your tests should emulate the
        way the user would interact with your code and confirm that it still works
        the way you intended.
        One of the most important features of the tests is that it should alert other
        developers when their changes will have an impact on the behavior of your
        module.  For example, if a developer removes a feature that you depend on,
        your test should break so they know that the feature is needed.
        """
        """ This test loads the MRHead sample image volume, clones it and translates it 
        50 mm in the superior direction, and then stitches it together with the untranslated
        original.  An ROI is created which is fitted to the original image volume and then 
        symmetrically expanded 50 mm in the Superior-Inferior direction.  The stitched
        image volume size is set by the ROI, so there is a 25 mm inferior region which is
        all zeros because it is outside both image volumes. The top 25 mm of the
        translated image is cropped off because it is outside the ROI. Finally, there
        is a visible seam halfway into the overlap region (which is correct in this case 
        because they should not seamlessly meet).  All that is verified by the current
        test is that the stitching runs without error, and that the bounds of the 
        stitched volume are very close to the bounds of the ROI. 
        """

        self.delayDisplay("Starting the test")

        # Get/create input data

        import SampleData

        inputVolume = SampleData.downloadFromURL(
            nodeNames="MRHead",
            fileNames="MR-Head.nrrd",
            uris="https://github.com/Slicer/SlicerTestingData/releases/download/MD5/39b01631b7b38232a220007230624c8e",
            checksums="MD5:39b01631b7b38232a220007230624c8e",
        )[0]
        self.delayDisplay("Finished with download and loading")

        volumeCopy = slicer.vtkSlicerVolumesLogic().CloneVolume(
            slicer.mrmlScene, inputVolume, "cloned_copy"
        )

        # Create transform matrix with 50mm translation
        import numpy as np

        transformMatrixForCopy = np.array(
            [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 50], [0, 0, 0, 1]]
        )
        TNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLinearTransformNode")
        TNode.SetAndObserveMatrixTransformToParent(
            slicer.util.vtkMatrixFromArray(transformMatrixForCopy)
        )
        # Apply transform to cloned copy and harden
        volumeCopy.SetAndObserveTransformNodeID(TNode.GetID())
        slicer.vtkSlicerTransformLogic().hardenTransform(volumeCopy)

        # Create markupsROI and fit to input volume
        roiNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsROINode")
        # Set the axes directions of the roi to match those of the image volume
        # (if we don't do this before fitting using CropVolumes the ROI based image
        # directions can be permuted versions of the original image directions, and
        # we want them to match exactly)
        imageDirectionMatrix = vtk.vtkMatrix4x4()
        volumeCopy.GetIJKToRASDirectionMatrix(imageDirectionMatrix)
        roiNode.SetAndObserveObjectToNodeMatrix(imageDirectionMatrix)

        cropVolumeParameters = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLCropVolumeParametersNode"
        )
        cropVolumeParameters.SetInputVolumeNodeID(inputVolume.GetID())
        cropVolumeParameters.SetROINodeID(roiNode.GetID())
        slicer.modules.cropvolume.logic().SnapROIToVoxelGrid(
            cropVolumeParameters
        )  # optional (rotates the ROI to match the volume axis directions)
        slicer.modules.cropvolume.logic().FitROIToInputVolume(cropVolumeParameters)
        slicer.mrmlScene.RemoveNode(cropVolumeParameters)

        # Expand ROI to include some of the copy volume and some empty space
        sz = list(roiNode.GetSize())
        sz[1] = sz[1] + 50  # axis 1 is the superior-inferior axis for MRHead
        roiNode.SetSize(*sz)

        # Test the module logic

        logic = StitchVolumesLogic()
        stitched_node = logic.stitch_volumes(
            [inputVolume, volumeCopy],
            roiNode,
            None,
            keep_intermediate_volumes=False,
        )

        # Check results

        # Check that stitched image bounds are very close to ROI edges
        stitched_bnds = np.zeros((6))
        stitched_node.GetBounds(stitched_bnds)
        roi_bnds = np.zeros((6))
        roiNode.GetBounds(roi_bnds)
        maxVoxelSize = np.max(stitched_node.GetSpacing())
        maxBndsDeviation = np.max(np.abs(roi_bnds - stitched_bnds))
        self.assertLess(
            maxBndsDeviation,
            maxVoxelSize,
            msg="RAS bounds of stitched volume are greater than 1 voxel off from bounds of ROI!",
        )

        # TODO: implement more tests, for example
        # Could also spot check voxel values
        # - outside both volumes should be 0
        # - the outer corner voxel values should match
        # - the inner corner voxel values (in the overlap region) should not

        self.delayDisplay("Test passed")


####################
#
# Subfunctions
#
####################


def get_RAS_center(vol_node):
    """Find the RAS coordinate center of the image volume from the RAS bounds"""
    b = [0] * 6
    vol_node.GetBounds(b)
    cen = [np.mean([b[0], b[1]]), np.mean([b[2], b[3]]), np.mean([b[4], b[5]])]
    return cen


def find_dim_to_stitch(orig_nodes, resamp_node):
    # This function determines the dimension to stitch the original nodes along by
    # finding the image axis dimension (I,J,or K) which is best aligned with the
    # vector between the centers of the furthest apart original volumes.
    # A resampled volume is needed just in case its IJK direction matrix
    # differs from the original nodes. I believe this method should be
    # fairly robust.
    RAS_centers = [get_RAS_center(vol) for vol in orig_nodes]
    dists = [
        np.linalg.norm(np.subtract(RAS_center, RAS_centers[0]))
        for RAS_center in RAS_centers
    ]
    furthest_from_first = np.argmax(dists)
    stitch_vect = np.subtract(RAS_centers[0], RAS_centers[furthest_from_first])
    stitch_vect = stitch_vect / np.linalg.norm(stitch_vect)
    # RAS_biggest_change_idx= np.argmax(np.abs(stitch_vect))
    # Now I need to know which image volume axis (I,J,or K) is most aligned with the stitching vector
    # We can do this by comparing the dot products of each of the I J and K vectors with the stitch
    # vector.  The one with the maximum abs dot product is the winner
    ijkdirs = [
        [0, 0, 0],
        [0, 0, 0],
        [0, 0, 0],
    ]  # NOTE these will be the ROWS, not columns of ijk to ras matrix
    resamp_node.GetIJKToRASDirections(ijkdirs)  # fill in values
    ijkdirs_np = np.array(ijkdirs)
    # Compute dot products with the columns of ijk to ras matrix
    absDotsIJK = [np.abs(np.dot(d, stitch_vect)) for d in ijkdirs_np.T]
    IJKmatchIdx = np.argmax(absDotsIJK)
    KJImatchIdx = 2 - IJKmatchIdx
    dim_to_stitch = KJImatchIdx
    return dim_to_stitch


def createOrReplaceNode(name, nodeClass="vtkMRMLScalarVolumeNode"):
    try:
        node = slicer.util.getNode(name)
    except:
        node = slicer.mrmlScene.AddNewNodeByClass(nodeClass, name)
    return node


def resample_volume(roi_node, input_vol_node, output_vol_name):
    """Carry out the cropping of input_vol_node to the space described by roi_node"""
    cropVolumeNode = slicer.vtkMRMLCropVolumeParametersNode()
    cropVolumeNode.SetScene(slicer.mrmlScene)
    cropVolumeNode.SetName("MyCropVolumeParametersNode")
    cropVolumeNode.SetIsotropicResampling(False)
    cropVolumeNode.SetInterpolationMode(
        cropVolumeNode.InterpolationNearestNeighbor
    )  # use nearest neighbor to avoid resampling artifacts
    cropVolumeNode.SetFillValue(
        0
    )  # needs to be zero so that sum of filled slices is zero
    cropVolumeNode.SetROINodeID(roi_node.GetID())  # roi
    slicer.mrmlScene.AddNode(cropVolumeNode)
    output_vol_node = createOrReplaceNode(output_vol_name, "vtkMRMLScalarVolumeNode")
    cropVolumeNode.SetInputVolumeNodeID(input_vol_node.GetID())  # input
    cropVolumeNode.SetOutputVolumeNodeID(output_vol_node.GetID())  # output
    slicer.modules.cropvolume.logic().Apply(cropVolumeNode)  # do the crop
    slicer.mrmlScene.RemoveNode(cropVolumeNode)
    return output_vol_node


def resample(
    vol_node_to_resample,
    reference_vol_node,
    output_vol_node=None,
    interpolationMode="NearestNeighbor",
):
    """Handle resampling a second node based on the geometry of reference node."""
    # Switch method and warn if NearestNeighbor is selected and inappropriate
    if interpolationMode == "NearestNeighbor":
        import numpy as np

        maxVoxDimDiff = np.max(
            np.abs(
                np.subtract(
                    reference_vol_node.GetSpacing(), vol_node_to_resample.GetSpacing()
                )
            )
        )
        if maxVoxDimDiff > 1e-4:
            interpolationMode = "Linear"
            logging.warning(
                "Automatically switching from NearestNeighbor interpolation to Linear interpolation because the volume to resample (%s) has a different resolution (%0.2fmm x %0.2fmm x %0.2fmm) than the first original volume (%s, %0.2fmm x %0.2fmm x %0.2fmm)"
                % (
                    vol_node_to_resample.GetName(),
                    *vol_node_to_resample.GetSpacing(),
                    reference_vol_node.GetName(),
                    *reference_vol_node.GetSpacing(),
                )
            )
    inputVolID = vol_node_to_resample.GetID()
    refVolID = reference_vol_node.GetID()
    if output_vol_node is None:
        output_vol_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
    outputVolID = output_vol_node.GetID()
    params = {
        "inputVolume": inputVolID,
        "referenceVolume": refVolID,
        "outputVolume": outputVolID,
        "interpolationMode": interpolationMode,
        "defaultValue": 0,
    }
    slicer.cli.runSync(slicer.modules.brainsresample, None, params)
    return output_vol_node


def getSliceIndexTuple(start, end, dim_to_stitch, nDims=3):
    # Constructs a tuple which can be used as an index into a 3D array
    # To illustrate, if the dim_to_stitch were 1, the output would be
    # (slice(None),slice(start:end),slice(None)), which can be used in
    # indexing into a 3D array equivalently to arr[:,start:end,:]
    sliceIndexList = []
    for dim in range(nDims):
        if dim == dim_to_stitch:
            sliceIndexList.append(slice(start, end))
        else:
            sliceIndexList.append(slice(None))
    return tuple(sliceIndexList)


""" def rename_dixon_dicom_volumes(volNodes=None):
    # substitutes the "imageType N" with the Dixon type ("F","W","OP", or "IP")
    # If volume is not a DICOM volume, then it is left unchanged
    import re

    if volNodes is None:
        # Gather all scalar volumes in the scene
        volNodes = []
        shNode = slicer.mrmlScene.GetSubjectHierarchyNode()
        sceneItemID = shNode.GetSceneItemID()
        c = vtk.vtkCollection()
        shNode.GetDataNodesInBranch(sceneItemID, c, "vtkMRMLScalarVolumeNode")
        for idx in range(c.GetNumberOfItems()):
            volNodes.append(c.GetItemAsObject(idx))
    # Loop over all volumes, renaming only if DICOM and if node name matches r"imageType \d"
    for volNode in volNodes:
        uids = volNode.GetAttribute("DICOM.instanceUIDs")  # empty for non DICOM volumes
        imageTypeField = "0008,0008"  # DICOM field corresponding to ImageType
        if uids is not None:
            uid = uids.split()[
                0
            ]  # all of these UIDs have the same ImageType (at least so far as I tested)
            filename = slicer.dicomDatabase.fileForInstance(uid)
            imageType = slicer.dicomDatabase.fileValue(
                filename, imageTypeField
            )  # looks like "DERIVED\PRIMARY\OP\OP\DERIVED"
            dixonType = imageType.split("\\")[
                2
            ]  # pulls out the 3rd entry in that field
            origVolName = volNode.GetName()
            # Substitute dixon type for 'imageType N'
            newName = re.sub(r"imageType \d", dixonType, origVolName)
            volNode.SetName(newName) """
