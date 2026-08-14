from __future__ import annotations

from dataclasses import replace

from src.beat_grid import (
    BEAT_GRID_SOURCE_REF,
    BeatGridResult,
    BeatGridSeries,
    BeatGridSource,
)
from src.loop_candidates import (
    DEFAULT_BAR_COUNTS,
    LoopSourceIdentity,
    generate_loop_candidates,
)
from src.structure_v1 import (
    StructureBoundary,
    StructureV1Result,
    StructureV1Source,
)


def _downbeat_result(indices) -> BeatGridResult:
    times_sec = tuple(float(i) / 1000.0 for i in indices)
    downbeats = BeatGridSeries(
        status="ok",
        sample_indices=tuple(indices),
        times_sec=times_sec,
    )
    beats = BeatGridSeries(status="no_result", reason_code="BEATS_UNAVAILABLE")
    source = BeatGridSource(
        component=BEAT_GRID_SOURCE_REF,
        backend="librosa",
        backend_version="0.10.0",
        checkpoint=None,
    )
    return BeatGridResult(
        status="ok",
        bpm=None,
        beats=beats,
        downbeats=downbeats,
        source=source,
    )


def _downbeat_unavailable_result() -> BeatGridResult:
    downbeats = BeatGridSeries(status="no_result", reason_code="DOWNBEATS_UNAVAILABLE")
    beats = BeatGridSeries(status="no_result", reason_code="BEATS_UNAVAILABLE")
    source = BeatGridSource(
        component=BEAT_GRID_SOURCE_REF,
        backend="librosa",
        backend_version="0.10.0",
        checkpoint=None,
    )
    return BeatGridResult(
        status="no_result",
        bpm=None,
        beats=beats,
        downbeats=downbeats,
        source=source,
    )


def _master() -> LoopSourceIdentity:
    return LoopSourceIdentity(
        source_kind="master", track_audio_ref="/source/working_audio"
    )


def _structure_with_boundary(sample_index: int, bar_index: int) -> StructureV1Result:
    boundary = StructureBoundary(
        sample_index=sample_index,
        time_sec=sample_index / 1000.0,
        bar_index=bar_index,
        downbeat_index=bar_index,
        score=0.9,
        contributing_signals=("bar_energy_rms",),
    )
    return StructureV1Result(
        status="ok",
        boundaries=(boundary,),
        sections=(),
        feature_status={},
        notes=(),
        source=StructureV1Source(
            backend="numpy_librosa",
            backend_version="test",
            config={},
        ),
    )


def test_four_bar_candidates_from_real_downbeats():
    indices = [i * 1000 for i in range(24)]
    result = generate_loop_candidates(_master(), beat_grid=_downbeat_result(indices))

    assert result.status == "ok"
    four_bar = [c for c in result.candidates if c.bar_count == 4]
    assert len(four_bar) == 20
    for candidate in four_bar:
        assert candidate.start_sample == indices[candidate.start_bar]
        assert (
            candidate.end_sample_exclusive
            == indices[candidate.start_bar + candidate.bar_count]
        )
        assert candidate.end_sample_exclusive in indices
        assert (
            candidate.n_samples
            == candidate.end_sample_exclusive - candidate.start_sample
        )


def test_eight_bar_candidates_from_real_downbeats():
    indices = [i * 1000 for i in range(24)]
    result = generate_loop_candidates(_master(), beat_grid=_downbeat_result(indices))

    eight_bar = [c for c in result.candidates if c.bar_count == 8]
    assert len(eight_bar) == 16
    for candidate in eight_bar:
        assert candidate.bar_count == 8
        assert candidate.end_bar_exclusive == candidate.start_bar + 8


def test_sixteen_bar_candidates_from_real_downbeats():
    indices = [i * 1000 for i in range(24)]
    result = generate_loop_candidates(_master(), beat_grid=_downbeat_result(indices))

    sixteen_bar = [c for c in result.candidates if c.bar_count == 16]
    assert len(sixteen_bar) == 8
    for candidate in sixteen_bar:
        assert candidate.bar_count == 16
        assert candidate.end_sample_exclusive == indices[candidate.start_bar + 16]


def test_bar_count_is_exactly_four_eight_or_sixteen():
    indices = [i * 1000 for i in range(24)]
    result = generate_loop_candidates(_master(), beat_grid=_downbeat_result(indices))

    assert {c.bar_count for c in result.candidates} == {4, 8, 16}
    assert result.bar_counts == (4, 8, 16)


def test_start_and_end_bar_semantics():
    indices = [i * 1000 for i in range(24)]
    result = generate_loop_candidates(_master(), beat_grid=_downbeat_result(indices))

    for candidate in result.candidates:
        assert candidate.start_bar >= 0
        assert candidate.end_bar_exclusive == candidate.start_bar + candidate.bar_count
        assert candidate.end_bar_exclusive > candidate.start_bar


def test_deterministic_order_and_reproducibility():
    indices = [i * 1000 for i in range(24)]
    first = generate_loop_candidates(_master(), beat_grid=_downbeat_result(indices))
    second = generate_loop_candidates(_master(), beat_grid=_downbeat_result(indices))

    assert first == second
    assert [c.start_bar for c in first.candidates if c.bar_count == 4] == list(
        range(20)
    )


def test_missing_downbeats_produce_no_approximated_candidates():
    result = generate_loop_candidates(
        _master(), beat_grid=_downbeat_unavailable_result()
    )

    assert result.status == "no_result"
    assert result.reason_code == "DOWNBEATS_UNAVAILABLE"
    assert result.candidates == ()


