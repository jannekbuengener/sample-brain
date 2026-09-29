from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CANON_PATHS = (
    "docs/CANON_INDEX.md",
    "docs/PRODUCT_WORKFLOW_CANON.md",
    "docs/PRODUCT_REQUIREMENTS.md",
    "docs/SYSTEM_REQUIREMENTS.md",
    "docs/TARGET_ARCHITECTURE.md",
    "docs/REALTIME_WORKBENCH_SCOPE.md",
    "docs/DATA_AND_ARTIFACT_POLICY.md",
    "docs/WORKBENCH_QML_PROOF_SPIKE.md",
    "docs/EPIC_2_SEMANTIC_SEARCH_SPEC.md",
    "knowledge/CURRENT_STATUS.md",
    "knowledge/ACTIVE_ROADMAP.md",
    "docs/ISSUE_BACKLOG.md",
)

_REQUIRED_CANON_CLASSES = (
    "ACTIVE_CANON",
    "ACTIVE_SUPPORTING",
    "DURABLE_SNAPSHOT",
    "HISTORICAL_LEDGER",
    "SUPERSEDED_RECORD",
)

_RECONCILED_RE = re.compile(r"\*\*Last reconciled:\*\*\s+\d{4}-\d{2}-\d{2}")


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def collect_canon_drift() -> list[str]:
    problems: list[str] = []

    for relative_path in CANON_PATHS:
        if not (ROOT / relative_path).is_file():
            problems.append(f"missing canon/front-door path: {relative_path}")

    if problems:
        return problems

    canon = _read("docs/CANON_INDEX.md")
    for classification in _REQUIRED_CANON_CLASSES:
        if classification not in canon:
            problems.append(f"CANON_INDEX missing classification: {classification}")

    bootloader = _read("SB.BOOTLOADER.md")
    if "docs/CANON_INDEX.md" not in bootloader:
        problems.append("SB.BOOTLOADER does not route through docs/CANON_INDEX.md")
    if "live #691" not in bootloader:
        problems.append("SB.BOOTLOADER does not route Screen-1 work through live #691")
    if "#503/#579 are historical" not in bootloader:
        problems.append("SB.BOOTLOADER does not classify #503/#579 as historical")

    backlog = _read("docs/ISSUE_BACKLOG.md")
    if "HISTORICAL LEDGER, NOT LIVE TRACKER" not in backlog:
        problems.append("ISSUE_BACKLOG is not explicitly classified as a historical ledger")

    for relative_path in (
        "knowledge/CURRENT_STATUS.md",
        "knowledge/ACTIVE_ROADMAP.md",
    ):
        if not _RECONCILED_RE.search(_read(relative_path)):
            problems.append(f"{relative_path} lacks a valid Last reconciled marker")

    workflow = _read("docs/PRODUCT_WORKFLOW_CANON.md")
    if "canonical product-path decision" not in workflow:
        problems.append("PRODUCT_WORKFLOW_CANON is not explicitly marked canonical")
    if "#469" not in workflow:
        problems.append("PRODUCT_WORKFLOW_CANON does not retain the parked VST3 boundary")

    epic2 = _read("docs/EPIC_2_SEMANTIC_SEARCH_SPEC.md")
    stale_primary_path_phrases = (
        "VST3-first product target",
        "VST3 plugin is now the primary product path",
    )
    for phrase in stale_primary_path_phrases:
        if phrase in epic2:
            problems.append(
                f"EPIC_2_SEMANTIC_SEARCH_SPEC resurrects superseded primary-path wording: {phrase}"
            )

    key_conf = _read("docs/benchmarks/KEY_CONF_EVIDENCE.md")
    if "Historical evidence snapshot" not in key_conf:
        problems.append("KEY_CONF_EVIDENCE does not identify its historical snapshot boundary")
    if "Commands recorded during the historical capture" not in key_conf:
        problems.append("KEY_CONF_EVIDENCE capture commands are not clearly historical")

    return problems


def main() -> int:
    problems = collect_canon_drift()
    if problems:
        print("CANON_DRIFT_CHECK: FAIL")
        for problem in problems:
            print(f"- {problem}")
        return 1

    print("CANON_DRIFT_CHECK: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
