#!/usr/bin/env python3
"""Minimal Sample Brain QML/component test run helper (#1306).

Normalizes focused pytest invocation, probes the live environment, and
classifies outcomes. Does not invent a second harness or redesign tests.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

FAILURE_CLASSES = (
    "PASS",
    "TEST_HARNESS_BOOTSTRAP",
    "QML_PARSE_LOAD_IMPORT",
    "ASSERTION_BEHAVIOR",
    "PYTHON_BRIDGE_ADAPTER",
    "PLATFORM_WINDOW_DISPLAY_RUNTIME",
    "UNRELATED_BASELINE",
    "INCONCLUSIVE",
)

_SUMMARY_RE = re.compile(
    r"(?P<failed>\d+)\s+failed"
    r"|(?P<passed>\d+)\s+passed"
    r"|(?P<skipped>\d+)\s+skipped"
    r"|(?P<xfailed>\d+)\s+xfailed"
    r"|(?P<xpassed>\d+)\s+xpassed"
    r"|(?P<errors>\d+)\s+error"
    r"|(?P<deselected>\d+)\s+deselected",
    re.IGNORECASE,
)

_QT_WARN_RE = re.compile(
    r"(qrc:/|QQml|QML\s|Binding loop|Cannot assign|TypeError|"
    r"ReferenceError|Module .* is not installed|file://.*\.qml|"
    r"keine QML|QML load|Component\.Error|import\s+QtQuick)",
    re.IGNORECASE,
)


@dataclass
class ProbeResult:
    python_executable: str
    platform: str
    pyside6: str | None
    qt_version: str | None
    qt_qpa_platform_env: str | None
    recommended_qt_qpa: str | None
    runner_docs: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class RunReport:
    target: str
    run_mode: str
    command: list[str]
    environment_assumptions: list[str]
    exit_code: int
    counts: dict[str, int]
    failure_class: str
    relevant_evidence: list[str]
    interpretation: str
    next_route: str
    result_state: str
    assertions_exercised: bool
    target_collected: bool


def repo_root_from_here() -> Path:
    return Path(__file__).resolve().parents[4]


def discover_runner_docs(root: Path) -> list[str]:
    docs: list[str] = []
    for rel in (
        "docs/WINDOWS_TEST_HARNESS.md",
        "AGENTS.md",
        ".github/workflows/core-pytest.yml",
    ):
        if (root / rel).is_file():
            docs.append(rel)
    return docs


def recommended_qt_qpa(system: str | None = None) -> str | None:
    sys_name = (system or platform.system()).lower()
    if sys_name == "windows":
        # Live authority: docs/WINDOWS_TEST_HARNESS.md — do not invent offscreen.
        return "windows"
    if sys_name == "linux":
        # CI uses xvfb-run; do not auto-force QT_QPA_PLATFORM=offscreen.
        return None
    return None


def probe_environment(root: Path | None = None) -> ProbeResult:
    root = root or repo_root_from_here()
    notes: list[str] = []
    pyside_ver: str | None = None
    qt_ver: str | None = None
    try:
        import PySide6

        pyside_ver = getattr(PySide6, "__version__", "present")
        try:
            from PySide6.QtCore import qVersion

            qt_ver = qVersion()
        except Exception as exc:  # noqa: BLE001 — probe only
            notes.append(f"Qt version probe failed: {type(exc).__name__}")
    except ModuleNotFoundError:
        notes.append("PySide6 not importable in this interpreter")
    except Exception as exc:  # noqa: BLE001
        notes.append(f"PySide6 import failed: {type(exc).__name__}: {exc}")

    qt_env = os.environ.get("QT_QPA_PLATFORM")
    rec = recommended_qt_qpa()
    if qt_env and rec and qt_env != rec:
        notes.append(
            f"QT_QPA_PLATFORM={qt_env!r} differs from live Windows harness "
            f"recommendation {rec!r}; classify mismatches carefully"
        )
    if qt_env == "offscreen" and platform.system().lower() == "windows":
        notes.append(
            "Blind QT_QPA_PLATFORM=offscreen is not the Sample Brain Windows "
            "documented path (see docs/WINDOWS_TEST_HARNESS.md)"
        )

    return ProbeResult(
        python_executable=sys.executable,
        platform=platform.platform(),
        pyside6=pyside_ver,
        qt_version=qt_ver,
        qt_qpa_platform_env=qt_env,
        recommended_qt_qpa=rec,
        runner_docs=discover_runner_docs(root),
        notes=notes,
    )


def parse_pytest_counts(text: str) -> dict[str, int]:
    counts = {
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "xfailed": 0,
        "xpassed": 0,
        "errors": 0,
        "deselected": 0,
    }
    for match in _SUMMARY_RE.finditer(text):
        for key, value in match.groupdict().items():
            if value is not None:
                counts[key] = int(value)
    return counts


def extract_relevant_evidence(text: str, *, limit: int = 12) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if _QT_WARN_RE.search(line) or any(
            token in line
            for token in (
                "ImportError",
                "ModuleNotFoundError",
                "PermissionError",
                "AssertionError",
                "FAILED",
                "ERROR",
                "RuntimeError",
                "DLL load failed",
                "pytest-current",
                "WinError",
                "QPA",
                "could not connect to display",
                "This application failed to start",
            )
        ):
            # Sanitize absolute user paths lightly.
            sanitized = re.sub(r"[A-Za-z]:\\Users\\[^\\]+", r"<USER>", line)
            sanitized = re.sub(r"/home/[^/]+", r"<USER>", sanitized)
            lines.append(sanitized[:240])
        if len(lines) >= limit:
            break
    return lines


def classify_outcome(
    *,
    exit_code: int,
    output: str,
    counts: Mapping[str, int] | None = None,
) -> tuple[str, str, str, bool, bool, str]:
    """Return failure_class, interpretation, next_route, assertions_exercised,
    target_collected, result_state."""
    text = output or ""
    counts = dict(counts or parse_pytest_counts(text))
    lowered = text.lower()

    passed = int(counts.get("passed", 0))
    failed = int(counts.get("failed", 0))
    errors = int(counts.get("errors", 0))
    skipped = int(counts.get("skipped", 0))
    deselected = int(counts.get("deselected", 0))

    collected_hint = (
        "collected" in lowered
        or "test session starts" in lowered
        or passed + failed + errors + skipped + deselected > 0
        or "====" in text
    )
    assertions_exercised = passed > 0 or failed > 0
    target_collected = collected_hint and not (
        "found no collectors" in lowered or "error during collection" in lowered
    )

    # Cleanup / shared basetemp noise with green assertions (#1143).
    if (
        passed > 0
        and failed == 0
        and errors == 0
        and (
            "permissionerror" in lowered
            or "pytest-current" in lowered
            or "winerror 5" in lowered
        )
        and exit_code != 0
    ):
        return (
            "UNRELATED_BASELINE",
            "Selected target assertions passed; non-zero exit tied to shared "
            "pytest temp cleanup / host permission noise, not QML product logic.",
            "HOLD_ISOLATE_BASETEMP",
            True,
            True,
            "HOLD",
        )

    # Collection / import / bootstrap before product assertions.
    bootstrap_tokens = (
        "error during collection",
        "found no collectors",
        "dll load failed",
        "modulenotfounderror",
        "importerror while importing test module",
        "no module named 'pyside6'",
        "no module named \"pyside6\"",
    )
    if errors > 0 or any(tok in lowered for tok in bootstrap_tokens):
        if any(
            tok in lowered
            for tok in (
                "could not connect to display",
                "this application failed to start because no qt platform",
                "qt.qpa",
            )
        ):
            return (
                "PLATFORM_WINDOW_DISPLAY_RUNTIME",
                "Qt platform/display/runtime prevented execution; not proven "
                "product regression.",
                "HOLD_ENVIRONMENT",
                False,
                False,
                "HOLD",
            )
        return (
            "TEST_HARNESS_BOOTSTRAP",
            "Failure occurred before/during collection or interpreter bootstrap; "
            "do not label as QML product behavior.",
            "HOLD_INFRASTRUCTURE",
            False,
            False,
            "HOLD",
        )

    if any(
        tok in lowered
        for tok in (
            "could not connect to display",
            "this application failed to start because no qt platform",
            "qt.qpa.plugin",
        )
    ):
        return (
            "PLATFORM_WINDOW_DISPLAY_RUNTIME",
            "Platform/window/display/runtime limitation observed.",
            "HOLD_ENVIRONMENT",
            assertions_exercised,
            target_collected,
            "HOLD",
        )

    # Unexpected QML parse/load/import failures (failed tests / uncaught load).
    qml_load_tokens = (
        "keine qml",
        "qml load",
        "qqmlapplicationengine",
        "qqmlcomponent",
        "component.error",
        'module "qtquick" is not installed',
        "is not installed",
        "invalid qml source",
        "failed to load source",
    )
    if failed > 0 and any(tok in lowered for tok in qml_load_tokens):
        return (
            "QML_PARSE_LOAD_IMPORT",
            "QML parse/load/import failure layer; separate invalid product QML "
            "from missing/incorrect import path or runtime with evidence. "
            "Do not invent musical/product root cause from a load error.",
            "HOLD_QML_LOAD",
            True,
            True,
            "HOLD",
        )

    if failed > 0 or "assertionerror" in lowered:
        bridge_tokens = (
            "shiboken",
            "slot",
            "qobject",
            "pyqt",
            "pyside",
            "adapter",
            "bridge",
        )
        if any(tok in lowered for tok in bridge_tokens) and "assertionerror" in lowered:
            # Prefer ASSERTION_BEHAVIOR unless clearly import/bootstrap.
            pass
        return (
            "ASSERTION_BEHAVIOR",
            "Target booted and an assertion/behavior check failed. Do not invent "
            "product root cause here; route if cause remains unclear.",
            "sample-brain-root-cause",
            True,
            True,
            "HOLD",
        )

    if exit_code == 0 and passed > 0 and failed == 0 and errors == 0:
        return (
            "PASS",
            "Target collected, assertions exercised, process exit coherent with PASS.",
            "PASS",
            True,
            True,
            "PASS",
        )

    if exit_code in (0, 5) and passed == 0 and failed == 0 and errors == 0:
        if skipped > 0 or deselected > 0 or "skipped" in lowered:
            return (
                "TEST_HARNESS_BOOTSTRAP",
                "Skip/deselect only — target assertions were not exercised; "
                "not a product PASS.",
                "HOLD_ENVIRONMENT",
                False,
                target_collected,
                "HOLD",
            )

    if exit_code != 0:
        return (
            "INCONCLUSIVE",
            "Non-zero exit without a clear classified layer; capture evidence and "
            "re-run smallest target with isolated basetemp.",
            "HOLD_RERUN_FOCUSED",
            assertions_exercised,
            target_collected,
            "HOLD",
        )

    return (
        "INCONCLUSIVE",
        "Unable to prove PASS: exit 0 without exercised assertions.",
        "HOLD_RERUN_FOCUSED",
        False,
        target_collected,
        "HOLD",
    )


def build_command(
    target: str,
    *,
    basetemp: Path | None,
    extra_args: Sequence[str] | None = None,
) -> list[str]:
    cmd = [sys.executable, "-m", "pytest", "-q", target]
    if basetemp is not None:
        cmd.extend(["--basetemp", str(basetemp)])
    if extra_args:
        cmd.extend(extra_args)
    return cmd


def run_target(
    target: str,
    *,
    root: Path | None = None,
    basetemp: Path | None = None,
    extra_args: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
    dry_classify_output: str | None = None,
    dry_exit_code: int | None = None,
) -> RunReport:
    root = root or repo_root_from_here()
    probe = probe_environment(root)
    assumptions = [
        "runner=pytest via python -m pytest (not qmltestrunner)",
        f"cwd={root.name}",
    ]
    if probe.recommended_qt_qpa:
        assumptions.append(
            f"recommended_QT_QPA_PLATFORM={probe.recommended_qt_qpa} "
            "(from live Windows harness docs when on Windows)"
        )
    if probe.qt_qpa_platform_env:
        assumptions.append(f"current_QT_QPA_PLATFORM={probe.qt_qpa_platform_env}")
    assumptions.extend(f"note:{n}" for n in probe.notes)

    if dry_classify_output is not None:
        output = dry_classify_output
        exit_code = 0 if dry_exit_code is None else dry_exit_code
        cmd = ["<dry-classify>"]
        run_mode = "classify-only"
    else:
        if basetemp is None:
            basetemp = Path(tempfile.mkdtemp(prefix="sb-qml-test-run-"))
        cmd = build_command(target, basetemp=basetemp, extra_args=extra_args)
        run_env = os.environ.copy()
        if env:
            run_env.update(env)
        # Do not silently force QT_QPA_PLATFORM; only inherit or use caller env.
        completed = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            text=True,
            env=run_env,
            check=False,
        )
        output = (completed.stdout or "") + ("\n" + completed.stderr if completed.stderr else "")
        exit_code = int(completed.returncode)
        run_mode = "focused-pytest"

    counts = parse_pytest_counts(output)
    failure_class, interpretation, next_route, exercised, collected, state = (
        classify_outcome(exit_code=exit_code, output=output, counts=counts)
    )
    evidence = extract_relevant_evidence(output)
    if not evidence:
        evidence = [
            f"exit_code={exit_code}",
            f"counts={counts}",
        ]

    return RunReport(
        target=target,
        run_mode=run_mode,
        command=cmd,
        environment_assumptions=assumptions,
        exit_code=exit_code,
        counts=counts,
        failure_class=failure_class,
        relevant_evidence=evidence,
        interpretation=interpretation,
        next_route=next_route,
        result_state=state,
        assertions_exercised=exercised,
        target_collected=collected,
    )


def report_to_mapping(report: RunReport) -> dict[str, Any]:
    data = asdict(report)
    # Compact YAML-like consumer shape.
    return {
        "target": data["target"],
        "run_mode": data["run_mode"],
        "command": data["command"],
        "environment_assumptions": data["environment_assumptions"],
        "result_state": data["result_state"],
        "exit_code": data["exit_code"],
        "counts": data["counts"],
        "target_collected": data["target_collected"],
        "assertions_exercised": data["assertions_exercised"],
        "failure_class": data["failure_class"],
        "relevant_evidence": data["relevant_evidence"],
        "interpretation": data["interpretation"],
        "next_route": data["next_route"],
    }


def format_yaml_like(report: RunReport) -> str:
    data = report_to_mapping(report)
    lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            if not value:
                lines.append("  []")
            for item in value:
                lines.append(f"  - {item}")
        elif isinstance(value, dict):
            lines.append(f"{key}:")
            for k, v in value.items():
                lines.append(f"  {k}: {v}")
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sample Brain QML/component test run helper"
    )
    parser.add_argument(
        "--target",
        help="pytest node id or path (focused first)",
    )
    parser.add_argument(
        "--basetemp",
        type=Path,
        help="isolated pytest basetemp (recommended on Windows)",
    )
    parser.add_argument(
        "--classify-transcript",
        type=Path,
        help="classify a saved pytest transcript without re-running",
    )
    parser.add_argument(
        "--exit-code",
        type=int,
        default=None,
        help="exit code accompanying --classify-transcript",
    )
    parser.add_argument("--probe-env", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--extra-arg",
        action="append",
        default=[],
        help="extra pytest arg (repeatable)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    root = repo_root_from_here()

    if args.probe_env:
        probe = probe_environment(root)
        payload = asdict(probe)
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            for key, value in payload.items():
                print(f"{key}: {value}")
        return 0

    if args.classify_transcript is not None:
        text = args.classify_transcript.read_text(encoding="utf-8")
        report = run_target(
            args.target or str(args.classify_transcript),
            root=root,
            dry_classify_output=text,
            dry_exit_code=args.exit_code if args.exit_code is not None else 1,
        )
    elif args.target:
        report = run_target(
            args.target,
            root=root,
            basetemp=args.basetemp,
            extra_args=args.extra_arg,
        )
    else:
        parser.error("provide --target, --classify-transcript, or --probe-env")
        return 2

    if args.json:
        print(json.dumps(report_to_mapping(report), indent=2))
    else:
        print(format_yaml_like(report))
    return 0 if report.result_state == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
