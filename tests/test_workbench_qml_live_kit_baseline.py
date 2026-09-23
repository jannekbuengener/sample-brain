"""RED contracts for [#545] QML Live Kit group + slot baseline.

The production Screen-1 QML shell projects a runtime-owned Live Kit through a
thin adapter instead of the frozen synthetic projection, exposes honest
Empty/Assigned slot states, routes Add/Replace through the existing
``LiveKitState.assign`` seam, and keeps disclosure-only collapse/expand on
``LiveKitPresentationState``.  QML must remain a pure projection reader.
"""

from __future__ import annotations

import importlib.util

import pytest

from src.workbench_live_kit import LIVE_KIT_SLOT_MAPPING, LiveKitState
from src.workbench_controller import WorkbenchRow
from src.workbench_qml import LiveKitPresenter, QML_SOURCE
from src.workbench_qml_spike import (
    Screen1QmlInteractionAdapter,
    build_qml_view_model_from_fixture,
)
from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1


EXPECTED_GROUPS = tuple(group for group, _slots in LIVE_KIT_SLOT_MAPPING)
CANONICAL_GROUPS = ("Kick + Bass", "Drums", "Melodic", "Atmos / FX")


def _row(name: str = "closed_hat_01.wav") -> WorkbenchRow:
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
        pred_type="Closed Hat",
        status="ok",
        details={"duration_sec": "0.25", "source": "synthetic"},
    )


def _production_adapter(state: LiveKitState | None = None, **kwargs):
    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(
        fixture,
        "screen1-default-3panel",
    )
    live_kit = LiveKitPresenter(state=state)
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        live_kit=live_kit,
        **kwargs,
    )
    view_model.live_kit_groups = live_kit.groups
    return fixture, view_model, adapter, live_kit


def test_live_kit_projection_has_exactly_four_canonical_groups_in_order():
    live_kit = LiveKitPresenter()

    assert tuple(group.name for group in live_kit.groups) == CANONICAL_GROUPS
    assert tuple(group.name for group in live_kit.groups) == EXPECTED_GROUPS


def test_collapse_expand_changes_only_presentation_state_not_assignments():
    fixture, view_model, adapter, live_kit = _production_adapter()
    before = tuple(
        (group.name, tuple(slot.name for slot in group.slots))
        for group in live_kit.groups
    )

    assert live_kit.groups[1].active is True
    assert adapter.toggle_live_kit_group("Drums") is True
    assert live_kit.groups[1].active is False
    assert adapter.toggle_live_kit_group("Drums") is False
    assert live_kit.groups[1].active is True

    assert before == tuple(
        (group.name, tuple(slot.name for slot in group.slots))
        for group in live_kit.groups
    )
    assert all(slot.assignment is None for group in live_kit.groups for slot in group.slots)
    assert view_model.live_kit_groups is live_kit.groups
    assert fixture.browser_rows[0] is not None


def test_empty_slot_projects_an_honest_empty_state():
    _fixture, view_model, _adapter, _live_kit = _production_adapter()
    drums = view_model.qml_context()["liveKitGroups"][1]

    assert drums["name"] == "Drums"
    assert drums["slots"][0]["assigned"] is False
    assert drums["slots"][0]["assignment"] == "Empty · Slot wählen"
    assert all(not slot["assigned"] for slot in drums["slots"])


def test_assigned_slot_projects_existing_assignment_data():
    fixture, view_model, adapter, live_kit = _production_adapter()
    row = fixture.browser_rows[0]

    adapter.request_add_to_kit(0)
    assert adapter.assign_live_kit_slot("Drums", "Main Drum") is True

    assert live_kit.state.assignment_for("Drums", "Main Drum") is row
    assert live_kit.groups[1].slots[0].assignment is row
    projected = view_model.qml_context()["liveKitGroups"][1]["slots"][0]
    assert projected["assigned"] is True
    assert projected["assignment"] == row.display_name


def test_add_routes_through_the_existing_live_kit_state_seam():
    calls = []

    class RecordingState(LiveKitState):
        def assign(self, group, slot, row):
            calls.append((group, slot, row))
            super().assign(group, slot, row)

    fixture, _view_model, adapter, _live_kit = _production_adapter(state=RecordingState())
    row = fixture.browser_rows[0]

    adapter.request_add_to_kit(0)
    assert adapter.assign_live_kit_slot("Drums", "Main Drum") is True
    assert calls == [("Drums", "Main Drum", row)]


