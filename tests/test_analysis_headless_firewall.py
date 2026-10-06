"""M5 firewall / privacy / fail-closed regression pack (#1054).

Additive pack against frozen ``src/analysis_headless_run.py`` (W0 SHA).
Uses local stub DomainAdapters only — no real AQ1/AQ6 adapters.
Does not modify shared contracts, registry, CANON, or runner modules.
"""

from __future__ import annotations

import copy
import math
from typing import Any, Mapping

import pytest

from src.analysis_eval_artifact import fingerprint
from src.analysis_headless_run import (
    ARTIFACT_VERSION,
    DOCUMENT_TYPE,
    EXPLORATORY_OPERATIONS,
    HEADLESS_PARTITION_ROLES,
    STATIC_ADAPTER_REGISTRY,
    TUNABLE_PARTITION_ROLES,
    AnalysisHeadlessRunError,
    DomainAdapter,
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

_FP_A = fingerprint({"fixture": "firewall-a"})
_FP_B = fingerprint({"fixture": "firewall-b"})
_FP_CFG = fingerprint({"profile": "firewall-cfg"})
_FP_BASE = fingerprint({"profile": "firewall-baseline"})
_FP_CUR = fingerprint({"profile": "firewall-current"})


def _req_kwargs(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "domain": "firewall.stub",
        "adapter_id": "firewall.stub.adapter",
        "operation": "compare",
        "benchmark_id": "firewall-bench-v1",
        "dataset_id": "firewall-cal-smoke",
        "dataset_content_fingerprint": _FP_A,
        "partition_id": "firewall-cal-p1",
        "partition_role": "calibration",
        "baseline_candidate_id": "baseline-default",
        "baseline_config_fingerprint": _FP_BASE,
        "current_candidate_id": "candidate-a",
        "current_config_fingerprint": _FP_CUR,
        "evidence_intent": "domain_artifact",
    }
    kwargs.update(overrides)
    return kwargs


def _res_kwargs(request: Mapping[str, Any], **overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "run_status": "completed",
        "adapter_id": request["adapter_id"],
        "adapter_version": "0.0.1-firewall",
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
        "baseline_candidate_id": request.get("baseline", {}).get("candidate_id"),
        "baseline_config_fingerprint": request.get("baseline", {}).get(
            "config_fingerprint"
        ),
        "current_candidate_id": request.get("current", {}).get("candidate_id"),
        "current_config_fingerprint": request.get("current", {}).get(
            "config_fingerprint"
        ),
        "domain_artifact_id": "firewall-artifact",
        "domain_artifact_fingerprint": _FP_B,
    }
    kwargs.update(overrides)
    return kwargs


class _FirewallStubAdapter:
    """Local stub DomainAdapter for M5 only (not registered in STATIC_ADAPTER_REGISTRY)."""

    adapter_id = "firewall.stub.adapter"
    adapter_version = "0.0.1-firewall"
    capabilities: frozenset[str] = frozenset(
        {"baseline", "compare", "locked_evaluation"}
    )

    def run(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        return build_result(**_res_kwargs(request, adapter_version=self.adapter_version))


class _ControlledFailureStubAdapter:
    """Stub that always returns a machine-readable controlled_failure result."""

    adapter_id = "firewall.stub.controlled_failure"
    adapter_version = "0.0.1-cf"
    capabilities: frozenset[str] = frozenset({"compare"})

    def run(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        return build_result(
            **_res_kwargs(
                request,
                adapter_id=self.adapter_id,
                adapter_version=self.adapter_version,
                run_status="controlled_failure",
                domain_artifact_id=None,
                domain_artifact_fingerprint=None,
                error_code="ADAPTER_INPUT_INVALID",
                error_detail="stub controlled failure",
            )
        )


# ---------------------------------------------------------------------------
# Unknown adapter / operation — fail-closed
# ---------------------------------------------------------------------------


def test_unknown_adapter_fail_closed_on_empty_static_registry() -> None:
    assert dict(STATIC_ADAPTER_REGISTRY) == {}
    with pytest.raises(AnalysisHeadlessRunError, match="unknown adapter"):
        lookup_adapter("aq1.tempo.candidate_compare")
    with pytest.raises(AnalysisHeadlessRunError, match="unknown adapter"):
        lookup_adapter("aq6.harmonic.ranking")
    with pytest.raises(AnalysisHeadlessRunError, match="unknown adapter"):
        lookup_adapter("totally.unknown.adapter")


def test_unknown_adapter_fail_closed_on_explicit_registry() -> None:
    stub = _FirewallStubAdapter()
    registry = {stub.adapter_id: stub}
    with pytest.raises(AnalysisHeadlessRunError, match="unknown adapter"):
        lookup_adapter("missing.adapter", registry=registry)
    assert lookup_adapter(stub.adapter_id, registry=registry) is stub


def test_unknown_operation_fail_closed() -> None:
    with pytest.raises(AnalysisHeadlessRunError, match="unsupported operation"):
        preflight_operation_partition(operation="tune", partition_role="calibration")
    with pytest.raises(AnalysisHeadlessRunError, match="unsupported operation"):
        preflight_operation_partition(
            operation="candidate_selection", partition_role="calibration"
        )
    with pytest.raises(AnalysisHeadlessRunError, match="unsupported operation"):
        build_request(**_req_kwargs(operation="optimize"))
    with pytest.raises(AnalysisHeadlessRunError, match="unsupported operation"):
        build_request(**_req_kwargs(operation="rank_and_promote"))


def test_stub_adapter_protocol_and_explicit_registry_run() -> None:
    stub = _FirewallStubAdapter()
    assert isinstance(stub, DomainAdapter)
    req = build_request(**_req_kwargs())
    found = lookup_adapter(stub.adapter_id, registry={stub.adapter_id: stub})
    result = found.run(req)
    assert result["run_status"] == "completed"
    assert result["production_authorized"] is False
    assert "decision_token" not in result
    assert "next_action" not in result


# ---------------------------------------------------------------------------
# Partition firewall: TEST/HOLDOUT deny tuning-like exploratory ops
# ---------------------------------------------------------------------------


def test_calibration_allows_exploratory_ops() -> None:
    preflight_operation_partition(operation="baseline", partition_role="calibration")
    preflight_operation_partition(operation="compare", partition_role="calibration")
    preflight_operation_partition(operation="compare", partition_role="development")
    req = build_request(**_req_kwargs(partition_role="calibration", operation="compare"))
    assert req["partition"]["role"] == "calibration"
    assert req["operation"] == "compare"


def test_test_holdout_deny_compare_and_baseline_via_preflight() -> None:
    locked_roles = sorted(HEADLESS_PARTITION_ROLES - TUNABLE_PARTITION_ROLES)
    for role in locked_roles:
        for operation in sorted(EXPLORATORY_OPERATIONS):
            with pytest.raises(AnalysisHeadlessRunError, match="partition firewall"):
                preflight_operation_partition(operation=operation, partition_role=role)


def test_test_holdout_tuning_like_compare_denied_on_build_request() -> None:
    for role in ("test", "holdout"):
        with pytest.raises(AnalysisHeadlessRunError, match="partition firewall"):
            build_request(**_req_kwargs(partition_role=role, operation="compare"))
        with pytest.raises(AnalysisHeadlessRunError, match="partition firewall"):
            build_request(
                **_req_kwargs(
                    partition_role=role,
                    operation="baseline",
                    current_candidate_id=None,
                    current_config_fingerprint=None,
                )
            )


def test_test_holdout_allow_locked_evaluation_only() -> None:
    for role in ("test", "holdout", "validation", "external_check"):
        preflight_operation_partition(
            operation="locked_evaluation", partition_role=role
        )
        req = build_request(
            **_req_kwargs(
                operation="locked_evaluation",
                partition_role=role,
                partition_id=f"firewall-{role}-p1",
            )
        )
        assert req["operation"] == "locked_evaluation"
        assert req["partition"]["role"] == role


def test_holdout_cannot_emit_tuning_result_via_exploratory_op() -> None:
    """Result builder also enforces partition firewall (no holdout+compare leak)."""
    req = build_request(
        **_req_kwargs(
            operation="locked_evaluation",
            partition_role="holdout",
            partition_id="firewall-holdout-p1",
        )
    )
    with pytest.raises(AnalysisHeadlessRunError, match="partition firewall"):
        build_result(**_res_kwargs(req, operation="compare", partition_role="holdout"))


# ---------------------------------------------------------------------------
# production_authorized + #1043 boundary (no decision_token / next_action)
# ---------------------------------------------------------------------------


def test_production_authorized_cannot_be_true_on_request_or_result() -> None:
    with pytest.raises(AnalysisHeadlessRunError, match="production_authorized"):
        build_request(**_req_kwargs(production_authorized=True))
    req = build_request(**_req_kwargs())
    assert req["production_authorized"] is False
    with pytest.raises(AnalysisHeadlessRunError, match="production_authorized"):
        build_result(**_res_kwargs(req, production_authorized=True))
    result = build_result(**_res_kwargs(req))
    assert result["production_authorized"] is False


def test_validate_rejects_production_authorized_true_injected() -> None:
    req = build_request(**_req_kwargs())
    dirty = dict(req)
    dirty["production_authorized"] = True
    with pytest.raises(AnalysisHeadlessRunError, match="production_authorized"):
        validate_request(dirty)
    result = build_result(**_res_kwargs(req))
    dirty_res = dict(result)
    dirty_res["production_authorized"] = True
    with pytest.raises(AnalysisHeadlessRunError, match="production_authorized"):
        validate_result(dirty_res)


def test_no_decision_token_or_next_action_on_request_or_result() -> None:
    with pytest.raises(AnalysisHeadlessRunError, match="forbidden|decision_token"):
        build_request(**_req_kwargs(extra_fields={"decision_token": "KEEP_CURRENT"}))
    with pytest.raises(AnalysisHeadlessRunError, match="forbidden|next_action"):
        build_request(**_req_kwargs(extra_fields={"next_action": "continue_calibration"}))

    req = build_request(**_req_kwargs())
    with pytest.raises(AnalysisHeadlessRunError, match="forbidden|decision_token"):
        build_result(
            **_res_kwargs(req, extra_fields={"decision_token": "PROMOTION_CANDIDATE"})
        )
    with pytest.raises(AnalysisHeadlessRunError, match="forbidden|next_action"):
        build_result(
            **_res_kwargs(req, extra_fields={"next_action": "require_human_governance"})
        )

    result = build_result(**_res_kwargs(req))
    assert "decision_token" not in result
    assert "next_action" not in result
    for key in ("decision_token", "next_action"):
        dirty = dict(result)
        dirty[key] = "should-not-land"
        with pytest.raises(AnalysisHeadlessRunError, match=f"{key}|forbidden"):
            validate_result(dirty)


# ---------------------------------------------------------------------------
# Portable path / assert_portable_value surfaces + non-finite
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_path",
    [
        r"C:\Users\private\samples\kick.wav",
        "/home/private/samples/kick.wav",
        "file:///tmp/private/kick.wav",
        r"\\nas\private\kick.wav",
    ],
)
def test_portable_path_rejection_on_request(bad_path: str) -> None:
    with pytest.raises(
        AnalysisHeadlessRunError, match="path|portable|forbidden"
    ):
        build_request(**_req_kwargs(evidence_intent=bad_path))


def test_portable_path_rejection_on_result_extra_field() -> None:
    req = build_request(**_req_kwargs())
    with pytest.raises(
        AnalysisHeadlessRunError, match="path|portable|forbidden"
    ):
        build_result(
            **_res_kwargs(
                req,
                extra_fields={"note": "/var/lib/private/cache.bin"},
            )
        )


def test_sensitive_key_rejection_surfaces_via_assert_portable_value() -> None:
    req = build_request(**_req_kwargs())
    dirty = dict(req)
    dirty["sample_path"] = "fixtures/public/ok.wav"
    with pytest.raises(AnalysisHeadlessRunError, match="sensitive|portable|forbidden"):
        validate_request(dirty)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_rejection_on_request(bad: float) -> None:
    req = build_request(**_req_kwargs())
    dirty = copy.deepcopy(req)
    dirty["probe_score"] = bad
    with pytest.raises(
        AnalysisHeadlessRunError, match="non-finite|portable|canonical"
    ):
        validate_request(dirty)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_non_finite_rejection_on_result(bad: float) -> None:
    req = build_request(**_req_kwargs())
    result = build_result(**_res_kwargs(req))
    dirty = copy.deepcopy(result)
    dirty["error"] = {"code": "X", "detail": "ok", "score": bad}
    with pytest.raises(
        AnalysisHeadlessRunError, match="non-finite|portable|canonical"
    ):
        validate_result(dirty)


# ---------------------------------------------------------------------------
# Invalid version / identity / missing required fields
# ---------------------------------------------------------------------------


def test_invalid_document_type_and_artifact_version_fail_closed() -> None:
    req = build_request(**_req_kwargs())
    dirty = dict(req)
    dirty["document_type"] = "sample-brain.analysis-headless-run.v0"
    with pytest.raises(AnalysisHeadlessRunError, match="document_type"):
        validate_request(dirty)
    dirty2 = dict(req)
    dirty2["artifact_version"] = "9.9.9"
    with pytest.raises(AnalysisHeadlessRunError, match="artifact_version"):
        validate_request(dirty2)
    assert req["document_type"] == DOCUMENT_TYPE
    assert req["artifact_version"] == ARTIFACT_VERSION


def test_missing_benchmark_and_candidate_identities_fail_closed() -> None:
    with pytest.raises(AnalysisHeadlessRunError, match="benchmark_id|non-empty"):
        build_request(**_req_kwargs(benchmark_id=""))
    with pytest.raises(AnalysisHeadlessRunError, match="baseline|required"):
        build_request(
            **_req_kwargs(
                baseline_candidate_id=None,
                baseline_config_fingerprint=None,
            )
        )
    with pytest.raises(AnalysisHeadlessRunError, match="current|required"):
        build_request(
            **_req_kwargs(
                current_candidate_id=None,
                current_config_fingerprint=None,
            )
        )


def test_unsupported_partition_role_fail_closed() -> None:
    with pytest.raises(AnalysisHeadlessRunError, match="unsupported partition"):
        preflight_operation_partition(operation="compare", partition_role="production")
    with pytest.raises(AnalysisHeadlessRunError, match="unsupported partition"):
        build_request(**_req_kwargs(partition_role="prod"))


# ---------------------------------------------------------------------------
# Status vocabulary / no fake success / fingerprints
# ---------------------------------------------------------------------------


def test_hold_and_controlled_failure_are_not_success() -> None:
    req = build_request(**_req_kwargs())
    hold = build_result(
        **_res_kwargs(
            req,
            run_status="hold",
            domain_artifact_id=None,
            domain_artifact_fingerprint=None,
            error_code="INSUFFICIENT_EVIDENCE",
            error_detail="hold for evidence",
        )
    )
    fail = build_result(
        **_res_kwargs(
            req,
            run_status="controlled_failure",
            domain_artifact_id=None,
            domain_artifact_fingerprint=None,
            error_code="ADAPTER_INPUT_INVALID",
            error_detail="missing members",
        )
    )
    assert hold["run_status"] == "hold"
    assert fail["run_status"] == "controlled_failure"
    assert hold["run_status"] != "completed"
    assert fail["run_status"] != "completed"
    assert "domain_artifact" not in hold
    assert "domain_artifact" not in fail
    assert hold["error"]["code"]
    assert fail["error"]["code"]


def test_controlled_failure_stub_adapter_no_fake_success() -> None:
    stub = _ControlledFailureStubAdapter()
    req = build_request(**_req_kwargs(adapter_id=stub.adapter_id))
    result = stub.run(req)
    assert result["run_status"] == "controlled_failure"
    assert "domain_artifact" not in result
    assert "metrics" not in result
    assert "metric_values" not in result
    assert result["production_authorized"] is False


def test_no_fake_zero_metrics_on_completed_result() -> None:
    req = build_request(**_req_kwargs())
    result = build_result(**_res_kwargs(req))
    assert "metrics" not in result
    assert "metric_values" not in result
    with pytest.raises(AnalysisHeadlessRunError, match="forbidden|metrics"):
        build_result(**_res_kwargs(req, extra_fields={"metrics": {"score": 0.0}}))
    with pytest.raises(AnalysisHeadlessRunError, match="forbidden|metric_values"):
        build_result(
            **_res_kwargs(req, extra_fields={"metric_values": {"score": 0.0}})
        )


def test_deterministic_request_and_result_fingerprints() -> None:
    a = build_request(**_req_kwargs())
    b = build_request(**_req_kwargs())
    assert a["request_fingerprint"] == b["request_fingerprint"]
    assert a["request_fingerprint"] == request_semantic_fingerprint(a)
    assert serialize_request(a) == serialize_request(b)

    ra = build_result(**_res_kwargs(a))
    rb = build_result(**_res_kwargs(b))
    assert ra["result_fingerprint"] == rb["result_fingerprint"]
    assert ra["result_fingerprint"] == result_semantic_fingerprint(ra)
    assert serialize_result(ra) == serialize_result(rb)


def test_ready_status_rejected_as_fake_success_vocabulary() -> None:
    req = build_request(**_req_kwargs())
    with pytest.raises(AnalysisHeadlessRunError, match="unsupported run_status"):
        build_result(**_res_kwargs(req, run_status="ready"))


# ---------------------------------------------------------------------------
# #956 / #1043 regression compatibility (import-only / boundary)
# ---------------------------------------------------------------------------


def test_headless_reuses_956_fingerprint_helper() -> None:
    """Semantic fingerprints must match #956 ``fingerprint`` over semantic payload."""
    from src.analysis_headless_run import (
        request_semantic_payload,
        result_semantic_payload,
    )

    req = build_request(**_req_kwargs())
    assert request_semantic_fingerprint(req) == fingerprint(request_semantic_payload(req))
    result = build_result(**_res_kwargs(req))
    assert result_semantic_fingerprint(result) == fingerprint(
        result_semantic_payload(result)
    )


def test_1043_decision_fields_remain_outside_headless_result() -> None:
    """#1043 may own decision_token/next_action; headless results must never emit them."""
    req = build_request(**_req_kwargs())
    for status, err in (
        ("completed", {}),
        (
            "hold",
            {
                "domain_artifact_id": None,
                "domain_artifact_fingerprint": None,
                "error_code": "INSUFFICIENT_EVIDENCE",
                "error_detail": "hold",
            },
        ),
        (
            "controlled_failure",
            {
                "domain_artifact_id": None,
                "domain_artifact_fingerprint": None,
                "error_code": "ADAPTER_INPUT_INVALID",
                "error_detail": "fail",
            },
        ),
    ):
        result = build_result(**_res_kwargs(req, run_status=status, **err))
        assert "decision_token" not in result
        assert "next_action" not in result
        assert result["production_authorized"] is False
