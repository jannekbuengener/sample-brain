"""Read-only catalog.db access for the workbench (no writes, no schema changes)."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Any

from . import config
from .db import KeyAnalysisFeatureRecord, decode_key_analysis_feature_record
from .workbench_library import normalize_display_name

CATALOG_SOURCE = "catalog"
CATALOG_LIBRARY_FOLDER_LABEL = "catalog.db (read-only)"
DEFAULT_CATALOG_LOAD_LIMIT = 5000

_OPTIONAL_KEY_COLUMNS = (
    "key_mode",
    "key_mode_evidence",
    "key_analysis_contract_version",
    "key_root_evidence",
)


def _optional_feature_expr(feature_columns: set[str], column: str) -> str:
    if column in feature_columns:
        return f"f.{column}"
    return f"NULL AS {column}"


def _catalog_select_sql(feature_columns: set[str]) -> str:
    optional_key_fields = ",\n    ".join(
        _optional_feature_expr(feature_columns, column)
        for column in _OPTIONAL_KEY_COLUMNS
    )
    return f"""
SELECT
    s.id AS sample_id,
    s.path,
    s.relpath,
    s.size_bytes,
    s.duration,
    f.sample_id AS feature_sample_id,
    f.bpm,
    f.key,
    f.key_conf,
    {optional_key_fields},
    f.loudness,
    f.brightness,
    f.class,
    f.pred_type,
    CASE WHEN f.sample_id IS NULL THEN 'pending' ELSE 'ok' END AS analysis_status
FROM samples s
LEFT JOIN features f ON f.sample_id = s.id
ORDER BY s.path COLLATE NOCASE
"""


def catalog_db_path(path: Path | str | None = None) -> Path:
    """Resolve the catalog database path (profile/env/default via config)."""
    if path is not None:
        resolved = Path(path).expanduser()
        if not resolved.is_absolute():
            resolved = (config.PROJECT_ROOT / resolved).resolve()
        else:
            resolved = resolved.resolve()
        return resolved
    return config.DB_PATH


def catalog_available(path: Path | str | None = None) -> bool:
    """Return True when *path* exists and contains a ``samples`` table."""
    db_path = catalog_db_path(path)
    if not db_path.is_file():
        return False
    try:
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        try:
            row = conn.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = 'samples'
                LIMIT 1
                """
            ).fetchone()
            return row is not None
        finally:
            conn.close()
    except sqlite3.Error:
        return False


@dataclass
class CatalogSampleRow:
    path: str
    relative_path: str
    display_name: str
    size_bytes: int | None
    duration: float | None
    bpm: float | None
    key: str | None
    key_conf: float | None
    loudness: float | None
    brightness: float | None
    sample_class: str | None
    pred_type: str | None
    status: str
    source: str = CATALOG_SOURCE
    key_claim: str | None = None
    key_mode: str | None = None
    key_analysis_contract_version: int | None = None
    key_claim_valid: bool = False
    key_matching_eligible: bool = False
    key_root_evidence_kind: str | None = None
    key_mode_evidence_kind: str | None = None

    def to_workbench_row(self) -> Any:
        from .workbench_controller import WorkbenchRow

        details: dict[str, Any] = {
            "path": self.path,
            "relative_path": self.relative_path,
            "source": self.source,
            "catalog_readonly": True,
            "library_folder": CATALOG_LIBRARY_FOLDER_LABEL,
        }
        if self.size_bytes is not None:
            details["size_bytes"] = self.size_bytes
        if self.duration is not None:
            details["duration"] = self.duration

        relative_path = self.relative_path or PurePath(self.path).name

        return WorkbenchRow(
            display_name=self.display_name,
            relative_path=relative_path,
            path=self.path,
            bpm=self.bpm,
            key=self.key,
            key_conf=self.key_conf,
            loudness=self.loudness,
            brightness=self.brightness,
            sample_class=self.sample_class,
            pred_type=self.pred_type,
            status=self.status,
            error=None,
            error_code=None,
            details=details,
        )


