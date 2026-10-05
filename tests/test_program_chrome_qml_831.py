"""#831 program chrome — QML structure and runtime geometry (TEST_FREEZE)."""

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
        ("Browser", "programNavBrowser"),
        ("Live Kit", "programNavLiveKit"),
        ("Step Sequencer", "programNavStepSequencer"),
        ("Arrangement", "programNavArrangement"),
    ):
        assert label in nav
        assert f'objectName: "{obj}"' in nav
    assert 'objectName: "producerCommandZone"' not in header
    assert 'objectName: "openChannelRackButton"' not in header


def test_program_chrome_transport_on_right_without_harmonic_header() -> None:
    header = _header_block()
    transport = header[header.index('objectName: "headerTransportZone"') :]
    assert 'text: "MASTER"' in transport
    assert 'text: "GRID"' in transport
    assert 'text: "SYNC"' in transport
    assert 'objectName: "displayPreferencesOverflow"' in transport
    assert 'objectName: "harmonicMatchButton"' not in transport
    nav_snip = header[
        header.index('objectName: "headerNavZone"') : header.index(
            'objectName: "headerTransportZone"'
        )
    ]
    assert "idealX" in nav_snip or "anchors.horizontalCenter" in nav_snip
    assert 'objectName: "masterTempoValue"' in transport


def test_program_chrome_footer_hosts_scope_bar_and_right_hint() -> None:
    footer = _footer_block()
    assert 'objectName: "libraryScopeBar"' in footer
    assert 'objectName: "contextHintPlacement"' in footer or 'objectName: "programFooterBand"' in footer
    assert 'objectName: "contextHintDisplay"' in footer
    hint_block = footer.split('objectName: "contextHintDisplay"', 1)[1].split("}", 1)[0]
    assert "horizontalCenter" not in hint_block
    pane = QML_SOURCE.split("id: libraryPane", 1)[1].split(
        'objectName: "elasticHandleAfterLibrary"', 1
    )[0]
    assert 'objectName: "libraryScopeBar"' not in pane


def test_program_footer_is_global_chrome_across_screens() -> None:
    """#831 P2: program footer is global frame chrome, not Screen-1-only."""
    footer = _footer_block()
    band = footer.split('objectName: "programFooterBand"', 1)[1].split("Rectangle", 1)[0]
    assert 'visible: window.activeScreen === "screen1"' not in band
    assert "height:" in band


def test_live_kit_nav_inert_before_materialization_in_qml() -> None:
    block = QML_SOURCE.split('objectName: "programNavLiveKit"', 1)[1].split("ToolButton", 2)[0]
    assert "liveKitRevealed" in block or "enabled:" in block


def test_program_nav_browser_handler_reveals_collapsed_browser() -> None:
    """#831 P2: Browser nav must use #845 reveal when Browser is collapsed."""
    block = QML_SOURCE.split('objectName: "programNavBrowser"', 1)[1].split(
        "ToolButton", 1
    )[0]
    assert "browserCollapsed" in block
    assert "toggleBrowserCollapsed" in block


def test_program_nav_live_kit_handler_reveals_after_screen2_return() -> None:
    """#831 P2: Live Kit nav must reveal after returnToScreen1 in one activation."""
    block = QML_SOURCE.split('objectName: "programNavLiveKit"', 1)[1].split(
        "ToolButton", 1
    )[0]
    assert "returnToScreen1" in block
    assert "liveKitCollapsed" in block
    assert "toggleLiveKitCollapsed" in block
    # Must not be an exclusive if/else that skips reveal after Screen-2 return.
    assert "else if (window.interaction.liveKitCollapsed)" not in block


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
    with_session: bool = False,
):
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
    view_model.set_library_revealed(True)
    view_model.set_workspace_materialization(
        has_active_source=True,
        calm_canvas_visible=False,
        browser_materialized=True,
        live_kit_materialized=live_kit_materialized,
    )
    if with_session:
        # Compose-owned Channel Rack / Screen-2 navigation (#678).
        app, engine, window = _qml_engine(view_model)
        adapter = engine._screen1_interaction_adapter
    else:
        adapter = Screen1QmlInteractionAdapter(
            view_model=view_model,
            harmony_controller=HarmonicMatchLibraryController(),
        )
        app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    view_model.set_workspace_materialization(
        has_active_source=True,
        calm_canvas_visible=False,
        browser_materialized=True,
        live_kit_materialized=live_kit_materialized,
    )
    window.show()
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

        # Nav labels stay window-centered; the zone itself is the non-overlap band.
        _assert_centered(nav_row, header, label=f"nav row {width}x{height}")
        transport_in_header = transport.mapToItem(header, QPointF(0, 0))
        assert transport_in_header.x() + transport.width() <= header.width() + 2.0
        assert transport_in_header.x() > header.width() * 0.45

        bar_in_footer = bar.mapToItem(footer, QPointF(0, 0))
        assert bar_in_footer.x() >= -1.0
        assert bar_in_footer.y() >= -1.0
    finally:
        window.close()
        app.processEvents()


