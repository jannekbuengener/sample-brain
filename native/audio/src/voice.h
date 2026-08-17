#ifndef SAMPLEBRAIN_VOICE_H
#define SAMPLEBRAIN_VOICE_H

#include "samplebrain_audio.h"
#include <atomic>
#include <vector>

class Voice {
public:
    Voice(uint32_t sample_rate, const sb_voice_config_t& config);
    ~Voice();

    void process(float* output, size_t num_frames, sb_frame_t engine_frame, size_t output_channels);
    void schedule_start(sb_frame_t frame, sb_frame_t current_engine_frame);
    void stop();
    void set_rate(float rate);

    sb_voice_state_t get_state() const { return state.load(); }

    sb_voice_id_t id;
    sb_frame_t requested_start_frame = 0;
    sb_frame_t actual_start_frame = 0;
    float rate = 1.0f;
    float gain = 1.0f;
    int sync_mode = 0;
    float source_bpm = 128.0f;
    float master_bpm = 132.0f;

    // #324 Key-Lock accessors
    bool is_key_lock_active() const;
    int get_input_latency_frames() const;
    int get_output_latency_frames() const;
    int get_grid_compensation_frames() const;

private:
    uint32_t sample_rate;
    std::atomic<sb_voice_state_t> state{SB_VOICE_IDLE};
    sb_frame_t scheduled_frame = 0;

    // Synthetic click source
    std::vector<float> click_samples;
    size_t click_length = 0;
    double source_click_interval_frames = 0.0;  // Stable beat spacing for the source BPM
    double click_interval_frames = 0.0;          // Effective click spacing after RATE_SYNC
    sb_frame_t next_click_frame = 0;
    std::atomic<uint64_t> rendered_click_count{0};
    std::atomic<sb_frame_t> last_rendered_click_engine_frame{0};

    // Stored config for Key-Lock processing
    sb_synthetic_click_config_t click_config;

    void generate_click_samples(const sb_synthetic_click_config_t& click_config);
    void render_click(float* output, size_t offset, size_t num_frames,
                      sb_frame_t engine_frame, size_t output_channels);

    // #324 Key-Lock Voice
    class KeyLockVoiceImpl;
    KeyLockVoiceImpl* kl_voice = nullptr;
};

#endif
