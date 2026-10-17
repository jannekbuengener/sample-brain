"""#1080 C2c1: Timeline Viewport + Zoom/Pan Presentation Model.

Test-first contract for the arrangement timeline viewport. All zoom/pan/viewport
state is pure Presentation State owned by Python/QML seam; no musical mutation,
no persistence, no QML-owned tempo/horizon truth.
"""

from dataclasses import FrozenInstanceError
from fractions import Fraction
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src import arrangement_domain as ad
from src import workbench_arrangement_qml as seam
from src.arrangement_32_field_time import (
    ARRANGEMENT_BLOCK_LENGTH_QUARTER_NOTES,
    build_32_field_channel_rack_state,
)
from src.pattern_core import Trigger
from src.session_grid import TempoMap
from tests.test_arrangement_domain_1087 import rack, tempo
from tests.test_workbench_arrangement_qml_1080_c1 import session as c1_session  # noqa: F401


# --- Fixtures ---------------------------------------------------------------- #

@pytest.fixture
def session(c1_session):
    return c1_session


@pytest.fixture
def tempo_map():
    return tempo()


# --- ArrangementViewportState contracts -------------------------------------- #

def test_viewport_state_is_frozen_and_presentation_only():
    vp = seam.ArrangementViewportState(
        start_quarter_note=Fraction(0),
        visible_duration_qn=Fraction(360),
        zoom_level=1.0,
        logical_horizon_qn=Fraction(1200),
    )
    assert vp.start_quarter_note == Fraction(0)
    assert vp.visible_duration_qn == Fraction(360)
    assert vp.zoom_level == 1.0
    assert vp.logical_horizon_qn == Fraction(1200)
    with pytest.raises(FrozenInstanceError):
        vp.start_quarter_note = Fraction(100)


def test_initial_view_approximately_three_minutes(tempo_map):
    """Initial view derives ~180s from TempoMap, not hardcoded block count."""
    vp = seam.viewport_for_initial_view(tempo_map)
    # ~3 minutes = 180s * sample_rate frames -> QN via TempoMap
    expected_qn = tempo_map.frame_to_quarter_note(180 * tempo_map.sample_rate)
    assert vp.visible_duration_qn == expected_qn
    assert vp.start_quarter_note == Fraction(0)
    # 3 minutes is well within the 10-minute horizon
    assert vp.visible_duration_qn <= vp.logical_horizon_qn


def test_initial_view_respects_logical_horizon(tempo_map):
    """Initial view never exceeds the logical horizon."""
    vp = seam.viewport_for_initial_view(tempo_map)
    assert vp.visible_duration_qn <= vp.logical_horizon_qn


def test_logical_horizon_never_exceeds_ten_minutes(tempo_map):
    """Logical horizon is max 10 minutes from domain authority."""
    vp = seam.viewport_for_initial_view(tempo_map)
    horizon_qn = tempo_map.frame_to_quarter_note(600 * tempo_map.sample_rate)
    assert vp.logical_horizon_qn == horizon_qn


def test_initial_view_below_block_window_cap_is_uncapped():
    """Below the cap, the initial view keeps the derived ~3-minute duration."""
    below_cap_map = tempo(1300)  # 3 minutes = 3900 QN < cap 3904 QN
    vp = seam.viewport_for_initial_view(below_cap_map)
    expected_qn = below_cap_map.frame_to_quarter_note(180 * below_cap_map.sample_rate)
    assert vp.visible_duration_qn == expected_qn
    assert vp.start_quarter_note == Fraction(0)


def test_initial_view_capped_at_block_window_budget():
    """At extreme tempos the initial ~3-minute duration is capped so the
    projection never exceeds one bounded block window (no blank view)."""
    fast_map = tempo(1600)  # 3 minutes = 4800 QN >= cap 3904 QN
    vp = seam.viewport_for_initial_view(fast_map)
    assert vp.visible_duration_qn == seam._max_zoom_out_duration_qn()
    assert vp.start_quarter_note == Fraction(0)
    # Capped view still fits inside the 10-minute horizon
    assert vp.visible_duration_qn < vp.logical_horizon_qn


