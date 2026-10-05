"""R&D Slice 7 (#680/#899): composition → Rack/Session integration plan.

Pure planner that translates an existing ``ChannelRackState`` plus a
``GesturePatternCoreComposition`` into an immutable integration plan /
target-state intent.

Does not mutate Channel Rack controller state, WorkbenchSession, persistence,
playback, or QML. Pattern replacement is explicit-authority only.

See ``docs/GESTURE_RACK_SESSION_INTEGRATION_RND_SLICE7.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from .channel_rack import ChannelRackState
from .gesture_pattern_core_composition import GesturePatternCoreComposition
from .pattern_core import (
    Channel,
    Pattern,
    require_triggers_reference_known_channels,
)


@dataclass(frozen=True)
class GestureRackIntegrationPlan:
    """Immutable Rack/Session integration intent (no mutation applied)."""

    expected_base_state: ChannelRackState
    target_channels: tuple[Channel, ...]
    target_pattern: Pattern
    target_step_count: int
    appended_channel_ids: tuple[str, ...]
    replaced_pattern_id: str
    replaced_trigger_count: int
    off_grid_event_count: int
    ready_for_apply: bool


def plan_gesture_rack_integration(
    base_state: ChannelRackState,
    composition: GesturePatternCoreComposition,
    *,
    allow_pattern_replacement: bool,
) -> GestureRackIntegrationPlan:
    """Plan explicit Pattern replacement into an existing Rack context.

    Pure and mutation-free. ``ready_for_apply`` is ``True`` only when inputs are
    structurally valid, channel IDs are collision-free, target membership holds,
    and ``allow_pattern_replacement is True``.
    """
    if not isinstance(base_state, ChannelRackState):
        raise TypeError(
            "base_state must be a ChannelRackState "
            f"(got {type(base_state).__name__})"
        )
    if not isinstance(composition, GesturePatternCoreComposition):
        raise TypeError(
            "composition must be a GesturePatternCoreComposition "
            f"(got {type(composition).__name__})"
        )

    base_ids = _unique_channel_ids(
        base_state.channels,
        label="base_state.channels",
    )
    composition_ids = _unique_channel_ids(
        composition.channels,
        label="composition.channels",
    )
    collisions = sorted(base_ids & composition_ids)
    if collisions:
        raise ValueError(
            "composition channel_id collision with base Rack: "
            f"{collisions!r}"
        )

    target_channels = tuple(base_state.channels) + tuple(composition.channels)
    target_pattern = composition.pattern
    target_step_count = base_state.step_count

    require_triggers_reference_known_channels(
        target_pattern.triggers,
        known_channel_ids=[channel.channel_id for channel in target_channels],
    )

    on_grid_positions = frozenset(
        Fraction(step_index, 4) for step_index in range(base_state.step_count)
    )
    off_grid_event_count = sum(
        1
        for trigger in target_pattern.triggers
        if trigger.position not in on_grid_positions
    )

    ready_for_apply = allow_pattern_replacement is True

    return GestureRackIntegrationPlan(
        expected_base_state=base_state,
        target_channels=target_channels,
        target_pattern=target_pattern,
        target_step_count=target_step_count,
        appended_channel_ids=tuple(
            channel.channel_id for channel in composition.channels
        ),
        replaced_pattern_id=target_pattern.pattern_id,
        replaced_trigger_count=len(target_pattern.triggers),
        off_grid_event_count=off_grid_event_count,
        ready_for_apply=ready_for_apply,
    )


def _unique_channel_ids(
    channels: object,
    *,
    label: str,
) -> set[str]:
    if not isinstance(channels, tuple):
        raise TypeError(f"{label} must be a tuple")
    seen: set[str] = set()
    for channel in channels:
        if not isinstance(channel, Channel):
            raise TypeError(f"{label} entries must be Channel instances")
        channel_id = channel.channel_id
        if channel_id in seen:
            raise ValueError(f"duplicate channel_id in {label}: {channel_id!r}")
        seen.add(channel_id)
    return seen


__all__ = [
    "GestureRackIntegrationPlan",
    "plan_gesture_rack_integration",
]