def _decode_catalog_key_claim(row: sqlite3.Row) -> KeyAnalysisFeatureRecord | None:
    if row["feature_sample_id"] is None:
        return None
    return decode_key_analysis_feature_record(
        {
            "sample_id": row["sample_id"],
            "key": row["key"],
            "key_conf": row["key_conf"],
            "key_mode": row["key_mode"],
            "key_mode_evidence": row["key_mode_evidence"],
            "key_analysis_contract_version": row["key_analysis_contract_version"],
            "key_root_evidence": row["key_root_evidence"],
        }
    )


def _catalog_row_from_sqlite(row: sqlite3.Row) -> CatalogSampleRow:
    path = row["path"]
    record = _decode_catalog_key_claim(row)
    valid_claim = record is not None and record.key is not None
    legacy_v1 = valid_claim and record.key_analysis_contract_version is None
    root_kind = (
        record.key_root_evidence.get("kind")
        if record is not None and record.key_root_evidence is not None
        else None
    )
    mode_kind = (
        record.key_mode_evidence.get("kind")
        if record is not None and record.key_mode_evidence is not None
        else None
    )
    return CatalogSampleRow(
        path=path,
        relative_path=row["relpath"] or "",
        display_name=normalize_display_name(PurePath(path).name),
        size_bytes=row["size_bytes"],
        duration=row["duration"],
        bpm=row["bpm"],
        # Boundary: only legacy V1 remains downstream-eligible in #661.
        # Valid V2 is retained as a catalog claim below but is not projected
        # into WorkbenchRow.key/key_conf, so Harmony/cache behavior cannot
        # activate implicitly.
        key=record.key if legacy_v1 else None,
        key_conf=record.key_conf if legacy_v1 else None,
        loudness=row["loudness"],
        brightness=row["brightness"],
        sample_class=row["class"],
        pred_type=row["pred_type"],
        status=row["analysis_status"],
        key_claim=record.key if valid_claim else None,
        key_mode=record.key_mode if valid_claim else None,
        key_analysis_contract_version=(
            record.key_analysis_contract_version if valid_claim else None
        ),
        key_claim_valid=valid_claim,
        key_matching_eligible=legacy_v1,
        key_root_evidence_kind=root_kind if valid_claim else None,
        key_mode_evidence_kind=mode_kind if valid_claim else None,
    )


def load_catalog_samples(
    path: Path | str | None = None,
    *,
    limit: int | None = None,
) -> list[CatalogSampleRow]:
    """Load catalog samples via SELECT-only access. Returns [] when unavailable."""
    db_path = catalog_db_path(path)
    if not catalog_available(db_path):
        return []

    params: tuple[Any, ...] = ()
    try:
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            feature_columns = {
                str(column[1])
                for column in conn.execute("PRAGMA table_info(features)").fetchall()
            }
            sql = _catalog_select_sql(feature_columns)
            if limit is not None:
                if limit < 0:
                    raise ValueError("limit must be non-negative")
                sql = sql.rstrip() + "\nLIMIT ?"
                params = (limit,)
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return []

    return [_catalog_row_from_sqlite(row) for row in rows]


def count_catalog_samples(path: Path | str | None = None) -> int:
    """Return total sample count in catalog via SELECT-only access. Returns 0 when unavailable."""
    db_path = catalog_db_path(path)
    if not catalog_available(db_path):
        return 0
    try:
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        try:
            row = conn.execute("SELECT COUNT(*) AS n FROM samples").fetchone()
            return int(row[0]) if row is not None else 0
        finally:
            conn.close()
    except sqlite3.Error:
        return 0


def format_catalog_load_status(
    loaded: int,
    total: int,
    *,
    limit: int | None = None,
) -> str:
    """Build a user-facing catalog load status line (no performance claims)."""
    if loaded <= 0:
        return "Catalog-Samples: keine geladen (read-only)."
    base = f"Catalog-Samples: {loaded}"
    if total > loaded:
        base += f" von {total}"
    if limit is not None and total > limit:
        base += " (Limit aktiv)"
    base += " geladen (read-only)."
    return base


__all__ = [
    "CATALOG_LIBRARY_FOLDER_LABEL",
    "CATALOG_SOURCE",
    "DEFAULT_CATALOG_LOAD_LIMIT",
    "CatalogSampleRow",
    "catalog_available",
    "catalog_db_path",
    "count_catalog_samples",
    "format_catalog_load_status",
    "load_catalog_samples",
]
