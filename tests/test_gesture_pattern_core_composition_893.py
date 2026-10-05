"""Frozen acceptance for R&D Slice 6 — Pattern Core composition (#680 / #893).

Docs authority: docs/GESTURE_PATTERN_CORE_COMPOSITION_RND_SLICE6.md

Frozen acceptance for implemented src/gesture_pattern_core_composition.py.
Synthetic fixtures only — no audio, no DB, no private catalogs.
"""

from __future__ import annotations

import ast
import copy
import importlib
import inspect
from fractions import Fraction
from pathlib import Path
from unittest import mock

import pytest

from src.gesture_library_ranking import (
    ClusterRanking,
    LibraryCandidate,
    RankedCandidate,
)
from src.gesture_pattern_binding import (
    GesturePatternBindingPlan,
    PlannedGestureChannelBinding,
    PlannedGestureEventBinding,
    plan_gesture_pattern_binding,
)
from src.gesture_timing_projection import (
    GestureTimingProjection,
    ProjectedGestureEvent,
)
from src.pattern_core import (
    Channel,
    Pattern,
    Trigger,
    require_triggers_reference_known_channels,
)

from src.gesture_pattern_core_composition import (
    GesturePatternCoreComposition,
    compose_gesture_pattern_core,
)

_MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "src" / "gesture_pattern_core_composition.py"
)

_ALLOWED_IMPORT_ROOTS = frozenset(
    {
        "annotations",
        "__future__",
        "dataclasses",
        "fractions",
        "typing",
        "collections",
        "collections.abc",
        "gesture_pattern_binding",
        "src.gesture_pattern_binding",
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
        "gesture_library_ranking",
        "src.gesture_library_ranking",
        "gesture_timing_projection",
        "src.gesture_timing_projection",
        "gesture_analysis",
        "src.gesture_analysis",
        "sqlite3",
        "sqlalchemy",
        "db",
        "src.db",
        "workbench_qml",
        "src.workbench_qml",
        "librosa",
        "soundfile",
        "numpy",
        "torch",
    }
)


