"""Sample Brain analysis orchestration-run contract v1 (#1060).

Single-shot binder:

    headless request
      → bind_adapter / DomainAdapter.run
      → validate headless result
      → portable analysis-eval.v1 fingerprint (binder-side projection)
      → opaque ARVP evidence_fingerprint + gate_verdict
      → build_decision (#1043)
      → deterministic orchestration outcome

Reuses frozen #956 / #1043 / #1054 contracts. No ``import arvp``.
No second status taxonomy. ``production_authorized`` always false.
"""

from __future__ import annotations

from typing import Any, Mapping

from src.analysis_automation_decision import (
    AnalysisAutomationDecisionError,
    GATE_VERDICTS,
    TUNABLE_PARTITION_ROLES,
    TUNING_NEXT_ACTIONS,
    build_decision,
    validate_decision,
)
from src.analysis_eval_artifact import (
    AnalysisEvalArtifactError,
    assert_portable_value,
    build_artifact,
    build_candidate,
    build_observation,
    build_record,
    fingerprint,
    validate_artifact,
)
from src.analysis_headless_run import (
    AnalysisHeadlessRunError,
    bind_adapter,
    validate_request,
    validate_result,
)

DOCUMENT_TYPE = "sample-brain.analysis-orchestration-run.v1"
ARTIFACT_VERSION = "1.0.0"
PRODUCER_ID = "sample-brain.analysis-orchestration-run"

# analysis-eval.v1 has no holdout role — map locked final check to test.
_EVAL_PARTITION_ROLE_MAP: Mapping[str, str] = {
    "development": "development",
    "calibration": "calibration",
    "validation": "validation",
    "test": "test",
    "external_check": "external_check",
    "holdout": "test",
}

_OUTCOME_FP_EXCLUDED: frozenset[str] = frozenset(
    {"generated_at", "outcome_fingerprint", "artifact_hash"}
)


class AnalysisOrchestrationRunError(ValueError):
    """Raised when an orchestration request/outcome violates the v1 contract."""


def _wrap_eval(exc: AnalysisEvalArtifactError) -> AnalysisOrchestrationRunError:
    return AnalysisOrchestrationRunError(str(exc))


def _wrap_headless(exc: AnalysisHeadlessRunError) -> AnalysisOrchestrationRunError:
    return AnalysisOrchestrationRunError(str(exc))


def _wrap_decision(exc: AnalysisAutomationDecisionError) -> AnalysisOrchestrationRunError:
    return AnalysisOrchestrationRunError(str(exc))


def _require_text(value: object, field: str) -> str:
    if type(value) is not str or not value.strip():
        raise AnalysisOrchestrationRunError(f"{field} must be a non-empty string")
    return value.strip()


def _require_hex_fingerprint(value: object, field: str) -> str:
    text = _require_text(value, field)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise AnalysisOrchestrationRunError(
            f"{field} must be a lowercase sha256 hex digest"
        )
    return text


def map_eval_partition_role(partition_role: str) -> str:
    """Map headless/decision partition roles onto analysis-eval.v1 roles."""
    mapped = _EVAL_PARTITION_ROLE_MAP.get(partition_role)
    if mapped is None:
        raise AnalysisOrchestrationRunError(
            f"unsupported partition role for eval projection: {partition_role!r}"
        )
    return mapped


