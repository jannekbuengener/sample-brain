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


def read_audio_duration_ms(path: Path | str) -> int | None:
    """Return audio duration in milliseconds without modifying *path*."""
    resolved = Path(path)
    if not resolved.is_file():
        return None
    try:
        info = sf.info(resolved)
    except Exception:
        return None
    if info.duration is None or info.duration <= 0:
        return None
    return max(1, int(round(float(info.duration) * 1000.0)))


def clamp_cue_start_ms(cue_start_ms: int, duration_ms: int | None) -> int:
    """Clamp cue start to ``[0, duration_ms)`` when duration is known."""
    if cue_start_ms < 0:
        return 0
    if duration_ms is None or duration_ms <= 0:
        return cue_start_ms
    if cue_start_ms >= duration_ms:
        return max(0, duration_ms - 1)
    return cue_start_ms


def cue_marker_x(cue_start_ms: int, duration_ms: int, width: int) -> int | None:
    """Map cue time to canvas x coordinate."""
    if duration_ms <= 0 or width <= 0:
        return None
    clamped = clamp_cue_start_ms(cue_start_ms, duration_ms)
    return int((clamped / duration_ms) * width)


def normalize_loop_bounds(
    loop_start_ms: int | None,
    loop_end_ms: int | None,
    duration_ms: int,
) -> tuple[int, int] | None:
    """Return clamped loop bounds in ms for read-only display, or None when invalid."""
    if loop_start_ms is None or loop_end_ms is None:
        return None
    if duration_ms <= 0:
        return None
    if loop_end_ms < loop_start_ms:
        return None
    start = max(0, min(loop_start_ms, duration_ms - 1))
    end = max(start + 1, min(loop_end_ms, duration_ms))
    if end <= start:
        return None
    return start, end


def loop_region_x(
    loop_start_ms: int | None,
    loop_end_ms: int | None,
    duration_ms: int,
    width: int,
) -> tuple[int, int] | None:
    """Map loop bounds to canvas x coordinates ``(x_start, x_end)`` for display."""
    if width <= 0:
        return None
    bounds = normalize_loop_bounds(loop_start_ms, loop_end_ms, duration_ms)
    if bounds is None:
        return None
    start_ms, end_ms = bounds
    x_start = int((start_ms / duration_ms) * width)
    x_end = int((end_ms / duration_ms) * width)
    if x_end <= x_start:
        x_end = min(width, x_start + 1)
    return x_start, x_end


def attack_marker_x(attack_ms: int | None, duration_ms: int, width: int) -> int | None:
    """Map attack time to canvas x coordinate, or None when unset/invalid."""
    if attack_ms is None or attack_ms < 0:
        return None
    return cue_marker_x(attack_ms, duration_ms, width)


def cue_ms_from_x(x: int, width: int, duration_ms: int) -> int:
    """Map canvas x coordinate to cue time in milliseconds."""
    if width <= 0 or duration_ms <= 0:
        return 0
    if x <= 0:
        return 0
    if x >= width:
        return max(0, duration_ms - 1)
    ms = int(round((x / width) * duration_ms))
    return clamp_cue_start_ms(ms, duration_ms)


__all__ = [
    "attack_marker_x",
    "clamp_cue_start_ms",
    "compute_waveform_envelope",
    "cue_marker_x",
    "cue_ms_from_x",
    "loop_region_x",
    "normalize_loop_bounds",
    "read_audio_duration_ms",
]