def _candidate(sample_id: str, path: str | None = None) -> LibraryCandidate:
    # Align fixture fields with live #882 LibraryCandidate (freeze typo repair).
    return LibraryCandidate(
        sample_id=sample_id,
        path=path if path is not None else f"{sample_id}.wav",
        audio_class="oneshot",
        loudness=0.1,
        brightness=1000.0,
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
        source_onset_sec=float(pos) * 0.5,
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


def _plan_from_891(
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


def _channel_binding(
    cluster_id: int,
    channel_id: str,
    *,
    sample_id: str = "a",
    sample_path: str = "a.wav",
    selected_rank: int = 1,
    distance: float = 0.1,
) -> PlannedGestureChannelBinding:
    return PlannedGestureChannelBinding(
        cluster_id=cluster_id,
        channel_id=channel_id,
        sample_id=sample_id,
        sample_path=sample_path,
        selected_rank=selected_rank,
        distance=distance,
    )


def _event_binding(
    cluster_id: int,
    channel_id: str,
    quarter: Fraction,
) -> PlannedGestureEventBinding:
    return PlannedGestureEventBinding(
        cluster_id=cluster_id,
        channel_id=channel_id,
        quarter_position=quarter,
    )


def _ready_plan(
    *,
    channels: tuple[PlannedGestureChannelBinding, ...] = (),
    events: tuple[PlannedGestureEventBinding, ...] = (),
    length: Fraction = Fraction(4, 1),
    unresolved: tuple[int, ...] = (),
    ready: bool = True,
) -> GesturePatternBindingPlan:
    return GesturePatternBindingPlan(
        channel_bindings=channels,
        event_bindings=events,
        unresolved_cluster_ids=unresolved,
        pattern_length_quarters=length,
        ready_for_pattern=ready,
    )


def _simple_ready_plan() -> GesturePatternBindingPlan:
    return _ready_plan(
        channels=(_channel_binding(0, "ch_user_1", sample_path="kick.wav"),),
        events=(_event_binding(0, "ch_user_1", Fraction(1, 4)),),
        length=Fraction(4, 1),
    )


def _source_text() -> str:
    return _MODULE_PATH.read_text(encoding="utf-8")


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


def _compose(plan: GesturePatternBindingPlan, pattern_id: str = "gesture-pat-1"):
    return compose_gesture_pattern_core(plan, pattern_id=pattern_id)


# ---------------------------------------------------------------------------
# Happy path / object identity / preservation
# ---------------------------------------------------------------------------


def test_01_one_ready_binding_event_one_channel_trigger_pattern() -> None:
    """1. one ready binding/event → one Channel + one Trigger + one Pattern."""
    plan = _simple_ready_plan()
    result = _compose(plan, "pat-1")
    assert isinstance(result, GesturePatternCoreComposition)
    assert len(result.channels) == 1
    assert len(result.pattern.triggers) == 1
    assert result.pattern.pattern_id == "pat-1"


def test_02_result_uses_actual_pattern_core_channel() -> None:
    """2. result uses actual pattern_core.Channel."""
    result = _compose(_simple_ready_plan())
    assert len(result.channels) == 1
    assert type(result.channels[0]) is Channel
    assert isinstance(result.channels[0], Channel)


def test_03_result_uses_actual_pattern_core_trigger() -> None:
    """3. result uses actual pattern_core.Trigger."""
    result = _compose(_simple_ready_plan())
    assert len(result.pattern.triggers) == 1
    assert type(result.pattern.triggers[0]) is Trigger
    assert isinstance(result.pattern.triggers[0], Trigger)


def test_04_result_uses_actual_pattern_core_pattern() -> None:
    """4. result uses actual pattern_core.Pattern."""
    result = _compose(_simple_ready_plan())
    assert type(result.pattern) is Pattern
    assert isinstance(result.pattern, Pattern)


def test_05_channel_id_preserved_exactly() -> None:
    """5. channel_id preserved exactly."""
    plan = _ready_plan(
        channels=(_channel_binding(7, "ch_user_42"),),
        events=(_event_binding(7, "ch_user_42", Fraction(0, 1)),),
    )
    result = _compose(plan)
    assert result.channels[0].channel_id == "ch_user_42"
    assert result.pattern.triggers[0].channel_id == "ch_user_42"


def test_06_sample_path_preserved_exactly() -> None:
    """6. sample_path preserved exactly."""
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1", sample_path="samples/exact/path.wav"),),
        events=(_event_binding(0, "ch_user_1", Fraction(0, 1)),),
    )
    result = _compose(plan)
    assert result.channels[0].sample_path == "samples/exact/path.wav"


def test_07_user_provenance_none_none() -> None:
    """7. user provenance = None / None."""
    result = _compose(_simple_ready_plan())
    ch = result.channels[0]
    assert ch.live_kit_group is None
    assert ch.live_kit_slot is None


def test_08_repeated_events_one_channel_n_triggers() -> None:
    """8. repeated events → one Channel + N Triggers."""
    positions = (Fraction(0, 1), Fraction(1, 2), Fraction(3, 2))
    plan = _ready_plan(
        channels=(_channel_binding(3, "ch_user_1"),),
        events=tuple(_event_binding(3, "ch_user_1", p) for p in positions),
    )
    result = _compose(plan)
    assert len(result.channels) == 1
    assert len(result.pattern.triggers) == 3
    assert [t.position for t in result.pattern.triggers] == list(positions)


def test_09_two_clusters_two_channels() -> None:
    """9. two clusters → two Channels."""
    plan = _ready_plan(
        channels=(
            _channel_binding(1, "ch_user_1", sample_id="a", sample_path="a.wav"),
            _channel_binding(2, "ch_user_2", sample_id="b", sample_path="b.wav"),
        ),
        events=(
            _event_binding(1, "ch_user_1", Fraction(0, 1)),
            _event_binding(2, "ch_user_2", Fraction(1, 1)),
        ),
    )
    result = _compose(plan)
    assert len(result.channels) == 2
    assert [c.channel_id for c in result.channels] == ["ch_user_1", "ch_user_2"]


def test_10_same_path_across_clusters_separate_channels() -> None:
    """10. same path across clusters → separate Channels."""
    plan = _ready_plan(
        channels=(
            _channel_binding(1, "ch_user_1", sample_id="42", sample_path="shared.wav"),
            _channel_binding(2, "ch_user_2", sample_id="42", sample_path="shared.wav"),
        ),
        events=(
            _event_binding(1, "ch_user_1", Fraction(0, 1)),
            _event_binding(2, "ch_user_2", Fraction(1, 1)),
        ),
    )
    result = _compose(plan)
    assert len(result.channels) == 2
    assert result.channels[0].channel_id != result.channels[1].channel_id
    assert result.channels[0].sample_path == result.channels[1].sample_path == "shared.wav"


def test_11_quarter_fractions_preserved_exactly() -> None:
    """11. quarter Fractions preserved exactly."""
    pos = Fraction(3, 10)
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1"),),
        events=(_event_binding(0, "ch_user_1", pos),),
    )
    result = _compose(plan)
    trigger = result.pattern.triggers[0]
    assert trigger.position == pos
    assert type(trigger.position) is Fraction


