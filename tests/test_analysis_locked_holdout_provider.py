"""Additive S6 provider contract; frozen before implementation."""

import copy
import json

import pytest

from src.analysis_automation_decision import validate_decision
from src.analysis_eval_artifact import assert_portable_value, fingerprint
from tests.test_analysis_locked_holdout import frozen, transition  # noqa: F401


POLICY = dict(
    evidence_fingerprint="d" * 64,
    gate_verdict="PASS",
    decision_token="PROMOTION_CANDIDATE_IDENTIFIED",
    next_action="handoff_promotion_controller",
)


def provider_call(frozen, callback=None, identity="policy.synthetic.v1"):
    args = {k: v for k, v in frozen.items() if k not in POLICY}
    return dict(
        args,
        decision_provider=callback or (lambda context: dict(POLICY)),
        decision_provider_id=identity,
    )


def read_document(frozen, suffix):
    return json.loads(
        frozen["state_path"]
        .with_name("state.json.locked-" + suffix + ".json")
        .read_text()
    )


def write_result(frozen, result):
    result["result_fingerprint"] = fingerprint(
        {k: v for k, v in result.items() if k != "result_fingerprint"}
    )
    frozen["state_path"].with_name("state.json.locked-result.json").write_text(
        json.dumps(result)
    )


@pytest.mark.parametrize("role", ["test", "holdout"])
@pytest.mark.parametrize(
    "gate,token,action,status",
    [
        (
            "PASS",
            "PROMOTION_CANDIDATE_IDENTIFIED",
            "handoff_promotion_controller",
            "ready",
        ),
        ("FAIL", "NO_JUSTIFIED_CANDIDATE", "keep_baseline_and_stop", "ready"),
        ("HOLD", None, None, "hold"),
    ],
)
def test_real_provider_chain_claim_order_evidence_and_replay(
    frozen, monkeypatch, role, gate, token, action, status
):
    from src.analysis_headless_run import validate_request
    from src.aq_headless_adapters.aq1_tempo_compare import Aq1TempoCompareAdapter

    frozen["request"]["partition"]["role"] = role
    frozen["request"].pop("request_fingerprint")
    frozen["request"] = validate_request(frozen["request"])
    events = []
    original = Aq1TempoCompareAdapter.run
    before = frozen["state_path"].read_bytes()

    def evaluate(self, request):
        claim = read_document(frozen, "claim")
        assert claim == dict(
            freeze_state_fingerprint=json.loads(before)["state_fingerprint"],
            request_fingerprint=request["request_fingerprint"],
            mode="provider",
            decision_provider_id="policy.synthetic.v1",
        )
        events.append("eval")
        return original(self, request)

    monkeypatch.setattr(Aq1TempoCompareAdapter, "run", evaluate)
    seen = []
    policy = dict(POLICY, gate_verdict=gate, decision_token=token, next_action=action)

    def decide(context):
        assert events == ["eval"]
        events.append("provider")
        assert_portable_value(context)
        assert "bind_kwargs" not in context
        assert context["analysis_eval_fingerprint"] == fingerprint(
            context["analysis_eval"]
        )
        assert context["evidence_fingerprint"] == fingerprint(
            {k: v for k, v in context.items() if k != "evidence_fingerprint"}
        )
        assert context["evidence_fingerprint"] != policy["evidence_fingerprint"]
        seen.append(copy.deepcopy(context))
        context["current_candidate"]["candidate_id"] = "mutated-copy"
        return policy

    args = provider_call(frozen, decide)
    result = transition(**args)["result"]
    assert events == ["eval", "provider"]
    assert result["artifact_version"] == "1.1.0"
    assert result["analysis_eval_fingerprint"] == seen[0]["analysis_eval_fingerprint"]
    assert result["current_candidate"] == seen[0]["current_candidate"]
    assert result["baseline_candidate"] == seen[0]["baseline_candidate"]
    assert result["partition"] == seen[0]["partition"]
    assert result["production_authorized"] is False
    decision = validate_decision(result["decision"])
    assert decision["decision_status"] == status
    assert decision["production_authorized"] is False
    assert (
        decision["evidence"]["evidence_fingerprint"] == policy["evidence_fingerprint"]
    )
    assert result["decision_provider_provenance"] == dict(
        decision_provider_id=args["decision_provider_id"],
        eval_context_fingerprint=seen[0]["evidence_fingerprint"],
        policy_inputs=policy,
    )
    assert frozen["state_path"].read_bytes() == before
    monkeypatch.setattr(
        Aq1TempoCompareAdapter, "run", lambda *a: pytest.fail("second evaluation")
    )
    args["decision_provider"] = lambda context: pytest.fail("second provider call")
    assert transition(**args) == dict(already_committed=True, result=result)


@pytest.mark.parametrize(
    "change",
    ["missing_id", "missing_provider", "empty_id", "path_id", "not_callable", *POLICY],
)
def test_invalid_provider_mode_before_dispatch(frozen, monkeypatch, change):
    args = provider_call(frozen)
    if change == "missing_id":
        args.pop("decision_provider_id")
    elif change == "missing_provider":
        args.pop("decision_provider")
    elif change == "empty_id":
        args["decision_provider_id"] = " "
    elif change == "path_id":
        args["decision_provider_id"] = "C:/private/policy.py"
    elif change == "not_callable":
        args["decision_provider"] = "callable-repr"
    else:
        args[change] = None
    monkeypatch.setattr(
        "src.analysis_orchestration_run.bind_adapter",
        lambda *a, **k: pytest.fail("dispatched"),
    )
    with pytest.raises(ValueError):
        transition(**args)
    assert not frozen["state_path"].with_name("state.json.locked-claim.json").exists()


