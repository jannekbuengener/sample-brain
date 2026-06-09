from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf


def write_sine_wav(
    path: Path,
    *,
    duration_sec: float,
    frequency_hz: float,
    sr: int = 44100,
    amplitude: float = 0.5,
) -> Path:
    """Generate a deterministic mono sine-wave WAV fixture."""
    path.parent.mkdir(parents=True, exist_ok=True)
    sample_count = max(1, int(sr * duration_sec))
    t = np.linspace(0.0, duration_sec, sample_count, endpoint=False, dtype=np.float32)
    wave = amplitude * np.sin(2.0 * np.pi * frequency_hz * t)
    sf.write(path, wave.astype(np.float32), sr, subtype="PCM_16")
    return path


def write_pulse_train_wav(
    path: Path,
    *,
    bpm: float,
    duration_sec: float = 4.0,
    sr: int = 44100,
    pulse_duration: float = 0.005,
    amplitude: float = 0.8,
) -> Path:
    """Generate a rhythmic pulse-train WAV at a known BPM.

    Each pulse is a short decaying sine click to give librosa a clear
    rhythmic signal without harmonic content that would confuse the
    beat tracker.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    n_total = max(1, int(sr * duration_sec))
    y = np.zeros(n_total, dtype=np.float32)
    interval_sec = 60.0 / bpm
    pulse_samples = max(1, int(pulse_duration * sr))

    if pulse_samples > 1:
        t_pulse = np.linspace(0.0, pulse_duration, pulse_samples, dtype=np.float32)
        envelope = np.linspace(1.0, 0.0, pulse_samples, dtype=np.float32) ** 2
        pulse = amplitude * np.sin(2.0 * np.pi * 800.0 * t_pulse) * envelope
    else:
        pulse = np.ones(1, dtype=np.float32) * amplitude

    num_pulses = int(duration_sec / interval_sec)
    for i in range(num_pulses):
        start = int(i * interval_sec * sr)
        if start + pulse_samples <= n_total:
            y[start : start + pulse_samples] += pulse.astype(np.float32)

    y = np.clip(y, -1.0, 1.0)
    sf.write(path, y, sr, subtype="PCM_16")
    return path


def write_kick_transient_wav(
    path: Path,
    *,
    bpm: float,
    duration_sec: float = 4.0,
    sr: int = 44100,
    amplitude: float = 0.8,
) -> Path:
    """Generate kick-like transients at a known BPM.

    Each transient is a low-frequency (60 Hz) decaying sine with a
    sharp attack and exponential decay, simulating a kick drum hit.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
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
