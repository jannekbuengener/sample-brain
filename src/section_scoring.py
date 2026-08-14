"""Deterministic scoring of section asset candidates (issue #267).

This module consumes a section candidate produced by :mod:`src.section_candidates`
and optional, already-computed StructureV1 ``bar_features`` evidence, and returns
separated, traceable score components plus hard-exclusion reasons.

Design contract
---------------
* Pure, deterministic core logic. No file IO, no database, no network, no model
  download, no audio mutation, no rendering, no crossfade.
* Every score component has an explicit name, value, value range and meaning.
  Missing evidence is represented by ``status != "ok"`` and ``value is None``;
  no dummy zeros are invented.
* Section coherence and musical development are distinct components and are
  explicitly **not** loop repetition or seam continuity.
* Boundary security and role security are strictly separate fields; there is no
  universal confidence value that mixes the two (#241).
* Hard exclusions are reported separately from soft scores in ``reject_reasons``.
* Thresholds and weights are configurable via :class:`SectionScoringConfig` and
  stay provisional until the Techno pilot (#256) calibrates them. No final global
  pilot threshold is baked into the scoring logic.
* Vocal/FX edge risk is only scored when real explicit evidence is supplied;
  it is never invented.

The section score contract is intentionally disjoint from loop scoring (#252).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from .arrangement_classifier import SectionRole
from .section_candidates import SectionCandidate

# Score component names
SECTION_COHERENCE = "section_coherence"
MUSICAL_DEVELOPMENT = "musical_development"
BOUNDARY_SECURITY = "boundary_security"
ROLE_SECURITY = "role_security"
TRANSITION_RISK = "transition_risk"
VOCAL_FX_EDGE_RISK = "vocal_fx_edge_risk"

# Hard-reject reason codes (separate from numeric scores)
REJECT_INVALID_RANGE = "INVALID_RANGE"

ScoreComponentStatus = Literal["ok", "not_evaluated", "unknown", "failed"]
SectionScoreStatus = Literal["ok", "excluded", "no_evidence"]

_COMPONENT_RANGE: tuple[float, float] = (0.0, 1.0)

_COMPONENT_MEANING: dict[str, str] = {
    SECTION_COHERENCE: (
        "Internal musical coherence of the section: how self-similar, recurrent "
        "and rhythmically/timbrally consistent the bars within the section are. "
        "Higher means the section holds together as one musical idea. This is "
        "NOT loop repetition or seam continuity."
    ),
    MUSICAL_DEVELOPMENT: (
        "Whether the section follows a sensible musical arc across its bars "
        "(e.g. a steady build or drop). A clear, consistent directional movement "
        "scores high; a flat/steady section scores neutral (0.5, not punished); "
        "this is not the same as stability and change is never penalised."
    ),
    BOUNDARY_SECURITY: (
        "Safety of the neutral section boundaries, derived from the boundary "
        "status and optional relative boundary quality (0-1). Separated from the "
        "arrangement role; an uncertain boundary never implies an uncertain role."
    ),
    ROLE_SECURITY: (
        "Confidence in the effective arrangement role, derived from the role "
        "status (or manual override). Separated from boundary security; "
        "``unknown`` is a valid, non-rejected role with a modest score."
    ),
    TRANSITION_RISK: (
        "Risk from an internal bar-to-bar transition inside the section "
        "(neighbor delta). Higher means a larger internal jump that may reduce "
        "clean usability. Separate from hard rejection."
    ),
    VOCAL_FX_EDGE_RISK: (
        "Risk from explicit vocal / FX edge evidence; only set when real evidence "
        "is supplied, otherwise not evaluated (never invented)."
    ),
}

# Features used for internal coherence (higher = more cohesive).
_COHERENCE_FEATURES: tuple[tuple[str, float], ...] = (
    ("self_similarity", 1.0),
    ("recurrence", 1.0),
    ("rhythm_stability", 1.0),
    ("timbre_delta", -1.0),  # lower delta => more consistent texture
    ("spectral_delta", -1.0),
)


@dataclass(frozen=True)
class SectionEdgeRiskEvidence:
    side: Literal["start", "end", "any"]
    kind: Literal["vocal", "fx"]
    evidence_ref: str
    note: str = ""


@dataclass(frozen=True)
class SectionScoringConfig:
    weights: Mapping[str, float] = field(default_factory=dict)
    boundary_status_scores: Mapping[str, float] = field(default_factory=dict)
    role_status_scores: Mapping[str, float] = field(default_factory=dict)
    role_manual_certainty: float = 0.9
    include_summary_score: bool = True

    def __post_init__(self) -> None:
        if not 0.0 <= self.role_manual_certainty <= 1.0:
            raise ValueError("role_manual_certainty must be in [0, 1]")
        for name in (
            "boundary_status_scores",
            "role_status_scores",
        ):
            mapping = dict(getattr(self, name))
            for key, value in mapping.items():
                if not 0.0 <= float(value) <= 1.0:
                    raise ValueError(f"{name}[{key}] must be in [0, 1]")
            object.__setattr__(self, name, mapping)

    def to_dict(self) -> dict[str, object]:
        return {
            "weights": dict(self.weights),
            "boundary_status_scores": dict(self.boundary_status_scores),
            "role_status_scores": dict(self.role_status_scores),
            "role_manual_certainty": self.role_manual_certainty,
            "include_summary_score": self.include_summary_score,
        }


def default_boundary_status_scores() -> dict[str, float]:
    # Provisional v1 mapping, configurable, NOT a calibrated truth.
    return {
        "ok": 1.0,
        "partial": 0.7,
        "no_result": 0.4,
        "failed": 0.2,
    }


def default_role_status_scores() -> dict[str, float]:
    # Provisional v1 mapping, configurable, NOT a calibrated truth.
    return {
        "available": 1.0,
        "uncertain": 0.6,
        "unknown": 0.4,
        "unavailable": 0.3,
        "failed": 0.2,
    }


def default_weights() -> dict[str, float]:
    # Provisional v1 weights. Documented, configurable, NOT a universal truth.
    return {
        SECTION_COHERENCE: 0.30,
        MUSICAL_DEVELOPMENT: 0.20,
        BOUNDARY_SECURITY: 0.20,
        ROLE_SECURITY: 0.20,
        TRANSITION_RISK: 0.05,
        VOCAL_FX_EDGE_RISK: 0.05,
    }


def default_section_scoring_config() -> SectionScoringConfig:
    return SectionScoringConfig(
        weights=default_weights(),
        boundary_status_scores=default_boundary_status_scores(),
        role_status_scores=default_role_status_scores(),
    )


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
class SectionCandidateRef:
    start_sample: int
    end_sample_exclusive: int
    n_samples: int
    section_ref: str
    arrangement_role: SectionRole
    arrangement_role_source: Literal["automatic", "manual"]
    boundary_status: str
    boundary_kind: str


@dataclass(frozen=True)
class SectionScoreResult:
    candidate_ref: SectionCandidateRef
    source_identity: dict[str, object]
    status: SectionScoreStatus
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


# --- internal helpers -------------------------------------------------------


def _clip(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _section_values(
    bar_features: Mapping[str, Sequence[float]] | None,
    name: str,
    start_bar: int | None,
    end_bar_exclusive: int | None,
) -> np.ndarray | None:
    """Return the per-bar values for ``name`` within the section's bar span.

    Returns ``None`` (status-based fallback) when features are absent, the
    feature is missing, the bar span is invalid, or any value is non-finite.
    Missing or dirty evidence is never silently turned into a fake number.
    """
    if bar_features is None or name not in bar_features:
        return None
    if start_bar is None or end_bar_exclusive is None:
        return None
    array = np.asarray(bar_features[name], dtype=float)
    if array.ndim != 1 or array.size == 0:
        return None
    start = max(0, int(start_bar))
    end = min(array.size, int(end_bar_exclusive))
    if end <= start:
        return None
    segment = array[start:end]
    if not np.all(np.isfinite(segment)):
        return None
    return segment


# --- main entry point -------------------------------------------------------


def score_section_candidate(
    candidate: SectionCandidate,
    *,
    bar_features: Mapping[str, Sequence[float]] | None = None,
    vocal_fx_evidence: Sequence[SectionEdgeRiskEvidence] | None = None,
    config: SectionScoringConfig | None = None,
) -> SectionScoreResult:
    if config is None:
        config = default_section_scoring_config()

    source_identity = candidate.source.as_dict()
    ref = SectionCandidateRef(
        start_sample=candidate.start_sample,
        end_sample_exclusive=candidate.end_sample_exclusive,
        n_samples=candidate.n_samples,
        section_ref=candidate.section_ref,
        arrangement_role=candidate.arrangement_role,
        arrangement_role_source=candidate.arrangement_role_source,
        boundary_status=candidate.boundary.status,
        boundary_kind=candidate.boundary.kind,
    )

    components: dict[str, ScoreComponent] = {}

    # --- section coherence (no loop repetition / seam) ---------------------
    coherence_parts: list[float] = []
    for fname, sign in _COHERENCE_FEATURES:
        values = _section_values(
            bar_features, fname, candidate.start_bar, candidate.end_bar_exclusive
        )
        if values is None:
            continue
        mean_value = float(np.mean(values))
        if sign < 0:
            mean_value = 1.0 - mean_value
        coherence_parts.append(_clip(mean_value))
    if coherence_parts:
        coherence_value = _clip(float(np.mean(coherence_parts)))
        coherence_status: ScoreComponentStatus = "ok"
    else:
        coherence_value = None
        coherence_status = "not_evaluated"
    components[SECTION_COHERENCE] = ScoreComponent(
        name=SECTION_COHERENCE,
        value=coherence_value,
        value_range=_COMPONENT_RANGE,
        meaning=_COMPONENT_MEANING[SECTION_COHERENCE],
        status=coherence_status,
    )

    # --- musical development (directional arc, change not punished) --------
    trend = _section_values(
        bar_features,
        "multi_bar_trend",
        candidate.start_bar,
        candidate.end_bar_exclusive,
    )
    if trend is None or trend.size < 2:
        development_value = None
        development_status: ScoreComponentStatus = "not_evaluated"
    else:
        mean_t = float(np.mean(trend))
        if abs(mean_t) < 1e-6:
            # Flat/steady section: neutral, no penalty.
            development_value = 0.5
        else:
            same_sign = float(
                np.mean(
                    [
                        1.0 if (t == 0.0 or (t > 0) == (mean_t > 0)) else 0.0
                        for t in trend
                    ]
                )
            )
            development_value = _clip(same_sign)
        development_status = "ok"
    components[MUSICAL_DEVELOPMENT] = ScoreComponent(
        name=MUSICAL_DEVELOPMENT,
        value=development_value,
        value_range=_COMPONENT_RANGE,
        meaning=_COMPONENT_MEANING[MUSICAL_DEVELOPMENT],
        status=development_status,
    )

    # --- boundary security (separate from role) ---------------------------
    boundary_base = float(
        config.boundary_status_scores.get(candidate.boundary.status, 0.4)
    )
    quality = candidate.boundary.quality
    if quality is not None and np.isfinite(quality) and 0.0 <= float(quality) <= 1.0:
        boundary_value = _clip(0.6 * float(quality) + 0.4 * boundary_base)
    else:
        # Missing or invalid quality falls back to the status-based score; it is
        # never silently "corrected" into a fake calibrated value.
        boundary_value = boundary_base
    components[BOUNDARY_SECURITY] = ScoreComponent(
        name=BOUNDARY_SECURITY,
        value=boundary_value,
        value_range=_COMPONENT_RANGE,
        meaning=_COMPONENT_MEANING[BOUNDARY_SECURITY],
        status="ok",
    )

    # --- role security (separate from boundary) ---------------------------
    if candidate.arrangement_role_source == "manual":
        role_value = _clip(config.role_manual_certainty)
    else:
        role_value = float(
            config.role_status_scores.get(candidate.arrangement_role_status, 0.4)
        )
    components[ROLE_SECURITY] = ScoreComponent(
        name=ROLE_SECURITY,
        value=role_value,
        value_range=_COMPONENT_RANGE,
        meaning=_COMPONENT_MEANING[ROLE_SECURITY],
        status="ok",
    )

    # --- transition risk (internal neighbor delta) ------------------------
    neighbor = _section_values(
        bar_features, "neighbor_delta", candidate.start_bar, candidate.end_bar_exclusive
    )
    if neighbor is None:
        transition_value = None
        transition_status: ScoreComponentStatus = "not_evaluated"
    else:
        transition_value = _clip(float(np.max(neighbor)))
        transition_status = "ok"
    components[TRANSITION_RISK] = ScoreComponent(
        name=TRANSITION_RISK,
        value=transition_value,
        value_range=_COMPONENT_RANGE,
        meaning=_COMPONENT_MEANING[TRANSITION_RISK],
        status=transition_status,
    )

    # --- vocal / fx edge risk (only with real evidence) ------------------
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

    # --- hard exclusions (separate from soft scores) ----------------------
    reject_reasons: list[str] = []
    if candidate.n_samples <= 0:
        reject_reasons.append(REJECT_INVALID_RANGE)

    hard_rejected = len(reject_reasons) > 0
    summary = (
        _summary_score(components, config) if config.include_summary_score else None
    )

    provenance = config.to_dict()
    provenance["provisional"] = True
    provenance["effective_role_source"] = candidate.arrangement_role_source
    provenance["effective_role"] = candidate.arrangement_role
    provenance["note"] = (
        "Thresholds and weights are provisional v1 defaults; calibrate via #256 "
        "before treating any value as a final global truth. No fixed pilot "
        "selection threshold is applied here."
    )

    return SectionScoreResult(
        candidate_ref=ref,
        source_identity=source_identity,
        status="excluded" if hard_rejected else "ok",
        score_components=components,
        hard_rejected=hard_rejected,
        reject_reasons=tuple(reject_reasons),
        config_provenance=provenance,
        summary_score=summary,
    )


def _summary_score(
    components: Mapping[str, ScoreComponent], config: SectionScoringConfig
) -> float | None:
    weights = config.weights or default_weights()
    positive = (
        SECTION_COHERENCE,
        MUSICAL_DEVELOPMENT,
        BOUNDARY_SECURITY,
        ROLE_SECURITY,
    )
    soft_total = 0.0
    soft_weight = 0.0
    for name in positive:
        comp = components.get(name)
        w = weights.get(name, 0.0)
        if (
            w > 0.0
            and comp is not None
            and comp.value is not None
            and comp.status == "ok"
        ):
            soft_total += w * comp.value
            soft_weight += w
    if soft_weight <= 0.0:
        return None
    score = soft_total / soft_weight
    penalty = 0.0
    for name in (TRANSITION_RISK, VOCAL_FX_EDGE_RISK):
        w = weights.get(name, 0.0)
        comp = components.get(name)
        if w > 0.0 and comp is not None and comp.value is not None:
            penalty += w * comp.value
    return _clip(score - penalty)


__all__ = [
    "BOUNDARY_SECURITY",
    "MUSICAL_DEVELOPMENT",
    "REJECT_INVALID_RANGE",
    "ROLE_SECURITY",
    "SECTION_COHERENCE",
    "TRANSITION_RISK",
    "VOCAL_FX_EDGE_RISK",
    "ScoreComponent",
    "SectionCandidateRef",
    "SectionEdgeRiskEvidence",
    "SectionScoreResult",
    "SectionScoringConfig",
    "default_boundary_status_scores",
    "default_role_status_scores",
    "default_section_scoring_config",
    "default_weights",
    "score_section_candidate",
]
