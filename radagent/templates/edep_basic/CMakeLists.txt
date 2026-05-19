cmake_minimum_required(VERSION 3.16...3.27)
project(RadG4)

find_package(Geant4 REQUIRED ui_all vis_all)

file(GLOB sources ${PROJECT_SOURCE_DIR}/src/*.cc)
file(GLOB headers ${PROJECT_SOURCE_DIR}/include/*.hh)

add_executable(radg4_sim exampleB1.cc ${sources} ${headers})
target_include_directories(radg4_sim PRIVATE include)
target_link_libraries(radg4_sim PRIVATE ${Geant4_LIBRARIES})
