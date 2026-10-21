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

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from src.analysis_candidate_iterator import (
    AnalysisCandidateIteratorError,
    SearchSpaceProvider,
    iterate_candidates,
)
from src.analysis_orchestration_run import (
    POLICY_UNSET,
    AnalysisOrchestrationRunError,
    resolve_decision_mode,
    run_orchestration,
)
from src.analysis_quality_loop_state import (
    AnalysisQualityLoopStateError,
    load_state,
    save_state_atomic,
    validate_state,
)
from src.aq_candidate_search_spaces import default_search_space_provider

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


def _state_commit_lock_path(state_path: Path) -> Path:
    normalized = os.path.normcase(str(state_path.resolve()))
    identity = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return Path(tempfile.gettempdir()) / f"sample-brain-s5-state-{identity}.lock"


def _state_commit_lock(state_path: Path):
    """Serialize only the compare-and-commit section for one S5 state path."""
    lock_path = _state_commit_lock_path(state_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b")
    if os.name == "nt":
        import msvcrt

        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.seek(0)
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        except OSError as exc:
            handle.close()
            raise AnalysisQualityLoopStateError(
                "failed to acquire supervisor state commit lock"
            ) from exc

        class _Lock:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                handle.close()

        return _Lock()

    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    except OSError as exc:
        handle.close()
        raise AnalysisQualityLoopStateError(
            "failed to acquire supervisor state commit lock"
        ) from exc

    class _Lock:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()

    return _Lock()


def _commit_state_if_unchanged(
    *,
    state_path: Path,
    expected_state_fingerprint: str,
    next_state: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare current S5 ownership and atomically commit under one path lock."""
    with _state_commit_lock(state_path):
        current = load_state(state_path)
        if current["state_fingerprint"] != expected_state_fingerprint:
            raise AnalysisQualityLoopStateError(
                "supervisor state changed before atomic commit"
            )
        return save_state_atomic(state_path, next_state)


def _default_provider(domain: str) -> SearchSpaceProvider:
    try:
        return default_search_space_provider(domain)
    except KeyError:
        raise AnalysisQualityLoopSupervisorError(
            f"no default search-space provider for domain {domain!r}"
        ) from None


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
    request_fingerprint: str | None = None,
    decision_provider_id: str | None = None,
) -> dict[str, Any]:
    analysis_eval = outcome.get("analysis_eval") or {}
    decision_evidence = (outcome.get("decision") or {}).get("evidence") or {}
    ref: dict[str, Any] = {
        "outcome_fingerprint": outcome["outcome_fingerprint"],
    }
    eval_fp = analysis_eval.get("artifact_fingerprint")
    if eval_fp is not None:
        ref["analysis_eval_fingerprint"] = eval_fp
    evidence_fp = decision_evidence.get("evidence_fingerprint")
    if evidence_fp is not None:
        ref["evidence_fingerprint"] = evidence_fp
    gate = (decision_evidence.get("gate_decision") or {}).get("verdict")
    if gate is not None:
        ref["gate_verdict"] = gate
    if decision_provider_id is not None:
        ref["request_fingerprint"] = request_fingerprint
        ref["decision_provider_id"] = decision_provider_id
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
    expected_state_fingerprint: str,
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
    return _commit_state_if_unchanged(
        state_path=state_path,
        expected_state_fingerprint=expected_state_fingerprint,
        next_state=updated,
    )


def run_supervisor_step(
    *,
    state_path: str | Path,
    request: Mapping[str, Any],
    bind_kwargs: Mapping[str, Any] | None = None,
    evidence_fingerprint: str | object = POLICY_UNSET,
    gate_verdict: str | None | object = POLICY_UNSET,
    decision_token: str | None | object = POLICY_UNSET,
    next_action: str | None | object = POLICY_UNSET,
    provider: SearchSpaceProvider | None = None,
    analysis_eval_artifact: Mapping[str, Any] | None = None,
    adapter_id: str | None = None,
    decision_provider=None,
    decision_provider_id: str | None = None,
    expected_state_fingerprint: str | None = None,
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

    if (
        expected_state_fingerprint is not None
        and state["state_fingerprint"] != expected_state_fingerprint
    ):
        raise AnalysisQualityLoopSupervisorError(
            "supervisor state changed before supervisor dispatch"
        )

    loop_status = state["loop_status"]
    if loop_status in _TERMINAL_LOOP_STATUSES:
        raise AnalysisQualityLoopSupervisorError(
            f"supervisor loop is {loop_status}; refusing further iteration"
        )

    bind = {} if bind_kwargs is None else dict(bind_kwargs)
    policy_inputs = {
        "evidence_fingerprint": evidence_fingerprint,
        "gate_verdict": gate_verdict,
        "decision_token": decision_token,
        "next_action": next_action,
    }
    try:
        resolve_decision_mode(decision_provider, decision_provider_id, policy_inputs)
    except AnalysisOrchestrationRunError as exc:
        raise AnalysisQualityLoopSupervisorError(str(exc)) from exc

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
            decision_provider=decision_provider,
            decision_provider_id=decision_provider_id,
        )
    except AnalysisQualityLoopSupervisorError:
        raise
    except Exception as exc:
        try:
            _persist_retry_failure(
                state_path=path,
                state=state,
                failure_class="unknown",
                expected_state_fingerprint=state["state_fingerprint"],
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
                    expected_state_fingerprint=state["state_fingerprint"],
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
            request_fingerprint=request.get("request_fingerprint"),
            decision_provider_id=decision_provider_id,
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
        committed = _commit_state_if_unchanged(
            state_path=path,
            expected_state_fingerprint=state["state_fingerprint"],
            next_state=validate_state(next_state),
        )
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
