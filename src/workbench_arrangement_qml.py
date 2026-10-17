"""#1080 Arrangement projection/intents — Slice A/B sequencer + C1 masks.

Immutable renderer-facing projection types over the merged Python-owned
seams. Python owns the projection mode (``WorkbenchSession`` #1078), the
single Pattern truth (``channel_rack`` / #1086 frozen 32-field model), the
channel classification (``sample_class_for_channel`` single consumption
point), and the active-track identity. This module only *projects* and, since
Slice B, routes field-click intents and, since C1, bounded block/group/track
mask intents through the existing Python owners. It owns no musical store.

Composed seams (no duplication):
- ``src.workbench_session`` — sole ``projection_mode`` / transition owner;
- ``src.arrangement_32_field_time`` — frozen 32-field / 8-bar geometry, the
  ``require_32_field_channel_rack_state`` validation, and the exact
  field ↔ quarter-note authority;
- ``src.channel_rack`` — classification authority
  (``sample_class_for_channel`` / ``is_point_trigger_safe``);
- ``src.workbench_channel_rack`` — row-kind vocabulary and the single
  ``ChannelRackController.toggle_arrangement_field`` mutation command.
- ``src.arrangement_domain`` — group membership, masks and block eligibility;
- ``WorkbenchSession.set_arrangement_state`` — existing active-track save owner.
"""

from __future__ import annotations

from dataclasses import dataclass

from .arrangement_32_field_time import (
    BARS_PER_CYCLE,
    FIELDS_PER_BAR,
    TOTAL_FIELDS,
    field_to_quarter_note,
    quarter_note_to_field,
    require_32_field_channel_rack_state,
)
from .channel_rack import is_point_trigger_safe, sample_class_for_channel
from .arrangement_domain import ArrangementError, ArrangementState
from .workbench_channel_rack import ROW_KIND_LOOP_IDENTITY, ROW_KIND_STEP

PROJECTION_MODE_EDIT = "EDIT"
PROJECTION_MODE_ARRANGEMENT = "ARRANGEMENT"
_PROJECTION_MODES = frozenset({PROJECTION_MODE_EDIT, PROJECTION_MODE_ARRANGEMENT})

# --- QML field-click intent outcomes (fail-closed vocabulary, Slice B) ---------- #

ARRANGEMENT_FIELD_TOGGLE_MUTATED = "mutated"
ARRANGEMENT_FIELD_TOGGLE_NO_RACK_STATE = "no_rack_state"
ARRANGEMENT_FIELD_TOGGLE_LEGACY_RACK = "legacy_rack_fail_closed"
ARRANGEMENT_FIELD_TOGGLE_UNKNOWN_CHANNEL = "unknown_channel"
ARRANGEMENT_FIELD_TOGGLE_ROW_NOT_EDITABLE = "row_not_editable"
ARRANGEMENT_FIELD_TOGGLE_INVALID_FIELD = "invalid_field_index"
ARRANGEMENT_FIELD_TOGGLE_FAIL_CLOSED = "fail_closed"


@dataclass(frozen=True)
class ArrangementQmlField:
    """One read-only sequencer field in the 32-field cycle."""

    index: int
    bar_index: int
    index_in_bar: int
    active: bool


@dataclass(frozen=True)
class ArrangementQmlBar:
    """One bar grouping of exactly four fields."""

    index: int
    fields: tuple[ArrangementQmlField, ...]


@dataclass(frozen=True)
class ArrangementQmlChannelRow:
    """Renderer-facing channel row over the single Pattern truth (#1080 Slice B).

    ``fields``/``bars`` carry this channel's per-field trigger presence in the
    frozen 32-field / 8-bar geometry. ``step_grid_enabled`` comes from the one
    existing classification authority (point-trigger-safe one-shot only);
    loop / ambiguous channels remain visible identity rows without an
    editable trigger matrix. No sample metadata is stored as new truth here.
    """

    channel_id: str
    display_name: str
    row_kind: str
    step_grid_enabled: bool
    fields: tuple[ArrangementQmlField, ...]
    bars: tuple[ArrangementQmlBar, ...]


@dataclass(frozen=True)
class ArrangementQmlProjection:
    """Immutable renderer-facing Arrangement projection (identity only)."""

    projection_mode: str
    active_track_id: str | None
    pattern_id: str
    field_count: int
    bar_count: int
    fields_per_bar: int
    bars: tuple[ArrangementQmlBar, ...]
    any_active_step: bool
    channel_rows: tuple[ArrangementQmlChannelRow, ...] = ()


