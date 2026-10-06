"""Common analyzer runtime measurement methodology v1 (#958).

Comparable measurement only — not optimization. Reuses
``src.measurement.stats.percentile`` for aggregate math.
"""

from __future__ import annotations

import json
import platform
import sys
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Any

from .measurement.stats import percentile

METHODOLOGY_ID = "sample_brain.analyzer_runtime_methodology.v1"
SCHEMA_VERSION = "1.0.0"
DOCUMENT_TYPE = "sample_brain.analyzer_runtime_observation.v1"
METHODOLOGY_VERSION = SCHEMA_VERSION

DEFAULT_STEADY_WARMUP_COUNT = 2
DEFAULT_MEASURED_REPETITIONS = 11
MIN_SAMPLES_P50 = 1
MIN_SAMPLES_P95 = 5
MIN_SAMPLES_P99 = 100

STATUS_OK = "ok"
STATUS_TIMEOUT = "timeout"
STATUS_FAILED = "failed"
STATUS_FALLBACK = "fallback"
STATUS_MISSING = "missing"

_NON_OK = frozenset({STATUS_TIMEOUT, STATUS_FAILED, STATUS_FALLBACK, STATUS_MISSING})

AnalyzerCallable = Callable[[], Mapping[str, Any]]
AnalyzerFactory = Callable[[], AnalyzerCallable]


def sanitize_runtime_ms(*, status: str, runtime_ms: float | None) -> float | None:
    """Hard rule: missing/failed/timeout/fallback never publish fabricated 0 ms.

    ``missing`` always forces ``runtime_ms`` to ``null`` (run could not start).
    """
    if runtime_ms is None:
        return None
    if status == STATUS_MISSING:
        return None
    if status in _NON_OK and runtime_ms == 0.0:
        return None
    return float(runtime_ms)


def aggregate_ok_runtimes(ok_runtimes_ms: list[float]) -> dict[str, float | int | None]:
    """Deterministic percentile / throughput aggregates for ok samples only."""
    ok_count = len(ok_runtimes_ms)
    if ok_count == 0:
        return {
            "ok_count": 0,
            "p50_ms": None,
            "p95_ms": None,
            "p99_ms": None,
            "throughput_items_per_s": None,
        }

    p50 = percentile(ok_runtimes_ms, 50) if ok_count >= MIN_SAMPLES_P50 else None
    p95 = percentile(ok_runtimes_ms, 95) if ok_count >= MIN_SAMPLES_P95 else None
    p99 = percentile(ok_runtimes_ms, 99) if ok_count >= MIN_SAMPLES_P99 else None
    total_ms = sum(ok_runtimes_ms)
    throughput = (ok_count / (total_ms / 1000.0)) if total_ms > 0 else None
    return {
        "ok_count": ok_count,
        "p50_ms": p50,
        "p95_ms": p95,
        "p99_ms": p99,
        "throughput_items_per_s": throughput,
    }


def _time_one(
    fn: AnalyzerCallable,
    *,
    timeout_ms: float | None,
) -> dict[str, Any]:
    started = time.perf_counter_ns()
    if timeout_ms is None:
        try:
            payload = dict(fn())
        except Exception as exc:
            elapsed = (time.perf_counter_ns() - started) / 1_000_000
            return {
                "status": STATUS_FAILED,
                "runtime_ms": sanitize_runtime_ms(
                    status=STATUS_FAILED, runtime_ms=elapsed
                ),
                "reason_code": "callable_exception",
                "reason_detail": type(exc).__name__,
            }
    else:
        timeout_s = max(float(timeout_ms) / 1000.0, 0.0)
        # Bounded wait: mark timeout without blocking forever on hung callables.
        # Do not wait=True on shutdown — a timed-out worker may still be running.
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            future = pool.submit(fn)
            try:
                payload = dict(future.result(timeout=timeout_s))
            except FuturesTimeout:
                elapsed = (time.perf_counter_ns() - started) / 1_000_000
                return {
                    "status": STATUS_TIMEOUT,
                    "runtime_ms": sanitize_runtime_ms(
                        status=STATUS_TIMEOUT, runtime_ms=elapsed
                    ),
                    "reason_code": "timeout",
                }
            except Exception as exc:
                elapsed = (time.perf_counter_ns() - started) / 1_000_000
                return {
                    "status": STATUS_FAILED,
                    "runtime_ms": sanitize_runtime_ms(
                        status=STATUS_FAILED, runtime_ms=elapsed
                    ),
                    "reason_code": "callable_exception",
                    "reason_detail": type(exc).__name__,
                }
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    elapsed = (time.perf_counter_ns() - started) / 1_000_000
    status = str(payload.get("status") or STATUS_OK)
    if timeout_ms is not None and elapsed > float(timeout_ms):
        status = STATUS_TIMEOUT
    runtime_ms = sanitize_runtime_ms(status=status, runtime_ms=elapsed)
    out: dict[str, Any] = {
        "status": status,
        "runtime_ms": runtime_ms,
    }
    reason = payload.get("reason_code")
    if reason is not None:
        out["reason_code"] = reason
    return out


