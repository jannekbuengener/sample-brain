# src/export_extended.py
"""
Extended export formats: XML, Parquet, SQLite Views.
"""
from __future__ import annotations
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from .metadata import export_all_metadata
from .config import DATA_DIR
from .db import init_db
from sqlalchemy import text


def export_to_xml(output_path: Path, metadata_list: list[dict[str, Any]]) -> Path:
    """
    Export metadata to XML format.

    Args:
        output_path: Output file path
        metadata_list: List of metadata dictionaries

    Returns:
        Path to created file
    """
    # Create root element
    root = ET.Element("SampleCatalog")
    root.set("version", "1.0")
    root.set("total_samples", str(len(metadata_list)))

    # Create samples container
    samples_elem = ET.SubElement(root, "Samples")

    for item in metadata_list:
        sample_elem = ET.SubElement(samples_elem, "Sample")
        sample_elem.set("id", str(item.get("sample_id", "")))

        # Basic info
        path_elem = ET.SubElement(sample_elem, "Path")
        path_elem.text = item.get("path", "")

        if item.get("relpath"):
            relpath_elem = ET.SubElement(sample_elem, "RelativePath")
            relpath_elem.text = item["relpath"]

        filename_elem = ET.SubElement(sample_elem, "Filename")
        filename_elem.text = item.get("filename", "")

        # Musical properties
        if item.get("bpm") or item.get("key") or item.get("duration"):
            musical_elem = ET.SubElement(sample_elem, "MusicalProperties")

            if item.get("bpm"):
                bpm_elem = ET.SubElement(musical_elem, "BPM")
                bpm_elem.text = str(item["bpm"])

            if item.get("key"):
                key_elem = ET.SubElement(musical_elem, "Key")
                key_elem.text = item["key"]

            if item.get("duration"):
                dur_elem = ET.SubElement(musical_elem, "Duration")
                dur_elem.text = str(item["duration"])

        # Audio properties
        if item.get("loudness") is not None or item.get("brightness") is not None:
            audio_elem = ET.SubElement(sample_elem, "AudioProperties")

            if item.get("loudness") is not None:
                loud_elem = ET.SubElement(audio_elem, "Loudness")
                loud_elem.text = str(item["loudness"])

            if item.get("brightness") is not None:
                bright_elem = ET.SubElement(audio_elem, "Brightness")
                bright_elem.text = str(item["brightness"])

        # Tags
        if item.get("tags"):
            tags_elem = ET.SubElement(sample_elem, "Tags")
            for tag in item["tags"]:
                tag_elem = ET.SubElement(tags_elem, "Tag")
                tag_elem.text = tag

    # Write to file
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")  # Pretty print
    tree.write(output_path, encoding="utf-8", xml_declaration=True)

    return output_path


def export_to_parquet(output_path: Path, metadata_list: list[dict[str, Any]]) -> Path:
    """
    Export metadata to Parquet format (requires pyarrow or fastparquet).

    Args:
        output_path: Output file path
        metadata_list: List of metadata dictionaries

    Returns:
        Path to created file
    """
    try:
        import pandas as pd
    except ImportError:
        raise ImportError(
            "pandas is required for Parquet export. Install with: pip install pandas pyarrow"
        )

    # Flatten tags for DataFrame
    flattened = []
    for item in metadata_list:
        flat_item = item.copy()
        flat_item["tags"] = "|".join(item.get("tags", []))  # Use | as separator
        flattened.append(flat_item)

    # Create DataFrame
    df = pd.DataFrame(flattened)

    # Write to Parquet
    df.to_parquet(output_path, index=False, engine="pyarrow")

    return output_path


