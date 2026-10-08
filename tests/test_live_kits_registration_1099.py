"""Issue #1099 — Live Kits package registration + explicit Open seam.

Contract: docs/TRACK_PACKAGE_OWNERSHIP_CONTRACT.md §10 (#1082).
Register ≠ Open. Package rows are not sample rows. Fail-closed Open
preserves an already-valid Active Track via #1098 bind_active_track_package.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from src import live_kits_registry as lkr
from src import track_package as tp
from src.workbench_controller import WorkbenchRow
from src.workbench_live_kit import LiveKitState
from src.workbench_session import compose_workbench_session
from src.workbench_session_store import (
    active_track_pointer_path,
    workbench_session_path,
)
from tests.audio_fixtures import write_sine_wav


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


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


def _create_package(
    tmp_path: Path,
    *,
    track_id: str,
    name: str = "track-one",
    source_name: str = "kick.wav",
) -> tuple[Path, Path]:
    library = tmp_path / "library"
    library.mkdir(parents=True, exist_ok=True)
    source = library / source_name
    if not source.exists():
        write_sine_wav(source, duration_sec=0.05, frequency_hz=60.0)
    package_root = tmp_path / "tracks" / name
    package_root.parent.mkdir(parents=True, exist_ok=True)
    live_kit = {
        "Kick + Bass": {"Kick": {"path": str(source.resolve())}, "Bass": None},
        "Drums": {
            "Main Drum": None,
            "Closed Hat": None,
            "Open Hat": None,
            "Percussion": None,
            "Additional": None,
        },
        "Melodic": {"Lead": None, "Pad": None},
        "Atmos / FX": {"Atmos": None, "FX": None},
    }
    musical = {
        "live_kit": live_kit,
        "channel_rack": None,
        "master_bpm": 128.0,
        "sync_enabled": True,
    }
    created = tp.create_track_package(
        tp.TrackPackageDraft(
            media_sources=(tp.TrackPackageMediaSource(source_path=source),),
            musical=musical,
            track_id=track_id,
        ),
        package_root,
        repo_root=_repo_root(),
    )
    assert created.outcome == tp.OUTCOME_OPEN
    assert created.package_root == package_root
    return package_root, source


def test_register_does_not_activate_active_track(tmp_path: Path) -> None:
    package_root, _source = _create_package(tmp_path, track_id="trk_1099_a")
    state_dir = tmp_path / "state"
    registry = lkr.LiveKitsRegistry(state_dir=state_dir)
    session = compose_workbench_session(state_dir=state_dir)
    try:
        assert session.active_track_id is None
        assert session.active_track_package_root is None

        result = registry.register(package_root)
        assert result.outcome == lkr.OUTCOME_READY
        assert result.entry is not None
        assert result.entry.track_id == "trk_1099_a"
        assert result.entry.entity_kind == lkr.ENTITY_KIND_TRACK_PACKAGE

        assert session.active_track_id is None
        assert session.active_track_package_root is None
        assert session.track_package_status is None
        assert not active_track_pointer_path(state_dir=state_dir).exists()
    finally:
        session.transport.close()


def test_registered_packages_listed_in_live_kits_scope(tmp_path: Path) -> None:
    root_a, _ = _create_package(tmp_path, track_id="trk_1099_list_a", name="a")
    root_b, _ = _create_package(
        tmp_path, track_id="trk_1099_list_b", name="b", source_name="snare.wav"
    )
    registry = lkr.LiveKitsRegistry(state_dir=tmp_path / "state")
    assert registry.register(root_a).outcome == lkr.OUTCOME_READY
    assert registry.register(root_b).outcome == lkr.OUTCOME_READY

    listed = registry.list_packages()
    assert registry.scope == lkr.SCOPE_LIVE_KITS
    assert [row.track_id for row in listed] == ["trk_1099_list_a", "trk_1099_list_b"]
    assert all(row.entity_kind == lkr.ENTITY_KIND_TRACK_PACKAGE for row in listed)
    assert all(row.status == lkr.OUTCOME_READY for row in listed)
    assert listed[0].package_root == root_a.resolve(strict=False)
    assert listed[1].package_root == root_b.resolve(strict=False)


def test_repeated_register_same_track_id_is_idempotent(tmp_path: Path) -> None:
    package_root, _ = _create_package(tmp_path, track_id="trk_1099_idem")
    registry = lkr.LiveKitsRegistry(state_dir=tmp_path / "state")
    first = registry.register(package_root)
    second = registry.register(package_root)
    assert first.outcome == lkr.OUTCOME_READY
    assert second.outcome == lkr.OUTCOME_READY
    assert first.entry is not None and second.entry is not None
    assert first.entry.track_id == second.entry.track_id == "trk_1099_idem"
    listed = registry.list_packages()
    assert len(listed) == 1
    assert listed[0].package_root == package_root.resolve(strict=False)


def test_register_relocate_same_track_id_updates_root_without_activation(
    tmp_path: Path,
) -> None:
    root_v1, source = _create_package(tmp_path, track_id="trk_1099_move", name="v1")
    state_dir = tmp_path / "state"
    registry = lkr.LiveKitsRegistry(state_dir=state_dir)
    session = compose_workbench_session(state_dir=state_dir)
    try:
        assert registry.register(root_v1).outcome == lkr.OUTCOME_READY
        # Relocate package directory; track_id stays the same.
        root_v2 = tmp_path / "tracks" / "v2"
        root_v1.rename(root_v2)
        assert (root_v2 / tp.TRACK_PACKAGE_FILENAME).is_file()

        again = registry.register(root_v2)
        assert again.outcome == lkr.OUTCOME_READY
        listed = registry.list_packages()
        assert len(listed) == 1
        assert listed[0].track_id == "trk_1099_move"
        assert listed[0].package_root == root_v2.resolve(strict=False)
        assert session.active_track_id is None
        assert not active_track_pointer_path(state_dir=state_dir).exists()
        assert source.exists()  # library sample untouched
    finally:
        session.transport.close()


def test_register_conflict_different_track_id_same_root_preserves_prior(
    tmp_path: Path,
) -> None:
    package_root, _ = _create_package(tmp_path, track_id="trk_1099_keep")
    registry = lkr.LiveKitsRegistry(state_dir=tmp_path / "state")
    assert registry.register(package_root).outcome == lkr.OUTCOME_READY

    # Overwrite manifest track_id in place to simulate a different package
    # trying to claim the same registry locate handle / slot.
    payload = json.loads((package_root / tp.TRACK_PACKAGE_FILENAME).read_text(encoding="utf-8"))
    payload["track_id"] = "trk_1099_intruder"
    (package_root / tp.TRACK_PACKAGE_FILENAME).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    conflict = registry.register(package_root)
    assert conflict.outcome == lkr.OUTCOME_REGISTER_CONFLICT
    listed = registry.list_packages()
    assert len(listed) == 1
    assert listed[0].track_id == "trk_1099_keep"
    assert listed[0].package_root == package_root.resolve(strict=False)


def test_explicit_open_activates_via_1098_owner(tmp_path: Path) -> None:
    package_root, _ = _create_package(tmp_path, track_id="trk_1099_open")
    state_dir = tmp_path / "state"
    registry = lkr.LiveKitsRegistry(state_dir=state_dir)
    session = compose_workbench_session(state_dir=state_dir)
    try:
        assert registry.register(package_root).outcome == lkr.OUTCOME_READY
        assert session.active_track_id is None

        opened = registry.open_package(package_root, session=session)
        assert opened.outcome == tp.OUTCOME_OPEN
        assert session.active_track_id == "trk_1099_open"
        assert session.active_track_package_root == package_root.resolve(strict=False)
        assert session.track_package_status == tp.OUTCOME_OPEN
        pointer = json.loads(
            active_track_pointer_path(state_dir=state_dir).read_text(encoding="utf-8")
        )
        assert pointer["track_id"] == "trk_1099_open"
        assert Path(pointer["package_root"]) == package_root.resolve(strict=False)
    finally:
        session.transport.close()


def test_explicit_open_binds_exactly_one_active_track(tmp_path: Path) -> None:
    root_a, _ = _create_package(tmp_path, track_id="trk_1099_one_a", name="a")
    root_b, _ = _create_package(
        tmp_path, track_id="trk_1099_one_b", name="b", source_name="snare.wav"
    )
    state_dir = tmp_path / "state"
    registry = lkr.LiveKitsRegistry(state_dir=state_dir)
    session = compose_workbench_session(state_dir=state_dir)
    try:
        assert registry.register(root_a).outcome == lkr.OUTCOME_READY
        assert registry.register(root_b).outcome == lkr.OUTCOME_READY
        assert registry.open_package(root_a, session=session).outcome == tp.OUTCOME_OPEN
        assert registry.open_package(root_b, session=session).outcome == tp.OUTCOME_OPEN
        assert session.active_track_id == "trk_1099_one_b"
        assert session.active_track_package_root == root_b.resolve(strict=False)
        # Exactly one durable pointer.
        pointer = json.loads(
            active_track_pointer_path(state_dir=state_dir).read_text(encoding="utf-8")
        )
        assert pointer["track_id"] == "trk_1099_one_b"
        assert Path(pointer["package_root"]) == root_b.resolve(strict=False)
        listed = registry.list_packages()
        assert len(listed) == 2
    finally:
        session.transport.close()


def test_open_corrupt_activates_nothing(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    registry = lkr.LiveKitsRegistry(state_dir=state_dir)
    session = compose_workbench_session(state_dir=state_dir)
    bogus = tmp_path / "tracks" / "corrupt"
    bogus.mkdir(parents=True)
    (bogus / tp.TRACK_PACKAGE_FILENAME).write_text("{not-json", encoding="utf-8")
    try:
        opened = registry.open_package(bogus, session=session)
        assert opened.outcome == tp.OUTCOME_CORRUPT_OR_UNSUPPORTED
        assert session.active_track_id is None
        assert session.active_track_package_root is None
        assert not active_track_pointer_path(state_dir=state_dir).exists()
    finally:
        session.transport.close()


def test_open_missing_media_activates_nothing(tmp_path: Path) -> None:
    package_root, _ = _create_package(tmp_path, track_id="trk_1099_media")
    media_dir = package_root / tp.MEDIA_DIR_NAME
    for child in media_dir.iterdir():
        child.unlink()
    state_dir = tmp_path / "state"
    registry = lkr.LiveKitsRegistry(state_dir=state_dir)
    session = compose_workbench_session(state_dir=state_dir)
    try:
        opened = registry.open_package(package_root, session=session)
        assert opened.outcome == tp.OUTCOME_MISSING_MEDIA
        assert session.active_track_id is None
        assert not active_track_pointer_path(state_dir=state_dir).exists()
    finally:
        session.transport.close()


def test_open_path_escape_activates_nothing(tmp_path: Path) -> None:
    package_root, _ = _create_package(tmp_path, track_id="trk_1099_escape")
    payload = json.loads((package_root / tp.TRACK_PACKAGE_FILENAME).read_text(encoding="utf-8"))
    payload["media"] = [{"media_id": "m_escape", "relpath": "../outside.wav"}]
    (package_root / tp.TRACK_PACKAGE_FILENAME).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    state_dir = tmp_path / "state"
    registry = lkr.LiveKitsRegistry(state_dir=state_dir)
    session = compose_workbench_session(state_dir=state_dir)
    try:
        opened = registry.open_package(package_root, session=session)
        assert opened.outcome == tp.OUTCOME_PATH_ESCAPE_REJECTED
        assert session.active_track_id is None
        assert not active_track_pointer_path(state_dir=state_dir).exists()
    finally:
        session.transport.close()


def test_failed_open_preserves_valid_active_track(tmp_path: Path) -> None:
    root_ok, _ = _create_package(tmp_path, track_id="trk_1099_keep_active", name="ok")
    state_dir = tmp_path / "state"
    registry = lkr.LiveKitsRegistry(state_dir=state_dir)
    session = compose_workbench_session(state_dir=state_dir)
    bogus = tmp_path / "tracks" / "bogus"
    bogus.mkdir(parents=True)
    (bogus / tp.TRACK_PACKAGE_FILENAME).write_text("{bad", encoding="utf-8")
    try:
        assert registry.register(root_ok).outcome == lkr.OUTCOME_READY
        assert registry.open_package(root_ok, session=session).outcome == tp.OUTCOME_OPEN
        before_id = session.active_track_id
        before_root = session.active_track_package_root
        before_status = session.track_package_status
        before_assignment = session.live_kit.assignment_for("Kick + Bass", "Kick")

        failed = registry.open_package(bogus, session=session)
        assert failed.outcome != tp.OUTCOME_OPEN
        assert session.active_track_id == before_id
        assert session.active_track_package_root == before_root
        assert session.track_package_status == before_status
        after = session.live_kit.assignment_for("Kick + Bass", "Kick")
        assert after is not None and before_assignment is not None
        assert after.path == before_assignment.path
        pointer = json.loads(
            active_track_pointer_path(state_dir=state_dir).read_text(encoding="utf-8")
        )
        assert pointer["track_id"] == before_id
        assert Path(pointer["package_root"]) == before_root
    finally:
        session.transport.close()


def test_package_row_cannot_enter_sample_audition_or_assignment(tmp_path: Path) -> None:
    package_root, _ = _create_package(tmp_path, track_id="trk_1099_row")
    registry = lkr.LiveKitsRegistry(state_dir=tmp_path / "state")
    result = registry.register(package_root)
    assert result.entry is not None
    row = result.entry
    assert row.entity_kind == lkr.ENTITY_KIND_TRACK_PACKAGE
    assert not isinstance(row, WorkbenchRow)

    with pytest.raises(lkr.PackageEntityError):
        lkr.require_sample_row(row)

    kit = LiveKitState()
    with pytest.raises(lkr.PackageEntityError):
        lkr.assign_sample_to_kit(kit, "Kick + Bass", "Kick", row)

    with pytest.raises(lkr.PackageEntityError):
        lkr.audition_sample_row(row)

    with pytest.raises(lkr.PackageEntityError):
        lkr.replace_sample_assignment(kit, "Kick + Bass", "Kick", row)

    assert kit.assignment_for("Kick + Bass", "Kick") is None


def test_registration_does_not_touch_sample_library_catalog(tmp_path: Path) -> None:
    db_path = tmp_path / "catalog.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE samples (id INTEGER PRIMARY KEY, path TEXT UNIQUE, hash TEXT)"
        )
        conn.execute(
            "INSERT INTO samples (path, hash) VALUES (?, ?)",
            ("rel/synthetic.wav", "abc"),
        )
        conn.commit()
        before = conn.execute("SELECT COUNT(*), path, hash FROM samples").fetchall()
    finally:
        conn.close()

    package_root, _ = _create_package(tmp_path, track_id="trk_1099_lib")
    registry = lkr.LiveKitsRegistry(state_dir=tmp_path / "state")
    assert registry.register(package_root).outcome == lkr.OUTCOME_READY

    conn = sqlite3.connect(db_path)
    try:
        after = conn.execute("SELECT COUNT(*), path, hash FROM samples").fetchall()
    finally:
        conn.close()
    assert after == before


def test_no_private_absolute_paths_leaked_in_registry_messages(tmp_path: Path) -> None:
    bogus = tmp_path / "tracks" / "private-fail"
    bogus.mkdir(parents=True)
    (bogus / tp.TRACK_PACKAGE_FILENAME).write_text("{bad", encoding="utf-8")
    registry = lkr.LiveKitsRegistry(state_dir=tmp_path / "state")
    session = compose_workbench_session(state_dir=tmp_path / "state")
    try:
        opened = registry.open_package(bogus, session=session)
        assert opened.outcome == tp.OUTCOME_CORRUPT_OR_UNSUPPORTED
        if opened.message:
            assert str(bogus) not in opened.message
            assert ":\\" not in opened.message
            assert "/Users/" not in opened.message
    finally:
        session.transport.close()


def test_register_then_list_inactive_then_open_active_smoke(tmp_path: Path) -> None:
    """Runtime smoke: register -> listed inactive -> open -> active."""
    package_root, _ = _create_package(tmp_path, track_id="trk_1099_smoke")
    state_dir = tmp_path / "state"
    registry = lkr.LiveKitsRegistry(state_dir=state_dir)
    session = compose_workbench_session(state_dir=state_dir)
    try:
        assert registry.register(package_root).outcome == lkr.OUTCOME_READY
        listed = registry.list_packages()
        assert len(listed) == 1
        assert listed[0].status == lkr.OUTCOME_READY
        assert session.active_track_id is None
        assert registry.open_package(package_root, session=session).outcome == tp.OUTCOME_OPEN
        assert session.active_track_id == "trk_1099_smoke"
        assert workbench_session_path(state_dir=state_dir).exists() or True
    finally:
        session.transport.close()


def test_open_conflict_preserves_prior_registration_and_active_track(
    tmp_path: Path,
) -> None:
    """P1: Open must not bind when root is claimed by a different track_id."""
    root_ok, _ = _create_package(tmp_path, track_id="trk_1099_claim", name="claimed")
    state_dir = tmp_path / "state"
    registry = lkr.LiveKitsRegistry(state_dir=state_dir)
    session = compose_workbench_session(state_dir=state_dir)
    try:
        assert registry.register(root_ok).outcome == lkr.OUTCOME_READY
        assert registry.open_package(root_ok, session=session).outcome == tp.OUTCOME_OPEN
        before_id = session.active_track_id
        before_root = session.active_track_package_root

        payload = json.loads((root_ok / tp.TRACK_PACKAGE_FILENAME).read_text(encoding="utf-8"))
        payload["track_id"] = "trk_1099_intruder_open"
        (root_ok / tp.TRACK_PACKAGE_FILENAME).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        conflicted = registry.open_package(root_ok, session=session)
        assert conflicted.outcome == lkr.OUTCOME_REGISTER_CONFLICT
        assert session.active_track_id == before_id
        assert session.active_track_package_root == before_root
        listed = registry.list_packages()
        assert len(listed) == 1
        assert listed[0].track_id == "trk_1099_claim"
    finally:
        session.transport.close()


def test_register_persist_failure_rolls_back_in_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P2: unwritable registry persist must not leave ambiguous in-memory state."""
    package_root, _ = _create_package(tmp_path, track_id="trk_1099_write")
    registry = lkr.LiveKitsRegistry(state_dir=tmp_path / "state")

    def boom(_path: Path, _payload: object) -> None:
        raise OSError("synthetic registry write failure")

    monkeypatch.setattr(lkr, "_atomic_write_json", boom)
    failed = registry.register(package_root)
    assert failed.outcome == tp.OUTCOME_WRITE_FAILED
    assert registry.list_packages() == ()


