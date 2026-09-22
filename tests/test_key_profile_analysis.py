from __future__ import annotations

import math

import numpy as np

from src.key_profile_analysis import (
    MAJOR_KEY_PROFILE,
    MINOR_KEY_PROFILE,
    PROFILE_EVIDENCE_KIND,
    PROFILE_EVIDENCE_VERSION,
    characterize_synthetic_margins,
    rank_key_profiles,
)


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
