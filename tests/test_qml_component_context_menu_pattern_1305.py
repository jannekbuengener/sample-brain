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


class _ContextLoopStub:
    def __init__(self) -> None:
        from src.browser_loop_playback import BrowserLoopExtent

        self.owner_row = None
        self.extent = None
        self._extent_type = BrowserLoopExtent
        self.reduced_capability_reason = None
        self.loop_on_calls: list[object] = []
        self.loop_off_calls = 0

    @property
    def is_active(self) -> bool:
        return self.owner_row is not None and self.extent is not None

    def current_source_phase_frame(self):
        return 100 if self.is_active else None

    def loop_on(self, row):
        from src.browser_loop_playback import BrowserLoopResult

        self.loop_on_calls.append(row)
        self.owner_row = row
        self.extent = self._extent_type(100, 700, 1, (100, 700))
        return BrowserLoopResult(ok=True, owner_path=str(row.path), bar_count=1)

    def loop_off(self):
        from src.browser_loop_playback import BrowserLoopResult

        self.loop_off_calls += 1
        self.owner_row = None
        self.extent = None
        return BrowserLoopResult(ok=True, message="LOOP OFF")


def test_qml_right_click_loop_action_targets_b_exactly_once_without_selection_or_preview():
    from PySide6.QtCore import QObject, QPointF, Qt
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest

    from src.workbench_qml_spike import _qml_engine, _settle_qml_frame

    previews: list[object] = []
    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(fixture, "screen1-default-3panel")
    loop = _ContextLoopStub()
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        on_preview_requested=lambda row, **_kwargs: previews.append(row),
    )
    adapter.bind_browser_loop(loop)
    adapter.select_row(0)

    app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    window.show()
    QTest.qWaitForWindowExposed(window, 5000)
    _settle_qml_frame(app)
    try:
        browser = window.findChild(QQuickItem, "browserList")
        menu = window.findChild(QObject, "sampleContextMenu")
        loop_item = window.findChild(QQuickItem, "contextLoopItem")
        assert browser is not None and menu is not None and loop_item is not None

        row_height = float(window.property("densityRowHeight") or browser.property("rowHeight") or 30)
        row_b_point = browser.mapToScene(
            QPointF(float(browser.width()) * 0.55, row_height + row_height / 2)
        ).toPoint()
        QTest.mouseClick(window, Qt.RightButton, Qt.NoModifier, row_b_point)
        assert _wait_until(lambda: bool(menu.property("visible")), app=app)
        assert view_model.selected_browser_index == 0
        assert previews == []
        assert adapter.sample_context_target is fixture.browser_rows[1]
        assert str(menu.property("actionLoopLabel")) == "LOOP ON"

        click_point = loop_item.mapToScene(loop_item.boundingRect().center()).toPoint()
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, click_point)
        assert _wait_until(lambda: len(loop.loop_on_calls) == 1, app=app)

        assert loop.loop_on_calls == [fixture.browser_rows[1]]
        assert view_model.selected_browser_index == 0
        assert previews == []
    finally:
        _cleanup(engine, window, app)


def test_qml_context_loop_action_keyboard_spans_three_actions_and_escape_restores_browser_focus():
    from PySide6.QtCore import QObject, Qt
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest

    from src.workbench_qml_spike import _qml_engine, _settle_qml_frame

    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(fixture, "screen1-default-3panel")
    loop = _ContextLoopStub()
    adapter = Screen1QmlInteractionAdapter(view_model=view_model)
    adapter.bind_browser_loop(loop)
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
        assert int(menu.property("focusedAction")) == 0

        QTest.keyClick(window, Qt.Key_Down)
        QTest.keyClick(window, Qt.Key_Down)
        assert int(menu.property("focusedAction")) == 2
        QTest.keyClick(window, Qt.Key_Down)
        assert int(menu.property("focusedAction")) == 2

        QTest.keyClick(window, Qt.Key_Escape)
        assert _wait_until(lambda: not bool(menu.property("visible")), app=app)
        assert _wait_until(lambda: bool(browser.property("activeFocus")), app=app)
        assert adapter.sample_context_target is None
    finally:
        _cleanup(engine, window, app)


def test_qml_context_loop_action_accessible_press_dispatches_same_typed_intent_once():
    from PySide6.QtCore import QObject, Qt
    from PySide6.QtGui import QAccessible, QAccessibleActionInterface
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest

    from src.workbench_qml_spike import _qml_engine, _settle_qml_frame

    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(fixture, "screen1-default-3panel")
    loop = _ContextLoopStub()
    adapter = Screen1QmlInteractionAdapter(view_model=view_model)
    adapter.bind_browser_loop(loop)
    adapter.select_row(0)

    app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    window.show()
    QTest.qWaitForWindowExposed(window, 5000)
    _settle_qml_frame(app)
    try:
        browser = window.findChild(QQuickItem, "browserList")
        menu = window.findChild(QObject, "sampleContextMenu")
        loop_item = window.findChild(QQuickItem, "contextLoopItem")
        assert browser is not None and menu is not None and loop_item is not None

        browser.forceActiveFocus()
        QTest.keyClick(window, Qt.Key_Menu)
        assert _wait_until(lambda: bool(menu.property("visible")), app=app)

        iface = QAccessible.queryAccessibleInterface(loop_item)
        assert iface is not None
        action = iface.actionInterface()
        assert action is not None
        assert QAccessibleActionInterface.pressAction() in action.actionNames()
        action.doAction(QAccessibleActionInterface.pressAction())
        assert _wait_until(lambda: len(loop.loop_on_calls) == 1, app=app)
        assert loop.loop_on_calls == [fixture.browser_rows[0]]
    finally:
        _cleanup(engine, window, app)
