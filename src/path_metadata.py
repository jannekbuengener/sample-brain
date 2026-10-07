"""Deterministic filename/path metadata pre-pass and evidence reconciliation.

Contract: docs/PATH_METADATA_RECONCILIATION.md
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import text

from .bpm_display import round_bpm_display
from .bpm_evidence import classify_bpm_error
from .config import REGEX_MAP_PATH
from .db import get_engine, init_db, upsert_sample_tag
from .key_signature import (
    format_key_signature,
    is_same_mode,
    is_same_root,
    parse_key_signature,
)

PATH_METADATA_PARSER_VERSION = "1"

FIELD_BPM = "bpm"
FIELD_KEY = "key"
FIELD_SAMPLE_CLASS = "sample_class"
FIELD_PRED_TYPE = "pred_type"
FIELD_GENRE = "genre"

SOURCE_FILENAME = "filename"
SOURCE_FOLDER = "folder"

STATUS_CONFIRMED = "CONFIRMED"
STATUS_COMPATIBLE = "COMPATIBLE"
STATUS_PARTIAL = "PARTIAL"
STATUS_CONFLICT = "CONFLICT"
STATUS_DECLARED_ONLY = "DECLARED_ONLY"
STATUS_ANALYSIS_ONLY = "ANALYSIS_ONLY"
STATUS_UNKNOWN = "UNKNOWN"

BPM_HINT_RE = re.compile(
    r"(?<!\d)(\d{2,3})\s*[-_ ]?\s*bpm(?![A-Za-z0-9])", re.IGNORECASE
)
KEY_HINT_RE = re.compile(
    r"\b([A-Ga-g])([#b]?)(?:\s*)(maj(?:or)?|min(?:or)?|m)\b",
    re.IGNORECASE,
)

_TYPE_PATTERNS = {
    "oneshot": re.compile(
        r"\b(?:one[\s_-]*shots?|oneshots?)\b", re.IGNORECASE
    ),
    "loop": re.compile(r"\bloops?\b", re.IGNORECASE),
}

# Weak-label instrument hints (validate_report compatibility).
_INSTRUMENT_HINT_PATTERNS = (
    ("kick", re.compile(r"\bkicks?\b", re.IGNORECASE)),
    ("snare", re.compile(r"\bsnares?\b", re.IGNORECASE)),
    ("clap", re.compile(r"\bclaps?\b", re.IGNORECASE)),
    ("hihat", re.compile(r"\b(?:hi\s*hat|hihat|hats?)\b", re.IGNORECASE)),
    ("impact", re.compile(r"\bimpacts?\b", re.IGNORECASE)),
    ("drone", re.compile(r"\bdrones?\b", re.IGNORECASE)),
    ("pad", re.compile(r"\bpads?\b", re.IGNORECASE)),
    ("fx", re.compile(r"\b(?:fx|sfx)\b", re.IGNORECASE)),
)

# Pred_type claims mapped onto existing classify / brief taxonomy (ordered).
_PRED_TYPE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("HiHat-Closed", re.compile(r"\b(?:closed[\s_-]*hats?|hihat[\s_-]*closed|hhc)\b", re.IGNORECASE)),
    ("HiHat-Open", re.compile(r"\b(?:open[\s_-]*hats?|hihat[\s_-]*open|hho)\b", re.IGNORECASE)),
    ("Drum Loop", re.compile(r"\bdrum[\s_-]*loops?\b", re.IGNORECASE)),
    ("Kick", re.compile(r"\bkicks?\b", re.IGNORECASE)),
    ("Snare", re.compile(r"\bsnares?\b", re.IGNORECASE)),
    ("Clap", re.compile(r"\bclaps?\b", re.IGNORECASE)),
    ("HiHat-Closed", re.compile(r"\b(?:hi[\s_-]*hats?|hihats?|hats?)\b", re.IGNORECASE)),
    ("Bass", re.compile(r"\bbass\b", re.IGNORECASE)),
    ("Pad", re.compile(r"\bpads?\b", re.IGNORECASE)),
    ("Drone", re.compile(r"\bdrones?\b", re.IGNORECASE)),
    ("Riser", re.compile(r"\brisers?\b", re.IGNORECASE)),
    ("Impact", re.compile(r"\bimpacts?\b", re.IGNORECASE)),
    ("Vocal", re.compile(r"\b(?:vocals?|vox)\b", re.IGNORECASE)),
    ("Perc", re.compile(r"\bperc(?:ussion)?\b", re.IGNORECASE)),
    ("FX", re.compile(r"\b(?:fx|sfx)\b", re.IGNORECASE)),
)

_genre_patterns_cache: list[tuple[str, re.Pattern[str]]] | None = None


@dataclass(frozen=True)
class PathClaim:
    field: str
    normalized_value: str
    source: str
    raw_evidence: str


def _normalized_ref(text: str | None) -> str:
    text = text or ""
    # Split camelCase so KickLoop / OneShot become explicit tokens.
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    return re.sub(r"[_./\\()\[\]-]+", " ", text).strip()


def path_fingerprint(basename: str, relpath: str | None) -> str:
    """Stable fingerprint of path identity used for claim invalidation."""
    payload = f"{relpath or ''}\0{basename}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def extract_bpm_hint(text: str | None) -> float | None:
    if not text:
        return None
    match = BPM_HINT_RE.search(text)
    if match is None:
        return None
    return float(match.group(1))


def extract_key_hint(text: str | None) -> str | None:
    """Return canonical modeful key string (e.g. ``Amin``) or None."""
    normalized = _normalized_ref(text)
    match = KEY_HINT_RE.search(normalized)
    if match is None:
        return None
    raw = f"{match.group(1)}{match.group(2) or ''}{match.group(3)}"
    parsed = parse_key_signature(raw)
    if parsed is None or parsed.mode is None:
        return None
    return format_key_signature(parsed.root, parsed.mode)


def extract_type_hint(text: str | None) -> str | None:
    """Structural sample_class claim: ``oneshot`` or ``loop``."""
    normalized = _normalized_ref(text)
    for label in ("oneshot", "loop"):
        if _TYPE_PATTERNS[label].search(normalized):
            return label
    return None


def extract_instrument_hint(text: str | None) -> str | None:
    """Lowercase weak-label instrument hint (validate_report compatibility)."""
    normalized = _normalized_ref(text)
    for label, pattern in _INSTRUMENT_HINT_PATTERNS:
        if pattern.search(normalized):
            return label
    return None


def extract_pred_type_claim(text: str | None) -> str | None:
    """Semantic sample-type claim using classify-aligned taxonomy labels."""
    normalized = _normalized_ref(text)
    for label, pattern in _PRED_TYPE_PATTERNS:
        match = pattern.search(normalized)
        if match is not None:
            return label
    return None


def _load_genre_patterns() -> list[tuple[str, re.Pattern[str]]]:
    global _genre_patterns_cache
    if _genre_patterns_cache is not None:
        return _genre_patterns_cache
    patterns: list[tuple[str, re.Pattern[str]]] = []
    try:
        if REGEX_MAP_PATH.exists():
            data = json.loads(REGEX_MAP_PATH.read_text(encoding="utf-8"))
            genre_map = data.get("genre") or {}
            if isinstance(genre_map, dict):
                for label, pats in genre_map.items():
                    if not isinstance(pats, list):
                        continue
                    for pat in pats:
                        if not isinstance(pat, str):
                            continue
                        try:
                            patterns.append((str(label), re.compile(pat, re.IGNORECASE)))
                        except re.error:
                            continue
    except (OSError, json.JSONDecodeError, TypeError):
        patterns = []
    _genre_patterns_cache = patterns
    return patterns


def extract_genre_claims(text: str | None) -> list[tuple[str, str]]:
    """Return list of (normalized_genre_label, raw_evidence)."""
    if not text:
        return []
    normalized = _normalized_ref(text)
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for label, pattern in _load_genre_patterns():
        match = pattern.search(normalized)
        if match is None:
            continue
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        found.append((label, match.group(0)))
    return found


def _basename_and_folder(filename: str, relpath: str | None) -> tuple[str, str]:
    name = Path(filename).name
    stem = Path(name).stem
    folder = ""
    if relpath:
        parent = Path(relpath.replace("\\", "/")).parent
        if str(parent) not in (".", ""):
            folder = str(parent).replace("\\", "/")
    return stem, folder


def extract_claims_from_path(
    filename: str, relpath: str | None = None
) -> list[PathClaim]:
    """Extract deterministic path claims from filename stem and folder segments."""
    try:
        stem, folder = _basename_and_folder(filename, relpath)
        claims: list[PathClaim] = []

        def _add_scalar(
            field: str,
            value: str | None,
            source: str,
            raw: str | None,
        ) -> None:
            if value is None or raw is None:
                return
            # Prefer filename over folder for scalar fields when both present.
            if any(c.field == field for c in claims):
                return
            claims.append(
                PathClaim(
                    field=field,
                    normalized_value=value,
                    source=source,
                    raw_evidence=raw,
                )
            )

        for source, text_value in (
            (SOURCE_FILENAME, stem),
            (SOURCE_FOLDER, folder),
        ):
            if not text_value:
                continue
            bpm = extract_bpm_hint(text_value)
            if bpm is not None:
                match = BPM_HINT_RE.search(text_value)
                _add_scalar(
                    FIELD_BPM,
                    str(int(bpm)),
                    source,
                    match.group(0) if match else str(int(bpm)),
                )
            key = extract_key_hint(text_value)
            if key is not None:
                match = KEY_HINT_RE.search(_normalized_ref(text_value))
                _add_scalar(
                    FIELD_KEY,
                    key,
                    source,
                    match.group(0) if match else key,
                )
            sample_class = extract_type_hint(text_value)
            if sample_class is not None:
                match = _TYPE_PATTERNS[sample_class].search(_normalized_ref(text_value))
                _add_scalar(
                    FIELD_SAMPLE_CLASS,
                    sample_class,
                    source,
                    match.group(0) if match else sample_class,
                )
            pred = extract_pred_type_claim(text_value)
            if pred is not None:
                _add_scalar(FIELD_PRED_TYPE, pred, source, pred)

            for genre_label, raw in extract_genre_claims(text_value):
                # Genre allows multiple; unique per (field, source, value) later in DB.
                if any(
                    c.field == FIELD_GENRE
                    and c.source == source
                    and c.normalized_value.casefold() == genre_label.casefold()
                    for c in claims
                ):
                    continue
                claims.append(
                    PathClaim(
                        field=FIELD_GENRE,
                        normalized_value=genre_label,
                        source=source,
                        raw_evidence=raw,
                    )
                )
        return claims
    except Exception:
        return []


def replace_path_metadata_claims(
    sample_id: int,
    claims: Iterable[PathClaim],
    *,
    path_fingerprint_value: str,
) -> None:
    engine = get_engine()
    claim_list = list(claims)
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM path_metadata_claims WHERE sample_id = :sid"),
            {"sid": sample_id},
        )
        for claim in claim_list:
            conn.execute(
                text(
                    """
                    INSERT INTO path_metadata_claims (
                        sample_id, field, normalized_value, source, raw_evidence,
                        parser_version, path_fingerprint
                    ) VALUES (
                        :sample_id, :field, :normalized_value, :source, :raw_evidence,
                        :parser_version, :path_fingerprint
                    )
                    """
                ),
                {
                    "sample_id": sample_id,
                    "field": claim.field,
                    "normalized_value": claim.normalized_value,
                    "source": claim.source,
                    "raw_evidence": claim.raw_evidence,
                    "parser_version": PATH_METADATA_PARSER_VERSION,
                    "path_fingerprint": path_fingerprint_value,
                },
            )


def list_path_metadata_claims(sample_id: int | None = None) -> list[dict[str, Any]]:
    engine = get_engine()
    query = """
        SELECT sample_id, field, normalized_value, source, raw_evidence,
               parser_version, path_fingerprint
        FROM path_metadata_claims
    """
    params: dict[str, Any] = {}
    if sample_id is not None:
        query += " WHERE sample_id = :sample_id"
        params["sample_id"] = sample_id
    query += " ORDER BY sample_id, field, source, normalized_value"
    with engine.begin() as conn:
        rows = conn.execute(text(query), params).fetchall()
    return [
        {
            "sample_id": int(row[0]),
            "field": row[1],
            "normalized_value": row[2],
            "source": row[3],
            "raw_evidence": row[4],
            "parser_version": row[5],
            "path_fingerprint": row[6],
        }
        for row in rows
    ]


def list_metadata_resolutions(sample_id: int | None = None) -> list[dict[str, Any]]:
    engine = get_engine()
    query = """
        SELECT sample_id, field, resolution_status, resolved_value,
               filename_value, analysis_value, provenance_note,
               parser_version, reconciled_at
        FROM metadata_resolutions
    """
    params: dict[str, Any] = {}
    if sample_id is not None:
        query += " WHERE sample_id = :sample_id"
        params["sample_id"] = sample_id
    query += " ORDER BY sample_id, field"
    with engine.begin() as conn:
        rows = conn.execute(text(query), params).fetchall()
    return [
        {
            "sample_id": int(row[0]),
            "field": row[1],
            "resolution_status": row[2],
            "resolved_value": row[3],
            "filename_value": row[4],
            "analysis_value": row[5],
            "provenance_note": row[6],
            "parser_version": row[7],
            "reconciled_at": row[8],
        }
        for row in rows
    ]


def _upsert_resolution(
    conn: Any,
    *,
    sample_id: int,
    field: str,
    status: str,
    resolved_value: str | None,
    filename_value: str | None,
    analysis_value: str | None,
    provenance_note: str,
    reconciled_at: str,
) -> None:
    conn.execute(
        text(
            """
            INSERT INTO metadata_resolutions (
                sample_id, field, resolution_status, resolved_value,
                filename_value, analysis_value, provenance_note,
                parser_version, reconciled_at
            ) VALUES (
                :sample_id, :field, :resolution_status, :resolved_value,
                :filename_value, :analysis_value, :provenance_note,
                :parser_version, :reconciled_at
            )
            ON CONFLICT(sample_id, field) DO UPDATE SET
                resolution_status=excluded.resolution_status,
                resolved_value=excluded.resolved_value,
                filename_value=excluded.filename_value,
                analysis_value=excluded.analysis_value,
                provenance_note=excluded.provenance_note,
                parser_version=excluded.parser_version,
                reconciled_at=excluded.reconciled_at
            """
        ),
        {
            "sample_id": sample_id,
            "field": field,
            "resolution_status": status,
            "resolved_value": resolved_value,
            "filename_value": filename_value,
            "analysis_value": analysis_value,
            "provenance_note": provenance_note,
            "parser_version": PATH_METADATA_PARSER_VERSION,
            "reconciled_at": reconciled_at,
        },
    )


def _prefer_path_claim(
    claims: list[dict[str, Any]], field: str
) -> dict[str, Any] | None:
    filename = next(
        (c for c in claims if c["field"] == field and c["source"] == SOURCE_FILENAME),
        None,
    )
    if filename is not None:
        return filename
    return next((c for c in claims if c["field"] == field), None)


def _reconcile_bpm(
    filename_value: str | None, analysis_bpm: float | None
) -> tuple[str, str | None, str]:
    analysis_display = round_bpm_display(analysis_bpm)
    analysis_str = str(analysis_display) if analysis_display is not None else None
    if filename_value is None and analysis_str is None:
        return STATUS_UNKNOWN, None, "no BPM evidence"
    if filename_value is None:
        return STATUS_ANALYSIS_ONLY, analysis_str, "analysis BPM only"
    try:
        label = float(filename_value)
    except (TypeError, ValueError):
        if analysis_str is None:
            return STATUS_UNKNOWN, None, "unparseable filename BPM"
        return STATUS_ANALYSIS_ONLY, analysis_str, "unparseable filename BPM"
    if analysis_bpm is None or analysis_display is None:
        return (
            STATUS_DECLARED_ONLY,
            str(int(label)),
            "filename BPM without analysis",
        )
    err = classify_bpm_error(float(analysis_bpm), label)
    if analysis_display == int(label) or err == "correct":
        return (
            STATUS_CONFIRMED,
            str(int(label)),
            "filename BPM confirmed by audio",
        )
    if err in {"half", "double"}:
        return (
            STATUS_COMPATIBLE,
            str(int(label)),
            f"filename BPM compatible via half/double ({err})",
        )
    return (
        STATUS_CONFLICT,
        None,
        f"BPM conflict filename={int(label)} analysis={analysis_display}",
    )


def _reconcile_key(
    filename_value: str | None, analysis_key: str | None
) -> tuple[str, str | None, str]:
    path_parsed = parse_key_signature(filename_value) if filename_value else None
    analysis_parsed = parse_key_signature(analysis_key) if analysis_key else None
    path_fmt = (
        format_key_signature(path_parsed.root, path_parsed.mode)
        if path_parsed is not None
        else None
    )
    analysis_fmt = (
        format_key_signature(analysis_parsed.root, analysis_parsed.mode)
        if analysis_parsed is not None
        else None
    )
    if path_fmt is None and analysis_fmt is None:
        return STATUS_UNKNOWN, None, "no key evidence"
    if path_fmt is None:
        return STATUS_ANALYSIS_ONLY, analysis_fmt, "analysis key only"
    if analysis_fmt is None:
        return STATUS_DECLARED_ONLY, path_fmt, "filename key without analysis"
    if is_same_root(path_parsed, analysis_parsed) and is_same_mode(
        path_parsed, analysis_parsed
    ):
        if path_parsed.mode is not None and analysis_parsed.mode is not None:
            return (
                STATUS_CONFIRMED,
                path_fmt,
                "filename key confirmed by analysis after canonicalization",
            )
        # Both root-only — treat as confirmed root-only agreement.
        return STATUS_CONFIRMED, path_fmt, "filename and analysis share root-only key"
    if is_same_root(path_parsed, analysis_parsed):
        if path_parsed.mode is not None and analysis_parsed.mode is None:
            return (
                STATUS_PARTIAL,
                format_key_signature(path_parsed.root, None),
                "key root agrees; analysis mode unresolved — not full confirmation",
            )
        if path_parsed.mode is None and analysis_parsed.mode is not None:
            return (
                STATUS_PARTIAL,
                analysis_fmt,
                "key root agrees; filename mode absent",
            )
        if (
            path_parsed.mode is not None
            and analysis_parsed.mode is not None
            and path_parsed.mode != analysis_parsed.mode
        ):
            return (
                STATUS_CONFLICT,
                None,
                f"key mode conflict filename={path_fmt} analysis={analysis_fmt}",
            )
    return (
        STATUS_CONFLICT,
        None,
        f"key conflict filename={path_fmt} analysis={analysis_fmt}",
    )


def _reconcile_class_or_type(
    field: str,
    filename_value: str | None,
    analysis_value: str | None,
) -> tuple[str, str | None, str]:
    def _norm(value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip().casefold()

    fn = _norm(filename_value)
    an = _norm(analysis_value)
    if fn is None and an is None:
        return STATUS_UNKNOWN, None, f"no {field} evidence"
    if fn is None:
        return STATUS_ANALYSIS_ONLY, analysis_value, f"analysis {field} only"
    if an is None:
        return STATUS_DECLARED_ONLY, filename_value, f"filename {field} without analysis"
    if fn == an:
        return (
            STATUS_CONFIRMED,
            filename_value,
            f"filename {field} confirmed by analysis",
        )
    return (
        STATUS_CONFLICT,
        None,
        f"{field} conflict filename={filename_value} analysis={analysis_value}",
    )


def run_path_metadata_prepass(
    sample_ids: list[int] | None = None,
) -> dict[str, int]:
    """Parse path claims for catalog samples. Fail-soft; never raises to callers."""
    init_db()
    engine = get_engine()
    parsed = 0
    refreshed = 0
    try:
        with engine.begin() as conn:
            if sample_ids:
                placeholders = ", ".join(
                    f":id_{i}" for i in range(len(sample_ids))
                )
                params = {f"id_{i}": sid for i, sid in enumerate(sample_ids)}
                rows = conn.execute(
                    text(
                        f"""
                        SELECT id, path, relpath FROM samples
                        WHERE id IN ({placeholders})
                        ORDER BY id
                        """
                    ),
                    params,
                ).fetchall()
            else:
                rows = conn.execute(
                    text("SELECT id, path, relpath FROM samples ORDER BY id")
                ).fetchall()

        for sid, path, relpath in rows:
            try:
                basename = Path(str(path)).name
                fp = path_fingerprint(basename, relpath)
                existing = list_path_metadata_claims(int(sid))
                if existing and all(c["path_fingerprint"] == fp for c in existing):
                    # Still re-parse when parser version changes.
                    if all(
                        c["parser_version"] == PATH_METADATA_PARSER_VERSION
                        for c in existing
                    ):
                        parsed += 1
                        continue
                claims = extract_claims_from_path(basename, relpath)
                replace_path_metadata_claims(
                    int(sid), claims, path_fingerprint_value=fp
                )
                # Searchable genre tags (do not wipe other sources).
                for claim in claims:
                    if claim.field == FIELD_GENRE:
                        upsert_sample_tag(
                            int(sid),
                            claim.normalized_value.casefold(),
                            claim.source,
                        )
                parsed += 1
                refreshed += 1
            except Exception:
                continue
    except Exception:
        return {"samples_considered": 0, "samples_refreshed": 0}
    return {"samples_considered": parsed, "samples_refreshed": refreshed}


def run_metadata_reconcile(
    sample_ids: list[int] | None = None,
) -> dict[str, int]:
    """Reconcile path claims against features. Never mutates features.*."""
    init_db()
    engine = get_engine()
    reconciled = 0
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    try:
        with engine.begin() as conn:
            if sample_ids:
                placeholders = ", ".join(
                    f":id_{i}" for i in range(len(sample_ids))
                )
                params = {f"id_{i}": sid for i, sid in enumerate(sample_ids)}
                rows = conn.execute(
                    text(
                        f"""
                        SELECT s.id, f.bpm, f.key, f.class, f.pred_type
                        FROM samples s
                        LEFT JOIN features f ON f.sample_id = s.id
                        WHERE s.id IN ({placeholders})
                        ORDER BY s.id
                        """
                    ),
                    params,
                ).fetchall()
            else:
                rows = conn.execute(
                    text(
                        """
                        SELECT s.id, f.bpm, f.key, f.class, f.pred_type
                        FROM samples s
                        LEFT JOIN features f ON f.sample_id = s.id
                        ORDER BY s.id
                        """
                    )
                ).fetchall()

        for sid, bpm, key, clazz, pred_type in rows:
            claims = list_path_metadata_claims(int(sid))
            with engine.begin() as conn:
                # BPM
                bpm_claim = _prefer_path_claim(claims, FIELD_BPM)
                status, resolved, note = _reconcile_bpm(
                    bpm_claim["normalized_value"] if bpm_claim else None,
                    float(bpm) if bpm is not None else None,
                )
                _upsert_resolution(
                    conn,
                    sample_id=int(sid),
                    field=FIELD_BPM,
                    status=status,
                    resolved_value=resolved,
                    filename_value=(
                        bpm_claim["normalized_value"] if bpm_claim else None
                    ),
                    analysis_value=(
                        str(round_bpm_display(bpm))
                        if bpm is not None and round_bpm_display(bpm) is not None
                        else None
                    ),
                    provenance_note=note,
                    reconciled_at=now,
                )

                # Key
                key_claim = _prefer_path_claim(claims, FIELD_KEY)
                status, resolved, note = _reconcile_key(
                    key_claim["normalized_value"] if key_claim else None,
                    key if isinstance(key, str) else None,
                )
                _upsert_resolution(
                    conn,
                    sample_id=int(sid),
                    field=FIELD_KEY,
                    status=status,
                    resolved_value=resolved,
                    filename_value=(
                        key_claim["normalized_value"] if key_claim else None
                    ),
                    analysis_value=key if isinstance(key, str) else None,
                    provenance_note=note,
                    reconciled_at=now,
                )

                # sample_class
                class_claim = _prefer_path_claim(claims, FIELD_SAMPLE_CLASS)
                status, resolved, note = _reconcile_class_or_type(
                    FIELD_SAMPLE_CLASS,
                    class_claim["normalized_value"] if class_claim else None,
                    clazz if isinstance(clazz, str) else None,
                )
                _upsert_resolution(
                    conn,
                    sample_id=int(sid),
                    field=FIELD_SAMPLE_CLASS,
                    status=status,
                    resolved_value=resolved,
                    filename_value=(
                        class_claim["normalized_value"] if class_claim else None
                    ),
                    analysis_value=clazz if isinstance(clazz, str) else None,
                    provenance_note=note,
                    reconciled_at=now,
                )

                # pred_type
                pred_claim = _prefer_path_claim(claims, FIELD_PRED_TYPE)
                status, resolved, note = _reconcile_class_or_type(
                    FIELD_PRED_TYPE,
                    pred_claim["normalized_value"] if pred_claim else None,
                    pred_type if isinstance(pred_type, str) else None,
                )
                _upsert_resolution(
                    conn,
                    sample_id=int(sid),
                    field=FIELD_PRED_TYPE,
                    status=status,
                    resolved_value=resolved,
                    filename_value=(
                        pred_claim["normalized_value"] if pred_claim else None
                    ),
                    analysis_value=pred_type if isinstance(pred_type, str) else None,
                    provenance_note=note,
                    reconciled_at=now,
                )

                # genre — DECLARED_ONLY (no analyzer)
                genre_claims = [c for c in claims if c["field"] == FIELD_GENRE]
                if genre_claims:
                    # One resolution row summarizing primary genre claim.
                    primary = genre_claims[0]
                    joined = ", ".join(
                        sorted({c["normalized_value"] for c in genre_claims})
                    )
                    _upsert_resolution(
                        conn,
                        sample_id=int(sid),
                        field=FIELD_GENRE,
                        status=STATUS_DECLARED_ONLY,
                        resolved_value=joined,
                        filename_value=joined,
                        analysis_value=None,
                        provenance_note="path genre without independent genre analyzer",
                        reconciled_at=now,
                    )
                else:
                    _upsert_resolution(
                        conn,
                        sample_id=int(sid),
                        field=FIELD_GENRE,
                        status=STATUS_UNKNOWN,
                        resolved_value=None,
                        filename_value=None,
                        analysis_value=None,
                        provenance_note="no genre evidence",
                        reconciled_at=now,
                    )
            reconciled += 1
    except Exception:
        return {"samples_reconciled": 0}
    return {"samples_reconciled": reconciled}


__all__ = [
    "PATH_METADATA_PARSER_VERSION",
    "PathClaim",
    "path_fingerprint",
    "extract_bpm_hint",
    "extract_key_hint",
    "extract_type_hint",
    "extract_instrument_hint",
    "extract_pred_type_claim",
    "extract_genre_claims",
    "extract_claims_from_path",
    "replace_path_metadata_claims",
    "list_path_metadata_claims",
    "list_metadata_resolutions",
    "run_path_metadata_prepass",
    "run_metadata_reconcile",
    "STATUS_CONFIRMED",
    "STATUS_COMPATIBLE",
    "STATUS_PARTIAL",
    "STATUS_CONFLICT",
    "STATUS_DECLARED_ONLY",
    "STATUS_ANALYSIS_ONLY",
    "STATUS_UNKNOWN",
]
