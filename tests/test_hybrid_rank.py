from __future__ import annotations

import pytest

from src.hybrid_rank import (
    HybridMetadata,
    HybridQuery,
    combine_hybrid_score,
    rerank_hits,
    score_bpm_match,
    score_key_match,
    score_type_match,
)
from src.index import SearchHit


class TestScoreBpmMatch:
    def test_exact_match_returns_one(self):
        assert score_bpm_match(128.0, 128.0, 8.0) == 1.0

    def test_outside_tolerance_returns_zero(self):
        assert score_bpm_match(120.0, 128.0, 8.0) == 0.0

    def test_halfway_inside_tolerance_returns_expected_decay(self):
        assert score_bpm_match(124.0, 128.0, 8.0) == pytest.approx(0.5)

    def test_missing_bpm_returns_zero(self):
        assert score_bpm_match(None, 128.0, 8.0) == 0.0
        assert score_bpm_match(128.0, None, 8.0) == 0.0


class TestScoreKeyMatch:
    def test_exact_match_is_case_insensitive_and_whitespace_normalized(self):
        assert score_key_match("  C Minor ", "c minor") == 1.0

    def test_missing_key_returns_zero(self):
        assert score_key_match(None, "c minor") == 0.0
        assert score_key_match("c minor", None) == 0.0


class TestScoreTypeMatch:
    def test_exact_match_is_case_insensitive_and_whitespace_normalized(self):
        assert score_type_match(" Kick ", "kick") == 1.0

    def test_missing_type_returns_zero(self):
        assert score_type_match(None, "kick") == 0.0
        assert score_type_match("kick", None) == 0.0


class TestCombineHybridScore:
    def test_default_query_preserves_semantic_score(self):
        metadata = HybridMetadata(sample_id=1, bpm=120.0, key="Am", pred_type="kick")
        query = HybridQuery()
        assert combine_hybrid_score(0.87, metadata, query) == pytest.approx(0.87)


class TestRerankHits:
    def test_default_query_preserves_semantic_order_and_scores(self):
        hits = [
            SearchHit(sample_id=10, path="/a.wav", score=0.9),
            SearchHit(sample_id=20, path="/b.wav", score=0.7),
            SearchHit(sample_id=30, path="/c.wav", score=0.5),
        ]
        metadata = {
            10: HybridMetadata(sample_id=10, bpm=120.0),
            20: HybridMetadata(sample_id=20, bpm=140.0),
            30: HybridMetadata(sample_id=30, bpm=128.0),
        }

        reranked = rerank_hits(hits, metadata, HybridQuery())

        assert [hit.sample_id for hit in reranked] == [10, 20, 30]
        assert [hit.score for hit in reranked] == pytest.approx([0.9, 0.7, 0.5])
        assert [hit.path for hit in reranked] == ["/a.wav", "/b.wav", "/c.wav"]

    def test_bpm_weighting_can_promote_lower_semantic_hit(self):
        hits = [
            SearchHit(sample_id=1, path="/far.wav", score=0.9),
            SearchHit(sample_id=2, path="/close.wav", score=0.7),
        ]
        metadata = {
            1: HybridMetadata(sample_id=1, bpm=100.0),
            2: HybridMetadata(sample_id=2, bpm=128.0),
        }
        query = HybridQuery(target_bpm=128.0, bpm_weight=0.5)

        reranked = rerank_hits(hits, metadata, query)

        assert reranked[0].sample_id == 2
        assert reranked[0].score == pytest.approx(1.2)
        assert reranked[1].sample_id == 1
        assert reranked[1].score == pytest.approx(0.9)

    def test_missing_metadata_does_not_crash_or_add_bonus(self):
        hits = [SearchHit(sample_id=5, path="/unknown.wav", score=0.6)]
        query = HybridQuery(target_bpm=128.0, target_key="Am", target_type="kick", bpm_weight=0.4)

        reranked = rerank_hits(hits, {}, query)

        assert len(reranked) == 1
        assert reranked[0].sample_id == 5
        assert reranked[0].score == pytest.approx(0.6)

    def test_tie_handling_is_deterministic(self):
        hits = [
            SearchHit(sample_id=30, path="/c.wav", score=0.8),
            SearchHit(sample_id=10, path="/a.wav", score=0.8),
        ]
        metadata = {
            10: HybridMetadata(sample_id=10, bpm=128.0),
            30: HybridMetadata(sample_id=30, bpm=128.0),
        }
        query = HybridQuery(target_bpm=128.0, bpm_weight=0.0)

        first = rerank_hits(hits, metadata, query)
        second = rerank_hits(hits, metadata, query)

        assert [hit.sample_id for hit in first] == [30, 10]
        assert [hit.sample_id for hit in second] == [30, 10]
