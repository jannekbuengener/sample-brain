"""Frozen behavioral contracts for the shared Screen-1 playback owner (#528)."""

from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf

from src.session_grid import SessionTransport, TimeSignature
from src.workbench import WorkbenchApp
from src.workbench_controller import WorkbenchRow
from src.workbench_live_kit import LiveKitState
from src.workbench_transport_adapter import WorkbenchTransportAdapter
from src.workbench_transport_ui import TransportAwarePreview


class _NativeEngine:
    def __init__(self, *, engine_frame: int = 4_096) -> None:
        self.engine_frame = engine_frame
        self.running = False
        self.events: list[tuple] = []
        self.configs: list[object] = []

    def start(self) -> None:
        self.running = True
        self.events.append(("engine_start",))

    def stop(self) -> None:
        self.running = False
        self.events.append(("engine_stop",))

    def close(self) -> None:
        self.events.append(("engine_close",))

    def snapshot(self):
        return SimpleNamespace(engine_frame=self.engine_frame, running=self.running)

    def create_voice(self, config) -> int:
        self.configs.append(config)
        self.events.append(("create", config.id, config.initial_rate))
        return config.id

    def schedule_voice_start(self, voice_id: int, engine_frame: int) -> None:
        self.events.append(("schedule", voice_id, engine_frame))

    def stop_voice(self, voice_id: int) -> None:
        self.events.append(("stop_voice", voice_id))

    def remove_voice(self, voice_id: int) -> None:
        self.events.append(("remove_voice", voice_id))

    def set_voice_rate(self, voice_id: int, rate: float) -> None:
        self.events.append(("rate", voice_id, rate))


class _LegacyPreview:
    def __init__(self) -> None:
        self.current_path: Path | None = None
        self.play_calls: list[tuple[Path, int]] = []
        self.stop_calls = 0

    def play(self, path, *, start_ms: int = 0):
        resolved = Path(path).resolve()
        self.current_path = resolved
        self.play_calls.append((resolved, start_ms))
        return SimpleNamespace(ok=True, message="")

    def stop(self) -> None:
        self.stop_calls += 1
        self.current_path = None


def _row(
    path: Path,
    *,
    name: str = "loop.wav",
    bpm: float | None = 120.0,
    sample_class: str = "loop",
    duration_sec: str = "2.0",
) -> WorkbenchRow:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(b"generated-test-placeholder")
    return WorkbenchRow(
        display_name=name,
        relative_path=f"synthetic/{name}",
        path=str(path),
        bpm=bpm,
        key="Am",
        key_conf=0.9,
        loudness=-12.0,
        brightness=2_000.0,
        sample_class=sample_class,
        pred_type=None,
        status="ok",
        details={"duration_sec": duration_sec, "source": "generated"},
    )


def _pcm_loader(calls: list[tuple[Path, int, int]]):
    def load(path: Path, *, sample_rate: int, start_ms: int):
        calls.append((Path(path).resolve(), sample_rate, start_ms))
        return np.array([[0.25], [-0.25], [0.5]], dtype=np.float32), 1

    return load


def _bridge(
    *,
    bpm: float = 132.0,
    time_signature: TimeSignature | None = None,
    engine_frame: int = 4_096,
):
    native = _NativeEngine(engine_frame=engine_frame)
    session = SessionTransport(
        sample_rate=48_000,
        bpm=bpm,
        time_signature=time_signature,
    )
    transport = WorkbenchTransportAdapter(
        transport=session,
        native_engine=native,
    )
    load_calls: list[tuple[Path, int, int]] = []
    owner = TransportAwarePreview(
        _LegacyPreview(),
        transport,
        pcm_load_fn=_pcm_loader(load_calls),
    )
    return owner, transport, native, load_calls


