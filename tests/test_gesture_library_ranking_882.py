"""Frozen acceptance for R&D Slice 2 — gesture cluster → library ranking (#680 / #882).

Docs authority: docs/GESTURE_LIBRARY_RANKING_RND_SLICE2.md

Do not weaken assertions to fit an incorrect implementation.
Synthetic candidates only — no private catalog paths, DBs, or audio binaries.
"""

from __future__ import annotations

import importlib
import inspect
import math
import sys
from typing import Iterable

import pytest

from src.gesture_analysis import FEATURE_DIM, GestureAnalysis, GestureEvent

from src.gesture_library_ranking import (
    ClusterRanking,
    LibraryCandidate,
    RankedCandidate,
    rank_gesture_library_candidates,
)


def _feat(
    rms: float,
    brightness: float,
    mfcc0: float = 1.0,
    *,
    mfcc_rest: float = 0.0,
) -> tuple[float, ...]:
    mfcc = [float(mfcc0)] + [float(mfcc_rest)] * 12
    assert len(mfcc) == 13
    vec = (float(rms), float(brightness), *mfcc)
    assert len(vec) == FEATURE_DIM
    return vec


def _analysis(events: Iterable[GestureEvent]) -> GestureAnalysis:
    return GestureAnalysis(
        events=tuple(events),
        sample_rate=44100,
        duration_sec=2.0,
        feature_dim=FEATURE_DIM,
        status="ok",
    )


def _candidate(
    sample_id: str,
    *,
    audio_class: str = "oneshot",
    loudness: float = -12.0,
    brightness: float = 1200.0,
    mfcc0: float = 1.0,
    mfcc_rest: float = 0.0,
    path: str | None = None,
) -> LibraryCandidate:
    mfcc13 = (float(mfcc0),) + tuple(float(mfcc_rest) for _ in range(12))
    return LibraryCandidate(
        sample_id=sample_id,
        path=path,
        audio_class=audio_class,
        loudness=float(loudness),
        brightness=float(brightness),
        mfcc13=mfcc13,
    )


def _ranking_by_cluster(
    result: tuple[ClusterRanking, ...],
) -> dict[int, ClusterRanking]:
    out = {row.cluster_id: row for row in result}
    assert len(out) == len(result)
    return out


def test_repeated_events_same_cluster_exactly_one_prototype() -> None:
    """1. Repeated events same cluster → exactly one prototype."""
    vec = _feat(0.25, 1100.0, mfcc0=2.0)
    analysis = _analysis(
        [
            GestureEvent(0.10, vec, 0),
            GestureEvent(0.40, vec, 0),
            GestureEvent(0.70, vec, 0),
        ]
    )
    candidates = (
        _candidate("a", loudness=-12.0, brightness=1100.0, mfcc0=2.0),
        _candidate("b", loudness=-20.0, brightness=4000.0, mfcc0=-3.0),
    )
    result = rank_gesture_library_candidates(analysis, candidates, top_n=3)
    by_c = _ranking_by_cluster(result)
    assert list(by_c) == [0]
    assert len(by_c[0].prototype_aligned) == FEATURE_DIM
    assert all(math.isfinite(x) for x in by_c[0].prototype_aligned)


def test_all_events_same_cluster_share_ranking_semantics() -> None:
    """2. All events same cluster → same ranking object/content semantics."""
    v1 = _feat(0.20, 1000.0, mfcc0=1.0)
    v2 = _feat(0.22, 1050.0, mfcc0=1.1)
    analysis = _analysis(
        [
            GestureEvent(0.1, v1, 7),
            GestureEvent(0.5, v2, 7),
        ]
    )
    candidates = (
        _candidate("near", loudness=-13.0, brightness=1025.0, mfcc0=1.05),
        _candidate("far", loudness=-30.0, brightness=7000.0, mfcc0=-5.0),
    )
    result = rank_gesture_library_candidates(analysis, candidates, top_n=2)
    assert len(result) == 1
    ranked = result[0]
    assert ranked.cluster_id == 7
    assert isinstance(ranked.ranked, tuple)
    assert len(ranked.ranked) >= 1
    again = rank_gesture_library_candidates(analysis, candidates, top_n=2)
    assert again[0].cluster_id == ranked.cluster_id
    assert again[0].prototype_aligned == ranked.prototype_aligned
    assert again[0].ranked == ranked.ranked


