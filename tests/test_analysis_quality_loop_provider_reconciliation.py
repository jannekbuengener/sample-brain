"""Regression tests for the #1179 provider contract at the S5 supervisor seam."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.analysis_quality_loop_state import load_state, save_state_atomic
from src.analysis_quality_loop_supervisor import (
    AnalysisQualityLoopSupervisorError,
    run_supervisor_step,
)
from tests.test_analysis_quality_loop_supervisor import (
    _aq1_path_b_request,
    _fresh_aq1_state,
    _patch_aq1_repo,
    _state_path,
)


def _provider(context):
    assert context["headless_result"]["run_status"] == "completed"
    assert context["analysis_eval"]["document_type"] == "sample-brain.analysis-eval.v1"
    return {
        "evidence_fingerprint": context["evidence_fingerprint"],
        "gate_verdict": "PASS",
        "decision_token": "KEEP_CURRENT_BASELINE_PATH",
        "next_action": "keep_baseline_and_stop",
    }


def _seed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _patch_aq1_repo(monkeypatch, tmp_path)
    work = tmp_path / "provider-reconciliation"
    work.mkdir()
    state_path = _state_path(tmp_path)
    state_path.parent.mkdir(parents=True)
    save_state_atomic(state_path, _fresh_aq1_state())
    return work, state_path


def test_supervisor_provider_mode_preserves_1179_omitted_policy_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work, state_path = _seed(tmp_path, monkeypatch)
    request = _aq1_path_b_request(work)

    result = run_supervisor_step(
        state_path=state_path,
        request=request,
        bind_kwargs={"work_dir": work},
        decision_provider=_provider,
        decision_provider_id="aq1-s9-provider-v1",
    )

    assert result["decision"]["next_action"] == "keep_baseline_and_stop"
    state = load_state(state_path)
    assert state["retry"]["budget_remaining"] == state["retry"]["budget_initial"]
    assert state["last_orchestration_ref"]["decision_provider_id"] == "aq1-s9-provider-v1"
    assert state["last_orchestration_ref"]["request_fingerprint"] == request[
        "request_fingerprint"
    ]


def test_supervisor_rejects_explicit_legacy_none_before_retry_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work, state_path = _seed(tmp_path, monkeypatch)
    before = load_state(state_path)

    with pytest.raises(AnalysisQualityLoopSupervisorError, match="mixed legacy/provider"):
        run_supervisor_step(
            state_path=state_path,
            request=_aq1_path_b_request(work),
            bind_kwargs={"work_dir": work},
            evidence_fingerprint=None,
            decision_provider=_provider,
            decision_provider_id="aq1-s9-provider-v1",
        )

    assert load_state(state_path) == before
