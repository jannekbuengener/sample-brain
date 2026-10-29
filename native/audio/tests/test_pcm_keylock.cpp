// test_pcm_keylock.cpp - #1279 PCM Key-Lock activation + scheduling compensation
#include <samplebrain_audio.h>

#include "../src/voice.h"
#include "../src/keylock_voice.h"

#include <chrono>
#include <cmath>
#include <cstdio>
#include <limits>
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

static int expected_grid_compensation(int input_latency, int output_latency,
                                      float source_bpm, float master_bpm) {
    double ratio = 1.0;
    if (std::isfinite(source_bpm) && source_bpm > 0.0f &&
        std::isfinite(master_bpm) && master_bpm > 0.0f) {
        ratio = static_cast<double>(master_bpm) / static_cast<double>(source_bpm);
    }
    return static_cast<int>(std::lround(static_cast<double>(input_latency) / ratio)) +
           output_latency;
}

static sb_voice_config_t make_pcm_config(
    sb_voice_id_t id,
    const float* data,
    uint64_t frame_count,
    uint32_t channels,
    int sync_mode,
    float source_bpm,
    float master_bpm,
    float initial_rate = 1.0f
) {
    sb_voice_config_t config = {};
    config.id = id;
    config.source.type = SB_SOURCE_PCM_BUFFER;
    config.source.pcm_buffer.data = data;
    config.source.pcm_buffer.frame_count = frame_count;
    config.source.pcm_buffer.channels = channels;
    config.initial_rate = initial_rate;
    config.gain = 1.0f;
    config.sync_mode = sync_mode;
    config.source_bpm = source_bpm;
    config.master_bpm = master_bpm;
    return config;
}

static std::vector<float> make_tone(size_t frames, float freq_hz, uint32_t sample_rate) {
    std::vector<float> pcm(frames);
    const double two_pi = 6.28318530717958647692;
    for (size_t i = 0; i < frames; ++i) {
        pcm[i] = static_cast<float>(std::sin(two_pi * freq_hz * static_cast<double>(i) / sample_rate));
    }
    return pcm;
}

static float dominant_frequency(const std::vector<float>& signal, uint32_t sample_rate) {
    // Goertzel-style peak search over a coarse FFT-like magnitude grid.
    const size_t n = signal.size();
    if (n < 16) return 0.0f;
    double best_mag = -1.0;
    float best_freq = 0.0f;
    for (int bin = 1; bin < static_cast<int>(n / 2); ++bin) {
        const double omega = 6.28318530717958647692 * bin / static_cast<double>(n);
        double s0 = 0.0;
        double s1 = 0.0;
        double s2 = 0.0;
        const double coeff = 2.0 * std::cos(omega);
        for (size_t i = 0; i < n; ++i) {
            s0 = signal[i] + coeff * s1 - s2;
            s2 = s1;
            s1 = s0;
        }
        const double mag = s1 * s1 + s2 * s2 - coeff * s1 * s2;
        if (mag > best_mag) {
            best_mag = mag;
            best_freq = static_cast<float>(bin) * static_cast<float>(sample_rate) / static_cast<float>(n);
        }
    }
    return best_freq;
}

static void test_pcm_keylock_activates_when_prerequisites_met() {
    std::printf("test_pcm_keylock_activates_when_prerequisites_met...\n");
    auto pcm = make_tone(4800, 440.0f, 48000);
    Voice voice(48000, make_pcm_config(1, pcm.data(), pcm.size(), 1, 1, 128.0f, 132.0f));
    TEST_ASSERT(voice.is_key_lock_active(),
                "PCM + KEY_LOCK + valid BPMs activates effective Key-Lock");
    TEST_ASSERT(voice.get_grid_compensation_frames() > 0,
                "effective Key-Lock exposes positive grid compensation");
    TEST_ASSERT_EQ(voice.get_grid_compensation_frames(),
                   expected_grid_compensation(
                       voice.get_input_latency_frames(),
                       voice.get_output_latency_frames(),
                       128.0f, 132.0f),
                   "compensation is tempo-adjusted input latency + output latency");
}

