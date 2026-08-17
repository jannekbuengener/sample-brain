// test_voice.cpp - Voice lifecycle tests
#include <samplebrain_audio.h>
#include <cassert>
#include <cstdio>
#include <thread>
#include <chrono>

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

void test_voice_create_remove() {
    printf("test_voice_create_remove...\n");
    sb_engine_t engine = create_test_engine();

    sb_voice_config_t vconfig = {};
    vconfig.id = 1;
    vconfig.source.type = SB_SOURCE_SYNTHETIC_CLICK;
    vconfig.source.synthetic_click.bpm = 128.0;
    vconfig.source.synthetic_click.frequency_hz = 800.0;
    vconfig.source.synthetic_click.duration_ms = 5.0;
    vconfig.source.synthetic_click.amplitude = 0.8;
    vconfig.initial_rate = 1.0f;
    vconfig.gain = 1.0f;

    sb_voice_id_t voice_id = 0;
    sb_result_t result = sb_voice_create(engine, &vconfig, &voice_id);
    TEST_ASSERT_EQ(result, SB_OK, "voice_create succeeds");
    TEST_ASSERT_EQ(voice_id, 1u, "voice_id matches config");

    sb_snapshot_t snapshot = {};
    sb_engine_snapshot(engine, &snapshot);
    TEST_ASSERT_EQ(snapshot.total_voice_count, 1u, "total_voice_count is 1");
    TEST_ASSERT_EQ(snapshot.active_voice_count, 0u, "active_voice_count is 0 (idle)");

    result = sb_voice_remove(engine, 1);
    TEST_ASSERT_EQ(result, SB_OK, "voice_remove succeeds");

    sb_engine_snapshot(engine, &snapshot);
    TEST_ASSERT_EQ(snapshot.total_voice_count, 0u, "total_voice_count is 0 after remove");

    destroy_test_engine(engine);
}

void test_voice_create_duplicate_id() {
    printf("test_voice_create_duplicate_id...\n");
    sb_engine_t engine = create_test_engine();

    sb_voice_config_t vconfig = {};
    vconfig.id = 1;
    vconfig.source.type = SB_SOURCE_SYNTHETIC_CLICK;
    vconfig.source.synthetic_click.bpm = 128.0;
    vconfig.initial_rate = 1.0f;
    vconfig.gain = 1.0f;

    sb_voice_id_t voice_id = 0;
    sb_result_t result = sb_voice_create(engine, &vconfig, &voice_id);
    TEST_ASSERT_EQ(result, SB_OK, "first create succeeds");

    result = sb_voice_create(engine, &vconfig, &voice_id);
    TEST_ASSERT_EQ(result, SB_ERR_INVALID_ARG, "duplicate id returns INVALID_ARG");

    destroy_test_engine(engine);
}

void test_voice_schedule_start_stop() {
    printf("test_voice_schedule_start_stop...\n");
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
    TEST_ASSERT_EQ(result, SB_OK, "schedule_start succeeds");

    // Voice control is delivered through the realtime command queue. Give the
    // audio thread at least two 512-frame callbacks to publish SCHEDULED state.
    std::this_thread::sleep_for(std::chrono::milliseconds(30));
    sb_engine_snapshot(engine, &snapshot);
    TEST_ASSERT_EQ(snapshot.voice_states[0], SB_VOICE_SCHEDULED, "voice state is SCHEDULED");
    TEST_ASSERT_EQ(snapshot.requested_start_frame[0], start_frame, "requested_start_frame matches");

    std::this_thread::sleep_for(std::chrono::milliseconds(1100));

    sb_engine_snapshot(engine, &snapshot);
    TEST_ASSERT_EQ(snapshot.voice_states[0], SB_VOICE_PLAYING, "voice state is PLAYING");
    TEST_ASSERT_EQ(snapshot.actual_start_frame[0], start_frame, "actual_start_frame matches requested");
    TEST_ASSERT_EQ(snapshot.start_skew_frames[0], 0, "start_skew_frames is 0");

    result = sb_voice_stop(engine, 1);
    TEST_ASSERT_EQ(result, SB_OK, "voice_stop succeeds");

    std::this_thread::sleep_for(std::chrono::milliseconds(20));

    sb_engine_snapshot(engine, &snapshot);
    TEST_ASSERT_EQ(snapshot.voice_states[0], SB_VOICE_IDLE, "voice state is IDLE after stop");

    destroy_test_engine(engine);
}

