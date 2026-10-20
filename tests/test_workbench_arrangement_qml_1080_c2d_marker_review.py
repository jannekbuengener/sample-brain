"""C2d review regression: the song end marker belongs to the upper timeline."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF
from PySide6.QtQuick import QQuickItem

from tests.test_workbench_arrangement_qml_1080_c2d_visual_runtime import (
    _enter_populated_arrangement,
)


def _rect_in_window(item, window):
    p = item.mapToItem(window.contentItem(), QPointF(0, 0))
    return float(p.x()), float(p.y()), float(item.width()), float(item.height())


@pytest.mark.parametrize("size", [(1600, 900), (1280, 720), (1120, 640)])
def test_end_marker_renders_in_upper_arrangement_timeline_not_sequencer(tmp_path, monkeypatch, size):
    app, engine, window, settle, session, bridge = _enter_populated_arrangement(tmp_path, monkeypatch)
    try:
        window.resize(*size)
        assert bridge.requestEndMarkerSet(64.0) == "mutated"
        bridge.refresh()
        settle(app)

        upper = window.findChild(QQuickItem, "arrangementUpperStage")
        sequencer = window.findChild(QQuickItem, "arrangementSequencer")
        marker = window.findChild(QQuickItem, "arrangementEndMarker")
        assert upper is not None and sequencer is not None and marker is not None
        assert marker.isVisible()

        ux, uy, uw, uh = _rect_in_window(upper, window)
        sx, sy, sw, sh = _rect_in_window(sequencer, window)
        mx, my, mw, mh = _rect_in_window(marker, window)

        assert my >= uy
        assert my + mh <= uy + uh + 0.5
        assert my + mh <= sy + 0.5
        assert mx + mw <= sx or sx + sw <= mx or my + mh <= sy or sy + sh <= my
    finally:
        window.close()
        app.processEvents()
        session.transport.close()
