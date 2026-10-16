"""Frozen #1078 transition contract; synthetic media and real package I/O."""

from dataclasses import replace
from pathlib import Path

import pytest

from src import track_package as tp
from src import workbench_session as ws
from src.arrangement_32_field_time import build_32_field_channel_rack_state
from src.workbench_feature_settings import (
    WorkbenchFeatureSettings,
    load_workbench_feature_settings,
    save_workbench_feature_settings,
)
from src.workbench_session_store import active_track_pointer_path
from tests.audio_fixtures import write_sine_wav
from tests.test_active_track_persistence_1098 import _row, _manifest_payload


@pytest.fixture
def draft(tmp_path):
    session = ws.compose_workbench_session(state_dir=tmp_path / "state")
    source = tmp_path / "kick.wav"
    write_sine_wav(source, duration_sec=0.05, frequency_hz=60)
    session.live_kit.assign("Kick + Bass", "Kick", _row(source))
    session.channel_rack.restore_state(
        build_32_field_channel_rack_state(session.live_kit)
    )
    yield session, tmp_path / "track", source
    session.transport.close()


def enable(session):
    settings = replace(WorkbenchFeatureSettings(), arrangement_mode_enabled=True)
    assert save_workbench_feature_settings(settings, state_dir=session._state_dir)


def enter(session, destination=None):
    return session.enter_arrangement_from_edit(package_root=destination)


def test_gate_off_rejects_without_package_domain_or_mode_mutation(draft):
    s, root, _ = draft
    before = s.channel_rack.state
    result = enter(s, root)
    assert result.outcome == "feature_disabled"
    assert not result.ok
    assert s.projection_mode == "EDIT"
    assert s.active_track_id is None
    assert s.arrangement_state is None
    assert s.channel_rack.state is before
    assert not root.exists()


def test_settings_gate_defaults_off_and_roundtrips(draft):
    s, _, _ = draft
    assert (
        load_workbench_feature_settings(state_dir=s._state_dir).arrangement_mode_enabled
        is False
    )
    enable(s)
    assert (
        load_workbench_feature_settings(state_dir=s._state_dir).arrangement_mode_enabled
        is True
    )


def test_package_created_only_on_explicit_entry_with_partial_kit(draft):
    s, root, _ = draft
    enable(s)
    owners = (s.live_kit, s.channel_rack, s.transport, s.audition)
    assert s.active_track_id is None
    assert not root.exists()
    pattern = s.channel_rack.state.pattern
    result = enter(s, root)
    assert result.ok
    assert s.projection_mode == "ARRANGEMENT"
    assert s.active_track_id == result.track_id
    assert s.active_track_package_root == root
    assert s.arrangement_state.pattern_id == pattern.pattern_id
    assert s.channel_rack.state.pattern == pattern
    assert owners == (s.live_kit, s.channel_rack, s.transport, s.audition)
    assert _manifest_payload(root)["arrangement"] == s.arrangement_state.to_payload()
    assert active_track_pointer_path(state_dir=s._state_dir).is_file()


def test_create_failure_preserves_exact_draft_and_allows_retry(draft):
    s, root, _ = draft
    enable(s)
    root.write_text("occupied", encoding="utf-8")
    rack = s.channel_rack.state
    assignment = s.live_kit.assignment_for("Kick + Bass", "Kick")
    failed = enter(s, root)
    assert not failed.ok and failed.message
    assert s.projection_mode == "EDIT"
    assert s.active_track_id is None and s.active_track_package_root is None
    assert s.channel_rack.state is rack
    assert s.live_kit.assignment_for("Kick + Bass", "Kick") is assignment
    assert s.arrangement_state is None
    assert enter(s, root.with_name("retry")).ok


def test_repeated_entry_and_cycles_preserve_track_and_owners(draft):
    s, root, _ = draft
    enable(s)
    assert enter(s, root).ok
    track_id = s.active_track_id
    rack = s.channel_rack.state
    pattern = rack.pattern
    owners = (s.live_kit, s.channel_rack, s.transport, s.audition)
    for _ in range(5):
        assert enter(s).ok
        s.return_to_edit()
        assert s.projection_mode == "EDIT"
        assert s.active_track_id == track_id
        assert s.arrangement_state is not None
        assert s.channel_rack.state is rack
        assert s.channel_rack.state.pattern is pattern
        assert enter(s, root.with_name("must-not-exist")).ok
    assert not root.with_name("must-not-exist").exists()
    assert owners == (s.live_kit, s.channel_rack, s.transport, s.audition)


def test_return_and_reentry_preserve_arrangement_masks(draft):
    s, root, _ = draft
    enable(s)
    assert enter(s, root).ok
    state = replace(s.arrangement_state, disabled_blocks=frozenset({2}))
    s.set_arrangement_state(state)
    before = (root / tp.TRACK_PACKAGE_FILENAME).read_bytes()
    s.return_to_edit()
    assert s.projection_mode == "EDIT"
    assert s.arrangement_state == state
    assert (root / tp.TRACK_PACKAGE_FILENAME).read_bytes() == before
    assert enter(s).ok
    assert s.arrangement_state == state


