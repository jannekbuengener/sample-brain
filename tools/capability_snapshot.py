#!/usr/bin/env python3
"""On-demand capability/KPI snapshot (stdout JSON). Never invent live zeros."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import capability_lib as caplib  # noqa: E402


def _load_canon_checker():
    path = ROOT / "tools" / "check_canon_drift.py"
    spec = importlib.util.spec_from_file_location("check_canon_drift", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _gh_available() -> bool:
    if shutil.which("gh") is None:
        return False
    try:
        proc = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.returncode == 0
    except OSError:
        return False


def _kpi(
    status: str,
    value: Any,
    source: str,
    freshness: str,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "value": value,
        "source": source,
        "freshness": freshness,
        "limitations": limitations or [],
    }


def build_snapshot() -> dict[str, Any]:
    registry = caplib.load_registry(ROOT)
    kpi_contract = caplib.load_kpi_contract(ROOT)
    drift = caplib.collect_capability_drift(ROOT)
    canon = _load_canon_checker().collect_canon_drift()
    gh_ok = _gh_available()

    kpis: dict[str, Any] = {
        "canon_contradiction_count": _kpi(
            "measured",
            len(canon),
            "tools/check_canon_drift.py",
            "repo_current",
        ),
        "duplicate_capability_count": _kpi(
            "derived",
            caplib.count_duplicate_authority_surfaces(ROOT),
            "tools/capability_lib.py",
            "repo_current",
        ),
        "skill_contract_gap_count": _kpi(
            "derived",
            len(drift),
            "tools/check_capability_drift.py",
            "repo_current",
            limitations=drift[:20],
        ),
        "stale_skill_reference_count": _kpi(
            "derived",
            len(
                [
                    p
                    for p in drift
                    if "historical" in p.lower() or "skills liste" in p.lower()
                ]
            ),
            "capability drift historical checks",
            "repo_current",
        ),
        "capability_registry_entry_count": _kpi(
            "measured",
            len(registry.get("capabilities", [])),
            "docs/operations/CAPABILITY_REGISTRY.json",
            "repo_current",
        ),
        "kpi_contract_entry_count": _kpi(
            "measured",
            len(kpi_contract.get("kpis", [])),
            "docs/operations/KPI_CONTRACT.json",
            "repo_current",
        ),
    }

    github_deferred = [
        "repair_rounds_per_pr",
        "required_check_retries",
        "first_pass_ready_rate",
        "closed_issue_referenced_as_active_count",
        "stale_active_doc_count",
    ]
    for kid in github_deferred:
        if gh_ok:
            kpis[kid] = _kpi(
                "unknown",
                None,
                "gh",
                "unknown",
                limitations=[
                    "definition present in KPI_CONTRACT.json; live collector not enabled in this slice"
                ],
            )
        else:
            kpis[kid] = _kpi(
                "unknown",
                None,
                "gh",
                "unknown",
                limitations=["github unavailable or unauthenticated"],
            )

    for kid in (
        "unclassified_artifact_count",
        "historical_evidence_missing_status_count",
        "validation_generations_per_delivery",
        "review_rework_rounds",
        "scope_expansion_count",
        "manual_clarification_count",
        "fallback_to_generic_flow_count",
        "routing_mismatch_count",
    ):
        kpis[kid] = _kpi(
            "unknown",
            None,
            "NONE",
            "unknown",
            limitations=["classified UNKNOWN / not collected in this snapshot"],
        )

    kpis["agent_escalation_without_real_blocker_count"] = _kpi(
        "not_applicable",
        None,
        "NONE",
        "unknown",
        limitations=["REJECT in KPI contract; not measured"],
    )

    return {
        "schema_version": 1,
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repository": "jannekbuengener/sample-brain",
        "source_state": {
            "repo": str(ROOT.name),
            "github": "available" if gh_ok else "unavailable",
        },
        "capability_drift": "PASS" if not drift else "FAIL",
        "kpis": kpis,
    }


def main() -> int:
    print(json.dumps(build_snapshot(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
