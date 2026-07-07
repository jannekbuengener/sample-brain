from __future__ import annotations

from pathlib import Path

import pytest

from src.benchmark_search_quality import (
    DEFAULT_SUITE_PATH,
    DEFAULT_TIER_B_SUITE_PATH,
    load_search_quality_suite,
    run_search_quality_benchmark,
)
from src.embed import _clap_available
from src.search_eval import (
    aggregate_metric_summaries,
    aggregate_metric_summaries_by_group,
    assign_failure_bucket,
    failure_bucket_counts,
    negatives_in_top_k,
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

    def test_negatives_in_top_k(self):
        ranked = [1, 2, 3, 4, 5]
        negatives = {2, 4, 99}
        assert negatives_in_top_k(ranked, negatives, 5) == 2
        assert negatives_in_top_k(ranked, negatives, 2) == 1

    def test_assign_failure_bucket(self):
        metrics = summarize_query_metrics([1, 2, 3], {1})
        assert (
            assign_failure_bucket(
                metrics,
                negatives_in_top5=0,
                passed_must_recall=True,
                error=None,
            )
            == "success"
        )
        assert (
            assign_failure_bucket(
                metrics,
                negatives_in_top5=1,
                passed_must_recall=True,
                error=None,
            )
            == "negative_leak_top5"
        )

    def test_aggregate_by_group(self):
        row_a = summarize_query_metrics([1, 2], {1})
        row_b = summarize_query_metrics([3, 4], {3})
        grouped = aggregate_metric_summaries_by_group(
            [("kick", row_a), ("pad", row_b), ("kick", row_a)]
        )
        by_key = {item.group_key: item.summary.query_count for item in grouped}
        assert by_key["kick"] == 2
        assert by_key["pad"] == 1

    def test_failure_bucket_counts(self):
        counts = failure_bucket_counts(["success", "success", "error"])
        assert counts["success"] == 2
        assert counts["error"] == 1


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


class TestGoldenTierBPhase1:
    @pytest.fixture
    def suite_path(self) -> Path:
        return DEFAULT_TIER_B_SUITE_PATH

    def test_suite_structure(self, suite_path: Path):
        suite = load_search_quality_suite(suite_path)
        assert suite["tier"] == "B"
        assert suite["defaults"]["backend"] == "clap"
        assert len(suite["catalog"]["samples"]) >= 10
        classes = {query.get("query_class") for query in suite["queries"]}
        assert "kick_snare_perc" in classes
        assert "pad_texture" in classes
        modes = {query.get("mode") for query in suite["queries"]}
        assert modes == {"text", "audio"}
        for query in suite["queries"]:
            assert query.get("relevant_sample_ids")
            assert query.get("negative_sample_ids")

    @pytest.mark.clap
    def test_tier_b_phase1_benchmark(self, suite_path: Path, tmp_path: Path):
        if not _clap_available():
            pytest.skip("CLAP optional extra not installed")
        result = run_search_quality_benchmark(
            suite_path,
            work_dir=tmp_path / "clap-quality",
        )
        assert result.tier == "B"
        assert result.summary.query_count >= 8
        for row in result.query_results:
            assert row.error is None, row.query_id
        assert result.class_summaries
        assert result.mode_summaries
        assert result.failure_buckets is not None
        checks = result.threshold_pass()
        assert checks["mean_precision_at_5"]
        assert result.failure_buckets is not None


class TestGoldenTierBPhase2:
    @pytest.fixture
    def suite_path(self) -> Path:
        return DEFAULT_TIER_B_SUITE_PATH

    def test_suite_structure(self, suite_path: Path):
        suite = load_search_quality_suite(suite_path)
        assert int(suite.get("phase", 1)) >= 2
        classes = {query.get("query_class") for query in suite["queries"]}
        assert "riser_impact" in classes
        assert "dry_wet" in classes
        assert classes >= {
            "kick_snare_perc",
            "pad_texture",
            "riser_impact",
            "dry_wet",
        }
        sample_classes = {
            sample.get("sample_class") for sample in suite["catalog"]["samples"]
        }
        assert "riser_impact" in sample_classes
        assert "dry_wet" in sample_classes
        riser_queries = [
            q for q in suite["queries"] if q.get("query_class") == "riser_impact"
        ]
        dry_wet_queries = [
            q for q in suite["queries"] if q.get("query_class") == "dry_wet"
        ]
        assert len(riser_queries) >= 6
        assert len(dry_wet_queries) >= 6
        text_queries = [q for q in suite["queries"] if q.get("mode") == "text"]
        styled = [q for q in text_queries if q.get("query_style")]
        assert len(styled) >= 10
        styles = {q.get("query_style") for q in styled}
        assert styles >= {"keyword", "natural_language", "exclusion"}
        for query in riser_queries + dry_wet_queries:
            assert query.get("negative_sample_ids")
            assert query.get("mode") in {"text", "audio"}

    @pytest.mark.clap
    def test_tier_b_phase2_benchmark(self, suite_path: Path, tmp_path: Path):
        if not _clap_available():
            pytest.skip("CLAP optional extra not installed")
        result = run_search_quality_benchmark(
            suite_path,
            work_dir=tmp_path / "clap-quality-p2",
        )
        assert result.tier == "B"
        assert result.summary.query_count >= 20
        for row in result.query_results:
            assert row.error is None, row.query_id
        class_keys = {row.group_key for row in result.class_summaries}
        assert "riser_impact" in class_keys
        assert "dry_wet" in class_keys
        style_keys = {row.group_key for row in result.style_summaries}
        assert "keyword" in style_keys
        assert "natural_language" in style_keys
        assert "exclusion" in style_keys
        checks = result.threshold_pass()
        assert checks["mean_precision_at_5"]
        assert checks["mean_recall_at_10"]
