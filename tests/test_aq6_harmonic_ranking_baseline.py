"""Frozen tests for AQ6 Harmonic Match ranking + upstream-delta baseline (#1018).

TEST FREEZE: these assertions define the measurement harness contract. Fix the
baseline runner — not these expectations — when they turn red. Do not retune
0.75/0.25 weights or rewrite #1016 labels to become green. Theory (#1017)
stays on a separate plane.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import aq6_harmonic_ranking_baseline as baseline
from src import aq6_harmonic_ranking_relevance as ranking


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = REPO_ROOT / ranking.FIXTURE_RELPATH


def test_baseline_identity_constants_are_frozen() -> None:
    assert baseline.DOCUMENT_TYPE == "sample-brain.aq6.harmonic-ranking-baseline.v1"
    assert baseline.SCHEMA_VERSION == "1.0.0"
    assert baseline.DOMAIN_TOKEN == "aq6.ranking"
    assert baseline.EXIT_MEASURED == (
        "AQ6_RANKING_BASELINE_AND_UPSTREAM_DELTA_MEASURED"
    )
    assert baseline.EXIT_PARTIAL == "AQ6_RANKING_BASELINE_PARTIAL_HOLD"
    assert baseline.EXIT_INCOMPLETE == "AQ6_RANKING_BASELINE_INCOMPLETE"
    assert baseline.SURFACE == (
        "src.workbench_harmony.find_harmony_matches"
    )
    assert baseline.BENCHMARK_ID == ranking.BENCHMARK_ID
    assert baseline.WEIGHTS == {"harmony": 0.75, "bpm": 0.25}
    assert baseline.THEORY_PLANE_NOTE.startswith("separate")
    assert set(baseline.UPSTREAM_STATES) == {
        "as_labeled",
        "missing_candidate_key",
        "wrong_candidate_key",
    }


def test_row_from_fixture_preserves_synthetic_id_as_rank_key() -> None:
    item = {
        "synthetic_id": "cal_direct_cmaj",
        "key": "Cmaj",
        "bpm": 128.0,
        "path": "synthetic/aq6_ranking/cal_direct_cmaj.wav",
    }
    row = baseline.row_from_fixture_item(item)
    assert row.display_name == "cal_direct_cmaj"
    assert row.key == "Cmaj"
    assert row.bpm == 128.0
    assert row.path.endswith("cal_direct_cmaj.wav")


def test_rank_query_as_labeled_returns_deterministic_order() -> None:
    doc = ranking.load_relevance_benchmark_fixture(FIXTURE_PATH)
    query = next(q for q in doc["queries"] if q["query_id"] == "q_test_dmin_spectrum")
    first = baseline.rank_query(query, upstream_state="as_labeled")
    second = baseline.rank_query(query, upstream_state="as_labeled")
    assert first["error"] is None
    assert first["ranked_ids"] == second["ranked_ids"]
    assert first["ranked_ids"][0] == "test_direct_dmin"
    assert "test_related_fmaj" in first["ranked_ids"][:3]


def test_missing_reference_bpm_abstains_without_forced_matches() -> None:
    doc = ranking.load_relevance_benchmark_fixture(FIXTURE_PATH)
    query = next(
        q
        for q in doc["queries"]
        if q["query_id"] == "q_test_amaj_bpm_missing_reference"
    )
    result = baseline.rank_query(query, upstream_state="as_labeled")
    assert result["ranked_ids"] == []
    assert result["empty_result"] is True
    assert result["error"] is not None
    assert result["abstention_reason"] == "missing_reference_bpm"


def test_missing_candidate_key_collapses_harmony_to_uncertain() -> None:
    doc = ranking.load_relevance_benchmark_fixture(FIXTURE_PATH)
    query = next(
        q for q in doc["queries"] if q["query_id"] == "q_cal_cmaj_full_spectrum"
    )
    result = baseline.rank_query(query, upstream_state="missing_candidate_key")
    assert result["error"] is None
    assert result["ranked_ids"]
    for detail in result["rank_details"]:
        assert detail["relation"] == "uncertain"
        assert detail["harmony_score"] == 0.0


def test_wrong_candidate_key_degrades_precision_vs_as_labeled() -> None:
    doc = ranking.load_relevance_benchmark_fixture(FIXTURE_PATH)
    query = next(
        q for q in doc["queries"] if q["query_id"] == "q_cal_cmaj_full_spectrum"
    )
    labeled = baseline.score_ranked_query(
        query, baseline.rank_query(query, upstream_state="as_labeled")
    )
    wrong = baseline.score_ranked_query(
        query, baseline.rank_query(query, upstream_state="wrong_candidate_key")
    )
    assert labeled["precision_at_1"] == 1.0
    assert wrong["precision_at_1"] < labeled["precision_at_1"]


def test_ineligible_evidence_never_forced_compatible() -> None:
    doc = ranking.load_relevance_benchmark_fixture(FIXTURE_PATH)
    report = baseline.prove_missing_evidence_not_forced_certainty(doc)
    assert report["ineligible_candidates_checked"] >= 1
    assert report["forced_compatible_count"] == 0
    assert report["pass"] is True


def test_aggregate_metrics_macro_averages_and_coverage() -> None:
    doc = ranking.load_relevance_benchmark_fixture(FIXTURE_PATH)
    scored = []
    for query in doc["queries"]:
        ranked = baseline.rank_query(query, upstream_state="as_labeled")
        scored.append(baseline.score_ranked_query(query, ranked))
    agg = baseline.aggregate_query_metrics(scored)
    assert agg["queries_total"] == 5
    assert agg["queries_scored"] == 4  # one abstains on missing ref BPM
    assert agg["queries_empty"] == 1
    assert "precision_at_1" in agg["macro"]
    assert "mrr_at_5" in agg["macro"]
    assert "ndcg_at_5" in agg["macro"]
    assert "top_5_false_positive_rate" in agg["macro"]
    assert agg["coverage"]["queries_with_eligible_relevant"] >= 1
    assert agg["coverage"]["ineligible_candidate_fraction"] > 0.0


def test_upstream_delta_attributes_quality_loss() -> None:
    doc = ranking.load_relevance_benchmark_fixture(FIXTURE_PATH)
    by_state = baseline.measure_upstream_states(doc)
    deltas = baseline.compute_upstream_deltas(by_state)
    assert set(by_state) == set(baseline.UPSTREAM_STATES)
    assert "as_labeled_to_missing_candidate_key" in deltas
    assert "as_labeled_to_wrong_candidate_key" in deltas
    # Wrong upstream keys must not improve P@1 over correct labeled evidence.
    assert (
        deltas["as_labeled_to_wrong_candidate_key"]["precision_at_1"]["delta"] <= 0.0
    )
    assert deltas["as_labeled_to_wrong_candidate_key"]["attribution"] == (
        "upstream_evidence"
    )


def test_determinism_two_full_passes_match() -> None:
    doc = ranking.load_relevance_benchmark_fixture(FIXTURE_PATH)
    repeat = baseline.measure_repeatability(doc)
    assert repeat["passes"] == 2
    assert repeat["ranked_lists_identical"] is True
    assert repeat["metrics_identical"] is True
    assert repeat["deterministic"] is True


def test_theory_plane_remains_separate() -> None:
    doc = ranking.load_relevance_benchmark_fixture(FIXTURE_PATH)
    plane = baseline.theory_plane_visibility(doc)
    assert plane["token"] == "aq6.theory"
    assert plane["mixed_into_ranking_metrics"] is False
    assert plane["issue_ref"] == "#1017"
    assert plane["incompatible_in_top_k_reported_separately"] is True


def test_run_rejects_output_inside_repo() -> None:
    inside = REPO_ROOT / ".pytest_aq6_ranking_baseline_should_not_exist.json"
    with pytest.raises(ValueError, match="outside"):
        baseline.run_aq6_ranking_baseline(
            output_path=inside,
            repo_root=REPO_ROOT,
        )


def test_run_writes_external_json_measured(tmp_path: Path) -> None:
    out = tmp_path / "aq6-ranking-baseline.json"
    result = baseline.run_aq6_ranking_baseline(
        output_path=out,
        repo_root=REPO_ROOT,
    )

    assert out.is_file()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["exit_status"] == baseline.EXIT_MEASURED
    assert loaded["document_type"] == baseline.DOCUMENT_TYPE
    assert loaded["domain"] == "aq6.ranking"
    assert loaded["benchmark_id"] == ranking.BENCHMARK_ID
    assert loaded["weights"] == {"harmony": 0.75, "bpm": 0.25}
    assert "as_labeled" in loaded["upstream_states"]
    assert "missing_candidate_key" in loaded["upstream_states"]
    assert "wrong_candidate_key" in loaded["upstream_states"]
    assert "upstream_deltas" in loaded
    assert loaded["determinism"]["deterministic"] is True
    assert loaded["missing_evidence_guard"]["pass"] is True
    assert loaded["theory_plane"]["mixed_into_ranking_metrics"] is False
    assert loaded["as_labeled"]["macro"]["precision_at_1"] == 1.0
    assert loaded["as_labeled"]["queries_empty"] == 1
    assert result["exit_status"] == baseline.EXIT_MEASURED
    # Exact floats may live only in external JSON; no absolute host paths.
    blob = out.read_text(encoding="utf-8")
    assert "D:/" not in blob
    assert "C:/" not in blob


def test_is_measured_requires_full_support() -> None:
    incomplete = {
        "as_labeled": {"queries_scored": 0, "queries_total": 5},
        "upstream_states": {},
        "upstream_deltas": {},
        "determinism": {"deterministic": False},
        "missing_evidence_guard": {"pass": False},
        "theory_plane": {"mixed_into_ranking_metrics": True},
        "bpm_cohorts": {},
        "coverage": {"complete": False},
    }
    assert baseline.is_measured(incomplete) is False
