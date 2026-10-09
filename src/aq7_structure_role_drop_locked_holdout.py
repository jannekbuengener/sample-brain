"""AQ7 locked TEST/HOLDOUT evaluation + regression gates (#1030).

Consumes the immutable #1028 freeze (`aq7.baseline.v1` /
`AQ7_NO_JUSTIFIED_CANDIDATE_KEEP_BASELINE`). No post-reveal tuning.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import statistics
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

from .analysis_eval_artifact import (
    AnalysisEvalArtifactError,
    assert_portable_value,
)
from .aq7_structure_boundary_baseline import (
    DOCUMENT_TYPE as BOUNDARY_BASELINE_DOCUMENT_TYPE,
    CANDIDATE_ID as BOUNDARY_BASELINE_CANDIDATE_ID,
    PLANE_TOKEN as BOUNDARY_PLANE,
    STRUCTURE_SURFACE,
    aggregate_boundary_splits,
)
from .aq7_structure_role_drop_baseline import (
    ARRANGEMENT_SURFACE,
    BOUNDARY_CONTEXT_CANDIDATE_ID,
    CANDIDATE_ID as ROLE_DROP_BASELINE_CANDIDATE_ID,
    DOCUMENT_TYPE as ROLE_DROP_BASELINE_DOCUMENT_TYPE,
    DROP_PLANE_TOKEN,
    ROLE_PLANE_TOKEN,
    SECTION_SIGNAL_SURFACE,
    aggregate_role_drop_splits,
)
from .aq7_structure_role_drop_candidate_compare import (
    BASELINE_CANDIDATE_ID,
    BOUNDARY_SURFACE_POLICY,
    DOCUMENT_TYPE as COMPARE_DOCUMENT_TYPE,
    EXIT_KEEP_BASELINE,
    Aq7Candidate,
    candidate_by_id,
    candidate_public,
    predict_fixture_for_candidate,
)
from .aq7_structure_role_drop_corpus import (
    CORPUS_ID,
    CORPUS_VERSION,
    GENERATOR_SEED,
    assert_work_dir_outside_repo,
    generate_aq7_structure_role_drop_corpus,
)
from .aq7_structure_role_drop_schema import load_aq7_corpus_manifest, load_aq7_fixture_gt
from .measurement.stats import percentile

DOCUMENT_TYPE = "sample-brain.aq7.structure-role-drop-locked-holdout.v1"
SCHEMA_VERSION = "1.0.0"
ISSUE_ID = 1030
AQ7_SLICE = "locked_holdout_evaluation"
FROZEN_CANDIDATE_ID = BASELINE_CANDIDATE_ID  # aq7.baseline.v1
FREEZE_TOKEN = EXIT_KEEP_BASELINE  # AQ7_NO_JUSTIFIED_CANDIDATE_KEEP_BASELINE
EVALUATED_PARTITION = "TEST"
TEST_FIXTURE_COUNT = 4
EXIT_EVALUATED = "AQ7_LOCKED_HOLDOUT_EVALUATED"
EXIT_PARTIAL_HOLD = "AQ7_HOLDOUT_PARTIAL_HOLD"
EXIT_INCOMPLETE = "AQ7_HOLDOUT_INCOMPLETE"
FEATURE_TOGGLE = "N/A"
PRODUCTION_DEFAULTS_CHANGED = False
CANDIDATE_EQUALS_BASELINE = True
AUTHORIZED_HOLD_REASONS = frozenset({"BEATGRID_PROVENANCE_LIMITATION"})
REJECTED_CANDIDATE_IDS = frozenset(
    {
        "boundary.min_distance.4",
        "role.unknown_margin.0.03",
        "drop.onset_thresh.0.80",
    }
)
# Literal #1028/#1030 freeze fingerprints. Live StructureV1 /
# ArrangementClassifier defaults must match these or evaluation fails closed.
FROZEN_STRUCTURE_CONFIG = {
    "bar_grid_policy": "require_downbeats",
    "candidate_percentile": 0.8,
    "disabled_features": [],
    "fft_size": 512,
    "low_end_hz": 150.0,
    "min_boundary_distance_bars": 2,
    "min_contributing_groups": 2,
    "n_mfcc": 8,
    "trend_windows_bars": [4, 8, 16],
}
FROZEN_ARRANGEMENT_CONFIG = {
    "available_min_completeness": 0.75,
    "drop_onset_threshold": 0.65,
    "unknown_min_best_score": 0.45,
    "unknown_min_completeness": 0.5,
    "unknown_min_margin": 0.05,
}

_REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[1]

PARTITION_POLICY = {
    "CALIBRATION": "DEVELOPMENT/CALIBRATION",
    "TEST": "TEST/HOLDOUT",
}

PLANE_TOKENS = (BOUNDARY_PLANE, ROLE_PLANE_TOKEN, DROP_PLANE_TOKEN)


class Aq7LockedHoldoutError(ValueError):
    """Controlled, fail-closed identity / firewall / contract error."""


def _canonical_config(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def assert_frozen_config_fingerprint(candidate: Aq7Candidate) -> None:
    """Fail closed if live baseline knobs drifted after the #1028/#1030 freeze."""
    structure = asdict(candidate.structure_config)
    arrangement = asdict(candidate.arrangement_config)
    if _canonical_config(structure) != _canonical_config(FROZEN_STRUCTURE_CONFIG):
        raise Aq7LockedHoldoutError(
            "frozen StructureV1 config fingerprint mismatch against "
            f"{FROZEN_CANDIDATE_ID}: live defaults drifted after holdout freeze"
        )
    if _canonical_config(arrangement) != _canonical_config(FROZEN_ARRANGEMENT_CONFIG):
        raise Aq7LockedHoldoutError(
            "frozen ArrangementClassifier config fingerprint mismatch against "
            f"{FROZEN_CANDIDATE_ID}: live defaults drifted after holdout freeze"
        )


