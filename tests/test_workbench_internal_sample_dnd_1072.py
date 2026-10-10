"""#1072 Internal Sample DnD contract — TEST_GATE (frozen after RED).

Python-owned Edit/Kit internal Sample drag: descriptor, resolution, visible
Live-Kit targets, Add/Replace routing, feature gate, replay guard, payload
isolation from #1070 docking and #768 file DnD. No QML in this slice.
"""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pytest

from src.live_kits_registry import assign_sample_to_kit
from src.workbench_controller import WorkbenchRow
from src.workbench_edit_docking import PanelMoveIntent
from src.workbench_feature_settings import (
    WorkbenchFeatureSettings,
    load_workbench_feature_settings,
    replace_workbench_feature_settings,
    save_workbench_feature_settings,
)
from src.workbench_live_kit import LiveKitState
from src import workbench_internal_sample_dnd as sample_dnd


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DOC = REPO_ROOT / "docs" / "WORKBENCH_INTERNAL_SAMPLE_DND_CONTRACT.md"


def _row(
    relative_path: str = "packs/kick.wav",
    *,
    display_name: str | None = None,
    absolute_path: str | None = None,
) -> WorkbenchRow:
    name = display_name or Path(relative_path).name
    path = absolute_path or f"/private/library/{relative_path}"
    return WorkbenchRow(
        display_name=name,
        relative_path=relative_path,
        path=path,
        bpm=120.0,
        key="Am",
        key_conf=0.9,
        loudness=-12.0,
        brightness=3000.0,
        sample_class="one_shot",
        pred_type="kick",
        status="ok",
    )


def _features(*, enabled: bool = True) -> WorkbenchFeatureSettings:
    return WorkbenchFeatureSettings(
        gesture_rack_apply_enabled=False,
        workspace_panel_docking_enabled=False,
        internal_sample_dnd_enabled=enabled,
    )


def _kit_snapshot(kit: LiveKitState) -> dict[str, dict[str, str | None]]:
    return {
        group: {
            slot: (
                None
                if kit.assignment_for(group, slot) is None
                else kit.assignment_for(group, slot).relative_path
            )
            for slot in kit.slots_for(group)
        }
        for group in kit.groups()
    }


def _apply(
    *,
    kit: LiveKitState,
    row: WorkbenchRow,
    source_surface: str = "browser",
    group: str = "Kick + Bass",
    slot: str = "Kick",
    visible: bool = True,
    live_kit_materialized: bool = True,
    features: WorkbenchFeatureSettings | None = None,
    catalog: tuple[WorkbenchRow, ...] | None = None,
    delivery_id: str = "delivery-1",
    session: sample_dnd.InternalSampleDropSession | None = None,
    target_kind: str = sample_dnd.TARGET_LIVE_KIT_ASSIGNMENT,
):
    features = features if features is not None else _features(enabled=True)
    descriptor = sample_dnd.descriptor_from_row(
        row,
        source_surface=source_surface,
        features=features,
    )
    assert descriptor is not None
    intent = sample_dnd.InternalSampleDropIntent(
        descriptor=descriptor,
        target=sample_dnd.LiveKitAssignmentTarget(
            group=group,
            slot=slot,
            visible=visible,
            kind=target_kind,
        ),
        delivery_id=delivery_id,
    )
    return sample_dnd.apply_internal_sample_drop(
        intent,
        kit=kit,
        catalog=catalog if catalog is not None else (row,),
        features=features,
        live_kit_materialized=live_kit_materialized,
        session=session,
    )


# ---------------------------------------------------------------------------
# Contract surface
# ---------------------------------------------------------------------------


def test_contract_doc_freezes_edit_only_boundary():
    text = CONTRACT_DOC.read_text(encoding="utf-8")
    assert "internal_sample_dnd_enabled" in text
    assert "live_kit_assignment" in text or "Live Kit" in text
    assert "No QML" in text or "does **not** implement QML" in text
    assert "#1073" in text
    assert "#768" in text
    assert "#1070" in text
    assert "relative_path" in text


