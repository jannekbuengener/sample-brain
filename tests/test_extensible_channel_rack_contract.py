"""TEST_GATE / TEST_FREEZE — Extensible Channel Rack identity (#681).

Canonical authority:
- docs/PRODUCT_WORKFLOW_CANON.md
- docs/PATTERN_CORE_CONTRACT.md (#681 extension)
- Issue #681 (Live Kit seed + user-added channels)
- src/pattern_core.py
- src/channel_rack.py

Live Kit is the initial seed, not a fixed channel universe. User-added channels
carry opaque IDs without Live Kit provenance. Trigger membership is validated
at the rack/context boundary.

Forbidden in this slice:
- Screen-2 QML / + button UI
- VST3 / CLAP / plugin host
- arrangement / mixer / piano roll
- persistence redesign
"""

from __future__ import annotations

import importlib
from fractions import Fraction

import pytest

from src.pattern_core import (
    CHANNEL_ID_BY_LIVE_KIT_SLOT,
    Channel,
    Pattern,
    Trigger,
)
from src.workbench_live_kit import LiveKitState


REQUIRED_PATTERN_CORE_SYMBOLS = (
    "allocate_user_channel_id",
    "require_triggers_reference_known_channels",
)

REQUIRED_CHANNEL_RACK_SYMBOLS = (
    "add_user_channel",
)


def _pattern_core():
    return importlib.import_module("src.pattern_core")


def _channel_rack():
    return importlib.import_module("src.channel_rack")


def _require(module, name: str):
    value = getattr(module, name, None)
    if value is None:
        pytest.fail(f"MISSING_PRODUCTION_SURFACE: {module.__name__}.{name}")
    return value


# --- Live Kit compatibility --------------------------------------------------


def test_live_kit_channel_remains_valid_with_stable_ids():
    for (group, slot), channel_id in CHANNEL_ID_BY_LIVE_KIT_SLOT.items():
        channel = Channel(
            channel_id=channel_id,
            live_kit_group=group,
            live_kit_slot=slot,
            sample_path=None,
        )
        assert channel.channel_id == channel_id
        assert channel.live_kit_group == group
        assert channel.live_kit_slot == slot


def test_frozen_live_kit_channel_ids_unchanged():
    assert CHANNEL_ID_BY_LIVE_KIT_SLOT[("Kick + Bass", "Kick")] == "ch_kick"
    assert CHANNEL_ID_BY_LIVE_KIT_SLOT[("Drums", "Closed Hat")] == "ch_closed_hat"
    assert len(CHANNEL_ID_BY_LIVE_KIT_SLOT) == 11


def test_mismatched_live_kit_group_slot_id_still_invalid():
    with pytest.raises(ValueError):
        Channel(
            channel_id="ch_kick",
            live_kit_group="Drums",
            live_kit_slot="Open Hat",
            sample_path=None,
        )


def test_partial_live_kit_provenance_is_invalid():
    with pytest.raises(ValueError):
        Channel(
            channel_id="ch_user_1",
            live_kit_group="Drums",
            live_kit_slot=None,
            sample_path=None,
        )
    with pytest.raises(ValueError):
        Channel(
            channel_id="ch_user_1",
            live_kit_group=None,
            live_kit_slot="Kick",
            sample_path=None,
        )


# --- User-added channels -----------------------------------------------------


def test_user_channel_without_live_kit_slot_is_valid():
    channel = Channel(
        channel_id="ch_user_1",
        live_kit_group=None,
        live_kit_slot=None,
        sample_path=None,
    )
    assert channel.live_kit_group is None
    assert channel.live_kit_slot is None
    assert channel.channel_id == "ch_user_1"


def test_user_channel_rejects_canonical_live_kit_id_without_provenance():
    with pytest.raises(ValueError):
        Channel(
            channel_id="ch_kick",
            live_kit_group=None,
            live_kit_slot=None,
            sample_path="synthetic/kick.wav",
        )


def test_allocate_user_channel_id_is_stable_opaque_and_unique():
    module = _pattern_core()
    allocate = _require(module, "allocate_user_channel_id")

    first = allocate([])
    second = allocate([first])
    assert first.startswith("ch_user_")
    assert second.startswith("ch_user_")
    assert first != second
    assert first not in CHANNEL_ID_BY_LIVE_KIT_SLOT.values()
    assert second not in CHANNEL_ID_BY_LIVE_KIT_SLOT.values()


def test_user_channel_may_carry_sample_path():
    path = "synthetic/user_perc_01.wav"
    channel = Channel(
        channel_id="ch_user_1",
        live_kit_group=None,
        live_kit_slot=None,
        sample_path=path,
    )
    assert channel.sample_path == path


