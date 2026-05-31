from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from . import config
from .config import set_db_path
from .db import get_engine, init_db, text, upsert_embedding_model
from .hybrid_rank import HybridQuery
from .search import collect_search_hits
from .search_eval import (
    MetricSummary,
    aggregate_metric_summaries,
    filter_compliance,
    summarize_query_metrics,
)
from .search_filters import SearchFilters

DEFAULT_SUITE_PATH = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "search_quality"
    / "golden_v1.yaml"
)


@dataclass(frozen=True)
class QueryEvalResult:
    query_id: str
    ranked_ids: list[int]
    metrics: dict[str, float]
    filter_compliance: float
    passed_must_recall: bool
    error: str | None = None


@dataclass(frozen=True)
class SearchQualityBenchmarkResult:
    suite_path: Path
    tier: str
    summary: MetricSummary
    query_results: tuple[QueryEvalResult, ...]
    thresholds: dict[str, float]

    def threshold_pass(self) -> dict[str, bool]:
        checks = {
            "mean_precision_at_1": self.summary.precision_at_1
            >= self.thresholds.get("mean_precision_at_1", 0.0),
            "mean_precision_at_5": self.summary.precision_at_5
            >= self.thresholds.get("mean_precision_at_5", 0.0),
            "mean_recall_at_10": self.summary.recall_at_10
            >= self.thresholds.get("mean_recall_at_10", 0.0),
        }
        checks["must_recall_queries"] = all(
            row.passed_must_recall for row in self.query_results if row.error is None
        )
        checks["filter_compliance"] = all(
            row.filter_compliance >= 1.0 for row in self.query_results if row.error is None
        )
        return checks


