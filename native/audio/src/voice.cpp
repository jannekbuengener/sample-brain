// voice.cpp - Voice implementation
#include "voice.h"
#include "keylock_voice.h"
#include <cmath>
#include <algorithm>
#include <limits>

namespace {
constexpr double kPi = 3.141592653589793238462643383279502884;
constexpr size_t kKeyLockMaxCallbackFrames = 4096;
constexpr uint32_t kKeyLockMaxMixChannels = 8;
}

// KeyLockVoiceImpl implementation
class Voice::KeyLockVoiceImpl {
public:
    samplebrain::KeyLockVoice kv;
    bool prepared = false;
};

bool Voice::bpm_is_syncable(float bpm) {
    return std::isfinite(bpm) && bpm > 0.0f;
}

bool Voice::validate_config(const sb_voice_config_t& config) {
    if (!std::isfinite(config.initial_rate) || config.initial_rate <= 0.0f ||
        config.initial_rate > 10.0f || !std::isfinite(config.gain)) {
        return false;
    }

    if (config.source.type == SB_SOURCE_SYNTHETIC_CLICK) {
        return true;
    }
    if (config.source.type != SB_SOURCE_PCM_BUFFER) {
        return false;
    }

    const sb_pcm_buffer_config_t& pcm = config.source.pcm_buffer;
    if (!pcm.data || pcm.frame_count == 0 || (pcm.channels != 1 && pcm.channels != 2)) {
        return false;
    }
    if (pcm.frame_count > std::numeric_limits<size_t>::max() / pcm.channels) {
        return false;
    }

    const size_t sample_count = static_cast<size_t>(pcm.frame_count) * pcm.channels;
    if (sample_count > std::vector<float>().max_size()) {
        return false;
    }
    for (size_t i = 0; i < sample_count; ++i) {
        if (!std::isfinite(pcm.data[i])) {
            return false;
        }
    }
    return true;
}

Voice::Voice(uint32_t sample_rate_, const sb_voice_config_t& config)
    : id(config.id), rate(config.initial_rate), gain(config.gain), sample_rate(sample_rate_),
      source_type(config.source.type) {
    if (config.source.type == SB_SOURCE_SYNTHETIC_CLICK) {
        click_config = config.source.synthetic_click;
        generate_click_samples(config.source.synthetic_click);
    } else if (config.source.type == SB_SOURCE_PCM_BUFFER) {
        const sb_pcm_buffer_config_t& pcm = config.source.pcm_buffer;
        const size_t sample_count = static_cast<size_t>(pcm.frame_count) * pcm.channels;
        pcm_samples.assign(pcm.data, pcm.data + sample_count);
        pcm_frame_count = pcm.frame_count;
        pcm_channels = pcm.channels;
    }

    sync_mode = config.sync_mode;
    source_bpm = config.source_bpm;
    master_bpm = config.master_bpm;

    // Prepare Key-Lock on the control / construction path (never in the callback).
    configure_key_lock();
}

Voice::~Voice() {
    if (kl_voice) {
        delete kl_voice;
        kl_voice = nullptr;
    }
}

void Voice::generate_click_samples(const sb_synthetic_click_config_t& config) {
    source_click_interval_frames = (60.0 / config.bpm) * sample_rate;
    click_interval_frames = source_click_interval_frames / rate;

    size_t click_samples_count = static_cast<size_t>(config.duration_ms / 1000.0 * sample_rate);
    click_samples_count = std::max<size_t>(1, click_samples_count);
    click_length = click_samples_count;

    click_samples.resize(click_length);
    for (size_t i = 0; i < click_length; ++i) {
        double t = static_cast<double>(i) / sample_rate;
        double envelope = 1.0 - t / (config.duration_ms / 1000.0);
        envelope = std::max(0.0, envelope * envelope);
        click_samples[i] = config.amplitude * std::sin(2.0 * kPi * config.frequency_hz * t) * envelope;
    }
}