def _app_with_owner(owner, row: WorkbenchRow):
    app = WorkbenchApp.__new__(WorkbenchApp)
    app._preview = owner
    app._preview_row_path = row.path
    app._detail_row = row
    app._busy = False
    app._rows = [row]
    app._visible_rows = [row]
    app._playlist_names = ["Synthetic"]
    app._live_kit_state = LiveKitState()
    app._set_status = lambda *_args, **_kwargs: None
    app._update_preview_state = lambda *_args, **_kwargs: None
    return app


def test_browser_and_live_kit_use_the_same_authoritative_playback_owner(tmp_path):
    owner, _transport, native, _loads = _bridge()
    browser_row = _row(tmp_path / "browser.wav", name="browser.wav")
    slot_row = _row(tmp_path / "slot.wav", name="slot.wav")
    app = _app_with_owner(owner, browser_row)
    app._live_kit_state.assign("Drums", "Main Drum", slot_row)

    app._play_preview(start_ms=0)
    assert app._audition_live_kit_slot("Drums", "Main Drum") is True

    assert app._preview is owner
    assert [Path(call[0]).name for call in _loads] == ["browser.wav", "slot.wav"]
    assert [event[0] for event in native.events].count("schedule") == 2


def test_assigned_live_kit_slot_auditions_its_exact_workbench_row_once(tmp_path):
    owner, _transport, native, loads = _bridge()
    selected = _row(tmp_path / "selected.wav", name="selected.wav")
    assigned = _row(tmp_path / "assigned.wav", name="assigned.wav", bpm=128.0)
    app = _app_with_owner(owner, selected)
    app._live_kit_state.assign("Drums", "Closed Hat", assigned)

    assert app._audition_live_kit_slot("Drums", "Closed Hat") is True

    assert loads == [(Path(assigned.path).resolve(), 48_000, 0)]
    assert len(native.configs) == 1


def test_empty_live_kit_slot_plays_nothing_and_mutates_nothing(tmp_path):
    owner, _transport, native, loads = _bridge()
    row = _row(tmp_path / "selected.wav", name="selected.wav")
    app = _app_with_owner(owner, row)
    before = (
        tuple(app._rows),
        tuple(app._visible_rows),
        tuple(app._playlist_names),
        app._detail_row,
        app._preview_row_path,
        app._live_kit_state.assignment_for("Drums", "Open Hat"),
    )

    assert app._audition_live_kit_slot("Drums", "Open Hat") is False

    after = (
        tuple(app._rows),
        tuple(app._visible_rows),
        tuple(app._playlist_names),
        app._detail_row,
        app._preview_row_path,
        app._live_kit_state.assignment_for("Drums", "Open Hat"),
    )
    assert after == before
    assert loads == []
    assert native.events == []


def test_browser_to_live_kit_replacement_never_leaves_a_parallel_owner(tmp_path):
    owner, _transport, native, _loads = _bridge()
    first = _row(tmp_path / "first.wav", name="first.wav")
    second = _row(tmp_path / "second.wav", name="second.wav")

    assert owner.play_row(first).ok
    assert owner.play_row(second).ok

    first_id = native.configs[0].id
    second_id = native.configs[1].id
    names = [event[0] for event in native.events]
    assert first_id != second_id
    assert names.index("stop_voice") < names.index("remove_voice")
    assert names.index("remove_voice") < max(
        index for index, event in enumerate(native.events) if event[0] == "create"
    )
    assert owner.active_voice_id == second_id


def test_one_shot_without_meaningful_bpm_never_invents_stretch(tmp_path):
    owner, transport, native, _loads = _bridge()
    transport.toggle_sync()
    one_shot = _row(
        tmp_path / "one-shot.wav",
        name="one-shot.wav",
        bpm=None,
        sample_class="one_shot",
        duration_sec="0.2",
    )

    result = owner.play_row(one_shot)

    assert result.ok
    assert native.configs[0].initial_rate == pytest.approx(1.0)
    assert native.configs[0].source_bpm == pytest.approx(0.0)


