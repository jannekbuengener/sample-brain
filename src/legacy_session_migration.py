"""Explicit non-destructive legacy workbench_session.json → track package (#1100).

Detection is query-only. Migration/claim is an explicit API — never auto-run on
compose/app start. Reuses track package create (#1096), active-track bind
(#1098), and Live Kits registration (#1099). Legacy file bytes are never
deleted, overwritten, truncated, or renamed by this module.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .channel_rack import DEFAULT_PATTERN_LENGTH, DEFAULT_STEP_COUNT
from .live_kits_registry import OUTCOME_READY, LiveKitsRegistry
from .track_package import (
    OUTCOME_COPY_INTERRUPTED,
    OUTCOME_CORRUPT_OR_UNSUPPORTED,
    OUTCOME_DESTINATION_UNAVAILABLE,
    OUTCOME_MISSING_MEDIA,
    OUTCOME_OPEN,
    OUTCOME_PATH_ESCAPE_REJECTED,
    OUTCOME_WRITE_FAILED,
    CopyFileFn,
    TrackPackageDraft,
    TrackPackageMediaSource,
    TrackPackageResult,
    create_track_package,
    open_track_package,
)
from .workbench_live_kit import LIVE_KIT_SLOT_MAPPING
from .workbench_session import WorkbenchSession
from .workbench_session_store import (
    PERSISTENCE_STATUS_FRESH_MISSING,
    PERSISTENCE_STATUS_REJECTED_CORRUPT,
    PERSISTENCE_STATUS_REJECTED_SCHEMA,
    PERSISTENCE_STATUS_REJECTED_SEMANTIC,
    PERSISTENCE_STATUS_RESTORED_OK,
    WorkbenchSessionSnapshot,
    load_active_track_pointer,
    load_workbench_session_outcome,
    track_package_musical_from_snapshot,
    workbench_session_path,
)

OUTCOME_DRAFT = "draft"
OUTCOME_MIGRATION_REQUIRED = "migration_required"
OUTCOME_MIGRATION_FAILED = "migration_failed"

_SAFE_MESSAGES = {
    OUTCOME_DRAFT: "No legacy workbench session to migrate.",
    OUTCOME_MIGRATION_REQUIRED: "Legacy workbench session requires explicit migration.",
    OUTCOME_MIGRATION_FAILED: "Legacy session timing shape is unsupported for lossless migration.",
    OUTCOME_OPEN: "Legacy session migrated into track package.",
    OUTCOME_MISSING_MEDIA: "Legacy session media is missing.",
    OUTCOME_CORRUPT_OR_UNSUPPORTED: "Legacy session is corrupt or unsupported.",
    OUTCOME_DESTINATION_UNAVAILABLE: "Track package destination is unavailable.",
    OUTCOME_COPY_INTERRUPTED: "Media copy was interrupted.",
    OUTCOME_WRITE_FAILED: "Track package write failed.",
    OUTCOME_PATH_ESCAPE_REJECTED: "Package media path escape rejected.",
}

# Proven legacy Channel Rack shape from live session store / #809 inventory.
_LEGACY_RACK_STEP_COUNT = DEFAULT_STEP_COUNT
_LEGACY_RACK_LENGTH = DEFAULT_PATTERN_LENGTH


@dataclass(frozen=True)
class LegacyMigrationResult:
    """Lifecycle outcome for detect/migrate (no private paths or dumps)."""

    outcome: str
    package_root: Path | None = None
    track_id: str | None = None
    message: str | None = None

    @property
    def ok(self) -> bool:
        return self.outcome == OUTCOME_OPEN


def _safe_message(outcome: str, fallback: str | None = None) -> str:
    if fallback:
        text = fallback.strip()
        if (
            text
            and ":\\" not in text
            and "\\\\" not in text
            and "/Users/" not in text
            and "Traceback" not in text
            and not (len(text) >= 2 and text[1] == ":")
            and not text.startswith("/")
        ):
            return text
    return _SAFE_MESSAGES.get(outcome, "Legacy migration failed.")


def _result(
    outcome: str,
    *,
    package_root: Path | None = None,
    track_id: str | None = None,
    message: str | None = None,
) -> LegacyMigrationResult:
    return LegacyMigrationResult(
        outcome=outcome,
        package_root=package_root,
        track_id=track_id,
        message=_safe_message(outcome, message),
    )


def _legacy_bytes(state_dir: Path | None, env: Mapping[str, str] | None) -> bytes | None:
    path = workbench_session_path(state_dir=state_dir, env=env)
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError:
        return None


def _assert_legacy_unchanged(
    state_dir: Path | None,
    env: Mapping[str, str] | None,
    before: bytes | None,
) -> None:
    """Internal invariant helper for tests/callers; never mutates the file."""
    after = _legacy_bytes(state_dir, env)
    if before != after:
        # Programming error only — migration must never alter legacy bytes.
        raise RuntimeError("Legacy session bytes changed during migration")


def detect_legacy_session_migration(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> LegacyMigrationResult:
    """Query-only detection. Never creates packages or mutates legacy state."""
    outcome = load_workbench_session_outcome(state_dir=state_dir, env=env)
    if outcome.status == PERSISTENCE_STATUS_FRESH_MISSING:
        return _result(OUTCOME_DRAFT)
    if outcome.status == PERSISTENCE_STATUS_RESTORED_OK and outcome.snapshot is not None:
        return _result(OUTCOME_MIGRATION_REQUIRED)
    return _result(OUTCOME_CORRUPT_OR_UNSUPPORTED)


def _collect_absolute_media_paths(snapshot: WorkbenchSessionSnapshot) -> list[Path]:
    ordered: list[Path] = []
    seen: set[str] = set()
    for group, slots in LIVE_KIT_SLOT_MAPPING:
        for slot in slots:
            path_text = snapshot.live_kit[group][slot]
            if path_text is None:
                continue
            key = str(Path(path_text))
            if key in seen:
                continue
            seen.add(key)
            ordered.append(Path(path_text))
    if snapshot.channel_rack is not None:
        for channel in snapshot.channel_rack.channels:
            if channel.sample_path is None:
                continue
            key = str(Path(channel.sample_path))
            if key in seen:
                continue
            seen.add(key)
            ordered.append(Path(channel.sample_path))
    return ordered


def _legacy_rack_is_migratable(snapshot: WorkbenchSessionSnapshot) -> bool:
    """Only proven 16-step / 1-bar rack shapes migrate losslessly under #1100.

    Shapes that require #1086 32-field / 8-bar reinterpretation are held.
    ``channel_rack is None`` is migratable (kit + clock only).
    """
    rack = snapshot.channel_rack
    if rack is None:
        return True
    if rack.step_count != _LEGACY_RACK_STEP_COUNT:
        return False
    if rack.pattern.length_quarter_notes != _LEGACY_RACK_LENGTH:
        return False
    return True


def _media_missing(paths: list[Path]) -> bool:
    for path in paths:
        try:
            if not path.is_file():
                return True
            with path.open("rb") as handle:
                handle.read(1)
        except OSError:
            return True
    return False


def _already_migrated_open(
    *,
    state_dir: Path | None,
    env: Mapping[str, str] | None,
    package_root: Path,
    session: WorkbenchSession | None,
) -> LegacyMigrationResult | None:
    """Idempotent path when destination already holds a valid bound package."""
    if not package_root.exists():
        return None
    opened = open_track_package(package_root)
    if opened.outcome != OUTCOME_OPEN or opened.track_id is None:
        return _result(
            OUTCOME_DESTINATION_UNAVAILABLE,
            package_root=package_root,
            message="Package destination already exists.",
        )

    present, pointer = load_active_track_pointer(state_dir=state_dir, env=env)
    pointer_matches = False
    if present and pointer is not None:
        try:
            pointer_matches = (
                pointer.track_id == opened.track_id
                and pointer.package_root.resolve(strict=False)
                == package_root.resolve(strict=False)
            )
        except (OSError, RuntimeError, ValueError):
            pointer_matches = False

    session_matches = False
    if session is not None and session.active_track_id == opened.track_id:
        try:
            if session.active_track_package_root is not None:
                session_matches = (
                    session.active_track_package_root.resolve(strict=False)
                    == package_root.resolve(strict=False)
                )
        except (OSError, RuntimeError, ValueError):
            session_matches = False

    if pointer_matches or session_matches:
        if session is not None and not session_matches:
            bound = session.bind_active_track_package(package_root)
            if bound.outcome != OUTCOME_OPEN:
                return _result(
                    bound.outcome,
                    package_root=package_root,
                    track_id=opened.track_id,
                    message=bound.message,
                )
        return _result(
            OUTCOME_OPEN,
            package_root=package_root,
            track_id=opened.track_id,
            message="Legacy session already migrated.",
        )
    return _result(
        OUTCOME_DESTINATION_UNAVAILABLE,
        package_root=package_root,
        track_id=opened.track_id,
        message="Package destination already exists.",
    )


def migrate_legacy_session_to_track_package(
    package_root: Path | str,
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
    session: WorkbenchSession | None = None,
    repo_root: Path | None = None,
    copy_file: CopyFileFn | None = None,
    track_id: str | None = None,
) -> LegacyMigrationResult:
    """Explicit claim: legacy resume → staged package → optional bind/register.

    On every failure path the legacy ``workbench_session.json`` bytes remain
    identical and no half-valid final package is published.
    """
    try:
        final_root = Path(package_root).expanduser()
    except (OSError, RuntimeError, ValueError):
        return _result(OUTCOME_DESTINATION_UNAVAILABLE)

    legacy_before = _legacy_bytes(state_dir, env)

    idempotent = _already_migrated_open(
        state_dir=state_dir,
        env=env,
        package_root=final_root,
        session=session,
    )
    if idempotent is not None:
        _assert_legacy_unchanged(state_dir, env, legacy_before)
        return idempotent

    load = load_workbench_session_outcome(state_dir=state_dir, env=env)
    if load.status == PERSISTENCE_STATUS_FRESH_MISSING:
        return _result(OUTCOME_DRAFT)
    if load.status in {
        PERSISTENCE_STATUS_REJECTED_CORRUPT,
        PERSISTENCE_STATUS_REJECTED_SCHEMA,
        PERSISTENCE_STATUS_REJECTED_SEMANTIC,
    }:
        _assert_legacy_unchanged(state_dir, env, legacy_before)
        return _result(OUTCOME_CORRUPT_OR_UNSUPPORTED)
    if load.status != PERSISTENCE_STATUS_RESTORED_OK or load.snapshot is None:
        _assert_legacy_unchanged(state_dir, env, legacy_before)
        return _result(OUTCOME_CORRUPT_OR_UNSUPPORTED)

    snapshot = load.snapshot
    if not _legacy_rack_is_migratable(snapshot):
        _assert_legacy_unchanged(state_dir, env, legacy_before)
        return _result(
            OUTCOME_MIGRATION_FAILED,
            message=(
                "Legacy pattern timing requires Arrangement 32-field migration "
                "(unsupported by this claim path)."
            ),
        )

    media_paths = _collect_absolute_media_paths(snapshot)
    if not media_paths:
        _assert_legacy_unchanged(state_dir, env, legacy_before)
        return _result(
            OUTCOME_MIGRATION_FAILED,
            message="Legacy session has no media to package.",
        )
    if _media_missing(media_paths):
        _assert_legacy_unchanged(state_dir, env, legacy_before)
        return _result(OUTCOME_MISSING_MEDIA)

    musical: Mapping[str, Any] = track_package_musical_from_snapshot(snapshot)
    draft = TrackPackageDraft(
        media_sources=tuple(
            TrackPackageMediaSource(source_path=path) for path in media_paths
        ),
        musical=musical,
        track_id=track_id,
    )
    created: TrackPackageResult = create_track_package(
        draft,
        final_root,
        repo_root=repo_root,
        copy_file=copy_file,
    )
    if created.outcome != OUTCOME_OPEN or created.package_root is None:
        _assert_legacy_unchanged(state_dir, env, legacy_before)
        return _result(
            created.outcome,
            package_root=None,
            track_id=created.track_id,
            message=created.message,
        )

    # Register (list only) then bind active track via existing owners.
    registry = LiveKitsRegistry(state_dir=state_dir, env=env)
    registered = registry.register(created.package_root)
    if registered.outcome != OUTCOME_READY:
        # Package may already be published; never touch legacy bytes.
        _assert_legacy_unchanged(state_dir, env, legacy_before)
        return _result(
            OUTCOME_WRITE_FAILED
            if registered.outcome == OUTCOME_WRITE_FAILED
            else registered.outcome,
            package_root=created.package_root,
            track_id=created.track_id,
            message=registered.message,
        )

    if session is not None:
        bound = session.bind_active_track_package(created.package_root)
        if bound.outcome != OUTCOME_OPEN:
            _assert_legacy_unchanged(state_dir, env, legacy_before)
            return _result(
                bound.outcome,
                package_root=created.package_root,
                track_id=created.track_id,
                message=bound.message,
            )

    _assert_legacy_unchanged(state_dir, env, legacy_before)
    return _result(
        OUTCOME_OPEN,
        package_root=created.package_root,
        track_id=created.track_id,
        message=created.message,
    )


__all__ = [
    "OUTCOME_COPY_INTERRUPTED",
    "OUTCOME_CORRUPT_OR_UNSUPPORTED",
    "OUTCOME_DESTINATION_UNAVAILABLE",
    "OUTCOME_DRAFT",
    "OUTCOME_MIGRATION_FAILED",
    "OUTCOME_MIGRATION_REQUIRED",
    "OUTCOME_MISSING_MEDIA",
    "OUTCOME_OPEN",
    "OUTCOME_PATH_ESCAPE_REJECTED",
    "OUTCOME_WRITE_FAILED",
    "LegacyMigrationResult",
    "detect_legacy_session_migration",
    "migrate_legacy_session_to_track_package",
]
