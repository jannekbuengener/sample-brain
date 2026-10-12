"""#1073 Codex review fixes — regression gate (P1 projection, P2 delivery, P2 descriptor).

Follow-up to the frozen #1073 TEST_GATE. Adds the three review-mandated
regressions without modifying the frozen gate file:

* P1 — an accepted drop re-projects the canonical kit state immediately.
* P2 — one drag = one stable delivery id; a repeated delivery is idempotent.
* P2 — the *complete* transported descriptor is validated by Python; foreign or
  malformed payloads fail closed.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from src.workbench_controller import WorkbenchRow
from src.workbench_internal_sample_dnd import KIND_INTERNAL_SAMPLE
from src.workbench_live_kit import LiveKitState
from src.workbench_qml import QML_SOURCE, LiveKitPresenter, QmlBrowserRow, QmlHarmonyRow
from src.workbench_qml_spike import (
    Screen1QmlInteractionAdapter,
    build_qml_view_model_from_fixture,
)
from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1

DELIVERY_MIME = "application/x-sample-brain-internal-delivery"
INNER_MIME = "application/x-sample-brain-internal-sample"

QT_SKIP = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="PySide6 Qt Quick ist in dieser Testumgebung nicht installiert.",
)


def _row(
    tmp_path: Path,
    name: str = "kick.wav",
    relative: str = "packs/kick.wav",
) -> WorkbenchRow:
    abs_path = tmp_path / relative
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


def _adapter(
    *,
    dnd_enabled: bool = True,
    state: LiveKitState | None = None,
) -> tuple[Screen1QmlInteractionAdapter, LiveKitPresenter]:
    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(fixture, "screen1-default-3panel")
    live_kit = LiveKitPresenter(state=state)
    adapter = Screen1QmlInteractionAdapter(view_model=view_model, live_kit=live_kit)
    view_model.live_kit_groups = live_kit.groups
    view_model.live_kit_materialized = True
    adapter._live_kit_drawer_open = True
    adapter.live_kit_collapsed = False
    adapter._internal_sample_dnd_enabled = dnd_enabled
    return adapter, live_kit


def _inject_browser_row(
    adapter: Screen1QmlInteractionAdapter,
    tmp_path: Path,
    relative: str = "packs/kick.wav",
    name: str = "kick.wav",
) -> WorkbenchRow:
    row = _row(tmp_path, name=name, relative=relative)
    rows = list(adapter.view_model.browser_rows)
    rows[0] = QmlBrowserRow(
        source_row=row,
        display_name=row.display_name,
        sample_type=row.pred_type or "",
        bpm=str(row.bpm or ""),
        key=row.key or "",
        duration="0:00",
        waveform_envelope=(),
        is_favorite=False,
    )
    adapter.view_model.browser_rows = tuple(rows)
    return row


def _inject_harmony_row(
    adapter: Screen1QmlInteractionAdapter,
    tmp_path: Path,
    relative: str = "packs/pad.wav",
    name: str = "pad.wav",
) -> WorkbenchRow:
    row = _row(tmp_path, name=name, relative=relative)
    rows = list(adapter.view_model.harmony_rows)
    projected = QmlHarmonyRow(
        source_row=row,
        display_name=row.display_name,
        sample_type=row.pred_type or "",
        key=row.key or "",
        waveform_envelope=(),
        fit="",
        relation="",
        explanation="",
    )
    if rows:
        rows[0] = projected
        adapter.view_model.harmony_rows = tuple(rows)
    else:
        adapter.view_model.harmony_rows = (projected,)
    return row


def _projected_assignment_of(
    adapter: Screen1QmlInteractionAdapter,
    group: str,
    slot: str,
) -> WorkbenchRow | None:
    for grp in adapter.view_model.live_kit_groups:
        if grp.name != group:
            continue
        for slt in grp.slots:
            if slt.name == slot:
                return slt.assignment
    return None


def _slot_indices(
    adapter: Screen1QmlInteractionAdapter,
    group: str,
    slot: str,
) -> tuple[int, int]:
    for gi, grp in enumerate(adapter.view_model.live_kit_groups):
        if grp.name != group:
            continue
        for si, slt in enumerate(grp.slots):
            if slt.name == slot:
                return gi, si
    raise AssertionError(f"slot not found: {group}/{slot}")


# --- P1: accepted drop re-projects the canonical kit state immediately --------


def test_accepted_browser_drop_reprojects_slot_immediately(tmp_path: Path):
    adapter, live_kit = _adapter()
    row = _inject_browser_row(adapter, tmp_path, relative="packs/kick.wav")
    adapter.toggle_live_kit_group("Kick + Bass")

    assert _projected_assignment_of(adapter, "Kick + Bass", "Kick") is None

    result = adapter.apply_internal_sample_drop(
        row.relative_path, "browser", "Kick + Bass", "Kick", "reproject-1"
    )

    assert result["accepted"] is True
    assert result["mutation"] == "assign"
    assert live_kit.state.assignment_for("Kick + Bass", "Kick") is row
    # Projection is fresh without any unrelated group toggle.
    assert _projected_assignment_of(adapter, "Kick + Bass", "Kick") is row


def test_accepted_harmony_replace_reprojects_slot_immediately(tmp_path: Path):
    prior = _row(tmp_path, name="prior.wav", relative="packs/prior.wav")
    state = LiveKitState()
    state.assign("Kick + Bass", "Bass", prior)
    adapter, live_kit = _adapter(state=state)
    incoming = _inject_harmony_row(adapter, tmp_path, relative="packs/pad.wav")
    adapter.toggle_live_kit_group("Kick + Bass")

    result = adapter.apply_internal_sample_drop(
        incoming.relative_path, "harmony", "Kick + Bass", "Bass", "reproject-2"
    )

    assert result["accepted"] is True
    assert result["mutation"] == "replace"
    assert _projected_assignment_of(adapter, "Kick + Bass", "Bass") is incoming


# --- P2: one drag = one stable delivery id -----------------------------------


def test_repeated_delivery_id_is_idempotent(tmp_path: Path):
    adapter, live_kit = _adapter()
    row = _inject_browser_row(adapter, tmp_path, relative="packs/kick.wav")
    adapter.toggle_live_kit_group("Kick + Bass")

    first = adapter.apply_internal_sample_drop(
        row.relative_path, "browser", "Kick + Bass", "Kick", "drag-same-id"
    )
    second = adapter.apply_internal_sample_drop(
        row.relative_path, "browser", "Kick + Bass", "Kick", "drag-same-id"
    )

    assert first["accepted"] is True and first["mutation"] == "assign"
    assert second["accepted"] is True
    assert second["mutation"] is None
    assert second["reason"] == "duplicate_delivery"
    assert live_kit.state.assignment_for("Kick + Bass", "Kick") is row


@QT_SKIP
def test_bridge_begin_internal_sample_drag_mints_unique_ids():
    from src.workbench_qml import _qml_interaction_bridge

    adapter, _live_kit = _adapter()
    bridge = _qml_interaction_bridge(adapter)

    first = bridge.beginInternalSampleDrag()
    second = bridge.beginInternalSampleDrag()

    assert first and second
    assert first != second


@QT_SKIP
def test_bridge_drop_at_slot_replays_same_delivery_id(tmp_path: Path):
    from src.workbench_qml import _qml_interaction_bridge

    adapter, _live_kit = _adapter()
    _inject_browser_row(adapter, tmp_path, relative="packs/kick.wav")
    adapter.toggle_live_kit_group("Kick + Bass")
    bridge = _qml_interaction_bridge(adapter)
    gi, si = _slot_indices(adapter, "Kick + Bass", "Kick")

    descriptor = bridge.requestInternalSampleDragDescriptor(0, "browser")
    delivery = bridge.beginInternalSampleDrag()
    first = bridge.applyInternalSampleDropAtSlot(gi, si, descriptor, delivery)
    second = bridge.applyInternalSampleDropAtSlot(gi, si, descriptor, delivery)

    assert first["accepted"] is True and first["mutation"] == "assign"
    assert second["accepted"] is True
    assert second["mutation"] is None
    assert second["reason"] == "duplicate_delivery"


@QT_SKIP
def test_bridge_drop_at_slot_new_delivery_mutates_again(tmp_path: Path):
    from src.workbench_qml import _qml_interaction_bridge

    adapter, live_kit = _adapter()
    row_a = _inject_browser_row(adapter, tmp_path, relative="packs/kick_a.wav")
    adapter.toggle_live_kit_group("Kick + Bass")
    bridge = _qml_interaction_bridge(adapter)
    gi, si = _slot_indices(adapter, "Kick + Bass", "Kick")

    first = bridge.applyInternalSampleDropAtSlot(
        gi, si, bridge.requestInternalSampleDragDescriptor(0, "browser"),
        bridge.beginInternalSampleDrag(),
    )
    assert first["accepted"] is True and first["mutation"] == "assign"
    assert live_kit.state.assignment_for("Kick + Bass", "Kick") is row_a

    row_b = _inject_browser_row(adapter, tmp_path, relative="packs/kick_b.wav")
    second = bridge.applyInternalSampleDropAtSlot(
        gi, si, bridge.requestInternalSampleDragDescriptor(0, "browser"),
        bridge.beginInternalSampleDrag(),
    )

    assert second["accepted"] is True and second["mutation"] == "replace"
    assert live_kit.state.assignment_for("Kick + Bass", "Kick") is row_b


def test_qml_source_transports_delivery_id_and_mints_at_drag_start():
    assert DELIVERY_MIME in QML_SOURCE
    assert "beginInternalSampleDrag" in QML_SOURCE
    # The slot DropArea must accept both carried mime types.
    drop_area = QML_SOURCE.split('objectName: "internalSampleDropArea"', 1)[1].split(
        "Rectangle {", 1
    )[0]
    assert INNER_MIME in drop_area
    assert DELIVERY_MIME in drop_area


# --- P2: full descriptor validation (Python authoritative) -------------------


def test_valid_full_internal_sample_descriptor_accepted(tmp_path: Path):
    adapter, live_kit = _adapter()
    row = _inject_browser_row(adapter, tmp_path, relative="packs/kick.wav")
    adapter.toggle_live_kit_group("Kick + Bass")

    result = adapter.apply_internal_sample_drop_payload(
        {
            "kind": KIND_INTERNAL_SAMPLE,
            "relative_path": "packs/kick.wav",
            "source_surface": "browser",
        },
        "Kick + Bass",
        "Kick",
        "payload-1",
    )

    assert result["accepted"] is True and result["mutation"] == "assign"
    assert live_kit.state.assignment_for("Kick + Bass", "Kick") is row


def test_foreign_panel_move_descriptor_fails_closed(tmp_path: Path):
    adapter, live_kit = _adapter()
    _inject_browser_row(adapter, tmp_path, relative="packs/kick.wav")
    adapter.toggle_live_kit_group("Kick + Bass")

    result = adapter.apply_internal_sample_drop_payload(
        {
            "kind": "panel_move",
            "relative_path": "packs/kick.wav",
            "source_surface": "browser",
        },
        "Kick + Bass",
        "Kick",
        "payload-foreign",
    )

    assert result["accepted"] is False
    assert result["reason"] == "invalid_descriptor"
    assert result["mutation"] is None
    assert live_kit.state.assignment_for("Kick + Bass", "Kick") is None


def test_wrong_kind_descriptor_fails_closed(tmp_path: Path):
    adapter, _live_kit = _adapter()
    _inject_browser_row(adapter, tmp_path, relative="packs/kick.wav")
    adapter.toggle_live_kit_group("Kick + Bass")

    result = adapter.apply_internal_sample_drop_payload(
        {
            "kind": "not_internal_sample",
            "relative_path": "packs/kick.wav",
            "source_surface": "browser",
        },
        "Kick + Bass",
        "Kick",
        "payload-wrong-kind",
    )

    assert result["accepted"] is False
    assert result["reason"] == "invalid_descriptor"


@pytest.mark.parametrize(
    "payload",
    [
        None,
        "not-a-mapping",
        42,
        {"relative_path": "packs/kick.wav", "source_surface": "browser"},
        {"kind": KIND_INTERNAL_SAMPLE, "relative_path": "../escape.wav"},
    ],
)
def test_malformed_descriptor_fails_closed(tmp_path: Path, payload):
    adapter, live_kit = _adapter()
    _inject_browser_row(adapter, tmp_path, relative="packs/kick.wav")
    adapter.toggle_live_kit_group("Kick + Bass")

    result = adapter.apply_internal_sample_drop_payload(
        payload, "Kick + Bass", "Kick", "payload-malformed"
    )

    assert result["accepted"] is False
    assert result["reason"] == "invalid_descriptor"
    assert live_kit.state.assignment_for("Kick + Bass", "Kick") is None


@QT_SKIP
def test_bridge_drop_at_slot_rejects_foreign_payload(tmp_path: Path):
    from src.workbench_qml import _qml_interaction_bridge

    adapter, live_kit = _adapter()
    _inject_browser_row(adapter, tmp_path, relative="packs/kick.wav")
    adapter.toggle_live_kit_group("Kick + Bass")
    bridge = _qml_interaction_bridge(adapter)
    gi, si = _slot_indices(adapter, "Kick + Bass", "Kick")

    foreign = json.dumps(
        {
            "kind": "panel_move",
            "relative_path": "packs/kick.wav",
            "source_surface": "browser",
        }
    )
    result = bridge.applyInternalSampleDropAtSlot(gi, si, foreign, "foreign-1")

    assert result["accepted"] is False
    assert result["reason"] == "invalid_descriptor"
    assert live_kit.state.assignment_for("Kick + Bass", "Kick") is None


@QT_SKIP
def test_bridge_drop_at_slot_rejects_malformed_json(tmp_path: Path):
    from src.workbench_qml import _qml_interaction_bridge

    adapter, _live_kit = _adapter()
    _inject_browser_row(adapter, tmp_path, relative="packs/kick.wav")
    adapter.toggle_live_kit_group("Kick + Bass")
    bridge = _qml_interaction_bridge(adapter)
    gi, si = _slot_indices(adapter, "Kick + Bass", "Kick")

    result = bridge.applyInternalSampleDropAtSlot(gi, si, "{not json", "malformed-1")

    assert result["accepted"] is False
    assert result["reason"] == "invalid_descriptor"


def test_valid_descriptor_transport_shape_unchanged(tmp_path: Path):
    adapter, _live_kit = _adapter()
    _inject_browser_row(adapter, tmp_path, relative="packs/kick.wav")

    descriptor = adapter.build_internal_sample_descriptor(0, "browser")

    assert descriptor == {
        "kind": KIND_INTERNAL_SAMPLE,
        "relative_path": "packs/kick.wav",
        "source_surface": "browser",
    }


# --- P2 (review-2): reuse the effective Live Kit visibility predicate ---------


def test_browser_collapsed_hides_drop_targets_and_rejects(tmp_path: Path):
    adapter, live_kit = _adapter()
    row = _inject_browser_row(adapter, tmp_path, relative="packs/kick.wav")
    adapter.toggle_live_kit_group("Kick + Bass")
    assert adapter.visible_live_kit_drop_targets() != []

    adapter.browser_collapsed = True

    assert adapter.visible_live_kit_drop_targets() == []
    result = adapter.apply_internal_sample_drop(
        row.relative_path, "browser", "Kick + Bass", "Kick", "collapsed-1"
    )
    assert result["accepted"] is False
    assert result["reason"] == "hidden_target"
    assert live_kit.state.assignment_for("Kick + Bass", "Kick") is None


def test_pending_add_chooser_exposes_targets_with_drawer_closed(tmp_path: Path):
    adapter, live_kit = _adapter()
    row = _inject_browser_row(adapter, tmp_path, relative="packs/kick.wav")
    adapter.toggle_live_kit_group("Kick + Bass")
    adapter._live_kit_drawer_open = False
    adapter._pending_live_kit_row = row

    keys = {
        (t["group"], t["slot"]) for t in adapter.visible_live_kit_drop_targets()
    }
    assert ("Kick + Bass", "Kick") in keys

    result = adapter.apply_internal_sample_drop(
        row.relative_path, "browser", "Kick + Bass", "Kick", "pending-chooser-1"
    )
    assert result["accepted"] is True and result["mutation"] == "assign"
    assert live_kit.state.assignment_for("Kick + Bass", "Kick") is row


# --- P2 (review-2): clear audition when replacing the playing slot ------------


def test_replace_clears_audition_of_destination_slot(tmp_path: Path):
    prior = _row(tmp_path, name="prior.wav", relative="packs/prior.wav")
    state = LiveKitState()
    state.assign("Kick + Bass", "Kick", prior)
    adapter, _live_kit = _adapter(state=state)
    new = _inject_browser_row(
        adapter, tmp_path, name="new.wav", relative="packs/new.wav"
    )
    adapter.toggle_live_kit_group("Kick + Bass")
    adapter._auditioning_live_kit_slot = ("Kick + Bass", "Kick")
    adapter.view_model.auditioning_live_kit_slot = ("Kick + Bass", "Kick")

    result = adapter.apply_internal_sample_drop(
        new.relative_path, "browser", "Kick + Bass", "Kick", "audition-1"
    )

    assert result["accepted"] is True and result["mutation"] == "replace"
    assert adapter._auditioning_live_kit_slot is None
    assert adapter.view_model.auditioning_live_kit_slot is None


def test_replace_other_slot_keeps_unrelated_audition(tmp_path: Path):
    prior = _row(tmp_path, name="prior.wav", relative="packs/prior.wav")
    state = LiveKitState()
    state.assign("Kick + Bass", "Kick", prior)
    adapter, _live_kit = _adapter(state=state)
    new = _inject_browser_row(
        adapter, tmp_path, name="new.wav", relative="packs/new.wav"
    )
    adapter.toggle_live_kit_group("Kick + Bass")
    adapter._auditioning_live_kit_slot = ("Kick + Bass", "Bass")
    adapter.view_model.auditioning_live_kit_slot = ("Kick + Bass", "Bass")

    result = adapter.apply_internal_sample_drop(
        new.relative_path, "browser", "Kick + Bass", "Kick", "audition-2"
    )

    assert result["accepted"] is True and result["mutation"] == "replace"
    assert adapter._auditioning_live_kit_slot == ("Kick + Bass", "Bass")


# --- P1 (review-3): distinct samples sharing a relative path stay distinct ----


def test_distinct_samples_sharing_relative_path_fail_closed_ambiguous(
    tmp_path: Path,
):
    """Two distinct samples projecting to the same relative_path must not be
    collapsed into one catalog row: the authoritative resolver must fail closed
    with ``ambiguous_sample`` so no wrong sample is silently assigned.
    """
    adapter, live_kit = _adapter()
    a = _row(
        tmp_path / "root_a", name="same.wav", relative="packs/same.wav"
    )
    b = _row(tmp_path / "root_b", name="same.wav", relative="packs/same.wav")
    assert a.relative_path == b.relative_path
    assert a.path != b.path
    adapter.view_model.browser_rows = (_qml_browser_row(a), _qml_browser_row(b))
    adapter.toggle_live_kit_group("Kick + Bass")

    result = adapter.apply_internal_sample_drop(
        a.relative_path, "browser", "Kick + Bass", "Kick", "ambiguous-1"
    )

    assert result["accepted"] is False
    assert result["reason"] == "ambiguous_sample"
    assert result["mutation"] is None
    assert live_kit.state.assignment_for("Kick + Bass", "Kick") is None
    evidence = json.dumps(result)
    assert a.path not in evidence and b.path not in evidence


def test_drag_keys_match_live_kit_droparea_and_external_dnd_unaffected():
    from src.workbench_qml import QML_SOURCE

    qml = QML_SOURCE
    # DropArea keys used by Live Kit
    assert '"application/x-sample-brain-internal-sample"' in qml
    # Browser source builds Drag.keys from actual channels
    assert 'Drag.keys: {' in qml
    assert 'browserRow.internalSampleDescriptor.length > 0' in qml
    assert 'k.push("application/x-sample-brain-internal-sample")' in qml
    assert 'browserRow.outboundUrl.length > 0' in qml
    assert 'k.push("text/uri-list")' in qml
    assert 'return k' in qml
    # Harmony source has matching Drag.keys
    assert 'window.interaction.internalSampleDragEnabled ? ["application/x-sample-brain-internal-sample"] : []' in qml
    # external text/uri-list path remains independent
    assert '"text/uri-list"' in qml
    assert 'browserRow.internalSampleDescriptor.length > 0 || browserRow.outboundUrl.length > 0' in qml



def test_same_underlying_sample_on_both_surfaces_not_self_ambiguous(tmp_path: Path):
    adapter, live_kit = _adapter()
    row = _row(tmp_path, relative="packs/kick.wav")
    browser = list(adapter.view_model.browser_rows)
    browser[0] = _qml_browser_row(row)
    adapter.view_model.browser_rows = tuple(browser)
    harmony = list(adapter.view_model.harmony_rows)
    if harmony:
        harmony[0] = _qml_harmony_row(row)
    else:
        harmony = [_qml_harmony_row(row)]
    adapter.view_model.harmony_rows = tuple(harmony)
    adapter.toggle_live_kit_group("Kick + Bass")

    result = adapter.apply_internal_sample_drop(
        row.relative_path, "browser", "Kick + Bass", "Kick", "both-surfaces-1"
    )

    assert result["accepted"] is True and result["mutation"] == "assign"
    assert live_kit.state.assignment_for("Kick + Bass", "Kick") is row
