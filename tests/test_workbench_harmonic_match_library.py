"""Issue #532 contracts for the opt-in Screen-1 Harmonic Match Library."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk

import pytest

from src import workbench, workbench_harmony
from src.workbench import WorkbenchApp
from src.workbench_controller import WorkbenchResult, WorkbenchRow
from src.workbench_harmony import HarmonyRelation, HarmonySuggestion
from src.workbench_live_kit import LiveKitState
from src.workbench_visual_acceptance import (
    apply_screen1_visual_fixture,
    build_screen1_visual_fixture_v1,
)


def _row(
    name: str,
    *,
    bpm: float | None = 128.0,
    key: str | None = "Cmaj",
) -> WorkbenchRow:
    return WorkbenchRow(
        display_name=name,
        relative_path=f"synthetic/{name}.wav",
        path=f"synthetic/{name}.wav",
        bpm=bpm,
        key=key,
        key_conf=0.9 if key else None,
        loudness=-18.0,
        brightness=2400.0,
        sample_class="loop",
        pred_type="Synth Loop",
        status="ok",
        details={"source": "synthetic"},
    )


def _suggestion(
    row: WorkbenchRow,
    relation: HarmonyRelation,
    *,
    total: float,
    pitch: int | None = None,
    reason: str | None = None,
) -> HarmonySuggestion:
    return HarmonySuggestion(
        row=row,
        relation=relation,
        harmony_score={
            HarmonyRelation.DIRECT: 1.0,
            HarmonyRelation.RELATED: 0.7,
            HarmonyRelation.TRANSPOSE: 0.5,
            HarmonyRelation.UNCERTAIN: 0.0,
        }[relation],
        bpm_score=1.0,
        total_score=total,
        pitch_shift_semitones=pitch,
        explanation=reason or relation.value,
    )


def _controller(*, finder=None):
    surface = getattr(workbench_harmony, "HarmonicMatchLibraryController", None)
    if surface is None:
        pytest.fail("MISSING_PRODUCTION_SURFACE: HarmonicMatchLibraryController")
    return surface(finder=finder) if finder is not None else surface()


def test_explicit_anchor_calls_existing_finder_once_and_preserves_runtime_order_data():
    anchor = _row("anchor", key="Cmaj")
    direct = _suggestion(_row("direct", key="Cmaj"), HarmonyRelation.DIRECT, total=0.97)
    related = _suggestion(
        _row("related", key="Amin"),
        HarmonyRelation.RELATED,
        total=0.71,
        reason="Relative Dur/Moll",
    )
    transpose = _suggestion(
        _row("transpose", key="Dmaj"),
        HarmonyRelation.TRANSPOSE,
        total=0.58,
        pitch=-2,
        reason="Transpose -2",
    )
    calls: list[tuple[WorkbenchRow, list[WorkbenchRow]]] = []

    def finder(reference, candidates, **_kwargs):
        calls.append((reference, candidates))
        return [direct, related, transpose], None

    controller = _controller(finder=finder)
    controller.set_anchor(anchor, [anchor, direct.row, related.row, transpose.row])

    assert calls == [(anchor, [direct.row, related.row, transpose.row])]
    assert controller.anchor is anchor
    assert controller.results == (direct, related, transpose)
    assert controller.results[1].total_score == 0.71
    assert controller.results[1].explanation == "Relative Dur/Moll"


def test_match_only_policy_excludes_anchor_uncertain_and_out_of_contract_hints():
    anchor = _row("anchor")
    direct = _suggestion(anchor, HarmonyRelation.DIRECT, total=1.0)
    uncertain = _suggestion(_row("unknown", key=None), HarmonyRelation.UNCERTAIN, total=0.2)
    invalid_hint = _suggestion(
        _row("far", key="F#maj"), HarmonyRelation.TRANSPOSE, total=0.5, pitch=6
    )

    controller = _controller(
        finder=lambda *_args, **_kwargs: ([direct, uncertain, invalid_hint], None)
    )
    controller.set_anchor(anchor, [anchor, uncertain.row, invalid_hint.row])

    assert controller.results == ()
    assert "keine" in controller.status.casefold()


@pytest.mark.parametrize(
    "anchor",
    [
        _row("missing-bpm", bpm=None),
        _row("invalid-bpm", bpm=0),
        _row("nan-bpm", bpm=float("nan")),
        _row("positive-infinity-bpm", bpm=float("inf")),
        _row("negative-infinity-bpm", bpm=float("-inf")),
        _row("bad-key", key="???"),
    ],
)
def test_missing_or_invalid_anchor_evidence_fails_closed_without_calling_finder(anchor):
    calls: list[str] = []
    controller = _controller(
        finder=lambda *_args, **_kwargs: calls.append("finder") or ([], None)
    )

    controller.set_anchor(anchor, [_row("candidate")])

    assert calls == []
    assert controller.results == ()
    assert controller.status


def test_ordinary_selection_and_result_audition_never_change_anchor_or_refresh():
    anchor = _row("anchor")
    match = _suggestion(_row("match"), HarmonyRelation.DIRECT, total=1.0)
    calls: list[str] = []
    controller = _controller(
        finder=lambda *_args, **_kwargs: calls.append("refresh") or ([match], None)
    )
    controller.set_anchor(anchor, [match.row])

    controller.observe_selection(match.row)
    controller.observe_audition(match.row)

    assert controller.anchor is anchor
    assert calls == ["refresh"]


def test_each_explicit_anchor_change_refreshes_exactly_once():
    calls: list[str] = []
    controller = _controller(
        finder=lambda reference, *_args, **_kwargs: calls.append(reference.path)
        or ([], None)
    )

    controller.set_anchor(_row("first"), [_row("candidate")])
    controller.set_anchor(_row("second"), [_row("candidate")])

    assert calls == ["synthetic/first.wav", "synthetic/second.wav"]


def _widget_visible(widget) -> bool:
    return bool(widget.winfo_manager())


def _select_browser_row(app: WorkbenchApp, index: int) -> None:
    app._tree.selection_set(str(index))


def _column_contract(app: WorkbenchApp) -> tuple[tuple[int, int], ...]:
    return tuple(
        (
            int(app._body.grid_columnconfigure(index)["weight"]),
            int(app._body.grid_columnconfigure(index)["minsize"]),
        )
        for index in range(1, 4)
    )


def _descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from _descendants(child)


def _button_texts(widget) -> tuple[str, ...]:
    return tuple(
        str(child.cget("text"))
        for child in _descendants(widget)
        if isinstance(child, ttk.Button)
    )


def _recording_finder(calls):
    def finder(reference, candidates, **_kwargs):
        candidates = list(candidates)
        calls.append((reference, tuple(candidates)))
        return [
            _suggestion(row, HarmonyRelation.DIRECT, total=1.0 - index * 0.01)
            for index, row in enumerate(candidates)
        ], None

    return finder


@contextmanager
def _fresh_app(tmp_path: Path, monkeypatch):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(state_dir))
    root = tk.Tk()
    root.withdraw()
    try:
        app = WorkbenchApp(root)
        root.update_idletasks()
        yield root, app
    finally:
        root.destroy()


def test_match_library_is_absent_by_default_and_opens_between_browser_and_live_kit(
    tmp_path: Path, monkeypatch
):
    with _fresh_app(tmp_path, monkeypatch) as (root, app):
        anchor = _row("anchor")
        direct = _row("direct")
        app._populate_playlist(WorkbenchResult(summary={"ok": 2}, rows=[anchor, direct]))
        root.update_idletasks()

        assert not _widget_visible(app._harmonic_match_frame)
        assert app._center_notebook.grid_info()["column"] == 1
        assert app._right_pane.grid_info()["column"] == 2

        app._open_harmonic_match_library(anchor)
        root.update_idletasks()

        assert _widget_visible(app._harmonic_match_frame)
        assert app._harmonic_match_frame.grid_info()["column"] == 2
        assert app._right_pane.grid_info()["column"] == 3
        assert "anchor" in app._harmonic_match_anchor_var.get().casefold()
        assert app._harmonic_match_canvas.find_all()


def test_close_restores_three_panel_layout_without_losing_browser_or_live_kit(
    tmp_path: Path, monkeypatch
):
    with _fresh_app(tmp_path, monkeypatch) as (root, app):
        rows = [_row("anchor"), _row("direct")]
        app._populate_playlist(WorkbenchResult(summary={"ok": 2}, rows=rows))
        app._open_harmonic_match_library(rows[0])

        app._close_harmonic_match_library()
        root.update_idletasks()

        assert not _widget_visible(app._harmonic_match_frame)
        assert app._right_pane.grid_info()["column"] == 2
        assert app._browser_canvas.winfo_manager() == "pack"
        assert app._right_pane.tab(app._right_pane.select(), "text") == "Live Kit"


def test_harmonic_match_button_is_the_single_toggle_and_restores_layout_and_focus(
    tmp_path: Path, monkeypatch
):
    with _fresh_app(tmp_path, monkeypatch) as (root, app):
        rows = [_row("anchor"), _row("direct")]
        calls = []
        match_focus = []
        browser_focus = []
        app._harmonic_match_controller._finder = _recording_finder(calls)
        app._populate_playlist(WorkbenchResult(summary={"ok": 2}, rows=rows))
        _select_browser_row(app, 0)
        app._harmonic_match_canvas.focus_set = lambda: match_focus.append("match")
        app._browser_canvas.focus_set = lambda: browser_focus.append("browser")
        root.update_idletasks()

        assert app._harmonic_match_btn.cget("text") == "Harmonic Match"
        assert app._harmonic_match_btn.cget("style") == "HarmonicMatchInactive.TButton"
        assert _column_contract(app) == ((5, 560), (2, 300), (0, 0))

        app._harmonic_match_btn.invoke()
        root.update_idletasks()

        assert _widget_visible(app._harmonic_match_frame)
        assert app._harmonic_match_btn.cget("style") == "HarmonicMatchActive.TButton"
        assert app._harmonic_match_controller.anchor is rows[0]
        assert len(calls) == 1
        assert match_focus == ["match"]
        assert _column_contract(app) == ((4, 420), (3, 360), (2, 300))

        app._harmonic_match_btn.invoke()
        root.update_idletasks()

        assert not _widget_visible(app._harmonic_match_frame)
        assert app._harmonic_match_btn.cget("style") == "HarmonicMatchInactive.TButton"
        assert app._harmonic_match_controller.anchor is rows[0]
        assert len(calls) == 1
        assert browser_focus == ["browser"]
        assert _column_contract(app) == ((5, 560), (2, 300), (0, 0))
        assert app._right_pane.grid_info()["column"] == 2


def test_same_context_reopen_preserves_results_selection_and_scroll_without_refresh(
    tmp_path: Path, monkeypatch
):
    with _fresh_app(tmp_path, monkeypatch) as (root, app):
        rows = [_row("anchor"), *[_row(f"match-{index}") for index in range(12)]]
        calls = []
        app._harmonic_match_controller._finder = _recording_finder(calls)
        app._populate_playlist(WorkbenchResult(summary={"ok": len(rows)}, rows=rows))
        _select_browser_row(app, 0)

        app._harmonic_match_btn.invoke()
        root.update_idletasks()
        results = app._harmonic_match_controller.results
        app._harmonic_match_selected_index = 7
        app._harmonic_match_canvas.yview_moveto(0.5)
        root.update_idletasks()
        scroll = app._harmonic_match_canvas.yview()

        app._harmonic_match_btn.invoke()
        app._harmonic_match_btn.invoke()
        root.update_idletasks()

        assert len(calls) == 1
        assert app._harmonic_match_controller.results is results
        assert app._harmonic_match_selected_index == 7
        assert app._harmonic_match_canvas.yview() == pytest.approx(scroll)


def test_new_selected_anchor_recomputes_once_and_resets_match_view(
    tmp_path: Path, monkeypatch
):
    with _fresh_app(tmp_path, monkeypatch) as (root, app):
        rows = [_row("first"), _row("second"), _row("candidate")]
        calls = []
        app._harmonic_match_controller._finder = _recording_finder(calls)
        app._populate_playlist(WorkbenchResult(summary={"ok": 3}, rows=rows))
        _select_browser_row(app, 0)
        app._harmonic_match_btn.invoke()
        app._harmonic_match_selected_index = 1
        app._harmonic_match_canvas.yview_moveto(1.0)
        app._harmonic_match_btn.invoke()

        _select_browser_row(app, 1)
        app._harmonic_match_btn.invoke()
        root.update_idletasks()

        assert len(calls) == 2
        assert app._harmonic_match_controller.anchor is rows[1]
        assert app._harmonic_match_selected_index == 0
        assert app._harmonic_match_canvas.yview()[0] == pytest.approx(0.0)


@pytest.mark.parametrize("target", ["anchor", "candidate"])
@pytest.mark.parametrize(
    ("field", "value"),
    [("key", "Dmaj"), ("bpm", 130.0), ("display_name", "renamed")],
)
def test_matching_metadata_change_at_same_path_recomputes_once(
    tmp_path: Path, monkeypatch, target: str, field: str, value
):
    with _fresh_app(tmp_path, monkeypatch) as (_root, app):
        anchor = _row("anchor")
        candidate = _row("candidate")
        rows = [anchor, candidate]
        calls = []
        app._harmonic_match_controller._finder = _recording_finder(calls)
        app._populate_playlist(WorkbenchResult(summary={"ok": 2}, rows=rows))
        _select_browser_row(app, 0)
        app._harmonic_match_btn.invoke()
        app._harmonic_match_btn.invoke()

        setattr(anchor if target == "anchor" else candidate, field, value)
        app._harmonic_match_btn.invoke()

        assert len(calls) == 2


def test_nonfinite_bpm_fingerprint_is_stable_and_distinct(tmp_path: Path, monkeypatch):
    with _fresh_app(tmp_path, monkeypatch) as (_root, app):
        anchor = _row("anchor", bpm=float("nan"))
        candidate = _row("candidate")
        set_anchor_calls = []
        original = app._harmonic_match_controller.set_anchor

        def record_set_anchor(selected, candidates):
            set_anchor_calls.append(selected.bpm)
            original(selected, candidates)

        app._harmonic_match_controller.set_anchor = record_set_anchor
        app._populate_playlist(WorkbenchResult(summary={"ok": 2}, rows=[anchor, candidate]))
        _select_browser_row(app, 0)

        app._harmonic_match_btn.invoke()
        app._harmonic_match_btn.invoke()
        app._harmonic_match_btn.invoke()
        assert len(set_anchor_calls) == 1

        app._harmonic_match_btn.invoke()
        anchor.bpm = float("inf")
        app._harmonic_match_btn.invoke()
        assert len(set_anchor_calls) == 2

        app._harmonic_match_btn.invoke()
        anchor.bpm = float("-inf")
        app._harmonic_match_btn.invoke()
        assert len(set_anchor_calls) == 3


def test_candidate_reorder_does_not_refresh_same_context(tmp_path: Path, monkeypatch):
    with _fresh_app(tmp_path, monkeypatch) as (_root, app):
        rows = [_row("anchor"), _row("first"), _row("second")]
        calls = []
        app._harmonic_match_controller._finder = _recording_finder(calls)
        app._populate_playlist(WorkbenchResult(summary={"ok": 3}, rows=rows))
        _select_browser_row(app, 0)
        app._harmonic_match_btn.invoke()
        app._harmonic_match_btn.invoke()

        app._rows = [rows[0], rows[2], rows[1]]
        app._harmonic_match_btn.invoke()

        assert len(calls) == 1
        assert app._harmonic_match_controller.anchor is rows[0]


def test_no_browser_selection_keeps_match_closed_and_inactive(tmp_path: Path, monkeypatch):
    with _fresh_app(tmp_path, monkeypatch) as (_root, app):
        calls = []
        app._harmonic_match_controller._finder = _recording_finder(calls)
        app._populate_playlist(WorkbenchResult(summary={"ok": 1}, rows=[_row("row")]))
        app._tree.selection_remove(app._tree.selection())

        app._harmonic_match_btn.invoke()

        assert not _widget_visible(app._harmonic_match_frame)
        assert app._harmonic_match_btn.cget("style") == "HarmonicMatchInactive.TButton"
        assert calls == []


def test_match_panel_has_no_second_close_or_on_off_control(tmp_path: Path, monkeypatch):
    with _fresh_app(tmp_path, monkeypatch) as (_root, app):
        assert _button_texts(app._harmonic_match_frame) == ()


def test_repeated_toggles_keep_widget_identity_and_layout_stable(tmp_path: Path, monkeypatch):
    with _fresh_app(tmp_path, monkeypatch) as (root, app):
        rows = [_row("anchor"), _row("candidate")]
        app._populate_playlist(WorkbenchResult(summary={"ok": 2}, rows=rows))
        _select_browser_row(app, 0)
        widget_ids = tuple(str(widget) for widget in _descendants(app._harmonic_match_frame))

        for _ in range(4):
            app._harmonic_match_btn.invoke()
            root.update_idletasks()
            assert _column_contract(app) == ((4, 420), (3, 360), (2, 300))
            app._harmonic_match_btn.invoke()
            root.update_idletasks()
            assert _column_contract(app) == ((5, 560), (2, 300), (0, 0))

        assert tuple(str(widget) for widget in _descendants(app._harmonic_match_frame)) == widget_ids


def test_visual_fixture_opens_harmonic_state_through_real_button(tmp_path: Path, monkeypatch):
    with _fresh_app(tmp_path, monkeypatch) as (_root, app):
        fixture = build_screen1_visual_fixture_v1()
        invokes = []
        original = app._harmonic_match_btn.invoke

        def invoke():
            invokes.append("invoke")
            return original()

        app._harmonic_match_btn.invoke = invoke

        apply_screen1_visual_fixture(app, fixture, "screen1-harmonic-4panel")

        assert invokes == ["invoke"]
        assert _widget_visible(app._harmonic_match_frame)


def _interaction_app(anchor: WorkbenchRow, results: list[HarmonySuggestion]):
    app = WorkbenchApp.__new__(WorkbenchApp)
    app._harmonic_match_controller = SimpleNamespace(anchor=anchor, results=tuple(results))
    app._harmonic_match_selected_index = 0
    app._harmonic_match_canvas = SimpleNamespace(focus_set=lambda: None)
    return app


def test_match_waveform_click_auditions_exact_result_once_without_reanchoring():
    anchor = _row("anchor")
    result = _suggestion(_row("result"), HarmonyRelation.DIRECT, total=1.0)
    app = _interaction_app(anchor, [result])
    auditions: list[WorkbenchRow] = []
    app._audition_harmonic_match_row = auditions.append
    app._open_add_to_live_kit_dialog = lambda _row: pytest.fail("unexpected add")

    outcome = app._on_harmonic_match_canvas_click(
        SimpleNamespace(x=10, y=5), canvas_width=300, row_height=58
    )

    assert outcome == "break"
    assert auditions == [result.row]
    assert app._harmonic_match_controller.anchor is anchor


def test_match_add_routes_exact_result_through_existing_live_kit_path():
    anchor = _row("anchor")
    result = _suggestion(_row("result"), HarmonyRelation.DIRECT, total=1.0)
    app = _interaction_app(anchor, [result])
    assigned: list[WorkbenchRow] = []
    focus_restores = []

    def open_dialog(row, *, focus_restore=None):
        assigned.append(row)
        focus_restores.append(focus_restore)

    app._open_add_to_live_kit_dialog = open_dialog
    app._audition_harmonic_match_row = lambda _row: pytest.fail("unexpected audition")

    app._on_harmonic_match_canvas_click(
        SimpleNamespace(x=295, y=5), canvas_width=300, row_height=58
    )

    assert assigned == [result.row]
    assert focus_restores == [app._harmonic_match_canvas.focus_set]


class _DialogWidget:
    def __init__(self, parent=None, **options):
        self.parent = parent
        self.options = options
        self.children = []
        self.bindings = {}
        self.protocols = {}
        self.destroyed = False
        if parent is not None:
            parent.children.append(self)

    def title(self, _text):
        pass

    def configure(self, **_options):
        pass

    def transient(self, _parent):
        pass

    def resizable(self, *_args):
        pass

    def pack(self, **_options):
        pass

    def grab_set(self):
        pass

    def grab_release(self):
        pass

    def destroy(self):
        self.destroyed = True

    def focus_set(self):
        pass

    def bind(self, event, callback):
        self.bindings[event] = callback

    def protocol(self, event, callback):
        self.protocols[event] = callback

    def invoke(self):
        return self.options["command"]()


def _dialog_app(monkeypatch):
    app = WorkbenchApp.__new__(WorkbenchApp)
    app.root = _DialogWidget()
    app._live_kit_state = LiveKitState()
    browser_focus: list[str] = []
    app._browser_canvas = SimpleNamespace(
        focus_set=lambda: browser_focus.append("browser")
    )
    buttons = []

    def button(parent, **options):
        widget = _DialogWidget(parent, **options)
        buttons.append(widget)
        return widget

    monkeypatch.setattr(workbench.tk, "Toplevel", _DialogWidget)
    monkeypatch.setattr(workbench.ttk, "Frame", _DialogWidget)
    monkeypatch.setattr(workbench.ttk, "Label", _DialogWidget)
    monkeypatch.setattr(workbench.ttk, "Button", button)
    return app, browser_focus, buttons


def _cancel_button(buttons):
    return next(button for button in buttons if button.options.get("text") == "Abbrechen")


def test_add_to_kit_dialog_defaults_focus_restore_to_browser(monkeypatch):
    app, browser_focus, buttons = _dialog_app(monkeypatch)

    app._open_add_to_live_kit_dialog(_row("browser-result"))
    _cancel_button(buttons).invoke()

    assert browser_focus == ["browser"]


def test_match_add_dialog_restores_match_focus_and_keeps_arrow_navigation_local(
    monkeypatch,
):
    app, browser_focus, buttons = _dialog_app(monkeypatch)
    anchor = _row("anchor")
    results = [
        _suggestion(_row("first"), HarmonyRelation.DIRECT, total=1.0),
        _suggestion(_row("second"), HarmonyRelation.RELATED, total=0.7),
    ]
    match_focus: list[str] = []
    app._harmonic_match_controller = SimpleNamespace(
        anchor=anchor, results=tuple(results)
    )
    app._harmonic_match_selected_index = 0
    app._harmonic_match_canvas = SimpleNamespace(
        focus_set=lambda: match_focus.append("match")
    )
    auditions: list[WorkbenchRow] = []
    app._audition_harmonic_match_row = auditions.append
    app._render_harmonic_match_rows = lambda: None

    app._open_add_to_live_kit_dialog(
        results[0].row,
        focus_restore=app._harmonic_match_canvas.focus_set,
    )
    _cancel_button(buttons).invoke()
    outcome = app._route_harmonic_match_navigation("next")

    assert match_focus == ["match"]
    assert browser_focus == []
    assert outcome == "break"
    assert auditions == [results[1].row]


def test_match_arrow_navigation_is_local_deterministic_and_editable_safe():
    anchor = _row("anchor")
    results = [
        _suggestion(_row("first"), HarmonyRelation.DIRECT, total=1.0),
        _suggestion(_row("second"), HarmonyRelation.RELATED, total=0.7),
    ]
    app = _interaction_app(anchor, results)
    auditions: list[WorkbenchRow] = []
    app._audition_harmonic_match_row = auditions.append
    app._render_harmonic_match_rows = lambda: None

    native = app._route_harmonic_match_navigation("next", editable_focus=True)
    handled = app._route_harmonic_match_navigation("next", editable_focus=False)

    assert native is None
    assert handled == "break"
    assert app._harmonic_match_selected_index == 1
    assert auditions == [results[1].row]


def test_match_escape_reuses_existing_preview_stop_contract():
    app = WorkbenchApp.__new__(WorkbenchApp)
    calls: list[object] = []
    app._on_browser_escape = lambda event: calls.append(event) or "break"
    event = object()

    assert app._on_harmonic_match_escape(event) == "break"
    assert calls == [event]
