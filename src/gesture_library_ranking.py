"""R&D Slice 2 (#680/#882): gesture cluster → ranked oneshot library candidates.

Quality labels
--------------
MEASURED: aligned feature values, L2 distances, deterministic Top-N ordering.
HEURISTIC: per-cluster median prototype; classical L2 after candidate-corpus
z-score; onset-window vs full-file feature-space mismatch remains unclaimed.
NOT YET CLAIMED: drum-role identity, producer-quality match, musical
correctness, calibrated confidence.

See ``docs/GESTURE_LIBRARY_RANKING_RND_SLICE2.md`` for the frozen contract.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from math import log10

import numpy as np

from .gesture_analysis import FEATURE_DIM, GestureAnalysis

ALIGNED_FEATURE_DIM = FEATURE_DIM
MFCC_DIM = 13
ONESHOT_CLASS = "oneshot"
RMS_DBFS_EPSILON = 1e-12
_NORM_STD_FLOOR = 1e-12


@dataclass(frozen=True)
class LibraryCandidate:
    """Immutable catalog-feature projection used by the ranking core."""

    sample_id: str
    path: str | None
    audio_class: str
    loudness: float
    brightness: float
    mfcc13: tuple[float, ...]


@dataclass(frozen=True)
class RankedCandidate:
    """One ranked hit for a gesture cluster (distance is not confidence)."""

    sample_id: str
    distance: float
    rank: int


@dataclass(frozen=True)
class ClusterRanking:
    """Shared ranking for every event that carries ``cluster_id``."""

    cluster_id: int
    prototype_aligned: tuple[float, ...]
    ranked: tuple[RankedCandidate, ...]


def rank_gesture_library_candidates(
    analysis: GestureAnalysis,
    candidates: Sequence[LibraryCandidate],
    *,
    top_n: int = 5,
) -> tuple[ClusterRanking, ...]:
    """Rank oneshot library candidates per gesture cluster.

    Deterministic for identical inputs. Does not mutate ``analysis``. Does not
    open a database or invoke models. Timing fields on ``analysis`` are unused
    for distance math and remain measured source seconds.
    """
    if top_n <= 0:
        raise ValueError(f"top_n must be positive, got {top_n!r}")

    pool = tuple(_filter_candidate(c) for c in candidates)
    pool = tuple(c for c in pool if c is not None)
    # Canonicalize by stable identity so corpus mean/std are independent of
    # input iteration order (IEEE reduction order otherwise can drift).
    pool = tuple(sorted(pool, key=lambda c: c.sample_id))
    pool_matrix = (
        np.stack([_candidate_aligned_vector(c) for c in pool], axis=0).astype(np.float64)
        if pool
        else np.zeros((0, ALIGNED_FEATURE_DIM), dtype=np.float64)
    )

    by_cluster: dict[int, list[tuple[float, ...]]] = defaultdict(list)
    for event in analysis.events:
        by_cluster[int(event.cluster_id)].append(tuple(event.feature_vector))

    rankings: list[ClusterRanking] = []
    for cluster_id in sorted(by_cluster):
        prototype_raw = _median_prototype(by_cluster[cluster_id])
        aligned = _align_gesture_prototype(prototype_raw)
        if aligned is None:
            rankings.append(
                ClusterRanking(
                    cluster_id=cluster_id,
                    prototype_aligned=(),
                    ranked=(),
                )
            )
            continue

        if pool_matrix.shape[0] == 0:
            rankings.append(
                ClusterRanking(
                    cluster_id=cluster_id,
                    prototype_aligned=aligned,
                    ranked=(),
                )
            )
            continue

        query = np.asarray(aligned, dtype=np.float64)
        ranked = _rank_against_pool(query, pool, pool_matrix, top_n=top_n)
        rankings.append(
            ClusterRanking(
                cluster_id=cluster_id,
                prototype_aligned=aligned,
                ranked=ranked,
            )
        )
    return tuple(rankings)


def _filter_candidate(candidate: LibraryCandidate) -> LibraryCandidate | None:
    if not isinstance(candidate.sample_id, str) or not candidate.sample_id:
        return None
    if candidate.audio_class != ONESHOT_CLASS:
        return None
    if not np.isfinite(candidate.loudness) or not np.isfinite(candidate.brightness):
        return None
    mfcc = candidate.mfcc13
    if len(mfcc) != MFCC_DIM:
        return None
    if not all(np.isfinite(x) for x in mfcc):
        return None
    return candidate


def _candidate_aligned_vector(candidate: LibraryCandidate) -> np.ndarray:
    vec = np.empty(ALIGNED_FEATURE_DIM, dtype=np.float64)
    vec[0] = float(candidate.loudness)
    vec[1] = float(candidate.brightness)
    vec[2:] = np.asarray(candidate.mfcc13, dtype=np.float64)
    return vec


def _median_prototype(vectors: Sequence[tuple[float, ...]]) -> tuple[float, ...] | None:
    if not vectors:
        return None
    matrix = np.asarray(vectors, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[1] != FEATURE_DIM:
        return None
    # Any non-finite raw value fail-closes the cluster (no silent imputation).
    if not np.isfinite(matrix).all():
        return None
    med = np.median(matrix, axis=0)
    if not np.isfinite(med).all():
        return None
    return tuple(float(x) for x in med)


def _align_gesture_prototype(
    prototype_raw: tuple[float, ...] | None,
) -> tuple[float, ...] | None:
    if prototype_raw is None or len(prototype_raw) != FEATURE_DIM:
        return None
    rms = float(prototype_raw[0])
    brightness = float(prototype_raw[1])
    mfcc = prototype_raw[2:]
    if not np.isfinite(rms) or rms <= 0.0:
        return None
    if not np.isfinite(brightness):
        return None
    if len(mfcc) != MFCC_DIM or not all(np.isfinite(x) for x in mfcc):
        return None
    loudness = 20.0 * log10(rms + RMS_DBFS_EPSILON)
    if not np.isfinite(loudness):
        return None
    return (float(loudness), float(brightness), *tuple(float(x) for x in mfcc))


def _zscore_fit(matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mean = np.mean(matrix, axis=0)
    std = np.std(matrix, axis=0)
    return mean.astype(np.float64), std.astype(np.float64)


def _zscore_apply(vec: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    out = np.zeros_like(vec, dtype=np.float64)
    for d in range(vec.shape[0]):
        s = float(std[d])
        m = float(mean[d])
        x = float(vec[d])
        if not np.isfinite(s) or not np.isfinite(m) or s <= _NORM_STD_FLOOR:
            out[d] = 0.0
            continue
        z = (x - m) / s
        out[d] = float(z) if np.isfinite(z) else 0.0
    return out


def _rank_against_pool(
    query: np.ndarray,
    pool: Sequence[LibraryCandidate],
    pool_matrix: np.ndarray,
    *,
    top_n: int,
) -> tuple[RankedCandidate, ...]:
    mean, std = _zscore_fit(pool_matrix)
    qn = _zscore_apply(query, mean, std)
    scored: list[tuple[float, str]] = []
    for cand, row in zip(pool, pool_matrix, strict=True):
        cn = _zscore_apply(row, mean, std)
        dist = float(np.linalg.norm(qn - cn))
        if not np.isfinite(dist):
            continue
        scored.append((dist, cand.sample_id))
    scored.sort(key=lambda item: (item[0], item[1]))
    top = scored[:top_n]
    return tuple(
        RankedCandidate(sample_id=sample_id, distance=distance, rank=index)
        for index, (distance, sample_id) in enumerate(top, start=1)
    )
