from __future__ import annotations

import pytest

from src.arrangement_classifier import ArrangementClassifier
from src.section_signals import SectionSignalsAssembler, build_arrangement_map
from src.structure_v1 import (
    StructureBoundary,
    StructureSection,
    StructureV1Result,
    StructureV1Source,
)


def _result(
    *, missing: tuple[str, ...] = (), inferred: bool = False
) -> StructureV1Result:
    source = StructureV1Source(
        backend="synthetic",
        backend_version="1",
        config={"bar_grid_inference": "beats_grouped_in_fours"} if inferred else {},
    )
    sections = (
        StructureSection("section_1", 0, 200, 0.0, 2.0, 0, 2),
        StructureSection("section_2", 200, 400, 2.0, 4.0, 2, 4),
    )
    values = {
        "bar_energy_rms": (0.1, 0.3, 0.7, 0.9),
        "bar_loudness_delta": (0.0, 0.2, 0.6, 1.0),
        "low_end_share": (0.2, 0.4, 0.6, 0.8),
        "onset_density": (0.1, 0.2, 0.7, 0.8),
        "rhythm_stability": (0.9, 0.8, 0.7, 0.6),
        "timbre_delta": (0.0, 0.2, 0.7, 1.0),
        "spectral_delta": (0.0, 0.3, 0.6, 0.9),
        "self_similarity": (0.9, 0.8, 0.7, 0.6),
        "recurrence": (0.4, 0.5, 0.6, 0.7),
        "novelty": (0.0, 0.2, 0.8, 1.0),
        "neighbor_delta": (0.0, 0.2, 0.7, 1.0),
        "multi_bar_trend": (0.0, 0.2, 0.5, 0.8),
    }
    for name in missing:
        values.pop(name)
    return StructureV1Result(
        "partial" if inferred else "ok",
        (),
        sections,
        {name: "ok" for name in values},
        (),
        source,
        None,
        values,
    )


def test_assembler_preserves_sections_aggregates_evidence_and_is_deterministic() -> (
    None
):
    result = _result()
    first = SectionSignalsAssembler().assemble(result)
    assert first == SectionSignalsAssembler().assemble(result)
    assert len(first) == len(result.sections)
    assert first[0].relative_track_position == 0.25
    assert first[1].relative_track_position == 0.75
    assert first[0].bar_energy_rms == 0.2
    assert first[1].low_end_share == 0.7
    assert {
        "onset_density",
        "rhythm_stability",
        "novelty",
        "recurrence",
        "self_similarity",
    } <= set(first[0].available_signals)
    assert first[0].evidence_completeness == 1.0


def test_missing_feature_is_not_defaulted_and_classifier_stays_unknown() -> None:
    signals = SectionSignalsAssembler().assemble(_result(missing=("low_end_share",)))
    assert "low_end_share" in signals[0].missing_signals
    assert "low_end_share" not in signals[0].available_signals
    classified = ArrangementClassifier().classify_track(
        _result(missing=("low_end_share",)), signals
    )
    assert all(item.automatic_result.role == "unknown" for item in classified.sections)


def test_assembler_preserves_inferred_provenance_and_runtime_wiring() -> None:
    result = _result(inferred=True)
    signals = SectionSignalsAssembler().assemble(result)
    assert signals[0].provenance["bar_grid_inference"] == "beats_grouped_in_fours"
    arrangement = build_arrangement_map(result)
    assert len(arrangement.sections) == len(result.sections)


def test_invalid_feature_alignment_fails_closed_without_boundary_or_role_changes() -> (
    None
):
    result = _result()
    invalid = StructureV1Result(
        result.status,
        result.boundaries,
        result.sections,
        result.feature_status,
        result.notes,
        result.source,
        result.reason_code,
        {"bar_energy_rms": (0.1,)},
    )
    with pytest.raises(ValueError, match="bar feature"):
        SectionSignalsAssembler().assemble(invalid)


@pytest.mark.parametrize("inferred", [False, True])
def test_boundary_local_drop_onset_survives_section_aggregation(
    inferred: bool,
) -> None:
    source = StructureV1Source(
        backend="synthetic",
        backend_version="1",
        config={"bar_grid_inference": "beats_grouped_in_fours"} if inferred else {},
    )
    sections = (
        StructureSection("section_1", 0, 100, 0.0, 1.0, 0, 1),
        StructureSection("section_2", 100, 600, 1.0, 6.0, 1, 6),
    )
    transition = (0.0, 0.95, 0.0, 0.0, 0.0, 0.0)
    values = {
        "bar_energy_rms": (0.1, 0.9, 0.9, 0.9, 0.9, 0.9),
        "bar_loudness_delta": transition,
        "low_end_share": (0.1, 0.9, 0.9, 0.9, 0.9, 0.9),
        "onset_density": (0.1, 0.9, 0.9, 0.9, 0.9, 0.9),
        "rhythm_stability": (0.1, 0.9, 0.9, 0.9, 0.9, 0.9),
        "timbre_delta": transition,
        "spectral_delta": transition,
        "self_similarity": (0.1, 0.9, 0.9, 0.9, 0.9, 0.9),
        "recurrence": (0.1, 0.9, 0.9, 0.9, 0.9, 0.9),
        "novelty": transition,
        "neighbor_delta": transition,
        "multi_bar_trend": (0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    }
    result = StructureV1Result(
        "partial" if inferred else "ok",
        (StructureBoundary(100, 1.0, 1, 1, 0.9, ("novelty",)),),
        sections,
        {name: "ok" for name in values},
        (),
        source,
        None,
        values,
    )

    arrangement = build_arrangement_map(result)

    assert len(arrangement.events) == 1
    event = arrangement.events[0]
    assert event.event == "drop_onset"
    assert event.boundary_id == 100
    assert event.boundary_sec == 1.0
    assert event.status == ("uncertain" if inferred else "available")
    assert arrangement.status == ("uncertain" if inferred else "available")
    assert event.provenance["bar_grid_inference"] == (
        "beats_grouped_in_fours" if inferred else None
    )
    assert arrangement.provenance["bar_grid_inference"] == (
        "beats_grouped_in_fours" if inferred else None
    )
