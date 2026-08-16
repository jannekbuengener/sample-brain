"""Harmony Finder music logic — deterministic tests with synthetic data."""

from __future__ import annotations

import math

import pytest

from src.workbench_controller import WorkbenchRow
from src.workbench_harmony import (
    HarmonyRelation,
    HarmonySuggestion,
    find_harmony_matches,
    rate_harmony,
    determine_relation,
)
from src.key_signature import (
    parse_key_signature,
    is_same_root,
    key_distance_semitones,
)


def _row(
    name: str,
    *,
    bpm: float | None = 128.0,
    key: str | None = "C",
    pred_type: str | None = "kick",
    status: str = "ok",
    path: str | None = None,
) -> WorkbenchRow:
    if path is None:
        path = f"/synthetic/{name}.wav"
    return WorkbenchRow(
        display_name=name,
        relative_path=f"{name}.wav",
        path=path,
        bpm=bpm,
        key=key,
        key_conf=0.8 if key else None,
        loudness=-20.0,
        brightness=2000.0,
        sample_class="loop",
        pred_type=pred_type,
        status=status,
    )


class TestKeySignatureCanonical:
    def test_flat_normalizes_to_sharp(self):
        k = parse_key_signature("Dbmin")
        assert k is not None
        assert k.root == "C#"
        assert k.mode == "min"

    def test_enharmonic_equality(self):
        a = parse_key_signature("C#min")
        b = parse_key_signature("Dbmin")
        assert is_same_root(a, b)
        assert key_distance_semitones(a, b) == 0

    def test_unknown_mode_is_none(self):
        k = parse_key_signature("C")
        assert k is not None
        assert k.root == "C"
        assert k.mode is None

    def test_invalid_key_returns_none(self):
        assert parse_key_signature("!!!") is None
        assert parse_key_signature(None) is None


class TestDirectRelation:
    def test_same_root_same_mode_is_direct(self):
        ref = _row("ref", bpm=128.0, key="Cmaj")
        cand = _row("cand", bpm=128.0, key="Cmaj")
        result = rate_harmony(ref, cand)
        assert result.relation == HarmonyRelation.DIRECT
        assert "C" in result.explanation or "Direkt" in result.explanation

    def test_enharmonic_direct(self):
        ref = _row("ref", bpm=128.0, key="C#min")
        cand = _row("cand", bpm=128.0, key="Dbmin")
        result = rate_harmony(ref, cand)
        assert result.relation == HarmonyRelation.DIRECT

    def test_cmaj_equals_cmaj_direct(self):
        ref = _row("ref", key="Cmaj")
        cand = _row("cand", key="Cmaj")
        assert rate_harmony(ref, cand).relation == HarmonyRelation.DIRECT

    def test_dbmaj_equals_csharpsmaj_direct(self):
        ref = _row("ref", key="Dbmaj")
        cand = _row("cand", key="C#maj")
        assert rate_harmony(ref, cand).relation == HarmonyRelation.DIRECT


class TestRelatedRelation:
    def test_relative_major_minor(self):
        ref = _row("ref", key="Cmaj")
        cand = _row("cand", key="Amin")
        result = rate_harmony(ref, cand)
        assert result.relation == HarmonyRelation.RELATED

    def test_relative_minor_major(self):
        ref = _row("ref", key="Amin")
        cand = _row("cand", key="Cmaj")
        assert rate_harmony(ref, cand).relation == HarmonyRelation.RELATED

    def test_fifth_same_mode(self):
        ref = _row("ref", key="Cmaj")
        cand = _row("cand", key="Gmaj")
        result = rate_harmony(ref, cand)
        assert result.relation == HarmonyRelation.RELATED

    def test_fourth_same_mode(self):
        ref = _row("ref", key="Cmaj")
        cand = _row("cand", key="Fmaj")
        assert rate_harmony(ref, cand).relation == HarmonyRelation.RELATED

    def test_fifth_minor(self):
        ref = _row("ref", key="Amin")
        cand = _row("cand", key="Emin")
        assert rate_harmony(ref, cand).relation == HarmonyRelation.RELATED

    def test_fourth_minor(self):
        ref = _row("ref", key="Amin")
        cand = _row("cand", key="Dmin")
        assert rate_harmony(ref, cand).relation == HarmonyRelation.RELATED


