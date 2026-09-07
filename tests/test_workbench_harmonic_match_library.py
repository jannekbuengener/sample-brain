"""Issue #532 contracts for the opt-in Screen-1 Harmonic Match Library."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk

import pytest

from src import workbench, workbench_harmony
from src.workbench import WorkbenchApp
from src.workbench_controller import WorkbenchResult, WorkbenchRow
from src.workbench_harmony import HarmonyRelation, HarmonySuggestion


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
    [_row("missing-bpm", bpm=None), _row("invalid-bpm", bpm=0), _row("bad-key", key="???")],
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
    app._open_add_to_live_kit_dialog = assigned.append
    app._audition_harmonic_match_row = lambda _row: pytest.fail("unexpected audition")

    app._on_harmonic_match_canvas_click(
        SimpleNamespace(x=295, y=5), canvas_width=300, row_height=58
    )

    assert assigned == [result.row]


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
