"""Frozen RED coverage for the AQ6 second-domain search-space provider (#1200).

The AQ6 provider is the only new domain surface for the S10 portability proof.
Generic S5-S9 code must stay domain-neutral, so these cases also assert that no
AQ6 special-case path leaked into the generic chain.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.analysis_candidate_iterator import (
    AnalysisCandidateIteratorError,
    SearchSpaceProvider,
    iterate_candidates,
    search_space_fingerprint,
)
from src.analysis_eval_artifact import fingerprint
from src.analysis_headless_run import build_request
from src.aq6_harmonic_ranking_candidate_compare import (
    HARMONIC_RANKING_CANDIDATES,
    candidate_by_id,
    candidate_public,
)
from src.aq_candidate_search_spaces.aq6_harmonic import (
    SEARCH_SPACE_ID,
    SEARCH_SPACE_VERSION,
    Aq6HarmonicSearchSpaceProvider,
)

AQ6_DOMAIN = "aq6.ranking"
AQ6_ADAPTER_ID = "aq6.ranking.candidate_compare"

EXPECTED_CANDIDATE_IDS = (
    "harmonic.baseline.v1",
    "harmonic.weights.harmony_0.90_bpm_0.10",
    "harmonic.weights.harmony_1.00_bpm_0.00",
    "harmonic.rank_filter.drop_uncertain",
)

# Generic S5-S9 chain that must never learn an AQ6 branch.
GENERIC_CHAIN_MODULES = (
    "src/analysis_quality_loop_supervisor.py",
    "src/analysis_quality_closed_cycle.py",
    "src/analysis_candidate_iterator.py",
    "src/analysis_quality_loop_state.py",
    "src/analysis_locked_holdout.py",
)


def _provider() -> Aq6HarmonicSearchSpaceProvider:
    return Aq6HarmonicSearchSpaceProvider()


def _baseline_id() -> str:
    return EXPECTED_CANDIDATE_IDS[0]


def _baseline_fp() -> str:
    return fingerprint(candidate_public(candidate_by_id(_baseline_id())))


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# 1 — provider exposes exactly the four canonical frozen candidates, in order
# ---------------------------------------------------------------------------


def test_provider_exposes_exactly_the_four_frozen_candidates_in_order() -> None:
    provider = _provider()

    members = provider.ordered_members()

    assert [member["candidate_id"] for member in members] == list(
        EXPECTED_CANDIDATE_IDS
    )
    assert [candidate.candidate_id for candidate in HARMONIC_RANKING_CANDIDATES] == list(
        EXPECTED_CANDIDATE_IDS
    )
    assert len(members) == 4
    assert provider.search_space_id == SEARCH_SPACE_ID
    assert provider.search_space_version == SEARCH_SPACE_VERSION
    assert isinstance(provider, SearchSpaceProvider)


def test_provider_is_deterministic_across_instances() -> None:
    first = _provider()
    second = _provider()

    assert first.ordered_members() == second.ordered_members()
    assert first.search_space_fingerprint() == second.search_space_fingerprint()


# ---------------------------------------------------------------------------
# 2 — every config fingerprint matches the canonical candidate representation
# ---------------------------------------------------------------------------


def test_provider_config_fingerprints_match_canonical_candidate_public() -> None:
    members = _provider().ordered_members()

    for member, candidate in zip(members, HARMONIC_RANKING_CANDIDATES):
        assert member["config_fingerprint"] == fingerprint(candidate_public(candidate))


def test_provider_config_fingerprints_match_adapter_candidate_identity() -> None:
    """The AQ6 headless adapter is the authority for candidate identity."""
    from src.aq_headless_adapters.aq6_harmonic_ranking_compare import (
        candidate_config_fingerprint,
    )

    members = _provider().ordered_members()

    for member in members:
        assert member["config_fingerprint"] == candidate_config_fingerprint(
            member["candidate_id"]
        )


def test_search_space_fingerprint_uses_existing_iterator_contract() -> None:
    provider = _provider()
    members = provider.ordered_members()

    expected = search_space_fingerprint(
        search_space_id=provider.search_space_id,
        search_space_version=provider.search_space_version,
        ordered_members=members,
    )

    assert provider.search_space_fingerprint() == expected


# ---------------------------------------------------------------------------
# 3 — unknown / modified candidate identity fails closed
# ---------------------------------------------------------------------------


def test_iterator_rejects_modified_candidate_config_fingerprint() -> None:
    provider = _provider()

    with pytest.raises(AnalysisCandidateIteratorError):
        iterate_candidates(
            domain=AQ6_DOMAIN,
            next_action="continue_calibration",
            partition_role="calibration",
            provider=provider,
            current_candidate_id=_baseline_id(),
            current_config_fingerprint="0" * 64,
            visited_candidate_ids=[_baseline_id()],
            search_space_fingerprint=provider.search_space_fingerprint(),
        )


def test_iterator_rejects_unknown_candidate_identity() -> None:
    provider = _provider()

    with pytest.raises(AnalysisCandidateIteratorError):
        iterate_candidates(
            domain=AQ6_DOMAIN,
            next_action="continue_calibration",
            partition_role="calibration",
            provider=provider,
            current_candidate_id="harmonic.unknown.v9",
            current_config_fingerprint=_baseline_fp(),
            visited_candidate_ids=[],
            search_space_fingerprint=provider.search_space_fingerprint(),
        )


def test_headless_adapter_fails_closed_on_unknown_candidate(tmp_path: Path) -> None:
    from src.analysis_headless_run import bind_adapter

    request = build_request(
        domain=AQ6_DOMAIN,
        adapter_id=AQ6_ADAPTER_ID,
        operation="compare",
        benchmark_id="aq6-search-space-bench-v1",
        dataset_id="aq6-search-space-dataset-v1",
        dataset_content_fingerprint=fingerprint({"dataset": "aq6-search-space"}),
        partition_id="aq6-search-space-cal",
        partition_role="calibration",
        baseline_candidate_id="harmonic.unknown.v9",
        baseline_config_fingerprint="0" * 64,
        current_candidate_id="harmonic.unknown.v9",
        current_config_fingerprint="0" * 64,
        evidence_intent="domain_artifact",
    )
    adapter = bind_adapter(
        AQ6_ADAPTER_ID, output_path=tmp_path / "aq6-unknown.json"
    )

    result = adapter.run(request)

    assert result["run_status"] == "controlled_failure"
    assert result["error"]["code"] == "unknown_candidate"


# ---------------------------------------------------------------------------
# 4 — calibration iteration cannot run against TEST/HOLDOUT
# ---------------------------------------------------------------------------


def test_iterator_refuses_calibration_action_on_locked_partition() -> None:
    provider = _provider()

    with pytest.raises(AnalysisCandidateIteratorError):
        iterate_candidates(
            domain=AQ6_DOMAIN,
            next_action="continue_calibration",
            partition_role="holdout",
            provider=provider,
            current_candidate_id=_baseline_id(),
            current_config_fingerprint=_baseline_fp(),
            visited_candidate_ids=[_baseline_id()],
            search_space_fingerprint=provider.search_space_fingerprint(),
        )


def test_headless_request_refuses_compare_on_locked_partition() -> None:
    from src.analysis_headless_run import AnalysisHeadlessRunError

    with pytest.raises(AnalysisHeadlessRunError):
        build_request(
            domain=AQ6_DOMAIN,
            adapter_id=AQ6_ADAPTER_ID,
            operation="compare",
            benchmark_id="aq6-search-space-bench-v1",
            dataset_id="aq6-search-space-dataset-v1",
            dataset_content_fingerprint=fingerprint({"dataset": "aq6-search-space"}),
            partition_id="aq6-search-space-test",
            partition_role="test",
            baseline_candidate_id=_baseline_id(),
            baseline_config_fingerprint=_baseline_fp(),
            current_candidate_id=_baseline_id(),
            current_config_fingerprint=_baseline_fp(),
            evidence_intent="domain_artifact",
        )


# ---------------------------------------------------------------------------
# 6 — preference stays NOT_REQUIRED (no fabricated ranking/decision signal)
# ---------------------------------------------------------------------------


def test_preference_plane_stays_not_required_without_pseudo_signal() -> None:
    from src.aq_headless_adapters.aq6_harmonic_ranking_compare import (
        ADAPTER_CAPABILITIES,
        DOMAIN_TOKEN,
    )

    assert DOMAIN_TOKEN == AQ6_DOMAIN
    assert "locked_evaluation" in ADAPTER_CAPABILITIES
    assert "compare" in ADAPTER_CAPABILITIES


def test_preference_plane_is_not_required_in_real_aq6_execution(tmp_path: Path) -> None:
    from src.analysis_headless_run import bind_adapter

    provider = _provider()
    baseline = provider.ordered_members()[0]
    request = build_request(
        domain=AQ6_DOMAIN,
        adapter_id=AQ6_ADAPTER_ID,
        operation="compare",
        benchmark_id="aq6-search-space-bench-v1",
        dataset_id="aq6-search-space-dataset-v1",
        dataset_content_fingerprint=fingerprint({"dataset": "aq6-search-space"}),
        partition_id="aq6-search-space-cal",
        partition_role="calibration",
        baseline_candidate_id=baseline["candidate_id"],
        baseline_config_fingerprint=baseline["config_fingerprint"],
        current_candidate_id=baseline["candidate_id"],
        current_config_fingerprint=baseline["config_fingerprint"],
        evidence_intent="domain_artifact",
    )
    adapter = bind_adapter(
        AQ6_ADAPTER_ID, output_path=tmp_path / "aq6-compare.json"
    )

    result = adapter.run(request)

    assert result["run_status"] == "completed"
    planes = result["domain_planes"]
    assert planes["preference"]["status"] == "NOT_REQUIRED"
    assert planes["preference"]["signal"] is None
    assert planes["ranking"]["mixed_into_aggregate_score"] is False


# ---------------------------------------------------------------------------
# 7 — valid AQ6 self-start advances through the generic candidate iterator
# ---------------------------------------------------------------------------


def test_generic_iterator_advances_to_the_next_declared_aq6_candidate() -> None:
    provider = _provider()

    result = iterate_candidates(
        domain=AQ6_DOMAIN,
        next_action="continue_calibration",
        partition_role="calibration",
        provider=provider,
        current_candidate_id=_baseline_id(),
        current_config_fingerprint=_baseline_fp(),
        visited_candidate_ids=[_baseline_id()],
        search_space_fingerprint=provider.search_space_fingerprint(),
    )

    assert result["iterator_effect"] == "advance"
    assert result["next_candidate"]["candidate_id"] == EXPECTED_CANDIDATE_IDS[1]
    assert result["next_candidate"]["config_fingerprint"] == fingerprint(
        candidate_public(candidate_by_id(EXPECTED_CANDIDATE_IDS[1]))
    )
    assert result["production_authorized"] is False
    assert result["search_space"]["search_space_fingerprint"] == (
        provider.search_space_fingerprint()
    )


def test_generic_iterator_binds_exact_aq6_search_space_identity() -> None:
    provider = _provider()

    result = iterate_candidates(
        domain=AQ6_DOMAIN,
        next_action="continue_calibration",
        partition_role="calibration",
        provider=provider,
        current_candidate_id=_baseline_id(),
        current_config_fingerprint=_baseline_fp(),
        visited_candidate_ids=[_baseline_id()],
        search_space_fingerprint=provider.search_space_fingerprint(),
    )

    assert result["search_space"]["search_space_id"] == SEARCH_SPACE_ID
    assert result["search_space"]["search_space_version"] == SEARCH_SPACE_VERSION
    assert [member["candidate_id"] for member in result["search_space"]["ordered_members"]] == list(
        EXPECTED_CANDIDATE_IDS
    )


# ---------------------------------------------------------------------------
# Cross-domain neutrality — generic S5-S9 code keeps no AQ6 special case
# ---------------------------------------------------------------------------


def test_generic_chain_modules_contain_no_aq6_special_case() -> None:
    root = _repo_root()

    for relative in GENERIC_CHAIN_MODULES:
        path = root / relative
        assert path.exists(), relative
        text = path.read_text(encoding="utf-8").casefold()
        assert "aq6" not in text, f"{relative} must not contain an AQ6 special case"


def test_domain_owned_surface_owns_the_aq6_provider() -> None:
    root = _repo_root()

    provider_path = root / "src" / "aq_candidate_search_spaces" / "aq6_harmonic.py"
    assert provider_path.exists()
    assert "aq6" not in Path(
        root / "src" / "analysis_quality_loop_supervisor.py"
    ).read_text(encoding="utf-8").casefold()
