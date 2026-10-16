"""Runtime contract vectors for #1087 (frozen before implementation)."""
from dataclasses import replace
from fractions import Fraction
import builtins
import json
from pathlib import Path

import pytest

from src import arrangement_domain as ad
from src import arrangement_32_field_time as a32
from src import track_package as tp
from src.channel_rack import ChannelRackState
from src.pattern_core import Channel, Trigger
from src.session_grid import TempoMap
from src.workbench_live_kit import LiveKitState, LiveKitPresentationState
from src.workbench_session import compose_workbench_session
from tests.test_active_track_persistence_1098 import _seed_bound_session


def rack():
    state = a32.build_32_field_channel_rack_state(LiveKitState())
    return replace(state, pattern=a32.build_32_field_pattern(
        state.pattern.pattern_id,
        (Trigger("ch_kick", Fraction(0)), Trigger("ch_bass", Fraction(31)),
         Trigger("ch_main_drum", Fraction(4))),
    ))


def tempo(bpm=120):
    return TempoMap(sample_rate=48000, bpm=bpm)


def test_sparse_defaults_membership_and_presentation():
    r = rack()
    state = ad.ArrangementState.for_rack(r)
    before = state.to_payload()
    for index in (0, 1, 18):
        assert state.block_status(index, tempo()) == "eligible"
        assert state.effective("ch_kick", index, r, tempo()) is True
    for key in ("disabled_blocks", "disabled_group_blocks", "disabled_track_blocks"):
        assert before[key] == []
    assert state.groups(r) == {
        "pg_baseline": ("ch_kick", "ch_bass"),
        "pg_drums": ("ch_main_drum", "ch_closed_hat", "ch_open_hat", "ch_percussion", "ch_additional"),
        "pg_melodic_atmos_fx": ("ch_lead", "ch_pad", "ch_atmos", "ch_fx"),
        "pg_vocals": (),
    }
    presentation = LiveKitPresentationState(LiveKitState())
    presentation.toggle_group("Kick + Bass")
    presentation.toggle_group("Kick + Bass")
    assert state.to_payload() == before
    assert r == rack()
    assert state.render_eligible(r, tempo()) is False


def test_masks_independent_deterministic_and_round_trip():
    r, tm = rack(), tempo()
    state = ad.ArrangementState.for_rack(r).set_track("ch_kick", 1, False, r, tm)
    state = state.set_group("pg_baseline", 1, False, tm)
    assert state.effective("ch_bass", 1, r, tm) is False
    state = state.set_group("pg_baseline", 1, True, tm)
    assert state.effective("ch_kick", 1, r, tm) is False
    assert state.effective("ch_bass", 1, r, tm) is True
    state = state.set_group("pg_drums", 2, False, tm).set_block(3, False, tm)
    restored = ad.ArrangementState.from_payload(state.to_payload(), r)
    assert restored == state
    assert restored.effective("ch_main_drum", 2, r, tm) is False
    assert restored.effective("ch_bass", 3, r, tm) is False
    other = ad.ArrangementState.for_rack(r).set_block(3, False, tm)
    other = other.set_group("pg_drums", 2, False, tm).set_track("ch_kick", 1, False, r, tm)
    assert json.dumps(other.to_payload()) == json.dumps(state.to_payload())
    assert other.set_block(3, True, tm).to_payload()["disabled_blocks"] == []


@pytest.mark.parametrize("index", [-1, True, 1.0, "1", None, 19])
def test_invalid_or_out_of_horizon_block_no_mutation(index):
    state = ad.ArrangementState.for_rack(rack())
    before = state.to_payload()
    with pytest.raises(ad.ArrangementError):
        state.set_block(index, False, tempo())
    assert state.to_payload() == before


@pytest.mark.parametrize("kind,identity", [("group", "Drums"), ("group", []), ("track", "ch_missing")])
def test_invalid_identity_no_mutation(kind, identity):
    r = rack()
    state = ad.ArrangementState.for_rack(r)
    before = state.to_payload()
    with pytest.raises(ad.ArrangementError):
        if kind == "group":
            state.set_group(identity, 0, False, tempo())
        else:
            state.set_track(identity, 0, False, r, tempo())
    assert state.to_payload() == before


def test_unknown_channels_preserved_unmapped_never_silent_played_or_muted():
    base = rack()
    user = Channel("ch_user_1", None, None, "Drums/kick.wav")
    r = ChannelRackState(base.channels + (user,), a32.build_32_field_pattern(
        base.pattern.pattern_id, (*base.pattern.triggers, Trigger(user.channel_id, Fraction(8)))
    ), 32)
    state = ad.ArrangementState.for_rack(r).set_end_marker(Fraction(64))
    before = r
    assert state.membership(user.channel_id, r) == "unmapped"
    assert state.membership_status(r) == "migration_required"
    assert state.effective(user.channel_id, 0, r, tempo()) == "unresolved"
    assert state.render_eligible(r, tempo()) is False
    with pytest.raises(ad.ArrangementError, match="migration_required"):
        state.plan_block(0, r, tempo(), block_start_engine_frame=0)
    assert ad.ArrangementState.from_payload(state.to_payload(), r) == state
    assert r == before
    assert user.channel_id not in sum(state.groups(r).values(), ())


@pytest.mark.parametrize("marker", [Fraction(0), Fraction(-4), Fraction(3), Fraction(1, 2), True, 4.0, "4"])
def test_invalid_marker_rejected(marker):
    state = ad.ArrangementState.for_rack(rack())
    with pytest.raises(ad.ArrangementError):
        state.set_end_marker(marker)
    assert state.end_marker_qn is None


