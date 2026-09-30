"""Screen-1 visible label coherence after #747 owner review.

Browser context and Harmonic Match status must not contradict materialised
workspace state (e.g. "No library selected" with Browser rows, or
"Harmonic Match ist ausgeschaltet." while the Harmony pane is open).
"""

from __future__ import annotations

from src.workbench_harmony import HarmonicMatchLibraryController
from src.workbench_qml import Screen1QmlInteractionAdapter, Screen1QmlViewModel
from src.workbench_qml_spike import (
    apply_screen1_visual_state_v2,
    build_qml_view_model_from_fixture,
    build_qml_view_model_from_fixture_v2,
)
from src.workbench_visual_acceptance import (
    build_screen1_visual_fixture_v1,
    build_screen1_visual_fixture_v2,
)


CLOSED_HARMONY = "Harmonic Match ist ausgeschaltet."
NO_LIBRARY = "No library selected"


def test_v1_active_fixture_sets_browser_context_not_no_library_selected():
    fixture = build_screen1_visual_fixture_v1()
    view = build_qml_view_model_from_fixture(fixture, "screen1-default-3panel")
    assert view.has_active_source is True
    assert view.browser_materialized is True
    assert len(view.browser_rows) >= 1
    assert view.browser_context != NO_LIBRARY
    assert view.browser_context.strip() != ""


def test_v1_harmonic_fixture_status_not_closed_when_4panel():
    fixture = build_screen1_visual_fixture_v1()
    view = build_qml_view_model_from_fixture(fixture, "screen1-harmonic-4panel")
    assert view.panel_count == 4
    assert len(view.harmony_rows) >= 1
    assert view.harmony_status != CLOSED_HARMONY


def test_adapter_sync_fixes_stale_labels_when_harmony_forced_open():
    fixture = build_screen1_visual_fixture_v1()
    view = build_qml_view_model_from_fixture(fixture, "screen1-default-3panel")
    # Simulate a stale harness that opens Harmony without projecting status.
    view.browser_context = NO_LIBRARY
    view.harmony_status = CLOSED_HARMONY
    adapter = Screen1QmlInteractionAdapter(
        view_model=view,
        harmony_controller=HarmonicMatchLibraryController(),
    )
    adapter.harmonic_match_open = True
    from src.workbench_qml import _qml_harmony_row

    view.harmony_rows = tuple(_qml_harmony_row(m) for m in fixture.harmony_results)

    changed = adapter.sync_visible_state_labels()
    assert changed is True
    assert view.browser_context != NO_LIBRARY
    assert view.harmony_status != CLOSED_HARMONY


def test_adapter_toggle_close_resets_harmony_status_to_closed():
    fixture = build_screen1_visual_fixture_v1()
    view = build_qml_view_model_from_fixture(fixture, "screen1-default-3panel")
    adapter = Screen1QmlInteractionAdapter(
        view_model=view,
        harmony_controller=HarmonicMatchLibraryController(),
    )
    assert adapter.toggle_harmonic_match() is True
    assert view.harmony_status != CLOSED_HARMONY
    assert adapter.toggle_harmonic_match() is False
    assert adapter.harmonic_match_open is False
    assert view.harmony_status == CLOSED_HARMONY


def test_v2_active_source_never_falls_back_to_no_library_selected():
    fixture = build_screen1_visual_fixture_v2()
    view = build_qml_view_model_from_fixture_v2(fixture, "screen1-active-source")
    assert view.has_active_source is True
    assert view.browser_context == "Techno"
    assert view.browser_context != NO_LIBRARY


def test_v2_harmonic_open_status_coherent_via_apply_helper():
    from src.workbench_visual_acceptance import resolve_screen1_visual_state_v2

    fixture = build_screen1_visual_fixture_v2()
    state = resolve_screen1_visual_state_v2(fixture, "screen1-harmonic-open")
    view = build_qml_view_model_from_fixture_v2(fixture, "screen1-clean-start")
    adapter = Screen1QmlInteractionAdapter(
        view_model=view,
        harmony_controller=HarmonicMatchLibraryController(),
    )
    apply_screen1_visual_state_v2(view, adapter, fixture, state)
    assert adapter.harmonic_match_open is True
    assert view.harmony_status != CLOSED_HARMONY
    assert view.browser_context != NO_LIBRARY
    assert len(view.harmony_rows) >= 1


def test_clean_start_keeps_no_library_selected():
    view = Screen1QmlViewModel.baseline("screen1-default-3panel")
    view.set_workspace_materialization(
        has_active_source=False,
        calm_canvas_visible=True,
        browser_materialized=False,
        live_kit_materialized=False,
    )
    view.browser_context = NO_LIBRARY
    view.browser_rows = ()
    adapter = Screen1QmlInteractionAdapter(view_model=view)
    assert adapter.sync_visible_state_labels() is False
    assert view.browser_context == NO_LIBRARY
    assert view.harmony_status == CLOSED_HARMONY
