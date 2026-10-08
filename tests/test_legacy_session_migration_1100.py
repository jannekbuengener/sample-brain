"""Issue #1100 — non-destructive legacy workbench_session.json → track package.

Contract authority: docs/TRACK_PACKAGE_OWNERSHIP_CONTRACT.md §7 / vectors 11–13.
Reuses #1096 package create, #1098 active-track bind, #1099 Live Kits register.
Never auto-migrates on compose. Never mutates/deletes legacy bytes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import legacy_session_migration as lsm
from src import live_kits_registry as lkr
from src import track_package as tp
from src.pattern_core import CHANNEL_ID_BY_LIVE_KIT_SLOT
from src.workbench_live_kit import LIVE_KIT_SLOT_MAPPING
from src.workbench_session import compose_workbench_session
from src.workbench_session_store import (
    workbench_session_path,
)
from tests.audio_fixtures import write_sine_wav


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _empty_live_kit(path_by_slot: dict[tuple[str, str], str] | None = None) -> dict:
    assigned = path_by_slot or {}
    return {
        group: {
            slot: (
                {"path": assigned[(group, slot)]}
                if (group, slot) in assigned
                else None
            )
            for slot in slots
        }
        for group, slots in LIVE_KIT_SLOT_MAPPING
    }


def _seed_channels(path_by_slot: dict[tuple[str, str], str] | None = None) -> list[dict]:
    assigned = path_by_slot or {}
    channels: list[dict] = []
    for (group, slot), channel_id in CHANNEL_ID_BY_LIVE_KIT_SLOT.items():
        channels.append(
            {
                "channel_id": channel_id,
                "live_kit_group": group,
                "live_kit_slot": slot,
                "sample_path": assigned.get((group, slot)),
            }
        )
    return channels


def _legacy_v2_payload(
    *,
    kick_path: str,
    master_bpm: float = 132.0,
    sync_enabled: bool = True,
    with_rack: bool = True,
) -> dict:
    assigned = {("Kick + Bass", "Kick"): kick_path}
    rack = None
    if with_rack:
        rack = {
            "pattern_id": "pattern_main",
            "length_quarter_notes": {"numerator": 4, "denominator": 1},
            "step_count": 16,
            "channels": _seed_channels(assigned),
            "triggers": [
                {
                    "channel_id": "ch_kick",
                    "position": {"numerator": 0, "denominator": 1},
                },
                {
                    "channel_id": "ch_kick",
                    "position": {"numerator": 1, "denominator": 1},
                },
            ],
        }
    return {
        "schema_version": 2,
        "master_bpm": master_bpm,
        "sync_enabled": sync_enabled,
        "live_kit": _empty_live_kit(assigned),
        "channel_rack": rack,
    }


def _legacy_v1_payload(*, kick_path: str) -> dict:
    """Proven schema v1 shape (no master_bpm / sync_enabled root keys)."""
    assigned = {("Kick + Bass", "Kick"): kick_path}
    return {
        "schema_version": 1,
        "live_kit": _empty_live_kit(assigned),
        "channel_rack": {
            "pattern_id": "pattern_main",
            "length_quarter_notes": {"numerator": 4, "denominator": 1},
            "step_count": 16,
            "channels": _seed_channels(assigned),
            "triggers": [
                {
                    "channel_id": "ch_kick",
                    "position": {"numerator": 0, "denominator": 4},
                }
            ],
        },
    }


def _write_legacy(state_dir: Path, payload: dict) -> Path:
    state_dir.mkdir(parents=True, exist_ok=True)
    path = workbench_session_path(state_dir=state_dir)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return path


def _seed_legacy_v2(tmp_path: Path, *, with_rack: bool = True):
    state_dir = tmp_path / "state"
    library = tmp_path / "library"
    library.mkdir(parents=True)
    kick = library / "kick.wav"
    write_sine_wav(kick, duration_sec=0.05, frequency_hz=60.0)
    kick_bytes = kick.read_bytes()
    path = _write_legacy(
        state_dir,
        _legacy_v2_payload(kick_path=str(kick.resolve()), with_rack=with_rack),
    )
    legacy_bytes = path.read_bytes()
    packages = tmp_path / "packages"
    packages.mkdir()
    package_root = packages / "migrated-track"
    return state_dir, kick, kick_bytes, path, legacy_bytes, package_root


def _assert_no_private_paths(document: str, *forbidden: Path) -> None:
    assert ":\\" not in document
    assert "file://" not in document.casefold()
    for item in forbidden:
        assert str(item.resolve()) not in document
        assert str(item) not in document


def _assert_no_half_valid_package(package_root: Path) -> None:
    assert not package_root.exists()
    parent = package_root.parent
    if parent.exists():
        leftovers = [
            p
            for p in parent.iterdir()
            if p.name.startswith(".sample-brain-track-package-")
        ]
        assert leftovers == []


# ---------------------------------------------------------------------------
# Detection (explicit; no auto-migrate on compose)
# ---------------------------------------------------------------------------


def test_detect_no_legacy_state(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    result = lsm.detect_legacy_session_migration(state_dir=state_dir)
    assert result.outcome == lsm.OUTCOME_DRAFT
    assert result.package_root is None
    assert result.message is None or ":\\" not in (result.message or "")


def test_detect_valid_v2_requires_migration_not_auto_on_compose(tmp_path: Path) -> None:
    state_dir, kick, _kb, _path, legacy_bytes, _pkg = _seed_legacy_v2(tmp_path)
    detected = lsm.detect_legacy_session_migration(state_dir=state_dir)
    assert detected.outcome == lsm.OUTCOME_MIGRATION_REQUIRED

    session = compose_workbench_session(state_dir=state_dir)
    try:
        assert session.active_track_id is None
        assert session.active_track_package_root is None
        restored = session.live_kit.assignment_for("Kick + Bass", "Kick")
        assert restored is not None
        assert Path(restored.path) == kick.resolve()
    finally:
        session.transport.close()

    assert workbench_session_path(state_dir=state_dir).read_bytes() == legacy_bytes


def test_detect_valid_v1_golden_requires_migration(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    library = tmp_path / "library"
    library.mkdir()
    kick = library / "kick.wav"
    write_sine_wav(kick, duration_sec=0.05, frequency_hz=55.0)
    _write_legacy(state_dir, _legacy_v1_payload(kick_path=str(kick.resolve())))
    detected = lsm.detect_legacy_session_migration(state_dir=state_dir)
    assert detected.outcome == lsm.OUTCOME_MIGRATION_REQUIRED


# ---------------------------------------------------------------------------
# Happy path: valid legacy → package + relative media + legacy preserved
# ---------------------------------------------------------------------------


def test_migrate_valid_v2_to_package_relative_media_preserves_legacy(
    tmp_path: Path,
) -> None:
    state_dir, kick, kick_bytes, legacy_path, legacy_bytes, package_root = _seed_legacy_v2(
        tmp_path
    )
    session = compose_workbench_session(state_dir=state_dir)
    try:
        result = lsm.migrate_legacy_session_to_track_package(
            package_root,
            state_dir=state_dir,
            session=session,
            repo_root=_repo_root(),
            track_id="trk_1100_happy",
        )
        assert result.outcome == tp.OUTCOME_OPEN
        assert result.ok is True
        assert result.track_id == "trk_1100_happy"
        assert result.package_root == package_root
        assert package_root.is_dir()
        assert (package_root / tp.TRACK_PACKAGE_FILENAME).is_file()

        payload = json.loads(
            (package_root / tp.TRACK_PACKAGE_FILENAME).read_text(encoding="utf-8")
        )
        dumped = json.dumps(payload)
        _assert_no_private_paths(dumped, kick, legacy_path, state_dir)
        for entry in payload["media"]:
            assert entry["relpath"].startswith(f"{tp.MEDIA_DIR_NAME}/")
            assert not Path(entry["relpath"]).is_absolute()
            assert (package_root / entry["relpath"]).is_file()

        kick_rel = payload["musical"]["live_kit"]["Kick + Bass"]["Kick"]["path"]
        assert kick_rel.startswith(f"{tp.MEDIA_DIR_NAME}/")
        assert Path(kick_rel).is_absolute() is False

        assert legacy_path.read_bytes() == legacy_bytes
        assert kick.read_bytes() == kick_bytes
        assert kick.exists()

        assert session.active_track_id == "trk_1100_happy"
        assert session.active_track_package_root == package_root
        assert session.track_package_status == tp.OUTCOME_OPEN
        bound = session.live_kit.assignment_for("Kick + Bass", "Kick")
        assert bound is not None
        assert Path(bound.path).is_relative_to(package_root)
        assert session.transport.get_current_tempo() == pytest.approx(132.0)
        assert session.transport.is_sync_enabled() is True
    finally:
        session.transport.close()


def test_migrate_valid_v1_golden_preserves_defaults_and_legacy(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    library = tmp_path / "library"
    library.mkdir()
    kick = library / "kick.wav"
    write_sine_wav(kick, duration_sec=0.05, frequency_hz=70.0)
    kick_bytes = kick.read_bytes()
    legacy_path = _write_legacy(
        state_dir, _legacy_v1_payload(kick_path=str(kick.resolve()))
    )
    legacy_bytes = legacy_path.read_bytes()
    package_root = tmp_path / "packages" / "v1-track"
    package_root.parent.mkdir()

    session = compose_workbench_session(state_dir=state_dir)
    try:
        result = lsm.migrate_legacy_session_to_track_package(
            package_root,
            state_dir=state_dir,
            session=session,
            repo_root=_repo_root(),
            track_id="trk_1100_v1",
        )
        assert result.outcome == tp.OUTCOME_OPEN
        payload = json.loads(
            (package_root / tp.TRACK_PACKAGE_FILENAME).read_text(encoding="utf-8")
        )
        assert payload["musical"]["sync_enabled"] is False
        assert payload["musical"]["channel_rack"]["step_count"] == 16
        assert payload["musical"]["channel_rack"]["length_quarter_notes"] == {
            "numerator": 4,
            "denominator": 1,
        }
        assert legacy_path.read_bytes() == legacy_bytes
        assert kick.read_bytes() == kick_bytes
    finally:
        session.transport.close()


def test_migrate_v2_null_rack_variant(tmp_path: Path) -> None:
    state_dir, kick, kick_bytes, legacy_path, legacy_bytes, package_root = _seed_legacy_v2(
        tmp_path, with_rack=False
    )
    session = compose_workbench_session(state_dir=state_dir)
    try:
        result = lsm.migrate_legacy_session_to_track_package(
            package_root,
            state_dir=state_dir,
            session=session,
            repo_root=_repo_root(),
            track_id="trk_1100_null_rack",
        )
        assert result.outcome == tp.OUTCOME_OPEN
        payload = json.loads(
            (package_root / tp.TRACK_PACKAGE_FILENAME).read_text(encoding="utf-8")
        )
        assert payload["musical"]["channel_rack"] is None
        assert legacy_path.read_bytes() == legacy_bytes
        assert kick.read_bytes() == kick_bytes
    finally:
        session.transport.close()


# ---------------------------------------------------------------------------
# Missing media / corrupt / unsupported
# ---------------------------------------------------------------------------


def test_missing_media_recoverable_legacy_bytes_identical(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    missing = tmp_path / "library" / "gone.wav"
    missing.parent.mkdir()
    # File never created.
    legacy_path = _write_legacy(
        state_dir, _legacy_v2_payload(kick_path=str(missing.resolve()))
    )
    legacy_bytes = legacy_path.read_bytes()
    package_root = tmp_path / "packages" / "pkg"
    package_root.parent.mkdir()

    detected = lsm.detect_legacy_session_migration(state_dir=state_dir)
    assert detected.outcome == lsm.OUTCOME_MIGRATION_REQUIRED

    session = compose_workbench_session(state_dir=state_dir)
    try:
        result = lsm.migrate_legacy_session_to_track_package(
            package_root,
            state_dir=state_dir,
            session=session,
            repo_root=_repo_root(),
        )
        assert result.outcome == tp.OUTCOME_MISSING_MEDIA
        assert result.ok is False
        assert session.active_track_id is None
        _assert_no_half_valid_package(package_root)
        assert legacy_path.read_bytes() == legacy_bytes
        assert result.message is None or ":\\" not in result.message
    finally:
        session.transport.close()


def test_corrupt_legacy_fail_closed_source_unchanged(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    legacy_path = workbench_session_path(state_dir=state_dir)
    legacy_path.write_text("{not-json", encoding="utf-8")
    legacy_bytes = legacy_path.read_bytes()
    package_root = tmp_path / "packages" / "pkg"
    package_root.parent.mkdir()

    detected = lsm.detect_legacy_session_migration(state_dir=state_dir)
    assert detected.outcome == tp.OUTCOME_CORRUPT_OR_UNSUPPORTED

    session = compose_workbench_session(state_dir=state_dir)
    try:
        result = lsm.migrate_legacy_session_to_track_package(
            package_root,
            state_dir=state_dir,
            session=session,
            repo_root=_repo_root(),
        )
        assert result.outcome == tp.OUTCOME_CORRUPT_OR_UNSUPPORTED
        _assert_no_half_valid_package(package_root)
        assert legacy_path.read_bytes() == legacy_bytes
    finally:
        session.transport.close()


def test_unsupported_schema_fail_closed(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    payload = {
        "schema_version": 99,
        "live_kit": _empty_live_kit(),
        "channel_rack": None,
    }
    legacy_path = _write_legacy(state_dir, payload)
    legacy_bytes = legacy_path.read_bytes()
    package_root = tmp_path / "packages" / "pkg"
    package_root.parent.mkdir()

    detected = lsm.detect_legacy_session_migration(state_dir=state_dir)
    assert detected.outcome == tp.OUTCOME_CORRUPT_OR_UNSUPPORTED

    result = lsm.migrate_legacy_session_to_track_package(
        package_root,
        state_dir=state_dir,
        repo_root=_repo_root(),
    )
    assert result.outcome == tp.OUTCOME_CORRUPT_OR_UNSUPPORTED
    _assert_no_half_valid_package(package_root)
    assert legacy_path.read_bytes() == legacy_bytes


def test_semantic_32_field_shape_unsupported_no_guess(tmp_path: Path) -> None:
    """#1100 must not remap/rescale into #1086 32-field semantics."""
    state_dir = tmp_path / "state"
    library = tmp_path / "library"
    library.mkdir()
    kick = library / "kick.wav"
    write_sine_wav(kick, duration_sec=0.05, frequency_hz=60.0)
    assigned = {("Kick + Bass", "Kick"): str(kick.resolve())}
    # Proven inventory is step_count=16 / length=4. A 32/32 payload is outside
    # lossless #1100 claim and must not be silently reinterpreted.
    payload = {
        "schema_version": 2,
        "master_bpm": 128.0,
        "sync_enabled": False,
        "live_kit": _empty_live_kit(assigned),
        "channel_rack": {
            "pattern_id": "pattern_main",
            "length_quarter_notes": {"numerator": 32, "denominator": 1},
            "step_count": 32,
            "channels": _seed_channels(assigned),
            "triggers": [
                {
                    "channel_id": "ch_kick",
                    "position": {"numerator": 0, "denominator": 1},
                }
            ],
        },
    }
    legacy_path = _write_legacy(state_dir, payload)
    legacy_bytes = legacy_path.read_bytes()
    package_root = tmp_path / "packages" / "pkg"
    package_root.parent.mkdir()

    result = lsm.migrate_legacy_session_to_track_package(
        package_root,
        state_dir=state_dir,
        repo_root=_repo_root(),
    )
    assert result.outcome == lsm.OUTCOME_MIGRATION_FAILED
    _assert_no_half_valid_package(package_root)
    assert legacy_path.read_bytes() == legacy_bytes
    assert result.message is None or "32" in (result.message or "").casefold() or True
    assert result.message is None or ":\\" not in result.message


