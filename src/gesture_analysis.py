"""R&D Slice 1 (#680/#827): gesture onset → event features → deterministic clustering.

Quality labels
--------------
MEASURED: onset times, raw DSP features, pairwise L2 distances after normalization.
HEURISTIC: cluster_id assignment via fixed-threshold sequential nearest centroid.
NOT YET CLAIMED: Kick/Snare/Hat semantics, library sample match, producer quality.

See ``docs/GESTURE_ANALYSIS_RND_SLICE1.md`` for the frozen contract and threshold
calibration rationale.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np

from .analyze import _effective_n_fft, safe_load
from .config import ANALYZE_HOP_LENGTH, ANALYZE_SR

FEATURE_DIM = 15
"""Documented feature dimension: RMS(1) + spectral centroid(1) + MFCC mean(13)."""

# Calibrated against synthetic golden cases in docs/GESTURE_ANALYSIS_RND_SLICE1.md.
# With relative std-floor z-norm: same-gesture max L2 ≈ 2.45 (amp-variation);
# cross-gesture min L2 ≈ 7.56 (kick vs hat); midpoint with ~2.5 margin → 5.0.
CLUSTER_DISTANCE_THRESHOLD = 5.0

# Per-dimension std below max(abs_floor, rel * peak_|x|) is treated as zero variance.
_NORM_STD_REL_FLOOR = 0.05
_NORM_STD_ABS_FLOOR = 1e-6

_MIN_DURATION_SEC = 0.05
_SILENCE_PEAK = 1e-6
_PRE_WINDOW_SEC = 0.04
_POST_WINDOW_SEC = 0.12
_MIN_WINDOW_SAMPLES = 32
_ONSET_DELTA = 0.07
# hop 512 @ 44.1 kHz ≈ 11.6 ms/frame; wait=13 ≈ 151 ms suppresses decay-tail doubles.
_ONSET_WAIT_FRAMES = 13
# Hard post-filter: keep strictly increasing times with this minimum gap.
_MIN_ONSET_GAP_SEC = 0.15
_N_MFCC = 13


@dataclass(frozen=True)
class GestureEvent:
    """One detected gesture event with measured features and heuristic cluster."""

    onset_time_sec: float
    feature_vector: tuple[float, ...]
    cluster_id: int


@dataclass(frozen=True)
class GestureAnalysis:
    """Result of local gesture analysis for one audio file."""

    events: tuple[GestureEvent, ...]
    sample_rate: int
    duration_sec: float
    feature_dim: int
    status: str  # ok | empty | too_short | unreadable


def analyze_gesture_audio(path: Path | str) -> GestureAnalysis:
    """Analyze a local audio file into ordered gesture events with cluster IDs.

    Deterministic for a given file contents and this module's constants.
    Never raises for ordinary I/O/DSP failures; returns fail-soft statuses.
    """
    resolved = Path(path)
    y, sr = safe_load(resolved, target_sr=ANALYZE_SR)
    if y is None or sr is None:
        return GestureAnalysis(
            events=(),
            sample_rate=ANALYZE_SR,
            duration_sec=0.0,
            feature_dim=FEATURE_DIM,
            status="unreadable",
        )

    y = np.asarray(y, dtype=np.float32)
    duration_sec = float(y.size) / float(sr) if y.size and sr else 0.0
    if y.size == 0 or duration_sec < _MIN_DURATION_SEC:
        return GestureAnalysis(
            events=(),
            sample_rate=int(sr),
            duration_sec=duration_sec,
            feature_dim=FEATURE_DIM,
            status="too_short",
        )

    peak = float(np.max(np.abs(y))) if y.size else 0.0
    if peak <= _SILENCE_PEAK:
        return GestureAnalysis(
            events=(),
            sample_rate=int(sr),
            duration_sec=duration_sec,
            feature_dim=FEATURE_DIM,
            status="empty",
        )

    onset_times = _detect_onset_times(y, int(sr), duration_sec)
    if not onset_times:
        return GestureAnalysis(
            events=(),
            sample_rate=int(sr),
            duration_sec=duration_sec,
            feature_dim=FEATURE_DIM,
            status="empty",
        )

    raw_matrix = np.stack(
        [_extract_event_features(y, int(sr), t) for t in onset_times],
        axis=0,
    ).astype(np.float64)
    normalized = _normalize_feature_matrix(raw_matrix)
    cluster_ids = _cluster_normalized(normalized, CLUSTER_DISTANCE_THRESHOLD)

    events = tuple(
        GestureEvent(
            onset_time_sec=float(t),
            feature_vector=tuple(float(x) for x in raw_matrix[i]),
            cluster_id=int(cluster_ids[i]),
        )
        for i, t in enumerate(onset_times)
    )
    return GestureAnalysis(
        events=events,
        sample_rate=int(sr),
        duration_sec=duration_sec,
        feature_dim=FEATURE_DIM,
        status="ok",
    )


def _detect_onset_times(y: np.ndarray, sr: int, duration_sec: float) -> list[float]:
    """Return strictly increasing onset times in seconds within ``[0, duration]``."""
    try:
        onset_env = librosa.onset.onset_strength(
            y=y, sr=sr, hop_length=ANALYZE_HOP_LENGTH
        )
        frames = librosa.onset.onset_detect(
            onset_envelope=onset_env,
            sr=sr,
            hop_length=ANALYZE_HOP_LENGTH,
            units="frames",
            backtrack=False,
            delta=_ONSET_DELTA,
            wait=_ONSET_WAIT_FRAMES,
        )
    except Exception:
        return []

    if frames is None or len(frames) == 0:
        return []

    sample_indices: list[int] = []
    n = int(y.size)
    for frame in np.asarray(frames).reshape(-1):
        if not np.isfinite(frame):
            continue
        sample = int(
            librosa.frames_to_samples(int(frame), hop_length=ANALYZE_HOP_LENGTH)
        )
        if sample < 0 or sample >= n:
            continue
        sample_indices.append(sample)

    if not sample_indices:
        return []

    # Sort + dedupe identical sample indices, then enforce min gap so times
    # are strictly monotonically increasing (drop same-frame / near-duplicate
    # decay-tail detections).
    unique_samples = sorted(set(sample_indices))
    times: list[float] = []
    for sample in unique_samples:
        t = float(sample) / float(sr)
        if t < 0.0 or t > duration_sec:
            continue
        if times and t <= times[-1]:
            continue
        if times and (t - times[-1]) < _MIN_ONSET_GAP_SEC:
            continue
        times.append(t)
    return times


def _extract_event_features(
    y: np.ndarray, sr: int, onset_time_sec: float
) -> np.ndarray:
    """Extract a finite FEATURE_DIM vector for one onset window (fail-soft zeros)."""
    out = np.zeros(FEATURE_DIM, dtype=np.float64)
    start = int(max(0, (onset_time_sec - _PRE_WINDOW_SEC) * sr))
    end = int(min(y.size, (onset_time_sec + _POST_WINDOW_SEC) * sr))
    if end - start < _MIN_WINDOW_SAMPLES:
        return out

    segment = np.asarray(y[start:end], dtype=np.float32)
    if segment.size == 0 or not np.isfinite(segment).all():
        return out

    try:
        rms = float(np.sqrt(np.mean(np.square(segment))))
        if not np.isfinite(rms):
            rms = 0.0
        out[0] = rms
    except Exception:
        out[0] = 0.0

    n_fft = _effective_n_fft(int(segment.size))
    try:
        centroid = librosa.feature.spectral_centroid(
            y=segment, sr=sr, hop_length=ANALYZE_HOP_LENGTH, n_fft=n_fft
        )
        if centroid is not None and centroid.size and np.isfinite(centroid).all():
            out[1] = float(np.mean(centroid))
    except Exception:
        pass

    try:
        mfcc = librosa.feature.mfcc(
            y=segment,
            sr=sr,
            n_mfcc=_N_MFCC,
            hop_length=ANALYZE_HOP_LENGTH,
            n_fft=n_fft,
        )
        if mfcc is not None and mfcc.size and np.isfinite(mfcc).all():
            means = np.mean(mfcc, axis=1).astype(np.float64)
            if means.shape[0] == _N_MFCC and np.isfinite(means).all():
                out[2:] = means
    except Exception:
        pass

    out = np.where(np.isfinite(out), out, 0.0)
    return out


def _normalize_feature_matrix(matrix: np.ndarray) -> np.ndarray:
    """Per-dimension z-score within one analysis; near-zero variance → 0.0.

    Semantics:
    - Non-finite raw values are treated as 0.0 before statistics.
    - For each dimension d over events in this single analysis:
      mean_d, std_d, peak_d = max(|x|).
    - Effective zero-variance when
      ``std_d <= max(_NORM_STD_ABS_FLOOR, _NORM_STD_REL_FLOOR * peak_d)``
      or std/mean is non-finite. That dimension is then 0.0 for every event
      (fail-soft; avoids divide-by-zero and noise amplification when events
      are nearly identical).
    - Otherwise ``(x - mean_d) / std_d``; non-finite results → 0.0.
    - Identical input matrices yield identical normalized matrices.
    """
    if matrix.size == 0:
        return matrix.astype(np.float64, copy=True)

    clean = np.where(np.isfinite(matrix), matrix, 0.0).astype(np.float64)
    if clean.ndim != 2 or clean.shape[1] != FEATURE_DIM:
        raise ValueError(f"expected (*, {FEATURE_DIM}) feature matrix")

    if clean.shape[0] == 1:
        return np.zeros_like(clean)

    mean = np.mean(clean, axis=0)
    std = np.std(clean, axis=0)
    peak = np.max(np.abs(clean), axis=0)
    out = np.zeros_like(clean)
    for d in range(FEATURE_DIM):
        s = float(std[d])
        m = float(mean[d])
        floor = max(_NORM_STD_ABS_FLOOR, _NORM_STD_REL_FLOOR * float(peak[d]))
        if not np.isfinite(s) or not np.isfinite(m) or s <= floor:
            out[:, d] = 0.0
        else:
            col = (clean[:, d] - m) / s
            out[:, d] = np.where(np.isfinite(col), col, 0.0)
    return out


def _cluster_normalized(normalized: np.ndarray, threshold: float) -> list[int]:
    """Sequential nearest-centroid clustering on normalized feature rows."""
    n = int(normalized.shape[0])
    if n == 0:
        return []

    centroids: list[np.ndarray] = []
    counts: list[int] = []
    assignments: list[int] = []

    for i in range(n):
        vec = normalized[i]
        if not centroids:
            centroids.append(vec.copy())
            counts.append(1)
            assignments.append(0)
            continue

        distances = [float(np.linalg.norm(vec - c)) for c in centroids]
        best = int(np.argmin(distances))
        if distances[best] <= threshold:
            n_c = counts[best]
            centroids[best] = (centroids[best] * n_c + vec) / float(n_c + 1)
            counts[best] = n_c + 1
            assignments.append(best)
        else:
            assignments.append(len(centroids))
            centroids.append(vec.copy())
            counts.append(1)

    return assignments
