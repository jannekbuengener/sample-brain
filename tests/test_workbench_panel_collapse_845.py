"""#845 Panel presentation collapse / mid-edge handles — frozen contracts.

Canon: docs/WORKBENCH_ELASTIC_LAYOUT.md (Presentation collapse #845).
Parent: #844. Boundaries: #843 (Matches embed), #846 (resize/divider styling).

TEST_FREEZE: assertions below express the intended #845 behaviour. Do not weaken
them to fit incomplete product code. Expected RED until implementation.
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
    HANDLE_WIDTH_PX,
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


def test_solver_collapsed_browser_with_live_kit_renormalises_without_ratio_drift():
    available = 1600.0
    solution = solve_widths(
        CANONICAL_DEFAULT_RATIOS,
        available_width=available,
        harmony_open=False,
        has_active_source=True,
        browser_visible=False,
        live_kit_visible=True,
        library_visible=True,
    )
    # #908: Live Kit no longer takes horizontal width.
    assert set(solution.widths) == {"library"}
    assert abs(solution.widths["library"] - available) < 1e-6
    assert solution.ratios == CANONICAL_DEFAULT_RATIOS


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


# --- QML source contracts: handles vs resize ---------------------------------


def test_qml_declares_distinct_collapse_handle_object_names():
    assert 'objectName: "browserCollapseHandle"' in QML_SOURCE
    assert 'objectName: "harmonyCollapseHandle"' in QML_SOURCE
    assert 'objectName: "liveKitCollapseHandle"' in QML_SOURCE
    assert 'objectName: "browserCollapseAffordance"' in QML_SOURCE
    assert 'objectName: "harmonyCollapseAffordance"' in QML_SOURCE
    assert 'objectName: "liveKitCollapseAffordance"' in QML_SOURCE


def test_qml_collapse_handles_use_click_cursor_not_resize_cursor():
    """Collapse = PointingHand; elastic resize strips keep SizeHorCursor."""
    assert "toggleBrowserCollapsed" in QML_SOURCE
    assert "toggleLiveKitCollapsed" in QML_SOURCE
    assert "browserCollapseHandle" in QML_SOURCE
    assert "PointingHandCursor" in QML_SOURCE
    # Existing elastic resize contract remains present and unchanged in intent.
    assert 'objectName: "elasticHandleAfterLibrary"' in QML_SOURCE
    assert 'objectName: "elasticHandleAfterBrowser"' in QML_SOURCE
    assert 'objectName: "elasticHandleAfterHarmony"' not in QML_SOURCE
    assert "Qt.SizeHorCursor" in QML_SOURCE
    assert 'layoutModel.applyDrag("library"' in QML_SOURCE
    assert 'layoutModel.applyDrag("browser"' in QML_SOURCE
    assert 'layoutModel.applyDrag("harmony"' not in QML_SOURCE


def test_qml_collapse_handles_are_keyboard_activatable():
    """Hover may emphasize; Space/Enter activation must remain possible."""
    for name in (
        "browserCollapseHandle",
        "harmonyCollapseHandle",
        "liveKitCollapseHandle",
        "browserCollapseAffordance",
        "harmonyCollapseAffordance",
        "liveKitCollapseAffordance",
    ):
        assert f'objectName: "{name}"' in QML_SOURCE
    assert "Key_Return" in QML_SOURCE or "Keys.onReturnPressed" in QML_SOURCE
    assert "Key_Space" in QML_SOURCE or "Keys.onPressed" in QML_SOURCE


def test_qml_collapse_handles_do_not_share_apply_drag_mouse_area():
    """Collapse click/activate must not live inside elastic drag MouseAreas."""
    # #908: library + browser handles only.
    assert QML_SOURCE.count("layoutModel.applyDrag(") == 2
    for handle in (
        "browserCollapseHandle",
        "harmonyCollapseHandle",
        "liveKitCollapseHandle",
    ):
        idx = QML_SOURCE.index(f'objectName: "{handle}"')
        window = QML_SOURCE[idx : idx + 1200]
        assert "layoutModel.applyDrag" not in window
        assert "SizeHorCursor" not in window


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


def test_adapter_exposes_browser_and_live_kit_collapse_flags_and_toggles():
    _fixture, _view_model, adapter, _composition, _live_kit = _adapter_with_harmony_and_kit()
    assert hasattr(adapter, "browser_collapsed")
    assert hasattr(adapter, "live_kit_collapsed")
    assert adapter.browser_collapsed is False
    assert adapter.live_kit_collapsed is False
    assert callable(getattr(adapter, "toggle_browser_collapsed"))
    assert callable(getattr(adapter, "toggle_live_kit_collapsed"))


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


def test_collapse_live_kit_preserves_materialization_and_slot_content():
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

    assert adapter.toggle_live_kit_collapsed() is True
    assert adapter.live_kit_collapsed is True
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

    adapter.toggle_live_kit_collapsed()
    assert adapter.live_kit_collapsed is False
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


def test_production_layout_wiring_uses_materialized_and_not_collapsed_for_live_kit():
    """materialized != visible: collapse hides pane without clearing disclosure."""
    text = _WORKBENCH_QML_PY.read_text(encoding="utf-8")
    assert "live_kit_collapsed" in text
    assert "live_kit_materialized" in text
    assert "live_kit_visible=" in text
    assert "browser_visible=" in text or "browser_collapsed" in text
