"""#1204 panel disclosure + collapse geometry (historical #845 functional rules).

Canon: docs/WORKBENCH_ELASTIC_LAYOUT.md (Panel disclosure + collapse geometry #1204).
Historical origin: #845 / parent #844. Boundaries: #843 (Matches embed),
#1211/#1210 out of scope, Live Kit drawer via #1077 (not horizontal panel chrome).

TEST_FREEZE: assertions below express the intended #1204 behaviour. Do not weaken
them to fit incomplete product code. Functional #845 rules that remain valid are
retained; superseded chrome/geometry rules are replaced by residual-workspace and
hairline-disclosure contracts.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from src.workbench_harmony import (
    HarmonicMatchLibraryController,
    HarmonyRelation,
    HarmonySuggestion,
)
from src.workbench_layout_solver import (
    CANONICAL_DEFAULT_RATIOS,
    PANEL_MIN_WIDTH,
    solve_widths,
    visible_panel_ids,
)
from src.workbench_live_kit import LiveKitState
from src.workbench_qml import (
    LiveKitPresenter,
    QML_SOURCE,
    Screen1QmlInteractionAdapter,
)
from src.workbench_qml_elastic import create_elastic_layout_bridge
from src.workbench_qml_runtime import Screen1QmlRuntimeComposition
from src.workbench_qml_spike import build_qml_view_model_from_fixture
from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1

_WORKBENCH_QML_PY = Path(__file__).resolve().parents[1] / "src" / "workbench_qml.py"

# Shared hairline disclosure objectNames (#1204). Historical #845 names retained
# where they still identify Browser/Harmony disclosure controls.
_BROWSER_DISCLOSURE_OPEN = "browserCollapseHandle"
_BROWSER_DISCLOSURE_REOPEN = "browserCollapseAffordance"
_HARMONY_DISCLOSURE_OPEN = "harmonyCollapseHandle"
_HARMONY_DISCLOSURE_REOPEN = "harmonyCollapseAffordance"
_PANEL_DISCLOSURE_MARKERS = (
    _BROWSER_DISCLOSURE_OPEN,
    _BROWSER_DISCLOSURE_REOPEN,
    _HARMONY_DISCLOSURE_OPEN,
    _HARMONY_DISCLOSURE_REOPEN,
)


# --- Pure ownership / solver contracts ---------------------------------------


def test_presentation_collapse_combo_helper_rejects_browser_collapsed_matches_open():
    """Matches ⊂ Browser — Browser COLLAPSED + Matches OPEN is invalid."""
    from src.workbench_layout_solver import presentation_collapse_combo_is_valid

    assert (
        presentation_collapse_combo_is_valid(
            browser_collapsed=True,
            harmonic_open=True,
            live_kit_collapsed=False,
        )
        is False
    )
    assert (
        presentation_collapse_combo_is_valid(
            browser_collapsed=True,
            harmonic_open=False,
            live_kit_collapsed=False,
        )
        is True
    )
    assert (
        presentation_collapse_combo_is_valid(
            browser_collapsed=False,
            harmonic_open=True,
            live_kit_collapsed=True,
        )
        is True
    )


def test_solver_excludes_collapsed_browser_from_visible_panels():
    assert visible_panel_ids(
        harmony_open=False,
        has_active_source=True,
        browser_visible=False,
        live_kit_visible=True,
        library_visible=True,
    ) == ("library",)


def test_solver_forces_harmony_out_when_browser_not_visible():
    """Ownership fail-safe: harmony never participates without Browser."""
    assert visible_panel_ids(
        harmony_open=True,
        has_active_source=True,
        browser_visible=False,
        live_kit_visible=False,
        library_visible=True,
    ) == ("library",)


def test_solver_collapsed_browser_keeps_library_bounded_with_residual_workspace():
    """#1204: Browser collapse must not expand Library to the full workspace."""
    available = 1600.0
    open_solution = solve_widths(
        CANONICAL_DEFAULT_RATIOS,
        available_width=available,
        harmony_open=False,
        has_active_source=True,
        browser_visible=True,
        library_visible=True,
    )
    collapsed = solve_widths(
        CANONICAL_DEFAULT_RATIOS,
        available_width=available,
        harmony_open=False,
        has_active_source=True,
        browser_visible=False,
        live_kit_visible=True,
        library_visible=True,
    )
    assert set(collapsed.widths) == {"library"}
    assert "harmony" not in collapsed.widths
    assert "browser" not in collapsed.widths
    library_width = float(collapsed.widths["library"])
    residual = float(collapsed.residual_width)
    assert abs(library_width + residual - available) < 1e-6
    assert library_width < available * 0.5
    assert library_width >= PANEL_MIN_WIDTH["library"] - 1e-6
    # Bounded near stored absolute share, not renormalized to ~100%.
    expected_share = CANONICAL_DEFAULT_RATIOS["library"] * available
    assert abs(library_width - expected_share) < 1.0
    assert residual > library_width
    assert collapsed.ratios == CANONICAL_DEFAULT_RATIOS
    assert collapsed.ratios == open_solution.ratios

    # Harmony-open input must still force Matches out when Browser is hidden.
    collapsed_harmony_input = solve_widths(
        CANONICAL_DEFAULT_RATIOS,
        available_width=available,
        harmony_open=True,
        has_active_source=True,
        browser_visible=False,
        library_visible=True,
    )
    assert set(collapsed_harmony_input.widths) == {"library"}
    assert float(collapsed_harmony_input.residual_width) > 0.0
    assert collapsed_harmony_input.ratios == CANONICAL_DEFAULT_RATIOS


