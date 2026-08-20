"""Deterministic local Pond5 readiness bundle for issue #451.

This module combines existing Sample-Brain Track Map and stock-music semantic
artifacts with the explicit Pond5 contributor/rights profile.  It performs only
container/header probing on the selected submission file; it does not redo
musical analysis, mutate audio, upload files, or contact Pond5.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import csv
import io
import json
import math
from pathlib import Path
import re
import unicodedata

import soundfile as sf

from .content_hash import compute_file_hash
from .pond5_profile import profile_hold_reasons


POND5_READINESS_DOCUMENT_TYPE = "sample_brain.pond5_readiness"
POND5_READINESS_SCHEMA_VERSION = "1.0.0"
POND5_METADATA_DOCUMENT_TYPE = "sample_brain.pond5_metadata"
POND5_METADATA_SCHEMA_VERSION = "1.0.0"
POND5_CSV_COLUMNS = (
    "OriginalFilename",
    "Title",
    "Description",
    "Keywords",
    "Copyright",
    "Price",
)

_ALLOWED_FORMATS = frozenset({"wav", "aiff"})
_ALLOWED_BIT_DEPTHS = frozenset({16, 24, 32})
_ALLOWED_SAMPLE_RATES = frozenset({44100, 48000, 96000})
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9_]+\.(?:wav|aiff|aif)$", re.IGNORECASE)
_WORD = re.compile(r"^[A-Za-z0-9_]+$")
_PROHIBITED_PHRASES = (
    "sounds like",
    "sound like",
    "in the style of",
)
# Conservative offline seed list for obvious leakage checks. Generated listing
# terms come from controlled vocabularies, so this mainly guards caller-supplied
# listing objects and future manual override surfaces.
_PROHIBITED_REFERENCES = (
    "spotify",
    "netflix",
    "nike",
    "coca cola",
    "star wars",
    "marvel",
    "taylor swift",
    "daft punk",
)


def probe_submission_technical(path: Path) -> dict[str, object]:
    """Read portable container/header facts for the selected submission file."""
    source = Path(path)
    source_hash = compute_file_hash(source)
    try:
        info = sf.info(str(source))
    except Exception:
        return {
            "status": "failed",
            "reason_code": "AUDIO_HEADER_PROBE_FAILED",
            "source_ref": "submission_file_header_probe",
        }

    format_name = _normalize_format(info.format, source.suffix)
    bit_depth = _bit_depth(info.subtype)
    duration = float(info.frames) / float(info.samplerate) if info.samplerate else None
    values = {
        "format": format_name,
        "bit_depth": bit_depth,
        "sample_rate_hz": int(info.samplerate),
        "channels": int(info.channels),
        "duration_sec": duration,
    }
    result: dict[str, object] = {"status": "ok"}
    for key, value in values.items():
        result[key] = {
            "status": "ok" if value is not None else "no_result",
            "value": value,
            "evidence_refs": [f"submission_file_header.{key}"],
            "source_ref": "submission_file_header_probe",
        }
    result["file_name"] = source.name
    result["hash"] = source_hash
    return result


def build_pond5_bundle(
    track_map: Mapping[str, object],
    semantic_analysis: Mapping[str, object],
    profile: Mapping[str, object],
    *,
    source_path: Path,
    listing: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build portable metadata/readiness and one supported Apply CSV row."""
    source = _track_source(track_map)
    technical = probe_submission_technical(Path(source_path))
    source_name = str(source.get("file_name") or Path(source_path).name)
    target_name = suggest_target_upload_filename(source_name)

    generated_listing = (
        _normalize_listing(listing, target_name)
        if listing is not None
        else _generate_listing(source_name, semantic_analysis, profile, target_name)
    )

    source_block = {
        "file_name": source_name,
        "hash": source.get("hash"),
        "size_bytes": source.get("size_bytes"),
        "audio_properties": source.get("audio_properties", {}),
        "source_ref": "track_map_v1",
        "submission_technical": technical,
    }
    semantic = _semantic_block(semantic_analysis)
    analysis = _analysis_adapter(track_map)
    provenance_sources = {
        "track_map_v1": {
            "kind": "analysis_artifact",
            "document_type": track_map.get("document_type"),
            "schema_version": track_map.get("schema_version"),
        },
        "stock_music_analysis": {
            "kind": "semantic_artifact",
            "document_type": semantic_analysis.get("document_type"),
            "schema_version": semantic_analysis.get("schema_version"),
        },
        "submission_file_header_probe": {
            "kind": "local_container_header_probe",
            "file_name": Path(source_path).name,
            "hash": technical.get("hash") if isinstance(technical, Mapping) else None,
        },
        "listing_generator": {
            "kind": "listing_generator",
            "component": "pond5_readiness",
            "version": POND5_READINESS_SCHEMA_VERSION,
        },
        "listing_override": {"kind": "manual_listing_override"},
        "pond5_profile": {"kind": "manual_profile_adapter"},
        **_portable_semantic_sources(semantic_analysis),
        **_portable_profile_sources(profile),
    }
    metadata = {
        "document_type": POND5_METADATA_DOCUMENT_TYPE,
        "schema_version": POND5_METADATA_SCHEMA_VERSION,
        "source": source_block,
        "analysis": analysis,
        "semantic": semantic,
        "contributor": profile.get("contributor", {}),
        "rights": profile.get("rights", {}),
        "listing": generated_listing,
        "platform": _platform_snapshot(),
        "provenance": {"sources": provenance_sources},
    }
    readiness_block = evaluate_pond5_readiness(metadata, profile)
    readiness = {
        "document_type": POND5_READINESS_DOCUMENT_TYPE,
        "schema_version": POND5_READINESS_SCHEMA_VERSION,
        "source": source_block,
        "analysis": analysis,
        "semantic": semantic,
        "contributor": profile.get("contributor", {}),
        "rights": profile.get("rights", {}),
        "listing": generated_listing,
        "platform": metadata["platform"],
        "provenance": metadata["provenance"],
        "readiness": readiness_block,
    }
    csv_row = _csv_row(metadata)
    return {"metadata": metadata, "readiness": readiness, "csv_row": csv_row}


