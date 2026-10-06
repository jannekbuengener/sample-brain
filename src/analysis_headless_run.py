"""Sample Brain analysis headless-run contract v1 (#1054 W0 freeze).

Frozen public API for M3/M4/M5 (do not rename without integrator GO):

Constants
    DOCUMENT_TYPE, ARTIFACT_VERSION, PRODUCER_ID
    RUN_STATUSES, OPERATIONS, HEADLESS_PARTITION_ROLES
    TUNABLE_PARTITION_ROLES, EXPLORATORY_OPERATIONS
    STATIC_ADAPTER_REGISTRY

Types / Protocol
    RunStatus, Operation, DomainAdapter

Builders / validators
    build_request, validate_request, serialize_request
    build_result, validate_result, serialize_result
    request_semantic_fingerprint, result_semantic_fingerprint
    request_semantic_payload, result_semantic_payload

Registry / preflight
    lookup_adapter
    preflight_operation_partition

Status vocabulary is ``completed`` | ``hold`` | ``controlled_failure``
(not #1043 ``ready``). Results must never emit ``decision_token`` /
``next_action`` and must never set ``production_authorized`` true.

Reuses #956 helpers (import-only): ``canonical_json_dumps``, ``fingerprint``,
``assert_portable_value``. No ARVP import. No CLI/subprocess primary.
Concrete AQ adapters are registered by M6; W0 keeps an empty static registry.
"""

from __future__ import annotations

import json
from types import MappingProxyType
from typing import Any, Literal, Mapping, Protocol, runtime_checkable

from src.analysis_eval_artifact import (
    AnalysisEvalArtifactError,
    assert_portable_value,
    canonical_json_dumps,
    fingerprint,
)

DOCUMENT_TYPE = "sample-brain.analysis-headless-run.v1"
ARTIFACT_VERSION = "1.0.0"
PRODUCER_ID = "sample-brain.analysis-headless-run"

RunStatus = Literal["completed", "hold", "controlled_failure"]
Operation = Literal["baseline", "compare", "locked_evaluation"]

RUN_STATUSES: frozenset[str] = frozenset(
    {"completed", "hold", "controlled_failure"}
)
OPERATIONS: frozenset[str] = frozenset(
    {"baseline", "compare", "locked_evaluation"}
)
EXPLORATORY_OPERATIONS: frozenset[str] = frozenset({"baseline", "compare"})

# Align with #1043 decision roles (includes holdout) for shared firewall ideas.
HEADLESS_PARTITION_ROLES: frozenset[str] = frozenset(
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

_FORBIDDEN_RESULT_KEYS: frozenset[str] = frozenset(
    {"decision_token", "next_action", "metrics", "metric_values"}
)
_REQUEST_FP_EXCLUDED: frozenset[str] = frozenset(
    {"generated_at", "request_fingerprint", "artifact_hash"}
)
_RESULT_FP_EXCLUDED: frozenset[str] = frozenset(
    {"generated_at", "result_fingerprint", "artifact_hash"}
)

# W0 freeze: empty static registry; M6 registers concrete AQ adapters.
STATIC_ADAPTER_REGISTRY: Mapping[str, "DomainAdapter"] = MappingProxyType({})


class AnalysisHeadlessRunError(ValueError):
    """Raised when a headless-run request/result violates the v1 contract."""


@runtime_checkable
class DomainAdapter(Protocol):
    """In-process AQ domain adapter Protocol (wraps existing ``run_*`` APIs)."""

    @property
    def adapter_id(self) -> str: ...

    @property
    def adapter_version(self) -> str: ...

    @property
    def capabilities(self) -> frozenset[str]: ...

    def run(self, request: Mapping[str, Any]) -> Mapping[str, Any]: ...


def _wrap_portable(exc: AnalysisEvalArtifactError) -> AnalysisHeadlessRunError:
    return AnalysisHeadlessRunError(str(exc))


def _require_text(value: object, field: str) -> str:
    if type(value) is not str or not value.strip():
        raise AnalysisHeadlessRunError(f"{field} must be a non-empty string")
    return value.strip()


def _require_hex_fingerprint(value: object, field: str) -> str:
    text = _require_text(value, field)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text.lower()):
        raise AnalysisHeadlessRunError(
            f"{field} must be a 64-char sha256 hex digest"
        )
    return text.lower()


