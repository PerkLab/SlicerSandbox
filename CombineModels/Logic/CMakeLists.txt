project(vtkSlicer${MODULE_NAME}ModuleLogic)

set(KIT ${PROJECT_NAME})

set(${KIT}_EXPORT_DIRECTIVE "VTK_SLICER_${MODULE_NAME_UPPER}_MODULE_LOGIC_EXPORT")

set(${KIT}_INCLUDE_DIRECTORIES
  ${CMAKE_CURRENT_SOURCE_DIR}
  )

set(${KIT}_SRCS
# private details
  Utilities.cxx
  Optimize.cxx
  Contact.cxx
  Merger.cxx
# public
  vtkPolyDataBooleanFilter.cxx
  vtkPolyDataBooleanFilter.h
# octree backend, which only needs VTK
  vtkOctreeBooleanFilter.cxx
  vtkOctreeBooleanFilter.h
  )

set_source_files_properties(
  Utilities.cxx
  Optimize.cxx
  Contact.cxx
  Merger.cxx
  WRAP_EXCLUDE
  )

set(${KIT}_TARGET_LIBRARIES
  ${ITK_LIBRARIES}
  )

#-----------------------------------------------------------------------------
# kigumi backend (https://github.com/unageek/kigumi, MIT license).
# kigumi/include, vtkKigumiBooleanFilter.{h,cxx}, vtkKigumiBooleanSequenceFilter.{h,cxx},
# vtkKigumiMeshDefectsFilter.{h,cxx} and vtkKigumiBooleanInternals.h are copied from the CGAL-free kigumi fork
# (https://github.com/mauigna06/kigumi), branch vtk-backend, commit 3d7048e.
# kigumi requires C++20 and the header-only parts of Boost >= 1.81, which Slicer
# does not provide, so Boost is downloaded at configure time.
option(CombineModels_USE_KIGUMI "Build the kigumi Boolean backend (downloads Boost)" ON)

if(CombineModels_USE_KIGUMI)
  list(APPEND ${KIT}_SRCS
    vtkKigumiBooleanFilter.cxx
    vtkKigumiBooleanFilter.h
    vtkKigumiBooleanSequenceFilter.cxx
    vtkKigumiBooleanSequenceFilter.h
    vtkKigumiMeshDefectsFilter.cxx
    vtkKigumiMeshDefectsFilter.h
    )

  # Build the Boost libraries statically into the logic library and keep them out
  # of the extension package. Set FETCHCONTENT_SOURCE_DIR_BOOST to build offline.
  function(combinemodels_fetch_boost)
    include(FetchContent)
    set(BUILD_SHARED_LIBS OFF)
    set(BUILD_TESTING OFF)
    set(CMAKE_POSITION_INDEPENDENT_CODE ON)
    set(BOOST_SKIP_INSTALL_RULES ON)
    set(BOOST_INCLUDE_LIBRARIES container container_hash endian iterator multiprecision range unordered)
    FetchContent_Declare(Boost
      URL https://github.com/boostorg/boost/releases/download/boost-1.92.0/boost-1.92.0-cmake.tar.xz
      URL_HASH SHA256=9bed76128d4e46755dbe818487788c6fceb6f72b378f4daa49b7e1e600d9088d
      DOWNLOAD_EXTRACT_TIMESTAMP ON
      )
    FetchContent_MakeAvailable(Boost)
  endfunction()
  combinemodels_fetch_boost()

  find_package(Threads REQUIRED)
endif()

#-----------------------------------------------------------------------------
SlicerMacroBuildModuleLogic(
  NAME ${KIT}
  EXPORT_DIRECTIVE ${${KIT}_EXPORT_DIRECTIVE}
  INCLUDE_DIRECTORIES ${${KIT}_INCLUDE_DIRECTORIES}
  SRCS ${${KIT}_SRCS}
  TARGET_LIBRARIES ${${KIT}_TARGET_LIBRARIES}
  )

if(CombineModels_USE_KIGUMI)
  target_compile_features(${KIT} PRIVATE cxx_std_20)
  target_include_directories(${KIT} PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/kigumi/include)
  # Link privately, so that Boost stays out of the exported interface. SlicerMacroBuildModuleLogic
  # uses the plain target_link_libraries() signature, which cannot be mixed with PRIVATE.
  set_property(TARGET ${KIT} APPEND PROPERTY LINK_LIBRARIES
    Boost::container
    Boost::container_hash
    Boost::endian
    Boost::iterator
    Boost::multiprecision
    Boost::range
    Boost::unordered
    Threads::Threads
    )
endif()
