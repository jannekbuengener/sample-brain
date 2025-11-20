# src/export_generic.py
"""
Generic, DAW-neutral export module.
Exports sample metadata to various formats: JSON, CSV, YAML.
Supports streaming for large libraries.
"""
from __future__ import annotations
import json
import csv
from pathlib import Path
from typing import Literal, Iterator, Callable
from .metadata import export_all_metadata
from .config import DATA_DIR
from sqlalchemy import text
from .db import init_db


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


# ===== Streaming Export for Large Libraries =====


def stream_metadata_chunks(chunk_size: int = 1000) -> Iterator[list[dict]]:
    """
    Stream metadata in chunks for memory-efficient processing.

    Args:
        chunk_size: Number of samples per chunk

    Yields:
        Lists of metadata dictionaries
    """
    engine = init_db()

    # Get total count
    with engine.begin() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM samples")).fetchone()[0]

    # Process in chunks
    offset = 0
    while offset < total:
        with engine.begin() as conn:
            rows = conn.execute(text(f"""
                SELECT
                    s.id, s.path, s.relpath, s.duration,
                    f.bpm, f.key, f.key_conf, f.loudness, f.brightness,
                    f.class, f.pred_type
                FROM samples s
                LEFT JOIN features f ON f.sample_id = s.id
                ORDER BY s.id
                LIMIT {chunk_size} OFFSET {offset}
            """)).fetchall()

        if not rows:
            break

        # Build metadata for this chunk
        from .metadata import build_sample_metadata

        chunk = []
        for row in rows:
            sid, path, relpath, duration, bpm, key, key_conf, loudness, brightness, clazz, pred_type = row

            features = {
                "bpm": bpm,
                "key": key,
                "key_conf": key_conf,
                "loudness": loudness,
                "brightness": brightness,
                "class": clazz,
                "pred_type": pred_type,
            }

            metadata = build_sample_metadata(sid, path, relpath, duration, features)
            chunk.append(metadata)

        yield chunk
        offset += chunk_size


def export_streaming_json(
    output_path: Path,
    chunk_size: int = 1000,
    progress_callback: Callable[[int, int], None] | None = None
) -> Path:
    """
    Export to JSON using streaming for large libraries.

    Args:
        output_path: Output file path
        chunk_size: Samples per chunk
        progress_callback: Optional callback(processed, total)

    Returns:
        Path to created file
    """
    engine = init_db()
    with engine.begin() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM samples")).fetchone()[0]

    # Write JSON incrementally
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("[\n")

        first_chunk = True
        processed = 0

        for chunk in stream_metadata_chunks(chunk_size):
            for i, item in enumerate(chunk):
                # Add comma separator between items
                if not first_chunk or i > 0:
                    f.write(",\n")
                first_chunk = False

                # Write item
                json.dump(item, f, indent=2, ensure_ascii=False)
                processed += 1

                # Progress callback
                if progress_callback:
                    progress_callback(processed, total)

        f.write("\n]")

    return output_path


def export_streaming_csv(
    output_path: Path,
    chunk_size: int = 1000,
    progress_callback: Callable[[int, int], None] | None = None
) -> Path:
    """
    Export to CSV using streaming for large libraries.

    Args:
        output_path: Output file path
        chunk_size: Samples per chunk
        progress_callback: Optional callback(processed, total)

    Returns:
        Path to created file
    """
    engine = init_db()
    with engine.begin() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM samples")).fetchone()[0]

    # Determine fieldnames from first chunk
    first_chunk = next(stream_metadata_chunks(chunk_size))
    if not first_chunk:
        return output_path

    # Flatten first item to get fieldnames
    flat = first_chunk[0].copy()
    flat["tags"] = ",".join(first_chunk[0].get("tags", []))
    fieldnames = list(flat.keys())

    # Write CSV incrementally
    processed = 0
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        # Write first chunk
        for item in first_chunk:
            flat_item = item.copy()
            flat_item["tags"] = ",".join(item.get("tags", []))
            writer.writerow(flat_item)
            processed += 1

            if progress_callback:
                progress_callback(processed, total)

        # Write remaining chunks
        for chunk in stream_metadata_chunks(chunk_size):
            for item in chunk:
                flat_item = item.copy()
                flat_item["tags"] = ",".join(item.get("tags", []))
                writer.writerow(flat_item)
                processed += 1

                if progress_callback:
                    progress_callback(processed, total)

    return output_path


def run_export_streaming(
    format: ExportFormat = "json",
    output_path: Path | None = None,
    chunk_size: int = 1000,
    show_progress: bool = True
) -> Path:
    """
    Export using streaming (memory-efficient for large libraries).

    Args:
        format: Output format
        output_path: Optional custom output path
        chunk_size: Samples per chunk
        show_progress: Show progress bar

    Returns:
        Path to created export file
    """
    # Determine output path
    if output_path is None:
        output_path = DATA_DIR / f"catalog_export_streaming.{format}"
    else:
        output_path = Path(output_path)

    # Ensure parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Progress callback
    progress_fn = None
    if show_progress:
        def progress_fn(processed: int, total: int):
            percent = (processed / total) * 100 if total > 0 else 0
            print(f"\rExporting: {processed}/{total} ({percent:.1f}%)", end="", flush=True)

    # Export based on format
    if format == "json":
        result = export_streaming_json(output_path, chunk_size, progress_fn)
    elif format == "csv":
        result = export_streaming_csv(output_path, chunk_size, progress_fn)
    elif format == "yaml":
        # YAML doesn't support streaming well, fall back to regular export
        metadata_list = export_all_metadata()
        export_to_yaml(output_path, metadata_list)
        result = output_path
    else:
        raise ValueError(f"Unsupported format: {format}")

    if show_progress:
        print()  # New line after progress

    return result
