from __future__ import annotations

import pytest

from src.haeftig import (
    HAEFTIG_BAR_COUNT,
    HAEFTIG_REGION_TYPE,
    HaeftigRegion,
    add_haeftig_region,
    select_haeftig_region,
)


def _downbeats(*, count: int = 50, spacing: int = 1_000) -> tuple[int, ...]:
    return tuple(index * spacing for index in range(count))


def _require_region(selection):
    assert selection.status == "ok"
    assert selection.reason_code is None
    assert selection.region is not None
    return selection.region


def test_exact_bar_40_selects_bar_24_to_bar_40():
    downbeats = _downbeats()
    region = _require_region(
        select_haeftig_region(
            downbeat_frames=downbeats,
            trigger_source_frame=downbeats[40],
            source_ref="track:test",
            grid_reliable=True,
        )
    )
    assert region.source_start_bar_index == 24
    assert region.source_end_bar_index_exclusive == 40
    assert region.source_start_frame == downbeats[24]
    assert region.source_end_frame_exclusive == downbeats[40]


def test_mid_bar_40_selects_bar_25_to_bar_41():
    downbeats = _downbeats()
    trigger = downbeats[40] + 321
    region = _require_region(
        select_haeftig_region(
            downbeat_frames=downbeats,
            trigger_source_frame=trigger,
            source_ref="track:test",
            grid_reliable=True,
        )
    )
    assert region.source_start_bar_index == 25
    assert region.source_end_bar_index_exclusive == 41
    assert region.source_start_frame == downbeats[25]
    assert region.source_end_frame_exclusive == downbeats[41]


def test_region_is_exactly_16_real_downbeat_intervals():
    downbeats = (
        0,
        103,
        241,
        390,
        551,
        733,
        910,
        1_101,
        1_311,
        1_542,
        1_790,
        2_057,
        2_341,
        2_642,
        2_960,
        3_295,
        3_647,
        4_018,
        4_409,
        4_820,
        5_252,
        5_705,
    )
    trigger = downbeats[20] - 17
    region = _require_region(
        select_haeftig_region(
            downbeat_frames=downbeats,
            trigger_source_frame=trigger,
            source_ref="track:variable-grid",
            grid_reliable=True,
        )
    )
    assert region.source_end_bar_index_exclusive - region.source_start_bar_index == 16
    assert region.source_start_frame in downbeats
    assert region.source_end_frame_exclusive in downbeats
    assert region.frame_count == region.source_end_frame_exclusive - region.source_start_frame


def test_less_than_16_complete_bars_is_unavailable():
    downbeats = _downbeats(count=16)
    selection = select_haeftig_region(
        downbeat_frames=downbeats,
        trigger_source_frame=downbeats[-1],
        source_ref="track:short",
        grid_reliable=True,
    )
    assert selection.status == "unavailable"
    assert selection.region is None
    assert selection.reason_code == "INSUFFICIENT_BARS"


def test_first_possible_exact_boundary_becomes_available_at_index_16():
    downbeats = _downbeats(count=17)
    region = _require_region(
        select_haeftig_region(
            downbeat_frames=downbeats,
            trigger_source_frame=downbeats[16],
            source_ref="track:first-valid",
            grid_reliable=True,
        )
    )
    assert region.source_start_bar_index == 0
    assert region.source_end_bar_index_exclusive == 16


def test_unreliable_or_missing_grid_fails_closed():
    unreliable = select_haeftig_region(
        downbeat_frames=_downbeats(),
        trigger_source_frame=20_000,
        source_ref="track:test",
        grid_reliable=False,
    )
    missing = select_haeftig_region(
        downbeat_frames=(),
        trigger_source_frame=0,
        source_ref="track:test",
        grid_reliable=True,
    )
    assert unreliable.status == "unavailable"
    assert unreliable.reason_code == "GRID_UNRELIABLE"
    assert missing.status == "unavailable"
    assert missing.reason_code == "GRID_UNRELIABLE"


@pytest.mark.parametrize(
    "downbeats",
    [
        (0, 1_000, 1_000, 2_000),
        (0, 2_000, 1_000, 3_000),
        (0, -1, 1_000),
        (0, 1_000.0, 2_000),
        (False, 1_000, 2_000),
    ],
)
def test_invalid_source_grid_fails_closed(downbeats):
    selection = select_haeftig_region(
        downbeat_frames=downbeats,
        trigger_source_frame=1_000,
        source_ref="track:test",
        grid_reliable=True,
    )
    assert selection.status == "unavailable"
    assert selection.reason_code == "INVALID_GRID"


