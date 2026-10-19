"""Frozen supervisor → one locked evaluation → terminal #1043 decision (#1170).

Keeps #1097 state immutable. Durable claims fail closed after uncertain dispatch;
portable result references compose the existing orchestration/evidence chain.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Mapping

from src.analysis_automation_decision import build_decision, validate_decision
from src.analysis_candidate_iterator import (
    SearchSpaceProvider,
    search_space_fingerprint,
)
from src.analysis_eval_artifact import (
    assert_portable_value,
    canonical_json_dumps,
    fingerprint,
)
from src.analysis_headless_run import validate_request
from src.analysis_orchestration_run import run_orchestration, validate_outcome
from src.analysis_quality_loop_state import load_state
from src.aq_candidate_search_spaces.aq1_tempo import Aq1TempoSearchSpaceProvider

DOCUMENT_TYPE = "sample-brain.analysis-locked-holdout-result.v1"
ARTIFACT_VERSION = "1.0.0"


class AnalysisLockedHoldoutError(ValueError):
    """Invalid locked transition, corrupt persistence or uncertain prior dispatch."""


def _digest(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise AnalysisLockedHoldoutError(
            "required lowercase sha256 fingerprint missing or invalid"
        )
    return value


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AnalysisLockedHoldoutError("persisted document must be a mapping")
    assert_portable_value(value)
    return value


def _check_frozen(state, request, provider):
    if state["loop_status"] != "frozen":
        raise AnalysisLockedHoldoutError(
            "only frozen supervisor state may enter locked evaluation"
        )
    freeze = state.get("last_decision") or {}
    if (
        freeze.get("next_action") != "freeze_candidate"
        or freeze.get("decision_status") != "ready"
    ):
        raise AnalysisLockedHoldoutError("missing ready freeze provenance")
    _digest(freeze.get("decision_fingerprint"))
    if request["operation"] != "locked_evaluation" or request["partition"][
        "role"
    ] not in {"test", "holdout"}:
        raise AnalysisLockedHoldoutError(
            "locked_evaluation requires locked TEST/HOLDOUT partition"
        )
    for key, expected in (
        ("domain", state["domain"]),
        ("baseline", state["baseline_candidate"]),
        ("current", state["active_candidate"]),
    ):
        if request.get(key) != expected:
            raise AnalysisLockedHoldoutError(f"frozen identity mismatch: {key}")
    if provider is None:
        if state["domain"] != "aq1.tempo":
            raise AnalysisLockedHoldoutError(
                "explicit domain search-space provider required"
            )
        provider = Aq1TempoSearchSpaceProvider()
    members = provider.ordered_members()
    actual_fp = search_space_fingerprint(
        search_space_id=provider.search_space_id,
        search_space_version=provider.search_space_version,
        ordered_members=members,
    )
    if (
        state["search_space_id"] != provider.search_space_id
        or state["search_space_version"] != provider.search_space_version
        or state["search_space_fingerprint"] != actual_fp
        or provider.search_space_fingerprint() != actual_fp
        or state["active_candidate"] not in members
        or state["baseline_candidate"] not in members
    ):
        raise AnalysisLockedHoldoutError(
            "frozen search-space identity/content/order mismatch"
        )


def _check_policy(request, evidence_fp, gate, token, action):
    if action in {"continue_calibration", "freeze_candidate"}:
        raise AnalysisLockedHoldoutError(
            "terminal partition firewall forbids tuning actions"
        )
    if gate not in {None, "PASS", "FAIL", "HOLD"}:
        raise AnalysisLockedHoldoutError("invalid gate verdict")
    if gate in {"PASS", "FAIL"} and (token is None or action is None):
        raise AnalysisLockedHoldoutError(
            "explicit domain policy token and next_action required"
        )
    if gate is None:
        if token is not None or action is not None:
            raise AnalysisLockedHoldoutError(
                "absent gate requires no ready policy inputs"
            )
        return
    build_decision(
        domain=request["domain"],
        **request["benchmark"],
        partition_id=request["partition"]["partition_id"],
        partition_role=request["partition"]["role"],
        baseline_candidate_id=request["baseline"]["candidate_id"],
        baseline_config_fingerprint=request["baseline"]["config_fingerprint"],
        current_candidate_id=request["current"]["candidate_id"],
        current_config_fingerprint=request["current"]["config_fingerprint"],
        analysis_eval_fingerprint="0" * 64,
        evidence_fingerprint=evidence_fp,
        gate_verdict=gate,
        decision_status="hold" if gate == "HOLD" else "ready",
        decision_token=token,
        next_action=action or "defer_for_evidence",
    )
    if token == "PROMOTION_CANDIDATE_IDENTIFIED" and action not in {
        "handoff_promotion_controller",
        "require_human_governance",
    }:
        raise AnalysisLockedHoldoutError(
            "promotion policy requires explicit handoff or governance"
        )


def validate_locked_result(result: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the portable terminal reference artifact, including #1043 decision."""
    expected_keys = {
        "document_type",
        "artifact_version",
        "freeze_state_fingerprint",
        "invocation_fingerprint",
        "domain",
        "baseline_candidate",
        "current_candidate",
        "partition",
        "request_fingerprint",
        "outcome_fingerprint",
        "analysis_eval_fingerprint",
        "decision",
        "terminal_status",
        "production_authorized",
        "result_fingerprint",
    }
    if not isinstance(result, Mapping) or set(result) != expected_keys:
        raise AnalysisLockedHoldoutError("invalid locked result fields")
    if (
        result["document_type"] != DOCUMENT_TYPE
        or result["artifact_version"] != ARTIFACT_VERSION
    ):
        raise AnalysisLockedHoldoutError("unsupported locked result version")
    if result["production_authorized"] is not False:
        raise AnalysisLockedHoldoutError("production_authorized must be false")
    assert_portable_value(dict(result))
    for key in expected_keys:
        if key.endswith("fingerprint"):
            _digest(result[key])
    decision = validate_decision(result["decision"])
    if result["terminal_status"] != decision["decision_status"]:
        raise AnalysisLockedHoldoutError("terminal status differs from decision")
    for key in ("domain", "baseline_candidate", "current_candidate", "partition"):
        if result[key] != decision[key]:
            raise AnalysisLockedHoldoutError(
                f"locked result decision identity mismatch: {key}"
            )
    if decision["partition"]["role"] not in {"test", "holdout"} or decision[
        "next_action"
    ] in {"continue_calibration", "freeze_candidate"}:
        raise AnalysisLockedHoldoutError("locked terminal firewall")
    if (
        result["analysis_eval_fingerprint"]
        != decision["evidence"]["analysis_eval_fingerprint"]
    ):
        raise AnalysisLockedHoldoutError("locked result eval identity mismatch")
    payload = {k: v for k, v in result.items() if k != "result_fingerprint"}
    if fingerprint(payload) != result["result_fingerprint"]:
        raise AnalysisLockedHoldoutError("locked result fingerprint mismatch")
    return json.loads(canonical_json_dumps(dict(result)))


