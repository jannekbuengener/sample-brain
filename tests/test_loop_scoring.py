from __future__ import annotations

import numpy as np

from src.loop_candidates import (
    LoopSourceIdentity,
    generate_loop_candidates,
)
from src.loop_scoring import (
    EDGE_SILENCE_RISK,
    ENERGY_DISTRIBUTION,
    GROOVE_STABILITY,
    INTERNAL_STABILITY,
    REJECT_EDGE_SILENCE,
    REJECT_SEAM_DISCONTINUITY,
    SEAM_CONTINUITY,
    TRANSITION_BLEED_RISK,
    VOCAL_FX_EDGE_RISK,
    LoopEdgeRiskEvidence,
    LoopScoringThresholds,
    default_loop_scoring_config,
    score_loop_candidate,
)

SR = 44100
BAR_LEN = 4410  # 0.1 s per bar at 44.1 kHz


def _sine_segment(length: int, freq: float, amp: float = 0.3) -> np.ndarray:
    t = np.arange(length, dtype=np.float64)
    return (amp * np.sin(2 * np.pi * freq * t / SR)).astype(np.float32)


def _bar_signal(samples_per_bar: int, energy: float, onset_bins) -> np.ndarray:
    tone = _sine_segment(samples_per_bar, freq=220.0, amp=energy)
    seg = tone.copy()
    active = [i for i, v in enumerate(onset_bins) if v]
    if active:
        burst_len = max(1, samples_per_bar // 64)
        for bin_idx in active:
            center = int((bin_idx + 0.5) * samples_per_bar / len(onset_bins))
            start = max(0, center - burst_len // 2)
            end = min(samples_per_bar, start + burst_len)
            env = np.hanning(max(1, end - start)).astype(np.float32)
            seg[start:end] += 0.5 * energy * env
    return seg.astype(np.float32)


def _build_waveform(
    bar_count: int,
    *,
    energies,
    onset_patterns,
    start_edge=None,
    end_edge=None,
):
    parts = []
    for b in range(bar_count):
        parts.append(_bar_signal(BAR_LEN, energies[b], onset_patterns[b]))
    wf = np.concatenate(parts).astype(np.float32)
    if start_edge is not None:
        wf[: len(start_edge)] = np.asarray(start_edge, dtype=np.float32)
    if end_edge is not None:
        wf[-len(end_edge) :] = np.asarray(end_edge, dtype=np.float32)
    return wf


def _stable_pattern():
    return (1, 0, 0, 1, 0, 0, 1, 0)


def _alt_pattern():
    return (0, 1, 1, 0, 1, 1, 0, 1)


def _master():
    return LoopSourceIdentity(
        source_kind="master", track_audio_ref="/source/working_audio"
    )


def _downbeat_result(indices):
    from src.beat_grid import (
        BEAT_GRID_SOURCE_REF,
        BeatGridResult,
        BeatGridSeries,
        BeatGridSource,
    )

    times = tuple(float(i) / SR for i in indices)
    downbeats = BeatGridSeries(
        status="ok", sample_indices=tuple(indices), times_sec=times
    )
    beats = BeatGridSeries(status="no_result", reason_code="BEATS_UNAVAILABLE")
    source = BeatGridSource(
        component=BEAT_GRID_SOURCE_REF,
        backend="librosa",
        backend_version="0.10.0",
        checkpoint=None,
    )
    return BeatGridResult(
        status="ok", bpm=None, beats=beats, downbeats=downbeats, source=source
    )


def _candidates_for(bar_count: int, structure=None, source=None):
    indices = [i * BAR_LEN for i in range(24)]
    result = generate_loop_candidates(
        source if source is not None else _master(),
        beat_grid=_downbeat_result(indices),
        structure=structure,
    )
    chosen = [
        c for c in result.candidates if c.bar_count == bar_count and c.start_bar == 0
    ]
    assert chosen, "expected at least one candidate"
    return chosen[0]


def _structure_crossing(sample_index: int, bar_index: int):
    from src.structure_v1 import (
        StructureBoundary,
        StructureV1Result,
        StructureV1Source,
    )

    boundary = StructureBoundary(
        sample_index=sample_index,
        time_sec=sample_index / SR,
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
            backend="numpy_librosa", backend_version="t", config={}
        ),
    )


# --- 1. determinism -------------------------------------------------------


def test_same_input_same_config_reproducible():
    candidate = _candidates_for(4)
    wf = _build_waveform(4, energies=[0.3] * 4, onset_patterns=[_stable_pattern()] * 4)
    cfg = default_loop_scoring_config()
    first = score_loop_candidate(candidate, wf, sample_rate=SR, config=cfg)
    second = score_loop_candidate(candidate, wf, sample_rate=SR, config=cfg)
    assert first == second


def test_score_components_remain_separated_and_traceable():
    candidate = _candidates_for(8)
    wf = _build_waveform(8, energies=[0.3] * 8, onset_patterns=[_stable_pattern()] * 8)
    result = score_loop_candidate(candidate, wf, sample_rate=SR)
    names = set(result.score_components.keys())
    assert {
        SEAM_CONTINUITY,
        INTERNAL_STABILITY,
        GROOVE_STABILITY,
        ENERGY_DISTRIBUTION,
        EDGE_SILENCE_RISK,
        TRANSITION_BLEED_RISK,
        VOCAL_FX_EDGE_RISK,
    } <= names
    for comp in result.score_components.values():
        assert comp.name
        assert comp.meaning
        assert comp.value_range is not None


# --- 2. seam --------------------------------------------------------------


def test_seam_evaluated_as_separate_component():
    candidate = _candidates_for(4)
    edge = _sine_segment(256, freq=220.0, amp=0.3)
    wf = _build_waveform(
        4,
        energies=[0.3] * 4,
        onset_patterns=[_stable_pattern()] * 4,
        start_edge=edge,
        end_edge=edge,
    )
    result = score_loop_candidate(candidate, wf, sample_rate=SR)
    assert SEAM_CONTINUITY in result.score_components
    assert result.score_components[SEAM_CONTINUITY].status == "ok"
    assert 0.0 <= result.score_components[SEAM_CONTINUITY].value <= 1.0


def test_clearly_bad_seam_triggers_hard_reject():
    candidate = _candidates_for(4)
    start_edge = _sine_segment(256, freq=220.0, amp=0.05)
    end_edge = np.full(256, 0.9, dtype=np.float32)  # discontinuity click
    wf = _build_waveform(
        4,
        energies=[0.3] * 4,
        onset_patterns=[_stable_pattern()] * 4,
        start_edge=start_edge,
        end_edge=end_edge,
    )
    result = score_loop_candidate(candidate, wf, sample_rate=SR)
    assert result.hard_rejected is True
    assert REJECT_SEAM_DISCONTINUITY in result.reject_reasons


def test_good_seam_not_falsely_rejected():
    candidate = _candidates_for(4)
    edge = np.full(256, 0.3, dtype=np.float32)  # identical continuous edges
    wf = _build_waveform(
        4,
        energies=[0.3] * 4,
        onset_patterns=[_stable_pattern()] * 4,
        start_edge=edge,
        end_edge=edge,
    )
    result = score_loop_candidate(candidate, wf, sample_rate=SR)
    assert result.hard_rejected is False
    assert result.score_components[SEAM_CONTINUITY].value > 0.6


# --- 3. internal / groove / energy ---------------------------------------


def test_internal_stability_distinguishes_stable_from_changing():
    stable = _build_waveform(
        8, energies=[0.3] * 8, onset_patterns=[_stable_pattern()] * 8
    )
    changing = _build_waveform(
        8,
        energies=[0.05, 0.9] * 4,
        onset_patterns=[_stable_pattern(), _alt_pattern()] * 4,
    )
    cand = _candidates_for(8)
    stable_res = score_loop_candidate(cand, stable, sample_rate=SR)
    changing_res = score_loop_candidate(cand, changing, sample_rate=SR)
    assert (
        stable_res.score_components[INTERNAL_STABILITY].value
        > changing_res.score_components[INTERNAL_STABILITY].value
    )


def test_groove_stability_separately_visible():
    stable = _build_waveform(
        8, energies=[0.3] * 8, onset_patterns=[_stable_pattern()] * 8
    )
    changing = _build_waveform(
        8, energies=[0.3] * 8, onset_patterns=[_stable_pattern(), _alt_pattern()] * 4
    )
    cand = _candidates_for(8)
    stable_res = score_loop_candidate(cand, stable, sample_rate=SR)
    changing_res = score_loop_candidate(cand, changing, sample_rate=SR)
    assert GROOVE_STABILITY in stable_res.score_components
    assert (
        stable_res.score_components[GROOVE_STABILITY].value
        >= changing_res.score_components[GROOVE_STABILITY].value
    )


def test_energy_distribution_separately_visible():
    cand = _candidates_for(8)
    flat = _build_waveform(
        8, energies=[0.3] * 8, onset_patterns=[_stable_pattern()] * 8
    )
    spiky = _build_waveform(
        8, energies=[0.02, 0.6] * 4, onset_patterns=[_stable_pattern()] * 8
    )
    flat_res = score_loop_candidate(cand, flat, sample_rate=SR)
    spiky_res = score_loop_candidate(cand, spiky, sample_rate=SR)
    assert ENERGY_DISTRIBUTION in flat_res.score_components
    assert (
        spiky_res.score_components[ENERGY_DISTRIBUTION].value
        != flat_res.score_components[ENERGY_DISTRIBUTION].value
    )


# --- 4. edge silence ------------------------------------------------------


def test_edge_silence_at_start_is_visible_and_rejected():
    cand = _candidates_for(4)
    silent = np.zeros(256, dtype=np.float32)
    tone = _sine_segment(256, freq=220.0, amp=0.3)
    wf = _build_waveform(
        4,
        energies=[0.3] * 4,
        onset_patterns=[_stable_pattern()] * 4,
        start_edge=silent,
        end_edge=tone,
    )
    result = score_loop_candidate(cand, wf, sample_rate=SR)
    assert result.score_components[EDGE_SILENCE_RISK].value > 0.5
    assert result.hard_rejected is True
    assert REJECT_EDGE_SILENCE in result.reject_reasons


def test_near_silence_edge_detected():
    cand = _candidates_for(4)
    near = np.full(256, 1e-5, dtype=np.float32)
    tone = _sine_segment(256, freq=220.0, amp=0.3)
    wf = _build_waveform(
        4,
        energies=[0.3] * 4,
        onset_patterns=[_stable_pattern()] * 4,
        start_edge=near,
        end_edge=tone,
    )
    result = score_loop_candidate(cand, wf, sample_rate=SR)
    assert result.hard_rejected is True
    assert REJECT_EDGE_SILENCE in result.reject_reasons


# --- 5. transition bleed --------------------------------------------------


def test_section_crossing_marks_transition_bleed_risk():
    indices = [i * BAR_LEN for i in range(8)]
    # candidate start_bar==2 spans indices[2]..indices[6] => 8820..26460 samples
    structure = _structure_crossing(sample_index=15000, bar_index=3)
    result = generate_loop_candidates(
        _master(), beat_grid=_downbeat_result(indices), structure=structure
    )
    crossing_candidate = next(
        c for c in result.candidates if c.start_bar == 2 and c.bar_count == 4
    )
    assert crossing_candidate.boundary.section_crossing.crosses is True
    wf = _build_waveform(4, energies=[0.3] * 4, onset_patterns=[_stable_pattern()] * 4)
    score = score_loop_candidate(crossing_candidate, wf, sample_rate=SR)
    assert score.score_components[TRANSITION_BLEED_RISK].value == 1.0
    assert score.score_components[TRANSITION_BLEED_RISK].status == "ok"


def test_section_crossing_alone_does_not_hard_reject():
    indices = [i * BAR_LEN for i in range(8)]
    structure = _structure_crossing(sample_index=15000, bar_index=3)
    result = generate_loop_candidates(
        _master(), beat_grid=_downbeat_result(indices), structure=structure
    )
    crossing_candidate = next(
        c for c in result.candidates if c.start_bar == 2 and c.bar_count == 4
    )
    wf = _build_waveform(4, energies=[0.3] * 4, onset_patterns=[_stable_pattern()] * 4)
    score = score_loop_candidate(crossing_candidate, wf, sample_rate=SR)
    assert score.hard_rejected is False
    assert score.reject_reasons == ()


# --- 6. vocal / fx evidence -----------------------------------------------


def test_vocal_fx_risk_not_invented_without_evidence():
    cand = _candidates_for(4)
    wf = _build_waveform(4, energies=[0.3] * 4, onset_patterns=[_stable_pattern()] * 4)
    result = score_loop_candidate(cand, wf, sample_rate=SR)
    comp = result.score_components[VOCAL_FX_EDGE_RISK]
    assert comp.status == "not_evaluated"
    assert comp.value is None


def test_explicit_vocal_fx_evidence_is_visible():
    cand = _candidates_for(4)
    wf = _build_waveform(4, energies=[0.3] * 4, onset_patterns=[_stable_pattern()] * 4)
    evidence = [
        LoopEdgeRiskEvidence(
            side="start",
            kind="vocal",
            evidence_ref="manual_review_001",
            note="breath at head",
        )
    ]
    result = score_loop_candidate(cand, wf, sample_rate=SR, vocal_fx_evidence=evidence)
    comp = result.score_components[VOCAL_FX_EDGE_RISK]
    assert comp.status == "ok"
    assert comp.value == 1.0


# --- 7. source kinds ------------------------------------------------------


def test_source_identity_master_preserved():
    cand = _candidates_for(4)
    wf = _build_waveform(4, energies=[0.3] * 4, onset_patterns=[_stable_pattern()] * 4)
    result = score_loop_candidate(cand, wf, sample_rate=SR)
    assert result.source_identity["source_kind"] == "master"
    assert result.source_identity["track_audio_ref"] == "/source/working_audio"


def test_source_identity_stem_preserved():
    stem = LoopSourceIdentity(
        source_kind="stem", stem_id="stem_drums_01", stem_ref="stemmanifest_drums_01"
    )
    indices = [i * BAR_LEN for i in range(24)]
    cand = generate_loop_candidates(
        stem, beat_grid=_downbeat_result(indices)
    ).candidates[0]
    wf = _build_waveform(4, energies=[0.3] * 4, onset_patterns=[_stable_pattern()] * 4)
    result = score_loop_candidate(cand, wf, sample_rate=SR)
    assert result.source_identity["source_kind"] == "stem"
    assert result.source_identity["stem_id"] == "stem_drums_01"


def test_source_identity_producer_group_preserved():
    pg = LoopSourceIdentity(
        source_kind="producer_group",
        producer_group_id="pg_bridge_fx",
        producer_group_ref="producergroup_bridge_fx",
    )
    indices = [i * BAR_LEN for i in range(24)]
    cand = generate_loop_candidates(pg, beat_grid=_downbeat_result(indices)).candidates[
        0
    ]
    wf = _build_waveform(4, energies=[0.3] * 4, onset_patterns=[_stable_pattern()] * 4)
    result = score_loop_candidate(cand, wf, sample_rate=SR)
    assert result.source_identity["source_kind"] == "producer_group"
    assert result.source_identity["producer_group_id"] == "pg_bridge_fx"


def test_different_source_kinds_can_use_own_thresholds():
    cand_master = _candidates_for(4)
    stem = LoopSourceIdentity(
        source_kind="stem", stem_id="stem_drums_01", stem_ref="stemmanifest_drums_01"
    )
    indices = [i * BAR_LEN for i in range(24)]
    cand_stem = generate_loop_candidates(
        stem, beat_grid=_downbeat_result(indices)
    ).candidates[0]
    start_edge = _sine_segment(256, freq=220.0, amp=0.2)
    end_edge = -_sine_segment(256, freq=220.0, amp=0.8)  # inverted, large amp gap
    wf = _build_waveform(
        4,
        energies=[0.3] * 4,
        onset_patterns=[_stable_pattern()] * 4,
        start_edge=start_edge,
        end_edge=end_edge,
    )
    relaxed = default_loop_scoring_config()
    relaxed.source_kind_thresholds = {
        "stem": LoopScoringThresholds(seam_hard_min_continuity=0.05)
    }
    master_res = score_loop_candidate(cand_master, wf, sample_rate=SR)
    stem_res = score_loop_candidate(cand_stem, wf, sample_rate=SR, config=relaxed)
    if master_res.hard_rejected:
        assert not stem_res.hard_rejected


# --- 8. hard reject vs scores --------------------------------------------


def test_hard_reject_reasons_separated_from_scores():
    cand = _candidates_for(4)
    start_edge = _sine_segment(256, freq=220.0, amp=0.05)
    end_edge = np.full(256, 0.9, dtype=np.float32)
    wf = _build_waveform(
        4,
        energies=[0.3] * 4,
        onset_patterns=[_stable_pattern()] * 4,
        start_edge=start_edge,
        end_edge=end_edge,
    )
    result = score_loop_candidate(cand, wf, sample_rate=SR)
    assert result.hard_rejected is True
    assert result.reject_reasons  # separate list
    assert result.score_components[SEAM_CONTINUITY].value is not None


# --- 9. thresholds configurable ------------------------------------------


def test_threshold_change_reproducibly_changes_decision():
    cand = _candidates_for(4)
    start_edge = _sine_segment(256, freq=220.0, amp=0.2)
    end_edge = _sine_segment(256, freq=220.0, amp=0.45)
    wf = _build_waveform(
        4,
        energies=[0.3] * 4,
        onset_patterns=[_stable_pattern()] * 4,
        start_edge=start_edge,
        end_edge=end_edge,
    )
    cfg_tight = default_loop_scoring_config()
    cfg_tight.thresholds = LoopScoringThresholds(seam_hard_min_continuity=0.99)
    cfg_loose = default_loop_scoring_config()
    cfg_loose.thresholds = LoopScoringThresholds(seam_hard_min_continuity=0.01)
    tight = score_loop_candidate(cand, wf, sample_rate=SR, config=cfg_tight)
    loose = score_loop_candidate(cand, wf, sample_rate=SR, config=cfg_loose)
    assert tight.hard_rejected != loose.hard_rejected


def test_no_global_pilot_threshold_baked_in():
    cfg = default_loop_scoring_config()
    assert isinstance(cfg.thresholds, LoopScoringThresholds)
    cand = _candidates_for(4)
    start_edge = _sine_segment(256, freq=220.0, amp=0.2)
    end_edge = _sine_segment(256, freq=220.0, amp=0.45)
    wf = _build_waveform(
        4,
        energies=[0.3] * 4,
        onset_patterns=[_stable_pattern()] * 4,
        start_edge=start_edge,
        end_edge=end_edge,
    )
    cfg_override = default_loop_scoring_config()
    cfg_override.thresholds = LoopScoringThresholds(seam_hard_min_continuity=0.5)
    default_res = score_loop_candidate(cand, wf, sample_rate=SR)
    overridden_res = score_loop_candidate(cand, wf, sample_rate=SR, config=cfg_override)
    assert (
        default_res.config_provenance["thresholds"]
        != overridden_res.config_provenance["thresholds"]
    )


# --- 10. invalid inputs fail-closed --------------------------------------


def test_mismatched_waveform_length_fails_closed():
    cand = _candidates_for(4)
    wf = np.zeros(cand.n_samples + 10, dtype=np.float32)
    try:
        score_loop_candidate(cand, wf, sample_rate=SR)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_non_finite_waveform_fails_closed():
    cand = _candidates_for(4)
    wf = np.full(cand.n_samples, np.nan, dtype=np.float32)
    try:
        score_loop_candidate(cand, wf, sample_rate=SR)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_none_waveform_uses_status_based_no_evidence():
    cand = _candidates_for(4)
    result = score_loop_candidate(cand, None, sample_rate=SR)
    assert result.status == "no_evidence"
    assert result.hard_rejected is False
    assert result.reject_reasons == ()


# --- 11. manifest mapping ------------------------------------------------


def test_result_maps_to_asset_manifest_candidate_block():
    cand = _candidates_for(4)
    wf = _build_waveform(4, energies=[0.3] * 4, onset_patterns=[_stable_pattern()] * 4)
    result = score_loop_candidate(cand, wf, sample_rate=SR)
    block = result.as_candidate_dict()
    assert "score_components" in block
    assert block["excluded"] == result.hard_rejected
    if result.hard_rejected:
        assert block["reject_reasons"]
    assert block["status"] in {"candidate", "rejected"}


def test_summary_score_documented_and_keeps_components():
    cand = _candidates_for(4)
    wf = _build_waveform(4, energies=[0.3] * 4, onset_patterns=[_stable_pattern()] * 4)
    result = score_loop_candidate(cand, wf, sample_rate=SR)
    if result.summary_score is not None:
        assert 0.0 <= result.summary_score <= 1.0
    assert SEAM_CONTINUITY in result.score_components
