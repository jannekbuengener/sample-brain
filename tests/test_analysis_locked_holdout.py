"""#1170 frozen behavioral acceptance tests; real AQ1 Path B composition."""

import copy
import json

import pytest

from src.analysis_automation_decision import (
    AnalysisAutomationDecisionError,
    aq1_scalar_decision_fixture,
    validate_decision,
)
from src.analysis_eval_artifact import fingerprint
from src.analysis_headless_run import validate_request
from src.analysis_quality_loop_state import load_state, save_state_atomic
from src.analysis_quality_loop_supervisor import run_supervisor_step
from src.aq_candidate_search_spaces.aq1_tempo import Aq1TempoSearchSpaceProvider
from tests.test_analysis_quality_loop_supervisor import (
    _aq1_path_b_request,
    _fresh_aq1_state,
    _patch_aq1_repo,
)


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    _patch_aq1_repo(monkeypatch, tmp_path)
    cal = tmp_path / "cal"
    cal.mkdir()
    state_path = tmp_path / "state.json"
    save_state_atomic(state_path, _fresh_aq1_state())
    run_supervisor_step(
        state_path=state_path,
        request=_aq1_path_b_request(cal),
        bind_kwargs={"work_dir": cal},
        evidence_fingerprint="a" * 64,
        gate_verdict="PASS",
        decision_token="KEEP_CURRENT_BASELINE_PATH",
        next_action="freeze_candidate",
    )
    locked = tmp_path / "locked"
    locked.mkdir()
    request = _aq1_path_b_request(
        locked, operation="locked_evaluation", partition_role="holdout", split="TEST"
    )
    return dict(
        state_path=state_path, request=request, bind_kwargs={"work_dir": locked},
        evidence_fingerprint="b" * 64, gate_verdict="PASS",
        decision_token="KEEP_CURRENT_BASELINE_PATH", next_action="keep_baseline_and_stop",
    )


def transition(**kwargs):
    # Lazy import makes missing implementation an observed behavioral RED.
    from src.analysis_locked_holdout import run_locked_holdout_transition

    return run_locked_holdout_transition(**kwargs)


def reseal_request(request):
    request.pop("request_fingerprint", None)
    return validate_request(request)


@pytest.mark.parametrize("role", ["test", "holdout"])
def test_real_locked_chain_persists_and_replays(frozen, monkeypatch, role):
    request = frozen["request"]
    request["partition"]["role"] = role
    frozen["request"] = reseal_request(request)
    before = frozen["state_path"].read_bytes()
    first = transition(**frozen)
    result = first["result"]
    assert first["already_committed"] is False
    assert result["terminal_status"] == "ready"
    assert result["production_authorized"] is False
    assert result["request_fingerprint"] == frozen["request"]["request_fingerprint"]
    assert result["partition"] == frozen["request"]["partition"]
    assert result["current_candidate"] == load_state(frozen["state_path"])["active_candidate"]
    decision = validate_decision(result["decision"])
    assert decision["current_candidate"] == result["current_candidate"]
    assert decision["baseline_candidate"] == result["baseline_candidate"]
    assert decision["evidence"]["analysis_eval_fingerprint"] == result["analysis_eval_fingerprint"]
    assert decision["evidence"]["evidence_fingerprint"] == "b" * 64
    assert len(result["outcome_fingerprint"]) == 64
    assert frozen["state_path"].read_bytes() == before
    persisted = frozen["state_path"].with_name("state.json.locked-result.json")
    assert json.loads(persisted.read_text()) == result
    monkeypatch.setattr("src.analysis_orchestration_run.bind_adapter", lambda *a, **k: pytest.fail("reran"))
    assert transition(**frozen) == {"already_committed": True, "result": result}
    assert frozen["state_path"].read_bytes() == before


@pytest.mark.parametrize("status", ["ready", "held", "stopped", "exhausted", "controlled_failure", "retry_exhausted"])
def test_nonfrozen_rejected_before_execution(frozen, monkeypatch, status):
    state = load_state(frozen["state_path"])
    state["loop_status"] = status
    state.pop("state_fingerprint")
    save_state_atomic(frozen["state_path"], state)
    monkeypatch.setattr("src.analysis_orchestration_run.bind_adapter", lambda *a, **k: pytest.fail("executed"))
    with pytest.raises(ValueError, match="frozen"):
        transition(**frozen)


