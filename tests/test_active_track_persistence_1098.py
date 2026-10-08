"""Issue #1098 — active track package persistence + restart precedence.

Contract authority: docs/TRACK_PACKAGE_OWNERSHIP_CONTRACT.md (#1082).
These tests protect one WorkbenchSession musical owner while a bound package,
not legacy workbench_session.json, becomes the durable musical authority.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from src import track_package as tp
from src.workbench_controller import WorkbenchRow
from src.workbench_session import compose_workbench_session
from src.workbench_session_store import (
    active_track_pointer_path,
    workbench_session_path,
)
from tests.audio_fixtures import write_sine_wav


def _row(path: Path) -> WorkbenchRow:
    return WorkbenchRow(
        display_name=path.name,
        relative_path=path.name,
        path=str(path),
        bpm=None,
        key=None,
        key_conf=None,
        loudness=None,
        brightness=None,
        sample_class="oneshot",
        pred_type=None,
        status="ok",
        details={},
    )


def _legacy_payload(state_dir: Path) -> dict:
    return json.loads(workbench_session_path(state_dir=state_dir).read_text(encoding="utf-8"))


def _create_from_current_session(
    *,
    state_dir: Path,
    package_root: Path,
    source: Path,
    track_id: str,
    arrangement: object | None = None,
) -> tp.TrackPackageResult:
    payload = _legacy_payload(state_dir)
    musical = {
        "live_kit": payload["live_kit"],
        "channel_rack": payload["channel_rack"],
        "master_bpm": payload["master_bpm"],
        "sync_enabled": payload["sync_enabled"],
    }
    return tp.create_track_package(
        tp.TrackPackageDraft(
            media_sources=(tp.TrackPackageMediaSource(source_path=source),),
            musical=musical,
            track_id=track_id,
            arrangement=arrangement,
        ),
        package_root,
        repo_root=Path(__file__).resolve().parents[1],
    )


def _manifest_payload(package_root: Path) -> dict:
    return json.loads((package_root / tp.TRACK_PACKAGE_FILENAME).read_text(encoding="utf-8"))


def _seed_bound_session(tmp_path: Path, *, arrangement: object | None = None):
    state_dir = tmp_path / "state"
    library = tmp_path / "library"
    package_root = tmp_path / "tracks" / "track-one"
    library.mkdir(parents=True)
    package_root.parent.mkdir(parents=True)
    kick = library / "kick.wav"
    write_sine_wav(kick, duration_sec=0.05, frequency_hz=60.0)

    session = compose_workbench_session(state_dir=state_dir)
    session.live_kit.assign("Kick + Bass", "Kick", _row(kick))
    session.channel_rack.ensure_state()
    legacy_before = workbench_session_path(state_dir=state_dir).read_bytes()

    created = _create_from_current_session(
        state_dir=state_dir,
        package_root=package_root,
        source=kick,
        track_id="trk_1098_test",
        arrangement=arrangement,
    )
    assert created.outcome == tp.OUTCOME_OPEN

    bound = session.bind_active_track_package(package_root)
    assert bound.outcome == tp.OUTCOME_OPEN
    return session, state_dir, package_root, kick, legacy_before


def test_bound_track_autosaves_package_and_restart_prefers_it_over_legacy(tmp_path: Path) -> None:
    arrangement = {"future": {"opaque": [1, 2, 3]}}
    session, state_dir, package_root, _kick, legacy_before = _seed_bound_session(
        tmp_path, arrangement=arrangement
    )
    try:
        assert session.active_track_id == "trk_1098_test"
        assert session.active_track_package_root == package_root
        assert session.track_package_status == tp.OUTCOME_OPEN
        assert session.track_package_dirty is False
        rebound = session.live_kit.assignment_for("Kick + Bass", "Kick")
        assert rebound is not None
        assert Path(rebound.path).is_relative_to(package_root)

        session.transport.set_tempo(140.0)

        assert session.track_package_status == tp.OUTCOME_OPEN
        assert session.track_package_dirty is False
        assert workbench_session_path(state_dir=state_dir).read_bytes() == legacy_before
        package_payload = _manifest_payload(package_root)
        assert package_payload["musical"]["master_bpm"] == pytest.approx(140.0)
        assert package_payload["arrangement"] == arrangement
    finally:
        session.transport.close()

    restarted = compose_workbench_session(state_dir=state_dir)
    try:
        assert restarted.active_track_id == "trk_1098_test"
        assert restarted.active_track_package_root == package_root
        assert restarted.track_package_status == tp.OUTCOME_OPEN
        assert restarted.transport.get_current_tempo() == pytest.approx(140.0)
        restored = restarted.live_kit.assignment_for("Kick + Bass", "Kick")
        assert restored is not None
        assert Path(restored.path).is_relative_to(package_root)
        assert workbench_session_path(state_dir=state_dir).read_bytes() == legacy_before
    finally:
        restarted.transport.close()


def test_track_write_failure_is_separate_honest_and_preserves_last_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session, state_dir, package_root, _kick, legacy_before = _seed_bound_session(tmp_path)
    manifest_path = package_root / tp.TRACK_PACKAGE_FILENAME
    package_before = manifest_path.read_bytes()
    legacy_status_before = session.persistence_status
    real_replace = os.replace
    failures_left = 1

    def fail_first_manifest_replace(src: str | bytes | os.PathLike, dst: str | bytes | os.PathLike) -> None:
        nonlocal failures_left
        if Path(dst) == manifest_path and failures_left:
            failures_left -= 1
            raise OSError("synthetic package write failure")
        real_replace(src, dst)

    monkeypatch.setattr(tp.os, "replace", fail_first_manifest_replace)
    try:
        session.transport.set_tempo(141.0)
        assert session.transport.get_current_tempo() == pytest.approx(141.0)
        assert session.track_package_status == tp.OUTCOME_WRITE_FAILED
        assert session.track_package_dirty is True
        assert session.persistence_status == legacy_status_before
        assert manifest_path.read_bytes() == package_before
        assert workbench_session_path(state_dir=state_dir).read_bytes() == legacy_before

        # Next meaningful mutation retries the same package writer and clears dirty on success.
        session.transport.set_tempo(142.0)
        assert session.track_package_status == tp.OUTCOME_OPEN
        assert session.track_package_dirty is False
        assert _manifest_payload(package_root)["musical"]["master_bpm"] == pytest.approx(142.0)
    finally:
        session.transport.close()


def test_missing_bound_package_on_restart_fails_closed_instead_of_restoring_stale_legacy(
    tmp_path: Path,
) -> None:
    session, state_dir, package_root, _kick, legacy_before = _seed_bound_session(tmp_path)
    session.transport.close()
    shutil.rmtree(package_root)

    restarted = compose_workbench_session(state_dir=state_dir)
    try:
        assert restarted.track_package_status == tp.OUTCOME_CORRUPT_OR_UNSUPPORTED
        assert restarted.active_track_id == "trk_1098_test"
        assert restarted.active_track_package_root == package_root
        assert restarted.live_kit.assignment_for("Kick + Bass", "Kick") is None
        assert restarted.channel_rack.state is None
        assert workbench_session_path(state_dir=state_dir).read_bytes() == legacy_before
    finally:
        restarted.transport.close()


def test_bound_live_kit_replacement_copies_new_media_and_restores_portably(tmp_path: Path) -> None:
    session, state_dir, package_root, _kick, legacy_before = _seed_bound_session(tmp_path)
    replacement = tmp_path / "another-library" / "replacement.wav"
    replacement.parent.mkdir()
    write_sine_wav(replacement, duration_sec=0.05, frequency_hz=92.0)
    replacement_bytes = replacement.read_bytes()
    try:
        session.live_kit.assign("Kick + Bass", "Kick", _row(replacement))
        assert session.track_package_status == tp.OUTCOME_OPEN
        assert session.track_package_dirty is False
        active_assignment = session.live_kit.assignment_for("Kick + Bass", "Kick")
        assert active_assignment is not None
        assert Path(active_assignment.path).is_relative_to(package_root)
        payload = _manifest_payload(package_root)
        portable_ref = payload["musical"]["live_kit"]["Kick + Bass"]["Kick"]["path"]
        assert portable_ref.startswith("media/")
        assert str(replacement) not in json.dumps(payload)
        copied = package_root / Path(*portable_ref.split("/"))
        assert copied.read_bytes() == replacement_bytes
        media_count = len(payload["media"])

        # A later unrelated autosave must reuse that already-imported media,
        # not duplicate the same source into another package media entry.
        session.transport.set_tempo(133.0)
        after_clock_save = _manifest_payload(package_root)
        assert len(after_clock_save["media"]) == media_count
        assert workbench_session_path(state_dir=state_dir).read_bytes() == legacy_before
    finally:
        session.transport.close()

    restarted = compose_workbench_session(state_dir=state_dir)
    try:
        restored = restarted.live_kit.assignment_for("Kick + Bass", "Kick")
        assert restored is not None
        restored_path = Path(restored.path)
        assert restored_path.is_relative_to(package_root)
        assert restored_path.read_bytes() == replacement_bytes
    finally:
        restarted.transport.close()


def test_failed_open_does_not_replace_existing_active_track(tmp_path: Path) -> None:
    session, state_dir, package_root, kick, legacy_before = _seed_bound_session(tmp_path)
    bogus_root = tmp_path / "tracks" / "bogus"
    bogus_root.mkdir(parents=True)
    (bogus_root / tp.TRACK_PACKAGE_FILENAME).write_text("{not a package", encoding="utf-8")
    try:
        before_id = session.active_track_id
        before_root = session.active_track_package_root
        before_assignment = session.live_kit.assignment_for("Kick + Bass", "Kick")
        failed = session.bind_active_track_package(bogus_root)
        assert failed.outcome != tp.OUTCOME_OPEN
        assert session.active_track_id == before_id
        assert session.active_track_package_root == before_root
        assert session.track_package_status == tp.OUTCOME_OPEN
        after_assignment = session.live_kit.assignment_for("Kick + Bass", "Kick")
        assert after_assignment is not None
        assert after_assignment.path == before_assignment.path
        assert workbench_session_path(state_dir=state_dir).read_bytes() == legacy_before
        pointer = json.loads(
            active_track_pointer_path(state_dir=state_dir).read_text(encoding="utf-8")
        )
        assert pointer["track_id"] == before_id
        assert Path(pointer["package_root"]) == before_root
    finally:
        session.transport.close()


def test_active_pointer_outranks_legacy_on_restart(tmp_path: Path) -> None:
    session, state_dir, package_root, _kick, legacy_before = _seed_bound_session(tmp_path)
    session.transport.set_tempo(137.0)
    session.transport.close()

    legacy_payload = json.loads(
        workbench_session_path(state_dir=state_dir).read_text(encoding="utf-8")
    )
    legacy_payload["master_bpm"] = 999.0
    workbench_session_path(state_dir=state_dir).write_text(
        json.dumps(legacy_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    assert workbench_session_path(state_dir=state_dir).read_bytes() != legacy_before

    restarted = compose_workbench_session(state_dir=state_dir)
    try:
        assert restarted.transport.get_current_tempo() == pytest.approx(137.0)
        assert restarted.active_track_id == "trk_1098_test"
    finally:
        restarted.transport.close()


def test_corrupt_active_pointer_fails_closed_without_touching_legacy(
    tmp_path: Path,
) -> None:
    session, state_dir, package_root, _kick, legacy_before = _seed_bound_session(tmp_path)
    session.transport.close()
    active_track_pointer_path(state_dir=state_dir).write_text("{bad", encoding="utf-8")

    restarted = compose_workbench_session(state_dir=state_dir)
    try:
        assert restarted.track_package_status == tp.OUTCOME_CORRUPT_OR_UNSUPPORTED
        assert restarted.live_kit.assignment_for("Kick + Bass", "Kick") is None
        assert workbench_session_path(state_dir=state_dir).read_bytes() == legacy_before
    finally:
        restarted.transport.close()


def test_bound_pattern_mutation_round_trips_through_track_package(tmp_path: Path) -> None:
    session, state_dir, package_root, _kick, legacy_before = _seed_bound_session(tmp_path)
    try:
        before = session.channel_rack.state
        assert before is not None
        mutated = session.channel_rack.toggle_step("ch_kick", 0)
        assert mutated.pattern.triggers != before.pattern.triggers
        assert session.track_package_status == tp.OUTCOME_OPEN
        assert session.track_package_dirty is False
        assert workbench_session_path(state_dir=state_dir).read_bytes() == legacy_before
    finally:
        session.transport.close()

    restarted = compose_workbench_session(state_dir=state_dir)
    try:
        restored = restarted.channel_rack.state
        assert restored is not None
        assert restored.pattern.triggers == mutated.pattern.triggers
        assert restarted.active_track_package_root == package_root
    finally:
        restarted.transport.close()