def test_12_no_quantization() -> None:
    """12. no quantization."""
    # Unquantized position that is not on a 16th grid.
    pos = Fraction(1, 7)
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1"),),
        events=(_event_binding(0, "ch_user_1", pos),),
        length=Fraction(4, 1),
    )
    result = _compose(plan)
    assert result.pattern.triggers[0].position == Fraction(1, 7)
    src = _source_text().lower()
    for token in ("quantize", "snap", "swing", "groove", "round("):
        assert token not in src


def test_13_plan_pattern_length_preserved_exactly() -> None:
    """13. plan Pattern length preserved exactly."""
    length = Fraction(17, 4)
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1"),),
        events=(_event_binding(0, "ch_user_1", Fraction(0, 1)),),
        length=length,
    )
    result = _compose(plan)
    assert result.pattern.length_quarter_notes == length
    assert type(result.pattern.length_quarter_notes) is Fraction


def test_14_explicit_pattern_id_preserved() -> None:
    """14. explicit pattern_id preserved."""
    result = _compose(_simple_ready_plan(), pattern_id="explicit-gesture-42")
    assert result.pattern.pattern_id == "explicit-gesture-42"


# ---------------------------------------------------------------------------
# Fail-closed gates
# ---------------------------------------------------------------------------


def test_15_empty_pattern_id_rejected() -> None:
    """15. empty pattern_id rejected."""
    with pytest.raises((TypeError, ValueError)):
        _compose(_simple_ready_plan(), pattern_id="")


def test_16_non_string_pattern_id_rejected() -> None:
    """16. non-string pattern_id rejected."""
    with pytest.raises((TypeError, ValueError)):
        compose_gesture_pattern_core(_simple_ready_plan(), pattern_id=123)  # type: ignore[arg-type]


def test_17_non_ready_plan_rejected() -> None:
    """17. non-ready plan rejected."""
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1"),),
        events=(_event_binding(0, "ch_user_1", Fraction(0, 1)),),
        unresolved=(1,),
        ready=False,
    )
    with pytest.raises((TypeError, ValueError)):
        _compose(plan)


def test_18_unresolved_plan_rejected() -> None:
    """18. unresolved plan rejected."""
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1"),),
        events=(_event_binding(0, "ch_user_1", Fraction(0, 1)),),
        unresolved=(9,),
        ready=False,
    )
    assert plan.unresolved_cluster_ids == (9,)
    with pytest.raises((TypeError, ValueError)):
        _compose(plan)


def test_19_spoofed_ready_with_unresolved_ids_rejected() -> None:
    """19. spoofed ready=True + unresolved IDs rejected."""
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1"),),
        events=(_event_binding(0, "ch_user_1", Fraction(0, 1)),),
        unresolved=(3,),
        ready=True,
    )
    with pytest.raises((TypeError, ValueError)):
        _compose(plan)


