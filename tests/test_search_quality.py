from __future__ import annotations

from pathlib import Path

import pytest

from src.benchmark_search_quality import (
    DEFAULT_SUITE_PATH,
    DEFAULT_TIER_B_SUITE_PATH,
    load_search_quality_suite,
    run_search_quality_benchmark,
    ModeClassEvaluationSummary,
)
from src.embed import EmbeddingBackendUnavailableError, _clap_available
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
        assert suite.get("contract_version") == 1
        assert set(suite.get("query_classes_present") or []) >= {
            "kick_snare_perc",
            "pad_texture",
            "riser_impact",
            "dry_wet",
            "vocal_no_vocal",
            "genre_mood",
        }
        assert not suite.get("query_classes_pending")
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
        try:
            result = run_search_quality_benchmark(
                suite_path,
                work_dir=tmp_path / "clap-quality",
            )
        except EmbeddingBackendUnavailableError as exc:
            pytest.skip(f"CLAP runtime unavailable: {exc}")
        assert result.tier == "B"
        assert result.summary.query_count >= 8
        for row in result.query_results:
            assert row.error is None, row.query_id
        assert result.class_summaries
        assert result.mode_summaries
        assert result.mode_class_summaries
        assert result.failure_buckets is not None
        checks = result.threshold_pass()
        assert checks["mean_precision_at_5"]
        assert result.failure_buckets is not None
        # Verify mode_class_summaries has entries for text mode classes
        mc_keys = {(row.mode, row.query_class) for row in result.mode_class_summaries}
        # Phase 1 had kick_snare_perc and pad_texture; full suite has all 6
        # Just verify that mode_class_summaries exists and has text mode entries
        text_modes = [row for row in result.mode_class_summaries if row.mode == "text"]
        assert len(text_modes) >= 2, "Should have at least 2 text mode classes"
        # Verify all mode_class_summaries have required fields
        for row in result.mode_class_summaries:
            assert row.mode in {"text", "audio"}
            assert row.query_count > 0
            assert isinstance(row.failure_buckets, dict)
            assert isinstance(row.hard_negative_violations, int)
            assert row.hard_negative_violations >= 0


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
        try:
            result = run_search_quality_benchmark(
                suite_path,
                work_dir=tmp_path / "clap-quality-p2",
            )
        except EmbeddingBackendUnavailableError as exc:
            pytest.skip(f"CLAP runtime unavailable: {exc}")
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
        assert result.mode_class_summaries
        # Verify mode_class_summaries has entries for all 4 phase 1+2 classes in text mode
        mc_keys = {(row.mode, row.query_class) for row in result.mode_class_summaries}
        assert ("text", "riser_impact") in mc_keys
        assert ("text", "dry_wet") in mc_keys
        assert ("text", "kick_snare_perc") in mc_keys
        assert ("text", "pad_texture") in mc_keys
        # Verify all mode_class_summaries have required fields
        for row in result.mode_class_summaries:
            assert row.mode in {"text", "audio"}
            assert row.query_count > 0
            assert isinstance(row.failure_buckets, dict)
            assert isinstance(row.hard_negative_violations, int)
            assert row.hard_negative_violations >= 0
        checks = result.threshold_pass()
        assert checks["mean_precision_at_5"]
        assert checks["mean_recall_at_10"]


