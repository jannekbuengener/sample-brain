"""Programmatic workbench GUI startup smoke — no display or audio output required."""
from __future__ import annotations

import tkinter as tk

from src.workbench import WAVEFORM_USAGE_HINT, WorkbenchApp
from src.workbench_controller import WORKBENCH_VIEW_TOGGLE_HELP


def test_workbench_gui_startup_smoke_constructs_key_widgets():
    """WorkbenchApp builds without error and exposes core UI handles."""
    root = tk.Tk()
    root.withdraw()
    try:
        app = WorkbenchApp(root)
        root.update_idletasks()

        assert hasattr(app, "_library_list"), "library folder list must exist"
        assert hasattr(app, "_waveform_canvas"), "waveform canvas must exist"
        assert WAVEFORM_USAGE_HINT in app._waveform_usage_var.get()
        assert hasattr(app, "_loop_edit_mode_var")
        assert hasattr(app, "_attack_edit_mode_var")
        assert hasattr(app, "_attack_suggest_apply_btn")
        assert hasattr(app, "_tree"), "playlist tree must exist"
        assert hasattr(app, "_show_search_var")
        assert hasattr(app, "_filter_bar")
        assert not hasattr(app, "_copy_path_btn")
        assert WORKBENCH_VIEW_TOGGLE_HELP in app._view_help_var.get()
    finally:
        root.destroy()