def test_solver_browser_reopen_restores_geometry_from_same_ratio_truth_without_drift():
    available = 1600.0
    ratios = dict(CANONICAL_DEFAULT_RATIOS)
    open_a = solve_widths(
        ratios,
        available_width=available,
        harmony_open=False,
        has_active_source=True,
        browser_visible=True,
        library_visible=True,
    )
    for _ in range(5):
        collapsed = solve_widths(
            ratios,
            available_width=available,
            harmony_open=False,
            has_active_source=True,
            browser_visible=False,
            library_visible=True,
        )
        assert collapsed.ratios == ratios
        assert "browser" not in collapsed.widths
        open_b = solve_widths(
            collapsed.ratios,
            available_width=available,
            harmony_open=False,
            has_active_source=True,
            browser_visible=True,
            library_visible=True,
        )
        assert open_b.ratios == open_a.ratios
        assert abs(open_b.widths["library"] - open_a.widths["library"]) < 1e-6
        assert abs(open_b.widths["browser"] - open_a.widths["browser"]) < 1e-6
        assert open_b.residual_width == 0.0 or open_b.residual_width < 1e-6
        ratios = dict(open_b.ratios)


def test_solver_narrow_width_collapsed_browser_clamps_library_deterministically():
    available = 400.0
    collapsed = solve_widths(
        CANONICAL_DEFAULT_RATIOS,
        available_width=available,
        harmony_open=False,
        has_active_source=True,
        browser_visible=False,
        library_visible=True,
    )
    library_width = float(collapsed.widths["library"])
    assert library_width <= available + 1e-6
    assert library_width >= min(PANEL_MIN_WIDTH["library"], available) - 1e-6
    assert abs(library_width + float(collapsed.residual_width) - available) < 1e-6
    assert collapsed.ratios == CANONICAL_DEFAULT_RATIOS


def test_solver_browser_visible_default_preserves_pre845_panel_sets():
    """Default browser_visible=True; #908 drops horizontal livekit."""
    assert visible_panel_ids(
        harmony_open=False,
        has_active_source=True,
        live_kit_visible=True,
    ) == ("library", "browser")
    assert visible_panel_ids(
        harmony_open=True,
        has_active_source=True,
        live_kit_visible=True,
    ) == ("library", "browser", "harmony")


# --- QML source contracts: hairline disclosure vs resize ---------------------


def test_qml_declares_unified_panel_disclosure_object_names():
    for name in _PANEL_DISCLOSURE_MARKERS:
        assert f'objectName: "{name}"' in QML_SOURCE
    # Live Kit is drawer/HUD — not part of the horizontal panel disclosure set.
    assert 'objectName: "liveKitCollapseHandle"' not in QML_SOURCE
    assert 'objectName: "liveKitCollapseAffordance"' not in QML_SOURCE
    assert "toggleLiveKitDrawer" in QML_SOURCE
    assert 'objectName: "editLiveKitRevealControl"' in QML_SOURCE
    assert 'objectName: "liveKitDrawerHideButton"' in QML_SOURCE