def test_replacement_overwrites_only_the_explicit_target_slot():
    fixture, _view_model, adapter, live_kit = _production_adapter()
    first = fixture.browser_rows[0]
    second = fixture.browser_rows[1]

    adapter.request_add_to_kit(0)
    assert adapter.assign_live_kit_slot("Drums", "Main Drum") is True
    adapter.request_add_to_kit(1)
    assert adapter.assign_live_kit_slot("Drums", "Main Drum") is True

    assert live_kit.state.assignment_for("Drums", "Main Drum") is second
    assert live_kit.state.assignment_for("Drums", "Closed Hat") is None
    assert live_kit.state.assignment_for("Drums", "Open Hat") is None
    assert (
        sum(
            1
            for slot in live_kit.groups[1].slots
            if slot.assignment is second
        )
        == 1
    )
    assert first is not second


def test_pending_intent_and_escape_cancel_never_mutate_the_kit():
    fixture, _view_model, adapter, live_kit = _production_adapter()

    adapter.request_add_to_kit(0)
    assert adapter.pending_live_kit_add == fixture.browser_rows[0].display_name
    assert all(
        slot.assignment is None for group in live_kit.groups for slot in group.slots
    )

    assert adapter.cancel_live_kit_add() is True
    assert adapter.pending_live_kit_add == ""
    assert all(
        slot.assignment is None for group in live_kit.groups for slot in group.slots
    )
    assert adapter.cancel_live_kit_add() is False


def test_assign_without_pending_uses_selected_row_without_mutating_other_state():
    fixture, _view_model, adapter, live_kit = _production_adapter()
    adapter.select_row(4)

    assert adapter.assign_live_kit_slot("Drums", "Closed Hat") is True
    assert live_kit.state.assignment_for("Drums", "Closed Hat") is fixture.browser_rows[4]
    assert live_kit.state.assignment_for("Drums", "Main Drum") is None


def test_browser_and_harmony_add_intents_stay_compatible_and_seed_pending():
    added = []
    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(
        fixture,
        "screen1-default-3panel",
    )
    live_kit = LiveKitPresenter()
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        live_kit=live_kit,
        on_add_to_kit_requested=added.append,
    )
    view_model.live_kit_groups = live_kit.groups

    assert adapter.request_add_to_kit(4) is fixture.browser_rows[4]
    assert added == [fixture.browser_rows[4]]
    assert adapter.pending_live_kit_add == fixture.browser_rows[4].display_name
    assert view_model.live_kit_groups is live_kit.groups
    assert view_model.live_kit_groups[1].slots[0].assignment is None


def test_harmonic_default_toggle_preserves_runtime_live_kit_state():
    fixture, view_model, adapter, live_kit = _production_adapter()
    row = fixture.browser_rows[0]
    adapter.request_add_to_kit(0)
    assert adapter.assign_live_kit_slot("Drums", "Main Drum") is True
    live_kit_before = live_kit.groups
    assert view_model.live_kit_groups is live_kit_before

    assert adapter.toggle_harmonic_match() is True
    assert view_model.panel_count == 4
    assert view_model.live_kit_groups is live_kit.groups
    assert view_model.live_kit_groups is live_kit_before
    assert live_kit.state.assignment_for("Drums", "Main Drum") is row

    assert adapter.toggle_harmonic_match() is False
    assert view_model.panel_count == 3
    assert view_model.live_kit_groups is live_kit_before


def test_qml_renders_only_the_projection_without_domain_duplication():
    for forbidden in (
        "LiveKitState",
        "LiveKitPresentationState",
        "assignment_for",
        "slots_for",
        "toggle_group",
        "LIVE_KIT_SLOT_MAPPING",
        "Kick + Bass",
        "Main Drum",
        "Closed Hat",
        "Open Hat",
        "Percussion",
        "Additional",
        "Melodic",
        "Atmos / FX",
        "Slot wählen",
    ):
        assert forbidden not in QML_SOURCE, forbidden
    assert "window.screenData.liveKitGroups" in QML_SOURCE
    assert "liveKitAssignedCount" in QML_SOURCE
    assert "liveKitTotalSlotCount" in QML_SOURCE
    assert '" / 11"' not in QML_SOURCE
    assert 'objectName: "liveKitPane"' in QML_SOURCE


