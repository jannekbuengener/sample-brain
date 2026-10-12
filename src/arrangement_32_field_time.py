"""Runtime implementation of the frozen #1083 32-field / 8-bar Pattern time model.

Normative policy plane (frozen, do not reinterpret):
- ``docs/ARRANGEMENT_32_FIELD_TIME_CONTRACT.md``
- ``docs/arrangement_32_field_time_v1.json``

Runtime owner: [#1086]. This module *implements* the frozen contract; it never
redefines it. It is an integration layer that composes the existing runtime
seams instead of duplicating them:

- exact Fraction quarter-note positions, ``Pattern``/``Trigger`` identity
  (:mod:`src.pattern_core`);
- frame mapping through the sole authority :class:`TempoMap`
  (:mod:`src.session_grid`) — never hardcoded milliseconds;
- one-pass scheduling through the live ``plan_pattern_once``
  (:mod:`src.sequencer_playback`);
- rack snapshots through the live ``ChannelRackState`` /
  ``build_channel_rack_state`` (:mod:`src.channel_rack`).

Boundaries (see the contract):
- one single Pattern truth; the 16-bar block is two cycles of that one Pattern
  identity (offset 0 and 32), never a copied second half;
- half-open cycle interval ``[0, 32)`` — the point qn=32 belongs to the next
  cycle only, so there is no double fire at the 8-bar wrap;
- 64-field state is forbidden in v1;
- ``time_semantics_version`` is *derived* from ``(step_count, length)`` — there
  is no second persisted marker and no second persistence store;
- legacy v1 (16-step, length=4) migration is executed here as a pure decision:
  no silent reinterpretation, no phantom triggers, no rounding/stretching.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction

from .channel_rack import (
    DEFAULT_PATTERN_ID,
    ChannelRackState,
    build_channel_rack_state,
)
from .pattern_core import (
    Channel,
    Pattern,
    Trigger,
    allocate_user_channel_id,
)
from .sequencer_playback import ScheduledTrigger, plan_pattern_once
from .session_grid import TempoMap

# --- frozen field geometry -------------------------------------------------- #

TIME_SEMANTICS_LEGACY_V1 = "legacy_16_step_v1"
TIME_SEMANTICS_32_FIELD_V1 = "arrangement_32_field_v1"

FIELDS_PER_BAR = 4
BARS_PER_CYCLE = 8
TOTAL_FIELDS = 32
QUARTER_NOTES_PER_FIELD = Fraction(1, 1)
CYCLE_LENGTH_QUARTER_NOTES = Fraction(32, 1)

ARRANGEMENT_BLOCK_CYCLES = 2
ARRANGEMENT_BLOCK_BARS = 16
ARRANGEMENT_BLOCK_LENGTH_QUARTER_NOTES = Fraction(64, 1)
SIXTY_FOUR_FIELDS_IN_V1 = False

LEGACY_V1_STEP_COUNT = 16
LEGACY_V1_LENGTH_QUARTER_NOTES = Fraction(4, 1)
LEGACY_V1_STEP_TO_POSITION = Fraction(1, 4)

MAX_FIELDS_V1 = TOTAL_FIELDS

# --- migration outcomes (frozen vocabulary) --------------------------------- #

OUTCOME_MIGRATED_EMPTY = "migrated_empty"
OUTCOME_MIGRATED_FIELD_ALIGNED_BAR_REPLICATED = "migrated_field_aligned_bar_replicated"
OUTCOME_MIGRATION_REQUIRED = "migration_required"
OUTCOME_MIGRATION_HOLD = "migration_hold"
OUTCOME_REJECT_FAIL_CLOSED = "reject_fail_closed"

MIGRATION_OUTCOMES = frozenset(
    {
        OUTCOME_MIGRATED_EMPTY,
        OUTCOME_MIGRATED_FIELD_ALIGNED_BAR_REPLICATED,
        OUTCOME_MIGRATION_REQUIRED,
        OUTCOME_MIGRATION_HOLD,
        OUTCOME_REJECT_FAIL_CLOSED,
    }
)

# Fail-closed case identifiers pinned by the frozen contract.
FAIL_CLOSED_IDS = (
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


class Arrangement32FieldTimeError(ValueError):
    """Fail-closed rejection for the 32-field runtime time model."""


# --- field index <-> exact quarter-note position ---------------------------- #


def _require_field_index(field: object) -> int:
    if type(field) is not int or isinstance(field, bool):
        raise Arrangement32FieldTimeError(
            "malformed_field_type: field index must be an exact int"
        )
    if field < 0:
        raise Arrangement32FieldTimeError("field_index_negative: field index must be >= 0")
    if field >= TOTAL_FIELDS:
        raise Arrangement32FieldTimeError(
            f"field_index_ge_32: field index must be < {TOTAL_FIELDS}"
        )
    return field


def field_to_quarter_note(field: object) -> Fraction:
    """Exact quarter-note position of a field index in ``[0, 32)``."""
    return Fraction(_require_field_index(field), 1)


def quarter_note_to_field(position: object) -> int:
    """Inverse of :func:`field_to_quarter_note` for a one-cycle position."""
    if type(position) is not Fraction:
        raise Arrangement32FieldTimeError(
            "malformed_field_type: position must be an exact Fraction"
        )
    if position.denominator != 1:
        raise Arrangement32FieldTimeError(
            "malformed_field_type: position is not field-aligned"
        )
    return _require_field_index(position.numerator)


def field_to_bar(field: object) -> int:
    """Zero-based bar index of a field (four fields per bar)."""
    return _require_field_index(field) // FIELDS_PER_BAR


def field_in_bar(field: object) -> int:
    """Zero-based field offset within its bar."""
    return _require_field_index(field) % FIELDS_PER_BAR


def bar_start_fields() -> tuple[int, ...]:
    """Field indexes that start each of the eight bars in a cycle."""
    return tuple(k * FIELDS_PER_BAR for k in range(BARS_PER_CYCLE))


# --- Pattern build / validate ----------------------------------------------- #


def build_32_field_pattern(
    pattern_id: str, triggers: Iterable[Trigger] = ()
) -> Pattern:
    """Build an empty-by-default 32-field Pattern (length 32 quarter notes).

    Only field-aligned triggers (exact integer quarter-note positions in
    ``[0, 32)``) are representable in v1; anything else fails closed.
    """
    pattern = Pattern(
        pattern_id=pattern_id,
        length_quarter_notes=CYCLE_LENGTH_QUARTER_NOTES,
        triggers=tuple(triggers),
    )
    return require_32_field_pattern(pattern)


def require_32_field_pattern(pattern: object) -> Pattern:
    """Fail closed unless *pattern* is a valid one-cycle 32-field Pattern.

    Every trigger must sit on an exact integer quarter-note field in the
    half-open cycle interval ``[0, 32)`` — a finer (sub-field) grid is not part
    of v1, so fractional in-range positions such as ``Fraction(1, 4)`` are
    rejected, not silently accepted.
    """
    if not isinstance(pattern, Pattern):
        raise Arrangement32FieldTimeError("pattern must be a Pattern instance")
    if pattern.length_quarter_notes != CYCLE_LENGTH_QUARTER_NOTES:
        raise Arrangement32FieldTimeError(
            "invalid_pattern_length: length_quarter_notes must be 32, got "
            f"{pattern.length_quarter_notes}"
        )
    for trigger in pattern.triggers:
        position = trigger.position
        if (
            position.denominator != 1
            or not (Fraction(0, 1) <= position < CYCLE_LENGTH_QUARTER_NOTES)
        ):
            raise Arrangement32FieldTimeError(
                "trigger_at_or_outside_cycle_end_in_one_cycle_truth: position "
                "must be a field-aligned integer quarter note in [0, 32), got "
                f"{position}"
            )
    return pattern


# --- Pattern field mutation helpers ----------------------------------------- #


def add_field(pattern: Pattern, trigger: Trigger) -> Pattern:
    """Return *pattern* with *trigger* present (idempotent, deduplicated)."""
    require_32_field_pattern(pattern)
    existing = {(t.channel_id, t.position) for t in pattern.triggers}
    key = (trigger.channel_id, trigger.position)
    if key in existing:
        return pattern
    return build_32_field_pattern(pattern.pattern_id, (*pattern.triggers, trigger))


def remove_field(pattern: Pattern, trigger: Trigger) -> Pattern:
    """Return *pattern* with *trigger* removed (idempotent)."""
    require_32_field_pattern(pattern)
    key = (trigger.channel_id, trigger.position)
    kept = tuple(t for t in pattern.triggers if (t.channel_id, t.position) != key)
    return build_32_field_pattern(pattern.pattern_id, kept)


def toggle_field(pattern: Pattern, trigger: Trigger) -> Pattern:
    """Flip the presence of a field trigger on the single Pattern truth."""
    require_32_field_pattern(pattern)
    key = (trigger.channel_id, trigger.position)
    if any((t.channel_id, t.position) == key for t in pattern.triggers):
        return remove_field(pattern, trigger)
    return add_field(pattern, trigger)


def set_field(
    state: ChannelRackState, trigger: Trigger, *, active: bool
) -> ChannelRackState:
    """Set/clear one field on a rack state's single Pattern truth."""
    require_32_field_channel_rack_state(state)
    pattern = add_field(state.pattern, trigger) if active else remove_field(state.pattern, trigger)
    return ChannelRackState(
        channels=state.channels,
        pattern=pattern,
        step_count=TOTAL_FIELDS,
    )


