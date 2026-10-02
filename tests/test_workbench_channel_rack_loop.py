"""TEST_GATE / TEST_FREEZE — Screen-2 Channel Rack loop playback (#810).

Canonical authority:
- docs/PATTERN_CORE_CONTRACT.md
- docs/SEQUENCER_PLAYBACK_CONTRACT.md
- docs/SESSION_OWNERSHIP_CONTRACT.md
- live issue #810

Frozen policy:
- PatternPassPlayer remains a finite one-pass primitive
- ChannelRackController owns multi-pass loop until Stop
- Musical quarter positions + TempoMap are timing authority
- No QML loop state; Play = loop, Stop/Esc = hard stop
- Current pass = frozen plan; next pass = live ChannelRackState
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.channel_rack import ChannelRackState
from src.native_audio import (
    SB_MAX_VOICES,
    SB_VOICE_IDLE,
    SB_VOICE_PLAYING,
    SB_VOICE_SCHEDULED,
    PcmBufferConfig,
    VoiceConfig,
)
from src.pattern_core import Channel, Pattern, Trigger, USER_CHANNEL_ID_PREFIX
from src.sequencer_pcm import SequencerPcmProvider
from src.session_grid import SessionTransport, TempoMap
from src.workbench_controller import WorkbenchRow
from src.workbench_live_kit import LiveKitState


PCM_FRAMES = 8
SAMPLE_RATE = 48_000
BPM = 120


def _controller_module():
    return importlib.import_module("src.workbench_channel_rack")


def _require(module, name: str):
    value = getattr(module, name, None)
    if value is None:
        pytest.fail(f"MISSING_PRODUCTION_SURFACE: {module.__name__}.{name}")
    return value


def _row(name: str, *, path: str | None = None) -> WorkbenchRow:
    return WorkbenchRow(
        display_name=name,
        relative_path=name,
        path=path or f"synthetic/{name}",
        bpm=132.0,
        key="Am",
        key_conf=0.9,
        loudness=-12.0,
        brightness=3000.0,
        sample_class="one_shot",
        pred_type="Kick",
        status="ok",
        details={"duration_sec": "0.2"},
    )


def _kit_with_kick(path: str = "synthetic/kick.wav") -> LiveKitState:
    kit = LiveKitState()
    kit.assign("Kick + Bass", "Kick", _row("kick.wav", path=path))
    return kit


def _pcm_provider() -> SequencerPcmProvider:
    def decode_fn(path, *, sample_rate, start_ms=0):
        del path, sample_rate, start_ms
        return np.linspace(-0.2, 0.2, PCM_FRAMES, dtype=np.float32), 1

    return SequencerPcmProvider(sample_rate=SAMPLE_RATE, decode_fn=decode_fn)


class FakeNativeEngine:
    """Minimal engine double with IDLE reclaim (mirrors sequencer contract fake)."""

    def __init__(self) -> None:
        self.create_calls: list[VoiceConfig] = []
        self.schedule_calls: list[tuple[int, int]] = []
        self.stop_voice_calls: list[int] = []
        self.remove_voice_calls: list[int] = []
        self.engine_frame = 0
        self._voices: dict[int, dict[str, Any]] = {}

    def seed_foreign_voice(self, voice_id: int, *, pcm_frames: int = 8) -> None:
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
                meta["state"] = SB_VOICE_SCHEDULED

    def get_snapshot(self) -> Any:
        ids = list(self._voices.keys())
        states = [int(self._voices[vid]["state"]) for vid in ids]
        pad = SB_MAX_VOICES - len(ids)
        if pad > 0:
            ids = ids + [0] * pad
            states = states + [SB_VOICE_IDLE] * pad

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

    def snapshot(self) -> Any:
        return self.get_snapshot()

    def create_voice(self, config: VoiceConfig) -> int:
        self.create_calls.append(config)
        voice_id = int(config.id)
        pcm_frames = PCM_FRAMES
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
        meta = self._voices[voice_id]
        meta["start_frame"] = engine_frame
        if self.engine_frame >= engine_frame + int(meta["pcm_frames"]):
            meta["state"] = SB_VOICE_IDLE
        elif self.engine_frame >= engine_frame:
            meta["state"] = SB_VOICE_PLAYING
        else:
            meta["state"] = SB_VOICE_SCHEDULED

    def stop_voice(self, voice_id: int) -> None:
        self.stop_voice_calls.append(voice_id)
        if voice_id in self._voices:
            self._voices[voice_id]["state"] = SB_VOICE_IDLE

    def remove_voice(self, voice_id: int) -> None:
        self.remove_voice_calls.append(voice_id)
        self._voices.pop(voice_id, None)


class LoopTransport:
    """Transport facade exposing engine/session frames for ChannelRackController."""

    def __init__(
        self,
        engine: FakeNativeEngine,
        *,
        sample_rate: int = SAMPLE_RATE,
        bpm: float = BPM,
        core: SessionTransport | None = None,
    ) -> None:
        self._engine = engine
        self._core = core or SessionTransport(sample_rate=sample_rate, bpm=bpm)
        self.sample_rate = self._core.sample_rate
        self.start = MagicMock(side_effect=self._on_start)
        self.stop = MagicMock(side_effect=self._on_stop)
        self.poll = MagicMock()

    def _on_start(self) -> None:
        self._core.play()

    def _on_stop(self) -> None:
        self._core.stop()

    @property
    def tempo_map(self) -> TempoMap:
        return self._core.tempo_map

    @property
    def engine_frame(self) -> int:
        return self._core.engine_frame

    @engine_frame.setter
    def engine_frame(self, value: int) -> None:
        self._core.engine_frame = int(value)

    @property
    def session_frame(self) -> int:
        return self._core.session_frame

    @session_frame.setter
    def session_frame(self, value: int) -> None:
        self._core.session_frame = int(value)

    def ensure_engine_running(self) -> bool:
        return True

    def get_native_engine(self) -> FakeNativeEngine:
        return self._engine

    def is_native_available(self) -> bool:
        return True

    def set_tempo(self, bpm: float) -> int:
        return self._core.set_tempo(bpm)

    def advance(self, frames: int) -> None:
        if not self._core.playing:
            self._core.play()
        self._core.advance(int(frames))
        self._engine.advance_to(self._core.engine_frame)

    def seek_session(self, frame: int) -> None:
        self._core.seek(int(frame))


def _minimal_kick_state(path: str = "synthetic/kick.wav") -> ChannelRackState:
    channel = Channel(
        channel_id="ch_kick",
        live_kit_group="Kick + Bass",
        live_kit_slot="Kick",
        sample_path=path,
    )
    return ChannelRackState(
        channels=(channel,),
        pattern=Pattern(
            pattern_id="screen2-main",
            length_quarter_notes=Fraction(4, 1),
            triggers=(Trigger(channel_id="ch_kick", position=Fraction(0, 1)),),
        ),
        step_count=16,
    )


def _make_controller(*, engine=None, transport=None, state=None):
    module = _controller_module()
    Controller = _require(module, "ChannelRackController")
    engine = engine or FakeNativeEngine()
    transport = transport or LoopTransport(engine)
    controller = Controller(
        live_kit=_kit_with_kick(),
        transport=transport,
        pcm_provider=_pcm_provider(),
        lookahead_frames=4800,
    )
    controller.enter_screen2()
    if state is not None:
        controller._state = state
    else:
        controller._state = _minimal_kick_state()
    return module, controller, engine, transport


def _drain_until_pass_boundary(controller, transport, engine, *, max_ticks: int = 64):
    """Advance clock far enough that the current pass finishes voices and loops."""
    length = controller.state.pattern.length_quarter_notes
    module = _controller_module()
    helper = _require(module, "pattern_pass_start_frames")
    start_q, start_e = helper(
        transport.tempo_map,
        anchor_quarter=controller._loop_anchor_quarter,
        anchor_engine_frame=controller._loop_anchor_engine_frame,
        pass_index=controller._loop_pass_index,
        length_quarter_notes=length,
    )
    del start_q
    # Jump near end of current voices, then tick reclaim + loop seam.
    transport.advance(max(0, start_e + PCM_FRAMES + 1 - transport.engine_frame))
    engine.advance_to(transport.engine_frame)
    for _ in range(max_ticks):
        before = controller._loop_pass_index
        tick = controller.tick_playback()
        if tick is None:
            return None
        if controller._loop_pass_index > before:
            return tick
        # Nudge clock if still waiting on reclaim.
        transport.advance(PCM_FRAMES)
        engine.advance_to(transport.engine_frame)
    pytest.fail("expected loop pass boundary within tick budget")


def test_pattern_pass_start_frames_uses_tempomap_not_constant_duration():
    module = _controller_module()
    helper = _require(module, "pattern_pass_start_frames")
    tempo = TempoMap(sample_rate=SAMPLE_RATE, bpm=120)
    anchor_q = Fraction(0, 1)
    anchor_e = 10_000
    length = Fraction(4, 1)

    q0, e0 = helper(
        tempo,
        anchor_quarter=anchor_q,
        anchor_engine_frame=anchor_e,
        pass_index=0,
        length_quarter_notes=length,
    )
    q1, e1 = helper(
        tempo,
        anchor_quarter=anchor_q,
        anchor_engine_frame=anchor_e,
        pass_index=1,
        length_quarter_notes=length,
    )
    q2, e2 = helper(
        tempo,
        anchor_quarter=anchor_q,
        anchor_engine_frame=anchor_e,
        pass_index=2,
        length_quarter_notes=length,
    )

    assert q0 == Fraction(0, 1)
    assert e0 == anchor_e
    assert q1 == length
    assert q2 == 2 * length
    expected_e1 = anchor_e + (
        tempo.quarter_note_to_frame(length) - tempo.quarter_note_to_frame(anchor_q)
    )
    expected_e2 = anchor_e + (
        tempo.quarter_note_to_frame(2 * length) - tempo.quarter_note_to_frame(anchor_q)
    )
    assert e1 == expected_e1
    assert e2 == expected_e2
    # Constant-frame assumption would equal e1-e0 twice; keep algebraic identity.
    assert e2 - e1 == e1 - e0

    # After a tempo change at a later quarter, pass spans diverge from constant frames.
    tempo.add_tempo_change_at_quarter(effective_quarter=length, bpm=240)
    _, e1_fast = helper(
        tempo,
        anchor_quarter=anchor_q,
        anchor_engine_frame=anchor_e,
        pass_index=1,
        length_quarter_notes=length,
    )
    _, e2_fast = helper(
        tempo,
        anchor_quarter=anchor_q,
        anchor_engine_frame=anchor_e,
        pass_index=2,
        length_quarter_notes=length,
    )
    assert e1_fast == e1  # boundary at length still same segment start
    assert (e2_fast - e1_fast) != (e1 - e0)


def test_play_anchor_uses_session_musical_position_not_forced_zero():
    module = _controller_module()
    helper = _require(module, "pattern_pass_start_frames")
    engine = FakeNativeEngine()
    transport = LoopTransport(engine)
    # Session already advanced / seeked; engine clock is independent.
    transport.seek_session(transport.tempo_map.quarter_note_to_frame(Fraction(8, 1)))
    transport.engine_frame = 50_000

    _, controller, _, _ = _make_controller(engine=engine, transport=transport)
    handle = controller.play()
    assert handle is not None
    assert controller.is_playing is True

    anchor_q = transport.tempo_map.frame_to_quarter_note(transport.session_frame)
    assert controller._loop_anchor_quarter == anchor_q
    assert controller._loop_anchor_engine_frame == 50_000
    assert anchor_q != Fraction(0, 1)

    q1, e1 = helper(
        transport.tempo_map,
        anchor_quarter=controller._loop_anchor_quarter,
        anchor_engine_frame=controller._loop_anchor_engine_frame,
        pass_index=1,
        length_quarter_notes=Fraction(4, 1),
    )
    assert q1 == anchor_q + Fraction(4, 1)
    assert e1 == 50_000 + (
        transport.tempo_map.quarter_note_to_frame(q1)
        - transport.tempo_map.quarter_note_to_frame(anchor_q)
    )


def test_two_pass_minimum_keeps_playing_and_schedules_second_pass():
    _, controller, engine, transport = _make_controller()
    controller.play()
    assert controller.is_playing is True
    assert controller._loop_pass_index == 0
    first_schedules = list(engine.schedule_calls)
    assert first_schedules

    _drain_until_pass_boundary(controller, transport, engine)
    assert controller.is_playing is True
    assert controller._loop_pass_index == 1
    assert len(engine.schedule_calls) > len(first_schedules)

    module = _controller_module()
    helper = _require(module, "pattern_pass_start_frames")
    _, expected_e1 = helper(
        transport.tempo_map,
        anchor_quarter=controller._loop_anchor_quarter,
        anchor_engine_frame=controller._loop_anchor_engine_frame,
        pass_index=1,
        length_quarter_notes=Fraction(4, 1),
    )
    second_frames = [frame for _vid, frame in engine.schedule_calls[len(first_schedules) :]]
    assert expected_e1 in second_frames


def test_multi_pass_musical_starts_have_no_cumulative_frame_drift():
    _, controller, engine, transport = _make_controller()
    controller.play()
    module = _controller_module()
    helper = _require(module, "pattern_pass_start_frames")

    observed_pass_starts: list[int] = []
    for expected_index in range(1, 4):
        before = len(engine.schedule_calls)
        _drain_until_pass_boundary(controller, transport, engine)
        assert controller._loop_pass_index == expected_index
        assert controller.is_playing is True
        _, expected_e = helper(
            transport.tempo_map,
            anchor_quarter=controller._loop_anchor_quarter,
            anchor_engine_frame=controller._loop_anchor_engine_frame,
            pass_index=expected_index,
            length_quarter_notes=Fraction(4, 1),
        )
        new_frames = [f for _v, f in engine.schedule_calls[before:]]
        assert expected_e in new_frames
        observed_pass_starts.append(expected_e)

    # Algebraic TempoMap positions — not previous_start + constant.
    q_anchor = controller._loop_anchor_quarter
    e_anchor = controller._loop_anchor_engine_frame
    for index, observed in enumerate(observed_pass_starts, start=1):
        _, expected = helper(
            transport.tempo_map,
            anchor_quarter=q_anchor,
            anchor_engine_frame=e_anchor,
            pass_index=index,
            length_quarter_notes=Fraction(4, 1),
        )
        assert observed == expected


def test_stop_prevents_further_passes_and_tick_resurrection():
    _, controller, engine, transport = _make_controller()
    controller.play()
    _drain_until_pass_boundary(controller, transport, engine)
    assert controller._loop_pass_index == 1
    assert controller.is_playing is True

    schedules_before_stop = len(engine.schedule_calls)
    controller.stop()
    assert controller.is_playing is False
    assert getattr(controller, "_loop_active", False) is False

    transport.advance(200_000)
    engine.advance_to(transport.engine_frame)
    for _ in range(8):
        assert controller.tick_playback() is None
    assert len(engine.schedule_calls) == schedules_before_stop
    assert controller.is_playing is False


def test_leave_screen2_stops_loop_like_esc_return():
    _, controller, engine, transport = _make_controller()
    controller.play()
    _drain_until_pass_boundary(controller, transport, engine)
    assert controller.is_playing is True

    controller.leave_screen2()
    assert controller.active_screen == "screen1"
    assert controller.is_playing is False
    assert getattr(controller, "_loop_active", False) is False

    transport.advance(100_000)
    engine.advance_to(transport.engine_frame)
    assert controller.tick_playback() is None


def test_tempo_change_between_passes_uses_current_tempomap():
    engine = FakeNativeEngine()
    transport = LoopTransport(engine)
    _, controller, engine, transport = _make_controller(engine=engine, transport=transport)
    controller.play()
    assert controller._loop_pass_index == 0

    # Finish pass 0 voices, but capture expected pass-1 anchor BEFORE tempo change
    # would incorrectly use a constant frame span from pass 0.
    module = _controller_module()
    helper = _require(module, "pattern_pass_start_frames")
    _q1_before, e1_before = helper(
        transport.tempo_map,
        anchor_quarter=controller._loop_anchor_quarter,
        anchor_engine_frame=controller._loop_anchor_engine_frame,
        pass_index=1,
        length_quarter_notes=Fraction(4, 1),
    )

    # Advance into the first pass so transport is playing, then change tempo.
    transport.advance(PCM_FRAMES + 1)
    engine.advance_to(transport.engine_frame)
    transport.set_tempo(240)

    # Pass 1 boundary musical quarter is still anchor+length; frames come from new map.
    _q1_after, e1_after = helper(
        transport.tempo_map,
        anchor_quarter=controller._loop_anchor_quarter,
        anchor_engine_frame=controller._loop_anchor_engine_frame,
        pass_index=1,
        length_quarter_notes=Fraction(4, 1),
    )
    # With change at next bar, pass-1 start (4Q) may still match; pass-2 must differ
    # from constant-frame extrapolation once the new segment applies.
    _q2, e2 = helper(
        transport.tempo_map,
        anchor_quarter=controller._loop_anchor_quarter,
        anchor_engine_frame=controller._loop_anchor_engine_frame,
        pass_index=2,
        length_quarter_notes=Fraction(4, 1),
    )
    constant_e2 = e1_after + (e1_before - controller._loop_anchor_engine_frame)
    assert e2 != constant_e2

    before = len(engine.schedule_calls)
    _drain_until_pass_boundary(controller, transport, engine)
    assert controller._loop_pass_index == 1
    new_frames = [f for _v, f in engine.schedule_calls[before:]]
    assert e1_after in new_frames

    before2 = len(engine.schedule_calls)
    _drain_until_pass_boundary(controller, transport, engine)
    assert controller._loop_pass_index == 2
    new_frames2 = [f for _v, f in engine.schedule_calls[before2:]]
    assert e2 in new_frames2


def test_pattern_edit_between_passes_applies_on_next_pass_only():
    _, controller, engine, transport = _make_controller()
    controller.play()
    first_count = len(engine.schedule_calls)
    assert first_count >= 1

    # Disable the only step while pass 0 is active — current plan stays frozen.
    controller.toggle_step("ch_kick", 0)
    assert Trigger(channel_id="ch_kick", position=Fraction(0, 1)) not in (
        controller.state.pattern.triggers
    )

    # Re-enable a different step so pass 1 has something playable.
    controller.toggle_step("ch_kick", 4)  # position 1.0 quarter
    assert Trigger(channel_id="ch_kick", position=Fraction(1, 1)) in (
        controller.state.pattern.triggers
    )

    before = len(engine.schedule_calls)
    _drain_until_pass_boundary(controller, transport, engine)
    assert controller._loop_pass_index == 1
    assert controller.is_playing is True

    module = _controller_module()
    helper = _require(module, "pattern_pass_start_frames")
    start_q, start_e = helper(
        transport.tempo_map,
        anchor_quarter=controller._loop_anchor_quarter,
        anchor_engine_frame=controller._loop_anchor_engine_frame,
        pass_index=1,
        length_quarter_notes=Fraction(4, 1),
    )
    expected_event_e = start_e + (
        transport.tempo_map.quarter_note_to_frame(start_q + Fraction(1, 1))
        - transport.tempo_map.quarter_note_to_frame(start_q)
    )
    # Pass 1 may hold future events in pending until the engine reaches them.
    while transport.engine_frame < expected_event_e + PCM_FRAMES:
        transport.advance(max(1, min(4800, expected_event_e + PCM_FRAMES - transport.engine_frame)))
        engine.advance_to(transport.engine_frame)
        controller.tick_playback()
        if any(f == expected_event_e for _v, f in engine.schedule_calls[before:]):
            break
    new_frames = [f for _v, f in engine.schedule_calls[before:]]
    assert expected_event_e in new_frames
    # Pass 0 did not retroactively gain the new step.
    assert all(f != expected_event_e for _v, f in engine.schedule_calls[:before])


def test_voice_lifecycle_across_multiple_passes_no_leak_no_foreign_steal():
    engine = FakeNativeEngine()
    engine.seed_foreign_voice(42, pcm_frames=10_000)
    _, controller, engine, transport = _make_controller(engine=engine)
    controller.play()

    for expected in range(1, 4):
        _drain_until_pass_boundary(controller, transport, engine)
        assert controller._loop_pass_index == expected
        snap = engine.get_snapshot()
        assert snap.total_voice_count <= SB_MAX_VOICES
        assert 42 in [vid for vid in snap.voice_ids if vid != 0]
        # Foreign voice never stopped/removed by rack player.
        assert 42 not in engine.stop_voice_calls
        assert 42 not in engine.remove_voice_calls

    controller.stop()
    assert 42 not in engine.remove_voice_calls
    owned_live = [
        vid
        for vid, meta in engine._voices.items()
        if not meta.get("foreign") and meta["state"] != SB_VOICE_IDLE
    ]
    assert owned_live == []


def test_empty_pass_does_not_busy_loop_playing_true():
    state = ChannelRackState(
        channels=(
            Channel(
                channel_id="ch_kick",
                live_kit_group="Kick + Bass",
                live_kit_slot="Kick",
                sample_path=None,
            ),
        ),
        pattern=Pattern(
            pattern_id="screen2-main",
            length_quarter_notes=Fraction(4, 1),
            triggers=(Trigger(channel_id="ch_kick", position=Fraction(0, 1)),),
        ),
        step_count=16,
    )
    _, controller, engine, transport = _make_controller(state=state)
    handle = controller.play()
    assert handle is not None
    assert controller.is_playing is False
    assert getattr(controller, "_loop_active", False) is False

    transport.advance(200_000)
    for _ in range(8):
        assert controller.tick_playback() is None
    assert engine.schedule_calls == []


def test_later_empty_pass_fails_closed_without_busy_loop():
    """If a later pass cannot schedule, loop stops (no endless empty generations)."""
    module = _controller_module()
    _, controller, engine, transport = _make_controller()
    controller.play()
    assert controller.is_playing is True

    # After pass 0, wipe playable content so pass 1 is empty.
    def _drain_once():
        _drain_until_pass_boundary(controller, transport, engine)

    # Intercept: finish pass 0, then clear sample before replan by toggling path off.
    # Make sample path missing before boundary by mutating state channels.
    transport.advance(PCM_FRAMES + 1)
    engine.advance_to(transport.engine_frame)
    # Force next pass empty: replace state with no sample path before loop seam.
    empty = ChannelRackState(
        channels=(
            Channel(
                channel_id="ch_kick",
                live_kit_group="Kick + Bass",
                live_kit_slot="Kick",
                sample_path=None,
            ),
        ),
        pattern=Pattern(
            pattern_id="screen2-main",
            length_quarter_notes=Fraction(4, 1),
            triggers=(Trigger(channel_id="ch_kick", position=Fraction(0, 1)),),
        ),
        step_count=16,
    )
    # Tick until pass attempts to advance.
    for _ in range(32):
        controller._state = empty
        tick = controller.tick_playback()
        if tick is not None and not controller.is_playing:
            break
        transport.advance(PCM_FRAMES)
        engine.advance_to(transport.engine_frame)
    else:
        # If pass 0 not done yet, force more advance.
        transport.advance(100_000)
        engine.advance_to(transport.engine_frame)
        controller._state = empty
        controller.tick_playback()

    assert controller.is_playing is False
    assert getattr(controller, "_loop_active", False) is False
    for _ in range(5):
        assert controller.tick_playback() is None


def test_user_channel_loops_repeated_schedule_events(tmp_path: Path):
    from tests.audio_fixtures import write_sine_wav

    wav = write_sine_wav(
        tmp_path / "user.wav",
        duration_sec=0.05,
        frequency_hz=440.0,
        sr=SAMPLE_RATE,
    )
    module = _controller_module()
    Controller = _require(module, "ChannelRackController")
    engine = FakeNativeEngine()
    transport = LoopTransport(engine)
    # Synthetic short PCM keeps multi-pass drains deterministic; path is still #808 assign.
    controller = Controller(
        live_kit=LiveKitState(),
        transport=transport,
        pcm_provider=_pcm_provider(),
        lookahead_frames=4800,
    )
    controller.enter_screen2()
    controller.add_user_channel()
    user = next(
        ch
        for ch in controller.state.channels
        if ch.channel_id.startswith(USER_CHANNEL_ID_PREFIX)
    )
    controller.assign_user_channel_sample(user.channel_id, str(wav))
    # Keep a single step for deterministic multi-pass schedules.
    for step in range(16):
        if step == 0:
            continue
        if Trigger(channel_id=user.channel_id, position=Fraction(step, 4)) in (
            controller.state.pattern.triggers
        ):
            controller.toggle_step(user.channel_id, step)

    controller.play()
    assert controller.is_playing is True
    first = len(engine.schedule_calls)
    assert first >= 1
    _drain_until_pass_boundary(controller, transport, engine)
    assert controller._loop_pass_index == 1
    assert len(engine.schedule_calls) > first
    _drain_until_pass_boundary(controller, transport, engine)
    assert controller._loop_pass_index == 2
    assert len(engine.schedule_calls) > first + 1
    assert str(wav) == controller.state.channels[
        next(
            i
            for i, ch in enumerate(controller.state.channels)
            if ch.channel_id == user.channel_id
        )
    ].sample_path


def test_play_prefers_transport_play_for_session_clock_coupling():
    """Production adapter exposes play(), not start — session must advance while looping."""
    module = _controller_module()
    Controller = _require(module, "ChannelRackController")
    engine = FakeNativeEngine()
    core = SessionTransport(sample_rate=SAMPLE_RATE, bpm=BPM)

    class PlayOnlyTransport:
        def __init__(self) -> None:
            self._core = core
            self._engine = engine
            self.sample_rate = SAMPLE_RATE
            self.play_calls = 0

        @property
        def tempo_map(self):
            return self._core.tempo_map

        @property
        def engine_frame(self) -> int:
            return self._core.engine_frame

        @property
        def session_frame(self) -> int:
            return self._core.session_frame

        def play(self) -> None:
            self.play_calls += 1
            self._core.play()

        def ensure_engine_running(self) -> bool:
            return True

        def get_native_engine(self):
            return self._engine

        def advance(self, frames: int) -> None:
            self._core.advance(int(frames))
            self._engine.advance_to(self._core.engine_frame)

    transport = PlayOnlyTransport()
    controller = Controller(
        live_kit=_kit_with_kick(),
        transport=transport,
        pcm_provider=_pcm_provider(),
        lookahead_frames=4800,
    )
    controller.enter_screen2()
    controller._state = _minimal_kick_state()
    controller.play()
    assert transport.play_calls == 1
    assert controller.is_playing is True
    assert core.playing is True
    session_before = transport.session_frame
    transport.advance(PCM_FRAMES + 4)
    assert transport.session_frame > session_before
    # Tempo-while-playing must use next-bar path (requires playing session clock).
    change_frame = transport._core.set_tempo(240)
    assert change_frame > transport.session_frame or change_frame >= 0
    _drain_until_pass_boundary(controller, transport, engine)
    assert controller._loop_pass_index == 1
    assert controller.is_playing is True


def test_audio_focus_claim_still_runs_on_loop_play():
    module = _controller_module()
    Controller = _require(module, "ChannelRackController")
    claims: list[str] = []
    engine = FakeNativeEngine()
    transport = LoopTransport(engine)
    controller = Controller(
        live_kit=_kit_with_kick(),
        transport=transport,
        pcm_provider=_pcm_provider(),
        on_claim_audio_focus=lambda: claims.append("claim"),
    )
    controller.enter_screen2()
    controller._state = _minimal_kick_state()
    assert "claim" in claims
    claims.clear()
    controller.play()
    assert claims == ["claim"]
    assert controller.is_playing is True


def test_qml_play_stop_space_remain_intent_only_no_loop_flag():
    qml = importlib.import_module("src.workbench_qml")
    source = qml.QML_SOURCE
    assert "channelRack.play()" in source
    assert "channelRack.stop()" in source
    assert "loopEnabled" not in source
    assert "loop_active" not in source
    assert "loopPattern" not in source


def test_one_pass_primitive_and_forbidden_loop_api_remain():
    seq = importlib.import_module("src.sequencer_playback")
    assert not hasattr(seq, "loop_pattern_forever")
    source = Path(seq.__file__).read_text(encoding="utf-8")
    assert "one finite pattern pass" in source or "ONE_PATTERN_PASS" in source or (
        "finite pattern pass" in source
    )
    rack = importlib.import_module("src.channel_rack")
    assert hasattr(rack, "play_channel_rack_once")
    assert not hasattr(rack, "loop_pattern_forever")


# ---------------------------------------------------------------------------
# #821 — Deterministic Channel Rack loop soak / voice reclaim gate
# ---------------------------------------------------------------------------
#
# N=64 generations: long enough to catch monotonic voice growth that the
# short 2–4 pass lifecycle tests miss, short enough for CI with 8-frame
# synthetic PCM + FakeNativeEngine (no WASAPI / wall-clock sleeps).
SOAK_GENERATIONS = 64
# Single-step pattern + reclaim should keep owned registered voices tiny;
# bound far below SB_MAX_VOICES so growth regressions trip early.
SOAK_OWNED_VOICE_BOUND = 4


def _owned_registered_voice_count(engine: FakeNativeEngine) -> int:
    return sum(1 for meta in engine._voices.values() if not meta.get("foreign"))


def _foreign_voice_still_registered(engine: FakeNativeEngine, voice_id: int) -> bool:
    meta = engine._voices.get(voice_id)
    return meta is not None and bool(meta.get("foreign"))


def _record_soak_voice_snapshot(
    engine: FakeNativeEngine,
    *,
    foreign_id: int,
    owned_counts: list[int],
    total_counts: list[int],
) -> None:
    snap = engine.get_snapshot()
    owned = _owned_registered_voice_count(engine)
    owned_counts.append(owned)
    total_counts.append(int(snap.total_voice_count))
    assert snap.total_voice_count <= SB_MAX_VOICES
    assert owned <= SOAK_OWNED_VOICE_BOUND
    assert _foreign_voice_still_registered(engine, foreign_id)
    assert foreign_id not in engine.stop_voice_calls
    assert foreign_id not in engine.remove_voice_calls


def _path_pcm_seed(path: str) -> float:
    return 0.05 + (abs(hash(str(path))) % 50) / 1000.0


def _path_distinct_pcm_provider(decode_paths: list[str]) -> SequencerPcmProvider:
    """Synthetic PCM keyed by path so sample-replace decode is observable."""

    def decode_fn(path, *, sample_rate, start_ms=0):
        del sample_rate, start_ms
        decode_paths.append(str(path))
        seed = _path_pcm_seed(str(path))
        return np.full(PCM_FRAMES, seed, dtype=np.float32), 1

    return SequencerPcmProvider(sample_rate=SAMPLE_RATE, decode_fn=decode_fn)


def _create_call_matches_path_seed(config: VoiceConfig, path: str) -> bool:
    if config.pcm_buffer is None:
        return False
    samples = config.pcm_buffer.samples
    if samples.size == 0:
        return False
    return abs(float(samples.flat[0]) - _path_pcm_seed(path)) < 1e-6


def _pass_event_engine_frame(
    transport,
    controller,
    *,
    pass_index: int,
    trigger_quarter: Fraction,
) -> int:
    module = _controller_module()
    helper = _require(module, "pattern_pass_start_frames")
    start_q, start_e = helper(
        transport.tempo_map,
        anchor_quarter=controller._loop_anchor_quarter,
        anchor_engine_frame=controller._loop_anchor_engine_frame,
        pass_index=pass_index,
        length_quarter_notes=controller.state.pattern.length_quarter_notes,
    )
    return int(
        start_e
        + (
            transport.tempo_map.quarter_note_to_frame(start_q + trigger_quarter)
            - transport.tempo_map.quarter_note_to_frame(start_q)
        )
    )


def _materialize_until_frame_scheduled(
    controller,
    transport,
    engine,
    *,
    target_frame: int,
    schedule_from: int,
    max_steps: int = 64,
) -> None:
    """Advance/tick until ``target_frame`` appears in new schedule calls."""
    for _ in range(max_steps):
        if any(
            frame == target_frame
            for _vid, frame in engine.schedule_calls[schedule_from:]
        ):
            return
        remaining = target_frame + PCM_FRAMES - transport.engine_frame
        transport.advance(max(1, min(4800, max(remaining, 1))))
        engine.advance_to(transport.engine_frame)
        controller.tick_playback()
    pytest.fail(f"expected schedule frame {target_frame} within materialize budget")


def _owned_has_state(engine: FakeNativeEngine, state: int) -> bool:
    return any(
        not meta.get("foreign") and int(meta["state"]) == state
        for meta in engine._voices.values()
    )


def _drain_full_pass_until_boundary(
    controller,
    transport,
    engine,
    *,
    max_ticks: int = 256,
    lifecycle: dict[str, int] | None = None,
):
    """Advance through the current pass with mid-pass ticks, then cross the seam.

    Unlike `_drain_until_pass_boundary` (step-0 shortcut) and a single jump to
    ``next_e``, this helper steps in small increments so the player observes
    SCHEDULED → PLAYING → IDLE reclaim before starting the next generation.
    """
    length = controller.state.pattern.length_quarter_notes
    module = _controller_module()
    helper = _require(module, "pattern_pass_start_frames")
    current_index = int(controller._loop_pass_index)
    next_index = current_index + 1
    _cur_q, start_e = helper(
        transport.tempo_map,
        anchor_quarter=controller._loop_anchor_quarter,
        anchor_engine_frame=controller._loop_anchor_engine_frame,
        pass_index=current_index,
        length_quarter_notes=length,
    )
    _next_q, next_e = helper(
        transport.tempo_map,
        anchor_quarter=controller._loop_anchor_quarter,
        anchor_engine_frame=controller._loop_anchor_engine_frame,
        pass_index=next_index,
        length_quarter_notes=length,
    )
    del _cur_q, _next_q

    saw_playing = False
    removes_before = len(engine.remove_voice_calls)

    def _finish_if_advanced(before: int, tick):
        if controller._loop_pass_index <= before:
            return None
        if lifecycle is not None:
            lifecycle["playing_passes"] = lifecycle.get("playing_passes", 0) + int(
                saw_playing
            )
            lifecycle["reclaim_passes"] = lifecycle.get("reclaim_passes", 0) + int(
                len(engine.remove_voice_calls) > removes_before
            )
        return tick

    # 1) Materialize near pass start and observe active PLAYING one-shots.
    mid_target = int(start_e) + 1
    if transport.engine_frame < mid_target:
        transport.advance(mid_target - transport.engine_frame)
        engine.advance_to(transport.engine_frame)
    before = controller._loop_pass_index
    tick = controller.tick_playback()
    if _owned_has_state(engine, SB_VOICE_PLAYING):
        saw_playing = True
    done = _finish_if_advanced(before, tick)
    if done is not None:
        return done

    # 2) Nudge past one-shot EOF so IDLE reclaim runs on the control thread.
    idle_target = int(start_e) + PCM_FRAMES + 1
    if transport.engine_frame < idle_target:
        transport.advance(idle_target - transport.engine_frame)
        engine.advance_to(transport.engine_frame)
    before = controller._loop_pass_index
    tick = controller.tick_playback()
    done = _finish_if_advanced(before, tick)
    if done is not None:
        return done

    # 3) Walk remaining bar in lookahead chunks (covers mid-bar step edits).
    while transport.engine_frame < int(next_e):
        before = controller._loop_pass_index
        chunk = min(4800, int(next_e) - transport.engine_frame)
        if chunk <= 0:
            break
        transport.advance(chunk)
        engine.advance_to(transport.engine_frame)
        if _owned_has_state(engine, SB_VOICE_PLAYING):
            saw_playing = True
        tick = controller.tick_playback()
        if tick is None:
            return None
        done = _finish_if_advanced(before, tick)
        if done is not None:
            return done

    # 4) Land just past the next-pass seam and tick until the generation advances.
    target = int(next_e) + PCM_FRAMES + 1
    transport.advance(max(0, target - transport.engine_frame))
    engine.advance_to(transport.engine_frame)
    for _ in range(max_ticks):
        before = controller._loop_pass_index
        if _owned_has_state(engine, SB_VOICE_PLAYING):
            saw_playing = True
        tick = controller.tick_playback()
        if tick is None:
            return None
        done = _finish_if_advanced(before, tick)
        if done is not None:
            return done
        transport.advance(max(PCM_FRAMES, 4800))
        engine.advance_to(transport.engine_frame)
    pytest.fail("expected full-pass loop boundary within tick budget")


def test_channel_rack_loop_soak_voice_reclaim_gate(tmp_path: Path):
    """Frozen reliability soak (#821): many loop generations under Flow-F edits.

    Covers repeated generations, mid-soak step edit, user-channel sample
    replace, tempo change, stop/play restart, final clean stop. Proves owned
    voices stay bounded (no monotonic unbounded growth), foreign voices are
    not stolen, and stop leaves is_playing=False with loop runtime cleared.
    """
    from tests.audio_fixtures import write_sine_wav

    wav_a = write_sine_wav(
        tmp_path / "user_a.wav",
        duration_sec=0.05,
        frequency_hz=440.0,
        sr=SAMPLE_RATE,
    )
    wav_b = write_sine_wav(
        tmp_path / "user_b.wav",
        duration_sec=0.05,
        frequency_hz=550.0,
        sr=SAMPLE_RATE,
    )

    foreign_id = 42
    engine = FakeNativeEngine()
    engine.seed_foreign_voice(foreign_id, pcm_frames=10_000)
    transport = LoopTransport(engine)
    decode_paths: list[str] = []
    pcm_provider = _path_distinct_pcm_provider(decode_paths)
    module = _controller_module()
    Controller = _require(module, "ChannelRackController")
    controller = Controller(
        live_kit=_kit_with_kick(),
        transport=transport,
        pcm_provider=pcm_provider,
        lookahead_frames=4800,
    )
    controller.enter_screen2()
    # Minimal kick trigger + user channel (assign path exercises #808 replace).
    controller._state = _minimal_kick_state()
    controller.add_user_channel()
    user = next(
        ch
        for ch in controller.state.channels
        if ch.channel_id.startswith(USER_CHANNEL_ID_PREFIX)
    )
    controller.assign_user_channel_sample(user.channel_id, str(wav_a))
    # Keep user channel silent until replace checkpoint (one kick step only).
    for step in range(16):
        if Trigger(channel_id=user.channel_id, position=Fraction(step, 4)) in (
            controller.state.pattern.triggers
        ):
            controller.toggle_step(user.channel_id, step)

    handle = controller.play()
    assert handle is not None
    assert controller.is_playing is True

    owned_counts: list[int] = []
    total_counts: list[int] = []
    lifecycle: dict[str, int] = {"playing_passes": 0, "reclaim_passes": 0}
    # Segment A: continuous loop with mid-soak mutations (no pass-index reset).
    segment_a = 56
    step_edit_at = 16
    sample_replace_at = 32
    tempo_change_at = 48
    create_marker_before_replace = len(engine.create_calls)
    schedule_marker_after_edit = 0
    schedule_marker_before_tempo = len(engine.schedule_calls)
    expected_tempo_event_frame: int | None = None

    for generation in range(1, segment_a + 1):
        _drain_full_pass_until_boundary(
            controller, transport, engine, lifecycle=lifecycle
        )
        assert controller._loop_pass_index == generation
        assert controller.is_playing is True
        _record_soak_voice_snapshot(
            engine,
            foreign_id=foreign_id,
            owned_counts=owned_counts,
            total_counts=total_counts,
        )

        if generation == step_edit_at:
            # Mid-soak step edit: disable beat 0, enable beat 1 (next pass only).
            controller.toggle_step("ch_kick", 0)
            controller.toggle_step("ch_kick", 4)
            assert Trigger(channel_id="ch_kick", position=Fraction(1, 1)) in (
                controller.state.pattern.triggers
            )
            schedule_marker_after_edit = len(engine.schedule_calls)

        if generation == step_edit_at + 1:
            # Replanned pass must schedule kick at quarter 1 (not this pass's q0).
            expected_kick_q1 = _pass_event_engine_frame(
                transport,
                controller,
                pass_index=generation,
                trigger_quarter=Fraction(1, 1),
            )
            stale_kick_q0 = _pass_event_engine_frame(
                transport,
                controller,
                pass_index=generation,
                trigger_quarter=Fraction(0, 1),
            )
            _materialize_until_frame_scheduled(
                controller,
                transport,
                engine,
                target_frame=expected_kick_q1,
                schedule_from=schedule_marker_after_edit,
            )
            new_frames = [
                frame
                for _vid, frame in engine.schedule_calls[schedule_marker_after_edit:]
            ]
            assert expected_kick_q1 in new_frames
            assert stale_kick_q0 not in new_frames

        if generation == sample_replace_at:
            controller.assign_user_channel_sample(user.channel_id, str(wav_b))
            replaced = next(
                ch for ch in controller.state.channels if ch.channel_id == user.channel_id
            )
            assert replaced.sample_path == str(wav_b)
            # Arm one user step so replace is on the playable path for later gens.
            if Trigger(channel_id=user.channel_id, position=Fraction(0, 1)) not in (
                controller.state.pattern.triggers
            ):
                controller.toggle_step(user.channel_id, 0)
            create_marker_before_replace = len(engine.create_calls)

        if generation == sample_replace_at + 1:
            # Replacement must reach a created/scheduled voice, not only warm-decode.
            created_after = engine.create_calls[create_marker_before_replace:]
            assert any(
                _create_call_matches_path_seed(cfg, str(wav_b)) for cfg in created_after
            ), "expected a scheduled voice seeded from replaced user sample wav_b"

        if generation == tempo_change_at:
            module = _controller_module()
            helper = _require(module, "pattern_pass_start_frames")
            _q1_before, e1_before = helper(
                transport.tempo_map,
                anchor_quarter=controller._loop_anchor_quarter,
                anchor_engine_frame=controller._loop_anchor_engine_frame,
                pass_index=generation + 1,
                length_quarter_notes=Fraction(4, 1),
            )
            del _q1_before
            change_frame = transport.set_tempo(180)
            assert isinstance(change_frame, int)
            assert change_frame >= 0
            schedule_marker_before_tempo = len(engine.schedule_calls)
            expected_tempo_event_frame = _pass_event_engine_frame(
                transport,
                controller,
                pass_index=generation + 1,
                trigger_quarter=Fraction(1, 1),
            )
            _q2, e2_after = helper(
                transport.tempo_map,
                anchor_quarter=controller._loop_anchor_quarter,
                anchor_engine_frame=controller._loop_anchor_engine_frame,
                pass_index=generation + 2,
                length_quarter_notes=Fraction(4, 1),
            )
            del _q2
            constant_e2 = e1_before + (
                e1_before - controller._loop_anchor_engine_frame
            )
            # TempoMap must diverge from constant-frame extrapolation on a later pass.
            assert e2_after != constant_e2

        if generation == tempo_change_at + 1:
            assert expected_tempo_event_frame is not None
            _materialize_until_frame_scheduled(
                controller,
                transport,
                engine,
                target_frame=expected_tempo_event_frame,
                schedule_from=schedule_marker_before_tempo,
            )
            new_frames = [
                frame
                for _vid, frame in engine.schedule_calls[schedule_marker_before_tempo:]
            ]
            assert expected_tempo_event_frame in new_frames

    # Stop/Play restart mid-session: clean stop, then fresh loop segment.
    controller.stop()
    assert controller.is_playing is False
    assert getattr(controller, "_loop_active", False) is False
    assert controller._play_handle is None
    assert _foreign_voice_still_registered(engine, foreign_id)
    owned_after_stop = _owned_registered_voice_count(engine)
    assert owned_after_stop == 0

    restarted = controller.play()
    assert restarted is not None
    assert controller.is_playing is True
    assert controller._loop_pass_index == 0

    # Segment B: remaining generations after restart (pass index restarts at 0).
    segment_b = SOAK_GENERATIONS - segment_a
    assert segment_b >= 8
    for generation in range(1, segment_b + 1):
        _drain_full_pass_until_boundary(
            controller, transport, engine, lifecycle=lifecycle
        )
        assert controller._loop_pass_index == generation
        assert controller.is_playing is True
        _record_soak_voice_snapshot(
            engine,
            foreign_id=foreign_id,
            owned_counts=owned_counts,
            total_counts=total_counts,
        )

    assert len(owned_counts) == SOAK_GENERATIONS
    # Most generations must exercise active PLAYING and IDLE reclaim (Codex P2).
    assert lifecycle["playing_passes"] >= SOAK_GENERATIONS // 2
    assert lifecycle["reclaim_passes"] >= SOAK_GENERATIONS // 2

    # No monotonic unbounded growth: late window must not exceed early window
    # by more than reclaim slack (growth linear in generation count is a fail).
    early = owned_counts[:8]
    late = owned_counts[-8:]
    assert max(late) <= max(early) + 1
    assert max(owned_counts) <= SOAK_OWNED_VOICE_BOUND
    assert max(total_counts) <= SB_MAX_VOICES
    # Voice id allocator may increment, but registered ownership must reclaim.
    assert max(owned_counts) < SOAK_GENERATIONS // 4

    controller.stop()
    assert controller.is_playing is False
    assert getattr(controller, "_loop_active", False) is False
    assert controller._play_handle is None
    assert controller._loop_pass_index == 0
    assert _foreign_voice_still_registered(engine, foreign_id)
    assert foreign_id not in engine.stop_voice_calls
    assert foreign_id not in engine.remove_voice_calls
    owned_live = [
        vid
        for vid, meta in engine._voices.items()
        if not meta.get("foreign") and meta["state"] != SB_VOICE_IDLE
    ]
    assert owned_live == []
    # Owned IDLE leftovers may exist only until explicit remove; stop must
    # leave no owned registered voices (PatternPassPlayer.stop contract).
    assert _owned_registered_voice_count(engine) == 0

    # Tick after stop must not resurrect loop runtime.
    transport.advance(200_000)
    engine.advance_to(transport.engine_frame)
    for _ in range(8):
        assert controller.tick_playback() is None
    assert controller.is_playing is False