def test_two_distinct_clusters_may_rank_different_candidates() -> None:
    """3. Two clearly distinct synthetic clusters → may rank different candidates."""
    low = _feat(0.30, 800.0, mfcc0=3.0)
    high = _feat(0.15, 5000.0, mfcc0=-2.0)
    analysis = _analysis(
        [
            GestureEvent(0.1, low, 0),
            GestureEvent(0.3, high, 1),
            GestureEvent(0.5, low, 0),
            GestureEvent(0.7, high, 1),
        ]
    )
    candidates = (
        _candidate("dark", loudness=-10.0, brightness=800.0, mfcc0=3.0),
        _candidate("bright", loudness=-16.0, brightness=5000.0, mfcc0=-2.0),
        _candidate("mid", loudness=-14.0, brightness=2500.0, mfcc0=0.0),
    )
    result = rank_gesture_library_candidates(analysis, candidates, top_n=1)
    by_c = _ranking_by_cluster(result)
    assert set(by_c) == {0, 1}
    assert by_c[0].ranked[0].sample_id != by_c[1].ranked[0].sample_id


def test_near_feature_candidate_ranks_before_distant() -> None:
    """4. Near/exact feature candidate → before distant candidate."""
    rms = 0.25
    expected_dbfs = 20.0 * math.log10(rms + 1e-12)
    analysis = _analysis([GestureEvent(0.2, _feat(rms, 1500.0, mfcc0=1.5), 0)])
    candidates = (
        _candidate("exact", loudness=expected_dbfs, brightness=1500.0, mfcc0=1.5),
        _candidate("far", loudness=-40.0, brightness=8000.0, mfcc0=-8.0),
    )
    result = rank_gesture_library_candidates(analysis, candidates, top_n=2)
    ranked = result[0].ranked
    assert [r.sample_id for r in ranked] == ["exact", "far"]
    assert ranked[0].distance < ranked[1].distance
    assert ranked[0].rank == 1
    assert ranked[1].rank == 2


def test_candidate_order_permutation_same_semantic_ranking() -> None:
    """5. Candidate order permutation → same semantic ranking."""
    analysis = _analysis([GestureEvent(0.2, _feat(0.2, 2000.0, mfcc0=0.5), 0)])
    a = _candidate("a", loudness=-14.0, brightness=2000.0, mfcc0=0.5)
    b = _candidate("b", loudness=-25.0, brightness=6000.0, mfcc0=-4.0)
    c = _candidate("c", loudness=-18.0, brightness=3000.0, mfcc0=-1.0)
    r1 = rank_gesture_library_candidates(analysis, (a, b, c), top_n=3)
    r2 = rank_gesture_library_candidates(analysis, (c, a, b), top_n=3)
    r3 = rank_gesture_library_candidates(analysis, (b, c, a), top_n=3)
    assert r1[0].prototype_aligned == r2[0].prototype_aligned == r3[0].prototype_aligned
    assert r1[0].ranked == r2[0].ranked == r3[0].ranked


def test_equal_distance_stable_identifier_tie_break() -> None:
    """6. Equal-distance candidates → stable identifier tie-break."""
    analysis = _analysis([GestureEvent(0.2, _feat(0.2, 1000.0, mfcc0=0.0), 0)])
    c_z = _candidate("z_id", loudness=-14.0, brightness=1000.0, mfcc0=0.0)
    c_a = _candidate("a_id", loudness=-14.0, brightness=1000.0, mfcc0=0.0)
    c_m = _candidate("m_id", loudness=-14.0, brightness=1000.0, mfcc0=0.0)
    result = rank_gesture_library_candidates(analysis, (c_z, c_a, c_m), top_n=3)
    ids = [r.sample_id for r in result[0].ranked]
    assert ids == ["a_id", "m_id", "z_id"]
    dists = [r.distance for r in result[0].ranked]
    assert dists[0] == pytest.approx(dists[1])
    assert dists[1] == pytest.approx(dists[2])


