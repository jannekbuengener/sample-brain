"""Frozen #1080 C2c2: End Marker + Render Eligibility seam contract; RED until implementation.

Sections:
  Projection (1-9), Snap (10-16), Mutation (17-24), Nudge / Keyboard (25-29),
  Render Eligibility (30-35), Accessibility (36-37), Persistence / Re-entry (38-40),
  Regression (41-46).

Fail-closed rule: all invalid inputs yield controlled results, zero mutations,
and never mutate session state after failure.
"""

from dataclasses import FrozenInstanceError, replace
from fractions import Fraction
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src import arrangement_domain as ad
from src import workbench_arrangement_qml as seam
from src.arrangement_32_field_time import (
    ARRANGEMENT_BLOCK_LENGTH_QUARTER_NOTES,
    BARS_PER_CYCLE,
    FIELDS_PER_BAR,
    TOTAL_FIELDS,
)
from src.pattern_core import Channel
from src.workbench_qml import QML_SOURCE, _qml_arrangement_bridge
from tests.test_arrangement_domain_1087 import tempo as tempo_fixture
from tests.test_workbench_arrangement_qml_1080_c1 import session as c1_session  # noqa: F401


# --- Fixtures --- #

def tempo(bpm=120):
    return tempo_fixture(bpm)


@pytest.fixture
def session(c1_session):
    return c1_session


def make_session(state, bpm=120):
    s = SimpleNamespace(
        channel_rack=SimpleNamespace(state=state),
        arrangement_state=ad.ArrangementState.for_rack(state),
        transport=SimpleNamespace(tempo_map=tempo(bpm)),
    )

    def save(new_state):
        s.arrangement_state = new_state

    s.set_arrangement_state = Mock(side_effect=save)
    return s


def migrated_rack():
    r = rack_state()
    unknown = Channel("ch_unknown_zzz", None, None, "/tmp/unknown.wav")
    return replace(r, channels=tuple(r.channels) + (unknown,))


def rack_state():
    # Import late to mirror C1 fixture authority (rack() from 1087).
    from tests.test_arrangement_domain_1087 import rack

    return rack()


@pytest.fixture
def migration_session():
    return make_session(migrated_rack())


def vp(start=200, duration=360, horizon=1200):
    return seam.ArrangementViewportState(
        start_quarter_note=Fraction(start),
        visible_duration_qn=Fraction(duration),
        zoom_level=1.0,
        logical_horizon_qn=Fraction(horizon),
    )


def set_marker(s, qn):
    """Place a marker directly on state (independent of the mutation API)."""
    s.arrangement_state = replace(s.arrangement_state, end_marker_qn=Fraction(qn))


def domain_horizon(tempo_map):
    return tempo_map.frame_to_quarter_note(600 * tempo_map.sample_rate)


def stage_source():
    return QML_SOURCE.split('id: arrangementStageComponent', 1)[1].split(
        'id: arrangementStageHeader', 1)[0]


def save_spy(s, monkeypatch):
    spy = Mock(wraps=s.set_arrangement_state)
    monkeypatch.setattr(s, "set_arrangement_state", spy)
    return spy


# --- Projection (1-9) --- #

def test_projection_returns_frozen_dataclass(session):
    p = seam.project_end_marker(session, vp())
    assert isinstance(p, seam.ArrangementEndMarkerProjection)
    with pytest.raises(FrozenInstanceError):
        p.exists = True


def test_no_marker_projection_defaults(session):
    p = seam.project_end_marker(session, vp())
    assert p.exists is False
    assert p.quarter_note is None
    assert p.visible is False
    assert p.normalized_position is None
    assert p.render_eligible is False


def test_marker_inside_viewport_projection_fields(session):
    set_marker(session, 96)
    p = seam.project_end_marker(session, vp())
    assert p.exists is True
    assert p.quarter_note == Fraction(96)
    assert p.visible is True
    assert p.normalized_position == Fraction(96 - 200, 360)
    assert p.render_eligible is True


def test_marker_outside_viewport_not_visible_still_exists(session):
    set_marker(session, 24)
    left = seam.project_end_marker(session, vp())
    assert left.exists is True
    assert left.quarter_note == Fraction(24)
    assert left.visible is False
    assert left.normalized_position == Fraction(24 - 200, 360)

    sessionB = make_session(session.channel_rack.state)
    set_marker(sessionB, 1200)
    right = seam.project_end_marker(sessionB, vp())
    assert right.exists is True
    assert right.visible is False
    assert right.normalized_position == Fraction(1200 - 200, 360)


def test_projection_is_pure_zero_saves(session, monkeypatch):
    set_marker(session, 96)
    spy = save_spy(session, monkeypatch)
    v = vp()
    first = seam.project_end_marker(session, v)
    second = seam.project_end_marker(session, v)
    assert first == second
    spy.assert_not_called()