@pytest.mark.parametrize("sample_class", ["loop", "long_audio"])
def test_tempo_bearing_audio_uses_master_over_source_rate_when_sync_is_on(
    tmp_path, sample_class
):
    owner, transport, native, _loads = _bridge(bpm=132.0)
    transport.toggle_sync()

    result = owner.play_row(
        _row(tmp_path / f"{sample_class}.wav", bpm=120.0, sample_class=sample_class)
    )

    assert result.ok
    assert native.configs[0].initial_rate == pytest.approx(1.1)
    voice_rate, voice_status = transport.voice_sync_state(native.configs[0].id)
    assert voice_rate == pytest.approx(1.1)
    assert voice_status == "sync"


def test_sync_off_keeps_tempo_bearing_audio_at_original_rate(tmp_path):
    owner, _transport, native, _loads = _bridge(bpm=132.0)

    result = owner.play_row(_row(tmp_path / "loop.wav", bpm=120.0))

    assert result.ok
    assert native.configs[0].initial_rate == pytest.approx(1.0)


def test_unknown_bpm_fails_closed_when_tempo_sync_is_required(tmp_path):
    owner, transport, native, loads = _bridge()
    transport.toggle_sync()

    result = owner.play_row(
        _row(tmp_path / "unknown-loop.wav", bpm=None, sample_class="loop")
    )

    assert not result.ok
    assert "BPM" in result.message
    assert loads == []
    assert native.configs == []
    assert owner.active_voice_id is None


def test_schedule_and_grid_come_from_the_shared_session_transport(tmp_path):
    signature = TimeSignature(3, 4)
    owner, transport, native, _loads = _bridge(
        time_signature=signature,
        engine_frame=12_345,
    )

    assert owner.play_row(_row(tmp_path / "grid.wav")).ok

    assert owner.transport is transport
    assert owner.grid_time_signature is transport.tempo_map.time_signature
    assert owner.grid_time_signature is signature
    assert ("schedule", native.configs[0].id, 12_345) in native.events


def test_playback_does_not_mutate_assignments_library_playlist_or_audio(tmp_path):
    wav = tmp_path / "generated.wav"
    sf.write(wav, np.linspace(-0.25, 0.25, 2_400, dtype=np.float32), 48_000)
    row = _row(wav, sample_class="long_audio")
    owner, _transport, _native, _loads = _bridge()
    app = _app_with_owner(owner, row)
    app._live_kit_state.assign("Melodic", "Pad", row)
    before_digest = hashlib.sha256(wav.read_bytes()).hexdigest()
    before_assignment = app._live_kit_state.assignment_for("Melodic", "Pad")
    before_library = tuple(app._rows)
    before_playlist = tuple(app._playlist_names)

    assert owner.play_row(row).ok

    assert hashlib.sha256(wav.read_bytes()).hexdigest() == before_digest
    assert app._live_kit_state.assignment_for("Melodic", "Pad") is before_assignment
    assert tuple(app._rows) == before_library
    assert tuple(app._playlist_names) == before_playlist


def test_live_kit_audition_uses_assignment_without_reselecting_browser_row(tmp_path):
    owner, _transport, _native, loads = _bridge()
    browser_row = _row(tmp_path / "browser.wav", name="browser.wav")
    slot_row = replace(
        browser_row,
        display_name="slot.wav",
        relative_path="synthetic/slot.wav",
        path=str(tmp_path / "slot.wav"),
    )
    app = _app_with_owner(owner, browser_row)
    app._live_kit_state.assign("Atmos / FX", "FX", slot_row)
    app._selected_row = lambda: pytest.fail("slot audition re-read Browser selection")

    assert app._audition_live_kit_slot("Atmos / FX", "FX") is True

    assert loads[0][0] == Path(slot_row.path).resolve()
    assert app._detail_row is browser_row
    assert app._preview_row_path == browser_row.path
