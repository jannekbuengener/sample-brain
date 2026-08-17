// keylock_voice.h - Key-Lock Voice using Signalsmith Stretch
// Part of #324: Signalsmith key-lock mode for SYNC playback

#pragma once

#include "samplebrain_audio.h"
#include "voice.h"
#include <signalsmith-stretch/signalsmith-stretch.h>
#include <vector>
#include <memory>

namespace samplebrain {

// Sync mode enumeration
enum class SyncMode {
    RATE_SYNC = 0,    // #323: rate = master/source, pitch follows tempo
    KEY_LOCK_SYNC = 1 // #324: tempo follows master, pitch preserved via Signalsmith
};

// Key-Lock voice configuration
struct KeyLockVoiceConfig {
    sb_voice_id_t id = 0;
    float source_bpm = 128.0f;      // Original sample BPM
    float master_bpm = 132.0f;      // Current session/master BPM
    int sample_rate = 48000;        // Audio sample rate
    int channels = 2;               // Number of channels
    SyncMode sync_mode = SyncMode::RATE_SYNC;
    float gain = 1.0f;              // Voice gain
    bool signalsmith_available = true; // Set to false if Signalsmith init failed
    float frequency_hz = 800.0f;      // Click frequency for synthetic source
    float amplitude = 0.8f;           // Click amplitude
};

class KeyLockVoice {
public:
    KeyLockVoice() = default;
    ~KeyLockVoice() = default;

    // Initialize with configuration
    bool init(const KeyLockVoiceConfig& config);

    // Process audio - fills output buffer
    // Returns true if voice is active and produced output
    bool process(float* output, size_t num_frames, size_t output_channels);

    // Schedule voice to start at exact engine frame
    void schedule_start(sb_frame_t engine_frame);

    // Stop the voice
    void stop();

    // Set playback rate (tempo ratio = master_bpm / source_bpm)
    // This is called when master tempo or source BPM changes
    void set_tempo_ratio(float tempo_ratio);

    // Set sync mode (RATE_SYNC or KEY_LOCK_SYNC)
    void set_sync_mode(SyncMode mode);

    // Set source BPM (original sample BPM)
    void set_source_bpm(float bpm);

    // Set master BPM (current session/master BPM)
    void set_master_bpm(float bpm);

    // Get current sync mode
    SyncMode get_sync_mode() const { return config_.sync_mode; }

    // Check if key-lock is active (Signalsmith initialized and mode is KEY_LOCK_SYNC)
    bool is_key_lock_active() const { return key_lock_active_; }

    // Get latency information (for grid compensation)
    int get_input_latency_frames() const { return input_latency_frames_; }
    int get_output_latency_frames() const { return output_latency_frames_; }
    int get_effective_grid_compensation_frames() const { return effective_compensation_frames_; }

    // Get voice state
    sb_voice_state_t get_state() const { return state_; }

    // Get voice ID
    sb_voice_id_t get_id() const { return config_.id; }

    // Get scheduled start frame
    sb_frame_t get_requested_start_frame() const { return requested_start_frame_; }
    sb_frame_t get_actual_start_frame() const { return actual_start_frame_; }

    // Get current gain
    float get_gain() const { return config_.gain; }

    // Set gain
    void set_gain(float gain) { config_.gain = gain; }

    // Set PCM source buffer directly (for testing offline processing)
    void set_pcm_source(const float* data, size_t frames, int channels);

private:
    // Configuration
    KeyLockVoiceConfig config_;

    // Runtime state
    sb_voice_state_t state_ = SB_VOICE_IDLE;
    sb_frame_t requested_start_frame_ = 0;
    sb_frame_t actual_start_frame_ = 0;
    sb_frame_t scheduled_frame_ = 0;
    float current_tempo_ratio_ = 1.0f;

    // Audio buffer (source audio data)
    std::vector<float> source_buffer_;
    size_t source_read_pos_ = 0;
    bool source_buffer_loaded_ = false;
    bool pcm_source_loaded_ = false;

    // Signalsmith Stretch instance (only for KEY_LOCK_SYNC mode)
    std::unique_ptr<signalsmith::stretch::SignalsmithStretch<float>> stretch_;
    bool key_lock_active_ = false;

    // Latency tracking (from Signalsmith)
    int input_latency_frames_ = 0;
    int output_latency_frames_ = 0;
    int effective_compensation_frames_ = 0;

    // For RATE_SYNC mode (simple rate-based playback)
    double rate_playback_pos_ = 0.0;
    double rate_interval_frames_ = 0.0;

    // Initialize Signalsmith Stretch
    bool init_signalsmith();

    // Load source audio buffer (synthetic click for testing, or PCM data)
    void load_source_buffer();

    // Check if PCM source is loaded (vs synthetic clicks)

    // Process using Rate Sync (simple rate change)
    void process_rate_sync(float* output, size_t num_frames, size_t output_channels);

    // Process using Key-Lock Sync (Signalsmith time-stretch)
    void process_key_lock(float* output, size_t num_frames, size_t output_channels);

    // Update latency values from Signalsmith
    void update_latency();
};

} // namespace samplebrain