def _active_field_indexes(rack: object) -> frozenset[int]:
    """Field indexes with at least one canonical trigger, fail-closed.

    A rack that is not a valid 32-field truth (e.g. a legacy v1 rack pending
    explicit migration) projects no active fields — it is never silently
    reinterpreted here.
    """
    try:
        require_32_field_channel_rack_state(rack)
    except (TypeError, ValueError):
        return frozenset()
    return frozenset(
        quarter_note_to_field(trigger.position)
        for trigger in rack.pattern.triggers
    )


def _channel_display_name(channel: object) -> str:
    """Established row naming: Live Kit slot name, else the user channel id."""
    if channel.live_kit_group is not None or channel.live_kit_slot is not None:
        return channel.live_kit_slot or channel.channel_id
    return channel.channel_id.replace("ch_user_", "User ")


def _channel_rows_for_rack(
    controller: object, rack: object
) -> tuple[ArrangementQmlChannelRow, ...]:
    """Project renderer-facing channel rows from the one rack truth.

    Fail-closed: a rack that is not a valid 32-field truth (legacy v1 or
    malformed) projects no rows rather than being reinterpreted. Occupied
    channels only, mirroring the bottom-Rack occupancy rule. Classification
    flows through the single ``sample_class_for_channel`` consumption point;
    a missing Live Kit owner fails closed to identity rows.
    """
    try:
        require_32_field_channel_rack_state(rack)
    except (TypeError, ValueError):
        return ()
    live_kit = getattr(controller, "live_kit", None)
    user_metadata = getattr(controller, "user_metadata", None)
    active_by_channel: dict[str, set[int]] = {}
    for trigger in rack.pattern.triggers:
        active_by_channel.setdefault(trigger.channel_id, set()).add(
            quarter_note_to_field(trigger.position)
        )
    rows: list[ArrangementQmlChannelRow] = []
    for channel in rack.channels:
        if channel.sample_path is None or channel.sample_path == "":
            continue
        resolved = None
        if live_kit is not None:
            resolved = sample_class_for_channel(
                channel, live_kit, user_metadata=user_metadata
            )
        step_grid_enabled = is_point_trigger_safe(resolved)
        active = active_by_channel.get(channel.channel_id, frozenset())
        fields = tuple(
            ArrangementQmlField(
                index=index,
                bar_index=index // FIELDS_PER_BAR,
                index_in_bar=index % FIELDS_PER_BAR,
                active=index in active,
            )
            for index in range(TOTAL_FIELDS)
        )
        bars = tuple(
            ArrangementQmlBar(
                index=bar_index,
                fields=fields[
                    bar_index * FIELDS_PER_BAR : (bar_index + 1) * FIELDS_PER_BAR
                ],
            )
            for bar_index in range(BARS_PER_CYCLE)
        )
        rows.append(
            ArrangementQmlChannelRow(
                channel_id=channel.channel_id,
                display_name=_channel_display_name(channel),
                row_kind=ROW_KIND_STEP if step_grid_enabled else ROW_KIND_LOOP_IDENTITY,
                step_grid_enabled=step_grid_enabled,
                fields=fields,
                bars=bars,
            )
        )
    return tuple(rows)


def project_arrangement_for_qml(session: object) -> ArrangementQmlProjection:
    """Project the session's Arrangement state for the QML renderer.

    Fail-closed on an unknown ``projection_mode`` vocabulary; total for a
    missing rack (complete, inert 32-field geometry) because the mode owner
    guarantees a valid 32-field Pattern in ``ARRANGEMENT`` mode anyway.
    """
    mode = getattr(session, "projection_mode", PROJECTION_MODE_EDIT)
    if mode not in _PROJECTION_MODES:
        raise ValueError(f"unknown_projection_mode: {mode!r}")

    active_track_id = getattr(session, "active_track_id", None)
    pattern_id = ""
    active_fields: frozenset[int] = frozenset()
    controller = getattr(session, "channel_rack", None)
    rack = getattr(controller, "state", None) if controller is not None else None
    channel_rows: tuple[ArrangementQmlChannelRow, ...] = ()
    if rack is not None:
        pattern_id = str(rack.pattern.pattern_id)
        active_fields = _active_field_indexes(rack)
        channel_rows = _channel_rows_for_rack(controller, rack)

    fields = tuple(
        ArrangementQmlField(
            index=index,
            bar_index=index // FIELDS_PER_BAR,
            index_in_bar=index % FIELDS_PER_BAR,
            active=index in active_fields,
        )
        for index in range(TOTAL_FIELDS)
    )
    bars = tuple(
        ArrangementQmlBar(
            index=bar_index,
            fields=fields[
                bar_index * FIELDS_PER_BAR : (bar_index + 1) * FIELDS_PER_BAR
            ],
        )
        for bar_index in range(BARS_PER_CYCLE)
    )
    return ArrangementQmlProjection(
        projection_mode=mode,
        active_track_id=active_track_id,
        pattern_id=pattern_id,
        field_count=TOTAL_FIELDS,
        bar_count=BARS_PER_CYCLE,
        fields_per_bar=FIELDS_PER_BAR,
        bars=bars,
        any_active_step=bool(active_fields),
        channel_rows=channel_rows,
    )


