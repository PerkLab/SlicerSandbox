import os
import unittest
import logging
import re
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

#
# DocumentationTools
#

class DocumentationTools(ScriptedLoadableModule):
  """Uses ScriptedLoadableModule base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "DocumentationTools"  # TODO: make this more human readable by adding spaces
    self.parent.categories = ["Utilities"]  # TODO: set categories (folders where the module shows up in the module selector)
    self.parent.dependencies = []  # TODO: add here list of module names that this module requires
    self.parent.contributors = ["John Doe (AnyWare Corp.)"]  # TODO: replace with "Firstname Lastname (Organization)"
    self.parent.helpText = """
This is an example of scripted loadable module bundled in an extension.
"""  # TODO: update with short description of the module
    self.parent.helpText += self.getDefaultModuleDocumentationLink()  # TODO: verify that the default URL is correct or change it to the actual documentation
    self.parent.acknowledgementText = """
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
"""  # TODO: replace with organization, grant and thanks.

#
# DocumentationToolsWidget
#

class DocumentationToolsWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
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
    uiWidget = slicer.util.loadUI(self.resourcePath('UI/DocumentationTools.ui'))
    self.layout.addWidget(uiWidget)
    self.ui = slicer.util.childWidgetVariables(uiWidget)

    # Set scene in MRML widgets. Make sure that in Qt designer
    # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
    # "setMRMLScene(vtkMRMLScene*)" slot.
    uiWidget.setMRMLScene(slicer.mrmlScene)

    self.ui.moduleNameLineEdit.text = slicer.util.settingsValue("DocumentationTools/moduleName", "")

    # Create a new parameterNode
    # This parameterNode stores all user choices in parameter values, node selections, etc.
    # so that when the scene is saved and reloaded, these settings are restored.
    self.logic = DocumentationToolsLogic()

    # Connections
    self.ui.convertWikiToMarkdownButton.connect('clicked(bool)', self.onConvertWikiToMarkdown)
    self.ui.generateDocumentationButton.connect('clicked(bool)', self.onGenerateDocumentation)

  def cleanup(self):
    """
    Called when the application closes and the module widget is destroyed.
    """
    pass

  def onConvertWikiToMarkdown(self):
    try:
      self.ui.inputModuleWikiPathLineEdit.addCurrentPathToHistory()
      self.ui.outputMarkdownPathLineEdit.addCurrentPathToHistory()
      settings = qt.QSettings()
      settings.setValue("DocumentationTools/moduleName", self.ui.moduleNameLineEdit.text)
      with open(self.ui.inputModuleWikiPathLineEdit.currentPath, 'r') as f:
        wikiTextInput = f.read()
      markdownOutput = DocumentationToolsLogic.convertWikiToMarkdown(
        wikiTextInput, self.ui.moduleNameLineEdit.text)
      with open(self.ui.outputMarkdownPathLineEdit.currentPath, 'w') as f:
        f.write(markdownOutput)
    except Exception as e:
      slicer.util.errorDisplay("Failed to compute results: "+str(e))
      import traceback
      traceback.print_exc()

  def onGenerateDocumentation(self):
    try:
      self.ui.inputSlicerRepositoryPathLineEdit.addCurrentPathToHistory()
      self.ui.outputDocumentationPathLineEdit.addCurrentPathToHistory() 
      DocumentationToolsLogic.generateDocumentation(
        self.ui.inputSlicerRepositoryPathLineEdit.currentPath,
        self.ui.outputDocumentationPathLineEdit.currentPath)
    except Exception as e:
      slicer.util.errorDisplay("Failed to compute results: "+str(e))
      import traceback
      traceback.print_exc()


#
# DocumentationToolsLogic
#

class DocumentationToolsLogic(ScriptedLoadableModuleLogic):
  """This class should implement all the actual
  computation done by your module.  The interface
  should be such that other python code can import
  this class and make use of the functionality without
  requiring an instance of the Widget.
  Uses ScriptedLoadableModuleLogic base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  @staticmethod
  def convertWikiToMarkdown(wikiTextInput, moduleName):
    wikiText = wikiTextInput
    wikiText = wikiText.replace("{{documentation/modulename}}",moduleName)  # module name
    wikiText = wikiText.replace("<br>","\n")  # newline

    wikiText = re.sub("\n\*\*\*(.+)", "\n        - \\1", wikiText)  # bullet-point level 3
    wikiText = re.sub("\n\*\*(.+)", "\n    - \\1", wikiText)  # bullet-point level 2
    wikiText = re.sub("\n\*(.+)", "\n- \\1", wikiText)  # bullet-point level 1

    wikiText = re.sub("'''[ ]*(.*[^ ]+)[ ]*'''", "**\\1**", wikiText)  # bold text

    wikiText = re.sub(re.escape("[[Documentation/{{documentation/version}}/Modules/")+"(.+[^\|])\|(.+[^\]])\]\]","[\\2](Module_\\1)",wikiText)
    # From: [[Documentation/{{documentation/version}}/Modules/SegmentEditor|Segment Editor]]
    # To: [Segment Editor](module_SegmentEditor)
                      
    wikiText = re.sub("\[\[\:File\:([^\|\[]+)\|([^\[]+)\]\]", "[\\2](https://www.slicer.org/wiki/File:\\1)", wikiText)  # wiki File: links
    # From: [[:File:20160526_Segmentations.pptx|these slides]]
    # To: https://www.slicer.org/wiki/File:20160526_Segmentations.pptx

    # remove versioncheck
    wikiText = wikiText.replace("<noinclude>{{documentation/versioncheck}}</noinclude>","")
    # remove separator comments
    wikiText = wikiText.replace("{{documentation/{{documentation/version}}/module-header}}","")
    wikiText = wikiText.replace("{{documentation/{{documentation/version}}/module-footer}}","")
    sectionSeparator = "<!-- ---------------------------- -->"
    wikiTextSectionList = wikiText.split(sectionSeparator)

    wikiSections = {}
    otherWikiSections = []
    for wikiSection in wikiTextSectionList:
        wikiSection = wikiSection.strip(" \r\n\t")   
        if not wikiSection:
            continue
        sectionName, sectionText = extract_wiki_section_name(wikiSection)
        if sectionName:
            wikiSections[sectionName] = sectionText
        else:
            otherWikiSections.append(sectionText)

    #print(wikiSections.keys())

    intro = wikiSections['Introduction and Acknowledgements']
    intro = intro.replace("{{documentation/{{documentation/version}}/module-introduction-start|{{documentation/modulename}}}}", "")
    intro = intro.replace("{{documentation/{{documentation/version}}/module-introduction-end}}", "")
    intro = intro.replace("{{documentation/{{documentation/version}}/module-introduction-row}}", "\n")
    logoGalleryPrefix = "{{documentation/{{documentation/version}}/module-introduction-logo-gallery"
    logoGallerySuffix = "}}"
    # result = re.match("(.*)"+re.escape(logoGalleryPrefix)+"("
    #                   + re.escape()
    #                   +")*"+re.escape(logoGallerySuffix))
    print(intro)

    standardSectionTitles = [
        'Module Description',
        'How to',
        'Panels and their use',
        'Tutorials',
        'Use Cases',
        'Information for Developers',
        'Similar Modules',
        'References'
    ]

    markdownOutput = "# {0}\n\n".format(moduleName)

    for standardSectionTitle in standardSectionTitles:
        if standardSectionTitle not in wikiSections.keys():
            continue
        markdownOutput += "## {0}\n\n".format(standardSectionTitle)
        markdownOutput += wikiSections[standardSectionTitle] + "\n\n"

    for standardSectionTitle in wikiSections.keys():
        if standardSectionTitle in standardSectionTitles:
            # standard sections has been taken care of already
            continue
        markdownOutput += "## {0}\n\n".format(standardSectionTitle)
        markdownOutput += wikiSections[standardSectionTitle] + "\n\n"

    for index, wikiSection in enumerate(otherWikiSections):
        markdownOutput += "## {0} {1}\n\n".format("Unnamed ", index+1)
        markdownOutput += wikiSection + "\n\n"

    return markdownOutput

  @staticmethod
  def generateDocumentation(slicerRepositoryDir, documentationOutputDir):
    try:
      import sphinx, sphinx_rtd_theme, recommonmark, sphinx_markdown_tables
    except ImportError:
      slicer.util.pip_install('sphinx sphinx_rtd_theme recommonmark sphinx-markdown-tables')

    import sys
    sphinxBuild = slicer.util.launchConsoleProcess([sys.exec_prefix+"/Scripts/sphinx-build", "-M", "html",
      slicerRepositoryDir+'/Docs', documentationOutputDir], useStartupEnvironment=False)
    slicer.util.logProcessOutput(sphinxBuild)


  def setDefaultParameters(self, parameterNode):
    """
    Initialize parameter node with default settings.
    """
    if not parameterNode.GetParameter("Threshold"):
      parameterNode.SetParameter("Threshold", "50.0")
    if not parameterNode.GetParameter("Invert"):
      parameterNode.SetParameter("Invert", "false")

  def run(self, inputVolume, outputVolume, imageThreshold, invert=False, showResult=True):
    """
    Run the processing algorithm.
    Can be used without GUI widget.
    :param inputVolume: volume to be thresholded
    :param outputVolume: thresholding result
    :param imageThreshold: values above/below this threshold will be set to 0
    :param invert: if True then values above the threshold will be set to 0, otherwise values below are set to 0
    :param showResult: show output volume in slice viewers
    """

    if not inputVolume or not outputVolume:
      raise ValueError("Input or output volume is invalid")

    logging.info('Processing started')

    # Compute the thresholded output volume using the Threshold Scalar Volume CLI module
    cliParams = {
      'InputVolume': inputVolume.GetID(),
      'OutputVolume': outputVolume.GetID(),
      'ThresholdValue' : imageThreshold,
      'ThresholdType' : 'Above' if invert else 'Below'
      }
    cliNode = slicer.cli.run(slicer.modules.thresholdscalarvolume, None, cliParams, wait_for_completion=True, update_display=showResult)

    logging.info('Processing completed')

