"""Frozen tests for AQ4 classification candidate comparison harness (#1034).

TEST FREEZE: these assertions define the compare contract. Fix the harness,
not these expectations, when they turn red.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import aq4_classification_baseline as baseline
from src import aq4_classification_candidate_compare as compare
from src import aq4_classification_corpus as corpus
from src import classify


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_compare_identity_constants_are_frozen() -> None:
    assert compare.DOCUMENT_TYPE == (
        "sample-brain.aq4.classification-candidate-compare.v1"
    )
    assert compare.SCHEMA_VERSION == "1.0.0"
    assert compare.CORPUS_ID == corpus.CORPUS_ID
    assert compare.EXIT_REPRODUCIBLE == (
        "AQ4_CLASSIFICATION_CANDIDATE_COMPARE_REPRODUCIBLE"
    )
    assert compare.EXIT_INCOMPLETE == (
        "AQ4_CLASSIFICATION_CANDIDATE_COMPARE_INCOMPLETE"
    )
    assert compare.BASELINE_DOCUMENT_TYPE == baseline.DOCUMENT_TYPE
    assert compare.SAMPLE_CLASS_SURFACE == baseline.SAMPLE_CLASS_SURFACE
    assert compare.PRED_TYPE_RULE_SURFACE == baseline.PRED_TYPE_RULE_SURFACE
    assert compare.PRED_TYPE_KNN_SURFACE == baseline.PRED_TYPE_KNN_SURFACE


def test_frozen_candidate_registry_has_at_most_four_documented_adapters() -> None:
    candidates = compare.list_classification_candidates()
    assert 3 <= len(candidates) <= 4
    ids = [c.candidate_id for c in candidates]
    assert len(ids) == len(set(ids))

    baseline_c = compare.candidate_by_id("classification.baseline.v1")
    assert baseline_c.oneshot_max_duration_sec == pytest.approx(
        compare.BASELINE_ONESHOT_MAX_DURATION_SEC
    )
    assert baseline_c.short_max_sec == pytest.approx(compare.BASELINE_SHORT_MAX_SEC)
    assert baseline_c.mid_max_sec == pytest.approx(compare.BASELINE_MID_MAX_SEC)
    assert baseline_c.long_min_sec == pytest.approx(compare.BASELINE_LONG_MIN_SEC)
    assert baseline_c.bright_min == pytest.approx(compare.BASELINE_BRIGHT_MIN)
    assert baseline_c.dark_max == pytest.approx(compare.BASELINE_DARK_MAX)
    assert baseline_c.punchy_min_loudness == pytest.approx(
        compare.BASELINE_PUNCHY_MIN_LOUDNESS
    )

    for candidate in candidates:
        assert candidate.description.strip()
        public = compare.candidate_public(candidate)
        assert public["candidate_id"] == candidate.candidate_id
        assert "oneshot_max_duration_sec" in public
        assert "bright_min" in public


def test_candidate_by_id_rejects_unknown() -> None:
    with pytest.raises(compare.Aq4ClassificationCandidateCompareError, match="unknown"):
        compare.candidate_by_id("not.a.real.candidate")


def test_predict_clip_for_candidate_uses_declared_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Adapters must thread declared config into duration class + rule_type."""
    work = tmp_path / "corpus"
    corpus.generate_aq4_classification_corpus(work, repo_root=REPO_ROOT)
    clip_id = "aq4-synth-kick-oneshot-cal-001"
    gt = json.loads((work / "gt" / f"{clip_id}.json").read_text(encoding="utf-8"))
    audio = work / "audio" / f"{clip_id}.wav"
    candidate = compare.candidate_by_id("pred_type.bright_min.4000")

    seen: dict[str, object] = {}

    def fake_rule_type(duration, loudness, brightness, mfcc_mean_blob, clazz, **kwargs):  # type: ignore[no-untyped-def]
        seen["kwargs"] = kwargs
        seen["clazz"] = clazz
        return ["Kick"]

    monkeypatch.setattr(compare, "rule_type", fake_rule_type)

    row = compare.predict_clip_for_candidate(audio, gt, candidate)
    assert row["clip_id"] == clip_id
    assert row["candidate_id"] == candidate.candidate_id
    assert row["sample_class_pred"] in {"oneshot", "loop"}
    assert seen["kwargs"]["bright_min"] == pytest.approx(candidate.bright_min)
    assert seen["kwargs"]["short_max_sec"] == pytest.approx(candidate.short_max_sec)
    assert seen["kwargs"]["mid_max_sec"] == pytest.approx(candidate.mid_max_sec)
    assert seen["kwargs"]["long_min_sec"] == pytest.approx(candidate.long_min_sec)
    assert seen["kwargs"]["dark_max"] == pytest.approx(candidate.dark_max)
    assert seen["kwargs"]["punchy_min_loudness"] == pytest.approx(
        candidate.punchy_min_loudness
    )


