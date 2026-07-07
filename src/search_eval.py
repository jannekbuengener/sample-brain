from __future__ import annotations

from dataclasses import dataclass


FAILURE_BUCKET_LABELS: tuple[str, ...] = (
    "success",
    "negative_leak_top5",
    "zero_precision_at_5",
    "zero_mrr",
    "must_recall_fail",
    "error",
)


@dataclass(frozen=True)
class MetricSummary:
    precision_at_1: float
    precision_at_5: float
    precision_at_10: float
    recall_at_10: float
    mrr: float
    query_count: int


@dataclass(frozen=True)
class GroupedMetricSummary:
    group_key: str
    summary: MetricSummary


def precision_at_k(ranked_ids: list[int], relevant_ids: set[int], k: int) -> float:
    if k <= 0:
        return 0.0
    top_k = ranked_ids[:k]
    if not top_k:
        return 0.0
    hits = sum(1 for sample_id in top_k if sample_id in relevant_ids)
    return hits / k


def recall_at_k(ranked_ids: list[int], relevant_ids: set[int], k: int) -> float:
    if k <= 0 or not relevant_ids:
        return 0.0
    top_k = ranked_ids[:k]
    hits = sum(1 for sample_id in top_k if sample_id in relevant_ids)
    return hits / len(relevant_ids)


def reciprocal_rank(ranked_ids: list[int], relevant_ids: set[int]) -> float:
    for index, sample_id in enumerate(ranked_ids, start=1):
        if sample_id in relevant_ids:
            return 1.0 / index
    return 0.0


def negatives_in_top_k(
    ranked_ids: list[int],
    negative_ids: set[int],
    k: int,
) -> int:
    if k <= 0 or not negative_ids:
        return 0
    return sum(1 for sample_id in ranked_ids[:k] if sample_id in negative_ids)


def summarize_query_metrics(
    ranked_ids: list[int],
    relevant_ids: set[int],
) -> dict[str, float]:
    return {
        "precision_at_1": precision_at_k(ranked_ids, relevant_ids, 1),
        "precision_at_5": precision_at_k(ranked_ids, relevant_ids, 5),
        "precision_at_10": precision_at_k(ranked_ids, relevant_ids, 10),
        "recall_at_10": recall_at_k(ranked_ids, relevant_ids, 10),
        "mrr": reciprocal_rank(ranked_ids, relevant_ids),
    }


def aggregate_metric_summaries(
    per_query: list[dict[str, float]],
) -> MetricSummary:
    if not per_query:
        return MetricSummary(0.0, 0.0, 0.0, 0.0, 0.0, 0)

    def mean(key: str) -> float:
        return sum(row[key] for row in per_query) / len(per_query)

    return MetricSummary(
        precision_at_1=mean("precision_at_1"),
        precision_at_5=mean("precision_at_5"),
        precision_at_10=mean("precision_at_10"),
        recall_at_10=mean("recall_at_10"),
        mrr=mean("mrr"),
        query_count=len(per_query),
    )


def aggregate_metric_summaries_by_group(
    rows: list[tuple[str, dict[str, float]]],
) -> list[GroupedMetricSummary]:
    grouped: dict[str, list[dict[str, float]]] = {}
    for group_key, metrics in rows:
        grouped.setdefault(group_key, []).append(metrics)
    return [
        GroupedMetricSummary(group_key=key, summary=aggregate_metric_summaries(values))
        for key, values in sorted(grouped.items())
    ]


def filter_compliance(
    ranked_ids: list[int],
    allowed_ids: set[int] | None,
) -> float:
    if allowed_ids is None:
        return 1.0
    if not ranked_ids:
        return 1.0
    compliant = sum(1 for sample_id in ranked_ids if sample_id in allowed_ids)
    return compliant / len(ranked_ids)


def assign_failure_bucket(
    metrics: dict[str, float],
    *,
    negatives_in_top5: int,
    passed_must_recall: bool,
    error: str | None,
) -> str:
    if error:
        return "error"
    if negatives_in_top5 > 0:
        return "negative_leak_top5"
    if not passed_must_recall:
        return "must_recall_fail"
    if metrics.get("precision_at_5", 0.0) == 0.0:
        return "zero_precision_at_5"
    if metrics.get("mrr", 0.0) == 0.0:
        return "zero_mrr"
    return "success"


def failure_bucket_counts(buckets: list[str]) -> dict[str, int]:
    counts = {label: 0 for label in FAILURE_BUCKET_LABELS}
    for bucket in buckets:
        counts[bucket] = counts.get(bucket, 0) + 1
    return counts
