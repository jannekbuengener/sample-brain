// engine.cpp - Core engine implementation
#include "samplebrain_audio.h"
#include "voice.h"
#include "ringbuffer.h"
#include "scheduler.h"
#include "metrics.h"
#include "synthetic.h"

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

    // Recording management
    std::mutex recordings_mutex;
    std::vector<Recording*> recordings;

    // Command queue for realtime-safe control
    struct Command {
        enum Type {
            CMD_NONE,
            CMD_CREATE_VOICE,
            CMD_REMOVE_VOICE,
            CMD_SCHEDULE_START,
            CMD_STOP_VOICE,
            CMD_SET_RATE,
            CMD_START_RECORDING,
            CMD_STOP_RECORDING
        } type;

        union {
            struct { sb_voice_config_t config; sb_voice_id_t* out_id; } create_voice;
            struct { sb_voice_id_t id; } remove_voice;
            struct { sb_voice_id_t id; sb_frame_t frame; } schedule_start;
            struct { sb_voice_id_t id; } stop_voice;
            struct { sb_voice_id_t id; float rate; } set_rate;
            struct { sb_recording_id_t* out_id; sb_frame_t frame; } start_recording;
            struct { sb_recording_id_t id; float** out_buffer; size_t* out_frames; } stop_recording;
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

// Forward declarations
static void ma_data_callback(ma_device* pDevice, void* pOutput, const void* pInput, ma_uint32 frameCount);
static sb_result_t process_commands(sb_engine_t engine);
static Voice* find_voice(sb_engine_t engine, sb_voice_id_t id);
static Recording* find_recording(sb_engine_t engine, sb_recording_id_t id);
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

    // Initialize miniaudio context
    ma_context_config ctx_config = ma_context_config_init();
    ma_result ma_res = ma_context_init(nullptr, 0, &ctx_config, &engine->context);
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

    if (config->output_device) {
        ma_device_id device_id;
        // Note: miniaudio device ID handling would go here
        // For now, use default device
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

sb_result_t sb_voice_create(sb_engine_t engine, const sb_voice_config_t* config, sb_voice_id_t* out_id) {
    if (!engine || !config || !out_id) return SB_ERR_INVALID_ARG;

    // Check for duplicate ID
    {
        std::lock_guard<std::mutex> lock(engine->voices_mutex);
        for (auto* v : engine->voices) {
            if (v->id == config->id) return SB_ERR_INVALID_ARG;
        }
    }

    // Create voice
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

    // Stop if playing
    (*it)->stop();

    delete *it;
    engine->voices.erase(it);
    return SB_OK;
}

sb_result_t sb_voice_schedule_start(sb_engine_t engine, sb_voice_id_t id, sb_frame_t engine_frame) {
    if (!engine) return SB_ERR_NOT_INITIALIZED;

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

sb_result_t sb_recording_start(sb_engine_t engine, sb_recording_id_t* out_id, sb_frame_t engine_frame) {
    if (!engine || !out_id) return SB_ERR_INVALID_ARG;

    sb_engine::Command cmd{};
    cmd.type = sb_engine::Command::CMD_START_RECORDING;
    cmd.start_recording.out_id = out_id;
    cmd.start_recording.frame = engine_frame;

    return enqueue_command(engine, cmd);
}

sb_result_t sb_recording_stop(sb_engine_t engine, sb_recording_id_t id, float** out_buffer, size_t* out_frames) {
    if (!engine || !out_buffer || !out_frames) return SB_ERR_INVALID_ARG;

    sb_engine::Command cmd{};
    cmd.type = sb_engine::Command::CMD_STOP_RECORDING;
    cmd.stop_recording.id = id;
    cmd.stop_recording.out_buffer = out_buffer;
    cmd.stop_recording.out_frames = out_frames;

    return enqueue_command(engine, cmd);
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

    // Process pending commands
    process_commands(engine);

    // Get current frame before processing
    sb_frame_t current_frame = engine->engine_frame.load(std::memory_order_relaxed);
    engine->engine_frame.store(current_frame + frameCount, std::memory_order_relaxed);

    // Process voices (mix to output)
    float* output = static_cast<float*>(pOutput);
    const size_t num_channels = engine->config.output_channels;
    const size_t num_frames = frameCount;

    // Clear output
    std::fill(output, output + num_frames * num_channels, 0.0f);

    {
        std::lock_guard<std::mutex> lock(engine->voices_mutex);
        for (auto* v : engine->voices) {
            v->process(output, num_frames, current_frame, num_channels);
        }
    }

    // Process recording (capture input)
    if (pInput && engine->config.input_channels > 0) {
        const float* input = static_cast<const float*>(pInput);
        std::lock_guard<std::mutex> lock(engine->recordings_mutex);
        for (auto* r : engine->recordings) {
            if (r->is_active()) {
                r->write(input, num_frames, engine->config.input_channels);
            }
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
            case sb_engine::Command::CMD_START_RECORDING: {
                Recording* rec = new (std::nothrow) Recording(engine->config.sample_rate, engine->config.input_channels, cmd.start_recording.frame);
                if (rec) {
                    std::lock_guard<std::mutex> lock(engine->recordings_mutex);
                    sb_recording_id_t id = static_cast<sb_recording_id_t>(engine->recordings.size() + 1);
                    rec->id = id;
                    engine->recordings.push_back(rec);
                    *cmd.start_recording.out_id = id;
                } else {
                    result = SB_ERR_OUT_OF_MEMORY;
                }
                break;
            }
            case sb_engine::Command::CMD_STOP_RECORDING: {
                std::lock_guard<std::mutex> lock(engine->recordings_mutex);
                auto it = std::find_if(engine->recordings.begin(), engine->recordings.end(),
                                       [&](Recording* r) { return r->id == cmd.stop_recording.id; });
                if (it != engine->recordings.end()) {
                    (*it)->finalize(cmd.stop_recording.out_buffer, cmd.stop_recording.out_frames);
                    delete *it;
                    engine->recordings.erase(it);
                } else {
                    result = SB_ERR_RECORDING_NOT_FOUND;
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

static Recording* find_recording(sb_engine_t engine, sb_recording_id_t id) {
    std::lock_guard<std::mutex> lock(engine->recordings_mutex);
    auto it = std::find_if(engine->recordings.begin(), engine->recordings.end(),
                           [id](Recording* r) { return r->id == id; });
    return (it != engine->recordings.end()) ? *it : nullptr;
}
