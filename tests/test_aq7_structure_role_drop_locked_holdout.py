"""Frozen tests for AQ7 locked TEST/HOLDOUT evaluation (#1030).

TEST FREEZE: these assertions define the holdout/firewall/gate contract.
Fix the harness, not these expectations, when they turn red.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from src import aq7_structure_role_drop_candidate_compare as compare
from src import aq7_structure_role_drop_corpus as corpus
from src import aq7_structure_role_drop_locked_holdout as holdout
from src.arrangement_classifier import DEFAULT_ARRANGEMENT_CLASSIFIER_CONFIG
from src.structure_v1 import StructureV1Config

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_holdout_identity_constants_are_frozen() -> None:
    assert holdout.DOCUMENT_TYPE == (
        "sample-brain.aq7.structure-role-drop-locked-holdout.v1"
    )
    assert holdout.SCHEMA_VERSION == "1.0.0"
    assert holdout.ISSUE_ID == 1030
    assert holdout.AQ7_SLICE == "locked_holdout_evaluation"
    assert holdout.FROZEN_CANDIDATE_ID == "aq7.baseline.v1"
    assert holdout.FREEZE_TOKEN == "AQ7_NO_JUSTIFIED_CANDIDATE_KEEP_BASELINE"
    assert holdout.EVALUATED_PARTITION == "TEST"
    assert holdout.TEST_FIXTURE_COUNT == 4
    assert holdout.CORPUS_ID == corpus.CORPUS_ID
    assert holdout.CORPUS_VERSION == corpus.CORPUS_VERSION
    assert holdout.EXIT_EVALUATED == "AQ7_LOCKED_HOLDOUT_EVALUATED"
    assert holdout.EXIT_PARTIAL_HOLD == "AQ7_HOLDOUT_PARTIAL_HOLD"
    assert holdout.EXIT_INCOMPLETE == "AQ7_HOLDOUT_INCOMPLETE"
    assert holdout.FEATURE_TOGGLE == "N/A"
    assert holdout.PRODUCTION_DEFAULTS_CHANGED is False
    assert holdout.CANDIDATE_EQUALS_BASELINE is True


def test_frozen_candidate_matches_1028_baseline_retention() -> None:
    frozen = holdout.frozen_candidate()
    assert frozen.candidate_id == holdout.FROZEN_CANDIDATE_ID
    assert frozen.is_baseline is True
    assert frozen.structure_config == StructureV1Config()
    assert frozen.arrangement_config == DEFAULT_ARRANGEMENT_CLASSIFIER_CONFIG
    assert frozen.candidate_id == compare.BASELINE_CANDIDATE_ID
    holdout.assert_frozen_config_fingerprint(frozen)


def test_frozen_config_fingerprint_rejects_live_default_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex P1 residual: candidate id alone must not survive knob drift."""
    drifted = compare.Aq7Candidate(
        candidate_id=holdout.FROZEN_CANDIDATE_ID,
        hypothesis_ids=(),
        primary_plane="multi",
        structure_config=StructureV1Config(min_boundary_distance_bars=99),
        arrangement_config=DEFAULT_ARRANGEMENT_CLASSIFIER_CONFIG,
        description="drifted",
        is_baseline=True,
    )
    monkeypatch.setattr(holdout, "candidate_by_id", lambda _cid: drifted)
    with pytest.raises(holdout.Aq7LockedHoldoutError, match="fingerprint|drifted"):
        holdout.frozen_candidate()


def test_assert_freeze_identity_accepts_authorized_freeze() -> None:
    holdout.assert_freeze_identity(
        freeze_token=holdout.FREEZE_TOKEN,
        candidate_id=holdout.FROZEN_CANDIDATE_ID,
    )


def test_assert_freeze_identity_rejects_wrong_token() -> None:
    with pytest.raises(holdout.Aq7LockedHoldoutError, match="freeze_token"):
        holdout.assert_freeze_identity(
            freeze_token="AQ7_CANDIDATE_COMPARE_CALIBRATION_FROZEN",
            candidate_id=holdout.FROZEN_CANDIDATE_ID,
        )


