import os
import unittest
import logging
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin
import numpy as np

#
# CharacterizeTransformMatrix
#


class CharacterizeTransformMatrix(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Characterize Transform Matrix"
        self.parent.categories = ["Utilities"]
        self.parent.dependencies = []
        self.parent.contributors = ["Mike Bindschadler (Seattle Children's Hospital)"]
        # TODO: update with short description of the module and a link to online module documentation
        self.parent.helpText = """
This module uses polar decomposition to describe the components of a 4x4 transform matrix. The decomposition has the form:
H = T * F * R * K, where H is the full homogeneous transformation matrix (with 0,0,0,1 as the bottom row), T is a translation-only matrix,
F is a reflection-only matrix (identity matrix if no reflection), R is a rotation-only matrix, and K is a stretch matrix. K can further be decompsed into three scale matrices, which can each be
characterized by a stretch direction (an eigenvector) and a stretch factor (the associated eigenvalue). Points 
to be transformed are on the right, so the order of operations is stretching first, then rotation, then translation.

If you would like access to the decomposed components of the matrix, you can call the relevant logic function of this module as follows:

import CharacterizeTransformMatrix

decompositionResults = CharacterizeTransformMatrix.CharacterizeTransformMatrixLogic().characterizeLinearTransformNode(transformNode)

decompositionResults will then be a namedTuple with all the information from the decomposition.

See more information in <a href="https://github.com/PerkLab/SlicerSandbox#characterize-transform-matrix">module documentation</a>.
"""

        self.parent.acknowledgementText = """
This file was originally developed by Mike Bindschadler and funded by Seattle Children's Hosptial.  The decomposition approach closely follows an example originally found <a href="https://colab.research.google.com/drive/1ImBB-N6P9zlNMCBH9evHD6tjk0dzvy1_"> here</a>.
"""


#
# CharacterizeTransformMatrixWidget
#


class CharacterizeTransformMatrixWidget(
    ScriptedLoadableModuleWidget, VTKObservationMixin
):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent=None):
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)  # needed for parameter node observation
        self.logic = None
        self._parameterNode = None
        self._updatingGUIFromParameterNode = False

    def setup(self):
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.setup(self)

        # Load widget from .ui file (created by Qt Designer).
        # Additional widgets can be instantiated manually and added to self.layout.
        uiWidget = slicer.util.loadUI(
            self.resourcePath("UI/CharacterizeTransformMatrix.ui")
        )
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = CharacterizeTransformMatrixLogic()

        # Connections

        # These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
        # (in the selected parameter node).
        self.ui.inputSelector.connect(
            "currentNodeChanged(vtkMRMLNode*)", self.onTransformNodeChange
        )

        # Make sure parameter node is initialized (needed for module reload)
        # self.initializeParameterNode()

    def onTransformNodeChange(self):
        """Update the text area with info about newly selected transform node"""
        transformNode = self.ui.inputSelector.currentNode()
        if transformNode is None:
            self.ui.transformDescriptionTextEdit.setPlainText(
                "No transform node selected"
            )
            return
        elif not transformNode.IsLinear():
            self.ui.transformDescriptionTextEdit.setPlainText(
                "Selected transform is composite or not linear"
            )
            return
        # Otherwise, transform node exists and is linear
        results = self.logic.characterizeLinearTransformNode(transformNode)
        resultsText = results.textResults
        resultsText = "\n".join(resultsText)
        self.ui.transformDescriptionTextEdit.setPlainText(resultsText)

    def cleanup(self):
        """
        Called when the application closes and the module widget is destroyed.
        """
        self.removeObservers()


#
# CharacterizeTransformMatrixLogic
#


