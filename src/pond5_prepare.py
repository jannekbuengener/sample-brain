"""Pond5 local readiness bundle generator and validator (#451).

This module prepares a local, deterministic Pond5 readiness bundle consisting
of ``pond5_metadata.json``, ``pond5.csv``, and ``pond5_readiness.json``.
It reuses existing Sample Brain analysis without modifying source audio or
performing remote/network/browser activity.
"""

from __future__ import annotations

import aifc
from collections.abc import Mapping, Sequence
import csv
import json
import math
from pathlib import Path
import re
from typing import Any
import wave

import soundfile as sf

from .context_analyze import ContextAnalyzeError, analyze_context_file_cached
from .pond5_profile import profile_hold_reasons, resolve_pond5_profile
from .stock_music_analysis import produce_stock_music_analysis


POND5_READINESS_DOCUMENT_TYPE = "sample_brain.pond5_readiness"
POND5_METADATA_DOCUMENT_TYPE = "sample_brain.pond5_metadata"
POND5_READINESS_SCHEMA_VERSION = "1.0.0"

_VALID_FORMATS = frozenset({"WAV", "AIFF"})
_VALID_BIT_DEPTHS = frozenset({16, 24, 32})
_VALID_SAMPLE_RATES = frozenset({44100, 48000, 96000})
_MAX_DURATION_SEC = 600.0  # < 10 minutes
_MAX_TITLE_LEN = 80
_MAX_DESC_LEN = 500
_MAX_KEYWORDS = 50

_PROHIBITED_LEAKAGE_TERMS = frozenset(
    {
        "sounds like",
        "in the style of",
        "style of",
        "similar to",
        "zimmer",
        "hans zimmer",
        "drake",
        "disney",
        "marvel",
        "netflix",
        "apple",
        "nike",
        "adidas",
        "sony",
        "paramount",
        "universal",
        "warner",
        "nintendo",
        "playstation",
        "xbox",
    }
)

_SAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9_.]")


def probe_submission_technical(file_path: Path, source_hash: dict[str, str]) -> dict[str, Any]:
    """Probe the submission file container/header metadata portably."""

    file_path = Path(file_path)
    fmt: str | None = None
    bit_depth: int | None = None
    sample_rate_hz: int | None = None
    channels: int | None = None
    duration_sec: float | None = None
    probe_status = "ok"

    ext = file_path.suffix.lower()
    if ext in {".wav", ".wave"}:
        fmt = "WAV"
        try:
            with wave.open(str(file_path), "rb") as w:
                channels = w.getnchannels()
                bit_depth = w.getsampwidth() * 8
                sample_rate_hz = w.getframerate()
                nframes = w.getnframes()
                if sample_rate_hz > 0:
                    duration_sec = float(nframes) / float(sample_rate_hz)
        except Exception:
            pass

    if fmt is None and ext in {".aif", ".aiff"}:
        fmt = "AIFF"
        try:
            with aifc.open(str(file_path), "rb") as a:
                channels = a.getnchannels()
                bit_depth = a.getsampwidth() * 8
                sample_rate_hz = a.getframerate()
                nframes = a.getnframes()
                if sample_rate_hz > 0:
                    duration_sec = float(nframes) / float(sample_rate_hz)
        except Exception:
            pass

    if sample_rate_hz is None or bit_depth is None or channels is None:
        try:
            info = sf.info(str(file_path))
            if fmt is None:
                fmt = str(info.format).upper()
            if sample_rate_hz is None:
                sample_rate_hz = int(info.samplerate)
            if channels is None:
                channels = int(info.channels)
            if duration_sec is None:
                duration_sec = float(info.duration)
            if bit_depth is None:
                subtype = str(info.subtype).upper()
                if "16" in subtype:
                    bit_depth = 16
                elif "24" in subtype:
                    bit_depth = 24
                elif "32" in subtype or "FLOAT" in subtype:
                    bit_depth = 32
        except Exception:
            probe_status = "failed"

    if probe_status == "failed" or fmt is None or sample_rate_hz is None:
        return {
            "status": "failed",
            "format": {"status": "failed", "value": None, "evidence_refs": ["submission_file_header_probe"], "source_ref": "submission_file_header_probe"},
            "bit_depth": {"status": "failed", "value": None, "evidence_refs": ["submission_file_header_probe"], "source_ref": "submission_file_header_probe"},
            "sample_rate_hz": {"status": "failed", "value": None, "evidence_refs": ["submission_file_header_probe"], "source_ref": "submission_file_header_probe"},
            "channels": {"status": "failed", "value": None, "evidence_refs": ["submission_file_header_probe"], "source_ref": "submission_file_header_probe"},
            "duration_sec": {"status": "failed", "value": None, "evidence_refs": ["submission_file_header_probe"], "source_ref": "submission_file_header_probe"},
        }

    return {
        "status": "ok",
        "format": {"status": "ok", "value": fmt, "evidence_refs": ["submission_file_header_probe"], "source_ref": "submission_file_header_probe"},
        "bit_depth": {"status": "ok" if bit_depth is not None else "failed", "value": bit_depth, "evidence_refs": ["submission_file_header_probe"], "source_ref": "submission_file_header_probe"},
        "sample_rate_hz": {"status": "ok", "value": sample_rate_hz, "evidence_refs": ["submission_file_header_probe"], "source_ref": "submission_file_header_probe"},
        "channels": {"status": "ok", "value": channels, "evidence_refs": ["submission_file_header_probe"], "source_ref": "submission_file_header_probe"},
        "duration_sec": {"status": "ok" if duration_sec is not None else "failed", "value": duration_sec, "evidence_refs": ["submission_file_header_probe"], "source_ref": "submission_file_header_probe"},
    }


