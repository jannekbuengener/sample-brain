"""Runtime vectors for #1086 — 32-field / 8-bar Pattern timing + migration.

Runtime owner: [#1086]. Normative policy plane (frozen): #1083
(``docs/ARRANGEMENT_32_FIELD_TIME_CONTRACT.md``,
``docs/arrangement_32_field_time_v1.json``).

These tests exercise the #1086 runtime module ``src/arrangement_32_field_time.py``
*through the frozen runtime seams* — it is not isolated code:

- frames come only from the live ``TempoMap`` (``src/session_grid.py``),
- scheduling reuses the live ``plan_pattern_once`` (``src/sequencer_playback.py``),
- Pattern identity / triggers are the live ``Pattern``/``Trigger``
  (``src/pattern_core.py``),
- the rack state is the live ``ChannelRackState`` builder (``src/channel_rack.py``),
- serialize/restore reuses the live session store (``src/workbench_session_store.py``).

The covered vectors are the ten ``required_later_runtime_vectors`` of the frozen
contract plus the eleven ``fail_closed_cases``.
"""

from __future__ import annotations

import dataclasses
import inspect
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from src import arrangement_32_field_time as a32
from src import session_grid, sequencer_playback
from src.channel_rack import ChannelRackState, build_channel_rack_state
from src.native_audio import PcmBufferConfig
from src.pattern_core import Channel, Pattern, Trigger
from src.session_grid import TempoMap
from src.sequencer_playback import schedule_pattern_once
from src.workbench_channel_rack import ChannelRackController
from src.workbench_live_kit import LiveKitState
from src.workbench_session_store import (
    load_workbench_session_outcome,
    save_workbench_session_snapshot,
    snapshot_from_musical_state,
)

REPRESENTATIVE_FIELDS = (0, 3, 4, 7, 8, 15, 16, 31)
BAR_START_FIELDS = (0, 4, 8, 12, 16, 20, 24, 28)

# Pinned contract TempoMap frames (docs/arrangement_32_field_time_v1.json).
PINNED_FRAMES_48K_120 = {
    0: 0,
    3: 72000,
    4: 96000,
    7: 168000,
    8: 192000,
    15: 360000,
    16: 384000,
    31: 744000,
    32: 768000,
}
PINNED_FRAMES_48K_140 = {
    0: 0,
    3: 61714,
    4: 82286,
    7: 144000,
    8: 164571,
    15: 308571,
    16: 329143,
    31: 637714,
    32: 658286,
}

FORBIDDEN_MIGRATION_TOKENS = (
    "index_times_two",
    "index_times_any_factor",
    "blind_trigger_copy_as_32_fields",
    "spread_16_steps_across_32_fields",
    "replicate_pattern_eight_times",
    "silent_fractional_trigger_rounding",
    "silent_reinterpret_canonical_default_on_as_32_field_grid",
)