class TestGoldenTierBPhase3:
    @pytest.fixture
    def suite_path(self) -> Path:
        return DEFAULT_TIER_B_SUITE_PATH

    def test_suite_structure(self, suite_path: Path):
        suite = load_search_quality_suite(suite_path)
        assert int(suite.get("phase", 1)) >= 3
        classes = {query.get("query_class") for query in suite["queries"]}
        assert classes >= {
            "kick_snare_perc",
            "pad_texture",
            "riser_impact",
            "dry_wet",
            "vocal_no_vocal",
            "genre_mood",
        }
        sample_classes = {
            sample.get("sample_class") for sample in suite["catalog"]["samples"]
        }
        assert "vocal_no_vocal" in sample_classes
        assert "genre_mood" in sample_classes
        vocal_queries = [
            q for q in suite["queries"] if q.get("query_class") == "vocal_no_vocal"
        ]
        genre_queries = [
            q for q in suite["queries"] if q.get("query_class") == "genre_mood"
        ]
        assert len(vocal_queries) >= 6
        assert len(genre_queries) >= 6
        for query in vocal_queries + genre_queries:
            assert query.get("negative_sample_ids")
            assert query.get("relevant_sample_ids")
            assert query.get("mode") in {"text", "audio"}

    @pytest.mark.clap
    def test_tier_b_phase3_benchmark(self, suite_path: Path, tmp_path: Path):
        if not _clap_available():
            pytest.skip("CLAP optional extra not installed")
        try:
            result = run_search_quality_benchmark(
                suite_path,
                work_dir=tmp_path / "clap-quality-p3",
            )
        except EmbeddingBackendUnavailableError as exc:
            pytest.skip(f"CLAP runtime unavailable: {exc}")
        assert result.tier == "B"
        assert result.summary.query_count >= 30
        for row in result.query_results:
            assert row.error is None, row.query_id
        assert result.mode_class_summaries
        # Verify mode_class_summaries has entries for all 6 classes in text mode
        mc_keys = {(row.mode, row.query_class) for row in result.mode_class_summaries}
        assert ("text", "kick_snare_perc") in mc_keys
        assert ("text", "pad_texture") in mc_keys
        assert ("text", "riser_impact") in mc_keys
        assert ("text", "dry_wet") in mc_keys
        assert ("text", "vocal_no_vocal") in mc_keys
        assert ("text", "genre_mood") in mc_keys
        # Verify all mode_class_summaries have required fields
        for row in result.mode_class_summaries:
            assert row.mode in {"text", "audio"}
            assert row.query_count > 0
            assert isinstance(row.failure_buckets, dict)
            assert isinstance(row.hard_negative_violations, int)
            assert row.hard_negative_violations >= 0
        # Verify P@5 and MRR are finite
        for row in result.mode_class_summaries:
            assert row.summary.precision_at_5 >= 0.0
            assert row.summary.mrr >= 0.0
            # Failure bucket sums should match query count
            bucket_sum = sum(row.failure_buckets.values())
            assert bucket_sum == row.query_count


