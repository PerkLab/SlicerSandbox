# This 3D Slicer module allows launching 3D Slicer from the web browser and load NRRD file.
# It uses a custom URL, which launches 3D Slicer and contains the download URL as query parameter (with percent encoding).
# See discussion at https://discourse.slicer.org/t/how-to-load-nifti-file-from-web-browser-link/18664/5
#
# Setup:
# - save this file as "LoadRemoteFile.py" in an empty folder.
# - add the folder to additional module paths in Slicer
#
# To test, open a terminal and execute this command:
#
# start slicer://viewer/?download=https%3A%2F%2Fgithub.com%2Frbumm%2FSlicerLungCTAnalyzer%2Freleases%2Fdownload%2FSampleData%2FLungCTAnalyzerChestCT.nrrd
#

import os
import unittest
import logging
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

#
# LoadRemoteFile
#

class LoadRemoteFile(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "Load Remote File"
    self.parent.categories = ["Utilities"]
    self.parent.dependencies = []
    self.parent.contributors = ["ASH", "Andras Lasso (PerkLab)"]
    self.parent.helpText = """
This module loads NRRD files from custom URLs such as:
slicer://viewer/?download=https%3A%2F%2Fgithub.com%2Frbumm%2FSlicerLungCTAnalyzer%2Freleases%2Fdownload%2FSampleData%2FLungCTAnalyzerChestCT.nrrd
See more information <a href="https://discourse.slicer.org/t/how-to-load-nifti-file-from-web-browser-link/18664/5">here</a>.
"""
    self.parent.acknowledgementText = """
This file was originally developed by Andras Lasso, PerkLab and ASH.
"""

    # Initilize self.sampleDataLogic. At this point, Slicer modules are not initialized yet, so we cannot instantiate the logic yet.
    self.sampleDataLogic = None

    slicer.app.connect("urlReceived(QString)", self.onURLReceived)

  def reportProgress(self, message, logLevel=None):
    # Print progress in the console
    print(f"Loading... {self.sampleDataLogic.downloadPercent}%")
    # Abort download if cancel is clicked in progress bar
    if self.progressWindow.wasCanceled:
        raise Exception("download aborted")
    # Update progress window
    self.progressWindow.show()
    self.progressWindow.activateWindow()
    self.progressWindow.setValue(int(self.sampleDataLogic.downloadPercent))
    self.progressWindow.setLabelText("Downloading...")
    # Process events to allow screen to refresh
    slicer.app.processEvents()

  def center3dViews(self):
    layoutManager = slicer.app.layoutManager()
    for threeDViewIndex in range(layoutManager.threeDViewCount):
      threeDWidget = layoutManager.threeDWidget(0)
      threeDView = threeDWidget.threeDView()
      threeDView.resetFocalPoint()

  def showSliceViewsIn3d(self):
    layoutManager = slicer.app.layoutManager()
    for sliceViewName in layoutManager.sliceViewNames():
      controller = layoutManager.sliceWidget(sliceViewName).sliceController()
      controller.setSliceVisible(True)

  def onURLReceived(self, urlString):
    """Process DICOM view requests. URL protocol and path must be: slicer://viewer/
    Query parameters:
      - `download`: download and show with default file type
      - `image` or `volume`: download and show as image
      - `segmentation`: download and show as segmentation
      - `show3d`: show segmentation in 3D and center 3D view

    Display a file (using default file type):

        slicer://viewer/?download=https%3A%2F%2Fgithub.com%2Frbumm%2FSlicerLungCTAnalyzer%2Freleases%2Fdownload%2FSampleData%2FLungCTAnalyzerChestCT.nrrd

    Display a segmentation and volume file:

        slicer://viewer/?show3d=true&segmentation=https%3A%2F%2Fgithub.com%2Frbumm%2FSlicerLungCTAnalyzer%2Freleases%2Fdownload%2FSampleData%2FLungCTAnalyzerMaskSegmentation.seg.nrrd&image=https%3A%2F%2Fgithub.com%2Frbumm%2FSlicerLungCTAnalyzer%2Freleases%2Fdownload%2FSampleData%2FLungCTAnalyzerChestCT.nrrd

    """
    logging.info(f"URL received: {urlString}")

    # Check if we understand this URL
    url = qt.QUrl(urlString)
    if url.authority().lower() != "viewer":
        return
    query = qt.QUrlQuery(url)

    # Get list of files to load
    filesToOpen = []
    for key, value in query.queryItems(qt.QUrl.FullyDecoded):
      if key == "download":
        fileType = None
      elif key == "image" or key == "volume":
        fileType = "VolumeFile"
      elif key == "segmentation":
        fileType = "SegmentationFile"
      else:
        continue
      downloadUrl = qt.QUrl(value)

       # Get the node name from URL
      nodeName, ext = os.path.splitext(os.path.basename(downloadUrl.path()))
      # Generate random filename to avoid reusing/overwriting older downloaded files that may have the same name
      import uuid
      fileName = f"{nodeName}-{uuid.uuid4().hex}{ext}"
      info = {"downloadUrl": downloadUrl, "nodeName": nodeName, "fileName": fileName, "fileType": fileType}
      filesToOpen.append(info)

    if not filesToOpen:
        return

    # Parse additional options
    queryMap = {}
    for key, value in query.queryItems(qt.QUrl.FullyDecoded):
        queryMap[key] = value

    show3d = False
    if "show3d" in queryMap:
      print("Show 3d")
      show3d = slicer.util.toBool(queryMap["show3d"])

    # Ensure sampleData logic is created
    if not self.sampleDataLogic:
      import SampleData
      self.sampleDataLogic = SampleData.SampleDataLogic()

    for info in filesToOpen:
      downloadUrlString = info["downloadUrl"].toString()
      logging.info(f"Download URL detected - get the file from {downloadUrlString} and load it now")
      try:
          self.progressWindow = slicer.util.createProgressDialog()
          self.sampleDataLogic.logMessage = self.reportProgress

          loadedNodes = self.sampleDataLogic.downloadFromURL(nodeNames=info["nodeName"], fileNames=info["fileName"], uris=downloadUrlString, loadFileTypes=info["fileType"])
          # remove downloaded file
          os.remove(slicer.app.cachePath + "/" + info["fileName"])

          if show3d:
            for loadedNode in loadedNodes:
              if type(loadedNode) == slicer.vtkMRMLSegmentationNode:
                # Show segmentation in 3D
                loadedNode.CreateClosedSurfaceRepresentation()
              # elif type(loadedNode) == slicer.vtkMRMLVolumeNode:
              #   # Show volume rendering in 3D
              #   pluginHandler = slicer.qSlicerSubjectHierarchyPluginHandler().instance()
              #   vrPlugin = pluginHandler.pluginByName("VolumeRendering")
              #   volumeItem = slicer.vtkMRMLSubjectHierarchyNode.GetSubjectHierarchyNode(slicer.mrmlScene).GetItemByDataNode(loadedNode)
              #   vrPlugin.setDisplayVisibility(volumeItem, True)
              #   vrPlugin.showVolumeRendering(True, volumeItem)
      finally:
          self.progressWindow.close()

    if show3d:
      self.center3dViews()
      self.showSliceViewsIn3d()
