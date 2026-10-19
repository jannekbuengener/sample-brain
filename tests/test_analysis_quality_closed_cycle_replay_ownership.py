"""Focused S9 replay-ownership regressions from final review."""

from __future__ import annotations

import pytest

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