void Voice::configure_key_lock() {
    if (kl_voice) {
        delete kl_voice;
        kl_voice = nullptr;
    }
    keylock_arm_on_play_ = false;
    keylock_mix_scratch_.clear();

    // Effective Key-Lock requires requested mode + syncable BPMs + PCM source + backend.
    if (sync_mode != 1) {
        return;
    }
    if (source_type != SB_SOURCE_PCM_BUFFER || pcm_samples.empty() || pcm_frame_count == 0) {
        return;
    }
    if (!bpm_is_syncable(source_bpm) || !bpm_is_syncable(master_bpm)) {
        return;
    }

    kl_voice = new KeyLockVoiceImpl();
    samplebrain::KeyLockVoiceConfig kv_config;
    kv_config.id = id;
    kv_config.sample_rate = static_cast<int>(sample_rate);
    kv_config.channels = static_cast<int>(pcm_channels);
    kv_config.source_bpm = source_bpm;
    kv_config.master_bpm = master_bpm;
    kv_config.sync_mode = samplebrain::SyncMode::KEY_LOCK_SYNC;
    kv_config.gain = gain;
    kv_config.signalsmith_available = signalsmith_available_;
    kv_config.load_synthetic_source = false;

    if (!kl_voice->kv.init(kv_config)) {
        delete kl_voice;
        kl_voice = nullptr;
        return;
    }

    kl_voice->kv.set_pcm_source(pcm_samples.data(), static_cast<size_t>(pcm_frame_count),
                                static_cast<int>(pcm_channels));
    kl_voice->kv.prepare_process_capacity(kKeyLockMaxCallbackFrames, 4.0f);
    // Scratch covers one max chunk across the largest supported engine channel count.
    keylock_mix_scratch_.assign(
        kKeyLockMaxCallbackFrames * static_cast<size_t>(kKeyLockMaxMixChannels), 0.0f);
    kl_voice->prepared = true;

    if (!kl_voice->kv.is_key_lock_active()) {
        // Honest fallback to Rate Sync semantics for PCM rendering.
        rate = master_bpm / source_bpm;
    }
}

void Voice::set_signalsmith_available_for_test(bool available) {
    signalsmith_available_ = available;
    configure_key_lock();
}

void Voice::set_sync_mode(int mode) {
    const sb_voice_state_t prior = state.load(std::memory_order_acquire);
    const bool was_audible =
        prior == SB_VOICE_PLAYING || prior == SB_VOICE_SCHEDULED;
    sync_mode = mode;
    configure_key_lock();
    if (was_audible && is_key_lock_active() && kl_voice) {
        // Re-arm the replacement DSP without dropping the outer voice state.
        if (prior == SB_VOICE_PLAYING) {
            kl_voice->kv.schedule_start(0);
            keylock_arm_on_play_ = false;
        } else {
            keylock_arm_on_play_ = true;
        }
    }
}

void Voice::set_source_bpm(float bpm) {
    source_bpm = bpm;
    if (sync_mode == 1 && kl_voice && kl_voice->prepared &&
        bpm_is_syncable(source_bpm) && bpm_is_syncable(master_bpm)) {
        // Update the live DSP instance in place — do not tear down mid-playback.
        kl_voice->kv.set_source_bpm(source_bpm);
        kl_voice->kv.set_tempo_ratio(master_bpm / source_bpm);
        if (!is_key_lock_active()) {
            rate = master_bpm / source_bpm;
        }
        return;
    }
    configure_key_lock();
    if (!is_key_lock_active() && sync_mode == 1 &&
        bpm_is_syncable(source_bpm) && bpm_is_syncable(master_bpm)) {
        rate = master_bpm / source_bpm;
    }
}

void Voice::set_master_bpm(float bpm) {
    master_bpm = bpm;
    if (kl_voice && kl_voice->prepared &&
        bpm_is_syncable(source_bpm) && bpm_is_syncable(master_bpm)) {
        kl_voice->kv.set_master_bpm(bpm);
        kl_voice->kv.set_tempo_ratio(master_bpm / source_bpm);
        if (!is_key_lock_active() && sync_mode == 1) {
            rate = master_bpm / source_bpm;
        }
        return;
    }
    configure_key_lock();
    if (sync_mode == 1 && bpm_is_syncable(source_bpm) && bpm_is_syncable(master_bpm)) {
        rate = master_bpm / source_bpm;
    }
}

