from __future__ import annotations

from pathlib import Path

import numpy as np

from src.analyze import extract_features
from src.key_profile_analysis import (
    DEFAULT_PROFILE_GATE,
    SyntheticProfileFixture,
    calibrate_profile_gate,
    characterize_profile_gate_fixtures,
    gate_ranked_key_profile,
)
from src.key_profile_audio_calibration import extract_audio_chroma_statistics
from tests.audio_fixtures import (
    write_hihat_noise_wav,
    write_key_audio_wav,
    write_kick_transient_wav,
    write_major_minor_blend_wav,
    write_octave_wav,
    write_pulse_train_wav,
    write_root_fifth_wav,
    write_seeded_noise_wav,
    write_sine_wav,
)


NOTE_HZ = {
    "C": 261.63,
    "D": 293.66,
    "E": 329.63,
    "F": 349.23,
    "G": 392.00,
    "A": 440.00,
}


def build_audio_domain_calibration_fixtures(work_dir: Path) -> tuple[SyntheticProfileFixture, ...]:
    """Build the public WAV corpus and consume its real CQT mean/std evidence."""
    fixtures: list[SyntheticProfileFixture] = []

    def add(name: str, group: str, path: Path, root: str | None = None, mode: str | None = None) -> None:
        statistics = extract_audio_chroma_statistics(path)
        assert statistics is not None, name
        mean, std = statistics
        fixtures.append(SyntheticProfileFixture(name, group, mean, std, root, mode))

    for root, frequency_hz in NOTE_HZ.items():
        add(
            f"clear_{root}_maj", "clear",
            write_key_audio_wav(work_dir / f"clear_{root}_maj.wav", frequency_hz=frequency_hz, mode="maj"),
            root, "maj",
        )
        add(
            f"clear_{root}_min", "clear",
            write_key_audio_wav(work_dir / f"clear_{root}_min.wav", frequency_hz=frequency_hz, mode="min"),
            root, "min",
        )

    base = NOTE_HZ["C"]
    add("single_note", "ambiguous", write_sine_wav(work_dir / "single.wav", duration_sec=2.0, frequency_hz=base))
    add("octave", "ambiguous", write_octave_wav(work_dir / "octave.wav", frequency_hz=base))
    add("root_fifth", "ambiguous", write_root_fifth_wav(work_dir / "root-fifth.wav", frequency_hz=base))
    add("major_minor_blend", "ambiguous", write_major_minor_blend_wav(work_dir / "blend.wav", frequency_hz=base))
    add("pulse_train", "percussive", write_pulse_train_wav(work_dir / "pulse.wav", bpm=120.0))
    add("kick_transient", "percussive", write_kick_transient_wav(work_dir / "kick.wav", bpm=120.0))
    add("broadband_noise", "percussive", write_seeded_noise_wav(work_dir / "noise.wav"))
    add("hihat_noise", "percussive", write_hihat_noise_wav(work_dir / "hat.wav"))
    return tuple(fixtures)


def test_audio_domain_calibration_uses_real_extractor_statistics(tmp_path: Path) -> None:
    path = write_key_audio_wav(tmp_path / "clear.wav", frequency_hz=NOTE_HZ["C"], mode="maj")
    statistics = extract_audio_chroma_statistics(path)
    features = extract_features(path, duration=2.0)

    assert statistics is not None
    assert features is not None
    mean, std = statistics
    assert np.array_equal(mean.astype(np.float32), np.frombuffer(features.chroma_mean, dtype=np.float32))
    assert np.array_equal(std.astype(np.float32), np.frombuffer(features.chroma_std, dtype=np.float32))


def test_audio_domain_calibration_selects_a_deterministic_frozen_gate(tmp_path: Path) -> None:
    fixtures = build_audio_domain_calibration_fixtures(tmp_path)
    first = calibrate_profile_gate(fixtures)
    second = calibrate_profile_gate(fixtures)

    assert first == second
    assert first == DEFAULT_PROFILE_GATE
    assert first.name in {"G0", "G1", "G2", "G3", "G4", "NO_DEFENSIBLE_SYNTHETIC_GATE"}


def test_audio_domain_gate_contracts_and_characterization(tmp_path: Path) -> None:
    fixtures = build_audio_domain_calibration_fixtures(tmp_path)
    config = calibrate_profile_gate(fixtures)
    characterization = characterize_profile_gate_fixtures(fixtures)

    assert characterization["clear"]["count"] == 12
    assert characterization["ambiguous"]["count"] == 4
    assert characterization["percussive"]["count"] == 4
    assert set(characterization["gate_candidates"]) == {"G0", "G1", "G2", "G3", "G4"}
    if config.name != "NO_DEFENSIBLE_SYNTHETIC_GATE":
        for fixture in fixtures:
            result = gate_ranked_key_profile(fixture.chroma_mean, fixture.chroma_std, config=config)
            if fixture.group == "clear":
                assert result.status == "resolved", fixture.name
                assert result.root == fixture.root
                assert result.mode == fixture.mode
            else:
                assert result.status == "abstained", fixture.name
