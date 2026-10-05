"""Frozen acceptance for R&D Slice 5 — Pattern binding plan (#680 / #891).

Docs authority: docs/GESTURE_PATTERN_BINDING_RND_SLICE5.md

Intentionally RED until src/gesture_pattern_binding.py exists.
Synthetic fixtures only — no audio, no DB, no private catalogs.
"""

from __future__ import annotations

import ast
import copy
import importlib
import math
from collections import OrderedDict
from fractions import Fraction
from pathlib import Path

import pytest

from src.gesture_library_ranking import (
    ClusterRanking,
    LibraryCandidate,
    RankedCandidate,
)
from src.gesture_timing_projection import (
    GestureTimingProjection,
    ProjectedGestureEvent,
)
from src.pattern_core import (
    CHANNEL_ID_BY_LIVE_KIT_SLOT,
    Channel,
    Pattern,
    Trigger,
    allocate_user_channel_id,
)

from src.gesture_pattern_binding import (
    GesturePatternBindingPlan,
    PlannedGestureChannelBinding,
    PlannedGestureEventBinding,
    plan_gesture_pattern_binding,
)

_MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "gesture_pattern_binding.py"

_ALLOWED_IMPORT_ROOTS = frozenset(
    {
        "annotations",
        "__future__",
        "dataclasses",
        "fractions",
        "math",
        "typing",
        "collections",
        "collections.abc",
        "gesture_analysis",
        "src.gesture_analysis",
        "gesture_library_ranking",
        "src.gesture_library_ranking",
        "gesture_timing_projection",
        "src.gesture_timing_projection",
        "pattern_core",
        "src.pattern_core",
    }
)

_BANNED_IMPORT_ROOTS = frozenset(
    {
        "channel_rack",
        "src.channel_rack",
        "gesture_catalog_adapter",
        "src.gesture_catalog_adapter",
        "sqlite3",
        "sqlalchemy",
        "db",
        "src.db",
        "workbench_qml",
        "src.workbench_qml",
        "librosa",
        "numpy",
        "torch",
    }
)


def _candidate(
    sample_id: str,
    path: str | None = None,
    *,
    loudness: float = -12.0,
    brightness: float = 1200.0,
) -> LibraryCandidate:
    return LibraryCandidate(
        sample_id=sample_id,
        path=path if path is not None else f"{sample_id}.wav",
        audio_class="oneshot",
        loudness=loudness,
        brightness=brightness,
        mfcc13=tuple(float(i) for i in range(13)),
    )


def _ranked(sample_id: str, distance: float, rank: int) -> RankedCandidate:
    return RankedCandidate(sample_id=sample_id, distance=distance, rank=rank)


def _ranking(
    cluster_id: int,
    ranked: tuple[RankedCandidate, ...] | list[RankedCandidate],
) -> ClusterRanking:
    return ClusterRanking(
        cluster_id=cluster_id,
        prototype_aligned=tuple(0.0 for _ in range(15)),
        ranked=tuple(ranked),
    )


def _event(cluster_id: int, quarter: Fraction | int | str) -> ProjectedGestureEvent:
    pos = quarter if isinstance(quarter, Fraction) else Fraction(quarter)
    return ProjectedGestureEvent(
        source_onset_sec=float(pos) * 0.5,  # decorative only for tests
        quarter_position=pos,
        cluster_id=cluster_id,
    )


def _timing(
    events: list[ProjectedGestureEvent] | tuple[ProjectedGestureEvent, ...],
    *,
    duration_quarters: Fraction | None = None,
    bpm: Fraction = Fraction(120, 1),
) -> GestureTimingProjection:
    ev = tuple(events)
    if duration_quarters is None:
        if ev:
            duration_quarters = max(e.quarter_position for e in ev) + Fraction(1, 1)
        else:
            duration_quarters = Fraction(4, 1)
    return GestureTimingProjection(
        events=ev,
        reference_bpm=bpm,
        projected_duration_quarters=duration_quarters,
    )


def _plan(
    timing: GestureTimingProjection,
    rankings: list[ClusterRanking] | tuple[ClusterRanking, ...],
    candidates: list[LibraryCandidate] | tuple[LibraryCandidate, ...],
    selections: dict[int, str],
    existing: list[str] | tuple[str, ...] = (),
    *,
    length: Fraction = Fraction(4, 1),
) -> GesturePatternBindingPlan:
    return plan_gesture_pattern_binding(
        timing,
        rankings,
        candidates,
        selections,
        existing,
        pattern_length_quarters=length,
    )


