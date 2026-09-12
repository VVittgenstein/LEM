cmake_minimum_required(VERSION 3.20)
project(voxel_terrain_viewer LANGUAGES CXX)

find_package(OpenMP QUIET)

set(LEM_RAYLIB_PREFIX "" CACHE PATH "Prefix containing raylib include/ and lib/")
if(LEM_RAYLIB_PREFIX)
    find_path(LEM_RAYLIB_INCLUDE_DIR raylib.h
        PATHS "${LEM_RAYLIB_PREFIX}/include"
        NO_DEFAULT_PATH
        REQUIRED)
    find_library(LEM_RAYLIB_LIBRARY raylib
        PATHS "${LEM_RAYLIB_PREFIX}/lib"
        NO_DEFAULT_PATH
        REQUIRED)
    add_library(lem_raylib STATIC IMPORTED)
    set_target_properties(lem_raylib PROPERTIES
        IMPORTED_LOCATION "${LEM_RAYLIB_LIBRARY}"
        INTERFACE_INCLUDE_DIRECTORIES "${LEM_RAYLIB_INCLUDE_DIR}")
else()
    find_package(raylib CONFIG REQUIRED)
    add_library(lem_raylib ALIAS raylib)
endif()

file(GLOB_RECURSE SOURCE_FILES CONFIGURE_DEPENDS *.cpp *.h)

add_executable(voxel_terrain_viewer ${SOURCE_FILES})
target_compile_features(voxel_terrain_viewer PRIVATE cxx_std_17)

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(voxel_terrain_viewer PRIVATE -Wall -Wextra -Wpedantic)
endif()

target_include_directories(voxel_terrain_viewer PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/core
)

target_link_libraries(voxel_terrain_viewer PRIVATE lem_raylib)

if(UNIX AND NOT APPLE AND LEM_RAYLIB_PREFIX)
    target_link_libraries(voxel_terrain_viewer PRIVATE
        m pthread dl rt X11 Xrandr Xi Xinerama Xcursor GL)
endif()

if(TARGET OpenMP::OpenMP_CXX)
    target_link_libraries(voxel_terrain_viewer PRIVATE OpenMP::OpenMP_CXX)
endif()

# Resources are optional because the viewer has built-in palette defaults and
# accepts an explicit .flem path. Copy them when a resources directory exists.
if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/resources")
    add_custom_command(
        TARGET voxel_terrain_viewer POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_directory
        "${CMAKE_CURRENT_SOURCE_DIR}/resources"
        "$<TARGET_FILE_DIR:voxel_terrain_viewer>/resources"
    )
endif()
