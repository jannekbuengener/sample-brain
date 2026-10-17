"""#1080 Slice A — read-only Arrangement QML projection seam.

Immutable renderer-facing projection types over the merged Python-owned
seams. Python owns the projection mode (``WorkbenchSession`` #1078), the
single Pattern truth (``channel_rack`` / #1086 frozen 32-field model) and
the active-track identity. This module only *projects*; it never owns,
copies, or mutates Pattern, block, mask, marker, or persistence state.

Composed seams (no duplication):
- ``src.workbench_session`` — sole ``projection_mode`` / transition owner;
- ``src.arrangement_32_field_time`` — frozen 32-field / 8-bar geometry and
  the ``require_32_field_channel_rack_state`` validation;
- ``src.pattern_core`` — exact Fraction quarter-note Pattern identity.
"""

from __future__ import annotations

from dataclasses import dataclass

from .arrangement_32_field_time import (
    BARS_PER_CYCLE,
    FIELDS_PER_BAR,
    TOTAL_FIELDS,
    quarter_note_to_field,
    require_32_field_channel_rack_state,
)

PROJECTION_MODE_EDIT = "EDIT"
PROJECTION_MODE_ARRANGEMENT = "ARRANGEMENT"
_PROJECTION_MODES = frozenset({PROJECTION_MODE_EDIT, PROJECTION_MODE_ARRANGEMENT})


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
    if rack is not None:
        pattern_id = str(rack.pattern.pattern_id)
        active_fields = _active_field_indexes(rack)

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
    )


__all__ = [
    "ArrangementQmlBar",
    "ArrangementQmlField",
    "ArrangementQmlProjection",
    "PROJECTION_MODE_ARRANGEMENT",
    "PROJECTION_MODE_EDIT",
    "project_arrangement_for_qml",
]
