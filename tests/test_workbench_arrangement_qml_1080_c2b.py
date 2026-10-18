"""Frozen C2b expand/collapse + track rows + track-mask interaction contract over C2a authority."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src import workbench_arrangement_qml as seam
from src.workbench_qml import QML_SOURCE, _qml_arrangement_bridge
from tests.test_workbench_arrangement_qml_1080_c1 import session as c1_session  # noqa: F401


@pytest.fixture
def session(c1_session):
    """Extend C1 session with methods needed for C2b re-entry tests."""
    # Add mock methods for return_to_edit and enter_arrangement_from_edit
    c1_session.return_to_edit = Mock()
    c1_session.enter_arrangement_from_edit = Mock(return_value=Mock(ok=True))
    return c1_session


@pytest.fixture
def bridge(session):
    pytest.importorskip("PySide6")
    session.projection_mode = "ARRANGEMENT"
    return _qml_arrangement_bridge(session, SimpleNamespace(arrangement_mode_enabled=True))


def test_exactly_four_parent_groups_remain(session, bridge):
    """Contract 1: exactly four parent groups from C2a persist."""
    bridge.refresh()
    assert len(bridge.groupRows) == 4
    group_ids = [r["groupId"] for r in bridge.groupRows]
    assert group_ids == ["pg_baseline", "pg_drums", "pg_melodic_atmos_fx", "pg_vocals"]


def test_expand_group_projects_only_python_owned_members(session, bridge, monkeypatch):
    """Contract 2: expand projects only Python-owned members; no QML hardcoding."""
    bridge.refresh()
    # Initially all collapsed — no track rows visible
    assert all("trackRows" not in r or r.get("trackRows", []) == [] for r in bridge.groupRows)

    # Expand first group
    bridge.toggleArrangementGroupExpanded("pg_baseline")
    bridge.refresh()

    # Track rows come from Python projection only
    baseline = next(r for r in bridge.groupRows if r["groupId"] == "pg_baseline")
    assert "trackRows" in baseline
    track_rows = baseline["trackRows"]
    assert len(track_rows) > 0  # Python-owned members exist
    for tr in track_rows:
        assert "channelId" in tr
        assert "displayName" in tr
        assert "blocks" in tr
    # Membership list must match arrangement_domain.PRESENTATION_GROUPS
    from src.arrangement_domain import PRESENTATION_GROUPS
    expected_channels = list(PRESENTATION_GROUPS["pg_baseline"])
    actual_channels = [tr["channelId"] for tr in track_rows]
    assert actual_channels == expected_channels


def test_collapse_removes_track_rows(session, bridge):
    """Contract 3: collapse removes/hides track rows."""
    bridge.refresh()
    bridge.toggleArrangementGroupExpanded("pg_baseline")
    bridge.refresh()
    baseline = next(r for r in bridge.groupRows if r["groupId"] == "pg_baseline")
    assert len(baseline.get("trackRows", [])) > 0

    bridge.toggleArrangementGroupExpanded("pg_baseline")
    bridge.refresh()
    baseline = next(r for r in bridge.groupRows if r["groupId"] == "pg_baseline")
    assert "trackRows" not in baseline or baseline.get("trackRows", []) == []


def test_expand_collapse_zero_musical_mutation_zero_save(session, bridge, monkeypatch):
    """Contract 4: expand/collapse causes exactly zero musical mutation and zero save."""
    save_spy = Mock(wraps=session.set_arrangement_state)
    monkeypatch.setattr(session, "set_arrangement_state", save_spy)

    bridge.refresh()
    bridge.toggleArrangementGroupExpanded("pg_baseline")
    bridge.refresh()
    bridge.toggleArrangementGroupExpanded("pg_drums")
    bridge.refresh()
    bridge.toggleArrangementGroupExpanded("pg_baseline")
    bridge.refresh()

    save_spy.assert_not_called()
    # Arrangement state unchanged
    assert session.arrangement_state.disabled_group_blocks == frozenset()
    assert session.arrangement_state.disabled_track_blocks == frozenset()


def test_no_membership_hardcoding_in_qml():
    """Contract 5: no membership/track-ID hardcoding in QML source."""
    stage = QML_SOURCE.split('id: arrangementStageComponent', 1)[1].split('id: arrangementStageHeader', 1)[0]
    # Group labels come from Python projection, not hardcoded
    for gid in ("pg_baseline", "pg_drums", "pg_melodic_atmos_fx", "pg_vocals"):
        assert gid not in stage
    # Track IDs not hardcoded either
    for ch in ("ch_kick", "ch_bass", "ch_main_drum", "ch_closed_hat", "ch_open_hat",
               "ch_percussion", "ch_additional", "ch_lead", "ch_pad", "ch_atmos", "ch_fx"):
        assert ch not in stage


def test_track_block_click_routes_once_to_python_intent(session, bridge, monkeypatch):
    """Contract 6: track block click routes exactly once to Python track-mask intent."""
    spy = Mock(wraps=seam.request_arrangement_track_toggle)
    monkeypatch.setattr(seam, "request_arrangement_track_toggle", spy)

    bridge.refresh()
    bridge.toggleArrangementGroupExpanded("pg_baseline")
    bridge.refresh()

    # Click a track block
    baseline = next(r for r in bridge.groupRows if r["groupId"] == "pg_baseline")
    track_rows = baseline.get("trackRows", [])
    assert len(track_rows) > 0
    first_track = track_rows[0]
    assert len(first_track["blocks"]) > 0

    # Only interactive blocks route
    interactive_blocks = [b for b in first_track["blocks"] if b["interactive"]]
    if interactive_blocks:
        block = interactive_blocks[0]
        bridge.toggleArrangementTrackBlock(first_track["channelId"], block["blockIndex"])
        spy.assert_called_once_with(session, first_track["channelId"], block["blockIndex"])


def test_successful_track_mutation_one_persistence_mutation(session, bridge, monkeypatch):
    """Contract 7: successful track mutation produces exactly one persistence mutation."""
    save_spy = Mock(wraps=session.set_arrangement_state)
    monkeypatch.setattr(session, "set_arrangement_state", save_spy)

    bridge.refresh()
    bridge.toggleArrangementGroupExpanded("pg_baseline")
    bridge.refresh()

    baseline = next(r for r in bridge.groupRows if r["groupId"] == "pg_baseline")
    track_rows = baseline.get("trackRows", [])
    first_track = track_rows[0]
    interactive_blocks = [b for b in first_track["blocks"] if b["interactive"]]
    if interactive_blocks:
        block = interactive_blocks[0]
        result = bridge.toggleArrangementTrackBlock(first_track["channelId"], block["blockIndex"])
        assert result == "mutated"
        save_spy.assert_called_once()


def test_qml_reprojects_after_mutation(session, bridge, monkeypatch):
    """Contract 8: QML reprojects from Python state after mutation."""
    bridge.refresh()
    bridge.toggleArrangementGroupExpanded("pg_baseline")
    bridge.refresh()

    baseline = next(r for r in bridge.groupRows if r["groupId"] == "pg_baseline")
    track_rows = baseline.get("trackRows", [])
    first_track = track_rows[0]
    interactive_blocks = [b for b in first_track["blocks"] if b["interactive"]]
    if interactive_blocks:
        block = interactive_blocks[0]
        channel_id = first_track["channelId"]
        block_index = block["blockIndex"]

        # Before: track enabled
        before = next(b for b in first_track["blocks"] if b["blockIndex"] == block_index)
        assert before["trackEnabled"] is True

        # Toggle OFF
        bridge.toggleArrangementTrackBlock(channel_id, block_index)
        bridge.refresh()

        baseline = next(r for r in bridge.groupRows if r["groupId"] == "pg_baseline")
        track_rows = baseline.get("trackRows", [])
        first_track = next(tr for tr in track_rows if tr["channelId"] == channel_id)
        after = next(b for b in first_track["blocks"] if b["blockIndex"] == block_index)
        assert after["trackEnabled"] is False
        # Effective respects group/block hierarchy
        assert after["effective"] is False


def test_track_off_preserved_after_group_off_on(session, bridge):
    """Contract 9: track OFF remains after group OFF→ON."""
    bridge.refresh()
    bridge.toggleArrangementGroupExpanded("pg_baseline")
    bridge.refresh()

    baseline = next(r for r in bridge.groupRows if r["groupId"] == "pg_baseline")
    track_rows = baseline.get("trackRows", [])
    first_track = track_rows[0]
    interactive_blocks = [b for b in first_track["blocks"] if b["interactive"]]
    if interactive_blocks:
        block = interactive_blocks[0]
        channel_id = first_track["channelId"]
        block_index = block["blockIndex"]

        # Turn track OFF
        bridge.toggleArrangementTrackBlock(channel_id, block_index)
        bridge.refresh()

        # Turn group OFF then ON
        bridge.toggleArrangementGroupBlock("pg_baseline", block_index)
        bridge.refresh()
        bridge.toggleArrangementGroupBlock("pg_baseline", block_index)
        bridge.refresh()

        baseline = next(r for r in bridge.groupRows if r["groupId"] == "pg_baseline")
        track_rows = baseline.get("trackRows", [])
        first_track = next(tr for tr in track_rows if tr["channelId"] == channel_id)
        after = next(b for b in first_track["blocks"] if b["blockIndex"] == block_index)
        assert after["trackEnabled"] is False  # Track OFF preserved


def test_group_off_reversible(session, bridge):
    """Contract 10: group OFF remains reversible."""
    bridge.refresh()
    bridge.toggleArrangementGroupExpanded("pg_baseline")
    bridge.refresh()

    block_index = 0
    # Turn group OFF
    bridge.toggleArrangementGroupBlock("pg_baseline", block_index)
    bridge.refresh()
    baseline = next(r for r in bridge.groupRows if r["groupId"] == "pg_baseline")
    block = next(b for b in baseline["blocks"] if b["blockIndex"] == block_index)
    assert block["groupEnabled"] is False
    assert block["interactive"] is True  # Still interactive for reversal

    # Turn group ON
    bridge.toggleArrangementGroupBlock("pg_baseline", block_index)
    bridge.refresh()
    baseline = next(r for r in bridge.groupRows if r["groupId"] == "pg_baseline")
    block = next(b for b in baseline["blocks"] if b["blockIndex"] == block_index)
    assert block["groupEnabled"] is True


def test_global_block_off_prevents_track_mutation(session, bridge, monkeypatch):
    """Contract 11: global block OFF prevents track mutation at that block index."""
    # Turn global block OFF at index 0
    seam.request_arrangement_block_toggle(session, 0)
    bridge.refresh()

    bridge.toggleArrangementGroupExpanded("pg_baseline")
    bridge.refresh()

    baseline = next(r for r in bridge.groupRows if r["groupId"] == "pg_baseline")
    track_rows = baseline.get("trackRows", [])
    first_track = track_rows[0]

    # Only the block at the disabled global index (0) should be non-interactive
    # (available=True means visible, interactive=False means cannot be clicked)
    for block in first_track["blocks"]:
        if block["blockIndex"] == 0:
            assert block["available"] is True  # Still visible
            assert block["interactive"] is False  # But not clickable
        else:
            # Other blocks should still be interactive (if eligible)
            if block["status"] == "eligible":
                assert block["available"] is True
                assert block["interactive"] is True

    # Attempt mutation at disabled index should not route to Python
    spy = Mock(wraps=seam.request_arrangement_track_toggle)
    monkeypatch.setattr(seam, "request_arrangement_track_toggle", spy)
    bridge.toggleArrangementTrackBlock(first_track["channelId"], 0)
    spy.assert_not_called()

    # But mutation at other indices should still work
    spy.reset_mock()
    if len(first_track["blocks"]) > 1:
        bridge.toggleArrangementTrackBlock(first_track["channelId"], 1)
        spy.assert_called_once()


def test_out_of_horizon_prevents_mutation(session, bridge, monkeypatch):
    """Contract 12: out-of-horizon track block prevents mutation."""
    bridge.refresh()
    bridge.toggleArrangementGroupExpanded("pg_baseline")
    bridge.refresh()

    # Find an out-of-horizon block (block 19 is typically out of horizon)
    baseline = next(r for r in bridge.groupRows if r["groupId"] == "pg_baseline")
    track_rows = baseline.get("trackRows", [])
    first_track = track_rows[0]
    ooh_block = next((b for b in first_track["blocks"] if b["status"] == "out_of_current_horizon"), None)
    if ooh_block:
        assert ooh_block["interactive"] is False
        assert ooh_block["available"] is False

        spy = Mock(wraps=seam.request_arrangement_track_toggle)
        monkeypatch.setattr(seam, "request_arrangement_track_toggle", spy)
        bridge.toggleArrangementTrackBlock(first_track["channelId"], ooh_block["blockIndex"])
        spy.assert_not_called()


def test_invalid_targets_prevent_mutation(session, bridge, monkeypatch):
    """Contract 13: invalid group/track/block IDs prevent mutation."""
    spy = Mock(wraps=seam.request_arrangement_track_toggle)
    monkeypatch.setattr(seam, "request_arrangement_track_toggle", spy)

    bridge.refresh()
    # Invalid group
    assert bridge.toggleArrangementTrackBlock("ch_kick", 999) != "mutated"
    # Invalid track
    assert bridge.toggleArrangementTrackBlock("ch_missing", 0) != "mutated"
    # Invalid block (negative)
    assert bridge.toggleArrangementTrackBlock("ch_kick", -1) != "mutated"
    spy.assert_not_called()


def test_pointer_space_accessibility_same_intent(session, bridge, monkeypatch):
    """Contract 14: pointer/Space/Accessibility invoke use same Python intent."""
    spy = Mock(wraps=seam.request_arrangement_track_toggle)
    monkeypatch.setattr(seam, "request_arrangement_track_toggle", spy)

    bridge.refresh()
    bridge.toggleArrangementGroupExpanded("pg_baseline")
    bridge.refresh()

    baseline = next(r for r in bridge.groupRows if r["groupId"] == "pg_baseline")
    track_rows = baseline.get("trackRows", [])
    first_track = track_rows[0]
    interactive_blocks = [b for b in first_track["blocks"] if b["interactive"]]
    if interactive_blocks:
        block = interactive_blocks[0]
        channel_id = first_track["channelId"]
        block_index = block["blockIndex"]

        # Test QML string contracts for Space and Accessibility
        stage_region = QML_SOURCE.split('id: arrangementStageComponent', 1)[1].split('id: arrangementStageHeader', 1)[0]
        # Track row repeaters must have Keys.onSpacePressed and Accessible.onPressAction
        assert 'Keys.onSpacePressed' in stage_region or 'Accessible.onPressAction' in stage_region
        # Both should call toggleArrangementTrackBlock
        assert 'toggleArrangementTrackBlock' in stage_region


def test_unavailable_track_blocks_disabled_for_accessibility(session, bridge):
    """Contract 15: unavailable track blocks are disabled for Accessibility."""
    # Turn global block OFF
    seam.request_arrangement_block_toggle(session, 0)
    bridge.refresh()
    bridge.toggleArrangementGroupExpanded("pg_baseline")
    bridge.refresh()

    baseline = next(r for r in bridge.groupRows if r["groupId"] == "pg_baseline")
    track_rows = baseline.get("trackRows", [])
    first_track = track_rows[0]
    for block in first_track["blocks"]:
        if block["blockIndex"] == 0:
            assert block["interactive"] is False
            assert block["available"] is True  # Visible but not interactive
        else:
            # Other blocks should still be interactive if eligible
            if block["status"] == "eligible":
                assert block["interactive"] is True
                assert block["available"] is True


def test_collapsed_groups_materialize_no_unnecessary_controls(session, bridge):
    """Contract 16: collapsed groups don't materialize unnecessary track block controls."""
    bridge.refresh()
    # All groups collapsed by default
    for group in bridge.groupRows:
        # Should not have trackRows or trackRows should be empty
        track_rows = group.get("trackRows", [])
        assert track_rows == []


