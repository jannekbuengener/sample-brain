"""Frozen tests for AQ7 role/drop baseline harness (#1026).

TEST FREEZE: these assertions define the role/drop eval contract. Task 3 must
fix the new harness module, not weaken these tests.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from src import aq7_structure_boundary_baseline as boundary_baseline
from src import aq7_structure_role_drop_corpus as corpus
from src import aq7_structure_role_drop_schema as schema


def _baseline():
    return importlib.import_module("src.aq7_structure_role_drop_baseline")


def _gt() -> dict:
    return {
        "document_type": corpus.DOCUMENT_TYPE,
        "corpus_id": corpus.CORPUS_ID,
        "corpus_version": corpus.CORPUS_VERSION,
        "generator_id": corpus.GENERATOR_ID,
        "generator_seed": corpus.GENERATOR_SEED,
        "fixture_id": "aq7-synth-drop-at-boundary-test-001",
        "sample_rate": corpus.SAMPLE_RATE,
        "split": "TEST",
        "label_source": corpus.LABEL_SOURCE,
        "family": "drop_at_boundary",
        "beatgrid_provenance": {"status": "authored_synthetic"},
        "boundaries": [
            {"boundary_id": "b1", "bar_index": 16, "annotation_status": "single_source"},
            {"boundary_id": "b2", "bar_index": 32, "annotation_status": "single_source"},
        ],
        "sections": [
            {
                "section_id": "s0",
                "start_bar": 0,
                "end_bar": 16,
                "role": "intro",
                "annotation_status": "single_source",
            },
            {
                "section_id": "s1",
                "start_bar": 16,
                "end_bar": 32,
                "role": "build",
                "annotation_status": "single_source",
            },
            {
                "section_id": "s2",
                "start_bar": 32,
                "end_bar": 48,
                "role": "drop",
                "annotation_status": "single_source",
            },
        ],
        "drop_events": [
            {
                "event_id": "e1",
                "event_type": "drop_onset",
                "boundary_id": "b2",
                "bar_index": 32,
                "annotation_status": "single_source",
            }
        ],
        "drop_events_complete": True,
        "plane_status": {
            "aq7.boundary": "single_source",
            "aq7.role": "single_source",
            "aq7.drop_event": "single_source",
        },
        "join_key": {"analysis_eval_record_id": "aq7-synth-drop-at-boundary-test-001"},
    }


def _role_pred(section_id: str, automatic: str, effective: str | None = None) -> dict:
    return {
        "section_id": section_id,
        "automatic_result": {"role": automatic, "status": "measured"},
        "effective_result": {"role": effective or automatic, "status": "measured"},
    }


def _drop_pred(boundary_id: str, bar_index: int, event_id: str = "p1") -> dict:
    return {
        "event_id": event_id,
        "event_type": "drop_onset",
        "boundary_id": boundary_id,
        "bar_index": bar_index,
        "status": "measured",
    }


def test_01_candidate_identity_stable() -> None:
    b = _baseline()
    assert b.DOCUMENT_TYPE == "sample-brain.aq7.structure-role-drop-baseline.v1"
    assert b.SCHEMA_VERSION == "1.0.0"
    assert b.CANDIDATE_ID == "arrangement_classifier.baseline.v1"
    assert b.ROLE_PLANE_TOKEN == "aq7.role"
    assert b.DROP_PLANE_TOKEN == "aq7.drop_event"


def test_02_corpus_identity_exact() -> None:
    b = _baseline()
    assert b.CORPUS_ID == corpus.CORPUS_ID == schema.CORPUS_ID
    assert b.CORPUS_VERSION == corpus.CORPUS_VERSION == schema.CORPUS_VERSION
    assert b.GENERATOR_SEED == corpus.GENERATOR_SEED


def test_03_boundary_reference_is_1025_identity() -> None:
    b = _baseline()
    assert b.BOUNDARY_CONTEXT_CANDIDATE_ID == boundary_baseline.CANDIDATE_ID
    assert b.BOUNDARY_CONTEXT_DOCUMENT_TYPE == boundary_baseline.DOCUMENT_TYPE


def test_04_classifier_receives_frozen_reference_sections() -> None:
    b = _baseline()
    payload = b.build_frozen_geometry_classifier_input(_gt(), bar_features=[{"bar": 0}])
    assert [(s["section_id"], s["start_bar"], s["end_bar"]) for s in payload["sections"]] == [
        ("s0", 0, 16),
        ("s1", 16, 32),
        ("s2", 32, 48),
    ]
    assert payload["manual_overrides"] is None


def test_05_gt_role_does_not_enter_feature_extraction() -> None:
    b = _baseline()
    payload = b.build_frozen_geometry_classifier_input(_gt(), bar_features=[{"energy": 1.0}])
    assert json.dumps(payload["feature_inputs"]).find('"role"') == -1


def test_06_gt_drop_does_not_enter_feature_extraction() -> None:
    b = _baseline()
    payload = b.build_frozen_geometry_classifier_input(_gt(), bar_features=[{"energy": 1.0}])
    dumped = json.dumps(payload["feature_inputs"])
    assert "drop_onset" not in dumped
    assert "drop_events" not in dumped


def test_07_manual_override_is_ignored() -> None:
    b = _baseline()
    refs = b.frozen_reference_sections_from_gt(_gt())
    metrics = b.score_roles(
        refs,
        [_role_pred("s0", "intro", "drop"), _role_pred("s1", "build", "drop"), _role_pred("s2", "drop")],
        manual_overrides={"s1": "drop"},
    )
    assert metrics["confusion_matrix"]["build"]["build"] == 1


def test_08_effective_manual_result_is_ignored() -> None:
    b = _baseline()
    refs = b.frozen_reference_sections_from_gt(_gt())
    metrics = b.score_roles(refs, [_role_pred("s0", "drop", "intro")])
    assert metrics["confusion_matrix"]["intro"]["drop"] == 1
    assert metrics["confusion_matrix"]["intro"].get("intro", 0) == 0


def test_09_automatic_role_output_is_measured() -> None:
    b = _baseline()
    refs = b.frozen_reference_sections_from_gt(_gt())[:1]
    metrics = b.score_roles(refs, [_role_pred("s0", "intro", "drop")])
    assert metrics["per_role"]["intro"]["recall"] == pytest.approx(1.0)


def test_10_role_vocabulary_exact() -> None:
    b = _baseline()
    assert b.ROLE_VOCABULARY == (
        "intro",
        "groove",
        "build",
        "drop",
        "breakdown",
        "outro",
        "unknown",
    )
    assert b.CONCRETE_ROLE_VOCABULARY == ("intro", "groove", "build", "drop", "breakdown", "outro")


def test_11_semantic_unknown_remains_visible() -> None:
    b = _baseline()
    gt = _gt()
    gt["sections"][1]["role"] = "unknown"
    refs = b.frozen_reference_sections_from_gt(gt)
    metrics = b.score_roles(refs, [_role_pred("s1", "unknown")])
    assert metrics["confusion_matrix"]["unknown"]["unknown"] == 1
    assert metrics["unknown_reference_recall"] == pytest.approx(1.0)


def test_12_ambiguous_annotation_is_not_unknown_role() -> None:
    b = _baseline()
    gt = _gt()
    gt["sections"][1]["annotation_status"] = "ambiguous"
    refs = b.frozen_reference_sections_from_gt(gt)
    assert refs[1]["role"] == "build"
    assert refs[1]["annotation_status"] == "ambiguous"
    metrics = b.score_roles(refs, [_role_pred("s1", "unknown")])
    assert metrics["excluded_section_count"] == 1
    assert metrics["confusion_matrix"].get("build", {}).get("unknown", 0) == 0


def test_13_per_role_precision_recall_f1_correct() -> None:
    b = _baseline()
    refs = b.frozen_reference_sections_from_gt(_gt())
    metrics = b.score_roles(refs, [_role_pred("s0", "intro"), _role_pred("s1", "drop"), _role_pred("s2", "drop")])
    assert metrics["per_role"]["intro"]["f1"] == pytest.approx(1.0)
    assert metrics["per_role"]["build"]["recall"] == pytest.approx(0.0)
    assert metrics["per_role"]["drop"]["precision"] == pytest.approx(0.5)


def test_14_macro_f1_correct() -> None:
    b = _baseline()
    refs = b.frozen_reference_sections_from_gt(_gt())
    metrics = b.score_roles(refs, [_role_pred("s0", "intro"), _role_pred("s1", "drop"), _role_pred("s2", "drop")])
    # intro=1, build=0, drop=2/3; other concrete roles omitted when support=prediction=0.
    assert metrics["macro_f1"] == pytest.approx((1.0 + 0.0 + (2.0 / 3.0)) / 3.0)


def test_15_confusion_matrix_deterministic() -> None:
    b = _baseline()
    refs = b.frozen_reference_sections_from_gt(_gt())
    preds = [_role_pred("s2", "drop"), _role_pred("s0", "intro"), _role_pred("s1", "build")]
    first = b.score_roles(refs, preds)["confusion_matrix"]
    second = b.score_roles(refs, list(reversed(preds)))["confusion_matrix"]
    assert first == second
    assert list(first) == sorted(first)


def test_16_unknown_abstention_rates_correct() -> None:
    b = _baseline()
    refs = b.frozen_reference_sections_from_gt(_gt())
    metrics = b.score_roles(refs, [_role_pred("s0", "unknown")], prediction_usable=True)
    assert metrics["unknown_rate"] == pytest.approx(1.0)
    assert metrics["coverage"] == pytest.approx(0.0)
    held = b.score_roles(refs, [], prediction_usable=False, prediction_status="failed")
    assert held["abstention_rate"] == pytest.approx(1.0)


def test_17_weighted_accuracy_is_diagnostic_only() -> None:
    b = _baseline()
    refs = b.frozen_reference_sections_from_gt(_gt())
    metrics = b.score_roles(refs, [_role_pred("s0", "intro"), _role_pred("s1", "build"), _role_pred("s2", "drop")])
    assert metrics["bar_weighted_accuracy"] == pytest.approx(1.0)
    assert metrics["bar_weighted_accuracy_kind"] == "diagnostic"


def test_18_drop_plane_separate_from_role_plane() -> None:
    b = _baseline()
    drops = b.score_drops(b.reference_boundaries_from_gt(_gt()), _gt()["drop_events"], [_drop_pred("b2", 32)])
    roles = b.score_roles(b.frozen_reference_sections_from_gt(_gt()), [_role_pred("s2", "drop")])
    assert drops["plane"] == "aq7.drop_event"
    assert roles["plane"] == "aq7.role"
    assert "macro_f1" not in drops


def test_19_drop_true_positive_correct() -> None:
    b = _baseline()
    metrics = b.score_drops(b.reference_boundaries_from_gt(_gt()), _gt()["drop_events"], [_drop_pred("b2", 32)])
    assert metrics["matched_count"] == 1
    assert metrics["precision_1bar"] == pytest.approx(1.0)
    assert metrics["recall_1bar"] == pytest.approx(1.0)


def test_20_false_drop_visible() -> None:
    b = _baseline()
    metrics = b.score_drops(b.reference_boundaries_from_gt(_gt()), [], [_drop_pred("b1", 16)])
    assert metrics["false_positive_count"] == 1
    assert metrics["false_rate"] == pytest.approx(1.0)


def test_21_missed_drop_visible() -> None:
    b = _baseline()
    metrics = b.score_drops(b.reference_boundaries_from_gt(_gt()), _gt()["drop_events"], [])
    assert metrics["missed_count"] == 1
    assert metrics["miss_rate"] == pytest.approx(1.0)


def test_22_drop_timing_error_correct() -> None:
    b = _baseline()
    metrics = b.score_drops(b.reference_boundaries_from_gt(_gt()), _gt()["drop_events"], [_drop_pred("b2", 33)])
    assert metrics["abs_error_bars_median"] == pytest.approx(1.0)
    assert metrics["matched_pairs"][0]["signed_error_bars"] == 1


def test_23_event_cannot_create_boundary() -> None:
    b = _baseline()
    with pytest.raises(ValueError, match="unknown boundary|boundary"):
        b.score_drops(b.reference_boundaries_from_gt(_gt()), _gt()["drop_events"], [_drop_pred("new-boundary", 40)])


def test_24_role_cannot_create_boundary() -> None:
    b = _baseline()
    refs = b.frozen_reference_sections_from_gt(_gt())
    with pytest.raises(ValueError, match="unknown section|section"):
        b.score_roles(refs, [_role_pred("invented-section", "drop")])


def test_25_section_ranges_exactly_preserved() -> None:
    b = _baseline()
    refs = b.frozen_reference_sections_from_gt(_gt())
    assert [(r["start_bar"], r["end_bar"]) for r in refs] == [(0, 16), (16, 32), (32, 48)]


def test_26_boundary_set_exactly_unchanged() -> None:
    b = _baseline()
    refs = b.reference_boundaries_from_gt(_gt())
    b.assert_boundary_geometry_preserved(refs, list(refs), b.frozen_reference_sections_from_gt(_gt()), b.frozen_reference_sections_from_gt(_gt()))
    changed = [dict(refs[0], bar_index=17), refs[1]]
    with pytest.raises(ValueError, match="boundary.*changed|geometry"):
        b.assert_boundary_geometry_preserved(refs, changed, b.frozen_reference_sections_from_gt(_gt()), b.frozen_reference_sections_from_gt(_gt()))


def test_27_beatgrid_hold_explicit() -> None:
    b = _baseline()
    hold = b.evaluate_beatgrid_hold(
        fixture_id="aq7-synth-beatgrid-hold-test-001",
        beatgrid_status="missing",
        role_eligible=False,
        drop_eligible=False,
    )
    assert hold["role"]["evidence_status"] == "unknown"
    assert hold["drop_event"]["evidence_status"] == "unknown"
    assert hold["hold_kind"] == "BEATGRID_PROVENANCE_LIMITATION"


def test_28_missing_optional_signals_visible() -> None:
    b = _baseline()
    provenance = b.optional_signal_provenance({"energy": "measured"}, optional_backends={"clap": None, "stems": None})
    assert provenance["energy"] == "measured"
    assert provenance["clap"] in {"missing", "not_applicable", "unavailable"}
    assert provenance["stems"] in {"missing", "not_applicable", "unavailable"}


def test_29_no_result_partial_state_visible() -> None:
    b = _baseline()
    state = b.prediction_surface_state(role_status="partial", drop_status="no_result")
    assert state["role_status"] == "partial"
    assert state["drop_status"] == "no_result"
    assert state["visible"] is True


def test_30_calibration_and_test_separate() -> None:
    b = _baseline()
    rows = [
        {"split": "CALIBRATION", "role": {"support": 2}, "drop_event": {"support": 0}},
        {"split": "TEST", "role": {"support": 1}, "drop_event": {"support": 1}},
    ]
    agg = b.aggregate_splits(rows)
    assert set(agg) == {"CALIBRATION", "TEST"}
    assert agg["CALIBRATION"]["role"]["support"] == 2
    assert agg["TEST"]["role"]["support"] == 1


def test_31_repeat_semantically_equal() -> None:
    b = _baseline()
    artifact = {"candidate_id": b.CANDIDATE_ID, "runtime": {"wall": 1.23}, "splits": {"TEST": {"role": {"support": 1}}}}
    again = {"candidate_id": b.CANDIDATE_ID, "runtime": {"wall": 9.87}, "splits": {"TEST": {"role": {"support": 1}}}}
    assert b.compare_semantic(b.semantic_projection(artifact), b.semantic_projection(again)) is True


def test_32_changed_role_semantic_mismatch() -> None:
    b = _baseline()
    left = {"candidate_id": b.CANDIDATE_ID, "fixtures": [{"fixture_id": "f", "roles": [{"section_id": "s1", "role": "build"}]}]}
    right = {"candidate_id": b.CANDIDATE_ID, "fixtures": [{"fixture_id": "f", "roles": [{"section_id": "s1", "role": "drop"}]}]}
    assert b.compare_semantic(b.semantic_projection(left), b.semantic_projection(right)) is False


def test_33_changed_drop_event_semantic_mismatch() -> None:
    b = _baseline()
    left = {"candidate_id": b.CANDIDATE_ID, "fixtures": [{"fixture_id": "f", "drops": [{"boundary_id": "b1", "bar_index": 16}]}]}
    right = {"candidate_id": b.CANDIDATE_ID, "fixtures": [{"fixture_id": "f", "drops": [{"boundary_id": "b2", "bar_index": 32}]}]}
    assert b.compare_semantic(b.semantic_projection(left), b.semantic_projection(right)) is False


def test_34_no_absolute_private_paths_in_artifact(tmp_path: Path) -> None:
    b = _baseline()
    payload = {"document_type": b.DOCUMENT_TYPE, "bad": str(tmp_path / "private.wav")}
    with pytest.raises(ValueError, match="portable|path|absolute|Host"):
        b.assert_portable_baseline_payload(payload)


def test_35_analyzer_files_declared_protected() -> None:
    b = _baseline()
    assert b.PROTECTED_ANALYZER_FILES == (
        "src/arrangement_classifier.py",
        "src/section_signals.py",
        "src/structure_v1.py",
    )
    assert b.PROTECTED_ANALYZER_FILES_CHANGED is False


def test_36_evidence_reload_validates(tmp_path: Path) -> None:
    b = _baseline()
    artifact = {
        "document_type": b.DOCUMENT_TYPE,
        "schema_version": b.SCHEMA_VERSION,
        "candidate_id": b.CANDIDATE_ID,
        "corpus_id": b.CORPUS_ID,
        "corpus_version": b.CORPUS_VERSION,
        "boundary_reference": b.BOUNDARY_CONTEXT_CANDIDATE_ID,
        "splits": {"CALIBRATION": {}, "TEST": {}},
    }
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")
    loaded = b.load_role_drop_baseline_artifact(path)
    assert loaded["candidate_id"] == b.CANDIDATE_ID


def test_37_no_production_default_change() -> None:
    b = _baseline()
    assert b.PRODUCTION_DEFAULTS_CHANGED is False
    assert b.FEATURE_TOGGLE == "N/A"