def project_analysis_eval_from_headless(
    *,
    request: Mapping[str, Any],
    headless_result: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a portable analysis-eval.v1 artifact from headless identities.

    Binder-side projection keeps AQ adapters thin. Host-local paths must never
    enter this envelope — only portable fingerprints and identities.
    """
    try:
        domain = _require_text(headless_result.get("domain"), "domain")
        adapter_id = _require_text(headless_result.get("adapter_id"), "adapter_id")
        adapter_version = _require_text(
            headless_result.get("adapter_version"), "adapter_version"
        )
        run_status = _require_text(headless_result.get("run_status"), "run_status")
        benchmark = headless_result.get("benchmark")
        if not isinstance(benchmark, Mapping):
            raise AnalysisOrchestrationRunError("headless_result.benchmark must be a mapping")
        partition = headless_result.get("partition")
        if not isinstance(partition, Mapping):
            raise AnalysisOrchestrationRunError("headless_result.partition must be a mapping")

        partition_id = _require_text(partition.get("partition_id"), "partition.partition_id")
        partition_role = _require_text(partition.get("role"), "partition.role")
        eval_role = map_eval_partition_role(partition_role)

        baseline = headless_result.get("baseline")
        current = headless_result.get("current")
        if not isinstance(baseline, Mapping):
            baseline = request.get("baseline") if isinstance(request.get("baseline"), Mapping) else {}
        if not isinstance(current, Mapping):
            current = request.get("current") if isinstance(request.get("current"), Mapping) else {}

        candidate_id = _require_text(
            current.get("candidate_id") or baseline.get("candidate_id"),
            "candidate_id",
        )
        config_fingerprint = _require_hex_fingerprint(
            current.get("config_fingerprint")
            or baseline.get("config_fingerprint"),
            "config_fingerprint",
        )

        domain_artifact = headless_result.get("domain_artifact")
        error = headless_result.get("error")
        record_id = "orch.headless.primary"
        if run_status == "completed":
            if not isinstance(domain_artifact, Mapping):
                raise AnalysisOrchestrationRunError(
                    "completed headless result requires domain_artifact for eval projection"
                )
            domain_artifact_id = _require_text(
                domain_artifact.get("artifact_id"), "domain_artifact.artifact_id"
            )
            domain_artifact_fp = _require_hex_fingerprint(
                domain_artifact.get("artifact_fingerprint"),
                "domain_artifact.artifact_fingerprint",
            )
            observations = [
                build_observation(
                    observation_id=f"{record_id}.domain_artifact.link",
                    metric_id="orchestration.domain_artifact.link",
                    status="measured",
                    value=1.0,
                    unit="count",
                    direction="maximize",
                    payload={
                        "domain_artifact_id": domain_artifact_id,
                        "domain_artifact_fingerprint": domain_artifact_fp,
                        "adapter_id": adapter_id,
                        "adapter_version": adapter_version,
                        "headless_run_status": run_status,
                    },
                )
            ]
            eligibility: dict[str, Any] = {"status": "eligible"}
        else:
            if not isinstance(error, Mapping):
                raise AnalysisOrchestrationRunError(
                    f"{run_status} headless result requires error for eval projection"
                )
            error_code = _require_text(error.get("code"), "error.code")
            observations = [
                build_observation(
                    observation_id=f"{record_id}.headless.{run_status}",
                    metric_id="orchestration.headless.status",
                    status="controlled_failure"
                    if run_status == "controlled_failure"
                    else "unknown",
                    unit="status",
                    direction="minimize",
                    failure_code=error_code
                    if run_status == "controlled_failure"
                    else None,
                    payload={
                        "adapter_id": adapter_id,
                        "adapter_version": adapter_version,
                        "headless_run_status": run_status,
                        "error_code": error_code,
                    },
                )
            ]
            eligibility = {"status": "eligible"}

        candidate = build_candidate(
            candidate_id=candidate_id,
            implementation_id=adapter_id,
            revision=adapter_version,
            configuration={
                "domain": domain,
                "candidate_id": candidate_id,
                "config_fingerprint": config_fingerprint,
                "headless_run_status": run_status,
            },
        )
        record = build_record(
            record_id=record_id,
            domain=domain,
            eligibility=eligibility,
            ground_truth={},
            observations=observations,
        )
        artifact = build_artifact(
            benchmark_id=_require_text(benchmark.get("benchmark_id"), "benchmark_id"),
            dataset_id=_require_text(benchmark.get("dataset_id"), "dataset_id"),
            dataset_member_ids=[record_id],
            partition_id=partition_id,
            partition_role=eval_role,
            candidate=candidate,
            source_benchmark_version=ARTIFACT_VERSION,
            run_id=f"orch-{headless_result.get('request_fingerprint', 'unknown')[:16]}",
            records=[record],
            source_origin="orchestration-binder",
        )
        return validate_artifact(artifact)
    except AnalysisEvalArtifactError as exc:
        raise _wrap_eval(exc) from exc


def map_decision_inputs(
    *,
    run_status: str,
    gate_verdict: str | None,
    partition_role: str,
    decision_token: str | None = None,
    next_action: str | None = None,
) -> tuple[str, str | None, str]:
    """Map headless status + opaque gate into #1043 decision fields."""
    if run_status == "hold":
        action = next_action or "defer_for_evidence"
        if action not in {"defer_for_evidence", "require_human_governance"}:
            raise AnalysisOrchestrationRunError(
                "hold mapping requires defer_for_evidence or require_human_governance"
            )
        if decision_token is not None:
            raise AnalysisOrchestrationRunError(
                "hold mapping forbids decision_token"
            )
        return "hold", None, action

    if run_status == "controlled_failure":
        if decision_token is not None:
            raise AnalysisOrchestrationRunError(
                "controlled_failure mapping forbids decision_token"
            )
        action = next_action or "stop_controlled_failure"
        if action != "stop_controlled_failure":
            raise AnalysisOrchestrationRunError(
                "controlled_failure mapping requires stop_controlled_failure"
            )
        return "controlled_failure", None, action

    if run_status != "completed":
        raise AnalysisOrchestrationRunError(f"unsupported run_status: {run_status!r}")

    if gate_verdict is None:
        raise AnalysisOrchestrationRunError(
            "completed headless result requires opaque gate_verdict"
        )
    if gate_verdict not in GATE_VERDICTS:
        raise AnalysisOrchestrationRunError(
            f"gate_verdict must be PASS|FAIL|HOLD, got {gate_verdict!r}"
        )

    if gate_verdict == "HOLD":
        action = next_action or "defer_for_evidence"
        if action not in {"defer_for_evidence", "require_human_governance"}:
            raise AnalysisOrchestrationRunError(
                "gate HOLD mapping requires defer_for_evidence or require_human_governance"
            )
        if decision_token is not None:
            raise AnalysisOrchestrationRunError(
                "gate HOLD mapping forbids decision_token"
            )
        return "hold", None, action

    # PASS / FAIL → ready with existing tokens only
    if gate_verdict == "PASS":
        token = decision_token or "KEEP_CURRENT_BASELINE_PATH"
        action = next_action or "keep_baseline_and_stop"
    else:
        token = decision_token or "NO_JUSTIFIED_CANDIDATE"
        action = next_action or "keep_baseline_and_stop"

    if (
        partition_role not in TUNABLE_PARTITION_ROLES
        and action in TUNING_NEXT_ACTIONS
    ):
        raise AnalysisOrchestrationRunError(
            f"partition firewall: illegal next_action {action!r} "
            f"for non-tuning role {partition_role!r}"
        )
    return "ready", token, action


def _assert_eval_matches_headless(
    eval_artifact: Mapping[str, Any],
    headless_result: Mapping[str, Any],
) -> None:
    """Reject host-supplied eval artifacts that describe a different experiment."""
    benchmark = headless_result.get("benchmark")
    partition = headless_result.get("partition")
    if not isinstance(benchmark, Mapping) or not isinstance(partition, Mapping):
        raise AnalysisOrchestrationRunError(
            "headless_result missing benchmark/partition for eval identity check"
        )
    eval_benchmark = eval_artifact.get("benchmark")
    eval_partition = eval_artifact.get("partition")
    eval_candidate = eval_artifact.get("candidate")
    if not isinstance(eval_benchmark, Mapping) or not isinstance(eval_partition, Mapping):
        raise AnalysisOrchestrationRunError(
            "analysis_eval artifact missing benchmark/partition"
        )
    if not isinstance(eval_candidate, Mapping):
        raise AnalysisOrchestrationRunError(
            "analysis_eval artifact missing candidate"
        )

    expected_role = map_eval_partition_role(str(partition.get("role")))
    checks = (
        (
            eval_benchmark.get("benchmark_id") == benchmark.get("benchmark_id"),
            "benchmark_id",
        ),
        (
            eval_benchmark.get("dataset_id") == benchmark.get("dataset_id"),
            "dataset_id",
        ),
        (
            eval_partition.get("partition_id") == partition.get("partition_id"),
            "partition_id",
        ),
        (eval_partition.get("role") == expected_role, "partition.role"),
    )
    for ok, field in checks:
        if not ok:
            raise AnalysisOrchestrationRunError(
                f"analysis_eval artifact identity mismatch on {field}"
            )

    # Domain: first eligible record or any record domain must match headless domain.
    domain = str(headless_result.get("domain"))
    records = eval_artifact.get("records")
    if not isinstance(records, list) or not records:
        raise AnalysisOrchestrationRunError(
            "analysis_eval artifact must include records"
        )
    record_domains = {
        str(item.get("domain"))
        for item in records
        if isinstance(item, Mapping) and item.get("domain") is not None
    }
    if domain not in record_domains:
        raise AnalysisOrchestrationRunError(
            "analysis_eval artifact domain does not match headless_result.domain"
        )

    baseline = headless_result.get("baseline")
    current = headless_result.get("current")
    allowed_candidates: set[str] = set()
    if isinstance(baseline, Mapping) and baseline.get("candidate_id"):
        allowed_candidates.add(str(baseline["candidate_id"]))
    if isinstance(current, Mapping) and current.get("candidate_id"):
        allowed_candidates.add(str(current["candidate_id"]))
    cand_id = str(eval_candidate.get("candidate_id") or "")
    if allowed_candidates and cand_id not in allowed_candidates:
        raise AnalysisOrchestrationRunError(
            "analysis_eval artifact candidate_id does not match headless candidates"
        )


def _assert_decision_matches_headless(
    decision: Mapping[str, Any],
    headless_result: Mapping[str, Any],
) -> None:
    """Ensure decision identities are bound to the embedded headless result."""
    benchmark = headless_result.get("benchmark")
    partition = headless_result.get("partition")
    if not isinstance(benchmark, Mapping) or not isinstance(partition, Mapping):
        raise AnalysisOrchestrationRunError(
            "headless_result missing benchmark/partition for decision identity check"
        )
    dec_benchmark = decision.get("benchmark")
    dec_partition = decision.get("partition")
    if not isinstance(dec_benchmark, Mapping) or not isinstance(dec_partition, Mapping):
        raise AnalysisOrchestrationRunError("decision missing benchmark/partition")

    pairs = (
        (decision.get("domain"), headless_result.get("domain"), "domain"),
        (
            dec_benchmark.get("benchmark_id"),
            benchmark.get("benchmark_id"),
            "benchmark_id",
        ),
        (
            dec_benchmark.get("dataset_id"),
            benchmark.get("dataset_id"),
            "dataset_id",
        ),
        (
            dec_benchmark.get("dataset_content_fingerprint"),
            benchmark.get("dataset_content_fingerprint"),
            "dataset_content_fingerprint",
        ),
        (
            dec_partition.get("partition_id"),
            partition.get("partition_id"),
            "partition_id",
        ),
        (dec_partition.get("role"), partition.get("role"), "partition.role"),
    )
    for left, right, field in pairs:
        if left != right:
            raise AnalysisOrchestrationRunError(
                f"decision identity mismatch on {field}"
            )

    baseline = headless_result.get("baseline")
    current = headless_result.get("current")
    dec_baseline = decision.get("baseline_candidate")
    dec_current = decision.get("current_candidate")
    if isinstance(baseline, Mapping) and isinstance(dec_baseline, Mapping):
        if (
            dec_baseline.get("candidate_id") != baseline.get("candidate_id")
            or dec_baseline.get("config_fingerprint")
            != baseline.get("config_fingerprint")
        ):
            raise AnalysisOrchestrationRunError(
                "decision identity mismatch on baseline_candidate"
            )
    if isinstance(current, Mapping) and isinstance(dec_current, Mapping):
        if (
            dec_current.get("candidate_id") != current.get("candidate_id")
            or dec_current.get("config_fingerprint")
            != current.get("config_fingerprint")
        ):
            raise AnalysisOrchestrationRunError(
                "decision identity mismatch on current_candidate"
            )


def outcome_semantic_payload(outcome: Mapping[str, Any]) -> dict[str, Any]:
    """Return the portable payload used for outcome fingerprinting."""
    return {
        key: value
        for key, value in outcome.items()
        if key not in _OUTCOME_FP_EXCLUDED
    }


def outcome_semantic_fingerprint(outcome: Mapping[str, Any]) -> str:
    """Deterministic fingerprint of the portable orchestration outcome."""
    try:
        return fingerprint(outcome_semantic_payload(outcome))
    except AnalysisEvalArtifactError as exc:
        raise _wrap_eval(exc) from exc


def validate_outcome(outcome: Mapping[str, Any]) -> dict[str, Any]:
    """Validate orchestration outcome invariants; return a plain dict copy."""
    if not isinstance(outcome, Mapping):
        raise AnalysisOrchestrationRunError("outcome must be a mapping")
    if outcome.get("document_type") != DOCUMENT_TYPE:
        raise AnalysisOrchestrationRunError(
            f"document_type must be {DOCUMENT_TYPE!r}"
        )
    if outcome.get("artifact_version") != ARTIFACT_VERSION:
        raise AnalysisOrchestrationRunError(
            f"artifact_version must be {ARTIFACT_VERSION!r}"
        )
    if outcome.get("production_authorized") is not False:
        raise AnalysisOrchestrationRunError(
            "production_authorized must be false"
        )
    if "decision_token" in outcome or "next_action" in outcome:
        raise AnalysisOrchestrationRunError(
            "orchestration outcome must not hoist decision_token/next_action "
            "(they live under decision)"
        )

    try:
        headless_result = validate_result(outcome["headless_result"])
    except (AnalysisHeadlessRunError, KeyError) as exc:
        raise AnalysisOrchestrationRunError(
            f"outcome.headless_result invalid: {exc}"
        ) from exc

    analysis_eval = outcome.get("analysis_eval")
    if not isinstance(analysis_eval, Mapping):
        raise AnalysisOrchestrationRunError("analysis_eval must be a mapping")
    if analysis_eval.get("document_type") != "sample-brain.analysis-eval.v1":
        raise AnalysisOrchestrationRunError(
            "analysis_eval.document_type must be sample-brain.analysis-eval.v1"
        )
    _require_hex_fingerprint(
        analysis_eval.get("artifact_fingerprint"),
        "analysis_eval.artifact_fingerprint",
    )

    try:
        decision = validate_decision(outcome["decision"])
    except (AnalysisAutomationDecisionError, KeyError) as exc:
        raise AnalysisOrchestrationRunError(
            f"outcome.decision invalid: {exc}"
        ) from exc

    if decision["evidence"]["analysis_eval_fingerprint"] != analysis_eval[
        "artifact_fingerprint"
    ]:
        raise AnalysisOrchestrationRunError(
            "decision.evidence.analysis_eval_fingerprint must match "
            "analysis_eval.artifact_fingerprint"
        )

    _assert_decision_matches_headless(decision, headless_result)

    expected_fp = outcome_semantic_fingerprint(
        {
            **dict(outcome),
            "headless_result": headless_result,
            "decision": decision,
        }
    )
    actual_fp = outcome.get("outcome_fingerprint")
    if actual_fp != expected_fp:
        raise AnalysisOrchestrationRunError(
            "outcome_fingerprint does not match semantic payload"
        )

    try:
        assert_portable_value(outcome, field="outcome")
    except AnalysisEvalArtifactError as exc:
        raise _wrap_eval(exc) from exc

    return {
        **dict(outcome),
        "headless_result": headless_result,
        "decision": decision,
    }


def run_orchestration(
    *,
    request: Mapping[str, Any],
    bind_kwargs: Mapping[str, Any],
    evidence_fingerprint: str,
    gate_verdict: str | None = None,
    decision_token: str | None = None,
    next_action: str | None = None,
    analysis_eval_artifact: Mapping[str, Any] | None = None,
    adapter_id: str | None = None,
) -> dict[str, Any]:
    """Execute the single-shot headless → eval → decision binder.

    ``evidence_fingerprint`` and ``gate_verdict`` are opaque ARVP handoff inputs
    supplied by the host. Sample Brain does not recompute gate semantics.
    """
    try:
        validated_request = validate_request(request)
    except AnalysisHeadlessRunError as exc:
        raise _wrap_headless(exc) from exc

    resolved_adapter_id = _require_text(
        adapter_id or validated_request.get("adapter_id"), "adapter_id"
    )
    if validated_request.get("adapter_id") != resolved_adapter_id:
        raise AnalysisOrchestrationRunError(
            "adapter_id mismatch between request and orchestration override"
        )

    evidence_fp = _require_hex_fingerprint(
        evidence_fingerprint, "evidence_fingerprint"
    )

    if not isinstance(bind_kwargs, Mapping):
        raise AnalysisOrchestrationRunError("bind_kwargs must be a mapping")

    try:
        adapter = bind_adapter(resolved_adapter_id, **dict(bind_kwargs))
    except AnalysisHeadlessRunError as exc:
        raise _wrap_headless(exc) from exc

    try:
        raw_result = adapter.run(validated_request)
        headless_result = validate_result(raw_result)
    except AnalysisHeadlessRunError as exc:
        raise _wrap_headless(exc) from exc

    run_status = str(headless_result["run_status"])
    partition_role = str(headless_result["partition"]["role"])

    # Portable eval: prefer host-supplied artifact; else binder projection.
    if analysis_eval_artifact is not None:
        try:
            eval_artifact = validate_artifact(analysis_eval_artifact)
        except AnalysisEvalArtifactError as exc:
            raise _wrap_eval(exc) from exc
        _assert_eval_matches_headless(eval_artifact, headless_result)
    else:
        eval_artifact = project_analysis_eval_from_headless(
            request=validated_request,
            headless_result=headless_result,
        )

    try:
        analysis_eval_fp = fingerprint(eval_artifact)
    except AnalysisEvalArtifactError as exc:
        raise _wrap_eval(exc) from exc

    # Completed without a usable eval fingerprint is fail-closed (unreachable if
    # projection succeeded, but keep the invariant explicit for host-supplied arts).
    if run_status == "completed" and not analysis_eval_fp:
        raise AnalysisOrchestrationRunError(
            "completed headless result requires portable analysis-eval evidence"
        )

    decision_status, mapped_token, mapped_action = map_decision_inputs(
        run_status=run_status,
        gate_verdict=gate_verdict,
        partition_role=partition_role,
        decision_token=decision_token,
        next_action=next_action,
    )

    # Non-completed runs ignore caller gate verdicts; force opaque HOLD stand-in.
    if run_status != "completed":
        effective_gate = "HOLD"
    else:
        effective_gate = gate_verdict
    if effective_gate not in GATE_VERDICTS:
        raise AnalysisOrchestrationRunError(
            f"gate_verdict must be PASS|FAIL|HOLD, got {effective_gate!r}"
        )

    baseline = headless_result.get("baseline")
    current = headless_result.get("current")
    if not isinstance(baseline, Mapping):
        baseline = validated_request.get("baseline")
    if not isinstance(current, Mapping):
        current = validated_request.get("current")
    if not isinstance(baseline, Mapping) or not isinstance(current, Mapping):
        # hold/CF may omit current; fall back to request identities.
        req_baseline = validated_request.get("baseline")
        req_current = validated_request.get("current")
        if not isinstance(baseline, Mapping):
            if not isinstance(req_baseline, Mapping):
                raise AnalysisOrchestrationRunError(
                    "baseline candidate identity required for decision"
                )
            baseline = req_baseline
        if not isinstance(current, Mapping):
            if isinstance(req_current, Mapping):
                current = req_current
            else:
                current = baseline

    try:
        decision = build_decision(
            domain=str(headless_result["domain"]),
            benchmark_id=str(headless_result["benchmark"]["benchmark_id"]),
            dataset_id=str(headless_result["benchmark"]["dataset_id"]),
            dataset_content_fingerprint=str(
                headless_result["benchmark"]["dataset_content_fingerprint"]
            ),
            partition_id=str(headless_result["partition"]["partition_id"]),
            partition_role=partition_role,
            baseline_candidate_id=str(baseline["candidate_id"]),
            baseline_config_fingerprint=str(baseline["config_fingerprint"]),
            current_candidate_id=str(current["candidate_id"]),
            current_config_fingerprint=str(current["config_fingerprint"]),
            analysis_eval_fingerprint=analysis_eval_fp,
            evidence_fingerprint=evidence_fp,
            gate_verdict=str(effective_gate),
            decision_status=decision_status,
            next_action=mapped_action,
            decision_token=mapped_token,
            production_authorized=False,
        )
    except AnalysisAutomationDecisionError as exc:
        raise _wrap_decision(exc) from exc

    outcome: dict[str, Any] = {
        "document_type": DOCUMENT_TYPE,
        "artifact_version": ARTIFACT_VERSION,
        "producer_id": PRODUCER_ID,
        "adapter_id": resolved_adapter_id,
        "headless_result": headless_result,
        "analysis_eval": {
            "document_type": "sample-brain.analysis-eval.v1",
            "artifact_fingerprint": analysis_eval_fp,
        },
        "decision": decision,
        "production_authorized": False,
    }
    try:
        assert_portable_value(outcome, field="outcome")
    except AnalysisEvalArtifactError as exc:
        raise _wrap_eval(exc) from exc
    outcome["outcome_fingerprint"] = outcome_semantic_fingerprint(outcome)
    return validate_outcome(outcome)
