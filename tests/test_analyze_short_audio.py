from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from src.analyze import (
    SHORT_AUDIO_QUALITY_NOTE,
    SHORT_AUDIO_WARNING_CODE,
    extract_features,
)
from src.workbench_controller import analyze_folder_for_workbench
from tests.audio_fixtures import write_kick_transient_wav, write_sine_wav


@pytest.fixture(autouse=True)
def _isolated_workbench_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_dir = tmp_path / "workbench_state"
    state_dir.mkdir()
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(state_dir))


def test_short_clip_sets_quality_note_without_user_warnings(tmp_path: Path):
    sample = tmp_path / "short.wav"
    write_sine_wav(sample, duration_sec=0.08, frequency_hz=440.0)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", UserWarning)
        feats = extract_features(sample, 0.08)

    assert feats is not None
    assert feats.quality_note == SHORT_AUDIO_QUALITY_NOTE
    assert feats.bpm is None
    assert feats.key is None
    assert feats.key_conf is None
    assert feats.loudness is not None

    librosa_warns = [
        w
        for w in caught
        if issubclass(w.category, UserWarning)
        and "n_fft=" in str(w.message)
    ]
    assert not librosa_warns


def test_short_clip_workbench_row_keeps_ok_status_with_hint(tmp_path: Path):
    sample = tmp_path / "hit.wav"
    write_sine_wav(sample, duration_sec=0.08, frequency_hz=220.0)

    result = analyze_folder_for_workbench(tmp_path)

    assert result.summary == {
        "files_found": 1,
        "analyzed_count": 1,
        "error_count": 0,
        "cache_hits": 0,
        "cache_misses": 1,
    }
    row = result.rows[0]
    assert row.status == "ok"
    assert row.error is None
    assert row.details["short_audio_warning"] == SHORT_AUDIO_QUALITY_NOTE
    assert row.details["short_audio_warning_code"] == SHORT_AUDIO_WARNING_CODE
    assert row.bpm is None
    assert row.key is None


def test_longer_loop_sample_still_analyzes_normally(tmp_path: Path):
    sample = tmp_path / "loop.wav"
    write_kick_transient_wav(sample, bpm=120.0, duration_sec=2.0)

    feats = extract_features(sample, 2.0)

    assert feats is not None
    assert feats.quality_note is None
    assert feats.bpm is not None
    assert feats.key is not None
    assert feats.loudness is not None

    result = analyze_folder_for_workbench(tmp_path)
    row = result.rows[0]
    assert row.status == "ok"
    assert "short_audio_warning" not in row.details
    assert row.bpm is not None
