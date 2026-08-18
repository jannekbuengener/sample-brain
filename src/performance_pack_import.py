"""Performance Pack re-import reader (issue #263).

Re-imports a produced Performance Pack into the normal Sample-Brain catalog so
its Loops, Sections, and (optional) technical Stems become ordinary, analyzable,
searchable, matchable samples.

Design contract
---------------
* The Performance Pack manifest is the external truth. SQLite is only a local
  search/working index. No pack field becomes part of the schema.
* No new table and no new ``samples`` column are introduced. Lineage lives in
  ``sample_tags`` (source = ``performance_pack``).
* Every reference is validated as portable and resolved inside the pack root;
  anything escaping it is rejected fail-closed.
* Audio is verified by content hash + audio properties before registration.
* Deduplication is by content hash and never overwrites an existing row with new
  content (same path + different hash fails closed).
* No features are pre-filled; ``run_analyze`` computes them afterward.

This module deliberately reuses the existing catalog, analyze, autotype, match,
and search paths. It implements none of those.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import text

from .db import (
    find_sample_by_path,
    find_sample_id_by_hash,
    get_engine,
    init_db,
    insert_sample,
    upsert_sample_tag,
)
from .utils import file_hash

TAG_SOURCE = "performance_pack"
SUPPORTED_MAJOR = 1
PACK_DOCUMENT_TYPE = "sample_brain.performance_pack_manifest"
TRACK_MAP_DOCUMENT_TYPE = "sample_brain.track_map"
ASSET_DOCUMENT_TYPE = "sample_brain.asset_manifest"
STEM_DOCUMENT_TYPE = "sample_brain.stem_manifest"
USABLE_STATUSES = {"ok", "partial"}

DETERMINISTIC_ERROR_CODES = {
    "MANIFEST_NOT_FOUND",
    "MANIFEST_INVALID_JSON",
    "DOCUMENT_TYPE_MISMATCH",
    "UNSUPPORTED_SCHEMA_MAJOR",
    "MISSING_SOURCE_TRACK",
    "MISSING_TRACK_MAP",
    "TRACK_MAP_PORTABLE_REF",
    "TRACK_MAP_REF_OUTSIDE_PACK",
    "TRACK_MAP_DOCUMENT_TYPE",
    "TRACK_MAP_SCHEMA_MAJOR",
    "TRACK_MAP_TRACK_ID_MISMATCH",
    "TRACK_MAP_FAILED",
    "ASSET_REF_MISSING",
    "ASSET_REF_PORTABLE",
    "ASSET_REF_OUTSIDE_PACK",
    "ASSET_MANIFEST_NOT_FOUND",
    "ASSET_DOCUMENT_TYPE",
    "ASSET_SCHEMA_MAJOR",
    "ASSET_ID_MISMATCH",
    "ASSET_TRACK_REF_MISMATCH",
    "ASSET_KIND_MISMATCH",
    "ASSET_NOT_RENDERED",
    "ASSET_AUDIO_REF_PORTABLE",
    "ASSET_AUDIO_REF_OUTSIDE_PACK",
    "ASSET_AUDIO_NOT_FOUND",
    "ASSET_HASH_MISMATCH",
    "ASSET_PROPS_MISMATCH",
    "STEM_REF_MISSING",
    "STEM_REF_PORTABLE",
    "STEM_REF_OUTSIDE_PACK",
    "STEM_MANIFEST_NOT_FOUND",
    "STEM_DOCUMENT_TYPE",
    "STEM_SCHEMA_MAJOR",
    "STEM_TRACK_REF_MISMATCH",
    "STEM_NOT_RENDERED",
    "STEM_AUDIO_REF_PORTABLE",
    "STEM_AUDIO_REF_OUTSIDE_PACK",
    "STEM_AUDIO_NOT_FOUND",
    "STEM_HASH_MISMATCH",
    "STEM_PROPS_MISMATCH",
    "SAME_PATH_DIFFERENT_HASH",
}


class PackImportError(Exception):
    """Fail-closed error for an invalid or untrustworthy Performance Pack."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _is_portable_ref(raw: str) -> bool:
    """True when ``raw`` is a safe, relative, in-pack reference.

    Rejects: empty, ``..`` traversal, ``file://``, backslashes (Windows absolute
    / UNC), leading ``/``, and drive-letter references (``C:``).
    """
    if not isinstance(raw, str) or not raw:
        return False
    if ".." in raw:
        return False
    if "file://" in raw:
        return False
    if "\\" in raw:
        return False
    if raw.startswith("/"):
        return False
    for i, ch in enumerate(raw[:-1]):
        if ch.isalpha() and raw[i + 1] == ":":
            return False
    return True


