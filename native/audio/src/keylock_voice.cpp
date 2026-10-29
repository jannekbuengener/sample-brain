// keylock_voice.cpp - Key-Lock Voice using Signalsmith Stretch
// Part of #324: Signalsmith key-lock mode for SYNC playback

#include "keylock_voice.h"
#include <cmath>
#include <algorithm>
#include <limits>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

namespace samplebrain {

bool KeyLockVoice::init(const KeyLockVoiceConfig& config) {
    config_ = config;
    state_ = SB_VOICE_IDLE;
    requested_start_frame_ = 0;
    actual_start_frame_ = 0;
    scheduled_frame_ = 0;
    source_read_pos_ = 0;
    source_buffer_loaded_ = false;
    pcm_source_loaded_ = false;
    key_lock_active_ = false;
    stretch_.reset();
    input_latency_frames_ = 0;
    output_latency_frames_ = 0;
    effective_compensation_frames_ = 0;

    const bool bpm_valid =
        std::isfinite(config_.source_bpm) && config_.source_bpm > 0.0f &&
        std::isfinite(config_.master_bpm) && config_.master_bpm > 0.0f;

    if (!bpm_valid) {
        current_tempo_ratio_ = 1.0f;
        if (config_.sync_mode == SyncMode::KEY_LOCK_SYNC) {
            config_.sync_mode = SyncMode::RATE_SYNC;
        }
        if (config_.load_synthetic_source) {
            load_source_buffer();
        }
        return true;
    }

    current_tempo_ratio_ = config_.master_bpm / config_.source_bpm;

    if (config_.load_synthetic_source) {
        load_source_buffer();
    }

    // Initialize Signalsmith if Key-Lock mode and available
    if (config_.sync_mode == SyncMode::KEY_LOCK_SYNC && config_.signalsmith_available) {
        key_lock_active_ = init_signalsmith();
        if (!key_lock_active_) {
            // Fallback to Rate Sync - Signalsmith unavailable
            config_.sync_mode = SyncMode::RATE_SYNC;
        }
    }

    // Calculate rate sync interval
    if (config_.source_bpm > 0) {
        double interval_sec = 60.0 / config_.source_bpm;
        rate_interval_frames_ = interval_sec * config_.sample_rate / current_tempo_ratio_;
    }

    return true;
}

bool KeyLockVoice::init_signalsmith() {
    try {
        stretch_ = std::make_unique<signalsmith::stretch::SignalsmithStretch<float>>();

        // Use default preset for high quality
        stretch_->presetDefault(config_.channels, static_cast<float>(config_.sample_rate), false);

        // For Key-Lock: NO pitch transpose (freqMultiplier = 1.0)
        // Time-stretch is achieved by passing different input/output buffer sizes to process()
        stretch_->setTransposeFactor(1.0f);

        update_latency();
        return true;
    } catch (const std::exception&) {
        stretch_.reset();
        return false;
    } catch (...) {
        stretch_.reset();
        return false;
    }
}

void KeyLockVoice::update_latency() {
    if (stretch_) {
        input_latency_frames_ = stretch_->inputLatency();
        output_latency_frames_ = stretch_->outputLatency();
        // Input latency is measured in source frames; convert to output frames via
        // the current tempo ratio so audible alignment lands on musical P.
        const double ratio = (std::isfinite(current_tempo_ratio_) && current_tempo_ratio_ > 0.0f)
            ? static_cast<double>(current_tempo_ratio_)
            : 1.0;
        effective_compensation_frames_ =
            static_cast<int>(std::lround(static_cast<double>(input_latency_frames_) / ratio)) +
            output_latency_frames_;
    } else {
        input_latency_frames_ = 0;
        output_latency_frames_ = 0;
        effective_compensation_frames_ = 0;
    }
}

void KeyLockVoice::prepare_process_capacity(size_t max_output_frames, float max_tempo_ratio) {
    if (max_output_frames == 0) {
        max_output_frames = 4096;
    }
    if (!std::isfinite(max_tempo_ratio) || max_tempo_ratio < 1.0f) {
        max_tempo_ratio = 4.0f;
    }
    const size_t max_input = static_cast<size_t>(
        std::ceil(static_cast<double>(max_output_frames) * static_cast<double>(max_tempo_ratio))) + 64;

    const size_t ch_count = static_cast<size_t>(std::max(config_.channels, 1));
    input_planar_.assign(ch_count, std::vector<float>(max_input, 0.0f));
    // Always allocate one planar buffer per DSP channel. Signalsmith writes every
    // configured channel even when the engine mix destination has fewer channels.
    output_planar_.assign(ch_count, std::vector<float>(max_output_frames, 0.0f));
    input_ptrs_.assign(ch_count, nullptr);
    output_ptrs_.assign(ch_count, nullptr);
    max_output_frames_ = max_output_frames;
    max_input_frames_ = max_input;
}

void KeyLockVoice::load_source_buffer() {
    // Generate synthetic click as source audio (offline / synthetic testing path).
    double interval_sec = 60.0 / std::max(config_.source_bpm, 1.0f);
    size_t click_interval_frames = static_cast<size_t>(interval_sec * config_.sample_rate);

    size_t total_frames = static_cast<size_t>(2.0 * config_.sample_rate);
    source_buffer_.assign(total_frames * static_cast<size_t>(config_.channels), 0.0f);

    float frequency_hz = config_.frequency_hz > 0.0f ? config_.frequency_hz : 800.0f;
    float amplitude = config_.amplitude;
    float duration_ms = 5.0f;

    size_t click_samples = static_cast<size_t>(duration_ms / 1000.0 * config_.sample_rate);
    click_samples = std::max<size_t>(1, click_samples);

    std::vector<float> click_waveform(click_samples);
    for (size_t i = 0; i < click_samples; ++i) {
        double t = static_cast<double>(i) / config_.sample_rate;
        double envelope = 1.0 - t / (duration_ms / 1000.0);
        envelope = std::max(0.0, envelope * envelope);
        click_waveform[i] = amplitude * std::sin(2.0 * M_PI * frequency_hz * t) * envelope;
    }

    if (click_interval_frames == 0) {
        click_interval_frames = 1;
    }
    for (size_t frame = 0; frame < total_frames; frame += click_interval_frames) {
        for (size_t i = 0; i < click_samples && (frame + i) < total_frames; ++i) {
            for (int ch = 0; ch < config_.channels; ++ch) {
                source_buffer_[(frame + i) * config_.channels + ch] += click_waveform[i];
            }
        }
    }

    source_buffer_loaded_ = true;
    source_read_pos_ = 0;
}

void KeyLockVoice::set_pcm_source(const float* data, size_t frames, int channels) {
    if (!data || frames == 0 || channels <= 0) {
        return;
    }
    source_buffer_.assign(frames * static_cast<size_t>(config_.channels), 0.0f);
    for (size_t i = 0; i < frames; ++i) {
        for (int ch = 0; ch < std::min(channels, config_.channels); ++ch) {
            source_buffer_[i * config_.channels + ch] = data[i * channels + ch];
        }
    }
    source_buffer_loaded_ = true;
    pcm_source_loaded_ = true;
    source_read_pos_ = 0;
    rate_playback_pos_ = 0.0;
    // Do NOT force key_lock_active_: effective Key-Lock requires a live stretch backend.
}

void KeyLockVoice::schedule_start(sb_frame_t engine_frame) {
    requested_start_frame_ = engine_frame;
    scheduled_frame_ = engine_frame;
    state_ = SB_VOICE_PLAYING;
    actual_start_frame_ = engine_frame;
    source_read_pos_ = 0;
    rate_playback_pos_ = 0.0;
    draining_ = false;
    drain_output_frames_remaining_ = 0;

    if (stretch_ && key_lock_active_) {
        stretch_->reset();
    }
}

void KeyLockVoice::stop() {
    state_ = SB_VOICE_STOPPING;
}

void KeyLockVoice::set_tempo_ratio(float tempo_ratio) {
    if (!std::isfinite(tempo_ratio) || tempo_ratio <= 0.0f) {
        return;
    }
    current_tempo_ratio_ = tempo_ratio;

    if (config_.source_bpm > 0) {
        double interval_sec = 60.0 / config_.source_bpm;
        rate_interval_frames_ = interval_sec * config_.sample_rate / current_tempo_ratio_;
    }
    update_latency();
}

void KeyLockVoice::set_sync_mode(SyncMode mode) {
    if (config_.sync_mode == mode) return;

    config_.sync_mode = mode;

    if (mode == SyncMode::KEY_LOCK_SYNC && config_.signalsmith_available) {
        key_lock_active_ = init_signalsmith();
        if (!key_lock_active_) {
            config_.sync_mode = SyncMode::RATE_SYNC;
        }
    } else {
        key_lock_active_ = false;
        stretch_.reset();
        input_latency_frames_ = 0;
        output_latency_frames_ = 0;
        effective_compensation_frames_ = 0;
    }

    source_read_pos_ = 0;
    rate_playback_pos_ = 0.0;
}

void KeyLockVoice::set_source_bpm(float bpm) {
    if (!std::isfinite(bpm) || bpm <= 0.0f) return;
    config_.source_bpm = bpm;
    current_tempo_ratio_ = config_.master_bpm / config_.source_bpm;

    if (config_.source_bpm > 0) {
        double interval_sec = 60.0 / config_.source_bpm;
        rate_interval_frames_ = interval_sec * config_.sample_rate / current_tempo_ratio_;
    }
    update_latency();

    if (!pcm_source_loaded_ && config_.load_synthetic_source) {
        load_source_buffer();
    }
}

void KeyLockVoice::set_master_bpm(float bpm) {
    if (!std::isfinite(bpm) || bpm <= 0.0f) return;
    config_.master_bpm = bpm;
    current_tempo_ratio_ = config_.master_bpm / config_.source_bpm;

    if (config_.source_bpm > 0) {
        double interval_sec = 60.0 / config_.source_bpm;
        rate_interval_frames_ = interval_sec * config_.sample_rate / current_tempo_ratio_;
    }
    update_latency();
}

bool KeyLockVoice::process(float* output, size_t num_frames, size_t output_channels) {
    sb_voice_state_t current_state = state_;

    if (current_state != SB_VOICE_PLAYING) {
        if (current_state == SB_VOICE_STOPPING) {
            state_ = SB_VOICE_IDLE;
        }
        std::fill(output, output + num_frames * output_channels, 0.0f);
        return false;
    }

    if (config_.sync_mode == SyncMode::KEY_LOCK_SYNC && key_lock_active_) {
        process_key_lock(output, num_frames, output_channels);
    } else {
        process_rate_sync(output, num_frames, output_channels);
    }

    return state_ == SB_VOICE_PLAYING;
}

void KeyLockVoice::process_rate_sync(float* output, size_t num_frames, size_t output_channels) {
    std::fill(output, output + num_frames * output_channels, 0.0f);

    if (!source_buffer_loaded_ || source_buffer_.empty()) return;

    if (pcm_source_loaded_) {
        size_t source_frames = source_buffer_.size() / static_cast<size_t>(config_.channels);
        double read_speed = current_tempo_ratio_;

        for (size_t i = 0; i < num_frames; ++i) {
            double src_pos = rate_playback_pos_ + static_cast<double>(i) * read_speed;
            if (src_pos < 0.0 || src_pos >= static_cast<double>(source_frames) - 1.0) {
                if (src_pos >= static_cast<double>(source_frames) - 1.0) {
                    state_ = SB_VOICE_IDLE;
                }
                continue;
            }

            size_t src_idx = static_cast<size_t>(src_pos);
            double frac = src_pos - static_cast<double>(src_idx);

            for (size_t ch = 0; ch < output_channels && ch < static_cast<size_t>(config_.channels); ++ch) {
                float s0 = source_buffer_[src_idx * config_.channels + ch];
                float s1 = (src_idx + 1 < source_frames)
                    ? source_buffer_[(src_idx + 1) * config_.channels + ch]
                    : s0;
                float sample = static_cast<float>(s0 * (1.0 - frac) + s1 * frac) * config_.gain;
                output[i * output_channels + ch] = sample;
            }
        }
        rate_playback_pos_ += static_cast<double>(num_frames) * read_speed;
        if (rate_playback_pos_ >= static_cast<double>(source_frames)) {
            state_ = SB_VOICE_IDLE;
        }
    } else {
        size_t source_frames = source_buffer_.size() / static_cast<size_t>(config_.channels);

        double frame = 0.0;
        while (frame < static_cast<double>(num_frames)) {
            size_t pos = static_cast<size_t>(frame);
            if (pos < num_frames && source_frames > 0) {
                size_t source_pos = static_cast<size_t>(rate_playback_pos_ * current_tempo_ratio_) % source_frames;
                for (size_t ch = 0; ch < output_channels && ch < static_cast<size_t>(config_.channels); ++ch) {
                    for (size_t i = 0; i < 64 && (pos + i) < num_frames && (source_pos + i) < source_frames; ++i) {
                        float sample = source_buffer_[(source_pos + i) * config_.channels + ch] * config_.gain;
                        output[(pos + i) * output_channels + ch] += sample;
                    }
                }
            }
            frame += rate_interval_frames_;
        }
        rate_playback_pos_ += static_cast<double>(num_frames) / current_tempo_ratio_;
    }
}

void KeyLockVoice::process_key_lock(float* output, size_t num_frames, size_t output_channels) {
    std::fill(output, output + num_frames * output_channels, 0.0f);

    if (!source_buffer_loaded_ || !stretch_ || !key_lock_active_) return;
    if (num_frames == 0) return;

    if (max_output_frames_ < num_frames || max_input_frames_ == 0 ||
        input_planar_.size() != static_cast<size_t>(config_.channels)) {
        // Capacity must be prepared on the control path. Fail closed without allocating.
        return;
    }

    size_t source_frames = source_buffer_.size() / static_cast<size_t>(config_.channels);
    if (source_frames == 0) {
        state_ = SB_VOICE_IDLE;
        return;
    }

    float stretch_ratio = 1.0f / current_tempo_ratio_;
    size_t input_frames_needed = static_cast<size_t>(std::ceil(static_cast<double>(num_frames) / stretch_ratio));
    if (input_frames_needed > max_input_frames_) {
        input_frames_needed = max_input_frames_;
    }

    for (int ch = 0; ch < config_.channels; ++ch) {
        for (size_t i = 0; i < input_frames_needed; ++i) {
            if (pcm_source_loaded_) {
                size_t src_idx = source_read_pos_ + i;
                if (src_idx < source_frames) {
                    input_planar_[static_cast<size_t>(ch)][i] =
                        source_buffer_[src_idx * config_.channels + ch];
                } else {
                    input_planar_[static_cast<size_t>(ch)][i] = 0.0f;
                }
            } else {
                size_t src_idx = (source_read_pos_ + i) % source_frames;
                input_planar_[static_cast<size_t>(ch)][i] =
                    source_buffer_[src_idx * config_.channels + ch];
            }
        }
        input_ptrs_[static_cast<size_t>(ch)] = input_planar_[static_cast<size_t>(ch)].data();
    }

    // Signalsmith always writes config_.channels planar outputs.
    for (int ch = 0; ch < config_.channels; ++ch) {
        output_ptrs_[static_cast<size_t>(ch)] = output_planar_[static_cast<size_t>(ch)].data();
    }

    stretch_->process(
        input_ptrs_.data(), static_cast<int>(input_frames_needed),
        output_ptrs_.data(), static_cast<int>(num_frames));

    if (pcm_source_loaded_) {
        source_read_pos_ += input_frames_needed;
        if (source_read_pos_ >= source_frames && !draining_) {
            // Source consumed, but stretch still holds latency tail — drain with zeros.
            draining_ = true;
            drain_output_frames_remaining_ =
                static_cast<size_t>(std::max(0, effective_compensation_frames_));
        }
    } else {
        source_read_pos_ = (source_read_pos_ + input_frames_needed) % source_frames;
    }

    const size_t dsp_channels = static_cast<size_t>(std::max(config_.channels, 1));
    for (size_t i = 0; i < num_frames; ++i) {
        for (size_t ch = 0; ch < output_channels; ++ch) {
            const size_t src_ch = std::min(ch, dsp_channels - 1);
            output[i * output_channels + ch] = output_planar_[src_ch][i] * config_.gain;
        }
    }

    if (draining_) {
        if (drain_output_frames_remaining_ <= num_frames) {
            draining_ = false;
            drain_output_frames_remaining_ = 0;
            state_ = SB_VOICE_IDLE;
        } else {
            drain_output_frames_remaining_ -= num_frames;
        }
    }
}

} // namespace samplebrain
