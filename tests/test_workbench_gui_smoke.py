"""Programmatic workbench GUI startup smoke — no display or audio output required."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from unittest.mock import patch

from src.workbench import (
    PLAYLIST_ACTION_COLUMN,
    PLAYLIST_ACTION_LABEL,
    WAVEFORM_USAGE_HINT,
    WorkbenchApp,
)
from src.workbench_controller import (
    FILTER_ALL_LABEL,
    WORKBENCH_VIEW_TOGGLE_HELP,
    WorkbenchResult,
    WorkbenchRow,
    format_workbench_view_toolbar_hidden_status,
    format_workbench_view_toolbar_shown_status,
    load_workbench_analysis_limit,
    load_workbench_view_settings,
    save_workbench_analysis_limit,
    save_workbench_view_settings,
    workbench_filter_options,
    WorkbenchViewSettings,
)


def _widget_is_packed(widget: tk.Misc) -> bool:
    try:
        widget.pack_info()
        return True
    except tk.TclError:
        return False


def test_workbench_gui_startup_smoke_constructs_key_widgets(
    tmp_path: Path, monkeypatch
):
    """WorkbenchApp builds without error and exposes core UI handles."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(state_dir))
    folder = tmp_path / "samples"
    folder.mkdir()
    dialog_folder = tmp_path / "dialog_samples"
    dialog_folder.mkdir()

    root = tk.Tk()
    root.withdraw()
    try:
        app = WorkbenchApp(root)
        root.update_idletasks()

        assert hasattr(app, "_library_list"), "library folder list must exist"
        assert hasattr(app, "_waveform_canvas"), "waveform canvas must exist"
        assert hasattr(app, "_provenance_label"), "metadata provenance label must exist"
        assert hasattr(app, "_provenance_var"), "metadata provenance var must exist"
        assert WAVEFORM_USAGE_HINT in app._waveform_usage_var.get()
        assert hasattr(app, "_loop_edit_mode_var")
        assert hasattr(app, "_attack_edit_mode_var")
        assert hasattr(app, "_attack_suggest_apply_btn")
        assert hasattr(app, "_play_btn"), "play button must exist"
        assert hasattr(app, "_stop_btn"), "stop button must exist"
        assert app._play_btn.instate(["disabled"])
        assert app._stop_btn.instate(["disabled"])
        assert hasattr(app, "_tree"), "playlist tree must exist"
        assert PLAYLIST_ACTION_COLUMN in app._tree["columns"]
        assert hasattr(app, "_open_add_to_playlist_dialog")
        assert hasattr(app, "_playlist_list"), "playlist sidebar list must exist"
        assert hasattr(app, "_load_playlist_samples")
        assert hasattr(app, "_show_search_var")
        assert hasattr(app, "_show_view_toolbar_var")
        assert hasattr(app, "_view_bar")
        assert _widget_is_packed(app._view_bar)
        assert hasattr(app, "_filter_bar")
        assert not hasattr(app, "_copy_path_btn")
        assert WORKBENCH_VIEW_TOGGLE_HELP in app._view_help_var.get()
        assert hasattr(app, "_folder_entry"), "folder path entry must exist"
        assert hasattr(app, "_cancel_btn"), "cancel button must exist"
        assert app._cancel_btn.instate(["disabled"])
        assert hasattr(app, "_fl_export_btn"), "fl export button must exist"
        assert app._fl_export_btn.instate(["disabled"])
        assert hasattr(app, "_catalog_import_btn"), "catalog import button must exist"
        assert app._catalog_import_btn.instate(["disabled"])
        assert hasattr(app, "_similar_btn"), "similar samples button must exist"
        assert hasattr(app, "_similar_tree"), "similar samples tree must exist"
        assert app._similar_btn.instate(["disabled"])

        app._folder_var.set(str(folder))
        started = threading.Event()

        def fake_run_analysis(folder_path: Path, limit: int | None) -> None:
            started.set()

        with patch.object(app, "_run_analysis", side_effect=fake_run_analysis):
            app._start_analysis()
            root.update_idletasks()
            assert started.wait(timeout=2.0), "analysis thread should start"
            assert app._cancel_btn.instate(["!disabled"])
            assert app._analyze_btn.instate(["disabled"])
            app._cancel_analysis()
            root.update_idletasks()
            assert app._cancel_event.is_set()

        app._busy = False
        app._cancel_event.clear()
        app._analyze_btn.state(["!disabled"])
        app._cancel_btn.state(["disabled"])

        with patch(
            "src.workbench.filedialog.askdirectory", return_value=str(dialog_folder)
        ):
            app._pick_folder()
            root.update_idletasks()
        assert app._folder_var.get() == str(dialog_folder)
    finally:
        root.destroy()


