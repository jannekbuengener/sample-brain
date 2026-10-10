"""#1070 Edit docking topology — TEST_GATE (frozen after RED).

Python-owned bounded Edit/Kit topology: feature gate, lock, move/swap/reflow,
materialization, persistence/migration, intent typing. No QML in this slice.
"""

from __future__ import annotations

import copy
import json
import math
from dataclasses import fields
from pathlib import Path

import pytest

from src.workbench_feature_settings import (
    WorkbenchFeatureSettings,
    load_workbench_feature_settings,
    replace_workbench_feature_settings,
    save_workbench_feature_settings,
)
from src import workbench_edit_docking as edit_docking
from src.workbench_layout_solver import (
    CANONICAL_DEFAULT_RATIOS,
    apply_divider_drag,
    load_layout_preferences,
    normalize_ratios,
    save_layout_preferences,
)


CANONICAL_ORDER = ("library", "browser", "harmony", "live_kit")
CONTRACT_DOC = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "WORKBENCH_EDIT_DOCKING_TOPOLOGY.md"
)


def _mat(
    *,
    library: bool = True,
    browser: bool = True,
    harmony: bool = True,
    live_kit: bool = True,
):
    return edit_docking.EditDockingMaterialization(
        library=library,
        browser=browser,
        harmony=harmony,
        live_kit=live_kit,
    )


def _state(
    *,
    panel_order=CANONICAL_ORDER,
    lock_state="LOCKED",
    schema_version=None,
):
    kwargs = {
        "panel_order": tuple(panel_order),
        "lock_state": lock_state,
    }
    if schema_version is not None:
        kwargs["schema_version"] = schema_version
    return edit_docking.EditDockingState(**kwargs)


def _features(*, docking: bool = True) -> WorkbenchFeatureSettings:
    return WorkbenchFeatureSettings(
        gesture_rack_apply_enabled=False,
        workspace_panel_docking_enabled=docking,
    )


# ---------------------------------------------------------------------------
# Contract surface
# ---------------------------------------------------------------------------


def test_contract_doc_freezes_edit_only_boundary():
    text = CONTRACT_DOC.read_text(encoding="utf-8")
    assert "workspace_panel_docking_enabled" in text
    assert "LOCKED" in text and "UNLOCKED" in text
    assert "arrangement" in text.lower()
    assert "live_kit" in text
    assert "channel_rack" in text or "step_sequencer" in text
    assert "#1071" in text
    assert "No QML" in text or "does **not** implement QML" in text


def test_canonical_panel_and_slot_identities_are_stable():
    assert edit_docking.EDIT_PANEL_IDS == frozenset(CANONICAL_ORDER)
    assert edit_docking.CANONICAL_PANEL_ORDER == CANONICAL_ORDER
    assert edit_docking.LOCK_LOCKED == "LOCKED"
    assert edit_docking.LOCK_UNLOCKED == "UNLOCKED"
    assert "panel_move" in edit_docking.INTENT_KINDS
    assert "sample_drag" in edit_docking.INTENT_KINDS
    assert "resize" in edit_docking.INTENT_KINDS
    assert "collapse" in edit_docking.INTENT_KINDS


def test_feature_settings_exposes_docking_flag_default_off():
    settings = WorkbenchFeatureSettings()
    assert settings.workspace_panel_docking_enabled is False
    names = {f.name for f in fields(WorkbenchFeatureSettings)}
    assert "workspace_panel_docking_enabled" in names


# ---------------------------------------------------------------------------
# 1) Feature OFF → no docking mutation
# ---------------------------------------------------------------------------


def test_feature_off_rejects_valid_looking_move():
    state = _state(lock_state="UNLOCKED", panel_order=CANONICAL_ORDER)
    intent = edit_docking.PanelMoveIntent(
        panel_id="library",
        target_slot_id="edit_slot_1",
    )
    result = edit_docking.apply_edit_docking_intent(
        state,
        intent,
        features=_features(docking=False),
        materialization=_mat(),
    )
    assert result.accepted is False
    assert result.state == state
    assert result.state.panel_order == CANONICAL_ORDER


# ---------------------------------------------------------------------------
# 2) ON + LOCKED → reject
# ---------------------------------------------------------------------------