def test_qml_header_and_panels_remain_structurally_stable():
    assert QML_SOURCE.count("LIVE KIT") == 1
    assert 'text: "MASTER"' in QML_SOURCE
    assert 'text: "GRID"' in QML_SOURCE
    assert 'text: "SYNC"' in QML_SOURCE
    assert QML_SOURCE.count("visible: window.interaction.harmonicMatchOpen") == 1
    assert "Layout.preferredWidth: visible ? 360 : 0" in QML_SOURCE
    assert 'objectName: "harmonicMatchButton"' in QML_SOURCE


def test_qml_exposes_pending_and_slot_action_wiring():
    assert "liveKitPendingAdd" in QML_SOURCE
    assert "toggleLiveKitGroup(" in QML_SOURCE
    assert "addLiveKitSlot(" in QML_SOURCE
    assert "cancelLiveKitAdd" in QML_SOURCE
    assert "window.interaction.liveKitPendingAdd !== \"\"" in QML_SOURCE
    assert "Keys.onEscapePressed: window.interaction.cancelLiveKitAdd()" in QML_SOURCE
    assert "modelData.assigned" in QML_SOURCE


def test_qml_group_header_hit_area_is_structurally_valid():
    wrapper = (
        "Item { Layout.fillWidth: true; Layout.preferredHeight: 44; "
        "Layout.leftMargin: 12; Layout.rightMargin: 10"
    )
    assert wrapper in QML_SOURCE
    assert QML_SOURCE.count(wrapper) == 1
    assert "RowLayout { anchors.fill: parent; spacing: 6" in QML_SOURCE
    assert 'objectName: "liveKitGroupHeader" + index' in QML_SOURCE
    assert "anchors.fill: parent\n                                    onClicked: window.interaction.toggleLiveKitGroup(kitGroupIndex)" in QML_SOURCE
    assert "LiveKitState" not in QML_SOURCE


