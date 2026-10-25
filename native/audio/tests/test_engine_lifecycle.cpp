#include "../src/engine.cpp"

#include <chrono>
#include <cstdio>
#include <thread>
#include <vector>

static int tests_passed = 0;
static int tests_failed = 0;

#define TEST_ASSERT(cond, msg) \
    do { \
        if (cond) { \
            std::printf("  PASS: %s\n", msg); \
            tests_passed++; \
        } else { \
            std::printf("  FAIL: %s\n", msg); \
            tests_failed++; \
        } \
    } while (0)

#define TEST_ASSERT_EQ(a, b, msg) TEST_ASSERT((a) == (b), msg)

static sb_engine_t open_test_engine() {
    sb_engine_config_t config = {};
    config.sample_rate = 48000;
    config.buffer_frames = 64;
    config.output_channels = 2;
    config.input_channels = 0;

    sb_engine_t engine = nullptr;
    TEST_ASSERT_EQ(sb_engine_open(&config, &engine), SB_OK, "test engine opens");
    return engine;
}

static void notify_device(sb_engine_t engine, ma_device_notification_type type) {
    ma_device_notification notification = {};
    notification.pDevice = &engine->device;
    notification.type = type;
    ma_on_notification(&notification);
}

static void test_open_start_reports_healthy_device() {
    std::printf("test_open_start_reports_healthy_device...\n");
    sb_engine_t engine = open_test_engine();

    TEST_ASSERT_EQ(sb_engine_start(engine), SB_OK, "engine starts");
    sb_snapshot_t snapshot = {};
    TEST_ASSERT_EQ(sb_engine_snapshot(engine, &snapshot), SB_OK, "snapshot succeeds");
    TEST_ASSERT_EQ(snapshot.device_status, SB_DEVICE_OK, "started device status is OK");
    TEST_ASSERT_EQ(snapshot.recovery_state, 0u, "started recovery state is zero");

    TEST_ASSERT_EQ(sb_engine_stop(engine), SB_OK, "engine stops");
    TEST_ASSERT_EQ(sb_engine_close(engine), SB_OK, "engine closes");
}

static void test_intentional_stop_restart_reports_healthy_device() {
    std::printf("test_intentional_stop_restart_reports_healthy_device...\n");
    sb_engine_t engine = open_test_engine();

    TEST_ASSERT_EQ(sb_engine_start(engine), SB_OK, "engine starts");
    TEST_ASSERT_EQ(sb_engine_stop(engine), SB_OK, "engine stops intentionally");
    notify_device(engine, ma_device_notification_type_stopped);

    sb_snapshot_t snapshot = {};
    TEST_ASSERT_EQ(sb_engine_snapshot(engine, &snapshot), SB_OK, "stopped snapshot succeeds");
    TEST_ASSERT_EQ(snapshot.device_status, SB_DEVICE_OK,
                   "intentional stop does not report device loss");
    TEST_ASSERT_EQ(snapshot.recovery_state, 0u,
                   "intentional stop does not enter recovery");

    TEST_ASSERT_EQ(sb_engine_start(engine), SB_OK, "engine restarts");
    TEST_ASSERT_EQ(sb_engine_snapshot(engine, &snapshot), SB_OK, "restarted snapshot succeeds");
    TEST_ASSERT_EQ(snapshot.device_status, SB_DEVICE_OK,
                   "intentional restart reports device OK");
    TEST_ASSERT_EQ(snapshot.recovery_state, 0u,
                   "intentional restart clears recovery state");

    TEST_ASSERT_EQ(sb_engine_stop(engine), SB_OK, "engine stops after restart");
    TEST_ASSERT_EQ(sb_engine_close(engine), SB_OK, "engine closes");
}

