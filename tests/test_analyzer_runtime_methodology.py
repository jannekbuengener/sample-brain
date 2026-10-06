"""Frozen tests for analyzer runtime methodology v1 (#958).

DOCS -> TESTS -> TEST FREEZE -> IMPLEMENTATION.
These assertions define the contract; do not weaken them to fit broken code.
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from src import analyzer_runtime_methodology as arm


def test_methodology_constants_match_docs() -> None:
    assert arm.METHODOLOGY_ID == "sample_brain.analyzer_runtime_methodology.v1"
    assert arm.SCHEMA_VERSION == "1.0.0"
    assert arm.DOCUMENT_TYPE == "sample_brain.analyzer_runtime_observation.v1"
    assert arm.DEFAULT_STEADY_WARMUP_COUNT == 2
    assert arm.DEFAULT_MEASURED_REPETITIONS == 11
    assert arm.MIN_SAMPLES_P50 == 1
    assert arm.MIN_SAMPLES_P95 == 5
    assert arm.MIN_SAMPLES_P99 == 100


def test_percentile_gates_and_reuse_measurement_stats() -> None:
    # Empty / insufficient -> null, never fabricated 0.0 for missing aggregates.
    empty = arm.aggregate_ok_runtimes([])
    assert empty["ok_count"] == 0
    assert empty["p50_ms"] is None
    assert empty["p95_ms"] is None
    assert empty["p99_ms"] is None
    assert empty["throughput_items_per_s"] is None

    four = arm.aggregate_ok_runtimes([10.0, 20.0, 30.0, 40.0])
    assert four["ok_count"] == 4
    assert four["p50_ms"] == pytest.approx(25.0)
    assert four["p95_ms"] is None  # needs >= 5
    assert four["p99_ms"] is None

    five = arm.aggregate_ok_runtimes([10.0, 20.0, 30.0, 40.0, 50.0])
    assert five["p50_ms"] == pytest.approx(30.0)
    assert five["p95_ms"] is not None
    assert five["p99_ms"] is None  # needs >= 100

    # Deterministic reuse of measurement.stats.percentile
    from src.measurement.stats import percentile

    vals = [float(i) for i in range(1, 101)]
    big = arm.aggregate_ok_runtimes(vals)
    assert big["p99_ms"] == pytest.approx(percentile(vals, 99))
    assert big["throughput_items_per_s"] == pytest.approx(100.0 / (sum(vals) / 1000.0))


def test_non_ok_runtime_never_fabricated_zero() -> None:
    assert arm.sanitize_runtime_ms(status="missing", runtime_ms=None) is None
    assert arm.sanitize_runtime_ms(status="missing", runtime_ms=0.0) is None
    assert arm.sanitize_runtime_ms(status="failed", runtime_ms=0.0) is None
    assert arm.sanitize_runtime_ms(status="timeout", runtime_ms=0.0) is None
    assert arm.sanitize_runtime_ms(status="fallback", runtime_ms=0.0) is None
    assert arm.sanitize_runtime_ms(status="failed", runtime_ms=12.5) == pytest.approx(12.5)
    assert arm.sanitize_runtime_ms(status="ok", runtime_ms=0.0) == pytest.approx(0.0)


def test_cold_vs_steady_warmup_policy() -> None:
    calls: list[str] = []

    def probe() -> dict[str, Any]:
        calls.append("x")
        return {"status": "ok"}

    cold = arm.measure_callable(
        probe,
        mode="cold",
        measured_repetitions=3,
        analyzer_id="t.cold",
        analyzer_revision="r1",
        backend_id="synthetic",
        input_bucket="synthetic_unit",
        record_set_id="cold-proof",
    )
    assert cold["mode"] == "cold"
    assert cold["warmup_count"] == 0
    assert len(cold["warmup_runs"]) == 0
    assert len(cold["measured_runs"]) == 3
    assert len(calls) == 3

    calls.clear()
    steady = arm.measure_callable(
        probe,
        mode="steady",
        warmup_count=2,
        measured_repetitions=3,
        analyzer_id="t.steady",
        analyzer_revision="r1",
        backend_id="synthetic",
        input_bucket="synthetic_unit",
        record_set_id="steady-proof",
    )
    assert steady["mode"] == "steady"
    assert steady["warmup_count"] == 2
    assert len(steady["warmup_runs"]) == 2
    assert len(steady["measured_runs"]) == 3
    assert len(calls) == 5
    # Warm-up timings must not enter ok aggregates.
    assert steady["aggregates"]["ok_count"] == 3


def test_timeout_and_failure_keep_explicit_status() -> None:
    def boom() -> dict[str, Any]:
        raise RuntimeError("analyzer blew up")

    failed = arm.measure_callable(
        boom,
        mode="cold",
        measured_repetitions=1,
        analyzer_id="t.fail",
        analyzer_revision="r1",
        backend_id="synthetic",
        input_bucket="synthetic_unit",
        record_set_id="fail-proof",
    )
    run = failed["measured_runs"][0]
    assert run["status"] == "failed"
    assert run["runtime_ms"] is None or run["runtime_ms"] > 0
    assert run["runtime_ms"] != 0
    assert failed["aggregates"]["p50_ms"] is None

    def slow() -> dict[str, Any]:
        time.sleep(0.05)
        return {"status": "ok"}

    timed = arm.measure_callable(
        slow,
        mode="cold",
        measured_repetitions=1,
        timeout_ms=1.0,
        analyzer_id="t.timeout",
        analyzer_revision="r1",
        backend_id="synthetic",
        input_bucket="synthetic_unit",
        record_set_id="timeout-proof",
    )
    t_run = timed["measured_runs"][0]
    assert t_run["status"] == "timeout"
    assert t_run["runtime_ms"] is None or t_run["runtime_ms"] > 0
    assert t_run["runtime_ms"] != 0


def test_provenance_fields_are_portable() -> None:
    result = arm.measure_callable(
        lambda: {"status": "ok"},
        mode="cold",
        measured_repetitions=1,
        analyzer_id="t.prov",
        analyzer_revision="rev-abc",
        analyzer_config={"bpm_normalization": "none"},
        backend_id="noop",
        dependency_versions={"numpy": "1.26.0"},
        input_bucket="synthetic_unit",
        record_set_id="prov-proof",
    )
    for key in (
        "document_type",
        "schema_version",
        "methodology_id",
        "methodology_version",
        "mode",
        "analyzer_id",
        "analyzer_revision",
        "analyzer_config",
        "backend_id",
        "dependency_versions",
        "input_bucket",
        "record_set_id",
        "warmup_count",
        "measured_repetitions",
        "timeout_ms",
        "aggregates",
        "measured_runs",
    ):
        assert key in result
    assert result["document_type"] == arm.DOCUMENT_TYPE
    assert result["methodology_id"] == arm.METHODOLOGY_ID
    blob = arm.to_portable_json(result)
    assert "Users" not in blob
    assert ":\\" not in blob
    assert "/home/" not in blob


def test_two_shape_proof_cases() -> None:
    light = arm.measure_proof_lightweight(mode="steady", measured_repetitions=5)
    assert light["analyzer_id"] == "proof.lightweight_features"
    assert light["aggregates"]["ok_count"] == 5
    assert light["aggregates"]["p50_ms"] is not None
    assert light["aggregates"]["p95_ms"] is not None
    assert all(r["status"] == "ok" for r in light["measured_runs"])

    # Cold(n=1) keeps startup in the only measured sample; steady warm-up discards it.
    cold_fb = arm.measure_proof_fallback_startup(mode="cold", measured_repetitions=1, enable_backend=True)
    steady_fb = arm.measure_proof_fallback_startup(mode="steady", measured_repetitions=5, enable_backend=True)
    assert cold_fb["analyzer_id"] == "proof.optional_backend_startup"
    assert cold_fb["aggregates"]["p50_ms"] is not None
    assert steady_fb["aggregates"]["p50_ms"] is not None
    assert cold_fb["aggregates"]["p50_ms"] > steady_fb["aggregates"]["p50_ms"]

    disabled = arm.measure_proof_fallback_startup(
        mode="cold",
        measured_repetitions=2,
        enable_backend=False,
    )
    assert all(r["status"] == "fallback" for r in disabled["measured_runs"])
    assert all(r["runtime_ms"] is None or r["runtime_ms"] > 0 for r in disabled["measured_runs"])
    assert all(r["runtime_ms"] != 0 for r in disabled["measured_runs"])
    assert disabled["aggregates"]["ok_count"] == 0
    assert disabled["aggregates"]["p50_ms"] is None
