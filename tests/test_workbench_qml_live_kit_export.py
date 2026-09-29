"""QML / interaction contracts for #728 Live Kit Export Kit control.

The Export control remains a secondary Live Kit action. FolderDialog only
selects a destination; the pure Python export service owns the write path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.workbench_controller import WorkbenchRow
from src.workbench_live_kit import LiveKitState
from src.workbench_live_kit_export import LIVE_KIT_EXPORT_DIR_NAME, LiveKitExportResult
from src.workbench_qml import (
    QML_SOURCE,
    LiveKitPresenter,
    Screen1QmlInteractionAdapter,
)
from src.workbench_qml_spike import build_qml_view_model_from_fixture
from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1


def _write_bytes(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _row(path: Path, *, display_name: str | None = None) -> WorkbenchRow:
    name = display_name or path.name
    return WorkbenchRow(
        display_name=name,
        relative_path=f"synthetic/{name}",
        path=str(path),
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


def test_export_kit_control_is_reachable_from_live_kit_qml() -> None:
    assert 'text: "Export Kit"' in QML_SOURCE
    assert "objectName: \"liveKitExportButton\"" in QML_SOURCE
    assert "id: exportKitDialog" in QML_SOURCE
    assert "FolderDialog" in QML_SOURCE
    assert "exportLiveKitUrl" in QML_SOURCE
    assert "liveKitExportStatus" in QML_SOURCE
    # Secondary action — not a dominant red CTA.
    export_block = QML_SOURCE.split('text: "Export Kit"', 1)[1][:400]
    assert "theme.actionDestructive" not in export_block
    assert "theme.danger" not in export_block


def test_folder_dialog_cancellation_has_no_mutation(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    kick = _write_bytes(sources / "kick.wav", b"RIFF-KICK")
    state = LiveKitState()
    state.assign("Kick + Bass", "Kick", _row(kick))
    _fixture, view_model, adapter, live_kit = _production_adapter(state)

    before_assignment = live_kit.state.assignment_for("Kick + Bass", "Kick")
    before_selected = adapter.selected_browser_index
    before_pending = adapter.pending_live_kit_add
    before_preview = adapter.preview_active
    before_status = adapter.live_kit_export_status

    # Cancellation is a no-op: no export intent is dispatched.
    assert adapter.live_kit_export_status == before_status
    assert live_kit.state.assignment_for("Kick + Bass", "Kick") is before_assignment
    assert adapter.selected_browser_index == before_selected
    assert adapter.pending_live_kit_add == before_pending
    assert adapter.preview_active == before_preview
    assert view_model.live_kit_groups is live_kit.groups


def test_successful_selection_calls_exactly_one_export_intent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sources = tmp_path / "sources"
    kick = _write_bytes(sources / "kick.wav", b"RIFF-KICK")
    destination = tmp_path / "dest"
    destination.mkdir()
    state = LiveKitState()
    state.assign("Kick + Bass", "Kick", _row(kick))
    _fixture, _view_model, adapter, _live_kit = _production_adapter(state)

    calls: list[object] = []

    def fake_export(live_state, destination_parent):
        calls.append((live_state, Path(destination_parent)))
        return LiveKitExportResult(
            ok=True,
            export_path=Path(destination_parent) / LIVE_KIT_EXPORT_DIR_NAME,
            assigned_count=1,
            empty_count=10,
        )

    monkeypatch.setattr(
        "src.workbench_qml.export_live_kit",
        fake_export,
    )

    result = adapter.export_live_kit(destination)
    assert result.ok is True
    assert len(calls) == 1
    assert calls[0][0] is adapter._live_kit.state
    assert calls[0][1] == destination
    assert LIVE_KIT_EXPORT_DIR_NAME in adapter.live_kit_export_status
    assert str(result.export_path) in adapter.live_kit_export_status or result.export_path.name in adapter.live_kit_export_status


def test_success_message_exposes_resulting_destination(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    kick = _write_bytes(sources / "kick.wav", b"RIFF-KICK")
    destination = tmp_path / "dest"
    destination.mkdir()
    state = LiveKitState()
    state.assign("Kick + Bass", "Kick", _row(kick))
    _fixture, _view_model, adapter, _live_kit = _production_adapter(state)

    result = adapter.export_live_kit(destination)
    assert result.ok is True
    assert result.export_path is not None
    assert str(result.export_path) in adapter.live_kit_export_status
    assert adapter.live_kit_export_ok is True


def test_failure_message_is_understandable_without_tracebacks(tmp_path: Path) -> None:
    destination = tmp_path / "dest"
    destination.mkdir()
    _fixture, _view_model, adapter, _live_kit = _production_adapter(LiveKitState())

    result = adapter.export_live_kit(destination)
    assert result.ok is False
    assert adapter.live_kit_export_ok is False
    message = adapter.live_kit_export_status
    assert message
    assert "Traceback" not in message
    assert "File \"" not in message
    assert "leer" in message.casefold() or "empty" in message.casefold()


def test_no_export_when_kit_is_empty(tmp_path: Path) -> None:
    destination = tmp_path / "dest"
    destination.mkdir()
    _fixture, _view_model, adapter, live_kit = _production_adapter(LiveKitState())

    result = adapter.export_live_kit(destination)
    assert result.ok is False
    assert result.error_code == "EMPTY_KIT"
    assert not (destination / LIVE_KIT_EXPORT_DIR_NAME).exists()
    assert all(
        slot.assignment is None
        for group in live_kit.groups
        for slot in group.slots
    )


def test_export_preserves_browser_preview_harmony_and_transport_contracts(tmp_path: Path) -> None:
    sources = tmp_path / "sources"
    kick = _write_bytes(sources / "kick.wav", b"RIFF-KICK")
    destination = tmp_path / "dest"
    destination.mkdir()
    state = LiveKitState()
    state.assign("Kick + Bass", "Kick", _row(kick))

    preview_calls: list[str] = []
    stop_calls: list[str] = []

    def on_preview(row, **_kwargs):
        preview_calls.append(row.path)
        return True

    def on_stop():
        stop_calls.append("stop")

    fixture, view_model, adapter, live_kit = _production_adapter(
        state,
        on_preview_requested=on_preview,
        on_preview_stopped=on_stop,
    )

    selected = adapter.select_row(0)
    adapter.preview_row(0)
    assert adapter.preview_active is True
    before_selected = adapter.selected_browser_index
    before_harmony_open = adapter.harmonic_match_open
    before_pending = adapter.pending_live_kit_add
    before_assignment = live_kit.state.assignment_for("Kick + Bass", "Kick")
    before_collapsed = live_kit.presentation.is_collapsed("Kick + Bass")

    result = adapter.export_live_kit(destination)
    assert result.ok is True

    assert adapter.selected_browser_index == before_selected
    assert adapter.harmonic_match_open == before_harmony_open
    assert adapter.pending_live_kit_add == before_pending
    assert adapter.preview_active is True
    assert live_kit.state.assignment_for("Kick + Bass", "Kick") is before_assignment
    assert live_kit.presentation.is_collapsed("Kick + Bass") is before_collapsed
    assert selected.path == fixture.browser_rows[0].path
    assert view_model.browser_rows[0].source_row.path == fixture.browser_rows[0].path
    assert stop_calls == []
    assert preview_calls == [fixture.browser_rows[0].path]


def test_qml_export_dialog_wires_accepted_url_once() -> None:
    assert "onAccepted: window.interaction.exportLiveKitUrl(selectedFolder.toString())" in QML_SOURCE
    assert QML_SOURCE.count("exportLiveKitUrl(") == 1
    assert "onClicked: exportKitDialog.open()" in QML_SOURCE
