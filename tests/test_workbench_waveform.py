from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from src.workbench_waveform import (
    clamp_cue_start_ms,
    compute_waveform_envelope,
    cue_marker_x,
    cue_ms_from_x,
    read_audio_duration_ms,
)
from tests.audio_fixtures import write_sine_wav


def test_compute_waveform_envelope_missing_file(tmp_path: Path):
    assert compute_waveform_envelope(tmp_path / "missing.wav") == []


def test_compute_waveform_envelope_rejects_non_positive_max_points(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.1, frequency_hz=440.0)
    with pytest.raises(ValueError):
        compute_waveform_envelope(wav, max_points=0)


def test_compute_waveform_envelope_returns_normalized_peaks(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.2, frequency_hz=440.0)
    envelope = compute_waveform_envelope(wav, max_points=32)
    assert envelope
    assert len(envelope) <= 32
    assert max(envelope) <= 1.0 + 1e-6
    assert min(envelope) >= 0.0


def test_compute_waveform_envelope_downsamples_long_audio(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "long.wav", duration_sec=2.0, frequency_hz=220.0)
    envelope = compute_waveform_envelope(wav, max_points=50)
    assert len(envelope) == 50


def test_compute_waveform_envelope_handles_silence(tmp_path: Path):
    path = tmp_path / "silent.wav"
    write_sine_wav(path, duration_sec=0.1, frequency_hz=440.0, amplitude=0.0)
    envelope = compute_waveform_envelope(path, max_points=10)
    assert envelope
    assert max(envelope) == pytest.approx(0.0)


def test_cue_marker_x_at_zero():
    assert cue_marker_x(0, duration_ms=1000, width=200) == 0


def test_cue_marker_x_at_midpoint():
    assert cue_marker_x(500, duration_ms=1000, width=200) == 100


def test_clamp_cue_start_ms_limits_to_duration():
    assert clamp_cue_start_ms(1500, duration_ms=1000) == 999
    assert clamp_cue_start_ms(-5, duration_ms=1000) == 0


def test_read_audio_duration_ms_from_synthetic_wav(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.2, frequency_hz=440.0)
    duration_ms = read_audio_duration_ms(wav)
    assert duration_ms is not None
    assert 180 <= duration_ms <= 220


def test_cue_ms_from_x_at_zero():
    assert cue_ms_from_x(0, width=200, duration_ms=1000) == 0


def test_cue_ms_from_x_at_midpoint():
    assert cue_ms_from_x(100, width=200, duration_ms=1000) == 500


def test_cue_ms_from_x_clamps_negative_x():
    assert cue_ms_from_x(-10, width=200, duration_ms=1000) == 0


def test_cue_ms_from_x_clamps_beyond_width():
    assert cue_ms_from_x(500, width=200, duration_ms=1000) == 999


def test_cue_ms_from_x_handles_zero_width_or_duration():
    assert cue_ms_from_x(50, width=0, duration_ms=1000) == 0
    assert cue_ms_from_x(50, width=200, duration_ms=0) == 0


def test_cue_ms_from_x_roundtrip_with_marker_x():
    duration_ms = 1000
    width = 240
    for x in (0, 60, 120, 180, 239):
        cue_ms = cue_ms_from_x(x, width, duration_ms)
        marker = cue_marker_x(cue_ms, duration_ms, width)
        assert marker is not None
        assert abs(marker - x) <= 1
