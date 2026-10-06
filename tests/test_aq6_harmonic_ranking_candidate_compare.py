"""Frozen tests for AQ6 Harmonic Match ranking candidate compare (#1019).

TEST FREEZE: these assertions define the compare harness contract. Fix the
compare runner — not these expectations — when they turn red. Do not retune
production 0.75/0.25 weights, rewrite #1016 labels, or claim theory fixes from
ranking metrics. CALIBRATION may narrate; TEST/HOLDOUT stay frozen evidence.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import aq6_harmonic_ranking_baseline as baseline
from src import aq6_harmonic_ranking_candidate_compare as compare
from src import aq6_harmonic_ranking_relevance as ranking
from src import aq6_harmonic_theory_truth_table as theory


REPO_ROOT = Path(__file__).resolve().parents[1]
RANKING_FIXTURE = REPO_ROOT / ranking.FIXTURE_RELPATH
THEORY_FIXTURE = REPO_ROOT / theory.FIXTURE_RELPATH


def test_compare_identity_constants_are_frozen() -> None:
    assert compare.DOCUMENT_TYPE == (
        "sample-brain.aq6.harmonic-ranking-candidate-compare.v1"
    )
    assert compare.SCHEMA_VERSION == "1.0.0"
    assert compare.DOMAIN_TOKEN == "aq6.ranking"
    assert compare.EXIT_REPRODUCIBLE == (
        "AQ6_HARMONIC_CANDIDATE_COMPARE_REPRODUCIBLE"
    )
    assert compare.EXIT_NO_JUSTIFIED == "AQ6_HARMONIC_NO_JUSTIFIED_CANDIDATE"
    assert compare.EXIT_INCOMPLETE == (
        "AQ6_HARMONIC_CANDIDATE_COMPARE_INCOMPLETE"
    )
    assert compare.BASELINE_DOCUMENT_TYPE == baseline.DOCUMENT_TYPE
    assert compare.BENCHMARK_ID == ranking.BENCHMARK_ID
    assert len(compare.HARMONIC_RANKING_CANDIDATES) == 4
    assert compare.PARTITION_POLICY["CALIBRATION"]["allowed_use"] == (
        "exploration_narrative_only"
    )
    assert compare.PARTITION_POLICY["TEST"]["allowed_use"].startswith(
        "frozen_evidence"
    )
    assert compare.PARTITION_POLICY["HOLDOUT"]["allowed_use"].startswith(
        "frozen_evidence"
    )


def test_candidate_registry_ids_are_frozen() -> None:
    ids = [c.candidate_id for c in compare.list_harmonic_ranking_candidates()]
    assert ids == [
        "harmonic.baseline.v1",
        "harmonic.weights.harmony_0.90_bpm_0.10",
        "harmonic.weights.harmony_1.00_bpm_0.00",
        "harmonic.rank_filter.drop_uncertain",
    ]
    baseline_cand = compare.candidate_by_id("harmonic.baseline.v1")
    assert baseline_cand.harmony_weight == 0.75
    assert baseline_cand.bpm_weight == 0.25
    assert baseline_cand.drop_uncertain is False
    assert baseline_cand.relation_scores == compare.BASELINE_RELATION_SCORES


def test_unknown_candidate_id_fails_closed() -> None:
    with pytest.raises(compare.Aq6HarmonicCandidateCompareError, match="unknown"):
        compare.candidate_by_id("harmonic.not.a.real.candidate")


def test_baseline_candidate_matches_product_rank_order() -> None:
    doc = ranking.load_relevance_benchmark_fixture(RANKING_FIXTURE)
    query = next(q for q in doc["queries"] if q["query_id"] == "q_test_dmin_spectrum")
    product = baseline.rank_query(query, upstream_state="as_labeled")
    candidate = compare.candidate_by_id("harmonic.baseline.v1")
    adapted = compare.rank_query_for_candidate(
        query, candidate, upstream_state="as_labeled"
    )
    assert adapted["ranked_ids"] == product["ranked_ids"]
    assert adapted["error"] is None


def test_drop_uncertain_removes_uncertain_without_changing_theory_relation() -> None:
    doc = ranking.load_relevance_benchmark_fixture(RANKING_FIXTURE)
    query = next(
        q for q in doc["queries"] if q["query_id"] == "q_cal_cmaj_full_spectrum"
    )
    baseline_cand = compare.candidate_by_id("harmonic.baseline.v1")
    filtered = compare.candidate_by_id("harmonic.rank_filter.drop_uncertain")
    base_rank = compare.rank_query_for_candidate(
        query, baseline_cand, upstream_state="as_labeled"
    )
    filt_rank = compare.rank_query_for_candidate(
        query, filtered, upstream_state="as_labeled"
    )
    assert any(d["relation"] == "uncertain" for d in base_rank["rank_details"])
    assert all(d["relation"] != "uncertain" for d in filt_rank["rank_details"])
    assert len(filt_rank["ranked_ids"]) < len(base_rank["ranked_ids"])


def test_weight_candidate_keeps_identical_relation_labels() -> None:
    doc = ranking.load_relevance_benchmark_fixture(RANKING_FIXTURE)
    query = next(
        q for q in doc["queries"] if q["query_id"] == "q_cal_cmaj_full_spectrum"
    )
    baseline_cand = compare.candidate_by_id("harmonic.baseline.v1")
    heavy = compare.candidate_by_id("harmonic.weights.harmony_0.90_bpm_0.10")
    base_rank = compare.rank_query_for_candidate(
        query, baseline_cand, upstream_state="as_labeled"
    )
    heavy_rank = compare.rank_query_for_candidate(
        query, heavy, upstream_state="as_labeled"
    )
    base_rel = {
        d["synthetic_id"]: d["relation"] for d in base_rank["rank_details"]
    }
    heavy_rel = {
        d["synthetic_id"]: d["relation"] for d in heavy_rank["rank_details"]
    }
    assert base_rel == heavy_rel


def test_theory_gate_passes_for_every_frozen_candidate() -> None:
    theory_doc = theory.load_truth_table_fixture(THEORY_FIXTURE)
    for candidate in compare.HARMONIC_RANKING_CANDIDATES:
        gate = compare.theory_gate_for_candidate(theory_doc, candidate)
        assert gate["pass"] is True, candidate.candidate_id
        assert gate["relation_classification_accuracy"] == 1.0
        assert gate["ranking_gain_may_not_hide_theory_regression"] is True


def test_partitions_reported_separately_without_test_tuning_flag() -> None:
    doc = ranking.load_relevance_benchmark_fixture(RANKING_FIXTURE)
    candidate = compare.candidate_by_id("harmonic.baseline.v1")
    scored = compare.score_candidate_on_ranking(doc, candidate)
    parts = scored["as_labeled"]["by_partition"]
    assert set(parts) == {"CALIBRATION", "TEST", "HOLDOUT"}
    assert scored["exploration_partition"] == "CALIBRATION"
    assert scored["frozen_evidence_partitions"] == ["TEST", "HOLDOUT"]
    assert parts["CALIBRATION"]["queries_total"] == 2
    assert parts["TEST"]["queries_total"] == 2
    assert parts["HOLDOUT"]["queries_total"] == 1


def test_determinism_two_passes_match_per_candidate() -> None:
    doc = ranking.load_relevance_benchmark_fixture(RANKING_FIXTURE)
    for candidate in compare.HARMONIC_RANKING_CANDIDATES:
        report = compare.measure_candidate_determinism(doc, candidate)
        assert report["deterministic"] is True, candidate.candidate_id


def test_run_rejects_output_inside_repo() -> None:
    inside = REPO_ROOT / ".pytest_aq6_compare_should_not_exist.json"
    with pytest.raises(ValueError, match="outside"):
        compare.run_aq6_harmonic_ranking_candidate_compare(
            output_path=inside,
            repo_root=REPO_ROOT,
        )


def test_run_writes_external_json_reproducible(tmp_path: Path) -> None:
    out = tmp_path / "aq6-ranking-candidate-compare.json"
    result = compare.run_aq6_harmonic_ranking_candidate_compare(
        output_path=out,
        repo_root=REPO_ROOT,
    )
    assert out.is_file()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["exit_status"] == compare.EXIT_REPRODUCIBLE
    assert loaded["document_type"] == compare.DOCUMENT_TYPE
    assert loaded["domain"] == "aq6.ranking"
    assert loaded["candidate_count"] == 4
    assert loaded["no_tuning_on_test"] is True
    assert loaded["production_switch"] is False
    assert loaded["theory_plane"]["mixed_into_ranking_metrics"] is False
    assert loaded["missing_evidence_guard"]["pass"] is True
    ids = [c["candidate_id"] for c in loaded["candidates"]]
    assert ids == [
        "harmonic.baseline.v1",
        "harmonic.weights.harmony_0.90_bpm_0.10",
        "harmonic.weights.harmony_1.00_bpm_0.00",
        "harmonic.rank_filter.drop_uncertain",
    ]
    baseline_entry = loaded["candidates"][0]
    assert baseline_entry["baseline_anchor"]["matches_1018_as_labeled"] is True
    assert baseline_entry["theory_gate"]["pass"] is True
    assert baseline_entry["ranking"]["as_labeled"]["macro"]["precision_at_1"] == 1.0
    for entry in loaded["candidates"]:
        assert entry["theory_gate"]["pass"] is True
        assert entry["determinism"]["deterministic"] is True
        assert "TEST" in entry["ranking"]["as_labeled"]["by_partition"]
        assert "HOLDOUT" in entry["ranking"]["as_labeled"]["by_partition"]
    assert result["exit_status"] == compare.EXIT_REPRODUCIBLE
    blob = out.read_text(encoding="utf-8")
    assert "D:/" not in blob
    assert "C:/" not in blob


def test_is_reproducible_requires_theory_and_baseline_anchor() -> None:
    incomplete = {
        "candidate_count": 4,
        "no_tuning_on_test": True,
        "production_switch": False,
        "missing_evidence_guard": {"pass": True},
        "candidates": [
            {
                "candidate_id": "harmonic.baseline.v1",
                "theory_gate": {"pass": False},
                "determinism": {"deterministic": True},
                "ranking": {
                    "as_labeled": {
                        "queries_total": 5,
                        "by_partition": {
                            "CALIBRATION": {},
                            "TEST": {},
                            "HOLDOUT": {},
                        },
                    }
                },
                "baseline_anchor": {"matches_1018_as_labeled": False},
            }
        ],
    }
    assert compare.is_reproducible(incomplete) is False
