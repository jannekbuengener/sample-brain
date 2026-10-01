"""#805 QML MASTER/GRID/SYNC must project session transport — no decorative state.

Frozen acceptance:
- Default SYNC off is shown as off
- Tempo projection matches get_current_tempo()
- Tempo change updates QML and the same TempoMap Channel Rack uses
- SYNC toggle updates authority + QML
- No second tempo/sync store in QML
- Producer command zone geometry remains centered
"""

from __future__ import annotations

import importlib.util
import re

import pytest

from src.workbench_qml import QML_SOURCE

PY_SIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None

CENTER_TOLERANCE_RATIO = 0.04
CENTER_TOLERANCE_MIN_PX = 24


def _header_center_snip() -> str:
    start = QML_SOURCE.index('objectName: "producerCommandZone"')
    end = QML_SOURCE.index('objectName: "headerRightZone"', start)
    return QML_SOURCE[start:end]


def test_qml_source_has_no_hardcoded_decorative_transport_truth():
    """QML must not paint a second BPM/SYNC truth independent of the bridge."""
    center = _header_center_snip()
    # Decorative literals from pre-#805 chrome must be gone.
    assert re.search(r'text:\s*"132"', center) is None
    assert re.search(r'text:\s*"4/4"', center) is None
    # SYNC must not hardcode an ON pill without binding.
    assert 'text: "ON"' not in center or "syncEnabled" in center
    assert "transport." in center or "window.transport" in center
    assert "adjustTempo" in center
    assert "toggleSync" in center
    # No QML-local BPM / sync stores.
    assert "property real masterBpm" not in QML_SOURCE
    assert "property bool syncEnabled" not in QML_SOURCE.split("transportModel")[0]


def test_transport_bridge_projects_adapter_authority_without_local_store():
    from src.workbench_qml import _qml_transport_bridge
    from src.workbench_transport_adapter import WorkbenchTransportAdapter
    from src.workbench_transport_ui import DEFAULT_TEMPO_BPM

    adapter = WorkbenchTransportAdapter(initial_bpm=DEFAULT_TEMPO_BPM)
    bridge = _qml_transport_bridge(adapter)

    assert adapter.is_sync_enabled() is False
    assert bridge.syncEnabled is False
    assert float(bridge.masterTempo) == pytest.approx(adapter.get_current_tempo())
    assert bridge.masterTempoText == f"{adapter.get_current_tempo():g}"
    ts = adapter.tempo_map.time_signature
    assert bridge.gridText == f"{ts.numerator}/{ts.denominator}"

    adapter.set_tempo(140.0)
    bridge.refresh()
    assert float(bridge.masterTempo) == pytest.approx(140.0)
    assert bridge.masterTempoText == "140"

    enabled = bridge.toggleSync()
    assert enabled is True
    assert adapter.is_sync_enabled() is True
    assert bridge.syncEnabled is True

    bridge.adjustTempo(-2.0)
    assert adapter.get_current_tempo() == pytest.approx(138.0)
    assert float(bridge.masterTempo) == pytest.approx(138.0)


def test_transport_bridge_null_transport_fail_closed_defaults_sync_off():
    from src.workbench_qml import _qml_transport_bridge
    from src.workbench_transport_ui import DEFAULT_TEMPO_BPM

    bridge = _qml_transport_bridge(None)
    assert bridge.syncEnabled is False
    assert float(bridge.masterTempo) == pytest.approx(DEFAULT_TEMPO_BPM)
    assert bridge.gridText == "4/4"
    # Commands must not invent a second mutable authority.
    assert bridge.toggleSync() is False
    assert bridge.syncEnabled is False
    bridge.adjustTempo(5.0)
    assert float(bridge.masterTempo) == pytest.approx(DEFAULT_TEMPO_BPM)


