"""Tk-free state and presentation contracts for the minimal Screen-1 Live Kit."""

from __future__ import annotations

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
"""Canonical Live Kit taxonomy shared by state, presentation, and chooser."""

LIVE_KIT_GROUPS = tuple(group for group, _slots in LIVE_KIT_SLOT_MAPPING)
"""Compatibility projection of the canonical taxonomy's group order."""

_SLOTS_BY_GROUP = dict(LIVE_KIT_SLOT_MAPPING)
DRUM_SLOTS = _SLOTS_BY_GROUP["Drums"]
"""Compatibility projection for existing callers that address drum slots."""


class LiveKitState:
    """In-memory musical assignments; deliberately independent of Tk and storage.

    Optional ``on_assignment_changed`` supports session-owned persistence (#809).
    Wire the callback only after restore completes so assign-during-restore does
    not autosave a half-built snapshot.
    """

    def __init__(
        self,
        *,
        on_assignment_changed: Callable[[], None] | None = None,
    ) -> None:
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
        return _SLOTS_BY_GROUP[group]

    def assignment_for(self, group: str, slot: str) -> WorkbenchRow | None:
        self._validate_slot(group, slot)
        return self._assignments[group][slot]

    def assign(self, group: str, slot: str, row: WorkbenchRow) -> None:
        self._validate_slot(group, slot)
        self._assignments[group][slot] = row
        if self._on_assignment_changed is not None:
            self._on_assignment_changed()

    def clear_assignments(self, *, notify: bool = True) -> None:
        """Clear all musical assignments, optionally without persistence callback."""
        changed = False
        for group, slots in LIVE_KIT_SLOT_MAPPING:
            for slot in slots:
                if self._assignments[group][slot] is not None:
                    self._assignments[group][slot] = None
                    changed = True
        if changed and notify and self._on_assignment_changed is not None:
            self._on_assignment_changed()

    @staticmethod
    def _validate_group(group: str) -> None:
        if group not in LIVE_KIT_GROUPS:
            raise ValueError(f"Unbekannte Live-Kit-Gruppe: {group}")

    def _validate_slot(self, group: str, slot: str) -> None:
        self._validate_group(group)
        if slot not in self.slots_for(group):
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
    """Disclosure-only state layered over a LiveKitState."""

    def __init__(self, state: LiveKitState) -> None:
        self._state = state
        # #743: first reveal shows only compact group headers; expand is explicit.
        self._active_group: str | None = None
        self._collapsed_groups: set[str] = set(state.groups())

    def toggle_group(self, group: str) -> bool:
        self._state.slots_for(group)
        if group in self._collapsed_groups:
            self._collapsed_groups = set(self._state.groups()) - {group}
            self._active_group = group
            return False
        self._collapsed_groups.add(group)
        self._active_group = None
        return True

    def is_collapsed(self, group: str) -> bool:
        self._state.slots_for(group)
        return group in self._collapsed_groups

    def active_group(self) -> str | None:
        return self._active_group

    def visible_structure(self) -> tuple[LiveKitGroupView, ...]:
        return tuple(
            LiveKitGroupView(
                name=group,
                slots=tuple(
                    LiveKitSlotView(
                        name=slot,
                        assignment=self._state.assignment_for(group, slot),
                    )
                    for slot in self._state.slots_for(group)
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
    "LIVE_KIT_SLOT_MAPPING",
    "LiveKitGroupView",
    "LiveKitPresentationState",
    "LiveKitSlotView",
    "LiveKitState",
    "RightPanePresentation",
]