def test_qml_panel_disclosure_uses_hairline_seam_not_chunky_permanent_tab():
    """Visible seam ~1 DIP; hit area wider; chevron only when disclosed."""
    assert "component PanelDisclosureSeam" in QML_SOURCE
    seam_idx = QML_SOURCE.index("component PanelDisclosureSeam")
    seam = QML_SOURCE[seam_idx : seam_idx + 2200]
    assert "property int hitWidth: 8" in seam
    assert "width: 1" in seam
    assert "disclosed" in seam
    assert "PointingHandCursor" in seam
    for name in _PANEL_DISCLOSURE_MARKERS:
        idx = QML_SOURCE.index(f'objectName: "{name}"')
        window = QML_SOURCE[max(0, idx - 220) : idx + 360]
        assert "PanelDisclosureSeam" in window
    # Chunky #845 permanent reopen slabs (fixed 18×72 elevated tabs) are gone.
    reopen_idx = QML_SOURCE.index(f'objectName: "{_BROWSER_DISCLOSURE_REOPEN}"')
    reopen_block = QML_SOURCE[reopen_idx : reopen_idx + 500]
    assert "height: 72" not in reopen_block
    assert "surfaceElevated" not in reopen_block


def test_qml_collapse_handles_use_click_cursor_not_resize_cursor():
    """Disclosure = PointingHand; elastic resize strips keep SizeHorCursor."""
    assert "toggleBrowserCollapsed" in QML_SOURCE
    assert "toggleLiveKitDrawer" in QML_SOURCE
    assert "PointingHandCursor" in QML_SOURCE
    assert 'objectName: "elasticHandleAfterLibrary"' in QML_SOURCE
    assert 'objectName: "elasticHandleAfterBrowser"' in QML_SOURCE
    assert 'objectName: "elasticHandleAfterHarmony"' not in QML_SOURCE
    assert "Qt.SizeHorCursor" in QML_SOURCE
    assert 'layoutModel.applyDrag("library"' in QML_SOURCE
    assert 'layoutModel.applyDrag("browser"' in QML_SOURCE
    assert 'layoutModel.applyDrag("harmony"' not in QML_SOURCE


def test_qml_disclosure_and_resize_remain_separate_intents():
    """Collapse must not share applyDrag; resize must not call collapse toggles."""
    assert QML_SOURCE.count("layoutModel.applyDrag(") == 2
    for handle in (_BROWSER_DISCLOSURE_OPEN, _HARMONY_DISCLOSURE_OPEN):
        idx = QML_SOURCE.index(f'objectName: "{handle}"')
        window = QML_SOURCE[max(0, idx - 120) : idx + 500]
        assert "layoutModel.applyDrag" not in window
        assert "SizeHorCursor" not in window
    for resize_name in ("elasticHandleAfterLibrary", "elasticHandleAfterBrowser"):
        idx = QML_SOURCE.index(f'objectName: "{resize_name}"')
        window = QML_SOURCE[idx : idx + 2200]
        assert "toggleBrowserCollapsed" not in window
        assert "activateHarmonicMatchToggle" not in window
        assert "SizeHorCursor" in window
        assert "layoutModel.applyDrag" in window


def test_qml_collapse_handles_are_keyboard_activatable():
    """Hover may emphasize; Space/Enter activation must remain possible."""
    assert "component PanelDisclosureSeam" in QML_SOURCE
    seam_idx = QML_SOURCE.index("component PanelDisclosureSeam")
    seam = QML_SOURCE[seam_idx : seam_idx + 3200]
    assert "Keys.onReturnPressed" in seam or "Key_Return" in seam
    assert "Key_Space" in seam or "Keys.onPressed" in seam
    assert "Accessible.role" in seam
    assert "Accessible.name" in seam
    for name in _PANEL_DISCLOSURE_MARKERS:
        assert f'objectName: "{name}"' in QML_SOURCE


def test_qml_library_reveal_uses_same_disclosure_primitive_style():
    assert 'objectName: "libraryRevealAffordance"' in QML_SOURCE
    idx = QML_SOURCE.index('objectName: "libraryRevealAffordance"')
    window = QML_SOURCE[max(0, idx - 180) : idx + 500]
    assert "PanelDisclosureSeam" in window


