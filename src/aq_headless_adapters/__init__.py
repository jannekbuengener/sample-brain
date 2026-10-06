"""Headless AQ domain adapters (#1054).

Concrete adapters live here; ``STATIC_ADAPTER_REGISTRY`` wiring lives in
``src.analysis_headless_run`` (M6 integrator ownership).
"""

from __future__ import annotations

from src.aq_headless_adapters.aq1_tempo_compare import (
    ADAPTER_ID as AQ1_TEMPO_COMPARE_ADAPTER_ID,
    ADAPTER_VERSION as AQ1_TEMPO_COMPARE_ADAPTER_VERSION,
    Aq1TempoCompareAdapter,
)
from src.aq_headless_adapters.aq6_harmonic_ranking_compare import (
    ADAPTER_ID as AQ6_RANKING_COMPARE_ADAPTER_ID,
    ADAPTER_VERSION as AQ6_RANKING_COMPARE_ADAPTER_VERSION,
    Aq6HarmonicRankingCompareAdapter,
)

__all__ = [
    "AQ1_TEMPO_COMPARE_ADAPTER_ID",
    "AQ1_TEMPO_COMPARE_ADAPTER_VERSION",
    "AQ6_RANKING_COMPARE_ADAPTER_ID",
    "AQ6_RANKING_COMPARE_ADAPTER_VERSION",
    "Aq1TempoCompareAdapter",
    "Aq6HarmonicRankingCompareAdapter",
]