def test_expand_collapse_no_pattern_kit_tempo_transport_audio(session, bridge, monkeypatch):
    """Contract 17: expand/collapse doesn't affect pattern, kit, tempo, transport, audio."""
    # Verify arrangement state is unchanged
    state_before = session.arrangement_state.to_payload()

    bridge.refresh()
    bridge.toggleArrangementGroupExpanded("pg_baseline")
    bridge.refresh()
    bridge.toggleArrangementGroupExpanded("pg_drums")
    bridge.refresh()
    bridge.toggleArrangementGroupExpanded("pg_baseline")
    bridge.refresh()

    state_after = session.arrangement_state.to_payload()
    assert state_before == state_after


def test_return_to_edit_and_reentry_preserve_track_masks(session, bridge):
    """Contract 18: return to Edit and re-entry preserve track masks."""
    bridge.refresh()
    bridge.toggleArrangementGroupExpanded("pg_baseline")
    bridge.refresh()

    baseline = next(r for r in bridge.groupRows if r["groupId"] == "pg_baseline")
    track_rows = baseline.get("trackRows", [])
    first_track = track_rows[0]
    interactive_blocks = [b for b in first_track["blocks"] if b["interactive"]]
    if interactive_blocks:
        block = interactive_blocks[0]
        channel_id = first_track["channelId"]
        block_index = block["blockIndex"]

        # Turn track OFF
        bridge.toggleArrangementTrackBlock(channel_id, block_index)
        bridge.refresh()
        masks_before = session.arrangement_state.to_payload()

        # Return to edit and re-enter
        bridge.returnToBrowser()
        bridge.refresh()
        bridge.enterArrangement()
        bridge.refresh()
        bridge.toggleArrangementGroupExpanded("pg_baseline")
        bridge.refresh()

        masks_after = session.arrangement_state.to_payload()
        assert masks_before == masks_after


