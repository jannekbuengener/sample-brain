from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.workbench_controller import WorkbenchRow, preview_start_ms_from_waveform_x
from src.workbench_preview import PreviewResult, WorkbenchPreviewPlayer
from tests.audio_fixtures import write_sine_wav


def _workbench_module():
    """Return the live workbench module (controller tests may reload it)."""
    return importlib.import_module("src.workbench")


def _workbench_app_cls():
    return _workbench_module().WorkbenchApp


def test_preview_start_ms_from_waveform_x_maps_click_to_ms():
    assert preview_start_ms_from_waveform_x(100, 200, 1000) == 500
    assert preview_start_ms_from_waveform_x(0, 200, 1000) == 0
    assert preview_start_ms_from_waveform_x(200, 200, 1000) == 999


def test_workbench_layout_has_no_play_stop_buttons():
    source = inspect.getsource(_workbench_app_cls()._build_layout)
    assert "_play_btn" not in source
    assert "_stop_btn" not in source


def _sample_row(path: Path) -> WorkbenchRow:
    return WorkbenchRow(
        display_name=path.name,
        relative_path=path.name,
        path=str(path.resolve()),
        bpm=120.0,
        key="C",
        key_conf=0.9,
        loudness=-10.0,
        brightness=50.0,
        sample_class="kick",
        pred_type="kick",
        status="ok",
    )


def _playback_app(*, canvas_width: int = 400, loop_edit_mode: bool = False):
    cls = _workbench_app_cls()
    app = cls.__new__(cls)
    app._busy = False
    app._detail_row = None
    app._preview_row_path = None
    app._status_var = SimpleNamespace(value="")
    app._loop_edit_pending_start_ms = None
    loop_mode = {"value": loop_edit_mode}
    usage_values: list[str] = []

    app._loop_edit_mode_var = SimpleNamespace(
        get=lambda: loop_mode["value"],
        set=lambda value: loop_mode.__setitem__("value", bool(value)),
    )
    app._waveform_usage_var = SimpleNamespace(
        set=lambda value: usage_values.append(str(value)),
    )
    app._usage_values = usage_values

    def set_status(message: str, *, tone: str = "neutral") -> None:
        app._status_var.value = message

    app._set_status = set_status
    app._waveform_canvas = SimpleNamespace(
        winfo_width=lambda: canvas_width,
    )
    play_calls: list[tuple[str, int]] = []

    def mock_play(path, *, start_ms=0):
        play_calls.append((str(path), start_ms))
        return PreviewResult(ok=True)

    app._preview = SimpleNamespace(play=mock_play)
    app._play_calls = play_calls
    return app


def test_left_click_plays_without_saving_cue(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.2, frequency_hz=440.0)
    app = _playback_app()
    app._detail_row = _sample_row(wav)
    app._preview_row_path = str(wav.resolve())

    wb = _workbench_module()

    with (
        patch.object(wb, "get_preview_start_ms", return_value=456),
        patch.object(wb, "save_workbench_sample_cue") as mock_save,
    ):
        app._play_selected_from_waveform()
        mock_save.assert_not_called()

    assert app._play_calls == [(str(wav.resolve()), 456)]
    assert "Cue (456 ms)" in app._status_var.value


def test_left_click_no_sample_sets_status():
    app = _playback_app()
    app._detail_row = None
    app._play_selected_from_waveform()
    assert app._status_var.value == "Kein Sample ausgewählt."


def test_right_click_plays_at_click_position_without_saving_cue(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.5, frequency_hz=440.0)
    app = _playback_app()
    app._detail_row = _sample_row(wav)
    app._preview_row_path = str(wav.resolve())

    wb = _workbench_module()

    with (
        patch.object(wb, "preview_start_ms_from_waveform_x", return_value=123),
        patch.object(wb, "save_workbench_sample_cue") as mock_save,
    ):
        app._play_selected_from_waveform_position(100)
        mock_save.assert_not_called()

    assert app._play_calls == [(str(wav.resolve()), 123)]
    assert "Klickposition (123 ms)" in app._status_var.value