static void test_pcm_keylock_inactive_for_rate_sync_and_sync_off() {
    std::printf("test_pcm_keylock_inactive_for_rate_sync_and_sync_off...\n");
    auto pcm = make_tone(1024, 440.0f, 48000);

    Voice rate(48000, make_pcm_config(2, pcm.data(), pcm.size(), 1, 0, 128.0f, 132.0f, 132.0f / 128.0f));
    TEST_ASSERT(!rate.is_key_lock_active(), "Rate Sync reports Key-Lock inactive");
    TEST_ASSERT_EQ(rate.get_grid_compensation_frames(), 0, "Rate Sync has zero compensation");

    // sync_mode 0 with unity rate models SYNC off / unsynced playback.
    Voice off(48000, make_pcm_config(3, pcm.data(), pcm.size(), 1, 0, 128.0f, 128.0f, 1.0f));
    TEST_ASSERT(!off.is_key_lock_active(), "SYNC-off style config reports Key-Lock inactive");
}

static void test_pcm_keylock_inactive_for_invalid_source_bpm() {
    std::printf("test_pcm_keylock_inactive_for_invalid_source_bpm...\n");
    auto pcm = make_tone(512, 440.0f, 48000);
    const float invalids[] = {0.0f, -10.0f, std::numeric_limits<float>::quiet_NaN()};
    for (size_t i = 0; i < 3; ++i) {
        Voice voice(48000, make_pcm_config(
            static_cast<sb_voice_id_t>(10 + i),
            pcm.data(), pcm.size(), 1, 1, invalids[i], 132.0f));
        TEST_ASSERT(!voice.is_key_lock_active(),
                    "invalid/missing source BPM must not activate Key-Lock");
    }
}

static void test_pcm_keylock_backend_unavailable_falls_back_to_rate_sync() {
    std::printf("test_pcm_keylock_backend_unavailable_falls_back_to_rate_sync...\n");
    auto pcm = make_tone(2048, 440.0f, 48000);
    Voice voice(48000, make_pcm_config(20, pcm.data(), pcm.size(), 1, 1, 128.0f, 140.0f));
    voice.set_signalsmith_available_for_test(false);
    TEST_ASSERT(!voice.is_key_lock_active(),
                "backend unavailable keeps effective Key-Lock inactive");
    TEST_ASSERT_EQ(voice.get_grid_compensation_frames(), 0,
                   "fallback exposes zero Key-Lock compensation");

    // Fallback must remain crash-free and still render via rate semantics.
    voice.schedule_start(0, 0);
    std::vector<float> out(256, 0.0f);
    voice.process(out.data(), 128, 0, 1);
    float energy = 0.0f;
    for (float s : out) energy += s * s;
    TEST_ASSERT(energy > 0.0f, "fallback Rate Sync still produces audio");
}

static void test_pcm_does_not_bypass_keylock_renderer() {
    std::printf("test_pcm_does_not_bypass_keylock_renderer...\n");
    // With Key-Lock, pitch must stay near 440 Hz at 128->140.
    // With Rate Sync, pitch scales by 140/128.
    constexpr uint32_t sr = 48000;
    auto pcm = make_tone(sr * 2, 440.0f, sr);

    Voice keylock(sr, make_pcm_config(30, pcm.data(), pcm.size(), 1, 1, 128.0f, 140.0f));
    TEST_ASSERT(keylock.is_key_lock_active(), "Key-Lock path is active for pitch probe");
    keylock.schedule_start(0, 0);

    Voice rate(sr, make_pcm_config(31, pcm.data(), pcm.size(), 1, 0, 128.0f, 140.0f, 140.0f / 128.0f));
    TEST_ASSERT(!rate.is_key_lock_active(), "Rate Sync path is inactive for Key-Lock");
    rate.schedule_start(0, 0);

    std::vector<float> kl_out(sr, 0.0f);
    std::vector<float> rate_out(sr, 0.0f);
    // Render enough callbacks to cover one second of output.
    const size_t block = 256;
    for (size_t frame = 0; frame + block <= sr; frame += block) {
        keylock.process(kl_out.data() + frame, block, static_cast<sb_frame_t>(frame), 1);
        rate.process(rate_out.data() + frame, block, static_cast<sb_frame_t>(frame), 1);
    }

    // Skip early transient / latency region for stable pitch estimate.
    const size_t skip = static_cast<size_t>(std::max(0, keylock.get_grid_compensation_frames())) + 2048;
    TEST_ASSERT(skip + 8192 < kl_out.size(), "pitch analysis window fits output");
    std::vector<float> kl_win(kl_out.begin() + static_cast<std::ptrdiff_t>(skip),
                              kl_out.begin() + static_cast<std::ptrdiff_t>(skip + 8192));
    std::vector<float> rate_win(rate_out.begin() + 2048, rate_out.begin() + 2048 + 8192);

    const float kl_freq = dominant_frequency(kl_win, sr);
    const float rate_freq = dominant_frequency(rate_win, sr);
    std::printf("    keylock_freq=%.2f rate_freq=%.2f\n", kl_freq, rate_freq);

    TEST_ASSERT(std::fabs(kl_freq - 440.0f) < 12.0f,
                "Key-Lock PCM preserves pitch near 440 Hz");
    TEST_ASSERT(std::fabs(rate_freq - 440.0f * (140.0f / 128.0f)) < 20.0f,
                "Rate Sync PCM shifts pitch with tempo");
    TEST_ASSERT(std::fabs(kl_freq - rate_freq) > 20.0f,
                "PCM Key-Lock path differs from Rate Sync pitch behavior");
}