def frozen_candidate() -> Aq7Candidate:
    candidate = candidate_by_id(FROZEN_CANDIDATE_ID)
    assert_frozen_config_fingerprint(candidate)
    return candidate


def assert_freeze_identity(*, freeze_token: str, candidate_id: str) -> None:
    if freeze_token != FREEZE_TOKEN:
        raise Aq7LockedHoldoutError(
            f"freeze_token mismatch: expected {FREEZE_TOKEN!r}, got {freeze_token!r}"
        )
    if candidate_id != FROZEN_CANDIDATE_ID:
        raise Aq7LockedHoldoutError(
            f"frozen candidate identity mismatch: expected {FROZEN_CANDIDATE_ID!r}, "
            f"got {candidate_id!r}"
        )


def resolve_evaluable_candidate(candidate_id: str) -> Aq7Candidate:
    if candidate_id in REJECTED_CANDIDATE_IDS:
        raise Aq7LockedHoldoutError(
            f"rejected CALIBRATION candidate is not authorized for locked holdout: "
            f"{candidate_id}"
        )
    if candidate_id != FROZEN_CANDIDATE_ID:
        raise Aq7LockedHoldoutError(
            f"candidate {candidate_id!r} is not authorized for locked holdout; "
            f"only {FROZEN_CANDIDATE_ID!r} is frozen"
        )
    return frozen_candidate()


def request_post_holdout_tuning(
    *, reason: str, proposed_candidate_id: str | None = None
) -> None:
    raise Aq7LockedHoldoutError(
        "post-holdout tuning is forbidden "
        f"(reason={reason!r}, proposed_candidate_id={proposed_candidate_id!r})"
    )


def same_identity_plane_deltas(metrics: Mapping[str, Any]) -> dict[str, Any]:
    """Candidate ≡ baseline → explicit zero deltas (no artificial challenger)."""
    out: dict[str, Any] = {"candidate_equals_baseline": True}
    for key, value in metrics.items():
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, (int, float)):
            delta_key = f"{key}_delta" if not key.endswith("_delta") else key
            if isinstance(value, float) or (isinstance(value, int) and not isinstance(value, bool)):
                if isinstance(value, float):
                    out[delta_key] = 0.0
                else:
                    out[delta_key] = 0
    # Always expose the primary keys expected by the gate contract.
    for key in (
        "precision_1bar",
        "recall_1bar",
        "macro_f1",
        "f1_1bar",
        "false_positive_count",
    ):
        delta_key = f"{key}_delta"
        if delta_key not in out:
            out[delta_key] = 0.0 if key != "false_positive_count" else 0
    return out


