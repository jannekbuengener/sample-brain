"""Minimal Pattern Core — Live Kit channels, triggers, and patterns.

Python-owned musical model between Live Kit assignments and a later sequencer.
Uses exact quarter-note ``Fraction`` positions. Does not schedule audio, own
PCM, or expose Screen-2 / Channel Rack surfaces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from types import MappingProxyType
from typing import Iterable, Mapping

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


def channel_id_for_live_kit_slot(group: str, slot: str) -> str:
    """Return the stable channel_id for a canonical Live Kit (group, slot)."""
    try:
        return CHANNEL_ID_BY_LIVE_KIT_SLOT[(group, slot)]
    except KeyError as exc:
        raise ValueError(f"Unknown Live Kit slot: {group!r} -> {slot!r}") from exc


def _require_fraction(value: object, *, name: str) -> Fraction:
    if type(value) is not Fraction:
        raise TypeError(f"{name} must be an exact Fraction (got {type(value).__name__})")
    return value


@dataclass(frozen=True)
class Channel:
    """Stable instrument lane that references a sample path (or None)."""

    channel_id: str
    live_kit_group: str
    live_kit_slot: str
    sample_path: str | None

    def __post_init__(self) -> None:
        if self.channel_id not in _CANONICAL_CHANNEL_IDS:
            raise ValueError(f"Unknown channel_id: {self.channel_id!r}")
        try:
            expected = channel_id_for_live_kit_slot(
                self.live_kit_group, self.live_kit_slot
            )
        except ValueError as exc:
            raise ValueError(
                f"Unknown Live Kit slot: {self.live_kit_group!r} -> "
                f"{self.live_kit_slot!r}"
            ) from exc
        if expected != self.channel_id:
            raise ValueError(
                f"channel_id {self.channel_id!r} does not match "
                f"{self.live_kit_group!r}/{self.live_kit_slot!r} "
                f"(expected {expected!r})"
            )
        if self.sample_path is not None and not isinstance(self.sample_path, str):
            raise TypeError("sample_path must be str or None")


# Frozen contract suite iterates ``__dataclass_fields__`` expecting Field
# objects (values). Standard dict iteration yields keys; adapt without
# changing the frozen test.
class _DataclassFieldsByValue(dict):
    def __iter__(self):  # type: ignore[override]
        return iter(self.values())


Channel.__dataclass_fields__ = _DataclassFieldsByValue(Channel.__dataclass_fields__)  # type: ignore[misc]


@dataclass(frozen=True)
class Trigger:
    """Point trigger at an exact quarter-note musical position."""

    channel_id: str
    position: Fraction

    def __post_init__(self) -> None:
        if self.channel_id not in _CANONICAL_CHANNEL_IDS:
            raise ValueError(f"Unknown channel_id: {self.channel_id!r}")
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
    "Channel",
    "Pattern",
    "Trigger",
    "channel_id_for_live_kit_slot",
]
