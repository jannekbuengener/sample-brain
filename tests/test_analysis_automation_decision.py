"""Contract tests for sample-brain.analysis-automation-decision.v1 (#1043)."""

from __future__ import annotations

import ast
import copy
import json
from pathlib import Path

import pytest

from src.analysis_automation_decision import (
    ARTIFACT_VERSION,
    DOCUMENT_TYPE,
    NEXT_ACTIONS,
    READY_DECISION_TOKENS,
    AnalysisAutomationDecisionError,
    aq1_scalar_decision_fixture,
    aq5_ranking_decision_fixture,
    build_decision,
    decision_semantic_fingerprint,
    serialize_decision,
    validate_decision,
)
from src.analysis_eval_artifact import fingerprint

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"


def test_document_identity_frozen() -> None:
    """T16: frozen document identity."""
    dec = aq1_scalar_decision_fixture()
    assert dec["document_type"] == DOCUMENT_TYPE == (
        "sample-brain.analysis-automation-decision.v1"
    )
    assert dec["artifact_version"] == ARTIFACT_VERSION == "1.0.0"


def test_t01_keep_current_baseline_calibration() -> None:
    """T01: Fixture A keep-baseline ready path."""
    dec = aq1_scalar_decision_fixture()
    validated = validate_decision(dec)
    assert validated["decision_status"] == "ready"
    assert validated["decision_token"] == "KEEP_CURRENT_BASELINE_PATH"
    assert validated["next_action"] == "keep_baseline_and_stop"
    assert validated["production_authorized"] is False
    assert validated["partition"]["role"] == "calibration"


def test_t02_promotion_candidate_not_production() -> None:
    """T02: Fixture B promotion candidate never authorizes production."""
    dec = aq5_ranking_decision_fixture(
        decision_token="PROMOTION_CANDIDATE_IDENTIFIED",
        next_action="require_human_governance",
        partition_role="test",
        partition_id="aq5-test-smoke",
        gate_verdict="PASS",
    )
    validated = validate_decision(dec)
    assert validated["decision_status"] == "ready"
    assert validated["decision_token"] == "PROMOTION_CANDIDATE_IDENTIFIED"
    assert validated["production_authorized"] is False
    assert validated["next_action"] == "require_human_governance"


def test_t03_no_justified_candidate() -> None:
    """T03: Fixture B NO_JUSTIFIED_CANDIDATE."""
    dec = aq5_ranking_decision_fixture(
        decision_token="NO_JUSTIFIED_CANDIDATE",
        next_action="keep_baseline_and_stop",
        partition_role="test",
        partition_id="aq5-test-smoke",
        gate_verdict="FAIL",
    )
    validated = validate_decision(dec)
    assert validated["decision_token"] == "NO_JUSTIFIED_CANDIDATE"
    assert validated["next_action"] == "keep_baseline_and_stop"


def test_t04_defer_insufficient_evidence() -> None:
    """T04: Fixture A DEFER_INSUFFICIENT_EVIDENCE."""
    dec = aq1_scalar_decision_fixture(
        decision_token="DEFER_INSUFFICIENT_EVIDENCE",
        next_action="defer_for_evidence",
        gate_verdict="HOLD",
    )
    validated = validate_decision(dec)
    assert validated["decision_token"] == "DEFER_INSUFFICIENT_EVIDENCE"
    assert validated["next_action"] == "defer_for_evidence"


def test_t05_continue_calibration_on_calibration_partition() -> None:
    """T05: CALIBRATION may continue iteration."""
    dec = aq1_scalar_decision_fixture(
        decision_token="NO_JUSTIFIED_CANDIDATE",
        next_action="continue_calibration",
        gate_verdict="PASS",
    )
    validated = validate_decision(dec)
    assert validated["partition"]["role"] == "calibration"
    assert validated["next_action"] == "continue_calibration"


def test_t06_freeze_candidate_on_calibration() -> None:
    """T06: CALIBRATION may freeze candidate for locked eval."""
    dec = aq1_scalar_decision_fixture(
        decision_token="PROMOTION_CANDIDATE_IDENTIFIED",
        next_action="freeze_candidate",
        gate_verdict="PASS",
    )
    validated = validate_decision(dec)
    assert validated["next_action"] == "freeze_candidate"
    assert validated["production_authorized"] is False


