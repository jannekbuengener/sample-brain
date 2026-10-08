"""Python-owned track package core (#1085A / #1082 contract).

Owns runtime ``track_package.json`` schema v1, staged create, path confinement,
and explicit validate/open. Does not own Browser registration, legacy session
migration, autosave wiring, or a second musical session authority.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any
import uuid

SCHEMA_VERSION = 1
PACKAGE_KIND = "sample_brain_track_package"
TRACK_PACKAGE_FILENAME = "track_package.json"
MEDIA_DIR_NAME = "media"
TRACK_ID_PREFIX = "trk_"
MEDIA_ID_PREFIX = "m_"

OUTCOME_OPEN = "open"
OUTCOME_MISSING_MEDIA = "missing_media"
OUTCOME_CORRUPT_OR_UNSUPPORTED = "corrupt_or_unsupported"
OUTCOME_DESTINATION_UNAVAILABLE = "destination_unavailable"
OUTCOME_COPY_INTERRUPTED = "copy_interrupted"
OUTCOME_WRITE_FAILED = "write_failed"
OUTCOME_PATH_ESCAPE_REJECTED = "path_escape_rejected"

_STAGING_PREFIX = ".sample-brain-track-package-"
_UNSAFE_FILENAME = re.compile(r"[^a-z0-9._-]+")
_DRIVE_ABS = re.compile(r"^[a-zA-Z]:[/\\]")
_UNC = re.compile(r"^(\\\\|//)")
_FILE_URI = re.compile(r"^file:", re.IGNORECASE)

_REQUIRED_ROOT_FIELDS = frozenset(
    {"schema_version", "package_kind", "track_id", "media", "musical"}
)
_REQUIRED_MUSICAL_FIELDS = frozenset(
    {"live_kit", "channel_rack", "master_bpm", "sync_enabled"}
)

CopyFileFn = Callable[[Path, Path], None]


@dataclass(frozen=True)
class MediaEntry:
    media_id: str
    relpath: str


@dataclass(frozen=True)
class TrackPackageMediaSource:
    source_path: Path
    media_id: str | None = None


@dataclass(frozen=True)
class TrackPackageDraft:
    """Create input: required media sources + portable musical payload draft."""

    media_sources: tuple[TrackPackageMediaSource, ...]
    musical: Mapping[str, Any]
    track_id: str | None = None
    arrangement: Any | None = None
    midi: Any | None = None


@dataclass(frozen=True)
class TrackPackageManifest:
    schema_version: int
    package_kind: str
    track_id: str
    media: tuple[MediaEntry, ...]
    musical: Mapping[str, Any]
    arrangement: Any | None = None
    midi: Any | None = None


@dataclass(frozen=True)
class TrackPackageResult:
    """Pure create/open/validate outcome (no global active-track side effects)."""

    outcome: str
    package_root: Path | None = None
    track_id: str | None = None
    manifest: TrackPackageManifest | None = None
    message: str | None = None

    @property
    def ok(self) -> bool:
        return self.outcome == OUTCOME_OPEN


def new_track_id() -> str:
    """Allocate an opaque package-local track id (stdlib uuid, no machine info)."""
    return f"{TRACK_ID_PREFIX}{uuid.uuid4().hex}"


def new_media_id() -> str:
    return f"{MEDIA_ID_PREFIX}{uuid.uuid4().hex}"


def default_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def destination_inside_repository(
    destination: Path,
    *,
    repo_root: Path | None = None,
) -> bool:
    """True when destination resolves inside the repository checkout."""
    root = (repo_root if repo_root is not None else default_repo_root()).resolve()
    try:
        target = destination.expanduser().resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return False
    try:
        target.relative_to(root)
    except ValueError:
        return False
    return True


def _failure(
    outcome: str,
    *,
    package_root: Path | None = None,
    track_id: str | None = None,
    message: str | None = None,
) -> TrackPackageResult:
    return TrackPackageResult(
        outcome=outcome,
        package_root=package_root,
        track_id=track_id,
        message=message,
    )


def _success_open(
    package_root: Path,
    manifest: TrackPackageManifest,
) -> TrackPackageResult:
    return TrackPackageResult(
        outcome=OUTCOME_OPEN,
        package_root=package_root,
        track_id=manifest.track_id,
        manifest=manifest,
    )


def _posix_relpath(value: str) -> str:
    return str(value).replace("\\", "/")


def _looks_like_forbidden_ref(relpath: str) -> bool:
    text = _posix_relpath(relpath.strip())
    if not text:
        return True
    if _FILE_URI.match(text):
        return True
    if _UNC.match(text):
        return True
    if _DRIVE_ABS.match(text):
        return True
    if text.startswith("/"):
        return True
    parts = [p for p in text.split("/") if p not in ("", ".")]
    if any(part == ".." for part in parts):
        return True
    if ".." in text:
        return True
    return False


def validate_confined_media_relpath(
    relpath: str,
    package_root: Path,
    *,
    require_under_media: bool = True,
) -> str | None:
    """Return a lifecycle outcome when *relpath* escapes; else ``None``."""
    if not isinstance(relpath, str):
        return OUTCOME_CORRUPT_OR_UNSUPPORTED
    text = _posix_relpath(relpath)
    if _looks_like_forbidden_ref(text):
        return OUTCOME_PATH_ESCAPE_REJECTED
    if require_under_media and not text.startswith(f"{MEDIA_DIR_NAME}/"):
        return OUTCOME_PATH_ESCAPE_REJECTED
    if text.rstrip("/") == MEDIA_DIR_NAME:
        return OUTCOME_PATH_ESCAPE_REJECTED

    root = package_root.resolve(strict=False)
    candidate = (package_root / Path(*text.split("/"))).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError:
        return OUTCOME_PATH_ESCAPE_REJECTED

    # If the path exists, resolve again after following links / reparse points.
    if candidate.exists() or (package_root / Path(*text.split("/"))).exists():
        try:
            resolved = (package_root / Path(*text.split("/"))).resolve(strict=True)
        except (OSError, RuntimeError, ValueError):
            return OUTCOME_PATH_ESCAPE_REJECTED
        try:
            resolved.relative_to(root)
        except ValueError:
            return OUTCOME_PATH_ESCAPE_REJECTED
        # Reject when any path component is a symlink/junction that escapes.
        probe = package_root
        for part in text.split("/"):
            probe = probe / part
            if not probe.exists():
                break
            try:
                if probe.is_symlink():
                    link_target = probe.resolve(strict=True)
                    try:
                        link_target.relative_to(root)
                    except ValueError:
                        return OUTCOME_PATH_ESCAPE_REJECTED
            except OSError:
                return OUTCOME_PATH_ESCAPE_REJECTED
    return None


def _sanitize_suffix(source_path: Path) -> str:
    suffix = source_path.suffix.casefold()
    if not suffix.startswith("."):
        suffix = f".{suffix}" if suffix else ".wav"
    body = re.sub(r"[^a-z0-9]", "", suffix[1:])
    return f".{body}" if body else ".wav"


def _media_relpath_for(media_id: str, source_path: Path) -> str:
    safe_id = _UNSAFE_FILENAME.sub("-", media_id.strip().casefold()).strip("-") or "media"
    return f"{MEDIA_DIR_NAME}/{safe_id}{_sanitize_suffix(source_path)}"


def serialize_track_package_json(manifest: TrackPackageManifest) -> str:
    """Deterministic UTF-8 JSON document for ``track_package.json``."""
    media_sorted = sorted(manifest.media, key=lambda entry: entry.media_id)
    payload: dict[str, Any] = {
        "schema_version": int(manifest.schema_version),
        "package_kind": str(manifest.package_kind),
        "track_id": str(manifest.track_id),
        "media": [
            {"media_id": entry.media_id, "relpath": _posix_relpath(entry.relpath)}
            for entry in media_sorted
        ],
        "musical": manifest.musical,
    }
    if manifest.arrangement is not None:
        payload["arrangement"] = manifest.arrangement
    if manifest.midi is not None:
        payload["midi"] = manifest.midi
    return json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"


def _rewrite_paths(value: Any, path_map: Mapping[str, str]) -> Any:
    if isinstance(value, str):
        key = value
        mapped = path_map.get(key)
        if mapped is not None:
            return mapped
        try:
            mapped = path_map.get(str(Path(value).resolve()))
        except (OSError, RuntimeError, ValueError):
            mapped = None
        return mapped if mapped is not None else value
    if isinstance(value, list):
        return [_rewrite_paths(item, path_map) for item in value]
    if isinstance(value, Mapping):
        return {str(k): _rewrite_paths(v, path_map) for k, v in value.items()}
    return value


def _normalize_source_key(path: Path) -> str:
    return str(path.expanduser().resolve(strict=False))


def _validate_draft_sources(
    draft: TrackPackageDraft,
) -> tuple[list[tuple[str, Path]], str | None]:
    planned: list[tuple[str, Path]] = []
    seen_ids: set[str] = set()
    for item in draft.media_sources:
        media_id = item.media_id or new_media_id()
        if media_id in seen_ids:
            return [], OUTCOME_CORRUPT_OR_UNSUPPORTED
        seen_ids.add(media_id)
        source = Path(item.source_path)
        if not source.exists() or not source.is_file():
            return [], OUTCOME_MISSING_MEDIA
        try:
            with source.open("rb") as handle:
                handle.read(1)
        except OSError:
            return [], OUTCOME_MISSING_MEDIA
        planned.append((media_id, source))
    if not planned:
        return [], OUTCOME_CORRUPT_OR_UNSUPPORTED
    musical = draft.musical
    if not isinstance(musical, Mapping):
        return [], OUTCOME_CORRUPT_OR_UNSUPPORTED
    missing = _REQUIRED_MUSICAL_FIELDS - set(musical.keys())
    if missing:
        return [], OUTCOME_CORRUPT_OR_UNSUPPORTED
    return planned, None


def _validate_destination_eligibility(
    package_root: Path,
    *,
    repo_root: Path | None,
) -> str | None:
    try:
        root = package_root.expanduser()
    except (OSError, RuntimeError, ValueError):
        return OUTCOME_DESTINATION_UNAVAILABLE
    if destination_inside_repository(root, repo_root=repo_root):
        return OUTCOME_DESTINATION_UNAVAILABLE
    parent = root.parent
    if not parent.exists() or not parent.is_dir():
        return OUTCOME_DESTINATION_UNAVAILABLE
    if root.exists():
        return OUTCOME_DESTINATION_UNAVAILABLE
    probe = parent / ".sample-brain-track-package-probe"
    try:
        with probe.open("wb") as handle:
            handle.write(b"ok")
        probe.unlink(missing_ok=True)
    except OSError:
        probe.unlink(missing_ok=True)
        return OUTCOME_DESTINATION_UNAVAILABLE
    return None


def _remove_own_staging(path: Path) -> None:
    name = path.name
    if not name.startswith(_STAGING_PREFIX):
        return
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def _default_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def create_track_package(
    draft: TrackPackageDraft,
    package_root: Path | str,
    *,
    repo_root: Path | None = None,
    copy_file: CopyFileFn | None = None,
) -> TrackPackageResult:
    """Staged create transaction ending in lifecycle ``open`` on success.

    Stage 9 (active-track bind) is represented only as a pure result object for
    this slice; no global Workbench active-track owner is mutated here.
    """
    final_root = Path(package_root)
    dest_error = _validate_destination_eligibility(final_root, repo_root=repo_root)
    if dest_error is not None:
        return _failure(dest_error, message="Package destination is unavailable.")

    planned, draft_error = _validate_draft_sources(draft)
    if draft_error is not None:
        return _failure(draft_error, message="Draft or media is not eligible.")

    track_id = draft.track_id or new_track_id()
    if not isinstance(track_id, str) or not track_id.strip():
        return _failure(
            OUTCOME_CORRUPT_OR_UNSUPPORTED,
            message="track_id is invalid.",
        )
    track_id = track_id.strip()

    copy_fn = copy_file or _default_copy
    parent = final_root.parent
    staging: Path | None = None
    try:
        staging = Path(
            tempfile.mkdtemp(prefix=_STAGING_PREFIX, dir=str(parent))
        )
        media_root = staging / MEDIA_DIR_NAME
        media_root.mkdir(parents=True, exist_ok=True)

        path_map: dict[str, str] = {}
        media_entries: list[MediaEntry] = []
        for media_id, source in planned:
            relpath = _media_relpath_for(media_id, source)
            target = staging / Path(*relpath.split("/"))
            try:
                copy_fn(source, target)
            except OSError:
                _remove_own_staging(staging)
                staging = None
                return _failure(
                    OUTCOME_COPY_INTERRUPTED,
                    message="Media copy was interrupted.",
                )
            if not target.is_file():
                _remove_own_staging(staging)
                staging = None
                return _failure(
                    OUTCOME_COPY_INTERRUPTED,
                    message="Copied media validation failed.",
                )
            try:
                if target.read_bytes() != source.read_bytes():
                    _remove_own_staging(staging)
                    staging = None
                    return _failure(
                        OUTCOME_COPY_INTERRUPTED,
                        message="Copied media validation failed.",
                    )
            except OSError:
                _remove_own_staging(staging)
                staging = None
                return _failure(
                    OUTCOME_COPY_INTERRUPTED,
                    message="Copied media validation failed.",
                )
            escape = validate_confined_media_relpath(relpath, staging)
            if escape is not None:
                _remove_own_staging(staging)
                staging = None
                return _failure(escape, message="Media path escape rejected.")
            media_entries.append(MediaEntry(media_id=media_id, relpath=relpath))
            path_map[_normalize_source_key(source)] = relpath
            path_map[str(source)] = relpath
            path_map[str(source.resolve())] = relpath

        musical = _rewrite_paths(dict(draft.musical), path_map)
        manifest = TrackPackageManifest(
            schema_version=SCHEMA_VERSION,
            package_kind=PACKAGE_KIND,
            track_id=track_id,
            media=tuple(media_entries),
            musical=musical,
            arrangement=draft.arrangement,
            midi=draft.midi,
        )
        document = serialize_track_package_json(manifest)
        if _contains_forbidden_serialized_path(document):
            _remove_own_staging(staging)
            staging = None
            return _failure(
                OUTCOME_CORRUPT_OR_UNSUPPORTED,
                message="Package payload is not portable.",
            )
        try:
            (staging / TRACK_PACKAGE_FILENAME).write_text(document, encoding="utf-8")
        except OSError:
            _remove_own_staging(staging)
            staging = None
            return _failure(OUTCOME_WRITE_FAILED, message="Package write failed.")

        staged_check = _validate_package_at(staging, require_bindable=True)
        if staged_check.outcome != OUTCOME_OPEN or staged_check.manifest is None:
            _remove_own_staging(staging)
            staging = None
            return _failure(
                staged_check.outcome
                if staged_check.outcome != OUTCOME_OPEN
                else OUTCOME_CORRUPT_OR_UNSUPPORTED,
                message=staged_check.message or "Staged package invalid.",
            )

        if final_root.exists():
            _remove_own_staging(staging)
            staging = None
            return _failure(
                OUTCOME_DESTINATION_UNAVAILABLE,
                message="Package destination already exists.",
            )
        try:
            os.replace(staging, final_root)
            staging = None
        except OSError:
            if staging is not None:
                _remove_own_staging(staging)
                staging = None
            if final_root.exists():
                # Never leave a half-valid visible package from our commit.
                # Only remove if it still looks like our incomplete publish.
                _cleanup_failed_final(final_root)
            return _failure(OUTCOME_WRITE_FAILED, message="Package commit failed.")
    except OSError:
        if staging is not None:
            _remove_own_staging(staging)
        return _failure(OUTCOME_WRITE_FAILED, message="Package create failed.")

    opened = open_track_package(final_root)
    if opened.outcome != OUTCOME_OPEN:
        return opened
    return _success_open(final_root, opened.manifest)  # type: ignore[arg-type]


def _cleanup_failed_final(final_root: Path) -> None:
    """Remove a final root only when it is our incomplete publish attempt."""
    try:
        names = {p.name for p in final_root.iterdir()}
    except OSError:
        return
    allowed = {TRACK_PACKAGE_FILENAME, MEDIA_DIR_NAME}
    if names and names.issubset(allowed):
        shutil.rmtree(final_root, ignore_errors=True)


def _contains_forbidden_serialized_path(document: str) -> bool:
    if "file://" in document.casefold():
        return True
    if "\\\\" in document:
        return True
    # Absolute Windows drive path fragments inside JSON string values.
    if re.search(r"[A-Za-z]:\\\\", document) or re.search(r"[A-Za-z]:/", document):
        return True
    return False


def _parse_manifest_payload(data: object) -> tuple[TrackPackageManifest | None, str]:
    if not isinstance(data, dict):
        return None, OUTCOME_CORRUPT_OR_UNSUPPORTED
    if not _REQUIRED_ROOT_FIELDS.issubset(data.keys()):
        return None, OUTCOME_CORRUPT_OR_UNSUPPORTED
    try:
        schema_version = data["schema_version"]
        if not isinstance(schema_version, int) or isinstance(schema_version, bool):
            return None, OUTCOME_CORRUPT_OR_UNSUPPORTED
        if schema_version != SCHEMA_VERSION:
            return None, OUTCOME_CORRUPT_OR_UNSUPPORTED
        package_kind = data["package_kind"]
        if package_kind != PACKAGE_KIND:
            return None, OUTCOME_CORRUPT_OR_UNSUPPORTED
        track_id = data["track_id"]
        if not isinstance(track_id, str) or not track_id.strip():
            return None, OUTCOME_CORRUPT_OR_UNSUPPORTED
        media_raw = data["media"]
        if not isinstance(media_raw, list):
            return None, OUTCOME_CORRUPT_OR_UNSUPPORTED
        musical = data["musical"]
        if not isinstance(musical, Mapping):
            return None, OUTCOME_CORRUPT_OR_UNSUPPORTED
        if not _REQUIRED_MUSICAL_FIELDS.issubset(musical.keys()):
            return None, OUTCOME_CORRUPT_OR_UNSUPPORTED
    except (KeyError, TypeError, ValueError):
        return None, OUTCOME_CORRUPT_OR_UNSUPPORTED

    media_entries: list[MediaEntry] = []
    seen_ids: set[str] = set()
    seen_relpaths: set[str] = set()
    for item in media_raw:
        if not isinstance(item, Mapping):
            return None, OUTCOME_CORRUPT_OR_UNSUPPORTED
        media_id = item.get("media_id")
        relpath = item.get("relpath")
        if not isinstance(media_id, str) or not media_id.strip():
            return None, OUTCOME_CORRUPT_OR_UNSUPPORTED
        if not isinstance(relpath, str) or not relpath.strip():
            return None, OUTCOME_CORRUPT_OR_UNSUPPORTED
        media_id = media_id.strip()
        relpath = _posix_relpath(relpath.strip())
        if media_id in seen_ids or relpath in seen_relpaths:
            return None, OUTCOME_CORRUPT_OR_UNSUPPORTED
        seen_ids.add(media_id)
        seen_relpaths.add(relpath)
        media_entries.append(MediaEntry(media_id=media_id, relpath=relpath))

    arrangement = data.get("arrangement")
    midi = data.get("midi")
    manifest = TrackPackageManifest(
        schema_version=schema_version,
        package_kind=str(package_kind),
        track_id=track_id.strip(),
        media=tuple(sorted(media_entries, key=lambda e: e.media_id)),
        musical=dict(musical),
        arrangement=arrangement,
        midi=midi,
    )
    return manifest, OUTCOME_OPEN


def _validate_package_at(
    package_root: Path,
    *,
    require_bindable: bool,
) -> TrackPackageResult:
    root = Path(package_root)
    manifest_path = root / TRACK_PACKAGE_FILENAME
    if not manifest_path.is_file():
        return _failure(
            OUTCOME_CORRUPT_OR_UNSUPPORTED,
            package_root=root,
            message="Package manifest missing.",
        )
    try:
        raw = manifest_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return _failure(
            OUTCOME_CORRUPT_OR_UNSUPPORTED,
            package_root=root,
            message="Package manifest is corrupt.",
        )

    manifest, status = _parse_manifest_payload(data)
    if manifest is None or status != OUTCOME_OPEN:
        return _failure(status, package_root=root, message="Unsupported package.")

    if not (root / MEDIA_DIR_NAME).is_dir():
        return _failure(
            OUTCOME_CORRUPT_OR_UNSUPPORTED,
            package_root=root,
            track_id=manifest.track_id,
            message="Package media directory missing.",
        )

    for entry in manifest.media:
        escape = validate_confined_media_relpath(entry.relpath, root)
        if escape is not None:
            return _failure(
                escape,
                package_root=root,
                track_id=manifest.track_id,
                message="Media path escape rejected.",
            )
        media_file = root / Path(*entry.relpath.split("/"))
        if not media_file.exists():
            return _failure(
                OUTCOME_MISSING_MEDIA,
                package_root=root,
                track_id=manifest.track_id,
                message="Required media is missing.",
            )
        if not media_file.is_file():
            return _failure(
                OUTCOME_CORRUPT_OR_UNSUPPORTED,
                package_root=root,
                track_id=manifest.track_id,
                message="Media entry is not a file.",
            )
        try:
            resolved = media_file.resolve(strict=True)
            resolved.relative_to(root.resolve(strict=False))
        except (OSError, RuntimeError, ValueError):
            return _failure(
                OUTCOME_PATH_ESCAPE_REJECTED,
                package_root=root,
                track_id=manifest.track_id,
                message="Media path escape rejected.",
            )

    if require_bindable and not manifest.media:
        return _failure(
            OUTCOME_CORRUPT_OR_UNSUPPORTED,
            package_root=root,
            track_id=manifest.track_id,
            message="Package has no media.",
        )
    return _success_open(root, manifest)


def validate_track_package(package_root: Path | str) -> TrackPackageResult:
    """Fail-closed package integrity check (no global bind side effects)."""
    return _validate_package_at(Path(package_root), require_bindable=False)


def open_track_package(package_root: Path | str) -> TrackPackageResult:
    """Explicit open/load: validate then return lifecycle ``open`` on success."""
    return _validate_package_at(Path(package_root), require_bindable=True)


__all__ = [
    "MEDIA_DIR_NAME",
    "MEDIA_ID_PREFIX",
    "OUTCOME_COPY_INTERRUPTED",
    "OUTCOME_CORRUPT_OR_UNSUPPORTED",
    "OUTCOME_DESTINATION_UNAVAILABLE",
    "OUTCOME_MISSING_MEDIA",
    "OUTCOME_OPEN",
    "OUTCOME_PATH_ESCAPE_REJECTED",
    "OUTCOME_WRITE_FAILED",
    "PACKAGE_KIND",
    "SCHEMA_VERSION",
    "TRACK_ID_PREFIX",
    "TRACK_PACKAGE_FILENAME",
    "MediaEntry",
    "TrackPackageDraft",
    "TrackPackageManifest",
    "TrackPackageMediaSource",
    "TrackPackageResult",
    "create_track_package",
    "default_repo_root",
    "destination_inside_repository",
    "new_media_id",
    "new_track_id",
    "open_track_package",
    "serialize_track_package_json",
    "validate_confined_media_relpath",
    "validate_track_package",
]
