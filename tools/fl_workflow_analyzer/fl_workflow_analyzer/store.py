"""Derived-schema persistence. Raw recorder tables remain immutable."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from . import ANALYZER_VERSION, DERIVED_SCHEMA_VERSION, RULE_VERSION
from .rules import rule_manifest

_DERIVED_SQL = """
CREATE TABLE IF NOT EXISTS analysis_runs (
    id TEXT PRIMARY KEY NOT NULL,
    analyzer_version TEXT NOT NULL,
    rule_version INTEGER NOT NULL,
    derived_schema_version INTEGER NOT NULL,
    started_at_wall_ns INTEGER NOT NULL,
    finished_at_wall_ns INTEGER,
    source_fingerprint TEXT NOT NULL,
    session_filter_json TEXT NOT NULL,
    status TEXT NOT NULL,
    rule_manifest_json TEXT NOT NULL,
    summary_json TEXT
);

CREATE TABLE IF NOT EXISTS derived_actions (
    run_id TEXT NOT NULL REFERENCES analysis_runs(id),
    session_id TEXT NOT NULL,
    action_id TEXT NOT NULL,
    start_wall_ns INTEGER NOT NULL,
    end_wall_ns INTEGER NOT NULL,
    action_type TEXT NOT NULL,
    surface TEXT,
    truth_level TEXT NOT NULL,
    confidence TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    PRIMARY KEY (run_id, session_id, action_id)
);

CREATE TABLE IF NOT EXISTS derived_segments (
    run_id TEXT NOT NULL REFERENCES analysis_runs(id),
    session_id TEXT NOT NULL,
    segment_id TEXT NOT NULL,
    start_wall_ns INTEGER NOT NULL,
    end_wall_ns INTEGER NOT NULL,
    activity TEXT NOT NULL,
    truth_level TEXT NOT NULL,
    confidence TEXT NOT NULL,
    surface TEXT,
    duration_ns INTEGER NOT NULL,
    evidence_json TEXT NOT NULL,
    PRIMARY KEY (run_id, session_id, segment_id)
);

CREATE TABLE IF NOT EXISTS derived_transitions (
    run_id TEXT NOT NULL REFERENCES analysis_runs(id),
    session_id TEXT NOT NULL,
    from_activity TEXT NOT NULL,
    to_activity TEXT NOT NULL,
    count INTEGER NOT NULL,
    total_duration_ns INTEGER NOT NULL,
    median_duration_ns INTEGER NOT NULL,
    PRIMARY KEY (run_id, session_id, from_activity, to_activity)
);

CREATE TABLE IF NOT EXISTS derived_path_counts (
    run_id TEXT NOT NULL REFERENCES analysis_runs(id),
    session_id TEXT NOT NULL,
    n INTEGER NOT NULL,
    path_json TEXT NOT NULL,
    count INTEGER NOT NULL,
    relative_frequency REAL NOT NULL,
    median_duration_ns INTEGER NOT NULL,
    PRIMARY KEY (run_id, session_id, n, path_json)
);

CREATE TABLE IF NOT EXISTS derived_loops (
    run_id TEXT NOT NULL REFERENCES analysis_runs(id),
    session_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    pattern_json TEXT NOT NULL,
    repeats INTEGER NOT NULL,
    duration_ns INTEGER NOT NULL,
    confidence TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    PRIMARY KEY (run_id, session_id, idx)
);

CREATE TABLE IF NOT EXISTS derived_metrics (
    run_id TEXT NOT NULL REFERENCES analysis_runs(id),
    session_id TEXT NOT NULL,
    metric_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (run_id, session_id, metric_type)
);

CREATE INDEX IF NOT EXISTS idx_derived_segments_run
    ON derived_segments(run_id, activity);
CREATE INDEX IF NOT EXISTS idx_derived_actions_run
    ON derived_actions(run_id, action_type);