@dataclass(frozen=True)
class ArrangementFieldToggleResult:
    """Outcome of one QML field-click intent routed through this seam."""

    ok: bool
    outcome: str


def request_arrangement_field_toggle(
    session: object, channel_id: str, field_index: int
) -> ArrangementFieldToggleResult:
    """Python interaction seam for the QML arrangement field click (#1080 Slice B).

    QML sends only ``channel_id`` and ``field_index``. This seam owns the
    editability decision through the projected rows (the same classification
    authority the renderer sees), validates the field only through the frozen
    #1086 geometry, and routes the mutation to the single
    :meth:`ChannelRackController.toggle_arrangement_field` command on the one
    Pattern truth. Fail-closed everywhere: no silent migration, no guessed
    quarter-note semantics, never the legacy ``step_index / 4`` mapping.
    """
    controller = getattr(session, "channel_rack", None)
    state = getattr(controller, "state", None) if controller is not None else None
    if state is None:
        return ArrangementFieldToggleResult(
            False, ARRANGEMENT_FIELD_TOGGLE_NO_RACK_STATE
        )
    try:
        require_32_field_channel_rack_state(state)
    except (TypeError, ValueError):
        return ArrangementFieldToggleResult(
            False, ARRANGEMENT_FIELD_TOGGLE_LEGACY_RACK
        )
    row = next(
        (
            channel_row
            for channel_row in project_arrangement_for_qml(session).channel_rows
            if channel_row.channel_id == channel_id
        ),
        None,
    )
    if row is None:
        return ArrangementFieldToggleResult(
            False, ARRANGEMENT_FIELD_TOGGLE_UNKNOWN_CHANNEL
        )
    if not row.step_grid_enabled:
        return ArrangementFieldToggleResult(
            False, ARRANGEMENT_FIELD_TOGGLE_ROW_NOT_EDITABLE
        )
    try:
        field_to_quarter_note(field_index)
    except (TypeError, ValueError):
        return ArrangementFieldToggleResult(
            False, ARRANGEMENT_FIELD_TOGGLE_INVALID_FIELD
        )
    try:
        controller.toggle_arrangement_field(channel_id, field_index)
    except (TypeError, ValueError):
        # Remaining fail-closed rejections (e.g. a deferred user-channel
        # mutation from an active Rack Play) surface without any mutation.
        return ArrangementFieldToggleResult(
            False, ARRANGEMENT_FIELD_TOGGLE_FAIL_CLOSED
        )
    return ArrangementFieldToggleResult(True, ARRANGEMENT_FIELD_TOGGLE_MUTATED)


@dataclass(frozen=True)
class ArrangementQmlGroup:
    group_id: str
    display_name: str
    channel_ids: tuple[str, ...]


@dataclass(frozen=True)
class ArrangementQmlBlock:
    block_index: int
    status: str
    enabled: bool


@dataclass(frozen=True)
class ArrangementQmlGroupBlock:
    group_id: str
    block_index: int
    enabled: bool
    available: bool


@dataclass(frozen=True)
class ArrangementQmlTrackBlock:
    channel_id: str
    group_id: str
    block_index: int
    enabled: bool
    effective: bool | str


@dataclass(frozen=True)
class ArrangementBlockWindow:
    groups: tuple[ArrangementQmlGroup, ...]
    blocks: tuple[ArrangementQmlBlock, ...]
    group_blocks: tuple[ArrangementQmlGroupBlock, ...]
    track_blocks: tuple[ArrangementQmlTrackBlock, ...]
    membership_status: str


_GROUP_LABELS = {
    "pg_baseline": "Baseline",
    "pg_drums": "Drums",
    "pg_melodic_atmos_fx": "Melodic / Atmos / FX",
    "pg_vocals": "Vocals",
}


def _arrangement_context(session: object) -> tuple:
    state = session.arrangement_state
    if not isinstance(state, ArrangementState):
        raise ArrangementError("no_arrangement_state")
    rack = session.channel_rack.state
    state.validate(rack)
    return state, rack, session.transport.tempo_map


