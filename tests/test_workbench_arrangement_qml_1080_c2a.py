"""Frozen C2a collapsed group renderer contract over the C1 authority."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src import workbench_arrangement_qml as seam
from src.workbench_qml import QML_SOURCE, _qml_arrangement_bridge
from tests.test_workbench_arrangement_qml_1080_c1 import session  # noqa: F401


@pytest.fixture
def bridge(session):
    pytest.importorskip("PySide6")
    session.projection_mode = "ARRANGEMENT"
    return _qml_arrangement_bridge(session, SimpleNamespace(arrangement_mode_enabled=True))


def test_four_python_labels_and_bounded_default_on_window(session, bridge, monkeypatch):
    original = seam.project_arrangement_block_window
    spy = Mock(wraps=original)
    monkeypatch.setattr(seam, "project_arrangement_block_window", spy)
    bridge.refresh()
    spy.assert_called_once()
    assert spy.call_args.args[:2] == (session, 0)
    count = spy.call_args.args[2]
    assert 2 <= count <= 8
    expected = original(session, 0, count)
    assert len(bridge.groupRows) == 4
    assert [(r["groupId"], r["displayName"]) for r in bridge.groupRows] == [
        (g.group_id, g.display_name) for g in expected.groups]
    assert all(len(r["blocks"]) == count for r in bridge.groupRows)
    assert all(c["groupEnabled"] and c["available"] and c["interactive"]
               for r in bridge.groupRows for c in r["blocks"])
    session.set_arrangement_state.assert_not_called()


def test_one_c1_intent_one_save_and_reprojection(session, bridge, monkeypatch):
    spy = Mock(wraps=seam.request_arrangement_group_toggle)
    monkeypatch.setattr(seam, "request_arrangement_group_toggle", spy)
    assert bridge.toggleArrangementGroupBlock("pg_baseline", 0) == "mutated"
    spy.assert_called_once_with(session, "pg_baseline", 0)
    session.set_arrangement_state.assert_called_once()
    cell = bridge.groupRows[0]["blocks"][0]
    assert not cell["groupEnabled"] and not cell["available"]
    assert cell["interactive"]  # explicit OFF remains reversible
    assert bridge.toggleArrangementGroupBlock("pg_baseline", 0) == "mutated"
    assert bridge.groupRows[0]["blocks"][0]["available"]


def test_global_off_and_horizon_targets_cannot_send_intent(session, bridge, monkeypatch):
    assert seam.request_arrangement_block_toggle(session, 0).ok
    bridge.refresh()
    assert all(not r["blocks"][0]["available"] and not r["blocks"][0]["interactive"]
               for r in bridge.groupRows)
    spy = Mock(wraps=seam.request_arrangement_group_toggle)
    monkeypatch.setattr(seam, "request_arrangement_group_toggle", spy)
    before = session.arrangement_state
    for index in (0, 19, -1, 999):
        assert bridge.toggleArrangementGroupBlock("pg_baseline", index) != "mutated"
    spy.assert_not_called()
    assert session.arrangement_state is before


def test_track_off_preserved_and_refresh_never_mutates(session, bridge):
    assert seam.request_arrangement_track_toggle(session, "ch_kick", 0).ok
    for _ in range(2):
        assert bridge.toggleArrangementGroupBlock("pg_baseline", 0) == "mutated"
    before = session.arrangement_state
    session.set_arrangement_state.reset_mock()
    bridge.refresh()
    bridge.refresh()
    assert session.arrangement_state is before
    assert before.disabled_track_blocks == frozenset({("ch_kick", 0)})
    session.set_arrangement_state.assert_not_called()


def test_gate_off_has_no_projection_or_group_intent(session, monkeypatch):
    pytest.importorskip("PySide6")
    session.projection_mode = "EDIT"
    spy = Mock(wraps=seam.project_arrangement_block_window)
    monkeypatch.setattr(seam, "project_arrangement_block_window", spy)
    bridge = _qml_arrangement_bridge(session, SimpleNamespace(arrangement_mode_enabled=False))
    assert bridge.groupRows == []
    assert bridge.toggleArrangementGroupBlock("pg_baseline", 0) != "mutated"
    spy.assert_not_called()
    session.set_arrangement_state.assert_not_called()


def test_qml_projects_labels_and_ids_without_local_mask_or_membership():
    stage = QML_SOURCE.split('id: arrangementStageComponent', 1)[1].split('id: arrangementStageHeader', 1)[0]
    assert 'model: window.arrangement.groupRows' in stage
    assert 'text: arrangementGroupRow.row.displayName' in stage
    assert 'toggleArrangementGroupBlock(arrangementGroupRow.groupId, arrangementGroupBlock.blockIndex)' in stage
    assert 'pg_baseline' not in stage
    assert 'enabled = !enabled' not in stage
    assert 'Keys.onSpacePressed' in stage
    assert 'acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton' in stage
    assert 'toggleArrangementField' in stage


def test_runtime_cells_reentry_pointer_protection_and_sequencer(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    from PySide6.QtQuick import QQuickItem
    from tests.test_workbench_arrangement_qml_1080_slice_b import (
        _build_production_window, _visual_items_named, _click_item,
        _enable, _oneshot_row, _cells_by_field_index,
    )
    from tests.audio_fixtures import write_sine_wav
    from src.arrangement_32_field_time import build_32_field_channel_rack_state

    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path / "state"))
    app, engine, window, settle = _build_production_window()
    s = engine._screen1_session
    try:
        window.resize(1600, 900)
        bridge = engine.rootContext().contextProperty("arrangementModel")
        assert not _visual_items_named(window.contentItem(), "arrangementGroupBlock")
        source = tmp_path / "kick.wav"
        write_sine_wav(source, duration_sec=0.05, frequency_hz=60)
        s.live_kit.assign("Kick + Bass", "Kick", _oneshot_row(source))
        s.channel_rack.restore_state(build_32_field_channel_rack_state(s.live_kit))
        _enable(s)
        engine._screen1_interaction_adapter.load_feature_settings()
        assert s.enter_arrangement_from_edit(package_root=tmp_path / "track").ok
        bridge.refresh()
        settle(app)
        stage = window.findChild(QQuickItem, "arrangementStage")
        rows = _visual_items_named(stage, "arrangementGroupRow")
        assert len(rows) == 4

        def cell():
            return next(c for c in _visual_items_named(stage, "arrangementGroupBlock")
                        if c.property("groupId") == "pg_baseline" and c.property("blockIndex") == 0)

        assert cell().property("effectiveOn") is True
        assert 8 <= len(_visual_items_named(stage, "arrangementGroupBlock")) <= 32
        vm = engine._screen1_interaction_adapter.view_model
        selected = vm.selected_browser_index
        save = Mock(wraps=s.set_arrangement_state)
        monkeypatch.setattr(s, "set_arrangement_state", save)
        _click_item(window, cell(), settle, app)
        settle(app)
        assert save.call_count == 1
        assert cell().property("effectiveOn") is False
        assert vm.selected_browser_index == selected
        assert not engine._screen1_interaction_adapter.preview_active
        assert len(_cells_by_field_index(stage)) == 32
        _click_item(window, _cells_by_field_index(stage)[0], settle, app)
        assert bridge.anyActiveStep
        masks = s.arrangement_state.to_payload()
        bridge.returnToBrowser()
        settle(app)
        assert not _visual_items_named(window.contentItem(), "arrangementGroupBlock")
        bridge.enterArrangement()
        settle(app)
        stage = window.findChild(QQuickItem, "arrangementStage")
        assert s.arrangement_state.to_payload() == masks
        assert cell().property("effectiveOn") is False
        assert bridge.anyActiveStep
    finally:
        window.close()
        app.processEvents()
        s.transport.close()
