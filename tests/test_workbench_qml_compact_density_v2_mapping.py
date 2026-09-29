"""Additive #692 v2 fixture → production shell mapping (no PySide6)."""

from __future__ import annotations

from src.workbench_qml_spike import build_qml_view_model_from_fixture_v2
from src.workbench_visual_acceptance import (
    DENSITY_MODE_V2_COMPACT_TARGET,
    build_screen1_visual_fixture_v2,
    resolve_screen1_visual_state_v2,
)


def test_v2_active_source_maps_to_three_panel_shell_with_browser_rows():
    fixture = build_screen1_visual_fixture_v2()
    state = resolve_screen1_visual_state_v2(fixture, "screen1-active-source")
    assert state.density_mode == DENSITY_MODE_V2_COMPACT_TARGET
    view = build_qml_view_model_from_fixture_v2(fixture, "screen1-active-source")
    assert view.state_id == "screen1-default-3panel"
    assert view.panel_count == 3
    assert len(view.browser_rows) == 12
    assert view.selected_browser_index == 2
    assert view.browser_context == "Techno"


def test_v2_harmonic_open_maps_to_four_panel_shell():
    fixture = build_screen1_visual_fixture_v2()
    view = build_qml_view_model_from_fixture_v2(fixture, "screen1-harmonic-open")
    assert view.state_id == "screen1-harmonic-4panel"
    assert view.panel_count == 4
    assert len(view.browser_rows) == 12
    assert len(view.harmony_rows) >= 1


def test_v2_clean_start_does_not_materialize_browser_rows():
    fixture = build_screen1_visual_fixture_v2()
    view = build_qml_view_model_from_fixture_v2(fixture, "screen1-clean-start")
    assert view.state_id == "screen1-default-3panel"
    assert view.browser_rows == ()
    assert view.browser_context == "No library selected"