# --- rack state / derived semantic version ---------------------------------- #


def build_32_field_channel_rack_state(
    live_kit: object, *, pattern_id: str = DEFAULT_PATTERN_ID
) -> ChannelRackState:
    """Project Live Kit channels into a fresh, *empty* 32-field rack.

    Reuses the live channel projection but does NOT inherit the legacy 16-step
    DEFAULT_ON seed: fresh 32-field initialization has no phantom triggers.
    """
    base = build_channel_rack_state(live_kit)
    return ChannelRackState(
        channels=base.channels,
        pattern=build_32_field_pattern(pattern_id),
        step_count=TOTAL_FIELDS,
    )


def require_32_field_channel_rack_state(state: object) -> ChannelRackState:
    if not isinstance(state, ChannelRackState):
        raise Arrangement32FieldTimeError("state must be a ChannelRackState")
    if state.step_count != TOTAL_FIELDS:
        raise Arrangement32FieldTimeError(
            "invalid_pattern_length: step_count must be 32, got "
            f"{state.step_count}"
        )
    require_32_field_pattern(state.pattern)
    return state


def add_user_channel_32_field(
    state: ChannelRackState,
    *,
    sample_path: str | None = None,
    channel_id: str | None = None,
) -> ChannelRackState:
    """Append a user channel with no auto-seeded triggers (no phantom fields).

    Under 32-field semantics a user-added channel starts empty until the user
    sets fields; the legacy sample-bearing DEFAULT_ON seed is not inherited.
    """
    require_32_field_channel_rack_state(state)
    existing = [channel.channel_id for channel in state.channels]
    new_id = channel_id if channel_id is not None else allocate_user_channel_id(existing)
    if new_id in existing:
        raise Arrangement32FieldTimeError(f"Duplicate channel_id: {new_id!r}")
    new_channel = Channel(
        channel_id=new_id,
        live_kit_group=None,
        live_kit_slot=None,
        sample_path=sample_path,
    )
    return ChannelRackState(
        channels=state.channels + (new_channel,),
        pattern=build_32_field_pattern(state.pattern.pattern_id, state.pattern.triggers),
        step_count=TOTAL_FIELDS,
    )


