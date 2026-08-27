from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

import numpy as np

from .canon_audio import AudioTimebase

BeatStatus = Literal["ok", "partial", "not_run", "failed", "no_result"]
BeatBackend = Literal["auto", "beat_this", "librosa"]
BEAT_GRID_SOURCE_REF = "beat_grid"


class BeatGridBackendUnavailable(RuntimeError):
    """Raised when an optional beat backend cannot be loaded."""


@dataclass(frozen=True)
class BeatGridError:
    code: str
    message: str
    retryable: bool = True

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }


@dataclass(frozen=True)
class BeatGridSeries:
    status: BeatStatus
    sample_indices: tuple[int, ...] = ()
    times_sec: tuple[float, ...] = ()
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if len(self.sample_indices) != len(self.times_sec):
            raise ValueError("sample_indices and times_sec must have equal length")
        if any(sample_index < 0 for sample_index in self.sample_indices):
            raise ValueError("sample_indices must be non-negative")
        if any(
            not np.isfinite(time_sec) or time_sec < 0 for time_sec in self.times_sec
        ):
            raise ValueError("times_sec must contain finite non-negative values")

    def as_dict(self, *, source_ref: str = BEAT_GRID_SOURCE_REF) -> dict[str, object]:
        payload: dict[str, object] = {"status": self.status}
        if self.times_sec:
            payload["times_sec"] = list(self.times_sec)
            payload["sample_indices"] = list(self.sample_indices)
        if self.reason_code is not None:
            payload["reason_code"] = self.reason_code
        if self.status in {"ok", "partial"} or self.times_sec:
            payload["source_ref"] = source_ref
        return payload

    def to_track_map_block(
        self, *, source_ref: str = BEAT_GRID_SOURCE_REF
    ) -> dict[str, object]:
        payload: dict[str, object] = {"status": self.status}
        if self.times_sec:
            payload["times_sec"] = list(self.times_sec)
            payload["source_ref"] = source_ref
        if self.reason_code is not None:
            payload["reason_code"] = self.reason_code
        return payload


@dataclass(frozen=True)
class BeatGridSource:
    component: str
    backend: str
    backend_version: str
    checkpoint: str | None
    config: Mapping[str, object] = field(default_factory=dict)
    fallback_from: str | None = None
    fallback_reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "component": self.component,
            "backend": {
                "name": self.backend,
                "version": self.backend_version,
            },
            "config": dict(self.config),
        }
        if self.checkpoint is not None:
            payload["backend"]["checkpoint"] = self.checkpoint
        if self.fallback_from is not None:
            payload["fallback_from"] = self.fallback_from
        if self.fallback_reason is not None:
            payload["fallback_reason"] = self.fallback_reason
        return payload


@dataclass(frozen=True)
class BeatGridResult:
    status: BeatStatus
    bpm: float | None
    beats: BeatGridSeries
    downbeats: BeatGridSeries
    source: BeatGridSource
    error: BeatGridError | None = None

    def as_dict(self) -> dict[str, object]:
        bpm_payload: dict[str, object] = {"status": "no_result"}
        if self.bpm is not None:
            bpm_payload = {
                "status": "ok",
                "value": self.bpm,
                "source_ref": BEAT_GRID_SOURCE_REF,
            }
        payload: dict[str, object] = {
            "status": self.status,
            "bpm": bpm_payload,
            "beats": self.beats.as_dict(),
            "downbeats": self.downbeats.as_dict(),
            "source": self.source.as_dict(),
        }
        if self.error is not None:
            payload["error"] = self.error.as_dict()
        return payload

    def to_track_map_timeline(self) -> dict[str, object]:
        bpm_payload: dict[str, object] = {"status": "no_result"}
        if self.bpm is not None:
            bpm_payload = {
                "status": "ok",
                "value": self.bpm,
                "source_ref": BEAT_GRID_SOURCE_REF,
            }
        return {
            "bpm": bpm_payload,
            "beats": self.beats.to_track_map_block(),
            "downbeats": self.downbeats.to_track_map_block(),
        }


