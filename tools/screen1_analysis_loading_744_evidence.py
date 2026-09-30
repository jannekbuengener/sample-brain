"""Capture #744 analysis-loading Owner Visual evidence outside the repository.

Usage (fresh processes; evidence_dir must be outside the repo):

  python tools/screen1_analysis_loading_744_evidence.py ^
    --runtime-root <VALID-runtime> ^
    --evidence-dir D:\\Temp\\sample-brain-744-evidence

Writes a Git-administrative runtime manifest when missing, then captures
01–09 across QT_SCALE_FACTOR 1.0 / 1.25 / 1.5 in fresh processes.
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

    report = evaluate_runtime(
        runtime_root,
        executable=python_exe,
    )
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


def _run_scale(
    *,
    runtime_root: Path,
    evidence_dir: Path,
    scale: float,
    python_exe: Path,
) -> dict[str, object]:
    env = os.environ.copy()
    env["QT_SCALE_FACTOR"] = str(scale)
    env["QT_QUICK_BACKEND"] = "software"
    code = (
        "import json,sys; "
        "from pathlib import Path; "
        "from src.workbench_qml_spike import run_qml_visual_acceptance_744; "
        f"m=run_qml_visual_acceptance_744("
        f"runtime_root=Path({str(runtime_root)!r}), "
        f"evidence_dir=Path({str(evidence_dir)!r}), "
        f"scale_factor={scale!r}); "
        "print(json.dumps(m, sort_keys=True))"
    )
    completed = subprocess.run(
        [str(python_exe), "-c", code],
        cwd=str(runtime_root),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        raise SystemExit(completed.returncode)
    lines = [line for line in completed.stdout.splitlines() if line.strip().startswith("{")]
    if not lines:
        sys.stderr.write(completed.stdout)
        sys.stderr.write(completed.stderr)
        raise SystemExit("no manifest JSON from #744 capture process")
    return json.loads(lines[-1])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument(
        "--python",
        type=Path,
        default=None,
        help="Interpreter under runtime-root/.venv (default: runtime .venv python)",
    )
    args = parser.parse_args()
    runtime_root = args.runtime_root.resolve()
    evidence_dir = args.evidence_dir.resolve()
    try:
        if evidence_dir.is_relative_to(runtime_root):
            print(
                "[ERROR] evidence-dir must stay outside the runtime/repo tree",
                file=sys.stderr,
            )
            return 2
    except AttributeError:
        if str(evidence_dir).startswith(str(runtime_root)):
            print(
                "[ERROR] evidence-dir must stay outside the runtime/repo tree",
                file=sys.stderr,
            )
            return 2
    python_exe = args.python
    if python_exe is None:
        candidate = runtime_root / ".venv" / "Scripts" / "python.exe"
        if not candidate.is_file():
            candidate = runtime_root / ".venv" / "bin" / "python"
        python_exe = candidate
    if not python_exe.is_file():
        print(f"[ERROR] python not found: {python_exe}", file=sys.stderr)
        return 2

    sys.path.insert(0, str(runtime_root))
    _ensure_runtime_manifest(runtime_root, python_exe.resolve())
    evidence_dir.mkdir(parents=True, exist_ok=True)
    manifests = []
    for scale in (1.0, 1.25, 1.5):
        manifests.append(
            _run_scale(
                runtime_root=runtime_root,
                evidence_dir=evidence_dir,
                scale=scale,
                python_exe=python_exe.resolve(),
            )
        )
    summary = {
        "issue": 744,
        "evidence_dir": str(evidence_dir),
        "manifests": [m.get("capture_labels") for m in manifests],
    }
    (evidence_dir / "manifest-744-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