def test_qml_values_blood_red_only_for_active_group_and_pending_intent():
    assert "border.color: modelData.active ? window.accent : window.border" in QML_SOURCE
    assert (
        "border.color: window.interaction.liveKitPendingAdd !== \"\" ? window.accent : \"transparent\""
        in QML_SOURCE
    )
    assert 'text: "+"' in QML_SOURCE


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="PySide6 Qt Quick ist in dieser Testumgebung nicht installiert.",
)
def test_qml_live_kit_runtime_roundtrip_pending_assign_and_group_toggle():
    from PySide6.QtCore import Qt
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest

    from src.workbench_qml_spike import _qml_engine, _settle_qml_frame

    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(
        fixture,
        "screen1-default-3panel",
    )
    live_kit = LiveKitPresenter()
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        live_kit=live_kit,
    )
    view_model.live_kit_groups = live_kit.groups
    app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    window.show()
    _settle_qml_frame(app)
    try:
        bridge = engine._screen1_interaction_bridge
        pane = window.findChild(QQuickItem, "liveKitPane")
        assert pane is not None
        banner = window.findChild(QQuickItem, "liveKitPendingBanner")
        assert banner is not None
        assert pane.property("visible") is True

        projected = window.property("screenData").property("liveKitGroups")
        assert tuple(group["name"] for group in projected) == CANONICAL_GROUPS
        screen_data = window.property("screenData")
        assert screen_data.property("liveKitTotalSlotCount") == sum(
            len(_slots) for _group, _slots in LIVE_KIT_SLOT_MAPPING
        )
        assert screen_data.property("liveKitAssignedCount") == 0

        bridge.addToKit(4)
        app.processEvents()
        assert (
            window.property("interaction").property("liveKitPendingAdd")
            == fixture.browser_rows[4].display_name
        )
        assert banner.property("visible") is True
        assert live_kit.groups[1].slots[0].assignment is None

        bridge.addLiveKitSlot(1, 0)
        app.processEvents()
        assert live_kit.state.assignment_for("Drums", "Main Drum") is fixture.browser_rows[4]
        assert adapter.pending_live_kit_add == ""
        assert banner.property("visible") is False
        after = window.property("screenData").property("liveKitGroups")
        assert after[1]["slots"][0]["assigned"] is True
        assert after[1]["slots"][0]["assignment"] == fixture.browser_rows[4].display_name

        bridge.addToKit(5)
        app.processEvents()
        assert adapter.pending_live_kit_add == fixture.browser_rows[5].display_name
        assert banner.property("visible") is True
        bridge.cancelLiveKitAdd()
        app.processEvents()
        assert adapter.pending_live_kit_add == ""
        assert banner.property("visible") is False
        assert live_kit.state.assignment_for("Drums", "Closed Hat") is None

        def group_header(index: int) -> QQuickItem:
            target = f"liveKitGroupHeader{index}"
            to_visit = [pane]
            while to_visit:
                current = to_visit.pop()
                if current.objectName() == target:
                    return current
                to_visit.extend(current.childItems())
            raise AssertionError(f"kein Live Kit Gruppen-Header {target} gefunden")

        def click_group_header(index: int) -> None:
            header = group_header(index)
            QTest.mouseClick(
                window,
                Qt.LeftButton,
                Qt.NoModifier,
                header.mapToScene(header.boundingRect().center()).toPoint(),
            )
            app.processEvents()

        def canonical_start() -> None:
            for index, want_active in (
                (0, False),
                (1, True),
                (2, False),
                (3, False),
            ):
                if live_kit.groups[index].active is not want_active:
                    bridge.toggleLiveKitGroup(index)
                    app.processEvents()

        canonical_start()
        assert live_kit.groups[1].active is True
        click_group_header(1)
        assert live_kit.groups[1].active is False
        collapsed = window.property("screenData").property("liveKitGroups")
        assert collapsed[1]["active"] is False
        assert live_kit.state.assignment_for("Drums", "Main Drum") is fixture.browser_rows[4]
        assert view_model.live_kit_groups is live_kit.groups

        click_group_header(1)
        assert live_kit.groups[1].active is True
        assert live_kit.state.assignment_for("Drums", "Main Drum") is fixture.browser_rows[4]
    finally:
        window.close()
        app.processEvents()
        timer = getattr(engine, "_screen1_waveform_timer", None)
        if timer is not None:
            timer.stop()
        loader = getattr(engine, "_screen1_waveform_loader", None)
        if loader is not None:
            loader.close()


def test_live_kit_denominator_derives_from_projected_groups():
    live_kit = LiveKitPresenter()
    projected_total = sum(len(group.slots) for group in live_kit.groups)
    canonical_total = sum(len(slots) for _group, slots in LIVE_KIT_SLOT_MAPPING)

    assert canonical_total == 11
    assert projected_total == canonical_total
    assert tuple(
        (group.name, len(group.slots)) for group in live_kit.groups
    ) == tuple((group, len(slots)) for group, slots in LIVE_KIT_SLOT_MAPPING)


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="PySide6 Qt Quick ist in dieser Testumgebung nicht installiert.",
)
def test_qml_live_kit_total_slot_count_follows_the_projected_slot_set():
    from PySide6.QtGui import QGuiApplication

    from src.workbench_qml import (
        QmlLiveKitGroup,
        QmlLiveKitSlot,
        _qml_screen_data_bridge,
    )

    app = QGuiApplication.instance() or QGuiApplication([])
    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(
        fixture,
        "screen1-default-3panel",
    )
    restricted = (
        QmlLiveKitGroup(
            "Kick + Bass",
            (QmlLiveKitSlot("Kick", _row("kick_01.wav")),),
            False,
        ),
        QmlLiveKitGroup(
            "Drums",
            (
                QmlLiveKitSlot("Main Drum", None),
                QmlLiveKitSlot("Closed Hat", _row("closed_hat_01.wav")),
            ),
            False,
        ),
    )
    view_model.live_kit_groups = restricted
    screen_data = _qml_screen_data_bridge(view_model)

    assert screen_data.property("liveKitTotalSlotCount") == 3
    assert screen_data.property("liveKitAssignedCount") == 2
    assert screen_data.property("liveKitTotalSlotCount") != 11