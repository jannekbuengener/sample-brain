"""Focused S9 replay-ownership regressions from final review."""

from __future__ import annotations

import pytest

import src.analysis_quality_closed_cycle as closed_cycle
from src.analysis_quality_closed_cycle import (
    AnalysisQualityClosedCycleError,
    _require_completed_s5_ownership,
    _require_locked_result_ownership,
    _require_result_attempt_ownership,
)


def _attempt() -> dict:
    return {
        "cycle_id": "cycle-a",
        "domain": "aq1.tempo",
        "initial_baseline_candidate": {
            "candidate_id": "baseline",
            "config_fingerprint": "a" * 64,
        },
        "initial_baseline_generation": 3,
        "calibration_refs": [
            {
                "committed_state_fingerprint": "b" * 64,
                "decision_fingerprint": "c" * 64,
            }
        ],
        "candidate_history": ["baseline", "candidate"],
        "locked_ref": {"result_fingerprint": "d" * 64},
        "promotion_ref": {"attempt_fingerprint": "e" * 64},
        "post_merge_ref": {"attempt_fingerprint": "f" * 64},
        "continuation_ref": {"state_fingerprint": "1" * 64},
    }


def _result_from(attempt: dict) -> dict:
    return {
        "cycle_id": attempt["cycle_id"],
        "domain": attempt["domain"],
        "initial_baseline_candidate": attempt["initial_baseline_candidate"],
        "initial_baseline_generation": attempt["initial_baseline_generation"],
        "calibration_refs": attempt["calibration_refs"],
        "candidate_history": attempt["candidate_history"],
        "locked_ref": attempt["locked_ref"],
        "promotion_ref": attempt["promotion_ref"],
        "post_merge_ref": attempt["post_merge_ref"],
        "continuation_ref": attempt["continuation_ref"],
    }


def test_completed_replay_rejects_different_current_s5_lineage() -> None:
    attempt = _attempt()
    current_s5 = {"state_fingerprint": "9" * 64}

    with pytest.raises(AnalysisQualityClosedCycleError, match="S5 lineage"):
        _require_completed_s5_ownership(attempt, current_s5)


def test_same_cycle_id_does_not_authorize_result_from_other_attempt() -> None:
    attempt = _attempt()
    result = _result_from(attempt)
    result["locked_ref"] = {"result_fingerprint": "8" * 64}

    with pytest.raises(AnalysisQualityClosedCycleError, match="persisted cycle attempt"):
        _require_result_attempt_ownership(attempt, result)


def test_promotion_rejects_replaced_locked_result() -> None:
    attempt = _attempt()
    replacement = {"result_fingerprint": "7" * 64}

    with pytest.raises(AnalysisQualityClosedCycleError, match="committed S6"):
        _require_locked_result_ownership(attempt, replacement)


def test_supervisor_return_rejects_state_changed_before_reload() -> None:
    identity = {
        "request_fingerprint": "2" * 64,
        "decision_provider_id": "policy.v1",
    }
    returned_state = {
        "state_fingerprint": "3" * 64,
        "last_orchestration_ref": {
            "request_fingerprint": identity["request_fingerprint"],
            "decision_provider_id": identity["decision_provider_id"],
        },
    }
    persisted_state = {
        **returned_state,
        "state_fingerprint": "4" * 64,
    }

    with pytest.raises(AnalysisQualityClosedCycleError, match="changed after supervisor"):
        closed_cycle._require_supervisor_result_state_ownership(
            {"state": returned_state}, persisted_state, identity, "S5"
        )


def test_supervisor_return_requires_pending_request_and_provider_identity() -> None:
    identity = {
        "request_fingerprint": "2" * 64,
        "decision_provider_id": "policy.v1",
    }
    state = {
        "state_fingerprint": "3" * 64,
        "last_orchestration_ref": {
            "request_fingerprint": "9" * 64,
            "decision_provider_id": "other-policy.v1",
        },
    }

    with pytest.raises(AnalysisQualityClosedCycleError, match="pending invocation"):
        closed_cycle._require_supervisor_result_state_ownership(
            {"state": state}, state, identity, "continuation"
        )


def test_completed_result_persists_continuation_ownership_before_publish(
    monkeypatch, tmp_path
) -> None:
    cycle = _attempt()
    cycle.update(
        phase="continuation",
        status="running",
        pending={"phase": "continuation", "identity": {}, "invocation_fingerprint": "5" * 64},
        reason=None,
    )
    lineage = {
        "current": {"baseline_fingerprint": "6" * 64},
        "last_known_good": {"baseline_fingerprint": "7" * 64},
    }
    events = []

    def save_attempt(path, state):
        events.append(("save", dict(state)))
        return dict(state)

    def write_result(path, attempt, current_lineage):
        events.append(("write", dict(attempt)))
        return {"result_fingerprint": "8" * 64}

    def commit_phase(path, state, phase):
        events.append(("commit", phase, dict(state)))
        return dict(state)

    monkeypatch.setattr(closed_cycle, "_save_attempt", save_attempt)
    monkeypatch.setattr(closed_cycle, "_write_result", write_result)
    monkeypatch.setattr(closed_cycle, "_commit_phase", commit_phase)

    result = closed_cycle._publish_completed_result(
        tmp_path / "cycle.json", cycle, lineage
    )

    assert result["result_fingerprint"] == "8" * 64
    assert [event[0] for event in events] == ["save", "write", "commit"]
    assert events[0][1]["continuation_ref"] == cycle["continuation_ref"]
    assert events[0][1]["status"] == "running"
