"""Public, evaluation-only Full-vs-HPSS key-profile measurements.

This module deliberately consumes explicit public fixture paths.  It neither
creates audio nor feeds a result into ``estimate_key`` / ``estimate_key_mode``:
the profile rankings remain diagnostic evidence for the #594 evaluation slice.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter_ns
from typing import Iterable

import math
import numpy as np

from .key_profile_analysis import KeyProfileRanking, rank_key_profiles
from .key_profile_audio_calibration import (
    extract_audio_chroma_statistics,
    extract_harmonic_chroma_evidence,
)


@dataclass(frozen=True)
class HarmonicProfileFixture:
    """One explicit public audio fixture used solely for profile evaluation."""

    name: str
    group: str
    path: Path
    root: str | None = None
    mode: str | None = None


@dataclass(frozen=True)
class RankedProfileMeasurement:
    """Stable, scalar-only representation of one 24-key profile ranking."""

    status: str
    root: str | None
    mode: str | None
    canonical_key: str | None
    best_score: float | None
    runner_up_score: float | None
    margin: float | None
    next_distinct_root_margin: float | None


@dataclass(frozen=True)
class HarmonicProfileFixtureEvaluation:
    """Full-path and harmonic-path diagnostic measurements for one fixture."""

    fixture: HarmonicProfileFixture
    full: RankedProfileMeasurement
    harmonic: RankedProfileMeasurement
    harmonic_rms: float
    percussive_rms: float
    harmonic_energy_fraction: float


def _measurement(ranking: KeyProfileRanking) -> RankedProfileMeasurement:
    return RankedProfileMeasurement(
        status=ranking.status,
        root=ranking.root,
        mode=ranking.mode,
        canonical_key=ranking.canonical_key,
        best_score=ranking.best_score,
        runner_up_score=ranking.runner_up_score,
        margin=ranking.margin,
        next_distinct_root_margin=ranking.next_distinct_root_margin,
    )


def _full_ranking(path: Path) -> KeyProfileRanking:
    statistics = extract_audio_chroma_statistics(path)
    return rank_key_profiles(statistics[0] if statistics is not None else ())


def _harmonic_ranking(path: Path) -> tuple[KeyProfileRanking, float, float, float]:
    evidence = extract_harmonic_chroma_evidence(path)
    return (
        rank_key_profiles(evidence.chroma_mean if evidence.chroma_mean is not None else ()),
        evidence.harmonic_rms,
        evidence.percussive_rms,
        evidence.harmonic_energy_fraction,
    )


def evaluate_harmonic_profile_fixtures(
    fixtures: Iterable[HarmonicProfileFixture],
) -> tuple[HarmonicProfileFixtureEvaluation, ...]:
    """Evaluate explicit fixtures through full and HPSS-harmonic CQT paths."""
    evaluations: list[HarmonicProfileFixtureEvaluation] = []
    for fixture in fixtures:
        full = _full_ranking(fixture.path)
        harmonic, harmonic_rms, percussive_rms, fraction = _harmonic_ranking(fixture.path)
        evaluations.append(HarmonicProfileFixtureEvaluation(
            fixture=fixture,
            full=_measurement(full),
            harmonic=_measurement(harmonic),
            harmonic_rms=harmonic_rms,
            percussive_rms=percussive_rms,
            harmonic_energy_fraction=fraction,
        ))
    return tuple(evaluations)


def _accuracy(values: Iterable[bool]) -> dict[str, int | float | None]:
    comparable = list(values)
    correct = sum(value is True for value in comparable)
    count = len(comparable)
    return {
        "correct_count": correct,
        "comparable_count": count,
        "accuracy": correct / count if count else None,
    }


def _distribution(values: Iterable[float | None]) -> dict[str, float | int | None]:
    finite = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    if not finite:
        return {"count": 0, "min": None, "median": None, "p95": None, "max": None}
    array = np.asarray(finite, dtype=np.float64)
    return {
        "count": int(array.size),
        "min": float(np.min(array)),
        "median": float(np.median(array)),
        "p95": float(np.percentile(array, 95)),
        "max": float(np.max(array)),
    }


def _expected_tonal(item: HarmonicProfileFixtureEvaluation) -> bool:
    return item.fixture.root is not None and item.fixture.mode is not None


def _path_metrics(
    items: Iterable[HarmonicProfileFixtureEvaluation], *, path: str
) -> dict[str, dict[str, int | float | None]]:
    values = list(items)
    measurements = [getattr(item, path) for item in values]
    return {
        "root_accuracy": _accuracy(
            measurement.root == item.fixture.root for item, measurement in zip(values, measurements)
        ),
        "mode_accuracy": _accuracy(
            measurement.mode == item.fixture.mode for item, measurement in zip(values, measurements)
        ),
        "full_key_accuracy": _accuracy(
            measurement.root == item.fixture.root and measurement.mode == item.fixture.mode
            for item, measurement in zip(values, measurements)
        ),
    }


def summarize_harmonic_profile_evaluation(
    evaluations: Iterable[HarmonicProfileFixtureEvaluation],
) -> dict[str, object]:
    """Return deterministic aggregate metrics without defining a production gate."""
    items = tuple(evaluations)
    tonal = tuple(item for item in items if _expected_tonal(item))
    groups: dict[str, object] = {}
    for group in sorted({item.fixture.group for item in tonal}):
        grouped = tuple(item for item in tonal if item.fixture.group == group)
        groups[group] = {
            "fixture_count": len(grouped),
            "full": _path_metrics(grouped, path="full"),
            "harmonic": _path_metrics(grouped, path="harmonic"),
        }

    transitions = {
        "full_correct_to_harmonic_correct": 0,
        "full_correct_to_harmonic_wrong": 0,
        "full_wrong_to_harmonic_correct": 0,
        "full_wrong_to_harmonic_wrong": 0,
    }
    for item in tonal:
        full_correct = item.full.root == item.fixture.root
        harmonic_correct = item.harmonic.root == item.fixture.root
        if full_correct and harmonic_correct:
            transitions["full_correct_to_harmonic_correct"] += 1
        elif full_correct:
            transitions["full_correct_to_harmonic_wrong"] += 1
        elif harmonic_correct:
            transitions["full_wrong_to_harmonic_correct"] += 1
        else:
            transitions["full_wrong_to_harmonic_wrong"] += 1

    non_tonal = tuple(item for item in items if not _expected_tonal(item))
    return {
        "groups": groups,
        "transitions": transitions,
        "non_tonal_diagnostics": {
            "fixture_count": len(non_tonal),
            "full_profile_margin": _distribution(item.full.margin for item in non_tonal),
            "full_profile_no_margin_count": sum(item.full.margin is None for item in non_tonal),
            "harmonic_profile_margin": _distribution(item.harmonic.margin for item in non_tonal),
            "harmonic_profile_no_margin_count": sum(
                item.harmonic.margin is None for item in non_tonal
            ),
            "harmonic_energy_fraction": _distribution(
                item.harmonic_energy_fraction for item in non_tonal
            ),
        },
    }


def _run_full_path(path: Path) -> None:
    _full_ranking(path)


def _run_harmonic_path(path: Path) -> None:
    _harmonic_ranking(path)


def _timings_ms(paths: Iterable[Path], runner) -> list[float]:
    timings: list[float] = []
    for path in paths:
        start = perf_counter_ns()
        runner(path)
        timings.append((perf_counter_ns() - start) / 1_000_000.0)
    return timings


def benchmark_harmonic_profile_paths(
    fixtures: Iterable[HarmonicProfileFixture], *, warmup_count: int = 1
) -> dict[str, int | float]:
    """Measure full and HPSS paths on explicit public fixtures.

    Warm-up executions are deliberately excluded from the reported timing
    samples.  The function reports observations only; it has no target or gate.
    """
    fixture_list = tuple(fixtures)
    if not fixture_list:
        raise ValueError("at least one fixture is required for benchmarking")
    if warmup_count < 0:
        raise ValueError("warmup_count must be non-negative")

    warmup = fixture_list[:warmup_count]
    for fixture in warmup:
        _run_full_path(fixture.path)
        _run_harmonic_path(fixture.path)

    paths = tuple(fixture.path for fixture in fixture_list)
    full_timings = np.asarray(_timings_ms(paths, _run_full_path), dtype=np.float64)
    harmonic_timings = np.asarray(_timings_ms(paths, _run_harmonic_path), dtype=np.float64)
    full_median = float(np.median(full_timings))
    harmonic_median = float(np.median(harmonic_timings))
    return {
        "warmup_file_count": len(warmup),
        "file_count": len(paths),
        "full_median_ms": full_median,
        "full_p95_ms": float(np.percentile(full_timings, 95)),
        "harmonic_median_ms": harmonic_median,
        "harmonic_p95_ms": float(np.percentile(harmonic_timings, 95)),
        "harmonic_to_full_ratio": harmonic_median / full_median,
        "additive_delta_ms": harmonic_median - full_median,
    }


__all__ = [
    "HarmonicProfileFixture",
    "HarmonicProfileFixtureEvaluation",
    "RankedProfileMeasurement",
    "benchmark_harmonic_profile_paths",
    "evaluate_harmonic_profile_fixtures",
    "summarize_harmonic_profile_evaluation",
]
