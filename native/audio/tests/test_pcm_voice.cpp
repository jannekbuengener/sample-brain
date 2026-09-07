// test_pcm_voice.cpp - deterministic finite PCM voice contracts (#529)
#include <samplebrain_audio.h>

#include "../src/voice.h"

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <type_traits>
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

static sb_voice_config_t pcm_config(
    sb_voice_id_t id,
    const float* data,
    uint64_t frame_count,
    uint32_t channels
) {
    sb_voice_config_t config = {};
    config.id = id;
    config.source.type = SB_SOURCE_PCM_BUFFER;
    config.source.pcm_buffer.data = data;
    config.source.pcm_buffer.frame_count = frame_count;
    config.source.pcm_buffer.channels = channels;
    config.initial_rate = 1.0f;
    config.gain = 1.0f;
    return config;
}

static sb_engine_t open_test_engine() {
    sb_engine_t engine = nullptr;
    sb_engine_config_t config = {};
    config.sample_rate = 48000;
    config.buffer_frames = 64;
    config.output_channels = 2;
    config.input_channels = 0;
    TEST_ASSERT_EQ(sb_engine_open(&config, &engine), SB_OK, "test engine opens");
    return engine;
}

static void test_pcm_descriptor_abi_shape() {
    std::printf("test_pcm_descriptor_abi_shape...\n");
    TEST_ASSERT(std::is_standard_layout<sb_pcm_buffer_config_t>::value,
                "PCM descriptor has a standard C-compatible layout");
    TEST_ASSERT_EQ(sizeof(((sb_source_descriptor_t*)nullptr)->pcm_buffer),
                   sizeof(sb_pcm_buffer_config_t),
                   "source union exposes the complete PCM descriptor");
}

static void test_pcm_deep_copy_scheduling_and_eof() {
    std::printf("test_pcm_deep_copy_scheduling_and_eof...\n");
    float caller_pcm[] = {0.25f, -0.5f, 0.75f, -1.0f};
    sb_voice_config_t config = pcm_config(11, caller_pcm, 4, 1);
    Voice voice(48000, config);

    for (float& sample : caller_pcm) sample = 0.0f;

    voice.schedule_start(102, 100);
    std::vector<float> output(6 * 2, 0.0f);
    voice.process(output.data(), 6, 100, 2);

    TEST_ASSERT_EQ(voice.requested_start_frame, 102, "requested frame is retained");
    TEST_ASSERT_EQ(voice.actual_start_frame, 102, "actual frame equals requested frame");
    TEST_ASSERT_EQ(output[0], 0.0f, "output is silent before scheduled frame");
    TEST_ASSERT_EQ(output[2], 0.0f, "second pre-start frame is silent");
    TEST_ASSERT_EQ(output[4], 0.25f, "deep-copied first mono sample renders on left");
    TEST_ASSERT_EQ(output[5], 0.25f, "mono sample is duplicated to right");
    TEST_ASSERT_EQ(output[10], -1.0f, "finite source renders through its final frame");
    TEST_ASSERT_EQ(voice.get_state(), SB_VOICE_IDLE, "finite PCM reaches IDLE at EOF");
}

static void test_pcm_stereo_and_rate_progression() {
    std::printf("test_pcm_stereo_and_rate_progression...\n");
    const float stereo_pcm[] = {0.1f, -0.1f, 0.2f, -0.2f};
    Voice stereo_voice(48000, pcm_config(12, stereo_pcm, 2, 2));
    stereo_voice.schedule_start(0, 0);
    float stereo_output[4] = {};
    stereo_voice.process(stereo_output, 2, 0, 2);
    TEST_ASSERT_EQ(stereo_output[0], 0.1f, "stereo left channel is preserved");
    TEST_ASSERT_EQ(stereo_output[1], -0.1f, "stereo right channel is preserved");
    TEST_ASSERT_EQ(stereo_output[2], 0.2f, "second stereo frame renders");

    float ramp[20];
    for (size_t i = 0; i < 20; ++i) ramp[i] = static_cast<float>(i);
    Voice rate_voice(48000, pcm_config(13, ramp, 20, 1));
    rate_voice.set_rate(1.1f);
    rate_voice.schedule_start(0, 0);
    float rate_output[11] = {};
    rate_voice.process(rate_output, 11, 0, 1);
    TEST_ASSERT_EQ(rate_output[0], 0.0f, "rate playback starts at source frame zero");
    TEST_ASSERT_EQ(rate_output[9], 9.0f, "rate 1.1 advances through source frame nine");
    TEST_ASSERT_EQ(rate_output[10], 11.0f, "rate 1.1 skips to source frame eleven");
}

