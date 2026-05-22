cmake_minimum_required(VERSION 3.16 FATAL_ERROR)
project(radg4_multilayer)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(Geant4 REQUIRED ui_all)

include(${Geant4_USE_FILE})

include_directories(${PROJECT_SOURCE_DIR}/include)

file(GLOB sources ${PROJECT_SOURCE_DIR}/src/*.cc)
file(GLOB headers ${PROJECT_SOURCE_DIR}/include/*.hh)

add_executable(radg4_sim exampleB1.cc ${sources} ${headers})
target_link_libraries(radg4_sim ${Geant4_LIBRARIES})