def test_empty_candidates_defined_empty_result() -> None:
    """7. Empty candidates → empty defined result."""
    analysis = _analysis([GestureEvent(0.2, _feat(0.2, 1000.0), 0)])
    result = rank_gesture_library_candidates(analysis, (), top_n=5)
    assert len(result) == 1
    assert result[0].cluster_id == 0
    assert result[0].ranked == ()


def test_top_n_zero_and_negative_fail_closed() -> None:
    """8. top_n == 0 / negative → fail closed per frozen API."""
    analysis = _analysis([GestureEvent(0.2, _feat(0.2, 1000.0), 0)])
    candidates = (_candidate("a"),)
    with pytest.raises(ValueError):
        rank_gesture_library_candidates(analysis, candidates, top_n=0)
    with pytest.raises(ValueError):
        rank_gesture_library_candidates(analysis, candidates, top_n=-1)


def test_malformed_mfcc_length_excluded() -> None:
    """9. Malformed MFCC length → excluded / fail closed (not ranked)."""
    good = _candidate("good", loudness=-12.0, brightness=1200.0, mfcc0=1.0)
    try:
        bad = LibraryCandidate(
            sample_id="bad",
            path=None,
            audio_class="oneshot",
            loudness=-12.0,
            brightness=1200.0,
            mfcc13=(1.0, 2.0),  # length 2
        )
        pool: tuple[LibraryCandidate, ...] = (good, bad)
    except (ValueError, TypeError):
        pool = (good,)

    analysis = _analysis([GestureEvent(0.2, _feat(0.25, 1200.0, mfcc0=1.0), 0)])
    result = rank_gesture_library_candidates(analysis, pool, top_n=5)
    ids = [r.sample_id for r in result[0].ranked]
    assert "bad" not in ids
    assert "good" in ids


def test_nan_inf_required_features_excluded() -> None:
    """10. NaN / Inf any required feature → excluded / fail closed."""
    analysis = _analysis([GestureEvent(0.2, _feat(0.2, 1000.0, mfcc0=0.0), 0)])
    good = _candidate("good", loudness=-14.0, brightness=1000.0, mfcc0=0.0)
    nan_loud = LibraryCandidate(
        sample_id="nan_loud",
        path=None,
        audio_class="oneshot",
        loudness=float("nan"),
        brightness=1000.0,
        mfcc13=(0.0,) + (0.0,) * 12,
    )
    inf_bright = LibraryCandidate(
        sample_id="inf_bright",
        path=None,
        audio_class="oneshot",
        loudness=-14.0,
        brightness=float("inf"),
        mfcc13=(0.0,) + (0.0,) * 12,
    )
    nan_mfcc = LibraryCandidate(
        sample_id="nan_mfcc",
        path=None,
        audio_class="oneshot",
        loudness=-14.0,
        brightness=1000.0,
        mfcc13=(float("nan"),) + (0.0,) * 12,
    )
    loop = _candidate("loop_x", audio_class="loop", loudness=-14.0, brightness=1000.0)
    result = rank_gesture_library_candidates(
        analysis, (nan_loud, inf_bright, nan_mfcc, loop, good), top_n=5
    )
    ids = [r.sample_id for r in result[0].ranked]
    assert ids == ["good"]


def test_zero_variance_normalization_finite_deterministic() -> None:
    """11. Zero-variance normalization dimension → finite deterministic result."""
    analysis = _analysis([GestureEvent(0.2, _feat(0.2, 1000.0, mfcc0=1.0), 0)])
    cands = (
        _candidate("c1", loudness=-10.0, brightness=1000.0, mfcc0=1.0),
        _candidate("c2", loudness=-20.0, brightness=1000.0, mfcc0=2.0),
        _candidate("c3", loudness=-30.0, brightness=1000.0, mfcc0=3.0),
    )
    r1 = rank_gesture_library_candidates(analysis, cands, top_n=3)
    r2 = rank_gesture_library_candidates(analysis, cands, top_n=3)
    assert r1 == r2
    for row in r1[0].ranked:
        assert math.isfinite(row.distance)
    assert all(math.isfinite(x) for x in r1[0].prototype_aligned)