@dataclass(frozen=True)
class _RawBeatGrid:
    bpm: float | None
    beats_sec: Sequence[float]
    downbeats_sec: Sequence[float]


def _package_version(distribution: str) -> str:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return "unknown"


def _as_numpy(values: Any) -> np.ndarray:
    detached = getattr(values, "detach", None)
    if callable(detached):
        values = detached()
    on_cpu = getattr(values, "cpu", None)
    if callable(on_cpu):
        values = on_cpu()
    as_array = getattr(values, "numpy", None)
    if callable(as_array):
        values = as_array()
    return np.asarray(values, dtype=float)


def _as_seconds(values: Any) -> tuple[float, ...]:
    if values is None:
        return ()
    values_array = _as_numpy(values).reshape(-1)
    if values_array.size == 0:
        return ()
    if not np.isfinite(values_array).all() or (values_array < 0).any():
        raise ValueError("backend returned invalid beat positions")
    if values_array.size > 1 and (np.diff(values_array) < 0).any():
        raise ValueError("backend returned unsorted beat positions")
    return tuple(float(value) for value in values_array)


def _as_bpm(value: Any) -> float | None:
    if value is None:
        return None
    values = _as_numpy(value).reshape(-1)
    if values.size == 0:
        return None
    bpm = float(values[0])
    return bpm if np.isfinite(bpm) and bpm > 0 else None


def _derive_bpm(beat_times_sec: tuple[float, ...]) -> float | None:
    if len(beat_times_sec) < 2:
        return None
    intervals = np.diff(np.asarray(beat_times_sec, dtype=float))
    positive_intervals = intervals[intervals > 0]
    if positive_intervals.size == 0:
        return None
    bpm = 60.0 / float(np.median(positive_intervals))
    return bpm if np.isfinite(bpm) and bpm > 0 else None


def _beat_this_worker_launch(
    audio_path: Path,
    *,
    checkpoint: str,
    device: str,
) -> tuple[list[str], dict[str, str] | None]:
    """Build the isolated worker command without inheriting CLI argv.

    On Windows venvs, ``sys.executable`` is a launcher stub that re-executes the
    base interpreter. Launch the worker with ``sys._base_executable`` and set
    ``__PYVENV_LAUNCHER__`` so the child stays in the venv while the command
    remains exclusively ``-m src.beat_this_worker`` (never ``src.cli deconstruct``).
    """
    module_args = [
        "-m",
        "src.beat_this_worker",
        "--input",
        str(audio_path),
        "--checkpoint",
        checkpoint,
        "--device",
        device,
    ]
    base_executable = getattr(sys, "_base_executable", None)
    if (
        sys.platform == "win32"
        and isinstance(base_executable, str)
        and base_executable
        and os.path.normcase(base_executable) != os.path.normcase(sys.executable)
    ):
        env = os.environ.copy()
        env["__PYVENV_LAUNCHER__"] = sys.executable
        return [base_executable, *module_args], env
    return [sys.executable, *module_args], None


def _run_beat_this_backend(
    audio_path: Path,
    *,
    checkpoint: str,
    device: str,
    config: Mapping[str, object],
) -> _RawBeatGrid:
    del config
    command, env = _beat_this_worker_launch(
        audio_path,
        checkpoint=checkpoint,
        device=device,
    )
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise BeatGridBackendUnavailable("beat_this worker timed out") from exc
    except OSError as exc:
        raise BeatGridBackendUnavailable("beat_this worker could not start") from exc

    if completed.returncode != 0:
        raise BeatGridBackendUnavailable("beat_this worker failed")
    try:
        payload = _parse_beat_this_worker_output(completed.stdout)
    except ValueError as exc:
        raise BeatGridBackendUnavailable("beat_this worker returned invalid output") from exc
    if payload.get("status") != "ok":
        raise BeatGridBackendUnavailable(
            f"beat_this worker failed: {payload.get('code', 'UNKNOWN')}"
        )

    beats_sec = payload.get("beats_sec")
    downbeats_sec = payload.get("downbeats_sec")
    return _RawBeatGrid(
        bpm=None,
        beats_sec=_as_seconds(beats_sec),
        downbeats_sec=_as_seconds(downbeats_sec),
    )