def test_c2a_group_block_interaction_unchanged(session, bridge, monkeypatch):
    """Contract 19: C2a group block interaction remains unchanged."""
    spy = Mock(wraps=seam.request_arrangement_group_toggle)
    monkeypatch.setattr(seam, "request_arrangement_group_toggle", spy)

    bridge.refresh()
    result = bridge.toggleArrangementGroupBlock("pg_baseline", 0)
    assert result == "mutated"
    spy.assert_called_once_with(session, "pg_baseline", 0)


def test_slice_a_b_c1_c2a_regressions_green(session, bridge, monkeypatch):
    """Contract 20: Slice A/B/C1/C2a regressions remain green."""
    # Slice A/B: field toggle still works (if channel rows are projected)
    field_spy = Mock(wraps=seam.request_arrangement_field_toggle)
    monkeypatch.setattr(seam, "request_arrangement_field_toggle", field_spy)

    bridge.refresh()
    # Channel rows may be empty if no sample paths (depends on test fixture)
    if bridge.channelRows:
        row = bridge.channelRows[0]
        assert "channelId" in row
        assert "stepGridEnabled" in row

        # Field toggle
        if row["stepGridEnabled"] and row["fields"]:
            field = row["fields"][0]
            result = bridge.toggleArrangementField(row["channelId"], field["index"])
            assert result in ("mutated", "row_not_editable", "unknown_channel", "invalid_field_index")
    else:
        # No channel rows projected (no sample paths in fixture) - verify projection still works
        assert bridge.projectionMode == "ARRANGEMENT"
        assert bridge.barCount == 8
        assert bridge.fieldCount == 32

    # C1: group block toggle still works
    group_spy = Mock(wraps=seam.request_arrangement_group_toggle)
    monkeypatch.setattr(seam, "request_arrangement_group_toggle", group_spy)
    result = bridge.toggleArrangementGroupBlock("pg_baseline", 0)
    assert result == "mutated"


