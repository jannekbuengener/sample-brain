"""Neutral BPM matching semantics shared by matching and harmony."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .bpm_display import format_bpm_display

DEFAULT_BPM_TOLERANCE = 8.0
HALF_DOUBLE_PENALTY = 0.9

DIMENSION_OK = "ok"
DIMENSION_NO_RESULT = "no_result"

BPM_RELATION_DIRECT = "direct"
BPM_RELATION_HALF_TIME = "half_time"
BPM_RELATION_DOUBLE_TIME = "double_time"
BPM_RELATION_NO_RESULT = "no_result"


@dataclass(frozen=True)
class _BpmMatchDetails:
    score: float
    reason: str
    status: str
    relation: str = BPM_RELATION_NO_RESULT
    tempo_multiplier: float | None = None


def _linear_decay(diff: float, tolerance: float) -> float:
    if tolerance <= 0:
        return 0.0
    if diff >= tolerance:
        return 0.0
    if diff == 0:
        return 1.0
    return 1.0 - (diff / tolerance)


def _score_bpm_details(
    sample_bpm: float | None,
    target_bpm: float | None,
    tolerance: float,
) -> _BpmMatchDetails:
    if sample_bpm is None or target_bpm is None:
        return _BpmMatchDetails(
            score=0.0,
            reason="bpm missing",
            status=DIMENSION_NO_RESULT,
        )

    if not math.isfinite(sample_bpm) or not math.isfinite(target_bpm):
        return _BpmMatchDetails(
            score=0.0,
            reason="bpm invalid",
            status=DIMENSION_NO_RESULT,
        )

    if sample_bpm <= 0 or target_bpm <= 0:
        return _BpmMatchDetails(
            score=0.0,
            reason="bpm invalid",
            status=DIMENSION_NO_RESULT,
        )

    direct_score = _linear_decay(abs(sample_bpm - target_bpm), tolerance)
    half_time_score = (
        _linear_decay(abs((sample_bpm * 2.0) - target_bpm), tolerance)
        * HALF_DOUBLE_PENALTY
    )
    double_time_score = (
        _linear_decay(abs((sample_bpm / 2.0) - target_bpm), tolerance)
        * HALF_DOUBLE_PENALTY
    )

    candidates = [
        (
            direct_score,
            BPM_RELATION_DIRECT,
            1.0,
            f"bpm direct match: {format_bpm_display(sample_bpm)} vs {format_bpm_display(target_bpm)}",
        ),
        (
            half_time_score,
            BPM_RELATION_HALF_TIME,
            2.0,
            f"bpm half-time fit: {format_bpm_display(sample_bpm)} -> {format_bpm_display(sample_bpm * 2.0)}",
        ),
        (
            double_time_score,
            BPM_RELATION_DOUBLE_TIME,
            0.5,
            f"bpm double-time fit: {format_bpm_display(sample_bpm)} -> {format_bpm_display(sample_bpm / 2.0)}",
        ),
    ]
    best_score, relation, tempo_multiplier, best_reason = max(
        candidates, key=lambda item: item[0]
    )
    if best_score > 0.0:
        return _BpmMatchDetails(
            score=best_score,
            reason=best_reason,
            status=DIMENSION_OK,
            relation=relation,
            tempo_multiplier=tempo_multiplier,
        )

    return _BpmMatchDetails(
        score=0.0,
        reason=f"bpm mismatch: {format_bpm_display(sample_bpm)} vs {format_bpm_display(target_bpm)}",
        status=DIMENSION_OK,
    )


def score_bpm_match(
    sample_bpm: float | None,
    target_bpm: float | None,
    tolerance: float,
) -> float:
    return _score_bpm_details(sample_bpm, target_bpm, tolerance).score


__all__ = [
    "DEFAULT_BPM_TOLERANCE",
    "HALF_DOUBLE_PENALTY",
    "BPM_RELATION_DIRECT",
    "BPM_RELATION_HALF_TIME",
    "BPM_RELATION_DOUBLE_TIME",
    "BPM_RELATION_NO_RESULT",
    "DIMENSION_OK",
    "DIMENSION_NO_RESULT",
    "score_bpm_match",
]