"""


def _j(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


class DerivedStore:
    """Opens the same workflow.sqlite3 and adds derived tables beside raw ones."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            if not self.db_path.exists():
                raise FileNotFoundError(f"workflow db missing: {self.db_path}")
            conn = sqlite3.connect(str(self.db_path), timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executescript(_DERIVED_SQL)
            conn.commit()
            self._conn = conn
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def source_fingerprint(self, session_ids: list[str] | None = None) -> str:
        conn = self.connect()
        if session_ids:
            placeholders = ",".join("?" * len(session_ids))
            rows = conn.execute(
                f"""
                SELECT id, event_count, started_at_wall_ns, ended_at_wall_ns, status
                FROM sessions WHERE id IN ({placeholders}) ORDER BY id
                """,
                session_ids,
            ).fetchall()
            # Do not SUM(t_wall_ns): wall-ns values are ~1e18 and overflow SQLite INTEGER.
            ev = conn.execute(
                f"""
                SELECT COUNT(*) AS c,
                       COALESCE(MIN(t_wall_ns),0) AS tmin,
                       COALESCE(MAX(t_wall_ns),0) AS tmax,
                       COALESCE(MAX(id),0) AS max_id
                FROM events WHERE session_id IN ({placeholders})
                """,
                session_ids,
            ).fetchone()
        else:
            rows = conn.execute(
                "SELECT id, event_count, started_at_wall_ns, ended_at_wall_ns, status "
                "FROM sessions ORDER BY id"
            ).fetchall()
            ev = conn.execute(
                """
                SELECT COUNT(*) AS c,
                       COALESCE(MIN(t_wall_ns),0) AS tmin,
                       COALESCE(MAX(t_wall_ns),0) AS tmax,
                       COALESCE(MAX(id),0) AS max_id
                FROM events
                """
            ).fetchone()
        payload = {
            "sessions": [dict(r) for r in rows],
            "event_count": int(ev["c"]),
            "event_wall_min": int(ev["tmin"]),
            "event_wall_max": int(ev["tmax"]),
            "event_max_id": int(ev["max_id"]),
            "analyzer": ANALYZER_VERSION,
            "rule": RULE_VERSION,
        }
        return _j(payload)

    def begin_run(self, *, session_ids: list[str] | None = None) -> str:
        conn = self.connect()
        run_id = str(uuid.uuid4())
        now = time.time_ns()
        fp = self.source_fingerprint(session_ids)
        conn.execute(
            """
            INSERT INTO analysis_runs(
                id, analyzer_version, rule_version, derived_schema_version,
                started_at_wall_ns, source_fingerprint, session_filter_json,
                status, rule_manifest_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'running', ?)
            """,
            (
                run_id,
                ANALYZER_VERSION,
                RULE_VERSION,
                DERIVED_SCHEMA_VERSION,
                now,
                fp,
                _j(session_ids or []),
                _j(rule_manifest()),
            ),
        )
        conn.commit()
        return run_id

    def finish_run(self, run_id: str, *, status: str, summary: dict) -> None:
        conn = self.connect()
        conn.execute(
            """
            UPDATE analysis_runs SET
                finished_at_wall_ns = ?,
                status = ?,
                summary_json = ?
            WHERE id = ?
            """,
            (time.time_ns(), status, _j(summary), run_id),
        )
        conn.commit()

    def delete_run(self, run_id: str) -> None:
        conn = self.connect()
        for table in (
            "derived_actions",
            "derived_segments",
            "derived_transitions",
            "derived_path_counts",
            "derived_loops",
            "derived_metrics",
        ):
            conn.execute(f"DELETE FROM {table} WHERE run_id = ?", (run_id,))
        conn.execute("DELETE FROM analysis_runs WHERE id = ?", (run_id,))
        conn.commit()

    def clear_derived(self) -> None:
        """Drop all derived rows (raw untouched). Used for full reprocess."""
        conn = self.connect()
        runs = [r["id"] for r in conn.execute("SELECT id FROM analysis_runs")]
        for rid in runs:
            self.delete_run(rid)

    def load_raw_events(self, session_id: str) -> list[sqlite3.Row]:
        conn = self.connect()
        return list(
            conn.execute(
                """
                SELECT id, session_id, source, source_seq, t_wall_ns, t_utc,
                       t_mono_ns, event_type, props_json
                FROM events
                WHERE session_id = ?
                ORDER BY t_wall_ns, source, source_seq, id
                """,
                (session_id,),
            )
        )

    def list_sessions(self, *, include_open: bool = False) -> list[sqlite3.Row]:
        conn = self.connect()
        if include_open:
            return list(conn.execute("SELECT * FROM sessions ORDER BY started_at_wall_ns"))
        return list(
            conn.execute(
                "SELECT * FROM sessions WHERE status != 'open' ORDER BY started_at_wall_ns"
            )
        )

    def persist_session_result(
        self,
        run_id: str,
        session_id: str,
        *,
        actions: list[dict],
        segments: list[dict],
        transitions: list[dict],
        paths: list[dict],
        loops: list[dict],
        metrics: dict[str, Any],
    ) -> None:
        conn = self.connect()
        for a in actions:
            conn.execute(
                """
                INSERT INTO derived_actions(
                    run_id, session_id, action_id, start_wall_ns, end_wall_ns,
                    action_type, surface, truth_level, confidence, evidence_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    session_id,
                    a["action_id"],
                    a["start_wall_ns"],
                    a["end_wall_ns"],
                    a["action_type"],
                    a.get("surface"),
                    a["truth_level"],
                    a["confidence"],
                    _j(
                        {
                            "evidence_event_ids": a.get("evidence_event_ids"),
                            "evidence_types": a.get("evidence_types"),
                            "reasons": a.get("reasons"),
                            "props": a.get("props"),
                        }
                    ),
                ),
            )
        for s in segments:
            conn.execute(
                """
                INSERT INTO derived_segments(
                    run_id, session_id, segment_id, start_wall_ns, end_wall_ns,
                    activity, truth_level, confidence, surface, duration_ns, evidence_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    session_id,
                    s["segment_id"],
                    s["start_wall_ns"],
                    s["end_wall_ns"],
                    s["activity"],
                    s["truth_level"],
                    s["confidence"],
                    s.get("surface"),
                    s.get("duration_ns", max(0, s["end_wall_ns"] - s["start_wall_ns"])),
                    _j(
                        {
                            "action_ids": s.get("action_ids"),
                            "reasons": s.get("reasons"),
                            "props": s.get("props"),
                        }
                    ),
                ),
            )
        for t in transitions:
            conn.execute(
                """
                INSERT INTO derived_transitions(
                    run_id, session_id, from_activity, to_activity,
                    count, total_duration_ns, median_duration_ns
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    session_id,
                    t["from_activity"],
                    t["to_activity"],
                    t["count"],
                    t["total_duration_ns"],
                    t["median_duration_ns"],
                ),
            )
        for p in paths:
            conn.execute(
                """
                INSERT INTO derived_path_counts(
                    run_id, session_id, n, path_json, count,
                    relative_frequency, median_duration_ns
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    session_id,
                    p["n"],
                    _j(p["path"]),
                    p["count"],
                    p["relative_frequency"],
                    p["median_duration_ns"],
                ),
            )
        for idx, loop in enumerate(loops):
            conn.execute(
                """
                INSERT INTO derived_loops(
                    run_id, session_id, idx, pattern_json, repeats,
                    duration_ns, confidence, evidence_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    session_id,
                    idx,
                    _j(loop["pattern"]),
                    loop["repeats"],
                    loop["duration_ns"],
                    loop["confidence"],
                    _j(loop),
                ),
            )
        for mtype, payload in metrics.items():
            conn.execute(
                """
                INSERT INTO derived_metrics(run_id, session_id, metric_type, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (run_id, session_id, mtype, _j(payload)),
            )
        conn.commit()
