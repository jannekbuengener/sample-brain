"""Deterministic bar-aligned loop candidate generation from real downbeats.

Issue: #251. This module produces reproducible 4/8/16-bar loop candidates
exclusively from real BeatGrid downbeat sample indices. It never approximates
bars from BPM, beats, or seconds, and it never fabricates a track end. Each
candidate is bounded by two real downbeats on the shared #234 sample timebase
(half-open interval). Optional StructureV1 section boundaries are carried as
crossing context only; no quality judgement is made here (#252 decides later).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

from .beat_grid import BEAT_GRID_SOURCE_REF, BeatGridResult
from .structure_v1 import StructureV1Result

LoopSourceKind = Literal["master", "stem", "producer_group"]
LoopBarCount = Literal[4, 8, 16]
LoopBatchStatus = Literal["ok", "no_result", "failed"]
LoopBoundaryStatus = Literal["ok", "no_result", "failed"]

DEFAULT_BAR_COUNTS: tuple[int, ...] = (4, 8, 16)
DOWNBEAT_GRID_REF = "/analysis/timeline/downbeats"
DOWNBEATS_UNAVAILABLE_REASON = "DOWNBEATS_UNAVAILABLE"
INSUFFICIENT_DOWNBEATS_REASON = "INSUFFICIENT_DOWNBEATS"
INVALID_DOWNBEAT_GRID_REASON = "INVALID_DOWNBEAT_GRID"
SECTION_CROSSING_SOURCE = "structure_v1"
SECTION_CROSSING_NONE = "none"


@dataclass(frozen=True)
class LoopSourceIdentity:
    source_kind: LoopSourceKind
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
class LoopSectionCrossing:
    source: str
    crosses: bool
    crossed_sample_indices: tuple[int, ...]


@dataclass(frozen=True)
class LoopBoundaryContext:
    source: str
    status: LoopBoundaryStatus
    section_crossing: LoopSectionCrossing


@dataclass(frozen=True)
class LoopCandidate:
    asset_kind: str
    bar_count: int
    start_bar: int
    end_bar_exclusive: int
    start_sample: int
    end_sample_exclusive: int
    n_samples: int
    source: LoopSourceIdentity
    downbeat_grid_ref: str
    boundary: LoopBoundaryContext
    candidate_status: str
    rendering_status: str = "not_rendered"
    reason_code: str | None = None

    def as_manifest_dict(self) -> dict[str, object]:
        return {
            "asset_kind": self.asset_kind,
            "source": self.source.as_dict(),
            "range": {
                "start_sample": self.start_sample,
                "end_sample_exclusive": self.end_sample_exclusive,
                "n_samples": self.n_samples,
            },
            "loop": {
                "bars": {
                    "start_bar": self.start_bar,
                    "end_bar_exclusive": self.end_bar_exclusive,
                    "bar_count": self.bar_count,
                },
                "downbeat_start_sample": self.start_sample,
                "bar_grid_ref": self.downbeat_grid_ref,
            },
            "boundary": {
                "status": self.boundary.status,
                "source": self.boundary.source,
                "kind": "bar_grid",
                "section_crossing": {
                    "source": self.boundary.section_crossing.source,
                    "crosses": self.boundary.section_crossing.crosses,
                    "crossed_sample_indices": list(
                        self.boundary.section_crossing.crossed_sample_indices
                    ),
                },
            },
            "candidate": {
                "status": self.candidate_status,
                "excluded": False,
            },
            "rendering": {"status": self.rendering_status},
        }


@dataclass(frozen=True)
class LoopCandidateBatch:
    status: LoopBatchStatus
    reason_code: str | None
    candidates: tuple[LoopCandidate, ...]
    bar_counts: tuple[int, ...]


def generate_loop_candidates(
    source: LoopSourceIdentity,
    *,
    beat_grid: BeatGridResult | None = None,
    downbeat_sample_indices: Sequence[int] | None = None,
    bar_counts: Sequence[int] = DEFAULT_BAR_COUNTS,
    structure: StructureV1Result | None = None,
    downbeat_grid_ref: str = DOWNBEAT_GRID_REF,
) -> LoopCandidateBatch:
    if beat_grid is not None:
        downbeats = beat_grid.downbeats
        if downbeats.status in {"no_result", "failed"} or not downbeats.sample_indices:
            reason = downbeats.reason_code or (
                DOWNBEATS_UNAVAILABLE_REASON
                if downbeats.status == "no_result"
                else "DOWNBEATS_FAILED"
            )
            return LoopCandidateBatch(
                status="no_result" if downbeats.status == "no_result" else "failed",
                reason_code=reason,
                candidates=(),
                bar_counts=tuple(bar_counts),
            )
        indices = tuple(int(i) for i in downbeats.sample_indices)
    elif downbeat_sample_indices is not None:
        indices = tuple(int(i) for i in downbeat_sample_indices)
    else:
        raise ValueError(
            "generate_loop_candidates requires beat_grid or downbeat_sample_indices"
        )

    return _build_candidates(
        indices,
        source,
        tuple(bar_counts),
        structure,
        downbeat_grid_ref,
    )


def _validate_indices(indices: tuple[int, ...]) -> str | None:
    if any(index < 0 for index in indices):
        return INVALID_DOWNBEAT_GRID_REASON
    for previous, following in zip(indices, indices[1:]):
        if following <= previous:
            return INVALID_DOWNBEAT_GRID_REASON
    return None


def _internal_boundary_sample_indices(
    structure: StructureV1Result | None, indices: tuple[int, ...]
) -> tuple[int, ...]:
    if structure is None or not structure.boundaries:
        return ()
    if not indices:
        return ()
    span_start, span_end = indices[0], indices[-1]
    return tuple(
        boundary.sample_index
        for boundary in structure.boundaries
        if span_start < boundary.sample_index < span_end
    )


def _build_candidates(
    indices: tuple[int, ...],
    source: LoopSourceIdentity,
    bar_counts: tuple[int, ...],
    structure: StructureV1Result | None,
    downbeat_grid_ref: str,
) -> LoopCandidateBatch:
    invalid = _validate_indices(indices)
    if invalid is not None:
        return LoopCandidateBatch(
            status="failed",
            reason_code=invalid,
            candidates=(),
            bar_counts=bar_counts,
        )

    if len(indices) < 2:
        return LoopCandidateBatch(
            status="no_result",
            reason_code=INSUFFICIENT_DOWNBEATS_REASON,
            candidates=(),
            bar_counts=bar_counts,
        )

    boundaries = _internal_boundary_sample_indices(structure, indices)
    candidates: list[LoopCandidate] = []
    for bar_count in bar_counts:
        for start_bar in range(0, len(indices) - bar_count):
            start_sample = indices[start_bar]
            end_sample = indices[start_bar + bar_count]
            crossed = tuple(
                boundary
                for boundary in boundaries
                if start_sample < boundary < end_sample
            )
            candidates.append(
                LoopCandidate(
                    asset_kind="loop",
                    bar_count=bar_count,
                    start_bar=start_bar,
                    end_bar_exclusive=start_bar + bar_count,
                    start_sample=start_sample,
                    end_sample_exclusive=end_sample,
                    n_samples=end_sample - start_sample,
                    source=source,
                    downbeat_grid_ref=downbeat_grid_ref,
                    boundary=LoopBoundaryContext(
                        source=BEAT_GRID_SOURCE_REF,
                        status="ok",
                        section_crossing=LoopSectionCrossing(
                            source=(
                                SECTION_CROSSING_SOURCE
                                if structure is not None
                                else SECTION_CROSSING_NONE
                            ),
                            crosses=bool(crossed),
                            crossed_sample_indices=crossed,
                        ),
                    ),
                    candidate_status="candidate",
                )
            )

    if not candidates:
        return LoopCandidateBatch(
            status="no_result",
            reason_code=INSUFFICIENT_DOWNBEATS_REASON,
            candidates=(),
            bar_counts=bar_counts,
        )

    return LoopCandidateBatch(
        status="ok",
        reason_code=None,
        candidates=tuple(candidates),
        bar_counts=bar_counts,
    )


__all__ = [
    "DEFAULT_BAR_COUNTS",
    "DOWNBEAT_GRID_REF",
    "LoopBarCount",
    "LoopBatchStatus",
    "LoopBoundaryContext",
    "LoopBoundaryStatus",
    "LoopCandidate",
    "LoopCandidateBatch",
    "LoopSectionCrossing",
    "LoopSourceIdentity",
    "LoopSourceKind",
    "generate_loop_candidates",
]