def _candidate_identity(
    *,
    candidate_id: str | None,
    config_fingerprint: str | None,
    label: str,
    required: bool,
) -> dict[str, str] | None:
    if candidate_id is None and config_fingerprint is None:
        if required:
            raise AnalysisHeadlessRunError(
                f"{label} candidate identity is required"
            )
        return None
    if candidate_id is None or config_fingerprint is None:
        raise AnalysisHeadlessRunError(
            f"{label} requires both candidate_id and config_fingerprint"
        )
    return {
        "candidate_id": _require_text(candidate_id, f"{label}.candidate_id"),
        "config_fingerprint": _require_hex_fingerprint(
            config_fingerprint, f"{label}.config_fingerprint"
        ),
    }


def preflight_operation_partition(*, operation: str, partition_role: str) -> None:
    """Fail-closed operation×partition firewall (shared seam; #1043-inspired)."""
    if operation not in OPERATIONS:
        raise AnalysisHeadlessRunError(f"unsupported operation: {operation}")
    if partition_role not in HEADLESS_PARTITION_ROLES:
        raise AnalysisHeadlessRunError(
            f"unsupported partition role: {partition_role}"
        )
    if (
        partition_role not in TUNABLE_PARTITION_ROLES
        and operation in EXPLORATORY_OPERATIONS
    ):
        raise AnalysisHeadlessRunError(
            f"partition firewall: illegal operation {operation!r} "
            f"for non-tuning role {partition_role!r}"
        )


def lookup_adapter(
    adapter_id: str,
    *,
    registry: Mapping[str, DomainAdapter] | None = None,
) -> DomainAdapter:
    """Static registry lookup; unknown adapter_id fails closed."""
    adapter_key = _require_text(adapter_id, "adapter_id")
    table = STATIC_ADAPTER_REGISTRY if registry is None else registry
    try:
        return table[adapter_key]
    except KeyError as exc:
        raise AnalysisHeadlessRunError(
            f"unknown adapter: {adapter_key}"
        ) from exc


def request_semantic_payload(request: Mapping[str, Any]) -> dict[str, Any]:
    """Fingerprint body excluding volatile / self-hash fields."""
    return {
        key: value
        for key, value in request.items()
        if key not in _REQUEST_FP_EXCLUDED
    }


def request_semantic_fingerprint(request: Mapping[str, Any]) -> str:
    """SHA-256 of canonical JSON over semantic request fields only."""
    try:
        return fingerprint(request_semantic_payload(request))
    except AnalysisEvalArtifactError as exc:
        raise _wrap_portable(exc) from exc


def result_semantic_payload(result: Mapping[str, Any]) -> dict[str, Any]:
    """Fingerprint body excluding volatile / self-hash fields."""
    return {
        key: value
        for key, value in result.items()
        if key not in _RESULT_FP_EXCLUDED
    }


def result_semantic_fingerprint(result: Mapping[str, Any]) -> str:
    """SHA-256 of canonical JSON over semantic result fields only."""
    try:
        return fingerprint(result_semantic_payload(result))
    except AnalysisEvalArtifactError as exc:
        raise _wrap_portable(exc) from exc


