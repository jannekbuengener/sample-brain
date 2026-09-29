"""TEST_GATE / TEST_FREEZE — Channel Rack DEFAULT_ON initial step semantics (#677).

Canonical authority:
- docs/PRODUCT_WORKFLOW_CANON.md (§3 Channel Rack product rules)
- docs/PATTERN_CORE_CONTRACT.md (Channel Rack initial step semantics)
- Issue #677 / parent #675
- src/channel_rack.py
- src/pattern_core.py

Product rule frozen here:
- sample-bearing channel (non-empty sample_path) → 16/16 steps ON
- empty channel → 0 triggers (no phantoms)
- toggle_step remains symmetric presence toggle
- no Additive/Subtractive mode framework
- QML / arrangement / mixer out of scope
"""

from __future__ import annotations

import importlib
from fractions import Fraction

import pytest

from src.pattern_core import CHANNEL_ID_BY_LIVE_KIT_SLOT, Trigger
from src.workbench_controller import WorkbenchRow
from src.workbench_live_kit import LIVE_KIT_SLOT_MAPPING, LiveKitState

EXPECTED_STEP_COUNT = 16
EXPECTED_STEP_POSITIONS = tuple(Fraction(i, 4) for i in range(EXPECTED_STEP_COUNT))


def _channel_rack():
    return importlib.import_module("src.channel_rack")


def _require(module, name: str):
    value = getattr(module, name, None)
    if value is None:
        pytest.fail(f"MISSING_PRODUCTION_SURFACE: {module.__name__}.{name}")
    return value


def _synthetic_row(name: str, path: str) -> WorkbenchRow:
    return WorkbenchRow(
        display_name=name,
        relative_path=path,
        path=path,
        bpm=120.0,
        key="Cmaj",
        key_conf=0.9,
        loudness=-18.0,
        brightness=2400.0,
        sample_class="oneshot",
        pred_type="Kick",
        status="ok",
        details={"source": "synthetic"},
    )


def _live_kit_with_assignments(*assignments: tuple[str, str, str]) -> LiveKitState:
    state = LiveKitState()
    for group, slot, path in assignments:
        state.assign(group, slot, _synthetic_row(f"{slot}", path))
    return state


def _triggers_for_channel(triggers, channel_id: str) -> tuple[Trigger, ...]:
    return tuple(t for t in triggers if t.channel_id == channel_id)


def test_sample_bearing_live_kit_channel_initializes_with_16_active_steps():
    rack = _channel_rack()
    build = _require(rack, "build_channel_rack_state")
    state = build(
        _live_kit_with_assignments(
            ("Kick + Bass", "Kick", "synthetic/kick_01.wav"),
        )
    )

    kick_triggers = _triggers_for_channel(state.pattern.triggers, "ch_kick")
    assert len(kick_triggers) == EXPECTED_STEP_COUNT
    assert [t.position for t in kick_triggers] == list(EXPECTED_STEP_POSITIONS)
    assert all(type(t.position) is Fraction for t in kick_triggers)


def test_empty_live_kit_channel_initializes_without_triggers():
    rack = _channel_rack()
    build = _require(rack, "build_channel_rack_state")
    state = build(
        _live_kit_with_assignments(
            ("Kick + Bass", "Kick", "synthetic/kick_01.wav"),
        )
    )

    empty_ids = [
        CHANNEL_ID_BY_LIVE_KIT_SLOT[(group, slot)]
        for group, slots in LIVE_KIT_SLOT_MAPPING
        for slot in slots
        if (group, slot) != ("Kick + Bass", "Kick")
    ]
    assert len(empty_ids) == 10
    for channel_id in empty_ids:
        assert _triggers_for_channel(state.pattern.triggers, channel_id) == ()


def test_two_sample_bearing_channels_seed_32_triggers_total():
    rack = _channel_rack()
    build = _require(rack, "build_channel_rack_state")
    state = build(
        _live_kit_with_assignments(
            ("Kick + Bass", "Kick", "synthetic/kick_01.wav"),
            ("Drums", "Closed Hat", "synthetic/ch_01.wav"),
        )
    )

    kick = _triggers_for_channel(state.pattern.triggers, "ch_kick")
    hat = _triggers_for_channel(state.pattern.triggers, "ch_closed_hat")
    assert len(kick) == EXPECTED_STEP_COUNT
    assert len(hat) == EXPECTED_STEP_COUNT
    assert len(state.pattern.triggers) == 32


def test_default_on_triggers_are_deterministically_normalized():
    rack = _channel_rack()
    build = _require(rack, "build_channel_rack_state")
    state = build(
        _live_kit_with_assignments(
            ("Kick + Bass", "Kick", "synthetic/kick_01.wav"),
            ("Drums", "Closed Hat", "synthetic/ch_01.wav"),
        )
    )

    # Pattern Core sort key: (position, channel_id)
    assert state.pattern.triggers == tuple(
        sorted(
            state.pattern.triggers,
            key=lambda t: (t.position, t.channel_id),
        )
    )
    # At step 0 both channels fire; closed_hat sorts before kick.
    assert state.pattern.triggers[0:2] == (
        Trigger(channel_id="ch_closed_hat", position=Fraction(0, 4)),
        Trigger(channel_id="ch_kick", position=Fraction(0, 4)),
    )


