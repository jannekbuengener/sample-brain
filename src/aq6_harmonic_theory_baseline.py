"""AQ6 Harmonic Match theory correctness baseline (#1017).

Measures current ``rate_harmony`` / relation classification against the frozen
#1015 truth table + KPI contract. Theory plane only — ranking relevance (#1016)
stays separate. No production switch. External JSON evidence only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .aq6_harmonic_theory_truth_table import (
    DOMAIN_TOKEN as THEORY_DOMAIN_TOKEN,
    FIXTURE_RELPATH,
    RELATIONS,
    ROOTS,
    MODES,
    TRUTH_TABLE_ID,
    TRUTH_TABLE_VERSION,
    load_truth_table_fixture,
    score_theory_predictions,
)
from .key_signature import parse_key_signature
from .workbench_controller import WorkbenchRow
from .workbench_harmony import rate_harmony

DOCUMENT_TYPE = "sample-brain.aq6.harmonic-theory-baseline.v1"
SCHEMA_VERSION = "1.0.0"
DOMAIN_TOKEN = THEORY_DOMAIN_TOKEN
EXIT_MEASURED = "AQ6_THEORY_BASELINE_MEASURED"
EXIT_INCOMPLETE = "AQ6_THEORY_BASELINE_INCOMPLETE"
SURFACE = "src.workbench_harmony.rate_harmony"
RANKING_PLANE_NOTE = (
    "separate plane — aq6.ranking (#1016) must not rewrite or excuse theory cells"
)

_REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[1]

# BPM pairs used only to prove ranking score does not alter theory fields.
_BPM_BASELINE = (128.0, 128.0)
_BPM_PERTURBED = (90.0, 140.0)


def _row(
    name: str,
    *,
    key: str | None,
    bpm: float | None = 128.0,
) -> WorkbenchRow:
    return WorkbenchRow(
        display_name=name,
        relative_path=f"{name}.wav",
        path=f"/synthetic/aq6-theory-baseline/{name}.wav",
        bpm=bpm,
        key=key,
        key_conf=0.8 if key else None,
        loudness=-20.0,
        brightness=2000.0,
        sample_class="loop",
        pred_type="kick",
        status="ok",
    )


def product_prediction(
    source_key: str | None,
    target_key: str | None,
    *,
    ref_bpm: float | None = 128.0,
    cand_bpm: float | None = 128.0,
) -> dict[str, Any]:
    """Map live product ``rate_harmony`` output onto theory prediction fields."""
    suggestion = rate_harmony(
        _row("ref", key=source_key, bpm=ref_bpm),
        _row("cand", key=target_key, bpm=cand_bpm),
    )
    relation = suggestion.relation.value
    if relation in {"direct", "related", "transpose"}:
        compatibility = "compatible"
    else:
        source_parsed = parse_key_signature(source_key) if source_key else None
        target_parsed = parse_key_signature(target_key) if target_key else None
        modeful = (
            source_parsed is not None
            and target_parsed is not None
            and source_parsed.mode is not None
            and target_parsed.mode is not None
        )
        compatibility = "incompatible" if modeful else "uncertain"
    return {
        "relation": relation,
        "compatibility": compatibility,
        "pitch_shift_semitones": suggestion.pitch_shift_semitones,
        "harmony_score": suggestion.harmony_score,
        "bpm_score": suggestion.bpm_score,
        "total_score": suggestion.total_score,
    }


def predict_all_cells(
    cells: Sequence[Mapping[str, Any]],
    *,
    ref_bpm: float | None = 128.0,
    cand_bpm: float | None = 128.0,
) -> dict[str, dict[str, Any]]:
    """Predict theory fields for every truth-table cell via product path."""
    predictions: dict[str, dict[str, Any]] = {}
    for cell in cells:
        predictions[str(cell["cell_id"])] = product_prediction(
            cell.get("source_key"),
            cell.get("target_key"),
            ref_bpm=ref_bpm,
            cand_bpm=cand_bpm,
        )
    return predictions


def _theory_fields(pred: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "relation": pred.get("relation"),
        "compatibility": pred.get("compatibility"),
        "pitch_shift_semitones": pred.get("pitch_shift_semitones"),
    }


def bucket_relation_errors(
    expected_cells: Sequence[Mapping[str, Any]],
    predicted_by_cell_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Bucket prediction mismatches by frozen expected relation label."""
    buckets: dict[str, Any] = {
        rel: {
            "support": 0,
            "errors": 0,
            "error_cell_ids": [],
            "error_kinds": {
                "relation": 0,
                "compatibility": 0,
                "pitch_shift": 0,
            },
        }
        for rel in RELATIONS
    }
    for expected in expected_cells:
        cell_id = str(expected["cell_id"])
        rel = str(expected["relation"])
        if rel not in buckets:
            continue
        pred = predicted_by_cell_id.get(cell_id)
        if pred is None:
            continue
        buckets[rel]["support"] += 1
        relation_mismatch = pred.get("relation") != expected["relation"]
        compatibility_mismatch = pred.get("compatibility") != expected["compatibility"]
        pitch_mismatch = pred.get("pitch_shift_semitones") != expected[
            "pitch_shift_semitones"
        ]
        if relation_mismatch or compatibility_mismatch or pitch_mismatch:
            buckets[rel]["errors"] += 1
            buckets[rel]["error_cell_ids"].append(cell_id)
            if relation_mismatch:
                buckets[rel]["error_kinds"]["relation"] += 1
            if compatibility_mismatch:
                buckets[rel]["error_kinds"]["compatibility"] += 1
            if pitch_mismatch:
                buckets[rel]["error_kinds"]["pitch_shift"] += 1
    return buckets


