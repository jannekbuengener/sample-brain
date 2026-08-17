cmake_minimum_required(VERSION 3.16)
project(samplebrain_audio LANGUAGES CXX C)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib)
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib)

if(WIN32)
    if(MSVC)
        add_compile_options(/MP)
    endif()
    # Miniaudio runtime-loads the Windows backends; no extra link library is
    # required here. Do not force MA_WIN32: miniaudio performs platform detection.
    set(MINIAUDIO_SYSTEM_LIBS "")
elseif(APPLE)
    find_library(COREAUDIO CoreAudio)
    find_library(AUDIOTOOLBOX AudioToolbox)
    find_library(COREFOUNDATION CoreFoundation)
    set(MINIAUDIO_SYSTEM_LIBS ${COREAUDIO} ${AUDIOTOOLBOX} ${COREFOUNDATION})
elseif(UNIX)
    find_library(PTHREAD pthread)
    find_library(DL dl)
    find_library(RT rt)
    set(MINIAUDIO_SYSTEM_LIBS ${PTHREAD} ${DL} ${RT})
endif()

# Miniaudio configuration. Runtime linking must stay enabled so optional
# backends such as JACK do not become compile-time header dependencies.
set(MINIAUDIO_INCLUDE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/third_party)
add_definitions(-DMA_API=static)

# Include directories
include_directories(${MINIAUDIO_INCLUDE_DIR} ${CMAKE_CURRENT_SOURCE_DIR}/include)

set(SAMPLEBRAIN_AUDIO_SOURCES
    src/engine.cpp
    src/voice.cpp
    src/keylock_voice.cpp
    src/ringbuffer.cpp
    src/metrics.cpp
    src/synthetic.cpp
)

# Python loads this target through ctypes, so it must be a shared library.
add_library(samplebrain_audio SHARED ${SAMPLEBRAIN_AUDIO_SOURCES})

# The public C API is declared without per-symbol dllexport annotations. Let CMake
# export the target's global symbols on Windows so ctypes can resolve the sb_* API.
set_target_properties(samplebrain_audio PROPERTIES
    WINDOWS_EXPORT_ALL_SYMBOLS ON
)

target_include_directories(samplebrain_audio PRIVATE
    ${MINIAUDIO_INCLUDE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${CMAKE_CURRENT_SOURCE_DIR}/src
)

target_link_libraries(samplebrain_audio PRIVATE ${MINIAUDIO_SYSTEM_LIBS})

# Hosted CI runners do not provide a dependable physical duplex audio device.
# Compile the same core a second time for native CTest with miniaudio's null
# backend only. This keeps production runtime behavior on the real platform
# backend while making transport/voice/recording logic deterministic headlessly.
add_library(samplebrain_audio_test_backend STATIC ${SAMPLEBRAIN_AUDIO_SOURCES})
target_compile_definitions(samplebrain_audio_test_backend PRIVATE
    SAMPLEBRAIN_AUDIO_TEST_NULL_BACKEND=1
)
target_link_libraries(samplebrain_audio_test_backend PRIVATE ${MINIAUDIO_SYSTEM_LIBS})

# Every native test file owns its own main(), so build them as independent
# executables instead of linking all test translation units into one binary.
enable_testing()
set(SAMPLEBRAIN_AUDIO_TESTS
    engine
    voice
    ringbuffer
    scheduler
    metrics
)

foreach(test_name IN LISTS SAMPLEBRAIN_AUDIO_TESTS)
    set(test_target samplebrain_audio_test_${test_name})
    add_executable(${test_target} tests/test_${test_name}.cpp)
    target_link_libraries(${test_target} PRIVATE samplebrain_audio_test_backend)
    add_test(NAME ${test_target} COMMAND ${test_target})
endforeach()

install(TARGETS samplebrain_audio
    ARCHIVE DESTINATION lib
    LIBRARY DESTINATION lib
    RUNTIME DESTINATION bin
)
install(FILES include/samplebrain_audio.h DESTINATION include)