def test_assert_freeze_identity_rejects_wrong_candidate() -> None:
    with pytest.raises(holdout.Aq7LockedHoldoutError, match="candidate"):
        holdout.assert_freeze_identity(
            freeze_token=holdout.FREEZE_TOKEN,
            candidate_id="boundary.min_distance.4",
        )


def test_rejected_calibration_candidates_are_not_evaluable() -> None:
    for rejected_id in (
        "boundary.min_distance.4",
        "role.unknown_margin.0.03",
        "drop.onset_thresh.0.80",
    ):
        with pytest.raises(holdout.Aq7LockedHoldoutError, match="rejected|not authorized"):
            holdout.resolve_evaluable_candidate(rejected_id)


def test_post_holdout_tuning_path_is_forbidden() -> None:
    with pytest.raises(holdout.Aq7LockedHoldoutError, match="tuning|forbidden"):
        holdout.request_post_holdout_tuning(
            reason="threshold chase after reveal",
            proposed_candidate_id="boundary.min_distance.4",
        )


def test_same_identity_deltas_are_zero() -> None:
    metrics = {
        "precision_1bar": 0.4,
        "recall_1bar": 0.8,
        "macro_f1": 0.5,
        "f1_1bar": 0.0,
        "false_positive_count": 2,
    }
    deltas = holdout.same_identity_plane_deltas(metrics)
    assert deltas["candidate_equals_baseline"] is True
    assert deltas["precision_1bar_delta"] == 0.0
    assert deltas["recall_1bar_delta"] == 0.0
    assert deltas["macro_f1_delta"] == 0.0
    assert deltas["f1_1bar_delta"] == 0.0
    assert deltas["false_positive_count_delta"] == 0


def _test_plane_block(
    *,
    n_usable: int = 3,
    n_hold: int = 1,
    n_unauthorized: int = 0,
    coverage: float = 0.75,
    metrics: dict | None = None,
    hold_reasons: list[str] | None = None,
    unauthorized_reasons: list[str] | None = None,
) -> dict:
    return {
        "n_fixtures": holdout.TEST_FIXTURE_COUNT,
        "n_usable": n_usable,
        "n_hold": n_hold,
        "n_unauthorized": n_unauthorized,
        "coverage": coverage,
        "metrics": metrics
        or {
            "precision_1bar": 0.3,
            "recall_1bar": 0.8,
            "macro_f1": 0.4,
            "f1_1bar": 0.0,
            "false_positive_count": 2,
        },
        "hold_reasons": hold_reasons or ["BEATGRID_PROVENANCE_LIMITATION"],
        "unauthorized_reasons": unauthorized_reasons or [],
        "provenance_ok": True,
    }


def test_plane_gate_measured_when_full_usable_no_hold() -> None:
    block = _test_plane_block(n_usable=4, n_hold=0, coverage=1.0, hold_reasons=[])
    gate = holdout.resolve_plane_gate(plane="aq7.boundary", test_block=block)
    assert gate["outcome"] == "MEASURED"


def test_plane_gate_hold_when_beatgrid_limitation_present() -> None:
    gate = holdout.resolve_plane_gate(
        plane="aq7.role", test_block=_test_plane_block()
    )
    assert gate["outcome"] == "HOLD"
    assert "BEATGRID_PROVENANCE_LIMITATION" in gate["hold_reasons"]


def test_plane_gate_incomplete_without_usable_or_authorized_hold() -> None:
    block = _test_plane_block(
        n_usable=0,
        n_hold=0,
        coverage=0.0,
        hold_reasons=[],
        metrics={},
    )
    gate = holdout.resolve_plane_gate(plane="aq7.drop_event", test_block=block)
    assert gate["outcome"] == "INCOMPLETE"