def test_holdout_firewall_block() -> dict[str, Any]:
    return {
        "post_reveal_tuning": False,
        "annotation_changes": False,
        "partition_changes": False,
        "tolerance_changes": False,
        "test_used_for_selection": False,
        "no_tuning_on_test": True,
        "evaluated_partition": EVALUATED_PARTITION,
        "selection_partition": None,
        "note": (
            "TEST/HOLDOUT is terminal evidence for this iteration; "
            "no feedback into selection or tuning."
        ),
    }


def assert_no_composite_quality_score(payload: Mapping[str, Any]) -> None:
    forbidden = ("aq7_composite", "global_score", "composite_quality")
    stack: list[Any] = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, Mapping):
            for key, value in node.items():
                if key in forbidden:
                    raise Aq7LockedHoldoutError(
                        f"composite quality score field is forbidden: {key}"
                    )
                stack.append(value)
        elif isinstance(node, list):
            stack.extend(node)


def resolve_plane_gate(*, plane: str, test_block: Mapping[str, Any]) -> dict[str, Any]:
    if plane not in PLANE_TOKENS:
        raise Aq7LockedHoldoutError(f"unknown plane: {plane}")
    n_fixtures = int(test_block.get("n_fixtures") or 0)
    n_usable = int(test_block.get("n_usable") or 0)
    n_hold = int(test_block.get("n_hold") or 0)
    n_unauthorized = int(test_block.get("n_unauthorized") or 0)
    coverage = test_block.get("coverage")
    metrics = dict(test_block.get("metrics") or {})
    hold_reasons = list(test_block.get("hold_reasons") or [])
    unauthorized_reasons = list(test_block.get("unauthorized_reasons") or [])
    provenance_ok = bool(test_block.get("provenance_ok", True))
    hold_records = list(test_block.get("hold_records") or [])
    difficult = list(test_block.get("difficult_slice_evidence") or [])

    authorized_holds = [
        reason for reason in hold_reasons if reason in AUTHORIZED_HOLD_REASONS
    ]
    unauthorized_holds = [
        reason
        for reason in (hold_reasons + unauthorized_reasons)
        if reason not in AUTHORIZED_HOLD_REASONS
    ]
    # Every TEST fixture must be accounted for as usable or authorized HOLD.
    accounted = n_usable + n_hold
    fixtures_fully_accounted = (
        n_fixtures == TEST_FIXTURE_COUNT
        and accounted == n_fixtures
        and n_unauthorized == 0
        and not unauthorized_holds
    )

    if not provenance_ok:
        outcome = "INCOMPLETE"
    elif unauthorized_holds or n_unauthorized > 0:
        outcome = "INCOMPLETE"
    elif n_fixtures < TEST_FIXTURE_COUNT or not fixtures_fully_accounted:
        outcome = "INCOMPLETE"
    elif n_hold > 0 and authorized_holds and n_usable >= 1:
        outcome = "HOLD"
    elif n_usable >= 1 and n_hold == 0 and (
        coverage is None or float(coverage) >= 1.0 - 1e-12
    ):
        outcome = "MEASURED"
    elif n_usable >= 1 and n_hold == 0:
        # Partial usable coverage without authorized HOLD reason.
        outcome = "INCOMPLETE"
    elif n_hold > 0 and authorized_holds and n_usable == 0:
        # Authorized HOLD only — still HOLD, not a fake MEASURED/PASS.
        outcome = "HOLD"
    else:
        outcome = "INCOMPLETE"

    return {
        "plane": plane,
        "frozen_config_identity": FROZEN_CANDIDATE_ID,
        "partition_identity": EVALUATED_PARTITION,
        "provenance": {
            "ok": provenance_ok,
            "freeze_token": FREEZE_TOKEN,
            "corpus_id": CORPUS_ID,
            "corpus_version": CORPUS_VERSION,
        },
        "n_fixtures": n_fixtures,
        "n_usable": n_usable,
        "n_hold": n_hold,
        "n_unauthorized": n_unauthorized,
        "coverage": coverage,
        "hold_reasons": hold_reasons,
        "unauthorized_reasons": unauthorized_reasons,
        "hold_records": hold_records,
        "baseline_metrics": metrics,
        "holdout_metrics": metrics,
        "regressions": same_identity_plane_deltas(metrics),
        "difficult_slice_evidence": difficult,
        "fixtures_fully_accounted": fixtures_fully_accounted,
        "outcome": outcome,
    }


