"""Slice-10 contracts for the producer-facing Screen-1 shell."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk

from src import workbench
from src.workbench import WorkbenchApp
from src.workbench_controller import (
    WorkbenchRow,
    WorkbenchViewSettings,
    save_workbench_view_settings,
)
from src.workbench_live_kit import (
    LIVE_KIT_SLOT_MAPPING,
    LiveKitPresentationState,
    LiveKitState,
)


EXPECTED_GROUPS = ("Kick + Bass", "Drums", "Melodic", "Atmos / FX")


def _row(name: str = "closed_hat_01.wav") -> WorkbenchRow:
    return WorkbenchRow(
        display_name=name,
        relative_path=f"synthetic/{name}",
        path=f"synthetic/{name}",
        bpm=132.0,
        key="Am",
        key_conf=0.91,
        loudness=-13.5,
        brightness=3200.0,
        sample_class="one_shot",
        pred_type="Closed Hat",
        status="ok",
        details={"duration_sec": "0.25", "source": "synthetic"},
    )


def _packed(widget) -> bool:
    try:
        widget.pack_info()
        return True
    except tk.TclError:
        return False


@contextmanager
def _fresh_app(tmp_path: Path, monkeypatch, *, settings=None):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(state_dir))
    if settings is not None:
        assert save_workbench_view_settings(settings, state_dir=state_dir)
    root = tk.Tk()
    root.withdraw()
    try:
        app = WorkbenchApp(root)
        root.update_idletasks()
        yield app
    finally:
        root.destroy()


def _menu_labels(menu) -> set[str]:
    end = menu.index("end")
    if end is None:
        return set()
    return {
        str(menu.entrycget(index, "label"))
        for index in range(int(end) + 1)
        if menu.type(index) != "separator"
    }


def _rgb(value: str) -> tuple[int, int, int]:
    normalized = value.removeprefix("#")
    assert len(normalized) == 6
    return tuple(int(normalized[index : index + 2], 16) for index in (0, 2, 4))


def test_fresh_default_hides_the_legacy_analysis_toolbar(tmp_path: Path, monkeypatch):
    with _fresh_app(tmp_path, monkeypatch) as app:
        assert not _packed(app._toolbar)
        assert app._show_legacy_toolbar_var.get() is False


def test_fresh_default_exposes_compact_product_and_transport_header(
    tmp_path: Path, monkeypatch
):
    with _fresh_app(tmp_path, monkeypatch) as app:
        assert _packed(app._shell_header)
        assert app._product_title.cget("text") == "Sample Brain"
        assert app._tempo_var.get().startswith("MASTER ")
        assert app._grid_var.get().startswith("GRID ")
        assert app._sync_control.cget("text") == "SYNC"
        assert app._transport_bar.master is app._shell_header_controls


def test_fresh_default_keeps_sources_browser_and_live_kit_visible(
    tmp_path: Path, monkeypatch
):
    with _fresh_app(tmp_path, monkeypatch) as app:
        assert app._library_list.winfo_manager() == "pack"
        assert app._browser_canvas.winfo_manager() == "pack"
        assert app._right_pane.tab(app._right_pane.select(), "text") == "Live Kit"
        assert app._right_pane_presentation.active_view() == "Live Kit"


def test_center_browser_has_the_largest_explicit_layout_weight(
    tmp_path: Path, monkeypatch
):
    with _fresh_app(tmp_path, monkeypatch) as app:
        weights = tuple(
            int(app._body.grid_columnconfigure(index)["weight"])
            for index in range(3)
        )
        assert weights == (0, 5, 2)


def test_structured_filters_and_library_management_are_hidden_by_default(
    tmp_path: Path, monkeypatch
):
    with _fresh_app(tmp_path, monkeypatch) as app:
        assert _packed(app._filter_bar)
        assert not _packed(app._structured_bar)
        assert not _packed(app._lib_manage_btns)


def test_engineering_tools_are_not_permanently_visible_in_the_center(
    tmp_path: Path, monkeypatch
):
    with _fresh_app(tmp_path, monkeypatch) as app:
        assert not _packed(app._center_tools_bar)
        assert not _packed(app._similar_panel)
        assert app._center_notebook.cget("style") == "Shell.TNotebook"
        assert app._center_notebook.tab(app._center_notebook.select(), "text") == "Samples"


def test_advanced_and_legacy_features_remain_reachable_from_tools(
    tmp_path: Path, monkeypatch
):
    with _fresh_app(tmp_path, monkeypatch) as app:
        labels = _menu_labels(app._tools_menu)
        assert {
            "Analyse & Aufnahme",
            "Browser-Werkzeuge",
            "Ähnliche Samples",
            "Sample Browser",
            "Harmonie-Finder",
            "Live Kit",
            "Sample Details",
        } <= labels


def test_complete_persisted_view_settings_remain_authoritative(
    tmp_path: Path, monkeypatch
):
    settings = WorkbenchViewSettings(
        show_view_toolbar=True,
        show_search=False,
        show_filters=True,
        show_library_manage=True,
        show_waveform_tools=True,
    )
    with _fresh_app(tmp_path, monkeypatch, settings=settings) as app:
        assert app._current_view_settings() == settings
        assert _packed(app._view_bar)
        assert not _packed(app._filter_bar)
        assert _packed(app._structured_bar)
        assert _packed(app._lib_manage_btns)
        assert _packed(app._waveform_controls)
        assert not _packed(app._toolbar)


def test_live_kit_default_uses_one_clear_active_group():
    presentation = LiveKitPresentationState(LiveKitState())

    assert presentation.active_group() == "Drums"
    assert presentation.is_collapsed("Drums") is False
    assert tuple(
        group
        for group in EXPECTED_GROUPS
        if not presentation.is_collapsed(group)
    ) == ("Drums",)


def test_live_kit_accordion_preserves_taxonomy_slots_and_assignment_state():
    state = LiveKitState()
    assigned = _row()
    state.assign("Drums", "Closed Hat", assigned)
    presentation = LiveKitPresentationState(state)

    assert presentation.toggle_group("Melodic") is False

    assert presentation.active_group() == "Melodic"
    assert presentation.is_collapsed("Drums") is True
    assert presentation.is_collapsed("Melodic") is False
    assert tuple((group, state.slots_for(group)) for group in state.groups()) == (
        LIVE_KIT_SLOT_MAPPING
    )
    assert state.assignment_for("Drums", "Closed Hat") is assigned


def test_live_kit_direct_assignment_semantics_remain_authoritative():
    state = LiveKitState()
    first = _row("first.wav")
    second = replace(first, display_name="second.wav", path="synthetic/second.wav")

    state.assign("Drums", "Closed Hat", first)
    state.assign("Drums", "Closed Hat", second)

    assert state.assignment_for("Drums", "Closed Hat") is second
    assert state.assignment_for("Drums", "Main Drum") is None


def test_source_selection_remains_non_auditioning_and_preserves_kit_state(monkeypatch):
    app = WorkbenchApp.__new__(WorkbenchApp)
    state = LiveKitState()
    assigned = _row()
    state.assign("Drums", "Closed Hat", assigned)
    app._live_kit_state = state
    app._busy = False
    app._playlist_library_mode = False
    app._selected_library_path = lambda: "synthetic/source_b"
    app._clear_playlist_list_selection = lambda: None
    app._folder_var = SimpleNamespace(set=lambda _value: None)
    app._load_cached_folder = lambda *_args, **_kwargs: None
    app._set_browser_context = lambda _value: None
    monkeypatch.setattr(workbench, "save_workbench_last_folder", lambda _path: True)
    previews: list[str] = []
    app._play_preview = lambda: previews.append("preview")

    app._on_library_select()

    assert previews == []
    assert state.assignment_for("Drums", "Closed Hat") is assigned


def test_browser_audition_and_add_to_kit_routes_remain_on_existing_seams():
    source = Path(workbench.__file__).read_text(encoding="utf-8")

    assert 'self._browser_canvas.bind("<Down>", self._on_browser_down)' in source
    assert 'self._browser_canvas.bind("<Up>", self._on_browser_up)' in source
    assert 'self._browser_canvas.bind("<Escape>", self._on_browser_escape)' in source
    assert "self._audition_browser_row(row, event_timestamp_ns=event_timestamp_ns)" in source
    assert "self._open_add_to_live_kit_dialog(row)" in source


def test_shell_composition_does_not_dispatch_preview_or_mutate_live_kit():
    class Surface:
        def __init__(self) -> None:
            self.visible = True

        def pack(self, **_kwargs) -> None:
            self.visible = True

        def pack_forget(self) -> None:
            self.visible = False

    app = WorkbenchApp.__new__(WorkbenchApp)
    app._toolbar = Surface()
    app._center_tools_bar = Surface()
    app._similar_panel = Surface()
    app._show_legacy_toolbar_var = SimpleNamespace(get=lambda: False)
    app._show_center_tools_var = SimpleNamespace(get=lambda: False)
    app._show_similar_var = SimpleNamespace(get=lambda: False)
    app._body = object()
    assigned = _row()
    app._live_kit_state = LiveKitState()
    app._live_kit_state.assign("Drums", "Closed Hat", assigned)
    preview_calls: list[str] = []
    app._preview = SimpleNamespace(play=lambda *_args, **_kwargs: preview_calls.append("play"))

    app._apply_shell_presentation()

    assert preview_calls == []
    assert app._live_kit_state.assignment_for("Drums", "Closed Hat") is assigned


def test_shell_palette_is_near_black_with_blood_red_intent_not_orange():
    for color in (workbench.BG_DARK, workbench.PANEL, workbench.PANEL_ALT):
        assert max(_rgb(color)) <= 30
    red, green, blue = _rgb(workbench.ACCENT)
    assert red >= 120 and red > green * 3 and red > blue * 1.25
    assert workbench.ACCENT.casefold() != "#ff4500"
    assert workbench.WAVEFORM_COLOR != workbench.ACCENT


def test_fresh_default_does_not_show_the_complete_technical_workbench(
    tmp_path: Path, monkeypatch
):
    with _fresh_app(tmp_path, monkeypatch) as app:
        assert not _packed(app._toolbar)
        assert not _packed(app._view_bar)
        assert not _packed(app._center_tools_bar)
        assert not _packed(app._structured_bar)
        assert not _packed(app._similar_panel)
        assert not _packed(app._waveform_controls)
        assert app._right_pane.cget("style") == "Shell.TNotebook"
