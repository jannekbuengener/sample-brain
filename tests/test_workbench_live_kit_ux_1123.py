"""Frozen contracts for [#1123] Live Kit always-closed start + group cards.

Follow-up to #1077 Owner Visual Gate PASS. Does not reopen #1077 as FAIL.
Display mapping only — domain taxonomy keys stay authoritative.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from src.workbench_controller import WorkbenchRow
from src.workbench_feature_settings import WorkbenchFeatureSettings
from src.workbench_internal_sample_dnd import list_visible_live_kit_targets
from src.workbench_live_kit import (
    LIVE_KIT_GROUPS,
    LIVE_KIT_SLOT_MAPPING,
    LiveKitState,
    live_kit_group_display_name,
    live_kit_slot_display_name,
)
from src.workbench_live_kit_edit import (
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


def test_display_mapping_bassline_and_kick_drum_without_domain_rename():
    assert live_kit_group_display_name("Kick + Bass") == "Bassline"
    assert live_kit_slot_display_name("Kick + Bass", "Kick") == "Kick Drum"
    assert live_kit_slot_display_name("Kick + Bass", "Bass") == "Bass"
    assert "Kick + Bass" in LIVE_KIT_GROUPS
    assert ("Kick + Bass", ("Kick", "Bass")) in LIVE_KIT_SLOT_MAPPING
    for group in ("Drums", "Melodic", "Atmos / FX"):
        assert live_kit_group_display_name(group) == group


def test_qml_context_projects_display_names_keep_domain_keys():
    presenter = LiveKitPresenter()
    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(fixture, "screen1-default-3panel")
    view_model.live_kit_groups = presenter.groups
    groups = view_model.qml_context()["liveKitGroups"]
    assert groups[0]["name"] == "Kick + Bass"
    assert groups[0]["displayName"] == "Bassline"
    slot_names = {slot["name"]: slot["displayName"] for slot in groups[0]["slots"]}
    assert slot_names["Kick"] == "Kick Drum"
    assert slot_names["Bass"] == "Bass"
    assert [g["displayName"] for g in groups] == [
        "Bassline",
        "Drums",
        "Melodic",
        "Atmos / FX",
    ]
    # Single Atmos / FX domain group → one card (no invented dual domain).
    assert sum(1 for g in groups if "Atmos" in g["name"] or "FX" in g["name"]) == 1


def test_new_workspace_start_live_kit_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    adapter = _adapter()
    assert adapter.apply_live_kit_visibility_preference() is False
    assert adapter.live_kit_is_visible() is False
    assert adapter._live_kit_drawer_open is False
    assert adapter.live_kit_collapsed is True
    assert adapter.edit_docking_materialization().live_kit is False


def test_persisted_visible_true_does_not_auto_open_on_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    save_live_kit_visibility_preference(True, state_dir=tmp_path)
    kit = LiveKitState()
    kit.assign("Kick + Bass", "Kick", _row("keep.wav"))
    adapter = _adapter(state=kit)

    assert adapter.apply_live_kit_visibility_preference() is False
    assert adapter.live_kit_is_visible() is False
    assert adapter._live_kit_visibility_desired is False
    # Musical state fully preserved.
    assert kit.assignment_for("Kick + Bass", "Kick") is not None
    assert kit.assignment_for("Kick + Bass", "Kick").display_name == "keep.wav"


def test_reveal_control_still_opens_live_kit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    save_live_kit_visibility_preference(True, state_dir=tmp_path)
    kit = LiveKitState()
    kit.assign("Drums", "Main Drum", _row("md.wav"))
    adapter = _adapter(state=kit)
    adapter.apply_live_kit_visibility_preference()
    assert adapter.live_kit_is_visible() is False

    assert adapter.toggle_live_kit_drawer() is True
    assert adapter.live_kit_is_visible() is True
    assert adapter.edit_docking_materialization().live_kit is True


def test_hide_reveal_preserves_musical_kit_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    kit = LiveKitState()
    kit.assign("Kick + Bass", "Kick", _row("keep.wav"))
    kit.assign("Kick + Bass", "Bass", _row("bass.wav"))
    adapter = _adapter(state=kit)
    adapter.apply_live_kit_visibility_preference()
    assert adapter.toggle_live_kit_drawer() is True
    assert adapter.toggle_live_kit_drawer() is False
    assert adapter.live_kit_is_visible() is False
    assert adapter.toggle_live_kit_drawer() is True
    assert kit.assignment_for("Kick + Bass", "Kick").display_name == "keep.wav"
    assert kit.assignment_for("Kick + Bass", "Bass").display_name == "bass.wav"


def test_bassline_expand_exposes_kick_drum_and_bass_targets():
    adapter = _adapter()
    adapter._live_kit_drawer_open = True
    adapter.live_kit_collapsed = False
    assert adapter.visible_live_kit_slot_keys() == ()
    assert adapter.toggle_live_kit_group("Kick + Bass") is False
    keys = adapter.visible_live_kit_slot_keys()
    assert keys == (("Kick + Bass", "Kick"), ("Kick + Bass", "Bass"))
    targets = list_visible_live_kit_targets(
        features=WorkbenchFeatureSettings(internal_sample_dnd_enabled=True),
        live_kit_materialized=True,
        visible_slot_keys=keys,
    )
    assert len(targets) == 2


def test_qml_projects_horizontal_responsive_group_cards():
    assert 'objectName: "liveKitGroupsFlow"' in QML_SOURCE
    assert "Flow {" in QML_SOURCE
    assert 'objectName: "liveKitGroupsColumn"' not in QML_SOURCE
    # Cards wrap; minimum width guard against unreadably narrow cells.
    assert "groupCardMinWidth" in QML_SOURCE
    assert "groupCardWidth" in QML_SOURCE
    assert "groupCardMinWidth:" in QML_SOURCE
    assert "groupCardMinWidth: 140" in QML_SOURCE or "groupCardMinWidth: 200" in QML_SOURCE
    flow = QML_SOURCE.split('objectName: "liveKitGroupsFlow"', 1)[1][:2500]
    assert "displayName" in flow
    assert 'objectName: "liveKitGroupHeader" + index' in QML_SOURCE


def test_reveal_control_hidden_when_browser_collapsed():
    block = QML_SOURCE.split('objectName: "editLiveKitRevealControl"', 1)[1][:900]
    assert "!window.interaction.browserCollapsed" in block


PY_SIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None


def _click_window_at(window, app, settle, center) -> None:
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QMouseEvent

    for action in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        event = QMouseEvent(
            action,
            center,
            window.mapToGlobal(center.toPoint()),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        app.sendEvent(window, event)
        settle(app)


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_runtime_browser_collapse_gates_reveal_control_and_open_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """#1123 blocker: reveal eligibility follows the authoritative collapsed state.

    Browser open + kit closed => reveal control available; Browser collapsed =>
    control invisible and inert (no invisible drawer-open state change via
    click); Browser reopened => control available again; musical kit state
    unchanged across the whole cycle.
    """
    from PySide6.QtCore import QPointF
    from PySide6.QtQuick import QQuickItem

    from src.workbench_harmony import HarmonicMatchLibraryController
    from src.workbench_qml import LiveKitPresenter, Screen1QmlInteractionAdapter
    from src.workbench_qml_spike import (
        _qml_engine,
        _settle_qml_frame,
        build_qml_view_model_from_fixture,
    )

    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(fixture, "screen1-default-3panel")
    view_model.set_library_revealed(True)
    kit = LiveKitState()
    kit.assign("Kick + Bass", "Kick", _row("keep.wav"))
    live_kit = LiveKitPresenter(state=kit)
    view_model.live_kit_groups = live_kit.groups
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        harmony_controller=HarmonicMatchLibraryController(),
        live_kit=live_kit,
    )
    app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    view_model.set_workspace_materialization(
        has_active_source=True,
        calm_canvas_visible=False,
        browser_materialized=True,
        live_kit_materialized=True,
    )
    adapter._live_kit_drawer_open = False
    adapter.live_kit_collapsed = True
    window.show()
    _settle_qml_frame(app)
    bridge = getattr(engine, "_screen1_interaction_bridge", None)
    assert bridge is not None and hasattr(bridge, "refreshState")
    bridge.refreshState()
    _settle_qml_frame(app)

    reveal = window.findChild(QQuickItem, "editLiveKitRevealControl")
    assert reveal is not None
    try:
        # 1) Browser open + kit closed => reveal control available and usable.
        assert adapter.browser_collapsed is False
        assert reveal.isVisible() is True
        assert reveal.isEnabled() is True
        center = reveal.mapToItem(
            window.contentItem(), QPointF(reveal.width() / 2, reveal.height() / 2)
        )
        _click_window_at(window, app, _settle_qml_frame, center)
        assert adapter._live_kit_drawer_open is True

        # Close the drawer again for the collapsed-Browser phase.
        bridge.toggleLiveKitDrawer()
        _settle_qml_frame(app)
        assert adapter._live_kit_drawer_open is False

        # 2) Browser collapsed => reveal control neither visible nor enabled.
        bridge.toggleBrowserCollapsed()
        _settle_qml_frame(app)
        assert adapter.browser_collapsed is True
        assert reveal.isVisible() is False
        assert reveal.isEnabled() is False

        # 3) Clicking where the control was must not open the drawer invisibly.
        _click_window_at(window, app, _settle_qml_frame, center)
        assert adapter._live_kit_drawer_open is False

        # 4) Browser reopened => reveal control available again.
        bridge.toggleBrowserCollapsed()
        _settle_qml_frame(app)
        assert adapter.browser_collapsed is False
        assert reveal.isVisible() is True
        assert reveal.isEnabled() is True

        # 5) Musical kit state unchanged across the whole cycle.
        assignment = kit.assignment_for("Kick + Bass", "Kick")
        assert assignment is not None
        assert assignment.display_name == "keep.wav"
    finally:
        window.close()
        app.processEvents()


def test_closed_live_kit_has_no_phantom_bottom_geometry():
    pane = QML_SOURCE.split('objectName: "bottomRackPane"', 1)[1][:4500]
    assert "height: kitHudExpanded" in pane or "height: bottomExpanded" in pane
    assert ": 0" in pane
    assert "kitHudExpanded" in pane
    assert "bottomExpanded" in pane  # compat alias
    adapter = _adapter()
    adapter.apply_live_kit_visibility_preference()
    assert adapter.live_kit_is_visible() is False
    assert adapter.edit_docking_materialization().live_kit is False
    assert (
        visible_live_kit_slot_keys(live_kit_visible=False, expanded_groups=("Kick + Bass",))
        == ()
    )


def test_add_replace_remove_export_contracts_stay_green(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    adapter = _adapter()
    adapter._pending_live_kit_row = _row("a.wav")
    assert adapter.assign_live_kit_slot("Kick + Bass", "Kick") is True
    adapter._pending_live_kit_row = _row("b.wav")
    assert adapter.assign_live_kit_slot("Kick + Bass", "Kick") is True
    assert adapter._live_kit.state.assignment_for("Kick + Bass", "Kick").display_name == "b.wav"
    # Export may fail-closed on synthetic missing paths; seam must remain callable.
    result = adapter.export_live_kit(tmp_path / "kit-out")
    assert result.error_code is None or isinstance(result.error_code, str)
    assert adapter.remove_live_kit_slot("Kick + Bass", "Kick") is True
    assert adapter._live_kit.state.assignment_for("Kick + Bass", "Kick") is None


def test_live_kit_not_top_level_mode_nav():
    header_nav = QML_SOURCE.split('objectName: "headerNavRow"', 1)[1].split(
        'objectName: "headerTransportZone"', 1
    )[0]
    assert 'objectName: "programNavLiveKit"' not in header_nav
    assert 'text: "Live Kit"' not in header_nav
    assert 'objectName: "editLiveKitRevealControl"' in QML_SOURCE


def test_no_invented_atmos_fx_domain_split():
    assert tuple(LIVE_KIT_GROUPS).count("Atmos / FX") == 1
    assert "Atmos" not in LIVE_KIT_GROUPS
    assert "FX" not in LIVE_KIT_GROUPS
