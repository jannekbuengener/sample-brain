"""Deterministic section asset candidate generation from the Arrangement Map.

Issue: #266. This module produces reproducible section asset candidates from
existing arrangement sections (StructureV1 neutral boundaries + Arrangement Map
roles) and optional manual corrections. Each candidate is bounded by two integer
sample indices on the shared #234 timebase (half-open interval).

It deliberately does NOT:

* classify arrangement roles (belongs to #240)
* detect or move boundaries (belongs to StructureV1 / #265)
* perform audio analysis, rendering, or scoring (belongs to #253 / #267)
* require a fixed bar length, repetition, or seam continuity

The automatic / manual / effective role provenance from the Arrangement
Confidence & Override contract (#241) is preserved verbatim. Boundary evidence
and role evidence stay on separate levels (also #241); an uncertain boundary
never implies an uncertain role and vice versa. ``unknown`` is a valid, normal
role and a valid result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .arrangement_classifier import (
    ARRANGEMENT_CLASSIFIER_COMPONENT,
    ArrangementResult,
    SectionRole,
)
from .canon_audio import AudioRange
from .structure_v1 import StructureSection, StructureV1Result

SectionSourceKind = Literal["master", "stem", "producer_group"]
SectionBatchStatus = Literal["ok", "no_result", "failed"]
SectionBoundaryStatus = Literal["ok", "partial", "no_result", "failed"]

SECTION_ARRANGEMENT_SOURCE = "arrangement_map"
SECTION_BOUNDARY_KIND = "neutral_section"
SECTION_CANDIDATE_STATUS = "candidate"
SECTION_RENDERING_STATUS = "not_rendered"
SECTION_ANALYSIS_STATUS = "not_run"
SECTION_ANALYSIS_REASON = "ANALYSIS_NOT_REQUESTED"
NO_SECTIONS_REASON = "NO_SECTIONS"
STRUCTURE_FAILED_REASON = "STRUCTURE_FAILED"
STRUCTURE_NO_RESULT_REASON = "STRUCTURE_NO_RESULT"
SECTION_ID_MISMATCH_REASON = "SECTION_ID_MISMATCH"
INVALID_RANGE_REASON = "INVALID_RANGE"


@dataclass(frozen=True)
class SectionSourceIdentity:
    """Portable source identity for a section asset (mirrors loop source)."""

    source_kind: SectionSourceKind
    track_audio_ref: str | None = None
    stem_id: str | None = None
    stem_ref: str | None = None
    producer_group_id: str | None = None
    producer_group_ref: str | None = None

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {"source_kind": self.source_kind}
        if self.source_kind == "master":
            payload["track_audio_ref"] = self.track_audio_ref or "/source/working_audio"
        elif self.source_kind == "stem":
            payload["stem_id"] = self.stem_id
            payload["stem_ref"] = self.stem_ref
        elif self.source_kind == "producer_group":
            payload["producer_group_id"] = self.producer_group_id
            payload["producer_group_ref"] = self.producer_group_ref
        return payload


@dataclass(frozen=True)
class SectionBoundaryContext:
    """Boundary provenance and quality, kept separate from role certainty (#241)."""

    source: str
    status: SectionBoundaryStatus
    kind: str
    quality: float | None = None


@dataclass(frozen=True)
class SectionCandidate:
    """One reproducible section asset candidate.

    ``arrangement_role`` is the effective role (override wins over automatic).
    ``arrangement_role_status`` preserves the automatic analysis status from
    #241; ``arrangement_role_source`` records whether the effective role came
    from the automatic analysis or a manual override; ``automatic_role`` keeps
    the original automatic result so manual corrections never destroy the
    automatic origin (#241 effective value policy).
    """

    asset_id: str
    track_ref: str
    section_ref: str
    start_sample: int
    end_sample_exclusive: int
    n_samples: int
    source: SectionSourceIdentity
    arrangement_role: SectionRole
    arrangement_role_status: str
    arrangement_role_source: Literal["automatic", "manual"]
    automatic_role: SectionRole
    boundary: SectionBoundaryContext
    start_bar: int | None = None
    end_bar_exclusive: int | None = None
    arrangement_role_ref: str | None = None
    candidate_status: str = SECTION_CANDIDATE_STATUS
    rendering_status: str = SECTION_RENDERING_STATUS
    analysis_status: str = SECTION_ANALYSIS_STATUS
    analysis_reason_code: str = SECTION_ANALYSIS_REASON

    def as_manifest_dict(self) -> dict[str, object]:
        section_block: dict[str, object] = {
            "section_ref": self.section_ref,
            "arrangement_role": self.arrangement_role,
            "arrangement_role_status": self.arrangement_role_status,
        }
        if self.arrangement_role_ref is not None:
            section_block["arrangement_role_ref"] = self.arrangement_role_ref
        if (
            self.start_bar is not None
            and self.end_bar_exclusive is not None
            and self.end_bar_exclusive > self.start_bar
        ):
            section_block["bars"] = {
                "start_bar": self.start_bar,
                "end_bar_exclusive": self.end_bar_exclusive,
                "bar_count": self.end_bar_exclusive - self.start_bar,
            }

        boundary_block: dict[str, object] = {
            "status": self.boundary.status,
            "source": self.boundary.source,
            "kind": self.boundary.kind,
        }
        if self.boundary.quality is not None:
            boundary_block["quality"] = self.boundary.quality

        return {
            "asset_id": self.asset_id,
            "track_ref": self.track_ref,
            "asset_kind": "section",
            "source": self.source.as_dict(),
            "range": {
                "start_sample": self.start_sample,
                "end_sample_exclusive": self.end_sample_exclusive,
                "n_samples": self.n_samples,
            },
            "section": section_block,
            "boundary": boundary_block,
            "candidate": {"status": self.candidate_status, "excluded": False},
            "rendering": {"status": self.rendering_status},
            "analysis": {
                "status": self.analysis_status,
                "reason_code": self.analysis_reason_code,
            },
        }


@dataclass(frozen=True)
class SectionCandidateBatch:
    status: SectionBatchStatus
    reason_code: str | None
    candidates: tuple[SectionCandidate, ...]


def generate_section_candidates(
    structure_result: StructureV1Result,
    arrangement_result: ArrangementResult | None = None,
    *,
    source: SectionSourceIdentity,
    track_ref: str,
    arrangement_source_ref: str = ARRANGEMENT_CLASSIFIER_COMPONENT,
) -> SectionCandidateBatch:
    """Produce one section candidate per effective arrangement section.

    Section sample boundaries come from ``structure_result`` (authoritative #234
    timebase). Role, status, and override provenance come from
    ``arrangement_result`` (#240 / #241). When ``arrangement_result`` is omitted,
    each section is emitted with ``unknown`` role and ``automatic`` provenance so
    a missing optional role never prevents a candidate.
    """
    if structure_result.status == "failed" or not structure_result.sections:
        reason = (
            STRUCTURE_FAILED_REASON
            if structure_result.status == "failed"
            else STRUCTURE_NO_RESULT_REASON
        )
        return SectionCandidateBatch(
            status="failed" if structure_result.status == "failed" else "no_result",
            reason_code=reason,
            candidates=(),
        )

    sections_by_id = {section.id: section for section in structure_result.sections}
    boundary_by_start = {
        boundary.sample_index: boundary for boundary in structure_result.boundaries
    }

    ordered = (
        arrangement_result.sections
        if arrangement_result is not None
        else structure_result.sections
    )

    candidates: list[SectionCandidate] = []
    for item in ordered:
        section_id = item.section_id if arrangement_result is not None else item.id
        structure_section = sections_by_id.get(section_id)
        if structure_section is None:
            raise ValueError(
                f"{SECTION_ID_MISMATCH_REASON}: {section_id} not found in StructureV1"
            )
        candidates.append(
            _build_candidate(
                structure_section,
                structure_result,
                boundary_by_start,
                arrangement_item=item if arrangement_result is not None else None,
                source=source,
                track_ref=track_ref,
                arrangement_source_ref=arrangement_source_ref,
            )
        )

    return SectionCandidateBatch(
        status="ok",
        reason_code=None,
        candidates=tuple(candidates),
    )


def _build_candidate(
    structure_section: StructureSection,
    structure_result: StructureV1Result,
    boundary_by_start: dict[int, object],
    *,
    arrangement_item: object | None,
    source: SectionSourceIdentity,
    track_ref: str,
    arrangement_source_ref: str,
) -> SectionCandidate:
    start_sample = structure_section.start_sample
    end_sample = structure_section.end_sample
    try:
        AudioRange(start_sample=start_sample, end_sample=end_sample)
    except ValueError as exc:
        raise ValueError(f"{INVALID_RANGE_REASON}: {exc}") from exc

    effective_role: SectionRole
    role_status: str
    role_source: Literal["automatic", "manual"]
    automatic_role: SectionRole
    role_ref: str | None

    if arrangement_item is not None:
        effective = arrangement_item.effective_value
        effective_role = effective.role
        role_source = effective.source
        automatic_role = arrangement_item.automatic_result.role
        role_status = arrangement_item.automatic_result.status
        role_ref = f"{arrangement_source_ref}/{arrangement_item.section_id}"
    else:
        effective_role = "unknown"
        role_source = "automatic"
        automatic_role = "unknown"
        role_status = "unknown"
        role_ref = None

    edge = boundary_by_start.get(start_sample)
    quality = None
    if edge is not None and edge.score is not None:
        quality = max(0.0, min(1.0, float(edge.score)))

    boundary = SectionBoundaryContext(
        source=SECTION_ARRANGEMENT_SOURCE,
        status=_boundary_status(structure_result.status),
        kind=SECTION_BOUNDARY_KIND,
        quality=quality,
    )

    return SectionCandidate(
        asset_id=f"asset_section_{structure_section.id}",
        track_ref=track_ref,
        section_ref=structure_section.id,
        start_sample=start_sample,
        end_sample_exclusive=end_sample,
        n_samples=end_sample - start_sample,
        source=source,
        arrangement_role=effective_role,
        arrangement_role_status=role_status,
        arrangement_role_source=role_source,
        automatic_role=automatic_role,
        boundary=boundary,
        start_bar=structure_section.start_bar,
        end_bar_exclusive=structure_section.end_bar,
        arrangement_role_ref=role_ref,
        candidate_status=SECTION_CANDIDATE_STATUS,
        rendering_status=SECTION_RENDERING_STATUS,
        analysis_status=SECTION_ANALYSIS_STATUS,
        analysis_reason_code=SECTION_ANALYSIS_REASON,
    )


def _boundary_status(structure_status: str) -> SectionBoundaryStatus:
    if structure_status in ("ok", "partial", "no_result", "failed"):
        return structure_status  # type: ignore[return-value]
    return "ok"


__all__ = [
    "SECTION_ARRANGEMENT_SOURCE",
    "SECTION_BOUNDARY_KIND",
    "SectionBoundaryContext",
    "SectionCandidate",
    "SectionCandidateBatch",
    "SectionSourceIdentity",
    "SectionSourceKind",
    "generate_section_candidates",
]
