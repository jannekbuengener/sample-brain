"""Deterministic, track-relative Arrangement Map heuristic for Issue #240."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from .structure_v1 import StructureBoundary, StructureSection, StructureV1Result

ArrangementStatus = Literal[
    "available", "uncertain", "unknown", "unavailable", "failed"
]
SectionRole = Literal[
    "intro", "groove", "build", "drop", "breakdown", "outro", "unknown"
]
BoundaryEvent = Literal["drop_onset"]

ARRANGEMENT_CLASSIFIER_COMPONENT = "arrangement_classifier"
_ROLES: tuple[SectionRole, ...] = (
    "intro",
    "groove",
    "build",
    "drop",
    "breakdown",
    "outro",
)
_CORE_SIGNALS = frozenset(
    {
        "bar_energy_rms",
        "bar_loudness_delta",
        "low_end_share",
        "onset_density",
        "rhythm_stability",
        "timbre_delta",
        "spectral_delta",
        "self_similarity",
        "recurrence",
        "novelty",
        "neighbor_delta",
        "multi_bar_trend",
        "relative_track_position",
    }
)


@dataclass(frozen=True)
class SectionSignals:
    """Track-relative section signals from StructureV1/#239 (values normally 0..1).

    ``multi_bar_trend`` is directional: positive means rising, negative falling.
    Missing signals are named explicitly rather than replaced with synthetic values.
    """

    bar_energy_rms: float = 0.5
    bar_loudness_delta: float = 0.5
    low_end_share: float = 0.5
    onset_density: float = 0.5
    rhythm_stability: float = 0.5
    timbre_delta: float = 0.5
    spectral_delta: float = 0.5
    self_similarity: float = 0.5
    recurrence: float = 0.5
    novelty: float = 0.5
    neighbor_delta: float = 0.5
    multi_bar_trend: float = 0.0
    relative_track_position: float = 0.5
    evidence_completeness: float | None = None
    available_signals: tuple[str, ...] = ()
    missing_signals: tuple[str, ...] = ()
    contradictory_signals: tuple[str, ...] = ()


@dataclass(frozen=True)
class ArrangementEvidence:
    positive_signals: tuple[str, ...] = ()
    negative_signals: tuple[str, ...] = ()
    missing_signals: tuple[str, ...] = ()
    contradictory_signals: tuple[str, ...] = ()
    contributions: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True)
class AutomaticResult:
    role: SectionRole
    event: BoundaryEvent | None
    status: ArrangementStatus
    evidence: ArrangementEvidence
    provenance: dict[str, object]
    scores: dict[str, float] | None = None


@dataclass(frozen=True)
class ManualOverride:
    role: SectionRole | None = None
    event: BoundaryEvent | None = None
    author: str | None = None
    timestamp_utc: str | None = None
    reason: str | None = None
    source: Literal["manual"] = "manual"


@dataclass(frozen=True)
class EffectiveValue:
    role: SectionRole
    event: BoundaryEvent | None
    source: Literal["automatic", "manual"]


@dataclass(frozen=True)
class SectionClassification:
    section_id: str
    start_sec: float
    end_sec: float
    start_bar: int
    end_bar: int
    automatic_result: AutomaticResult
    manual_override: ManualOverride | None
    effective_value: EffectiveValue


@dataclass(frozen=True)
class BoundaryEventClassification:
    boundary_id: int
    boundary_sec: float
    bar_index: int
    event: BoundaryEvent
    role_after: SectionRole
    status: ArrangementStatus
    evidence: ArrangementEvidence


@dataclass(frozen=True)
class ArrangementResult:
    sections: tuple[SectionClassification, ...]
    events: tuple[BoundaryEventClassification, ...]
    status: ArrangementStatus
    provenance: dict[str, object]

    def to_arrangement_map(self) -> dict[str, object]:
        """Return the Track-Map-compatible Arrangement Map consumer payload.

        The adapter copies StructureV1 ranges verbatim. It never creates or
        moves boundaries; events only point at a supplied neutral boundary.
        """
        return {
            "status": self.status,
            "source_ref": ARRANGEMENT_CLASSIFIER_COMPONENT,
            "sections": [
                {
                    "id": item.section_id,
                    "start_sec": item.start_sec,
                    "end_sec": item.end_sec,
                    "start_bar": item.start_bar,
                    "end_bar": item.end_bar,
                    "automatic_result": _automatic_payload(item.automatic_result),
                    "manual_override": (
                        asdict(item.manual_override) if item.manual_override else None
                    ),
                    "effective_value": asdict(item.effective_value),
                }
                for item in self.sections
            ],
            "events": [asdict(item) for item in self.events],
            "provenance": self.provenance,
        }


def _automatic_payload(result: AutomaticResult) -> dict[str, object]:
    payload: dict[str, object] = {
        "role": result.role,
        "event": result.event,
        "status": result.status,
        "evidence": asdict(result.evidence),
        "provenance": result.provenance,
    }
    if result.scores:
        payload["scores"] = result.scores
    return payload


def _clip(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _score_roles(signals: SectionSignals) -> dict[SectionRole, float]:
    """Score relative combinations, not absolute genre thresholds or confidence."""
    v = {
        name: _clip(getattr(signals, name))
        for name in _CORE_SIGNALS - {"multi_bar_trend"}
    }
    rising = _clip(signals.multi_bar_trend)
    falling = _clip(-signals.multi_bar_trend)
    scores: dict[SectionRole, float] = {
        "intro": 0.40 * (1 - v["relative_track_position"])
        + 0.20 * (1 - v["bar_energy_rms"])
        + 0.20 * (1 - v["low_end_share"])
        + 0.20 * rising,
        "groove": 0.16 * v["bar_energy_rms"]
        + 0.14 * v["low_end_share"]
        + 0.14 * v["onset_density"]
        + 0.20 * v["rhythm_stability"]
        + 0.18 * v["self_similarity"]
        + 0.18 * v["recurrence"]
        - 0.15 * v["novelty"]
        - 0.10 * v["neighbor_delta"]
        - 0.10 * abs(signals.multi_bar_trend),
        "build": 0.18 * v["bar_loudness_delta"]
        + 0.16 * v["onset_density"]
        + 0.16 * v["timbre_delta"]
        + 0.16 * v["spectral_delta"]
        + 0.14 * v["novelty"]
        + 0.10 * v["neighbor_delta"]
        + 0.10 * rising,
        "drop": 0.20 * v["bar_energy_rms"]
        + 0.18 * v["low_end_share"]
        + 0.16 * v["onset_density"]
        + 0.12 * v["rhythm_stability"]
        + 0.10 * v["bar_loudness_delta"]
        + 0.08 * v["neighbor_delta"]
        + 0.08 * v["self_similarity"]
        + 0.08 * v["recurrence"],
        "breakdown": 0.19 * (1 - v["bar_energy_rms"])
        + 0.19 * (1 - v["low_end_share"])
        + 0.19 * (1 - v["onset_density"])
        + 0.10 * (1 - v["rhythm_stability"])
        + 0.12 * v["timbre_delta"]
        + 0.09 * v["spectral_delta"]
        + 0.12 * v["novelty"]
        + 0.10 * falling
        - 0.10 * v["relative_track_position"],
        "outro": 0.30 * v["relative_track_position"]
        + 0.18 * (1 - v["bar_energy_rms"])
        + 0.15 * (1 - v["onset_density"])
        + 0.15 * falling
        + 0.12 * v["neighbor_delta"]
        + 0.10 * (1 - v["low_end_share"]),
    }
    return scores


def _classify(
    signals: SectionSignals,
) -> tuple[SectionRole, ArrangementStatus, dict[SectionRole, float]]:
    available = set(signals.available_signals)
    completeness = signals.evidence_completeness
    if (
        signals.contradictory_signals
        or len(available & _CORE_SIGNALS) < 3
        or completeness == 0
    ):
        return "unknown", "unknown", {}
    scores = _score_roles(signals)
    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    role, best = ranked[0]
    runner_up = ranked[1][1]
    # These are score-separation rules, not audio/genre thresholds.  They avoid
    # turning near-ties into an asserted arrangement role.
    if (
        best < 0.45
        or best - runner_up < 0.05
        or (completeness is not None and completeness < 0.5)
    ):
        return "unknown", "unknown", {}
    status: ArrangementStatus = (
        "available" if completeness is None or completeness >= 0.75 else "uncertain"
    )
    return role, status, {name: round(value, 6) for name, value in scores.items()}


def _evidence(signals: SectionSignals, role: SectionRole) -> ArrangementEvidence:
    available = set(signals.available_signals)
    positive: dict[SectionRole, tuple[str, ...]] = {
        "intro": (
            "relative_track_position",
            "bar_energy_rms",
            "low_end_share",
            "multi_bar_trend",
        ),
        "groove": (
            "rhythm_stability",
            "self_similarity",
            "recurrence",
            "bar_energy_rms",
        ),
        "build": (
            "bar_loudness_delta",
            "onset_density",
            "timbre_delta",
            "spectral_delta",
            "multi_bar_trend",
        ),
        "drop": (
            "bar_energy_rms",
            "low_end_share",
            "onset_density",
            "rhythm_stability",
            "neighbor_delta",
        ),
        "breakdown": (
            "bar_energy_rms",
            "low_end_share",
            "onset_density",
            "novelty",
            "multi_bar_trend",
        ),
        "outro": (
            "relative_track_position",
            "bar_energy_rms",
            "onset_density",
            "multi_bar_trend",
        ),
        "unknown": (),
    }
    selected = tuple(name for name in positive[role] if name in available)
    contributions = tuple(
        {
            "signal": name,
            "direction": "positive",
            "strength": "track_relative",
            "source": "StructureV1/#239",
        }
        for name in selected
    )
    negatives = tuple(
        name for name in signals.contradictory_signals if name in available
    )
    return ArrangementEvidence(
        selected,
        negatives,
        signals.missing_signals,
        signals.contradictory_signals,
        contributions,
    )


class ArrangementClassifier:
    """Rule-based v1 classifier with a StructureV1 -> Arrangement Map adapter."""

    def classify_sections(
        self,
        sections: list[StructureSection] | tuple[StructureSection, ...],
        section_signals: list[SectionSignals] | tuple[SectionSignals, ...],
        manual_overrides: dict[str, ManualOverride] | None = None,
    ) -> tuple[SectionClassification, ...]:
        if len(sections) != len(section_signals):
            raise ValueError("sections and section_signals length mismatch")
        overrides = manual_overrides or {}
        result: list[SectionClassification] = []
        for section, signals in zip(sections, section_signals):
            role, status, scores = _classify(signals)
            event = self._drop_onset_candidate(role, signals)
            automatic = AutomaticResult(
                role=role,
                event=event,
                status=status,
                evidence=_evidence(signals, role),
                provenance={
                    "component": ARRANGEMENT_CLASSIFIER_COMPONENT,
                    "method": "deterministic_track_relative_heuristic_v1",
                },
                scores=scores or None,
            )
            override = overrides.get(section.id)
            effective = EffectiveValue(
                role=override.role if override and override.role is not None else role,
                event=(
                    override.event if override and override.event is not None else event
                ),
                source=(
                    "manual"
                    if override
                    and (override.role is not None or override.event is not None)
                    else "automatic"
                ),
            )
            result.append(
                SectionClassification(
                    section.id,
                    section.start_sec,
                    section.end_sec,
                    section.start_bar,
                    section.end_bar,
                    automatic,
                    override,
                    effective,
                )
            )
        return tuple(result)

    @staticmethod
    def _drop_onset_candidate(
        role: SectionRole, signals: SectionSignals
    ) -> BoundaryEvent | None:
        required = {
            "bar_loudness_delta",
            "novelty",
            "timbre_delta",
            "spectral_delta",
            "neighbor_delta",
        }
        if role != "drop" or not required <= set(signals.available_signals):
            return None
        onset_evidence = (
            signals.bar_loudness_delta
            + signals.novelty
            + signals.timbre_delta
            + signals.spectral_delta
            + signals.neighbor_delta
        ) / 5
        return "drop_onset" if onset_evidence >= 0.65 else None

    def classify_events(
        self,
        boundaries: list[StructureBoundary] | tuple[StructureBoundary, ...],
        sections: tuple[SectionClassification, ...],
    ) -> tuple[BoundaryEventClassification, ...]:
        by_bar = {section.start_bar: section for section in sections}
        events: list[BoundaryEventClassification] = []
        for boundary in boundaries:
            after = by_bar.get(boundary.bar_index)
            if after and after.automatic_result.event == "drop_onset":
                events.append(
                    BoundaryEventClassification(
                        boundary.sample_index,
                        boundary.time_sec,
                        boundary.bar_index,
                        "drop_onset",
                        after.automatic_result.role,
                        after.automatic_result.status,
                        after.automatic_result.evidence,
                    )
                )
        return tuple(events)

    def classify_track(
        self,
        structure_result: StructureV1Result,
        section_signals: list[SectionSignals] | tuple[SectionSignals, ...],
        manual_overrides: dict[str, ManualOverride] | None = None,
    ) -> ArrangementResult:
        if structure_result.status == "failed":
            return ArrangementResult(
                (),
                (),
                "failed",
                {
                    "component": ARRANGEMENT_CLASSIFIER_COMPONENT,
                    "structure_status": "failed",
                },
            )
        if structure_result.status == "no_result" or not structure_result.sections:
            return ArrangementResult(
                (),
                (),
                "unavailable",
                {
                    "component": ARRANGEMENT_CLASSIFIER_COMPONENT,
                    "structure_status": structure_result.status,
                },
            )
        sections = self.classify_sections(
            structure_result.sections, section_signals, manual_overrides
        )
        events = self.classify_events(structure_result.boundaries, sections)
        status: ArrangementStatus = (
            "available"
            if all(item.automatic_result.status == "available" for item in sections)
            else "uncertain"
        )
        return ArrangementResult(
            sections,
            events,
            status,
            {
                "component": ARRANGEMENT_CLASSIFIER_COMPONENT,
                "structure_source_ref": "structure_v1",
                "method": "deterministic_track_relative_heuristic_v1",
            },
        )


__all__ = [
    "ARRANGEMENT_CLASSIFIER_COMPONENT",
    "ArrangementClassifier",
    "ArrangementEvidence",
    "ArrangementResult",
    "ArrangementStatus",
    "AutomaticResult",
    "BoundaryEvent",
    "BoundaryEventClassification",
    "EffectiveValue",
    "ManualOverride",
    "SectionClassification",
    "SectionRole",
    "SectionSignals",
]
