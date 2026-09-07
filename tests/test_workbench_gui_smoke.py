"""Programmatic workbench GUI startup smoke — no display or audio output required."""

from __future__ import annotations

import threading
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.workbench import (
    PLAYLIST_ACTION_COLUMN,
    PLAYLIST_ACTION_LABEL,
    WAVEFORM_USAGE_HINT,
    WorkbenchApp,
    build_workbench_library_sources,
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


def _synthetic_row(name: str, *, pred_type: str = "Kick") -> WorkbenchRow:
    return WorkbenchRow(
        display_name=name,
        relative_path=f"synthetic/{name}",
        path=f"synthetic/{name}",
        bpm=128.0,
        key="Am",
        key_conf=0.9,
        loudness=-12.0,
        brightness=1000.0,
        sample_class="one_shot",
        pred_type=pred_type,
        status="ok",
        details={"duration_sec": "0.25"},
    )


def test_library_source_model_keeps_all_library_and_registered_folders_deterministic():
    """Source navigation exposes stable identities without host-specific paths."""
    sources = build_workbench_library_sources(
        ["synthetic/pack_a", "synthetic/pack_b"]
    )

    assert [(source.kind, source.path) for source in sources] == [
        ("all_library", "__workbench_all_library__"),
        ("catalog", "__workbench_catalog_readonly__"),
        ("folder", "synthetic/pack_a"),
        ("folder", "synthetic/pack_b"),
    ]
    assert sources[0].label == "Alle Samples"
    assert sources[2].label == "…/synthetic/pack_a"


def test_source_selection_uses_selected_folder_rows_without_preview_or_kit_mutation(
    tmp_path: Path, monkeypatch
):
    """A registered source switch is cache-only and makes the selected source authoritative."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(state_dir))
    folder_a = "synthetic/pack_a"
    folder_b = "synthetic/pack_b"
    rows_by_folder = {
        folder_a: [_synthetic_row("kick.wav"), _synthetic_row("bass.wav")],
        folder_b: [_synthetic_row("hat.wav")],
    }
    cached_loads: list[str] = []
    preview_dispatches: list[str] = []

    def load_cached(folder: Path) -> list[WorkbenchRow]:
        cached_loads.append(str(folder))
        return rows_by_folder[str(folder)]

    monkeypatch.setattr("src.workbench.load_cached_folder_rows", load_cached)
    root = tk.Tk()
    root.withdraw()
    try:
        app = WorkbenchApp(root)
        app._library_paths = ["__workbench_all_library__", "__workbench_catalog_readonly__", folder_a, folder_b]
        app._library_list.delete(0, tk.END)
        for label in ("Alle Samples", "Catalog", "…/synthetic/pack_a", "…/synthetic/pack_b"):
            app._library_list.insert(tk.END, label)
        kit_state = app._live_kit_state
        monkeypatch.setattr(app._preview, "play", lambda *_args, **_kwargs: preview_dispatches.append("preview"))

        app._library_list.selection_set(2)
        app._on_library_select()
        app._library_list.selection_clear(0, tk.END)
        app._library_list.selection_set(3)
        app._on_library_select()
        root.update_idletasks()

        assert cached_loads == [folder_a, folder_b]
        assert app._current_source_path == folder_b
        assert app._folder_var.get() == folder_b
        assert [row.display_name for row in app._rows] == ["hat.wav"]
        assert [row.display_name for row in app._visible_rows] == ["hat.wav"]
        assert app._live_kit_state is kit_state
        assert preview_dispatches == []
    finally:
        root.destroy()


def test_empty_source_selection_does_not_stop_an_active_preview(tmp_path: Path, monkeypatch):
    """Navigation is non-auditioning even when the selected cache source is empty."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(state_dir))
    empty_folder = "synthetic/empty_pack"
    monkeypatch.setattr("src.workbench.load_cached_folder_rows", lambda _folder: [])
    root = tk.Tk()
    root.withdraw()
    try:
        app = WorkbenchApp(root)
        app._library_paths = ["__workbench_all_library__", "__workbench_catalog_readonly__", empty_folder]
        app._library_list.delete(0, tk.END)
        for label in ("Alle Samples", "Catalog", "…/synthetic/empty_pack"):
            app._library_list.insert(tk.END, label)
        stopped: list[bool] = []
        monkeypatch.setattr(app, "_stop_preview", lambda: stopped.append(True))

        app._library_list.selection_set(2)
        app._on_library_select()

        assert app._current_source_path == empty_folder
        assert stopped == []
    finally:
        root.destroy()


def test_all_library_source_loads_cached_rows_from_each_registered_folder(
    tmp_path: Path, monkeypatch
):
    """All Library continues to use the existing aggregate cache seam."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(state_dir))
    all_rows = [_synthetic_row("kick.wav"), _synthetic_row("hat.wav")]
    monkeypatch.setattr("src.workbench.load_all_cached_rows", lambda: all_rows)
    root = tk.Tk()
    root.withdraw()
    try:
        app = WorkbenchApp(root)
        app._library_list.selection_set(0)
        app._on_library_select()

        assert app._current_source_path == "__workbench_all_library__"
        assert [row.display_name for row in app._rows] == ["kick.wav", "hat.wav"]
        assert [row.display_name for row in app._visible_rows] == ["kick.wav", "hat.wav"]
    finally:
        root.destroy()


def test_source_switch_reapplies_search_without_stale_rows_or_browser_selection(
    tmp_path: Path, monkeypatch
):
    """An active search is evaluated against B, not stale rows from source A."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(state_dir))
    folder_a = "synthetic/pack_a"
    folder_b = "synthetic/pack_b"
    rows_by_folder = {
        folder_a: [_synthetic_row("kick.wav")],
        folder_b: [_synthetic_row("hat.wav", pred_type="Hat")],
    }
    monkeypatch.setattr(
        "src.workbench.load_cached_folder_rows",
        lambda folder: rows_by_folder[str(folder)],
    )
    root = tk.Tk()
    root.withdraw()
    try:
        app = WorkbenchApp(root)
        app._library_paths = ["__workbench_all_library__", "__workbench_catalog_readonly__", folder_a, folder_b]
        app._library_list.delete(0, tk.END)
        for label in ("Alle Samples", "Catalog", "…/synthetic/pack_a", "…/synthetic/pack_b"):
            app._library_list.insert(tk.END, label)

        app._library_list.selection_set(2)
        app._on_library_select()
        app._filter_var.set("kick")
        root.update_idletasks()
        assert [row.display_name for row in app._visible_rows] == ["kick.wav"]
        app._tree.selection_set("0")

        app._library_list.selection_clear(0, tk.END)
        app._library_list.selection_set(3)
        app._on_library_select()
        root.update_idletasks()

        assert app._current_source_path == folder_b
        assert [row.display_name for row in app._rows] == ["hat.wav"]
        assert app._visible_rows == []
        assert app._tree.get_children() == ()
        assert app._tree.selection() == ()
    finally:
        root.destroy()


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
        assert not _widget_is_packed(app._view_bar)
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


def test_workbench_gui_startup_selects_live_kit_right_pane(tmp_path: Path, monkeypatch):
    """Fresh Tk startup must agree with the Live Kit presentation default."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(state_dir))

    root = tk.Tk()
    root.withdraw()
    try:
        app = WorkbenchApp(root)
        root.update_idletasks()

        assert app._right_pane.tab(app._right_pane.select(), "text") == "Live Kit"
        assert app._right_pane_presentation.active_view() == "Live Kit"
    finally:
        root.destroy()


def test_workbench_right_pane_round_trip_preserves_state_and_synchronizes_views(
    tmp_path: Path, monkeypatch
):
    """Actual notebook changes preserve owned surfaces and the Live Kit assignment."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(state_dir))
    row = WorkbenchRow(
        display_name="closed_hat_01.wav",
        relative_path="synthetic/closed_hat_01.wav",
        path="synthetic/closed_hat_01.wav",
        bpm=128.0,
        key="Am",
        key_conf=0.91,
        loudness=-13.5,
        brightness=3200.0,
        sample_class="one_shot",
        pred_type="Closed Hat",
        status="ok",
        details={"duration_sec": "0.25", "source": "synthetic"},
    )

    root = tk.Tk()
    root.withdraw()
    try:
        app = WorkbenchApp(root)
        app._live_kit_state.assign("Drums", "Closed Hat", row)
        detail_text = app._right_pane_presentation.detail_text
        detail_waveform = app._right_pane_presentation.detail_waveform
        edit_controls = app._right_pane_presentation.edit_controls
        live_kit_state = app._live_kit_state
        playlist_names = tuple(app._playlist_names)
        preview = app._preview
        transport_adapter = app._transport_adapter

        for tab, expected_view in (
            (app._live_kit_frame, "Live Kit"),
            (app._right_pane.tabs()[0], "Sample Details"),
            (app._live_kit_frame, "Live Kit"),
        ):
            app._right_pane.select(tab)
            root.update()
            assert app._right_pane.tab(app._right_pane.select(), "text") == expected_view
            assert app._right_pane_presentation.active_view() == expected_view

        assert app._right_pane_presentation.detail_text is detail_text
        assert app._right_pane_presentation.detail_waveform is detail_waveform
        assert app._right_pane_presentation.edit_controls is edit_controls
        assert app._live_kit_state is live_kit_state
        assert app._live_kit_state.assignment_for("Drums", "Closed Hat") is row
        assert tuple(app._playlist_names) == playlist_names
        assert app._preview is preview
        assert app._transport_adapter is transport_adapter
    finally:
        root.destroy()


def _descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from _descendants(child)


def test_live_kit_slot_exposes_compact_audition_affordance(tmp_path, monkeypatch):
    """Real Tk: the assigned slot button dispatches its exact row once."""
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path / "state"))
    assigned = _synthetic_row("assigned.wav", pred_type="OneShot")
    root = tk.Tk()
    root.withdraw()
    try:
        app = WorkbenchApp(root)
        app._live_kit_state.assign("Drums", "Main Drum", assigned)
        dispatched = []
        monkeypatch.setattr(
            app._preview,
            "play_row",
            lambda row, *, start_ms=0: (
                dispatched.append((row, start_ms))
                or SimpleNamespace(ok=True, message="")
            ),
        )
        app._refresh_live_kit_view()
        root.update_idletasks()

        slot_frames = [
            widget
            for widget in _descendants(app._live_kit_frame)
            if any(
                child.winfo_class() == "TLabel"
                and child.cget("text") == "Main Drum"
                for child in widget.winfo_children()
            )
        ]
        assert len(slot_frames) == 1
        audition_buttons = [
            child
            for child in slot_frames[0].winfo_children()
            if child.winfo_class() == "TButton" and child.cget("text") == "▶"
        ]
        assert len(audition_buttons) == 1

        assert bool(audition_buttons[0].invoke()) is True
        assert dispatched == [(assigned, 0)]
        assert app._live_kit_state.assignment_for("Drums", "Main Drum") is assigned
    finally:
        root.destroy()


