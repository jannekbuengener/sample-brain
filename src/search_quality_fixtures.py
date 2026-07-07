from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from .config import ANALYZE_SR

_CLAP_SR = 48_000


def write_kick_transient_wav(
    path: Path,
    *,
    bpm: float = 120.0,
    duration_sec: float = 4.0,
    amplitude: float = 0.8,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sr = _CLAP_SR
    n_total = max(1, int(sr * duration_sec))
    y = np.zeros(n_total, dtype=np.float32)
    interval_sec = 60.0 / bpm
    kick_duration = min(0.15, interval_sec * 0.4)
    kick_samples = max(1, int(kick_duration * sr))
    t_kick = np.linspace(0.0, kick_duration, kick_samples, dtype=np.float32)
    envelope = np.exp(-t_kick * 25.0)
    kick = amplitude * np.sin(2.0 * np.pi * 60.0 * t_kick) * envelope
    num_pulses = int(duration_sec / interval_sec)
    for i in range(num_pulses):
        start = int(i * interval_sec * sr)
        if start + kick_samples <= n_total:
            y[start : start + kick_samples] += kick.astype(np.float32)
    y = np.clip(y, -1.0, 1.0)
    sf.write(path, y, sr, subtype="PCM_16")
    return path


def write_pulse_train_wav(
    path: Path,
    *,
    bpm: float = 120.0,
    duration_sec: float = 4.0,
    amplitude: float = 0.8,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sr = _CLAP_SR
    n_total = max(1, int(sr * duration_sec))
    y = np.zeros(n_total, dtype=np.float32)
    interval_sec = 60.0 / bpm
    pulse_duration = 0.005
    pulse_samples = max(1, int(pulse_duration * sr))
    t_pulse = np.linspace(0.0, pulse_duration, pulse_samples, dtype=np.float32)
    envelope = np.linspace(1.0, 0.0, pulse_samples, dtype=np.float32) ** 2
    pulse = amplitude * np.sin(2.0 * np.pi * 800.0 * t_pulse) * envelope
    num_pulses = int(duration_sec / interval_sec)
    for i in range(num_pulses):
        start = int(i * interval_sec * sr)
        if start + pulse_samples <= n_total:
            y[start : start + pulse_samples] += pulse.astype(np.float32)
    y = np.clip(y, -1.0, 1.0)
    sf.write(path, y, sr, subtype="PCM_16")
    return path


def write_perc_hit_wav(
    path: Path,
    *,
    duration_sec: float = 0.08,
    amplitude: float = 0.9,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sr = _CLAP_SR
    sample_count = max(1, int(sr * duration_sec))
    t = np.linspace(0.0, duration_sec, sample_count, dtype=np.float32)
    envelope = np.exp(-t * 80.0)
    wave = amplitude * np.sin(2.0 * np.pi * 1200.0 * t) * envelope
    sf.write(path, wave.astype(np.float32), sr, subtype="PCM_16")
    return path


def write_sine_wav(
    path: Path,
    *,
    frequency_hz: float = 220.0,
    duration_sec: float = 4.0,
    amplitude: float = 0.5,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sr = _CLAP_SR
    sample_count = max(1, int(sr * duration_sec))
    t = np.linspace(0.0, duration_sec, sample_count, endpoint=False, dtype=np.float32)
    wave = amplitude * np.sin(2.0 * np.pi * frequency_hz * t)
    sf.write(path, wave.astype(np.float32), sr, subtype="PCM_16")
    return path


def write_chord_pad_wav(
    path: Path,
    *,
    root_hz: float = 220.0,
    duration_sec: float = 4.0,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sr = _CLAP_SR
    sample_count = max(1, int(sr * duration_sec))
    t = np.linspace(0.0, duration_sec, sample_count, endpoint=False, dtype=np.float32)
    freqs = [root_hz, root_hz * 5.0 / 4.0, root_hz * 3.0 / 2.0]
    wave = sum(0.33 * np.sin(2.0 * np.pi * freq * t) for freq in freqs).astype(np.float32)
    sf.write(path, wave, sr, subtype="PCM_16")
    return path


def write_texture_noise_wav(
    path: Path,
    *,
    duration_sec: float = 4.0,
    seed: int = 42,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sr = _CLAP_SR
    sample_count = max(1, int(sr * duration_sec))
    rng = np.random.default_rng(seed)
    wave = rng.normal(0.0, 0.25, sample_count).astype(np.float32)
    sf.write(path, wave, sr, subtype="PCM_16")
    return path


_NOTE_ROOT_HZ: dict[str, float] = {
    "C": 261.63,
    "D": 293.66,
    "E": 329.63,
    "F": 349.23,
    "G": 392.00,
    "A": 440.00,
    "B": 493.88,
}


def generate_search_quality_fixture(
    audio_dir: Path,
    fixture_name: str,
    fixture_type: str,
    params: dict[str, Any] | None = None,
) -> Path:
    params = params or {}
    path = audio_dir / f"{fixture_name}.wav"
    if fixture_type == "kick_transient":
        return write_kick_transient_wav(
            path,
            bpm=float(params.get("bpm", 120.0)),
            duration_sec=float(params.get("duration_sec", 4.0)),
        )
    if fixture_type == "pulse_train":
        return write_pulse_train_wav(
            path,
            bpm=float(params.get("bpm", 120.0)),
            duration_sec=float(params.get("duration_sec", 4.0)),
        )
    if fixture_type == "perc_hit":
        return write_perc_hit_wav(path)
    if fixture_type == "sine_tone":
        return write_sine_wav(
            path,
            frequency_hz=float(params.get("frequency_hz", 220.0)),
            duration_sec=float(params.get("duration_sec", 4.0)),
        )
    if fixture_type == "chord_pad":
        root = str(params.get("root", "A"))
        root_hz = float(params.get("root_hz", _NOTE_ROOT_HZ.get(root, 440.0)))
        return write_chord_pad_wav(path, root_hz=root_hz)
    if fixture_type == "texture_noise":
        return write_texture_noise_wav(
            path,
            seed=int(params.get("seed", 42)),
        )
    raise ValueError(f"Unknown search quality fixture type: {fixture_type}")
