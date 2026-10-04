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
    assert "anchors.horizontalCenter" in nav_snip
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


def test_live_kit_nav_inert_before_materialization_in_qml() -> None:
    block = QML_SOURCE.split('objectName: "programNavLiveKit"', 1)[1].split("ToolButton", 2)[0]
    assert "liveKitRevealed" in block or "enabled:" in block


def _zone_center_x(item) -> float:
    return float(item.x()) + float(item.width()) / 2.0


def _assert_centered(zone, reference, *, label: str) -> None:
    ref_center = float(reference.width()) / 2.0
    zone_center = _zone_center_x(zone)
    tol = max(CENTER_TOLERANCE_MIN_PX, float(reference.width()) * CENTER_TOLERANCE_RATIO)
    delta = abs(zone_center - ref_center)
    assert delta <= tol, f"{label}: center delta={delta:.1f}px tol={tol:.1f}px"


def _build_screen1_window(*, live_kit_materialized: bool = True):
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
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        harmony_controller=HarmonicMatchLibraryController(),
    )
    app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
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
        transport = window.findChild(QQuickItem, "headerTransportZone")
        bar = window.findChild(QQuickItem, "libraryScopeBar")
        footer = window.findChild(QQuickItem, "programFooterBand") or window.findChild(
            QQuickItem, "contextHintPlacement"
        )
        assert header is not None and nav is not None and transport is not None
        assert bar is not None and footer is not None

        _assert_centered(nav, header, label=f"nav {width}x{height}")
        transport_in_header = transport.mapToItem(header, QPointF(0, 0))
        assert transport_in_header.x() + transport.width() <= header.width() + 2.0
        assert transport_in_header.x() > header.width() * 0.45

        bar_in_footer = bar.mapToItem(footer, QPointF(0, 0))
        assert bar_in_footer.x() >= -1.0
        assert bar_in_footer.y() >= -1.0
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
        assert float(header.height()) <= 60.0
        grab = window.grabWindow()
        out = evidence / "screen1_program_chrome_1600x900.png"
        assert grab.save(str(out))
        assert out.stat().st_size > 0
    finally:
        window.close()
        app.processEvents()