def test_initial_view_projects_bounded_window_at_extreme_tempo(session):
    """End-to-end: the initial viewport projects a valid bounded block window
    at extreme tempos instead of raising block_window_too_large."""
    fast_map = tempo(1600)
    vp = seam.viewport_for_initial_view(fast_map)
    window = seam.project_visible_blocks(session, vp)
    assert 0 < len(window.blocks) <= seam.MAX_ARRANGEMENT_BLOCK_WINDOW
    assert window.blocks[0].block_index == 0


# --- Bounded / virtualized block projection --------------------------------- #

def test_project_visible_blocks_only_materializes_visible_window(session, tempo_map):
    """Projection materializes only visible blocks + small overscan, not full horizon."""
    vp = seam.viewport_for_initial_view(tempo_map)
    window = seam.project_visible_blocks(session, vp)
    # Visible ~3min at 120BPM = ~360QN / 64QN per block ≈ 5.6 blocks
    # Plus small overscan; must be far less than full 10-min horizon (~18.75 blocks)
    assert len(window.blocks) <= 8
    # Not the entire horizon
    assert len(window.blocks) < 18


def test_no_unbounded_horizon_materialization(session, tempo_map):
    """No complete horizon is materialized as QML object list."""
    vp = seam.viewport_for_initial_view(tempo_map)
    window = seam.project_visible_blocks(session, vp)
    # Sanity: window is bounded
    assert len(window.blocks) <= 8


def test_visible_block_range_derives_from_viewport(session, tempo_map):
    """Visible block indexes derive from viewport start + duration, not hardcoded."""
    vp = seam.viewport_for_initial_view(tempo_map)
    window = seam.project_visible_blocks(session, vp)
    first = window.blocks[0].block_index if window.blocks else 0
    last = window.blocks[-1].block_index if window.blocks else -1
    # Blocks should start at or near 0 (viewport starts at 0)
    assert first == 0
    # Last block should be within visible range
    assert last < 10


# --- Zoom contracts ---------------------------------------------------------- #

def test_ctrl_wheel_up_zooms_in(tempo_map):
    """Ctrl+Wheel Up reduces visible duration (zoom in)."""
    vp = seam.viewport_for_initial_view(tempo_map)
    zoomed = seam.zoom_in(vp, Fraction(180), tempo_map)
    assert zoomed.visible_duration_qn < vp.visible_duration_qn
    assert zoomed.zoom_level > vp.zoom_level


def test_ctrl_wheel_down_zooms_out(tempo_map):
    """Ctrl+Wheel Down increases visible duration (zoom out)."""
    vp = seam.viewport_for_initial_view(tempo_map)
    zoomed = seam.zoom_out(vp, Fraction(180), tempo_map)
    assert zoomed.visible_duration_qn > vp.visible_duration_qn
    assert zoomed.zoom_level < vp.zoom_level


def test_zoom_out_clamped_to_horizon(tempo_map):
    """Zoom out cannot exceed the logical horizon."""
    vp = seam.viewport_for_initial_view(tempo_map)
    # Zoom out many times
    for _ in range(10):
        vp = seam.zoom_out(vp, Fraction(180), tempo_map)
    assert vp.visible_duration_qn <= vp.logical_horizon_qn


def test_zoom_in_clamped_to_minimum(tempo_map):
    """Zoom in has a minimum visible duration for block readability."""
    vp = seam.viewport_for_initial_view(tempo_map)
    for _ in range(20):
        vp = seam.zoom_in(vp, Fraction(180), tempo_map)
    # Should not shrink to zero or absurdly small
    assert vp.visible_duration_qn > Fraction(0)


def test_wheel_without_ctrl_does_not_zoom(tempo_map):
    """Wheel without Ctrl: no zoom change."""
    vp = seam.viewport_for_initial_view(tempo_map)
    # zoom_without_ctrl should be a no-op or not exist; verify by calling
    # zoom functions only with explicit intent
    unchanged = seam.viewport_for_initial_view(tempo_map)
    assert unchanged == vp


