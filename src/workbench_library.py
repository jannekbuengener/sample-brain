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
WORKBENCH_LIBRARY_SCHEMA_VERSION = 2
_LIBRARY_DB_NAME = "workbench_library.db"

_CUE_SAMPLE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("cue_start_ms", "INTEGER DEFAULT 0"),
    ("attack_ms", "INTEGER DEFAULT NULL"),
    ("loop_start_ms", "INTEGER DEFAULT NULL"),
    ("loop_end_ms", "INTEGER DEFAULT NULL"),
    ("cue_source", "TEXT DEFAULT 'manual'"),
    ("cue_updated_at", "TEXT DEFAULT NULL"),
)

_SAMPLES_CREATE_SQL = """
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
                cue_start_ms INTEGER DEFAULT 0,
                attack_ms INTEGER DEFAULT NULL,
                loop_start_ms INTEGER DEFAULT NULL,
                loop_end_ms INTEGER DEFAULT NULL,
                cue_source TEXT DEFAULT 'manual',
                cue_updated_at TEXT DEFAULT NULL,
                FOREIGN KEY(folder_id) REFERENCES folders(id)
            );
"""


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

"""
            + _SAMPLES_CREATE_SQL
            + """
            CREATE INDEX IF NOT EXISTS idx_samples_folder_id ON samples(folder_id);
            CREATE INDEX IF NOT EXISTS idx_samples_lookup
                ON samples(original_path, size_bytes, mtime_ns);
            """
        )
        _migrate_library_schema_v2(conn)
        conn.commit()


def normalize_display_name(filename: str) -> str:
    """Derive an internal display title from a filename without touching the file."""
    stem = PurePath(filename.strip()).stem
    text = stem.replace("_", " ").replace("-", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text or stem or filename.strip()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class WorkbenchCueValidationError(ValueError):
    """Raised when cue metadata fails validation."""


class WorkbenchCueNotFoundError(LookupError):
    """Raised when cue metadata is saved for an unknown library sample."""


@dataclass
class WorkbenchCueMetadata:
    cue_start_ms: int = 0
    attack_ms: int | None = None
    loop_start_ms: int | None = None
    loop_end_ms: int | None = None
    cue_source: str = "manual"
    cue_updated_at: str | None = None


def default_workbench_cue_metadata() -> WorkbenchCueMetadata:
    """Return default cue metadata (start at 0 ms)."""
    return WorkbenchCueMetadata()


def _sample_table_columns(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("PRAGMA table_info(samples)").fetchall()
    return {str(row[1]) for row in rows}


def _migrate_library_schema_v2(conn: sqlite3.Connection) -> None:
    """Add cue metadata columns to existing workbench library databases."""
    columns = _sample_table_columns(conn)
    if not columns:
        return
    for name, definition in _CUE_SAMPLE_COLUMNS:
        if name not in columns:
            conn.execute(f"ALTER TABLE samples ADD COLUMN {name} {definition}")


def validate_workbench_cue_metadata(
    metadata: WorkbenchCueMetadata,
    *,
    duration_ms: int | None = None,
) -> None:
    """Validate cue metadata invariants. Raises WorkbenchCueValidationError."""
    if metadata.cue_start_ms < 0:
        raise WorkbenchCueValidationError("cue_start_ms must be non-negative")
    if metadata.attack_ms is not None and metadata.attack_ms < 0:
        raise WorkbenchCueValidationError("attack_ms must be non-negative when set")
    if metadata.loop_start_ms is not None and metadata.loop_start_ms < 0:
        raise WorkbenchCueValidationError("loop_start_ms must be non-negative when set")
    if metadata.loop_end_ms is not None and metadata.loop_end_ms < 0:
        raise WorkbenchCueValidationError("loop_end_ms must be non-negative when set")
    if metadata.loop_start_ms is not None and metadata.loop_end_ms is None:
        raise WorkbenchCueValidationError("loop_end_ms required when loop_start_ms is set")
    if metadata.loop_end_ms is not None and metadata.loop_start_ms is None:
        raise WorkbenchCueValidationError("loop_start_ms required when loop_end_ms is set")
    if (
        metadata.loop_start_ms is not None
        and metadata.loop_end_ms is not None
        and metadata.loop_end_ms < metadata.loop_start_ms
    ):
        raise WorkbenchCueValidationError("loop_end_ms must be >= loop_start_ms")
    if duration_ms is not None and duration_ms > 0:
        if metadata.cue_start_ms >= duration_ms:
            raise WorkbenchCueValidationError("cue_start_ms must be before sample end")
        if metadata.attack_ms is not None and metadata.attack_ms >= duration_ms:
            raise WorkbenchCueValidationError("attack_ms must be before sample end")
        if metadata.loop_start_ms is not None and metadata.loop_start_ms >= duration_ms:
            raise WorkbenchCueValidationError("loop_start_ms must be before sample end")
        if metadata.loop_end_ms is not None and metadata.loop_end_ms > duration_ms:
            raise WorkbenchCueValidationError("loop_end_ms must not exceed sample duration")


def _cue_metadata_from_row(row: sqlite3.Row | None) -> WorkbenchCueMetadata:
    if row is None:
        return default_workbench_cue_metadata()
    cue_start = row["cue_start_ms"]
    return WorkbenchCueMetadata(
        cue_start_ms=0 if cue_start is None else int(cue_start),
        attack_ms=None if row["attack_ms"] is None else int(row["attack_ms"]),
        loop_start_ms=None if row["loop_start_ms"] is None else int(row["loop_start_ms"]),
        loop_end_ms=None if row["loop_end_ms"] is None else int(row["loop_end_ms"]),
        cue_source=row["cue_source"] or "manual",
        cue_updated_at=row["cue_updated_at"],
    )


def load_sample_cue(
    original_path: Path | str,
    *,
    db_path: Path | None = None,
) -> WorkbenchCueMetadata:
    """Load cue metadata for a library sample. Returns defaults when unknown."""
    path = str(Path(original_path).expanduser().resolve())
    init_workbench_library(db_path)
    with connect_workbench_library(db_path) as conn:
        row = conn.execute(
            """
            SELECT cue_start_ms, attack_ms, loop_start_ms, loop_end_ms,
                   cue_source, cue_updated_at
            FROM samples
            WHERE original_path = ?
            """,
            (path,),
        ).fetchone()
    return _cue_metadata_from_row(row)


def save_sample_cue(
    original_path: Path | str,
    metadata: WorkbenchCueMetadata,
    *,
    db_path: Path | None = None,
    duration_ms: int | None = None,
) -> None:
    """Persist cue metadata for an existing library sample."""
    path = str(Path(original_path).expanduser().resolve())
    validate_workbench_cue_metadata(metadata, duration_ms=duration_ms)
    init_workbench_library(db_path)
    updated_at = metadata.cue_updated_at or _utc_now_iso()
    with connect_workbench_library(db_path) as conn:
        row = conn.execute(
            "SELECT id FROM samples WHERE original_path = ?",
            (path,),
        ).fetchone()
        if row is None:
            raise WorkbenchCueNotFoundError(f"sample not in workbench library: {path}")
        conn.execute(
            """
            UPDATE samples SET
                cue_start_ms = ?,
                attack_ms = ?,
                loop_start_ms = ?,
                loop_end_ms = ?,
                cue_source = ?,
                cue_updated_at = ?
            WHERE original_path = ?
            """,
            (
                metadata.cue_start_ms,
                metadata.attack_ms,
                metadata.loop_start_ms,
                metadata.loop_end_ms,
                metadata.cue_source,
                updated_at,
                path,
            ),
        )
        conn.commit()


@dataclass
class LibraryFolder:
    id: int
    path: str
    last_scan_at: str | None
    last_opened_at: str | None


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
    library_folder_path: str | None = None

    def to_workbench_row(self) -> Any:
        from .workbench_controller import WorkbenchRow, error_message_for_code

        details: dict[str, Any] = {
            "path": self.original_path,
            "relative_path": self.relative_path,
        }
        if self.library_folder_path:
            details["library_folder"] = self.library_folder_path
        if self.error_code:
            details["error_code"] = self.error_code
            details["error_detail"] = self.quality_note or ""
        if self.quality_note and self.status == "ok":
            details["short_audio_warning"] = self.quality_note
        if self.tags:
            details["tags"] = list(self.tags)

        relative_path = self.relative_path
        if self.library_folder_path:
            folder_label = PurePath(self.library_folder_path).name
            if relative_path:
                relative_path = f"{folder_label}/{relative_path}"
            else:
                relative_path = folder_label

        return WorkbenchRow(
            display_name=self.display_name,
            relative_path=relative_path,
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


def _cached_row_from_sqlite_row(
    row: sqlite3.Row,
    *,
    library_folder_path: str | None = None,
) -> CachedWorkbenchRow:
    tags_raw = row["tags"]
    tags = json.loads(tags_raw) if tags_raw else None
    folder_path = library_folder_path
    if folder_path is None and "library_folder_path" in row.keys():
        folder_path = row["library_folder_path"]
    original_path = row["original_path"]
    return CachedWorkbenchRow(
        original_path=original_path,
        relative_path=row["relative_path"] or "",
        display_name=row["display_name"] or PurePath(original_path).name,
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
        library_folder_path=folder_path,
    )


def _resolve_folder_id(
    folder_id_or_path: int | str | Path,
    conn: sqlite3.Connection,
) -> int | None:
    if isinstance(folder_id_or_path, int):
        row = conn.execute(
            "SELECT id FROM folders WHERE id = ?",
            (folder_id_or_path,),
        ).fetchone()
        return int(row["id"]) if row is not None else None

    path = str(Path(folder_id_or_path).expanduser().resolve())
    row = conn.execute("SELECT id FROM folders WHERE path = ?", (path,)).fetchone()
    return int(row["id"]) if row is not None else None


def register_library_folder(folder_path: Path | str, *, db_path: Path | None = None) -> int:
    """Add a folder to the workbench library without running analysis."""
    path = Path(folder_path).expanduser().resolve()
    now = _utc_now_iso()
    init_workbench_library(db_path)
    with connect_workbench_library(db_path) as conn:
        conn.execute(
            """
            INSERT INTO folders (path, last_scan_at, last_opened_at)
            VALUES (?, NULL, ?)
            ON CONFLICT(path) DO UPDATE SET
                last_opened_at=excluded.last_opened_at
            """,
            (str(path), now),
        )
        row = conn.execute("SELECT id FROM folders WHERE path = ?", (str(path),)).fetchone()
        conn.commit()
    assert row is not None
    return int(row["id"])


def mark_folder_opened(folder_path: Path | str, *, db_path: Path | None = None) -> None:
    """Update last_opened_at for a known library folder."""
    path = str(Path(folder_path).expanduser().resolve())
    now = _utc_now_iso()
    init_workbench_library(db_path)
    with connect_workbench_library(db_path) as conn:
        conn.execute(
            "UPDATE folders SET last_opened_at = ? WHERE path = ?",
            (now, path),
        )
        conn.commit()


def list_library_folders(*, db_path: Path | None = None) -> list[LibraryFolder]:
    """Return known library folders, most recently opened first."""
    init_workbench_library(db_path)
    with connect_workbench_library(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, path, last_scan_at, last_opened_at
            FROM folders
            ORDER BY
                CASE WHEN last_opened_at IS NULL THEN 1 ELSE 0 END,
                last_opened_at DESC,
                path COLLATE NOCASE ASC
            """
        ).fetchall()
    return [
        LibraryFolder(
            id=int(row["id"]),
            path=row["path"],
            last_scan_at=row["last_scan_at"],
            last_opened_at=row["last_opened_at"],
        )
        for row in rows
    ]