def time_semantics_version(
    step_count: object, length_quarter_notes: object
) -> str:
    """Derive the time-semantics version from ``(step_count, length)``.

    No persisted marker: the version is a pure function of the live rack shape.
    """
    if type(step_count) is not int or isinstance(step_count, bool):
        raise Arrangement32FieldTimeError(
            "corrupt_persistence_payload: step_count must be an exact int"
        )
    if type(length_quarter_notes) is not Fraction:
        raise Arrangement32FieldTimeError(
            "corrupt_persistence_payload: length_quarter_notes must be an exact Fraction"
        )
    if (
        step_count == TOTAL_FIELDS
        and length_quarter_notes == CYCLE_LENGTH_QUARTER_NOTES
    ):
        return TIME_SEMANTICS_32_FIELD_V1
    if (
        step_count == LEGACY_V1_STEP_COUNT
        and length_quarter_notes == LEGACY_V1_LENGTH_QUARTER_NOTES
    ):
        return TIME_SEMANTICS_LEGACY_V1
    if step_count == 64 or length_quarter_notes == Fraction(64, 1):
        raise Arrangement32FieldTimeError("sixty_four_field_state")
    raise Arrangement32FieldTimeError(
        "corrupt_persistence_payload: unrecognized "
        f"(step_count={step_count}, length={length_quarter_notes})"
    )


