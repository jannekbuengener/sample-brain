"""AQ1 tempo candidate-compare thin DomainAdapter (#1054 M3).

Wraps ``run_tempo_candidate_comparison`` / Path B (baseline-predictions).
Does not alter AQ1 algorithms or register into ``STATIC_ADAPTER_REGISTRY``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from src.analysis_eval_artifact import fingerprint
from src.analysis_headless_run import (
    AnalysisHeadlessRunError,
    build_result,
    preflight_operation_partition,
    validate_request,
)
from src.fsld_aq1_tempo_candidate_compare import (
    DOCUMENT_TYPE as AQ1_DOCUMENT_TYPE,
    SCHEMA_VERSION as AQ1_SCHEMA_VERSION,
    FsldAq1TempoCandidateCompareError,
    candidate_by_id,
    run_tempo_candidate_comparison,
)
from src.fsld_current_analyzer_eval import PUBLIC_AUDIO_NOT_AVAILABLE_LOCALLY

# Frozen adapter identity (M6 registers this id; do not rename without integrator GO).
ADAPTER_ID = "aq1.tempo.candidate_compare"
ADAPTER_VERSION = "1.0.0"
DOMAIN = "aq1.tempo"
CAPABILITIES: frozenset[str] = frozenset(
    {"baseline", "compare", "locked_evaluation"}
)

_SPLIT_BY_PARTITION_ROLE: Mapping[str, str] = {
    "development": "CALIBRATION",
    "calibration": "CALIBRATION",
    "validation": "TEST",
    "test": "TEST",
    "external_check": "TEST",
    "holdout": "TEST",
}


def tempo_candidate_config_fingerprint(candidate_id: str) -> str:
    """Deterministic config fingerprint for a frozen AQ1 tempo candidate."""
    candidate = candidate_by_id(candidate_id)
    return fingerprint(
        {
            "analyzer_id": candidate.analyzer_id,
            "bpm_normalization": candidate.bpm_normalization,
            "candidate_id": candidate.candidate_id,
            "schema_version": AQ1_SCHEMA_VERSION,
        }
    )


def _require_mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AnalysisHeadlessRunError(f"{field} must be a mapping")
    return value


def _require_relpath(value: object, field: str) -> str:
    if type(value) is not str or not value.strip():
        raise AnalysisHeadlessRunError(f"{field} must be a non-empty string")
    text = value.strip().replace("\\", "/")
    if text.startswith("/") or text.startswith("../") or "/../" in f"/{text}/":
        raise AnalysisHeadlessRunError(f"{field} must be a safe relative path")
    if len(text) >= 3 and text[1] == ":":
        raise AnalysisHeadlessRunError(f"{field} must be a safe relative path")
    return text


def _resolve_under_work_dir(work_dir: Path, relpath: str) -> Path:
    root = work_dir.resolve(strict=False)
    target = (root / relpath).resolve(strict=False)
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise AnalysisHeadlessRunError(
            "aq1_inputs path escapes work_dir"
        ) from exc
    return target


def _validate_candidate_identity(
    identity: Mapping[str, Any] | None, *, label: str, required: bool
) -> None:
    if identity is None:
        if required:
            raise AnalysisHeadlessRunError(f"{label} candidate identity is required")
        return
    candidate_id = identity.get("candidate_id")
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        raise AnalysisHeadlessRunError(f"{label}.candidate_id is required")
    expected_fp = tempo_candidate_config_fingerprint(candidate_id.strip())
    if identity.get("config_fingerprint") != expected_fp:
        raise AnalysisHeadlessRunError(
            f"{label}.config_fingerprint does not match frozen AQ1 candidate identity"
        )


def _domain_artifact_fingerprint(domain_result: Mapping[str, Any]) -> str:
    """Fingerprint the portable domain payload (exclude bulky records)."""
    portable = {
        "beat_grid_status": domain_result.get("beat_grid_status"),
        "candidates": domain_result.get("candidates"),
        "document_type": domain_result.get("document_type"),
        "manifest_sha256": domain_result.get("manifest_sha256"),
        "partition_role": domain_result.get("partition_role"),
        "raw_source": domain_result.get("raw_source"),
        "run_status": domain_result.get("run_status"),
        "schema_version": domain_result.get("schema_version"),
        "split": domain_result.get("split"),
    }
    return fingerprint(portable)


def _error_result(
    request: Mapping[str, Any],
    *,
    run_status: str,
    error_code: str,
    error_detail: str,
) -> dict[str, Any]:
    baseline = request.get("baseline") if isinstance(request.get("baseline"), Mapping) else {}
    current = request.get("current") if isinstance(request.get("current"), Mapping) else {}
    return build_result(
        run_status=run_status,
        adapter_id=ADAPTER_ID,
        adapter_version=ADAPTER_VERSION,
        request_fingerprint=str(request["request_fingerprint"]),
        domain=str(request["domain"]),
        operation=str(request["operation"]),
        partition_id=str(request["partition"]["partition_id"]),
        partition_role=str(request["partition"]["role"]),
        benchmark_id=str(request["benchmark"]["benchmark_id"]),
        dataset_id=str(request["benchmark"]["dataset_id"]),
        dataset_content_fingerprint=str(
            request["benchmark"]["dataset_content_fingerprint"]
        ),
        baseline_candidate_id=baseline.get("candidate_id"),
        baseline_config_fingerprint=baseline.get("config_fingerprint"),
        current_candidate_id=current.get("candidate_id"),
        current_config_fingerprint=current.get("config_fingerprint"),
        error_code=error_code,
        error_detail=error_detail[:500],
    )


class Aq1TempoCompareAdapter:
    """In-process DomainAdapter for AQ1 tempo candidate compare (Path B)."""

    def __init__(self, *, work_dir: Path) -> None:
        self._work_dir = Path(work_dir)

    @property
    def adapter_id(self) -> str:
        return ADAPTER_ID

    @property
    def adapter_version(self) -> str:
        return ADAPTER_VERSION

    @property
    def capabilities(self) -> frozenset[str]:
        return CAPABILITIES

    def run(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            validated = validate_request(request)
        except AnalysisHeadlessRunError as exc:
            # Contract-invalid requests cannot be projected into a typed result
            # safely without a validated fingerprint; re-raise.
            raise AnalysisHeadlessRunError(str(exc)) from exc

        try:
            return self._run_validated(validated)
        except AnalysisHeadlessRunError as exc:
            return _error_result(
                validated,
                run_status="controlled_failure",
                error_code="AQ1_ADAPTER_INPUT_INVALID",
                error_detail=str(exc),
            )
        except FsldAq1TempoCandidateCompareError as exc:
            return _error_result(
                validated,
                run_status="controlled_failure",
                error_code="AQ1_RUNNER_CONTROLLED_FAILURE",
                error_detail=str(exc),
            )

    def _run_validated(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        if request.get("adapter_id") != ADAPTER_ID:
            raise AnalysisHeadlessRunError(
                f"adapter_id mismatch: expected {ADAPTER_ID!r}"
            )
        if request.get("domain") != DOMAIN:
            raise AnalysisHeadlessRunError(f"domain mismatch: expected {DOMAIN!r}")

        operation = str(request["operation"])
        if operation not in CAPABILITIES:
            raise AnalysisHeadlessRunError(f"unsupported operation for AQ1: {operation}")

        baseline = request.get("baseline")
        current = request.get("current")
        _validate_candidate_identity(
            baseline if isinstance(baseline, Mapping) else None,
            label="baseline",
            required=True,
        )
        _validate_candidate_identity(
            current if isinstance(current, Mapping) else None,
            label="current",
            required=operation in {"compare", "locked_evaluation"},
        )

        partition = _require_mapping(request.get("partition"), "partition")
        partition_role = str(partition["role"])
        preflight_operation_partition(
            operation=operation, partition_role=partition_role
        )

        aq1_inputs = _require_mapping(request.get("aq1_inputs"), "aq1_inputs")
        raw_source = aq1_inputs.get("raw_source")
        if raw_source != "baseline_predictions":
            raise AnalysisHeadlessRunError(
                "aq1_inputs.raw_source must be 'baseline_predictions' (Path B)"
            )

        baseline_rel = _require_relpath(
            aq1_inputs.get("baseline_predictions_relpath"),
            "aq1_inputs.baseline_predictions_relpath",
        )
        output_rel = _require_relpath(
            aq1_inputs.get("output_relpath"), "aq1_inputs.output_relpath"
        )
        manifest_rel = _require_relpath(
            aq1_inputs.get("manifest_relpath"), "aq1_inputs.manifest_relpath"
        )
        sha_rel = _require_relpath(
            aq1_inputs.get("sha256_relpath"), "aq1_inputs.sha256_relpath"
        )

        split_value = aq1_inputs.get("split")
        if split_value is None:
            split = _SPLIT_BY_PARTITION_ROLE.get(partition_role)
            if split is None:
                raise AnalysisHeadlessRunError(
                    f"cannot derive AQ1 split from partition role {partition_role!r}"
                )
        else:
            if type(split_value) is not str or split_value not in {
                "CALIBRATION",
                "TEST",
            }:
                raise AnalysisHeadlessRunError(
                    "aq1_inputs.split must be CALIBRATION or TEST"
                )
            split = split_value
            expected = _SPLIT_BY_PARTITION_ROLE.get(partition_role)
            if expected is not None and split != expected:
                raise AnalysisHeadlessRunError(
                    "aq1_inputs.split disagrees with partition.role mapping"
                )

        baseline_path = _resolve_under_work_dir(self._work_dir, baseline_rel)
        output_path = _resolve_under_work_dir(self._work_dir, output_rel)
        manifest_path = _resolve_under_work_dir(self._work_dir, manifest_rel)
        sha256_path = _resolve_under_work_dir(self._work_dir, sha_rel)

        domain_result = run_tempo_candidate_comparison(
            split=split,
            output_path=output_path,
            baseline_predictions_path=baseline_path,
            manifest_path=manifest_path,
            sha256_path=sha256_path,
        )

        if domain_result.get("document_type") != AQ1_DOCUMENT_TYPE:
            raise AnalysisHeadlessRunError("AQ1 runner returned unexpected document_type")

        if domain_result.get("run_status") == PUBLIC_AUDIO_NOT_AVAILABLE_LOCALLY:
            return _error_result(
                request,
                run_status="hold",
                error_code="AQ1_NO_SUCCESSFUL_PREDICTIONS",
                error_detail=(
                    "AQ1 Path B produced no successful predictions "
                    f"(runner status {PUBLIC_AUDIO_NOT_AVAILABLE_LOCALLY})"
                ),
            )

        if domain_result.get("run_status") != "EVALUATED":
            return _error_result(
                request,
                run_status="controlled_failure",
                error_code="AQ1_UNEXPECTED_RUN_STATUS",
                error_detail=f"unexpected AQ1 run_status: {domain_result.get('run_status')!r}",
            )

        artifact_fp = _domain_artifact_fingerprint(domain_result)
        artifact_id = (
            f"{AQ1_DOCUMENT_TYPE}.{split}."
            f"{str(domain_result.get('manifest_sha256', ''))[:12]}"
        )

        baseline = request.get("baseline") if isinstance(request.get("baseline"), Mapping) else {}
        current = request.get("current") if isinstance(request.get("current"), Mapping) else {}
        return build_result(
            run_status="completed",
            adapter_id=ADAPTER_ID,
            adapter_version=ADAPTER_VERSION,
            request_fingerprint=str(request["request_fingerprint"]),
            domain=str(request["domain"]),
            operation=operation,
            partition_id=str(partition["partition_id"]),
            partition_role=partition_role,
            benchmark_id=str(request["benchmark"]["benchmark_id"]),
            dataset_id=str(request["benchmark"]["dataset_id"]),
            dataset_content_fingerprint=str(
                request["benchmark"]["dataset_content_fingerprint"]
            ),
            baseline_candidate_id=baseline.get("candidate_id"),
            baseline_config_fingerprint=baseline.get("config_fingerprint"),
            current_candidate_id=current.get("candidate_id"),
            current_config_fingerprint=current.get("config_fingerprint"),
            domain_artifact_id=artifact_id,
            domain_artifact_fingerprint=artifact_fp,
            extra_fields={
                "aq1_provenance": {
                    "raw_source": "baseline_predictions",
                    "split": split,
                    "schema_version": AQ1_SCHEMA_VERSION,
                    "output_relpath": output_rel,
                }
            },
        )
