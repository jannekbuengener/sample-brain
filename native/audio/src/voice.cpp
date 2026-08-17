// voice.cpp - Voice implementation
#include "voice.h"
#include "keylock_voice.h"
#include <cmath>
#include <algorithm>

namespace {
constexpr double kPi = 3.141592653589793238462643383279502884;
}

// KeyLockVoiceImpl implementation
class Voice::KeyLockVoiceImpl {
public:
    samplebrain::KeyLockVoice kv;
    std::vector<float> source_buffer;
    bool initialized = false;
    bool active = false;
};

Voice::Voice(uint32_t sample_rate_, const sb_voice_config_t& config)
    : id(config.id), rate(config.initial_rate), gain(config.gain), sample_rate(sample_rate_) {
    if (config.source.type == SB_SOURCE_SYNTHETIC_CLICK) {
        click_config = config.source.synthetic_click;
        generate_click_samples(config.source.synthetic_click);
    }

    // #324: Initialize sync mode and BPM
    sync_mode = config.sync_mode;
    source_bpm = config.source_bpm;
    master_bpm = config.master_bpm;
}

Voice::~Voice() {
    if (kl_voice) {
        delete kl_voice;
    }
}

void Voice::generate_click_samples(const sb_synthetic_click_config_t& config) {
    // Calculate click interval in frames.
    double interval_sec = 60.0 / config.bpm;
    click_interval_frames = interval_sec * sample_rate;

    // Generate click waveform.
    size_t click_samples_count = static_cast<size_t>(config.duration_ms / 1000.0 * sample_rate);
    click_samples_count = std::max<size_t>(1, click_samples_count);
    click_length = click_samples_count;

    click_samples.resize(click_length);
    for (size_t i = 0; i < click_length; ++i) {
        double t = static_cast<double>(i) / sample_rate;
        double envelope = 1.0 - t / (config.duration_ms / 1000.0);
        envelope = std::max(0.0, envelope * envelope);  // Quadratic decay
        click_samples[i] = config.amplitude * std::sin(2.0 * kPi * config.frequency_hz * t) * envelope;
    }
}

void Voice::schedule_start(sb_frame_t frame, sb_frame_t current_engine_frame) {
    requested_start_frame = frame;
    if (frame < current_engine_frame) {
        // Already past - start at the current authoritative engine frame.
        scheduled_frame = current_engine_frame;
        state.store(SB_VOICE_PLAYING, std::memory_order_release);
        actual_start_frame = current_engine_frame;
        next_click_frame = current_engine_frame + static_cast<sb_frame_t>(click_interval_frames);
    } else {
        scheduled_frame = frame;
        state.store(SB_VOICE_SCHEDULED, std::memory_order_release);
        next_click_frame = frame + static_cast<sb_frame_t>(click_interval_frames);
    }
}

void Voice::stop() {
    state.store(SB_VOICE_STOPPING, std::memory_order_release);
    // Will transition to IDLE in process().
}

void Voice::set_rate(float new_rate) {
    rate = new_rate;
    // Recalculate click interval with new rate.
    if (click_interval_frames > 0) {
        click_interval_frames = click_interval_frames * (1.0 / rate);
    }
}