# --- Adapter / presentation preservation -------------------------------------


def _adapter_with_harmony_and_kit():
    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(fixture, "screen1-harmonic-4panel")
    view_model.set_workspace_materialization(
        has_active_source=True,
        calm_canvas_visible=False,
        browser_materialized=True,
        live_kit_materialized=True,
    )
    view_model.set_library_revealed(True)

    def _finder(anchor, candidates):
        return (
            [
                HarmonySuggestion(
                    row=candidate,
                    relation=HarmonyRelation.DIRECT,
                    harmony_score=1.0,
                    bpm_score=1.0,
                    total_score=1.0,
                    explanation="stub",
                )
                for candidate in candidates[:2]
            ],
            None,
        )

    harmony = HarmonicMatchLibraryController(finder=_finder)
    live_kit = LiveKitPresenter(LiveKitState())
    composition = Screen1QmlRuntimeComposition()
    composition.reveal_live_kit()
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        harmony_controller=harmony,
        live_kit=live_kit,
    )
    adapter._runtime_composition = composition
    view_model.live_kit_groups = live_kit.groups
    adapter.harmonic_match_open = True
    # Seed projected Matches state directly so preservation asserts domain retention
    # independent of finder eligibility on fixture rows.
    if len(view_model.browser_rows) >= 2:
        anchor = view_model.browser_rows[0].source_row
        match = view_model.browser_rows[1].source_row
        view_model.harmony_anchor = f"Reference: {anchor.display_name}"
        from src.workbench_qml import QmlHarmonyRow

        view_model.harmony_rows = (
            QmlHarmonyRow(
                source_row=match,
                display_name=match.display_name,
                sample_type=match.pred_type or "—",
                key=str(match.key or "—"),
                waveform_envelope=(),
                fit="100%",
                relation="Direct",
                explanation="seed",
            ),
        )
    return fixture, view_model, adapter, composition, live_kit


def test_adapter_exposes_browser_and_transient_live_kit_drawer_flags_and_toggles():
    _fixture, _view_model, adapter, _composition, _live_kit = _adapter_with_harmony_and_kit()
    assert hasattr(adapter, "browser_collapsed")
    assert hasattr(adapter, "live_kit_drawer_open")
    assert hasattr(adapter, "live_kit_auto_disclosure_consumed")
    assert adapter.browser_collapsed is False
    # #954: Restored musical content must not reopen a presentation overlay.
    assert adapter.live_kit_drawer_open is False
    assert adapter.live_kit_auto_disclosure_consumed is False
    assert callable(getattr(adapter, "toggle_browser_collapsed"))
    assert callable(getattr(adapter, "toggle_live_kit_drawer"))


def test_collapse_browser_forces_matches_closed_and_preserves_selection_and_results():
    _fixture, view_model, adapter, _composition, _live_kit = _adapter_with_harmony_and_kit()
    selected = int(view_model.selected_browser_index)
    harmony_rows_before = tuple(view_model.harmony_rows)
    harmony_anchor_before = view_model.harmony_anchor
    assert adapter.harmonic_match_open is True
    assert harmony_rows_before

    collapsed = adapter.toggle_browser_collapsed()
    assert collapsed is True
    assert adapter.browser_collapsed is True
    assert adapter.harmonic_match_open is False
    assert view_model.selected_browser_index == selected
    assert tuple(view_model.harmony_rows) == harmony_rows_before
    assert view_model.harmony_anchor == harmony_anchor_before

    # Reopen Browser must not auto-reopen Matches.
    adapter.toggle_browser_collapsed()
    assert adapter.browser_collapsed is False
    assert adapter.harmonic_match_open is False
    assert tuple(view_model.harmony_rows) == harmony_rows_before