def test_plane_gate_incomplete_when_unauthorized_failure_beside_beatgrid_hold() -> None:
    """Codex P1: BeatGrid HOLD must not mask analyzer/harness failures."""
    block = _test_plane_block(
        n_usable=2,
        n_hold=1,
        n_unauthorized=1,
        coverage=0.5,
        hold_reasons=["BEATGRID_PROVENANCE_LIMITATION"],
        unauthorized_reasons=["ANALYZER_FEATURE_LIMITATION"],
    )
    gate = holdout.resolve_plane_gate(plane="aq7.boundary", test_block=block)
    assert gate["outcome"] == "INCOMPLETE"
    assert gate["n_unauthorized"] == 1
    assert "ANALYZER_FEATURE_LIMITATION" in gate["unauthorized_reasons"]
    assert (
        holdout.resolve_holdout_exit(
            gates={
                "aq7.boundary": gate,
                "aq7.role": {"outcome": "HOLD"},
                "aq7.drop_event": {"outcome": "HOLD"},
            },
            freeze_ok=True,
            partition_complete=True,
        )
        == holdout.EXIT_INCOMPLETE
    )


def test_plane_gate_incomplete_without_provenance() -> None:
    block = _test_plane_block()
    block["provenance_ok"] = False
    gate = holdout.resolve_plane_gate(plane="aq7.boundary", test_block=block)
    assert gate["outcome"] == "INCOMPLETE"


def test_overall_exit_partial_hold_when_any_plane_holds() -> None:
    gates = {
        "aq7.boundary": {"outcome": "MEASURED"},
        "aq7.role": {"outcome": "HOLD"},
        "aq7.drop_event": {"outcome": "MEASURED"},
    }
    assert (
        holdout.resolve_holdout_exit(gates=gates, freeze_ok=True, partition_complete=True)
        == holdout.EXIT_PARTIAL_HOLD
    )


def test_overall_exit_evaluated_when_all_planes_measured() -> None:
    gates = {
        "aq7.boundary": {"outcome": "MEASURED"},
        "aq7.role": {"outcome": "MEASURED"},
        "aq7.drop_event": {"outcome": "MEASURED"},
    }
    assert (
        holdout.resolve_holdout_exit(gates=gates, freeze_ok=True, partition_complete=True)
        == holdout.EXIT_EVALUATED
    )


def test_overall_exit_incomplete_on_plane_or_partition_failure() -> None:
    gates = {
        "aq7.boundary": {"outcome": "INCOMPLETE"},
        "aq7.role": {"outcome": "MEASURED"},
        "aq7.drop_event": {"outcome": "MEASURED"},
    }
    assert (
        holdout.resolve_holdout_exit(gates=gates, freeze_ok=True, partition_complete=True)
        == holdout.EXIT_INCOMPLETE
    )
    assert (
        holdout.resolve_holdout_exit(
            gates={
                "aq7.boundary": {"outcome": "MEASURED"},
                "aq7.role": {"outcome": "MEASURED"},
                "aq7.drop_event": {"outcome": "MEASURED"},
            },
            freeze_ok=True,
            partition_complete=False,
        )
        == holdout.EXIT_INCOMPLETE
    )
    assert (
        holdout.resolve_holdout_exit(
            gates={
                "aq7.boundary": {"outcome": "MEASURED"},
                "aq7.role": {"outcome": "MEASURED"},
                "aq7.drop_event": {"outcome": "MEASURED"},
            },
            freeze_ok=False,
            partition_complete=True,
        )
        == holdout.EXIT_INCOMPLETE
    )


def test_plane_hold_is_not_compensated_by_other_planes() -> None:
    """Strong boundary/role must not flip overall exit past PARTIAL_HOLD."""
    gates = {
        "aq7.boundary": {"outcome": "MEASURED", "metrics": {"precision_1bar": 0.99}},
        "aq7.role": {"outcome": "MEASURED", "metrics": {"macro_f1": 0.99}},
        "aq7.drop_event": {
            "outcome": "HOLD",
            "hold_reasons": ["BEATGRID_PROVENANCE_LIMITATION"],
        },
    }
    assert (
        holdout.resolve_holdout_exit(gates=gates, freeze_ok=True, partition_complete=True)
        == holdout.EXIT_PARTIAL_HOLD
    )


