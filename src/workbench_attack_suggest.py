"""Compatibility re-exports for Workbench attack suggestion consumers."""
from __future__ import annotations

from .attack_analysis import (
    AttackSuggestion,
    _ENERGY_RATIO_THRESHOLD,
    _FRAME_MS,
    _PEAK_FRACTION_THRESHOLD,
    suggest_attack_ms,
)

__all__ = ["AttackSuggestion", "suggest_attack_ms"]
