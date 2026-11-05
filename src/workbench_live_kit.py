"""Tk-free state and presentation contracts for the minimal Screen-1 Live Kit."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from .workbench_controller import WorkbenchRow


LIVE_KIT_SLOT_MAPPING = (
    ("Kick + Bass", ("Kick", "Bass")),
    (
        "Drums",
        ("Main Drum", "Closed Hat", "Open Hat", "Percussion", "Additional"),
    ),
    ("Melodic", ("Lead", "Pad")),
    ("Atmos / FX", ("Atmos", "FX")),
)
"""Canonical Live Kit taxonomy shared by state, presentation, and chooser.

Seed / migration identity for every kit. Groups may grow beyond this map via
:meth:`LiveKitState.append_empty_slot` (#1377); Export V1 still describes only
this canonical map, while kits with extras export as schema V2.
"""

LIVE_KIT_GROUPS = tuple(group for group, _slots in LIVE_KIT_SLOT_MAPPING)
"""Compatibility projection of the canonical taxonomy's group order."""

_SLOTS_BY_GROUP = dict(LIVE_KIT_SLOT_MAPPING)
DRUM_SLOTS = _SLOTS_BY_GROUP["Drums"]
"""Compatibility projection for existing callers that address drum slots."""

LIVE_KIT_MAX_SLOTS_PER_GROUP = 32
"""Hard ceiling per group for growable racks (#1377)."""

_EXTRA_SLOT_RE = re.compile(r"^Extra ([1-9]\d*)$")

# Display-only labels (#1123 / #1377). Domain taxonomy keys stay authoritative.
_LIVE_KIT_GROUP_DISPLAY_NAMES = {
    "Kick + Bass": "Bassline",
    "Atmos / FX": "Atmos / FX / Vocal",
}
_LIVE_KIT_SLOT_DISPLAY_NAMES = {
    ("Kick + Bass", "Kick"): "Kick Drum",
}


def live_kit_group_display_name(group: str) -> str:
    """Renderer label for a domain group key; unknown keys echo the domain name."""
    return _LIVE_KIT_GROUP_DISPLAY_NAMES.get(group, group)


def live_kit_slot_display_name(group: str, slot: str) -> str:
    """Renderer label for a domain slot key; unknown keys echo the domain name."""
    return _LIVE_KIT_SLOT_DISPLAY_NAMES.get((group, slot), slot)


def is_live_kit_extra_slot(slot: str) -> bool:
    """True when *slot* is a growable Extra-N identity (#1377)."""
    return _EXTRA_SLOT_RE.fullmatch(slot) is not None


def live_kit_extra_slot_index(slot: str) -> int | None:
    match = _EXTRA_SLOT_RE.fullmatch(slot)
    if match is None:
        return None
    return int(match.group(1))


def live_kit_has_extra_slots(state: LiveKitState) -> bool:
    """True when any group currently holds a non-canonical Extra-N slot."""
    for group in state.groups():
        canonical = set(_SLOTS_BY_GROUP[group])
        for slot in state.slots_for(group):
            if slot not in canonical:
                return True
    return False


def is_live_kit_slot_identity(group: str, slot: str) -> bool:
    """True for canonical taxonomy slots or Extra-N under a known group (#1377)."""
    if group not in LIVE_KIT_GROUPS or not isinstance(slot, str):
        return False
    if slot in _SLOTS_BY_GROUP[group]:
        return True
    return is_live_kit_extra_slot(slot)


class LiveKitState:
    """In-memory musical assignments; deliberately independent of Tk and storage.

    Optional ``on_assignment_changed`` supports session-owned persistence (#809).
    Wire the callback only after restore completes so assign-during-restore does
    not autosave a half-built snapshot.

    #1377: each group is seeded from :data:`LIVE_KIT_SLOT_MAPPING` and may grow
    through :meth:`append_empty_slot`. Creating a slot is distinct from assigning
    a sample into an existing slot.
    """

    def __init__(
        self,
        *,
        on_assignment_changed: Callable[[], None] | None = None,
    ) -> None:
        self._slot_order: dict[str, list[str]] = {
            group: list(slots) for group, slots in LIVE_KIT_SLOT_MAPPING
        }
        self._assignments: dict[str, dict[str, WorkbenchRow | None]] = {
            group: {slot: None for slot in slots}
            for group, slots in LIVE_KIT_SLOT_MAPPING
        }
        self._on_assignment_changed = on_assignment_changed

    def set_on_assignment_changed(
        self, callback: Callable[[], None] | None
    ) -> None:
        """Bind or clear the post-mutation observer (session persistence)."""
        self._on_assignment_changed = callback

    def groups(self) -> tuple[str, ...]:
        return LIVE_KIT_GROUPS

    def slots_for(self, group: str) -> tuple[str, ...]:
        self._validate_group(group)
        return tuple(self._slot_order[group])

    def assignment_for(self, group: str, slot: str) -> WorkbenchRow | None:
        self._validate_slot(group, slot)
        return self._assignments[group][slot]

    def assign(self, group: str, slot: str, row: WorkbenchRow) -> None:
        self._validate_slot(group, slot)
        self._assignments[group][slot] = row
        if self._on_assignment_changed is not None:
            self._on_assignment_changed()

    def clear_slot(self, group: str, slot: str, *, notify: bool = True) -> bool:
        """Clear one slot through the same validate/notify contract as assign.

        Returns True when a prior assignment was cleared. Empty slots are an
        idempotent no-op without notify. Invalid group/slot raise like assign.
        """
        self._validate_slot(group, slot)
        if self._assignments[group][slot] is None:
            return False
        self._assignments[group][slot] = None
        if notify and self._on_assignment_changed is not None:
            self._on_assignment_changed()
        return True

    def clear_assignments(self, *, notify: bool = True) -> None:
        """Clear all musical assignments, optionally without persistence callback."""
        changed = False
        for group in LIVE_KIT_GROUPS:
            for slot in self._slot_order[group]:
                if self._assignments[group][slot] is not None:
                    self._assignments[group][slot] = None
                    changed = True
        if changed and notify and self._on_assignment_changed is not None:
            self._on_assignment_changed()

    def append_empty_slot(self, group: str, *, notify: bool = True) -> str:
        """Append one empty Extra-N slot to *group*. Returns the new slot key.

        Does not assign a sample. Fails closed when the group is at
        :data:`LIVE_KIT_MAX_SLOTS_PER_GROUP`.
        """
        self._validate_group(group)
        order = self._slot_order[group]
        if len(order) >= LIVE_KIT_MAX_SLOTS_PER_GROUP:
            raise ValueError(
                f"Maximum Live-Kit-Slots erreicht: {group} "
                f"({LIVE_KIT_MAX_SLOTS_PER_GROUP})"
            )
        next_index = 1
        for slot in order:
            index = live_kit_extra_slot_index(slot)
            if index is not None and index >= next_index:
                next_index = index + 1
        new_slot = f"Extra {next_index}"
        if new_slot in self._assignments[group]:
            raise ValueError(f"Live-Kit-Slot existiert bereits: {group} -> {new_slot}")
        order.append(new_slot)
        self._assignments[group][new_slot] = None
        if notify and self._on_assignment_changed is not None:
            self._on_assignment_changed()
        return new_slot

    def ensure_slot(self, group: str, slot: str) -> None:
        """Ensure *slot* exists under *group* for session restore (#1377).

        Canonical taxonomy slots are always present. Extra-N slots may be
        appended in restore order. Unknown non-extra identities fail closed.
        """
        self._validate_group(group)
        if slot in self._assignments[group]:
            return
        if not is_live_kit_extra_slot(slot):
            raise ValueError(f"Unbekannter Live-Kit-Slot: {group} -> {slot}")
        if len(self._slot_order[group]) >= LIVE_KIT_MAX_SLOTS_PER_GROUP:
            raise ValueError(
                f"Maximum Live-Kit-Slots erreicht: {group} "
                f"({LIVE_KIT_MAX_SLOTS_PER_GROUP})"
            )
        self._slot_order[group].append(slot)
        self._assignments[group][slot] = None

    def reset_slot_structure(self, *, notify: bool = False) -> None:
        """Reset every group to the canonical taxonomy with empty assignments."""
        self._slot_order = {
            group: list(slots) for group, slots in LIVE_KIT_SLOT_MAPPING
        }
        self._assignments = {
            group: {slot: None for slot in slots}
            for group, slots in LIVE_KIT_SLOT_MAPPING
        }
        if notify and self._on_assignment_changed is not None:
            self._on_assignment_changed()

    @staticmethod
    def _validate_group(group: str) -> None:
        if group not in LIVE_KIT_GROUPS:
            raise ValueError(f"Unbekannte Live-Kit-Gruppe: {group}")

    def _validate_slot(self, group: str, slot: str) -> None:
        self._validate_group(group)
        if slot not in self._assignments[group]:
            raise ValueError(f"Unbekannter Live-Kit-Slot: {group} -> {slot}")


@dataclass(frozen=True)
class LiveKitSlotView:
    name: str
    assignment: WorkbenchRow | None


@dataclass(frozen=True)
class LiveKitGroupView:
    name: str
    slots: tuple[LiveKitSlotView, ...]


class LiveKitPresentationState:
    """Disclosure-only state layered over a LiveKitState.

    #1377 vertical rack: groups start expanded (no collapse arrows). Accordion
    toggle remains available for callers that still use it (pending-add ensure,
    historical tests).

    Minimal default rack (#1377 follow-up): each group projects a prefix of its
    domain slots — default one empty field. Occupied slots and Extra-N (session
    domain truth) always extend the prefix. Revealing the next empty canonical
    slot is presentation-only and must not mutate :class:`LiveKitState`.
    """

    def __init__(self, state: LiveKitState) -> None:
        self._state = state
        self._active_group: str | None = None
        self._collapsed_groups: set[str] = set()
        # Inclusive 0-based end index of the visible prefix per group.
        self._visible_prefix_end: dict[str, int] = {
            group: 0 for group in state.groups()
        }
        self.sync_visible_prefix_from_domain()

    def toggle_group(self, group: str) -> bool:
        self._state.slots_for(group)
        if group in self._collapsed_groups:
            self._collapsed_groups = set(self._state.groups()) - {group}
            self._active_group = group
            return False
        self._collapsed_groups.add(group)
        self._active_group = None
        return True

    def ensure_group_expanded(self, group: str) -> bool:
        """Expand *group*. No-op when already open.

        Returns True when *group* is expanded after the call.
        Used by pending Add-to-Kit (#1374) so Slot + affordances are reachable.
        #1377 vertical rack starts fully expanded; in that state siblings stay
        open so every group's slots remain assignment targets.
        """
        self._state.slots_for(group)
        if not self._collapsed_groups:
            self._active_group = group
            return True
        if group not in self._collapsed_groups and self._active_group == group:
            return True
        self._collapsed_groups = set(self._state.groups()) - {group}
        self._active_group = group
        return True

    def is_collapsed(self, group: str) -> bool:
        self._state.slots_for(group)
        return group in self._collapsed_groups

    def active_group(self) -> str | None:
        return self._active_group

    def sync_visible_prefix_from_domain(self) -> None:
        """Raise each group's visible prefix to cover occupied slots and Extra-N.

        Does not shrink a session watermark from prior Plus reveals. Empty
        Extra-N remain visible because they are domain/session truth; empty
        canonical reveals without Extra-N are not session-backed and therefore
        collapse on a fresh presentation over the same empty domain.
        """
        for group in self._state.groups():
            slots = self._state.slots_for(group)
            if not slots:
                self._visible_prefix_end[group] = 0
                continue
            required = 0
            for index, slot in enumerate(slots):
                if (
                    self._state.assignment_for(group, slot) is not None
                    or is_live_kit_extra_slot(slot)
                ):
                    required = index
            current = self._visible_prefix_end.get(group, 0)
            end = max(current, required)
            self._visible_prefix_end[group] = min(end, len(slots) - 1)

    def cover_slot(self, group: str, slot: str) -> None:
        """Ensure *slot* is inside the visible prefix (assign / Extra append)."""
        slots = self._state.slots_for(group)
        index = slots.index(slot)
        current = self._visible_prefix_end.get(group, 0)
        self._visible_prefix_end[group] = max(current, index)

    def reveal_next_slot(self, group: str) -> str | None:
        """Reveal the next already-existing domain slot. No domain mutation.

        Returns the newly revealed slot key, or ``None`` when every domain slot
        in *group* is already visible (caller may then append Extra-N).
        """
        slots = self._state.slots_for(group)
        end = self._visible_prefix_end.get(group, 0)
        next_index = end + 1
        if next_index >= len(slots):
            return None
        self._visible_prefix_end[group] = next_index
        return slots[next_index]

    def visible_slot_names(self, group: str) -> tuple[str, ...]:
        """Ordered visible slot keys for *group* (prefix projection).

        Always includes every occupied slot and every Extra-N, even when the
        domain was mutated without a presentation notify (Tk / restore paths).
        """
        slots = self._state.slots_for(group)
        if not slots:
            return ()
        required = 0
        for index, slot in enumerate(slots):
            if (
                self._state.assignment_for(group, slot) is not None
                or is_live_kit_extra_slot(slot)
            ):
                required = index
        end = max(self._visible_prefix_end.get(group, 0), required)
        end = min(end, len(slots) - 1)
        self._visible_prefix_end[group] = end
        return slots[: end + 1]

    def visible_structure(self) -> tuple[LiveKitGroupView, ...]:
        return tuple(
            LiveKitGroupView(
                name=group,
                slots=tuple(
                    LiveKitSlotView(
                        name=slot,
                        assignment=self._state.assignment_for(group, slot),
                    )
                    for slot in self.visible_slot_names(group)
                ),
            )
            for group in self._state.groups()
        )


class RightPanePresentation:
    """Small router preserving the existing Sample Details widget identities."""

    def __init__(
        self,
        *,
        detail_text: object | None = None,
        detail_waveform: object | None = None,
        edit_controls: object | None = None,
    ) -> None:
        self.detail_text = detail_text
        self.detail_waveform = detail_waveform
        self.edit_controls = edit_controls
        self._active_view = "Live Kit"

    def show_live_kit(self) -> str:
        self._active_view = "Live Kit"
        return self._active_view

    def show_sample_details(self) -> str:
        self._active_view = "Sample Details"
        return self._active_view

    def active_view(self) -> str:
        return self._active_view


__all__ = [
    "DRUM_SLOTS",
    "LIVE_KIT_GROUPS",
    "LIVE_KIT_MAX_SLOTS_PER_GROUP",
    "LIVE_KIT_SLOT_MAPPING",
    "LiveKitGroupView",
    "LiveKitPresentationState",
    "LiveKitSlotView",
    "LiveKitState",
    "RightPanePresentation",
    "is_live_kit_extra_slot",
    "is_live_kit_slot_identity",
    "live_kit_extra_slot_index",
    "live_kit_group_display_name",
    "live_kit_has_extra_slots",
    "live_kit_slot_display_name",
]
