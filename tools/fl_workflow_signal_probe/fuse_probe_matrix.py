"""
Offline fusion for #1320 probe JSONL files.

Joins fl-events.jsonl + windows-events.jsonl by integer t_wall_ns.
Computes cross-process clock-marker skew. Emits a markdown/json matrix scaffold.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
from pathlib import Path


def _load_jsonl(path: Path) -> list[dict]:
    events = []
    if not path.exists():
        return events
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                events.append(
                    {
                        "schema": "sb.fl_workflow_signal_probe.v1",
                        "seq": -line_no,
                        "t_wall_ns": 0,
                        "source": "unknown",
                        "type": "PARSE_ERROR",
                        "props": {"line": line_no},
                    }
                )
                continue
            events.append(evt)
    return events


def _skew(fl_events: list[dict], win_events: list[dict]) -> dict:
    fl_marks = [e for e in fl_events if e.get("type") == "CLOCK_MARKER"]
    win_marks = [e for e in win_events if e.get("type") == "CLOCK_MARKER"]
    deltas = []
    # Pair each win marker with nearest fl marker by t_wall_ns.
    for w in win_marks:
        wt = w.get("t_wall_ns") or 0
        if not fl_marks:
            break
        nearest = min(fl_marks, key=lambda f: abs((f.get("t_wall_ns") or 0) - wt))
        deltas.append((w.get("t_wall_ns") or 0) - (nearest.get("t_wall_ns") or 0))
    if not deltas:
        return {
            "pairs": 0,
            "note": "no CLOCK_MARKER pairs available",
        }
    abs_ms = [abs(d) / 1_000_000.0 for d in deltas]
    return {
        "pairs": len(deltas),
        "delta_ns_samples": deltas[:20],
        "abs_ms_min": round(min(abs_ms), 3),
        "abs_ms_p50": round(statistics.median(abs_ms), 3),
        "abs_ms_max": round(max(abs_ms), 3),
        "signed_ms_mean": round((sum(deltas) / len(deltas)) / 1_000_000.0, 3),
    }


def _type_counts(events: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for e in events:
        t = str(e.get("type"))
        out[t] = out.get(t, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))


def fuse(spool: Path) -> dict:
    fl_path = spool / "fl-events.jsonl"
    win_path = spool / "windows-events.jsonl"
    meta_path = spool / "probe-meta.json"
    fl_events = _load_jsonl(fl_path)
    win_events = _load_jsonl(win_path)
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            meta = {"parse_error": True}

    merged = sorted(
        fl_events + win_events,
        key=lambda e: (
            e.get("t_wall_ns") if e.get("t_wall_ns") is not None else 0,
            0 if e.get("source") == "fl" else 1,
            e.get("seq") or 0,
        ),
    )
    report = {
        "schema": "sb.fl_workflow_signal_probe.fusion.v1",
        "FL_VERSION": meta.get("FL_VERSION"),
        "MIDI_SCRIPT_API_VERSION": meta.get("MIDI_SCRIPT_API_VERSION"),
        "fl_event_count": len(fl_events),
        "win_event_count": len(win_events),
        "merged_count": len(merged),
        "fl_type_counts": _type_counts(fl_events),
        "win_type_counts": _type_counts(win_events),
        "clock_skew": _skew(fl_events, win_events),
        "merged_preview": merged[:40],
    }
    out_json = spool / "fusion-report.json"
    out_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    # Human markdown scaffold for issue evidence (sanitized by caller).
    md_lines = [
        "# #1320 Probe Fusion Report",
        "",
        f"- FL_VERSION: `{report['FL_VERSION']}`",
        f"- MIDI_SCRIPT_API_VERSION: `{report['MIDI_SCRIPT_API_VERSION']}`",
        f"- fl_events: {report['fl_event_count']}",
        f"- windows_events: {report['win_event_count']}",
        f"- clock_skew: {json.dumps(report['clock_skew'])}",
        "",
        "## FL type counts",
        "",
        "```json",
        json.dumps(report["fl_type_counts"], indent=2),
        "```",
        "",
        "## Windows type counts",
        "",
        "```json",
        json.dumps(report["win_type_counts"], indent=2),
        "```",
        "",
        "## Matrix scaffold",
        "",
        "| ACTION | EXPECTED | ACTUAL FL | ACTUAL WIN | ORDERING | RELIABILITY | OVERHEAD | V1 USE? | NOTES |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    (spool / "fusion-report.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--spool",
        default=os.path.join(
            os.environ.get("LOCALAPPDATA") or ".",
            "sample-brain",
            "workflow-observer-probe",
        ),
    )
    args = parser.parse_args()
    spool = Path(args.spool)
    report = fuse(spool)
    print(json.dumps({k: report[k] for k in report if k != "merged_preview"}, indent=2))


if __name__ == "__main__":
    main()
