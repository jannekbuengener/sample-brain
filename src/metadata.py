# src/metadata.py
"""
DAW-neutral metadata consolidation module.
Aggregates all analyzed features into standardized metadata records.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
import re
import json
from sqlalchemy import text
from .db import init_db
from .config import DATA_DIR

# Configuration
CONF_KEY_MIN = 0.55  # Minimum confidence for key detection


def _load_regex_map() -> dict:
    """Load filename regex patterns for tag extraction."""
    p = DATA_DIR / "filename_tag_regex.json"
    if not p.exists():
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _parse_filename_tags(filename: str, regex_map: dict) -> list[str]:
    """Extract tags from filename using regex patterns."""
    tags = []
    name_lower = filename.lower()

    # Instrument patterns
    for instrument, patterns in regex_map.get("instrument", {}).items():
        for pattern in patterns:
            try:
                if re.search(pattern, name_lower):
                    tags.append(instrument)
                    break
            except re.error:
                continue

    # Mood patterns
    for mood, patterns in regex_map.get("mood", {}).items():
        for pattern in patterns:
            try:
                if re.search(pattern, name_lower):
                    tags.append(mood.capitalize())
                    break
            except re.error:
                continue

    # Genre patterns
    for genre, patterns in regex_map.get("genre", {}).items():
        for pattern in patterns:
            try:
                if re.search(pattern, name_lower):
                    tags.append(genre)
                    break
            except re.error:
                continue

    return tags


def _normalize_key(key: str | None, confidence: float | None) -> str | None:
    """Normalize key notation to standard format."""
    if not key or (confidence is not None and confidence < CONF_KEY_MIN):
        return None

    # Standardize notation
    k = key.replace("min", "m").replace("maj", "").upper()
    if len(k) == 1:
        k = k + "maj"
    if k.endswith("M"):
        k = k[:-1] + "maj"
    if k.endswith("m"):
        k = k[:-1] + "min"
    return k


def _normalize_bpm(bpm: float | None) -> int | None:
    """Normalize BPM to integer."""
    if not bpm or bpm <= 0:
        return None
    return int(round(bpm))


def _classify_brightness(brightness: float | None) -> str | None:
    """Classify brightness into categories."""
    if brightness is None:
        return None
    if brightness < 1500:
        return "Dark"
    if brightness > 3500:
        return "Bright"
    return None


def _classify_loudness(loudness: float | None) -> str | None:
    """Classify loudness into categories."""
    if loudness is None:
        return None
    if loudness > -18:
        return "Punchy"
    if loudness < -28:
        return "Clean"
    return None


def _classify_duration(duration: float | None, clazz: str | None) -> str | None:
    """Classify duration class."""
    if clazz == "oneshot":
        return "OneShot"
    if clazz == "loop":
        return "Loop"
    return None


def build_sample_metadata(
    sample_id: int,
    path: str,
    relpath: str | None,
    duration: float | None,
    features: dict[str, Any]
) -> dict[str, Any]:
    """
    Build consolidated metadata for a single sample.

    Args:
        sample_id: Database ID
        path: Absolute file path
        relpath: Relative path from sample root
        duration: Duration in seconds
        features: Dictionary of analyzed features from database

    Returns:
        Dictionary with standardized metadata
    """
    filename = Path(path).name
    regex_map = _load_regex_map()

    # Core metadata
    metadata = {
        "sample_id": sample_id,
        "path": path,
        "relpath": relpath,
        "filename": filename,
        "duration": round(duration, 2) if duration else None,
    }

    # Musical features
    bpm = _normalize_bpm(features.get("bpm"))
    key = _normalize_key(features.get("key"), features.get("key_conf"))

    if bpm:
        metadata["bpm"] = bpm
    if key:
        metadata["key"] = key

    # Audio characteristics
    metadata["loudness"] = round(features.get("loudness"), 2) if features.get("loudness") is not None else None
    metadata["brightness"] = round(features.get("brightness"), 2) if features.get("brightness") is not None else None

    # Tags collection
    tags = []

    # 1. Predicted type (from autotype)
    if features.get("pred_type"):
        tags.append(features["pred_type"])

    # 2. Filename-derived tags
    filename_tags = _parse_filename_tags(filename, regex_map)
    for tag in filename_tags[:3]:  # Limit to top 3
        if tag not in tags:
            tags.append(tag)

    # 3. Character tags
    brightness_tag = _classify_brightness(features.get("brightness"))
    if brightness_tag and brightness_tag not in tags:
        tags.append(brightness_tag)

    loudness_tag = _classify_loudness(features.get("loudness"))
    if loudness_tag and loudness_tag not in tags:
        tags.append(loudness_tag)

    # 4. Duration class
    duration_tag = _classify_duration(duration, features.get("class"))
    if duration_tag and duration_tag not in tags:
        tags.append(duration_tag)

    # 5. Atmospheric tag for long samples
    if duration and duration > 6 and "Atmospheric" not in tags:
        pred_type = features.get("pred_type", "")
        if pred_type in ["Pad", "Drone", "Texture", "AmbientLayer"] or not pred_type:
            tags.append("Atmospheric")

    # 6. BPM tag
    if bpm:
        tags.append(f"{bpm}BPM")

    # 7. Key tag
    if key:
        tags.append(key)

    metadata["tags"] = tags

    return metadata


def export_all_metadata() -> list[dict[str, Any]]:
    """
    Export metadata for all samples in the database.

    Returns:
        List of metadata dictionaries
    """
    engine = init_db()

    with engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT
                s.id, s.path, s.relpath, s.duration,
                f.bpm, f.key, f.key_conf, f.loudness, f.brightness,
                f.class, f.pred_type
            FROM samples s
            LEFT JOIN features f ON f.sample_id = s.id
            ORDER BY s.id
        """)).fetchall()

    metadata_list = []

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
        metadata_list.append(metadata)

    return metadata_list