def prove_bpm_does_not_alter_relation(
    cells: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Prove BPM / ranking score perturbation leaves theory fields unchanged."""
    base = predict_all_cells(
        cells, ref_bpm=_BPM_BASELINE[0], cand_bpm=_BPM_BASELINE[1]
    )
    perturbed = predict_all_cells(
        cells, ref_bpm=_BPM_PERTURBED[0], cand_bpm=_BPM_PERTURBED[1]
    )
    relation_changed = 0
    compatibility_changed = 0
    pitch_shift_changed = 0
    total_score_changed = 0
    for cell_id, base_pred in base.items():
        other = perturbed[cell_id]
        if base_pred["relation"] != other["relation"]:
            relation_changed += 1
        if base_pred["compatibility"] != other["compatibility"]:
            compatibility_changed += 1
        if base_pred["pitch_shift_semitones"] != other["pitch_shift_semitones"]:
            pitch_shift_changed += 1
        if base_pred.get("total_score") != other.get("total_score"):
            total_score_changed += 1
    theory_ok = (
        relation_changed == 0
        and compatibility_changed == 0
        and pitch_shift_changed == 0
    )
    return {
        "cells_checked": len(cells),
        "bpm_baseline": list(_BPM_BASELINE),
        "bpm_perturbed": list(_BPM_PERTURBED),
        "relation_changed": relation_changed,
        "compatibility_changed": compatibility_changed,
        "pitch_shift_changed": pitch_shift_changed,
        "total_score_changed": total_score_changed,
        "theory_invariant_under_bpm": theory_ok,
        "note": (
            "BPM may change total_score (ranking-adjacent); theory relation/"
            "compatibility/pitch_shift must stay identical"
        ),
    }


def measure_repeatability(
    cells: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Two identical passes — consume #959 semantic determinism by reference."""
    first = predict_all_cells(cells)
    second = predict_all_cells(cells)
    first_theory = {cid: _theory_fields(p) for cid, p in first.items()}
    second_theory = {cid: _theory_fields(p) for cid, p in second.items()}
    scores_a = score_theory_predictions(cells, first_theory)
    scores_b = score_theory_predictions(cells, second_theory)
    predictions_identical = first_theory == second_theory
    scores_identical = scores_a == scores_b
    return {
        "passes": 2,
        "predictions_identical": predictions_identical,
        "scores_identical": scores_identical,
        "deterministic": predictions_identical and scores_identical,
        "reference": "#959 / docs/ANALYZER_SEMANTIC_DETERMINISM_V1.md",
    }


def coverage_report(
    document: Mapping[str, Any],
    predictions: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    cells = list(document["cells"])
    expected_ids = {str(c["cell_id"]) for c in cells}
    scored_ids = set(predictions.keys()) & expected_ids
    missing = sorted(expected_ids - scored_ids)
    modeful = [c for c in cells if c.get("evidence_state") == "modeful"]
    evidence = [
        c for c in cells if str(c.get("cell_id", "")).startswith("evidence:")
    ]
    roots = sorted(
        {
            c["source_root"]
            for c in modeful
            if c.get("source_root") is not None
        }
        | {
            c["target_root"]
            for c in modeful
            if c.get("target_root") is not None
        }
    )
    modes = sorted(
        {
            c["source_mode"]
            for c in modeful
            if c.get("source_mode") is not None
        }
        | {
            c["target_mode"]
            for c in modeful
            if c.get("target_mode") is not None
        }
    )
    # Preserve canonical ROOTS/MODES order when complete.
    roots_covered = list(ROOTS) if set(roots) == set(ROOTS) else roots
    modes_covered = list(MODES) if set(modes) == set(MODES) else modes
    complete = (
        len(missing) == 0
        and len(scored_ids) == len(cells)
        and len(modeful) == 576
        and len(evidence) == 8
        and roots_covered == list(ROOTS)
        and modes_covered == list(MODES)
    )
    return {
        "cells_expected": len(cells),
        "cells_scored": len(scored_ids),
        "modeful_pairs": len(modeful),
        "evidence_edge_cases": len(evidence),
        "roots_covered": roots_covered,
        "modes_covered": modes_covered,
        "missing_cell_ids": missing,
        "complete": complete,
    }


def is_measured(result: Mapping[str, Any]) -> bool:
    """Return True when measurement meets #1017 acceptance completeness."""
    coverage = result.get("coverage") or {}
    metrics = result.get("metrics") or {}
    determinism = result.get("determinism") or {}
    bpm_isolation = result.get("bpm_isolation") or {}
    buckets = result.get("relation_error_buckets") or {}
    ranking = result.get("ranking_plane") or {}

    required_metrics = (
        "relation_classification_accuracy",
        "incompatible_false_positive_rate",
        "compatible_false_negative_rate",
        "pitch_shift_suggestion_correctness",
        "evidence_fail_closed_rate",
        "transposition_invariance_violations",
    )
    if not coverage.get("complete"):
        return False
    if coverage.get("cells_scored") != coverage.get("cells_expected"):
        return False
    if coverage.get("modeful_pairs") != 576:
        return False
    if coverage.get("evidence_edge_cases") != 8:
        return False
    if coverage.get("roots_covered") != list(ROOTS):
        return False
    if coverage.get("modes_covered") != list(MODES):
        return False
    for key in required_metrics:
        if key not in metrics:
            return False
    if not determinism.get("deterministic"):
        return False
    if determinism.get("passes", 0) < 2:
        return False
    if not bpm_isolation.get("theory_invariant_under_bpm"):
        return False
    for rel in RELATIONS:
        if rel not in buckets:
            return False
        if "errors" not in buckets[rel] or "support" not in buckets[rel]:
            return False
    if ranking.get("mixed_into_theory") is not False:
        return False
    return True


def _assert_output_outside_repo(output_path: Path, root: Path) -> None:
    resolved = output_path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return
    raise ValueError(f"output path must be outside repo: {resolved}")


def run_aq6_theory_baseline(
    *,
    output_path: Path | str,
    repo_root: Path | str | None = None,
    fixture_path: Path | str | None = None,
) -> dict[str, Any]:
    """Score current product harmony against frozen truth table; write JSON."""
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT_DEFAULT
    out = Path(output_path)
    _assert_output_outside_repo(out, root)

    fixture = Path(fixture_path) if fixture_path is not None else root / FIXTURE_RELPATH
    document = load_truth_table_fixture(fixture)
    cells = list(document["cells"])

    predictions_full = predict_all_cells(cells)
    theory_preds = {cid: _theory_fields(p) for cid, p in predictions_full.items()}
    metrics = score_theory_predictions(cells, theory_preds)
    coverage = coverage_report(document, theory_preds)
    error_buckets = bucket_relation_errors(cells, theory_preds)
    determinism = measure_repeatability(cells)
    bpm_isolation = prove_bpm_does_not_alter_relation(cells)

    # Sanitize: never embed absolute host paths; omit full prediction dump of paths.
    mismatch_cell_ids = [
        cid
        for bucket in error_buckets.values()
        for cid in bucket["error_cell_ids"]
    ]

    draft: dict[str, Any] = {
        "document_type": DOCUMENT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "domain": DOMAIN_TOKEN,
        "truth_table_id": TRUTH_TABLE_ID,
        "truth_table_version": document.get(
            "truth_table_version", TRUTH_TABLE_VERSION
        ),
        "surface": SURFACE,
        "fixture_relpath": str(FIXTURE_RELPATH).replace("\\", "/"),
        "coverage": coverage,
        "metrics": metrics,
        "relation_error_buckets": error_buckets,
        "mismatch_cell_ids": mismatch_cell_ids,
        "determinism": determinism,
        "bpm_isolation": bpm_isolation,
        "ranking_plane": {
            "token": "aq6.ranking",
            "mixed_into_theory": False,
            "note": RANKING_PLANE_NOTE,
            "issue_ref": "#1016",
        },
        "non_goals_honored": [
            "no_ranking_weight_tuning",
            "no_ui_qml",
            "no_key_bpm_detector_changes",
            "no_ml_embeddings",
            "no_private_audio",
            "no_production_switch",
        ],
        "parents": ["#948", "#942", "#1015"],
        "issue": "#1017",
    }
    draft["exit_status"] = (
        EXIT_MEASURED if is_measured(draft) else EXIT_INCOMPLETE
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(draft, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return draft


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Measure AQ6 Harmonic Match theory correctness against the frozen "
            "truth table (#1017)."
        )
    )
    parser.add_argument(
        "--output",
        required=True,
        help="External JSON output path (outside repo).",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repository root used for outside-repo checks (default: package root).",
    )
    parser.add_argument(
        "--fixture",
        default=None,
        help="Optional truth-table fixture path (default: frozen repo fixture).",
    )
    args = parser.parse_args(argv)
    result = run_aq6_theory_baseline(
        output_path=args.output,
        repo_root=args.repo_root,
        fixture_path=args.fixture,
    )
    print(
        json.dumps(
            {
                "exit_status": result["exit_status"],
                "cells_scored": result["coverage"]["cells_scored"],
                "relation_classification_accuracy": result["metrics"][
                    "relation_classification_accuracy"
                ],
            }
        )
    )
    return 0 if result["exit_status"] == EXIT_MEASURED else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DOCUMENT_TYPE",
    "DOMAIN_TOKEN",
    "EXIT_INCOMPLETE",
    "EXIT_MEASURED",
    "RANKING_PLANE_NOTE",
    "SCHEMA_VERSION",
    "SURFACE",
    "TRUTH_TABLE_ID",
    "bucket_relation_errors",
    "coverage_report",
    "is_measured",
    "measure_repeatability",
    "product_prediction",
    "predict_all_cells",
    "prove_bpm_does_not_alter_relation",
    "run_aq6_theory_baseline",
]
