cmake_minimum_required(VERSION 3.20)

project(magerr_core LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

option(MAGERR_BUILD_PYTHON "Build pybind11 Python module" ON)
option(MAGERR_USE_BUNDLED_WMM "Compile bundled WMM2025 C sources" ON)
set(MAGERR_GEOIST_ROOT "" CACHE PATH "Path to external geoist source tree for staged Swarm port")

add_library(magerr_core
  cpp/core/time.cpp
  cpp/models/wmm2025_provider.cpp
  cpp/models/swarm_external_provider.cpp
  cpp/workflow/field_workflow.cpp
)

if(MAGERR_USE_BUNDLED_WMM)
  target_sources(magerr_core
    PRIVATE
      third_party/wmm2025/src/GeomagnetismLibrary.c
  )
  target_include_directories(magerr_core
    PRIVATE
      ${CMAKE_CURRENT_SOURCE_DIR}/third_party/wmm2025/src
  )
  target_compile_definitions(magerr_core
    PRIVATE
      MAGERR_DEFAULT_RESOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}/resources"
  )
endif()

target_include_directories(magerr_core
  PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
  PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/third_party/geoist_magmod/include
)

if(MAGERR_BUILD_PYTHON)
  set(PYBIND11_FINDPYTHON ON)
  find_package(Python COMPONENTS Interpreter Development.Module REQUIRED)
  find_package(pybind11 CONFIG REQUIRED)
  pybind11_add_module(magerr_native bindings/python_module.cpp)
  target_link_libraries(magerr_native PRIVATE magerr_core)
  install(TARGETS magerr_native LIBRARY DESTINATION . RUNTIME DESTINATION .)
  install(DIRECTORY resources/ DESTINATION resources)
endif()
