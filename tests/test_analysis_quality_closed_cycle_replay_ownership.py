"""Public S9 replay/dispatch ownership regressions from final review."""

from __future__ import annotations

import pytest

import src.analysis_quality_closed_cycle as closed_cycle
from src.analysis_eval_artifact import fingerprint
from src.analysis_quality_closed_cycle import run_quality_cycle
from src.analysis_quality_loop_state import load_state, save_state_atomic
from src.analysis_quality_loop_supervisor import AnalysisQualityLoopSupervisorError
from tests.test_analysis_quality_loop_supervisor import (
    _aq1_path_b_request,
    _fresh_aq1_state,
    _patch_aq1_repo,
)


def test_cycle_rejects_state_changed_between_request_and_supervisor_dispatch(
    tmp_path, monkeypatch
) -> None:
    _patch_aq1_repo(monkeypatch, tmp_path)
    state_path = tmp_path / "host" / "quality-state.json"
    state_path.parent.mkdir()
    save_state_atomic(state_path, _fresh_aq1_state())
    attempt_path = tmp_path / "host" / "cycle-attempt.json"
    work = tmp_path / "dispatch-race-work"
    work.mkdir()
    provider_calls = {"count": 0}

    def calibration_inputs(*, state_path, state):
        request = _aq1_path_b_request(
            work, current_candidate_id=state["active_candidate"]["candidate_id"]
        )

        def decide(context):
            provider_calls["count"] += 1
            return {
                "evidence_fingerprint": fingerprint(
                    {
                        "request_fingerprint": request["request_fingerprint"],
                        "analysis_eval_fingerprint": fingerprint(context["analysis_eval"]),
                        "domain_artifact_fingerprint": context["headless_result"][
                            "domain_artifact"
                        ]["artifact_fingerprint"],
                    }
                ),
                "gate_verdict": "HOLD",
                "decision_token": None,
                "next_action": "defer_for_evidence",
            }

        return {
            "request": request,
            "bind_kwargs": {"work_dir": work},
            "decision_provider": decide,
            "decision_provider_id": "aq1-dispatch-race-policy-v1",
        }

    real_step = closed_cycle.run_supervisor_step
    raced = {"done": False}

    def race_step(**kwargs):
        if not raced["done"]:
            raced["done"] = True
            current = load_state(kwargs["state_path"])
            changed = dict(current)
            changed.pop("state_fingerprint")
            changed["generation"] = int(current["generation"]) + 1
            save_state_atomic(kwargs["state_path"], changed)
        return real_step(**kwargs)

    monkeypatch.setattr(closed_cycle, "run_supervisor_step", race_step)

    with pytest.raises(
        AnalysisQualityLoopSupervisorError,
        match="state changed before supervisor dispatch",
    ):
        run_quality_cycle(
            state_path=state_path,
            attempt_path=attempt_path,
            calibration_inputs=calibration_inputs,
            locked_inputs=lambda **_: (_ for _ in ()).throw(
                AssertionError("dispatch race must fail before S6")
            ),
            promotion_inputs=lambda **_: (_ for _ in ()).throw(
                AssertionError("dispatch race must fail before S7")
            ),
            post_merge_inputs=lambda **_: (_ for _ in ()).throw(
                AssertionError("dispatch race must fail before S8")
            ),
        )

    persisted = load_state(state_path)
    assert provider_calls["count"] == 0
    assert persisted["last_decision"] is None
    assert persisted["retry"]["budget_remaining"] == persisted["retry"]["budget_initial"]