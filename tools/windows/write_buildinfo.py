"""CLI helper to write hygiene-checked BUILDINFO for the Windows distributable."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.workbench_distributable_buildinfo import (
    default_pilot_buildinfo_fields,
    format_buildinfo,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--python", required=True)
    parser.add_argument("--pyside6", required=True)
    parser.add_argument("--qt", required=True)
    parser.add_argument("--pyinstaller", required=True)
    parser.add_argument("--nuitka", required=True)
    parser.add_argument("--artifact-zip", required=True)
    args = parser.parse_args()
    text = format_buildinfo(
        default_pilot_buildinfo_fields(
            build_id=args.build_id,
            source_sha=args.source_sha,
            python=args.python,
            pyside6=args.pyside6,
            qt=args.qt,
            pyinstaller=args.pyinstaller,
            nuitka=args.nuitka,
            artifact_zip=args.artifact_zip,
        )
    )
    args.out.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
