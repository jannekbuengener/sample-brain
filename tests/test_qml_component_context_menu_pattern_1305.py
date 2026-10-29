"""#1305 focused pattern: QML component coverage for sample context menu.

Demonstrates sample-brain-qml-component-test guidance against live Screen-1
harness conventions. Non-mutating beyond session-local kit intent callbacks;
does not redesign product UI.

Companion Python adapter contracts remain in
tests/test_workbench_qml_sample_context_menu_839.py.
"""

from __future__ import annotations

import importlib.util
import time

import pytest

from src.workbench_qml_spike import (
    Screen1QmlInteractionAdapter,
    build_qml_view_model_from_fixture,
)
from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="PySide6 Qt Quick ist in dieser Testumgebung nicht installiert.",
)


def _wait_until(predicate, *, timeout_sec: float = 2.0, app=None) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if predicate():
            return True
        if app is not None:
            app.processEvents()
        time.sleep(0.01)
    return bool(predicate())


def _cleanup(engine, window, app) -> None:
    window.close()
    app.processEvents()
    timer = getattr(engine, "_screen1_waveform_timer", None)
    if timer is not None:
        timer.stop()
    loader = getattr(engine, "_screen1_waveform_loader", None)
    if loader is not None:
        loader.close()


def test_qml_right_click_add_to_kit_exactly_once_keeps_selection():
    """Scenario A: real pointer path — not adapter-only bridge calls."""
    from PySide6.QtCore import QObject, QPointF, Qt
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest

    from src.workbench_qml_spike import _qml_engine, _settle_qml_frame

    added: list[object] = []
    fixture = build_screen1_visual_fixture_v1()
    assert len(fixture.browser_rows) >= 2
    view_model = build_qml_view_model_from_fixture(fixture, "screen1-default-3panel")
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        on_add_to_kit_requested=added.append,
    )
    adapter.select_row(0)
    assert view_model.selected_browser_index == 0

    app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    window.show()
    QTest.qWaitForWindowExposed(window, 5000)
    _settle_qml_frame(app)
    try:
        browser = window.findChild(QQuickItem, "browserList")
        # Popup is not a QQuickItem in this stack; find as QObject (see #770 tests).
        menu = window.findChild(QObject, "sampleContextMenu")
        assert browser is not None and menu is not None

        bridge = engine._screen1_interaction_bridge
        intents: list[str] = []
        bridge.addToKitIntent.connect(intents.append)

        row_height = float(
            window.property("densityRowHeight") or browser.property("rowHeight") or 30
        )
        # Click center of row index 1 (unselected).
        row_b = browser.mapToScene(
            QPointF(float(browser.width()) * 0.55, 1 * row_height + row_height / 2)
        ).toPoint()
        QTest.mouseClick(window, Qt.RightButton, Qt.NoModifier, row_b)
        assert _wait_until(lambda: bool(menu.property("visible")), app=app)
        assert view_model.selected_browser_index == 0
        assert adapter.sample_context_target is fixture.browser_rows[1]

        # Activate first Popup action (Add to Kit) via real left-click on the
        # menu item hit zone — not bridge.contextAddToKit().
        pane = window.findChild(QQuickItem, "browserPane")
        assert pane is not None
        menu_x = float(menu.property("x") or 0)
        menu_y = float(menu.property("y") or 0)
        add_point = pane.mapToScene(QPointF(menu_x + 100.0, menu_y + 22.0)).toPoint()
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, add_point)
        assert _wait_until(lambda: len(intents) >= 1 or len(added) >= 1, app=app)

        assert len(intents) == 1
        assert added == [fixture.browser_rows[1]]
        assert intents[0] == (
            fixture.browser_rows[1].relative_path or str(fixture.browser_rows[1].path)
        )
        assert view_model.selected_browser_index == 0
        assert adapter.sample_context_target is None
    finally:
        _cleanup(engine, window, app)


def test_qml_menu_key_opens_context_for_selected_index_not_hover_row():
    """Scenario A companion: keyboard entry uses selectedBrowserIndex."""
    from PySide6.QtCore import QObject, Qt
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest

    from src.workbench_qml_spike import _qml_engine, _settle_qml_frame

    fixture = build_screen1_visual_fixture_v1()
    assert len(fixture.browser_rows) >= 2
    view_model = build_qml_view_model_from_fixture(fixture, "screen1-default-3panel")
    adapter = Screen1QmlInteractionAdapter(view_model=view_model)
    adapter.select_row(0)

    app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    window.show()
    QTest.qWaitForWindowExposed(window, 5000)
    _settle_qml_frame(app)
    try:
        browser = window.findChild(QQuickItem, "browserList")
        menu = window.findChild(QObject, "sampleContextMenu")
        assert browser is not None and menu is not None

        browser.forceActiveFocus()
        app.processEvents()
        QTest.keyClick(window, Qt.Key_Menu)
        assert _wait_until(lambda: bool(menu.property("visible")), app=app)
        assert view_model.selected_browser_index == 0
        assert adapter.sample_context_target is fixture.browser_rows[0]

        QTest.keyClick(window, Qt.Key_Escape)
        assert _wait_until(lambda: not bool(menu.property("visible")), app=app)
        assert adapter.sample_context_target is None
        assert view_model.selected_browser_index == 0
    finally:
        _cleanup(engine, window, app)
