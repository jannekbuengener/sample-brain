"""Domain-owned candidate search-space providers for analyzer optimization.

Generic S5-S9 code resolves the search space of a domain through
:func:`default_search_space_provider`, so the generic chain never needs a
domain-specific branch. Domain owners register their provider here.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from src.analysis_candidate_iterator import SearchSpaceProvider
from src.aq_candidate_search_spaces.aq1_tempo import Aq1TempoSearchSpaceProvider
from src.aq_candidate_search_spaces.aq6_harmonic import Aq6HarmonicSearchSpaceProvider

SEARCH_SPACE_PROVIDERS: Mapping[str, type[SearchSpaceProvider]] = MappingProxyType(
    {
        "aq1.tempo": Aq1TempoSearchSpaceProvider,
        "aq6.ranking": Aq6HarmonicSearchSpaceProvider,
    }
)


def default_search_space_provider(domain: str) -> SearchSpaceProvider:
    """Return the registered provider for ``domain``; unknown domains fail closed."""
    try:
        factory = SEARCH_SPACE_PROVIDERS[domain]
    except KeyError:
        raise KeyError(domain) from None
    return factory()


def registered_search_space_domains() -> tuple[str, ...]:
    """Registered domains in deterministic order."""
    return tuple(sorted(SEARCH_SPACE_PROVIDERS))


__all__ = [
    "SEARCH_SPACE_PROVIDERS",
    "default_search_space_provider",
    "registered_search_space_domains",
]
