"""TEST_GATE / TEST_FREEZE — Screen-2 QML Channel Rack (#678).

Canonical authority:
- docs/PRODUCT_WORKFLOW_CANON.md
- docs/PATTERN_CORE_CONTRACT.md
- docs/SEQUENCER_PLAYBACK_CONTRACT.md
- docs/SESSION_OWNERSHIP_CONTRACT.md
- live #678 / #675 (Owner-GO lifts PARKED for Screen-2 only)
- src/channel_rack.py
- src/pattern_core.py
- src/sequencer_playback.py
- src/workbench_live_kit.py

Python remains musical SoT. QML projects state and sends commands.
No pattern shadow truth, no second transport/audio/session owner.

Forbidden in this slice:
- Arrangement / Playlist / Screen 3
- Piano Roll / Mixer / Sends / Inserts / Buses
- Vocal/Beatbox / VST / Bitwig / Cloud
- Fake Live Kit slot IDs for user channels

TEST_FREEZE_RECONCILIATION (#1077 / #1075 / #1076 — explicit, not silent):
Historical #908 QML-bottom-Rack projection assertions in this file
(``bottomRackPane`` visibly hosting ``bottomRackStepList`` /
``bottomRackPlayButton`` / ``bottomRackStopButton`` as Edit product UI) are
**superseded** by PRODUCT_WORKFLOW_CANON + #1075/#1076/#1077:

- Live Kit = Edit tool (visible-only; no Rack/step co-host)
- Channel Rack / Pattern / Step Sequencer = domain foundation
- Product step-UI placement = Arrangement workflow
- Closed #908 bottom projection = historical evidence, not product authority

Released from this freeze (do not reassert as Edit product UI here):
- ``bottom is not None and bottom.isVisible()`` with step-list/play/stop present
- Any requirement that ``openChannelRack`` forces Edit bottom Rack geometry

Still frozen here: Channel Rack domain / controller / playback / navigation
contracts (ensure_state materialization, step toggle, user channels, play/stop
fail-soft, legacy Screen-2 page stays hidden, Live Kit musical assignments).

New #1077 Live Kit Edit product-UI expectations live in
``tests/test_workbench_live_kit_edit_1077.py``.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.channel_rack import (
    ChannelRackState,
    add_user_channel,
    build_channel_rack_state,
    toggle_step,
)
from src.pattern_core import USER_CHANNEL_ID_PREFIX, Channel, Trigger
from src.session_grid import TempoMap
from src.workbench_controller import WorkbenchRow
from src.workbench_live_kit import LIVE_KIT_SLOT_MAPPING, LiveKitState


REQUIRED_CONTROLLER_SYMBOLS = (
    "ChannelRackController",
    "project_channel_rack_for_qml",
)


def _controller_module_or_fail():
    try:
        return importlib.import_module("src.workbench_channel_rack")
    except ModuleNotFoundError as exc:
        if exc.name in {"src.workbench_channel_rack", "workbench_channel_rack"} or (
            exc.name is not None and exc.name.endswith("workbench_channel_rack")
        ):
            pytest.fail(
                "MISSING_PRODUCTION_SURFACE: src.workbench_channel_rack "
                "(Screen-2 Channel Rack controller not implemented)"
            )
        raise


def _require(module, name: str):
    value = getattr(module, name, None)
    if value is None:
        pytest.fail(f"MISSING_PRODUCTION_SURFACE: {module.__name__}.{name}")
    return value


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


def _kit_with_samples() -> LiveKitState:
    kit = LiveKitState()
    kit.assign("Kick + Bass", "Kick", _row("kick.wav"))
    kit.assign("Drums", "Closed Hat", _row("ch.wav"))
    kit.assign("Drums", "Open Hat", _row("oh.wav"))
    return kit


def _fake_transport(*, sample_rate: int = 48_000, engine=None):
    tempo = TempoMap(sample_rate=sample_rate, bpm=132.0)
    transport = SimpleNamespace(
        tempo_map=tempo,
        engine_frame=0,
        sample_rate=sample_rate,
        ensure_engine_running=lambda: engine is not None,
        get_native_engine=lambda: engine,
        is_native_available=lambda: engine is not None,
        start=MagicMock(),
        stop=MagicMock(),
    )
    return transport


# --- Projection / Live Kit ---------------------------------------------------


def test_controller_public_seam_exists():
    module = _controller_module_or_fail()
    for name in REQUIRED_CONTROLLER_SYMBOLS:
        _require(module, name)


def test_live_kit_projection_is_deterministic_and_grouped():
    module = _controller_module_or_fail()
    Controller = _require(module, "ChannelRackController")
    project = _require(module, "project_channel_rack_for_qml")

    kit = _kit_with_samples()
    controller = Controller(live_kit=kit, transport=_fake_transport())
    controller.enter_screen2()
    projection = project(controller.state)

    assert controller.active_screen == "screen2"
    assert projection["step_count"] == 16
    assert projection["pattern_id"] == "screen2-main"
    group_names = [group["name"] for group in projection["groups"]]
    assert group_names == [group for group, _slots in LIVE_KIT_SLOT_MAPPING]
    rows = [row for group in projection["groups"] for row in group["rows"]]
    assert len(rows) == 11
    kick = next(row for row in rows if row["channel_id"] == "ch_kick")
    assert kick["display_name"] == "Kick"
    assert kick["live_kit_group"] == "Kick + Bass"
    assert kick["live_kit_slot"] == "Kick"
    assert kick["sample_label"] == "kick.wav"
    assert kick["is_user_channel"] is False
    assert kick["steps"] == [True] * 16
    empty = next(row for row in rows if row["channel_id"] == "ch_bass")
    assert empty["steps"] == [False] * 16
    assert empty["sample_label"] == ""


def test_step_toggle_is_exactly_one_python_state_transition():
    module = _controller_module_or_fail()
    Controller = _require(module, "ChannelRackController")
    project = _require(module, "project_channel_rack_for_qml")

    kit = _kit_with_samples()
    controller = Controller(live_kit=kit, transport=_fake_transport())
    controller.enter_screen2()
    before = controller.state
    assert before is not None
    after = controller.toggle_step("ch_kick", 0)
    assert after is not before
    assert after is controller.state
    assert Trigger(channel_id="ch_kick", position=Fraction(0, 4)) not in after.pattern.triggers
    projection = project(after)
    kick = next(
        row
        for group in projection["groups"]
        for row in group["rows"]
        if row["channel_id"] == "ch_kick"
    )
    assert kick["steps"][0] is False
    assert kick["steps"][1] is True

    restored = controller.toggle_step("ch_kick", 0)
    assert Trigger(channel_id="ch_kick", position=Fraction(0, 4)) in restored.pattern.triggers


def test_user_channel_uses_opaque_id_without_fake_live_kit_slot():
    module = _controller_module_or_fail()
    Controller = _require(module, "ChannelRackController")
    project = _require(module, "project_channel_rack_for_qml")

    controller = Controller(live_kit=LiveKitState(), transport=_fake_transport())
    controller.enter_screen2()
    state = controller.add_user_channel(sample_path="synthetic/user.wav")
    user = next(ch for ch in state.channels if ch.channel_id.startswith(USER_CHANNEL_ID_PREFIX))
    assert user.live_kit_group is None
    assert user.live_kit_slot is None
    assert user.sample_path == "synthetic/user.wav"
    projection = project(state)
    user_groups = [g for g in projection["groups"] if g["name"] == "User"]
    assert len(user_groups) == 1
    assert user_groups[0]["rows"][0]["is_user_channel"] is True
    assert user_groups[0]["rows"][0]["channel_id"] == user.channel_id
    assert user_groups[0]["rows"][0]["steps"] == [True] * 16


def test_navigation_preserves_live_kit_and_pattern():
    module = _controller_module_or_fail()
    Controller = _require(module, "ChannelRackController")

    kit = _kit_with_samples()
    controller = Controller(live_kit=kit, transport=_fake_transport())
    controller.enter_screen2()
    controller.toggle_step("ch_kick", 3)
    pattern_before = controller.state.pattern if controller.state else None
    assert pattern_before is not None

    controller.leave_screen2()
    assert controller.active_screen == "screen1"
    assert kit.assignment_for("Kick + Bass", "Kick") is not None
    assert controller.state is not None
    assert controller.state.pattern.triggers == pattern_before.triggers

    controller.enter_screen2()
    assert controller.state.pattern.triggers == pattern_before.triggers
    assert Trigger(channel_id="ch_kick", position=Fraction(3, 4)) not in controller.state.pattern.triggers


def test_play_stop_uses_pattern_pass_player_and_pcm_provider(monkeypatch):
    module = _controller_module_or_fail()
    Controller = _require(module, "ChannelRackController")

    engine = MagicMock()
    engine.get_snapshot.return_value = SimpleNamespace(
        total_voice_count=0,
        voice_ids=(),
        voice_states=(),
    )
    transport = _fake_transport(engine=engine)
    kit = _kit_with_samples()
    controller = Controller(live_kit=kit, transport=transport)

    play_calls: list[dict] = []
    stop_calls: list[object] = []

    class FakeHandle:
        def __init__(self) -> None:
            self.player = SimpleNamespace(
                stop=lambda eng: stop_calls.append(eng),
                tick=MagicMock(
                    return_value=SimpleNamespace(
                        scheduled_count=0,
                        pending_count=0,
                        live_voice_count=0,
                    )
                ),
                done=False,
                planned_count=48,
            )
            self.planned_count = 48
            self.scheduled_count = 0
            self.skipped_voice_limit_count = 0

    def fake_play(state, **kwargs):
        play_calls.append({"state": state, **kwargs})
        return FakeHandle()

    monkeypatch.setattr(module, "play_channel_rack_once", fake_play)
    monkeypatch.setattr(module, "warm_channel_rack_pcm", lambda *_a, **_k: ())

    controller.enter_screen2()
    handle = controller.play()
    assert handle is not None
    assert controller.is_playing is True
    assert len(play_calls) == 1
    assert play_calls[0]["pcm_provider"] is controller.pcm_provider
    assert play_calls[0]["engine"]._engine is engine
    assert "lookahead_frames" in play_calls[0]

    controller.stop()
    assert controller.is_playing is False
    assert len(stop_calls) == 1
    assert stop_calls[0]._engine is engine


def test_play_without_native_engine_fails_closed():
    module = _controller_module_or_fail()
    Controller = _require(module, "ChannelRackController")
    transport = _fake_transport(engine=None)
    controller = Controller(live_kit=_kit_with_samples(), transport=transport)
    controller.enter_screen2()
    with pytest.raises(RuntimeError, match="Native audio engine"):
        controller.play()
    assert controller.is_playing is False
    assert controller.state is not None


def test_play_transport_start_failure_does_not_advertise_playing():
    module = _controller_module_or_fail()
    Controller = _require(module, "ChannelRackController")
    engine = MagicMock()
    transport = _fake_transport(engine=engine)
    transport.play = MagicMock(side_effect=RuntimeError("device busy"))
    # Prefer play() over legacy start() alias.
    del transport.start
    controller = Controller(live_kit=_kit_with_samples(), transport=transport)
    controller.enter_screen2()
    with pytest.raises(RuntimeError, match="transport failed to start"):
        controller.play()
    assert controller.is_playing is False


def test_qml_channel_rack_bridge_play_fails_soft_without_engine():
    qml_mod = importlib.import_module("src.workbench_qml")
    bridge_src = inspect.getsource(qml_mod._qml_channel_rack_bridge)
    assert "except RuntimeError:" in bridge_src
    assert "Fail soft in the Qt slot" in bridge_src


def test_multi_channel_default_on_step_grid_projection():
    module = _controller_module_or_fail()
    project = _require(module, "project_channel_rack_for_qml")

    kit = _kit_with_samples()
    state = build_channel_rack_state(kit)
    assert sum(1 for ch in state.channels if ch.sample_path) == 3
    assert len(state.pattern.triggers) == 48
    projection = project(state)
    active_rows = [
        row
        for group in projection["groups"]
        for row in group["rows"]
        if any(row["steps"])
    ]
    assert len(active_rows) == 3
    for row in active_rows:
        assert len(row["steps"]) == 16
        assert all(row["steps"])


def test_controller_does_not_own_second_live_kit_or_transport():
    module = _controller_module_or_fail()
    Controller = _require(module, "ChannelRackController")
    kit = LiveKitState()
    transport = _fake_transport()
    controller = Controller(live_kit=kit, transport=transport)
    assert controller.live_kit is kit
    assert controller.transport is transport
    source = Path(module.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "WorkbenchPreviewPlayer",
        "arrangement",
        "PianoRoll",
        "mixer",
        "VST",
        "Bitwig",
    ):
        assert forbidden not in source


def test_qml_source_exposes_screen2_channel_rack_surface():
    qml = importlib.import_module("src.workbench_qml")
    source = qml.QML_SOURCE
    for token in (
        'objectName: "channelRackScreen"',
        'objectName: "channelRackStepGrid"',
        'objectName: "programNavStepSequencer"',
        'objectName: "programNavBrowser"',
        'objectName: "channelRackPlayButton"',
        'objectName: "channelRackStopButton"',
        'objectName: "addUserChannelButton"',
        "Channel Rack",
    ):
        assert token in source
    nav_block = source.split('objectName: "headerNavZone"', 1)[1].split(
        'objectName: "headerTransportZone"', 1
    )[0]
    assert "Arrangement" in nav_block
    assert 'objectName: "programNavArrangement"' in nav_block
    for forbidden in (
        "Playlist",
        "Piano Roll",
        "Mixer",
        "Screen 3",
    ):
        assert forbidden not in source


def test_qml_screen2_focus_bindings_are_local_not_global_shortcuts():
    qml = importlib.import_module("src.workbench_qml")
    source = qml.QML_SOURCE
    assert 'objectName: "channelRackScreen"' in source
    assert "Keys.onPressed" in source
    assert "context: Qt.ApplicationShortcut" not in source
    assert "Shortcut {" not in source


def test_session_wires_channel_rack_controller_without_forbidden_exports():
    session_mod = importlib.import_module("src.workbench_session")
    compose = getattr(session_mod, "compose_workbench_session")
    session = compose()
    assert hasattr(session, "channel_rack")
    controller = session.channel_rack
    assert controller.live_kit is session.live_kit
    assert controller.transport is session.transport
    for forbidden in (
        "ChannelRack",
        "Pattern",
        "PatternTrigger",
        "Screen2",
        "SequencerEngine",
    ):
        assert not hasattr(session_mod, forbidden)
        assert not hasattr(importlib.import_module("src.workbench_qml"), forbidden)


def test_qml_engine_injection_path_does_not_invent_transport():
    """Injected-adapter harnesses must fail closed for Screen-2 (#678)."""
    qml_mod = importlib.import_module("src.workbench_qml")
    engine_src = inspect.getsource(qml_mod._qml_engine)
    assert "WorkbenchTransportAdapter()" not in engine_src
    assert "channel_rack_controller = None" in engine_src


def test_beat_bar_grouping_markers_are_projected():
    module = _controller_module_or_fail()
    project = _require(module, "project_channel_rack_for_qml")
    state = build_channel_rack_state(LiveKitState())
    projection = project(state)
    markers = projection["step_markers"]
    assert len(markers) == 16
    assert markers[0]["bar_boundary"] is True
    assert markers[0]["beat_boundary"] is True
    assert markers[4]["bar_boundary"] is False
    assert markers[4]["beat_boundary"] is True
    assert markers[1]["beat_boundary"] is False


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="PySide6 Qt Quick ist in dieser Testumgebung nicht installiert.",
)
def test_qml_runtime_screen2_navigation_projection_and_step_toggle():
    """Real QML runtime acceptance for Screen-2 Channel Rack (#678).

    Uses the compose-owned ``_qml_engine`` path so Channel Rack shares the
    session transport (no second ``WorkbenchTransportAdapter``).
    """
    from PySide6.QtQuick import QQuickItem

    from src.workbench_qml import (
        Screen1QmlViewModel,
        _qml_engine,
        _settle_qml_frame,
    )

    view_model = Screen1QmlViewModel.baseline("screen1-default-3panel")
    app, engine, window = _qml_engine(view_model)
    adapter = engine._screen1_interaction_adapter
    controller = engine._screen1_channel_rack
    assert controller is not None
    audition = getattr(engine, "_screen1_preview_player", None)
    assert audition is not None
    assert controller.transport is audition.transport
    assert controller.live_kit is adapter._live_kit.state

    kit = controller.live_kit
    kit.assign("Kick + Bass", "Kick", _row("kick.wav"))
    kit.assign("Drums", "Closed Hat", _row("ch.wav"))
    kit.assign("Drums", "Open Hat", _row("oh.wav"))
    view_model.live_kit_groups = adapter._live_kit.groups

    window.show()
    _settle_qml_frame(app)
    try:
        step_nav = window.findChild(QQuickItem, "programNavStepSequencer")
        assert step_nav is not None

        channel_rack = engine.rootContext().contextProperty("channelRackModel")
        assert channel_rack is not None
        channel_rack.openChannelRack()
        app.processEvents()
        _settle_qml_frame(app)

        # Domain/controller freeze: ensure_state materializes Rack projection
        # while the legacy Screen-2 page stays hidden. Historical #908 Edit
        # bottom-Rack QML visibility assertions are released (see file header);
        # #1077 product-UI gates live in test_workbench_live_kit_edit_1077.py.
        rack_screen = window.findChild(QQuickItem, "channelRackScreen")
        browser_nav = window.findChild(QQuickItem, "programNavBrowser")
        assert rack_screen is not None and rack_screen.property("visible") is False
        assert browser_nav is not None
        assert window.property("activeScreen") == "screen1"
        assert channel_rack.bottomRackMaterialized is True
        assert channel_rack.stepCount == 16
        assert len(channel_rack.groups) >= 1
        assert adapter._live_kit.state is controller.live_kit

        before = controller.state
        assert before is not None
        channel_rack.toggleStep("ch_kick", 0)
        app.processEvents()
        assert controller.state is not before
        assert Trigger(channel_id="ch_kick", position=Fraction(0, 4)) not in controller.state.pattern.triggers

        channel_rack.addUserChannel()
        app.processEvents()
        user_channels = [
            ch
            for ch in controller.state.channels
            if ch.channel_id.startswith(USER_CHANNEL_ID_PREFIX)
        ]
        assert len(user_channels) == 1
        assert user_channels[0].live_kit_group is None

        pattern_triggers = controller.state.pattern.triggers
        # returnToScreen1 remains a no-op-safe legacy slot while already on screen1.
        channel_rack.returnToScreen1()
        app.processEvents()
        _settle_qml_frame(app)
        assert window.property("activeScreen") == "screen1"
        assert kit.assignment_for("Kick + Bass", "Kick") is not None
        assert controller.state.pattern.triggers == pattern_triggers
        workspace = window.findChild(QQuickItem, "workspaceRow")
        assert workspace is not None and workspace.property("visible") is True
    finally:
        engine.deleteLater()
        app.processEvents()

