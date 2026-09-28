from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from src.joint_key_profile_benchmark import score_audio
from tests.audio_fixtures import (
    write_major_minor_blend_wav,
    write_octave_wav,
    write_root_fifth_wav,
    write_sine_wav,
)


def _write_c_major_bass_fixture(path: Path, *, fifth_bass: bool) -> Path:
    sr = 44100
    duration = 2.0
    t = np.linspace(0.0, duration, int(sr * duration), endpoint=False, dtype=np.float32)
    if fifth_bass:
        bass = 0.65 * np.sin(2.0 * np.pi * 98.00 * t)
        triad_gain = 0.35
    else:
        bass = 0.85 * np.sin(2.0 * np.pi * 65.406 * t)
        triad_gain = 0.30
    triad = triad_gain * sum(
        np.sin(2.0 * np.pi * frequency * t) for frequency in (261.63, 329.63, 392.00)
    )
    sf.write(path, np.clip(bass + triad, -1.0, 1.0).astype(np.float32), sr, subtype="PCM_16")
    return path


def test_raw_profile_prototype_commits_on_all_frozen_ambiguous_418_cases(tmp_path: Path):
    paths = (
        write_sine_wav(tmp_path / "single.wav", duration_sec=2.0, frequency_hz=261.63),
        write_octave_wav(tmp_path / "octave.wav", frequency_hz=261.63),
        write_root_fifth_wav(tmp_path / "root_fifth.wav", frequency_hz=261.63),
        write_major_minor_blend_wav(tmp_path / "blend.wav", frequency_hz=261.63),
    )

    results = [score_audio(path) for path in paths]

    assert all(result.root is not None and result.mode in {"maj", "min"} for result in results)


def test_raw_profile_prototype_preserves_measured_418_bass_outcomes(tmp_path: Path):
    root_bass = score_audio(_write_c_major_bass_fixture(tmp_path / "root_bass.wav", fifth_bass=False))
    fifth_bass = score_audio(_write_c_major_bass_fixture(tmp_path / "fifth_bass.wav", fifth_bass=True))

    assert (root_bass.root, root_bass.mode) == ("C", "maj")
    assert (fifth_bass.root, fifth_bass.mode) == ("G", "maj")
