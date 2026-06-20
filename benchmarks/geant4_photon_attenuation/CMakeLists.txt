cmake_minimum_required(VERSION 3.16)
project(radagent_photon_attenuation_benchmark)

find_package(Geant4 REQUIRED)
include(${Geant4_USE_FILE})

add_executable(photon_attenuation main.cc)
target_link_libraries(photon_attenuation ${Geant4_LIBRARIES})