# --- #806 Live Kit late-assignment via ChannelRackController -----------------


def _kick_trigger_count(state) -> int:
    return sum(1 for t in state.pattern.triggers if t.channel_id == "ch_kick")


def test_late_live_kit_assign_after_empty_screen2_seeds_default_on():
    """empty kit → Screen 2 → assign → re-enter → path + DEFAULT_ON (#806)."""
    module = _controller_module_or_fail()
    Controller = _require(module, "ChannelRackController")

    kit = LiveKitState()
    controller = Controller(live_kit=kit, transport=_fake_transport())
    controller.enter_screen2()
    assert next(ch for ch in controller.state.channels if ch.channel_id == "ch_kick").sample_path is None
    assert _kick_trigger_count(controller.state) == 0

    controller.leave_screen2()
    kit.assign("Kick + Bass", "Kick", _row("kick.wav", path="synthetic/kick_late.wav"))
    controller.enter_screen2()

    kick = next(ch for ch in controller.state.channels if ch.channel_id == "ch_kick")
    assert kick.sample_path == "synthetic/kick_late.wav"
    assert _kick_trigger_count(controller.state) == 16
    assert all(
        Trigger(channel_id="ch_kick", position=Fraction(i, 4)) in controller.state.pattern.triggers
        for i in range(16)
    )