#
# DocumentationToolsTest
#

class DocumentationToolsTest(ScriptedLoadableModuleTest):
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
    self.test_DocumentationTools1()

  def test_DocumentationTools1(self):
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

    # Get/create input data

    import SampleData
    inputVolume = SampleData.downloadFromURL(
      nodeNames='MRHead',
      fileNames='MR-Head.nrrd',
      uris='https://github.com/Slicer/SlicerTestingData/releases/download/MD5/39b01631b7b38232a220007230624c8e',
      checksums='MD5:39b01631b7b38232a220007230624c8e')[0]
    self.delayDisplay('Finished with download and loading')

    inputScalarRange = inputVolume.GetImageData().GetScalarRange()
    self.assertEqual(inputScalarRange[0], 0)
    self.assertEqual(inputScalarRange[1], 279)

    outputVolume = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLScalarVolumeNode")
    threshold = 50

    # Test the module logic

    logic = DocumentationToolsLogic()

    # Test algorithm with non-inverted threshold
    logic.run(inputVolume, outputVolume, threshold, True)
    outputScalarRange = outputVolume.GetImageData().GetScalarRange()
    self.assertEqual(outputScalarRange[0], inputScalarRange[0])
    self.assertEqual(outputScalarRange[1], threshold)

    # Test algorithm with inverted threshold
    logic.run(inputVolume, outputVolume, threshold, False)
    outputScalarRange = outputVolume.GetImageData().GetScalarRange()
    self.assertEqual(outputScalarRange[0], inputScalarRange[0])
    self.assertEqual(outputScalarRange[1], inputScalarRange[1])

    self.delayDisplay('Test passed')

def find_between(s, first, last):
  try:
      start = s.index(first) + len(first)
      end = s.index(last, start)
      return s[start:end]
  except ValueError:
      return ""

def extract_between(s, prefix, suffix):
    """returns text after extracting part between prefix and suffix, then the extracted part"""
    try:
        start = s.index(prefix)
        end = s.index(suffix, start)
        return s[:start]+s[end+len(suffix):], s[start+len(prefix):end]
    except ValueError:
        return s, ""

def extract_wiki_section_name(s):
    prefix = "{{documentation/{{documentation/version}}/module-section|"
    separator = "}}"
    try:
        sectionNameStart = s.index(prefix)
        sectionNameEnd = s.index(separator, sectionNameStart+len(prefix))
        return s[sectionNameStart+len(prefix):sectionNameEnd], s[sectionNameEnd+len(separator):]
    except ValueError:
        return "", s
