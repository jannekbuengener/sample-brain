"""CLI: python -m fl_workflow_analyzer analyze|status"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PKG_PARENT = Path(__file__).resolve().parents[1]
if str(_PKG_PARENT) not in sys.path:
    sys.path.insert(0, str(_PKG_PARENT))


def _default_db() -> Path:
    # Reuse recorder path helper without importing product code.
    recorder_parent = Path(__file__).resolve().parents[2] / "fl_workflow_recorder"
    if str(recorder_parent) not in sys.path:
        sys.path.insert(0, str(recorder_parent))
    from fl_workflow_recorder.paths import ObserverPaths

    return ObserverPaths().db


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="FL Workflow deterministic reconstruction analyzer (#1322)"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_an = sub.add_parser("analyze", help="Reprocess raw sessions into derived evidence")
    p_an.add_argument("--db", type=Path, default=None, help="Path to workflow.sqlite3")
    p_an.add_argument("--root", type=Path, default=None, help="Observer root (uses workflow.sqlite3)")
    p_an.add_argument("--session", action="append", default=None, help="Limit to session id (repeatable)")
    p_an.add_argument("--include-open", action="store_true", help="Also analyze open sessions")
    p_an.add_argument(
        "--clear-previous",
        action="store_true",
        help="Delete prior derived runs before writing a new one (raw untouched)",
    )

    p_st = sub.add_parser("status", help="Show latest analysis_run summary")
    p_st.add_argument("--db", type=Path, default=None)
    p_st.add_argument("--root", type=Path, default=None)

    args = parser.parse_args(argv)

    def resolve_db() -> Path:
        if args.db:
            return Path(args.db)
        if getattr(args, "root", None):
            return Path(args.root) / "workflow.sqlite3"
        return _default_db()

    if args.cmd == "analyze":
        from .pipeline import run_analysis

        db = resolve_db()
        if not db.exists():
            print(json.dumps({"ok": False, "error": "db_missing", "path_hint": "local workflow.sqlite3"}))
            return 1
        result = run_analysis(
            db,
            session_ids=args.session,
            include_open=args.include_open,
            clear_previous=args.clear_previous,
        )
        # Sanitize: never print raw event payloads.
        safe = {
            "ok": True,
            "run_id": result["run_id"],
            "status": result["status"],
            "analyzer_version": result["analyzer_version"],
            "rule_version": result["rule_version"],
            "sessions_analyzed": result["sessions_analyzed"],
            "sessions": [
                {
                    "session_id": s["session_id"],
                    "events_normalized": s["events_normalized"],
                    "action_count": s["action_count"],
                    "segment_count": s["segment_count"],
                    "transition_count": s["transition_count"],
                    "path_count": s["path_count"],
                    "loop_count": s["loop_count"],
                    "coverage": {
                        k: s["coverage"][k]
                        for k in (
                            "active_ns",
                            "listening_ns",
                            "idle_ns",
                            "high_confidence_active_ns",
                            "medium_confidence_active_ns",
                            "low_confidence_active_ns",
                            "unknown_active_ns",
                        )
                        if k in s["coverage"]
                    },
                }
                for s in result["sessions"]
            ],
            "exit": result.get("exit"),
        }
        print(json.dumps(safe, indent=2))
        return 0

    if args.cmd == "status":
        import sqlite3

        db = resolve_db()
        if not db.exists():
            print(json.dumps({"ok": False, "error": "db_missing"}))
            return 1
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT id, analyzer_version, rule_version, status, summary_json, "
                "started_at_wall_ns, finished_at_wall_ns FROM analysis_runs "
                "ORDER BY started_at_wall_ns DESC LIMIT 1"
            ).fetchone()
        except sqlite3.OperationalError:
            print(json.dumps({"ok": False, "error": "no_derived_schema"}))
            return 1
        finally:
            conn.close()
        if not row:
            print(json.dumps({"ok": False, "error": "no_runs"}))
            return 1
        summary = {}
        if row["summary_json"]:
            try:
                summary = json.loads(row["summary_json"])
            except json.JSONDecodeError:
                summary = {}
        print(
            json.dumps(
                {
                    "ok": True,
                    "run_id": row["id"],
                    "analyzer_version": row["analyzer_version"],
                    "rule_version": row["rule_version"],
                    "status": row["status"],
                    "sessions_analyzed": summary.get("sessions_analyzed"),
                    "exit": summary.get("exit"),
                },
                indent=2,
            )
        )
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