def test_feature_on_locked_rejects_valid_looking_move():
    state = _state(lock_state="LOCKED", panel_order=CANONICAL_ORDER)
    intent = edit_docking.PanelMoveIntent(
        panel_id="library",
        target_slot_id="edit_slot_2",
    )
    result = edit_docking.apply_edit_docking_intent(
        state,
        intent,
        features=_features(docking=True),
        materialization=_mat(),
    )
    assert result.accepted is False
    assert result.state.panel_order == CANONICAL_ORDER
    assert result.state.lock_state == "LOCKED"


# ---------------------------------------------------------------------------
# 3) ON + UNLOCKED → valid move commits once
# ---------------------------------------------------------------------------


def test_feature_on_unlocked_commits_valid_move_once():
    state = _state(lock_state="UNLOCKED", panel_order=CANONICAL_ORDER)
    intent = edit_docking.PanelMoveIntent(
        panel_id="library",
        target_slot_id="edit_slot_1",
    )
    result = edit_docking.apply_edit_docking_intent(
        state,
        intent,
        features=_features(docking=True),
        materialization=_mat(),
    )
    assert result.accepted is True
    assert result.state.panel_order == ("browser", "library", "harmony", "live_kit")
    # Second identical apply against already-committed state is deterministic.
    again = edit_docking.apply_edit_docking_intent(
        result.state,
        intent,
        features=_features(docking=True),
        materialization=_mat(),
    )
    assert again.accepted is True
    assert again.state.panel_order == result.state.panel_order


# ---------------------------------------------------------------------------
# 4) Swap / reflow deterministic
# ---------------------------------------------------------------------------


def test_valid_swap_is_deterministic():
    state = _state(lock_state="UNLOCKED", panel_order=CANONICAL_ORDER)
    intent = edit_docking.PanelSwapIntent(panel_a="browser", panel_b="harmony")
    first = edit_docking.apply_edit_docking_intent(
        state,
        intent,
        features=_features(docking=True),
        materialization=_mat(),
    )
    second = edit_docking.apply_edit_docking_intent(
        state,
        intent,
        features=_features(docking=True),
        materialization=_mat(),
    )
    assert first.accepted is True
    assert first.state.panel_order == ("library", "harmony", "browser", "live_kit")
    assert second.state == first.state


def test_reflow_compacts_after_dematerialization():
    state = _state(
        lock_state="UNLOCKED",
        panel_order=("library", "browser", "harmony", "live_kit"),
    )
    active = edit_docking.active_panel_order(
        state,
        materialization=_mat(harmony=False, live_kit=False),
    )
    assert active == ("library", "browser")
    slots = edit_docking.active_slot_assignments(
        state,
        materialization=_mat(harmony=False, live_kit=False),
    )
    assert slots == {"edit_slot_0": "library", "edit_slot_1": "browser"}
    assert "edit_slot_2" not in slots
    assert "edit_slot_3" not in slots


# ---------------------------------------------------------------------------
# 5) Invalid panel / slot → no mutation
# ---------------------------------------------------------------------------


def test_invalid_panel_or_slot_rejects_without_mutation():
    state = _state(lock_state="UNLOCKED")
    bad_panel = edit_docking.apply_edit_docking_intent(
        state,
        edit_docking.PanelMoveIntent(panel_id="inspector_x", target_slot_id="edit_slot_0"),
        features=_features(docking=True),
        materialization=_mat(),
    )
    bad_slot = edit_docking.apply_edit_docking_intent(
        state,
        edit_docking.PanelMoveIntent(panel_id="library", target_slot_id="floating_canvas"),
        features=_features(docking=True),
        materialization=_mat(),
    )
    assert bad_panel.accepted is False
    assert bad_slot.accepted is False
    assert bad_panel.state == state
    assert bad_slot.state == state


# ---------------------------------------------------------------------------
# 6) Duplicate / illegal persisted topology → safe fallback
# ---------------------------------------------------------------------------


def test_duplicate_illegal_persisted_topology_falls_back(tmp_path: Path):
    path = edit_docking.edit_docking_topology_path(state_dir=tmp_path)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "lock_state": "UNLOCKED",
                "panel_order": ["library", "browser", "library", "harmony"],
            }
        ),
        encoding="utf-8",
    )
    loaded = edit_docking.load_edit_docking_state(state_dir=tmp_path)
    assert loaded.panel_order == CANONICAL_ORDER
    assert loaded.lock_state == "LOCKED"
    assert loaded.schema_version == edit_docking.EDIT_DOCKING_SCHEMA_VERSION


