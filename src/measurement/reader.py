"""Read-only Measurement sidecar access (ADR-0006 Local Report v1)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from .contract import MeasurementEvent, PrivacyClass, validate_event


class ReadStatus(str, Enum):
    OK = "ok"
    NO_DATA = "no_data"
    MISSING_DB = "missing_db"
    ERROR = "error"


TARGET_EVENT_NAME = "pipeline.stage_finished"


@dataclass(frozen=True)
class ReadCounters:
    rows_seen: int = 0
    valid: int = 0
    invalid: int = 0
    skipped_unknown: int = 0


def event_from_payload(payload: dict[str, Any]) -> Optional[MeasurementEvent]:
    try:
        privacy_raw = payload.get("privacy_class", PrivacyClass.EXPORT_SAFE)
        try:
            privacy = PrivacyClass(str(privacy_raw))
        except ValueError:
            privacy = privacy_raw
        event = MeasurementEvent(
            document_type=str(payload.get("document_type", "")),
            schema_version=str(payload.get("schema_version", "")),
            event_name=str(payload.get("event_name", "")),
            event_version=int(payload["event_version"]),
            occurred_at=str(payload.get("occurred_at", "")),
            run_id=str(payload.get("run_id", "")),
            session_id=payload.get("session_id"),
            domain=str(payload.get("domain", "")),
            privacy_class=privacy,
            status=str(payload.get("status", "")),
            reason_code=payload.get("reason_code"),
            app=payload.get("app") or {},
            props=payload.get("props") or {},
        )
        return validate_event(event)
    except Exception:
        return None


class MeasurementReader:
    """Open the sidecar read-only and yield validated contract events."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)

    def open_connection(self) -> sqlite3.Connection:
        # URI form forces read-only; prevents accidental writes from the report path.
        uri = f"file:{quote(str(self.db_path.resolve()).replace(chr(92), '/'))}?mode=ro"
        return sqlite3.connect(uri, uri=True)

    def iter_stage_finished(self) -> tuple[list[MeasurementEvent], ReadCounters, ReadStatus]:
        if not self.db_path.is_file():
            return [], ReadCounters(), ReadStatus.MISSING_DB
        try:
            conn = self.open_connection()
        except sqlite3.Error:
            return [], ReadCounters(), ReadStatus.ERROR
        try:
            try:
                rows = conn.execute(
                    """
                    SELECT event_name, payload_json
                    FROM events
                    ORDER BY id ASC
                    """
                ).fetchall()
            except sqlite3.Error:
                return [], ReadCounters(), ReadStatus.ERROR
        finally:
            conn.close()

        events: list[MeasurementEvent] = []
        rows_seen = 0
        invalid = 0
        skipped_unknown = 0
        for event_name, payload_json in rows:
            rows_seen += 1
            if event_name != TARGET_EVENT_NAME:
                skipped_unknown += 1
                continue
            try:
                payload = json.loads(payload_json)
            except (TypeError, json.JSONDecodeError):
                invalid += 1
                continue
            if not isinstance(payload, dict):
                invalid += 1
                continue
            event = event_from_payload(payload)
            if event is None:
                invalid += 1
                continue
            events.append(event)

        counters = ReadCounters(
            rows_seen=rows_seen,
            valid=len(events),
            invalid=invalid,
            skipped_unknown=skipped_unknown,
        )
        if not events:
            return [], counters, ReadStatus.NO_DATA
        return events, counters, ReadStatus.OK
