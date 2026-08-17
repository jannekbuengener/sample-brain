// keylock_voice.cpp - Key-Lock Voice using Signalsmith Stretch
// Part of #324: Signalsmith key-lock mode for SYNC playback

#include "keylock_voice.h"
#include <cmath>
#include <algorithm>
#include <random>

namespace samplebrain {

bool KeyLockVoice::init(const KeyLockVoiceConfig& config) {
    config_ = config;
    state_ = SB_VOICE_IDLE;
    requested_start_frame_ = 0;
    actual_start_frame_ = 0;
    scheduled_frame_ = 0;
    source_read_pos_ = 0;
    source_buffer_loaded_ = false;
    key_lock_active_ = false;
    current_tempo_ratio_ = config_.master_bpm / config_.source_bpm;

    // Load source buffer (synthetic click for now)
    load_source_buffer();

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
        stretch_->setTransposeFactor(1.0f); // Explicitly ensure no pitch shift
        
        // Update latency values
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
        effective_compensation_frames_ = input_latency_frames_ + output_latency_frames_;
    } else {
        input_latency_frames_ = 0;
        output_latency_frames_ = 0;
        effective_compensation_frames_ = 0;
    }
}

void KeyLockVoice::load_source_buffer() {
    // Generate synthetic click as source audio (same as Voice class)
    // This is for testing - real implementation would load PCM from file
    double interval_sec = 60.0 / config_.source_bpm;
    size_t click_interval_frames = static_cast<size_t>(interval_sec * config_.sample_rate);
    
    // Generate 2 seconds of clicks at source BPM
    size_t total_frames = static_cast<size_t>(2.0 * config_.sample_rate);
    source_buffer_.resize(total_frames * config_.channels, 0.0f);
    
    float frequency_hz = 800.0f;
    float amplitude = 0.8f;
    float duration_ms = 5.0f;
    
    size_t click_samples = static_cast<size_t>(duration_ms / 1000.0 * config_.sample_rate);
    click_samples = std::max<size_t>(1, click_samples);
    
    // Generate click waveform
    std::vector<float> click_waveform(click_samples);
    for (size_t i = 0; i < click_samples; ++i) {
        double t = static_cast<double>(i) / config_.sample_rate;
        double envelope = 1.0 - t / (duration_ms / 1000.0);
        envelope = std::max(0.0, envelope * envelope);
        click_waveform[i] = amplitude * std::sin(2.0 * M_PI * frequency_hz * t) * envelope;
    }
    
    // Place clicks at source BPM intervals
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
    source_buffer_.resize(frames * config_.channels, 0.0f);
    for (size_t i = 0; i < frames; ++i) {
        for (int ch = 0; ch < std::min(channels, config_.channels); ++ch) {
            source_buffer_[i * config_.channels + ch] = data[i * channels + ch];
        }
    }
    source_buffer_loaded_ = true;
    pcm_source_loaded_ = true;
    source_read_pos_ = 0;
    key_lock_active_ = true;
}

void KeyLockVoice::schedule_start(sb_frame_t engine_frame) {
    sb_frame_t current = engine_frame; // Will be compared against actual engine frame in process
    if (engine_frame <= current) {
        scheduled_frame_ = current;
        requested_start_frame_ = engine_frame;
        state_ = SB_VOICE_PLAYING;
        actual_start_frame_ = current;
    } else {
        scheduled_frame_ = engine_frame;
        requested_start_frame_ = engine_frame;
        state_ = SB_VOICE_SCHEDULED;
    }
    source_read_pos_ = 0;
    rate_playback_pos_ = 0.0;
    
    // Reset Signalsmith if active
    if (stretch_ && key_lock_active_) {
        stretch_->reset();
    }
}

void KeyLockVoice::stop() {
    state_ = SB_VOICE_STOPPING;
}

