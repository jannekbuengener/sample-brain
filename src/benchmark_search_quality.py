from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from . import config
from .config import set_db_path
from .db import (
    get_engine,
    init_db,
    insert_sample_embedding,
    text,
    upsert_embedding_model,
)
from .embed import ClapEmbeddingBackend, EmbeddingBackendUnavailableError
from .hybrid_rank import HybridQuery
from .search import collect_search_hits
from .search_eval import (
    FAILURE_BUCKET_LABELS,
    GroupedMetricSummary,
    MetricSummary,
    aggregate_metric_summaries,
    aggregate_metric_summaries_by_group,
    assign_failure_bucket,
    failure_bucket_counts,
    filter_compliance,
    negatives_in_top_k,
    summarize_query_metrics,
)
from .search_filters import SearchFilters
from .search_quality_contract import (
    SearchQualityContractError,
    validate_search_quality_suite,
)
from .search_quality_fixtures import generate_search_quality_fixture

DEFAULT_SUITE_PATH = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "search_quality"
    / "golden_v1.yaml"
)

DEFAULT_TIER_B_SUITE_PATH = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "search_quality"
    / "golden_v2_clap.yaml"
)


@dataclass(frozen=True)
class QueryEvalResult:
    query_id: str
    query_class: str | None
    mode: str
    ranked_ids: list[int]
    metrics: dict[str, float]
    filter_compliance: float
    passed_must_recall: bool
    negatives_in_top5: int
    negatives_in_top10: int
    failure_bucket: str
    error: str | None = None
    query_style: str | None = None


@dataclass(frozen=True)
class ModeClassEvaluationSummary:
    mode: str
    query_class: str
    summary: MetricSummary
    query_count: int
    failure_buckets: dict[str, int]
    hard_negative_violations: int


@dataclass(frozen=True)
class SearchQualityBenchmarkResult:
    suite_path: Path
    tier: str
    summary: MetricSummary
    query_results: tuple[QueryEvalResult, ...]
    thresholds: dict[str, float]
    class_summaries: tuple[GroupedMetricSummary, ...] = ()
    mode_summaries: tuple[GroupedMetricSummary, ...] = ()
    style_summaries: tuple[GroupedMetricSummary, ...] = ()
    failure_buckets: dict[str, int] | None = None
    mode_class_summaries: tuple[ModeClassEvaluationSummary, ...] = ()

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
            row.filter_compliance >= 1.0
            for row in self.query_results
            if row.error is None
        )
        return checks


def load_search_quality_suite(
    path: Path,
    *,
    validate: bool = True,
) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid suite file: {path}")
    if validate:
        try:
            validate_search_quality_suite(data)
        except SearchQualityContractError as exc:
            raise ValueError(f"Invalid suite contract in {path}: {exc}") from exc
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


def _path_hash(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest[:16]


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
                text("""
                    INSERT INTO samples (id, path, hash, duration)
                    VALUES (:id, :path, :hash, :duration)
                    """),
                {
                    "id": sample_id,
                    "path": sample.get("path", f"/golden/sample-{sample_id}.wav"),
                    "hash": sample.get("hash", f"hash-{sample_id}"),
                    "duration": float(sample.get("duration", 1.0)),
                },
            )
            conn.execute(
                text("""
                    INSERT INTO features (sample_id, bpm, key, pred_type, class)
                    VALUES (:sample_id, :bpm, :key, :pred_type, :class)
                    """),
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
                    text("""
                        INSERT OR IGNORE INTO sample_tags (sample_id, tag, source)
                        VALUES (:sample_id, :tag, 'golden')
                        """),
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
                text("""
                    INSERT OR IGNORE INTO sample_embeddings
                        (sample_id, model_id, embedding, embedding_format, source_hash)
                    VALUES (:sample_id, :model_id, :embedding, :embedding_format, :source_hash)
                    """),
                {
                    "sample_id": sample_id,
                    "model_id": model_id,
                    "embedding": vector.tobytes(),
                    "embedding_format": "float32",
                    "source_hash": source_hash,
                },
            )

    return model_id