def test_duration_class_adapter_respects_oneshot_max() -> None:
    assert compare.duration_class_for_candidate(1.0, oneshot_max_duration_sec=1.0) == (
        "oneshot"
    )
    assert compare.duration_class_for_candidate(1.01, oneshot_max_duration_sec=1.0) == (
        "loop"
    )
    assert compare.duration_class_for_candidate(1.2, oneshot_max_duration_sec=1.2) == (
        "oneshot"
    )
    assert compare.duration_class_for_candidate(1.21, oneshot_max_duration_sec=1.2) == (
        "loop"
    )
    assert compare.duration_class_for_candidate(None, oneshot_max_duration_sec=1.2) is None


def test_run_rejects_output_inside_repo(tmp_path: Path) -> None:
    work = tmp_path / "corpus"
    corpus.generate_aq4_classification_corpus(work, repo_root=REPO_ROOT)
    inside = REPO_ROOT / ".pytest_aq4_classification_compare_should_not_exist.json"
    with pytest.raises(ValueError, match="outside"):
        compare.run_aq4_classification_candidate_compare(
            work_dir=work,
            output_path=inside,
            repo_root=REPO_ROOT,
        )


def test_run_writes_external_json_with_per_candidate_metrics(tmp_path: Path) -> None:
    work = tmp_path / "corpus"
    out = tmp_path / "aq4-classification-compare.json"
    corpus.generate_aq4_classification_corpus(work, repo_root=REPO_ROOT)

    result = compare.run_aq4_classification_candidate_compare(
        work_dir=work,
        output_path=out,
        repo_root=REPO_ROOT,
    )

    assert out.is_file()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded == result
    assert result["document_type"] == compare.DOCUMENT_TYPE
    assert result["schema_version"] == compare.SCHEMA_VERSION
    assert result["corpus_id"] == corpus.CORPUS_ID
    assert result["exit_status"] in {
        compare.EXIT_REPRODUCIBLE,
        compare.EXIT_INCOMPLETE,
    }
    assert result["no_tuning_on_test"] is True
    assert result["partition_policy"]["CALIBRATION"] == "DEVELOPMENT/CALIBRATION"
    assert result["partition_policy"]["TEST"] == "TEST/HOLDOUT"
    assert result["baseline_document_type"] == baseline.DOCUMENT_TYPE
    assert result["aq4.pred_type_knn"]["status"] == "HOLD"

    candidate_ids = {c["candidate_id"] for c in result["candidates"]}
    expected_ids = {c.candidate_id for c in compare.list_classification_candidates()}
    assert candidate_ids == expected_ids

    for entry in result["candidates"]:
        assert "description" in entry
        assert set(entry["splits"]) == {"CALIBRATION", "TEST"}
        for split_name in ("CALIBRATION", "TEST"):
            split = entry["splits"][split_name]
            assert "aq4.sample_class" in split
            assert "aq4.pred_type_rule" in split
            sc = split["aq4.sample_class"]
            pt = split["aq4.pred_type_rule"]
            assert "metrics" in sc
            assert "metrics" in pt
            assert "macro_f1" in sc["metrics"]
            assert "macro_f1" in pt["metrics"]
            sc_labels = set((sc["metrics"].get("per_class") or {}).keys())
            pt_labels = set((pt["metrics"].get("per_class") or {}).keys())
            assert sc_labels.isdisjoint({"Kick", "Snare", "Pad", "Drone", "Loop", "FX"})
            assert pt_labels.isdisjoint({"oneshot", "loop"})

    dumped = json.dumps(result)
    assert "D:/" not in dumped
    assert "D:\\" not in dumped
    assert "/Users/" not in dumped
    for key in ("audio_path", "file_path", "sample_path", "work_dir"):
        assert key not in result


def test_baseline_candidate_matches_baseline_harness_metrics(tmp_path: Path) -> None:
    """Fairness: baseline candidate must reproduce baseline harness aggregates."""
    work = tmp_path / "corpus"
    corpus.generate_aq4_classification_corpus(work, repo_root=REPO_ROOT)
    baseline_out = tmp_path / "baseline.json"
    compare_out = tmp_path / "compare.json"

    baseline_result = baseline.run_aq4_classification_baseline(
        work_dir=work,
        output_path=baseline_out,
        repo_root=REPO_ROOT,
        regenerate_corpus=False,
    )
    compare_result = compare.run_aq4_classification_candidate_compare(
        work_dir=work,
        output_path=compare_out,
        repo_root=REPO_ROOT,
        regenerate_corpus=False,
    )

    baseline_entry = next(
        c
        for c in compare_result["candidates"]
        if c["candidate_id"] == "classification.baseline.v1"
    )
    for split_name in ("CALIBRATION", "TEST"):
        for plane in ("aq4.sample_class", "aq4.pred_type_rule"):
            assert (
                baseline_entry["splits"][split_name][plane]
                == baseline_result["splits"][split_name][plane]
            )


def test_rule_type_optional_kwargs_preserve_default_behavior() -> None:
    """Production defaults must remain identical when kwargs are omitted."""
    tags_default = classify.rule_type(0.2, -10.0, 5000.0, None, "oneshot")
    tags_explicit = classify.rule_type(
        0.2,
        -10.0,
        5000.0,
        None,
        "oneshot",
        short_max_sec=0.35,
        mid_max_sec=1.2,
        long_min_sec=2.5,
        bright_min=4500.0,
        dark_max=1500.0,
        punchy_min_loudness=-18.0,
    )
    assert tags_default == tags_explicit