def test_20_duplicate_planned_channel_ids_rejected() -> None:
    """20. duplicate planned channel IDs rejected."""
    plan = _ready_plan(
        channels=(
            _channel_binding(1, "ch_user_1"),
            _channel_binding(2, "ch_user_1"),
        ),
        events=(
            _event_binding(1, "ch_user_1", Fraction(0, 1)),
            _event_binding(2, "ch_user_1", Fraction(1, 1)),
        ),
    )
    with pytest.raises((TypeError, ValueError)):
        _compose(plan)


def test_21_duplicate_planned_cluster_ids_rejected() -> None:
    """21. duplicate planned cluster IDs rejected."""
    plan = _ready_plan(
        channels=(
            _channel_binding(1, "ch_user_1"),
            _channel_binding(1, "ch_user_2"),
        ),
        events=(
            _event_binding(1, "ch_user_1", Fraction(0, 1)),
            _event_binding(1, "ch_user_2", Fraction(1, 1)),
        ),
    )
    with pytest.raises((TypeError, ValueError)):
        _compose(plan)


def test_22_empty_sample_path_rejected() -> None:
    """22. empty sample_path rejected."""
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1", sample_path=""),),
        events=(_event_binding(0, "ch_user_1", Fraction(0, 1)),),
    )
    with pytest.raises((TypeError, ValueError)):
        _compose(plan)


def test_23_event_unknown_channel_rejected() -> None:
    """23. event unknown channel rejected."""
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1"),),
        events=(_event_binding(0, "ch_user_99", Fraction(0, 1)),),
    )
    with pytest.raises((TypeError, ValueError)):
        _compose(plan)


def test_24_event_cluster_channel_mismatch_rejected() -> None:
    """24. event cluster/channel mismatch rejected."""
    plan = _ready_plan(
        channels=(
            _channel_binding(1, "ch_user_1"),
            _channel_binding(2, "ch_user_2"),
        ),
        events=(
            # cluster 1 must map to ch_user_1, not ch_user_2
            _event_binding(1, "ch_user_2", Fraction(0, 1)),
            _event_binding(2, "ch_user_2", Fraction(1, 1)),
        ),
    )
    with pytest.raises((TypeError, ValueError)):
        _compose(plan)


def test_25_event_non_fraction_position_rejected() -> None:
    """25. event non-Fraction position rejected."""
    # Bypass dataclass construction by object.__setattr__ on a copy-like path:
    # PlannedGestureEventBinding validates nothing on Fraction type, so craft via
    # object mutation after replace is not available — build with Fraction then
    # overwrite using object.__setattr__ on a frozen instance is blocked.
    # Use a hand-built instance via GesturePatternBindingPlan with a mock-like
    # event object that has the right attributes but wrong position type.
    bad_event = PlannedGestureEventBinding(
        cluster_id=0,
        channel_id="ch_user_1",
        quarter_position=Fraction(1, 4),
    )
    object.__setattr__(bad_event, "quarter_position", 0.25)
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1"),),
        events=(bad_event,),
    )
    with pytest.raises((TypeError, ValueError)):
        _compose(plan)


def test_26_event_position_equal_length_rejected() -> None:
    """26. event position == length rejected."""
    length = Fraction(4, 1)
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1"),),
        events=(_event_binding(0, "ch_user_1", length),),
        length=length,
    )
    with pytest.raises((TypeError, ValueError)):
        _compose(plan)


def test_27_event_position_greater_than_length_rejected() -> None:
    """27. event position > length rejected."""
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1"),),
        events=(_event_binding(0, "ch_user_1", Fraction(5, 1)),),
        length=Fraction(4, 1),
    )
    with pytest.raises((TypeError, ValueError)):
        _compose(plan)


def test_28_valid_exclusive_end_position_accepted() -> None:
    """28. valid exclusive-end position accepted."""
    length = Fraction(4, 1)
    just_before = length - Fraction(1, 16)
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1"),),
        events=(_event_binding(0, "ch_user_1", just_before),),
        length=length,
    )
    result = _compose(plan)
    assert result.pattern.triggers[0].position == just_before
    assert result.pattern.triggers[0].position < result.pattern.length_quarter_notes