class CharacterizeTransformMatrixLogic(ScriptedLoadableModuleLogic):
    """This class should implement all the actual
    computation done by your module.  The interface
    should be such that other python code can import
    this class and make use of the functionality without
    requiring an instance of the Widget.
    Uses ScriptedLoadableModuleLogic base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self):
        """
        Called when the logic class is instantiated. Can be used for initializing member variables.
        """
        ScriptedLoadableModuleLogic.__init__(self)

    def characterizeLinearTransformNode(self, transformNode, verbose=True):
        """A wrapper for characterizeLinearTransformMatrix() which takes a transform node
        rather than a transform matrix."""
        H = slicer.util.arrayFromTransformMatrix(transformNode)
        # H is 4x4 numpy array transformation matrix
        outputs = self.characterizeLinearTransformMatrix(H, verbose=verbose)
        return outputs  # outputs is a namedtuple

    def characterizeLinearTransformMatrix(self, H, verbose=True):
        import numpy as np
        import scipy

        T, F, R, K, S, f, X = self.polarDecompose(H)
        textResults = []
        #### Reflection
        if np.linalg.det(F) < 0:
            hasReflection = True
            line = "This transformation includes a reflection!"
        else:
            hasReflection = False
            line = "This transformation does not include a reflection."
        textResults.append(line)
        #### Stretch
        # Report scale factors and stretch directions, determine if rigid, largest percent change, volumePercentChange
        line = "Scale factors and stretch directions (eigenvalues and eigenvectors of stretch matrix K):"
        textResults.append(line)
        if verbose:
            print(line)
        percentChanges = []
        scaleDirections = []
        for idx, (factor, axis) in enumerate(zip(f[:3], X.T[:3])):
            percentChange = 100 * (factor - 1)
            percentChanges.append(percentChange)
            scaleDirections.append(axis)
            line = f"  f{idx}: {percentChange:+0.3f}% change in direction [{axis[0]:0.2f}, {axis[1]:0.2f}, {axis[2]:0.2f}"
            textResults.append(line)
            if verbose:
                print(line)
        largestPercentChangeIdx = np.argmax(np.abs(percentChanges))
        largestPercentChange = percentChanges[largestPercentChangeIdx]
        volumePercentChange = (np.prod(f) - 1) * 100
        if np.abs(largestPercentChange) < 0.1 and not hasReflection:
            isRigid = True
            line = f"This transform is essentially rigid (largest percent scale changes is {largestPercentChange:+0.3f}%, volume percent change is {volumePercentChange:+0.3f}%)."
        else:
            isRigid = False
            if np.abs(largestPercentChange) < 0.1 and hasReflection:
                line = f"This transform does not change volume (largest percent scale changes is {largestPercentChange:+0.3f}%, volume percent change is {volumePercentChange:+0.3f}%), but is not rigid because it contains a reflection."
            else:
                line = f"This transform is not rigid! Total volume changes by {volumePercentChange:+0.3f}%, and maximal change in one direction is {largestPercentChange:+0.3f}%"
        textResults.append(line)
        if verbose:
            print(line)
        #### Rotation
        # Create Rotation object from matrix
        r = scipy.spatial.transform.Rotation.from_matrix(R[:3, :3])
        #
        # What is rotation axis and rotation angle about that axis?
        rv = (
            r.as_rotvec()
        )  # the conversion ensures angle is >=0 and <=pi, axis is inverted as needed to make this true
        rotation_angle_deg = (
            180 / np.pi * np.linalg.norm(rv)
        )  # length of rotvec is rotation angle in radians
        if rotation_angle_deg < 1e-4:
            # No rotation!
            line = f"There is essentially no rotation (rotation angle =  {rotation_angle_deg:0.1g} degrees (less than < 1e-4 degrees threshold))."
            textResults.append(line)
            if verbose:
                print(line)
            # expected outputs need to be filled with NaNs
            rotation_axis = [np.NaN, np.NaN, np.NaN]  # no rotation axis
            euler_angles_xyz = [np.NaN, np.NaN, np.NaN]  # no rotations...
        else:
            # There is rotation
            # If you look in the direction of the rotation axis vector, positive angles mean counter-clockwise rotation.
            # (as_rotvec() always returns non-negative angles, the rotation axis is inverted as necessary)
            # If you point your LEFT thumb in the direction of the rotation axis, your fingers curl in the positive rotation direction
            rotation_axis = rv / np.linalg.norm(
                rv
            )  # unit vector version of rotation axis
            #
            line = (
                f"The rotation matrix portion of this transformation rotates {np.abs(rotation_angle_deg):0.1f} degrees "
                f"{'ccw' if rotation_angle_deg >= 0 else 'cw'} (if you look in the direction the vector points) "
                f"around a vector which points to [{rotation_axis[0]:0.2f}, {rotation_axis[1]:0.2f}, {rotation_axis[2]:0.2f}] (RAS)"
            )
            textResults.append(line)
            if verbose:
                print(line)
            #
            # What is the best way to understand these as a sequence of rotations around coordinate axes?
            euler_angles_xyz = r.as_euler("xyz", degrees=True)
            # The results are the rotation angles about the positive x axis, then y, then z (in that order,
            # and without the axes moving with the volume ("extrinsic" axes, not "intrinsic"))
            # Same as above, positive angles mean ccw rotation if looking in the positive direction along the
            # axis.
            Rrot, Arot, Srot = euler_angles_xyz
            line = (
                f"Broken down into a series of rotations around axes, the rotation matrix portion of the transformation rotates \n"
                f"  {np.abs(Rrot):0.1f} degrees {'ccw' if Rrot >=0 else 'cw'} around the positive R axis, then \n"
                f"  {np.abs(Arot):0.1f} degrees {'ccw' if Arot >=0 else 'cw'} around the positive A axis, then \n"
                f"  {np.abs(Srot):0.1f} degrees {'ccw' if Srot >=0 else 'cw'} around the positive S axis"
            )
            textResults.append(line)
            if verbose:
                print(line)

        #### Translation
        translationVector = T[:3, 3]
        line = (
            f"This transformation matrix translates by shifting: \n"
            f"  {translationVector[0]:+0.1f} mm in the R direction\n"
            f"  {translationVector[1]:+0.1f} mm in the A direction\n"
            f"  {translationVector[2]:+0.1f} mm in the S direction"
        )
        textResults.append(line)
        #### Order of operations
        line = f"The order of application of the decomposed operations is stretch, then rotate, {'then reflect through origin, ' if hasReflection else ''}then translate. A different order of transform application would generally lead to a different set of decomposition matrices."
        textResults.append(line)
        if verbose:
            print(line)
        if hasReflection:
            line = "Reflection, which is present in this case, could be thought of as applied at any single step in the transformation process since scalar multiplication is communtative."
        #### Return values as named tuple
        import collections

        resultsNamedTupleClass = collections.namedtuple(
            "TransformMatrixAnaylsisResults",
            [
                "textResults",
                "hasReflection",
                "isRigid",
                "scaleFactors",
                "scaleDirections",
                "largestPercentChangeScale",
                "volumePercentChangeOverall",
                "scipyRotationObject",
                "rotationAxis",
                "rotationAngleDegrees",
                "eulerAnglesRAS",
                "translationVector",
                "translationOnlyMatrix",
                "reflectionOnlyMatrix",
                "rotationOnlyMatrix",
                "stretchOnlyMatrix",
                "scaleMatrixList",
                "stretchEigenvectorMatrix",
            ],
        )
        results = resultsNamedTupleClass(
            textResults=textResults,
            hasReflection=hasReflection,
            isRigid=isRigid,
            scaleFactors=f,
            scaleDirections=scaleDirections,
            largestPercentChangeScale=largestPercentChange,
            volumePercentChangeOverall=volumePercentChange,
            scipyRotationObject=r,
            rotationAxis=rotation_axis,
            rotationAngleDegrees=rotation_angle_deg,
            eulerAnglesRAS=euler_angles_xyz,
            translationVector=translationVector,
            translationOnlyMatrix=T,
            rotationOnlyMatrix=R,
            reflectionOnlyMatrix=F,
            stretchOnlyMatrix=K,
            scaleMatrixList=S,
            stretchEigenvectorMatrix=X,
        )
        return results

    def separateTranslation(self, H):
        """Given 4x4 numpy matrix H, decompose into a translation-only
        matrix T and a no-translation matrix L, such that the matrix
        product T*L is H.
        """
        T = np.eye(4)
        T[:3, 3] = H[:3, 3]
        L = H.copy()
        L[:3, 3] = 0
        if not np.allclose(H, T @ L):
            raise Exception("T*L should equal H, but it does not!")
        return T, L

    def polarDecompose(self, H):
        """Compute polar decomposition of 4x4 numpy matrix H.
        Outputs are:
        T: translation only matrix
        F: reflection only matrix
        R: rotation only matrix
        K: stretch matrix
        S: list of scale matrices, in order of decreasing eigenvalues
        f: list of eigenvalues of the stretch matrix
        X: eigenvector matrix of stretch matrix

        The decomposition is such that the following is true:
        T*F*R*K = H
        S1*S2*S3 = K (where S<N> is the Nth scale matrix)
        Furthermore, S1 is a matrix which scales in the direction of
        the first eigenvector of K by a factor of the first (largest) eigenvalue
        of K. Similarly, S2 is a matrix which scales in the direction of
        the eigenvector associated with the second largest eigenvalue of K by
        a factor of the second largest eigenvalue. Analgously for S3.
        """
        from scipy.linalg import polar

        T, L = self.separateTranslation(H)  # T is translation matrix,
        R, K = polar(L)  # R is rotation matrix, K is stretch matrix
        if np.linalg.det(R) < 0:
            # The transformation matrix rotation component is improper (contains
            # a reflection as well as a rotation)),
            # convert to a proper rotation matrix
            R[:3, :3] = -R[:3, :3]
            # and set the 'reflection' matrix
            F = np.diag([-1.0, -1.0, -1.0, 1.0])
        else:
            # The transformation matrix does not contain a reflection, the
            # "reflection" matrix is just the identity matrix
            F = np.eye(4)
        # Check answer still OK
        if not np.allclose(L, F @ R @ K):
            raise Exception("F*R*K should equal L, but it does not!")
        if not np.allclose(H, T @ F @ R @ K):
            raise Exception("T*F*R*K should equal H, but it does not!")
        # Decompose stretch matrix K into scale matrices
        f, X = np.linalg.eig(K)  # eigenvalues and eigenvectors of stretch matrix
        S = []
        for factor, axis in zip(f[:3], X.T[:3]):
            # if not np.isclose(factor, 1):
            scale = np.eye(4) + np.outer(axis, axis) * (factor - 1)
            S.append(scale)
        # Check answers still OK
        scale_prod = np.eye(4)
        for scale in S:
            scale_prod = scale_prod @ scale
        # At this level of decomposition, these are more like warnings than definite errors, so don't throw exception
        if not np.allclose(K, scale_prod):
            logging.warn(
                "Product of scale matrices should equal stretch matrix K, but it does not!"
            )
        if not np.allclose(H, T @ F @ R @ scale_prod):
            logging.warn(
                "T*F*R*(product of scale matrices) should equal H, but it does not!"
            )
        # Return all interesting outputs
        return T, F, R, K, S, f, X


#
# CharacterizeTransformMatrixTest
#


class CharacterizeTransformMatrixTest(ScriptedLoadableModuleTest):
    """
    This is the test case for your scripted module.
    Uses ScriptedLoadableModuleTest base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def setUp(self):
        """Do whatever is needed to reset the state - typically a scene clear will be enough."""
        slicer.mrmlScene.Clear()

    def runTest(self):
        """Run as few or as many tests as needed here."""
        self.setUp()
        self.test_CharacterizeTransformMatrix1()

    def test_CharacterizeTransformMatrix1(self):
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

        self.delayDisplay("Starting the test")

        self.delayDisplay("Test passed")