def channel_rack_time_semantics_version(state: ChannelRackState) -> str:
    """Derive the time-semantics version of a live rack state."""
    return time_semantics_version(state.step_count, state.pattern.length_quarter_notes)


def classify_channel_rack_state(state: object) -> Mapping[str, object]:
    """Fail-closed, never-raising classification of a live rack state.

    Production entry point for the #1086 runtime on the workbench rack path:
    derives the semantic version and, for legacy v1 racks, the frozen migration
    outcome. Never mutates the state and never activates a migration — a legacy
    DEFAULT_ON rack is surfaced as ``migration_required``, not converted.
    """
    if not isinstance(state, ChannelRackState):
        return {
            "semantic_version": None,
            "migration_outcome": None,
        }
    try:
        version = channel_rack_time_semantics_version(state)
    except Arrangement32FieldTimeError:
        return {
            "semantic_version": None,
            "migration_outcome": OUTCOME_REJECT_FAIL_CLOSED,
        }
    migration_outcome: str | None = None
    if version == TIME_SEMANTICS_LEGACY_V1:
        migration_outcome = migrate_legacy_channel_rack_state(state).outcome
    elif version == TIME_SEMANTICS_32_FIELD_V1:
        try:
            require_32_field_channel_rack_state(state)
        except Arrangement32FieldTimeError:
            migration_outcome = OUTCOME_REJECT_FAIL_CLOSED
    return {
        "semantic_version": version,
        "migration_outcome": migration_outcome,
    }


# --- 16-bar block projection ------------------------------------------------- #


@dataclass(frozen=True)
class ArrangementCycleProjection:
    """One of the two 8-bar cycles that make up the 16-bar block."""

    cycle_index: int
    absolute_quarter_offset: Fraction
    bars_one_based: tuple[int, int]


def project_arrangement_block(
    pattern: Pattern,
) -> tuple[ArrangementCycleProjection, ...]:
    """Project the 16-bar block as two cycles of the ONE Pattern identity."""
    require_32_field_pattern(pattern)
    return tuple(
        ArrangementCycleProjection(
            cycle_index=k,
            absolute_quarter_offset=Fraction(k, 1) * CYCLE_LENGTH_QUARTER_NOTES,
            bars_one_based=(
                k * BARS_PER_CYCLE + 1,
                (k + 1) * BARS_PER_CYCLE,
            ),
        )
        for k in range(ARRANGEMENT_BLOCK_CYCLES)
    )


# --- scheduling through the live one-pass seam ------------------------------- #


def plan_pattern_cycle(
    *,
    pattern: Pattern,
    channels_by_id: Mapping[str, Channel],
    tempo_map: TempoMap,
    cycle_index: int,
    block_start_quarter: Fraction,
    block_start_engine_frame: int,
) -> tuple[ScheduledTrigger, ...]:
    """Plan one 8-bar cycle's absolute engine frames via ``plan_pattern_once``.

    The cycle start frame is derived from :class:`TempoMap` (no wall clock, no
    hardcoded milliseconds); the block is a sequence of cycles of the same
    Pattern identity.
    """
    require_32_field_pattern(pattern)
    if type(cycle_index) is not int or isinstance(cycle_index, bool) or cycle_index < 0:
        raise Arrangement32FieldTimeError("cycle_index must be a non-negative int")
    if type(block_start_quarter) is not Fraction:
        raise Arrangement32FieldTimeError("block_start_quarter must be an exact Fraction")

    cycle_start_quarter = (
        block_start_quarter + Fraction(cycle_index, 1) * CYCLE_LENGTH_QUARTER_NOTES
    )
    block_start_session_frame = tempo_map.quarter_note_to_frame(block_start_quarter)
    cycle_start_session_frame = tempo_map.quarter_note_to_frame(cycle_start_quarter)
    cycle_start_engine_frame = block_start_engine_frame + (
        cycle_start_session_frame - block_start_session_frame
    )
    return plan_pattern_once(
        pattern=pattern,
        channels_by_id=channels_by_id,
        tempo_map=tempo_map,
        pattern_start_quarter=cycle_start_quarter,
        pattern_start_engine_frame=cycle_start_engine_frame,
    )