def _check_claim_decision(invocation, decision):
    evidence = decision["evidence"]
    if "decision_provider_id" in invocation:
        _digest(evidence.get("evidence_fingerprint"))
        if evidence.get("gate_decision", {}).get("verdict") not in {
            "PASS", "FAIL", "HOLD"
        }:
            raise AnalysisLockedHoldoutError(
                "committed provider decision has invalid gate evidence"
            )
        return
    if evidence["evidence_fingerprint"] != invocation["evidence_fingerprint"]:
        raise AnalysisLockedHoldoutError("committed evidence differs from invocation")
    status = decision["decision_status"]
    if status == "ready":
        if (
            invocation["gate_verdict"] not in {"PASS", "FAIL"}
            or decision.get("decision_token") != invocation["decision_token"]
            or decision["next_action"] != invocation["next_action"]
            or evidence["gate_decision"]["verdict"] != invocation["gate_verdict"]
        ):
            raise AnalysisLockedHoldoutError("committed policy differs from invocation")
    elif evidence["gate_decision"]["verdict"] != "HOLD":
        raise AnalysisLockedHoldoutError("non-ready invocation requires HOLD evidence")


def _sync_entry(path: Path) -> None:
    """Persist name metadata before dispatch/commit, failing closed on error.

    POSIX requires a separate parent-directory fsync. Windows file flushes also
    flush file metadata (Microsoft File Caching); reopen the destination after
    rename so the metadata barrier covers its final name.
    """
    if os.name == "nt":
        with path.open("r+b") as handle:
            os.fsync(handle.fileno())
    else:
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _write_atomic(path: Path, value):
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical_json_dumps(value) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _sync_entry(path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def run_locked_holdout_transition(
    *,
    state_path: str | Path,
    request: Mapping[str, Any],
    bind_kwargs: Mapping[str, Any],
    evidence_fingerprint: str | None = None,
    gate_verdict: str | None = None,
    decision_token: str | None = None,
    next_action: str | None = None,
    provider: SearchSpaceProvider | None = None,
    decision_provider=None,
    decision_provider_id: str | None = None,
) -> dict[str, Any]:
    """Dispatch at most once; replay an identical durable terminal outcome.

    A durable claim without a result is an uncertain execution, never permission
    to re-evaluate locked evidence. Host input integrity is owned by the adapter.
    """
    path = Path(state_path)
    state = load_state(path)
    validated = validate_request(request)
    _check_frozen(state, validated, provider)
    if decision_provider is None:
        evidence_fp = _digest(evidence_fingerprint)
        _check_policy(validated, evidence_fp, gate_verdict, decision_token, next_action)
        invocation = {
            "freeze_state_fingerprint": state["state_fingerprint"],
            "request_fingerprint": validated["request_fingerprint"],
            "evidence_fingerprint": evidence_fp,
            "gate_verdict": gate_verdict,
            "decision_token": decision_token,
            "next_action": next_action,
        }
    else:
        if not callable(decision_provider):
            raise AnalysisLockedHoldoutError("decision_provider must be callable")
        if not isinstance(decision_provider_id, str) or re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", decision_provider_id
        ) is None:
            raise AnalysisLockedHoldoutError("decision_provider_id is required")
        if any(value is not None for value in (
            evidence_fingerprint, gate_verdict, decision_token, next_action
        )):
            raise AnalysisLockedHoldoutError(
                "decision_provider cannot be combined with precomputed decision inputs"
            )
        invocation = {
            "freeze_state_fingerprint": state["state_fingerprint"],
            "request_fingerprint": validated["request_fingerprint"],
            "decision_provider_id": decision_provider_id,
        }
    invocation_fp = fingerprint(invocation)
    claim_path = path.with_name(path.name + ".locked-claim.json")
    result_path = path.with_name(path.name + ".locked-result.json")
    if result_path.exists():
        result = validate_locked_result(_read(result_path))
        if (
            _read(claim_path) != invocation
            or result["invocation_fingerprint"] != invocation_fp
        ):
            raise AnalysisLockedHoldoutError(
                "committed invocation/freeze identity mismatch"
            )
        if (
            result["freeze_state_fingerprint"] != state["state_fingerprint"]
            or result["request_fingerprint"] != validated["request_fingerprint"]
        ):
            raise AnalysisLockedHoldoutError("committed freeze/request mismatch")
        for key in ("domain", "partition"):
            if result[key] != validated[key]:
                raise AnalysisLockedHoldoutError(
                    "committed invocation identity mismatch"
                )
        if (
            result["current_candidate"] != state["active_candidate"]
            or result["baseline_candidate"] != state["baseline_candidate"]
        ):
            raise AnalysisLockedHoldoutError(
                "committed frozen candidate identity mismatch"
            )
        _check_claim_decision(invocation, result["decision"])
        if result["decision"]["benchmark"] != validated["benchmark"]:
            raise AnalysisLockedHoldoutError(
                "committed benchmark differs from invocation"
            )
        _sync_entry(result_path)
        return {"already_committed": True, "result": result}
    try:
        with claim_path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical_json_dumps(invocation) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise AnalysisLockedHoldoutError(
            "durable claim exists; uncertain execution requires reconciliation"
        ) from exc

    _sync_entry(claim_path)

    outcome = validate_outcome(
        run_orchestration(
            request=validated,
            bind_kwargs=bind_kwargs,
            evidence_fingerprint=evidence_fp if decision_provider is None else None,
            gate_verdict=gate_verdict,
            decision_token=decision_token,
            next_action=next_action,
            decision_provider=decision_provider,
        )
    )
    decision = outcome["decision"]
    if decision["benchmark"] != validated["benchmark"]:
        raise AnalysisLockedHoldoutError("outcome benchmark differs from invocation")
    headless = outcome["headless_result"]
    if (
        headless["request_fingerprint"] != validated["request_fingerprint"]
        or headless["operation"] != "locked_evaluation"
        or headless["adapter_id"] != validated["adapter_id"]
    ):
        raise AnalysisLockedHoldoutError("outcome differs from locked invocation")
    result = {
        "document_type": DOCUMENT_TYPE,
        "artifact_version": ARTIFACT_VERSION,
        "freeze_state_fingerprint": state["state_fingerprint"],
        "invocation_fingerprint": invocation_fp,
        "domain": state["domain"],
        "baseline_candidate": state["baseline_candidate"],
        "current_candidate": state["active_candidate"],
        "partition": validated["partition"],
        "request_fingerprint": validated["request_fingerprint"],
        "outcome_fingerprint": outcome["outcome_fingerprint"],
        "analysis_eval_fingerprint": outcome["analysis_eval"]["artifact_fingerprint"],
        "decision": decision,
        "terminal_status": decision["decision_status"],
        "production_authorized": False,
    }
    result["result_fingerprint"] = fingerprint(result)
    result = validate_locked_result(result)
    _check_claim_decision(invocation, result["decision"])
    if load_state(path) != state:
        raise AnalysisLockedHoldoutError(
            "freeze state changed during locked evaluation"
        )
    _write_atomic(result_path, result)
    return {"already_committed": False, "result": result}