def test_29_non_monotonic_ready_plan_not_silently_reordered() -> None:
    """29. malformed non-monotonic ready plan does not get silently reordered."""
    plan = _ready_plan(
        channels=(
            _channel_binding(1, "ch_user_1"),
            _channel_binding(2, "ch_user_2"),
        ),
        events=(
            _event_binding(2, "ch_user_2", Fraction(1, 1)),
            _event_binding(1, "ch_user_1", Fraction(0, 1)),  # earlier position later
            _event_binding(2, "ch_user_2", Fraction(2, 1)),
        ),
    )
    with pytest.raises((TypeError, ValueError)):
        _compose(plan)


def test_30_valid_event_order_unchanged_after_pattern_creation() -> None:
    """30. valid event order remains unchanged after Pattern creation."""
    positions = [Fraction(0, 1), Fraction(1, 3), Fraction(2, 3), Fraction(5, 2)]
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1"),),
        events=tuple(_event_binding(0, "ch_user_1", p) for p in positions),
        length=Fraction(4, 1),
    )
    result = _compose(plan)
    assert [t.position for t in result.pattern.triggers] == positions
    assert [t.channel_id for t in result.pattern.triggers] == ["ch_user_1"] * 4


# ---------------------------------------------------------------------------
# Boundary: no reallocation / rack / DEFAULT_ON / recomputation
# ---------------------------------------------------------------------------


def test_31_no_channel_reallocation() -> None:
    """31. no channel reallocation."""
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_7"),),
        events=(_event_binding(0, "ch_user_7", Fraction(0, 1)),),
    )
    result = _compose(plan)
    assert result.channels[0].channel_id == "ch_user_7"
    assert result.pattern.triggers[0].channel_id == "ch_user_7"


def test_32_no_allocate_user_channel_id_call() -> None:
    """32. no allocate_user_channel_id call."""
    src = _source_text()
    assert "allocate_user_channel_id" not in src
    with mock.patch(
        "src.pattern_core.allocate_user_channel_id",
        side_effect=AssertionError("allocate_user_channel_id must not be called"),
    ):
        result = _compose(_simple_ready_plan())
    assert result.channels[0].channel_id == "ch_user_1"


def test_33_no_add_user_channel_call() -> None:
    """33. no add_user_channel call."""
    src = _source_text()
    assert "add_user_channel" not in src
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            assert name != "add_user_channel"


def test_34_no_default_on() -> None:
    """34. no DEFAULT_ON."""
    src = _source_text()
    assert "DEFAULT_ON" not in src
    assert "_full_step_triggers" not in src
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1"),),
        events=(_event_binding(0, "ch_user_1", Fraction(1, 3)),),
    )
    result = _compose(plan)
    # Only the one planned event — not 16 DEFAULT_ON steps.
    assert len(result.pattern.triggers) == 1


def test_35_trigger_count_equals_event_binding_count() -> None:
    """35. Trigger count == event binding count."""
    events = (
        _event_binding(0, "ch_user_1", Fraction(0, 1)),
        _event_binding(0, "ch_user_1", Fraction(1, 2)),
        _event_binding(0, "ch_user_1", Fraction(5, 4)),
    )
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1"),),
        events=events,
    )
    result = _compose(plan)
    assert len(result.pattern.triggers) == len(plan.event_bindings) == 3


def test_36_no_ranking_recomputation() -> None:
    """36. no ranking recomputation."""
    src = _source_text()
    for token in (
        "rank_gesture_library_candidates",
        "rank_gesture_against_catalog",
        "normalize_feature",
        "median_prototype",
    ):
        assert token not in src


def test_37_no_timing_recomputation() -> None:
    """37. no timing recomputation."""
    src = _source_text()
    assert "project_gesture_timing" not in src
    assert "onset_time_sec" not in src


def test_38_no_catalog_db_access() -> None:
    """38. no catalog/DB access."""
    mod = importlib.import_module("src.gesture_pattern_core_composition")
    imported = _imported_module_names(mod)
    for banned in (
        "sqlite3",
        "sqlalchemy",
        "db",
        "src.db",
        "gesture_catalog_adapter",
        "src.gesture_catalog_adapter",
    ):
        assert banned not in imported
    src = _source_text()
    for token in ("init_db", "INSERT", "UPDATE", "DELETE", "sqlite3", "load_gesture_library"):
        assert token not in src


