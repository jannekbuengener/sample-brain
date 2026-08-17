// engine.cpp - Core engine implementation
#include "samplebrain_audio.h"
#include "voice.h"
#include "ringbuffer.h"
#include "scheduler.h"
#include "metrics.h"
#include "synthetic.h"

#include "keylock_voice.h"
#define MINIAUDIO_IMPLEMENTATION
#include "miniaudio.h"

#include <atomic>
#include <mutex>
#include <condition_variable>
#include <thread>
#include <vector>
#include <cstring>
#include <cmath>
#include <algorithm>
#include <cctype>
#include <cstdio>

// Hex encode/decode for ma_device_id
static void device_id_to_hex(const ma_device_id* id, char* out_hex, size_t out_len) {
    const uint8_t* bytes = reinterpret_cast<const uint8_t*>(id);
    size_t id_size = sizeof(ma_device_id);
    size_t i = 0, j = 0;
    for (i = 0; i < id_size && j + 2 < out_len; ++i) {
        int hi = (bytes[i] >> 4) & 0xF;
        int lo = bytes[i] & 0xF;
        out_hex[j++] = (hi < 10) ? '0' + hi : 'a' + hi - 10;
        out_hex[j++] = (lo < 10) ? '0' + lo : 'a' + lo - 10;
    }
    out_hex[j] = '\0';
}

