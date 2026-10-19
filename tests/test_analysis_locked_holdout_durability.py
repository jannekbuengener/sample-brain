"""#1174 review regressions: metadata barriers and exact decision versions."""

import pytest

from src.analysis_automation_decision import (
    aq1_scalar_decision_fixture,
    decision_semantic_fingerprint,
    validate_decision,
)
from src.analysis_locked_holdout import run_locked_holdout_transition as transition
from src.analysis_quality_loop_state import load_state, save_state_atomic
from tests.test_analysis_locked_holdout import (
    _fresh_frozen_state,
    _locked_request,
    _patch_aq1_repo,
    _state_path,
)


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    _patch_aq1_repo(monkeypatch, tmp_path)
    state_path = _state_path(tmp_path)
    state_path.parent.mkdir(parents=True)
    save_state_atomic(state_path, _fresh_frozen_state())
    locked = tmp_path / "locked"
    locked.mkdir()
    request = _locked_request(
        locked, operation="locked_evaluation", partition_role="holdout", split="TEST"
    )
    return dict(
        state_path=state_path,
        request=request,
        bind_kwargs={"work_dir": locked},
        evidence_fingerprint="b" * 64,
        gate_verdict="PASS",
        decision_token="KEEP_CURRENT_BASELINE_PATH",
        next_action="keep_baseline_and_stop",
    )


def test_legacy_action_cannot_claim_handoff_version():
    decision = aq1_scalar_decision_fixture()
    decision["artifact_version"] = "1.1.0"
    decision["decision_fingerprint"] = decision_semantic_fingerprint(decision)
    with pytest.raises(ValueError, match="version"):
        validate_decision(decision)


@pytest.mark.parametrize("barrier", ["fsync", "replace"])
def test_state_commit_failure_preserves_frozen_state(frozen, monkeypatch, barrier):
    import src.analysis_quality_loop_state as store

    before = frozen["state_path"].read_bytes()

    def fail(*args, **kwargs):
        raise OSError("injected commit barrier failure")

    with monkeypatch.context() as patch:
        patch.setattr(store.os, barrier, fail)
        with pytest.raises(ValueError, match="injected commit barrier failure"):
            transition(**frozen)

    assert frozen["state_path"].read_bytes() == before
    assert "locked_evaluation" not in load_state(frozen["state_path"])
    assert not list(frozen["state_path"].parent.glob(".*.tmp"))