def test_feature_settings_exposes_internal_sample_dnd_flag_default_off():
    settings = WorkbenchFeatureSettings()
    assert settings.internal_sample_dnd_enabled is False
    names = {f.name for f in fields(WorkbenchFeatureSettings)}
    assert "internal_sample_dnd_enabled" in names


def test_legacy_feature_json_defaults_sample_dnd_off_without_resetting_siblings(
    tmp_path: Path,
):
    path = tmp_path / "workbench_feature_settings.json"
    path.write_text(
        '{"schema_version": 1, "gesture_rack_apply_enabled": true,'
        ' "workspace_panel_docking_enabled": true}\n',
        encoding="utf-8",
    )
    loaded = load_workbench_feature_settings(state_dir=tmp_path)
    assert loaded.gesture_rack_apply_enabled is True
    assert loaded.workspace_panel_docking_enabled is True
    assert loaded.internal_sample_dnd_enabled is False


# ---------------------------------------------------------------------------
# 1–3) Browser / Harmony Add + Replace
# ---------------------------------------------------------------------------


def test_browser_sample_to_empty_visible_live_kit_slot_assigns_once():
    kit = LiveKitState()
    row = _row("packs/kick.wav")
    before = _kit_snapshot(kit)
    result = _apply(kit=kit, row=row, source_surface="browser")
    assert result.accepted is True
    assert result.mutation == "assign"
    assert kit.assignment_for("Kick + Bass", "Kick") is row
    assert before["Kick + Bass"]["Kick"] is None
    assert sum(
        1
        for group in before
        for slot, value in before[group].items()
        if value is not None
    ) == 0
    assert (
        sum(
            1
            for group in kit.groups()
            for slot in kit.slots_for(group)
            if kit.assignment_for(group, slot) is not None
        )
        == 1
    )


def test_harmony_sample_to_empty_visible_live_kit_slot_same_semantics():
    kit = LiveKitState()
    row = _row("packs/pad.wav")
    result = _apply(
        kit=kit,
        row=row,
        source_surface="harmony",
        group="Melodic",
        slot="Pad",
    )
    assert result.accepted is True
    assert result.mutation == "assign"
    assert kit.assignment_for("Melodic", "Pad") is row


def test_browser_and_harmony_replace_occupied_slot_once():
    kit = LiveKitState()
    old = _row("packs/old_kick.wav")
    new = _row("packs/new_kick.wav")
    kit.assign("Kick + Bass", "Kick", old)
    result = _apply(kit=kit, row=new, source_surface="browser")
    assert result.accepted is True
    assert result.mutation == "replace"
    assert kit.assignment_for("Kick + Bass", "Kick") is new

    harmony_row = _row("packs/harmony_kick.wav")
    result2 = _apply(
        kit=kit,
        row=harmony_row,
        source_surface="harmony",
        delivery_id="delivery-2",
    )
    assert result2.accepted is True
    assert result2.mutation == "replace"
    assert kit.assignment_for("Kick + Bass", "Kick") is harmony_row


# ---------------------------------------------------------------------------
# 4) Stale / deleted source
# ---------------------------------------------------------------------------


def test_stale_or_deleted_source_rejects_with_null_mutation():
    kit = LiveKitState()
    row = _row("packs/gone.wav")
    before = _kit_snapshot(kit)
    result = _apply(kit=kit, row=row, catalog=())
    assert result.accepted is False
    assert result.mutation is None
    assert result.reason == "unresolvable_sample"
    assert _kit_snapshot(kit) == before
    assert result.evidence is not None
    # Absolute path must never appear in user-visible evidence.
    assert "/private/" not in result.evidence
    assert row.path not in result.evidence


# ---------------------------------------------------------------------------
# 5–9) Target rejection matrix
# ---------------------------------------------------------------------------