def _parse_beat_this_worker_output(stdout: str) -> dict[str, object]:
    """Read the dedicated worker's final protocol record, ignoring worker logs."""
    marker = "SAMPLE_BRAIN_BEAT_THIS_RESULT="
    for line in reversed(stdout.splitlines()):
        if line.startswith(marker):
            payload = json.loads(line[len(marker) :])
            if isinstance(payload, dict):
                return payload
            break
    payload = json.loads(stdout)
    if not isinstance(payload, dict):
        raise ValueError("worker payload must be an object")
    return payload


def _run_librosa_backend(
    audio_path: Path,
    *,
    timebase: AudioTimebase,
    config: Mapping[str, object],
) -> _RawBeatGrid:
    del config
    import librosa

    audio, loaded_sample_rate = librosa.load(
        str(audio_path), sr=timebase.sample_rate, mono=True
    )
    if int(loaded_sample_rate) != timebase.sample_rate:
        raise ValueError("librosa fallback returned a mismatched sample rate")
    tempo, beat_frames = librosa.beat.beat_track(y=audio, sr=timebase.sample_rate)
    beat_times_sec = librosa.frames_to_time(beat_frames, sr=timebase.sample_rate)
    return _RawBeatGrid(
        bpm=_as_bpm(tempo),
        beats_sec=_as_seconds(beat_times_sec),
        downbeats_sec=(),
    )


def _map_series(
    positions_sec: Any,
    *,
    timebase: AudioTimebase,
    empty_reason: str,
) -> BeatGridSeries:
    times_sec = _as_seconds(positions_sec)
    if not times_sec:
        return BeatGridSeries(status="no_result", reason_code=empty_reason)

    sample_indices: list[int] = []
    for time_sec in times_sec:
        if time_sec > timebase.duration_seconds + 1e-9:
            raise ValueError("backend returned a position outside the audio timebase")
        sample_index = timebase.seconds_to_samples(time_sec)
        if sample_index >= timebase.n_samples:
            raise ValueError("backend returned an endpoint outside the audio range")
        sample_indices.append(sample_index)

    return BeatGridSeries(
        status="ok",
        sample_indices=tuple(sample_indices),
        times_sec=times_sec,
    )


def _result_from_raw(
    raw: _RawBeatGrid,
    *,
    timebase: AudioTimebase,
    source: BeatGridSource,
) -> BeatGridResult:
    beats = _map_series(
        raw.beats_sec,
        timebase=timebase,
        empty_reason="BEATS_UNAVAILABLE",
    )
    downbeats = _map_series(
        raw.downbeats_sec,
        timebase=timebase,
        empty_reason="DOWNBEATS_UNAVAILABLE",
    )
    bpm = _as_bpm(raw.bpm) or _derive_bpm(beats.times_sec)

    if beats.status == "ok" and downbeats.status == "ok":
        status: BeatStatus = "ok"
    elif beats.status == "ok" or downbeats.status == "ok" or bpm is not None:
        status = "partial"
    else:
        status = "no_result"

    return BeatGridResult(
        status=status,
        bpm=bpm,
        beats=beats,
        downbeats=downbeats,
        source=source,
    )


