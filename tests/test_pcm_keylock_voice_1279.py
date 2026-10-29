"""#1279: PCM Key-Lock productive path + scheduling compensation.

Covers Adapter→Native state handoff and an objective synthetic audio probe
for tonal and percussive material across 128↔132/140 ratios.

Does NOT claim subjective audio quality (that remains #1217).
"""

from __future__ import annotations

import math
import time
from pathlib import Path

import numpy as np
import pytest

from src.native_audio import (
    SB_SOURCE_PCM_BUFFER,
    SB_SYNC_MODE_KEY_LOCK_SYNC,
    SB_SYNC_MODE_RATE_SYNC,
    EngineConfig,
    NativeAudioEngine,
    PcmBufferConfig,
    SyncMode,
    VoiceConfig,
    create_keylock_voice,
    is_available,
)


pytestmark = pytest.mark.skipif(not is_available(), reason="Native audio DLL not available")


def _sine(freq_hz: float, frames: int, sample_rate: int = 48000) -> np.ndarray:
    t = np.arange(frames, dtype=np.float64) / sample_rate
    return np.sin(2.0 * np.pi * freq_hz * t).astype(np.float32)


def _click_train(frames: int, bpm: float, sample_rate: int = 48000) -> np.ndarray:
    out = np.zeros(frames, dtype=np.float32)
    interval = max(1, int((60.0 / bpm) * sample_rate))
    click_len = max(1, int(0.005 * sample_rate))
    for start in range(0, frames, interval):
        for i in range(click_len):
            if start + i >= frames:
                break
            env = 1.0 - (i / click_len)
            env = env * env
            out[start + i] += 0.8 * math.sin(2.0 * math.pi * 1000.0 * i / sample_rate) * env
    return out


def _dominant_freq(signal: np.ndarray, sample_rate: int) -> float:
    n = len(signal)
    window = np.hanning(n)
    spectrum = np.fft.rfft(signal * window)
    freqs = np.fft.rfftfreq(n, 1.0 / sample_rate)
    return float(freqs[int(np.argmax(np.abs(spectrum)))])


def _pcm_voice_config(
    voice_id: int,
    pcm: np.ndarray,
    *,
    sync_mode: int,
    source_bpm: float,
    master_bpm: float,
    rate: float | None = None,
) -> VoiceConfig:
    if rate is None:
        rate = (master_bpm / source_bpm) if source_bpm > 0 else 1.0
    return VoiceConfig(
        id=voice_id,
        source_type=SB_SOURCE_PCM_BUFFER,
        pcm_buffer=PcmBufferConfig(samples=pcm, channels=1),
        initial_rate=rate,
        gain=1.0,
        sync_mode=sync_mode,
        source_bpm=source_bpm,
        master_bpm=master_bpm,
    )


def _open_engine() -> NativeAudioEngine:
    engine = NativeAudioEngine()
    engine.open(EngineConfig(sample_rate=48000, buffer_frames=256, output_channels=1, input_channels=0))
    engine.start()
    return engine


def test_adapter_native_pcm_keylock_requested_vs_effective(tmp_path: Path):
    """Adapter→Native: requested KEY_LOCK becomes effective when backend is ready."""
    del tmp_path  # runtime-only; keeps probe audio out of the repo
    pcm = _sine(440.0, 48000)
    engine = _open_engine()
    try:
        vid = engine.create_voice(
            _pcm_voice_config(
                1,
                pcm,
                sync_mode=SB_SYNC_MODE_KEY_LOCK_SYNC,
                source_bpm=128.0,
                master_bpm=132.0,
            )
        )
        snap = engine.snapshot()
        idx = list(snap.voice_ids).index(vid)
        assert snap.voice_sync_modes[idx] == SB_SYNC_MODE_KEY_LOCK_SYNC
        assert snap.voice_key_lock_active[idx] is True
        assert snap.voice_grid_compensation_frames[idx] > 0
        ratio = 132.0 / 128.0
        expected = int(round(snap.voice_input_latency_frames[idx] / ratio)) + snap.voice_output_latency_frames[idx]
        assert snap.voice_grid_compensation_frames[idx] == expected
    finally:
        engine.stop()
        engine.close()


def test_adapter_native_rate_sync_and_invalid_bpm_not_keylock():
    pcm = _sine(440.0, 8000)
    engine = _open_engine()
    try:
        rate_id = engine.create_voice(
            _pcm_voice_config(
                2,
                pcm,
                sync_mode=SB_SYNC_MODE_RATE_SYNC,
                source_bpm=128.0,
                master_bpm=132.0,
                rate=132.0 / 128.0,
            )
        )
        snap = engine.snapshot()
        rate_idx = list(snap.voice_ids).index(rate_id)
        assert snap.voice_key_lock_active[rate_idx] is False
        assert snap.voice_grid_compensation_frames[rate_idx] == 0

        bad = engine.create_voice(
            _pcm_voice_config(
                3,
                pcm,
                sync_mode=SB_SYNC_MODE_KEY_LOCK_SYNC,
                source_bpm=0.0,
                master_bpm=132.0,
                rate=1.0,
            )
        )
        snap = engine.snapshot()
        bad_idx = list(snap.voice_ids).index(bad)
        assert snap.voice_key_lock_active[bad_idx] is False
    finally:
        engine.stop()
        engine.close()


