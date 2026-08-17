// test_scheduler.cpp - Frame-accurate scheduling tests
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

void test_clock_monotonic() {
    printf("test_clock_monotonic...\n");
    sb_engine_t engine = create_test_engine();

    sb_frame_t last_frame = -1;
    bool non_decreasing = true;
    bool advanced = false;

    // The authoritative clock advances per audio callback. Snapshots taken more
    // frequently than one buffer may legitimately observe the same frame twice.
    for (int i = 0; i < 100; i++) {
        sb_snapshot_t snapshot = {};
        sb_engine_snapshot(engine, &snapshot);
        if (snapshot.engine_frame < last_frame) {
            non_decreasing = false;
            break;
        }
        if (snapshot.engine_frame > last_frame && last_frame >= 0) {
            advanced = true;
        }
        last_frame = snapshot.engine_frame;
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }

    TEST_ASSERT(non_decreasing, "engine_frame never moves backwards");
    TEST_ASSERT(advanced && last_frame > 0, "engine_frame advances across callbacks");

    destroy_test_engine(engine);
}

void test_buffer_size_independence() {
    printf("test_buffer_size_independence...\n");
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
    sb_frame_t start_frame = snapshot.engine_frame + 48000;

    result = sb_voice_schedule_start(engine, 1, start_frame);
    TEST_ASSERT_EQ(result, SB_OK, "schedule succeeds");

    std::this_thread::sleep_for(std::chrono::milliseconds(1100));

    sb_engine_snapshot(engine, &snapshot);
    TEST_ASSERT_EQ(snapshot.actual_start_frame[0], start_frame, "actual start matches requested regardless of buffer");
    TEST_ASSERT_EQ(snapshot.start_skew_frames[0], 0, "skew is 0");

    destroy_test_engine(engine);
}

void test_multiple_voices_same_frame() {
    printf("test_multiple_voices_same_frame...\n");
    sb_engine_t engine = create_test_engine();

    for (int i = 1; i <= 4; i++) {
        sb_voice_config_t vconfig = {};
        vconfig.id = i;
        vconfig.source.type = SB_SOURCE_SYNTHETIC_CLICK;
        vconfig.source.synthetic_click.bpm = 120.0 + i * 10.0;
        vconfig.initial_rate = 1.0f;
        vconfig.gain = 1.0f;

        sb_voice_id_t voice_id = 0;
        sb_result_t result = sb_voice_create(engine, &vconfig, &voice_id);
        TEST_ASSERT_EQ(result, SB_OK, "voice create succeeds");
    }

    sb_snapshot_t snapshot = {};
    sb_engine_snapshot(engine, &snapshot);
    sb_frame_t start_frame = snapshot.engine_frame + 48000;

    for (int i = 1; i <= 4; i++) {
        sb_result_t result = sb_voice_schedule_start(engine, i, start_frame);
        TEST_ASSERT_EQ(result, SB_OK, "schedule succeeds");
    }

    std::this_thread::sleep_for(std::chrono::milliseconds(1100));

    sb_engine_snapshot(engine, &snapshot);
    for (int i = 0; i < 4; i++) {
        TEST_ASSERT_EQ(snapshot.actual_start_frame[i], start_frame, "voice actual start matches");
        TEST_ASSERT_EQ(snapshot.start_skew_frames[i], 0, "voice skew is 0");
    }
    TEST_ASSERT_EQ(snapshot.active_voice_count, 4u, "all 4 voices active");

    destroy_test_engine(engine);
}

void test_schedule_at_buffer_boundary() {
    printf("test_schedule_at_buffer_boundary...\n");
    sb_engine_t engine = create_test_engine();

    sb_voice_config_t vconfig = {};
    vconfig.id = 1;
    vconfig.source.type = SB_SOURCE_SYNTHETIC_CLICK;
    vconfig.source.synthetic_click.bpm = 128.0;
    vconfig.initial_rate = 1.0f;
    vconfig.gain = 1.0f;

    sb_voice_id_t voice_id = 0;
    sb_result_t result = sb_voice_create(engine, &vconfig, &voice_id);
    TEST_ASSERT_EQ(result, SB_OK, "create succeeds");

    sb_snapshot_t snapshot = {};
    sb_engine_snapshot(engine, &snapshot);
    sb_frame_t current = snapshot.engine_frame;
    sb_frame_t aligned = ((current + 511) / 512) * 512 + 512;

    result = sb_voice_schedule_start(engine, 1, aligned);
    TEST_ASSERT_EQ(result, SB_OK, "schedule at boundary succeeds");

    double wait_sec = (aligned - current) / 48000.0 + 0.1;
    std::this_thread::sleep_for(std::chrono::milliseconds(static_cast<int>(wait_sec * 1000)));

    sb_engine_snapshot(engine, &snapshot);
    TEST_ASSERT_EQ(snapshot.actual_start_frame[0], aligned, "actual start at boundary matches");
    TEST_ASSERT_EQ(snapshot.start_skew_frames[0], 0, "skew is 0 at boundary");

    destroy_test_engine(engine);
}

