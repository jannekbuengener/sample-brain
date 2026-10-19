"""S9 composition of the existing analysis quality-loop controllers.

This module coordinates durable S5/S6/S7/S8 results. Domain policy, candidate
iteration, locked evaluation, promotion, and post-merge acceptance remain owned
by their existing components.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

from src.analysis_eval_artifact import assert_portable_value, fingerprint
from src.analysis_locked_holdout import (
    _write_atomic,
    run_locked_holdout_transition,
)
from src.analysis_post_merge import load_baseline_lineage, run_post_merge
from src.analysis_promotion import run_promotion
from src.analysis_quality_loop_state import (
    fresh_state,
    load_state,
    save_state_atomic,
)
from src.analysis_quality_loop_supervisor import run_supervisor_step

DOCUMENT_TYPE = "sample-brain.analysis-quality-loop-closed-cycle.v1"
ATTEMPT_TYPE = "sample-brain.analysis-quality-loop-closed-cycle-attempt.v1"
ARTIFACT_VERSION = "1.0.0"
OUTCOME_TOKEN = "AUTONOMOUS_QUALITY_LOOP_FIRST_CLOSED_CYCLE"
_ATTEMPT_KEYS = {
    "document_type", "artifact_version", "cycle_id", "domain",
    "initial_state_fingerprint", "initial_baseline_candidate",
    "initial_baseline_generation", "partition", "search_space_fingerprint",
    "phase", "status", "pending", "calibration_refs", "candidate_history",
    "locked_ref", "promotion_ref", "post_merge_ref", "continuation_ref",
    "reason", "production_authorized", "attempt_fingerprint",
}
_PHASES = {
    "calibration", "locked", "promotion", "post_merge", "continuation",
    "held", "failed", "completed",
}


class AnalysisQualityClosedCycleError(ValueError):
    """Invalid S9 composition state or a controller stopped without proof."""


def _result_path(attempt_path: Path) -> Path:
    return attempt_path.with_name(f"{attempt_path.stem}.result.json")


def _seal_attempt(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result.pop("attempt_fingerprint", None)
    assert_portable_value(result)
    result["attempt_fingerprint"] = fingerprint(result)
    return result


def _load_attempt(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AnalysisQualityClosedCycleError("missing or corrupt cycle attempt") from exc
    if not isinstance(value, dict):
        raise AnalysisQualityClosedCycleError("cycle attempt must be a mapping")
    if (
        set(value) != _ATTEMPT_KEYS
        or value.get("artifact_version") != ARTIFACT_VERSION
        or value.get("phase") not in _PHASES
        or value.get("status") not in {"running", "held", "failed", "completed"}
        or value.get("production_authorized") is not False
        or not isinstance(value.get("calibration_refs"), list)
        or not isinstance(value.get("candidate_history"), list)
    ):
        raise AnalysisQualityClosedCycleError("invalid closed-cycle attempt schema")
    pending = value.get("pending")
    if pending is not None:
        if not isinstance(pending, dict) or set(pending) != {
            "phase", "identity", "invocation_fingerprint"
        }:
            raise AnalysisQualityClosedCycleError("invalid pending cycle invocation")
        if (
            pending["phase"] != value["phase"]
            or not isinstance(pending["identity"], dict)
            or pending["invocation_fingerprint"]
            != fingerprint({"phase": pending["phase"], "identity": pending["identity"]})
        ):
            raise AnalysisQualityClosedCycleError("pending invocation fingerprint mismatch")
    sealed = _seal_attempt(value)
    if value != sealed or value.get("document_type") != ATTEMPT_TYPE:
        raise AnalysisQualityClosedCycleError("cycle attempt fingerprint mismatch")
    return value


def _new_attempt(state: Mapping[str, Any]) -> dict[str, Any]:
    cycle_id = fingerprint(
        {
            "domain": state["domain"],
            "initial_state_fingerprint": state["state_fingerprint"],
            "schema": ARTIFACT_VERSION,
        }
    )
    return _seal_attempt(
        {
            "document_type": ATTEMPT_TYPE,
            "artifact_version": ARTIFACT_VERSION,
            "cycle_id": cycle_id,
            "domain": state["domain"],
            "initial_state_fingerprint": state["state_fingerprint"],
            "initial_baseline_candidate": state["baseline_candidate"],
            "initial_baseline_generation": state["generation"],
            "partition": state["partition"],
            "search_space_fingerprint": state["search_space_fingerprint"],
            "phase": "calibration",
            "status": "running",
            "pending": None,
            "calibration_refs": [],
            "candidate_history": [item for item in state["visited_candidate_ids"]],
            "locked_ref": None,
            "promotion_ref": None,
            "post_merge_ref": None,
            "continuation_ref": None,
            "reason": None,
            "production_authorized": False,
        }
    )


def _save_attempt(path: Path, state: Mapping[str, Any]) -> dict[str, Any]:
    sealed = _seal_attempt(state)
    _write_atomic(path, sealed)
    return sealed


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AnalysisQualityClosedCycleError("required controller result is missing") from exc
    if not isinstance(value, dict):
        raise AnalysisQualityClosedCycleError("controller result must be a mapping")
    assert_portable_value(value)
    return value


def _read_result(path: Path) -> dict[str, Any]:
    value = _read_json(path)
    check = dict(value)
    result_fp = check.pop("result_fingerprint", None)
    post_merge = value.get("post_merge_ref")
    accepted_baseline = value.get("accepted_baseline")
    continuation = value.get("continuation_ref")
    if (
        set(value)
        != {
            "document_type", "artifact_version", "cycle_id", "domain",
            "initial_baseline_candidate", "initial_baseline_generation",
            "final_candidate", "calibration_refs", "candidate_history",
            "locked_ref", "promotion_ref", "post_merge_ref",
            "accepted_baseline", "last_known_good", "continuation_ref",
            "component_contracts", "evidence_classifications", "outcome_token",
            "production_authorized", "result_fingerprint",
        }
        or value.get("document_type") != DOCUMENT_TYPE
        or value.get("artifact_version") != ARTIFACT_VERSION
        or value.get("outcome_token") != OUTCOME_TOKEN
        or value.get("production_authorized") is not False
        or result_fp != fingerprint(check)
        or not isinstance(post_merge, dict)
        or post_merge.get("status") != "accepted"
        or not isinstance(accepted_baseline, dict)
        or accepted_baseline.get("candidate") != value.get("final_candidate")
        or value.get("last_known_good") is None
        or not isinstance(continuation, dict)
        or continuation.get("next_action") != "continue_calibration"
    ):
        raise AnalysisQualityClosedCycleError("closed-cycle result fingerprint mismatch")
    return value


def _require_simulation_repository(inputs: Mapping[str, Any], manifest: Mapping[str, Any]) -> None:
    repository = inputs.get("repository")
    repository_path = getattr(repository, "path", None)
    if repository_path is None:
        raise AnalysisQualityClosedCycleError("S9 promotion requires an isolated Git repository")
    resolved_repository = Path(repository_path).resolve()
    temporary_root = Path(tempfile.gettempdir()).resolve()
    try:
        resolved_repository.relative_to(temporary_root)
    except ValueError:
        raise AnalysisQualityClosedCycleError(
            "S9 promotion repository must live under a temporary directory"
        ) from None
    source_root = Path(__file__).resolve().parents[1]
    if resolved_repository == source_root:
        raise AnalysisQualityClosedCycleError("S9 cannot promote into its own Sample Brain repository")
    identity = str(manifest.get("repository_id", "")).casefold()
    if "jannekbuengener/sample-brain" in identity:
        raise AnalysisQualityClosedCycleError("real Sample Brain self-promotion is outside S9 proof scope")
    try:
        origin = repository.git("remote", "get-url", "origin").casefold()
    except Exception as exc:
        raise AnalysisQualityClosedCycleError(
            "S9 cannot verify the temporary proof repository remote"
        ) from exc
    if "jannekbuengener/sample-brain" in origin or "sample-brain.git" in origin:
        raise AnalysisQualityClosedCycleError("S9 promotion remote must be a temporary proof repository")


def _domain_lock_path(state_path: Path, state: Mapping[str, Any]) -> Path:
    identity = fingerprint(
        {
            "domain": state["domain"],
            "baseline_candidate": state["baseline_candidate"],
            "search_space_fingerprint": state["search_space_fingerprint"],
        }
    )[:24]
    return state_path.parent / f".analysis-quality-cycle-{identity}.lock"


def _provider_id(inputs: dict[str, Any], *, remove: bool = True) -> str:
    provider_id = (
        inputs.pop("decision_provider_id", None)
        if remove
        else inputs.get("decision_provider_id")
    )
    if not isinstance(provider_id, str) or not provider_id or len(provider_id) > 128:
        raise AnalysisQualityClosedCycleError("stable decision_provider_id is required")
    if not provider_id[0].isalnum() or any(
        char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-"
        for char in provider_id
    ):
        raise AnalysisQualityClosedCycleError("invalid decision_provider_id")
    if not callable(inputs.get("decision_provider")):
        raise AnalysisQualityClosedCycleError("decision_provider must be callable")
    return provider_id


def _replay_committed_promotion(
    *,
    cycle: Mapping[str, Any],
    locked: Mapping[str, Any],
    state_path: Path,
    manifest: Mapping[str, Any],
    promotion_args: Mapping[str, Any],
) -> dict[str, Any]:
    expected = cycle.get("promotion_ref") or {}
    if locked.get("result_fingerprint") != (cycle.get("locked_ref") or {}).get(
        "result_fingerprint"
    ):
        raise AnalysisQualityClosedCycleError("locked S6 result differs from committed cycle identity")
    if manifest.get("manifest_fingerprint") != expected.get("manifest_fingerprint"):
        raise AnalysisQualityClosedCycleError("S7 manifest differs from committed cycle identity")
    promoted = run_promotion(
        source_state_path=state_path, manifest=manifest, **dict(promotion_args)
    )
    actual = {
        "manifest_fingerprint": manifest.get("manifest_fingerprint"),
        "attempt_fingerprint": promoted.get("state_fingerprint"),
        "status": promoted.get("status"),
        "pr_number": promoted.get("pr_number"),
        "head_sha": promoted.get("head_sha"),
        "merge_sha": promoted.get("merge_sha"),
    }
    for key, value in actual.items():
        if expected.get(key) != value:
            raise AnalysisQualityClosedCycleError(
                f"replayed S7 {key} differs from committed cycle identity"
            )
    if promoted.get("status") != "merged" or promoted.get(
        "repository_merge_eligible"
    ) is not True:
        raise AnalysisQualityClosedCycleError("committed S7 promotion is no longer merge eligible")
    return promoted


def _recovered_orchestration_ref(
    supervisor_state: Mapping[str, Any],
    identity: Mapping[str, Any],
    phase: str,
) -> Mapping[str, Any]:
    ref = supervisor_state.get("last_orchestration_ref") or {}
    if (
        ref.get("request_fingerprint") != identity.get("request_fingerprint")
        or ref.get("decision_provider_id") != identity.get("decision_provider_id")
    ):
        raise AnalysisQualityClosedCycleError(
            f"{phase} state changed outside the pending invocation"
        )
    return ref


def _require_cycle_owned_freeze(
    cycle: Mapping[str, Any], supervisor_state: Mapping[str, Any]
) -> None:
    decision = supervisor_state.get("last_decision") or {}
    refs = cycle.get("calibration_refs") or []
    last = refs[-1] if refs else {}
    if (
        decision.get("next_action") != "freeze_candidate"
        or last.get("next_action") != "freeze_candidate"
        or last.get("decision_fingerprint") != decision.get("decision_fingerprint")
        or last.get("candidate") != supervisor_state.get("active_candidate")
    ):
        raise AnalysisQualityClosedCycleError(
            "frozen S5 state lacks this cycle's committed selection evidence"
        )


def _retry_only_s5_update(identity: Mapping[str, Any], state: Mapping[str, Any]) -> bool:
    retry_before = identity.get("retry") or {}
    retry_now = state.get("retry") or {}
    return (
        state.get("generation") == identity.get("s5_generation")
        and (state.get("last_decision") or {}).get("decision_fingerprint")
        == identity.get("previous_decision_fingerprint")
        and state.get("active_candidate") == identity.get("active_candidate")
        and state.get("visited_candidate_ids") == identity.get("visited_candidate_ids")
        and retry_now.get("budget_remaining", retry_before.get("budget_remaining", 0))
        < retry_before.get("budget_remaining", 0)
        and retry_now.get("consecutive_failures", 0)
        > retry_before.get("consecutive_failures", 0)
        and bool(retry_now.get("last_failure_class"))
        and state.get("loop_status") == "ready"
    )


def _require_committed_post_merge_replay(
    cycle: Mapping[str, Any], plan: Mapping[str, Any], merged: Mapping[str, Any]
) -> None:
    expected = cycle.get("post_merge_ref") or {}
    actual = {
        "plan_fingerprint": plan.get("plan_fingerprint"),
        "attempt_fingerprint": merged.get("state_fingerprint"),
        "status": merged.get("status"),
        "merge_sha": merged.get("merge_sha"),
        "accepted_baseline_fingerprint": merged.get(
            "accepted_baseline_fingerprint"
        ),
        "last_known_good_fingerprint": merged.get("last_known_good_fingerprint"),
        "baseline_generation_start": merged.get("baseline_generation_start"),
        "baseline_verification_refs": merged.get("baseline_verification_refs"),
        "promoted_verification_refs": merged.get("promoted_verification_refs"),
        "recovery_verification_refs": merged.get("recovery_verification_refs"),
    }
    if any(expected.get(key) != value for key, value in actual.items()):
        raise AnalysisQualityClosedCycleError(
            "replayed S8 acceptance differs from committed cycle identity"
        )
    if merged.get("status") != "accepted":
        raise AnalysisQualityClosedCycleError(
            "committed S8 acceptance is no longer valid"
        )


def _pending(state: dict[str, Any], phase: str, identity: Mapping[str, Any]) -> None:
    invocation_fp = fingerprint({"phase": phase, "identity": dict(identity)})
    prior = state.get("pending")
    if prior is not None and prior != {
        "phase": phase,
        "identity": dict(identity),
        "invocation_fingerprint": invocation_fp,
    }:
        raise AnalysisQualityClosedCycleError("pending cycle invocation identity mismatch")
    state["pending"] = {
        "phase": phase,
        "identity": dict(identity),
        "invocation_fingerprint": invocation_fp,
    }


def _commit_phase(path: Path, state: dict[str, Any], phase: str) -> dict[str, Any]:
    state["phase"] = phase
    state["pending"] = None
    return _save_attempt(path, state)


def _ref_from_supervisor(
    result: Mapping[str, Any], state: Mapping[str, Any], request_fp: str | None
) -> dict[str, Any]:
    orchestration = result.get("orchestration") or {}
    decision = result.get("decision") or {}
    evidence = state.get("last_orchestration_ref") or {}
    return {
        "candidate": state.get("active_candidate"),
        "baseline_candidate": state.get("baseline_candidate"),
        "request_fingerprint": request_fp,
        "outcome_fingerprint": orchestration.get("outcome_fingerprint"),
        "analysis_eval_fingerprint": evidence.get("analysis_eval_fingerprint"),
        "evidence_fingerprint": evidence.get("evidence_fingerprint"),
        "decision_fingerprint": decision.get("decision_fingerprint"),
        "decision_status": decision.get("decision_status"),
        "decision_token": decision.get("decision_token"),
        "next_action": decision.get("next_action"),
    }


def _file_lock(path: Path):
    """Return a process lock; the OS releases it after a crash."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    if os.name == "nt":
        import msvcrt

        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.seek(0)
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            handle.close()
            raise AnalysisQualityClosedCycleError("cycle generation is already executing") from exc

        class _Lock:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                handle.close()

        return _Lock()
    else:
        import fcntl

        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise AnalysisQualityClosedCycleError("cycle generation is already executing") from exc

        class _Lock:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                handle.close()

        return _Lock()


