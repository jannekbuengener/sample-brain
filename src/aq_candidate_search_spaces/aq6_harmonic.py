"""AQ6 harmonic ranking candidate search-space provider for #1200.

Reuses the frozen AQ6 candidate declaration. The declaration order is domain
policy and must not be re-sorted here.
"""

from __future__ import annotations

from src.analysis_candidate_iterator import search_space_fingerprint
from src.analysis_eval_artifact import fingerprint
from src.aq6_harmonic_ranking_candidate_compare import (
    HARMONIC_RANKING_CANDIDATES,
    HarmonicRankingCandidate,
    candidate_public,
)

SEARCH_SPACE_ID = "aq6.ranking.candidate-search-space"
SEARCH_SPACE_VERSION = "1.0.0"


def _candidate_config_fingerprint(candidate: HarmonicRankingCandidate) -> str:
    """Mirror the frozen AQ6 public candidate config identity without adapter coupling."""
    return fingerprint(candidate_public(candidate))


class Aq6HarmonicSearchSpaceProvider:
    """Finite ordered AQ6 candidate/config search space."""

    @property
    def search_space_id(self) -> str:
        return SEARCH_SPACE_ID

    @property
    def search_space_version(self) -> str:
        return SEARCH_SPACE_VERSION

    def ordered_members(self) -> list[dict[str, str]]:
        return [
            {
                "candidate_id": candidate.candidate_id,
                "config_fingerprint": _candidate_config_fingerprint(candidate),
            }
            for candidate in HARMONIC_RANKING_CANDIDATES
        ]

    def search_space_fingerprint(self) -> str:
        return search_space_fingerprint(
            search_space_id=self.search_space_id,
            search_space_version=self.search_space_version,
            ordered_members=self.ordered_members(),
        )


__all__ = [
    "SEARCH_SPACE_ID",
    "SEARCH_SPACE_VERSION",
    "Aq6HarmonicSearchSpaceProvider",
]
