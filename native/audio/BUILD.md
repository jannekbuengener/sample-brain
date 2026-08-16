# Building samplebrain_audio on Windows

## Prerequisites

- Windows 10/11 (64-bit)
- Visual Studio 2022 (Community/Professional/Enterprise) with "Desktop development with C++" workload
- CMake 3.16+ (included with VS 2022)
- Python 3.12+ (for FFI testing)

## Build Steps

### 1. Open Developer Command Prompt
Open "x64 Native Tools Command Prompt for VS 2022" from Start menu, or run:
```cmd
"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" x64
```

### 2. Configure and Build
```cmd
cd native\audio
mkdir build
cd build
cmake .. -G "Visual Studio 17 2022" -A x64
cmake --build . --config Release
```

### 3. Run Tests
```cmd
ctest -C Release --output-on-failure
```
Or run the test executable directly:
```cmd
.\Release\samplebrain_audio_tests.exe
```

### 4. Verify Library Output
The build produces:
- `build/lib/Release/samplebrain_audio.lib` - Static library
- `build/bin/Release/samplebrain_audio.dll` - Dynamic library (if built as shared)

For Python FFI, copy `samplebrain_audio.dll` to a location in PATH or next to `src/native_audio.py`.

## Python FFI Test
```cmd
cd sample-brain
python -m src.native_audio
```

## Hardware Validation Matrix

Run the following tests on actual Windows audio hardware:

| Test | Buffer | Duration | Expected |
|------|--------|----------|----------|
| Playback only | 512 | 10 min | PASS |
| Playback + Recording | 512 | 10 min | PASS |
| Playback only | 256 | 10 min | PASS |
| Playback + Recording | 256 | 10 min | PASS |
| Playback only | 128 | 10 min | PASS |
| Playback + Recording | 128 | 10 min | PASS |
| Device Lost/Recovery | 512 | N/A | PASS |

### Metrics to Collect
For each test, record:
- `start_skew_frames` for both voices (MUST be 0)
- `callback_mean_us`, `callback_p95_us`, `callback_p99_us`, `callback_max_us`
- `underflow_count`, `overflow_count`, `xrun_count`
- `recording_dropped_frames`
- Engine frame at start/end
- Relative voice drift to grid reference
- Device recovery result

## Troubleshooting

### CMake not found
Install CMake from https://cmake.org/download/ or use Visual Studio Installer to add "CMake tools for Windows".

### Miniaudio errors
Ensure `third_party/miniaudio.h` exists and is v0.11.25 or compatible.

### WASAPI not available
- Requires Windows 10+
- Run `msinfo32` to verify audio drivers
- Check Windows Audio service is running

### Device lost test
To test device loss:
1. Start engine with specific device
2. In Windows Sound settings, disable the output device
3. Observe `device_status` in snapshot transitions: OK → LOST → RECOVERING → OK/FAILED
4. Re-enable device
5. Verify no crash/deadlock

## CI/CD Notes
This native component is NOT built in GitHub Actions CI (requires Windows runners with VS 2022).
Local validation on Windows hardware is required per issue #321 acceptance criteria.

## License
miniaudio: MIT-0 / Public Domain (see third_party/miniaudio.h)
samplebrain_audio: MIT (project license)