def test_late_assign_does_not_reset_other_programmed_channels():
    """Isolation: only the newly filled channel is healed (#806)."""
    module = _controller_module_or_fail()
    Controller = _require(module, "ChannelRackController")

    kit = LiveKitState()
    kit.assign("Drums", "Closed Hat", _row("ch.wav", path="synthetic/ch.wav"))
    controller = Controller(live_kit=kit, transport=_fake_transport())
    controller.enter_screen2()
    controller.toggle_step("ch_closed_hat", 0)
    controller.toggle_step("ch_closed_hat", 1)
    hat_before = tuple(
        t for t in controller.state.pattern.triggers if t.channel_id == "ch_closed_hat"
    )
    assert len(hat_before) == 14

    controller.leave_screen2()
    kit.assign("Kick + Bass", "Kick", _row("kick.wav", path="synthetic/kick.wav"))
    controller.enter_screen2()

    assert _kick_trigger_count(controller.state) == 16
    hat_after = tuple(
        t for t in controller.state.pattern.triggers if t.channel_id == "ch_closed_hat"
    )
    assert hat_after == hat_before


def test_sample_replacement_preserves_exact_user_step_pattern():
    """Replace sample on programmed channel → user steps preserved exactly (#806)."""
    module = _controller_module_or_fail()
    Controller = _require(module, "ChannelRackController")

    kit = LiveKitState()
    kit.assign("Kick + Bass", "Kick", _row("kick_a.wav", path="synthetic/kick_a.wav"))
    controller = Controller(live_kit=kit, transport=_fake_transport())
    controller.enter_screen2()
    for step in (0, 4, 8, 12):
        controller.toggle_step("ch_kick", step)
    expected = tuple(
        t for t in controller.state.pattern.triggers if t.channel_id == "ch_kick"
    )
    assert len(expected) == 12

    controller.leave_screen2()
    kit.assign("Kick + Bass", "Kick", _row("kick_b.wav", path="synthetic/kick_b.wav"))
    controller.enter_screen2()

    kick = next(ch for ch in controller.state.channels if ch.channel_id == "ch_kick")
    assert kick.sample_path == "synthetic/kick_b.wav"
    assert (
        tuple(t for t in controller.state.pattern.triggers if t.channel_id == "ch_kick")
        == expected
    )


