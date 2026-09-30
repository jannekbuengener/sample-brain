#!/usr/bin/env python3
"""CLI entry: Sample Brain Screen-1 UI acceptance (local Windows).

Usage:
  python tools/screen1_ui_acceptance.py
  python tools/screen1_ui_acceptance.py --keep-app

Evidence is written outside the repo under ~/.sample-brain/ui-acceptance/<run-id>/.
Does not depend on windows-mcp as a Python package.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Screen-1 UI acceptance runner")
    parser.add_argument(
        "--keep-app",
        action="store_true",
        help="Do not terminate a Sample Brain process started by this runner",
    )
    args = parser.parse_args(argv)

    from src.screen1_ui_acceptance import run_acceptance

    report, code = run_acceptance(keep_app=bool(args.keep_app))
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