void Voice::process(float* output, size_t num_frames, sb_frame_t engine_frame, size_t output_channels) {
    sb_voice_state_t current_state = state.load(std::memory_order_acquire);

    if (current_state == SB_VOICE_SCHEDULED) {
        const sb_frame_t buffer_end = engine_frame + static_cast<sb_frame_t>(num_frames);
        if (scheduled_frame < buffer_end) {
            // The logical start may fall inside this callback buffer. Preserve the
            // requested sample frame instead of snapping the event to the buffer edge.
            state.store(SB_VOICE_PLAYING, std::memory_order_release);
            actual_start_frame = scheduled_frame;
            current_state = SB_VOICE_PLAYING;
        }
    }

    if (current_state != SB_VOICE_PLAYING) {
        if (current_state == SB_VOICE_STOPPING) {
            state.store(SB_VOICE_IDLE, std::memory_order_release);
        }
        // Clear output
        std::fill(output, output + num_frames * output_channels, 0.0f);
        return;
    }

    // Process based on sync mode
    if (sync_mode == 1) {  // KEY_LOCK_SYNC
        // Use KeyLockVoice for Signalsmith time-stretch
        if (!kl_voice) {
            kl_voice = new KeyLockVoiceImpl();
        }
        if (!kl_voice->initialized) {
            samplebrain::KeyLockVoiceConfig kv_config;
            kv_config.sample_rate = sample_rate;
            kv_config.channels = 1;
            kv_config.source_bpm = source_bpm;
            kv_config.master_bpm = master_bpm;
            kv_config.sync_mode = samplebrain::SyncMode::KEY_LOCK_SYNC;
            kv_config.signalsmith_available = true;

            if (kl_voice->kv.init(kv_config)) {
                // Generate source buffer with click samples
                double ratio = master_bpm / source_bpm;
                size_t source_frames = static_cast<size_t>(num_frames * ratio * 2);

                kl_voice->source_buffer.resize(source_frames);
                double interval_sec = 60.0 / source_bpm;
                size_t click_interval = static_cast<size_t>(interval_sec * kv_config.sample_rate);

                float freq = click_config.frequency_hz;
                float dur_ms = click_config.duration_ms;
                float amp = click_config.amplitude;
                size_t click_samples_count = static_cast<size_t>(dur_ms / 1000.0 * kv_config.sample_rate);

                std::vector<float> click_waveform(click_samples_count);
                for (size_t i = 0; i < click_samples_count; ++i) {
                    double t = static_cast<double>(i) / kv_config.sample_rate;
                    double envelope = 1.0 - t / (dur_ms / 1000.0);
                    envelope = std::max(0.0, envelope * envelope);
                    click_waveform[i] = amp * std::sin(2.0 * kPi * freq * t) * envelope;
                }

                for (size_t frame = 0; frame < source_frames; frame += click_interval) {
                    for (size_t i = 0; i < click_samples_count && (frame + i) < source_frames; ++i) {
                        kl_voice->source_buffer[frame + i] += click_waveform[i];
                    }
                }

                kl_voice->kv.set_pcm_source(kl_voice->source_buffer.data(), source_frames, 1);
                kl_voice->initialized = true;
                kl_voice->active = true;
                kl_voice->kv.schedule_start(0);
            }
        }
        if (kl_voice->active) {
            kl_voice->kv.process(output, num_frames, output_channels);
        } else {
            std::fill(output, output + num_frames * output_channels, 0.0f);
        }
    } else {
        // Render clicks for this buffer
        render_click(output, 0, num_frames, engine_frame, output_channels);
    }
}

bool Voice::is_key_lock_active() const {
    return kl_voice && kl_voice->kv.is_key_lock_active();
}

int Voice::get_input_latency_frames() const {
    return kl_voice ? kl_voice->kv.get_input_latency_frames() : 0;
}

int Voice::get_output_latency_frames() const {
    return kl_voice ? kl_voice->kv.get_output_latency_frames() : 0;
}

int Voice::get_grid_compensation_frames() const {
    return kl_voice ? kl_voice->kv.get_effective_grid_compensation_frames() : 0;
}

void Voice::render_click(float* output, size_t offset, size_t num_frames,
                         sb_frame_t engine_frame, size_t output_channels) {
    if (click_samples.empty() || click_interval_frames <= 0) return;

    // Find all clicks that fall within this buffer.
    sb_frame_t frame = next_click_frame;
    while (frame < engine_frame + static_cast<sb_frame_t>(num_frames)) {
        if (frame >= engine_frame) {
            size_t pos = offset + static_cast<size_t>(frame - engine_frame);
            if (pos < num_frames) {
                // Mix click into all output channels.
                for (size_t ch = 0; ch < output_channels; ++ch) {
                    for (size_t i = 0; i < click_length && (pos + i) < num_frames; ++i) {
                        output[(pos + i) * output_channels + ch] += gain * click_samples[i];
                    }
                }
            }
        }
        frame += static_cast<sb_frame_t>(click_interval_frames);
    }

    // Update next_click_frame for next buffer.
    next_click_frame = frame;
}
