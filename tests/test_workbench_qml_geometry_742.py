"""#742 runtime QML pane geometry — Row owns horizontal workspace layout.

Regression for the failure where Browser/Harmony/Live Kit had non-zero widths
but shared runtime x=0 because libraryRevealAffordance used horizontal anchors
as a direct workspaceRow child (Qt: "Row will not function").
"""

from __future__ import annotations

import importlib.util

import pytest

from src.workbench_qml import QML_SOURCE

PY_SIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None


def test_qml_library_reveal_affordance_is_overlay_not_row_child():
    """Affordance must be declared outside workspaceRow pane flow."""
    row_marker = 'objectName: "workspaceRow"'
    affordance_marker = 'objectName: "libraryRevealAffordance"'
    live_kit_marker = 'objectName: "liveKitPane"'
    handle_library_marker = 'objectName: "elasticHandleAfterLibrary"'
    assert row_marker in QML_SOURCE
    assert affordance_marker in QML_SOURCE
    assert live_kit_marker in QML_SOURCE
    # Overlay sibling after the pane/handle flow (not between library and handles).
    assert QML_SOURCE.index(affordance_marker) > QML_SOURCE.index(live_kit_marker)
    # Direct Row children between libraryPane and the first handle must not host
    # the edge affordance (that mix broke Row x-ownership).
    library_block = QML_SOURCE.index('objectName: "libraryPane"')
    handle_block = QML_SOURCE.index(handle_library_marker)
    between = QML_SOURCE[library_block:handle_block]
    assert affordance_marker not in between
    assert "overlay, not a workspaceRow child" in QML_SOURCE


def _assert_no_horizontal_overlap(left, right, *, label: str) -> None:
    assert left.isVisible() and right.isVisible()
    assert left.width() > 0 and right.width() > 0
    assert left.x() + left.width() <= right.x() + 1.0, label


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_qml_runtime_pane_x_ordering_four_disclosure_states():
    """QQuickItem geometry: visible panes must not share the same x origin."""
    from PySide6.QtCore import qInstallMessageHandler
    from PySide6.QtQuick import QQuickItem

    from src.workbench_harmony import HarmonicMatchLibraryController
    from src.workbench_qml import Screen1QmlInteractionAdapter
    from src.workbench_qml_spike import (
        _qml_engine,
        _settle_qml_frame,
        build_qml_view_model_from_fixture,
    )
    from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1

    warnings: list[str] = []

    def _qt_handler(_mode, _context, message):  # noqa: ANN001
        text = str(message)
        if "Row will not function" in text or "anchors for items inside Row" in text:
            warnings.append(text)

    qInstallMessageHandler(_qt_handler)

    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(fixture, "screen1-default-3panel")
    view_model.set_library_revealed(False)
    view_model.set_workspace_materialization(
        has_active_source=True,
        calm_canvas_visible=False,
        browser_materialized=True,
        live_kit_materialized=False,
    )
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        harmony_controller=HarmonicMatchLibraryController(),
    )
    adapter.harmonic_match_open = False

    app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    window.show()
    _settle_qml_frame(app)
    try:
        browser = window.findChild(QQuickItem, "browserPane")
        harmony = window.findChild(QQuickItem, "harmonyPane")
        live_kit = window.findChild(QQuickItem, "liveKitPane")
        handle_browser = window.findChild(QQuickItem, "elasticHandleAfterBrowser")
        handle_harmony = window.findChild(QQuickItem, "elasticHandleAfterHarmony")
        workspace = window.findChild(QQuickItem, "workspaceRow")
        affordance = window.findChild(QQuickItem, "libraryRevealAffordance")
        assert all(
            item is not None
            for item in (
                browser,
                harmony,
                live_kit,
                handle_browser,
                handle_harmony,
                workspace,
                affordance,
            )
        )

        def settle() -> None:
            engine._screen1_interaction_bridge.refreshState()
            engine._screen1_layout_model.syncFromInteraction()
            app.processEvents()
            _settle_qml_frame(app)

        # 1) Browser only (Library collapsed, Harmony closed, Live Kit hidden)
        settle()
        assert browser.isVisible() and browser.width() > 0
        assert browser.x() >= 0
        assert not live_kit.isVisible() or live_kit.width() == 0
        assert harmony.width() == 0 or harmony.opacity() == 0

        # 2) Browser + Harmony
        adapter.harmonic_match_open = True
        settle()
        assert browser.isVisible() and harmony.isVisible()
        assert browser.width() > 0 and harmony.width() > 0
        assert browser.x() < harmony.x()
        assert not (browser.x() == 0 and harmony.x() == 0)
        _assert_no_horizontal_overlap(browser, harmony, label="browser/harmony overlap")
        if handle_browser.isVisible() and handle_browser.width() > 0:
            assert browser.x() < handle_browser.x() < harmony.x()

        # 3) Browser + Live Kit (Harmony closed)
        adapter.harmonic_match_open = False
        view_model.set_workspace_materialization(
            has_active_source=True,
            calm_canvas_visible=False,
            browser_materialized=True,
            live_kit_materialized=True,
        )
        settle()
        assert browser.isVisible() and live_kit.isVisible()
        assert browser.width() > 0 and live_kit.width() > 0
        assert browser.x() < live_kit.x()
        assert not (browser.x() == 0 and live_kit.x() == 0)
        _assert_no_horizontal_overlap(browser, live_kit, label="browser/livekit overlap")

        # 4) Browser + Harmony + Live Kit (failure case from RUNTIME_DEFECT_FOUND)
        adapter.harmonic_match_open = True
        settle()
        assert browser.isVisible() and harmony.isVisible() and live_kit.isVisible()
        assert browser.width() > 0 and harmony.width() > 0 and live_kit.width() > 0
        xs = (browser.x(), harmony.x(), live_kit.x())
        assert not (xs[0] == 0 and xs[1] == 0 and xs[2] == 0)
        assert browser.x() < harmony.x() < live_kit.x()
        if handle_browser.isVisible() and handle_browser.width() > 0:
            assert browser.x() < handle_browser.x() < harmony.x()
        if handle_harmony.isVisible() and handle_harmony.width() > 0:
            assert harmony.x() < handle_harmony.x() < live_kit.x()
        _assert_no_horizontal_overlap(browser, harmony, label="3p browser/harmony")
        _assert_no_horizontal_overlap(harmony, live_kit, label="3p harmony/livekit")
        total = (
            browser.width()
            + harmony.width()
            + live_kit.width()
            + handle_browser.width()
            + handle_harmony.width()
        )
        assert total <= workspace.width() + 2.0
        assert affordance.isVisible()
        assert affordance.parentItem() is not workspace
        assert not warnings, f"Row positioner still broken: {warnings}"
    finally:
        qInstallMessageHandler(None)
        window.close()
        app.processEvents()
        timer = getattr(engine, "_screen1_waveform_timer", None)
        if timer is not None:
            timer.stop()
        loader = getattr(engine, "_screen1_waveform_loader", None)
        if loader is not None:
            loader.close()
