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
