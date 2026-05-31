from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MetricSummary:
    precision_at_1: float
    precision_at_5: float
    precision_at_10: float
    recall_at_10: float
    mrr: float
    query_count: int


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
