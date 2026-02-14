import logging
import os
import vtk
import qt
import ctk
import slicer
from slicer.ScriptedLoadableModule import *


class ExportModelTo3mf(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Export Model to 3MF"
        self.parent.categories = ["Surface Models"]
        self.parent.dependencies = []
        self.parent.contributors = ["Andras Lasso (PerkLab)"]
        self.parent.helpText = """
This module exports model nodes as 3MF (3D Manufacturing Format) files.
3MF is an open source file format designed for 3D printing.
It registers a file writer plugin, so you can also export models to 3MF using
"Export to file..." function in the right-click menu in Data module; and in the Save dialog.
"""
        self.parent.acknowledgementText = """
This module was developed for the Slicer community.
"""


class ExportModelTo3mfWidget(ScriptedLoadableModuleWidget):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)

        # Create layout
        layout = qt.QVBoxLayout()
        self.layout.addLayout(layout)

        # Create form layout for model and file selection
        formLayout = qt.QFormLayout()

        # Model selection
        self.modelSelector = slicer.qMRMLNodeComboBox()
        self.modelSelector.nodeTypes = ["vtkMRMLModelNode"]
        self.modelSelector.setMRMLScene(slicer.mrmlScene)
        formLayout.addRow("Model:", self.modelSelector)

        # File selector
        self.filePath = ctk.ctkPathLineEdit()
        self.filePath.filters = ctk.ctkPathLineEdit.Files
        self.filePath.settingKey = "ExportModelTo3mf/OutputPath"
        self.filePath.nameFilters = ["3MF Files (*.3mf)"]
        self.filePath.setToolTip("Select output .3mf file")
        formLayout.addRow("Output File:", self.filePath)

        layout.addLayout(formLayout)

        # Export button
        self.exportButton = qt.QPushButton("Export")
        self.exportButton.clicked.connect(self.onExport)
        layout.addWidget(self.exportButton)

        layout.addStretch(1)

    def onExport(self):
        with slicer.util.tryWithErrorDisplay("Export failed."):
            modelNode = self.modelSelector.currentNode()
            outputPath = self.filePath.currentPath
            logic = ExportModelTo3mfLogic()
            logic.exportModelTo3MF(modelNode, outputPath)
            slicer.util.delayDisplay("Export succeeded.")

class ExportModelTo3mfLogic(ScriptedLoadableModuleLogic):
    """This class should implement all the actual computation done by your module."""

    def __init__(self):
        ScriptedLoadableModuleLogic.__init__(self)

    @staticmethod
    def ensurePyLib3mf():
        """Ensure Lib3MF is installed, install if missing."""
        try:
            import lib3mf
            return True
        except ImportError:
            try:
                slicer.util.pip_install("Lib3MF")
                import lib3mf
                logging.info("Lib3MF installed successfully")
                return True
            except Exception as e:
                logging.error(f"Failed to install Lib3MF: {str(e)}")
                return False

    def exportModelTo3MF(self, modelNode, filePath):
        """Export a model node to 3MF format.

        Args:
            modelNode: vtkMRMLModelNode to export
            filePath: output file path for the 3MF file

        Raises:
            RuntimeError: if export fails
        """
        # Ensure Lib3MF is available
        if not self.ensurePyLib3mf():
            raise RuntimeError("Lib3MF is required. Please install it with: pip install Lib3MF")

        try:
            import lib3mf
        except ImportError as e:
            raise RuntimeError(f"Failed to import Lib3MF: {str(e)}")

        polyData = modelNode.GetPolyData()
        if not polyData:
            raise RuntimeError("Model has no polydata")

        # Validate the path directory exists
        outputDir = os.path.dirname(filePath)
        if outputDir and not os.path.exists(outputDir):
            raise RuntimeError(f"Output directory does not exist: {outputDir}")

        # Create 3MF model
        wrapper = lib3mf.Wrapper()
        model = wrapper.CreateModel()
        meshResource = model.AddMeshObject()
        meshObject = meshResource

        # Add vertices one by one using lib3mf.Position
        vertices = polyData.GetPoints()
        if vertices:
            for i in range(vertices.GetNumberOfPoints()):
                point = vertices.GetPoint(i)
                position = lib3mf.Position()
                position.Coordinates[0] = float(point[0])
                position.Coordinates[1] = float(point[1])
                position.Coordinates[2] = float(point[2])
                meshResource.AddVertex(position)
        else:
            logging.warning("Model has no vertices")

        # Add triangles with triangulation using lib3mf.Triangle
        polys = polyData.GetPolys()
        if polys:
            polys.InitTraversal()
            idList = vtk.vtkIdList()
            triangleCount = 0
            while polys.GetNextCell(idList):
                numIds = idList.GetNumberOfIds()
                if numIds >= 3:
                    # Triangulate polygons
                    for j in range(1, numIds - 1):
                        triangle = lib3mf.Triangle()
                        triangle.Indices[0] = int(idList.GetId(0))
                        triangle.Indices[1] = int(idList.GetId(j))
                        triangle.Indices[2] = int(idList.GetId(j + 1))
                        meshResource.AddTriangle(triangle)
                        triangleCount += 1
            logging.info(f"Added {triangleCount} triangles to 3MF model")
        else:
            logging.warning("Model has no polygons")

        # Add build item with model name
        modelName = modelNode.GetName() or "Model"
        meshResource.SetName(modelName)
        model.AddBuildItem(meshObject, wrapper.GetIdentityTransform())

        # Write file - use proper error handling
        try:
            writer = model.QueryWriter("3mf")
            if not writer:
                raise RuntimeError("Failed to get 3MF writer from Lib3MF")
            writer.WriteToFile(filePath)
        except AttributeError:
            # Fallback for older Lib3MF versions
            logging.info("Using fallback write method")
            model.Write(filePath)

        if not os.path.exists(filePath):
            raise RuntimeError(f"Output file was not created: {filePath}")

        fileSize = os.path.getsize(filePath)
        logging.info(f"Exported to: {filePath} ({fileSize} bytes)")