def test_projection_missing_context_fails_closed():
    dead = SimpleNamespace(
        channel_rack=SimpleNamespace(state=None),
        arrangement_state=None,
        transport=SimpleNamespace(tempo_map=None),
    )
    with pytest.raises(ad.ArrangementError, match="no_arrangement_state"):
        seam.project_end_marker(dead, vp())


def test_projection_render_eligible_false_migration_required(migration_session):
    set_marker(migration_session, 96)
    p = seam.project_end_marker(migration_session, vp())
    assert p.exists is True
    assert p.render_eligible is False


def test_projection_render_eligible_matches_domain_state_method(session):
    fresh = make_session(session.channel_rack.state)
    p_fresh = seam.project_end_marker(fresh, vp())
    assert p_fresh.render_eligible == fresh.arrangement_state.render_eligible(
        fresh.channel_rack.state, fresh.transport.tempo_map)

    set_marker(session, 96)
    p = seam.project_end_marker(session, vp())
    assert p.render_eligible == session.arrangement_state.render_eligible(
        session.channel_rack.state, session.transport.tempo_map)
    assert p.render_eligible is True


def test_projection_marker_at_horizon_is_eligible(session):
    assert domain_horizon(session.transport.tempo_map) == Fraction(1200)
    set_marker(session, 1200)
    p = seam.project_end_marker(session, vp())
    assert p.render_eligible is True


# --- Snap (10-16) --- #

def test_python_owned_snap_constant_is_four_qn():
    assert seam.ARRANGEMENT_END_MARKER_SNAP_QN == 4


def test_snap_exact_multiples_unchanged(session):
    for qn in (4, 8, 400, 1200):
        assert seam.snap_end_marker_qn(Fraction(qn)) == Fraction(qn)


def test_snap_ties_reduce_to_lower_multiple():
    assert seam.snap_end_marker_qn(Fraction(6)) == Fraction(4)
    assert seam.snap_end_marker_qn(Fraction(7)) == Fraction(8)
    assert seam.snap_end_marker_qn(Fraction(11, 2)) == Fraction(4)


def test_snap_fractional_qn_rounds_to_nearest():
    assert seam.snap_end_marker_qn(Fraction(59, 10)) == Fraction(4)
    assert seam.snap_end_marker_qn(Fraction(27, 2)) == Fraction(12)
    assert seam.snap_end_marker_qn(Fraction(23, 2)) == Fraction(12)
    assert seam.snap_end_marker_qn(Fraction(35, 4)) == Fraction(8)


def test_snap_below_first_block_clamps_to_zero():
    assert seam.snap_end_marker_qn(Fraction(1)) == Fraction(0)
    assert seam.snap_end_marker_qn(Fraction(2)) == Fraction(0)
    assert seam.snap_end_marker_qn(Fraction(3)) == Fraction(4)


def test_snap_pure_no_save(session, monkeypatch):
    spy = save_spy(session, monkeypatch)
    for qn in (0, 1, Fraction(11, 2), 96, 1203):
        seam.snap_end_marker_qn(Fraction(qn))
    spy.assert_not_called()


def test_qml_stage_owns_no_snap_or_horizon_math():
    stage = stage_source()
    assert "endMarkerNormalizedPosition" in stage
    for forbidden in ("% 4", "* 4", "/ 4"):
        assert forbidden not in stage


def test_preview_snap_returns_snapped_within_range(session):
    assert seam.preview_end_marker_snap(session, Fraction(7)) == Fraction(8)
    assert seam.preview_end_marker_snap(session, Fraction(11, 2)) == Fraction(4)
    assert seam.preview_end_marker_snap(session, Fraction(1200)) == Fraction(1200)


def test_preview_snap_none_out_of_range(session):
    assert seam.preview_end_marker_snap(session, Fraction(1)) is None
    assert seam.preview_end_marker_snap(session, Fraction(1205)) is None
    assert seam.preview_end_marker_snap(session, Fraction(-50)) is None


# --- Mutation (17-24) --- #

def test_set_valid_value_commits_snapped_one_save(session):
    result = seam.request_end_marker_set(session, Fraction(97))
    assert result.ok is True
    assert isinstance(result.status, str) and result.status
    assert session.arrangement_state.end_marker_qn == Fraction(96)
    assert session.set_arrangement_state.call_count == 1
    assert result.projection.quarter_note == Fraction(96)
    assert result.projection.render_eligible is True


def test_set_snaps_fractional_input(session):
    result = seam.request_end_marker_set(session, Fraction(47, 2))
    assert result.ok is True
    assert session.arrangement_state.end_marker_qn == Fraction(24)