@pytest.mark.parametrize("trigger", [-1, 1.5, True, None])
def test_invalid_trigger_fails_closed(trigger):
    selection = select_haeftig_region(
        downbeat_frames=_downbeats(),
        trigger_source_frame=trigger,
        source_ref="track:test",
        grid_reliable=True,
    )
    assert selection.status == "unavailable"
    assert selection.reason_code == "INVALID_TRIGGER"


def test_trigger_before_or_after_grid_is_unavailable():
    shifted = tuple(frame + 1_000 for frame in _downbeats())
    before = select_haeftig_region(
        downbeat_frames=shifted,
        trigger_source_frame=999,
        source_ref="track:test",
        grid_reliable=True,
    )
    after = select_haeftig_region(
        downbeat_frames=shifted,
        trigger_source_frame=shifted[-1] + 1,
        source_ref="track:test",
        grid_reliable=True,
    )
    assert before.reason_code == "TRIGGER_OUT_OF_RANGE"
    assert after.reason_code == "TRIGGER_OUT_OF_RANGE"


def test_exact_last_downbeat_is_valid_when_enough_bars_exist():
    downbeats = _downbeats(count=21)
    region = _require_region(
        select_haeftig_region(
            downbeat_frames=downbeats,
            trigger_source_frame=downbeats[-1],
            source_ref="track:last",
            grid_reliable=True,
        )
    )
    assert region.source_start_bar_index == 4
    assert region.source_end_bar_index_exclusive == 20


def test_selection_is_deterministic_for_identical_input():
    kwargs = dict(
        downbeat_frames=_downbeats(),
        trigger_source_frame=40_250,
        source_ref="track:stable",
        grid_reliable=True,
        trigger_session_frame=999_123,
        grid_source_ref="beat-grid:v1",
    )
    first = select_haeftig_region(**kwargs)
    second = select_haeftig_region(**kwargs)
    assert first == second


def test_session_context_does_not_change_authoritative_source_boundaries():
    base = dict(
        downbeat_frames=_downbeats(),
        trigger_source_frame=40_250,
        source_ref="track:stable",
        grid_reliable=True,
        grid_source_ref="beat-grid:v1",
    )
    first = _require_region(select_haeftig_region(**base, trigger_session_frame=100))
    later = _require_region(
        select_haeftig_region(**base, trigger_session_frame=999_999)
    )
    assert first.source_start_frame == later.source_start_frame
    assert first.source_end_frame_exclusive == later.source_end_frame_exclusive
    assert first.identity == later.identity
    assert first.trigger_session_frame != later.trigger_session_frame


def test_identical_region_is_deduplicated_but_overlap_is_allowed():
    downbeats = _downbeats()
    first = _require_region(
        select_haeftig_region(
            downbeat_frames=downbeats,
            trigger_source_frame=40_250,
            source_ref="track:test",
            grid_reliable=True,
        )
    )
    duplicate = _require_region(
        select_haeftig_region(
            downbeat_frames=downbeats,
            trigger_source_frame=40_250,
            trigger_session_frame=123_456,
            source_ref="track:test",
            grid_reliable=True,
        )
    )
    overlapping = _require_region(
        select_haeftig_region(
            downbeat_frames=downbeats,
            trigger_source_frame=41_250,
            source_ref="track:test",
            grid_reliable=True,
        )
    )
    regions, added_first = add_haeftig_region((), first)
    regions, added_duplicate = add_haeftig_region(regions, duplicate)
    regions, added_overlap = add_haeftig_region(regions, overlapping)
    assert added_first is True
    assert added_duplicate is False
    assert added_overlap is True
    assert regions == (first, overlapping)


def test_empty_source_ref_is_unavailable():
    selection = select_haeftig_region(
        downbeat_frames=_downbeats(),
        trigger_source_frame=40_000,
        source_ref="   ",
        grid_reliable=True,
    )
    assert selection.status == "unavailable"
    assert selection.reason_code == "INVALID_SOURCE_REF"


def test_manual_region_type_is_only_haeftig():
    assert HAEFTIG_REGION_TYPE == "HÄFTIG"
    assert HAEFTIG_BAR_COUNT == 16
    with pytest.raises(ValueError, match="only supported manual region type"):
        HaeftigRegion(
            region_type="DROP",
            source_ref="track:test",
            source_start_frame=0,
            source_end_frame_exclusive=16_000,
            source_start_bar_index=0,
            source_end_bar_index_exclusive=16,
            trigger_source_frame=16_000,
        )