def test_corrupt_ratios_adjacent_payload_does_not_poison_topology(tmp_path: Path):
    path = edit_docking.edit_docking_topology_path(state_dir=tmp_path)
    path.write_text("{not-json", encoding="utf-8")
    loaded = edit_docking.load_edit_docking_state(state_dir=tmp_path)
    assert loaded == edit_docking.DEFAULT_EDIT_DOCKING_STATE


# ---------------------------------------------------------------------------
# 7) Hidden Live Kit → no phantom space
# ---------------------------------------------------------------------------


def test_hidden_live_kit_consumes_no_phantom_slot():
    state = _state(panel_order=CANONICAL_ORDER)
    slots = edit_docking.active_slot_assignments(
        state,
        materialization=_mat(live_kit=False),
    )
    assert "live_kit" not in slots.values()
    assert len(slots) == 3
    assert list(slots.values()) == ["library", "browser", "harmony"]


# ---------------------------------------------------------------------------
# 8) Legacy Rack reference → migrate without empty cavity
# ---------------------------------------------------------------------------


def test_legacy_rack_reference_migrates_without_empty_cavity(tmp_path: Path):
    path = edit_docking.edit_docking_topology_path(state_dir=tmp_path)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "lock_state": "UNLOCKED",
                "panel_order": [
                    "library",
                    "browser",
                    "channel_rack",
                    "livekit",
                    "harmony",
                ],
            }
        ),
        encoding="utf-8",
    )
    loaded = edit_docking.load_edit_docking_state(state_dir=tmp_path)
    assert "channel_rack" not in loaded.panel_order
    assert "rack" not in loaded.panel_order
    assert "livekit" not in loaded.panel_order
    assert "live_kit" in loaded.panel_order
    assert loaded.panel_order == ("library", "browser", "live_kit", "harmony")
    slots = edit_docking.active_slot_assignments(
        loaded,
        materialization=_mat(harmony=True, live_kit=True),
    )
    assert "channel_rack" not in slots.values()
    assert list(slots.values()).count("live_kit") == 1


# ---------------------------------------------------------------------------
# 9) Arrangement / Live target IDs rejected
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_id", ["arrangement", "live", "step_sequencer"])
def test_arrangement_and_live_targets_rejected(bad_id: str):
    state = _state(lock_state="UNLOCKED")
    move = edit_docking.apply_edit_docking_intent(
        state,
        edit_docking.PanelMoveIntent(panel_id=bad_id, target_slot_id="edit_slot_0"),
        features=_features(docking=True),
        materialization=_mat(),
    )
    swap = edit_docking.apply_edit_docking_intent(
        state,
        edit_docking.PanelSwapIntent(panel_a="library", panel_b=bad_id),
        features=_features(docking=True),
        materialization=_mat(),
    )
    assert move.accepted is False
    assert swap.accepted is False
    assert move.state == state
    assert swap.state == state


# ---------------------------------------------------------------------------
# 10) Resize / collapse independent of docking lock
# ---------------------------------------------------------------------------


def test_resize_and_collapse_remain_independent_of_docking_lock(tmp_path: Path):
    state = _state(lock_state="LOCKED")
    ratios = normalize_ratios(CANONICAL_DEFAULT_RATIOS)
    save_layout_preferences(ratios, state_dir=tmp_path)
    resized = apply_divider_drag(
        ratios,
        divider_after="library",
        delta_px=24.0,
        available_width=1400.0,
        harmony_open=True,
        has_active_source=True,
    )
    assert resized != ratios
    # Docking lock must not block elastic resize.
    assert math.isfinite(sum(resized.values()))

    collapse = edit_docking.apply_edit_docking_intent(
        state,
        edit_docking.CollapseIntent(panel_id="harmony"),
        features=_features(docking=True),
        materialization=_mat(),
    )
    # Collapse is not a docking mutation; accepted as non-topology no-op passthrough.
    assert collapse.accepted is True
    assert collapse.state.panel_order == state.panel_order
    assert collapse.state.lock_state == "LOCKED"
    assert collapse.intent_kind == "collapse"


# ---------------------------------------------------------------------------
# 11) Restart restores topology + lock
# ---------------------------------------------------------------------------


def test_restart_restores_committed_topology_and_lock(tmp_path: Path):
    state = _state(
        lock_state="UNLOCKED",
        panel_order=("browser", "library", "live_kit", "harmony"),
    )
    assert edit_docking.save_edit_docking_state(state, state_dir=tmp_path) is True
    loaded = edit_docking.load_edit_docking_state(state_dir=tmp_path)
    assert loaded == state
    assert loaded.lock_state == "UNLOCKED"
    assert loaded.panel_order == ("browser", "library", "live_kit", "harmony")


