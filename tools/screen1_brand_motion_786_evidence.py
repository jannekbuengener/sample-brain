"""Capture #786 brand/motion Visual Acceptance evidence outside the repository.

Usage:

  python tools/screen1_brand_motion_786_evidence.py ^
    --runtime-root <VALID-runtime-or-worktree> ^
    --evidence-dir D:\\Temp\\sample-brain-786-evidence
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


def _git_head(runtime_root: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(runtime_root), "rev-parse", "HEAD"],
        text=True,
    ).strip()


def _ensure_runtime_manifest(runtime_root: Path, python_exe: Path) -> None:
    from src.runtime_provenance import (
        MANIFEST_SCHEMA,
        RuntimeManifest,
        evaluate_runtime,
        write_runtime_manifest,
    )

    report = evaluate_runtime(runtime_root, executable=python_exe)
    if report.status.value == "valid":
        return
    head = _git_head(runtime_root)
    dirty = subprocess.check_output(
        ["git", "-C", str(runtime_root), "status", "--porcelain"],
        text=True,
    ).strip()
    if dirty:
        raise SystemExit(
            "worktree is dirty; commit before writing runtime manifest / capturing evidence"
        )
    write_runtime_manifest(
        runtime_root,
        RuntimeManifest(
            schema=MANIFEST_SCHEMA,
            channel="main",
            commit=head,
            runtime_root=str(runtime_root.resolve()),
            python_executable=str(python_exe.resolve()),
            installed_at=datetime.now(UTC).isoformat(),
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument(
        "--python-exe",
        type=Path,
        default=Path(sys.executable),
    )
    args = parser.parse_args()
    runtime_root = args.runtime_root.resolve()
    evidence_dir = args.evidence_dir.resolve()
    if evidence_dir.is_relative_to(runtime_root):
        raise SystemExit("evidence-dir must be outside the repository")

    _ensure_runtime_manifest(runtime_root, args.python_exe.resolve())
    env = os.environ.copy()
    env["QT_SCALE_FACTOR"] = "1.0"
    env["QT_QUICK_BACKEND"] = "software"
    code = (
        "import json; "
        "from pathlib import Path; "
        "from src.workbench_qml_spike import run_qml_visual_acceptance_786; "
        f"m=run_qml_visual_acceptance_786("
        f"runtime_root=Path({str(runtime_root)!r}), "
        f"evidence_dir=Path({str(evidence_dir)!r})); "
        "print(json.dumps(m, sort_keys=True))"
    )
    completed = subprocess.run(
        [str(args.python_exe), "-c", code],
        cwd=str(runtime_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        return completed.returncode
    lines = [line for line in completed.stdout.splitlines() if line.strip().startswith("{")]
    if not lines:
        sys.stderr.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        raise SystemExit("no manifest JSON emitted")
    print(lines[-1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