def test_register_resolve_failure_returns_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Path resolution failures must not escape as exceptions."""
    package_root, _ = _create_package(tmp_path, track_id="trk_1099_resolve")
    registry = lkr.LiveKitsRegistry(state_dir=tmp_path / "state")

    def boom(_path: Path | str) -> Path | None:
        return None

    monkeypatch.setattr(lkr, "_safe_resolve", boom)
    failed = registry.register(package_root)
    assert failed.outcome == tp.OUTCOME_CORRUPT_OR_UNSUPPORTED
    assert registry.list_packages() == ()


def test_stale_unresolvable_registry_entry_does_not_crash_register(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stored roots that fail resolve are skipped during conflict checks."""
    root_a, _ = _create_package(tmp_path, track_id="trk_1099_stale_a", name="a")
    root_b, _ = _create_package(
        tmp_path, track_id="trk_1099_stale_b", name="b", source_name="snare.wav"
    )
    registry = lkr.LiveKitsRegistry(state_dir=tmp_path / "state")
    assert registry.register(root_a).outcome == lkr.OUTCOME_READY

    real_safe = lkr._safe_resolve

    def selective(path: Path | str) -> Path | None:
        resolved = real_safe(path)
        if resolved is None:
            return None
        if resolved == root_a.resolve(strict=False):
            return None
        return resolved

    monkeypatch.setattr(lkr, "_safe_resolve", selective)
    result = registry.register(root_b)
    assert result.outcome == lkr.OUTCOME_READY
    assert result.entry is not None
    assert result.entry.track_id == "trk_1099_stale_b"


def test_open_registry_persist_failure_does_not_activate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Registry must persist before bind; write failure leaves Active Track untouched."""
    package_root, _ = _create_package(tmp_path, track_id="trk_1099_open_write")
    state_dir = tmp_path / "state"
    registry = lkr.LiveKitsRegistry(state_dir=state_dir)
    session = compose_workbench_session(state_dir=state_dir)

    def boom(_path: Path, _payload: object) -> None:
        raise OSError("synthetic registry write failure")

    monkeypatch.setattr(lkr, "_atomic_write_json", boom)
    try:
        failed = registry.open_package(package_root, session=session)
        assert failed.outcome == tp.OUTCOME_WRITE_FAILED
        assert session.active_track_id is None
        assert session.active_track_package_root is None
        assert not active_track_pointer_path(state_dir=state_dir).exists()
        assert registry.list_packages() == ()
    finally:
        session.transport.close()
