"""Offline analysis orchestration — idempotent / reprocessable."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import ANALYZER_VERSION, RULE_VERSION
from .correlate import correlate_actions
from .derive import (
    bottleneck_candidates,
    coverage_metrics,
    churn_metrics,
    detect_backtracks,
    detect_loops,
    edit_arrangement_evidence,
    hot_paths,
    transition_matrix,
    undo_metrics,
)
from .normalize import normalize_events
from .rules import BLIND_SPOTS, rule_manifest
from .segment import build_segments
from .store import DerivedStore


def analyze_session(
    store: DerivedStore,
    session_row: Any,
) -> dict[str, Any]:
    """Analyze one session in memory; caller persists."""
    sid = str(session_row["id"])
    rows = store.load_raw_events(sid)
    events = normalize_events(rows)
    actions = correlate_actions(events)

    start_ns = int(session_row["started_at_wall_ns"])
    end_ns = session_row["ended_at_wall_ns"]
    if end_ns is None:
        end_ns = store.connect().execute(
            "SELECT COALESCE(MAX(t_wall_ns), ?) FROM events WHERE session_id = ?",
            (start_ns, sid),
        ).fetchone()[0]
    end_ns = int(end_ns or start_ns)

    segments = build_segments(
        actions,
        events,
        session_id=sid,
        session_start_ns=start_ns,
        session_end_ns=end_ns,
    )
    transitions = transition_matrix(segments)
    paths = hot_paths(segments, session_id=sid)
    loops = detect_loops(segments, session_id=sid)
    backtracks = detect_backtracks(segments, session_id=sid)
    churn = churn_metrics(segments, session_id=sid)
    undo = undo_metrics(actions, segments, session_id=sid)
    bottlenecks = bottleneck_candidates(segments, session_id=sid)
    ea = edit_arrangement_evidence(segments, session_id=sid)
    coverage = coverage_metrics(segments, actions, session_id=sid)

    quality = {}
    if session_row["quality_json"]:
        import json

        try:
            quality = json.loads(session_row["quality_json"])
        except Exception:
            quality = {}
    recovered = bool(session_row["recovery_marker"])

    metrics = {
        "coverage": coverage,
        "churn": churn,
        "undo": undo,
        "bottlenecks": bottlenecks,
        "backtracks": backtracks,
        "edit_arrangement": ea,
        "blind_spots": list(BLIND_SPOTS),
        "session_quality": {
            "status": session_row["status"],
            "close_reason": session_row["close_reason"],
            "recovery_marker": recovered,
            "completeness": "reduced" if recovered else "normal",
            "raw_quality": quality,
        },
    }

    return {
        "session_id": sid,
        "events_normalized": len(events),
        "actions": [a.to_dict() for a in actions],
        "segments": [s.to_dict() for s in segments],
        "transitions": transitions,
        "paths": paths,
        "loops": loops,
        "metrics": metrics,
    }


def run_analysis(
    db_path: Path,
    *,
    session_ids: list[str] | None = None,
    include_open: bool = False,
    clear_previous: bool = False,
) -> dict[str, Any]:
    """Run a full offline analysis. Raw events are never mutated."""
    store = DerivedStore(db_path)
    try:
        if clear_previous:
            store.clear_derived()
        sessions = store.list_sessions(include_open=include_open)
        if session_ids is not None:
            wanted = set(session_ids)
            sessions = [s for s in sessions if s["id"] in wanted]

        run_id = store.begin_run(session_ids=[s["id"] for s in sessions])
        session_summaries = []
        try:
            for sess in sessions:
                result = analyze_session(store, sess)
                store.persist_session_result(
                    run_id,
                    result["session_id"],
                    actions=result["actions"],
                    segments=result["segments"],
                    transitions=result["transitions"],
                    paths=result["paths"],
                    loops=result["loops"],
                    metrics=result["metrics"],
                )
                session_summaries.append(
                    {
                        "session_id": result["session_id"],
                        "events_normalized": result["events_normalized"],
                        "action_count": len(result["actions"]),
                        "segment_count": len(result["segments"]),
                        "transition_count": len(result["transitions"]),
                        "path_count": len(result["paths"]),
                        "loop_count": len(result["loops"]),
                        "coverage": result["metrics"]["coverage"],
                    }
                )
            summary = {
                "analyzer_version": ANALYZER_VERSION,
                "rule_version": RULE_VERSION,
                "sessions_analyzed": len(session_summaries),
                "sessions": session_summaries,
                "rule_manifest": rule_manifest(),
                "exit": "FL_WORKFLOW_RECONSTRUCTION_READY",
            }
            store.finish_run(run_id, status="ok", summary=summary)
            return {"run_id": run_id, "status": "ok", **summary}
        except Exception as exc:
            store.finish_run(
                run_id,
                status="error",
                summary={"error": type(exc).__name__, "message": str(exc)[:500]},
            )
            raise
    finally:
        store.close()


def analyze_events_in_memory(
    raw_events: list[dict],
    *,
    session_id: str = "synthetic",
    session_start_ns: int | None = None,
    session_end_ns: int | None = None,
) -> dict[str, Any]:
    """Golden-test helper: analyze a synthetic event list without SQLite raw tables.

    Each raw event dict needs: id, session_id, source, source_seq, t_wall_ns,
    t_utc, event_type, props_json (str or dict).
    """
    import json

    class _Row(dict):
        def __getitem__(self, key):  # type: ignore[override]
            return dict.__getitem__(self, key)

        def keys(self):
            return dict.keys(self)

        def get(self, key, default=None):
            return dict.get(self, key, default)

    rows = []
    for i, ev in enumerate(raw_events, start=1):
        props = ev.get("props") or ev.get("props_json") or {}
        if isinstance(props, dict):
            props_json = json.dumps(props, sort_keys=True)
        else:
            props_json = str(props)
        rows.append(
            _Row(
                {
                    "id": int(ev.get("id", i)),
                    "session_id": ev.get("session_id", session_id),
                    "source": ev["source"],
                    "source_seq": int(ev.get("source_seq", i)),
                    "t_wall_ns": int(ev["t_wall_ns"]),
                    "t_utc": ev.get("t_utc", ""),
                    "t_mono_ns": ev.get("t_mono_ns"),
                    "event_type": ev["event_type"],
                    "props_json": props_json,
                }
            )
        )
    events = normalize_events(rows)
    actions = correlate_actions(events)
    t0 = session_start_ns if session_start_ns is not None else (
        events[0].t_wall_ns if events else 0
    )
    t1 = session_end_ns if session_end_ns is not None else (
        events[-1].t_wall_ns if events else t0
    )
    segments = build_segments(
        actions, events, session_id=session_id, session_start_ns=t0, session_end_ns=t1
    )
    return {
        "events": [e.to_dict() for e in events],
        "actions": [a.to_dict() for a in actions],
        "segments": [s.to_dict() for s in segments],
        "transitions": transition_matrix(segments),
        "paths": hot_paths(segments, session_id=session_id),
        "loops": detect_loops(segments, session_id=session_id),
        "backtracks": detect_backtracks(segments, session_id=session_id),
        "churn": churn_metrics(segments, session_id=session_id),
        "undo": undo_metrics(actions, segments, session_id=session_id),
        "bottlenecks": bottleneck_candidates(segments, session_id=session_id),
        "edit_arrangement": edit_arrangement_evidence(segments, session_id=session_id),
        "coverage": coverage_metrics(segments, actions, session_id=session_id),
        "blind_spots": list(BLIND_SPOTS),
        "analyzer_version": ANALYZER_VERSION,
        "rule_version": RULE_VERSION,
    }
