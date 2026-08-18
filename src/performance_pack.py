"""Performance Pack Assembler (issue #260).

This module assembles the final Performance Pack manifest from deconstruction
outputs, integrating Track Map, Arrangement Map, and Asset Manifests into a
portable Performance Pack according to the #257 contract.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.deconstruct import RunResult
from src.content_hash import compute_file_hash
from src.utils import file_hash


@dataclass
class PerformancePackManifest:
    """Performance Pack Manifest v1 structure."""

    document_type: str = "sample_brain.performance_pack_manifest"
    schema_version: str = "1.0.0"
    pack_id: str = ""
    source_track: dict[str, Any] | None = None
    documents: dict[str, Any] | None = None
    assets: list[dict[str, Any]] | None = None
    stems: list[dict[str, Any]] | None = None
    status: str = "complete"
    provenance: dict[str, Any] | None = None
    quality: dict[str, Any] | None = None


def build_performance_pack_manifest(
    run_result: RunResult, pack_root: Path
) -> PerformancePackManifest:
    """Build a Performance Pack manifest from deconstruction run results.

    Args:
        run_result: The result from the deconstruction orchestrator
        pack_root: The root directory of the Performance Pack

    Returns:
        PerformancePackManifest ready to be serialized to manifest.json
    """
    # Initialize manifest
    manifest = PerformancePackManifest()

    # Get track identity from Track Map file on disk
    track_map_result = next(
        (s for s in run_result.steps if s.step_id == "track_map"), None
    )
    if not track_map_result or not track_map_result.output_refs:
        manifest.status = "failed"
        return manifest

    # Read the actual Track Map file
    track_map_path = pack_root / track_map_result.output_refs[0]
    if not track_map_path.exists():
        manifest.status = "failed"
        return manifest

    try:
        track_map = json.loads(track_map_path.read_text(encoding="utf-8"))
    except Exception:
        manifest.status = "failed"
        return manifest

    # Extract original source from Track Map
    original = track_map.get("source", {}).get("original")
    if (
        not original
        or "hash" not in original
        or not original["hash"]
        or not original["hash"].get("value")
    ):
        raise ValueError(
            "Authoritative track hash (source.original.hash.value) is missing. Cannot assemble Performance Pack."
        )

    # Set source_track from Track Map (authoritative identity)
    manifest.source_track = {
        "track_id": original["hash"]["value"],
        "track_ref": "analysis/track_map.json",
        "file_name": original["file_name"],
        "hash": original["hash"],
        "audio_properties": {
            "duration_sec": original["audio_properties"]["duration_sec"],
            "sample_rate_hz": original["audio_properties"]["sample_rate_hz"],
            "channels": original["audio_properties"]["channels"],
        },
    }

    # Set pack_id based on track_id
    manifest.pack_id = f"pack_{original['hash']['value'][:16]}"

    # Set documents
    documents = {}

    # Track Map (required)
    track_map_entry = {
        "ref": "analysis/track_map.json",
        "document_type": "sample_brain.track_map",
        "schema_version": "1.0.0",
        "status": track_map_result.status,
    }
    # Extract status from the analysis section of the track map
    analysis = track_map.get("analysis", {})
    if analysis and analysis.get("status"):
        track_map_entry["reason_code"] = analysis.get("reason_code", "")
    documents["track_map"] = track_map_entry

    # Arrangement Map (optional)
    arrangement_result = next(
        (s for s in run_result.steps if s.step_id == "arrangement"), None
    )
    if arrangement_result and arrangement_result.output_refs:
        arrangement_map = {
            "ref": arrangement_result.output_refs[0],
            "document_type": "sample_brain.arrangement_map",
            "schema_version": "0.1.0-draft",
            "status": arrangement_result.status,
        }
        if arrangement_result.reason_code:
            arrangement_map["reason_code"] = arrangement_result.reason_code
        documents["arrangement"] = arrangement_map

    manifest.documents = documents

    # Set assets
    assets = []

    # Collect all asset manifest references from the assets step
    assets_result = next((s for s in run_result.steps if s.step_id == "assets"), None)
    if assets_result and assets_result.output_refs:
        pack_root_path = Path(pack_root)
        for asset_ref in assets_result.output_refs:
            asset_path = pack_root_path / asset_ref
            if asset_path.exists():
                try:
                    asset_data = json.loads(asset_path.read_text(encoding="utf-8"))
                    # Ensure the asset has correct track_ref (must match source_track.track_id)
                    if "track_ref" in asset_data:
                        asset_data["track_ref"] = manifest.source_track["track_id"]

                    # The pack entry must carry the portable reference to the Asset
                    # Manifest so re-importers (#263) can locate it. The deconstruction
                    # pipeline writes the Asset Manifest content but drops asset_ref;
                    # restore it here from the resolved output reference.
                    asset_data["asset_ref"] = asset_ref

                    # Add the asset to our list
                    assets.append(asset_data)
                except Exception:
                    # Skip invalid asset manifests
                    continue

    manifest.assets = assets

    # Set provenance
    manifest.provenance = {
        "components": {
            "pack_assembler": {
                "component": "pack_assembler",
                "sample_brain_version": "0.1.0",
                "configuration": {
                    "Performance Pack schema": "1.0.0",
                    "Layout-Vertrag": "Performance Pack Layout v1",
                },
            }
        },
    }

    # Set quality (assembler integrity notes are appended during stem integration)
    manifest.quality = {"notes": []}

    # Set stems (optional) — integrate authoritative Stem Manifests from the
    # deconstruction `stems` step when present (#261). The assembler is read-only
    # toward the Stem Manifest files and never rewrites their track_ref.
    stems_result = next((s for s in run_result.steps if s.step_id == "stems"), None)
    stems_entries, stems_degraded = _collect_pack_stems(
        stems_result,
        pack_root,
        manifest.source_track["track_id"],
        manifest.quality["notes"],
    )
    manifest.stems = stems_entries
    manifest.provenance["components"]["pack_assembler"]["configuration"][
        "stems_included"
    ] = bool(stems_entries)

    # Determine final pack status based on #257 rules, then apply stem
    # assembler-integrity degradation (invalid/missing declared references).
    manifest.status = _compute_pack_status(manifest)
    if stems_degraded and manifest.status == "complete":
        manifest.status = "partial"

    return manifest


def _compute_pack_status(manifest: PerformancePackManifest) -> str:
    """Compute the overall pack status according to #257 rules.

    Rules:
    1. If Track Map is missing or failed -> pack failed
    2. Else if any present component has partial/failed -> pack partial
    3. Else -> pack complete
    """
    # Check Track Map (required)
    track_map = manifest.documents.get("track_map") if manifest.documents else None
    if not track_map or track_map.get("status") == "failed":
        return "failed"

    # Check optional components
    components = []

    # Arrangement
    arrangement = manifest.documents.get("arrangement") if manifest.documents else None
    if arrangement:
        components.append(arrangement.get("status"))

    # Assets
    for asset in manifest.assets or []:
        components.append(asset.get("status"))

    # Stems (currently not used but kept for completeness)
    for stem in manifest.stems or []:
        components.append(stem.get("status"))

    # Apply aggregation rules
    if any(c in ("partial", "failed") for c in components):
        return "partial"

    return "complete"


_STEM_DOCUMENT_TYPE = "sample_brain.stem_manifest"
_STEM_ORDER = {"drums": 0, "bass": 1, "vocals": 2, "other": 3}
_ALLOWED_STEM_STATUS = {"ok", "partial", "not_run", "no_result", "failed"}


def _is_portable_stem_ref(raw: str) -> bool:
    """Reject absolute/UNC/drive/file:///.. references for stem refs."""
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


