"""TEST_GATE / TEST_FREEZE — Cross-screen audio focus (#807).

Canonical authority:
- docs/SESSION_OWNERSHIP_CONTRACT.md (Cross-screen audio focus)
- docs/SEQUENCER_PLAYBACK_CONTRACT.md
- live issue #807

Policy: entering Screen 2 (and before pattern play) stops Screen-1 audition;
pattern stop does not revive preview; return to Screen 1 stays quiet.
QML remains intent-only; Python session owns the handoff.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.session_grid import TempoMap
from src.workbench_controller import WorkbenchRow
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
        start=MagicMock(),
        stop=MagicMock(),
        poll=MagicMock(),
    )


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


def _track_preview_releases(session) -> list[str]:
    """Focus transfer uses voice-only release (#916), not full audition.stop."""
    releases: list[str] = []
    adapter = session.qml_interaction_adapter
    original = adapter._on_preview_released

    def tracked() -> None:
        releases.append("audition.release_voice")
        if original is not None:
            original()

    adapter._on_preview_released = tracked
    return releases


def test_session_exposes_cross_screen_audio_focus_api():
    session = compose_workbench_session()
    assert callable(session.release_screen1_audition)
    assert callable(session.enter_screen2)
    assert callable(session.return_to_screen1)


def test_enter_screen2_stops_active_screen1_preview_projection():
    session = compose_workbench_session()
    adapter = session.qml_interaction_adapter
    release_calls = _track_preview_releases(session)
    adapter._preview_active = True
    adapter.view_model.auditioning_live_kit_slot = ("Kick + Bass", "Kick")
    adapter._auditioning_live_kit_slot = ("Kick + Bass", "Kick")

    state = session.enter_screen2()

    assert state is not None
    assert session.channel_rack.active_screen == "screen2"
    assert adapter.preview_active is False
    assert adapter.auditioning_live_kit_slot is None
    assert release_calls == ["audition.release_voice"]


def test_channel_rack_enter_screen2_claims_focus_via_session_hook():
    """Bridge/controller enter path must share the same release authority."""
    session = compose_workbench_session()
    adapter = session.qml_interaction_adapter
    adapter._preview_active = True
    release_calls: list[str] = []
    original = session.release_screen1_audition

    def tracked() -> None:
        release_calls.append("release")
        original()

    session.release_screen1_audition = tracked  # type: ignore[method-assign]
    # Re-bind controller hook to the tracked method (compose binds once).
    session.channel_rack.set_audio_focus_hooks(
        on_claim_focus=session.release_screen1_audition,
        on_release_to_screen1=session.release_screen1_audition,
    )

    session.channel_rack.enter_screen2()

    assert release_calls == ["release"]
    assert adapter.preview_active is False


def test_pattern_play_releases_screen1_audition_before_scheduling(monkeypatch):
    session = compose_workbench_session()
    session.channel_rack._transport = _fake_transport()
    adapter = session.qml_interaction_adapter
    kit = session.live_kit
    kit.assign("Kick + Bass", "Kick", _row("kick.wav"))

    stop_calls = _track_preview_releases(session)
    adapter._preview_active = True
    session.audition._active_voice_id = 42

    play_calls: list[dict] = []

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

    def fake_play(state, **kwargs):
        play_calls.append({"preview_active": adapter.preview_active, **kwargs})
        return FakeHandle()

    monkeypatch.setattr(
        "src.workbench_channel_rack.play_channel_rack_once",
        fake_play,
    )
    monkeypatch.setattr(
        "src.workbench_channel_rack.warm_channel_rack_pcm",
        lambda *_a, **_k: (),
    )

    session.enter_screen2()
    assert adapter.preview_active is False
    assert "audition.release_voice" in stop_calls

    # Simulate leftover projection if producer re-auditioned somehow before play.
    adapter._preview_active = True
    session.audition._active_voice_id = 99
    stop_calls.clear()

    original_release = session.audition.release_voice

    def release_and_clear() -> None:
        stop_calls.append("audition.release_voice")
        session.audition._active_voice_id = None
        original_release()

    adapter._on_preview_released = release_and_clear

    handle = session.channel_rack.play()
    assert handle is not None
    assert session.channel_rack.is_playing is True
    assert adapter.preview_active is False
    assert session.audition.active_voice_id is None
    assert stop_calls == ["audition.release_voice"]
    assert play_calls[0]["preview_active"] is False


def test_pattern_stop_does_not_restart_preview(monkeypatch):
    session = compose_workbench_session()
    session.channel_rack._transport = _fake_transport()
    adapter = session.qml_interaction_adapter
    session.live_kit.assign("Kick + Bass", "Kick", _row("kick.wav"))

    class FakeHandle:
        def __init__(self) -> None:
            self.player = SimpleNamespace(
                stop=lambda _eng: None,
                done=False,
                planned_count=16,
            )
            self.scheduled_count = 1

    monkeypatch.setattr(
        "src.workbench_channel_rack.play_channel_rack_once",
        lambda *_a, **_k: FakeHandle(),
    )
    monkeypatch.setattr(
        "src.workbench_channel_rack.warm_channel_rack_pcm",
        lambda *_a, **_k: (),
    )

    session.enter_screen2()
    session.channel_rack.play()
    assert session.channel_rack.is_playing is True

    session.channel_rack.stop()
    assert session.channel_rack.is_playing is False
    assert adapter.preview_active is False
    assert session.audition.active_voice_id is None


def test_return_to_screen1_leaves_quiet_and_does_not_resume_audition(monkeypatch):
    session = compose_workbench_session()
    session.channel_rack._transport = _fake_transport()
    adapter = session.qml_interaction_adapter
    session.live_kit.assign("Kick + Bass", "Kick", _row("kick.wav"))

    class FakeHandle:
        def __init__(self) -> None:
            self.player = SimpleNamespace(
                stop=lambda _eng: None,
                done=False,
                planned_count=16,
            )
            self.scheduled_count = 1

    monkeypatch.setattr(
        "src.workbench_channel_rack.play_channel_rack_once",
        lambda *_a, **_k: FakeHandle(),
    )
    monkeypatch.setattr(
        "src.workbench_channel_rack.warm_channel_rack_pcm",
        lambda *_a, **_k: (),
    )

    adapter._preview_active = True
    session.enter_screen2()
    session.channel_rack.play()
    session.return_to_screen1()

    assert session.channel_rack.active_screen == "screen1"
    assert session.channel_rack.is_playing is False
    assert adapter.preview_active is False
    assert adapter.auditioning_live_kit_slot is None
    assert session.audition.active_voice_id is None


def test_play_with_zero_schedulable_voices_does_not_advertise_playing(monkeypatch):
    """playing=True honesty: empty/soft-skipped pass must not strand UI."""
    session = compose_workbench_session()
    session.channel_rack._transport = _fake_transport()
    session.live_kit.assign(
        "Kick + Bass",
        "Kick",
        _row("missing.wav", path="synthetic/does-not-exist.wav"),
    )

    class EmptyHandle:
        def __init__(self) -> None:
            self.player = SimpleNamespace(
                stop=lambda _eng: None,
                done=True,
                planned_count=16,
            )
            self.planned_count = 16
            self.scheduled_count = 0
            self.scheduled_voice_ids = ()
            self.skipped_missing_source_count = 16

    monkeypatch.setattr(
        "src.workbench_channel_rack.play_channel_rack_once",
        lambda *_a, **_k: EmptyHandle(),
    )
    monkeypatch.setattr(
        "src.workbench_channel_rack.warm_channel_rack_pcm",
        lambda *_a, **_k: (),
    )

    session.enter_screen2()
    handle = session.channel_rack.play()
    assert handle is not None
    assert handle.scheduled_count == 0
    assert handle.player.done is True
    assert session.channel_rack.is_playing is False


def test_qml_open_channel_rack_routes_through_session_focus_policy():
    """#908 product open materializes bottom Rack without Screen-2 / focus claim.

    Audition quieting remains a play/enter_screen2 concern (#916), not open.
    """
    from src.workbench_qml import Screen1QmlViewModel, _qml_engine

    pytest.importorskip("PySide6.QtQuick")

    view_model = Screen1QmlViewModel.baseline("screen1-default-3panel")
    app, engine, _window = _qml_engine(view_model)
    try:
        adapter = engine._screen1_interaction_adapter
        session = getattr(engine, "_screen1_session", None)
        assert session is not None
        adapter._preview_active = True
        adapter._auditioning_live_kit_slot = ("Kick + Bass", "Kick")
        adapter.view_model.auditioning_live_kit_slot = ("Kick + Bass", "Kick")

        bridge = engine._screen1_interaction_bridge
        bridge.openChannelRack()
        app.processEvents()

        # Open must not claim audio focus or flip Screen-2 product navigation.
        assert adapter.preview_active is True
        assert adapter.auditioning_live_kit_slot == ("Kick + Bass", "Kick")
        assert engine._screen1_channel_rack.active_screen == "screen1"
        assert engine._screen1_channel_rack.state is not None

        # Legacy enter_screen2 still quiets audition (#916).
        session.enter_screen2()
        app.processEvents()
        assert adapter.preview_active is False
        assert adapter.auditioning_live_kit_slot is None
        assert bridge.property("previewActive") is False
        assert engine._screen1_channel_rack.active_screen == "screen2"

        bridge.returnToScreen1()
        app.processEvents()
        assert engine._screen1_channel_rack.active_screen == "screen1"
        assert adapter.preview_active is False
        assert bridge.property("previewActive") is False
        assert adapter.auditioning_live_kit_slot is None
    finally:
        engine.deleteLater()
        app.processEvents()
