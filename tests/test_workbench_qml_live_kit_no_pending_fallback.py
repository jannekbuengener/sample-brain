"""RED contracts for [#613] Preserve no-pending Live Kit slot add fallback after #612.

The regression in #612 made empty slots without pending add non-interactive,
breaking the fallback to selected browser row. This test file captures the
expected behavior that must be restored.

Key contracts:
1. Empty Slot + kein Pending Add + gültige Browser Selection → Action-Affordance ist interaktiv, exakt Selected Row wird assigned
2. Assigned Slot + kein Pending Add → primärer Slot-Klick auditioniert weiterhin, Assignment bleibt unverändert
3. Assigned Slot + kein Pending Add + explizite Replace-Affordance → Selected Browser Row ersetzt exakt diesen Slot
4. Pending Add + Empty Slot → bestehender #611 Add-Flow unverändert
5. Pending Add + Assigned Slot → bestehender #611 Replace-Flow unverändert
6. Audition-Affordance → ruft niemals Assignment auf
7. Assignment-Affordance → startet niemals Audition
8. Escape/Cancel → keine unbeabsichtigte Assignment-Mutation
9. Kein gültiger Selected Row und kein Pending Add → fail closed; keine Mutation
10. Nur expliziter Zielslot wird verändert
"""

from __future__ import annotations

import pytest

from src.workbench_controller import WorkbenchRow
from src.workbench_live_kit import LiveKitState
from src.workbench_qml import LiveKitPresenter
from src.workbench_qml_spike import (
    Screen1QmlInteractionAdapter,
    build_qml_view_model_from_fixture,
)
from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1


def _row(name: str = "test_row.wav") -> WorkbenchRow:
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


class TestNoPendingEmptySlotAdd:
    """Empty slot without pending add should use selected browser row."""

    def test_empty_slot_no_pending_add_with_valid_selection_assigns_selected_row(self):
        """Empty slot with valid browser selection should assign the selected row."""
        fixture, view_model, adapter, live_kit = _production_adapter()
        # Select a browser row
        adapter.select_row(4)
        selected_row = fixture.browser_rows[4]

        # No pending add
        assert adapter.pending_live_kit_add == ""

        # Assign to empty slot (Drums / Main Drum is first slot in Drums group)
        assert adapter.assign_live_kit_slot("Drums", "Main Drum") is True

        # Verify the selected row was assigned
        assert live_kit.state.assignment_for("Drums", "Main Drum") is selected_row
        # Other slots unchanged
        assert live_kit.state.assignment_for("Drums", "Closed Hat") is None

    def test_empty_slot_no_pending_add_no_selection_fails_closed(self):
        """Empty slot without pending add and without valid selection should fail closed."""
        fixture, view_model, adapter, live_kit = _production_adapter()
        # Empty browser rows - no valid selection possible
        view_model.browser_rows = ()
        adapter.view_model.selected_browser_index = -1

        assert adapter.pending_live_kit_add == ""
        assert adapter.assign_live_kit_slot("Drums", "Main Drum") is False
        assert live_kit.state.assignment_for("Drums", "Main Drum") is None

    def test_empty_slot_with_pending_add_uses_pending_row(self):
        """Empty slot with pending add should use the pending row (existing #611 behavior)."""
        fixture, view_model, adapter, live_kit = _production_adapter()
        pending_row = fixture.browser_rows[0]

        adapter.request_add_to_kit(0)
        assert adapter.pending_live_kit_add == pending_row.display_name

        assert adapter.assign_live_kit_slot("Drums", "Main Drum") is True
        assert live_kit.state.assignment_for("Drums", "Main Drum") is pending_row
        assert adapter.pending_live_kit_add == ""


