"""#843 Context Harmonic Matches open/retarget — frozen contracts.

Canon:
- docs/WORKBENCH_SAMPLE_CONTEXT_MENU_CONTRACT.md
- docs/product/02_HARMONIC_RHYTHMIC_MATCHING_SPEC.md §9.1–§9.2
- docs/WORKBENCH_ELASTIC_LAYOUT.md (#845 collapse ownership)

Parent: #841. Dependencies delivered: #839, #840, #842, #845.
Related UX meta: #838.

TEST_FREEZE: assertions below express the intended #843 behaviour.
Do not weaken matching/#842 contracts to fit a broken panel bind.
Do not repair matching domain if #842 tests go red.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from src.workbench_controller import WorkbenchKeyAnalysisClaim, WorkbenchRow
from src.workbench_harmony import (
    HarmonicMatchLibraryController,
    find_harmony_matches,
)
from src.workbench_qml import QML_SOURCE, Screen1QmlInteractionAdapter
from src.workbench_qml_spike import build_qml_view_model_from_fixture
from src.workbench_session import compose_workbench_session
from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1

_WORKBENCH_QML_PY = Path(__file__).resolve().parents[1] / "src" / "workbench_qml.py"
_INELIGIBLE_STATUS = "Harmonic Match benötigt einen auswertbaren Referenz-Key."


def _claim(**kwargs) -> WorkbenchKeyAnalysisClaim:
    base = dict(
        key="Gmaj",
        mode="maj",
        contract_version=2,
        valid=True,
        matching_eligible=False,
        root_evidence_kind="joint_24_profile_pearson",
        mode_evidence_kind="third_contrast",
    )
    base.update(kwargs)
    return WorkbenchKeyAnalysisClaim(**base)


def _row(
    name: str,
    *,
    key: str | None = None,
    claim: WorkbenchKeyAnalysisClaim | None = None,
    bpm: float | None = 128.0,
) -> WorkbenchRow:
    return WorkbenchRow(
        display_name=name,
        relative_path=f"{name}.wav",
        path=f"/synthetic/843/{name}.wav",
        bpm=bpm,
        key=key,
        key_conf=0.85 if key else None,
        loudness=-14.0,
        brightness=1800.0,
        sample_class="loop",
        pred_type="Pad",
        status="ok",
        key_analysis_claim=claim,
    )


def _adapter(
    *,
    rows: tuple[WorkbenchRow, ...] | None = None,
    harmony_controller: HarmonicMatchLibraryController | None = None,
    preview_command=None,
    preview_stop=None,
    browse_command=None,
    context_harmonic_command=None,
    bind_context_callback: bool = False,
):
    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(
        fixture,
        "screen1-default-3panel",
        on_browser_selected=browse_command,
    )
    if rows is not None:
        from src.workbench_qml import _qml_row

        view_model.browser_rows = tuple(_qml_row(row) for row in rows)
        view_model.selected_browser_index = 0 if rows else -1
    if harmony_controller is None:
        harmony_controller = HarmonicMatchLibraryController(finder=find_harmony_matches)
    kwargs = dict(
        view_model=view_model,
        harmony_controller=harmony_controller,
        on_preview_requested=preview_command,
        on_preview_stopped=preview_stop,
    )
    params = inspect.signature(Screen1QmlInteractionAdapter).parameters
    if bind_context_callback and "on_context_harmonic_match_requested" in params:
        kwargs["on_context_harmonic_match_requested"] = context_harmonic_command
    return fixture, view_model, Screen1QmlInteractionAdapter(**kwargs)


def _require_open_retarget_api(adapter: Screen1QmlInteractionAdapter) -> None:
    assert callable(getattr(adapter, "open_harmonic_matches_for_row", None))
    assert callable(getattr(adapter, "request_context_harmonic_matches", None))
    assert hasattr(adapter, "sample_context_target")


# --- API / production seam ----------------------------------------------------


def test_adapter_exposes_open_harmonic_matches_for_row_authority():
    _fixture, _view_model, adapter = _adapter()
    _require_open_retarget_api(adapter)
    sig = inspect.signature(adapter.open_harmonic_matches_for_row)
    assert "row" in sig.parameters


def test_production_compose_leaves_context_callback_unbound_and_reuses_controller():
    """Production bind is the adapter default open/retarget seam (callback None)."""
    session = compose_workbench_session()
    adapter = session.qml_interaction_adapter
    assert isinstance(adapter.harmony_controller, HarmonicMatchLibraryController)
    assert getattr(adapter, "_on_context_harmonic_match_requested", "missing") is None
    assert callable(getattr(adapter, "open_harmonic_matches_for_row", None))


# --- Core open/retarget semantics --------------------------------------------


def test_selected_a_context_b_opens_anchor_b_keeps_selection_a():
    row_a = _row("sel_a", key="Amin")
    row_b = _row("ctx_b", key="Gmaj")
    cand = _row("cand", key="Gmaj")
    controller = HarmonicMatchLibraryController(finder=find_harmony_matches)
    _fixture, view_model, adapter = _adapter(
        rows=(row_a, row_b, cand),
        harmony_controller=controller,
    )
    _require_open_retarget_api(adapter)
    adapter.select_row(0)
    assert view_model.selected_browser_index == 0

    adapter.open_sample_context(1)
    result = adapter.request_context_harmonic_matches()

    assert result is row_b
    assert view_model.selected_browser_index == 0
    assert adapter.harmonic_match_open is True
    assert controller.anchor is row_b
    assert "ctx_b" in view_model.harmony_anchor
    assert adapter.sample_context_target is None


def test_context_harmonic_open_does_not_preview_or_audition():
    previews = []
    stops = []
    selected = []
    row_a = _row("a", key="Amin")
    row_b = _row("b", key="Gmaj")
    _fixture, view_model, adapter = _adapter(
        rows=(row_a, row_b),
        preview_command=previews.append,
        preview_stop=stops.append,
        browse_command=selected.append,
    )
    _require_open_retarget_api(adapter)
    adapter.select_row(0)
    selected.clear()

    adapter.open_sample_context(1)
    adapter.request_context_harmonic_matches()

    assert previews == []
    assert stops == []
    assert selected == []
    assert adapter.preview_active is False
    assert view_model.selected_browser_index == 0


def test_panel_closed_context_b_opens_panel():
    row_a = _row("a", key="Amin")
    row_b = _row("b", key="Cmaj")
    _fixture, _view_model, adapter = _adapter(rows=(row_a, row_b))
    _require_open_retarget_api(adapter)
    assert adapter.harmonic_match_open is False

    adapter.open_sample_context(1)
    adapter.request_context_harmonic_matches()

    assert adapter.harmonic_match_open is True
    assert adapter.harmony_controller.anchor is row_b


def test_panel_open_a_context_b_retargets_without_close():
    row_a = _row("a_ref", key="Amin")
    row_b = _row("b_ref", key="Gmaj")
    cand_a = _row("cand_a", key="Amin")
    cand_b = _row("cand_b", key="Gmaj")
    controller = HarmonicMatchLibraryController(finder=find_harmony_matches)
    _fixture, view_model, adapter = _adapter(
        rows=(row_a, row_b, cand_a, cand_b),
        harmony_controller=controller,
    )
    _require_open_retarget_api(adapter)

    assert adapter.open_harmonic_matches_for_row(row_a) is True
    assert adapter.harmonic_match_open is True
    assert controller.anchor is row_a
    rows_a = tuple(view_model.harmony_rows)

    toggle_calls = []
    original_toggle = adapter.toggle_harmonic_match

    def _spy_toggle():
        toggle_calls.append(True)
        return original_toggle()

    adapter.toggle_harmonic_match = _spy_toggle  # type: ignore[method-assign]

    adapter.open_sample_context(1)
    adapter.request_context_harmonic_matches()

    assert toggle_calls == []
    assert adapter.harmonic_match_open is True
    assert controller.anchor is row_b
    assert "b_ref" in view_model.harmony_anchor
    assert "a_ref" not in view_model.harmony_anchor
    assert tuple(view_model.harmony_rows) != rows_a or not rows_a


def test_panel_open_b_context_b_stays_open():
    row_a = _row("a", key="Amin")
    row_b = _row("b", key="Gmaj")
    _fixture, _view_model, adapter = _adapter(rows=(row_a, row_b))
    _require_open_retarget_api(adapter)
    assert adapter.open_harmonic_matches_for_row(row_b) is True
    assert adapter.harmonic_match_open is True

    adapter.open_sample_context(1)
    adapter.request_context_harmonic_matches()

    assert adapter.harmonic_match_open is True
    assert adapter.harmony_controller.anchor is row_b


def test_context_target_clears_while_harmony_anchor_remains_b():
    row_a = _row("a", key="Amin")
    row_b = _row("b", key="Gmaj")
    _fixture, _view_model, adapter = _adapter(rows=(row_a, row_b))
    _require_open_retarget_api(adapter)

    adapter.open_sample_context(1)
    assert adapter.sample_context_target is row_b
    adapter.request_context_harmonic_matches()

    assert adapter.sample_context_target is None
    assert adapter.harmony_controller.anchor is row_b


def test_exactly_one_set_anchor_per_context_activation():
    row_a = _row("a", key="Amin")
    row_b = _row("b", key="Gmaj")
    cand = _row("c", key="Gmaj")
    controller = HarmonicMatchLibraryController(finder=find_harmony_matches)
    calls = []
    original = controller.set_anchor

    def _spy(anchor, candidates):
        calls.append(anchor)
        return original(anchor, candidates)

    controller.set_anchor = _spy  # type: ignore[method-assign]
    _fixture, _view_model, adapter = _adapter(
        rows=(row_a, row_b, cand),
        harmony_controller=controller,
    )
    _require_open_retarget_api(adapter)

    adapter.open_sample_context(1)
    adapter.request_context_harmonic_matches()

    assert calls == [row_b]


def test_reuses_existing_controller_and_find_harmony_matches():
    controller = HarmonicMatchLibraryController(finder=find_harmony_matches)
    row_a = _row("a", key="Amin")
    row_b = _row("b", key="Gmaj")
    _fixture, _view_model, adapter = _adapter(
        rows=(row_a, row_b),
        harmony_controller=controller,
    )
    _require_open_retarget_api(adapter)

    adapter.open_sample_context(1)
    adapter.request_context_harmonic_matches()

    assert adapter.harmony_controller is controller
    assert controller._finder is find_harmony_matches


def test_context_path_never_calls_toggle_harmonic_match():
    row_a = _row("a", key="Amin")
    row_b = _row("b", key="Gmaj")
    _fixture, _view_model, adapter = _adapter(rows=(row_a, row_b))
    _require_open_retarget_api(adapter)
    toggle_calls = []
    original = adapter.toggle_harmonic_match

    def _spy():
        toggle_calls.append(True)
        return original()

    adapter.toggle_harmonic_match = _spy  # type: ignore[method-assign]
    adapter.open_sample_context(1)
    adapter.request_context_harmonic_matches()
    assert toggle_calls == []


# --- Reference / result integrity --------------------------------------------


def test_eligible_v1_context_b_projects_results_for_b():
    row_a = _row("a", key="Amin")
    row_b = _row("b_v1", key="Gmaj")
    cand = _row("cand_v1", key="Gmaj")
    controller = HarmonicMatchLibraryController(finder=find_harmony_matches)
    _fixture, view_model, adapter = _adapter(
        rows=(row_a, row_b, cand),
        harmony_controller=controller,
    )
    _require_open_retarget_api(adapter)

    adapter.open_sample_context(1)
    adapter.request_context_harmonic_matches()

    assert controller.anchor is row_b
    assert controller.results
    assert "b_v1" in view_model.harmony_anchor
    assert "Harmonic Matches" in view_model.harmony_status


def test_eligible_v2_context_b_projects_results_for_b():
    row_a = _row("a", key="Amin")
    row_b = _row("b_v2", key=None, claim=_claim(key="Gmaj", mode="maj"))
    cand = _row("cand_v2", key="Cmaj")
    controller = HarmonicMatchLibraryController(finder=find_harmony_matches)
    _fixture, view_model, adapter = _adapter(
        rows=(row_a, row_b, cand),
        harmony_controller=controller,
    )
    _require_open_retarget_api(adapter)

    adapter.open_sample_context(1)
    adapter.request_context_harmonic_matches()

    assert controller.anchor is row_b
    assert controller.results
    assert "b_v2" in view_model.harmony_anchor


def test_root_only_context_b_opens_empty_with_truthful_status():
    row_a = _row("a", key="Amin")
    row_b = _row("b_root", key="G")
    cand = _row("cand", key="Gmaj")
    controller = HarmonicMatchLibraryController(finder=find_harmony_matches)
    _fixture, view_model, adapter = _adapter(
        rows=(row_a, row_b, cand),
        harmony_controller=controller,
    )
    _require_open_retarget_api(adapter)

    adapter.open_sample_context(1)
    adapter.request_context_harmonic_matches()

    assert adapter.harmonic_match_open is True
    assert controller.anchor is row_b
    assert controller.results == ()
    assert view_model.harmony_rows == ()
    assert view_model.harmony_status == _INELIGIBLE_STATUS
    assert "b_root" in view_model.harmony_anchor


def test_invalid_bpm_context_b_fail_closed_no_stale_rows():
    row_a = _row("a", key="Amin")
    row_b = _row("b_bad", key="Gmaj", bpm=None)
    stale = _row("stale", key="Gmaj")
    controller = HarmonicMatchLibraryController(finder=find_harmony_matches)
    _fixture, view_model, adapter = _adapter(
        rows=(row_a, row_b, stale),
        harmony_controller=controller,
    )
    _require_open_retarget_api(adapter)
    assert adapter.open_harmonic_matches_for_row(stale) is True
    assert controller.results

    adapter.open_sample_context(1)
    adapter.request_context_harmonic_matches()

    assert adapter.harmonic_match_open is True
    assert controller.anchor is row_b
    assert controller.results == ()
    assert view_model.harmony_rows == ()
    assert "stale" not in view_model.harmony_anchor


def test_a_to_b_invalidates_a_rows_atomically_with_b_projection():
    row_a = _row("ref_a", key="Amin")
    row_b = _row("ref_b", key="Gmaj")
    cand_a = _row("only_a", key="Amin")
    cand_b = _row("only_b", key="Gmaj")
    controller = HarmonicMatchLibraryController(finder=find_harmony_matches)
    _fixture, view_model, adapter = _adapter(
        rows=(row_a, row_b, cand_a, cand_b),
        harmony_controller=controller,
    )
    _require_open_retarget_api(adapter)
    adapter.open_harmonic_matches_for_row(row_a)
    rows_a = tuple((r.display_name, getattr(r, "path", None)) for r in view_model.harmony_rows)
    assert rows_a  # A produced a visible projection

    adapter.open_sample_context(1)
    adapter.request_context_harmonic_matches()

    assert controller.anchor is row_b
    assert "ref_b" in view_model.harmony_anchor
    assert "ref_a" not in view_model.harmony_anchor
    rows_b = tuple((r.display_name, getattr(r, "path", None)) for r in view_model.harmony_rows)
    # Atomic retarget: projection is freshly computed for B, not the prior A tuple.
    # Amin candidates may still appear as fresh #842 TRANSPOSE matches for Gmaj;
    # that is not stale A reuse.
    assert rows_b != rows_a
    assert view_model.harmony_rows[0].display_name == "only_b"


# --- UI / panel / header supersession ----------------------------------------


def test_harmonic_match_header_button_structurally_removed():
    assert 'objectName: "harmonicMatchButton"' not in QML_SOURCE
    producer = QML_SOURCE[
        QML_SOURCE.index('objectName: "producerCommandZone"') : QML_SOURCE.index(
            'objectName: "headerRightZone"'
        )
    ]
    assert "harmonicMatchButton" not in producer
    assert 'Accessible.name: "Harmonic Match"' not in producer


def test_context_menu_still_wires_harmonic_matches_action():
    assert 'objectName: "sampleContextMenu"' in QML_SOURCE
    assert "actionHarmonicLabel" in QML_SOURCE or "Harmonic Matches" in QML_SOURCE
    assert "contextHarmonicMatches" in QML_SOURCE
    text = _WORKBENCH_QML_PY.read_text(encoding="utf-8")
    assert "def contextHarmonicMatches" in text


def test_no_new_close_x_or_on_off_and_845_handles_remain():
    for forbidden in ('text: "✕"', 'text: "X"', 'text: "OFF"', 'text: "ON"'):
        assert forbidden not in QML_SOURCE
    assert 'objectName: "harmonyCollapseHandle"' in QML_SOURCE
    assert 'objectName: "harmonyCollapseAffordance"' in QML_SOURCE
    assert "activateHarmonicMatchToggle()" in QML_SOURCE
    assert "toggleHarmonicMatch()" in QML_SOURCE


def test_browser_matches_livekit_order_and_live_kit_unchanged_on_open():
    browser_i = QML_SOURCE.index('objectName: "browserPane"')
    harmony_i = QML_SOURCE.index('objectName: "harmonyPane"')
    live_i = QML_SOURCE.index('objectName: "liveKitPane"')
    assert browser_i < harmony_i < live_i

    row_a = _row("a", key="Amin")
    row_b = _row("b", key="Gmaj")
    _fixture, view_model, adapter = _adapter(rows=(row_a, row_b))
    _require_open_retarget_api(adapter)
    live_before = view_model.live_kit_groups
    live_mat_before = view_model.live_kit_materialized

    adapter.open_sample_context(1)
    adapter.request_context_harmonic_matches()

    assert view_model.live_kit_groups is live_before
    assert view_model.live_kit_materialized == live_mat_before


def test_no_qml_matching_or_open_panel_alias_and_reuse_items():
    assert "find_harmony_matches" not in QML_SOURCE
    assert "rate_harmony" not in QML_SOURCE
    assert "is_harmonic_match_claim_eligible" not in QML_SOURCE
    assert "function openHarmonicMatchesPanel" not in QML_SOURCE
    assert QML_SOURCE.count("reuseItems: true") == 2
    assert "addHarmonyToKit(index)" in QML_SOURCE


def test_focus_not_auto_stolen_to_results_on_harmony_open():
    """Context/panel open must not forceActiveFocus results solely on open."""
    block_start = QML_SOURCE.index("onHarmonyOpenChanged:")
    block = QML_SOURCE[block_start : block_start + 500]
    assert "harmonicMatchList.forceActiveFocus()" not in block


# --- Collapse preservation (#845) --------------------------------------------


def test_collapse_matches_preserves_context_b_anchor_and_reopen_restores():
    row_a = _row("a", key="Amin")
    row_b = _row("b", key="Gmaj")
    cand = _row("cand", key="Gmaj")
    controller = HarmonicMatchLibraryController(finder=find_harmony_matches)
    _fixture, view_model, adapter = _adapter(
        rows=(row_a, row_b, cand),
        harmony_controller=controller,
    )
    _require_open_retarget_api(adapter)

    adapter.open_sample_context(1)
    adapter.request_context_harmonic_matches()
    assert adapter.harmonic_match_open is True
    assert controller.anchor is row_b
    results_before = tuple(controller.results)

    assert adapter.toggle_harmonic_match() is False
    assert adapter.harmonic_match_open is False
    assert controller.anchor is row_b
    assert tuple(controller.results) == results_before

    assert adapter.toggle_harmonic_match() is True
    assert adapter.harmonic_match_open is True
    assert controller.anchor is row_b
    assert "b" in view_model.harmony_anchor


# --- Protected interaction markers -------------------------------------------


def test_browser_keyboard_preview_favorite_845_846_markers_untouched():
    text = _WORKBENCH_QML_PY.read_text(encoding="utf-8")
    assert "navigateBrowser(1)" in QML_SOURCE
    assert "navigateBrowser(-1)" in QML_SOURCE
    assert "stopPreview()" in QML_SOURCE
    assert "previewRow(index)" in QML_SOURCE
    assert "toggleFavorite(index)" in QML_SOURCE
    assert "browserCollapsed" in text
    assert "liveKitCollapsed" in text
    assert 'objectName: "browserColumnResize_waveform"' in QML_SOURCE
    assert 'objectName: "browserColumnResize_meta"' in QML_SOURCE
    assert "contextAddToKit" in QML_SOURCE
    assert "request_context_add_to_kit" in text