REQUIRED_FAIL_CLOSED_IDS = (
    "field_index_negative",
    "field_index_ge_32",
    "malformed_field_type",
    "trigger_at_or_outside_cycle_end_in_one_cycle_truth",
    "invalid_pattern_length",
    "unknown_or_malformed_legacy_step_count",
    "legacy_trigger_outside_old_pattern_bounds",
    "ambiguous_legacy_mapping",
    "corrupt_persistence_payload",
    "user_added_unknown_legacy_state",
    "sixty_four_field_state",
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _rack(channel_ids: tuple[str, ...] = ("ch_kick",)) -> ChannelRackState:
    return a32.build_32_field_channel_rack_state(LiveKitState())


def _channels_by_id(
    *channel_ids: str, sample_path: str | None = None
) -> dict[str, Channel]:
    state = build_channel_rack_state(LiveKitState())
    by_id = {ch.channel_id: ch for ch in state.channels}
    wanted = channel_ids or tuple(by_id)
    return {
        cid: dataclasses.replace(by_id[cid], sample_path=sample_path)
        for cid in wanted
    }


def _pattern(*triggers: Trigger) -> Pattern:
    return a32.build_32_field_pattern("screen2-main", triggers)


class _FakeEngine:
    """Minimal native engine double: records create + schedule calls."""

    def __init__(self) -> None:
        self.schedule_calls: list[tuple[int, int]] = []
        self._next = 1

    def create_voice(self, config) -> int:  # noqa: ANN001
        voice_id = self._next
        self._next += 1
        return voice_id

    def schedule_voice_start(self, voice_id: int, engine_frame: int) -> None:
        self.schedule_calls.append((voice_id, engine_frame))


class _TransportStub:
    def __init__(self, bpm: float = 120.0, sync: bool = False) -> None:
        self._bpm = bpm
        self._sync = sync

    def get_resume_master_bpm(self) -> float:
        return self._bpm

    def is_sync_enabled(self) -> bool:
        return self._sync

    def get_snapshot(self):  # noqa: ANN201
        return {"current_tempo": self._bpm}


def _pcm(frames: int = 8) -> PcmBufferConfig:
    samples = np.linspace(-0.2, 0.2, frames, dtype=np.float32)
    return PcmBufferConfig(samples=samples, channels=1)


# --------------------------------------------------------------------------- #
# non-isolation: the module binds the frozen runtime seams, not a copy
# --------------------------------------------------------------------------- #


def test_module_binds_frozen_runtime_seams_not_a_copy():
    assert a32.TempoMap is session_grid.TempoMap
    assert a32.plan_pattern_once is sequencer_playback.plan_pattern_once
    assert a32.Pattern is Pattern
    assert a32.Trigger is Trigger
    assert a32.ChannelRackState is ChannelRackState

    # The runtime module composes the live seam rather than re-implementing it.
    src = inspect.getsource(a32)
    assert "plan_pattern_once(" in src
    assert "TempoMap" in src


def test_module_source_has_no_forbidden_migration_tokens():
    src = inspect.getsource(a32)
    for token in FORBIDDEN_MIGRATION_TOKENS:
        assert token not in src, token


# --------------------------------------------------------------------------- #
# vector 1 — exact quarter positions for all 32 fields
# --------------------------------------------------------------------------- #


def test_exact_quarter_positions_all_32_fields():
    assert a32.TOTAL_FIELDS == 32
    assert a32.FIELDS_PER_BAR == 4
    assert a32.BARS_PER_CYCLE == 8
    assert a32.QUARTER_NOTES_PER_FIELD == Fraction(1, 1)
    assert a32.CYCLE_LENGTH_QUARTER_NOTES == Fraction(32, 1)
    assert a32.SIXTY_FOUR_FIELDS_IN_V1 is False

    for field in range(32):
        assert a32.field_to_quarter_note(field) == Fraction(field, 1)
        assert a32.field_to_bar(field) == field // 4
        assert a32.field_in_bar(field) == field % 4
        assert a32.quarter_note_to_field(Fraction(field, 1)) == field

    assert a32.bar_start_fields() == BAR_START_FIELDS


# --------------------------------------------------------------------------- #
# vector 2 — representative engine frames, two BPM, via TempoMap
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("bpm", "expected"),
    [(120, PINNED_FRAMES_48K_120), (140, PINNED_FRAMES_48K_140)],
)
def test_representative_engine_frames_two_bpm_via_tempo_map(bpm, expected):
    tempo_map = TempoMap(sample_rate=48000, bpm=bpm)
    pattern = _pattern(
        *(
            Trigger(channel_id="ch_kick", position=Fraction(field, 1))
            for field in REPRESENTATIVE_FIELDS
        )
    )
    plan = a32.plan_pattern_cycle(
        pattern=pattern,
        channels_by_id=_channels_by_id("ch_kick"),
        tempo_map=tempo_map,
        cycle_index=0,
        block_start_quarter=Fraction(0, 1),
        block_start_engine_frame=0,
    )
    frames = {int(t.position): t.engine_frame for t in plan}
    for field in REPRESENTATIVE_FIELDS:
        assert frames[field] == expected[field]
        # frames track the live authority exactly
        assert frames[field] == tempo_map.quarter_note_to_frame(Fraction(field, 1))


# --------------------------------------------------------------------------- #
# vector 3 — no double fire at the 8-bar loop wrap (half-open [0, 32))
# --------------------------------------------------------------------------- #