def _click_item(window, item, settle, app) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    point = item.mapToScene(item.boundingRect().center()).toPoint()
    QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)
    settle(app)
    settle(app)


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_runtime_browser_nav_noop_when_already_open() -> None:
    from PySide6.QtQuick import QQuickItem

    app, engine, window, adapter, settle = _build_screen1_window()
    try:
        assert adapter.browser_collapsed is False
        browser = window.findChild(QQuickItem, "browserPane")
        nav = window.findChild(QQuickItem, "programNavBrowser")
        assert browser is not None and nav is not None
        selected_before = adapter.selected_browser_index
        _click_item(window, nav, settle, app)
        assert adapter.browser_collapsed is False
        assert adapter.selected_browser_index == selected_before
        assert browser.isVisible()
    finally:
        window.close()
        app.processEvents()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_runtime_browser_nav_reveals_collapsed_browser_on_screen1() -> None:
    from PySide6.QtQuick import QQuickItem

    app, engine, window, adapter, settle = _build_screen1_window()
    try:
        adapter.toggle_browser_collapsed()
        settle(app)
        assert adapter.browser_collapsed is True
        nav = window.findChild(QQuickItem, "programNavBrowser")
        browser = window.findChild(QQuickItem, "browserPane")
        assert nav is not None and browser is not None
        _click_item(window, nav, settle, app)
        assert adapter.browser_collapsed is False
        assert browser.isVisible()
    finally:
        window.close()
        app.processEvents()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_runtime_browser_nav_from_screen2_returns_and_reveals() -> None:
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
        assert window.property("activeScreen") == "screen2"
        nav = window.findChild(QQuickItem, "programNavBrowser")
        assert nav is not None
        _click_item(window, nav, settle, app)
        assert window.property("activeScreen") == "screen1"
        assert adapter.browser_collapsed is False
    finally:
        window.close()
        app.processEvents()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_runtime_live_kit_nav_inert_when_unmaterialized() -> None:
    from PySide6.QtQuick import QQuickItem

    app, engine, window, adapter, settle = _build_screen1_window(
        live_kit_materialized=False
    )
    try:
        nav = window.findChild(QQuickItem, "programNavLiveKit")
        assert nav is not None
        assert nav.isEnabled() is False
        assert adapter.live_kit_collapsed is False
    finally:
        window.close()
        app.processEvents()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_runtime_live_kit_nav_keeps_visible_materialized() -> None:
    from PySide6.QtQuick import QQuickItem

    app, engine, window, adapter, settle = _build_screen1_window(
        live_kit_materialized=True
    )
    try:
        assert adapter.live_kit_collapsed is False
        nav = window.findChild(QQuickItem, "programNavLiveKit")
        pane = window.findChild(QQuickItem, "liveKitPane")
        assert nav is not None and pane is not None
        _click_item(window, nav, settle, app)
        assert adapter.live_kit_collapsed is False
        assert pane.isVisible()
    finally:
        window.close()
        app.processEvents()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_runtime_live_kit_nav_reveals_collapsed_on_screen1() -> None:
    from PySide6.QtQuick import QQuickItem

    app, engine, window, adapter, settle = _build_screen1_window(
        live_kit_materialized=True
    )
    try:
        adapter.toggle_live_kit_collapsed()
        settle(app)
        assert adapter.live_kit_collapsed is True
        nav = window.findChild(QQuickItem, "programNavLiveKit")
        pane = window.findChild(QQuickItem, "liveKitPane")
        assert nav is not None and pane is not None
        _click_item(window, nav, settle, app)
        assert adapter.live_kit_collapsed is False
        assert pane.isVisible()
    finally:
        window.close()
        app.processEvents()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_runtime_live_kit_nav_from_screen2_returns_and_reveals() -> None:
    from PySide6.QtQuick import QQuickItem

    app, engine, window, adapter, settle = _build_screen1_window(
        live_kit_materialized=True,
        with_session=True,
    )
    try:
        adapter.toggle_live_kit_collapsed()
        settle(app)
        assert adapter.live_kit_collapsed is True
        channel_rack = engine.rootContext().contextProperty("channelRackModel")
        assert channel_rack is not None
        channel_rack.openChannelRack()
        settle(app)
        assert window.property("activeScreen") == "screen2"
        nav = window.findChild(QQuickItem, "programNavLiveKit")
        assert nav is not None
        assert nav.isEnabled() is True
        _click_item(window, nav, settle, app)
        assert window.property("activeScreen") == "screen1"
        assert adapter.live_kit_collapsed is False
        pane = window.findChild(QQuickItem, "liveKitPane")
        assert pane is not None and pane.isVisible()
    finally:
        window.close()
        app.processEvents()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_runtime_program_footer_remains_visible_on_screen2() -> None:
    """#831 P2: global footer chrome stays present on Step Sequencer route."""
    from PySide6.QtQuick import QQuickItem

    app, engine, window, adapter, settle = _build_screen1_window(with_session=True)
    try:
        channel_rack = engine.rootContext().contextProperty("channelRackModel")
        assert channel_rack is not None
        channel_rack.openChannelRack()
        settle(app)
        assert window.property("activeScreen") == "screen2"
        footer = window.findChild(QQuickItem, "programFooterBand")
        bar = window.findChild(QQuickItem, "libraryScopeBar")
        assert footer is not None and bar is not None
        assert footer.isVisible() is True
        # #880: footer must stay globally present, but no longer lock #831 mass (>=40).
        assert 24.0 <= float(footer.height()) <= 32.0
        assert bar.isVisible() is True
    finally:
        window.close()
        app.processEvents()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
