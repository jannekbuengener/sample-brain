"""Frozen contracts for the optional Screen-1 Qt Quick proof spike."""

from __future__ import annotations

import importlib

from src.workbench_controller import WorkbenchRow
from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1


def _surface():
    """Import the new optional renderer boundary without requiring PySide6."""
    try:
        return importlib.import_module("src.workbench_qml_spike")
    except ModuleNotFoundError as exc:
        if exc.name == "src.workbench_qml_spike":
            raise AssertionError("MISSING_PRODUCTION_SURFACE: Qt Quick proof spike") from exc
        raise


def test_view_model_reuses_the_public_visual_fixture_for_both_required_states():
    surface = _surface()
    fixture = build_screen1_visual_fixture_v1()

    default = surface.Screen1QmlViewModel.from_fixture(
        fixture, "screen1-default-3panel"
    )
    harmonic = surface.Screen1QmlViewModel.from_fixture(
        fixture, "screen1-harmonic-4panel"
    )

    assert default.panel_count == 3
    assert harmonic.panel_count == 4
    assert default.browser_rows[fixture.selected_browser_index].source_row is fixture.browser_rows[2]
    assert harmonic.harmony_rows[0].source_row is fixture.harmony_results[0].row
    assert default.live_kit_groups[1].name == "Drums"
    assert default.live_kit_groups[1].slots[0].assignment is fixture.browser_rows[0]


def test_view_model_routes_selection_once_to_the_existing_python_callback():
    surface = _surface()
    fixture = build_screen1_visual_fixture_v1()
    selected: list[WorkbenchRow] = []
    view_model = surface.Screen1QmlViewModel.from_fixture(
        fixture,
        "screen1-default-3panel",
        on_browser_selected=selected.append,
    )

    result = view_model.select_browser_index(4)

    assert result is fixture.browser_rows[4]
    assert selected == [fixture.browser_rows[4]]
    assert view_model.selected_browser_index == 4


def test_virtual_window_is_bounded_for_a_50k_library_and_keeps_selection_visible():
    surface = _surface()
    rows = tuple(
        WorkbenchRow(
            display_name=f"SYNTH_{index:05d}",
            relative_path=f"fixture/SYNTH_{index:05d}.wav",
            path=f"fixture/SYNTH_{index:05d}.wav",
            bpm=132.0,
            key=None,
            key_conf=None,
            loudness=None,
            brightness=None,
            sample_class="one_shot",
            pred_type="Kick",
            status="ok",
            details={},
        )
        for index in range(50_000)
    )

    window = surface.virtual_row_window(
        rows, selected_index=49_999, visible_rows=12, cache_buffer_rows=4
    )

    assert window.total_rows == 50_000
    assert len(window.rows) <= 20
    assert window.rows[-1].source_row is rows[-1]
    assert window.first_index <= 49_999 <= window.last_index


def test_qml_source_declares_a_recycling_listview_without_importing_pyside_on_core_import():
    surface = _surface()

    assert "ListView" in surface.QML_SOURCE
    assert "reuseItems: true" in surface.QML_SOURCE
    assert surface.qml_runtime_available() in {True, False}
