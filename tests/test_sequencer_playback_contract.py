"""TEST_GATE / TEST_FREEZE — Minimal Sequencer Playback contract.

Canonical authority:
- docs/PRODUCT_WORKFLOW_CANON.md (build-order step 4)
- docs/SEQUENCER_PLAYBACK_CONTRACT.md
- docs/PATTERN_CORE_CONTRACT.md
- src/pattern_core.py (Channel / Trigger / Pattern)
- src/session_grid.py (TempoMap Fraction quarter notes)
- src/native_audio.py (VoiceConfig / PcmBufferConfig / SB_MAX_VOICES)

This file freezes the public seam ``src.sequencer_playback`` before any product
implementation. Expected baseline on current main: intentional RED until a
separate IMPLEMENTATION_GATE lands the module.

v1 scope frozen here:
- ONE_PATTERN_PASS (no looping)
- FAIL_SOFT_NO_VOICE_STEALING
- ``schedule_pattern_once`` remains the eager create-budget helper
- ``PatternPassPlayer`` owns bounded materialization + IDLE reclaim
- ``SB_MAX_VOICES`` is engine-global registered capacity (``total_voice_count``)
- injectable ``lookahead_frames`` (no hardcoded sample_rate product law)
- injected voice-id allocator
- injected PCM provider (no decode in audio callback)
- TempoMap + engine-frame anchor formula
- no TransportAwarePreview / Screen-2 / QML / arrangement
"""

from __future__ import annotations

import ast
import importlib
import inspect
from dataclasses import dataclass, fields, is_dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pytest

from src.native_audio import (
    SB_MAX_VOICES,
    SB_SOURCE_PCM_BUFFER,
    SB_VOICE_IDLE,
    SB_VOICE_PLAYING,
    SB_VOICE_SCHEDULED,
    PcmBufferConfig,
    VoiceConfig,
)
from src.pattern_core import Channel, Pattern, Trigger
from src.session_grid import TempoMap


REQUIRED_PUBLIC_SYMBOLS = (
    "ScheduledTrigger",
    "PlaybackScheduleResult",
    "PatternPassPlayer",
    "PatternPassTickResult",
    "plan_pattern_once",
    "schedule_pattern_once",
)

FORBIDDEN_SEQUENCER_SURFACE_TOKENS = (
    "TransportAwarePreview",
    "WorkbenchPreviewPlayer",
    "Screen2",
    "ChannelRack",
    "workbench_qml",
    "PySide6",
    "arrangement",
    "BeatGrid",
    "start_ms",
    "wall_clock",
    "steal_voice",
    "voice_steal",
)


def _sequencer_or_fail():
    try:
        return importlib.import_module("src.sequencer_playback")
    except ModuleNotFoundError as exc:
        if exc.name in {"src.sequencer_playback", "sequencer_playback"} or (
            exc.name is not None and exc.name.endswith("sequencer_playback")
        ):
            pytest.fail(
                "MISSING_PRODUCTION_SURFACE: src.sequencer_playback "
                "(Sequencer Playback not implemented — expected RED until "
                "IMPLEMENTATION_GATE)"
            )
        raise


def _require_symbol(module, name: str):
    value = getattr(module, name, None)
    if value is None:
        pytest.fail(f"MISSING_PRODUCTION_SURFACE: src.sequencer_playback.{name}")
    return value


def _pcm(frames: int = 8, channels: int = 1) -> PcmBufferConfig:
    samples = np.linspace(-0.2, 0.2, frames * channels, dtype=np.float32)
    if channels > 1:
        samples = samples.reshape(frames, channels)
    return PcmBufferConfig(samples=samples, channels=channels)


def _channel(channel_id: str, group: str, slot: str, path: str | None) -> Channel:
    return Channel(
        channel_id=channel_id,
        live_kit_group=group,
        live_kit_slot=slot,
        sample_path=path,
    )


def _channels(*items: Channel) -> dict[str, Channel]:
    return {ch.channel_id: ch for ch in items}