def measure_callable(
    fn: AnalyzerCallable | None = None,
    *,
    mode: str,
    analyzer_id: str,
    analyzer_revision: str,
    backend_id: str,
    input_bucket: str,
    record_set_id: str,
    measured_repetitions: int = DEFAULT_MEASURED_REPETITIONS,
    warmup_count: int | None = None,
    timeout_ms: float | None = None,
    analyzer_config: Mapping[str, Any] | None = None,
    dependency_versions: Mapping[str, str] | None = None,
    include_host_hints: bool = False,
    cold_factory: AnalyzerFactory | None = None,
) -> dict[str, Any]:
    """Run warm-up + measured repetitions under the frozen methodology.

    For ``mode="cold"``, pass ``cold_factory`` (a zero-arg factory returning a fresh
    ``AnalyzerCallable``) so each measured sample reinitializes the analyzer.
    When only ``fn`` is supplied in cold mode, the same callable is reused
    (steady-state after the first call) — prefer ``cold_factory`` for true cold.
    """
    if mode not in {"cold", "steady"}:
        raise ValueError("mode must be 'cold' or 'steady'")
    if measured_repetitions < 1:
        raise ValueError("measured_repetitions must be >= 1")
    if fn is None and cold_factory is None:
        raise ValueError("measure_callable requires fn and/or cold_factory")

    if warmup_count is None:
        resolved_warmup = 0 if mode == "cold" else DEFAULT_STEADY_WARMUP_COUNT
    else:
        resolved_warmup = int(warmup_count)
    if mode == "cold" and resolved_warmup != 0:
        raise ValueError("cold mode requires warmup_count == 0")
    if resolved_warmup < 0:
        raise ValueError("warmup_count must be >= 0")

    def _resolve_callable() -> AnalyzerCallable:
        if mode == "cold" and cold_factory is not None:
            return cold_factory()
        if fn is not None:
            return fn
        assert cold_factory is not None
        return cold_factory()

    warmup_runs = [
        _time_one(_resolve_callable(), timeout_ms=timeout_ms)
        for _ in range(resolved_warmup)
    ]
    measured_runs = [
        _time_one(_resolve_callable(), timeout_ms=timeout_ms)
        for _ in range(measured_repetitions)
    ]

    ok_runtimes = [
        float(run["runtime_ms"])
        for run in measured_runs
        if run.get("status") == STATUS_OK and run.get("runtime_ms") is not None
    ]
    aggregates = aggregate_ok_runtimes(ok_runtimes)

    result: dict[str, Any] = {
        "document_type": DOCUMENT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "methodology_id": METHODOLOGY_ID,
        "methodology_version": METHODOLOGY_VERSION,
        "mode": mode,
        "analyzer_id": analyzer_id,
        "analyzer_revision": analyzer_revision,
        "analyzer_config": dict(analyzer_config or {}),
        "backend_id": backend_id,
        "dependency_versions": dict(dependency_versions or {}),
        "input_bucket": input_bucket,
        "record_set_id": record_set_id,
        "warmup_count": resolved_warmup,
        "measured_repetitions": measured_repetitions,
        "timeout_ms": timeout_ms,
        "warmup_runs": warmup_runs,
        "measured_runs": measured_runs,
        "aggregates": aggregates,
    }
    if include_host_hints:
        result["host_hints"] = {
            "python_version": platform.python_version(),
            "platform_system": platform.system(),
        }
    return result


