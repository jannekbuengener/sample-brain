from __future__ import annotations

from src import attack_analysis, aq3_onset_attack_baseline as baseline
from src import aq3_onset_attack_candidate_compare as compare
from src import workbench_attack_suggest as facade


def test_workbench_facade_reexports_canonical_class_and_function() -> None:
    assert facade.AttackSuggestion is attack_analysis.AttackSuggestion
    assert facade.suggest_attack_ms is attack_analysis.suggest_attack_ms


def test_workbench_facade_preserves_frozen_candidate_constants() -> None:
    assert facade._FRAME_MS == attack_analysis._FRAME_MS
    assert facade._ENERGY_RATIO_THRESHOLD == attack_analysis._ENERGY_RATIO_THRESHOLD
    assert facade._PEAK_FRACTION_THRESHOLD == attack_analysis._PEAK_FRACTION_THRESHOLD
    assert facade.__all__ == ["AttackSuggestion", "suggest_attack_ms"]


def test_aq3_attack_surfaces_bind_the_canonical_function() -> None:
    assert baseline.suggest_attack_ms is attack_analysis.suggest_attack_ms
    assert compare.suggest_attack_ms is attack_analysis.suggest_attack_ms