static void test_keylock_scheduling_applies_compensation_once() {
    std::printf("test_keylock_scheduling_applies_compensation_once...\n");
    auto pcm = make_tone(4096, 440.0f, 48000);
    Voice voice(48000, make_pcm_config(40, pcm.data(), pcm.size(), 1, 1, 128.0f, 132.0f));
    TEST_ASSERT(voice.is_key_lock_active(), "Key-Lock active before schedule");
    const int compensation = voice.get_grid_compensation_frames();
    TEST_ASSERT(compensation > 0, "compensation is positive");

    const sb_frame_t musical_p = 20000;
    const sb_frame_t engine_now = 1000;
    voice.schedule_start(musical_p, engine_now);
    TEST_ASSERT_EQ(voice.requested_start_frame, musical_p,
                   "requested musical start remains P");
    TEST_ASSERT_EQ(voice.get_state(), SB_VOICE_SCHEDULED, "future compensated start is scheduled");

    // DSP start must be advanced by compensation exactly once.
    const sb_frame_t expected_dsp = musical_p - static_cast<sb_frame_t>(compensation);
    // Drive one process call before the DSP start so actual_start is set when due.
    std::vector<float> silent(64, 0.0f);
    voice.process(silent.data(), 64, engine_now, 1);
    TEST_ASSERT_EQ(voice.get_state(), SB_VOICE_SCHEDULED, "still scheduled before DSP start");

    voice.process(silent.data(), 64, expected_dsp, 1);
    TEST_ASSERT_EQ(voice.actual_start_frame, expected_dsp,
                   "actual DSP start is P - compensation");
    TEST_ASSERT_EQ(voice.actual_start_frame - voice.requested_start_frame,
                   -static_cast<sb_frame_t>(compensation),
                   "start skew equals -compensation");

    // Re-schedule must not accumulate compensation.
    voice.stop();
    voice.process(silent.data(), 1, expected_dsp + 64, 1);
    voice.schedule_start(musical_p, engine_now);
    voice.process(silent.data(), 64, expected_dsp, 1);
    TEST_ASSERT_EQ(voice.actual_start_frame, expected_dsp,
                   "reschedule applies compensation once, not cumulatively");
}

static void test_rate_sync_scheduling_unchanged() {
    std::printf("test_rate_sync_scheduling_unchanged...\n");
    auto pcm = make_tone(1024, 440.0f, 48000);
    Voice voice(48000, make_pcm_config(41, pcm.data(), pcm.size(), 1, 0, 128.0f, 132.0f, 132.0f / 128.0f));
    TEST_ASSERT(!voice.is_key_lock_active(), "Rate Sync inactive");
    const sb_frame_t musical_p = 5000;
    voice.schedule_start(musical_p, 0);
    std::vector<float> out(8, 0.0f);
    voice.process(out.data(), 8, musical_p, 1);
    TEST_ASSERT_EQ(voice.requested_start_frame, musical_p, "Rate Sync requested equals P");
    TEST_ASSERT_EQ(voice.actual_start_frame, musical_p, "Rate Sync actual equals P");
}

