"""Deterministic, reproducible scoring of loop candidates (issue #252).

This module consumes a loop candidate produced by :mod:`src.loop_candidates`
and a monophonic waveform slice of exactly that candidate's sample range, and
returns separated, traceable score components plus hard-exclusion reasons.

Design contract
---------------
* Pure, deterministic core logic. No file IO, no database, no network, no model
  download, no audio mutation, no crossfade.
* Every score component has an explicit name, value, value range and meaning.
  Missing evidence is represented by ``status != "ok"`` and ``value is None``;
  no dummy zeros are invented.
* Hard exclusions are reported separately from soft scores in ``reject_reasons``.
* Thresholds are configurable via :class:`LoopScoringConfig` and must stay
  provisional until the Techno pilot (#256) calibrates them. No global fixed
  pilot threshold is baked into the scoring logic.

The loop score contract is intentionally disjoint from section scoring (#267).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from .loop_candidates import LoopCandidate, LoopSourceKind

# Score component names
SEAM_CONTINUITY = "seam_continuity"
INTERNAL_STABILITY = "internal_stability"
GROOVE_STABILITY = "groove_stability"
ENERGY_DISTRIBUTION = "energy_distribution"
EDGE_SILENCE_RISK = "edge_silence_risk"
TRANSITION_BLEED_RISK = "transition_bleed_risk"
VOCAL_FX_EDGE_RISK = "vocal_fx_edge_risk"

# Hard-reject reason codes (separate from numeric scores)
REJECT_SEAM_DISCONTINUITY = "SEAM_DISCONTINUITY"
REJECT_EDGE_SILENCE = "EDGE_SILENCE"
REJECT_TOO_QUIET = "TOO_QUIET"

ScoreComponentStatus = Literal["ok", "not_evaluated", "unknown", "failed"]
LoopScoreStatus = Literal["ok", "excluded", "no_evidence"]

_COMPONENT_MEANING: dict[str, str] = {
    SEAM_CONTINUITY: (
        "End-to-start loop continuity; higher means the loop seam is smoother "
        "and less likely to click when played repeatedly."
    ),
    INTERNAL_STABILITY: (
        "Consistency of bar energy across the loop; higher means steadier "
        "internal repetition (less drift between bars)."
    ),
    GROOVE_STABILITY: (
        "Similarity of per-bar onset / groove patterns; higher means a more "
        "consistent rhythmic groove across the loop."
    ),
    ENERGY_DISTRIBUTION: (
        "Dynamic spread of energy across the loop; higher means more energetic "
        "variation, lower means a flatter, more static signal."
    ),
    EDGE_SILENCE_RISK: (
        "Risk that the loop edges are silent or near-silent; higher means a "
        "more likely dead start or end."
    ),
    TRANSITION_BLEED_RISK: (
        "Risk from crossing a neutral section boundary inside the loop "
        "(transition bleed); 1.0 when a crossing is present, else 0.0."
    ),
    VOCAL_FX_EDGE_RISK: (
        "Risk from explicit vocal / FX edge evidence; only set when real "
        "evidence is supplied, otherwise not evaluated (never invented)."
    ),
}

_COMPONENT_RANGE: tuple[float, float] = (0.0, 1.0)


@dataclass(frozen=True)
class LoopEdgeRiskEvidence:
    side: Literal["start", "end", "any"]
    kind: Literal["vocal", "fx"]
    evidence_ref: str
    note: str = ""


@dataclass(frozen=True)
class LoopScoringThresholds:
    edge_window_ms: float = 5.0
    seam_hard_min_continuity: float = 0.35
    silence_edge_rms_max: float = 1e-3
    min_loop_rms: float = 5e-3

    def __post_init__(self) -> None:
        if self.edge_window_ms <= 0:
            raise ValueError("edge_window_ms must be positive")
        if not 0.0 <= self.seam_hard_min_continuity <= 1.0:
            raise ValueError("seam_hard_min_continuity must be in [0, 1]")
        if self.silence_edge_rms_max < 0:
            raise ValueError("silence_edge_rms_max must be non-negative")
        if self.min_loop_rms < 0:
            raise ValueError("min_loop_rms must be non-negative")

    def as_dict(self) -> dict[str, float]:
        return {
            "edge_window_ms": self.edge_window_ms,
            "seam_hard_min_continuity": self.seam_hard_min_continuity,
            "silence_edge_rms_max": self.silence_edge_rms_max,
            "min_loop_rms": self.min_loop_rms,
        }


@dataclass
class LoopScoringConfig:
    thresholds: LoopScoringThresholds = field(default_factory=LoopScoringThresholds)
    source_kind_thresholds: Mapping[str, LoopScoringThresholds] = field(
        default_factory=dict
    )
    weights: Mapping[str, float] = field(default_factory=dict)
    include_summary_score: bool = True

    def __post_init__(self) -> None:
        if not 0.0 <= self.thresholds.seam_hard_min_continuity <= 1.0:
            raise ValueError("invalid thresholds")
        for sk, th in self.source_kind_thresholds.items():
            if not isinstance(th, LoopScoringThresholds):
                raise TypeError(f"invalid thresholds for source_kind {sk}")

    def resolve_thresholds(self, source_kind: str) -> LoopScoringThresholds:
        return self.source_kind_thresholds.get(source_kind, self.thresholds)

    def to_dict(self) -> dict[str, object]:
        return {
            "thresholds": self.thresholds.as_dict(),
            "source_kind_thresholds": {
                sk: th.as_dict() for sk, th in self.source_kind_thresholds.items()
            },
            "weights": dict(self.weights),
            "include_summary_score": self.include_summary_score,
        }


def default_weights() -> dict[str, float]:
    # Provisional v1 weights. Documented, configurable, NOT a universal truth.
    return {
        SEAM_CONTINUITY: 0.30,
        INTERNAL_STABILITY: 0.20,
        GROOVE_STABILITY: 0.20,
        ENERGY_DISTRIBUTION: 0.15,
        TRANSITION_BLEED_RISK: 0.05,
        EDGE_SILENCE_RISK: 0.05,
        VOCAL_FX_EDGE_RISK: 0.05,
    }


def default_loop_scoring_config() -> LoopScoringConfig:
    return LoopScoringConfig(weights=default_weights())


@dataclass(frozen=True)
class ScoreComponent:
    name: str
    value: float | None
    value_range: tuple[float, float] | None
    meaning: str
    status: ScoreComponentStatus

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "value": self.value,
            "range": list(self.value_range) if self.value_range else None,
            "meaning": self.meaning,
            "status": self.status,
        }


@dataclass(frozen=True)
class LoopCandidateRef:
    start_sample: int
    end_sample_exclusive: int
    start_bar: int
    end_bar_exclusive: int
    bar_count: int
    n_samples: int


@dataclass(frozen=True)
class LoopScoreResult:
    candidate_ref: LoopCandidateRef
    source_identity: dict[str, object]
    status: LoopScoreStatus
    score_components: dict[str, ScoreComponent]
    hard_rejected: bool
    reject_reasons: tuple[str, ...]
    config_provenance: dict[str, object]
    summary_score: float | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "candidate_ref": self.candidate_ref.__dict__,
            "source_identity": self.source_identity,
            "score_components": {
                name: comp.as_dict() for name, comp in self.score_components.items()
            },
            "hard_rejected": self.hard_rejected,
            "reject_reasons": list(self.reject_reasons),
            "summary_score": self.summary_score,
            "config_provenance": self.config_provenance,
        }

    def as_candidate_dict(self) -> dict[str, object]:
        """Map to the Asset Manifest v1 ``candidate`` block (#250 §10)."""
        return {
            "status": "rejected" if self.hard_rejected else "candidate",
            "score_components": {
                name: comp.as_dict() for name, comp in self.score_components.items()
            },
            "excluded": self.hard_rejected,
            "reject_reasons": list(self.reject_reasons),
        }


# --- internal helpers ------------------------------------------------------


def _rms(arr: np.ndarray) -> float:
    arr = np.asarray(arr, dtype=float)
    if arr.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(arr))))