@pytest.mark.parametrize("size", [(1120, 640), (1600, 900)])
def test_runtime_header_zones_do_not_overlap(size) -> None:
    from PySide6.QtCore import QPointF
    from PySide6.QtQuick import QQuickItem

    width, height = size
    app, engine, window, adapter, settle = _build_screen1_window()
    try:
        window.setWidth(width)
        window.setHeight(height)
        settle(app)
        settle(app)
        # Long attention label case (secondary text may elide; must not overlap nav).
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
        assert left_right <= nav_left + 1.0
        assert nav_right <= transport_left + 1.0
        # Usable nav band must fit the four program-nav destinations.
        assert float(nav.width()) >= 360.0
        assert float(transport.width()) > 8.0

        for name in (
            "programNavBrowser",
            "programNavLiveKit",
            "programNavStepSequencer",
            "programNavArrangement",
        ):
            btn = window.findChild(QQuickItem, name)
            assert btn is not None
            btn_left = float(btn.mapToItem(header, QPointF(0, 0)).x())
            btn_right = float(btn.mapToItem(header, QPointF(btn.width(), 0)).x())
            assert btn_left >= nav_left - 1.0
            assert btn_right <= nav_right + 1.0
            assert btn_right <= transport_left + 1.0
    finally:
        window.close()
        app.processEvents()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_automated_runtime_visual_acceptance_program_chrome_831(tmp_path) -> None:
    """VISUAL_ACCEPT_PASS evidence: program chrome at 1600x900 (100% scale baseline)."""
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
        # #880 slim corridor (clearly under #831 mass of 54); not screenshot-pixel truth.
        assert 24.0 <= float(header.height()) <= 40.0
        assert 24.0 <= float(footer.height()) <= 32.0
        grab = window.grabWindow()
        out = evidence / "screen1_program_chrome_1600x900.png"
        assert grab.save(str(out))
        assert out.stat().st_size > 0
    finally:
        window.close()
        app.processEvents()