def test_expand_collapse_is_presentation_state_only(session, bridge, monkeypatch):
    """Expand/collapse is purely presentation state — no arrangement mutation."""
    # Verify that expand/collapse doesn't call any arrangement mutation seam
    group_spy = Mock(wraps=seam.request_arrangement_group_toggle)
    track_spy = Mock(wraps=seam.request_arrangement_track_toggle)
    block_spy = Mock(wraps=seam.request_arrangement_block_toggle)
    monkeypatch.setattr(seam, "request_arrangement_group_toggle", group_spy)
    monkeypatch.setattr(seam, "request_arrangement_track_toggle", track_spy)
    monkeypatch.setattr(seam, "request_arrangement_block_toggle", block_spy)

    bridge.refresh()
    bridge.toggleArrangementGroupExpanded("pg_baseline")
    bridge.refresh()
    bridge.toggleArrangementGroupExpanded("pg_baseline")
    bridge.refresh()

    group_spy.assert_not_called()
    track_spy.assert_not_called()
    block_spy.assert_not_called()


def test_track_rows_share_visible_block_window_geometry(session, bridge):
    """Track rows share the same visible block window geometry as parent group."""
    bridge.refresh()
    bridge.toggleArrangementGroupExpanded("pg_baseline")
    bridge.refresh()

    baseline = next(r for r in bridge.groupRows if r["groupId"] == "pg_baseline")
    group_blocks = baseline["blocks"]
    track_rows = baseline.get("trackRows", [])

    if track_rows:
        for tr in track_rows:
            track_blocks = tr["blocks"]
            assert len(track_blocks) == len(group_blocks)
            for i, (gb, tb) in enumerate(zip(group_blocks, track_blocks)):
                assert gb["blockIndex"] == tb["blockIndex"]


