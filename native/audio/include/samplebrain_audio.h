#ifndef SAMPLEBRAIN_AUDIO_H
#define SAMPLEBRAIN_AUDIO_H

// The public C API is exported by the build system (WINDOWS_EXPORT_ALL_SYMBOLS on
// Windows), so the SAMPLEBRAIN_EXPORT annotation is intentionally a no-op here.
#ifndef SAMPLEBRAIN_EXPORT
#define SAMPLEBRAIN_EXPORT
#endif

#include <stddef.h>
#include <stdint.h>
#ifndef __cplusplus
#include <stdbool.h>
#endif

#ifdef __cplusplus
extern "C" {
#endif

// Opaque handles
typedef struct sb_engine* sb_engine_t;
typedef struct sb_voice* sb_voice_t;
typedef struct sb_recording* sb_recording_t;

// Identifiers
typedef uint64_t sb_voice_id_t;
typedef uint64_t sb_recording_id_t;
typedef int64_t sb_frame_t;

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
    SB_SOURCE_SYNTHETIC_CLICK = 0,
    SB_SOURCE_PCM_BUFFER = 1
} sb_source_type_t;

// Synthetic click configuration
typedef struct {
    double bpm;
    float frequency_hz;
    float duration_ms;
    float amplitude;
} sb_synthetic_click_config_t;

// Source descriptor
typedef struct {
    sb_source_type_t type;
    union {
        sb_synthetic_click_config_t synthetic_click;
    };
} sb_source_descriptor_t;

// Engine configuration
typedef struct {
    uint32_t sample_rate;
    uint32_t buffer_frames;
    uint32_t output_channels;
    uint32_t input_channels;
    const char* output_device;
    const char* input_device;
    void* user_data;
} sb_engine_config_t;

// Voice configuration
typedef struct {
    sb_voice_id_t id;
    sb_source_descriptor_t source;
    float initial_rate;
    float gain;
    int sync_mode;
    float source_bpm;
    float master_bpm;
} sb_voice_config_t;

// Snapshot/metrics
typedef struct {
    sb_frame_t engine_frame;
    bool running;
    uint32_t sample_rate;
    uint32_t buffer_frames;
    sb_device_status_t device_status;
    uint32_t recovery_state;

    uint32_t active_voice_count;
    uint32_t total_voice_count;

    sb_voice_id_t voice_ids[32];
    sb_voice_state_t voice_states[32];
    sb_frame_t requested_start_frame[32];
    sb_frame_t actual_start_frame[32];
    int32_t start_skew_frames[32];
    float voice_rates[32];
    float voice_gains[32];

    // #324 Key-Lock extensions
    int voice_sync_modes[32];
    bool voice_key_lock_active[32];
    int32_t voice_input_latency_frames[32];
    int32_t voice_output_latency_frames[32];
    int32_t voice_grid_compensation_frames[32];

    double callback_mean_us;
    double callback_p95_us;
    double callback_p99_us;
    double callback_max_us;

    uint64_t underflow_count;
    uint64_t overflow_count;
    uint64_t xrun_count;

    uint64_t recording_dropped_frames;
    bool recording_active;

    uint64_t reserved[8];
} sb_snapshot_t;

#define SB_MAX_VOICES 32
#define SB_MAX_RECORDINGS 8
#define SB_MAX_DEVICE_NAME 256

// Engine lifecycle
SAMPLEBRAIN_EXPORT sb_result_t sb_engine_open(const sb_engine_config_t* config, sb_engine_t* out_engine);
SAMPLEBRAIN_EXPORT sb_result_t sb_engine_start(sb_engine_t engine);
SAMPLEBRAIN_EXPORT sb_result_t sb_engine_stop(sb_engine_t engine);
SAMPLEBRAIN_EXPORT sb_result_t sb_engine_close(sb_engine_t engine);

// Engine config accessors
SAMPLEBRAIN_EXPORT uint32_t sb_engine_get_sample_rate(sb_engine_t engine);
SAMPLEBRAIN_EXPORT uint32_t sb_engine_get_buffer_frames(sb_engine_t engine);
SAMPLEBRAIN_EXPORT uint32_t sb_engine_get_output_channels(sb_engine_t engine);
SAMPLEBRAIN_EXPORT uint32_t sb_engine_get_input_channels(sb_engine_t engine);

// Engine state accessors
SAMPLEBRAIN_EXPORT sb_frame_t sb_engine_get_frame(sb_engine_t engine);

// #324 Test API: Offline KeyLockVoice processing for tests
typedef struct {
    int sample_rate;
    int channels;
    int sync_mode;
    float source_bpm;
    float master_bpm;
    float frequency_hz;
    float amplitude;
} sb_test_keylock_config_t;

// Process audio through KeyLockVoice offline (not real-time)
// Returns frames actually written to output
SAMPLEBRAIN_EXPORT int sb_test_keylock_process(
    const sb_test_keylock_config_t* config,
    const float* input_buffer,
    size_t input_frames,
    float* output_buffer,
    size_t output_frames
);

// Get latency values from a KeyLockVoice with given config
SAMPLEBRAIN_EXPORT int sb_test_keylock_get_latency(
    const sb_test_keylock_config_t* config,
    int* input_latency_frames,
    int* output_latency_frames,
    int* grid_compensation_frames
);

// Voice lifecycle
SAMPLEBRAIN_EXPORT sb_result_t sb_voice_create(sb_engine_t engine, const sb_voice_config_t* config, sb_voice_id_t* out_id);
SAMPLEBRAIN_EXPORT sb_result_t sb_voice_remove(sb_engine_t engine, sb_voice_id_t id);
SAMPLEBRAIN_EXPORT sb_result_t sb_voice_schedule_start(sb_engine_t engine, sb_voice_id_t id, sb_frame_t engine_frame);
SAMPLEBRAIN_EXPORT sb_result_t sb_voice_stop(sb_engine_t engine, sb_voice_id_t id);
SAMPLEBRAIN_EXPORT sb_result_t sb_voice_set_rate(sb_engine_t engine, sb_voice_id_t id, float rate);
SAMPLEBRAIN_EXPORT sb_result_t sb_voice_set_sync_mode(sb_engine_t engine, sb_voice_id_t id, int mode);
SAMPLEBRAIN_EXPORT sb_result_t sb_voice_set_source_bpm(sb_engine_t engine, sb_voice_id_t id, float bpm);
SAMPLEBRAIN_EXPORT sb_result_t sb_voice_set_master_bpm(sb_engine_t engine, sb_voice_id_t id, float bpm);

// Recording
SAMPLEBRAIN_EXPORT sb_result_t sb_recording_start(sb_engine_t engine, sb_recording_id_t* out_id, sb_frame_t engine_frame);
SAMPLEBRAIN_EXPORT sb_result_t sb_recording_stop(sb_engine_t engine, sb_recording_id_t id, float** out_buffer, size_t* out_frames);
SAMPLEBRAIN_EXPORT void sb_recording_free_buffer(float* buffer);

// Snapshot / Metrics
SAMPLEBRAIN_EXPORT sb_result_t sb_engine_snapshot(sb_engine_t engine, sb_snapshot_t* out_snapshot);

#ifdef __cplusplus
}
#endif

#endif // SAMPLEBRAIN_AUDIO_H
