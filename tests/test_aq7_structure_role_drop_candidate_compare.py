"""Frozen tests for AQ7 structure/role/drop candidate comparison (#1028).

TEST FREEZE: these assertions define the compare/freeze contract. Fix the
harness, not these expectations, when they turn red.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from src import aq7_structure_boundary_baseline as boundary_baseline
from src import aq7_structure_role_drop_baseline as role_drop_baseline
from src import aq7_structure_role_drop_candidate_compare as compare
from src import aq7_structure_role_drop_corpus as corpus
from src.arrangement_classifier import (
    ArrangementClassifier,
    ArrangementClassifierConfig,
    DEFAULT_ARRANGEMENT_CLASSIFIER_CONFIG,
)
from src.structure_v1 import StructureV1Config

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_compare_identity_constants_are_frozen() -> None:
    assert compare.DOCUMENT_TYPE == (
        "sample-brain.aq7.structure-role-drop-candidate-compare.v1"
    )
    assert compare.SCHEMA_VERSION == "1.0.0"
    assert compare.CORPUS_ID == corpus.CORPUS_ID
    assert compare.CORPUS_VERSION == corpus.CORPUS_VERSION
    assert compare.BASELINE_CANDIDATE_ID == "aq7.baseline.v1"
    assert compare.EXIT_FROZEN == "AQ7_CANDIDATE_COMPARE_CALIBRATION_FROZEN"
    assert compare.EXIT_KEEP_BASELINE == "AQ7_NO_JUSTIFIED_CANDIDATE_KEEP_BASELINE"
    assert compare.EXIT_INCOMPLETE == "AQ7_CANDIDATE_COMPARE_INCOMPLETE"
    assert compare.SELECTION_PARTITION == "CALIBRATION"
    assert compare.FEATURE_TOGGLE == "N/A"
    assert compare.PRODUCTION_DEFAULTS_CHANGED is False
    assert compare.BOUNDARY_SURFACE_POLICY == "frozen_gt_reference_sections"


def test_frozen_candidate_registry_has_three_to_four_documented_adapters() -> None:
    candidates = compare.list_aq7_candidates()
    assert 3 <= len(candidates) <= 4
    ids = [c.candidate_id for c in candidates]
    assert len(ids) == len(set(ids))
    assert ids[0] == compare.BASELINE_CANDIDATE_ID
    assert candidates[0].is_baseline is True

    baseline = compare.candidate_by_id(compare.BASELINE_CANDIDATE_ID)
    assert baseline.structure_config == StructureV1Config()
    assert baseline.arrangement_config == DEFAULT_ARRANGEMENT_CLASSIFIER_CONFIG

    boundary = compare.candidate_by_id("boundary.min_distance.4")
    assert boundary.hypothesis_ids == ("H-AQ7-1027-01",)
    assert boundary.primary_plane == "aq7.boundary"
    assert boundary.structure_config.min_boundary_distance_bars == 4
    assert boundary.arrangement_config == DEFAULT_ARRANGEMENT_CLASSIFIER_CONFIG

    role = compare.candidate_by_id("role.unknown_margin.0.03")
    assert role.hypothesis_ids == ("H-AQ7-1027-02",)
    assert role.primary_plane == "aq7.role"
    assert role.arrangement_config.unknown_min_margin == pytest.approx(0.03)
    assert role.structure_config == StructureV1Config()

    drop = compare.candidate_by_id("drop.onset_thresh.0.80")
    assert drop.hypothesis_ids == ("H-AQ7-1027-05",)
    assert drop.primary_plane == "aq7.drop_event"
    assert drop.arrangement_config.drop_onset_threshold == pytest.approx(0.80)

    for candidate in candidates:
        assert candidate.description.strip()
        public = compare.candidate_public(candidate)
        assert public["candidate_id"] == candidate.candidate_id
        assert "structure_config" in public
        assert "arrangement_config" in public
        assert public["boundary_surface_policy"] == compare.BOUNDARY_SURFACE_POLICY

    not_selected = {row["hypothesis_id"] for row in compare.SHORTLIST_NOT_SELECTED}
    assert "H-AQ7-1027-03" in not_selected
    assert "H-AQ7-1027-04" in not_selected


def test_candidate_by_id_rejects_unknown() -> None:
    with pytest.raises(compare.Aq7CandidateCompareError, match="unknown"):
        compare.candidate_by_id("not.a.real.candidate")


def test_arrangement_classifier_default_config_matches_historical_knobs() -> None:
    cfg = ArrangementClassifierConfig()
    assert cfg.unknown_min_best_score == pytest.approx(0.45)
    assert cfg.unknown_min_margin == pytest.approx(0.05)
    assert cfg.unknown_min_completeness == pytest.approx(0.5)
    assert cfg.available_min_completeness == pytest.approx(0.75)
    assert cfg.drop_onset_threshold == pytest.approx(0.65)
    assert ArrangementClassifier().config == DEFAULT_ARRANGEMENT_CLASSIFIER_CONFIG


def test_planes_remain_separate_in_public_candidate_schema() -> None:
    for candidate in compare.list_aq7_candidates():
        public = compare.candidate_public(candidate)
        assert public["primary_plane"] in {
            "multi",
            "aq7.boundary",
            "aq7.role",
            "aq7.drop_event",
        }
        # No composite quality score field is authorized on the identity surface.
        assert "aq7_composite" not in public
        assert "global_score" not in public


def _complete_cal(**overrides: object) -> dict:
    """Minimal CALIBRATION block that passes the completeness gate."""
    cal = {
        "n_fixtures": compare.CALIBRATION_FIXTURE_COUNT,
        "aq7.boundary": {
            "n_usable": compare.CALIBRATION_FIXTURE_COUNT,
            "metrics": {
                "precision_1bar": 0.30,
                "recall_1bar": 0.90,
                "extra_rate": 0.70,
                "over_segmentation_rate": 1.0,
                "false_positive_count": 20,
            },
        },
        "aq7.role": {
            "macro_f1": 0.2,
            "unknown_rate": 0.4,
            "support": 17,
            "abstention_count": 0,
            "per_role": {},
        },
        "aq7.drop_event": {
            "f1_1bar": 0.0,
            "matched_count": 0,
            "false_positive_count": 6,
            "coverage": 1.0,
        },
    }
    for key, value in overrides.items():
        cal[key] = value
    return cal


def test_partition_firewall_decision_ignores_test_metrics() -> None:
    # Fabricate CAL where boundary candidate is NOT justified...
    weak_cal = _complete_cal()
    # ...but invent a glowing TEST block that must never drive selection.
    glowing_test = {
        "aq7.boundary": {
            "metrics": {
                "precision_1bar": 0.99,
                "recall_1bar": 0.99,
                "extra_rate": 0.01,
                "over_segmentation_rate": 0.0,
                "false_positive_count": 0,
            }
        },
        "aq7.role": {"macro_f1": 0.99, "unknown_rate": 0.0, "per_role": {}},
        "aq7.drop_event": {
            "f1_1bar": 1.0,
            "matched_count": 10,
            "false_positive_count": 0,
        },
    }
    del glowing_test  # explicit: TEST metrics are not passed into decide_*

    calibration_by_id = {
        candidate.candidate_id: deepcopy(weak_cal)
        for candidate in compare.list_aq7_candidates()
    }
    decision = compare.decide_calibration_freeze(
        candidates=compare.list_aq7_candidates(),
        calibration_by_id=calibration_by_id,
    )
    assert decision["selection_partition"] == "CALIBRATION"
    assert decision["test_used_for_selection"] is False
    assert decision["exit_token"] == compare.EXIT_KEEP_BASELINE
    assert decision["frozen_candidate_id"] == compare.BASELINE_CANDIDATE_ID


def test_incomplete_role_drop_measurements_refuse_freeze() -> None:
    """Codex P1: boundary-only usable CAL must not emit KEEP_BASELINE."""
    incomplete = _complete_cal(
        **{
            "aq7.role": {
                "macro_f1": None,
                "support": 0,
                "abstention_count": compare.CALIBRATION_FIXTURE_COUNT,
                "per_role": {},
            },
            "aq7.drop_event": {
                "f1_1bar": None,
                "matched_count": None,
                "false_positive_count": None,
                "coverage": 0.0,
            },
        }
    )
    assert compare.calibration_measurement_complete(incomplete)["complete"] is False
    calibration_by_id = {
        candidate.candidate_id: deepcopy(incomplete)
        for candidate in compare.list_aq7_candidates()
    }
    decision = compare.decide_calibration_freeze(
        candidates=compare.list_aq7_candidates(),
        calibration_by_id=calibration_by_id,
    )
    assert decision["exit_token"] == compare.EXIT_INCOMPLETE
    assert decision["frozen_candidate_id"] is None


def test_partial_role_hold_or_drop_coverage_is_incomplete() -> None:
    """Codex follow-up: one successful fixture must not authorize freeze."""
    partial_role = _complete_cal()
    partial_role["aq7.role"] = {
        "macro_f1": 0.2,
        "support": 3,
        "abstention_count": 1,
        "per_role": {},
    }
    assert compare.calibration_measurement_complete(partial_role)["complete"] is False

    partial_drop = _complete_cal()
    partial_drop["aq7.drop_event"] = {
        "f1_1bar": 0.0,
        "matched_count": 0,
        "false_positive_count": 1,
        "coverage": 1.0 / compare.CALIBRATION_FIXTURE_COUNT,
    }
    assert compare.calibration_measurement_complete(partial_drop)["complete"] is False


def test_single_usable_boundary_fixture_is_incomplete() -> None:
    thin = _complete_cal()
    thin["aq7.boundary"] = {
        "n_usable": 1,
        "metrics": thin["aq7.boundary"]["metrics"],
    }
    assert compare.calibration_measurement_complete(thin)["complete"] is False


def test_drop_fp_only_reduction_is_not_justified() -> None:
    baseline_cal = {
        "aq7.boundary": {"metrics": {}},
        "aq7.role": {"macro_f1": 0.2, "per_role": {}},
        "aq7.drop_event": {
            "f1_1bar": 0.0,
            "matched_count": 0,
            "false_positive_count": 6,
            "missed_count": 1,
        },
    }
    candidate_cal = {
        "aq7.boundary": {"metrics": {}},
        "aq7.role": {"macro_f1": 0.2, "per_role": {}},
        "aq7.drop_event": {
            "f1_1bar": 0.0,
            "matched_count": 0,
            "false_positive_count": 1,
            "missed_count": 1,
        },
    }
    drop = compare.candidate_by_id("drop.onset_thresh.0.80")
    verdict = compare.candidate_justified_on_calibration(
        drop, baseline_cal=baseline_cal, candidate_cal=candidate_cal
    )
    assert verdict["justified"] is False
    assert verdict["false_positive_reduced"] is True


def test_boundary_candidate_justified_when_precision_up_without_recall_collapse() -> None:
    baseline_cal = {
        "aq7.boundary": {
            "metrics": {
                "precision_1bar": 0.34,
                "recall_1bar": 0.92,
                "extra_rate": 0.66,
                "over_segmentation_rate": 1.0,
                "false_positive_count": 23,
            }
        },
        "aq7.role": {"macro_f1": 0.2, "per_role": {}},
        "aq7.drop_event": {"f1_1bar": 0.0, "matched_count": 0},
    }
    candidate_cal = {
        "aq7.boundary": {
            "metrics": {
                "precision_1bar": 0.50,
                "recall_1bar": 0.90,
                "extra_rate": 0.40,
                "over_segmentation_rate": 0.5,
                "false_positive_count": 10,
            }
        },
        "aq7.role": {"macro_f1": 0.2, "per_role": {}},
        "aq7.drop_event": {"f1_1bar": 0.0, "matched_count": 0},
    }
    boundary = compare.candidate_by_id("boundary.min_distance.4")
    verdict = compare.candidate_justified_on_calibration(
        boundary, baseline_cal=baseline_cal, candidate_cal=candidate_cal
    )
    assert verdict["justified"] is True


def test_role_drop_path_does_not_invent_or_move_boundaries(tmp_path: Path) -> None:
    """Boundary-ownership: role/drop consume frozen GT geometry only."""
    work = tmp_path / "corpus"
    corpus.generate_aq7_structure_role_drop_corpus(work, repo_root=REPO_ROOT)
    fixture_id = "aq7-synth-simple-clean-cal-001"
    gt = json.loads((work / "gt" / f"{fixture_id}.json").read_text(encoding="utf-8"))
    audio = work / "audio" / f"{fixture_id}.wav"
    candidate = compare.candidate_by_id("role.unknown_margin.0.03")

    row = compare.predict_fixture_for_candidate(
        audio_path=audio, gt=gt, candidate=candidate
    )
    assert row["boundary_surface_policy"] == compare.BOUNDARY_SURFACE_POLICY
    role_drop = row["role_drop"]
    assert role_drop.get("hold_kind") is None

    ref_sections = role_drop_baseline.frozen_reference_sections_from_gt(gt)
    role_items = (role_drop.get("role") or {}).get("role_items") or []
    by_id = {item["section_id"]: item for item in role_items}
    for section in ref_sections:
        if section.get("excluded_by_ambiguous_boundary"):
            continue
        item = by_id[section["section_id"]]
        assert int(item["start_bar"]) == int(section["start_bar"])
        assert int(item["end_bar"]) == int(section["end_bar"])

    # Role candidate must not alter StructureV1 boundary identity knobs.
    assert candidate.structure_config == StructureV1Config()


def test_hard_case_deltas_keep_planes_separate() -> None:
    baseline_cal = {
        "aq7.boundary": {
            "metrics": {
                "precision_1bar": 0.3,
                "recall_1bar": 0.9,
                "extra_rate": 0.7,
                "over_segmentation_rate": 1.0,
                "false_positive_count": 20,
            }
        },
        "aq7.role": {
            "macro_f1": 0.2,
            "unknown_rate": 0.4,
            "per_role": {"intro": {"recall": 0.0, "f1": 0.0}},
        },
        "aq7.drop_event": {
            "f1_1bar": 0.0,
            "matched_count": 0,
            "false_positive_count": 6,
            "missed_count": 1,
        },
    }
    candidate_cal = {
        "aq7.boundary": {
            "metrics": {
                "precision_1bar": 0.4,
                "recall_1bar": 0.9,
                "extra_rate": 0.5,
                "over_segmentation_rate": 0.5,
                "false_positive_count": 10,
            }
        },
        "aq7.role": {
            "macro_f1": 0.25,
            "unknown_rate": 0.3,
            "per_role": {"intro": {"recall": 0.5, "f1": 0.4}},
        },
        "aq7.drop_event": {
            "f1_1bar": 0.0,
            "matched_count": 0,
            "false_positive_count": 2,
            "missed_count": 1,
        },
    }
    deltas = compare.hard_case_deltas(
        baseline_cal=baseline_cal, candidate_cal=candidate_cal
    )
    assert deltas["partition"] == "CALIBRATION"
    assert set(deltas) >= {"partition", "aq7.boundary", "aq7.role", "aq7.drop_event"}
    assert deltas["aq7.boundary"]["precision_1bar_delta"] == pytest.approx(0.1)
    assert deltas["aq7.role"]["macro_f1_delta"] == pytest.approx(0.05)
    assert deltas["aq7.drop_event"]["false_positive_count_delta"] == -4
    assert "composite" not in deltas


def test_end_to_end_compare_emits_machine_readable_freeze(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = tmp_path / "aq7-compare-corpus"
    out = tmp_path / "aq7-compare.json"
    # Force outside-repo checks to treat tmp as allowed by pointing repo_root
    # at a sibling placeholder that is not an ancestor of work/out.
    fake_repo = tmp_path / "fake-repo"
    fake_repo.mkdir()
    monkeypatch.setattr(compare, "_REPO_ROOT_DEFAULT", fake_repo)
    monkeypatch.setattr(corpus, "_REPO_ROOT_DEFAULT", fake_repo)

    # Corpus generator also checks outside-repo; patch its assert.
    monkeypatch.setattr(
        compare,
        "assert_work_dir_outside_repo",
        lambda work_dir, root: None,
    )
    monkeypatch.setattr(
        corpus,
        "assert_work_dir_outside_repo",
        lambda work_dir, root: None,
    )

    result = compare.run_aq7_structure_role_drop_candidate_compare(
        work_dir=work,
        output_path=out,
        repo_root=fake_repo,
    )
    assert out.is_file()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["document_type"] == compare.DOCUMENT_TYPE
    assert payload["corpus_id"] == corpus.CORPUS_ID
    assert payload["corpus_version"] == corpus.CORPUS_VERSION
    assert payload["baseline_candidate_id"] == compare.BASELINE_CANDIDATE_ID
    assert payload["selection_partition"] == "CALIBRATION"
    assert payload["test_used_for_selection"] is False
    assert payload["no_tuning_on_test"] is True
    assert payload["feature_toggle"] == "N/A"
    assert payload["production_defaults_changed"] is False
    assert payload["exit_token"] in {
        compare.EXIT_FROZEN,
        compare.EXIT_KEEP_BASELINE,
        compare.EXIT_INCOMPLETE,
    }
    assert payload["exit_status"] == payload["exit_token"]
    assert 3 <= payload["candidate_count"] <= 4
    assert len(payload["candidates"]) == payload["candidate_count"]

    decision = payload["decision"]
    assert decision["selection_partition"] == "CALIBRATION"
    assert decision["test_used_for_selection"] is False
    assert decision["exit_token"] == payload["exit_token"]
    if payload["exit_token"] == compare.EXIT_KEEP_BASELINE:
        assert decision["frozen_candidate_id"] == compare.BASELINE_CANDIDATE_ID
        assert decision["frozen_config"]["candidate_id"] == compare.BASELINE_CANDIDATE_ID
    elif payload["exit_token"] == compare.EXIT_FROZEN:
        assert decision["frozen_candidate_id"]
        assert decision["frozen_config"]["candidate_id"] == decision["frozen_candidate_id"]

    for entry in payload["candidates"]:
        assert "splits" in entry
        assert "CALIBRATION" in entry["splits"]
        assert "TEST" in entry["splits"]
        cal = entry["splits"]["CALIBRATION"]
        assert "aq7.boundary" in cal
        assert "aq7.role" in cal
        assert "aq7.drop_event" in cal
        # Plane separation: no composite score.
        assert "aq7_composite" not in cal

    # Baseline identity surfaces reused.
    assert (
        payload["boundary_baseline_candidate_id"]
        == boundary_baseline.CANDIDATE_ID
    )
    assert (
        payload["role_drop_baseline_candidate_id"]
        == role_drop_baseline.CANDIDATE_ID
    )


def test_deterministic_repeat_of_same_candidate_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    work = tmp_path / "corpus"
    fake_repo = tmp_path / "fake-repo"
    fake_repo.mkdir()
    monkeypatch.setattr(corpus, "assert_work_dir_outside_repo", lambda *a, **k: None)
    corpus.generate_aq7_structure_role_drop_corpus(work, repo_root=fake_repo)
    fixture_id = "aq7-synth-simple-clean-cal-001"
    gt = json.loads((work / "gt" / f"{fixture_id}.json").read_text(encoding="utf-8"))
    audio = work / "audio" / f"{fixture_id}.wav"
    candidate = compare.candidate_by_id("boundary.min_distance.4")

    first = compare.predict_fixture_for_candidate(
        audio_path=audio, gt=gt, candidate=candidate
    )
    second = compare.predict_fixture_for_candidate(
        audio_path=audio, gt=gt, candidate=candidate
    )
    assert first["boundary"]["predicted_bars"] == second["boundary"]["predicted_bars"]
    assert first["boundary"]["precision_1bar"] == second["boundary"]["precision_1bar"]
    assert (first["role_drop"].get("role") or {}).get("macro_f1") == (
        second["role_drop"].get("role") or {}
    ).get("macro_f1")
