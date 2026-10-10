"""Frozen RED→GREEN contracts for [#1077] Live Kit Edit workspace tool.

Live Kit is an Edit/Kit tool: visible-only projection, no Rack/step co-host,
Python-owned mutations (including clear_slot), #1070 materialization binding,
and #1072 visible targets without #1073 drag visuals.

Product-UI expectations that supersede historical #908 bottom-Rack QML
projection live here (not in the Channel Rack domain freeze suite).
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
from src.workbench_library_navigation import (
    LibraryAvailability,
    LibraryNode,
    LibraryNodeKind,
    LibraryScope,
    LibraryScopeKind,
)

_SAMPLE_SOURCES = "container:sample-sources"
from src.workbench_live_kit import LIVE_KIT_SLOT_MAPPING, LiveKitState
from src.workbench_live_kit_edit import (
    LIVE_KIT_VISIBILITY_PREF_KEY,
    edit_docking_materialization_for_live_kit,
    load_live_kit_visibility_preference,
    save_live_kit_visibility_preference,
    try_save_live_kit_visibility_preference,
    visible_live_kit_slot_keys,
)
from src.workbench_qml import QML_SOURCE, LiveKitPresenter
from src.workbench_qml_library import LibrarySelectionIntent, WorkbenchLibraryTreeState
from src.workbench_qml_runtime import Screen1QmlRuntimeComposition
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


class _FakeNav:
    def __init__(self) -> None:
        self.root = LibraryNode(
            "root:1",
            LibraryNodeKind.REGISTERED_ROOT,
            "Samples",
            _SAMPLE_SOURCES,
            True,
            True,
            LibraryAvailability.AVAILABLE,
            folder_id=1,
        )
        self._top = (
            LibraryNode(
                _SAMPLE_SOURCES,
                LibraryNodeKind.SAMPLE_SOURCES,
                "Sample Sources",
                None,
                False,
                True,
                LibraryAvailability.AVAILABLE,
            ),
            self.root,
        )

    @property
    def library_db_path(self):
        return None

    def top_level_nodes(self):
        return self._top

    def children(self, node_id: str):
        if node_id == _SAMPLE_SOURCES:
            return (self.root,)
        return ()

    def resolve_scope(self, node_id: str):
        if node_id == "root:1":
            return LibraryScope(
                LibraryScopeKind.ROOT,
                folder_id=1,
                folder_path="C:/samples",
            )
        return None


def _production_composed_adapter(
    monkeypatch: pytest.MonkeyPatch,
    *,
    state: LiveKitState | None = None,
    active_source: bool = True,
) -> tuple[Screen1QmlInteractionAdapter, Screen1QmlRuntimeComposition, LiveKitState]:
    """Harness that mirrors production: runtime composition + interaction adapter."""
    from src import workbench_qml_runtime as runtime_mod

    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(fixture, "screen1-default-3panel")
    kit_state = state if state is not None else LiveKitState()
    live_kit = LiveKitPresenter(state=kit_state)
    composition = Screen1QmlRuntimeComposition(
        tree_state=WorkbenchLibraryTreeState(_FakeNav())
    )
    monkeypatch.setattr(
        runtime_mod,
        "load_cached_folder_rows",
        lambda _folder: [_row("a.wav"), _row("b.wav")],
    )
    if active_source:
        nav = composition.library_tree.navigation
        scope = nav.resolve_scope("root:1")
        composition.dispatch_selection(
            LibrarySelectionIntent(node=nav.root, scope=scope)
        )
    adapter = Screen1QmlInteractionAdapter(view_model=view_model, live_kit=live_kit)
    adapter._runtime_composition = composition
    view_model.live_kit_groups = live_kit.groups
    view_model.set_workspace_materialization(
        has_active_source=composition.has_active_source,
        calm_canvas_visible=not composition.has_active_source,
        browser_materialized=composition.browser_materialized,
        live_kit_materialized=composition.live_kit_materialized,
    )
    return adapter, composition, kit_state


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


def test_pending_add_counts_as_visible_for_docking_and_targets():
    adapter = _adapter()
    kit = adapter._live_kit.state
    keep = _row("keep.wav")
    kit.assign("Kick + Bass", "Kick", keep)
    adapter._live_kit_drawer_open = False
    adapter.live_kit_collapsed = True
    adapter.view_model.live_kit_materialized = True
    assert adapter.live_kit_is_visible() is False
    assert adapter.visible_live_kit_slot_keys() == ()
    assert adapter.edit_docking_materialization().live_kit is False

    pending = _row("pending.wav")
    adapter._request_add_to_kit_row(pending)
    assert adapter.pending_live_kit_add == pending.display_name
    assert adapter._live_kit_drawer_open is False
    assert adapter.live_kit_is_visible() is True
    assert adapter.visible_live_kit_slot_keys()
    assert adapter.edit_docking_materialization().live_kit is True
    assert kit.assignment_for("Kick + Bass", "Kick") is keep

    assert adapter.cancel_live_kit_add() is True
    assert adapter.pending_live_kit_add == ""
    assert adapter._live_kit_drawer_open is False
    assert adapter.live_kit_is_visible() is False
    assert adapter.visible_live_kit_slot_keys() == ()
    assert adapter.edit_docking_materialization().live_kit is False
    assert kit.assignment_for("Kick + Bass", "Kick") is keep


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
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
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


# --- Preference restore rematerializes Live Kit (#1077 Codex P1) --------------


def test_persisted_visible_preference_rematerializes_live_kit_on_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    save_live_kit_visibility_preference(True, state_dir=tmp_path)

    kit = LiveKitState()
    kit.assign("Kick + Bass", "Kick", _row("keep.wav"))
    adapter, composition, kit_state = _production_composed_adapter(
        monkeypatch, state=kit, active_source=True
    )
    assert composition.has_active_source is True
    assert composition.live_kit_materialized is False
    assert adapter.view_model.live_kit_materialized is False
    assert adapter.live_kit_is_visible() is False

    restored = adapter.apply_live_kit_visibility_preference()

    assert restored is True
    assert composition.live_kit_revealed is True
    assert composition.live_kit_materialized is True
    assert adapter.view_model.live_kit_materialized is True
    assert adapter.live_kit_is_visible() is True
    assert adapter.edit_docking_materialization().live_kit is True
    assert len(adapter.visible_live_kit_slot_keys()) == sum(
        len(slots) for _group, slots in LIVE_KIT_SLOT_MAPPING
    )
    targets = list_visible_live_kit_targets(
        features=WorkbenchFeatureSettings(internal_sample_dnd_enabled=True),
        live_kit_materialized=adapter.view_model.live_kit_materialized,
        visible_slot_keys=adapter.visible_live_kit_slot_keys(),
    )
    assert len(targets) == len(adapter.visible_live_kit_slot_keys())
    assert kit_state.assignment_for("Kick + Bass", "Kick") is not None
    assert kit_state.assignment_for("Kick + Bass", "Kick").display_name == "keep.wav"


def test_persisted_hidden_preference_stays_unmaterialized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    save_live_kit_visibility_preference(False, state_dir=tmp_path)
    kit = LiveKitState()
    kit.assign("Drums", "Main Drum", _row("md.wav"))
    adapter, composition, kit_state = _production_composed_adapter(
        monkeypatch, state=kit, active_source=True
    )

    restored = adapter.apply_live_kit_visibility_preference()

    assert restored is False
    assert composition.live_kit_revealed is False
    assert composition.live_kit_materialized is False
    assert adapter.view_model.live_kit_materialized is False
    assert adapter.live_kit_is_visible() is False
    assert adapter.edit_docking_materialization().live_kit is False
    assert adapter.visible_live_kit_slot_keys() == ()
    assert kit_state.assignment_for("Drums", "Main Drum") is not None


def test_visible_preference_without_active_source_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    save_live_kit_visibility_preference(True, state_dir=tmp_path)
    adapter, composition, _kit = _production_composed_adapter(
        monkeypatch, active_source=False
    )

    adapter.apply_live_kit_visibility_preference()

    assert composition.has_active_source is False
    assert composition.live_kit_materialized is False
    assert adapter.view_model.live_kit_materialized is False
    assert adapter.live_kit_is_visible() is False
    assert adapter.visible_live_kit_slot_keys() == ()


# --- Preference write fail-soft (#1077 Codex P2) ------------------------------


def test_try_save_visibility_preference_swallows_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    def _boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(
        "src.workbench_live_kit_edit.save_live_kit_visibility_preference",
        _boom,
    )
    assert try_save_live_kit_visibility_preference(True, state_dir=tmp_path) is False


def test_toggle_drawer_remains_functional_when_preference_write_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    adapter = _adapter()
    kit = adapter._live_kit.state
    kit.assign("Kick + Bass", "Kick", _row("stable.wav"))
    adapter.view_model.live_kit_materialized = True
    adapter._live_kit_drawer_open = False
    adapter.live_kit_collapsed = True
    refresh_calls: list[str] = []

    def _boom(*_args, **_kwargs):
        raise OSError("unwritable state dir")

    monkeypatch.setattr(
        "src.workbench_live_kit_edit.save_live_kit_visibility_preference",
        _boom,
    )

    # Simulate bridge slot: toggle then refresh even if persistence fails.
    opened = adapter.toggle_live_kit_drawer()
    refresh_calls.append("after-open")
    assert opened is True
    assert adapter.live_kit_is_visible() is True
    assert adapter._live_kit_drawer_open is True
    assert adapter.live_kit_collapsed is False

    closed = adapter.toggle_live_kit_drawer()
    refresh_calls.append("after-close")
    assert closed is False
    assert adapter.live_kit_is_visible() is False
    assert refresh_calls == ["after-open", "after-close"]
    assert kit.assignment_for("Kick + Bass", "Kick") is not None
    assert kit.assignment_for("Kick + Bass", "Kick").display_name == "stable.wav"


def test_assign_auto_disclosure_persists_fail_soft(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    adapter, composition, kit_state = _production_composed_adapter(
        monkeypatch, active_source=True
    )
    adapter._pending_live_kit_row = _row("first.wav")
    adapter._live_kit_auto_disclosure_consumed = False

    def _boom(*_args, **_kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(
        "src.workbench_live_kit_edit.save_live_kit_visibility_preference",
        _boom,
    )

    assert adapter.assign_live_kit_slot("Kick + Bass", "Kick") is True
    assert adapter.view_model.live_kit_materialized is True
    assert adapter.live_kit_is_visible() is True
    assert kit_state.assignment_for("Kick + Bass", "Kick") is not None
    assert composition.live_kit_revealed is True


# --- Product UI: no Rack/step co-host in Live Kit Edit (#1077) ---------------


def test_live_kit_edit_qml_has_no_bottom_rack_step_controls():
    """#1077 product-UI gate (moved out of Channel Rack freeze suite)."""
    assert "bottomRackStepList" not in QML_SOURCE
    assert "bottomRackPlayButton" not in QML_SOURCE
    assert "bottomRackStopButton" not in QML_SOURCE
    assert "Live Kit / Rack" not in QML_SOURCE
    assert 'text: "RACK"' not in QML_SOURCE


