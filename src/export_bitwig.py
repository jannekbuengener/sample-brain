# src/export_bitwig.py
"""
Bitwig Studio adapter for sample metadata export.
Generates Bitwig metadata database format.
"""
from __future__ import annotations
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from .metadata import export_all_metadata
from .config import DATA_DIR


def convert_to_bitwig_format(metadata_list: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Convert generic metadata to Bitwig Studio format.

    Bitwig uses a JSON-based metadata structure for samples.

    Args:
        metadata_list: List of generic metadata dictionaries

    Returns:
        Dictionary in Bitwig format
    """
    bitwig_db = {
        "version": "1.0",
        "samples": []
    }

    for item in metadata_list:
        # Build Bitwig sample entry
        bitwig_sample = {
            "path": item.get("path", ""),
            "relativePath": item.get("relpath", ""),
            "tags": item.get("tags", []),
            "color": "",  # Empty = no color
            "rating": 0,
        }

        # Musical properties
        musical_props = {}
        if item.get("bpm"):
            musical_props["tempo"] = item["bpm"]
        if item.get("key"):
            musical_props["key"] = item["key"]
        if item.get("duration"):
            musical_props["duration"] = item["duration"]

        if musical_props:
            bitwig_sample["musicalProperties"] = musical_props

        # Audio characteristics
        audio_props = {}
        if item.get("loudness") is not None:
            audio_props["loudness"] = item["loudness"]
        if item.get("brightness") is not None:
            audio_props["brightness"] = item["brightness"]

        if audio_props:
            bitwig_sample["audioProperties"] = audio_props

        # Custom metadata
        bitwig_sample["customMetadata"] = {
            "sampleID": item.get("sample_id"),
            "filename": item.get("filename"),
        }

        bitwig_db["samples"].append(bitwig_sample)

    return bitwig_db


def convert_to_bitwig_xml(metadata_list: list[dict[str, Any]]) -> ET.Element:
    """
    Convert metadata to Bitwig XML format (alternative format).

    Args:
        metadata_list: List of generic metadata dictionaries

    Returns:
        XML Element tree root
    """
    root = ET.Element("BitwigSampleDatabase")
    root.set("version", "1.0")

    samples_elem = ET.SubElement(root, "Samples")

    for item in metadata_list:
        sample_elem = ET.SubElement(samples_elem, "Sample")
        sample_elem.set("id", str(item.get("sample_id", "")))

        # Path
        path_elem = ET.SubElement(sample_elem, "Path")
        path_elem.text = item.get("path", "")

        # Tags
        tags_elem = ET.SubElement(sample_elem, "Tags")
        for tag in item.get("tags", []):
            tag_elem = ET.SubElement(tags_elem, "Tag")
            tag_elem.text = tag

        # Properties
        props_elem = ET.SubElement(sample_elem, "Properties")

        if item.get("bpm"):
            bpm_elem = ET.SubElement(props_elem, "Tempo")
            bpm_elem.text = str(item["bpm"])

        if item.get("key"):
            key_elem = ET.SubElement(props_elem, "Key")
            key_elem.text = item["key"]

        if item.get("duration"):
            dur_elem = ET.SubElement(props_elem, "Duration")
            dur_elem.text = str(item["duration"])

        if item.get("loudness") is not None:
            loud_elem = ET.SubElement(props_elem, "Loudness")
            loud_elem.text = str(item["loudness"])

        if item.get("brightness") is not None:
            bright_elem = ET.SubElement(props_elem, "Brightness")
            bright_elem.text = str(item["brightness"])

    return root


def export_to_bitwig_json(output_path: Path | None = None) -> Path:
    """
    Export to Bitwig JSON format.

    Args:
        output_path: Optional custom output path

    Returns:
        Path to created Bitwig database file
    """
    # Generate metadata
    metadata_list = export_all_metadata()

    # Convert to Bitwig format
    bitwig_db = convert_to_bitwig_format(metadata_list)

    # Determine output path
    if output_path is None:
        output_path = DATA_DIR / "bitwig_database.json"
    else:
        output_path = Path(output_path)

    # Ensure parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write database
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(bitwig_db, f, indent=2, ensure_ascii=False)

    return output_path


def export_to_bitwig_xml(output_path: Path | None = None) -> Path:
    """
    Export to Bitwig XML format.

    Args:
        output_path: Optional custom output path

    Returns:
        Path to created Bitwig XML file
    """
    # Generate metadata
    metadata_list = export_all_metadata()

    # Convert to Bitwig XML
    root = convert_to_bitwig_xml(metadata_list)

    # Determine output path
    if output_path is None:
        output_path = DATA_DIR / "bitwig_database.xml"
    else:
        output_path = Path(output_path)

    # Ensure parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write XML
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")  # Pretty print
    tree.write(output_path, encoding="utf-8", xml_declaration=True)

    return output_path


def run_export_bitwig(format: str = "json", output_path: Path | None = None) -> Path:
    """
    Export to Bitwig format.

    Args:
        format: 'json' or 'xml'
        output_path: Optional custom output path

    Returns:
        Path to created file
    """
    if format == "xml":
        return export_to_bitwig_xml(output_path)
    else:
        return export_to_bitwig_json(output_path)