def test_clear_assignment_strips_channel_triggers_fail_closed():
    """Clear Live Kit slot → sample_path None and triggers removed (#806)."""
    module = _controller_module_or_fail()
    Controller = _require(module, "ChannelRackController")

    kit = _kit_with_samples()
    controller = Controller(live_kit=kit, transport=_fake_transport())
    controller.enter_screen2()
    assert _kick_trigger_count(controller.state) == 16

    controller.leave_screen2()
    kit._assignments["Kick + Bass"]["Kick"] = None
    controller.enter_screen2()

    kick = next(ch for ch in controller.state.channels if ch.channel_id == "ch_kick")
    assert kick.sample_path is None
    assert _kick_trigger_count(controller.state) == 0
    # Sibling channels remain programmed.
    assert (
        sum(1 for t in controller.state.pattern.triggers if t.channel_id == "ch_closed_hat")
        == 16
    )


# --- #808 assign selected sample to user channel -----------------------------


def test_controller_assign_user_channel_sample_empty_to_assigned():
    module = _controller_module_or_fail()
    Controller = _require(module, "ChannelRackController")
    project = _require(module, "project_channel_rack_for_qml")

    controller = Controller(live_kit=LiveKitState(), transport=_fake_transport())
    controller.enter_screen2()
    controller.add_user_channel()
    user = next(
        ch for ch in controller.state.channels if ch.channel_id.startswith(USER_CHANNEL_ID_PREFIX)
    )
    assert user.sample_path is None

    after = controller.assign_user_channel_sample(user.channel_id, "synthetic/assigned.wav")
    assigned = next(ch for ch in after.channels if ch.channel_id == user.channel_id)
    assert assigned.sample_path == "synthetic/assigned.wav"
    assert assigned.live_kit_group is None
    assert assigned.live_kit_slot is None
    assert sum(1 for t in after.pattern.triggers if t.channel_id == user.channel_id) == 16

    projection = project(after)
    user_row = next(
        row
        for group in projection["groups"]
        for row in group["rows"]
        if row["channel_id"] == user.channel_id
    )
    assert user_row["sample_path"] == "synthetic/assigned.wav"
    assert user_row["sample_label"] == "assigned.wav"
    assert user_row["is_user_channel"] is True
    assert user_row["steps"] == [True] * 16


