"""Frozen tests for AQ5 retrieval baseline harness (#1010).

TEST FREEZE: these assertions define the baseline measurement contract.
Fix the harness, not these expectations, when they turn red.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import aq5_relevance_benchmark as relevance
from src import aq5_retrieval_baseline as baseline
from src.embed import ClapEmbeddingBackend, EmbeddingBackendUnavailableError


REPO_ROOT = Path(__file__).resolve().parents[1]


def _clap_usable() -> bool:
    try:
        ClapEmbeddingBackend()
        return True
    except (EmbeddingBackendUnavailableError, Exception):
        return False


def test_baseline_identity_and_exit_tokens_are_frozen() -> None:
    assert baseline.DOCUMENT_TYPE == "sample-brain.aq5.retrieval-baseline.v1"
    assert baseline.SCHEMA_VERSION == "1.0.0"
    assert baseline.BENCHMARK_ID == relevance.BENCHMARK_ID
    assert baseline.EXIT_MEASURED == "AQ5_RETRIEVAL_BASELINE_MEASURED"
    assert baseline.EXIT_PARTIAL == "AQ5_RETRIEVAL_BASELINE_PARTIAL_HOLD"
    assert baseline.EXIT_INCOMPLETE == "AQ5_RETRIEVAL_BASELINE_INCOMPLETE"


def test_candidate_path_inventory_enumerates_reachable_and_hold_paths() -> None:
    inventory = baseline.candidate_path_inventory()
    by_id = {row["candidate_id"]: row for row in inventory}
    assert set(by_id) == {
        baseline.CANDIDATE_NUMPY_TIER_A,
        baseline.CANDIDATE_NUMPY_TIER_B_TEXT,
        baseline.CANDIDATE_NUMPY_TIER_B_AUDIO,
        baseline.CANDIDATE_SQLITE_VEC_ANN,
        baseline.CANDIDATE_HISTORICAL_VOCAL_SPIKE,
    }
    assert by_id[baseline.CANDIDATE_NUMPY_TIER_A]["plane"] == "aq5.retrieval"
    assert by_id[baseline.CANDIDATE_NUMPY_TIER_A]["product_reachable"] is True
    assert by_id[baseline.CANDIDATE_NUMPY_TIER_B_TEXT]["plane"] == "aq5.retrieval"
    assert by_id[baseline.CANDIDATE_NUMPY_TIER_B_AUDIO]["plane"] == "aq5.retrieval"
    assert by_id[baseline.CANDIDATE_SQLITE_VEC_ANN]["plane"] == "aq5.ranking"
    assert by_id[baseline.CANDIDATE_SQLITE_VEC_ANN]["default_promotion"] is False
    assert by_id[baseline.CANDIDATE_HISTORICAL_VOCAL_SPIKE]["product_reachable"] is False
    assert by_id[baseline.CANDIDATE_HISTORICAL_VOCAL_SPIKE]["status"] == "HOLD"


def test_retrieval_metric_helpers_match_kpi_contract() -> None:
    ranked = [10, 20, 30, 40, 50]
    relevant = {20, 99}
    negatives = {30, 88}
    metrics = baseline.score_retrieval_query(
        ranked_ids=ranked,
        relevant_ids=relevant,
        negative_ids=negatives,
    )
    assert metrics["precision_at_1"] == pytest.approx(0.0)
    assert metrics["precision_at_5"] == pytest.approx(0.2)
    assert metrics["recall_at_1"] == pytest.approx(0.0)
    assert metrics["recall_at_5"] == pytest.approx(0.5)
    assert metrics["recall_at_10"] == pytest.approx(0.5)
    assert metrics["mrr"] == pytest.approx(0.5)
    assert metrics["hit_rate_at_1"] == pytest.approx(0.0)
    assert metrics["hit_rate_at_5"] == pytest.approx(1.0)
    assert metrics["hit_rate_at_10"] == pytest.approx(1.0)
    assert metrics["hard_negative_fp_at_5"] == pytest.approx(1.0)
    assert metrics["ndcg_at_10"] is None  # graded HOLD


def test_planes_never_opaque_combine_relevance_and_latency() -> None:
    # Contract: aggregate helper keeps plane keys disjoint.
    payload = baseline.separate_reporting_planes(
        retrieval={"mean_precision_at_5": 0.5},
        ranking={"determinism_equal": True},
        operational={"p50_ms": 12.0},
    )
    assert set(payload) == {"aq5.retrieval", "aq5.ranking", "operational"}
    assert "p50_ms" not in payload["aq5.retrieval"]
    assert "mean_precision_at_5" not in payload["operational"]
    assert "quality_latency" not in payload
    assert "combined_score" not in payload


def test_run_rejects_output_inside_repo(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    inside = REPO_ROOT / ".pytest_aq5_retrieval_baseline_should_not_exist.json"
    with pytest.raises(ValueError, match="outside"):
        baseline.run_aq5_retrieval_baseline(
            work_dir=work,
            output_path=inside,
            repo_root=REPO_ROOT,
            include_tier_b=False,
            include_runtime=False,
            include_sqlite_vec=False,
        )


def test_run_tier_a_writes_external_json_with_separate_planes(tmp_path: Path) -> None:
    work = tmp_path / "work"
    out = tmp_path / "aq5-retrieval-baseline.json"
    result = baseline.run_aq5_retrieval_baseline(
        work_dir=work,
        output_path=out,
        repo_root=REPO_ROOT,
        include_tier_b=False,
        include_runtime=True,
        include_sqlite_vec=True,
        runtime_repetitions=5,
    )

    assert out.is_file()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded == result
    assert result["document_type"] == baseline.DOCUMENT_TYPE
    assert result["schema_version"] == baseline.SCHEMA_VERSION
    assert result["benchmark_id"] == relevance.BENCHMARK_ID
    assert result["exit_status"] in {
        baseline.EXIT_MEASURED,
        baseline.EXIT_PARTIAL,
        baseline.EXIT_INCOMPLETE,
    }
    # Without Tier-B, exit must not claim full measured.
    assert result["exit_status"] != baseline.EXIT_MEASURED

    assert "aq5.retrieval" in result
    assert "aq5.ranking" in result
    assert "operational" in result
    assert "quality_latency" not in result
    assert "combined_score" not in result

    retrieval = result["aq5.retrieval"]
    assert retrieval["ndcg_eligibility"] == "HOLD"
    assert set(retrieval["splits"]) == {"CALIBRATION", "TEST"}
    for split_name in ("CALIBRATION", "TEST"):
        split = retrieval["splits"][split_name]
        assert "by_query_family" in split
        assert "by_mode" in split
        assert "aggregate" in split
        assert split["aggregate"]["query_count"] >= 1
        assert "mean_precision_at_1" in split["aggregate"]
        assert "mean_precision_at_5" in split["aggregate"]
        assert "mean_precision_at_10" in split["aggregate"]
        assert "mean_recall_at_10" in split["aggregate"]
        assert "mean_mrr" in split["aggregate"]
        assert "mean_hit_rate_at_5" in split["aggregate"]
        assert "mean_hard_negative_fp_at_5" in split["aggregate"]
        assert "failure_buckets" in split
        assert "ndcg_at_10" not in split["aggregate"] or split["aggregate"][
            "ndcg_at_10"
        ] is None

    ranking = result["aq5.ranking"]
    assert ranking["determinism"]["status"] in {"measured", "HOLD"}
    assert "tie_order_checked" in ranking["determinism"]
    ann = ranking["ann_vs_reference"]
    assert ann["candidate_id"] == baseline.CANDIDATE_SQLITE_VEC_ANN
    assert ann["status"] in {"measured", "HOLD"}
    assert ann.get("default_promotion") is False

    operational = result["operational"]
    assert operational["methodology_id"] == baseline.RUNTIME_METHODOLOGY_ID
    assert "relevance_score" not in operational

    paths = {row["candidate_id"]: row for row in result["candidate_paths"]}
    assert paths[baseline.CANDIDATE_NUMPY_TIER_A]["status"] == "measured"
    assert paths[baseline.CANDIDATE_HISTORICAL_VOCAL_SPIKE]["status"] == "HOLD"
    assert paths[baseline.CANDIDATE_NUMPY_TIER_B_TEXT]["status"] == "HOLD"
    assert paths[baseline.CANDIDATE_NUMPY_TIER_B_AUDIO]["status"] == "HOLD"

    holds = {item["item"]: item["status"] for item in result["hold_stubs"]}
    assert holds["graded_relevance_ndcg"] == "HOLD"
    assert holds["vocal_no_vocal_production_claim"] == "HOLD"
    assert holds["genre_mood_production_claim"] == "HOLD"
    assert holds["vocal_proxy_spike_suite"] == "HOLD"

    dumped = json.dumps(result)
    assert "D:/" not in dumped
    assert "D:\\" not in dumped
    assert "/Users/" not in dumped
    assert "/home/" not in dumped
    for key in ("work_dir", "db_path", "audio_path", "file_path", "source_path"):
        assert key not in result

    assert result["partition_policy"]["CALIBRATION"] == "DEVELOPMENT/CALIBRATION"
    assert result["partition_policy"]["TEST"] == "TEST/HOLDOUT"
    assert result["no_tuning_on_test"] is True
    assert result["query_set_fingerprint"]
    assert result["partition_fingerprint"]


@pytest.mark.clap
def test_run_with_tier_b_clap_measures_text_and_audio_paths(tmp_path: Path) -> None:
    if not _clap_usable():
        pytest.skip("CLAP backend not available")

    work = tmp_path / "work-clap"
    out = tmp_path / "aq5-retrieval-baseline-clap.json"
    result = baseline.run_aq5_retrieval_baseline(
        work_dir=work,
        output_path=out,
        repo_root=REPO_ROOT,
        include_tier_b=True,
        include_runtime=True,
        include_sqlite_vec=True,
        runtime_repetitions=5,
    )

    assert result["exit_status"] in {
        baseline.EXIT_MEASURED,
        baseline.EXIT_PARTIAL,
    }
    paths = {row["candidate_id"]: row for row in result["candidate_paths"]}
    assert paths[baseline.CANDIDATE_NUMPY_TIER_A]["status"] == "measured"
    assert paths[baseline.CANDIDATE_NUMPY_TIER_B_TEXT]["status"] == "measured"
    assert paths[baseline.CANDIDATE_NUMPY_TIER_B_AUDIO]["status"] == "measured"

    retrieval = result["aq5.retrieval"]
    support = retrieval["support_counts"]["query_family"]
    for family in relevance.TIER_B_QUERY_FAMILIES:
        assert support.get(family, 0) >= 1

    # Per-family slice must exist for measured Tier-B families.
    families_seen: set[str] = set()
    for split in retrieval["splits"].values():
        families_seen.update(split["by_query_family"].keys())
    for family in relevance.TIER_B_QUERY_FAMILIES:
        assert family in families_seen

    # Planes stay separate after full run.
    assert "p50_ms" not in json.dumps(retrieval)
    assert "mean_precision_at_5" not in json.dumps(result["operational"])