def seed_tier_b_clap_catalog(
    db_path: Path,
    suite: dict[str, Any],
    *,
    work_root: Path,
) -> tuple[int, dict[str, Path]]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    os.environ["SAMPLE_BRAIN_DB_PATH"] = str(db_path)
    set_db_path(env={"SAMPLE_BRAIN_DB_PATH": str(db_path)})
    config.DB_PATH = db_path
    init_db()

    audio_dir = work_root / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    try:
        backend = ClapEmbeddingBackend()
        info = backend.model_info()
    except Exception as exc:
        raise EmbeddingBackendUnavailableError(
            "CLAP backend is not available for Tier-B search quality benchmark."
        ) from exc

    model_id = upsert_embedding_model(
        provider=info.provider,
        model_name=info.model_name,
        model_version=info.model_version or "1",
        embedding_dim=info.embedding_dim,
        modality=info.modality,
    )

    catalog = suite.get("catalog") or {}
    samples = catalog.get("samples") or []
    fixture_paths: dict[str, Path] = {}
    engine = get_engine()

    for sample in samples:
        sample_id = int(sample["id"])
        fixture_name = str(sample["fixture_name"])
        fixture_type = str(sample["fixture_type"])
        fixture_params = sample.get("fixture_params") or {}
        wav_path = generate_search_quality_fixture(
            audio_dir,
            fixture_name,
            fixture_type,
            fixture_params,
        )
        fixture_paths[fixture_name] = wav_path
        source_hash = _path_hash(wav_path)

        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO samples (id, path, hash, duration)
                    VALUES (:id, :path, :hash, :duration)
                    """),
                {
                    "id": sample_id,
                    "path": str(wav_path),
                    "hash": source_hash,
                    "duration": float(sample.get("duration", 1.0)),
                },
            )
            conn.execute(
                text("""
                    INSERT INTO features (sample_id, bpm, key, pred_type, class)
                    VALUES (:sample_id, :bpm, :key, :pred_type, :class)
                    """),
                {
                    "sample_id": sample_id,
                    "bpm": sample.get("bpm"),
                    "key": sample.get("key"),
                    "pred_type": sample.get("pred_type"),
                    "class": sample.get("sample_class"),
                },
            )
            for tag in sample.get("tags") or []:
                conn.execute(
                    text("""
                        INSERT OR IGNORE INTO sample_tags (sample_id, tag, source)
                        VALUES (:sample_id, :tag, 'golden')
                        """),
                    {"sample_id": sample_id, "tag": str(tag)},
                )

        vector = backend.embed_audio(str(wav_path))
        arr = np.asarray(
            vector.vector if hasattr(vector, "vector") else vector,
            dtype=np.float32,
        )
        insert_sample_embedding(
            sample_id=sample_id,
            model_id=model_id,
            embedding=arr.tobytes(),
            embedding_format="numpy.float32",
            source_hash=source_hash,
        )

    return model_id, fixture_paths


def _resolve_query_audio(
    raw_query: dict[str, Any],
    fixture_paths: dict[str, Path],
) -> str | None:
    if raw_query.get("query_audio"):
        return str(raw_query["query_audio"])
    fixture_name = raw_query.get("query_audio_fixture")
    if fixture_name:
        path = fixture_paths.get(str(fixture_name))
        if path is None:
            raise ValueError(f"Unknown query_audio_fixture: {fixture_name}")
        return str(path)
    return None


def run_search_quality_benchmark(
    suite_path: Path,
    *,
    work_dir: Path | None = None,
) -> SearchQualityBenchmarkResult:
    suite = load_search_quality_suite(suite_path)
    tier = str(suite.get("tier", "A"))
    defaults = suite.get("defaults") or {}
    default_topk = int(defaults.get("topk", 10))
    default_model_id = int(defaults.get("model_id", 1))
    default_backend = str(defaults.get("backend", "noop"))

    work_root = work_dir or Path(".bench_search_quality")
    work_root.mkdir(parents=True, exist_ok=True)
    db_path = work_root / "golden_catalog.db"

    fixture_paths: dict[str, Path] = {}
    if tier == "B":
        seeded_model_id, fixture_paths = seed_tier_b_clap_catalog(
            db_path,
            suite,
            work_root=work_root,
        )
    else:
        seeded_model_id = seed_golden_catalog(db_path, suite)
    if default_model_id != seeded_model_id:
        default_model_id = seeded_model_id

    query_results: list[QueryEvalResult] = []
    metric_rows: list[dict[str, float]] = []
    class_metric_rows: list[tuple[str, dict[str, float]]] = []
    mode_metric_rows: list[tuple[str, dict[str, float]]] = []
    style_metric_rows: list[tuple[str, dict[str, float]]] = []
    mode_class_metric_rows: list[tuple[tuple[str, str], dict[str, float]]] = []
    mode_class_buckets: dict[tuple[str, str], list[str]] = {}
    mode_class_neg_violations: dict[tuple[str, str], int] = {}
    bucket_labels: list[str] = []

    for raw_query in suite.get("queries") or []:
        if raw_query.get("eval_excluded"):
            continue
        query_id = str(raw_query["id"])
        mode = str(raw_query.get("mode", "vector"))
        query_class = raw_query.get("query_class")
        query_style = raw_query.get("query_style")
        topk = int(raw_query.get("topk", default_topk))
        relevant_ids = {
            int(value) for value in raw_query.get("relevant_sample_ids") or []
        }
        negative_ids = {
            int(value) for value in raw_query.get("negative_sample_ids") or []
        }
        filters = _filters_from_mapping(raw_query.get("filters"))
        hybrid = _hybrid_from_mapping(raw_query.get("hybrid"))
        must_recall_k = raw_query.get("must_recall_within_k")
        backend_name = str(raw_query.get("backend", default_backend))

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
            try:
                query_audio = (
                    _resolve_query_audio(raw_query, fixture_paths)
                    if mode == "audio"
                    else None
                )
            except ValueError as exc:
                query_results.append(
                    QueryEvalResult(
                        query_id=query_id,
                        query_class=query_class,
                        mode=mode,
                        ranked_ids=[],
                        metrics={},
                        filter_compliance=0.0,
                        passed_must_recall=False,
                        negatives_in_top5=0,
                        negatives_in_top10=0,
                        failure_bucket="error",
                        error=str(exc),
                    )
                )
                bucket_labels.append("error")
                continue

            result = collect_search_hits(
                query=raw_query.get("text") if mode == "text" else None,
                query_audio=query_audio,
                model_id=default_model_id,
                topk=topk,
                backend_name=backend_name,
                search_backend="numpy",
                hybrid_query=hybrid,
                search_filters=filters,
            )
        else:
            query_results.append(
                QueryEvalResult(
                    query_id=query_id,
                    query_class=query_class,
                    mode=mode,
                    ranked_ids=[],
                    metrics={},
                    filter_compliance=0.0,
                    passed_must_recall=False,
                    negatives_in_top5=0,
                    negatives_in_top10=0,
                    failure_bucket="error",
                    error=f"Unknown query mode: {mode}",
                )
            )
            bucket_labels.append("error")
            continue

        if result.error or result.info:
            query_results.append(
                QueryEvalResult(
                    query_id=query_id,
                    query_class=query_class,
                    mode=mode,
                    ranked_ids=[],
                    metrics={},
                    filter_compliance=0.0,
                    passed_must_recall=False,
                    negatives_in_top5=0,
                    negatives_in_top10=0,
                    failure_bucket="error",
                    error=result.error or result.info,
                )
            )
            bucket_labels.append("error")
            continue

        ranked_ids = [hit.sample_id for hit in result.hits]
        allowed_ids = None
        if filters is not None and filters.active():
            from .search_filters import resolve_filtered_sample_ids

            allowed_ids = resolve_filtered_sample_ids(filters)

        metrics = summarize_query_metrics(ranked_ids, relevant_ids)
        metric_rows.append(metrics)
        if query_class:
            class_metric_rows.append((str(query_class), metrics))
        mode_metric_rows.append((mode, metrics))
        if mode == "text" and query_style:
            style_metric_rows.append((str(query_style), metrics))

        passed_must_recall = True
        if must_recall_k is not None:
            from .search_eval import recall_at_k

            passed_must_recall = (
                recall_at_k(ranked_ids, relevant_ids, int(must_recall_k)) >= 1.0
            )

        neg_top5 = negatives_in_top_k(ranked_ids, negative_ids, 5)
        neg_top10 = negatives_in_top_k(ranked_ids, negative_ids, 10)
        bucket = assign_failure_bucket(
            metrics,
            negatives_in_top5=neg_top5,
            passed_must_recall=passed_must_recall,
            error=None,
        )
        bucket_labels.append(bucket)

        if query_class:
            mc_key = (mode, str(query_class))
            mode_class_metric_rows.append((mc_key, metrics))
            mode_class_buckets.setdefault(mc_key, []).append(bucket)
            if neg_top5 > 0:
                mode_class_neg_violations[mc_key] = mode_class_neg_violations.get(mc_key, 0) + 1

        query_results.append(
            QueryEvalResult(
                query_id=query_id,
                query_class=query_class,
                mode=mode,
                ranked_ids=ranked_ids,
                metrics=metrics,
                filter_compliance=filter_compliance(ranked_ids, allowed_ids),
                passed_must_recall=passed_must_recall,
                negatives_in_top5=neg_top5,
                negatives_in_top10=neg_top10,
                failure_bucket=bucket,
                query_style=str(query_style) if query_style else None,
            )
        )

    summary = aggregate_metric_summaries(metric_rows)
    thresholds = suite.get("thresholds") or {}

    # Build mode+class summaries
    mode_class_summaries: list[ModeClassEvaluationSummary] = []
    for grouped in aggregate_metric_summaries_by_group(mode_class_metric_rows):
        mc_key = grouped.group_key
        mode, query_class = mc_key
        grouped_summary = grouped.summary
        buckets = failure_bucket_counts(mode_class_buckets.get(mc_key, []))
        hard_neg = mode_class_neg_violations.get(mc_key, 0)
        mode_class_summaries.append(
            ModeClassEvaluationSummary(
                mode=mode,
                query_class=query_class,
                summary=grouped_summary,
                query_count=grouped_summary.query_count,
                failure_buckets=buckets,
                hard_negative_violations=hard_neg,
            )
        )
    # Sort deterministically: mode first, then query_class
    mode_class_summaries.sort(key=lambda x: (x.mode, x.query_class))

    return SearchQualityBenchmarkResult(
        suite_path=suite_path,
        tier=tier,
        summary=summary,
        query_results=tuple(query_results),
        thresholds={key: float(value) for key, value in thresholds.items()},
        class_summaries=tuple(aggregate_metric_summaries_by_group(class_metric_rows)),
        mode_summaries=tuple(aggregate_metric_summaries_by_group(mode_metric_rows)),
        style_summaries=tuple(aggregate_metric_summaries_by_group(style_metric_rows)),
        failure_buckets=failure_bucket_counts(bucket_labels),
        mode_class_summaries=tuple(mode_class_summaries),
    )


def print_search_quality_report(result: SearchQualityBenchmarkResult) -> None:
    checks = result.threshold_pass()
    print(
        f"suite={result.suite_path} tier={result.tier} queries={result.summary.query_count}"
    )
    print(
        "mean_precision_at_1="
        f"{result.summary.precision_at_1:.3f} "
        f"mean_precision_at_5={result.summary.precision_at_5:.3f} "
        f"mean_recall_at_10={result.summary.recall_at_10:.3f} "
        f"mrr={result.summary.mrr:.3f}"
    )
    for key, passed in checks.items():
        print(f"gate_{key}={'PASS' if passed else 'FAIL'}")
    if result.class_summaries:
        print("per_query_class:")
        for row in result.class_summaries:
            print(
                f"  class={row.group_key} "
                f"p@5={row.summary.precision_at_5:.3f} "
                f"mrr={row.summary.mrr:.3f} "
                f"queries={row.summary.query_count}"
            )
    if result.mode_summaries:
        print("per_mode:")
        for row in result.mode_summaries:
            print(
                f"  mode={row.group_key} "
                f"p@5={row.summary.precision_at_5:.3f} "
                f"mrr={row.summary.mrr:.3f} "
                f"queries={row.summary.query_count}"
            )
    if result.style_summaries:
        print("per_query_style:")
        for row in result.style_summaries:
            print(
                f"  style={row.group_key} "
                f"p@5={row.summary.precision_at_5:.3f} "
                f"mrr={row.summary.mrr:.3f} "
                f"queries={row.summary.query_count}"
            )
    if result.mode_class_summaries:
        print("per_mode_query_class:")
        for row in result.mode_class_summaries:
            print(
                f"  mode={row.mode} class={row.query_class} "
                f"p@5={row.summary.precision_at_5:.3f} "
                f"mrr={row.summary.mrr:.3f} "
                f"queries={row.query_count} "
                f"hard_negative_violations={row.hard_negative_violations}"
            )
            # Failure buckets per mode+class
            for label in FAILURE_BUCKET_LABELS:
                count = row.failure_buckets.get(label, 0)
                if count:
                    print(f"    {label}={count}")
    if result.failure_buckets:
        print("failure_buckets:")
        for label in FAILURE_BUCKET_LABELS:
            count = result.failure_buckets.get(label, 0)
            if count:
                print(f"  {label}={count}")
    for row in result.query_results:
        if row.error:
            print(f"query={row.query_id} error={row.error}")
            continue
        print(
            f"query={row.query_id} "
            f"class={row.query_class or '-'} "
            f"mode={row.mode} "
            f"style={row.query_style or '-'} "
            f"p@1={row.metrics['precision_at_1']:.3f} "
            f"p@5={row.metrics['precision_at_5']:.3f} "
            f"mrr={row.metrics['mrr']:.3f} "
            f"neg@5={row.negatives_in_top5} "
            f"bucket={row.failure_bucket} "
            f"must_recall={'PASS' if row.passed_must_recall else 'FAIL'}"
        )
