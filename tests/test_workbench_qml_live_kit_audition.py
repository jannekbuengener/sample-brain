"""RED contracts for [#545] QML Live Kit slot audition — shared playback and focused state.

Slice 2 under #545: the production Screen-1 QML shell gains one compact audition
affordance for ASSIGNED Live Kit slots.  Auditioning plays the slot's exact
assigned WorkbenchRow through the existing shared preview/playback owner seam
(``_on_preview_requested``), projects an honest Python-authoritative
focused/auditioning slot state, never re-reads or changes the Browser
selection, never mutates the slot assignment, and reuses the existing Stop
contract (``stop_preview``) for Escape/Stop.

QML stays a pure projection reader: the audition glyph and the auditioning
visual state come only from projected keys (``assigned`` / ``auditioning``),
never from QML audio/domain logic.
"""

from __future__ import annotations

import importlib.util

import pytest

from src.workbench_controller import WorkbenchRow
from src.workbench_live_kit import LiveKitState
from src.workbench_qml import LiveKitPresenter, QML_SOURCE
from src.workbench_qml_spike import (
    Screen1QmlInteractionAdapter,
    _qml_engine,
    _settle_qml_frame,
    build_qml_view_model_from_fixture,
)
from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1


def _row(name: str = "assigned_slot.wav") -> WorkbenchRow:
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


def _production_adapter(**kwargs):
    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(
        fixture,
        "screen1-default-3panel",
    )
    live_kit = LiveKitPresenter()
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        live_kit=live_kit,
        **kwargs,
    )
    view_model.live_kit_groups = live_kit.groups
    return fixture, view_model, adapter, live_kit


def _assign(adapter, live_kit, group, slot, row) -> None:
    live_kit.assign(group, slot, row)
    adapter._sync_live_kit_projection()


def test_empty_slot_audition_fails_closed_and_dispatches_nothing():
    previews = []
    _fixture, _view_model, adapter, _live_kit = _production_adapter(
        on_preview_requested=previews.append,
    )

    assert adapter.audition_live_kit_slot("Drums", "Percussion") is False
    assert previews == []
    assert adapter.preview_active is False
    assert adapter.auditioning_live_kit_slot is None


def test_assigned_slot_auditions_exactly_its_own_workbench_row():
    previews = []
    _fixture, _view_model, adapter, live_kit = _production_adapter(
        on_preview_requested=previews.append,
    )
    assigned = _row("main_drum.wav")
    _assign(adapter, live_kit, "Drums", "Main Drum", assigned)

    assert adapter.audition_live_kit_slot("Drums", "Main Drum") is True
    assert previews == [assigned]


def test_slot_audition_never_reads_or_changes_browser_selection():
    previews = []
    fixture, view_model, adapter, live_kit = _production_adapter(
        on_preview_requested=previews.append,
    )
    assigned = _row("closed_hat.wav")
    _assign(adapter, live_kit, "Drums", "Closed Hat", assigned)
    selected_before = adapter.selected_browser_index
    browser_rows_before = view_model.browser_rows

    assert adapter.audition_live_kit_slot("Drums", "Closed Hat") is True

    assert previews == [assigned]
    assert fixture.browser_rows[selected_before] is not assigned
    assert adapter.selected_browser_index == selected_before
    assert view_model.browser_rows is browser_rows_before


def test_slot_audition_dispatches_exactly_one_preview_and_marks_active():
    previews = []
    _fixture, _view_model, adapter, live_kit = _production_adapter(
        on_preview_requested=previews.append,
    )
    _assign(adapter, live_kit, "Drums", "Main Drum", _row("main.wav"))

    assert adapter.audition_live_kit_slot("Drums", "Main Drum") is True

    assert len(previews) == 1
    assert adapter.preview_active is True
    assert adapter.auditioning_live_kit_slot == ("Drums", "Main Drum")


def test_slot_audition_browser_preview_and_harmony_share_one_playback_seam():
    previews = []
    fixture, _view_model, adapter, live_kit = _production_adapter(
        on_preview_requested=previews.append,
    )
    slot_row = _row("atmos.wav")
    _assign(adapter, live_kit, "Atmos / FX", "Atmos", slot_row)
    browser_row = fixture.browser_rows[0]

    assert adapter.preview_row(0) is browser_row
    assert adapter.audition_live_kit_slot("Atmos / FX", "Atmos") is True

    assert previews == [browser_row, slot_row]
    assert adapter.auditioning_live_kit_slot == ("Atmos / FX", "Atmos")