def _write_result(
    attempt_path: Path,
    attempt: Mapping[str, Any],
    lineage: Mapping[str, Any],
) -> dict[str, Any]:
    state = dict(attempt)
    body = {
        "document_type": DOCUMENT_TYPE,
        "artifact_version": ARTIFACT_VERSION,
        "cycle_id": state["cycle_id"],
        "domain": state["domain"],
        "initial_baseline_candidate": state["initial_baseline_candidate"],
        "initial_baseline_generation": state["initial_baseline_generation"],
        "final_candidate": state["locked_ref"]["current_candidate"],
        "calibration_refs": state["calibration_refs"],
        "candidate_history": state["candidate_history"],
        "locked_ref": state["locked_ref"],
        "promotion_ref": state["promotion_ref"],
        "post_merge_ref": state["post_merge_ref"],
        "accepted_baseline": lineage["current"],
        "last_known_good": lineage["last_known_good"],
        "continuation_ref": state["continuation_ref"],
        "component_contracts": {
            "decision": "sample-brain.analysis-automation-decision.v1",
            "headless": "sample-brain.analysis-headless-run.v1",
            "orchestration": "sample-brain.analysis-orchestration-run.v1",
            "candidate_iterator": "sample-brain.analysis-candidate-iterator.v1",
            "supervisor": "sample-brain.analysis-quality-loop-supervisor.v1",
            "locked_holdout": "sample-brain.analysis-locked-holdout-result.v1",
            "promotion": "sample-brain.analysis-promotion-attempt.v1",
            "post_merge": "sample-brain.analysis-post-merge-attempt.v1",
        },
        "evidence_classifications": {
            "domain_execution": "REAL_SANITIZED_DOMAIN_EXECUTION",
            "proof_evaluator": "INJECTED_PROOF_EVALUATOR",
            "repository_governance": "INFRASTRUCTURE_SIMULATION",
            "production_quality_claim": False,
        },
        "outcome_token": OUTCOME_TOKEN,
        "production_authorized": False,
    }
    assert_portable_value(body)
    result = {**body, "result_fingerprint": fingerprint(body)}
    _write_atomic(_result_path(attempt_path), result)
    return result


