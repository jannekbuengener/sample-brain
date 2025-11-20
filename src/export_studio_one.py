# src/export_studio_one.py
"""
PreSonus Studio One adapter for sample metadata export.
Generates Studio One Sound Set format (XML).
"""
from __future__ import annotations
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from .metadata import export_all_metadata
from .config import DATA_DIR


def convert_to_studio_one_format(metadata_list: list[dict[str, Any]]) -> ET.Element:
    """
    Convert generic metadata to Studio One Sound Set format.

    Studio One uses XML-based Sound Sets for sample organization.

    Args:
        metadata_list: List of generic metadata dictionaries

    Returns:
        XML Element tree root
    """
    # Create root element
    root = ET.Element("SoundSet")
    root.set("version", "1.0")
    root.set("name", "Sample Brain Library")

    # Create files container
    files_elem = ET.SubElement(root, "Files")

    for item in metadata_list:
        file_elem = ET.SubElement(files_elem, "File")
        file_elem.set("path", item.get("path", ""))
        file_elem.set("id", str(item.get("sample_id", "")))

        # Metadata
        metadata_elem = ET.SubElement(file_elem, "Metadata")

        # Name
        name_elem = ET.SubElement(metadata_elem, "Name")
        name_elem.text = item.get("filename", "")

        # Tempo
        if item.get("bpm"):
            tempo_elem = ET.SubElement(metadata_elem, "Tempo")
            tempo_elem.set("value", str(item["bpm"]))

        # Key
        if item.get("key"):
            key_elem = ET.SubElement(metadata_elem, "Key")
            key_elem.text = item["key"]

        # Duration
        if item.get("duration"):
            duration_elem = ET.SubElement(metadata_elem, "Duration")
            duration_elem.set("seconds", str(item["duration"]))

        # Tags
        if item.get("tags"):
            tags_elem = ET.SubElement(metadata_elem, "Tags")
            for tag in item["tags"]:
                tag_elem = ET.SubElement(tags_elem, "Tag")
                tag_elem.text = tag

        # Color (default: none)
        color_elem = ET.SubElement(metadata_elem, "Color")
        color_elem.set("rgb", "0,0,0")

        # Rating (0-5)
        rating_elem = ET.SubElement(metadata_elem, "Rating")
        rating_elem.set("stars", "0")

    return root


def export_to_studio_one_xml(output_path: Path, metadata_list: list[dict[str, Any]]) -> Path:
    """
    Export to Studio One Sound Set XML format.

    Args:
        output_path: Output file path
        metadata_list: List of metadata dictionaries

    Returns:
        Path to created file
    """
    root = convert_to_studio_one_format(metadata_list)

    # Write XML
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(output_path, encoding="utf-8", xml_declaration=True)

    return output_path


def run_export_studio_one(output_path: Path | None = None) -> Path:
    """
    Export to Studio One Sound Set format.

    Args:
        output_path: Optional custom output path

    Returns:
        Path to created file
    """
    metadata_list = export_all_metadata()

    if output_path is None:
        output_path = DATA_DIR / "studio_one_soundset.xml"
    else:
        output_path = Path(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    return export_to_studio_one_xml(output_path, metadata_list)