def test_firewall_block_forbids_post_reveal_mutations() -> None:
    block = holdout.test_holdout_firewall_block()
    assert block["post_reveal_tuning"] is False
    assert block["annotation_changes"] is False
    assert block["partition_changes"] is False
    assert block["tolerance_changes"] is False
    assert block["test_used_for_selection"] is False
    assert block["no_tuning_on_test"] is True
    assert block["evaluated_partition"] == "TEST"
    assert block["selection_partition"] is None


def test_end_to_end_locked_holdout_emits_machine_readable_gates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = tmp_path / "aq7-holdout-corpus"
    out = tmp_path / "aq7-locked-holdout.json"
    fake_repo = tmp_path / "fake-repo"
    fake_repo.mkdir()
    monkeypatch.setattr(holdout, "_REPO_ROOT_DEFAULT", fake_repo)
    monkeypatch.setattr(corpus, "_REPO_ROOT_DEFAULT", fake_repo)
    monkeypatch.setattr(compare, "_REPO_ROOT_DEFAULT", fake_repo)
    monkeypatch.setattr(
        holdout, "assert_work_dir_outside_repo", lambda work_dir, root: None
    )
    monkeypatch.setattr(
        corpus, "assert_work_dir_outside_repo", lambda work_dir, root: None
    )
    monkeypatch.setattr(
        compare, "assert_work_dir_outside_repo", lambda work_dir, root: None
    )

    result = holdout.run_aq7_structure_role_drop_locked_holdout(
        work_dir=work,
        output_path=out,
        repo_root=fake_repo,
    )
    assert out.is_file()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["exit_token"] == result["exit_token"]
    assert payload["frozen_candidate_id"] == result["frozen_candidate_id"]
    assert payload["document_type"] == holdout.DOCUMENT_TYPE
    assert payload["schema_version"] == holdout.SCHEMA_VERSION
    assert payload["issue_id"] == 1030
    assert payload["aq7_slice"] == holdout.AQ7_SLICE
    assert payload["frozen_candidate_id"] == holdout.FROZEN_CANDIDATE_ID
    assert payload["freeze_token"] == holdout.FREEZE_TOKEN
    assert payload["freeze_provenance"]["source_issue"] == 1028
    assert payload["freeze_provenance"]["freeze_token"] == holdout.FREEZE_TOKEN
    assert payload["evaluated_partition"] == "TEST"
    assert payload["corpus_id"] == corpus.CORPUS_ID
    assert payload["corpus_version"] == corpus.CORPUS_VERSION
    assert "code_head_identity" in payload
    assert payload["candidate_equals_baseline"] is True
    assert payload["feature_toggle"] == "N/A"
    assert payload["production_defaults_changed"] is False
    assert payload["no_tuning_on_test"] is True
    assert payload["test_used_for_selection"] is False

    firewall = payload["test_holdout_firewall"]
    assert firewall["post_reveal_tuning"] is False
    assert firewall["annotation_changes"] is False
    assert firewall["partition_changes"] is False
    assert firewall["tolerance_changes"] is False

    gates = payload["gates"]
    assert set(gates) >= {"aq7.boundary", "aq7.role", "aq7.drop_event"}
    for plane in ("aq7.boundary", "aq7.role", "aq7.drop_event"):
        gate = gates[plane]
        assert gate["frozen_config_identity"] == holdout.FROZEN_CANDIDATE_ID
        assert gate["partition_identity"] == "TEST"
        assert "coverage" in gate
        assert "hold_records" in gate
        assert "baseline_metrics" in gate
        assert "holdout_metrics" in gate
        assert "regressions" in gate
        assert gate["regressions"]["candidate_equals_baseline"] is True
        assert "difficult_slice_evidence" in gate
        assert gate["outcome"] in {"MEASURED", "HOLD", "INCOMPLETE"}
        assert "aq7_composite" not in gate

    assert payload["exit_token"] in {
        holdout.EXIT_EVALUATED,
        holdout.EXIT_PARTIAL_HOLD,
        holdout.EXIT_INCOMPLETE,
    }
    assert payload["exit_status"] == payload["exit_token"]
    # Frozen corpus includes beatgrid_hold on TEST → expect PARTIAL_HOLD.
    assert payload["exit_token"] == holdout.EXIT_PARTIAL_HOLD

    cvb = payload["candidate_vs_baseline"]
    assert cvb["candidate_id"] == holdout.FROZEN_CANDIDATE_ID
    assert cvb["baseline_id"] == holdout.FROZEN_CANDIDATE_ID
    assert cvb["candidate_equals_baseline"] is True

    splits = payload["splits"]
    assert "CALIBRATION" in splits
    assert "TEST" in splits
    for split_name in ("CALIBRATION", "TEST"):
        block = splits[split_name]
        assert "aq7.boundary" in block
        assert "aq7.role" in block
        assert "aq7.drop_event" in block
        assert "aq7_composite" not in block

    assert payload["determinism"]["by_reference"] is True
    assert payload["runtime"]["by_reference"] is True
    assert payload["runtime"].get("diagnostic_only") is True


