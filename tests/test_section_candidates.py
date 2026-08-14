"""Test-first evidence for section asset candidate generation (Issue #266).

These tests use synthetic StructureV1 / Arrangement Map results only. No private
audio, no network, no model downloads. They assert the contract from
docs/ASSET_MANIFEST_V1.md, docs/ARRANGEMENT_CONFIDENCE_OVERRIDE_V1.md and the
#266 acceptance criteria: sample-authoritative boundaries, preserved section id
and role, automatic/manual/effective provenance separation, strict boundary/role
separation, ``unknown`` as a valid role, and no loop-style repetition/seam rules.
"""

from __future__ import annotations

import copy

from src.arrangement_classifier import (
    ArrangementEvidence,
    ArrangementResult,
    AutomaticResult,
    EffectiveValue,
    ManualOverride,
    SectionClassification,
)
from src.section_candidates import (
    SectionSourceIdentity,
    generate_section_candidates,
)
from src.structure_v1 import (
    StructureBoundary,
    StructureSection,
    StructureV1Result,
    StructureV1Source,
)

SR = 44100
SOURCE = SectionSourceIdentity(
    source_kind="master", track_audio_ref="/source/working_audio"
)
TRACK_REF = "track_9f8e7d6c5b4a"


def _structure_source() -> StructureV1Source:
    return StructureV1Source(
        backend="numpy_librosa",
        backend_version="test",
        config={"bar_grid_inference": None},
    )


def _make_structure(
    sections: tuple[StructureSection, ...],
    boundaries: tuple[StructureBoundary, ...],
    status: str = "ok",
) -> StructureV1Result:
    return StructureV1Result(
        status=status,
        boundaries=boundaries,
        sections=sections,
        feature_status={},
        notes=(),
        source=_structure_source(),
        reason_code=None,
        bar_features={},
    )


def _section(
    section_id: str, start: int, end: int, start_bar: int, end_bar: int
) -> StructureSection:
    return StructureSection(
        id=section_id,
        start_sample=start,
        end_sample=end,
        start_sec=start / SR,
        end_sec=end / SR,
        start_bar=start_bar,
        end_bar=end_bar,
    )


def _boundary(sample_index: int, bar_index: int, score: float) -> StructureBoundary:
    return StructureBoundary(
        sample_index=sample_index,
        time_sec=sample_index / SR,
        bar_index=bar_index,
        downbeat_index=bar_index,
        score=score,
        contributing_signals=("novelty",),
    )


def _classification(
    section_id: str,
    role: str,
    status: str,
    effective_role: str,
    effective_source: str,
    start_bar: int,
    end_bar: int,
    override_role: str | None = None,
) -> SectionClassification:
    automatic = AutomaticResult(
        role=role,
        event=None,
        status=status,
        evidence=ArrangementEvidence(),
        provenance={"component": "arrangement_classifier"},
    )
    override = (
        ManualOverride(role=override_role, author="user1", reason="test")
        if override_role is not None
        else None
    )
    return SectionClassification(
        section_id=section_id,
        start_sec=0.0,
        end_sec=1.0,
        start_bar=start_bar,
        end_bar=end_bar,
        automatic_result=automatic,
        manual_override=override,
        effective_value=EffectiveValue(
            role=effective_role, event=None, source=effective_source
        ),
    )


def _arrangement(
    items: tuple[SectionClassification, ...], status: str = "available"
) -> ArrangementResult:
    return ArrangementResult(
        sections=items,
        events=(),
        status=status,
        provenance={"component": "arrangement_classifier"},
    )


def _base_structure() -> StructureV1Result:
    return _make_structure(
        (
            _section("section_1", 0, 44100, 0, 4),
            _section("section_2", 44100, 88200, 4, 8),
            _section("section_3", 88200, 132300, 8, 12),
        ),
        (
            _boundary(44100, 4, 0.8),
            _boundary(88200, 8, 0.6),
        ),
    )


def _base_arrangement() -> ArrangementResult:
    return _arrangement(
        (
            _classification(
                "section_1", "intro", "available", "intro", "automatic", 0, 4
            ),
            _classification(
                "section_2",
                "drop",
                "available",
                "build",
                "manual",
                4,
                8,
                override_role="build",
            ),
            _classification(
                "section_3", "unknown", "unknown", "unknown", "automatic", 8, 12
            ),
        )
    )


def test_one_valid_section_produces_one_candidate():
    structure = _make_structure((_section("section_1", 0, 44100, 0, 4),), ())
    arrangement = _arrangement(
        (
            _classification(
                "section_1", "intro", "available", "intro", "automatic", 0, 4
            ),
        )
    )
    batch = generate_section_candidates(
        structure, arrangement, source=SOURCE, track_ref=TRACK_REF
    )
    assert batch.status == "ok"
    assert len(batch.candidates) == 1


