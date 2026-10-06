"""AQ5 retrieval/ranking candidate comparison on frozen relevance set (#1012).

Frozen ≤4 thin hybrid/classical adapters over the #1010 search surfaces.
Relevance, ANN approximation (#1011), and operational latency (#958) stay on
separate planes. CALIBRATION may narrate; TEST/HOLDOUT stay frozen evidence.
No production switch / no graded NDCG invention.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .aq5_ann_reference_delta import (
    DOCUMENT_TYPE as ANN_DOCUMENT_TYPE,
    EXIT_BACKEND_HOLD as ANN_EXIT_BACKEND_HOLD,
    EXIT_INCOMPLETE as ANN_EXIT_INCOMPLETE,
    EXIT_MEASURED as ANN_EXIT_MEASURED,
    run_aq5_ann_reference_delta,
)
from .aq5_relevance_benchmark import (
    BENCHMARK_ID,
    TIER_A_SUITE_RELPATH,
    TIER_B_SUITE_RELPATH,
    assert_work_dir_outside_repo,
    audit_aq5_relevance_benchmark,
    build_aq5_relevance_benchmark_manifest,
)
from .aq5_retrieval_baseline import (
    DOCUMENT_TYPE as BASELINE_DOCUMENT_TYPE,
    PARTITION_POLICY,
    RUNTIME_METHODOLOGY_ID,
    _build_split_block,
    _compare_ranked_passes,
    _measure_operational_latency,
    _query_meta_from_suite,
    _tier_a_mode_label,
    score_retrieval_query,
    separate_reporting_planes,
)
from .benchmark_search_quality import (
    _filters_from_mapping,
    _hybrid_from_mapping,
    _resolve_query_audio,
    load_search_quality_suite,
    seed_golden_catalog,
    seed_tier_b_clap_catalog,
)
from .embed import EmbeddingBackendUnavailableError
from .hybrid_rank import HybridQuery
from .search import collect_search_hits
from .search_eval import (
    assign_failure_bucket,
    failure_bucket_counts,
    filter_compliance,
    negatives_in_top_k,
    summarize_query_metrics,
)

DOCUMENT_TYPE = "sample-brain.aq5.retrieval-candidate-compare.v1"
SCHEMA_VERSION = "1.0.0"
EXIT_REPRODUCIBLE = "AQ5_RETRIEVAL_CANDIDATE_COMPARE_REPRODUCIBLE"
EXIT_NO_JUSTIFIED = "AQ5_RETRIEVAL_NO_JUSTIFIED_CANDIDATE"
EXIT_INCOMPLETE = "AQ5_RETRIEVAL_CANDIDATE_COMPARE_INCOMPLETE"

# Ordered longest-first so "snare" wins over shorter collisions if added later.
_TYPE_HINT_TOKENS: tuple[tuple[str, str], ...] = (
    ("percussion", "percussion"),
    ("texture", "texture"),
    ("impact", "impact"),
    ("snare", "snare"),
    ("vocal", "vocal"),
    ("voice", "vocal"),
    ("singing", "vocal"),
    ("kick", "kick"),
    ("bass drum", "kick"),
    ("pad", "pad"),
    ("riser", "fx"),
    ("whoosh", "fx"),
    ("reverb", "fx"),
)

_HOLD_STUBS: tuple[dict[str, str], ...] = (
    {"item": "graded_relevance_ndcg", "status": "HOLD"},
    {"item": "vocal_no_vocal_production_claim", "status": "HOLD"},
    {"item": "genre_mood_production_claim", "status": "HOLD"},
    {"item": "sqlite_vec_production_promotion", "status": "HOLD"},
    {"item": "opaque_relevance_latency_aggregate", "status": "HOLD"},
    {"item": "private_producer_reality_check_queries", "status": "HOLD"},
)

_REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[1]


class Aq5RetrievalCandidateCompareError(ValueError):
    """Controlled, fail-closed input or identity error for this compare runner."""


@dataclass(frozen=True)
class RetrievalCandidate:
    candidate_id: str
    adapter_kind: str
    semantic_weight_override: float | None
    type_weight: float | None
    description: str
    derived_from: str


RETRIEVAL_CANDIDATES: tuple[RetrievalCandidate, ...] = (
    RetrievalCandidate(
        candidate_id="retrieval.baseline.v1",
        adapter_kind="identity",
        semantic_weight_override=None,
        type_weight=None,
        description=(
            "Current #1010 path: suite hybrid/filters/topk unchanged "
            "(NumPy Tier-A + CLAP Tier-B when available)."
        ),
        derived_from="#1010 measured retrieval-path anchor",
    ),
    RetrievalCandidate(
        candidate_id="hybrid.semantic_weight.0.8",
        adapter_kind="hybrid_semantic_weight",
        semantic_weight_override=0.8,
        type_weight=None,
        description=(
            "Thin hybrid adapter: when the suite declares hybrid, set "
            "semantic_weight=0.8 and keep declared metadata weights."
        ),
        derived_from=(
            "#1010 hybrid queries use semantic_weight=0.2; isolate metadata "
            "vs semantic pull on CALIBRATION"
        ),
    ),
    RetrievalCandidate(
        candidate_id="classical.type_rerank.text_hint.0.5",
        adapter_kind="classical_type_rerank",
        semantic_weight_override=None,
        type_weight=0.5,
        description=(
            "Thin classical adapter: Tier-B text type-token → "
            "HybridQuery(target_type, type_weight=0.5); suite hybrid left intact."
        ),
        derived_from=(
            "#1010 CALIBRATION hard-neg FP@5 ≈ 0.533 / family HN leaks; "
            "reuse existing hybrid type path"
        ),
    ),
    RetrievalCandidate(
        candidate_id="classical.type_rerank.text_hint.1.0",
        adapter_kind="classical_type_rerank",
        semantic_weight_override=None,
        type_weight=1.0,
        description=(
            "Thin classical adapter: Tier-B text type-token → "
            "HybridQuery(target_type, type_weight=1.0); suite hybrid left intact."
        ),
        derived_from=(
            "#1010 hard-neg FP narrative; stronger classical type pull "
            "(still evaluation-only)"
        ),
    ),
)


def list_retrieval_candidates() -> list[RetrievalCandidate]:
    return list(RETRIEVAL_CANDIDATES)


def candidate_by_id(candidate_id: str) -> RetrievalCandidate:
    for candidate in RETRIEVAL_CANDIDATES:
        if candidate.candidate_id == candidate_id:
            return candidate
    raise Aq5RetrievalCandidateCompareError(
        f"unknown retrieval candidate_id: {candidate_id}"
    )


def candidate_public(candidate: RetrievalCandidate) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "adapter_kind": candidate.adapter_kind,
        "semantic_weight_override": candidate.semantic_weight_override,
        "type_weight": candidate.type_weight,
        "description": candidate.description,
        "derived_from": candidate.derived_from,
    }


def type_hint_from_text(text: str | None) -> str | None:
    """Map query text to a catalog pred_type hint (deterministic, public tokens)."""
    if not text:
        return None
    lowered = text.casefold()
    for token, pred_type in _TYPE_HINT_TOKENS:
        if token in lowered:
            return pred_type
    return None


def adapt_hybrid_query(
    *,
    suite_hybrid: HybridQuery | None,
    mode: str,
    query_text: str | None,
    candidate: RetrievalCandidate,
) -> HybridQuery | None:
    """Apply a thin candidate adapter without changing production defaults."""
    if candidate.adapter_kind == "identity":
        return suite_hybrid

    if candidate.adapter_kind == "hybrid_semantic_weight":
        if suite_hybrid is None:
            return None
        override = candidate.semantic_weight_override
        if override is None:
            return suite_hybrid
        return HybridQuery(
            target_bpm=suite_hybrid.target_bpm,
            target_key=suite_hybrid.target_key,
            target_type=suite_hybrid.target_type,
            semantic_weight=float(override),
            bpm_weight=suite_hybrid.bpm_weight,
            key_weight=suite_hybrid.key_weight,
            type_weight=suite_hybrid.type_weight,
            bpm_tolerance=suite_hybrid.bpm_tolerance,
        )

    if candidate.adapter_kind == "classical_type_rerank":
        # Never replace an explicit suite hybrid (Tier-A hybrid queries).
        if suite_hybrid is not None:
            return suite_hybrid
        if mode != "text":
            return None
        hint = type_hint_from_text(query_text)
        if hint is None or candidate.type_weight is None:
            return None
        return HybridQuery(
            target_type=hint,
            semantic_weight=1.0,
            type_weight=float(candidate.type_weight),
        )

    raise Aq5RetrievalCandidateCompareError(
        f"unsupported adapter_kind: {candidate.adapter_kind}"
    )


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


def _score_row(
    *,
    suite_key: str,
    query_id: str,
    mode: str,
    ranked_ids: list[int],
    error: str | None,
    identity: dict[str, Any],
    suite_meta: dict[str, Any],
    filter_ok: float,
    passed_must_recall: bool,
    negatives_in_top5: int,
    failure_bucket: str,
) -> dict[str, Any]:
    relevant = set(identity["relevant_sample_ids"])
    negatives = set(identity["negative_sample_ids"])
    if error:
        metrics = None
        bucket = "error"
    else:
        metrics = score_retrieval_query(
            ranked_ids=ranked_ids,
            relevant_ids=relevant,
            negative_ids=negatives,
        )
        bucket = failure_bucket
    mode_label = (
        _tier_a_mode_label(
            query_id,
            mode,
            bool(suite_meta.get("filters")),
            bool(suite_meta.get("hybrid")),
        )
        if suite_key == "tier_a"
        else mode
    )
    family = str(
        identity.get("query_family")
        or ("tier_a_pipeline" if suite_key == "tier_a" else "unknown")
    )
    if suite_key == "tier_a":
        family = "tier_a_pipeline"
    return {
        "query_key": f"{suite_key}:{query_id}",
        "query_id": query_id,
        "suite": suite_key,
        "split": identity["split"],
        "mode": mode_label,
        "query_family": family,
        "ranked_ids": list(ranked_ids) if not error else [],
        "metrics": metrics,
        "failure_bucket": bucket,
        "error": error,
        "filter_compliance": filter_ok,
        "passed_must_recall": passed_must_recall,
        "negatives_in_top5": negatives_in_top5,
    }


def _eval_suite_for_candidate(
    *,
    suite_path: Path,
    suite_key: str,
    work_dir: Path,
    candidate: RetrievalCandidate,
    identity_by_key: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    suite = load_search_quality_suite(suite_path)
    suite_meta = _query_meta_from_suite(suite)
    defaults = suite.get("defaults") or {}
    default_topk = int(defaults.get("topk", 10))
    default_backend = str(defaults.get("backend", "noop"))
    tier = str(suite.get("tier", "A"))

    work_dir.mkdir(parents=True, exist_ok=True)
    db_path = work_dir / "golden_catalog.db"
    fixture_paths: dict[str, Path] = {}
    if tier == "B":
        seeded_model_id, fixture_paths = seed_tier_b_clap_catalog(
            db_path,
            suite,
            work_root=work_dir,
        )
    else:
        seeded_model_id = seed_golden_catalog(db_path, suite)

    rows: list[dict[str, Any]] = []
    for raw_query in suite.get("queries") or []:
        if raw_query.get("eval_excluded"):
            continue
        query_id = str(raw_query["id"])
        query_key = f"{suite_key}:{query_id}"
        identity = identity_by_key.get(query_key)
        if identity is None:
            continue
        mode = str(raw_query.get("mode", "vector"))
        topk = int(raw_query.get("topk", default_topk))
        filters = _filters_from_mapping(raw_query.get("filters"))
        suite_hybrid = _hybrid_from_mapping(raw_query.get("hybrid"))
        query_text = raw_query.get("text") if mode == "text" else None
        hybrid = adapt_hybrid_query(
            suite_hybrid=suite_hybrid,
            mode=mode,
            query_text=str(query_text) if query_text is not None else None,
            candidate=candidate,
        )
        backend_name = str(raw_query.get("backend", default_backend))
        relevant_ids = {
            int(value) for value in raw_query.get("relevant_sample_ids") or []
        }
        negative_ids = {
            int(value) for value in raw_query.get("negative_sample_ids") or []
        }
        must_recall_k = raw_query.get("must_recall_within_k")

        try:
            if mode == "vector":
                query_vector = np.asarray(raw_query["query_vector"], dtype=np.float32)
                result = collect_search_hits(
                    query_vector=query_vector,
                    model_id=seeded_model_id,
                    topk=topk,
                    search_backend="numpy",
                    hybrid_query=hybrid,
                    search_filters=filters,
                )
            elif mode in {"text", "audio"}:
                query_audio = (
                    _resolve_query_audio(raw_query, fixture_paths)
                    if mode == "audio"
                    else None
                )
                result = collect_search_hits(
                    query=query_text if mode == "text" else None,
                    query_audio=query_audio,
                    model_id=seeded_model_id,
                    topk=topk,
                    backend_name=backend_name,
                    search_backend="numpy",
                    hybrid_query=hybrid,
                    search_filters=filters,
                )
            else:
                rows.append(
                    _score_row(
                        suite_key=suite_key,
                        query_id=query_id,
                        mode=mode,
                        ranked_ids=[],
                        error=f"Unknown query mode: {mode}",
                        identity=identity,
                        suite_meta=suite_meta.get(query_id) or {},
                        filter_ok=0.0,
                        passed_must_recall=False,
                        negatives_in_top5=0,
                        failure_bucket="error",
                    )
                )
                continue
        except EmbeddingBackendUnavailableError as exc:
            rows.append(
                _score_row(
                    suite_key=suite_key,
                    query_id=query_id,
                    mode=mode,
                    ranked_ids=[],
                    error=str(exc),
                    identity=identity,
                    suite_meta=suite_meta.get(query_id) or {},
                    filter_ok=0.0,
                    passed_must_recall=False,
                    negatives_in_top5=0,
                    failure_bucket="error",
                )
            )
            continue
        except Exception as exc:  # noqa: BLE001 — portable per-query failure
            rows.append(
                _score_row(
                    suite_key=suite_key,
                    query_id=query_id,
                    mode=mode,
                    ranked_ids=[],
                    error=f"{type(exc).__name__}: {exc}",
                    identity=identity,
                    suite_meta=suite_meta.get(query_id) or {},
                    filter_ok=0.0,
                    passed_must_recall=False,
                    negatives_in_top5=0,
                    failure_bucket="error",
                )
            )
            continue

        if result.error or result.info:
            rows.append(
                _score_row(
                    suite_key=suite_key,
                    query_id=query_id,
                    mode=mode,
                    ranked_ids=[],
                    error=result.error or result.info,
                    identity=identity,
                    suite_meta=suite_meta.get(query_id) or {},
                    filter_ok=0.0,
                    passed_must_recall=False,
                    negatives_in_top5=0,
                    failure_bucket="error",
                )
            )
            continue

        ranked_ids = [hit.sample_id for hit in result.hits]
        allowed_ids = None
        if filters is not None and filters.active():
            from .search_filters import resolve_filtered_sample_ids

            allowed_ids = resolve_filtered_sample_ids(filters)
        metrics = summarize_query_metrics(ranked_ids, relevant_ids)
        passed_must_recall = True
        if must_recall_k is not None:
            from .search_eval import recall_at_k

            passed_must_recall = (
                recall_at_k(ranked_ids, relevant_ids, int(must_recall_k)) >= 1.0
            )
        neg_top5 = negatives_in_top_k(ranked_ids, negative_ids, 5)
        bucket = assign_failure_bucket(
            metrics,
            passed_must_recall=passed_must_recall,
            negatives_in_top5=neg_top5,
            error=None,
        )
        rows.append(
            _score_row(
                suite_key=suite_key,
                query_id=query_id,
                mode=mode,
                ranked_ids=ranked_ids,
                error=None,
                identity=identity,
                suite_meta=suite_meta.get(query_id) or {},
                filter_ok=filter_compliance(ranked_ids, allowed_ids),
                passed_must_recall=passed_must_recall,
                negatives_in_top5=neg_top5,
                failure_bucket=bucket,
            )
        )
    return rows


def _candidate_measured(rows: list[dict[str, Any]]) -> bool:
    return any(r.get("error") is None and r.get("metrics") for r in rows)


def _baseline_anchor_matches(
    baseline_rows: list[dict[str, Any]],
    *,
    include_tier_b: bool,
) -> bool:
    """Baseline candidate must score the expected frozen query support."""
    if not _candidate_measured(baseline_rows):
        return False
    by_suite = {}
    for row in baseline_rows:
        by_suite.setdefault(row["suite"], 0)
        by_suite[row["suite"]] += 1
    if by_suite.get("tier_a", 0) < 1:
        return False
    if include_tier_b and by_suite.get("tier_b", 0) < 1:
        return False
    # Identity adapter: every successful row must have metrics + split.
    for row in baseline_rows:
        if row.get("error") is None and row.get("metrics") is None:
            return False
        if row.get("split") not in {"CALIBRATION", "TEST"}:
            return False
    return True


def run_aq5_retrieval_candidate_compare(
    *,
    work_dir: Path | str,
    output_path: Path | str,
    repo_root: Path | str | None = None,
    include_tier_b: bool = True,
    include_runtime: bool = True,
    include_ann: bool = True,
    runtime_repetitions: int = 5,
) -> dict[str, Any]:
    """Compare frozen retrieval candidates; write external JSON evidence."""
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT_DEFAULT
    work = Path(work_dir)
    out = Path(output_path)

    assert_work_dir_outside_repo(work, root)
    _assert_output_outside_repo(out, root)
    work.mkdir(parents=True, exist_ok=True)

    if not (3 <= len(RETRIEVAL_CANDIDATES) <= 4):
        raise Aq5RetrievalCandidateCompareError(
            "frozen candidate registry must contain 3–4 identities"
        )

    audit = audit_aq5_relevance_benchmark(repo_root=root)
    manifest = build_aq5_relevance_benchmark_manifest(repo_root=root)
    identity_by_key = {q["query_key"]: q for q in manifest["queries"]}

    tier_a_path = root / TIER_A_SUITE_RELPATH
    tier_b_path = root / TIER_B_SUITE_RELPATH

    candidate_entries: list[dict[str, Any]] = []
    baseline_rows_for_determinism: list[dict[str, Any]] = []
    baseline_rows_pass_b: list[dict[str, Any]] = []
    any_candidate_measured = False
    tier_b_attempted = False
    tier_b_ok = False

    for candidate in RETRIEVAL_CANDIDATES:
        all_rows: list[dict[str, Any]] = []
        cand_work = work / candidate.candidate_id.replace(".", "_")

        tier_a_rows = _eval_suite_for_candidate(
            suite_path=tier_a_path,
            suite_key="tier_a",
            work_dir=cand_work / "tier_a",
            candidate=candidate,
            identity_by_key=identity_by_key,
        )
        all_rows.extend(tier_a_rows)

        if include_tier_b:
            tier_b_attempted = True
            try:
                tier_b_rows = _eval_suite_for_candidate(
                    suite_path=tier_b_path,
                    suite_key="tier_b",
                    work_dir=cand_work / "tier_b",
                    candidate=candidate,
                    identity_by_key=identity_by_key,
                )
                all_rows.extend(tier_b_rows)
                if _candidate_measured(tier_b_rows):
                    tier_b_ok = True
            except EmbeddingBackendUnavailableError:
                pass

        if _candidate_measured(all_rows):
            any_candidate_measured = True

        splits = {
            split_name: _build_split_block(
                [r for r in all_rows if r.get("split") == split_name]
            )
            for split_name in ("CALIBRATION", "TEST")
        }
        entry: dict[str, Any] = {
            **candidate_public(candidate),
            "status": "measured" if _candidate_measured(all_rows) else "HOLD",
            "query_count": len(all_rows),
            "error_count": sum(1 for r in all_rows if r.get("error")),
            "splits": splits,
            "failure_buckets": failure_bucket_counts(
                [str(r.get("failure_bucket") or "error") for r in all_rows]
            ),
            "queries": [
                {
                    "query_key": r["query_key"],
                    "split": r["split"],
                    "suite": r["suite"],
                    "mode": r["mode"],
                    "query_family": r["query_family"],
                    "ranked_ids": r.get("ranked_ids") or [],
                    "metrics": r.get("metrics"),
                    "failure_bucket": r.get("failure_bucket"),
                    "error": r.get("error"),
                }
                for r in all_rows
            ],
        }
        if candidate.candidate_id == "retrieval.baseline.v1":
            entry["baseline_anchor_ok"] = _baseline_anchor_matches(
                all_rows, include_tier_b=include_tier_b and tier_b_ok
            )
            baseline_rows_for_determinism = tier_a_rows
            # Second Tier-A pass for #959 determinism on the baseline adapter.
            baseline_rows_pass_b = _eval_suite_for_candidate(
                suite_path=tier_a_path,
                suite_key="tier_a",
                work_dir=cand_work / "tier_a_pass_b",
                candidate=candidate,
                identity_by_key=identity_by_key,
            )
        candidate_entries.append(entry)

    determinism = _compare_ranked_passes(
        baseline_rows_for_determinism,
        baseline_rows_pass_b,
    )

    ann_block: dict[str, Any]
    if include_ann:
        try:
            ann_out = work / "ann_carry.json"
            ann_result = run_aq5_ann_reference_delta(
                work_dir=work / "ann_reference",
                output_path=ann_out,
                repo_root=root,
                include_runtime=False,
            )
            ann_block = {
                "plane": "aq5.ranking",
                "default_promotion": False,
                "document_type": ANN_DOCUMENT_TYPE,
                "exit_status": ann_result.get("exit_status"),
                "status": (
                    "measured"
                    if ann_result.get("exit_status") == ANN_EXIT_MEASURED
                    else "HOLD"
                ),
                "carry_ref": "docs/benchmarks/AQ5_ANN_REFERENCE_DELTA.md",
                "note": (
                    "ANN approximation carried separately from relevance; "
                    "not folded into aq5.retrieval macros; no promotion"
                ),
                "portable_summary": {
                    "exit_status": ann_result.get("exit_status"),
                    "aggregate": (ann_result.get("aq5.ranking") or {}).get(
                        "aggregate"
                    ),
                },
            }
            if ann_result.get("exit_status") in {
                ANN_EXIT_BACKEND_HOLD,
                ANN_EXIT_INCOMPLETE,
            }:
                ann_block["reason"] = ann_result.get("exit_status")
        except Exception as exc:  # noqa: BLE001
            ann_block = {
                "plane": "aq5.ranking",
                "default_promotion": False,
                "status": "HOLD",
                "reason": f"{type(exc).__name__}: {exc}",
                "carry_ref": "docs/benchmarks/AQ5_ANN_REFERENCE_DELTA.md",
            }
    else:
        ann_block = {
            "plane": "aq5.ranking",
            "default_promotion": False,
            "status": "HOLD",
            "reason": "ANN carry skipped by caller",
            "carry_ref": "docs/benchmarks/AQ5_ANN_REFERENCE_DELTA.md",
        }

    if include_runtime and baseline_rows_for_determinism:
        operational = _measure_operational_latency(
            work_dir=work / "operational",
            suite_path=tier_a_path,
            measured_repetitions=runtime_repetitions,
        )
    else:
        operational = {
            "methodology_id": RUNTIME_METHODOLOGY_ID,
            "methodology_ref": "docs/benchmarks/ANALYZER_RUNTIME_METHODOLOGY_V1.md",
            "plane": "operational",
            "status": "HOLD",
            "reason": "runtime measurement skipped or baseline Tier-A unavailable",
            "p50_ms": None,
            "p95_ms": None,
            "p99_ms": None,
        }

    planes = separate_reporting_planes(
        retrieval={
            "benchmark_id": BENCHMARK_ID,
            "ndcg_eligibility": "HOLD",
            "relevance_scheme": "binary",
            "identical_query_relevance_records": True,
            "k_values": [1, 5, 10],
            "candidate_ids": [c["candidate_id"] for c in candidate_entries],
            "note": (
                "Per-candidate relevance lives under candidates[].splits; "
                "this plane never mixes ANN or latency"
            ),
        },
        ranking={
            "determinism": determinism,
            "ann_approximation": ann_block,
        },
        operational=operational,
    )

    baseline_entry = next(
        (
            c
            for c in candidate_entries
            if c["candidate_id"] == "retrieval.baseline.v1"
        ),
        None,
    )
    baseline_ok = bool(
        baseline_entry
        and baseline_entry.get("status") == "measured"
        and baseline_entry.get("baseline_anchor_ok")
    )

    # Full REPRODUCIBLE requires Tier-A + Tier-B on the frozen query identity.
    # Tier-A-only (skipped or unavailable CLAP) stays INCOMPLETE — never a
    # silent partial that looks like a complete bake-off.
    if not any_candidate_measured or not baseline_ok:
        exit_status = EXIT_INCOMPLETE
    elif not (include_tier_b and tier_b_attempted and tier_b_ok):
        exit_status = EXIT_INCOMPLETE
    elif len(RETRIEVAL_CANDIDATES) < 3:
        exit_status = EXIT_NO_JUSTIFIED
    else:
        exit_status = EXIT_REPRODUCIBLE

    result: dict[str, Any] = {
        "document_type": DOCUMENT_TYPE,
        "schema_version": SCHEMA_VERSION,
        "benchmark_id": BENCHMARK_ID,
        "benchmark_version": manifest.get("benchmark_version"),
        "baseline_document_type": BASELINE_DOCUMENT_TYPE,
        "exit_status": exit_status,
        "partition_policy": dict(PARTITION_POLICY),
        "no_tuning_on_test": True,
        "production_switch": False,
        "partition_fingerprint": audit["partition_fingerprint"],
        "query_set_fingerprint": audit["query_set_fingerprint"],
        "candidate_count": len(candidate_entries),
        "candidates": candidate_entries,
        "hold_stubs": [dict(item) for item in _HOLD_STUBS],
        "aq5.retrieval": planes["aq5.retrieval"],
        "aq5.ranking": planes["aq5.ranking"],
        "operational": planes["operational"],
        "automation_seam": {
            "headless_invocation": True,
            "module": "src.aq5_retrieval_candidate_compare",
            "exit_status": exit_status,
            "benchmark_id": BENCHMARK_ID,
            "partition_fingerprint": audit["partition_fingerprint"],
            "query_set_fingerprint": audit["query_set_fingerprint"],
            "test_holdout_locked": True,
            "production_promotion_unguarded": False,
            "planes": ["aq5.retrieval", "aq5.ranking", "operational"],
            "quality_loop_ref": "#1040",
        },
        "notes": {
            "plane_separation": (
                "Relevance, ANN approximation, and operational latency are "
                "reported on separate planes and never opaque-combined"
            ),
            "tier_b_attempted": tier_b_attempted,
            "tier_b_ok": tier_b_ok,
            "default_search_backend": "numpy",
            "sqlite_vec_promotion": False,
            "calibration_vs_test": (
                "CALIBRATION is exploration narrative only; "
                "TEST/HOLDOUT is frozen evidence with no tuning"
            ),
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
            "Compare frozen AQ5 retrieval/ranking candidates on the relevance "
            "benchmark (external JSON only; no production switch)."
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
        help="External JSON evidence path (outside repo).",
    )
    parser.add_argument(
        "--skip-tier-b",
        action="store_true",
        help="Skip CLAP Tier-B measurement (exit cannot be REPRODUCIBLE).",
    )
    parser.add_argument(
        "--skip-runtime",
        action="store_true",
        help="Skip #958 operational suite-wall timing.",
    )
    parser.add_argument(
        "--skip-ann",
        action="store_true",
        help="Skip #1011 ANN approximation carry on the ranking plane.",
    )
    parser.add_argument(
        "--runtime-repetitions",
        type=int,
        default=5,
        help="Operational suite-wall repetitions (default 5).",
    )
    args = parser.parse_args(argv)
    result = run_aq5_retrieval_candidate_compare(
        work_dir=args.work_dir,
        output_path=args.output,
        include_tier_b=not args.skip_tier_b,
        include_runtime=not args.skip_runtime,
        include_ann=not args.skip_ann,
        runtime_repetitions=args.runtime_repetitions,
    )
    print(json.dumps({"exit_status": result["exit_status"]}, indent=2))
    if result["exit_status"] == EXIT_REPRODUCIBLE:
        return 0
    if result["exit_status"] == EXIT_NO_JUSTIFIED:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DOCUMENT_TYPE",
    "SCHEMA_VERSION",
    "EXIT_REPRODUCIBLE",
    "EXIT_NO_JUSTIFIED",
    "EXIT_INCOMPLETE",
    "BENCHMARK_ID",
    "BASELINE_DOCUMENT_TYPE",
    "PARTITION_POLICY",
    "RETRIEVAL_CANDIDATES",
    "RetrievalCandidate",
    "Aq5RetrievalCandidateCompareError",
    "list_retrieval_candidates",
    "candidate_by_id",
    "candidate_public",
    "type_hint_from_text",
    "adapt_hybrid_query",
    "run_aq5_retrieval_candidate_compare",
    "main",
]