def test_no_double_fire_at_8_bar_loop_wrap():
    tempo_map = TempoMap(sample_rate=48000, bpm=120)
    pattern = _pattern(
        Trigger(channel_id="ch_kick", position=Fraction(0, 1)),
        Trigger(channel_id="ch_kick", position=Fraction(31, 1)),
    )
    cycles = a32.plan_arrangement_block(
        pattern=pattern,
        channels_by_id=_channels_by_id("ch_kick"),
        tempo_map=tempo_map,
        block_start_quarter=Fraction(0, 1),
        block_start_engine_frame=0,
    )
    assert len(cycles) == 2

    frames = [t.engine_frame for cycle in cycles for t in cycle]
    assert len(frames) == len(set(frames)), "cycle boundary double-fired"

    cycle0 = {int(t.position): t.engine_frame for t in cycles[0]}
    cycle1 = {int(t.position): t.engine_frame for t in cycles[1]}
    assert cycle0[0] == tempo_map.quarter_note_to_frame(Fraction(0, 1))
    assert cycle0[31] == tempo_map.quarter_note_to_frame(Fraction(31, 1))
    assert cycle1[0] == tempo_map.quarter_note_to_frame(Fraction(32, 1))
    assert cycle1[31] == tempo_map.quarter_note_to_frame(Fraction(63, 1))
    # qn=32 is the first event of cycle 1 only; cycle 0's last event is qn=31.
    assert cycle1[0] != cycle0[31]
    assert all(t.position < a32.CYCLE_LENGTH_QUARTER_NOTES for t in cycles[0])


# --------------------------------------------------------------------------- #
# vector 4 — 16-bar block = two identical cycles of ONE Pattern identity
# --------------------------------------------------------------------------- #


def test_16_bar_block_two_identical_cycles_one_pattern_id():
    projection = a32.project_arrangement_block(_pattern())
    assert [c.cycle_index for c in projection] == [0, 1]
    assert [c.absolute_quarter_offset for c in projection] == [
        Fraction(0, 1),
        Fraction(32, 1),
    ]
    assert [c.bars_one_based for c in projection] == [(1, 8), (9, 16)]
    assert a32.ARRANGEMENT_BLOCK_BARS == 16
    assert a32.ARRANGEMENT_BLOCK_LENGTH_QUARTER_NOTES == Fraction(64, 1)

    tempo_map = TempoMap(sample_rate=48000, bpm=120)
    pattern = _pattern(Trigger(channel_id="ch_kick", position=Fraction(2, 1)))
    cycles = a32.plan_arrangement_block(
        pattern=pattern,
        channels_by_id=_channels_by_id("ch_kick"),
        tempo_map=tempo_map,
        block_start_quarter=Fraction(0, 1),
        block_start_engine_frame=0,
    )
    # Same pattern identity in both halves — identical channel/position sequence.
    seq0 = [(t.channel_id, t.position) for t in cycles[0]]
    seq1 = [(t.channel_id, t.position) for t in cycles[1]]
    assert seq0 == seq1 == [("ch_kick", Fraction(2, 1))]
    # second half is offset by exactly 32 quarter notes, nothing copied.
    assert cycles[1][0].engine_frame == tempo_map.quarter_note_to_frame(Fraction(34, 1))


# --------------------------------------------------------------------------- #
# vector 5 — toggling one field changes both repetitions without a copy
# --------------------------------------------------------------------------- #


def test_toggle_one_field_changes_both_repetitions_without_copy():
    base = _pattern()
    toggled = a32.toggle_field(base, Trigger(channel_id="ch_kick", position=Fraction(5, 1)))
    assert toggled is not base  # a new authoritative Pattern value
    assert toggled.pattern_id == base.pattern_id  # one identity, no second copy state

    tempo_map = TempoMap(sample_rate=48000, bpm=120)
    cycles = a32.plan_arrangement_block(
        pattern=toggled,
        channels_by_id=_channels_by_id("ch_kick"),
        tempo_map=tempo_map,
        block_start_quarter=Fraction(0, 1),
        block_start_engine_frame=0,
    )
    assert [t.position for t in cycles[0]] == [Fraction(5, 1)]
    assert [t.position for t in cycles[1]] == [Fraction(5, 1)]

    # toggling twice removes the trigger again (no accumulating shadow copy)
    assert a32.toggle_field(toggled, Trigger(channel_id="ch_kick", position=Fraction(5, 1))).triggers == ()


