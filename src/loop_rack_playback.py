"""Natural-cycle Loop Rack playback — controller-owned finite PCM cycles (#926).

Schedules successive finite native PCM voices at absolute
``play_anchor + n * ceil(pcm_frame_count / rate)`` boundaries while Rack Play
is active. Does not own transport, Pattern Core shapes, or PatternPassPlayer.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .channel_rack import (
    ChannelRackState,
    is_explicit_loop,
    sample_class_for_channel,
    user_metadata_source_bpm,
)
from .native_audio import (
    SB_MAX_VOICES,
    SB_SOURCE_PCM_BUFFER,
    SB_VOICE_IDLE,
    VoiceConfig,
)
from .session_grid import compute_sync_playback_rate
from .workbench_live_kit import LiveKitState


@dataclass(frozen=True)
class LoopCycleSpec:
    channel_id: str
    sample_path: str
    pcm_frame_count: int
    source_bpm: float | None
    playback_rate: float
    effective_cycle_duration_frames: int
    play_anchor_engine_frame: int


@dataclass(frozen=True)
class LoopTickResult:
    scheduled_voice_ids: tuple[int, ...]
    scheduled_count: int
    skipped_missing_source_count: int
    skipped_voice_limit_count: int
    skipped_engine_error_count: int
    next_cycle_index_by_channel: Mapping[str, int]


def pcm_frame_count(pcm: Any) -> int:
    """Return interleaved frame count: ``samples.size // channels``."""
    if pcm is None:
        raise ValueError("pcm buffer is required")
    channels = int(getattr(pcm, "channels", 0) or 0)
    if channels not in (1, 2):
        raise ValueError(f"pcm channels must be 1 or 2, got {channels}")
    samples = getattr(pcm, "samples", None)
    if samples is None:
        raise ValueError("pcm samples are required")
    size = int(getattr(samples, "size", 0) or 0)
    frames = size // channels
    if frames <= 0:
        raise ValueError("pcm frame_count must be > 0")
    return frames


def effective_cycle_duration_frames(
    pcm_frame_count_value: int, playback_rate: float
) -> int:
    """``ceil(pcm_frame_count / playback_rate)`` matching native finite EOF."""
    try:
        rate = float(playback_rate)
    except (TypeError, ValueError) as exc:
        raise ValueError("playback_rate must be a finite float > 0") from exc
    if not math.isfinite(rate) or rate <= 0:
        raise ValueError("playback_rate must be a finite float > 0")
    frames = int(pcm_frame_count_value)
    if frames <= 0:
        raise ValueError("pcm_frame_count must be > 0")
    return int(math.ceil(frames / rate))


def cycle_start_engine_frame(
    play_anchor_engine_frame: int, cycle_index: int, duration_frames: int
) -> int:
    if cycle_index < 0:
        raise ValueError("cycle_index must be >= 0")
    if duration_frames <= 0:
        raise ValueError("duration_frames must be > 0")
    return int(play_anchor_engine_frame) + int(cycle_index) * int(duration_frames)


def build_loop_cycle_specs(
    *,
    state: ChannelRackState,
    live_kit: LiveKitState,
    pcm_for_path: Callable[[str], Any],
    play_anchor_engine_frame: int,
    sync_enabled: bool,
    master_bpm: float,
    user_metadata: Mapping[str, Any] | None = None,
) -> tuple[LoopCycleSpec, ...]:
    """Build frozen per-Play specs for explicit loop channels only.

    ``user_metadata`` is the resolved path-keyed binding from
    ``docs/USER_CHANNEL_CLASSIFICATION_AUTHORITY.md`` §1. User loop channels
    take their ``source_bpm`` from the same already-read library row, which
    closes the second seam SYNC-on user loops would otherwise need. A missing or
    unusable bound BPM stays fail-closed under SYNC exactly like a Live Kit
    assignment without BPM.
    """
    specs: list[LoopCycleSpec] = []
    for channel in state.channels:
        sample_class = sample_class_for_channel(
            channel, live_kit, user_metadata=user_metadata
        )
        if not is_explicit_loop(sample_class):
            continue
        path = channel.sample_path
        if path is None or path == "":
            continue
        if channel.live_kit_group is None and channel.live_kit_slot is None:
            source_bpm = user_metadata_source_bpm(channel, user_metadata=user_metadata)
        else:
            assignment = live_kit.assignment_for(
                channel.live_kit_group, channel.live_kit_slot
            )
            source_bpm = (
                getattr(assignment, "bpm", None) if assignment is not None else None
            )
        rate, status = compute_sync_playback_rate(master_bpm, source_bpm, sync_enabled)
        if sync_enabled and status != "sync":
            continue
        pcm = pcm_for_path(path)
        if pcm is None:
            continue
        try:
            frames = pcm_frame_count(pcm)
            duration = effective_cycle_duration_frames(frames, rate)
        except ValueError:
            continue
        specs.append(
            LoopCycleSpec(
                channel_id=channel.channel_id,
                sample_path=path,
                pcm_frame_count=frames,
                source_bpm=float(source_bpm) if source_bpm is not None else None,
                playback_rate=float(rate),
                effective_cycle_duration_frames=duration,
                play_anchor_engine_frame=int(play_anchor_engine_frame),
            )
        )
    return tuple(specs)


