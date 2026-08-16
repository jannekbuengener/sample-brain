cmake_minimum_required(VERSION 3.16)
project(samplebrain_audio LANGUAGES CXX C)

# C++ standard
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Build configuration
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib)
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib)

# Platform-specific settings
if(WIN32)
    # Windows: link against required system libraries
    add_definitions(-DMA_WIN32=1)
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} /MP")
    # Miniaudio needs these on Windows
    set(MINIAUDIO_SYSTEM_LIBS ole32 uuidpropsys)
elseif(APPLE)
    add_definitions(-DMA_APPLE=1)
    find_library(COREAUDIO CoreAudio)
    find_library(AUDIOTOOLBOX AudioToolbox)
    find_library(COREFOUNDATION CoreFoundation)
    set(MINIAUDIO_SYSTEM_LIBS ${COREAUDIO} ${AUDIOTOOLBOX} ${COREFOUNDATION})
elseif(UNIX)
    add_definitions(-DMA_LINUX=1)
    find_library(PTHREAD pthread)
    find_library(DL dl)
    find_library(RT rt)
    set(MINIAUDIO_SYSTEM_LIBS ${PTHREAD} ${DL} ${RT})
endif()

# Miniaudio configuration
set(MINIAUDIO_INCLUDE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/third_party)
add_definitions(-DMA_NO_RUNTIME_LINKING=1)
add_definitions(-DMA_API=static)

# Include directories
include_directories(${MINIAUDIO_INCLUDE_DIR} ${CMAKE_CURRENT_SOURCE_DIR}/include)

# Library target
add_library(samplebrain_audio STATIC
    src/engine.cpp
    src/voice.cpp
    src/ringbuffer.cpp
    src/scheduler.cpp
    src/metrics.cpp
    src/synthetic.cpp
)

target_link_libraries(samplebrain_audio ${MINIAUDIO_SYSTEM_LIBS})

# Test executable
enable_testing()
add_executable(samplebrain_audio_tests
    tests/test_engine.cpp
    tests/test_voice.cpp
    tests/test_ringbuffer.cpp
    tests/test_scheduler.cpp
    tests/test_metrics.cpp
)

target_link_libraries(samplebrain_audio_tests samplebrain_audio)
add_test(NAME samplebrain_audio_tests COMMAND samplebrain_audio_tests)

# Installation (optional, for Python FFI)
install(TARGETS samplebrain_audio
    ARCHIVE DESTINATION lib
    LIBRARY DESTINATION lib
    RUNTIME DESTINATION bin
)
install(FILES include/samplebrain_audio.h DESTINATION include)