def resolve_holdout_exit(
    *,
    gates: Mapping[str, Mapping[str, Any]],
    freeze_ok: bool,
    partition_complete: bool,
) -> str:
    if not freeze_ok or not partition_complete:
        return EXIT_INCOMPLETE
    outcomes = []
    for plane in PLANE_TOKENS:
        gate = gates.get(plane) or {}
        outcome = str(gate.get("outcome") or "INCOMPLETE")
        outcomes.append(outcome)
    if any(o == "INCOMPLETE" for o in outcomes):
        return EXIT_INCOMPLETE
    if any(o == "HOLD" for o in outcomes):
        return EXIT_PARTIAL_HOLD
    if all(o == "MEASURED" for o in outcomes):
        return EXIT_EVALUATED
    return EXIT_INCOMPLETE


def _assert_output_outside_repo(out: Path, root: Path) -> None:
    assert_work_dir_outside_repo(out.parent if out.parent != out else out, root)
    try:
        out.resolve().relative_to(root.resolve())
    except ValueError:
        return
    raise ValueError(f"output path must be outside repo: {out.resolve()}")


def _code_head_identity(repo_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    if completed.returncode != 0:
        return "unknown"
    sha = (completed.stdout or "").strip()
    return sha or "unknown"


def _runtime_block(boundary_rows: list[dict[str, Any]], role_rows: list[dict[str, Any]]) -> dict[str, Any]:
    times = [
        float(r["runtime_sec"])
        for r in boundary_rows + role_rows
        if r.get("runtime_sec") is not None
    ]
    return {
        "methodology": "docs/benchmarks/ANALYZER_RUNTIME_METHODOLOGY_V1.md",
        "by_reference": True,
        "methodology_v1_compliant": False,
        "diagnostic_only": True,
        "status": "diagnostic" if times else "unknown",
        "track_length_buckets": "HOLD",
        "n_timed_observations": len(times),
        "runtime_sec_median_diagnostic": (
            float(statistics.median(times)) if times else None
        ),
        "runtime_sec_p95_diagnostic": percentile(times, 95) if times else None,
    }


def _classify_fixture_rows(test_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Partition TEST rows into usable / authorized HOLD / unauthorized failure."""
    hold_rows: list[dict[str, Any]] = []
    usable_rows: list[dict[str, Any]] = []
    unauthorized_rows: list[dict[str, Any]] = []
    for row in test_rows:
        hold_kind = row.get("hold_kind")
        if hold_kind is None and row.get("prediction_usable", True):
            usable_rows.append(row)
        elif hold_kind in AUTHORIZED_HOLD_REASONS:
            hold_rows.append(row)
        else:
            unauthorized_rows.append(row)
    hold_reasons = sorted(
        {str(r.get("hold_kind")) for r in hold_rows if r.get("hold_kind")}
    )
    unauthorized_reasons = sorted(
        {
            str(r.get("hold_kind") or "UNACCOUNTED_FIXTURE_FAILURE")
            for r in unauthorized_rows
        }
    )
    return {
        "usable_rows": usable_rows,
        "hold_rows": hold_rows,
        "unauthorized_rows": unauthorized_rows,
        "hold_reasons": hold_reasons,
        "unauthorized_reasons": unauthorized_reasons,
    }


def _boundary_test_block(
    *,
    boundary_splits: Mapping[str, Any],
    boundary_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    test = (boundary_splits.get("TEST") or {}).get(BOUNDARY_PLANE) or {}
    metrics = dict(test.get("metrics") or {})
    test_rows = [r for r in boundary_rows if r.get("split") == "TEST"]
    classified = _classify_fixture_rows(test_rows)
    hold_rows = classified["hold_rows"]
    usable_rows = classified["usable_rows"]
    unauthorized_rows = classified["unauthorized_rows"]
    difficult = [
        {
            "fixture_id": r.get("fixture_id"),
            "family": r.get("family"),
            "hold_kind": r.get("hold_kind"),
            "precision_1bar": r.get("precision_1bar"),
            "recall_1bar": r.get("recall_1bar"),
            "false_positive_count": r.get("false_positive_count"),
        }
        for r in test_rows
    ]
    return {
        "n_fixtures": len(test_rows),
        "n_usable": len(usable_rows),
        "n_hold": len(hold_rows),
        "n_unauthorized": len(unauthorized_rows),
        "coverage": test.get("coverage"),
        "metrics": metrics,
        "hold_reasons": classified["hold_reasons"],
        "unauthorized_reasons": classified["unauthorized_reasons"],
        "hold_records": [
            {
                "fixture_id": r.get("fixture_id"),
                "family": r.get("family"),
                "reason": r.get("hold_kind"),
            }
            for r in hold_rows
        ]
        + [
            {
                "fixture_id": r.get("fixture_id"),
                "family": r.get("family"),
                "reason": r.get("hold_kind") or "UNACCOUNTED_FIXTURE_FAILURE",
                "authorized": False,
            }
            for r in unauthorized_rows
        ],
        "difficult_slice_evidence": difficult,
        "provenance_ok": True,
    }


def _role_drop_test_block(
    *,
    plane: str,
    role_drop_splits: Mapping[str, Any],
    role_drop_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    test_pack = role_drop_splits.get("TEST") or {}
    plane_block = dict(test_pack.get(plane) or {})
    test_rows = [r for r in role_drop_rows if r.get("split") == "TEST"]
    classified = _classify_fixture_rows(test_rows)
    hold_rows = classified["hold_rows"]
    usable_rows = classified["usable_rows"]
    unauthorized_rows = classified["unauthorized_rows"]
    if plane == ROLE_PLANE_TOKEN:
        metrics = {
            "macro_f1": plane_block.get("macro_f1"),
            "unknown_rate": plane_block.get("unknown_rate"),
            "support": plane_block.get("support"),
            "abstention_count": plane_block.get("abstention_count"),
            "unknown_reference_recall": plane_block.get("unknown_reference_recall"),
            "coverage": plane_block.get("coverage"),
        }
        difficult = [
            {
                "fixture_id": r.get("fixture_id"),
                "family": r.get("family"),
                "hold_kind": r.get("hold_kind"),
                "macro_f1": (r.get("role") or {}).get("macro_f1"),
            }
            for r in test_rows
        ]
        coverage = plane_block.get("coverage")
        if coverage is None and test_rows:
            coverage = len(usable_rows) / len(test_rows)
    else:
        metrics = {
            "f1_1bar": plane_block.get("f1_1bar"),
            "matched_count": plane_block.get("matched_count"),
            "false_positive_count": plane_block.get("false_positive_count"),
            "missed_count": plane_block.get("missed_count"),
            "coverage": plane_block.get("coverage"),
        }
        difficult = [
            {
                "fixture_id": r.get("fixture_id"),
                "family": r.get("family"),
                "hold_kind": r.get("hold_kind"),
                "f1_1bar": (r.get("drop_event") or {}).get("f1_1bar"),
                "false_positive_count": (r.get("drop_event") or {}).get(
                    "false_positive_count"
                ),
            }
            for r in test_rows
        ]
        coverage = plane_block.get("coverage")
        if coverage is None and test_rows:
            coverage = len(usable_rows) / len(test_rows)

    return {
        "n_fixtures": len(test_rows),
        "n_usable": len(usable_rows),
        "n_hold": len(hold_rows),
        "n_unauthorized": len(unauthorized_rows),
        "coverage": coverage,
        "metrics": metrics,
        "hold_reasons": classified["hold_reasons"],
        "unauthorized_reasons": classified["unauthorized_reasons"],
        "hold_records": [
            {
                "fixture_id": r.get("fixture_id"),
                "family": r.get("family"),
                "reason": r.get("hold_kind"),
            }
            for r in hold_rows
        ]
        + [
            {
                "fixture_id": r.get("fixture_id"),
                "family": r.get("family"),
                "reason": r.get("hold_kind") or "UNACCOUNTED_FIXTURE_FAILURE",
                "authorized": False,
            }
            for r in unauthorized_rows
        ],
        "difficult_slice_evidence": difficult,
        "provenance_ok": True,
    }


def assert_portable_holdout_payload(payload: Any) -> None:
    try:
        assert_portable_value(payload, field="aq7.structure_role_drop_locked_holdout")
    except AnalysisEvalArtifactError as exc:
        raise ValueError(str(exc)) from exc


def run_aq7_structure_role_drop_locked_holdout(
    *,
    work_dir: Path | str,
    output_path: Path | str,
    repo_root: Path | str | None = None,
    freeze_token: str = FREEZE_TOKEN,
    candidate_id: str = FROZEN_CANDIDATE_ID,
    regenerate_corpus: bool = True,
) -> dict[str, Any]:
    """Evaluate frozen baseline on locked TEST/HOLDOUT with separate plane gates."""
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT_DEFAULT
    work = Path(work_dir)
    out = Path(output_path)
    assert_work_dir_outside_repo(work, root)
    _assert_output_outside_repo(out, root)

    assert_freeze_identity(freeze_token=freeze_token, candidate_id=candidate_id)
    candidate = resolve_evaluable_candidate(candidate_id)

    _ = regenerate_corpus
    generate_aq7_structure_role_drop_corpus(work, repo_root=root)
    manifest = load_aq7_corpus_manifest(work / "manifest.json")
    if manifest.get("corpus_id") != CORPUS_ID:
        raise Aq7LockedHoldoutError("corpus_id mismatch against frozen #1024 identity")
    if manifest.get("corpus_version") != CORPUS_VERSION:
        raise Aq7LockedHoldoutError(
            "corpus_version mismatch against frozen #1024 identity"
        )

    boundary_rows: list[dict[str, Any]] = []
    role_drop_rows: list[dict[str, Any]] = []
    fixture_join_rows: list[dict[str, Any]] = []

    for item in manifest["fixtures"]:
        fixture_id = str(item["fixture_id"])
        gt = load_aq7_fixture_gt(work / "gt" / f"{fixture_id}.json")
        audio = work / "audio" / f"{fixture_id}.wav"
        row = predict_fixture_for_candidate(
            audio_path=audio, gt=gt, candidate=candidate
        )
        boundary_rows.append(row["boundary"])
        role_drop_rows.append(row["role_drop"])
        fixture_join_rows.append(
            {
                "candidate_id": candidate.candidate_id,
                "fixture_id": fixture_id,
                "split": gt["split"],
                "family": gt.get("family"),
                "boundary_hold_kind": row["boundary"].get("hold_kind"),
                "role_drop_hold_kind": row["role_drop"].get("hold_kind"),
                "boundary_precision_1bar": row["boundary"].get("precision_1bar"),
                "boundary_recall_1bar": row["boundary"].get("recall_1bar"),
                "role_macro_f1": (row["role_drop"].get("role") or {}).get("macro_f1"),
                "drop_f1_1bar": (row["role_drop"].get("drop_event") or {}).get(
                    "f1_1bar"
                ),
            }
        )

    boundary_splits = aggregate_boundary_splits(boundary_rows)
    role_drop_splits = aggregate_role_drop_splits(role_drop_rows)
    splits: dict[str, Any] = {}
    for split_name in ("CALIBRATION", "TEST"):
        splits[split_name] = {
            BOUNDARY_PLANE: (boundary_splits.get(split_name) or {}).get(BOUNDARY_PLANE),
            ROLE_PLANE_TOKEN: (role_drop_splits.get(split_name) or {}).get(
                ROLE_PLANE_TOKEN
            ),
            DROP_PLANE_TOKEN: (role_drop_splits.get(split_name) or {}).get(
                DROP_PLANE_TOKEN
            ),
            "n_fixtures": (role_drop_splits.get(split_name) or {}).get("n_fixtures"),
            "n_beatgrid_hold": (role_drop_splits.get(split_name) or {}).get(
                "n_beatgrid_hold"
            ),
        }

    test_fixture_count = int((splits.get("TEST") or {}).get("n_fixtures") or 0)
    partition_complete = test_fixture_count == TEST_FIXTURE_COUNT

    boundary_block = _boundary_test_block(
        boundary_splits=boundary_splits, boundary_rows=boundary_rows
    )
    role_block = _role_drop_test_block(
        plane=ROLE_PLANE_TOKEN,
        role_drop_splits=role_drop_splits,
        role_drop_rows=role_drop_rows,
    )
    drop_block = _role_drop_test_block(
        plane=DROP_PLANE_TOKEN,
        role_drop_splits=role_drop_splits,
        role_drop_rows=role_drop_rows,
    )

    gates = {
        BOUNDARY_PLANE: resolve_plane_gate(
            plane=BOUNDARY_PLANE, test_block=boundary_block
        ),
        ROLE_PLANE_TOKEN: resolve_plane_gate(
            plane=ROLE_PLANE_TOKEN, test_block=role_block
        ),
        DROP_PLANE_TOKEN: resolve_plane_gate(
            plane=DROP_PLANE_TOKEN, test_block=drop_block
        ),
    }

    exit_token = resolve_holdout_exit(
        gates=gates, freeze_ok=True, partition_complete=partition_complete
    )

    freeze_provenance = {
        "source_issue": 1028,
        "source_document_type": COMPARE_DOCUMENT_TYPE,
        "freeze_token": FREEZE_TOKEN,
        "frozen_candidate_id": FROZEN_CANDIDATE_ID,
        "frozen_outcome": "baseline_retention",
        "note": (
            "No justified CALIBRATION challenger; retain aq7.baseline.v1. "
            "Rejected adapters and H-AQ7-1027-03/04 remain non-evaluable here."
        ),
    }

    result: dict[str, Any] = {
        "document_type": DOCUMENT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "issue_id": ISSUE_ID,
        "aq7_slice": AQ7_SLICE,
        "corpus_id": CORPUS_ID,
        "corpus_version": CORPUS_VERSION,
        "generator_seed": GENERATOR_SEED,
        "frozen_candidate_id": FROZEN_CANDIDATE_ID,
        "frozen_config": candidate_public(candidate),
        "freeze_token": FREEZE_TOKEN,
        "freeze_provenance": freeze_provenance,
        "baseline_candidate_id": FROZEN_CANDIDATE_ID,
        "candidate_equals_baseline": CANDIDATE_EQUALS_BASELINE,
        "candidate_vs_baseline": {
            "candidate_id": FROZEN_CANDIDATE_ID,
            "baseline_id": FROZEN_CANDIDATE_ID,
            "candidate_equals_baseline": True,
            "note": (
                "#1028 kept baseline; locked holdout evaluates the same frozen "
                "identity — deltas are structurally zero, not invented gains."
            ),
        },
        "boundary_baseline_candidate_id": BOUNDARY_BASELINE_CANDIDATE_ID,
        "role_drop_baseline_candidate_id": ROLE_DROP_BASELINE_CANDIDATE_ID,
        "boundary_baseline_document_type": BOUNDARY_BASELINE_DOCUMENT_TYPE,
        "role_drop_baseline_document_type": ROLE_DROP_BASELINE_DOCUMENT_TYPE,
        "boundary_reference": BOUNDARY_CONTEXT_CANDIDATE_ID,
        "boundary_surface_policy": BOUNDARY_SURFACE_POLICY,
        "surfaces": {
            BOUNDARY_PLANE: STRUCTURE_SURFACE,
            ROLE_PLANE_TOKEN: ARRANGEMENT_SURFACE,
            DROP_PLANE_TOKEN: ARRANGEMENT_SURFACE,
            "section_signals": SECTION_SIGNAL_SURFACE,
        },
        "partition_policy": dict(PARTITION_POLICY),
        "evaluated_partition": EVALUATED_PARTITION,
        "no_tuning_on_test": True,
        "test_used_for_selection": False,
        "feature_toggle": FEATURE_TOGGLE,
        "production_defaults_changed": PRODUCTION_DEFAULTS_CHANGED,
        "algorithm_changed": False,
        "code_head_identity": _code_head_identity(root),
        "test_holdout_firewall": test_holdout_firewall_block(),
        "rejected_candidates_not_evaluated": sorted(REJECTED_CANDIDATE_IDS),
        "shortlist_not_promoted": ["H-AQ7-1027-03", "H-AQ7-1027-04"],
        "gates": gates,
        "splits": splits,
        "fixtures": fixture_join_rows,
        "determinism": {
            "methodology": "docs/ANALYZER_SEMANTIC_DETERMINISM_V1.md",
            "by_reference": True,
            "status": "unknown",
            "note": (
                "Harness is deterministic for the frozen baseline identity; "
                "repeat-run equality is validated in tests, not claimed from a "
                "single CLI invocation."
            ),
        },
        "runtime": _runtime_block(boundary_rows, role_drop_rows),
        "exit_status": exit_token,
        "exit_token": exit_token,
    }
    assert_no_composite_quality_score(result)
    assert_portable_holdout_payload(result)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate frozen AQ7 baseline on locked TEST/HOLDOUT and emit "
            "separate boundary/role/drop regression-gate evidence."
        )
    )
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--repo-root", default=None)
    parser.add_argument(
        "--freeze-token",
        default=FREEZE_TOKEN,
        help="Must match #1028 freeze token (fail closed otherwise).",
    )
    parser.add_argument(
        "--candidate-id",
        default=FROZEN_CANDIDATE_ID,
        help="Must be the frozen aq7.baseline.v1 identity (fail closed otherwise).",
    )
    parser.add_argument(
        "--no-regenerate",
        action="store_true",
        help="Ignored: corpus is always rewritten for identity proof.",
    )
    args = parser.parse_args(argv)
    result = run_aq7_structure_role_drop_locked_holdout(
        work_dir=args.work_dir,
        output_path=args.output,
        repo_root=args.repo_root,
        freeze_token=args.freeze_token,
        candidate_id=args.candidate_id,
        regenerate_corpus=not args.no_regenerate,
    )
    print(
        json.dumps(
            {
                "exit_status": result["exit_status"],
                "exit_token": result["exit_token"],
                "frozen_candidate_id": result["frozen_candidate_id"],
                "freeze_token": result["freeze_token"],
                "evaluated_partition": result["evaluated_partition"],
                "candidate_equals_baseline": result["candidate_equals_baseline"],
                "gates": {
                    plane: {"outcome": gate.get("outcome")}
                    for plane, gate in (result.get("gates") or {}).items()
                },
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if result["exit_status"] in {EXIT_EVALUATED, EXIT_PARTIAL_HOLD} else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "AQ7_SLICE",
    "AUTHORIZED_HOLD_REASONS",
    "CANDIDATE_EQUALS_BASELINE",
    "CORPUS_ID",
    "CORPUS_VERSION",
    "DOCUMENT_TYPE",
    "EVALUATED_PARTITION",
    "EXIT_EVALUATED",
    "EXIT_INCOMPLETE",
    "EXIT_PARTIAL_HOLD",
    "FEATURE_TOGGLE",
    "FREEZE_TOKEN",
    "FROZEN_ARRANGEMENT_CONFIG",
    "FROZEN_CANDIDATE_ID",
    "FROZEN_STRUCTURE_CONFIG",
    "GENERATOR_SEED",
    "ISSUE_ID",
    "PLANE_TOKENS",
    "PRODUCTION_DEFAULTS_CHANGED",
    "REJECTED_CANDIDATE_IDS",
    "SCHEMA_VERSION",
    "TEST_FIXTURE_COUNT",
    "Aq7LockedHoldoutError",
    "assert_freeze_identity",
    "assert_frozen_config_fingerprint",
    "assert_no_composite_quality_score",
    "assert_work_dir_outside_repo",
    "frozen_candidate",
    "request_post_holdout_tuning",
    "resolve_evaluable_candidate",
    "resolve_holdout_exit",
    "resolve_plane_gate",
    "run_aq7_structure_role_drop_locked_holdout",
    "same_identity_plane_deltas",
    "test_holdout_firewall_block",
]