def load_search_quality_suite(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid suite file: {path}")
    return data


def _filters_from_mapping(raw: dict[str, Any] | None) -> SearchFilters | None:
    if not raw:
        return None
    tags = tuple(raw.get("tags") or [])
    filters = SearchFilters(
        tags=tags,
        min_bpm=raw.get("min_bpm"),
        max_bpm=raw.get("max_bpm"),
        key=raw.get("key"),
        scale=raw.get("scale"),
        min_duration=raw.get("min_duration"),
        max_duration=raw.get("max_duration"),
        pred_type=raw.get("pred_type"),
    )
    if not filters.active():
        return None
    return filters


def _hybrid_from_mapping(raw: dict[str, Any] | None) -> HybridQuery | None:
    if not raw:
        return None
    return HybridQuery(
        target_bpm=raw.get("target_bpm"),
        target_key=raw.get("target_key"),
        target_type=raw.get("target_type"),
        semantic_weight=float(raw.get("semantic_weight", 1.0)),
        bpm_weight=float(raw.get("bpm_weight", 0.0)),
        key_weight=float(raw.get("key_weight", 0.0)),
        type_weight=float(raw.get("type_weight", 0.0)),
        bpm_tolerance=float(raw.get("bpm_tolerance", 8.0)),
    )


def seed_golden_catalog(
    db_path: Path,
    suite: dict[str, Any],
) -> int:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    os.environ["SAMPLE_BRAIN_DB_PATH"] = str(db_path)
    set_db_path(env={"SAMPLE_BRAIN_DB_PATH": str(db_path)})
    config.DB_PATH = db_path
    init_db()

    catalog = suite.get("catalog") or {}
    samples = catalog.get("samples") or []
    embedding_dim = int(suite.get("embedding_dim", 512))

    model_id = upsert_embedding_model(
        provider="golden",
        model_name="tier-a",
        model_version="1",
        embedding_dim=embedding_dim,
        modality="audio+text",
    )

    engine = get_engine()
    with engine.begin() as conn:
        for sample in samples:
            sample_id = int(sample["id"])
            conn.execute(
                text(
                    """
                    INSERT INTO samples (id, path, hash, duration)
                    VALUES (:id, :path, :hash, :duration)
                    """
                ),
                {
                    "id": sample_id,
                    "path": sample.get("path", f"/golden/sample-{sample_id}.wav"),
                    "hash": sample.get("hash", f"hash-{sample_id}"),
                    "duration": float(sample.get("duration", 1.0)),
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO features (sample_id, bpm, key, pred_type, class)
                    VALUES (:sample_id, :bpm, :key, :pred_type, :class)
                    """
                ),
                {
                    "sample_id": sample_id,
                    "bpm": sample.get("bpm"),
                    "key": sample.get("key"),
                    "pred_type": sample.get("pred_type"),
                    "class": sample.get("class"),
                },
            )
            for tag in sample.get("tags") or []:
                conn.execute(
                    text(
                        """
                        INSERT OR IGNORE INTO sample_tags (sample_id, tag, source)
                        VALUES (:sample_id, :tag, 'golden')
                        """
                    ),
                    {"sample_id": sample_id, "tag": str(tag)},
                )

            vector = np.asarray(sample["vector"], dtype=np.float32)
            if vector.shape[0] != embedding_dim:
                raise ValueError(
                    f"Sample {sample_id} vector dim {vector.shape[0]} "
                    f"!= suite embedding_dim {embedding_dim}"
                )
            source_hash = str(sample.get("hash", f"hash-{sample_id}"))
            conn.execute(
                text(
                    """
                    INSERT OR IGNORE INTO sample_embeddings
                        (sample_id, model_id, embedding, embedding_format, source_hash)
                    VALUES (:sample_id, :model_id, :embedding, :embedding_format, :source_hash)
                    """
                ),
                {
                    "sample_id": sample_id,
                    "model_id": model_id,
                    "embedding": vector.tobytes(),
                    "embedding_format": "float32",
                    "source_hash": source_hash,
                },
            )

    return model_id


def run_search_quality_benchmark(
    suite_path: Path,
    *,
    work_dir: Path | None = None,
) -> SearchQualityBenchmarkResult:
    suite = load_search_quality_suite(suite_path)
    defaults = suite.get("defaults") or {}
    default_topk = int(defaults.get("topk", 10))
    default_model_id = int(defaults.get("model_id", 1))

    work_root = work_dir or Path(".bench_search_quality")
    work_root.mkdir(parents=True, exist_ok=True)
    db_path = work_root / "golden_catalog.db"

    seeded_model_id = seed_golden_catalog(db_path, suite)
    if default_model_id != seeded_model_id:
        default_model_id = seeded_model_id

    query_results: list[QueryEvalResult] = []
    metric_rows: list[dict[str, float]] = []

    for raw_query in suite.get("queries") or []:
        query_id = str(raw_query["id"])
        mode = str(raw_query.get("mode", "vector"))
        topk = int(raw_query.get("topk", default_topk))
        relevant_ids = {int(value) for value in raw_query.get("relevant_sample_ids") or []}
        filters = _filters_from_mapping(raw_query.get("filters"))
        hybrid = _hybrid_from_mapping(raw_query.get("hybrid"))
        must_recall_k = raw_query.get("must_recall_within_k")

        if mode == "vector":
            query_vector = np.asarray(raw_query["query_vector"], dtype=np.float32)
            result = collect_search_hits(
                query_vector=query_vector,
                model_id=default_model_id,
                topk=topk,
                search_backend="numpy",
                hybrid_query=hybrid,
                search_filters=filters,
            )
        elif mode in {"text", "audio"}:
            result = collect_search_hits(
                query=raw_query.get("text") if mode == "text" else None,
                query_audio=raw_query.get("query_audio"),
                model_id=default_model_id,
                topk=topk,
                backend_name=str(raw_query.get("backend", "clap")),
                search_backend="numpy",
                hybrid_query=hybrid,
                search_filters=filters,
            )
        else:
            query_results.append(
                QueryEvalResult(
                    query_id=query_id,
                    ranked_ids=[],
                    metrics={},
                    filter_compliance=0.0,
                    passed_must_recall=False,
                    error=f"Unknown query mode: {mode}",
                )
            )
            continue

        if result.error or result.info:
            query_results.append(
                QueryEvalResult(
                    query_id=query_id,
                    ranked_ids=[],
                    metrics={},
                    filter_compliance=0.0,
                    passed_must_recall=False,
                    error=result.error or result.info,
                )
            )
            continue

        ranked_ids = [hit.sample_id for hit in result.hits]
        allowed_ids = None
        if filters is not None and filters.active():
            from .search_filters import resolve_filtered_sample_ids

            allowed_ids = resolve_filtered_sample_ids(filters)

        metrics = summarize_query_metrics(ranked_ids, relevant_ids)
        metric_rows.append(metrics)

        passed_must_recall = True
        if must_recall_k is not None:
            from .search_eval import recall_at_k

            passed_must_recall = (
                recall_at_k(ranked_ids, relevant_ids, int(must_recall_k)) >= 1.0
            )

        query_results.append(
            QueryEvalResult(
                query_id=query_id,
                ranked_ids=ranked_ids,
                metrics=metrics,
                filter_compliance=filter_compliance(ranked_ids, allowed_ids),
                passed_must_recall=passed_must_recall,
            )
        )

    summary = aggregate_metric_summaries(metric_rows)
    thresholds = suite.get("thresholds") or {}
    return SearchQualityBenchmarkResult(
        suite_path=suite_path,
        tier=str(suite.get("tier", "A")),
        summary=summary,
        query_results=tuple(query_results),
        thresholds={key: float(value) for key, value in thresholds.items()},
    )


def print_search_quality_report(result: SearchQualityBenchmarkResult) -> None:
    checks = result.threshold_pass()
    print(f"suite={result.suite_path} tier={result.tier} queries={result.summary.query_count}")
    print(
        "mean_precision_at_1="
        f"{result.summary.precision_at_1:.3f} "
        f"mean_precision_at_5={result.summary.precision_at_5:.3f} "
        f"mean_recall_at_10={result.summary.recall_at_10:.3f} "
        f"mrr={result.summary.mrr:.3f}"
    )
    for key, passed in checks.items():
        print(f"gate_{key}={'PASS' if passed else 'FAIL'}")
    for row in result.query_results:
        if row.error:
            print(f"query={row.query_id} error={row.error}")
            continue
        print(
            f"query={row.query_id} "
            f"p@1={row.metrics['precision_at_1']:.3f} "
            f"p@5={row.metrics['precision_at_5']:.3f} "
            f"r@10={row.metrics['recall_at_10']:.3f} "
            f"filter={row.filter_compliance:.3f} "
            f"must_recall={'PASS' if row.passed_must_recall else 'FAIL'}"
        )