def test_set_same_value_each_call_one_save(session):
    first = seam.request_end_marker_set(session, Fraction(96))
    assert first.ok is True
    assert session.set_arrangement_state.call_count == 1
    second = seam.request_end_marker_set(session, Fraction(96))
    assert second.ok is True
    assert session.set_arrangement_state.call_count == 2
    assert session.arrangement_state.end_marker_qn == Fraction(96)


def test_set_non_positive_fails_closed_zero_saves(session):
    for bad in (Fraction(0), Fraction(-12)):
        result = seam.request_end_marker_set(session, bad)
        assert result.ok is False
        assert session.arrangement_state.end_marker_qn is None
        assert session.set_arrangement_state.call_count == 0


def test_set_beyond_horizon_fails_closed(session):
    for bad in (Fraction(1205), Fraction(2000)):
        result = seam.request_end_marker_set(session, bad)
        assert result.ok is False
        assert session.arrangement_state.end_marker_qn is None
        assert session.set_arrangement_state.call_count == 0


def test_set_result_projection_is_same_type_as_projection(session):
    result = seam.request_end_marker_set(session, Fraction(96))
    assert isinstance(result.projection, seam.ArrangementEndMarkerProjection)
    assert result.projection == seam.project_end_marker(session, vp())


def test_clear_sets_none_one_save(session):
    set_marker(session, 96)
    result = seam.request_end_marker_clear(session)
    assert result.ok is True
    assert session.arrangement_state.end_marker_qn is None
    assert session.set_arrangement_state.call_count == 1
    assert result.projection.exists is False


def test_clear_idempotent_no_marker_already_cleared_zero_saves(session):
    result = seam.request_end_marker_clear(session)
    assert result.ok is True
    assert result.status == "already_cleared"
    assert session.set_arrangement_state.call_count == 0


# --- Nudge / Keyboard (25-29) --- #

def test_nudge_without_marker_fails_closed(session):
    result = seam.request_end_marker_nudge(session, +1)
    assert result.ok is False
    assert session.set_arrangement_state.call_count == 0


def test_nudge_right_commits(session):
    set_marker(session, 96)
    result = seam.request_end_marker_nudge(session, +1)
    assert result.ok is True
    assert session.arrangement_state.end_marker_qn == Fraction(100)
    assert session.set_arrangement_state.call_count == 1


def test_nudge_left_commits(session):
    set_marker(session, 8)
    result = seam.request_end_marker_nudge(session, -1)
    assert result.ok is True
    assert session.arrangement_state.end_marker_qn == Fraction(4)
    assert session.set_arrangement_state.call_count == 1


def test_nudge_left_at_first_block_fails_closed(session):
    set_marker(session, 4)
    result = seam.request_end_marker_nudge(session, -1)
    assert result.ok is False
    assert session.arrangement_state.end_marker_qn == Fraction(4)
    assert session.set_arrangement_state.call_count == 0


def test_nudge_beyond_horizon_and_invalid_direction_fails(session):
    set_marker(session, 1200)
    result = seam.request_end_marker_nudge(session, +1)
    assert result.ok is False
    assert session.set_arrangement_state.call_count == 0
    assert session.arrangement_state.end_marker_qn == Fraction(1200)

    for bad_direction in (0, 2, "up"):
        result = seam.request_end_marker_nudge(session, bad_direction)
        assert result.ok is False
        assert session.set_arrangement_state.call_count == 0


# --- Render Eligibility (30-35) --- #

def test_render_eligible_false_without_marker(session):
    p = seam.project_end_marker(session, vp())
    assert p.render_eligible is False


def test_render_eligible_true_resolved_within_horizon(session):
    set_marker(session, 400)
    p = seam.project_end_marker(session, vp())
    assert p.render_eligible is True


def test_render_eligible_false_direct_beyond_horizon(session, monkeypatch):
    set_marker(session, 1400)
    spy = save_spy(session, monkeypatch)
    p = seam.project_end_marker(session, vp())
    assert p.exists is True
    assert p.render_eligible is False
    spy.assert_not_called()


def test_render_eligible_false_migration_required_marker_divergence(migration_session):
    set_marker(migration_session, 96)
    p = seam.project_end_marker(migration_session, vp())
    assert p.exists is True
    assert p.render_eligible is False


def test_qml_stage_binds_projection_not_computation():
    stage = stage_source()
    assert "endMarkerRenderEligible" in stage
    assert "endMarkerQn >" not in stage
    assert "endMarkerQn <" not in stage


def test_projection_after_tempo_change_updates_eligibility_zero_saves(session, monkeypatch):
    set_marker(session, 400)
    spy = save_spy(session, monkeypatch)
    fast = seam.project_end_marker(session, vp())
    assert fast.render_eligible is True
    assert fast.quarter_note == Fraction(400)

    session.transport = SimpleNamespace(tempo_map=tempo(30))
    slow_vp = vp(horizon=300)
    slow = seam.project_end_marker(session, slow_vp)
    assert slow.render_eligible is False
    assert slow.quarter_note == Fraction(400)
    spy.assert_not_called()


