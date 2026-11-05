"""#1377 vertical growing Sample Rack — domain / session / export / projection."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.workbench_controller import WorkbenchRow
from src.workbench_live_kit import (
    LIVE_KIT_MAX_SLOTS_PER_GROUP,
    LIVE_KIT_SLOT_MAPPING,
    LiveKitPresentationState,
    LiveKitState,
    is_live_kit_extra_slot,
    live_kit_has_extra_slots,
)
from src.workbench_live_kit_export import (
    LIVE_KIT_EXPORT_SCHEMA_VERSION,
    LIVE_KIT_EXPORT_SCHEMA_VERSION_V2,
    export_live_kit,
)
from src.workbench_session_store import (
    WorkbenchSessionSnapshot,
    apply_snapshot_to_live_kit,
    load_workbench_session_snapshot,
    save_workbench_session_snapshot,
    snapshot_from_musical_state,
)


def _row(name: str = "sample.wav") -> WorkbenchRow:
    return WorkbenchRow(
        display_name=name,
        relative_path=f"synthetic/{name}",
        path=f"synthetic/{name}",
        bpm=120.0,
        key="C",
        key_conf=0.9,
        loudness=-12.0,
        brightness=2000.0,
        sample_class="one_shot",
        pred_type="Bass",
        status="ok",
        details={"duration_sec": "1.0", "source": "synthetic"},
    )


def _transport() -> SimpleNamespace:
    return SimpleNamespace(
        get_resume_master_bpm=lambda: 120.0,
        is_sync_enabled=lambda: False,
        get_snapshot=lambda: {"current_tempo": 120.0, "next_tempo_bpm": None},
    )


def test_canonical_seed_unchanged_and_append_creates_extra_slot() -> None:
    state = LiveKitState()
    for group, slots in LIVE_KIT_SLOT_MAPPING:
        assert state.slots_for(group) == slots

    created = state.append_empty_slot("Kick + Bass")
    assert created == "Extra 1"
    assert is_live_kit_extra_slot(created)
    assert state.slots_for("Kick + Bass") == ("Kick", "Bass", "Extra 1")
    assert state.assignment_for("Kick + Bass", "Extra 1") is None
    assert live_kit_has_extra_slots(state) is True


def test_append_does_not_mutate_existing_assignments() -> None:
    state = LiveKitState()
    row = _row("bass.wav")
    state.assign("Kick + Bass", "Bass", row)
    state.append_empty_slot("Kick + Bass")
    assert state.assignment_for("Kick + Bass", "Bass") is row
    assert state.assignment_for("Kick + Bass", "Kick") is None


def test_append_notifies_persistence_observer_once() -> None:
    calls: list[int] = []
    state = LiveKitState(on_assignment_changed=lambda: calls.append(1))
    state.append_empty_slot("Drums")
    assert calls == [1]


def test_append_is_bounded_per_group() -> None:
    state = LiveKitState()
    # Canonical Drums already has 5 slots.
    remaining = LIVE_KIT_MAX_SLOTS_PER_GROUP - len(state.slots_for("Drums"))
    for _ in range(remaining):
        state.append_empty_slot("Drums")
    with pytest.raises(ValueError, match="Maximum"):
        state.append_empty_slot("Drums")


def test_presentation_defaults_all_groups_expanded_for_vertical_rack() -> None:
    state = LiveKitState()
    presentation = LiveKitPresentationState(state)
    assert all(not presentation.is_collapsed(group) for group in state.groups())


def test_session_roundtrip_preserves_extra_slots_and_assignments(
    tmp_path: Path,
) -> None:
    state = LiveKitState()
    state.assign("Kick + Bass", "Bass", _row("kept.wav"))
    extra = state.append_empty_slot("Kick + Bass")
    state.assign("Kick + Bass", extra, _row("extra.wav"))

    snapshot = snapshot_from_musical_state(state, None, _transport())
    assert "Extra 1" in snapshot.live_kit["Kick + Bass"]
    save_workbench_session_snapshot(snapshot, state_dir=tmp_path)

    restored_snap = load_workbench_session_snapshot(state_dir=tmp_path)
    assert restored_snap is not None
    restored = LiveKitState()
    apply_snapshot_to_live_kit(restored_snap, restored)
    assert restored.slots_for("Kick + Bass") == ("Kick", "Bass", "Extra 1")
    assert restored.assignment_for("Kick + Bass", "Bass") is not None
    assert restored.assignment_for("Kick + Bass", "Extra 1") is not None
    assert restored.assignment_for("Kick + Bass", "Bass").path.endswith("kept.wav")
    assert restored.assignment_for("Kick + Bass", "Extra 1").path.endswith("extra.wav")


def test_legacy_canonical_only_session_still_restores(tmp_path: Path) -> None:
    """Pre-#1377 sessions with only the 11-slot map must not lose assignments."""
    payload = {
        "schema_version": 2,
        "master_bpm": 128.0,
        "sync_enabled": False,
        "live_kit": {
            group: {
                slot: ({"path": f"C:/synth/{group}_{slot}.wav"} if slot == "Bass" else None)
                for slot in slots
            }
            for group, slots in LIVE_KIT_SLOT_MAPPING
        },
        "channel_rack": None,
    }
    # Only Kick+Bass/Bass filled — write raw JSON as older serializer would.
    path = tmp_path / "workbench_session.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    snap = load_workbench_session_snapshot(state_dir=tmp_path)
    assert snap is not None
    state = LiveKitState()
    apply_snapshot_to_live_kit(snap, state)
    assert state.slots_for("Kick + Bass") == ("Kick", "Bass")
    assert state.assignment_for("Kick + Bass", "Bass") is not None
    assert live_kit_has_extra_slots(state) is False


