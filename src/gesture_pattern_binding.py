"""R&D Slice 5 (#680/#891): ranking + timing to Pattern-binding plan.

Pure planner that joins delivered #882/#888 evidence under explicit sample
selection and explicit Pattern length. Does not create Pattern / Channel /
Trigger objects, call Channel Rack helpers, or recompute ranking/timing.

See ``docs/GESTURE_PATTERN_BINDING_RND_SLICE5.md``.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction

from .gesture_library_ranking import ClusterRanking, LibraryCandidate, RankedCandidate
from .gesture_timing_projection import GestureTimingProjection, ProjectedGestureEvent
from .pattern_core import allocate_user_channel_id


@dataclass(frozen=True)
class PlannedGestureChannelBinding:
    """One selected cluster mapped to a newly planned user channel."""

    cluster_id: int
    channel_id: str
    sample_id: str
    sample_path: str
    selected_rank: int
    distance: float


@dataclass(frozen=True)
class PlannedGestureEventBinding:
    """One resolved timing event bound to a planned channel."""

    cluster_id: int
    channel_id: str
    quarter_position: Fraction


@dataclass(frozen=True)
class GesturePatternBindingPlan:
    """Immutable Pattern-binding intent; composer-ready only when ready flag is set."""

    channel_bindings: tuple[PlannedGestureChannelBinding, ...]
    event_bindings: tuple[PlannedGestureEventBinding, ...]
    unresolved_cluster_ids: tuple[int, ...]
    pattern_length_quarters: Fraction
    ready_for_pattern: bool


def _require_exact_fraction(value: object, *, name: str) -> Fraction:
    if type(value) is not Fraction:
        raise TypeError(f"{name} must be an exact Fraction (got {type(value).__name__})")
    if value <= Fraction(0, 1):
        raise ValueError(f"{name} must be > 0")
    return value


def _require_existing_channel_ids(existing_channel_ids: object) -> list[str]:
    if not isinstance(existing_channel_ids, Collection) or isinstance(
        existing_channel_ids, (str, bytes)
    ):
        raise TypeError("existing_channel_ids must be a collection of strings")
    seen: set[str] = set()
    ordered: list[str] = []
    for item in existing_channel_ids:
        if not isinstance(item, str) or isinstance(item, bool) or not item:
            raise ValueError("existing_channel_ids entries must be non-empty strings")
        if item in seen:
            raise ValueError(f"duplicate existing channel id: {item!r}")
        seen.add(item)
        ordered.append(item)
    return ordered


def _validate_event_bounds(
    events: tuple[ProjectedGestureEvent, ...],
    *,
    pattern_length: Fraction,
) -> None:
    zero = Fraction(0, 1)
    for event in events:
        if not isinstance(event, ProjectedGestureEvent):
            raise TypeError("timing.events entries must be ProjectedGestureEvent")
        position = event.quarter_position
        if type(position) is not Fraction:
            raise TypeError("quarter_position must be an exact Fraction")
        if not (zero <= position < pattern_length):
            raise ValueError(
                f"quarter_position {position} must satisfy "
                f"0 <= position < {pattern_length}"
            )
        if not isinstance(event.cluster_id, int) or isinstance(event.cluster_id, bool):
            raise TypeError("cluster_id must be an int")


def _ranking_by_cluster(
    rankings: Sequence[ClusterRanking],
    *,
    timing_clusters: set[int],
) -> dict[int, ClusterRanking]:
    by_cluster: dict[int, ClusterRanking] = {}
    for ranking in rankings:
        if not isinstance(ranking, ClusterRanking):
            raise TypeError("rankings entries must be ClusterRanking")
        cluster_id = ranking.cluster_id
        if not isinstance(cluster_id, int) or isinstance(cluster_id, bool):
            raise TypeError("ranking.cluster_id must be an int")
        if cluster_id in by_cluster:
            raise ValueError(f"duplicate ranking cluster_id: {cluster_id}")
        by_cluster[cluster_id] = ranking
    ranking_clusters = set(by_cluster)
    if ranking_clusters != timing_clusters:
        missing = sorted(timing_clusters - ranking_clusters)
        extra = sorted(ranking_clusters - timing_clusters)
        raise ValueError(
            "ranking cluster set must match timing cluster set exactly; "
            f"missing={missing!r} extra={extra!r}"
        )
    return by_cluster


def _candidate_by_id(
    candidates: Sequence[LibraryCandidate],
) -> dict[str, LibraryCandidate]:
    by_id: dict[str, LibraryCandidate] = {}
    for candidate in candidates:
        if not isinstance(candidate, LibraryCandidate):
            raise TypeError("candidates entries must be LibraryCandidate")
        sample_id = candidate.sample_id
        if not isinstance(sample_id, str) or not sample_id:
            raise ValueError("candidate.sample_id must be a non-empty string")
        if sample_id in by_id:
            raise ValueError(f"duplicate candidate sample_id: {sample_id!r}")
        by_id[sample_id] = candidate
    return by_id


def _require_selection_map(selections: object) -> Mapping[int, str]:
    if not isinstance(selections, Mapping):
        raise TypeError("selections must be a mapping of cluster_id to sample_id")
    normalized: dict[int, str] = {}
    for key, value in selections.items():
        if isinstance(key, bool) or not isinstance(key, int):
            raise TypeError("selection keys must be int cluster_id values")
        if not isinstance(value, str) or not value:
            raise ValueError("selection values must be non-empty sample_id strings")
        if key in normalized:
            raise ValueError(f"duplicate selection for cluster_id: {key}")
        normalized[key] = value
    return normalized


def _resolve_selected_rank(
    ranking: ClusterRanking,
    *,
    sample_id: str,
) -> RankedCandidate:
    matches = [item for item in ranking.ranked if item.sample_id == sample_id]
    if len(matches) != 1:
        raise ValueError(
            f"selected sample_id {sample_id!r} must appear exactly once in "
            f"cluster {ranking.cluster_id} ranking"
        )
    ranked = matches[0]
    if not isinstance(ranked, RankedCandidate):
        raise TypeError("ranked entries must be RankedCandidate")
    if not isinstance(ranked.sample_id, str) or not ranked.sample_id:
        raise ValueError("ranked.sample_id must be a non-empty string")
    if isinstance(ranked.rank, bool) or not isinstance(ranked.rank, int) or ranked.rank <= 0:
        raise ValueError("ranked.rank must be a positive integer")
    if isinstance(ranked.distance, bool) or not isinstance(ranked.distance, (int, float)):
        raise TypeError("ranked.distance must be a real number")
    if not math.isfinite(float(ranked.distance)):
        raise ValueError("ranked.distance must be finite")
    return ranked


def plan_gesture_pattern_binding(
    timing: GestureTimingProjection,
    rankings: Sequence[ClusterRanking],
    candidates: Sequence[LibraryCandidate],
    selections: Mapping[int, str],
    existing_channel_ids: Collection[str],
    *,
    pattern_length_quarters: Fraction,
) -> GesturePatternBindingPlan:
    """Join ranking + timing evidence into an immutable Pattern-binding plan.

    Sample choice and Pattern length are caller-authoritative. Missing selection
    yields an unresolved cluster (not an automatic first-ranked pick).
    """
    if not isinstance(timing, GestureTimingProjection):
        raise TypeError("timing must be a GestureTimingProjection")

    length = _require_exact_fraction(
        pattern_length_quarters, name="pattern_length_quarters"
    )
    existing = _require_existing_channel_ids(existing_channel_ids)
    events = timing.events
    if not isinstance(events, tuple):
        raise TypeError("timing.events must be a tuple")

    # Bounds for every timing event, including clusters that stay unresolved.
    _validate_event_bounds(events, pattern_length=length)

    timing_clusters = {event.cluster_id for event in events}
    ranking_by_cluster = _ranking_by_cluster(rankings, timing_clusters=timing_clusters)
    candidate_by_id = _candidate_by_id(candidates)
    selection_map = _require_selection_map(selections)

    unknown = sorted(set(selection_map) - timing_clusters)
    if unknown:
        raise ValueError(f"selection for unknown cluster_id(s): {unknown!r}")

    unresolved: list[int] = []
    selected_resolution: dict[int, tuple[str, RankedCandidate, LibraryCandidate]] = {}

    for cluster_id in sorted(timing_clusters):
        if cluster_id not in selection_map:
            unresolved.append(cluster_id)
            continue
        sample_id = selection_map[cluster_id]
        ranked = _resolve_selected_rank(
            ranking_by_cluster[cluster_id], sample_id=sample_id
        )
        candidate = candidate_by_id.get(sample_id)
        if candidate is None:
            raise ValueError(f"selected sample_id {sample_id!r} missing from candidates")
        path = candidate.path
        if not isinstance(path, str) or not path:
            raise ValueError(
                f"selected candidate path for sample_id {sample_id!r} must be a "
                "non-empty string"
            )
        selected_resolution[cluster_id] = (sample_id, ranked, candidate)

    planned_ids: list[str] = list(existing)
    channel_for_cluster: dict[int, str] = {}
    channel_bindings: list[PlannedGestureChannelBinding] = []

    for cluster_id in sorted(selected_resolution):
        sample_id, ranked, candidate = selected_resolution[cluster_id]
        channel_id = allocate_user_channel_id(planned_ids)
        planned_ids.append(channel_id)
        channel_for_cluster[cluster_id] = channel_id
        channel_bindings.append(
            PlannedGestureChannelBinding(
                cluster_id=cluster_id,
                channel_id=channel_id,
                sample_id=sample_id,
                sample_path=str(candidate.path),
                selected_rank=int(ranked.rank),
                distance=float(ranked.distance),
            )
        )

    event_bindings: list[PlannedGestureEventBinding] = []
    for event in events:
        channel_id = channel_for_cluster.get(event.cluster_id)
        if channel_id is None:
            continue
        event_bindings.append(
            PlannedGestureEventBinding(
                cluster_id=event.cluster_id,
                channel_id=channel_id,
                quarter_position=event.quarter_position,
            )
        )

    unresolved_ids = tuple(sorted(unresolved))
    return GesturePatternBindingPlan(
        channel_bindings=tuple(channel_bindings),
        event_bindings=tuple(event_bindings),
        unresolved_cluster_ids=unresolved_ids,
        pattern_length_quarters=length,
        ready_for_pattern=not unresolved_ids,
    )
