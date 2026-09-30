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
        'objectName: "openChannelRackButton"',
        'objectName: "returnToScreen1Button"',
        'objectName: "channelRackPlayButton"',
        'objectName: "channelRackStopButton"',
        'objectName: "addUserChannelButton"',
        "Channel Rack",
    ):
        assert token in source
    for forbidden in (
        "Arrangement",
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
    """Real QML runtime acceptance for Screen-2 Channel Rack (#678)."""
    from PySide6.QtQuick import QQuickItem

    from src.workbench_qml import (
        LiveKitPresenter,
        Screen1QmlInteractionAdapter,
        Screen1QmlViewModel,
        _qml_engine,
        _settle_qml_frame,
    )

    kit = _kit_with_samples()
    presenter = LiveKitPresenter(state=kit)
    view_model = Screen1QmlViewModel.baseline("screen1-default-3panel")
    view_model.live_kit_groups = presenter.groups
    adapter = Screen1QmlInteractionAdapter(view_model=view_model, live_kit=presenter)
    app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    window.show()
    _settle_qml_frame(app)
    try:
        open_btn = window.findChild(QQuickItem, "openChannelRackButton")
        assert open_btn is not None
        assert open_btn.property("visible") is True

        channel_rack = engine.rootContext().contextProperty("channelRackModel")
        assert channel_rack is not None
        channel_rack.openChannelRack()
        app.processEvents()
        _settle_qml_frame(app)

        rack_screen = window.findChild(QQuickItem, "channelRackScreen")
        step_grid = window.findChild(QQuickItem, "channelRackStepGrid")
        play_btn = window.findChild(QQuickItem, "channelRackPlayButton")
        stop_btn = window.findChild(QQuickItem, "channelRackStopButton")
        add_btn = window.findChild(QQuickItem, "addUserChannelButton")
        back_btn = window.findChild(QQuickItem, "returnToScreen1Button")
        assert rack_screen is not None and rack_screen.property("visible") is True
        assert step_grid is not None
        assert play_btn is not None and stop_btn is not None and add_btn is not None
        assert back_btn is not None and back_btn.property("visible") is True
        assert window.property("activeScreen") == "screen2"
        assert channel_rack.stepCount == 16
        assert len(channel_rack.groups) >= 4

        controller = engine._screen1_channel_rack
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
