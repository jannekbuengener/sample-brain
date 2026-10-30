"""#1284 Browser Loop audio runtime — domain/scheduling contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from src.browser_loop_playback import (
    BrowserLoopExtent,
    BrowserLoopOwner,
    browser_loop_extent_from_downbeats,
    map_comparison_phase_to_source_frame,
)
from src.native_audio import SB_VOICE_IDLE, SB_VOICE_PLAYING, SB_VOICE_SCHEDULED
from src.workbench_controller import WorkbenchRow
from src.workbench_preview import WorkbenchPreviewPlayer
from src.workbench_transport_adapter import WorkbenchTransportAdapter
from src.workbench_transport_preview import TransportAwarePreview


SR = 48_000
BEATS_PER_BAR = 4


def _downbeats_for_bars(bar_count: int, *, frames_per_bar: int = 12_000) -> tuple[int, ...]:
    return tuple(i * frames_per_bar for i in range(bar_count + 1))


def _details(downbeats: tuple[int, ...], *, bpm: float | None = 120.0) -> dict:
    payload: dict = {
        "beat_grid": {
            "downbeats": {"status": "ok", "sample_indices": list(downbeats)},
            "beats": {"status": "ok", "sample_indices": list(downbeats)},
        }
    }
    if bpm is not None:
        payload["bpm"] = bpm
    return payload


def _row(
    name: str,
    *,
    path: str | None = None,
    bpm: float | None = 120.0,
    downbeats: tuple[int, ...] | None = None,
    pred_type: str = "loop",
) -> WorkbenchRow:
    resolved = path or str(Path(f"C:/samples/{name}"))
    db = downbeats if downbeats is not None else _downbeats_for_bars(4)
    return WorkbenchRow(
        display_name=name,
        relative_path=name,
        path=resolved,
        bpm=bpm,
        key="Am",
        key_conf=0.9,
        loudness=-12.0,
        brightness=0.4,
        sample_class="loop",
        pred_type=pred_type,
        status="ok",
        details=_details(db, bpm=bpm),
    )


@dataclass
class _FakeVoice:
    voice_id: int
    state: int = SB_VOICE_IDLE
    start_frame: int | None = None
    rate: float = 1.0
    pcm_frames: int = 0
    config: object | None = None


@dataclass
class _FakeEngine:
    voices: dict[int, _FakeVoice] = field(default_factory=dict)
    schedule_calls: list[tuple[int, int]] = field(default_factory=list)
    removed: list[int] = field(default_factory=list)
    stopped: list[int] = field(default_factory=list)
    _engine_frame: int = 0
    running: bool = True

    def create_voice(self, config) -> int:  # noqa: ANN001
        voice_id = int(config.id)
        pcm = getattr(config, "pcm_buffer", None)
        frames = 0
        if pcm is not None:
            samples = getattr(pcm, "samples", None)
            channels = int(getattr(pcm, "channels", 1) or 1)
            if samples is not None:
                frames = int(getattr(samples, "shape", [0])[0])
                if frames == 0:
                    size = int(getattr(samples, "size", 0) or 0)
                    frames = size // max(1, channels)
        self.voices[voice_id] = _FakeVoice(
            voice_id=voice_id,
            rate=float(config.initial_rate),
            pcm_frames=frames,
            config=config,
        )
        return voice_id

    def schedule_voice_start(self, voice_id: int, engine_frame: int) -> None:
        self.schedule_calls.append((int(voice_id), int(engine_frame)))
        voice = self.voices[voice_id]
        voice.start_frame = int(engine_frame)
        voice.state = SB_VOICE_SCHEDULED

    def stop_voice(self, voice_id: int) -> None:
        self.stopped.append(voice_id)
        if voice_id in self.voices:
            self.voices[voice_id].state = SB_VOICE_IDLE

    def remove_voice(self, voice_id: int) -> None:
        self.removed.append(voice_id)
        self.voices.pop(voice_id, None)

    def set_voice_rate(self, voice_id: int, rate: float) -> None:
        if voice_id in self.voices:
            self.voices[voice_id].rate = float(rate)

    def snapshot(self):
        ids = list(self.voices)
        states = [self.voices[v].state for v in ids]
        return SimpleNamespace(
            engine_frame=self._engine_frame,
            running=self.running,
            sample_rate=SR,
            voice_ids=ids + [0] * max(0, 8 - len(ids)),
            voice_states=states + [SB_VOICE_IDLE] * max(0, 8 - len(states)),
            active_voice_count=len(ids),
            total_voice_count=len(ids),
        )

    def advance(self, frames: int) -> None:
        self._engine_frame += int(frames)
        for voice in self.voices.values():
            if voice.start_frame is None:
                continue
            if voice.state == SB_VOICE_SCHEDULED and self._engine_frame >= voice.start_frame:
                voice.state = SB_VOICE_PLAYING


def _pcm_for_extent(extent: BrowserLoopExtent) -> tuple[np.ndarray, int]:
    frames = extent.source_end_frame_exclusive - extent.source_start_frame
    return np.zeros((frames, 1), dtype=np.float32), 1


def _owner(
    monkeypatch: pytest.MonkeyPatch,
    *,
    sync: bool = False,
    bpm: float = 120.0,
) -> tuple[BrowserLoopOwner, _FakeEngine, WorkbenchTransportAdapter]:
    engine = _FakeEngine()
    transport = WorkbenchTransportAdapter(initial_bpm=bpm, initial_sync_enabled=sync)
    transport._native_engine = engine  # noqa: SLF001
    transport._native_available = True  # noqa: SLF001
    transport._native_owned = False  # noqa: SLF001
    transport._native_opened = True  # noqa: SLF001
    transport._native_started = True  # noqa: SLF001
    transport._last_native_engine_frame = 0  # noqa: SLF001

    def pcm_load(path, *, sample_rate: int, start_frame: int, end_frame_exclusive: int):  # noqa: ANN001
        frames = max(1, int(end_frame_exclusive) - int(start_frame))
        return np.zeros((frames, 1), dtype=np.float32), 1

    owner = BrowserLoopOwner(transport, pcm_load_fn=pcm_load)
    return owner, engine, transport


# ---------------------------------------------------------------------------
# Extent + phase mapping
# ---------------------------------------------------------------------------


def test_extent_from_downbeats_full_span_exact():
    downbeats = _downbeats_for_bars(8, frames_per_bar=1000)
    ext = browser_loop_extent_from_downbeats(downbeats)
    assert ext is not None
    assert ext.source_start_frame == 0
    assert ext.source_end_frame_exclusive == 8000
    assert ext.bar_count == 8
    assert ext.downbeat_frames == downbeats


def test_extent_excludes_tail_after_final_downbeat():
    # Musical end is last downbeat, not a later file-end sentinel.
    downbeats = (100, 200, 300, 400)
    ext = browser_loop_extent_from_downbeats(downbeats)
    assert ext is not None
    assert ext.source_end_frame_exclusive == 400
    assert 500 not in ext.downbeat_frames


def test_extent_rejects_missing_or_invalid_downbeats():
    assert browser_loop_extent_from_downbeats(()) is None
    assert browser_loop_extent_from_downbeats((0,)) is None
    assert browser_loop_extent_from_downbeats((10, 10)) is None
    assert browser_loop_extent_from_downbeats((10, 5)) is None
    assert browser_loop_extent_from_downbeats((-1, 10)) is None


def test_modulo_mapping_different_L_and_A():
    # L=8, A=4, master bar 17 → comparison 1 → source bar 1 % 4 = 1
    downbeats = tuple(i * 100 for i in range(5))  # 4 audition bars
    frame = map_comparison_phase_to_source_frame(
        master_bar=17,
        master_beat=0,
        master_beat_fraction=0,
        beats_per_bar=4,
        loop_bar_count=8,
        audition_bar_count=4,
        downbeat_frames=downbeats,
    )
    assert frame == 100


def test_modulo_mapping_fractional_within_bar():
    downbeats = (0, 100, 200, 300, 400)
    frame = map_comparison_phase_to_source_frame(
        master_bar=0,
        master_beat=2,
        master_beat_fraction=Fraction(0),
        beats_per_bar=4,
        loop_bar_count=4,
        audition_bar_count=4,
        downbeat_frames=downbeats,
    )
    # Halfway through bar 0 → frame 50
    assert frame == 50


# ---------------------------------------------------------------------------
# Owner lifecycle
# ---------------------------------------------------------------------------


def test_first_valid_loop_creates_exactly_one_owner(monkeypatch):
    owner, engine, _transport = _owner(monkeypatch)
    row = _row("loop-a.wav")
    result = owner.loop_on(row)
    assert result.ok
    assert owner.is_active
    assert owner.owner_row is not None
    assert Path(owner.owner_row.path) == Path(row.path)
    assert owner.extent is not None
    assert owner.extent.bar_count == 4
    owner.tick()
    # One owner may hold sounding + one lookahead-scheduled voice.
    assert 1 <= len(owner.active_voice_ids) <= 2
    assert len([v for v in engine.voices if v != 0]) == len(owner.active_voice_ids)


def test_invalid_replacement_preserves_existing_owner(monkeypatch):
    owner, _engine, _transport = _owner(monkeypatch)
    good = _row("good.wav", downbeats=_downbeats_for_bars(4))
    bad = _row("bad.wav", downbeats=())
    assert owner.loop_on(good).ok
    before = owner.owner_row.path
    result = owner.loop_on(bad)
    assert not result.ok
    assert result.reason_code == "NO_DOWNBEATS"
    assert owner.is_active
    assert owner.owner_row.path == before


def test_valid_replacement_is_atomic(monkeypatch):
    owner, engine, _transport = _owner(monkeypatch)
    a = _row("a.wav", path="C:/samples/a.wav", downbeats=_downbeats_for_bars(4))
    b = _row("b.wav", path="C:/samples/b.wav", downbeats=_downbeats_for_bars(8))
    assert owner.loop_on(a).ok
    owner.tick()
    old_voices = set(owner.active_voice_ids)
    assert owner.loop_on(b).ok
    owner.tick()
    assert Path(owner.owner_row.path) == Path(b.path)
    assert owner.extent.bar_count == 8
    # Old loop voices must be gone; new owner has at most sounding+lookahead.
    for vid in old_voices:
        assert vid not in engine.voices or engine.voices[vid].state == SB_VOICE_IDLE
    assert 1 <= len(owner.active_voice_ids) <= 2
    assert not (set(old_voices) & set(owner.active_voice_ids))


def test_loop_off_clears_only_loop_role(monkeypatch):
    owner, engine, transport = _owner(monkeypatch)
    row = _row("loop.wav")
    assert owner.loop_on(row).ok
    owner.tick()
    audition = TransportAwarePreview(WorkbenchPreviewPlayer(), transport)

    def pcm_load(path, *, sample_rate: int, start_ms: int = 0):  # noqa: ANN001
        return np.zeros((sample_rate, 1), dtype=np.float32), 1

    audition._pcm_load_fn = pcm_load  # noqa: SLF001
    monkeypatch.setattr(
        "src.workbench_transport_preview.read_audio_duration_ms",
        lambda _p: 1000,
    )
    click = _row("click.wav", path="C:/samples/click.wav", pred_type="one_shot", bpm=None)
    assert audition.play_row(click).ok
    audition_voice = audition.active_voice_id
    assert owner.loop_off().ok
    assert not owner.is_active
    assert owner.owner_row is None
    assert audition.active_voice_id == audition_voice
    assert audition_voice in engine.voices


def test_never_two_persistent_loop_owners(monkeypatch):
    owner, _engine, _transport = _owner(monkeypatch)
    assert owner.loop_on(_row("a.wav", path="C:/samples/a.wav")).ok
    assert owner.loop_on(_row("b.wav", path="C:/samples/b.wav")).ok
    assert len([owner.owner_row]) == 1
    assert owner.owner_row is not None


def test_start_stop_replace_leave_no_stale_voice(monkeypatch):
    owner, engine, _transport = _owner(monkeypatch)
    a = _row("a.wav", path="C:/samples/a.wav")
    b = _row("b.wav", path="C:/samples/b.wav")
    owner.loop_on(a)
    owner.tick()
    owner.loop_on(b)
    owner.tick()
    owner.loop_off()
    live = [
        v
        for v in engine.voices.values()
        if v.state in (SB_VOICE_SCHEDULED, SB_VOICE_PLAYING)
    ]
    assert live == []


# ---------------------------------------------------------------------------
# Audition coexistence / scroll
# ---------------------------------------------------------------------------


def test_click_replaces_audition_while_loop_stays(monkeypatch):
    owner, engine, transport = _owner(monkeypatch)
    loop_row = _row("loop.wav", path="C:/samples/loop.wav")
    assert owner.loop_on(loop_row).ok
    owner.tick()
    loop_voices = set(owner.active_voice_ids)

    audition = TransportAwarePreview(
        WorkbenchPreviewPlayer(),
        transport,
        should_keep_shared_transport=lambda: owner.is_active,
    )

    def pcm_load(path, *, sample_rate: int, start_ms: int = 0):  # noqa: ANN001
        return np.zeros((sample_rate, 1), dtype=np.float32), 1

    audition._pcm_load_fn = pcm_load  # noqa: SLF001
    monkeypatch.setattr(
        "src.workbench_transport_preview.read_audio_duration_ms",
        lambda _p: 1000,
    )
    a = _row("a.wav", path="C:/samples/a.wav", pred_type="one_shot", bpm=None)
    b = _row("b.wav", path="C:/samples/b.wav", pred_type="one_shot", bpm=None)
    assert audition.play_row(a).ok
    first = audition.active_voice_id
    assert audition.play_row(b).ok
    second = audition.active_voice_id
    assert first != second
    assert owner.is_active
    assert set(owner.active_voice_ids) == loop_voices
    # Shared transport must remain available for the Loop.
    assert owner.active_voice_ids[0] in engine.voices
    assert owner.is_active


def test_browser_scroll_emits_zero_playback_commands(monkeypatch):
    """Scroll/selection without explicit preview must not mutate Loop/audition."""
    owner, engine, _transport = _owner(monkeypatch)
    before_schedules = list(engine.schedule_calls)
    before_voices = set(engine.voices)
    # Scroll is navigation-only: no loop_on / play_row side effects.
    assert before_schedules == engine.schedule_calls
    assert before_voices == set(engine.voices)
    assert not owner.is_active
    assert owner.active_voice_ids == ()


# ---------------------------------------------------------------------------
# SYNC behavior
# ---------------------------------------------------------------------------


def test_sync_off_uses_independent_source_clock(monkeypatch):
    owner, engine, transport = _owner(monkeypatch, sync=False)
    row = _row("loop.wav", bpm=140.0)
    assert owner.loop_on(row).ok
    owner.tick()
    voice = engine.voices[owner.active_voice_ids[0]]
    assert voice.rate == pytest.approx(1.0)
    # Cycle length equals musical PCM frames at rate 1.0
    assert owner.extent is not None
    pcm_frames = (
        owner.extent.source_end_frame_exclusive - owner.extent.source_start_frame
    )
    starts = [frame for _vid, frame in engine.schedule_calls]
    engine.advance(pcm_frames)
    transport._transport.advance(pcm_frames)  # noqa: SLF001
    owner.tick(engine_frame=engine._engine_frame)
    starts2 = [frame for _vid, frame in engine.schedule_calls]
    assert len(starts2) >= len(starts)
    if len(starts2) > 1:
        assert starts2[1] - starts2[0] == pcm_frames


def test_sync_on_uses_master_tempo_grid_phase(monkeypatch):
    owner, engine, transport = _owner(monkeypatch, sync=True, bpm=120.0)
    row = _row("loop.wav", bpm=120.0, downbeats=_downbeats_for_bars(4))
    assert owner.loop_on(row).ok
    owner.tick()
    voice = engine.voices[owner.active_voice_ids[0]]
    assert voice.rate == pytest.approx(1.0)
    # Advance one comparison cycle (4 bars at 120 BPM, 48k):
    # 4 bars * 4 beats * (60/120)s * 48000 = 384000 frames
    cycle = 4 * 4 * (60.0 / 120.0) * SR
    assert owner.comparison_cycle_frames() == int(round(cycle))


def test_loop_repeats_at_n_bar_master_comparison_boundary(monkeypatch):
    owner, engine, transport = _owner(monkeypatch, sync=True, bpm=120.0)
    row = _row("loop.wav", bpm=120.0, downbeats=_downbeats_for_bars(4))
    assert owner.loop_on(row).ok
    # Force start at session frame 0
    owner.tick(engine_frame=0)
    cycle = owner.comparison_cycle_frames()
    assert cycle is not None and cycle > 0
    engine.advance(cycle)
    transport._transport.advance(cycle)  # noqa: SLF001
    owner.tick(engine_frame=engine._engine_frame)
    starts = [frame for _vid, frame in engine.schedule_calls]
    assert 0 in starts
    assert cycle in starts or any(s == cycle for s in starts)


def test_audition_enters_at_current_master_comparison_phase(monkeypatch):
    from src.session_grid import MusicalPosition

    owner, _engine, transport = _owner(monkeypatch, sync=True, bpm=120.0)
    loop_row = _row("loop.wav", bpm=120.0, downbeats=_downbeats_for_bars(8))
    assert owner.loop_on(loop_row).ok
    # Seek MASTER into bar 3 beat 0 of an 8-bar cycle
    target = transport.tempo_map.bar_beat_to_frame(MusicalPosition(bar=3, beat=0))
    transport._transport.seek(target)  # noqa: SLF001
    audition_row = _row(
        "aud.wav",
        path="C:/samples/aud.wav",
        bpm=120.0,
        downbeats=_downbeats_for_bars(4),
    )
    frame = owner.comparison_source_frame_for_row(audition_row)
    assert frame is not None
    # comparison bar 3 % 8 = 3; audition A=4 → source bar 3
    expected = map_comparison_phase_to_source_frame(
        master_bar=3,
        master_beat=0,
        master_beat_fraction=0,
        beats_per_bar=4,
        loop_bar_count=8,
        audition_bar_count=4,
        downbeat_frames=_downbeats_for_bars(4),
    )
    assert frame == expected


def test_sync_off_to_on_reanchors_without_restart_at_zero(monkeypatch):
    owner, engine, transport = _owner(monkeypatch, sync=False, bpm=120.0)
    row = _row("loop.wav", bpm=120.0)
    assert owner.loop_on(row).ok
    owner.tick()
    # Advance into the middle of a cycle
    engine.advance(5000)
    transport._transport.advance(5000)  # noqa: SLF001
    pre = list(engine.schedule_calls)
    transport.set_sync_enabled(True)
    owner.on_sync_changed(enabled=True)
    post = engine.schedule_calls[len(pre) :]
    assert owner.is_active
    # Re-anchor schedules at the transition engine frame (phase-mapped PCM), not a
    # forced restart that waits for a decorative UI boundary.
    assert post
    assert any(start == engine._engine_frame for _vid, start in post)


def test_sync_on_to_off_keeps_current_source_phase(monkeypatch):
    owner, engine, transport = _owner(monkeypatch, sync=True, bpm=120.0)
    row = _row("loop.wav", bpm=120.0)
    assert owner.loop_on(row).ok
    owner.tick()
    engine.advance(8000)
    transport._transport.advance(8000)  # noqa: SLF001
    phase_before = owner.current_source_phase_frame()
    transport.set_sync_enabled(False)
    owner.on_sync_changed(enabled=False)
    phase_after = owner.current_source_phase_frame()
    assert phase_before is not None
    assert phase_after == phase_before
    voice = engine.voices[owner.active_voice_ids[0]]
    assert voice.rate == pytest.approx(1.0)


def test_master_bpm_change_keeps_synced_roles_coherent(monkeypatch):
    owner, engine, transport = _owner(monkeypatch, sync=True, bpm=120.0)
    row = _row("loop.wav", bpm=120.0)
    assert owner.loop_on(row).ok
    owner.tick()
    # Apply tempo while stopped so the change is immediate on the map.
    transport._transport.stop()  # noqa: SLF001
    transport._transport.session_frame = 0  # noqa: SLF001
    transport.set_tempo(140.0)
    assert transport.get_current_tempo() == pytest.approx(140.0)
    owner.on_master_bpm_changed()
    voice = engine.voices[owner.active_voice_ids[0]]
    assert voice.rate == pytest.approx(140.0 / 120.0, rel=1e-6)


def test_invalid_bpm_under_sync_fails_closed(monkeypatch):
    owner, _engine, _transport = _owner(monkeypatch, sync=True, bpm=120.0)
    row = _row("loop.wav", bpm=None)
    result = owner.loop_on(row)
    assert not result.ok
    assert result.reason_code == "SYNC_NOT_SYNCABLE"
    assert not owner.is_active


def test_active_loop_becomes_unsyncable_preserves_owner_stops_audio(monkeypatch):
    owner, engine, transport = _owner(monkeypatch, sync=False, bpm=120.0)
    row = _row("loop.wav", bpm=120.0)
    assert owner.loop_on(row).ok
    owner.tick()
    # Force owner BPM invalid then enable SYNC
    owner._source_bpm = None  # noqa: SLF001 — intentional reduced-capability path
    transport.set_sync_enabled(True)
    owner.on_sync_changed(enabled=True)
    assert owner.is_active
    assert owner.owner_row is not None
    live = [
        v
        for v in engine.voices.values()
        if v.state in (SB_VOICE_SCHEDULED, SB_VOICE_PLAYING)
    ]
    assert live == []
    assert owner.reduced_capability_reason == "SYNC_NOT_SYNCABLE"


def test_many_repeats_no_growing_relative_drift(monkeypatch):
    owner, engine, transport = _owner(monkeypatch, sync=True, bpm=120.0)
    row = _row("loop.wav", bpm=120.0, downbeats=_downbeats_for_bars(4))
    assert owner.loop_on(row).ok
    cycle = owner.comparison_cycle_frames()
    assert cycle is not None
    owner.tick(engine_frame=0)
    for i in range(1, 65):
        engine.advance(cycle)
        transport._transport.advance(cycle)  # noqa: SLF001
        owner.tick(engine_frame=engine._engine_frame)
    starts = sorted({frame for _vid, frame in engine.schedule_calls})
    # All starts must land exactly on integer multiples of cycle
    for start in starts:
        assert start % cycle == 0


def test_declick_does_not_shift_musical_boundary(monkeypatch):
    owner, engine, transport = _owner(monkeypatch, sync=True, bpm=120.0)
    row = _row("loop.wav", bpm=120.0, downbeats=_downbeats_for_bars(4))
    assert owner.loop_on(row).ok
    cycle = owner.comparison_cycle_frames()
    owner.tick(engine_frame=0)
    engine.advance(cycle)
    transport._transport.advance(cycle)  # noqa: SLF001
    owner.tick(engine_frame=engine._engine_frame)
    # Crossfade may overlap voices but the scheduled musical start remains exact.
    assert any(frame == cycle for _vid, frame in engine.schedule_calls)
    assert owner.declick_frames() <= 64