def _validate_stem_identity(data: object, source_track_id: str) -> list[str]:
    """Validate a parsed Stem Manifest for pack-level referencing.

    Returns a list of stable error codes (empty == valid). A track_ref mismatch
    is reported as ``STEM_TRACK_REF_MISMATCH``; everything else as
    ``INVALID_STEM_REFERENCE``. The manifest is never mutated.
    """
    if not isinstance(data, dict):
        return ["INVALID_STEM_REFERENCE"]
    errors: list[str] = []

    if data.get("document_type") != _STEM_DOCUMENT_TYPE:
        errors.append("INVALID_STEM_REFERENCE")

    schema_version = data.get("schema_version")
    if not isinstance(schema_version, str) or not schema_version:
        errors.append("INVALID_STEM_REFERENCE")
    else:
        try:
            major = int(schema_version.split(".")[0])
        except (ValueError, IndexError):
            errors.append("INVALID_STEM_REFERENCE")
        else:
            if major != 1:
                errors.append("INVALID_STEM_REFERENCE")

    stem_id = data.get("stem_id")
    if not isinstance(stem_id, str) or not stem_id:
        errors.append("INVALID_STEM_REFERENCE")

    stem_kind = data.get("stem_kind")
    if stem_kind not in _STEM_ORDER:
        errors.append("INVALID_STEM_REFERENCE")

    status = data.get("status")
    if status not in _ALLOWED_STEM_STATUS:
        errors.append("INVALID_STEM_REFERENCE")

    if data.get("track_ref") != source_track_id:
        errors.append("STEM_TRACK_REF_MISMATCH")

    if status in ("ok", "partial"):
        output = data.get("output")
        file_ref = output.get("file_ref") if isinstance(output, dict) else None
        if not isinstance(file_ref, str) or not file_ref:
            errors.append("INVALID_STEM_REFERENCE")

    return errors


