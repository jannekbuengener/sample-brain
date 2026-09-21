from __future__ import annotations

import importlib.util

import pytest

from src.workbench_harmony import HarmonicMatchLibraryController
from src.workbench_controller import WorkbenchRow
from src.workbench_qml_spike import (
    Screen1QmlInteractionAdapter,
    Screen1QmlViewModel,
    build_qml_view_model_from_fixture,
)
from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1


def _adapter(
    *,
    browse_command=None,
    preview_command=None,
    preview_stop=None,
    add_to_kit_command=None,
    harmony_controller=None,
):
    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(
        fixture,
        "screen1-default-3panel",
        on_browser_selected=browse_command,
    )
    return fixture, view_model, Screen1QmlInteractionAdapter(
        view_model=view_model,
        harmony_controller=harmony_controller,
        on_preview_requested=preview_command,
        on_preview_stopped=preview_stop,
        on_add_to_kit_requested=add_to_kit_command,
    )


def test_row_click_selects_exact_row_updates_view_state_and_dispatches_once():
    dispatched = []
    previews = []
    fixture, view_model, adapter = _adapter(
        browse_command=dispatched.append,
        preview_command=previews.append,
    )

    selected = adapter.select_row(4)

    assert selected is fixture.browser_rows[4]
    assert view_model.selected_browser_index == 4
    assert adapter.selected_browser_index == 4
    assert dispatched == [fixture.browser_rows[4]]
    assert previews == []


def test_waveform_intent_selects_and_dispatches_exactly_one_preview():
    dispatched = []
    previews = []
    fixture, view_model, adapter = _adapter(
        browse_command=dispatched.append,
        preview_command=previews.append,
    )

    selected = adapter.preview_row(4)

    assert selected is fixture.browser_rows[4]
    assert view_model.selected_browser_index == 4
    assert dispatched == [fixture.browser_rows[4]]
    assert previews == [fixture.browser_rows[4]]


def test_browser_arrow_navigation_reuses_single_browse_command_and_clamps_edges():
    dispatched = []
    previews = []
    fixture, view_model, adapter = _adapter(
        browse_command=dispatched.append,
        preview_command=previews.append,
    )

    assert adapter.navigate_browser("next", browser_has_focus=True) is fixture.browser_rows[3]
    assert view_model.selected_browser_index == 3
    assert dispatched == [fixture.browser_rows[3]]
    assert previews == [fixture.browser_rows[3]]

    adapter.select_row(len(fixture.browser_rows) - 1)
    dispatched.clear()
    previews.clear()
    assert adapter.navigate_browser("next", browser_has_focus=True) is fixture.browser_rows[-1]
    assert dispatched == []
    assert previews == []

    adapter.select_row(0)
    dispatched.clear()
    previews.clear()
    assert adapter.navigate_browser("previous", browser_has_focus=True) is fixture.browser_rows[0]
    assert dispatched == []
    assert previews == []


def test_browser_arrows_do_not_capture_text_field_focus():
    dispatched = []
    fixture, view_model, adapter = _adapter(browse_command=dispatched.append)
    initial_index = view_model.selected_browser_index

    assert adapter.navigate_browser("next", browser_has_focus=False) is None
    assert view_model.selected_browser_index == initial_index
    assert dispatched == []
    assert fixture.browser_rows[initial_index] is view_model.browser_rows[initial_index].source_row


def test_escape_stops_only_an_active_preview():
    stops = []
    fixture, _view_model, adapter = _adapter(
        preview_command=lambda _row: None,
        preview_stop=lambda: stops.append("stop"),
    )

    assert adapter.stop_preview() is False
    adapter.preview_row(2)
    assert adapter.preview_active is True
    assert adapter.stop_preview() is True
    assert adapter.preview_active is False
    assert adapter.stop_preview() is False
    assert stops == ["stop"]
    assert fixture.browser_rows[2] is not None