def test_same_inputs_twice_identical_ranking() -> None:
    """12. Same inputs twice → identical prototype/distances/ranking."""
    analysis = _analysis(
        [
            GestureEvent(0.1, _feat(0.21, 900.0, mfcc0=1.2), 0),
            GestureEvent(0.4, _feat(0.23, 950.0, mfcc0=1.3), 0),
        ]
    )
    candidates = (
        _candidate("p", loudness=-12.5, brightness=920.0, mfcc0=1.25),
        _candidate("q", loudness=-22.0, brightness=4500.0, mfcc0=-2.0),
    )
    a = rank_gesture_library_candidates(analysis, candidates, top_n=2)
    b = rank_gesture_library_candidates(analysis, candidates, top_n=2)
    assert a == b


def test_no_mutation_of_gesture_analysis() -> None:
    """13. No mutation of GestureAnalysis."""
    events = (
        GestureEvent(0.1, _feat(0.2, 1000.0), 0),
        GestureEvent(0.5, _feat(0.25, 1100.0), 0),
    )
    analysis = _analysis(events)
    before_events = analysis.events
    before_status = analysis.status
    before_ids = [e.cluster_id for e in analysis.events]
    before_onsets = [e.onset_time_sec for e in analysis.events]
    before_feats = [e.feature_vector for e in analysis.events]
    rank_gesture_library_candidates(analysis, (_candidate("a"),), top_n=1)
    assert analysis.events is before_events
    assert analysis.status == before_status
    assert [e.cluster_id for e in analysis.events] == before_ids
    assert [e.onset_time_sec for e in analysis.events] == before_onsets
    assert [e.feature_vector for e in analysis.events] == before_feats


def test_onset_time_sec_unchanged() -> None:
    """14. onset_time_sec unchanged."""
    analysis = _analysis(
        [
            GestureEvent(0.11, _feat(0.2, 1000.0), 0),
            GestureEvent(0.55, _feat(0.2, 1000.0), 1),
        ]
    )
    onsets = [e.onset_time_sec for e in analysis.events]
    rank_gesture_library_candidates(analysis, (_candidate("a"), _candidate("b")), top_n=1)
    assert [e.onset_time_sec for e in analysis.events] == onsets


def test_cluster_id_unchanged() -> None:
    """15. cluster_id unchanged."""
    analysis = _analysis(
        [
            GestureEvent(0.11, _feat(0.2, 1000.0), 3),
            GestureEvent(0.55, _feat(0.4, 4000.0), 9),
        ]
    )
    ids = [e.cluster_id for e in analysis.events]
    rank_gesture_library_candidates(analysis, (_candidate("a"),), top_n=1)
    assert [e.cluster_id for e in analysis.events] == ids


def test_no_pattern_channel_trigger_objects_created() -> None:
    """16. No Pattern/Channel/Trigger objects created."""
    from src import pattern_core

    analysis = _analysis([GestureEvent(0.2, _feat(0.2, 1000.0), 0)])
    result = rank_gesture_library_candidates(analysis, (_candidate("a"),), top_n=1)
    assert all(isinstance(x, ClusterRanking) for x in result)
    assert all(isinstance(r, RankedCandidate) for x in result for r in x.ranked)
    for x in result:
        assert not isinstance(x, pattern_core.Pattern)
        for r in x.ranked:
            assert not isinstance(r, pattern_core.Trigger)
    mod = importlib.import_module("src.gesture_library_ranking")
    src = inspect.getsource(mod)
    assert "pattern_core" not in src
    assert "Pattern(" not in src
    assert "Trigger(" not in src
    assert "Channel(" not in src