def test_workbench_restores_persisted_analysis_limit(tmp_path: Path, monkeypatch):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(state_dir))
    assert save_workbench_analysis_limit("25", state_dir=state_dir)
    assert load_workbench_analysis_limit(state_dir=state_dir) == "25"

    root = tk.Tk()
    root.withdraw()
    try:
        app = WorkbenchApp(root)
        root.update_idletasks()
        assert app._limit_var.get() == "25"
    finally:
        root.destroy()


def test_workbench_populate_playlist_updates_structured_filter_options(tmp_path: Path):
    """Regression: playlist population must refresh type/key filter combos."""
    sample = tmp_path / "kick.wav"
    sample.write_bytes(b"data")
    row = WorkbenchRow(
        display_name="kick",
        relative_path="kick.wav",
        path=str(sample),
        bpm=128.0,
        key="Am",
        key_conf=0.8,
        loudness=-20.0,
        brightness=2000.0,
        sample_class="loop",
        pred_type="Kick",
        status="ok",
        details={"duration_sec": "2.5"},
    )

    root = tk.Tk()
    root.withdraw()
    try:
        app = WorkbenchApp(root)
        options = workbench_filter_options([row])
        app._populate_playlist(WorkbenchResult(summary={"ok": 1}, rows=[row]))
        root.update_idletasks()
        assert app._type_filter_combo["values"] == (FILTER_ALL_LABEL, *options["types"])
        assert app._key_filter_combo["values"] == (FILTER_ALL_LABEL, *options["keys"])
    finally:
        root.destroy()


def test_workbench_fl_export_button_enables_with_exportable_rows(tmp_path: Path):
    sample = tmp_path / "kick.wav"
    sample.write_bytes(b"data")
    row = WorkbenchRow(
        display_name="kick",
        relative_path="kick.wav",
        path=str(sample),
        bpm=128.0,
        key="Am",
        key_conf=0.8,
        loudness=-20.0,
        brightness=2000.0,
        sample_class="loop",
        pred_type="Kick",
        status="ok",
        details={"duration_sec": "2.5"},
    )

    root = tk.Tk()
    root.withdraw()
    try:
        app = WorkbenchApp(root)
        app._rows = [row]
        app._refresh_playlist_view()
        root.update_idletasks()
        assert app._fl_export_btn.instate(["!disabled"])
    finally:
        root.destroy()


def test_workbench_playlist_action_column_shows_add_label(tmp_path: Path):
    sample = tmp_path / "kick.wav"
    sample.write_bytes(b"data")
    row = WorkbenchRow(
        display_name="kick",
        relative_path="kick.wav",
        path=str(sample),
        bpm=128.0,
        key="Am",
        key_conf=0.8,
        loudness=-20.0,
        brightness=2000.0,
        sample_class="loop",
        pred_type="Kick",
        status="ok",
    )

    root = tk.Tk()
    root.withdraw()
    try:
        app = WorkbenchApp(root)
        app._populate_playlist(WorkbenchResult(summary={"ok": 1}, rows=[row]))
        root.update_idletasks()
        values = app._tree.item("0", "values")
        assert values[-1] == PLAYLIST_ACTION_LABEL
    finally:
        root.destroy()