# --------------------------------------------------------------------------- #
# vector 6 — tempo change preserves musical identity and remaps frames
# --------------------------------------------------------------------------- #


def test_tempo_change_preserves_musical_identity_remaps_frames():
    tempo_map = TempoMap(sample_rate=48000, bpm=120)
    tempo_map.add_tempo_change_at_quarter(effective_quarter=16, bpm=140)

    pattern = _pattern(
        Trigger(channel_id="ch_kick", position=Fraction(0, 1)),
        Trigger(channel_id="ch_kick", position=Fraction(16, 1)),
    )
    cycles = a32.plan_arrangement_block(
        pattern=pattern,
        channels_by_id=_channels_by_id("ch_kick"),
        tempo_map=tempo_map,
        block_start_quarter=Fraction(0, 1),
        block_start_engine_frame=0,
    )
    # Stored musical positions are unchanged by the tempo change.
    assert [t.position for t in cycles[0]] == [Fraction(0, 1), Fraction(16, 1)]
    # Future frames follow the (changed) TempoMap.
    cycle1 = {int(t.position): t.engine_frame for t in cycles[1]}
    assert cycle1[0] == tempo_map.quarter_note_to_frame(Fraction(32, 1))
    assert cycle1[16] == tempo_map.quarter_note_to_frame(Fraction(48, 1))
    # cycle-0 field 0 sits in the pre-change segment.
    assert cycles[0][0].engine_frame == tempo_map.quarter_note_to_frame(Fraction(0, 1))


# --------------------------------------------------------------------------- #
# vector 7 — serialize / restore round-trip through the live session store
# --------------------------------------------------------------------------- #


def test_serialize_restore_round_trip_32_field_pattern(tmp_path: Path):
    state = a32.build_32_field_channel_rack_state(LiveKitState())
    state = a32.set_field(
        state,
        Trigger(channel_id="ch_kick", position=Fraction(0, 1)),
        active=True,
    )
    state = a32.set_field(
        state,
        Trigger(channel_id="ch_kick", position=Fraction(31, 1)),
        active=True,
    )
    assert a32.channel_rack_time_semantics_version(state) == a32.TIME_SEMANTICS_32_FIELD_V1

    snapshot = snapshot_from_musical_state(
        LiveKitState(), state, _TransportStub()
    )
    state_dir = tmp_path / "state"
    save_workbench_session_snapshot(snapshot, state_dir=state_dir)

    outcome = load_workbench_session_outcome(state_dir=state_dir)
    assert outcome.status == "restored_ok"
    restored = outcome.snapshot.channel_rack
    assert restored is not None
    assert restored.step_count == 32
    assert restored.pattern.length_quarter_notes == Fraction(32, 1)
    assert restored.pattern.triggers == (
        Trigger(channel_id="ch_kick", position=Fraction(0, 1)),
        Trigger(channel_id="ch_kick", position=Fraction(31, 1)),
    )
    assert a32.channel_rack_time_semantics_version(restored) == a32.TIME_SEMANTICS_32_FIELD_V1


# --------------------------------------------------------------------------- #
# vector 8 — legacy 16-step fixtures follow the frozen migration outcomes
# --------------------------------------------------------------------------- #


def test_legacy_empty_migrates_to_empty_32_field():
    result = a32.migrate_legacy_v1_rack(
        step_count=16,
        length_quarter_notes=Fraction(4, 1),
        triggers=(),
    )
    assert result.outcome == a32.OUTCOME_MIGRATED_EMPTY
    assert result.pattern is not None
    assert result.pattern.length_quarter_notes == Fraction(32, 1)
    assert result.pattern.triggers == ()