def test_controller_assign_rejects_live_kit_and_empty_path():
    module = _controller_module_or_fail()
    Controller = _require(module, "ChannelRackController")
    controller = Controller(live_kit=LiveKitState(), transport=_fake_transport())
    controller.enter_screen2()
    with pytest.raises(ValueError, match="Live Kit"):
        controller.assign_user_channel_sample("ch_kick", "synthetic/x.wav")
    controller.add_user_channel()
    user_id = next(
        ch.channel_id
        for ch in controller.state.channels
        if ch.channel_id.startswith(USER_CHANNEL_ID_PREFIX)
    )
    with pytest.raises(ValueError, match="sample_path"):
        controller.assign_user_channel_sample(user_id, "  ")


def test_unclassified_user_channel_persists_steps_but_does_not_play(tmp_path):
    """TEST_CONTRACT_FIX: #920 excludes unclassified user rows from Rack Play."""
    from tests.audio_fixtures import write_sine_wav

    module = _controller_module_or_fail()
    Controller = _require(module, "ChannelRackController")

    wav = write_sine_wav(
        tmp_path / "user_assign.wav",
        duration_sec=0.05,
        frequency_hz=440.0,
        sr=48_000,
    )
    engine = MagicMock()
    created: list[object] = []

    def create_voice(cfg):
        created.append(cfg)
        return getattr(cfg, "id", len(created))

    engine.create_voice.side_effect = create_voice
    engine.schedule_voice_start = MagicMock()
    engine.get_snapshot.return_value = SimpleNamespace(
        total_voice_count=0,
        voice_ids=(),
        voice_states=(),
    )
    engine.stop_voice = MagicMock()
    engine.remove_voice = MagicMock()

    transport = _fake_transport(sample_rate=48_000, engine=engine)
    controller = Controller(live_kit=LiveKitState(), transport=transport)
    controller.enter_screen2()
    controller.add_user_channel()
    user_id = next(
        ch.channel_id
        for ch in controller.state.channels
        if ch.channel_id.startswith(USER_CHANNEL_ID_PREFIX)
    )
    controller.assign_user_channel_sample(user_id, str(wav))
    # Retain only step 0: persistence/editing is non-destructive even though
    # this user channel has no explicit classification authority for playback.
    for step in range(1, 16):
        controller.toggle_step(user_id, step)

    handle = controller.play()
    assert handle is not None
    assert handle.scheduled_count == 0
    assert handle.skipped_missing_source_count == 0
    assert created == []
    assert controller.is_playing is False
    assert Trigger(channel_id=user_id, position=Fraction(0, 1)) in (
        controller.state.pattern.triggers
    )