@pytest.mark.parametrize("identity,field", [("current", "candidate_id"), ("current", "config_fingerprint"), ("baseline", "candidate_id"), ("baseline", "config_fingerprint")])
def test_identity_mismatch_before_runner(frozen, monkeypatch, identity, field):
    frozen["request"][identity][field] = "other" if field == "candidate_id" else "c" * 64
    frozen["request"] = reseal_request(frozen["request"])
    monkeypatch.setattr("src.analysis_orchestration_run.bind_adapter", lambda *a, **k: pytest.fail("executed"))
    with pytest.raises(ValueError, match="identity"):
        transition(**frozen)


@pytest.mark.parametrize("role", ["test", "holdout"])
@pytest.mark.parametrize("action", ["continue_calibration", "freeze_candidate"])
def test_tuning_firewall_before_runner(frozen, monkeypatch, role, action):
    frozen["request"]["partition"]["role"] = role
    frozen["request"] = reseal_request(frozen["request"])
    frozen["next_action"] = action
    monkeypatch.setattr("src.analysis_orchestration_run.bind_adapter", lambda *a, **k: pytest.fail("executed"))
    with pytest.raises(ValueError, match="tuning|terminal|firewall"):
        transition(**frozen)


@pytest.mark.parametrize("field", ["search_space_id", "search_space_version", "search_space_fingerprint", "last_decision"])
def test_freeze_provenance_checked(frozen, field):
    state = load_state(frozen["state_path"])
    state[field] = ({**state[field], "next_action": "continue_calibration"} if field == "last_decision" else "c" * 64)
    state.pop("state_fingerprint")
    save_state_atomic(frozen["state_path"], state)
    with pytest.raises(ValueError, match="search.space|freeze"):
        transition(**frozen)


def test_provider_contents_and_order_are_authoritative(frozen):
    provider = Aq1TempoSearchSpaceProvider()
    provider.ordered_members = lambda: list(reversed(Aq1TempoSearchSpaceProvider().ordered_members()))
    with pytest.raises(ValueError, match="search.space"):
        transition(**frozen, provider=provider)


@pytest.mark.parametrize("gate,token,action,status", [
    ("HOLD", None, None, "hold"),
    ("FAIL", "NO_JUSTIFIED_CANDIDATE", "keep_baseline_and_stop", "ready"),
    ("PASS", "PROMOTION_CANDIDATE_IDENTIFIED", "handoff_promotion_controller", "ready"),
])
def test_explicit_policy_and_terminal_families(frozen, gate, token, action, status):
    frozen.update(gate_verdict=gate, decision_token=token, next_action=action)
    decision = transition(**frozen)["result"]["decision"]
    assert decision["decision_status"] == status
    assert decision.get("decision_token") == token
    assert decision["production_authorized"] is False


@pytest.mark.parametrize("missing", ["decision_token", "next_action"])
def test_gate_is_not_policy(frozen, monkeypatch, missing):
    frozen[missing] = None
    monkeypatch.setattr("src.analysis_orchestration_run.bind_adapter", lambda *a, **k: pytest.fail("executed"))
    with pytest.raises(ValueError, match="policy"):
        transition(**frozen)


@pytest.mark.parametrize("evidence", [None, "", "not-a-hash", "C:/private/evidence.json", float("nan")])
def test_bad_evidence_fail_closed(frozen, monkeypatch, evidence):
    frozen["evidence_fingerprint"] = evidence
    monkeypatch.setattr("src.analysis_orchestration_run.bind_adapter", lambda *a, **k: pytest.fail("executed"))
    with pytest.raises(ValueError):
        transition(**frozen)


@pytest.mark.parametrize("extra", [{"value": float("inf")}, {"path": "C:/Users/private/samples.wav"}, {"path": "/home/private/db.sqlite"}])
def test_nonportable_request(frozen, extra):
    frozen["request"].update(extra)
    frozen["request"].pop("request_fingerprint")
    with pytest.raises(ValueError):
        transition(**frozen)


@pytest.mark.parametrize("changed", ["request", "evidence_fingerprint", "gate_verdict", "decision_token", "next_action", "state"])
def test_committed_input_change_rejected(frozen, changed):
    transition(**frozen)
    if changed == "state":
        state = load_state(frozen["state_path"])
        state["history_refs"].append("c" * 64)
        state.pop("state_fingerprint")
        save_state_atomic(frozen["state_path"], state)
    elif changed == "request":
        frozen["request"]["partition"]["partition_id"] = "different-locked-partition"
        frozen["request"] = reseal_request(frozen["request"])
    else:
        frozen[changed] = {"evidence_fingerprint": "c" * 64, "gate_verdict": "FAIL", "decision_token": "NO_JUSTIFIED_CANDIDATE", "next_action": "require_human_governance"}[changed]
    with pytest.raises(ValueError, match="committed|invocation|freeze"):
        transition(**frozen)


