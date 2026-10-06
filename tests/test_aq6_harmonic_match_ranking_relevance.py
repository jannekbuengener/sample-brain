"""Frozen AQ6 Harmonic Match ranking relevance contract tests (#1016).

TEST FREEZE: these assertions define the ranking-relevance freeze. Fix the
benchmark module / fixture generator — not these expectations — when red.
Do not tune product ranking weights to satisfy these tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src import aq6_harmonic_ranking_relevance as ranking
from src.aq6_harmonic_theory_truth_table import classify_theory_pair

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = REPO_ROOT / ranking.FIXTURE_RELPATH


class TestAq6RankingIdentities:
    def test_frozen_identities(self) -> None:
        assert ranking.BENCHMARK_ID == (
            "sample-brain.aq6.harmonic-ranking.relevance.v1"
        )
        assert ranking.DOCUMENT_TYPE == (
            "sample-brain.aq6.harmonic-ranking-relevance.v1"
        )
        assert ranking.BENCHMARK_VERSION == "1.0.0"
        assert ranking.DOMAIN_TOKEN == "aq6.ranking"
        assert ranking.THEORY_TRUTH_TABLE_ID == (
            "sample-brain.aq6.harmonic-theory.truth-table.v1"
        )
        assert ranking.PARTITIONS == ("CALIBRATION", "TEST", "HOLDOUT")
        assert ranking.DEFAULT_KS == (1, 3, 5)
        assert ranking.RELEVANCE_GRADE_MEANINGS == {
            "3": "direct_compatible",
            "2": "related_compatible",
            "1": "transpose_compatible",
            "0": "incompatible_known",
        }


class TestAq6RankingFixture:
    def test_fixture_exists_and_matches_generator(self) -> None:
        assert FIXTURE_PATH.is_file(), (
            "missing frozen fixture; run write_relevance_benchmark_fixture"
        )
        loaded = ranking.load_relevance_benchmark_fixture(FIXTURE_PATH)
        generated = ranking.build_relevance_benchmark_document()
        assert loaded["benchmark_id"] == ranking.BENCHMARK_ID
        assert loaded["domain"] == "aq6.ranking"
        assert loaded["support"]["queries_total"] == 5
        assert loaded["support"]["by_partition"] == {
            "CALIBRATION": 2,
            "TEST": 2,
            "HOLDOUT": 1,
        }
        assert FIXTURE_PATH.read_bytes() == ranking.relevance_benchmark_json_bytes(
            generated
        )

    def test_audit_passes(self) -> None:
        audit = ranking.audit_relevance_benchmark(
            ranking.load_relevance_benchmark_fixture(FIXTURE_PATH)
        )
        assert audit["status"] == "PASS"
        assert audit["findings"] == []
        assert audit["coverage"]["direct"] is True
        assert audit["coverage"]["related"] is True
        assert audit["coverage"]["transpose"] is True
        assert audit["coverage"]["incompatible"] is True
        assert audit["coverage"]["uncertain"] is True
        assert audit["coverage"]["bpm_known"] is True
        assert audit["coverage"]["bpm_missing"] is True


class TestAq6RankingTheorySeparation:
    def test_theory_fields_match_1015_classifier(self) -> None:
        doc = ranking.load_relevance_benchmark_fixture(FIXTURE_PATH)
        for query in doc["queries"]:
            ref_key = query["reference"]["key"]
            for cand in query["candidates"]:
                theory = classify_theory_pair(ref_key, cand["key"])
                assert cand["theory_relation"] == theory["relation"]
                assert cand["theory_compatibility"] == theory["compatibility"]
                # Ranking grade is a separate field; must not erase theory labels.
                assert "relevance_grade" in cand
                assert "ranking_eligible" in cand
                assert "theory_relation" in cand
                assert cand["theory_relation"] != cand.get("relevance_grade")

    def test_uncertain_evidence_is_ranking_ineligible(self) -> None:
        doc = ranking.load_relevance_benchmark_fixture(FIXTURE_PATH)
        ineligible = [
            c
            for q in doc["queries"]
            for c in q["candidates"]
            if not c["ranking_eligible"]
        ]
        assert len(ineligible) >= 1
        for cand in ineligible:
            assert cand["relevance_grade"] is None
            assert cand["theory_compatibility"] == "uncertain"

    def test_grades_align_to_theory_compatibility_classes(self) -> None:
        doc = ranking.load_relevance_benchmark_fixture(FIXTURE_PATH)
        for query in doc["queries"]:
            for cand in query["candidates"]:
                if not cand["ranking_eligible"]:
                    continue
                if cand["theory_relation"] == "direct":
                    assert cand["relevance_grade"] == 3
                elif cand["theory_relation"] == "related":
                    assert cand["relevance_grade"] == 2
                elif cand["theory_relation"] == "transpose":
                    assert cand["relevance_grade"] == 1
                elif cand["theory_compatibility"] == "incompatible":
                    assert cand["relevance_grade"] == 0


class TestAq6RankingPartitionsAndHygiene:
    def test_query_ids_unique_and_partitioned(self) -> None:
        doc = ranking.load_relevance_benchmark_fixture(FIXTURE_PATH)
        ids = [q["query_id"] for q in doc["queries"]]
        assert len(ids) == len(set(ids))
        partitions = {q["partition"] for q in doc["queries"]}
        assert partitions == {"CALIBRATION", "TEST", "HOLDOUT"}

    def test_no_private_paths(self) -> None:
        doc = ranking.load_relevance_benchmark_fixture(FIXTURE_PATH)
        for query in doc["queries"]:
            assert not ranking.is_private_absolute_path(query["reference"]["path"])
            assert query["reference"]["path"].startswith("synthetic/")
            for cand in query["candidates"]:
                assert not ranking.is_private_absolute_path(cand["path"])
                assert cand["path"].startswith("synthetic/")

    def test_bpm_evidence_explicit_when_missing(self) -> None:
        doc = ranking.load_relevance_benchmark_fixture(FIXTURE_PATH)
        missing_cases = [
            (q, c)
            for q in doc["queries"]
            for c in q["candidates"]
            if c["bpm_evidence"] != "known"
        ]
        assert missing_cases, "expected at least one missing-BPM case"
        for query, cand in missing_cases:
            assert cand["bpm_evidence"] in {
                "missing_reference",
                "missing_candidate",
                "missing_both",
            }
            # Missing BPM must not be silently treated as a certain tempo match.
            assert cand["bpm"] is None or query["reference"]["bpm"] is None


class TestAq6RankingMetrics:
    def test_precision_mrr_ndcg_and_fp_definitions(self) -> None:
        grades = {
            "a": 3,
            "b": 0,
            "c": 2,
            "d": 1,
        }
        ranked = ["b", "a", "c", "d"]
        assert ranking.precision_at_k(ranked, grades, 1) == 0.0
        assert ranking.precision_at_k(ranked, grades, 3) == pytest.approx(2 / 3)
        assert ranking.mrr_at_k(ranked, grades, 3) == pytest.approx(0.5)
        assert ranking.top_k_false_positive_rate(ranked, grades, 1) == 1.0
        assert ranking.top_k_false_positive_rate(ranked, grades, 3) == pytest.approx(
            1 / 3
        )
        ndcg = ranking.ndcg_at_k(["a", "c", "d", "b"], grades, 3)
        assert ndcg is not None
        assert ndcg == pytest.approx(1.0)

    def test_ideal_ranking_on_calibration_query(self) -> None:
        doc = ranking.load_relevance_benchmark_fixture(FIXTURE_PATH)
        query = next(
            q for q in doc["queries"] if q["query_id"] == "q_cal_cmaj_full_spectrum"
        )
        grades = ranking.grades_by_id(query)
        ideal = [
            cid
            for cid, _ in sorted(grades.items(), key=lambda kv: (-kv[1], kv[0]))
        ]
        metrics = ranking.score_ranking_for_query(query, ideal)
        assert metrics["precision_at_1"] == 1.0
        assert metrics["mrr_at_5"] == 1.0
        assert metrics["ndcg_at_5"] == pytest.approx(1.0)
        assert metrics["top_5_false_positive_rate"] < 1.0
        assert metrics["ineligible_count"] >= 1

    def test_hard_negative_first_is_false_positive(self) -> None:
        doc = ranking.load_relevance_benchmark_fixture(FIXTURE_PATH)
        query = next(
            q for q in doc["queries"] if q["query_id"] == "q_cal_cmaj_full_spectrum"
        )
        ranked = ["cal_incompatible_fsharpmaj", "cal_direct_cmaj"]
        metrics = ranking.score_ranking_for_query(query, ranked, ks=(1, 2))
        assert metrics["precision_at_1"] == 0.0
        assert metrics["top_1_false_positive_rate"] == 1.0
        assert metrics["mrr_at_2"] == pytest.approx(0.5)