class TestNoPendingAssignedSlotAudition:
    """Assigned slot primary click should audition, not assign."""

    def test_assigned_slot_primary_click_auditions_not_assigns(self):
        """Primary click on assigned slot should audition, not trigger assignment."""
        fixture, view_model, adapter, live_kit = _production_adapter()
        assigned_row = _row("assigned_drum.wav")
        _assign(adapter, live_kit, "Drums", "Main Drum", assigned_row)

        # Select a different browser row
        adapter.select_row(3)
        browser_row = fixture.browser_rows[3]

        # No pending add
        assert adapter.pending_live_kit_add == ""

        # Audition the slot
        previews = []
        adapter._on_preview_requested = previews.append
        assert adapter.audition_live_kit_slot("Drums", "Main Drum") is True

        # Should audition the assigned row, not the browser selection
        assert previews == [assigned_row]
        assert adapter.auditioning_live_kit_slot == ("Drums", "Main Drum")

        # Assignment should remain unchanged
        assert live_kit.state.assignment_for("Drums", "Main Drum") is assigned_row


class TestNoPendingAssignedSlotReplace:
    """Assigned slot with explicit replace affordance should replace."""

    def test_assigned_slot_replace_affordance_uses_selected_row(self):
        """Explicit replace affordance on assigned slot should use selected browser row."""
        fixture, view_model, adapter, live_kit = _production_adapter()
        original_row = _row("original.wav")
        _assign(adapter, live_kit, "Drums", "Main Drum", original_row)

        # Select a different browser row for replacement
        adapter.select_row(2)
        replacement_row = fixture.browser_rows[2]

        assert adapter.pending_live_kit_add == ""
        assert adapter.assign_live_kit_slot("Drums", "Main Drum") is True

        # Should replace with selected browser row
        assert live_kit.state.assignment_for("Drums", "Main Drum") is replacement_row
        assert live_kit.state.assignment_for("Drums", "Main Drum") is not original_row

    def test_assigned_slot_replace_with_pending_uses_pending_row(self):
        """Replace with pending add should use pending row (existing #611 behavior)."""
        fixture, view_model, adapter, live_kit = _production_adapter()
        original_row = _row("original.wav")
        _assign(adapter, live_kit, "Drums", "Main Drum", original_row)

        pending_row = fixture.browser_rows[1]
        adapter.request_add_to_kit(1)
        assert adapter.pending_live_kit_add == pending_row.display_name

        assert adapter.assign_live_kit_slot("Drums", "Main Drum") is True
        assert live_kit.state.assignment_for("Drums", "Main Drum") is pending_row
        assert adapter.pending_live_kit_add == ""


class TestPendingAddFlowsUnchanged:
    """Existing pending add flows from #611 must remain unchanged."""

    def test_pending_add_empty_slot_uses_pending_row(self):
        """Pending add to empty slot uses pending row."""
        fixture, view_model, adapter, live_kit = _production_adapter()
        pending_row = fixture.browser_rows[0]
        adapter.request_add_to_kit(0)

        assert adapter.assign_live_kit_slot("Drums", "Main Drum") is True
        assert live_kit.state.assignment_for("Drums", "Main Drum") is pending_row
        assert adapter.pending_live_kit_add == ""

    def test_pending_add_assigned_slot_replaces_with_pending_row(self):
        """Pending add to assigned slot replaces with pending row."""
        fixture, view_model, adapter, live_kit = _production_adapter()
        original_row = _row("original.wav")
        _assign(adapter, live_kit, "Drums", "Main Drum", original_row)

        pending_row = fixture.browser_rows[0]
        adapter.request_add_to_kit(0)

        assert adapter.assign_live_kit_slot("Drums", "Main Drum") is True
        assert live_kit.state.assignment_for("Drums", "Main Drum") is pending_row
        assert adapter.pending_live_kit_add == ""


