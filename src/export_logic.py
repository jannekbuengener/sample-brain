# src/export_logic.py
"""
Apple Logic Pro adapter for sample metadata export.
Generates Logic Pro Library format (XML-based).
"""
from __future__ import annotations
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from .metadata import export_all_metadata
from .config import DATA_DIR


def convert_to_logic_format(metadata_list: list[dict[str, Any]]) -> ET.Element:
    """
    Convert generic metadata to Logic Pro Library XML format.

    Logic uses an XML-based format for its sample library.

    Args:
        metadata_list: List of generic metadata dictionaries

    Returns:
        XML Element tree root
    """
    # Create root element
    root = ET.Element("plist")
    root.set("version", "1.0")

    # Create dict container
    dict_elem = ET.SubElement(root, "dict")

    # Version
    key_version = ET.SubElement(dict_elem, "key")
    key_version.text = "Version"
    string_version = ET.SubElement(dict_elem, "string")
    string_version.text = "1.0"

    # Samples array
    key_samples = ET.SubElement(dict_elem, "key")
    key_samples.text = "Samples"
    array_samples = ET.SubElement(dict_elem, "array")

    for item in metadata_list:
        sample_dict = ET.SubElement(array_samples, "dict")

        # Path
        key_path = ET.SubElement(sample_dict, "key")
        key_path.text = "Path"
        string_path = ET.SubElement(sample_dict, "string")
        string_path.text = item.get("path", "")

        # Name
        key_name = ET.SubElement(sample_dict, "key")
        key_name.text = "Name"
        string_name = ET.SubElement(sample_dict, "string")
        string_name.text = item.get("filename", "")

        # Tempo
        if item.get("bpm"):
            key_tempo = ET.SubElement(sample_dict, "key")
            key_tempo.text = "Tempo"
            integer_tempo = ET.SubElement(sample_dict, "integer")
            integer_tempo.text = str(item["bpm"])

        # Key
        if item.get("key"):
            key_key = ET.SubElement(sample_dict, "key")
            key_key.text = "Key"
            string_key = ET.SubElement(sample_dict, "string")
            string_key.text = item["key"]

        # Duration
        if item.get("duration"):
            key_dur = ET.SubElement(sample_dict, "key")
            key_dur.text = "Duration"
            real_dur = ET.SubElement(sample_dict, "real")
            real_dur.text = str(item["duration"])

        # Tags
        if item.get("tags"):
            key_tags = ET.SubElement(sample_dict, "key")
            key_tags.text = "Tags"
            array_tags = ET.SubElement(sample_dict, "array")
            for tag in item["tags"]:
                string_tag = ET.SubElement(array_tags, "string")
                string_tag.text = tag

        # Color (default: none)
        key_color = ET.SubElement(sample_dict, "key")
        key_color.text = "Color"
        integer_color = ET.SubElement(sample_dict, "integer")
        integer_color.text = "0"

    return root


def export_to_logic_xml(output_path: Path, metadata_list: list[dict[str, Any]]) -> Path:
    """
    Export to Logic Pro XML format.

    Args:
        output_path: Output file path
        metadata_list: List of metadata dictionaries

    Returns:
        Path to created file
    """
    root = convert_to_logic_format(metadata_list)

    # Write XML
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(output_path, encoding="utf-8", xml_declaration=True)

    return output_path


def run_export_logic(output_path: Path | None = None) -> Path:
    """
    Export to Logic Pro format.

    Args:
        output_path: Optional custom output path

    Returns:
        Path to created file
    """
    metadata_list = export_all_metadata()

    if output_path is None:
        output_path = DATA_DIR / "logic_library.xml"
    else:
        output_path = Path(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    return export_to_logic_xml(output_path, metadata_list)
