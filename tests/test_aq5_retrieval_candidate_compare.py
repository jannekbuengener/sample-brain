"""Frozen tests for AQ5 retrieval/ranking candidate comparison (#1012).

TEST FREEZE: these assertions define the compare contract. Fix the harness,
not these expectations, when they turn red. Do not promote backends, invent
graded NDCG labels, or tune on TEST/HOLDOUT.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import aq5_relevance_benchmark as relevance
from src import aq5_retrieval_baseline as baseline
from src import aq5_retrieval_candidate_compare as compare
from src.embed import ClapEmbeddingBackend
from src.hybrid_rank import HybridQuery


REPO_ROOT = Path(__file__).resolve().parents[1]


def _clap_usable() -> bool:
    try:
        backend = ClapEmbeddingBackend()
        vector = backend.embed_text("kick")
        return getattr(vector, "size", 0) > 0 or len(vector) > 0
    except Exception:
        return False


def test_compare_identity_constants_are_frozen() -> None:
    assert compare.DOCUMENT_TYPE == (
        "sample-brain.aq5.retrieval-candidate-compare.v1"
    )
    assert compare.SCHEMA_VERSION == "1.0.0"
    assert compare.BENCHMARK_ID == relevance.BENCHMARK_ID
    assert compare.BASELINE_DOCUMENT_TYPE == baseline.DOCUMENT_TYPE
    assert compare.EXIT_REPRODUCIBLE == (
        "AQ5_RETRIEVAL_CANDIDATE_COMPARE_REPRODUCIBLE"
    )
    assert compare.EXIT_NO_JUSTIFIED == "AQ5_RETRIEVAL_NO_JUSTIFIED_CANDIDATE"
    assert compare.EXIT_INCOMPLETE == (
        "AQ5_RETRIEVAL_CANDIDATE_COMPARE_INCOMPLETE"
    )
    assert compare.PARTITION_POLICY["CALIBRATION"] == "DEVELOPMENT/CALIBRATION"
    assert compare.PARTITION_POLICY["TEST"] == "TEST/HOLDOUT"


def test_frozen_candidate_registry_has_at_most_four_justified_adapters() -> None:
    candidates = compare.list_retrieval_candidates()
    assert 3 <= len(candidates) <= 4
    ids = [c.candidate_id for c in candidates]
    assert len(ids) == len(set(ids))
    assert ids[0] == "retrieval.baseline.v1"
    assert ids == [
        "retrieval.baseline.v1",
        "hybrid.semantic_weight.0.8",
        "classical.type_rerank.text_hint.0.5",
        "classical.type_rerank.text_hint.1.0",
    ]
    for candidate in candidates:
        assert candidate.description.strip()
        assert candidate.derived_from.strip()
        public = compare.candidate_public(candidate)
        assert public["candidate_id"] == candidate.candidate_id
        assert "adapter_kind" in public
        assert "derived_from" in public


def test_candidate_by_id_rejects_unknown() -> None:
    with pytest.raises(compare.Aq5RetrievalCandidateCompareError, match="unknown"):
        compare.candidate_by_id("retrieval.not.a.real.candidate")


def test_type_hint_from_text_is_deterministic() -> None:
    assert compare.type_hint_from_text("kick drum") == "kick"
    assert compare.type_hint_from_text("snare drum") == "snare"
    assert compare.type_hint_from_text("warm pad synth") == "pad"
    assert compare.type_hint_from_text("cinematic impact hit") == "impact"
    assert compare.type_hint_from_text("singing voice") == "vocal"
    assert compare.type_hint_from_text("dark driving electronic loop") is None


def test_adapt_hybrid_query_baseline_preserves_suite_hybrid() -> None:
    candidate = compare.candidate_by_id("retrieval.baseline.v1")
    suite = HybridQuery(
        target_bpm=130.0,
        bpm_weight=1.0,
        semantic_weight=0.2,
    )
    adapted = compare.adapt_hybrid_query(
        suite_hybrid=suite,
        mode="vector",
        query_text=None,
        candidate=candidate,
    )
    assert adapted == suite


def test_adapt_hybrid_query_semantic_weight_override() -> None:
    candidate = compare.candidate_by_id("hybrid.semantic_weight.0.8")
    suite = HybridQuery(
        target_bpm=130.0,
        bpm_weight=1.0,
        semantic_weight=0.2,
    )
    adapted = compare.adapt_hybrid_query(
        suite_hybrid=suite,
        mode="vector",
        query_text=None,
        candidate=candidate,
    )
    assert adapted is not None
    assert adapted.semantic_weight == pytest.approx(0.8)
    assert adapted.bpm_weight == pytest.approx(1.0)
    assert adapted.target_bpm == pytest.approx(130.0)
    # No suite hybrid → no-op
    assert (
        compare.adapt_hybrid_query(
            suite_hybrid=None,
            mode="vector",
            query_text=None,
            candidate=candidate,
        )
        is None
    )


def test_adapt_hybrid_query_classical_type_rerank_on_text() -> None:
    candidate = compare.candidate_by_id("classical.type_rerank.text_hint.0.5")
    adapted = compare.adapt_hybrid_query(
        suite_hybrid=None,
        mode="text",
        query_text="kick drum",
        candidate=candidate,
    )
    assert adapted is not None
    assert adapted.target_type == "kick"
    assert adapted.type_weight == pytest.approx(0.5)
    assert adapted.semantic_weight == pytest.approx(1.0)
    # Suite hybrid wins — do not replace Tier-A hybrid with type hint.
    suite = HybridQuery(target_key="Dm", key_weight=1.0, semantic_weight=0.2)
    assert (
        compare.adapt_hybrid_query(
            suite_hybrid=suite,
            mode="text",
            query_text="kick drum",
            candidate=candidate,
        )
        == suite
    )


def test_run_rejects_output_inside_repo(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    inside = REPO_ROOT / ".pytest_aq5_retrieval_compare_should_not_exist.json"
    with pytest.raises(ValueError, match="outside"):
        compare.run_aq5_retrieval_candidate_compare(
            work_dir=work,
            output_path=inside,
            repo_root=REPO_ROOT,
            include_tier_b=False,
            include_runtime=False,
            include_ann=False,
        )


def test_run_tier_a_writes_external_json_with_separate_planes(tmp_path: Path) -> None:
    work = tmp_path / "work"
    out = tmp_path / "aq5-retrieval-candidate-compare.json"
    result = compare.run_aq5_retrieval_candidate_compare(
        work_dir=work,
        output_path=out,
        repo_root=REPO_ROOT,
        include_tier_b=False,
        include_runtime=True,
        include_ann=False,
        runtime_repetitions=2,
    )

    assert out.is_file()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded == result
    assert result["document_type"] == compare.DOCUMENT_TYPE
    assert result["schema_version"] == compare.SCHEMA_VERSION
    assert result["benchmark_id"] == relevance.BENCHMARK_ID
    assert result["baseline_document_type"] == baseline.DOCUMENT_TYPE
    assert result["exit_status"] in {
        compare.EXIT_REPRODUCIBLE,
        compare.EXIT_NO_JUSTIFIED,
        compare.EXIT_INCOMPLETE,
    }
    # Without Tier-B, must not claim full reproducible measured compare.
    assert result["exit_status"] != compare.EXIT_REPRODUCIBLE
    assert result["no_tuning_on_test"] is True
    assert result["production_switch"] is False
    assert result["partition_policy"]["CALIBRATION"] == "DEVELOPMENT/CALIBRATION"
    assert result["partition_policy"]["TEST"] == "TEST/HOLDOUT"

    assert "aq5.retrieval" in result
    assert "aq5.ranking" in result
    assert "operational" in result
    assert "quality_latency" not in result
    assert "combined_score" not in result

    candidate_ids = {c["candidate_id"] for c in result["candidates"]}
    expected_ids = {c.candidate_id for c in compare.list_retrieval_candidates()}
    assert candidate_ids == expected_ids

    for entry in result["candidates"]:
        assert "description" in entry
        assert "derived_from" in entry
        assert set(entry["splits"]) == {"CALIBRATION", "TEST"}
        for split_name in ("CALIBRATION", "TEST"):
            split = entry["splits"][split_name]
            assert "aggregate" in split
            assert "by_query_family" in split
            assert "by_mode" in split
            agg = split["aggregate"]
            assert "mean_precision_at_5" in agg
            assert "mean_mrr" in agg
            assert "mean_hard_negative_fp_at_5" in agg
            assert agg.get("ndcg_at_10") is None

    retrieval = result["aq5.retrieval"]
    assert retrieval["ndcg_eligibility"] == "HOLD"
    assert retrieval["identical_query_relevance_records"] is True

    ranking = result["aq5.ranking"]
    assert "determinism" in ranking
    assert "ann_approximation" in ranking
    assert ranking["ann_approximation"]["plane"] == "aq5.ranking"
    assert ranking["ann_approximation"].get("default_promotion") is False
    assert "relevance_score" not in ranking

    operational = result["operational"]
    assert "relevance_score" not in operational

    seam = result["automation_seam"]
    assert seam["headless_invocation"] is True
    assert "exit_status" in seam
    assert seam["test_holdout_locked"] is True
    assert seam["production_promotion_unguarded"] is False

    holds = {item["item"]: item["status"] for item in result["hold_stubs"]}
    assert holds["graded_relevance_ndcg"] == "HOLD"
    assert holds["sqlite_vec_production_promotion"] == "HOLD"

    dumped = json.dumps(result)
    assert "D:/" not in dumped
    assert "D:\\" not in dumped
    assert "/Users/" not in dumped
    assert "/home/" not in dumped
    for key in ("work_dir", "db_path", "audio_path", "file_path", "source_path"):
        assert key not in result


@pytest.mark.skipif(not _clap_usable(), reason="CLAP backend unavailable")
def test_run_with_tier_b_can_exit_reproducible(tmp_path: Path) -> None:
    work = tmp_path / "work"
    out = tmp_path / "aq5-retrieval-candidate-compare-full.json"
    result = compare.run_aq5_retrieval_candidate_compare(
        work_dir=work,
        output_path=out,
        repo_root=REPO_ROOT,
        include_tier_b=True,
        include_runtime=False,
        include_ann=False,
    )
    assert result["exit_status"] == compare.EXIT_REPRODUCIBLE
    baseline_entry = next(
        c for c in result["candidates"] if c["candidate_id"] == "retrieval.baseline.v1"
    )
    assert baseline_entry["splits"]["CALIBRATION"]["aggregate"]["query_count"] >= 1
    assert baseline_entry["splits"]["TEST"]["aggregate"]["query_count"] >= 1
    assert baseline_entry.get("baseline_anchor_ok") is True
