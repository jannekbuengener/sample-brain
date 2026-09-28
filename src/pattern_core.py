"""Minimal Pattern Core — Live Kit channels, triggers, and patterns.

Python-owned musical model between Live Kit assignments and a later sequencer.
Uses exact quarter-note ``Fraction`` positions. Does not schedule audio, own
PCM, or expose Screen-2 / Channel Rack surfaces.

Live Kit seed channels keep frozen IDs and provenance. User-added rack channels
use opaque IDs without Live Kit slots (#681). Trigger membership is validated
at the rack/context boundary, not against a global Live Kit ID universe alone.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass, field
from fractions import Fraction
from types import MappingProxyType
from typing import Mapping

from .workbench_live_kit import LIVE_KIT_SLOT_MAPPING

# Explicit opaque IDs — not derived from display-label slugification.
_FROZEN_CHANNEL_IDS: dict[tuple[str, str], str] = {
    ("Kick + Bass", "Kick"): "ch_kick",
    ("Kick + Bass", "Bass"): "ch_bass",
    ("Drums", "Main Drum"): "ch_main_drum",
    ("Drums", "Closed Hat"): "ch_closed_hat",
    ("Drums", "Open Hat"): "ch_open_hat",
    ("Drums", "Percussion"): "ch_percussion",
    ("Drums", "Additional"): "ch_additional",
    ("Melodic", "Lead"): "ch_lead",
    ("Melodic", "Pad"): "ch_pad",
    ("Atmos / FX", "Atmos"): "ch_atmos",
    ("Atmos / FX", "FX"): "ch_fx",
}

CHANNEL_ID_BY_LIVE_KIT_SLOT: Mapping[tuple[str, str], str] = MappingProxyType(
    {
        (group, slot): _FROZEN_CHANNEL_IDS[(group, slot)]
        for group, slots in LIVE_KIT_SLOT_MAPPING
        for slot in slots
    }
)

_CANONICAL_CHANNEL_IDS: frozenset[str] = frozenset(CHANNEL_ID_BY_LIVE_KIT_SLOT.values())

USER_CHANNEL_ID_PREFIX = "ch_user_"


def channel_id_for_live_kit_slot(group: str, slot: str) -> str:
    """Return the stable channel_id for a canonical Live Kit (group, slot)."""
    try:
        return CHANNEL_ID_BY_LIVE_KIT_SLOT[(group, slot)]
    except KeyError as exc:
        raise ValueError(f"Unknown Live Kit slot: {group!r} -> {slot!r}") from exc


def allocate_user_channel_id(existing_ids: Iterable[str]) -> str:
    """Allocate a stable opaque user channel_id not colliding with existing IDs."""
    existing = set(existing_ids) | set(_CANONICAL_CHANNEL_IDS)
    n = 1
    while True:
        candidate = f"{USER_CHANNEL_ID_PREFIX}{n}"
        if candidate not in existing:
            return candidate
        n += 1


def require_triggers_reference_known_channels(
    triggers: Iterable[Trigger],
    *,
    known_channel_ids: Collection[str],
) -> None:
    """Fail closed when any trigger references a channel outside the context."""
    known = frozenset(known_channel_ids)
    for trigger in triggers:
        if trigger.channel_id not in known:
            raise ValueError(f"Unknown channel_id: {trigger.channel_id!r}")


def _require_fraction(value: object, *, name: str) -> Fraction:
    if type(value) is not Fraction:
        raise TypeError(f"{name} must be an exact Fraction (got {type(value).__name__})")
    return value


def _require_non_empty_channel_id(channel_id: object) -> str:
    if not isinstance(channel_id, str) or channel_id == "":
        raise ValueError("channel_id must be a non-empty string")
    return channel_id


@dataclass(frozen=True)
class Channel:
    """Stable instrument lane that references a sample path (or None).

    Live Kit seed channels carry matching group/slot provenance. User-added
    channels set both provenance fields to None and use a non-canonical opaque ID.
    """

    channel_id: str
    live_kit_group: str | None
    live_kit_slot: str | None
    sample_path: str | None

    def __post_init__(self) -> None:
        channel_id = _require_non_empty_channel_id(self.channel_id)
        object.__setattr__(self, "channel_id", channel_id)

        group = self.live_kit_group
        slot = self.live_kit_slot
        if (group is None) ^ (slot is None):
            raise ValueError(
                "live_kit_group and live_kit_slot must both be set or both be None"
            )

        if group is not None and slot is not None:
            try:
                expected = channel_id_for_live_kit_slot(group, slot)
            except ValueError as exc:
                raise ValueError(
                    f"Unknown Live Kit slot: {group!r} -> {slot!r}"
                ) from exc
            if expected != channel_id:
                raise ValueError(
                    f"channel_id {channel_id!r} does not match "
                    f"{group!r}/{slot!r} (expected {expected!r})"
                )
        elif channel_id in _CANONICAL_CHANNEL_IDS:
            raise ValueError(
                f"canonical Live Kit channel_id {channel_id!r} requires "
                "live_kit_group/live_kit_slot provenance"
            )

        if self.sample_path is not None and not isinstance(self.sample_path, str):
            raise TypeError("sample_path must be str or None")


@dataclass(frozen=True)
class Trigger:
    """Point trigger at an exact quarter-note musical position."""

    channel_id: str
    position: Fraction

    def __post_init__(self) -> None:
        channel_id = _require_non_empty_channel_id(self.channel_id)
        object.__setattr__(self, "channel_id", channel_id)
        position = _require_fraction(self.position, name="position")
        if position < Fraction(0, 1):
            raise ValueError("position must be >= 0")
        object.__setattr__(self, "position", position)


@dataclass(frozen=True)
class Pattern:
    """Finite musical loop holding normalized triggers."""

    pattern_id: str
    length_quarter_notes: Fraction
    triggers: tuple[Trigger, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.pattern_id, str) or self.pattern_id == "":
            raise ValueError("pattern_id must be a non-empty string")
        length = _require_fraction(
            self.length_quarter_notes, name="length_quarter_notes"
        )
        if length <= Fraction(0, 1):
            raise ValueError("length_quarter_notes must be > 0")
        object.__setattr__(self, "length_quarter_notes", length)

        raw: Iterable[Trigger] = self.triggers
        normalized = tuple(
            sorted(raw, key=lambda t: (t.position, t.channel_id))
        )
        for trigger in normalized:
            if not isinstance(trigger, Trigger):
                raise TypeError("triggers must contain Trigger instances")
            if not (Fraction(0, 1) <= trigger.position < length):
                raise ValueError(
                    f"trigger position {trigger.position} must satisfy "
                    f"0 <= position < {length}"
                )
        object.__setattr__(self, "triggers", normalized)


__all__ = [
    "CHANNEL_ID_BY_LIVE_KIT_SLOT",
    "USER_CHANNEL_ID_PREFIX",
    "Channel",
    "Pattern",
    "Trigger",
    "allocate_user_channel_id",
    "channel_id_for_live_kit_slot",
    "require_triggers_reference_known_channels",
]