def suggest_target_upload_filename(original_filename: str) -> str:
    """Return deterministic, safe Pond5 target upload filename suggestion."""
    stem = Path(original_filename).stem
    suffix = Path(original_filename).suffix
    safe_stem = _SAFE_FILENAME_CHARS.sub("_", stem)
    # Collapse consecutive underscores
    while "__" in safe_stem:
        safe_stem = safe_stem.replace("__", "_")
    safe_stem = safe_stem.strip("_")
    if not safe_stem:
        safe_stem = "track"
    return f"{safe_stem}{suffix}"


def _detect_leakage(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in _PROHIBITED_LEAKAGE_TERMS)


def _collect_keywords(
    stock_analysis: Mapping[str, Any],
    explicit_keywords: Sequence[str] = (),
) -> tuple[list[str], str]:
    """Extract, rank, and deduplicate keywords from semantic descriptors and overrides."""
    keywords: list[str] = []
    seen: set[str] = set()

    def _add(term: str | None) -> None:
        if not term or not isinstance(term, str):
            return
        cleaned = term.strip().lower()
        if not cleaned or cleaned in seen or _detect_leakage(cleaned):
            return
        seen.add(cleaned)
        keywords.append(cleaned)

    for kw in explicit_keywords:
        _add(kw)

    semantic = stock_analysis.get("semantic", {})
    if isinstance(semantic, Mapping):
        for field in (
            "genre",
            "subgenre",
            "mood",
            "energy_class",
            "pace_character",
            "instrumentation",
            "sound_palette",
            "production_character",
            "usage_context",
            "arrangement_character",
        ):
            val = semantic.get(field)
            if isinstance(val, Mapping):
                if val.get("status") == "ok" and isinstance(val.get("value"), str):
                    _add(val["value"])
                items = val.get("items")
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, Mapping) and isinstance(item.get("value"), str):
                            _add(item["value"])

    deduped = keywords[:_MAX_KEYWORDS]
    status = "ok" if deduped else "no_result"
    return deduped, status


