"""Pure, evaluation-only 24-key profile ranking over a 12-bin chroma vector.

This module deliberately does not alter the production analyzer.  It provides
raw, deterministic profile-ranking evidence for a local A/B evaluation only.
No margin threshold is applied: returning the best hypothesis alone must not
be interpreted as a production-ready key or mode decision.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .key_signature import format_key_signature


PITCH_CLASSES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

# Krumhansl-Kessler-style C-major / C-minor profiles.  These values previously
# existed only as test-fixture constants; they are canonicalized here so the
# runtime evaluator and its tests cannot drift into different profile tables.
MAJOR_KEY_PROFILE = (6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
MINOR_KEY_PROFILE = (6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17)

PROFILE_EVIDENCE_KIND = "krumhansl_kessler_pearson_ranking"
PROFILE_EVIDENCE_VERSION = 1
_EPSILON = 1e-12


@dataclass(frozen=True)
class KeyProfileHypothesis:
    root: str
    root_index: int
    mode: str
    canonical_key: str
    score: float


@dataclass(frozen=True)
class KeyProfileRanking:
    """Raw 24-key ranking; ``ranked_only`` intentionally makes no key claim."""

    status: str
    root: str | None
    root_index: int | None
    mode: str | None
    canonical_key: str | None
    best_score: float | None
    runner_up_score: float | None
    margin: float | None
    next_distinct_root_score: float | None
    next_distinct_root_margin: float | None
    evidence_kind: str
    evidence_version: int
    hypotheses: tuple[KeyProfileHypothesis, ...]


def _abstained_ranking() -> KeyProfileRanking:
    return KeyProfileRanking(
        status="abstained",
        root=None,
        root_index=None,
        mode=None,
        canonical_key=None,
        best_score=None,
        runner_up_score=None,
        margin=None,
        next_distinct_root_score=None,
        next_distinct_root_margin=None,
        evidence_kind=PROFILE_EVIDENCE_KIND,
        evidence_version=PROFILE_EVIDENCE_VERSION,
        hypotheses=(),
    )


def _pearson_score(values: np.ndarray, profile: np.ndarray) -> float | None:
    centered_values = values - float(np.mean(values))
    centered_profile = profile - float(np.mean(profile))
    denominator = float(np.linalg.norm(centered_values) * np.linalg.norm(centered_profile))
    if not np.isfinite(denominator) or denominator <= _EPSILON:
        return None
    score = float(np.dot(centered_values, centered_profile) / denominator)
    if not np.isfinite(score):
        return None
    return max(-1.0, min(1.0, score))


def rank_key_profiles(chroma_mean: np.ndarray | tuple[float, ...] | list[float]) -> KeyProfileRanking:
    """Rank all rotated major/minor profiles against one 12-bin chroma vector.

    Pearson correlation is used because it compares the tonal shape after
    removing absolute level.  Tie-breaking is deterministic by root index and
    then major before minor.  The result is always ``ranked_only`` for usable
    evidence: this evaluation candidate intentionally has no confidence gate.
    """
    values = np.asarray(chroma_mean, dtype=np.float64).reshape(-1)
    if values.size != 12 or not np.isfinite(values).all():
        return _abstained_ranking()

    profiles = (("maj", np.asarray(MAJOR_KEY_PROFILE)), ("min", np.asarray(MINOR_KEY_PROFILE)))
    hypotheses: list[KeyProfileHypothesis] = []
    for root_index, root in enumerate(PITCH_CLASSES):
        for mode_order, (mode, profile) in enumerate(profiles):
            score = _pearson_score(values, np.roll(profile, root_index))
            if score is None:
                return _abstained_ranking()
            canonical_key = format_key_signature(root, mode)
            assert canonical_key is not None
            hypotheses.append(KeyProfileHypothesis(
                root=root,
                root_index=root_index,
                mode=mode,
                canonical_key=canonical_key,
                score=score,
            ))

    mode_order = {"maj": 0, "min": 1}
    hypotheses.sort(key=lambda item: (-item.score, item.root_index, mode_order[item.mode]))
    best, runner_up = hypotheses[:2]
    next_distinct_root = next(item for item in hypotheses[1:] if item.root_index != best.root_index)
    return KeyProfileRanking(
        status="ranked_only",
        root=best.root,
        root_index=best.root_index,
        mode=best.mode,
        canonical_key=best.canonical_key,
        best_score=best.score,
        runner_up_score=runner_up.score,
        margin=best.score - runner_up.score,
        next_distinct_root_score=next_distinct_root.score,
        next_distinct_root_margin=best.score - next_distinct_root.score,
        evidence_kind=PROFILE_EVIDENCE_KIND,
        evidence_version=PROFILE_EVIDENCE_VERSION,
        hypotheses=tuple(hypotheses),
    )


def _margin_distribution(rankings: list[KeyProfileRanking]) -> dict[str, float | int | None]:
    margins = np.asarray([ranking.margin for ranking in rankings if ranking.margin is not None])
    if not margins.size:
        return {"count": 0, "min": None, "median": None, "p90": None, "max": None}
    return {
        "count": int(margins.size),
        "min": float(np.min(margins)),
        "median": float(np.median(margins)),
        "p90": float(np.percentile(margins, 90)),
        "max": float(np.max(margins)),
    }


def characterize_synthetic_margins() -> dict[str, dict[str, float | int | None]]:
    """Describe raw-profile margins without defining a production threshold."""
    clear = [
        rank_key_profiles(np.roll(np.asarray(profile), root_index))
        for profile in (MAJOR_KEY_PROFILE, MINOR_KEY_PROFILE)
        for root_index in range(12)
    ]
    ambiguous = [
        rank_key_profiles(np.array([1.0] + [0.0] * 11)),
        rank_key_profiles(np.array([2.0] + [0.0] * 11)),
        rank_key_profiles(np.array([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0] + [0.0] * 4)),
        rank_key_profiles(np.array([1.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 1.0] + [0.0] * 4)),
    ]
    return {
        "clear_synthetic_profiles": _margin_distribution(clear),
        "ambiguous_synthetic_chroma": _margin_distribution(ambiguous),
    }


__all__ = [
    "KeyProfileHypothesis",
    "KeyProfileRanking",
    "MAJOR_KEY_PROFILE",
    "MINOR_KEY_PROFILE",
    "PROFILE_EVIDENCE_KIND",
    "PROFILE_EVIDENCE_VERSION",
    "PITCH_CLASSES",
    "characterize_synthetic_margins",
    "rank_key_profiles",
]
