"""Frozen tests for AQ6 Harmonic Match theory correctness baseline (#1017).

TEST FREEZE: these assertions define the measurement harness contract. Fix the
baseline runner — not these expectations — when they turn red. Ranking
relevance (#1016) stays on a separate plane.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import aq6_harmonic_theory_baseline as baseline
from src import aq6_harmonic_theory_truth_table as theory


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = REPO_ROOT / theory.FIXTURE_RELPATH


def test_baseline_identity_constants_are_frozen() -> None:
    assert baseline.DOCUMENT_TYPE == "sample-brain.aq6.harmonic-theory-baseline.v1"
    assert baseline.SCHEMA_VERSION == "1.0.0"
    assert baseline.DOMAIN_TOKEN == "aq6.theory"
    assert baseline.EXIT_MEASURED == "AQ6_THEORY_BASELINE_MEASURED"
    assert baseline.EXIT_INCOMPLETE == "AQ6_THEORY_BASELINE_INCOMPLETE"
    assert baseline.SURFACE == "src.workbench_harmony.rate_harmony"
    assert baseline.TRUTH_TABLE_ID == theory.TRUTH_TABLE_ID
    assert baseline.RANKING_PLANE_NOTE.startswith("separate")


def test_product_prediction_maps_relation_and_compatibility() -> None:
    direct = baseline.product_prediction("Cmaj", "Cmaj")
    assert direct["relation"] == "direct"
    assert direct["compatibility"] == "compatible"
    assert direct["pitch_shift_semitones"] is None

    transpose = baseline.product_prediction("Cmaj", "Dmaj")
    assert transpose["relation"] == "transpose"
    assert transpose["compatibility"] == "compatible"
    assert transpose["pitch_shift_semitones"] == 2

    missing = baseline.product_prediction(None, "Cmaj")
    assert missing["relation"] == "uncertain"
    assert missing["compatibility"] == "uncertain"
    assert missing["pitch_shift_semitones"] is None

    modeful_incompatible = baseline.product_prediction("Cmaj", "F#maj")
    assert modeful_incompatible["relation"] == "uncertain"
    assert modeful_incompatible["compatibility"] == "incompatible"


def test_bucket_relation_errors_groups_by_expected_relation() -> None:
    cells = [
        {
            "cell_id": "ok_direct",
            "relation": "direct",
            "compatibility": "compatible",
            "pitch_shift_semitones": None,
        },
        {
            "cell_id": "bad_related",
            "relation": "related",
            "compatibility": "compatible",
            "pitch_shift_semitones": None,
        },
        {
            "cell_id": "bad_transpose",
            "relation": "transpose",
            "compatibility": "compatible",
            "pitch_shift_semitones": 2,
        },
    ]
    preds = {
        "ok_direct": {
            "relation": "direct",
            "compatibility": "compatible",
            "pitch_shift_semitones": None,
        },
        "bad_related": {
            "relation": "uncertain",
            "compatibility": "incompatible",
            "pitch_shift_semitones": None,
        },
        "bad_transpose": {
            "relation": "transpose",
            "compatibility": "compatible",
            "pitch_shift_semitones": 1,
        },
    }
    buckets = baseline.bucket_relation_errors(cells, preds)
    assert buckets["direct"]["errors"] == 0
    assert buckets["direct"]["support"] == 1
    assert buckets["related"]["errors"] == 1
    assert buckets["related"]["error_cell_ids"] == ["bad_related"]
    assert buckets["transpose"]["errors"] == 1
    assert "pitch_shift" in buckets["transpose"]["error_kinds"]
    assert buckets["uncertain"]["support"] == 0


def test_bpm_isolation_does_not_alter_theory_fields() -> None:
    cells = theory.load_truth_table_fixture(FIXTURE_PATH)["cells"][:12]
    result = baseline.prove_bpm_does_not_alter_relation(cells)
    assert result["cells_checked"] == 12
    assert result["relation_changed"] == 0
    assert result["compatibility_changed"] == 0
    assert result["pitch_shift_changed"] == 0
    assert result["theory_invariant_under_bpm"] is True
    # Ranking score may still move — that is allowed and recorded.
    assert "total_score_changed" in result


def test_repeatability_two_passes_match() -> None:
    doc = theory.load_truth_table_fixture(FIXTURE_PATH)
    repeat = baseline.measure_repeatability(doc["cells"])
    assert repeat["passes"] == 2
    assert repeat["predictions_identical"] is True
    assert repeat["scores_identical"] is True
    assert repeat["deterministic"] is True


def test_coverage_report_covers_roots_modes_and_evidence() -> None:
    doc = theory.load_truth_table_fixture(FIXTURE_PATH)
    preds = baseline.predict_all_cells(doc["cells"])
    coverage = baseline.coverage_report(doc, preds)
    assert coverage["cells_expected"] == 584
    assert coverage["cells_scored"] == 584
    assert coverage["modeful_pairs"] == 576
    assert coverage["evidence_edge_cases"] == 8
    assert coverage["roots_covered"] == list(theory.ROOTS)
    assert coverage["modes_covered"] == list(theory.MODES)
    assert coverage["missing_cell_ids"] == []
    assert coverage["complete"] is True


def test_run_rejects_output_inside_repo() -> None:
    inside = REPO_ROOT / ".pytest_aq6_theory_baseline_should_not_exist.json"
    with pytest.raises(ValueError, match="outside"):
        baseline.run_aq6_theory_baseline(
            output_path=inside,
            repo_root=REPO_ROOT,
        )


def test_run_writes_external_json_measured(tmp_path: Path) -> None:
    out = tmp_path / "aq6-theory-baseline.json"
    result = baseline.run_aq6_theory_baseline(
        output_path=out,
        repo_root=REPO_ROOT,
    )

    assert out.is_file()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["exit_status"] == baseline.EXIT_MEASURED
    assert loaded["document_type"] == baseline.DOCUMENT_TYPE
    assert loaded["domain"] == "aq6.theory"
    assert loaded["truth_table_id"] == theory.TRUTH_TABLE_ID
    assert "aq6.ranking" not in loaded.get("metrics", {})
    assert loaded["metrics"]["relation_classification_accuracy"] == 1.0
    assert loaded["metrics"]["incompatible_false_positive_rate"] == 0.0
    assert loaded["metrics"]["compatible_false_negative_rate"] == 0.0
    assert loaded["metrics"]["pitch_shift_suggestion_correctness"] == 1.0
    assert loaded["metrics"]["evidence_fail_closed_rate"] == 1.0
    assert loaded["metrics"]["transposition_invariance_violations"] == 0
    assert loaded["coverage"]["complete"] is True
    assert loaded["determinism"]["deterministic"] is True
    assert loaded["bpm_isolation"]["theory_invariant_under_bpm"] is True
    assert loaded["relation_error_buckets"]["direct"]["errors"] == 0
    assert loaded["relation_error_buckets"]["related"]["errors"] == 0
    assert loaded["relation_error_buckets"]["transpose"]["errors"] == 0
    assert loaded["relation_error_buckets"]["uncertain"]["errors"] == 0
    assert loaded["ranking_plane"]["mixed_into_theory"] is False
    assert result["exit_status"] == baseline.EXIT_MEASURED


def test_is_measured_requires_full_support() -> None:
    incomplete = {
        "coverage": {"complete": False, "cells_scored": 10, "cells_expected": 584},
        "metrics": {"relation_classification_accuracy": 1.0},
        "determinism": {"deterministic": True},
        "bpm_isolation": {"theory_invariant_under_bpm": True},
        "relation_error_buckets": {},
        "ranking_plane": {"mixed_into_theory": False},
    }
    assert baseline.is_measured(incomplete) is False

    complete = {
        "coverage": {
            "complete": True,
            "cells_scored": 584,
            "cells_expected": 584,
            "modeful_pairs": 576,
            "evidence_edge_cases": 8,
            "roots_covered": list(theory.ROOTS),
            "modes_covered": list(theory.MODES),
        },
        "metrics": {
            "relation_classification_accuracy": 1.0,
            "incompatible_false_positive_rate": 0.0,
            "compatible_false_negative_rate": 0.0,
            "pitch_shift_suggestion_correctness": 1.0,
            "evidence_fail_closed_rate": 1.0,
            "transposition_invariance_violations": 0,
            "counts": {"transpose": 1},
        },
        "determinism": {"deterministic": True, "passes": 2},
        "bpm_isolation": {"theory_invariant_under_bpm": True},
        "relation_error_buckets": {rel: {"errors": 0, "support": 1} for rel in theory.RELATIONS},
        "ranking_plane": {"mixed_into_theory": False},
    }
    assert baseline.is_measured(complete) is True