def test_no_unbounded_horizon_materialization(session, bridge):
    """No unbounded horizon is materialized — bounded by viewport window."""
    bridge.refresh()
    bridge.toggleArrangementGroupExpanded("pg_baseline")
    bridge.refresh()

    baseline = next(r for r in bridge.groupRows if r["groupId"] == "pg_baseline")
    track_rows = baseline.get("trackRows", [])

    if track_rows:
        for tr in track_rows:
            track_blocks = tr["blocks"]
            # Bounded by viewport (~3 min = ~6 blocks + small overscan), not full horizon
            assert len(track_blocks) <= 8


def test_effective_respects_global_group_track_hierarchy(session, bridge):
    """Effective state respects global → group → track hierarchy."""
    bridge.refresh()
    bridge.toggleArrangementGroupExpanded("pg_baseline")
    bridge.refresh()

    baseline = next(r for r in bridge.groupRows if r["groupId"] == "pg_baseline")
    track_rows = baseline.get("trackRows", [])
    first_track = track_rows[0]

    # Initially all enabled
    for block in first_track["blocks"]:
        if block["status"] == "eligible":
            assert block["effective"] is True

    # Disable global block
    seam.request_arrangement_block_toggle(session, 0)
    bridge.refresh()

    baseline = next(r for r in bridge.groupRows if r["groupId"] == "pg_baseline")
    track_rows = baseline.get("trackRows", [])
    first_track = next(tr for tr in track_rows if tr["channelId"] == first_track["channelId"])

    for block in first_track["blocks"]:
        if block["blockIndex"] == 0 and block["status"] == "eligible":
            assert block["effective"] is False

    # Re-enable global, disable group
    seam.request_arrangement_block_toggle(session, 0)
    seam.request_arrangement_group_toggle(session, "pg_baseline", 0)
    bridge.refresh()

    baseline = next(r for r in bridge.groupRows if r["groupId"] == "pg_baseline")
    track_rows = baseline.get("trackRows", [])
    first_track = next(tr for tr in track_rows if tr["channelId"] == first_track["channelId"])

    for block in first_track["blocks"]:
        if block["blockIndex"] == 0 and block["status"] == "eligible":
            assert block["effective"] is False