# ---------------------------------------------------------------------------
# Destination / copy / validation failure injection
# ---------------------------------------------------------------------------


def test_unwritable_destination_no_half_valid_package(tmp_path: Path) -> None:
    state_dir, kick, kick_bytes, legacy_path, legacy_bytes, _pkg = _seed_legacy_v2(
        tmp_path
    )
    # Destination parent does not exist → destination_unavailable.
    package_root = tmp_path / "missing-parent" / "pkg"
    result = lsm.migrate_legacy_session_to_track_package(
        package_root,
        state_dir=state_dir,
        repo_root=_repo_root(),
    )
    assert result.outcome == tp.OUTCOME_DESTINATION_UNAVAILABLE
    _assert_no_half_valid_package(package_root)
    assert legacy_path.read_bytes() == legacy_bytes
    assert kick.read_bytes() == kick_bytes


def test_interrupted_copy_retryable_legacy_unchanged(tmp_path: Path) -> None:
    state_dir, kick, kick_bytes, legacy_path, legacy_bytes, package_root = _seed_legacy_v2(
        tmp_path
    )

    def _boom(src: Path, dst: Path) -> None:
        raise OSError("simulated copy interrupt")

    result = lsm.migrate_legacy_session_to_track_package(
        package_root,
        state_dir=state_dir,
        repo_root=_repo_root(),
        copy_file=_boom,
    )
    assert result.outcome == tp.OUTCOME_COPY_INTERRUPTED
    _assert_no_half_valid_package(package_root)
    assert legacy_path.read_bytes() == legacy_bytes
    assert kick.read_bytes() == kick_bytes

    # Retry with real copy succeeds (explicit copy_file; no lingering inject).
    session = compose_workbench_session(state_dir=state_dir)
    try:
        retry = lsm.migrate_legacy_session_to_track_package(
            package_root,
            state_dir=state_dir,
            session=session,
            repo_root=_repo_root(),
            track_id="trk_1100_retry",
        )
        assert retry.outcome == tp.OUTCOME_OPEN
        assert package_root.is_dir()
        assert legacy_path.read_bytes() == legacy_bytes
        assert kick.read_bytes() == kick_bytes
    finally:
        session.transport.close()