def test_t07_hold_status_has_no_ready_token() -> None:
    """T07: HOLD status never carries a ready token."""
    dec = aq1_scalar_decision_fixture(
        decision_status="hold",
        decision_token=None,
        next_action="defer_for_evidence",
        gate_verdict="HOLD",
    )
    validated = validate_decision(dec)
    assert validated["decision_status"] == "hold"
    assert "decision_token" not in validated or validated.get("decision_token") is None
    assert validated["next_action"] == "defer_for_evidence"


def test_t08_test_partition_terminal_only() -> None:
    """T08: TEST/HOLDOUT terminal handoff (no continue_calibration)."""
    dec = aq5_ranking_decision_fixture(
        decision_token="KEEP_CURRENT_BASELINE_PATH",
        next_action="keep_baseline_and_stop",
        partition_role="holdout",
        partition_id="aq6-holdout-smoke",
        gate_verdict="PASS",
    )
    validated = validate_decision(dec)
    assert validated["partition"]["role"] == "holdout"
    assert validated["next_action"] == "keep_baseline_and_stop"
    assert validated["next_action"] not in {"continue_calibration", "freeze_candidate"}


def test_t09_test_continue_calibration_rejected() -> None:
    """T09: TEST/HOLDOUT → continue_calibration fail-closed."""
    with pytest.raises(
        AnalysisAutomationDecisionError, match="partition firewall|illegal next_action"
    ):
        aq5_ranking_decision_fixture(
            decision_token="NO_JUSTIFIED_CANDIDATE",
            next_action="continue_calibration",
            partition_role="test",
            partition_id="aq5-test-smoke",
            gate_verdict="PASS",
        )


def test_t10_controlled_failure_stop() -> None:
    """T10: controlled_failure stops with no ready token."""
    dec = aq1_scalar_decision_fixture(
        decision_status="controlled_failure",
        decision_token=None,
        next_action="stop_controlled_failure",
        gate_verdict="FAIL",
    )
    validated = validate_decision(dec)
    assert validated["decision_status"] == "controlled_failure"
    assert validated["next_action"] == "stop_controlled_failure"
    assert validated.get("decision_token") in (None, )


def test_t11_promotion_always_production_unauthorized() -> None:
    """T11: PROMOTION_CANDIDATE_IDENTIFIED ⇒ production_authorized=false."""
    with pytest.raises(
        AnalysisAutomationDecisionError, match="production_authorized"
    ):
        build_decision(
            domain="aq5.ranking",
            benchmark_id="synthetic.aq5.ranking.decision.smoke",
            dataset_id="synthetic.aq5.ranking.v1",
            dataset_content_fingerprint=fingerprint({"dataset_id": "synthetic.aq5.ranking.v1"}),
            partition_id="aq5-test-smoke",
            partition_role="test",
            baseline_candidate_id="sample-brain.search.ranking.baseline",
            baseline_config_fingerprint=fingerprint({"profile": "baseline"}),
            current_candidate_id="sample-brain.search.ranking.weight-adapter-a",
            current_config_fingerprint=fingerprint({"profile": "weight-a"}),
            analysis_eval_fingerprint=fingerprint({"fixture": "aq5"}),
            evidence_fingerprint=fingerprint({"evidence": "opaque-a"}),
            gate_verdict="PASS",
            decision_status="ready",
            decision_token="PROMOTION_CANDIDATE_IDENTIFIED",
            next_action="require_human_governance",
            production_authorized=True,
        )


def test_t12_fingerprint_key_order_stable() -> None:
    """T12: fingerprint independent of key order."""
    a = aq1_scalar_decision_fixture()
    b = json.loads(json.dumps(a, sort_keys=False))
    # Shuffle by rebuilding from unsorted loads then reordering keys.
    shuffled = {k: b[k] for k in reversed(list(b.keys()))}
    assert decision_semantic_fingerprint(a) == decision_semantic_fingerprint(shuffled)
    assert len(decision_semantic_fingerprint(a)) == 64