static void test_frame_zero_and_underflow_boundaries() {
    std::printf("test_frame_zero_and_underflow_boundaries...\n");
    auto pcm = make_tone(2048, 440.0f, 48000);
    Voice voice(48000, make_pcm_config(42, pcm.data(), pcm.size(), 1, 1, 128.0f, 132.0f));
    TEST_ASSERT(voice.is_key_lock_active(), "Key-Lock active for boundary cases");
    const int compensation = voice.get_grid_compensation_frames();
    TEST_ASSERT(compensation > 1, "compensation exceeds one frame");

    // Musical P = 0: cannot start before 0; DSP start clamps to 0.
    voice.schedule_start(0, 0);
    TEST_ASSERT_EQ(voice.requested_start_frame, 0, "frame-0 requested retained");
    std::vector<float> out(32, 0.0f);
    voice.process(out.data(), 32, 0, 1);
    TEST_ASSERT_EQ(voice.actual_start_frame, 0, "frame-0 DSP start clamps to 0");

    // Musical P < compensation: DSP start clamps to 0 (no unsigned wrap).
    Voice early(48000, make_pcm_config(43, pcm.data(), pcm.size(), 1, 1, 128.0f, 132.0f));
    const sb_frame_t small_p = static_cast<sb_frame_t>(compensation / 2);
    early.schedule_start(small_p, 0);
    TEST_ASSERT_EQ(early.requested_start_frame, small_p, "sub-compensation requested retained");
    early.process(out.data(), 32, 0, 1);
    TEST_ASSERT_EQ(early.actual_start_frame, 0,
                   "P < compensation clamps DSP start to 0 without wraparound");

    // Late schedule: pre-roll already past current engine frame.
    Voice late(48000, make_pcm_config(44, pcm.data(), pcm.size(), 1, 1, 128.0f, 132.0f));
    const sb_frame_t late_p = static_cast<sb_frame_t>(compensation + 10);
    const sb_frame_t now = static_cast<sb_frame_t>(compensation + 50);
    late.schedule_start(late_p, now);
    TEST_ASSERT_EQ(late.requested_start_frame, late_p, "late requested retained");
    late.process(out.data(), 32, now, 1);
    TEST_ASSERT_EQ(late.actual_start_frame, now,
                   "late pre-roll starts at current engine frame, no underflow");
}

static void test_stereo_pcm_keylock_into_mono_mix_does_not_crash() {
    std::printf("test_stereo_pcm_keylock_into_mono_mix_does_not_crash...\n");
    constexpr size_t stereo_frames = 48000;
    std::vector<float> stereo(stereo_frames * 2);
    for (size_t i = 0; i < stereo_frames; ++i) {
        stereo[i * 2] = 0.25f;
        stereo[i * 2 + 1] = -0.25f;
    }
    Voice voice(48000, make_pcm_config(60, stereo.data(), stereo_frames, 2, 1, 128.0f, 128.0f));
    TEST_ASSERT(voice.is_key_lock_active(), "stereo PCM Key-Lock activates");
    const int compensation = voice.get_grid_compensation_frames();
    voice.schedule_start(0, 0);
    std::vector<float> mono(256, 0.0f);
    float energy = 0.0f;
    sb_frame_t engine = 0;
    // Advance past Signalsmith startup latency so the mix is audibly non-zero.
    const size_t need = static_cast<size_t>(compensation) + 512;
    for (size_t produced = 0; produced < need; produced += 256) {
        std::fill(mono.begin(), mono.end(), 0.0f);
        voice.process(mono.data(), 256, engine, 1);
        engine += 256;
        for (float s : mono) energy += s * s;
    }
    TEST_ASSERT(energy > 0.0f, "stereo→mono Key-Lock mix produces audio without crash");
}

