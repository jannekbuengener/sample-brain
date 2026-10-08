"""Sample Brain analysis quality-loop supervisor composition v1 (#1097).

One-step composition:

    load/fresh supervisor state
      → run_orchestration (#1060)
      → consume decision.next_action unchanged (#1043)
      → iff continue_calibration: exactly one iterate_candidates (#1064)
      → build next portable state
      → atomic save (commit boundary)

No persisted ``running``. No reinterpretation of decision vocabulary.
``production_authorized`` remains false. AQ1 Path B is the proof domain.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from src.analysis_candidate_iterator import (
    AnalysisCandidateIteratorError,
    SearchSpaceProvider,
    iterate_candidates,
)
from src.analysis_orchestration_run import (
    AnalysisOrchestrationRunError,
    run_orchestration,
)
from src.analysis_quality_loop_state import (
    AnalysisQualityLoopStateError,
    load_state,
    save_state_atomic,
    validate_state,
)
from src.aq_candidate_search_spaces.aq1_tempo import Aq1TempoSearchSpaceProvider

# Terminal statuses that refuse further supervisor steps.
_TERMINAL_LOOP_STATUSES: frozenset[str] = frozenset(
    {
        "held",
        "frozen",
        "stopped",
        "exhausted",
        "controlled_failure",
        "retry_exhausted",
    }
)

_ACTION_TO_STATUS: Mapping[str, str] = {
    "freeze_candidate": "frozen",
    "keep_baseline_and_stop": "stopped",
    "require_human_governance": "stopped",
    "defer_for_evidence": "held",
    "stop_controlled_failure": "controlled_failure",
}

_EFFECT_TO_STATUS: Mapping[str, str] = {
    "advance": "ready",
    "exhausted": "exhausted",
    "freeze": "frozen",
    "stop": "stopped",
    "hold": "held",
    "controlled_failure": "controlled_failure",
}


class AnalysisQualityLoopSupervisorError(ValueError):
    """Raised when supervisor composition violates the v1 contract."""


def _default_provider(domain: str) -> SearchSpaceProvider:
    if domain == "aq1.tempo":
        return Aq1TempoSearchSpaceProvider()
    raise AnalysisQualityLoopSupervisorError(
        f"no default search-space provider for domain {domain!r}"
    )


def _decision_ref(decision: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "decision_status": decision["decision_status"],
        "decision_token": decision.get("decision_token"),
        "next_action": decision["next_action"],
        "decision_fingerprint": decision["decision_fingerprint"],
    }


def _orchestration_ref(
    outcome: Mapping[str, Any],
    *,
    evidence_fingerprint: str,
    gate_verdict: str | None,
) -> dict[str, Any]:
    analysis_eval = outcome.get("analysis_eval") or {}
    ref: dict[str, Any] = {
        "outcome_fingerprint": outcome["outcome_fingerprint"],
    }
    eval_fp = analysis_eval.get("artifact_fingerprint")
    if eval_fp is not None:
        ref["analysis_eval_fingerprint"] = eval_fp
    ref["evidence_fingerprint"] = evidence_fingerprint
    if gate_verdict is not None:
        ref["gate_verdict"] = gate_verdict
    return ref


def _iterator_ref(iterator_result: Mapping[str, Any]) -> dict[str, Any]:
    ref: dict[str, Any] = {
        "iterator_effect": iterator_result["iterator_effect"],
        "result_fingerprint": iterator_result["result_fingerprint"],
    }
    next_candidate = iterator_result.get("next_candidate")
    if next_candidate is not None:
        ref["next_candidate"] = {
            "candidate_id": next_candidate["candidate_id"],
            "config_fingerprint": next_candidate["config_fingerprint"],
        }
    return ref


def _step_result(
    *,
    state: Mapping[str, Any],
    outcome: Mapping[str, Any],
    iterator_result: Mapping[str, Any] | None,
    already_committed: bool = False,
) -> dict[str, Any]:
    decision = outcome["decision"]
    result: dict[str, Any] = {
        "production_authorized": False,
        "already_committed": already_committed,
        "orchestration": {
            "outcome_fingerprint": outcome["outcome_fingerprint"],
        },
        "decision": {
            "decision_status": decision["decision_status"],
            "decision_token": decision.get("decision_token"),
            "next_action": decision["next_action"],
            "decision_fingerprint": decision["decision_fingerprint"],
            "production_authorized": bool(decision.get("production_authorized", False)),
        },
        "state": dict(state),
    }
    if iterator_result is not None:
        result["iterator"] = {
            "iterator_effect": iterator_result["iterator_effect"],
            "result_fingerprint": iterator_result["result_fingerprint"],
            "next_candidate": iterator_result.get("next_candidate"),
        }
    return result


def _persist_retry_failure(
    *,
    state_path: Path,
    state: Mapping[str, Any],
    failure_class: str,
) -> dict[str, Any]:
    """Decrement persisted retry budget after a counted infrastructure failure."""
    retry = dict(state["retry"])
    remaining = int(retry["budget_remaining"])
    if remaining > 0:
        remaining -= 1
    retry["budget_remaining"] = remaining
    retry["consecutive_failures"] = int(retry["consecutive_failures"]) + 1
    retry["last_failure_class"] = failure_class
    updated = dict(state)
    updated["retry"] = retry
    if remaining == 0:
        updated["loop_status"] = "retry_exhausted"
    # Keep generation unchanged; failure is not a committed iteration.
    updated.pop("state_fingerprint", None)
    return save_state_atomic(state_path, updated)


def run_supervisor_step(
    *,
    state_path: str | Path,
    request: Mapping[str, Any],
    bind_kwargs: Mapping[str, Any] | None = None,
    evidence_fingerprint: str,
    gate_verdict: str | None = None,
    decision_token: str | None = None,
    next_action: str | None = None,
    provider: SearchSpaceProvider | None = None,
    analysis_eval_artifact: Mapping[str, Any] | None = None,
    adapter_id: str | None = None,
) -> dict[str, Any]:
    """Execute one supervisor step and commit the next portable state atomically."""
    path = Path(state_path)
    try:
        state = load_state(path)
    except AnalysisQualityLoopStateError:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise AnalysisQualityLoopSupervisorError(
            f"failed to load supervisor state: {exc}"
        ) from exc

    loop_status = state["loop_status"]
    if loop_status in _TERMINAL_LOOP_STATUSES:
        raise AnalysisQualityLoopSupervisorError(
            f"supervisor loop is {loop_status}; refusing further iteration"
        )

    bind = {} if bind_kwargs is None else dict(bind_kwargs)

    try:
        outcome = run_orchestration(
            request=request,
            bind_kwargs=bind,
            evidence_fingerprint=evidence_fingerprint,
            gate_verdict=gate_verdict,
            decision_token=decision_token,
            next_action=next_action,
            analysis_eval_artifact=analysis_eval_artifact,
            adapter_id=adapter_id,
        )
    except AnalysisQualityLoopSupervisorError:
        raise
    except Exception as exc:
        try:
            _persist_retry_failure(
                state_path=path,
                state=state,
                failure_class="unknown",
            )
        except AnalysisQualityLoopStateError as persist_exc:
            raise AnalysisQualityLoopSupervisorError(
                f"infrastructure failure and retry persist failed: {persist_exc}"
            ) from exc
        raise AnalysisQualityLoopSupervisorError(
            f"infrastructure failure during orchestration: {exc}"
        ) from exc

    decision = outcome["decision"]
    action = decision["next_action"]
    outcome_fp = outcome["outcome_fingerprint"]
    last_orch = state.get("last_orchestration_ref") or {}
    if last_orch.get("outcome_fingerprint") == outcome_fp:
        # Replay / duplicate completion: do not advance again.
        return _step_result(
            state=state,
            outcome=outcome,
            iterator_result=None,
            already_committed=True,
        )

    iterator_result: dict[str, Any] | None = None
    next_active = dict(state["active_candidate"])
    next_visited = list(state["visited_candidate_ids"])
    iteration_index = int(state["iteration_index"])
    next_loop_status: str

    if action == "continue_calibration":
        space = provider or _default_provider(str(state["domain"]))
        try:
            iterator_result = iterate_candidates(
                domain=str(state["domain"]),
                next_action=action,
                partition_role=str(state["partition"]["role"]),
                provider=space,
                current_candidate_id=str(state["active_candidate"]["candidate_id"]),
                current_config_fingerprint=str(
                    state["active_candidate"]["config_fingerprint"]
                ),
                visited_candidate_ids=list(state["visited_candidate_ids"]),
                search_space_fingerprint=str(state["search_space_fingerprint"]),
                iteration_index=int(state["iteration_index"])
                if int(state["iteration_index"]) > 0
                else None,
                max_iterations=state.get("max_iterations"),
            )
        except (
            AnalysisCandidateIteratorError,
            AnalysisOrchestrationRunError,
        ) as exc:
            try:
                _persist_retry_failure(
                    state_path=path,
                    state=state,
                    failure_class="iterator_failure",
                )
            except AnalysisQualityLoopStateError as persist_exc:
                raise AnalysisQualityLoopSupervisorError(
                    f"iterator failure and retry persist failed: {persist_exc}"
                ) from exc
            raise AnalysisQualityLoopSupervisorError(
                f"iterator failure: {exc}"
            ) from exc

        effect = iterator_result["iterator_effect"]
        next_loop_status = _EFFECT_TO_STATUS[effect]
        if effect == "advance":
            next_candidate = iterator_result["next_candidate"]
            next_active = {
                "candidate_id": next_candidate["candidate_id"],
                "config_fingerprint": next_candidate["config_fingerprint"],
            }
            next_visited = list(iterator_result["visited_candidate_ids"])
            iteration_index = int(iterator_result["iteration_index"])
        else:
            next_visited = list(iterator_result["visited_candidate_ids"])
            iteration_index = int(iterator_result["iteration_index"])
    else:
        # Non-continue actions: consume decision unchanged; do not invent candidates.
        if action not in _ACTION_TO_STATUS:
            raise AnalysisQualityLoopSupervisorError(
                f"unsupported next_action for supervisor v1: {action!r}"
            )
        next_loop_status = _ACTION_TO_STATUS[action]

    history = list(state.get("history_refs") or [])
    history.append(outcome_fp)
    if iterator_result is not None:
        history.append(iterator_result["result_fingerprint"])

    retry = dict(state["retry"])
    retry["consecutive_failures"] = 0
    retry["last_failure_class"] = None

    next_state: dict[str, Any] = {
        "document_type": state["document_type"],
        "artifact_version": state["artifact_version"],
        "schema_version": state["schema_version"],
        "domain": state["domain"],
        "partition": dict(state["partition"]),
        "baseline_candidate": dict(state["baseline_candidate"]),
        "active_candidate": next_active,
        "last_known_good": state.get("last_known_good"),
        "visited_candidate_ids": next_visited,
        "search_space_id": state["search_space_id"],
        "search_space_version": state["search_space_version"],
        "search_space_fingerprint": state["search_space_fingerprint"],
        "iteration_index": iteration_index,
        "max_iterations": state.get("max_iterations"),
        "loop_status": next_loop_status,
        "last_decision": _decision_ref(decision),
        "last_orchestration_ref": _orchestration_ref(
            outcome,
            evidence_fingerprint=evidence_fingerprint,
            gate_verdict=gate_verdict,
        ),
        "last_iterator_ref": (
            None if iterator_result is None else _iterator_ref(iterator_result)
        ),
        "history_refs": history,
        "retry": retry,
        "generation": int(state["generation"]) + 1,
        "production_authorized": False,
    }

    try:
        committed = save_state_atomic(path, validate_state(next_state))
    except AnalysisQualityLoopStateError:
        # Observable write failure; previous committed state remains authoritative.
        raise
    except OSError as exc:
        raise AnalysisQualityLoopStateError(
            f"atomic supervisor state write failed: {exc}"
        ) from exc

    return _step_result(
        state=committed,
        outcome=outcome,
        iterator_result=iterator_result,
        already_committed=False,
    )


__all__ = [
    "AnalysisQualityLoopSupervisorError",
    "run_orchestration",
    "run_supervisor_step",
]