def test_right_click_unknown_duration_sets_status(tmp_path: Path, monkeypatch):
    missing = tmp_path / "missing.wav"
    app = _playback_app()
    app._detail_row = _sample_row(missing)
    app._preview_row_path = str(missing.resolve())
    monkeypatch.setattr(_workbench_module(), "read_audio_duration_ms", lambda _path: None)

    app._play_selected_from_waveform_position(50)
    assert app._play_calls == []
    assert app._status_var.value == "Kann Startposition nicht bestimmen."


def test_play_preview_status_for_click_position(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.2, frequency_hz=440.0)
    app = _playback_app()
    app._preview_row_path = str(wav.resolve())
    app._preview = WorkbenchPreviewPlayer(
        play_fn=lambda path, start_ms=0: PreviewResult(ok=True),
        stop_fn=lambda: None,
    )
    app._play_preview(start_ms=77, from_click_position=True)
    assert "Klickposition (77 ms)" in app._status_var.value


def test_waveform_click_handlers_delegate(monkeypatch):
    app = _playback_app()
    left_called: list[bool] = []
    right_called: list[int] = []
    shift_called: list[int] = []

    monkeypatch.setattr(app, "_play_selected_from_waveform", lambda: left_called.append(True))
    monkeypatch.setattr(
        app,
        "_play_selected_from_waveform_position",
        lambda x: right_called.append(x),
    )
    monkeypatch.setattr(
        app,
        "_set_selected_cue_from_waveform_position",
        lambda x: shift_called.append(x),
    )

    app._on_waveform_click(SimpleNamespace(state=0, x=0))
    app._on_waveform_click(SimpleNamespace(state=0x0001, x=88))
    app._on_waveform_right_click(SimpleNamespace(x=42))

    assert left_called == [True]
    assert shift_called == [88]
    assert right_called == [42]


def test_shift_click_saves_cue_without_playing(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.5, frequency_hz=440.0)
    app = _playback_app()
    app._detail_row = _sample_row(wav)
    app._preview_row_path = str(wav.resolve())
    draw_calls: list[bool] = []

    wb = _workbench_module()

    monkeypatch_draw = lambda row: draw_calls.append(True)
    app._draw_waveform = monkeypatch_draw

    with (
        patch.object(wb, "preview_start_ms_from_waveform_x", return_value=250),
        patch.object(wb, "load_workbench_sample_cue") as mock_load,
        patch.object(wb, "save_workbench_sample_cue") as mock_save,
        patch.object(wb, "read_audio_duration_ms", return_value=500),
    ):
        from src.workbench_library import WorkbenchCueMetadata

        mock_load.return_value = WorkbenchCueMetadata(cue_start_ms=0)
        app._set_selected_cue_from_waveform_position(200)

        mock_save.assert_called_once()
        saved_path, saved_metadata = mock_save.call_args[0]
        assert str(saved_path) == str(wav.resolve())
        assert saved_metadata.cue_start_ms == 250
        assert saved_metadata.cue_source == "manual"

    assert app._play_calls == []
    assert draw_calls == [True]
    assert app._status_var.value == "Cue dauerhaft gesetzt: 250 ms"


def test_shift_click_preserves_attack_and_loop_metadata(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.5, frequency_hz=440.0)
    app = _playback_app()
    app._detail_row = _sample_row(wav)

    wb = _workbench_module()
    from src.workbench_library import WorkbenchCueMetadata

    existing = WorkbenchCueMetadata(
        cue_start_ms=10,
        attack_ms=50,
        loop_start_ms=100,
        loop_end_ms=400,
        cue_source="detected",
    )

    with (
        patch.object(wb, "preview_start_ms_from_waveform_x", return_value=300),
        patch.object(wb, "load_workbench_sample_cue", return_value=existing),
        patch.object(wb, "save_workbench_sample_cue") as mock_save,
        patch.object(wb, "read_audio_duration_ms", return_value=500),
        patch.object(app, "_draw_waveform", lambda _row: None),
    ):
        app._set_selected_cue_from_waveform_position(150)

        saved_metadata = mock_save.call_args[0][1]
        assert saved_metadata.cue_start_ms == 300
        assert saved_metadata.attack_ms == 50
        assert saved_metadata.loop_start_ms == 100
        assert saved_metadata.loop_end_ms == 400
        assert saved_metadata.cue_source == "manual"


def test_shift_click_no_sample_sets_status():
    app = _playback_app()
    app._detail_row = None
    app._set_selected_cue_from_waveform_position(50)
    assert app._play_calls == []
    assert app._status_var.value == "Kein Sample ausgewählt."


