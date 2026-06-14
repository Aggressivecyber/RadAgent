"""Canonical CMakeLists.txt for RadAgent-generated Geant4 projects.

Derived from the Geant4 B1 example. It ``file(GLOB)``s every ``src/*.cc`` and
``include/*.hh``, so ALL generated sources compile automatically with UI/Vis/Qt
enabled — no per-project source listing, no from-scratch CMake. This is both
shown to the runtime_app module agent (so it does not reinvent CMake) and
force-applied by the integration assembler (so the final project always has a
correct CMakeLists regardless of what the model wrote).
"""

RADAGENT_CMAKE_TEMPLATE = """\
cmake_minimum_required(VERSION 3.16...3.27)
project(RadAgentG4)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Geant4 with all UI + Vis drivers (incl. Qt/OGL), same as the B1 example.
find_package(Geant4 REQUIRED ui_all vis_all)

# Auto-include every generated source/header — never hand-list files.
file(GLOB sources ${PROJECT_SOURCE_DIR}/src/*.cc)
file(GLOB headers ${PROJECT_SOURCE_DIR}/include/*.hh)

add_executable(RadAgentG4 main.cc ${sources} ${headers})
target_include_directories(RadAgentG4 PRIVATE include)
target_link_libraries(RadAgentG4 PRIVATE ${Geant4_LIBRARIES})
"""

CMAKE_PATH = "CMakeLists.txt"