def to_portable_json(result: Mapping[str, Any]) -> str:
    """Serialize without NaN and with stable key order for artifact consumers."""
    return json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"


def _synthetic_feature_work(n: int = 256) -> float:
    """Deterministic lightweight CPU work (no audio I/O, no models)."""
    acc = 0.0
    x = 1.0
    for i in range(n):
        x = (x * 1.0001 + (i % 17)) % 97.0
        acc += x
    return acc


def measure_proof_lightweight(
    *,
    mode: str = "steady",
    measured_repetitions: int = 5,
) -> dict[str, Any]:
    """Proof shape 1: lightweight deterministic analyzer/feature-style path."""

    def _fn() -> dict[str, Any]:
        _synthetic_feature_work()
        return {"status": STATUS_OK}

    return measure_callable(
        _fn,
        mode=mode,
        measured_repetitions=measured_repetitions,
        analyzer_id="proof.lightweight_features",
        analyzer_revision="proof-lightweight-v1",
        analyzer_config={"work_units": 256},
        backend_id="synthetic",
        dependency_versions={"python": f"{sys.version_info.major}.{sys.version_info.minor}"},
        input_bucket="synthetic_unit",
        record_set_id="proof-lightweight-v1",
    )


class _OptionalBackendProbe:
    """Proof shape 2: first-call startup cost + optional fallback."""

    def __init__(self, *, enable_backend: bool) -> None:
        self.enable_backend = enable_backend
        self._started = False

    def __call__(self) -> dict[str, Any]:
        if not self.enable_backend:
            # Tiny non-zero work so elapsed is measurable; status stays fallback.
            _synthetic_feature_work(32)
            return {"status": STATUS_FALLBACK, "reason_code": "optional_backend_disabled"}
        if not self._started:
            time.sleep(0.02)
            self._started = True
        else:
            _synthetic_feature_work(64)
        return {"status": STATUS_OK}


def measure_proof_fallback_startup(
    *,
    mode: str = "cold",
    measured_repetitions: int = 3,
    enable_backend: bool = True,
) -> dict[str, Any]:
    """Proof shape 2: materially different startup / fallback behavior.

    Cold mode uses ``cold_factory`` so every measured sample is a fresh probe
    (true cold), not a warmed instance after the first repetition.
    """
    common = dict(
        measured_repetitions=measured_repetitions,
        analyzer_id="proof.optional_backend_startup",
        analyzer_revision="proof-fallback-startup-v1",
        analyzer_config={"enable_backend": enable_backend, "startup_sleep_s": 0.02},
        backend_id="optional_synthetic" if enable_backend else "fallback",
        dependency_versions={"python": f"{sys.version_info.major}.{sys.version_info.minor}"},
        input_bucket="synthetic_unit",
        record_set_id="proof-optional-backend-v1",
    )
    if mode == "cold":
        return measure_callable(
            mode=mode,
            cold_factory=lambda: _OptionalBackendProbe(enable_backend=enable_backend),
            **common,
        )
    probe = _OptionalBackendProbe(enable_backend=enable_backend)
    return measure_callable(probe, mode=mode, **common)


__all__ = [
    "DEFAULT_MEASURED_REPETITIONS",
    "DEFAULT_STEADY_WARMUP_COUNT",
    "DOCUMENT_TYPE",
    "METHODOLOGY_ID",
    "METHODOLOGY_VERSION",
    "MIN_SAMPLES_P50",
    "MIN_SAMPLES_P95",
    "MIN_SAMPLES_P99",
    "SCHEMA_VERSION",
    "STATUS_FAILED",
    "STATUS_FALLBACK",
    "STATUS_MISSING",
    "STATUS_OK",
    "STATUS_TIMEOUT",
    "aggregate_ok_runtimes",
    "measure_callable",
    "measure_proof_fallback_startup",
    "measure_proof_lightweight",
    "sanitize_runtime_ms",
    "to_portable_json",
]
