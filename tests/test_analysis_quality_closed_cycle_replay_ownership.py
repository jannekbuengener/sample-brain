"""Public S9 replay/dispatch ownership regressions from final review."""

from __future__ import annotations

import threading

import pytest

import src.analysis_quality_closed_cycle as closed_cycle
import src.analysis_quality_loop_supervisor as supervisor
from src.analysis_eval_artifact import fingerprint
from src.aq_candidate_search_spaces.aq1_tempo import Aq1TempoSearchSpaceProvider
from src.analysis_quality_closed_cycle import run_quality_cycle
from src.analysis_quality_loop_state import (
    AnalysisQualityLoopStateError,
    load_state,
    save_state_atomic,
)
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


def test_cycle_and_direct_supervisor_cannot_both_own_same_s5_commit(
    tmp_path, monkeypatch
) -> None:
    _patch_aq1_repo(monkeypatch, tmp_path)
    state_path = tmp_path / "host" / "quality-state.json"
    state_path.parent.mkdir()
    save_state_atomic(state_path, _fresh_aq1_state())
    initial = load_state(state_path)
    attempt_path = tmp_path / "host" / "cycle-attempt.json"
    cycle_work = tmp_path / "cycle-owner-work"
    competitor_work = tmp_path / "direct-s5-work"
    cycle_work.mkdir()
    competitor_work.mkdir()

    def calibration_inputs(*, state_path, state):
        request = _aq1_path_b_request(
            cycle_work,
            current_candidate_id=state["active_candidate"]["candidate_id"],
        )

        def decide(context):
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
            "bind_kwargs": {"work_dir": cycle_work},
            "decision_provider": decide,
            "decision_provider_id": "aq1-cycle-owner-policy-v1",
        }

    real_orchestration = supervisor.run_orchestration
    cycle_in_orchestration = threading.Event()
    release_cycle = threading.Event()

    def pause_cycle_orchestration(*args, **kwargs):
        if threading.current_thread().name == "cycle-owner":
            cycle_in_orchestration.set()
            if not release_cycle.wait(timeout=10):
                raise AssertionError("timed out waiting to release cycle orchestration")
        return real_orchestration(*args, **kwargs)

    monkeypatch.setattr(supervisor, "run_orchestration", pause_cycle_orchestration)

    cycle_errors: list[BaseException] = []
    competitor_errors: list[BaseException] = []

    def run_cycle() -> None:
        try:
            run_quality_cycle(
                state_path=state_path,
                attempt_path=attempt_path,
                calibration_inputs=calibration_inputs,
                locked_inputs=lambda **_: (_ for _ in ()).throw(
                    AssertionError("HOLD cycle must fail before S6")
                ),
                promotion_inputs=lambda **_: (_ for _ in ()).throw(
                    AssertionError("HOLD cycle must fail before S7")
                ),
                post_merge_inputs=lambda **_: (_ for _ in ()).throw(
                    AssertionError("HOLD cycle must fail before S8")
                ),
            )
        except BaseException as exc:  # noqa: BLE001 - thread handoff for assertion
            cycle_errors.append(exc)

    competitor_request = _aq1_path_b_request(
        competitor_work,
        current_candidate_id=initial["active_candidate"]["candidate_id"],
    )

    def run_competitor() -> None:
        try:
            supervisor.run_supervisor_step(
                state_path=state_path,
                request=competitor_request,
                bind_kwargs={"work_dir": competitor_work},
                evidence_fingerprint="a" * 64,
                gate_verdict="PASS",
                next_action="continue_calibration",
                provider=Aq1TempoSearchSpaceProvider(),
                expected_state_fingerprint=initial["state_fingerprint"],
            )
        except BaseException as exc:  # noqa: BLE001 - thread handoff for assertion
            competitor_errors.append(exc)

    cycle_thread = threading.Thread(target=run_cycle, name="cycle-owner")
    cycle_thread.start()
    assert cycle_in_orchestration.wait(timeout=10)

    competitor_thread = threading.Thread(target=run_competitor, name="direct-s5")
    competitor_thread.start()
    competitor_thread.join(timeout=10)
    release_cycle.set()
    cycle_thread.join(timeout=10)

    assert not competitor_thread.is_alive()
    assert not cycle_thread.is_alive()
    assert competitor_errors == []
    assert len(cycle_errors) == 1
    assert isinstance(cycle_errors[0], AnalysisQualityLoopStateError)
    assert "state changed before atomic commit" in str(cycle_errors[0])

    persisted = load_state(state_path)
    assert persisted["loop_status"] == "ready"
    assert persisted["generation"] == initial["generation"] + 1
    assert persisted["active_candidate"] != initial["active_candidate"]
    assert len(persisted["visited_candidate_ids"]) == 2