def evaluate_pond5_readiness(
    metadata: Mapping[str, object], profile: Mapping[str, object]
) -> dict[str, object]:
    blocking: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    satisfied: list[dict[str, object]] = []

    source = _as_mapping(metadata.get("source"))
    technical = _as_mapping(source.get("submission_technical"))
    _check_source_binding(source, technical, blocking, satisfied)
    _check_technical(technical, blocking, satisfied)

    source_name = str(source.get("file_name") or "")
    listing = _as_mapping(metadata.get("listing"))
    _check_listing(source_name, listing, blocking, warnings, satisfied)

    semantic = _as_mapping(metadata.get("semantic"))
    if not _semantic_terms(semantic):
        blocking.append(_finding("SEMANTIC_EVIDENCE_INSUFFICIENT", "semantic", "No usable stock-music descriptor is available."))
    else:
        satisfied.append(_finding("SEMANTIC_EVIDENCE_AVAILABLE", "semantic", "At least one evidence-backed stock-music descriptor is available."))

    for code in profile_hold_reasons(profile):
        blocking.append(_finding(code, _profile_field_ref(code), _profile_message(code)))

    status = "POND5_READY" if not blocking else "HOLD"
    return {
        "status": status,
        "satisfied": satisfied,
        "missing": [item for item in blocking if item["status"] == "missing"],
        "blocking": blocking,
        "warnings": warnings,
    }