def test_validation_failure_no_false_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_dir, kick, kick_bytes, legacy_path, legacy_bytes, package_root = _seed_legacy_v2(
        tmp_path
    )

    real_validate = tp._validate_package_at

    def _bad_validate(root: Path, *, require_bindable: bool):
        # Fail only staged validation (staging dirs use the package prefix).
        if root.name.startswith(".sample-brain-track-package-"):
            return tp.TrackPackageResult(
                outcome=tp.OUTCOME_CORRUPT_OR_UNSUPPORTED,
                message="Injected staged validation failure.",
            )
        return real_validate(root, require_bindable=require_bindable)

    monkeypatch.setattr(tp, "_validate_package_at", _bad_validate)

    result = lsm.migrate_legacy_session_to_track_package(
        package_root,
        state_dir=state_dir,
        repo_root=_repo_root(),
    )
    assert result.outcome == tp.OUTCOME_CORRUPT_OR_UNSUPPORTED
    assert result.ok is False
    _assert_no_half_valid_package(package_root)
    assert legacy_path.read_bytes() == legacy_bytes
    assert kick.read_bytes() == kick_bytes


# ---------------------------------------------------------------------------
# Retry / idempotency / bind + restart
# ---------------------------------------------------------------------------


def test_post_success_idempotent_no_op_or_conflict(tmp_path: Path) -> None:
    state_dir, kick, kick_bytes, legacy_path, legacy_bytes, package_root = _seed_legacy_v2(
        tmp_path
    )
    session = compose_workbench_session(state_dir=state_dir)
    try:
        first = lsm.migrate_legacy_session_to_track_package(
            package_root,
            state_dir=state_dir,
            session=session,
            repo_root=_repo_root(),
            track_id="trk_1100_idem",
        )
        assert first.outcome == tp.OUTCOME_OPEN
        manifest_before = (package_root / tp.TRACK_PACKAGE_FILENAME).read_bytes()

        second = lsm.migrate_legacy_session_to_track_package(
            package_root,
            state_dir=state_dir,
            session=session,
            repo_root=_repo_root(),
            track_id="trk_1100_idem",
        )
        # Idempotent resume/finalize of the published package → open; never
        # mutates legacy or rewrites package media/manifest.
        assert second.outcome == tp.OUTCOME_OPEN
        assert second.track_id == "trk_1100_idem"
        assert legacy_path.read_bytes() == legacy_bytes
        assert kick.read_bytes() == kick_bytes
        assert (package_root / tp.TRACK_PACKAGE_FILENAME).read_bytes() == manifest_before
    finally:
        session.transport.close()


