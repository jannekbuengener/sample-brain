"""PR #1180: real wheel delivery and shared group/track block columns."""
from __future__ import annotations

import copy
from unittest.mock import Mock

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

from tests.test_workbench_arrangement_qml_1080_c2d_visual_runtime import (
    _enter_populated_arrangement,
    _x_in_window,
    _y_in_window,
)
from tests.test_workbench_arrangement_qml_1080_slice_b import _visual_items_named


@pytest.mark.parametrize("size", [(1600, 900), (1280, 720), (1120, 640)])
def test_group_and_track_block_edges_share_columns(tmp_path, monkeypatch, size):
    app, engine, window, settle, session, bridge = _enter_populated_arrangement(tmp_path, monkeypatch)
    try:
        window.resize(*size)
        settle(app)
        viewport = window.findChild(QQuickItem, "arrangementGroupViewport")
        sequencer = window.findChild(QQuickItem, "arrangementSequencer")
        assert viewport.property("clip")
        assert _y_in_window(viewport, window) + viewport.height() <= _y_in_window(sequencer, window)
        # Check both initial and zoomed projections, matching by domain block index.
        for zoomed in (False, True):
            if zoomed:
                bridge.zoomIn()
                settle(app)
            groups = _visual_items_named(viewport, "arrangementGroupRow")
            drums = next(row for row in groups if row.property("groupId") == "pg_drums")
            group_blocks = {
                int(block.property("blockIndex")): block
                for block in _visual_items_named(drums, "arrangementGroupBlock")
            }
            assert len(group_blocks) >= 2
            if not zoomed:
                assert 0 in group_blocks
            tracks = _visual_items_named(drums, "arrangementTrackRow")
            assert len(tracks) >= 2
            for track in tracks:
                blocks = _visual_items_named(track, "arrangementTrackBlock")
                assert {int(b.property("blockIndex")) for b in blocks} == set(group_blocks)
                for block in blocks:
                    parent_block = group_blocks[int(block.property("blockIndex"))]
                    assert block.width() > 0
                    assert _x_in_window(block, window) == pytest.approx(_x_in_window(parent_block, window), abs=0.5)
                    assert _x_in_window(block, window) + block.width() == pytest.approx(
                        _x_in_window(parent_block, window) + parent_block.width(), abs=0.5
                    )
                label = _visual_items_named(track, "arrangementTrackRowName")[0]
                assert label.isVisible() and label.property("text")
                assert label.width() >= 72
                assert _x_in_window(label, window) >= _x_in_window(drums, window)
                assert _x_in_window(label, window) + label.width() < min(
                    _x_in_window(block, window) for block in blocks
                )
    finally:
        window.close()
        app.processEvents()
        session.transport.close()


def _wheel(app, window, position, delta, modifiers):
    QTest.wheelEvent(window, position, QPoint(0, delta), stateKey=modifiers)
    QTest.qWait(200)
    app.processEvents()


@pytest.mark.parametrize("surface", ["viewport", "label", "block"])
def test_group_viewport_routes_ctrl_zoom_and_plain_scroll(tmp_path, monkeypatch, surface):
    app, engine, window, settle, session, bridge = _enter_populated_arrangement(tmp_path, monkeypatch)
    try:
        window.resize(1120, 640)
        assert bridge.requestEndMarkerSet(64.0) == "mutated"
        settle(app)
        viewport = window.findChild(QQuickItem, "arrangementGroupViewport")
        assert viewport.property("contentHeight") > viewport.height()
        state_before = copy.deepcopy(session.arrangement_state.to_payload())
        pattern_before = copy.deepcopy(session.channel_rack.state.pattern)
        save = Mock(wraps=session.set_arrangement_state)
        monkeypatch.setattr(session, "set_arrangement_state", save)

        def position():
            if surface == "viewport":
                return viewport.mapToItem(window.contentItem(), QPointF(2, 10))
            groups = _visual_items_named(viewport, "arrangementGroupRow")
            drums = next(row for row in groups if row.property("groupId") == "pg_drums")
            name = "arrangementTrackRowName" if surface == "label" else "arrangementGroupBlock"
            item = min(_visual_items_named(drums, name), key=lambda item: _x_in_window(item, window))
            point = item.mapToItem(window.contentItem(), QPointF(item.width() / 2, item.height() / 2))
            assert _y_in_window(viewport, window) <= point.y() < _y_in_window(viewport, window) + viewport.height()
            return point

        zoom = bridge.viewportZoomLevel
        scroll = viewport.property("contentY")
        _wheel(app, window, position(), 120, Qt.ControlModifier)
        assert bridge.viewportZoomLevel == pytest.approx(zoom * 2)
        assert viewport.property("contentY") == pytest.approx(scroll)
        _wheel(app, window, position(), -120, Qt.ControlModifier)
        assert bridge.viewportZoomLevel == pytest.approx(zoom)
        assert viewport.property("contentY") == pytest.approx(scroll)

        _wheel(app, window, position(), -120, Qt.NoModifier)
        assert viewport.property("contentY") > scroll
        assert bridge.viewportZoomLevel == pytest.approx(zoom)
        assert session.arrangement_state.to_payload() == state_before
        assert session.channel_rack.state.pattern == pattern_before
        save.assert_not_called()
    finally:
        window.close()
        app.processEvents()
        session.transport.close()
