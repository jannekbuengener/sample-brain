from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from src.workbench_waveform import compute_waveform_envelope
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
