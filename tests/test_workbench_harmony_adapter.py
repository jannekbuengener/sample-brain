"""Frozen Product-adapter contracts for Analysis Extraction Slice 1."""
from dataclasses import replace

import pytest

from src import harmony
from src import workbench_harmony as product
from src.workbench_controller import WorkbenchKeyAnalysisClaim, WorkbenchRow


def _claim(**overrides):
    values = dict(key="Cmaj", mode="maj", contract_version=2, valid=True,
                  matching_eligible=False, root_evidence_kind=None, mode_evidence_kind=None)
    values.update(overrides)
    return WorkbenchKeyAnalysisClaim(**values)


def _row(name, *, key="Cmaj", claim=None):
    return WorkbenchRow(display_name=name, relative_path=f"{name}.wav", path=f"/synthetic/{name}.wav",
                        bpm=128.0, key=key, key_conf=None, loudness=None, brightness=None,
                        sample_class=None, pred_type="kick", status="ok", key_analysis_claim=claim)


def test_relation_result_and_relation_function_are_canonical_reexports():
    assert product.HarmonyRelation is harmony.HarmonyRelation
    assert product.HarmonySuggestion is harmony.HarmonySuggestion
    assert product.determine_relation is harmony.determine_relation


@pytest.mark.parametrize("key,claim,effective,relation", [
    ("Dmaj", _claim(), "Cmaj", "direct"),
    ("Cmaj", None, "Cmaj", "direct"),
    ("Gmaj", _claim(key="malformed"), "Gmaj", "related"),
    ("Gmaj", _claim(key="Cmaj", mode="min"), "Gmaj", "related"),
    (None, _claim(key="C", mode=None), None, "uncertain"),
    ("C", None, "C", "uncertain"),
    (None, None, None, "uncertain"),
])
def test_product_key_resolution_projects_effective_key_without_mutation(monkeypatch, key, claim, effective, relation):
    ref = _row("ref")
    candidate = _row("cand", key=key, claim=claim)
    seen = []
    original = harmony.rate_harmony

    def spy(reference, projected, key_override=None):
        assert isinstance(reference, harmony.HarmonyInput)
        assert isinstance(projected, harmony.HarmonyInput)
        seen.append(projected.key)
        return original(reference, projected, key_override=key_override)

    monkeypatch.setattr(harmony, "rate_harmony", spy)
    result = product.rate_harmony(ref, candidate)
    assert seen == [effective]
    assert result.relation.value == relation
    assert result.row is candidate
    assert candidate.key == key
    assert candidate.key_analysis_claim is claim


def test_finder_delegates_and_preserves_distinct_original_rows_with_equal_values(monkeypatch):
    first = _row("same")
    second = replace(first)
    assert first == second and first is not second
    projected_ids = []
    original = harmony.find_harmony_matches

    def spy(reference, candidates, **kwargs):
        assert isinstance(reference, harmony.HarmonyInput)
        assert all(isinstance(row, harmony.HarmonyInput) for row in candidates)
        projected_ids.extend(id(row) for row in candidates)
        return original(reference, candidates, **kwargs)

    monkeypatch.setattr(harmony, "find_harmony_matches", spy)
    matches, error = product.find_harmony_matches(_row("ref"), [first, second])
    assert error is None
    assert len(matches) == 2
    assert len(set(projected_ids)) == 2
    assert matches[0].row is first
    assert matches[1].row is second
    matches[0].row = _row("rebound")
    assert matches[0].row.display_name == "rebound"
    assert matches[1].row is second


def test_finder_queries_effective_v2_key_and_override_stays_local():
    ref = _row("ref", key="Gmaj")
    candidate = _row("cand", key=None, claim=_claim(key="Fmaj"))
    matches, error = product.find_harmony_matches(ref, [candidate], query="Fmaj", key_override="Fmaj")
    assert error is None
    assert len(matches) == 1
    assert matches[0].row is candidate
    assert matches[0].relation is harmony.HarmonyRelation.DIRECT
    assert ref.key == "Gmaj"
    assert candidate.key is None