def _center(arr: np.ndarray) -> np.ndarray:
    arr = np.asarray(arr, dtype=float)
    return arr - np.mean(arr)


def _cosine(left: np.ndarray, right: np.ndarray) -> float:
    left = np.asarray(left, dtype=float).reshape(-1)
    right = np.asarray(right, dtype=float).reshape(-1)
    norm_l = float(np.linalg.norm(left))
    norm_r = float(np.linalg.norm(right))
    if norm_l <= 1e-12 and norm_r <= 1e-12:
        return 1.0
    if norm_l <= 1e-12 or norm_r <= 1e-12:
        return 0.0
    return float(np.dot(left, right) / (norm_l * norm_r))


def _segment_rms(waveform: np.ndarray, n_segments: int) -> np.ndarray:
    n_segments = max(1, n_segments)
    if waveform.size == 0:
        return np.zeros(0)
    splits = np.array_split(waveform, n_segments)
    return np.asarray([_rms(seg) for seg in splits], dtype=float)


def _onset_envelope(waveform: np.ndarray) -> np.ndarray:
    waveform = np.asarray(waveform, dtype=float).reshape(-1)
    if waveform.size == 0:
        return np.zeros(0)
    diff = np.abs(np.diff(waveform, prepend=waveform[:1]))
    return diff