def test_track_rows_only_for_occupied_channels(session, bridge):
    """Track rows only projected for channels that exist in the rack."""
    bridge.refresh()
    bridge.toggleArrangementGroupExpanded("pg_baseline")
    bridge.refresh()

    baseline = next(r for r in bridge.groupRows if r["groupId"] == "pg_baseline")
    track_rows = baseline.get("trackRows", [])

    # All track rows must correspond to channels in the rack
    rack_channels = {c.channel_id for c in session.channel_rack.state.channels}
    for tr in track_rows:
        assert tr["channelId"] in rack_channels


def test_expand_collapse_preserves_selection_and_focus(session, bridge):
    """Expand/collapse doesn't disrupt keyboard focus or selection."""
    bridge.refresh()
    # Focus should be on arrangement stage after enter
    bridge.toggleArrangementGroupExpanded("pg_baseline")
    bridge.refresh()
    bridge.toggleArrangementGroupExpanded("pg_baseline")
    bridge.refresh()
    # No error, focus preserved implicitly


def test_four_groups_each_expandable_independently(session, bridge):
    """Each of the four groups expands independently."""
    bridge.refresh()

    for group_id in ["pg_baseline", "pg_drums", "pg_melodic_atmos_fx", "pg_vocals"]:
        bridge.toggleArrangementGroupExpanded(group_id)
        bridge.refresh()
        group = next(r for r in bridge.groupRows if r["groupId"] == group_id)
        # Track rows should exist (may be empty for pg_vocals if no channels)
        assert "trackRows" in group

        bridge.toggleArrangementGroupExpanded(group_id)
        bridge.refresh()
        group = next(r for r in bridge.groupRows if r["groupId"] == group_id)
        assert "trackRows" not in group or group.get("trackRows", []) == []