def test_marker_and_horizon_recomputed_without_musical_mutation():
    r = rack()
    state = ad.ArrangementState.for_rack(r).set_end_marker(Fraction(1200))
    state = state.set_block(18, False, tempo())
    assert state.render_eligible(r, tempo()) is True
    assert state.block_status(18, tempo()) == "eligible"
    assert state.block_status(19, tempo()) == "out_of_current_horizon"
    before = state.to_payload()
    assert state.render_eligible(r, tempo(60)) is False
    assert state.block_status(18, tempo(60)) == "out_of_current_horizon"
    assert state.end_marker_qn == Fraction(1200)
    assert state.to_payload() == before
    assert ad.ArrangementState.from_payload(before, r) == state
    changed = tempo()
    changed._append_or_replace_segment(effective_frame=48000 * 32,
                                      effective_quarter=Fraction(64), bpm=60)
    assert state.block_status(10, changed) == "out_of_current_horizon"


@pytest.mark.parametrize("key,value", [
    ("disabled_blocks", [True]), ("disabled_blocks", [-1]),
    ("disabled_blocks", [1, 1]), ("disabled_blocks", "1"),
    ("disabled_group_blocks", [{"group_id": "bogus", "block_index": 0}]),
    ("disabled_track_blocks", [{"channel_id": "missing", "block_index": 0}]),
    ("disabled_track_blocks", [None]), ("disabled_group_blocks", {}),
    ("end_marker_qn", "3"), ("end_marker_qn", "0"),
    ("pattern_id", "unknown"), ("schema_version", True), ("surprise", []),
])
def test_corrupt_payload_fail_closed(key, value):
    r = rack()
    payload = ad.ArrangementState.for_rack(r).to_payload()
    payload[key] = value
    with pytest.raises(ad.ArrangementError):
        ad.ArrangementState.from_payload(payload, r)


@pytest.mark.parametrize("mask,expected", [("none", 6), ("block", 0), ("group", 2), ("track", 4)])
def test_playback_single_projection_masks_no_io(mask, expected, monkeypatch):
    r, tm = rack(), tempo()
    state = ad.ArrangementState.for_rack(r)
    if mask == "block":
        state = state.set_block(1, False, tm)
    if mask == "group":
        state = state.set_group("pg_baseline", 1, False, tm)
    if mask == "track":
        state = state.set_track("ch_kick", 1, False, r, tm)
    def forbidden(*args, **kwargs):
        raise AssertionError("I/O in scheduling")
    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(tp, "save_track_package_musical_state", forbidden)
    planned = state.plan_block(1, r, tm, block_start_engine_frame=1536000)
    assert len(planned) == expected
    assert len({(e.channel_id, e.engine_frame) for e in planned}) == expected
    if mask == "none":
        assert sorted(e.engine_frame for e in planned) == [1536000, 1632000, 2280000, 2304000, 2400000, 3048000]
    assert r == rack()


def test_pattern_edit_both_repetitions_and_marker_limits_events():
    r = rack()
    state = ad.ArrangementState.for_rack(r).set_end_marker(Fraction(36))
    changed = replace(r, pattern=a32.remove_field(r.pattern, Trigger("ch_kick", Fraction(0))))
    events = state.plan_block(0, changed, tempo(), block_start_engine_frame=0)
    assert [(e.channel_id, e.position) for e in events] == [("ch_main_drum", Fraction(4)), ("ch_bass", Fraction(31))]


def test_active_owner_restart_and_failure_honesty(tmp_path, monkeypatch):
    session, state_dir, root, _, legacy_before = _seed_bound_session(tmp_path)
    try:
        r = a32.build_32_field_channel_rack_state(session.live_kit)
        session.channel_rack.restore_state(r)
        state = ad.ArrangementState.for_rack(r).set_end_marker(Fraction(64))
        state = state.set_track("ch_kick", 0, False, r, tempo())
        session.set_arrangement_state(state)
        assert session.arrangement_state == state
        manifest = root / tp.TRACK_PACKAGE_FILENAME
        before = manifest.read_bytes()
        assert json.loads(before)["arrangement"] == state.to_payload()
        real_replace = tp.os.replace
        def fail(src, dst):
            if Path(dst) == manifest:
                raise OSError("synthetic write failure")
            return real_replace(src, dst)
        monkeypatch.setattr(tp.os, "replace", fail)
        updated = state.set_end_marker(Fraction(128))
        session.set_arrangement_state(updated)
        assert session.arrangement_state == updated
        assert session.track_package_status == tp.OUTCOME_WRITE_FAILED
        assert session.track_package_dirty is True
        assert manifest.read_bytes() == before
        monkeypatch.setattr(tp.os, "replace", real_replace)
        session.transport.set_tempo(140)
        assert session.track_package_status == tp.OUTCOME_OPEN
        assert session.track_package_dirty is False
    finally:
        session.transport.close()
    restarted = compose_workbench_session(state_dir=state_dir)
    try:
        assert restarted.arrangement_state == updated
        assert restarted.channel_rack.state.step_count == 32
        assert (state_dir / "workbench_session.json").read_bytes() == legacy_before
    finally:
        restarted.transport.close()


def test_fresh_session_inert_cannot_write_arrangement_to_global_store(tmp_path):
    session = compose_workbench_session(state_dir=tmp_path)
    try:
        assert session.arrangement_state is None
        with pytest.raises(ad.ArrangementError, match="active_track"):
            session.set_arrangement_state(ad.ArrangementState.for_rack(rack()))
        assert session.channel_rack.state is None
        assert not (tmp_path / "workbench_session.json").exists()
    finally:
        session.transport.close()