void test_stop_before_scheduled_start() {
    printf("test_stop_before_scheduled_start...\n");
    sb_engine_t engine = create_test_engine();

    sb_voice_config_t vconfig = {};
    vconfig.id = 1;
    vconfig.source.type = SB_SOURCE_SYNTHETIC_CLICK;
    vconfig.source.synthetic_click.bpm = 128.0;
    vconfig.initial_rate = 1.0f;
    vconfig.gain = 1.0f;

    sb_voice_id_t voice_id = 0;
    sb_result_t result = sb_voice_create(engine, &vconfig, &voice_id);
    TEST_ASSERT_EQ(result, SB_OK, "create succeeds");

    sb_snapshot_t snapshot = {};
    sb_engine_snapshot(engine, &snapshot);
    sb_frame_t start_frame = snapshot.engine_frame + 48000;

    result = sb_voice_schedule_start(engine, 1, start_frame);
    TEST_ASSERT_EQ(result, SB_OK, "schedule succeeds");

    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    result = sb_voice_stop(engine, 1);
    TEST_ASSERT_EQ(result, SB_OK, "stop before start succeeds");

    std::this_thread::sleep_for(std::chrono::milliseconds(1000));

    sb_engine_snapshot(engine, &snapshot);
    TEST_ASSERT_EQ(snapshot.voice_states[0], SB_VOICE_IDLE, "voice remains IDLE after early stop");
    TEST_ASSERT_EQ(snapshot.actual_start_frame[0], 0, "actual_start_frame stays 0");

    destroy_test_engine(engine);
}

void test_rate_change_during_playback() {
    printf("test_rate_change_during_playback...\n");
    sb_engine_t engine = create_test_engine();

    sb_voice_config_t vconfig = {};
    vconfig.id = 1;
    vconfig.source.type = SB_SOURCE_SYNTHETIC_CLICK;
    vconfig.source.synthetic_click.bpm = 128.0;
    vconfig.initial_rate = 1.0f;
    vconfig.gain = 1.0f;

    sb_voice_id_t voice_id = 0;
    sb_result_t result = sb_voice_create(engine, &vconfig, &voice_id);
    TEST_ASSERT_EQ(result, SB_OK, "create succeeds");

    sb_snapshot_t snapshot = {};
    sb_engine_snapshot(engine, &snapshot);
    sb_frame_t start_frame = snapshot.engine_frame + 24000;

    result = sb_voice_schedule_start(engine, 1, start_frame);
    TEST_ASSERT_EQ(result, SB_OK, "schedule succeeds");

    std::this_thread::sleep_for(std::chrono::milliseconds(600));

    result = sb_voice_set_rate(engine, 1, 2.0f);
    TEST_ASSERT_EQ(result, SB_OK, "set_rate during playback succeeds");
    std::this_thread::sleep_for(std::chrono::milliseconds(30));

    sb_engine_snapshot(engine, &snapshot);
    TEST_ASSERT_EQ(snapshot.voice_rates[0], 2.0f, "rate updated to 2.0");

    result = sb_voice_set_rate(engine, 1, 0.5f);
    TEST_ASSERT_EQ(result, SB_OK, "set_rate again succeeds");
    std::this_thread::sleep_for(std::chrono::milliseconds(30));

    sb_engine_snapshot(engine, &snapshot);
    TEST_ASSERT_EQ(snapshot.voice_rates[0], 0.5f, "rate updated to 0.5");

    destroy_test_engine(engine);
}

int main() {
    printf("=== Scheduler Tests ===\n\n");

    test_clock_monotonic();
    test_buffer_size_independence();
    test_multiple_voices_same_frame();
    test_schedule_at_buffer_boundary();
    test_stop_before_scheduled_start();
    test_rate_change_during_playback();

    printf("\n=== Results ===\n");
    printf("Passed: %d\n", tests_passed);
    printf("Failed: %d\n", tests_failed);

    return tests_failed > 0 ? 1 : 0;
}