def test_edit_replacement_persists_same_package_and_is_seen_on_reentry(draft, tmp_path):
    s, root, _ = draft
    enable(s)
    assert enter(s, root).ok
    identity = s.active_track_id
    s.return_to_edit()
    replacement = tmp_path / "replacement.wav"
    write_sine_wav(replacement, duration_sec=0.05, frequency_hz=90)
    s.live_kit.assign("Kick + Bass", "Kick", _row(replacement))
    assert enter(s).ok
    assert s.active_track_id == identity
    assigned = Path(s.live_kit.assignment_for("Kick + Bass", "Kick").path)
    assert assigned.is_relative_to(root)
    assert assigned.read_bytes() == replacement.read_bytes()
    assert s.channel_rack.state.channels[0].sample_path == str(assigned)
    assert _manifest_payload(root)["track_id"] == identity


@pytest.mark.parametrize("payload", [{"future": "opaque"}, {"schema_version": 999}, []])
def test_opaque_arrangement_fails_closed_without_overwrite(draft, payload):
    s, root, _ = draft
    enable(s)
    assert enter(s, root).ok
    s.return_to_edit()
    s._arrangement_payload = payload
    before = (root / tp.TRACK_PACKAGE_FILENAME).read_bytes()
    result = enter(s)
    assert not result.ok and result.message
    assert s.projection_mode == "EDIT"
    assert s._arrangement_payload is payload
    assert (root / tp.TRACK_PACKAGE_FILENAME).read_bytes() == before


def test_save_failure_never_claims_success(draft, monkeypatch):
    s, root, _ = draft
    enable(s)
    assert enter(s, root).ok
    s.return_to_edit()
    before = (root / tp.TRACK_PACKAGE_FILENAME).read_bytes()

    def fail(*args, **kwargs):
        return tp.TrackPackageResult(
            tp.OUTCOME_WRITE_FAILED, message="synthetic write failure"
        )

    monkeypatch.setattr(ws, "save_track_package_musical_state", fail)
    result = enter(s)
    assert not result.ok and result.outcome == tp.OUTCOME_WRITE_FAILED
    assert s.projection_mode == "EDIT"
    assert s.track_package_dirty
    assert (root / tp.TRACK_PACKAGE_FILENAME).read_bytes() == before


def test_pointer_write_failure_preserves_draft_without_half_active_track(
    draft, monkeypatch
):
    s, root, _ = draft
    enable(s)
    rack = s.channel_rack.state
    assignment = s.live_kit.assignment_for("Kick + Bass", "Kick")

    def fail(*args, **kwargs):
        raise OSError("synthetic pointer write failure")

    monkeypatch.setattr(ws, "save_active_track_pointer", fail)
    result = enter(s, root)
    assert not result.ok and result.outcome == tp.OUTCOME_WRITE_FAILED
    assert s.projection_mode == "EDIT"
    assert s.active_track_id is None and s.active_track_package_root is None
    assert s.channel_rack.state is rack
    assert s.live_kit.assignment_for("Kick + Bass", "Kick") is assignment
    assert s.arrangement_state is None


def test_missing_source_rejects_without_mutation(draft):
    s, root, source = draft
    enable(s)
    source.unlink()
    rack = s.channel_rack.state
    result = enter(s, root)
    assert not result.ok and result.message
    assert not root.exists()
    assert s.active_track_id is None
    assert s.projection_mode == "EDIT"
    assert s.channel_rack.state is rack


def test_empty_draft_rejects_without_initializing_arrangement(tmp_path):
    s = ws.compose_workbench_session(state_dir=tmp_path / "state")
    try:
        enable(s)
        result = enter(s, tmp_path / "track")
        assert result.outcome == "empty_draft"
        assert s.channel_rack.state is None
        assert s.arrangement_state is None
        assert s.projection_mode == "EDIT"
    finally:
        s.transport.close()


def test_legacy_pattern_requires_migration_without_silent_conversion(draft):
    s, root, _ = draft
    enable(s)
    from src.channel_rack import build_channel_rack_state

    s.channel_rack.restore_state(build_channel_rack_state(s.live_kit))
    rack = s.channel_rack.state
    assert enter(s, root).outcome == "migration_required"
    assert s.channel_rack.state is rack
    assert not root.exists()


def test_opened_track_reuses_package_and_restart_keeps_mode_separate(draft):
    s, root, _ = draft
    enable(s)
    assert enter(s, root).ok
    reopened = ws.compose_workbench_session(state_dir=s._state_dir)
    try:
        assert reopened.projection_mode == "EDIT"
        assert reopened.arrangement_state == s.arrangement_state
        assert enter(reopened).ok
        assert reopened.active_track_id == s.active_track_id
        assert reopened.active_track_package_root == root
    finally:
        reopened.transport.close()


def test_transition_does_not_use_export_or_start_playback(draft, monkeypatch):
    s, root, _ = draft
    enable(s)

    def forbidden(*args, **kwargs):
        pytest.fail("transition must not export or schedule playback")

    monkeypatch.setattr(s.channel_rack, "play", forbidden)
    from src import export_fl

    monkeypatch.setattr(export_fl, "run_export", forbidden)
    assert enter(s, root).ok
    s.return_to_edit()
    assert enter(s).ok


def test_active_playback_rejected_without_stopping_or_second_owner(draft, monkeypatch):
    s, root, _ = draft
    enable(s)
    monkeypatch.setattr(type(s.channel_rack), "is_playing", property(lambda self: True))
    result = enter(s, root)
    assert result.outcome == "playback_active"
    assert s.channel_rack.is_playing
    assert not root.exists()
    assert s.projection_mode == "EDIT"
