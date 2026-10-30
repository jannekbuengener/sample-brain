"""Crash-safe incremental JSONL spool ingest."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .privacy import sanitize_event
from .store import WorkflowStore


@dataclass
class IngestResult:
    inserted: int = 0
    duplicates: int = 0
    quarantined: int = 0
    bytes_advanced: int = 0
    partial_tail: bool = False
    events: list[dict] = field(default_factory=list)


def _read_complete_lines(data: bytes) -> tuple[list[bytes], bytes]:
    """Split into complete newline-terminated lines + optional incomplete tail."""
    if not data:
        return [], b""
    parts = data.split(b"\n")
    if data.endswith(b"\n"):
        # Last split element is empty after trailing newline.
        complete = parts[:-1]
        return complete, b""
    complete = parts[:-1]
    tail = parts[-1]
    return complete, tail


class SpoolIngestor:
    def __init__(self, store: WorkflowStore) -> None:
        self.store = store

    def ingest_file(
        self,
        spool_path: Path,
        *,
        spool_name: str,
        session_id: str | None,
        rotate_after_commit: bool = False,
        rotate_keep_bytes: int = 0,
        on_event: Callable[[dict], None] | None = None,
    ) -> IngestResult:
        result = IngestResult()
        if session_id is None:
            return result
        if not spool_path.exists():
            return result

        offset = self.store.get_cursor(spool_name)
        size = spool_path.stat().st_size
        if offset > size:
            # File rotated/truncated under us — reset cursor fail-soft.
            offset = 0
            self.store.set_cursor(spool_name, 0)

        with spool_path.open("rb") as fh:
            fh.seek(offset)
            chunk = fh.read()
            new_offset = offset + len(chunk)

        lines, tail = _read_complete_lines(chunk)
        if tail:
            result.partial_tail = True
            # Do not advance past incomplete final line.
            new_offset = offset + len(chunk) - len(tail)

        last_seq = None
        last_wall = None
        for raw_line in lines:
            if not raw_line.strip():
                continue
            text = raw_line.decode("utf-8", errors="replace")
            try:
                obj = json.loads(text)
            except json.JSONDecodeError:
                self.store.quarantine(
                    spool_name,
                    _safe_quarantine_excerpt(text),
                    "malformed_json",
                    byte_offset=offset,
                )
                result.quarantined += 1
                continue
            event = sanitize_event(obj)
            if event is None:
                self.store.quarantine(
                    spool_name,
                    _safe_quarantine_excerpt(text),
                    "rejected_privacy_or_schema",
                    byte_offset=offset,
                )
                result.quarantined += 1
                continue
            if self.store.insert_event(session_id, event):
                result.inserted += 1
                result.events.append(event)
                if on_event is not None:
                    try:
                        on_event(event)
                    except Exception:
                        pass
            else:
                result.duplicates += 1
            last_seq = event["source_seq"]
            last_wall = event["t_wall_ns"]

        self.store.set_cursor(
            spool_name,
            new_offset,
            last_source_seq=last_seq,
            last_t_wall_ns=last_wall,
        )
        result.bytes_advanced = max(0, new_offset - offset)

        # Active spool compaction against concurrent FL/Windows writers is unsafe
        # (appends between size-check and truncate can be lost). V1 keeps spools
        # append-only; disk growth is bounded by retention + optional offline compact.
        _ = (rotate_after_commit, rotate_keep_bytes)

        return result


def _safe_quarantine_excerpt(text: str) -> str:
    """Never persist raw rejected payloads that may contain secrets/paths."""
    raw = text or ""
    return (
        "len=%d sha_prefix=%s redacted=true"
        % (len(raw), ("%08x" % (abs(hash(raw)) & 0xFFFFFFFF)))
    )
