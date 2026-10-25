"""#831 program chrome — QML structure and runtime geometry (TEST_FREEZE).

## TEST_FREEZE_RECONCILIATION (#1077 / PRODUCT_WORKFLOW_CANON)

Historical #831 placed “Live Kit” in upper center navigation beside Browser /
Step Sequencer / Arrangement. Current product authority (#1075/#1076/#1077 +
Owner visual gate on `PROGRAM_CHROME_CONTRACT.md`) forbids that reading as a
top-level mode.

Consciously released from this freeze suite (moved to
`tests/test_workbench_live_kit_edit_1077.py`):
- `programNavLiveKit` in `headerNavRow`
- upper-chrome Live Kit label among mode peers
- Live Kit reveal/hide runtime via header nav clicks

Still frozen here: three-zone header geometry, Browser / Step Sequencer /
Arrangement objectNames in nav, footer/transport chrome structure, Browser
nav reveal-collapsed behavior.
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


def _footer_block() -> str:
    start = QML_SOURCE.index("footer:")
    end = QML_SOURCE.index("header:", start)
    return QML_SOURCE[start:end]


def test_program_chrome_header_zones_and_nav_labels() -> None:
    header = _header_block()
    assert 'objectName: "headerLeftZone"' in header
    assert 'objectName: "headerNavZone"' in header
    assert 'objectName: "headerTransportZone"' in header
    assert "Sample Brain" in header
    order = (
        header.index('objectName: "headerLeftZone"'),
        header.index('objectName: "headerNavZone"'),
        header.index('objectName: "headerTransportZone"'),
    )
    assert order[0] < order[1] < order[2]
    nav = header[
        header.index('objectName: "headerNavZone"') : header.index(
            'objectName: "headerTransportZone"'
        )
    ]
    for label, obj in (
        ("Edit", "programNavEdit"),
        ("Arrangement", "programNavArrangement"),
    ):
        assert label in nav
        assert f'objectName: "{obj}"' in nav
    assert nav.count('objectName: "programNavEdit"') == 1
    assert nav.count('text: "Edit"') == 1
    assert 'text: "Browser"' not in nav
    assert 'objectName: "programNavStepSequencer"' not in nav
    # #1077 Owner gate: Live Kit is not a mode peer in upper navigation.
    assert "programNavLiveKit" not in nav
    assert 'text: "Live Kit"' not in nav
    assert 'objectName: "producerCommandZone"' not in header
    assert 'objectName: "openChannelRackButton"' not in header


def test_program_chrome_transport_on_right_without_harmonic_header() -> None:
    header = _header_block()
    transport = header[header.index('objectName: "headerTransportZone"') :]
    assert 'text: "MASTER"' in transport
    assert 'text: "GRID"' not in transport
    assert 'text: "SYNC"' in transport
    assert transport.count('text: "SYNC"') == 1
    assert 'objectName: "syncButton"' in transport
    assert 'syncStateLabel' not in transport
    assert 'text: "ON"' not in transport
    assert 'text: "OFF"' not in transport
    assert 'objectName: "displayPreferencesOverflow"' in transport
    assert 'objectName: "harmonicMatchButton"' not in transport
    nav_snip = header[
        header.index('objectName: "headerNavZone"') : header.index(
            'objectName: "headerTransportZone"'
        )
    ]
    assert "idealX" in nav_snip or "anchors.horizontalCenter" in nav_snip
    assert 'objectName: "masterTempoValue"' in transport


def test_program_chrome_footer_hosts_context_status_without_scope_navigation() -> None:
    footer = _footer_block()
    assert 'objectName: "libraryScopeBar"' not in footer
    assert 'objectName: "contextHintPlacement"' in footer or 'objectName: "programFooterBand"' in footer
    assert 'objectName: "contextHintDisplay"' in footer
    assert 'objectName: "footerContextCenterLayer"' in footer
    assert 'objectName: "footerStatusZone"' in footer
    hint_block = footer.split('objectName: "contextHintDisplay"', 1)[1].split(
        "Accessible.ignored", 1
    )[0]
    assert (
        "horizontalCenter" in hint_block
        or "parent.width / 2" in hint_block
        or "mid -" in hint_block
    )
    assert "AlignRight" not in hint_block
    pane = QML_SOURCE.split("id: libraryPane", 1)[1].split(
        'objectName: "elasticHandleAfterLibrary"', 1
    )[0]
    assert 'objectName: "libraryScopeBar"' in pane
    assert pane.index('objectName: "libraryAddSourceButton"') < pane.index(
        'objectName: "libraryScopeBar"'
    )


def test_program_footer_is_global_chrome_across_screens() -> None:
    """#831 P2: program footer is global frame chrome, not Screen-1-only."""
    footer = _footer_block()
    band = footer.split('objectName: "programFooterBand"', 1)[1].split("Rectangle", 1)[0]
    assert 'visible: window.activeScreen === "screen1"' not in band
    assert "height:" in band


