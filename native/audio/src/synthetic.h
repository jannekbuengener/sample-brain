// synthetic.h - Synthetic signal generation
#ifndef SAMPLEBRAIN_SYNTHETIC_H
#define SAMPLEBRAIN_SYNTHETIC_H

#include "samplebrain_audio.h"
#include <vector>

namespace synthetic {

// Generate a click track at specified BPM
void generate_click_track(std::vector<float>& output,
                          double bpm,
                          uint32_t sample_rate,
                          uint32_t num_channels,
                          size_t duration_frames,
                          float frequency_hz = 800.0f,
                          float duration_ms = 5.0f,
                          float amplitude = 0.8f);

// Generate sine wave
void generate_sine(std::vector<float>& output,
                   double frequency_hz,
                   uint32_t sample_rate,
                   uint32_t num_channels,
                   size_t num_frames,
                   float amplitude = 0.5f);

// Generate silence
void generate_silence(std::vector<float>& output,
                      uint32_t num_channels,
                      size_t num_frames);

} // namespace synthetic

#endif