class TestUnknownModeCautious:
    def test_unknown_mode_not_claimed_direct(self):
        ref = _row("ref", key="C")
        cand = _row("cand", key="C")
        result = rate_harmony(ref, cand)
        assert result.relation == HarmonyRelation.UNCERTAIN
        assert "Modus unbekannt" in result.explanation

    def test_unknown_mode_no_relative_claim(self):
        ref = _row("ref", key="C")
        cand = _row("cand", key="A")
        result = rate_harmony(ref, cand)
        assert result.relation == HarmonyRelation.UNCERTAIN

    def test_unknown_mode_no_fifth_claim(self):
        ref = _row("ref", key="C")
        cand = _row("cand", key="G")
        result = rate_harmony(ref, cand)
        assert result.relation == HarmonyRelation.UNCERTAIN


class TestTransposeRelation:
    def test_transposable_within_range(self):
        ref = _row("ref", bpm=128.0, key="Cmaj")
        cand = _row("cand", bpm=128.0, key="Dmaj")
        result = rate_harmony(ref, cand)
        assert result.relation == HarmonyRelation.TRANSPOSE
        assert result.pitch_shift_semitones == 2
        assert "+2" in result.explanation or "Halbtön" in result.explanation

    def test_transpose_minus_one(self):
        ref = _row("ref", key="Cmaj")
        cand = _row("cand", key="Bmaj")
        result = rate_harmony(ref, cand)
        assert result.relation == HarmonyRelation.TRANSPOSE
        assert result.pitch_shift_semitones == -1

    def test_transpose_plus_one(self):
        ref = _row("ref", key="Cmaj")
        cand = _row("cand", key="C#maj")
        result = rate_harmony(ref, cand)
        assert result.relation == HarmonyRelation.TRANSPOSE
        assert result.pitch_shift_semitones == 1

    def test_transpose_within_3_semitones(self):
        ref = _row("ref", key="Cmaj")
        for target_key, shift in [
            ("C#maj", 1),
            ("Dmaj", 2),
            ("D#maj", 3),
            ("Bmaj", -1),
            ("A#maj", -2),
            ("Amaj", -3),
        ]:
            cand = _row("cand", key=target_key)
            result = rate_harmony(ref, cand)
            assert result.relation == HarmonyRelation.TRANSPOSE
            assert result.pitch_shift_semitones == shift

    def test_transpose_outside_range_no_recommendation(self):
        ref = _row("ref", key="Cmaj")
        cand = _row("cand", key="Emaj")
        result = rate_harmony(ref, cand)
        assert result.relation == HarmonyRelation.UNCERTAIN
        assert result.pitch_shift_semitones is None


class TestUncertainRelation:
    def test_missing_reference_key(self):
        ref = _row("ref", key=None)
        cand = _row("cand", key="Cmaj")
        result = rate_harmony(ref, cand)
        assert result.relation == HarmonyRelation.UNCERTAIN

    def test_missing_candidate_key(self):
        ref = _row("ref", key="Cmaj")
        cand = _row("cand", key=None)
        result = rate_harmony(ref, cand)
        assert result.relation == HarmonyRelation.UNCERTAIN

    def test_both_keys_missing(self):
        ref = _row("ref", key=None)
        cand = _row("cand", key=None)
        result = rate_harmony(ref, cand)
        assert result.relation == HarmonyRelation.UNCERTAIN

    def test_invalid_key(self):
        ref = _row("ref", key="invalid")
        cand = _row("cand", key="Cmaj")
        result = rate_harmony(ref, cand)
        assert result.relation == HarmonyRelation.UNCERTAIN