def _resolve_ref(raw: str, base_dir: Path, *, kind: str) -> Path:
    """Validate portability and resolve ``raw`` against ``base_dir``.

    ``base_dir`` is the pack root for pack-level refs, or the referencing
    manifest's own directory for in-manifest ``file_ref`` values.
    """
    if not _is_portable_ref(raw):
        raise PackImportError(
            _ref_code(kind, "PORTABLE"),
            f"{kind} reference is not portable: {raw!r}",
        )
    base = Path(base_dir).resolve()
    candidate = (base / raw)
    try:
        resolved = candidate.resolve()
    except Exception as exc:  # pragma: no cover - defensive
        raise PackImportError(
            _ref_code(kind, "PORTABLE"),
            f"{kind} reference could not be resolved: {raw!r} ({exc})",
        )
    if resolved != base and base not in resolved.parents:
        raise PackImportError(
            _ref_code(kind, "OUTSIDE_PACK"),
            f"{kind} reference escapes the pack root: {raw!r}",
        )
    return resolved


def _ref_code(kind: str, suffix: str) -> str:
    return f"{kind.upper()}_{suffix}"


def _major(version: str) -> int:
    try:
        return int(str(version).split(".")[0])
    except (ValueError, AttributeError):
        return -1


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PackImportError(
            "MANIFEST_INVALID_JSON",
            f"Could not read JSON at {path}: {exc}",
        )


def _resolve_manifest_path(pack_root: Path) -> tuple[Path, Path]:
    """Return (manifest_path, pack_root_dir)."""
    manifest_path = Path(pack_root)
    if manifest_path.is_file():
        return manifest_path, manifest_path.parent
    if manifest_path.is_dir():
        candidate = manifest_path / "manifest.json"
        if candidate.exists():
            return candidate, manifest_path
    raise PackImportError(
        "MANIFEST_NOT_FOUND",
        f"Performance Pack manifest not found at {pack_root}",
    )


def _verify_audio_integrity(
    audio_path: Path,
    expected_hash: str,
    expected_props: dict,
    *,
    audio_kind: str,
) -> dict:
    if not audio_path.exists():
        raise PackImportError(
            f"{audio_kind}_AUDIO_NOT_FOUND",
            f"Declared {audio_kind} audio not found: {audio_path}",
        )
    actual_hash = file_hash(audio_path)
    if actual_hash != expected_hash:
        raise PackImportError(
            f"{audio_kind}_HASH_MISMATCH",
            f"{audio_kind} audio hash mismatch at {audio_path}: "
            f"expected {expected_hash}, got {actual_hash}",
        )
    try:
        import soundfile as sf

        with sf.SoundFile(str(audio_path)) as f:
            actual_sr = int(f.samplerate)
            actual_ch = int(f.channels)
            actual_n = int(len(f))
    except Exception as exc:
        raise PackImportError(
            f"{audio_kind}_PROPS_MISMATCH",
            f"Could not read {audio_kind} audio properties at {audio_path}: {exc}",
        )
    expected_sr = expected_props.get("sample_rate_hz")
    expected_ch = expected_props.get("channels")
    expected_n = expected_props.get("n_samples")
    if actual_sr != expected_sr or actual_ch != expected_ch or actual_n != expected_n:
        raise PackImportError(
            f"{audio_kind}_PROPS_MISMATCH",
            f"{audio_kind} audio properties mismatch at {audio_path}: "
            f"expected sr={expected_sr} ch={expected_ch} n={expected_n}, "
            f"got sr={actual_sr} ch={actual_ch} n={actual_n}",
        )
    duration = actual_n / actual_sr if actual_sr else None
    return {
        "sample_rate_hz": actual_sr,
        "channels": actual_ch,
        "n_samples": actual_n,
        "duration": duration,
        "size_bytes": audio_path.stat().st_size,
        "hash": actual_hash,
    }