def test_39_no_selection_recomputation() -> None:
    """39. no selection recomputation."""
    src = _source_text()
    assert "plan_gesture_pattern_binding" not in src
    # Composer must not invent rank-1 acceptance / auto-resolve.
    assert "selected_rank == 1" not in src
    assert "auto-select" not in src.lower()
    assert "auto_select" not in src.lower()
    assert "rank_1" not in src.lower()


def test_40_no_pattern_length_recomputation() -> None:
    """40. no Pattern-length recomputation."""
    src = _source_text()
    for token in (
        "projected_duration_quarters",
        "source_duration",
        "last_onset",
        "next_beat",
        "next_bar",
    ):
        assert token not in src
    length = Fraction(11, 3)
    plan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1"),),
        events=(_event_binding(0, "ch_user_1", Fraction(0, 1)),),
        length=length,
    )
    assert _compose(plan).pattern.length_quarter_notes == length


def test_41_no_channel_rack_state() -> None:
    """41. no ChannelRackState."""
    src = _source_text()
    assert "ChannelRackState" not in src
    assert "build_channel_rack_state" not in src
    assert "reconcile_live_kit" not in src
    result = _compose(_simple_ready_plan())
    assert not hasattr(result, "rack")
    assert not hasattr(result, "channel_rack")
    assert set(getattr(result, "__dataclass_fields__", {})) <= {"channels", "pattern"} or (
        hasattr(result, "channels") and hasattr(result, "pattern")
    )


def test_42_input_plan_unchanged() -> None:
    """42. input plan unchanged."""
    plan = _simple_ready_plan()
    before = copy.deepcopy(plan)
    _compose(plan)
    assert plan == before
    assert plan.channel_bindings == before.channel_bindings
    assert plan.event_bindings == before.event_bindings


def test_43_identical_input_twice_equal_composition() -> None:
    """43. identical input twice → equal composition."""
    plan = _simple_ready_plan()
    a = _compose(plan, "same-id")
    b = _compose(plan, "same-id")
    assert a == b
    assert a.channels == b.channels
    assert a.pattern == b.pattern


def test_44_every_trigger_references_composed_channel() -> None:
    """44. every trigger references a composed channel."""
    plan = _ready_plan(
        channels=(
            _channel_binding(1, "ch_user_1"),
            _channel_binding(2, "ch_user_2"),
        ),
        events=(
            _event_binding(1, "ch_user_1", Fraction(0, 1)),
            _event_binding(2, "ch_user_2", Fraction(1, 2)),
            _event_binding(1, "ch_user_1", Fraction(1, 1)),
        ),
    )
    result = _compose(plan)
    known = {c.channel_id for c in result.channels}
    assert known == {"ch_user_1", "ch_user_2"}
    for trigger in result.pattern.triggers:
        assert trigger.channel_id in known


def test_45_pattern_core_membership_helper_accepts_graph() -> None:
    """45. Pattern-Core membership helper accepts graph."""
    result = _compose(_simple_ready_plan())
    require_triggers_reference_known_channels(
        result.pattern.triggers,
        known_channel_ids=[c.channel_id for c in result.channels],
    )


def test_46_valid_891_generated_plan_composes_directly() -> None:
    """46. valid #891-generated plan composes directly."""
    timing = _timing(
        [
            _event(0, Fraction(0, 1)),
            _event(0, Fraction(1, 2)),
            _event(1, Fraction(5, 4)),
        ]
    )
    rankings = [
        _ranking(0, [_ranked("a", 0.1, 1)]),
        _ranking(1, [_ranked("b", 0.2, 1)]),
    ]
    plan = _plan_from_891(
        timing,
        rankings,
        [_candidate("a"), _candidate("b")],
        {0: "a", 1: "b"},
        length=Fraction(4, 1),
    )
    assert plan.ready_for_pattern is True
    assert plan.unresolved_cluster_ids == ()
    result = _compose(plan, "from-891")
    assert len(result.channels) == len(plan.channel_bindings) == 2
    assert len(result.pattern.triggers) == len(plan.event_bindings) == 3
    assert result.pattern.pattern_id == "from-891"
    assert result.pattern.length_quarter_notes == plan.pattern_length_quarters
    assert [c.channel_id for c in result.channels] == [
        b.channel_id for b in plan.channel_bindings
    ]
    assert [t.position for t in result.pattern.triggers] == [
        e.quarter_position for e in plan.event_bindings
    ]