void test_voice_schedule_past_frame() {
    printf("test_voice_schedule_past_frame...\n");
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
    sb_frame_t past_frame = snapshot.engine_frame - 1000;

    result = sb_voice_schedule_start(engine, 1, past_frame);
    TEST_ASSERT_EQ(result, SB_ERR_INVALID_ARG, "schedule past frame returns INVALID_ARG");

    destroy_test_engine(engine);
}

void test_voice_set_rate() {
    printf("test_voice_set_rate...\n");
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

    result = sb_voice_set_rate(engine, 1, 1.5f);
    TEST_ASSERT_EQ(result, SB_OK, "set_rate succeeds");

    std::this_thread::sleep_for(std::chrono::milliseconds(600));

    sb_engine_snapshot(engine, &snapshot);
    TEST_ASSERT_EQ(snapshot.voice_rates[0], 1.5f, "voice_rate updated to 1.5");

    destroy_test_engine(engine);
}

void test_voice_rate_sync_scenario() {
    printf("test_voice_rate_sync_scenario...\n");
    sb_engine_t engine = create_test_engine();

    sb_voice_config_t vconfig_a = {};
    vconfig_a.id = 1;
    vconfig_a.source.type = SB_SOURCE_SYNTHETIC_CLICK;
    vconfig_a.source.synthetic_click.bpm = 128.0;
    vconfig_a.initial_rate = 132.0 / 128.0;
    vconfig_a.gain = 1.0f;

    sb_voice_id_t voice_id = 0;
    sb_result_t result = sb_voice_create(engine, &vconfig_a, &voice_id);
    TEST_ASSERT_EQ(result, SB_OK, "voice A create succeeds");

    sb_voice_config_t vconfig_b = {};
    vconfig_b.id = 2;
    vconfig_b.source.type = SB_SOURCE_SYNTHETIC_CLICK;
    vconfig_b.source.synthetic_click.bpm = 140.0;
    vconfig_b.initial_rate = 132.0 / 140.0;
    vconfig_b.gain = 1.0f;

    result = sb_voice_create(engine, &vconfig_b, &voice_id);
    TEST_ASSERT_EQ(result, SB_OK, "voice B create succeeds");

    sb_snapshot_t snapshot = {};
    sb_engine_snapshot(engine, &snapshot);
    sb_frame_t start_frame = snapshot.engine_frame + 48000;

    result = sb_voice_schedule_start(engine, 1, start_frame);
    TEST_ASSERT_EQ(result, SB_OK, "voice A schedule succeeds");
    result = sb_voice_schedule_start(engine, 2, start_frame);
    TEST_ASSERT_EQ(result, SB_OK, "voice B schedule succeeds");

    std::this_thread::sleep_for(std::chrono::milliseconds(1100));

    sb_engine_snapshot(engine, &snapshot);
    TEST_ASSERT_EQ(snapshot.actual_start_frame[0], start_frame, "voice A actual start matches");
    TEST_ASSERT_EQ(snapshot.actual_start_frame[1], start_frame, "voice B actual start matches");
    TEST_ASSERT_EQ(snapshot.start_skew_frames[0], 0, "voice A skew is 0");
    TEST_ASSERT_EQ(snapshot.start_skew_frames[1], 0, "voice B skew is 0");
    TEST_ASSERT(snapshot.voice_rates[0] > 1.0f && snapshot.voice_rates[0] < 1.1f, "voice A rate ~1.03125");
    TEST_ASSERT(snapshot.voice_rates[1] > 0.9f && snapshot.voice_rates[1] < 1.0f, "voice B rate ~0.9428");

    destroy_test_engine(engine);
}

void test_voice_remove_not_found() {
    printf("test_voice_remove_not_found...\n");
    sb_engine_t engine = create_test_engine();

    sb_result_t result = sb_voice_remove(engine, 999);
    TEST_ASSERT_EQ(result, SB_ERR_VOICE_NOT_FOUND, "remove non-existent returns VOICE_NOT_FOUND");

    destroy_test_engine(engine);
}

int main() {
    printf("=== Voice Lifecycle Tests ===\n\n");

    test_voice_create_remove();
    test_voice_create_duplicate_id();
    test_voice_schedule_start_stop();
    test_voice_schedule_past_frame();
    test_voice_set_rate();
    test_voice_rate_sync_scenario();
    test_voice_remove_not_found();

    printf("\n=== Results ===\n");
    printf("Passed: %d\n", tests_passed);
    printf("Failed: %d\n", tests_failed);

    return tests_failed > 0 ? 1 : 0;
}
