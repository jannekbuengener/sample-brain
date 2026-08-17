// test_metrics.cpp - Metrics collection tests
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

void test_snapshot_fields_populated() {
    printf("test_snapshot_fields_populated...\n");
    sb_engine_t engine = create_test_engine();

    sb_snapshot_t snapshot = {};
    sb_result_t result = sb_engine_snapshot(engine, &snapshot);
    TEST_ASSERT_EQ(result, SB_OK, "snapshot succeeds");

    // Verify all fields are populated (non-zero/initialized)
    TEST_ASSERT(snapshot.sample_rate == 48000u, "sample_rate populated");
    TEST_ASSERT(snapshot.buffer_frames == 512u, "buffer_frames populated");
    TEST_ASSERT(snapshot.device_status == SB_DEVICE_OK, "device_status is OK");
    TEST_ASSERT(snapshot.active_voice_count == 0u, "active_voice_count is 0");
    TEST_ASSERT(snapshot.total_voice_count == 0u, "total_voice_count is 0");
    TEST_ASSERT(snapshot.callback_mean_us >= 0.0, "callback_mean_us non-negative");
    TEST_ASSERT(snapshot.callback_p95_us >= 0.0, "callback_p95_us non-negative");
    TEST_ASSERT(snapshot.callback_p99_us >= 0.0, "callback_p99_us non-negative");
    TEST_ASSERT(snapshot.callback_max_us >= 0.0, "callback_max_us non-negative");
    TEST_ASSERT(snapshot.underflow_count == 0u, "underflow_count is 0");
    TEST_ASSERT(snapshot.overflow_count == 0u, "overflow_count is 0");
    TEST_ASSERT(snapshot.xrun_count == 0u, "xrun_count is 0");
    TEST_ASSERT(snapshot.recording_dropped_frames == 0u, "recording_dropped_frames is 0");
    TEST_ASSERT(snapshot.recording_active == false, "recording_active is false");

    destroy_test_engine(engine);
}

void test_callback_timing_metrics() {
    printf("test_callback_timing_metrics...\n");
    sb_engine_t engine = create_test_engine();

    // Let engine run for a bit to collect timing stats
    std::this_thread::sleep_for(std::chrono::milliseconds(200));

    sb_snapshot_t snapshot = {};
    sb_result_t result = sb_engine_snapshot(engine, &snapshot);
    TEST_ASSERT_EQ(result, SB_OK, "snapshot succeeds");

    // Timing metrics should be populated
    TEST_ASSERT(snapshot.callback_mean_us > 0.0, "callback_mean_us > 0");
    TEST_ASSERT(snapshot.callback_p95_us >= snapshot.callback_mean_us, "p95 >= mean");
    TEST_ASSERT(snapshot.callback_p99_us >= snapshot.callback_p95_us, "p99 >= p95");
    TEST_ASSERT(snapshot.callback_max_us >= snapshot.callback_p99_us, "max >= p99");

    // Reasonable bounds for 512 frames at 48kHz = ~10.6ms budget
    TEST_ASSERT(snapshot.callback_mean_us < 5000.0, "mean < 5ms (reasonable)");
    TEST_ASSERT(snapshot.callback_max_us < 10000.0, "max < 10ms (reasonable)");

    destroy_test_engine(engine);
}

void test_xrun_counters() {
    printf("test_xrun_counters...\n");
    sb_engine_t engine = create_test_engine();

    sb_snapshot_t snapshot = {};
    sb_engine_snapshot(engine, &snapshot);
    uint64_t initial_xruns = snapshot.xrun_count;

    // Run for a bit
    std::this_thread::sleep_for(std::chrono::milliseconds(500));

    sb_engine_snapshot(engine, &snapshot);
    // Xruns should not increase significantly in normal operation
    TEST_ASSERT(snapshot.xrun_count >= initial_xruns, "xrun_count non-decreasing");
    TEST_ASSERT(snapshot.xrun_count - initial_xruns < 10, "xruns minimal in normal op");

    destroy_test_engine(engine);
}

void test_snapshot_thread_safety() {
    printf("test_snapshot_thread_safety...\n");
    sb_engine_t engine = create_test_engine();

    // Call snapshot from multiple threads simultaneously
    const int num_threads = 4;
    const int iterations = 100;
    std::atomic<int> errors{0};

    auto snapshot_worker = [&]() {
        for (int i = 0; i < iterations; i++) {
            sb_snapshot_t snapshot = {};
            sb_result_t result = sb_engine_snapshot(engine, &snapshot);
            if (result != SB_OK) {
                errors++;
            }
            // Verify consistency
            if (snapshot.sample_rate != 48000u) errors++;
            if (snapshot.buffer_frames != 512u) errors++;
        }
    };

    std::vector<std::thread> threads;
    for (int i = 0; i < num_threads; i++) {
        threads.emplace_back(snapshot_worker);
    }

    for (auto& t : threads) {
        t.join();
    }

    TEST_ASSERT_EQ(errors.load(), 0, "no errors from concurrent snapshot reads");

    destroy_test_engine(engine);
}

void test_snapshot_during_voice_activity() {
    printf("test_snapshot_during_voice_activity...\n");
    sb_engine_t engine = create_test_engine();

    // Create and start a voice
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
    TEST_ASSERT_EQ(result, SB_OK, "schedule succeeds");

    // Wait for voice to start
    std::this_thread::sleep_for(std::chrono::milliseconds(600));

    // Snapshot during playback
    sb_engine_snapshot(engine, &snapshot);
    TEST_ASSERT_EQ(snapshot.active_voice_count, 1u, "active_voice_count is 1");
    TEST_ASSERT_EQ(snapshot.voice_states[0], SB_VOICE_PLAYING, "voice state is PLAYING");
    TEST_ASSERT_EQ(snapshot.voice_rates[0], 1.0f, "voice_rate is 1.0");
    TEST_ASSERT_EQ(snapshot.voice_gains[0], 1.0f, "voice_gain is 1.0");

    destroy_test_engine(engine);
}

void test_snapshot_during_recording() {
    printf("test_snapshot_during_recording...\n");
    sb_engine_t engine = create_test_engine();

    sb_recording_id_t rec_id = 0;
    sb_result_t result = sb_recording_start(engine, &rec_id, 0);
    TEST_ASSERT_EQ(result, SB_OK, "recording start succeeds");

    std::this_thread::sleep_for(std::chrono::milliseconds(100));

    sb_snapshot_t snapshot = {};
    sb_engine_snapshot(engine, &snapshot);
    TEST_ASSERT_EQ(snapshot.recording_active, true, "recording_active is true");
    TEST_ASSERT(snapshot.recording_dropped_frames < 100, "dropped frames minimal");

    float* buffer = nullptr;
    size_t frames = 0;
    result = sb_recording_stop(engine, 1, &buffer, &frames);
    TEST_ASSERT_EQ(result, SB_OK, "recording stop succeeds");
    sb_recording_free_buffer(buffer);

    destroy_test_engine(engine);
}

int main() {
    printf("=== Metrics Tests ===\n\n");

    test_snapshot_fields_populated();
    test_callback_timing_metrics();
    test_xrun_counters();
    test_snapshot_thread_safety();
    test_snapshot_during_voice_activity();
    test_snapshot_during_recording();

    printf("\n=== Results ===\n");
    printf("Passed: %d\n", tests_passed);
    printf("Failed: %d\n", tests_failed);

    return tests_failed > 0 ? 1 : 0;
}
