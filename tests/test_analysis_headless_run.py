"""Contract tests for sample-brain.analysis-headless-run.v1 (#1054 W0).

M1: request/result envelope + fingerprints + portability.
M2: DomainAdapter Protocol, static registry, invoke, operation×partition preflight.
"""

from __future__ import annotations

import ast
import copy
import math
from pathlib import Path
from typing import Any, Mapping

import pytest

from src.analysis_eval_artifact import fingerprint
from src.analysis_headless_run import (
    ADAPTERS,
    ARTIFACT_VERSION,
    DOCUMENT_TYPE,
    OPERATIONS,
    RUN_STATUSES,
    AnalysisHeadlessRunError,
    DomainAdapter,
    build_request,
    build_result,
    invoke_analysis_headless_run,
    lookup_adapter,
    preflight_operation_partition,
    request_semantic_fingerprint,
    result_semantic_fingerprint,
    validate_request,
    validate_result,
)

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
MODULE_PATH = SRC_ROOT / "analysis_headless_run.py"
FP_A = fingerprint({"profile": "baseline"})
FP_B = fingerprint({"profile": "candidate-a"})
FP_DS = fingerprint({"members": ["a", "b"]})


def _minimal_request_kwargs(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "request_id": "req-aq1-cal-001",
        "domain_id": "aq1.tempo",
        "adapter_id": "test.stub.adapter",
        "expected_adapter_version": "1.0.0",
        "operation": "compare",
        "benchmark_id": "aq1-tempo-bench-v1",
        "partition_id": "aq1-cal-p1",
        "partition_role": "calibration",
        "output_intent": {
            "domain_artifact": True,
            "analysis_eval_projection": False,
        },
        "baseline_candidate_id": "baseline-default",
        "baseline_config_fingerprint": FP_A,
        "current_candidate_id": "candidate-a",
        "current_config_fingerprint": FP_B,
    }
    kwargs.update(overrides)
    return kwargs


def _minimal_result_kwargs(request: Mapping[str, Any], **overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "status": "completed",
        "adapter_id": request["adapter_id"],
        "adapter_version": request["expected_adapter_version"],
        "request_fingerprint": request["request_fingerprint"],
        "domain_id": request["domain_id"],
        "operation": request["operation"],
        "partition_id": request["partition"]["partition_id"],
        "partition_role": request["partition"]["role"],
        "benchmark_id": request["benchmark"]["benchmark_id"],
        "baseline_candidate_id": request.get("baseline", {}).get("candidate_id"),
        "baseline_config_fingerprint": request.get("baseline", {}).get(
            "config_fingerprint"
        ),
        "current_candidate_id": request.get("current", {}).get("candidate_id"),
        "current_config_fingerprint": request.get("current", {}).get(
            "config_fingerprint"
        ),
        "domain_artifact_id": "aq1-compare-smoke",
        "domain_artifact_fingerprint": fingerprint({"fixture": "aq1"}),
    }
    kwargs.update(overrides)
    return kwargs