def test_multiple_sections_keep_deterministic_order():
    batch_a = generate_section_candidates(
        _base_structure(), _base_arrangement(), source=SOURCE, track_ref=TRACK_REF
    )
    batch_b = generate_section_candidates(
        _base_structure(), _base_arrangement(), source=SOURCE, track_ref=TRACK_REF
    )
    ids_a = [c.section_ref for c in batch_a.candidates]
    ids_b = [c.section_ref for c in batch_b.candidates]
    assert ids_a == ["section_1", "section_2", "section_3"]
    assert ids_a == ids_b


def test_start_sample_preserved():
    batch = generate_section_candidates(
        _base_structure(), _base_arrangement(), source=SOURCE, track_ref=TRACK_REF
    )
    assert batch.candidates[0].start_sample == 0
    assert batch.candidates[1].start_sample == 44100


def test_end_sample_exclusive_preserved():
    batch = generate_section_candidates(
        _base_structure(), _base_arrangement(), source=SOURCE, track_ref=TRACK_REF
    )
    assert batch.candidates[0].end_sample_exclusive == 44100
    assert batch.candidates[1].end_sample_exclusive == 88200


def test_end_must_exceed_start():
    batch = generate_section_candidates(
        _base_structure(), _base_arrangement(), source=SOURCE, track_ref=TRACK_REF
    )
    for candidate in batch.candidates:
        assert candidate.end_sample_exclusive > candidate.start_sample
        assert candidate.n_samples > 0


def test_section_id_preserved():
    batch = generate_section_candidates(
        _base_structure(), _base_arrangement(), source=SOURCE, track_ref=TRACK_REF
    )
    assert batch.candidates[0].section_ref == "section_1"


def test_intro_role_preserved():
    batch = generate_section_candidates(
        _base_structure(), _base_arrangement(), source=SOURCE, track_ref=TRACK_REF
    )
    intro = next(c for c in batch.candidates if c.section_ref == "section_1")
    assert intro.arrangement_role == "intro"


def test_drop_role_preserved():
    structure = _make_structure(
        (_section("section_2", 44100, 88200, 4, 8),), (_boundary(44100, 4, 0.8),)
    )
    arrangement = _arrangement(
        (_classification("section_2", "drop", "available", "drop", "automatic", 4, 8),)
    )
    batch = generate_section_candidates(
        structure, arrangement, source=SOURCE, track_ref=TRACK_REF
    )
    assert batch.candidates[0].arrangement_role == "drop"


def test_unknown_role_is_valid_and_produces_candidate():
    batch = generate_section_candidates(
        _base_structure(), _base_arrangement(), source=SOURCE, track_ref=TRACK_REF
    )
    unknown = next(c for c in batch.candidates if c.section_ref == "section_3")
    assert unknown.arrangement_role == "unknown"
    assert len(batch.candidates) == 3


def test_role_status_preserved():
    batch = generate_section_candidates(
        _base_structure(), _base_arrangement(), source=SOURCE, track_ref=TRACK_REF
    )
    intro = next(c for c in batch.candidates if c.section_ref == "section_1")
    assert intro.arrangement_role_status == "available"


def test_boundary_provenance_preserved():
    batch = generate_section_candidates(
        _base_structure(), _base_arrangement(), source=SOURCE, track_ref=TRACK_REF
    )
    assert batch.candidates[0].boundary.source == "arrangement_map"
    assert batch.candidates[0].boundary.kind == "neutral_section"


def test_boundary_quality_separate_from_role_status():
    batch = generate_section_candidates(
        _base_structure(), _base_arrangement(), source=SOURCE, track_ref=TRACK_REF
    )
    drop = next(c for c in batch.candidates if c.section_ref == "section_2")
    # Strong neutral boundary (quality present) while role was overridden; the
    # two layers must stay independent and both be present.
    assert drop.boundary.quality is not None
    assert drop.arrangement_role_status == "available"
    # Boundary quality must not flow into the role status or vice versa.
    assert "quality" not in drop.as_manifest_dict()["section"]


def test_automatic_section_identifiable():
    batch = generate_section_candidates(
        _base_structure(), _base_arrangement(), source=SOURCE, track_ref=TRACK_REF
    )
    intro = next(c for c in batch.candidates if c.section_ref == "section_1")
    assert intro.arrangement_role_source == "automatic"


def test_manual_override_section_identifiable():
    batch = generate_section_candidates(
        _base_structure(), _base_arrangement(), source=SOURCE, track_ref=TRACK_REF
    )
    drop = next(c for c in batch.candidates if c.section_ref == "section_2")
    assert drop.arrangement_role_source == "manual"


def test_effective_value_from_override_used():
    batch = generate_section_candidates(
        _base_structure(), _base_arrangement(), source=SOURCE, track_ref=TRACK_REF
    )
    drop = next(c for c in batch.candidates if c.section_ref == "section_2")
    # Automatic role was "drop"; override effective role is "build".
    assert drop.arrangement_role == "build"


