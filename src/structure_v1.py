"""Deterministic, neutral, bar-synchronous structure boundary analysis."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Literal, Mapping

import librosa
import numpy as np
import soundfile as sf

from .beat_grid import BeatGridResult
from .canon_audio import AudioTimebase

StructureStatus = Literal["ok", "partial", "no_result", "failed"]
BarGridPolicy = Literal["require_downbeats", "infer_4_4_from_beats"]
STRUCTURE_V1_SOURCE_REF = "structure_v1"


@dataclass(frozen=True)
class StructureV1Config:
    bar_grid_policy: BarGridPolicy = "require_downbeats"
    low_end_hz: float = 150.0
    n_mfcc: int = 8
    fft_size: int = 512
    candidate_percentile: float = 0.80
    min_boundary_distance_bars: int = 2
    min_contributing_groups: int = 2
    trend_windows_bars: tuple[int, ...] = (4, 8, 16)
    disabled_features: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.bar_grid_policy not in {"require_downbeats", "infer_4_4_from_beats"}:
            raise ValueError(f"Unsupported bar grid policy: {self.bar_grid_policy}")
        if self.low_end_hz <= 0 or self.n_mfcc <= 0 or self.fft_size < 16:
            raise ValueError("StructureV1 feature parameters must be positive")
        if not 0 < self.candidate_percentile <= 1:
            raise ValueError("candidate_percentile must be in (0, 1]")
        if self.min_boundary_distance_bars < 1 or self.min_contributing_groups < 1:
            raise ValueError("candidate settings must be positive")
        if not self.trend_windows_bars or any(
            window < 2 for window in self.trend_windows_bars
        ):
            raise ValueError("trend windows must each contain at least two bars")


@dataclass(frozen=True)
class StructureV1Source:
    backend: str
    backend_version: str
    config: Mapping[str, object]

    def as_track_map_component(self) -> dict[str, object]:
        return {
            "component": STRUCTURE_V1_SOURCE_REF,
            "sample_brain_version": _package_version("sample-brain"),
            "backend": {"name": self.backend, "version": self.backend_version},
            "configuration": dict(self.config),
        }


@dataclass(frozen=True)
class StructureBoundary:
    sample_index: int
    time_sec: float
    bar_index: int
    downbeat_index: int
    score: float
    contributing_signals: tuple[str, ...]


@dataclass(frozen=True)
class StructureSection:
    id: str
    start_sample: int
    end_sample: int
    start_sec: float
    end_sec: float
    start_bar: int
    end_bar: int


@dataclass(frozen=True)
class StructureV1Result:
    status: StructureStatus
    boundaries: tuple[StructureBoundary, ...]
    sections: tuple[StructureSection, ...]
    feature_status: Mapping[str, str]
    notes: tuple[str, ...]
    source: StructureV1Source
    reason_code: str | None = None
    bar_features: Mapping[str, tuple[float, ...]] = field(default_factory=dict)

    def to_track_map_sections(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "status": self.status,
            "source_ref": STRUCTURE_V1_SOURCE_REF,
        }
        if self.sections:
            payload["items"] = [
                {
                    "id": section.id,
                    "start_sec": section.start_sec,
                    "end_sec": section.end_sec,
                }
                for section in self.sections
            ]
        if self.reason_code is not None:
            payload["reason_code"] = self.reason_code
        return payload


class StructureV1Analyzer:
    """Compute neutral boundaries without arrangement-role interpretation."""

    def __init__(self, config: StructureV1Config | None = None) -> None:
        self.config = config or StructureV1Config()

    def analyze_path(
        self, audio_path: Path, timebase: AudioTimebase, beat_grid: BeatGridResult
    ) -> StructureV1Result:
        try:
            samples, sample_rate = sf.read(
                str(audio_path), dtype="float32", always_2d=False
            )
            if int(sample_rate) != timebase.sample_rate:
                raise ValueError("audio sample rate does not match AudioTimebase")
            samples = np.asarray(samples, dtype=np.float32)
            if samples.ndim != 1:
                raise ValueError("StructureV1 requires mono canonical working audio")
            return self.analyze(samples, timebase, beat_grid)
        except Exception as exc:
            return self._result(
                "failed", reason_code="AUDIO_LOAD_FAILED", notes=(str(exc),)
            )

    def analyze(
        self,
        samples: np.ndarray,
        timebase: AudioTimebase,
        beat_grid: BeatGridResult,
    ) -> StructureV1Result:
        waveform = np.asarray(samples, dtype=np.float32).reshape(-1)
        if waveform.size != timebase.n_samples:
            return self._result(
                "failed",
                reason_code="TIMEBASE_LENGTH_MISMATCH",
                notes=("sample array length does not match AudioTimebase",),
            )
        if not np.isfinite(waveform).all():
            return self._result(
                "failed",
                reason_code="INVALID_AUDIO",
                notes=("audio contains non-finite values",),
            )

        bar_starts, inferred, grid_error = self._bar_starts(timebase, beat_grid)
        if grid_error is not None:
            return self._result(
                grid_error[0], reason_code=grid_error[1], notes=(grid_error[2],)
            )
        assert bar_starts is not None
        if len(bar_starts) < 3:
            return self._result(
                "no_result",
                reason_code="INSUFFICIENT_BARS",
                notes=("StructureV1 requires at least three bar ranges",),
                inferred=inferred,
            )

        feature_status: dict[str, str] = {}
        notes: list[str] = []
        features = self._bar_features(
            waveform, timebase, bar_starts, feature_status, notes
        )
        usable = {
            name: values for name, values in features.items() if values is not None
        }
        if not usable:
            return self._result(
                "no_result",
                reason_code="FEATURES_UNAVAILABLE",
                notes=tuple(notes),
                feature_status=feature_status,
                inferred=inferred,
            )

        scores, signal_strengths = self._boundary_scores(usable, feature_status)
        candidates = self._candidates(scores, signal_strengths, bar_starts, timebase)
        sections = self._sections(candidates, bar_starts, timebase)
        partial = inferred or any(status != "ok" for status in feature_status.values())
        status: StructureStatus = "partial" if partial else "ok"
        if not candidates:
            status = "partial" if partial else "no_result"
            notes.append(
                "No multi-signal boundary candidate exceeded the track-relative threshold"
            )

        return StructureV1Result(
            status=status,
            boundaries=tuple(candidates),
            sections=tuple(sections),
            feature_status=feature_status,
            notes=tuple(notes),
            source=self._source(inferred=inferred),
            reason_code=None if candidates else "NO_BOUNDARY_CANDIDATE",
            bar_features=self._public_bar_features(usable, signal_strengths),
        )

    def _public_bar_features(
        self, features: Mapping[str, np.ndarray], strengths: Mapping[str, np.ndarray]
    ) -> dict[str, tuple[float, ...]]:
        """Expose normalized bar evidence for role consumers without role labels."""
        result: dict[str, tuple[float, ...]] = {}
        for name, values in features.items():
            array = np.asarray(values, dtype=float)
            if name == "self_similarity" and array.ndim == 2:
                if len(array) < 2:
                    public = np.zeros(len(array))
                else:
                    public = (np.sum(array, axis=1) - np.diag(array)) / (len(array) - 1)
            elif array.ndim > 1:
                public = _deltas(array)
            else:
                public = array
            result[name] = tuple(float(value) for value in _relative_strength(public))
        for name in ("neighbor_delta",):
            if name in strengths:
                result[name] = tuple(float(value) for value in strengths[name])
        if "bar_energy_rms" in features:
            energy = np.asarray(features["bar_energy_rms"], dtype=float)
            trend = np.zeros(len(energy), dtype=float)
            for window in self.config.trend_windows_bars:
                for index in range(window - 1, len(energy)):
                    trend[index] += float(energy[index] - energy[index - window + 1])
            magnitude = float(np.max(np.abs(trend))) if trend.size else 0.0
            result["multi_bar_trend"] = tuple(
                float(value / magnitude) if magnitude > 1e-12 else 0.0
                for value in trend
            )
        return result

    def _bar_starts(
        self, timebase: AudioTimebase, beat_grid: BeatGridResult
    ) -> tuple[list[int] | None, bool, tuple[StructureStatus, str, str] | None]:
        downbeats = beat_grid.downbeats.sample_indices
        if downbeats:
            if not self._valid_positions(downbeats, timebase):
                return (
                    None,
                    False,
                    ("failed", "INVALID_BEAT_GRID", "downbeats are invalid"),
                )
            return list(downbeats), False, None

        if self.config.bar_grid_policy == "require_downbeats":
            return (
                None,
                False,
                ("no_result", "DOWNBEATS_UNAVAILABLE", "no downbeats available"),
            )
        beats = beat_grid.beats.sample_indices
        if not self._valid_positions(beats, timebase):
            return None, False, ("failed", "INVALID_BEAT_GRID", "beats are invalid")
        inferred = list(beats[::4])
        if not inferred:
            return (
                None,
                True,
                (
                    "no_result",
                    "DOWNBEATS_UNAVAILABLE",
                    "no beats available for inference",
                ),
            )
        return inferred, True, None

    @staticmethod
    def _valid_positions(positions: tuple[int, ...], timebase: AudioTimebase) -> bool:
        if not positions:
            return False
        if any(
            position < 0 or position >= timebase.n_samples for position in positions
        ):
            return False
        return all(
            next_position > position
            for position, next_position in zip(positions, positions[1:])
        )

    def _bar_features(
        self,
        waveform: np.ndarray,
        timebase: AudioTimebase,
        starts: list[int],
        feature_status: dict[str, str],
        notes: list[str],
    ) -> dict[str, np.ndarray | None]:
        ends = starts[1:] + [timebase.n_samples]
        bars = [waveform[start:end] for start, end in zip(starts, ends)]
        result: dict[str, np.ndarray | None] = {}
        disabled = set(self.config.disabled_features)

        def compute(name: str, operation) -> None:
            if name in disabled:
                result[name] = None
                feature_status[name] = "not_run"
                notes.append(f"{name} disabled by configuration")
                return
            try:
                result[name] = operation()
                feature_status[name] = "ok"
            except Exception as exc:
                result[name] = None
                feature_status[name] = "failed"
                notes.append(f"{name} unavailable: {exc}")

        compute("bar_energy_rms", lambda: np.asarray([_rms(bar) for bar in bars]))
        compute(
            "low_end_share",
            lambda: np.asarray([self._low_end_share(bar, timebase) for bar in bars]),
        )
        compute(
            "onset_density", lambda: np.asarray([_onset_density(bar) for bar in bars])
        )
        compute("rhythm_stability", lambda: self._rhythm_stability(bars))
        compute("timbre_delta", lambda: self._bar_mfcc(bars, timebase))
        compute("spectral_delta", lambda: self._spectral_descriptors(bars, timebase))

        base_names = (
            "bar_energy_rms",
            "low_end_share",
            "onset_density",
            "rhythm_stability",
            "timbre_delta",
            "spectral_delta",
        )
        base = [result[name] for name in base_names if result.get(name) is not None]
        if "self_similarity" in disabled:
            result["self_similarity"] = None
            feature_status["self_similarity"] = "not_run"
            notes.append("self_similarity disabled by configuration")
        elif not base:
            result["self_similarity"] = None
            feature_status["self_similarity"] = "failed"
            notes.append("self_similarity unavailable without base features")
        else:
            descriptor = _stack_feature_vectors(base)
            result["self_similarity"] = _self_similarity(descriptor)
            feature_status["self_similarity"] = "ok"

        similarity = result.get("self_similarity")
        if "recurrence" in disabled:
            result["recurrence"] = None
            feature_status["recurrence"] = "not_run"
            notes.append("recurrence disabled by configuration")
        elif similarity is None:
            result["recurrence"] = None
            feature_status["recurrence"] = "failed"
            notes.append("recurrence unavailable without self similarity")
        else:
            result["recurrence"] = _recurrence(np.asarray(similarity))
            feature_status["recurrence"] = "ok"

        if "novelty" in disabled:
            result["novelty"] = None
            feature_status["novelty"] = "not_run"
            notes.append("novelty disabled by configuration")
        elif base:
            result["novelty"] = _deltas(_stack_feature_vectors(base))
            feature_status["novelty"] = "ok"
        else:
            result["novelty"] = None
            feature_status["novelty"] = "failed"
            notes.append("novelty unavailable without base features")

        return result

    def _boundary_scores(
        self, features: Mapping[str, np.ndarray], feature_status: Mapping[str, str]
    ) -> tuple[np.ndarray, Mapping[str, np.ndarray]]:
        del feature_status
        n_bars = len(next(iter(features.values())))
        groups: dict[str, np.ndarray] = {}
        for name, values in features.items():
            if name == "self_similarity":
                values = 1.0 - np.diag(values)
            elif values.ndim > 1:
                values = _deltas(values)
            elif name not in {"novelty", "recurrence"}:
                values = _deltas(values.reshape(-1, 1))
            groups[name] = _relative_strength(np.asarray(values, dtype=float))

        base = [
            groups[name]
            for name in groups
            if name not in {"self_similarity", "recurrence"}
        ]
        if base:
            groups["neighbor_delta"] = _relative_strength(
                np.mean(np.vstack(base), axis=0)
            )
            groups["multi_bar_trend"] = _relative_strength(
                self._multi_bar_trend(
                    np.asarray(features.get("bar_energy_rms", np.zeros(n_bars)))
                )
            )
        score = (
            np.mean(np.vstack(list(groups.values())), axis=0)
            if groups
            else np.zeros(n_bars)
        )
        return score, groups

    def _candidates(
        self,
        scores: np.ndarray,
        strengths: Mapping[str, np.ndarray],
        bar_starts: list[int],
        timebase: AudioTimebase,
    ) -> list[StructureBoundary]:
        if len(scores) < 3 or float(np.max(scores)) <= 0:
            return []
        threshold = float(np.percentile(scores, self.config.candidate_percentile * 100))
        candidates: list[StructureBoundary] = []
        for bar_index in range(1, len(scores)):
            score = float(scores[bar_index])
            previous = float(scores[bar_index - 1])
            following = (
                float(scores[bar_index + 1]) if bar_index + 1 < len(scores) else -np.inf
            )
            contributing = tuple(
                name
                for name, values in strengths.items()
                if float(values[bar_index]) >= 0.5
            )
            if score < threshold or score <= 0 or score < previous or score < following:
                continue
            if len(contributing) < self.config.min_contributing_groups:
                continue
            if (
                candidates
                and bar_index - candidates[-1].bar_index
                < self.config.min_boundary_distance_bars
            ):
                continue
            sample_index = bar_starts[bar_index]
            candidates.append(
                StructureBoundary(
                    sample_index=sample_index,
                    time_sec=timebase.samples_to_seconds(sample_index),
                    bar_index=bar_index,
                    downbeat_index=bar_index,
                    score=score,
                    contributing_signals=contributing,
                )
            )
        return candidates

    def _sections(
        self,
        boundaries: list[StructureBoundary],
        bar_starts: list[int],
        timebase: AudioTimebase,
    ) -> list[StructureSection]:
        if not boundaries:
            return []
        points = (
            [0]
            + [boundary.sample_index for boundary in boundaries]
            + [timebase.n_samples]
        )
        bars = [0] + [boundary.bar_index for boundary in boundaries] + [len(bar_starts)]
        return [
            StructureSection(
                id=f"section_{index + 1}",
                start_sample=start,
                end_sample=end,
                start_sec=timebase.samples_to_seconds(start),
                end_sec=timebase.samples_to_seconds(end),
                start_bar=start_bar,
                end_bar=end_bar,
            )
            for index, (start, end, start_bar, end_bar) in enumerate(
                zip(points, points[1:], bars, bars[1:])
            )
        ]

    def _low_end_share(self, bar: np.ndarray, timebase: AudioTimebase) -> float:
        spectrum = np.abs(np.fft.rfft(bar * np.hanning(len(bar)))) ** 2
        frequencies = np.fft.rfftfreq(len(bar), d=1 / timebase.sample_rate)
        total = float(np.sum(spectrum))
        return (
            0.0
            if total <= 1e-12
            else float(np.sum(spectrum[frequencies <= self.config.low_end_hz]) / total)
        )

    def _bar_mfcc(self, bars: list[np.ndarray], timebase: AudioTimebase) -> np.ndarray:
        descriptors = []
        for bar in bars:
            n_fft = min(self.config.fft_size, max(16, len(bar)))
            mfcc = librosa.feature.mfcc(
                y=bar, sr=timebase.sample_rate, n_mfcc=self.config.n_mfcc, n_fft=n_fft
            )
            descriptors.append(np.mean(mfcc, axis=1))
        return np.asarray(descriptors)

    def _spectral_descriptors(
        self, bars: list[np.ndarray], timebase: AudioTimebase
    ) -> np.ndarray:
        descriptors = []
        for bar in bars:
            spectrum = np.abs(np.fft.rfft(bar * np.hanning(len(bar))))
            frequencies = np.fft.rfftfreq(len(bar), d=1 / timebase.sample_rate)
            total = float(np.sum(spectrum))
            centroid = (
                0.0 if total <= 1e-12 else float(np.sum(spectrum * frequencies) / total)
            )
            descriptors.append((centroid, self._low_end_share(bar, timebase)))
        return np.asarray(descriptors)

    def _rhythm_stability(self, bars: list[np.ndarray]) -> np.ndarray:
        patterns = np.asarray([_onset_pattern(bar) for bar in bars])
        stability = np.ones(len(bars), dtype=float)
        for index in range(1, len(bars)):
            stability[index] = _cosine(patterns[index - 1], patterns[index])
        return stability

    def _multi_bar_trend(self, values: np.ndarray) -> np.ndarray:
        trend = np.zeros(len(values), dtype=float)
        for window in self.config.trend_windows_bars:
            for index in range(window - 1, len(values)):
                segment = values[index - window + 1 : index + 1]
                trend[index] += abs(float(segment[-1] - segment[0]))
        return trend

    def _source(self, *, inferred: bool = False) -> StructureV1Source:
        config = asdict(self.config)
        config["timebase"] = "AudioTimebase sample indices"
        config["beat_grid_source_ref"] = "beat_grid"
        if inferred:
            config["bar_grid_inference"] = "beats_grouped_in_fours"
        return StructureV1Source(
            backend="numpy_librosa",
            backend_version=f"numpy-{np.__version__};librosa-{librosa.__version__}",
            config=config,
        )

    def _result(
        self,
        status: StructureStatus,
        *,
        reason_code: str,
        notes: tuple[str, ...],
        feature_status: Mapping[str, str] | None = None,
        inferred: bool = False,
    ) -> StructureV1Result:
        return StructureV1Result(
            status=status,
            boundaries=(),
            sections=(),
            feature_status=dict(feature_status or {}),
            notes=notes,
            source=self._source(inferred=inferred),
            reason_code=reason_code,
        )


def _package_version(distribution: str) -> str:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return "unknown"


def _rms(values: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(values, dtype=float))))


def _onset_pattern(values: np.ndarray, bins: int = 8) -> np.ndarray:
    differences = np.abs(np.diff(values, prepend=values[:1]))
    threshold = max(float(np.max(differences)) * 0.2, 1e-6)
    onsets = differences >= threshold
    parts = np.array_split(onsets.astype(float), bins)
    return np.asarray([float(np.sum(part)) for part in parts])


def _onset_density(values: np.ndarray) -> float:
    return float(np.sum(_onset_pattern(values))) / max(1, len(values))


def _cosine(left: np.ndarray, right: np.ndarray) -> float:
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    return 1.0 if denominator <= 1e-12 else float(np.dot(left, right) / denominator)


def _stack_feature_vectors(features: list[np.ndarray | None]) -> np.ndarray:
    vectors = [
        feature.reshape(len(feature), -1) for feature in features if feature is not None
    ]
    return np.hstack([_normalize_columns(vector) for vector in vectors])


def _normalize_columns(values: np.ndarray) -> np.ndarray:
    median = np.median(values, axis=0)
    mad = np.median(np.abs(values - median), axis=0)
    scale = np.where(mad > 1e-9, mad, 1.0)
    normalized = (values - median) / scale
    normalized[:, mad <= 1e-9] = 0.0
    return normalized


def _self_similarity(descriptor: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(descriptor, axis=1, keepdims=True)
    normalized = np.divide(
        descriptor, norms, out=np.zeros_like(descriptor), where=norms > 1e-12
    )
    return normalized @ normalized.T


def _recurrence(similarity: np.ndarray) -> np.ndarray:
    result = np.zeros(similarity.shape[0], dtype=float)
    for index in range(len(result)):
        values = similarity[index].copy()
        values[max(0, index - 1) : min(len(result), index + 2)] = -np.inf
        finite = values[np.isfinite(values)]
        result[index] = float(np.max(finite)) if finite.size else 0.0
    return result


def _deltas(values: np.ndarray) -> np.ndarray:
    vectors = values.reshape(len(values), -1)
    output = np.zeros(len(vectors), dtype=float)
    if len(vectors) > 1:
        output[1:] = np.linalg.norm(vectors[1:] - vectors[:-1], axis=1)
    return output


def _relative_strength(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float).reshape(-1)
    if not np.isfinite(values).all():
        return np.zeros_like(values)
    minimum = float(np.min(values))
    maximum = float(np.max(values))
    if maximum - minimum <= 1e-12:
        return np.zeros_like(values)
    return (values - minimum) / (maximum - minimum)


__all__ = [
    "STRUCTURE_V1_SOURCE_REF",
    "BarGridPolicy",
    "StructureBoundary",
    "StructureSection",
    "StructureStatus",
    "StructureV1Analyzer",
    "StructureV1Config",
    "StructureV1Result",
    "StructureV1Source",
]
