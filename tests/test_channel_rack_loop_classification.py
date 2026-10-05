"""#926 classification-aware Channel Rack seed / reconcile / point-trigger filter."""

from __future__ import annotations

from fractions import Fraction

import pytest

from src.channel_rack import (
    ChannelRackState,
    DEFAULT_STEP_COUNT,
    build_channel_rack_state,
    classification_kind,
    filter_pattern_for_point_trigger_playback,
    is_explicit_loop,
    is_point_trigger_safe,
    normalize_sample_class,
    point_trigger_eligible_channel_ids,
    reconcile_live_kit_sample_assignments,
    sample_class_for_channel,
)
from src.pattern_core import CHANNEL_ID_BY_LIVE_KIT_SLOT, Channel, Pattern, Trigger
from src.workbench_controller import WorkbenchRow
from src.workbench_live_kit import LiveKitState


def _row(
    name: str,
    path: str,
    *,
    sample_class: str | None,
    bpm: float | None = 120.0,
) -> WorkbenchRow:
    return WorkbenchRow(
        display_name=name,
        relative_path=path,
        path=path,
        bpm=bpm,
        key="Cmaj",
        key_conf=0.9,
        loudness=-18.0,
        brightness=2400.0,
        sample_class=sample_class,
        pred_type="Kick",
        status="ok",
        details={"source": "synthetic"},
    )


def _triggers_for(state: ChannelRackState, channel_id: str) -> tuple[Trigger, ...]:
    return tuple(t for t in state.pattern.triggers if t.channel_id == channel_id)


def test_normalize_and_classification_kind_helpers():
    assert normalize_sample_class("One-Shot") == "one_shot"
    assert classification_kind("oneshot") == "oneshot"
    assert classification_kind("one_shot") == "oneshot"
    assert classification_kind("loop") == "loop"
    assert classification_kind(None) == "ambiguous"
    assert classification_kind("pad") == "ambiguous"
    assert is_point_trigger_safe("oneshot")
    assert is_explicit_loop("loop")
    assert not is_point_trigger_safe("loop")
    assert not is_explicit_loop(None)


def test_new_oneshot_assignment_seeds_default_on():
    kit = LiveKitState()
    kit.assign(
        "Kick + Bass",
        "Kick",
        _row("kick", "synthetic/kick.wav", sample_class="oneshot"),
    )
    state = build_channel_rack_state(kit)
    kick_id = CHANNEL_ID_BY_LIVE_KIT_SLOT[("Kick + Bass", "Kick")]
    assert len(_triggers_for(state, kick_id)) == DEFAULT_STEP_COUNT


def test_new_loop_assignment_does_not_seed_default_on():
    kit = LiveKitState()
    kit.assign(
        "Atmos / FX",
        "Atmos",
        _row("loop", "synthetic/loop.wav", sample_class="loop"),
    )
    state = build_channel_rack_state(kit)
    loop_id = CHANNEL_ID_BY_LIVE_KIT_SLOT[("Atmos / FX", "Atmos")]
    assert _triggers_for(state, loop_id) == ()
    channel = next(c for c in state.channels if c.channel_id == loop_id)
    assert channel.sample_path == "synthetic/loop.wav"


def test_ambiguous_assignment_does_not_seed_default_on():
    kit = LiveKitState()
    kit.assign(
        "Kick + Bass",
        "Kick",
        _row("mystery", "synthetic/mystery.wav", sample_class=None),
    )
    state = build_channel_rack_state(kit)
    kick_id = CHANNEL_ID_BY_LIVE_KIT_SLOT[("Kick + Bass", "Kick")]
    assert _triggers_for(state, kick_id) == ()


def test_late_oneshot_seed_via_reconcile_only_when_empty_to_assigned():
    empty = build_channel_rack_state(LiveKitState())
    kit = LiveKitState()
    kit.assign(
        "Kick + Bass",
        "Kick",
        _row("kick", "synthetic/kick.wav", sample_class="one_shot"),
    )
    state = reconcile_live_kit_sample_assignments(empty, kit)
    kick_id = CHANNEL_ID_BY_LIVE_KIT_SLOT[("Kick + Bass", "Kick")]
    assert len(_triggers_for(state, kick_id)) == DEFAULT_STEP_COUNT


def test_late_loop_seed_via_reconcile_does_not_default_on():
    empty = build_channel_rack_state(LiveKitState())
    kit = LiveKitState()
    kit.assign(
        "Atmos / FX",
        "Atmos",
        _row("loop", "synthetic/loop.wav", sample_class="loop"),
    )
    state = reconcile_live_kit_sample_assignments(empty, kit)
    loop_id = CHANNEL_ID_BY_LIVE_KIT_SLOT[("Atmos / FX", "Atmos")]
    assert _triggers_for(state, loop_id) == ()


