"""Frozen RED→GREEN contracts for [#1077] Live Kit Edit workspace tool.

Live Kit is an Edit/Kit tool: visible-only projection, no Rack/step co-host,
Python-owned mutations (including clear_slot), #1070 materialization binding,
and #1072 visible targets without #1073 drag visuals.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.workbench_controller import WorkbenchRow
from src.workbench_edit_docking import (
    EDIT_PANEL_LIVE_KIT,
    EditDockingMaterialization,
    EditDockingState,
    LOCK_LOCKED,
    LOCK_UNLOCKED,
    PanelMoveIntent,
    active_panel_order,
    apply_edit_docking_intent,
)
from src.workbench_feature_settings import WorkbenchFeatureSettings
from src.workbench_internal_sample_dnd import list_visible_live_kit_targets
from src.workbench_live_kit import LIVE_KIT_SLOT_MAPPING, LiveKitState
from src.workbench_live_kit_edit import (
    LIVE_KIT_VISIBILITY_PREF_KEY,
    edit_docking_materialization_for_live_kit,
    load_live_kit_visibility_preference,
    save_live_kit_visibility_preference,
    visible_live_kit_slot_keys,
)
from src.workbench_qml import QML_SOURCE, LiveKitPresenter
from src.workbench_qml_spike import (
    Screen1QmlInteractionAdapter,
    build_qml_view_model_from_fixture,
)
from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1


def _row(name: str = "kick_01.wav") -> WorkbenchRow:
    return WorkbenchRow(
        display_name=name,
        relative_path=f"synthetic/{name}",
        path=f"synthetic/{name}",
        bpm=132.0,
        key="Am",
        key_conf=0.91,
        loudness=-13.5,
        brightness=3200.0,
        sample_class="one_shot",
        pred_type="Kick",
        status="ok",
        details={"duration_sec": "0.25", "source": "synthetic"},
    )


def _adapter(state: LiveKitState | None = None) -> Screen1QmlInteractionAdapter:
    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(fixture, "screen1-default-3panel")
    live_kit = LiveKitPresenter(state=state)
    adapter = Screen1QmlInteractionAdapter(view_model=view_model, live_kit=live_kit)
    view_model.live_kit_groups = live_kit.groups
    view_model.live_kit_materialized = True
    return adapter


# --- Domain: clear_slot parity -------------------------------------------------


def test_clear_slot_mutates_exactly_one_slot_and_notifies():
    events: list[str] = []
    kit = LiveKitState(on_assignment_changed=lambda: events.append("changed"))
    kit.assign("Kick + Bass", "Kick", _row("a.wav"))
    kit.assign("Drums", "Closed Hat", _row("b.wav"))
    events.clear()

    cleared = kit.clear_slot("Kick + Bass", "Kick")

    assert cleared is True
    assert kit.assignment_for("Kick + Bass", "Kick") is None
    assert kit.assignment_for("Drums", "Closed Hat") is not None
    assert events == ["changed"]


def test_clear_slot_empty_is_idempotent_without_notify():
    events: list[str] = []
    kit = LiveKitState(on_assignment_changed=lambda: events.append("changed"))
    assert kit.clear_slot("Kick + Bass", "Kick") is False
    assert events == []


def test_clear_slot_invalid_target_raises_like_assign():
    kit = LiveKitState()
    with pytest.raises(ValueError):
        kit.clear_slot("No Group", "Kick")
    with pytest.raises(ValueError):
        kit.clear_slot("Kick + Bass", "No Slot")


def test_clear_slot_notify_false_skips_callback():
    events: list[str] = []
    kit = LiveKitState(on_assignment_changed=lambda: events.append("changed"))
    kit.assign("Kick + Bass", "Kick", _row())
    events.clear()
    assert kit.clear_slot("Kick + Bass", "Kick", notify=False) is True
    assert kit.assignment_for("Kick + Bass", "Kick") is None
    assert events == []


# --- Visibility / geometry / projection ---------------------------------------


def test_hidden_live_kit_has_no_visible_slot_keys_or_targets():
    keys = visible_live_kit_slot_keys(live_kit_visible=False)
    assert keys == ()
    targets = list_visible_live_kit_targets(
        features=WorkbenchFeatureSettings(internal_sample_dnd_enabled=True),
        live_kit_materialized=False,
        visible_slot_keys=keys,
    )
    assert targets == ()


def test_visible_live_kit_exposes_canonical_1072_targets():
    keys = visible_live_kit_slot_keys(live_kit_visible=True)
    expected = tuple(
        (group, slot) for group, slots in LIVE_KIT_SLOT_MAPPING for slot in slots
    )
    assert keys == expected
    targets = list_visible_live_kit_targets(
        features=WorkbenchFeatureSettings(internal_sample_dnd_enabled=True),
        live_kit_materialized=True,
        visible_slot_keys=keys,
    )
    assert len(targets) == len(expected)
    assert all(t.kind == "live_kit_assignment" and t.visible for t in targets)


def test_hidden_live_kit_not_in_edit_docking_materialization():
    mat = edit_docking_materialization_for_live_kit(
        live_kit_visible=False,
        library=True,
        browser=True,
        harmony=False,
    )
    assert mat.live_kit is False
    order = active_panel_order(EditDockingState(), materialization=mat)
    assert EDIT_PANEL_LIVE_KIT not in order


def test_visible_live_kit_in_edit_docking_materialization():
    mat = edit_docking_materialization_for_live_kit(
        live_kit_visible=True,
        library=True,
        browser=True,
        harmony=False,
    )
    assert mat.live_kit is True
    order = active_panel_order(EditDockingState(), materialization=mat)
    assert EDIT_PANEL_LIVE_KIT in order


def test_hide_preserves_musical_assignments():
    adapter = _adapter()
    kit = adapter._live_kit.state
    kit.assign("Kick + Bass", "Kick", _row("keep.wav"))
    adapter._live_kit_drawer_open = True
    adapter.live_kit_collapsed = False
    adapter.view_model.live_kit_materialized = True

    assert adapter.live_kit_is_visible() is True
    adapter.toggle_live_kit_drawer()
    assert adapter.live_kit_is_visible() is False
    assert kit.assignment_for("Kick + Bass", "Kick") is not None
    assert adapter.visible_live_kit_slot_keys() == ()


def test_repeated_reveal_hide_no_assignment_drift():
    adapter = _adapter()
    kit = adapter._live_kit.state
    kit.assign("Drums", "Main Drum", _row("md.wav"))
    adapter.view_model.live_kit_materialized = True
    fingerprint = (
        kit.assignment_for("Drums", "Main Drum").relative_path,
        kit.assignment_for("Kick + Bass", "Kick"),
    )
    for _ in range(5):
        adapter._live_kit_drawer_open = False
        adapter.live_kit_collapsed = True
        assert adapter.live_kit_is_visible() is False
        adapter._live_kit_drawer_open = True
        adapter.live_kit_collapsed = False
        assert adapter.live_kit_is_visible() is True
    assert (
        kit.assignment_for("Drums", "Main Drum").relative_path,
        kit.assignment_for("Kick + Bass", "Kick"),
    ) == fingerprint


def test_remove_live_kit_slot_routes_one_clear_slot_mutation():
    events: list[str] = []
    kit = LiveKitState(on_assignment_changed=lambda: events.append("n"))
    adapter = _adapter(state=kit)
    kit.assign("Melodic", "Lead", _row("lead.wav"))
    events.clear()
    assert adapter.remove_live_kit_slot("Melodic", "Lead") is True
    assert kit.assignment_for("Melodic", "Lead") is None
    assert events == ["n"]


def test_add_replace_still_single_assign_mutation():
    events: list[str] = []
    kit = LiveKitState(on_assignment_changed=lambda: events.append("n"))
    adapter = _adapter(state=kit)
    adapter._pending_live_kit_row = _row("first.wav")
    assert adapter.assign_live_kit_slot("Kick + Bass", "Kick") is True
    assert events == ["n"]
    events.clear()
    adapter._pending_live_kit_row = _row("second.wav")
    assert adapter.assign_live_kit_slot("Kick + Bass", "Kick") is True
    assert kit.assignment_for("Kick + Bass", "Kick").display_name == "second.wav"
    assert events == ["n"]


def test_export_is_distinct_from_arrangement_entry_in_qml():
    assert "Export Kit" in QML_SOURCE
    assert "liveKitExportButton" in QML_SOURCE
    # No fake Arrangement Entry CTA in Live Kit module.
    assert "Arrangement Entry" not in QML_SOURCE
    assert "Enter Arrangement" not in QML_SOURCE


def test_live_kit_module_has_no_step_grid_projection():
    # Live Kit Edit pane must not host Rack/step-grid product UI.
    assert "bottomRackStepList" not in QML_SOURCE
    assert "bottomRackPlayButton" not in QML_SOURCE
    assert 'text: "RACK"' not in QML_SOURCE
    assert "Live Kit / Rack" not in QML_SOURCE
    assert 'objectName: "liveKitGroupsColumn"' in QML_SOURCE
    assert "objectName: \"liveKitPane\"" in QML_SOURCE


def test_qml_has_no_second_musical_kit_truth():
    # Projection reads screenData / interaction; must not invent QML kit store.
    assert "property var qmlOwnedKit" not in QML_SOURCE
    assert "ListModel { id: liveKitOwnedModel" not in QML_SOURCE


def test_visibility_preference_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SAMPLE_BRAIN_STATE_DIR", str(tmp_path))
    assert load_live_kit_visibility_preference(state_dir=tmp_path) is False
    save_live_kit_visibility_preference(True, state_dir=tmp_path)
    assert load_live_kit_visibility_preference(state_dir=tmp_path) is True
    save_live_kit_visibility_preference(False, state_dir=tmp_path)
    assert load_live_kit_visibility_preference(state_dir=tmp_path) is False
    # Preference key is workspace UI, not a musical feature flag.
    assert LIVE_KIT_VISIBILITY_PREF_KEY == "live_kit_visible"


def test_locked_docking_allows_reveal_without_reorder():
    mat = EditDockingMaterialization(
        library=True, browser=True, harmony=False, live_kit=True
    )
    state = EditDockingState(lock_state=LOCK_LOCKED)
    features = WorkbenchFeatureSettings(workspace_panel_docking_enabled=True)
    before = active_panel_order(state, materialization=mat)
    result = apply_edit_docking_intent(
        state,
        PanelMoveIntent(panel_id=EDIT_PANEL_LIVE_KIT, target_slot_id="edit_slot_0"),
        features=features,
        materialization=mat,
    )
    assert result.accepted is False
    assert result.reason == "layout_locked"
    assert active_panel_order(result.state, materialization=mat) == before
    # Reveal/hide materialization remains independent of lock.
    assert edit_docking_materialization_for_live_kit(True).live_kit is True
    assert edit_docking_materialization_for_live_kit(False).live_kit is False


def test_unlocked_docking_live_kit_only_valid_edit_slots():
    mat = EditDockingMaterialization(
        library=True, browser=True, harmony=False, live_kit=True
    )
    state = EditDockingState(lock_state=LOCK_UNLOCKED)
    features = WorkbenchFeatureSettings(workspace_panel_docking_enabled=True)
    rejected = apply_edit_docking_intent(
        state,
        PanelMoveIntent(
            panel_id=EDIT_PANEL_LIVE_KIT,
            target_slot_id="arrangement_slot_0",
        ),
        features=features,
        materialization=mat,
    )
    assert rejected.accepted is False
    assert rejected.reason == "invalid_slot"
    assert active_panel_order(rejected.state, materialization=mat) == active_panel_order(
        state, materialization=mat
    )


def test_clean_edit_startup_pref_default_hidden(tmp_path: Path):
    assert load_live_kit_visibility_preference(state_dir=tmp_path) is False
