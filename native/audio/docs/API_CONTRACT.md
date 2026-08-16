# samplebrain_audio Native API Contract

## Overview
This document defines the C-compatible API for the samplebrain_audio native core.
The API is designed for real-time audio processing with strict realtime constraints.

## Version
API Version: 1.0.0
Issue: #321 — [AUDIO] Build native miniaudio/WASAPI core proof of concept

## Design Principles
- **Single authoritative clock**: Engine frame counter is the only time source
- **Realtime-safe**: No heap allocations, locks, or blocking in audio callback
- **Command queue**: Control operations via lock-free command ring buffer
- **Snapshot polling**: Metrics via non-blocking snapshot reads
- **No Python in audio thread**: Pure C++ hot path

## Types

```c
// Opaque handles
typedef struct sb_engine* sb_engine_t;
typedef struct sb_voice* sb_voice_t;
typedef struct sb_recording* sb_recording_t;

// Identifiers (uint64_t for future extensibility)
typedef uint64_t sb_voice_id_t;
typedef uint64_t sb_recording_id_t;
typedef int64_t sb_frame_t;  // Signed for relative operations

// Result codes
typedef enum {
    SB_OK = 0,
    SB_ERR_INVALID_ARG = -1,
    SB_ERR_NOT_INITIALIZED = -2,
    SB_ERR_ALREADY_RUNNING = -3,
    SB_ERR_DEVICE_ERROR = -4,
    SB_ERR_OUT_OF_MEMORY = -5,
    SB_ERR_VOICE_NOT_FOUND = -6,
    SB_ERR_RECORDING_NOT_FOUND = -7,
    SB_ERR_INVALID_STATE = -8,
    SB_ERR_UNSUPPORTED = -9
} sb_result_t;

// Device status
typedef enum {
    SB_DEVICE_OK = 0,
    SB_DEVICE_LOST = 1,
    SB_DEVICE_RECOVERING = 2,
    SB_DEVICE_FAILED = 3
} sb_device_status_t;

// Voice state
typedef enum {
    SB_VOICE_IDLE = 0,
    SB_VOICE_SCHEDULED = 1,
    SB_VOICE_PLAYING = 2,
    SB_VOICE_STOPPING = 3
} sb_voice_state_t;

// Source descriptor types
typedef enum {
    SB_SOURCE_SYNTHETIC_CLICK = 0,  // Generated click track at specified BPM
    SB_SOURCE_PCM_BUFFER = 1        // Pre-loaded PCM buffer (future)
} sb_source_type_t;

// Synthetic click configuration
typedef struct {
    double bpm;           // Click BPM (e.g., 128.0, 140.0)
    float frequency_hz;   // Click frequency (default 800 Hz)
    float duration_ms;    // Click duration (default 5 ms)
    float amplitude;      // Click amplitude (default 0.8)
} sb_synthetic_click_config_t;

// Source descriptor (discriminated union)
typedef struct {
    sb_source_type_t type;
    union {
        sb_synthetic_click_config_t synthetic_click;
        // Future: PCM buffer descriptor
    };
} sb_source_descriptor_t;

// Engine configuration
typedef struct {
    uint32_t sample_rate;       // e.g., 48000, 44100
    uint32_t buffer_frames;     // e.g., 512, 256, 128, 64
    uint32_t output_channels;   // Typically 2
    uint32_t input_channels;    // Typically 2 (for recording)
    const char* output_device;  // NULL = default
    const char* input_device;   // NULL = default (same clock domain preferred)
    void* user_data;            // Passed to callbacks
} sb_engine_config_t;

// Voice configuration
typedef struct {
    sb_voice_id_t id;                    // Assigned by caller, must be unique
    sb_source_descriptor_t source;       // What to play
    float initial_rate;                  // Playback rate (1.0 = normal)
    float gain;                          // Linear gain (1.0 = unity)
} sb_voice_config_t;

// Snapshot/metrics structure (read-only, populated by sb_engine_snapshot)
typedef struct {
    // Engine state
    sb_frame_t engine_frame;            // Monotonic frame counter
    bool running;                       // Engine running state
    uint32_t sample_rate;               // Actual sample rate
    uint32_t buffer_frames;             // Actual buffer size
    sb_device_status_t device_status;   // Current device status
    uint32_t recovery_state;            // Recovery state machine value

    // Voice metrics
    uint32_t active_voice_count;        // Currently playing voices
    uint32_t total_voice_count;         // Total created voices

    // Per-voice arrays (max SB_MAX_VOICES)
    sb_voice_id_t voice_ids[32];
    sb_voice_state_t voice_states[32];
    sb_frame_t requested_start_frame[32];
    sb_frame_t actual_start_frame[32];
    int32_t start_skew_frames[32];      // actual - requested
    float voice_rates[32];
    float voice_gains[32];

    // Callback timing (microseconds)
    double callback_mean_us;
    double callback_p95_us;
    double callback_p99_us;
    double callback_max_us;

    // Xrun counters
    uint64_t underflow_count;
    uint64_t overflow_count;
    uint64_t xrun_count;

    // Recording
    uint64_t recording_dropped_frames;
    bool recording_active;

    // Reserved for future expansion
    uint64_t reserved[16];
} sb_snapshot_t;

// Maximum limits
#define SB_MAX_VOICES 32
#define SB_MAX_RECORDINGS 8
#define SB_MAX_DEVICE_NAME 256
```

