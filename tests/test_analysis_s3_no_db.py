from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf


def _write_tone(path: Path, *, sr: int = 44100, duration: float = 0.25) -> None:
    frames = max(1, int(sr * duration))
    t = np.arange(frames, dtype=np.float32) / float(sr)
    y = (0.1 * np.sin(2.0 * np.pi * 220.0 * t)).astype(np.float32)
    sf.write(path, y, sr, subtype="PCM_16")


def test_neutral_feature_analysis_does_not_create_catalog_db(tmp_path: Path, monkeypatch) -> None:
    catalog = tmp_path / "catalog.db"
    monkeypatch.setenv("SAMPLE_BRAIN_DB_PATH", str(catalog))
    audio = tmp_path / "tone.wav"
    _write_tone(audio)

    from src.feature_analysis import extract_features

    result = extract_features(audio, duration=0.25)

    assert result is not None
    assert not catalog.exists()