def project_arrangement_block_window(
    session: object, start_block: int, block_count: int
) -> ArrangementBlockWindow:
    """Pure bounded projection; all timing/eligibility comes from #1087.

    Out-of-horizon masks remain visible as intent, with explicit unavailable
    effective state. Unknown channels remain unmapped, never guessed or lost.
    """
    if any(type(v) is not int or v < 0 for v in (start_block, block_count)):
        raise ArrangementError("invalid_block_window")
    state, rack, tempo_map = _arrangement_context(session)
    groups = tuple(
        ArrangementQmlGroup(g, _GROUP_LABELS[g], channels)
        for g, channels in state.groups(rack).items()
    )
    blocks = tuple(
        ArrangementQmlBlock(i, state.block_status(i, tempo_map),
                            i not in state.disabled_blocks)
        for i in range(start_block, start_block + block_count)
    )
    group_blocks = tuple(
        ArrangementQmlGroupBlock(
            g.group_id, b.block_index,
            (g.group_id, b.block_index) not in state.disabled_group_blocks,
            b.status == "eligible" and b.enabled
            and (g.group_id, b.block_index) not in state.disabled_group_blocks,
        )
        for b in blocks for g in groups
    )
    track_blocks = tuple(
        ArrangementQmlTrackBlock(
            c.channel_id, state.membership(c.channel_id, rack), b.block_index,
            (c.channel_id, b.block_index) not in state.disabled_track_blocks,
            state.effective(c.channel_id, b.block_index, rack, tempo_map)
            if b.status == "eligible" else b.status,
        )
        for b in blocks for c in rack.channels
    )
    return ArrangementBlockWindow(
        groups, blocks, group_blocks, track_blocks, state.membership_status(rack)
    )


@dataclass(frozen=True)
class ArrangementMaskToggleResult:
    ok: bool
    outcome: str
    projection: ArrangementBlockWindow | None = None


def _request_mask_toggle(
    session: object, kind: str, block_index: int, identity: str | None = None
) -> ArrangementMaskToggleResult:
    """Validate before one immutable domain command and one owner save.

    Success denotes accepted musical intent. The existing session owner's
    dirty/status fields remain authoritative for disk-write failures/retries.
    """
    try:
        state, rack, tempo_map = _arrangement_context(session)
        status = state.block_status(block_index, tempo_map)
        if status != "eligible":
            raise ArrangementError(status)
        if kind == "group":
            if not isinstance(identity, str) or identity not in state.groups(rack):
                raise ArrangementError("unknown_group_id")
            updated = state.set_group(
                identity, block_index,
                (identity, block_index) in state.disabled_group_blocks, tempo_map,
            )
        elif kind == "track":
            membership = state.membership(identity, rack)
            if membership == "unmapped" or state.membership_status(rack) == "migration_required":
                raise ArrangementError("migration_required")
            updated = state.set_track(
                identity, block_index,
                (identity, block_index) in state.disabled_track_blocks, rack, tempo_map,
            )
        else:
            updated = state.set_block(
                block_index, block_index in state.disabled_blocks, tempo_map
            )
        session.set_arrangement_state(updated)
    except (TypeError, ValueError, AttributeError) as exc:
        return ArrangementMaskToggleResult(False, str(exc))
    return ArrangementMaskToggleResult(
        True, "mutated", project_arrangement_block_window(session, block_index, 1)
    )


def request_arrangement_block_toggle(
    session: object, block_index: int
) -> ArrangementMaskToggleResult:
    return _request_mask_toggle(session, "block", block_index)


def request_arrangement_group_toggle(
    session: object, group_id: str, block_index: int
) -> ArrangementMaskToggleResult:
    return _request_mask_toggle(session, "group", block_index, group_id)


def request_arrangement_track_toggle(
    session: object, channel_id: str, block_index: int
) -> ArrangementMaskToggleResult:
    return _request_mask_toggle(session, "track", block_index, channel_id)


__all__ = [
    "ArrangementQmlGroup",
    "ArrangementQmlBlock",
    "ArrangementQmlGroupBlock",
    "ArrangementQmlTrackBlock",
    "ArrangementBlockWindow",
    "ArrangementMaskToggleResult",
    "project_arrangement_block_window",
    "request_arrangement_block_toggle",
    "request_arrangement_group_toggle",
    "request_arrangement_track_toggle",
    "ARRANGEMENT_FIELD_TOGGLE_FAIL_CLOSED",
    "ARRANGEMENT_FIELD_TOGGLE_INVALID_FIELD",
    "ARRANGEMENT_FIELD_TOGGLE_LEGACY_RACK",
    "ARRANGEMENT_FIELD_TOGGLE_MUTATED",
    "ARRANGEMENT_FIELD_TOGGLE_NO_RACK_STATE",
    "ARRANGEMENT_FIELD_TOGGLE_ROW_NOT_EDITABLE",
    "ARRANGEMENT_FIELD_TOGGLE_UNKNOWN_CHANNEL",
    "ArrangementFieldToggleResult",
    "ArrangementQmlBar",
    "ArrangementQmlChannelRow",
    "ArrangementQmlField",
    "ArrangementQmlProjection",
    "PROJECTION_MODE_ARRANGEMENT",
    "PROJECTION_MODE_EDIT",
    "project_arrangement_for_qml",
    "request_arrangement_field_toggle",
]
