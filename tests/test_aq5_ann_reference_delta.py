"""Frozen tests for AQ5 ANN vs NumPy reference delta harness (#1011).

TEST FREEZE: these assertions define the ANN/ranking-separation measurement
contract. Fix the harness, not these expectations, when they turn red.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from src import aq5_ann_reference_delta as ann
from src import aq5_relevance_benchmark as relevance
from src.vec_availability import VecAvailabilityReport


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_ann_identity_and_exit_tokens_are_frozen() -> None:
    assert ann.DOCUMENT_TYPE == "sample-brain.aq5.ann-reference-delta.v1"
    assert ann.SCHEMA_VERSION == "1.0.0"
    assert ann.BENCHMARK_ID == relevance.BENCHMARK_ID
    assert ann.EXIT_MEASURED == "AQ5_ANN_REFERENCE_DELTA_MEASURED"
    assert ann.EXIT_BACKEND_HOLD == "AQ5_ANN_BACKEND_HOLD"
    assert ann.EXIT_INCOMPLETE == "AQ5_ANN_COMPARISON_INCOMPLETE"
    assert ann.REFERENCE_PATH_ID == "sample-brain.aq5.path.numpy.exact_reference"
    assert ann.APPROX_PATH_ID == "sample-brain.aq5.path.sqlite_vec.ann_vs_numpy"


def test_backend_identities_freeze_reference_and_approx() -> None:
    identities = ann.backend_path_identities()
    by_id = {row["path_id"]: row for row in identities}
    assert set(by_id) == {ann.REFERENCE_PATH_ID, ann.APPROX_PATH_ID}
    assert by_id[ann.REFERENCE_PATH_ID]["role"] == "exact_reference"
    assert by_id[ann.REFERENCE_PATH_ID]["plane"] == "aq5.ranking"
    assert by_id[ann.REFERENCE_PATH_ID]["default_promotion"] is True
    assert by_id[ann.APPROX_PATH_ID]["role"] == "approximate_index"
    assert by_id[ann.APPROX_PATH_ID]["plane"] == "aq5.ranking"
    assert by_id[ann.APPROX_PATH_ID]["default_promotion"] is False
    assert by_id[ann.APPROX_PATH_ID]["promotion_blocked"] is True


def test_topk_overlap_and_rank_displacement_helpers() -> None:
    reference = [10, 20, 30, 40, 50]
    approx_perfect = [10, 20, 30, 40, 50]
    approx_shifted = [10, 30, 20, 50, 40]
    relevant = {20, 40}

    assert ann.topk_set_overlap(reference, approx_perfect, k=5) == pytest.approx(1.0)
    assert ann.topk_set_overlap(reference, approx_shifted, k=5) == pytest.approx(1.0)
    assert ann.topk_set_overlap(reference, [10, 20, 99, 98, 97], k=5) == pytest.approx(0.4)
    # Filtered paths may return fewer than K hits; identical short lists are perfect.
    assert ann.topk_set_overlap([2, 1, 7], [2, 1, 7], k=5) == pytest.approx(1.0)
    assert ann.topk_set_overlap([2, 1, 7], [2, 1], k=5) == pytest.approx(2 / 3)

    displacements = ann.relevant_rank_displacements(
        reference_ids=reference,
        approx_ids=approx_shifted,
        relevant_ids=relevant,
    )
    by_id = {row["sample_id"]: row for row in displacements}
    assert by_id[20]["reference_rank"] == 2
    assert by_id[20]["approx_rank"] == 3
    assert by_id[20]["displacement"] == 1
    assert by_id[40]["reference_rank"] == 4
    assert by_id[40]["approx_rank"] == 5
    assert by_id[40]["displacement"] == 1

    delta = ann.ordered_ranking_delta(reference, approx_shifted)
    assert delta["identical_ordered_topk"] is False
    assert delta["first_divergence_rank"] == 2
    assert delta["position_mismatch_count"] == 4

    perfect = ann.ordered_ranking_delta(reference, approx_perfect)
    assert perfect["identical_ordered_topk"] is True
    assert perfect["first_divergence_rank"] is None
    assert perfect["position_mismatch_count"] == 0


def test_planes_never_opaque_combine_ranking_and_latency() -> None:
    payload = ann.separate_reporting_planes(
        ranking={"mean_topk_overlap": 1.0},
        operational={"p50_ms": 12.0},
        retrieval_note={"status": "out_of_scope", "cite": "#1010"},
    )
    assert set(payload) == {"aq5.ranking", "operational", "aq5.retrieval"}
    assert "p50_ms" not in payload["aq5.ranking"]
    assert "mean_topk_overlap" not in payload["operational"]
    assert payload["aq5.retrieval"]["status"] == "out_of_scope"
    assert "quality_latency" not in payload
    assert "combined_score" not in payload


def test_run_rejects_output_inside_repo(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    inside = REPO_ROOT / ".pytest_aq5_ann_delta_should_not_exist.json"
    with pytest.raises(ValueError, match="outside"):
        ann.run_aq5_ann_reference_delta(
            work_dir=work,
            output_path=inside,
            repo_root=REPO_ROOT,
            include_runtime=False,
        )


def test_unavailable_backend_fail_closed_hold(tmp_path: Path) -> None:
    work = tmp_path / "work-hold"
    out = tmp_path / "aq5-ann-hold.json"
    unavailable = VecAvailabilityReport(
        available=False,
        reason="not_installed",
        python_version="3.12.0",
        sqlite_version="3.49.1",
        vec_version=None,
        package_installed=False,
        extension_loaded=False,
    )
    with mock.patch.object(ann, "probe_sqlite_vec", return_value=unavailable):
        result = ann.run_aq5_ann_reference_delta(
            work_dir=work,
            output_path=out,
            repo_root=REPO_ROOT,
            include_runtime=False,
        )

    assert out.is_file()
    assert result["exit_status"] == ann.EXIT_BACKEND_HOLD
    ranking = result["aq5.ranking"]
    assert ranking["approximate_path"]["status"] == "HOLD"
    assert ranking["approximate_path"]["path_id"] == ann.APPROX_PATH_ID
    assert ranking["reference_path"]["path_id"] == ann.REFERENCE_PATH_ID
    assert ranking["reference_path"]["status"] in {"measured", "HOLD"}
    assert result["notes"]["sqlite_vec_promotion"] is False
    assert result["notes"]["default_search_backend"] == "numpy"
    assert "quality_latency" not in result
    assert result["aq5.retrieval"]["status"] == "out_of_scope"
    assert result["hold_stubs"]
    holds = {item["item"]: item["status"] for item in result["hold_stubs"]}
    assert holds["graded_relevance_ndcg"] == "HOLD"
    assert holds["sqlite_vec_production_promotion"] == "HOLD"
    dumped = json.dumps(result)
    assert "D:/" not in dumped
    assert "D:\\" not in dumped
    assert "/Users/" not in dumped
    assert "/home/" not in dumped


def test_run_measures_ann_delta_when_sqlite_vec_available(tmp_path: Path) -> None:
    from src.vec_availability import is_sqlite_vec_available

    if not is_sqlite_vec_available():
        pytest.skip("sqlite-vec optional dependency unavailable")

    work = tmp_path / "work-ann"
    out = tmp_path / "aq5-ann-reference-delta.json"
    result = ann.run_aq5_ann_reference_delta(
        work_dir=work,
        output_path=out,
        repo_root=REPO_ROOT,
        include_runtime=True,
        runtime_repetitions=3,
    )

    assert out.is_file()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded == result
    assert result["document_type"] == ann.DOCUMENT_TYPE
    assert result["schema_version"] == ann.SCHEMA_VERSION
    assert result["benchmark_id"] == relevance.BENCHMARK_ID
    assert result["exit_status"] == ann.EXIT_MEASURED

    assert set(result) >= {
        "aq5.ranking",
        "aq5.retrieval",
        "operational",
        "backend_paths",
        "hold_stubs",
    }
    assert "quality_latency" not in result
    assert "combined_score" not in result

    ranking = result["aq5.ranking"]
    assert ranking["ndcg_eligibility"] == "HOLD"
    assert ranking["reference_path"]["path_id"] == ann.REFERENCE_PATH_ID
    assert ranking["reference_path"]["status"] == "measured"
    assert ranking["approximate_path"]["path_id"] == ann.APPROX_PATH_ID
    assert ranking["approximate_path"]["status"] == "measured"
    assert ranking["approximate_path"]["default_promotion"] is False
    assert ranking["aggregate"]["query_count"] >= 1
    assert "mean_topk_overlap" in ranking["aggregate"]
    assert "mean_abs_relevant_displacement" in ranking["aggregate"]
    assert "identical_ordered_topk_rate" in ranking["aggregate"]
    assert set(ranking["by_mode"]) <= {"vector", "filter", "hybrid"}
    assert ranking["determinism"]["reference"]["status"] in {"measured", "HOLD"}
    assert ranking["determinism"]["approximate"]["status"] in {"measured", "HOLD"}

    assert result["aq5.retrieval"]["status"] == "out_of_scope"
    assert "#1010" in str(result["aq5.retrieval"].get("cite") or "")

    operational = result["operational"]
    assert operational["plane"] == "operational"
    assert "relevance_score" not in operational
    assert "mean_topk_overlap" not in operational

    assert result["notes"]["sqlite_vec_promotion"] is False
    assert result["notes"]["default_search_backend"] == "numpy"
    assert result["notes"]["issue_74_solved"] is False
    assert result["no_tuning_on_test"] is True

    dumped = json.dumps(result)
    assert "D:/" not in dumped
    assert "D:\\" not in dumped
    for key in ("work_dir", "db_path", "audio_path", "file_path", "source_path"):
        assert key not in result