def test_uncertain_execution_never_retried(frozen, monkeypatch):
    def interrupted(**kwargs):
        raise RuntimeError("interrupted")
    monkeypatch.setattr("src.analysis_locked_holdout.run_orchestration", interrupted)
    with pytest.raises(RuntimeError, match="interrupted"):
        transition(**frozen)
    with pytest.raises(ValueError, match="claim|uncertain"):
        transition(**frozen)


def test_reentrant_execution_claim(frozen, monkeypatch):
    from src.analysis_locked_holdout import run_orchestration
    calls = []
    def reentrant(**kwargs):
        calls.append(1)
        with pytest.raises(ValueError, match="claim|uncertain"):
            transition(**frozen)
        return run_orchestration(**kwargs)
    monkeypatch.setattr("src.analysis_locked_holdout.run_orchestration", reentrant)
    transition(**frozen)
    assert calls == [1]


def test_result_write_failure_is_visible_and_not_retried(frozen, monkeypatch):
    import src.analysis_locked_holdout as locked
    original = locked.os.replace
    monkeypatch.setattr(locked.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("write failed")))
    with pytest.raises(OSError, match="write failed"):
        transition(**frozen)
    monkeypatch.setattr(locked.os, "replace", original)
    with pytest.raises(ValueError, match="claim|uncertain"):
        transition(**frozen)


def test_corrupt_result_fails_closed(frozen):
    transition(**frozen)
    path = frozen["state_path"].with_name("state.json.locked-result.json")
    path.write_text('{"bad":true}')
    with pytest.raises(ValueError):
        transition(**frozen)


def test_controlled_runner_failure_persisted(frozen, monkeypatch):
    from src.analysis_headless_run import build_result
    from src.aq_headless_adapters.aq1_tempo_compare import Aq1TempoCompareAdapter
    def failed(self, request):
        return build_result(
            run_status="controlled_failure", adapter_id=self.adapter_id,
            adapter_version=self.adapter_version, request_fingerprint=request["request_fingerprint"],
            domain=request["domain"], operation=request["operation"],
            partition_id=request["partition"]["partition_id"], partition_role=request["partition"]["role"],
            **request["benchmark"], error_code="CONTROLLED", error_detail="sanitized failure",
        )
    monkeypatch.setattr(Aq1TempoCompareAdapter, "run", failed)
    frozen.update(decision_token=None, next_action=None, gate_verdict=None)
    # S6 may accept no policy for a non-completed run; completed would fail closed.
    result = transition(**frozen)["result"]
    assert result["terminal_status"] == "controlled_failure"
    assert result["decision"]["next_action"] == "stop_controlled_failure"
    assert "decision_token" not in result["decision"]


def test_handoff_contract_version_and_legacy_compatibility():
    old = aq1_scalar_decision_fixture()
    assert old["artifact_version"] == "1.0.0"
    assert validate_decision(old) == old
    new = aq1_scalar_decision_fixture(partition_role="holdout", decision_token="PROMOTION_CANDIDATE_IDENTIFIED", next_action="handoff_promotion_controller")
    assert new["artifact_version"] == "1.1.0"
    assert validate_decision(new) == new
    invalid = copy.deepcopy(new)
    invalid["artifact_version"] = "1.0.0"
    invalid["decision_fingerprint"] = fingerprint({k: v for k, v in invalid.items() if k not in {"decision_fingerprint", "generated_at", "artifact_hash"}})
    with pytest.raises(AnalysisAutomationDecisionError, match="version|1.1.0"):
        validate_decision(invalid)


@pytest.mark.parametrize("role,token,gate", [("calibration", "PROMOTION_CANDIDATE_IDENTIFIED", "PASS"), ("holdout", "KEEP_CURRENT_BASELINE_PATH", "PASS"), ("test", "PROMOTION_CANDIDATE_IDENTIFIED", "FAIL")])
def test_invalid_handoff_semantics(role, token, gate):
    with pytest.raises(AnalysisAutomationDecisionError, match="handoff"):
        aq1_scalar_decision_fixture(partition_role=role, decision_token=token, next_action="handoff_promotion_controller", gate_verdict=gate)