def test_wrong_freeze_in_runner_kwargs_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = tmp_path / "corpus"
    out = tmp_path / "out.json"
    fake_repo = tmp_path / "fake-repo"
    fake_repo.mkdir()
    monkeypatch.setattr(holdout, "assert_work_dir_outside_repo", lambda *a, **k: None)
    monkeypatch.setattr(corpus, "assert_work_dir_outside_repo", lambda *a, **k: None)
    with pytest.raises(holdout.Aq7LockedHoldoutError):
        holdout.run_aq7_structure_role_drop_locked_holdout(
            work_dir=work,
            output_path=out,
            repo_root=fake_repo,
            freeze_token="WRONG_TOKEN",
            candidate_id=holdout.FROZEN_CANDIDATE_ID,
        )


def test_incomplete_test_partition_does_not_emit_false_pass() -> None:
    gates = {
        "aq7.boundary": {"outcome": "MEASURED"},
        "aq7.role": {"outcome": "MEASURED"},
        "aq7.drop_event": {"outcome": "MEASURED"},
    }
    # Missing fixtures → incomplete even if fabricated gates look green.
    assert (
        holdout.resolve_holdout_exit(
            gates=gates, freeze_ok=True, partition_complete=False
        )
        == holdout.EXIT_INCOMPLETE
    )


def test_deterministic_repeat_of_frozen_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = tmp_path / "corpus"
    fake_repo = tmp_path / "fake-repo"
    fake_repo.mkdir()
    monkeypatch.setattr(corpus, "assert_work_dir_outside_repo", lambda *a, **k: None)
    corpus.generate_aq7_structure_role_drop_corpus(work, repo_root=fake_repo)
    fixture_id = "aq7-synth-simple-clean-cal-001"
    gt = json.loads((work / "gt" / f"{fixture_id}.json").read_text(encoding="utf-8"))
    audio = work / "audio" / f"{fixture_id}.wav"
    candidate = holdout.frozen_candidate()

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


def test_holdout_payload_rejects_composite_score_fields() -> None:
    sample = {
        "document_type": holdout.DOCUMENT_TYPE,
        "gates": {
            "aq7.boundary": {"outcome": "HOLD"},
            "aq7.role": {"outcome": "HOLD"},
            "aq7.drop_event": {"outcome": "HOLD"},
        },
        "splits": {"TEST": {"aq7.boundary": {}, "aq7.role": {}, "aq7.drop_event": {}}},
    }
    holdout.assert_no_composite_quality_score(sample)
    bad = deepcopy(sample)
    bad["aq7_composite"] = 0.5
    with pytest.raises(holdout.Aq7LockedHoldoutError, match="composite"):
        holdout.assert_no_composite_quality_score(bad)
