// test_ringbuffer.cpp - Ring buffer accounting tests
#include <samplebrain_audio.h>
#include <cassert>
#include <cstdio>
#include <thread>
#include <chrono>
#include <vector>

static int tests_passed = 0;
static int tests_failed = 0;

#define TEST_ASSERT(cond, msg) \
    do { \
        if (cond) { \
            printf("  PASS: %s\n", msg); \
            tests_passed++; \
        } else { \
            printf("  FAIL: %s\n", msg); \
            tests_failed++; \
        } \
    } while(0)

#define TEST_ASSERT_EQ(a, b, msg) TEST_ASSERT((a) == (b), msg)

static sb_engine_t create_test_engine() {
    sb_engine_t engine = nullptr;
    sb_engine_config_t config = {};
    config.sample_rate = 48000;
    config.buffer_frames = 512;
    config.output_channels = 2;
    config.input_channels = 2;
    sb_result_t result = sb_engine_open(&config, &engine);
    assert(result == SB_OK);
    result = sb_engine_start(engine);
    assert(result == SB_OK);
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
    return engine;
}

static void destroy_test_engine(sb_engine_t engine) {
    sb_engine_stop(engine);
    sb_engine_close(engine);
}

void test_recording_start_stop() {
    printf("test_recording_start_stop...\n");
    sb_engine_t engine = create_test_engine();

    sb_snapshot_t snapshot = {};
    sb_engine_snapshot(engine, &snapshot);
    sb_frame_t start_frame = snapshot.engine_frame + 24000;  // 0.5s in future

    sb_recording_id_t rec_id = 0;
    sb_result_t result = sb_recording_start(engine, &rec_id, start_frame);
    TEST_ASSERT_EQ(result, SB_OK, "recording_start succeeds");
    TEST_ASSERT_EQ(rec_id, 1u, "recording_id is 1");

    // Wait 0.5s until the scheduled start plus about 0.5s of capture.
    std::this_thread::sleep_for(std::chrono::milliseconds(1000));

    sb_engine_snapshot(engine, &snapshot);
    TEST_ASSERT_EQ(snapshot.recording_active, true, "recording_active is true");

    float* buffer = nullptr;
    size_t frames = 0;
    result = sb_recording_stop(engine, rec_id, &buffer, &frames);
    TEST_ASSERT_EQ(result, SB_OK, "recording_stop succeeds");
    TEST_ASSERT(buffer != nullptr, "buffer is non-null");
    TEST_ASSERT(frames > 0, "frames > 0");

    size_t expected_frames = 24000;
    TEST_ASSERT(frames >= expected_frames * 0.9 && frames <= expected_frames * 1.1,
                "frames approximately matches 0.5s capture duration");

    sb_recording_free_buffer(buffer);

    sb_engine_snapshot(engine, &snapshot);
    TEST_ASSERT_EQ(snapshot.recording_active, false, "recording_active is false after stop");

    destroy_test_engine(engine);
}

void test_recording_dropped_frames_accounting() {
    printf("test_recording_dropped_frames_accounting...\n");
    sb_engine_t engine = create_test_engine();

    sb_recording_id_t rec_id = 0;
    sb_result_t result = sb_recording_start(engine, &rec_id, 0);
    TEST_ASSERT_EQ(result, SB_OK, "recording_start succeeds");

    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    sb_snapshot_t snapshot = {};
    sb_engine_snapshot(engine, &snapshot);
    uint64_t dropped_before = snapshot.recording_dropped_frames;

    TEST_ASSERT(dropped_before < 100, "dropped_frames is low during normal operation");

    float* buffer = nullptr;
    size_t frames = 0;
    result = sb_recording_stop(engine, rec_id, &buffer, &frames);
    TEST_ASSERT_EQ(result, SB_OK, "recording_stop succeeds");

    sb_recording_free_buffer(buffer);
    destroy_test_engine(engine);
}

