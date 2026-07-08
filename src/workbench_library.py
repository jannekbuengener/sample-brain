"""Persistent workbench library cache (user-local SQLite, separate from catalog.db)."""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePath
from typing import Any, Mapping

WORKBENCH_ANALYZER_VERSION = "workbench_v1"
_LIBRARY_DB_NAME = "workbench_library.db"


def _workbench_state_dir(*, env: Mapping[str, str] | None = None) -> Path:
    import os

    env_map = os.environ if env is None else env
    override = env_map.get("SAMPLE_BRAIN_WORKBENCH_STATE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / ".sample-brain").resolve()


def workbench_library_db_path(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    base = state_dir if state_dir is not None else _workbench_state_dir(env=env)
    return base / _LIBRARY_DB_NAME


def connect_workbench_library(path: Path | None = None) -> sqlite3.Connection:
    db_path = path if path is not None else workbench_library_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_workbench_library(db_path: Path | None = None) -> None:
    with connect_workbench_library(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS folders (
                id INTEGER PRIMARY KEY,
                path TEXT UNIQUE NOT NULL,
                last_scan_at TEXT,
                last_opened_at TEXT
            );

            CREATE TABLE IF NOT EXISTS samples (
                id INTEGER PRIMARY KEY,
                folder_id INTEGER NOT NULL,
                original_path TEXT UNIQUE NOT NULL,
                relative_path TEXT,
                size_bytes INTEGER,
                mtime_ns INTEGER,
                display_name TEXT,
                bpm REAL,
                key TEXT,
                key_conf REAL,
                loudness REAL,
                brightness REAL,
                sample_class TEXT,
                pred_type TEXT,
                status TEXT,
                error_code TEXT,
                quality_note TEXT,
                tags TEXT,
                analyzed_at TEXT,
                analyzer_version TEXT,
                FOREIGN KEY(folder_id) REFERENCES folders(id)
            );

            CREATE INDEX IF NOT EXISTS idx_samples_folder_id ON samples(folder_id);
            CREATE INDEX IF NOT EXISTS idx_samples_lookup
                ON samples(original_path, size_bytes, mtime_ns);
            """
        )
        conn.commit()


def normalize_display_name(filename: str) -> str:
    """Derive an internal display title from a filename without touching the file."""
    stem = PurePath(filename.strip()).stem
    text = stem.replace("_", " ").replace("-", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text or stem or filename.strip()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class CachedWorkbenchRow:
    original_path: str
    relative_path: str
    display_name: str
    size_bytes: int
    mtime_ns: int
    bpm: float | None
    key: str | None
    key_conf: float | None
    loudness: float | None
    brightness: float | None
    sample_class: str | None
    pred_type: str | None
    status: str
    error_code: str | None = None
    quality_note: str | None = None
    tags: list[str] | None = None
    analyzed_at: str | None = None
    analyzer_version: str | None = None

    def to_workbench_row(self) -> Any:
        from .workbench_controller import WorkbenchRow, error_message_for_code

        details: dict[str, Any] = {
            "path": self.original_path,
            "relative_path": self.relative_path,
        }
        if self.error_code:
            details["error_code"] = self.error_code
            details["error_detail"] = self.quality_note or ""
        if self.quality_note and self.status == "ok":
            details["short_audio_warning"] = self.quality_note
        if self.tags:
            details["tags"] = list(self.tags)

        return WorkbenchRow(
            display_name=self.display_name,
            relative_path=self.relative_path,
            path=self.original_path,
            bpm=self.bpm,
            key=self.key,
            key_conf=self.key_conf,
            loudness=self.loudness,
            brightness=self.brightness,
            sample_class=self.sample_class,
            pred_type=self.pred_type,
            status=self.status,
            error=error_message_for_code(self.error_code) if self.error_code else None,
            error_code=self.error_code,
            details=details,
        )


def upsert_folder(folder_path: Path | str, *, db_path: Path | None = None) -> int:
    path = Path(folder_path).expanduser().resolve()
    now = _utc_now_iso()
    init_workbench_library(db_path)
    with connect_workbench_library(db_path) as conn:
        conn.execute(
            """
            INSERT INTO folders (path, last_scan_at, last_opened_at)
            VALUES (?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                last_scan_at=excluded.last_scan_at,
                last_opened_at=excluded.last_opened_at
            """,
            (str(path), now, now),
        )
        row = conn.execute("SELECT id FROM folders WHERE path = ?", (str(path),)).fetchone()
        conn.commit()
    assert row is not None
    return int(row["id"])


def lookup_sample(
    original_path: Path | str,
    size_bytes: int,
    mtime_ns: int,
    *,
    db_path: Path | None = None,
) -> CachedWorkbenchRow | None:
    path = str(Path(original_path).expanduser().resolve())
    init_workbench_library(db_path)
    with connect_workbench_library(db_path) as conn:
        row = conn.execute(
            """
            SELECT * FROM samples
            WHERE original_path = ? AND size_bytes = ? AND mtime_ns = ?
            """,
            (path, size_bytes, mtime_ns),
        ).fetchone()
    if row is None:
        return None
    tags_raw = row["tags"]
    tags = json.loads(tags_raw) if tags_raw else None
    return CachedWorkbenchRow(
        original_path=row["original_path"],
        relative_path=row["relative_path"] or "",
        display_name=row["display_name"] or PurePath(path).name,
        size_bytes=int(row["size_bytes"]),
        mtime_ns=int(row["mtime_ns"]),
        bpm=row["bpm"],
        key=row["key"],
        key_conf=row["key_conf"],
        loudness=row["loudness"],
        brightness=row["brightness"],
        sample_class=row["sample_class"],
        pred_type=row["pred_type"],
        status=row["status"] or "ok",
        error_code=row["error_code"],
        quality_note=row["quality_note"],
        tags=tags,
        analyzed_at=row["analyzed_at"],
        analyzer_version=row["analyzer_version"],
    )


def upsert_sample(
    folder_id: int,
    row: Any,
    *,
    size_bytes: int,
    mtime_ns: int,
    db_path: Path | None = None,
    analyzer_version: str = WORKBENCH_ANALYZER_VERSION,
) -> None:
    from .workbench_controller import WorkbenchRow

    if not isinstance(row, WorkbenchRow):
        raise TypeError("row must be a WorkbenchRow")

    tags = row.details.get("tags")
    if tags is not None and not isinstance(tags, list):
        tags = [str(tags)]
    quality_note = row.details.get("short_audio_warning")
    if row.status == "error":
        quality_note = row.details.get("error_detail") or quality_note

    init_workbench_library(db_path)
    with connect_workbench_library(db_path) as conn:
        conn.execute(
            """
            INSERT INTO samples (
                folder_id, original_path, relative_path, size_bytes, mtime_ns,
                display_name, bpm, key, key_conf, loudness, brightness,
                sample_class, pred_type, status, error_code, quality_note,
                tags, analyzed_at, analyzer_version
            ) VALUES (
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?
            )
            ON CONFLICT(original_path) DO UPDATE SET
                folder_id=excluded.folder_id,
                relative_path=excluded.relative_path,
                size_bytes=excluded.size_bytes,
                mtime_ns=excluded.mtime_ns,
                display_name=excluded.display_name,
                bpm=excluded.bpm,
                key=excluded.key,
                key_conf=excluded.key_conf,
                loudness=excluded.loudness,
                brightness=excluded.brightness,
                sample_class=excluded.sample_class,
                pred_type=excluded.pred_type,
                status=excluded.status,
                error_code=excluded.error_code,
                quality_note=excluded.quality_note,
                tags=excluded.tags,
                analyzed_at=excluded.analyzed_at,
                analyzer_version=excluded.analyzer_version
            """,
            (
                folder_id,
                str(Path(row.path).expanduser().resolve()),
                row.relative_path,
                size_bytes,
                mtime_ns,
                row.display_name,
                row.bpm,
                row.key,
                row.key_conf,
                row.loudness,
                row.brightness,
                row.sample_class,
                row.pred_type,
                row.status,
                row.error_code,
                quality_note,
                json.dumps(tags) if tags else None,
                _utc_now_iso(),
                analyzer_version,
            ),
        )
        conn.commit()


def load_folder_samples(
    folder_path: Path | str,
    *,
    db_path: Path | None = None,
) -> list[CachedWorkbenchRow]:
    path = str(Path(folder_path).expanduser().resolve())
    init_workbench_library(db_path)
    with connect_workbench_library(db_path) as conn:
        rows = conn.execute(
            """
            SELECT s.* FROM samples s
            JOIN folders f ON f.id = s.folder_id
            WHERE f.path = ?
            ORDER BY s.relative_path, s.display_name
            """,
            (path,),
        ).fetchall()
    result: list[CachedWorkbenchRow] = []
    for row in rows:
        tags_raw = row["tags"]
        tags = json.loads(tags_raw) if tags_raw else None
        result.append(
            CachedWorkbenchRow(
                original_path=row["original_path"],
                relative_path=row["relative_path"] or "",
                display_name=row["display_name"] or "",
                size_bytes=int(row["size_bytes"]),
                mtime_ns=int(row["mtime_ns"]),
                bpm=row["bpm"],
                key=row["key"],
                key_conf=row["key_conf"],
                loudness=row["loudness"],
                brightness=row["brightness"],
                sample_class=row["sample_class"],
                pred_type=row["pred_type"],
                status=row["status"] or "ok",
                error_code=row["error_code"],
                quality_note=row["quality_note"],
                tags=tags,
                analyzed_at=row["analyzed_at"],
                analyzer_version=row["analyzer_version"],
            )
        )
    return result


__all__ = [
    "WORKBENCH_ANALYZER_VERSION",
    "CachedWorkbenchRow",
    "connect_workbench_library",
    "init_workbench_library",
    "load_folder_samples",
    "lookup_sample",
    "normalize_display_name",
    "upsert_folder",
    "upsert_sample",
    "workbench_library_db_path",
]