def write_pond5_bundle(bundle: Mapping[str, object], output_dir: Path) -> None:
    """Write the deterministic local v1 bundle; never writes source audio."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    metadata = _as_mapping(bundle.get("metadata"))
    readiness = _as_mapping(bundle.get("readiness"))
    csv_row = _as_mapping(bundle.get("csv_row"))
    _write_json(out / "pond5_metadata.json", metadata)
    _write_json(out / "pond5_readiness.json", readiness)
    (out / "pond5.csv").write_text(render_pond5_csv(csv_row), encoding="utf-8", newline="")


def render_pond5_csv(row: Mapping[str, object]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(POND5_CSV_COLUMNS), extrasaction="ignore")
    writer.writeheader()
    writer.writerow({key: row.get(key, "") for key in POND5_CSV_COLUMNS})
    return buffer.getvalue()


def suggest_target_upload_filename(source_name: str) -> str:
    path = Path(source_name)
    ext = path.suffix.lower()
    if ext not in {".wav", ".aif", ".aiff"}:
        ext = ".wav"
    ascii_stem = unicodedata.normalize("NFKD", path.stem).encode("ascii", "ignore").decode("ascii")
    stem = re.sub(r"[^A-Za-z0-9_]+", "_", ascii_stem).strip("_")
    stem = re.sub(r"_+", "_", stem) or "pond5_track"
    candidate = f"{stem}{ext}"
    if _SAFE_FILENAME.fullmatch(candidate):
        return candidate
    return f"pond5_track{ext}"


def _generate_listing(
    source_name: str,
    semantic_analysis: Mapping[str, object],
    profile: Mapping[str, object],
    target_name: str,
) -> dict[str, object]:
    semantic = _semantic_block(semantic_analysis)
    terms = _semantic_terms(semantic)
    display_terms = [term.replace("_", " ").title() for term in terms]
    title_terms = display_terms[:2]
    title = " ".join(title_terms + ["Music"]) if title_terms else "Music Track"
    if len(title) > 80:
        title = title[:80].rstrip()
    description = (
        f"{title}. Evidence-backed descriptors: {', '.join(display_terms[:8])}."
        if display_terms
        else "Music track prepared for Pond5 metadata review."
    )
    description = description[:500].rstrip()
    keywords = _dedupe(["music", *terms])[:50]
    copyright_owner = _manual_value(profile, "contributor", "copyright_owner")
    price = _profile_price(profile)
    return {
        "status": "ok" if terms else "partial",
        "title": _value(title, ["semantic"], "listing_generator"),
        "description": _value(description, ["semantic"], "listing_generator"),
        "keywords": _value(keywords, ["semantic"], "listing_generator"),
        "copyright": _value(copyright_owner or "", ["contributor.copyright_owner"], "pond5_profile"),
        "price": _value(price, ["listing.price"], "pond5_profile") if price is not None else {"status": "unknown", "value": None, "source_ref": "pond5_profile"},
        "target_upload_filename": {
            **_value(target_name, ["source.file_name"], "listing_generator"),
            "source_name_ref": "source.file_name",
        },
    }


def _normalize_listing(listing: Mapping[str, object], target_name: str) -> dict[str, object]:
    title = str(listing.get("title") or "")
    description = str(listing.get("description") or "")
    raw_keywords = listing.get("keywords") or []
    keywords = [str(item).strip() for item in raw_keywords] if isinstance(raw_keywords, Sequence) and not isinstance(raw_keywords, (str, bytes)) else []
    return {
        "status": "ok",
        "title": _value(title, ["listing.override.title"], "listing_override"),
        "description": _value(description, ["listing.override.description"], "listing_override"),
        "keywords": _value(keywords, ["listing.override.keywords"], "listing_override"),
        "copyright": _value(str(listing.get("copyright") or ""), ["listing.override.copyright"], "listing_override"),
        "price": _value(listing.get("price"), ["listing.override.price"], "listing_override"),
        "target_upload_filename": {
            **_value(str(listing.get("target_upload_filename") or target_name), ["source.file_name"], "listing_override"),
            "source_name_ref": "source.file_name",
        },
    }


def _check_source_binding(
    source: Mapping[str, object],
    technical: Mapping[str, object],
    blocking: list[dict[str, object]],
    satisfied: list[dict[str, object]],
) -> None:
    track_hash = source.get("hash")
    probe_hash = technical.get("hash")
    if not _same_hash(track_hash, probe_hash):
        blocking.append(
            _finding(
                "SOURCE_IDENTITY_MISMATCH",
                "source.hash",
                "Track Map identity does not match the selected submission file.",
            )
        )
    else:
        satisfied.append(
            _finding(
                "SOURCE_IDENTITY_BOUND",
                "source.hash",
                "Track Map identity matches the selected submission file.",
                status="ok",
            )
        )


def _check_technical(technical: Mapping[str, object], blocking: list[dict[str, object]], satisfied: list[dict[str, object]]) -> None:
    if technical.get("status") != "ok":
        blocking.append(_finding("AUDIO_TECHNICAL_UNAVAILABLE", "source.submission_technical", "Submission-file technical metadata is unavailable."))
        return
    checks = (
        ("format", lambda v: v in _ALLOWED_FORMATS, "AUDIO_FORMAT_UNSUPPORTED", "Audio must be WAV or AIFF."),
        ("bit_depth", lambda v: v in _ALLOWED_BIT_DEPTHS, "AUDIO_BIT_DEPTH_UNSUPPORTED", "Audio bit depth must be 16, 24, or 32 bit."),
        ("sample_rate_hz", lambda v: v in _ALLOWED_SAMPLE_RATES, "AUDIO_SAMPLE_RATE_UNSUPPORTED", "Audio sample rate must be 44.1, 48, or 96 kHz."),
        ("channels", lambda v: v == 2, "AUDIO_NOT_STEREO", "Audio must be stereo."),
        ("duration_sec", lambda v: isinstance(v, (int, float)) and math.isfinite(float(v)) and 0 < float(v) < 600, "AUDIO_DURATION_INVALID", "Audio duration must be greater than zero and under 10 minutes."),
    )
    for field, predicate, code, message in checks:
        item = _as_mapping(technical.get(field))
        value = item.get("value")
        if item.get("status") != "ok" or not predicate(value):
            blocking.append(_finding(code, f"source.submission_technical.{field}", message))
        else:
            satisfied.append(_finding(f"{field.upper()}_VALID", f"source.submission_technical.{field}", message, status="ok"))


def _check_listing(source_name: str, listing: Mapping[str, object], blocking: list[dict[str, object]], warnings: list[dict[str, object]], satisfied: list[dict[str, object]]) -> None:
    title = str(_as_mapping(listing.get("title")).get("value") or "")
    description = str(_as_mapping(listing.get("description")).get("value") or "")
    keywords_obj = _as_mapping(listing.get("keywords"))
    raw_keywords = keywords_obj.get("value")
    keywords = [str(item).strip() for item in raw_keywords] if isinstance(raw_keywords, list) else []
    target_name = str(_as_mapping(listing.get("target_upload_filename")).get("value") or "")

    if not title or len(title) > 80 or not _ascii_text(title) or _contains_prohibited_reference(title):
        blocking.append(_finding("TITLE_INVALID", "listing.title", "Title must be English-compatible ASCII text, <= 80 characters, without prohibited references."))
    else:
        satisfied.append(_finding("TITLE_VALID", "listing.title", "Title satisfies v1 listing limits.", status="ok"))
    if description and (len(description) > 500 or not _ascii_text(description) or _contains_prohibited_reference(description)):
        blocking.append(_finding("DESCRIPTION_INVALID", "listing.description", "Description must be English-compatible ASCII text, <= 500 characters, without prohibited references."))
    if not keywords or len(keywords) > 50 or keywords != _dedupe(keywords) or any(not _keyword_valid(item) for item in keywords):
        blocking.append(_finding("KEYWORDS_INSUFFICIENT", "listing.keywords", "Keywords must be present, relevant controlled terms, deduplicated, and <= 50."))
    elif any(_contains_prohibited_reference(item) for item in keywords):
        blocking.append(_finding("KEYWORDS_PROHIBITED_REFERENCE", "listing.keywords", "Keywords contain a prohibited marketing/reference term."))
    else:
        satisfied.append(_finding("KEYWORDS_VALID", "listing.keywords", "Keywords satisfy v1 hard limits.", status="ok"))
        if len(keywords) < 10:
            warnings.append(_finding("KEYWORD_COUNT_RECOMMENDATION", "listing.keywords", "Fewer than 10 keywords is allowed but may reduce discoverability.", status="warning"))
    if not target_name or not _SAFE_FILENAME.fullmatch(target_name):
        blocking.append(_finding("FILENAME_INVALID_NO_TARGET_NAME", "listing.target_upload_filename", "A valid upload filename suggestion is required."))
    elif target_name != source_name:
        warnings.append(_finding("TARGET_FILENAME_SUGGESTED", "listing.target_upload_filename", "Source filename is preserved; use the generated upload filename suggestion.", status="warning"))


def _semantic_block(semantic_analysis: Mapping[str, object]) -> dict[str, object]:
    semantic = semantic_analysis.get("semantic")
    return dict(semantic) if isinstance(semantic, Mapping) else {"status": "not_run"}


def _semantic_terms(semantic: Mapping[str, object]) -> list[str]:
    terms: list[str] = []
    for field, raw in semantic.items():
        if field == "status":
            continue
        if isinstance(raw, Mapping):
            status = raw.get("status")
            if status not in {"ok", "partial"}:
                continue
            value = raw.get("value")
            if isinstance(value, str):
                terms.append(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        terms.append(item)
                    elif isinstance(item, Mapping) and isinstance(item.get("value"), str):
                        terms.append(str(item["value"]))
            elif isinstance(raw.get("items"), list):
                for item in raw["items"]:
                    if isinstance(item, Mapping) and isinstance(item.get("value"), str):
                        terms.append(str(item["value"]))
            elif isinstance(raw.get("values"), list):
                for item in raw["values"]:
                    if isinstance(item, Mapping) and isinstance(item.get("value"), str):
                        terms.append(str(item["value"]))
    return [term for term in _dedupe(terms) if _keyword_valid(term)]


def _track_source(track_map: Mapping[str, object]) -> Mapping[str, object]:
    source = _as_mapping(track_map.get("source"))
    original = source.get("original")
    if not isinstance(original, Mapping):
        raise ValueError("Track Map source.original is required")
    return original


def _analysis_adapter(track_map: Mapping[str, object]) -> dict[str, object]:
    analysis = _as_mapping(track_map.get("analysis"))
    result: dict[str, object] = {"status": analysis.get("status", "not_run")}
    fields = (
        ("bpm", "musical", "track_map.analysis.musical.bpm"),
        ("key", "musical", "track_map.analysis.musical.key"),
        ("loudness", "audio_summary", "track_map.analysis.audio_summary.loudness"),
        ("brightness", "audio_summary", "track_map.analysis.audio_summary.brightness"),
    )
    for name, block_name, evidence_ref in fields:
        item = _as_mapping(_as_mapping(analysis.get(block_name)).get(name))
        if not item:
            continue
        adapted = dict(item)
        adapted["source_ref"] = "track_map_v1"
        adapted["evidence_refs"] = [evidence_ref]
        result[name] = adapted
    timeline = analysis.get("timeline")
    if isinstance(timeline, Mapping):
        result["timeline"] = dict(timeline)
    return result


def _portable_semantic_sources(semantic_analysis: Mapping[str, object]) -> dict[str, object]:
    provenance = _as_mapping(semantic_analysis.get("provenance"))
    sources = _as_mapping(provenance.get("sources"))
    return {str(key): dict(value) for key, value in sources.items() if isinstance(value, Mapping)}


def _portable_profile_sources(profile: Mapping[str, object]) -> dict[str, object]:
    provenance = _as_mapping(profile.get("provenance"))
    sources = _as_mapping(provenance.get("sources"))
    return {str(key): dict(value) for key, value in sources.items() if isinstance(value, Mapping)}


def _same_hash(left: object, right: object) -> bool:
    if not isinstance(left, Mapping) or not isinstance(right, Mapping):
        return False
    left_algorithm = left.get("algorithm")
    left_value = left.get("value")
    right_algorithm = right.get("algorithm")
    right_value = right.get("value")
    return (
        isinstance(left_algorithm, str)
        and isinstance(left_value, str)
        and left_algorithm == right_algorithm
        and left_value == right_value
    )


def _csv_row(metadata: Mapping[str, object]) -> dict[str, object]:
    source = _as_mapping(metadata.get("source"))
    listing = _as_mapping(metadata.get("listing"))
    return {
        "OriginalFilename": _as_mapping(listing.get("target_upload_filename")).get("value") or source.get("file_name") or "",
        "Title": _as_mapping(listing.get("title")).get("value") or "",
        "Description": _as_mapping(listing.get("description")).get("value") or "",
        "Keywords": ",".join(_as_mapping(listing.get("keywords")).get("value") or []),
        "Copyright": _as_mapping(listing.get("copyright")).get("value") or "",
        "Price": "" if _as_mapping(listing.get("price")).get("value") is None else _as_mapping(listing.get("price")).get("value"),
    }


def _platform_snapshot() -> dict[str, object]:
    music_url = "https://contributor.pond5.com/getting-started/preparing-your-files-2/music/"
    files_url = "https://contributor.pond5.com/getting-started/preparing-your-files/"
    return {
        "snapshot_date": "2026-08-20",
        "primary_sources": [music_url, files_url],
        "csv_supported_columns": list(POND5_CSV_COLUMNS),
        "non_csv_submission": {
            "composer": "ui/manual|unknown",
            "ipi": "ui/manual|unknown",
            "pro": "ui/manual|unknown",
            "publisher": "ui/manual|unknown",
            "ownership_authorized": "ui/manual|unknown",
            "third_party_elements_cleared_for_resale": "ui/manual|unknown",
            "cleared_for_sampling": "ui/manual|unknown",
        },
    }


def _normalize_format(format_name: str | None, suffix: str) -> str | None:
    raw = (format_name or "").upper()
    if raw in {"WAV", "WAVEX", "RF64"}:
        return "wav"
    if raw in {"AIFF", "AIFC"}:
        return "aiff"
    if raw == "FLAC":
        return "flac"
    ext = suffix.lower()
    return ext[1:] if ext else None


def _bit_depth(subtype: str | None) -> int | None:
    raw = (subtype or "").upper()
    for bits in (16, 24, 32):
        if str(bits) in raw:
            return bits
    if raw in {"FLOAT"}:
        return 32
    return None


def _value(value: object, evidence_refs: list[str], source_ref: str) -> dict[str, object]:
    return {"status": "ok", "value": value, "evidence_refs": evidence_refs, "source_ref": source_ref}


def _manual_value(profile: Mapping[str, object], block: str, field: str) -> str | None:
    item = _as_mapping(_as_mapping(profile.get(block)).get(field))
    value = item.get("value")
    return value.strip() if item.get("status") == "ok" and isinstance(value, str) and value.strip() else None


def _profile_price(profile: Mapping[str, object]) -> float | None:
    item = _as_mapping(_as_mapping(profile.get("listing")).get("price"))
    value = item.get("value")
    if item.get("status") == "ok" and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
        return float(value)
    return None


def _dedupe(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw).strip().lower().replace(" ", "_")
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _keyword_valid(value: str) -> bool:
    return bool(value and len(value) <= 64 and _WORD.fullmatch(value.replace("-", "_")))


def _ascii_text(value: str) -> bool:
    try:
        value.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def _contains_prohibited_reference(value: str) -> bool:
    lowered = value.lower()
    return any(term in lowered for term in (*_PROHIBITED_PHRASES, *_PROHIBITED_REFERENCES))


def _finding(rule_id: str, field_ref: str, message: str, *, status: str = "missing") -> dict[str, object]:
    return {"rule_id": rule_id, "field_ref": field_ref, "status": status, "evidence_refs": [field_ref], "message": message}


def _profile_field_ref(code: str) -> str:
    mapping = {
        "COMPOSER_MISSING": "contributor.composer",
        "OWNERSHIP_AUTHORIZATION_UNRESOLVED": "rights.ownership_authorized",
        "OWNERSHIP_NOT_AUTHORIZED": "rights.ownership_authorized",
        "THIRD_PARTY_CLEARANCE_UNRESOLVED": "rights.third_party_elements_cleared_for_resale",
        "THIRD_PARTY_CLEARANCE_DENIED": "rights.third_party_elements_cleared_for_resale",
        "SAMPLING_POLICY_UNSET": "rights.cleared_for_sampling",
    }
    return mapping.get(code, "profile")


def _profile_message(code: str) -> str:
    return {
        "COMPOSER_MISSING": "Composer must be explicitly supplied.",
        "OWNERSHIP_AUTHORIZATION_UNRESOLVED": "Ownership authorization must be explicitly resolved.",
        "OWNERSHIP_NOT_AUTHORIZED": "Ownership authorization is explicitly false.",
        "THIRD_PARTY_CLEARANCE_UNRESOLVED": "Third-party resale clearance must be explicitly resolved.",
        "THIRD_PARTY_CLEARANCE_DENIED": "Third-party resale clearance is explicitly false.",
        "SAMPLING_POLICY_UNSET": "Cleared For Sampling must be explicitly true or false.",
    }.get(code, "Required Pond5 profile value is unresolved.")


def _as_mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