void test_multiple_recordings_sequential() {
    printf("test_multiple_recordings_sequential...\n");
    sb_engine_t engine = create_test_engine();

    for (int i = 1; i <= 3; i++) {
        sb_recording_id_t rec_id = 0;
        sb_result_t result = sb_recording_start(engine, &rec_id, 0);
        TEST_ASSERT_EQ(result, SB_OK, "recording_start succeeds");
        TEST_ASSERT_EQ(rec_id, static_cast<sb_recording_id_t>(i), "recording id is monotonic");

        std::this_thread::sleep_for(std::chrono::milliseconds(50));

        float* buffer = nullptr;
        size_t frames = 0;
        result = sb_recording_stop(engine, rec_id, &buffer, &frames);
        TEST_ASSERT_EQ(result, SB_OK, "recording_stop succeeds");
        TEST_ASSERT(buffer != nullptr, "buffer is non-null");
        TEST_ASSERT(frames > 0, "frames > 0");

        sb_recording_free_buffer(buffer);
    }

    destroy_test_engine(engine);
}

void test_recording_not_found() {
    printf("test_recording_not_found...\n");
    sb_engine_t engine = create_test_engine();

    float* buffer = nullptr;
    size_t frames = 0;
    sb_result_t result = sb_recording_stop(engine, 999, &buffer, &frames);
    TEST_ASSERT_EQ(result, SB_ERR_RECORDING_NOT_FOUND, "stop non-existent returns RECORDING_NOT_FOUND");
    TEST_ASSERT(buffer == nullptr, "buffer is null on error");

    destroy_test_engine(engine);
}

void test_playback_and_recording_simultaneous() {
    printf("test_playback_and_recording_simultaneous...\n");
    sb_engine_t engine = create_test_engine();

    sb_voice_config_t vconfig = {};
    vconfig.id = 1;
    vconfig.source.type = SB_SOURCE_SYNTHETIC_CLICK;
    vconfig.source.synthetic_click.bpm = 128.0;
    vconfig.initial_rate = 1.0f;
    vconfig.gain = 1.0f;

    sb_voice_id_t voice_id = 0;
    sb_result_t result = sb_voice_create(engine, &vconfig, &voice_id);
    TEST_ASSERT_EQ(result, SB_OK, "voice create succeeds");

    sb_snapshot_t snapshot = {};
    sb_engine_snapshot(engine, &snapshot);
    sb_frame_t start_frame = snapshot.engine_frame + 24000;

    result = sb_voice_schedule_start(engine, 1, start_frame);
    TEST_ASSERT_EQ(result, SB_OK, "voice schedule succeeds");

    sb_recording_id_t rec_id = 0;
    result = sb_recording_start(engine, &rec_id, start_frame);
    TEST_ASSERT_EQ(result, SB_OK, "recording start succeeds");

    std::this_thread::sleep_for(std::chrono::milliseconds(1100));

    result = sb_voice_stop(engine, 1);
    TEST_ASSERT_EQ(result, SB_OK, "voice stop succeeds");

    float* buffer = nullptr;
    size_t frames = 0;
    result = sb_recording_stop(engine, rec_id, &buffer, &frames);
    TEST_ASSERT_EQ(result, SB_OK, "recording stop succeeds");
    TEST_ASSERT(buffer != nullptr, "buffer is non-null");
    TEST_ASSERT(frames > 0, "frames > 0");

    sb_recording_free_buffer(buffer);
    destroy_test_engine(engine);
}

int main() {
    printf("=== Ring Buffer / Recording Tests ===\n\n");

    test_recording_start_stop();
    test_recording_dropped_frames_accounting();
    test_multiple_recordings_sequential();
    test_recording_not_found();
    test_playback_and_recording_simultaneous();

    printf("\n=== Results ===\n");
    printf("Passed: %d\n", tests_passed);
    printf("Failed: %d\n", tests_failed);

    return tests_failed > 0 ? 1 : 0;
}
