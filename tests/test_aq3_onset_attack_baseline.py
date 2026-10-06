"""Frozen tests for AQ3 onset/attack timing baseline harness (#995).

TEST FREEZE: these assertions define the baseline eval contract. Fix the
harness, not these expectations, when they turn red.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import aq3_onset_attack_baseline as baseline
from src import aq3_timing_corpus as corpus


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_baseline_identity_constants_are_frozen() -> None:
    assert baseline.DOCUMENT_TYPE == "sample-brain.aq3.onset-attack-baseline.v1"
    assert baseline.SCHEMA_VERSION == "1.0.0"
    assert baseline.CORPUS_ID == corpus.CORPUS_ID
    assert baseline.TOLERANCE_CANDIDATES_MS == corpus.TOLERANCE_CANDIDATES_MS
    assert baseline.EXIT_MEASURED == "AQ3_ONSET_ATTACK_BASELINE_MEASURED"
    assert baseline.EXIT_INCOMPLETE == "AQ3_ONSET_ATTACK_BASELINE_INCOMPLETE"
    assert baseline.ONSET_SURFACE == "src.gesture_analysis.analyze_gesture_audio"
    assert baseline.ATTACK_SURFACE == "src.workbench_attack_suggest.suggest_attack_ms"


def test_match_onsets_greedy_within_tolerance() -> None:
    labels = [100.0, 300.0, 550.0]
    preds = [105.0, 290.0, 700.0]
    matched, missed, extras = baseline.match_onsets(preds, labels, tolerance_ms=20.0)
    assert len(matched) == 2
    assert missed == [550.0]
    assert extras == [700.0]
    # Matched pairs carry absolute errors.
    errors = sorted(abs(p - l) for p, l in matched)
    assert errors == pytest.approx([5.0, 10.0])


def test_onset_metrics_report_explicit_tolerance_windows() -> None:
    labels = [100.0, 300.0]
    preds = [100.0, 330.0]  # second is late by 30 ms
    m20 = baseline.score_onset_metrics(preds, labels, tolerance_ms=20)
    m50 = baseline.score_onset_metrics(preds, labels, tolerance_ms=50)
    assert m20["tolerance_ms"] == 20
    assert m50["tolerance_ms"] == 50
    assert m20["matched"] == 1
    assert m50["matched"] == 2
    assert m20["recall"] == pytest.approx(0.5)
    assert m50["recall"] == pytest.approx(1.0)
    assert m20["precision"] == pytest.approx(0.5)
    assert m50["precision"] == pytest.approx(1.0)


def test_attack_metrics_early_late_and_within_tolerance() -> None:
    # Early by 15 ms → inside 20 and 50.
    early = baseline.score_attack_metrics(predicted_ms=185.0, label_ms=200.0, tolerances_ms=(20, 50))
    assert early["eligible"] is True
    assert early["predicted"] is True
    assert early["abs_error_ms"] == pytest.approx(15.0)
    assert early["signed_error_ms"] == pytest.approx(-15.0)
    assert early["within_tolerance"]["20"] is True
    assert early["within_tolerance"]["50"] is True
    assert early["early"] is True
    assert early["late"] is False

    late = baseline.score_attack_metrics(predicted_ms=260.0, label_ms=200.0, tolerances_ms=(20, 50))
    assert late["within_tolerance"]["20"] is False
    assert late["within_tolerance"]["50"] is False
    assert late["late"] is True

    abstain = baseline.score_attack_metrics(predicted_ms=None, label_ms=200.0, tolerances_ms=(20, 50))
    assert abstain["eligible"] is True
    assert abstain["predicted"] is False
    assert abstain["abs_error_ms"] is None


def test_run_rejects_output_inside_repo(tmp_path: Path) -> None:
    work = tmp_path / "corpus"
    corpus.generate_aq3_timing_corpus(work, repo_root=REPO_ROOT)
    inside = REPO_ROOT / ".pytest_aq3_onset_attack_baseline_should_not_exist.json"
    with pytest.raises(ValueError, match="outside"):
        baseline.run_aq3_onset_attack_baseline(
            work_dir=work,
            output_path=inside,
            repo_root=REPO_ROOT,
        )


def test_run_writes_external_json_with_portable_metrics(tmp_path: Path) -> None:
    work = tmp_path / "corpus"
    out = tmp_path / "aq3-onset-attack-baseline.json"
    corpus.generate_aq3_timing_corpus(work, repo_root=REPO_ROOT)

    result = baseline.run_aq3_onset_attack_baseline(
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
    assert result["tolerance_candidates_ms"] == list(corpus.TOLERANCE_CANDIDATES_MS)
    assert result["hold_buckets"] == list(corpus.HOLD_BUCKETS)
    assert set(result["splits"]) == {"CALIBRATION", "TEST"}

    for split_name in ("CALIBRATION", "TEST"):
        split = result["splits"][split_name]
        assert "aq3.onset" in split
        assert "aq3.attack" in split
        assert "aq3.gesture" in split
        onset = split["aq3.onset"]
        assert "by_tolerance" in onset
        for tol in corpus.TOLERANCE_CANDIDATES_MS:
            key = str(tol)
            assert key in onset["by_tolerance"]
            block = onset["by_tolerance"][key]
            assert block["tolerance_ms"] == tol
            for field in (
                "precision",
                "recall",
                "f1",
                "missed_onset_rate",
                "duplicate_onset_rate",
                "matched",
                "label_count",
                "pred_count",
            ):
                assert field in block
        attack = split["aq3.attack"]
        assert "eligible" in attack
        assert "within_tolerance_rates" in attack
        for tol in corpus.TOLERANCE_CANDIDATES_MS:
            assert str(tol) in attack["within_tolerance_rates"]
        gesture = split["aq3.gesture"]
        assert gesture["status"] in {"MEASURED", "PARTIAL", "HOLD"}

    # Portable: no absolute host paths / drive letters in committed-style JSON.
    dumped = json.dumps(result)
    assert "D:/" not in dumped
    assert "D:\\" not in dumped
    assert "/Users/" not in dumped
    for key in ("audio_path", "file_path", "sample_path", "work_dir"):
        assert key not in result

    # Per-clip rows keep clip_id join keys only.
    assert result["clip_count"] >= 4
    for row in result["clips"]:
        assert "clip_id" in row
        assert row["split"] in corpus.SPLITS
        assert "onset_times_ms_pred" in row
        assert "attack_ms_pred" in row
        assert ":" not in row["clip_id"]


def test_no_tuning_on_test_is_documented_in_result(tmp_path: Path) -> None:
    work = tmp_path / "corpus"
    out = tmp_path / "out.json"
    corpus.generate_aq3_timing_corpus(work, repo_root=REPO_ROOT)
    result = baseline.run_aq3_onset_attack_baseline(
        work_dir=work,
        output_path=out,
        repo_root=REPO_ROOT,
    )
    assert result["partition_policy"]["CALIBRATION"] == "DEVELOPMENT/CALIBRATION"
    assert result["partition_policy"]["TEST"] == "TEST/HOLDOUT"
    assert result["no_tuning_on_test"] is True