def test_unknown_target_rejects():
    kit = LiveKitState()
    row = _row()
    before = _kit_snapshot(kit)
    result = _apply(
        kit=kit,
        row=row,
        target_kind="unknown_surface",
        group="Kick + Bass",
        slot="Kick",
    )
    assert result.accepted is False
    assert result.mutation is None
    assert result.reason == "invalid_target"
    assert _kit_snapshot(kit) == before


def test_hidden_live_kit_target_rejects():
    kit = LiveKitState()
    row = _row()
    before = _kit_snapshot(kit)
    result = _apply(kit=kit, row=row, visible=False)
    assert result.accepted is False
    assert result.reason == "hidden_target"
    assert _kit_snapshot(kit) == before


def test_non_materialized_live_kit_rejects_as_hidden():
    kit = LiveKitState()
    row = _row()
    before = _kit_snapshot(kit)
    result = _apply(kit=kit, row=row, live_kit_materialized=False)
    assert result.accepted is False
    assert result.reason == "hidden_target"
    assert _kit_snapshot(kit) == before


@pytest.mark.parametrize(
    "target_kind",
    [
        "channel_rack",
        "rack",
        "step_sequencer",
    ],
)
def test_hidden_rack_or_sequencer_target_rejects(target_kind: str):
    kit = LiveKitState()
    row = _row()
    before = _kit_snapshot(kit)
    result = _apply(kit=kit, row=row, target_kind=target_kind)
    assert result.accepted is False
    assert result.reason == "invalid_target"
    assert _kit_snapshot(kit) == before


def test_arrangement_target_rejects():
    kit = LiveKitState()
    row = _row()
    before = _kit_snapshot(kit)
    result = _apply(kit=kit, row=row, target_kind="arrangement")
    assert result.accepted is False
    assert result.reason == "invalid_target"
    assert _kit_snapshot(kit) == before


def test_later_live_target_rejects():
    kit = LiveKitState()
    row = _row()
    before = _kit_snapshot(kit)
    result = _apply(kit=kit, row=row, target_kind="live")
    assert result.accepted is False
    assert result.reason == "invalid_target"
    assert _kit_snapshot(kit) == before


# ---------------------------------------------------------------------------
# 10) Duplicate / replay
# ---------------------------------------------------------------------------


def test_duplicate_delivery_does_not_double_assign():
    kit = LiveKitState()
    row = _row("packs/kick.wav")
    session = sample_dnd.InternalSampleDropSession()
    first = _apply(kit=kit, row=row, delivery_id="same-drop", session=session)
    assert first.accepted is True
    assert first.mutation == "assign"
    assigned = kit.assignment_for("Kick + Bass", "Kick")
    second = _apply(kit=kit, row=row, delivery_id="same-drop", session=session)
    assert second.accepted is True
    assert second.mutation is None
    assert second.reason == "duplicate_delivery"
    assert kit.assignment_for("Kick + Bass", "Kick") is assigned


# ---------------------------------------------------------------------------
# 11–13) Payload isolation
# ---------------------------------------------------------------------------


def test_panel_docking_payload_cannot_parse_as_sample_dnd():
    payload = {
        "kind": "panel_move",
        "panel_id": "browser",
        "target_slot_id": "edit_slot_1",
    }
    assert sample_dnd.parse_internal_sample_descriptor(payload) is None
    assert sample_dnd.parse_internal_sample_drop_intent(payload) is None
    move = PanelMoveIntent(panel_id="browser", target_slot_id="edit_slot_1")
    assert sample_dnd.parse_internal_sample_descriptor(move) is None