def test_trigger_on_user_channel_is_constructible():
    trigger = Trigger(channel_id="ch_user_1", position=Fraction(1, 4))
    assert trigger.channel_id == "ch_user_1"
    assert trigger.position == Fraction(1, 4)


def test_pattern_accepts_trigger_on_user_channel():
    pattern = Pattern(
        pattern_id="pat_user",
        length_quarter_notes=Fraction(4, 1),
        triggers=[Trigger(channel_id="ch_user_1", position=Fraction(0, 1))],
    )
    assert pattern.triggers[0].channel_id == "ch_user_1"


# --- Context-boundary membership ---------------------------------------------


def test_require_triggers_rejects_phantom_channel_at_context_boundary():
    module = _pattern_core()
    require = _require(module, "require_triggers_reference_known_channels")

    with pytest.raises(ValueError, match="Unknown channel_id"):
        require(
            (Trigger(channel_id="ch_phantom", position=Fraction(0, 1)),),
            known_channel_ids={"ch_kick", "ch_user_1"},
        )


def test_require_triggers_accepts_known_live_kit_and_user_ids():
    module = _pattern_core()
    require = _require(module, "require_triggers_reference_known_channels")

    require(
        (
            Trigger(channel_id="ch_kick", position=Fraction(0, 1)),
            Trigger(channel_id="ch_user_1", position=Fraction(1, 4)),
        ),
        known_channel_ids={"ch_kick", "ch_user_1"},
    )


def test_channel_rack_state_rejects_phantom_trigger():
    rack = _channel_rack()
    ChannelRackState = _require(rack, "ChannelRackState")
    build = _require(rack, "build_channel_rack_state")

    state = build(LiveKitState())
    with pytest.raises(ValueError, match="Unknown channel_id"):
        ChannelRackState(
            channels=state.channels,
            pattern=Pattern(
                pattern_id="screen2-main",
                length_quarter_notes=Fraction(4, 1),
                triggers=[
                    Trigger(channel_id="ch_phantom", position=Fraction(0, 1)),
                ],
            ),
            step_count=state.step_count,
        )


# --- Channel rack seed + add -------------------------------------------------


def test_build_channel_rack_still_seeds_live_kit_channels_only():
    rack = _channel_rack()
    build = _require(rack, "build_channel_rack_state")

    state = build(LiveKitState())
    assert len(state.channels) == 11
    assert all(ch.live_kit_group is not None for ch in state.channels)
    assert all(ch.live_kit_slot is not None for ch in state.channels)
    assert [ch.channel_id for ch in state.channels] == list(
        CHANNEL_ID_BY_LIVE_KIT_SLOT.values()
    )


def test_add_user_channel_appends_opaque_channel_without_live_kit_slot():
    rack = _channel_rack()
    build = _require(rack, "build_channel_rack_state")
    add = _require(rack, "add_user_channel")
    toggle = _require(rack, "toggle_step")

    seed = build(LiveKitState())
    extended = add(seed, sample_path="synthetic/user_01.wav")

    assert len(extended.channels) == 12
    user = extended.channels[-1]
    assert user.live_kit_group is None
    assert user.live_kit_slot is None
    assert user.sample_path == "synthetic/user_01.wav"
    assert user.channel_id.startswith("ch_user_")
    assert user.channel_id not in CHANNEL_ID_BY_LIVE_KIT_SLOT.values()

    # Seed channels unchanged.
    assert extended.channels[:11] == seed.channels

    # #677 DEFAULT_ON: sample-bearing user channel seeds all 16 steps.
    assert len(extended.pattern.triggers) == 16
    assert all(t.channel_id == user.channel_id for t in extended.pattern.triggers)

    toggled = toggle(extended, user.channel_id, 2)
    assert len(toggled.pattern.triggers) == 15
    assert Trigger(channel_id=user.channel_id, position=Fraction(2, 4)) not in (
        toggled.pattern.triggers
    )


def test_add_user_channel_rejects_duplicate_explicit_id():
    rack = _channel_rack()
    build = _require(rack, "build_channel_rack_state")
    add = _require(rack, "add_user_channel")

    seed = build(LiveKitState())
    with pytest.raises(ValueError):
        add(seed, channel_id="ch_kick")


def test_extensible_slice_exports_required_helpers():
    pattern_core = _pattern_core()
    for name in REQUIRED_PATTERN_CORE_SYMBOLS:
        _require(pattern_core, name)
    rack = _channel_rack()
    for name in REQUIRED_CHANNEL_RACK_SYMBOLS:
        _require(rack, name)