@pytest.mark.parametrize(
    "change",
    [
        "continue_calibration",
        "freeze_candidate",
        "missing_policy",
        "bad_evidence",
        "extra_field",
        "exception",
    ],
)
def test_provider_failure_leaves_uncertain_claim(frozen, monkeypatch, change):
    calls = []

    def decide(context):
        calls.append(1)
        if change == "exception":
            raise RuntimeError("provider interrupted")
        policy = dict(POLICY)
        if change in {"continue_calibration", "freeze_candidate"}:
            policy["next_action"] = change
        elif change == "missing_policy":
            policy["decision_token"] = None
        elif change == "bad_evidence":
            policy["evidence_fingerprint"] = "invalid"
        else:
            policy["production_authorized"] = True
        return policy

    args = provider_call(frozen, decide)
    with pytest.raises((ValueError, RuntimeError)):
        transition(**args)
    assert calls == [1]
    assert not frozen["state_path"].with_name("state.json.locked-result.json").exists()
    monkeypatch.setattr(
        "src.analysis_locked_holdout.run_orchestration",
        lambda **kw: pytest.fail("redispatched"),
    )
    with pytest.raises(ValueError, match="claim|uncertain"):
        transition(**args)
    assert calls == [1]


def test_changed_provider_authority_and_mode_refused(frozen):
    args = provider_call(frozen)
    transition(**args)
    with pytest.raises(ValueError, match="invocation|provider|claim"):
        transition(**dict(args, decision_provider_id="policy.other.v1"))
    with pytest.raises(ValueError, match="invocation|provider|claim"):
        transition(**frozen)


def test_provider_claim_only_restart_no_dispatch(frozen, monkeypatch):
    args = provider_call(frozen)

    def interrupted(**kw):
        raise RuntimeError("before evaluation")

    monkeypatch.setattr("src.analysis_locked_holdout.run_orchestration", interrupted)
    with pytest.raises(RuntimeError):
        transition(**args)
    monkeypatch.setattr(
        "src.analysis_locked_holdout.run_orchestration",
        lambda **kw: pytest.fail("redispatched"),
    )
    with pytest.raises(ValueError, match="claim|uncertain"):
        transition(**args)


def test_provider_lost_response_after_commit_replays(frozen, monkeypatch):
    import src.analysis_locked_holdout as locked

    args = provider_call(frozen)
    original = locked._write_atomic

    def lost(path, result):
        original(path, result)
        raise OSError("lost response")

    monkeypatch.setattr(locked, "_write_atomic", lost)
    with pytest.raises(OSError, match="lost response"):
        transition(**args)
    monkeypatch.setattr(
        locked, "run_orchestration", lambda **kw: pytest.fail("redispatched")
    )
    assert transition(**args) == dict(
        already_committed=True, result=read_document(frozen, "result")
    )


def test_legacy_result_shape_and_reader_unchanged(frozen):
    from src.analysis_locked_holdout import validate_locked_result
    from src.analysis_promotion import load_promotion_source

    frozen.update(
        decision_token=POLICY["decision_token"], next_action=POLICY["next_action"]
    )
    result = transition(**frozen)["result"]
    assert result["artifact_version"] == "1.0.0"
    assert "decision_provider_provenance" not in result
    assert "mode" not in read_document(frozen, "claim")
    assert validate_locked_result(copy.deepcopy(result)) == result
    assert load_promotion_source(frozen["state_path"]) == result


def test_s7_reads_provider_without_execution(frozen, monkeypatch):
    from src.analysis_promotion import load_promotion_source

    result = transition(**provider_call(frozen))["result"]
    monkeypatch.setattr(
        "src.analysis_locked_holdout.run_orchestration",
        lambda **kw: pytest.fail("reader dispatched"),
    )
    assert load_promotion_source(frozen["state_path"]) == result


@pytest.mark.parametrize(
    "field", ["decision_provider_id", "policy_inputs", "eval_context_fingerprint"]
)
def test_s7_rejects_bad_provider_provenance(frozen, field):
    from src.analysis_promotion import load_promotion_source

    args = provider_call(frozen)
    result = transition(**args)["result"]
    provenance = result["decision_provider_provenance"]
    if field == "decision_provider_id":
        provenance[field] = "policy.other.v1"
    elif field == "policy_inputs":
        provenance[field]["evidence_fingerprint"] = "e" * 64
    else:
        provenance[field] = "invalid"
    write_result(frozen, result)
    with pytest.raises(ValueError):
        load_promotion_source(frozen["state_path"])
    with pytest.raises(ValueError):
        transition(**args)


def test_provider_controlled_failure_is_terminal(frozen, monkeypatch):
    from src.analysis_headless_run import build_result
    from src.aq_headless_adapters.aq1_tempo_compare import Aq1TempoCompareAdapter

    def failed(self, request):
        return build_result(
            run_status="controlled_failure",
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            request_fingerprint=request["request_fingerprint"],
            domain=request["domain"],
            operation=request["operation"],
            partition_id=request["partition"]["partition_id"],
            partition_role=request["partition"]["role"],
            **request["benchmark"],
            error_code="CONTROLLED",
            error_detail="sanitized failure",
        )

    monkeypatch.setattr(Aq1TempoCompareAdapter, "run", failed)
    calls = []

    def decide(context):
        calls.append(context)
        assert context["headless_result"]["run_status"] == "controlled_failure"
        return dict(
            evidence_fingerprint="d" * 64,
            gate_verdict=None,
            decision_token=None,
            next_action=None,
        )

    args = provider_call(frozen, decide)
    result = transition(**args)["result"]
    assert len(calls) == 1
    assert result["terminal_status"] == "controlled_failure"
    assert result["decision"]["next_action"] == "stop_controlled_failure"
    assert result["production_authorized"] is False
    assert transition(**args)["already_committed"] is True
    assert len(calls) == 1