class ExportModelTo3mfFileWriter:
    """File writer plugin for exporting models to 3MF format"""

    def __init__(self, parent):
        self.parent = parent

    def description(self):
        return "3MF Format"

    def fileType(self):
        return "3MF"

    def extensions(self, obj):
        return ["3D Model (*.3mf)"]

    def canWriteObjectConfidence(self, obj):
        if obj and obj.IsA("vtkMRMLModelNode"):
            return 0.9
        return 0.0

    def write(self, properties):
        """Write method called by Slicer's IO manager.

        Properties dict contains:
        - fileName: output file path
        - fileType: file type (3MF)
        - nodeID: MRML node ID (optional)
        - scene: MRML scene
        """
        try:
            if not properties:
                raise RuntimeError("No properties provided")

            filePath = properties.get("fileName")
            if not filePath:
                raise RuntimeError("No fileName in properties")

            modelNode = slicer.mrmlScene.GetNodeByID(properties["nodeID"])
            if not modelNode:
                raise RuntimeError("Could not find model node to export")

            logic = ExportModelTo3mfLogic()
            logic.exportModelTo3MF(modelNode, filePath)

            # Return written nodes to Slicer
            self.parent.writtenNodes = [modelNode.GetID()]
            return True

        except Exception as e:
            logging.error(f"Write failed: {str(e)}", exc_info=True)
            return False


class ExportModelTo3mfTest(ScriptedLoadableModuleTest):
    """Test case for ExportModelTo3mf module"""

    def setUp(self):
        slicer.mrmlScene.Clear(0)
        import tempfile
        self.tempDir = tempfile.gettempdir()

    def runTest(self):
        self.setUp()
        self.test_ExportModelTo3mf()

    def test_ExportModelTo3mf(self):
        """Test export functionality"""
        self.delayDisplay("Testing export...")

        # Create test model (sphere)
        sphereSource = vtk.vtkSphereSource()
        sphereSource.SetRadius(10)
        sphereSource.Update()

        modelNode = slicer.mrmlScene.CreateNodeByClass("vtkMRMLModelNode")
        modelNode.SetName("TestSphere")
        modelNode.SetPolyDataConnection(sphereSource.GetOutputPort())
        slicer.mrmlScene.AddNode(modelNode)

        # Test export
        testFile = os.path.join(self.tempDir, "test_export.3mf")
        logic = ExportModelTo3mfLogic()

        try:
            logic.exportModelTo3MF(modelNode, testFile)
            self.assertTrue(os.path.exists(testFile), "Output file should exist")
            fileSize = os.path.getsize(testFile)
            self.assertGreater(fileSize, 0, "Output file should have content")
            self.delayDisplay("Test passed!")
        finally:
            if os.path.exists(testFile):
                os.remove(testFile)

