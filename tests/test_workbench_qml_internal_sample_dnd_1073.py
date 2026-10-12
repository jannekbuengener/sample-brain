"""#1073 QML internal Sample DnD integration ÔÇö TEST_GATE (frozen after RED).

Verifies that Browser and Harmonic Match rows reuse the frozen #1072 Python
contract for internal Sample drag onto visible Live Kit targets, and that QML
owns only presentation, intent, and cancel while Python owns descriptor
resolution, target eligibility, Add/Replace, and replay protection.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from src.workbench_controller import WorkbenchRow
from src.workbench_feature_settings import (
    WorkbenchFeatureSettings,
    replace_workbench_feature_settings,
    save_workbench_feature_settings,
)
from src.workbench_internal_sample_dnd import (
    KIND_INTERNAL_SAMPLE,
    TARGET_LIVE_KIT_ASSIGNMENT,
)
from src.workbench_live_kit import LiveKitState
from src.workbench_qml import (
    LiveKitPresenter,
    QML_SOURCE,
    QmlBrowserRow,
    QmlHarmonyRow,
)
from src.workbench_qml_spike import (
    Screen1QmlInteractionAdapter,
    build_qml_view_model_from_fixture,
)
from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1


MIME_INTERNAL_SAMPLE = "application/x-sample-brain-internal-sample"


def _row(
    tmp_path: Path,
    name: str = "kick.wav",
    relative: str = "packs/kick.wav",
    *,
    missing: bool = False,
) -> WorkbenchRow:
    abs_path = tmp_path / relative
    if not missing:
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_bytes(b"RIFFTEST")
    return WorkbenchRow(
        display_name=name,
        relative_path=relative,
        path=str(abs_path),
        bpm=132.0,
        key="Am",
        key_conf=0.9,
        loudness=-12.0,
        brightness=3000.0,
        sample_class="one_shot",
        pred_type="kick",
        status="ok",
    )


def _qml_browser_row(row: WorkbenchRow) -> QmlBrowserRow:
    return QmlBrowserRow(
        source_row=row,
        display_name=row.display_name,
        sample_type=row.pred_type or "",
        bpm=str(row.bpm or ""),
        key=row.key or "",
        duration="0:00",
        waveform_envelope=(),
        is_favorite=False,
    )


def _qml_harmony_row(row: WorkbenchRow) -> QmlHarmonyRow:
    return QmlHarmonyRow(
        source_row=row,
        display_name=row.display_name,
        sample_type=row.pred_type or "",
        key=row.key or "",
        waveform_envelope=(),
        fit="",
        relation="",
        explanation="",
    )


def _inject_browser_row(
    adapter: Screen1QmlInteractionAdapter,
    tmp_path: Path,
    relative: str = "packs/kick.wav",
    name: str = "kick.wav",
    *,
    missing: bool = False,
) -> WorkbenchRow:
    row = _row(tmp_path, name=name, relative=relative, missing=missing)
    existing = list(adapter.view_model.browser_rows)
    existing[0] = _qml_browser_row(row)
    adapter.view_model.browser_rows = tuple(existing)
    return row


def _adapter(
    *,
    dnd_enabled: bool = True,
    state: LiveKitState | None = None,
    materialized: bool = True,
    drawer_open: bool = True,
) -> tuple[Screen1QmlInteractionAdapter, LiveKitPresenter]:
    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(fixture, "screen1-default-3panel")
    live_kit = LiveKitPresenter(state=state)
    adapter = Screen1QmlInteractionAdapter(view_model=view_model, live_kit=live_kit)
    view_model.live_kit_groups = live_kit.groups
    view_model.live_kit_materialized = materialized
    if drawer_open:
        adapter._live_kit_drawer_open = True
        adapter.live_kit_collapsed = False
    adapter._internal_sample_dnd_enabled = dnd_enabled
    return adapter, live_kit


def test_feature_settings_default_has_internal_sample_dnd_off():
    settings = WorkbenchFeatureSettings()
    assert settings.internal_sample_dnd_enabled is False


def test_adapter_loads_internal_sample_dnd_from_feature_settings(tmp_path: Path):
    enabled = replace_workbench_feature_settings(
        WorkbenchFeatureSettings(), internal_sample_dnd_enabled=True
    )
    assert save_workbench_feature_settings(enabled, state_dir=tmp_path) is True

    adapter, _live_kit = _adapter(dnd_enabled=False)
    loaded = adapter.load_feature_settings(state_dir=tmp_path)

    assert loaded.internal_sample_dnd_enabled is True
    assert adapter.internal_sample_drag_enabled() is True


def test_adapter_feature_off_keeps_sample_dnd_inert(tmp_path: Path):
    row = _row(tmp_path)
    adapter, _live_kit = _adapter(dnd_enabled=False)

    assert adapter.internal_sample_drag_enabled() is False
    assert adapter.build_internal_sample_descriptor(0, "browser") is None
    assert adapter.build_internal_sample_descriptor(0, "harmony") is None
    assert adapter.visible_live_kit_drop_targets() == []

    result = adapter.apply_internal_sample_drop(
        row.relative_path, "browser", "Kick + Bass", "Kick", "drop-1"
    )
    assert result["accepted"] is False
    assert result["reason"] == "feature_disabled"


def test_browser_descriptor_uses_relative_path_and_internal_sample_kind(tmp_path: Path):
    adapter, _live_kit = _adapter(dnd_enabled=True)
    injected = _inject_browser_row(adapter, tmp_path, relative="packs/kick.wav")

    descriptor = adapter.build_internal_sample_descriptor(0, "browser")

    assert descriptor is not None
    assert descriptor["kind"] == KIND_INTERNAL_SAMPLE
    assert descriptor["relative_path"] == "packs/kick.wav"
    assert descriptor["source_surface"] == "browser"
    assert "path" not in descriptor
    assert str(injected.path) not in str(descriptor)


def test_harmony_descriptor_uses_same_contract_as_browser(tmp_path: Path):
    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(fixture, "screen1-harmonic-4panel")
    live_kit = LiveKitPresenter()
    adapter = Screen1QmlInteractionAdapter(view_model=view_model, live_kit=live_kit)
    adapter._internal_sample_dnd_enabled = True

    injected_browser = _row(tmp_path, name="browser.wav", relative="packs/browser.wav")
    injected_harmony = _row(tmp_path, name="harmony.wav", relative="packs/harmony.wav")
    browser_rows = list(adapter.view_model.browser_rows)
    browser_rows[0] = _qml_browser_row(injected_browser)
    adapter.view_model.browser_rows = tuple(browser_rows)
    harmony_rows = list(adapter.view_model.harmony_rows)
    harmony_rows[0] = _qml_harmony_row(injected_harmony)
    adapter.view_model.harmony_rows = tuple(harmony_rows)

    browser = adapter.build_internal_sample_descriptor(0, "browser")
    harmony = adapter.build_internal_sample_descriptor(0, "harmony")

    assert browser is not None and harmony is not None
    assert browser["kind"] == harmony["kind"] == KIND_INTERNAL_SAMPLE
    assert browser["relative_path"] == "packs/browser.wav"
    assert harmony["relative_path"] == "packs/harmony.wav"
    assert browser["source_surface"] == "browser"
    assert harmony["source_surface"] == "harmony"


def test_descriptor_out_of_range_index_returns_none():
    adapter, _live_kit = _adapter(dnd_enabled=True)

    assert adapter.build_internal_sample_descriptor(-1, "browser") is None
    assert adapter.build_internal_sample_descriptor(9999, "browser") is None


def test_visible_targets_empty_when_live_kit_hidden():
    adapter, _live_kit = _adapter(dnd_enabled=True, drawer_open=False)
    adapter._live_kit_drawer_open = False
    adapter.live_kit_collapsed = True

    assert adapter.visible_live_kit_drop_targets() == []


def test_visible_targets_empty_when_live_kit_not_materialized():
    adapter, _live_kit = _adapter(dnd_enabled=True, materialized=False)

    assert adapter.visible_live_kit_drop_targets() == []


def test_visible_targets_only_for_expanded_groups():
    adapter, live_kit = _adapter(dnd_enabled=True)
    assert adapter.visible_live_kit_drop_targets() == []

    adapter.toggle_live_kit_group("Kick + Bass")
    targets = adapter.visible_live_kit_drop_targets()
    keys = {(t["group"], t["slot"]) for t in targets}

    assert keys == {("Kick + Bass", "Kick"), ("Kick + Bass", "Bass")}
    assert all(t["kind"] == TARGET_LIVE_KIT_ASSIGNMENT for t in targets)
    assert all(t["visible"] is True for t in targets)


def test_visible_targets_feature_off_returns_empty():
    adapter, _live_kit = _adapter(dnd_enabled=False)
    adapter.toggle_live_kit_group("Kick + Bass")

    assert adapter.visible_live_kit_drop_targets() == []


def test_drop_to_empty_visible_slot_assigns_once(tmp_path: Path):
    adapter, live_kit = _adapter(dnd_enabled=True)
    row = _inject_browser_row(adapter, tmp_path, relative="packs/kick.wav")
    adapter.toggle_live_kit_group("Kick + Bass")

    result = adapter.apply_internal_sample_drop(
        row.relative_path, "browser", "Kick + Bass", "Kick", "drop-add-1"
    )

    assert result["accepted"] is True
    assert result["mutation"] == "assign"
    assert live_kit.state.assignment_for("Kick + Bass", "Kick") is row


def test_drop_to_occupied_slot_replaces_once(tmp_path: Path):
    old = _row(tmp_path, name="old.wav", relative="packs/old.wav")
    state = LiveKitState()
    state.assign("Kick + Bass", "Kick", old)
    adapter, live_kit = _adapter(dnd_enabled=True, state=state)
    new = _inject_browser_row(adapter, tmp_path, name="new.wav", relative="packs/new.wav")
    adapter.toggle_live_kit_group("Kick + Bass")

    result = adapter.apply_internal_sample_drop(
        new.relative_path, "browser", "Kick + Bass", "Kick", "drop-replace-1"
    )

    assert result["accepted"] is True
    assert result["mutation"] == "replace"
    assert live_kit.state.assignment_for("Kick + Bass", "Kick") is new


def test_harmony_drop_uses_same_python_semantics(tmp_path: Path):
    adapter, live_kit = _adapter(dnd_enabled=True)
    row = _row(tmp_path, name="pad.wav", relative="packs/pad.wav")
    harmony_rows = list(adapter.view_model.harmony_rows)
    harmony_rows[0] = _qml_harmony_row(row)
    adapter.view_model.harmony_rows = tuple(harmony_rows)
    adapter.toggle_live_kit_group("Melodic")

    result = adapter.apply_internal_sample_drop(
        row.relative_path, "harmony", "Melodic", "Pad", "drop-harmony-1"
    )

    assert result["accepted"] is True
    assert result["mutation"] == "assign"
    assert live_kit.state.assignment_for("Melodic", "Pad") is row


def test_stale_deleted_sample_rejects_without_mutation(tmp_path: Path):
    adapter, live_kit = _adapter(dnd_enabled=True)
    row = _inject_browser_row(
        adapter, tmp_path, relative="packs/gone.wav", missing=True
    )
    adapter.toggle_live_kit_group("Kick + Bass")
    before = live_kit.state.assignment_for("Kick + Bass", "Kick")

    result = adapter.apply_internal_sample_drop(
        row.relative_path, "browser", "Kick + Bass", "Kick", "drop-stale-1"
    )

    assert result["accepted"] is False
    assert result["reason"] == "unresolvable_sample"
    assert result["mutation"] is None
    assert live_kit.state.assignment_for("Kick + Bass", "Kick") is before
    assert str(row.path) not in str(result)


def test_drop_to_collapsed_group_rejects(tmp_path: Path):
    adapter, live_kit = _adapter(dnd_enabled=True)
    row = _inject_browser_row(adapter, tmp_path, relative="packs/kick.wav")
    before = live_kit.state.assignment_for("Kick + Bass", "Kick")

    result = adapter.apply_internal_sample_drop(
        row.relative_path, "browser", "Kick + Bass", "Kick", "drop-collapsed-1"
    )

    assert result["accepted"] is False
    assert result["reason"] == "hidden_target"
    assert live_kit.state.assignment_for("Kick + Bass", "Kick") is before


def test_duplicate_delivery_does_not_double_assign(tmp_path: Path):
    adapter, live_kit = _adapter(dnd_enabled=True)
    row = _inject_browser_row(adapter, tmp_path, relative="packs/kick.wav")
    adapter.toggle_live_kit_group("Kick + Bass")

    first = adapter.apply_internal_sample_drop(
        row.relative_path, "browser", "Kick + Bass", "Kick", "duplicate-drop"
    )
    assert first["accepted"] is True
    assert first["mutation"] == "assign"

    second = adapter.apply_internal_sample_drop(
        row.relative_path, "browser", "Kick + Bass", "Kick", "duplicate-drop"
    )
    assert second["accepted"] is True
    assert second["mutation"] is None
    assert second["reason"] == "duplicate_delivery"

    assert live_kit.state.assignment_for("Kick + Bass", "Kick") is row


def test_python_mutation_failure_preserves_prior_state(tmp_path: Path):
    existing = _row(tmp_path, name="existing.wav", relative="packs/existing.wav")
    state = LiveKitState()
    state.assign("Kick + Bass", "Kick", existing)

    def _failing_assign(group, slot, row):
        raise RuntimeError("simulated assign failure")

    state.assign = _failing_assign  # type: ignore[method-assign]
    adapter, live_kit = _adapter(dnd_enabled=True, state=state)
    incoming = _inject_browser_row(
        adapter, tmp_path, name="incoming.wav", relative="packs/incoming.wav"
    )
    adapter.toggle_live_kit_group("Kick + Bass")

    result = adapter.apply_internal_sample_drop(
        incoming.relative_path, "browser", "Kick + Bass", "Kick", "drop-fail-1"
    )

    assert result["accepted"] is False
    assert result["reason"] == "mutation_failed"
    assert live_kit.state.assignment_for("Kick + Bass", "Kick") is existing


def test_qml_source_uses_internal_sample_mime_type():
    assert MIME_INTERNAL_SAMPLE in QML_SOURCE


def test_qml_source_has_internal_sample_drag_on_browser_row():
    browser_delegate = QML_SOURCE.split("id: browserRow", 1)[1].split(
        "Rectangle { anchors.left: parent.left", 1
    )[0]
    assert (
        MIME_INTERNAL_SAMPLE in browser_delegate
        or "requestInternalSampleDragDescriptor" in browser_delegate
    )


def test_qml_source_has_internal_sample_drag_on_harmony_row():
    harmony_delegate = QML_SOURCE.split("id: harmonyRow", 1)[1].split(
        "Rectangle { anchors.left: parent.left", 1
    )[0]
    assert (
        MIME_INTERNAL_SAMPLE in harmony_delegate
        or "requestInternalSampleDragDescriptor" in harmony_delegate
    )


def test_qml_source_has_drop_area_on_live_kit_slot():
    slot_block = QML_SOURCE.split('objectName: "liveKitSlot"', 1)[1].split(
        "Repeater { model: modelData.active", 1
    )[0]
    assert "DropArea" in slot_block
    assert MIME_INTERNAL_SAMPLE in slot_block


def test_qml_source_calls_apply_internal_sample_drop_on_slot():
    slot_block = QML_SOURCE.split('objectName: "liveKitSlot"', 1)[1].split(
        "Repeater { model: modelData.active", 1
    )[0]
    assert "applyInternalSampleDrop" in slot_block


def test_qml_source_no_qml_owned_kit_truth():
    forbidden = (
        "qmlOwnedKit",
        "liveKitOwnedModel",
        "assign_sample_to_kit",
        "replace_sample_assignment",
    )
    for token in forbidden:
        assert token not in QML_SOURCE, token


def test_qml_source_keeps_external_file_dnd_separate():
    browser_delegate = QML_SOURCE.split("id: browserRow", 1)[1].split(
        "Rectangle { anchors.left: parent.left", 1
    )[0]
    assert "text/uri-list" in browser_delegate
    assert MIME_INTERNAL_SAMPLE in browser_delegate


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="PySide6 Qt Quick ist in dieser Testumgebung nicht installiert.",
)
def test_qml_bridge_exposes_internal_sample_drag_enabled():
    from src.workbench_qml import _qml_interaction_bridge

    adapter, _live_kit = _adapter(dnd_enabled=True)
    bridge = _qml_interaction_bridge(adapter)

    assert bridge.property("internalSampleDragEnabled") is True


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="PySide6 Qt Quick ist in dieser Testumgebung nicht installiert.",
)
def test_qml_bridge_descriptor_request_returns_json_when_enabled(tmp_path: Path):
    from src.workbench_qml import _qml_interaction_bridge

    adapter, _live_kit = _adapter(dnd_enabled=True)
    _inject_browser_row(adapter, tmp_path, relative="packs/kick.wav")
    bridge = _qml_interaction_bridge(adapter)

    raw = bridge.requestInternalSampleDragDescriptor(0, "browser")
    descriptor = json.loads(raw)
    assert descriptor["kind"] == KIND_INTERNAL_SAMPLE
    assert descriptor["relative_path"] == "packs/kick.wav"
    assert descriptor["source_surface"] == "browser"


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="PySide6 Qt Quick ist in dieser Testumgebung nicht installiert.",
)
def test_qml_bridge_descriptor_request_returns_empty_when_disabled():
    from src.workbench_qml import _qml_interaction_bridge

    adapter, _live_kit = _adapter(dnd_enabled=False)
    bridge = _qml_interaction_bridge(adapter)

    assert bridge.requestInternalSampleDragDescriptor(0, "browser") == ""


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="PySide6 Qt Quick ist in dieser Testumgebung nicht installiert.",
)
def test_qml_bridge_drop_target_list_returns_visible_slots():
    from src.workbench_qml import _qml_interaction_bridge

    adapter, _live_kit = _adapter(dnd_enabled=True)
    adapter.toggle_live_kit_group("Drums")
    bridge = _qml_interaction_bridge(adapter)

    targets = bridge.requestVisibleLiveKitDropTargets()
    keys = {(t["group"], t["slot"]) for t in targets}
    assert keys == {
        ("Drums", "Main Drum"),
        ("Drums", "Closed Hat"),
        ("Drums", "Open Hat"),
        ("Drums", "Percussion"),
        ("Drums", "Additional"),
    }


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="PySide6 Qt Quick ist in dieser Testumgebung nicht installiert.",
)
def test_qml_bridge_apply_drop_returns_result_dict(tmp_path: Path):
    from src.workbench_qml import _qml_interaction_bridge

    adapter, _live_kit = _adapter(dnd_enabled=True)
    row = _inject_browser_row(adapter, tmp_path, relative="packs/kick.wav")
    adapter.toggle_live_kit_group("Kick + Bass")
    bridge = _qml_interaction_bridge(adapter)

    result = bridge.applyInternalSampleDrop(
        row.relative_path, "browser", "Kick + Bass", "Kick", "bridge-drop-1"
    )

    assert result["accepted"] is True
    assert result["mutation"] == "assign"


def test_existing_add_to_kit_pill_still_works_with_feature_off(tmp_path: Path):
    row = _row(tmp_path, relative="packs/kick.wav")
    adapter, live_kit = _adapter(dnd_enabled=False)
    adapter._pending_live_kit_row = row

    assert adapter.assign_live_kit_slot("Kick + Bass", "Kick") is True
    assert live_kit.state.assignment_for("Kick + Bass", "Kick") is row


def test_existing_add_to_kit_pill_still_works_with_feature_on(tmp_path: Path):
    row = _row(tmp_path, relative="packs/kick.wav")
    adapter, live_kit = _adapter(dnd_enabled=True)
    adapter._pending_live_kit_row = row

    assert adapter.assign_live_kit_slot("Kick + Bass", "Kick") is True
    assert live_kit.state.assignment_for("Kick + Bass", "Kick") is row