def build_request(
    *,
    domain: str,
    adapter_id: str,
    operation: str,
    benchmark_id: str,
    dataset_id: str,
    dataset_content_fingerprint: str,
    partition_id: str,
    partition_role: str,
    evidence_intent: str,
    baseline_candidate_id: str | None = None,
    baseline_config_fingerprint: str | None = None,
    current_candidate_id: str | None = None,
    current_config_fingerprint: str | None = None,
    production_authorized: bool = False,
    generated_at: str | None = None,
    extra_fields: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble and validate a v1 headless-run request envelope."""
    if production_authorized is not False:
        raise AnalysisHeadlessRunError(
            "production_authorized must be false "
            "(headless run never authorizes production)"
        )
    preflight_operation_partition(
        operation=operation, partition_role=partition_role
    )

    require_baseline = operation in {"compare", "locked_evaluation", "baseline"}
    require_current = operation in {"compare", "locked_evaluation"}
    # baseline op: baseline identity required; current optional
    if operation == "baseline":
        require_baseline = True
        require_current = False

    baseline = _candidate_identity(
        candidate_id=baseline_candidate_id,
        config_fingerprint=baseline_config_fingerprint,
        label="baseline",
        required=require_baseline,
    )
    current = _candidate_identity(
        candidate_id=current_candidate_id,
        config_fingerprint=current_config_fingerprint,
        label="current",
        required=require_current,
    )

    request: dict[str, Any] = {
        "document_type": DOCUMENT_TYPE,
        "artifact_version": ARTIFACT_VERSION,
        "producer_id": PRODUCER_ID,
        "domain": _require_text(domain, "domain"),
        "adapter_id": _require_text(adapter_id, "adapter_id"),
        "operation": operation,
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
        "evidence_intent": _require_text(evidence_intent, "evidence_intent"),
        "production_authorized": False,
    }
    if baseline is not None:
        request["baseline"] = baseline
    if current is not None:
        request["current"] = current
    if generated_at is not None:
        request["generated_at"] = _require_text(generated_at, "generated_at")
    if extra_fields:
        for key, value in extra_fields.items():
            if key in request:
                raise AnalysisHeadlessRunError(
                    f"extra_fields cannot override reserved key: {key}"
                )
            if key in _FORBIDDEN_RESULT_KEYS or key in {
                "decision_token",
                "next_action",
            }:
                raise AnalysisHeadlessRunError(
                    f"forbidden request field: {key}"
                )
            request[key] = value

    return validate_request(request)


def validate_request(request: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a headless-run request and attach/verify request_fingerprint."""
    if not isinstance(request, Mapping):
        raise AnalysisHeadlessRunError("request must be a mapping")
    if request.get("document_type") != DOCUMENT_TYPE:
        raise AnalysisHeadlessRunError(
            f"document_type must be {DOCUMENT_TYPE!r}"
        )
    if request.get("artifact_version") != ARTIFACT_VERSION:
        raise AnalysisHeadlessRunError(
            f"artifact_version must be {ARTIFACT_VERSION!r}"
        )
    for forbidden in ("decision_token", "next_action"):
        if forbidden in request:
            raise AnalysisHeadlessRunError(
                f"{forbidden} is forbidden on headless-run request"
            )
    if request.get("production_authorized") is not False:
        raise AnalysisHeadlessRunError(
            "production_authorized must be false "
            "(headless run never authorizes production)"
        )

    operation = request.get("operation")
    if not isinstance(operation, str):
        raise AnalysisHeadlessRunError("operation must be a string")
    partition = request.get("partition")
    if not isinstance(partition, Mapping):
        raise AnalysisHeadlessRunError("partition must be a mapping")
    role = partition.get("role")
    if not isinstance(role, str):
        raise AnalysisHeadlessRunError("partition.role must be a string")
    preflight_operation_partition(operation=operation, partition_role=role)

    _require_text(request.get("domain"), "domain")
    _require_text(request.get("adapter_id"), "adapter_id")
    _require_text(request.get("evidence_intent"), "evidence_intent")
    _require_text(partition.get("partition_id"), "partition_id")

    benchmark = request.get("benchmark")
    if not isinstance(benchmark, Mapping):
        raise AnalysisHeadlessRunError("benchmark must be a mapping")
    _require_text(benchmark.get("benchmark_id"), "benchmark_id")
    _require_text(benchmark.get("dataset_id"), "dataset_id")
    _require_hex_fingerprint(
        benchmark.get("dataset_content_fingerprint"),
        "dataset_content_fingerprint",
    )

    require_baseline = operation in {"baseline", "compare", "locked_evaluation"}
    require_current = operation in {"compare", "locked_evaluation"}
    baseline = request.get("baseline")
    current = request.get("current")
    if require_baseline:
        if not isinstance(baseline, Mapping):
            raise AnalysisHeadlessRunError("baseline candidate identity is required")
        _require_text(baseline.get("candidate_id"), "baseline.candidate_id")
        _require_hex_fingerprint(
            baseline.get("config_fingerprint"), "baseline.config_fingerprint"
        )
    if require_current:
        if not isinstance(current, Mapping):
            raise AnalysisHeadlessRunError("current candidate identity is required")
        _require_text(current.get("candidate_id"), "current.candidate_id")
        _require_hex_fingerprint(
            current.get("config_fingerprint"), "current.config_fingerprint"
        )

    copy_req = dict(request)
    try:
        assert_portable_value(copy_req, field="request")
        canonical_json_dumps(copy_req)
    except AnalysisEvalArtifactError as exc:
        raise _wrap_portable(exc) from exc

    expected_fp = request_semantic_fingerprint(copy_req)
    attached = copy_req.get("request_fingerprint")
    if attached is None:
        copy_req["request_fingerprint"] = expected_fp
    else:
        attached_fp = _require_hex_fingerprint(attached, "request_fingerprint")
        if attached_fp != expected_fp:
            raise AnalysisHeadlessRunError(
                "request_fingerprint does not match semantic payload"
            )
        copy_req["request_fingerprint"] = attached_fp

    return json.loads(canonical_json_dumps(copy_req))


def serialize_request(request: Mapping[str, Any]) -> str:
    """Canonical JSON serialization of a validated request."""
    validated = validate_request(request)
    try:
        return canonical_json_dumps(validated)
    except AnalysisEvalArtifactError as exc:
        raise _wrap_portable(exc) from exc


def build_result(
    *,
    run_status: str,
    adapter_id: str,
    adapter_version: str,
    request_fingerprint: str,
    domain: str,
    operation: str,
    partition_id: str,
    partition_role: str,
    benchmark_id: str,
    dataset_id: str,
    dataset_content_fingerprint: str,
    baseline_candidate_id: str | None = None,
    baseline_config_fingerprint: str | None = None,
    current_candidate_id: str | None = None,
    current_config_fingerprint: str | None = None,
    domain_artifact_id: str | None = None,
    domain_artifact_fingerprint: str | None = None,
    analysis_eval_fingerprint: str | None = None,
    error_code: str | None = None,
    error_detail: str | None = None,
    production_authorized: bool = False,
    generated_at: str | None = None,
    extra_fields: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble and validate a v1 headless-run result envelope."""
    if production_authorized is not False:
        raise AnalysisHeadlessRunError(
            "production_authorized must be false "
            "(headless run never authorizes production)"
        )
    if run_status not in RUN_STATUSES:
        raise AnalysisHeadlessRunError(f"unsupported run_status: {run_status}")
    preflight_operation_partition(
        operation=operation, partition_role=partition_role
    )

    result: dict[str, Any] = {
        "document_type": DOCUMENT_TYPE,
        "artifact_version": ARTIFACT_VERSION,
        "producer_id": PRODUCER_ID,
        "run_status": run_status,
        "adapter_id": _require_text(adapter_id, "adapter_id"),
        "adapter_version": _require_text(adapter_version, "adapter_version"),
        "request_fingerprint": _require_hex_fingerprint(
            request_fingerprint, "request_fingerprint"
        ),
        "domain": _require_text(domain, "domain"),
        "operation": operation,
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
        "production_authorized": False,
    }

    baseline = _candidate_identity(
        candidate_id=baseline_candidate_id,
        config_fingerprint=baseline_config_fingerprint,
        label="baseline",
        required=False,
    )
    current = _candidate_identity(
        candidate_id=current_candidate_id,
        config_fingerprint=current_config_fingerprint,
        label="current",
        required=False,
    )
    if baseline is not None:
        result["baseline"] = baseline
    if current is not None:
        result["current"] = current

    if run_status == "completed":
        if domain_artifact_id is None or domain_artifact_fingerprint is None:
            raise AnalysisHeadlessRunError(
                "completed status requires domain_artifact identity/fingerprint"
            )
        result["domain_artifact"] = {
            "artifact_id": _require_text(
                domain_artifact_id, "domain_artifact.artifact_id"
            ),
            "artifact_fingerprint": _require_hex_fingerprint(
                domain_artifact_fingerprint, "domain_artifact.artifact_fingerprint"
            ),
        }
        if analysis_eval_fingerprint is not None:
            result["analysis_eval"] = {
                "document_type": "sample-brain.analysis-eval.v1",
                "artifact_fingerprint": _require_hex_fingerprint(
                    analysis_eval_fingerprint, "analysis_eval.artifact_fingerprint"
                ),
            }
    else:
        # hold / controlled_failure: machine-readable error; no fake success artifact
        if error_code is None or error_detail is None:
            raise AnalysisHeadlessRunError(
                f"{run_status} requires error_code and error_detail"
            )
        result["error"] = {
            "code": _require_text(error_code, "error.code"),
            "detail": _require_text(error_detail, "error.detail"),
        }
        if domain_artifact_id is not None or domain_artifact_fingerprint is not None:
            raise AnalysisHeadlessRunError(
                f"{run_status} must not attach a successful domain_artifact"
            )

    if generated_at is not None:
        result["generated_at"] = _require_text(generated_at, "generated_at")
    if extra_fields:
        for key, value in extra_fields.items():
            if key in result:
                raise AnalysisHeadlessRunError(
                    f"extra_fields cannot override reserved key: {key}"
                )
            if key in _FORBIDDEN_RESULT_KEYS:
                raise AnalysisHeadlessRunError(f"forbidden result field: {key}")
            result[key] = value

    return validate_result(result)


def validate_result(result: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a headless-run result and attach/verify result_fingerprint."""
    if not isinstance(result, Mapping):
        raise AnalysisHeadlessRunError("result must be a mapping")
    if result.get("document_type") != DOCUMENT_TYPE:
        raise AnalysisHeadlessRunError(
            f"document_type must be {DOCUMENT_TYPE!r}"
        )
    if result.get("artifact_version") != ARTIFACT_VERSION:
        raise AnalysisHeadlessRunError(
            f"artifact_version must be {ARTIFACT_VERSION!r}"
        )
    for forbidden in _FORBIDDEN_RESULT_KEYS:
        if forbidden in result:
            raise AnalysisHeadlessRunError(
                f"{forbidden} is forbidden on headless-run result"
            )
    if result.get("production_authorized") is not False:
        raise AnalysisHeadlessRunError(
            "production_authorized must be false "
            "(headless run never authorizes production)"
        )

    run_status = result.get("run_status")
    if run_status not in RUN_STATUSES:
        raise AnalysisHeadlessRunError(f"unsupported run_status: {run_status}")

    operation = result.get("operation")
    if not isinstance(operation, str):
        raise AnalysisHeadlessRunError("operation must be a string")
    partition = result.get("partition")
    if not isinstance(partition, Mapping):
        raise AnalysisHeadlessRunError("partition must be a mapping")
    role = partition.get("role")
    if not isinstance(role, str):
        raise AnalysisHeadlessRunError("partition.role must be a string")
    preflight_operation_partition(operation=operation, partition_role=role)

    _require_text(result.get("adapter_id"), "adapter_id")
    _require_text(result.get("adapter_version"), "adapter_version")
    _require_hex_fingerprint(result.get("request_fingerprint"), "request_fingerprint")
    _require_text(result.get("domain"), "domain")
    _require_text(partition.get("partition_id"), "partition_id")

    benchmark = result.get("benchmark")
    if not isinstance(benchmark, Mapping):
        raise AnalysisHeadlessRunError("benchmark must be a mapping")
    _require_text(benchmark.get("benchmark_id"), "benchmark_id")
    _require_text(benchmark.get("dataset_id"), "dataset_id")
    _require_hex_fingerprint(
        benchmark.get("dataset_content_fingerprint"),
        "dataset_content_fingerprint",
    )

    if run_status == "completed":
        domain_artifact = result.get("domain_artifact")
        if not isinstance(domain_artifact, Mapping):
            raise AnalysisHeadlessRunError(
                "completed status requires domain_artifact identity/fingerprint"
            )
        _require_text(domain_artifact.get("artifact_id"), "domain_artifact.artifact_id")
        _require_hex_fingerprint(
            domain_artifact.get("artifact_fingerprint"),
            "domain_artifact.artifact_fingerprint",
        )
        analysis_eval = result.get("analysis_eval")
        if analysis_eval is not None:
            if not isinstance(analysis_eval, Mapping):
                raise AnalysisHeadlessRunError("analysis_eval must be a mapping")
            if analysis_eval.get("document_type") != "sample-brain.analysis-eval.v1":
                raise AnalysisHeadlessRunError(
                    "analysis_eval.document_type must be "
                    "'sample-brain.analysis-eval.v1'"
                )
            _require_hex_fingerprint(
                analysis_eval.get("artifact_fingerprint"),
                "analysis_eval.artifact_fingerprint",
            )
    else:
        error = result.get("error")
        if not isinstance(error, Mapping):
            raise AnalysisHeadlessRunError(
                f"{run_status} requires error_code and error_detail"
            )
        _require_text(error.get("code"), "error.code")
        _require_text(error.get("detail"), "error.detail")
        if result.get("domain_artifact") is not None:
            raise AnalysisHeadlessRunError(
                f"{run_status} must not attach a successful domain_artifact"
            )

    copy_res = dict(result)
    try:
        assert_portable_value(copy_res, field="result")
        canonical_json_dumps(copy_res)
    except AnalysisEvalArtifactError as exc:
        raise _wrap_portable(exc) from exc

    expected_fp = result_semantic_fingerprint(copy_res)
    attached = copy_res.get("result_fingerprint")
    if attached is None:
        copy_res["result_fingerprint"] = expected_fp
    else:
        attached_fp = _require_hex_fingerprint(attached, "result_fingerprint")
        if attached_fp != expected_fp:
            raise AnalysisHeadlessRunError(
                "result_fingerprint does not match semantic payload"
            )
        copy_res["result_fingerprint"] = attached_fp

    return json.loads(canonical_json_dumps(copy_res))


def serialize_result(result: Mapping[str, Any]) -> str:
    """Canonical JSON serialization of a validated result."""
    validated = validate_result(result)
    try:
        return canonical_json_dumps(validated)
    except AnalysisEvalArtifactError as exc:
        raise _wrap_portable(exc) from exc