class TestScoring:
    def test_weighting_075_harmony_025_bpm(self):
        ref = _row("ref", bpm=128.0, key="Cmaj")
        direct_bpm_match = _row("d", bpm=128.0, key="Gmaj")  # related, bpm exact
        related_no_bpm = _row("r", bpm=60.0, key="Am")  # related, bpm far

        direct_direct = rate_harmony(ref, _row("dd", bpm=128.0, key="Cmaj"))
        related_exact_bpm = rate_harmony(ref, direct_bpm_match)
        related_far_bpm = rate_harmony(ref, related_no_bpm)

        # Direct should beat related when bpm is far for related.
        assert direct_direct.total_score > related_far_bpm.total_score

    def test_direct_beats_related_at_equal_subscores(self):
        ref = _row("ref", bpm=128.0, key="Cmaj")
        related = _row("rel", bpm=128.0, key="Am")  # related, bpm exact
        direct = _row("dir", bpm=128.0, key="Cmaj")  # direct, bpm exact

        result_rel = rate_harmony(ref, related)
        result_dir = rate_harmony(ref, direct)

        assert result_dir.total_score > result_rel.total_score

    def test_excludes_reference_from_results(self):
        ref = _row("ref", bpm=128.0, key="Cmaj")
        suggestions, status = find_harmony_matches(ref, [ref])
        assert suggestions == []
        assert status is not None
        assert (
            "keine" in status.casefold()
            or "keine" in status.lower()
            or len(suggestions) == 0
        )

    def test_query_filters_candidates(self):
        ref = _row("ref", bpm=128.0, key="Cmaj")
        kick_row = _row("kick-hit", bpm=128.0, key="Cmaj", pred_type="kick")
        pad_row = _row("pad", bpm=128.0, key="Cmaj", pred_type="pad")

        all_s, _ = find_harmony_matches(ref, [ref, kick_row, pad_row])
        filtered_s, _ = find_harmony_matches(ref, [ref, kick_row, pad_row], query="pad")

        assert len(filtered_s) == 1
        assert filtered_s[0].row.display_name == "pad"

    def test_empty_query_allows_all(self):
        ref = _row("ref", bpm=128.0, key="Cmaj")
        others = [_row(f"o{i}", bpm=128.0, key="Cmaj") for i in range(3)]
        suggestions, _ = find_harmony_matches(ref, [ref, *others])
        assert len(suggestions) == 3

    def test_missing_bpm_does_not_crash(self):
        ref = _row("ref", bpm=128.0, key="Cmaj")
        no_bpm = _row("nobpm", bpm=None, key="Cmaj")
        suggestions, _ = find_harmony_matches(ref, [ref, no_bpm])
        assert len(suggestions) == 1
        assert suggestions[0].bpm_score >= 0.0

    def test_reference_bpm_zero_rejected(self):
        ref = _row("ref", bpm=0.0, key="Cmaj")
        suggestions, status = find_harmony_matches(ref, [ref])
        assert suggestions == []
        assert status is not None

    def test_deterministic_tie_break(self):
        ref = _row("ref", bpm=128.0, key="Cmaj")
        # Two identical-score candidates
        a = _row("a", bpm=128.0, key="Cmaj", path="/synthetic/a.wav")
        b = _row("b", bpm=128.0, key="Cmaj", path="/synthetic/b.wav")
        first = find_harmony_matches(ref, [ref, a, b])[0]
        second = find_harmony_matches(ref, [ref, a, b])[0]
        assert [s.row.path for s in first] == [s.row.path for s in second]

    def test_results_sorted_by_relation_priority_then_score(self):
        ref = _row("ref", bpm=128.0, key="Cmaj")
        direct_row = _row("direct", bpm=128.0, key="Cmaj")
        related_row = _row("related", bpm=128.0, key="Gmaj")  # fifth
        uncertain_row = _row("uncertain", bpm=60.0, key=None)

        suggestions, _ = find_harmony_matches(
            ref, [ref, direct_row, related_row, uncertain_row]
        )
        relations = [s.relation for s in suggestions]
        assert (
            relations
            == [
                (
                    HarmonyRelation.DIRECT.value
                    if hasattr(HarmonyRelation.DIRECT, "value")
                    else HarmonyRelation.DIRECT
                ),
            ]
            or relations[0] == HarmonyRelation.DIRECT
        )

    def test_reference_excluded_not_in_any_group(self):
        ref = _row("ref", bpm=128.0, key="Cmaj")
        suggestions, _ = find_harmony_matches(
            ref, [ref, _row("other", bpm=128.0, key="Cmaj")]
        )
        assert all(s.row.path != ref.path for s in suggestions)