static void test_pcm_keylock_drains_latency_tail_before_idle() {
    std::printf("test_pcm_keylock_drains_latency_tail_before_idle...\n");
    constexpr size_t frames = 48000;  // 1 second at 48 kHz
    std::vector<float> pcm(frames, 0.5f);
    Voice voice(48000, make_pcm_config(61, pcm.data(), frames, 1, 1, 128.0f, 128.0f));
    TEST_ASSERT(voice.is_key_lock_active(), "Key-Lock active for drain probe");
    const int compensation = voice.get_grid_compensation_frames();
    TEST_ASSERT(compensation > 0, "compensation positive for drain probe");
    voice.schedule_start(0, 0);

    size_t produced = 0;
    std::vector<float> block(256, 0.0f);
    sb_frame_t engine = 0;
    while (voice.get_state() != SB_VOICE_IDLE && produced < frames + static_cast<size_t>(compensation) + 4096) {
        std::fill(block.begin(), block.end(), 0.0f);
        voice.process(block.data(), 256, engine, 1);
        engine += 256;
        produced += 256;
    }
    TEST_ASSERT_EQ(voice.get_state(), SB_VOICE_IDLE, "voice reaches IDLE after drain");
    TEST_ASSERT(produced >= frames + static_cast<size_t>(compensation),
                "output spans at least source duration plus latency drain");
}

static void test_large_callback_is_chunked_not_truncated() {
    std::printf("test_large_callback_is_chunked_not_truncated...\n");
    auto pcm = make_tone(96000, 440.0f, 48000);
    Voice voice(48000, make_pcm_config(63, pcm.data(), pcm.size(), 1, 1, 128.0f, 128.0f));
    TEST_ASSERT(voice.is_key_lock_active(), "Key-Lock active for large callback");
    voice.schedule_start(0, 0);
    std::vector<float> out(8192, 0.0f);
    voice.process(out.data(), 8192, 0, 1);
    float energy = 0.0f;
    for (float s : out) energy += s * s;
    // Even inside startup latency, chunking must advance DSP; after enough
    // large callbacks the buffer should contain energy. Drive past latency.
    const int compensation = voice.get_grid_compensation_frames();
    sb_frame_t engine = 8192;
    for (int i = 0; i < (compensation / 8192) + 2; ++i) {
        std::fill(out.begin(), out.end(), 0.0f);
        voice.process(out.data(), 8192, engine, 1);
        engine += 8192;
        for (float s : out) energy += s * s;
    }
    TEST_ASSERT(energy > 0.0f, "callbacks larger than scratch chunk still produce audio");
    TEST_ASSERT(voice.get_state() == SB_VOICE_PLAYING || voice.get_state() == SB_VOICE_IDLE,
                "large chunked callback leaves voice in a valid state");
}

static void test_source_bpm_update_preserves_playing_keylock() {
    std::printf("test_source_bpm_update_preserves_playing_keylock...\n");
    auto pcm = make_tone(48000, 440.0f, 48000);
    Voice voice(48000, make_pcm_config(62, pcm.data(), pcm.size(), 1, 1, 128.0f, 132.0f));
    TEST_ASSERT(voice.is_key_lock_active(), "Key-Lock active before BPM update");
    const int compensation = voice.get_grid_compensation_frames();
    voice.schedule_start(0, 0);
    std::vector<float> out(256, 0.0f);
    sb_frame_t engine = 0;
    for (size_t produced = 0; produced < static_cast<size_t>(compensation) + 256; produced += 256) {
        voice.process(out.data(), 256, engine, 1);
        engine += 256;
    }
    TEST_ASSERT_EQ(voice.get_state(), SB_VOICE_PLAYING, "playing before BPM update");
    voice.set_source_bpm(130.0f);
    TEST_ASSERT(voice.is_key_lock_active(), "Key-Lock remains effective after BPM update");
    std::fill(out.begin(), out.end(), 0.0f);
    voice.process(out.data(), 256, engine, 1);
    TEST_ASSERT_EQ(voice.get_state(), SB_VOICE_PLAYING, "still playing after source BPM update");
    float energy = 0.0f;
    for (float s : out) energy += s * s;
    TEST_ASSERT(energy > 0.0f, "audio continues after in-place source BPM update");
}

