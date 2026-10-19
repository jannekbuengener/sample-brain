"""Replay-integrity and failure-atomicity regressions for locked evaluation."""

import pytest

from src.analysis_headless_run import request_semantic_fingerprint
from src.analysis_locked_holdout import run_locked_holdout_transition as transition
from src.analysis_quality_loop_state import load_state, save_state_atomic
from tests.test_analysis_locked_holdout_durability import frozen  # noqa: F401


@pytest.mark.parametrize(
    "field,value",
    [
        ("request_fingerprint", "d" * 64),
        ("evidence_fingerprint", "d" * 64),
        ("gate_verdict", "HOLD"),
        ("decision_token", "NO_JUSTIFIED_CANDIDATE"),
        ("next_action", "defer_for_evidence"),
    ],
)
def test_resealed_result_cannot_change_committed_claim(frozen, monkeypatch, field, value):
    transition(**frozen)
    state = load_state(frozen["state_path"])
    locked = state["locked_evaluation"]
    target = locked["decision"] if field in {"decision_token", "next_action"} else locked
    target[field] = value
    state.pop("state_fingerprint")
    save_state_atomic(frozen["state_path"], state)
    before = frozen["state_path"].read_bytes()

    def no_dispatch(**kwargs):
        pytest.fail("replay must not rerun orchestration")

    monkeypatch.setattr("src.analysis_locked_holdout.run_orchestration", no_dispatch)
    with pytest.raises(ValueError, match="already committed.*different"):
        transition(**frozen)
    assert frozen["state_path"].read_bytes() == before


def test_freeze_change_during_execution_does_not_commit(frozen, monkeypatch):
    from src.analysis_locked_holdout import run_orchestration

    changed_bytes = None

    def mutate(**kwargs):
        nonlocal changed_bytes
        result = run_orchestration(**kwargs)
        state = load_state(frozen["state_path"])
        state["generation"] += 1
        state.pop("state_fingerprint")
        save_state_atomic(frozen["state_path"], state)
        changed_bytes = frozen["state_path"].read_bytes()
        return result

    monkeypatch.setattr("src.analysis_locked_holdout.run_orchestration", mutate)
    with pytest.raises(ValueError, match="freeze"):
        transition(**frozen)
    assert frozen["state_path"].read_bytes() == changed_bytes
    assert "locked_evaluation" not in load_state(frozen["state_path"])


def test_corrupt_supervisor_is_not_reset(frozen):
    frozen["state_path"].write_text("{broken")
    with pytest.raises(ValueError, match="corrupt"):
        transition(**frozen)
    assert frozen["state_path"].read_text() == "{broken"


@pytest.mark.parametrize("field", ["benchmark_id", "dataset_id", "dataset_content_fingerprint"])
def test_resealed_request_cannot_change_committed_benchmark(frozen, monkeypatch, field):
    transition(**frozen)
    before = frozen["state_path"].read_bytes()
    request = frozen["request"]
    request["benchmark"][field] = "d" * 64
    request["request_fingerprint"] = request_semantic_fingerprint(request)

    def no_dispatch(**kwargs):
        pytest.fail("changed request must not rerun orchestration")

    monkeypatch.setattr("src.analysis_locked_holdout.run_orchestration", no_dispatch)
    with pytest.raises(ValueError, match="different request"):
        transition(**frozen)
    assert frozen["state_path"].read_bytes() == before