def generate_pond5_listing(
    source_filename: str,
    stock_analysis: Mapping[str, Any],
    profile: Mapping[str, Any],
    *,
    per_track_overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate listing data for Pond5 submission."""

    overrides = per_track_overrides or {}
    listing_overrides = overrides.get("listing", {}) if isinstance(overrides, Mapping) else {}

    # Target Upload Filename
    target_upload_filename = suggest_target_upload_filename(source_filename)

    # Title
    explicit_title = listing_overrides.get("title") if isinstance(listing_overrides, Mapping) else None
    if explicit_title is not None and isinstance(explicit_title, str) and explicit_title.strip():
        raw_title = explicit_title.strip()
        title_source = "per_track_override"
    else:
        stem = Path(source_filename).stem.replace("_", " ").replace("-", " ")
        raw_title = " ".join(word.capitalize() for word in stem.split())
        title_source = "derived_from_source"

    # Description
    explicit_desc = listing_overrides.get("description") if isinstance(listing_overrides, Mapping) else None
    if explicit_desc is not None and isinstance(explicit_desc, str) and explicit_desc.strip():
        raw_desc = explicit_desc.strip()
        desc_source = "per_track_override"
    else:
        # Build description from semantic descriptors if available
        parts = []
        semantic = stock_analysis.get("semantic", {})
        if isinstance(semantic, Mapping):
            genre_val = semantic.get("genre", {}).get("value") if isinstance(semantic.get("genre"), Mapping) else None
            mood_val = semantic.get("mood", {}).get("value") if isinstance(semantic.get("mood"), Mapping) else None
            if genre_val or mood_val:
                desc_parts = [p for p in (mood_val, genre_val, "music track") if p]
                parts.append(f"A {' '.join(desc_parts)}.")
        raw_desc = " ".join(parts) if parts else ""
        desc_source = "derived_from_semantic" if raw_desc else "none"

    # Keywords
    explicit_kws = listing_overrides.get("keywords") if isinstance(listing_overrides, Mapping) else ()
    if not isinstance(explicit_kws, (list, tuple)):
        explicit_kws = ()
    keywords_list, kw_status = _collect_keywords(stock_analysis, explicit_kws)

    # Price
    price_obj = profile.get("listing", {}).get("price", {}) if isinstance(profile.get("listing"), Mapping) else {}
    price_val = price_obj.get("value") if isinstance(price_obj, Mapping) else None

    # Copyright
    copyright_obj = profile.get("contributor", {}).get("copyright_owner", {}) if isinstance(profile.get("contributor"), Mapping) else {}
    copyright_val = copyright_obj.get("value") if isinstance(copyright_obj, Mapping) else None

    return {
        "status": "ok",
        "title": {
            "status": "ok" if raw_title else "no_result",
            "value": raw_title,
            "evidence_refs": ["listing.title"],
            "source_ref": title_source,
        },
        "description": {
            "status": "ok" if raw_desc else "no_result",
            "value": raw_desc if raw_desc else None,
            "evidence_refs": ["listing.description"],
            "source_ref": desc_source,
        },
        "keywords": {
            "status": kw_status,
            "items": keywords_list,
            "evidence_refs": ["stock_music_analysis.semantic"],
            "source_ref": "stock_music_analysis",
        },
        "target_upload_filename": {
            "status": "ok",
            "value": target_upload_filename,
            "source_name_ref": source_filename,
            "source_ref": "target_filename_suggestion",
        },
        "price": {
            "status": price_obj.get("status", "unknown"),
            "value": price_val,
            "source_ref": price_obj.get("source_ref", "pond5_unknown"),
        },
        "copyright": {
            "status": copyright_obj.get("status", "unknown"),
            "value": copyright_val,
            "source_ref": copyright_obj.get("source_ref", "pond5_unknown"),
        },
    }


def build_platform_snapshot() -> dict[str, Any]:
    """Return normative Pond5 platform snapshot metadata."""
    return {"status": "ok", "snapshot_date": "2026-08-20", "fields": {
        "audio": {
            "required": True,
            "rules": "WAV or AIFF; 16/24/32-bit; 44.1/48/96 kHz; stereo; duration < 10 minutes",
            "csv_supported": False,
            "primary_source_url": "https://contributor.pond5.com/getting-started/preparing-your-files-2/music/",
        },
        "OriginalFilename": {
            "required": True,
            "rules": "documented mandatory Apply CSV column",
            "csv_supported": True,
            "primary_source_url": "https://contributor.pond5.com/getting-started/preparing-your-files/",
        },
        "target_upload_filename": {
            "required": True,
            "rules": "no spaces/dashes or prohibited special/accented characters",
            "csv_supported": "unknown",
            "primary_source_url": "https://contributor.pond5.com/getting-started/preparing-your-files/",
        },
        "title": {
            "required": True,
            "rules": "English; maximum 80 characters",
            "csv_supported": True,
            "primary_source_url": "https://contributor.pond5.com/getting-started/preparing-your-files/",
        },
        "description": {
            "required": False,
            "rules": "English; maximum 500 characters",
            "csv_supported": True,
            "primary_source_url": "https://contributor.pond5.com/getting-started/preparing-your-files/",
        },
        "keywords": {
            "required": True,
            "rules": "English, relevant, maximum 50; no prohibited references",
            "csv_supported": True,
            "primary_source_url": "https://contributor.pond5.com/getting-started/preparing-your-files/",
        },
        "copyright": {
            "required": False,
            "rules": "metadata field documented by Apply CSV",
            "csv_supported": True,
            "primary_source_url": "https://contributor.pond5.com/getting-started/preparing-your-files/",
        },
        "price": {
            "required": False,
            "rules": "metadata field documented by Apply CSV",
            "csv_supported": True,
            "primary_source_url": "https://contributor.pond5.com/getting-started/preparing-your-files/",
        },
        "composer": {
            "required": True,
            "rules": "required at submission",
            "csv_supported": "unknown",
            "primary_source_url": "https://contributor.pond5.com/getting-started/preparing-your-files-2/music/",
        },
        "pro": {
            "required": False,
            "rules": "may be supplied",
            "csv_supported": "unknown",
            "primary_source_url": "https://contributor.pond5.com/getting-started/preparing-your-files-2/music/",
        },
        "publisher": {
            "required": False,
            "rules": "may be supplied",
            "csv_supported": "unknown",
            "primary_source_url": "https://contributor.pond5.com/getting-started/preparing-your-files-2/music/",
        },
        "cleared_for_sampling": {
            "required": True,
            "rules": "per-file licensing choice",
            "csv_supported": "unknown",
            "primary_source_url": "https://contributor.pond5.com/getting-started/preparing-your-files-2/music/",
        },
        "rights_assertions": {
            "required": True,
            "rules": "seller owns/controls rights and clears third-party elements for resale",
            "csv_supported": False,
            "primary_source_url": "https://contributor.pond5.com/getting-started/preparing-your-files-2/music/",
        },
    }}


def evaluate_pond5_readiness(
    source_tech: Mapping[str, Any],
    stock_analysis: Mapping[str, Any],
    profile: Mapping[str, Any],
    listing: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate deterministic Pond5 readiness rules and return the readiness model."""

    satisfied: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    blocking: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    # 1. Technical Audio Validation (TECHNICAL_FAILURE)
    fmt_val = source_tech.get("format", {}).get("value")
    bit_depth_val = source_tech.get("bit_depth", {}).get("value")
    sample_rate_val = source_tech.get("sample_rate_hz", {}).get("value")
    channels_val = source_tech.get("channels", {}).get("value")
    duration_val = source_tech.get("duration_sec", {}).get("value")

    tech_passed = True
    tech_reasons = []

    if source_tech.get("status") != "ok":
        tech_passed = False
        tech_reasons.append("Audio container probe failed.")
    if fmt_val not in _VALID_FORMATS:
        tech_passed = False
        tech_reasons.append(f"Format '{fmt_val}' is not supported (must be WAV or AIFF).")
    if bit_depth_val not in _VALID_BIT_DEPTHS:
        tech_passed = False
        tech_reasons.append(f"Bit depth '{bit_depth_val}' is not supported (must be 16, 24, or 32).")
    if sample_rate_val not in _VALID_SAMPLE_RATES:
        tech_passed = False
        tech_reasons.append(f"Sample rate '{sample_rate_val}' Hz is not supported (must be 44.1, 48, or 96 kHz).")
    if channels_val != 2:
        tech_passed = False
        tech_reasons.append(f"Channel count '{channels_val}' is not supported (must be stereo / 2 channels).")
    if duration_val is None or duration_val >= _MAX_DURATION_SEC:
        tech_passed = False
        tech_reasons.append(f"Duration {duration_val} sec exceeds maximum allowed 10 minutes.")

    if tech_passed:
        satisfied.append({
            "rule_id": "TECHNICAL_AUDIO_VALID",
            "field_ref": "source.submission_technical",
            "status": "passed",
            "evidence_refs": ["submission_file_header_probe"],
            "message": "Submission file meets Pond5 technical specifications.",
        })
    else:
        blocking.append({
            "rule_id": "TECHNICAL_FAILURE",
            "field_ref": "source.submission_technical",
            "status": "failed",
            "evidence_refs": ["submission_file_header_probe"],
            "message": "; ".join(tech_reasons),
        })

    # 2. Semantic Analysis Evidence (SEMANTIC_INSUFFICIENT)
    semantic_status = stock_analysis.get("semantic", {}).get("status") if isinstance(stock_analysis.get("semantic"), Mapping) else None
    if semantic_status in {"not_run", "failed", "no_result"} and listing.get("keywords", {}).get("status") == "no_result":
        blocking.append({
            "rule_id": "SEMANTIC_INSUFFICIENT",
            "field_ref": "semantic",
            "status": "failed",
            "evidence_refs": ["stock_music_analysis"],
            "message": "Insufficient semantic analysis evidence to produce required descriptors.",
        })
    else:
        satisfied.append({
            "rule_id": "SEMANTIC_EVIDENCE_AVAILABLE",
            "field_ref": "semantic",
            "status": "passed",
            "evidence_refs": ["stock_music_analysis"],
            "message": "Semantic descriptors are available.",
        })

    # 3. Profile Contributor and Rights Checks (#450 profile_hold_reasons)
    profile_reasons = profile_hold_reasons(profile)
    for reason in profile_reasons:
        if reason == "COMPOSER_MISSING":
            blocking.append({
                "rule_id": "COMPOSER_MISSING",
                "field_ref": "contributor.composer",
                "status": "failed",
                "evidence_refs": ["contributor.composer"],
                "message": "Composer is required for submission.",
            })
        elif reason in {"OWNERSHIP_AUTHORIZATION_UNRESOLVED", "THIRD_PARTY_CLEARANCE_UNRESOLVED"}:
            blocking.append({
                "rule_id": "RIGHTS_UNRESOLVED",
                "field_ref": "rights",
                "status": "failed",
                "evidence_refs": ["rights"],
                "message": f"Rights assertion unresolved: {reason}.",
            })
        elif reason in {"OWNERSHIP_NOT_AUTHORIZED", "THIRD_PARTY_CLEARANCE_DENIED"}:
            blocking.append({
                "rule_id": "RIGHTS_DENIED",
                "field_ref": "rights",
                "status": "failed",
                "evidence_refs": ["rights"],
                "message": f"Rights assertion denied: {reason}.",
            })
        elif reason == "SAMPLING_POLICY_UNSET":
            blocking.append({
                "rule_id": "SAMPLING_UNSET",
                "field_ref": "rights.cleared_for_sampling",
                "status": "failed",
                "evidence_refs": ["rights.cleared_for_sampling"],
                "message": "Cleared for sampling policy is unset.",
            })

    # 4. Listing Validation (LISTING_INVALID)
    title_val = listing.get("title", {}).get("value")
    desc_val = listing.get("description", {}).get("value")
    keywords_items = listing.get("keywords", {}).get("items") or []

    listing_reasons = []
    if not title_val or len(title_val) > _MAX_TITLE_LEN or _detect_leakage(title_val):
        listing_reasons.append(f"Title is invalid (length {len(title_val) if title_val else 0}, max 80, no brand leakage).")
    if desc_val and (len(desc_val) > _MAX_DESC_LEN or _detect_leakage(desc_val)):
        listing_reasons.append(f"Description is invalid (length {len(desc_val)}, max 500, no brand leakage).")
    if not keywords_items or any(_detect_leakage(kw) for kw in keywords_items):
        listing_reasons.append("Keywords list is empty or contains prohibited terms.")

    if listing_reasons:
        blocking.append({
            "rule_id": "LISTING_INVALID",
            "field_ref": "listing",
            "status": "failed",
            "evidence_refs": ["listing"],
            "message": "; ".join(listing_reasons),
        })
    else:
        satisfied.append({
            "rule_id": "LISTING_VALID",
            "field_ref": "listing",
            "status": "passed",
            "evidence_refs": ["listing"],
            "message": "Listing data conforms to Pond5 requirements.",
        })

    # 5. CSV Support Awareness (CSV_SUPPORT_UNKNOWN)
    warnings.append({
        "rule_id": "CSV_SUPPORT_UNKNOWN",
        "field_ref": "platform.fields",
        "status": "warning",
        "evidence_refs": ["platform"],
        "message": "Non-CSV fields (composer, PRO, publisher, sampling, rights assertions) must be submitted via UI/manual channel.",
    })

    readiness_status = "POND5_READY" if not blocking else "HOLD"

    return {
        "status": readiness_status,
        "satisfied": satisfied,
        "missing": missing,
        "blocking": blocking,
        "warnings": warnings,
    }


def export_pond5_csv(listing: Mapping[str, Any], output_path: Path) -> None:
    """Export ONLY proven Apply columns to CSV with UTF-8 encoding."""
    columns = ["OriginalFilename", "Title", "Description", "Keywords", "Copyright", "Price"]

    orig_filename = listing.get("target_upload_filename", {}).get("value") or ""
    title = listing.get("title", {}).get("value") or ""
    description = listing.get("description", {}).get("value") or ""

    keywords_items = listing.get("keywords", {}).get("items") or []
    keywords = ", ".join(keywords_items)

    copyright_val = listing.get("copyright", {}).get("value")
    copyright_str = str(copyright_val) if copyright_val is not None else ""

    price_val = listing.get("price", {}).get("value")
    price_str = f"{float(price_val):.2f}" if price_val is not None and isinstance(price_val, (int, float)) else ""

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(columns)
        writer.writerow([orig_filename, title, description, keywords, copyright_str, price_str])


def prepare_pond5_bundle(
    track_path: Path,
    output_dir: Path,
    config: Mapping[str, Any],
    *,
    per_track_overrides: Mapping[str, Any] | None = None,
    track_cache_dir: Path | None = None,
) -> dict[str, Any]:
    """Prepare local Pond5 readiness bundle and return the readiness document."""

    track_path = Path(track_path).resolve()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Track Analysis & Track Map v1
    cache_res = analyze_context_file_cached(track_path, cache_dir=track_cache_dir)
    track_map = cache_res.track_map

    source_info = track_map.get("source", {}).get("original", {}) if isinstance(track_map.get("source"), Mapping) else {}
    source_hash = source_info.get("hash", {})
    source_filename = source_info.get("file_name", track_path.name)

    # 2. Submission Technical Probe
    source_tech = probe_submission_technical(track_path, source_hash)

    # 3. Stock Music Semantic Analysis (#449)
    stock_analysis = produce_stock_music_analysis(track_map)

    # 4. Profile Contributor and Rights Resolution (#450)
    profile = resolve_pond5_profile(config, per_track_overrides=per_track_overrides)

    # 5. Generated Listing Data
    listing = generate_pond5_listing(
        source_filename,
        stock_analysis,
        profile,
        per_track_overrides=per_track_overrides,
    )

    # 6. Platform Snapshot
    platform = build_platform_snapshot()

    # 7. Evaluate Readiness
    readiness = evaluate_pond5_readiness(source_tech, stock_analysis, profile, listing)

    # Provenance
    provenance = {
        "sources": {
            "submission_file_header_probe": {
                "kind": "submission_file_header_probe",
                "file_name": source_filename,
                "hash": source_hash,
            },
            "stock_music_analysis": {
                "kind": "analysis_artifact",
                "document_type": stock_analysis.get("document_type"),
                "schema_version": stock_analysis.get("schema_version"),
            },
            "pond5_profile": {
                "kind": "local_config_profile",
                "document_type": profile.get("document_type"),
                "schema_version": profile.get("schema_version"),
            },
        }
    }

    # Combined Metadata Object
    metadata_doc = {
        "document_type": POND5_METADATA_DOCUMENT_TYPE,
        "schema_version": POND5_READINESS_SCHEMA_VERSION,
        "submission_channel": "ui/manual",
        "source": {
            "file_name": source_filename,
            "hash": source_hash,
            "size_bytes": source_info.get("size_bytes"),
            "audio_properties": source_info.get("audio_properties", {}),
            "submission_technical": source_tech,
        },
        "analysis": {
            "status": track_map.get("analysis", {}).get("status", "unknown") if isinstance(track_map.get("analysis"), Mapping) else "unknown",
            "bpm": track_map.get("analysis", {}).get("musical", {}).get("bpm") if isinstance(track_map.get("analysis"), Mapping) else None,
            "key": track_map.get("analysis", {}).get("musical", {}).get("key") if isinstance(track_map.get("analysis"), Mapping) else None,
            "loudness": track_map.get("analysis", {}).get("audio_summary", {}).get("loudness") if isinstance(track_map.get("analysis"), Mapping) else None,
            "brightness": track_map.get("analysis", {}).get("audio_summary", {}).get("brightness") if isinstance(track_map.get("analysis"), Mapping) else None,
        },
        "semantic": stock_analysis.get("semantic", {}),
        "contributor": profile.get("contributor", {}),
        "rights": profile.get("rights", {}),
        "listing": listing,
        "platform": platform,
        "provenance": provenance,
    }

    # Combined Readiness Document (normative shape from docs/POND5_READINESS_V1.md)
    readiness_doc = {
        "document_type": POND5_READINESS_DOCUMENT_TYPE,
        "schema_version": POND5_READINESS_SCHEMA_VERSION,
        "source": metadata_doc["source"],
        "analysis": metadata_doc["analysis"],
        "semantic": metadata_doc["semantic"],
        "contributor": metadata_doc["contributor"],
        "rights": metadata_doc["rights"],
        "listing": metadata_doc["listing"],
        "platform": metadata_doc["platform"],
        "provenance": metadata_doc["provenance"],
        "readiness": readiness,
    }

    # Export artifacts
    (output_dir / "pond5_metadata.json").write_text(
        json.dumps(metadata_doc, indent=2, sort_keys=True), encoding="utf-8"
    )

    (output_dir / "pond5_readiness.json").write_text(
        json.dumps(readiness_doc, indent=2, sort_keys=True), encoding="utf-8"
    )

    export_pond5_csv(listing, output_dir / "pond5.csv")

    return readiness_doc


__all__ = [
    "POND5_READINESS_DOCUMENT_TYPE",
    "POND5_METADATA_DOCUMENT_TYPE",
    "POND5_READINESS_SCHEMA_VERSION",
    "probe_submission_technical",
    "suggest_target_upload_filename",
    "generate_pond5_listing",
    "build_platform_snapshot",
    "evaluate_pond5_readiness",
    "export_pond5_csv",
    "prepare_pond5_bundle",
]