void Voice::schedule_start(sb_frame_t frame, sb_frame_t current_engine_frame) {
    requested_start_frame = frame;
    pcm_position = 0.0;
    keylock_arm_on_play_ = is_key_lock_active();

    // Musical target P is `frame`. Effective Key-Lock advances DSP start by
    // input+output latency exactly once so audible output lands on P.
    sb_frame_t dsp_frame = frame;
    if (is_key_lock_active()) {
        const int compensation = get_grid_compensation_frames();
        if (compensation > 0) {
            if (frame >= static_cast<sb_frame_t>(compensation)) {
                dsp_frame = frame - static_cast<sb_frame_t>(compensation);
            } else {
                // P < compensation / frame-0: clamp, never unsigned wrap.
                dsp_frame = 0;
            }
        }
    }

    if (dsp_frame < current_engine_frame) {
        // Pre-roll already past: start at the authoritative current frame.
        scheduled_frame = current_engine_frame;
        state.store(SB_VOICE_PLAYING, std::memory_order_release);
        actual_start_frame = current_engine_frame;
        next_click_frame = current_engine_frame + static_cast<sb_frame_t>(click_interval_frames);
        if (keylock_arm_on_play_ && kl_voice) {
            kl_voice->kv.schedule_start(0);
            keylock_arm_on_play_ = false;
        }
    } else {
        scheduled_frame = dsp_frame;
        state.store(SB_VOICE_SCHEDULED, std::memory_order_release);
        next_click_frame = frame + static_cast<sb_frame_t>(click_interval_frames);
    }
}

void Voice::stop() {
    state.store(SB_VOICE_STOPPING, std::memory_order_release);
}

void Voice::set_rate(float new_rate) {
    rate = new_rate;
    if (source_click_interval_frames > 0.0) {
        click_interval_frames = source_click_interval_frames / rate;
    }
}

void Voice::process(float* output, size_t num_frames, sb_frame_t engine_frame, size_t output_channels) {
    sb_voice_state_t current_state = state.load(std::memory_order_acquire);
    size_t render_offset = 0;

    if (current_state == SB_VOICE_SCHEDULED) {
        const sb_frame_t buffer_end = engine_frame + static_cast<sb_frame_t>(num_frames);
        if (scheduled_frame < buffer_end) {
            state.store(SB_VOICE_PLAYING, std::memory_order_release);
            actual_start_frame = scheduled_frame;
            if (scheduled_frame > engine_frame) {
                render_offset = static_cast<size_t>(scheduled_frame - engine_frame);
            }
            current_state = SB_VOICE_PLAYING;
            if (keylock_arm_on_play_ && kl_voice && is_key_lock_active()) {
                kl_voice->kv.schedule_start(0);
                keylock_arm_on_play_ = false;
            }
        }
    }

    if (current_state != SB_VOICE_PLAYING) {
        if (current_state == SB_VOICE_STOPPING) {
            state.store(SB_VOICE_IDLE, std::memory_order_release);
        }
        return;
    }

    if (source_type == SB_SOURCE_PCM_BUFFER) {
        if (is_key_lock_active() && kl_voice && kl_voice->prepared) {
            render_pcm_keylock(output, render_offset, num_frames - render_offset, output_channels);
            if (kl_voice->kv.get_state() == SB_VOICE_IDLE) {
                state.store(SB_VOICE_IDLE, std::memory_order_release);
            }
        } else {
            render_pcm(output, render_offset, num_frames - render_offset, output_channels);
        }
    } else if (sync_mode == 1) {
        // Legacy synthetic KEY_LOCK path (non-PCM). Keep offline/synthetic behavior
        // without introducing PCM callback lazy-init allocations.
        if (!kl_voice) {
            // Synthetic Key-Lock remains best-effort; PCM is the productive path.
            render_click(output, 0, num_frames, engine_frame, output_channels);
        } else if (kl_voice->prepared && is_key_lock_active()) {
            render_pcm_keylock(output, render_offset, num_frames - render_offset, output_channels);
        } else {
            render_click(output, 0, num_frames, engine_frame, output_channels);
        }
    } else {
        render_click(output, 0, num_frames, engine_frame, output_channels);
    }
}

