"""Minimal one-pass Pattern to NativeAudio scheduling.

Plans absolute engine frames via TempoMap, then schedules PCM voices through
an injected native engine. Audition and preview owners are intentionally unused.
UI rack and song-timeline surfaces are out of scope for this seam.

Surfaces:
- ``plan_pattern_once`` — pure full-pass plan
- ``schedule_pattern_once`` — eager create-budget helper (no reclaim)
- ``PatternPassPlayer`` — stateful bounded materialization + IDLE reclaim
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Protocol

from .native_audio import (
    SB_MAX_VOICES,
    SB_SOURCE_PCM_BUFFER,
    SB_VOICE_IDLE,
    PcmBufferConfig,
    VoiceConfig,
)
from .pattern_core import Channel, Pattern, require_triggers_reference_known_channels
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


@dataclass(frozen=True)
class PatternPassTickResult:
    """Observable outcome of one ``PatternPassPlayer.tick`` call."""

    scheduled_voice_ids: tuple[int, ...]
    scheduled_count: int
    skipped_missing_source_count: int
    skipped_voice_limit_count: int
    skipped_engine_error_count: int
    pending_count: int
    live_voice_count: int
    total_voice_count: int


class _NativeEngine(Protocol):
    def create_voice(self, config: VoiceConfig) -> int: ...

    def schedule_voice_start(self, voice_id: int, engine_frame: int) -> None: ...


class _LifecycleEngine(Protocol):
    def create_voice(self, config: VoiceConfig) -> int: ...

    def schedule_voice_start(self, voice_id: int, engine_frame: int) -> None: ...

    def stop_voice(self, voice_id: int) -> None: ...

    def remove_voice(self, voice_id: int) -> None: ...

    def get_snapshot(self) -> Any: ...


def _validate_non_negative_int(value: object, *, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative int")
    return value


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

    # Membership fail-closed at this public seam (#681): unknown channel_id is
    # invalid context, not a missing sample. Empty sample_path stays fail-soft.
    require_triggers_reference_known_channels(
        pattern.triggers,
        known_channel_ids=channels_by_id.keys(),
    )

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
        channel = channels_by_id[trigger.channel_id]
        planned.append(
            ScheduledTrigger(
                channel_id=trigger.channel_id,
                sample_path=channel.sample_path,
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
    """Eager helper: create+schedule up to ``max_voices`` in one call (no reclaim)."""
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


@dataclass
class PatternPassPlayer:
    """Stateful control-thread owner for one finite pattern pass.

    Materialises voices inside an injectable lookahead window, reclaims owned
    IDLE voices, and respects engine-global ``SB_MAX_VOICES`` via snapshot
    ``total_voice_count``. Does not steal voices and does not redefine the
    eager ``schedule_pattern_once`` helper.
    """

    _pending: deque[ScheduledTrigger] = field(init=False, repr=False)
    _owned_live: dict[int, dict[str, Any]] = field(init=False, repr=False)
    _lookahead_frames: int = field(init=False, repr=False)
    _max_voices: int = field(init=False, repr=False)
    _scheduled_voice_ids: list[int] = field(init=False, repr=False)
    _skipped_missing_source_count: int = field(init=False, repr=False)
    _skipped_voice_limit_count: int = field(init=False, repr=False)
    _skipped_engine_error_count: int = field(init=False, repr=False)
    _stopped: bool = field(init=False, repr=False)
    planned_count: int = field(init=False)

    def __init__(
        self,
        planned_triggers: Sequence[ScheduledTrigger] | Iterable[ScheduledTrigger],
        *,
        lookahead_frames: int,
        max_voices: int = SB_MAX_VOICES,
    ) -> None:
        self._lookahead_frames = _validate_non_negative_int(
            lookahead_frames, name="lookahead_frames"
        )
        self._max_voices = _validate_non_negative_int(max_voices, name="max_voices")
        if self._max_voices > SB_MAX_VOICES:
            raise ValueError(
                f"max_voices must be <= SB_MAX_VOICES ({SB_MAX_VOICES}), "
                f"got {self._max_voices}"
            )
        ordered = sorted(
            list(planned_triggers),
            key=lambda trigger: (trigger.engine_frame, trigger.channel_id),
        )
        self._pending = deque(ordered)
        self.planned_count = len(ordered)
        # voice_id → {start_frame, seen_active}
        self._owned_live: dict[int, dict[str, Any]] = {}
        self._scheduled_voice_ids = []
        self._skipped_missing_source_count = 0
        self._skipped_voice_limit_count = 0
        self._skipped_engine_error_count = 0
        self._stopped = False

    @property
    def lookahead_frames(self) -> int:
        return self._lookahead_frames

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def live_voice_count(self) -> int:
        return len(self._owned_live)

    @property
    def scheduled_count(self) -> int:
        return len(self._scheduled_voice_ids)

    @property
    def scheduled_voice_ids(self) -> tuple[int, ...]:
        return tuple(self._scheduled_voice_ids)

    @property
    def skipped_missing_source_count(self) -> int:
        return self._skipped_missing_source_count

    @property
    def skipped_voice_limit_count(self) -> int:
        return self._skipped_voice_limit_count

    @property
    def skipped_engine_error_count(self) -> int:
        return self._skipped_engine_error_count

    @property
    def done(self) -> bool:
        return self._stopped or (
            not self._pending and not self._owned_live
        )

    def _snapshot_total_and_states(
        self, engine: _LifecycleEngine
    ) -> tuple[int, dict[int, int]]:
        snapshot = engine.get_snapshot()
        total = int(getattr(snapshot, "total_voice_count", 0))
        states: dict[int, int] = {}
        voice_ids = getattr(snapshot, "voice_ids", ())
        voice_states = getattr(snapshot, "voice_states", ())
        limit = min(total, len(voice_ids), len(voice_states), SB_MAX_VOICES)
        for index in range(limit):
            voice_id = int(voice_ids[index])
            if voice_id == 0:
                continue
            states[voice_id] = int(voice_states[index])
        return total, states

    def _reclaim_owned_idle(
        self, engine: _LifecycleEngine, *, engine_frame: int
    ) -> None:
        _total, states = self._snapshot_total_and_states(engine)
        for voice_id in list(self._owned_live):
            meta = self._owned_live[voice_id]
            state = states.get(voice_id)
            if state is None:
                # Voice disappeared from snapshot (foreign remove) — drop tracking.
                self._owned_live.pop(voice_id, None)
                continue
            if state != SB_VOICE_IDLE:
                # SCHEDULED / PLAYING / STOPPING: schedule command was observed.
                meta["seen_active"] = True
                continue
            # IDLE may mean "created, schedule not yet applied" OR "EOF finished".
            # Only reclaim after we have seen a non-IDLE state, or after the
            # audio clock has advanced strictly past the requested start frame
            # (same-buffer start+EOF can skip intermediate states in snapshots).
            if not meta["seen_active"] and engine_frame <= int(meta["start_frame"]):
                continue
            try:
                engine.remove_voice(voice_id)
            except Exception:
                self._skipped_engine_error_count += 1
                continue
            self._owned_live.pop(voice_id, None)

    def tick(
        self,
        *,
        engine_frame: int,
        engine: _LifecycleEngine,
        pcm_for_path: Callable[[str], PcmBufferConfig | None],
        allocate_voice_id: Callable[[], int],
        lookahead_frames: int | None = None,
    ) -> PatternPassTickResult:
        """Reclaim owned IDLE voices, then materialise due/lookahead events."""
        if self._stopped:
            total, _states = self._snapshot_total_and_states(engine)
            return PatternPassTickResult(
                scheduled_voice_ids=(),
                scheduled_count=self.scheduled_count,
                skipped_missing_source_count=self._skipped_missing_source_count,
                skipped_voice_limit_count=self._skipped_voice_limit_count,
                skipped_engine_error_count=self._skipped_engine_error_count,
                pending_count=0,
                live_voice_count=0,
                total_voice_count=total,
            )

        if not isinstance(engine_frame, int) or isinstance(engine_frame, bool):
            raise TypeError("engine_frame must be an int")
        if engine_frame < 0:
            raise ValueError("engine_frame must be non-negative")

        window = (
            self._lookahead_frames
            if lookahead_frames is None
            else _validate_non_negative_int(lookahead_frames, name="lookahead_frames")
        )
        horizon = engine_frame + window

        self._reclaim_owned_idle(engine, engine_frame=engine_frame)

        tick_scheduled: list[int] = []
        while self._pending:
            trigger = self._pending[0]
            if trigger.engine_frame > horizon:
                break

            sample_path = trigger.sample_path
            if sample_path is None or sample_path == "":
                self._pending.popleft()
                self._skipped_missing_source_count += 1
                continue

            pcm = pcm_for_path(sample_path)
            if pcm is None:
                self._pending.popleft()
                self._skipped_missing_source_count += 1
                continue

            total, _states = self._snapshot_total_and_states(engine)
            remaining = self._max_voices - total
            if remaining <= 0:
                if trigger.engine_frame <= engine_frame:
                    self._pending.popleft()
                    self._skipped_voice_limit_count += 1
                    continue
                break

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
                self._pending.popleft()
                self._skipped_engine_error_count += 1
                continue

            try:
                engine.schedule_voice_start(created_id, trigger.engine_frame)
            except Exception:
                self._pending.popleft()
                self._skipped_engine_error_count += 1
                try:
                    engine.remove_voice(created_id)
                except Exception:
                    self._skipped_engine_error_count += 1
                continue

            self._pending.popleft()
            self._owned_live[created_id] = {
                "start_frame": trigger.engine_frame,
                "seen_active": False,
            }
            self._scheduled_voice_ids.append(created_id)
            tick_scheduled.append(created_id)

        total, _states = self._snapshot_total_and_states(engine)
        return PatternPassTickResult(
            scheduled_voice_ids=tuple(tick_scheduled),
            scheduled_count=self.scheduled_count,
            skipped_missing_source_count=self._skipped_missing_source_count,
            skipped_voice_limit_count=self._skipped_voice_limit_count,
            skipped_engine_error_count=self._skipped_engine_error_count,
            pending_count=len(self._pending),
            live_voice_count=len(self._owned_live),
            total_voice_count=total,
        )

    def stop(self, engine: _LifecycleEngine) -> None:
        """Stop and remove all owned live voices; drop remaining pending."""
        for voice_id in list(self._owned_live):
            try:
                engine.stop_voice(voice_id)
            except Exception:
                self._skipped_engine_error_count += 1
            try:
                engine.remove_voice(voice_id)
            except Exception:
                self._skipped_engine_error_count += 1
            self._owned_live.pop(voice_id, None)
        self._pending.clear()
        self._stopped = True


__all__ = [
    "PlaybackScheduleResult",
    "PatternPassPlayer",
    "PatternPassTickResult",
    "ScheduledTrigger",
    "plan_pattern_once",
    "schedule_pattern_once",
]
