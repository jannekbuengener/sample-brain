"""Frozen AQ6 Harmonic Match theory truth-table + KPI contract tests (#1015).

TEST FREEZE: these assertions define the theory regression contract. Fix the
truth-table module / product harmony classification — not these expectations —
when they turn red.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src import aq6_harmonic_theory_truth_table as theory
from src.key_signature import parse_key_signature
from src.workbench_harmony import (
    HarmonyRelation,
    determine_relation,
    rate_harmony,
)
from src.workbench_controller import WorkbenchRow

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = REPO_ROOT / theory.FIXTURE_RELPATH


def _row(name: str, *, key: str | None) -> WorkbenchRow:
    return WorkbenchRow(
        display_name=name,
        relative_path=f"{name}.wav",
        path=f"/synthetic/aq6/{name}.wav",
        bpm=128.0,
        key=key,
        key_conf=0.8 if key else None,
        loudness=-20.0,
        brightness=2000.0,
        sample_class="loop",
        pred_type="kick",
        status="ok",
    )


def _product_prediction(source_key: str | None, target_key: str | None) -> dict:
    """Map live product ``rate_harmony`` output onto theory prediction fields."""
    suggestion = rate_harmony(_row("ref", key=source_key), _row("cand", key=target_key))
    relation = suggestion.relation.value
    if relation in {"direct", "related", "transpose"}:
        compatibility = "compatible"
    else:
        source_parsed = parse_key_signature(source_key) if source_key else None
        target_parsed = parse_key_signature(target_key) if target_key else None
        modeful = (
            source_parsed is not None
            and target_parsed is not None
            and source_parsed.mode is not None
            and target_parsed.mode is not None
        )
        compatibility = "incompatible" if modeful else "uncertain"
    return {
        "relation": relation,
        "compatibility": compatibility,
        "pitch_shift_semitones": suggestion.pitch_shift_semitones,
    }


class TestAq6TheoryIdentities:
    def test_frozen_identities(self) -> None:
        assert theory.TRUTH_TABLE_ID == (
            "sample-brain.aq6.harmonic-theory.truth-table.v1"
        )
        assert theory.DOCUMENT_TYPE == "sample-brain.aq6.harmonic-theory-kpi.v1"
        assert theory.TRUTH_TABLE_VERSION == "1.0.0"
        assert theory.DOMAIN_TOKEN == "aq6.theory"
        assert theory.ROOTS == (
            "C",
            "C#",
            "D",
            "D#",
            "E",
            "F",
            "F#",
            "G",
            "G#",
            "A",
            "A#",
            "B",
        )
        assert theory.MODES == ("maj", "min")
        assert theory.RELATIONS == ("direct", "related", "transpose", "uncertain")


class TestAq6TruthTableFixture:
    def test_fixture_exists_and_matches_generator(self) -> None:
        assert FIXTURE_PATH.is_file(), (
            "missing frozen fixture; run write_truth_table_fixture"
        )
        loaded = theory.load_truth_table_fixture(FIXTURE_PATH)
        generated = theory.build_truth_table_document()
        assert loaded["truth_table_id"] == theory.TRUTH_TABLE_ID
        assert loaded["counts"]["modeful_pairs"] == 576
        assert loaded["counts"]["evidence_edge_cases"] == 8
        assert len(loaded["cells"]) == 584
        assert FIXTURE_PATH.read_bytes() == theory.truth_table_json_bytes(generated)

    def test_modeful_grid_covers_all_roots_and_modes(self) -> None:
        doc = theory.build_truth_table_document()
        modeful = list(theory.iter_modeful_cells(doc))
        assert len(modeful) == 576
        roots = {c["source_root"] for c in modeful} | {c["target_root"] for c in modeful}
        modes = {c["source_mode"] for c in modeful} | {c["target_mode"] for c in modeful}
        assert roots == set(theory.ROOTS)
        assert modes == set(theory.MODES)


class TestAq6TheoryInvariants:
    def test_transposition_invariance_zero_violations(self) -> None:
        violations = theory.transposition_invariance_violations()
        assert violations == []

    def test_relation_symmetry_on_modeful_pairs(self) -> None:
        for cell in theory.iter_modeful_cells(theory.build_truth_table_document()):
            assert cell["relation_symmetric_with_swap"] is True, cell["cell_id"]

    def test_pitch_shift_antisymmetry_for_transpose_pairs(self) -> None:
        for cell in theory.iter_modeful_cells(theory.build_truth_table_document()):
            if cell["relation"] != "transpose":
                assert cell["pitch_shift_semitones"] is None
                continue
            assert cell["pitch_shift_semitones"] is not None
            assert abs(cell["pitch_shift_semitones"]) <= 3
            assert cell["pitch_shift_antisymmetric_with_swap"] is True, cell["cell_id"]

    def test_no_incompatible_marked_compatible_in_truth_table(self) -> None:
        for cell in theory.build_truth_table_document()["cells"]:
            if cell["compatibility"] == "incompatible":
                assert cell["relation"] == "uncertain"
                assert cell["evidence_state"] == "modeful"

    def test_fail_closed_evidence_cells(self) -> None:
        evidence = [
            c
            for c in theory.build_truth_table_document()["cells"]
            if str(c["cell_id"]).startswith("evidence:")
        ]
        assert len(evidence) == 8
        for cell in evidence:
            assert cell["relation"] == "uncertain"
            assert cell["compatibility"] == "uncertain"
            assert cell["pitch_shift_semitones"] is None
            assert cell["evidence_state"] in {
                "missing_key",
                "missing_mode",
                "unparseable",
            }


class TestAq6ProductMatchesTruthTable:
    def test_determine_relation_and_rate_harmony_match_every_cell(self) -> None:
        doc = theory.load_truth_table_fixture(FIXTURE_PATH)
        mismatches: list[str] = []
        predictions: dict[str, dict] = {}
        for cell in doc["cells"]:
            pred = _product_prediction(cell["source_key"], cell["target_key"])
            predictions[cell["cell_id"]] = pred
            if (
                pred["relation"] != cell["relation"]
                or pred["compatibility"] != cell["compatibility"]
                or pred["pitch_shift_semitones"] != cell["pitch_shift_semitones"]
            ):
                mismatches.append(
                    f"{cell['cell_id']}: expected "
                    f"{cell['relation']}/{cell['compatibility']}/"
                    f"{cell['pitch_shift_semitones']} got "
                    f"{pred['relation']}/{pred['compatibility']}/"
                    f"{pred['pitch_shift_semitones']}"
                )
            # Also pin determine_relation enum for modeful / missing paths.
            ref = parse_key_signature(cell["source_key"]) if cell["source_key"] else None
            cand = parse_key_signature(cell["target_key"]) if cell["target_key"] else None
            # Unparseable strings parse as None — same as missing for determine_relation.
            if cell["source_key"] is not None and ref is None:
                ref = None
            if cell["target_key"] is not None and cand is None:
                cand = None
            relation, _ = determine_relation(ref, cand)
            assert relation == HarmonyRelation(cell["relation"])

        assert mismatches == []

        scores = theory.score_theory_predictions(doc["cells"], predictions)
        assert scores["relation_classification_accuracy"] == 1.0
        assert scores["incompatible_false_positive_rate"] == 0.0
        assert scores["compatible_false_negative_rate"] == 0.0
        assert scores["pitch_shift_suggestion_correctness"] == 1.0
        assert scores["counts"]["transpose"] == scores["counts"]["pitch_ok_transpose_only"]
        assert scores["counts"]["non_transpose_shift_null_failures"] == 0
        assert scores["evidence_fail_closed_rate"] == 1.0
        assert scores["transposition_invariance_violations"] == 0

    def test_pitch_shift_kpi_uses_transpose_denominator_only(self) -> None:
        cells = [
            {
                "cell_id": "t1",
                "relation": "transpose",
                "compatibility": "compatible",
                "evidence_state": "modeful",
                "pitch_shift_semitones": 2,
                "source_key": "Cmaj",
                "target_key": "Dmaj",
                "source_root": "C",
                "source_mode": "maj",
                "target_root": "D",
                "target_mode": "maj",
            },
            {
                "cell_id": "d1",
                "relation": "direct",
                "compatibility": "compatible",
                "evidence_state": "modeful",
                "pitch_shift_semitones": None,
                "source_key": "Cmaj",
                "target_key": "Cmaj",
                "source_root": "C",
                "source_mode": "maj",
                "target_root": "C",
                "target_mode": "maj",
            },
        ]
        preds = {
            "t1": {
                "relation": "transpose",
                "compatibility": "compatible",
                "pitch_shift_semitones": 1,  # wrong
            },
            "d1": {
                "relation": "direct",
                "compatibility": "compatible",
                "pitch_shift_semitones": None,
            },
        }
        scores = theory.score_theory_predictions(cells, preds)
        assert scores["pitch_shift_suggestion_correctness"] == 0.0
        assert scores["counts"]["transpose"] == 1

    def test_score_invariance_uses_candidate_predictions(self) -> None:
        cells = [
            {
                "cell_id": "a",
                "relation": "direct",
                "compatibility": "compatible",
                "evidence_state": "modeful",
                "pitch_shift_semitones": None,
                "source_key": "Cmaj",
                "target_key": "Cmaj",
                "source_root": "C",
                "source_mode": "maj",
                "target_root": "C",
                "target_mode": "maj",
            },
            {
                "cell_id": "b",
                "relation": "direct",
                "compatibility": "compatible",
                "evidence_state": "modeful",
                "pitch_shift_semitones": None,
                "source_key": "C#maj",
                "target_key": "C#maj",
                "source_root": "C#",
                "source_mode": "maj",
                "target_root": "C#",
                "target_mode": "maj",
            },
        ]
        preds = {
            "a": {
                "relation": "direct",
                "compatibility": "compatible",
                "pitch_shift_semitones": None,
            },
            "b": {
                "relation": "related",  # breaks +1 rotation of a
                "compatibility": "compatible",
                "pitch_shift_semitones": None,
            },
        }
        scores = theory.score_theory_predictions(cells, preds)
        assert scores["transposition_invariance_violations"] >= 1


class TestAq6NoForcedMatchWithoutEvidence:
    @pytest.mark.parametrize(
        "source_key,target_key",
        [
            (None, "Cmaj"),
            ("Cmaj", None),
            ("C", "Amin"),
            ("Cmaj", "A"),
            ("!!!", "Cmaj"),
        ],
    )
    def test_uncertain_is_valid_fail_closed(
        self, source_key: str | None, target_key: str | None
    ) -> None:
        cell = theory.classify_theory_pair(source_key, target_key)
        assert cell["relation"] == "uncertain"
        assert cell["compatibility"] == "uncertain"
        assert cell["pitch_shift_semitones"] is None
        product = _product_prediction(source_key, target_key)
        assert product["relation"] == "uncertain"
        assert product["compatibility"] == "uncertain"