class TestAuditionAndAssignmentSeparation:
    """Audition and Assignment affordances must be strictly separated."""

    def test_audition_never_calls_assign(self):
        """Audition must never trigger assignment mutation."""
        fixture, view_model, adapter, live_kit = _production_adapter()
        assigned_row = _row("audition_test.wav")
        _assign(adapter, live_kit, "Drums", "Main Drum", assigned_row)

        # Select different browser row
        adapter.select_row(2)
        browser_row = fixture.browser_rows[2]

        previews = []
        adapter._on_preview_requested = previews.append

        # Audition
        assert adapter.audition_live_kit_slot("Drums", "Main Drum") is True

        # Only preview should be dispatched, no assignment change
        assert previews == [assigned_row]
        assert live_kit.state.assignment_for("Drums", "Main Drum") is assigned_row

    def test_assignment_never_starts_audition(self):
        """Assignment must never start audition playback."""
        fixture, view_model, adapter, live_kit = _production_adapter()
        # Empty slot
        adapter.select_row(1)
        selected_row = fixture.browser_rows[1]

        previews = []
        adapter._on_preview_requested = previews.append

        # Assign (no pending)
        assert adapter.assign_live_kit_slot("Drums", "Main Drum") is True

        # Should NOT dispatch preview
        assert previews == []
        assert adapter.preview_active is False
        assert adapter.auditioning_live_kit_slot is None

        # But assignment should happen
        assert live_kit.state.assignment_for("Drums", "Main Drum") is selected_row

    def test_escape_cancel_never_mutates_assignment(self):
        """Escape/Cancel should not cause assignment mutations."""
        fixture, view_model, adapter, live_kit = _production_adapter()
        assigned_row = _row("escape_test.wav")
        _assign(adapter, live_kit, "Drums", "Main Drum", assigned_row)

        # Start audition
        previews = []
        adapter._on_preview_requested = previews.append
        assert adapter.audition_live_kit_slot("Drums", "Main Drum") is True

        # Escape: stop preview
        assert adapter.stop_preview() is True
        assert adapter.auditioning_live_kit_slot is None
        assert adapter.preview_active is False

        # Assignment unchanged
        assert live_kit.state.assignment_for("Drums", "Main Drum") is assigned_row

        # Cancel pending add (if any)
        adapter.request_add_to_kit(0)
        assert adapter.cancel_live_kit_add() is True
        assert adapter.pending_live_kit_add == ""

        # Assignment still unchanged
        assert live_kit.state.assignment_for("Drums", "Main Drum") is assigned_row


class TestOnlyExplicitTargetSlotChanged:
    """Only the explicitly targeted slot should be modified."""

    def test_assign_to_one_slot_does_not_affect_others(self):
        """Assigning to one slot must not affect other slots."""
        fixture, view_model, adapter, live_kit = _production_adapter()
        adapter.select_row(0)
        row0 = fixture.browser_rows[0]
        adapter.select_row(1)
        row1 = fixture.browser_rows[1]

        # Assign to Main Drum
        assert adapter.assign_live_kit_slot("Drums", "Main Drum") is True
        assert live_kit.state.assignment_for("Drums", "Main Drum") is row1  # selected was row1

        # Other slots in same group unchanged
        assert live_kit.state.assignment_for("Drums", "Closed Hat") is None
        assert live_kit.state.assignment_for("Drums", "Open Hat") is None

        # Other groups unchanged
        assert live_kit.state.assignment_for("Kick + Bass", "Kick") is None
        assert live_kit.state.assignment_for("Melodic", "Pad") is None

    def test_replace_one_slot_does_not_affect_others(self):
        """Replacing one slot must not affect other slots."""
        fixture, view_model, adapter, live_kit = _production_adapter()

        # Pre-assign multiple slots
        row_a = _row("a.wav")
        row_b = _row("b.wav")
        _assign(adapter, live_kit, "Drums", "Main Drum", row_a)
        _assign(adapter, live_kit, "Drums", "Closed Hat", row_b)

        # Select new row for replacement
        adapter.select_row(2)
        row_c = fixture.browser_rows[2]

        # Replace Main Drum only
        assert adapter.assign_live_kit_slot("Drums", "Main Drum") is True
        assert live_kit.state.assignment_for("Drums", "Main Drum") is row_c

        # Other slots unchanged
        assert live_kit.state.assignment_for("Drums", "Closed Hat") is row_b
        assert live_kit.state.assignment_for("Drums", "Open Hat") is None
        assert live_kit.state.assignment_for("Kick + Bass", "Kick") is None


# ============================================================
# QML-Level Tests (require PySide6)
# ============================================================

pytestmark = pytest.mark.skipif(
    __import__("importlib.util").util.find_spec("PySide6") is None,
    reason="PySide6 Qt Quick ist in dieser Testumgebung nicht installiert.",
)


def _click_item(app, window, item):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtTest import QTest

    point = item.mapToScene(QPointF(8, 8)).toPoint()
    QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)
    app.processEvents()


