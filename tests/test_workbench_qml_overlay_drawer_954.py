"""TEST_GATE / TEST_FREEZE - Browser-scoped Live Kit overlay drawer (#954)."""

from __future__ import annotations

import pytest

from src.workbench_live_kit import LiveKitState
from src.workbench_qml import (
    LiveKitPresenter,
    QML_SOURCE,
    Screen1QmlInteractionAdapter,
    Screen1QmlViewModel,
)


def _adapter(*, occupied: bool = False) -> tuple[Screen1QmlInteractionAdapter, LiveKitState]:
    view_model = Screen1QmlViewModel.baseline("screen1-harmonic-4panel")
    row = view_model.browser_rows[0].source_row
    state = LiveKitState()
    if occupied:
        state.assign("Kick + Bass", "Kick", row)
    presenter = LiveKitPresenter(state=state)
    view_model.live_kit_groups = presenter.groups
    view_model.set_workspace_materialization(
        has_active_source=True,
        calm_canvas_visible=False,
        browser_materialized=True,
        live_kit_materialized=occupied,
    )
    return (
        Screen1QmlInteractionAdapter(view_model=view_model, live_kit=presenter),
        state,
    )


def test_drawer_starts_closed_even_when_the_musical_kit_is_restored():
    adapter, state = _adapter(occupied=True)

    assert state.assignment_for("Kick + Bass", "Kick") is not None
    assert adapter.live_kit_drawer_open is False
    assert adapter.live_kit_auto_disclosure_consumed is False


def test_first_successful_slot_assignment_auto_opens_once_and_closes_harmony_non_destructively():
    adapter, state = _adapter()
    adapter.harmonic_match_open = True
    preserved_rows = (object(),)
    adapter.view_model.harmony_rows = preserved_rows  # type: ignore[assignment]

    adapter.request_add_to_kit(0)
    assert adapter.assign_live_kit_slot("Kick + Bass", "Kick") is True

    assert state.assignment_for("Kick + Bass", "Kick") is not None
    assert adapter.live_kit_drawer_open is True
    assert adapter.live_kit_auto_disclosure_consumed is True
    assert adapter.harmonic_match_open is False
    assert adapter.view_model.harmony_rows is preserved_rows


def test_later_assignment_respects_manual_drawer_close_and_manually_reopened_harmony():
    adapter, state = _adapter()
    adapter.request_add_to_kit(0)
    assert adapter.assign_live_kit_slot("Kick + Bass", "Kick") is True
    assert adapter.toggle_live_kit_drawer() is False

    adapter.harmonic_match_open = True
    adapter.request_add_to_kit(0)
    assert adapter.assign_live_kit_slot("Kick + Bass", "Bass") is True

    assert state.assignment_for("Kick + Bass", "Bass") is not None
    assert adapter.live_kit_drawer_open is False
    assert adapter.harmonic_match_open is True


@pytest.mark.parametrize(
    ("rows", "available_height", "expected"),
    [
        (1, 900, 112),
        (2, 900, 160),
        (20, 900, 360),
    ],
)
def test_drawer_height_grows_per_real_row_and_caps_with_internal_overflow(
    rows: int, available_height: int, expected: int
):
    from src.workbench_live_kit_drawer import drawer_geometry_for_rows

    geometry = drawer_geometry_for_rows(rows, available_height)

    assert geometry.height == expected
    assert geometry.browser_bottom_inset == expected
    assert geometry.internal_scroll is (rows >= 20)


def test_qml_declares_browser_scoped_overlay_and_does_not_keep_the_bottom_band():
    assert 'objectName: "liveKitOverlayDrawer"' in QML_SOURCE
    assert "property bool liveKitDrawerOpen: window.interaction.liveKitDrawerOpen" in QML_SOURCE
    assert "x: upperWorkspaceRow.x + browserPane.x" in QML_SOURCE
    assert "width: browserPane.width" in QML_SOURCE
    assert "bottomMargin: liveKitOverlayDrawer.visible ? liveKitOverlayDrawer.height : 0" in QML_SOURCE
    upper_workspace_start = QML_SOURCE.index('id: upperWorkspaceRow')
    assert "height: parent.height" in QML_SOURCE[upper_workspace_start : upper_workspace_start + 500]
    assert "bottomRackHeightRatio, 0.24" not in QML_SOURCE
