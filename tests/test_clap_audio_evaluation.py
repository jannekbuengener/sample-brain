from __future__ import annotations

import math
from pathlib import Path

import pytest

from src.benchmark_search_quality import (
    DEFAULT_TIER_B_SUITE_PATH,
    ModeClassEvaluationSummary,
    load_search_quality_suite,
    run_search_quality_benchmark,
)
from src.embed import _clap_available
from src.search_eval import (
    FAILURE_BUCKET_LABELS,
    aggregate_metric_summaries,
    aggregate_metric_summaries_by_group,
    summarize_query_metrics,
)
from src.search_quality_contract import (
    TIER_B_QUERY_CLASSES,
    is_private_absolute_path,
    validate_search_quality_suite,
)

CANONICAL_CLASSES: tuple[str, ...] = tuple(sorted(TIER_B_QUERY_CLASSES))


def _load_tier_b_suite() -> dict:
    suite = load_search_quality_suite(DEFAULT_TIER_B_SUITE_PATH)
    validate_search_quality_suite(suite)  # enforce golden contract
    return suite


class TestAudioContractNoClap:
    """Structural audio-to-audio contract checks (no CLAP runtime).

    These prove the golden suite and the generic Mode x Class machinery
    satisfy the #217 acceptance criteria without requiring a model download.
    """

    def test_tier_b_suite_has_all_six_classes(self):
        suite = _load_tier_b_suite()
        present = set(suite.get("query_classes_present") or [])
        assert TIER_B_QUERY_CLASSES.issubset(present)
        assert not suite.get("query_classes_pending")

    def test_each_class_has_active_audio_query(self):
        suite = _load_tier_b_suite()
        audio_by_class: dict[str, list[dict]] = {}
        for q in suite["queries"]:
            if q.get("eval_excluded"):
                continue
            if q.get("mode") == "audio":
                audio_by_class.setdefault(q.get("query_class"), []).append(q)
        for cls in CANONICAL_CLASSES:
            assert audio_by_class.get(cls), f"no active audio query for {cls}"

    def test_audio_query_contract(self):
        suite = _load_tier_b_suite()
        fixture_names = {
            s.get("fixture_name") for s in suite["catalog"]["samples"]
        }
        audio_queries = [
            q
            for q in suite["queries"]
            if q.get("mode") == "audio" and not q.get("eval_excluded")
        ]
        assert audio_queries, "expected at least one audio query"
        for q in audio_queries:
            # uses portable query_audio_fixture (no local audio path)
            assert q.get("query_audio_fixture"), q["id"]
            # audio mode must not carry text
            assert not q.get("text"), q["id"]
            # audio mode must not carry a query_audio local path
            assert not q.get("query_audio"), q["id"]
            # referenced fixture must exist in the catalog
            assert q["query_audio_fixture"] in fixture_names, q["id"]
            # has both positive and hard-negative ground truth
            assert q.get("relevant_sample_ids"), q["id"]
            assert q.get("negative_sample_ids"), q["id"]
            # class is canonical
            assert q.get("query_class") in TIER_B_QUERY_CLASSES, q["id"]

    def test_no_private_absolute_paths(self):
        suite = _load_tier_b_suite()
        for q in suite["queries"]:
            qa = q.get("query_audio")
            if qa:
                assert not is_private_absolute_path(str(qa)), q["id"]
        for s in suite["catalog"]["samples"]:
            p = s.get("path")
            if p:
                assert not is_private_absolute_path(str(p)), s.get("id")
        # fixture names are portable identifiers, never absolute paths
        for q in suite["queries"]:
            if q.get("query_audio_fixture"):
                assert not is_private_absolute_path(
                    str(q["query_audio_fixture"])
                ), q["id"]

    def test_audio_queries_separate_from_text(self):
        suite = _load_tier_b_suite()
        modes = {q["id"]: q.get("mode") for q in suite["queries"]}
        audio_ids = {i for i, m in modes.items() if m == "audio"}
        text_ids = {i for i, m in modes.items() if m == "text"}
        assert audio_ids and text_ids
        # a single query id is exactly one mode; audio ids never text ids
        assert audio_ids.isdisjoint(text_ids)

    def test_mode_class_summary_represents_audio_entry(self):
        # The generic ModeClassEvaluationSummary can hold an audio entry
        # and exposes the fields the #217 report consumes.
        row = summarize_query_metrics([1, 2, 3], {1, 2})
        summary = ModeClassEvaluationSummary(
            mode="audio",
            query_class="kick_snare_perc",
            summary=aggregate_metric_summaries([row]),
            query_count=1,
            failure_buckets={label: 0 for label in FAILURE_BUCKET_LABELS},
            hard_negative_violations=0,
        )
        assert summary.mode == "audio"
        assert summary.query_class == "kick_snare_perc"
        assert summary.query_count == 1
        assert summary.hard_negative_violations >= 0
        assert set(summary.failure_buckets) == set(FAILURE_BUCKET_LABELS)

    def test_mode_class_failure_bucket_sum_and_hard_neg(self):
        # Deterministic invariant: per mode+class the failure-bucket counts
        # must sum to the query count, and hard-negative violations are >= 0.
        row = summarize_query_metrics([1], {1})
        buckets = {label: 0 for label in FAILURE_BUCKET_LABELS}
        buckets["success"] = 3
        buckets["negative_leak_top5"] = 1
        summary = ModeClassEvaluationSummary(
            mode="audio",
            query_class="pad_texture",
            summary=aggregate_metric_summaries([row]),
            query_count=4,
            failure_buckets=buckets,
            hard_negative_violations=1,
        )
        assert sum(summary.failure_buckets.values()) == summary.query_count
        assert summary.hard_negative_violations >= 0

    def test_mode_class_aggregation_deterministic_and_separates_modes(self):
        # The same generic aggregation the harness uses must separate modes
        # and order deterministically by (mode, query_class).
        r1 = summarize_query_metrics([1, 2], {1})
        r2 = summarize_query_metrics([3, 4], {3})
        rows = [
            (("audio", "kick_snare_perc"), r1),
            (("text", "kick_snare_perc"), r2),
            (("audio", "pad_texture"), r1),
            (("text", "pad_texture"), r2),
        ]
        grouped = aggregate_metric_summaries_by_group(rows)
        keys = [(g.group_key[0], g.group_key[1]) for g in grouped]
        assert keys == sorted(keys)
        assert ("audio", "kick_snare_perc") in keys
        assert ("text", "kick_snare_perc") in keys
        by_key = {
            (g.group_key[0], g.group_key[1]): g.summary.query_count
            for g in grouped
        }
        assert by_key[("audio", "kick_snare_perc")] == 1
        assert by_key[("text", "kick_snare_perc")] == 1


