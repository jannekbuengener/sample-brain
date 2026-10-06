"""Frozen tests for AQ5 relevance benchmark identity (#1009).

TEST FREEZE: these assertions define the adopted ADR-0005 query/label contract.
Fix the benchmark module or partition overlay, not these expectations, when red.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from src import aq5_relevance_benchmark as bench


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_benchmark_identity_and_surface_paths_are_frozen() -> None:
    assert bench.BENCHMARK_ID == "sample-brain.aq5.relevance.adr0005-golden.v1"
    assert bench.DOCUMENT_TYPE == "sample-brain.aq5.relevance-benchmark.v1"
    assert bench.BENCHMARK_VERSION == "1.0.0"
    assert bench.LABEL_SOURCE == "adr0005_synthetic_binary"
    assert set(bench.SPLITS) == {"CALIBRATION", "TEST"}
    assert bench.TIER_A_SUITE_RELPATH.as_posix() == (
        "tests/fixtures/search_quality/golden_v1.yaml"
    )
    assert bench.TIER_B_SUITE_RELPATH.as_posix() == (
        "tests/fixtures/search_quality/golden_v2_clap.yaml"
    )
    assert bench.EXCLUDED_SPIKE_SUITE_RELPATH.as_posix() == (
        "tests/fixtures/search_quality/golden_v2_clap_vocal_proxy_spike.yaml"
    )
    assert bench.PARTITION_OVERLAY_RELPATH.as_posix() == (
        "tests/fixtures/search_quality/aq5_relevance_benchmark_v1.yaml"
    )


def test_build_manifest_freezes_query_identity_labels_and_partitions() -> None:
    manifest = bench.build_aq5_relevance_benchmark_manifest(repo_root=REPO_ROOT)

    assert manifest["document_type"] == bench.DOCUMENT_TYPE
    assert manifest["benchmark_id"] == bench.BENCHMARK_ID
    assert manifest["benchmark_version"] == bench.BENCHMARK_VERSION
    assert manifest["label_source"] == bench.LABEL_SOURCE
    assert manifest["status"] == "AQ5_RELEVANCE_BENCHMARK_FROZEN"
    assert manifest["graded_relevance"]["status"] == "HOLD"
    assert manifest["ndcg_eligibility"] == "HOLD"

    queries = {q["query_key"]: q for q in manifest["queries"]}
    assert len(queries) == 46  # 9 Tier-A + 37 Tier-B
    assert all(q["relevance_scheme"] == "binary" for q in queries.values())
    assert all(q["graded_labels"] is None for q in queries.values())

    splits = {q["split"] for q in queries.values()}
    assert splits == {"CALIBRATION", "TEST"}
    cal_keys = {k for k, q in queries.items() if q["split"] == "CALIBRATION"}
    test_keys = {k for k, q in queries.items() if q["split"] == "TEST"}
    assert cal_keys.isdisjoint(test_keys)
    assert len(cal_keys) + len(test_keys) == len(queries)
    assert len(cal_keys) >= 1
    assert len(test_keys) >= 1

    # Composite identity prevents cross-suite collisions with the excluded spike.
    assert "tier_a:kick_cluster" in queries
    assert "tier_b:singing_voice_text" in queries
    assert all(not k.startswith("spike:") for k in queries)

    tier_b = [q for q in queries.values() if q["suite"] == "tier_b"]
    assert len(tier_b) == 37
    assert all(q["negative_sample_ids"] for q in tier_b)
    assert all(q["relevant_sample_ids"] for q in tier_b)

    tier_a = [q for q in queries.values() if q["suite"] == "tier_a"]
    assert len(tier_a) == 9
    assert all(q["relevant_sample_ids"] for q in tier_a)
    assert all(not q["negative_sample_ids"] for q in tier_a)

    support = manifest["support_counts"]
    assert support["split"] == dict(Counter(q["split"] for q in queries.values()))
    assert support["suite"] == {"tier_a": 9, "tier_b": 37}
    for family in bench.TIER_B_QUERY_FAMILIES:
        assert support["query_family"][family] >= 1

    holds = {item["item"]: item["status"] for item in manifest["hold_stubs"]}
    assert holds["graded_relevance_ndcg"] == "HOLD"
    assert holds["vocal_no_vocal_production_claim"] == "HOLD"
    assert holds["genre_mood_production_claim"] == "HOLD"
    assert holds["vocal_proxy_spike_suite"] == "HOLD"
    assert holds["private_producer_reality_check_queries"] == "HOLD"

    excluded = manifest["excluded_surfaces"]
    assert excluded[0]["suite"] == "vocal_proxy_spike"
    assert excluded[0]["status"] == "HOLD"

    audit = manifest["leakage_audit"]
    assert audit["duplicate_query_keys"] == []
    assert audit["relevant_negative_overlap"] == []
    assert audit["private_absolute_paths"] == []
    assert audit["cross_split_query_text_collisions"] == []
    assert audit["cross_split_audio_fixture_collisions"] == []
    assert audit["partition_coverage_ok"] is True


def test_audit_is_reproducible_and_rejects_partition_drift(tmp_path: Path) -> None:
    first = bench.audit_aq5_relevance_benchmark(repo_root=REPO_ROOT)
    second = bench.audit_aq5_relevance_benchmark(repo_root=REPO_ROOT)
    assert first["benchmark_id"] == second["benchmark_id"]
    assert first["partition_fingerprint"] == second["partition_fingerprint"]
    assert first["query_set_fingerprint"] == second["query_set_fingerprint"]
    assert first["status"] == "AQ5_RELEVANCE_BENCHMARK_FROZEN"

    # Partition overlay must cover every included query exactly once.
    broken = tmp_path / "broken_overlay.yaml"
    broken.write_text(
        "benchmark_id: sample-brain.aq5.relevance.adr0005-golden.v1\n"
        "partitions:\n"
        "  tier_a:\n"
        "    CALIBRATION: [kick_cluster]\n"
        "    TEST: []\n"
        "  tier_b:\n"
        "    CALIBRATION: []\n"
        "    TEST: []\n",
        encoding="utf-8",
    )
    with pytest.raises(bench.Aq5RelevanceBenchmarkError, match="partition"):
        bench.build_aq5_relevance_benchmark_manifest(
            repo_root=REPO_ROOT,
            partition_overlay_path=broken,
        )


def test_write_manifest_rejects_path_inside_repo(tmp_path: Path) -> None:
    inside = REPO_ROOT / ".pytest_aq5_relevance_manifest_should_not_exist.json"
    with pytest.raises(ValueError, match="outside"):
        bench.write_aq5_relevance_benchmark_manifest(
            inside, repo_root=REPO_ROOT, work_dir_guard_root=REPO_ROOT
        )

    out = tmp_path / "aq5_relevance_benchmark_manifest.json"
    payload = bench.write_aq5_relevance_benchmark_manifest(
        out, repo_root=REPO_ROOT, work_dir_guard_root=REPO_ROOT
    )
    assert out.is_file()
    assert payload["benchmark_id"] == bench.BENCHMARK_ID
    text = out.read_text(encoding="utf-8")
    assert "C:\\" not in text
    assert "/Users/" not in text
    assert "/home/" not in text
