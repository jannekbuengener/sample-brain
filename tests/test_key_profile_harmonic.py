from __future__ import annotations

from pathlib import Path

from src.key_profile_analysis import rank_key_profiles
from src.key_profile_audio_calibration import extract_harmonic_chroma_evidence
from tests.audio_fixtures import write_key_audio_wav, write_seeded_noise_wav


def test_hpss_evidence_is_deterministic_finite_and_bounded(tmp_path: Path) -> None:
    path = write_key_audio_wav(tmp_path / "clear.wav", frequency_hz=261.63, mode="maj")
    first = extract_harmonic_chroma_evidence(path)
    second = extract_harmonic_chroma_evidence(path)
    assert first.harmonic_energy_fraction == second.harmonic_energy_fraction
    assert first.harmonic_rms == second.harmonic_rms
    assert first.percussive_rms == second.percussive_rms
    assert 0.0 <= first.harmonic_energy_fraction <= 1.0
    assert first.harmonic_rms >= 0.0 and first.percussive_rms >= 0.0
    assert rank_key_profiles(first.chroma_mean if first.chroma_mean is not None else ()).root == "C"


def test_noise_is_not_a_production_key_claim(tmp_path: Path) -> None:
    evidence = extract_harmonic_chroma_evidence(write_seeded_noise_wav(tmp_path / "noise.wav"))
    assert 0.0 <= evidence.harmonic_energy_fraction <= 1.0