def test_workbench_playlist_action_click_opens_dialog(tmp_path: Path):
    sample = tmp_path / "kick.wav"
    sample.write_bytes(b"data")
    row = WorkbenchRow(
        display_name="kick",
        relative_path="kick.wav",
        path=str(sample),
        bpm=128.0,
        key="Am",
        key_conf=0.8,
        loudness=-20.0,
        brightness=2000.0,
        sample_class="loop",
        pred_type="Kick",
        status="ok",
    )

    root = tk.Tk()
    root.withdraw()
    try:
        app = WorkbenchApp(root)
        app._populate_playlist(WorkbenchResult(summary={"ok": 1}, rows=[row]))
        root.update_idletasks()
        opened: list[WorkbenchRow] = []

        def capture_dialog(target: WorkbenchRow) -> None:
            opened.append(target)

        with patch.object(app._tree, "identify_region", return_value="cell"):
            with patch.object(
                app, "_column_id_at_x", return_value=PLAYLIST_ACTION_COLUMN
            ):
                with patch.object(app, "_row_at_tree_event", return_value=row):
                    with patch.object(
                        app, "_open_add_to_playlist_dialog", side_effect=capture_dialog
                    ):
                        app._on_tree_click(type("E", (), {"x": 1, "y": 1})())
        assert opened == [row]
    finally:
        root.destroy()


def test_workbench_playlist_select_loads_rows(tmp_path: Path, monkeypatch):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(state_dir))
    from src.workbench_library import (
        add_sample_to_playlist,
        create_playlist,
        workbench_library_db_path,
    )

    sample = tmp_path / "kick.wav"
    sample.write_bytes(b"data")
    db_path = workbench_library_db_path(state_dir=state_dir)
    playlist = create_playlist("Song A", db_path=db_path)
    add_sample_to_playlist(playlist.id, sample, db_path=db_path)

    root = tk.Tk()
    root.withdraw()
    try:
        app = WorkbenchApp(root)
        root.update_idletasks()
        assert app._playlist_list.size() == 1
        app._playlist_list.selection_set(0)
        loaded: list[str] = []

        def capture_load(name: str) -> None:
            loaded.append(name)

        with patch.object(app, "_load_playlist_samples", side_effect=capture_load):
            app._on_playlist_select()
        assert loaded == ["Song A"]
    finally:
        root.destroy()


def test_workbench_view_toolbar_hidden_via_edit_menu(tmp_path: Path, monkeypatch):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(state_dir))
    root = tk.Tk()
    root.withdraw()
    try:
        app = WorkbenchApp(root)
        root.update_idletasks()
        assert _widget_is_packed(app._view_bar)

        app._show_view_toolbar_var.set(False)
        app._on_view_toolbar_toggled()
        root.update_idletasks()
        assert not _widget_is_packed(app._view_bar)
        assert app._show_search_var.get() is True
        assert _widget_is_packed(app._filter_bar)

        app._show_view_toolbar_var.set(True)
        app._on_view_toolbar_toggled()
        root.update_idletasks()
        assert _widget_is_packed(app._view_bar)
        assert WORKBENCH_VIEW_TOGGLE_HELP in app._view_help_var.get()
    finally:
        root.destroy()


def test_workbench_restore_default_view_shows_toolbar_and_sections(
    tmp_path: Path, monkeypatch
):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(state_dir))
    root = tk.Tk()
    root.withdraw()
    try:
        app = WorkbenchApp(root)
        root.update_idletasks()
        app._show_view_toolbar_var.set(False)
        app._on_view_toolbar_toggled()
        app._show_search_var.set(False)
        app._on_view_section_toggled("search")
        root.update_idletasks()
        assert not _widget_is_packed(app._view_bar)

        app._restore_default_view()
        root.update_idletasks()
        assert _widget_is_packed(app._view_bar)
        assert app._show_search_var.get() is True
        assert _widget_is_packed(app._filter_bar)
    finally:
        root.destroy()