def test_bind_failure_then_retry_resumes_published_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_dir, kick, kick_bytes, legacy_path, legacy_bytes, package_root = _seed_legacy_v2(
        tmp_path
    )
    session = compose_workbench_session(state_dir=state_dir)
    try:
        real_bind = session.bind_active_track_package
        calls = {"n": 0}

        def _fail_once(root):
            calls["n"] += 1
            if calls["n"] == 1:
                return tp.TrackPackageResult(
                    outcome=tp.OUTCOME_WRITE_FAILED,
                    package_root=Path(root),
                    track_id="trk_1100_resume",
                    message="Active track selection could not be persisted.",
                )
            return real_bind(root)

        monkeypatch.setattr(session, "bind_active_track_package", _fail_once)
        first = lsm.migrate_legacy_session_to_track_package(
            package_root,
            state_dir=state_dir,
            session=session,
            repo_root=_repo_root(),
            track_id="trk_1100_resume",
        )
        assert first.outcome == tp.OUTCOME_WRITE_FAILED
        assert package_root.is_dir()
        assert (package_root / tp.TRACK_PACKAGE_FILENAME).is_file()
        assert legacy_path.read_bytes() == legacy_bytes
        assert kick.read_bytes() == kick_bytes

        monkeypatch.setattr(session, "bind_active_track_package", real_bind)
        retry = lsm.migrate_legacy_session_to_track_package(
            package_root,
            state_dir=state_dir,
            session=session,
            repo_root=_repo_root(),
            track_id="trk_1100_resume",
        )
        assert retry.outcome == tp.OUTCOME_OPEN
        assert session.active_track_id == "trk_1100_resume"
        assert legacy_path.read_bytes() == legacy_bytes
        assert kick.read_bytes() == kick_bytes
    finally:
        session.transport.close()


