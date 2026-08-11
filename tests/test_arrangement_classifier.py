from __future__ import annotations

import pytest

from src.arrangement_classifier import (
    ArrangementClassifier,
    ManualOverride,
    SectionSignals,
)
from src.structure_v1 import (
    StructureBoundary,
    StructureSection,
    StructureV1Result,
    StructureV1Source,
)

ALL_SIGNALS = (
    "bar_energy_rms",
    "bar_loudness_delta",
    "low_end_share",
    "onset_density",
    "rhythm_stability",
    "timbre_delta",
    "spectral_delta",
    "self_similarity",
    "recurrence",
    "novelty",
    "neighbor_delta",
    "multi_bar_trend",
    "relative_track_position",
    "evidence_completeness",
)


def _signals(**values: float) -> SectionSignals:
    defaults = dict.fromkeys(ALL_SIGNALS, 0.5)
    defaults.update(values)
    return SectionSignals(
        **{
            key: value
            for key, value in defaults.items()
            if key != "evidence_completeness"
        },
        available_signals=ALL_SIGNALS,
        evidence_completeness=values.get("evidence_completeness", 1.0),
    )


def _section(index: int) -> StructureSection:
    return StructureSection(
        id=f"section_{index}",
        start_sample=index * 100,
        end_sample=(index + 1) * 100,
        start_sec=float(index * 10),
        end_sec=float((index + 1) * 10),
        start_bar=index * 8,
        end_bar=(index + 1) * 8,
    )


@pytest.mark.parametrize(
    ("signals", "expected"),
    [
        (
            _signals(
                relative_track_position=0.05,
                bar_energy_rms=0.1,
                low_end_share=0.1,
                onset_density=0.1,
                multi_bar_trend=0.7,
            ),
            "intro",
        ),
        (
            _signals(
                relative_track_position=0.45,
                bar_energy_rms=0.6,
                low_end_share=0.6,
                onset_density=0.6,
                rhythm_stability=0.9,
                self_similarity=0.9,
                recurrence=0.9,
                novelty=0.05,
                neighbor_delta=0.05,
                multi_bar_trend=0.0,
            ),
            "groove",
        ),
        (
            _signals(
                relative_track_position=0.35,
                bar_energy_rms=0.5,
                bar_loudness_delta=0.8,
                onset_density=0.7,
                timbre_delta=0.7,
                spectral_delta=0.7,
                novelty=0.7,
                neighbor_delta=0.6,
                multi_bar_trend=0.9,
            ),
            "build",
        ),
        (
            _signals(
                relative_track_position=0.55,
                bar_energy_rms=0.95,
                low_end_share=0.95,
                onset_density=0.9,
                rhythm_stability=0.9,
                self_similarity=0.8,
                recurrence=0.8,
                bar_loudness_delta=0.8,
                neighbor_delta=0.8,
            ),
            "drop",
        ),
        (
            _signals(
                relative_track_position=0.65,
                bar_energy_rms=0.1,
                low_end_share=0.1,
                onset_density=0.1,
                rhythm_stability=0.2,
                timbre_delta=0.8,
                spectral_delta=0.7,
                novelty=0.8,
                neighbor_delta=0.8,
                multi_bar_trend=-0.8,
            ),
            "breakdown",
        ),
        (
            _signals(
                relative_track_position=0.95,
                bar_energy_rms=0.15,
                low_end_share=0.2,
                onset_density=0.15,
                rhythm_stability=0.2,
                neighbor_delta=0.7,
                multi_bar_trend=-0.8,
            ),
            "outro",
        ),
    ],
)
def test_classifier_assigns_clear_role_evidence(
    signals: SectionSignals, expected: str
) -> None:
    result = ArrangementClassifier().classify_sections([_section(1)], [signals])[0]
    assert result.automatic_result.role == expected
    assert result.automatic_result.status == "available"


def test_weak_or_contradictory_evidence_is_unknown_without_dummy_score() -> None:
    weak = SectionSignals(available_signals=(), missing_signals=("bar_energy_rms",))
    contradictory = _signals(contradictory_signals=("bar_energy_rms", "low_end_share"))
    results = ArrangementClassifier().classify_sections(
        [_section(1), _section(2)], [weak, contradictory]
    )
    assert [result.automatic_result.role for result in results] == [
        "unknown",
        "unknown",
    ]
    assert [result.automatic_result.status for result in results] == [
        "unknown",
        "unknown",
    ]
    assert all(not result.automatic_result.scores for result in results)


