"""#1080 C2d visual-runtime regressions found during final Direction-B acceptance.

These tests freeze three presentation-only requirements from the approved #1079
Direction-B design contract: expanded tracks must occupy real width, group labels
must retain their own lane before block controls, and constrained-height stages
must clip/scroll instead of overlapping the fixed bottom sequencer.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QPointF
from PySide6.QtQuick import QQuickItem

from src.arrangement_32_field_time import build_32_field_channel_rack_state
from tests.audio_fixtures import write_sine_wav
from tests.test_workbench_arrangement_qml_1080_slice_b import (
    _build_production_window,
    _enable,
    _oneshot_row,
    _visual_items_named,
)


def _enter_populated_arrangement(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path / "state"))
    app, engine, window, settle = _build_production_window()
    session = engine._screen1_session
    bridge = engine.rootContext().contextProperty("arrangementModel")

    kick = tmp_path / "kick.wav"
    main_drum = tmp_path / "main_drum.wav"
    closed_hat = tmp_path / "closed_hat.wav"
    write_sine_wav(kick, duration_sec=0.05, frequency_hz=60)
    write_sine_wav(main_drum, duration_sec=0.05, frequency_hz=90)
    write_sine_wav(closed_hat, duration_sec=0.05, frequency_hz=9000)
    session.live_kit.assign("Kick + Bass", "Kick", _oneshot_row(kick))
    session.live_kit.assign("Drums", "Main Drum", _oneshot_row(main_drum))
    session.live_kit.assign("Drums", "Closed Hat", _oneshot_row(closed_hat))
    session.channel_rack.restore_state(build_32_field_channel_rack_state(session.live_kit))
    _enable(session)
    engine._screen1_interaction_adapter.load_feature_settings()
    assert session.enter_arrangement_from_edit(package_root=tmp_path / "track").ok
    bridge.refresh()
    settle(app)
    assert bridge.toggleArrangementGroupExpanded("pg_drums") == "toggled"
    bridge.refresh()
    settle(app)
    return app, engine, window, settle, session, bridge


def _x_in_window(item, window) -> float:
    return float(item.mapToItem(window.contentItem(), QPointF(0, 0)).x())


def _y_in_window(item, window) -> float:
    return float(item.mapToItem(window.contentItem(), QPointF(0, 0)).y())


def test_c2d_expanded_tracks_have_width_and_group_blocks_start_after_label_lane(tmp_path, monkeypatch):
    app, engine, window, settle, session, _bridge = _enter_populated_arrangement(tmp_path, monkeypatch)
    try:
        window.resize(1600, 900)
        settle(app)
        stage = window.findChild(QQuickItem, "arrangementStage")
        assert stage is not None

        tracks = _visual_items_named(stage, "arrangementTrackRow")
        assert len(tracks) >= 2
        assert all(float(row.width()) > 200 for row in tracks), [float(row.width()) for row in tracks]
        assert all(bool(row.isVisible()) for row in tracks)
        first_track = tracks[0]
        first_track_block = next(
            block for block in _visual_items_named(first_track, "arrangementTrackBlock")
            if int(block.property("blockIndex")) == 0
        )
        assert _x_in_window(first_track_block, window) - _x_in_window(first_track, window) >= 72

        group_rows = _visual_items_named(stage, "arrangementGroupRow")
        drums = next(row for row in group_rows if str(row.property("groupId")) == "pg_drums")
        first_block = next(
            block for block in _visual_items_named(drums, "arrangementGroupBlock")
            if int(block.property("blockIndex")) == 0
        )
        # Direction B reserves expand control + readable group-label lane before blocks.
        assert _x_in_window(first_block, window) - _x_in_window(drums, window) >= 200
    finally:
        window.close()
        app.processEvents()
        session.transport.close()


def test_c2d_constrained_height_uses_clipped_scrollable_group_viewport(tmp_path, monkeypatch):
    app, engine, window, settle, session, _bridge = _enter_populated_arrangement(tmp_path, monkeypatch)
    try:
        window.resize(1120, 640)
        settle(app)
        stage = window.findChild(QQuickItem, "arrangementStage")
        assert stage is not None
        viewport = window.findChild(QQuickItem, "arrangementGroupViewport")
        sequencer = window.findChild(QQuickItem, "arrangementSequencer")
        assert viewport is not None, "Direction-B constrained-height stage needs a bounded group viewport"
        assert sequencer is not None
        assert bool(viewport.property("clip")) is True
        viewport_bottom = _y_in_window(viewport, window) + float(viewport.height())
        sequencer_top = _y_in_window(sequencer, window)
        assert viewport_bottom <= sequencer_top + 0.5
        assert bool(viewport.property("contentHeight") > viewport.height()) is True
    finally:
        window.close()
        app.processEvents()
        session.transport.close()
