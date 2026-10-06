"""Frozen tests for AQ3 onset/attack candidate comparison harness (#997).

TEST FREEZE: these assertions define the compare contract. Fix the harness,
not these expectations, when they turn red.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import aq3_onset_attack_baseline as baseline
from src import aq3_onset_attack_candidate_compare as compare
from src import aq3_timing_corpus as corpus
from src import gesture_analysis
from src import workbench_attack_suggest as attack_suggest


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_compare_identity_constants_are_frozen() -> None:
    assert compare.DOCUMENT_TYPE == "sample-brain.aq3.onset-attack-candidate-compare.v1"
    assert compare.SCHEMA_VERSION == "1.0.0"
    assert compare.CORPUS_ID == corpus.CORPUS_ID
    assert compare.TOLERANCE_CANDIDATES_MS == corpus.TOLERANCE_CANDIDATES_MS
    assert compare.EXIT_REPRODUCIBLE == "AQ3_ONSET_ATTACK_CANDIDATE_COMPARE_REPRODUCIBLE"
    assert compare.EXIT_INCOMPLETE == "AQ3_ONSET_ATTACK_CANDIDATE_COMPARE_INCOMPLETE"
    assert compare.BASELINE_DOCUMENT_TYPE == baseline.DOCUMENT_TYPE
    assert compare.ONSET_SURFACE == baseline.ONSET_SURFACE
    assert compare.ATTACK_SURFACE == baseline.ATTACK_SURFACE


def test_frozen_candidate_registry_has_at_most_four_documented_adapters() -> None:
    candidates = compare.list_onset_attack_candidates()
    assert 3 <= len(candidates) <= 4
    ids = [c.candidate_id for c in candidates]
    assert len(ids) == len(set(ids))
    # Baseline identity must be present and match current module constants.
    baseline_c = compare.candidate_by_id("gesture_attack.baseline.v1")
    assert baseline_c.onset_delta == pytest.approx(gesture_analysis._ONSET_DELTA)
    assert baseline_c.onset_wait_frames == gesture_analysis._ONSET_WAIT_FRAMES
    assert baseline_c.min_onset_gap_sec == pytest.approx(
        gesture_analysis._MIN_ONSET_GAP_SEC
    )
    assert baseline_c.attack_energy_ratio == pytest.approx(
        attack_suggest._ENERGY_RATIO_THRESHOLD
    )
    assert baseline_c.attack_peak_fraction == pytest.approx(
        attack_suggest._PEAK_FRACTION_THRESHOLD
    )
    assert baseline_c.attack_frame_ms == attack_suggest._FRAME_MS
    for candidate in candidates:
        assert candidate.description.strip()
        public = compare.candidate_public(candidate)
        assert public["candidate_id"] == candidate.candidate_id
        assert "onset_delta" in public
        assert "attack_energy_ratio" in public


def test_candidate_by_id_rejects_unknown() -> None:
    with pytest.raises(compare.Aq3OnsetAttackCandidateCompareError, match="unknown"):
        compare.candidate_by_id("not.a.real.candidate")


def test_predict_clip_for_candidate_uses_declared_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Adapters must thread declared config into onset/attack surfaces."""
    work = tmp_path / "corpus"
    corpus.generate_aq3_timing_corpus(work, repo_root=REPO_ROOT)
    clip_id = "aq3-synth-soft-attack-cal-001"
    gt = json.loads((work / "gt" / f"{clip_id}.json").read_text(encoding="utf-8"))
    audio = work / "audio" / f"{clip_id}.wav"
    candidate = compare.candidate_by_id("gesture.onset_delta.0.04")

    seen: dict[str, object] = {}

    def fake_analyze(path, **kwargs):  # type: ignore[no-untyped-def]
        seen["onset"] = kwargs
        return gesture_analysis.GestureAnalysis(
            events=(),
            sample_rate=44100,
            duration_sec=0.5,
            feature_dim=gesture_analysis.FEATURE_DIM,
            status="empty",
        )

    def fake_attack(path, **kwargs):  # type: ignore[no-untyped-def]
        seen["attack"] = kwargs
        return None

    monkeypatch.setattr(compare, "analyze_gesture_audio", fake_analyze)
    monkeypatch.setattr(compare, "suggest_attack_ms", fake_attack)

    row = compare.predict_clip_for_candidate(audio, gt, candidate)
    assert row["clip_id"] == clip_id
    assert row["candidate_id"] == candidate.candidate_id
    assert seen["onset"]["onset_delta"] == pytest.approx(candidate.onset_delta)
    assert seen["onset"]["onset_wait_frames"] == candidate.onset_wait_frames
    assert seen["onset"]["min_onset_gap_sec"] == pytest.approx(
        candidate.min_onset_gap_sec
    )
    assert seen["attack"]["energy_ratio_threshold"] == pytest.approx(
        candidate.attack_energy_ratio
    )
    assert seen["attack"]["peak_fraction_threshold"] == pytest.approx(
        candidate.attack_peak_fraction
    )
    assert seen["attack"]["frame_ms"] == candidate.attack_frame_ms


