#!/usr/bin/env python3
"""Write midi-gate-status.json under the LOCALAPPDATA spool (Windows)."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--status",
        required=True,
        choices=["PASS", "MIDI_DRIVER_REQUIRED", "UNKNOWN"],
    )
    p.add_argument(
        "--hold",
        action="store_true",
        help="Set disposition HOLD (required for MIDI_DRIVER_REQUIRED)",
    )
    p.add_argument("--note", default="")
    args = p.parse_args()

    local = os.environ.get("LOCALAPPDATA") or os.path.join(
        os.path.expanduser("~"), "AppData", "Local"
    )
    spool = Path(local) / "sample-brain" / "workflow-observer-probe"
    spool.mkdir(parents=True, exist_ok=True)

    disposition = "HOLD" if (args.hold or args.status == "MIDI_DRIVER_REQUIRED") else "CONTINUE"
    doc = {
        "status": args.status,
        "disposition": disposition,
        "written_t_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "note": args.note,
        "rule": "No virtual MIDI driver install without Owner GO",
    }
    path = spool / "midi-gate-status.json"
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print("wrote midi-gate-status.json status=%s disposition=%s" % (args.status, disposition))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