def test_shift_click_unknown_duration_sets_status(tmp_path: Path, monkeypatch):
    missing = tmp_path / "missing.wav"
    app = _playback_app()
    app._detail_row = _sample_row(missing)
    monkeypatch.setattr(_workbench_module(), "read_audio_duration_ms", lambda _path: None)

    app._set_selected_cue_from_waveform_position(50)
    assert app._play_calls == []
    assert app._status_var.value == "Kann Cue-Position nicht bestimmen."


def test_shift_click_sample_not_in_library_sets_status(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.5, frequency_hz=440.0)
    app = _playback_app()
    app._detail_row = _sample_row(wav)

    wb = _workbench_module()
    from src.workbench_library import WorkbenchCueNotFoundError, WorkbenchCueMetadata

    with (
        patch.object(wb, "preview_start_ms_from_waveform_x", return_value=100),
        patch.object(wb, "load_workbench_sample_cue", return_value=WorkbenchCueMetadata()),
        patch.object(
            wb,
            "save_workbench_sample_cue",
            side_effect=WorkbenchCueNotFoundError("not in library"),
        ),
        patch.object(wb, "read_audio_duration_ms", return_value=500),
    ):
        app._set_selected_cue_from_waveform_position(80)

    assert app._play_calls == []
    assert "Bibliothek" in app._status_var.value


def test_cue_start_ms_from_waveform_x_returns_none_without_duration(tmp_path: Path, monkeypatch):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.2, frequency_hz=440.0)
    app = _playback_app()
    app._detail_row = _sample_row(wav)
    monkeypatch.setattr(_workbench_module(), "read_audio_duration_ms", lambda _path: None)

    assert app._cue_start_ms_from_waveform_x(100) is None


def test_waveform_usage_hint_documents_click_controls():
    wb = _workbench_module()
    hint = wb.WAVEFORM_USAGE_HINT
    assert "Linksklick" in hint
    assert "Rechtsklick" in hint
    assert "Shift" in hint
    assert "Cue" in hint


def test_waveform_loop_edit_hint_documents_mode_controls():
    wb = _workbench_module()
    hint = wb.WAVEFORM_LOOP_EDIT_HINT
    assert "Loop-Modus" in hint
    assert "Start" in hint
    assert "Ende" in hint
    assert "löschen" in hint


def test_update_waveform_usage_hint_switches_with_loop_mode():
    wb = _workbench_module()
    app = _playback_app()
    usage_values: list[str] = []
    app._waveform_usage_var = SimpleNamespace(
        set=lambda value: usage_values.append(str(value)),
    )

    app._loop_edit_mode_var.set(True)
    app._update_waveform_usage_hint()
    assert usage_values[-1] == wb.WAVEFORM_LOOP_EDIT_HINT

    app._loop_edit_mode_var.set(False)
    app._update_waveform_usage_hint()
    assert usage_values[-1] == wb.WAVEFORM_USAGE_HINT


def test_loop_edit_mode_toggle_sets_status():
    app = _playback_app()
    app._loop_edit_mode_var.set(True)
    app._on_loop_edit_mode_toggled()
    assert "Loop bearbeiten aktiv" in app._status_var.value

    app._loop_edit_mode_var.set(False)
    app._on_loop_edit_mode_toggled()
    assert app._status_var.value == "Loop bearbeiten aus"


def test_loop_edit_first_click_sets_pending_without_save(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.5, frequency_hz=440.0)
    app = _playback_app(loop_edit_mode=True)
    app._detail_row = _sample_row(wav)
    wb = _workbench_module()

    with (
        patch.object(wb, "preview_start_ms_from_waveform_x", return_value=120),
        patch.object(wb, "read_audio_duration_ms", return_value=500),
        patch.object(wb, "save_workbench_sample_cue") as mock_save,
    ):
        app._handle_loop_edit_waveform_click(80)

    mock_save.assert_not_called()
    assert app._loop_edit_pending_start_ms == 120
    assert "Loop-Start gesetzt: 120 ms" in app._status_var.value