void Voice::render_pcm_keylock(float* output, size_t offset, size_t num_frames,
                               size_t output_channels) {
    if (!kl_voice || num_frames == 0 || output_channels == 0) {
        return;
    }
    if (output_channels > kKeyLockMaxMixChannels) {
        // Control-path scratch is sized for the supported mix width; fail closed.
        return;
    }
    const size_t max_chunk_frames = keylock_mix_scratch_.size() / output_channels;
    if (max_chunk_frames == 0) {
        return;
    }
    const size_t chunk_limit = (std::min)(max_chunk_frames, kKeyLockMaxCallbackFrames);

    float* scratch = keylock_mix_scratch_.data();
    size_t frames_done = 0;
    while (frames_done < num_frames) {
        const size_t chunk = (std::min)(chunk_limit, num_frames - frames_done);
        kl_voice->kv.process(scratch, chunk, output_channels);
        const size_t sample_count = chunk * output_channels;
        const size_t out_base = (offset + frames_done) * output_channels;
        for (size_t i = 0; i < sample_count; ++i) {
            output[out_base + i] += scratch[i];
        }
        frames_done += chunk;
        if (kl_voice->kv.get_state() == SB_VOICE_IDLE) {
            break;
        }
    }
}

void Voice::render_pcm(float* output, size_t offset, size_t num_frames,
                       size_t output_channels) {
    for (size_t output_frame = 0; output_frame < num_frames; ++output_frame) {
        const uint64_t source_frame = static_cast<uint64_t>(pcm_position);
        if (source_frame >= pcm_frame_count) {
            state.store(SB_VOICE_IDLE, std::memory_order_release);
            return;
        }

        const size_t source_base = static_cast<size_t>(source_frame) * pcm_channels;
        const size_t output_base = (offset + output_frame) * output_channels;
        for (size_t channel = 0; channel < output_channels; ++channel) {
            const size_t source_channel = pcm_channels == 1 ? 0 : std::min<size_t>(channel, 1);
            output[output_base + channel] += gain * pcm_samples[source_base + source_channel];
        }
        pcm_position += static_cast<double>(rate);
    }

    if (pcm_position >= static_cast<double>(pcm_frame_count)) {
        state.store(SB_VOICE_IDLE, std::memory_order_release);
    }
}

bool Voice::is_key_lock_active() const {
    return kl_voice && kl_voice->prepared && kl_voice->kv.is_key_lock_active();
}

int Voice::get_input_latency_frames() const {
    return is_key_lock_active() ? kl_voice->kv.get_input_latency_frames() : 0;
}

int Voice::get_output_latency_frames() const {
    return is_key_lock_active() ? kl_voice->kv.get_output_latency_frames() : 0;
}

int Voice::get_grid_compensation_frames() const {
    return is_key_lock_active() ? kl_voice->kv.get_effective_grid_compensation_frames() : 0;
}

void Voice::render_click(float* output, size_t offset, size_t num_frames,
                         sb_frame_t engine_frame, size_t output_channels) {
    if (click_samples.empty() || click_interval_frames <= 0) return;

    sb_frame_t frame = next_click_frame;
    while (frame < engine_frame + static_cast<sb_frame_t>(num_frames)) {
        if (frame >= engine_frame) {
            size_t pos = offset + static_cast<size_t>(frame - engine_frame);
            if (pos < num_frames) {
                rendered_click_count.fetch_add(1, std::memory_order_relaxed);
                last_rendered_click_engine_frame.store(frame, std::memory_order_release);

                for (size_t ch = 0; ch < output_channels; ++ch) {
                    for (size_t i = 0; i < click_length && (pos + i) < num_frames; ++i) {
                        output[(pos + i) * output_channels + ch] += gain * click_samples[i];
                    }
                }
            }
        }
        frame += static_cast<sb_frame_t>(click_interval_frames);
    }

    next_click_frame = frame;
}
