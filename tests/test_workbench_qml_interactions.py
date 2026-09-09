from __future__ import annotations

import importlib.util

import pytest

from src.workbench_harmony import HarmonicMatchLibraryController
from src.workbench_qml_spike import (
    Screen1QmlInteractionAdapter,
    Screen1QmlViewModel,
    build_qml_view_model_from_fixture,
)
from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1


def _adapter(*, browse_command=None, harmony_controller=None):
    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(
        fixture,
        "screen1-default-3panel",
        on_browser_selected=browse_command,
    )
    return fixture, view_model, Screen1QmlInteractionAdapter(
        view_model=view_model,
        harmony_controller=harmony_controller,
    )


def test_row_click_selects_exact_row_updates_view_state_and_dispatches_once():
    dispatched = []
    fixture, view_model, adapter = _adapter(browse_command=dispatched.append)

    selected = adapter.select_row(4)

    assert selected is fixture.browser_rows[4]
    assert view_model.selected_browser_index == 4
    assert adapter.selected_browser_index == 4
    assert dispatched == [fixture.browser_rows[4]]


def test_browser_arrow_navigation_reuses_single_browse_command_and_clamps_edges():
    dispatched = []
    fixture, view_model, adapter = _adapter(browse_command=dispatched.append)

    assert adapter.navigate_browser("next", browser_has_focus=True) is fixture.browser_rows[3]
    assert view_model.selected_browser_index == 3
    assert dispatched == [fixture.browser_rows[3]]

    adapter.select_row(len(fixture.browser_rows) - 1)
    dispatched.clear()
    assert adapter.navigate_browser("next", browser_has_focus=True) is fixture.browser_rows[-1]
    assert dispatched == []

    adapter.select_row(0)
    dispatched.clear()
    assert adapter.navigate_browser("previous", browser_has_focus=True) is fixture.browser_rows[0]
    assert dispatched == []


def test_browser_arrows_do_not_capture_text_field_focus():
    dispatched = []
    fixture, view_model, adapter = _adapter(browse_command=dispatched.append)
    initial_index = view_model.selected_browser_index

    assert adapter.navigate_browser("next", browser_has_focus=False) is None
    assert view_model.selected_browser_index == initial_index
    assert dispatched == []
    assert fixture.browser_rows[initial_index] is view_model.browser_rows[initial_index].source_row


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
    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(
        fixture,
        "screen1-default-3panel",
        on_browser_selected=dispatched.append,
    )
    app, engine, window = _qml_engine(view_model)
    window.show()
    _settle_qml_frame(app)
    try:
        browser = window.findChild(QQuickItem, "browserList")
        search = window.findChild(QObject, "browserSearch")
        toggle = window.findChild(QQuickItem, "harmonicMatchButton")
        assert browser is not None and search is not None and toggle is not None

        row_four = browser.mapToScene(QPointF(20, 4 * 58 + 29)).toPoint()
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, row_four)
        app.processEvents()
        assert view_model.selected_browser_index == 4
        assert dispatched == [fixture.browser_rows[4]]

        search.forceActiveFocus()
        QTest.keyClick(window, Qt.Key_Down)
        app.processEvents()
        assert view_model.selected_browser_index == 4

        browser.forceActiveFocus()
        QTest.keyClick(window, Qt.Key_Up)
        app.processEvents()
        assert view_model.selected_browser_index == 3
        assert dispatched == [fixture.browser_rows[4], fixture.browser_rows[3]]

        toggle_point = toggle.mapToScene(QPointF(8, 8)).toPoint()
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, toggle_point)
        app.processEvents()
        assert window.property("interaction").property("harmonicMatchOpen") is True
        assert engine._screen1_interaction_adapter.harmony_controller.anchor is fixture.browser_rows[3]
    finally:
        window.close()
        app.processEvents()
