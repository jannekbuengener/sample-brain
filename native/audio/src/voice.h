// voice.h - Voice management
#ifndef SAMPLEBRAIN_VOICE_H
#define SAMPLEBRAIN_VOICE_H

#include "samplebrain_audio.h"
#include <atomic>
#include <vector>

struct sb_engine;

class Voice {
public:
    Voice(sb_engine_t engine, const sb_voice_config_t& config);
    ~Voice();

    void process(float* output, size_t num_frames, sb_frame_t engine_frame, size_t output_channels);
    void schedule_start(sb_frame_t frame);
    void stop();
    void set_rate(float rate);

    sb_voice_state_t get_state() const { return state.load(); }

    sb_voice_id_t id;
    sb_frame_t requested_start_frame = 0;
    sb_frame_t actual_start_frame = 0;
    float rate = 1.0f;
    float gain = 1.0f;

private:
    sb_engine_t engine;
    std::atomic<sb_voice_state_t> state{SB_VOICE_IDLE};
    sb_frame_t scheduled_frame = 0;

    // Synthetic click source
    std::vector<float> click_samples;
    size_t click_length = 0;
    double click_interval_frames = 0;  // Frames between clicks
    sb_frame_t next_click_frame = 0;

    void generate_click_samples(const sb_synthetic_click_config_t& click_config);
    void render_click(float* output, size_t offset, size_t num_frames, size_t output_channels);
};

#endif