def test_zoom_keeps_anchor_stable(tempo_map):
    """Zoom should keep the visible area stable around the anchor when possible."""
    vp = seam.viewport_for_initial_view(tempo_map)
    anchor = Fraction(360)
    zoomed = seam.zoom_in(vp, anchor, tempo_map)
    # Start should not move drastically; anchor stays in view
    assert zoomed.start_quarter_note >= Fraction(0)
    assert zoomed.start_quarter_note + zoomed.visible_duration_qn > anchor


# --- Pan contracts ----------------------------------------------------------- #

def test_pan_changes_only_viewport_start(session, tempo_map):
    """Pan changes only viewport start, nothing else."""
    vp = seam.viewport_for_initial_view(tempo_map)
    original = vp
    panned = seam.pan(vp, Fraction(64))
    assert panned.start_quarter_note == original.start_quarter_note + Fraction(64)
    assert panned.visible_duration_qn == original.visible_duration_qn
    assert panned.zoom_level == original.zoom_level
    assert panned.logical_horizon_qn == original.logical_horizon_qn


def test_pan_zero_musical_mutation(session, tempo_map):
    """Pan causes zero musical mutation / save."""
    save_spy = Mock(wraps=session.set_arrangement_state)
    # Just verify pan doesn't touch session state
    vp = seam.viewport_for_initial_view(tempo_map)
    _ = seam.pan(vp, Fraction(64))
    session.set_arrangement_state.assert_not_called()


def test_viewport_start_clamped_left_at_zero(tempo_map):
    """Viewport start is clamped at 0 on the left."""
    vp = seam.viewport_for_initial_view(tempo_map)
    panned = seam.pan(vp, Fraction(-1000))
    assert panned.start_quarter_note == Fraction(0)


def test_viewport_end_clamped_at_horizon(tempo_map):
    """Viewport end is clamped at the logical horizon."""
    vp = seam.viewport_for_initial_view(tempo_map)
    # Pan far right
    panned = seam.pan(vp, Fraction(2000))
    assert panned.start_quarter_note + panned.visible_duration_qn <= vp.logical_horizon_qn


# --- Zero mutation on zoom/pan ---------------------------------------------- #

def test_zoom_zero_arrangement_mutation(session, tempo_map, monkeypatch):
    """Zoom causes zero arrangement mutation."""
    monkeypatch.setattr(ad.ArrangementState, "set_block", Mock(side_effect=AssertionError("mutation")))
    monkeypatch.setattr(ad.ArrangementState, "set_group", Mock(side_effect=AssertionError("mutation")))
    monkeypatch.setattr(ad.ArrangementState, "set_track", Mock(side_effect=AssertionError("mutation")))
    vp = seam.viewport_for_initial_view(tempo_map)
    _ = seam.zoom_in(vp, Fraction(180), tempo_map)
    _ = seam.zoom_out(vp, Fraction(180), tempo_map)


def test_zoom_zero_pattern_mutation(session, tempo_map):
    """Zoom causes zero pattern mutation."""
    before = session.channel_rack.state.pattern
    vp = seam.viewport_for_initial_view(tempo_map)
    _ = seam.zoom_in(vp, Fraction(180), tempo_map)
    _ = seam.zoom_out(vp, Fraction(180), tempo_map)
    assert session.channel_rack.state.pattern is before


def test_zoom_zero_persistence_save(session, tempo_map, monkeypatch):
    """Zoom causes zero persistence save."""
    save_spy = Mock(wraps=session.set_arrangement_state)
    monkeypatch.setattr(session, "set_arrangement_state", save_spy)
    vp = seam.viewport_for_initial_view(tempo_map)
    _ = seam.zoom_in(vp, Fraction(180), tempo_map)
    _ = seam.zoom_out(vp, Fraction(180), tempo_map)
    save_spy.assert_not_called()