static void test_repeated_intentional_restarts_are_stable() {
    std::printf("test_repeated_intentional_restarts_are_stable...\n");
    sb_engine_t engine = open_test_engine();

    TEST_ASSERT_EQ(sb_engine_start(engine), SB_OK, "engine starts");
    sb_snapshot_t snapshot = {};

    for (int cycle = 1; cycle <= 3; ++cycle) {
        TEST_ASSERT_EQ(sb_engine_stop(engine), SB_OK, "cycle stops intentionally");
        notify_device(engine, ma_device_notification_type_stopped);
        TEST_ASSERT_EQ(sb_engine_snapshot(engine, &snapshot), SB_OK,
                       "cycle stopped snapshot succeeds");
        TEST_ASSERT_EQ(snapshot.device_status, SB_DEVICE_OK,
                       "cycle stopped status remains OK");
        TEST_ASSERT_EQ(snapshot.recovery_state, 0u,
                       "cycle stopped recovery state remains zero");

        TEST_ASSERT_EQ(sb_engine_start(engine), SB_OK, "cycle restarts");
        TEST_ASSERT_EQ(sb_engine_snapshot(engine, &snapshot), SB_OK,
                       "cycle restarted snapshot succeeds");
        TEST_ASSERT_EQ(snapshot.device_status, SB_DEVICE_OK,
                       "cycle restarted status remains OK");
        TEST_ASSERT_EQ(snapshot.recovery_state, 0u,
                       "cycle restarted recovery state remains zero");
    }

    TEST_ASSERT_EQ(sb_engine_stop(engine), SB_OK, "engine stops after cycles");
    TEST_ASSERT_EQ(sb_engine_close(engine), SB_OK, "engine closes");
}

static void test_unexpected_device_events_preserve_loss_and_recovery() {
    std::printf("test_unexpected_device_events_preserve_loss_and_recovery...\n");
    sb_engine_t engine = open_test_engine();

    TEST_ASSERT_EQ(sb_engine_start(engine), SB_OK, "engine starts");
    notify_device(engine, ma_device_notification_type_stopped);

    sb_snapshot_t snapshot = {};
    TEST_ASSERT_EQ(sb_engine_snapshot(engine, &snapshot), SB_OK, "loss snapshot succeeds");
    TEST_ASSERT_EQ(snapshot.device_status, SB_DEVICE_LOST,
                   "unexpected stopped event reports device loss");
    TEST_ASSERT_EQ(snapshot.recovery_state, 1u,
                   "unexpected stopped event enters loss recovery state");

    notify_device(engine, ma_device_notification_type_started);
    TEST_ASSERT_EQ(sb_engine_snapshot(engine, &snapshot), SB_OK, "recovery snapshot succeeds");
    TEST_ASSERT_EQ(snapshot.device_status, SB_DEVICE_RECOVERING,
                   "unexpected restart reports recovery in progress");
    TEST_ASSERT_EQ(snapshot.recovery_state, 2u,
                   "unexpected restart enters active recovery state");

    notify_device(engine, ma_device_notification_type_rerouted);
    TEST_ASSERT_EQ(sb_engine_snapshot(engine, &snapshot), SB_OK, "reroute snapshot succeeds");
    TEST_ASSERT_EQ(snapshot.device_status, SB_DEVICE_LOST,
                   "unexpected reroute reports device loss");
    TEST_ASSERT_EQ(snapshot.recovery_state, 1u,
                   "unexpected reroute enters loss recovery state");

    TEST_ASSERT_EQ(sb_engine_stop(engine), SB_OK, "engine stops after device loss");
    TEST_ASSERT_EQ(sb_engine_start(engine), SB_OK, "engine starts after device loss");
    TEST_ASSERT_EQ(sb_engine_snapshot(engine, &snapshot), SB_OK,
                   "post-loss restart snapshot succeeds");
    TEST_ASSERT(snapshot.device_status != SB_DEVICE_OK,
                "successful start does not erase an actual device loss");
    TEST_ASSERT(snapshot.recovery_state != 0u,
                "successful start does not clear actual recovery state");

    TEST_ASSERT_EQ(sb_engine_stop(engine), SB_OK, "engine stops");
    TEST_ASSERT_EQ(sb_engine_close(engine), SB_OK, "engine closes");
}

