cmake_minimum_required(VERSION 3.5)

project(Sandbox)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://github.com/PerkLab/SlicerSandbox")
set(EXTENSION_CATEGORY "Examples")
set(EXTENSION_CONTRIBUTORS "Csaba Pinter (Queen's University), Andras Lasso (Queen's University)")
set(EXTENSION_DESCRIPTION "Collection of utilities that are not polished implementations but can be useful to users")
set(EXTENSION_ICONURL "https://github.com/PerkLab/SlicerSandbox/raw/master/Sandbox_Logo_128.png")
set(EXTENSION_SCREENSHOTURLS "")
set(EXTENSION_DEPENDS "NA") # Specified as a space separated string, a list or 'NA' if any

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(LineProfile)
add_subdirectory(Lights)
add_subdirectory(UserStatistics)
add_subdirectory(CurvedPlanarReformat)
add_subdirectory(AutoSave)
add_subdirectory(ImportOsirixROI)
add_subdirectory(VolumeRenderingSpecialEffects)
add_subdirectory(SegmentCrossSectionArea)

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})
