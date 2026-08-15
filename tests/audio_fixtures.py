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


def _chord_wave(
    *,
    duration_sec: float,
    root_hz: float,
    third_ratio: float,
    fifth_ratio: float = 2.0 ** (7.0 / 12.0),
    sr: int = 44100,
    amplitude: float = 0.5,
) -> np.ndarray:
    sample_count = max(1, int(sr * duration_sec))
    t = np.linspace(0.0, duration_sec, sample_count, endpoint=False, dtype=np.float32)
    freqs = [root_hz, root_hz * third_ratio, root_hz * fifth_ratio]
    wave = sum(amplitude / 3.0 * np.sin(2.0 * np.pi * f * t) for f in freqs).astype(
        np.float32
    )
    return np.clip(wave, -1.0, 1.0)


def write_major_chord_wav(
    path: Path,
    *,
    duration_sec: float = 2.0,
    frequency_hz: float = 261.63,
    sr: int = 44100,
    amplitude: float = 0.5,
) -> Path:
    """Deterministic major triad (root, major third, fifth) WAV fixture."""
    path.parent.mkdir(parents=True, exist_ok=True)
    wave = _chord_wave(
        duration_sec=duration_sec,
        root_hz=frequency_hz,
        third_ratio=2.0 ** (4.0 / 12.0),
        sr=sr,
        amplitude=amplitude,
    )
    sf.write(path, wave, sr, subtype="PCM_16")
    return path


def write_minor_chord_wav(
    path: Path,
    *,
    duration_sec: float = 2.0,
    frequency_hz: float = 261.63,
    sr: int = 44100,
    amplitude: float = 0.5,
) -> Path:
    """Deterministic minor triad (root, minor third, fifth) WAV fixture."""
    path.parent.mkdir(parents=True, exist_ok=True)
    wave = _chord_wave(
        duration_sec=duration_sec,
        root_hz=frequency_hz,
        third_ratio=2.0 ** (3.0 / 12.0),
        sr=sr,
        amplitude=amplitude,
    )
    sf.write(path, wave, sr, subtype="PCM_16")
    return path


def write_root_fifth_wav(
    path: Path,
    *,
    duration_sec: float = 2.0,
    frequency_hz: float = 261.63,
    sr: int = 44100,
    amplitude: float = 0.5,
) -> Path:
    """Deterministic root + perfect fifth (power chord) WAV fixture.

    Ambiguous for mode: contains no third, so neither major nor minor is
    evidenced.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    sample_count = max(1, int(sr * duration_sec))
    t = np.linspace(0.0, duration_sec, sample_count, endpoint=False, dtype=np.float32)
    fifth_ratio = 2.0 ** (7.0 / 12.0)
    wave = sum(
        amplitude / 2.0 * np.sin(2.0 * np.pi * f * t)
        for f in (frequency_hz, frequency_hz * fifth_ratio)
    ).astype(np.float32)
    sf.write(path, np.clip(wave, -1.0, 1.0), sr, subtype="PCM_16")
    return path


def write_octave_wav(
    path: Path,
    *,
    duration_sec: float = 2.0,
    frequency_hz: float = 261.63,
    sr: int = 44100,
    amplitude: float = 0.5,
) -> Path:
    """Deterministic root + octave WAV fixture (single pitch class, ambiguous)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    sample_count = max(1, int(sr * duration_sec))
    t = np.linspace(0.0, duration_sec, sample_count, endpoint=False, dtype=np.float32)
    wave = sum(
        amplitude / 2.0 * np.sin(2.0 * np.pi * f * t)
        for f in (frequency_hz, frequency_hz * 2.0)
    ).astype(np.float32)
    sf.write(path, np.clip(wave, -1.0, 1.0), sr, subtype="PCM_16")
    return path


# Krumhansl-Schmuckler profile weights, reused here only to synthesize a clean
# "known key" signal (deterministic, no private audio). Detection uses the same
# profiles in src.analyze; this is a functional correctness fixture, not a claim
# about real-music accuracy.
_MAJOR_SCALE_DEGREES = (0, 2, 4, 5, 7, 9, 11)
_MINOR_SCALE_DEGREES = (0, 2, 3, 5, 7, 8, 10)
_MAJOR_KEY_WEIGHTS = (6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
_MINOR_KEY_WEIGHTS = (6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17)


def write_key_audio_wav(
    path: Path,
    *,
    duration_sec: float = 2.0,
    frequency_hz: float = 261.63,
    mode: str = "maj",
    sr: int = 44100,
    amplitude: float = 0.5,
) -> Path:
    """Deterministic sustained 'known key' WAV built from a peaked triad.

    Root + third + fifth, with the root clearly dominant (as in real tonal
    audio). In the requested mode the third is the characteristic major/minor
    third. This gives ``estimate_key_mode`` (third-contrast detector) a clean
    Dur/Moll signal: the major third (root + 4) dominates for major fixtures and
    the minor third (root + 3) dominates for minor fixtures, yielding a contrast
    well above ``MODE_CONTRAST_MIN`` while keeping the root the dominant pitch
    class. Used by the synthetic validation gate in
    tests/test_key_mode_analysis.py.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if mode == "min":
        degrees = (0, 3, 7)
    else:
        degrees = (0, 4, 7)
    weights = (1.0, 0.85, 0.7)

    sample_count = max(1, int(sr * duration_sec))
    t = np.linspace(0.0, duration_sec, sample_count, endpoint=False, dtype=np.float32)
    wave = np.zeros(sample_count, dtype=np.float64)
    for deg, w in zip(degrees, weights):
        freq = frequency_hz * (2.0 ** (deg / 12.0))
        wave = wave + w * np.sin(2.0 * np.pi * freq * t)
    peak = float(np.max(np.abs(wave))) or 1.0
    wave = (amplitude * wave / peak).astype(np.float32)
    sf.write(path, wave, sr, subtype="PCM_16")
    return path


def write_major_minor_blend_wav(
    path: Path,
    *,
    duration_sec: float = 2.0,
    frequency_hz: float = 261.63,
    sr: int = 44100,
    amplitude: float = 0.5,
) -> Path:
    """Deterministic ambiguous blend: root + equal major & minor third + fifth.

    Neither Dur/Moll mode is evidenced, so the analyzer should abstain.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    sample_count = max(1, int(sr * duration_sec))
    t = np.linspace(0.0, duration_sec, sample_count, endpoint=False, dtype=np.float32)
    freqs = [
        frequency_hz,
        frequency_hz * 2.0 ** (3.0 / 12.0),
        frequency_hz * 2.0 ** (4.0 / 12.0),
        frequency_hz * 2.0 ** (7.0 / 12.0),
    ]
    wave = sum(amplitude / 4.0 * np.sin(2.0 * np.pi * f * t) for f in freqs).astype(
        np.float32
    )
    sf.write(path, np.clip(wave, -1.0, 1.0), sr, subtype="PCM_16")
    return path
