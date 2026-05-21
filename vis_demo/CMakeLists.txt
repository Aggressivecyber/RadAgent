cmake_minimum_required(VERSION 3.16)
project(radagent_vis LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)

find_package(Qt5 REQUIRED COMPONENTS Widgets OpenGL)
find_package(OpenGL REQUIRED)

add_executable(radagent_vis
    main.cpp
    GLWidget.h
    GLWidget.cpp
    SceneBuilder.h
    SceneBuilder.cpp
    Camera.h
    Camera.cpp
    ParticleData.h
    ParticleData.cpp
)

target_include_directories(radagent_vis PRIVATE
    ${OPENGL_INCLUDE_DIRS}
)

target_link_libraries(radagent_vis PRIVATE
    Qt5::Widgets
    Qt5::OpenGL
    OpenGL::GL
)

file(COPY shaders DESTINATION ${CMAKE_BINARY_DIR})
