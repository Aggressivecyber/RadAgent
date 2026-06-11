cmake_minimum_required(VERSION 3.16...3.27)
project(RadAgentG4)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Find Geant4 package with all UI and Vis drivers
find_package(Geant4 REQUIRED ui_all vis_all)

# Collect sources from all modules
set(SOURCES
  # simulation_core sources
  src/MaterialRegistry.cc
  src/PlacementManager.cc
  src/DetectorConstruction.cc
  src/Hit.cc
  src/SensitiveDetector.cc
  src/ScoringManager.cc
  # beam_physics sources
  src/PrimaryGeneratorAction.cc
  src/PhysicsListFactoryWrapper.cc
  # runtime_app sources
  src/OutputManager.cc
  src/ActionInitialization.cc
  src/RunAction.cc
  src/EventAction.cc
  src/SteppingAction.cc
  # main
  main.cc
)

add_executable(RadAgentG4 ${SOURCES})
target_include_directories(RadAgentG4 PRIVATE ${PROJECT_SOURCE_DIR}/include)
target_link_libraries(RadAgentG4 PRIVATE ${Geant4_LIBRARIES})

# Copy macros to build directory
set(MACRO_FILES
  macros/init.mac
  macros/run.mac
  macros/physics_list.mac
)

foreach(_macro ${MACRO_FILES})
  if(EXISTS ${PROJECT_SOURCE_DIR}/${_macro})
    configure_file(
      ${PROJECT_SOURCE_DIR}/${_macro}
      ${PROJECT_BINARY_DIR}/${_macro}
      COPYONLY
    )
  endif()
endforeach()