def test_program_nav_edit_handler_reveals_collapsed_browser() -> None:
    """#831 P2: Edit nav retains the #845 Browser reveal intent."""
    block = QML_SOURCE.split('objectName: "programNavEdit"', 1)[1].split(
        'objectName: "programNavArrangement"', 1
    )[0]
    assert "browserCollapsed" in block
    assert "toggleBrowserCollapsed" in block
    assert "returnToBrowser" in block


def test_program_chrome_header_reserves_three_zones_without_free_center_overlap() -> None:
    """#831 P2: nav zone is bounded by left/right zones (no free float overlap)."""
    header = _header_block()
    nav = header[
        header.index('objectName: "headerNavZone"') : header.index(
            'objectName: "headerTransportZone"'
        )
    ]
    assert "leftEdge" in nav
    assert "rightEdge" in nav
    assert "headerLeftZone" in nav
    assert "headerTransportZone" in nav
    assert "headerTransportZone.x - 12" in nav
    tempo = header[header.index('objectName: "headerTransportZone"') :]
    assert "maxWidth" in tempo


def _zone_center_x(item, reference=None) -> float:
    from PySide6.QtCore import QPointF

    if reference is None:
        return float(item.x()) + float(item.width()) / 2.0
    origin = item.mapToItem(reference, QPointF(0, 0))
    return float(origin.x()) + float(item.width()) / 2.0


def _assert_centered(zone, reference, *, label: str) -> None:
    ref_center = float(reference.width()) / 2.0
    zone_center = _zone_center_x(zone, reference)
    tol = max(CENTER_TOLERANCE_MIN_PX, float(reference.width()) * CENTER_TOLERANCE_RATIO)
    delta = abs(zone_center - ref_center)
    assert delta <= tol, f"{label}: center delta={delta:.1f}px tol={tol:.1f}px"


def _build_screen1_window(
    *,
    live_kit_materialized: bool = True,
    live_kit_drawer_open: bool | None = None,
    clear_live_kit_assignments: bool = False,
    with_session: bool = False,
):
    from src.workbench_harmony import HarmonicMatchLibraryController
    from src.workbench_live_kit import LiveKitState
    from src.workbench_qml import LiveKitPresenter, Screen1QmlInteractionAdapter
    from src.workbench_qml_spike import (
        _qml_engine,
        _settle_qml_frame,
        build_qml_view_model_from_fixture,
    )
    from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1

    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(fixture, "screen1-default-3panel")
    view_model.set_library_revealed(True)
    live_kit = None
    if clear_live_kit_assignments:
        live_kit = LiveKitPresenter(state=LiveKitState())
        view_model.live_kit_groups = live_kit.groups
    view_model.set_workspace_materialization(
        has_active_source=True,
        calm_canvas_visible=False,
        browser_materialized=True,
        live_kit_materialized=live_kit_materialized,
    )
    if with_session:
        app, engine, window = _qml_engine(view_model)
        adapter = engine._screen1_interaction_adapter
        if live_kit is not None:
            adapter._live_kit = live_kit
            view_model.live_kit_groups = live_kit.groups
    else:
        adapter = Screen1QmlInteractionAdapter(
            view_model=view_model,
            harmony_controller=HarmonicMatchLibraryController(),
            live_kit=live_kit,
        )
        app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    view_model.set_workspace_materialization(
        has_active_source=True,
        calm_canvas_visible=False,
        browser_materialized=True,
        live_kit_materialized=live_kit_materialized,
    )
    if live_kit_drawer_open is None:
        live_kit_drawer_open = bool(live_kit_materialized)
    adapter._live_kit_drawer_open = bool(live_kit_drawer_open)
    adapter.live_kit_collapsed = not bool(live_kit_drawer_open)
    window.show()
    _settle_qml_frame(app)
    bridge = getattr(engine, "_screen1_interaction_bridge", None)
    if bridge is not None and hasattr(bridge, "refreshState"):
        bridge.refreshState()
        _settle_qml_frame(app)
    return app, engine, window, adapter, _settle_qml_frame


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
@pytest.mark.parametrize("size", [(1120, 640), (1600, 900)])
def test_runtime_nav_centered_transport_on_right(size) -> None:
    from PySide6.QtCore import QPointF
    from PySide6.QtQuick import QQuickItem

    width, height = size
    app, engine, window, adapter, settle = _build_screen1_window()
    try:
        window.setWidth(width)
        window.setHeight(height)
        settle(app)
        settle(app)

        header = window.findChild(QQuickItem, "screen1Header")
        nav = window.findChild(QQuickItem, "headerNavZone")
        nav_row = window.findChild(QQuickItem, "headerNavRow")
        transport = window.findChild(QQuickItem, "headerTransportZone")
        bar = window.findChild(QQuickItem, "libraryScopeBar")
        footer = window.findChild(QQuickItem, "programFooterBand") or window.findChild(
            QQuickItem, "contextHintPlacement"
        )
        assert header is not None and nav is not None and transport is not None
        assert nav_row is not None
        assert bar is not None and footer is not None

        _assert_centered(nav_row, header, label=f"nav row {width}x{height}")
        transport_in_header = transport.mapToItem(header, QPointF(0, 0))
        assert transport_in_header.x() + transport.width() <= header.width() + 2.0
        assert transport_in_header.x() > header.width() * 0.45

        bar_in_footer = bar.mapToItem(footer, QPointF(0, 0))
        assert bar_in_footer.x() < footer.width() * 0.5
    finally:
        window.close()
        app.processEvents()