## Engine Lifecycle

### sb_engine_open
```c
sb_result_t sb_engine_open(const sb_engine_config_t* config, sb_engine_t* out_engine);
```
- Creates and initializes the audio engine
- Does NOT start audio processing
- Validates config, opens WASAPI Shared device
- Returns SB_OK on success, error code on failure
- `out_engine` is valid only on success

### sb_engine_start
```c
sb_result_t sb_engine_start(sb_engine_t engine);
```
- Starts the audio callback thread
- Begins processing audio frames
- Engine frame counter starts at 0
- Returns SB_OK on success, SB_ERR_ALREADY_RUNNING if already started

### sb_engine_stop
```c
sb_result_t sb_engine_stop(sb_engine_t engine);
```
- Stops the audio callback thread
- Waits for callback to finish current buffer
- Preserves engine frame counter
- Returns SB_OK on success, SB_ERR_INVALID_STATE if not running

### sb_engine_close
```c
sb_result_t sb_engine_close(sb_engine_t engine);
```
- Destroys engine, releases all resources
- Must be called after sb_engine_stop
- Invalidates engine handle
- Returns SB_OK on success

## Voice Lifecycle

### sb_voice_create
```c
sb_result_t sb_voice_create(sb_engine_t engine, const sb_voice_config_t* config, sb_voice_id_t* out_id);
```
- Creates a new voice with given configuration
- For synthetic click sources, generates click pattern at specified BPM
- Voice starts in SB_VOICE_IDLE state
- Returns SB_OK on success, `out_id` set to config->id

### sb_voice_remove
```c
sb_result_t sb_voice_remove(sb_engine_t engine, sb_voice_id_t id);
```
- Removes a voice, freeing its resources
- If voice is playing, stops it first
- Returns SB_OK on success, SB_ERR_VOICE_NOT_FOUND if not found

### sb_voice_schedule_start
```c
sb_result_t sb_voice_schedule_start(sb_engine_t engine, sb_voice_id_t id, sb_frame_t engine_frame);
```
- Schedules voice to start at exact engine frame
- Frame must be >= current engine frame
- Voice transitions to SB_VOICE_SCHEDULED
- At target frame, transitions to SB_VOICE_PLAYING
- Returns SB_OK on success

### sb_voice_stop
```c
sb_result_t sb_voice_stop(sb_engine_t engine, sb_voice_id_t id);
```
- Stops a playing or scheduled voice
- Voice transitions to SB_VOICE_STOPPING then SB_VOICE_IDLE
- Returns SB_OK on success

### sb_voice_set_rate
```c
sb_result_t sb_voice_set_rate(sb_engine_t engine, sb_voice_id_t id, float rate);
```
- Changes playback rate in real-time
- Rate applied from next audio callback
- Typical range: 0.25 to 4.0
- For SYNC: rate = target_bpm / source_bpm
- Returns SB_OK on success

## Recording

### sb_recording_start
```c
sb_result_t sb_recording_start(sb_engine_t engine, sb_recording_id_t* out_id, sb_frame_t engine_frame);
```
- Starts recording at exact engine frame
- Allocates ring buffer (pre-allocated, sized for max recording duration)
- Audio callback writes directly to ring buffer (no allocation)
- Returns SB_OK on success, `out_id` assigned

### sb_recording_stop
```c
sb_result_t sb_recording_stop(sb_engine_t engine, sb_recording_id_t id, float** out_buffer, size_t* out_frames);
```
- Stops recording, returns recorded audio data
- `out_buffer` points to contiguous buffer (caller must free with sb_recording_free_buffer)
- `out_frames` = number of frames recorded per channel
- Returns SB_OK on success

### sb_recording_free_buffer
```c
void sb_recording_free_buffer(float* buffer);
```
- Frees buffer returned by sb_recording_stop

## Snapshot / Metrics

