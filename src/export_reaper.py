# src/export_reaper.py
"""
Cockos REAPER adapter for sample metadata export.
Generates REAPER Media Item metadata (RPP-compatible).
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from .metadata import export_all_metadata
from .config import DATA_DIR


def convert_to_reaper_format(metadata_list: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Convert generic metadata to REAPER-compatible format.

    REAPER uses JSON for external metadata management.

    Args:
        metadata_list: List of generic metadata dictionaries

    Returns:
        Dictionary in REAPER format
    """
    reaper_db = {
        "version": "1.0",
        "format": "REAPER Media Database",
        "items": []
    }

    for item in metadata_list:
        reaper_item = {
            "file": item.get("path", ""),
            "name": item.get("filename", ""),
        }

        # Properties
        props = {}
        if item.get("bpm"):
            props["bpm"] = item["bpm"]
        if item.get("key"):
            props["key"] = item["key"]
        if item.get("duration"):
            props["length"] = item["duration"]
        if item.get("loudness") is not None:
            props["loudness"] = item["loudness"]
        if item.get("brightness") is not None:
            props["brightness"] = item["brightness"]

        if props:
            reaper_item["properties"] = props

        # Tags (REAPER uses "notes" field for tags)
        if item.get("tags"):
            reaper_item["notes"] = " | ".join(item["tags"])

        # Color (default: 0)
        reaper_item["color"] = 0

        reaper_db["items"].append(reaper_item)

    return reaper_db


def export_to_reaper_json(output_path: Path, metadata_list: list[dict[str, Any]]) -> Path:
    """
    Export to REAPER JSON format.

    Args:
        output_path: Output file path
        metadata_list: List of metadata dictionaries

    Returns:
        Path to created file
    """
    reaper_db = convert_to_reaper_format(metadata_list)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(reaper_db, f, indent=2, ensure_ascii=False)

    return output_path


def export_to_reaper_csv(output_path: Path, metadata_list: list[dict[str, Any]]) -> Path:
    """
    Export to REAPER CSV format (simple import).

    REAPER can import CSV files with: File, Name, BPM, Key, Tags

    Args:
        output_path: Output file path
        metadata_list: List of metadata dictionaries

    Returns:
        Path to created file
    """
    import csv

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["File", "Name", "BPM", "Key", "Duration", "Tags"])

        for item in metadata_list:
            writer.writerow([
                item.get("path", ""),
                item.get("filename", ""),
                item.get("bpm", ""),
                item.get("key", ""),
                item.get("duration", ""),
                " | ".join(item.get("tags", []))
            ])

    return output_path


def run_export_reaper(
    format: str = "json",
    output_path: Path | None = None
) -> Path:
    """
    Export to REAPER format.

    Args:
        format: 'json' or 'csv'
        output_path: Optional custom output path

    Returns:
        Path to created file
    """
    metadata_list = export_all_metadata()

    if output_path is None:
        extension = "json" if format == "json" else "csv"
        output_path = DATA_DIR / f"reaper_media_db.{extension}"
    else:
        output_path = Path(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if format == "csv":
        return export_to_reaper_csv(output_path, metadata_list)
    else:
        return export_to_reaper_json(output_path, metadata_list)
