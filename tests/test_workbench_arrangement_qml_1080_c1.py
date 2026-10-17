"""Frozen #1080 C1: Python group/window/mask seam; no QML dependency."""

from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace
from unittest.mock import Mock
import json

import pytest

from src import arrangement_domain as ad
from src import workbench_arrangement_qml as seam
from src.arrangement_32_field_time import build_32_field_channel_rack_state
from src.pattern_core import Channel
from src.workbench_feature_settings import (
    WorkbenchFeatureSettings, save_workbench_feature_settings,
)
from src.workbench_session import compose_workbench_session
from tests.test_active_track_persistence_1098 import _seed_bound_session
from tests.test_arrangement_domain_1087 import rack, tempo


@pytest.fixture
def session():
    r = rack()
    s = SimpleNamespace(channel_rack=SimpleNamespace(state=r),
                        arrangement_state=ad.ArrangementState.for_rack(r),
                        transport=SimpleNamespace(tempo_map=tempo()))
    def save(state):
        s.arrangement_state = state
    s.set_arrangement_state = Mock(side_effect=save)
    return s


def project(s, start=0, count=2):
    return seam.project_arrangement_block_window(s, start, count)


def toggle(s, kind, index=1, identity=None):
    fn = getattr(seam, f"request_arrangement_{kind}_toggle")
    return fn(s, index) if kind == "block" else fn(s, identity, index)


def test_four_immutable_groups_and_bounded_default_on_window(session):
    p = project(session, 5, 2)
    assert tuple(g.group_id for g in p.groups) == tuple(ad.PRESENTATION_GROUPS)
    assert tuple(g.display_name for g in p.groups) == (
        "Baseline", "Drums", "Melodic / Atmos / FX", "Vocals")
    assert {g.group_id: g.channel_ids for g in p.groups} == session.arrangement_state.groups(session.channel_rack.state)
    assert [b.block_index for b in p.blocks] == [5, 6]
    assert len(p.group_blocks) == 8
    assert len(p.track_blocks) == len(session.channel_rack.state.channels) * 2
    assert all(b.status == "eligible" and b.enabled for b in p.blocks)
    assert all(t.enabled and t.effective is True for t in p.track_blocks)
    with pytest.raises(FrozenInstanceError):
        p.blocks[0].enabled = False
    assert project(session, 0, 0).blocks == ()


@pytest.mark.parametrize("kind,identity,field,key", [
    ("block", None, "disabled_blocks", 1),
    ("group", "pg_baseline", "disabled_group_blocks", ("pg_baseline", 1)),
    ("track", "ch_kick", "disabled_track_blocks", ("ch_kick", 1)),
])
def test_one_intent_one_domain_command_one_save_and_sparse_restore(session, monkeypatch, kind, identity, field, key):
    method = "set_" + kind
    original = getattr(ad.ArrangementState, method)
    calls = []
    def spy(self, *args, **kwargs):
        calls.append((args, kwargs))
        return original(self, *args, **kwargs)
    monkeypatch.setattr(ad.ArrangementState, method, spy)
    before = session.arrangement_state.to_payload()
    result = toggle(session, kind, identity=identity)
    assert result.ok and result.outcome == "mutated"
    assert result.projection == project(session, 1, 1)
    assert len(calls) == 1
    session.set_arrangement_state.assert_called_once_with(session.arrangement_state)
    assert getattr(session.arrangement_state, field) == frozenset({key})
    for other in ("disabled_blocks", "disabled_group_blocks", "disabled_track_blocks"):
        if other != field:
            assert getattr(session.arrangement_state, other) == frozenset()
    assert toggle(session, kind, identity=identity).ok
    assert session.arrangement_state.to_payload() == before


def test_group_cycle_preserves_track_and_effective_domain_truth(session):
    assert toggle(session, "track", identity="ch_kick").ok
    assert toggle(session, "group", identity="pg_baseline").ok
    p = project(session, 1, 1)
    assert not next(g for g in p.group_blocks if g.group_id == "pg_baseline").enabled
    assert toggle(session, "group", identity="pg_baseline").ok
    assert session.arrangement_state.disabled_track_blocks == frozenset({("ch_kick", 1)})
    for t in project(session, 1, 1).track_blocks:
        assert t.effective == session.arrangement_state.effective(t.channel_id, 1, session.channel_rack.state, session.transport.tempo_map)
    assert toggle(session, "block").ok
    assert all(g.available is False for g in project(session, 1, 1).group_blocks)


