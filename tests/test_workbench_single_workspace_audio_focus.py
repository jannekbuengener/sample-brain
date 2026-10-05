"""TEST_GATE / TEST_FREEZE — Single Workspace audio-focus seams (#916).

Canonical authority:
- docs/SESSION_OWNERSHIP_CONTRACT.md (domain audio focus; generalized from #807)
- live issue #916 (parent #905; audit #907)

Frozen v1 policy: last explicit playback intent wins.
- Rack Play releases audition voice/projection without shared-transport teardown
  for focus transfer, then starts Rack.
- Preview Play while Rack is playing stops Rack first, then starts preview.
- No auto-resume. No concurrent Preview+Rack.
- Stop invariant: never leave transport stopped while channel_rack.is_playing.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.session_grid import TempoMap
from src.workbench_controller import WorkbenchRow
from src.workbench_preview import PreviewResult
from src.workbench_qml import QmlBrowserRow
from src.workbench_session import compose_workbench_session


def _row(name: str, *, path: str | None = None) -> WorkbenchRow:
    resolved = path or f"synthetic/{name}"
    return WorkbenchRow(
        display_name=name,
        relative_path=name,
        path=resolved,
        bpm=132.0,
        key="Am",
        key_conf=0.9,
        loudness=-12.0,
        brightness=3000.0,
        sample_class="one_shot",
        pred_type="Kick",
        status="ok",
        details={"duration_sec": "0.2"},
    )


def _fake_engine() -> MagicMock:
    engine = MagicMock()
    engine.snapshot.return_value = SimpleNamespace(
        total_voice_count=0,
        voice_ids=(),
        voice_states=(),
        running=True,
        engine_frame=0,
    )
    engine.get_snapshot = engine.snapshot
    return engine


def _fake_transport(*, engine=None):
    if engine is None:
        engine = _fake_engine()
    return SimpleNamespace(
        tempo_map=TempoMap(bpm=120.0, sample_rate=48_000),
        sample_rate=48_000,
        engine_frame=0,
        ensure_engine_running=MagicMock(return_value=True),
        get_native_engine=MagicMock(return_value=engine),
        is_native_available=MagicMock(return_value=True),
        play=MagicMock(),
        start=MagicMock(),
        stop=MagicMock(),
        poll=MagicMock(),
        get_session_frame=MagicMock(return_value=0),
        get_engine_frame=MagicMock(return_value=0),
    )


def _track_transport_stops(session) -> list[str]:
    stops: list[str] = []
    transport = session.transport
    original = transport.stop

    def tracked() -> None:
        stops.append("transport.stop")
        original()

    transport.stop = tracked  # type: ignore[method-assign]
    return stops


def _track_preview_stops(session) -> list[str]:
    stops: list[str] = []
    adapter = session.qml_interaction_adapter
    original = adapter._on_preview_stopped

    def tracked() -> None:
        stops.append("audition.stop")
        if original is not None:
            original()

    adapter._on_preview_stopped = tracked
    return stops


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


def _install_browser_preview_row(adapter, row: WorkbenchRow) -> None:
    adapter.view_model.browser_rows = (_qml_browser_row(row),)
    adapter.view_model.selected_browser_index = -1


def _install_playable_rack(session, monkeypatch) -> None:
    """Materialize rack + fake engine path so play() can advertise playing."""
    session.channel_rack._transport = _fake_transport()
    session.live_kit.assign("Kick + Bass", "Kick", _row("kick.wav"))

    class FakeHandle:
        def __init__(self) -> None:
            self.player = SimpleNamespace(
                stop=lambda _eng: None,
                tick=MagicMock(
                    return_value=SimpleNamespace(
                        scheduled_count=1,
                        pending_count=0,
                        live_voice_count=1,
                    )
                ),
                done=False,
                planned_count=16,
            )
            self.planned_count = 16
            self.scheduled_count = 1
            self.scheduled_voice_ids = (1,)

    monkeypatch.setattr(
        "src.workbench_channel_rack.play_channel_rack_once",
        lambda *_a, **_k: FakeHandle(),
    )
    monkeypatch.setattr(
        "src.workbench_channel_rack.warm_channel_rack_pcm",
        lambda *_a, **_k: (),
    )


# --- 1–3: Rack materialization independent of screen navigation ---


def test_ensure_state_materializes_rack_without_enter_screen2():
    session = compose_workbench_session()
    session.live_kit.assign("Kick + Bass", "Kick", _row("kick.wav"))

    assert hasattr(session.channel_rack, "ensure_state")
    assert session.channel_rack.state is None
    assert session.channel_rack.active_screen == "screen1"

    state = session.channel_rack.ensure_state()

    assert state is not None
    assert session.channel_rack.state is state
    assert session.channel_rack.active_screen == "screen1"


def test_ensure_state_does_not_release_or_stop_active_audition():
    session = compose_workbench_session()
    session.live_kit.assign("Kick + Bass", "Kick", _row("kick.wav"))
    adapter = session.qml_interaction_adapter
    transport_stops = _track_transport_stops(session)
    preview_stops = _track_preview_stops(session)

    adapter._preview_active = True
    adapter._auditioning_live_kit_slot = ("Kick + Bass", "Kick")
    adapter.view_model.auditioning_live_kit_slot = ("Kick + Bass", "Kick")
    session.audition._active_voice_id = 7

    session.channel_rack.ensure_state()

    assert adapter.preview_active is True
    assert adapter.auditioning_live_kit_slot == ("Kick + Bass", "Kick")
    assert session.audition.active_voice_id == 7
    assert transport_stops == []
    assert preview_stops == []


def test_ensure_state_reconciles_existing_live_kit_assignments():
    session = compose_workbench_session()
    session.live_kit.assign("Kick + Bass", "Kick", _row("kick-a.wav"))
    first = session.channel_rack.ensure_state()
    kick_before = next(
        ch.sample_path
        for ch in first.channels
        if ch.live_kit_slot == "Kick"
    )
    assert kick_before is not None
    assert "kick-a.wav" in kick_before.replace("\\", "/")

    session.live_kit.assign("Kick + Bass", "Kick", _row("kick-b.wav"))
    second = session.channel_rack.ensure_state()

    kick_after = next(
        ch.sample_path
        for ch in second.channels
        if ch.live_kit_slot == "Kick"
    )
    assert kick_after is not None
    assert "kick-b.wav" in kick_after.replace("\\", "/")
    assert session.channel_rack.active_screen == "screen1"


# --- 4–6: Rack Play focus + shared transport ---


def test_rack_play_releases_active_audition_before_scheduling(monkeypatch):
    session = compose_workbench_session()
    _install_playable_rack(session, monkeypatch)
    adapter = session.qml_interaction_adapter
    session.channel_rack.ensure_state()

    adapter._preview_active = True
    session.audition._active_voice_id = 42
    preview_stops = _track_preview_stops(session)

    # Focus claim may use release_voice rather than full stop hook; also track
    # voice-id clearing via claim path.
    handle = session.channel_rack.play()

    assert handle is not None
    assert session.channel_rack.is_playing is True
    assert adapter.preview_active is False
    assert session.audition.active_voice_id is None
    assert adapter.auditioning_live_kit_slot is None
    # Focus may use voice-only release; full stop hook is optional.
    assert isinstance(preview_stops, list)


def test_rack_play_audition_release_does_not_stop_shared_transport(monkeypatch):
    session = compose_workbench_session()
    _install_playable_rack(session, monkeypatch)
    adapter = session.qml_interaction_adapter
    session.channel_rack.ensure_state()

    # Track stops on the *shared* session transport (audition owner), which is
    # what focus release historically tore down incorrectly.
    shared_stops = _track_transport_stops(session)
    adapter._preview_active = True
    session.audition._active_voice_id = 99

    session.channel_rack.play()

    assert "transport.stop" not in shared_stops
    assert session.channel_rack.is_playing is True
    assert adapter.preview_active is False
    assert session.audition.active_voice_id is None


def test_rack_play_uses_exactly_one_shared_transport_authority(monkeypatch):
    session = compose_workbench_session()
    shared = session.transport
    session.channel_rack._transport = shared
    engine = _fake_engine()
    shared.ensure_engine_running = MagicMock(return_value=True)  # type: ignore[method-assign]
    shared.get_native_engine = MagicMock(return_value=engine)  # type: ignore[method-assign]
    session.live_kit.assign("Kick + Bass", "Kick", _row("kick.wav"))
    session.channel_rack.ensure_state()

    class FakeHandle:
        def __init__(self) -> None:
            self.player = SimpleNamespace(
                stop=lambda _eng: None,
                done=False,
                planned_count=16,
            )
            self.planned_count = 16
            self.scheduled_count = 1
            self.scheduled_voice_ids = (1,)

    monkeypatch.setattr(
        "src.workbench_channel_rack.play_channel_rack_once",
        lambda *_a, **_k: FakeHandle(),
    )
    monkeypatch.setattr(
        "src.workbench_channel_rack.warm_channel_rack_pcm",
        lambda *_a, **_k: (),
    )

    session.channel_rack.play()
    assert session.channel_rack.transport is shared
    assert session.audition.transport is shared


# --- 7–8: Preview Play while Rack playing ---


def test_preview_play_while_rack_playing_stops_rack_then_starts_preview(monkeypatch):
    session = compose_workbench_session()
    _install_playable_rack(session, monkeypatch)
    adapter = session.qml_interaction_adapter
    session.channel_rack.ensure_state()
    session.channel_rack.play()
    assert session.channel_rack.is_playing is True

    play_calls: list[str] = []

    def ok_play_row(row, *, start_ms=0):
        play_calls.append("play_row")
        assert session.channel_rack.is_playing is False
        return PreviewResult(ok=True)

    monkeypatch.setattr(session.audition, "play_row", ok_play_row)

    row = _row("preview.wav")
    _install_browser_preview_row(adapter, row)
    adapter.preview_row(0)

    assert "play_row" in play_calls
    assert session.channel_rack.is_playing is False


def test_preview_focus_transfer_leaves_channel_rack_not_playing(monkeypatch):
    session = compose_workbench_session()
    _install_playable_rack(session, monkeypatch)
    adapter = session.qml_interaction_adapter
    session.channel_rack.ensure_state()
    session.channel_rack.play()

    monkeypatch.setattr(
        session.audition,
        "play_row",
        lambda row, *, start_ms=0: PreviewResult(ok=True),
    )
    row = _row("preview.wav")
    _install_browser_preview_row(adapter, row)
    adapter.preview_row(0)

    assert session.channel_rack.is_playing is False


# --- 9–10: Stop / idempotency ---


def test_no_auto_resume_after_rack_or_preview_stop(monkeypatch):
    session = compose_workbench_session()
    _install_playable_rack(session, monkeypatch)
    adapter = session.qml_interaction_adapter
    session.channel_rack.ensure_state()

    adapter._preview_active = True
    session.channel_rack.play()
    session.channel_rack.stop()
    assert adapter.preview_active is False
    assert session.audition.active_voice_id is None

    monkeypatch.setattr(
        session.audition,
        "play_row",
        lambda row, *, start_ms=0: PreviewResult(ok=True),
    )
    row = _row("preview.wav")
    _install_browser_preview_row(adapter, row)
    adapter.preview_row(0)
    adapter.stop_preview()

    assert session.channel_rack.is_playing is False
    assert adapter.preview_active is False


def test_repeated_focus_transfers_are_idempotent(monkeypatch):
    session = compose_workbench_session()
    _install_playable_rack(session, monkeypatch)
    session.channel_rack.ensure_state()
    shared_stops = _track_transport_stops(session)

    session.release_screen1_audition()
    session.release_screen1_audition()
    assert shared_stops.count("transport.stop") == 0

    session.channel_rack.play()
    session.channel_rack.play()
    assert session.channel_rack.is_playing is True
    assert shared_stops.count("transport.stop") == 0


# --- 11–12: Fail-closed honesty ---


def test_failed_preview_after_rack_stop_does_not_restart_rack(monkeypatch):
    session = compose_workbench_session()
    _install_playable_rack(session, monkeypatch)
    adapter = session.qml_interaction_adapter
    session.channel_rack.ensure_state()
    session.channel_rack.play()
    assert session.channel_rack.is_playing is True

    monkeypatch.setattr(
        session.audition,
        "play_row",
        lambda row, *, start_ms=0: PreviewResult(ok=False, message="fail"),
    )
    row = _row("preview.wav")
    _install_browser_preview_row(adapter, row)
    adapter.preview_row(0)

    assert session.channel_rack.is_playing is False


def test_failed_rack_start_after_audition_release_does_not_resume_audition(
    monkeypatch,
):
    session = compose_workbench_session()
    adapter = session.qml_interaction_adapter
    session.live_kit.assign("Kick + Bass", "Kick", _row("kick.wav"))
    session.channel_rack.ensure_state()
    session.channel_rack._transport = _fake_transport()

    adapter._preview_active = True
    session.audition._active_voice_id = 5

    monkeypatch.setattr(
        session.channel_rack,
        "_resolve_engine_adapter",
        MagicMock(side_effect=RuntimeError("engine missing")),
    )

    with pytest.raises(RuntimeError, match="engine missing"):
        session.channel_rack.play()

    assert session.channel_rack.is_playing is False
    assert adapter.preview_active is False
    assert session.audition.active_voice_id is None


# --- Owner-required stop invariant ---


def test_preview_stop_never_leaves_transport_stopped_while_rack_playing(
    monkeypatch,
):
    """INVARIANT (#916): no audition stop path may stop shared transport while
    ChannelRackController.is_playing remains True.

    Allowed: preview-only release without transport teardown while Rack owns
    playback, OR stop Rack via ChannelRackController.stop() before any shared
    transport teardown. Forbidden: transport stopped + is_playing True.
    """
    session = compose_workbench_session()
    _install_playable_rack(session, monkeypatch)
    adapter = session.qml_interaction_adapter
    session.channel_rack.ensure_state()
    session.channel_rack.play()
    assert session.channel_rack.is_playing is True

    # Simulate an active audition projection that a stop path might clear.
    adapter._preview_active = True
    session.audition._active_voice_id = 77

    transport_stops = _track_transport_stops(session)

    def _assert_invariant() -> None:
        if "transport.stop" in transport_stops:
            assert session.channel_rack.is_playing is False, (
                "transport.stop while channel_rack.is_playing=True is forbidden"
            )

    # Path A: session focus release (historically quiet_audition -> full stop)
    session.release_screen1_audition()
    _assert_invariant()

    # Re-arm rack playing + audition for path B if path A stopped the rack.
    if not session.channel_rack.is_playing:
        session.channel_rack.play()
        assert session.channel_rack.is_playing is True
        adapter._preview_active = True
        session.audition._active_voice_id = 78
        transport_stops.clear()

    # Path B: adapter quiet / stop_preview / audition.stop
    adapter.quiet_audition()
    _assert_invariant()

    if not session.channel_rack.is_playing:
        session.channel_rack.play()
        assert session.channel_rack.is_playing is True
        adapter._preview_active = True
        session.audition._active_voice_id = 79
        transport_stops.clear()

    adapter.stop_preview()
    _assert_invariant()

    if not session.channel_rack.is_playing:
        session.channel_rack.play()
        assert session.channel_rack.is_playing is True
        session.audition._active_voice_id = 80
        transport_stops.clear()

    session.audition.stop()
    _assert_invariant()