def test_toggle_removes_then_restores_initially_active_step():
    rack = _channel_rack()
    build = _require(rack, "build_channel_rack_state")
    toggle = _require(rack, "toggle_step")
    state = build(
        _live_kit_with_assignments(
            ("Kick + Bass", "Kick", "synthetic/kick_01.wav"),
        )
    )
    assert len(state.pattern.triggers) == EXPECTED_STEP_COUNT

    removed = toggle(state, "ch_kick", 5)
    assert len(removed.pattern.triggers) == EXPECTED_STEP_COUNT - 1
    assert Trigger(channel_id="ch_kick", position=Fraction(5, 4)) not in (
        removed.pattern.triggers
    )

    restored = toggle(removed, "ch_kick", 5)
    assert restored.pattern.triggers == state.pattern.triggers
    assert Trigger(channel_id="ch_kick", position=Fraction(5, 4)) in (
        restored.pattern.triggers
    )


def test_toggle_on_one_channel_does_not_affect_other_channel_triggers():
    rack = _channel_rack()
    build = _require(rack, "build_channel_rack_state")
    toggle = _require(rack, "toggle_step")
    state = build(
        _live_kit_with_assignments(
            ("Kick + Bass", "Kick", "synthetic/kick_01.wav"),
            ("Drums", "Closed Hat", "synthetic/ch_01.wav"),
        )
    )
    hat_before = _triggers_for_channel(state.pattern.triggers, "ch_closed_hat")

    after = toggle(state, "ch_kick", 0)
    hat_after = _triggers_for_channel(after.pattern.triggers, "ch_closed_hat")
    kick_after = _triggers_for_channel(after.pattern.triggers, "ch_kick")

    assert hat_after == hat_before
    assert len(kick_after) == EXPECTED_STEP_COUNT - 1
    assert Trigger(channel_id="ch_kick", position=Fraction(0, 4)) not in kick_after


def test_add_user_channel_with_sample_path_seeds_16_active_steps():
    rack = _channel_rack()
    build = _require(rack, "build_channel_rack_state")
    add = _require(rack, "add_user_channel")

    seed = build(LiveKitState())
    assert seed.pattern.triggers == ()

    extended = add(seed, sample_path="synthetic/user_01.wav")
    user = extended.channels[-1]
    user_triggers = _triggers_for_channel(extended.pattern.triggers, user.channel_id)

    assert len(extended.channels) == 12
    assert len(user_triggers) == EXPECTED_STEP_COUNT
    assert [t.position for t in user_triggers] == list(EXPECTED_STEP_POSITIONS)
    assert extended.channels[:11] == seed.channels


def test_add_user_channel_without_sample_path_seeds_zero_triggers():
    rack = _channel_rack()
    build = _require(rack, "build_channel_rack_state")
    add = _require(rack, "add_user_channel")

    seed = build(
        _live_kit_with_assignments(
            ("Kick + Bass", "Kick", "synthetic/kick_01.wav"),
        )
    )
    before = seed.pattern.triggers
    extended = add(seed, sample_path=None)
    user = extended.channels[-1]

    assert len(extended.channels) == 12
    assert _triggers_for_channel(extended.pattern.triggers, user.channel_id) == ()
    assert extended.pattern.triggers == before


def test_live_kit_channel_ids_remain_canonical_after_default_on_init():
    rack = _channel_rack()
    build = _require(rack, "build_channel_rack_state")
    state = build(
        _live_kit_with_assignments(
            ("Kick + Bass", "Kick", "synthetic/kick_01.wav"),
        )
    )
    expected_ids = list(CHANNEL_ID_BY_LIVE_KIT_SLOT.values())
    assert [ch.channel_id for ch in state.channels] == expected_ids


def test_user_channel_remains_opaque_without_live_kit_provenance():
    rack = _channel_rack()
    build = _require(rack, "build_channel_rack_state")
    add = _require(rack, "add_user_channel")

    extended = add(build(LiveKitState()), sample_path="synthetic/user_01.wav")
    user = extended.channels[-1]
    assert user.live_kit_group is None
    assert user.live_kit_slot is None
    assert user.channel_id.startswith("ch_user_")
    assert user.channel_id not in CHANNEL_ID_BY_LIVE_KIT_SLOT.values()


def test_phantom_channel_id_remains_fail_closed_on_toggle():
    rack = _channel_rack()
    build = _require(rack, "build_channel_rack_state")
    toggle = _require(rack, "toggle_step")
    state = build(
        _live_kit_with_assignments(
            ("Kick + Bass", "Kick", "synthetic/kick_01.wav"),
        )
    )

    with pytest.raises(ValueError, match="Unknown channel_id"):
        toggle(state, "ch_phantom", 0)