def test_a_to_b_slot_audition_replacement_dispatches_twice_and_switches_focus():
    previews = []
    _fixture, _view_model, adapter, live_kit = _production_adapter(
        on_preview_requested=previews.append,
    )
    first = _row("first.wav")
    second = _row("second.wav")
    _assign(adapter, live_kit, "Drums", "Main Drum", first)
    _assign(adapter, live_kit, "Drums", "Closed Hat", second)

    assert adapter.audition_live_kit_slot("Drums", "Main Drum") is True
    assert adapter.audition_live_kit_slot("Drums", "Closed Hat") is True

    assert previews == [first, second]
    assert len(previews) == 2
    assert adapter.auditioning_live_kit_slot == ("Drums", "Closed Hat")
    assert adapter.preview_active is True


def test_stop_clears_the_projected_auditioning_state_via_real_stop_contract():
    stops = []
    _fixture, _view_model, adapter, live_kit = _production_adapter(
        on_preview_requested=lambda _row: None,
        on_preview_stopped=lambda: stops.append("stop"),
    )
    _assign(adapter, live_kit, "Drums", "Open Hat", _row("open.wav"))

    assert adapter.audition_live_kit_slot("Drums", "Open Hat") is True
    assert adapter.auditioning_live_kit_slot == ("Drums", "Open Hat")
    assert adapter.stop_preview() is True
    assert adapter.preview_active is False
    assert adapter.auditioning_live_kit_slot is None
    assert stops == ["stop"]
    assert adapter.stop_preview() is False
    assert stops == ["stop"]


def test_audition_and_stop_never_mutate_slot_assignments():
    _fixture, _view_model, adapter, live_kit = _production_adapter()
    assigned = _row("pad.wav")
    _assign(adapter, live_kit, "Melodic", "Pad", assigned)

    assert adapter.audition_live_kit_slot("Melodic", "Pad") is True
    assert live_kit.state.assignment_for("Melodic", "Pad") is assigned
    adapter.stop_preview()
    assert live_kit.state.assignment_for("Melodic", "Pad") is assigned
    assert live_kit.state.assignment_for("Melodic", "Lead") is None


def test_slot_audition_fields_browser_preview_projection_advance():
    previews = []
    fixture, _view_model, adapter, live_kit = _production_adapter(
        on_preview_requested=previews.append,
    )
    assigned = _row("kick.wav")
    _assign(adapter, live_kit, "Kick + Bass", "Kick", assigned)

    assert adapter.audition_live_kit_slot("Kick + Bass", "Kick") is True
    assert adapter.auditioning_live_kit_slot == ("Kick + Bass", "Kick")

    assert adapter.preview_row(2) is fixture.browser_rows[2]
    assert adapter.auditioning_live_kit_slot is None
    assert adapter.preview_active is True
    assert previews == [assigned, fixture.browser_rows[2]]


def test_collapse_expand_does_not_stop_or_mutate_playback():
    _fixture, _view_model, adapter, live_kit = _production_adapter(
        on_preview_requested=lambda _row: None,
    )
    _assign(adapter, live_kit, "Drums", "Main Drum", _row("main.wav"))

    assert adapter.audition_live_kit_slot("Drums", "Main Drum") is True
    assert adapter.toggle_live_kit_group("Drums") is True

    assert adapter.preview_active is True
    assert adapter.auditioning_live_kit_slot == ("Drums", "Main Drum")
    assert live_kit.state.assignment_for("Drums", "Main Drum") is not None
    assert adapter.toggle_live_kit_group("Drums") is False
    assert adapter.auditioning_live_kit_slot == ("Drums", "Main Drum")


def test_harmonic_toggle_does_not_mutate_live_kit_playback_state():
    _fixture, view_model, adapter, live_kit = _production_adapter(
        on_preview_requested=lambda _row: None,
    )
    _assign(adapter, live_kit, "Drums", "Main Drum", _row("main.wav"))
    assert adapter.audition_live_kit_slot("Drums", "Main Drum") is True
    audition_target = adapter.auditioning_live_kit_slot

    assert adapter.toggle_harmonic_match() is True
    assert view_model.panel_count == 4
    assert adapter.preview_active is True
    assert adapter.auditioning_live_kit_slot == audition_target
    assert live_kit.state.assignment_for("Drums", "Main Drum") is not None

    assert adapter.toggle_harmonic_match() is False
    assert view_model.panel_count == 3
    assert adapter.auditioning_live_kit_slot == audition_target