static void test_snapshot_requested_actual_latency_consistency() {
    std::printf("test_snapshot_requested_actual_latency_consistency...\n");
    sb_engine_t engine = nullptr;
    sb_engine_config_t eng = {};
    eng.sample_rate = 48000;
    eng.buffer_frames = 64;
    eng.output_channels = 2;
    eng.input_channels = 0;
    TEST_ASSERT_EQ(sb_engine_open(&eng, &engine), SB_OK, "engine opens");
    TEST_ASSERT_EQ(sb_engine_start(engine), SB_OK, "engine starts");

    auto pcm = make_tone(4096, 440.0f, 48000);
    sb_voice_config_t cfg = make_pcm_config(50, pcm.data(), pcm.size(), 1, 1, 128.0f, 132.0f);
    sb_voice_id_t id = 0;
    TEST_ASSERT_EQ(sb_voice_create(engine, &cfg, &id), SB_OK, "PCM Key-Lock voice create");

    sb_snapshot_t snap = {};
    TEST_ASSERT_EQ(sb_engine_snapshot(engine, &snap), SB_OK, "snapshot before schedule");
    TEST_ASSERT(snap.voice_key_lock_active[0], "snapshot reports effective Key-Lock active");
    TEST_ASSERT(snap.voice_grid_compensation_frames[0] > 0, "snapshot compensation > 0");
    TEST_ASSERT_EQ(snap.voice_grid_compensation_frames[0],
                   expected_grid_compensation(
                       snap.voice_input_latency_frames[0],
                       snap.voice_output_latency_frames[0],
                       128.0f, 132.0f),
                   "snapshot compensation matches tempo-adjusted latency model");
    TEST_ASSERT_EQ(snap.voice_sync_modes[0], 1, "snapshot retains requested sync mode");

    const sb_frame_t now = snap.engine_frame;
    const int compensation = snap.voice_grid_compensation_frames[0];
    const sb_frame_t musical_p = now + static_cast<sb_frame_t>(compensation) + 2048;
    TEST_ASSERT_EQ(sb_voice_schedule_start(engine, id, musical_p), SB_OK, "schedule musical P");

    // Advance far enough for the compensated DSP start to land (~2048 frames).
    std::this_thread::sleep_for(std::chrono::milliseconds(200));
    TEST_ASSERT_EQ(sb_engine_snapshot(engine, &snap), SB_OK, "snapshot after start");
    TEST_ASSERT_EQ(snap.requested_start_frame[0], musical_p, "snapshot requested is musical P");
    TEST_ASSERT_EQ(snap.actual_start_frame[0],
                   musical_p - static_cast<sb_frame_t>(compensation),
                   "snapshot actual DSP start is P - compensation");
    TEST_ASSERT_EQ(snap.start_skew_frames[0], -compensation,
                   "snapshot skew equals -compensation");

    // Second voice shares the same engine clock (no private clock).
    sb_voice_config_t cfg2 = make_pcm_config(51, pcm.data(), pcm.size(), 1, 1, 140.0f, 132.0f);
    sb_voice_id_t id2 = 0;
    TEST_ASSERT_EQ(sb_voice_create(engine, &cfg2, &id2), SB_OK, "second Key-Lock voice create");
    TEST_ASSERT_EQ(sb_engine_snapshot(engine, &snap), SB_OK, "snapshot with two voices");
    TEST_ASSERT(snap.voice_key_lock_active[0] && snap.voice_key_lock_active[1],
                "both voices report effective Key-Lock");
    TEST_ASSERT_EQ(snap.total_voice_count, 2u, "two voices on shared engine");

    sb_engine_stop(engine);
    sb_engine_close(engine);
}

int main() {
    std::printf("=== PCM Key-Lock Tests (#1279) ===\n\n");
    test_pcm_keylock_activates_when_prerequisites_met();
    test_pcm_keylock_inactive_for_rate_sync_and_sync_off();
    test_pcm_keylock_inactive_for_invalid_source_bpm();
    test_pcm_keylock_backend_unavailable_falls_back_to_rate_sync();
    test_pcm_does_not_bypass_keylock_renderer();
    test_keylock_scheduling_applies_compensation_once();
    test_rate_sync_scheduling_unchanged();
    test_frame_zero_and_underflow_boundaries();
    test_stereo_pcm_keylock_into_mono_mix_does_not_crash();
    test_pcm_keylock_drains_latency_tail_before_idle();
    test_source_bpm_update_preserves_playing_keylock();
    test_large_callback_is_chunked_not_truncated();
    test_snapshot_requested_actual_latency_consistency();
    std::printf("\n=== Results ===\nPassed: %d\nFailed: %d\n", tests_passed, tests_failed);
    return tests_failed > 0 ? 1 : 0;
}
