"""Python-owned track package core (#1085A / #1082 contract).

Owns runtime ``track_package.json`` schema v1, staged create, path confinement,
and explicit validate/open. Does not own Browser registration, legacy session
migration, autosave wiring, or a second musical session authority.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import errno
from fractions import Fraction
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any
import uuid

from .pattern_core import CHANNEL_ID_BY_LIVE_KIT_SLOT
from .workbench_live_kit import LIVE_KIT_SLOT_MAPPING

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
_DRIVE_ABS = re.compile(r"^[a-zA-Z]:")
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

    try:
        root = package_root.resolve(strict=False)
        candidate = (package_root / Path(*text.split("/"))).resolve(strict=False)
        candidate.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return OUTCOME_PATH_ESCAPE_REJECTED

    # If the path exists, resolve again after following links / reparse points.
    try:
        exists = candidate.exists() or (package_root / Path(*text.split("/"))).exists()
    except (OSError, RuntimeError):
        return OUTCOME_PATH_ESCAPE_REJECTED
    if exists:
        try:
            resolved = (package_root / Path(*text.split("/"))).resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, RuntimeError, ValueError):
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
                    link_target.relative_to(root)
            except (OSError, RuntimeError, ValueError):
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
    probe: Path | None = None
    try:
        fd, probe_name = tempfile.mkstemp(
            prefix=".sample-brain-track-package-probe-",
            dir=str(parent),
        )
        probe = Path(probe_name)
        with os.fdopen(fd, "wb") as handle:
            handle.write(b"ok")
        probe.unlink(missing_ok=True)
        probe = None
    except OSError:
        if probe is not None:
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


def _files_byte_identical(left: Path, right: Path, *, chunk_size: int = 1024 * 1024) -> bool:
    """Compare two files incrementally without buffering both entirely."""
    left_stat = left.stat()
    right_stat = right.stat()
    if left_stat.st_size != right_stat.st_size:
        return False
    with left.open("rb") as left_handle, right.open("rb") as right_handle:
        while True:
            left_chunk = left_handle.read(chunk_size)
            right_chunk = right_handle.read(chunk_size)
            if left_chunk != right_chunk:
                return False
            if not left_chunk:
                return True


def _iter_musical_sample_refs(musical: Mapping[str, Any]) -> list[str]:
    refs: list[str] = []
    live_kit = musical.get("live_kit")
    if isinstance(live_kit, Mapping):
        for group_payload in live_kit.values():
            if not isinstance(group_payload, Mapping):
                continue
            for slot_payload in group_payload.values():
                if slot_payload is None:
                    continue
                if isinstance(slot_payload, Mapping):
                    path = slot_payload.get("path")
                    if isinstance(path, str) and path.strip():
                        refs.append(path.strip())
                elif isinstance(slot_payload, str) and slot_payload.strip():
                    refs.append(slot_payload.strip())
    channel_rack = musical.get("channel_rack")
    if isinstance(channel_rack, Mapping):
        channels = channel_rack.get("channels")
        if isinstance(channels, list):
            for channel in channels:
                if not isinstance(channel, Mapping):
                    continue
                path = channel.get("sample_path")
                if isinstance(path, str) and path.strip():
                    refs.append(path.strip())
    return refs


def _validate_live_kit_shape(live_kit: Mapping[str, Any]) -> str | None:
    known = {(group, slot) for group, slots in LIVE_KIT_SLOT_MAPPING for slot in slots}
    for group, slots_payload in live_kit.items():
        if not isinstance(group, str) or not isinstance(slots_payload, Mapping):
            return OUTCOME_CORRUPT_OR_UNSUPPORTED
        for slot, slot_payload in slots_payload.items():
            if not isinstance(slot, str):
                return OUTCOME_CORRUPT_OR_UNSUPPORTED
            if (group, slot) not in known:
                return OUTCOME_CORRUPT_OR_UNSUPPORTED
            if slot_payload is None:
                continue
            if not isinstance(slot_payload, Mapping):
                return OUTCOME_CORRUPT_OR_UNSUPPORTED
            if set(slot_payload.keys()) - {"path"}:
                return OUTCOME_CORRUPT_OR_UNSUPPORTED
            if "path" not in slot_payload:
                return OUTCOME_CORRUPT_OR_UNSUPPORTED
            path = slot_payload.get("path")
            if path is not None and (
                not isinstance(path, str) or path.strip() == ""
            ):
                return OUTCOME_CORRUPT_OR_UNSUPPORTED
    return None


def _exact_nonbool_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _fraction_from_payload_value(payload: object) -> Fraction | None:
    if not isinstance(payload, Mapping):
        return None
    if set(payload.keys()) - {"numerator", "denominator"}:
        return None
    numerator = _exact_nonbool_int(payload.get("numerator"))
    denominator = _exact_nonbool_int(payload.get("denominator"))
    if numerator is None or denominator is None or denominator == 0:
        return None
    try:
        return Fraction(numerator, denominator)
    except (TypeError, ValueError, ZeroDivisionError, OverflowError):
        return None


def _validate_fraction_payload(payload: object) -> bool:
    return _fraction_from_payload_value(payload) is not None


def _validate_channel_rack_shape(channel_rack: Mapping[str, Any]) -> str | None:
    required = {
        "pattern_id",
        "length_quarter_notes",
        "step_count",
        "channels",
        "triggers",
    }
    if set(channel_rack.keys()) != required:
        return OUTCOME_CORRUPT_OR_UNSUPPORTED
    pattern_id = channel_rack.get("pattern_id")
    if not isinstance(pattern_id, str) or not pattern_id.strip():
        return OUTCOME_CORRUPT_OR_UNSUPPORTED
    length = _fraction_from_payload_value(channel_rack.get("length_quarter_notes"))
    if length is None or length <= 0:
        return OUTCOME_CORRUPT_OR_UNSUPPORTED
    step_count = _exact_nonbool_int(channel_rack.get("step_count"))
    if step_count is None or step_count <= 0:
        return OUTCOME_CORRUPT_OR_UNSUPPORTED
    channels = channel_rack.get("channels")
    triggers = channel_rack.get("triggers")
    if not isinstance(channels, list) or not isinstance(triggers, list):
        return OUTCOME_CORRUPT_OR_UNSUPPORTED
    if not channels:
        return OUTCOME_CORRUPT_OR_UNSUPPORTED

    seed_by_id: dict[str, Mapping[str, Any]] = {}
    known_ids: set[str] = set()
    for channel in channels:
        if not isinstance(channel, Mapping):
            return OUTCOME_CORRUPT_OR_UNSUPPORTED
        if set(channel.keys()) - {
            "channel_id",
            "live_kit_group",
            "live_kit_slot",
            "sample_path",
        }:
            return OUTCOME_CORRUPT_OR_UNSUPPORTED
        channel_id = channel.get("channel_id")
        if not isinstance(channel_id, str) or not channel_id.strip():
            return OUTCOME_CORRUPT_OR_UNSUPPORTED
        if channel_id in known_ids:
            return OUTCOME_CORRUPT_OR_UNSUPPORTED
        known_ids.add(channel_id)
        group = channel.get("live_kit_group")
        slot = channel.get("live_kit_slot")
        if group is not None and not isinstance(group, str):
            return OUTCOME_CORRUPT_OR_UNSUPPORTED
        if slot is not None and not isinstance(slot, str):
            return OUTCOME_CORRUPT_OR_UNSUPPORTED
        if (group is None) != (slot is None):
            return OUTCOME_CORRUPT_OR_UNSUPPORTED
        sample_path = channel.get("sample_path")
        if sample_path is not None and (
            not isinstance(sample_path, str) or sample_path.strip() == ""
        ):
            return OUTCOME_CORRUPT_OR_UNSUPPORTED
        if group is not None and slot is not None:
            seed_by_id[channel_id] = channel

    expected_ids = set(CHANNEL_ID_BY_LIVE_KIT_SLOT.values())
    if set(seed_by_id) != expected_ids:
        return OUTCOME_CORRUPT_OR_UNSUPPORTED
    for (group, slot), channel_id in CHANNEL_ID_BY_LIVE_KIT_SLOT.items():
        channel = seed_by_id[channel_id]
        if channel.get("live_kit_group") != group or channel.get("live_kit_slot") != slot:
            return OUTCOME_CORRUPT_OR_UNSUPPORTED

    for trigger in triggers:
        if not isinstance(trigger, Mapping):
            return OUTCOME_CORRUPT_OR_UNSUPPORTED
        if set(trigger.keys()) - {"channel_id", "position"}:
            return OUTCOME_CORRUPT_OR_UNSUPPORTED
        channel_id = trigger.get("channel_id")
        if not isinstance(channel_id, str) or channel_id not in known_ids:
            return OUTCOME_CORRUPT_OR_UNSUPPORTED
        position = _fraction_from_payload_value(trigger.get("position"))
        if position is None or position < 0 or position >= length:
            return OUTCOME_CORRUPT_OR_UNSUPPORTED

    return None


def _live_kit_slot_path(live_kit: Mapping[str, Any], group: str, slot: str) -> str | None:
    group_payload = live_kit.get(group)
    if not isinstance(group_payload, Mapping):
        return None
    slot_payload = group_payload.get(slot)
    if slot_payload is None:
        return None
    if not isinstance(slot_payload, Mapping):
        return None
    path = slot_payload.get("path")
    if path is None:
        return None
    if not isinstance(path, str):
        return None
    return path


def _validate_rack_aligned_to_live_kit(
    channel_rack: Mapping[str, Any],
    live_kit: Mapping[str, Any],
) -> str | None:
    """Seed channel sample_path must match the corresponding Live Kit slot path."""
    channels = channel_rack.get("channels")
    if not isinstance(channels, list):
        return OUTCOME_CORRUPT_OR_UNSUPPORTED
    for channel in channels:
        if not isinstance(channel, Mapping):
            return OUTCOME_CORRUPT_OR_UNSUPPORTED
        group = channel.get("live_kit_group")
        slot = channel.get("live_kit_slot")
        if group is None or slot is None:
            continue
        kit_path = _live_kit_slot_path(live_kit, str(group), str(slot))
        sample_path = channel.get("sample_path")
        if kit_path != sample_path:
            return OUTCOME_CORRUPT_OR_UNSUPPORTED
    return None


def _validate_musical_semantics(musical: Mapping[str, Any]) -> str | None:
    live_kit = musical.get("live_kit")
    if not isinstance(live_kit, Mapping):
        return OUTCOME_CORRUPT_OR_UNSUPPORTED
    live_kit_error = _validate_live_kit_shape(live_kit)
    if live_kit_error is not None:
        return live_kit_error
    channel_rack = musical.get("channel_rack")
    if channel_rack is not None:
        if not isinstance(channel_rack, Mapping):
            return OUTCOME_CORRUPT_OR_UNSUPPORTED
        rack_error = _validate_channel_rack_shape(channel_rack)
        if rack_error is not None:
            return rack_error
        align_error = _validate_rack_aligned_to_live_kit(channel_rack, live_kit)
        if align_error is not None:
            return align_error
    master_bpm = musical.get("master_bpm")
    if isinstance(master_bpm, bool) or not isinstance(master_bpm, (int, float)):
        return OUTCOME_CORRUPT_OR_UNSUPPORTED
    try:
        bpm_value = float(master_bpm)
    except (OverflowError, ValueError):
        return OUTCOME_CORRUPT_OR_UNSUPPORTED
    if not math.isfinite(bpm_value) or bpm_value <= 0:
        return OUTCOME_CORRUPT_OR_UNSUPPORTED
    sync_enabled = musical.get("sync_enabled")
    if not isinstance(sync_enabled, bool):
        return OUTCOME_CORRUPT_OR_UNSUPPORTED
    return None


def _reject_non_finite_numbers(value: Any) -> str | None:
    if isinstance(value, float) and not math.isfinite(value):
        return OUTCOME_CORRUPT_OR_UNSUPPORTED
    if isinstance(value, list):
        for item in value:
            outcome = _reject_non_finite_numbers(item)
            if outcome is not None:
                return outcome
        return None
    if isinstance(value, Mapping):
        for item in value.values():
            outcome = _reject_non_finite_numbers(item)
            if outcome is not None:
                return outcome
        return None
    return None


def _reject_escaped_path_strings(value: Any) -> str | None:
    """Fail closed when any nested string looks like an absolute/escape path."""
    if isinstance(value, str):
        text = _posix_relpath(value.strip())
        if not text:
            return None
        # Package-relative media refs are allowed; everything else absolute-like
        # or traversal-bearing is rejected across the full payload.
        if text.startswith(f"{MEDIA_DIR_NAME}/"):
            if _looks_like_forbidden_ref(text):
                return OUTCOME_PATH_ESCAPE_REJECTED
            return None
        if _looks_like_forbidden_ref(text):
            return OUTCOME_PATH_ESCAPE_REJECTED
        return None
    if isinstance(value, list):
        for item in value:
            outcome = _reject_escaped_path_strings(item)
            if outcome is not None:
                return outcome
        return None
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str):
                key_outcome = _reject_escaped_path_strings(key)
                if key_outcome is not None:
                    return key_outcome
            outcome = _reject_escaped_path_strings(item)
            if outcome is not None:
                return outcome
        return None
    return None


def _is_destination_capacity_error(exc: OSError) -> bool:
    return getattr(exc, "errno", None) in {
        errno.ENOSPC,
        errno.EDQUOT,
        errno.EACCES,
        errno.EPERM,
        errno.EROFS,
    }


def _rewrite_musical_media_refs(
    musical: Mapping[str, Any],
    media_relpaths: set[str],
) -> tuple[dict[str, Any] | None, str | None]:
    """Return musical payload with canonical media refs, or a failure outcome."""
    try:
        rewritten = json.loads(json.dumps(musical, allow_nan=False))
    except (TypeError, ValueError):
        return None, OUTCOME_CORRUPT_OR_UNSUPPORTED

    def _canon(ref: object) -> tuple[str | None, str | None]:
        if not isinstance(ref, str):
            return None, OUTCOME_CORRUPT_OR_UNSUPPORTED
        # Reject noncanonical spellings (backslash separators / surrounding space).
        if ref != ref.strip() or "\\" in ref:
            return None, OUTCOME_CORRUPT_OR_UNSUPPORTED
        text = _posix_relpath(ref)
        if text != ref:
            return None, OUTCOME_CORRUPT_OR_UNSUPPORTED
        if _looks_like_forbidden_ref(text):
            return None, OUTCOME_PATH_ESCAPE_REJECTED
        if text not in media_relpaths:
            return None, OUTCOME_CORRUPT_OR_UNSUPPORTED
        return text, None

    live_kit = rewritten.get("live_kit")
    if isinstance(live_kit, dict):
        for _group, slots_payload in live_kit.items():
            if not isinstance(slots_payload, dict):
                continue
            for _slot, slot_payload in list(slots_payload.items()):
                if not isinstance(slot_payload, dict):
                    continue
                path = slot_payload.get("path")
                if path is None:
                    continue
                canon, err = _canon(path)
                if err is not None:
                    return None, err
                slot_payload["path"] = canon

    channel_rack = rewritten.get("channel_rack")
    if isinstance(channel_rack, dict):
        channels = channel_rack.get("channels")
        if isinstance(channels, list):
            for channel in channels:
                if not isinstance(channel, dict):
                    continue
                path = channel.get("sample_path")
                if path is None:
                    continue
                canon, err = _canon(path)
                if err is not None:
                    return None, err
                channel["sample_path"] = canon
    return rewritten, None


def _validate_musical_media_refs(
    musical: Mapping[str, Any],
    media_relpaths: set[str],
    package_root: Path,
) -> tuple[Mapping[str, Any] | None, str | None]:
    """Every musical sample ref must be a confined canonical media relpath."""
    rewritten, err = _rewrite_musical_media_refs(musical, media_relpaths)
    if err is not None or rewritten is None:
        return None, err or OUTCOME_CORRUPT_OR_UNSUPPORTED
    for ref in _iter_musical_sample_refs(rewritten):
        escape = validate_confined_media_relpath(ref, package_root)
        if escape is not None:
            return None, escape
    return rewritten, None


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
    try:
        final_root = Path(package_root).expanduser()
    except (OSError, RuntimeError, ValueError):
        return _failure(
            OUTCOME_DESTINATION_UNAVAILABLE,
            message="Package destination is unavailable.",
        )
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
            except OSError as exc:
                _remove_own_staging(staging)
                staging = None
                if _is_destination_capacity_error(exc):
                    return _failure(
                        OUTCOME_DESTINATION_UNAVAILABLE,
                        message="Package destination is unavailable.",
                    )
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
                if not _files_byte_identical(source, target):
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
        semantic_error = _validate_musical_semantics(musical)
        if semantic_error is not None:
            _remove_own_staging(staging)
            staging = None
            return _failure(semantic_error, message="Musical payload is invalid.")
        media_relpaths = {entry.relpath for entry in media_entries}
        musical_canon, ref_error = _validate_musical_media_refs(
            musical, media_relpaths, staging
        )
        if ref_error is not None or musical_canon is None:
            _remove_own_staging(staging)
            staging = None
            return _failure(
                ref_error or OUTCOME_CORRUPT_OR_UNSUPPORTED,
                message="Musical media refs are not portable.",
            )
        musical = dict(musical_canon)
        manifest = TrackPackageManifest(
            schema_version=SCHEMA_VERSION,
            package_kind=PACKAGE_KIND,
            track_id=track_id,
            media=tuple(media_entries),
            musical=musical,
            arrangement=draft.arrangement,
            midi=draft.midi,
        )
        payload_probe = {
            "schema_version": manifest.schema_version,
            "package_kind": manifest.package_kind,
            "track_id": manifest.track_id,
            "media": [
                {"media_id": e.media_id, "relpath": e.relpath} for e in media_entries
            ],
            "musical": musical,
            "arrangement": draft.arrangement,
            "midi": draft.midi,
        }
        path_scan = _reject_escaped_path_strings(payload_probe)
        if path_scan is not None:
            _remove_own_staging(staging)
            staging = None
            return _failure(path_scan, message="Package payload is not portable.")
        try:
            document = serialize_track_package_json(manifest)
        except (TypeError, ValueError):
            _remove_own_staging(staging)
            staging = None
            return _failure(
                OUTCOME_CORRUPT_OR_UNSUPPORTED,
                message="Package payload is not serializable.",
            )
        if _contains_forbidden_serialized_path(document):
            _remove_own_staging(staging)
            staging = None
            return _failure(
                OUTCOME_CORRUPT_OR_UNSUPPORTED,
                message="Package payload is not portable.",
            )
        try:
            (staging / TRACK_PACKAGE_FILENAME).write_text(document, encoding="utf-8")
        except OSError as exc:
            _remove_own_staging(staging)
            staging = None
            if _is_destination_capacity_error(exc):
                return _failure(
                    OUTCOME_DESTINATION_UNAVAILABLE,
                    message="Package destination is unavailable.",
                )
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
            # Never delete final_root on rename failure: a concurrent create may
            # already have published a valid package at this destination.
            if staging is not None:
                _remove_own_staging(staging)
                staging = None
            return _failure(
                OUTCOME_DESTINATION_UNAVAILABLE
                if final_root.exists()
                else OUTCOME_WRITE_FAILED,
                message="Package commit failed.",
            )
    except OSError:
        if staging is not None:
            _remove_own_staging(staging)
        return _failure(OUTCOME_WRITE_FAILED, message="Package create failed.")

    opened = open_track_package(final_root)
    if opened.outcome != OUTCOME_OPEN:
        return opened
    return _success_open(final_root, opened.manifest)  # type: ignore[arg-type]


def _contains_forbidden_serialized_path(document: str) -> bool:
    if "file://" in document.casefold():
        return True
    # Absolute Windows drive path fragments inside JSON string values.
    if re.search(r"[A-Za-z]:\\\\", document) or re.search(r"[A-Za-z]:/", document):
        return True
    # POSIX absolute path string values (e.g. "/home/...").
    if re.search(r'"/', document):
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
        semantic_error = _validate_musical_semantics(musical)
        if semantic_error is not None:
            return None, semantic_error
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


def _entrypoint_confined(manifest_path: Path, package_root: Path) -> bool:
    """True when track_package.json is a real in-package file (no symlink)."""
    try:
        if manifest_path.is_symlink():
            # Absolute or relative symlinks are not portable package entrypoints.
            return False
        root = package_root.resolve(strict=False)
        resolved = manifest_path.resolve(strict=False)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return False
    return True


def _validate_package_at(
    package_root: Path,
    *,
    require_bindable: bool,
) -> TrackPackageResult:
    root = Path(package_root)
    manifest_path = root / TRACK_PACKAGE_FILENAME
    if not manifest_path.exists():
        return _failure(
            OUTCOME_CORRUPT_OR_UNSUPPORTED,
            package_root=root,
            message="Package manifest missing.",
        )
    if not _entrypoint_confined(manifest_path, root):
        return _failure(
            OUTCOME_PATH_ESCAPE_REJECTED,
            package_root=root,
            message="Package manifest path escape rejected.",
        )
    if not manifest_path.is_file():
        return _failure(
            OUTCOME_CORRUPT_OR_UNSUPPORTED,
            package_root=root,
            message="Package manifest missing.",
        )
    try:
        raw = manifest_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return _failure(
            OUTCOME_CORRUPT_OR_UNSUPPORTED,
            package_root=root,
            message="Package manifest is corrupt.",
        )

    manifest, status = _parse_manifest_payload(data)
    if manifest is None or status != OUTCOME_OPEN:
        return _failure(status, package_root=root, message="Unsupported package.")

    path_scan = _reject_escaped_path_strings(data)
    if path_scan is not None:
        return _failure(
            path_scan,
            package_root=root,
            track_id=manifest.track_id,
            message="Package payload is not portable.",
        )
    finite_scan = _reject_non_finite_numbers(data)
    if finite_scan is not None:
        return _failure(
            finite_scan,
            package_root=root,
            track_id=manifest.track_id,
            message="Package payload contains non-finite numbers.",
        )

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

    media_relpaths = {entry.relpath for entry in manifest.media}
    musical_canon, ref_error = _validate_musical_media_refs(
        manifest.musical, media_relpaths, root
    )
    if ref_error is not None or musical_canon is None:
        return _failure(
            ref_error or OUTCOME_CORRUPT_OR_UNSUPPORTED,
            package_root=root,
            track_id=manifest.track_id,
            message="Musical media refs are not portable.",
        )
    if musical_canon != manifest.musical:
        manifest = TrackPackageManifest(
            schema_version=manifest.schema_version,
            package_kind=manifest.package_kind,
            track_id=manifest.track_id,
            media=manifest.media,
            musical=musical_canon,
            arrangement=manifest.arrangement,
            midi=manifest.midi,
        )

    if require_bindable and not manifest.media:
        return _failure(
            OUTCOME_CORRUPT_OR_UNSUPPORTED,
            package_root=root,
            track_id=manifest.track_id,
            message="Package has no media.",
        )
    return _success_open(root, manifest)


def save_track_package_musical_state(
    package_root: Path | str,
    musical: Mapping[str, Any],
    *,
    copy_file: CopyFileFn | None = None,
) -> TrackPackageResult:
    """Atomically replace package musical state, preserving last valid manifest.

    Existing package media is reused. Newly referenced runtime media is copied
    into ``media/`` first; if the manifest commit fails, media created by this
    write is removed so the previous package remains authoritative.
    """
    root = Path(package_root)
    opened = open_track_package(root)
    if opened.outcome != OUTCOME_OPEN or opened.manifest is None:
        return opened
    manifest = opened.manifest
    copy_fn = copy_file or _default_copy

    path_map: dict[str, str] = {}
    media_entries = list(manifest.media)
    for entry in media_entries:
        media_path = root / Path(*entry.relpath.split("/"))
        path_map[entry.relpath] = entry.relpath
        path_map[str(media_path)] = entry.relpath
        try:
            resolved = media_path.resolve(strict=True)
        except (OSError, RuntimeError, ValueError):
            return _failure(
                OUTCOME_MISSING_MEDIA,
                package_root=root,
                track_id=manifest.track_id,
                message="Required package media is missing.",
            )
        path_map[str(resolved)] = entry.relpath
        path_map[_normalize_source_key(resolved)] = entry.relpath

    created_media: list[Path] = []
    temp_files: list[Path] = []
    committed = False
    try:
        for ref in dict.fromkeys(_iter_musical_sample_refs(musical)):
            if ref in path_map:
                continue
            try:
                source = Path(ref).expanduser()
                source_resolved = source.resolve(strict=True)
            except (OSError, RuntimeError, ValueError):
                return _failure(
                    OUTCOME_MISSING_MEDIA,
                    package_root=root,
                    track_id=manifest.track_id,
                    message="Required musical media is missing.",
                )
            source_key = _normalize_source_key(source_resolved)
            if source_key in path_map:
                path_map[ref] = path_map[source_key]
                continue
            if not source_resolved.is_file():
                return _failure(
                    OUTCOME_MISSING_MEDIA,
                    package_root=root,
                    track_id=manifest.track_id,
                    message="Required musical media is missing.",
                )

            # The live runtime may still hold the pre-import library path after a
            # successful package copy. Reuse byte-identical package media before
            # allocating another entry so unrelated later autosaves stay stable.
            reused_relpath: str | None = None
            for existing in media_entries:
                existing_path = root / Path(*existing.relpath.split("/"))
                try:
                    if _files_byte_identical(source_resolved, existing_path):
                        reused_relpath = existing.relpath
                        break
                except OSError:
                    continue
            if reused_relpath is not None:
                path_map[ref] = reused_relpath
                path_map[str(source)] = reused_relpath
                path_map[str(source_resolved)] = reused_relpath
                path_map[source_key] = reused_relpath
                continue

            media_id = new_media_id()
            relpath = _media_relpath_for(media_id, source_resolved)
            target = root / Path(*relpath.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            temp_target = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
            temp_files.append(temp_target)
            try:
                copy_fn(source_resolved, temp_target)
                if not temp_target.is_file() or not _files_byte_identical(source_resolved, temp_target):
                    raise OSError("copied media validation failed")
                os.replace(temp_target, target)
                temp_files.remove(temp_target)
            except OSError:
                try:
                    temp_target.unlink(missing_ok=True)
                except OSError:
                    pass
                return _failure(
                    OUTCOME_WRITE_FAILED,
                    package_root=root,
                    track_id=manifest.track_id,
                    message="Track package media write failed.",
                )
            created_media.append(target)
            media_entries.append(MediaEntry(media_id=media_id, relpath=relpath))
            path_map[ref] = relpath
            path_map[str(source)] = relpath
            path_map[str(source_resolved)] = relpath
            path_map[source_key] = relpath

        portable = _rewrite_paths(dict(musical), path_map)
        semantic_error = _validate_musical_semantics(portable)
        if semantic_error is not None:
            return _failure(semantic_error, package_root=root, track_id=manifest.track_id)
        media_relpaths = {entry.relpath for entry in media_entries}
        musical_canon, ref_error = _validate_musical_media_refs(portable, media_relpaths, root)
        if ref_error is not None or musical_canon is None:
            return _failure(
                ref_error or OUTCOME_CORRUPT_OR_UNSUPPORTED,
                package_root=root,
                track_id=manifest.track_id,
                message="Musical media refs are not portable.",
            )
        updated = TrackPackageManifest(
            schema_version=manifest.schema_version,
            package_kind=manifest.package_kind,
            track_id=manifest.track_id,
            media=tuple(sorted(media_entries, key=lambda entry: entry.media_id)),
            musical=dict(musical_canon),
            arrangement=manifest.arrangement,
            midi=manifest.midi,
        )
        payload_probe = {
            "schema_version": updated.schema_version,
            "package_kind": updated.package_kind,
            "track_id": updated.track_id,
            "media": [
                {"media_id": entry.media_id, "relpath": entry.relpath}
                for entry in updated.media
            ],
            "musical": updated.musical,
            "arrangement": updated.arrangement,
            "midi": updated.midi,
        }
        if _reject_escaped_path_strings(payload_probe) is not None:
            return _failure(
                OUTCOME_PATH_ESCAPE_REJECTED,
                package_root=root,
                track_id=manifest.track_id,
                message="Package payload is not portable.",
            )
        try:
            document = serialize_track_package_json(updated)
        except (TypeError, ValueError):
            return _failure(
                OUTCOME_CORRUPT_OR_UNSUPPORTED,
                package_root=root,
                track_id=manifest.track_id,
                message="Package payload is not serializable.",
            )
        temp_manifest = root / f".{TRACK_PACKAGE_FILENAME}.{uuid.uuid4().hex}.tmp"
        temp_files.append(temp_manifest)
        try:
            temp_manifest.write_text(document, encoding="utf-8")
            os.replace(temp_manifest, root / TRACK_PACKAGE_FILENAME)
            committed = True
            temp_files.remove(temp_manifest)
        except OSError:
            return _failure(
                OUTCOME_WRITE_FAILED,
                package_root=root,
                track_id=manifest.track_id,
                message="Track package write failed.",
            )
        return _success_open(root, updated)
    finally:
        for temp_path in temp_files:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
        # A failed transaction keeps the prior valid manifest authoritative;
        # any newly copied media is unreferenced and owned by this failed write.
        if not committed:
            for created in created_media:
                try:
                    created.unlink(missing_ok=True)
                except OSError:
                    pass


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
    "save_track_package_musical_state",
    "serialize_track_package_json",
    "validate_confined_media_relpath",
    "validate_track_package",
]