def test_add_replace_collapse_regressions_stay_green_with_audition_present():
    fixture, _view_model, adapter, live_kit = _production_adapter()
    row = fixture.browser_rows[0]
    replacement = fixture.browser_rows[1]

    adapter.request_add_to_kit(0)
    assert adapter.assign_live_kit_slot("Drums", "Main Drum") is True
    adapter.request_add_to_kit(1)
    assert adapter.assign_live_kit_slot("Drums", "Main Drum") is True
    assert live_kit.state.assignment_for("Drums", "Main Drum") is replacement
    assert live_kit.state.assignment_for("Drums", "Closed Hat") is None

    assert adapter.audition_live_kit_slot("Drums", "Main Drum") is True
    assert adapter.toggle_live_kit_group("Drums") is True
    assert adapter.auditioning_live_kit_slot == ("Drums", "Main Drum")


def test_slot_replacement_clears_the_auditioning_projection():
    fixture, view_model, adapter, live_kit = _production_adapter(
        on_preview_requested=lambda _row: None,
    )
    first = _row("first.wav")
    _assign(adapter, live_kit, "Melodic", "Pad", first)

    assert adapter.audition_live_kit_slot("Melodic", "Pad") is True
    assert adapter.auditioning_live_kit_slot == ("Melodic", "Pad")

    replacement = view_model.browser_rows[0].source_row
    assert replacement is not first
    adapter.request_add_to_kit(0)
    assert adapter.assign_live_kit_slot("Melodic", "Pad") is True

    assert live_kit.state.assignment_for("Melodic", "Pad") is replacement
    assert adapter.auditioning_live_kit_slot is None
    assert view_model.auditioning_live_kit_slot is None


def test_failed_replacement_audition_stops_prior_playback_and_clears_projection():
    stops = []
    fixture, view_model, adapter, live_kit = _production_adapter(
        on_preview_requested=_rejecting_probe(rejected_name="b.wav"),
        on_preview_stopped=lambda: stops.append("stop"),
    )
    selected_before = adapter.selected_browser_index
    drum_a = _row("a.wav")
    reject_b = _row("b.wav")
    _assign(adapter, live_kit, "Drums", "Main Drum", drum_a)
    _assign(adapter, live_kit, "Drums", "Closed Hat", reject_b)

    assert adapter.audition_live_kit_slot("Drums", "Main Drum") is True
    assert adapter.preview_active is True

    assert adapter.audition_live_kit_slot("Drums", "Closed Hat") is False
    assert stops == ["stop"]
    assert adapter.preview_active is False
    assert adapter.auditioning_live_kit_slot is None
    assert view_model.auditioning_live_kit_slot is None
    assert live_kit.state.assignment_for("Drums", "Main Drum") is drum_a
    assert live_kit.state.assignment_for("Drums", "Closed Hat") is reject_b
    assert adapter.selected_browser_index == selected_before


def test_live_kit_audition_requests_zero_offset_while_browser_keeps_cue():
    calls = []
    fixture, _view_model, adapter, live_kit = _production_adapter(
        on_preview_requested=lambda row, *, start_ms=None: calls.append((row, start_ms)),
    )
    slot_row = _row("cue.wav")
    _assign(adapter, live_kit, "Drums", "Main Drum", slot_row)
    browser_row = fixture.browser_rows[0]

    assert adapter.preview_row(0) is browser_row
    assert adapter.audition_live_kit_slot("Drums", "Main Drum") is True

    assert calls[0] == (browser_row, None)
    assert calls[1] == (slot_row, 0)
    assert adapter.auditioning_live_kit_slot == ("Drums", "Main Drum")


def test_browser_preview_failure_stops_prior_playback_and_clears_projection():
    stops = []
    fixture, view_model, adapter, live_kit = _production_adapter(
        on_preview_requested=_rejecting_probe(rejected_name="TECH_KICK_02.wav"),
        on_preview_stopped=lambda: stops.append("stop"),
    )
    _assign(adapter, live_kit, "Drums", "Main Drum", _row("main.wav"))

    assert adapter.audition_live_kit_slot("Drums", "Main Drum") is True
    assert adapter.preview_active is True
    assert stops == []

    failing_index = 1
    assert adapter.preview_row(failing_index) is fixture.browser_rows[failing_index]
    assert stops == ["stop"]
    assert adapter.preview_active is False
    assert adapter.auditioning_live_kit_slot is None
    assert view_model.auditioning_live_kit_slot is None
    assert adapter.stop_preview() is False


