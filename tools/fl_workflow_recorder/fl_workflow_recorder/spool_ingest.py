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
                    text,
                    "malformed_json",
                    byte_offset=offset,
                )
                result.quarantined += 1
                continue
            event = sanitize_event(obj)
            if event is None:
                self.store.quarantine(
                    spool_name,
                    text[:500],
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

        if rotate_after_commit and new_offset > rotate_keep_bytes and not result.partial_tail:
            self._compact_spool(spool_path, spool_name, keep_from=new_offset)

        return result

    def _compact_spool(self, spool_path: Path, spool_name: str, *, keep_from: int) -> None:
        """Drop already-committed prefix. Never delete before cursor commit."""
        try:
            size = spool_path.stat().st_size
            if keep_from <= 0 or keep_from >= size:
                if keep_from >= size and size > 0:
                    spool_path.write_bytes(b"")
                    self.store.set_cursor(spool_name, 0)
                return
            with spool_path.open("rb") as fh:
                fh.seek(keep_from)
                remainder = fh.read()
            spool_path.write_bytes(remainder)
            self.store.set_cursor(spool_name, 0)
        except OSError:
            # Fail-soft: leave spool as-is; cursor already committed.
            return