def _click_item(window, item, settle, app) -> None:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QEvent

    center = item.mapToItem(window.contentItem(), QPointF(item.width() / 2, item.height() / 2))
    for action in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        event = QMouseEvent(
            action,
            center,
            window.mapToGlobal(center.toPoint()),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        app.sendEvent(window, event)
        settle(app)


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_runtime_edit_nav_from_screen2_returns_and_reveals_browser() -> None:
    from PySide6.QtQuick import QQuickItem

    app, engine, window, adapter, settle = _build_screen1_window(with_session=True)
    try:
        adapter.toggle_browser_collapsed()
        settle(app)
        assert adapter.browser_collapsed is True
        channel_rack = engine.rootContext().contextProperty("channelRackModel")
        assert channel_rack is not None
        channel_rack.openChannelRack()
        settle(app)
        assert window.property("activeScreen") == "screen1"
        nav = window.findChild(QQuickItem, "programNavEdit")
        assert nav is not None
        _click_item(window, nav, settle, app)
        assert window.property("activeScreen") == "screen1"
        assert adapter.browser_collapsed is False
    finally:
        window.close()
        app.processEvents()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_runtime_header_nav_has_no_live_kit_mode_peer() -> None:
    from PySide6.QtQuick import QQuickItem

    app, engine, window, adapter, settle = _build_screen1_window()
    try:
        assert window.findChild(QQuickItem, "programNavLiveKit") is None
        header = window.findChild(QQuickItem, "screen1Header")
        nav_row = window.findChild(QQuickItem, "headerNavRow")
        assert header is not None and nav_row is not None
        for name in (
            "programNavEdit",
            "programNavArrangement",
        ):
            btn = window.findChild(QQuickItem, name)
            assert btn is not None
            assert nav_row.isAncestorOf(btn)
        assert window.findChild(QQuickItem, "programNavStepSequencer") is None
    finally:
        window.close()
        app.processEvents()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_runtime_program_footer_remains_visible_on_screen2() -> None:
    """#831 P2 / #908: global footer chrome stays present with bottom Rack open."""
    from PySide6.QtQuick import QQuickItem

    app, engine, window, adapter, settle = _build_screen1_window(with_session=True)
    try:
        channel_rack = engine.rootContext().contextProperty("channelRackModel")
        assert channel_rack is not None
        channel_rack.openChannelRack()
        settle(app)
        footer = window.findChild(QQuickItem, "programFooterBand")
        assert footer is not None
        assert footer.isVisible()
    finally:
        window.close()
        app.processEvents()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
@pytest.mark.parametrize("size", [(1120, 640), (1600, 900)])
def test_runtime_header_zones_do_not_overlap(size) -> None:
    """Frozen #831 three-zone header geometry incl. minimum supported width."""
    from PySide6.QtCore import QPointF
    from PySide6.QtQuick import QQuickItem

    width, height = size
    app, engine, window, adapter, settle = _build_screen1_window()
    try:
        window.setWidth(width)
        window.setHeight(height)
        settle(app)
        settle(app)

        persistence = engine.rootContext().contextProperty("sessionPersistenceModel")
        if persistence is not None:
            persistence._session = type(
                "S",
                (),
                {"persistence_status": "autosave_failed"},
            )()
            persistence.refresh()
            settle(app)

        header = window.findChild(QQuickItem, "screen1Header")
        left = window.findChild(QQuickItem, "headerLeftZone")
        nav = window.findChild(QQuickItem, "headerNavZone")
        transport = window.findChild(QQuickItem, "headerTransportZone")
        assert all(x is not None for x in (header, left, nav, transport))

        left_right = float(left.mapToItem(header, QPointF(left.width(), 0)).x())
        nav_left = float(nav.mapToItem(header, QPointF(0, 0)).x())
        nav_right = float(nav.mapToItem(header, QPointF(nav.width(), 0)).x())
        transport_left = float(transport.mapToItem(header, QPointF(0, 0)).x())
        transport_right = float(
            transport.mapToItem(header, QPointF(transport.width(), 0)).x()
        )
        assert left_right <= nav_left + 1.0
        assert nav_right <= transport_left + 1.0
        # Two top-level mode destinations remain; Live stays parked.
        assert float(nav.width()) >= 240.0
        assert float(transport.width()) > 8.0
        # Transport stays fully inside the header, footer chrome stays visible
        # and geometrically valid down to the minimum supported window size.
        assert transport_right <= float(header.width()) + 1.0
        footer = window.findChild(QQuickItem, "programFooterBand")
        assert footer is not None
        assert footer.isVisible()
        assert float(footer.height()) > 8.0
        footer_right = float(
            footer.mapToItem(window.contentItem(), QPointF(footer.width(), 0)).x()
        )
        assert footer_right <= float(header.width()) + 1.0

        for name in (
            "programNavEdit",
            "programNavArrangement",
        ):
            btn = window.findChild(QQuickItem, name)
            assert btn is not None
            btn_left = float(btn.mapToItem(header, QPointF(0, 0)).x())
            btn_right = float(btn.mapToItem(header, QPointF(btn.width(), 0)).x())
            assert btn_left >= nav_left - 1.0
            assert btn_right <= nav_right + 1.0
            assert btn_right <= transport_left + 1.0
        assert window.findChild(QQuickItem, "programNavStepSequencer") is None
        assert window.findChild(QQuickItem, "programNavLiveKit") is None
    finally:
        window.close()
        app.processEvents()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_visual_accept_program_chrome_baseline_1600x900(tmp_path) -> None:
    """VISUAL_ACCEPT_PASS evidence: program chrome at 1600x900 (100% scale baseline).

    #1077 releases only Live Kit upper-nav expectations; footer/transport chrome
    remains frozen here.
    """
    from pathlib import Path

    from PySide6.QtQuick import QQuickItem

    evidence = Path(tmp_path) / "program_chrome_831"
    evidence.mkdir()
    app, engine, window, adapter, settle = _build_screen1_window()
    try:
        window.setWidth(1600)
        window.setHeight(900)
        settle(app)
        settle(app)
        header = window.findChild(QQuickItem, "screen1Header")
        nav = window.findChild(QQuickItem, "headerNavZone")
        transport = window.findChild(QQuickItem, "headerTransportZone")
        footer = window.findChild(QQuickItem, "programFooterBand")
        bar = window.findChild(QQuickItem, "libraryScopeBar")
        assert all(x is not None for x in (header, nav, transport, footer, bar))
        assert float(header.width()) == 1600.0
        # #880 slim corridor (under #831 mass; toward Owner reference language).
        assert 26.0 <= float(header.height()) <= 34.0
        assert 18.0 <= float(footer.height()) <= 26.0
        assert window.findChild(QQuickItem, "programNavLiveKit") is None
        grab = window.grabWindow()
        out = evidence / "screen1_program_chrome_1600x900.png"
        assert grab.save(str(out))
        assert out.stat().st_size > 0
    finally:
        window.close()
        app.processEvents()