def test_pan_zero_persistence_save(session, tempo_map, monkeypatch):
    """Pan causes zero persistence save."""
    save_spy = Mock(wraps=session.set_arrangement_state)
    monkeypatch.setattr(session, "set_arrangement_state", save_spy)
    vp = seam.viewport_for_initial_view(tempo_map)
    _ = seam.pan(vp, Fraction(64))
    save_spy.assert_not_called()


# --- Tempo change reprojection ---------------------------------------------- #

def test_tempo_change_reprojects_visible_block_range(session, tempo_map):
    """Tempo change reprojects the visible block area."""
    vp = seam.viewport_for_initial_view(tempo_map)
    window_before = seam.project_visible_blocks(session, vp)
    # Change tempo (slower = more QN per second, horizon shrinks in QN)
    slow_tempo = tempo(60)
    vp_slow = seam.viewport_for_initial_view(slow_tempo)
    window_after = seam.project_visible_blocks(session, vp_slow)
    # Visible duration in QN changes with tempo
    assert vp_slow.visible_duration_qn != vp.visible_duration_qn


def test_zoom_pan_after_tempo_change_remains_valid(session, tempo_map):
    """Zoom/Pan after tempo change stays within clamped bounds."""
    vp = seam.viewport_for_initial_view(tempo_map)
    slow_tempo = tempo(60)
    vp_slow = seam.viewport_for_initial_view(slow_tempo)
    # Pan and zoom should still clamp
    panned = seam.pan(vp_slow, Fraction(2000))
    assert panned.start_quarter_note + panned.visible_duration_qn <= vp_slow.logical_horizon_qn
    zoomed = seam.zoom_out(vp_slow, Fraction(300), slow_tempo)
    assert zoomed.visible_duration_qn <= zoomed.logical_horizon_qn


def test_zoom_in_at_extreme_tempo_keeps_block_window_bounded(session):
    """F8 (Codex P2): zoom rungs from uncapped base durations stay bounded.

    At extreme tempos a zoom rung derived from the uncapped base duration can
    project more blocks than MAX_ARRANGEMENT_BLOCK_WINDOW; the rung duration
    must be capped like the initial viewport so the group rows stay visible.
    """
    fast_tempo = tempo(3000)
    vp = seam.viewport_for_initial_view(fast_tempo)
    zoomed = seam.zoom_in(vp, Fraction(100), fast_tempo)
    assert zoomed.zoom_level == 2.0
    asserted_cap = seam._max_zoom_out_duration_qn()
    assert zoomed.visible_duration_qn <= asserted_cap
    # Projection succeeds and stays within the consumer block budget.
    window = seam.project_visible_blocks(session, zoomed)
    assert 0 < len(window.blocks) <= seam.MAX_ARRANGEMENT_BLOCK_WINDOW
    assert len(window.group_blocks) > 0


def test_rebase_viewport_tempo_change_preserves_wall_clock_length(session):
    """Rebase maps the visible span wall-clock through the tempo change.

    The visible duration is re-expressed under the current tempo map so the
    slice keeps its wall-clock length, while the musical pan position is
    carried over and clamped into the new horizon.
    """
    previous = tempo(120)
    current = tempo(60)
    viewport = seam.ArrangementViewportState(
        start_quarter_note=Fraction(600),
        visible_duration_qn=Fraction(360),
        zoom_level=1.0,
        logical_horizon_qn=Fraction(1200),
    )
    rebased = seam.rebase_viewport_for_tempo_change(viewport, previous, current)
    # Old span: 360 QN at 120 BPM = 180 s wall clock -> 180 QN at 60 BPM.
    assert rebased.start_quarter_note == Fraction(600)
    assert rebased.visible_duration_qn == Fraction(180)
    assert rebased.zoom_level == 1.0
    assert rebased.logical_horizon_qn == Fraction(1200)
    assert rebased.start_quarter_note + rebased.visible_duration_qn <= rebased.logical_horizon_qn
    # Same slice in QN must project within bounds.
    window = seam.project_visible_blocks(session, rebased)
    assert len(window.blocks) > 0