void KeyLockVoice::set_tempo_ratio(float tempo_ratio) {
    current_tempo_ratio_ = tempo_ratio;
    
    // Update rate sync interval
    if (config_.source_bpm > 0) {
        double interval_sec = 60.0 / config_.source_bpm;
        rate_interval_frames_ = interval_sec * config_.sample_rate / current_tempo_ratio_;
    }
    
    // For Key-Lock, the tempo ratio is applied by passing different
    // input/output buffer sizes to Signalsmith process()
    // No additional config needed - handled in process_key_lock()
}

void KeyLockVoice::set_sync_mode(SyncMode mode) {
    if (config_.sync_mode == mode) return;
    
    config_.sync_mode = mode;
    
    if (mode == SyncMode::KEY_LOCK_SYNC && config_.signalsmith_available) {
        key_lock_active_ = init_signalsmith();
        if (!key_lock_active_) {
            // Fallback to Rate Sync
            config_.sync_mode = SyncMode::RATE_SYNC;
        }
    } else {
        key_lock_active_ = false;
        stretch_.reset();
    }
    
    // Reset playback position on mode change
    source_read_pos_ = 0;
    rate_playback_pos_ = 0.0;
}

void KeyLockVoice::set_source_bpm(float bpm) {
    if (bpm <= 0.0f) return;
    config_.source_bpm = bpm;
    current_tempo_ratio_ = config_.master_bpm / config_.source_bpm;
    
    // Update rate sync interval
    if (config_.source_bpm > 0) {
        double interval_sec = 60.0 / config_.source_bpm;
        rate_interval_frames_ = interval_sec * config_.sample_rate / current_tempo_ratio_;
    }
    
    // Reload source buffer with new BPM (for synthetic clicks)
    load_source_buffer();
}

void KeyLockVoice::set_master_bpm(float bpm) {
    if (bpm <= 0.0f) return;
    config_.master_bpm = bpm;
    current_tempo_ratio_ = config_.master_bpm / config_.source_bpm;
    
    // Update rate sync interval
    if (config_.source_bpm > 0) {
        double interval_sec = 60.0 / config_.source_bpm;
        rate_interval_frames_ = interval_sec * config_.sample_rate / current_tempo_ratio_;
    }
}

bool KeyLockVoice::process(float* output, size_t num_frames, size_t output_channels) {
    sb_voice_state_t current_state = state_;
    
    // Check if scheduled voice should start
    // Note: actual engine frame comparison is done by the engine
    if (current_state == SB_VOICE_SCHEDULED) {
        // The engine will call this with current engine_frame
        // We transition to PLAYING when scheduled_frame_ <= engine_frame
        // This is handled by the engine's command queue
    }
    
    if (current_state != SB_VOICE_PLAYING) {
        if (current_state == SB_VOICE_STOPPING) {
            state_ = SB_VOICE_IDLE;
        }
        // Clear output
        std::fill(output, output + num_frames * output_channels, 0.0f);
        return false;
    }
    
    // Process based on sync mode
    if (config_.sync_mode == SyncMode::KEY_LOCK_SYNC && key_lock_active_) {
        process_key_lock(output, num_frames, output_channels);
    } else {
        process_rate_sync(output, num_frames, output_channels);
    }
    
    return true;
}