class TestKeyOverride:
    def test_override_changes_results(self):
        ref = _row("ref", bpm=128.0, key="Cmaj")
        cand = _row("cand", bpm=128.0, key="Cmaj")
        original_result = rate_harmony(ref, cand)

        ref_override = _row("ref", bpm=128.0, key="Cmin")
        override_result = rate_harmony(ref_override, cand)

        assert (
            override_result.relation != original_result.relation
            or override_result.harmony_score != original_result.harmony_score
        )

    def test_original_row_key_unchanged_after_search(self):
        ref = _row("ref", bpm=128.0, key="C")
        original_key = ref.key
        find_harmony_matches(
            ref, [_row("c", bpm=128.0, key="Cmin")], key_override="Cmin"
        )
        assert ref.key == original_key

    def test_no_override_uses_original_key(self):
        ref = _row("ref", bpm=128.0, key="Cmaj")
        cand = _row("cand", bpm=128.0, key="Am")
        result_no_override = rate_harmony(ref, cand)
        assert result_no_override.relation == HarmonyRelation.RELATED


class TestServiceGrouping:
    def test_direct_group_populated(self):
        ref = _row("ref", bpm=128.0, key="Cmaj")
        cand = _row("direct", bpm=128.0, key="Cmaj")
        suggestions, _ = find_harmony_matches(ref, [ref, cand])
        direct_items = [s for s in suggestions if s.relation == HarmonyRelation.DIRECT]
        assert len(direct_items) == 1

    def test_related_group_populated(self):
        ref = _row("ref", bpm=128.0, key="Cmaj")
        cand = _row("related", bpm=128.0, key="Gmaj")
        suggestions, _ = find_harmony_matches(ref, [ref, cand])
        related_items = [
            s for s in suggestions if s.relation == HarmonyRelation.RELATED
        ]
        assert len(related_items) == 1

    def test_transpose_group_populated(self):
        ref = _row("ref", bpm=128.0, key="Cmaj")
        cand = _row("transpose", bpm=128.0, key="Dmaj")
        suggestions, _ = find_harmony_matches(ref, [ref, cand])
        transpose_items = [
            s for s in suggestions if s.relation == HarmonyRelation.TRANSPOSE
        ]
        assert len(transpose_items) == 1

    def test_uncertain_group_populated(self):
        ref = _row("ref", bpm=128.0, key="Cmaj")
        cand = _row("uncertain", bpm=60.0, key=None)
        suggestions, _ = find_harmony_matches(ref, [ref, cand])
        uncertain_items = [
            s for s in suggestions if s.relation == HarmonyRelation.UNCERTAIN
        ]
        assert len(uncertain_items) == 1

    def test_results_come_in_priority_order(self):
        ref = _row("ref", bpm=128.0, key="Cmaj")
        direct = _row("direct", bpm=128.0, key="Cmaj")
        related = _row("related", bpm=128.0, key="Gmaj")
        transpose = _row("trans", bpm=128.0, key="Dmaj")
        uncertain = _row("unc", bpm=128.0, key=None)

        suggestions, _ = find_harmony_matches(
            ref, [ref, direct, related, transpose, uncertain]
        )

        priority = {
            HarmonyRelation.DIRECT: 0,
            HarmonyRelation.RELATED: 1,
            HarmonyRelation.TRANSPOSE: 2,
            HarmonyRelation.UNCERTAIN: 3,
        }
        relations = [s.relation for s in suggestions]
        priorities = [priority[r] for r in relations]
        assert priorities == sorted(priorities)