### sb_engine_snapshot
```c
sb_result_t sb_engine_snapshot(sb_engine_t engine, sb_snapshot_t* out_snapshot);
```
- Non-blocking read of current engine state and metrics
- Must be callable from any thread (including Python)
- Does not block audio thread
- Populates all fields in `out_snapshot`
- Returns SB_OK on success

## Real-time Constraints

### Audio Callback Prohibitions
The following are **strictly forbidden** in the audio callback:
- Any heap allocation (malloc, new, std::vector, etc.)
- Any blocking operation (mutex, condition_variable, sleep, I/O)
- Any system call that may block
- Python C API calls
- SQLite or any database access
- File I/O (read, write, open, close)
- Logging to disk
- Network operations
- Dynamic memory allocation

### Allowed in Audio Callback
- Lock-free ring buffer operations (atomic indices)
- Fixed-size array operations
- Atomic load/store operations
- Simple arithmetic
- miniaudio data conversion helpers

### Command Queue
Control operations (voice create, schedule, rate change) are submitted via
a lock-free single-producer single-consumer ring buffer:
- Producer: Python/control thread
- Consumer: Audio callback thread
- Commands executed at next callback boundary
- Frame-accurate scheduling via engine_frame targeting

## Error Handling
- All functions return sb_result_t
- SB_OK (0) = success
- Negative values = errors
- On error, output parameters are not modified
- Engine remains in valid state after any error

## Thread Safety
- sb_engine_open/close: Not thread-safe (caller must serialize)
- sb_engine_start/stop: Thread-safe wrt each other
- sb_voice_*: Thread-safe (commands queued to audio thread)
- sb_recording_*: Thread-safe (commands queued)
- sb_engine_snapshot: Thread-safe (lock-free read)
- Audio callback: Single-threaded, no concurrent access

## Device Recovery
- On device loss: callback receives NULL buffers, device_status = SB_DEVICE_LOST
- Engine attempts automatic recovery (re-init device)
- During recovery: device_status = SB_DEVICE_RECOVERING
- On recovery success: device_status = SB_DEVICE_OK, engine_frame continues
- On recovery failure: device_status = SB_DEVICE_FAILED, engine stops
- No crash or deadlock in any case

## Build Requirements
- C++17 compiler (MSVC 19.20+, GCC 7+, Clang 6+)
- CMake 3.16+
- miniaudio.h (vendored at third_party/miniaudio.h, v0.11.25)
- Windows: WASAPI (Windows 10+)
- No other external dependencies

## Python FFI Binding (src/native_audio.py)
```python
# Minimal ctypes binding
# Loads native library, exposes:
# - open_engine(config) -> engine_handle
# - start_engine(handle)
# - stop_engine(handle)
# - close_engine(handle)
# - create_voice(handle, config) -> voice_id
# - remove_voice(handle, voice_id)
# - schedule_voice_start(handle, voice_id, engine_frame)
# - stop_voice(handle, voice_id)
# - set_voice_rate(handle, voice_id, rate)
# - start_recording(handle, engine_frame) -> recording_id
# - stop_recording(handle, recording_id) -> (buffer, frames)
# - snapshot(handle) -> Snapshot dataclass
```

## Test Contract (tests/)
Unit tests must verify:
1. Engine open/start/stop/close lifecycle
2. Voice create/schedule/start/stop/rate
3. Two voices scheduled at same frame -> start_skew_frames == 0
4. Rate change applied at next callback
5. Recording ring buffer accounting
6. Snapshot reads without blocking audio thread
7. Clock monotonicity (engine_frame always increases)
8. Device state machine transitions

## Hardware Validation Matrix (Issue #321)
| Buffer | Playback | Playback+Rec | 10-min Drift | Device Lost |
|--------|----------|-------------|--------------|-------------|
| 512    | PASS     | PASS        | PASS         | PASS        |
| 256    | PASS     | PASS        | PASS         | PASS        |
| 128    | PASS     | PASS        | PASS         | PASS        |
| 64     | OPTIONAL | OPTIONAL    | OPTIONAL     | OPTIONAL    |

Required metrics per run:
- requested_start_frame per voice
- actual_start_frame per voice
- start_skew_frames (MUST be 0 for PASS)
- callback_mean_us, callback_p95_us, callback_p99_us, callback_max_us
- underflow_count, overflow_count, xrun_count
- recording_dropped_frames
- engine_frame at start/end
- relative voice drift to grid reference
- device_recovery_result

## Non-Goals (Explicit)
- ASIO support
- Signalsmith Stretch integration
- Key-lock / pitch preservation
- Full plugin infrastructure
- Multi-backend abstraction layer
- File decoding in audio callback
- Automatic recording playlist management (#325)