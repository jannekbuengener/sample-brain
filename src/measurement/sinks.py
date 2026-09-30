"""Measurement sinks — Null and Sidecar SQLite (ADR-0006)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional, Protocol

from .contract import MeasurementEvent, PrivacyClass


class MeasurementSink(Protocol):
    def write(self, event: MeasurementEvent) -> None: ...

    def flush(self) -> None: ...


class NullSink:
    def write(self, event: MeasurementEvent) -> None:
        return None

    def flush(self) -> None:
        return None


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    event_name TEXT NOT NULL,
    domain TEXT NOT NULL,
    privacy_class TEXT NOT NULL,
    run_id TEXT NOT NULL,
    session_id TEXT,
    payload_json TEXT NOT NULL
);
"""


class SidecarSqliteSink:
    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None
        # Create store eagerly so mode=local has a durable sidecar even before first valid write.
        self._ensure()

    def _ensure(self) -> sqlite3.Connection:
        if self._conn is None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.execute(_SCHEMA_SQL)
            self._conn.commit()
        return self._conn

    def write(self, event: MeasurementEvent) -> None:
        payload = event.to_dict()
        privacy = (
            event.privacy_class.value
            if isinstance(event.privacy_class, PrivacyClass)
            else str(event.privacy_class)
        )
        conn = self._ensure()
        conn.execute(
            """
            INSERT INTO events (
                occurred_at, event_name, domain, privacy_class,
                run_id, session_id, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.occurred_at,
                event.event_name,
                event.domain,
                privacy,
                event.run_id,
                event.session_id,
                json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False),
            ),
        )

    def flush(self) -> None:
        if self._conn is not None:
            self._conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