def test_legacy_field_aligned_bar_replicated():
    triggers = tuple(
        Trigger(channel_id="ch_kick", position=Fraction(i, 1)) for i in (0, 3)
    )
    result = a32.migrate_legacy_v1_rack(
        step_count=16,
        length_quarter_notes=Fraction(4, 1),
        triggers=triggers,
    )
    assert result.outcome == a32.OUTCOME_MIGRATED_FIELD_ALIGNED_BAR_REPLICATED
    positions = sorted(t.position for t in result.pattern.triggers)
    # p + 4*k for k in 0..7
    assert positions == [
        Fraction(0, 1),
        Fraction(3, 1),
        Fraction(4, 1),
        Fraction(7, 1),
        Fraction(8, 1),
        Fraction(11, 1),
        Fraction(12, 1),
        Fraction(15, 1),
        Fraction(16, 1),
        Fraction(19, 1),
        Fraction(20, 1),
        Fraction(23, 1),
        Fraction(24, 1),
        Fraction(27, 1),
        Fraction(28, 1),
        Fraction(31, 1),
    ]


def test_legacy_canonical_default_on_is_migration_required():
    triggers = tuple(
        Trigger(channel_id="ch_kick", position=Fraction(i, 4)) for i in range(16)
    )
    result = a32.migrate_legacy_v1_rack(
        step_count=16,
        length_quarter_notes=Fraction(4, 1),
        triggers=triggers,
    )
    assert result.outcome == a32.OUTCOME_MIGRATION_REQUIRED
    assert result.pattern is None  # never auto-activated


def test_legacy_trigger_outside_old_bounds_is_hold():
    result = a32.migrate_legacy_v1_rack(
        step_count=16,
        length_quarter_notes=Fraction(4, 1),
        triggers=(Trigger(channel_id="ch_kick", position=Fraction(4, 1)),),
    )
    assert result.outcome == a32.OUTCOME_MIGRATION_HOLD
    assert result.pattern is None


# --------------------------------------------------------------------------- #
# vector 9 — empty and user-added channels produce no phantom triggers
# --------------------------------------------------------------------------- #


def test_empty_and_user_added_channels_no_phantom_triggers():
    state = a32.build_32_field_channel_rack_state(LiveKitState())
    assert state.pattern.triggers == ()
    assert state.step_count == 32

    # Frozen 16-step build DOES seed DEFAULT_ON for a sample-bearing channel…
    assert build_channel_rack_state(LiveKitState()).step_count == 16
    # …but the 32-field initialization must not invent that density.
    with_sample = a32.add_user_channel_32_field(state, sample_path="/tmp/x.wav")
    assert with_sample.pattern.triggers == ()
    assert with_sample.step_count == 32

    empty_user = a32.add_user_channel_32_field(state)
    assert empty_user.pattern.triggers == ()


# --------------------------------------------------------------------------- #
# vector 10 — malformed / out-of-range field or trigger fails closed
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("field", [-1, 32, 33, 100])
def test_field_index_out_of_range_rejected(field):
    with pytest.raises(a32.Arrangement32FieldTimeError):
        a32.field_to_quarter_note(field)


@pytest.mark.parametrize("field", [True, False, 1.0, "3", Fraction(3, 1), None])
def test_malformed_field_type_rejected(field):
    with pytest.raises(a32.Arrangement32FieldTimeError):
        a32.field_to_quarter_note(field)


def test_invalid_pattern_length_rejected():
    legacy = Pattern(
        pattern_id="screen2-main",
        length_quarter_notes=Fraction(4, 1),
        triggers=(),
    )
    with pytest.raises(a32.Arrangement32FieldTimeError):
        a32.require_32_field_pattern(legacy)


def test_trigger_at_cycle_end_rejected_by_pattern_truth():
    # The one-cycle Pattern truth is half-open [0, 32): a position of 32 is not
    # a field and must never be representable.
    with pytest.raises(ValueError):
        Pattern(
            pattern_id="screen2-main",
            length_quarter_notes=Fraction(32, 1),
            triggers=(Trigger(channel_id="ch_kick", position=Fraction(32, 1)),),
        )


def test_sixty_four_field_state_rejected():
    with pytest.raises(a32.Arrangement32FieldTimeError):
        a32.time_semantics_version(64, Fraction(64, 1))


