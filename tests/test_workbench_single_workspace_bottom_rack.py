"""TEST_GATE / TEST_FREEZE — Single Workspace bottom Live Kit/Rack (#908).

Canonical authority:
- docs/WORKBENCH_SINGLE_WORKSPACE_CONTRACT.md
- docs/SESSION_OWNERSHIP_CONTRACT.md (#916 seams)
- live issues #908 / #920 (loop step-grid deferred)

Frozen v1:
- occupied + point-trigger-safe rows expose Step Grid
- loop-class rows show identity only (no DEFAULT_ON 16-step grid)
- empty groups omitted; empty slots disappear from occupied projection
- geometry: Library full-height; bottom band ~0.24; empty strip ~32px
- no product Screen-2 / enter_screen2 navigation
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.session_grid import TempoMap
from src.workbench_channel_rack import (
    BOTTOM_RACK_EMPTY_STRIP_PX,
    BOTTOM_RACK_HEIGHT_RATIO,
    project_bottom_rack_for_qml,
)
from src.workbench_controller import WorkbenchRow
from src.workbench_layout_solver import (
    CANONICAL_DEFAULT_RATIOS,
    PANEL_IDS,
    visible_panel_ids,
)
from src.workbench_session import compose_workbench_session


def _row(
    name: str,
    *,
    path: str | None = None,
    sample_class: str | None = "one_shot",
    pred_type: str = "Kick",
) -> WorkbenchRow:
    resolved = path or f"synthetic/{name}"
    return WorkbenchRow(
        display_name=name,
        relative_path=name,
        path=resolved,
        bpm=132.0,
        key="Am",
        key_conf=0.9,
        loudness=-12.0,
        brightness=3000.0,
        sample_class=sample_class,
        pred_type=pred_type,
        status="ok",
        details={"duration_sec": "0.2"},
    )


def _flat_rows(projection: dict) -> list[dict]:
    rows: list[dict] = []
    for group in projection.get("groups") or []:
        for row in group.get("rows") or []:
            rows.append({**row, "_group": group.get("name")})
    return rows


def _fake_transport():
    engine = MagicMock()
    engine.snapshot.return_value = SimpleNamespace(
        total_voice_count=0,
        voice_ids=(),
        voice_states=(),
        running=True,
        engine_frame=0,
    )
    return SimpleNamespace(
        tempo_map=TempoMap(bpm=120.0, sample_rate=48_000),
        sample_rate=48_000,
        engine_frame=0,
        ensure_engine_running=MagicMock(return_value=True),
        get_native_engine=MagicMock(return_value=engine),
        is_native_available=MagicMock(return_value=True),
        play=MagicMock(),
        start=MagicMock(),
        stop=MagicMock(),
        poll=MagicMock(),
        get_session_frame=MagicMock(return_value=0),
        get_engine_frame=MagicMock(return_value=0),
    )


def test_bottom_rack_geometry_constants_are_stable():
    assert BOTTOM_RACK_HEIGHT_RATIO == pytest.approx(0.24)
    assert BOTTOM_RACK_EMPTY_STRIP_PX == 32


def test_horizontal_elastic_panels_exclude_livekit():
    assert "livekit" not in PANEL_IDS
    assert PANEL_IDS == ("library", "browser", "harmony")
    assert set(CANONICAL_DEFAULT_RATIOS) == set(PANEL_IDS)
    assert abs(sum(CANONICAL_DEFAULT_RATIOS.values()) - 1.0) < 1e-12


def test_visible_panel_ids_no_longer_allocate_horizontal_livekit():
    assert visible_panel_ids(harmony_open=False, has_active_source=True) == (
        "library",
        "browser",
    )
    assert visible_panel_ids(harmony_open=True, has_active_source=True) == (
        "library",
        "browser",
        "harmony",
    )


def test_live_kit_assign_materializes_rack_without_enter_screen2():
    session = compose_workbench_session()
    assert session.channel_rack.state is None
    assert session.channel_rack.active_screen == "screen1"

    session.live_kit.assign(
        "Kick + Bass", "Kick", _row("kick.wav", sample_class="one_shot")
    )

    assert session.channel_rack.state is not None
    assert session.channel_rack.active_screen == "screen1"
    proj = session.channel_rack.projection()
    rows = _flat_rows(proj)
    assert len(rows) == 1
    assert rows[0]["live_kit_slot"] == "Kick"
    assert rows[0]["_group"] == "Kick + Bass"


def test_first_oneshot_assignment_creates_exactly_one_visible_row():
    session = compose_workbench_session()
    session.live_kit.assign(
        "Drums",
        "Closed Hat",
        _row("hat.wav", sample_class="oneshot", pred_type="Hat"),
    )
    rows = _flat_rows(session.channel_rack.projection())
    assert len(rows) == 1
    assert rows[0]["row_kind"] == "step"
    assert rows[0]["step_grid_enabled"] is True
    assert len(rows[0]["steps"]) == 16


def test_second_assignment_does_not_duplicate_existing_row():
    session = compose_workbench_session()
    session.live_kit.assign(
        "Kick + Bass", "Kick", _row("kick-a.wav", sample_class="one_shot")
    )
    session.live_kit.assign(
        "Kick + Bass", "Kick", _row("kick-b.wav", sample_class="one_shot")
    )
    rows = _flat_rows(session.channel_rack.projection())
    kick_rows = [r for r in rows if r["live_kit_slot"] == "Kick"]
    assert len(kick_rows) == 1
    assert "kick-b.wav" in kick_rows[0]["sample_path"].replace("\\", "/")


def test_empty_groups_omitted_from_bottom_projection():
    session = compose_workbench_session()
    session.live_kit.assign(
        "Kick + Bass", "Kick", _row("kick.wav", sample_class="one_shot")
    )
    groups = session.channel_rack.projection()["groups"]
    names = [g["name"] for g in groups]
    assert names == ["Kick + Bass"]
    assert "Drums" not in names
    assert "Melodic" not in names


def test_cleared_slot_disappears_from_occupied_projection():
    session = compose_workbench_session()
    session.live_kit.assign(
        "Kick + Bass", "Kick", _row("kick.wav", sample_class="one_shot")
    )
    assert len(_flat_rows(session.channel_rack.projection())) == 1

    session.live_kit._assignments["Kick + Bass"]["Kick"] = None
    session.channel_rack.ensure_state()

    proj = session.channel_rack.projection()
    assert _flat_rows(proj) == []
    assert proj.get("bottom_rack_materialized") is False
    assert proj.get("bottom_rack_height_px") == BOTTOM_RACK_EMPTY_STRIP_PX


def test_loop_class_assignment_has_identity_without_step_grid():
    session = compose_workbench_session()
    session.live_kit.assign(
        "Melodic",
        "Pad",
        _row("pad-loop.wav", sample_class="loop", pred_type="Pad"),
    )
    rows = _flat_rows(session.channel_rack.projection())
    assert len(rows) == 1
    row = rows[0]
    assert row["row_kind"] == "loop_identity"
    assert row["step_grid_enabled"] is False
    assert row["steps"] == []
    assert row["sample_label"]
    assert row["_group"] == "Melodic"


def test_mixed_oneshot_and_loop_projection_kinds():
    session = compose_workbench_session()
    session.live_kit.assign(
        "Kick + Bass", "Kick", _row("kick.wav", sample_class="one_shot")
    )
    session.live_kit.assign(
        "Atmos / FX",
        "Atmos",
        _row("atmos.wav", sample_class="loop", pred_type="Atmos"),
    )
    rows = _flat_rows(session.channel_rack.projection())
    by_slot = {r["live_kit_slot"]: r for r in rows}
    assert by_slot["Kick"]["step_grid_enabled"] is True
    assert by_slot["Atmos"]["step_grid_enabled"] is False
    assert by_slot["Atmos"]["row_kind"] == "loop_identity"


def test_ambiguous_sample_class_fails_closed_without_step_grid():
    session = compose_workbench_session()
    session.live_kit.assign(
        "Kick + Bass",
        "Bass",
        _row("mystery.wav", sample_class=None, pred_type="Bass"),
    )
    rows = _flat_rows(session.channel_rack.projection())
    assert len(rows) == 1
    assert rows[0]["step_grid_enabled"] is False
    assert rows[0]["row_kind"] == "loop_identity"


def test_bottom_projection_pure_helper_omits_empty_seed_channels():
    session = compose_workbench_session()
    session.live_kit.assign(
        "Kick + Bass", "Kick", _row("kick.wav", sample_class="one_shot")
    )
    state = session.channel_rack.ensure_state()
    assert len(state.channels) >= 11
    proj = project_bottom_rack_for_qml(state, session.live_kit)
    assert len(_flat_rows(proj)) == 1


def test_toggle_step_mutates_python_pattern_truth():
    session = compose_workbench_session()
    session.live_kit.assign(
        "Kick + Bass", "Kick", _row("kick.wav", sample_class="one_shot")
    )
    state = session.channel_rack.ensure_state()
    kick = next(ch for ch in state.channels if ch.live_kit_slot == "Kick")
    before = len(state.pattern.triggers)
    session.channel_rack.toggle_step(kick.channel_id, 0)
    after_state = session.channel_rack.state
    assert after_state is not None
    assert len(after_state.pattern.triggers) == before - 1
    row = _flat_rows(session.channel_rack.projection())[0]
    assert row["steps"][0] is False


def test_play_stop_route_through_channel_rack_controller(monkeypatch):
    session = compose_workbench_session()
    session.channel_rack._transport = _fake_transport()
    session.live_kit.assign(
        "Kick + Bass", "Kick", _row("kick.wav", sample_class="one_shot")
    )

    class FakeHandle:
        def __init__(self) -> None:
            self.player = SimpleNamespace(
                stop=lambda _eng: None,
                done=False,
                planned_count=16,
            )
            self.planned_count = 16
            self.scheduled_count = 1
            self.scheduled_voice_ids = (1,)

    monkeypatch.setattr(
        "src.workbench_channel_rack.play_channel_rack_once",
        lambda *_a, **_k: FakeHandle(),
    )
    monkeypatch.setattr(
        "src.workbench_channel_rack.warm_channel_rack_pcm",
        lambda *_a, **_k: (),
    )

    handle = session.channel_rack.play()
    assert handle is not None
    assert session.channel_rack.is_playing is True
    session.channel_rack.stop()
    assert session.channel_rack.is_playing is False


def test_product_surface_does_not_require_screen2_active_screen():
    session = compose_workbench_session()
    session.live_kit.assign(
        "Kick + Bass", "Kick", _row("kick.wav", sample_class="one_shot")
    )
    proj = session.channel_rack.projection()
    assert session.channel_rack.active_screen == "screen1"
    assert proj.get("product_surface") == "bottom_rack"
    assert len(_flat_rows(proj)) == 1


def test_ensure_state_idempotent_with_bottom_projection():
    session = compose_workbench_session()
    session.live_kit.assign(
        "Kick + Bass", "Kick", _row("kick.wav", sample_class="one_shot")
    )
    first = session.channel_rack.ensure_state()
    second = session.channel_rack.ensure_state()
    assert first.pattern.pattern_id == second.pattern.pattern_id
    assert len(_flat_rows(session.channel_rack.projection())) == 1


def test_materialized_bottom_height_ratio_metadata():
    empty = compose_workbench_session().channel_rack.projection()
    assert empty.get("bottom_rack_materialized") is False
    assert empty.get("bottom_rack_height_ratio") == pytest.approx(0.0)
    assert empty.get("bottom_rack_height_px") == BOTTOM_RACK_EMPTY_STRIP_PX

    session = compose_workbench_session()
    session.live_kit.assign(
        "Kick + Bass", "Kick", _row("kick.wav", sample_class="one_shot")
    )
    proj = session.channel_rack.projection()
    assert proj.get("bottom_rack_materialized") is True
    assert proj.get("bottom_rack_height_ratio") == pytest.approx(BOTTOM_RACK_HEIGHT_RATIO)
