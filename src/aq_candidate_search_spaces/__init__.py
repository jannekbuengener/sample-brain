"""Domain-owned candidate/config search-space providers (#1064).

Shared iteration lives in ``src.analysis_candidate_iterator``. Concrete
finite ordered spaces are owned by domain modules in this package.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "SEARCH_SPACE_ID",
    "SEARCH_SPACE_VERSION",
    "Aq1TempoSearchSpaceProvider",
    "pin_aq1_tempo_search_space",
]


def __getattr__(name: str) -> Any:
    if name in {
        "SEARCH_SPACE_ID",
        "SEARCH_SPACE_VERSION",
        "Aq1TempoSearchSpaceProvider",
        "pin_aq1_tempo_search_space",
    }:
        from src.aq_candidate_search_spaces.aq1_tempo import (
            SEARCH_SPACE_ID,
            SEARCH_SPACE_VERSION,
            Aq1TempoSearchSpaceProvider,
            pin_aq1_tempo_search_space,
        )

        mapping = {
            "SEARCH_SPACE_ID": SEARCH_SPACE_ID,
            "SEARCH_SPACE_VERSION": SEARCH_SPACE_VERSION,
            "Aq1TempoSearchSpaceProvider": Aq1TempoSearchSpaceProvider,
            "pin_aq1_tempo_search_space": pin_aq1_tempo_search_space,
        }
        return mapping[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
