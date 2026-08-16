// synthetic.cpp - Synthetic signal implementation
#include "synthetic.h"
#include <cmath>
#include <algorithm>

namespace synthetic {

void generate_click_track(std::vector<float>& output,
                          double bpm,
                          uint32_t sample_rate,
                          uint32_t num_channels,
                          size_t duration_frames,
                          float frequency_hz,
                          float duration_ms,
                          float amplitude) {
    output.assign(duration_frames * num_channels, 0.0f);

    double interval_sec = 60.0 / bpm;
    size_t interval_frames = static_cast<size_t>(interval_sec * sample_rate);
    size_t click_frames = static_cast<size_t>(duration_ms / 1000.0 * sample_rate);
    click_frames = std::max<size_t>(1, click_frames);

    // Pre-compute click waveform
    std::vector<float> click(click_frames);
    for (size_t i = 0; i < click_frames; ++i) {
        double t = static_cast<double>(i) / sample_rate;
        double envelope = 1.0 - t / (duration_ms / 1000.0);
        envelope = std::max(0.0, envelope * envelope);
        click[i] = amplitude * std::sin(2.0 * M_PI * frequency_hz * t) * envelope;
    }

    // Place clicks
    for (size_t frame = 0; frame < duration_frames; frame += interval_frames) {
        if (frame + click_frames > duration_frames) break;
        for (size_t ch = 0; ch < num_channels; ++ch) {
            for (size_t i = 0; i < click_frames; ++i) {
                output[(frame + i) * num_channels + ch] += click[i];
            }
        }
    }
}

void generate_sine(std::vector<float>& output,
                   double frequency_hz,
                   uint32_t sample_rate,
                   uint32_t num_channels,
                   size_t num_frames,
                   float amplitude) {
    output.resize(num_frames * num_channels);
    for (size_t i = 0; i < num_frames; ++i) {
        double t = static_cast<double>(i) / sample_rate;
        float sample = amplitude * std::sin(2.0 * M_PI * frequency_hz * t);
        for (size_t ch = 0; ch < num_channels; ++ch) {
            output[i * num_channels + ch] = sample;
        }
    }
}

void generate_silence(std::vector<float>& output,
                      uint32_t num_channels,
                      size_t num_frames) {
    output.assign(num_frames * num_channels, 0.0f);
}

} // namespace synthetic