def run_quality_cycle(
    *,
    state_path: str | os.PathLike[str],
    attempt_path: str | os.PathLike[str],
    calibration_inputs: Callable[..., Mapping[str, Any]],
    locked_inputs: Callable[..., Mapping[str, Any]],
    promotion_inputs: Callable[..., Mapping[str, Any]],
    post_merge_inputs: Callable[..., Mapping[str, Any]],
    max_transitions: int = 64,
) -> dict[str, Any]:
    """Self-start/resume one bounded AQ cycle through the existing S5–S8 owners.

    Input factories adapt portable controller results to domain-specific frozen
    requests and promotion/verification plans. They never choose a decision.
    """
    s5_path = Path(state_path)
    cycle_path = Path(attempt_path)
    if isinstance(max_transitions, bool) or not isinstance(max_transitions, int) or max_transitions < 1:
        raise AnalysisQualityClosedCycleError("max_transitions must be a positive integer")

    initial_s5 = load_state(s5_path)
    with _file_lock(_domain_lock_path(s5_path, initial_s5)):
        s5 = load_state(s5_path)
        if cycle_path.exists():
            cycle = _load_attempt(cycle_path)
            if (
                cycle["domain"] != s5["domain"]
                or cycle["initial_baseline_candidate"] != s5["baseline_candidate"]
                or cycle["partition"] != s5["partition"]
                or cycle["search_space_fingerprint"]
                != s5["search_space_fingerprint"]
            ):
                raise AnalysisQualityClosedCycleError("stale S5 baseline generation")
        else:
            if s5["loop_status"] != "ready":
                raise AnalysisQualityClosedCycleError("self-start requires ready S5 state")
            cycle = _new_attempt(s5)
            _save_attempt(cycle_path, cycle)
        if cycle["status"] == "completed":
            return _read_result(_result_path(cycle_path))
        if _result_path(cycle_path).exists():
            completed_result = _read_result(_result_path(cycle_path))
            if completed_result["cycle_id"] != cycle["cycle_id"]:
                raise AnalysisQualityClosedCycleError("result belongs to another cycle")
            cycle["status"] = "completed"
            cycle["phase"] = "completed"
            cycle["pending"] = None
            _save_attempt(cycle_path, cycle)
            return completed_result
        if cycle["status"] in {"held", "failed"}:
            return cycle

        for _ in range(max_transitions):
            phase = cycle["phase"]
            s5 = load_state(s5_path)

            if phase == "calibration":
                pending = cycle.get("pending")
                if pending and pending.get("phase") == phase:
                    identity = pending.get("identity") or {}
                    if identity.get("s5_state_fingerprint") != s5["state_fingerprint"]:
                        if _retry_only_s5_update(identity, s5):
                            cycle["pending"] = None
                            _save_attempt(cycle_path, cycle)
                            continue
                        current_decision = s5.get("last_decision") or {}
                        previous_orchestration = _recovered_orchestration_ref(
                            s5, identity, "S5"
                        )
                        recovered = {
                            "orchestration": {
                                "outcome_fingerprint": previous_orchestration.get(
                                    "outcome_fingerprint"
                                )
                            },
                            "decision": current_decision,
                        }
                        cycle["calibration_refs"].append(
                            _ref_from_supervisor(
                                recovered,
                                s5,
                                identity.get("request_fingerprint"),
                            )
                        )
                        cycle["calibration_refs"][-1]["candidate"] = identity[
                            "active_candidate"
                        ]
                        cycle["calibration_refs"][-1]["decision_provider_id"] = identity[
                            "decision_provider_id"
                        ]
                        cycle["candidate_history"] = list(s5["visited_candidate_ids"])
                        action = current_decision.get("next_action")
                        cycle = _commit_phase(
                            cycle_path,
                            cycle,
                            "locked" if action == "freeze_candidate" else "calibration",
                        )
                        if current_decision.get("decision_status") != "ready" or action not in {
                            "continue_calibration", "freeze_candidate"
                        }:
                            cycle["status"] = "held"
                            cycle["reason"] = "calibration_decision_not_actionable"
                            return _save_attempt(cycle_path, cycle)
                        continue
                if s5["loop_status"] == "frozen":
                    _require_cycle_owned_freeze(cycle, s5)
                    cycle = _commit_phase(cycle_path, cycle, "locked")
                    continue
                if s5["loop_status"] != "ready":
                    cycle["status"] = "held"
                    cycle["reason"] = f"calibration_{s5['loop_status']}"
                    return _save_attempt(cycle_path, cycle)
                inputs = dict(calibration_inputs(state_path=s5_path, state=s5))
                policy_id = _provider_id(inputs)
                request = inputs.get("request")
                if not isinstance(request, Mapping):
                    raise AnalysisQualityClosedCycleError("calibration input lacks request")
                request_fp = request.get("request_fingerprint")
                _pending(cycle, phase, {
                    "s5_state_fingerprint": s5["state_fingerprint"],
                    "previous_decision_fingerprint": (s5.get("last_decision") or {}).get(
                        "decision_fingerprint"
                    ),
                    "s5_generation": s5["generation"],
                    "active_candidate": s5["active_candidate"],
                    "visited_candidate_ids": list(s5["visited_candidate_ids"]),
                    "retry": dict(s5["retry"]),
                    "decision_provider_id": policy_id,
                    "request_fingerprint": request_fp,
                })
                _save_attempt(cycle_path, cycle)
                evaluated_candidate = s5["active_candidate"]
                result = run_supervisor_step(
                    state_path=s5_path,
                    decision_provider_id=policy_id,
                    **inputs,
                )
                post_state = load_state(s5_path)
                ref = _ref_from_supervisor(result, post_state, request_fp)
                ref["candidate"] = evaluated_candidate
                ref["decision_provider_id"] = policy_id
                cycle["calibration_refs"].append(ref)
                cycle["candidate_history"] = list(post_state["visited_candidate_ids"])
                action = result["decision"]["next_action"]
                cycle = _commit_phase(
                    cycle_path,
                    cycle,
                    "locked" if action == "freeze_candidate" else "calibration",
                )
                if result["decision"]["decision_status"] != "ready" or action not in {
                    "continue_calibration", "freeze_candidate"
                }:
                    cycle["status"] = "held"
                    cycle["reason"] = "calibration_decision_not_actionable"
                    return _save_attempt(cycle_path, cycle)
                continue

            if phase == "locked":
                if s5["loop_status"] != "frozen":
                    raise AnalysisQualityClosedCycleError("S6 requires frozen S5 state")
                _require_cycle_owned_freeze(cycle, s5)
                inputs = dict(locked_inputs(state_path=s5_path, state=s5))
                policy_id = _provider_id(inputs, remove=False)
                _pending(cycle, phase, {
                    "freeze_state_fingerprint": s5["state_fingerprint"],
                    "request_fingerprint": (inputs.get("request") or {}).get("request_fingerprint"),
                    "decision_provider_id": inputs.get("decision_provider_id"),
                })
                _save_attempt(cycle_path, cycle)
                transition = run_locked_holdout_transition(state_path=s5_path, **inputs)
                locked = transition["result"]
                cycle["locked_ref"] = {
                    "freeze_state_fingerprint": locked["freeze_state_fingerprint"],
                    "result_fingerprint": locked["result_fingerprint"],
                    "outcome_fingerprint": locked["outcome_fingerprint"],
                    "analysis_eval_fingerprint": locked["analysis_eval_fingerprint"],
                    "decision_fingerprint": locked["decision"]["decision_fingerprint"],
                    "current_candidate": locked["current_candidate"],
                    "terminal_status": locked["terminal_status"],
                    "decision_token": locked["decision"].get("decision_token"),
                    "next_action": locked["decision"]["next_action"],
                }
                if (
                    locked["terminal_status"] == "ready"
                    and locked["decision"].get("decision_token") == "PROMOTION_CANDIDATE_IDENTIFIED"
                    and locked["decision"]["next_action"] == "handoff_promotion_controller"
                ):
                    next_phase = "promotion"
                else:
                    next_phase = "held"
                    cycle["status"] = "held"
                    cycle["reason"] = "locked_result_not_promotion_eligible"
                cycle = _commit_phase(cycle_path, cycle, next_phase)
                if next_phase == "held":
                    return cycle
                continue

            if phase == "promotion":
                if cycle["locked_ref"] is None:
                    raise AnalysisQualityClosedCycleError("promotion lacks S6 handoff")
                locked_path = s5_path.with_name(s5_path.name + ".locked-result.json")
                locked = _read_json(locked_path)
                inputs = dict(promotion_inputs(locked_result=locked))
                manifest = inputs.pop("manifest")
                _require_simulation_repository(inputs, manifest)
                _pending(cycle, phase, {"manifest_fingerprint": manifest["manifest_fingerprint"], "locked_result_fingerprint": locked["result_fingerprint"]})
                _save_attempt(cycle_path, cycle)
                promoted = run_promotion(source_state_path=s5_path, manifest=manifest, **inputs)
                cycle["promotion_ref"] = {
                    "manifest_fingerprint": manifest["manifest_fingerprint"],
                    "attempt_fingerprint": promoted["state_fingerprint"],
                    "status": promoted["status"],
                    "pr_number": promoted.get("pr_number"),
                    "head_sha": promoted.get("head_sha"),
                    "merge_sha": promoted.get("merge_sha"),
                    "required_checks": promoted.get("required_checks"),
                    "observed_checks": promoted.get("observed_checks"),
                    "validation_refs": promoted.get("validation_refs"),
                    "changed_paths": promoted.get("changed_paths"),
                }
                if promoted["status"] == "merged" and promoted.get("repository_merge_eligible") is True:
                    next_phase = "post_merge"
                else:
                    next_phase = "failed"
                    cycle["status"] = "failed"
                    cycle["reason"] = "promotion_not_merged_and_verified"
                cycle = _commit_phase(cycle_path, cycle, next_phase)
                if next_phase == "failed":
                    return cycle
                continue

            if phase == "post_merge":
                if cycle["promotion_ref"] is None:
                    raise AnalysisQualityClosedCycleError("post-merge lacks S7 result")
                locked = _read_json(s5_path.with_name(s5_path.name + ".locked-result.json"))
                promotion_args = dict(promotion_inputs(locked_result=locked))
                manifest = promotion_args.pop("manifest")
                _require_simulation_repository(promotion_args, manifest)
                promotion = _replay_committed_promotion(
                    cycle=cycle,
                    locked=locked,
                    state_path=s5_path,
                    manifest=manifest,
                    promotion_args=promotion_args,
                )
                promotion_attempt_path = Path(promotion_args["attempt_root"]) / manifest["manifest_fingerprint"] / "attempt.json"
                post = dict(post_merge_inputs(
                    locked_result=locked,
                    promotion_manifest=manifest,
                    promotion_attempt=promotion,
                ))
                plan = post["plan"]
                _pending(cycle, phase, {"plan_fingerprint": plan["plan_fingerprint"], "merge_sha": promotion.get("merge_sha")})
                _save_attempt(cycle_path, cycle)
                merged = run_post_merge(
                    source_state_path=s5_path,
                    promotion_manifest=manifest,
                    promotion_provider=promotion_args["provider"],
                    promotion_attempt_path=promotion_attempt_path,
                    **post,
                )
                cycle["post_merge_ref"] = {
                    "plan_fingerprint": plan["plan_fingerprint"],
                    "attempt_fingerprint": merged["state_fingerprint"],
                    "status": merged["status"],
                    "merge_sha": merged.get("merge_sha"),
                    "accepted_baseline_fingerprint": merged.get("accepted_baseline_fingerprint"),
                    "last_known_good_fingerprint": merged.get("last_known_good_fingerprint"),
                    "baseline_generation_start": merged.get("baseline_generation_start"),
                    "baseline_verification_refs": merged.get("baseline_verification_refs"),
                    "promoted_verification_refs": merged.get("promoted_verification_refs"),
                    "recovery_verification_refs": merged.get("recovery_verification_refs"),
                }
                if merged["status"] != "accepted":
                    cycle["status"] = "failed"
                    cycle["reason"] = "post_merge_acceptance_not_passed"
                    cycle = _commit_phase(cycle_path, cycle, "failed")
                    return cycle
                cycle = _commit_phase(cycle_path, cycle, "continuation")
                continue

            if phase == "continuation":
                locked = _read_json(s5_path.with_name(s5_path.name + ".locked-result.json"))
                promotion_args = dict(promotion_inputs(locked_result=locked))
                manifest = promotion_args.pop("manifest")
                _require_simulation_repository(promotion_args, manifest)
                promotion = _replay_committed_promotion(
                    cycle=cycle,
                    locked=locked,
                    state_path=s5_path,
                    manifest=manifest,
                    promotion_args=promotion_args,
                )
                promotion_attempt_path = Path(promotion_args["attempt_root"]) / manifest["manifest_fingerprint"] / "attempt.json"
                post = dict(post_merge_inputs(
                    locked_result=locked,
                    promotion_manifest=manifest,
                    promotion_attempt=promotion,
                ))
                plan = post["plan"]
                expected_post = cycle.get("post_merge_ref") or {}
                if plan.get("plan_fingerprint") != expected_post.get("plan_fingerprint"):
                    raise AnalysisQualityClosedCycleError(
                        "S8 plan differs from committed cycle identity"
                    )
                merged = run_post_merge(
                    source_state_path=s5_path,
                    promotion_manifest=manifest,
                    promotion_provider=promotion_args["provider"],
                    promotion_attempt_path=promotion_attempt_path,
                    **post,
                )
                _require_committed_post_merge_replay(cycle, plan, merged)
                baseline_path = Path(post["baseline_state_path"])
                lineage = load_baseline_lineage(baseline_path)
                if (
                    lineage["current"]["baseline_fingerprint"]
                    != expected_post["accepted_baseline_fingerprint"]
                    or lineage["current"]["candidate"]
                    != locked["current_candidate"]
                    or lineage.get("last_known_good") is None
                    or lineage["last_known_good"]["baseline_fingerprint"]
                    != expected_post["last_known_good_fingerprint"]
                ):
                    raise AnalysisQualityClosedCycleError(
                        "accepted baseline lineage differs from committed S8 identity"
                    )
                candidate = lineage["current"]["candidate"]
                initial = load_state(s5_path)
                from src.analysis_quality_loop_supervisor import _default_provider

                provider = _default_provider(lineage["domain"])
                continuation_path = s5_path.with_name(
                    f"{s5_path.stem}.continuation-{lineage['generation']}.json"
                )
                if continuation_path.exists():
                    continuation_state = load_state(continuation_path)
                    if continuation_state["baseline_candidate"] != candidate:
                        raise AnalysisQualityClosedCycleError("continuation baseline mismatch")
                else:
                    continuation_state = fresh_state(
                        domain=lineage["domain"],
                        partition_id=f"{initial['partition']['partition_id']}.continuation.{lineage['generation']}",
                        partition_role="calibration",
                        baseline_candidate=candidate,
                        active_candidate=candidate,
                        last_known_good=(lineage["last_known_good"] or {}).get("candidate"),
                        search_space_id=provider.search_space_id,
                        search_space_version=provider.search_space_version,
                        search_space_fingerprint=provider.search_space_fingerprint(),
                        visited_candidate_ids=[candidate["candidate_id"]],
                        retry_budget=initial["retry"]["budget_initial"],
                        max_iterations=initial.get("max_iterations"),
                    )
                    save_state_atomic(continuation_path, continuation_state)
                pending = cycle.get("pending")
                if pending and pending.get("phase") == phase:
                    identity = pending.get("identity") or {}
                    if identity.get("continuation_state_fingerprint") != continuation_state[
                        "state_fingerprint"
                    ]:
                        if _retry_only_s5_update(identity, continuation_state):
                            cycle["pending"] = None
                            _save_attempt(cycle_path, cycle)
                            continue
                        current_decision = continuation_state.get("last_decision") or {}
                        last_orchestration = _recovered_orchestration_ref(
                            continuation_state, identity, "continuation"
                        )
                        iterator_ref = continuation_state.get("last_iterator_ref") or {}
                        next_candidate = iterator_ref.get("next_candidate")
                        if (
                            current_decision.get("next_action")
                            != "continue_calibration"
                            or iterator_ref.get("iterator_effect") != "advance"
                            or not next_candidate
                        ):
                            cycle["status"] = "held"
                            cycle["reason"] = "continuation_not_ready"
                            return _save_attempt(cycle_path, cycle)
                        cycle["continuation_ref"] = {
                            "baseline_generation": lineage["generation"],
                            "baseline_fingerprint": lineage["current"][
                                "baseline_fingerprint"
                            ],
                            "supervisor_state_fingerprint": continuation_state[
                                "state_fingerprint"
                            ],
                            "next_action": current_decision["next_action"],
                            "candidate": next_candidate,
                            "decision_fingerprint": current_decision[
                                "decision_fingerprint"
                            ],
                            "outcome_fingerprint": last_orchestration.get(
                                "outcome_fingerprint"
                            ),
                            "decision_provider_id": identity["decision_provider_id"],
                        }
                        cycle["candidate_history"] = load_state(s5_path)[
                            "visited_candidate_ids"
                        ]
                        cycle["status"] = "completed"
                        result = _write_result(cycle_path, cycle, lineage)
                        cycle["phase"] = "completed"
                        cycle["pending"] = None
                        _save_attempt(cycle_path, cycle)
                        return result
                inputs = dict(calibration_inputs(state_path=continuation_path, state=continuation_state))
                policy_id = _provider_id(inputs)
                request = inputs.get("request")
                if not isinstance(request, Mapping):
                    raise AnalysisQualityClosedCycleError("continuation input lacks request")
                _pending(cycle, phase, {
                    "baseline_generation": lineage["generation"],
                    "baseline_fingerprint": lineage["current"]["baseline_fingerprint"],
                    "continuation_state_fingerprint": continuation_state["state_fingerprint"],
                    "s5_generation": continuation_state["generation"],
                    "active_candidate": continuation_state["active_candidate"],
                    "visited_candidate_ids": list(continuation_state["visited_candidate_ids"]),
                    "retry": dict(continuation_state["retry"]),
                    "previous_decision_fingerprint": (
                        continuation_state.get("last_decision") or {}
                    ).get("decision_fingerprint"),
                    "decision_provider_id": policy_id,
                    "request_fingerprint": request.get("request_fingerprint"),
                })
                _save_attempt(cycle_path, cycle)
                result = run_supervisor_step(
                    state_path=continuation_path,
                    decision_provider_id=policy_id,
                    **inputs,
                )
                continuation_after = load_state(continuation_path)
                ref = _ref_from_supervisor(
                    result, continuation_after, request.get("request_fingerprint")
                )
                ref["decision_provider_id"] = policy_id
                iterator = result.get("iterator") or {}
                if result["decision"]["next_action"] != "continue_calibration" or not iterator.get("next_candidate"):
                    cycle["status"] = "held"
                    cycle["reason"] = "continuation_not_ready"
                    return _save_attempt(cycle_path, cycle)
                cycle["continuation_ref"] = {
                    "baseline_generation": lineage["generation"],
                    "baseline_fingerprint": lineage["current"]["baseline_fingerprint"],
                    "supervisor_state_fingerprint": continuation_after["state_fingerprint"],
                    "next_action": result["decision"]["next_action"],
                    "candidate": iterator["next_candidate"],
                    "decision_fingerprint": ref["decision_fingerprint"],
                    "outcome_fingerprint": ref["outcome_fingerprint"],
                    "decision_provider_id": policy_id,
                }
                cycle["candidate_history"] = load_state(s5_path)["visited_candidate_ids"]
                result = _write_result(cycle_path, cycle, lineage)
                cycle["status"] = "completed"
                cycle = _commit_phase(cycle_path, cycle, "completed")
                return result

            raise AnalysisQualityClosedCycleError(f"unknown cycle phase: {phase}")

        cycle["status"] = "held"
        cycle["reason"] = "transition_budget_exhausted"
        return _save_attempt(cycle_path, cycle)
