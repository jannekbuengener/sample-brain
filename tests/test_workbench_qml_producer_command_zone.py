"""#782 producer command zone — structure, ownership, geometry.

Header LEFT / CENTER / RIGHT hierarchy with MASTER/GRID/SYNC + Harmonic Match
geometrically centered. Browser Search stays contextual. No second music state.
"""

from __future__ import annotations

import importlib.util

import pytest

from src.workbench_qml import QML_SOURCE

PY_SIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None

# Horizontal center of producerCommandZone must stay within this fraction of
# header/window half-width (runtime geometry, not source-string).
CENTER_TOLERANCE_RATIO = 0.04
CENTER_TOLERANCE_MIN_PX = 24


def _header_block() -> str:
    start = QML_SOURCE.index('objectName: "screen1Header"')
    end = QML_SOURCE.index('objectName: "workspaceRow"', start)
    return QML_SOURCE[start:end]


def _browser_chrome_block() -> str:
    start = QML_SOURCE.index('objectName: "browserPane"')
    end = QML_SOURCE.index('objectName: "browserList"', start)
    return QML_SOURCE[start:end]


def test_header_exposes_left_center_right_zones():
    header = _header_block()
    assert 'objectName: "headerLeftZone"' in header
    assert 'objectName: "producerCommandZone"' in header
    assert 'objectName: "headerRightZone"' in header
    assert "Sample Brain" in header
    assert header.index('objectName: "headerLeftZone"') < header.index(
        'objectName: "producerCommandZone"'
    )
    assert header.index('objectName: "producerCommandZone"') < header.index(
        'objectName: "headerRightZone"'
    )


def test_producer_command_zone_keeps_master_grid_sync_and_moves_harmonic_match():
    header = _header_block()
    center = header[
        header.index('objectName: "producerCommandZone"') : header.index(
            'objectName: "headerRightZone"'
        )
    ]
    assert 'text: "MASTER"' in center
    assert 'text: "GRID"' in center
    assert 'text: "SYNC"' in center
    assert 'objectName: "harmonicMatchButton"' in center
    assert "toggleHarmonicMatch()" in center
    assert 'Accessible.name: "Harmonic Match"' in center

    right = header[header.index('objectName: "headerRightZone"') :]
    assert 'objectName: "openChannelRackButton"' in right
    assert 'objectName: "displayPreferencesOverflow"' in right
    assert 'objectName: "harmonicMatchButton"' not in right
    assert 'objectName: "browserSearch"' not in header


def test_harmonic_match_is_single_control_not_in_browser_chrome():
    assert QML_SOURCE.count('objectName: "harmonicMatchButton"') == 1
    assert QML_SOURCE.count("toggleHarmonicMatch()") == 1
    browser = _browser_chrome_block()
    assert 'objectName: "harmonicMatchButton"' not in browser
    assert 'objectName: "browserSearch"' in browser
    assert QML_SOURCE.count('objectName: "browserSearch"') == 1


def test_producer_zone_uses_geometric_center_anchor_not_fill_spacer():
    header = _header_block()
    center_snip = header[
        header.index('objectName: "producerCommandZone"') : header.index(
            'objectName: "headerRightZone"'
        )
    ]
    assert "anchors.horizontalCenter" in center_snip
    # Old fill-spacer pattern must not own the producer controls.
    assert "Item { Layout.fillWidth: true }" not in header.split(
        'objectName: "producerCommandZone"'
    )[0]


def _zone_center_x(item) -> float:
    return float(item.x()) + float(item.width()) / 2.0


def _assert_centered(zone, reference, *, label: str) -> None:
    ref_center = float(reference.width()) / 2.0
    zone_center = _zone_center_x(zone)
    tol = max(CENTER_TOLERANCE_MIN_PX, float(reference.width()) * CENTER_TOLERANCE_RATIO)
    delta = abs(zone_center - ref_center)
    assert delta <= tol, f"{label}: center delta={delta:.1f}px tol={tol:.1f}px"