def _bar_onset_pattern(env: np.ndarray, bins: int = 8) -> np.ndarray:
    env = np.asarray(env, dtype=float).reshape(-1)
    if env.size == 0:
        return np.zeros(bins)
    parts = np.array_split(env, bins)
    return np.asarray([float(np.sum(part)) for part in parts], dtype=float)


def _stability_like(values: np.ndarray) -> float | None:
    values = np.asarray(values, dtype=float)
    if values.size < 2:
        return None
    mean = float(np.mean(values))
    std = float(np.std(values))
    if mean <= 1e-12:
        return 0.0
    return float(np.clip(1.0 - std / mean, 0.0, 1.0))


def _seam_continuity(start: np.ndarray, end: np.ndarray) -> float:
    rms_s = _rms(start)
    rms_e = _rms(end)
    denom = rms_s + rms_e
    amp = abs(rms_s - rms_e) / denom if denom > 1e-12 else 0.0
    shape = _cosine(_center(start), _center(end))
    shape_discontinuity = (1.0 - shape) / 2.0
    discontinuity = 0.5 * amp + 0.5 * shape_discontinuity
    return float(np.clip(1.0 - discontinuity, 0.0, 1.0))


def _edge_silence_risk(start_rms: float, end_rms: float, silence_max: float) -> float:
    reference = max(silence_max * 20.0, 1e-9)
    risk_start = 1.0 - min(start_rms / reference, 1.0)
    risk_end = 1.0 - min(end_rms / reference, 1.0)
    return float(max(risk_start, risk_end))


# --- main entry point ------------------------------------------------------


