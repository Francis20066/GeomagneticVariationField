cmake_minimum_required(VERSION 3.20)

project(magerr_core LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

option(MAGERR_BUILD_PYTHON "Build pybind11 Python module" ON)
option(MAGERR_USE_BUNDLED_WMM "Compile bundled WMM2025 C sources" ON)
set(MAGERR_WMM2025_ROOT "" CACHE PATH "Path to external wmm2025 source tree")
set(MAGERR_GEOIST_ROOT "" CACHE PATH "Path to external geoist source tree for staged Swarm port")

add_library(magerr_core
  cpp/core/time.cpp
  cpp/models/wmm2025_provider.cpp
  cpp/models/swarm_external_provider.cpp
  cpp/workflow/field_workflow.cpp
)

target_include_directories(magerr_core
  PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

if(MAGERR_USE_BUNDLED_WMM AND MAGERR_WMM2025_ROOT)
  set(MAGERR_WMM2025_CPP_ROOT ${MAGERR_WMM2025_ROOT}/src/wmm2025)
  target_sources(magerr_core
    PRIVATE
      ${MAGERR_WMM2025_CPP_ROOT}/src/GeomagnetismLibrary.c
      ${MAGERR_WMM2025_CPP_ROOT}/src/wmm_point_sub.c
  )
  target_include_directories(magerr_core
    PRIVATE
      ${MAGERR_WMM2025_CPP_ROOT}/src
  )
  target_compile_definitions(magerr_core PRIVATE MAGERR_HAS_BUNDLED_WMM=1)
elseif(MAGERR_USE_BUNDLED_WMM)
  message(WARNING "MAGERR_USE_BUNDLED_WMM is ON but MAGERR_WMM2025_ROOT is empty; WMM provider will require a linked wmmsub symbol.")
endif()

if(MAGERR_BUILD_PYTHON)
  find_package(pybind11 CONFIG REQUIRED)
  pybind11_add_module(magerr_native bindings/python_module.cpp)
  target_link_libraries(magerr_native PRIVATE magerr_core)
endif()