def test_harmonic_preview_failure_stops_prior_playback_and_clears_projection():
    stops = []
    _fixture, _view_model, adapter, live_kit = _production_adapter(
        on_preview_requested=_rejecting_probe(rejected_name="TECH_PAD_01.wav"),
        on_preview_stopped=lambda: stops.append("stop"),
    )
    _assign(adapter, live_kit, "Drums", "Main Drum", _row("main.wav"))

    assert adapter.audition_live_kit_slot("Drums", "Main Drum") is True
    assert adapter.preview_active is True
    assert stops == []

    failing_index = 2
    assert adapter.select_harmonic_match(failing_index) is not None
    assert adapter.preview_harmonic_match(failing_index) is not None
    assert stops == ["stop"]
    assert adapter.preview_active is False
    assert adapter.auditioning_live_kit_slot is None
    assert adapter.stop_preview() is False


def _rejecting_probe(*, rejected_name: str):
    def probe(row, *, start_ms=None) -> object:
        if row.relative_path.endswith(rejected_name):
            return False
        return True

    return probe


def test_qml_pending_banner_escape_routes_through_bridge_contract():
    assert "Keys.onEscapePressed: window.interaction.escapeLiveKitContext()" in QML_SOURCE
    assert "Keys.onEscapePressed: window.interaction.cancelLiveKitAdd()" not in QML_SOURCE


def test_slot_audition_introduces_no_transport_or_second_clock():
    previews = []
    _fixture, _view_model, adapter, live_kit = _production_adapter(
        on_preview_requested=previews.append,
    )
    _assign(adapter, live_kit, "Drums", "Main Drum", _row("main.wav"))
    assert adapter.audition_live_kit_slot("Drums", "Main Drum") is True
    assert adapter.preview_active is True


def test_qml_slot_audition_wiring_has_no_audio_or_domain_implementation():
    for forbidden in (
        "play_row",
        "WorkbenchPreviewPlayer",
        "TransportAwarePreview",
        "WorkbenchTransportAdapter",
        "assignment_for",
        "slots_for",
        "LiveKitState",
        "LiveKitPresentationState",
        "start_ms",
        "soundfile",
        "PcmBuffer",
        "transport",
    ):
        assert forbidden not in QML_SOURCE, forbidden
    assert "auditionLiveKitSlot(" in QML_SOURCE
    assert "modelData.auditioning" in QML_SOURCE
    assert "▶" in QML_SOURCE
    assert "modelData.assigned" in QML_SOURCE
    assert "window.interaction.liveKitPendingAdd !== \"\"" in QML_SOURCE


def test_qml_live_kit_slot_audition_focused_state_is_subtle():
    assert "slotAuditionBackdrop" in QML_SOURCE
    assert "visible: modelData.auditioning" in QML_SOURCE
    assert "modelData.auditioning ? window.accent" in QML_SOURCE
    assert 'font.pixelSize: 10' in QML_SOURCE


def test_qml_replacement_target_is_separate_from_slot_audition_state():
    # Audition remains a projection of shared playback.  Replacement is only
    # the pending-add intent for the single hovered/focused target.
    assert "slotAuditionBackdrop" in QML_SOURCE
    assert "liveKitSlotTargetBackdrop" in QML_SOURCE
    assert "visible: modelData.auditioning" in QML_SOURCE
    assert "visible: liveKitSlotTarget" in QML_SOURCE
    assert "liveKitReplaceTarget" in QML_SOURCE
    assert "id: slotAdd" in QML_SOURCE
    assert "z: 1" in QML_SOURCE


