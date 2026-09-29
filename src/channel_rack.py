"""Minimal Channel Rack core — Live Kit channels, step grid, one pattern pass.

Projects canonical Live Kit slots into Pattern Core channels, toggles 16th-note
steps immutably, appends user-added channels without Live Kit provenance, and
schedules one pattern pass through sequencer_playback. Musical truth stays
Python-owned; this module adds no visual surfaces.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from .pattern_core import (
    CHANNEL_ID_BY_LIVE_KIT_SLOT,
    Channel,
    Pattern,
    Trigger,
    allocate_user_channel_id,
    require_triggers_reference_known_channels,
)
from .sequencer_pcm import SequencerPcmProvider
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

    def __post_init__(self) -> None:
        channel_ids = [channel.channel_id for channel in self.channels]
        if len(channel_ids) != len(set(channel_ids)):
            raise ValueError("channels must have unique channel_id values")
        require_triggers_reference_known_channels(
            self.pattern.triggers,
            known_channel_ids=channel_ids,
        )


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


def add_user_channel(
    state: ChannelRackState,
    *,
    sample_path: str | None = None,
    channel_id: str | None = None,
) -> ChannelRackState:
    """Append a user-added rack channel without Live Kit provenance."""

    existing_ids = [channel.channel_id for channel in state.channels]
    new_id = (
        channel_id
        if channel_id is not None
        else allocate_user_channel_id(existing_ids)
    )
    if new_id in existing_ids:
        raise ValueError(f"Duplicate channel_id: {new_id!r}")

    new_channel = Channel(
        channel_id=new_id,
        live_kit_group=None,
        live_kit_slot=None,
        sample_path=sample_path,
    )
    return ChannelRackState(
        channels=state.channels + (new_channel,),
        pattern=state.pattern,
        step_count=state.step_count,
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
    pcm_for_path: Callable[[str], Any] | None = None,
    pcm_provider: SequencerPcmProvider | None = None,
    allocate_voice_id: Callable[[], int],
) -> PlaybackScheduleResult:
    """Plan and schedule one pattern pass via the sequencer public seam.

    Resolution for PCM:

    1. Explicit ``pcm_for_path`` callable (tests / custom injectors).
    2. Else long-lived ``pcm_provider`` (preferred production path).

    At least one of ``pcm_for_path`` / ``pcm_provider`` is required. The provider
    is never created ephemerally here — keep it at rack/session lifetime and
    prefer ``warm_channel_rack_pcm`` before anchoring playback.
    """

    resolver = _resolve_pcm_injector(
        pcm_for_path=pcm_for_path,
        pcm_provider=pcm_provider,
        tempo_map=tempo_map,
    )

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
        pcm_for_path=resolver,
        allocate_voice_id=allocate_voice_id,
    )


def _resolve_pcm_injector(
    *,
    pcm_for_path: Callable[[str], Any] | None,
    pcm_provider: SequencerPcmProvider | None,
    tempo_map: TempoMap,
) -> Callable[[str], Any]:
    if pcm_for_path is not None:
        bound_provider = _sequencer_provider_from_callable(pcm_for_path)
        if bound_provider is not None:
            _require_matching_sample_rate(bound_provider, tempo_map)
        return pcm_for_path
    if pcm_provider is not None:
        _require_matching_sample_rate(pcm_provider, tempo_map)
        return pcm_provider
    raise ValueError(
        "play_channel_rack_once requires pcm_provider or pcm_for_path; "
        "pass a long-lived SequencerPcmProvider so PCM cache survives pattern passes"
    )


def _sequencer_provider_from_callable(
    pcm_for_path: Callable[[str], Any],
) -> SequencerPcmProvider | None:
    if isinstance(pcm_for_path, SequencerPcmProvider):
        return pcm_for_path
    owner = getattr(pcm_for_path, "__self__", None)
    if isinstance(owner, SequencerPcmProvider):
        return owner
    return None


def _require_matching_sample_rate(
    provider: SequencerPcmProvider,
    tempo_map: TempoMap,
) -> None:
    if int(provider.sample_rate) != int(tempo_map.sample_rate):
        raise ValueError(
            "pcm_provider.sample_rate must match tempo_map.sample_rate "
            f"(got provider={provider.sample_rate}, tempo_map={tempo_map.sample_rate})"
        )


def warm_channel_rack_pcm(
    state: ChannelRackState,
    provider: SequencerPcmProvider,
) -> None:
    """Decode/cache every assigned sample path before scheduling voices.

    Raises ``ValueError`` when unique assigned paths exceed ``provider.max_entries``
    so prewarming cannot silently evict samples still required for the pass.
    """

    paths: list[str] = []
    seen: set[str] = set()
    for channel in state.channels:
        path = channel.sample_path
        if path is None or path == "" or path.isspace() or path in seen:
            continue
        seen.add(path)
        paths.append(path)

    if len(paths) > provider.max_entries:
        raise ValueError(
            "warm_channel_rack_pcm requires provider.max_entries >= number of "
            f"unique sample paths (need {len(paths)}, max_entries={provider.max_entries})"
        )

    for path in paths:
        provider.pcm_for_path(path)


__all__ = [
    "ChannelRackState",
    "add_user_channel",
    "build_channel_rack_state",
    "play_channel_rack_once",
    "toggle_step",
    "warm_channel_rack_pcm",
]
