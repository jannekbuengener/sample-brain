"""Sample Brain analysis locked TEST/HOLDOUT transition + final decision v1 (#1170).

One-shot composition, entered only from a persisted supervisor state with
``loop_status="frozen"``:

    frozen candidate/config identity check
      → validate #1054 locked headless request (operation=locked_evaluation,
        partition role test|holdout)
      → run_orchestration (#1060, unchanged)
      → existing #1043 final machine-readable decision (unchanged vocabulary)
      → portable locked-evaluation ref inside supervisor state
      → atomic save (commit boundary)

TEST/HOLDOUT evidence is terminal for the iteration: it can never feed
``continue_calibration`` or ``freeze_candidate`` again. ``loop_status`` stays
``frozen`` so #1097 CALIBRATION refusal is never weakened. No PR, no merge,
no production mutation; ``production_authorized`` remains false everywhere.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from src.analysis_automation_decision import TUNING_NEXT_ACTIONS
from src.analysis_eval_artifact import (
    AnalysisEvalArtifactError,
    assert_portable_value,
    fingerprint,
)
from src.analysis_headless_run import AnalysisHeadlessRunError, validate_request
from src.analysis_orchestration_run import (
    AnalysisOrchestrationRunError,
    run_orchestration,
)
from src.analysis_quality_loop_state import (
    AnalysisQualityLoopStateError,
    load_state,
    save_state_atomic,
    validate_locked_evaluation_ref,
)

DOCUMENT_TYPE = "sample-brain.analysis-locked-holdout-transition.v1"
ARTIFACT_VERSION = "1.0.0"
PRODUCER_ID = "sample-brain.analysis-locked-holdout-transition"

LOCKED_OPERATION = "locked_evaluation"
LOCKED_PARTITION_ROLES = frozenset({"test", "holdout"})

_DECISION_STATUS_TO_TERMINAL: Mapping[str, str] = {
    "ready": "completed",
    "hold": "held",
    "controlled_failure": "controlled_failure",
}

_RESULT_FP_EXCLUDED: frozenset[str] = frozenset(
    {"generated_at", "result_fingerprint", "artifact_hash"}
)


class AnalysisLockedHoldoutError(ValueError):
    """Raised when a locked TEST/HOLDOUT transition violates the v1 contract."""


def _wrap_portable(exc: AnalysisEvalArtifactError) -> AnalysisLockedHoldoutError:
    return AnalysisLockedHoldoutError(str(exc))


def _require_hex_fingerprint(value: object, field: str) -> str:
    if type(value) is not str or not value.strip():
        raise AnalysisLockedHoldoutError(f"{field} must be a non-empty string")
    text = value.strip().lower()
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise AnalysisLockedHoldoutError(
            f"{field} must be a lowercase sha256 hex digest"
        )
    return text


def build_locked_evaluation_ref(
    *,
    outcome: Mapping[str, Any],
    frozen_candidate: Mapping[str, Any],
    baseline_candidate: Mapping[str, Any],
    evidence_fingerprint: str,
) -> dict[str, Any]:
    """Bind a validated orchestration outcome into the portable locked ref."""
    headless_result = outcome["headless_result"]
    decision = outcome["decision"]

    if decision["next_action"] in TUNING_NEXT_ACTIONS:
        raise AnalysisLockedHoldoutError(
            "locked TEST/HOLDOUT evidence cannot emit tuning next_action "
            f"{decision['next_action']!r}"
        )

    locked_current = {
        "candidate_id": str(headless_result["current"]["candidate_id"]),
        "config_fingerprint": str(headless_result["current"]["config_fingerprint"]),
    }
    if locked_current != dict(frozen_candidate):
        raise AnalysisLockedHoldoutError(
            "locked outcome current candidate does not match frozen "
            "active_candidate; no candidate substitution after freeze"
        )
    locked_baseline = {
        "candidate_id": str(headless_result["baseline"]["candidate_id"]),
        "config_fingerprint": str(headless_result["baseline"]["config_fingerprint"]),
    }
    if locked_baseline != dict(baseline_candidate):
        raise AnalysisLockedHoldoutError(
            "locked outcome baseline does not match frozen baseline_candidate"
        )

    partition = headless_result["partition"]
    role = str(partition["role"])
    if role not in LOCKED_PARTITION_ROLES:
        raise AnalysisLockedHoldoutError(
            f"locked outcome partition role must be test or holdout, got {role!r}"
        )

    terminal_status = _DECISION_STATUS_TO_TERMINAL.get(
        str(decision["decision_status"])
    )
    if terminal_status is None:
        raise AnalysisLockedHoldoutError(
            f"unsupported decision_status for locked outcome: "
            f"{decision['decision_status']!r}"
        )

    ref: dict[str, Any] = {
        "candidate": dict(locked_current),
        "baseline_candidate": dict(locked_baseline),
        "partition": {
            "partition_id": str(partition["partition_id"]),
            "role": role,
        },
        "request_fingerprint": str(headless_result["request_fingerprint"]),
        "outcome_fingerprint": str(outcome["outcome_fingerprint"]),
        "analysis_eval_fingerprint": str(outcome["analysis_eval"]["artifact_fingerprint"]),
        "evidence_fingerprint": _require_hex_fingerprint(
            evidence_fingerprint, "evidence_fingerprint"
        ),
        "gate_verdict": str(decision["evidence"]["gate_decision"]["verdict"]),
        "decision": {
            "decision_status": str(decision["decision_status"]),
            "next_action": str(decision["next_action"]),
            "decision_fingerprint": str(decision["decision_fingerprint"]),
        },
        "terminal_status": terminal_status,
        "production_authorized": False,
    }
    token = decision.get("decision_token")
    if token is not None:
        ref["decision"]["decision_token"] = str(token)
    try:
        return validate_locked_evaluation_ref(ref)
    except AnalysisQualityLoopStateError as exc:
        raise AnalysisLockedHoldoutError(str(exc)) from exc


def _assert_replay_identity(
    committed: Mapping[str, Any],
    validated_request: Mapping[str, Any],
    *,
    evidence_fingerprint: str,
    gate_verdict: str | None,
    decision_token: str | None,
    next_action: str | None,
) -> None:
    """Fail closed unless replay inputs match the already-committed claim."""
    if committed["request_fingerprint"] != validated_request.get(
        "request_fingerprint"
    ):
        raise AnalysisLockedHoldoutError(
            "locked evaluation already committed with a different request; "
            "post-freeze identity change refused"
        )
    if committed["evidence_fingerprint"] != evidence_fingerprint:
        raise AnalysisLockedHoldoutError(
            "locked evaluation already committed with a different evidence "
            "claim; post-freeze identity change refused"
        )
    if gate_verdict is not None and committed["gate_verdict"] != gate_verdict:
        raise AnalysisLockedHoldoutError(
            "locked evaluation already committed with a different gate "
            "verdict; post-freeze identity change refused"
        )
    if decision_token is not None and committed["decision"].get(
        "decision_token"
    ) != decision_token:
        raise AnalysisLockedHoldoutError(
            "locked evaluation already committed with a different decision "
            "token; post-freeze identity change refused"
        )
    if next_action is not None and committed["decision"]["next_action"] != next_action:
        raise AnalysisLockedHoldoutError(
            "locked evaluation already committed with a different next_action; "
            "post-freeze identity change refused"
        )


def _result(
    *,
    state: Mapping[str, Any],
    locked: Mapping[str, Any],
    already_committed: bool,
) -> dict[str, Any]:
    decision_ref = dict(locked["decision"])
    decision_ref["production_authorized"] = False
    result: dict[str, Any] = {
        "document_type": DOCUMENT_TYPE,
        "artifact_version": ARTIFACT_VERSION,
        "producer_id": PRODUCER_ID,
        "production_authorized": False,
        "already_committed": already_committed,
        "locked_evaluation": dict(locked),
        "decision": decision_ref,
        "state": dict(state),
    }
    try:
        assert_portable_value(result, field="locked_holdout_result")
        result["result_fingerprint"] = fingerprint(
            {
                key: value
                for key, value in result.items()
                if key not in _RESULT_FP_EXCLUDED
            }
        )
    except AnalysisEvalArtifactError as exc:
        raise _wrap_portable(exc) from exc
    return result


def run_locked_holdout_transition(
    *,
    state_path: str | Path,
    request: Mapping[str, Any],
    bind_kwargs: Mapping[str, Any] | None = None,
    evidence_fingerprint: str,
    gate_verdict: str | None = None,
    decision_token: str | None = None,
    next_action: str | None = None,
) -> dict[str, Any]:
    """Execute the one-shot locked TEST/HOLDOUT transition and commit atomically."""
    path = Path(state_path)
    try:
        state = load_state(path)
    except AnalysisQualityLoopStateError as exc:
        raise AnalysisLockedHoldoutError(
            f"failed to load supervisor state: {exc}"
        ) from exc

    loop_status = state["loop_status"]
    if loop_status != "frozen":
        raise AnalysisLockedHoldoutError(
            f"locked TEST/HOLDOUT transition requires loop_status=frozen; "
            f"got {loop_status!r}"
        )

    evidence_fp = _require_hex_fingerprint(
        evidence_fingerprint, "evidence_fingerprint"
    )
    bind = {} if bind_kwargs is None else dict(bind_kwargs)
    if not isinstance(bind, Mapping):
        raise AnalysisLockedHoldoutError("bind_kwargs must be a mapping")

    try:
        validated_request = validate_request(request)
    except AnalysisHeadlessRunError as exc:
        raise AnalysisLockedHoldoutError(str(exc)) from exc

    committed = state.get("locked_evaluation")
    if committed is not None:
        committed_ref = validate_locked_evaluation_ref(committed)
        _assert_replay_identity(
            committed_ref,
            validated_request,
            evidence_fingerprint=evidence_fp,
            gate_verdict=gate_verdict,
            decision_token=decision_token,
            next_action=next_action,
        )
        return _result(
            state=state, locked=committed_ref, already_committed=True
        )

    operation = str(validated_request["operation"])
    if operation != LOCKED_OPERATION:
        raise AnalysisLockedHoldoutError(
            f"locked transition requires operation={LOCKED_OPERATION!r}; "
            f"got {operation!r}"
        )
    role = str(validated_request["partition"]["role"])
    if role not in LOCKED_PARTITION_ROLES:
        raise AnalysisLockedHoldoutError(
            f"locked transition requires partition role test|holdout; got {role!r}"
        )
    if str(validated_request["domain"]) != str(state["domain"]):
        raise AnalysisLockedHoldoutError(
            "request domain does not match frozen supervisor domain"
        )
    current = validated_request.get("current") or {}
    if dict(current) != dict(state["active_candidate"]):
        raise AnalysisLockedHoldoutError(
            "request current candidate does not match frozen active_candidate; "
            "no candidate substitution after freeze"
        )
    baseline = validated_request.get("baseline") or {}
    if dict(baseline) != dict(state["baseline_candidate"]):
        raise AnalysisLockedHoldoutError(
            "request baseline candidate does not match frozen baseline_candidate"
        )

    try:
        outcome = run_orchestration(
            request=validated_request,
            bind_kwargs=bind,
            evidence_fingerprint=evidence_fp,
            gate_verdict=gate_verdict,
            decision_token=decision_token,
            next_action=next_action,
        )
    except (AnalysisOrchestrationRunError, AnalysisHeadlessRunError) as exc:
        raise AnalysisLockedHoldoutError(
            f"locked orchestration failed: {exc}"
        ) from exc

    locked = build_locked_evaluation_ref(
        outcome=outcome,
        frozen_candidate=state["active_candidate"],
        baseline_candidate=state["baseline_candidate"],
        evidence_fingerprint=evidence_fp,
    )

    history = list(state.get("history_refs") or [])
    history.append(locked["outcome_fingerprint"])
    history.append(locked["decision"]["decision_fingerprint"])

    next_state: dict[str, Any] = dict(state)
    next_state["locked_evaluation"] = locked
    next_state["generation"] = int(state["generation"]) + 1
    next_state["history_refs"] = history
    next_state.pop("state_fingerprint", None)
    # loop_status intentionally stays "frozen": CALIBRATION stays refused (#1097).

    try:
        committed_state = save_state_atomic(path, next_state)
    except AnalysisQualityLoopStateError as exc:
        raise AnalysisLockedHoldoutError(
            f"locked-outcome persist failed: {exc}"
        ) from exc
    except OSError as exc:
        raise AnalysisLockedHoldoutError(
            f"atomic locked-outcome write failed: {exc}"
        ) from exc

    return _result(
        state=committed_state, locked=locked, already_committed=False
    )


__all__ = [
    "ARTIFACT_VERSION",
    "DOCUMENT_TYPE",
    "LOCKED_OPERATION",
    "LOCKED_PARTITION_ROLES",
    "PRODUCER_ID",
    "AnalysisLockedHoldoutError",
    "build_locked_evaluation_ref",
    "run_locked_holdout_transition",
]
