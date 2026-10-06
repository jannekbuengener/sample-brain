"""Sample Brain analysis automation decision v1 (#1043).

Machine-readable decision / orchestration handoff after portable evidence.
Reuses #956 canonicalization / fingerprint / portability helpers.
No runtime ``import arvp``.
"""

from __future__ import annotations

import json
from typing import Any, Literal, Mapping

from src.analysis_eval_artifact import (
    AnalysisEvalArtifactError,
    assert_portable_value,
    canonical_json_dumps,
    fingerprint,
)

DOCUMENT_TYPE = "sample-brain.analysis-automation-decision.v1"
ARTIFACT_VERSION = "1.0.0"
PRODUCER_ID = "sample-brain.analysis-automation-decision"

EVIDENCE_CONTRACT_VERSION = "arvp.evidence.v1"
GATE_DECISION_CONTRACT_VERSION = "arvp.gate-decision.v1"

DecisionStatus = Literal["ready", "hold", "controlled_failure"]
ReadyDecisionToken = Literal[
    "KEEP_CURRENT_BASELINE_PATH",
    "PROMOTION_CANDIDATE_IDENTIFIED",
    "DEFER_INSUFFICIENT_EVIDENCE",
    "NO_JUSTIFIED_CANDIDATE",
]
NextAction = Literal[
    "continue_calibration",
    "freeze_candidate",
    "keep_baseline_and_stop",
    "defer_for_evidence",
    "require_human_governance",
    "stop_controlled_failure",
]
GateVerdict = Literal["PASS", "FAIL", "HOLD"]

DECISION_STATUSES: frozenset[str] = frozenset(
    {"ready", "hold", "controlled_failure"}
)
READY_DECISION_TOKENS: frozenset[str] = frozenset(
    {
        "KEEP_CURRENT_BASELINE_PATH",
        "PROMOTION_CANDIDATE_IDENTIFIED",
        "DEFER_INSUFFICIENT_EVIDENCE",
        "NO_JUSTIFIED_CANDIDATE",
    }
)
NEXT_ACTIONS: frozenset[str] = frozenset(
    {
        "continue_calibration",
        "freeze_candidate",
        "keep_baseline_and_stop",
        "defer_for_evidence",
        "require_human_governance",
        "stop_controlled_failure",
    }
)
GATE_VERDICTS: frozenset[str] = frozenset({"PASS", "FAIL", "HOLD"})
DEPRECATED_READY_ALIASES: frozenset[str] = frozenset(
    {
        "DEFER_PROMOTION",
        "NEED_MORE_EVIDENCE",
        "NEED_FURTHER_CANDIDATES",
    }
)

# analysis-eval roles + decision-envelope holdout alias for locked final check.
DECISION_PARTITION_ROLES: frozenset[str] = frozenset(
    {
        "development",
        "calibration",
        "validation",
        "test",
        "external_check",
        "holdout",
    }
)
TUNABLE_PARTITION_ROLES: frozenset[str] = frozenset({"development", "calibration"})
TUNING_NEXT_ACTIONS: frozenset[str] = frozenset(
    {"continue_calibration", "freeze_candidate"}
)

_FINGERPRINT_EXCLUDED_KEYS = frozenset(
    {"generated_at", "decision_fingerprint", "artifact_hash"}
)


class AnalysisAutomationDecisionError(ValueError):
    """Raised when an automation decision violates the v1 contract."""


def _wrap_portable(exc: AnalysisEvalArtifactError) -> AnalysisAutomationDecisionError:
    return AnalysisAutomationDecisionError(str(exc))


def _require_text(value: object, field: str) -> str:
    if type(value) is not str or not value.strip():
        raise AnalysisAutomationDecisionError(f"{field} must be a non-empty string")
    return value.strip()


def _require_hex_fingerprint(value: object, field: str) -> str:
    text = _require_text(value, field)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text.lower()):
        raise AnalysisAutomationDecisionError(
            f"{field} must be a 64-char sha256 hex digest"
        )
    return text.lower()


