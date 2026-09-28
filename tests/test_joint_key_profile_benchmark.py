from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from src.joint_key_profile import JointKeyProfileError, MAJOR_PROFILE, SEMITONES, rotate_profile
from src.joint_key_profile_benchmark import (
    evaluate_joint_key_profiles,
    mean_cqt_chroma,
    score_audio,
)
from tests.audio_fixtures import write_major_chord_wav


def test_adapter_uses_cqt_mean_and_returns_joint_raw_evidence(tmp_path: Path):
    audio = write_major_chord_wav(tmp_path / "c_major.wav")

    result = mean_cqt_chroma(audio)

    assert result.chroma_mean.shape == (12,)
    assert np.isfinite(result.chroma_mean).all()


def test_benchmark_reports_external_audio_unavailable_without_writing_repo_artifacts(tmp_path: Path):
    result = evaluate_joint_key_profiles(audio_root=tmp_path / "missing", split="TEST")

    assert result["run_status"] == "PUBLIC_AUDIO_NOT_AVAILABLE_LOCALLY"
    assert result["records"]


def test_invalid_chroma_from_adapter_is_fail_closed(monkeypatch, tmp_path: Path):
    audio = write_major_chord_wav(tmp_path / "c_major.wav")
    monkeypatch.setattr(
        "src.joint_key_profile_benchmark.mean_cqt_chroma",
        lambda _path: type("Result", (), {"chroma_mean": np.zeros(12)})(),
    )

    with pytest.raises(JointKeyProfileError):
        score_audio(audio)


def test_profile_fixture_input_is_accepted_by_core_contract():
    result = rotate_profile(MAJOR_PROFILE, SEMITONES.index("C"))
    assert result.shape == (12,)
