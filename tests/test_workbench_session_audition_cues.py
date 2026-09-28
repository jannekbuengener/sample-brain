"""TEST_GATE / TEST_FREEZE — Session audition cue offsets (Browser vs Live Kit).

Canonical authority for this slice:
- prompt_contract sample-brain-pr647-final-repair/v2
- docs/SESSION_OWNERSHIP_CONTRACT.md (when present)
- existing adapter contract:
  tests/test_workbench_qml_live_kit_audition.py::
  test_live_kit_audition_requests_zero_offset_while_browser_keeps_cue

Browser ``start_ms=None`` must resolve through ``get_preview_start_ms`` into the
shared session ``TransportAwarePreview``. Live Kit must keep explicit ``0``.
Both surfaces must share the identical ``session.audition`` owner.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src.workbench_controller import WorkbenchRow
from src.workbench_qml import QmlBrowserRow
from src.workbench_session import compose_workbench_session
from src.workbench_transport_ui import TransportAwarePreview


def _row(name: str = "cue_kick.wav", *, path: str | None = None) -> WorkbenchRow:
    resolved = path or f"synthetic/{name}"
    return WorkbenchRow(
        display_name=name,
        relative_path=resolved,
        path=resolved,
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


def _qml_browser_row(row: WorkbenchRow) -> QmlBrowserRow:
    return QmlBrowserRow(
        source_row=row,
        display_name=row.display_name,
        sample_type=row.pred_type or row.sample_class or "",
        bpm=str(row.bpm) if row.bpm is not None else "",
        key=row.key or "",
        duration=str(row.details.get("duration_sec", "")),
        waveform_envelope=(),
    )


def test_browser_preview_resolves_saved_cue_through_session_transport_aware_preview(
    monkeypatch: pytest.MonkeyPatch,
):
    """Browser ``start_ms=None`` must become the saved cue on the shared TAP."""

    saved_cue_ms = 456
    session = compose_workbench_session()
    adapter = session.qml_interaction_adapter
    audition = session.audition
    assert isinstance(audition, TransportAwarePreview)

    monkeypatch.setattr(
        "src.workbench_session.get_preview_start_ms",
        lambda path, *, library_db_path=None: saved_cue_ms,
        raising=False,
    )

    browser_row = _row("browser_saved_cue.wav")
    adapter.view_model.browser_rows = (_qml_browser_row(browser_row),)
    adapter.view_model.selected_browser_index = -1

    captured: list[tuple[Any, int]] = []
    original_play_row = audition.play_row

    def tracking_play_row(row: WorkbenchRow, *, start_ms: int = 0):
        captured.append((row, start_ms))
        return SimpleNamespace(ok=True)

    audition.play_row = tracking_play_row  # type: ignore[method-assign]
    try:
        assert adapter.preview_row(0) is browser_row
        assert captured == [(browser_row, saved_cue_ms)]
    finally:
        audition.play_row = original_play_row  # type: ignore[method-assign]


def test_live_kit_audition_forwards_explicit_zero_offset_unchanged(
    monkeypatch: pytest.MonkeyPatch,
):
    """Live Kit must keep ``start_ms=0`` and must not resolve a Browser cue."""

    session = compose_workbench_session()
    adapter = session.qml_interaction_adapter
    audition = session.audition

    def fail_if_resolved(*_args, **_kwargs):
        raise AssertionError("Live Kit must not call get_preview_start_ms")

    monkeypatch.setattr(
        "src.workbench_session.get_preview_start_ms",
        fail_if_resolved,
        raising=False,
    )

    assigned = _row("live_kit_zero.wav")
    session.live_kit.assign("Drums", "Main Drum", assigned)
    adapter._sync_live_kit_projection()

    captured: list[tuple[Any, int]] = []
    original_play_row = audition.play_row

    def tracking_play_row(row: WorkbenchRow, *, start_ms: int = 0):
        captured.append((row, start_ms))
        return SimpleNamespace(ok=True)

    audition.play_row = tracking_play_row  # type: ignore[method-assign]
    try:
        assert adapter.audition_live_kit_slot("Drums", "Main Drum") is True
        assert captured == [(assigned, 0)]
    finally:
        audition.play_row = original_play_row  # type: ignore[method-assign]


def test_browser_and_live_kit_share_exact_session_audition_owner(
    monkeypatch: pytest.MonkeyPatch,
):
    session = compose_workbench_session()
    adapter = session.qml_interaction_adapter
    audition = session.audition
    assert isinstance(audition, TransportAwarePreview)

    monkeypatch.setattr(
        "src.workbench_session.get_preview_start_ms",
        lambda path, *, library_db_path=None: 321,
        raising=False,
    )

    browser_row = _row("shared_owner_browser.wav")
    live_row = _row("shared_owner_live.wav")
    adapter.view_model.browser_rows = (_qml_browser_row(browser_row),)
    adapter.view_model.selected_browser_index = -1
    session.live_kit.assign("Drums", "Closed Hat", live_row)
    adapter._sync_live_kit_projection()

    owners: list[object] = []
    captured: list[tuple[Any, int]] = []
    original_play_row = audition.play_row

    def tracking_play_row(row: WorkbenchRow, *, start_ms: int = 0):
        owners.append(getattr(adapter._on_preview_requested, "__self__", None))
        captured.append((row, start_ms))
        return SimpleNamespace(ok=True)

    audition.play_row = tracking_play_row  # type: ignore[method-assign]
    try:
        assert adapter.preview_row(0) is browser_row
        assert adapter.audition_live_kit_slot("Drums", "Closed Hat") is True
    finally:
        audition.play_row = original_play_row  # type: ignore[method-assign]

    assert owners == [audition, audition]
    assert captured == [(browser_row, 321), (live_row, 0)]
    assert adapter._on_preview_requested is not None
    assert getattr(adapter._on_preview_requested, "__self__", None) is audition


def test_run_qml_screen1_remains_compatible_with_runtime_composition_only_engine(
    monkeypatch: pytest.MonkeyPatch,
):
    """Production entry must keep the established ``_qml_engine`` call shape."""

    from src import workbench_qml

    def fail_baseline(cls, _state_id):
        raise AssertionError("Production-QML darf baseline() nicht aufrufen")

    monkeypatch.setattr(
        workbench_qml.Screen1QmlViewModel,
        "baseline",
        classmethod(fail_baseline),
    )
    captured: dict[str, object] = {}

    class FakeApp:
        def exec(self) -> int:
            return 17

    def fake_engine(view_model, *, runtime_composition):
        captured["view_model"] = view_model
        captured["composition"] = runtime_composition
        return FakeApp(), object(), object()

    monkeypatch.setattr(workbench_qml, "_qml_engine", fake_engine)

    assert workbench_qml.run_qml_screen1() == 17
    view_model = captured["view_model"]
    assert view_model.browser_rows == ()
    assert view_model.selected_browser_index == -1
    assert captured["composition"].browser_state.rows == ()