def test_t13_generated_at_excluded_from_fingerprint() -> None:
    """T13: generated_at change does not alter semantic fingerprint."""
    a = aq1_scalar_decision_fixture(generated_at="2026-01-01T00:00:00Z")
    b = copy.deepcopy(a)
    b["generated_at"] = "2026-12-31T23:59:59Z"
    assert decision_semantic_fingerprint(a) == decision_semantic_fingerprint(b)


def test_t14_privacy_rejection() -> None:
    """T14: absolute paths / sensitive keys rejected."""
    with pytest.raises(AnalysisAutomationDecisionError, match="absolute/private path"):
        build_decision(
            domain="aq1.tempo",
            benchmark_id="synthetic.aq1.tempo.decision.smoke",
            dataset_id="synthetic.aq1.tempo.v1",
            dataset_content_fingerprint=fingerprint({"dataset_id": "x"}),
            partition_id="aq1-cal-smoke",
            partition_role="calibration",
            baseline_candidate_id="sample-brain.analyze.bpm.baseline",
            baseline_config_fingerprint=fingerprint({"profile": "baseline"}),
            current_candidate_id="sample-brain.analyze.bpm.baseline",
            current_config_fingerprint=fingerprint({"profile": "baseline"}),
            analysis_eval_fingerprint=fingerprint({"fixture": "aq1"}),
            evidence_fingerprint=fingerprint({"evidence": "opaque"}),
            gate_verdict="PASS",
            decision_status="ready",
            decision_token="KEEP_CURRENT_BASELINE_PATH",
            next_action="keep_baseline_and_stop",
            extra_fields={"note": r"C:\Users\janne\private\kick.wav"},
        )
    with pytest.raises(AnalysisAutomationDecisionError, match="sensitive key"):
        build_decision(
            domain="aq1.tempo",
            benchmark_id="synthetic.aq1.tempo.decision.smoke",
            dataset_id="synthetic.aq1.tempo.v1",
            dataset_content_fingerprint=fingerprint({"dataset_id": "x"}),
            partition_id="aq1-cal-smoke",
            partition_role="calibration",
            baseline_candidate_id="sample-brain.analyze.bpm.baseline",
            baseline_config_fingerprint=fingerprint({"profile": "baseline"}),
            current_candidate_id="sample-brain.analyze.bpm.baseline",
            current_config_fingerprint=fingerprint({"profile": "baseline"}),
            analysis_eval_fingerprint=fingerprint({"fixture": "aq1"}),
            evidence_fingerprint=fingerprint({"evidence": "opaque"}),
            gate_verdict="PASS",
            decision_status="ready",
            decision_token="KEEP_CURRENT_BASELINE_PATH",
            next_action="keep_baseline_and_stop",
            extra_fields={"username": "janne"},
        )


def test_t15_missing_identity_rejected() -> None:
    """T15: missing required identity rejected."""
    dec = aq1_scalar_decision_fixture()
    del dec["domain"]
    with pytest.raises(AnalysisAutomationDecisionError, match="domain"):
        validate_decision(dec)


def test_t16_wrong_document_type_rejected() -> None:
    """T16: wrong document_type rejected."""
    dec = aq1_scalar_decision_fixture()
    dec["document_type"] = "sample-brain.analysis-eval.v1"
    with pytest.raises(AnalysisAutomationDecisionError, match="document_type"):
        validate_decision(dec)


def test_t17_hold_with_ready_token_rejected() -> None:
    """T17: status/token orthogonality."""
    with pytest.raises(
        AnalysisAutomationDecisionError, match="ready token|orthogonality|decision_token"
    ):
        aq1_scalar_decision_fixture(
            decision_status="hold",
            decision_token="KEEP_CURRENT_BASELINE_PATH",
            next_action="defer_for_evidence",
            gate_verdict="HOLD",
        )


def test_t18_gate_verdict_not_decision_token() -> None:
    """T18: PASS/FAIL/HOLD are not ready tokens."""
    for bad in ("PASS", "FAIL", "HOLD", "measured", "controlled_failure"):
        with pytest.raises(AnalysisAutomationDecisionError, match="decision_token|unsupported"):
            aq1_scalar_decision_fixture(
                decision_token=bad,  # type: ignore[arg-type]
                next_action="keep_baseline_and_stop",
            )


