project(vtkSlicer${MODULE_NAME}ModuleLogic)

set(KIT ${PROJECT_NAME})

set(${KIT}_EXPORT_DIRECTIVE "VTK_SLICER_${MODULE_NAME_UPPER}_MODULE_LOGIC_EXPORT")

set(${KIT}_INCLUDE_DIRECTORIES
  ${CMAKE_CURRENT_SOURCE_DIR}
  ${CMAKE_CURRENT_SOURCE_DIR}/libs/aabb
  ${CMAKE_CURRENT_SOURCE_DIR}/libs/decomp
  ${CMAKE_CURRENT_SOURCE_DIR}/libs/merger
  ${CMAKE_CURRENT_SOURCE_DIR}/libs/vp
  )

ADD_LIBRARY(vtkboolutil STATIC
  Utilities.cxx
  libs/decomp/Decomposer.cxx
  libs/merger/Merger.cxx
  libs/vp/RmTrivials.cxx
  libs/vp/Tools.cxx
  libs/vp/VisPoly.cxx
)

set(${KIT}_SRCS
  vtkPolyDataBooleanFilter.cxx
  vtkPolyDataBooleanFilter.h
  vtkPolyDataContactFilter.cxx
  vtkPolyDataContactFilter.h
  )

set(${KIT}_TARGET_LIBRARIES
  ${ITK_LIBRARIES}
  vtkboolutil
  )

#-----------------------------------------------------------------------------
SlicerMacroBuildModuleLogic(
  NAME ${KIT}
  EXPORT_DIRECTIVE ${${KIT}_EXPORT_DIRECTIVE}
  INCLUDE_DIRECTORIES ${${KIT}_INCLUDE_DIRECTORIES}
  SRCS ${${KIT}_SRCS}
  TARGET_LIBRARIES ${${KIT}_TARGET_LIBRARIES}
  )
