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


def _playback_app(*, canvas_width: int = 400, loop_edit_mode: bool = False, attack_edit_mode: bool = False):
    cls = _workbench_app_cls()
    app = cls.__new__(cls)
    app._busy = False
    app._detail_row = None
    app._preview_row_path = None
    app._status_var = SimpleNamespace(value="")
    app._loop_edit_pending_start_ms = None
    loop_mode = {"value": loop_edit_mode}
    attack_mode = {"value": attack_edit_mode}
    usage_values: list[str] = []

    app._loop_edit_mode_var = SimpleNamespace(
        get=lambda: loop_mode["value"],
        set=lambda value: loop_mode.__setitem__("value", bool(value)),
    )
    app._attack_edit_mode_var = SimpleNamespace(
        get=lambda: attack_mode["value"],
        set=lambda value: attack_mode.__setitem__("value", bool(value)),
    )
    app._waveform_usage_var = SimpleNamespace(
        set=lambda value: usage_values.append(str(value)),
    )
    app._usage_values = usage_values

    def _update_waveform_usage_hint() -> None:
        wb = _workbench_module()
        if app._loop_edit_mode_var.get():
            hint = wb.WAVEFORM_LOOP_EDIT_HINT
        elif app._attack_edit_mode_var.get():
            hint = wb.WAVEFORM_ATTACK_EDIT_HINT
        else:
            hint = wb.WAVEFORM_USAGE_HINT
        app._waveform_usage_var.set(hint)

    app._update_waveform_usage_hint = _update_waveform_usage_hint

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


def test_waveform_attack_edit_hint_documents_mode_controls():
    wb = _workbench_module()
    hint = wb.WAVEFORM_ATTACK_EDIT_HINT
    assert "Attack-Modus" in hint
    assert "Attack vorschlagen" in hint
    assert "Attack löschen" in hint


def test_update_waveform_usage_hint_switches_to_attack_mode():
    wb = _workbench_module()
    app = _playback_app()
    usage_values: list[str] = []
    app._waveform_usage_var = SimpleNamespace(
        set=lambda value: usage_values.append(str(value)),
    )

    app._attack_edit_mode_var.set(True)
    app._update_waveform_usage_hint()
    assert usage_values[-1] == wb.WAVEFORM_ATTACK_EDIT_HINT


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


def test_attack_edit_mode_toggle_disables_loop_mode():
    app = _playback_app()
    app._loop_edit_mode_var.set(True)
    app._attack_edit_mode_var.set(True)
    app._on_attack_edit_mode_toggled()
    assert app._loop_edit_mode_var.get() is False
    assert "Attack bearbeiten aktiv" in app._status_var.value


def test_loop_edit_mode_toggle_disables_attack_mode():
    app = _playback_app()
    app._attack_edit_mode_var.set(True)
    app._loop_edit_mode_var.set(True)
    app._on_loop_edit_mode_toggled()
    assert app._attack_edit_mode_var.get() is False
    assert "Loop bearbeiten aktiv" in app._status_var.value


def test_attack_edit_click_saves_attack_and_exits_mode(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.5, frequency_hz=440.0)
    app = _playback_app(attack_edit_mode=True)
    app._detail_row = _sample_row(wav)
    draw_calls: list[bool] = []
    app._draw_waveform = lambda _row: draw_calls.append(True)

    wb = _workbench_module()
    from src.workbench_library import WorkbenchCueMetadata

    existing = WorkbenchCueMetadata(
        cue_start_ms=30,
        loop_start_ms=100,
        loop_end_ms=400,
    )

    with (
        patch.object(wb, "preview_start_ms_from_waveform_x", return_value=180),
        patch.object(wb, "load_workbench_sample_cue", return_value=existing),
        patch.object(wb, "save_workbench_sample_cue") as mock_save,
        patch.object(wb, "read_audio_duration_ms", return_value=500),
    ):
        app._handle_attack_edit_waveform_click(120)

    saved_metadata = mock_save.call_args[0][1]
    assert saved_metadata.attack_ms == 180
    assert saved_metadata.cue_start_ms == 30
    assert saved_metadata.loop_start_ms == 100
    assert saved_metadata.loop_end_ms == 400
    assert app._attack_edit_mode_var.get() is False
    assert draw_calls == [True]
    assert "Attack gesetzt: 180 ms" in app._status_var.value