def test_too_few_downbeats_produce_no_shortened_candidates():
    indices = [i * 1000 for i in range(3)]
    result = generate_loop_candidates(_master(), beat_grid=_downbeat_result(indices))

    assert result.status == "no_result"
    assert result.reason_code == "INSUFFICIENT_DOWNBEATS"
    assert result.candidates == ()


def test_beats_and_bpm_do_not_replace_missing_downbeats():
    bg = _downbeat_unavailable_result()
    bg = replace(
        bg,
        bpm=120.0,
        beats=BeatGridSeries(
            status="ok",
            sample_indices=(0, 500, 1000, 1500),
            times_sec=(0.0, 0.5, 1.0, 1.5),
        ),
    )

    result = generate_loop_candidates(_master(), beat_grid=bg)

    assert result.status == "no_result"
    assert result.candidates == ()


def test_non_monotonic_downbeats_fail_closed():
    indices = [0, 1000, 500, 2000]
    result = generate_loop_candidates(_master(), downbeat_sample_indices=indices)

    assert result.status == "failed"
    assert result.reason_code == "INVALID_DOWNBEAT_GRID"
    assert result.candidates == ()


def test_section_boundary_inside_candidate_is_marked_crossing():
    indices = [i * 1000 for i in range(8)]
    structure = _structure_with_boundary(sample_index=3500, bar_index=3)
    result = generate_loop_candidates(
        _master(),
        beat_grid=_downbeat_result(indices),
        structure=structure,
    )

    candidate = next(
        c for c in result.candidates if c.start_bar == 2 and c.bar_count == 4
    )
    assert candidate.boundary.section_crossing.crosses is True
    assert candidate.boundary.section_crossing.crossed_sample_indices == (3500,)
    # crossing is context only, candidate is still produced
    assert candidate.candidate_status == "candidate"


def test_boundary_at_start_or_end_is_not_internal_crossing():
    indices = [i * 1000 for i in range(8)]
    structure_start = _structure_with_boundary(sample_index=2000, bar_index=2)
    structure_end = _structure_with_boundary(sample_index=6000, bar_index=6)
    result = generate_loop_candidates(
        _master(),
        beat_grid=_downbeat_result(indices),
        structure=structure_start,
    )
    candidate_start = next(
        c for c in result.candidates if c.start_bar == 2 and c.bar_count == 4
    )
    assert candidate_start.boundary.section_crossing.crosses is False

    result_end = generate_loop_candidates(
        _master(),
        beat_grid=_downbeat_result(indices),
        structure=structure_end,
    )
    candidate_end = next(
        c for c in result_end.candidates if c.start_bar == 2 and c.bar_count == 4
    )
    assert candidate_end.boundary.section_crossing.crosses is False


def test_source_identity_master_preserved():
    indices = [i * 1000 for i in range(8)]
    result = generate_loop_candidates(_master(), beat_grid=_downbeat_result(indices))

    for candidate in result.candidates:
        assert candidate.source.source_kind == "master"
        assert candidate.source.track_audio_ref == "/source/working_audio"


def test_source_identity_stem_preserved():
    stem = LoopSourceIdentity(
        source_kind="stem", stem_id="stem_drums_01", stem_ref="stemmanifest_drums_01"
    )
    indices = [i * 1000 for i in range(8)]
    result = generate_loop_candidates(stem, beat_grid=_downbeat_result(indices))

    for candidate in result.candidates:
        assert candidate.source.source_kind == "stem"
        assert candidate.source.stem_id == "stem_drums_01"
        assert candidate.source.stem_ref == "stemmanifest_drums_01"


def test_source_identity_producer_group_preserved():
    pg = LoopSourceIdentity(
        source_kind="producer_group",
        producer_group_id="pg_bridge_fx",
        producer_group_ref="producergroup_bridge_fx",
    )
    indices = [i * 1000 for i in range(8)]
    result = generate_loop_candidates(pg, beat_grid=_downbeat_result(indices))

    for candidate in result.candidates:
        assert candidate.source.source_kind == "producer_group"
        assert candidate.source.producer_group_id == "pg_bridge_fx"
        assert candidate.source.producer_group_ref == "producergroup_bridge_fx"


def test_candidate_maps_to_asset_manifest_v1_fields():
    indices = [i * 1000 for i in range(8)]
    result = generate_loop_candidates(_master(), beat_grid=_downbeat_result(indices))
    candidate = result.candidates[0]
    manifest = candidate.as_manifest_dict()

    assert manifest["asset_kind"] == "loop"
    assert manifest["range"]["start_sample"] == candidate.start_sample
    assert manifest["range"]["end_sample_exclusive"] == candidate.end_sample_exclusive
    assert manifest["range"]["n_samples"] == candidate.n_samples
    assert manifest["loop"]["bars"]["bar_count"] == candidate.bar_count
    assert manifest["loop"]["downbeat_start_sample"] == candidate.start_sample
    assert manifest["boundary"]["source"] == BEAT_GRID_SOURCE_REF
    assert manifest["candidate"]["status"] == "candidate"
    assert manifest["rendering"]["status"] == "not_rendered"


def test_no_quality_score_preempted():
    indices = [i * 1000 for i in range(8)]
    result = generate_loop_candidates(_master(), beat_grid=_downbeat_result(indices))
    manifest = result.candidates[0].as_manifest_dict()

    assert "score_components" not in manifest["candidate"]
    assert manifest["candidate"]["excluded"] is False


def test_default_bar_counts_constant():
    assert DEFAULT_BAR_COUNTS == (4, 8, 16)