@dataclass
class _ChannelCycleState:
    spec: LoopCycleSpec
    next_cycle_index: int = 0
    sounding_voice_id: int | None = None
    scheduled_future_voice_id: int | None = None


class NaturalCycleLoopPlayer:
    """Bounded absolute-cycle scheduler for one Rack Play session."""

    def __init__(
        self,
        specs: Sequence[LoopCycleSpec],
        *,
        pcm_for_path: Callable[[str], Any],
        lookahead_frames: int,
        max_voices: int = SB_MAX_VOICES,
    ) -> None:
        if not isinstance(lookahead_frames, int) or isinstance(lookahead_frames, bool):
            raise TypeError("lookahead_frames must be an int")
        if lookahead_frames < 0:
            raise ValueError("lookahead_frames must be >= 0")
        if not isinstance(max_voices, int) or isinstance(max_voices, bool):
            raise TypeError("max_voices must be an int")
        if max_voices < 0 or max_voices > SB_MAX_VOICES:
            raise ValueError(f"max_voices must be in 0..{SB_MAX_VOICES}")
        self._pcm_for_path = pcm_for_path
        self._lookahead_frames = lookahead_frames
        self._max_voices = max_voices
        self._channels: dict[str, _ChannelCycleState] = {
            spec.channel_id: _ChannelCycleState(spec=spec) for spec in specs
        }
        self._owned_live: dict[int, dict[str, Any]] = {}
        self._scheduled_voice_ids: list[int] = []
        self._skipped_missing_source_count = 0
        self._skipped_voice_limit_count = 0
        self._skipped_engine_error_count = 0
        self._stopped = False

    @property
    def next_cycle_index_by_channel(self) -> Mapping[str, int]:
        return {
            channel_id: state.next_cycle_index
            for channel_id, state in self._channels.items()
        }

    def _snapshot_total_and_states(
        self, engine: Any
    ) -> tuple[int, dict[int, int]]:
        getter = getattr(engine, "get_snapshot", None)
        snapshot = getter() if callable(getter) else engine.snapshot()
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

    def _reclaim_owned_idle(self, engine: Any, *, engine_frame: int) -> None:
        _total, states = self._snapshot_total_and_states(engine)
        for voice_id in list(self._owned_live):
            meta = self._owned_live[voice_id]
            state = states.get(voice_id)
            if state is None:
                self._owned_live.pop(voice_id, None)
                self._clear_channel_voice_refs(voice_id)
                continue
            if state != SB_VOICE_IDLE:
                meta["seen_active"] = True
                continue
            if not meta["seen_active"] and engine_frame <= int(meta["start_frame"]):
                continue
            try:
                engine.remove_voice(voice_id)
            except Exception:
                self._skipped_engine_error_count += 1
                continue
            self._owned_live.pop(voice_id, None)
            self._clear_channel_voice_refs(voice_id)

    def _clear_channel_voice_refs(self, voice_id: int) -> None:
        for channel_state in self._channels.values():
            if channel_state.sounding_voice_id == voice_id:
                channel_state.sounding_voice_id = None
            if channel_state.scheduled_future_voice_id == voice_id:
                channel_state.scheduled_future_voice_id = None

    def _materialize_cycle(
        self,
        *,
        channel_state: _ChannelCycleState,
        cycle_index: int,
        engine_frame: int,
        engine: Any,
        allocate_voice_id: Callable[[], int],
        total_voice_count: int,
    ) -> int | None:
        spec = channel_state.spec
        start = cycle_start_engine_frame(
            spec.play_anchor_engine_frame,
            cycle_index,
            spec.effective_cycle_duration_frames,
        )
        if start > engine_frame + self._lookahead_frames:
            return None
        remaining = self._max_voices - total_voice_count
        if remaining <= 0:
            self._skipped_voice_limit_count += 1
            return None
        pcm = self._pcm_for_path(spec.sample_path)
        if pcm is None:
            self._skipped_missing_source_count += 1
            channel_state.next_cycle_index = cycle_index + 1
            return None
        allocated_id = allocate_voice_id()
        config = VoiceConfig(
            id=allocated_id,
            source_type=SB_SOURCE_PCM_BUFFER,
            pcm_buffer=pcm,
            initial_rate=float(spec.playback_rate),
        )
        try:
            created_id = engine.create_voice(config)
        except Exception:
            self._skipped_engine_error_count += 1
            channel_state.next_cycle_index = cycle_index + 1
            return None
        try:
            engine.schedule_voice_start(created_id, start)
        except Exception:
            self._skipped_engine_error_count += 1
            try:
                engine.remove_voice(created_id)
            except Exception:
                pass
            channel_state.next_cycle_index = cycle_index + 1
            return None
        self._owned_live[created_id] = {
            "start_frame": start,
            "seen_active": False,
            "channel_id": spec.channel_id,
            "cycle_index": cycle_index,
        }
        self._scheduled_voice_ids.append(created_id)
        channel_state.next_cycle_index = cycle_index + 1
        if start <= engine_frame:
            channel_state.sounding_voice_id = created_id
            channel_state.scheduled_future_voice_id = None
        else:
            channel_state.scheduled_future_voice_id = created_id
        return created_id

    @staticmethod
    def _first_nonexpired_cycle_index(
        channel_state: _ChannelCycleState, *, engine_frame: int
    ) -> int:
        """Return the first absolute cycle boundary that has not elapsed."""
        spec = channel_state.spec
        duration = spec.effective_cycle_duration_frames
        elapsed = int(engine_frame) - int(spec.play_anchor_engine_frame)
        if elapsed <= 0:
            return channel_state.next_cycle_index
        first_nonexpired = (elapsed + duration - 1) // duration
        return max(channel_state.next_cycle_index, first_nonexpired)

    def tick(
        self,
        *,
        engine_frame: int,
        engine: Any,
        allocate_voice_id: Callable[[], int],
    ) -> LoopTickResult:
        if self._stopped:
            return LoopTickResult(
                scheduled_voice_ids=(),
                scheduled_count=len(self._scheduled_voice_ids),
                skipped_missing_source_count=self._skipped_missing_source_count,
                skipped_voice_limit_count=self._skipped_voice_limit_count,
                skipped_engine_error_count=self._skipped_engine_error_count,
                next_cycle_index_by_channel=dict(self.next_cycle_index_by_channel),
            )
        if not isinstance(engine_frame, int) or isinstance(engine_frame, bool):
            raise TypeError("engine_frame must be an int")
        if engine_frame < 0:
            raise ValueError("engine_frame must be non-negative")

        self._reclaim_owned_idle(engine, engine_frame=engine_frame)
        newly: list[int] = []
        for channel_state in self._channels.values():
            # Promote due future voice to sounding.
            future_id = channel_state.scheduled_future_voice_id
            if future_id is not None:
                meta = self._owned_live.get(future_id)
                if meta is not None and int(meta["start_frame"]) <= engine_frame:
                    channel_state.sounding_voice_id = future_id
                    channel_state.scheduled_future_voice_id = None

            # Never materialize stale cycles after a UI stall or voice-budget
            # pressure. Cycle boundaries remain absolute from the Play anchor.
            channel_state.next_cycle_index = self._first_nonexpired_cycle_index(
                channel_state,
                engine_frame=engine_frame,
            )

            # At most one sounding + one future scheduled ownership per channel.
            while True:
                if (
                    channel_state.sounding_voice_id is not None
                    and channel_state.scheduled_future_voice_id is not None
                ):
                    break
                if (
                    channel_state.sounding_voice_id is None
                    and channel_state.scheduled_future_voice_id is not None
                ):
                    break
                total, _states = self._snapshot_total_and_states(engine)
                created = self._materialize_cycle(
                    channel_state=channel_state,
                    cycle_index=channel_state.next_cycle_index,
                    engine_frame=engine_frame,
                    engine=engine,
                    allocate_voice_id=allocate_voice_id,
                    total_voice_count=total,
                )
                if created is None:
                    break
                newly.append(created)
                # After scheduling one cycle, re-evaluate ownership caps.
                if channel_state.sounding_voice_id is None:
                    # Just scheduled current-or-future; loop to fill the other slot if needed.
                    continue
                if channel_state.scheduled_future_voice_id is not None:
                    break
                # Sounding exists; try one future within lookahead, then stop.
                continue

        return LoopTickResult(
            scheduled_voice_ids=tuple(newly),
            scheduled_count=len(self._scheduled_voice_ids),
            skipped_missing_source_count=self._skipped_missing_source_count,
            skipped_voice_limit_count=self._skipped_voice_limit_count,
            skipped_engine_error_count=self._skipped_engine_error_count,
            next_cycle_index_by_channel=dict(self.next_cycle_index_by_channel),
        )

    def stop(self, engine: Any) -> None:
        self._stopped = True
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
        for channel_state in self._channels.values():
            channel_state.sounding_voice_id = None
            channel_state.scheduled_future_voice_id = None


__all__ = [
    "LoopCycleSpec",
    "LoopTickResult",
    "NaturalCycleLoopPlayer",
    "build_loop_cycle_specs",
    "cycle_start_engine_frame",
    "effective_cycle_duration_frames",
    "pcm_frame_count",
]