static int hex_char_to_val(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

static int hex_to_device_id(const char* hex, ma_device_id* out_id) {
    if (!hex || !out_id) return 0;
    size_t id_size = sizeof(ma_device_id);
    size_t hex_len = strlen(hex);
    if (hex_len != id_size * 2) return 0;
    uint8_t* bytes = reinterpret_cast<uint8_t*>(out_id);
    for (size_t i = 0; i < id_size; ++i) {
        int hi = hex_char_to_val(hex[i * 2]);
        int lo = hex_char_to_val(hex[i * 2 + 1]);
        if (hi < 0 || lo < 0) return 0;
        bytes[i] = static_cast<uint8_t>((hi << 4) | lo);
    }
    return 1;
}

// Engine version
SAMPLEBRAIN_EXPORT sb_result_t sb_engine_version(char* out, size_t len) {
    if (!out || len == 0) return SB_ERR_INVALID_ARG;
    const char* version_str = "git:" SB_GIT_SHA " time:" SB_BUILD_TIMESTAMP;
    size_t needed = strlen(version_str) + 1;
    if (len < needed) return SB_ERR_BUFFER_TOO_SMALL;
    memcpy(out, version_str, needed);
    return SB_OK;
}

// Device enumeration
SAMPLEBRAIN_EXPORT sb_result_t sb_enumerate_devices(int capture, sb_device_info_t* out_list, uint32_t max_count, uint32_t* out_count) {
    if (!out_list || !out_count || max_count == 0) return SB_ERR_INVALID_ARG;

    ma_context context;
    ma_context_config ctx_config = ma_context_config_init();
    ma_result ma_res = ma_context_init(nullptr, 0, &ctx_config, &context);
    if (ma_res != MA_SUCCESS) return SB_ERR_DEVICE_ERROR;

    ma_device_info* pPlaybackInfos = nullptr;
    ma_device_info* pCaptureInfos = nullptr;
    ma_uint32 playbackCount = 0;
    ma_uint32 captureCount = 0;

    ma_res = ma_context_get_devices(&context, &pPlaybackInfos, &playbackCount, &pCaptureInfos, &captureCount);
    if (ma_res != MA_SUCCESS) {
        ma_context_uninit(&context);
        return SB_ERR_DEVICE_ERROR;
    }

    uint32_t count = 0;
    if (capture) {
        for (ma_uint32 i = 0; i < captureCount && count < max_count; ++i) {
            ma_device_info* info = &pCaptureInfos[i];
            strncpy(out_list[count].name, info->name, sizeof(out_list[count].name) - 1);
            out_list[count].name[sizeof(out_list[count].name) - 1] = '\0';
            device_id_to_hex(&info->id, out_list[count].id_hex, sizeof(out_list[count].id_hex));
            out_list[count].is_default = info->isDefault ? 1 : 0;
            count++;
        }
    } else {
        for (ma_uint32 i = 0; i < playbackCount && count < max_count; ++i) {
            ma_device_info* info = &pPlaybackInfos[i];
            strncpy(out_list[count].name, info->name, sizeof(out_list[count].name) - 1);
            out_list[count].name[sizeof(out_list[count].name) - 1] = '\0';
            device_id_to_hex(&info->id, out_list[count].id_hex, sizeof(out_list[count].id_hex));
            out_list[count].is_default = info->isDefault ? 1 : 0;
            count++;
        }
    }

    *out_count = count;

    // Free device info arrays
    if (pPlaybackInfos) free(pPlaybackInfos);
    if (pCaptureInfos) free(pCaptureInfos);
    ma_context_uninit(&context);

    return SB_OK;
}

// Internal engine structure
struct sb_engine {
    // Configuration
    sb_engine_config_t config;
    ma_device device;
    ma_context context;

    // State
    std::atomic<bool> running{false};
    std::atomic<bool> stopping{false};
    std::atomic<sb_device_status_t> device_status{SB_DEVICE_OK};
    std::atomic<uint32_t> recovery_state{0};

    // Clock
    std::atomic<sb_frame_t> engine_frame{0};

    // Voice management
    std::mutex voices_mutex;
    std::vector<Voice*> voices;

    // Recording management. Recording allocation/finalization intentionally
    // happens on the control thread, never in the audio callback.
    std::mutex recordings_mutex;
    std::vector<Recording*> recordings;
    std::atomic<sb_recording_id_t> next_recording_id{1};

    // Command queue for realtime-safe voice control
    struct Command {
        enum Type {
            CMD_NONE,
            CMD_CREATE_VOICE,
            CMD_REMOVE_VOICE,
            CMD_SCHEDULE_START,
            CMD_STOP_VOICE,
            CMD_SET_RATE,
            CMD_SET_SYNC_MODE,
            CMD_SET_SOURCE_BPM,
            CMD_SET_MASTER_BPM
        } type;

        union {
            struct { sb_voice_config_t config; sb_voice_id_t* out_id; } create_voice;
            struct { sb_voice_id_t id; } remove_voice;
            struct { sb_voice_id_t id; sb_frame_t frame; } schedule_start;
            struct { sb_voice_id_t id; } stop_voice;
            struct { sb_voice_id_t id; float rate; } set_rate;
            struct { sb_voice_id_t id; int mode; } set_sync_mode;
            struct { sb_voice_id_t id; float bpm; } set_source_bpm;
            struct { sb_voice_id_t id; float bpm; } set_master_bpm;
        };
        std::atomic<sb_result_t>* result_ptr;
    };

    static constexpr size_t COMMAND_QUEUE_SIZE = 256;
    std::atomic<size_t> cmd_head{0};
    std::atomic<size_t> cmd_tail{0};
    Command cmd_queue[COMMAND_QUEUE_SIZE];

    // Metrics
    MetricsCollector metrics;

    // Callbacks
    void (*data_callback)(ma_device*, void*, const void*, ma_uint32);
};

// Miniaudio notification callback (defined after sb_engine struct for member access)
static void ma_on_notification(const ma_device_notification* pNotification) {
    if (!pNotification || !pNotification->pDevice) return;
    sb_engine_t engine = static_cast<sb_engine_t>(pNotification->pDevice->pUserData);
    if (!engine) return;

    switch (pNotification->type) {
        case ma_device_notification_type_rerouted:
        case ma_device_notification_type_stopped:
            engine->device_status.store(SB_DEVICE_LOST, std::memory_order_relaxed);
            engine->recovery_state.store(1, std::memory_order_relaxed);
            break;
        case ma_device_notification_type_started:
            if (engine->device_status.load(std::memory_order_relaxed) == SB_DEVICE_LOST) {
                engine->device_status.store(SB_DEVICE_RECOVERING, std::memory_order_relaxed);
                engine->recovery_state.store(2, std::memory_order_relaxed);
            }
            break;
        default:
            break;
    }
}

// Forward declarations
static void ma_data_callback(ma_device* pDevice, void* pOutput, const void* pInput, ma_uint32 frameCount);
static sb_result_t process_commands(sb_engine_t engine);
static Voice* find_voice(sb_engine_t engine, sb_voice_id_t id);
static sb_result_t enqueue_command(sb_engine_t engine, const sb_engine::Command& cmd);

sb_result_t sb_engine_open(const sb_engine_config_t* config, sb_engine_t* out_engine) {
    if (!config || !out_engine) return SB_ERR_INVALID_ARG;
    if (config->sample_rate == 0 || config->buffer_frames == 0) return SB_ERR_INVALID_ARG;
    if (config->output_channels == 0 || config->output_channels > 8) return SB_ERR_INVALID_ARG;
    if (config->input_channels > 8) return SB_ERR_INVALID_ARG;

    // Allocate engine
    sb_engine_t engine = new (std::nothrow) sb_engine();
    if (!engine) return SB_ERR_OUT_OF_MEMORY;

    // Copy config
    engine->config = *config;
    engine->config.output_device = config->output_device ? strdup(config->output_device) : nullptr;
    engine->config.input_device = config->input_device ? strdup(config->input_device) : nullptr;

    // Initialize miniaudio context. Native CTest uses miniaudio's null backend so
    // transport/voice logic can be exercised on hosted runners without changing
    // production WASAPI/device behavior.
    ma_context_config ctx_config = ma_context_config_init();
#ifdef SAMPLEBRAIN_AUDIO_TEST_NULL_BACKEND
    ma_backend test_backends[] = {ma_backend_null};
    ma_result ma_res = ma_context_init(test_backends, 1, &ctx_config, &engine->context);
#else
    ma_result ma_res = ma_context_init(nullptr, 0, &ctx_config, &engine->context);
#endif
    if (ma_res != MA_SUCCESS) {
        delete engine;
        return SB_ERR_DEVICE_ERROR;
    }

    // Configure device
    ma_device_config dev_config = ma_device_config_init(ma_device_type_duplex);
    dev_config.sampleRate = config->sample_rate;
    dev_config.periodSizeInFrames = config->buffer_frames;
    dev_config.periods = 3;  // Triple buffering for safety
    dev_config.playback.format = ma_format_f32;
    dev_config.playback.channels = config->output_channels;
    dev_config.capture.format = ma_format_f32;
    dev_config.capture.channels = config->input_channels;
    dev_config.dataCallback = ma_data_callback;
    dev_config.pUserData = engine;
    dev_config.notificationCallback = ma_on_notification;

    // Apply output device ID if provided
    if (config->output_device) {
        ma_device_id device_id;
        if (hex_to_device_id(config->output_device, &device_id)) {
            dev_config.playback.pDeviceID = &device_id;
        }
    }

    // Apply input device ID if provided
    if (config->input_device) {
        ma_device_id device_id;
        if (hex_to_device_id(config->input_device, &device_id)) {
            dev_config.capture.pDeviceID = &device_id;
        }
    }

    ma_res = ma_device_init(&engine->context, &dev_config, &engine->device);
    if (ma_res != MA_SUCCESS) {
        ma_context_uninit(&engine->context);
        delete engine;
        return SB_ERR_DEVICE_ERROR;
    }

    *out_engine = engine;
    return SB_OK;
}

sb_result_t sb_engine_start(sb_engine_t engine) {
    if (!engine) return SB_ERR_NOT_INITIALIZED;
    if (engine->running.load()) return SB_ERR_ALREADY_RUNNING;

    ma_result res = ma_device_start(&engine->device);
    if (res != MA_SUCCESS) {
        return SB_ERR_DEVICE_ERROR;
    }

    engine->running.store(true);
    engine->stopping.store(false);
    engine->engine_frame.store(0);
    engine->metrics.reset();

    return SB_OK;
}

sb_result_t sb_engine_stop(sb_engine_t engine) {
    if (!engine) return SB_ERR_NOT_INITIALIZED;
    if (!engine->running.load()) return SB_ERR_INVALID_STATE;

    engine->stopping.store(true);

    // Wait for audio callback to finish
    ma_device_stop(&engine->device);

    engine->running.store(false);
    return SB_OK;
}

sb_result_t sb_engine_close(sb_engine_t engine) {
    if (!engine) return SB_ERR_NOT_INITIALIZED;
    if (engine->running.load()) return SB_ERR_INVALID_STATE;

    // Clean up voices
    {
        std::lock_guard<std::mutex> lock(engine->voices_mutex);
        for (auto* v : engine->voices) {
            delete v;
        }
        engine->voices.clear();
    }

    // Clean up recordings
    {
        std::lock_guard<std::mutex> lock(engine->recordings_mutex);
        for (auto* r : engine->recordings) {
            delete r;
        }
        engine->recordings.clear();
    }

    // Free device strings
    free((void*)engine->config.output_device);
    free((void*)engine->config.input_device);

    // Uninit miniaudio
    ma_device_uninit(&engine->device);
    ma_context_uninit(&engine->context);

    delete engine;
    return SB_OK;
}

// Engine config accessors
uint32_t sb_engine_get_sample_rate(sb_engine_t engine) {
    return engine->config.sample_rate;
}

uint32_t sb_engine_get_buffer_frames(sb_engine_t engine) {
    return engine->config.buffer_frames;
}

uint32_t sb_engine_get_output_channels(sb_engine_t engine) {
    return engine->config.output_channels;
}

uint32_t sb_engine_get_input_channels(sb_engine_t engine) {
    return engine->config.input_channels;
}

sb_frame_t sb_engine_get_frame(sb_engine_t engine) {
    return engine->engine_frame.load(std::memory_order_relaxed);
}

sb_result_t sb_voice_create(sb_engine_t engine, const sb_voice_config_t* config, sb_voice_id_t* out_id) {
    if (!engine || !config || !out_id) return SB_ERR_INVALID_ARG;

    // Check for duplicate ID
    {
        std::lock_guard<std::mutex> lock(engine->voices_mutex);
        for (auto* v : engine->voices) {
            if (v->id == config->id) return SB_ERR_INVALID_ARG;
        }
    }

    // Create voice outside the audio callback.
    Voice* voice = new (std::nothrow) Voice(engine->config.sample_rate, *config);
    if (!voice) return SB_ERR_OUT_OF_MEMORY;

    {
        std::lock_guard<std::mutex> lock(engine->voices_mutex);
        engine->voices.push_back(voice);
    }

    *out_id = config->id;
    return SB_OK;
}

sb_result_t sb_voice_remove(sb_engine_t engine, sb_voice_id_t id) {
    if (!engine) return SB_ERR_NOT_INITIALIZED;

    std::lock_guard<std::mutex> lock(engine->voices_mutex);
    auto it = std::find_if(engine->voices.begin(), engine->voices.end(),
                           [id](Voice* v) { return v->id == id; });
    if (it == engine->voices.end()) return SB_ERR_VOICE_NOT_FOUND;

    (*it)->stop();
    delete *it;
    engine->voices.erase(it);
    return SB_OK;
}

sb_result_t sb_voice_schedule_start(sb_engine_t engine, sb_voice_id_t id, sb_frame_t engine_frame) {
    if (!engine) return SB_ERR_NOT_INITIALIZED;
    if (engine_frame < engine->engine_frame.load(std::memory_order_acquire)) {
        return SB_ERR_INVALID_ARG;
    }
    {
        std::lock_guard<std::mutex> lock(engine->voices_mutex);
        auto it = std::find_if(engine->voices.begin(), engine->voices.end(),
                               [id](Voice* v) { return v->id == id; });
        if (it == engine->voices.end()) return SB_ERR_VOICE_NOT_FOUND;
    }

    sb_engine::Command cmd{};
    cmd.type = sb_engine::Command::CMD_SCHEDULE_START;
    cmd.schedule_start.id = id;
    cmd.schedule_start.frame = engine_frame;

    return enqueue_command(engine, cmd);
}

sb_result_t sb_voice_stop(sb_engine_t engine, sb_voice_id_t id) {
    if (!engine) return SB_ERR_NOT_INITIALIZED;

    sb_engine::Command cmd{};
    cmd.type = sb_engine::Command::CMD_STOP_VOICE;
    cmd.stop_voice.id = id;

    return enqueue_command(engine, cmd);
}

sb_result_t sb_voice_set_rate(sb_engine_t engine, sb_voice_id_t id, float rate) {
    if (!engine) return SB_ERR_NOT_INITIALIZED;
    if (rate <= 0.0f || rate > 10.0f) return SB_ERR_INVALID_ARG;

    sb_engine::Command cmd{};
    cmd.type = sb_engine::Command::CMD_SET_RATE;
    cmd.set_rate.id = id;
    cmd.set_rate.rate = rate;

    return enqueue_command(engine, cmd);
}

SAMPLEBRAIN_EXPORT sb_result_t sb_voice_set_sync_mode(sb_engine_t engine, sb_voice_id_t id, int mode) {
    if (!engine) return SB_ERR_NOT_INITIALIZED;

    sb_engine::Command cmd{};
    cmd.type = sb_engine::Command::CMD_SET_SYNC_MODE;
    cmd.set_sync_mode.id = id;
    cmd.set_sync_mode.mode = mode;

    return enqueue_command(engine, cmd);
}

SAMPLEBRAIN_EXPORT sb_result_t sb_voice_set_source_bpm(sb_engine_t engine, sb_voice_id_t id, float bpm) {
    if (!engine) return SB_ERR_NOT_INITIALIZED;
    if (bpm <= 0.0f) return SB_ERR_INVALID_ARG;

    sb_engine::Command cmd{};
    cmd.type = sb_engine::Command::CMD_SET_SOURCE_BPM;
    cmd.set_source_bpm.id = id;
    cmd.set_source_bpm.bpm = bpm;

    return enqueue_command(engine, cmd);
}

SAMPLEBRAIN_EXPORT sb_result_t sb_voice_set_master_bpm(sb_engine_t engine, sb_voice_id_t id, float bpm) {
    if (!engine) return SB_ERR_NOT_INITIALIZED;
    if (bpm <= 0.0f) return SB_ERR_INVALID_ARG;

    sb_engine::Command cmd{};
    cmd.type = sb_engine::Command::CMD_SET_MASTER_BPM;
    cmd.set_master_bpm.id = id;
    cmd.set_master_bpm.bpm = bpm;

    return enqueue_command(engine, cmd);
}

sb_result_t sb_recording_start(sb_engine_t engine, sb_recording_id_t* out_id, sb_frame_t engine_frame) {
    if (!engine || !out_id) return SB_ERR_INVALID_ARG;
    if (engine->config.input_channels == 0) return SB_ERR_UNSUPPORTED;

    const sb_frame_t current_frame = engine->engine_frame.load(std::memory_order_acquire);
    const sb_frame_t effective_start = engine_frame == 0 ? current_frame : engine_frame;
    if (effective_start < current_frame) return SB_ERR_INVALID_ARG;

    Recording* recording = new (std::nothrow) Recording(
        engine->config.sample_rate,
        engine->config.input_channels,
        effective_start);
    if (!recording) return SB_ERR_OUT_OF_MEMORY;

    sb_recording_id_t id = 0;
    {
        std::lock_guard<std::mutex> lock(engine->recordings_mutex);
        if (engine->recordings.size() >= SB_MAX_RECORDINGS) {
            delete recording;
            return SB_ERR_OUT_OF_MEMORY;
        }
        id = engine->next_recording_id.fetch_add(1, std::memory_order_relaxed);
        recording->id = id;
        engine->recordings.push_back(recording);
    }

    *out_id = id;
    return SB_OK;
}

sb_result_t sb_recording_stop(sb_engine_t engine, sb_recording_id_t id, float** out_buffer, size_t* out_frames) {
    if (!engine || !out_buffer || !out_frames) return SB_ERR_INVALID_ARG;

    *out_buffer = nullptr;
    *out_frames = 0;

    Recording* recording = nullptr;
    {
        std::lock_guard<std::mutex> lock(engine->recordings_mutex);
        auto it = std::find_if(engine->recordings.begin(), engine->recordings.end(),
                               [id](Recording* r) { return r->id == id; });
        if (it == engine->recordings.end()) return SB_ERR_RECORDING_NOT_FOUND;
        recording = *it;
        engine->recordings.erase(it);
    }

    // Finalization allocates/copies outside the realtime callback by contract.
    recording->finalize(out_buffer, out_frames);
    delete recording;
    return SB_OK;
}

void sb_recording_free_buffer(float* buffer) {
    delete[] buffer;
}

sb_result_t sb_engine_snapshot(sb_engine_t engine, sb_snapshot_t* out_snapshot) {
    if (!engine || !out_snapshot) return SB_ERR_INVALID_ARG;

    // Fill snapshot atomically/lock-free where possible
    out_snapshot->engine_frame = engine->engine_frame.load(std::memory_order_relaxed);
    out_snapshot->running = engine->running.load(std::memory_order_relaxed);
    out_snapshot->sample_rate = engine->config.sample_rate;
    out_snapshot->buffer_frames = engine->config.buffer_frames;
    out_snapshot->device_status = engine->device_status.load(std::memory_order_relaxed);
    out_snapshot->recovery_state = engine->recovery_state.load(std::memory_order_relaxed);

    // Voice snapshot
    {
        std::lock_guard<std::mutex> lock(engine->voices_mutex);
        out_snapshot->total_voice_count = static_cast<uint32_t>(engine->voices.size());
        out_snapshot->active_voice_count = 0;

        for (size_t i = 0; i < engine->voices.size() && i < SB_MAX_VOICES; ++i) {
            Voice* v = engine->voices[i];
            out_snapshot->voice_ids[i] = v->id;
            out_snapshot->voice_states[i] = v->get_state();
            out_snapshot->requested_start_frame[i] = v->requested_start_frame;
            out_snapshot->actual_start_frame[i] = v->actual_start_frame;
            out_snapshot->start_skew_frames[i] = v->actual_start_frame - v->requested_start_frame;
            out_snapshot->voice_rates[i] = v->rate;
            out_snapshot->voice_gains[i] = v->gain;
            out_snapshot->voice_sync_modes[i] = v->sync_mode;
            out_snapshot->voice_key_lock_active[i] = v->is_key_lock_active();
            out_snapshot->voice_input_latency_frames[i] = v->get_input_latency_frames();
            out_snapshot->voice_output_latency_frames[i] = v->get_output_latency_frames();
            out_snapshot->voice_grid_compensation_frames[i] = v->get_grid_compensation_frames();
            if (v->get_state() == SB_VOICE_PLAYING) {
                out_snapshot->active_voice_count++;
            }
        }
        // Clear remaining slots
        for (size_t i = engine->voices.size(); i < SB_MAX_VOICES; ++i) {
            out_snapshot->voice_ids[i] = 0;
            out_snapshot->voice_states[i] = SB_VOICE_IDLE;
            out_snapshot->requested_start_frame[i] = 0;
            out_snapshot->actual_start_frame[i] = 0;
            out_snapshot->start_skew_frames[i] = 0;
            out_snapshot->voice_rates[i] = 1.0f;
            out_snapshot->voice_gains[i] = 1.0f;
            out_snapshot->voice_sync_modes[i] = 0;
            out_snapshot->voice_key_lock_active[i] = false;
            out_snapshot->voice_input_latency_frames[i] = 0;
            out_snapshot->voice_output_latency_frames[i] = 0;
            out_snapshot->voice_grid_compensation_frames[i] = 0;
        }
    }

    // Recording snapshot
    {
        std::lock_guard<std::mutex> lock(engine->recordings_mutex);
        out_snapshot->recording_active = false;
        out_snapshot->recording_dropped_frames = 0;
        for (auto* r : engine->recordings) {
            if (r->is_active()) {
                out_snapshot->recording_active = true;
                out_snapshot->recording_dropped_frames += r->dropped_frames();
            }
        }
    }

    // Metrics snapshot
    engine->metrics.get_snapshot(
        out_snapshot->callback_mean_us,
        out_snapshot->callback_p95_us,
        out_snapshot->callback_p99_us,
        out_snapshot->callback_max_us,
        out_snapshot->callback_p99_9_us,
        out_snapshot->underflow_count,
        out_snapshot->overflow_count,
        out_snapshot->xrun_count
    );

    return SB_OK;
}

// Internal: miniaudio data callback
static void ma_data_callback(ma_device* pDevice, void* pOutput, const void* pInput, ma_uint32 frameCount) {
    sb_engine_t engine = static_cast<sb_engine_t>(pDevice->pUserData);
    if (!engine) {
        return;
    }
    if (!engine->running.load()) {
        if (pOutput) memset(pOutput, 0, frameCount * engine->config.output_channels * sizeof(float));
        return;
    }

    engine->metrics.on_callback_start();

    // Process pending voice-control commands.
    process_commands(engine);

    // Get current frame before processing
    sb_frame_t current_frame = engine->engine_frame.load(std::memory_order_relaxed);
    engine->engine_frame.store(current_frame + frameCount, std::memory_order_relaxed);

    // Process voices (mix to output)
    float* output = static_cast<float*>(pOutput);
    const size_t num_channels = engine->config.output_channels;
    const size_t num_frames = frameCount;

    if (output) {
        std::fill(output, output + num_frames * num_channels, 0.0f);

        std::lock_guard<std::mutex> lock(engine->voices_mutex);
        for (auto* v : engine->voices) {
            v->process(output, num_frames, current_frame, num_channels);
        }
    }

    // Process recording (capture input). Scheduled recordings are called every
    // callback; Recording::write applies the exact start-frame offset itself.
    if (pInput && engine->config.input_channels > 0) {
        const float* input = static_cast<const float*>(pInput);
        std::lock_guard<std::mutex> lock(engine->recordings_mutex);
        for (auto* r : engine->recordings) {
            r->write(input, num_frames, engine->config.input_channels, current_frame);
        }
    }

    // Update metrics
    engine->metrics.on_callback_end();
}

static sb_result_t process_commands(sb_engine_t engine) {
    size_t tail = engine->cmd_tail.load(std::memory_order_acquire);
    size_t head = engine->cmd_head.load(std::memory_order_relaxed);

    while (tail != head) {
        sb_engine::Command& cmd = engine->cmd_queue[tail];
        sb_result_t result = SB_OK;

        switch (cmd.type) {
            case sb_engine::Command::CMD_CREATE_VOICE: {
                Voice* voice = new (std::nothrow) Voice(engine->config.sample_rate, cmd.create_voice.config);
                if (voice) {
                    std::lock_guard<std::mutex> lock(engine->voices_mutex);
                    engine->voices.push_back(voice);
                    *cmd.create_voice.out_id = cmd.create_voice.config.id;
                } else {
                    result = SB_ERR_OUT_OF_MEMORY;
                }
                break;
            }
            case sb_engine::Command::CMD_REMOVE_VOICE: {
                std::lock_guard<std::mutex> lock(engine->voices_mutex);
                auto it = std::find_if(engine->voices.begin(), engine->voices.end(),
                                       [&](Voice* v) { return v->id == cmd.remove_voice.id; });
                if (it != engine->voices.end()) {
                    (*it)->stop();
                    delete *it;
                    engine->voices.erase(it);
                } else {
                    result = SB_ERR_VOICE_NOT_FOUND;
                }
                break;
            }
            case sb_engine::Command::CMD_SCHEDULE_START: {
                Voice* v = find_voice(engine, cmd.schedule_start.id);
                if (v) {
                    v->schedule_start(
                        cmd.schedule_start.frame,
                        engine->engine_frame.load(std::memory_order_relaxed));
                } else {
                    result = SB_ERR_VOICE_NOT_FOUND;
                }
                break;
            }
            case sb_engine::Command::CMD_STOP_VOICE: {
                Voice* v = find_voice(engine, cmd.stop_voice.id);
                if (v) {
                    v->stop();
                } else {
                    result = SB_ERR_VOICE_NOT_FOUND;
                }
                break;
            }
            case sb_engine::Command::CMD_SET_RATE: {
                Voice* v = find_voice(engine, cmd.set_rate.id);
                if (v) {
                    v->set_rate(cmd.set_rate.rate);
                } else {
                    result = SB_ERR_VOICE_NOT_FOUND;
                }
                break;
            }
            case sb_engine::Command::CMD_SET_SYNC_MODE: {
                Voice* v = find_voice(engine, cmd.set_sync_mode.id);
                if (v) {
                    v->sync_mode = cmd.set_sync_mode.mode;
                }
                break;
            }
            case sb_engine::Command::CMD_SET_SOURCE_BPM: {
                Voice* v = find_voice(engine, cmd.set_source_bpm.id);
                if (v) {
                    v->source_bpm = cmd.set_source_bpm.bpm;
                } else {
                    result = SB_ERR_VOICE_NOT_FOUND;
                }
                break;
            }
            case sb_engine::Command::CMD_SET_MASTER_BPM: {
                Voice* v = find_voice(engine, cmd.set_master_bpm.id);
                if (v) {
                    v->master_bpm = cmd.set_master_bpm.bpm;
                } else {
                    result = SB_ERR_VOICE_NOT_FOUND;
                }
                break;
            }
            default:
                result = SB_ERR_INVALID_ARG;
        }

        if (cmd.result_ptr) {
            cmd.result_ptr->store(result, std::memory_order_release);
        }

        tail = (tail + 1) % sb_engine::COMMAND_QUEUE_SIZE;
        engine->cmd_tail.store(tail, std::memory_order_release);
    }

    return SB_OK;
}

static sb_result_t enqueue_command(sb_engine_t engine, const sb_engine::Command& cmd) {
    size_t head = engine->cmd_head.load(std::memory_order_relaxed);
    size_t next_head = (head + 1) % sb_engine::COMMAND_QUEUE_SIZE;
    size_t tail = engine->cmd_tail.load(std::memory_order_acquire);

    if (next_head == tail) {
        return SB_ERR_OUT_OF_MEMORY;  // Queue full
    }

    engine->cmd_queue[head] = cmd;
    engine->cmd_head.store(next_head, std::memory_order_release);
    return SB_OK;
}

static Voice* find_voice(sb_engine_t engine, sb_voice_id_t id) {
    std::lock_guard<std::mutex> lock(engine->voices_mutex);
    auto it = std::find_if(engine->voices.begin(), engine->voices.end(),
                           [id](Voice* v) { return v->id == id; });
    return (it != engine->voices.end()) ? *it : nullptr;
}


// =============================================================================
// #324 Test API: Offline KeyLockVoice processing
// =============================================================================

static int compute_output_frames(const sb_test_keylock_config_t* config, size_t input_frames) {
    float tempo_ratio = config->master_bpm / config->source_bpm;
    if (tempo_ratio <= 0.0f) return 0;
    // Output frames = input_frames * tempo_ratio (time-stretch)
    return static_cast<int>(static_cast<float>(input_frames) * tempo_ratio);
}

SAMPLEBRAIN_EXPORT int sb_test_keylock_process(
    const sb_test_keylock_config_t* config,
    const float* input_buffer,
    size_t input_frames,
    float* output_buffer,
    size_t output_frames
) {
    if (!config || !input_buffer || !output_buffer) return -1;
    if (config->sample_rate <= 0 || config->channels <= 0) return -1;
    if (config->source_bpm <= 0.0f || config->master_bpm <= 0.0f) return -1;

    // Create KeyLockVoice
    samplebrain::KeyLockVoice kv;
    samplebrain::KeyLockVoiceConfig kv_config;
    kv_config.sample_rate = config->sample_rate;
    kv_config.channels = config->channels;
    kv_config.source_bpm = config->source_bpm;
    kv_config.master_bpm = config->master_bpm;
    kv_config.sync_mode = (config->sync_mode == 1) ? samplebrain::SyncMode::KEY_LOCK_SYNC : samplebrain::SyncMode::RATE_SYNC;
    kv_config.frequency_hz = config->frequency_hz;
    kv_config.amplitude = config->amplitude;
    kv_config.signalsmith_available = true;

    if (!kv.init(kv_config)) return -1;

    // Set PCM source (the input buffer)
    kv.set_pcm_source(input_buffer, input_frames, config->channels);

    // Schedule to start immediately
    kv.schedule_start(0);

    // Calculate expected output frames based on tempo ratio
    // For BPM sync: when tempo increases, output should be shorter
    float tempo_ratio = config->master_bpm / config->source_bpm;
    int expected_output_frames = static_cast<int>(static_cast<float>(input_frames) / tempo_ratio);
    size_t frames_to_process = static_cast<size_t>(expected_output_frames);
    if (frames_to_process > output_frames) frames_to_process = output_frames;

    // Process output
    if (!kv.process(output_buffer, static_cast<size_t>(frames_to_process), static_cast<size_t>(config->channels))) {
        // Voice not active - clear output
        std::fill(output_buffer, output_buffer + frames_to_process * config->channels, 0.0f);
    }

    return frames_to_process;
}

SAMPLEBRAIN_EXPORT int sb_test_keylock_get_latency(
    const sb_test_keylock_config_t* config,
    int* input_latency_frames,
    int* output_latency_frames,
    int* grid_compensation_frames
) {
    if (!config || !input_latency_frames || !output_latency_frames || !grid_compensation_frames) return -1;
    if (config->sample_rate <= 0 || config->channels <= 0) return -1;
    if (config->source_bpm <= 0.0f || config->master_bpm <= 0.0f) return -1;

    // Create KeyLockVoice to query latency
    samplebrain::KeyLockVoice kv;
    samplebrain::KeyLockVoiceConfig kv_config;
    kv_config.sample_rate = config->sample_rate;
    kv_config.channels = config->channels;
    kv_config.source_bpm = config->source_bpm;
    kv_config.master_bpm = config->master_bpm;
    kv_config.sync_mode = (config->sync_mode == 1) ? samplebrain::SyncMode::KEY_LOCK_SYNC : samplebrain::SyncMode::RATE_SYNC;
    kv_config.signalsmith_available = true;

    if (!kv.init(kv_config)) return -1;

    *input_latency_frames = kv.get_input_latency_frames();
    *output_latency_frames = kv.get_output_latency_frames();
    *grid_compensation_frames = kv.get_effective_grid_compensation_frames();

    return 0;
}
