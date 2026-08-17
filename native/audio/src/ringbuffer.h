// ringbuffer.h - Lock-free ring buffer for recording
#ifndef SAMPLEBRAIN_RINGBUFFER_H
#define SAMPLEBRAIN_RINGBUFFER_H

#include "samplebrain_audio.h"
#include <atomic>
#include <vector>
#include <cstddef>

class RingBuffer {
public:
    RingBuffer(size_t capacity_frames, size_t num_channels);
    ~RingBuffer();

    // Write from audio callback (single producer)
    bool write(const float* data, size_t num_frames, size_t num_channels);

    // Read for finalization (single consumer, after recording stopped)
    bool read_all(float* out_buffer, size_t& out_frames);

    // Query
    size_t available_frames() const;
    size_t capacity_frames() const { return capacity; }
    size_t num_channels() const { return channels; }
    size_t dropped_frames() const { return dropped.load(); }

    void reset();

private:
    const size_t capacity;
    const size_t channels;
    std::vector<float> buffer;
    std::atomic<size_t> write_pos{0};
    std::atomic<size_t> read_pos{0};
    std::atomic<size_t> dropped{0};
};

class Recording {
public:
    Recording(uint32_t sample_rate, uint32_t num_channels, sb_frame_t start_frame);
    ~Recording();

    bool is_active() const { return active.load(); }
    void write(const float* data, size_t num_frames, size_t num_channels);
    void finalize(float** out_buffer, size_t* out_frames);
    size_t dropped_frames() const { return ringbuf ? ringbuf->dropped_frames() : 0; }

    sb_recording_id_t id = 0;

private:
    std::atomic<bool> active{false};
    sb_frame_t start_frame;
    RingBuffer* ringbuf = nullptr;
    uint32_t sample_rate;
    uint32_t channels;
};

#endif
