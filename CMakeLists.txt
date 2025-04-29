cmake_minimum_required(VERSION 3.5)

project(Sandbox)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://github.com/PerkLab/SlicerSandbox")
set(EXTENSION_CATEGORY "Examples")
set(EXTENSION_CONTRIBUTORS "Csaba Pinter (Queen's University), Andras Lasso (Queen's University)")
set(EXTENSION_DESCRIPTION "Collection of utilities that are not polished implementations but can be useful to users")
set(EXTENSION_ICONURL "https://github.com/PerkLab/SlicerSandbox/raw/master/Sandbox_Logo_128.png")
set(EXTENSION_SCREENSHOTURLS "https://raw.githubusercontent.com/PerkLab/SlicerSandbox/master/RemovePatientTable.jpg https://raw.githubusercontent.com/PerkLab/SlicerSandbox/master/Lights.jpg")
set(EXTENSION_DEPENDS "NA") # Specified as a space separated string, a list or 'NA' if any

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
if (NOT DEFINED SLICERSANDBOX_ENABLE_IMPORT_MODULES)
  option(SLICERSANDBOX_ENABLE_IMPORT_MODULES "Enable the building of import modules." ON)
  mark_as_superbuild(SLICERSANDBOX_ENABLE_IMPORT_MODULES)
endif()

#-----------------------------------------------------------------------------
if (NOT DEFINED SLICERSANDBOX_ENABLE_AUTOSAVE_MODULE)
  option(SLICERSANDBOX_ENABLE_AUTOSAVE_MODULE "Enable the building of AutoSave module." ON)
  mark_as_superbuild(SLICERSANDBOX_ENABLE_AUTOSAVE_MODULE)
endif()

#-----------------------------------------------------------------------------
if (NOT DEFINED SLICERSANDBOX_ENABLE_CHARACTERIZETRANSFORMMATRIX_MODULE)
  option(SLICERSANDBOX_ENABLE_CHARACTERIZETRANSFORMMATRIX_MODULE "Enable the building of CharacterizeTransformMatrix module." ON)
  mark_as_superbuild(SLICERSANDBOX_ENABLE_CHARACTERIZETRANSFORMMATRIX_MODULE)
endif()

#-----------------------------------------------------------------------------
if (NOT DEFINED SLICERSANDBOX_ENABLE_COMBINEMODELS_MODULE)
  option(SLICERSANDBOX_ENABLE_COMBINEMODELS_MODULE "Enable the building of CombineModels module." ON)
  mark_as_superbuild(SLICERSANDBOX_ENABLE_COMBINEMODELS_MODULE)
endif()

#-----------------------------------------------------------------------------
if (NOT DEFINED SLICERSANDBOX_ENABLE_CURVEDPLANARREFORMAT_MODULE)
  option(SLICERSANDBOX_ENABLE_CURVEDPLANARREFORMAT_MODULE "Enable the building of CurvedPlanarReformat module." ON)
  mark_as_superbuild(SLICERSANDBOX_ENABLE_CURVEDPLANARREFORMAT_MODULE)
endif()

#-----------------------------------------------------------------------------
if (NOT DEFINED SLICERSANDBOX_ENABLE_DOCUMENTATIONTOOLS_MODULE)
  option(SLICERSANDBOX_ENABLE_DOCUMENTATIONTOOLS_MODULE "Enable the building of DocumentationTools module." ON)
  mark_as_superbuild(SLICERSANDBOX_ENABLE_DOCUMENTATIONTOOLS_MODULE)
endif()

#-----------------------------------------------------------------------------
if (NOT DEFINED SLICERSANDBOX_ENABLE_LIGHTS_MODULE)
  option(SLICERSANDBOX_ENABLE_LIGHTS_MODULE "Enable the building of Lights module." ON)
  mark_as_superbuild(SLICERSANDBOX_ENABLE_LIGHTS_MODULE)
endif()

#-----------------------------------------------------------------------------
if (NOT DEFINED SLICERSANDBOX_ENABLE_LINEPROFILE_MODULE)
  option(SLICERSANDBOX_ENABLE_LINEPROFILE_MODULE "Enable the building of LineProfile module." ON)
  mark_as_superbuild(SLICERSANDBOX_ENABLE_LINEPROFILE_MODULE)
endif()

#-----------------------------------------------------------------------------
if (NOT DEFINED SLICERSANDBOX_ENABLE_LOADREMOTEFILE_MODULE)
  option(SLICERSANDBOX_ENABLE_LOADREMOTEFILE_MODULE "Enable the building of LoadRemoteFile module." ON)
  mark_as_superbuild(SLICERSANDBOX_ENABLE_LOADREMOTEFILE_MODULE)
endif()

#-----------------------------------------------------------------------------
if (NOT DEFINED SLICERSANDBOX_ENABLE_SCENERECORDER_MODULE)
  option(SLICERSANDBOX_ENABLE_SCENERECORDER_MODULE "Enable the building of SceneRecorder module." ON)
  mark_as_superbuild(SLICERSANDBOX_ENABLE_SCENERECORDER_MODULE)
endif()

#-----------------------------------------------------------------------------
if (NOT DEFINED SLICERSANDBOX_ENABLE_SEGMENTCROSSSECTIONAREA_MODULE)
  option(SLICERSANDBOX_ENABLE_SEGMENTCROSSSECTIONAREA_MODULE "Enable the building of SegmentCrossSectionArea module." ON)
  mark_as_superbuild(SLICERSANDBOX_ENABLE_SEGMENTCROSSSECTIONAREA_MODULE)
endif()

