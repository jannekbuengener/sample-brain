"""#926 natural-cycle loop rack math + NaturalCycleLoopPlayer lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

import numpy as np
import pytest

from src.channel_rack import ChannelRackState, build_channel_rack_state
from src.loop_rack_playback import (
    LoopCycleSpec,
    NaturalCycleLoopPlayer,
    build_loop_cycle_specs,
    cycle_start_engine_frame,
    effective_cycle_duration_frames,
    pcm_frame_count,
)
from src.native_audio import (
    SB_MAX_VOICES,
    SB_VOICE_IDLE,
    SB_VOICE_PLAYING,
    SB_VOICE_SCHEDULED,
    PcmBufferConfig,
)
from src.pattern_core import CHANNEL_ID_BY_LIVE_KIT_SLOT, Channel, Pattern
from src.workbench_controller import WorkbenchRow
from src.workbench_live_kit import LiveKitState


def _row(path: str, *, sample_class: str | None, bpm: float | None = 120.0) -> WorkbenchRow:
    return WorkbenchRow(
        display_name=path,
        relative_path=path,
        path=path,
        bpm=bpm,
        key=None,
        key_conf=None,
        loudness=None,
        brightness=None,
        sample_class=sample_class,
        pred_type=None,
        status="ok",
        details={},
    )


def _pcm(frames: int, channels: int = 1) -> PcmBufferConfig:
    samples = np.zeros(frames * channels, dtype=np.float32)
    return PcmBufferConfig(samples=samples, channels=channels)


def test_pcm_frame_count_mono_and_stereo():
    assert pcm_frame_count(_pcm(100, 1)) == 100
    assert pcm_frame_count(_pcm(50, 2)) == 50


def test_pcm_frame_count_rejects_zero_and_bad_channels():
    with pytest.raises(ValueError):
        pcm_frame_count(_pcm(0, 1))
    with pytest.raises(ValueError):
        pcm_frame_count(SimpleNamespace(samples=np.zeros(10), channels=3))


def test_cycle_duration_rate_1_0_equals_frame_count():
    assert effective_cycle_duration_frames(48000, 1.0) == 48000


def test_cycle_duration_rate_sync_example():
    assert effective_cycle_duration_frames(1000, 2.0) == 500


def test_cycle_duration_boundary_rate_0_25():
    assert effective_cycle_duration_frames(100, 0.25) == 400


def test_cycle_duration_boundary_rate_4_0():
    assert effective_cycle_duration_frames(100, 4.0) == 25


@pytest.mark.parametrize("rate", [0.0, -1.0, float("nan"), float("inf")])
def test_cycle_duration_rejects_non_positive_nan_inf(rate: float):
    with pytest.raises(ValueError):
        effective_cycle_duration_frames(100, rate)


def test_cycle_starts_absolute_from_anchor_no_recursive_delta():
    starts = [cycle_start_engine_frame(100, n, 17) for n in range(1000)]
    assert starts[0] == 100
    assert starts[999] == 100 + 999 * 17
    assert starts[500] == 100 + 500 * 17


def test_build_specs_sync_off_rate_1():
    kit = LiveKitState()
    kit.assign("Atmos / FX", "Atmos", _row("loop.wav", sample_class="loop", bpm=128.0))
    state = build_channel_rack_state(kit)
    pcm = _pcm(1000)

    def pcm_for_path(path: str):
        return pcm if path.endswith("loop.wav") else None

    specs = build_loop_cycle_specs(
        state=state,
        live_kit=kit,
        pcm_for_path=pcm_for_path,
        play_anchor_engine_frame=50,
        sync_enabled=False,
        master_bpm=140.0,
    )
    assert len(specs) == 1
    assert specs[0].playback_rate == 1.0
    assert specs[0].effective_cycle_duration_frames == 1000
    assert specs[0].play_anchor_engine_frame == 50


def test_build_specs_sync_on_valid_bpm_uses_compute_sync_playback_rate():
    kit = LiveKitState()
    kit.assign("Atmos / FX", "Atmos", _row("loop.wav", sample_class="loop", bpm=100.0))
    state = build_channel_rack_state(kit)
    pcm = _pcm(1000)
    specs = build_loop_cycle_specs(
        state=state,
        live_kit=kit,
        pcm_for_path=lambda _p: pcm,
        play_anchor_engine_frame=0,
        sync_enabled=True,
        master_bpm=200.0,
    )
    assert len(specs) == 1
    assert specs[0].playback_rate == 2.0
    assert specs[0].effective_cycle_duration_frames == 500


def test_build_specs_sync_on_missing_bpm_skips_channel():
    kit = LiveKitState()
    kit.assign("Atmos / FX", "Atmos", _row("loop.wav", sample_class="loop", bpm=None))
    state = build_channel_rack_state(kit)
    specs = build_loop_cycle_specs(
        state=state,
        live_kit=kit,
        pcm_for_path=lambda _p: _pcm(1000),
        play_anchor_engine_frame=0,
        sync_enabled=True,
        master_bpm=120.0,
    )
    assert specs == ()


def test_build_specs_ignores_oneshot_and_ambiguous():
    kit = LiveKitState()
    kit.assign("Kick + Bass", "Kick", _row("kick.wav", sample_class="oneshot"))
    kit.assign("Kick + Bass", "Bass", _row("amb.wav", sample_class=None))
    kit.assign("Atmos / FX", "Atmos", _row("loop.wav", sample_class="loop", bpm=120.0))
    state = build_channel_rack_state(kit)
    specs = build_loop_cycle_specs(
        state=state,
        live_kit=kit,
        pcm_for_path=lambda p: _pcm(100) if "loop" in p else _pcm(10),
        play_anchor_engine_frame=0,
        sync_enabled=False,
        master_bpm=120.0,
    )
    assert len(specs) == 1
    assert specs[0].channel_id == CHANNEL_ID_BY_LIVE_KIT_SLOT[("Atmos / FX", "Atmos")]


@dataclass
class _FakeVoice:
    voice_id: int
    state: int = SB_VOICE_IDLE
    start_frame: int | None = None
    rate: float = 1.0
    removed: bool = False


@dataclass
class _FakeEngine:
    voices: dict[int, _FakeVoice] = field(default_factory=dict)
    create_fail_ids: set[int] = field(default_factory=set)
    schedule_fail_ids: set[int] = field(default_factory=set)
    set_rate_calls: list[tuple[int, float]] = field(default_factory=list)

    def create_voice(self, config) -> int:
        voice_id = int(config.id)
        if voice_id in self.create_fail_ids:
            raise RuntimeError("create failed")
        self.voices[voice_id] = _FakeVoice(
            voice_id=voice_id, rate=float(config.initial_rate)
        )
        return voice_id

    def schedule_voice_start(self, voice_id: int, engine_frame: int) -> None:
        if voice_id in self.schedule_fail_ids:
            raise RuntimeError("schedule failed")
        voice = self.voices[voice_id]
        voice.start_frame = int(engine_frame)
        voice.state = SB_VOICE_SCHEDULED

    def stop_voice(self, voice_id: int) -> None:
        if voice_id in self.voices:
            self.voices[voice_id].state = SB_VOICE_IDLE

    def remove_voice(self, voice_id: int) -> None:
        voice = self.voices.pop(voice_id, None)
        if voice is not None:
            voice.removed = True

    def set_rate(self, voice_id: int, rate: float) -> None:
        self.set_rate_calls.append((voice_id, rate))
        if voice_id in self.voices:
            self.voices[voice_id].rate = rate

    def get_snapshot(self):
        ids = list(self.voices)
        states = [self.voices[i].state for i in ids]
        # Pad to SB_MAX_VOICES-like arrays for realism.
        while len(ids) < SB_MAX_VOICES:
            ids.append(0)
            states.append(SB_VOICE_IDLE)
        return SimpleNamespace(
            total_voice_count=sum(1 for i in ids if i != 0),
            voice_ids=ids,
            voice_states=states,
        )

    def advance_to(self, engine_frame: int) -> None:
        for voice in self.voices.values():
            if voice.start_frame is None:
                continue
            if voice.state == SB_VOICE_SCHEDULED and engine_frame >= voice.start_frame:
                voice.state = SB_VOICE_PLAYING
            if voice.state == SB_VOICE_PLAYING:
                # Spec duration encoded via start_frame + duration stored in player.
                pass


def _spec(
    channel_id: str,
    *,
    path: str = "loop.wav",
    frames: int = 100,
    rate: float = 1.0,
    anchor: int = 0,
) -> LoopCycleSpec:
    duration = effective_cycle_duration_frames(frames, rate)
    return LoopCycleSpec(
        channel_id=channel_id,
        sample_path=path,
        pcm_frame_count=frames,
        source_bpm=120.0,
        playback_rate=rate,
        effective_cycle_duration_frames=duration,
        play_anchor_engine_frame=anchor,
    )


def test_first_cycle_starts_at_play_anchor():
    engine = _FakeEngine()
    player = NaturalCycleLoopPlayer(
        [_spec("ch_loop", anchor=42, frames=100)],
        pcm_for_path=lambda _p: _pcm(100),
        lookahead_frames=0,
    )
    counter = {"n": 0}

    def alloc() -> int:
        counter["n"] += 1
        return counter["n"]

    result = player.tick(engine_frame=42, engine=engine, allocate_voice_id=alloc)
    assert result.scheduled_count == 1
    voice = next(iter(engine.voices.values()))
    assert voice.start_frame == 42


def test_schedules_future_cycle_inside_lookahead_only():
    engine = _FakeEngine()
    player = NaturalCycleLoopPlayer(
        [_spec("ch_loop", anchor=0, frames=100)],
        pcm_for_path=lambda _p: _pcm(100),
        lookahead_frames=50,
    )
    n = {"v": 0}

    def alloc() -> int:
        n["v"] += 1
        return n["v"]

    player.tick(engine_frame=0, engine=engine, allocate_voice_id=alloc)
    # Cycle 0 at 0 (sounding), cycle 1 at 100 is outside lookahead 50 → not yet.
    assert len(engine.voices) == 1
    player.tick(engine_frame=60, engine=engine, allocate_voice_id=alloc)
    # From 60, cycle 1 at 100 is within lookahead 50.
    assert any(v.start_frame == 100 for v in engine.voices.values())


def test_no_self_overlap_one_sounding_voice_per_channel():
    engine = _FakeEngine()
    player = NaturalCycleLoopPlayer(
        [_spec("ch_loop", frames=100)],
        pcm_for_path=lambda _p: _pcm(100),
        lookahead_frames=1000,
    )
    n = {"v": 0}

    def alloc() -> int:
        n["v"] += 1
        return n["v"]

    player.tick(engine_frame=0, engine=engine, allocate_voice_id=alloc)
    # At most sounding + one future.
    assert len(engine.voices) <= 2


def test_idle_reclaim_allows_next_cycle():
    engine = _FakeEngine()
    player = NaturalCycleLoopPlayer(
        [_spec("ch_loop", frames=10)],
        pcm_for_path=lambda _p: _pcm(10),
        lookahead_frames=0,
    )
    n = {"v": 0}

    def alloc() -> int:
        n["v"] += 1
        return n["v"]

    player.tick(engine_frame=0, engine=engine, allocate_voice_id=alloc)
    voice_id = next(iter(engine.voices))
    engine.voices[voice_id].state = SB_VOICE_PLAYING
    player.tick(engine_frame=1, engine=engine, allocate_voice_id=alloc)
    engine.voices[voice_id].state = SB_VOICE_IDLE
    player.tick(engine_frame=10, engine=engine, allocate_voice_id=alloc)
    assert voice_id not in engine.voices
    assert any(v.start_frame == 10 for v in engine.voices.values())


def test_multiple_loop_channels_different_lengths():
    engine = _FakeEngine()
    player = NaturalCycleLoopPlayer(
        [
            _spec("ch_a", path="a.wav", frames=100, anchor=0),
            _spec("ch_b", path="b.wav", frames=250, anchor=0),
        ],
        pcm_for_path=lambda p: _pcm(100 if p.startswith("a") else 250),
        lookahead_frames=0,
    )
    n = {"v": 0}

    def alloc() -> int:
        n["v"] += 1
        return n["v"]

    player.tick(engine_frame=0, engine=engine, allocate_voice_id=alloc)
    starts = sorted(v.start_frame for v in engine.voices.values())
    assert starts == [0, 0]


def test_loop_player_respects_sb_max_voices_fail_soft():
    engine = _FakeEngine()
    # Fill capacity with foreign voices.
    for i in range(SB_MAX_VOICES):
        engine.voices[1000 + i] = _FakeVoice(voice_id=1000 + i, state=SB_VOICE_PLAYING)
    player = NaturalCycleLoopPlayer(
        [_spec("ch_loop", frames=100)],
        pcm_for_path=lambda _p: _pcm(100),
        lookahead_frames=0,
        max_voices=SB_MAX_VOICES,
    )
    result = player.tick(
        engine_frame=0, engine=engine, allocate_voice_id=lambda: 1
    )
    assert result.skipped_voice_limit_count >= 1
    assert 1 not in engine.voices


def test_loop_create_failure_fail_soft():
    engine = _FakeEngine(create_fail_ids={1})
    player = NaturalCycleLoopPlayer(
        [_spec("ch_loop", frames=100)],
        pcm_for_path=lambda _p: _pcm(100),
        lookahead_frames=0,
    )
    result = player.tick(
        engine_frame=0, engine=engine, allocate_voice_id=lambda: 1
    )
    assert result.skipped_engine_error_count >= 1
    assert engine.voices == {}


def test_loop_schedule_failure_cleans_up():
    engine = _FakeEngine(schedule_fail_ids={1})
    player = NaturalCycleLoopPlayer(
        [_spec("ch_loop", frames=100)],
        pcm_for_path=lambda _p: _pcm(100),
        lookahead_frames=0,
    )
    result = player.tick(
        engine_frame=0, engine=engine, allocate_voice_id=lambda: 1
    )
    assert result.skipped_engine_error_count >= 1
    assert engine.voices == {}


def test_stop_clears_current_and_future_ownership():
    engine = _FakeEngine()
    player = NaturalCycleLoopPlayer(
        [_spec("ch_loop", frames=100)],
        pcm_for_path=lambda _p: _pcm(100),
        lookahead_frames=1000,
    )
    n = {"v": 0}

    def alloc() -> int:
        n["v"] += 1
        return n["v"]

    player.tick(engine_frame=0, engine=engine, allocate_voice_id=alloc)
    assert engine.voices
    player.stop(engine)
    assert engine.voices == {}
    later = player.tick(engine_frame=50, engine=engine, allocate_voice_id=alloc)
    assert later.scheduled_voice_ids == ()
    assert engine.voices == {}


def test_stop_before_future_scheduled_cycle_removes_pending():
    engine = _FakeEngine()
    player = NaturalCycleLoopPlayer(
        [_spec("ch_loop", frames=100)],
        pcm_for_path=lambda _p: _pcm(100),
        lookahead_frames=200,
    )
    n = {"v": 0}

    def alloc() -> int:
        n["v"] += 1
        return n["v"]

    player.tick(engine_frame=0, engine=engine, allocate_voice_id=alloc)
    assert any(v.start_frame == 100 for v in engine.voices.values())
    player.stop(engine)
    assert engine.voices == {}


def test_cycle_starts_no_drift_over_1000_cycles():
    duration = 17
    anchor = 100
    starts = [
        cycle_start_engine_frame(anchor, n, duration) for n in range(1000)
    ]
    for n, start in enumerate(starts):
        assert start == anchor + n * duration