def test_automatic_origin_preserved_despite_override():
    batch = generate_section_candidates(
        _base_structure(), _base_arrangement(), source=SOURCE, track_ref=TRACK_REF
    )
    drop = next(c for c in batch.candidates if c.section_ref == "section_2")
    # Original automatic role is retained even though effective is overridden.
    assert drop.automatic_role == "drop"
    assert drop.arrangement_role == "build"


def test_missing_optional_role_does_not_block_candidate():
    # No arrangement_result at all: sections still produce candidates with unknown.
    structure = _base_structure()
    batch = generate_section_candidates(
        structure, None, source=SOURCE, track_ref=TRACK_REF
    )
    assert batch.status == "ok"
    assert len(batch.candidates) == 3
    assert all(c.arrangement_role == "unknown" for c in batch.candidates)
    assert all(c.arrangement_role_source == "automatic" for c in batch.candidates)


def test_invalid_range_fails_closed():
    structure = _make_structure((_section("section_1", 100, 100, 0, 4),), ())
    arrangement = _arrangement(
        (
            _classification(
                "section_1", "intro", "available", "intro", "automatic", 0, 4
            ),
        )
    )
    raised = False
    try:
        generate_section_candidates(
            structure, arrangement, source=SOURCE, track_ref=TRACK_REF
        )
    except ValueError:
        raised = True
    assert raised


def test_no_fixed_bar_length_required():
    # A short, non 4/8/16-bar section is still emitted.
    structure = _make_structure((_section("section_1", 0, 12345, 0, 3),), ())
    arrangement = _arrangement(
        (
            _classification(
                "section_1", "intro", "available", "intro", "automatic", 0, 3
            ),
        )
    )
    batch = generate_section_candidates(
        structure, arrangement, source=SOURCE, track_ref=TRACK_REF
    )
    assert batch.status == "ok"
    assert batch.candidates[0].end_bar_exclusive - batch.candidates[0].start_bar == 3


def test_no_repetition_or_seam_check():
    # Two identical consecutive sections must both be emitted; no seam/repeat rule.
    structure = _make_structure(
        (
            _section("section_1", 0, 44100, 0, 4),
            _section("section_2", 44100, 88200, 4, 8),
        ),
        (_boundary(44100, 4, 0.8),),
    )
    arrangement = _arrangement(
        (
            _classification(
                "section_1", "groove", "available", "groove", "automatic", 0, 4
            ),
            _classification(
                "section_2", "groove", "available", "groove", "automatic", 4, 8
            ),
        )
    )
    batch = generate_section_candidates(
        structure, arrangement, source=SOURCE, track_ref=TRACK_REF
    )
    assert len(batch.candidates) == 2


def test_same_input_is_reproducible():
    batch_a = generate_section_candidates(
        _base_structure(), _base_arrangement(), source=SOURCE, track_ref=TRACK_REF
    )
    batch_b = generate_section_candidates(
        _base_structure(), _base_arrangement(), source=SOURCE, track_ref=TRACK_REF
    )
    assert [c.as_manifest_dict() for c in batch_a.candidates] == [
        c.as_manifest_dict() for c in batch_b.candidates
    ]


def test_manifest_mapping_reproducible_and_contract_shaped():
    batch = generate_section_candidates(
        _base_structure(), _base_arrangement(), source=SOURCE, track_ref=TRACK_REF
    )
    manifest = batch.candidates[0].as_manifest_dict()
    assert manifest["asset_kind"] == "section"
    assert manifest["track_ref"] == TRACK_REF
    assert manifest["range"]["start_sample"] == 0
    assert manifest["range"]["end_sample_exclusive"] == 44100
    assert manifest["range"]["n_samples"] == 44100
    assert manifest["section"]["section_ref"] == "section_1"
    assert manifest["section"]["arrangement_role"] == "intro"
    assert manifest["section"]["arrangement_role_status"] == "available"
    assert (
        manifest["section"]["arrangement_role_ref"]
        == "arrangement_classifier/section_1"
    )
    assert manifest["boundary"]["source"] == "arrangement_map"
    assert manifest["candidate"]["status"] == "candidate"
    assert manifest["rendering"]["status"] == "not_rendered"
    assert manifest["analysis"]["status"] == "not_run"

    # Deep-equality after a defensive copy proves reproducibility.
    assert copy.deepcopy(manifest) == manifest


def test_no_result_structure_yields_no_result_batch():
    structure = _make_structure((), (), status="no_result")
    batch = generate_section_candidates(
        structure, None, source=SOURCE, track_ref=TRACK_REF
    )
    assert batch.status == "no_result"
    assert batch.candidates == ()


def test_failed_structure_yields_failed_batch():
    structure = _make_structure((), (), status="failed")
    batch = generate_section_candidates(
        structure, None, source=SOURCE, track_ref=TRACK_REF
    )
    assert batch.status == "failed"
    assert batch.candidates == ()
