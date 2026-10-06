"""AQ5 retrieval-path baseline on frozen relevance benchmark (#1010).

Measures current product-reachable retrieval/ranking paths against
``sample-brain.aq5.relevance.adr0005-golden.v1`` with separate reporting
planes for relevance, ANN/reference ranking equivalence, and operational
latency. No search/embedding/ANN algorithm changes and no promotion.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from .analyzer_runtime_methodology import (
    METHODOLOGY_ID as RUNTIME_METHODOLOGY_ID,
)
from .analyzer_runtime_methodology import (
    aggregate_ok_runtimes,
    sanitize_runtime_ms,
)
from .aq5_relevance_benchmark import (
    BENCHMARK_ID,
    TIER_A_SUITE_RELPATH,
    TIER_B_SUITE_RELPATH,
    assert_work_dir_outside_repo,
    audit_aq5_relevance_benchmark,
    build_aq5_relevance_benchmark_manifest,
)
from .benchmark_search_quality import (
    QueryEvalResult,
    run_search_quality_benchmark,
)
from .embed import EmbeddingBackendUnavailableError
from .search_eval import (
    failure_bucket_counts,
    negatives_in_top_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)

DOCUMENT_TYPE = "sample-brain.aq5.retrieval-baseline.v1"
SCHEMA_VERSION = "1.0.0"
EXIT_MEASURED = "AQ5_RETRIEVAL_BASELINE_MEASURED"
EXIT_PARTIAL = "AQ5_RETRIEVAL_BASELINE_PARTIAL_HOLD"
EXIT_INCOMPLETE = "AQ5_RETRIEVAL_BASELINE_INCOMPLETE"

CANDIDATE_NUMPY_TIER_A = "sample-brain.aq5.path.numpy.tier_a.vector_filter_hybrid"
CANDIDATE_NUMPY_TIER_B_TEXT = "sample-brain.aq5.path.numpy.tier_b.text_clap"
CANDIDATE_NUMPY_TIER_B_AUDIO = "sample-brain.aq5.path.numpy.tier_b.audio_clap"
CANDIDATE_SQLITE_VEC_ANN = "sample-brain.aq5.path.sqlite_vec.ann_vs_numpy"
CANDIDATE_HISTORICAL_VOCAL_SPIKE = "sample-brain.aq5.path.historical.vocal_proxy_spike"

NUMPY_TIER_A_SURFACE = (
    "src.search.collect_search_hits + NumpySearchBackend "
    "(Tier-A golden_v1 vector/filter/hybrid)"
)
NUMPY_TIER_B_TEXT_SURFACE = (
    "src.search.collect_search_hits + CLAP embed_text + NumpySearchBackend"
)
NUMPY_TIER_B_AUDIO_SURFACE = (
    "src.search.collect_search_hits + CLAP embed_audio + NumpySearchBackend"
)
SQLITE_VEC_SURFACE = (
    "src.search_backend.SqliteVecSearchBackend vs NumPy reference "
    "(ranking equivalence plane only; no promotion)"
)
VOCAL_SPIKE_SURFACE = (
    "tests/fixtures/search_quality/golden_v2_clap_vocal_proxy_spike.yaml"
)

PARTITION_POLICY = {
    "CALIBRATION": "DEVELOPMENT/CALIBRATION",
    "TEST": "TEST/HOLDOUT",
}

_HOLD_STUBS: tuple[dict[str, str], ...] = (
    {"item": "graded_relevance_ndcg", "status": "HOLD"},
    {"item": "vocal_no_vocal_production_claim", "status": "HOLD"},
    {"item": "genre_mood_production_claim", "status": "HOLD"},
    {"item": "vocal_proxy_spike_suite", "status": "HOLD"},
    {"item": "private_producer_reality_check_queries", "status": "HOLD"},
)

_REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[1]


def candidate_path_inventory() -> list[dict[str, Any]]:
    """Stable candidate IDs for product-reachable and explicitly held paths."""
    return [
        {
            "candidate_id": CANDIDATE_NUMPY_TIER_A,
            "plane": "aq5.retrieval",
            "product_reachable": True,
            "default_promotion": True,
            "surface": NUMPY_TIER_A_SURFACE,
            "suite": "tier_a",
            "modes": ["vector", "filter", "hybrid"],
            "status": "pending",
        },
        {
            "candidate_id": CANDIDATE_NUMPY_TIER_B_TEXT,
            "plane": "aq5.retrieval",
            "product_reachable": True,
            "default_promotion": True,
            "surface": NUMPY_TIER_B_TEXT_SURFACE,
            "suite": "tier_b",
            "modes": ["text"],
            "status": "pending",
        },
        {
            "candidate_id": CANDIDATE_NUMPY_TIER_B_AUDIO,
            "plane": "aq5.retrieval",
            "product_reachable": True,
            "default_promotion": True,
            "surface": NUMPY_TIER_B_AUDIO_SURFACE,
            "suite": "tier_b",
            "modes": ["audio"],
            "status": "pending",
        },
        {
            "candidate_id": CANDIDATE_SQLITE_VEC_ANN,
            "plane": "aq5.ranking",
            "product_reachable": True,
            "default_promotion": False,
            "surface": SQLITE_VEC_SURFACE,
            "suite": "shared_query_set",
            "modes": ["ann_vs_numpy"],
            "status": "pending",
        },
        {
            "candidate_id": CANDIDATE_HISTORICAL_VOCAL_SPIKE,
            "plane": "aq5.retrieval",
            "product_reachable": False,
            "default_promotion": False,
            "surface": VOCAL_SPIKE_SURFACE,
            "suite": "vocal_proxy_spike",
            "modes": [],
            "status": "HOLD",
            "reason": (
                "HOLD_VOCAL_PROXY_FAILED historical spike excluded from "
                f"{BENCHMARK_ID}; not an active AQ5 baseline path"
            ),
        },
    ]


def score_retrieval_query(
    *,
    ranked_ids: list[int],
    relevant_ids: set[int],
    negative_ids: set[int],
) -> dict[str, Any]:
    """Binary relevance metrics per AQ5 KPI; NDCG remains HOLD without grades."""
    return {
        "precision_at_1": precision_at_k(ranked_ids, relevant_ids, 1),
        "precision_at_5": precision_at_k(ranked_ids, relevant_ids, 5),
        "precision_at_10": precision_at_k(ranked_ids, relevant_ids, 10),
        "recall_at_1": recall_at_k(ranked_ids, relevant_ids, 1),
        "recall_at_5": recall_at_k(ranked_ids, relevant_ids, 5),
        "recall_at_10": recall_at_k(ranked_ids, relevant_ids, 10),
        "mrr": reciprocal_rank(ranked_ids, relevant_ids),
        "hit_rate_at_1": (
            1.0 if any(sid in relevant_ids for sid in ranked_ids[:1]) else 0.0
        ),
        "hit_rate_at_5": (
            1.0 if any(sid in relevant_ids for sid in ranked_ids[:5]) else 0.0
        ),
        "hit_rate_at_10": (
            1.0 if any(sid in relevant_ids for sid in ranked_ids[:10]) else 0.0
        ),
        "hard_negative_fp_at_5": (
            1.0 if negatives_in_top_k(ranked_ids, negative_ids, 5) > 0 else 0.0
        ),
        "hard_negative_count_at_5": float(
            negatives_in_top_k(ranked_ids, negative_ids, 5)
        ),
        "ndcg_at_10": None,
    }


def separate_reporting_planes(
    *,
    retrieval: dict[str, Any],
    ranking: dict[str, Any],
    operational: dict[str, Any],
) -> dict[str, Any]:
    """Keep relevance, ranking stability, and latency on disjoint planes."""
    return {
        "aq5.retrieval": dict(retrieval),
        "aq5.ranking": dict(ranking),
        "operational": dict(operational),
    }


def _assert_output_outside_repo(output_path: Path, root: Path) -> None:
    assert_work_dir_outside_repo(
        output_path.parent if output_path.parent != output_path else output_path,
        root,
    )
    try:
        output_path.resolve().relative_to(root.resolve())
    except ValueError:
        return
    raise ValueError(f"output path must be outside repo: {output_path.resolve()}")


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _aggregate_query_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [r for r in rows if r.get("error") is None and r.get("metrics")]
    if not scored:
        return {
            "query_count": 0,
            "error_count": sum(1 for r in rows if r.get("error")),
            "mean_precision_at_1": None,
            "mean_precision_at_5": None,
            "mean_precision_at_10": None,
            "mean_recall_at_1": None,
            "mean_recall_at_5": None,
            "mean_recall_at_10": None,
            "mean_mrr": None,
            "mean_hit_rate_at_1": None,
            "mean_hit_rate_at_5": None,
            "mean_hit_rate_at_10": None,
            "mean_hard_negative_fp_at_5": None,
            "ndcg_at_10": None,
        }

    def col(key: str) -> list[float]:
        return [float(r["metrics"][key]) for r in scored]

    return {
        "query_count": len(scored),
        "error_count": sum(1 for r in rows if r.get("error")),
        "mean_precision_at_1": _mean(col("precision_at_1")),
        "mean_precision_at_5": _mean(col("precision_at_5")),
        "mean_precision_at_10": _mean(col("precision_at_10")),
        "mean_recall_at_1": _mean(col("recall_at_1")),
        "mean_recall_at_5": _mean(col("recall_at_5")),
        "mean_recall_at_10": _mean(col("recall_at_10")),
        "mean_mrr": _mean(col("mrr")),
        "mean_hit_rate_at_1": _mean(col("hit_rate_at_1")),
        "mean_hit_rate_at_5": _mean(col("hit_rate_at_5")),
        "mean_hit_rate_at_10": _mean(col("hit_rate_at_10")),
        "mean_hard_negative_fp_at_5": _mean(col("hard_negative_fp_at_5")),
        "ndcg_at_10": None,
    }


def _group_rows(
    rows: list[dict[str, Any]],
    key: str,
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get(key) or "unknown"), []).append(row)
    return {
        group: {
            "aggregate": _aggregate_query_metrics(group_rows),
            "failure_buckets": failure_bucket_counts(
                [str(r.get("failure_bucket") or "error") for r in group_rows]
            ),
            "query_count": len(group_rows),
        }
        for group, group_rows in sorted(grouped.items())
    }


def _tier_a_mode_label(query_id: str, mode: str, has_filters: bool, has_hybrid: bool) -> str:
    if has_hybrid:
        return "hybrid"
    if has_filters:
        return "filter"
    return mode or "vector"


def _query_meta_from_suite(suite: dict[str, Any]) -> dict[str, dict[str, Any]]:
    meta: dict[str, dict[str, Any]] = {}
    for raw in suite.get("queries") or []:
        qid = str(raw["id"])
        meta[qid] = {
            "filters": bool(raw.get("filters")),
            "hybrid": bool(raw.get("hybrid")),
            "relevant_sample_ids": [int(x) for x in (raw.get("relevant_sample_ids") or [])],
            "negative_sample_ids": [int(x) for x in (raw.get("negative_sample_ids") or [])],
            "query_class": raw.get("query_class"),
            "mode": str(raw.get("mode") or "vector"),
        }
    return meta


def _rows_from_benchmark(
    *,
    suite_key: str,
    query_results: tuple[QueryEvalResult, ...],
    suite_meta: dict[str, dict[str, Any]],
    identity_by_key: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in query_results:
        query_key = f"{suite_key}:{result.query_id}"
        identity = identity_by_key.get(query_key)
        if identity is None:
            continue
        meta = suite_meta.get(result.query_id) or {}
        relevant = set(identity["relevant_sample_ids"])
        negatives = set(identity["negative_sample_ids"])
        if result.error:
            metrics = None
            failure_bucket = "error"
        else:
            metrics = score_retrieval_query(
                ranked_ids=list(result.ranked_ids),
                relevant_ids=relevant,
                negative_ids=negatives,
            )
            failure_bucket = result.failure_bucket
        mode = (
            _tier_a_mode_label(
                result.query_id,
                str(result.mode),
                bool(meta.get("filters")),
                bool(meta.get("hybrid")),
            )
            if suite_key == "tier_a"
            else str(result.mode)
        )
        family = str(
            identity.get("query_family")
            or result.query_class
            or ("tier_a_pipeline" if suite_key == "tier_a" else "unknown")
        )
        if suite_key == "tier_a":
            family = "tier_a_pipeline"
        rows.append(
            {
                "query_key": query_key,
                "query_id": result.query_id,
                "suite": suite_key,
                "split": identity["split"],
                "mode": mode,
                "query_family": family,
                "ranked_ids": list(result.ranked_ids) if not result.error else [],
                "metrics": metrics,
                "failure_bucket": failure_bucket,
                "error": result.error,
                "filter_compliance": result.filter_compliance,
                "passed_must_recall": result.passed_must_recall,
                "negatives_in_top5": result.negatives_in_top5,
                "candidate_id": (
                    CANDIDATE_NUMPY_TIER_A
                    if suite_key == "tier_a"
                    else (
                        CANDIDATE_NUMPY_TIER_B_TEXT
                        if mode == "text"
                        else CANDIDATE_NUMPY_TIER_B_AUDIO
                    )
                ),
            }
        )
    return rows


def _build_split_block(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "aggregate": _aggregate_query_metrics(rows),
        "by_query_family": _group_rows(rows, "query_family"),
        "by_mode": _group_rows(rows, "mode"),
        "failure_buckets": failure_bucket_counts(
            [str(r.get("failure_bucket") or "error") for r in rows]
        ),
        "query_count": len(rows),
        "error_count": sum(1 for r in rows if r.get("error")),
    }


def _sqlite_vec_available() -> bool:
    try:
        import sqlite_vec  # noqa: F401

        return True
    except Exception:
        return False


def _compare_ranked_passes(
    first: list[dict[str, Any]],
    second: list[dict[str, Any]],
) -> dict[str, Any]:
    by_key_a = {r["query_key"]: r for r in first if r.get("error") is None}
    by_key_b = {r["query_key"]: r for r in second if r.get("error") is None}
    shared = sorted(set(by_key_a) & set(by_key_b))
    if not shared:
        return {
            "status": "HOLD",
            "reason": "no shared successful queries across determinism passes",
            "tie_order_checked": False,
        }
    mismatches = [
        key
        for key in shared
        if by_key_a[key].get("ranked_ids") != by_key_b[key].get("ranked_ids")
    ]
    return {
        "status": "measured",
        "tie_order_checked": True,
        "comparable_query_count": len(shared),
        "equal_ordered_projections": len(mismatches) == 0,
        "mismatch_query_keys": mismatches[:20],
        "contract_ref": "docs/ANALYZER_SEMANTIC_DETERMINISM_V1.md",
    }


def _measure_operational_latency(
    *,
    work_dir: Path,
    suite_path: Path,
    measured_repetitions: int,
) -> dict[str, Any]:
    """Operational plane only — never folded into relevance (#958 consume)."""
    runtimes_ms: list[float] = []
    statuses: list[str] = []
    for idx in range(max(1, measured_repetitions)):
        started = time.perf_counter_ns()
        try:
            run_search_quality_benchmark(
                suite_path, work_dir=work_dir / f"runtime_pass_{idx}"
            )
            status = "ok"
        except Exception:
            status = "failed"
        elapsed = (time.perf_counter_ns() - started) / 1_000_000
        runtime_ms = sanitize_runtime_ms(status=status, runtime_ms=elapsed)
        statuses.append(status)
        if status == "ok" and runtime_ms is not None:
            runtimes_ms.append(float(runtime_ms))

    aggregates = aggregate_ok_runtimes(runtimes_ms)
    return {
        "methodology_id": RUNTIME_METHODOLOGY_ID,
        "methodology_ref": "docs/benchmarks/ANALYZER_RUNTIME_METHODOLOGY_V1.md",
        "plane": "operational",
        "input_bucket": "synthetic_unit",
        "record_set_id": "aq5.tier_a.golden_v1.suite_wall",
        "note": (
            "Suite-wall timing for harness reproducibility only; not a relevance "
            "substitute and not combined with aq5.retrieval metrics"
        ),
        "attempt_count": len(statuses),
        "status_counts": dict(Counter(statuses)),
        "p50_ms": aggregates["p50_ms"],
        "p95_ms": aggregates["p95_ms"],
        "p99_ms": aggregates["p99_ms"],
        "ok_count": aggregates["ok_count"],
    }


def run_aq5_retrieval_baseline(
    *,
    work_dir: Path | str,
    output_path: Path | str,
    repo_root: Path | str | None = None,
    include_tier_b: bool = True,
    include_runtime: bool = True,
    include_sqlite_vec: bool = True,
    runtime_repetitions: int = 5,
) -> dict[str, Any]:
    """Measure current retrieval paths on the frozen AQ5 query set."""
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT_DEFAULT
    work = Path(work_dir)
    out = Path(output_path)

    assert_work_dir_outside_repo(work, root)
    _assert_output_outside_repo(out, root)
    work.mkdir(parents=True, exist_ok=True)

    audit = audit_aq5_relevance_benchmark(repo_root=root)
    manifest = build_aq5_relevance_benchmark_manifest(repo_root=root)
    identity_by_key = {q["query_key"]: q for q in manifest["queries"]}

    inventory = candidate_path_inventory()
    path_status = {row["candidate_id"]: dict(row) for row in inventory}

    all_rows: list[dict[str, Any]] = []
    tier_a_pass_a: list[dict[str, Any]] = []
    tier_a_pass_b: list[dict[str, Any]] = []

    # --- Tier-A NumPy reference (always attempted) ---
    tier_a_suite_path = root / TIER_A_SUITE_RELPATH
    try:
        from .benchmark_search_quality import load_search_quality_suite

        tier_a_suite = load_search_quality_suite(tier_a_suite_path)
        tier_a_meta = _query_meta_from_suite(tier_a_suite)
        first = run_search_quality_benchmark(
            tier_a_suite_path, work_dir=work / "tier_a_pass_a"
        )
        second = run_search_quality_benchmark(
            tier_a_suite_path, work_dir=work / "tier_a_pass_b"
        )
        tier_a_pass_a = _rows_from_benchmark(
            suite_key="tier_a",
            query_results=first.query_results,
            suite_meta=tier_a_meta,
            identity_by_key=identity_by_key,
        )
        tier_a_pass_b = _rows_from_benchmark(
            suite_key="tier_a",
            query_results=second.query_results,
            suite_meta=tier_a_meta,
            identity_by_key=identity_by_key,
        )
        all_rows.extend(tier_a_pass_a)
        path_status[CANDIDATE_NUMPY_TIER_A]["status"] = (
            "measured"
            if any(r.get("error") is None for r in tier_a_pass_a)
            else "HOLD"
        )
        if path_status[CANDIDATE_NUMPY_TIER_A]["status"] != "measured":
            path_status[CANDIDATE_NUMPY_TIER_A]["reason"] = "Tier-A queries failed"
    except Exception as exc:
        path_status[CANDIDATE_NUMPY_TIER_A]["status"] = "HOLD"
        path_status[CANDIDATE_NUMPY_TIER_A]["reason"] = type(exc).__name__

    # --- Tier-B CLAP text/audio ---
    # Prefer attempting the product path over the optional-import probe: on
    # Windows ``_clap_available()`` child probes can false-negative while the
    # in-process CLAP backend still works.
    tier_b_attempted = False
    if include_tier_b:
        tier_b_attempted = True
        try:
            tier_b_suite_path = root / TIER_B_SUITE_RELPATH
            from .benchmark_search_quality import load_search_quality_suite

            tier_b_suite = load_search_quality_suite(tier_b_suite_path)
            tier_b_meta = _query_meta_from_suite(tier_b_suite)
            tier_b_result = run_search_quality_benchmark(
                tier_b_suite_path, work_dir=work / "tier_b"
            )
            tier_b_rows = _rows_from_benchmark(
                suite_key="tier_b",
                query_results=tier_b_result.query_results,
                suite_meta=tier_b_meta,
                identity_by_key=identity_by_key,
            )
            all_rows.extend(tier_b_rows)
            text_ok = any(
                r.get("mode") == "text" and r.get("error") is None for r in tier_b_rows
            )
            audio_ok = any(
                r.get("mode") == "audio" and r.get("error") is None for r in tier_b_rows
            )
            path_status[CANDIDATE_NUMPY_TIER_B_TEXT]["status"] = (
                "measured" if text_ok else "HOLD"
            )
            path_status[CANDIDATE_NUMPY_TIER_B_AUDIO]["status"] = (
                "measured" if audio_ok else "HOLD"
            )
            if not text_ok:
                path_status[CANDIDATE_NUMPY_TIER_B_TEXT]["reason"] = (
                    "no successful Tier-B text queries"
                )
            if not audio_ok:
                path_status[CANDIDATE_NUMPY_TIER_B_AUDIO]["reason"] = (
                    "no successful Tier-B audio queries"
                )
        except EmbeddingBackendUnavailableError:
            for cand in (CANDIDATE_NUMPY_TIER_B_TEXT, CANDIDATE_NUMPY_TIER_B_AUDIO):
                path_status[cand]["status"] = "HOLD"
                path_status[cand]["reason"] = "CLAP backend unavailable"
        except Exception as exc:
            for cand in (CANDIDATE_NUMPY_TIER_B_TEXT, CANDIDATE_NUMPY_TIER_B_AUDIO):
                path_status[cand]["status"] = "HOLD"
                path_status[cand]["reason"] = type(exc).__name__
    else:
        for cand in (CANDIDATE_NUMPY_TIER_B_TEXT, CANDIDATE_NUMPY_TIER_B_AUDIO):
            path_status[cand]["status"] = "HOLD"
            path_status[cand]["reason"] = "Tier-B measurement skipped by caller"

    # --- Ranking plane: determinism + ANN HOLD/measure ---
    determinism = _compare_ranked_passes(tier_a_pass_a, tier_a_pass_b)
    ann_block: dict[str, Any] = {
        "candidate_id": CANDIDATE_SQLITE_VEC_ANN,
        "plane": "aq5.ranking",
        "default_promotion": False,
        "reference_path": CANDIDATE_NUMPY_TIER_A,
        "surface": SQLITE_VEC_SURFACE,
    }
    if include_sqlite_vec and _sqlite_vec_available():
        # Optional path exists in product code; full ANN overlap campaign remains
        # owned by SQLITE_VEC_GATE_EVIDENCE. This baseline records availability
        # without promoting or inventing opaque relevance+latency scores.
        ann_block["status"] = "HOLD"
        ann_block["reason"] = (
            "sqlite-vec importable but AQ5 baseline defers numeric overlap campaign "
            "to docs/benchmarks/SQLITE_VEC_GATE_EVIDENCE.md (separate ranking plane); "
            "no promotion in this slice"
        )
        path_status[CANDIDATE_SQLITE_VEC_ANN]["status"] = "HOLD"
        path_status[CANDIDATE_SQLITE_VEC_ANN]["reason"] = ann_block["reason"]
    else:
        ann_block["status"] = "HOLD"
        ann_block["reason"] = (
            "sqlite-vec optional dependency unavailable in this environment; "
            "path remains product-reachable in code but not measured here"
        )
        path_status[CANDIDATE_SQLITE_VEC_ANN]["status"] = "HOLD"
        path_status[CANDIDATE_SQLITE_VEC_ANN]["reason"] = ann_block["reason"]

    path_status[CANDIDATE_HISTORICAL_VOCAL_SPIKE]["status"] = "HOLD"

    splits: dict[str, Any] = {}
    for split_name in ("CALIBRATION", "TEST"):
        split_rows = [r for r in all_rows if r.get("split") == split_name]
        splits[split_name] = _build_split_block(split_rows)

    support_counts = {
        "split": dict(Counter(r["split"] for r in all_rows)),
        "suite": dict(Counter(r["suite"] for r in all_rows)),
        "mode": dict(Counter(r["mode"] for r in all_rows)),
        "query_family": dict(Counter(r["query_family"] for r in all_rows)),
    }

    operational: dict[str, Any]
    if include_runtime and path_status[CANDIDATE_NUMPY_TIER_A]["status"] == "measured":
        operational = _measure_operational_latency(
            work_dir=work / "operational",
            suite_path=tier_a_suite_path,
            measured_repetitions=runtime_repetitions,
        )
    else:
        operational = {
            "methodology_id": RUNTIME_METHODOLOGY_ID,
            "methodology_ref": "docs/benchmarks/ANALYZER_RUNTIME_METHODOLOGY_V1.md",
            "plane": "operational",
            "status": "HOLD",
            "reason": "runtime measurement skipped or Tier-A unavailable",
            "p50_ms": None,
            "p95_ms": None,
            "p99_ms": None,
        }

    planes = separate_reporting_planes(
        retrieval={
            "benchmark_id": BENCHMARK_ID,
            "ndcg_eligibility": "HOLD",
            "relevance_scheme": "binary",
            "k_values": [1, 5, 10],
            "support_counts": support_counts,
            "splits": splits,
            "query_count": len(all_rows),
            "error_count": sum(1 for r in all_rows if r.get("error")),
        },
        ranking={
            "determinism": determinism,
            "ann_vs_reference": ann_block,
        },
        operational=operational,
    )

    tier_a_ok = path_status[CANDIDATE_NUMPY_TIER_A]["status"] == "measured"
    tier_b_text_ok = path_status[CANDIDATE_NUMPY_TIER_B_TEXT]["status"] == "measured"
    tier_b_audio_ok = path_status[CANDIDATE_NUMPY_TIER_B_AUDIO]["status"] == "measured"
    if tier_a_ok and tier_b_text_ok and tier_b_audio_ok:
        exit_status = EXIT_MEASURED
    elif tier_a_ok:
        exit_status = EXIT_PARTIAL
    else:
        exit_status = EXIT_INCOMPLETE

    # Portable query evidence: drop host-ish ranked payload size if huge; keep ids only.
    portable_queries = [
        {
            "query_key": r["query_key"],
            "split": r["split"],
            "suite": r["suite"],
            "mode": r["mode"],
            "query_family": r["query_family"],
            "candidate_id": r["candidate_id"],
            "ranked_ids": r.get("ranked_ids") or [],
            "metrics": r.get("metrics"),
            "failure_bucket": r.get("failure_bucket"),
            "error": r.get("error"),
            "filter_compliance": r.get("filter_compliance"),
            "passed_must_recall": r.get("passed_must_recall"),
            "negatives_in_top5": r.get("negatives_in_top5"),
        }
        for r in all_rows
    ]

    result: dict[str, Any] = {
        "document_type": DOCUMENT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "benchmark_id": BENCHMARK_ID,
        "benchmark_version": manifest.get("benchmark_version"),
        "exit_status": exit_status,
        "partition_policy": dict(PARTITION_POLICY),
        "no_tuning_on_test": True,
        "partition_fingerprint": audit["partition_fingerprint"],
        "query_set_fingerprint": audit["query_set_fingerprint"],
        "candidate_paths": [
            path_status[row["candidate_id"]] for row in inventory
        ],
        "hold_stubs": [dict(item) for item in _HOLD_STUBS],
        "aq5.retrieval": planes["aq5.retrieval"],
        "aq5.ranking": planes["aq5.ranking"],
        "operational": planes["operational"],
        "queries": portable_queries,
        "notes": {
            "plane_separation": (
                "Relevance, ranking/ANN equivalence, and operational latency are "
                "reported on separate planes and never opaque-combined"
            ),
            "tier_b_attempted": tier_b_attempted,
            "default_search_backend": "numpy",
            "sqlite_vec_promotion": False,
        },
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Measure current AQ5 retrieval paths on the frozen relevance "
            "benchmark (external JSON only)."
        )
    )
    parser.add_argument(
        "--work-dir",
        required=True,
        help="External work directory for temp DB/fixtures (outside repo).",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="External JSON output path (outside repo).",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repository root used for outside-repo checks (default: package root).",
    )
    parser.add_argument(
        "--skip-tier-b",
        action="store_true",
        help="Skip Tier-B CLAP text/audio measurement (forces PARTIAL_HOLD).",
    )
    parser.add_argument(
        "--skip-runtime",
        action="store_true",
        help="Skip operational suite-wall latency measurement.",
    )
    parser.add_argument(
        "--skip-sqlite-vec",
        action="store_true",
        help="Skip sqlite-vec availability probe on the ranking plane.",
    )
    parser.add_argument(
        "--runtime-repetitions",
        type=int,
        default=5,
        help="Operational suite-wall repetitions (default: 5).",
    )
    args = parser.parse_args(argv)
    result = run_aq5_retrieval_baseline(
        work_dir=args.work_dir,
        output_path=args.output,
        repo_root=args.repo_root,
        include_tier_b=not args.skip_tier_b,
        include_runtime=not args.skip_runtime,
        include_sqlite_vec=not args.skip_sqlite_vec,
        runtime_repetitions=args.runtime_repetitions,
    )
    print(
        json.dumps(
            {
                "exit_status": result["exit_status"],
                "query_count": result["aq5.retrieval"]["query_count"],
                "candidate_paths": {
                    row["candidate_id"]: row["status"]
                    for row in result["candidate_paths"]
                },
            },
            sort_keys=True,
        )
    )
    return 0 if result["exit_status"] == EXIT_MEASURED else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BENCHMARK_ID",
    "CANDIDATE_HISTORICAL_VOCAL_SPIKE",
    "CANDIDATE_NUMPY_TIER_A",
    "CANDIDATE_NUMPY_TIER_B_AUDIO",
    "CANDIDATE_NUMPY_TIER_B_TEXT",
    "CANDIDATE_SQLITE_VEC_ANN",
    "DOCUMENT_TYPE",
    "EXIT_INCOMPLETE",
    "EXIT_MEASURED",
    "EXIT_PARTIAL",
    "RUNTIME_METHODOLOGY_ID",
    "SCHEMA_VERSION",
    "candidate_path_inventory",
    "run_aq5_retrieval_baseline",
    "score_retrieval_query",
    "separate_reporting_planes",
]