class _FakeAdapter:
    """Test-only adapter; not registered in production ADAPTERS."""

    def __init__(
        self,
        *,
        adapter_id: str = "test.stub.adapter",
        adapter_version: str = "1.0.0",
        domain_id: str = "aq1.tempo",
        supported_operations: frozenset[str] | None = None,
        capabilities: frozenset[str] | None = None,
        fail_mode: str | None = None,
    ) -> None:
        self._adapter_id = adapter_id
        self._adapter_version = adapter_version
        self._domain_id = domain_id
        self._supported_operations = (
            frozenset({"baseline", "compare", "locked_evaluation"})
            if supported_operations is None
            else supported_operations
        )
        self._capabilities = (
            frozenset({"locked_evidence_ok"})
            if capabilities is None
            else capabilities
        )
        self._fail_mode = fail_mode
        self.last_request: Mapping[str, Any] | None = None

    @property
    def adapter_id(self) -> str:
        return self._adapter_id

    @property
    def adapter_version(self) -> str:
        return self._adapter_version

    @property
    def domain_id(self) -> str:
        return self._domain_id

    @property
    def supported_operations(self) -> frozenset[str]:
        return self._supported_operations

    @property
    def capabilities(self) -> frozenset[str]:
        return self._capabilities

    def run(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        self.last_request = request
        if self._fail_mode == "path":
            raise RuntimeError(r"failed reading C:\Users\private\samples\kick.wav")
        if self._fail_mode == "domain":
            raise AnalysisHeadlessRunError("ADAPTER_INPUT_INVALID: missing members")
        return build_result(**_minimal_result_kwargs(request))


# ---------------------------------------------------------------------------
# M1 — contract skeleton
# ---------------------------------------------------------------------------


def test_m1_minimal_valid_request() -> None:
    req = build_request(**_minimal_request_kwargs())
    assert req["document_type"] == DOCUMENT_TYPE == (
        "sample-brain.analysis-headless-run.v1"
    )
    assert req["artifact_version"] == ARTIFACT_VERSION == "1.0.0"
    assert req["request_id"] == "req-aq1-cal-001"
    assert req["domain_id"] == "aq1.tempo"
    assert req["adapter_id"] == "test.stub.adapter"
    assert req["expected_adapter_version"] == "1.0.0"
    assert req["operation"] == "compare"
    assert req["benchmark"]["benchmark_id"] == "aq1-tempo-bench-v1"
    assert req["partition"]["partition_id"] == "aq1-cal-p1"
    assert req["partition"]["role"] == "calibration"
    assert req["output_intent"]["domain_artifact"] is True
    assert req["output_intent"]["analysis_eval_projection"] is False
    assert "request_fingerprint" in req
    assert len(req["request_fingerprint"]) == 64


def test_m1_deterministic_request_fingerprint() -> None:
    a = build_request(**_minimal_request_kwargs())
    b = build_request(**_minimal_request_kwargs())
    assert a["request_fingerprint"] == b["request_fingerprint"]
    assert a["request_fingerprint"] == request_semantic_fingerprint(a)


def test_m1_semantic_mutation_changes_fingerprint() -> None:
    a = build_request(**_minimal_request_kwargs())
    b = build_request(**_minimal_request_kwargs(request_id="req-aq1-cal-002"))
    assert a["request_fingerprint"] != b["request_fingerprint"]


def test_m1_volatile_field_does_not_change_fingerprint() -> None:
    a = build_request(**_minimal_request_kwargs(generated_at="2026-01-01T00:00:00Z"))
    b = build_request(**_minimal_request_kwargs(generated_at="2026-12-31T23:59:59Z"))
    assert a["request_fingerprint"] == b["request_fingerprint"]


def test_m1_malformed_rejected() -> None:
    with pytest.raises(AnalysisHeadlessRunError):
        build_request(**_minimal_request_kwargs(operation="optimize"))
    req = build_request(**_minimal_request_kwargs())
    bad = dict(req)
    bad["document_type"] = "sample-brain.analysis-eval.v1"
    with pytest.raises(AnalysisHeadlessRunError, match="document_type"):
        validate_request(bad)
    bad2 = dict(req)
    del bad2["request_id"]
    with pytest.raises(AnalysisHeadlessRunError, match="request_id"):
        validate_request(bad2)


def test_m1_portable_path_violation_rejected() -> None:
    with pytest.raises(AnalysisHeadlessRunError, match="path|forbidden|portable"):
        build_request(
            **_minimal_request_kwargs(
                adapter_params={"note": r"C:\Users\private\samples"},
            )
        )


def test_m1_valid_completed_hold_controlled_failure_results() -> None:
    req = build_request(**_minimal_request_kwargs())
    completed = build_result(**_minimal_result_kwargs(req))
    hold = build_result(
        **_minimal_result_kwargs(
            req,
            status="hold",
            domain_artifact_id=None,
            domain_artifact_fingerprint=None,
            failure_code="INSUFFICIENT_EVIDENCE",
            failure_details="hold for evidence",
        )
    )
    fail = build_result(
        **_minimal_result_kwargs(
            req,
            status="controlled_failure",
            domain_artifact_id=None,
            domain_artifact_fingerprint=None,
            failure_code="ADAPTER_INPUT_INVALID",
            failure_details="missing benchmark members",
        )
    )
    assert validate_result(completed)["status"] == "completed"
    assert validate_result(hold)["status"] == "hold"
    assert validate_result(fail)["status"] == "controlled_failure"
    assert RUN_STATUSES == frozenset({"completed", "hold", "controlled_failure"})
    assert OPERATIONS == frozenset({"baseline", "compare", "locked_evaluation"})


def test_m1_result_fingerprint_deterministic_and_mismatch_rejected() -> None:
    req = build_request(**_minimal_request_kwargs())
    a = build_result(**_minimal_result_kwargs(req))
    b = build_result(**_minimal_result_kwargs(req))
    assert a["result_fingerprint"] == b["result_fingerprint"]
    assert a["result_fingerprint"] == result_semantic_fingerprint(a)
    dirty = dict(a)
    dirty["result_fingerprint"] = "0" * 64
    with pytest.raises(AnalysisHeadlessRunError, match="result_fingerprint"):
        validate_result(dirty)


def test_m1_hold_does_not_expose_fake_measured_zero() -> None:
    req = build_request(**_minimal_request_kwargs())
    hold = build_result(
        **_minimal_result_kwargs(
            req,
            status="hold",
            domain_artifact_id=None,
            domain_artifact_fingerprint=None,
            failure_code="INSUFFICIENT_EVIDENCE",
            failure_details="hold for evidence",
        )
    )
    assert hold.get("domain_artifact") is None
    assert "metrics" not in hold
    assert "metric_values" not in hold
    assert hold.get("status") != "completed"


def test_m1_no_decision_fields_on_result() -> None:
    req = build_request(**_minimal_request_kwargs())
    result = build_result(**_minimal_result_kwargs(req))
    assert "decision_token" not in result
    assert "next_action" not in result
    assert "decision_status" not in result
    assert result.get("production_authorized") is not True
    dirty = dict(result)
    dirty["decision_token"] = "KEEP_CURRENT_BASELINE_PATH"
    with pytest.raises(AnalysisHeadlessRunError, match="decision_token|forbidden"):
        validate_result(dirty)
    dirty2 = dict(result)
    dirty2["next_action"] = "continue_calibration"
    with pytest.raises(AnalysisHeadlessRunError, match="next_action|forbidden"):
        validate_result(dirty2)


def test_m1_no_runtime_import_arvp() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "arvp" and not alias.name.startswith("arvp.")
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert mod != "arvp" and not mod.startswith("arvp.")


def test_m1_reuses_eval_helpers_no_fork() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    imports: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "src.analysis_eval_artifact":
            imports.extend(alias.name for alias in node.names)
    for required in ("canonical_json_dumps", "fingerprint", "assert_portable_value"):
        assert required in imports
    defined = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "canonical_json_dumps" not in defined
    assert "fingerprint" not in defined
    assert "assert_portable_value" not in defined


def test_m1_optional_analysis_eval_fingerprint_on_completed() -> None:
    req = build_request(
        **_minimal_request_kwargs(
            output_intent={
                "domain_artifact": True,
                "analysis_eval_projection": True,
            }
        )
    )
    result = build_result(
        **_minimal_result_kwargs(
            req,
            analysis_eval_fingerprint=fingerprint({"document_type": "eval"}),
        )
    )
    assert result["analysis_eval"]["artifact_fingerprint"]
    assert "decision_token" not in result


def test_m1_candidate_pins_are_provenance_only() -> None:
    req = build_request(
        **_minimal_request_kwargs(
            candidate_set_fingerprint=fingerprint({"ids": ["a", "b"]}),
            candidate_ids=["baseline-default", "candidate-a"],
        )
    )
    assert req["candidate_set_fingerprint"]
    assert req["candidate_ids"] == ["baseline-default", "candidate-a"]
    # Shared request must not invent a second pair — pins are opaque provenance.
    assert "search_space" not in req
    assert "generated_candidates" not in req


# ---------------------------------------------------------------------------
# M2 — Protocol, static registry, preflight, invoke
# ---------------------------------------------------------------------------


def test_m2_domain_adapter_protocol_structural() -> None:
    stub = _FakeAdapter()
    assert isinstance(stub, DomainAdapter)


def test_m2_static_adapters_empty_and_unknown_rejected() -> None:
    assert dict(ADAPTERS) == {}
    with pytest.raises(AnalysisHeadlessRunError, match="unknown adapter"):
        lookup_adapter("aq1.tempo.candidate_compare")


def test_m2_version_mismatch_rejected() -> None:
    stub = _FakeAdapter(adapter_version="9.9.9")
    req = build_request(**_minimal_request_kwargs(expected_adapter_version="1.0.0"))
    result = invoke_analysis_headless_run(req, registry={stub.adapter_id: stub})
    assert result["status"] == "controlled_failure"
    assert result["failure"]["code"] == "ADAPTER_VERSION_MISMATCH"
    assert "decision_token" not in result


def test_m2_unsupported_operation_rejected() -> None:
    stub = _FakeAdapter(supported_operations=frozenset({"baseline"}))
    req = build_request(**_minimal_request_kwargs(operation="compare"))
    with pytest.raises(AnalysisHeadlessRunError, match="unsupported operation"):
        invoke_analysis_headless_run(req, registry={stub.adapter_id: stub})


def test_m2_development_calibration_legal_compare_accepted() -> None:
    stub = _FakeAdapter()
    for role in ("development", "calibration"):
        req = build_request(
            **_minimal_request_kwargs(
                partition_role=role,
                partition_id=f"aq1-{role}-p1",
                request_id=f"req-{role}",
            )
        )
        result = invoke_analysis_headless_run(req, registry={stub.adapter_id: stub})
        assert result["status"] == "completed"
        assert result["partition"]["role"] == role


def test_m2_test_holdout_illegal_compare_rejected() -> None:
    for role in ("test", "holdout"):
        with pytest.raises(AnalysisHeadlessRunError, match="partition firewall"):
            preflight_operation_partition(operation="compare", partition_role=role)
        with pytest.raises(AnalysisHeadlessRunError, match="partition firewall"):
            build_request(
                **_minimal_request_kwargs(
                    partition_role=role,
                    operation="compare",
                    partition_id=f"aq1-{role}-p1",
                )
            )


def test_m2_locked_evaluation_requires_declared_capability() -> None:
    no_lock = _FakeAdapter(capabilities=frozenset())
    req = build_request(
        **_minimal_request_kwargs(
            operation="locked_evaluation",
            partition_role="test",
            partition_id="aq1-test-p1",
            request_id="req-locked-no-cap",
        )
    )
    with pytest.raises(AnalysisHeadlessRunError, match="locked_evidence_ok"):
        invoke_analysis_headless_run(req, registry={no_lock.adapter_id: no_lock})

    ok = _FakeAdapter(capabilities=frozenset({"locked_evidence_ok"}))
    result = invoke_analysis_headless_run(req, registry={ok.adapter_id: ok})
    assert result["status"] == "completed"
    assert result["operation"] == "locked_evaluation"


def test_m2_adapter_receives_validated_request() -> None:
    stub = _FakeAdapter()
    req = build_request(**_minimal_request_kwargs())
    invoke_analysis_headless_run(req, registry={stub.adapter_id: stub})
    assert stub.last_request is not None
    assert stub.last_request["request_fingerprint"] == req["request_fingerprint"]
    assert stub.last_request["document_type"] == DOCUMENT_TYPE


def test_m2_adapter_failure_maps_to_controlled_failure() -> None:
    stub = _FakeAdapter(fail_mode="domain")
    req = build_request(**_minimal_request_kwargs())
    result = invoke_analysis_headless_run(req, registry={stub.adapter_id: stub})
    assert result["status"] == "controlled_failure"
    assert result["failure"]["code"]
    assert "decision_token" not in result
    assert "next_action" not in result


def test_m2_raw_host_path_exception_does_not_leak() -> None:
    stub = _FakeAdapter(fail_mode="path")
    req = build_request(**_minimal_request_kwargs())
    result = invoke_analysis_headless_run(req, registry={stub.adapter_id: stub})
    assert result["status"] == "controlled_failure"
    blob = str(result)
    assert r"C:\Users\private" not in blob
    assert "kick.wav" not in blob
    assert result["failure"]["code"] == "ADAPTER_RUNTIME_FAILURE"


def test_m2_no_decision_fields_and_no_arvp_on_invoke() -> None:
    stub = _FakeAdapter()
    req = build_request(**_minimal_request_kwargs())
    result = invoke_analysis_headless_run(req, registry={stub.adapter_id: stub})
    assert "decision_token" not in result
    assert "next_action" not in result
    assert "decision_status" not in result
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert "arvp" not in mod
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "arvp" not in alias.name


def test_m2_nan_rejected_in_portable_payload() -> None:
    req = build_request(**_minimal_request_kwargs())
    bad = copy.deepcopy(req)
    bad["probe_score"] = float("nan")
    with pytest.raises(AnalysisHeadlessRunError, match="non-finite|canonical|portable"):
        validate_request(bad)
    result = build_result(**_minimal_result_kwargs(req))
    bad_res = copy.deepcopy(result)
    bad_res["probe"] = math.nan
    with pytest.raises(AnalysisHeadlessRunError, match="non-finite|portable|canonical"):
        validate_result(bad_res)
