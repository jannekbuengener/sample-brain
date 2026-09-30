#!/usr/bin/env python3
"""Deterministic capability / routing / mirror drift checker."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import capability_lib as caplib  # noqa: E402


def main() -> int:
    problems = caplib.collect_capability_drift(ROOT)
    if problems:
        print("CAPABILITY_DRIFT_CHECK: FAIL")
        for problem in problems:
            print(f"- {problem}")
        return 1
    print("CAPABILITY_DRIFT_CHECK: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