def test_loop_edit_second_click_saves_loop_and_exits_mode(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.5, frequency_hz=440.0)
    app = _playback_app(loop_edit_mode=True)
    app._detail_row = _sample_row(wav)
    app._loop_edit_pending_start_ms = 100
    draw_calls: list[bool] = []
    app._draw_waveform = lambda _row: draw_calls.append(True)

    wb = _workbench_module()
    from src.workbench_library import WorkbenchCueMetadata

    existing = WorkbenchCueMetadata(cue_start_ms=20, attack_ms=40)

    with (
        patch.object(wb, "preview_start_ms_from_waveform_x", return_value=300),
        patch.object(wb, "load_workbench_sample_cue", return_value=existing),
        patch.object(wb, "save_workbench_sample_cue") as mock_save,
        patch.object(wb, "read_audio_duration_ms", return_value=500),
    ):
        app._handle_loop_edit_waveform_click(200)

    saved_metadata = mock_save.call_args[0][1]
    assert saved_metadata.loop_start_ms == 100
    assert saved_metadata.loop_end_ms == 300
    assert saved_metadata.cue_start_ms == 20
    assert saved_metadata.attack_ms == 40
    assert app._loop_edit_pending_start_ms is None
    assert app._loop_edit_mode_var.get() is False
    assert draw_calls == [True]
    assert "Loop gesetzt: 100–300 ms" in app._status_var.value


def test_loop_edit_second_click_sorts_when_reversed(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.5, frequency_hz=440.0)
    app = _playback_app(loop_edit_mode=True)
    app._detail_row = _sample_row(wav)
    app._loop_edit_pending_start_ms = 350
    app._draw_waveform = lambda _row: None

    wb = _workbench_module()
    from src.workbench_library import WorkbenchCueMetadata

    with (
        patch.object(wb, "preview_start_ms_from_waveform_x", return_value=150),
        patch.object(wb, "load_workbench_sample_cue", return_value=WorkbenchCueMetadata()),
        patch.object(wb, "save_workbench_sample_cue") as mock_save,
        patch.object(wb, "read_audio_duration_ms", return_value=500),
    ):
        app._handle_loop_edit_waveform_click(100)

    saved_metadata = mock_save.call_args[0][1]
    assert saved_metadata.loop_start_ms == 150
    assert saved_metadata.loop_end_ms == 350


def test_clear_loop_metadata_preserves_cue_and_attack(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.5, frequency_hz=440.0)
    app = _playback_app(loop_edit_mode=True)
    app._detail_row = _sample_row(wav)
    app._loop_edit_pending_start_ms = 99
    app._draw_waveform = lambda _row: None

    wb = _workbench_module()
    from src.workbench_library import WorkbenchCueMetadata

    existing = WorkbenchCueMetadata(
        cue_start_ms=25,
        attack_ms=60,
        loop_start_ms=100,
        loop_end_ms=400,
    )

    with (
        patch.object(wb, "load_workbench_sample_cue", return_value=existing),
        patch.object(wb, "save_workbench_sample_cue") as mock_save,
        patch.object(wb, "read_audio_duration_ms", return_value=500),
    ):
        app._clear_loop_metadata()

    saved_metadata = mock_save.call_args[0][1]
    assert saved_metadata.loop_start_ms is None
    assert saved_metadata.loop_end_ms is None
    assert saved_metadata.cue_start_ms == 25
    assert saved_metadata.attack_ms == 60
    assert app._loop_edit_pending_start_ms is None
    assert app._loop_edit_mode_var.get() is False
    assert app._status_var.value == "Loop gelöscht"


def test_loop_edit_mode_left_click_does_not_play(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.5, frequency_hz=440.0)
    app = _playback_app(loop_edit_mode=True)
    app._detail_row = _sample_row(wav)
    loop_called: list[int] = []

    monkeypatch_handle = lambda x: loop_called.append(x)
    app._handle_loop_edit_waveform_click = monkeypatch_handle

    app._on_waveform_click(SimpleNamespace(state=0, x=64))
    assert loop_called == [64]
    assert app._play_calls == []


def test_loop_edit_mode_shift_click_still_sets_cue(tmp_path: Path):
    app = _playback_app(loop_edit_mode=True)
    cue_called: list[int] = []

    app._set_selected_cue_from_waveform_position = lambda x: cue_called.append(x)
    app._on_waveform_click(SimpleNamespace(state=0x0001, x=55))
    assert cue_called == [55]