def test_collapse_does_not_mutate_kit_or_audition_product_state():
    _fixture, view_model, adapter, _composition, live_kit = _adapter_with_harmony_and_kit()
    preview_before = bool(getattr(adapter, "preview_active", False))
    groups_before = tuple(
        (
            group.name,
            tuple(
                (slot.name, None if slot.assignment is None else slot.assignment.path)
                for slot in group.slots
            ),
        )
        for group in live_kit.groups
    )
    selected = int(view_model.selected_browser_index)
    adapter.toggle_browser_collapsed()
    adapter.toggle_browser_collapsed()
    assert int(view_model.selected_browser_index) == selected
    assert bool(getattr(adapter, "preview_active", False)) == preview_before
    groups_after = tuple(
        (
            group.name,
            tuple(
                (slot.name, None if slot.assignment is None else slot.assignment.path)
                for slot in group.slots
            ),
        )
        for group in live_kit.groups
    )
    assert groups_after == groups_before


def test_transient_live_kit_drawer_toggle_preserves_materialization_and_slot_content():
    _fixture, view_model, adapter, composition, live_kit = _adapter_with_harmony_and_kit()
    assert view_model.live_kit_materialized is True
    groups_before = tuple(
        (
            group.name,
            tuple(
                (slot.name, None if slot.assignment is None else slot.assignment.path)
                for slot in group.slots
            ),
        )
        for group in live_kit.groups
    )

    assert adapter.toggle_live_kit_drawer() is True
    assert adapter.live_kit_drawer_open is True
    assert view_model.live_kit_materialized is True
    assert composition.live_kit_revealed is True
    groups_after = tuple(
        (
            group.name,
            tuple(
                (slot.name, None if slot.assignment is None else slot.assignment.path)
                for slot in group.slots
            ),
        )
        for group in live_kit.groups
    )
    assert groups_after == groups_before

    assert adapter.toggle_live_kit_drawer() is False
    assert adapter.live_kit_drawer_open is False
    assert view_model.live_kit_materialized is True


def test_matches_toggle_open_blocked_while_browser_collapsed():
    _fixture, _view_model, adapter, _composition, _live_kit = _adapter_with_harmony_and_kit()
    adapter.toggle_browser_collapsed()
    assert adapter.browser_collapsed is True
    assert adapter.harmonic_match_open is False

    opened = adapter.toggle_harmonic_match()
    assert opened is False
    assert adapter.harmonic_match_open is False


def test_interaction_bridge_projects_collapse_properties_and_slots():
    text = _WORKBENCH_QML_PY.read_text(encoding="utf-8")
    assert "browserCollapsed" in text
    assert "liveKitCollapsed" in text
    assert "def toggleBrowserCollapsed" in text
    assert "def toggleLiveKitCollapsed" in text


def test_elastic_bridge_accepts_browser_visible_callback():
    params = inspect.signature(create_elastic_layout_bridge).parameters
    assert "browser_visible" in params


def test_elastic_bridge_projects_residual_width_without_ratio_mutation(tmp_path: Path):
    import importlib.util

    if importlib.util.find_spec("PySide6") is None:
        return
    active = {"value": True}
    browser = {"value": True}
    bridge = create_elastic_layout_bridge(
        state_dir=tmp_path,
        harmony_open=lambda: False,
        has_active_source=lambda: active["value"],
        browser_visible=lambda: browser["value"],
        library_revealed=lambda: True,
    )
    bridge.setContentWidth(1600.0)
    before = dict(bridge.current_ratios())
    open_library = float(bridge.libraryWidth)
    assert float(bridge.residualWidth) < 1e-6
    browser["value"] = False
    bridge.syncFromInteraction()
    assert dict(bridge.current_ratios()) == before
    assert float(bridge.browserWidth) == 0.0
    assert float(bridge.libraryWidth) < open_library * 1.5
    assert float(bridge.libraryWidth) < 800.0
    assert float(bridge.residualWidth) > float(bridge.libraryWidth)
    browser["value"] = True
    bridge.syncFromInteraction()
    assert dict(bridge.current_ratios()) == before
    assert abs(float(bridge.libraryWidth) - open_library) < 1e-6
    assert float(bridge.residualWidth) < 1e-6


def test_production_layout_wiring_uses_materialized_and_not_collapsed_for_live_kit():
    """materialized != visible: collapse hides pane without clearing disclosure."""
    text = _WORKBENCH_QML_PY.read_text(encoding="utf-8")
    assert "live_kit_collapsed" in text
    assert "live_kit_materialized" in text
    assert "live_kit_visible=" in text
    assert "browser_visible=" in text or "browser_collapsed" in text