def _imported_module_names(mod) -> set[str]:
    path = Path(mod.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
                names.add(node.module)
    return names


def _source_text() -> str:
    return _MODULE_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Happy-path selection / channels / events
# ---------------------------------------------------------------------------


def test_01_one_cluster_explicit_selection_one_channel() -> None:
    """1. one cluster + explicit ranked selection → one channel binding."""
    timing = _timing([_event(0, Fraction(0, 1)), _event(0, Fraction(1, 2))])
    rankings = [_ranking(0, [_ranked("a", 0.1, 1), _ranked("b", 0.5, 2)])]
    candidates = [_candidate("a"), _candidate("b")]
    plan = _plan(timing, rankings, candidates, {0: "a"})
    assert len(plan.channel_bindings) == 1
    assert plan.channel_bindings[0].cluster_id == 0
    assert plan.channel_bindings[0].sample_id == "a"
    assert plan.ready_for_pattern is True


def test_02_repeated_events_same_cluster_multiple_bindings() -> None:
    """2. repeated events same cluster → one channel + multiple exact event bindings."""
    positions = [Fraction(0, 1), Fraction(1, 2), Fraction(3, 2)]
    timing = _timing([_event(3, p) for p in positions])
    rankings = [_ranking(3, [_ranked("x", 1.0, 1)])]
    plan = _plan(timing, rankings, [_candidate("x")], {3: "x"}, length=Fraction(4, 1))
    assert len(plan.channel_bindings) == 1
    assert plan.channel_bindings[0].channel_id
    assert len(plan.event_bindings) == 3
    assert [e.quarter_position for e in plan.event_bindings] == positions
    assert {e.channel_id for e in plan.event_bindings} == {
        plan.channel_bindings[0].channel_id
    }


def test_03_two_selected_clusters_two_unique_channel_ids() -> None:
    """3. two selected clusters → two unique planned channel IDs."""
    timing = _timing([_event(1, Fraction(0, 1)), _event(2, Fraction(1, 1))])
    rankings = [
        _ranking(1, [_ranked("a", 0.2, 1)]),
        _ranking(2, [_ranked("b", 0.3, 1)]),
    ]
    plan = _plan(
        timing,
        rankings,
        [_candidate("a"), _candidate("b")],
        {1: "a", 2: "b"},
    )
    ids = [c.channel_id for c in plan.channel_bindings]
    assert len(ids) == 2
    assert len(set(ids)) == 2


def test_04_allocation_follows_sorted_cluster_id() -> None:
    """4. allocation follows sorted cluster_id."""
    timing = _timing([_event(5, Fraction(0, 1)), _event(1, Fraction(1, 4))])
    rankings = [
        _ranking(5, [_ranked("z", 0.1, 1)]),
        _ranking(1, [_ranked("a", 0.1, 1)]),
    ]
    plan = _plan(
        timing,
        rankings,
        [_candidate("a"), _candidate("z")],
        {5: "z", 1: "a"},
        existing=[],
    )
    assert [c.cluster_id for c in plan.channel_bindings] == [1, 5]
    # First free ch_user_1 assigned to lowest cluster_id first.
    assert plan.channel_bindings[0].channel_id == "ch_user_1"
    assert plan.channel_bindings[1].channel_id == "ch_user_2"


def test_05_selection_mapping_insertion_order_permutation_same_plan() -> None:
    """5. selection mapping insertion order permutation → same semantic plan."""
    timing = _timing([_event(0, Fraction(0, 1)), _event(1, Fraction(1, 1))])
    rankings = [
        _ranking(0, [_ranked("a", 0.1, 1)]),
        _ranking(1, [_ranked("b", 0.2, 1)]),
    ]
    candidates = [_candidate("a"), _candidate("b")]
    sel_a = OrderedDict([(0, "a"), (1, "b")])
    sel_b = OrderedDict([(1, "b"), (0, "a")])
    plan_a = _plan(timing, rankings, candidates, dict(sel_a))
    plan_b = _plan(timing, rankings, candidates, dict(sel_b))
    assert plan_a == plan_b


def test_06_candidate_input_order_permutation_same_plan() -> None:
    """6. candidate input order permutation → same semantic plan."""
    timing = _timing([_event(0, Fraction(0, 1))])
    rankings = [_ranking(0, [_ranked("a", 0.1, 1), _ranked("b", 0.4, 2)])]
    plan_a = _plan(timing, rankings, [_candidate("a"), _candidate("b")], {0: "a"})
    plan_b = _plan(timing, rankings, [_candidate("b"), _candidate("a")], {0: "a"})
    assert plan_a == plan_b


def test_07_same_sample_different_clusters_distinct_channels() -> None:
    """7. different clusters selecting same sample → distinct channels, same path allowed."""
    timing = _timing([_event(1, Fraction(0, 1)), _event(2, Fraction(1, 1))])
    rankings = [
        _ranking(1, [_ranked("42", 0.1, 1)]),
        _ranking(2, [_ranked("42", 0.2, 1)]),
    ]
    plan = _plan(timing, rankings, [_candidate("42", "shared.wav")], {1: "42", 2: "42"})
    assert len(plan.channel_bindings) == 2
    assert plan.channel_bindings[0].channel_id != plan.channel_bindings[1].channel_id
    assert plan.channel_bindings[0].sample_path == plan.channel_bindings[1].sample_path


def test_08_selected_sample_copies_id_and_path() -> None:
    """8. selected sample copies sample_id/path."""
    timing = _timing([_event(0, Fraction(0, 1))])
    rankings = [_ranking(0, [_ranked("sid", 0.3, 1)])]
    plan = _plan(timing, rankings, [_candidate("sid", "path/to.wav")], {0: "sid"})
    bind = plan.channel_bindings[0]
    assert bind.sample_id == "sid"
    assert bind.sample_path == "path/to.wav"


def test_09_selected_ranking_evidence_copies_rank_distance() -> None:
    """9. selected ranking evidence copies rank/distance."""
    timing = _timing([_event(0, Fraction(0, 1))])
    rankings = [_ranking(0, [_ranked("a", 0.1, 1), _ranked("b", 2.5, 2)])]
    plan = _plan(timing, rankings, [_candidate("a"), _candidate("b")], {0: "b"})
    assert plan.channel_bindings[0].selected_rank == 2
    assert plan.channel_bindings[0].distance == 2.5


def test_10_distance_is_evidence_not_confidence_field() -> None:
    """10. distance remains evidence only; no confidence field invented."""
    timing = _timing([_event(0, Fraction(0, 1))])
    plan = _plan(
        timing,
        [_ranking(0, [_ranked("a", 0.7, 1)])],
        [_candidate("a")],
        {0: "a"},
    )
    bind = plan.channel_bindings[0]
    assert hasattr(bind, "distance")
    assert not hasattr(bind, "confidence")
    assert "confidence" not in _source_text().lower()


# ---------------------------------------------------------------------------
# Unresolved / readiness
# ---------------------------------------------------------------------------


def test_11_no_selection_unresolved_cluster() -> None:
    """11. no selection → unresolved cluster."""
    timing = _timing([_event(0, Fraction(0, 1))])
    plan = _plan(
        timing,
        [_ranking(0, [_ranked("a", 0.1, 1)])],
        [_candidate("a")],
        {},
    )
    assert plan.unresolved_cluster_ids == (0,)


def test_12_unresolved_cluster_no_channel_binding() -> None:
    """12. unresolved cluster → no channel binding."""
    timing = _timing([_event(0, Fraction(0, 1))])
    plan = _plan(
        timing,
        [_ranking(0, [_ranked("a", 0.1, 1)])],
        [_candidate("a")],
        {},
    )
    assert plan.channel_bindings == ()


def test_13_unresolved_cluster_no_event_binding() -> None:
    """13. unresolved cluster → no event binding."""
    timing = _timing([_event(0, Fraction(0, 1)), _event(0, Fraction(1, 2))])
    plan = _plan(
        timing,
        [_ranking(0, [_ranked("a", 0.1, 1)])],
        [_candidate("a")],
        {},
    )
    assert plan.event_bindings == ()


def test_14_one_resolved_one_unresolved_not_ready() -> None:
    """14. one resolved + one unresolved → ready_for_pattern == False."""
    timing = _timing([_event(0, Fraction(0, 1)), _event(1, Fraction(1, 1))])
    rankings = [
        _ranking(0, [_ranked("a", 0.1, 1)]),
        _ranking(1, [_ranked("b", 0.2, 1)]),
    ]
    plan = _plan(
        timing,
        rankings,
        [_candidate("a"), _candidate("b")],
        {0: "a"},
    )
    assert plan.unresolved_cluster_ids == (1,)
    assert len(plan.channel_bindings) == 1
    assert plan.ready_for_pattern is False


def test_15_all_clusters_selected_ready() -> None:
    """15. all clusters selected → ready_for_pattern == True."""
    timing = _timing([_event(0, Fraction(0, 1)), _event(1, Fraction(1, 1))])
    rankings = [
        _ranking(0, [_ranked("a", 0.1, 1)]),
        _ranking(1, [_ranked("b", 0.2, 1)]),
    ]
    plan = _plan(
        timing,
        rankings,
        [_candidate("a"), _candidate("b")],
        {0: "a", 1: "b"},
    )
    assert plan.unresolved_cluster_ids == ()
    assert plan.ready_for_pattern is True


def test_16_omitted_selection_does_not_auto_pick_rank1() -> None:
    """16. omitted selection does NOT auto-pick rank 1."""
    timing = _timing([_event(0, Fraction(0, 1))])
    rankings = [_ranking(0, [_ranked("rank1", 0.01, 1), _ranked("rank2", 0.5, 2)])]
    plan = _plan(timing, rankings, [_candidate("rank1"), _candidate("rank2")], {})
    assert plan.channel_bindings == ()
    assert plan.unresolved_cluster_ids == (0,)
    assert plan.ready_for_pattern is False


# ---------------------------------------------------------------------------
# Fail-closed selection / ranking / candidates
# ---------------------------------------------------------------------------


def test_17_selected_sample_not_in_topn_fail_closed() -> None:
    """17. selected sample not in that cluster Top-N → fail closed."""
    timing = _timing([_event(0, Fraction(0, 1))])
    rankings = [_ranking(0, [_ranked("a", 0.1, 1)])]
    with pytest.raises(ValueError):
        _plan(timing, rankings, [_candidate("a"), _candidate("z")], {0: "z"})


def test_18_selected_sample_missing_candidate_fail_closed() -> None:
    """18. selected sample missing candidate → fail closed."""
    timing = _timing([_event(0, Fraction(0, 1))])
    rankings = [_ranking(0, [_ranked("a", 0.1, 1)])]
    with pytest.raises(ValueError):
        _plan(timing, rankings, [_candidate("other")], {0: "a"})


def test_19_duplicate_candidate_ids_fail_closed() -> None:
    """19. duplicate candidate IDs → fail closed."""
    timing = _timing([_event(0, Fraction(0, 1))])
    rankings = [_ranking(0, [_ranked("a", 0.1, 1)])]
    with pytest.raises(ValueError):
        _plan(
            timing,
            rankings,
            [_candidate("a", "one.wav"), _candidate("a", "two.wav")],
            {0: "a"},
        )


def test_20_duplicate_ranking_cluster_ids_fail_closed() -> None:
    """20. duplicate ranking cluster IDs → fail closed."""
    timing = _timing([_event(0, Fraction(0, 1))])
    rankings = [
        _ranking(0, [_ranked("a", 0.1, 1)]),
        _ranking(0, [_ranked("b", 0.2, 1)]),
    ]
    with pytest.raises(ValueError):
        _plan(timing, rankings, [_candidate("a"), _candidate("b")], {0: "a"})


def test_21_ranking_cluster_missing_from_timing_fail_closed() -> None:
    """21. ranking cluster missing from timing set → fail closed."""
    timing = _timing([_event(0, Fraction(0, 1))])
    rankings = [
        _ranking(0, [_ranked("a", 0.1, 1)]),
        _ranking(9, [_ranked("z", 0.1, 1)]),
    ]
    with pytest.raises(ValueError):
        _plan(timing, rankings, [_candidate("a"), _candidate("z")], {0: "a"})


def test_22_timing_cluster_missing_ranking_fail_closed() -> None:
    """22. timing cluster missing ranking → fail closed."""
    timing = _timing([_event(0, Fraction(0, 1)), _event(1, Fraction(1, 1))])
    rankings = [_ranking(0, [_ranked("a", 0.1, 1)])]
    with pytest.raises(ValueError):
        _plan(timing, rankings, [_candidate("a")], {0: "a"})


def test_23_selection_unknown_cluster_fail_closed() -> None:
    """23. selection unknown cluster → fail closed."""
    timing = _timing([_event(0, Fraction(0, 1))])
    rankings = [_ranking(0, [_ranked("a", 0.1, 1)])]
    with pytest.raises(ValueError):
        _plan(timing, rankings, [_candidate("a")], {0: "a", 99: "a"})


def test_24_selected_candidate_empty_path_fail_closed() -> None:
    """24. selected candidate empty path → fail closed."""
    timing = _timing([_event(0, Fraction(0, 1))])
    rankings = [_ranking(0, [_ranked("a", 0.1, 1)])]
    with pytest.raises(ValueError):
        _plan(timing, rankings, [_candidate("a", "")], {0: "a"})


def test_25_selected_ranked_distance_nan_inf_fail_closed() -> None:
    """25. selected ranked distance NaN/Inf → fail closed."""
    timing = _timing([_event(0, Fraction(0, 1))])
    for bad in (float("nan"), float("inf"), float("-inf")):
        rankings = [_ranking(0, [_ranked("a", bad, 1)])]
        with pytest.raises(ValueError):
            _plan(timing, rankings, [_candidate("a")], {0: "a"})


@pytest.mark.parametrize("rank", [0, -1])
def test_26_invalid_nonpositive_rank_fail_closed(rank: int) -> None:
    """26. invalid/nonpositive rank → fail closed."""
    timing = _timing([_event(0, Fraction(0, 1))])
    rankings = [_ranking(0, [_ranked("a", 0.1, rank)])]
    with pytest.raises(ValueError):
        _plan(timing, rankings, [_candidate("a")], {0: "a"})


# ---------------------------------------------------------------------------
# Pattern length
# ---------------------------------------------------------------------------


def test_27_exact_fraction_pattern_length_accepted() -> None:
    """27. exact Fraction Pattern length accepted."""
    timing = _timing([_event(0, Fraction(1, 4))])
    plan = _plan(
        timing,
        [_ranking(0, [_ranked("a", 0.1, 1)])],
        [_candidate("a")],
        {0: "a"},
        length=Fraction(4, 1),
    )
    assert plan.pattern_length_quarters == Fraction(4, 1)
    assert type(plan.pattern_length_quarters) is Fraction


@pytest.mark.parametrize("length", [4, 4.0, "4", True])
def test_28_int_float_string_bool_pattern_length_rejected(length) -> None:
    """28. int/float/string Pattern length rejected (and bool)."""
    timing = _timing([_event(0, Fraction(0, 1))])
    with pytest.raises(TypeError):
        _plan(
            timing,
            [_ranking(0, [_ranked("a", 0.1, 1)])],
            [_candidate("a")],
            {0: "a"},
            length=length,  # type: ignore[arg-type]
        )


def test_29_zero_pattern_length_rejected() -> None:
    """29. zero Pattern length rejected."""
    timing = _timing([_event(0, Fraction(0, 1))])
    with pytest.raises(ValueError):
        _plan(
            timing,
            [_ranking(0, [_ranked("a", 0.1, 1)])],
            [_candidate("a")],
            {0: "a"},
            length=Fraction(0, 1),
        )


def test_30_negative_pattern_length_rejected() -> None:
    """30. negative Pattern length rejected."""
    timing = _timing([_event(0, Fraction(0, 1))])
    with pytest.raises(ValueError):
        _plan(
            timing,
            [_ranking(0, [_ranked("a", 0.1, 1)])],
            [_candidate("a")],
            {0: "a"},
            length=Fraction(-1, 1),
        )


def test_31_event_at_exactly_pattern_length_fail_closed() -> None:
    """31. event at exactly Pattern length → fail closed."""
    length = Fraction(4, 1)
    timing = _timing([_event(0, length)])
    with pytest.raises(ValueError):
        _plan(
            timing,
            [_ranking(0, [_ranked("a", 0.1, 1)])],
            [_candidate("a")],
            {0: "a"},
            length=length,
        )


def test_32_event_beyond_pattern_length_fail_closed() -> None:
    """32. event beyond Pattern length → fail closed."""
    timing = _timing([_event(0, Fraction(5, 1))])
    with pytest.raises(ValueError):
        _plan(
            timing,
            [_ranking(0, [_ranked("a", 0.1, 1)])],
            [_candidate("a")],
            {0: "a"},
            length=Fraction(4, 1),
        )


def test_33_all_events_within_pattern_length_accepted() -> None:
    """33. all events within Pattern length → accepted."""
    length = Fraction(4, 1)
    timing = _timing(
        [_event(0, Fraction(0, 1)), _event(0, length - Fraction(1, 16))]
    )
    plan = _plan(
        timing,
        [_ranking(0, [_ranked("a", 0.1, 1)])],
        [_candidate("a")],
        {0: "a"},
        length=length,
    )
    assert plan.ready_for_pattern is True


def test_34_unresolved_event_outside_length_still_fail_closed() -> None:
    """34. unresolved event outside Pattern length → STILL fail closed."""
    timing = _timing(
        [_event(0, Fraction(0, 1)), _event(1, Fraction(9, 1))],
        duration_quarters=Fraction(10, 1),
    )
    rankings = [
        _ranking(0, [_ranked("a", 0.1, 1)]),
        _ranking(1, [_ranked("b", 0.2, 1)]),
    ]
    # Cluster 1 unresolved, but its out-of-bounds event must still fail closed.
    with pytest.raises(ValueError):
        _plan(
            timing,
            rankings,
            [_candidate("a"), _candidate("b")],
            {0: "a"},
            length=Fraction(4, 1),
        )


def test_35_projected_duration_may_differ_from_pattern_length() -> None:
    """35. projected_duration_quarters may differ from Pattern length."""
    timing = _timing(
        [_event(0, Fraction(1, 4))],
        duration_quarters=Fraction(10, 1),
    )
    plan = _plan(
        timing,
        [_ranking(0, [_ranked("a", 0.1, 1)])],
        [_candidate("a")],
        {0: "a"},
        length=Fraction(4, 1),
    )
    assert timing.projected_duration_quarters == Fraction(10, 1)
    assert plan.pattern_length_quarters == Fraction(4, 1)
    assert plan.pattern_length_quarters != timing.projected_duration_quarters


def test_36_exact_quarter_positions_unchanged() -> None:
    """36. exact quarter positions unchanged."""
    positions = [Fraction(1, 7), Fraction(2, 5), Fraction(11, 8)]
    timing = _timing([_event(0, p) for p in positions], duration_quarters=Fraction(4, 1))
    plan = _plan(
        timing,
        [_ranking(0, [_ranked("a", 0.1, 1)])],
        [_candidate("a")],
        {0: "a"},
        length=Fraction(4, 1),
    )
    assert [e.quarter_position for e in plan.event_bindings] == positions
    assert all(type(e.quarter_position) is Fraction for e in plan.event_bindings)


def test_37_no_snapping_rounding_quantization() -> None:
    """37. no snapping / rounding / quantization."""
    src = _source_text().lower()
    for token in (
        "quantize",
        "quantise",
        "snap_to",
        "grid_snap",
        "swing",
        "groove",
        "nearest_16",
        "default_on",
    ):
        assert token not in src
    timing = _timing([_event(0, Fraction(3, 10))])
    plan = _plan(
        timing,
        [_ranking(0, [_ranked("a", 0.1, 1)])],
        [_candidate("a")],
        {0: "a"},
    )
    assert plan.event_bindings[0].quarter_position == Fraction(3, 10)


# ---------------------------------------------------------------------------
# Channel allocation context
# ---------------------------------------------------------------------------


def test_38_existing_channel_ids_never_reused() -> None:
    """38. existing channel IDs never reused."""
    timing = _timing([_event(0, Fraction(0, 1))])
    plan = _plan(
        timing,
        [_ranking(0, [_ranked("a", 0.1, 1)])],
        [_candidate("a")],
        {0: "a"},
        existing=["ch_user_1", "ch_user_2"],
    )
    assert plan.channel_bindings[0].channel_id == "ch_user_3"
    assert plan.channel_bindings[0].channel_id not in {"ch_user_1", "ch_user_2"}


def test_39_allocation_avoids_canonical_pattern_core_ids() -> None:
    """39. allocation avoids canonical Pattern-Core IDs."""
    timing = _timing([_event(0, Fraction(0, 1))])
    plan = _plan(
        timing,
        [_ranking(0, [_ranked("a", 0.1, 1)])],
        [_candidate("a")],
        {0: "a"},
        existing=[],
    )
    canonical = set(CHANNEL_ID_BY_LIVE_KIT_SLOT.values())
    assert plan.channel_bindings[0].channel_id not in canonical
    assert plan.channel_bindings[0].channel_id.startswith("ch_user_")


def test_40_existing_ch_user_ids_respected() -> None:
    """40. existing ch_user_* IDs respected."""
    existing = ["ch_user_1", "ch_user_5"]
    timing = _timing([_event(0, Fraction(0, 1)), _event(1, Fraction(1, 1))])
    rankings = [
        _ranking(0, [_ranked("a", 0.1, 1)]),
        _ranking(1, [_ranked("b", 0.2, 1)]),
    ]
    plan = _plan(
        timing,
        rankings,
        [_candidate("a"), _candidate("b")],
        {0: "a", 1: "b"},
        existing=existing,
    )
    allocated = {c.channel_id for c in plan.channel_bindings}
    assert allocated.isdisjoint(set(existing))
    # Matches sequential allocate_user_channel_id behavior.
    expected_first = allocate_user_channel_id(existing)
    expected_second = allocate_user_channel_id([*existing, expected_first])
    assert [c.channel_id for c in plan.channel_bindings] == [
        expected_first,
        expected_second,
    ]


# ---------------------------------------------------------------------------
# Determinism / immutability
# ---------------------------------------------------------------------------


def test_41_same_input_twice_identical_output() -> None:
    """41. same input twice → identical output."""
    timing = _timing([_event(0, Fraction(1, 3)), _event(1, Fraction(2, 3))])
    rankings = (
        _ranking(0, [_ranked("a", 0.1, 1)]),
        _ranking(1, [_ranked("b", 0.2, 1)]),
    )
    candidates = (_candidate("a"), _candidate("b"))
    selections = {0: "a", 1: "b"}
    a = _plan(timing, rankings, candidates, selections, existing=("ch_user_1",))
    b = _plan(timing, rankings, candidates, selections, existing=("ch_user_1",))
    assert a == b


def test_42_source_inputs_unchanged() -> None:
    """42. source inputs unchanged."""
    timing = _timing([_event(0, Fraction(0, 1))])
    rankings = [_ranking(0, [_ranked("a", 0.1, 1)])]
    candidates = [_candidate("a")]
    selections = {0: "a"}
    existing = ["ch_user_1"]
    before = (
        copy.deepcopy(timing),
        copy.deepcopy(rankings),
        copy.deepcopy(candidates),
        copy.deepcopy(selections),
        list(existing),
    )
    _plan(timing, rankings, candidates, selections, existing)
    assert timing == before[0]
    assert rankings == before[1]
    assert candidates == before[2]
    assert selections == before[3]
    assert existing == before[4]


# ---------------------------------------------------------------------------
# Scope / ownership guards
# ---------------------------------------------------------------------------


def test_43_no_pattern_instance_created() -> None:
    """43. no Pattern instance created."""
    plan = _plan(
        _timing([_event(0, Fraction(0, 1))]),
        [_ranking(0, [_ranked("a", 0.1, 1)])],
        [_candidate("a")],
        {0: "a"},
    )
    assert not isinstance(plan, Pattern)
    assert all(not isinstance(x, Pattern) for x in plan.channel_bindings)
    assert all(not isinstance(x, Pattern) for x in plan.event_bindings)


def test_44_no_channel_instance_created() -> None:
    """44. no Channel instance created."""
    plan = _plan(
        _timing([_event(0, Fraction(0, 1))]),
        [_ranking(0, [_ranked("a", 0.1, 1)])],
        [_candidate("a")],
        {0: "a"},
    )
    assert all(not isinstance(x, Channel) for x in plan.channel_bindings)
    assert all(isinstance(x, PlannedGestureChannelBinding) for x in plan.channel_bindings)


def test_45_no_trigger_instance_created() -> None:
    """45. no Trigger instance created."""
    plan = _plan(
        _timing([_event(0, Fraction(0, 1))]),
        [_ranking(0, [_ranked("a", 0.1, 1)])],
        [_candidate("a")],
        {0: "a"},
    )
    assert all(not isinstance(x, Trigger) for x in plan.event_bindings)
    assert all(isinstance(x, PlannedGestureEventBinding) for x in plan.event_bindings)


def test_46_no_channel_rack_state_mutation_or_import() -> None:
    """46. no ChannelRackState mutation."""
    mod = importlib.import_module("src.gesture_pattern_binding")
    imported = _imported_module_names(mod)
    assert "channel_rack" not in imported
    assert "src.channel_rack" not in imported
    src = _source_text()
    assert "ChannelRackState" not in src
    assert "add_user_channel" not in src


def test_47_no_add_user_channel_call() -> None:
    """47. no add_user_channel() call."""
    tree = ast.parse(_source_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            assert name != "add_user_channel"


def test_48_no_default_on_triggers() -> None:
    """48. no DEFAULT_ON triggers."""
    src = _source_text()
    assert "DEFAULT_ON" not in src
    assert "_full_step_triggers" not in src
    plan = _plan(
        _timing([_event(0, Fraction(1, 3))]),
        [_ranking(0, [_ranked("a", 0.1, 1)])],
        [_candidate("a")],
        {0: "a"},
    )
    # Only the one planned event — not 16 DEFAULT_ON steps.
    assert len(plan.event_bindings) == 1


def test_49_no_db_access_or_write() -> None:
    """49. no DB access/write."""
    mod = importlib.import_module("src.gesture_pattern_binding")
    imported = _imported_module_names(mod)
    for banned in ("sqlite3", "sqlalchemy", "db", "src.db", "gesture_catalog_adapter"):
        assert banned not in imported
    src = _source_text()
    for token in ("init_db", "INSERT", "UPDATE", "DELETE", "sqlite3"):
        assert token not in src


def test_50_no_ranking_recomputation() -> None:
    """50. no ranking recomputation."""
    src = _source_text()
    for token in (
        "rank_gesture_library_candidates",
        "normalize_feature",
        "median_prototype",
    ):
        assert token not in src


def test_51_no_timing_recomputation() -> None:
    """51. no timing recomputation."""
    src = _source_text()
    assert "project_gesture_timing" not in src
    assert "onset_time_sec" not in src


def test_52_no_semantic_kick_snare_hat_naming() -> None:
    """52. no semantic Kick/Snare/Hat naming."""
    plan = _plan(
        _timing([_event(0, Fraction(0, 1)), _event(1, Fraction(1, 1))]),
        [
            _ranking(0, [_ranked("a", 0.1, 1)]),
            _ranking(1, [_ranked("b", 0.2, 1)]),
        ],
        [_candidate("a"), _candidate("b")],
        {0: "a", 1: "b"},
    )
    blob = repr(plan).lower()
    for label in ("kick", "snare", "hat", "hihat", "hi-hat", "live kit"):
        assert label not in blob
    src = _source_text().lower()
    for label in ("kick", "snare", "hihat", "live_kit_slot"):
        assert label not in src


def test_53_pattern_core_allocator_compatibility() -> None:
    """53. Pattern Core allocator compatibility."""
    existing = ["ch_user_2"]
    timing = _timing([_event(0, Fraction(0, 1))])
    plan = _plan(
        timing,
        [_ranking(0, [_ranked("a", 0.1, 1)])],
        [_candidate("a")],
        {0: "a"},
        existing=existing,
    )
    assert plan.channel_bindings[0].channel_id == allocate_user_channel_id(existing)
    mod = importlib.import_module("src.gesture_pattern_binding")
    imported = _imported_module_names(mod)
    assert imported <= _ALLOWED_IMPORT_ROOTS
    assert "allocate_user_channel_id" in _source_text()


def test_54_planned_quarters_trigger_compatible_test_only() -> None:
    """54. TEST-ONLY: planned event Fraction accepted by Trigger(position=...)."""
    plan = _plan(
        _timing([_event(0, Fraction(0, 1)), _event(0, Fraction(3, 8))]),
        [_ranking(0, [_ranked("a", 0.1, 1)])],
        [_candidate("a")],
        {0: "a"},
    )
    for event in plan.event_bindings:
        trigger = Trigger(channel_id="ch_kick", position=event.quarter_position)
        assert trigger.position == event.quarter_position
        assert type(trigger.position) is Fraction
    assert all(not isinstance(e, Trigger) for e in plan.event_bindings)


def test_event_bindings_preserve_timing_source_order() -> None:
    """Timing event order is #888 source truth — preserve, do not reorder."""
    # Intentionally not sorted by quarter: cluster 2 then cluster 1.
    timing = _timing(
        [
            _event(2, Fraction(1, 1)),
            _event(1, Fraction(0, 1)),
            _event(2, Fraction(2, 1)),
        ]
    )
    rankings = [
        _ranking(1, [_ranked("a", 0.1, 1)]),
        _ranking(2, [_ranked("b", 0.2, 1)]),
    ]
    plan = _plan(
        timing,
        rankings,
        [_candidate("a"), _candidate("b")],
        {1: "a", 2: "b"},
        length=Fraction(4, 1),
    )
    assert [(e.cluster_id, e.quarter_position) for e in plan.event_bindings] == [
        (2, Fraction(1, 1)),
        (1, Fraction(0, 1)),
        (2, Fraction(2, 1)),
    ]


def test_module_does_not_construct_pattern_channel_trigger() -> None:
    """AST: planner must not construct Pattern/Channel/Trigger."""
    tree = ast.parse(_source_text())
    banned = {"Pattern", "Trigger", "Channel", "ChannelRackState"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            assert name not in banned


def test_banned_imports_absent() -> None:
    mod = importlib.import_module("src.gesture_pattern_binding")
    imported = _imported_module_names(mod)
    for banned in _BANNED_IMPORT_ROOTS:
        assert banned not in imported