def test_preference_reapplied_after_analysis_disclosure_clear(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Staged visible preference must rematerialize after #742 analysis clears."""
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    save_live_kit_visibility_preference(True, state_dir=tmp_path)

    adapter, composition, kit_state = _production_composed_adapter(
        monkeypatch, active_source=False
    )
    kit_state.assign("Kick + Bass", "Kick", _row("keep.wav"))
    assert adapter.apply_live_kit_visibility_preference() is False
    assert composition.live_kit_revealed is True
    assert adapter.live_kit_is_visible() is False

    # Analysis working surface: disclosure cleared + presentation closed.
    composition.clear_live_kit_disclosure()
    adapter._live_kit_drawer_open = False
    adapter.live_kit_collapsed = True
    assert adapter.view_model.live_kit_materialized is False

    # Active Source returns (post-analysis sync).
    nav = composition.library_tree.navigation
    scope = nav.resolve_scope("root:1")
    composition.dispatch_selection(
        LibrarySelectionIntent(node=nav.root, scope=scope)
    )
    adapter.view_model.set_workspace_materialization(
        has_active_source=True,
        calm_canvas_visible=False,
        browser_materialized=True,
        live_kit_materialized=composition.live_kit_materialized,
    )
    assert composition.has_active_source is True
    assert adapter.live_kit_is_visible() is False

    restored = adapter.apply_live_kit_visibility_preference()
    assert restored is True
    assert composition.live_kit_materialized is True
    assert adapter.live_kit_is_visible() is True
    assert adapter.edit_docking_materialization().live_kit is True
    assert adapter.visible_live_kit_slot_keys()
    assert kit_state.assignment_for("Kick + Bass", "Kick") is not None


def test_qml_live_kit_pane_requires_materialization_gate():
    """QML must not show Live Kit from drawer flags alone after analysis clears."""
    pane = QML_SOURCE.split('objectName: "bottomRackPane"', 1)[1][:2500]
    assert "liveKitRevealed" in pane
    assert "hasActiveSource" in pane
    assert "bottomExpanded" in pane


def test_live_kit_user_height_clamped_and_does_not_mutate_kit():
    adapter = _adapter()
    kit = adapter._live_kit.state
    kit.assign("Drums", "Main Drum", _row("md.wav"))
    adapter.view_model.live_kit_materialized = True
    adapter._live_kit_drawer_open = True
    adapter.live_kit_collapsed = False

    assert adapter.live_kit_user_height_px == 0
    assert adapter.set_live_kit_user_height_px(220) == 220
    assert adapter.live_kit_user_height_px == 220
    assert adapter.set_live_kit_user_height_px(10_000) <= 10_000
    assert adapter.set_live_kit_user_height_px(0) == 0
    assert kit.assignment_for("Drums", "Main Drum") is not None
    assert adapter.live_kit_is_visible() is True


def test_live_kit_resize_handle_exists_in_qml():
    assert 'objectName: "liveKitResizeHandle"' in QML_SOURCE
    assert "setLiveKitUserHeightPx" in QML_SOURCE
    assert "SizeVerCursor" in QML_SOURCE


def test_resize_drag_underflow_clamps_to_minimum_not_auto():
    adapter = _adapter()
    adapter.view_model.live_kit_materialized = True
    adapter._live_kit_drawer_open = True
    # Drag path always supplies max_px > 0; underflow must not reset to auto.
    assert adapter.set_live_kit_user_height_px(-40, max_px=320) == 120
    assert adapter.live_kit_user_height_px == 120
    # Explicit auto reset remains available without max ceiling.
    assert adapter.set_live_kit_user_height_px(0) == 0


def test_toggle_open_rematerializes_after_disclosure_clear(
    monkeypatch: pytest.MonkeyPatch,
):
    adapter, composition, kit = _production_composed_adapter(
        monkeypatch, active_source=True
    )
    kit.assign("Kick + Bass", "Kick", _row("keep.wav"))
    composition.reveal_live_kit()
    adapter.view_model.live_kit_materialized = True
    adapter._live_kit_drawer_open = True
    adapter.live_kit_collapsed = False
    composition.clear_live_kit_disclosure()
    adapter.view_model.set_workspace_materialization(
        has_active_source=True,
        calm_canvas_visible=False,
        browser_materialized=True,
        live_kit_materialized=False,
    )
    adapter._live_kit_drawer_open = False
    adapter.live_kit_collapsed = True

    assert adapter.toggle_live_kit_drawer() is True
    assert composition.live_kit_revealed is True
    assert adapter.view_model.live_kit_materialized is True
    assert adapter.live_kit_is_visible() is True


def test_active_source_restore_reapplies_visible_preference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    save_live_kit_visibility_preference(True, state_dir=tmp_path)
    adapter, composition, _kit = _production_composed_adapter(
        monkeypatch, active_source=True
    )
    composition.clear_live_kit_disclosure()
    adapter._live_kit_drawer_open = False
    adapter.live_kit_collapsed = True
    adapter.view_model.set_workspace_materialization(
        has_active_source=True,
        calm_canvas_visible=False,
        browser_materialized=True,
        live_kit_materialized=False,
    )
    adapter.restore_live_kit_after_active_source()
    assert adapter.live_kit_is_visible() is True


def test_step_sequencer_nav_disabled_until_arrangement_destination():
    block = QML_SOURCE.split('objectName: "programNavStepSequencer"', 1)[1][:900]
    assert "enabled: false" in block
    assert "openChannelRack()" not in block


def test_auto_disclosure_updates_session_visibility_desired(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    save_live_kit_visibility_preference(False, state_dir=tmp_path)
    adapter, composition, _kit = _production_composed_adapter(
        monkeypatch, active_source=True
    )
    assert adapter.apply_live_kit_visibility_preference() is False
    assert adapter._live_kit_visibility_desired is False
    adapter._pending_live_kit_row = _row("first.wav")
    adapter._live_kit_auto_disclosure_consumed = False
    assert adapter.assign_live_kit_slot("Kick + Bass", "Kick") is True
    assert adapter._live_kit_visibility_desired is True
    composition.clear_live_kit_disclosure()
    adapter.suspend_live_kit_for_analysis()
    adapter.view_model.set_workspace_materialization(
        has_active_source=True,
        calm_canvas_visible=False,
        browser_materialized=True,
        live_kit_materialized=False,
    )
    assert adapter.restore_live_kit_after_active_source() is True
    assert adapter.live_kit_is_visible() is True


def test_session_close_survives_stale_preference_on_source_restore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    save_live_kit_visibility_preference(True, state_dir=tmp_path)
    adapter, composition, kit = _production_composed_adapter(
        monkeypatch, active_source=True
    )
    kit.assign("Kick + Bass", "Kick", _row("keep.wav"))
    assert adapter.apply_live_kit_visibility_preference() is True

    def _boom(*_a, **_k):
        raise OSError("unwritable")

    monkeypatch.setattr(
        "src.workbench_live_kit_edit.save_live_kit_visibility_preference",
        _boom,
    )
    assert adapter.toggle_live_kit_drawer() is False
    assert adapter.live_kit_is_visible() is False
    # Disk still says true; session desired must win on restore.
    assert load_live_kit_visibility_preference(state_dir=tmp_path) is True
    composition.clear_live_kit_disclosure()
    adapter.view_model.set_workspace_materialization(
        has_active_source=True,
        calm_canvas_visible=False,
        browser_materialized=True,
        live_kit_materialized=False,
    )
    assert adapter.restore_live_kit_after_active_source() is False
    assert adapter.live_kit_is_visible() is False
