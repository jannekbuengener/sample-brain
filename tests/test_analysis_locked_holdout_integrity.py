"""Additional #1170 failure-atomicity and replay-integrity regressions."""

import json

import pytest

from src.analysis_automation_decision import decision_semantic_fingerprint
from src.analysis_eval_artifact import fingerprint
from src.analysis_quality_loop_state import load_state, save_state_atomic
from tests.test_analysis_locked_holdout import frozen, transition  # noqa: F401


@pytest.mark.parametrize("field", ["policy", "evidence"])
def test_resealed_result_cannot_change_committed_claim(frozen, field):
    transition(**frozen)
    path = frozen["state_path"].with_name("state.json.locked-result.json")
    result = json.loads(path.read_text())
    if field == "policy":
        result["decision"]["decision_token"] = "NO_JUSTIFIED_CANDIDATE"
    else:
        result["decision"]["evidence"]["evidence_fingerprint"] = "d" * 64
    result["decision"]["decision_fingerprint"] = decision_semantic_fingerprint(result["decision"])
    result["result_fingerprint"] = fingerprint({k: v for k, v in result.items() if k != "result_fingerprint"})
    path.write_text(json.dumps(result))
    with pytest.raises(ValueError, match="policy|evidence|invocation"):
        transition(**frozen)


def test_freeze_change_during_execution_does_not_commit(frozen, monkeypatch):
    from src.analysis_locked_holdout import run_orchestration

    def mutate(**kwargs):
        result = run_orchestration(**kwargs)
        state = load_state(frozen["state_path"])
        state["generation"] += 1
        state.pop("state_fingerprint")
        save_state_atomic(frozen["state_path"], state)
        return result

    monkeypatch.setattr("src.analysis_locked_holdout.run_orchestration", mutate)
    with pytest.raises(ValueError, match="freeze"):
        transition(**frozen)
    assert not frozen["state_path"].with_name("state.json.locked-result.json").exists()


def test_corrupt_supervisor_is_not_reset(frozen):
    frozen["state_path"].write_text("{broken")
    with pytest.raises(ValueError, match="corrupt"):
        transition(**frozen)
    assert frozen["state_path"].read_text() == "{broken"


@pytest.mark.parametrize("field", ["benchmark_id", "dataset_id", "dataset_content_fingerprint"])
def test_resealed_result_cannot_change_request_benchmark(frozen, field):
    transition(**frozen)
    path = frozen["state_path"].with_name("state.json.locked-result.json")
    result = json.loads(path.read_text())
    result["decision"]["benchmark"][field] = "d" * 64
    result["decision"]["decision_fingerprint"] = decision_semantic_fingerprint(result["decision"])
    result["result_fingerprint"] = fingerprint({k: v for k, v in result.items() if k != "result_fingerprint"})
    path.write_text(json.dumps(result))
    with pytest.raises(ValueError, match="benchmark|invocation"):
        transition(**frozen)