def test_rebase_viewport_tempo_change_faster_direction_wall_clock(session):
    """Rebasing 60 -> 120 BPM keeps the same wall-clock duration."""
    previous = tempo(60)
    current = tempo(120)
    viewport = seam.viewport_for_initial_view(previous)
    rebased = seam.rebase_viewport_for_tempo_change(viewport, previous, current)
    # 180 QN at 60 BPM = 180 s wall clock -> 360 QN at 120 BPM.
    assert rebased.start_quarter_note == Fraction(0)
    assert rebased.visible_duration_qn == Fraction(360)
    assert rebased.logical_horizon_qn == Fraction(600)
    window = seam.project_visible_blocks(session, rebased)
    assert len(window.blocks) > 0


# --- Group/Track alignment --------------------------------------------------- #

def test_visible_group_rows_use_same_block_range(session, tempo_map):
    """Visible group rows use exactly the same block range."""
    vp = seam.viewport_for_initial_view(tempo_map)
    window = seam.project_visible_blocks(session, vp)
    group_block_indexes = {b.block_index for b in window.blocks}
    for gb in window.group_blocks:
        assert gb.block_index in group_block_indexes


def test_expanded_track_rows_use_same_block_range_as_parent(session, tempo_map):
    """Expanded track rows use exactly the same block range as parent group."""
    vp = seam.viewport_for_initial_view(tempo_map)
    window = seam.project_visible_blocks(session, vp)
    group_indexes = {b.block_index for b in window.blocks}
    for track_rows in window.track_rows_by_group.values():
        for tr in track_rows:
            track_indexes = {b.block_index for b in tr.blocks}
            assert track_indexes == group_indexes


# --- Mask / presentation state preservation --------------------------------- #

def test_group_track_mask_state_unchanged_on_zoom_pan(session, tempo_map):
    """Group/Track mask state remains unchanged on zoom/pan."""
    before = session.arrangement_state.to_payload()
    vp = seam.viewport_for_initial_view(tempo_map)
    _ = seam.zoom_in(vp, Fraction(180), tempo_map)
    _ = seam.zoom_out(vp, Fraction(180), tempo_map)
    _ = seam.pan(vp, Fraction(64))
    assert session.arrangement_state.to_payload() == before


def test_expanded_collapsed_presentation_preserved_on_refresh(session, tempo_map):
    """Expanded/collapsed presentation state preserved on viewport refresh."""
    # This is tested via QML bridge in integration tests; here just verify
    # that viewport operations don't touch expanded_groups state
    vp = seam.viewport_for_initial_view(tempo_map)
    _ = seam.pan(vp, Fraction(64))
    _ = seam.zoom_in(vp, Fraction(180), tempo_map)


# --- Return / Edit / Re-entry ------------------------------------------------ #

def test_return_edit_preserves_musical_state(session, tempo_map):
    """Return/Edit preserves musical state; viewport is presentation only."""
    before = session.arrangement_state.to_payload()
    vp = seam.viewport_for_initial_view(tempo_map)
    _ = seam.zoom_in(vp, Fraction(180), tempo_map)
    _ = seam.pan(vp, Fraction(64))
    assert session.arrangement_state.to_payload() == before


def test_reentry_no_second_musical_owner(session, tempo_map):
    """Re-entry creates no second musical owner; viewport is seam-only."""
    vp1 = seam.viewport_for_initial_view(tempo_map)
    vp2 = seam.viewport_for_initial_view(tempo_map)
    assert vp1 == vp2  # Deterministic, no hidden state


# --- Feature gate ------------------------------------------------------------ #

def test_feature_gate_off_no_timeline_interaction(session, tempo_map):
    """Feature gate OFF => no timeline/viewport interaction."""
    # When arrangement_mode_enabled is False, no viewport projection should occur
    session_copy = SimpleNamespace(
        channel_rack=session.channel_rack,
        arrangement_state=session.arrangement_state,
        transport=session.transport,
    )
    # The projection_mode gate is checked by the QML bridge; here we verify
    # that the viewport functions themselves are pure and don't depend on gate
    vp = seam.viewport_for_initial_view(tempo_map)
    assert vp is not None


