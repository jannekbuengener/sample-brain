"""Workbench waveform helpers — read-only envelope data for UI display."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf


def compute_waveform_envelope(path: Path | str, *, max_points: int = 200) -> list[float]:
    """Return peak envelope samples in ``[0.0, 1.0]`` for read-only display.

    Reads audio via existing ``soundfile`` dependency; does not modify *path*.
    """
    if max_points <= 0:
        raise ValueError("max_points must be positive")

    resolved = Path(path)
    if not resolved.is_file():
        return []

    try:
        data, _sr = sf.read(resolved, dtype="float32", always_2d=False)
    except Exception:
        return []

    samples = np.asarray(data, dtype=np.float32)
    if samples.size == 0:
        return []

    if samples.ndim > 1:
        samples = samples.mean(axis=1)

    peak = float(np.max(np.abs(samples)))
    if peak <= 0.0:
        return [0.0] * min(max_points, samples.size)

    normalized = np.abs(samples) / peak
    count = int(normalized.size)
    if count <= max_points:
        return [float(value) for value in normalized]

    chunk_size = int(np.ceil(count / max_points))
    envelope: list[float] = []
    for start in range(0, count, chunk_size):
        chunk = normalized[start : start + chunk_size]
        if chunk.size == 0:
            continue
        envelope.append(float(np.max(chunk)))
    return envelope[:max_points]


__all__ = ["compute_waveform_envelope"]