def test_window_level_escape_stops_preview_independent_of_focus():
    assert "event.key === Qt.Key_Escape && window.interaction.previewActive" in QML_SOURCE
    assert "window.interaction.stopPreview()" in QML_SOURCE


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="PySide6 Qt Quick ist in dieser Testumgebung nicht installiert.",
)
def test_qml_live_kit_slot_audition_runtime_roundtrip_focus_and_stop():
    from PySide6.QtQuick import QQuickItem

    from src.workbench_qml_spike import _qml_engine

    previews = []
    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(
        fixture,
        "screen1-default-3panel",
    )
    live_kit = LiveKitPresenter()
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        live_kit=live_kit,
        on_preview_requested=previews.append,
    )
    _assign(adapter, live_kit, "Drums", "Main Drum", _row("runtime_main.wav"))
    view_model.live_kit_groups = live_kit.groups
    selected_before = adapter.selected_browser_index

    app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    window.show()
    _settle_qml_frame(app)
    try:
        bridge = engine._screen1_interaction_bridge
        pane = window.findChild(QQuickItem, "liveKitPane")
        assert pane is not None
        projected = window.property("screenData").property("liveKitGroups")
        assert projected[1]["slots"][0]["assigned"] is True

        bridge.auditionLiveKitSlot(1, 0)
        app.processEvents()
        asserted = window.property("screenData").property("liveKitGroups")
        assert asserted[1]["slots"][0]["auditioning"] is True
        assert asserted[1]["slots"][1]["auditioning"] is False
        assert window.property("interaction").property("previewActive") is True
        assert len(previews) == 1
        assert adapter.selected_browser_index == selected_before

        bridge.stopPreview()
        app.processEvents()
        stopped = window.property("screenData").property("liveKitGroups")
        assert stopped[1]["slots"][0]["auditioning"] is False
        assert window.property("interaction").property("previewActive") is False
    finally:
        window.close()
        app.processEvents()
        timer = getattr(engine, "_screen1_waveform_timer", None)
        if timer is not None:
            timer.stop()
        loader = getattr(engine, "_screen1_waveform_loader", None)
        if loader is not None:
            loader.close()


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="PySide6 Qt Quick ist in dieser Testumgebung nicht installiert.",
)
def test_qml_repeated_audition_cycles_do_not_accumulate_qml_objects():
    from PySide6.QtQuick import QQuickItem

    _fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(
        _fixture,
        "screen1-default-3panel",
    )
    live_kit = LiveKitPresenter()
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        live_kit=live_kit,
    )
    _assign(adapter, live_kit, "Drums", "Main Drum", _row("main.wav"))
    _assign(adapter, live_kit, "Drums", "Closed Hat", _row("closed.wav"))
    view_model.live_kit_groups = live_kit.groups

    app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    window.show()
    _settle_qml_frame(app)
    try:
        bridge = engine._screen1_interaction_bridge
        pane = window.findChild(QQuickItem, "liveKitPane")

        def descendant_count():
            count = 0
            to_visit = [pane]
            while to_visit:
                current = to_visit.pop(0)
                count += 1
                to_visit.extend(current.childItems())
            return count

        def delegate_creations():
            return int(window.property("browserDelegateCreations") or 0)

        before_objects = descendant_count()
        before_delegates = delegate_creations()

        for index in range(5):
            bridge.auditionLiveKitSlot(1, index % 2)
            app.processEvents()
            bridge.stopPreview()
            app.processEvents()

        assert descendant_count() == before_objects
        assert delegate_creations() == before_delegates
    finally:
        window.close()
        app.processEvents()
        timer = getattr(engine, "_screen1_waveform_timer", None)
        if timer is not None:
            timer.stop()
        loader = getattr(engine, "_screen1_waveform_loader", None)
        if loader is not None:
            loader.close()


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="PySide6 not installed (Qt runtime tests)",
)
def test_qml_pending_banner_escape_stops_audition_and_cancels_add():
    from PySide6.QtCore import Qt
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest

    previews = []
    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(fixture, "screen1-default-3panel")
    live_kit = LiveKitPresenter()
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        live_kit=live_kit,
        on_preview_requested=previews.append,
    )
    _assign(adapter, live_kit, "Drums", "Main Drum", _row("banner.wav"))
    view_model.live_kit_groups = live_kit.groups

    app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    window.show()
    _settle_qml_frame(app)
    try:
        bridge = engine._screen1_interaction_bridge
        interaction = window.property("interaction")
        screen_data = window.property("screenData")
        banner = window.findChild(QQuickItem, "liveKitPendingBanner")
        assert banner is not None

        bridge.auditionLiveKitSlot(1, 0)
        app.processEvents()
        assert interaction.property("previewActive") is True
        assert screen_data.property("liveKitGroups")[1]["slots"][0]["auditioning"] is True

        bridge.addToKit(4)
        app.processEvents()
        assert interaction.property("liveKitPendingAdd") == fixture.browser_rows[4].display_name
        assert banner.property("visible") is True
        assert banner.property("activeFocus") is True

        QTest.keyClick(window, Qt.Key_Escape)
        app.processEvents()

        assert interaction.property("previewActive") is False
        assert screen_data.property("liveKitGroups")[1]["slots"][0]["auditioning"] is False
        assert interaction.property("liveKitPendingAdd") == ""
        assert banner.property("visible") is False
    finally:
        window.close()
        app.processEvents()
        timer = getattr(engine, "_screen1_waveform_timer", None)
        if timer is not None:
            timer.stop()
        loader = getattr(engine, "_screen1_waveform_loader", None)
        if loader is not None:
            loader.close()


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="PySide6 not installed (Qt runtime tests)",
)
def test_qml_window_level_escape_stops_live_kit_audition_from_any_focus():
    from PySide6.QtCore import Qt
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest

    previews = []
    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(fixture, "screen1-default-3panel")
    live_kit = LiveKitPresenter()
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        live_kit=live_kit,
        on_preview_requested=previews.append,
    )
    _assign(adapter, live_kit, "Drums", "Main Drum", _row("esc.wav"))
    view_model.live_kit_groups = live_kit.groups

    app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    window.show()
    _settle_qml_frame(app)
    try:
        bridge = engine._screen1_interaction_bridge
        interaction = window.property("interaction")
        screen_data = window.property("screenData")

        QTest.keyClick(window, Qt.Key_Escape)
        app.processEvents()
        assert interaction.property("previewActive") is False

        bridge.auditionLiveKitSlot(1, 0)
        app.processEvents()
        assert interaction.property("previewActive") is True
        assert len(previews) == 1

        library_tree = window.findChild(QQuickItem, "libraryTree")
        assert library_tree is not None
        library_tree.forceActiveFocus()
        app.processEvents()
        assert window.property("activeFocusItem") is library_tree
        assert window.property("activeFocusItem").property("objectName") != "browserList"

        QTest.keyClick(window, Qt.Key_Escape)
        app.processEvents()
        assert interaction.property("previewActive") is False
        assert screen_data.property("liveKitGroups")[1]["slots"][0]["auditioning"] is False
    finally:
        window.close()
        app.processEvents()
        timer = getattr(engine, "_screen1_waveform_timer", None)
        if timer is not None:
            timer.stop()
        loader = getattr(engine, "_screen1_waveform_loader", None)
        if loader is not None:
            loader.close()


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="PySide6 not installed (Qt runtime tests)",
)
def test_qml_rejected_audition_refreshes_cleared_projection():
    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(fixture, "screen1-default-3panel")
    live_kit = LiveKitPresenter()
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        live_kit=live_kit,
        on_preview_requested=_rejecting_probe(rejected_name="b.wav"),
    )
    _assign(adapter, live_kit, "Drums", "Main Drum", _row("a.wav"))
    _assign(adapter, live_kit, "Drums", "Closed Hat", _row("b.wav"))
    view_model.live_kit_groups = live_kit.groups

    app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    window.show()
    _settle_qml_frame(app)
    try:
        bridge = engine._screen1_interaction_bridge
        screen_model = engine._screen1_screen_model
        screen_data = window.property("screenData")
        live_kit_refreshes = []

        screen_model.liveKitGroupsChanged.connect(
            lambda: live_kit_refreshes.append("refresh")
        )

        bridge.auditionLiveKitSlot(1, 0)
        app.processEvents()
        assert screen_data.property("liveKitGroups")[1]["slots"][0]["auditioning"] is True

        bridge.auditionLiveKitSlot(1, 1)
        app.processEvents()
        assert live_kit_refreshes, (
            "rejected audition must emit liveKitGroupsChanged so the QML "
            "Repeater re-evaluates the cleared audition projection"
        )
        assert screen_data.property("liveKitGroups")[1]["slots"][0]["auditioning"] is False
    finally:
        window.close()
        app.processEvents()
        timer = getattr(engine, "_screen1_waveform_timer", None)
        if timer is not None:
            timer.stop()
        loader = getattr(engine, "_screen1_waveform_loader", None)
        if loader is not None:
            loader.close()
