cmake_minimum_required(VERSION 3.10)
project(Geant4VoxelSim)

find_package(Geant4 REQUIRED)

include(${Geant4_USE_FILE})

add_executable(geant4_sim
  geant4_sim.cc
  DetectorConstruction.cc
  PrimaryGeneratorAction.cc
  RunAction.cc
  VoxelScorer.cc
  SensitiveDetector.cc
)

target_link_libraries(geant4_sim ${Geant4_LIBRARIES})

# Optional: set C++ standard
set_target_properties(geant4_sim PROPERTIES CXX_STANDARD 11)