def test_sample_dnd_cannot_parse_as_panel_docking_payload():
    row = _row()
    descriptor = sample_dnd.descriptor_from_row(
        row, source_surface="browser", features=_features(enabled=True)
    )
    assert descriptor is not None
    # Docking module only accepts its typed intent kinds for mutations;
    # a sample descriptor must not look like a panel_move payload.
    as_dict = {
        "kind": descriptor.kind,
        "relative_path": descriptor.relative_path,
        "source_surface": descriptor.source_surface,
    }
    assert as_dict["kind"] != "panel_move"
    assert as_dict["kind"] == sample_dnd.KIND_INTERNAL_SAMPLE
    from src.workbench_edit_docking import INTENT_PANEL_MOVE

    assert as_dict["kind"] != INTENT_PANEL_MOVE


def test_external_file_dnd_payload_remains_separate():
    file_payload = {
        "kind": "external_file_drop",
        "paths": [r"C:\Users\private\kick.wav"],
    }
    assert sample_dnd.parse_internal_sample_descriptor(file_payload) is None
    assert sample_dnd.parse_internal_sample_drop_intent(file_payload) is None
    # #768 seam still imports without treating sample descriptor as file drop.
    from src.workbench_sample_dnd import can_accept_sample_drop

    assert callable(can_accept_sample_drop)
    sample_payload = {
        "kind": sample_dnd.KIND_INTERNAL_SAMPLE,
        "relative_path": "packs/kick.wav",
        "source_surface": "browser",
    }
    assert sample_dnd.parse_internal_sample_descriptor(sample_payload) is not None


# ---------------------------------------------------------------------------
# 14–15) Feature OFF
# ---------------------------------------------------------------------------


def test_feature_off_makes_internal_sample_dnd_inert():
    kit = LiveKitState()
    row = _row()
    features = _features(enabled=False)
    assert (
        sample_dnd.descriptor_from_row(
            row, source_surface="browser", features=features
        )
        is None
    )
    assert sample_dnd.list_visible_live_kit_targets(
        features=features,
        live_kit_materialized=True,
        visible_slot_keys=(("Kick + Bass", "Kick"),),
    ) == ()
    # Even a hand-built intent is rejected when the feature is OFF.
    intent = sample_dnd.InternalSampleDropIntent(
        descriptor=sample_dnd.InternalSampleDescriptor(
            relative_path=row.relative_path,
            source_surface="browser",
        ),
        target=sample_dnd.LiveKitAssignmentTarget(
            group="Kick + Bass",
            slot="Kick",
            visible=True,
        ),
        delivery_id="off-1",
    )
    before = _kit_snapshot(kit)
    result = sample_dnd.apply_internal_sample_drop(
        intent,
        kit=kit,
        catalog=(row,),
        features=features,
        live_kit_materialized=True,
    )
    assert result.accepted is False
    assert result.reason == "feature_disabled"
    assert result.mutation is None
    assert _kit_snapshot(kit) == before


def test_feature_off_non_drag_add_replace_still_works():
    kit = LiveKitState()
    row = _row("packs/direct.wav")
    features = _features(enabled=False)
    assert features.internal_sample_dnd_enabled is False
    assign_sample_to_kit(kit, "Kick + Bass", "Kick", row)
    assert kit.assignment_for("Kick + Bass", "Kick") is row
    replacement = _row("packs/direct2.wav")
    assign_sample_to_kit(kit, "Kick + Bass", "Kick", replacement)
    assert kit.assignment_for("Kick + Bass", "Kick") is replacement


# ---------------------------------------------------------------------------
# 16) Failed mutation preserves prior kit state
# ---------------------------------------------------------------------------


class _FailingKit(LiveKitState):
    def assign(self, group: str, slot: str, row: WorkbenchRow) -> None:
        raise RuntimeError("simulated assign failure")


def test_failed_target_mutation_preserves_prior_kit_state():
    kit = _FailingKit()
    existing = _row("packs/existing.wav")
    # Bypass failing assign by writing through parent storage shape.
    LiveKitState.assign(kit, "Kick + Bass", "Kick", existing)
    before = _kit_snapshot(kit)
    row = _row("packs/new.wav")
    result = _apply(kit=kit, row=row)
    assert result.accepted is False
    assert result.mutation is None
    assert result.reason == "mutation_failed"
    assert _kit_snapshot(kit) == before
    assert kit.assignment_for("Kick + Bass", "Kick") is existing
    assert result.evidence is not None
    assert existing.path not in result.evidence
    assert row.path not in result.evidence