def plan_arrangement_block(
    *,
    pattern: Pattern,
    channels_by_id: Mapping[str, Channel],
    tempo_map: TempoMap,
    block_start_quarter: Fraction,
    block_start_engine_frame: int,
) -> tuple[tuple[ScheduledTrigger, ...], ...]:
    """Plan the full 16-bar block as two cycles of one Pattern identity."""
    return tuple(
        plan_pattern_cycle(
            pattern=pattern,
            channels_by_id=channels_by_id,
            tempo_map=tempo_map,
            cycle_index=cycle_index,
            block_start_quarter=block_start_quarter,
            block_start_engine_frame=block_start_engine_frame,
        )
        for cycle_index in range(ARRANGEMENT_BLOCK_CYCLES)
    )


# --- legacy v1 migration (pure execution) ------------------------------------ #


@dataclass(frozen=True)
class MigrationResult:
    """Outcome of classifying/migrating a legacy rack shape."""

    outcome: str
    reason: str
    semantic_version: str | None = None
    pattern: Pattern | None = None

    @property
    def activated(self) -> bool:
        """True only when a 32-field Pattern truth may be activated."""
        return self.pattern is not None


def _is_field_aligned_in_legacy_bar(position: Fraction) -> bool:
    return position.denominator == 1 and Fraction(0, 1) <= position < LEGACY_V1_LENGTH_QUARTER_NOTES


def _reject(reason: str) -> MigrationResult:
    return MigrationResult(outcome=OUTCOME_REJECT_FAIL_CLOSED, reason=reason)


def migrate_legacy_v1_rack(
    *,
    step_count: object,
    length_quarter_notes: object,
    triggers: Sequence[Trigger],
    pattern_id: str = DEFAULT_PATTERN_ID,
) -> MigrationResult:
    """Classify and (where lossless) migrate a legacy v1 rack shape.

    Faithful to the frozen outcomes:
    - recognized v1 shape ``(16, 4)`` only; anything else fails closed;
    - zero triggers → ``migrated_empty``;
    - all triggers field-aligned integers in ``[0, 4)`` →
      ``migrated_field_aligned_bar_replicated`` (``p + 4*k`` for ``k=0..7``,
      deduplicated);
    - recognizable but off-grid positions → ``migration_required`` (never
      auto-activated, never rounded/stretched);
    - positions outside the old Pattern bounds ``[0, 4)`` → ``migration_hold``.
    """
    if type(step_count) is not int or isinstance(step_count, bool):
        return _reject("unknown_or_malformed_legacy_step_count")
    if type(length_quarter_notes) is not Fraction:
        return _reject("corrupt_persistence_payload")

    if (step_count, length_quarter_notes) == (64, Fraction(64, 1)):
        return _reject("sixty_four_field_state")

    if (
        step_count != LEGACY_V1_STEP_COUNT
        or length_quarter_notes != LEGACY_V1_LENGTH_QUARTER_NOTES
    ):
        if (
            step_count == TOTAL_FIELDS
            and length_quarter_notes == CYCLE_LENGTH_QUARTER_NOTES
        ):
            return _reject("not_legacy_v1_shape")
        return _reject("unknown_or_malformed_legacy_step_count")

    materialized: list[Trigger] = []
    for trigger in triggers:
        if not isinstance(trigger, Trigger):
            return _reject("malformed_trigger_or_field_type")
        if type(trigger.position) is not Fraction:
            return _reject("malformed_trigger_or_field_type")
        if not (Fraction(0, 1) <= trigger.position < LEGACY_V1_LENGTH_QUARTER_NOTES):
            return MigrationResult(
                outcome=OUTCOME_MIGRATION_HOLD,
                reason="legacy_trigger_outside_old_pattern_bounds",
            )
        materialized.append(trigger)

    if not materialized:
        return MigrationResult(
            outcome=OUTCOME_MIGRATED_EMPTY,
            reason="legacy_v1_empty",
            semantic_version=TIME_SEMANTICS_32_FIELD_V1,
            pattern=build_32_field_pattern(pattern_id),
        )

    if all(_is_field_aligned_in_legacy_bar(t.position) for t in materialized):
        replicated: dict[tuple[str, Fraction], Trigger] = {}
        for trigger in materialized:
            seed = trigger.position.numerator
            for bar_offset in range(BARS_PER_CYCLE):
                position = Fraction(
                    seed + FIELDS_PER_BAR * bar_offset, 1
                )
                replicated[(trigger.channel_id, position)] = Trigger(
                    channel_id=trigger.channel_id, position=position
                )
        return MigrationResult(
            outcome=OUTCOME_MIGRATED_FIELD_ALIGNED_BAR_REPLICATED,
            reason="legacy_v1_field_aligned_bar_replicated",
            semantic_version=TIME_SEMANTICS_32_FIELD_V1,
            pattern=build_32_field_pattern(pattern_id, tuple(replicated.values())),
        )

    return MigrationResult(
        outcome=OUTCOME_MIGRATION_REQUIRED,
        reason="ambiguous_legacy_mapping",
    )