def test_workbench_similar_suggestions_panel_populates(tmp_path: Path):
    ref = tmp_path / "ref.wav"
    match = tmp_path / "match.wav"
    ref.write_bytes(b"data")
    match.write_bytes(b"data")
    reference = WorkbenchRow(
        display_name="ref",
        relative_path="ref.wav",
        path=str(ref),
        bpm=128.0,
        key="Am",
        key_conf=0.8,
        loudness=-20.0,
        brightness=2000.0,
        sample_class="loop",
        pred_type="kick",
        status="ok",
    )
    similar = WorkbenchRow(
        display_name="match",
        relative_path="match.wav",
        path=str(match),
        bpm=128.0,
        key="Am",
        key_conf=0.8,
        loudness=-20.0,
        brightness=2000.0,
        sample_class="loop",
        pred_type="kick",
        status="ok",
    )

    root = tk.Tk()
    root.withdraw()
    try:
        app = WorkbenchApp(root)
        app._populate_playlist(
            WorkbenchResult(summary={"ok": 2}, rows=[reference, similar]),
        )
        app._tree.selection_set("0")
        app._set_detail(reference)
        root.update_idletasks()
        app._refresh_similar_suggestions()
        root.update_idletasks()
        assert app._similar_tree.get_children()
        values = app._similar_tree.item("0", "values")
        assert values[0] == "match"
        assert values[5]  # score column non-empty
    finally:
        root.destroy()


def test_workbench_restores_persisted_view_toolbar_setting(tmp_path: Path, monkeypatch):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(state_dir))
    settings = WorkbenchViewSettings(show_view_toolbar=False)
    assert save_workbench_view_settings(settings, state_dir=state_dir)
    assert load_workbench_view_settings(state_dir=state_dir).show_view_toolbar is False

    root = tk.Tk()
    root.withdraw()
    try:
        app = WorkbenchApp(root)
        root.update_idletasks()
        assert app._show_view_toolbar_var.get() is False
        assert not _widget_is_packed(app._view_bar)
    finally:
        root.destroy()


def test_workbench_harmony_finder_tab_populates(tmp_path: Path, monkeypatch):
    """Issue #213: Harmonie-Finder tab builds and finds matches from loaded rows."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(state_dir))

    ref = tmp_path / "ref.wav"
    match = tmp_path / "match.wav"
    ref.write_bytes(b"data")
    match.write_bytes(b"data")
    reference = WorkbenchRow(
        display_name="ref",
        relative_path="ref.wav",
        path=str(ref),
        bpm=128.0,
        key="Cmaj",
        key_conf=0.8,
        loudness=-20.0,
        brightness=2000.0,
        sample_class="loop",
        pred_type="kick",
        status="ok",
    )
    direct = WorkbenchRow(
        display_name="match",
        relative_path="match.wav",
        path=str(match),
        bpm=128.0,
        key="Cmaj",
        key_conf=0.8,
        loudness=-20.0,
        brightness=2000.0,
        sample_class="loop",
        pred_type="kick",
        status="ok",
    )

    root = tk.Tk()
    root.withdraw()
    try:
        app = WorkbenchApp(root)
        root.update_idletasks()
        assert hasattr(app, "_center_notebook"), "center notebook must exist"
        assert hasattr(app, "_harmony_frame"), "harmony finder tab must exist"
        assert hasattr(app, "_harmony_tree"), "harmony results tree must exist"
        assert hasattr(app, "_harmony_ref_combo"), "harmony reference combo must exist"

        app._populate_playlist(
            WorkbenchResult(summary={"ok": 2}, rows=[reference, direct])
        )
        root.update_idletasks()
        assert app._harmony_tree.get_children(), "harmony matches should populate"
        values = app._harmony_tree.item("0", "values")
        assert values[0] == "match"
        assert values[1] == "Direkt"
    finally:
        root.destroy()
