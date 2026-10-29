#!/usr/bin/env python3
"""Deterministic Sample Brain QML review scanner for skill evidence.

Mechanical checks only (activation, binding-break assignments, delayed
cached-index use, optional qmllint). Python↔QML authority / ownership /
musical shadow state remain semantic review in SKILL.md — this helper must
not invent ownership findings from token lists.
Does not mutate product code. Stdlib-only.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]

QML_SUFFIXES = {".qml"}
QML_EMBED_HINTS = (
    "QML_SOURCE",
    "QtQuick",
    "ListView {",
    "reuseItems",
    "QQmlApplicationEngine",
)

INDEX_PROP_RE = re.compile(
    r"property\s+int\s+(\w*[Ii]ndex\w*)\s*:\s*index\b",
    re.MULTILINE,
)
CACHED_INDEX_USE_RE = re.compile(
    r"(?:toggleFavorite|selectRow|previewRow|openSampleContextMenu|"
    r"requestInternalSampleDragDescriptor|outboundFileUrl|persist|"
    r"addToKit|removeFromKit)\s*\(\s*([A-Za-z_][\w.]*)\s*\)",
)
TIMER_BLOCK_RE = re.compile(
    r"Timer\s*\{(?P<body>.*?)\n\s*\}",
    re.DOTALL,
)
ON_COMPLETED_ASSIGN_RE = re.compile(
    r"Component\.onCompleted\s*:\s*(?:\{[^}]*?\b(width|height|x|y)\s*=|"
    r"(width|height|x|y)\s*=)",
    re.DOTALL,
)


@dataclass(frozen=True)
class Finding:
    severity: str
    location: str
    category: str
    why: str
    authority: str
    repair: str
    evidence: str


def should_activate(paths: list[Path]) -> bool:
    for path in paths:
        if path.suffix.lower() in QML_SUFFIXES:
            return True
        if path.suffix.lower() == ".py":
            text = path.read_text(encoding="utf-8", errors="replace")
            if any(hint in text for hint in QML_EMBED_HINTS):
                return True
    return False


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def scan_text(path: Path, text: str) -> list[Finding]:
    """Emit only mechanical findings. Authority ownership is not decided here."""
    findings: list[Finding] = []
    rel = _rel(path)

    index_props = {m.group(1): m.start() for m in INDEX_PROP_RE.finditer(text)}
    for prop, start in index_props.items():
        delayed = False
        for timer in TIMER_BLOCK_RE.finditer(text):
            body = timer.group("body")
            if prop in body and CACHED_INDEX_USE_RE.search(body):
                delayed = True
                break
        uses = list(
            re.finditer(rf"\b(?:\w+\.)?{re.escape(prop)}\b", text[start:])
        )
        used_in_command = False
        for use in uses[1:]:  # skip declaration
            window = text[use.start() : use.start() + 120]
            if CACHED_INDEX_USE_RE.search(window) or (
                "toggleFavorite" in window
                or "selectRow" in window
                or "previewRow" in window
            ):
                if use.group(0).endswith(prop):
                    used_in_command = True
                    break
        if delayed or used_in_command:
            line = _line_of(text, start)
            findings.append(
                Finding(
                    severity="HIGH",
                    location=f"{rel}:{line}",
                    category="STALE_CACHED_DELEGATE_INDEX",
                    why=(
                        "A visual `index` is cached on a property and later used "
                        "on a delayed/command path. This is a mechanical reuse "
                        "risk signal only — whether it violates product authority "
                        "requires semantic review under SKILL.md."
                    ),
                    authority="n/a — semantic ownership review required",
                    repair=(
                        "Prefer immediate typed intent, or a stable model id; "
                        "clear deferred index state in ListView.onPooled when "
                        "semantic review confirms a product risk."
                    ),
                    evidence=f"property {prop}: index used across delayed/command path",
                )
            )

    for match in ON_COMPLETED_ASSIGN_RE.finditer(text):
        prop = match.group(1) or match.group(2)
        line = _line_of(text, match.start())
        findings.append(
            Finding(
                severity="MEDIUM",
                location=f"{rel}:{line}",
                category="BINDING_BREAK_ASSIGNMENT",
                why=(
                    f"Imperative assignment to `{prop}` in Component.onCompleted "
                    "replaces a declarative binding; later geometry updates may not "
                    "propagate."
                ),
                authority="n/a — QML presentation geometry",
                repair=(
                    "Keep width/height/x/y as bindings, or use Binding/anchors/"
                    "Layout instead of a one-shot assignment."
                ),
                evidence=match.group(0).splitlines()[0][:120],
            )
        )

    return findings


def try_qmllint(paths: list[Path]) -> tuple[bool, str]:
    """Run qmllint when a live binary is available. Never required for PASS/HOLD."""
    qml_files = [p for p in paths if p.suffix.lower() == ".qml"]
    if not qml_files:
        return False, "qmllint skipped: no .qml paths"
    exe = shutil.which("qmllint")
    if exe is None:
        try:
            import PySide6  # type: ignore

            candidate = Path(PySide6.__file__).resolve().parent / (
                "qmllint.exe" if sys.platform.startswith("win") else "qmllint"
            )
            if candidate.is_file():
                exe = str(candidate)
        except Exception:
            exe = None
    if not exe:
        return False, "qmllint unavailable in this environment"
    try:
        proc = subprocess.run(
            [exe, *[str(p) for p in qml_files]],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"qmllint failed to run: {exc}"
    out = (proc.stdout or "") + (proc.stderr or "")
    return True, out.strip() or f"qmllint exit={proc.returncode}"


def scan_paths(paths: list[Path]) -> dict:
    activated = should_activate(paths)
    findings: list[Finding] = []
    if activated:
        for path in paths:
            if not path.is_file():
                continue
            if path.suffix.lower() not in QML_SUFFIXES and path.suffix.lower() != ".py":
                continue
            if path.suffix.lower() == ".py":
                text = path.read_text(encoding="utf-8", errors="replace")
                if not any(hint in text for hint in QML_EMBED_HINTS):
                    continue
            else:
                text = path.read_text(encoding="utf-8", errors="replace")
            findings.extend(scan_text(path, text))
    qmllint_ran, qmllint_out = (
        try_qmllint(paths) if activated else (False, "not activated")
    )
    verdict = "HOLD" if findings else ("PASS" if activated else "NOT_ACTIVATED")
    return {
        "activated": activated,
        "verdict": verdict,
        "findings": [asdict(f) for f in findings],
        "qmllint": {"ran": qmllint_ran, "output": qmllint_out},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = scan_paths([p.resolve() for p in args.paths])
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"activated={result['activated']} verdict={result['verdict']}")
        for finding in result["findings"]:
            print(
                f"{finding['severity']} {finding['category']} "
                f"{finding['location']}: {finding['why']}"
            )
        if result["qmllint"]["ran"]:
            print("--- qmllint ---")
            print(result["qmllint"]["output"])
        elif result["activated"]:
            print(f"qmllint: {result['qmllint']['output']}")
    return 1 if result["verdict"] == "HOLD" else 0


if __name__ == "__main__":
    raise SystemExit(main())
