"""Programmatic workbench GUI startup smoke — no display or audio output required."""
from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from unittest.mock import patch

from src.workbench import WAVEFORM_USAGE_HINT, WorkbenchApp
from src.workbench_controller import (
    WORKBENCH_VIEW_TOGGLE_HELP,
    WorkbenchRow,
    load_workbench_analysis_limit,
    save_workbench_analysis_limit,
)


def test_workbench_gui_startup_smoke_constructs_key_widgets(tmp_path: Path):
    """WorkbenchApp builds without error and exposes core UI handles."""
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
        assert hasattr(app, "_show_search_var")
        assert hasattr(app, "_filter_bar")
        assert not hasattr(app, "_copy_path_btn")
        assert WORKBENCH_VIEW_TOGGLE_HELP in app._view_help_var.get()
        assert hasattr(app, "_folder_entry"), "folder path entry must exist"
        assert hasattr(app, "_cancel_btn"), "cancel button must exist"
        assert app._cancel_btn.instate(["disabled"])
        assert hasattr(app, "_fl_export_btn"), "fl export button must exist"
        assert app._fl_export_btn.instate(["disabled"])

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

        with patch("src.workbench.filedialog.askdirectory", return_value=str(dialog_folder)):
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