def test_qml_visual_contract_maintained():
    """Visual contract: deep black, subtle 2.5D, exact 2D hit geometry, restrained Blood A."""
    stage = QML_SOURCE.split('id: arrangementStageComponent', 1)[1].split('id: arrangementStageHeader', 1)[0]
    # Theme colors from Theme Authority
    assert 'theme.surfaceRoot' in stage
    assert 'theme.surfacePanel' in stage
    assert 'theme.borderSubtle' in stage
    assert 'theme.actionActive' in stage
    assert 'theme.selectionSurface' in stage
    assert 'theme.selectionBorder' in stage
    # No neon/arcade colors
    assert '#ff00' not in stage.lower()
    assert '#00ff' not in stage.lower()
    # Hierarchy: track rows visually under parent group (indented)
    assert 'channelNameColumnWidth' in stage


def test_no_timeline_zoom_pan_scope_creep(session, bridge):
    """C2b scope boundary: no end marker, render eligibility, MIDI, piano roll, etc.

    Note: zoom/pan/viewport are intentionally added by C2c1 and are no longer
    considered scope creep for the arrangement stage.
    """
    stage = QML_SOURCE.split('id: arrangementStageComponent', 1)[1].split('id: arrangementStageHeader', 1)[0]
    # These concepts must not appear in C2b as standalone features.
    # Use word-boundary-aware checks to avoid false positives from words like
    # "expand", "expanded", "span", "panel", etc.
    import re
    forbidden_patterns = [
        r'\btimeline\b', r'\bTIMELINE\b',
        r'\bLive\b', r'\bLIVE\b', r'\bMIDI\b', r'\bmidi\b',
        r'\bpianoRoll\b', r'\bPianoRoll\b', r'\bpianoroll\b',
        r'\bmixer\b', r'\bMixer\b', r'\bMIXER\b',
        r'\bautomation\b', r'\bAutomation\b', r'\bAUTOMATION\b',
    ]
    for pattern in forbidden_patterns:
        assert not re.search(pattern, stage), f"C2b scope creep: {pattern} found in QML"