def test_t19_deprecated_aliases_rejected() -> None:
    """T19: deprecated aliases rejected as V1 ready tokens."""
    for bad in ("DEFER_PROMOTION", "NEED_MORE_EVIDENCE", "NEED_FURTHER_CANDIDATES"):
        with pytest.raises(AnalysisAutomationDecisionError, match="decision_token|unsupported|deprecated"):
            aq1_scalar_decision_fixture(
                decision_token=bad,  # type: ignore[arg-type]
                next_action="keep_baseline_and_stop",
            )


def test_t20_two_domain_structural_proof() -> None:
    """T20: Fixture A scalar vs Fixture B ranking under same schema."""
    a = validate_decision(aq1_scalar_decision_fixture())
    b = validate_decision(
        aq5_ranking_decision_fixture(
            decision_token="PROMOTION_CANDIDATE_IDENTIFIED",
            next_action="require_human_governance",
            partition_role="test",
            partition_id="aq5-test-smoke",
        )
    )
    assert a["domain"] == "aq1.tempo"
    assert b["domain"] == "aq5.ranking"
    planes = b.get("planes") or {}
    assert "ranking" in planes
    ranked = planes["ranking"].get("ranked_ids")
    assert isinstance(ranked, list) and ranked
    # No blended opaque promotion score field.
    assert "blended_score" not in b
    assert "promotion_score" not in b


def test_t21_no_arvp_import_in_public_module() -> None:
    """T21: public module must not import arvp."""
    path = SRC_ROOT / "analysis_automation_decision.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("arvp"), alias.name
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert not mod.startswith("arvp"), mod


def test_t22_canonical_round_trip() -> None:
    """T22: serialize → loads → serialize is byte-identical."""
    dec = aq1_scalar_decision_fixture()
    a = serialize_decision(dec)
    b = serialize_decision(json.loads(a))
    assert a == b


def test_t23_holdout_not_used_for_tuning_helpers() -> None:
    """T23: no helper path that maps holdout metrics into calibration knobs."""
    path = SRC_ROOT / "analysis_automation_decision.py"
    source = path.read_text(encoding="utf-8")
    assert "tune_from_holdout" not in source
    assert "threshold_from_test" not in source
    # Holdout may continue_calibration only via rejected validation.
    with pytest.raises(AnalysisAutomationDecisionError):
        aq5_ranking_decision_fixture(
            decision_token="KEEP_CURRENT_BASELINE_PATH",
            next_action="continue_calibration",
            partition_role="holdout",
            partition_id="aq6-holdout-smoke",
        )


def test_ready_token_vocabulary_frozen() -> None:
    assert READY_DECISION_TOKENS == frozenset(
        {
            "KEEP_CURRENT_BASELINE_PATH",
            "PROMOTION_CANDIDATE_IDENTIFIED",
            "DEFER_INSUFFICIENT_EVIDENCE",
            "NO_JUSTIFIED_CANDIDATE",
        }
    )
    assert NEXT_ACTIONS == frozenset(
        {
            "continue_calibration",
            "freeze_candidate",
            "keep_baseline_and_stop",
            "defer_for_evidence",
            "require_human_governance",
            "stop_controlled_failure",
        }
    )


def test_fingerprint_mismatch_rejected() -> None:
    dec = aq1_scalar_decision_fixture()
    dec["decision_fingerprint"] = "0" * 64
    with pytest.raises(AnalysisAutomationDecisionError, match="fingerprint"):
        validate_decision(dec)


def test_validation_partition_cannot_continue_calibration() -> None:
    with pytest.raises(AnalysisAutomationDecisionError, match="partition firewall|illegal"):
        aq1_scalar_decision_fixture(
            partition_role="validation",
            partition_id="aq1-validation-smoke",
            decision_token="NO_JUSTIFIED_CANDIDATE",
            next_action="continue_calibration",
        )


def test_candidate_change_changes_fingerprint() -> None:
    a = aq1_scalar_decision_fixture()
    b = aq1_scalar_decision_fixture(
        current_candidate_id="sample-brain.analyze.bpm.heuristic-fold",
        current_config_fingerprint=fingerprint({"profile": "heuristic-fold"}),
    )
    assert decision_semantic_fingerprint(a) != decision_semantic_fingerprint(b)