def test_corrupt_persistence_payload_rejected():
    with pytest.raises(a32.Arrangement32FieldTimeError):
        a32.time_semantics_version("32", Fraction(32, 1))
    with pytest.raises(a32.Arrangement32FieldTimeError):
        a32.time_semantics_version(32, 32)


@pytest.mark.parametrize("step_count", [None, "16", 0, -1, 17, 32, True])
def test_unknown_or_malformed_legacy_step_count_rejected(step_count):
    result = a32.migrate_legacy_v1_rack(
        step_count=step_count,
        length_quarter_notes=Fraction(4, 1),
        triggers=(),
    )
    assert result.outcome == a32.OUTCOME_REJECT_FAIL_CLOSED


def test_ambiguous_legacy_mapping_required_or_hold():
    result = a32.migrate_legacy_v1_rack(
        step_count=16,
        length_quarter_notes=Fraction(4, 1),
        triggers=(Trigger(channel_id="ch_kick", position=Fraction(1, 4)),),
    )
    assert result.outcome in (
        a32.OUTCOME_MIGRATION_REQUIRED,
        a32.OUTCOME_MIGRATION_HOLD,
    )


def test_user_added_unknown_legacy_state_hold():
    result = a32.classify_unknown_legacy_state(reason="user_added_unknown_legacy_state")
    assert result.outcome == a32.OUTCOME_MIGRATION_HOLD
    assert result.pattern is None


def test_all_required_fail_closed_ids_are_exposed():
    assert set(REQUIRED_FAIL_CLOSED_IDS) <= set(a32.FAIL_CLOSED_IDS)


# --------------------------------------------------------------------------- #
# field-aligned position gate (code review P2) — only exact integer fields
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("position", [Fraction(1, 4), Fraction(3, 2), Fraction(31, 2)])
def test_fractional_trigger_rejected_by_builder(position):
    trigger = Trigger(channel_id="ch_kick", position=position)
    with pytest.raises(a32.Arrangement32FieldTimeError):
        a32.build_32_field_pattern("screen2-main", (trigger,))


@pytest.mark.parametrize("position", [Fraction(1, 4), Fraction(3, 2), Fraction(31, 2)])
def test_fractional_trigger_rejected_by_require(position):
    pattern = Pattern(
        pattern_id="screen2-main",
        length_quarter_notes=a32.CYCLE_LENGTH_QUARTER_NOTES,
        triggers=(Trigger(channel_id="ch_kick", position=position),),
    )
    with pytest.raises(a32.Arrangement32FieldTimeError):
        a32.require_32_field_pattern(pattern)


def test_add_and_toggle_reject_fractional_positions():
    rack = _rack()
    kick = next(iter(_channels_by_id().values()))
    trigger = Trigger(channel_id=kick.channel_id, position=Fraction(1, 4))
    with pytest.raises(a32.Arrangement32FieldTimeError):
        a32.add_field(rack.pattern, trigger)
    with pytest.raises(a32.Arrangement32FieldTimeError):
        a32.toggle_field(rack.pattern, trigger)
    with pytest.raises(a32.Arrangement32FieldTimeError):
        a32.set_field(rack, trigger, active=True)


# --------------------------------------------------------------------------- #
# live rack-path reachability (code review P1) — ChannelRackController
# --------------------------------------------------------------------------- #


class _RackStatusTransport:
    """Minimal transport facade for arrangement_time_status / restore tests."""

    sample_rate = 48_000

    def is_native_available(self) -> bool:
        return False


def _status_controller() -> ChannelRackController:
    return ChannelRackController(
        live_kit=LiveKitState(),
        transport=_RackStatusTransport(),
    )


def test_controller_restore_32_field_rack_surfaces_runtime_semantics():
    rack = _rack()
    controller = _status_controller()
    controller.restore_state(rack)
    status = controller.arrangement_time_status
    assert status["semantic_version"] == a32.TIME_SEMANTICS_32_FIELD_V1
    assert status["migration_outcome"] is None
    assert status["restored_migration_outcome"] is None
    assert controller.state is rack