def test_export_canonical_kit_remains_schema_v1(tmp_path: Path) -> None:
    media = tmp_path / "src"
    media.mkdir()
    wav = media / "kick.wav"
    wav.write_bytes(b"RIFF....WAVEfmt ")
    state = LiveKitState()
    state.assign(
        "Kick + Bass",
        "Kick",
        WorkbenchRow(
            display_name="kick.wav",
            relative_path="kick.wav",
            path=str(wav),
            bpm=120.0,
            key="C",
            key_conf=0.9,
            loudness=-12.0,
            brightness=2000.0,
            sample_class="one_shot",
            pred_type="Kick",
            status="ok",
            details={},
        ),
    )
    dest = tmp_path / "out"
    dest.mkdir()
    result = export_live_kit(state, dest)
    assert result.ok
    manifest = json.loads(
        (result.export_path / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["schema_version"] == LIVE_KIT_EXPORT_SCHEMA_VERSION
    assert LIVE_KIT_EXPORT_SCHEMA_VERSION == 1


def test_export_with_extra_slot_uses_schema_v2(tmp_path: Path) -> None:
    media = tmp_path / "src"
    media.mkdir()
    wav = media / "pad.wav"
    wav.write_bytes(b"RIFF....WAVEfmt ")
    state = LiveKitState()
    extra = state.append_empty_slot("Melodic")
    state.assign(
        "Melodic",
        extra,
        WorkbenchRow(
            display_name="pad.wav",
            relative_path="pad.wav",
            path=str(wav),
            bpm=None,
            key="Amin",
            key_conf=0.8,
            loudness=-14.0,
            brightness=1800.0,
            sample_class="loop",
            pred_type="Pad",
            status="ok",
            details={},
        ),
    )
    dest = tmp_path / "out"
    dest.mkdir()
    result = export_live_kit(state, dest)
    assert result.ok
    manifest = json.loads(
        (result.export_path / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["schema_version"] == LIVE_KIT_EXPORT_SCHEMA_VERSION_V2
    melodic = next(g for g in manifest["groups"] if g["name"] == "Melodic")
    slot_names = [s["slot"] for s in melodic["slots"]]
    assert "Extra 1" in slot_names
    assert "Lead" in slot_names and "Pad" in slot_names
    extra_entry = next(s for s in melodic["slots"] if s["slot"] == "Extra 1")
    assert extra_entry["assigned"] is True
    assert extra_entry["audio_path"] is not None
    assert (result.export_path / Path(extra_entry["audio_path"])).is_file()


def test_track_package_shape_accepts_extra_slots() -> None:
    from src.track_package import _validate_live_kit_shape

    payload = {
        group: {slot: None for slot in slots}
        for group, slots in LIVE_KIT_SLOT_MAPPING
    }
    payload["Kick + Bass"]["Extra 1"] = {"path": "media/bass_extra.wav"}
    assert _validate_live_kit_shape(payload) is None
    payload["Kick + Bass"]["Bogus"] = None
    assert _validate_live_kit_shape(payload) is not None


def test_internal_dnd_lists_and_accepts_extra_slot_targets(tmp_path: Path) -> None:
    from src import workbench_internal_sample_dnd as sample_dnd
    from src.workbench_feature_settings import WorkbenchFeatureSettings

    wav = tmp_path / "drop.wav"
    wav.write_bytes(b"RIFF....WAVEfmt ")
    row = WorkbenchRow(
        display_name="drop.wav",
        relative_path="synthetic/drop.wav",
        path=str(wav),
        bpm=120.0,
        key="C",
        key_conf=0.9,
        loudness=-12.0,
        brightness=2000.0,
        sample_class="one_shot",
        pred_type="Bass",
        status="ok",
        details={},
    )
    state = LiveKitState()
    extra = state.append_empty_slot("Kick + Bass")
    features = WorkbenchFeatureSettings(
        gesture_rack_apply_enabled=False,
        workspace_panel_docking_enabled=False,
        internal_sample_dnd_enabled=True,
    )
    keys = (("Kick + Bass", "Kick"), ("Kick + Bass", extra))
    targets = sample_dnd.list_visible_live_kit_targets(
        features=features,
        live_kit_materialized=True,
        visible_slot_keys=keys,
    )
    assert any(t.slot == extra for t in targets)

    descriptor = sample_dnd.descriptor_from_row(
        row, source_surface="browser", features=features
    )
    assert descriptor is not None
    intent = sample_dnd.InternalSampleDropIntent(
        descriptor=descriptor,
        target=sample_dnd.LiveKitAssignmentTarget(
            group="Kick + Bass",
            slot=extra,
            visible=True,
        ),
        delivery_id="delivery-extra-1",
    )
    result = sample_dnd.apply_internal_sample_drop(
        intent,
        kit=state,
        catalog=[row],
        features=features,
        live_kit_materialized=True,
        visible_slot_keys=keys,
        session=sample_dnd.InternalSampleDropSession(),
    )
    assert result.reason != "invalid_target"
    assert result.accepted is True
    assert state.assignment_for("Kick + Bass", extra) is not None


def test_qml_source_has_vertical_rack_plus_without_collapse_arrows() -> None:
    qml = Path("src/workbench_qml.py").read_text(encoding="utf-8")
    assert "appendEmptyLiveKitSlot" in qml
    assert "liveKitGroupPlus" in qml
    assert "liveKitVerticalRack" in qml
    rack_end = qml.find("channelRackScreen")
    rack_chunk = qml[qml.index('objectName: "liveKitVerticalRack"') : rack_end]
    assert "▸" not in rack_chunk
    assert "▾" not in rack_chunk
    assert "appendEmptyLiveKitSlot" in rack_chunk
    assert "toggleLiveKitGroup" not in rack_chunk


def test_qml_live_kit_hud_scroll_keeps_rack_reachable() -> None:
    """Owner visual: Atmos/FX and group + must stay reachable via HUD scroll."""
    qml = Path("src/workbench_qml.py").read_text(encoding="utf-8")
    pane = qml[qml.index('objectName: "liveKitPane"') : qml.index("channelRackScreen")]
    assert 'objectName: "liveKitDrawerScroll"' in pane
    assert 'objectName: "liveKitDrawerScrollBar"' in pane
    assert "ScrollBar.AlwaysOn" in pane
    # Sticky chrome (header) must precede the scroll viewport.
    assert pane.index("LIVE KIT") < pane.index('objectName: "liveKitDrawerScroll"')
    assert pane.index('objectName: "liveKitDrawerScroll"') < pane.index(
        'objectName: "liveKitVerticalRack"'
    )
    # Append control stays fully opaque / larger hit target.
    assert "rackPlusHeight: 28" in qml
    plus = pane[pane.index("id: liveKitGroupPlus") :]
    assert "width: 26" in plus
    assert "opacity: 1.0" in plus