# --- Accessibility (36-37) --- #

def test_qml_end_marker_has_accessibility_roles():
    stage = stage_source()
    assert "Accessible.role" in stage
    assert "Accessible.name" in stage
    assert "endMarker" in stage
    assert "END" in stage


def test_end_marker_projection_visible_bounds(session):
    set_marker(session, 200)  # exactly viewport start -> inclusive
    p = seam.project_end_marker(session, vp())
    assert p.visible is True
    assert p.normalized_position == Fraction(0)

    set_marker(session, 560)  # exactly viewport end -> inclusive
    p = seam.project_end_marker(session, vp())
    assert p.visible is True
    assert p.normalized_position == Fraction(1)

    set_marker(session, 560.5)
    p = seam.project_end_marker(session, vp())
    assert p.visible is False


# --- Persistence / Re-entry (38-40) --- #

def test_marker_roundtrips_payload_projection_identical(session):
    set_marker(session, 96)
    v = vp()
    before = seam.project_end_marker(session, v)
    payload = session.arrangement_state.to_payload()
    restored = ad.ArrangementState.from_payload(payload, session.channel_rack.state)
    session2 = make_session(session.channel_rack.state, bpm=120)
    session2.arrangement_state = restored
    after = seam.project_end_marker(session2, v)
    assert before == after


def test_reentry_two_fresh_projections_identical():
    s1 = make_session(rack_state())
    s2 = make_session(rack_state())
    set_marker(s1, 96)
    set_marker(s2, 96)
    v = vp()
    assert seam.project_end_marker(s1, v) == seam.project_end_marker(s2, v)


def test_bridge_refresh_zero_saves_marker_projection_persists(session, monkeypatch):
    pytest.importorskip("PySide6")
    set_marker(session, 96)
    spy = save_spy(session, monkeypatch)
    session.projection_mode = "ARRANGEMENT"
    bridge = _qml_arrangement_bridge(session, SimpleNamespace(arrangement_mode_enabled=True))
    first = bridge.refresh()
    second = bridge.refresh()
    assert first == second or (first is None and second is None)
    assert spy.call_count == 0
    assert session.arrangement_state.end_marker_qn == Fraction(96)


# --- Regression (41-46) --- #

def test_mask_toggles_still_route_and_marker_unchanged(session):
    set_marker(session, 96)
    result = seam.request_arrangement_group_toggle(session, "pg_drums", 1)
    assert result.ok is True
    p = seam.project_end_marker(session, vp())
    assert p.quarter_note == Fraction(96)
    assert session.arrangement_state.end_marker_qn == Fraction(96)


def test_zoom_pan_viewport_pure_and_marker_qn_unchanged(session, monkeypatch):
    set_marker(session, 96)
    spy = save_spy(session, monkeypatch)
    v = vp()
    assert seam.zoom_in(v, Fraction(180), session.transport.tempo_map)
    assert seam.zoom_out(v, Fraction(180), session.transport.tempo_map)
    panned = seam.pan(v, Fraction(64))
    assert panned.start_quarter_note + panned.visible_duration_qn <= v.logical_horizon_qn
    spy.assert_not_called()
    p = seam.project_end_marker(session, v)
    assert p.quarter_note == Fraction(96)


def test_c2c1_block_projection_unaffected_by_marker(session):
    set_marker(session, 96)
    window = seam.project_visible_blocks(session, vp())
    assert tuple(g.group_id for g in window.groups) == tuple(ad.PRESENTATION_GROUPS)
    blocks = session.arrangement_state.groups(session.channel_rack.state)
    assert {g.group_id: g.channel_ids for g in window.groups} == blocks
    assert window.blocks
    assert session.set_arrangement_state.call_count == 0


def test_sequencer_block_constants_unchanged():
    assert TOTAL_FIELDS == 32
    assert FIELDS_PER_BAR == 4
    assert BARS_PER_CYCLE == 8
    assert ARRANGEMENT_BLOCK_LENGTH_QUARTER_NOTES == 64


def test_no_render_or_export_creep_in_marker_work():
    import inspect
    import src.workbench_arrangement_qml as seam_module

    src_text = inspect.getsource(seam_module)
    assert "def export" not in src_text
    assert not hasattr(seam_module, "request_end_marker_export")
    stage = stage_source()
    assert "exportAudio" not in stage
    assert "renderAudio" not in stage


def test_marker_ops_still_work_on_migration_state_but_stay_ineligible(migration_session):
    result = seam.request_end_marker_set(migration_session, Fraction(96))
    assert result.ok is True
    assert migration_session.arrangement_state.end_marker_qn == Fraction(96)
    p = seam.project_end_marker(migration_session, vp())
    assert p.render_eligible is False
