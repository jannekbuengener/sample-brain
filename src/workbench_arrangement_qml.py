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
from fractions import Fraction

from .arrangement_32_field_time import (
    ARRANGEMENT_BLOCK_LENGTH_QUARTER_NOTES,
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
class ArrangementQmlTrackRow:
    """Renderer-facing track row within an expanded group (C2b).

    Membership comes exclusively from Python-owned arrangement_domain.
    Each track row shares the visible block window geometry with its parent group.
    """
    channel_id: str
    display_name: str
    group_id: str
    blocks: tuple[ArrangementQmlTrackBlock, ...]


@dataclass(frozen=True)
class ArrangementBlockWindow:
    groups: tuple[ArrangementQmlGroup, ...]
    blocks: tuple[ArrangementQmlBlock, ...]
    group_blocks: tuple[ArrangementQmlGroupBlock, ...]
    track_blocks: tuple[ArrangementQmlTrackBlock, ...]
    membership_status: str
    track_rows_by_group: dict[str, tuple[ArrangementQmlTrackRow, ...]] = ()


@dataclass(frozen=True)
class ArrangementViewportState:
    """Renderer-facing Arrangement viewport / zoom/pan presentation state.

    All values are pure presentation state — not persistent musical truth.
    The logical horizon comes from TempoMap / domain authority, never from
    QML-owned constants.
    """

    start_quarter_note: Fraction
    visible_duration_qn: Fraction
    zoom_level: float
    logical_horizon_qn: Fraction


# --- Viewport / zoom / pan constants ---------------------------------------- #

BASE_VISIBLE_SECONDS = 180  # ~3 minutes initial view
HORIZON_SECONDS = 600  # 10-minute logical horizon
MIN_VISIBLE_SECONDS = 30  # minimum visible duration for block readability

# Discrete, deterministic zoom levels (multiplier on base visible duration).
# Higher = zoomed in (less time visible). Lower = zoomed out.
ZOOM_LEVELS: tuple[float, ...] = (0.25, 0.5, 1.0, 2.0, 4.0)
ZOOM_STEP = 2.0

# Small overscan beyond the visible window so edge blocks don't pop in/out.
OVSCAN_BLOCKS = 1

_GROUP_LABELS = {
    "pg_baseline": "Baseline",
    "pg_drums": "Drums",
    "pg_melodic_atmos_fx": "Melodic / Atmos / FX",
    "pg_vocals": "Vocals",
}

# Allocation budget per call, independent of tempo/musical horizon. Consumers
# page larger viewports through multiple windows; no implicit horizon list.
MAX_ARRANGEMENT_BLOCK_WINDOW = 64


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
    if block_count > MAX_ARRANGEMENT_BLOCK_WINDOW:
        raise ArrangementError("block_window_too_large")
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
            "unresolved" if state.membership(c.channel_id, rack) == "unmapped"
            else state.effective(c.channel_id, b.block_index, rack, tempo_map)
            if b.status == "eligible" else b.status,
        )
        for b in blocks for c in rack.channels
    )

    # C2b: Project track rows per group from Python-owned membership
    track_rows_by_group: dict[str, tuple[ArrangementQmlTrackRow, ...]] = {}
    for group in groups:
        group_track_rows: list[ArrangementQmlTrackRow] = []
        for channel_id in group.channel_ids:
            # Find the channel in rack to get display name
            channel = next((c for c in rack.channels if c.channel_id == channel_id), None)
            if channel is None:
                continue
            display_name = _channel_display_name(channel)
            membership = state.membership(channel_id, rack)
            if membership == "unmapped":
                continue
            track_row_blocks = tuple(
                ArrangementQmlTrackBlock(
                    channel_id, group.group_id, b.block_index,
                    (channel_id, b.block_index) not in state.disabled_track_blocks,
                    "unresolved" if membership == "unmapped"
                    else state.effective(channel_id, b.block_index, rack, tempo_map)
                    if b.status == "eligible" else b.status,
                )
                for b in blocks
            )
            group_track_rows.append(
                ArrangementQmlTrackRow(
                    channel_id=channel_id,
                    display_name=display_name,
                    group_id=group.group_id,
                    blocks=track_row_blocks,
                )
            )
        track_rows_by_group[group.group_id] = tuple(group_track_rows)

    return ArrangementBlockWindow(
        groups, blocks, group_blocks, track_blocks, state.membership_status(rack),
        track_rows_by_group=track_rows_by_group
    )