def _legacy_default_on_rack() -> ChannelRackState:
    """Canonical legacy v1 rack: 16 steps seeded at quarter-16th positions."""
    kick = Channel(
        channel_id="ch_kick",
        live_kit_group="Kick + Bass",
        live_kit_slot="Kick",
        sample_path=None,
    )
    return ChannelRackState(
        channels=(kick,),
        pattern=Pattern(
            pattern_id="screen2-main",
            length_quarter_notes=Fraction(4, 1),
            triggers=tuple(
                Trigger(channel_id="ch_kick", position=Fraction(i, 4))
                for i in range(16)
            ),
        ),
        step_count=16,
    )


def test_controller_fresh_rack_stays_legacy_and_never_activates():
    controller = _status_controller()
    controller.ensure_state()
    status = controller.arrangement_time_status
    assert status["semantic_version"] == a32.TIME_SEMANTICS_LEGACY_V1
    assert status["migration_outcome"] == a32.OUTCOME_MIGRATED_EMPTY
    assert status["restored_migration_outcome"] is None
    assert controller.state.step_count == 16
    assert controller.state.pattern.length_quarter_notes == Fraction(4, 1)


def test_controller_restore_legacy_rack_surfaces_no_silent_migration():
    legacy = _legacy_default_on_rack()
    controller = _status_controller()
    controller.restore_state(legacy)
    status = controller.arrangement_time_status
    assert status["semantic_version"] == a32.TIME_SEMANTICS_LEGACY_V1
    assert status["restored_migration_outcome"] == a32.OUTCOME_MIGRATION_REQUIRED
    assert controller.state is legacy
    assert legacy.step_count == 16
    assert legacy.pattern.length_quarter_notes == Fraction(4, 1)
    result = a32.migrate_legacy_channel_rack_state(legacy)
    assert result.activated is False


def test_controller_restore_empty_legacy_rack_surfaces_migrated_empty():
    empty_legacy = ChannelRackState(
        channels=(),
        pattern=Pattern(
            pattern_id="screen2-main",
            length_quarter_notes=Fraction(4, 1),
            triggers=(),
        ),
        step_count=16,
    )
    controller = _status_controller()
    controller.restore_state(empty_legacy)
    status = controller.arrangement_time_status
    assert status["semantic_version"] == a32.TIME_SEMANTICS_LEGACY_V1
    assert status["restored_migration_outcome"] == a32.OUTCOME_MIGRATED_EMPTY


def test_controller_restore_unknown_rack_fails_closed_surface():
    unknown = ChannelRackState(
        channels=(),
        pattern=Pattern(
            pattern_id="screen2-main",
            length_quarter_notes=Fraction(5, 1),
            triggers=(),
        ),
        step_count=8,
    )
    controller = _status_controller()
    controller.restore_state(unknown)
    status = controller.arrangement_time_status
    assert status["semantic_version"] is None
    assert status["restored_migration_outcome"] == a32.OUTCOME_REJECT_FAIL_CLOSED


# --------------------------------------------------------------------------- #
# runtime seam reachability — plan feeds the live scheduling seam
# --------------------------------------------------------------------------- #


def test_plan_feeds_live_scheduling_seam_with_fake_engine():
    tempo_map = TempoMap(sample_rate=48000, bpm=120)
    channels_by_id = _channels_by_id("ch_kick", sample_path="/tmp/kick.wav")
    pattern = _pattern(
        Trigger(channel_id="ch_kick", position=Fraction(0, 1)),
        Trigger(channel_id="ch_kick", position=Fraction(31, 1)),
    )
    cycles = a32.plan_arrangement_block(
        pattern=pattern,
        channels_by_id=channels_by_id,
        tempo_map=tempo_map,
        block_start_quarter=Fraction(0, 1),
        block_start_engine_frame=0,
    )
    planned = tuple(t for cycle in cycles for t in cycle)

    engine = _FakeEngine()
    result = schedule_pattern_once(
        planned_triggers=planned,
        engine=engine,
        pcm_for_path=lambda path: _pcm() if path == "/tmp/kick.wav" else None,
        allocate_voice_id=lambda: 1,
    )
    assert result.scheduled_count == 4  # 2 triggers × 2 cycles
    assert [frame for _, frame in engine.schedule_calls] == [
        t.engine_frame for t in planned
    ]
