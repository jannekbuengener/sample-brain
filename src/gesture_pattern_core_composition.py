"""R&D Slice 6 (#680/#893): ready binding plan → Pattern Core composition.

Pure composer that translates a ready ``GesturePatternBindingPlan`` plus an
explicit caller ``pattern_id`` into existing Pattern-Core ``Channel`` /
``Trigger`` / ``Pattern`` objects.

Does not recompute ranking, selection, timing, channel allocation, or Pattern
length. Does not mutate Channel Rack state or seed full-step rack triggers.

See ``docs/GESTURE_PATTERN_CORE_COMPOSITION_RND_SLICE6.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from .gesture_pattern_binding import (
    GesturePatternBindingPlan,
    PlannedGestureChannelBinding,
    PlannedGestureEventBinding,
)
from .pattern_core import (
    Channel,
    Pattern,
    Trigger,
    require_triggers_reference_known_channels,
)


@dataclass(frozen=True)
class GesturePatternCoreComposition:
    """Immutable gesture-created Pattern-Core delta (channels + pattern only)."""

    channels: tuple[Channel, ...]
    pattern: Pattern


def compose_gesture_pattern_core(
    plan: GesturePatternBindingPlan,
    *,
    pattern_id: str,
) -> GesturePatternCoreComposition:
    """Compose Pattern-Core objects from a ready #891 binding plan.

    ``pattern_id`` is explicit caller authority (non-empty ``str``). The plan
    must already be ready with no unresolved clusters; structural fields are
    still validated so a spoofed ready flag cannot authorize malformed state.
    """
    if not isinstance(plan, GesturePatternBindingPlan):
        raise TypeError(
            "plan must be a GesturePatternBindingPlan "
            f"(got {type(plan).__name__})"
        )
    if plan.ready_for_pattern is not True:
        raise ValueError("plan.ready_for_pattern must be True")
    if plan.unresolved_cluster_ids != ():
        raise ValueError(
            "plan.unresolved_cluster_ids must be empty for composition"
        )
    if not isinstance(pattern_id, str) or pattern_id == "":
        raise ValueError("pattern_id must be a non-empty string")

    channel_by_cluster, channels = _validated_channels(plan.channel_bindings)
    events = _validated_events(
        plan.event_bindings,
        channel_by_cluster=channel_by_cluster,
        pattern_length=plan.pattern_length_quarters,
    )
    _require_no_orphan_channels(channel_by_cluster, events)

    composed_triggers = tuple(
        Trigger(
            channel_id=event.channel_id,
            position=event.quarter_position,
        )
        for event in events
    )
    expected_triggers = composed_triggers
    pattern = Pattern(
        pattern_id=pattern_id,
        length_quarter_notes=plan.pattern_length_quarters,
        triggers=expected_triggers,
    )
    if pattern.triggers != expected_triggers:
        raise ValueError(
            "Pattern Core normalization would change frozen gesture event order"
        )

    composition = GesturePatternCoreComposition(
        channels=channels,
        pattern=pattern,
    )
    require_triggers_reference_known_channels(
        composition.pattern.triggers,
        known_channel_ids=[c.channel_id for c in composition.channels],
    )
    return composition


def _validated_channels(
    bindings: object,
) -> tuple[dict[int, str], tuple[Channel, ...]]:
    if not isinstance(bindings, tuple):
        raise TypeError("plan.channel_bindings must be a tuple")

    cluster_ids: set[int] = set()
    channel_ids: set[str] = set()
    channel_by_cluster: dict[int, str] = {}
    channels: list[Channel] = []

    for binding in bindings:
        if not isinstance(binding, PlannedGestureChannelBinding):
            raise TypeError(
                "channel_bindings entries must be PlannedGestureChannelBinding"
            )
        cluster_id = binding.cluster_id
        if not isinstance(cluster_id, int) or isinstance(cluster_id, bool):
            raise TypeError("cluster_id must be an int")
        if cluster_id in cluster_ids:
            raise ValueError(f"duplicate planned cluster_id: {cluster_id!r}")
        cluster_ids.add(cluster_id)

        channel_id = binding.channel_id
        if not isinstance(channel_id, str) or channel_id == "":
            raise ValueError("channel_id must be a non-empty string")
        if channel_id in channel_ids:
            raise ValueError(f"duplicate planned channel_id: {channel_id!r}")
        channel_ids.add(channel_id)

        sample_path = binding.sample_path
        if not isinstance(sample_path, str) or sample_path == "":
            raise ValueError("sample_path must be a non-empty string")

        channel_by_cluster[cluster_id] = channel_id
        channels.append(
            Channel(
                channel_id=channel_id,
                live_kit_group=None,
                live_kit_slot=None,
                sample_path=sample_path,
            )
        )

    return channel_by_cluster, tuple(channels)


def _validated_events(
    bindings: object,
    *,
    channel_by_cluster: dict[int, str],
    pattern_length: Fraction,
) -> tuple[PlannedGestureEventBinding, ...]:
    if not isinstance(bindings, tuple):
        raise TypeError("plan.event_bindings must be a tuple")
    if type(pattern_length) is not Fraction:
        raise TypeError(
            "pattern_length_quarters must be an exact Fraction "
            f"(got {type(pattern_length).__name__})"
        )

    known_channel_ids = frozenset(channel_by_cluster.values())
    zero = Fraction(0, 1)
    previous_position: Fraction | None = None
    events: list[PlannedGestureEventBinding] = []

    for event in bindings:
        if not isinstance(event, PlannedGestureEventBinding):
            raise TypeError(
                "event_bindings entries must be PlannedGestureEventBinding"
            )
        cluster_id = event.cluster_id
        if not isinstance(cluster_id, int) or isinstance(cluster_id, bool):
            raise TypeError("cluster_id must be an int")
        if cluster_id not in channel_by_cluster:
            raise ValueError(
                f"event cluster_id {cluster_id!r} is not among planned channels"
            )

        channel_id = event.channel_id
        if not isinstance(channel_id, str) or channel_id == "":
            raise ValueError("event channel_id must be a non-empty string")
        if channel_id not in known_channel_ids:
            raise ValueError(f"event references unknown channel_id: {channel_id!r}")
        expected_channel_id = channel_by_cluster[cluster_id]
        if channel_id != expected_channel_id:
            raise ValueError(
                f"event cluster_id {cluster_id!r} maps to channel_id "
                f"{expected_channel_id!r}, not {channel_id!r}"
            )

        position = event.quarter_position
        if type(position) is not Fraction:
            raise TypeError(
                "quarter_position must be an exact Fraction "
                f"(got {type(position).__name__})"
            )
        if not (zero <= position < pattern_length):
            raise ValueError(
                f"quarter_position {position} must satisfy "
                f"0 <= position < {pattern_length}"
            )
        if previous_position is not None and not (position > previous_position):
            raise ValueError(
                "event quarter_position values must be strictly increasing"
            )
        previous_position = position
        events.append(event)

    return tuple(events)


def _require_no_orphan_channels(
    channel_by_cluster: dict[int, str],
    events: tuple[PlannedGestureEventBinding, ...],
) -> None:
    if not channel_by_cluster:
        return
    used_clusters = {event.cluster_id for event in events}
    orphans = sorted(set(channel_by_cluster) - used_clusters)
    if orphans:
        raise ValueError(
            f"planned channel(s) without events for cluster_id(s): {orphans!r}"
        )


__all__ = [
    "GesturePatternCoreComposition",
    "compose_gesture_pattern_core",
]
