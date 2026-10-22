#include <samplebrain_audio.h>

#include <cstdio>
#include <cstring>
#include <chrono>
#include <thread>

static bool enumerate_and_check(int capture, uint32_t capacity) {
    sb_device_info_t devices[32] = {};
    uint32_t count = 0;
    if (sb_enumerate_devices(capture, devices, capacity, &count) != SB_OK || count != 1 || count > capacity) {
        return false;
    }
    for (uint32_t i = 0; i < count; ++i) {
        if (std::memchr(devices[i].name, '\0', sizeof(devices[i].name)) == nullptr ||
            std::memchr(devices[i].id_hex, '\0', sizeof(devices[i].id_hex)) == nullptr ||
            devices[i].is_default != 1 ||
            std::strcmp(devices[i].name, capture ? "NULL Capture Device" : "NULL Playback Device") != 0) {
            return false;
        }
    }
    return true;
}

static bool engine_lifecycle() {
    sb_engine_config_t config = {};
    config.sample_rate = 48000;
    config.buffer_frames = 512;
    config.output_channels = 2;
    config.input_channels = 2;
    sb_engine_t engine = nullptr;
    if (sb_engine_open(&config, &engine) != SB_OK) return false;
    if (sb_engine_start(engine) != SB_OK) return false;

    sb_voice_config_t voice = {};
    voice.id = 1;
    voice.source.type = SB_SOURCE_SYNTHETIC_CLICK;
    voice.source.synthetic_click.bpm = 120.0;
    voice.source.synthetic_click.frequency_hz = 800.0f;
    voice.source.synthetic_click.duration_ms = 5.0f;
    voice.source.synthetic_click.amplitude = 0.5f;
    voice.initial_rate = 1.0f;
    voice.gain = 1.0f;
    sb_voice_id_t voice_id = 0;
    if (sb_voice_create(engine, &voice, &voice_id) != SB_OK) return false;
    sb_snapshot_t snapshot = {};
    if (sb_engine_snapshot(engine, &snapshot) != SB_OK ||
        sb_voice_schedule_start(engine, voice_id, snapshot.engine_frame + 512) != SB_OK) return false;
    std::this_thread::sleep_for(std::chrono::milliseconds(30));
    if (sb_engine_stop(engine) != SB_OK || sb_engine_close(engine) != SB_OK) return false;
    return true;
}

int main() {
    for (int repeat = 0; repeat < 32; ++repeat) {
        for (int capture = 0; capture <= 1; ++capture) {
            if (!enumerate_and_check(capture, 1) || !enumerate_and_check(capture, 32)) {
                std::fprintf(stderr, "device enumeration failed: capture=%d repeat=%d\n", capture, repeat);
                return 1;
            }
        }
    }
    if (!engine_lifecycle()) return 1;
    for (int capture = 0; capture <= 1; ++capture) {
        if (!enumerate_and_check(capture, 32)) return 1;
    }
    return 0;
}
