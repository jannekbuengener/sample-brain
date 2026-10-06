"""Contract tests for sample-brain.analysis-headless-run.v1 (#1054 W0).

M1: request/result envelope + fingerprints + portability.
M2: DomainAdapter Protocol, static registry, operation×partition preflight.
"""

from __future__ import annotations

import ast
import copy
import json
import math
from pathlib import Path
from typing import Any, Mapping

import pytest

from src.analysis_eval_artifact import fingerprint
from src.analysis_headless_run import (
    ARTIFACT_VERSION,
    DOCUMENT_TYPE,
    OPERATIONS,
    RUN_STATUSES,
    AnalysisHeadlessRunError,
    DomainAdapter,
    STATIC_ADAPTER_REGISTRY,
    bind_adapter,
    build_request,
    build_result,
    lookup_adapter,
    preflight_operation_partition,
    request_semantic_fingerprint,
    result_semantic_fingerprint,
    serialize_request,
    serialize_result,
    validate_request,
    validate_result,
)

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
MODULE_PATH = SRC_ROOT / "analysis_headless_run.py"


def _minimal_request_kwargs(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "domain": "aq1.tempo",
        "adapter_id": "aq1.tempo.candidate_compare",
        "operation": "compare",
        "benchmark_id": "aq1-tempo-bench-v1",
        "dataset_id": "aq1-cal-smoke",
        "dataset_content_fingerprint": fingerprint({"members": ["a", "b"]}),
        "partition_id": "aq1-cal-p1",
        "partition_role": "calibration",
        "baseline_candidate_id": "baseline-default",
        "baseline_config_fingerprint": fingerprint({"profile": "baseline"}),
        "current_candidate_id": "candidate-a",
        "current_config_fingerprint": fingerprint({"profile": "candidate-a"}),
        "evidence_intent": "domain_artifact",
    }
    kwargs.update(overrides)
    return kwargs


def _minimal_result_kwargs(request: Mapping[str, Any], **overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "run_status": "completed",
        "adapter_id": request["adapter_id"],
        "adapter_version": "1.0.0",
        "request_fingerprint": request["request_fingerprint"],
        "domain": request["domain"],
        "operation": request["operation"],
        "partition_id": request["partition"]["partition_id"],
        "partition_role": request["partition"]["role"],
        "benchmark_id": request["benchmark"]["benchmark_id"],
        "dataset_id": request["benchmark"]["dataset_id"],
        "dataset_content_fingerprint": request["benchmark"][
            "dataset_content_fingerprint"
        ],
        "baseline_candidate_id": request["baseline"]["candidate_id"],
        "baseline_config_fingerprint": request["baseline"]["config_fingerprint"],
        "current_candidate_id": request["current"]["candidate_id"],
        "current_config_fingerprint": request["current"]["config_fingerprint"],
        "domain_artifact_id": "aq1-compare-smoke",
        "domain_artifact_fingerprint": fingerprint({"fixture": "aq1"}),
    }
    kwargs.update(overrides)
    return kwargs


# ---------------------------------------------------------------------------
# M1 — contract skeleton
# ---------------------------------------------------------------------------


def test_document_identity_frozen() -> None:
    req = build_request(**_minimal_request_kwargs())
    assert req["document_type"] == DOCUMENT_TYPE == (
        "sample-brain.analysis-headless-run.v1"
    )
    assert req["artifact_version"] == ARTIFACT_VERSION == "1.0.0"


def test_run_status_vocabulary_excludes_ready() -> None:
    assert RUN_STATUSES == frozenset({"completed", "hold", "controlled_failure"})
    assert "ready" not in RUN_STATUSES


def test_operations_vocabulary_frozen() -> None:
    assert OPERATIONS == frozenset({"baseline", "compare", "locked_evaluation"})


def test_build_request_deterministic_fingerprint() -> None:
    a = build_request(**_minimal_request_kwargs())
    b = build_request(**_minimal_request_kwargs())
    assert a["request_fingerprint"] == b["request_fingerprint"]
    assert a["request_fingerprint"] == request_semantic_fingerprint(a)
    assert len(a["request_fingerprint"]) == 64