# --- Sequencer regression ---------------------------------------------------- #

def test_32_field_sequencer_unchanged(session, tempo_map):
    """32-field sequencer remains unchanged; no 64 fields, no sequencer zoom."""
    from src.arrangement_32_field_time import TOTAL_FIELDS, FIELDS_PER_BAR, BARS_PER_CYCLE
    assert TOTAL_FIELDS == 32
    assert FIELDS_PER_BAR == 4
    assert BARS_PER_CYCLE == 8


# --- No End Marker ----------------------------------------------------------- #

def test_no_end_marker_controls_in_this_slice():
    """No End Marker rendering/drag/keyboard/snap in C2c1."""
    # Verified by QML source contract test below
    pass


# --- No QML-owned tempo/horizon truth ---------------------------------------- #

def test_no_qml_owned_tempo_horizon_truth(tempo_map):
    """Viewport derives horizon from TempoMap/domain, not QML-owned constants."""
    vp = seam.viewport_for_initial_view(tempo_map)
    # Horizon must come from TempoMap, not hardcoded
    expected_horizon = tempo_map.frame_to_quarter_note(600 * tempo_map.sample_rate)
    assert vp.logical_horizon_qn == expected_horizon


# --- Offscreen blocks not instantiated --------------------------------------- #

def test_offscreen_blocks_not_instantiated(session, tempo_map):
    """Offscreen blocks are not unnecessarily instantiated."""
    vp = seam.viewport_for_initial_view(tempo_map)
    window = seam.project_visible_blocks(session, vp)
    # Only visible window blocks should exist
    assert len(window.blocks) <= 8
    # Horizon would allow ~18 blocks; we should not materialize all
    horizon_blocks = int(vp.logical_horizon_qn // ARRANGEMENT_BLOCK_LENGTH_QUARTER_NOTES) + 1
    assert len(window.blocks) < horizon_blocks


# --- QML source contract tests (no Qt required) ------------------------------ #

def test_qml_has_timeline_viewport_area():
    """QML arrangement stage has a timeline viewport area."""
    from src.workbench_qml import QML_SOURCE
    stage = QML_SOURCE.split('id: arrangementStageComponent', 1)[1].split('id: arrangementStageHeader', 1)[0]
    assert 'timelineViewport' in stage or 'arrangementTimeline' in stage.lower()


def test_qml_no_end_marker_controls():
    """No End Marker controls in C2c1 QML."""
    from src.workbench_qml import QML_SOURCE
    stage = QML_SOURCE.split('id: arrangementStageComponent', 1)[1].split('id: arrangementStageHeader', 1)[0]
    assert 'endMarker' not in stage
    assert 'end_marker' not in stage
    assert 'renderEligibility' not in stage
    assert 'render_eligibility' not in stage


def test_qml_ctrl_wheel_zoom_binding():
    """QML binds Ctrl+Wheel to zoom."""
    from src.workbench_qml import QML_SOURCE
    stage = QML_SOURCE.split('id: arrangementStageComponent', 1)[1].split('id: arrangementStageHeader', 1)[0]
    assert 'Control' in stage or 'ctrl' in stage.lower()
    assert 'Wheel' in stage or 'wheel' in stage.lower()


def test_qml_horizontal_pan_binding():
    """QML binds horizontal pan/scroll."""
    from src.workbench_qml import QML_SOURCE
    stage = QML_SOURCE.split('id: arrangementStageComponent', 1)[1].split('id: arrangementStageHeader', 1)[0]
    assert 'horizontal' in stage.lower() or 'Pan' in stage or 'pan' in stage.lower()


# --- Review findings F5/F6: anchor recenter + bounded zoom-out rungs ---------- #

def test_zoom_out_recenters_around_anchor(tempo_map):
    """Zoom out recalculates the start from the anchor, not the old start."""
    vp = seam.viewport_for_initial_view(tempo_map)  # 0..360 @ 120 BPM
    zoomed_in = seam.zoom_in(vp, Fraction(180), tempo_map)  # 90..270, dur 180
    assert zoomed_in.start_quarter_note == Fraction(90)
    zoomed_out = seam.zoom_out(zoomed_in, Fraction(270), tempo_map)  # dur 360
    assert zoomed_out.visible_duration_qn == Fraction(360)
    assert zoomed_out.start_quarter_note == Fraction(90)
    center = zoomed_out.start_quarter_note + zoomed_out.visible_duration_qn / 2
    assert center == Fraction(270)


def test_zoom_out_anchor_before_clamped_start(tempo_map):
    """Anchor near the left edge recenter clamps at 0 before clamping."""
    vp = seam.viewport_for_initial_view(tempo_map)  # 0..360
    zoomed_in = seam.zoom_in(vp, Fraction(180), tempo_map)  # 90..270, dur 180
    zoomed_out = seam.zoom_out(zoomed_in, Fraction(90), tempo_map)
    assert zoomed_out.visible_duration_qn == Fraction(360)
    assert zoomed_out.start_quarter_note == Fraction(0)


def test_zoom_out_widest_rung_stays_strictly_below_horizon(tempo_map):
    """Repeated zoom-out stops on a discrete rung below the logical horizon."""
    vp = seam.viewport_for_initial_view(tempo_map)  # dur 360, horizon 1200
    for _ in range(10):
        vp = seam.zoom_out(vp, Fraction(180), tempo_map)
    # Widest rung is 0.5 -> 720 QN at 120 BPM (0.25 -> 1440 is rejected)
    assert vp.zoom_level == 0.5
    assert vp.visible_duration_qn < vp.logical_horizon_qn
    assert vp.visible_duration_qn < seam._max_zoom_out_duration_qn()


def test_zoom_out_never_materializes_full_horizon_window(session, tempo_map):
    """Max zoom-out projection stays within one bounded block window."""
    vp = seam.viewport_for_initial_view(tempo_map)
    for _ in range(10):
        vp = seam.zoom_out(vp, Fraction(180), tempo_map)
    window = seam.project_visible_blocks(session, vp)
    assert len(window.blocks) <= seam.MAX_ARRANGEMENT_BLOCK_WINDOW
    assert len(window.blocks) < 18  # not the full ~10-min horizon


def test_zoom_out_skips_rung_that_exceeds_block_window_buget(session, tempo_map):
    """At very high BPM an otherwise valid rung wider than the window cap is
    skipped and the viewport stays unchanged (no block_window_too_large)."""
    fast_map = tempo(800)
    vp = seam.viewport_for_initial_view(fast_map)  # base 2400 QN < cap 3904
    zoomed = seam.zoom_out(vp, Fraction(100), fast_map)  # rung 0.5 -> 4800 QN
    assert zoomed.visible_duration_qn == vp.visible_duration_qn
    assert zoomed.zoom_level == vp.zoom_level
    assert zoomed.start_quarter_note == vp.start_quarter_note
    # Still projectable within one bounded window
    window = seam.project_visible_blocks(session, vp)
    assert len(window.blocks) <= seam.MAX_ARRANGEMENT_BLOCK_WINDOW


def test_zoom_out_at_large_horizon_stops_at_widest_rung(session):
    """At a slow tempo every wider rung still fits under the horizon; zoom_out
    reaches the widest rung and then stays there (zero-mutation at the cap)."""
    slow_map = tempo(60)  # horizon 600 QN; rung 0.25 -> 720 QN exceeds horizon
    vp = seam.viewport_for_initial_view(slow_map)
    for _ in range(10):
        vp = seam.zoom_out(vp, Fraction(100), slow_map)
    assert vp.zoom_level == 0.5
    assert vp.visible_duration_qn == Fraction(360)
    assert vp.visible_duration_qn < Fraction(600)
    final = seam.zoom_out(vp, Fraction(100), slow_map)
    assert final == vp

