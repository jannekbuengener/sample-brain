"""Frozen neutral harmony contracts for Analysis Extraction Slice 1."""
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from src import harmony
from src.aq6_harmonic_theory_truth_table import FIXTURE_RELPATH, load_truth_table_fixture


def _input(name, *, key="Cmaj", bpm=128.0, path=None, relative_path=None, pred_type="kick"):
    return harmony.HarmonyInput(
        display_name=name,
        relative_path=relative_path or f"{name}.wav",
        path=path or f"/synthetic/{name}.wav",
        bpm=bpm,
        key=key,
        pred_type=pred_type,
    )


def test_input_is_immutable_and_result_remains_generic_and_rebindable():
    original = _input("original")
    with pytest.raises(FrozenInstanceError):
        original.key = "Dmaj"
    suggestion = harmony.rate_harmony(_input("ref"), original)
    assert suggestion.row is original
    assert len(harmony.HarmonySuggestion.__parameters__) == 1
    rebound = _input("rebound")
    suggestion.row = rebound
    assert suggestion.row is rebound


def test_neutral_rater_matches_all_584_frozen_theory_cells():
    document = load_truth_table_fixture(Path(__file__).resolve().parents[1] / FIXTURE_RELPATH)
    assert len(document["cells"]) == 584
    for cell in document["cells"]:
        result = harmony.rate_harmony(
            _input("ref", key=cell["source_key"]),
            _input("cand", key=cell["target_key"]),
        )
        assert result.relation.value == cell["relation"], cell["cell_id"]
        assert result.pitch_shift_semitones == cell["pitch_shift_semitones"], cell["cell_id"]
        assert result.harmony_score == {"direct": 1.0, "related": 0.7, "transpose": 0.5, "uncertain": 0.0}[cell["relation"]]
        assert result.bpm_score == 1.0
        assert result.total_score == pytest.approx({"direct": 1.0, "related": 0.775, "transpose": 0.625, "uncertain": 0.25}[cell["relation"]])


@pytest.mark.parametrize("key,shift", [("C#maj", 1), ("Dmaj", 2), ("D#maj", 3), ("Bmaj", -1), ("A#maj", -2), ("Amaj", -3)])
def test_pitch_shift_preserves_existing_sign_and_band(key, shift):
    result = harmony.rate_harmony(_input("ref"), _input("cand", key=key))
    assert result.relation is harmony.HarmonyRelation.TRANSPOSE
    assert result.pitch_shift_semitones == shift


@pytest.mark.parametrize("key", [None, "C", "malformed"])
def test_missing_or_unknown_mode_stays_uncertain(key):
    result = harmony.rate_harmony(_input("ref"), _input("cand", key=key))
    assert result.relation is harmony.HarmonyRelation.UNCERTAIN
    assert result.harmony_score == 0.0
    assert result.pitch_shift_semitones is None


def test_bpm_only_changes_ranking_score_and_reuses_half_double_scoring():
    ref = _input("ref")
    direct = harmony.rate_harmony(ref, _input("cand"))
    mismatch = harmony.rate_harmony(ref, _input("cand", bpm=140.0))
    missing = harmony.rate_harmony(ref, _input("cand", bpm=None))
    half = harmony.rate_harmony(ref, _input("cand", bpm=64.0))
    assert direct.bpm_score == 1.0
    assert mismatch.bpm_score == missing.bpm_score == 0.0
    assert half.bpm_score == 0.9
    assert direct.total_score == 1.0
    assert mismatch.total_score == missing.total_score == 0.75
    for result in (direct, mismatch, missing, half):
        assert result.relation is harmony.HarmonyRelation.DIRECT
        assert result.pitch_shift_semitones is None
        assert result.harmony_score == 1.0


def test_override_only_changes_reference_evaluation():
    ref = _input("ref", key="Gmaj")
    candidate = _input("cand")
    result = harmony.rate_harmony(ref, candidate, key_override="Cmaj")
    assert result.relation is harmony.HarmonyRelation.DIRECT
    assert ref.key == "Gmaj"
    assert candidate.key == "Cmaj"
    matches, error = harmony.find_harmony_matches(ref, [candidate], key_override="Cmaj")
    assert error is None
    assert matches[0].relation is harmony.HarmonyRelation.DIRECT


@pytest.mark.parametrize("query", [" UNIQUE LABEL ", "special/subdir", "cmaj", "snare"])
def test_finder_queries_each_existing_metadata_surface(query):
    candidate = _input("Unique Label", relative_path="special/subdir/item.wav", pred_type="snare")
    other = _input("other", key="Dmin", pred_type="pad")
    matches, error = harmony.find_harmony_matches(_input("ref"), [other, candidate], query=query)
    assert error is None
    assert [result.row for result in matches] == [candidate]


def test_finder_keeps_reference_exclusion_and_error_messages():
    ref = _input("ref")
    alias = replace(ref, display_name="alias")
    matches, error = harmony.find_harmony_matches(ref, [ref, alias])
    assert matches == []
    assert error == "Keine weiteren geladenen Samples zum Vergleichen."
    for bpm in (None, 0.0, -1.0):
        matches, error = harmony.find_harmony_matches(replace(ref, bpm=bpm), [_input("cand")])
        assert matches == []
        assert error == "Ähnliche Samples benötigen ein analysiertes BPM."


def test_finder_relation_score_name_path_and_stable_tie_order():
    first = _input("Alpha", path="/a")
    second = replace(first)
    later_path = replace(first, display_name="alpha", path="/b")
    later_name = _input("Zulu")
    direct_low_bpm = _input("low-bpm", bpm=140.0)
    related = _input("related", key="Gmaj")
    transpose = _input("transpose", key="Dmaj")
    uncertain = _input("uncertain", key=None)
    candidates = [uncertain, transpose, related, direct_low_bpm, later_name, later_path, first, second]
    matches, error = harmony.find_harmony_matches(_input("ref"), candidates)
    assert error is None
    expected = [first, second, later_path, later_name, direct_low_bpm, related, transpose, uncertain]
    assert all(result.row is row for result, row in zip(matches, expected, strict=True))
    again, _ = harmony.find_harmony_matches(_input("ref"), candidates)
    assert [result.row for result in again] == expected
    for limit in (0, 1, 3, -1):
        limited, _ = harmony.find_harmony_matches(_input("ref"), candidates, limit=limit)
        assert [result.row for result in limited] == expected[:limit]


def test_aq6_factories_and_execution_bindings_use_neutral_owner():
    from src import aq6_harmonic_theory_baseline as theory_run
    from src import aq6_harmonic_ranking_baseline as ranking_run
    from src import aq6_harmonic_ranking_candidate_compare as compare

    assert isinstance(theory_run._row("ref", key="Cmaj"), harmony.HarmonyInput)
    assert isinstance(ranking_run.row_from_fixture_item({"synthetic_id": "candidate", "key": "Cmaj", "bpm": 128.0}), harmony.HarmonyInput)
    assert theory_run.rate_harmony is harmony.rate_harmony
    assert ranking_run.rate_harmony is harmony.rate_harmony
    assert ranking_run.find_harmony_matches is harmony.find_harmony_matches
    assert compare.find_harmony_matches is harmony.find_harmony_matches
    assert compare.HarmonySuggestion is harmony.HarmonySuggestion
    assert compare.HarmonyRelation is harmony.HarmonyRelation