def test_browser_add_to_kit_reveals_clicked_row_and_preserves_right_pane(
    tmp_path: Path, monkeypatch
):
    """Real Tk: stale selection, collapsed target, and Details -> Kit -> Details."""
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path / "state"))
    row_a = WorkbenchRow(
        display_name="sample_a.wav", relative_path="synthetic/sample_a.wav",
        path="synthetic/sample_a.wav", bpm=128.0, key="Am", key_conf=0.9,
        loudness=-12.0, brightness=1000.0, sample_class="one_shot",
        pred_type="Closed Hat", status="ok", details={"duration_sec": "0.25"},
    )
    row_b = replace(
        row_a, display_name="sample_b.wav", relative_path="synthetic/sample_b.wav",
        path="synthetic/sample_b.wav",
    )
    root = tk.Tk()
    root.withdraw()
    try:
        app = WorkbenchApp(root)
        # Keep this GUI routing contract independent of file/audio loading.
        monkeypatch.setattr(app, "_render_browser_rows", lambda: None)
        monkeypatch.setattr(app, "_selected_row", lambda: row_a)
        app._visible_rows = [row_a, row_b]
        app._live_kit_presentation.toggle_group("Drums")
        app._refresh_live_kit_view()
        details_tab = app._right_pane.tabs()[0]
        app._right_pane.select(details_tab)
        root.update()
        surfaces = (
            app._right_pane, app._live_kit_frame,
            app._right_pane_presentation.detail_text,
            app._right_pane_presentation.detail_waveform,
            app._right_pane_presentation.edit_controls,
        )
        playlist_calls = []
        previews = []
        monkeypatch.setattr(app, "_open_add_to_playlist_dialog", playlist_calls.append)
        monkeypatch.setattr(app, "_play_preview", lambda: previews.append("preview"))

        app._on_browser_canvas_click(SimpleNamespace(
            x=app._browser_canvas.winfo_width() - 1,
            y=app._browser_row_height_px + 1,
        ))
        root.update_idletasks()
        dialogs = [child for child in root.winfo_children() if isinstance(child, tk.Toplevel)]
        assert playlist_calls == [], "Browser Add must route to Live Kit, not Playlist"
        assert len(dialogs) == 1, "Browser Add must offer existing kit targets"
        dialog = dialogs[0]
        target = [
            widget for widget in _descendants(dialog)
            if widget.winfo_class() == "TButton"
            and widget.cget("text") == "Drums → Closed Hat"
        ]
        assert len(target) == 1
        target[0].invoke()
        root.update()

        assert not dialog.winfo_exists()
        assert root.grab_current() is None
        assert app._live_kit_state.assignment_for("Drums", "Closed Hat") is row_b
        assert not app._live_kit_presentation.is_collapsed("Drums")
        assert app._right_pane.tab(app._right_pane.select(), "text") == "Live Kit"
        assert app._right_pane_presentation.active_view() == "Live Kit"
        assert any(
            widget.winfo_class() == "TLabel" and widget.cget("text") == row_b.display_name
            for widget in _descendants(app._live_kit_frame)
        )
        assert previews == []
        assert playlist_calls == []

        app._right_pane.select(details_tab)
        root.update()
        assert app._right_pane_presentation.active_view() == "Sample Details"
        assert surfaces == (
            app._right_pane, app._live_kit_frame,
            app._right_pane_presentation.detail_text,
            app._right_pane_presentation.detail_waveform,
            app._right_pane_presentation.edit_controls,
        )
        assert all(widget.winfo_exists() for widget in surfaces)
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


