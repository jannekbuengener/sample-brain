"""AQ1 tempo candidate search-space provider for #1064.

Reuses the frozen AQ1 candidate declaration. The declaration order is domain
policy and must not be re-sorted here.
"""

from __future__ import annotations

from src.analysis_candidate_iterator import search_space_fingerprint
from src.analysis_eval_artifact import fingerprint
from src.fsld_aq1_tempo_candidate_compare import (
    SCHEMA_VERSION as AQ1_SCHEMA_VERSION,
    TEMPO_CANDIDATES,
    TempoCandidate,
)

SEARCH_SPACE_ID = "aq1.tempo.candidate-search-space"
SEARCH_SPACE_VERSION = "1.0.0"


def _candidate_config_fingerprint(candidate: TempoCandidate) -> str:
    """Mirror the frozen AQ1 public candidate config identity without adapter coupling."""
    return fingerprint(
        {
            "analyzer_id": candidate.analyzer_id,
            "bpm_normalization": candidate.bpm_normalization,
            "candidate_id": candidate.candidate_id,
            "schema_version": AQ1_SCHEMA_VERSION,
        }
    )


class Aq1TempoSearchSpaceProvider:
    """Finite ordered AQ1 candidate/config search space."""

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
            for candidate in TEMPO_CANDIDATES
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
    "Aq1TempoSearchSpaceProvider",
]