def test_request_fingerprint_stable_under_key_reorder() -> None:
    req = build_request(**_minimal_request_kwargs())
    # Rebuild with reversed key insertion order; canonical JSON sort_keys keeps FP stable.
    reordered = {
        "request_fingerprint": req["request_fingerprint"],
        "artifact_version": req["artifact_version"],
        "document_type": req["document_type"],
        "producer_id": req["producer_id"],
        "operation": req["operation"],
        "adapter_id": req["adapter_id"],
        "domain": req["domain"],
        "evidence_intent": req["evidence_intent"],
        "production_authorized": req["production_authorized"],
        "benchmark": dict(reversed(list(req["benchmark"].items()))),
        "partition": dict(reversed(list(req["partition"].items()))),
        "baseline": dict(reversed(list(req["baseline"].items()))),
        "current": dict(reversed(list(req["current"].items()))),
    }
    assert request_semantic_fingerprint(reordered) == req["request_fingerprint"]


def test_serialize_request_roundtrip() -> None:
    req = build_request(**_minimal_request_kwargs())
    text = serialize_request(req)
    again = json.loads(text)
    assert validate_request(again)["request_fingerprint"] == req["request_fingerprint"]
    assert serialize_request(again) == text


def test_build_result_completed_with_optional_analysis_eval_ref() -> None:
    req = build_request(**_minimal_request_kwargs())
    result = build_result(
        **_minimal_result_kwargs(
            req,
            analysis_eval_fingerprint=fingerprint(
                {"document_type": "sample-brain.analysis-eval.v1", "fixture": "aq1"}
            ),
        )
    )
    validated = validate_result(result)
    assert validated["run_status"] == "completed"
    assert validated["analysis_eval"]["artifact_fingerprint"]
    assert validated["production_authorized"] is False
    assert "decision_token" not in validated
    assert "next_action" not in validated


def test_result_hold_and_controlled_failure_are_not_success() -> None:
    req = build_request(**_minimal_request_kwargs())
    hold = build_result(
        **_minimal_result_kwargs(
            req,
            run_status="hold",
            domain_artifact_id=None,
            domain_artifact_fingerprint=None,
            error_code="INSUFFICIENT_EVIDENCE",
            error_detail="hold for evidence",
        )
    )
    fail = build_result(
        **_minimal_result_kwargs(
            req,
            run_status="controlled_failure",
            domain_artifact_id=None,
            domain_artifact_fingerprint=None,
            error_code="ADAPTER_INPUT_INVALID",
            error_detail="missing benchmark members",
        )
    )
    assert validate_result(hold)["run_status"] == "hold"
    assert validate_result(fail)["run_status"] == "controlled_failure"
    assert hold["run_status"] != "completed"
    assert fail["run_status"] != "completed"
    assert hold.get("domain_artifact") is None
    assert fail.get("domain_artifact") is None


def test_result_rejects_ready_status() -> None:
    req = build_request(**_minimal_request_kwargs())
    with pytest.raises(AnalysisHeadlessRunError, match="unsupported run_status|ready"):
        build_result(**_minimal_result_kwargs(req, run_status="ready"))


def test_result_rejects_decision_token_and_next_action() -> None:
    req = build_request(**_minimal_request_kwargs())
    result = build_result(**_minimal_result_kwargs(req))
    dirty = dict(result)
    dirty["decision_token"] = "KEEP_CURRENT_BASELINE_PATH"
    with pytest.raises(AnalysisHeadlessRunError, match="decision_token|forbidden"):
        validate_result(dirty)
    dirty2 = dict(result)
    dirty2["next_action"] = "continue_calibration"
    with pytest.raises(AnalysisHeadlessRunError, match="next_action|forbidden"):
        validate_result(dirty2)