# ---------------------------------------------------------------------------
# 17–19) Descriptor identity / source parity
# ---------------------------------------------------------------------------


def test_descriptor_contains_no_raw_pcm_payload():
    row = _row()
    descriptor = sample_dnd.descriptor_from_row(
        row, source_surface="browser", features=_features(enabled=True)
    )
    assert descriptor is not None
    payload = descriptor.as_transport_dict()
    banned = {"pcm", "samples", "audio_bytes", "waveform_pcm", "raw_pcm"}
    assert banned.isdisjoint(payload)
    assert "pcm" not in str(payload).casefold()


def test_stable_identity_does_not_depend_on_qml_row_index():
    row = _row("packs/same.wav")
    d0 = sample_dnd.descriptor_from_row(
        row, source_surface="browser", features=_features(enabled=True)
    )
    d1 = sample_dnd.descriptor_from_row(
        row, source_surface="browser", features=_features(enabled=True)
    )
    assert d0 is not None and d1 is not None
    assert d0.relative_path == d1.relative_path == "packs/same.wav"
    assert not hasattr(d0, "row_index")
    transport = d0.as_transport_dict()
    assert "row_index" not in transport
    assert "qml_index" not in transport


def test_browser_and_harmony_produce_same_descriptor_type():
    row = _row("packs/shared.wav")
    browser = sample_dnd.descriptor_from_row(
        row, source_surface="browser", features=_features(enabled=True)
    )
    harmony = sample_dnd.descriptor_from_row(
        row, source_surface="harmony", features=_features(enabled=True)
    )
    assert browser is not None and harmony is not None
    assert type(browser) is type(harmony)
    assert browser.kind == harmony.kind == sample_dnd.KIND_INTERNAL_SAMPLE
    assert browser.relative_path == harmony.relative_path
    assert browser.source_surface == "browser"
    assert harmony.source_surface == "harmony"


# ---------------------------------------------------------------------------
# 20) Privacy
# ---------------------------------------------------------------------------


def test_user_visible_failure_evidence_leaks_no_private_absolute_path():
    kit = LiveKitState()
    abs_path = r"D:\Users\janne\private\secret_kick.wav"
    row = _row("packs/secret.wav", absolute_path=abs_path)
    result = _apply(kit=kit, row=row, catalog=())
    assert result.accepted is False
    blob = " ".join(
        part
        for part in (result.reason, result.evidence, str(result))
        if part is not None
    )
    assert abs_path not in blob
    assert r"D:\Users" not in blob
    assert "/Users/janne" not in blob


def test_feature_flag_round_trip_preserves_siblings(tmp_path: Path):
    enabled = replace_workbench_feature_settings(
        WorkbenchFeatureSettings(
            gesture_rack_apply_enabled=True,
            workspace_panel_docking_enabled=True,
            internal_sample_dnd_enabled=False,
        ),
        internal_sample_dnd_enabled=True,
    )
    assert save_workbench_feature_settings(enabled, state_dir=tmp_path) is True
    loaded = load_workbench_feature_settings(state_dir=tmp_path)
    assert loaded.internal_sample_dnd_enabled is True
    assert loaded.gesture_rack_apply_enabled is True
    assert loaded.workspace_panel_docking_enabled is True


def test_invalid_slot_identity_rejects_without_mutation():
    kit = LiveKitState()
    row = _row()
    before = _kit_snapshot(kit)
    result = _apply(kit=kit, row=row, group="Kick + Bass", slot="NotARealSlot")
    assert result.accepted is False
    assert result.reason == "invalid_target"
    assert _kit_snapshot(kit) == before