def _register_sample(
    audio_path: Path,
    props: dict,
    *,
    pack_id: str,
    track_id: str,
    item_kind: str,
    item_id: str,
    source_kind: str | None,
) -> tuple[int, bool]:
    """Register (or reuse) a sample row and attach lineage tags.

    Returns (sample_id, reused). Never overwrites an existing row with new
    content: same path + different hash fails closed.
    """
    path = str(audio_path)
    content_hash = props["hash"]

    by_path = find_sample_by_path(path)
    if by_path is not None:
        existing_id, existing_hash = by_path
        if existing_hash == content_hash:
            sample_id = existing_id
            reused = True
        else:
            raise PackImportError(
                "SAME_PATH_DIFFERENT_HASH",
                f"Existing sample at {path} has a different content hash; "
                "refusing to reinterpret the identity.",
            )
    else:
        by_hash = find_sample_id_by_hash(content_hash)
        if by_hash is not None:
            sample_id = by_hash
            reused = True
        else:
            rel = None
            try:
                rel = str(audio_path.resolve().relative_to(audio_path.parent.resolve()))
            except Exception:
                rel = None
            sample_id = insert_sample(
                path=path,
                relpath=rel,
                samplerate=props["sample_rate_hz"],
                channels=props["channels"],
                duration=props["duration"],
                size_bytes=props["size_bytes"],
                content_hash=content_hash,
            )
            reused = False

    _attach_lineage(
        sample_id,
        pack_id=pack_id,
        track_id=track_id,
        item_kind=item_kind,
        item_id=item_id,
        source_kind=source_kind,
    )
    return sample_id, reused


def _attach_lineage(
    sample_id: int,
    *,
    pack_id: str,
    track_id: str,
    item_kind: str,
    item_id: str,
    source_kind: str | None,
) -> None:
    tags = [
        f"pack:{pack_id}",
        f"parent_track:{track_id}",
        f"item_kind:{item_kind}",
        f"item_id:{item_id}",
    ]
    if source_kind:
        tags.append(f"source_kind:{source_kind}")
    for tag in tags:
        upsert_sample_tag(sample_id, tag, TAG_SOURCE)


def _import_asset(
    entry: dict,
    pack_root: Path,
    *,
    pack_id: str,
    track_id: str,
) -> tuple[int | None, bool, str | None]:
    """Validate + import one pack asset entry.

    Returns (sample_id, reused, error_code). ``sample_id is None`` means the
    item was skipped (optional/unusable) or failed integrity (error_code set).
    """
    asset_ref = entry.get("asset_ref")
    if not isinstance(asset_ref, str) or not asset_ref:
        # A missing asset_ref is a structural contract gap; treat as fail-closed
        # so the pack cannot be silently partial.
        raise PackImportError(
            "ASSET_REF_MISSING",
            f"Asset entry missing asset_ref: {entry.get('asset_id')!r}",
        )

    asset_status = entry.get("status")
    if asset_status is None:
        asset_status = entry.get("candidate", {}).get("status")

    # Accept ok, partial, or candidate (pipeline normal output) as valid.
    # USABLE_STATUSES = {"ok", "partial"} stays unchanged; candidate is the
    # pipeline's normal status indicator for generated assets.
    resolved_status = asset_status
    if resolved_status in ("ok", "partial", "candidate"):
        pass  # valid
    elif resolved_status not in USABLE_STATUSES:
        # failed / not_run / no_result optional item: skip, no fake sample.
        return None, False, f"asset_status:{resolved_status}"

    asset_path = _resolve_ref(asset_ref, pack_root, kind="asset")
    if not asset_path.exists():
        raise PackImportError(
            "ASSET_MANIFEST_NOT_FOUND",
            f"Asset manifest not found: {asset_path}",
        )
    asset = _load_json(asset_path)

    if asset.get("document_type") != ASSET_DOCUMENT_TYPE:
        raise PackImportError(
            "ASSET_DOCUMENT_TYPE",
            f"Asset manifest document_type must be {ASSET_DOCUMENT_TYPE!r}",
        )
    if _major(asset.get("schema_version", "")) != SUPPORTED_MAJOR:
        raise PackImportError(
            "ASSET_SCHEMA_MAJOR",
            f"Unsupported asset manifest schema major for {asset_ref!r}",
        )
    if asset.get("asset_id") != entry.get("asset_id"):
        raise PackImportError(
            "ASSET_ID_MISMATCH",
            f"Asset manifest asset_id {asset.get('asset_id')!r} != pack entry "
            f"{entry.get('asset_id')!r}",
        )
    if asset.get("track_ref") != track_id:
        raise PackImportError(
            "ASSET_TRACK_REF_MISMATCH",
            f"Asset track_ref {asset.get('track_ref')!r} != source_track.track_id",
        )
    if asset.get("asset_kind") != entry.get("asset_kind"):
        raise PackImportError(
            "ASSET_KIND_MISMATCH",
            f"Asset kind {asset.get('asset_kind')!r} != pack entry "
            f"{entry.get('asset_kind')!r}",
        )

    rendering = asset.get("rendering") or {}
    if rendering.get("status") != "rendered" or not rendering.get("output"):
        # Declared but not actually rendered: cannot import audio.
        return None, False, "asset_not_rendered"

    output = rendering["output"]
    file_ref = output.get("file_ref")
    if not isinstance(file_ref, str) or not file_ref:
        raise PackImportError(
            "ASSET_AUDIO_REF_PORTABLE",
            f"Asset output.file_ref missing for {asset_ref!r}",
        )
    audio_path = _resolve_ref(file_ref, asset_path.parent, kind="asset_audio")
    audio_props = _verify_audio_integrity(
        audio_path,
        expected_hash=output["hash"]["value"],
        expected_props=output["audio_properties"],
        audio_kind="ASSET",
    )
    sample_id, reused = _register_sample(
        audio_path,
        audio_props,
        pack_id=pack_id,
        track_id=track_id,
        item_kind=asset["asset_kind"],
        item_id=asset["asset_id"],
        source_kind=entry.get("source_kind"),
    )
    return sample_id, reused, None