def test_add_to_kit_emits_intent_without_assigning_live_kit():
    added = []
    fixture, view_model, adapter = _adapter(add_to_kit_command=added.append)
    live_kit_before = view_model.live_kit_groups

    row = adapter.request_add_to_kit(4)

    assert row is fixture.browser_rows[4]
    assert added == [fixture.browser_rows[4]]
    assert view_model.live_kit_groups is live_kit_before


def test_browser_row_projects_real_metadata_and_empty_values_neutrally():
    fixture, view_model, _adapter_instance = _adapter()
    row = view_model.browser_rows[2]

    assert row.display_name == "TECH_BASS_01"
    assert row.sample_type == "Bass"
    assert row.bpm == "132"
    assert row.key == "F#"
    assert row.duration == "2.00s"
    assert row.waveform_envelope
    assert all(0.0 <= point <= 1.0 for point in row.waveform_envelope)

    missing = WorkbenchRow(
        display_name="UNKNOWN",
        relative_path="unknown.wav",
        path="unknown.wav",
        bpm=None,
        key=None,
        key_conf=None,
        loudness=None,
        brightness=None,
        sample_class="one_shot",
        pred_type=None,
        status="ok",
        details={},
    )
    from src.workbench_qml import _qml_row

    projected = _qml_row(missing)
    assert projected.sample_type == "—"
    assert projected.bpm == "—"
    assert projected.key == "—"
    assert projected.duration == "—"
    assert projected.waveform_envelope == ()


def test_browser_qml_uses_waveform_intent_and_has_no_row_play_button():
    from src.workbench_qml import QML_SOURCE

    assert "Canvas" in QML_SOURCE
    assert "previewRow(index)" in QML_SOURCE
    assert "addToKit(index)" in QML_SOURCE
    assert "stopPreview()" in QML_SOURCE
    assert 'text: "Play"' not in QML_SOURCE
    assert 'text: "▶"' not in QML_SOURCE


def test_harmonic_toggle_reuses_controller_and_preserves_browser_and_live_kit_state():
    controller_calls = []
    controller = HarmonicMatchLibraryController()
    original_set_anchor = controller.set_anchor

    def record_set_anchor(anchor, candidates):
        controller_calls.append((anchor, tuple(candidates)))
        original_set_anchor(anchor, candidates)

    controller.set_anchor = record_set_anchor
    _, view_model, adapter = _adapter(harmony_controller=controller)
    live_kit_before = view_model.live_kit_groups
    selected_before = view_model.selected_browser_index

    assert adapter.harmonic_match_open is False
    assert adapter.toggle_harmonic_match() is True
    assert controller.anchor is view_model.browser_rows[selected_before].source_row
    assert len(controller_calls) == 1
    assert adapter.harmonic_match_open is True
    assert view_model.selected_browser_index == selected_before
    assert view_model.live_kit_groups is live_kit_before
    assert adapter.toggle_harmonic_match() is False
    assert len(controller_calls) == 1
    assert view_model.selected_browser_index == selected_before
    assert view_model.live_kit_groups is live_kit_before


def test_harmonic_reopen_same_fingerprint_reuses_results_selection_and_scroll():
    calls = []
    controller = HarmonicMatchLibraryController()
    original = controller.set_anchor

    def record(anchor, candidates):
        calls.append((anchor, tuple(candidates)))
        original(anchor, candidates)

    controller.set_anchor = record
    _fixture, view_model, adapter = _adapter(harmony_controller=controller)

    assert adapter.toggle_harmonic_match() is True
    adapter.set_harmonic_match_scroll_y(42)
    if view_model.harmony_rows:
        adapter.select_harmonic_match(min(1, len(view_model.harmony_rows) - 1))
    selected = adapter.selected_harmonic_match_index
    assert adapter.toggle_harmonic_match() is False
    assert adapter.toggle_harmonic_match() is True
    assert len(calls) == 1
    assert adapter.selected_harmonic_match_index == selected
    assert adapter.harmonic_match_scroll_y == 42