def semantic_payload(decision: Mapping[str, Any]) -> dict[str, Any]:
    """Return the fingerprint body excluding volatile / self-hash fields."""
    return {
        key: value
        for key, value in decision.items()
        if key not in _FINGERPRINT_EXCLUDED_KEYS
    }


def decision_semantic_fingerprint(decision: Mapping[str, Any]) -> str:
    """SHA-256 of canonical JSON over semantic fields only."""
    try:
        return fingerprint(semantic_payload(decision))
    except AnalysisEvalArtifactError as exc:
        raise _wrap_portable(exc) from exc


def _assert_partition_firewall(*, role: str, next_action: str) -> None:
    if role not in DECISION_PARTITION_ROLES:
        raise AnalysisAutomationDecisionError(f"unsupported partition role: {role}")
    if role not in TUNABLE_PARTITION_ROLES and next_action in TUNING_NEXT_ACTIONS:
        raise AnalysisAutomationDecisionError(
            f"partition firewall: illegal next_action {next_action!r} "
            f"for non-tuning role {role!r}"
        )


def _assert_status_token_rules(
    *,
    decision_status: str,
    decision_token: str | None,
    next_action: str,
) -> None:
    if decision_status not in DECISION_STATUSES:
        raise AnalysisAutomationDecisionError(
            f"unsupported decision_status: {decision_status}"
        )
    if next_action not in NEXT_ACTIONS:
        raise AnalysisAutomationDecisionError(f"unsupported next_action: {next_action}")

    if decision_status == "ready":
        if decision_token is None:
            raise AnalysisAutomationDecisionError(
                "ready status requires a V1 decision_token"
            )
        if decision_token in DEPRECATED_READY_ALIASES:
            raise AnalysisAutomationDecisionError(
                f"deprecated decision_token alias is unsupported: {decision_token}"
            )
        if decision_token not in READY_DECISION_TOKENS:
            raise AnalysisAutomationDecisionError(
                f"unsupported decision_token: {decision_token}"
            )
        return

    # hold / controlled_failure: no ready token; fixed next-action families
    if decision_token is not None:
        raise AnalysisAutomationDecisionError(
            "decision_token orthogonality: ready token forbidden unless "
            "decision_status=ready"
        )
    if decision_status == "hold" and next_action not in {
        "defer_for_evidence",
        "require_human_governance",
    }:
        raise AnalysisAutomationDecisionError(
            "hold status requires defer_for_evidence or require_human_governance"
        )
    if (
        decision_status == "controlled_failure"
        and next_action != "stop_controlled_failure"
    ):
        raise AnalysisAutomationDecisionError(
            "controlled_failure requires next_action=stop_controlled_failure"
        )


