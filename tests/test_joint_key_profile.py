from __future__ import annotations

import math

import numpy as np
import pytest

from src.joint_key_profile import (
    MAJOR_PROFILE,
    MINOR_PROFILE,
    SEMITONES,
    JointKeyProfileError,
    pearson_score,
    rank_joint_key_profiles,
    rotate_profile,
)


@pytest.mark.parametrize("root_index", range(12))
def test_profile_rotation_places_tonic_weight_at_requested_root(root_index: int):
    rotated = rotate_profile(MAJOR_PROFILE, root_index)

    assert rotated.shape == (12,)
    assert rotated[root_index] == MAJOR_PROFILE[0]
    assert rotated[(root_index + 1) % 12] == MAJOR_PROFILE[1]


def test_major_profile_ranks_matching_major_key_first():
    result = rank_joint_key_profiles(rotate_profile(MAJOR_PROFILE, SEMITONES.index("D")))

    assert (result.root, result.mode) == ("D", "maj")
    assert result.ranking[0].score == pytest.approx(1.0)


def test_minor_profile_ranks_matching_minor_key_first():
    result = rank_joint_key_profiles(rotate_profile(MINOR_PROFILE, SEMITONES.index("A")))

    assert (result.root, result.mode) == ("A", "min")
    assert result.ranking[0].score == pytest.approx(1.0)


def test_pearson_score_is_deterministic_and_finite():
    observed = np.asarray([0.2, 0.4, 1.0, 0.1, 0.8, 0.7, 0.0, 0.6, 0.3, 0.5, 0.9, 0.25])

    first = pearson_score(observed, MAJOR_PROFILE)
    second = pearson_score(observed, MAJOR_PROFILE)

    assert first == second
    assert math.isfinite(first)
    assert -1.0 <= first <= 1.0


def test_tie_break_is_stable_and_uses_c_major_before_other_hypotheses(monkeypatch):
    monkeypatch.setattr("src.joint_key_profile.pearson_score", lambda *_args: 0.0)

    result = rank_joint_key_profiles(np.arange(12, dtype=np.float64))

    assert (result.root, result.mode) == ("C", "maj")
    assert [(entry.root, entry.mode) for entry in result.ranking[:3]] == [
        ("C", "maj"),
        ("C#", "maj"),
        ("D", "maj"),
    ]


@pytest.mark.parametrize(
    "chroma, message",
    [
        (np.asarray([]), "exactly 12"),
        (np.ones(11), "exactly 12"),
        (np.ones((12, 1)), "one-dimensional"),
        (np.zeros(12), "non-zero variance"),
        (np.ones(12), "non-zero variance"),
        (np.asarray([-1.0] + [0.0] * 11), "non-negative"),
        (np.asarray([np.nan] + [0.0] * 11), "finite"),
        (np.asarray([np.inf] + [0.0] * 11), "finite"),
    ],
)
def test_ranker_rejects_undefined_or_invalid_chroma(chroma: np.ndarray, message: str):
    with pytest.raises(JointKeyProfileError, match=message):
        rank_joint_key_profiles(chroma)


def test_ranker_rejects_non_numeric_chroma_as_a_controlled_error():
    with pytest.raises(JointKeyProfileError, match="numeric"):
        rank_joint_key_profiles(["not-a-pitch-class"] * 12)


def test_repeat_identical_input_has_identical_complete_evidence():
    chroma = rotate_profile(MAJOR_PROFILE, SEMITONES.index("F#")) + np.linspace(0.0, 0.01, 12)

    first = rank_joint_key_profiles(chroma)
    second = rank_joint_key_profiles(chroma)

    assert first == second
    assert len(first.ranking) == 24
    assert all(math.isfinite(entry.score) for entry in first.ranking)


def test_core_has_no_essentia_or_probability_dependency():
    import src.joint_key_profile as prototype

    source = prototype.__file__
    assert source is not None
    assert "essentia" not in open(source, encoding="utf-8").read().casefold()