def _find_visual_item(root, object_name: str):
    """Find Repeater delegates through the Qt Quick visual-child tree."""
    to_visit = [root]
    while to_visit:
        current = to_visit.pop()
        if current.objectName() == object_name:
            return current
        to_visit.extend(current.childItems())
    return None


class TestQmlNoPendingEmptySlotAdd:
    """QML runtime tests for empty slot add without pending."""

    def test_empty_slot_no_pending_add_affordance_clickable_assigns_selected(self):
        """Empty slot without pending add: affordance clickable, assigns selected row."""
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

        # Select a browser row
        adapter.select_row(4)
        selected_row = fixture.browser_rows[4]

        app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
        window.show()
        _settle_qml_frame(app)

        try:
            bridge = engine._screen1_interaction_bridge
            pane = window.findChild(__import__("PySide6.QtQuick").QtQuick.QQuickItem, "liveKitPane")
            assert pane is not None

            # Find the slot add button for Drums/Main Drum (group 1, slot 0)
            slot_add = _find_visual_item(pane, "liveKitSlot1_0")
            assert slot_add is not None

            # The add button should be visible/interactive even without pending
            # Click the add affordance
            bridge.addLiveKitSlot(1, 0)
            app.processEvents()

            # Selected row should be assigned
            assert live_kit.state.assignment_for("Drums", "Main Drum") is selected_row
            assert adapter.pending_live_kit_add == ""

            # Verify QML projection
            projected = window.property("screenData").property("liveKitGroups")
            assert projected[1]["slots"][0]["assigned"] is True
            assert projected[1]["slots"][0]["assignment"] == selected_row.display_name

        finally:
            window.close()
            app.processEvents()
            timer = getattr(engine, "_screen1_waveform_timer", None)
            if timer is not None:
                timer.stop()
            loader = getattr(engine, "_screen1_waveform_loader", None)
            if loader is not None:
                loader.close()


class TestQmlAssignedSlotAuditionPrimary:
    """QML runtime tests for assigned slot primary audition."""

    def test_assigned_slot_primary_click_auditions_not_assigns(self):
        """Assigned slot primary click should audition, not assign."""
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
        assigned_row = _row("assigned_for_audition.wav")
        _assign(adapter, live_kit, "Drums", "Main Drum", assigned_row)
        view_model.live_kit_groups = live_kit.groups

        # Select different browser row
        adapter.select_row(2)
        browser_row = fixture.browser_rows[2]

        app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
        window.show()
        _settle_qml_frame(app)

        try:
            bridge = engine._screen1_interaction_bridge

            # Click the slot primary area (audition)
            bridge.auditionLiveKitSlot(1, 0)
            app.processEvents()

            # Should audition the assigned row
            projected = window.property("screenData").property("liveKitGroups")
            assert projected[1]["slots"][0]["auditioning"] is True
            assert adapter.auditioning_live_kit_slot == ("Drums", "Main Drum")

            # Assignment unchanged
            assert live_kit.state.assignment_for("Drums", "Main Drum") is assigned_row

        finally:
            window.close()
            app.processEvents()
            timer = getattr(engine, "_screen1_waveform_timer", None)
            if timer is not None:
                timer.stop()
            loader = getattr(engine, "_screen1_waveform_loader", None)
            if loader is not None:
                loader.close()


class TestQmlAssignedSlotReplace:
    """QML runtime tests for assigned slot replace affordance."""

    def test_assigned_slot_replace_affordance_uses_selected_row(self):
        """Replace affordance on assigned slot should use selected browser row."""
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
        original_row = _row("original_for_replace.wav")
        _assign(adapter, live_kit, "Drums", "Main Drum", original_row)

        # Select different browser row for replacement
        adapter.select_row(3)
        replacement_row = fixture.browser_rows[3]
        view_model.live_kit_groups = live_kit.groups

        app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
        window.show()
        _settle_qml_frame(app)

        try:
            bridge = engine._screen1_interaction_bridge

            # Click the replace affordance (addLiveKitSlot on assigned slot)
            bridge.addLiveKitSlot(1, 0)
            app.processEvents()

            # Should replace with selected browser row
            assert live_kit.state.assignment_for("Drums", "Main Drum") is replacement_row
            assert live_kit.state.assignment_for("Drums", "Main Drum") is not original_row

            # Verify QML projection
            projected = window.property("screenData").property("liveKitGroups")
            assert projected[1]["slots"][0]["assigned"] is True
            assert projected[1]["slots"][0]["assignment"] == replacement_row.display_name

        finally:
            window.close()
            app.processEvents()
            timer = getattr(engine, "_screen1_waveform_timer", None)
            if timer is not None:
                timer.stop()
            loader = getattr(engine, "_screen1_waveform_loader", None)
            if loader is not None:
                loader.close()


