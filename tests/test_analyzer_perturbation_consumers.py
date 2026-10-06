"""Prove two AQ-shaped consumers reuse the same perturbation mechanics (#957).

These tests intentionally avoid domain thresholds / correctness gates.
They only show that tempo-style and onset/classification-style harnesses
can materialize derived fixtures through the shared contract API.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from src.analyzer_perturbation import materialize_derived_fixture
from tests.audio_fixtures import write_kick_transient_wav, write_pulse_train_wav


def _gain_pad_spec(factor: float = 0.5, pad: int = 2000) -> dict:
    return {
        "contract_id": "sample-brain.analyzer-perturbation.v1",
        "contract_version": "1",
        "transforms": [
            {"id": "gain", "version": "1", "params": {"factor": factor}},
            {
                "id": "pad_silence",
                "version": "1",
                "params": {"leading_samples": pad, "trailing_samples": pad},
            },
        ],
    }


def _aq1_tempo_style_pulse_interval(path: Path) -> float:
    """Minimal tempo-shaped proxy: mean spacing of strong amplitude peaks.

    Uses a refractory window so intra-click ringing does not invent extra
    onsets; this is harness measurement hygiene, not a domain KPI.
    """
    y, sr = sf.read(str(path), dtype="float32", always_2d=False)
    if y.ndim > 1:
        y = np.mean(y, axis=1)
    env = np.abs(y)
    threshold = 0.35 * float(np.max(env))
    candidates = np.where(
        (env[1:-1] > env[:-2]) & (env[1:-1] >= env[2:]) & (env[1:-1] >= threshold)
    )[0]
    min_distance = max(1, int(0.35 * float(sr)))
    peaks: list[int] = []
    for idx in candidates.tolist():
        if not peaks or (idx - peaks[-1]) >= min_distance:
            peaks.append(idx)
    assert len(peaks) >= 2
    intervals = np.diff(np.asarray(peaks, dtype=np.float64)) / float(sr)
    return float(np.mean(intervals))


def _aq3_onset_style_peak_count(path: Path) -> int:
    """Minimal onset/classification-shaped proxy: count of strong local peaks."""
    y, sr = sf.read(str(path), dtype="float32", always_2d=False)
    del sr  # rate unused; presence proves load of derived fixture
    if y.ndim > 1:
        y = np.mean(y, axis=1)
    env = np.abs(y)
    threshold = 0.25 * float(np.max(env))
    peaks = np.where((env[1:-1] > env[:-2]) & (env[1:-1] >= env[2:]) & (env[1:-1] >= threshold))[
        0
    ]
    return int(peaks.size)


def test_aq1_tempo_style_consumer_reuses_perturbation_api(tmp_path: Path) -> None:
    src = write_pulse_train_wav(tmp_path / "pulse.wav", bpm=120.0, duration_sec=2.0)
    derived = tmp_path / "pulse_perturbed.wav"
    provenance = materialize_derived_fixture(src, _gain_pad_spec(), derived)
    assert provenance["derived_identity"]
    assert provenance["source"]["content_hash"]["algorithm"] == "sha256"
    interval = _aq1_tempo_style_pulse_interval(derived)
    # Reuse proof only: a rhythmic signal remains measurable after gain+pad.
    assert 0.4 < interval < 0.6


def test_aq3_onset_style_consumer_reuses_same_perturbation_api(tmp_path: Path) -> None:
    src = write_kick_transient_wav(tmp_path / "kick.wav", bpm=100.0, duration_sec=2.0)
    derived = tmp_path / "kick_perturbed.wav"
    # Second consumer uses a different transform composition but the same API.
    spec = {
        "contract_id": "sample-brain.analyzer-perturbation.v1",
        "contract_version": "1",
        "transforms": [
            {"id": "to_stereo", "version": "1", "params": {"method": "duplicate"}},
            {"id": "resample", "version": "1", "params": {"target_sr": 22050}},
            {"id": "gain", "version": "1", "params": {"factor": 0.75}},
        ],
    }
    provenance = materialize_derived_fixture(src, spec, derived)
    assert provenance["transforms"][0]["id"] == "to_stereo"
    peaks = _aq3_onset_style_peak_count(derived)
    assert peaks >= 2
