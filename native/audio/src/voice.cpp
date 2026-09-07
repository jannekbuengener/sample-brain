// voice.cpp - Voice implementation
#include "voice.h"
#include "keylock_voice.h"
#include <cmath>
#include <algorithm>
#include <limits>

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

bool Voice::validate_config(const sb_voice_config_t& config) {
    if (!std::isfinite(config.initial_rate) || config.initial_rate <= 0.0f ||
        config.initial_rate > 10.0f || !std::isfinite(config.gain)) {
        return false;
    }

    if (config.source.type == SB_SOURCE_SYNTHETIC_CLICK) {
        return true;
    }
    if (config.source.type != SB_SOURCE_PCM_BUFFER) {
        return false;
    }

    const sb_pcm_buffer_config_t& pcm = config.source.pcm_buffer;
    if (!pcm.data || pcm.frame_count == 0 || (pcm.channels != 1 && pcm.channels != 2)) {
        return false;
    }
    if (pcm.frame_count > std::numeric_limits<size_t>::max() / pcm.channels) {
        return false;
    }

    const size_t sample_count = static_cast<size_t>(pcm.frame_count) * pcm.channels;
    if (sample_count > std::vector<float>().max_size()) {
        return false;
    }
    for (size_t i = 0; i < sample_count; ++i) {
        if (!std::isfinite(pcm.data[i])) {
            return false;
        }
    }
    return true;
}

Voice::Voice(uint32_t sample_rate_, const sb_voice_config_t& config)
    : id(config.id), rate(config.initial_rate), gain(config.gain), sample_rate(sample_rate_),
      source_type(config.source.type) {
    if (config.source.type == SB_SOURCE_SYNTHETIC_CLICK) {
        click_config = config.source.synthetic_click;
        generate_click_samples(config.source.synthetic_click);
    } else if (config.source.type == SB_SOURCE_PCM_BUFFER) {
        const sb_pcm_buffer_config_t& pcm = config.source.pcm_buffer;
        const size_t sample_count = static_cast<size_t>(pcm.frame_count) * pcm.channels;
        pcm_samples.assign(pcm.data, pcm.data + sample_count);
        pcm_frame_count = pcm.frame_count;
        pcm_channels = pcm.channels;
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
    // Keep a stable source-based beat interval for the original source BPM.
    source_click_interval_frames = (60.0 / config.bpm) * sample_rate;
    click_interval_frames = source_click_interval_frames / rate;

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
    pcm_position = 0.0;
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
    if (source_click_interval_frames > 0.0) {
        click_interval_frames = source_click_interval_frames / rate;
    }
}

void Voice::process(float* output, size_t num_frames, sb_frame_t engine_frame, size_t output_channels) {
    sb_voice_state_t current_state = state.load(std::memory_order_acquire);
    size_t render_offset = 0;

    if (current_state == SB_VOICE_SCHEDULED) {
        const sb_frame_t buffer_end = engine_frame + static_cast<sb_frame_t>(num_frames);
        if (scheduled_frame < buffer_end) {
            // The logical start may fall inside this callback buffer. Preserve the
            // requested sample frame instead of snapping the event to the buffer edge.
            state.store(SB_VOICE_PLAYING, std::memory_order_release);
            actual_start_frame = scheduled_frame;
            if (scheduled_frame > engine_frame) {
                render_offset = static_cast<size_t>(scheduled_frame - engine_frame);
            }
            current_state = SB_VOICE_PLAYING;
        }
    }

    if (current_state != SB_VOICE_PLAYING) {
        if (current_state == SB_VOICE_STOPPING) {
            state.store(SB_VOICE_IDLE, std::memory_order_release);
        }
        return;
    }

    if (source_type == SB_SOURCE_PCM_BUFFER) {
        render_pcm(output, render_offset, num_frames - render_offset, output_channels);
    // Process synthetic click based on sync mode.
    } else if (sync_mode == 1) {  // KEY_LOCK_SYNC
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

void Voice::render_pcm(float* output, size_t offset, size_t num_frames,
                       size_t output_channels) {
    for (size_t output_frame = 0; output_frame < num_frames; ++output_frame) {
        const uint64_t source_frame = static_cast<uint64_t>(pcm_position);
        if (source_frame >= pcm_frame_count) {
            state.store(SB_VOICE_IDLE, std::memory_order_release);
            return;
        }

        const size_t source_base = static_cast<size_t>(source_frame) * pcm_channels;
        const size_t output_base = (offset + output_frame) * output_channels;
        for (size_t channel = 0; channel < output_channels; ++channel) {
            const size_t source_channel = pcm_channels == 1 ? 0 : std::min<size_t>(channel, 1);
            output[output_base + channel] += gain * pcm_samples[source_base + source_channel];
        }
        pcm_position += static_cast<double>(rate);
    }

    if (pcm_position >= static_cast<double>(pcm_frame_count)) {
        state.store(SB_VOICE_IDLE, std::memory_order_release);
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
                rendered_click_count.fetch_add(1, std::memory_order_relaxed);
                last_rendered_click_engine_frame.store(frame, std::memory_order_release);

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
