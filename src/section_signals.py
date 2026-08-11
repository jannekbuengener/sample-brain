"""Runtime bridge from neutral StructureV1 evidence to Arrangement Map inputs."""

from __future__ import annotations

from typing import Mapping

from .arrangement_classifier import (
    ArrangementClassifier,
    ArrangementResult,
    ManualOverride,
    SectionSignals,
)
from .structure_v1 import StructureV1Result

_SIGNALS = (
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
)


class SectionSignalsAssembler:
    """Aggregate public neutral bar evidence; never create boundaries or roles."""

    def assemble(
        self, structure_result: StructureV1Result
    ) -> tuple[SectionSignals, ...]:
        if structure_result.status in {"failed", "no_result"}:
            return ()
        features = structure_result.bar_features
        if not structure_result.sections:
            return ()
        bar_count = max(section.end_bar for section in structure_result.sections)
        if bar_count <= 0:
            raise ValueError("StructureV1 sections must cover at least one bar")
        for name, values in features.items():
            if len(values) != bar_count:
                raise ValueError(f"bar feature {name} does not match section bars")
        output: list[SectionSignals] = []
        for section in structure_result.sections:
            if (
                section.start_bar < 0
                or section.end_bar <= section.start_bar
                or section.end_bar > bar_count
            ):
                raise ValueError(
                    "section bars are outside StructureV1 feature evidence"
                )
            available = tuple(name for name in _SIGNALS if name in features)
            missing = tuple(name for name in _SIGNALS if name not in features)
            values = {
                name: sum(features[name][section.start_bar : section.end_bar])
                / (section.end_bar - section.start_bar)
                for name in available
            }
            output.append(
                SectionSignals(
                    **values,
                    relative_track_position=(section.start_bar + section.end_bar)
                    / (2 * bar_count),
                    evidence_completeness=len(available) / len(_SIGNALS),
                    available_signals=available + ("relative_track_position",),
                    missing_signals=missing,
                    provenance={
                        "component": "section_signals_assembler",
                        "structure_source_ref": "structure_v1",
                        "bar_grid_inference": structure_result.source.config.get(
                            "bar_grid_inference"
                        ),
                    },
                )
            )
        return tuple(output)


def build_arrangement_map(
    structure_result: StructureV1Result,
    *,
    classifier: ArrangementClassifier | None = None,
    manual_overrides: Mapping[str, ManualOverride] | None = None,
) -> ArrangementResult:
    """Run the production StructureV1 -> SectionSignals -> classifier path."""
    signals = SectionSignalsAssembler().assemble(structure_result)
    return (classifier or ArrangementClassifier()).classify_track(
        structure_result, signals, dict(manual_overrides or {})
    )


__all__ = ["SectionSignalsAssembler", "build_arrangement_map"]
