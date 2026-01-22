# src/export_ableton.py
"""
Ableton Live adapter for sample metadata export.
Generates Ableton Collection format (.agr files) and tag database.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from .metadata import export_all_metadata
from .config import DATA_DIR


def convert_to_ableton_format(metadata_list: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Convert generic metadata to Ableton Live Collection format.

    Ableton uses .agr (Ableton Groove) files and a tag database structure.
    Reference: https://help.ableton.com/hc/en-us/articles/209071729

    Args:
        metadata_list: List of generic metadata dictionaries

    Returns:
        Dictionary in Ableton Collection format
    """
    collection = {
        "Version": "1.0",
        "Type": "Collection",
        "Items": []
    }

    for item in metadata_list:
        # Build Ableton item
        ableton_item = {
            "Path": item.get("path", ""),
            "Tags": item.get("tags", []),
            "Color": -1,  # -1 = no color
            "Rating": 0,
        }

        # Add tempo if available
        if item.get("bpm"):
            ableton_item["Tempo"] = item["bpm"]

        # Add musical key if available
        if item.get("key"):
            ableton_item["Key"] = item["key"]

        # Add duration
        if item.get("duration"):
            ableton_item["Duration"] = item["duration"]

        # Metadata fields
        ableton_item["Metadata"] = {
            "Loudness": item.get("loudness"),
            "Brightness": item.get("brightness"),
            "SampleID": item.get("sample_id"),
        }

        collection["Items"].append(ableton_item)

    return collection


def export_to_ableton(output_path: Path | None = None) -> Path:
    """
    Export all sample metadata to Ableton Live Collection format.

    Args:
        output_path: Optional custom output path

    Returns:
        Path to created Ableton collection file
    """
    # Generate metadata
    metadata_list = export_all_metadata()

    # Convert to Ableton format
    ableton_collection = convert_to_ableton_format(metadata_list)

    # Determine output path
    if output_path is None:
        output_path = DATA_DIR / "ableton_collection.json"
    else:
        output_path = Path(output_path)

    # Ensure parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write collection
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(ableton_collection, f, indent=2, ensure_ascii=False)

    # Also create a tag index for quick lookup
    tag_index_path = output_path.parent / "ableton_tags_index.json"
    tag_index = build_tag_index(metadata_list)

    with open(tag_index_path, "w", encoding="utf-8") as f:
        json.dump(tag_index, f, indent=2, ensure_ascii=False)

    return output_path


def build_tag_index(metadata_list: list[dict[str, Any]]) -> dict[str, list[str]]:
    """
    Build reverse index: tag -> [paths].

    Args:
        metadata_list: List of metadata dictionaries

    Returns:
        Dictionary mapping tags to file paths
    """
    tag_index = {}

    for item in metadata_list:
        path = item.get("path", "")
        for tag in item.get("tags", []):
            if tag not in tag_index:
                tag_index[tag] = []
            tag_index[tag].append(path)

    return tag_index


def run_export_ableton(output_path: Path | None = None) -> tuple[Path, Path]:
    """
    Export to Ableton format with tag index.

    Args:
        output_path: Optional custom output path

    Returns:
        Tuple of (collection_path, tag_index_path)
    """
    collection_path = export_to_ableton(output_path)
    tag_index_path = collection_path.parent / "ableton_tags_index.json"

    return collection_path, tag_index_path