def _build_screen1_window(*, harmonic_open: bool = False, library_revealed: bool = True):
    from src.workbench_harmony import HarmonicMatchLibraryController
    from src.workbench_qml import Screen1QmlInteractionAdapter
    from src.workbench_qml_spike import (
        _qml_engine,
        _settle_qml_frame,
        build_qml_view_model_from_fixture,
    )
    from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1

    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(fixture, "screen1-default-3panel")
    view_model.set_library_revealed(library_revealed)
    view_model.set_workspace_materialization(
        has_active_source=True,
        calm_canvas_visible=False,
        browser_materialized=True,
        live_kit_materialized=True,
    )
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        harmony_controller=HarmonicMatchLibraryController(),
    )
    adapter.harmonic_match_open = harmonic_open
    app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    window.show()
    _settle_qml_frame(app)
    return app, engine, window, adapter, _settle_qml_frame


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
@pytest.mark.parametrize("size", [(1120, 640), (1600, 900)])
def test_runtime_producer_zone_is_geometrically_centered(size):
    from PySide6.QtQuick import QQuickItem

    width, height = size
    app, engine, window, adapter, settle = _build_screen1_window()
    try:
        window.setWidth(width)
        window.setHeight(height)
        settle(app)
        settle(app)

        header = window.findChild(QQuickItem, "screen1Header")
        left = window.findChild(QQuickItem, "headerLeftZone")
        center = window.findChild(QQuickItem, "producerCommandZone")
        right = window.findChild(QQuickItem, "headerRightZone")
        harmonic = window.findChild(QQuickItem, "harmonicMatchButton")
        search = window.findChild(QQuickItem, "browserSearch")
        channel = window.findChild(QQuickItem, "openChannelRackButton")
        prefs = window.findChild(QQuickItem, "displayPreferencesOverflow")

        assert all(
            item is not None
            for item in (header, left, center, right, harmonic, search, channel, prefs)
        )
        assert left.x() < center.x()
        assert center.x() >= left.x() + left.width() - 1.0
        assert center.x() + center.width() <= right.x() + 1.0
        assert search.parentItem() is not None
        # Search remains under browser pane, not header.
        browser = window.findChild(QQuickItem, "browserPane")
        assert browser is not None
        assert search.mapToItem(browser, 0, 0).y() >= 0
        harmonic_in_header = harmonic.mapToItem(header, 0, 0)
        assert 0 <= harmonic_in_header.y() < header.height()
        assert 0 <= harmonic_in_header.x() < header.width()

        _assert_centered(center, header, label=f"{width}x{height}")

        # No clipping: center fully inside header bounds.
        assert center.x() >= 0
        assert center.x() + center.width() <= header.width() + 1.0
        # Secondary controls must not own the geometric center strip.
        channel_in_header = channel.mapToItem(header, 0, 0)
        assert channel_in_header.x() > header.width() * 0.55
        prefs_in_header = prefs.mapToItem(header, 0, 0)
        assert prefs_in_header.x() > header.width() * 0.55
        assert abs(
            (harmonic_in_header.x() + harmonic.width() / 2.0) - (header.width() / 2.0)
        ) < header.width() * 0.20
    finally:
        window.close()
        app.processEvents()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_runtime_center_stable_across_pane_disclosure_states():
    from PySide6.QtQuick import QQuickItem

    app, engine, window, adapter, settle = _build_screen1_window(harmonic_open=False)
    try:
        window.setWidth(1600)
        window.setHeight(900)
        settle(app)

        header = window.findChild(QQuickItem, "screen1Header")
        center = window.findChild(QQuickItem, "producerCommandZone")
        assert header is not None and center is not None

        centers: list[float] = []

        def capture(label: str) -> None:
            settle(app)
            engine._screen1_interaction_bridge.refreshState()
            engine._screen1_layout_model.syncFromInteraction()
            settle(app)
            _assert_centered(center, header, label=label)
            centers.append(_zone_center_x(center))

        capture("library+browser+livekit")

        adapter.harmonic_match_open = True
        capture("harmony_open")

        adapter.view_model.set_library_revealed(False)
        capture("library_collapsed")

        adapter.harmonic_match_open = False
        capture("harmony_closed_library_collapsed")

        # Same window width → center must not drift with pane widths.
        assert max(centers) - min(centers) <= CENTER_TOLERANCE_MIN_PX
    finally:
        window.close()
        app.processEvents()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_runtime_harmonic_match_from_center_zone_roundtrip():
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest

    app, engine, window, adapter, settle = _build_screen1_window()
    try:
        window.setWidth(1600)
        window.setHeight(900)
        settle(app)

        toggle = window.findChild(QQuickItem, "harmonicMatchButton")
        harmony = window.findChild(QQuickItem, "harmonicMatchList")
        search = window.findChild(QQuickItem, "browserSearch")
        assert toggle is not None and harmony is not None and search is not None

        point = toggle.mapToScene(QPointF(8, 8)).toPoint()
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)
        settle(app)
        assert adapter.harmonic_match_open is True

        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)
        settle(app)
        assert adapter.harmonic_match_open is False

        # Browser search still focusable after migration.
        search.forceActiveFocus()
        settle(app)
        assert search.property("activeFocus") is True
    finally:
        window.close()
        app.processEvents()