def test_qml_source_exposes_assign_selected_affordance_for_user_rows():
    qml = importlib.import_module("src.workbench_qml")
    source = qml.QML_SOURCE
    assert "assignSelectedSample" in source
    assert "Assign selected" in source
    assert "is_user_channel" in source


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="PySide6 Qt Quick ist in dieser Testumgebung nicht installiert.",
)
def test_qml_channel_rack_bridge_assign_selected_uses_browser_selection():
    qml_mod = importlib.import_module("src.workbench_qml")
    module = _controller_module_or_fail()
    Controller = _require(module, "ChannelRackController")

    controller = Controller(live_kit=LiveKitState(), transport=_fake_transport())
    controller.enter_screen2()
    controller.add_user_channel()
    user_id = next(
        ch.channel_id
        for ch in controller.state.channels
        if ch.channel_id.startswith(USER_CHANNEL_ID_PREFIX)
    )

    selected = {"path": "synthetic/from_browser.wav"}

    def resolve_selected() -> str | None:
        return selected["path"]

    bridge = qml_mod._qml_channel_rack_bridge(
        controller,
        resolve_selected_sample_path=resolve_selected,
    )
    assert bridge.hasSelectedSample is True
    bridge.assignSelectedSample(user_id)
    user = next(ch for ch in controller.state.channels if ch.channel_id == user_id)
    assert user.sample_path == "synthetic/from_browser.wav"
    assert sum(1 for t in controller.state.pattern.triggers if t.channel_id == user_id) == 16

    # fail-soft: no selection → no mutation
    before = controller.state
    selected["path"] = None
    bridge.refresh()
    assert bridge.hasSelectedSample is False
    bridge.assignSelectedSample(user_id)
    assert controller.state is before
    assert (
        next(ch for ch in controller.state.channels if ch.channel_id == user_id).sample_path
        == "synthetic/from_browser.wav"
    )


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="PySide6 Qt Quick ist in dieser Testumgebung nicht installiert.",
)
def test_qml_runtime_add_assign_selected_toggle_play(tmp_path):
    """Offscreen: browser select → Screen 2 → add → assign → toggle → play (#808)."""
    from PySide6.QtQuick import QQuickItem

    from tests.audio_fixtures import write_sine_wav
    from src.workbench_qml import (
        Screen1QmlViewModel,
        _qml_engine,
        _qml_row,
        _settle_qml_frame,
    )

    wav = write_sine_wav(
        tmp_path / "browser_pick.wav",
        duration_sec=0.05,
        frequency_hz=330.0,
        sr=48_000,
    )
    view_model = Screen1QmlViewModel.baseline("screen1-default-3panel")
    # Replace baseline rows with a real synthetic path for assignment.
    pick_row = _qml_row(_row("browser_pick.wav", path=str(wav)))
    view_model._browser_rows_all = (pick_row,)
    view_model.browser_rows = view_model._browser_rows_all
    view_model.selected_browser_index = 0

    app, engine, window = _qml_engine(view_model)
    controller = engine._screen1_channel_rack
    assert controller is not None
    channel_rack = engine.rootContext().contextProperty("channelRackModel")

    window.show()
    _settle_qml_frame(app)
    try:
        channel_rack.openChannelRack()
        app.processEvents()
        _settle_qml_frame(app)
        assert window.property("activeScreen") == "screen1"

        channel_rack.addUserChannel()
        app.processEvents()
        user = next(
            ch
            for ch in controller.state.channels
            if ch.channel_id.startswith(USER_CHANNEL_ID_PREFIX)
        )
        assert user.sample_path in (None, "")

        assert channel_rack.hasSelectedSample is True
        channel_rack.assignSelectedSample(user.channel_id)
        app.processEvents()
        assigned = next(ch for ch in controller.state.channels if ch.channel_id == user.channel_id)
        assert assigned.sample_path == str(wav)
        assert sum(
            1 for t in controller.state.pattern.triggers if t.channel_id == user.channel_id
        ) == 16

        channel_rack.toggleStep(user.channel_id, 0)
        app.processEvents()
        assert Trigger(channel_id=user.channel_id, position=Fraction(0, 4)) not in (
            controller.state.pattern.triggers
        )

        # Play: fail-soft without native engine; with engine, Screen-2 loops until Stop (#810).
        channel_rack.play()
        app.processEvents()
        transport = controller.transport
        native_engine = None
        if hasattr(transport, "get_native_engine"):
            native_engine = transport.get_native_engine()
        if native_engine is None:
            assert controller.is_playing is False
        else:
            assert controller.is_playing is True
            channel_rack.stop()
            app.processEvents()
            assert controller.is_playing is False

        rack_screen = window.findChild(QQuickItem, "channelRackScreen")
        assert rack_screen is not None and rack_screen.property("visible") is False
        # Domain ops remain reachable without requiring Edit bottom-Rack geometry
        # (historical #908 QML product placement released; see file header).
        assert controller.state is not None
        assert len(controller.state.channels) >= 1
    finally:
        engine.deleteLater()
        app.processEvents()
