"""#1377 minimal default Live Kit rack — one visible empty slot per group."""

from __future__ import annotations

from pathlib import Path

from src.workbench_controller import WorkbenchRow
from src.workbench_live_kit import (
    LIVE_KIT_SLOT_MAPPING,
    LiveKitPresentationState,
    LiveKitState,
    is_live_kit_extra_slot,
    live_kit_group_display_name,
    live_kit_has_extra_slots,
)
from src.workbench_live_kit_export import (
    LIVE_KIT_EXPORT_SCHEMA_VERSION,
    LIVE_KIT_EXPORT_SCHEMA_VERSION_V2,
    export_live_kit,
)
from src.workbench_qml import LiveKitPresenter
from src.workbench_qml_spike import (
    Screen1QmlInteractionAdapter,
    build_qml_view_model_from_fixture,
)
from src.workbench_session_store import (
    apply_snapshot_to_live_kit,
    load_workbench_session_snapshot,
    save_workbench_session_snapshot,
    snapshot_from_musical_state,
)
from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1


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


def _transport():
    from types import SimpleNamespace

    return SimpleNamespace(
        get_resume_master_bpm=lambda: 120.0,
        is_sync_enabled=lambda: False,
        get_snapshot=lambda: {"current_tempo": 120.0, "next_tempo_bpm": None},
    )


def test_empty_kit_projects_exactly_one_visible_slot_per_group() -> None:
    presenter = LiveKitPresenter()
    assert len(presenter.groups) == 4
    assert all(len(group.slots) == 1 for group in presenter.groups)
    assert sum(len(group.slots) for group in presenter.groups) == 4
    # Domain still owns the full canonical seed (no silent domain shrink).
    for group, slots in LIVE_KIT_SLOT_MAPPING:
        assert presenter.state.slots_for(group) == slots


def test_plus_reveals_hidden_canonical_before_creating_extra() -> None:
    presenter = LiveKitPresenter()
    first = presenter.grow_visible_slot("Kick + Bass")
    assert first == "Bass"
    assert [s.name for s in presenter.groups[0].slots] == ["Kick", "Bass"]
    assert live_kit_has_extra_slots(presenter.state) is False

    second = presenter.grow_visible_slot("Kick + Bass")
    assert second == "Extra 1"
    assert is_live_kit_extra_slot(second)
    assert [s.name for s in presenter.groups[0].slots] == ["Kick", "Bass", "Extra 1"]


def test_plus_grows_only_the_targeted_group() -> None:
    presenter = LiveKitPresenter()
    presenter.grow_visible_slot("Drums")
    by_name = {group.name: [s.name for s in group.slots] for group in presenter.groups}
    assert by_name["Drums"] == ["Main Drum", "Closed Hat"]
    assert by_name["Kick + Bass"] == ["Kick"]
    assert by_name["Melodic"] == ["Lead"]
    assert by_name["Atmos / FX"] == ["Atmos"]


def test_occupied_higher_slot_forces_prefix_visible_without_mutation() -> None:
    state = LiveKitState()
    state.assign("Kick + Bass", "Bass", _row("bass.wav"))
    presenter = LiveKitPresenter(state=state)
    assert [s.name for s in presenter.groups[0].slots] == ["Kick", "Bass"]
    assert live_kit_has_extra_slots(presenter.state) is False


def test_session_restart_keeps_assignments_and_extras_visible(
    tmp_path: Path,
) -> None:
    state = LiveKitState()
    state.assign("Drums", "Percussion", _row("perc.wav"))
    extra = state.append_empty_slot("Drums")
    state.assign("Drums", extra, _row("extra.wav"))
    snapshot = snapshot_from_musical_state(state, None, _transport())
    save_workbench_session_snapshot(snapshot, state_dir=tmp_path)

    restored_snap = load_workbench_session_snapshot(state_dir=tmp_path)
    assert restored_snap is not None
    restored = LiveKitState()
    apply_snapshot_to_live_kit(restored_snap, restored)
    presenter = LiveKitPresenter(state=restored)
    drums = next(g for g in presenter.groups if g.name == "Drums")
    names = [s.name for s in drums.slots]
    assert "Percussion" in names
    assert extra in names
    assert drums.slots[names.index("Percussion")].assignment is not None
    assert drums.slots[names.index(extra)].assignment is not None


def test_restart_collapses_empty_canonical_reveals_not_backed_by_session() -> None:
    """Empty Plus-reveals of canonical slots are presentation-only.

    After a cold restore of an empty kit, visibility returns to the minimal
    default. Empty Extra-N remain visible because they are session domain truth.
    """
    presenter = LiveKitPresenter()
    presenter.grow_visible_slot("Melodic")  # reveal Pad (canonical, empty)
    assert [s.name for s in next(g for g in presenter.groups if g.name == "Melodic").slots] == [
        "Lead",
        "Pad",
    ]
    # Cold presenter over the same empty domain → minimal default.
    cold = LiveKitPresenter(state=presenter.state)
    melodic = next(g for g in cold.groups if g.name == "Melodic")
    assert [s.name for s in melodic.slots] == ["Lead"]


def test_empty_extra_survives_restart_visibility(tmp_path: Path) -> None:
    state = LiveKitState()
    # Exhaust Melodic canonical via domain Extra (session-backed empty field).
    while len(state.slots_for("Melodic")) < 3:
        state.append_empty_slot("Melodic", notify=False)
    assert "Extra 1" in state.slots_for("Melodic")
    snapshot = snapshot_from_musical_state(state, None, _transport())
    save_workbench_session_snapshot(snapshot, state_dir=tmp_path)
    restored = LiveKitState()
    apply_snapshot_to_live_kit(load_workbench_session_snapshot(state_dir=tmp_path), restored)
    presenter = LiveKitPresenter(state=restored)
    melodic = next(g for g in presenter.groups if g.name == "Melodic")
    assert [s.name for s in melodic.slots] == ["Lead", "Pad", "Extra 1"]