static void test_pcm_playback_and_metrics_survive_intentional_restart() {
    std::printf("test_pcm_playback_and_metrics_survive_intentional_restart...\n");
    sb_engine_t engine = open_test_engine();
    std::vector<float> pcm(48000, 0.25f);

    sb_voice_config_t voice_config = {};
    voice_config.id = 1;
    voice_config.source.type = SB_SOURCE_PCM_BUFFER;
    voice_config.source.pcm_buffer.data = pcm.data();
    voice_config.source.pcm_buffer.frame_count = pcm.size();
    voice_config.source.pcm_buffer.channels = 1;
    voice_config.initial_rate = 1.0f;
    voice_config.gain = 1.0f;

    sb_voice_id_t voice_id = 0;
    TEST_ASSERT_EQ(sb_voice_create(engine, &voice_config, &voice_id), SB_OK,
                   "PCM voice creates");

    TEST_ASSERT_EQ(sb_engine_start(engine), SB_OK, "engine starts");
    TEST_ASSERT_EQ(sb_engine_stop(engine), SB_OK, "engine stops intentionally");
    notify_device(engine, ma_device_notification_type_stopped);
    TEST_ASSERT_EQ(sb_engine_start(engine), SB_OK, "engine restarts");

    sb_snapshot_t snapshot = {};
    TEST_ASSERT_EQ(sb_engine_snapshot(engine, &snapshot), SB_OK, "restart snapshot succeeds");
    TEST_ASSERT_EQ(snapshot.device_status, SB_DEVICE_OK,
                   "restart before playback reports device OK");
    TEST_ASSERT_EQ(snapshot.recovery_state, 0u,
                   "restart before playback clears recovery state");
    TEST_ASSERT_EQ(snapshot.underflow_count, 0u, "restart preserves underflow count");
    TEST_ASSERT_EQ(snapshot.overflow_count, 0u, "restart preserves overflow count");
    TEST_ASSERT_EQ(snapshot.xrun_count, 0u, "restart preserves xrun count");

    TEST_ASSERT_EQ(sb_voice_schedule_start(engine, voice_id, snapshot.engine_frame), SB_OK,
                   "PCM voice schedules after restart");
    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    TEST_ASSERT_EQ(sb_engine_snapshot(engine, &snapshot), SB_OK, "playback snapshot succeeds");
    TEST_ASSERT_EQ(snapshot.active_voice_count, 1u, "PCM voice is active after restart");
    TEST_ASSERT_EQ(snapshot.voice_states[0], SB_VOICE_PLAYING,
                   "PCM voice is playing after restart");
    TEST_ASSERT_EQ(snapshot.voice_rates[0], 1.0f, "PCM voice rate remains one");
    TEST_ASSERT_EQ(snapshot.voice_gains[0], 1.0f, "PCM voice gain remains one");
    TEST_ASSERT_EQ(snapshot.underflow_count, 0u, "playback preserves underflow count");
    TEST_ASSERT_EQ(snapshot.overflow_count, 0u, "playback preserves overflow count");
    TEST_ASSERT_EQ(snapshot.xrun_count, 0u, "playback preserves xrun count");

    TEST_ASSERT_EQ(sb_engine_stop(engine), SB_OK, "engine stops");
    TEST_ASSERT_EQ(sb_engine_close(engine), SB_OK, "engine closes");
}

int main() {
    std::printf("=== Engine Lifecycle Tests ===\n\n");

    test_open_start_reports_healthy_device();
    test_intentional_stop_restart_reports_healthy_device();
    test_repeated_intentional_restarts_are_stable();
    test_unexpected_device_events_preserve_loss_and_recovery();
    test_pcm_playback_and_metrics_survive_intentional_restart();

    std::printf("\n=== Results ===\nPassed: %d\nFailed: %d\n", tests_passed, tests_failed);
    return tests_failed > 0 ? 1 : 0;
}