#-----------------------------------------------------------------------------
if (NOT DEFINED SLICERSANDBOX_ENABLE_STITCHVOLUMES_MODULE)
  option(SLICERSANDBOX_ENABLE_STITCHVOLUMES_MODULE "Enable the building of StitchVolumes module." ON)
  mark_as_superbuild(SLICERSANDBOX_ENABLE_STITCHVOLUMES_MODULE)
endif()

#-----------------------------------------------------------------------------
if (NOT DEFINED SLICERSANDBOX_ENABLE_STYLETESTER_MODULE)
  option(SLICERSANDBOX_ENABLE_STYLETESTER_MODULE "Enable the building of StyleTester module." ON)
  mark_as_superbuild(SLICERSANDBOX_ENABLE_STYLETESTER_MODULE)
endif()

#-----------------------------------------------------------------------------
if (NOT DEFINED SLICERSANDBOX_ENABLE_USERSTATISTICS_MODULE)
  option(SLICERSANDBOX_ENABLE_USERSTATISTICS_MODULE "Enable the building of UserStatistics module." ON)
  mark_as_superbuild(SLICERSANDBOX_ENABLE_USERSTATISTICS_MODULE)
endif()


#-----------------------------------------------------------------------------
if (NOT DEFINED SLICERSANDBOX_ENABLE_VOLUMERENDERINGSPECIALEFFECTS_MODULE)
  option(SLICERSANDBOX_ENABLE_VOLUMERENDERINGSPECIALEFFECTS_MODULE "Enable the building of VolumeRenderingSpecialEffects module." ON)
  mark_as_superbuild(SLICERSANDBOX_ENABLE_VOLUMERENDERINGSPECIALEFFECTS_MODULE)
endif()

#-----------------------------------------------------------------------------
if (NOT DEFINED SLICERSANDBOX_ENABLE_REMOVECTTABLE_MODULE)
  option(SLICERSANDBOX_ENABLE_REMOVECTTABLE_MODULE "Enable the building of RemoveCtTable module." ON)
  mark_as_superbuild(SLICERSANDBOX_ENABLE_REMOVECTTABLE_MODULE)
endif()

#-----------------------------------------------------------------------------
if (NOT DEFINED SLICERSANDBOX_ENABLE_COLORIZEVOLUME_MODULE)
  option(SLICERSANDBOX_ENABLE_COLORIZEVOLUME_MODULE "Enable the building of ColorizeVolume module." ON)
  mark_as_superbuild(SLICERSANDBOX_ENABLE_COLORIZEVOLUME_MODULE)
endif()

#-----------------------------------------------------------------------------
# Extension modules

if (SLICERSANDBOX_ENABLE_AUTOSAVE_MODULE)
  add_subdirectory(AutoSave)
endif()

if (SLICERSANDBOX_ENABLE_CHARACTERIZETRANSFORMMATRIX_MODULE)
  add_subdirectory(CharacterizeTransformMatrix)
endif()

if (SLICERSANDBOX_ENABLE_COMBINEMODELS_MODULE)
  add_subdirectory(CombineModels)
endif()

if (SLICERSANDBOX_ENABLE_CURVEDPLANARREFORMAT_MODULE)
  add_subdirectory(CurvedPlanarReformat)
endif()

if (SLICERSANDBOX_ENABLE_DOCUMENTATIONTOOLS_MODULE)
  add_subdirectory(DocumentationTools)
endif()

if (SLICERSANDBOX_ENABLE_IMPORT_MODULES)
  if (Slicer_VERSION VERSION_LESS 5.1)
    # Latest Slicer 5.1 and above has ITK-Snap Label Description File importer built in
    add_subdirectory(ImportItkSnapLabel)
  endif()
  add_subdirectory(ImportNumPyArray)
  add_subdirectory(ImportOCT)
  add_subdirectory(ImportOpenInventor)
  add_subdirectory(ImportOsirixROI)
  add_subdirectory(ImportSliceOmatic)
endif()

if (SLICERSANDBOX_ENABLE_LIGHTS_MODULE)
  add_subdirectory(Lights)
endif()

if (SLICERSANDBOX_ENABLE_LINEPROFILE_MODULE)
  add_subdirectory(LineProfile)
endif()

if (SLICERSANDBOX_ENABLE_LOADREMOTEFILE_MODULE)
  add_subdirectory(LoadRemoteFile)
endif()

if (SLICERSANDBOX_ENABLE_SCENERECORDER_MODULE)
  add_subdirectory(SceneRecorder)
endif()

if (SLICERSANDBOX_ENABLE_SEGMENTCROSSSECTIONAREA_MODULE)
  add_subdirectory(SegmentCrossSectionArea)
endif()

if (SLICERSANDBOX_ENABLE_STITCHVOLUMES_MODULE)
  add_subdirectory(StitchVolumes)
endif()

if (SLICERSANDBOX_ENABLE_STYLETESTER_MODULE)
  add_subdirectory(StyleTester)
endif()

if (SLICERSANDBOX_ENABLE_USERSTATISTICS_MODULE)
  add_subdirectory(UserStatistics)
endif()

if (SLICERSANDBOX_ENABLE_VOLUMERENDERINGSPECIALEFFECTS_MODULE)
  add_subdirectory(VolumeRenderingSpecialEffects)
endif()

if (SLICERSANDBOX_ENABLE_REMOVECTTABLE_MODULE)
  add_subdirectory(RemoveCtTable)
endif()

if (SLICERSANDBOX_ENABLE_COLORIZEVOLUME_MODULE)
  add_subdirectory(ColorizeVolume)
endif()

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})