def test_compose_path_transport_is_same_instance_as_channel_rack():
    from src.workbench_session import compose_workbench_session

    session = compose_workbench_session()
    try:
        assert session.channel_rack.transport is session.transport
        assert session.transport.is_sync_enabled() is False
        before = session.transport.get_current_tempo()
        session.transport.set_tempo(before + 3.0)
        assert session.channel_rack.transport.get_current_tempo() == pytest.approx(
            before + 3.0
        )
        assert session.channel_rack.transport.tempo_map is session.transport.tempo_map
    finally:
        session.transport.close()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_runtime_qml_header_projects_live_transport_and_commands():
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest

    from src.workbench_qml import Screen1QmlViewModel, _qml_engine, _settle_qml_frame

    view_model = Screen1QmlViewModel.baseline("screen1-default-3panel")
    app, engine, window = _qml_engine(view_model)
    window.show()
    _settle_qml_frame(app)
    try:
        transport = engine._screen1_channel_rack.transport
        bridge = engine.rootContext().contextProperty("transportModel")
        assert bridge is not None
        assert engine._screen1_transport is transport
        assert bridge._transport is transport  # noqa: SLF001 — authority identity

        assert transport.is_sync_enabled() is False
        assert bridge.syncEnabled is False

        tempo_label = window.findChild(QQuickItem, "masterTempoValue")
        grid_label = window.findChild(QQuickItem, "gridValue")
        sync_indicator = window.findChild(QQuickItem, "syncIndicator")
        sync_label = window.findChild(QQuickItem, "syncStateLabel")
        tempo_down = window.findChild(QQuickItem, "tempoDownButton")
        tempo_up = window.findChild(QQuickItem, "tempoUpButton")
        assert all(
            item is not None
            for item in (
                tempo_label,
                grid_label,
                sync_indicator,
                sync_label,
                tempo_down,
                tempo_up,
            )
        )

        assert str(tempo_label.property("text")) == f"{transport.get_current_tempo():g}"
        ts = transport.tempo_map.time_signature
        assert str(grid_label.property("text")) == f"{ts.numerator}/{ts.denominator}"
        assert str(sync_label.property("text")) == "OFF"

        before = float(transport.get_current_tempo())
        point = tempo_up.mapToScene(QPointF(4, 4)).toPoint()
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)
        _settle_qml_frame(app)
        assert float(transport.get_current_tempo()) == pytest.approx(before + 1.0)
        assert str(tempo_label.property("text")) == f"{transport.get_current_tempo():g}"
        # Same TempoMap owner Channel Rack scheduling uses.
        assert (
            engine._screen1_channel_rack.transport.tempo_map is transport.tempo_map
        )

        sync_point = sync_indicator.mapToScene(QPointF(8, 8)).toPoint()
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, sync_point)
        _settle_qml_frame(app)
        assert transport.is_sync_enabled() is True
        assert bridge.syncEnabled is True
        assert str(sync_label.property("text")) == "ON"

        # Screen-2 open/play smoke at the changed tempo.
        channel_rack = engine.rootContext().contextProperty("channelRackModel")
        channel_rack.openChannelRack()
        _settle_qml_frame(app)
        assert engine._screen1_channel_rack.active_screen == "screen2"
        assert float(transport.get_current_tempo()) == pytest.approx(before + 1.0)
        # Play may fail-soft without samples; must not invent a second tempo.
        try:
            channel_rack.play()
        except Exception:
            pass
        _settle_qml_frame(app)
        assert float(transport.get_current_tempo()) == pytest.approx(before + 1.0)
        assert str(tempo_label.property("text")) == f"{transport.get_current_tempo():g}"
        channel_rack.stop()
        channel_rack.returnToScreen1()
        _settle_qml_frame(app)
    finally:
        window.close()
        app.processEvents()
        transport = getattr(engine, "_screen1_transport", None)
        if transport is not None:
            transport.close()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
@pytest.mark.parametrize("size", [(1120, 640), (1600, 900)])
def test_runtime_producer_zone_geometry_stable_with_transport_controls(size):
    from PySide6.QtQuick import QQuickItem

    from src.workbench_qml import Screen1QmlViewModel, _qml_engine, _settle_qml_frame

    width, height = size
    view_model = Screen1QmlViewModel.baseline("screen1-default-3panel")
    app, engine, window = _qml_engine(view_model)
    window.show()
    try:
        window.setWidth(width)
        window.setHeight(height)
        _settle_qml_frame(app)
        _settle_qml_frame(app)

        header = window.findChild(QQuickItem, "screen1Header")
        center = window.findChild(QQuickItem, "producerCommandZone")
        assert header is not None and center is not None
        ref_center = float(header.width()) / 2.0
        zone_center = float(center.x()) + float(center.width()) / 2.0
        tol = max(CENTER_TOLERANCE_MIN_PX, float(header.width()) * CENTER_TOLERANCE_RATIO)
        assert abs(zone_center - ref_center) <= tol
        assert center.x() >= 0
        assert center.x() + center.width() <= header.width() + 1.0
    finally:
        window.close()
        app.processEvents()
        transport = getattr(engine, "_screen1_transport", None)
        if transport is not None:
            transport.close()