def _import_stem(
    entry: dict,
    pack_root: Path,
    *,
    pack_id: str,
    track_id: str,
) -> tuple[int | None, bool, str | None]:
    stem_ref = entry.get("stem_ref")
    if not isinstance(stem_ref, str) or not stem_ref:
        raise PackImportError(
            "STEM_REF_MISSING",
            f"Stem entry missing stem_ref: {entry.get('stem_id')!r}",
        )
    stem_status = entry.get("status")
    if stem_status not in USABLE_STATUSES:
        return None, False, f"stem_status:{stem_status}"

    stem_path = _resolve_ref(stem_ref, pack_root, kind="stem")
    if not stem_path.exists():
        raise PackImportError(
            "STEM_MANIFEST_NOT_FOUND",
            f"Stem manifest not found: {stem_path}",
        )
    stem = _load_json(stem_path)

    if stem.get("document_type") != STEM_DOCUMENT_TYPE:
        raise PackImportError(
            "STEM_DOCUMENT_TYPE",
            f"Stem manifest document_type must be {STEM_DOCUMENT_TYPE!r}",
        )
    if _major(stem.get("schema_version", "")) != SUPPORTED_MAJOR:
        raise PackImportError(
            "STEM_SCHEMA_MAJOR",
            f"Unsupported stem manifest schema major for {stem_ref!r}",
        )
    if stem.get("track_ref") != track_id:
        raise PackImportError(
            "STEM_TRACK_REF_MISMATCH",
            f"Stem track_ref {stem.get('track_ref')!r} != source_track.track_id",
        )

    output = stem.get("output")
    if not output:
        return None, False, "stem_not_rendered"
    file_ref = output.get("file_ref")
    if not isinstance(file_ref, str) or not file_ref:
        raise PackImportError(
            "STEM_AUDIO_REF_PORTABLE",
            f"Stem output.file_ref missing for {stem_ref!r}",
        )
    audio_path = _resolve_ref(file_ref, stem_path.parent, kind="stem_audio")
    audio_props = _verify_audio_integrity(
        audio_path,
        expected_hash=output["hash"]["value"],
        expected_props=output["audio_properties"],
        audio_kind="STEM",
    )
    sample_id, reused = _register_sample(
        audio_path,
        audio_props,
        pack_id=pack_id,
        track_id=track_id,
        item_kind="stem",
        item_id=stem.get("stem_id"),
        source_kind=None,
    )
    return sample_id, reused, None


@dataclass
class ImportResult:
    pack_id: str = ""
    source_track_id: str = ""
    imported: int = 0
    reused: int = 0
    skipped: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)
    sample_ids: list[int] = field(default_factory=list)