def build_decision(
    *,
    domain: str,
    benchmark_id: str,
    dataset_id: str,
    dataset_content_fingerprint: str,
    partition_id: str,
    partition_role: str,
    baseline_candidate_id: str,
    baseline_config_fingerprint: str,
    current_candidate_id: str,
    current_config_fingerprint: str,
    analysis_eval_fingerprint: str,
    evidence_fingerprint: str,
    gate_verdict: str,
    decision_status: str,
    next_action: str,
    decision_token: str | None = None,
    production_authorized: bool = False,
    generated_at: str | None = None,
    planes: Mapping[str, Any] | None = None,
    extra_fields: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble and validate a v1 automation decision envelope."""
    if gate_verdict not in GATE_VERDICTS:
        raise AnalysisAutomationDecisionError(
            f"gate_decision.verdict must be PASS|FAIL|HOLD, got {gate_verdict!r}"
        )
    if production_authorized is not False:
        raise AnalysisAutomationDecisionError(
            "production_authorized must be false "
            "(promotion candidate never authorizes production)"
        )

    _assert_status_token_rules(
        decision_status=decision_status,
        decision_token=decision_token,
        next_action=next_action,
    )
    _assert_partition_firewall(role=partition_role, next_action=next_action)

    decision: dict[str, Any] = {
        "document_type": DOCUMENT_TYPE,
        "artifact_version": ARTIFACT_VERSION,
        "domain": _require_text(domain, "domain"),
        "benchmark": {
            "benchmark_id": _require_text(benchmark_id, "benchmark_id"),
            "dataset_id": _require_text(dataset_id, "dataset_id"),
            "dataset_content_fingerprint": _require_hex_fingerprint(
                dataset_content_fingerprint, "dataset_content_fingerprint"
            ),
        },
        "partition": {
            "partition_id": _require_text(partition_id, "partition_id"),
            "role": partition_role,
        },
        "baseline_candidate": {
            "candidate_id": _require_text(baseline_candidate_id, "baseline_candidate_id"),
            "config_fingerprint": _require_hex_fingerprint(
                baseline_config_fingerprint, "baseline_config_fingerprint"
            ),
        },
        "current_candidate": {
            "candidate_id": _require_text(current_candidate_id, "current_candidate_id"),
            "config_fingerprint": _require_hex_fingerprint(
                current_config_fingerprint, "current_config_fingerprint"
            ),
        },
        "evidence": {
            "analysis_eval_fingerprint": _require_hex_fingerprint(
                analysis_eval_fingerprint, "analysis_eval_fingerprint"
            ),
            "evidence_fingerprint": _require_hex_fingerprint(
                evidence_fingerprint, "evidence_fingerprint"
            ),
            "evidence_contract_version": EVIDENCE_CONTRACT_VERSION,
            "gate_decision": {
                "verdict": gate_verdict,
                "contract_version": GATE_DECISION_CONTRACT_VERSION,
            },
        },
        "decision_status": decision_status,
        "next_action": next_action,
        "production_authorized": False,
        "producer": PRODUCER_ID,
    }
    if decision_token is not None:
        decision["decision_token"] = decision_token
    if planes is not None:
        decision["planes"] = dict(planes)
    if generated_at is not None:
        decision["generated_at"] = _require_text(generated_at, "generated_at")
    if extra_fields:
        for key, value in extra_fields.items():
            if key in decision:
                raise AnalysisAutomationDecisionError(
                    f"extra field collides with reserved key: {key}"
                )
            decision[key] = value

    try:
        assert_portable_value(decision, field="decision")
    except AnalysisEvalArtifactError as exc:
        raise _wrap_portable(exc) from exc

    decision["decision_fingerprint"] = decision_semantic_fingerprint(decision)
    return validate_decision(decision)


def validate_decision(decision: Mapping[str, Any]) -> dict[str, Any]:
    """Validate envelope invariants; return a plain dict copy."""
    if not isinstance(decision, Mapping):
        raise AnalysisAutomationDecisionError("decision must be a mapping")
    if decision.get("document_type") != DOCUMENT_TYPE:
        raise AnalysisAutomationDecisionError(
            f"document_type must be {DOCUMENT_TYPE!r}"
        )
    if decision.get("artifact_version") != ARTIFACT_VERSION:
        raise AnalysisAutomationDecisionError(
            f"artifact_version must be {ARTIFACT_VERSION!r}"
        )

    domain = decision.get("domain")
    _require_text(domain, "domain")

    benchmark = decision.get("benchmark")
    if not isinstance(benchmark, Mapping):
        raise AnalysisAutomationDecisionError("benchmark must be a mapping")
    _require_text(benchmark.get("benchmark_id"), "benchmark_id")
    _require_text(benchmark.get("dataset_id"), "dataset_id")
    _require_hex_fingerprint(
        benchmark.get("dataset_content_fingerprint"),
        "dataset_content_fingerprint",
    )

    partition = decision.get("partition")
    if not isinstance(partition, Mapping):
        raise AnalysisAutomationDecisionError("partition must be a mapping")
    _require_text(partition.get("partition_id"), "partition_id")
    role = partition.get("role")
    if role not in DECISION_PARTITION_ROLES:
        raise AnalysisAutomationDecisionError(f"unsupported partition role: {role}")

    for cand_key in ("baseline_candidate", "current_candidate"):
        cand = decision.get(cand_key)
        if not isinstance(cand, Mapping):
            raise AnalysisAutomationDecisionError(f"{cand_key} must be a mapping")
        _require_text(cand.get("candidate_id"), f"{cand_key}.candidate_id")
        _require_hex_fingerprint(
            cand.get("config_fingerprint"), f"{cand_key}.config_fingerprint"
        )

    evidence = decision.get("evidence")
    if not isinstance(evidence, Mapping):
        raise AnalysisAutomationDecisionError("evidence must be a mapping")
    _require_hex_fingerprint(
        evidence.get("analysis_eval_fingerprint"), "analysis_eval_fingerprint"
    )
    _require_hex_fingerprint(
        evidence.get("evidence_fingerprint"), "evidence_fingerprint"
    )
    if evidence.get("evidence_contract_version") != EVIDENCE_CONTRACT_VERSION:
        raise AnalysisAutomationDecisionError(
            f"evidence_contract_version must be {EVIDENCE_CONTRACT_VERSION!r}"
        )
    gate = evidence.get("gate_decision")
    if not isinstance(gate, Mapping):
        raise AnalysisAutomationDecisionError("evidence.gate_decision must be a mapping")
    verdict = gate.get("verdict")
    if verdict not in GATE_VERDICTS:
        raise AnalysisAutomationDecisionError(
            f"gate_decision.verdict must be PASS|FAIL|HOLD, got {verdict!r}"
        )

    decision_status = decision.get("decision_status")
    next_action = decision.get("next_action")
    if not isinstance(next_action, str):
        raise AnalysisAutomationDecisionError("next_action must be a string")
    raw_token = decision.get("decision_token", None)
    decision_token = raw_token if raw_token is not None else None
    if decision_token is not None and type(decision_token) is not str:
        raise AnalysisAutomationDecisionError("decision_token must be a string or null")

    _assert_status_token_rules(
        decision_status=str(decision_status),
        decision_token=decision_token,
        next_action=next_action,
    )
    _assert_partition_firewall(role=str(role), next_action=next_action)

    if decision.get("production_authorized") is not False:
        raise AnalysisAutomationDecisionError(
            "production_authorized must be false "
            "(promotion candidate never authorizes production)"
        )

    try:
        assert_portable_value(dict(decision), field="decision")
        canonical_json_dumps(dict(decision))
    except AnalysisEvalArtifactError as exc:
        raise _wrap_portable(exc) from exc

    expected_fp = decision_semantic_fingerprint(decision)
    attached = decision.get("decision_fingerprint")
    if attached is None:
        raise AnalysisAutomationDecisionError("decision_fingerprint is required")
    if attached != expected_fp:
        raise AnalysisAutomationDecisionError(
            "decision_fingerprint does not match semantic payload"
        )

    # Drop null decision_token for a clean portable copy when absent.
    copy = json.loads(canonical_json_dumps(dict(decision)))
    if copy.get("decision_token") is None:
        copy.pop("decision_token", None)
    return copy


def serialize_decision(decision: Mapping[str, Any]) -> str:
    """Return canonical JSON for a validated decision."""
    validated = validate_decision(decision)
    try:
        return canonical_json_dumps(validated)
    except AnalysisEvalArtifactError as exc:
        raise _wrap_portable(exc) from exc


def aq1_scalar_decision_fixture(
    *,
    decision_status: str = "ready",
    decision_token: str | None = "KEEP_CURRENT_BASELINE_PATH",
    next_action: str = "keep_baseline_and_stop",
    partition_role: str = "calibration",
    partition_id: str = "aq1-cal-smoke",
    gate_verdict: str = "PASS",
    generated_at: str | None = "2026-10-06T00:00:00Z",
    current_candidate_id: str = "sample-brain.analyze.bpm.baseline",
    current_config_fingerprint: str | None = None,
    production_authorized: bool = False,
) -> dict[str, Any]:
    """Synthetic AQ1-style scalar decision fixture (Fixture A)."""
    baseline_fp = fingerprint({"profile": "baseline", "domain": "aq1.tempo"})
    current_fp = current_config_fingerprint or baseline_fp
    return build_decision(
        domain="aq1.tempo",
        benchmark_id="synthetic.aq1.tempo.decision.smoke",
        dataset_id="synthetic.aq1.tempo.v1",
        dataset_content_fingerprint=fingerprint(
            {"dataset_id": "synthetic.aq1.tempo.v1", "members": ["aq1-rec-001"]}
        ),
        partition_id=partition_id,
        partition_role=partition_role,
        baseline_candidate_id="sample-brain.analyze.bpm.baseline",
        baseline_config_fingerprint=baseline_fp,
        current_candidate_id=current_candidate_id,
        current_config_fingerprint=current_fp,
        analysis_eval_fingerprint=fingerprint(
            {"document_type": "sample-brain.analysis-eval.v1", "fixture": "aq1"}
        ),
        evidence_fingerprint=fingerprint(
            {"contract_version": EVIDENCE_CONTRACT_VERSION, "fixture": "aq1"}
        ),
        gate_verdict=gate_verdict,
        decision_status=decision_status,
        decision_token=decision_token,
        next_action=next_action,
        production_authorized=production_authorized,
        generated_at=generated_at,
    )


def aq5_ranking_decision_fixture(
    *,
    decision_status: str = "ready",
    decision_token: str | None = "PROMOTION_CANDIDATE_IDENTIFIED",
    next_action: str = "require_human_governance",
    partition_role: str = "calibration",
    partition_id: str = "aq5-cal-smoke",
    gate_verdict: str = "PASS",
    generated_at: str | None = "2026-10-06T00:00:00Z",
    production_authorized: bool = False,
) -> dict[str, Any]:
    """Synthetic AQ5/AQ6-style ranking / multi-plane decision fixture (Fixture B)."""
    baseline_fp = fingerprint({"profile": "baseline", "domain": "aq5.ranking"})
    current_fp = fingerprint({"profile": "weight-adapter-a", "domain": "aq5.ranking"})
    planes = {
        "ranking": {
            "k": 3,
            "ranked_ids": ["hit-a", "hit-b", "hit-c"],
            "scores": [0.91, 0.44, 0.33],
        },
        "companion": {
            "plane": "operational_latency",
            "status": "measured",
            "note": "kept separate; not a blended promotion score",
        },
    }
    return build_decision(
        domain="aq5.ranking",
        benchmark_id="synthetic.aq5.ranking.decision.smoke",
        dataset_id="synthetic.aq5.ranking.v1",
        dataset_content_fingerprint=fingerprint(
            {"dataset_id": "synthetic.aq5.ranking.v1", "members": ["aq5-query-001"]}
        ),
        partition_id=partition_id,
        partition_role=partition_role,
        baseline_candidate_id="sample-brain.search.ranking.baseline",
        baseline_config_fingerprint=baseline_fp,
        current_candidate_id="sample-brain.search.ranking.weight-adapter-a",
        current_config_fingerprint=current_fp,
        analysis_eval_fingerprint=fingerprint(
            {"document_type": "sample-brain.analysis-eval.v1", "fixture": "aq5"}
        ),
        evidence_fingerprint=fingerprint(
            {"contract_version": EVIDENCE_CONTRACT_VERSION, "fixture": "aq5"}
        ),
        gate_verdict=gate_verdict,
        decision_status=decision_status,
        decision_token=decision_token,
        next_action=next_action,
        production_authorized=production_authorized,
        generated_at=generated_at,
        planes=planes,
    )