@pytest.mark.parametrize("index", [-1, True, 1.5, "1", None, 19, 10**9])
@pytest.mark.parametrize("kind,identity", [("block", None), ("group", "pg_drums"), ("track", "ch_kick")])
def test_invalid_target_no_domain_mutation_or_save(session, monkeypatch, index, kind, identity):
    before = session.arrangement_state
    def forbidden(*args, **kwargs):
        pytest.fail("invalid intent reached domain mutation")
    for name in ("set_block", "set_group", "set_track"):
        monkeypatch.setattr(ad.ArrangementState, name, forbidden)
    assert not toggle(session, kind, index, identity).ok
    assert session.arrangement_state is before
    session.set_arrangement_state.assert_not_called()


@pytest.mark.parametrize("kind,identity", [("group", "unknown"), ("group", []), ("track", "missing"), ("track", [])])
def test_unknown_identity_fail_closed(session, kind, identity):
    before = session.arrangement_state
    assert not toggle(session, kind, identity=identity).ok
    assert session.arrangement_state is before
    session.set_arrangement_state.assert_not_called()


def test_unmapped_and_migration_required_prevent_track_mutation(session):
    session.channel_rack.state = replace(session.channel_rack.state, channels=(*session.channel_rack.state.channels, Channel("ch_user_1", None, None, "Drums/kick.wav")))
    assert project(session).membership_status == "migration_required"
    unknown = [t for t in project(session).track_blocks if t.channel_id == "ch_user_1"]
    assert unknown and all(t.group_id == "unmapped" and t.effective == "unresolved" for t in unknown)
    for channel in ("ch_user_1", "ch_kick"):
        result = toggle(session, "track", identity=channel)
        assert not result.ok and result.outcome == "migration_required"
    session.set_arrangement_state.assert_not_called()


def test_projection_only_is_pure_and_horizon_uses_live_tempo(session, monkeypatch):
    before = session.arrangement_state.to_payload()
    def forbidden(*args, **kwargs):
        pytest.fail("projection mutated")
    for name in ("set_block", "set_group", "set_track"):
        monkeypatch.setattr(ad.ArrangementState, name, forbidden)
    assert project(session, 18, 2).blocks[1].status == "out_of_current_horizon"
    session.transport.tempo_map = tempo(60)
    assert project(session, 18, 1).blocks[0].status == "out_of_current_horizon"
    assert session.arrangement_state.to_payload() == before
    session.set_arrangement_state.assert_not_called()


@pytest.mark.parametrize("start,count", [(-1, 1), (True, 1), (0, -1), (0, True), (0, 1.5)])
def test_invalid_window_rejected_without_persistence(session, start, count):
    with pytest.raises(ValueError):
        project(session, start, count)
    session.set_arrangement_state.assert_not_called()


def test_real_active_owner_persistence_reentry_restart_and_pattern_unchanged(tmp_path):
    s, state_dir, root, _, legacy = _seed_bound_session(tmp_path)
    try:
        s.channel_rack.restore_state(build_32_field_channel_rack_state(s.live_kit))
        s.set_arrangement_state(ad.ArrangementState.for_rack(s.channel_rack.state))
        assert save_workbench_feature_settings(replace(WorkbenchFeatureSettings(), arrangement_mode_enabled=True), state_dir=state_dir)
        assert s.enter_arrangement_from_edit().ok
        pattern = s.channel_rack.state.pattern
        fields = seam.project_arrangement_for_qml(s)
        for kind, identity in (("block", None), ("group", "pg_drums"), ("track", "ch_kick")):
            assert toggle(s, kind, identity=identity).ok
        assert s.channel_rack.state.pattern is pattern
        assert seam.project_arrangement_for_qml(s) == fields
        saved = s.arrangement_state
        assert json.loads((root / "track_package.json").read_text())["arrangement"] == saved.to_payload()
        assert not s.track_package_dirty
        s.return_to_edit()
        assert s.enter_arrangement_from_edit().ok
        assert s.arrangement_state == saved
        assert s.channel_rack.state.pattern == pattern
        assert (state_dir / "workbench_session.json").read_bytes() == legacy
    finally:
        s.transport.close()
    restarted = compose_workbench_session(state_dir=state_dir)
    try:
        assert restarted.arrangement_state == saved
    finally:
        restarted.transport.close()