class TestQmlPointerOwnership:
    """QML pointer ownership tests - verify action target and audition surface are separate."""

    def test_action_target_and_audition_surface_are_separate_pointer_owners(self):
        """Verify that the add/replace affordance and audition area are separate Qt Quick pointer owners."""
        from src.workbench_qml_spike import _qml_engine, _settle_qml_frame
        from PySide6.QtQuick import QQuickItem

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
        assigned_row = _row("pointer_test.wav")
        _assign(adapter, live_kit, "Drums", "Main Drum", assigned_row)
        view_model.live_kit_groups = live_kit.groups

        app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
        window.show()
        _settle_qml_frame(app)

        try:
            pane = window.findChild(QQuickItem, "liveKitPane")
            assert pane is not None

            # Find the slot delegate
            slot_item = _find_visual_item(pane, "liveKitSlot1_0")
            assert slot_item is not None

            # Find the audition mouse area (full slot)
            audition_mouse = _find_visual_item(slot_item, "slotAuditionMouse")
            assert audition_mouse is not None

            # Find the action button mouse area (small affordance) - new ID
            action_mouse = _find_visual_item(slot_item, "slotActionMouse1_0")
            assert action_mouse is not None

            # They should be separate QQuickItems with separate pointer ownership
            assert audition_mouse is not action_mouse

            # The audition mouse area should cover the full slot
            # The action mouse area should only cover the small button area
            # (Layout.preferredWidth: 22, Layout.preferredHeight: 22)

        finally:
            window.close()
            app.processEvents()
            timer = getattr(engine, "_screen1_waveform_timer", None)
            if timer is not None:
                timer.stop()
            loader = getattr(engine, "_screen1_waveform_loader", None)
            if loader is not None:
                loader.close()


class TestQmlPendingAddRegression:
    """QML runtime tests to verify pending add flows from #611 still work."""

    def test_pending_add_empty_slot_works(self):
        """Pending add to empty slot should work as before."""
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

            # Add to kit (creates pending)
            bridge.addToKit(0)
            app.processEvents()

            # Pending banner visible
            banner = window.findChild(__import__("PySide6.QtQuick").QtQuick.QQuickItem, "liveKitPendingBanner")
            assert banner is not None
            assert banner.property("visible") is True

            # Click add affordance on empty slot
            bridge.addLiveKitSlot(1, 0)
            app.processEvents()

            # Pending row assigned
            assert live_kit.state.assignment_for("Drums", "Main Drum") is fixture.browser_rows[0]
            assert adapter.pending_live_kit_add == ""
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

    def test_pending_add_assigned_slot_replaces(self):
        """Pending add to assigned slot should replace as before."""
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
        original_row = _row("original_pending.wav")
        _assign(adapter, live_kit, "Drums", "Main Drum", original_row)
        view_model.live_kit_groups = live_kit.groups

        app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
        window.show()
        _settle_qml_frame(app)

        try:
            bridge = engine._screen1_interaction_bridge

            # Add to kit (creates pending)
            bridge.addToKit(1)
            app.processEvents()

            banner = window.findChild(__import__("PySide6.QtQuick").QtQuick.QQuickItem, "liveKitPendingBanner")
            assert banner.property("visible") is True

            # Click add affordance on assigned slot (should replace)
            bridge.addLiveKitSlot(1, 0)
            app.processEvents()

            # Pending row should replace
            assert live_kit.state.assignment_for("Drums", "Main Drum") is fixture.browser_rows[1]
            assert adapter.pending_live_kit_add == ""
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
