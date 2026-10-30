"""#1207 Kit HUD — default-hidden, transient Add feedback, manual persistent open.

TEST_GATE / TEST_FREEZE — presentation ownership only. Musical kit authority
remains Python ``LiveKitState`` / ``assign`` / ``clear_slot``. HUD open/close
must never invent QML shadow kit truth or mutate assignments.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from src.workbench_controller import WorkbenchRow
from src.workbench_live_kit import LiveKitState
from src.workbench_live_kit_edit import (
    LIVE_KIT_HUD_MODE_HIDDEN,
    LIVE_KIT_HUD_MODE_MANUAL,
    LIVE_KIT_HUD_MODE_TRANSIENT,
    LIVE_KIT_HUD_TRANSIENT_MS,
)
from src.workbench_qml import QML_SOURCE, LiveKitPresenter
from src.workbench_qml_spike import (
    Screen1QmlInteractionAdapter,
    build_qml_view_model_from_fixture,
)
from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1


PY_SIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None


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


def _adapter(
    state: LiveKitState | None = None,
    *,
    materialized: bool = True,
) -> Screen1QmlInteractionAdapter:
    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(fixture, "screen1-default-3panel")
    live_kit = LiveKitPresenter(state=state)
    adapter = Screen1QmlInteractionAdapter(view_model=view_model, live_kit=live_kit)
    view_model.live_kit_groups = live_kit.groups
    view_model.live_kit_materialized = materialized
    view_model.has_active_source = True
    return adapter


def _assign(adapter: Screen1QmlInteractionAdapter, row: WorkbenchRow, group: str, slot: str) -> bool:
    adapter._pending_live_kit_row = row
    return adapter.assign_live_kit_slot(group, slot)


# --- Default / footprint ------------------------------------------------------


def test_cold_start_kit_hud_hidden_zero_footprint():
    adapter = _adapter()
    assert adapter.live_kit_hud_mode == LIVE_KIT_HUD_MODE_HIDDEN
    assert adapter.live_kit_drawer_open is False
    assert adapter.live_kit_is_visible() is False
    assert adapter.live_kit_collapsed is True


def test_musical_kit_state_survives_hidden_hud():
    state = LiveKitState()
    kept = _row("keep.wav")
    state.assign("Drums", "Main Drum", kept)
    adapter = _adapter(state)
    assert adapter.live_kit_hud_mode == LIVE_KIT_HUD_MODE_HIDDEN
    assert state.assignment_for("Drums", "Main Drum") is kept
    assert adapter.live_kit_is_visible() is False


def test_qml_has_no_permanent_kit_pane_height_when_closed():
    pane = QML_SOURCE.split('objectName: "bottomRackPane"', 1)[1][:4500]
    assert "height: kitHudExpanded" in pane or "height: bottomExpanded" in pane
    assert "kitHudExpanded" in pane
    assert ": 0" in pane
    # Overlay must not reserve Browser bottom margin permanently.
    assert "bottomMargin: liveKitOverlayDrawer.visible ? liveKitOverlayDrawer.height : 0" not in QML_SOURCE
    # Collapsed Browser host must hide HUD (match live_kit_is_visible).
    assert "!window.interaction.browserCollapsed" in pane


def test_qml_kit_hud_is_overlay_not_1204_panel():
    pane = QML_SOURCE.split('objectName: "bottomRackPane"', 1)[1][:6000]
    assert "PanelDisclosureSeam" not in pane
    assert "kit.hud" in QML_SOURCE or "liveKitHud" in QML_SOURCE.lower() or "Kit HUD" in QML_SOURCE


# --- Successful Add → transient ----------------------------------------------


def test_successful_add_mutates_canonical_python_state_once():
    adapter = _adapter()
    row = _row("a.wav")
    calls: list[tuple[str, str]] = []
    original = adapter._live_kit.state.assign

    def _tracked(group: str, slot: str, assigned: WorkbenchRow) -> None:
        calls.append((group, slot))
        original(group, slot, assigned)

    adapter._live_kit.state.assign = _tracked  # type: ignore[method-assign]
    assert _assign(adapter, row, "Kick + Bass", "Kick") is True
    assert calls == [("Kick + Bass", "Kick")]
    assert adapter._live_kit.state.assignment_for("Kick + Bass", "Kick") is row


def test_successful_add_opens_transient_hud_not_manual():
    adapter = _adapter()
    assert _assign(adapter, _row("a.wav"), "Kick + Bass", "Kick") is True
    assert adapter.live_kit_hud_mode == LIVE_KIT_HUD_MODE_TRANSIENT
    assert adapter.live_kit_drawer_open is True
    assert adapter.live_kit_is_visible() is True
    assert adapter.live_kit_hud_generation >= 1
    # Transient must not claim restart/session reopen authority.
    assert adapter._live_kit_visibility_desired is not True


def test_add_keeps_already_visible_harmony_open_beside_hud():
    adapter = _adapter()
    assert adapter.toggle_harmonic_match() is True
    assert adapter.harmonic_match_open is True

    assert _assign(adapter, _row("harmony_add.wav"), "Kick + Bass", "Kick") is True

    assert adapter.harmonic_match_open is True
    assert adapter.live_kit_hud_mode == LIVE_KIT_HUD_MODE_TRANSIENT
    assert adapter.live_kit_is_visible() is True


def test_failed_add_does_not_show_success_hud():
    adapter = _adapter()
    # Invalid slot → fail closed; no transient presentation.
    adapter._pending_live_kit_row = _row("bad.wav")
    assert adapter.assign_live_kit_slot("Kick + Bass", "NotASlot") is False
    assert adapter.live_kit_hud_mode == LIVE_KIT_HUD_MODE_HIDDEN
    assert adapter.live_kit_drawer_open is False
    assert adapter.live_kit_last_feedback_sample == ""


def test_transient_feedback_projects_authoritative_context():
    adapter = _adapter()
    row = _row("snare_01.wav")
    assert _assign(adapter, row, "Drums", "Main Drum") is True
    assert adapter.live_kit_last_feedback_sample == "snare_01.wav"
    assert adapter.live_kit_last_feedback_group == "Drums"
    assert adapter.live_kit_last_feedback_slot == "Main Drum"
    assert adapter.live_kit_last_feedback_mutation in {"add", "replace"}
    # Fill count comes from projected groups, not invented HUD state.
    fill = sum(
        1
        for group in adapter.view_model.live_kit_groups
        for slot in group.slots
        if slot.assignment is not None
    )
    assert fill == 1


def test_transient_timeout_hides_hud_only():
    adapter = _adapter()
    row = _row("a.wav")
    assert _assign(adapter, row, "Kick + Bass", "Kick") is True
    gen = adapter.live_kit_hud_generation
    assert adapter.dismiss_live_kit_transient(gen) is True
    assert adapter.live_kit_hud_mode == LIVE_KIT_HUD_MODE_HIDDEN
    assert adapter.live_kit_drawer_open is False
    assert adapter._live_kit.state.assignment_for("Kick + Bass", "Kick") is row


def test_stale_transient_generation_cannot_close_hud():
    adapter = _adapter()
    assert _assign(adapter, _row("a.wav"), "Kick + Bass", "Kick") is True
    stale = adapter.live_kit_hud_generation
    assert _assign(adapter, _row("b.wav"), "Kick + Bass", "Bass") is True
    assert adapter.dismiss_live_kit_transient(stale) is False
    assert adapter.live_kit_hud_mode == LIVE_KIT_HUD_MODE_TRANSIENT
    assert adapter.live_kit_drawer_open is True


def test_repeated_add_refreshes_transient_without_duplicate_mutation():
    adapter = _adapter()
    first = _row("a.wav")
    second = _row("b.wav")
    assert _assign(adapter, first, "Kick + Bass", "Kick") is True
    gen1 = adapter.live_kit_hud_generation
    assert _assign(adapter, second, "Drums", "Closed Hat") is True
    gen2 = adapter.live_kit_hud_generation
    assert gen2 > gen1
    assert adapter.live_kit_last_feedback_sample == "b.wav"
    assert adapter._live_kit.state.assignment_for("Kick + Bass", "Kick") is first
    assert adapter._live_kit.state.assignment_for("Drums", "Closed Hat") is second
    # Same sample re-assign to same slot must not invent a second kit authority.
    assert _assign(adapter, second, "Drums", "Closed Hat") is True
    assert adapter._live_kit.state.assignment_for("Drums", "Closed Hat") is second


# --- Manual open ownership ----------------------------------------------------


def test_manual_open_persists_beyond_transient_timeout():
    adapter = _adapter()
    row = _row("a.wav")
    adapter._live_kit.state.assign("Kick + Bass", "Kick", row)
    adapter.view_model.live_kit_materialized = True
    assert adapter.toggle_live_kit_drawer() is True
    assert adapter.live_kit_hud_mode == LIVE_KIT_HUD_MODE_MANUAL
    gen = adapter.live_kit_hud_generation
    assert adapter.dismiss_live_kit_transient(gen) is False
    assert adapter.live_kit_hud_mode == LIVE_KIT_HUD_MODE_MANUAL
    assert adapter.live_kit_drawer_open is True


def test_manual_open_during_transient_steals_timer_ownership():
    adapter = _adapter()
    assert _assign(adapter, _row("a.wav"), "Kick + Bass", "Kick") is True
    assert adapter.live_kit_hud_mode == LIVE_KIT_HUD_MODE_TRANSIENT
    gen = adapter.live_kit_hud_generation
    # Explicit manual open while already open → ownership becomes manual.
    assert adapter.open_live_kit_manual() is True
    assert adapter.live_kit_hud_mode == LIVE_KIT_HUD_MODE_MANUAL
    assert adapter.dismiss_live_kit_transient(gen) is False
    assert adapter.live_kit_drawer_open is True


def test_explicit_close_hides_without_mutating_kit():
    adapter = _adapter()
    row = _row("a.wav")
    assert _assign(adapter, row, "Kick + Bass", "Kick") is True
    assert adapter.open_live_kit_manual() is True
    selected = adapter.selected_browser_index
    assert adapter.close_live_kit_presentation() is True
    assert adapter.live_kit_hud_mode == LIVE_KIT_HUD_MODE_HIDDEN
    assert adapter.live_kit_drawer_open is False
    assert adapter._live_kit.state.assignment_for("Kick + Bass", "Kick") is row
    assert adapter.selected_browser_index == selected


def test_subsequent_add_after_manual_close_shows_transient_again():
    adapter = _adapter()
    assert _assign(adapter, _row("a.wav"), "Kick + Bass", "Kick") is True
    assert adapter.open_live_kit_manual() is True
    assert adapter.close_live_kit_presentation() is True
    assert _assign(adapter, _row("b.wav"), "Drums", "Main Drum") is True
    assert adapter.live_kit_hud_mode == LIVE_KIT_HUD_MODE_TRANSIENT
    assert adapter.live_kit_last_feedback_sample == "b.wav"


def test_manual_open_updates_live_after_add_replace_remove():
    adapter = _adapter()
    first = _row("a.wav")
    adapter._live_kit.state.assign("Kick + Bass", "Kick", first)
    adapter.view_model.live_kit_materialized = True
    assert adapter.toggle_live_kit_drawer() is True
    assert adapter.live_kit_hud_mode == LIVE_KIT_HUD_MODE_MANUAL

    second = _row("b.wav")
    assert _assign(adapter, second, "Kick + Bass", "Bass") is True
    assert adapter.live_kit_hud_mode == LIVE_KIT_HUD_MODE_MANUAL
    assert adapter.live_kit_last_feedback_sample == "b.wav"
    assert adapter.live_kit_last_feedback_mutation == "add"

    replacement = _row("c.wav")
    assert _assign(adapter, replacement, "Kick + Bass", "Bass") is True
    assert adapter.live_kit_hud_mode == LIVE_KIT_HUD_MODE_MANUAL
    assert adapter.live_kit_last_feedback_mutation == "replace"
    assert adapter._live_kit.state.assignment_for("Kick + Bass", "Bass") is replacement

    assert adapter.remove_live_kit_slot("Kick + Bass", "Bass") is True
    assert adapter.live_kit_hud_mode == LIVE_KIT_HUD_MODE_MANUAL
    assert adapter.live_kit_last_feedback_mutation == "remove"
    assert adapter._live_kit.state.assignment_for("Kick + Bass", "Bass") is None


# --- Reopen affordance / side effects / Esc ----------------------------------


def test_reopen_affordance_reflects_canonical_fill():
    assert 'objectName: "editLiveKitRevealControl"' in QML_SOURCE
    block = QML_SOURCE.split('objectName: "editLiveKitRevealControl"', 1)[1][:1200]
    assert "liveKitAssignedCount" in block
    assert "liveKitTotalSlotCount" in block
    assert "Kit " in block or '"Kit"' in block or "Kit +" in block


def test_hud_open_close_does_not_change_browser_selection_or_audition():
    adapter = _adapter()
    adapter.select_row(1)
    adapter._preview_active = False
    assert _assign(adapter, _row("a.wav"), "Kick + Bass", "Kick") is True
    assert adapter.selected_browser_index == 1
    assert adapter.preview_active is False
    assert adapter.open_live_kit_manual() is True
    assert adapter.selected_browser_index == 1
    assert adapter.preview_active is False
    assert adapter.close_live_kit_presentation() is True
    assert adapter.selected_browser_index == 1
    assert adapter.preview_active is False


def test_no_qml_shadow_kit_authority_in_source():
    # Musical mutations must still route through Python assign/clear_slot seams.
    assert "LiveKitState" in Path("src/workbench_live_kit.py").read_text(encoding="utf-8")
    assert "assign_live_kit_slot" in QML_SOURCE or "addLiveKitSlot" in QML_SOURCE
    assert "clear_slot" in Path("src/workbench_qml.py").read_text(encoding="utf-8")
    # HUD must not invent slot assignment maps in QML.
    assert "property var kitSlots" not in QML_SOURCE
    assert "shadowKit" not in QML_SOURCE


def test_transient_hud_does_not_force_active_focus_in_qml():
    # Only the pending-add chooser may steal focus (existing Esc contract).
    pane = QML_SOURCE.split('objectName: "liveKitPane"', 1)[1].split(
        'objectName: "editLiveKitRevealControl"', 1
    )[0]
    focuses = [line for line in pane.splitlines() if "forceActiveFocus()" in line]
    assert len(focuses) == 1
    banner = pane.split('objectName: "liveKitPendingBanner"', 1)[1].split(
        "forceActiveFocus()", 1
    )[0]
    assert "onVisibleChanged" in banner


def test_escape_closes_presentation_only_when_owned():
    adapter = _adapter()
    assert _assign(adapter, _row("a.wav"), "Kick + Bass", "Kick") is True
    assert adapter.pending_live_kit_add == ""
    # Escape while transient with no pending: presentation-only dismiss.
    assert adapter.escape_live_kit_context() is True
    assert adapter.live_kit_hud_mode == LIVE_KIT_HUD_MODE_HIDDEN
    assert adapter._live_kit.state.assignment_for("Kick + Bass", "Kick") is not None
    # Browser / Harmony / workspace Esc must reach the same seam (#1207 review).
    assert "escapeLiveKitContext()" in QML_SOURCE
    browser_keys = QML_SOURCE.split("Keys.onPressed: function(event) {", 1)[1][:500]
    assert "escapeLiveKitContext()" in browser_keys or (
        "Key_Escape" in QML_SOURCE
        and QML_SOURCE.count("escapeLiveKitContext()") >= 3
    )


def test_pending_escape_still_cancels_add_without_clearing_kit():
    adapter = _adapter()
    kept = _row("keep.wav")
    adapter._live_kit.state.assign("Kick + Bass", "Kick", kept)
    adapter._pending_live_kit_row = _row("pending.wav")
    assert adapter.escape_live_kit_context() is True
    assert adapter.pending_live_kit_add == ""
    assert adapter._live_kit.state.assignment_for("Kick + Bass", "Kick") is kept


def test_transient_duration_constant_is_bounded():
    assert 5000 <= LIVE_KIT_HUD_TRANSIENT_MS <= 12000


def test_bridge_exposes_hud_presentation_properties():
    text = Path("src/workbench_qml.py").read_text(encoding="utf-8")
    assert "liveKitHudMode" in text
    assert "dismissLiveKitTransient" in text
    assert "liveKitHudGeneration" in text
    assert "liveKitLastFeedbackSample" in text
    assert str(LIVE_KIT_HUD_TRANSIENT_MS) in text or "liveKitTransientMs" in text


def test_context_hints_cover_new_kit_controls():
    assert '"kit.hud.reveal"' in QML_SOURCE or '"kit.reveal"' in QML_SOURCE
    assert '"kit.hud.hide"' in QML_SOURCE or '"kit.hide"' in QML_SOURCE
    # Wired through shared contextHintState authority (#1210).
    assert 'contextHintState.reportHover("kit.hud.reveal")' in QML_SOURCE
    assert 'contextHintState.reportHover("kit.hud.hide")' in QML_SOURCE
    reveal = QML_SOURCE.split('objectName: "editLiveKitRevealControl"', 1)[1][:3200]
    assert "contextHintState" in reveal


def test_qml_timer_cannot_close_manual_mode():
    assert "dismissLiveKitTransient" in QML_SOURCE
    assert "liveKitHudGeneration" in QML_SOURCE
    assert "liveKitHudMode" in QML_SOURCE


def test_1213_onboarding_zero_chrome_unaffected_by_kit_reveal():
    # Reveal control still requires hasActiveSource; no new permanent chrome
    # before Browser-ready (browserMaterialized gate remains #1213 authority).
    block = QML_SOURCE.split('objectName: "editLiveKitRevealControl"', 1)[1][:900]
    assert "hasActiveSource" in block
    header = QML_SOURCE[
        QML_SOURCE.index('objectName: "screen1Header"') : QML_SOURCE.index(
            'objectName: "workspaceRow"'
        )
    ]
    assert "browserMaterialized" in header or "programChromeVisible" in QML_SOURCE


def test_browser_kit_route_independent_of_export():
    # #1207 / #1220 handoff ends at HUD feedback — no export dependency.
    assert "export_live_kit" not in QML_SOURCE.split("contextAddToKit", 1)[0][-500:]
    adapter = _adapter()
    assert _assign(adapter, _row("a.wav"), "Kick + Bass", "Kick") is True
    assert adapter.live_kit_hud_mode == LIVE_KIT_HUD_MODE_TRANSIENT
    # Export status must remain untouched by HUD presentation.
    assert adapter.live_kit_export_status == ""


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 required for bridge property smoke")
def test_qml_bridge_hud_properties_readable():
    from src.workbench_qml import _qml_interaction_bridge

    adapter = _adapter()
    bridge = _qml_interaction_bridge(adapter)
    assert bridge.liveKitHudMode == LIVE_KIT_HUD_MODE_HIDDEN
    assert _assign(adapter, _row("a.wav"), "Kick + Bass", "Kick") is True
    bridge.refreshState()
    assert bridge.liveKitHudMode == LIVE_KIT_HUD_MODE_TRANSIENT
    assert bridge.liveKitLastFeedbackSample == "a.wav"
    assert bridge.liveKitHudGeneration >= 1
    assert bridge.dismissLiveKitTransient(bridge.liveKitHudGeneration) is True
    assert bridge.liveKitHudMode == LIVE_KIT_HUD_MODE_HIDDEN
