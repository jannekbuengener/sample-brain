"""Dependency-free joint 24-key profile-scoring prototype.

This module is intentionally isolated from the production analyzer.  It ranks
all major and minor key hypotheses jointly from one validated 12-bin chroma
vector.  Scores are raw Pearson correlations, not probabilities or calibrated
confidence values.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


SEMITONES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
MAJOR_PROFILE = np.asarray(
    (6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88),
    dtype=np.float64,
)
MINOR_PROFILE = np.asarray(
    (6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17),
    dtype=np.float64,
)


class JointKeyProfileError(ValueError):
    """Raised when a 24-key score would be mathematically undefined."""


@dataclass(frozen=True)
class KeyProfileHypothesis:
    """One raw major or minor key hypothesis in deterministic rank order."""

    root: str
    mode: str
    score: float


@dataclass(frozen=True)
class JointKeyProfileResult:
    """Best joint key hypothesis plus all raw ranking evidence."""

    root: str
    mode: str
    raw_score: float
    ranking: tuple[KeyProfileHypothesis, ...]


def _validated_vector(values: object, *, label: str) -> np.ndarray:
    try:
        vector = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise JointKeyProfileError(f"{label} must be numeric") from exc
    if vector.ndim != 1:
        raise JointKeyProfileError(f"{label} must be one-dimensional")
    if vector.shape != (12,):
        raise JointKeyProfileError(f"{label} must contain exactly 12 bins")
    if not np.isfinite(vector).all():
        raise JointKeyProfileError(f"{label} must contain only finite values")
    if (vector < 0.0).any():
        raise JointKeyProfileError(f"{label} must contain only non-negative values")
    centered = vector - float(np.mean(vector))
    if float(np.linalg.norm(centered)) == 0.0:
        raise JointKeyProfileError(f"{label} must have non-zero variance")
    return vector


def rotate_profile(profile: object, root_index: int) -> np.ndarray:
    """Rotate a tonic-C profile so its tonic lands at ``root_index``.

    Input and output both use the canonical C-through-B chroma order.
    """

    if not isinstance(root_index, int) or not 0 <= root_index < len(SEMITONES):
        raise JointKeyProfileError("root_index must be an integer from 0 through 11")
    return np.roll(_validated_vector(profile, label="profile"), root_index)


def pearson_score(chroma: object, profile: object) -> float:
    """Return a finite raw Pearson correlation for two 12-bin vectors."""

    observed = _validated_vector(chroma, label="chroma")
    template = _validated_vector(profile, label="profile")
    observed_centered = observed - float(np.mean(observed))
    template_centered = template - float(np.mean(template))
    denominator = float(np.linalg.norm(observed_centered) * np.linalg.norm(template_centered))
    if not np.isfinite(denominator) or denominator <= 0.0:
        raise JointKeyProfileError("Pearson score has undefined denominator")
    score = float(np.dot(observed_centered, template_centered) / denominator)
    if not np.isfinite(score):
        raise JointKeyProfileError("Pearson score must be finite")
    return score


def rank_joint_key_profiles(chroma: object) -> JointKeyProfileResult:
    """Rank all 24 major/minor profiles with a stable explicit tie-break.

    Equal raw scores rank by mode (major before minor) and then by the canonical
    C-through-B root order.  This rule is only a deterministic ordering rule;
    it carries no probability or confidence interpretation.
    """

    observed = _validated_vector(chroma, label="chroma")
    candidates: list[KeyProfileHypothesis] = []
    for mode, profile in (("maj", MAJOR_PROFILE), ("min", MINOR_PROFILE)):
        for root_index, root in enumerate(SEMITONES):
            candidates.append(
                KeyProfileHypothesis(
                    root=root,
                    mode=mode,
                    score=pearson_score(observed, rotate_profile(profile, root_index)),
                )
            )
    ranking = tuple(
        sorted(
            candidates,
            key=lambda item: (-item.score, 0 if item.mode == "maj" else 1, SEMITONES.index(item.root)),
        )
    )
    best = ranking[0]
    return JointKeyProfileResult(
        root=best.root,
        mode=best.mode,
        raw_score=best.score,
        ranking=ranking,
    )
