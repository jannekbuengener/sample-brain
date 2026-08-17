// ringbuffer.cpp - Ring buffer implementation
#include "ringbuffer.h"
#include <algorithm>
#include <cstring>

RingBuffer::RingBuffer(size_t capacity_frames, size_t num_channels)
    : capacity(capacity_frames), channels(num_channels) {
    // Allocate buffer with extra space for wrap-around
    buffer.resize(capacity * channels);
    write_pos.store(0);
    read_pos.store(0);
    dropped.store(0);
}

RingBuffer::~RingBuffer() = default;

bool RingBuffer::write(const float* data, size_t num_frames, size_t num_channels) {
    if (num_channels != channels) return false;

    size_t current_write = write_pos.load(std::memory_order_relaxed);
    size_t current_read = read_pos.load(std::memory_order_acquire);

    size_t available = capacity - (current_write - current_read);
    if (num_frames > available) {
        // Buffer overflow - drop frames
        dropped.fetch_add(num_frames - available, std::memory_order_relaxed);
        num_frames = available;
        if (num_frames == 0) return false;
    }

    // Write data (handle wrap-around)
    size_t write_idx = (current_write % capacity) * channels;
    size_t first_chunk = std::min(num_frames, capacity - (current_write % capacity));

    // First chunk (before wrap)
    std::memcpy(&buffer[write_idx], data, first_chunk * channels * sizeof(float));

    // Second chunk (after wrap)
    if (first_chunk < num_frames) {
        size_t second_chunk = num_frames - first_chunk;
        std::memcpy(&buffer[0], &data[first_chunk * channels], second_chunk * channels * sizeof(float));
    }

    write_pos.store(current_write + num_frames, std::memory_order_release);
    return true;
}

bool RingBuffer::read_all(float* out_buffer, size_t& out_frames) {
    size_t current_write = write_pos.load(std::memory_order_acquire);
    size_t current_read = read_pos.load(std::memory_order_relaxed);

    size_t available = current_write - current_read;
    out_frames = available;

    if (available == 0) return true;

    // Read data (handle wrap-around)
    size_t read_idx = (current_read % capacity) * channels;
    size_t first_chunk = std::min(available, capacity - (current_read % capacity));

    std::memcpy(out_buffer, &buffer[read_idx], first_chunk * channels * sizeof(float));

    if (first_chunk < available) {
        size_t second_chunk = available - first_chunk;
        std::memcpy(&out_buffer[first_chunk * channels], &buffer[0], second_chunk * channels * sizeof(float));
    }

    read_pos.store(current_read + available, std::memory_order_release);
    return true;
}

size_t RingBuffer::available_frames() const {
    size_t current_write = write_pos.load(std::memory_order_acquire);
    size_t current_read = read_pos.load(std::memory_order_acquire);
    return current_write - current_read;
}

void RingBuffer::reset() {
    write_pos.store(0, std::memory_order_relaxed);
    read_pos.store(0, std::memory_order_relaxed);
    dropped.store(0, std::memory_order_relaxed);
}

Recording::Recording(uint32_t sample_rate_, uint32_t num_channels, sb_frame_t start_frame_)
    : start_frame(start_frame_), sample_rate(sample_rate_), channels(num_channels) {
    // Allocate ring buffer outside the audio callback for up to 30 minutes.
    size_t max_frames = static_cast<size_t>(sample_rate * 60 * 30);
    ringbuf = new RingBuffer(max_frames, num_channels);
}

Recording::~Recording() {
    delete ringbuf;
}

void Recording::write(const float* data, size_t num_frames, size_t num_channels, sb_frame_t engine_frame) {
    if (!ringbuf || num_channels != channels) return;

    const sb_frame_t buffer_end = engine_frame + static_cast<sb_frame_t>(num_frames);
    if (buffer_end <= start_frame) {
        return;
    }

    size_t first_frame = 0;
    if (engine_frame < start_frame) {
        first_frame = static_cast<size_t>(start_frame - engine_frame);
    }
    if (first_frame >= num_frames) return;

    active.store(true, std::memory_order_release);
    ringbuf->write(
        data + first_frame * num_channels,
        num_frames - first_frame,
        num_channels);
}

void Recording::finalize(float** out_buffer, size_t* out_frames) {
    active.store(false, std::memory_order_release);

    if (!out_buffer || !out_frames) return;
    *out_buffer = nullptr;
    *out_frames = 0;

    if (ringbuf) {
        size_t total_frames = ringbuf->available_frames();
        if (total_frames == 0) return;

        float* result = new float[total_frames * channels];
        size_t read_frames = total_frames;
        ringbuf->read_all(result, read_frames);
        *out_buffer = result;
        *out_frames = read_frames;
    }
}
