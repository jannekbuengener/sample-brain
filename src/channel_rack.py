"""Minimal Channel Rack core — Live Kit channels, step grid, one pattern pass.

Projects canonical Live Kit slots into Pattern Core channels, toggles 16th-note
steps immutably, and schedules one pattern pass through sequencer_playback.
Musical truth stays Python-owned; this module adds no visual surfaces.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from .pattern_core import CHANNEL_ID_BY_LIVE_KIT_SLOT, Channel, Pattern, Trigger
from .sequencer_playback import (
    PlaybackScheduleResult,
    plan_pattern_once,
    schedule_pattern_once,
)
from .session_grid import TempoMap
from .workbench_live_kit import LIVE_KIT_SLOT_MAPPING, LiveKitState

DEFAULT_PATTERN_ID = "screen2-main"
DEFAULT_STEP_COUNT = 16
DEFAULT_PATTERN_LENGTH = Fraction(4, 1)


@dataclass(frozen=True)
class ChannelRackState:
    """Immutable rack snapshot: channels, active pattern, and step grid size."""

    channels: tuple[Channel, ...]
    pattern: Pattern
    step_count: int


def build_channel_rack_state(live_kit: LiveKitState) -> ChannelRackState:
    """Project current Live Kit assignments into an empty 16-step rack state."""

    channels: list[Channel] = []
    for group, slots in LIVE_KIT_SLOT_MAPPING:
        for slot in slots:
            assignment = live_kit.assignment_for(group, slot)
            sample_path = str(assignment.path) if assignment is not None else None
            channels.append(
                Channel(
                    channel_id=CHANNEL_ID_BY_LIVE_KIT_SLOT[(group, slot)],
                    live_kit_group=group,
                    live_kit_slot=slot,
                    sample_path=sample_path,
                )
            )

    return ChannelRackState(
        channels=tuple(channels),
        pattern=Pattern(
            pattern_id=DEFAULT_PATTERN_ID,
            length_quarter_notes=DEFAULT_PATTERN_LENGTH,
            triggers=(),
        ),
        step_count=DEFAULT_STEP_COUNT,
    )


def toggle_step(
    state: ChannelRackState,
    channel_id: str,
    step_index: int,
) -> ChannelRackState:
    """Return a new state with the given step toggled on or off."""

    known_ids = {channel.channel_id for channel in state.channels}
    if channel_id not in known_ids:
        raise ValueError(f"Unknown channel_id: {channel_id!r}")

    if type(step_index) is not int:
        raise TypeError(
            f"step_index must be an exact int (got {type(step_index).__name__})"
        )
    if not (0 <= step_index < state.step_count):
        raise ValueError(
            f"step_index must be in 0..{state.step_count - 1}, got {step_index}"
        )

    position = Fraction(step_index, 4)
    existing = state.pattern.triggers
    match = Trigger(channel_id=channel_id, position=position)

    if match in existing:
        new_triggers = tuple(t for t in existing if t != match)
    else:
        new_triggers = existing + (match,)

    return ChannelRackState(
        channels=state.channels,
        pattern=Pattern(
            pattern_id=state.pattern.pattern_id,
            length_quarter_notes=state.pattern.length_quarter_notes,
            triggers=new_triggers,
        ),
        step_count=state.step_count,
    )


def play_channel_rack_once(
    state: ChannelRackState,
    *,
    tempo_map: TempoMap,
    pattern_start_quarter: Fraction,
    pattern_start_engine_frame: int,
    engine: Any,
    pcm_for_path: Callable[[str], Any],
    allocate_voice_id: Callable[[], int],
) -> PlaybackScheduleResult:
    """Plan and schedule one pattern pass via the sequencer public seam."""

    channels_by_id: Mapping[str, Channel] = {
        channel.channel_id: channel for channel in state.channels
    }
    planned = plan_pattern_once(
        pattern=state.pattern,
        channels_by_id=channels_by_id,
        tempo_map=tempo_map,
        pattern_start_quarter=pattern_start_quarter,
        pattern_start_engine_frame=pattern_start_engine_frame,
    )
    return schedule_pattern_once(
        planned_triggers=planned,
        engine=engine,
        pcm_for_path=pcm_for_path,
        allocate_voice_id=allocate_voice_id,
    )


__all__ = [
    "ChannelRackState",
    "build_channel_rack_state",
    "play_channel_rack_once",
    "toggle_step",
]