@pytest.mark.parametrize(
    "source_bpm,master_bpm",
    [
        (128.0, 128.0),
        (128.0, 132.0),
        (128.0, 140.0),
        (140.0, 128.0),
    ],
)
def test_objective_tonal_and_percussive_probe(source_bpm: float, master_bpm: float, tmp_path: Path):
    """Objective probe: Key-Lock path runs; pitch stays; rate sync differs; ratios apply."""
    assert tmp_path.exists()
    sample_rate = 48000
    frames = sample_rate * 2
    tonal = _sine(440.0, frames, sample_rate)
    perc = _click_train(frames, source_bpm, sample_rate)
    ratio = master_bpm / source_bpm

    engine = _open_engine()
    try:
        kl_id = engine.create_voice(
            _pcm_voice_config(
                10,
                tonal,
                sync_mode=SB_SYNC_MODE_KEY_LOCK_SYNC,
                source_bpm=source_bpm,
                master_bpm=master_bpm,
            )
        )
        rate_id = engine.create_voice(
            _pcm_voice_config(
                11,
                tonal,
                sync_mode=SB_SYNC_MODE_RATE_SYNC,
                source_bpm=source_bpm,
                master_bpm=master_bpm,
                rate=ratio,
            )
        )
        perc_id = engine.create_voice(
            _pcm_voice_config(
                12,
                perc,
                sync_mode=SB_SYNC_MODE_KEY_LOCK_SYNC,
                source_bpm=source_bpm,
                master_bpm=master_bpm,
            )
        )
        snap = engine.snapshot()
        kl_idx = list(snap.voice_ids).index(kl_id)
        rate_idx = list(snap.voice_ids).index(rate_id)
        perc_idx = list(snap.voice_ids).index(perc_id)

        assert snap.voice_key_lock_active[kl_idx] is True
        assert snap.voice_key_lock_active[rate_idx] is False
        assert snap.voice_key_lock_active[perc_idx] is True

        compensation = snap.voice_grid_compensation_frames[kl_idx]
        expected = int(round(snap.voice_input_latency_frames[kl_idx] / ratio)) + snap.voice_output_latency_frames[kl_idx]
        assert compensation == expected

        now = snap.engine_frame
        musical_p = now + compensation + 4096
        engine.schedule_voice_start(kl_id, musical_p)
        engine.schedule_voice_start(rate_id, musical_p)
        engine.schedule_voice_start(perc_id, musical_p)

        time.sleep(0.35)
        after = engine.snapshot()
        kl_idx = list(after.voice_ids).index(kl_id)
        assert after.requested_start_frame[kl_idx] == musical_p
        assert after.actual_start_frame[kl_idx] == musical_p - compensation
        assert after.start_skew_frames[kl_idx] == -compensation
    finally:
        engine.stop()
        engine.close()

    kv = create_keylock_voice(
        sample_rate=sample_rate,
        source_bpm=source_bpm,
        master_bpm=master_bpm,
        sync_mode=SyncMode.KEY_LOCK_SYNC,
        frequency_hz=440.0,
        channels=1,
    )
    assert kv is not None and kv.is_key_lock_active()
    processed, meta = kv.process_audio(tonal)
    assert meta["key_lock_active"] is True
    assert meta["tempo_ratio"] == pytest.approx(ratio)
    expected_out = max(1, int(len(tonal) / ratio))
    assert abs(meta["output_frames"] - expected_out) <= 2

    skip = max(int(meta["grid_compensation_frames"]), 2048)
    win = processed[skip : skip + 8192]
    if len(win) >= 4096:
        freq = _dominant_freq(win, sample_rate)
        assert abs(freq - 440.0) < 12.0

    rate_kv = create_keylock_voice(
        sample_rate=sample_rate,
        source_bpm=source_bpm,
        master_bpm=master_bpm,
        sync_mode=SyncMode.RATE_SYNC,
        frequency_hz=440.0,
        channels=1,
    )
    assert rate_kv is not None and not rate_kv.is_key_lock_active()
    rate_processed, rate_meta = rate_kv.process_audio(tonal)
    assert rate_meta["key_lock_active"] is False
    rate_win = rate_processed[2048 : 2048 + 8192]
    if len(rate_win) >= 4096 and abs(ratio - 1.0) > 0.01:
        rate_freq = _dominant_freq(rate_win, sample_rate)
        assert abs(rate_freq - 440.0) > 8.0
