"""Real-domain proof for the AQ1 tempo candidate search space (#1064 W1)."""

from __future__ import annotations

from src.analysis_candidate_iterator import iterate_candidates
from src.analysis_eval_artifact import fingerprint
from src.aq_candidate_search_spaces.aq1_tempo import (
    SEARCH_SPACE_ID,
    SEARCH_SPACE_VERSION,
    Aq1TempoSearchSpaceProvider,
)
from src.fsld_aq1_tempo_candidate_compare import (
    SCHEMA_VERSION as AQ1_SCHEMA_VERSION,
    TEMPO_CANDIDATES,
)


def _expected_config_fingerprint(candidate) -> str:
    return fingerprint(
        {
            "analyzer_id": candidate.analyzer_id,
            "bpm_normalization": candidate.bpm_normalization,
            "candidate_id": candidate.candidate_id,
            "schema_version": AQ1_SCHEMA_VERSION,
        }
    )


def test_aq1_provider_reuses_frozen_domain_order_and_config_identity() -> None:
    provider = Aq1TempoSearchSpaceProvider()
    expected = [
        {
            "candidate_id": candidate.candidate_id,
            "config_fingerprint": _expected_config_fingerprint(candidate),
        }
        for candidate in TEMPO_CANDIDATES
    ]

    assert SEARCH_SPACE_ID == "aq1.tempo.candidate-search-space"
    assert SEARCH_SPACE_VERSION == "1.0.0"
    assert provider.search_space_id == SEARCH_SPACE_ID
    assert provider.search_space_version == SEARCH_SPACE_VERSION
    assert provider.ordered_members() == expected
    assert provider.search_space_fingerprint() == provider.search_space_fingerprint()


def test_aq1_real_provider_advances_then_exhausts_in_frozen_order() -> None:
    provider = Aq1TempoSearchSpaceProvider()
    members = provider.ordered_members()

    first = iterate_candidates(
        domain="aq1.tempo",
        next_action="continue_calibration",
        partition_role="calibration",
        provider=provider,
        current_candidate_id=members[0]["candidate_id"],
        current_config_fingerprint=members[0]["config_fingerprint"],
        visited_candidate_ids=[members[0]["candidate_id"]],
        search_space_fingerprint=provider.search_space_fingerprint(),
    )
    assert first["iterator_effect"] == "advance"
    assert first["next_candidate"] == members[1]

    second = iterate_candidates(
        domain="aq1.tempo",
        next_action="continue_calibration",
        partition_role="calibration",
        provider=provider,
        current_candidate_id=members[1]["candidate_id"],
        current_config_fingerprint=members[1]["config_fingerprint"],
        visited_candidate_ids=[members[0]["candidate_id"], members[1]["candidate_id"]],
        search_space_fingerprint=provider.search_space_fingerprint(),
    )
    assert second["iterator_effect"] == "advance"
    assert second["next_candidate"] == members[2]

    exhausted = iterate_candidates(
        domain="aq1.tempo",
        next_action="continue_calibration",
        partition_role="calibration",
        provider=provider,
        current_candidate_id=members[2]["candidate_id"],
        current_config_fingerprint=members[2]["config_fingerprint"],
        visited_candidate_ids=[member["candidate_id"] for member in members],
        search_space_fingerprint=provider.search_space_fingerprint(),
    )
    assert exhausted["iterator_effect"] == "exhausted"
    assert "next_candidate" not in exhausted
    assert exhausted["production_authorized"] is False
