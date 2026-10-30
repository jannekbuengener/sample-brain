"""CLI entry: python -m fl_workflow_recorder …"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow `python -m fl_workflow_recorder` from tools/fl_workflow_recorder
_PKG_PARENT = Path(__file__).resolve().parents[1]
if str(_PKG_PARENT) not in sys.path:
    sys.path.insert(0, str(_PKG_PARENT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FL Workflow zero-touch recorder (#1321)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Run recorder service (foreground)")
    p_run.add_argument("--root", type=Path, default=None, help="Override observer root dir")
    p_run.add_argument("--no-windows-capture", action="store_true")
    p_run.add_argument("--poll-interval", type=float, default=0.5)
    p_run.add_argument("--retention-days", type=int, default=90)

    p_status = sub.add_parser("status", help="Print health.json")
    p_status.add_argument("--root", type=Path, default=None)

    p_midi = sub.add_parser("midi-check", help="Probe observer MIDI ports")
    p_midi.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    if args.cmd == "run":
        from .paths import ObserverPaths
        from .service import RecorderService

        paths = ObserverPaths(args.root) if args.root else ObserverPaths()
        return RecorderService(
            paths,
            enable_windows_capture=not args.no_windows_capture,
            poll_interval_sec=args.poll_interval,
            retention_days=args.retention_days,
        ).run()

    if args.cmd == "status":
        from .health import read_health
        from .paths import ObserverPaths

        paths = ObserverPaths(args.root) if args.root else ObserverPaths()
        data = read_health(paths.health)
        if not data:
            print(json.dumps({"ok": False, "error": "health_missing"}))
            return 1
        print(json.dumps(data, indent=2))
        return 0

    if args.cmd == "midi-check":
        from .midi_health import probe_midi_ports

        h = probe_midi_ports()
        payload = {
            "available": h.available,
            "observer_in_present": h.observer_in_present,
            "observer_out_present": h.observer_out_present,
            "input_count": h.input_count,
            "output_count": h.output_count,
            "detail": h.detail,
        }
        print(json.dumps(payload, indent=2 if args.json else None))
        return 0 if h.observer_in_present and h.observer_out_present else 2

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
