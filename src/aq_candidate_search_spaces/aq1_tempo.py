"""AQ1 tempo candidate search-space provider for #1064 W1.

Reuses the frozen AQ1 candidate declaration order from
``TEMPO_CANDIDATES`` / ``list_tempo_candidates()`` and the existing
``tempo_candidate_config_fingerprint`` authority (#1058/#1061).

Does not redefine candidate IDs, reorder members, interpret metrics/gates,
or drive a CALIBRATION loop.
"""

from __future__ import annotations

from src.analysis_candidate_iterator import (
    AnalysisCandidateIteratorError,
    search_space_fingerprint,
)

# Import headless-run first so STATIC_ADAPTER_REGISTRY init completes before the
# AQ1 adapter module is loaded (adapter imports headless helpers at module scope).
import src.analysis_headless_run as _analysis_headless_run  # noqa: F401
from src.aq_headless_adapters.aq1_tempo_compare import (
    tempo_candidate_config_fingerprint,
)
from src.fsld_aq1_tempo_candidate_compare import list_tempo_candidates

SEARCH_SPACE_ID = "aq1.tempo.candidate-search-space"
SEARCH_SPACE_VERSION = "1.0.0"


class Aq1TempoSearchSpaceProvider:
    """Finite ordered AQ1 candidate/config search space (domain-owned)."""

    @property
    def search_space_id(self) -> str:
        return SEARCH_SPACE_ID

    @property
    def search_space_version(self) -> str:
        return SEARCH_SPACE_VERSION

    def ordered_members(self) -> list[dict[str, str]]:
        # Declaration order is domain policy — do not re-sort.
        return [
            {
                "candidate_id": candidate.candidate_id,
                "config_fingerprint": tempo_candidate_config_fingerprint(
                    candidate.candidate_id
                ),
            }
            for candidate in list_tempo_candidates()
        ]

    def search_space_fingerprint(self) -> str:
        return search_space_fingerprint(
            search_space_id=self.search_space_id,
            search_space_version=self.search_space_version,
            ordered_members=self.ordered_members(),
        )


def pin_aq1_tempo_search_space(
    *,
    search_space_id: str | None = None,
    search_space_version: str | None = None,
    search_space_fingerprint: str | None = None,
) -> Aq1TempoSearchSpaceProvider:
    """Return the AQ1 provider after optional fail-closed identity pins."""
    provider = Aq1TempoSearchSpaceProvider()
    if search_space_id is not None and search_space_id != provider.search_space_id:
        raise AnalysisCandidateIteratorError(
            f"search_space_id mismatch: expected {provider.search_space_id!r}, "
            f"got {search_space_id!r}"
        )
    if (
        search_space_version is not None
        and search_space_version != provider.search_space_version
    ):
        raise AnalysisCandidateIteratorError(
            f"search_space_version mismatch: expected "
            f"{provider.search_space_version!r}, got {search_space_version!r}"
        )
    expected_fp = provider.search_space_fingerprint()
    if (
        search_space_fingerprint is not None
        and search_space_fingerprint != expected_fp
    ):
        raise AnalysisCandidateIteratorError(
            "search_space_fingerprint does not match AQ1 provider declaration"
        )
    return provider


__all__ = [
    "SEARCH_SPACE_ID",
    "SEARCH_SPACE_VERSION",
    "Aq1TempoSearchSpaceProvider",
    "pin_aq1_tempo_search_space",
]
