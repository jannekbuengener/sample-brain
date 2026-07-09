"""Read-only catalog.db access for the workbench (no writes, no schema changes)."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Any

from . import config
from .workbench_library import normalize_display_name

CATALOG_SOURCE = "catalog"
CATALOG_LIBRARY_FOLDER_LABEL = "catalog.db (read-only)"

_CATALOG_SELECT_SQL = """
SELECT
    s.path,
    s.relpath,
    s.size_bytes,
    s.duration,
    f.bpm,
    f.key,
    f.key_conf,
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


def _catalog_row_from_sqlite(row: sqlite3.Row) -> CatalogSampleRow:
    path = row["path"]
    return CatalogSampleRow(
        path=path,
        relative_path=row["relpath"] or "",
        display_name=normalize_display_name(PurePath(path).name),
        size_bytes=row["size_bytes"],
        duration=row["duration"],
        bpm=row["bpm"],
        key=row["key"],
        key_conf=row["key_conf"],
        loudness=row["loudness"],
        brightness=row["brightness"],
        sample_class=row["class"],
        pred_type=row["pred_type"],
        status=row["analysis_status"],
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

    sql = _CATALOG_SELECT_SQL
    params: tuple[Any, ...] = ()
    if limit is not None:
        if limit < 0:
            raise ValueError("limit must be non-negative")
        sql = sql.rstrip() + "\nLIMIT ?"
        params = (limit,)

    try:
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return []

    return [_catalog_row_from_sqlite(row) for row in rows]


__all__ = [
    "CATALOG_LIBRARY_FOLDER_LABEL",
    "CATALOG_SOURCE",
    "CatalogSampleRow",
    "catalog_available",
    "catalog_db_path",
    "load_catalog_samples",
]
