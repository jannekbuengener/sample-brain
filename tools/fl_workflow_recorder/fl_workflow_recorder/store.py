"""SQLite sidecar store for workflow observer (#1321)."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

from . import RECORDER_VERSION, SCHEMA_VERSION

_SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY NOT NULL,
    started_at_wall_ns INTEGER NOT NULL,
    ended_at_wall_ns INTEGER,
    started_at_utc TEXT NOT NULL,
    ended_at_utc TEXT,
    status TEXT NOT NULL,
    close_reason TEXT,
    fl_version TEXT,
    midi_script_api_version TEXT,
    recorder_version TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    recovery_marker INTEGER NOT NULL DEFAULT 0,
    fl_pid INTEGER,
    active_duration_ns INTEGER NOT NULL DEFAULT 0,
    listening_duration_ns INTEGER NOT NULL DEFAULT 0,
    idle_duration_ns INTEGER NOT NULL DEFAULT 0,
    event_count INTEGER NOT NULL DEFAULT 0,
    fl_event_count INTEGER NOT NULL DEFAULT 0,
    win_event_count INTEGER NOT NULL DEFAULT 0,
    quality_json TEXT,
    created_at_wall_ns INTEGER NOT NULL,
    updated_at_wall_ns INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    source TEXT NOT NULL,
    source_seq INTEGER NOT NULL,
    t_wall_ns INTEGER NOT NULL,
    t_utc TEXT NOT NULL,
    t_mono_ns INTEGER,
    event_type TEXT NOT NULL,
    props_json TEXT NOT NULL,
    ingest_wall_ns INTEGER NOT NULL,
    UNIQUE(source, source_seq, t_wall_ns)
);

CREATE INDEX IF NOT EXISTS idx_events_session_wall
    ON events(session_id, t_wall_ns);
CREATE INDEX IF NOT EXISTS idx_events_type
    ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_sessions_status
    ON sessions(status);

CREATE TABLE IF NOT EXISTS ingest_cursors (
    spool_name TEXT PRIMARY KEY NOT NULL,
    byte_offset INTEGER NOT NULL,
    last_source_seq INTEGER,
    last_t_wall_ns INTEGER,
    updated_at_wall_ns INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS spool_quarantine (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spool_name TEXT NOT NULL,
    byte_offset INTEGER,
    raw_excerpt TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at_wall_ns INTEGER NOT NULL
);
"""


def _utc_from_wall_ns(wall_ns: int) -> str:
    sec = wall_ns // 1_000_000_000
    ms = (wall_ns % 1_000_000_000) // 1_000_000
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(sec)) + (".%03dZ" % ms)


class WorkflowStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self.db_path), timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(_SCHEMA_SQL)
            self._ensure_meta(conn)
            conn.commit()
            self._conn = conn
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _ensure_meta(self, conn: sqlite3.Connection) -> None:
        row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO meta(key, value) VALUES (?, ?)",
                ("schema_version", str(SCHEMA_VERSION)),
            )
            conn.execute(
                "INSERT INTO meta(key, value) VALUES (?, ?)",
                ("recorder_version", RECORDER_VERSION),
            )
            return
        if int(row["value"]) != SCHEMA_VERSION:
            raise RuntimeError(
                f"workflow.sqlite3 schema_version={row['value']} != {SCHEMA_VERSION}"
            )

    def schema_version(self) -> int:
        conn = self.connect()
        row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        return int(row["value"]) if row else 0

    def get_cursor(self, spool_name: str) -> int:
        conn = self.connect()
        row = conn.execute(
            "SELECT byte_offset FROM ingest_cursors WHERE spool_name = ?",
            (spool_name,),
        ).fetchone()
        return int(row["byte_offset"]) if row else 0

    def set_cursor(
        self,
        spool_name: str,
        byte_offset: int,
        last_source_seq: int | None = None,
        last_t_wall_ns: int | None = None,
    ) -> None:
        conn = self.connect()
        now = time.time_ns()
        conn.execute(
            """
            INSERT INTO ingest_cursors(
                spool_name, byte_offset, last_source_seq, last_t_wall_ns, updated_at_wall_ns
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(spool_name) DO UPDATE SET
                byte_offset = excluded.byte_offset,
                last_source_seq = excluded.last_source_seq,
                last_t_wall_ns = excluded.last_t_wall_ns,
                updated_at_wall_ns = excluded.updated_at_wall_ns
            """,
            (spool_name, int(byte_offset), last_source_seq, last_t_wall_ns, now),
        )
        conn.commit()

    def quarantine(
        self,
        spool_name: str,
        raw_excerpt: str,
        reason: str,
        byte_offset: int | None = None,
    ) -> None:
        conn = self.connect()
        conn.execute(
            """
            INSERT INTO spool_quarantine(
                spool_name, byte_offset, raw_excerpt, reason, created_at_wall_ns
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                spool_name,
                byte_offset,
                (raw_excerpt or "")[:2000],
                reason,
                time.time_ns(),
            ),
        )
        conn.commit()

    def insert_event(self, session_id: str, event: dict) -> bool:
        """Insert one sanitized event. Returns True if inserted, False if duplicate."""
        conn = self.connect()
        now = time.time_ns()
        props_json = json.dumps(
            event.get("props") or {},
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        t_utc = event.get("t_utc") or _utc_from_wall_ns(int(event["t_wall_ns"]))
        try:
            conn.execute(
                """
                INSERT INTO events(
                    session_id, source, source_seq, t_wall_ns, t_utc, t_mono_ns,
                    event_type, props_json, ingest_wall_ns
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    event["source"],
                    int(event["source_seq"]),
                    int(event["t_wall_ns"]),
                    t_utc,
                    event.get("t_mono_ns"),
                    event["event_type"],
                    props_json,
                    now,
                ),
            )
        except sqlite3.IntegrityError:
            return False
        src = event["source"]
        if src == "fl":
            conn.execute(
                """
                UPDATE sessions SET
                    event_count = event_count + 1,
                    fl_event_count = fl_event_count + 1,
                    updated_at_wall_ns = ?
                WHERE id = ?
                """,
                (now, session_id),
            )
        elif src == "win":
            conn.execute(
                """
                UPDATE sessions SET
                    event_count = event_count + 1,
                    win_event_count = win_event_count + 1,
                    updated_at_wall_ns = ?
                WHERE id = ?
                """,
                (now, session_id),
            )
        else:
            conn.execute(
                """
                UPDATE sessions SET
                    event_count = event_count + 1,
                    updated_at_wall_ns = ?
                WHERE id = ?
                """,
                (now, session_id),
            )
        conn.commit()
        return True

    def insert_events(self, session_id: str, events: Iterable[dict]) -> tuple[int, int]:
        inserted = 0
        duplicates = 0
        for ev in events:
            if self.insert_event(session_id, ev):
                inserted += 1
            else:
                duplicates += 1
        return inserted, duplicates

    def open_sessions(self) -> list[sqlite3.Row]:
        conn = self.connect()
        return list(
            conn.execute(
                "SELECT * FROM sessions WHERE status = 'open' ORDER BY started_at_wall_ns"
            )
        )

    def get_session(self, session_id: str) -> sqlite3.Row | None:
        conn = self.connect()
        return conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()

    def create_session(
        self,
        session_id: str,
        *,
        fl_version: str | None = None,
        midi_script_api_version: str | None = None,
        fl_pid: int | None = None,
        quality: dict | None = None,
        started_at_wall_ns: int | None = None,
    ) -> str:
        conn = self.connect()
        now = started_at_wall_ns if started_at_wall_ns is not None else time.time_ns()
        conn.execute(
            """
            INSERT INTO sessions(
                id, started_at_wall_ns, started_at_utc, status,
                fl_version, midi_script_api_version, recorder_version, schema_version,
                recovery_marker, fl_pid, quality_json,
                created_at_wall_ns, updated_at_wall_ns
            ) VALUES (?, ?, ?, 'open', ?, ?, ?, ?, 0, ?, ?, ?, ?)
            """,
            (
                session_id,
                now,
                _utc_from_wall_ns(now),
                fl_version,
                midi_script_api_version,
                RECORDER_VERSION,
                SCHEMA_VERSION,
                fl_pid,
                json.dumps(quality or {}, ensure_ascii=True, separators=(",", ":")),
                now,
                now,
            ),
        )
        conn.commit()
        return session_id

    def close_session(
        self,
        session_id: str,
        *,
        close_reason: str,
        status: str = "closed",
        ended_at_wall_ns: int | None = None,
        recovery_marker: int | None = None,
        durations: dict[str, int] | None = None,
    ) -> None:
        conn = self.connect()
        end = ended_at_wall_ns if ended_at_wall_ns is not None else time.time_ns()
        d = durations or {}
        fields = [
            "ended_at_wall_ns = ?",
            "ended_at_utc = ?",
            "status = ?",
            "close_reason = ?",
            "updated_at_wall_ns = ?",
        ]
        params: list[Any] = [end, _utc_from_wall_ns(end), status, close_reason, end]
        if recovery_marker is not None:
            fields.append("recovery_marker = ?")
            params.append(int(recovery_marker))
        for key, col in (
            ("active_duration_ns", "active_duration_ns"),
            ("listening_duration_ns", "listening_duration_ns"),
            ("idle_duration_ns", "idle_duration_ns"),
        ):
            if key in d:
                fields.append(f"{col} = ?")
                params.append(int(d[key]))
        params.append(session_id)
        conn.execute(
            f"UPDATE sessions SET {', '.join(fields)} WHERE id = ?",
            params,
        )
        conn.commit()

    def update_session_meta(
        self,
        session_id: str,
        *,
        fl_version: str | None = None,
        midi_script_api_version: str | None = None,
        fl_pid: int | None = None,
        quality: dict | None = None,
        durations: dict[str, int] | None = None,
    ) -> None:
        conn = self.connect()
        fields: list[str] = ["updated_at_wall_ns = ?"]
        params: list[Any] = [time.time_ns()]
        if fl_version is not None:
            fields.append("fl_version = ?")
            params.append(fl_version)
        if midi_script_api_version is not None:
            fields.append("midi_script_api_version = ?")
            params.append(str(midi_script_api_version))
        if fl_pid is not None:
            fields.append("fl_pid = ?")
            params.append(int(fl_pid))
        if quality is not None:
            fields.append("quality_json = ?")
            params.append(json.dumps(quality, ensure_ascii=True, separators=(",", ":")))
        if durations:
            for key in ("active_duration_ns", "listening_duration_ns", "idle_duration_ns"):
                if key in durations:
                    fields.append(f"{key} = ?")
                    params.append(int(durations[key]))
        params.append(session_id)
        conn.execute(f"UPDATE sessions SET {', '.join(fields)} WHERE id = ?", params)
        conn.commit()

    def last_event_wall_ns(self, session_id: str | None = None) -> int | None:
        conn = self.connect()
        if session_id:
            row = conn.execute(
                "SELECT MAX(t_wall_ns) AS m FROM events WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        else:
            row = conn.execute("SELECT MAX(t_wall_ns) AS m FROM events").fetchone()
        return int(row["m"]) if row and row["m"] is not None else None

    def prune_raw(self, *, older_than_wall_ns: int, keep_session_ids: Iterable[str]) -> dict[str, int]:
        """Delete closed-session events older than cutoff. Never touches keep_session_ids."""
        conn = self.connect()
        keep = set(keep_session_ids)
        # Find eligible closed sessions fully before cutoff.
        rows = conn.execute(
            """
            SELECT id FROM sessions
            WHERE status != 'open'
              AND ended_at_wall_ns IS NOT NULL
              AND ended_at_wall_ns < ?
            """,
            (older_than_wall_ns,),
        ).fetchall()
        deleted_events = 0
        deleted_sessions = 0
        for row in rows:
            sid = row["id"]
            if sid in keep:
                continue
            cur = conn.execute("DELETE FROM events WHERE session_id = ?", (sid,))
            deleted_events += cur.rowcount
            conn.execute("DELETE FROM sessions WHERE id = ?", (sid,))
            deleted_sessions += 1
        conn.commit()
        return {"deleted_events": deleted_events, "deleted_sessions": deleted_sessions}
