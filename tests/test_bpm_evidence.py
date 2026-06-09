from __future__ import annotations

import pytest

from src.bpm_evidence import (
    BpmEvidenceResult,
    BpmSampleRecord,
    classify_bpm_error,
    run_bpm_evidence,
)


class TestClassifyBpmError:
    def test_exact_match_is_correct(self):
        assert classify_bpm_error(120.0, 120.0) == "correct"

    def test_within_5_percent_is_correct(self):
        assert classify_bpm_error(126.0, 120.0) == "correct"

    def test_half_ratio_is_half(self):
        assert classify_bpm_error(60.0, 120.0) == "half"

    def test_half_ratio_lower_bound(self):
        assert classify_bpm_error(54.0, 120.0) == "half"

    def test_half_ratio_upper_bound(self):
        assert classify_bpm_error(66.0, 120.0) == "half"

    def test_double_ratio_is_double(self):
        assert classify_bpm_error(240.0, 120.0) == "double"

    def test_double_ratio_lower_bound(self):
        assert classify_bpm_error(228.0, 120.0) == "double"

    def test_double_ratio_upper_bound(self):
        assert classify_bpm_error(252.0, 120.0) == "double"

    def test_plausible_but_not_half_double_is_ambiguous(self):
        assert classify_bpm_error(90.0, 120.0) == "ambiguous"

    def test_wildly_wrong_is_outlier(self):
        assert classify_bpm_error(600.0, 120.0) == "outlier"
        assert classify_bpm_error(12.0, 120.0) == "outlier"

    def test_none_is_outlier(self):
        assert classify_bpm_error(None, 120.0) == "outlier"

    def test_zero_is_outlier(self):
        assert classify_bpm_error(0.0, 120.0) == "outlier"

    def test_negative_is_outlier(self):
        assert classify_bpm_error(-1.0, 120.0) == "outlier"

    def test_label_zero_is_outlier(self):
        assert classify_bpm_error(120.0, 0.0) == "outlier"

    def test_label_negative_is_outlier(self):
        assert classify_bpm_error(120.0, -1.0) == "outlier"

    def test_high_bpm_within_ratio_is_correct(self):
        assert classify_bpm_error(175.0, 175.0) == "correct"

    def test_slow_bpm_half_is_half(self):
        assert classify_bpm_error(30.0, 60.0) == "half"


class TestBpmEvidenceResult:
    def test_empty_result_returns_zero_pct(self):
        result = BpmEvidenceResult()
        assert result.total == 0
        assert result.correct_pct == 0.0
        assert result.half_pct == 0.0
        assert result.double_pct == 0.0
        assert result.octave_error_pct == 0.0
        assert result.mean_absolute_error == 0.0

    def test_counts_and_pcts(self):
        from pathlib import Path
        result = BpmEvidenceResult()
        result.records.append(
            BpmSampleRecord(Path("a.wav"), "pulse", 120.0, 120.0, "correct")
        )
        result.records.append(
            BpmSampleRecord(Path("b.wav"), "pulse", 120.0, 60.0, "half")
        )
        result.records.append(
            BpmSampleRecord(Path("c.wav"), "kick", 120.0, 240.0, "double")
        )
        result.records.append(
            BpmSampleRecord(Path("d.wav"), "kick", 120.0, 90.0, "ambiguous")
        )

        assert result.total == 4
        assert result.correct_pct == 25.0
        assert result.half_pct == 25.0
        assert result.double_pct == 25.0
        assert result.ambiguous_pct == 25.0
        assert result.outlier_pct == 0.0
        assert result.octave_error_pct == 50.0

    def test_mean_absolute_error(self):
        from pathlib import Path
        result = BpmEvidenceResult()
        result.records.append(
            BpmSampleRecord(Path("a.wav"), "pulse", 120.0, 120.0, "correct")
        )
        result.records.append(
            BpmSampleRecord(Path("b.wav"), "pulse", 120.0, 100.0, "ambiguous")
        )
        assert result.mean_absolute_error == 10.0

    def test_recommendation_low_octave_error(self):
        from pathlib import Path
        result = BpmEvidenceResult()
        for _ in range(10):
            result.records.append(
                BpmSampleRecord(Path("x.wav"), "pulse", 120.0, 120.0, "correct")
            )
        assert "low_octave_error" in result.recommendation()

    def test_recommendation_moderate_octave_error(self):
        from pathlib import Path
        result = BpmEvidenceResult()
        for _ in range(8):
            result.records.append(
                BpmSampleRecord(Path("x.wav"), "pulse", 120.0, 120.0, "correct")
            )
        for _ in range(2):
            result.records.append(
                BpmSampleRecord(Path("x.wav"), "pulse", 120.0, 60.0, "half")
            )
        assert "heuristic_clamp" in result.recommendation()

    def test_recommendation_high_octave_error(self):
        from pathlib import Path
        result = BpmEvidenceResult()
        for _ in range(3):
            result.records.append(
                BpmSampleRecord(Path("x.wav"), "pulse", 120.0, 120.0, "correct")
            )
        for _ in range(7):
            result.records.append(
                BpmSampleRecord(Path("x.wav"), "pulse", 120.0, 60.0, "half")
            )
        assert "profile_or_ensemble" in result.recommendation()


def test_run_bpm_evidence_produces_complete_records(tmp_path):
    work_dir = tmp_path / "bpm-evid"
    result = run_bpm_evidence(work_dir, bpm_candidates=(60, 120))

    assert result.total == 4
    variants = {r.variant for r in result.records}
    assert variants == {"pulse", "kick"}

    for r in result.records:
        assert r.label_bpm in (60.0, 120.0)
        assert r.error_class in {"correct", "half", "double", "ambiguous", "outlier"}
        assert r.fixture_path.exists()

    assert result.correct_pct >= 0.0
    assert result.octave_error_pct >= 0.0
    assert isinstance(result.recommendation(), str)
