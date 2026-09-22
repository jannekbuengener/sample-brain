from __future__ import annotations

import math

import numpy as np

from src.key_profile_analysis import (
    DEFAULT_PROFILE_GATE,
    MAJOR_KEY_PROFILE,
    MINOR_KEY_PROFILE,
    PROFILE_GATE_VERSION,
    PROFILE_EVIDENCE_KIND,
    PROFILE_EVIDENCE_VERSION,
    characterize_synthetic_gate,
    characterize_synthetic_margins,
    gate_ranked_key_profile,
    rank_key_profiles,
    synthetic_profile_gate_fixtures,
)
from tests.audio_fixtures import write_hihat_noise_wav, write_seeded_noise_wav


def test_rotated_profiles_rank_all_major_and_minor_tonics() -> None:
    for root_index in range(12):
        major = rank_key_profiles(np.roll(np.asarray(MAJOR_KEY_PROFILE), root_index))
        minor = rank_key_profiles(np.roll(np.asarray(MINOR_KEY_PROFILE), root_index))
        assert major.root_index == root_index
        assert major.mode == "maj"
        assert minor.root_index == root_index
        assert minor.mode == "min"


def test_ambiguous_chroma_remains_ranked_only_not_a_production_claim() -> None:
    ambiguous_chroma = [
        np.array([1.0] + [0.0] * 11),  # single note
        np.array([2.0] + [0.0] * 11),  # octave, same pitch class
        np.array([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0] + [0.0] * 4),  # root + fifth
        np.array([1.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 1.0] + [0.0] * 4),  # maj/min blend
    ]
    for chroma in ambiguous_chroma:
        result = rank_key_profiles(chroma)
        assert result.status == "ranked_only"
        assert result.canonical_key is not None


def test_rankings_are_deterministic_and_evidence_is_finite() -> None:
    chroma = np.asarray(MAJOR_KEY_PROFILE) + np.roll(np.asarray(MAJOR_KEY_PROFILE), 6)
    first = rank_key_profiles(chroma)
    second = rank_key_profiles(chroma)

    assert first == second
    assert first.evidence_kind == PROFILE_EVIDENCE_KIND
    assert first.evidence_version == PROFILE_EVIDENCE_VERSION
    assert first.status == "ranked_only"
    assert len(first.hypotheses) == 24
    assert all(math.isfinite(hypothesis.score) for hypothesis in first.hypotheses)
    assert first.best_score is not None and math.isfinite(first.best_score)
    assert first.runner_up_score is not None and math.isfinite(first.runner_up_score)
    assert first.margin is not None and math.isfinite(first.margin)
    assert [hypothesis.score for hypothesis in first.hypotheses] == sorted(
        (hypothesis.score for hypothesis in first.hypotheses), reverse=True
    )


def test_noninformative_chroma_abstains() -> None:
    result = rank_key_profiles(np.ones(12, dtype=np.float64))

    assert result.status == "abstained"
    assert result.canonical_key is None
    assert result.hypotheses == ()


def test_synthetic_margin_characterization_does_not_define_a_threshold() -> None:
    summary = characterize_synthetic_margins()

    assert set(summary) == {"clear_synthetic_profiles", "ambiguous_synthetic_chroma"}
    assert summary["clear_synthetic_profiles"]["count"] == 24
    assert summary["ambiguous_synthetic_chroma"]["count"] == 4
    assert summary["clear_synthetic_profiles"]["median"] is not None
    assert summary["ambiguous_synthetic_chroma"]["median"] is not None


def test_synthetic_gate_resolves_every_clear_major_and_minor_fixture() -> None:
    clear = [fixture for fixture in synthetic_profile_gate_fixtures() if fixture.group == "clear"]

    assert len(clear) >= 12
    assert {fixture.mode for fixture in clear if fixture.mode == "maj"} == {"maj"}
    assert {fixture.mode for fixture in clear if fixture.mode == "min"} == {"min"}
    assert len({fixture.root for fixture in clear if fixture.mode == "maj"}) >= 6
    assert len({fixture.root for fixture in clear if fixture.mode == "min"}) >= 6
    for fixture in clear:
        result = gate_ranked_key_profile(fixture.chroma_mean, fixture.chroma_std)
        assert result.status == "resolved"
        assert result.root == fixture.root
        assert result.mode == fixture.mode


def test_synthetic_gate_abstains_for_ambiguous_and_percussive_fixtures() -> None:
    non_tonal = [fixture for fixture in synthetic_profile_gate_fixtures() if fixture.group != "clear"]

    assert {fixture.name for fixture in non_tonal} >= {
        "single_note",
        "octave",
        "root_fifth",
        "major_minor_blend",
        "pulse_train",
        "kick_transient",
        "broadband_noise",
        "hihat_noise",
    }
    for fixture in non_tonal:
        result = gate_ranked_key_profile(fixture.chroma_mean, fixture.chroma_std)
        assert result.status == "abstained", fixture.name
        assert result.abstention_reasons


def test_gate_evidence_is_finite_deterministic_and_transposition_safe() -> None:
    fixture = next(
        item for item in synthetic_profile_gate_fixtures()
        if item.group == "clear" and item.root == "C" and item.mode == "maj"
    )
    first = gate_ranked_key_profile(fixture.chroma_mean, fixture.chroma_std)
    second = gate_ranked_key_profile(fixture.chroma_mean, fixture.chroma_std)
    transposed = gate_ranked_key_profile(np.roll(fixture.chroma_mean, 5), np.roll(fixture.chroma_std, 5))

    assert first == second
    assert first.gate_version == PROFILE_GATE_VERSION
    assert first.gate_name == DEFAULT_PROFILE_GATE.name
    assert transposed.status == "resolved"
    assert transposed.root_index == 5
    assert all(math.isfinite(value) for value in (
        first.evidence.best_score,
        first.evidence.runner_up_score,
        first.evidence.margin,
        first.evidence.normalized_entropy,
        first.evidence.dominant_pitch_class_concentration,
        first.evidence.temporal_stability,
    ))
    assert list(first.evidence.conditions) == sorted(first.evidence.conditions)


def test_synthetic_gate_characterization_and_selection_are_public_and_bounded() -> None:
    characterization = characterize_synthetic_gate()

    assert set(characterization) == {"clear", "ambiguous", "percussive", "gate_candidates"}
    assert characterization["clear"]["count"] >= 12
    assert characterization["ambiguous"]["count"] == 4
    assert characterization["percussive"]["count"] == 4
    assert set(characterization["gate_candidates"]) == {"G0", "G1", "G2", "G3", "G4"}
    assert DEFAULT_PROFILE_GATE.name in {"G0", "G1", "G2", "G3", "G4"}
    assert characterization["gate_candidates"][DEFAULT_PROFILE_GATE.name]["viable"] is True


def test_noise_fixtures_are_seeded_and_deterministic(tmp_path) -> None:
    first_noise = write_seeded_noise_wav(tmp_path / "noise-a.wav")
    second_noise = write_seeded_noise_wav(tmp_path / "noise-b.wav")
    first_hihat = write_hihat_noise_wav(tmp_path / "hat-a.wav")
    second_hihat = write_hihat_noise_wav(tmp_path / "hat-b.wav")

    assert first_noise.read_bytes() == second_noise.read_bytes()
    assert first_hihat.read_bytes() == second_hihat.read_bytes()