def score_loop_candidate(
    candidate: LoopCandidate,
    waveform: np.ndarray | None,
    *,
    sample_rate: int,
    source_kind: LoopSourceKind | None = None,
    vocal_fx_evidence: Sequence[LoopEdgeRiskEvidence] | None = None,
    config: LoopScoringConfig | None = None,
) -> LoopScoreResult:
    if config is None:
        config = default_loop_scoring_config()
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")

    kind = source_kind or candidate.source.source_kind
    thresholds = config.resolve_thresholds(kind)
    edge_samples = max(1, round(thresholds.edge_window_ms / 1000.0 * sample_rate))

    source_identity = candidate.source.as_dict()

    ref = LoopCandidateRef(
        start_sample=candidate.start_sample,
        end_sample_exclusive=candidate.end_sample_exclusive,
        start_bar=candidate.start_bar,
        end_bar_exclusive=candidate.end_bar_exclusive,
        bar_count=candidate.bar_count,
        n_samples=candidate.n_samples,
    )

    if waveform is None:
        return _no_evidence(
            ref, source_identity, config, sample_rate, kind, edge_samples
        )

    waveform = np.asarray(waveform, dtype=np.float32).reshape(-1)
    if waveform.size != candidate.n_samples or waveform.size == 0:
        raise ValueError(
            "waveform length must equal candidate.n_samples and be non-empty"
        )
    if not np.all(np.isfinite(waveform)):
        raise ValueError("waveform contains non-finite values")

    components: dict[str, ScoreComponent] = {}
    reject_reasons: list[str] = []

    start_edge = waveform[:edge_samples]
    end_edge = waveform[-edge_samples:]
    start_rms = _rms(start_edge)
    end_rms = _rms(end_edge)
    loop_rms = _rms(waveform)

    # Seam (end-to-start)
    seam = _seam_continuity(start_edge, end_edge)
    components[SEAM_CONTINUITY] = ScoreComponent(
        name=SEAM_CONTINUITY,
        value=seam,
        value_range=_COMPONENT_RANGE,
        meaning=_COMPONENT_MEANING[SEAM_CONTINUITY],
        status="ok",
    )
    if seam < thresholds.seam_hard_min_continuity:
        reject_reasons.append(REJECT_SEAM_DISCONTINUITY)

    # Internal stability (bar energy consistency)
    internal = _stability_like(_segment_rms(waveform, candidate.bar_count))
    components[INTERNAL_STABILITY] = ScoreComponent(
        name=INTERNAL_STABILITY,
        value=internal,
        value_range=_COMPONENT_RANGE,
        meaning=_COMPONENT_MEANING[INTERNAL_STABILITY],
        status="ok" if internal is not None else "not_evaluated",
    )

    # Groove / onset stability (per-bar onset pattern similarity)
    env = _onset_envelope(waveform)
    bar_envs = np.array_split(env, max(1, candidate.bar_count))
    patterns = [_bar_onset_pattern(bar_env) for bar_env in bar_envs]
    groove: float | None = None
    if len(patterns) >= 2:
        sims = [_cosine(patterns[i - 1], patterns[i]) for i in range(1, len(patterns))]
        groove = float(np.clip(float(np.mean(sims)), 0.0, 1.0))
    components[GROOVE_STABILITY] = ScoreComponent(
        name=GROOVE_STABILITY,
        value=groove,
        value_range=_COMPONENT_RANGE,
        meaning=_COMPONENT_MEANING[GROOVE_STABILITY],
        status="ok" if groove is not None else "not_evaluated",
    )

    # Energy distribution (dynamic spread across frames)
    energy = _stability_like(_segment_rms(waveform, 32))
    components[ENERGY_DISTRIBUTION] = ScoreComponent(
        name=ENERGY_DISTRIBUTION,
        value=energy,
        value_range=_COMPONENT_RANGE,
        meaning=_COMPONENT_MEANING[ENERGY_DISTRIBUTION],
        status="ok" if energy is not None else "not_evaluated",
    )

    # Edge silence
    edge_risk = _edge_silence_risk(start_rms, end_rms, thresholds.silence_edge_rms_max)
    components[EDGE_SILENCE_RISK] = ScoreComponent(
        name=EDGE_SILENCE_RISK,
        value=edge_risk,
        value_range=_COMPONENT_RANGE,
        meaning=_COMPONENT_MEANING[EDGE_SILENCE_RISK],
        status="ok",
    )
    if (
        start_rms < thresholds.silence_edge_rms_max
        or end_rms < thresholds.silence_edge_rms_max
    ):
        reject_reasons.append(REJECT_EDGE_SILENCE)
    if loop_rms < thresholds.min_loop_rms:
        reject_reasons.append(REJECT_TOO_QUIET)

    # Transition bleed (reuse #251 section-crossing evidence; never auto-rejects)
    crosses = bool(candidate.boundary.section_crossing.crosses)
    components[TRANSITION_BLEED_RISK] = ScoreComponent(
        name=TRANSITION_BLEED_RISK,
        value=1.0 if crosses else 0.0,
        value_range=_COMPONENT_RANGE,
        meaning=_COMPONENT_MEANING[TRANSITION_BLEED_RISK],
        status="ok",
    )

    # Vocal / FX edge risk (only when real evidence is supplied; never invented)
    if vocal_fx_evidence:
        components[VOCAL_FX_EDGE_RISK] = ScoreComponent(
            name=VOCAL_FX_EDGE_RISK,
            value=1.0,
            value_range=_COMPONENT_RANGE,
            meaning=_COMPONENT_MEANING[VOCAL_FX_EDGE_RISK],
            status="ok",
        )
    else:
        components[VOCAL_FX_EDGE_RISK] = ScoreComponent(
            name=VOCAL_FX_EDGE_RISK,
            value=None,
            value_range=_COMPONENT_RANGE,
            meaning=_COMPONENT_MEANING[VOCAL_FX_EDGE_RISK],
            status="not_evaluated",
        )

    hard_rejected = len(reject_reasons) > 0
    summary = (
        _summary_score(components, config) if config.include_summary_score else None
    )

    provenance = config.to_dict()
    provenance["provisional"] = True
    provenance["source_kind"] = kind
    provenance["sample_rate"] = sample_rate
    provenance["edge_window_samples"] = edge_samples
    provenance["note"] = (
        "Thresholds are provisional v1 defaults; calibrate via #256 before "
        "treating any value as a final global truth."
    )

    return LoopScoreResult(
        candidate_ref=ref,
        source_identity=source_identity,
        status="excluded" if hard_rejected else "ok",
        score_components=components,
        hard_rejected=hard_rejected,
        reject_reasons=tuple(reject_reasons),
        config_provenance=provenance,
        summary_score=summary,
    )


