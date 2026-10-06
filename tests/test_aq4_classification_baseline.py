"""Frozen tests for AQ4 classification baseline harness (#1032).

TEST FREEZE: these assertions define the baseline eval contract. Fix the
harness, not these expectations, when they turn red.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import aq4_classification_baseline as baseline
from src import aq4_classification_corpus as corpus


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_baseline_identity_constants_are_frozen() -> None:
    assert baseline.DOCUMENT_TYPE == "sample-brain.aq4.classification-baseline.v1"
    assert baseline.SCHEMA_VERSION == "1.0.0"
    assert baseline.CORPUS_ID == corpus.CORPUS_ID
    assert baseline.EXIT_MEASURED == "AQ4_CLASSIFICATION_BASELINE_MEASURED"
    assert baseline.EXIT_INCOMPLETE == "AQ4_CLASSIFICATION_BASELINE_INCOMPLETE"
    assert baseline.SAMPLE_CLASS_SURFACE == "src.analyze.extract_features.clazz"
    assert baseline.PRED_TYPE_RULE_SURFACE == "src.classify.rule_type"
    assert baseline.PRED_TYPE_KNN_SURFACE == "src.classify.write_autotype_to_db(use_knn=True)"


def test_multiclass_metrics_report_explicit_denominators() -> None:
    # labels: A A B ; preds: A B B
    scored = baseline.score_multiclass(
        y_true=["A", "A", "B"],
        y_pred=["A", "B", "B"],
        labels=["A", "B"],
    )
    assert scored["support"] == {"A": 2, "B": 1}
    assert scored["per_class"]["A"]["tp"] == 1
    assert scored["per_class"]["A"]["fp"] == 0
    assert scored["per_class"]["A"]["fn"] == 1
    assert scored["per_class"]["A"]["precision"] == pytest.approx(1.0)
    assert scored["per_class"]["A"]["recall"] == pytest.approx(0.5)
    assert scored["per_class"]["B"]["precision"] == pytest.approx(0.5)
    assert scored["per_class"]["B"]["recall"] == pytest.approx(1.0)
    assert scored["macro_f1"] == pytest.approx(
        (scored["per_class"]["A"]["f1"] + scored["per_class"]["B"]["f1"]) / 2.0
    )
    assert scored["balanced_accuracy"] == pytest.approx(0.75)
    assert scored["confusion"]["A"]["A"] == 1
    assert scored["confusion"]["A"]["B"] == 1
    assert scored["confusion"]["B"]["B"] == 1
    assert scored["n_eligible"] == 3


def test_clear_vs_uncertain_eligibility_keeps_planes_separate() -> None:
    rows = [
        {
            "clip_id": "c1",
            "sample_class_label": "oneshot",
            "sample_class_pred": "oneshot",
            "pred_type_label": "Kick",
            "pred_type_rule_pred": "Kick",
            "label_status": "clear",
        },
        {
            "clip_id": "c2",
            "sample_class_label": "ambiguous",
            "sample_class_pred": "oneshot",
            "pred_type_label": "OneShot",
            "pred_type_rule_pred": "OneShot",
            "label_status": "ambiguous",
        },
        {
            "clip_id": "c3",
            "sample_class_label": "unknown",
            "sample_class_pred": "oneshot",
            "pred_type_label": "unknown",
            "pred_type_rule_pred": "FX",
            "label_status": "unknown",
        },
    ]
    sample_class = baseline.aggregate_sample_class(rows)
    pred_type = baseline.aggregate_pred_type_rule(rows)

    assert sample_class["n_clear_eligible"] == 1
    assert sample_class["n_uncertain"] == 2
    assert sample_class["metrics"]["n_eligible"] == 1
    assert "Kick" not in (sample_class["metrics"].get("per_class") or {})

    assert pred_type["n_clear_eligible"] == 1
    assert pred_type["n_uncertain"] == 2
    assert pred_type["metrics"]["n_eligible"] == 1
    assert "oneshot" not in (pred_type["metrics"].get("per_class") or {})


def test_run_rejects_output_inside_repo(tmp_path: Path) -> None:
    work = tmp_path / "corpus"
    corpus.generate_aq4_classification_corpus(work, repo_root=REPO_ROOT)
    inside = REPO_ROOT / ".pytest_aq4_classification_baseline_should_not_exist.json"
    with pytest.raises(ValueError, match="outside"):
        baseline.run_aq4_classification_baseline(
            work_dir=work,
            output_path=inside,
            repo_root=REPO_ROOT,
        )


def test_run_writes_external_json_with_separate_planes(tmp_path: Path) -> None:
    work = tmp_path / "corpus"
    out = tmp_path / "aq4-classification-baseline.json"
    corpus.generate_aq4_classification_corpus(work, repo_root=REPO_ROOT)

    result = baseline.run_aq4_classification_baseline(
        work_dir=work,
        output_path=out,
        repo_root=REPO_ROOT,
    )

    assert out.is_file()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded == result
    assert result["document_type"] == baseline.DOCUMENT_TYPE
    assert result["schema_version"] == baseline.SCHEMA_VERSION
    assert result["corpus_id"] == corpus.CORPUS_ID
    assert result["exit_status"] in {
        baseline.EXIT_MEASURED,
        baseline.EXIT_INCOMPLETE,
    }
    assert set(result["splits"]) == {"CALIBRATION", "TEST"}
    assert result["surfaces"]["aq4.sample_class"] == baseline.SAMPLE_CLASS_SURFACE
    assert result["surfaces"]["aq4.pred_type_rule"] == baseline.PRED_TYPE_RULE_SURFACE
    assert result["surfaces"]["aq4.pred_type_knn"] == baseline.PRED_TYPE_KNN_SURFACE

    knn = result["aq4.pred_type_knn"]
    assert knn["status"] == "HOLD"
    assert "reason" in knn

    for split_name in ("CALIBRATION", "TEST"):
        split = result["splits"][split_name]
        assert "aq4.sample_class" in split
        assert "aq4.pred_type_rule" in split
        sc = split["aq4.sample_class"]
        pt = split["aq4.pred_type_rule"]
        assert "metrics" in sc
        assert "metrics" in pt
        assert "n_clear_eligible" in sc
        assert "n_uncertain" in sc
        assert "macro_f1" in sc["metrics"]
        assert "balanced_accuracy" in sc["metrics"]
        assert "confusion" in sc["metrics"]
        assert "macro_f1" in pt["metrics"]
        assert "confusion" in pt["metrics"]
        # Planes stay separate: sample_class metrics must not use pred_type labels.
        sc_labels = set((sc["metrics"].get("per_class") or {}).keys())
        pt_labels = set((pt["metrics"].get("per_class") or {}).keys())
        assert sc_labels.isdisjoint({"Kick", "Snare", "Pad", "Drone", "Loop", "FX"})
        assert pt_labels.isdisjoint({"oneshot", "loop"})

    health = result["dataset_health"]
    assert "support_counts" in health
    assert "sample_class" in health["support_counts"]
    assert "pred_type" in health["support_counts"]

    dumped = json.dumps(result)
    assert "D:/" not in dumped
    assert "D:\\" not in dumped
    assert "/Users/" not in dumped
    for key in ("audio_path", "file_path", "sample_path", "work_dir"):
        assert key not in result

    assert result["clip_count"] >= 8
    for row in result["clips"]:
        assert "clip_id" in row
        assert row["split"] in corpus.SPLITS
        assert "sample_class_label" in row
        assert "sample_class_pred" in row
        assert "pred_type_label" in row
        assert "pred_type_rule_pred" in row
        assert "label_status" in row
        assert ":" not in row["clip_id"]
        # Separate taxonomy fields — never a collapsed joint label.
        assert "joint_label" not in row
        assert "combined_class" not in row


def test_no_tuning_on_test_is_documented_in_result(tmp_path: Path) -> None:
    work = tmp_path / "corpus"
    out = tmp_path / "out.json"
    corpus.generate_aq4_classification_corpus(work, repo_root=REPO_ROOT)
    result = baseline.run_aq4_classification_baseline(
        work_dir=work,
        output_path=out,
        repo_root=REPO_ROOT,
    )
    assert result["partition_policy"]["CALIBRATION"] == "DEVELOPMENT/CALIBRATION"
    assert result["partition_policy"]["TEST"] == "TEST/HOLDOUT"
    assert result["no_tuning_on_test"] is True
