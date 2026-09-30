#!/usr/bin/env python3
"""Generate marked capability routing blocks from the registry."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import capability_lib as caplib  # noqa: E402


def main() -> int:
    updated = caplib.apply_generated_views(ROOT)
    for rel in updated:
        print(f"updated: {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
