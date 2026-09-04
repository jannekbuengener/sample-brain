"""Tk-free state and presentation contracts for the minimal Screen-1 Live Kit."""

from __future__ import annotations

from dataclasses import dataclass

from .workbench_controller import WorkbenchRow


LIVE_KIT_GROUPS = ("Kick + Bass", "Drums", "Melodic", "Atmos / FX")
DRUM_SLOTS = (
    "Main Drum",
    "Closed Hat",
    "Open Hat",
    "Percussion",
    "Additional",
)


class LiveKitState:
    """In-memory musical assignments; deliberately independent of Tk and storage."""

    def __init__(self) -> None:
        self._assignments: dict[str, dict[str, WorkbenchRow | None]] = {
            "Drums": {slot: None for slot in DRUM_SLOTS}
        }

    def groups(self) -> tuple[str, ...]:
        return LIVE_KIT_GROUPS

    def slots_for(self, group: str) -> tuple[str, ...]:
        self._validate_group(group)
        return DRUM_SLOTS if group == "Drums" else ()

    def assignment_for(self, group: str, slot: str) -> WorkbenchRow | None:
        self._validate_slot(group, slot)
        return self._assignments[group][slot]

    def assign(self, group: str, slot: str, row: WorkbenchRow) -> None:
        self._validate_slot(group, slot)
        self._assignments[group][slot] = row

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
        self._collapsed_groups: set[str] = set()

    def toggle_group(self, group: str) -> bool:
        self._state.slots_for(group)
        if group in self._collapsed_groups:
            self._collapsed_groups.remove(group)
            return False
        self._collapsed_groups.add(group)
        return True

    def is_collapsed(self, group: str) -> bool:
        self._state.slots_for(group)
        return group in self._collapsed_groups

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
        self._active_view = "Sample Details"

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
    "LiveKitGroupView",
    "LiveKitPresentationState",
    "LiveKitSlotView",
    "LiveKitState",
    "RightPanePresentation",
]
