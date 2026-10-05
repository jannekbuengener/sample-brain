"""Frozen acceptance for R&D Slice 9 — guarded GestureRack apply (#680 / #921).

Docs authority: docs/GESTURE_RACK_CONTROLLER_APPLY_RND_SLICE9.md

Synthetic fixtures only — no audio binaries, no private catalogs, no QML workflow.
"""

from __future__ import annotations

import copy
import inspect
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from src.channel_rack import ChannelRackState
from src.gesture_pattern_core_composition import GesturePatternCoreComposition
from src.gesture_rack_integration import (
    GestureRackIntegrationPlan,
    plan_gesture_rack_integration,
)
from src.pattern_core import Channel, Pattern, Trigger
from src.session_grid import SessionTransport
from src.workbench_channel_rack import ChannelRackController
from src.workbench_controller import WorkbenchRow
from src.workbench_feature_settings import (
    WorkbenchFeatureSettings,
    load_workbench_feature_settings,
    save_workbench_feature_settings,
)
from src.workbench_live_kit import LiveKitState
from src.workbench_session import compose_workbench_session
from src.workbench_session_store import (
    PERSISTENCE_STATUS_AUTOSAVE_FAILED,
    workbench_session_path,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _live_kit_channel(
    channel_id: str,
    group: str,
    slot: str,
    *,
    sample_path: str | None = "kit.wav",
) -> Channel:
    return Channel(
        channel_id=channel_id,
        live_kit_group=group,
        live_kit_slot=slot,
        sample_path=sample_path,
    )


def _user_channel(channel_id: str, *, sample_path: str = "user.wav") -> Channel:
    return Channel(
        channel_id=channel_id,
        live_kit_group=None,
        live_kit_slot=None,
        sample_path=sample_path,
    )


def _pattern(
    pattern_id: str,
    *,
    length: Fraction = Fraction(4, 1),
    triggers: tuple[Trigger, ...] = (),
) -> Pattern:
    return Pattern(
        pattern_id=pattern_id,
        length_quarter_notes=length,
        triggers=triggers,
    )


def _base_state(
    *,
    channels: tuple[Channel, ...] | None = None,
    pattern: Pattern | None = None,
    step_count: int = 16,
) -> ChannelRackState:
    if channels is None:
        channels = (
            _live_kit_channel("ch_kick", "Kick + Bass", "Kick"),
            _live_kit_channel("ch_bass", "Kick + Bass", "Bass", sample_path=None),
            _user_channel("ch_user_9", sample_path="existing.wav"),
        )
    if pattern is None:
        pattern = _pattern(
            "screen2-main",
            triggers=(
                Trigger(channel_id="ch_kick", position=Fraction(0, 4)),
                Trigger(channel_id="ch_kick", position=Fraction(4, 4)),
                Trigger(channel_id="ch_user_9", position=Fraction(2, 4)),
            ),
        )
    return ChannelRackState(
        channels=channels,
        pattern=pattern,
        step_count=step_count,
    )


def _composition(
    *,
    channels: tuple[Channel, ...] | None = None,
    pattern: Pattern | None = None,
) -> GesturePatternCoreComposition:
    if channels is None:
        channels = (_user_channel("ch_user_1", sample_path="gesture_a.wav"),)
    if pattern is None:
        pattern = _pattern(
            "gesture-pat-1",
            length=Fraction(8, 1),
            triggers=(
                Trigger(channel_id="ch_user_1", position=Fraction(0, 4)),
                Trigger(channel_id="ch_user_1", position=Fraction(1, 4)),
                Trigger(channel_id="ch_user_1", position=Fraction(1, 3)),
            ),
        )
    return GesturePatternCoreComposition(channels=channels, pattern=pattern)


def _plan(
    base: ChannelRackState | None = None,
    composition: GesturePatternCoreComposition | None = None,
    *,
    allow_pattern_replacement: bool = True,
) -> GestureRackIntegrationPlan:
    return plan_gesture_rack_integration(
        base if base is not None else _base_state(),
        composition if composition is not None else _composition(),
        allow_pattern_replacement=allow_pattern_replacement,
    )


def _controller(
    *,
    state: ChannelRackState | None = None,
    on_musical_state_changed=None,
    on_claim_audio_focus=None,
    on_release_to_screen1=None,
) -> ChannelRackController:
    transport = SessionTransport(sample_rate=48_000, bpm=120.0)
    controller = ChannelRackController(
        live_kit=LiveKitState(),
        transport=transport,
        on_musical_state_changed=on_musical_state_changed,
        on_claim_audio_focus=on_claim_audio_focus,
        on_release_to_screen1=on_release_to_screen1,
    )
    if state is not None:
        controller.restore_state(state)
    return controller


def _expected_target(plan: GestureRackIntegrationPlan) -> ChannelRackState:
    return ChannelRackState(
        channels=plan.target_channels,
        pattern=plan.target_pattern,
        step_count=plan.target_step_count,
    )


def _apply(controller: ChannelRackController, plan, *, feature_enabled: bool):
    return controller.apply_gesture_integration_plan(
        plan, feature_enabled=feature_enabled
    )


# ---------------------------------------------------------------------------
# A. Happy path
# ---------------------------------------------------------------------------


def test_a1_ready_enabled_matching_base_applies_exact_target():
    base = _base_state()
    plan = _plan(base)
    assert plan.ready_for_apply is True
    controller = _controller(state=base)

    result = _apply(controller, plan, feature_enabled=True)

    expected = _expected_target(plan)
    assert result == expected
    assert controller.state == expected
    assert controller.state is result


def test_a2_target_equals_plan_fields_no_incumbent_merge():
    base = _base_state()
    composition = _composition()
    plan = _plan(base, composition)
    controller = _controller(state=base)

    result = _apply(controller, plan, feature_enabled=True)

    assert result.channels == plan.target_channels
    assert result.pattern == plan.target_pattern
    assert result.step_count == plan.target_step_count
    for trigger in base.pattern.triggers:
        assert trigger not in result.pattern.triggers


# ---------------------------------------------------------------------------
# B. Feature gate
# ---------------------------------------------------------------------------


def test_b1_disabled_zero_mutation_stop_observer_focus():
    base = _base_state()
    plan = _plan(base)
    observers: list[str] = []
    claims: list[str] = []
    releases: list[str] = []
    controller = _controller(
        state=base,
        on_musical_state_changed=lambda: observers.append("obs"),
        on_claim_audio_focus=lambda: claims.append("claim"),
        on_release_to_screen1=lambda: releases.append("release"),
    )
    original = controller.state

    with mock.patch.object(controller, "stop", wraps=controller.stop) as stop_spy:
        with pytest.raises(ValueError):
            _apply(controller, plan, feature_enabled=False)

    assert controller.state == original
    assert controller.state is original
    assert stop_spy.call_count == 0
    assert observers == []
    assert claims == []
    assert releases == []


def test_b2_settings_reload_false_still_blocked(tmp_path: Path):
    save_workbench_feature_settings(
        WorkbenchFeatureSettings(gesture_rack_apply_enabled=False),
        state_dir=tmp_path,
    )
    loaded = load_workbench_feature_settings(state_dir=tmp_path)
    assert loaded.gesture_rack_apply_enabled is False

    base = _base_state()
    plan = _plan(base)
    controller = _controller(state=base)
    original = controller.state

    with mock.patch.object(controller, "stop", wraps=controller.stop) as stop_spy:
        with pytest.raises(ValueError):
            _apply(controller, plan, feature_enabled=loaded.gesture_rack_apply_enabled)

    assert controller.state is original
    assert stop_spy.call_count == 0


def test_b3_settings_true_permits_capability(tmp_path: Path):
    save_workbench_feature_settings(
        WorkbenchFeatureSettings(gesture_rack_apply_enabled=True),
        state_dir=tmp_path,
    )
    enabled = load_workbench_feature_settings(
        state_dir=tmp_path
    ).gesture_rack_apply_enabled
    assert enabled is True

    base = _base_state()
    plan = _plan(base)
    controller = _controller(state=base)
    result = _apply(controller, plan, feature_enabled=enabled)
    assert result == _expected_target(plan)


# ---------------------------------------------------------------------------
# C. Stale plan
# ---------------------------------------------------------------------------


def test_c1_stale_base_zero_side_effects():
    base = _base_state()
    plan = _plan(base)
    mutated = ChannelRackState(
        channels=base.channels,
        pattern=_pattern(
            "screen2-main",
            triggers=(Trigger(channel_id="ch_kick", position=Fraction(1, 4)),),
        ),
        step_count=base.step_count,
    )
    assert mutated != plan.expected_base_state
    observers: list[str] = []
    controller = _controller(
        state=mutated,
        on_musical_state_changed=lambda: observers.append("obs"),
    )
    original = controller.state

    with mock.patch.object(controller, "stop", wraps=controller.stop) as stop_spy:
        with pytest.raises(ValueError):
            _apply(controller, plan, feature_enabled=True)

    assert controller.state is original
    assert stop_spy.call_count == 0
    assert observers == []


# ---------------------------------------------------------------------------
# D. Invalid plan / target
# ---------------------------------------------------------------------------


def test_d1_not_ready_zero_side_effects():
    base = _base_state()
    plan = _plan(base, allow_pattern_replacement=False)
    assert plan.ready_for_apply is False
    observers: list[str] = []
    controller = _controller(
        state=base,
        on_musical_state_changed=lambda: observers.append("obs"),
    )
    original = controller.state

    with mock.patch.object(controller, "stop", wraps=controller.stop) as stop_spy:
        with pytest.raises(ValueError):
            _apply(controller, plan, feature_enabled=True)

    assert controller.state is original
    assert stop_spy.call_count == 0
    assert observers == []


def test_d2_state_none_no_implicit_materialization():
    plan = _plan(_base_state())
    controller = _controller(state=None)
    assert controller.state is None

    with mock.patch.object(
        controller, "ensure_state", wraps=controller.ensure_state
    ) as ensure_spy:
        with mock.patch.object(controller, "stop", wraps=controller.stop) as stop_spy:
            with pytest.raises(RuntimeError):
                _apply(controller, plan, feature_enabled=True)

    assert controller.state is None
    assert ensure_spy.call_count == 0
    assert stop_spy.call_count == 0


def test_d3_invalid_membership_fails_before_stop():
    base = _base_state()
    plan = GestureRackIntegrationPlan(
        expected_base_state=base,
        target_channels=base.channels,
        target_pattern=_pattern(
            "bad",
            length=Fraction(4, 1),
            triggers=(Trigger(channel_id="phantom", position=Fraction(0, 1)),),
        ),
        target_step_count=16,
        appended_channel_ids=(),
        replaced_pattern_id="bad",
        replaced_trigger_count=1,
        off_grid_event_count=0,
        ready_for_apply=True,
    )
    controller = _controller(state=base)
    controller._playing = True
    original = controller.state

    with mock.patch.object(controller, "stop", wraps=controller.stop) as stop_spy:
        with pytest.raises(ValueError):
            _apply(controller, plan, feature_enabled=True)

    assert controller.state is original
    assert controller.is_playing is True
    assert stop_spy.call_count == 0


def test_d4_invalid_grid_span_fails_before_stop():
    base = _base_state(step_count=16)
    short = _pattern(
        "too-short",
        length=Fraction(2, 1),  # < Fraction(16, 4) == 4
        triggers=(Trigger(channel_id="ch_kick", position=Fraction(0, 1)),),
    )
    plan = GestureRackIntegrationPlan(
        expected_base_state=base,
        target_channels=base.channels,
        target_pattern=short,
        target_step_count=16,
        appended_channel_ids=(),
        replaced_pattern_id="too-short",
        replaced_trigger_count=1,
        off_grid_event_count=0,
        ready_for_apply=True,
    )
    controller = _controller(state=base)
    controller._playing = True
    original = controller.state

    with mock.patch.object(controller, "stop", wraps=controller.stop) as stop_spy:
        with pytest.raises(ValueError):
            _apply(controller, plan, feature_enabled=True)

    assert controller.state is original
    assert controller.is_playing is True
    assert stop_spy.call_count == 0


def test_d5_wrong_plan_type_fails_closed():
    controller = _controller(state=_base_state())
    original = controller.state
    with mock.patch.object(controller, "stop", wraps=controller.stop) as stop_spy:
        with pytest.raises(TypeError):
            _apply(controller, SimpleNamespace(ready_for_apply=True), feature_enabled=True)
    assert controller.state is original
    assert stop_spy.call_count == 0


# ---------------------------------------------------------------------------
# E. Playback safety
# ---------------------------------------------------------------------------


def test_e1_valid_while_stopped():
    base = _base_state()
    plan = _plan(base)
    claims: list[str] = []
    controller = _controller(
        state=base,
        on_claim_audio_focus=lambda: claims.append("claim"),
    )
    assert controller.is_playing is False

    with mock.patch.object(controller, "stop", wraps=controller.stop) as stop_spy:
        result = _apply(controller, plan, feature_enabled=True)

    assert result == _expected_target(plan)
    assert controller.is_playing is False
    assert controller._loop_active is False
    assert stop_spy.call_count == 1
    assert claims == []


def test_e2_valid_while_playing_stops_first():
    base = _base_state()
    plan = _plan(base)
    controller = _controller(state=base)
    controller._playing = True
    controller._loop_active = True
    fake_player = mock.Mock()
    fake_player.stop = mock.Mock()
    controller._play_handle = SimpleNamespace(
        player=fake_player,
        scheduled_count=0,
    )

    order: list[str] = []
    real_stop = controller.stop

    def tracking_stop() -> None:
        order.append("stop")
        real_stop()

    original_notify = controller._notify_musical_state_changed

    def tracking_notify() -> None:
        order.append("notify")
        assert controller.state == _expected_target(plan)
        original_notify()

    with mock.patch.object(controller, "stop", side_effect=tracking_stop):
        with mock.patch.object(
            controller, "_notify_musical_state_changed", side_effect=tracking_notify
        ):
            result = _apply(controller, plan, feature_enabled=True)

    assert result == _expected_target(plan)
    assert controller.is_playing is False
    assert controller._loop_active is False
    assert controller._play_handle is None
    assert order == ["stop", "notify"]


# ---------------------------------------------------------------------------
# F. Observer / autosave
# ---------------------------------------------------------------------------


def test_f1_observer_exactly_once_on_success():
    base = _base_state()
    plan = _plan(base)
    observers: list[str] = []
    controller = _controller(
        state=base,
        on_musical_state_changed=lambda: observers.append("obs"),
    )
    _apply(controller, plan, feature_enabled=True)
    assert observers == ["obs"]


def _row(name: str, path: str) -> WorkbenchRow:
    return WorkbenchRow(
        display_name=name,
        relative_path=Path(path).name,
        path=path,
        bpm=None,
        key=None,
        key_conf=None,
        loudness=None,
        brightness=None,
        sample_class=None,
        pred_type=None,
        status="ok",
        details={},
    )


def test_f2_session_autosave_once_coherent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import src.workbench_session as session_mod

    kick = str(tmp_path / "kick.wav")
    Path(kick).write_bytes(b"RIFF")
    session = compose_workbench_session(state_dir=tmp_path)
    session.live_kit.assign("Kick + Bass", "Kick", _row("kick.wav", kick))
    base = session.channel_rack.ensure_state()
    plan = _plan(base)

    save_calls: list[object] = []
    real_save = session_mod.save_workbench_session_snapshot

    def counting_save(snapshot, *, state_dir=None, env=None):
        save_calls.append(snapshot)
        return real_save(snapshot, state_dir=state_dir, env=env)

    monkeypatch.setattr(session_mod, "save_workbench_session_snapshot", counting_save)

    before = len(save_calls)
    result = session.channel_rack.apply_gesture_integration_plan(
        plan, feature_enabled=True
    )
    assert len(save_calls) == before + 1
    saved = save_calls[-1]
    assert result == session.channel_rack.state
    assert saved.channel_rack is not None
    assert saved.channel_rack.pattern == plan.target_pattern
    assert saved.channel_rack.step_count == plan.target_step_count
    # Appended gesture channels are present in the saved musical snapshot.
    saved_ids = {ch.channel_id for ch in saved.channel_rack.channels}
    for channel_id in plan.appended_channel_ids:
        assert channel_id in saved_ids
    session.transport.close()


def test_f3_save_failure_keeps_in_memory_honesty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from src import workbench_session_store as store_mod

    kick = str(tmp_path / "kick.wav")
    Path(kick).write_bytes(b"RIFF")
    session = compose_workbench_session(state_dir=tmp_path)
    session.live_kit.assign("Kick + Bass", "Kick", _row("kick.wav", kick))
    session.transport.close()
    session = compose_workbench_session(state_dir=tmp_path)
    base = session.channel_rack.ensure_state()
    plan = _plan(base)
    path = workbench_session_path(state_dir=tmp_path)
    previous = path.read_text(encoding="utf-8")

    def boom(src, dst):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(store_mod.os, "replace", boom)

    result = session.channel_rack.apply_gesture_integration_plan(
        plan, feature_enabled=True
    )
    assert result == _expected_target(plan)
    assert session.channel_rack.state == result
    assert session.persistence_status == PERSISTENCE_STATUS_AUTOSAVE_FAILED
    assert path.read_text(encoding="utf-8") == previous
    session.transport.close()


# ---------------------------------------------------------------------------
# G. Immutability / determinism
# ---------------------------------------------------------------------------


def test_g1_plan_object_unchanged():
    base = _base_state()
    plan = _plan(base)
    before = copy.deepcopy(plan)
    controller = _controller(state=base)
    _apply(controller, plan, feature_enabled=True)
    assert plan == before


def test_g2_fraction_timing_preserved():
    base = _base_state()
    composition = _composition(
        pattern=_pattern(
            "gesture-pat-1",
            length=Fraction(8, 1),
            triggers=(
                Trigger(channel_id="ch_user_1", position=Fraction(1, 3)),
                Trigger(channel_id="ch_user_1", position=Fraction(5, 7)),
            ),
        )
    )
    plan = _plan(base, composition)
    controller = _controller(state=base)
    result = _apply(controller, plan, feature_enabled=True)
    assert result.pattern.triggers[0].position == Fraction(1, 3)
    assert result.pattern.triggers[1].position == Fraction(5, 7)
    assert type(result.pattern.triggers[0].position) is Fraction


def test_g3_no_id_realloc_and_no_default_on():
    base = _base_state()
    composition = _composition()
    plan = _plan(base, composition)
    controller = _controller(state=base)

    with mock.patch(
        "src.channel_rack.allocate_user_channel_id",
        side_effect=AssertionError("must not reallocate"),
    ):
        with mock.patch(
            "src.channel_rack.add_user_channel",
            side_effect=AssertionError("must not add_user_channel"),
        ):
            result = _apply(controller, plan, feature_enabled=True)

    assert result.channels[-1].channel_id == plan.appended_channel_ids[0]
    appended = result.channels[-1]
    assert appended.live_kit_group is None
    assert appended.live_kit_slot is None
    # No DEFAULT_ON 16-step seed for gesture channel — only composition triggers.
    appended_triggers = [
        t for t in result.pattern.triggers if t.channel_id == appended.channel_id
    ]
    assert len(appended_triggers) == len(composition.pattern.triggers)
    assert len(appended_triggers) != 16


# ---------------------------------------------------------------------------
# H. Focus / restore_state anti-patterns
# ---------------------------------------------------------------------------


def test_h1_no_audio_focus_on_success_or_failure():
    base = _base_state()
    plan = _plan(base)
    claims: list[str] = []
    releases: list[str] = []
    controller = _controller(
        state=base,
        on_claim_audio_focus=lambda: claims.append("claim"),
        on_release_to_screen1=lambda: releases.append("release"),
    )
    _apply(controller, plan, feature_enabled=True)
    with pytest.raises(ValueError):
        _apply(controller, plan, feature_enabled=False)
    assert claims == []
    assert releases == []


def test_h2_success_notifies_unlike_restore_state():
    """Prove apply is not restore_state: restore never notifies; apply must."""
    base = _base_state()
    plan = _plan(base)
    observers: list[str] = []
    controller = _controller(
        state=base,
        on_musical_state_changed=lambda: observers.append("obs"),
    )
    # restore_state clears notify path effect for compose
    controller.restore_state(base)
    assert observers == []
    _apply(controller, plan, feature_enabled=True)
    assert observers == ["obs"]


def test_h3_public_signature_kwonly_feature_enabled():
    sig = inspect.signature(ChannelRackController.apply_gesture_integration_plan)
    params = list(sig.parameters)
    assert params[0] == "self"
    assert params[1] == "plan"
    assert "feature_enabled" in sig.parameters
    assert sig.parameters["feature_enabled"].kind is inspect.Parameter.KEYWORD_ONLY