def run_pack_import(pack_root: Path, engine: Any = None) -> ImportResult:
    """Re-import a Performance Pack into the catalog.

    Args:
        pack_root: pack root directory or a direct ``manifest.json`` path.
        engine: unused placeholder for API symmetry (catalog uses ``src.db``).

    Returns:
        ImportResult with deterministic counts and sample ids.

    Raises:
        PackImportError: fail-closed on any structural or integrity violation.
    """
    init_db()
    manifest_path, pack_root_dir = _resolve_manifest_path(Path(pack_root))

    if not manifest_path.exists():
        raise PackImportError("MANIFEST_NOT_FOUND", f"Manifest not found: {manifest_path}")

    manifest = _load_json(manifest_path)
    if manifest.get("document_type") != PACK_DOCUMENT_TYPE:
        raise PackImportError(
            "DOCUMENT_TYPE_MISMATCH",
            f"Root manifest document_type must be {PACK_DOCUMENT_TYPE!r}",
        )
    if _major(manifest.get("schema_version", "")) != SUPPORTED_MAJOR:
        raise PackImportError(
            "UNSUPPORTED_SCHEMA_MAJOR",
            f"Unsupported Performance Pack schema major: {manifest.get('schema_version')!r}",
        )

    source_track = manifest.get("source_track")
    if not isinstance(source_track, dict) or not source_track.get("track_id"):
        raise PackImportError("MISSING_SOURCE_TRACK", "source_track.track_id is required")
    track_id = source_track["track_id"]
    pack_id = manifest.get("pack_id", "")

    # Track Map (required anchor)
    documents = manifest.get("documents") or {}
    track_map_entry = documents.get("track_map")
    if not isinstance(track_map_entry, dict) or not track_map_entry.get("ref"):
        raise PackImportError("MISSING_TRACK_MAP", "documents.track_map.ref is required")
    track_map_path = _resolve_ref(track_map_entry["ref"], pack_root_dir, kind="track_map")
    if not track_map_path.exists():
        raise PackImportError(
            "TRACK_MAP_REF_OUTSIDE_PACK",
            f"Track Map not found: {track_map_path}",
        )
    track_map = _load_json(track_map_path)
    if track_map.get("document_type") != TRACK_MAP_DOCUMENT_TYPE:
        raise PackImportError(
            "TRACK_MAP_DOCUMENT_TYPE",
            f"Track Map document_type must be {TRACK_MAP_DOCUMENT_TYPE!r}",
        )
    if _major(track_map.get("schema_version", "")) != SUPPORTED_MAJOR:
        raise PackImportError(
            "TRACK_MAP_SCHEMA_MAJOR",
            "Unsupported Track Map schema major",
        )
    original = (track_map.get("source") or {}).get("original") or {}
    original_hash = (original.get("hash") or {}).get("value")
    if original_hash != track_id:
        raise PackImportError(
            "TRACK_MAP_TRACK_ID_MISMATCH",
            "Track Map source.original.hash.value must equal source_track.track_id",
        )
    if track_map_entry.get("status") == "failed":
        raise PackImportError("TRACK_MAP_FAILED", "Required Track Map has status failed")

    result = ImportResult(pack_id=pack_id, source_track_id=track_id)
    seen_ids: set[int] = set()

    for entry in manifest.get("assets", []) or []:
        sample_id, reused, skip_reason = _import_asset(
            entry, pack_root_dir, pack_id=pack_id, track_id=track_id
        )
        if sample_id is None:
            result.skipped += 1
            if skip_reason:
                result.errors.append(
                    {"asset_id": str(entry.get("asset_id")), "reason": skip_reason}
                )
            continue
        if reused:
            result.reused += 1
        else:
            result.imported += 1
        if sample_id not in seen_ids:
            seen_ids.add(sample_id)
            result.sample_ids.append(sample_id)

    for entry in manifest.get("stems", []) or []:
        sample_id, reused, skip_reason = _import_stem(
            entry, pack_root_dir, pack_id=pack_id, track_id=track_id
        )
        if sample_id is None:
            result.skipped += 1
            if skip_reason:
                result.errors.append(
                    {"stem_id": str(entry.get("stem_id")), "reason": skip_reason}
                )
            continue
        if reused:
            result.reused += 1
        else:
            result.imported += 1
        if sample_id not in seen_ids:
            seen_ids.add(sample_id)
            result.sample_ids.append(sample_id)

    return result


__all__ = [
    "PackImportError",
    "ImportResult",
    "run_pack_import",
]
