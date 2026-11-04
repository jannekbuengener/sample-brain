"""#743 / #1377 Live Kit disclosure — vertical rack starts expanded.

#1377 Owner decision: first Live Kit reveal shows every group's slot fields
in a vertical rack (no collapse arrows). ``active_group`` may still be
``None``. Accordion toggle remains for legacy callers. Assignment / audition /
export semantics stay outside presentation disclosure.
"""

from __future__ import annotations

import importlib.util
import pytest

from src.workbench_controller import WorkbenchRow
from src.workbench_live_kit import (
    LIVE_KIT_GROUPS,
    LIVE_KIT_SLOT_MAPPING,
    LiveKitPresentationState,
    LiveKitState,
)
from src.workbench_qml import LiveKitPresenter, QML_SOURCE
from src.workbench_qml_spike import (
    Screen1QmlInteractionAdapter,
    build_qml_view_model_from_fixture,
)
from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1


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


def test_new_presentation_state_expands_every_group_for_vertical_rack():
    presentation = LiveKitPresentationState(LiveKitState())

    assert presentation.active_group() is None
    assert tuple(presentation.is_collapsed(group) for group in LIVE_KIT_GROUPS) == (
        False,
        False,
        False,
        False,
    )
    assert LIVE_KIT_GROUPS == CANONICAL_GROUPS


def test_live_kit_presenter_projects_all_groups_active_at_first_reveal():
    live_kit = LiveKitPresenter()

    assert live_kit.presentation.active_group() is None
    assert tuple(group.name for group in live_kit.groups) == CANONICAL_GROUPS
    assert all(group.active is True for group in live_kit.groups)


def _collapse_all(presentation: LiveKitPresentationState) -> None:
    """Legacy accordion seed — vertical rack starts expanded (#1377)."""
    for group in LIVE_KIT_GROUPS:
        if not presentation.is_collapsed(group):
            presentation.toggle_group(group)


def test_explicit_drums_expand_then_collapse_returns_to_all_collapsed():
    presentation = LiveKitPresentationState(LiveKitState())
    _collapse_all(presentation)

    assert presentation.toggle_group("Drums") is False
    assert presentation.active_group() == "Drums"
    assert presentation.is_collapsed("Drums") is False
    assert all(
        presentation.is_collapsed(group)
        for group in LIVE_KIT_GROUPS
        if group != "Drums"
    )

    assert presentation.toggle_group("Drums") is True
    assert presentation.active_group() is None
    assert all(presentation.is_collapsed(group) for group in LIVE_KIT_GROUPS)


def test_accordion_switch_to_other_group_preserves_one_active_group():
    presentation = LiveKitPresentationState(LiveKitState())
    _collapse_all(presentation)

    assert presentation.toggle_group("Drums") is False
    assert presentation.toggle_group("Melodic") is False

    assert presentation.active_group() == "Melodic"
    assert presentation.is_collapsed("Melodic") is False
    assert presentation.is_collapsed("Drums") is True
    assert all(
        presentation.is_collapsed(group)
        for group in LIVE_KIT_GROUPS
        if group != "Melodic"
    )


def test_collapse_expand_does_not_mutate_assignments():
    state = LiveKitState()
    assigned = _row()
    state.assign("Drums", "Closed Hat", assigned)
    presentation = LiveKitPresentationState(state)
    _collapse_all(presentation)

    presentation.toggle_group("Drums")
    presentation.toggle_group("Kick + Bass")
    presentation.toggle_group("Kick + Bass")

    assert state.assignment_for("Drums", "Closed Hat") is assigned
    assert presentation.active_group() is None
    assert all(presentation.is_collapsed(group) for group in LIVE_KIT_GROUPS)


def test_add_to_kit_pending_works_with_initially_expanded_groups():
    fixture, view_model, adapter, live_kit = _production_adapter()

    assert all(group.active is True for group in live_kit.groups)
    adapter.request_add_to_kit(0)
    assert adapter.pending_live_kit_add == fixture.browser_rows[0].display_name
    # #1377: vertical rack keeps every group expanded; pending Add still marks
    # the preferred empty group as active without collapsing siblings.
    assert live_kit.presentation.active_group() == "Kick + Bass"
    assert all(group.active is True for group in live_kit.groups)

    assert adapter.assign_live_kit_slot("Drums", "Main Drum") is True
    assert live_kit.state.assignment_for("Drums", "Main Drum") is fixture.browser_rows[0]
    assert adapter.pending_live_kit_add == ""
    assert view_model.live_kit_groups is live_kit.groups


def test_pending_add_auto_expands_first_empty_group_slots_reachable():
    fixture, view_model, adapter, live_kit = _production_adapter()
    live_kit.assign("Kick + Bass", "Kick", _row("kick_occupied.wav"))

    adapter.request_add_to_kit(0)

    assert adapter.pending_live_kit_add == fixture.browser_rows[0].display_name
    # Kick+Bass still has empty Bass slot → stays preferred first empty group.
    assert live_kit.presentation.active_group() == "Kick + Bass"
    assert adapter.assign_live_kit_slot("Kick + Bass", "Bass") is True
    assert live_kit.state.assignment_for("Kick + Bass", "Bass") is fixture.browser_rows[0]


def test_qml_vertical_rack_shows_slots_without_collapse_gate():
    assert 'objectName: "liveKitVerticalRack"' in QML_SOURCE
    assert "model: modelData.slots" in QML_SOURCE
    assert "liveKitGroupPlus" in QML_SOURCE
    assert "appendEmptyLiveKitSlot" in QML_SOURCE


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="PySide6 is required for the Screen-1 QML Live Kit disclosure path",
)
def test_qml_first_reveal_shows_vertical_rack_slots_and_plus():
    from PySide6.QtQuick import QQuickItem

    from src.workbench_qml_spike import _qml_engine, _settle_qml_frame

    fixture, view_model, adapter, live_kit = _production_adapter()
    assert live_kit.presentation.active_group() is None
    assert all(group.active is True for group in live_kit.groups)

    view_model.live_kit_materialized = True
    adapter._live_kit_drawer_open = True
    adapter.live_kit_collapsed = False
    app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    window.show()
    _settle_qml_frame(app)
    try:
        pane = window.findChild(QQuickItem, "liveKitPane")
        assert pane is not None
        assert pane.property("visible") is True
        assert window.findChild(QQuickItem, "liveKitVerticalRack") is not None

        projected = window.property("screenData").property("liveKitGroups")
        assert tuple(group["name"] for group in projected) == CANONICAL_GROUPS
        assert all(group["active"] is True for group in projected)

        def find_named(root: QQuickItem, name: str) -> QQuickItem | None:
            to_visit = [root]
            while to_visit:
                current = to_visit.pop()
                if current.objectName() == name:
                    return current
                to_visit.extend(current.childItems())
            return None

        for index in range(4):
            assert find_named(pane, f"liveKitGroupHeader{index}") is not None
            assert find_named(pane, f"liveKitGroupPlus{index}") is not None

        for group_index, (_group, slots) in enumerate(LIVE_KIT_SLOT_MAPPING):
            for slot_index in range(len(slots)):
                assert (
                    find_named(pane, f"liveKitSlot{group_index}_{slot_index}") is not None
                )
        assert fixture.browser_rows[0] is not None
    finally:
        window.close()
        app.processEvents()
        timer = getattr(engine, "_screen1_waveform_timer", None)
        if timer is not None:
            timer.stop()
        loader = getattr(engine, "_screen1_waveform_loader", None)
        if loader is not None:
            loader.close()