def test_filter_excludes_loop_and_ambiguous_from_point_playback_without_mutating_state():
    kit = LiveKitState()
    kit.assign(
        "Kick + Bass",
        "Kick",
        _row("kick", "synthetic/kick.wav", sample_class="oneshot"),
    )
    kit.assign(
        "Atmos / FX",
        "Atmos",
        _row("loop", "synthetic/loop.wav", sample_class="loop"),
    )
    kit.assign(
        "Atmos / FX",
        "FX",
        _row("amb", "synthetic/amb.wav", sample_class=None),
    )
    state = build_channel_rack_state(kit)
    kick_id = CHANNEL_ID_BY_LIVE_KIT_SLOT[("Kick + Bass", "Kick")]
    loop_id = CHANNEL_ID_BY_LIVE_KIT_SLOT[("Atmos / FX", "Atmos")]
    amb_id = CHANNEL_ID_BY_LIVE_KIT_SLOT[("Atmos / FX", "FX")]
    # Simulate stale persisted triggers on loop/ambiguous channels.
    stale = ChannelRackState(
        channels=state.channels,
        pattern=Pattern(
            pattern_id=state.pattern.pattern_id,
            length_quarter_notes=state.pattern.length_quarter_notes,
            triggers=state.pattern.triggers
            + (
                Trigger(channel_id=loop_id, position=Fraction(0, 4)),
                Trigger(channel_id=amb_id, position=Fraction(0, 4)),
            ),
        ),
        step_count=state.step_count,
    )
    original = stale.pattern.triggers
    filtered = filter_pattern_for_point_trigger_playback(stale, kit)
    assert stale.pattern.triggers == original
    assert all(t.channel_id == kick_id for t in filtered.triggers)
    assert loop_id not in point_trigger_eligible_channel_ids(stale, kit)
    assert amb_id not in point_trigger_eligible_channel_ids(stale, kit)
    assert kick_id in point_trigger_eligible_channel_ids(stale, kit)


def test_explicit_loop_stale_triggers_reconciled_when_class_known():
    kit = LiveKitState()
    kit.assign(
        "Atmos / FX",
        "Atmos",
        _row("was-oneshot", "synthetic/loop.wav", sample_class="oneshot"),
    )
    state = build_channel_rack_state(kit)
    loop_id = CHANNEL_ID_BY_LIVE_KIT_SLOT[("Atmos / FX", "Atmos")]
    assert len(_triggers_for(state, loop_id)) == DEFAULT_STEP_COUNT

    kit.assign(
        "Atmos / FX",
        "Atmos",
        _row("now-loop", "synthetic/loop.wav", sample_class="loop"),
    )
    reconciled = reconcile_live_kit_sample_assignments(state, kit)
    assert _triggers_for(reconciled, loop_id) == ()
    channel = next(c for c in reconciled.channels if c.channel_id == loop_id)
    assert channel.sample_path == "synthetic/loop.wav"


def test_ambiguous_keeps_persisted_triggers_in_state():
    kit = LiveKitState()
    kit.assign(
        "Kick + Bass",
        "Kick",
        _row("kick", "synthetic/kick.wav", sample_class="oneshot"),
    )
    state = build_channel_rack_state(kit)
    kick_id = CHANNEL_ID_BY_LIVE_KIT_SLOT[("Kick + Bass", "Kick")]
    kit.assign(
        "Kick + Bass",
        "Kick",
        _row("kick", "synthetic/kick.wav", sample_class=None),
    )
    reconciled = reconcile_live_kit_sample_assignments(state, kit)
    assert _triggers_for(reconciled, kick_id) == _triggers_for(state, kick_id)
    assert sample_class_for_channel(
        next(c for c in reconciled.channels if c.channel_id == kick_id), kit
    ) is None


def test_unclassified_user_channel_persists_triggers_but_is_excluded_from_playback():
    user = Channel(
        channel_id="ch_user_1",
        live_kit_group=None,
        live_kit_slot=None,
        sample_path="synthetic/user.wav",
    )
    state = ChannelRackState(
        channels=(user,),
        pattern=Pattern(
            pattern_id="screen2-main",
            length_quarter_notes=Fraction(4, 1),
            triggers=(Trigger(channel_id=user.channel_id, position=Fraction(0, 1)),),
        ),
        step_count=DEFAULT_STEP_COUNT,
    )

    filtered = filter_pattern_for_point_trigger_playback(state, LiveKitState())

    assert state.pattern.triggers == (
        Trigger(channel_id=user.channel_id, position=Fraction(0, 1)),
    )
    assert user.channel_id not in point_trigger_eligible_channel_ids(state, LiveKitState())
    assert filtered.triggers == ()