def _add_stem_quality_note(quality_notes: list, code: str) -> None:
    quality_notes.append(
        {
            "code": code,
            "severity": "warning",
            "path": "/stems",
            "message": "A declared optional stem output could not be validated.",
        }
    )


def _collect_pack_stems(
    stems_result,
    pack_root: Path,
    source_track_id: str,
    quality_notes: list,
) -> tuple[list[dict], bool]:
    """Collect portable pack-level Stem Manifest references from the stems step.

    Authoritative source is ``stems_result.output_refs`` (never a filesystem
    scan). Invalid/missing/mismatched references are excluded, recorded as
    portable quality notes, and force a pack downgrade to ``partial``.

    Returns ``(entries, degraded)`` where ``entries`` is deterministically
    ordered (drums, bass, vocals, other, then by kind/id/ref).
    """
    entries: list[tuple[int, str, str, str, dict]] = []
    degraded = False
    pack_root = Path(pack_root).resolve()

    if stems_result is None:
        return [], degraded

    refs = list(stems_result.output_refs or [])

    for ref in refs:
        if not _is_portable_stem_ref(ref):
            _add_stem_quality_note(quality_notes, "INVALID_STEM_REFERENCE")
            degraded = True
            continue

        stem_path = pack_root / ref
        try:
            stem_path_resolved = stem_path.resolve()
        except Exception:
            _add_stem_quality_note(quality_notes, "INVALID_STEM_REFERENCE")
            degraded = True
            continue

        if (
            stem_path_resolved != pack_root
            and pack_root not in stem_path_resolved.parents
        ):
            _add_stem_quality_note(quality_notes, "INVALID_STEM_REFERENCE")
            degraded = True
            continue

        if not stem_path_resolved.is_file():
            _add_stem_quality_note(quality_notes, "MISSING_STEM_MANIFEST")
            degraded = True
            continue

        try:
            data = json.loads(stem_path_resolved.read_text(encoding="utf-8"))
        except Exception:
            _add_stem_quality_note(quality_notes, "INVALID_STEM_REFERENCE")
            degraded = True
            continue

        id_errors = _validate_stem_identity(data, source_track_id)
        if id_errors:
            code = (
                "STEM_TRACK_REF_MISMATCH"
                if "STEM_TRACK_REF_MISMATCH" in id_errors
                else "INVALID_STEM_REFERENCE"
            )
            _add_stem_quality_note(quality_notes, code)
            degraded = True
            continue

        # For usable stems, verify the referenced audio actually exists inside
        # the pack so the result is consumable.
        if data["status"] in ("ok", "partial"):
            file_ref = data["output"]["file_ref"]
            if not _is_portable_stem_ref(file_ref):
                _add_stem_quality_note(quality_notes, "INVALID_STEM_REFERENCE")
                degraded = True
                continue
            audio_path = (stem_path_resolved.parent / file_ref).resolve()
            if audio_path != pack_root and pack_root not in audio_path.parents:
                _add_stem_quality_note(quality_notes, "INVALID_STEM_REFERENCE")
                degraded = True
                continue
            if not audio_path.is_file():
                _add_stem_quality_note(quality_notes, "MISSING_STEM_MANIFEST")
                degraded = True
                continue

        try:
            file_value = compute_file_hash(stem_path_resolved)
        except Exception:
            file_value = None

        entry = {
            "stem_id": data["stem_id"],
            "stem_ref": ref,
            "document_type": _STEM_DOCUMENT_TYPE,
            "schema_version": data["schema_version"],
            "track_ref": source_track_id,
            "status": data["status"],
        }
        if file_value is not None:
            entry["hash"] = file_value

        order_key = _STEM_ORDER.get(data["stem_kind"], len(_STEM_ORDER))
        entries.append((order_key, data["stem_kind"], data["stem_id"], ref, entry))

    entries.sort(key=lambda x: (x[0], x[1], x[2], x[3]))
    built = [e[4] for e in entries]

    # Step-level degradation only when something was actually declared/produced.
    # A failed stem step with no output_refs (= nothing attempted/available) is a
    # normal missing optional result and must NOT downgrade the pack (#257).
    step_status = getattr(stems_result, "status", None)
    if step_status in ("partial", "failed") and (built or refs):
        degraded = True
        _add_stem_quality_note(
            quality_notes,
            (
                "MISSING_STEM_MANIFEST"
                if step_status == "partial"
                else "INVALID_STEM_REFERENCE"
            ),
        )

    return built, degraded