def test_47_empty_ready_plan_follows_docs_gate() -> None:
    """47. empty ready plan behavior exactly follows frozen DOCS_GATE decision."""
    # Live #891: empty timing → ready_for_pattern=True, empty bindings.
    empty_timing = _timing(())
    plan = _plan_from_891(empty_timing, [], [], {}, length=Fraction(8, 1))
    assert plan.ready_for_pattern is True
    assert plan.channel_bindings == ()
    assert plan.event_bindings == ()
    assert plan.unresolved_cluster_ids == ()

    result = _compose(plan, "empty-gesture")
    assert result.channels == ()
    assert result.pattern.triggers == ()
    assert result.pattern.pattern_id == "empty-gesture"
    assert result.pattern.length_quarter_notes == Fraction(8, 1)

    # Orphan planned channel (not producible by #891) must fail closed.
    orphan = _ready_plan(
        channels=(_channel_binding(0, "ch_user_1"),),
        events=(),
    )
    with pytest.raises((TypeError, ValueError)):
        _compose(orphan)


# ---------------------------------------------------------------------------
# Protected suites / module boundary (items 48-52 are runner-level;
# module AST/import guards freeze the composition boundary here too)
# ---------------------------------------------------------------------------


def test_48_module_import_boundary_allows_only_declared_roots() -> None:
    """48. module import boundary aligned with docs (supports protected #891 GREEN)."""
    mod = importlib.import_module("src.gesture_pattern_core_composition")
    imported = _imported_module_names(mod)
    assert imported <= _ALLOWED_IMPORT_ROOTS
    for banned in _BANNED_IMPORT_ROOTS:
        assert banned not in imported


def test_49_module_does_not_call_upstream_planner_or_timing() -> None:
    """49. no upstream planner/timing calls (supports #888 suite independence)."""
    src = _source_text()
    for token in (
        "plan_gesture_pattern_binding",
        "project_gesture_timing",
        "analyze_gesture_audio",
    ):
        assert token not in src


def test_50_module_does_not_call_ranking_or_catalog() -> None:
    """50. no ranking/catalog calls (supports #882/#886 suite independence)."""
    src = _source_text()
    for token in (
        "rank_gesture_library_candidates",
        "rank_gesture_against_catalog",
        "load_gesture_library_candidates",
    ):
        assert token not in src


def test_51_module_does_not_mutate_pattern_core_or_rack_helpers() -> None:
    """51. no Pattern Core mutation / Channel Rack DEFAULT_ON helpers."""
    src = _source_text()
    for token in (
        "add_user_channel",
        "assign_user_channel_sample",
        "reconcile_live_kit_sample_assignments",
        "build_channel_rack_state",
        "DEFAULT_ON",
        "allocate_user_channel_id",
    ):
        assert token not in src
    # Membership helper is allowed / expected.
    assert "require_triggers_reference_known_channels" in src


def test_52_public_seam_signature_frozen() -> None:
    """52. public seam signature frozen for sequencer-compatible composition delta."""
    sig = inspect.signature(compose_gesture_pattern_core)
    params = list(sig.parameters.values())
    assert params[0].name == "plan"
    assert params[0].kind in (
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    )
    assert "pattern_id" in sig.parameters
    assert sig.parameters["pattern_id"].kind == inspect.Parameter.KEYWORD_ONLY
    # Result type exposes channels + pattern only (composition delta).
    result = _compose(_simple_ready_plan(), "sig-check")
    assert hasattr(result, "channels")
    assert hasattr(result, "pattern")
    assert isinstance(result.pattern, Pattern)