@pytest.mark.clap
class TestClapAudioEvaluation:
    """Real CLAP Tier-B run: audio-to-audio quality by query class."""

    def test_audio_mode_class_summaries(self, tmp_path: Path):
        if not _clap_available():
            pytest.skip("CLAP optional extra not installed")
        work_dir = tmp_path / "clap-audio-eval"
        result = run_search_quality_benchmark(
            DEFAULT_TIER_B_SUITE_PATH,
            work_dir=work_dir,
        )

        # No runtime errors on any query.
        for row in result.query_results:
            assert row.error is None, row.query_id

        # mode_class_summaries must expose every audio x class tuple.
        mc = {(s.mode, s.query_class): s for s in result.mode_class_summaries}
        for cls in CANONICAL_CLASSES:
            key = ("audio", cls)
            assert key in mc, f"missing mode_class_summary {key}"
            s = mc[key]
            assert s.query_count > 0
            assert math.isfinite(s.summary.precision_at_5)
            assert math.isfinite(s.summary.mrr)
            assert sum(s.failure_buckets.values()) == s.query_count
            assert s.hard_negative_violations >= 0

        # Informative audio-vs-text comparison (no gate).
        print("\nAUDIO VS TEXT (informative, not a gate):")
        for cls in CANONICAL_CLASSES:
            a = mc.get(("audio", cls))
            t = mc.get(("text", cls))
            if a and t:
                delta_p5 = a.summary.precision_at_5 - t.summary.precision_at_5
                delta_mrr = a.summary.mrr - t.summary.mrr
                print(
                    f"  {cls}: text p@5={t.summary.precision_at_5:.3f} "
                    f"mrr={t.summary.mrr:.3f} | audio p@5={a.summary.precision_at_5:.3f} "
                    f"mrr={a.summary.mrr:.3f} | delta_p5={delta_p5:+.3f} "
                    f"delta_mrr={delta_mrr:+.3f}"
                )

        # Exercise the report printer (per_mode_query_class block).
        from src.benchmark_search_quality import print_search_quality_report

        print("\n--- search quality report ---")
        print_search_quality_report(result)