def _quarter_note_to_block_index(qn: Fraction) -> int:
    """Convert a quarter-note position to the containing block index."""
    return int(qn // ARRANGEMENT_BLOCK_LENGTH_QUARTER_NOTES)


def _block_index_to_quarter_note(block_index: int) -> Fraction:
    """Convert a block index to its starting quarter-note position."""
    return Fraction(block_index, 1) * ARRANGEMENT_BLOCK_LENGTH_QUARTER_NOTES


def viewport_for_initial_view(tempo_map) -> ArrangementViewportState:
    """Create the initial ~3-minute viewport from TempoMap authority.

    Visible duration is derived from ``BASE_VISIBLE_SECONDS`` through the
    TempoMap's frame→quarter-note mapping — no QML-owned seconds↔QN math.
    Logical horizon is the 10-minute domain horizon.
    """
    sample_rate = tempo_map.sample_rate
    visible_qn = tempo_map.frame_to_quarter_note(BASE_VISIBLE_SECONDS * sample_rate)
    horizon_qn = tempo_map.frame_to_quarter_note(HORIZON_SECONDS * sample_rate)
    return ArrangementViewportState(
        start_quarter_note=Fraction(0),
        visible_duration_qn=visible_qn,
        zoom_level=1.0,
        logical_horizon_qn=horizon_qn,
    )


def _clamp_viewport_start(viewport: ArrangementViewportState) -> Fraction:
    """Clamp viewport start to [0, horizon - visible_duration]."""
    max_start = viewport.logical_horizon_qn - viewport.visible_duration_qn
    if max_start < 0:
        max_start = Fraction(0)
    start = viewport.start_quarter_note
    if start < 0:
        return Fraction(0)
    if start > max_start:
        return max_start
    return start


def _visible_duration_for_zoom(zoom_level: float, tempo_map) -> Fraction:
    """Visible duration in QN for a given zoom level, derived from TempoMap."""
    sample_rate = tempo_map.sample_rate
    base_qn = tempo_map.frame_to_quarter_note(BASE_VISIBLE_SECONDS * sample_rate)
    return base_qn / Fraction(str(zoom_level))


def zoom_in(viewport: ArrangementViewportState, anchor_qn: Fraction, tempo_map) -> ArrangementViewportState:
    """Zoom in: reduce visible duration, keep anchor area stable.

    Moves to the next more-zoomed-in discrete level. Clamped at the maximum
    zoom level for block readability.
    """
    try:
        current_index = list(ZOOM_LEVELS).index(viewport.zoom_level)
    except ValueError:
        current_index = 2  # default to 1.0
    next_index = min(current_index + 1, len(ZOOM_LEVELS) - 1)
    new_level = ZOOM_LEVELS[next_index]
    new_duration = _visible_duration_for_zoom(new_level, tempo_map)

    # Re-anchor: keep the anchor within the new visible window where possible.
    new_start = anchor_qn - (new_duration / 2)
    new_start = max(Fraction(0), new_start)

    return ArrangementViewportState(
        start_quarter_note=new_start,
        visible_duration_qn=new_duration,
        zoom_level=new_level,
        logical_horizon_qn=viewport.logical_horizon_qn,
    )


def zoom_out(viewport: ArrangementViewportState, anchor_qn: Fraction, tempo_map) -> ArrangementViewportState:
    """Zoom out: increase visible duration, clamped at the logical horizon.

    Moves to the next less-zoomed-in discrete level. Clamped so the visible
    duration never exceeds the logical horizon.
    """
    try:
        current_index = list(ZOOM_LEVELS).index(viewport.zoom_level)
    except ValueError:
        current_index = 2  # default to 1.0
    next_index = max(current_index - 1, 0)
    new_level = ZOOM_LEVELS[next_index]
    new_duration = _visible_duration_for_zoom(new_level, tempo_map)

    # Clamp visible duration to logical horizon
    if new_duration > viewport.logical_horizon_qn:
        new_duration = viewport.logical_horizon_qn

    new_start = _clamp_viewport_start(
        ArrangementViewportState(
            start_quarter_note=viewport.start_quarter_note,
            visible_duration_qn=new_duration,
            zoom_level=new_level,
            logical_horizon_qn=viewport.logical_horizon_qn,
        )
    )

    return ArrangementViewportState(
        start_quarter_note=new_start,
        visible_duration_qn=new_duration,
        zoom_level=new_level,
        logical_horizon_qn=viewport.logical_horizon_qn,
    )


def pan(viewport: ArrangementViewportState, delta_qn: Fraction) -> ArrangementViewportState:
    """Horizontal pan: changes only viewport start, clamped to valid range."""
    new_start = _clamp_viewport_start(
        ArrangementViewportState(
            start_quarter_note=viewport.start_quarter_note + delta_qn,
            visible_duration_qn=viewport.visible_duration_qn,
            zoom_level=viewport.zoom_level,
            logical_horizon_qn=viewport.logical_horizon_qn,
        )
    )
    return ArrangementViewportState(
        start_quarter_note=new_start,
        visible_duration_qn=viewport.visible_duration_qn,
        zoom_level=viewport.zoom_level,
        logical_horizon_qn=viewport.logical_horizon_qn,
    )


def project_visible_blocks(session, viewport: ArrangementViewportState) -> ArrangementBlockWindow:
    """Project only blocks visible within the viewport + small overscan.

    Replaces the fixed block-window assumption with a viewport-driven bounded
    projection. Only currently-visible blocks (plus OVSCAN_BLOCKS overscan)
    are materialized — never the full horizon.
    """
    state, rack, tempo_map = _arrangement_context(session)

    start_qn = viewport.start_quarter_note
    end_qn = start_qn + viewport.visible_duration_qn

    # Determine block range covering the viewport, plus overscan.
    start_block = _quarter_note_to_block_index(start_qn) - OVSCAN_BLOCKS
    end_block = _quarter_note_to_block_index(end_qn) + 1 + OVSCAN_BLOCKS

    # Clamp to valid block range: [0, horizon_blocks]
    horizon_block = _quarter_note_to_block_index(viewport.logical_horizon_qn)
    start_block = max(0, start_block)
    end_block = min(end_block, horizon_block + 1)

    block_count = end_block - start_block
    if block_count <= 0:
        block_count = 1

    return project_arrangement_block_window(session, start_block, block_count)


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
    "MAX_ARRANGEMENT_BLOCK_WINDOW",
    "ArrangementQmlGroup",
    "ArrangementQmlBlock",
    "ArrangementQmlGroupBlock",
    "ArrangementQmlTrackBlock",
    "ArrangementQmlTrackRow",
    "ArrangementBlockWindow",
    "ArrangementViewportState",
    "ArrangementMaskToggleResult",
    "project_arrangement_block_window",
    "project_visible_blocks",
    "viewport_for_initial_view",
    "zoom_in",
    "zoom_out",
    "pan",
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