def test_workbench_fresh_start_hides_advanced_sections_and_edit_menu_restores_toolbar(
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
        assert not _widget_is_packed(app._view_bar)
        assert app._show_search_var.get() is True
        assert app._show_filters_var.get() is False
        assert app._show_library_manage_var.get() is False
        assert app._show_waveform_tools_var.get() is False
        assert _widget_is_packed(app._filter_bar)
        assert not _widget_is_packed(app._structured_bar)
        assert not _widget_is_packed(app._lib_manage_btns)
        assert not _widget_is_packed(app._waveform_controls)

        app._show_view_toolbar_var.set(True)
        app._on_view_toolbar_toggled()
        root.update_idletasks()
        assert _widget_is_packed(app._view_bar)
        assert WORKBENCH_VIEW_TOGGLE_HELP in app._view_help_var.get()
    finally:
        root.destroy()


def test_workbench_restore_default_view_restores_minimal_screen1_view(
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
        app._show_view_toolbar_var.set(True)
        app._on_view_toolbar_toggled()
        app._show_search_var.set(False)
        app._on_view_section_toggled("search")
        app._show_filters_var.set(True)
        app._on_view_section_toggled("filters")
        app._show_library_manage_var.set(True)
        app._on_view_section_toggled("library_manage")
        app._show_waveform_tools_var.set(True)
        app._on_view_section_toggled("waveform_tools")
        root.update_idletasks()
        assert _widget_is_packed(app._view_bar)

        app._restore_default_view()
        root.update_idletasks()
        assert not _widget_is_packed(app._view_bar)
        assert app._show_search_var.get() is True
        assert app._show_filters_var.get() is False
        assert app._show_library_manage_var.get() is False
        assert app._show_waveform_tools_var.get() is False
        assert _widget_is_packed(app._filter_bar)
        assert not _widget_is_packed(app._structured_bar)
        assert not _widget_is_packed(app._lib_manage_btns)
        assert not _widget_is_packed(app._waveform_controls)
        assert load_workbench_view_settings(state_dir=state_dir) == WorkbenchViewSettings(
            show_view_toolbar=False,
            show_search=True,
            show_filters=False,
            show_library_manage=False,
            show_waveform_tools=False,
        )
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