def create_sqlite_views(view_prefix: str = "v_") -> dict[str, str]:
    """
    Create SQLite views for common metadata queries.

    Args:
        view_prefix: Prefix for view names

    Returns:
        Dictionary of created view names and their SQL
    """
    engine = init_db()
    views = {}

    # View 1: Complete metadata (denormalized)
    view_complete = f"{view_prefix}complete_metadata"
    sql_complete = f"""
    CREATE VIEW IF NOT EXISTS {view_complete} AS
    SELECT
        s.id AS sample_id,
        s.path,
        s.relpath,
        s.duration,
        s.samplerate,
        s.channels,
        s.size_bytes,
        f.bpm,
        f.key,
        f.key_conf,
        f.loudness,
        f.brightness,
        f.class AS duration_class,
        f.pred_type
    FROM samples s
    LEFT JOIN features f ON f.sample_id = s.id
    """

    # View 2: Samples by BPM range
    view_bpm = f"{view_prefix}by_bpm"
    sql_bpm = f"""
    CREATE VIEW IF NOT EXISTS {view_bpm} AS
    SELECT
        CASE
            WHEN f.bpm < 90 THEN '< 90'
            WHEN f.bpm BETWEEN 90 AND 110 THEN '90-110'
            WHEN f.bpm BETWEEN 110 AND 130 THEN '110-130'
            WHEN f.bpm BETWEEN 130 AND 150 THEN '130-150'
            WHEN f.bpm BETWEEN 150 AND 170 THEN '150-170'
            ELSE '> 170'
        END AS bpm_range,
        COUNT(*) AS sample_count,
        AVG(f.bpm) AS avg_bpm
    FROM samples s
    JOIN features f ON f.sample_id = s.id
    WHERE f.bpm IS NOT NULL
    GROUP BY bpm_range
    ORDER BY MIN(f.bpm)
    """

    # View 3: Samples by key
    view_key = f"{view_prefix}by_key"
    sql_key = f"""
    CREATE VIEW IF NOT EXISTS {view_key} AS
    SELECT
        f.key,
        COUNT(*) AS sample_count,
        AVG(f.key_conf) AS avg_confidence
    FROM samples s
    JOIN features f ON f.sample_id = s.id
    WHERE f.key IS NOT NULL
    GROUP BY f.key
    ORDER BY sample_count DESC
    """

    # View 4: Samples by type
    view_type = f"{view_prefix}by_type"
    sql_type = f"""
    CREATE VIEW IF NOT EXISTS {view_type} AS
    SELECT
        f.pred_type,
        COUNT(*) AS sample_count,
        AVG(s.duration) AS avg_duration
    FROM samples s
    JOIN features f ON f.sample_id = s.id
    WHERE f.pred_type IS NOT NULL
    GROUP BY f.pred_type
    ORDER BY sample_count DESC
    """

    # View 5: Audio characteristics summary
    view_audio = f"{view_prefix}audio_summary"
    sql_audio = f"""
    CREATE VIEW IF NOT EXISTS {view_audio} AS
    SELECT
        CASE
            WHEN f.loudness > -18 THEN 'Punchy'
            WHEN f.loudness < -28 THEN 'Clean'
            ELSE 'Medium'
        END AS loudness_category,
        CASE
            WHEN f.brightness > 3500 THEN 'Bright'
            WHEN f.brightness < 1500 THEN 'Dark'
            ELSE 'Neutral'
        END AS brightness_category,
        COUNT(*) AS sample_count
    FROM samples s
    JOIN features f ON f.sample_id = s.id
    WHERE f.loudness IS NOT NULL AND f.brightness IS NOT NULL
    GROUP BY loudness_category, brightness_category
    ORDER BY sample_count DESC
    """

    # Create all views
    view_sqls = {
        view_complete: sql_complete,
        view_bpm: sql_bpm,
        view_key: sql_key,
        view_type: sql_type,
        view_audio: sql_audio,
    }

    with engine.begin() as conn:
        for view_name, sql in view_sqls.items():
            conn.execute(text(sql))
            views[view_name] = sql

    return views


def export_sqlite_views_schema(output_path: Path | None = None) -> Path:
    """
    Export SQLite views schema to SQL file.

    Args:
        output_path: Optional custom output path

    Returns:
        Path to created SQL file
    """
    if output_path is None:
        output_path = DATA_DIR / "sqlite_views_schema.sql"
    else:
        output_path = Path(output_path)

    # Create views and get SQL
    views = create_sqlite_views()

    # Write schema file
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("-- Sample Brain SQLite Views Schema\n")
        f.write("-- Auto-generated metadata views\n\n")

        for view_name, sql in views.items():
            f.write(f"-- View: {view_name}\n")
            f.write(sql)
            f.write(";\n\n")

    return output_path


def run_export_xml(output_path: Path | None = None) -> Path:
    """
    Export to XML format.

    Args:
        output_path: Optional custom output path

    Returns:
        Path to created file
    """
    metadata_list = export_all_metadata()

    if output_path is None:
        output_path = DATA_DIR / "catalog_export.xml"
    else:
        output_path = Path(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    return export_to_xml(output_path, metadata_list)


def run_export_parquet(output_path: Path | None = None) -> Path:
    """
    Export to Parquet format.

    Args:
        output_path: Optional custom output path

    Returns:
        Path to created file
    """
    metadata_list = export_all_metadata()

    if output_path is None:
        output_path = DATA_DIR / "catalog_export.parquet"
    else:
        output_path = Path(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    return export_to_parquet(output_path, metadata_list)


def run_create_sqlite_views() -> dict[str, str]:
    """
    Create SQLite views in the database.

    Returns:
        Dictionary of created view names and SQL
    """
    return create_sqlite_views()
