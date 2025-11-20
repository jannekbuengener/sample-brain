# src/export_fl.py
"""
FL Studio adapter for sample metadata export.
Generates FL Studio Browser Tags format.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any
from .metadata import export_all_metadata
from .config import DATA_DIR, SAMPLE_ROOTS


def convert_to_fl_format(metadata_list: list[dict[str, Any]], sample_roots: list[Path]) -> tuple[str, set[str]]:
    """
    Convert generic metadata to FL Studio Browser Tags format.

    FL Studio uses a CSV-like format with a header defining all tags,
    followed by rows with file paths and their tags.

    Args:
        metadata_list: List of generic metadata dictionaries
        sample_roots: List of sample root directories

    Returns:
        Tuple of (tags_file_content, all_tags_set)
    """
    all_tags = set()
    lines = []

    for item in metadata_list:
        path = item.get("path", "")
        relpath = item.get("relpath", "")
        tags = item.get("tags", [])

        # Add all tags to global set
        for tag in tags:
            all_tags.add(tag)

        # Build FL-compatible path
        if sample_roots and relpath:
            base = Path(sample_roots[0]) if sample_roots else Path(path).drive + "\\"
            lib_root_lower = str(Path(base)).lower().rstrip("\\/") + "\\"
            final_path = lib_root_lower + relpath.replace("/", "\\")
        else:
            final_path = path

        # Build line: "path",tag1,tag2,tag3
        tag_str = ",".join(tags) if tags else ""
        lines.append(f'"{final_path}"' + ("," + tag_str if tag_str else ""))

    return lines, all_tags


def export_to_fl_tags(
    output_path: Path,
    metadata_list: list[dict[str, Any]],
    sample_roots: list[Path]
) -> Path:
    """
    Export to FL Studio Browser Tags format.

    Args:
        output_path: Output file path
        metadata_list: List of metadata dictionaries
        sample_roots: List of sample root directories

    Returns:
        Path to created file
    """
    lines, all_tags = convert_to_fl_format(metadata_list, sample_roots)

    # Build header: @TagCase=*,Tag1,Tag2,Tag3,...
    header = "@TagCase=*"
    for tag in sorted(all_tags, key=lambda x: x.lower()):
        # Quote tags with special characters
        if re.search(r'[,\s"]', tag):
            header += "," + '"' + tag.replace('"', '') + '"'
        else:
            header += "," + tag

    # Write file
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header + "\n")
        for line in lines:
            f.write(line + "\n")

    return output_path


def run_export_fl(
    output_path: Path | None = None,
    fl_user_data: Path | None = None
) -> Path:
    """
    Export to FL Studio Browser Tags format.

    Args:
        output_path: Optional custom output path
        fl_user_data: Optional FL Studio user data directory

    Returns:
        Path to created Tags file
    """
    # Generate metadata
    metadata_list = export_all_metadata()

    # Determine output path
    if output_path is None:
        if fl_user_data is None:
            # Default to data directory
            output_path = DATA_DIR / "fl_browser_tags.txt"
        else:
            # FL Studio standard location
            tags_path = Path(fl_user_data) / "FL Studio" / "Settings" / "Browser" / "Tags"
            tags_path.parent.mkdir(parents=True, exist_ok=True)
            output_path = tags_path
    else:
        output_path = Path(output_path)

    # Ensure parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Export
    return export_to_fl_tags(output_path, metadata_list, SAMPLE_ROOTS)
