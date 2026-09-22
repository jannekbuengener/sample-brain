"""Evaluation-only 24-key profile ranking and deterministic abstention evidence.

The production analyzer deliberately remains untouched. This module consumes
already-extracted chroma statistics to evaluate a 24-key profile candidate and
to apply a synthetic-only, fail-closed abstention gate.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .key_signature import format_key_signature


PITCH_CLASSES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
MAJOR_KEY_PROFILE = (6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
MINOR_KEY_PROFILE = (6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17)

PROFILE_EVIDENCE_KIND = "krumhansl_kessler_pearson_ranking"
PROFILE_EVIDENCE_VERSION = 1
PROFILE_GATE_VERSION = "synthetic-v1-1pct"
PROFILE_GATE_SAFETY_FRACTION = 0.01
_EPSILON = 1e-12
_CHROMA_EPSILON = 1e-8


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


@dataclass(frozen=True)
class ProfileGateEvidence:
    """Finite profile, tonal-shape, and temporal-stability evidence."""

    best_score: float
    runner_up_score: float
    margin: float
    normalized_entropy: float
    dominant_pitch_class_concentration: float
    temporal_stability: float
    conditions: tuple[tuple[str, bool], ...]


@dataclass(frozen=True)
class ProfileGateConfig:
    name: str
    required_conditions: tuple[str, ...]
    margin_threshold: float
    best_score_threshold: float
    concentration_threshold: float
    stability_threshold: float
    version: str = PROFILE_GATE_VERSION


@dataclass(frozen=True)
class GatedKeyProfileResult:
    status: str
    root: str | None
    root_index: int | None
    mode: str | None
    canonical_key: str | None
    abstention_reasons: tuple[str, ...]
    gate_name: str
    gate_version: str
    evidence: ProfileGateEvidence | None


@dataclass(frozen=True)
class SyntheticProfileFixture:
    """Public deterministic chroma statistics used solely for gate calibration."""

    name: str
    group: str
    chroma_mean: np.ndarray
    chroma_std: np.ndarray
    root: str | None = None
    mode: str | None = None


def _abstained_ranking() -> KeyProfileRanking:
    return KeyProfileRanking(
        status="abstained", root=None, root_index=None, mode=None, canonical_key=None,
        best_score=None, runner_up_score=None, margin=None, next_distinct_root_score=None,
        next_distinct_root_margin=None, evidence_kind=PROFILE_EVIDENCE_KIND,
        evidence_version=PROFILE_EVIDENCE_VERSION, hypotheses=(),
    )


def _as_finite_chroma(values: np.ndarray | tuple[float, ...] | list[float]) -> np.ndarray | None:
    chroma = np.asarray(values, dtype=np.float64).reshape(-1)
    if chroma.size != 12 or not np.isfinite(chroma).all():
        return None
    return chroma


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
    """Rank all rotated major/minor profiles with deterministic tie ordering."""
    values = _as_finite_chroma(chroma_mean)
    if values is None:
        return _abstained_ranking()
    profiles = (("maj", np.asarray(MAJOR_KEY_PROFILE)), ("min", np.asarray(MINOR_KEY_PROFILE)))
    hypotheses: list[KeyProfileHypothesis] = []
    for root_index, root in enumerate(PITCH_CLASSES):
        for mode, profile in profiles:
            score = _pearson_score(values, np.roll(profile, root_index))
            if score is None:
                return _abstained_ranking()
            canonical_key = format_key_signature(root, mode)
            assert canonical_key is not None
            hypotheses.append(KeyProfileHypothesis(root, root_index, mode, canonical_key, score))
    mode_order = {"maj": 0, "min": 1}
    hypotheses.sort(key=lambda item: (-item.score, item.root_index, mode_order[item.mode]))
    best, runner_up = hypotheses[:2]
    next_distinct_root = next(item for item in hypotheses[1:] if item.root_index != best.root_index)
    return KeyProfileRanking(
        status="ranked_only", root=best.root, root_index=best.root_index, mode=best.mode,
        canonical_key=best.canonical_key, best_score=best.score, runner_up_score=runner_up.score,
        margin=best.score - runner_up.score, next_distinct_root_score=next_distinct_root.score,
        next_distinct_root_margin=best.score - next_distinct_root.score,
        evidence_kind=PROFILE_EVIDENCE_KIND, evidence_version=PROFILE_EVIDENCE_VERSION,
        hypotheses=tuple(hypotheses),
    )


def _shape_metrics(chroma_mean: np.ndarray, chroma_std: np.ndarray) -> tuple[float, float, float]:
    total = float(np.sum(chroma_mean))
    if total <= _CHROMA_EPSILON:
        distribution = np.full(12, 1.0 / 12.0, dtype=np.float64)
        concentration = 0.0
    else:
        distribution = chroma_mean / total
        concentration = float(np.max(distribution))
    entropy = float(-np.sum(distribution * np.log(np.maximum(distribution, _CHROMA_EPSILON))) / np.log(12.0))
    cv = float(np.mean(chroma_std / np.maximum(chroma_mean, _CHROMA_EPSILON)))
    stability = 1.0 / (1.0 + cv) if np.isfinite(cv) and cv >= 0.0 else 0.0
    return (
        max(0.0, min(1.0, entropy)),
        max(0.0, min(1.0, concentration)),
        max(0.0, min(1.0, stability)),
    )


def _evidence_for(
    chroma_mean: np.ndarray | tuple[float, ...] | list[float],
    chroma_std: np.ndarray | tuple[float, ...] | list[float],
    config: ProfileGateConfig,
) -> tuple[KeyProfileRanking, ProfileGateEvidence | None]:
    mean = _as_finite_chroma(chroma_mean)
    std = _as_finite_chroma(chroma_std)
    ranking = rank_key_profiles(chroma_mean)
    if (
        mean is None
        or std is None
        or np.any(mean < 0.0)
        or np.any(std < 0.0)
        or ranking.status != "ranked_only"
    ):
        return ranking, None
    assert ranking.best_score is not None
    assert ranking.runner_up_score is not None
    assert ranking.margin is not None
    entropy, concentration, stability = _shape_metrics(mean, std)
    values = {
        "best_profile_score": ranking.best_score >= config.best_score_threshold,
        "chroma_concentration": concentration >= config.concentration_threshold,
        "margin": ranking.margin >= config.margin_threshold,
        "temporal_stability": stability >= config.stability_threshold,
    }
    return ranking, ProfileGateEvidence(
        ranking.best_score, ranking.runner_up_score, ranking.margin, entropy, concentration, stability,
        tuple(sorted(values.items())),
    )


def _gate_with_config(
    chroma_mean: np.ndarray | tuple[float, ...] | list[float],
    chroma_std: np.ndarray | tuple[float, ...] | list[float],
    config: ProfileGateConfig,
) -> GatedKeyProfileResult:
    ranking, evidence = _evidence_for(chroma_mean, chroma_std, config)
    if evidence is None:
        reasons = ("invalid_chroma_statistics",) if ranking.status == "ranked_only" else ("no_profile_hypothesis",)
        return GatedKeyProfileResult("abstained", None, None, None, None, reasons, config.name, config.version, None)
    conditions = dict(evidence.conditions)
    failed = tuple(sorted(condition for condition in config.required_conditions if not conditions[condition]))
    if failed:
        return GatedKeyProfileResult("abstained", None, None, None, None, failed, config.name, config.version, evidence)
    return GatedKeyProfileResult(
        "resolved", ranking.root, ranking.root_index, ranking.mode, ranking.canonical_key,
        (), config.name, config.version, evidence,
    )


def synthetic_profile_gate_fixtures() -> tuple[SyntheticProfileFixture, ...]:
    """Return public deterministic calibration fixtures without private data.

    Profile-shaped transient means intentionally have high temporal variation.
    They model the margin-only failure that requires independent stability
    evidence, while thresholds remain derived from clear fixtures only.
    """
    fixtures: list[SyntheticProfileFixture] = []
    for mode, profile in (("maj", MAJOR_KEY_PROFILE), ("min", MINOR_KEY_PROFILE)):
        for root_index, root in enumerate(PITCH_CLASSES):
            mean = np.roll(np.asarray(profile, dtype=np.float64), root_index)
            fixtures.append(SyntheticProfileFixture(
                f"clear_{root}_{mode}", "clear", mean,
                np.maximum(mean * 0.01, _CHROMA_EPSILON), root, mode,
            ))
    ambiguous_means = {
        "single_note": np.array([1.0] + [0.0] * 11),
        "octave": np.array([2.0] + [0.0] * 11),
        "root_fifth": np.array([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0] + [0.0] * 4),
        "major_minor_blend": np.array([1.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 1.0] + [0.0] * 4),
    }
    for name, mean in ambiguous_means.items():
        fixtures.append(SyntheticProfileFixture(name, "ambiguous", mean, np.maximum(mean * 0.01, _CHROMA_EPSILON)))
    rng = np.random.default_rng(594)
    percussive_means = {
        "pulse_train": np.roll(np.asarray(MAJOR_KEY_PROFILE, dtype=np.float64), 7),
        "kick_transient": np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0] + [0.0] * 3),
        "broadband_noise": 0.2 + rng.random(12),
        "hihat_noise": np.roll(np.asarray(MINOR_KEY_PROFILE, dtype=np.float64), 2),
    }
    for name, mean in percussive_means.items():
        fixtures.append(SyntheticProfileFixture(name, "percussive", mean, np.maximum(mean * 2.0, _CHROMA_EPSILON)))
    return tuple(fixtures)


def _threshold_from_clear(values: list[float], *, lower: float, upper: float, value_range: float) -> float:
    return max(lower, min(upper, min(values) - value_range * PROFILE_GATE_SAFETY_FRACTION))


def _calibration_configurations() -> tuple[ProfileGateConfig, ...]:
    fixtures = synthetic_profile_gate_fixtures()
    probe = ProfileGateConfig("probe", (), -1.0, -1.0, 0.0, 0.0)
    clear_evidence = [
        evidence for fixture in fixtures if fixture.group == "clear"
        for _, evidence in [_evidence_for(fixture.chroma_mean, fixture.chroma_std, probe)]
        if evidence is not None
    ]
    if len(clear_evidence) != sum(fixture.group == "clear" for fixture in fixtures):
        raise RuntimeError("synthetic clear fixture calibration is incomplete")
    margin = _threshold_from_clear([item.margin for item in clear_evidence], lower=0.0, upper=2.0, value_range=2.0)
    score = _threshold_from_clear([item.best_score for item in clear_evidence], lower=-1.0, upper=1.0, value_range=2.0)
    concentration = _threshold_from_clear(
        [item.dominant_pitch_class_concentration for item in clear_evidence], lower=0.0, upper=1.0, value_range=1.0
    )
    stability = _threshold_from_clear(
        [item.temporal_stability for item in clear_evidence], lower=0.0, upper=1.0, value_range=1.0
    )
    return (
        ProfileGateConfig("G0", ("margin",), margin, score, concentration, stability),
        ProfileGateConfig("G1", ("margin", "best_profile_score"), margin, score, concentration, stability),
        ProfileGateConfig("G2", ("margin", "chroma_concentration"), margin, score, concentration, stability),
        ProfileGateConfig("G3", ("margin", "temporal_stability"), margin, score, concentration, stability),
        ProfileGateConfig("G4", ("margin", "best_profile_score", "temporal_stability"), margin, score, concentration, stability),
    )


def _is_viable_synthetic_gate(config: ProfileGateConfig) -> bool:
    for fixture in synthetic_profile_gate_fixtures():
        result = _gate_with_config(fixture.chroma_mean, fixture.chroma_std, config)
        if fixture.group == "clear":
            if result.status != "resolved" or result.root != fixture.root or result.mode != fixture.mode:
                return False
        elif result.status != "abstained":
            return False
    return True


def _select_synthetic_gate() -> ProfileGateConfig:
    for config in _calibration_configurations():
        if _is_viable_synthetic_gate(config):
            return config
    return ProfileGateConfig("NO_DEFENSIBLE_SYNTHETIC_GATE", (), 2.0, 1.0, 1.0, 1.0)


DEFAULT_PROFILE_GATE = _select_synthetic_gate()


def gate_ranked_key_profile(
    chroma_mean: np.ndarray | tuple[float, ...] | list[float],
    chroma_std: np.ndarray | tuple[float, ...] | list[float],
) -> GatedKeyProfileResult:
    """Resolve a raw ranking only when the selected synthetic gate passes."""
    if DEFAULT_PROFILE_GATE.name == "NO_DEFENSIBLE_SYNTHETIC_GATE":
        _, evidence = _evidence_for(chroma_mean, chroma_std, DEFAULT_PROFILE_GATE)
        return GatedKeyProfileResult(
            "abstained", None, None, None, None, ("no_defensible_synthetic_gate",),
            DEFAULT_PROFILE_GATE.name, DEFAULT_PROFILE_GATE.version, evidence,
        )
    return _gate_with_config(chroma_mean, chroma_std, DEFAULT_PROFILE_GATE)


def _distribution(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "min": None, "median": None, "p90": None, "max": None}
    array = np.asarray(values, dtype=np.float64)
    return {
        "count": int(array.size), "min": float(np.min(array)), "median": float(np.median(array)),
        "p90": float(np.percentile(array, 90)), "max": float(np.max(array)),
    }


def _margin_distribution(rankings: list[KeyProfileRanking]) -> dict[str, float | int | None]:
    return _distribution([ranking.margin for ranking in rankings if ranking.margin is not None])


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


def characterize_synthetic_gate() -> dict[str, dict]:
    """Return public aggregate calibration evidence and bounded gate outcomes."""
    grouped: dict[str, list[ProfileGateEvidence]] = {"clear": [], "ambiguous": [], "percussive": []}
    probe = ProfileGateConfig("probe", (), -1.0, -1.0, 0.0, 0.0)
    for fixture in synthetic_profile_gate_fixtures():
        _, evidence = _evidence_for(fixture.chroma_mean, fixture.chroma_std, probe)
        if evidence is not None:
            grouped[fixture.group].append(evidence)

    def describe(items: list[ProfileGateEvidence]) -> dict:
        return {
            "count": len(items),
            "best_score": _distribution([item.best_score for item in items]),
            "margin": _distribution([item.margin for item in items]),
            "normalized_entropy": _distribution([item.normalized_entropy for item in items]),
            "dominant_pitch_class_concentration": _distribution([item.dominant_pitch_class_concentration for item in items]),
            "temporal_stability": _distribution([item.temporal_stability for item in items]),
        }

    return {
        "clear": describe(grouped["clear"]),
        "ambiguous": describe(grouped["ambiguous"]),
        "percussive": describe(grouped["percussive"]),
        "gate_candidates": {
            config.name: {
                "required_conditions": list(config.required_conditions),
                "margin_threshold": config.margin_threshold,
                "best_score_threshold": config.best_score_threshold,
                "concentration_threshold": config.concentration_threshold,
                "stability_threshold": config.stability_threshold,
                "viable": _is_viable_synthetic_gate(config),
            }
            for config in _calibration_configurations()
        },
    }


__all__ = [
    "DEFAULT_PROFILE_GATE", "GatedKeyProfileResult", "KeyProfileHypothesis", "KeyProfileRanking",
    "MAJOR_KEY_PROFILE", "MINOR_KEY_PROFILE", "PROFILE_EVIDENCE_KIND", "PROFILE_EVIDENCE_VERSION",
    "PROFILE_GATE_VERSION", "PITCH_CLASSES", "ProfileGateConfig", "ProfileGateEvidence",
    "SyntheticProfileFixture", "characterize_synthetic_gate", "characterize_synthetic_margins",
    "gate_ranked_key_profile", "rank_key_profiles", "synthetic_profile_gate_fixtures",
]