def test_run_rejects_output_inside_repo(tmp_path: Path) -> None:
    work = tmp_path / "corpus"
    corpus.generate_aq3_timing_corpus(work, repo_root=REPO_ROOT)
    inside = REPO_ROOT / ".pytest_aq3_onset_attack_compare_should_not_exist.json"
    with pytest.raises(ValueError, match="outside"):
        compare.run_aq3_onset_attack_candidate_compare(
            work_dir=work,
            output_path=inside,
            repo_root=REPO_ROOT,
        )


def test_run_writes_external_json_with_per_candidate_metrics(tmp_path: Path) -> None:
    work = tmp_path / "corpus"
    out = tmp_path / "aq3-onset-attack-compare.json"
    corpus.generate_aq3_timing_corpus(work, repo_root=REPO_ROOT)

    result = compare.run_aq3_onset_attack_candidate_compare(
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
    assert result["tolerance_candidates_ms"] == list(corpus.TOLERANCE_CANDIDATES_MS)
    assert result["no_tuning_on_test"] is True
    assert result["partition_policy"]["CALIBRATION"] == "DEVELOPMENT/CALIBRATION"
    assert result["partition_policy"]["TEST"] == "TEST/HOLDOUT"
    assert result["baseline_document_type"] == baseline.DOCUMENT_TYPE

    candidate_ids = {c["candidate_id"] for c in result["candidates"]}
    expected_ids = {c.candidate_id for c in compare.list_onset_attack_candidates()}
    assert candidate_ids == expected_ids

    for entry in result["candidates"]:
        assert "description" in entry
        assert set(entry["splits"]) == {"CALIBRATION", "TEST"}
        for split_name in ("CALIBRATION", "TEST"):
            split = entry["splits"][split_name]
            assert "aq3.onset" in split
            assert "aq3.attack" in split
            assert "aq3.gesture" in split
            onset = split["aq3.onset"]
            assert "by_tolerance" in onset
            for tol in corpus.TOLERANCE_CANDIDATES_MS:
                block = onset["by_tolerance"][str(tol)]
                for field in ("precision", "recall", "f1", "matched", "label_count"):
                    assert field in block
            attack = split["aq3.attack"]
            assert "within_tolerance_rates" in attack
            for tol in corpus.TOLERANCE_CANDIDATES_MS:
                assert str(tol) in attack["within_tolerance_rates"]

    # Portable: no absolute host paths.
    dumped = json.dumps(result)
    assert "D:/" not in dumped
    assert "D:\\" not in dumped
    assert "/Users/" not in dumped
    for key in ("audio_path", "file_path", "sample_path", "work_dir"):
        assert key not in result


def test_baseline_candidate_matches_baseline_harness_metrics(tmp_path: Path) -> None:
    """Fairness: baseline candidate must reproduce baseline harness aggregates."""
    work = tmp_path / "corpus"
    corpus.generate_aq3_timing_corpus(work, repo_root=REPO_ROOT)
    baseline_out = tmp_path / "baseline.json"
    compare_out = tmp_path / "compare.json"

    baseline_result = baseline.run_aq3_onset_attack_baseline(
        work_dir=work,
        output_path=baseline_out,
        repo_root=REPO_ROOT,
        regenerate_corpus=False,
    )
    compare_result = compare.run_aq3_onset_attack_candidate_compare(
        work_dir=work,
        output_path=compare_out,
        repo_root=REPO_ROOT,
        regenerate_corpus=False,
    )

    baseline_entry = next(
        c
        for c in compare_result["candidates"]
        if c["candidate_id"] == "gesture_attack.baseline.v1"
    )
    for split_name in ("CALIBRATION", "TEST"):
        for plane in ("aq3.onset", "aq3.attack"):
            assert (
                baseline_entry["splits"][split_name][plane]
                == baseline_result["splits"][split_name][plane]
            )