# ---------------------------------------------------------------------------
# 12) Repeated identical moves → no ratio drift
# ---------------------------------------------------------------------------


def test_repeated_identical_moves_do_not_drift_ratios(tmp_path: Path):
    ratios = normalize_ratios(CANONICAL_DEFAULT_RATIOS)
    save_layout_preferences(ratios, state_dir=tmp_path)
    state = _state(lock_state="UNLOCKED", panel_order=CANONICAL_ORDER)
    intent = edit_docking.PanelMoveIntent(
        panel_id="harmony",
        target_slot_id="edit_slot_0",
    )
    current = state
    for _ in range(5):
        result = edit_docking.apply_edit_docking_intent(
            current,
            intent,
            features=_features(docking=True),
            materialization=_mat(),
        )
        assert result.accepted is True
        current = result.state
    loaded_ratios = load_layout_preferences(state_dir=tmp_path).ratios
    assert dict(loaded_ratios) == dict(ratios)
    assert current.panel_order == ("harmony", "library", "browser", "live_kit")


# ---------------------------------------------------------------------------
# 13) Pure topology change does not mutate musical session snapshot
# ---------------------------------------------------------------------------


def test_topology_mutation_does_not_change_musical_session_snapshot(tmp_path: Path):
    musical = {
        "kit": {"slots": [{"id": "kick", "path": "synth://kick"}]},
        "pattern": {"steps": [1, 0, 1, 0]},
        "session_clock": {"master_bpm": 128.0},
    }
    snapshot = copy.deepcopy(musical)
    state = _state(lock_state="UNLOCKED")
    result = edit_docking.apply_edit_docking_intent(
        state,
        edit_docking.PanelSwapIntent(panel_a="library", panel_b="browser"),
        features=_features(docking=True),
        materialization=_mat(),
        musical_session=musical,
    )
    assert result.accepted is True
    assert musical == snapshot
    # Persistence of topology must not write musical keys.
    edit_docking.save_edit_docking_state(result.state, state_dir=tmp_path)
    raw = json.loads(
        edit_docking.edit_docking_topology_path(state_dir=tmp_path).read_text(
            encoding="utf-8"
        )
    )
    assert "kit" not in raw
    assert "pattern" not in raw
    assert "session_clock" not in raw
    assert set(raw) <= {
        "schema_version",
        "lock_state",
        "panel_order",
    }


# ---------------------------------------------------------------------------
# Lock helpers + feature persistence
# ---------------------------------------------------------------------------


def test_set_lock_state_persists_and_defaults_locked(tmp_path: Path):
    state = edit_docking.DEFAULT_EDIT_DOCKING_STATE
    assert state.lock_state == "LOCKED"
    unlocked = edit_docking.set_edit_docking_lock(state, "UNLOCKED")
    assert unlocked.lock_state == "UNLOCKED"
    assert unlocked.panel_order == state.panel_order
    edit_docking.save_edit_docking_state(unlocked, state_dir=tmp_path)
    assert edit_docking.load_edit_docking_state(state_dir=tmp_path).lock_state == "UNLOCKED"


def test_feature_flag_round_trip_does_not_reset_gesture_flag(tmp_path: Path):
    enabled = replace_workbench_feature_settings(
        WorkbenchFeatureSettings(gesture_rack_apply_enabled=True),
        workspace_panel_docking_enabled=True,
    )
    assert save_workbench_feature_settings(enabled, state_dir=tmp_path) is True
    loaded = load_workbench_feature_settings(state_dir=tmp_path)
    assert loaded.workspace_panel_docking_enabled is True
    assert loaded.gesture_rack_apply_enabled is True


def test_legacy_feature_json_without_docking_key_keeps_gesture_flag(tmp_path: Path):
    path = tmp_path / "workbench_feature_settings.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "gesture_rack_apply_enabled": True,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    loaded = load_workbench_feature_settings(state_dir=tmp_path)
    assert loaded.gesture_rack_apply_enabled is True
    assert loaded.workspace_panel_docking_enabled is False


def test_moving_dematerialized_panel_is_rejected():
    state = _state(lock_state="UNLOCKED")
    result = edit_docking.apply_edit_docking_intent(
        state,
        edit_docking.PanelMoveIntent(panel_id="live_kit", target_slot_id="edit_slot_0"),
        features=_features(docking=True),
        materialization=_mat(live_kit=False),
    )
    assert result.accepted is False
    assert result.state == state