class BeatGridAdapter:
    """Run the provisional BeatGrid primary and its evidence-based fallback."""

    def __init__(
        self,
        *,
        backend: BeatBackend = "auto",
        checkpoint: str = "final0",
        device: str = "cpu",
        config: Mapping[str, object] | None = None,
    ) -> None:
        if backend not in {"auto", "beat_this", "librosa"}:
            raise ValueError(f"Unsupported BeatGrid backend: {backend}")
        self.backend = backend
        self.checkpoint = checkpoint
        self.device = device
        self.config = dict(config or {})

    def _source(
        self,
        backend: str,
        *,
        fallback_from: str | None = None,
        fallback_reason: str | None = None,
    ) -> BeatGridSource:
        source_config: dict[str, object] = {
            "backend_requested": self.backend,
            "device": self.device,
            "dbn": False,
            "fallback_policy": (
                "beat_this_then_librosa" if self.backend == "auto" else "disabled"
            ),
        }
        source_config.update(self.config)
        return BeatGridSource(
            component=BEAT_GRID_SOURCE_REF,
            backend=backend,
            backend_version=_package_version(
                "beat-this" if backend == "beat_this" else "librosa"
            ),
            checkpoint=self.checkpoint if backend == "beat_this" else None,
            config=source_config,
            fallback_from=fallback_from,
            fallback_reason=fallback_reason,
        )

    @staticmethod
    def _failed(
        source: BeatGridSource,
        *,
        code: str,
        message: str,
        retryable: bool = True,
    ) -> BeatGridResult:
        failed_beats = BeatGridSeries(status="failed", reason_code=code)
        failed_downbeats = BeatGridSeries(status="failed", reason_code=code)
        return BeatGridResult(
            status="failed",
            bpm=None,
            beats=failed_beats,
            downbeats=failed_downbeats,
            source=source,
            error=BeatGridError(code=code, message=message, retryable=retryable),
        )

    def _run_fallback(
        self,
        audio_path: Path,
        timebase: AudioTimebase,
        *,
        fallback_from: str | None = None,
        fallback_reason: str | None = None,
    ) -> BeatGridResult:
        source = self._source(
            "librosa",
            fallback_from=fallback_from,
            fallback_reason=fallback_reason,
        )
        try:
            raw = _run_librosa_backend(
                audio_path,
                timebase=timebase,
                config=source.config,
            )
            return _result_from_raw(raw, timebase=timebase, source=source)
        except Exception as exc:
            return self._failed(
                source,
                code="FALLBACK_BACKEND_FAILED",
                message=str(exc),
            )

    def analyze(self, audio_path: Path, timebase: AudioTimebase) -> BeatGridResult:
        audio_path = Path(audio_path)
        if not audio_path.exists():
            return self._failed(
                self._source("beat_this" if self.backend == "auto" else self.backend),
                code="AUDIO_NOT_FOUND",
                message=f"Audio path does not exist: {audio_path}",
                retryable=False,
            )
        if timebase.n_samples == 0:
            return self._failed(
                self._source("beat_this" if self.backend == "auto" else self.backend),
                code="EMPTY_AUDIO",
                message="BeatGrid requires a non-empty audio timebase",
                retryable=False,
            )

        if self.backend == "librosa":
            return self._run_fallback(audio_path, timebase)

        primary_source = self._source("beat_this")
        try:
            raw = _run_beat_this_backend(
                audio_path,
                checkpoint=self.checkpoint,
                device=self.device,
                config=primary_source.config,
            )
            if not raw.beats_sec:
                raise BeatGridBackendUnavailable("beat_this returned no beat positions")
            return _result_from_raw(raw, timebase=timebase, source=primary_source)
        except BeatGridBackendUnavailable as exc:
            reason = (
                "PRIMARY_BACKEND_NO_RESULT"
                if "no beat positions" in str(exc)
                else "PRIMARY_BACKEND_UNAVAILABLE"
            )
            if self.backend == "beat_this":
                return self._failed(
                    primary_source,
                    code=reason,
                    message=str(exc),
                )
            return self._run_fallback(
                audio_path,
                timebase,
                fallback_from="beat_this",
                fallback_reason=reason,
            )
        except Exception as exc:
            if self.backend == "beat_this":
                return self._failed(
                    primary_source,
                    code="PRIMARY_BACKEND_FAILED",
                    message=str(exc),
                )
            return self._run_fallback(
                audio_path,
                timebase,
                fallback_from="beat_this",
                fallback_reason="PRIMARY_BACKEND_FAILED",
            )


__all__ = [
    "BEAT_GRID_SOURCE_REF",
    "BeatBackend",
    "BeatGridAdapter",
    "BeatGridBackendUnavailable",
    "BeatGridError",
    "BeatGridResult",
    "BeatGridSeries",
    "BeatGridSource",
]