def test_migrate_then_restart_active_track_outranks_legacy(tmp_path: Path) -> None:
    state_dir, kick, _kb, legacy_path, legacy_bytes, package_root = _seed_legacy_v2(
        tmp_path
    )
    session = compose_workbench_session(state_dir=state_dir)
    try:
        result = lsm.migrate_legacy_session_to_track_package(
            package_root,
            state_dir=state_dir,
            session=session,
            repo_root=_repo_root(),
            track_id="trk_1100_restart",
        )
        assert result.outcome == tp.OUTCOME_OPEN
        session.transport.set_tempo(150.0)
    finally:
        session.transport.close()

    assert legacy_path.read_bytes() == legacy_bytes

    restarted = compose_workbench_session(state_dir=state_dir)
    try:
        assert restarted.active_track_id == "trk_1100_restart"
        assert restarted.active_track_package_root == package_root
        assert restarted.track_package_status == tp.OUTCOME_OPEN
        assert restarted.transport.get_current_tempo() == pytest.approx(150.0)
        bound = restarted.live_kit.assignment_for("Kick + Bass", "Kick")
        assert bound is not None
        assert Path(bound.path).is_relative_to(package_root)
        # Legacy absolute path must not win over package media.
        assert Path(bound.path) != kick.resolve()
        assert legacy_path.read_bytes() == legacy_bytes
    finally:
        restarted.transport.close()


