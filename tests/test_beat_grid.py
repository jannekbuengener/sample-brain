from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from pathlib import Path

import numpy as np
import pytest

from src.canon_audio import AudioTimebase
from src.beat_grid import (
    BeatGridAdapter,
    BeatGridBackendUnavailable,
)


def _timebase() -> AudioTimebase:
    return AudioTimebase(sample_rate=10, n_samples=20)


def _audio_path(tmp_path: Path) -> Path:
    path = tmp_path / "working.wav"
    path.write_bytes(b"test audio placeholder")
    return path


def test_beat_this_primary_maps_positions_to_sample_grid(
    tmp_path: Path, monkeypatch
) -> None:
    inference = ModuleType("beat_this.inference")

    class FakeFile2Beats:
        def __init__(self, *, checkpoint_path: str, device: str, dbn: bool) -> None:
            assert checkpoint_path == "final0"
            assert device == "cpu"
            assert dbn is False

        def __call__(self, path: str):
            assert path.endswith("working.wav")
            return np.array([0.1, 0.6, 1.1]), np.array([0.1])

    inference.File2Beats = FakeFile2Beats
    package = ModuleType("beat_this")
    package.inference = inference
    monkeypatch.setitem(sys.modules, "beat_this", package)
    monkeypatch.setitem(sys.modules, "beat_this.inference", inference)

    result = BeatGridAdapter(backend="beat_this").analyze(
        _audio_path(tmp_path), _timebase()
    )

    assert result.status == "ok"
    assert result.bpm == pytest.approx(120.0)
    assert result.beats.sample_indices == (1, 6, 11)
    assert result.downbeats.sample_indices == (1,)
    assert result.source.backend == "beat_this"
    assert result.source.checkpoint == "final0"
    assert result.source.config["backend_requested"] == "beat_this"
    assert result.to_track_map_timeline()["beats"]["times_sec"] == [0.1, 0.6, 1.1]


def test_auto_backend_falls_back_once_with_reason(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []

    def primary(*args, **kwargs):
        calls.append("beat_this")
        raise BeatGridBackendUnavailable("beat_this is not installed")

    def fallback(*args, **kwargs):
        calls.append("librosa")
        return SimpleNamespace(
            bpm=128.0,
            beats_sec=(0.0, 0.46875, 0.9375),
            downbeats_sec=(),
        )

    monkeypatch.setattr("src.beat_grid._run_beat_this_backend", primary)
    monkeypatch.setattr("src.beat_grid._run_librosa_backend", fallback)

    result = BeatGridAdapter(backend="auto").analyze(_audio_path(tmp_path), _timebase())

    assert calls == ["beat_this", "librosa"]
    assert result.status == "partial"
    assert result.source.backend == "librosa"
    assert result.source.fallback_from == "beat_this"
    assert result.source.fallback_reason == "PRIMARY_BACKEND_UNAVAILABLE"
    assert result.downbeats.status == "no_result"
    assert result.downbeats.reason_code == "DOWNBEATS_UNAVAILABLE"
    assert result.error is None


def test_primary_empty_result_triggers_evidence_based_fallback(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[str] = []

    def primary(*args, **kwargs):
        calls.append("beat_this")
        return SimpleNamespace(bpm=None, beats_sec=(), downbeats_sec=())

    def fallback(*args, **kwargs):
        calls.append("librosa")
        return SimpleNamespace(bpm=100.0, beats_sec=(0.0, 0.6), downbeats_sec=())

    monkeypatch.setattr("src.beat_grid._run_beat_this_backend", primary)
    monkeypatch.setattr("src.beat_grid._run_librosa_backend", fallback)

    result = BeatGridAdapter(backend="auto").analyze(_audio_path(tmp_path), _timebase())

    assert calls == ["beat_this", "librosa"]
    assert result.source.fallback_reason == "PRIMARY_BACKEND_NO_RESULT"
    assert result.beats.sample_indices == (0, 6)


def test_strict_primary_failure_is_reported_without_fallback(
    tmp_path: Path, monkeypatch
) -> None:
    def primary(*args, **kwargs):
        raise RuntimeError("model execution failed")

    def fallback(*args, **kwargs):
        raise AssertionError("strict primary mode must not run fallback")

    monkeypatch.setattr("src.beat_grid._run_beat_this_backend", primary)
    monkeypatch.setattr("src.beat_grid._run_librosa_backend", fallback)

    result = BeatGridAdapter(backend="beat_this").analyze(
        _audio_path(tmp_path), _timebase()
    )

    assert result.status == "failed"
    assert result.source.backend == "beat_this"
    assert result.error is not None
    assert result.error.code == "PRIMARY_BACKEND_FAILED"


def test_invalid_backend_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported BeatGrid backend"):
        BeatGridAdapter(backend="unknown")
