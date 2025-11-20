# src/export_cubase.py
"""
Steinberg Cubase/Nuendo adapter for sample metadata export.
Generates MediaBay database format (XML).
"""
from __future__ import annotations
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from .metadata import export_all_metadata
from .config import DATA_DIR


def convert_to_cubase_format(metadata_list: list[dict[str, Any]]) -> ET.Element:
    """
    Convert generic metadata to Cubase MediaBay format.

    Cubase uses MediaBay XML format for sample management.

    Args:
        metadata_list: List of generic metadata dictionaries

    Returns:
        XML Element tree root
    """
    # Create root element
    root = ET.Element("MediaBayDB")
    root.set("version", "1.0")

    # Create samples container
    samples_elem = ET.SubElement(root, "Samples")

    for item in metadata_list:
        sample_elem = ET.SubElement(samples_elem, "Sample")
        sample_elem.set("id", str(item.get("sample_id", "")))

        # File info
        file_elem = ET.SubElement(sample_elem, "File")
        path_elem = ET.SubElement(file_elem, "Path")
        path_elem.text = item.get("path", "")

        name_elem = ET.SubElement(file_elem, "Name")
        name_elem.text = item.get("filename", "")

        # Attributes
        attrs_elem = ET.SubElement(sample_elem, "Attributes")

        # Tempo
        if item.get("bpm"):
            tempo_elem = ET.SubElement(attrs_elem, "Attribute")
            tempo_elem.set("name", "Tempo")
            tempo_elem.set("type", "float")
            tempo_elem.text = str(item["bpm"])

        # Musical Key
        if item.get("key"):
            key_elem = ET.SubElement(attrs_elem, "Attribute")
            key_elem.set("name", "MusicalKey")
            key_elem.set("type", "string")
            key_elem.text = item["key"]

        # Length
        if item.get("duration"):
            length_elem = ET.SubElement(attrs_elem, "Attribute")
            length_elem.set("name", "Length")
            length_elem.set("type", "float")
            length_elem.text = str(item["duration"])

        # Rating (default: 0)
        rating_elem = ET.SubElement(attrs_elem, "Attribute")
        rating_elem.set("name", "Rating")
        rating_elem.set("type", "integer")
        rating_elem.text = "0"

        # Character tags (from our tags)
        if item.get("tags"):
            character_elem = ET.SubElement(attrs_elem, "Attribute")
            character_elem.set("name", "Character")
            character_elem.set("type", "string")
            # Cubase uses semicolon-separated tags
            character_elem.text = ";".join(item["tags"])

        # Category (use first tag as category)
        if item.get("tags"):
            category_elem = ET.SubElement(attrs_elem, "Attribute")
            category_elem.set("name", "Category")
            category_elem.set("type", "string")
            category_elem.text = item["tags"][0]

    return root


def export_to_cubase_xml(output_path: Path, metadata_list: list[dict[str, Any]]) -> Path:
    """
    Export to Cubase MediaBay XML format.

    Args:
        output_path: Output file path
        metadata_list: List of metadata dictionaries

    Returns:
        Path to created file
    """
    root = convert_to_cubase_format(metadata_list)

    # Write XML
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(output_path, encoding="utf-8", xml_declaration=True)

    return output_path


def run_export_cubase(output_path: Path | None = None) -> Path:
    """
    Export to Cubase/Nuendo MediaBay format.

    Args:
        output_path: Optional custom output path

    Returns:
        Path to created file
    """
    metadata_list = export_all_metadata()

    if output_path is None:
        output_path = DATA_DIR / "cubase_mediabay.xml"
    else:
        output_path = Path(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    return export_to_cubase_xml(output_path, metadata_list)