def write_performance_pack(manifest: PerformancePackManifest, pack_root: Path) -> None:
    """Write the Performance Pack manifest to disk.

    Args:
        manifest: The Performance Pack manifest to write
        pack_root: The root directory of the Performance Pack
    """
    pack_root.mkdir(parents=True, exist_ok=True)
    manifest_path = pack_root / "manifest.json"

    # Convert to dict for JSON serialization
    manifest_dict = {
        "document_type": manifest.document_type,
        "schema_version": manifest.schema_version,
        "pack_id": manifest.pack_id,
        "source_track": manifest.source_track,
        "documents": manifest.documents,
        "assets": manifest.assets,
        "stems": manifest.stems,
        "status": manifest.status,
        "provenance": manifest.provenance,
        "quality": manifest.quality,
    }

    # Remove None values to keep output clean
    manifest_dict = {k: v for k, v in manifest_dict.items() if v is not None}

    manifest_path.write_text(
        json.dumps(manifest_dict, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )


def finalize_performance_pack(run_result: RunResult, pack_root: Path) -> RunResult:
    """Finalize the deconstruction run by creating the Performance Pack.

    This function is called by the CLI after run_deconstruct completes.
    It creates manifest.json and returns an updated RunResult.

    Args:
        run_result: The result from the deconstruction orchestrator
        pack_root: The root directory of the Performance Pack

    Returns:
        Updated RunResult with pack information
    """
    # Build the manifest
    manifest = build_performance_pack_manifest(run_result, pack_root)

    # Write it to disk
    write_performance_pack(manifest, pack_root)

    # Update the run result to indicate pack completion
    # We don't modify the original run result, but we could add pack info to it
    # For now, we just return the original result since the pack is written separately
    return run_result


__all__ = [
    "PerformancePackManifest",
    "build_performance_pack_manifest",
    "_compute_pack_status",
    "write_performance_pack",
    "finalize_performance_pack",
]
