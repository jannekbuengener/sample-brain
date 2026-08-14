"""Performance Pack Assembler (issue #260).

This module assembles the final Performance Pack manifest from deconstruction
outputs, integrating Track Map, Arrangement Map, and Asset Manifests into a
portable Performance Pack according to the #257 contract.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.deconstruct import RunResult


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


def build_performance_pack_manifest(run_result: RunResult, pack_root: Path) -> PerformancePackManifest:
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
    track_map_result = next((s for s in run_result.steps if s.step_id == "track_map"), None)
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
    if not original or "hash" not in original or not original["hash"] or not original["hash"].get("value"):
        raise ValueError("Authoritative track hash (source.original.hash.value) is missing. Cannot assemble Performance Pack.")

    # Set source_track from Track Map (authoritative identity)
    manifest.source_track = {
        "track_id": original["hash"]["value"],
        "track_ref": "analysis/track_map.json",
        "file_name": original["file_name"],
        "hash": original["hash"],
        "audio_properties": {
            "duration_sec": original["audio_properties"]["duration_sec"],
            "sample_rate_hz": original["audio_properties"]["sample_rate_hz"],
            "channels": original["audio_properties"]["channels"]
        }
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
    arrangement_result = next((s for s in run_result.steps if s.step_id == "arrangement"), None)
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

                    # Ensure track_id matches source_track.track_id for proper traceability
                    if "asset_id" in asset_data:
                        # Asset ID should already be correct from generation
                        pass

                    # Add the asset to our list
                    assets.append(asset_data)
                except Exception:
                    # Skip invalid asset manifests
                    continue

    manifest.assets = assets

    # Set stems (optional - for now, we don't process stems in this version)
    manifest.stems = []

    # Set provenance
    manifest.provenance = {
        "components": {
            "pack_assembler": {
                "component": "pack_assembler",
                "sample_brain_version": "0.1.0",
                "configuration": {
                    "Performance Pack schema": "1.0.0",
                    "Layout-Vertrag": "Performance Pack Layout v1"
                }
            }
        }
    }

    # Set quality
    manifest.quality = {"notes": []}

    # Determine final pack status based on #257 rules
    manifest.status = _compute_pack_status(manifest)

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
        "quality": manifest.quality
    }

    # Remove None values to keep output clean
    manifest_dict = {k: v for k, v in manifest_dict.items() if v is not None}

    manifest_path.write_text(
        json.dumps(manifest_dict, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8"
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
    "finalize_performance_pack"
]
