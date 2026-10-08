"""Frozen tests for AQ7 StructureV1 boundary baseline harness (#1025).

TEST FREEZE: these assertions define the baseline eval contract. Fix the
harness, not these expectations, when they turn red.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import aq7_structure_boundary_baseline as baseline
from src import aq7_structure_role_drop_corpus as corpus
from src import aq7_structure_role_drop_schema as schema
from src.aq7_structure_role_drop_schema import BOUNDARY_MATCH_TOLERANCE_BARS


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_baseline_identity_constants_are_frozen() -> None:
    assert baseline.DOCUMENT_TYPE == "sample-brain.aq7.structure-boundary-baseline.v1"
    assert baseline.SCHEMA_VERSION == "1.0.0"
    assert baseline.CORPUS_ID == corpus.CORPUS_ID == schema.CORPUS_ID
    assert baseline.CANDIDATE_ID == "structure_v1.baseline.v1"
    assert baseline.EXIT_MEASURED == "AQ7_STRUCTURE_BOUNDARY_BASELINE_MEASURED"
    assert baseline.EXIT_PARTIAL_HOLD == "AQ7_STRUCTURE_BOUNDARY_BASELINE_PARTIAL_HOLD"
    assert baseline.EXIT_INCOMPLETE == "AQ7_STRUCTURE_BOUNDARY_BASELINE_INCOMPLETE"
    assert baseline.STRUCTURE_SURFACE == (
        "src.structure_v1.StructureV1Analyzer.analyze_path"
    )
    assert baseline.PLANE_TOKEN == "aq7.boundary"
    assert baseline.BOUNDARY_MATCH_TOLERANCE_BARS == BOUNDARY_MATCH_TOLERANCE_BARS == 1


def test_boundary_matching_uses_one_bar_tolerance_and_one_to_one() -> None:
    refs = [
        {"boundary_id": "r1", "bar_index": 16, "order": 0},
        {"boundary_id": "r2", "bar_index": 32, "order": 1},
    ]
    preds = [
        {"pred_id": "p1", "bar_index": 15, "order": 0},
        {"pred_id": "p2", "bar_index": 16, "order": 1},
        {"pred_id": "p3", "bar_index": 40, "order": 2},
    ]
    matched, missed, extras = baseline.match_boundaries_1bar(refs, preds)
    # Max matches (=1), then min total abs error → exact bar-16 pred wins over bar-15.
    assert len(matched) == 1
    assert matched[0]["ref_id"] == "r1"
    assert matched[0]["pred_id"] == "p2"
    assert matched[0]["abs_error_bars"] == 0
    assert [m["boundary_id"] for m in missed] == ["r2"]
    assert [e["pred_id"] for e in extras] == ["p1", "p3"]


def test_boundary_matching_maximizes_pairs_then_minimizes_total_error() -> None:
    refs = [
        {"boundary_id": "r1", "bar_index": 10, "order": 0},
        {"boundary_id": "r2", "bar_index": 20, "order": 1},
    ]
    preds = [
        {"pred_id": "p1", "bar_index": 10, "order": 0},
        {"pred_id": "p2", "bar_index": 20, "order": 1},
    ]
    matched, missed, extras = baseline.match_boundaries_1bar(refs, preds)
    assert len(matched) == 2
    assert missed == []
    assert extras == []
    assert sum(m["abs_error_bars"] for m in matched) == 0


def test_exact_early_late_offsets_visible_on_matched_pairs() -> None:
    refs = [{"boundary_id": "r1", "bar_index": 16, "order": 0}]
    early = [{"pred_id": "p1", "bar_index": 15, "order": 0}]
    late = [{"pred_id": "p1", "bar_index": 17, "order": 0}]
    exact = [{"pred_id": "p1", "bar_index": 16, "order": 0}]
    m_early, _, _ = baseline.match_boundaries_1bar(refs, early)
    m_late, _, _ = baseline.match_boundaries_1bar(refs, late)
    m_exact, _, _ = baseline.match_boundaries_1bar(refs, exact)
    assert m_early[0]["signed_error_bars"] == -1
    assert m_late[0]["signed_error_bars"] == 1
    assert m_exact[0]["abs_error_bars"] == 0
    assert m_exact[0]["signed_error_bars"] == 0


def test_ignore_mask_excludes_ambiguous_locus_from_fp_and_matching() -> None:
    refs = [
        {
            "boundary_id": "amb",
            "bar_index": 16,
            "order": 0,
            "annotation_status": "ambiguous",
        },
        {
            "boundary_id": "ok",
            "bar_index": 32,
            "order": 1,
            "annotation_status": "single_source",
        },
    ]
    preds = [
        {"pred_id": "near_amb", "bar_index": 16, "order": 0},
        {"pred_id": "hit", "bar_index": 32, "order": 1},
    ]
    scored = baseline.score_fixture_boundaries(
        refs,
        preds,
        track_end_bar=48,
        plane_status="single_source",
    )
    assert scored["eligible_ref_count"] == 1
    assert scored["matched_count"] == 1
    assert scored["false_positive_count"] == 0
    assert scored["missed_count"] == 0
    assert scored["ignore_masks"] == [{"lo": 15, "hi": 17, "source_bar": 16}]


def test_reference_boundaries_never_from_structure_v1_output() -> None:
    gt = {
        "boundaries": [
            {
                "boundary_id": "b1",
                "bar_index": 8,
                "annotation_status": "single_source",
            }
        ],
        "sections": [
            {"section_id": "s0", "start_bar": 0, "end_bar": 8, "role": "intro"},
            {"section_id": "s1", "start_bar": 8, "end_bar": 16, "role": "outro"},
        ],
        "plane_status": {"aq7.boundary": "single_source"},
        "beatgrid_provenance": {"status": "authored_synthetic"},
    }
    refs = baseline.reference_boundaries_from_gt(gt)
    assert refs[0]["bar_index"] == 8
    assert refs[0]["boundary_id"] == "b1"
    preds = [{"pred_id": "p", "bar_index": 99, "order": 0}]
    assert baseline.reference_boundaries_from_gt(gt)[0]["bar_index"] == 8
    assert preds[0]["bar_index"] != refs[0]["bar_index"]


def test_role_labels_do_not_enter_boundary_scoring_inputs() -> None:
    gt = {
        "boundaries": [
            {
                "boundary_id": "b1",
                "bar_index": 16,
                "annotation_status": "single_source",
            }
        ],
        "sections": [
            {
                "section_id": "s0",
                "start_bar": 0,
                "end_bar": 16,
                "role": "drop",
                "annotation_status": "single_source",
            },
            {
                "section_id": "s1",
                "start_bar": 16,
                "end_bar": 32,
                "role": "build",
                "annotation_status": "single_source",
            },
        ],
        "plane_status": {"aq7.boundary": "single_source", "aq7.role": "single_source"},
        "beatgrid_provenance": {"status": "authored_synthetic"},
    }
    refs = baseline.reference_boundaries_from_gt(gt)
    assert "role" not in refs[0]
    scored = baseline.score_fixture_boundaries(
        refs,
        [{"pred_id": "p1", "bar_index": 16, "order": 0}],
        track_end_bar=32,
        plane_status="single_source",
    )
    assert "role_metrics" not in scored
    assert scored["plane"] == "aq7.boundary"


def test_over_under_segmentation_and_section_count_error_visible() -> None:
    refs = [
        {
            "boundary_id": "r1",
            "bar_index": 8,
            "order": 0,
            "annotation_status": "single_source",
        },
        {
            "boundary_id": "r2",
            "bar_index": 16,
            "order": 1,
            "annotation_status": "single_source",
        },
        {
            "boundary_id": "r3",
            "bar_index": 24,
            "order": 2,
            "annotation_status": "single_source",
        },
    ]
    under_preds = [{"pred_id": "p1", "bar_index": 8, "order": 0}]
    over_preds = [
        {"pred_id": f"p{i}", "bar_index": bar, "order": i}
        for i, bar in enumerate([4, 8, 12, 16, 20, 24])
    ]
    under = baseline.score_fixture_boundaries(
        refs, under_preds, track_end_bar=32, plane_status="single_source"
    )
    over = baseline.score_fixture_boundaries(
        refs, over_preds, track_end_bar=32, plane_status="single_source"
    )
    assert under["segmentation"]["under_segmentation"] is True
    assert under["segmentation"]["over_segmentation"] is False
    assert under["segmentation"]["section_count_abs_error"] == 2
    assert over["segmentation"]["over_segmentation"] is True
    assert over["segmentation"]["section_count_abs_error"] == 3


def test_segment_iou_uses_half_open_bar_ranges() -> None:
    refs = [
        {
            "boundary_id": "r1",
            "bar_index": 16,
            "order": 0,
            "annotation_status": "single_source",
        }
    ]
    preds = [{"pred_id": "p1", "bar_index": 16, "order": 0}]
    scored = baseline.score_fixture_boundaries(
        refs, preds, track_end_bar=32, plane_status="single_source"
    )
    assert scored["segmentation"]["segment_iou_weighted"] == pytest.approx(1.0)


def test_empty_prediction_no_boundary_candidate_is_usable_empty_surface() -> None:
    refs = [
        {
            "boundary_id": "r1",
            "bar_index": 16,
            "order": 0,
            "annotation_status": "single_source",
        }
    ]
    scored = baseline.score_fixture_boundaries(
        refs,
        [],
        track_end_bar=32,
        plane_status="single_source",
        prediction_usable=True,
        prediction_status="no_result",
        reason_code="NO_BOUNDARY_CANDIDATE",
    )
    assert scored["prediction_usable"] is True
    assert scored["precision_1bar"] is None
    assert scored["recall_1bar"] == pytest.approx(0.0)
    assert scored["missed_count"] == 1
    assert scored["false_positive_count"] == 0


def test_downbeats_unavailable_is_hold_not_fabricated_zero() -> None:
    refs = [
        {
            "boundary_id": "r1",
            "bar_index": 16,
            "order": 0,
            "annotation_status": "single_source",
        }
    ]
    scored = baseline.score_fixture_boundaries(
        refs,
        [],
        track_end_bar=32,
        plane_status="single_source",
        prediction_usable=False,
        prediction_status="no_result",
        reason_code="DOWNBEATS_UNAVAILABLE",
    )
    assert scored["prediction_usable"] is False
    assert scored["evidence_status"] == "unknown"
    assert scored["precision_1bar"] is None
    assert scored["recall_1bar"] is None
    assert scored["matched_count"] is None


def test_beatgrid_missing_fixture_is_provenance_hold() -> None:
    row = baseline.evaluate_prediction_surface(
        structure_status=None,
        reason_code=None,
        beatgrid_status="missing",
        analyzer_ran=False,
    )
    assert row["prediction_usable"] is False
    assert row["hold_kind"] == "BEATGRID_PROVENANCE_LIMITATION"
    assert row["evidence_status"] == "unknown"


def test_median_and_p95_use_measurement_percentile() -> None:
    summary = baseline.error_summary_bars([0, 1, 1, 1])
    assert summary["median"] == pytest.approx(1.0)
    assert summary["p95"] is not None
    assert summary["n"] == 4
    empty = baseline.error_summary_bars([])
    assert empty["median"] is None
    assert empty["p95"] is None
    assert empty["status"] == "not_applicable"


def test_aggregate_keeps_calibration_and_test_separate() -> None:
    fixture_rows = [
        {
            "fixture_id": "cal-1",
            "split": "CALIBRATION",
            "family": "simple_clean",
            "boundary_eligible": True,
            "prediction_usable": True,
            "matched_count": 1,
            "eligible_ref_count": 1,
            "pred_count_unmasked": 1,
            "false_positive_count": 0,
            "missed_count": 0,
            "exact_match_count": 1,
            "abs_errors_bars": [0],
            "section_count_abs_error": 0,
            "over_segmentation": False,
            "under_segmentation": False,
            "segment_iou_weight_sum": 16.0,
            "segment_iou_weighted_numer": 16.0,
            "evidence_status": "measured",
            "hold_kind": None,
        },
        {
            "fixture_id": "test-1",
            "split": "TEST",
            "family": "drop_at_boundary",
            "boundary_eligible": True,
            "prediction_usable": True,
            "matched_count": 0,
            "eligible_ref_count": 2,
            "pred_count_unmasked": 1,
            "false_positive_count": 1,
            "missed_count": 2,
            "exact_match_count": 0,
            "abs_errors_bars": [],
            "section_count_abs_error": 1,
            "over_segmentation": False,
            "under_segmentation": True,
            "segment_iou_weight_sum": 32.0,
            "segment_iou_weighted_numer": 0.0,
            "evidence_status": "measured",
            "hold_kind": None,
        },
    ]
    splits = baseline.aggregate_boundary_splits(fixture_rows)
    assert "CALIBRATION" in splits and "TEST" in splits
    assert splits["CALIBRATION"]["aq7.boundary"]["metrics"]["recall_1bar"] == pytest.approx(
        1.0
    )
    assert splits["TEST"]["aq7.boundary"]["metrics"]["recall_1bar"] == pytest.approx(0.0)


def test_resolve_exit_partial_hold_when_beatgrid_limits_block_some_claims() -> None:
    splits = {
        "CALIBRATION": {
            "aq7.boundary": {
                "n_boundary_eligible": 5,
                "n_usable": 5,
                "metrics": {"f1_1bar": 0.5, "support": 8},
            }
        },
        "TEST": {
            "aq7.boundary": {
                "n_boundary_eligible": 3,
                "n_usable": 2,
                "metrics": {"f1_1bar": 0.4, "support": 4},
                "n_beatgrid_hold": 1,
            }
        },
    }
    assert (
        baseline.resolve_exit_status(
            splits=splits,
            fixture_rows=[{"fixture_id": f"f{i}"} for i in range(10)],
            has_beatgrid_hold=True,
        )
        == baseline.EXIT_PARTIAL_HOLD
    )


def test_resolve_exit_measured_when_both_partitions_fully_usable() -> None:
    splits = {
        "CALIBRATION": {
            "aq7.boundary": {
                "n_boundary_eligible": 5,
                "n_usable": 5,
                "metrics": {"f1_1bar": 0.5, "support": 8},
            }
        },
        "TEST": {
            "aq7.boundary": {
                "n_boundary_eligible": 3,
                "n_usable": 3,
                "metrics": {"f1_1bar": 0.4, "support": 4},
                "n_beatgrid_hold": 0,
            }
        },
    }
    assert (
        baseline.resolve_exit_status(
            splits=splits,
            fixture_rows=[{"fixture_id": f"f{i}"} for i in range(10)],
            has_beatgrid_hold=False,
        )
        == baseline.EXIT_MEASURED
    )


def test_portable_output_rejects_absolute_host_paths(tmp_path: Path) -> None:
    payload = {
        "document_type": baseline.DOCUMENT_TYPE,
        "fixture_id": "aq7-synth-simple-clean-cal-001",
        "bad_path": str(tmp_path / "secret" / "file.wav"),
    }
    with pytest.raises(ValueError, match="portable|path|absolute|Host"):
        baseline.assert_portable_baseline_payload(payload)


def test_end_to_end_baseline_consumes_frozen_corpus_identity(
    tmp_path: Path,
) -> None:
    # tmp_path is outside the git checkout on CI and local pytest runs.
    work = tmp_path / "aq7-1025-baseline"
    out = work / "baseline.json"
    result = baseline.run_aq7_structure_boundary_baseline(
        work_dir=work / "corpus",
        output_path=out,
        repo_root=REPO_ROOT,
    )
    assert result["corpus_id"] == corpus.CORPUS_ID
    assert result["corpus_version"] == corpus.CORPUS_VERSION
    assert result["candidate_id"] == baseline.CANDIDATE_ID
    assert result["plane"] == "aq7.boundary"
    assert "aq7.role" not in result["splits"]["CALIBRATION"]
    assert "aq7.drop_event" not in result["splits"]["CALIBRATION"]
    assert result["no_tuning_on_test"] is True
    assert result["algorithm_changed"] is False
    assert result["exit_status"] in {
        baseline.EXIT_MEASURED,
        baseline.EXIT_PARTIAL_HOLD,
    }
    assert len(result["fixtures"]) == 10
    again = baseline.run_aq7_structure_boundary_baseline(
        work_dir=work / "corpus",
        output_path=work / "baseline2.json",
        repo_root=REPO_ROOT,
        regenerate_corpus=False,
        prior_semantic=baseline.semantic_projection(result),
    )
    assert again["determinism"]["semantic_equal"] is True
    assert (
        again["splits"]["CALIBRATION"]["aq7.boundary"]["metrics"]
        == result["splits"]["CALIBRATION"]["aq7.boundary"]["metrics"]
    )
    assert (
        again["splits"]["TEST"]["aq7.boundary"]["metrics"]
        == result["splits"]["TEST"]["aq7.boundary"]["metrics"]
    )
    raw = json.loads(out.read_text(encoding="utf-8"))
    dumped = json.dumps(raw)
    assert "D:/" not in dumped
    assert "C:\\Users" not in dumped


def test_arrangement_classifier_is_not_imported_by_baseline_module() -> None:
    import src.aq7_structure_boundary_baseline as mod

    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert "arrangement_classifier" not in source
    assert "ArrangementClassifier" not in source
