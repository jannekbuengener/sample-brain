from __future__ import annotations

import numpy as np

from src.beat_grid import BeatGridResult, BeatGridSeries, BeatGridSource
from src.canon_audio import AudioTimebase
from src.structure_v1 import StructureV1Analyzer, StructureV1Config

SAMPLE_RATE = 1000
BAR_SAMPLES = 1000


def _timebase(n_bars: int = 8) -> AudioTimebase:
    return AudioTimebase(sample_rate=SAMPLE_RATE, n_samples=n_bars * BAR_SAMPLES)


def _source() -> BeatGridSource:
    return BeatGridSource(
        component="beat_grid",
        backend="synthetic",
        backend_version="1",
        checkpoint=None,
    )


def _grid(
    timebase: AudioTimebase,
    *,
    downbeats: tuple[int, ...] | None = None,
    beats: tuple[int, ...] | None = None,
    status: str = "ok",
) -> BeatGridResult:
    downbeats = (
        downbeats
        if downbeats is not None
        else tuple(range(0, timebase.n_samples, BAR_SAMPLES))
    )
    beats = (
        beats
        if beats is not None
        else tuple(range(0, timebase.n_samples, BAR_SAMPLES // 4))
    )
    return BeatGridResult(
        status=status,  # type: ignore[arg-type]
        bpm=60.0,
        beats=BeatGridSeries(
            status="ok",
            sample_indices=beats,
            times_sec=tuple(sample / SAMPLE_RATE for sample in beats),
        ),
        downbeats=BeatGridSeries(
            status="ok" if downbeats else "no_result",
            sample_indices=downbeats,
            times_sec=tuple(sample / SAMPLE_RATE for sample in downbeats),
            reason_code=None if downbeats else "DOWNBEATS_UNAVAILABLE",
        ),
        source=_source(),
    )


def _analyzer(**overrides: object) -> StructureV1Analyzer:
    return StructureV1Analyzer(
        StructureV1Config(
            candidate_percentile=0.70,
            min_contributing_groups=2,
            min_boundary_distance_bars=1,
            **overrides,
        )
    )


def _sine(freq: float, samples: int) -> np.ndarray:
    positions = np.arange(samples, dtype=np.float32) / SAMPLE_RATE
    return np.sin(2 * np.pi * freq * positions).astype(np.float32)


def _boundary_samples(result) -> set[int]:
    return {boundary.sample_index for boundary in result.boundaries}


def test_constant_signal_has_no_invented_internal_boundaries() -> None:
    timebase = _timebase()
    samples = np.full(timebase.n_samples, 0.2, dtype=np.float32)

    result = _analyzer().analyze(samples, timebase, _grid(timebase))

    assert result.status in {"ok", "no_result"}
    assert not result.boundaries


def test_energy_step_detects_boundary_on_downbeat_sample() -> None:
    timebase = _timebase()
    samples = np.concatenate(
        [_sine(110, 4 * BAR_SAMPLES) * 0.08, _sine(110, 4 * BAR_SAMPLES) * 0.8]
    )

    result = _analyzer().analyze(samples, timebase, _grid(timebase))

    assert 4 * BAR_SAMPLES in _boundary_samples(result)
    assert all(
        boundary.sample_index % BAR_SAMPLES == 0 for boundary in result.boundaries
    )


def test_low_end_and_spectral_change_produces_boundary_candidate() -> None:
    timebase = _timebase()
    samples = np.concatenate(
        [_sine(300, 4 * BAR_SAMPLES) * 0.4, _sine(55, 4 * BAR_SAMPLES) * 0.4]
    )

    result = _analyzer().analyze(samples, timebase, _grid(timebase))

    assert 4 * BAR_SAMPLES in _boundary_samples(result)


def test_onset_and_rhythm_change_contributes_to_novelty() -> None:
    timebase = _timebase()
    samples = np.zeros(timebase.n_samples, dtype=np.float32)
    for offset in range(0, 4 * BAR_SAMPLES, 500):
        samples[offset : offset + 20] = 0.7
    for offset in range(4 * BAR_SAMPLES, timebase.n_samples, 125):
        samples[offset : offset + 10] = 0.7

    result = _analyzer().analyze(samples, timebase, _grid(timebase))

    assert result.feature_status["onset_density"] == "ok"
    assert result.feature_status["novelty"] == "ok"
    assert 4 * BAR_SAMPLES in _boundary_samples(result)


def test_result_is_deterministic_and_seconds_are_derived_from_timebase() -> None:
    timebase = _timebase()
    samples = np.concatenate(
        [_sine(220, 4 * BAR_SAMPLES) * 0.1, _sine(70, 4 * BAR_SAMPLES) * 0.7]
    )
    analyzer = _analyzer()

    first = analyzer.analyze(samples, timebase, _grid(timebase))
    second = analyzer.analyze(samples, timebase, _grid(timebase))

    assert first == second
    assert all(
        boundary.time_sec == timebase.samples_to_seconds(boundary.sample_index)
        for boundary in first.boundaries
    )


def test_short_track_returns_no_result_without_false_boundary() -> None:
    timebase = _timebase(n_bars=1)
    result = _analyzer().analyze(np.ones(timebase.n_samples), timebase, _grid(timebase))

    assert result.status == "no_result"
    assert result.reason_code == "INSUFFICIENT_BARS"
    assert not result.boundaries


def test_missing_downbeats_fail_closed_by_default() -> None:
    timebase = _timebase()
    grid = _grid(timebase, downbeats=(), status="partial")

    result = _analyzer().analyze(np.ones(timebase.n_samples), timebase, grid)

    assert result.status == "no_result"
    assert result.reason_code == "DOWNBEATS_UNAVAILABLE"
    assert not result.boundaries


def test_explicit_four_four_inference_uses_beats_and_marks_partial() -> None:
    timebase = _timebase()
    grid = _grid(timebase, downbeats=(), status="partial")
    samples = np.concatenate(
        [_sine(220, 4 * BAR_SAMPLES) * 0.1, _sine(70, 4 * BAR_SAMPLES) * 0.7]
    )

    result = _analyzer(bar_grid_policy="infer_4_4_from_beats").analyze(
        samples, timebase, grid
    )

    assert result.status == "partial"
    assert result.source.config["bar_grid_policy"] == "infer_4_4_from_beats"
    assert result.source.config["bar_grid_inference"] == "beats_grouped_in_fours"


def test_invalid_beat_grid_fails_closed() -> None:
    timebase = _timebase()
    grid = _grid(timebase, downbeats=(0, 3000, 2000, 5000))

    result = _analyzer().analyze(np.ones(timebase.n_samples), timebase, grid)

    assert result.status == "failed"
    assert result.reason_code == "INVALID_BEAT_GRID"
    assert not result.boundaries


def test_disabled_optional_feature_is_explicit_partial_path() -> None:
    timebase = _timebase()
    samples = np.concatenate(
        [_sine(220, 4 * BAR_SAMPLES) * 0.1, _sine(70, 4 * BAR_SAMPLES) * 0.7]
    )

    result = _analyzer(disabled_features=("recurrence",)).analyze(
        samples, timebase, _grid(timebase)
    )

    assert result.status == "partial"
    assert result.feature_status["recurrence"] == "not_run"
    assert "recurrence" in result.notes[0]


def test_track_relative_normalization_handles_amplitude_scaling() -> None:
    timebase = _timebase()
    shape = np.concatenate(
        [_sine(110, 4 * BAR_SAMPLES) * 0.1, _sine(110, 4 * BAR_SAMPLES)]
    )

    quiet = _analyzer().analyze(shape * 0.1, timebase, _grid(timebase))
    loud = _analyzer().analyze(shape * 0.8, timebase, _grid(timebase))

    assert _boundary_samples(quiet) == _boundary_samples(loud)


def test_track_map_export_is_neutral_and_has_status_config_and_provenance() -> None:
    timebase = _timebase()
    samples = np.concatenate(
        [_sine(110, 4 * BAR_SAMPLES) * 0.1, _sine(110, 4 * BAR_SAMPLES) * 0.8]
    )

    result = _analyzer().analyze(samples, timebase, _grid(timebase))
    sections = result.to_track_map_sections()
    provenance = result.source.as_track_map_component()

    assert sections["status"] == result.status
    assert sections["source_ref"] == "structure_v1"
    assert all(
        set(item) == {"id", "start_sec", "end_sec"} for item in sections["items"]
    )
    assert provenance["component"] == "structure_v1"
    assert provenance["configuration"]
    forbidden = {
        "intro",
        "groove",
        "build",
        "drop",
        "breakdown",
        "outro",
        "unknown",
        "transition",
        "drop_onset",
    }
    assert not forbidden & set().union(*(set(item) for item in sections["items"]))
