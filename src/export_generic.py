# src/export_generic.py
"""
Generic, DAW-neutral export module.
Exports sample metadata to various formats: JSON, CSV, YAML.
"""
from __future__ import annotations
import json
import csv
from pathlib import Path
from typing import Literal
from .metadata import export_all_metadata
from .config import DATA_DIR


ExportFormat = Literal["json", "csv", "yaml"]


def export_to_json(output_path: Path, metadata_list: list[dict]) -> None:
    """
    Export metadata to JSON format.

    Args:
        output_path: Output file path
        metadata_list: List of metadata dictionaries
    """
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(metadata_list, f, indent=2, ensure_ascii=False)


def export_to_csv(output_path: Path, metadata_list: list[dict]) -> None:
    """
    Export metadata to CSV format.

    Args:
        output_path: Output file path
        metadata_list: List of metadata dictionaries
    """
    if not metadata_list:
        return

    # Flatten tags into comma-separated string
    flattened = []
    for item in metadata_list:
        flat_item = item.copy()
        flat_item["tags"] = ",".join(item.get("tags", []))
        flattened.append(flat_item)

    # Get all unique keys
    fieldnames = list(flattened[0].keys())

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flattened)


def export_to_yaml(output_path: Path, metadata_list: list[dict]) -> None:
    """
    Export metadata to YAML format (requires PyYAML).

    Args:
        output_path: Output file path
        metadata_list: List of metadata dictionaries
    """
    try:
        import yaml
    except ImportError:
        raise ImportError(
            "PyYAML is required for YAML export. Install with: pip install pyyaml"
        )

    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(metadata_list, f, default_flow_style=False, allow_unicode=True)


def run_export(
    format: ExportFormat = "json",
    output_path: Path | None = None,
) -> Path:
    """
    Export all sample metadata to specified format.

    Args:
        format: Output format ('json', 'csv', 'yaml')
        output_path: Optional custom output path

    Returns:
        Path to created export file
    """
    # Generate metadata
    metadata_list = export_all_metadata()

    # Determine output path
    if output_path is None:
        output_path = DATA_DIR / f"catalog_export.{format}"
    else:
        output_path = Path(output_path)

    # Ensure parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Export based on format
    if format == "json":
        export_to_json(output_path, metadata_list)
    elif format == "csv":
        export_to_csv(output_path, metadata_list)
    elif format == "yaml":
        export_to_yaml(output_path, metadata_list)
    else:
        raise ValueError(f"Unsupported format: {format}")

    return output_path


def export_single_sample(sample_id: int, format: ExportFormat = "json") -> dict | str:
    """
    Export metadata for a single sample.

    Args:
        sample_id: Database ID of the sample
        format: Output format

    Returns:
        Metadata as dict (json) or string (csv/yaml)
    """
    metadata_list = export_all_metadata()

    # Find sample
    sample_metadata = None
    for item in metadata_list:
        if item["sample_id"] == sample_id:
            sample_metadata = item
            break

    if sample_metadata is None:
        raise ValueError(f"Sample ID {sample_id} not found")

    if format == "json":
        return sample_metadata
    elif format == "csv":
        # Return as CSV row
        flat = sample_metadata.copy()
        flat["tags"] = ",".join(sample_metadata.get("tags", []))
        return ",".join(str(v) for v in flat.values())
    elif format == "yaml":
        import yaml
        return yaml.dump([sample_metadata], default_flow_style=False, allow_unicode=True)
    else:
        raise ValueError(f"Unsupported format: {format}")