def classify_legacy_v1_rack(**kwargs: object) -> str:
    """Return just the migration outcome string for a legacy v1 rack shape."""
    return migrate_legacy_v1_rack(**kwargs).outcome  # type: ignore[arg-type]


def classify_unknown_legacy_state(
    *, reason: str = "user_added_unknown_legacy_state"
) -> MigrationResult:
    """Fail closed / HOLD for a legacy shape that cannot be proven lossless."""
    return MigrationResult(outcome=OUTCOME_MIGRATION_HOLD, reason=reason)


def migrate_legacy_channel_rack_state(state: ChannelRackState) -> MigrationResult:
    """Classify the Pattern truth of a live legacy rack state."""
    return migrate_legacy_v1_rack(
        step_count=state.step_count,
        length_quarter_notes=state.pattern.length_quarter_notes,
        triggers=state.pattern.triggers,
        pattern_id=state.pattern.pattern_id,
    )


def apply_migration(
    state: ChannelRackState, result: MigrationResult
) -> ChannelRackState | None:
    """Return the migrated 32-field state, or ``None`` when not activated."""
    if not result.activated:
        return None
    return ChannelRackState(
        channels=state.channels,
        pattern=result.pattern,
        step_count=TOTAL_FIELDS,
    )


__all__ = [
    "ARRANGEMENT_BLOCK_BARS",
    "ARRANGEMENT_BLOCK_CYCLES",
    "ARRANGEMENT_BLOCK_LENGTH_QUARTER_NOTES",
    "Arrangement32FieldTimeError",
    "ArrangementCycleProjection",
    "BARS_PER_CYCLE",
    "CYCLE_LENGTH_QUARTER_NOTES",
    "ChannelRackState",
    "DEFAULT_PATTERN_ID",
    "FAIL_CLOSED_IDS",
    "FIELDS_PER_BAR",
    "LEGACY_V1_LENGTH_QUARTER_NOTES",
    "LEGACY_V1_STEP_COUNT",
    "LEGACY_V1_STEP_TO_POSITION",
    "MAX_FIELDS_V1",
    "MIGRATION_OUTCOMES",
    "MigrationResult",
    "OUTCOME_MIGRATED_EMPTY",
    "OUTCOME_MIGRATED_FIELD_ALIGNED_BAR_REPLICATED",
    "OUTCOME_MIGRATION_HOLD",
    "OUTCOME_MIGRATION_REQUIRED",
    "OUTCOME_REJECT_FAIL_CLOSED",
    "Pattern",
    "QUARTER_NOTES_PER_FIELD",
    "SIXTY_FOUR_FIELDS_IN_V1",
    "TIME_SEMANTICS_32_FIELD_V1",
    "TIME_SEMANTICS_LEGACY_V1",
    "TOTAL_FIELDS",
    "TempoMap",
    "Trigger",
    "add_field",
    "add_user_channel_32_field",
    "apply_migration",
    "bar_start_fields",
    "build_32_field_channel_rack_state",
    "build_32_field_pattern",
    "channel_rack_time_semantics_version",
    "classify_channel_rack_state",
    "classify_legacy_v1_rack",
    "classify_unknown_legacy_state",
    "field_in_bar",
    "field_to_bar",
    "field_to_quarter_note",
    "migrate_legacy_channel_rack_state",
    "migrate_legacy_v1_rack",
    "plan_arrangement_block",
    "plan_pattern_cycle",
    "plan_pattern_once",
    "project_arrangement_block",
    "quarter_note_to_field",
    "remove_field",
    "require_32_field_channel_rack_state",
    "require_32_field_pattern",
    "set_field",
    "time_semantics_version",
    "toggle_field",
]