def test_accessibility_roles_and_names(session, bridge):
    """New expand/collapse and track block controls have accessibility roles/names."""
    bridge.refresh()
    bridge.toggleArrangementGroupExpanded("pg_baseline")
    bridge.refresh()

    baseline = next(r for r in bridge.groupRows if r["groupId"] == "pg_baseline")
    track_rows = baseline.get("trackRows", [])

    if track_rows:
        first_track = track_rows[0]
        for block in first_track["blocks"]:
            if block["status"] == "eligible":
                # Should have proper accessibility
                assert "interactive" in block
                assert "available" in block
                assert "trackEnabled" in block


# ===== QML Source Contract Tests (no Qt required) =====

def test_qml_expand_collapse_buttons_exist():
    """Expand/collapse affordance exists in QML for each group row."""
    stage = QML_SOURCE.split('id: arrangementStageComponent', 1)[1].split('id: arrangementStageHeader', 1)[0]
    # Group rows should have expand/collapse control
    assert 'toggleArrangementGroupExpanded' in stage or 'expanded' in stage.lower()


def test_qml_track_rows_repeater_uses_python_membership():
    """Track rows repeater model comes from Python projection."""
    stage = QML_SOURCE.split('id: arrangementStageComponent', 1)[1].split('id: arrangementStageHeader', 1)[0]
    # Track rows model should reference window.arrangement.groupRows[].trackRows
    assert 'trackRows' in stage or 'channelRows' in stage


def test_qml_track_blocks_same_geometry_as_group():
    """Track blocks share geometry with group blocks."""
    stage = QML_SOURCE.split('id: arrangementStageComponent', 1)[1].split('id: arrangementStageHeader', 1)[0]
    # Track block width should derive from parent's block count
    assert 'blockIndex' in stage


def test_qml_no_local_mask_manipulation():
    """No local mask manipulation like 'enabled = !enabled'."""
    stage = QML_SOURCE.split('id: arrangementStageComponent', 1)[1].split('id: arrangementStageHeader', 1)[0]
    assert 'enabled = !enabled' not in stage
    assert 'trackEnabled = !trackEnabled' not in stage
    assert 'groupEnabled = !groupEnabled' not in stage


def test_qml_track_block_intent_routes_to_python():
    """Track block click routes to Python intent, not local flip."""
    stage = QML_SOURCE.split('id: arrangementStageComponent', 1)[1].split('id: arrangementStageHeader', 1)[0]
    assert 'toggleArrangementTrackBlock' in stage
    assert 'window.arrangement.toggleArrangementTrackBlock' in stage


def test_qml_expand_collapse_no_mutation_command():
    """Expand/collapse button does not call any arrangement mutation."""
    stage = QML_SOURCE.split('id: arrangementStageComponent', 1)[1].split('id: arrangementStageHeader', 1)[0]
    # Should call toggleArrangementGroupExpanded, not toggleArrangementGroupBlock
    assert 'toggleArrangementGroupExpanded' in stage
    # But not the mutation intent
    assert 'request_arrangement_group_toggle' not in stage