def remove_library_folder(
    folder_id_or_path: int | str | Path,
    *,
    db_path: Path | None = None,
) -> bool:
    """Remove folder metadata and cached samples from the workbench library.

    Does not delete or modify any files on disk. Idempotent: returns False when
    the folder was not in the library.
    """
    init_workbench_library(db_path)
    with connect_workbench_library(db_path) as conn:
        folder_id = _resolve_folder_id(folder_id_or_path, conn)
        if folder_id is None:
            return False
        conn.execute("DELETE FROM samples WHERE folder_id = ?", (folder_id,))
        conn.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
        conn.commit()
    return True


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
    return [_cached_row_from_sqlite_row(row, library_folder_path=path) for row in rows]


def load_all_cached_samples(*, db_path: Path | None = None) -> list[CachedWorkbenchRow]:
    """Load cached samples from every registered workbench library folder."""
    init_workbench_library(db_path)
    with connect_workbench_library(db_path) as conn:
        rows = conn.execute(
            """
            SELECT s.*, f.path AS library_folder_path
            FROM samples s
            JOIN folders f ON f.id = s.folder_id
            ORDER BY f.path COLLATE NOCASE, s.relative_path, s.display_name
            """
        ).fetchall()
    return [_cached_row_from_sqlite_row(row) for row in rows]


__all__ = [
    "WORKBENCH_ANALYZER_VERSION",
    "WORKBENCH_LIBRARY_SCHEMA_VERSION",
    "CachedWorkbenchRow",
    "LibraryFolder",
    "WorkbenchCueMetadata",
    "WorkbenchCueNotFoundError",
    "WorkbenchCueValidationError",
    "connect_workbench_library",
    "default_workbench_cue_metadata",
    "init_workbench_library",
    "list_library_folders",
    "load_all_cached_samples",
    "load_folder_samples",
    "load_sample_cue",
    "lookup_sample",
    "mark_folder_opened",
    "normalize_display_name",
    "register_library_folder",
    "remove_library_folder",
    "save_sample_cue",
    "upsert_folder",
    "upsert_sample",
    "validate_workbench_cue_metadata",
    "workbench_library_db_path",
]
