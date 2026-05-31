from __future__ import annotations

from pathlib import Path

import pytest

from src.benchmark_search_quality import (
    DEFAULT_SUITE_PATH,
    load_search_quality_suite,
    run_search_quality_benchmark,
)
from src.search_eval import (
    aggregate_metric_summaries,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    summarize_query_metrics,
)


class TestSearchEvalMetrics:
    def test_precision_at_k(self):
        ranked = [1, 2, 3, 4, 5]
        relevant = {1, 3, 99}
        assert precision_at_k(ranked, relevant, 1) == 1.0
        assert precision_at_k(ranked, relevant, 5) == 0.4

    def test_recall_at_k(self):
        ranked = [1, 2, 3, 4, 5]
        relevant = {1, 3, 99}
        assert recall_at_k(ranked, relevant, 5) == pytest.approx(2 / 3)
        assert recall_at_k(ranked, relevant, 1) == pytest.approx(1 / 3)

    def test_reciprocal_rank(self):
        assert reciprocal_rank([5, 2, 1], {1}) == pytest.approx(1 / 3)
        assert reciprocal_rank([5, 2, 1], {9}) == 0.0

    def test_summarize_and_aggregate(self):
        row = summarize_query_metrics([1, 2, 3], {1, 2})
        summary = aggregate_metric_summaries([row, row])
        assert summary.query_count == 2
        assert summary.precision_at_1 == row["precision_at_1"]


class TestGoldenTierARegression:
    @pytest.fixture
    def suite_path(self) -> Path:
        return DEFAULT_SUITE_PATH

    @pytest.fixture
    def benchmark_result(self, suite_path: Path, tmp_path: Path):
        return run_search_quality_benchmark(
            suite_path,
            work_dir=tmp_path / "search-quality",
        )

    def test_suite_loads(self, suite_path: Path):
        suite = load_search_quality_suite(suite_path)
        assert suite["tier"] == "A"
        assert len(suite["queries"]) >= 8

    def test_all_queries_succeed(self, benchmark_result):
        for row in benchmark_result.query_results:
            assert row.error is None, row.query_id

    def test_threshold_gates_pass(self, benchmark_result):
        checks = benchmark_result.threshold_pass()
        assert checks["mean_precision_at_1"]
        assert checks["mean_precision_at_5"]
        assert checks["mean_recall_at_10"]
        assert checks["must_recall_queries"]
        assert checks["filter_compliance"]

    def test_frozen_baseline_precision_at_5(self, benchmark_result):
        assert benchmark_result.summary.precision_at_5 >= 0.50


@pytest.mark.clap
class TestGoldenTierBPlaceholder:
    def test_clap_suite_is_documented(self):
        suite_path = (
            Path(__file__).resolve().parent
            / "fixtures"
            / "search_quality"
            / "golden_v2_clap.yaml"
        )
        suite = load_search_quality_suite(suite_path)
        assert suite["tier"] == "B"
        assert suite["defaults"]["backend"] == "clap"