void KeyLockVoice::process_rate_sync(float* output, size_t num_frames, size_t output_channels) {
    // Simple rate-based playback (existing #323 behavior)
    // For BPM sync: play source audio at tempo ratio
    
    std::fill(output, output + num_frames * output_channels, 0.0f);
    
    if (!source_buffer_loaded_ || source_buffer_.empty()) return;
    
    if (pcm_source_loaded_) {
        // PCM source mode: resample at tempo ratio
        // Rate Sync: pitch follows tempo (faster read = higher pitch)
        size_t source_frames = source_buffer_.size() / config_.channels;
        double read_speed = current_tempo_ratio_;
        
        for (size_t i = 0; i < num_frames; ++i) {
            double src_pos = (rate_playback_pos_ + i) * read_speed;
            if (src_pos < 0 || src_pos >= static_cast<double>(source_frames) - 1) continue;
            
            size_t src_idx = static_cast<size_t>(src_pos);
            double frac = src_pos - src_idx;
            
            for (size_t ch = 0; ch < output_channels && ch < static_cast<size_t>(config_.channels); ++ch) {
                float s0 = source_buffer_[src_idx * config_.channels + ch];
                float s1 = (src_idx + 1 < source_frames) ? 
                    source_buffer_[(src_idx + 1) * config_.channels + ch] : s0;
                float sample = (s0 * (1.0 - frac) + s1 * frac) * config_.gain;
                output[i * output_channels + ch] = sample;
            }
        }
        rate_playback_pos_ += num_frames * read_speed;
    } else {
        // Synthetic clicks mode: render clicks at adjusted rate
        size_t source_frames = source_buffer_.size() / config_.channels;
        
        // Render clicks for this buffer
        double frame = rate_playback_pos_;
        while (frame < static_cast<double>(num_frames)) {
            size_t pos = static_cast<size_t>(frame);
            if (pos < num_frames) {
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
        rate_playback_pos_ += num_frames / current_tempo_ratio_;
    }
}

void KeyLockVoice::process_key_lock(float* output, size_t num_frames, size_t output_channels) {
    // Signalsmith time-stretch processing
    // Key-Lock: tempo follows master (via tempo_ratio), pitch preserved
    
    std::fill(output, output + num_frames * output_channels, 0.0f);
    
    if (!source_buffer_loaded_ || !stretch_) return;
    
    size_t source_frames = source_buffer_.size() / config_.channels;
    
    // Prepare input buffers (planar format for Signalsmith)
    std::vector<float*> input_ptrs(config_.channels);
    std::vector<float*> output_ptrs(output_channels);
    
    // Calculate input frames needed for desired output frames
    // For BPM sync: when tempo increases (master > source), audio should be compressed
    // stretch_ratio = source_bpm / master_bpm (inverse of tempo ratio)
    float stretch_ratio = 1.0f / current_tempo_ratio_;
    
    // Input frames needed = output_frames / stretch_ratio
    size_t input_frames_needed = static_cast<size_t>(std::ceil(num_frames / stretch_ratio));
    
    // Prepare input data (planar)
    std::vector<std::vector<float>> input_planar(config_.channels, std::vector<float>(input_frames_needed));
    std::vector<std::vector<float>> output_planar(output_channels, std::vector<float>(num_frames));
    
    // Fill input from source buffer
    for (int ch = 0; ch < config_.channels; ++ch) {
        for (size_t i = 0; i < input_frames_needed; ++i) {
            size_t src_idx = (source_read_pos_ + i) % source_frames;
            input_planar[ch][i] = source_buffer_[src_idx * config_.channels + ch];
        }
        input_ptrs[ch] = input_planar[ch].data();
    }
    
    for (int ch = 0; ch < output_channels; ++ch) {
        output_ptrs[ch] = output_planar[ch].data();
    }
    
    // Process through Signalsmith
    // Input: input_frames_needed frames
    // Output: num_frames frames
    // This achieves time-stretch by ratio = num_frames / input_frames_needed ≈ stretch_ratio
    stretch_->process(input_ptrs.data(), static_cast<int>(input_frames_needed), 
                      output_ptrs.data(), static_cast<int>(num_frames));
    
    // Advance source read position
    source_read_pos_ = (source_read_pos_ + input_frames_needed) % source_frames;
    
    // Copy planar output to interleaved output
    for (size_t i = 0; i < num_frames; ++i) {
        for (int ch = 0; ch < output_channels; ++ch) {
            output[i * output_channels + ch] = output_planar[ch][i] * config_.gain;
        }
    }
}

} // namespace samplebrain