def _no_evidence(
    ref: LoopCandidateRef,
    source_identity: dict[str, object],
    config: LoopScoringConfig,
    sample_rate: int,
    kind: str,
    edge_samples: int,
) -> LoopScoreResult:
    components = {
        name: ScoreComponent(
            name=name,
            value=None,
            value_range=_COMPONENT_RANGE,
            meaning=_COMPONENT_MEANING[name],
            status="not_evaluated",
        )
        for name in (
            SEAM_CONTINUITY,
            INTERNAL_STABILITY,
            GROOVE_STABILITY,
            ENERGY_DISTRIBUTION,
            EDGE_SILENCE_RISK,
            TRANSITION_BLEED_RISK,
            VOCAL_FX_EDGE_RISK,
        )
    }
    provenance = config.to_dict()
    provenance["provisional"] = True
    provenance["source_kind"] = kind
    provenance["sample_rate"] = sample_rate
    provenance["edge_window_samples"] = edge_samples
    provenance["note"] = "No waveform supplied; scoring is status-based (no evidence)."
    return LoopScoreResult(
        candidate_ref=ref,
        source_identity=source_identity,
        status="no_evidence",
        score_components=components,
        hard_rejected=False,
        reject_reasons=(),
        config_provenance=provenance,
        summary_score=None,
    )


def _summary_score(
    components: Mapping[str, ScoreComponent], config: LoopScoringConfig
) -> float | None:
    weights = config.weights or default_weights()
    soft_total = 0.0
    soft_weight = 0.0
    for name, comp in components.items():
        w = weights.get(name, 0.0)
        if w <= 0.0 or comp.value is None or comp.status != "ok":
            continue
        if name in {
            TRANSITION_BLEED_RISK,
            EDGE_SILENCE_RISK,
            VOCAL_FX_EDGE_RISK,
        }:
            continue  # penalties applied separately below
        soft_total += w * comp.value
        soft_weight += w
    if soft_weight <= 0.0:
        return None
    score = soft_total / soft_weight
    penalty = 0.0
    for name in (TRANSITION_BLEED_RISK, EDGE_SILENCE_RISK, VOCAL_FX_EDGE_RISK):
        w = weights.get(name, 0.0)
        comp = components.get(name)
        if w > 0.0 and comp is not None and comp.value is not None:
            penalty += w * comp.value
    return float(np.clip(score - penalty, 0.0, 1.0))


__all__ = [
    "EDGE_SILENCE_RISK",
    "ENERGY_DISTRIBUTION",
    "GROOVE_STABILITY",
    "INTERNAL_STABILITY",
    "REJECT_EDGE_SILENCE",
    "REJECT_SEAM_DISCONTINUITY",
    "REJECT_TOO_QUIET",
    "SEAM_CONTINUITY",
    "TRANSITION_BLEED_RISK",
    "VOCAL_FX_EDGE_RISK",
    "LoopCandidateRef",
    "LoopEdgeRiskEvidence",
    "LoopScoreResult",
    "LoopScoringConfig",
    "LoopScoringThresholds",
    "ScoreComponent",
    "default_loop_scoring_config",
    "default_weights",
    "score_loop_candidate",
]