static void test_pcm_stop_is_deterministic() {
    std::printf("test_pcm_stop_is_deterministic...\n");
    const float pcm[] = {0.5f, 0.25f, 0.125f, 0.0625f};
    Voice voice(48000, pcm_config(14, pcm, 4, 1));
    voice.schedule_start(0, 0);
    voice.stop();
    float output[4] = {1.0f, 1.0f, 1.0f, 1.0f};
    voice.process(output, 4, 0, 1);
    TEST_ASSERT_EQ(voice.get_state(), SB_VOICE_IDLE, "stopped PCM voice becomes IDLE");
    TEST_ASSERT_EQ(output[0], 0.0f, "stopped PCM voice emits silence");
}

static void expect_invalid_pcm(
    sb_engine_t engine,
    const sb_voice_config_t& config,
    const char* message
) {
    sb_voice_id_t out_id = 9999;
    TEST_ASSERT_EQ(sb_voice_create(engine, &config, &out_id), SB_ERR_INVALID_ARG, message);
    TEST_ASSERT_EQ(out_id, 9999u, "failed create leaves out_id unchanged");
    sb_snapshot_t snapshot = {};
    TEST_ASSERT_EQ(sb_engine_snapshot(engine, &snapshot), SB_OK, "snapshot after rejected create succeeds");
    TEST_ASSERT_EQ(snapshot.total_voice_count, 0u, "rejected create registers no partial voice");
}

static void test_pcm_validation_is_fail_closed() {
    std::printf("test_pcm_validation_is_fail_closed...\n");
    sb_engine_t engine = open_test_engine();
    const float valid[] = {0.25f, -0.25f};

    expect_invalid_pcm(engine, pcm_config(20, nullptr, 2, 1), "null PCM data is rejected");
    expect_invalid_pcm(engine, pcm_config(21, valid, 0, 1), "empty PCM is rejected");
    expect_invalid_pcm(engine, pcm_config(22, valid, 2, 0), "zero channels are rejected");
    expect_invalid_pcm(engine, pcm_config(23, valid, 1, 3), "unsupported channels are rejected");

    const float non_finite[] = {0.0f, std::numeric_limits<float>::infinity()};
    expect_invalid_pcm(engine, pcm_config(24, non_finite, 2, 1), "non-finite PCM is rejected");
    expect_invalid_pcm(engine,
                       pcm_config(25, valid, std::numeric_limits<uint64_t>::max(), 2),
                       "PCM scalar-count overflow is rejected before reading data");

    sb_voice_config_t unknown = pcm_config(26, valid, 2, 1);
    unknown.source.type = static_cast<sb_source_type_t>(999);
    expect_invalid_pcm(engine, unknown, "unknown source type is rejected");

    sb_voice_config_t invalid_rate = pcm_config(27, valid, 2, 1);
    invalid_rate.initial_rate = std::numeric_limits<float>::quiet_NaN();
    expect_invalid_pcm(engine, invalid_rate, "non-finite initial rate is rejected");

    sb_voice_config_t invalid_gain = pcm_config(28, valid, 2, 1);
    invalid_gain.gain = std::numeric_limits<float>::quiet_NaN();
    expect_invalid_pcm(engine, invalid_gain, "non-finite gain is rejected");

    TEST_ASSERT_EQ(sb_engine_close(engine), SB_OK, "test engine closes");
}

static void test_pcm_public_create_remove_lifecycle() {
    std::printf("test_pcm_public_create_remove_lifecycle...\n");
    sb_engine_t engine = open_test_engine();
    const float pcm[] = {0.25f, -0.25f};
    sb_voice_config_t config = pcm_config(30, pcm, 2, 1);
    sb_voice_id_t out_id = 0;
    TEST_ASSERT_EQ(sb_voice_create(engine, &config, &out_id), SB_OK, "public PCM create succeeds");
    TEST_ASSERT_EQ(out_id, 30u, "public PCM create returns configured id");
    TEST_ASSERT_EQ(sb_voice_remove(engine, out_id), SB_OK, "public PCM remove succeeds");
    TEST_ASSERT_EQ(sb_voice_remove(engine, out_id), SB_ERR_VOICE_NOT_FOUND,
                   "removed PCM voice cannot be removed twice");
    TEST_ASSERT_EQ(sb_engine_close(engine), SB_OK, "test engine closes after remove");
}

int main() {
    std::printf("=== PCM Voice Tests ===\n\n");
    test_pcm_descriptor_abi_shape();
    test_pcm_deep_copy_scheduling_and_eof();
    test_pcm_stereo_and_rate_progression();
    test_pcm_stop_is_deterministic();
    test_pcm_validation_is_fail_closed();
    test_pcm_public_create_remove_lifecycle();
    std::printf("\n=== Results ===\nPassed: %d\nFailed: %d\n", tests_passed, tests_failed);
    return tests_failed > 0 ? 1 : 0;
}