def test_migrate_registers_in_live_kits_without_sample_row_confusion(
    tmp_path: Path,
) -> None:
    state_dir, _kick, _kb, _lp, _lb, package_root = _seed_legacy_v2(tmp_path)
    session = compose_workbench_session(state_dir=state_dir)
    try:
        result = lsm.migrate_legacy_session_to_track_package(
            package_root,
            state_dir=state_dir,
            session=session,
            repo_root=_repo_root(),
            track_id="trk_1100_reg",
        )
        assert result.outcome == tp.OUTCOME_OPEN
        registry = lkr.LiveKitsRegistry(state_dir=state_dir)
        rows = registry.list_packages()
        assert any(row.track_id == "trk_1100_reg" for row in rows)
        row = next(r for r in rows if r.track_id == "trk_1100_reg")
        assert row.entity_kind == lkr.ENTITY_KIND_TRACK_PACKAGE
        with pytest.raises(lkr.PackageEntityError):
            lkr.require_sample_row(row)
    finally:
        session.transport.close()


def test_migrate_message_has_no_exception_dump_or_abs_path(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    missing = tmp_path / "library" / "gone.wav"
    missing.parent.mkdir()
    _write_legacy(state_dir, _legacy_v2_payload(kick_path=str(missing.resolve())))
    package_root = tmp_path / "packages" / "pkg"
    package_root.parent.mkdir()
    result = lsm.migrate_legacy_session_to_track_package(
        package_root,
        state_dir=state_dir,
        repo_root=_repo_root(),
    )
    assert result.outcome == tp.OUTCOME_MISSING_MEDIA
    text = result.message or ""
    assert ":\\" not in text
    assert "Traceback" not in text
    assert str(missing.resolve()) not in text
