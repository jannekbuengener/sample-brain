"""Bounded raw retention for workflow observer sidecar."""

from __future__ import annotations

import time

from .store import WorkflowStore

DEFAULT_RAW_RETENTION_DAYS = 90


def retention_cutoff_wall_ns(days: int = DEFAULT_RAW_RETENTION_DAYS, *, now: int | None = None) -> int:
    now_ns = now if now is not None else time.time_ns()
    return now_ns - int(days) * 24 * 60 * 60 * 1_000_000_000


def apply_retention(
    store: WorkflowStore,
    *,
    days: int = DEFAULT_RAW_RETENTION_DAYS,
    keep_session_ids: list[str] | None = None,
) -> dict[str, int]:
    keep = list(keep_session_ids or [])
    for row in store.open_sessions():
        keep.append(row["id"])
    cutoff = retention_cutoff_wall_ns(days)
    return store.prune_raw(older_than_wall_ns=cutoff, keep_session_ids=keep)
