"""AQ5 ANN vs NumPy reference ranking delta (#1011).

Measures index/backend approximation loss against an explicit exact/reference
search path on identical Tier-A vectors/queries. Ranking plane stays separate
from semantic retrieval relevance and from operational latency. No promotion.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

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
    assert_work_dir_outside_repo,
    audit_aq5_relevance_benchmark,
    build_aq5_relevance_benchmark_manifest,
)
from .aq5_retrieval_baseline import CANDIDATE_SQLITE_VEC_ANN
from .benchmark_search_quality import (
    _filters_from_mapping,
    _hybrid_from_mapping,
    load_search_quality_suite,
    seed_golden_catalog,
)
from .search import collect_search_hits
from .vec_availability import probe_sqlite_vec
from .vec_index import rebuild_vec0_cache

DOCUMENT_TYPE = "sample-brain.aq5.ann-reference-delta.v1"
SCHEMA_VERSION = "1.0.0"
EXIT_MEASURED = "AQ5_ANN_REFERENCE_DELTA_MEASURED"
EXIT_BACKEND_HOLD = "AQ5_ANN_BACKEND_HOLD"
EXIT_INCOMPLETE = "AQ5_ANN_COMPARISON_INCOMPLETE"

REFERENCE_PATH_ID = "sample-brain.aq5.path.numpy.exact_reference"
APPROX_PATH_ID = CANDIDATE_SQLITE_VEC_ANN

REFERENCE_SURFACE = (
    "src.search.collect_search_hits + NumpySearchBackend "
    "(Tier-A golden_v1; exact/reference ranking path)"
)
APPROX_SURFACE = (
    "src.search.collect_search_hits + SqliteVecSearchBackend after "
    "rebuild_vec0_cache (same Tier-A catalog/embeddings; no promotion)"
)

_HOLD_STUBS: tuple[dict[str, str], ...] = (
    {"item": "graded_relevance_ndcg", "status": "HOLD"},
    {"item": "semantic_relevance_as_ann_proof", "status": "HOLD"},
    {"item": "sqlite_vec_production_promotion", "status": "HOLD"},
    {"item": "opaque_relevance_latency_aggregate", "status": "HOLD"},
    {"item": "private_producer_reality_check_queries", "status": "HOLD"},
    {"item": "issue_74_upstream_ann_release", "status": "HOLD"},
)

_REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[1]


def backend_path_identities() -> list[dict[str, Any]]:
    """Freeze exact/reference and approximate/index path identities."""
    return [
        {
            "path_id": REFERENCE_PATH_ID,
            "role": "exact_reference",
            "plane": "aq5.ranking",
            "product_reachable": True,
            "default_promotion": True,
            "promotion_blocked": False,
            "surface": REFERENCE_SURFACE,
            "backend": "numpy",
        },
        {
            "path_id": APPROX_PATH_ID,
            "role": "approximate_index",
            "plane": "aq5.ranking",
            "product_reachable": True,
            "default_promotion": False,
            "promotion_blocked": True,
            "surface": APPROX_SURFACE,
            "backend": "sqlite-vec",
        },
    ]


def topk_set_overlap(
    reference_ids: list[int],
    approx_ids: list[int],
    *,
    k: int,
) -> float:
    """Set overlap of Top-K IDs vs reference (ranking plane).

    When either path returns fewer than ``k`` hits (common after filters),
    the denominator is the longer returned prefix length so identical short
    result lists score 1.0 rather than looking like approximation loss.
    """
    if k <= 0:
        return 1.0
    ref_list = list(reference_ids[:k])
    approx_list = list(approx_ids[:k])
    denom = max(len(ref_list), len(approx_list))
    if denom == 0:
        return 1.0
    return len(set(ref_list) & set(approx_list)) / float(denom)


def _rank_of(sample_id: int, ranked_ids: list[int]) -> int | None:
    try:
        return ranked_ids.index(sample_id) + 1
    except ValueError:
        return None


def relevant_rank_displacements(
    *,
    reference_ids: list[int],
    approx_ids: list[int],
    relevant_ids: set[int],
) -> list[dict[str, Any]]:
    """Per-relevant-item rank change vs reference (not a relevance quality claim)."""
    rows: list[dict[str, Any]] = []
    for sample_id in sorted(relevant_ids):
        ref_rank = _rank_of(sample_id, reference_ids)
        approx_rank = _rank_of(sample_id, approx_ids)
        if ref_rank is None and approx_rank is None:
            displacement = 0
        elif ref_rank is None or approx_rank is None:
            displacement = None
        else:
            displacement = approx_rank - ref_rank
        rows.append(
            {
                "sample_id": sample_id,
                "reference_rank": ref_rank,
                "approx_rank": approx_rank,
                "displacement": displacement,
            }
        )
    return rows


def ordered_ranking_delta(
    reference_ids: list[int],
    approx_ids: list[int],
) -> dict[str, Any]:
    """Ordered Top-K ranking delta vs reference."""
    limit = max(len(reference_ids), len(approx_ids))
    mismatches = 0
    first_divergence: int | None = None
    for idx in range(limit):
        ref = reference_ids[idx] if idx < len(reference_ids) else None
        approx = approx_ids[idx] if idx < len(approx_ids) else None
        if ref != approx:
            mismatches += 1
            if first_divergence is None:
                first_divergence = idx + 1
    return {
        "identical_ordered_topk": (
            mismatches == 0 and len(reference_ids) == len(approx_ids)
        ),
        "first_divergence_rank": first_divergence,
        "position_mismatch_count": mismatches,
        "reference_len": len(reference_ids),
        "approx_len": len(approx_ids),
    }


def separate_reporting_planes(
    *,
    ranking: dict[str, Any],
    operational: dict[str, Any],
    retrieval_note: dict[str, Any],
) -> dict[str, Any]:
    """Keep ranking, operational latency, and retrieval notes on disjoint planes."""
    return {
        "aq5.ranking": dict(ranking),
        "operational": dict(operational),
        "aq5.retrieval": dict(retrieval_note),
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


def _tier_a_mode_label(mode: str, has_filters: bool, has_hybrid: bool) -> str:
    if has_hybrid:
        return "hybrid"
    if has_filters:
        return "filter"
    return mode or "vector"


def _compare_ordered_passes(
    first: list[dict[str, Any]],
    second: list[dict[str, Any]],
) -> dict[str, Any]:
    by_a = {r["query_id"]: r for r in first if r.get("error") is None}
    by_b = {r["query_id"]: r for r in second if r.get("error") is None}
    shared = sorted(set(by_a) & set(by_b))
    if not shared:
        return {
            "status": "HOLD",
            "reason": "no shared successful queries across determinism passes",
            "tie_order_checked": False,
        }
    mismatches = [
        qid
        for qid in shared
        if by_a[qid].get("ranked_ids") != by_b[qid].get("ranked_ids")
    ]
    return {
        "status": "measured",
        "tie_order_checked": True,
        "comparable_query_count": len(shared),
        "equal_ordered_projections": len(mismatches) == 0,
        "mismatch_query_ids": mismatches[:20],
        "contract_ref": "docs/ANALYZER_SEMANTIC_DETERMINISM_V1.md",
    }


def _run_tier_a_queries(
    *,
    suite: dict[str, Any],
    model_id: int,
    search_backend: str,
) -> list[dict[str, Any]]:
    defaults = suite.get("defaults") or {}
    default_topk = int(defaults.get("topk", 10))
    rows: list[dict[str, Any]] = []
    for raw in suite.get("queries") or []:
        query_id = str(raw["id"])
        mode = str(raw.get("mode") or "vector")
        topk = int(raw.get("topk", default_topk))
        filters = _filters_from_mapping(raw.get("filters"))
        hybrid = _hybrid_from_mapping(raw.get("hybrid"))
        relevant_ids = {int(x) for x in (raw.get("relevant_sample_ids") or [])}
        mode_label = _tier_a_mode_label(
            mode,
            filters is not None and filters.active(),
            hybrid is not None,
        )
        if mode != "vector":
            rows.append(
                {
                    "query_id": query_id,
                    "mode": mode_label,
                    "topk": topk,
                    "ranked_ids": [],
                    "relevant_sample_ids": sorted(relevant_ids),
                    "error": f"unsupported mode for ANN delta: {mode}",
                }
            )
            continue
        query_vector = raw.get("query_vector")
        if query_vector is None:
            rows.append(
                {
                    "query_id": query_id,
                    "mode": mode_label,
                    "topk": topk,
                    "ranked_ids": [],
                    "relevant_sample_ids": sorted(relevant_ids),
                    "error": "missing query_vector",
                }
            )
            continue
        result = collect_search_hits(
            query_vector=np.asarray(query_vector, dtype=np.float32),
            model_id=model_id,
            topk=topk,
            search_backend=search_backend,
            hybrid_query=hybrid,
            search_filters=filters,
        )
        if result.error or result.info:
            rows.append(
                {
                    "query_id": query_id,
                    "mode": mode_label,
                    "topk": topk,
                    "ranked_ids": [],
                    "relevant_sample_ids": sorted(relevant_ids),
                    "error": result.error or result.info,
                }
            )
            continue
        rows.append(
            {
                "query_id": query_id,
                "mode": mode_label,
                "topk": topk,
                "ranked_ids": [hit.sample_id for hit in result.hits],
                "relevant_sample_ids": sorted(relevant_ids),
                "error": None,
            }
        )
    return rows


def _pair_comparisons(
    reference_rows: list[dict[str, Any]],
    approx_rows: list[dict[str, Any]],
    *,
    identity_by_key: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    by_approx = {r["query_id"]: r for r in approx_rows}
    paired: list[dict[str, Any]] = []
    for ref in reference_rows:
        qid = ref["query_id"]
        approx = by_approx.get(qid)
        query_key = f"tier_a:{qid}"
        identity = identity_by_key.get(query_key) or {}
        split = identity.get("split", "UNKNOWN")
        if approx is None:
            paired.append(
                {
                    "query_key": query_key,
                    "query_id": qid,
                    "split": split,
                    "mode": ref.get("mode"),
                    "error": "approximate path missing query",
                    "metrics": None,
                }
            )
            continue
        if ref.get("error") or approx.get("error"):
            paired.append(
                {
                    "query_key": query_key,
                    "query_id": qid,
                    "split": split,
                    "mode": ref.get("mode") or approx.get("mode"),
                    "error": ref.get("error") or approx.get("error"),
                    "metrics": None,
                    "reference_ranked_ids": ref.get("ranked_ids") or [],
                    "approx_ranked_ids": approx.get("ranked_ids") or [],
                }
            )
            continue
        topk = int(ref.get("topk") or approx.get("topk") or 10)
        relevant = set(ref.get("relevant_sample_ids") or [])
        overlap = topk_set_overlap(
            list(ref["ranked_ids"]),
            list(approx["ranked_ids"]),
            k=topk,
        )
        displacements = relevant_rank_displacements(
            reference_ids=list(ref["ranked_ids"]),
            approx_ids=list(approx["ranked_ids"]),
            relevant_ids=relevant,
        )
        abs_disp = [
            abs(int(row["displacement"]))
            for row in displacements
            if row.get("displacement") is not None
        ]
        ordered = ordered_ranking_delta(
            list(ref["ranked_ids"]),
            list(approx["ranked_ids"]),
        )
        paired.append(
            {
                "query_key": query_key,
                "query_id": qid,
                "split": split,
                "mode": ref.get("mode"),
                "topk": topk,
                "error": None,
                "reference_ranked_ids": list(ref["ranked_ids"]),
                "approx_ranked_ids": list(approx["ranked_ids"]),
                "relevant_displacements": displacements,
                "metrics": {
                    "topk_overlap": overlap,
                    "identical_ordered_topk": (
                        1.0 if ordered["identical_ordered_topk"] else 0.0
                    ),
                    "position_mismatch_count": float(
                        ordered["position_mismatch_count"]
                    ),
                    "mean_abs_relevant_displacement": (
                        _mean([float(x) for x in abs_disp]) if abs_disp else 0.0
                    ),
                    "missing_relevant_on_either_path": float(
                        sum(
                            1
                            for row in displacements
                            if row.get("displacement") is None
                        )
                    ),
                },
                "ordered_delta": ordered,
            }
        )
    return paired


def _aggregate_pairs(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [p for p in pairs if p.get("error") is None and p.get("metrics")]
    if not scored:
        return {
            "query_count": 0,
            "error_count": sum(1 for p in pairs if p.get("error")),
            "mean_topk_overlap": None,
            "identical_ordered_topk_rate": None,
            "mean_abs_relevant_displacement": None,
            "mean_position_mismatch_count": None,
        }

    def col(key: str) -> list[float]:
        return [float(p["metrics"][key]) for p in scored]

    return {
        "query_count": len(scored),
        "error_count": sum(1 for p in pairs if p.get("error")),
        "mean_topk_overlap": _mean(col("topk_overlap")),
        "identical_ordered_topk_rate": _mean(col("identical_ordered_topk")),
        "mean_abs_relevant_displacement": _mean(
            col("mean_abs_relevant_displacement")
        ),
        "mean_position_mismatch_count": _mean(col("position_mismatch_count")),
    }


def _group_pairs_by_mode(pairs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for pair in pairs:
        grouped.setdefault(str(pair.get("mode") or "unknown"), []).append(pair)
    return {
        mode: {
            "aggregate": _aggregate_pairs(rows),
            "query_count": len(rows),
            "identical_ordered_topk_count": sum(
                1
                for row in rows
                if row.get("metrics")
                and float(row["metrics"]["identical_ordered_topk"]) >= 1.0
            ),
        }
        for mode, rows in sorted(grouped.items())
    }


def _measure_operational(
    *,
    suite: dict[str, Any],
    model_id: int,
    measured_repetitions: int,
) -> dict[str, Any]:
    """Operational plane only — never folded into ranking quality."""
    defaults = suite.get("defaults") or {}
    default_topk = int(defaults.get("topk", 10))
    vector_queries = [
        raw
        for raw in (suite.get("queries") or [])
        if str(raw.get("mode") or "vector") == "vector" and raw.get("query_vector")
    ]
    if not vector_queries:
        return {
            "methodology_id": RUNTIME_METHODOLOGY_ID,
            "methodology_ref": "docs/benchmarks/ANALYZER_RUNTIME_METHODOLOGY_V1.md",
            "plane": "operational",
            "status": "HOLD",
            "reason": "no vector queries available for operational timing",
            "p50_ms": None,
            "p95_ms": None,
            "p99_ms": None,
        }

    runtimes_ms: list[float] = []
    statuses: list[str] = []
    probe = vector_queries[0]
    query_vector = np.asarray(probe["query_vector"], dtype=np.float32)
    topk = int(probe.get("topk", default_topk))
    for _ in range(max(1, measured_repetitions)):
        started = time.perf_counter_ns()
        try:
            ref = collect_search_hits(
                query_vector=query_vector,
                model_id=model_id,
                topk=topk,
                search_backend="numpy",
            )
            approx = collect_search_hits(
                query_vector=query_vector,
                model_id=model_id,
                topk=topk,
                search_backend="sqlite-vec",
            )
            status = (
                "ok"
                if (
                    ref.error is None
                    and approx.error is None
                    and not ref.info
                    and not approx.info
                )
                else "failed"
            )
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
        "record_set_id": "aq5.tier_a.ann_vs_numpy.query_pair",
        "note": (
            "Paired NumPy+sqlite-vec query wall timing for harness reproducibility only; "
            "not a relevance substitute and not combined with aq5.ranking metrics. "
            "Large-N latency/size remain in docs/benchmarks/SQLITE_VEC_GATE_EVIDENCE.md"
        ),
        "attempt_count": len(statuses),
        "status_counts": dict(Counter(statuses)),
        "p50_ms": aggregates["p50_ms"],
        "p95_ms": aggregates["p95_ms"],
        "p99_ms": aggregates["p99_ms"],
        "ok_count": aggregates["ok_count"],
    }


def _base_result(
    *,
    exit_status: str,
    audit: dict[str, Any],
    manifest: dict[str, Any],
    path_status: dict[str, dict[str, Any]],
    identities: list[dict[str, Any]],
    planes: dict[str, Any],
) -> dict[str, Any]:
    return {
        "document_type": DOCUMENT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "benchmark_id": BENCHMARK_ID,
        "benchmark_version": manifest.get("benchmark_version"),
        "exit_status": exit_status,
        "partition_fingerprint": audit["partition_fingerprint"],
        "query_set_fingerprint": audit["query_set_fingerprint"],
        "no_tuning_on_test": True,
        "backend_paths": [path_status[row["path_id"]] for row in identities],
        "hold_stubs": [dict(item) for item in _HOLD_STUBS],
        "aq5.ranking": planes["aq5.ranking"],
        "aq5.retrieval": planes["aq5.retrieval"],
        "operational": planes["operational"],
        "notes": {
            "plane_separation": (
                "ANN/index approximation is reported on aq5.ranking only; "
                "semantic relevance stays on #1010 aq5.retrieval; latency stays operational"
            ),
            "default_search_backend": "numpy",
            "sqlite_vec_promotion": False,
            "issue_74_solved": False,
            "fail_closed_unavailable_backend": True,
        },
    }


def run_aq5_ann_reference_delta(
    *,
    work_dir: Path | str,
    output_path: Path | str,
    repo_root: Path | str | None = None,
    include_runtime: bool = True,
    runtime_repetitions: int = 5,
) -> dict[str, Any]:
    """Compare approximate index path to NumPy exact reference on frozen Tier-A."""
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT_DEFAULT
    work = Path(work_dir)
    out = Path(output_path)

    assert_work_dir_outside_repo(work, root)
    _assert_output_outside_repo(out, root)
    work.mkdir(parents=True, exist_ok=True)

    audit = audit_aq5_relevance_benchmark(repo_root=root)
    manifest = build_aq5_relevance_benchmark_manifest(repo_root=root)
    identity_by_key = {q["query_key"]: q for q in manifest["queries"]}

    identities = backend_path_identities()
    path_status = {row["path_id"]: dict(row) for row in identities}

    retrieval_note = {
        "status": "out_of_scope",
        "cite": (
            "#1010 / docs/benchmarks/AQ5_RETRIEVAL_BASELINE.md "
            "(aq5.retrieval plane; not reused as ANN quality)"
        ),
        "ndcg_eligibility": "HOLD",
    }

    vec_report = probe_sqlite_vec()
    suite_path = root / TIER_A_SUITE_RELPATH
    suite = load_search_quality_suite(suite_path)
    db_path = work / "ann_tier_a_catalog.db"
    model_id = seed_golden_catalog(db_path, suite)

    reference_pass_a = _run_tier_a_queries(
        suite=suite, model_id=model_id, search_backend="numpy"
    )
    reference_pass_b = _run_tier_a_queries(
        suite=suite, model_id=model_id, search_backend="numpy"
    )
    ref_ok = any(r.get("error") is None for r in reference_pass_a)
    path_status[REFERENCE_PATH_ID]["status"] = "measured" if ref_ok else "HOLD"
    if not ref_ok:
        path_status[REFERENCE_PATH_ID]["reason"] = "reference NumPy queries failed"

    if not vec_report.available:
        path_status[APPROX_PATH_ID]["status"] = "HOLD"
        path_status[APPROX_PATH_ID]["reason"] = (
            f"sqlite-vec unavailable ({vec_report.reason}); fail-closed — "
            "no silent backend substitution"
        )
        ranking = {
            "ndcg_eligibility": "HOLD",
            "semantic_inputs_fixed": True,
            "suite": "tier_a",
            "suite_relpath": str(TIER_A_SUITE_RELPATH).replace("\\", "/"),
            "reference_path": path_status[REFERENCE_PATH_ID],
            "approximate_path": path_status[APPROX_PATH_ID],
            "aggregate": _aggregate_pairs([]),
            "by_mode": {},
            "queries": [],
            "determinism": {
                "reference": _compare_ordered_passes(
                    reference_pass_a, reference_pass_b
                ),
                "approximate": {
                    "status": "HOLD",
                    "reason": "approximate backend unavailable",
                    "tie_order_checked": False,
                },
            },
            "historical_evidence_cite": (
                "docs/benchmarks/SQLITE_VEC_GATE_EVIDENCE.md "
                "(large-N overlap/latency; not AQ5 fixture authority)"
            ),
        }
        planes = separate_reporting_planes(
            ranking=ranking,
            operational={
                "methodology_id": RUNTIME_METHODOLOGY_ID,
                "methodology_ref": "docs/benchmarks/ANALYZER_RUNTIME_METHODOLOGY_V1.md",
                "plane": "operational",
                "status": "HOLD",
                "reason": "sqlite-vec unavailable; operational pair timing skipped",
                "p50_ms": None,
                "p95_ms": None,
                "p99_ms": None,
            },
            retrieval_note=retrieval_note,
        )
        result = _base_result(
            exit_status=EXIT_BACKEND_HOLD,
            audit=audit,
            manifest=manifest,
            path_status=path_status,
            identities=identities,
            planes=planes,
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        return result

    try:
        rebuild = rebuild_vec0_cache(model_id, db_path=db_path)
        approx_pass_a = _run_tier_a_queries(
            suite=suite, model_id=model_id, search_backend="sqlite-vec"
        )
        approx_pass_b = _run_tier_a_queries(
            suite=suite, model_id=model_id, search_backend="sqlite-vec"
        )
    except Exception as exc:
        path_status[APPROX_PATH_ID]["status"] = "HOLD"
        path_status[APPROX_PATH_ID]["reason"] = type(exc).__name__
        ranking = {
            "ndcg_eligibility": "HOLD",
            "semantic_inputs_fixed": True,
            "suite": "tier_a",
            "suite_relpath": str(TIER_A_SUITE_RELPATH).replace("\\", "/"),
            "reference_path": path_status[REFERENCE_PATH_ID],
            "approximate_path": path_status[APPROX_PATH_ID],
            "aggregate": _aggregate_pairs([]),
            "by_mode": {},
            "queries": [],
            "determinism": {
                "reference": _compare_ordered_passes(
                    reference_pass_a, reference_pass_b
                ),
                "approximate": {
                    "status": "HOLD",
                    "reason": type(exc).__name__,
                    "tie_order_checked": False,
                },
            },
            "historical_evidence_cite": "docs/benchmarks/SQLITE_VEC_GATE_EVIDENCE.md",
        }
        planes = separate_reporting_planes(
            ranking=ranking,
            operational={
                "methodology_id": RUNTIME_METHODOLOGY_ID,
                "methodology_ref": "docs/benchmarks/ANALYZER_RUNTIME_METHODOLOGY_V1.md",
                "plane": "operational",
                "status": "HOLD",
                "reason": type(exc).__name__,
                "p50_ms": None,
                "p95_ms": None,
                "p99_ms": None,
            },
            retrieval_note=retrieval_note,
        )
        result = _base_result(
            exit_status=EXIT_INCOMPLETE,
            audit=audit,
            manifest=manifest,
            path_status=path_status,
            identities=identities,
            planes=planes,
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        return result

    approx_ok = any(r.get("error") is None for r in approx_pass_a)
    path_status[APPROX_PATH_ID]["status"] = "measured" if approx_ok else "HOLD"
    if not approx_ok:
        path_status[APPROX_PATH_ID]["reason"] = "approximate sqlite-vec queries failed"
    path_status[APPROX_PATH_ID]["rebuild"] = {
        "sample_count": rebuild.sample_count,
        "embedding_dim": rebuild.embedding_dim,
        "vec_table_name": rebuild.vec_table_name,
        "source_fingerprint": rebuild.source_fingerprint,
    }

    pairs = _pair_comparisons(
        reference_pass_a,
        approx_pass_a,
        identity_by_key=identity_by_key,
    )
    aggregate = _aggregate_pairs(pairs)
    by_mode = _group_pairs_by_mode(pairs)

    if include_runtime and ref_ok and approx_ok:
        operational = _measure_operational(
            suite=suite,
            model_id=model_id,
            measured_repetitions=runtime_repetitions,
        )
    else:
        operational = {
            "methodology_id": RUNTIME_METHODOLOGY_ID,
            "methodology_ref": "docs/benchmarks/ANALYZER_RUNTIME_METHODOLOGY_V1.md",
            "plane": "operational",
            "status": "HOLD",
            "reason": "runtime measurement skipped or paths unavailable",
            "p50_ms": None,
            "p95_ms": None,
            "p99_ms": None,
        }

    ranking = {
        "ndcg_eligibility": "HOLD",
        "semantic_inputs_fixed": True,
        "suite": "tier_a",
        "suite_relpath": str(TIER_A_SUITE_RELPATH).replace("\\", "/"),
        "reference_path": path_status[REFERENCE_PATH_ID],
        "approximate_path": path_status[APPROX_PATH_ID],
        "aggregate": aggregate,
        "by_mode": by_mode,
        "queries": [
            {
                "query_key": p["query_key"],
                "query_id": p["query_id"],
                "split": p.get("split"),
                "mode": p.get("mode"),
                "metrics": p.get("metrics"),
                "ordered_delta": p.get("ordered_delta"),
                "relevant_displacements": p.get("relevant_displacements"),
                "reference_ranked_ids": p.get("reference_ranked_ids") or [],
                "approx_ranked_ids": p.get("approx_ranked_ids") or [],
                "error": p.get("error"),
            }
            for p in pairs
        ],
        "determinism": {
            "reference": _compare_ordered_passes(reference_pass_a, reference_pass_b),
            "approximate": _compare_ordered_passes(approx_pass_a, approx_pass_b),
        },
        "historical_evidence_cite": (
            "docs/benchmarks/SQLITE_VEC_GATE_EVIDENCE.md "
            "(large-N overlap/latency; not AQ5 fixture authority)"
        ),
    }

    planes = separate_reporting_planes(
        ranking=ranking,
        operational=operational,
        retrieval_note=retrieval_note,
    )

    if (
        path_status[REFERENCE_PATH_ID]["status"] == "measured"
        and path_status[APPROX_PATH_ID]["status"] == "measured"
        and aggregate.get("query_count", 0) > 0
        and aggregate.get("error_count", 0) == 0
    ):
        exit_status = EXIT_MEASURED
    else:
        exit_status = EXIT_INCOMPLETE

    result = _base_result(
        exit_status=exit_status,
        audit=audit,
        manifest=manifest,
        path_status=path_status,
        identities=identities,
        planes=planes,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Measure AQ5 ANN/index approximation vs NumPy exact reference "
            "on frozen Tier-A vectors (external JSON only)."
        )
    )
    parser.add_argument(
        "--work-dir",
        required=True,
        help="External work directory for temp DB (outside repo).",
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
        "--skip-runtime",
        action="store_true",
        help="Skip operational paired-query latency measurement.",
    )
    parser.add_argument(
        "--runtime-repetitions",
        type=int,
        default=5,
        help="Operational paired-query repetitions (default: 5).",
    )
    args = parser.parse_args(argv)
    result = run_aq5_ann_reference_delta(
        work_dir=args.work_dir,
        output_path=args.output,
        repo_root=args.repo_root,
        include_runtime=not args.skip_runtime,
        runtime_repetitions=args.runtime_repetitions,
    )
    print(
        json.dumps(
            {
                "exit_status": result["exit_status"],
                "aggregate": result["aq5.ranking"].get("aggregate"),
                "backend_paths": {
                    row["path_id"]: row.get("status")
                    for row in result["backend_paths"]
                },
            },
            sort_keys=True,
        )
    )
    return 0 if result["exit_status"] == EXIT_MEASURED else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "APPROX_PATH_ID",
    "BENCHMARK_ID",
    "DOCUMENT_TYPE",
    "EXIT_BACKEND_HOLD",
    "EXIT_INCOMPLETE",
    "EXIT_MEASURED",
    "REFERENCE_PATH_ID",
    "RUNTIME_METHODOLOGY_ID",
    "SCHEMA_VERSION",
    "backend_path_identities",
    "ordered_ranking_delta",
    "relevant_rank_displacements",
    "run_aq5_ann_reference_delta",
    "separate_reporting_planes",
    "topk_set_overlap",
]
