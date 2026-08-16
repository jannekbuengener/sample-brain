// test_engine.cpp - Engine lifecycle tests
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

void test_engine_open_close() {
    printf("test_engine_open_close...\n");
    sb_engine_t engine = nullptr;
    sb_engine_config_t config = {};
    config.sample_rate = 48000;
    config.buffer_frames = 512;
    config.output_channels = 2;
    config.input_channels = 2;
    config.output_device = nullptr;
    config.input_device = nullptr;
    config.user_data = nullptr;

    sb_result_t result = sb_engine_open(&config, &engine);
    TEST_ASSERT_EQ(result, SB_OK, "sb_engine_open returns SB_OK");
    TEST_ASSERT(engine != nullptr, "engine handle is non-null");

    result = sb_engine_close(engine);
    TEST_ASSERT_EQ(result, SB_OK, "sb_engine_close returns SB_OK");
}

void test_engine_open_invalid_config() {
    printf("test_engine_open_invalid_config...\n");
    sb_engine_t engine = nullptr;
    sb_engine_config_t config = {};
    config.sample_rate = 0;  // Invalid
    config.buffer_frames = 512;
    config.output_channels = 2;
    config.input_channels = 2;

    sb_result_t result = sb_engine_open(&config, &engine);
    TEST_ASSERT_EQ(result, SB_ERR_INVALID_ARG, "sb_engine_open rejects zero sample rate");
    TEST_ASSERT(engine == nullptr, "engine handle is null on error");
}

void test_engine_start_stop() {
    printf("test_engine_start_stop...\n");
    sb_engine_t engine = nullptr;
    sb_engine_config_t config = {};
    config.sample_rate = 48000;
    config.buffer_frames = 512;
    config.output_channels = 2;
    config.input_channels = 2;

    sb_result_t result = sb_engine_open(&config, &engine);
    TEST_ASSERT_EQ(result, SB_OK, "open succeeds");

    result = sb_engine_start(engine);
    TEST_ASSERT_EQ(result, SB_OK, "start succeeds");

    // Give it a moment to start
    std::this_thread::sleep_for(std::chrono::milliseconds(10));

    result = sb_engine_stop(engine);
    TEST_ASSERT_EQ(result, SB_OK, "stop succeeds");

    result = sb_engine_close(engine);
    TEST_ASSERT_EQ(result, SB_OK, "close succeeds");
}

void test_engine_double_start() {
    printf("test_engine_double_start...\n");
    sb_engine_t engine = nullptr;
    sb_engine_config_t config = {};
    config.sample_rate = 48000;
    config.buffer_frames = 512;
    config.output_channels = 2;
    config.input_channels = 2;

    sb_result_t result = sb_engine_open(&config, &engine);
    TEST_ASSERT_EQ(result, SB_OK, "open succeeds");

    result = sb_engine_start(engine);
    TEST_ASSERT_EQ(result, SB_OK, "first start succeeds");

    result = sb_engine_start(engine);
    TEST_ASSERT_EQ(result, SB_ERR_ALREADY_RUNNING, "second start returns ALREADY_RUNNING");

    result = sb_engine_stop(engine);
    TEST_ASSERT_EQ(result, SB_OK, "stop succeeds");

    result = sb_engine_close(engine);
    TEST_ASSERT_EQ(result, SB_OK, "close succeeds");
}

void test_engine_stop_without_start() {
    printf("test_engine_stop_without_start...\n");
    sb_engine_t engine = nullptr;
    sb_engine_config_t config = {};
    config.sample_rate = 48000;
    config.buffer_frames = 512;
    config.output_channels = 2;
    config.input_channels = 2;

    sb_result_t result = sb_engine_open(&config, &engine);
    TEST_ASSERT_EQ(result, SB_OK, "open succeeds");

    result = sb_engine_stop(engine);
    TEST_ASSERT_EQ(result, SB_ERR_INVALID_STATE, "stop without start returns INVALID_STATE");

    result = sb_engine_close(engine);
    TEST_ASSERT_EQ(result, SB_OK, "close succeeds");
}

void test_snapshot_before_start() {
    printf("test_snapshot_before_start...\n");
    sb_engine_t engine = nullptr;
    sb_engine_config_t config = {};
    config.sample_rate = 48000;
    config.buffer_frames = 512;
    config.output_channels = 2;
    config.input_channels = 2;

    sb_result_t result = sb_engine_open(&config, &engine);
    TEST_ASSERT_EQ(result, SB_OK, "open succeeds");

    sb_snapshot_t snapshot = {};
    result = sb_engine_snapshot(engine, &snapshot);
    TEST_ASSERT_EQ(result, SB_OK, "snapshot succeeds before start");
    TEST_ASSERT_EQ(snapshot.running, false, "running is false before start");
    TEST_ASSERT_EQ(snapshot.engine_frame, 0, "engine_frame is 0 before start");
    TEST_ASSERT_EQ(snapshot.sample_rate, 48000u, "sample_rate matches config");
    TEST_ASSERT_EQ(snapshot.buffer_frames, 512u, "buffer_frames matches config");

    result = sb_engine_close(engine);
    TEST_ASSERT_EQ(result, SB_OK, "close succeeds");
}

int main() {
    printf("=== Engine Lifecycle Tests ===\n\n");

    test_engine_open_close();
    test_engine_open_invalid_config();
    test_engine_start_stop();
    test_engine_double_start();
    test_engine_stop_without_start();
    test_snapshot_before_start();

    printf("\n=== Results ===\n");
    printf("Passed: %d\n", tests_passed);
    printf("Failed: %d\n", tests_failed);

    return tests_failed > 0 ? 1 : 0;
}