def test_production_authorized_always_false() -> None:
    with pytest.raises(AnalysisHeadlessRunError, match="production_authorized"):
        build_request(**_minimal_request_kwargs(production_authorized=True))
    req = build_request(**_minimal_request_kwargs())
    with pytest.raises(AnalysisHeadlessRunError, match="production_authorized"):
        build_result(**_minimal_result_kwargs(req, production_authorized=True))


def test_request_rejects_absolute_path_leakage() -> None:
    with pytest.raises(AnalysisHeadlessRunError, match="path|forbidden|portable"):
        build_request(
            **_minimal_request_kwargs(
                evidence_intent="C:\\Users\\private\\samples",
            )
        )


def test_request_rejects_non_finite_portable_values() -> None:
    req = build_request(**_minimal_request_kwargs())
    bad = copy.deepcopy(req)
    bad["probe_score"] = float("nan")
    with pytest.raises(AnalysisHeadlessRunError, match="non-finite|canonical|portable"):
        validate_request(bad)


def test_result_fingerprint_deterministic() -> None:
    req = build_request(**_minimal_request_kwargs())
    a = build_result(**_minimal_result_kwargs(req))
    b = build_result(**_minimal_result_kwargs(req))
    assert a["result_fingerprint"] == b["result_fingerprint"]
    assert a["result_fingerprint"] == result_semantic_fingerprint(a)


def test_serialize_result_roundtrip() -> None:
    req = build_request(**_minimal_request_kwargs())
    result = build_result(**_minimal_result_kwargs(req))
    text = serialize_result(result)
    assert serialize_result(json.loads(text)) == text


def test_completed_without_fake_zero_metrics_field() -> None:
    """Completed results must not invent a metrics blob of zeros."""
    req = build_request(**_minimal_request_kwargs())
    result = build_result(**_minimal_result_kwargs(req))
    assert "metrics" not in result
    assert "metric_values" not in result


def test_module_reuses_eval_helpers_no_fork() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    imports: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "src.analysis_eval_artifact":
            imports.extend(alias.name for alias in node.names)
    for required in ("canonical_json_dumps", "fingerprint", "assert_portable_value"):
        assert required in imports
    # No local redefinition of the three helpers.
    defined = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "canonical_json_dumps" not in defined
    assert "fingerprint" not in defined
    assert "assert_portable_value" not in defined


# ---------------------------------------------------------------------------
# M2 — Protocol, static registry, preflight
# ---------------------------------------------------------------------------


class _StubAdapter:
    adapter_id = "test.stub.adapter"
    adapter_version = "0.0.1"
    capabilities: frozenset[str] = frozenset({"baseline", "compare", "locked_evaluation"})

    def run(self, request: Mapping[str, Any]) -> dict[str, Any]:
        return build_result(**_minimal_result_kwargs(request, adapter_version=self.adapter_version))


def test_domain_adapter_protocol_structural() -> None:
    stub = _StubAdapter()
    assert isinstance(stub, DomainAdapter)


def test_static_registry_has_aq1_aq6_and_fail_closed_unknown() -> None:
    assert "aq1.tempo.candidate_compare" in STATIC_ADAPTER_REGISTRY
    assert "aq6.ranking.candidate_compare" in STATIC_ADAPTER_REGISTRY
    aq1 = lookup_adapter("aq1.tempo.candidate_compare")
    aq6 = lookup_adapter("aq6.ranking.candidate_compare")
    assert aq1.adapter_id == "aq1.tempo.candidate_compare"
    assert aq6.adapter_id == "aq6.ranking.candidate_compare"
    assert aq1.adapter_version == "1.0.0"
    assert aq6.adapter_version == "1.0.0"
    with pytest.raises(AnalysisHeadlessRunError, match="unknown adapter"):
        lookup_adapter("totally.unknown.adapter")
    with pytest.raises(AnalysisHeadlessRunError, match="unbound"):
        aq1.run({})