def test_harmonic_no_browser_selection_stays_closed_without_finder_call():
    calls = []
    controller = HarmonicMatchLibraryController(finder=lambda *_args: calls.append(True))
    _fixture, view_model, adapter = _adapter(harmony_controller=controller)
    view_model.browser_rows = ()
    view_model.selected_browser_index = -1

    assert adapter.toggle_harmonic_match() is False
    assert adapter.harmonic_match_open is False
    assert calls == []
    assert view_model.harmony_rows == ()
    assert "Kein Sample" in view_model.harmony_status


def test_harmonic_match_row_actions_are_local_preview_and_existing_add_intent_only():
    previews = []
    added = []
    _fixture, view_model, adapter = _adapter(
        harmony_controller=HarmonicMatchLibraryController(),
        preview_command=previews.append,
        add_to_kit_command=added.append,
    )
    assert adapter.toggle_harmonic_match() is True
    if not view_model.harmony_rows:
        pytest.skip("Fixture has no safe harmonic suggestion.")
    live_kit_before = view_model.live_kit_groups
    row = adapter.select_harmonic_match(0)
    assert previews == []
    assert adapter.preview_harmonic_match(0) is row
    assert previews == [row]
    assert adapter.request_add_harmonic_match_to_kit(0) is row
    assert added == [row]
    assert view_model.live_kit_groups is live_kit_before


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="PySide6 Qt Quick ist in dieser Testumgebung nicht installiert.",
)
def test_qml_real_interaction_smoke_click_arrows_focus_and_harmonic_toggle():
    from PySide6.QtCore import QObject, QPointF, Qt
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest

    from src.workbench_qml_spike import _qml_engine, _settle_qml_frame

    dispatched = []
    previews = []
    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(
        fixture,
        "screen1-default-3panel",
        on_browser_selected=dispatched.append,
    )
    interaction_adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        harmony_controller=HarmonicMatchLibraryController(),
        on_preview_requested=previews.append,
    )
    app, engine, window = _qml_engine(
        view_model,
        interaction_adapter=interaction_adapter,
    )
    window.show()
    _settle_qml_frame(app)
    try:
        browser = window.findChild(QQuickItem, "browserList")
        search = window.findChild(QObject, "browserSearch")
        toggle = window.findChild(QQuickItem, "harmonicMatchButton")
        assert browser is not None and search is not None and toggle is not None

        row_four = browser.mapToScene(QPointF(300, 4 * 66 + 33)).toPoint()
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, row_four)
        app.processEvents()
        assert view_model.selected_browser_index == 4
        assert dispatched == [fixture.browser_rows[4]]
        assert previews == []

        waveform_four = browser.mapToScene(QPointF(40, 4 * 66 + 33)).toPoint()
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, waveform_four)
        app.processEvents()
        assert view_model.selected_browser_index == 4
        assert previews == [fixture.browser_rows[4]]

        search.forceActiveFocus()
        QTest.keyClick(window, Qt.Key_Down)
        app.processEvents()
        assert view_model.selected_browser_index == 4

        browser.forceActiveFocus()
        QTest.keyClick(window, Qt.Key_Up)
        app.processEvents()
        assert view_model.selected_browser_index == 3
        assert dispatched == [fixture.browser_rows[4], fixture.browser_rows[3]]
        assert previews == [fixture.browser_rows[4], fixture.browser_rows[3]]

        QTest.keyClick(window, Qt.Key_Escape)
        app.processEvents()
        assert window.property("interaction").property("previewActive") is False

        add_intents = []
        engine._screen1_interaction_bridge.addToKitIntent.connect(add_intents.append)
        add_point = browser.mapToScene(
            QPointF(float(browser.property("width")) - 48, 4 * 66 + 33)
        ).toPoint()
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, add_point)
        app.processEvents()
        assert add_intents == [fixture.browser_rows[4].relative_path]
        assert view_model.selected_browser_index == 3

        toggle_point = toggle.mapToScene(QPointF(8, 8)).toPoint()
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, toggle_point)
        app.processEvents()
        assert window.property("interaction").property("harmonicMatchOpen") is True
        assert engine._screen1_interaction_adapter.harmony_controller.anchor is fixture.browser_rows[3]
    finally:
        window.close()
        app.processEvents()
