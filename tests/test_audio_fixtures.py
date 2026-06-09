from __future__ import annotations

from pathlib import Path

import soundfile as sf

from tests.audio_fixtures import write_kick_transient_wav, write_pulse_train_wav, write_sine_wav


def test_write_sine_wav_creates_valid_file(tmp_path: Path):
    path = write_sine_wav(tmp_path / "sine.wav", duration_sec=0.5, frequency_hz=440.0)
    assert path.exists()
    data, sr = sf.read(path)
    assert sr == 44100
    assert len(data) > 0


def test_write_pulse_train_wav_creates_valid_file(tmp_path: Path):
    path = write_pulse_train_wav(tmp_path / "pulse.wav", bpm=120.0, duration_sec=2.0)
    assert path.exists()
    data, sr = sf.read(path)
    assert sr == 44100
    assert len(data) > 0
    assert len(data) == int(44100 * 2.0)


def test_write_pulse_train_wav_has_nonzero_content(tmp_path: Path):
    path = write_pulse_train_wav(tmp_path / "pulse.wav", bpm=120.0, duration_sec=2.0)
    data, _ = sf.read(path)
    assert data.max() > 0.0


def test_write_pulse_train_wav_at_slow_bpm(tmp_path: Path):
    path = write_pulse_train_wav(tmp_path / "slow.wav", bpm=40.0, duration_sec=2.0)
    assert path.exists()
    data, _ = sf.read(path)
    assert data.max() > 0.0


def test_write_pulse_train_wav_at_fast_bpm(tmp_path: Path):
    path = write_pulse_train_wav(tmp_path / "fast.wav", bpm=200.0, duration_sec=2.0)
    assert path.exists()
    data, _ = sf.read(path)
    assert data.max() > 0.0


def test_write_kick_transient_wav_creates_valid_file(tmp_path: Path):
    path = write_kick_transient_wav(tmp_path / "kick.wav", bpm=120.0, duration_sec=2.0)
    assert path.exists()
    data, sr = sf.read(path)
    assert sr == 44100
    assert len(data) > 0
    assert len(data) == int(44100 * 2.0)


def test_write_kick_transient_wav_has_nonzero_content(tmp_path: Path):
    path = write_kick_transient_wav(tmp_path / "kick.wav", bpm=120.0, duration_sec=2.0)
    data, _ = sf.read(path)
    assert data.max() > 0.0


def test_pulse_and_kick_fixtures_are_deterministic(tmp_path: Path):
    a = write_pulse_train_wav(tmp_path / "a.wav", bpm=120.0, duration_sec=1.0)
    b = write_pulse_train_wav(tmp_path / "b.wav", bpm=120.0, duration_sec=1.0)
    data_a, _ = sf.read(a)
    data_b, _ = sf.read(b)
    assert (data_a == data_b).all()


def test_fixture_bpm_in_name_matches_label(tmp_path: Path):
    path = write_pulse_train_wav(tmp_path / "pulse_128bpm.wav", bpm=128.0)
    assert "pulse_128bpm" in path.name
