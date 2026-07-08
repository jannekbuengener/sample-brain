from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from src.workbench_waveform import (
    attack_marker_x,
    clamp_cue_start_ms,
    compute_waveform_envelope,
    cue_marker_x,
    cue_ms_from_x,
    loop_region_x,
    normalize_loop_bounds,
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


def test_normalize_loop_bounds_requires_both_values():
    assert normalize_loop_bounds(None, 500, 1000) is None
    assert normalize_loop_bounds(100, None, 1000) is None


def test_normalize_loop_bounds_rejects_inverted_range():
    assert normalize_loop_bounds(500, 100, 1000) is None


def test_normalize_loop_bounds_clamps_to_duration():
    bounds = normalize_loop_bounds(-50, 2000, 1000)
    assert bounds == (0, 1000)


def test_loop_region_x_maps_ms_to_canvas():
    region = loop_region_x(250, 750, duration_ms=1000, width=200)
    assert region == (50, 150)


def test_loop_region_x_returns_none_without_loop():
    assert loop_region_x(None, None, duration_ms=1000, width=200) is None


def test_loop_region_x_ensures_minimum_width():
    region = loop_region_x(500, 501, duration_ms=1000, width=200)
    assert region is not None
    x_start, x_end = region
    assert x_end > x_start


def test_loop_region_x_cue_marker_independent():
    duration_ms = 1000
    width = 200
    cue_x = cue_marker_x(100, duration_ms, width)
    loop = loop_region_x(400, 800, duration_ms, width)
    assert cue_x is not None
    assert loop is not None
    assert cue_x not in loop or loop[0] <= cue_x <= loop[1]


def test_attack_marker_x_maps_attack_time():
    assert attack_marker_x(250, duration_ms=1000, width=200) == 50


def test_attack_marker_x_returns_none_when_unset():
    assert attack_marker_x(None, duration_ms=1000, width=200) is None
    assert attack_marker_x(-1, duration_ms=1000, width=200) is None