def test_clear_attack_metadata_preserves_cue_and_loop(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.5, frequency_hz=440.0)
    app = _playback_app(attack_edit_mode=True)
    app._detail_row = _sample_row(wav)
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
        app._clear_attack_metadata()

    saved_metadata = mock_save.call_args[0][1]
    assert saved_metadata.attack_ms is None
    assert saved_metadata.cue_start_ms == 25
    assert saved_metadata.loop_start_ms == 100
    assert app._attack_edit_mode_var.get() is False
    assert app._status_var.value == "Attack gelöscht"


def test_attack_edit_mode_left_click_does_not_play(tmp_path: Path):
    app = _playback_app(attack_edit_mode=True)
    attack_called: list[int] = []
    app._handle_attack_edit_waveform_click = lambda x: attack_called.append(x)
    app._on_waveform_click(SimpleNamespace(state=0, x=90))
    assert attack_called == [90]
    assert app._play_calls == []


def _suggest_app(tmp_path: Path):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.25, frequency_hz=440.0)
    row = _sample_row(wav)
    app = _playback_app()
    app._detail_row = row
    apply_states: list[str] = []
    app._attack_suggest_apply_btn = SimpleNamespace(
        state=lambda args: apply_states.append(str(args)),
    )
    app._apply_states = apply_states
    return app, wav


def test_suggest_attack_metadata_sets_pending_without_saving(tmp_path: Path, monkeypatch):
    from src.workbench_attack_suggest import AttackSuggestion

    app, _wav = _suggest_app(tmp_path)
    suggestion = AttackSuggestion(
        attack_ms=42,
        method="energy_threshold",
        confidence="medium",
        reason="test",
    )
    monkeypatch.setattr(
        "src.workbench.suggest_attack_ms",
        lambda _path: suggestion,
    )
    saved: list[object] = []
    monkeypatch.setattr("src.workbench.save_workbench_sample_cue", lambda *a, **k: saved.append(a))

    app._suggest_attack_metadata()

    assert app._pending_attack_suggestion == suggestion
    assert "42 ms" in app._status_var.value
    assert saved == []
    assert app._apply_states[-1] == "['!disabled']"


def test_apply_attack_suggestion_persists_attack_ms(tmp_path: Path, monkeypatch):
    from src.workbench_attack_suggest import AttackSuggestion
    from src.workbench_controller import WorkbenchCueMetadata

    app, wav = _suggest_app(tmp_path)
    app._pending_attack_suggestion = AttackSuggestion(
        attack_ms=55,
        method="energy_threshold",
        confidence="high",
        reason="test",
    )
    existing = WorkbenchCueMetadata(cue_start_ms=10, attack_ms=None)
    monkeypatch.setattr("src.workbench.load_workbench_sample_cue", lambda _path: existing)
    saved: list[WorkbenchCueMetadata] = []
    monkeypatch.setattr(
        "src.workbench.save_workbench_sample_cue",
        lambda _path, metadata, **kwargs: saved.append(metadata),
    )
    redrawn: list[object] = []
    app._draw_waveform = lambda row: redrawn.append(row)
    app._update_waveform_usage_hint = lambda: None

    app._apply_attack_suggestion()

    assert len(saved) == 1
    assert saved[0].attack_ms == 55
    assert saved[0].cue_start_ms == 10
    assert app._pending_attack_suggestion is None
    assert "übernommen" in app._status_var.value.lower()
    assert redrawn == [app._detail_row]


def test_play_loop_repeat_invokes_preview_region_loop(tmp_path: Path, monkeypatch):
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.4, frequency_hz=440.0)
    row = _sample_row(wav)
    app = _playback_app()
    app._detail_row = row
    calls: list[tuple[int, int]] = []

    def fake_play_region_loop(_path, *, start_ms, end_ms):
        calls.append((start_ms, end_ms))
        return PreviewResult(ok=True)

    app._preview = SimpleNamespace(play_region_loop=fake_play_region_loop)
    monkeypatch.setattr(
        "src.workbench.load_workbench_sample_cue",
        lambda _path: SimpleNamespace(loop_start_ms=50.0, loop_end_ms=200.0),
    )
    app._play_loop_repeat()
    assert calls == [(50, 200)]
    assert "wiederholung aktiv" in app._status_var.value.lower()