def test_output_is_deterministic_and_includes_machine_readable_contributions() -> None:
    signals = _signals(
        relative_track_position=0.45,
        bar_energy_rms=0.6,
        low_end_share=0.6,
        onset_density=0.6,
        rhythm_stability=0.9,
        self_similarity=0.9,
        recurrence=0.9,
        novelty=0.05,
        neighbor_delta=0.05,
        multi_bar_trend=0.0,
    )
    classifier = ArrangementClassifier()
    first = classifier.classify_sections([_section(1)], [signals])[0]
    second = classifier.classify_sections([_section(1)], [signals])[0]
    assert first == second
    assert first.automatic_result.evidence.contributions
    assert all(
        {"signal", "direction", "strength", "source"} <= set(item)
        for item in first.automatic_result.evidence.contributions
    )
    assert first.automatic_result.provenance["component"] == "arrangement_classifier"
    assert "timestamp_utc" not in first.automatic_result.provenance


def test_override_preserves_automatic_and_effective_layer_is_independent() -> None:
    drop = _signals(
        relative_track_position=0.55,
        bar_energy_rms=0.95,
        low_end_share=0.95,
        onset_density=0.9,
        rhythm_stability=0.9,
        self_similarity=0.8,
        recurrence=0.8,
        bar_loudness_delta=0.8,
        neighbor_delta=0.8,
        novelty=0.9,
        timbre_delta=0.9,
        spectral_delta=0.9,
    )
    section = _section(1)
    override = ManualOverride(role="groove")
    overridden = ArrangementClassifier().classify_sections(
        [section], [drop], {section.id: override}
    )[0]
    automatic = ArrangementClassifier().classify_sections([section], [drop])[0]
    assert overridden.automatic_result == automatic.automatic_result
    assert overridden.effective_value.role == "groove"
    assert overridden.effective_value.event == automatic.automatic_result.event
    assert automatic.effective_value.role == automatic.automatic_result.role
    assert automatic.effective_value.event == automatic.automatic_result.event


def test_drop_onset_is_a_separate_existing_boundary_event() -> None:
    section = _section(1)
    boundary = StructureBoundary(
        sample_index=section.start_sample,
        time_sec=section.start_sec,
        bar_index=section.start_bar,
        downbeat_index=section.start_bar,
        score=0.8,
        contributing_signals=("novelty", "neighbor_delta"),
    )
    signals = _signals(
        relative_track_position=0.55,
        bar_energy_rms=0.95,
        low_end_share=0.95,
        onset_density=0.9,
        rhythm_stability=0.9,
        self_similarity=0.8,
        recurrence=0.8,
        bar_loudness_delta=0.8,
        neighbor_delta=0.9,
        novelty=0.9,
        timbre_delta=0.9,
        spectral_delta=0.9,
    )
    events = ArrangementClassifier().classify_events(
        [boundary], ArrangementClassifier().classify_sections([section], [signals])
    )
    assert len(events) == 1
    assert events[0].event == "drop_onset"
    assert events[0].boundary_id == boundary.sample_index
    assert events[0].role_after == "drop"


def test_invalid_input_fails_closed_and_never_changes_structure_sections() -> None:
    classifier = ArrangementClassifier()
    with pytest.raises(ValueError, match="length mismatch"):
        classifier.classify_sections([_section(1)], [])
    source = StructureV1Source(backend="test", backend_version="1", config={})
    structure = StructureV1Result("failed", (), (), {}, (), source, "TEST_FAILED")
    result = classifier.classify_track(structure, [])
    assert result.status == "failed"
    assert not result.sections and not result.events


def test_arrangement_map_adapter_keeps_neutral_section_bounds_and_never_emits_transition() -> (
    None
):
    section = _section(1)
    source = StructureV1Source(backend="test", backend_version="1", config={})
    structure = StructureV1Result("ok", (), (section,), {}, (), source)
    result = ArrangementClassifier().classify_track(
        structure,
        [
            _signals(
                relative_track_position=0.05,
                bar_energy_rms=0.1,
                low_end_share=0.1,
                onset_density=0.1,
                multi_bar_trend=0.7,
            )
        ],
    )
    payload = result.to_arrangement_map()
    assert payload["sections"][0]["start_sec"] == section.start_sec
    assert payload["sections"][0]["end_sec"] == section.end_sec
    assert all(
        item["automatic_result"]["role"] != "transition" for item in payload["sections"]
    )
