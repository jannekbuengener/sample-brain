"""Frozen #672 contract tests for V2 Harmonic Match consumer activation."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from src.workbench import WorkbenchApp
from src.workbench_controller import WorkbenchKeyAnalysisClaim, WorkbenchRow
from src.workbench_harmony import (
    HarmonicMatchLibraryController,
    HarmonyRelation,
    find_harmony_matches,
    rate_harmony,
)
from src.workbench_qml import Screen1QmlInteractionAdapter


def _claim(
    *,
    key: str = "Cmaj",
    mode: str | None = "maj",
    valid: bool = True,
    contract_version: int | None = 2,
    matching_eligible: bool = False,
) -> WorkbenchKeyAnalysisClaim:
    return WorkbenchKeyAnalysisClaim(
        key=key,
        mode=mode,
        contract_version=contract_version,
        valid=valid,
        matching_eligible=matching_eligible,
        root_evidence_kind="joint_24_profile_pearson",
        mode_evidence_kind="third_contrast",
    )


def _row(
    name: str,
    *,
    key: str | None = None,
    claim: WorkbenchKeyAnalysisClaim | None = None,
    bpm: float | None = 128.0,
) -> WorkbenchRow:
    return WorkbenchRow(
        display_name=name,
        relative_path=f"{name}.wav",
        path=f"/synthetic/{name}.wav",
        bpm=bpm,
        key=key,
        key_conf=0.9 if key else None,
        loudness=-18.0,
        brightness=2200.0,
        sample_class="loop",
        pred_type="Synth Loop",
        status="ok",
        key_analysis_claim=claim,
    )


def test_v2_modeful_pair_uses_existing_relation_logic_as_direct():
    reference = _row("reference", claim=_claim(key="Cmaj", mode="maj"))
    candidate = _row("candidate", claim=_claim(key="Cmaj", mode="maj"))

    result = rate_harmony(reference, candidate)

    assert reference.key is None
    assert candidate.key is None
    assert reference.key_analysis_claim is not None
    assert reference.key_analysis_claim.matching_eligible is False
    assert result.relation is HarmonyRelation.DIRECT


def test_v1_reference_and_v2_candidate_use_existing_related_relation():
    reference = _row("reference", key="Cmaj")
    candidate = _row("candidate", claim=_claim(key="Amin", mode="min"))

    result = rate_harmony(reference, candidate)

    assert result.relation is HarmonyRelation.RELATED


def test_v2_reference_and_v1_candidate_use_existing_related_relation():
    reference = _row("reference", claim=_claim(key="Cmaj", mode="maj"))
    candidate = _row("candidate", key="Gmaj")

    result = rate_harmony(reference, candidate)

    assert result.relation is HarmonyRelation.RELATED


def test_v2_root_only_candidate_remains_uncertain():
    reference = _row("reference", key="Cmaj")
    candidate = _row("candidate", claim=_claim(key="G", mode=None))

    result = rate_harmony(reference, candidate)

    assert result.relation is HarmonyRelation.UNCERTAIN


def test_controller_accepts_modeful_v2_anchor():
    anchor = _row("anchor", claim=_claim(key="Cmaj", mode="maj"))
    candidate = _row("candidate", key="Gmaj")
    calls: list[tuple[WorkbenchRow, tuple[WorkbenchRow, ...]]] = []

    def finder(reference, candidates, **_kwargs):
        calls.append((reference, tuple(candidates)))
        return [], None

    controller = HarmonicMatchLibraryController(finder=finder)
    controller.set_anchor(anchor, [anchor, candidate])

    assert calls == [(anchor, (candidate,))]
    assert controller.anchor is anchor


def test_controller_rejects_root_only_v2_anchor():
    anchor = _row("anchor", claim=_claim(key="G", mode=None))
    calls: list[str] = []
    controller = HarmonicMatchLibraryController(
        finder=lambda *_args, **_kwargs: calls.append("finder") or ([], None)
    )

    controller.set_anchor(anchor, [_row("candidate", key="Gmaj")])

    assert calls == []
    assert "key" in controller.status.casefold()


def test_harmonic_query_matches_effective_v2_key_text():
    reference = _row("reference", key="Cmaj")
    candidate = _row("candidate", claim=_claim(key="Amin", mode="min"))

    suggestions, status = find_harmony_matches(
        reference,
        [reference, candidate],
        query="amin",
    )

    assert status is None
    assert [item.row.path for item in suggestions] == [candidate.path]


def test_tk_harmonic_fingerprint_tracks_effective_v2_key():
    row = _row("candidate", claim=_claim(key="Cmaj", mode="maj"))

    fingerprint = WorkbenchApp._harmonic_match_row_fingerprint(row)
    changed = WorkbenchApp._harmonic_match_row_fingerprint(
        replace(row, key_analysis_claim=_claim(key="Dmin", mode="min"))
    )

    assert fingerprint[1] == "Cmaj"
    assert changed[1] == "Dmin"
    assert changed != fingerprint
    assert row.key is None


def test_qml_harmonic_fingerprint_tracks_effective_v2_key():
    row = _row("candidate", claim=_claim(key="Cmaj", mode="maj"))

    fingerprint = Screen1QmlInteractionAdapter._harmonic_match_row_fingerprint(row)
    changed = Screen1QmlInteractionAdapter._harmonic_match_row_fingerprint(
        replace(row, key_analysis_claim=_claim(key="Dmin", mode="min"))
    )

    assert fingerprint[1] == "Cmaj"
    assert changed[1] == "Dmin"
    assert changed != fingerprint
    assert row.key is None


def test_tk_harmonic_anchor_label_uses_effective_v2_key_only_locally():
    anchor = _row("anchor", claim=_claim(key="Cmaj", mode="maj"))
    captured: dict[str, str] = {}
    app = WorkbenchApp.__new__(WorkbenchApp)
    app._harmonic_match_anchor_var = SimpleNamespace(
        set=lambda value: captured.__setitem__("anchor", value)
    )
    app._harmonic_match_status_var = SimpleNamespace(set=lambda _value: None)
    app._harmonic_match_controller = SimpleNamespace(status="ok", results=())
    app._apply_harmonic_match_layout = lambda **_kwargs: None
    app._harmonic_match_btn = SimpleNamespace(configure=lambda **_kwargs: None)
    app._render_harmonic_match_rows = lambda: None
    app._harmonic_match_canvas = SimpleNamespace(focus_set=lambda: None)
    app._set_status = lambda *_args, **_kwargs: None

    app._show_harmonic_match_library(anchor)

    assert "Cmaj" in captured["anchor"]
    assert anchor.key is None


def test_qml_harmonic_anchor_label_uses_effective_v2_key_only_locally():
    anchor = _row("anchor", claim=_claim(key="Cmaj", mode="maj"))
    adapter = Screen1QmlInteractionAdapter.__new__(Screen1QmlInteractionAdapter)
    adapter.harmonic_match_open = True
    adapter.harmony_controller = SimpleNamespace(results=(), status="ok")
    adapter.view_model = SimpleNamespace(
        harmony_rows=(),
        harmony_anchor="",
        harmony_status="",
    )

    adapter._project_harmonic_match(anchor)

    assert "Cmaj" in adapter.view_model.harmony_anchor
    assert anchor.key is None
