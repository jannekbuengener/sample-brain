"""#782 / #831 producer transport zone — structure, ownership, geometry.

After #831: header LEFT / NAV center / TRANSPORT right. Browser search stays contextual.
"""

from __future__ import annotations

import importlib.util

import pytest

from src.workbench_qml import QML_SOURCE

PY_SIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None

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


def test_header_exposes_left_nav_transport_zones():
    header = _header_block()
    assert 'objectName: "headerLeftZone"' in header
    assert 'objectName: "headerNavZone"' in header
    assert 'objectName: "headerTransportZone"' in header
    assert "Sample Brain" in header
    assert header.index('objectName: "headerLeftZone"') < header.index(
        'objectName: "headerNavZone"'
    )
    assert header.index('objectName: "headerNavZone"') < header.index(
        'objectName: "headerTransportZone"'
    )


def test_transport_zone_keeps_master_grid_sync_without_harmonic_header():
    """#843: Harmonic Matches producer entry leaves the header; MASTER/GRID/SYNC stay."""
    header = _header_block()
    transport = header[header.index('objectName: "headerTransportZone"') :]
    assert 'text: "MASTER"' in transport
    assert 'text: "GRID"' in transport
    assert 'text: "SYNC"' in transport
    assert 'objectName: "harmonicMatchButton"' not in transport
    assert 'Accessible.name: "Harmonic Match"' not in transport
    assert "activateHarmonicMatchToggle()" in QML_SOURCE
    assert QML_SOURCE.count("toggleHarmonicMatch()") == 1

    nav = header[
        header.index('objectName: "headerNavZone"') : header.index(
            'objectName: "headerTransportZone"'
        )
    ]
    assert 'objectName: "programNavStepSequencer"' in nav
    assert 'objectName: "displayPreferencesOverflow"' in transport
    assert 'objectName: "harmonicMatchButton"' not in header
    assert 'objectName: "browserSearch"' not in header


def test_harmonic_match_header_button_removed_and_not_in_browser_chrome():
    assert 'objectName: "harmonicMatchButton"' not in QML_SOURCE
    assert QML_SOURCE.count("toggleHarmonicMatch()") == 1
    browser = _browser_chrome_block()
    assert 'objectName: "harmonicMatchButton"' not in browser
    assert 'objectName: "browserSearch"' in browser
    assert QML_SOURCE.count('objectName: "browserSearch"') == 1


def test_nav_zone_uses_geometric_center_anchor():
    header = _header_block()
    nav_snip = header[
        header.index('objectName: "headerNavZone"') : header.index(
            'objectName: "headerTransportZone"'
        )
    ]
    assert "anchors.horizontalCenter" in nav_snip
    assert 'objectName: "producerCommandZone"' not in header


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
def test_runtime_nav_zone_is_geometrically_centered(size):
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
        nav = window.findChild(QQuickItem, "headerNavZone")
        transport = window.findChild(QQuickItem, "headerTransportZone")
        harmonic = window.findChild(QQuickItem, "harmonicMatchButton")
        search = window.findChild(QQuickItem, "browserSearch")
        step_seq = window.findChild(QQuickItem, "programNavStepSequencer")
        prefs = window.findChild(QQuickItem, "displayPreferencesOverflow")

        assert all(
            item is not None
            for item in (header, left, nav, transport, search, step_seq, prefs)
        )
        assert harmonic is None
        assert left.x() < nav.x()
        assert nav.x() + nav.width() <= transport.x() + transport.width() + 1.0
        assert search.parentItem() is not None
        browser = window.findChild(QQuickItem, "browserPane")
        assert browser is not None
        assert search.mapToItem(browser, 0, 0).y() >= 0

        _assert_centered(nav, header, label=f"{width}x{height}")

        assert nav.x() >= 0
        assert nav.x() + nav.width() <= header.width() + 1.0
        transport_in_header = transport.mapToItem(header, 0, 0)
        assert transport_in_header.x() > header.width() * 0.45
        prefs_in_header = prefs.mapToItem(header, 0, 0)
        assert prefs_in_header.x() > header.width() * 0.45
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
        nav = window.findChild(QQuickItem, "headerNavZone")
        assert header is not None and nav is not None

        centers: list[float] = []

        def capture(label: str) -> None:
            settle(app)
            engine._screen1_interaction_bridge.refreshState()
            engine._screen1_layout_model.syncFromInteraction()
            settle(app)
            _assert_centered(nav, header, label=label)
            centers.append(_zone_center_x(nav))

        capture("library+browser+livekit")

        adapter.harmonic_match_open = True
        capture("harmony_open")

        adapter.view_model.set_library_revealed(False)
        capture("library_collapsed")

        adapter.harmonic_match_open = False
        capture("harmony_closed_library_collapsed")

        assert max(centers) - min(centers) <= CENTER_TOLERANCE_MIN_PX
    finally:
        window.close()
        app.processEvents()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_runtime_harmonic_match_roundtrip_via_845_helper_not_header_button():
    """#843 removes header button; #845 toggle helper remains for open/close."""
    from PySide6.QtQuick import QQuickItem

    app, engine, window, adapter, settle = _build_screen1_window()
    try:
        window.setWidth(1600)
        window.setHeight(900)
        settle(app)

        toggle = window.findChild(QQuickItem, "harmonicMatchButton")
        harmony = window.findChild(QQuickItem, "harmonicMatchList")
        search = window.findChild(QQuickItem, "browserSearch")
        assert toggle is None
        assert harmony is not None and search is not None

        bridge = engine._screen1_interaction_bridge
        bridge.toggleHarmonicMatch()
        settle(app)
        assert adapter.harmonic_match_open is True

        bridge.toggleHarmonicMatch()
        settle(app)
        assert adapter.harmonic_match_open is False

        search.forceActiveFocus()
        settle(app)
        assert search.property("activeFocus") is True
    finally:
        window.close()
        app.processEvents()
