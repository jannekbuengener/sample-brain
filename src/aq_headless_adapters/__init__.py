"""Headless AQ domain adapters (#1054).

Concrete adapters live here; ``STATIC_ADAPTER_REGISTRY`` wiring lives in
``src.analysis_headless_run`` (M6 integrator ownership).
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "AQ1_TEMPO_COMPARE_ADAPTER_ID",
    "AQ1_TEMPO_COMPARE_ADAPTER_VERSION",
    "AQ6_RANKING_COMPARE_ADAPTER_ID",
    "AQ6_RANKING_COMPARE_ADAPTER_VERSION",
    "Aq1TempoCompareAdapter",
    "Aq6HarmonicRankingCompareAdapter",
]


def __getattr__(name: str) -> Any:
    if name in {
        "AQ1_TEMPO_COMPARE_ADAPTER_ID",
        "AQ1_TEMPO_COMPARE_ADAPTER_VERSION",
        "Aq1TempoCompareAdapter",
    }:
        from src.aq_headless_adapters.aq1_tempo_compare import (
            ADAPTER_ID as AQ1_TEMPO_COMPARE_ADAPTER_ID,
            ADAPTER_VERSION as AQ1_TEMPO_COMPARE_ADAPTER_VERSION,
            Aq1TempoCompareAdapter,
        )

        mapping = {
            "AQ1_TEMPO_COMPARE_ADAPTER_ID": AQ1_TEMPO_COMPARE_ADAPTER_ID,
            "AQ1_TEMPO_COMPARE_ADAPTER_VERSION": AQ1_TEMPO_COMPARE_ADAPTER_VERSION,
            "Aq1TempoCompareAdapter": Aq1TempoCompareAdapter,
        }
        return mapping[name]
    if name in {
        "AQ6_RANKING_COMPARE_ADAPTER_ID",
        "AQ6_RANKING_COMPARE_ADAPTER_VERSION",
        "Aq6HarmonicRankingCompareAdapter",
    }:
        from src.aq_headless_adapters.aq6_harmonic_ranking_compare import (
            ADAPTER_ID as AQ6_RANKING_COMPARE_ADAPTER_ID,
            ADAPTER_VERSION as AQ6_RANKING_COMPARE_ADAPTER_VERSION,
            Aq6HarmonicRankingCompareAdapter,
        )

        mapping = {
            "AQ6_RANKING_COMPARE_ADAPTER_ID": AQ6_RANKING_COMPARE_ADAPTER_ID,
            "AQ6_RANKING_COMPARE_ADAPTER_VERSION": AQ6_RANKING_COMPARE_ADAPTER_VERSION,
            "Aq6HarmonicRankingCompareAdapter": Aq6HarmonicRankingCompareAdapter,
        }
        return mapping[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