def test_legacy_eleven_slot_kit_assignments_remain_visible() -> None:
    state = LiveKitState()
    state.assign("Atmos / FX", "FX", _row("fx.wav"))
    presenter = LiveKitPresenter(state=state)
    atmos = next(g for g in presenter.groups if g.name == "Atmos / FX")
    assert [s.name for s in atmos.slots] == ["Atmos", "FX"]
    assert atmos.slots[1].assignment is not None


def test_atmos_display_name_is_atmos_fx_vocal_without_domain_rename() -> None:
    assert live_kit_group_display_name("Atmos / FX") == "Atmos / FX / Vocal"
    assert "Atmos / FX" in dict(LIVE_KIT_SLOT_MAPPING)
    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(fixture, "screen1-default-3panel")
    view_model.live_kit_groups = LiveKitPresenter().groups
    groups = view_model.qml_context()["liveKitGroups"]
    assert groups[-1]["name"] == "Atmos / FX"
    assert groups[-1]["displayName"] == "Atmos / FX / Vocal"
    assert len(groups[-1]["slots"]) == 1


def test_grow_does_not_alter_existing_assignments() -> None:
    presenter = LiveKitPresenter()
    presenter.assign("Kick + Bass", "Kick", _row("kick.wav"))
    presenter.grow_visible_slot("Kick + Bass")
    assert presenter.state.assignment_for("Kick + Bass", "Kick") is not None
    assert presenter.state.assignment_for("Kick + Bass", "Bass") is None


def test_export_v1_canonical_and_v2_with_extras(tmp_path: Path) -> None:
    media = tmp_path / "src"
    media.mkdir()
    wav = media / "kick.wav"
    wav.write_bytes(b"RIFF....WAVEfmt ")
    row = WorkbenchRow(
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
    )
    canonical = LiveKitState()
    canonical.assign("Kick + Bass", "Kick", row)
    dest_v1 = tmp_path / "v1"
    dest_v1.mkdir()
    result_v1 = export_live_kit(canonical, dest_v1)
    assert result_v1.ok
    import json

    manifest_v1 = json.loads(
        (result_v1.export_path / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest_v1["schema_version"] == LIVE_KIT_EXPORT_SCHEMA_VERSION

    growing = LiveKitState()
    extra = growing.append_empty_slot("Kick + Bass")
    growing.assign("Kick + Bass", extra, row)
    dest_v2 = tmp_path / "v2"
    dest_v2.mkdir()
    result_v2 = export_live_kit(growing, dest_v2)
    assert result_v2.ok
    manifest_v2 = json.loads(
        (result_v2.export_path / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest_v2["schema_version"] == LIVE_KIT_EXPORT_SCHEMA_VERSION_V2


def test_presentation_reveal_is_not_a_domain_mutation() -> None:
    state = LiveKitState()
    presentation = LiveKitPresentationState(state, minimal_default_rack=True)
    before = state.slots_for("Drums")
    revealed = presentation.reveal_next_slot("Drums")
    assert revealed == "Closed Hat"
    assert state.slots_for("Drums") == before
    structure = presentation.visible_structure()
    drums = next(g for g in structure if g.name == "Drums")
    assert [s.name for s in drums.slots] == ["Main Drum", "Closed Hat"]


def test_tk_fallback_presentation_keeps_full_domain_visible() -> None:
    state = LiveKitState()
    presentation = LiveKitPresentationState(state)
    drums = next(g for g in presentation.visible_structure() if g.name == "Drums")
    assert [s.name for s in drums.slots] == list(state.slots_for("Drums"))


def test_adapter_plus_uses_grow_not_blind_extra() -> None:
    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(fixture, "screen1-default-3panel")
    live_kit = LiveKitPresenter()
    adapter = Screen1QmlInteractionAdapter(view_model=view_model, live_kit=live_kit)
    view_model.live_kit_groups = live_kit.groups
    created = adapter.append_empty_live_kit_slot("Kick + Bass")
    assert created == "Bass"
    assert live_kit_has_extra_slots(live_kit.state) is False
    assert [s.name for s in live_kit.groups[0].slots] == ["Kick", "Bass"]


def test_fresh_presenter_has_no_prefilled_assignments() -> None:
    presenter = LiveKitPresenter()
    for group in presenter.groups:
        assert len(group.slots) == 1
        assert group.slots[0].assignment is None
        assert presenter.state.assignment_for(group.name, group.slots[0].name) is None


def test_qml_source_has_bottom_plus_only_no_side_add() -> None:
    from src.workbench_qml import QML_SOURCE

    assert "showAddAffordance" not in QML_SOURCE
    assert 'objectName: "liveKitGroupPlus"' in QML_SOURCE
    rack = QML_SOURCE.split('objectName: "liveKitVerticalRack"', 1)[1]
    rack = rack.split("channelRackScreen", 1)[0]
    before_group_plus, after_group_plus = rack.split("id: liveKitGroupPlus", 1)
    assert 'text: "+"' not in before_group_plus
    assert 'text: "+"' in after_group_plus
    assert 'text: "↻"' in before_group_plus


def test_fixture_seed_is_not_the_product_empty_default() -> None:
    """Acceptance fixtures may carry demo assignments; product presenter must not."""
    fixture = build_screen1_visual_fixture_v1()
    assert fixture.assignments  # historical visual fixture still has seeds
    product = LiveKitPresenter()
    assert all(
        slot.assignment is None
        for group in product.groups
        for slot in group.slots
    )