def test_no_sqlite_dependency_in_core_ranker() -> None:
    """17. No SQLite dependency in core ranker."""
    mod = importlib.import_module("src.gesture_library_ranking")
    src = inspect.getsource(mod)
    for banned in ("sqlite", "sqlalchemy", "from .db", "import src.db", "from src.db"):
        assert banned not in src
    assert "src.db" not in getattr(mod, "__dict__", {})
    assert not any(n == "db" or n.endswith(".db") for n in getattr(mod, "__dict__", {}))


def test_no_embedding_model_invocation() -> None:
    """18. No embedding/model invocation."""
    mod = importlib.import_module("src.gesture_library_ranking")
    src = inspect.getsource(mod)
    src_lower = src.lower()
    for banned in (
        "clap",
        "torch",
        "get_backend",
        "embeddingbackend",
        "from .embed",
        "from .search",
        "import src.embed",
        "import src.search",
    ):
        assert banned not in src_lower

    analysis = _analysis([GestureEvent(0.2, _feat(0.2, 1000.0), 0)])
    rank_gesture_library_candidates(analysis, (_candidate("a"),), top_n=1)


def test_no_new_runtime_dependency_surface() -> None:
    """19. No new runtime dependency beyond existing analyze/gesture stack."""
    mod = importlib.import_module("src.gesture_library_ranking")
    src = inspect.getsource(mod)
    for banned in ("sklearn", "scipy.spatial", "faiss", "annoy", "hnswlib", "requests"):
        assert banned not in src


def test_no_semantic_drum_label_inferred() -> None:
    """20. No semantic drum label inferred."""
    analysis = _analysis(
        [
            GestureEvent(0.1, _feat(0.3, 700.0, mfcc0=2.0), 0),
            GestureEvent(0.4, _feat(0.15, 5000.0, mfcc0=-1.0), 1),
        ]
    )
    result = rank_gesture_library_candidates(
        analysis,
        (
            _candidate("x", loudness=-10.0, brightness=700.0, mfcc0=2.0),
            _candidate("y", loudness=-16.0, brightness=5000.0, mfcc0=-1.0),
        ),
        top_n=1,
    )
    blob = repr(result).lower()
    for label in ("kick", "snare", "hat", "hihat", "hi-hat"):
        assert label not in blob
    mod = importlib.import_module("src.gesture_library_ranking")
    src_lower = inspect.getsource(mod).lower()
    for label in ("kick", "snare", "hihat", "hi-hat"):
        assert label not in src_lower


def test_median_prototype_prefers_robust_center() -> None:
    """Docs freeze: prototype is per-dimension median of raw gesture features."""
    analysis = _analysis(
        [
            GestureEvent(0.1, _feat(0.10, 1000.0, mfcc0=1.0), 0),
            GestureEvent(0.3, _feat(0.20, 1000.0, mfcc0=1.0), 0),
            GestureEvent(0.5, _feat(1.00, 1000.0, mfcc0=1.0), 0),
        ]
    )
    median_rms = 0.20
    median_dbfs = 20.0 * math.log10(median_rms + 1e-12)
    mean_rms = (0.10 + 0.20 + 1.00) / 3.0
    mean_dbfs = 20.0 * math.log10(mean_rms + 1e-12)
    c_median = _candidate("med", loudness=median_dbfs, brightness=1000.0, mfcc0=1.0)
    c_mean = _candidate("mean", loudness=mean_dbfs, brightness=1000.0, mfcc0=1.0)
    result = rank_gesture_library_candidates(analysis, (c_mean, c_median), top_n=2)
    assert result[0].ranked[0].sample_id == "med"
    assert result[0].prototype_aligned[0] == pytest.approx(median_dbfs)


def test_non_positive_prototype_rms_fail_closed_empty_ranking() -> None:
    """Silence/invalid RMS on prototype → fail closed empty ranking for cluster."""
    analysis = _analysis([GestureEvent(0.2, _feat(0.0, 1000.0, mfcc0=1.0), 0)])
    result = rank_gesture_library_candidates(analysis, (_candidate("a"),), top_n=1)
    assert len(result) == 1
    assert result[0].ranked == ()
    assert result[0].prototype_aligned == ()
