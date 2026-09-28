"""Minimal one-pass Pattern to NativeAudio scheduling.

Plans absolute engine frames via TempoMap, then schedules PCM voices through
an injected native engine. Audition and preview owners are intentionally unused.
UI rack and song-timeline surfaces are out of scope for this seam.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Protocol

from .native_audio import (
    SB_MAX_VOICES,
    SB_SOURCE_PCM_BUFFER,
    PcmBufferConfig,
    VoiceConfig,
)
from .pattern_core import Channel, Pattern
from .session_grid import TempoMap


@dataclass(frozen=True)
class ScheduledTrigger:
    """One planned pattern trigger at an absolute engine frame."""

    channel_id: str
    sample_path: str | None
    position: Fraction
    engine_frame: int


@dataclass(frozen=True)
class PlaybackScheduleResult:
    """Observable outcome of one ``schedule_pattern_once`` call."""

    scheduled_voice_ids: tuple[int, ...]
    scheduled_count: int
    skipped_missing_source_count: int
    skipped_voice_limit_count: int
    skipped_engine_error_count: int


class _NativeEngine(Protocol):
    def create_voice(self, config: VoiceConfig) -> int: ...

    def schedule_voice_start(self, voice_id: int, engine_frame: int) -> None: ...


def plan_pattern_once(
    *,
    pattern: Pattern,
    channels_by_id: Mapping[str, Channel],
    tempo_map: TempoMap,
    pattern_start_quarter: Fraction,
    pattern_start_engine_frame: int,
) -> tuple[ScheduledTrigger, ...]:
    """Pure Pattern → absolute engine-frame plan (no native side effects)."""
    if type(pattern_start_quarter) is not Fraction:
        raise TypeError("pattern_start_quarter must be an exact Fraction")
    if not isinstance(pattern_start_engine_frame, int) or isinstance(
        pattern_start_engine_frame, bool
    ):
        raise TypeError("pattern_start_engine_frame must be an int")

    start_session_frame = tempo_map.quarter_note_to_frame(pattern_start_quarter)
    planned: list[ScheduledTrigger] = []
    for trigger in pattern.triggers:
        absolute_quarter = pattern_start_quarter + trigger.position
        event_session_frame = tempo_map.quarter_note_to_frame(absolute_quarter)
        engine_frame = pattern_start_engine_frame + (
            event_session_frame - start_session_frame
        )
        if engine_frame < 0:
            raise ValueError(f"engine_frame must be non-negative, got {engine_frame}")
        channel = channels_by_id.get(trigger.channel_id)
        sample_path = channel.sample_path if channel is not None else None
        planned.append(
            ScheduledTrigger(
                channel_id=trigger.channel_id,
                sample_path=sample_path,
                position=trigger.position,
                engine_frame=engine_frame,
            )
        )
    return tuple(planned)


def schedule_pattern_once(
    *,
    planned_triggers: Sequence[ScheduledTrigger] | Iterable[ScheduledTrigger],
    engine: _NativeEngine,
    pcm_for_path: Callable[[str], PcmBufferConfig | None],
    allocate_voice_id: Callable[[], int],
    max_voices: int = SB_MAX_VOICES,
) -> PlaybackScheduleResult:
    """Schedule one pattern pass onto an injected native-compatible engine."""
    if not isinstance(max_voices, int) or isinstance(max_voices, bool) or max_voices < 0:
        raise ValueError("max_voices must be a non-negative int")

    scheduled_voice_ids: list[int] = []
    skipped_missing_source_count = 0
    skipped_voice_limit_count = 0
    skipped_engine_error_count = 0
    voices_created = 0

    for trigger in planned_triggers:
        sample_path = trigger.sample_path
        if sample_path is None or sample_path == "":
            skipped_missing_source_count += 1
            continue

        pcm = pcm_for_path(sample_path)
        if pcm is None:
            skipped_missing_source_count += 1
            continue

        if voices_created >= max_voices:
            skipped_voice_limit_count += 1
            continue

        allocated_id = allocate_voice_id()
        config = VoiceConfig(
            id=allocated_id,
            source_type=SB_SOURCE_PCM_BUFFER,
            pcm_buffer=pcm,
            initial_rate=1.0,
        )
        try:
            created_id = engine.create_voice(config)
        except Exception:
            skipped_engine_error_count += 1
            continue

        voices_created += 1
        try:
            engine.schedule_voice_start(created_id, trigger.engine_frame)
        except Exception:
            skipped_engine_error_count += 1
            continue

        scheduled_voice_ids.append(created_id)

    return PlaybackScheduleResult(
        scheduled_voice_ids=tuple(scheduled_voice_ids),
        scheduled_count=len(scheduled_voice_ids),
        skipped_missing_source_count=skipped_missing_source_count,
        skipped_voice_limit_count=skipped_voice_limit_count,
        skipped_engine_error_count=skipped_engine_error_count,
    )


__all__ = [
    "PlaybackScheduleResult",
    "ScheduledTrigger",
    "plan_pattern_once",
    "schedule_pattern_once",
]