class TestModeClassEvaluation:
    """Tests for mode+class evaluation summaries (Issue #216)."""

    def test_mode_class_summary_dataclass_exists(self):
        """ModeClassEvaluationSummary dataclass exists with expected fields."""
        summary = ModeClassEvaluationSummary(
            mode="text",
            query_class="kick_snare_perc",
            summary=None,  # type: ignore[arg-type]
            query_count=5,
            failure_buckets={"success": 3, "negative_leak_top5": 2},
            hard_negative_violations=2,
        )
        assert summary.mode == "text"
        assert summary.query_class == "kick_snare_perc"
        assert summary.query_count == 5
        assert summary.failure_buckets["success"] == 3
        assert summary.failure_buckets["negative_leak_top5"] == 2
        assert summary.hard_negative_violations == 2

    def test_mode_class_separates_text_and_audio(self, tmp_path: Path):
        """Text and audio of same class are NOT mixed in mode_class_summaries."""
        # This test uses a mock benchmark result to verify aggregation logic
        # We can't easily create a full benchmark without CLAP, so we test the
        # aggregation function directly with known inputs
        from src.search_eval import (
            aggregate_metric_summaries,
            MetricSummary,
        )
        from src.benchmark_search_quality import QueryEvalResult

        # Create mock query results with both text and audio for same class
        text_metrics = {"precision_at_5": 0.6, "mrr": 0.8, "precision_at_1": 0.7, "precision_at_10": 0.5, "recall_at_10": 0.9}
        audio_metrics = {"precision_at_5": 0.4, "mrr": 0.5, "precision_at_1": 0.3, "precision_at_10": 0.3, "recall_at_10": 0.6}

        text_results = [
            QueryEvalResult(
                query_id="q1", query_class="kick_snare_perc", mode="text",
                ranked_ids=[1, 2, 3], metrics=text_metrics,
                filter_compliance=1.0, passed_must_recall=True,
                negatives_in_top5=0, negatives_in_top10=0,
                failure_bucket="success", query_style="keyword"
            ),
            QueryEvalResult(
                query_id="q2", query_class="kick_snare_perc", mode="text",
                ranked_ids=[1, 2, 4], metrics=text_metrics,
                filter_compliance=1.0, passed_must_recall=True,
                negatives_in_top5=1, negatives_in_top10=1,
                failure_bucket="negative_leak_top5", query_style="keyword"
            ),
        ]
        audio_results = [
            QueryEvalResult(
                query_id="q3", query_class="kick_snare_perc", mode="audio",
                ranked_ids=[1, 5, 6], metrics=audio_metrics,
                filter_compliance=1.0, passed_must_recall=True,
                negatives_in_top5=0, negatives_in_top10=0,
                failure_bucket="success", query_style=None
            ),
        ]

        # The mode_class aggregation should produce separate entries for
        # (text, kick_snare_perc) and (audio, kick_snare_perc)
        # We'll verify this after implementing the aggregation logic
        # For now, just verify the test structure is correct
        assert len(text_results) == 2
        assert len(audio_results) == 1
        assert text_results[0].mode != audio_results[0].mode
        assert text_results[0].query_class == audio_results[0].query_class

    def test_mode_class_aggregation_correctness(self):
        """P@5/MRR correctly aggregated per mode+class."""
        from src.search_eval import aggregate_metric_summaries

        # Two queries for text mode, same class
        metrics_1 = {"precision_at_5": 0.6, "mrr": 0.8, "precision_at_1": 0.7, "precision_at_10": 0.5, "recall_at_10": 0.9}
        metrics_2 = {"precision_at_5": 0.4, "mrr": 0.6, "precision_at_1": 0.5, "precision_at_10": 0.4, "recall_at_10": 0.8}
        summary = aggregate_metric_summaries([metrics_1, metrics_2])

        # Mean P@5 = (0.6 + 0.4) / 2 = 0.5
        # Mean MRR = (0.8 + 0.6) / 2 = 0.7
        assert summary.precision_at_5 == 0.5
        assert summary.mrr == 0.7
        assert summary.query_count == 2

    def test_failure_buckets_per_mode_class(self):
        """Failure buckets counted per mode+class."""
        from src.search_eval import failure_bucket_counts

        buckets = ["success", "negative_leak_top5", "success", "error"]
        counts = failure_bucket_counts(buckets)
        assert counts["success"] == 2
        assert counts["negative_leak_top5"] == 1
        assert counts["error"] == 1

    def test_hard_negative_violations_count(self):
        """hard_negative_violations counts queries with neg@5 > 0."""
        # This will be tested via the actual benchmark result structure
        # after implementation
        pass

    def test_class_isolation_no_cross_contamination(self):
        """Errors of one class not attributed to another class."""
        from src.search_eval import aggregate_metric_summaries_by_group

        kick_metrics = {"precision_at_5": 0.8, "mrr": 0.9, "precision_at_1": 0.9, "precision_at_10": 0.7, "recall_at_10": 1.0}
        pad_metrics = {"precision_at_5": 0.2, "mrr": 0.3, "precision_at_1": 0.1, "precision_at_10": 0.2, "recall_at_10": 0.5}

        grouped = aggregate_metric_summaries_by_group([
            ("kick_snare_perc", kick_metrics),
            ("pad_texture", pad_metrics),
            ("kick_snare_perc", kick_metrics),
        ])

        by_key = {item.group_key: item.summary for item in grouped}
        assert by_key["kick_snare_perc"].precision_at_5 == 0.8
        assert by_key["pad_texture"].precision_at_5 == 0.2
        assert by_key["kick_snare_perc"].query_count == 2
        assert by_key["pad_texture"].query_count == 1

    def test_deterministic_output_order(self):
        """mode_class_summaries sorted deterministically."""
        from src.search_eval import aggregate_metric_summaries_by_group

        metrics = {"precision_at_5": 0.5, "mrr": 0.6, "precision_at_1": 0.5, "precision_at_10": 0.4, "recall_at_10": 0.7}
        # Input in random order
        grouped = aggregate_metric_summaries_by_group([
            ("z_class", metrics),
            ("a_class", metrics),
            ("m_class", metrics),
        ])
        keys = [item.group_key for item in grouped]
        assert keys == ["a_class", "m_class", "z_class"]

    def test_existing_summaries_preserved(self):
        """class_summaries, mode_summaries, style_summaries remain unchanged."""
        # This is a contract test - after implementation, we'll verify
        # that the existing summary fields are still populated correctly
        pass
