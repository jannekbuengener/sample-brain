"""Golden tests for R&D gesture onset + clustering (#680 / #827).

Synthetic WAVs only. Frozen acceptance for Slice 1 — do not weaken to fit
incorrect clustering or onset behavior.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from src.gesture_analysis import (
    CLUSTER_DISTANCE_THRESHOLD,
    FEATURE_DIM,
    GestureAnalysis,
    analyze_gesture_audio,
)


SR = 44100


def _synth_hit(
    *,
    freq_hz: float,
    duration_sec: float,
    amplitude: float,
    sr: int = SR,
) -> np.ndarray:
    n = max(1, int(sr * duration_sec))
    t = np.linspace(0.0, duration_sec, n, endpoint=False, dtype=np.float32)
    decay = 40.0 if freq_hz < 200.0 else 80.0
    env = np.exp(-t * decay).astype(np.float32)
    return (amplitude * np.sin(2.0 * np.pi * freq_hz * t) * env).astype(np.float32)


def _place_hits(
    hits: list[tuple[float, np.ndarray]],
    *,
    duration_sec: float,
    sr: int = SR,
) -> np.ndarray:
    y = np.zeros(int(sr * duration_sec), dtype=np.float32)
    for t0, hit in hits:
        start = int(t0 * sr)
        end = min(y.size, start + hit.size)
        if start >= y.size or end <= start:
            continue
        y[start:end] += hit[: end - start]
    return np.clip(y, -1.0, 1.0).astype(np.float32)


def _write_wav(path: Path, y: np.ndarray, *, sr: int = SR) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, y, sr, subtype="PCM_16")
    return path


def _assert_event_invariants(result: GestureAnalysis) -> None:
    assert result.feature_dim == FEATURE_DIM
    prev = -1.0
    for event in result.events:
        assert len(event.feature_vector) == FEATURE_DIM
        assert all(np.isfinite(event.feature_vector))
        assert 0.0 <= event.onset_time_sec <= result.duration_sec
        assert event.onset_time_sec > prev
        prev = event.onset_time_sec
        assert isinstance(event.cluster_id, int)
        assert event.cluster_id >= 0


def test_three_identical_impulses_same_cluster(tmp_path: Path) -> None:
    kick = _synth_hit(freq_hz=60.0, duration_sec=0.12, amplitude=0.8)
    y = _place_hits(
        [(0.2, kick), (0.7, kick), (1.2, kick)],
        duration_sec=1.6,
    )
    path = _write_wav(tmp_path / "three_identical.wav", y)

    result = analyze_gesture_audio(path)
    _assert_event_invariants(result)
    assert result.status == "ok"
    assert len(result.events) == 3
    ids = [e.cluster_id for e in result.events]
    assert len(set(ids)) == 1


def test_alternating_gestures_abab_clusters(tmp_path: Path) -> None:
    kick = _synth_hit(freq_hz=60.0, duration_sec=0.12, amplitude=0.8)
    hat = _synth_hit(freq_hz=4000.0, duration_sec=0.05, amplitude=0.55)
    y = _place_hits(
        [(0.2, kick), (0.55, hat), (0.9, kick), (1.25, hat)],
        duration_sec=1.7,
    )
    path = _write_wav(tmp_path / "abab.wav", y)

    result = analyze_gesture_audio(path)
    _assert_event_invariants(result)
    assert result.status == "ok"
    assert len(result.events) == 4
    ids = [e.cluster_id for e in result.events]
    assert ids[0] == ids[2]
    assert ids[1] == ids[3]
    assert ids[0] != ids[1]


def test_silent_file_empty_no_crash(tmp_path: Path) -> None:
    path = _write_wav(tmp_path / "silence.wav", np.zeros(SR, dtype=np.float32))
    result = analyze_gesture_audio(path)
    assert result.status == "empty"
    assert result.events == ()
    assert result.feature_dim == FEATURE_DIM


def test_very_short_clip_fail_soft(tmp_path: Path) -> None:
    # Below _MIN_DURATION_SEC (0.05 s).
    path = _write_wav(
        tmp_path / "short.wav",
        np.zeros(int(0.02 * SR), dtype=np.float32),
    )
    result = analyze_gesture_audio(path)
    assert result.status == "too_short"
    assert result.events == ()


def test_same_wav_twice_identical_assignment(tmp_path: Path) -> None:
    kick = _synth_hit(freq_hz=60.0, duration_sec=0.12, amplitude=0.8)
    hat = _synth_hit(freq_hz=4000.0, duration_sec=0.05, amplitude=0.55)
    y = _place_hits(
        [(0.2, kick), (0.55, hat), (0.9, kick), (1.25, hat)],
        duration_sec=1.7,
    )
    path = _write_wav(tmp_path / "det.wav", y)

    a = analyze_gesture_audio(path)
    b = analyze_gesture_audio(path)
    assert a.status == b.status == "ok"
    assert [e.onset_time_sec for e in a.events] == [e.onset_time_sec for e in b.events]
    assert [e.feature_vector for e in a.events] == [e.feature_vector for e in b.events]
    assert [e.cluster_id for e in a.events] == [e.cluster_id for e in b.events]
    assert a.feature_dim == b.feature_dim == FEATURE_DIM


def test_features_finite_and_onset_monotonic(tmp_path: Path) -> None:
    kick = _synth_hit(freq_hz=60.0, duration_sec=0.12, amplitude=0.8)
    y = _place_hits(
        [(0.15, kick), (0.65, kick), (1.15, kick)],
        duration_sec=1.5,
    )
    path = _write_wav(tmp_path / "mono.wav", y)
    result = analyze_gesture_audio(path)
    assert result.status == "ok"
    assert len(result.events) >= 2
    _assert_event_invariants(result)


def test_mild_amplitude_variation_same_cluster(tmp_path: Path) -> None:
    y = _place_hits(
        [
            (0.2, _synth_hit(freq_hz=60.0, duration_sec=0.12, amplitude=0.8)),
            (0.7, _synth_hit(freq_hz=60.0, duration_sec=0.12, amplitude=0.5)),
            (1.2, _synth_hit(freq_hz=60.0, duration_sec=0.12, amplitude=0.65)),
        ],
        duration_sec=1.6,
    )
    path = _write_wav(tmp_path / "amp.wav", y)
    result = analyze_gesture_audio(path)
    _assert_event_invariants(result)
    assert result.status == "ok"
    assert len(result.events) == 3
    assert len({e.cluster_id for e in result.events}) == 1


def test_clear_spectrum_difference_separable(tmp_path: Path) -> None:
    """Regression for calibrated margin around CLUSTER_DISTANCE_THRESHOLD."""
    assert CLUSTER_DISTANCE_THRESHOLD == 5.0
    kick = _synth_hit(freq_hz=60.0, duration_sec=0.12, amplitude=0.8)
    hat = _synth_hit(freq_hz=4000.0, duration_sec=0.05, amplitude=0.55)
    y = _place_hits(
        [(0.25, kick), (0.7, hat)],
        duration_sec=1.2,
    )
    path = _write_wav(tmp_path / "sep.wav", y)
    result = analyze_gesture_audio(path)
    _assert_event_invariants(result)
    assert result.status == "ok"
    assert len(result.events) == 2
    assert result.events[0].cluster_id != result.events[1].cluster_id


def test_unreadable_path_fail_soft(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.wav"
    result = analyze_gesture_audio(missing)
    assert result.status == "unreadable"
    assert result.events == ()
    assert result.feature_dim == FEATURE_DIM