def test_bind_adapter_constructs_host_bound_instances(tmp_path: Path) -> None:
    work = tmp_path / "aq1-work"
    work.mkdir()
    out = tmp_path / "aq6-out" / "compare.json"
    out.parent.mkdir()
    aq1 = bind_adapter("aq1.tempo.candidate_compare", work_dir=work)
    aq6 = bind_adapter("aq6.ranking.candidate_compare", output_path=out)
    assert aq1.adapter_id == "aq1.tempo.candidate_compare"
    assert aq6.adapter_id == "aq6.ranking.candidate_compare"
    assert isinstance(aq1, DomainAdapter)
    assert isinstance(aq6, DomainAdapter)
    with pytest.raises(AnalysisHeadlessRunError, match="unknown adapter"):
        bind_adapter("totally.unknown.adapter", work_dir=work)


def test_lookup_adapter_accepts_explicit_registry() -> None:
    stub = _StubAdapter()
    found = lookup_adapter(stub.adapter_id, registry={stub.adapter_id: stub})
    assert found is stub


def test_unknown_operation_fail_closed() -> None:
    with pytest.raises(AnalysisHeadlessRunError, match="unsupported operation"):
        preflight_operation_partition(operation="tune", partition_role="calibration")
    with pytest.raises(AnalysisHeadlessRunError, match="unsupported operation"):
        build_request(**_minimal_request_kwargs(operation="optimize"))


def test_calibration_allows_baseline_and_compare() -> None:
    preflight_operation_partition(operation="baseline", partition_role="calibration")
    preflight_operation_partition(operation="compare", partition_role="development")
    req = build_request(
        **_minimal_request_kwargs(
            operation="baseline",
            current_candidate_id=None,
            current_config_fingerprint=None,
        )
    )
    assert req["operation"] == "baseline"
    assert "current" not in req or req.get("current") is None


def test_test_holdout_reject_exploratory_operations() -> None:
    with pytest.raises(AnalysisHeadlessRunError, match="partition firewall"):
        preflight_operation_partition(operation="compare", partition_role="test")
    with pytest.raises(AnalysisHeadlessRunError, match="partition firewall"):
        preflight_operation_partition(operation="baseline", partition_role="holdout")
    with pytest.raises(AnalysisHeadlessRunError, match="partition firewall"):
        build_request(**_minimal_request_kwargs(partition_role="test", operation="compare"))


def test_test_holdout_allow_locked_evaluation() -> None:
    preflight_operation_partition(
        operation="locked_evaluation", partition_role="test"
    )
    preflight_operation_partition(
        operation="locked_evaluation", partition_role="holdout"
    )
    req = build_request(
        **_minimal_request_kwargs(
            operation="locked_evaluation",
            partition_role="holdout",
            partition_id="aq1-holdout-p1",
        )
    )
    assert req["operation"] == "locked_evaluation"
    assert req["partition"]["role"] == "holdout"


def test_locked_roles_cannot_be_used_as_tuning_via_compare() -> None:
    """TEST/HOLDOUT cannot become tuning input through exploratory ops."""
    for role in ("test", "holdout", "validation", "external_check"):
        with pytest.raises(AnalysisHeadlessRunError, match="partition firewall"):
            preflight_operation_partition(operation="compare", partition_role=role)


def test_unsupported_partition_role_fail_closed() -> None:
    with pytest.raises(AnalysisHeadlessRunError, match="unsupported partition"):
        preflight_operation_partition(operation="compare", partition_role="prod")


def test_compare_requires_baseline_and_current() -> None:
    with pytest.raises(AnalysisHeadlessRunError, match="baseline|current|required"):
        build_request(
            **_minimal_request_kwargs(
                operation="compare",
                baseline_candidate_id=None,
                baseline_config_fingerprint=None,
            )
        )


def test_nan_rejected_in_result_portable_payload() -> None:
    req = build_request(**_minimal_request_kwargs())
    result = build_result(**_minimal_result_kwargs(req))
    bad = copy.deepcopy(result)
    bad["error"] = {"code": "X", "detail": "ok", "score": math.nan}
    with pytest.raises(AnalysisHeadlessRunError, match="non-finite|portable|canonical"):
        validate_result(bad)
