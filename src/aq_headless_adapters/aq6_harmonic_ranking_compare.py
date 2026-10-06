"""Thin #1054 headless DomainAdapter for AQ6 ranking candidate compare (M4).

Wraps ``run_aq6_harmonic_ranking_candidate_compare`` only. Does not rewrite
ranking/theory algorithms, blend multi-plane provenance into one score,
register into ``STATIC_ADAPTER_REGISTRY`` (M6), or invent preference signals.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from src.analysis_eval_artifact import fingerprint
from src.analysis_headless_run import (
    AnalysisHeadlessRunError,
    build_result,
    validate_request,
)
from src.aq6_harmonic_ranking_candidate_compare import (
    DOCUMENT_TYPE as AQ6_COMPARE_DOCUMENT_TYPE,
    EXIT_INCOMPLETE,
    EXIT_NO_JUSTIFIED,
    EXIT_REPRODUCIBLE,
    Aq6HarmonicCandidateCompareError,
    candidate_by_id,
    candidate_public,
    run_aq6_harmonic_ranking_candidate_compare,
)

ADAPTER_ID = "aq6.ranking.candidate_compare"
ADAPTER_VERSION = "1.0.0"
DOMAIN_TOKEN = "aq6.ranking"
ADAPTER_CAPABILITIES: frozenset[str] = frozenset({"compare", "locked_evaluation"})

_PREFERENCE_PLANE = {
    # plane_id — key name "token" is forbidden by assert_portable_value.
    "plane_id": "aq6.preference",
    "status": "NOT_REQUIRED",
    "signal": None,
    "note": (
        "AQ6 preference remains NOT_REQUIRED/HOLD for this bootstrap; "
        "adapter does not invent a preference pseudo-signal."
    ),
}


def candidate_config_fingerprint(candidate_id: str) -> str:
    """Portable config fingerprint for a frozen AQ6 ranking candidate."""
    return fingerprint(candidate_public(candidate_by_id(candidate_id)))


def _error_result(
    request: Mapping[str, Any],
    *,
    run_status: str,
    error_code: str,
    error_detail: str,
) -> dict[str, Any]:
    benchmark = (
        request.get("benchmark")
        if isinstance(request.get("benchmark"), Mapping)
        else {}
    )
    partition = (
        request.get("partition")
        if isinstance(request.get("partition"), Mapping)
        else {}
    )
    baseline = (
        request.get("baseline")
        if isinstance(request.get("baseline"), Mapping)
        else None
    )
    current = (
        request.get("current")
        if isinstance(request.get("current"), Mapping)
        else None
    )
    return build_result(
        run_status=run_status,
        adapter_id=ADAPTER_ID,
        adapter_version=ADAPTER_VERSION,
        request_fingerprint=str(
            request.get("request_fingerprint") or fingerprint({})
        ),
        domain=str(request.get("domain") or DOMAIN_TOKEN),
        operation=str(request.get("operation") or "compare"),
        partition_id=str(partition.get("partition_id") or "unknown"),
        partition_role=str(partition.get("role") or "calibration"),
        benchmark_id=str(benchmark.get("benchmark_id") or "unknown"),
        dataset_id=str(benchmark.get("dataset_id") or "unknown"),
        dataset_content_fingerprint=str(
            benchmark.get("dataset_content_fingerprint") or fingerprint({})
        ),
        baseline_candidate_id=(
            None if baseline is None else str(baseline.get("candidate_id"))
        ),
        baseline_config_fingerprint=(
            None
            if baseline is None
            else str(baseline.get("config_fingerprint"))
        ),
        current_candidate_id=(
            None if current is None else str(current.get("candidate_id"))
        ),
        current_config_fingerprint=(
            None if current is None else str(current.get("config_fingerprint"))
        ),
        error_code=error_code,
        error_detail=error_detail[:500],
    )


def _validate_known_candidate(
    identity: Mapping[str, Any] | None, *, label: str
) -> None:
    if identity is None:
        raise Aq6HarmonicCandidateCompareError(
            f"{label} candidate identity is required"
        )
    candidate_id = identity.get("candidate_id")
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        raise Aq6HarmonicCandidateCompareError(
            f"{label} candidate_id is required"
        )
    candidate = candidate_by_id(candidate_id.strip())
    expected_fp = fingerprint(candidate_public(candidate))
    attached = identity.get("config_fingerprint")
    if attached != expected_fp:
        raise Aq6HarmonicCandidateCompareError(
            f"{label} config_fingerprint does not match frozen candidate identity"
        )


def _map_exit_to_run_status(exit_status: str) -> str:
    if exit_status == EXIT_REPRODUCIBLE:
        return "completed"
    if exit_status == EXIT_NO_JUSTIFIED:
        return "hold"
    if exit_status == EXIT_INCOMPLETE:
        return "controlled_failure"
    return "controlled_failure"


def _domain_planes(domain_doc: Mapping[str, Any]) -> dict[str, Any]:
    candidates = domain_doc.get("candidates")
    theory_gates: list[dict[str, Any]] = []
    if isinstance(candidates, list):
        for entry in candidates:
            if not isinstance(entry, Mapping):
                continue
            gate = entry.get("theory_gate")
            theory_gates.append(
                {
                    "candidate_id": entry.get("candidate_id"),
                    "gate_pass": bool(
                        isinstance(gate, Mapping) and gate.get("pass") is True
                    ),
                }
            )
    theory_plane = domain_doc.get("theory_plane")
    mixed = False
    if isinstance(theory_plane, Mapping):
        mixed = bool(theory_plane.get("mixed_into_ranking_metrics"))
    return {
        "ranking": {
            "plane_id": "aq6.ranking",
            "document_type": AQ6_COMPARE_DOCUMENT_TYPE,
            "exit_status": domain_doc.get("exit_status"),
            "candidate_count": domain_doc.get("candidate_count"),
            "mixed_into_aggregate_score": False,
            "no_tuning_on_test": bool(domain_doc.get("no_tuning_on_test")),
            "production_switch": bool(domain_doc.get("production_switch")),
        },
        "theory": {
            "plane_id": "aq6.theory",
            "hard_gate": True,
            "mixed_into_ranking_metrics": mixed,
            "all_candidates_pass": all(g["gate_pass"] for g in theory_gates)
            if theory_gates
            else False,
            "per_candidate": theory_gates,
        },
        "preference": dict(_PREFERENCE_PLANE),
    }


class Aq6HarmonicRankingCompareAdapter:
    """In-process DomainAdapter wrapping AQ6 ranking candidate compare."""

    def __init__(
        self,
        *,
        output_path: Path | str,
        repo_root: Path | str | None = None,
        ranking_fixture_path: Path | str | None = None,
        theory_fixture_path: Path | str | None = None,
    ) -> None:
        self._output_path = Path(output_path)
        self._repo_root = Path(repo_root) if repo_root is not None else None
        self._ranking_fixture_path = (
            Path(ranking_fixture_path)
            if ranking_fixture_path is not None
            else None
        )
        self._theory_fixture_path = (
            Path(theory_fixture_path)
            if theory_fixture_path is not None
            else None
        )

    @property
    def adapter_id(self) -> str:
        return ADAPTER_ID

    @property
    def adapter_version(self) -> str:
        return ADAPTER_VERSION

    @property
    def capabilities(self) -> frozenset[str]:
        return ADAPTER_CAPABILITIES

    def run(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            validated = validate_request(request)
        except AnalysisHeadlessRunError as exc:
            # Match M3: contract-invalid requests re-raise (no trusted fingerprint).
            raise AnalysisHeadlessRunError(str(exc)) from exc

        try:
            return self._run_validated(validated)
        except Aq6HarmonicCandidateCompareError as exc:
            detail = str(exc)
            code = "domain_error"
            lowered = detail.lower()
            if "unknown" in lowered or "config_fingerprint" in lowered:
                code = "unknown_candidate"
            return _error_result(
                validated,
                run_status="controlled_failure",
                error_code=code,
                error_detail=detail,
            )
        except ValueError as exc:
            detail = str(exc)
            code = (
                "output_path_rejected"
                if "outside" in detail.lower() or "host path" in detail.lower()
                else "domain_error"
            )
            return _error_result(
                validated,
                run_status="controlled_failure",
                error_code=code,
                error_detail=detail,
            )
        except AnalysisHeadlessRunError as exc:
            return _error_result(
                validated,
                run_status="controlled_failure",
                error_code="adapter_controlled_failure",
                error_detail=str(exc),
            )

    def _run_validated(self, validated: Mapping[str, Any]) -> Mapping[str, Any]:
        if validated.get("adapter_id") != ADAPTER_ID:
            return _error_result(
                validated,
                run_status="controlled_failure",
                error_code="adapter_mismatch",
                error_detail=(
                    f"request adapter_id {validated.get('adapter_id')!r} "
                    f"does not match {ADAPTER_ID!r}"
                ),
            )

        if validated.get("domain") != DOMAIN_TOKEN:
            return _error_result(
                validated,
                run_status="controlled_failure",
                error_code="domain_mismatch",
                error_detail=(
                    f"request domain {validated.get('domain')!r} "
                    f"does not match {DOMAIN_TOKEN!r}"
                ),
            )

        operation = validated.get("operation")
        if operation not in ADAPTER_CAPABILITIES:
            return _error_result(
                validated,
                run_status="controlled_failure",
                error_code="unsupported_operation",
                error_detail=(
                    f"adapter {ADAPTER_ID} does not support operation {operation!r}"
                ),
            )

        baseline = validated.get("baseline")
        current = validated.get("current")
        if not isinstance(baseline, Mapping) or not isinstance(current, Mapping):
            raise Aq6HarmonicCandidateCompareError(
                "compare/locked_evaluation require baseline and current identities"
            )
        _validate_known_candidate(baseline, label="baseline")
        _validate_known_candidate(current, label="current")

        domain_doc = run_aq6_harmonic_ranking_candidate_compare(
            output_path=self._output_path,
            repo_root=self._repo_root,
            ranking_fixture_path=self._ranking_fixture_path,
            theory_fixture_path=self._theory_fixture_path,
        )

        exit_status = str(domain_doc.get("exit_status") or EXIT_INCOMPLETE)
        run_status = _map_exit_to_run_status(exit_status)
        planes = _domain_planes(domain_doc)
        artifact_fp = fingerprint(domain_doc)
        partition = validated["partition"]
        benchmark = validated["benchmark"]

        if run_status != "completed":
            return build_result(
                run_status=run_status,
                adapter_id=ADAPTER_ID,
                adapter_version=ADAPTER_VERSION,
                request_fingerprint=validated["request_fingerprint"],
                domain=DOMAIN_TOKEN,
                operation=str(operation),
                partition_id=partition["partition_id"],
                partition_role=partition["role"],
                benchmark_id=benchmark["benchmark_id"],
                dataset_id=benchmark["dataset_id"],
                dataset_content_fingerprint=benchmark[
                    "dataset_content_fingerprint"
                ],
                baseline_candidate_id=baseline["candidate_id"],
                baseline_config_fingerprint=baseline["config_fingerprint"],
                current_candidate_id=current["candidate_id"],
                current_config_fingerprint=current["config_fingerprint"],
                error_code=exit_status,
                error_detail=(
                    "AQ6 ranking candidate compare did not reach reproducible exit"
                ),
                extra_fields={"domain_planes": planes},
            )

        return build_result(
            run_status="completed",
            adapter_id=ADAPTER_ID,
            adapter_version=ADAPTER_VERSION,
            request_fingerprint=validated["request_fingerprint"],
            domain=DOMAIN_TOKEN,
            operation=str(operation),
            partition_id=partition["partition_id"],
            partition_role=partition["role"],
            benchmark_id=benchmark["benchmark_id"],
            dataset_id=benchmark["dataset_id"],
            dataset_content_fingerprint=benchmark["dataset_content_fingerprint"],
            baseline_candidate_id=baseline["candidate_id"],
            baseline_config_fingerprint=baseline["config_fingerprint"],
            current_candidate_id=current["candidate_id"],
            current_config_fingerprint=current["config_fingerprint"],
            domain_artifact_id=AQ6_COMPARE_DOCUMENT_TYPE,
            domain_artifact_fingerprint=artifact_fp,
            extra_fields={"domain_planes": planes},
        )


__all__ = [
    "ADAPTER_CAPABILITIES",
    "ADAPTER_ID",
    "ADAPTER_VERSION",
    "DOMAIN_TOKEN",
    "Aq6HarmonicRankingCompareAdapter",
    "candidate_config_fingerprint",
]