class FakeNativeEngine:
    """In-memory native engine double — no hardware / no ctypes.

    Tracks registered voices with PCM lengths so tests can advance
    ``engine_frame`` and observe IDLE reclaim / global ``total_voice_count``.
    """

    def __init__(self) -> None:
        self.create_calls: list[VoiceConfig] = []
        self.schedule_calls: list[tuple[int, int]] = []
        self.ops: list[tuple[str, Any]] = []
        self.create_errors: set[int] = set()
        self.schedule_errors: set[int] = set()
        self.stop_voice_calls: list[int] = []
        self.remove_voice_calls: list[int] = []
        # Optional: map VoiceConfig.id → distinct native-returned voice id.
        self.returned_voice_ids: dict[int, int] = {}
        self.engine_frame: int = 0
        self._voices: dict[int, dict[str, Any]] = {}
        # When True, schedule_voice_start only records the start frame; state
        # stays IDLE until advance_to (models native command-queue latency).
        self.defer_schedule_apply: bool = False

    def seed_foreign_voice(self, voice_id: int, *, pcm_frames: int = 8) -> None:
        """Register a non-player voice that still consumes global capacity."""
        self._voices[voice_id] = {
            "state": SB_VOICE_IDLE,
            "start_frame": None,
            "pcm_frames": pcm_frames,
            "foreign": True,
        }

    def advance_to(self, engine_frame: int) -> None:
        self.engine_frame = engine_frame
        for meta in self._voices.values():
            start = meta["start_frame"]
            if start is None:
                continue
            pcm_frames = int(meta["pcm_frames"])
            if engine_frame >= start + pcm_frames:
                meta["state"] = SB_VOICE_IDLE
            elif engine_frame >= start:
                meta["state"] = SB_VOICE_PLAYING
            else:
                # Future start: once the audio clock exists, a queued schedule
                # is visible as SCHEDULED (command applied in a prior callback).
                meta["state"] = SB_VOICE_SCHEDULED

    def get_snapshot(self) -> Any:
        ids = list(self._voices.keys())
        states = [int(self._voices[vid]["state"]) for vid in ids]
        pad = SB_MAX_VOICES - len(ids)
        if pad > 0:
            ids = ids + [0] * pad
            states = states + [SB_VOICE_IDLE] * pad
        else:
            ids = ids[:SB_MAX_VOICES]
            states = states[:SB_MAX_VOICES]

        @dataclass
        class _Snap:
            total_voice_count: int
            active_voice_count: int
            voice_ids: list[int]
            voice_states: list[int]
            engine_frame: int

        active = sum(1 for state in states if state == SB_VOICE_PLAYING)
        return _Snap(
            total_voice_count=len(self._voices),
            active_voice_count=active,
            voice_ids=ids,
            voice_states=states,
            engine_frame=self.engine_frame,
        )

    def create_voice(self, config: VoiceConfig) -> int:
        self.create_calls.append(config)
        self.ops.append(("create_voice", config.id))
        if config.id in self.create_errors:
            raise RuntimeError(f"native create_voice failed for {config.id}")
        voice_id = self.returned_voice_ids.get(config.id, config.id)
        pcm_frames = 8
        if config.pcm_buffer is not None:
            samples = config.pcm_buffer.samples
            channels = int(config.pcm_buffer.channels)
            pcm_frames = int(samples.size // max(channels, 1))
        self._voices[voice_id] = {
            "state": SB_VOICE_IDLE,
            "start_frame": None,
            "pcm_frames": pcm_frames,
            "foreign": False,
        }
        return voice_id

    def schedule_voice_start(self, voice_id: int, engine_frame: int) -> None:
        self.schedule_calls.append((voice_id, engine_frame))
        self.ops.append(("schedule_voice_start", (voice_id, engine_frame)))
        if voice_id in self.schedule_errors:
            raise RuntimeError(f"native schedule_voice_start failed for {voice_id}")
        meta = self._voices[voice_id]
        meta["start_frame"] = engine_frame
        if self.defer_schedule_apply:
            # Native path: command queued, voice remains IDLE until callback.
            meta["state"] = SB_VOICE_IDLE
            return
        if self.engine_frame >= engine_frame + int(meta["pcm_frames"]):
            meta["state"] = SB_VOICE_IDLE
        elif self.engine_frame >= engine_frame:
            meta["state"] = SB_VOICE_PLAYING
        else:
            meta["state"] = SB_VOICE_SCHEDULED

    def stop_voice(self, voice_id: int) -> None:
        self.stop_voice_calls.append(voice_id)
        self.ops.append(("stop_voice", voice_id))
        if voice_id in self._voices:
            self._voices[voice_id]["state"] = SB_VOICE_IDLE

    def remove_voice(self, voice_id: int) -> None:
        self.remove_voice_calls.append(voice_id)
        self.ops.append(("remove_voice", voice_id))
        self._voices.pop(voice_id, None)


# --- Public API --------------------------------------------------------------


def test_sequencer_playback_public_api_is_importable():
    module = _sequencer_or_fail()
    for name in REQUIRED_PUBLIC_SYMBOLS:
        _require_symbol(module, name)


def test_plan_single_trigger_maps_quarter_note_to_expected_engine_frame():
    module = _sequencer_or_fail()
    plan = _require_symbol(module, "plan_pattern_once")
    ScheduledTrigger = _require_symbol(module, "ScheduledTrigger")

    tempo_map = TempoMap(sample_rate=48_000, bpm=120)
    pattern = Pattern(
        pattern_id="pat_one",
        length_quarter_notes=Fraction(4, 1),
        triggers=[Trigger(channel_id="ch_kick", position=Fraction(1, 1))],
    )
    channels = _channels(
        _channel("ch_kick", "Kick + Bass", "Kick", "synthetic/kick.wav")
    )

    planned = plan(
        pattern=pattern,
        channels_by_id=channels,
        tempo_map=tempo_map,
        pattern_start_quarter=Fraction(0, 1),
        pattern_start_engine_frame=100_000,
    )

    assert len(planned) == 1
    event = planned[0]
    assert isinstance(event, ScheduledTrigger)
    assert is_dataclass(event) and event.__dataclass_params__.frozen
    assert event.channel_id == "ch_kick"
    assert event.sample_path == "synthetic/kick.wav"
    assert event.position == Fraction(1, 1)
    assert type(event.position) is Fraction
    # 120 BPM @ 48k => 24_000 frames/quarter; engine = 100_000 + 24_000
    assert event.engine_frame == 124_000
    assert event.engine_frame >= 0


def test_plan_uses_engine_anchor_without_treating_session_frame_as_engine_frame():
    module = _sequencer_or_fail()
    plan = _require_symbol(module, "plan_pattern_once")

    tempo_map = TempoMap(sample_rate=48_000, bpm=120)
    pattern = Pattern(
        pattern_id="pat_anchor",
        length_quarter_notes=Fraction(4, 1),
        triggers=[Trigger(channel_id="ch_kick", position=Fraction(0, 1))],
    )
    channels = _channels(
        _channel("ch_kick", "Kick + Bass", "Kick", "synthetic/kick.wav")
    )

    # Session frame for quarter 0 is 0; engine anchor is independent and non-zero.
    planned = plan(
        pattern=pattern,
        channels_by_id=channels,
        tempo_map=tempo_map,
        pattern_start_quarter=Fraction(0, 1),
        pattern_start_engine_frame=777_000,
    )
    assert planned[0].engine_frame == 777_000
    assert tempo_map.quarter_note_to_frame(Fraction(0, 1)) == 0
    assert planned[0].engine_frame != tempo_map.quarter_note_to_frame(Fraction(0, 1))


def test_plan_crossing_tempo_change_uses_tempo_map_exactly():
    module = _sequencer_or_fail()
    plan = _require_symbol(module, "plan_pattern_once")

    tempo_map = TempoMap(sample_rate=48_000, bpm=120)
    tempo_map.add_tempo_change_at_quarter(effective_quarter=Fraction(4, 1), bpm=60)

    # Pattern starts at absolute quarter 3; trigger at relative +2 => absolute 5.
    pattern = Pattern(
        pattern_id="pat_tempo",
        length_quarter_notes=Fraction(8, 1),
        triggers=[Trigger(channel_id="ch_kick", position=Fraction(2, 1))],
    )
    channels = _channels(
        _channel("ch_kick", "Kick + Bass", "Kick", "synthetic/kick.wav")
    )
    pattern_start_engine_frame = 50_000

    planned = plan(
        pattern=pattern,
        channels_by_id=channels,
        tempo_map=tempo_map,
        pattern_start_quarter=Fraction(3, 1),
        pattern_start_engine_frame=pattern_start_engine_frame,
    )

    start_session = tempo_map.quarter_note_to_frame(Fraction(3, 1))
    event_session = tempo_map.quarter_note_to_frame(Fraction(5, 1))
    expected = pattern_start_engine_frame + (event_session - start_session)
    # 24k frames (q3→q4 @120) + 48k frames (q4→q5 @60) = +72k
    assert event_session - start_session == 72_000
    assert planned[0].engine_frame == expected
    assert planned[0].engine_frame == pattern_start_engine_frame + 72_000


def test_same_position_triggers_share_engine_frame_and_keep_channel_id_order():
    module = _sequencer_or_fail()
    plan = _require_symbol(module, "plan_pattern_once")

    tempo_map = TempoMap(sample_rate=48_000, bpm=120)
    # Input scrambled; Pattern Core normalizes by (position, channel_id).
    pattern = Pattern(
        pattern_id="pat_same",
        length_quarter_notes=Fraction(4, 1),
        triggers=[
            Trigger(channel_id="ch_pad", position=Fraction(1, 1)),
            Trigger(channel_id="ch_lead", position=Fraction(1, 1)),
        ],
    )
    channels = _channels(
        _channel("ch_lead", "Melodic", "Lead", "synthetic/lead.wav"),
        _channel("ch_pad", "Melodic", "Pad", "synthetic/pad.wav"),
    )

    planned = plan(
        pattern=pattern,
        channels_by_id=channels,
        tempo_map=tempo_map,
        pattern_start_quarter=Fraction(0, 1),
        pattern_start_engine_frame=10_000,
    )
    assert [t.channel_id for t in planned] == ["ch_lead", "ch_pad"]
    assert planned[0].engine_frame == planned[1].engine_frame == 34_000


def test_schedule_creates_pcm_voice_then_schedules_exact_frame():
    module = _sequencer_or_fail()
    plan = _require_symbol(module, "plan_pattern_once")
    schedule = _require_symbol(module, "schedule_pattern_once")
    PlaybackScheduleResult = _require_symbol(module, "PlaybackScheduleResult")

    tempo_map = TempoMap(sample_rate=48_000, bpm=120)
    pattern = Pattern(
        pattern_id="pat_sched",
        length_quarter_notes=Fraction(4, 1),
        triggers=[Trigger(channel_id="ch_kick", position=Fraction(1, 1))],
    )
    channels = _channels(
        _channel("ch_kick", "Kick + Bass", "Kick", "synthetic/kick.wav")
    )
    planned = plan(
        pattern=pattern,
        channels_by_id=channels,
        tempo_map=tempo_map,
        pattern_start_quarter=Fraction(0, 1),
        pattern_start_engine_frame=100_000,
    )

    engine = FakeNativeEngine()
    pcm = _pcm()
    result = schedule(
        planned_triggers=planned,
        engine=engine,
        pcm_for_path=lambda path: pcm if path == "synthetic/kick.wav" else None,
        allocate_voice_id=lambda: 41,
        max_voices=SB_MAX_VOICES,
    )

    assert isinstance(result, PlaybackScheduleResult)
    assert is_dataclass(result) and result.__dataclass_params__.frozen
    assert result.scheduled_count == 1
    assert result.scheduled_voice_ids == (41,)
    assert result.skipped_missing_source_count == 0
    assert result.skipped_voice_limit_count == 0
    assert result.skipped_engine_error_count == 0

    assert len(engine.create_calls) == 1
    cfg = engine.create_calls[0]
    assert isinstance(cfg, VoiceConfig)
    assert cfg.id == 41
    assert cfg.source_type == SB_SOURCE_PCM_BUFFER
    assert cfg.initial_rate == 1.0
    assert cfg.pcm_buffer is pcm
    assert engine.schedule_calls == [(41, 124_000)]
    assert engine.ops[0][0] == "create_voice"
    assert engine.ops[1][0] == "schedule_voice_start"


def test_schedule_uses_voice_id_returned_by_native_create():
    """Allocator id → VoiceConfig.id → create_voice → schedule returned native id.

    Live NativeAudio returns ``voice_id.value`` from create_voice; that returned
    id may differ from ``VoiceConfig.id``. Scheduling must use the returned id.
    """
    module = _sequencer_or_fail()
    plan = _require_symbol(module, "plan_pattern_once")
    schedule = _require_symbol(module, "schedule_pattern_once")

    tempo_map = TempoMap(sample_rate=48_000, bpm=120)
    pattern = Pattern(
        pattern_id="pat_returned_id",
        length_quarter_notes=Fraction(4, 1),
        triggers=[Trigger(channel_id="ch_kick", position=Fraction(1, 1))],
    )
    channels = _channels(
        _channel("ch_kick", "Kick + Bass", "Kick", "synthetic/kick.wav")
    )
    planned = plan(
        pattern=pattern,
        channels_by_id=channels,
        tempo_map=tempo_map,
        pattern_start_quarter=Fraction(0, 1),
        pattern_start_engine_frame=100_000,
    )

    engine = FakeNativeEngine()
    engine.returned_voice_ids[41] = 9041
    result = schedule(
        planned_triggers=planned,
        engine=engine,
        pcm_for_path=lambda _path: _pcm(),
        allocate_voice_id=lambda: 41,
    )

    assert len(engine.create_calls) == 1
    assert engine.create_calls[0].id == 41
    assert engine.schedule_calls == [(9041, 124_000)]
    assert 41 not in [voice_id for voice_id, _frame in engine.schedule_calls]
    assert result.scheduled_voice_ids == (9041,)
    assert result.scheduled_count == 1


def test_voice_ids_come_from_injected_allocator():
    module = _sequencer_or_fail()
    plan = _require_symbol(module, "plan_pattern_once")
    schedule = _require_symbol(module, "schedule_pattern_once")

    tempo_map = TempoMap(sample_rate=48_000, bpm=120)
    pattern = Pattern(
        pattern_id="pat_ids",
        length_quarter_notes=Fraction(4, 1),
        triggers=[
            Trigger(channel_id="ch_kick", position=Fraction(0, 1)),
            Trigger(channel_id="ch_bass", position=Fraction(1, 1)),
        ],
    )
    channels = _channels(
        _channel("ch_kick", "Kick + Bass", "Kick", "synthetic/kick.wav"),
        _channel("ch_bass", "Kick + Bass", "Bass", "synthetic/bass.wav"),
    )
    planned = plan(
        pattern=pattern,
        channels_by_id=channels,
        tempo_map=tempo_map,
        pattern_start_quarter=Fraction(0, 1),
        pattern_start_engine_frame=0,
    )

    allocated = iter((9001, 9002))
    engine = FakeNativeEngine()
    result = schedule(
        planned_triggers=planned,
        engine=engine,
        pcm_for_path=lambda _path: _pcm(),
        allocate_voice_id=lambda: next(allocated),
    )
    assert result.scheduled_voice_ids == (9001, 9002)
    assert [c.id for c in engine.create_calls] == [9001, 9002]
    # Not a hard-coded global 1..N ownership claim.
    assert result.scheduled_voice_ids != (1, 2)


def test_concurrent_channels_create_distinct_polyphonic_voices():
    module = _sequencer_or_fail()
    plan = _require_symbol(module, "plan_pattern_once")
    schedule = _require_symbol(module, "schedule_pattern_once")

    tempo_map = TempoMap(sample_rate=48_000, bpm=120)
    pattern = Pattern(
        pattern_id="pat_poly",
        length_quarter_notes=Fraction(4, 1),
        triggers=[
            Trigger(channel_id="ch_kick", position=Fraction(1, 1)),
            Trigger(channel_id="ch_closed_hat", position=Fraction(1, 1)),
        ],
    )
    channels = _channels(
        _channel("ch_kick", "Kick + Bass", "Kick", "synthetic/kick.wav"),
        _channel("ch_closed_hat", "Drums", "Closed Hat", "synthetic/ch.wav"),
    )
    planned = plan(
        pattern=pattern,
        channels_by_id=channels,
        tempo_map=tempo_map,
        pattern_start_quarter=Fraction(0, 1),
        pattern_start_engine_frame=0,
    )
    assert planned[0].engine_frame == planned[1].engine_frame

    ids = iter((11, 12))
    engine = FakeNativeEngine()
    result = schedule(
        planned_triggers=planned,
        engine=engine,
        pcm_for_path=lambda _path: _pcm(),
        allocate_voice_id=lambda: next(ids),
    )
    assert result.scheduled_count == 2
    assert result.scheduled_voice_ids == (11, 12)
    assert engine.schedule_calls == [(11, 24_000), (12, 24_000)]


def test_pattern_playback_does_not_route_through_transport_aware_preview():
    module = _sequencer_or_fail()
    schedule = _require_symbol(module, "schedule_pattern_once")
    plan = _require_symbol(module, "plan_pattern_once")

    source = Path(inspect.getsourcefile(module) or "").read_text(encoding="utf-8")
    assert "TransportAwarePreview" not in source
    assert "WorkbenchPreviewPlayer" not in source

    # Runtime path uses only the injected engine protocol.
    sig = inspect.signature(schedule)
    assert "preview" not in sig.parameters
    assert "audition" not in sig.parameters
    assert "engine" in sig.parameters

    tempo_map = TempoMap(sample_rate=48_000, bpm=120)
    pattern = Pattern(
        pattern_id="pat_no_preview",
        length_quarter_notes=Fraction(4, 1),
        triggers=[Trigger(channel_id="ch_kick", position=Fraction(0, 1))],
    )
    channels = _channels(
        _channel("ch_kick", "Kick + Bass", "Kick", "synthetic/kick.wav")
    )
    planned = plan(
        pattern=pattern,
        channels_by_id=channels,
        tempo_map=tempo_map,
        pattern_start_quarter=Fraction(0, 1),
        pattern_start_engine_frame=0,
    )
    engine = FakeNativeEngine()
    schedule(
        planned_triggers=planned,
        engine=engine,
        pcm_for_path=lambda _path: _pcm(),
        allocate_voice_id=lambda: 7,
    )
    assert engine.create_calls and engine.schedule_calls


def test_empty_sample_path_fails_soft_without_engine_call():
    module = _sequencer_or_fail()
    plan = _require_symbol(module, "plan_pattern_once")
    schedule = _require_symbol(module, "schedule_pattern_once")

    tempo_map = TempoMap(sample_rate=48_000, bpm=120)
    pattern = Pattern(
        pattern_id="pat_empty",
        length_quarter_notes=Fraction(4, 1),
        triggers=[Trigger(channel_id="ch_kick", position=Fraction(0, 1))],
    )
    channels = _channels(_channel("ch_kick", "Kick + Bass", "Kick", None))
    planned = plan(
        pattern=pattern,
        channels_by_id=channels,
        tempo_map=tempo_map,
        pattern_start_quarter=Fraction(0, 1),
        pattern_start_engine_frame=0,
    )
    assert planned[0].sample_path is None

    engine = FakeNativeEngine()
    result = schedule(
        planned_triggers=planned,
        engine=engine,
        pcm_for_path=lambda _path: _pcm(),
        allocate_voice_id=lambda: 1,
    )
    assert result.scheduled_count == 0
    assert result.skipped_missing_source_count == 1
    assert engine.create_calls == []
    assert engine.schedule_calls == []


def test_pcm_provider_miss_fails_soft_without_engine_call():
    module = _sequencer_or_fail()
    plan = _require_symbol(module, "plan_pattern_once")
    schedule = _require_symbol(module, "schedule_pattern_once")

    tempo_map = TempoMap(sample_rate=48_000, bpm=120)
    pattern = Pattern(
        pattern_id="pat_pcm_miss",
        length_quarter_notes=Fraction(4, 1),
        triggers=[Trigger(channel_id="ch_kick", position=Fraction(0, 1))],
    )
    channels = _channels(
        _channel("ch_kick", "Kick + Bass", "Kick", "synthetic/missing.wav")
    )
    planned = plan(
        pattern=pattern,
        channels_by_id=channels,
        tempo_map=tempo_map,
        pattern_start_quarter=Fraction(0, 1),
        pattern_start_engine_frame=0,
    )

    engine = FakeNativeEngine()
    result = schedule(
        planned_triggers=planned,
        engine=engine,
        pcm_for_path=lambda _path: None,
        allocate_voice_id=lambda: 1,
    )
    assert result.scheduled_count == 0
    assert result.skipped_missing_source_count == 1
    assert engine.create_calls == []
    assert engine.schedule_calls == []


def test_native_voice_create_error_fails_soft_and_later_trigger_continues():
    module = _sequencer_or_fail()
    plan = _require_symbol(module, "plan_pattern_once")
    schedule = _require_symbol(module, "schedule_pattern_once")

    tempo_map = TempoMap(sample_rate=48_000, bpm=120)
    pattern = Pattern(
        pattern_id="pat_create_err",
        length_quarter_notes=Fraction(4, 1),
        triggers=[
            Trigger(channel_id="ch_kick", position=Fraction(0, 1)),
            Trigger(channel_id="ch_bass", position=Fraction(1, 1)),
        ],
    )
    channels = _channels(
        _channel("ch_kick", "Kick + Bass", "Kick", "synthetic/kick.wav"),
        _channel("ch_bass", "Kick + Bass", "Bass", "synthetic/bass.wav"),
    )
    planned = plan(
        pattern=pattern,
        channels_by_id=channels,
        tempo_map=tempo_map,
        pattern_start_quarter=Fraction(0, 1),
        pattern_start_engine_frame=0,
    )

    engine = FakeNativeEngine()
    engine.create_errors.add(1)
    ids = iter((1, 2))
    result = schedule(
        planned_triggers=planned,
        engine=engine,
        pcm_for_path=lambda _path: _pcm(),
        allocate_voice_id=lambda: next(ids),
    )
    assert result.skipped_engine_error_count == 1
    assert result.scheduled_voice_ids == (2,)
    assert result.scheduled_count == 1
    assert engine.schedule_calls == [(2, 24_000)]


def test_native_schedule_error_fails_soft_and_later_trigger_continues():
    module = _sequencer_or_fail()
    plan = _require_symbol(module, "plan_pattern_once")
    schedule = _require_symbol(module, "schedule_pattern_once")

    tempo_map = TempoMap(sample_rate=48_000, bpm=120)
    pattern = Pattern(
        pattern_id="pat_sched_err",
        length_quarter_notes=Fraction(4, 1),
        triggers=[
            Trigger(channel_id="ch_kick", position=Fraction(0, 1)),
            Trigger(channel_id="ch_bass", position=Fraction(1, 1)),
        ],
    )
    channels = _channels(
        _channel("ch_kick", "Kick + Bass", "Kick", "synthetic/kick.wav"),
        _channel("ch_bass", "Kick + Bass", "Bass", "synthetic/bass.wav"),
    )
    planned = plan(
        pattern=pattern,
        channels_by_id=channels,
        tempo_map=tempo_map,
        pattern_start_quarter=Fraction(0, 1),
        pattern_start_engine_frame=0,
    )

    engine = FakeNativeEngine()
    engine.schedule_errors.add(1)
    ids = iter((1, 2))
    result = schedule(
        planned_triggers=planned,
        engine=engine,
        pcm_for_path=lambda _path: _pcm(),
        allocate_voice_id=lambda: next(ids),
    )
    assert result.skipped_engine_error_count == 1
    assert result.scheduled_voice_ids == (2,)
    assert result.scheduled_count == 1
    assert len(engine.create_calls) == 2
    assert engine.schedule_calls == [(1, 0), (2, 24_000)]


def test_eager_schedule_pattern_once_create_budget_is_fail_soft_without_voice_stealing():
    """Eager helper contract: one call creates at most max_voices (no reclaim)."""
    module = _sequencer_or_fail()
    plan = _require_symbol(module, "plan_pattern_once")
    schedule = _require_symbol(module, "schedule_pattern_once")

    tempo_map = TempoMap(sample_rate=48_000, bpm=120)
    # 33 eligible triggers on one channel at distinct positions.
    triggers = [
        Trigger(channel_id="ch_kick", position=Fraction(i, 16))
        for i in range(33)
    ]
    pattern = Pattern(
        pattern_id="pat_limit",
        length_quarter_notes=Fraction(8, 1),
        triggers=triggers,
    )
    channels = _channels(
        _channel("ch_kick", "Kick + Bass", "Kick", "synthetic/kick.wav")
    )
    planned = plan(
        pattern=pattern,
        channels_by_id=channels,
        tempo_map=tempo_map,
        pattern_start_quarter=Fraction(0, 1),
        pattern_start_engine_frame=0,
    )
    assert len(planned) == 33

    next_id = iter(range(1, 100))
    engine = FakeNativeEngine()
    result = schedule(
        planned_triggers=planned,
        engine=engine,
        pcm_for_path=lambda _path: _pcm(),
        allocate_voice_id=lambda: next(next_id),
        max_voices=32,
    )
    assert result.scheduled_count == 32
    assert len(result.scheduled_voice_ids) == 32
    assert result.skipped_voice_limit_count == 1
    assert len(engine.create_calls) == 32
    assert len(engine.schedule_calls) == 32
    assert engine.stop_voice_calls == []
    assert engine.remove_voice_calls == []
    assert "stop_voice" not in {op for op, _ in engine.ops}
    assert "remove_voice" not in {op for op, _ in engine.ops}


# Keep legacy name as an alias so older checklists still resolve.
test_voice_limit_is_fail_soft_without_voice_stealing = (
    test_eager_schedule_pattern_once_create_budget_is_fail_soft_without_voice_stealing
)


def test_planning_is_pure_and_does_not_decode_or_touch_native_engine():
    module = _sequencer_or_fail()
    plan = _require_symbol(module, "plan_pattern_once")

    tempo_map = TempoMap(sample_rate=48_000, bpm=120)
    pattern = Pattern(
        pattern_id="pat_pure",
        length_quarter_notes=Fraction(4, 1),
        triggers=[Trigger(channel_id="ch_kick", position=Fraction(1, 2))],
    )
    channels = _channels(
        _channel("ch_kick", "Kick + Bass", "Kick", "synthetic/kick.wav")
    )
    engine = FakeNativeEngine()

    planned = plan(
        pattern=pattern,
        channels_by_id=channels,
        tempo_map=tempo_map,
        pattern_start_quarter=Fraction(0, 1),
        pattern_start_engine_frame=1_000,
    )
    assert planned
    assert engine.create_calls == []
    assert engine.schedule_calls == []
    assert engine.ops == []

    sig = inspect.signature(plan)
    assert "engine" not in sig.parameters
    assert "pcm_for_path" not in sig.parameters
    assert "decode" not in sig.parameters


def test_sequencer_slice_contains_no_screen2_qml_or_arrangement_surface():
    module = _sequencer_or_fail()
    source_path = Path(inspect.getsourcefile(module) or "")
    assert source_path.is_file()
    source = source_path.read_text(encoding="utf-8")

    for token in FORBIDDEN_SEQUENCER_SURFACE_TOKENS:
        assert token not in source, f"forbidden sequencer surface token: {token}"

    tree = ast.parse(source)
    defined = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    for forbidden in ("ChannelRack", "Screen2View", "TransportAwarePreview"):
        assert forbidden not in defined

    public = {name for name in dir(module) if not name.startswith("_")}
    for forbidden in ("play_arrangement", "run_screen2", "loop_pattern_forever"):
        assert forbidden not in public


def test_sequencer_contract_does_not_add_beatgrid_or_wall_clock_timing_authority():
    module = _sequencer_or_fail()
    ScheduledTrigger = _require_symbol(module, "ScheduledTrigger")
    plan = _require_symbol(module, "plan_pattern_once")

    field_names = {f.name for f in fields(ScheduledTrigger)}
    assert "position" in field_names
    assert "engine_frame" in field_names
    assert "start_ms" not in field_names
    assert "tick" not in field_names
    assert "ppq" not in field_names
    assert "beatgrid" not in {n.lower() for n in field_names}

    tempo_map = TempoMap(sample_rate=48_000, bpm=120)
    pattern = Pattern(
        pattern_id="pat_time_auth",
        length_quarter_notes=Fraction(4, 1),
        triggers=[Trigger(channel_id="ch_kick", position=Fraction(3, 4))],
    )
    channels = _channels(
        _channel("ch_kick", "Kick + Bass", "Kick", "synthetic/kick.wav")
    )
    planned = plan(
        pattern=pattern,
        channels_by_id=channels,
        tempo_map=tempo_map,
        pattern_start_quarter=Fraction(0, 1),
        pattern_start_engine_frame=0,
    )
    assert type(planned[0].position) is Fraction
    assert not hasattr(planned[0], "start_ms")
    assert not hasattr(planned[0], "beat_grid")


# --- #681 membership gate at plan_pattern_once boundary ----------------------


def test_plan_pattern_once_rejects_phantom_channel_id_fail_closed():
    """UNKNOWN CHANNEL != MISSING SAMPLE: phantom IDs must not soft-skip."""
    module = _sequencer_or_fail()
    plan = _require_symbol(module, "plan_pattern_once")

    tempo_map = TempoMap(sample_rate=48_000, bpm=120)
    pattern = Pattern(
        pattern_id="pat_phantom",
        length_quarter_notes=Fraction(4, 1),
        triggers=[Trigger(channel_id="ch_phantom", position=Fraction(0, 1))],
    )
    channels = _channels(
        _channel("ch_kick", "Kick + Bass", "Kick", "synthetic/kick.wav")
    )

    with pytest.raises(ValueError, match="Unknown channel_id"):
        plan(
            pattern=pattern,
            channels_by_id=channels,
            tempo_map=tempo_map,
            pattern_start_quarter=Fraction(0, 1),
            pattern_start_engine_frame=0,
        )


def test_plan_pattern_once_accepts_user_added_opaque_channel():
    module = _sequencer_or_fail()
    plan = _require_symbol(module, "plan_pattern_once")

    tempo_map = TempoMap(sample_rate=48_000, bpm=120)
    user = Channel(
        channel_id="ch_user_1",
        live_kit_group=None,
        live_kit_slot=None,
        sample_path="synthetic/user_01.wav",
    )
    pattern = Pattern(
        pattern_id="pat_user",
        length_quarter_notes=Fraction(4, 1),
        triggers=[Trigger(channel_id="ch_user_1", position=Fraction(1, 4))],
    )
    planned = plan(
        pattern=pattern,
        channels_by_id=_channels(user),
        tempo_map=tempo_map,
        pattern_start_quarter=Fraction(0, 1),
        pattern_start_engine_frame=0,
    )
    assert len(planned) == 1
    assert planned[0].channel_id == "ch_user_1"
    assert planned[0].sample_path == "synthetic/user_01.wav"


def test_plan_pattern_once_keeps_empty_sample_path_fail_soft_for_known_channel():
    """Existing channel with sample_path=None remains planable (missing source)."""
    module = _sequencer_or_fail()
    plan = _require_symbol(module, "plan_pattern_once")

    tempo_map = TempoMap(sample_rate=48_000, bpm=120)
    pattern = Pattern(
        pattern_id="pat_empty_known",
        length_quarter_notes=Fraction(4, 1),
        triggers=[Trigger(channel_id="ch_kick", position=Fraction(0, 1))],
    )
    planned = plan(
        pattern=pattern,
        channels_by_id=_channels(
            _channel("ch_kick", "Kick + Bass", "Kick", None)
        ),
        tempo_map=tempo_map,
        pattern_start_quarter=Fraction(0, 1),
        pattern_start_engine_frame=0,
    )
    assert planned[0].channel_id == "ch_kick"
    assert planned[0].sample_path is None


# --- #698 PatternPassPlayer voice lifecycle ---------------------------------


def _short_pcm() -> PcmBufferConfig:
    """Very short one-shot so temporal passes stay under concurrent capacity."""
    return _pcm(frames=2, channels=1)


def _drive_pattern_pass(
    player,
    *,
    engine: FakeNativeEngine,
    pcm_for_path,
    allocate_voice_id,
    end_frame: int,
    step: int = 1,
):
    max_total = 0
    frame = 0
    while frame <= end_frame:
        engine.advance_to(frame)
        result = player.tick(
            engine_frame=frame,
            engine=engine,
            pcm_for_path=pcm_for_path,
            allocate_voice_id=allocate_voice_id,
        )
        max_total = max(max_total, result.total_voice_count)
        if player.pending_count == 0 and player.live_voice_count == 0:
            break
        frame += step
    else:
        # Final reclaim sweep after last event durations.
        engine.advance_to(end_frame + 64)
        player.tick(
            engine_frame=end_frame + 64,
            engine=engine,
            pcm_for_path=pcm_for_path,
            allocate_voice_id=allocate_voice_id,
        )
        max_total = max(max_total, engine.get_snapshot().total_voice_count)
    return max_total


def test_pattern_pass_player_lookahead_frames_must_be_non_negative_int():
    module = _sequencer_or_fail()
    Player = _require_symbol(module, "PatternPassPlayer")
    with pytest.raises(ValueError, match="lookahead_frames"):
        Player((), lookahead_frames=-1)
    with pytest.raises(ValueError, match="lookahead_frames"):
        Player((), lookahead_frames=True)  # type: ignore[arg-type]


def test_pattern_pass_player_48_default_on_events_all_materialise_under_concurrent_32():
    """TOTAL EVENTS != CONCURRENCY: 3x16=48 with short PCM, peak registered <=32."""
    module = _sequencer_or_fail()
    plan = _require_symbol(module, "plan_pattern_once")
    Player = _require_symbol(module, "PatternPassPlayer")

    tempo_map = TempoMap(sample_rate=48_000, bpm=120)
    channel_specs = (
        ("ch_kick", "Kick + Bass", "Kick", "synthetic/kick.wav"),
        ("ch_main_drum", "Drums", "Main Drum", "synthetic/snare.wav"),
        ("ch_closed_hat", "Drums", "Closed Hat", "synthetic/hat.wav"),
    )
    channels = _channels(
        *[_channel(cid, group, slot, path) for cid, group, slot, path in channel_specs]
    )
    triggers = [
        Trigger(channel_id=cid, position=Fraction(step, 4))
        for cid, _g, _s, _p in channel_specs
        for step in range(16)
    ]
    pattern = Pattern(
        pattern_id="pat_48",
        length_quarter_notes=Fraction(4, 1),
        triggers=triggers,
    )
    planned = plan(
        pattern=pattern,
        channels_by_id=channels,
        tempo_map=tempo_map,
        pattern_start_quarter=Fraction(0, 1),
        pattern_start_engine_frame=0,
    )
    assert len(planned) == 48
    planned_frames = {t.engine_frame for t in planned}

    ids = iter(range(1, 10_000))
    engine = FakeNativeEngine()
    # Lookahead covers one 16th (6000 frames @ 120BPM/48k); injectable, not magic.
    player = Player(planned, lookahead_frames=6000)
    max_total = _drive_pattern_pass(
        player,
        engine=engine,
        pcm_for_path=lambda _path: _short_pcm(),
        allocate_voice_id=lambda: next(ids),
        end_frame=max(t.engine_frame for t in planned) + 16,
        step=100,
    )

    assert player.scheduled_count == 48
    assert player.skipped_voice_limit_count == 0
    assert player.pending_count == 0
    assert max_total <= SB_MAX_VOICES
    scheduled_frames = {frame for _vid, frame in engine.schedule_calls}
    assert scheduled_frames == planned_frames
    assert engine.get_snapshot().total_voice_count <= SB_MAX_VOICES


def test_pattern_pass_player_64_default_on_events_all_materialise_under_concurrent_32():
    module = _sequencer_or_fail()
    plan = _require_symbol(module, "plan_pattern_once")
    Player = _require_symbol(module, "PatternPassPlayer")

    tempo_map = TempoMap(sample_rate=48_000, bpm=120)
    channel_specs = (
        ("ch_kick", "Kick + Bass", "Kick", "synthetic/kick.wav"),
        ("ch_main_drum", "Drums", "Main Drum", "synthetic/snare.wav"),
        ("ch_closed_hat", "Drums", "Closed Hat", "synthetic/hat.wav"),
        ("ch_percussion", "Drums", "Percussion", "synthetic/perc.wav"),
    )
    channels = _channels(
        *[_channel(cid, group, slot, path) for cid, group, slot, path in channel_specs]
    )
    triggers = [
        Trigger(channel_id=cid, position=Fraction(step, 4))
        for cid, _g, _s, _p in channel_specs
        for step in range(16)
    ]
    pattern = Pattern(
        pattern_id="pat_64",
        length_quarter_notes=Fraction(4, 1),
        triggers=triggers,
    )
    planned = plan(
        pattern=pattern,
        channels_by_id=channels,
        tempo_map=tempo_map,
        pattern_start_quarter=Fraction(0, 1),
        pattern_start_engine_frame=0,
    )
    assert len(planned) == 64

    ids = iter(range(1, 10_000))
    engine = FakeNativeEngine()
    player = Player(planned, lookahead_frames=6000)
    max_total = _drive_pattern_pass(
        player,
        engine=engine,
        pcm_for_path=lambda _path: _short_pcm(),
        allocate_voice_id=lambda: next(ids),
        end_frame=max(t.engine_frame for t in planned) + 16,
        step=100,
    )

    assert player.scheduled_count == 64
    assert player.skipped_voice_limit_count == 0
    assert player.pending_count == 0
    assert max_total <= SB_MAX_VOICES
    assert len(engine.schedule_calls) == 64


def test_pattern_pass_player_more_than_32_same_frame_fail_soft_without_stealing():
    module = _sequencer_or_fail()
    plan = _require_symbol(module, "plan_pattern_once")
    Player = _require_symbol(module, "PatternPassPlayer")

    tempo_map = TempoMap(sample_rate=48_000, bpm=120)
    # 33 channels, one trigger each at the same musical position → same engine frame.
    channels_list = [
        Channel(
            channel_id=f"ch_user_{i}",
            live_kit_group=None,
            live_kit_slot=None,
            sample_path=f"synthetic/s{i}.wav",
        )
        for i in range(33)
    ]
    channels = _channels(*channels_list)
    triggers = [
        Trigger(channel_id=f"ch_user_{i}", position=Fraction(0, 1)) for i in range(33)
    ]
    pattern = Pattern(
        pattern_id="pat_simultaneous",
        length_quarter_notes=Fraction(4, 1),
        triggers=triggers,
    )
    planned = plan(
        pattern=pattern,
        channels_by_id=channels,
        tempo_map=tempo_map,
        pattern_start_quarter=Fraction(0, 1),
        pattern_start_engine_frame=0,
    )
    assert len({t.engine_frame for t in planned}) == 1

    ids = iter(range(1, 10_000))
    engine = FakeNativeEngine()
    player = Player(planned, lookahead_frames=0)
    engine.advance_to(0)
    result = player.tick(
        engine_frame=0,
        engine=engine,
        pcm_for_path=lambda _path: _short_pcm(),
        allocate_voice_id=lambda: next(ids),
    )
    assert result.scheduled_count == 32
    assert result.skipped_voice_limit_count == 1
    assert result.total_voice_count == 32
    assert engine.get_snapshot().total_voice_count == 32
    # No stealing: never stop/remove PLAYING voices to free capacity mid-tick.
    assert engine.stop_voice_calls == []


def test_pattern_pass_player_respects_foreign_voices_for_global_capacity():
    module = _sequencer_or_fail()
    Player = _require_symbol(module, "PatternPassPlayer")
    ScheduledTrigger = _require_symbol(module, "ScheduledTrigger")

    foreign = 10
    engine = FakeNativeEngine()
    for voice_id in range(1, foreign + 1):
        engine.seed_foreign_voice(voice_id)

    planned = tuple(
        ScheduledTrigger(
            channel_id="ch_kick",
            sample_path="synthetic/kick.wav",
            position=Fraction(0, 1),
            engine_frame=0,
        )
        for _ in range(30)
    )
    # 10 foreign + 30 attempted => only 22 can register (32-10).
    ids = iter(range(100, 10_000))
    player = Player(planned, lookahead_frames=0)
    engine.advance_to(0)
    result = player.tick(
        engine_frame=0,
        engine=engine,
        pcm_for_path=lambda _path: _short_pcm(),
        allocate_voice_id=lambda: next(ids),
    )
    assert result.scheduled_count == SB_MAX_VOICES - foreign
    assert result.skipped_voice_limit_count == 30 - (SB_MAX_VOICES - foreign)
    assert engine.get_snapshot().total_voice_count == SB_MAX_VOICES
    assert engine.get_snapshot().total_voice_count <= SB_MAX_VOICES


def test_pattern_pass_player_late_event_keeps_exact_engine_frame():
    module = _sequencer_or_fail()
    plan = _require_symbol(module, "plan_pattern_once")
    Player = _require_symbol(module, "PatternPassPlayer")

    tempo_map = TempoMap(sample_rate=48_000, bpm=120)
    triggers = [
        Trigger(channel_id="ch_kick", position=Fraction(i, 16)) for i in range(40)
    ]
    pattern = Pattern(
        pattern_id="pat_late",
        length_quarter_notes=Fraction(8, 1),
        triggers=triggers,
    )
    channels = _channels(
        _channel("ch_kick", "Kick + Bass", "Kick", "synthetic/kick.wav")
    )
    planned = plan(
        pattern=pattern,
        channels_by_id=channels,
        tempo_map=tempo_map,
        pattern_start_quarter=Fraction(0, 1),
        pattern_start_engine_frame=0,
    )
    target = planned[35]
    ids = iter(range(1, 10_000))
    engine = FakeNativeEngine()
    player = Player(planned, lookahead_frames=3000)
    _drive_pattern_pass(
        player,
        engine=engine,
        pcm_for_path=lambda _path: _short_pcm(),
        allocate_voice_id=lambda: next(ids),
        end_frame=max(t.engine_frame for t in planned) + 16,
        step=50,
    )
    assert (any(vid for vid, frame in engine.schedule_calls if frame == target.engine_frame))
    assert player.scheduled_count == 40
    assert player.skipped_voice_limit_count == 0
    matching = [frame for _vid, frame in engine.schedule_calls]
    assert matching.count(target.engine_frame) >= 1
    # Frame-exact: every planned frame appears unchanged in schedule requests.
    assert {frame for _vid, frame in engine.schedule_calls} == {
        t.engine_frame for t in planned
    }


def test_pattern_pass_player_stop_removes_owned_voices_without_leaks():
    module = _sequencer_or_fail()
    Player = _require_symbol(module, "PatternPassPlayer")
    ScheduledTrigger = _require_symbol(module, "ScheduledTrigger")

    planned = tuple(
        ScheduledTrigger(
            channel_id="ch_kick",
            sample_path="synthetic/kick.wav",
            position=Fraction(i, 4),
            engine_frame=i * 6000,
        )
        for i in range(4)
    )
    engine = FakeNativeEngine()
    engine.seed_foreign_voice(999)
    ids = iter(range(1, 100))
    player = Player(planned, lookahead_frames=20_000)
    engine.advance_to(0)
    player.tick(
        engine_frame=0,
        engine=engine,
        pcm_for_path=lambda _path: _short_pcm(),
        allocate_voice_id=lambda: next(ids),
    )
    assert player.live_voice_count > 0
    owned_before = set(player._owned_live)
    player.stop(engine)
    assert player.live_voice_count == 0
    assert player.pending_count == 0
    for voice_id in owned_before:
        assert voice_id in engine.remove_voice_calls
        assert voice_id not in engine._voices
    # Foreign voice remains.
    assert 999 in engine._voices
    assert engine.get_snapshot().total_voice_count == 1


def test_pattern_pass_player_missing_sample_fail_soft():
    module = _sequencer_or_fail()
    Player = _require_symbol(module, "PatternPassPlayer")
    ScheduledTrigger = _require_symbol(module, "ScheduledTrigger")

    planned = (
        ScheduledTrigger(
            channel_id="ch_kick",
            sample_path=None,
            position=Fraction(0, 1),
            engine_frame=0,
        ),
        ScheduledTrigger(
            channel_id="ch_snare",
            sample_path="synthetic/snare.wav",
            position=Fraction(0, 1),
            engine_frame=0,
        ),
    )
    engine = FakeNativeEngine()
    ids = iter(range(1, 10))
    player = Player(planned, lookahead_frames=0)
    result = player.tick(
        engine_frame=0,
        engine=engine,
        pcm_for_path=lambda path: _short_pcm() if path.endswith("snare.wav") else None,
        allocate_voice_id=lambda: next(ids),
    )
    assert result.skipped_missing_source_count == 1
    assert result.scheduled_count == 1

def test_pattern_pass_player_does_not_reclaim_unacked_initial_idle():
    """P1: IDLE before schedule-ack must not be treated as EOF reclaimable."""
    module = _sequencer_or_fail()
    Player = _require_symbol(module, "PatternPassPlayer")
    ScheduledTrigger = _require_symbol(module, "ScheduledTrigger")

    planned = (
        ScheduledTrigger(
            channel_id="ch_kick",
            sample_path="synthetic/kick.wav",
            position=Fraction(0, 1),
            engine_frame=4800,
        ),
    )
    engine = FakeNativeEngine()
    engine.defer_schedule_apply = True
    ids = iter(range(1, 10))
    player = Player(planned, lookahead_frames=4800)
    player.tick(
        engine_frame=0,
        engine=engine,
        pcm_for_path=lambda _path: _short_pcm(),
        allocate_voice_id=lambda: next(ids),
    )
    assert engine.get_snapshot().total_voice_count == 1
    assert engine.get_snapshot().voice_states[0] == SB_VOICE_IDLE
    # Second tick at same clock before audio callback — must keep the voice.
    player.tick(
        engine_frame=0,
        engine=engine,
        pcm_for_path=lambda _path: _short_pcm(),
        allocate_voice_id=lambda: next(ids),
    )
    assert engine.remove_voice_calls == []
    assert engine.get_snapshot().total_voice_count == 1
    assert player.live_voice_count == 1


def test_pattern_pass_player_rejects_max_voices_above_sb_max():
    module = _sequencer_or_fail()
    Player = _require_symbol(module, "PatternPassPlayer")
    with pytest.raises(ValueError, match="SB_MAX_VOICES"):
        Player((), lookahead_frames=0, max_voices=SB_MAX_VOICES + 1)
