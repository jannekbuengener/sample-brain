"""Optional production Screen-1 Qt Quick shell.

This module owns only renderer-facing state, interaction routing, and Qt engine
startup. It can be imported without PySide6; fixture, evidence, and synthetic
probe orchestration deliberately live in :mod:`src.workbench_qml_spike`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import inspect
import math
from pathlib import Path
from typing import Callable

from .workbench_controller import WorkbenchRow
from .workbench_browser_rows import (
    BoundedBackgroundWaveformLoader,
    BoundedLazyWaveformCache,
)
from .workbench_harmony import HarmonicMatchLibraryController, HarmonySuggestion
from .workbench_live_kit import LiveKitPresentationState, LiveKitState
from .workbench_library import workbench_library_db_path
from .workbench_library_navigation import LibraryNodeKind
from .workbench_qml_analysis import AnalysisUiState, create_qt_analysis_coordinator
from .workbench_qml_library import (
    WorkbenchLibraryTreeState,
    create_qt_library_tree_model,
)
from .workbench_qml_runtime import Screen1QmlRuntimeComposition
from .workbench_waveform import compute_waveform_envelope

SCREEN1_QML_STATE_IDS = ("screen1-default-3panel", "screen1-harmonic-4panel")


@dataclass(frozen=True)
class QmlBrowserRow:
    """Renderer projection retaining the authoritative Python row identity."""

    source_row: WorkbenchRow
    display_name: str
    sample_type: str
    bpm: str
    key: str
    duration: str
    waveform_envelope: tuple[float, ...]


@dataclass(frozen=True)
class QmlHarmonyRow:
    """Pure renderer projection of a controller-owned harmony suggestion."""

    source_row: WorkbenchRow
    display_name: str
    sample_type: str
    key: str
    waveform_envelope: tuple[float, ...]
    fit: str
    relation: str
    explanation: str


@dataclass(frozen=True)
class QmlLiveKitSlot:
    name: str
    assignment: WorkbenchRow | None


@dataclass(frozen=True)
class QmlLiveKitGroup:
    name: str
    slots: tuple[QmlLiveKitSlot, ...]
    active: bool


class LiveKitPresenter:
    """Thin runtime-owned projection adapter over the canonical Live Kit contracts.

    Owns exactly one :class:`LiveKitState` and :class:`LiveKitPresentationState`
    and renders their current truth into the renderer-only group shape.  QML
    never owns musical or disclosure state; it only reads this projection.
    """

    def __init__(self, state: LiveKitState | None = None) -> None:
        self._state = state if state is not None else LiveKitState()
        self._presentation = LiveKitPresentationState(self._state)
        self._groups = self._project()

    @property
    def state(self) -> LiveKitState:
        return self._state

    @property
    def presentation(self) -> LiveKitPresentationState:
        return self._presentation

    def _project(self) -> tuple[QmlLiveKitGroup, ...]:
        return tuple(
            QmlLiveKitGroup(
                name=group.name,
                slots=tuple(
                    QmlLiveKitSlot(slot.name, slot.assignment) for slot in group.slots
                ),
                active=not self._presentation.is_collapsed(group.name),
            )
            for group in self._presentation.visible_structure()
        )

    @property
    def groups(self) -> tuple[QmlLiveKitGroup, ...]:
        return self._groups

    def toggle_group(self, group: str) -> bool:
        self._presentation.toggle_group(group)
        self._groups = self._project()
        return self._presentation.is_collapsed(group)

    def assign(self, group: str, slot: str, row: WorkbenchRow) -> None:
        self._state.assign(group, slot, row)
        self._groups = self._project()


def _row_details(row: WorkbenchRow) -> dict[str, object]:
    """Read the public renderer details attached to a Workbench row."""
    if row.details:
        return row.details
    if isinstance(row.error, dict):
        return row.error
    return {}


def _duration(row: WorkbenchRow) -> str:
    details = _row_details(row)
    value = details.get("duration_sec", details.get("duration"))
    if value is None or value == "":
        return "—"
    try:
        return f"{float(value):.2f}s"
    except (TypeError, ValueError):
        return str(value)


def _waveform_envelope(row: WorkbenchRow) -> tuple[float, ...]:
    raw = _row_details(row).get("waveform_envelope")
    if raw is None or isinstance(raw, (str, bytes)):
        return ()
    try:
        return tuple(max(0.0, min(1.0, float(value))) for value in raw)
    except (TypeError, ValueError):
        return ()


def _qml_row(row: WorkbenchRow) -> QmlBrowserRow:
    return QmlBrowserRow(
        source_row=row,
        display_name=row.display_name,
        sample_type=row.pred_type or "—",
        bpm="—" if row.bpm is None else f"{row.bpm:g}",
        key=row.key or "—",
        duration=_duration(row),
        waveform_envelope=_waveform_envelope(row),
    )


def _qml_harmony_row(suggestion: HarmonySuggestion) -> QmlHarmonyRow:
    row = suggestion.row
    return QmlHarmonyRow(
        source_row=row,
        display_name=row.display_name,
        sample_type=row.pred_type or "—",
        key=row.key or "—",
        waveform_envelope=_waveform_envelope(row),
        fit=f"{suggestion.total_score:.0%}",
        relation=suggestion.relation.value.replace("_", " ").title(),
        explanation=suggestion.explanation,
    )


class Screen1QmlViewModel:
    """Small renderer adapter over existing fixture and state contracts."""

    def __init__(
        self,
        *,
        state_id: str,
        library_labels: tuple[str, ...],
        browser_rows: tuple[QmlBrowserRow, ...],
        selected_browser_index: int,
        harmony_rows: tuple[QmlHarmonyRow, ...],
        live_kit_groups: tuple[QmlLiveKitGroup, ...],
        on_browser_selected: Callable[[WorkbenchRow], None] | None = None,
        library_tree: WorkbenchLibraryTreeState | None = None,
        browser_context: str = "No library selected",
        browser_error: str | None = None,
        auditioning_live_kit_slot: tuple[str, str] | None = None,
    ) -> None:
        if state_id not in SCREEN1_QML_STATE_IDS:
            raise ValueError("Unbekannter Screen-1-QML-State.")
        self.state_id = state_id
        self.library_labels = library_labels
        self.browser_rows = browser_rows
        self.selected_browser_index = selected_browser_index
        self.harmony_rows = harmony_rows
        self.harmony_anchor = ""
        self.harmony_status = "Harmonic Match ist ausgeschaltet."
        self.live_kit_groups = live_kit_groups
        self._on_browser_selected = on_browser_selected
        self.library_tree = library_tree or WorkbenchLibraryTreeState()
        self.browser_context = browser_context
        self.browser_error = browser_error
        self.auditioning_live_kit_slot = auditioning_live_kit_slot
        self.analysis_status = "idle"
        self.analysis_folder_id: int | None = None
        self.analysis_current = 0
        self.analysis_total = 0
        self.analysis_source = ""
        self.analysis_error: str | None = None

    @property
    def panel_count(self) -> int:
        return 4 if self.state_id.endswith("4panel") else 3

    @classmethod
    def baseline(cls, state_id: str) -> "Screen1QmlViewModel":
        """Return a neutral shell state until live Screen-1 data is wired in."""
        rows = tuple(
            _qml_row(
                WorkbenchRow(
                    display_name=name,
                    relative_path=f"screen1-baseline/{index}",
                    path=f"screen1-baseline/{index}",
                    bpm=132.0,
                    key=None,
                    key_conf=None,
                    loudness=None,
                    brightness=None,
                    sample_class="one_shot",
                    pred_type="Unwired",
                    status="placeholder",
                    details={},
                )
            )
            for index, name in enumerate(("SAMPLE 01", "SAMPLE 02", "SAMPLE 03"))
        )
        return cls(
            state_id=state_id,
            library_labels=("Library", "All Samples"),
            browser_rows=rows,
            selected_browser_index=0,
            harmony_rows=(),
            live_kit_groups=(
                QmlLiveKitGroup("Kick + Bass", (), False),
                QmlLiveKitGroup("Drums", (), False),
                QmlLiveKitGroup("Melodic", (), False),
                QmlLiveKitGroup("Atmos / FX", (), False),
            ),
        )

    def select_browser_index(self, index: int) -> WorkbenchRow:
        if not 0 <= index < len(self.browser_rows):
            raise IndexError("Browser-Zeilenindex außerhalb des sichtbaren Modells.")
        self.selected_browser_index = index
        row = self.browser_rows[index].source_row
        if self._on_browser_selected is not None:
            self._on_browser_selected(row)
        return row

    def set_browser_state(
        self,
        *,
        rows: tuple[WorkbenchRow, ...],
        selected_index: int,
        browser_context: str,
        error: str | None,
    ) -> None:
        self.browser_rows = tuple(_qml_row(row) for row in rows)
        self.selected_browser_index = selected_index
        self.browser_context = browser_context
        self.browser_error = error


    def set_browser_waveform(self, path: str, envelope: tuple[float, ...]) -> bool:
        """Apply one cached waveform without changing browser selection."""
        changed = False
        updated: list[QmlBrowserRow] = []
        for row in self.browser_rows:
            if str(row.source_row.path) == path and row.waveform_envelope != envelope:
                row = replace(row, waveform_envelope=envelope)
                changed = True
            updated.append(row)
        if changed:
            self.browser_rows = tuple(updated)
        harmony_updated: list[QmlHarmonyRow] = []
        for row in self.harmony_rows:
            if str(row.source_row.path) == path and row.waveform_envelope != envelope:
                row = replace(row, waveform_envelope=envelope)
                changed = True
            harmony_updated.append(row)
        if changed:
            self.harmony_rows = tuple(harmony_updated)
        return changed

    def set_analysis_state(self, state: AnalysisUiState) -> None:
        self.analysis_status = state.phase
        self.analysis_folder_id = state.folder_id
        self.analysis_current = state.current
        self.analysis_total = state.total
        self.analysis_source = state.display_name
        self.analysis_error = state.error

    def qml_context(self) -> dict[str, object]:
        return {
            "panelCount": self.panel_count,
            "selectedBrowserIndex": self.selected_browser_index,
            "browserContext": self.browser_context,
            "errorMessage": self.browser_error or "",
            "analysisStatus": self.analysis_status,
            "analysisCurrent": self.analysis_current,
            "analysisTotal": self.analysis_total,
            "analysisSource": self.analysis_source,
            "analysisError": self.analysis_error or "",
            "harmonyAnchor": self.harmony_anchor,
            "harmonyStatus": self.harmony_status,
            "browserRows": [
                {
                    "name": row.display_name,
                    "type": row.sample_type,
                    "bpm": row.bpm,
                    "key": row.key,
                    "duration": row.duration,
                    "waveform": list(row.waveform_envelope),
                    "path": str(row.source_row.path),
                    "relativePath": row.source_row.relative_path,
                }
                for row in self.browser_rows
            ],
            "harmonyRows": [
                {
                    "name": row.display_name,
                    "type": row.sample_type,
                    "key": row.key,
                    "waveform": list(row.waveform_envelope),
                    "fit": row.fit,
                    "relation": row.relation,
                    "explanation": row.explanation,
                    "path": str(row.source_row.path),
                }
                for row in self.harmony_rows
            ],
            "liveKitGroups": [
                {
                    "name": group.name,
                    "active": group.active,
                    "slots": [
                        {
                            "name": slot.name,
                            "assignment": (
                                slot.assignment.display_name
                                if slot.assignment
                                else "Empty · Slot wählen"
                            ),
                            "assigned": slot.assignment is not None,
                            "auditioning": self.auditioning_live_kit_slot
                            == (group.name, slot.name),
                        }
                        for slot in group.slots
                    ],
                }
                for group in self.live_kit_groups
            ],
        }


def _sync_runtime_browser_state(
    view_model: Screen1QmlViewModel,
    adapter: "Screen1QmlInteractionAdapter",
    runtime_composition: Screen1QmlRuntimeComposition,
) -> None:
    """Project the authoritative runtime browser state into the QML adapter."""
    state = runtime_composition.browser_state
    view_model.set_browser_state(
        rows=state.rows,
        selected_index=state.selected_index,
        browser_context=state.browser_context,
        error=state.error,
    )
    adapter.replace_browser_scope(state.scope)


def _empty_live_kit_groups() -> tuple[QmlLiveKitGroup, ...]:
    """Project the canonical empty Live Kit into the renderer shape."""
    state = LiveKitState()
    presentation = LiveKitPresentationState(state)
    return tuple(
        QmlLiveKitGroup(
            name=group.name,
            slots=tuple(QmlLiveKitSlot(slot.name, slot.assignment) for slot in group.slots),
            active=not presentation.is_collapsed(group.name),
        )
        for group in presentation.visible_structure()
    )


def _qml_screen_data_bridge(
    view_model: Screen1QmlViewModel,
    *,
    on_cancel_analysis: Callable[[], None] | None = None,
):
    """Expose renderer state through notifyable Qt properties."""
    from PySide6.QtCore import QObject, Property, Signal, Slot

    class QmlScreenDataBridge(QObject):
        browserRowsChanged = Signal()
        selectedBrowserIndexChanged = Signal()
        browserContextChanged = Signal()
        errorMessageChanged = Signal()
        analysisStatusChanged = Signal()
        analysisProgressChanged = Signal()
        analysisSourceChanged = Signal()
        analysisErrorChanged = Signal()
        harmonyRowsChanged = Signal()
        harmonyAnchorChanged = Signal()
        harmonyStatusChanged = Signal()
        liveKitGroupsChanged = Signal()
        panelCountChanged = Signal()

        @Property(list, notify=browserRowsChanged)
        def browserRows(self) -> list[dict[str, object]]:
            return view_model.qml_context()["browserRows"]

        @Property(int, notify=selectedBrowserIndexChanged)
        def selectedBrowserIndex(self) -> int:
            return view_model.selected_browser_index

        @Property(str, notify=browserContextChanged)
        def browserContext(self) -> str:
            return view_model.browser_context

        @Property(str, notify=errorMessageChanged)
        def errorMessage(self) -> str:
            return view_model.browser_error or ""

        @Property(str, notify=analysisStatusChanged)
        def analysisStatus(self) -> str:
            return view_model.analysis_status

        @Property(int, notify=analysisProgressChanged)
        def analysisCurrent(self) -> int:
            return view_model.analysis_current

        @Property(int, notify=analysisProgressChanged)
        def analysisTotal(self) -> int:
            return view_model.analysis_total

        @Property(str, notify=analysisSourceChanged)
        def analysisSource(self) -> str:
            return view_model.analysis_source

        @Property(str, notify=analysisErrorChanged)
        def analysisError(self) -> str:
            return view_model.analysis_error or ""

        @Property(list, notify=harmonyRowsChanged)
        def harmonyRows(self) -> list[dict[str, object]]:
            return view_model.qml_context()["harmonyRows"]

        @Property(str, notify=harmonyAnchorChanged)
        def harmonyAnchor(self) -> str:
            return view_model.harmony_anchor

        @Property(str, notify=harmonyStatusChanged)
        def harmonyStatus(self) -> str:
            return view_model.harmony_status

        @Property(list, notify=liveKitGroupsChanged)
        def liveKitGroups(self) -> list[dict[str, object]]:
            return view_model.qml_context()["liveKitGroups"]

        @Property(int, notify=liveKitGroupsChanged)
        def liveKitAssignedCount(self) -> int:
            return sum(
                1
                for group in view_model.live_kit_groups
                for slot in group.slots
                if slot.assignment is not None
            )

        @Property(int, notify=liveKitGroupsChanged)
        def liveKitTotalSlotCount(self) -> int:
            return sum(len(group.slots) for group in view_model.live_kit_groups)

        @Property(int, notify=panelCountChanged)
        def panelCount(self) -> int:
            return view_model.panel_count

        @Slot()
        def refresh(self) -> None:
            self.selectedBrowserIndexChanged.emit()
            self.browserContextChanged.emit()
            self.errorMessageChanged.emit()
            self.analysisStatusChanged.emit()
            self.analysisProgressChanged.emit()
            self.analysisSourceChanged.emit()
            self.analysisErrorChanged.emit()
            self.harmonyRowsChanged.emit()
            self.harmonyAnchorChanged.emit()
            self.harmonyStatusChanged.emit()
            self.liveKitGroupsChanged.emit()
            self.panelCountChanged.emit()

        @Slot()
        def refresh_browser_rows(self) -> None:
            self.browserRowsChanged.emit()

        @Slot()
        def refresh_browser_scope(self) -> None:
            self.browserRowsChanged.emit()
            self.refresh()

        @Slot()
        def cancelAnalysis(self) -> None:
            if on_cancel_analysis is not None:
                on_cancel_analysis()

    return QmlScreenDataBridge()


def _callback_accepts_start_ms(callback: Callable[..., object] | None) -> bool:
    """True when the preview seam callback declares a ``start_ms`` keyword.

    The seam stays row-only for legacy callbacks; offset-negotiating callbacks
    receive the explicit preview start intention forwarded by the adapter.
    """
    if callback is None:
        return False
    try:
        parameters = inspect.signature(callback).parameters
    except (TypeError, ValueError):
        return False
    return any(
        parameter.name == "start_ms"
        or parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )


class Screen1QmlInteractionAdapter:
    """Route renderer intent to the established Screen-1 Python contracts.

    The adapter deliberately contains no catalog, audio, live-kit, or harmony
    implementation.  Browser audition continues through the callback already
    owned by the caller, while harmonic results remain owned by the existing
    ``HarmonicMatchLibraryController``.
    """

    def __init__(
        self,
        *,
        view_model: Screen1QmlViewModel,
        harmony_controller: HarmonicMatchLibraryController | None = None,
        on_preview_requested: Callable[[WorkbenchRow], object] | None = None,
        on_preview_stopped: Callable[[], object] | None = None,
        on_add_to_kit_requested: Callable[[WorkbenchRow], object] | None = None,
        live_kit: LiveKitPresenter | None = None,
    ) -> None:
        self.view_model = view_model
        self.harmony_controller = harmony_controller
        self.harmonic_match_open = view_model.panel_count == 4
        self._on_preview_requested = on_preview_requested
        self._preview_request_accepts_start_ms = _callback_accepts_start_ms(
            on_preview_requested
        )
        self._on_preview_stopped = on_preview_stopped
        self._on_add_to_kit_requested = on_add_to_kit_requested
        self._live_kit = live_kit
        self._pending_live_kit_row: WorkbenchRow | None = None
        self._preview_active = False
        self._auditioning_live_kit_slot: tuple[str, str] | None = None
        self._harmonic_match_context_fingerprint: tuple[object, ...] | None = None
        self._harmonic_match_selected_index = 0
        self._harmonic_match_scroll_y = 0.0
        self._harmonic_match_browser_scope: object | None = None
        self._harmonic_match_session_scope: object | None = None

    @property
    def selected_browser_index(self) -> int:
        return self.view_model.selected_browser_index

    def select_row(self, index: int) -> WorkbenchRow:
        """Select exactly one authoritative row without starting a preview."""
        return self.view_model.select_browser_index(index)

    def _dispatch_preview(
        self, row: WorkbenchRow, *, start_ms: int | None = None
    ) -> object:
        """Emit a preview intent through the shared owner seam.

        ``start_ms=None`` keeps the owned default (the Browser saved cue).
        Explicit offsets (Live Kit ``start_ms=0``) are forwarded only to
        callbacks that declare the keyword, so legacy row-only seams stay
        unchanged.
        """
        if self._on_preview_requested is None:
            return None
        if self._preview_request_accepts_start_ms:
            return self._on_preview_requested(row, start_ms=start_ms)
        return self._on_preview_requested(row)

    @property
    def preview_active(self) -> bool:
        return self._preview_active

    @property
    def auditioning_live_kit_slot(self) -> tuple[str, str] | None:
        return self._auditioning_live_kit_slot

    @property
    def selected_harmonic_match_index(self) -> int:
        return self._harmonic_match_selected_index

    @property
    def harmonic_match_scroll_y(self) -> float:
        return self._harmonic_match_scroll_y

    def preview_row(self, index: int) -> WorkbenchRow:
        """Select a row and emit exactly one preview intent.

        A rejected dispatch stops any prior playback through the authoritative
        stop seam (mirroring the Live Kit audition failure branch), so audio
        can never stay orphaned while the UI claims idle.
        """
        if index == self.selected_browser_index:
            row = self.view_model.browser_rows[index].source_row
        else:
            row = self.select_row(index)
        was_active = self._preview_active
        result = self._dispatch_preview(row)
        accepted = bool(
            result is None or getattr(result, "ok", result is not False)
        )
        if not accepted and was_active:
            self._stop_preview_authoritative()
        self._preview_active = accepted
        self._clear_live_kit_audition_projection()
        return row

    def stop_preview(self) -> bool:
        """Stop only an active preview and leave selection untouched."""
        if not self._preview_active:
            return False
        self._stop_preview_authoritative()
        self._clear_live_kit_audition_projection()
        return True

    def _stop_preview_authoritative(self) -> None:
        """Stop playback through the existing authoritative stop seam."""
        self._preview_active = False
        if self._on_preview_stopped is not None:
            self._on_preview_stopped()

    def _clear_live_kit_audition_projection(self) -> None:
        if self._auditioning_live_kit_slot is not None:
            self._auditioning_live_kit_slot = None
            self.view_model.auditioning_live_kit_slot = None

    def audition_live_kit_slot(self, group: str, slot: str) -> bool:
        """Audition exactly the assigned slot row through the shared preview seam.

        Mirrors the authoritative Tk contract: an empty or unknown slot fails
        closed without dispatching anything, and a browser selection is never
        read or changed.  The dispatch reuses :attr:`_on_preview_requested`
        (the sole preview owner), so the Slot->A/B->Browser replacement
        semantics of the shared owner apply unchanged.  Live Kit honours its
        zero-offset contract (``start_ms=0``) instead of the Browser saved cue.
        A failed audition stops any prior playback through the authoritative
        stop seam and clears the audition projection, so playback can never be
        orphaned while the UI claims it is idle.
        """
        if self._live_kit is None:
            return False
        try:
            row = self._live_kit.state.assignment_for(group, slot)
        except ValueError:
            return False
        if row is None:
            return False
        was_active = self._preview_active
        result = self._dispatch_preview(row, start_ms=0)
        accepted = bool(result is None or getattr(result, "ok", result is not False))
        if not accepted:
            if was_active:
                self._stop_preview_authoritative()
            self._clear_live_kit_audition_projection()
            return False
        self._preview_active = True
        self._auditioning_live_kit_slot = (group, slot)
        self.view_model.auditioning_live_kit_slot = self._auditioning_live_kit_slot
        return True

    def request_add_to_kit(self, index: int) -> WorkbenchRow:
        """Emit an Add-to-Kit intent without assigning the row.

        The row is remembered as the pending Live Kit target; the actual slot
        assignment happens only through :meth:`assign_live_kit_slot`.
        """
        row = self.view_model.browser_rows[index].source_row
        self._pending_live_kit_row = row
        if self._on_add_to_kit_requested is not None:
            self._on_add_to_kit_requested(row)
        return row

    @property
    def pending_live_kit_add(self) -> str:
        return (
            self._pending_live_kit_row.display_name
            if self._pending_live_kit_row is not None
            else ""
        )

    def _sync_live_kit_projection(self) -> None:
        if self._live_kit is not None:
            self.view_model.live_kit_groups = self._live_kit.groups

    def toggle_live_kit_group(self, group: str) -> bool:
        if self._live_kit is None:
            return False
        try:
            self._live_kit.state.slots_for(group)
        except ValueError:
            return False
        self._live_kit.toggle_group(group)
        self._sync_live_kit_projection()
        return self._live_kit.presentation.is_collapsed(group)

    def assign_live_kit_slot(self, group: str, slot: str) -> bool:
        """Assign the pending (or selected) row through the existing seam.

        Add and Replace both resolve to :meth:`LiveKitState.assign`, which
        overwrites exactly the explicit target slot.
        """
        if self._live_kit is None:
            return False
        try:
            self._live_kit.state.slots_for(group)
        except ValueError:
            return False
        row = self._pending_live_kit_row
        if row is None:
            if not 0 <= self.selected_browser_index < len(self.view_model.browser_rows):
                return False
            row = self.view_model.browser_rows[self.selected_browser_index].source_row
        try:
            self._live_kit.assign(group, slot, row)
        except ValueError:
            return False
        self._pending_live_kit_row = None
        self._sync_live_kit_projection()
        if self._auditioning_live_kit_slot == (group, slot):
            self._clear_live_kit_audition_projection()
        return True

    def cancel_live_kit_add(self) -> bool:
        if self._pending_live_kit_row is None:
            return False
        self._pending_live_kit_row = None
        return True

    def navigate_browser(
        self, direction: str, *, browser_has_focus: bool
    ) -> WorkbenchRow | None:
        """Use browser-local arrows without capturing editable controls."""
        if not browser_has_focus or not self.view_model.browser_rows:
            return None
        if direction == "next":
            target = min(
                self.selected_browser_index + 1, len(self.view_model.browser_rows) - 1
            )
        elif direction == "previous":
            target = max(self.selected_browser_index - 1, 0)
        else:
            raise ValueError(f"Unsupported browser direction: {direction}")
        if target == self.selected_browser_index:
            return self.view_model.browser_rows[target].source_row
        return self.preview_row(target)

    @staticmethod
    def _harmonic_match_bpm_fingerprint(bpm: float | None) -> tuple[str, object]:
        if bpm is None:
            return ("none", "")
        try:
            value = float(bpm)
        except (TypeError, ValueError):
            return ("invalid", repr(bpm))
        if math.isnan(value):
            return ("nan", "")
        if math.isinf(value):
            return ("positive-infinity" if value > 0 else "negative-infinity", "")
        return ("finite", value)

    @classmethod
    def _harmonic_match_row_fingerprint(cls, row: WorkbenchRow) -> tuple[object, ...]:
        return (row.path, row.key, cls._harmonic_match_bpm_fingerprint(row.bpm), row.display_name)

    def _current_harmonic_match_fingerprint(self, anchor: WorkbenchRow) -> tuple[object, ...]:
        candidates = tuple(sorted(
            self._harmonic_match_row_fingerprint(row.source_row)
            for row in self.view_model.browser_rows if row.source_row.path != anchor.path
        ))
        return (self._harmonic_match_row_fingerprint(anchor), candidates)

    def _rebind_harmonic_match_rows(self, anchor: WorkbenchRow) -> bool:
        if self.harmony_controller is None:
            return True
        current_by_path: dict[str, WorkbenchRow] = {}
        ambiguous_paths: set[str] = set()
        for qml_row in self.view_model.browser_rows:
            row = qml_row.source_row
            if row.path in current_by_path:
                ambiguous_paths.add(row.path)
            else:
                current_by_path[row.path] = row
        rebound: list[WorkbenchRow] = []
        for suggestion in self.harmony_controller.results:
            path = suggestion.row.path
            if path in ambiguous_paths or path not in current_by_path:
                return False
            rebound.append(current_by_path[path])
        self.harmony_controller.anchor = anchor
        for suggestion, row in zip(self.harmony_controller.results, rebound, strict=True):
            suggestion.row = row
        return True

    @property
    def effective_harmony_status(self) -> str:
        """Return the display status derived from actual pane visibility and controller state."""
        if not self.harmonic_match_open:
            return "Harmonic Match ist ausgeschaltet."
        if self.harmony_controller is None:
            return "Harmonic Match ist offen."
        if self.harmony_controller.status == "Harmonic Match ist ausgeschaltet.":
            return "Harmonic Match ist offen."
        return self.harmony_controller.status

    def _project_harmonic_match(self, anchor: WorkbenchRow) -> None:
        if self.harmony_controller is None:
            self.view_model.harmony_status = (
                "Harmonic Match ist offen."
                if self.harmonic_match_open
                else "Harmonic Match ist ausgeschaltet."
            )
            return
        self.view_model.harmony_rows = tuple(_qml_harmony_row(item) for item in self.harmony_controller.results)
        self.view_model.harmony_anchor = f"Reference: {anchor.display_name} · {anchor.key or '—'}"
        self.view_model.harmony_status = self.effective_harmony_status

    def select_harmonic_match(self, index: int) -> WorkbenchRow:
        if not 0 <= index < len(self.view_model.harmony_rows):
            raise IndexError("Harmonic-Match-Zeilenindex außerhalb des sichtbaren Modells.")
        self._harmonic_match_selected_index = index
        return self.view_model.harmony_rows[index].source_row

    def preview_harmonic_match(self, index: int) -> WorkbenchRow:
        row = self.select_harmonic_match(index)
        was_active = self._preview_active
        result = self._dispatch_preview(row)
        accepted = bool(
            result is None or getattr(result, "ok", result is not False)
        )
        if not accepted and was_active:
            self._stop_preview_authoritative()
        self._preview_active = accepted
        self._clear_live_kit_audition_projection()
        return row

    def navigate_harmonic_match(self, direction: str, *, match_has_focus: bool) -> WorkbenchRow | None:
        if not match_has_focus or not self.view_model.harmony_rows:
            return None
        if direction == "next":
            index = min(self._harmonic_match_selected_index + 1, len(self.view_model.harmony_rows) - 1)
        elif direction == "previous":
            index = max(self._harmonic_match_selected_index - 1, 0)
        else:
            raise ValueError(f"Unsupported harmonic direction: {direction}")
        if index == self._harmonic_match_selected_index:
            return self.view_model.harmony_rows[index].source_row
        return self.preview_harmonic_match(index)

    def request_add_harmonic_match_to_kit(self, index: int) -> WorkbenchRow:
        row = self.select_harmonic_match(index)
        self._pending_live_kit_row = row
        if self._on_add_to_kit_requested is not None:
            self._on_add_to_kit_requested(row)
        return row

    def set_harmonic_match_scroll_y(self, value: float) -> None:
        if not self.harmonic_match_open:
            return
        self._harmonic_match_scroll_y = max(0.0, float(value))

    def replace_browser_scope(self, scope: object) -> None:
        """Central hook after a successful browser-scope replacement.

        When *scope* differs from the scope the current harmonic-match session
        was computed against, the session is deterministically invalidated:
        the panel closes, old harmony rows stop being actionable, and the next
        open computes the new scope's anchor and candidate pool exactly once.
        Same-scope reloads keep the existing close/reopen reuse intact.
        """
        self._harmonic_match_browser_scope = scope
        if scope is not None and scope == self._harmonic_match_session_scope:
            if not self.harmonic_match_open:
                return
            if not self.view_model.browser_rows:
                self._invalidate_harmonic_session()
                return
            if not 0 <= self.view_model.selected_browser_index < len(self.view_model.browser_rows):
                self._invalidate_harmonic_session()
                return
            anchor = self.view_model.browser_rows[self.selected_browser_index].source_row
            fingerprint = self._current_harmonic_match_fingerprint(anchor)
            if fingerprint == self._harmonic_match_context_fingerprint and self._rebind_harmonic_match_rows(anchor):
                self._project_harmonic_match(anchor)
                return
            if self.harmony_controller is not None:
                self.harmony_controller.set_anchor(
                    anchor,
                    tuple(row.source_row for row in self.view_model.browser_rows),
                )
            self._harmonic_match_context_fingerprint = fingerprint
            self._harmonic_match_selected_index = 0
            self._harmonic_match_scroll_y = 0.0
            self._project_harmonic_match(anchor)
            return
        self._invalidate_harmonic_session()

    def _invalidate_harmonic_session(self) -> None:
        if self.harmonic_match_open:
            self.harmonic_match_open = False
            self.view_model.state_id = "screen1-default-3panel"
        self.view_model.harmony_rows = ()
        self.view_model.harmony_anchor = ""
        self.view_model.harmony_status = "Harmonic Match geschlossen – Browser-Scope wurde ersetzt."
        self._harmonic_match_context_fingerprint = None
        self._harmonic_match_selected_index = 0
        self._harmonic_match_scroll_y = 0.0
        self.stop_preview()
        if self.harmony_controller is not None:
            self.harmony_controller.anchor = None
            self.harmony_controller.results = ()
            self.harmony_controller.status = "Harmonic Match ist ausgeschaltet."
        self._harmonic_match_session_scope = None

    def toggle_harmonic_match(self) -> bool:
        """Open/close the existing harmony controller without mutating other state."""
        if self.harmonic_match_open:
            self.harmonic_match_open = False
            self.view_model.state_id = "screen1-default-3panel"
            return False
        if not self.view_model.browser_rows:
            self.view_model.harmony_rows = ()
            self.view_model.harmony_anchor = ""
            self.view_model.harmony_status = "Kein Sample als Harmonic-Match-Referenz ausgewählt."
            return False
        if not 0 <= self.view_model.selected_browser_index < len(self.view_model.browser_rows):
            self.view_model.harmony_rows = ()
            self.view_model.harmony_anchor = ""
            self.view_model.harmony_status = "Kein Sample als Harmonic-Match-Referenz ausgewählt."
            return False
        anchor = self.view_model.browser_rows[self.selected_browser_index].source_row
        fingerprint = self._current_harmonic_match_fingerprint(anchor)
        if fingerprint != self._harmonic_match_context_fingerprint or not self._rebind_harmonic_match_rows(anchor):
            if self.harmony_controller is not None:
                self.harmony_controller.set_anchor(anchor, tuple(row.source_row for row in self.view_model.browser_rows))
            self._harmonic_match_context_fingerprint = fingerprint
            self._harmonic_match_selected_index = 0
            self._harmonic_match_scroll_y = 0.0
        self._harmonic_match_session_scope = self._harmonic_match_browser_scope
        self.harmonic_match_open = True
        self._project_harmonic_match(anchor)
        self.view_model.state_id = "screen1-harmonic-4panel"
        return True


def qml_runtime_available() -> bool:
    try:
        import PySide6  # noqa: F401
    except ModuleNotFoundError:
        return False
    return True


QML_SOURCE = r'''
import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

ApplicationWindow {
    id: window
    visible: true
    width: 1600; height: 900
    minimumWidth: 1120; minimumHeight: 640
    color: "#08090a"
    title: "Sample Brain"
    property var screenData: screenModel
    property var interaction: interactionModel
    property color panel: "#0e1012"
    property color panelAlt: "#15181c"
    property color textColor: "#eceef1"
    property color muted: "#8b9098"
    property color border: "#26292e"
    property color accent: "#b1122b"
    property color divider: "#26292e"
    property int textTitle: 18
    property int textBody: 14
    property int textMeta: 13
    property int textCaption: 11
    property int browserRowHeight: 66
    property int browserRowInset: 12
    property int browserRowSpacing: 12
    property int browserWaveformWidth: 180
    property int browserWaveformMin: 150
    property int browserMetaColumnWidth: 48
    property int browserLengthColumnWidth: 62
    property int browserAddColumnWidth: 96
    property int browserDelegateCreations: 0

    FolderDialog {
        id: addSourceDialog
        title: "Sample Source hinzufügen"
        onAccepted: libraryInteraction.registerSourceUrl(selectedFolder.toString())
    }

    Dialog {
        id: removeSourceDialog
        title: "Sample Source entfernen"
        modal: true
        width: 520
        standardButtons: Dialog.Ok | Dialog.Cancel
        onAccepted: libraryInteraction.confirmRemoveSource()
        onRejected: libraryInteraction.cancelRemoveSource()
        contentItem: ColumnLayout {
            Label { text: "Registrierte Quelle: " + libraryInteraction.removalPath; wrapMode: Text.Wrap; Layout.fillWidth: true }
            Label { text: "Status: " + libraryInteraction.removalAvailability }
            Label { text: libraryInteraction.removalCachedSampleCount + " Cache-Metadaten werden gelöscht." }
            Label { text: "Nur aus Sample Brain entfernen. Originaldateien bleiben unverändert."; wrapMode: Text.Wrap; Layout.fillWidth: true }
        }
    }

    Connections {
        target: libraryInteraction
        function onRemovalRequested() { removeSourceDialog.open() }
    }

    header: Rectangle {
        height: 68; color: "#090a0b"; border.color: window.border
        RowLayout { anchors.fill: parent; anchors.leftMargin: 22; anchors.rightMargin: 22
            Label { text: "◉  Sample Brain"; color: window.textColor; font.pixelSize: 21; font.bold: true }
            Item { Layout.fillWidth: true }
            Label { text: "MASTER"; color: window.muted; font.pixelSize: 12 }
            Label { text: "132"; color: window.textColor; font.pixelSize: 24; font.bold: true }
            Label { text: "BPM"; color: window.muted; font.pixelSize: 12 }
            Item { width: 24 }
            Label { text: "GRID"; color: window.muted; font.pixelSize: 12 }
            Label { text: "4/4"; color: window.textColor; font.pixelSize: 24; font.bold: true }
            Item { width: 24 }
            Label { text: "SYNC"; color: window.muted; font.pixelSize: 12 }
            Rectangle { width: 48; height: 25; radius: 4; color: window.accent
                Label { anchors.centerIn: parent; text: "ON"; color: "white"; font.bold: true }
            }
        }
    }

    RowLayout { anchors.fill: parent; spacing: 0
        Keys.onPressed: function(event) {
            if (event.key === Qt.Key_Escape && window.interaction.previewActive) {
                window.interaction.stopPreview()
                event.accepted = true
            }
        }
        Rectangle { id: libraryPane; objectName: "libraryPane"; Layout.preferredWidth: 300; Layout.minimumWidth: 230; Layout.fillHeight: true; color: window.panel; border.color: window.border
            ColumnLayout { anchors.fill: parent; anchors.margins: 16
                RowLayout { Layout.fillWidth: true
                    Label { text: "LIBRARY"; color: window.muted; font.pixelSize: 12; Layout.fillWidth: true }
                    Button { text: "Add Source"; onClicked: addSourceDialog.open() }
                    Button { visible: libraryInteraction.canRemoveSelectedSource; text: "Remove"; onClicked: libraryInteraction.prepareRemoveSource() }
                }
                TreeView {
                    id: libraryTree
                    objectName: "libraryTree"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    model: libraryTreeModel
                    clip: true
                    focus: true
                    activeFocusOnTab: true
                    boundsBehavior: Flickable.StopAtBounds
                    delegate: TreeViewDelegate {
                        id: libraryDelegate
                        implicitHeight: 34
                        indentation: 16
                        background: Rectangle {
                            color: libraryInteraction.selectedLibraryNodeId === model.nodeId ? "#211014" : "transparent"
                            border.color: libraryInteraction.selectedLibraryNodeId === model.nodeId ? window.accent : "transparent"
                        }
                        contentItem: Item {
                            implicitHeight: 34
                            implicitWidth: libraryTree.width
                            TapHandler {
                                onTapped: {
                                    if (model.error) {
                                        libraryInteraction.retryLibraryNode(model.parentNodeId)
                                    } else if (model.kind === "add_source" && model.nodeId === "action:add-source") {
                                        addSourceDialog.open()
                                    } else if (model.selectable) {
                                        libraryTree.forceActiveFocus()
                                        libraryInteraction.selectLibraryNode(model.nodeId)
                                    }
                                }
                            }
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 4
                                anchors.rightMargin: 8
                                Label {
                                    Layout.fillWidth: true
                                    text: model.loading ? "Loading…" : model.display
                                    color: model.availability === "offline" ? window.muted : window.textColor
                                    opacity: model.error ? 0.72 : 1.0
                                    elide: Text.ElideRight
                                    font.pixelSize: 14
                                }
                                Label {
                                    visible: model.error
                                    text: "Retry"
                                    color: window.muted
                                    font.pixelSize: 11
                                }
                            }
                        }
                    }
                    Keys.onPressed: function(event) {
                        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                            browser.forceActiveFocus()
                            event.accepted = true
                        }
                    }
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                }
            }
        }
        Rectangle { id: browserPane; objectName: "browserPane"; Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.fillHeight: true; color: "#0a0b0c"; border.color: window.border
            ColumnLayout { anchors.fill: parent; anchors.margins: 18; spacing: 10
                RowLayout { Layout.fillWidth: true
                    ColumnLayout { Layout.fillWidth: true; spacing: 2
                        Label { text: window.screenData.browserContext; color: window.textColor; font.pixelSize: window.textTitle; font.bold: true }
                        Label { text: window.screenData.browserRows.length + " samples"; color: window.muted; font.pixelSize: window.textCaption }
                        Label { visible: window.screenData.errorMessage.length > 0; text: window.screenData.errorMessage; color: window.accent; font.pixelSize: 11 }
                    }
                    Item { Layout.fillWidth: true }
                    Button {
                        objectName: "harmonicMatchButton"
                        text: "Harmonic Match"
                        background: Rectangle {
                            color: window.interaction.harmonicMatchOpen ? window.accent : window.panelAlt
                            border.width: window.interaction.harmonicMatchOpen ? 1 : 0
                            border.color: window.accent
                            radius: 4
                        }
                        contentItem: Text {
                            text: "Harmonic Match"
                            color: window.textColor
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            rightPadding: 16
                            leftPadding: 16
                        }
                        onClicked: window.interaction.toggleHarmonicMatch()
                    }
                    TextField { objectName: "browserSearch"; placeholderText: "Search samples"; placeholderTextColor: window.muted; Layout.preferredWidth: 230; Layout.minimumWidth: 120
                        background: Rectangle {
                            radius: 6
                            border.width: 1
                            border.color: parent.activeFocus ? window.accent : window.border
                            color: "transparent"
                        }
                    }
                }
                RowLayout {
                    visible: window.screenData.analysisStatus !== "idle"
                    Layout.fillWidth: true
                    Label {
                        Layout.fillWidth: true
                        text: window.screenData.analysisStatus === "scanning" ? "Analysiere Quelle …" :
                              window.screenData.analysisStatus === "analyzing" ? "Analysiere " + window.screenData.analysisSource :
                              window.screenData.analysisStatus === "done" ? "Analyse abgeschlossen" :
                              window.screenData.analysisStatus === "cancelled" ? "Analyse abgebrochen" :
                              window.screenData.analysisStatus === "error" ? window.screenData.analysisError : ""
                        color: window.screenData.analysisStatus === "error" ? window.accent : window.muted
                        font.pixelSize: 11
                    }
                    Label {
                        visible: window.screenData.analysisTotal > 0
                        text: window.screenData.analysisCurrent + " / " + window.screenData.analysisTotal
                        color: window.textColor
                        font.pixelSize: 11
                    }
                    ProgressBar {
                        visible: window.screenData.analysisStatus === "scanning" || window.screenData.analysisStatus === "analyzing"
                        indeterminate: window.screenData.analysisTotal === 0
                        from: 0
                        to: Math.max(window.screenData.analysisTotal, 1)
                        value: window.screenData.analysisCurrent
                        Layout.preferredWidth: 120
                    }
                    Button {
                        visible: window.screenData.analysisStatus === "scanning" || window.screenData.analysisStatus === "analyzing"
                        text: "Cancel"
                        onClicked: window.screenData.cancelAnalysis()
                    }
                }
                RowLayout { Layout.fillWidth: true; anchors.leftMargin: window.browserRowInset; anchors.rightMargin: window.browserRowInset; spacing: window.browserRowSpacing
                    Item { Layout.preferredWidth: window.browserWaveformWidth; Layout.minimumWidth: window.browserWaveformMin }
                    Label { text: "SAMPLE NAME"; color: window.muted; Layout.fillWidth: true; font.pixelSize: window.textCaption; font.bold: true }
                    Label { text: "BPM"; color: window.muted; Layout.preferredWidth: window.browserMetaColumnWidth; horizontalAlignment: Text.AlignRight; font.pixelSize: window.textCaption; font.bold: true }
                    Label { text: "KEY"; color: window.muted; Layout.preferredWidth: window.browserMetaColumnWidth; horizontalAlignment: Text.AlignRight; font.pixelSize: window.textCaption; font.bold: true }
                    Label { text: "LENGTH"; color: window.muted; Layout.preferredWidth: window.browserLengthColumnWidth; horizontalAlignment: Text.AlignRight; font.pixelSize: window.textCaption; font.bold: true }
                    Item { Layout.preferredWidth: window.browserAddColumnWidth }
                }
                ListView { id: browser; objectName: "browserList"; Layout.fillWidth: true; Layout.fillHeight: true; model: window.screenData.browserRows; clip: true; reuseItems: true; focus: true; property int rowHeight: window.browserRowHeight; implicitHeight: window.browserRowHeight * 2
                    Keys.onPressed: function(event) {
                        if (event.key === Qt.Key_Down) { window.interaction.navigateBrowser(1); event.accepted = true }
                        else if (event.key === Qt.Key_Up) { window.interaction.navigateBrowser(-1); event.accepted = true }
                        else if (event.key === Qt.Key_Escape) { window.interaction.stopPreview(); event.accepted = true }
                    }
                    delegate: Rectangle { id: browserRow; width: browser.width; height: browser.rowHeight; color: index === window.screenData.selectedBrowserIndex ? "#211014" : (rowSelection.containsMouse ? "#15181c" : "transparent"); border.width: index === window.screenData.selectedBrowserIndex ? 1 : 0; border.color: window.accent
                        Component.onCompleted: window.browserDelegateCreations += 1
                        MouseArea { id: rowSelection; anchors.fill: parent; z: 0; hoverEnabled: true; onClicked: { browser.forceActiveFocus(); window.interaction.selectRow(index) } }
                        RowLayout { anchors.fill: parent; anchors.leftMargin: window.browserRowInset; anchors.rightMargin: window.browserRowInset; spacing: window.browserRowSpacing; z: 1
                            Item { id: waveformSurface; Layout.preferredWidth: window.browserWaveformWidth; Layout.minimumWidth: window.browserWaveformMin; Layout.fillHeight: true
                                Canvas { id: waveformCanvas; anchors.fill: parent; property var envelope: modelData.waveform
                                    onEnvelopeChanged: requestPaint()
                                    onPaint: {
                                        var context = getContext("2d")
                                        context.clearRect(0, 0, width, height)
                                        context.strokeStyle = index === window.screenData.selectedBrowserIndex ? window.accent : "#6d737c"
                                        context.lineWidth = 1.4
                                        context.beginPath()
                                        var points = envelope || []
                                        var center = height / 2
                                        if (points.length === 0) {
                                            context.moveTo(0, center)
                                            context.lineTo(width, center)
                                        } else {
                                            var step = width / points.length
                                            for (var point = 0; point < points.length; point++) {
                                                var value = Math.max(0, Math.min(1, Number(points[point]) || 0))
                                                var x = Math.min(width, point * step + step / 2)
                                                var amplitude = Math.max(2, height * 0.42 * value)
                                                context.moveTo(x, center - amplitude)
                                                context.lineTo(x, center + amplitude)
                                            }
                                        }
                                        context.stroke()
                                    }
                                }
                                MouseArea { anchors.fill: parent; z: 2; onClicked: { browser.forceActiveFocus(); window.interaction.previewRow(index) } }
                            }
                            ColumnLayout { Layout.fillWidth: true
                                spacing: 3
                                Label { text: modelData.name; color: window.textColor; font.pixelSize: window.textBody; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
                                Label { text: modelData.type; color: window.muted; font.pixelSize: window.textCaption; elide: Text.ElideRight; Layout.fillWidth: true }
                            }
                            Label { text: modelData.bpm; color: window.textColor; Layout.preferredWidth: window.browserMetaColumnWidth; horizontalAlignment: Text.AlignRight; font.pixelSize: window.textMeta }
                            Label { text: modelData.key; color: window.textColor; Layout.preferredWidth: window.browserMetaColumnWidth; horizontalAlignment: Text.AlignRight; font.pixelSize: window.textMeta }
                            Label { text: modelData.duration; color: window.textColor; Layout.preferredWidth: window.browserLengthColumnWidth; horizontalAlignment: Text.AlignRight; font.pixelSize: window.textMeta }
                            Rectangle {
                                id: addButton
                                Layout.preferredWidth: window.browserAddColumnWidth
                                Layout.preferredHeight: 28
                                radius: 3
                                property bool hovered: addButtonMouse.containsMouse
                                color: addButtonMouse.pressed ? "#3a1720" : (addButtonMouse.containsMouse ? "#24151a" : "transparent")
                                border.color: addButtonMouse.containsMouse || index === window.screenData.selectedBrowserIndex ? "#5b1d2a" : "transparent"
                                Label {
                                    anchors.fill: parent
                                    text: "+ Add to Kit"
                                    color: addButtonMouse.pressed || addButtonMouse.containsMouse || index === window.screenData.selectedBrowserIndex ? window.accent : window.muted
                                    horizontalAlignment: Text.AlignRight
                                    verticalAlignment: Text.AlignVCenter
                                    font.pixelSize: 11
                                }
                                MouseArea {
                                    id: addButtonMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    onClicked: {
                                        browser.forceActiveFocus()
                                        window.interaction.addToKit(index)
                                    }
                                }
                            }
                        }
                        Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 1; color: window.divider; opacity: index === window.screenData.selectedBrowserIndex ? 0.35 : 0.8 }
                    }
                }
            }
        }
        Rectangle { visible: window.interaction.harmonicMatchOpen; Layout.preferredWidth: visible ? 360 : 0; Layout.minimumWidth: visible ? 360 : 0; Layout.fillHeight: true; color: window.panel; border.color: window.border
            onVisibleChanged: {
                if (visible) {
                    harmonicMatchList.forceActiveFocus()
                    Qt.callLater(function() {
                        if (window.interaction.harmonyScrollY > 0) {
                            harmonicMatchList.contentY = window.interaction.harmonyScrollY
                        }
                        window.interaction.requestHarmonyWaveforms(
                            Math.max(0, Math.floor(harmonicMatchList.contentY / 72)),
                            Math.ceil(harmonicMatchList.height / 72) + 2
                        )
                    })
                } else {
                    browser.forceActiveFocus()
                }
            }
            ColumnLayout { anchors.fill: parent; anchors.margins: 14
                Label { text: "Harmonic Matches"; color: window.textColor; font.pixelSize: 18; font.bold: true }
                Label { text: window.screenData.harmonyAnchor; color: window.muted; font.pixelSize: 12 }
                Label { text: window.screenData.harmonyStatus; color: window.muted; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true }
                ListView { id: harmonicMatchList; objectName: "harmonicMatchList"; Layout.fillWidth: true; Layout.fillHeight: true; model: window.screenData.harmonyRows; clip: true; reuseItems: true; focus: window.interaction.harmonicMatchOpen
                    Keys.onUpPressed: {
                        window.interaction.navigateHarmony(-1)
                        harmonicMatchList.currentIndex = window.interaction.selectedHarmonyIndex
                        harmonicMatchList.positionViewAtIndex(harmonicMatchList.currentIndex, ListView.Contain)
                    }
                    Keys.onDownPressed: {
                        window.interaction.navigateHarmony(1)
                        harmonicMatchList.currentIndex = window.interaction.selectedHarmonyIndex
                        harmonicMatchList.positionViewAtIndex(harmonicMatchList.currentIndex, ListView.Contain)
                    }
                    Keys.onEscapePressed: window.interaction.stopPreview()
                    onContentYChanged: {
                        window.interaction.setHarmonyScrollY(contentY)
                        window.interaction.requestHarmonyWaveforms(
                            Math.max(0, Math.floor(contentY / 72)),
                            Math.ceil(height / 72) + 2
                        )
                    }
                    onHeightChanged: {
                        if (visible) {
                            window.interaction.requestHarmonyWaveforms(
                                Math.max(0, Math.floor(contentY / 72)),
                                Math.ceil(height / 72) + 2
                            )
                        }
                    }
                    delegate: Rectangle { width: parent.width; height: 72; color: index === window.interaction.selectedHarmonyIndex ? window.panelAlt : "transparent"; border.color: window.border
                        MouseArea { anchors.fill: parent; onClicked: { harmonicMatchList.forceActiveFocus(); window.interaction.selectHarmonyRow(index) } }
                        RowLayout { anchors.fill: parent; anchors.margins: 9
                            Canvas { Layout.preferredWidth: 100; Layout.fillHeight: true; property var envelope: modelData.waveform
                                onPaint: {
                                    var context = getContext("2d")
                                    context.clearRect(0, 0, width, height)
                                    context.strokeStyle = "#6d737c"
                                    context.lineWidth = 1.2
                                    context.beginPath()
                                    var points = envelope || []
                                    var center = height / 2
                                    var step = points.length > 0 ? width / points.length : width
                                    if (points.length === 0) { context.moveTo(0, center); context.lineTo(width, center) }
                                    for (var point = 0; point < points.length; point++) {
                                        var value = Math.max(0, Math.min(1, Number(points[point]) || 0))
                                        var x = Math.min(width, point * step + step / 2)
                                        var amplitude = Math.max(2, height * 0.38 * value)
                                        context.moveTo(x, center - amplitude)
                                        context.lineTo(x, center + amplitude)
                                    }
                                    context.stroke()
                                }
                                MouseArea { anchors.fill: parent; onClicked: { harmonicMatchList.forceActiveFocus(); window.interaction.previewHarmonyRow(index) } }
                            }
                            ColumnLayout { Layout.fillWidth: true
                                Label { text: modelData.name; color: window.textColor }
                                Label { text: modelData.type + " · " + modelData.relation + " · " + modelData.fit; color: window.muted; font.pixelSize: 11 }
                            }
                            Label { text: modelData.key; color: window.accent }
                            Text { text: "+ Add"; color: window.muted; font.pixelSize: 11
                                MouseArea { anchors.fill: parent; onClicked: { harmonicMatchList.forceActiveFocus(); window.interaction.addHarmonyToKit(index) } }
                            }
                        }
                    }
                }
            }
        }
        Rectangle { id: liveKitPane; objectName: "liveKitPane"; Layout.preferredWidth: 300; Layout.fillHeight: true; color: window.panel; border.color: window.border
            ColumnLayout { anchors.fill: parent; anchors.margins: 14; spacing: 8
                RowLayout { Layout.fillWidth: true
                    Label { text: "LIVE KIT"; color: window.muted; font.pixelSize: 12; Layout.fillWidth: true }
                    Label { text: window.screenData.liveKitAssignedCount + " / " + window.screenData.liveKitTotalSlotCount; color: window.muted; font.pixelSize: 11 }
                }
                Rectangle {
                    id: liveKitPendingBanner
                    objectName: "liveKitPendingBanner"
                    visible: window.interaction.liveKitPendingAdd !== ""
                    Layout.fillWidth: true
                    Layout.preferredHeight: 30
                    radius: 4
                    color: "#211014"
                    border.color: window.accent
                    focus: visible
                    Keys.onEscapePressed: window.interaction.escapeLiveKitContext()
                    Label {
                        anchors.fill: parent
                        anchors.leftMargin: 8
                        anchors.rightMargin: 8
                        text: "Add " + window.interaction.liveKitPendingAdd + " · Slot + · Esc"
                        color: "#f2a0ab"
                        font.pixelSize: 11
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                    }
                }
                Repeater { model: window.screenData.liveKitGroups
                    delegate: Rectangle {
                        property int kitGroupIndex: index
                        Layout.fillWidth: true
                        implicitHeight: 44 + (modelData.active ? modelData.slots.length * 26 + 14 : 0)
                        radius: 6
                        color: modelData.active ? window.panelAlt : "transparent"
                        border.color: modelData.active ? window.accent : window.border
                        ColumnLayout { anchors.fill: parent; spacing: 0
                            Item { Layout.fillWidth: true; Layout.preferredHeight: 44; Layout.leftMargin: 12; Layout.rightMargin: 10
                                RowLayout { anchors.fill: parent; spacing: 6
                                    Label { text: (index + 1) + "  "; color: modelData.active ? window.accent : window.muted; font.pixelSize: 13; font.bold: true }
                                    Label { text: modelData.name; color: window.textColor; font.pixelSize: 14; font.bold: modelData.active; elide: Text.ElideRight; Layout.fillWidth: true }
                                    Label { text: modelData.active ? "▾" : "▸"; color: modelData.active ? window.accent : window.muted; font.pixelSize: 12 }
                                }
                                MouseArea {
                                    id: liveKitGroupHeader
                                    objectName: "liveKitGroupHeader" + index
                                    anchors.fill: parent
                                    onClicked: window.interaction.toggleLiveKitGroup(kitGroupIndex)
                                }
                            }
                            ColumnLayout { visible: modelData.active; Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 10; Layout.topMargin: 2
                                Repeater { model: modelData.active ? modelData.slots : []
                                    delegate: Item {
                                        objectName: "liveKitSlot" + kitGroupIndex + "_" + index
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 26
                                        // This is renderer-only intent, derived from the authoritative
                                        // pending Add property and the current read-only slot projection.
                                        // It deliberately does not retain a second Live-Kit target state.
                                        property bool liveKitSlotTarget: window.interaction.liveKitPendingAdd !== "" && (slotAddMouse.containsMouse || slotAddMouse.activeFocus)
                                        property bool liveKitReplaceTarget: liveKitSlotTarget && modelData.assigned
                                        Rectangle {
                                            id: slotAuditionBackdrop
                                            anchors.fill: parent
                                            radius: 3
                                            visible: modelData.auditioning
                                            color: "#1a1418"
                                            border.color: window.accent
                                        }
                                        Rectangle {
                                            id: liveKitSlotTargetBackdrop
                                            objectName: "liveKitSlotTarget" + kitGroupIndex + "_" + index
                                            anchors.fill: parent
                                            radius: 3
                                            visible: liveKitSlotTarget
                                            color: "#211014"
                                            border.color: window.accent
                                        }
                                        MouseArea {
                                            id: slotAuditionMouse
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            enabled: modelData.assigned && window.interaction.liveKitPendingAdd === ""
                                            onClicked: window.interaction.auditionLiveKitSlot(kitGroupIndex, index)
                                        }
                                        RowLayout { anchors.fill: parent; spacing: 6
                                            Item { Layout.preferredWidth: 14; Layout.preferredHeight: 26
                                                Label {
                                                    anchors.centerIn: parent
                                                    text: modelData.assigned ? "▶" : ""
                                                    color: slotAuditionMouse.containsMouse ? window.accent : (modelData.auditioning ? window.accent : window.muted)
                                                    font.pixelSize: 10
                                                }
                                            }
                                            Label { text: modelData.name; color: window.muted; font.pixelSize: 11; Layout.fillWidth: true; elide: Text.ElideRight }
                                            Label { text: modelData.assignment; color: modelData.auditioning ? window.accent : (modelData.assigned ? window.textColor : window.muted); font.pixelSize: 11; elide: Text.ElideRight }
                                            Rectangle {
                                                id: slotAdd
                                                Layout.preferredHeight: 22
                                                radius: 3
                                                Layout.preferredWidth: liveKitReplaceTarget ? 52 : 22
                                                color: liveKitSlotTarget ? "#24151a" : "transparent"
                                                border.color: liveKitSlotTarget ? window.accent : "transparent"
                                                Label {
                                                    anchors.centerIn: parent
                                                    objectName: "liveKitSlotActionLabel" + kitGroupIndex + "_" + index
                                                    text: liveKitReplaceTarget ? "Replace" : "+"
                                                    color: liveKitSlotTarget ? window.accent : (slotAddMouse.containsMouse ? window.textColor : window.muted)
                                                    font.pixelSize: liveKitReplaceTarget ? 10 : 13
                                                }
                                            }
                                        }
                                        MouseArea {
                                            id: slotAddMouse
                                            objectName: "liveKitSlotAction" + kitGroupIndex + "_" + index
                                            anchors.right: parent.right
                                            anchors.verticalCenter: parent.verticalCenter
                                            width: slotAdd.width
                                            height: slotAdd.height
                                            hoverEnabled: true
                                            focus: true
                                            z: 1
                                            onClicked: { slotAddMouse.forceActiveFocus(); window.interaction.addLiveKitSlot(kitGroupIndex, index) }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                Item { Layout.fillHeight: true }
            }
        }
    }
}
'''


def _load_qt_modules():
    try:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtQml import QQmlApplicationEngine
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Qt Quick Screen-1 Renderer benötigt die optionale Abhängigkeit: pip install -e '.[qtquick]'"
        ) from exc
    return QUrl, QGuiApplication, QQmlApplicationEngine


def _qml_interaction_bridge(
    adapter: Screen1QmlInteractionAdapter,
    *,
    on_state_changed: Callable[[], None] | None = None,
    on_waveform_request: Callable[[int, int], None] | None = None,
    on_harmony_waveform_request: Callable[[int, int], None] | None = None,
):
    """Expose the pure interaction adapter to QML only when Qt is installed."""
    from PySide6.QtCore import QObject, Property, Signal, Slot

    class QmlInteractionBridge(QObject):
        state_changed = Signal()
        addToKitIntent = Signal(str)

        def _refresh(self) -> None:
            if on_state_changed is not None:
                on_state_changed()
            self.state_changed.emit()

        @Slot()
        def refreshState(self) -> None:
            self._refresh()

        @Property(int, notify=state_changed)
        def selectedBrowserIndex(self) -> int:
            return adapter.selected_browser_index

        @Property(bool, notify=state_changed)
        def harmonicMatchOpen(self) -> bool:
            return adapter.harmonic_match_open

        @Property(bool, notify=state_changed)
        def previewActive(self) -> bool:
            return adapter.preview_active

        @Property(int, notify=state_changed)
        def selectedHarmonyIndex(self) -> int:
            return adapter.selected_harmonic_match_index

        @Property(float, notify=state_changed)
        def harmonyScrollY(self) -> float:
            return adapter.harmonic_match_scroll_y

        @Slot(int)
        def selectRow(self, index: int) -> None:
            adapter.select_row(index)
            self._refresh()

        @Slot(int)
        def previewRow(self, index: int) -> None:
            adapter.preview_row(index)
            self._refresh()

        @Slot()
        def stopPreview(self) -> None:
            adapter.stop_preview()
            self._refresh()

        @Slot(int)
        def addToKit(self, index: int) -> None:
            row = adapter.request_add_to_kit(index)
            self.addToKitIntent.emit(row.relative_path or str(row.path))
            self._refresh()

        @Slot(int)
        def selectHarmonyRow(self, index: int) -> None:
            adapter.select_harmonic_match(index)
            self._refresh()

        @Slot(int)
        def previewHarmonyRow(self, index: int) -> None:
            adapter.preview_harmonic_match(index)
            self._refresh()

        @Slot(int)
        def addHarmonyToKit(self, index: int) -> None:
            row = adapter.request_add_harmonic_match_to_kit(index)
            self.addToKitIntent.emit(row.relative_path or str(row.path))
            self._refresh()

        @Property(str, notify=state_changed)
        def liveKitPendingAdd(self) -> str:
            return adapter.pending_live_kit_add

        def _live_kit_group_name(self, index: int) -> str | None:
            groups = adapter.view_model.live_kit_groups
            if not 0 <= index < len(groups):
                return None
            return groups[index].name

        def _live_kit_slot_target(self, group_index: int, slot_index: int) -> tuple[str, str] | None:
            groups = adapter.view_model.live_kit_groups
            if not 0 <= group_index < len(groups):
                return None
            slots = groups[group_index].slots
            if not 0 <= slot_index < len(slots):
                return None
            return (groups[group_index].name, slots[slot_index].name)

        @Slot(int)
        def toggleLiveKitGroup(self, index: int) -> None:
            name = self._live_kit_group_name(index)
            if name is None:
                return
            adapter.toggle_live_kit_group(name)
            self._refresh()

        @Slot(int, int)
        def addLiveKitSlot(self, group_index: int, slot_index: int) -> None:
            target = self._live_kit_slot_target(group_index, slot_index)
            if target is None:
                return
            if adapter.assign_live_kit_slot(*target):
                self._refresh()

        @Slot(int, int)
        def auditionLiveKitSlot(self, group_index: int, slot_index: int) -> None:
            target = self._live_kit_slot_target(group_index, slot_index)
            if target is None:
                return
            adapter.audition_live_kit_slot(*target)
            self._refresh()

        @Slot()
        def cancelLiveKitAdd(self) -> None:
            adapter.cancel_live_kit_add()
            self._refresh()

        @Slot()
        def escapeLiveKitContext(self) -> None:
            """Coherent single-Escape for the pending-add banner.

            Playback must never keep running because the focused banner
            consumed the event: this routes through the same authoritative
            stop contract first, then applies the established pending-add
            cancel.  Both operations are idempotent and safe when idle.
            """
            adapter.stop_preview()
            adapter.cancel_live_kit_add()
            self._refresh()

        @Slot(int)
        def navigateHarmony(self, step: int) -> None:
            adapter.navigate_harmonic_match("next" if step > 0 else "previous", match_has_focus=True)
            self._refresh()

        @Slot(float)
        def setHarmonyScrollY(self, value: float) -> None:
            adapter.set_harmonic_match_scroll_y(value)

        @Slot(int, int)
        def requestWaveforms(self, start: int, count: int) -> None:
            if on_waveform_request is not None:
                on_waveform_request(start, count)

        @Slot(int, int)
        def requestHarmonyWaveforms(self, start: int, count: int) -> None:
            if on_harmony_waveform_request is not None:
                on_harmony_waveform_request(start, count)

        @Slot(int)
        def navigateBrowser(self, step: int) -> None:
            direction = "next" if step > 0 else "previous"
            adapter.navigate_browser(direction, browser_has_focus=True)
            self._refresh()

        @Slot()
        def toggleHarmonicMatch(self) -> None:
            adapter.toggle_harmonic_match()
            self._refresh()

    return QmlInteractionBridge()


def _qml_library_interaction_bridge(
    library_model,
    *,
    on_selection: Callable[[], None] | None = None,
    on_add_source: Callable[[str], bool] | None = None,
    on_prepare_remove: Callable[[int], object | None] | None = None,
    on_confirm_remove: Callable[[int], bool] | None = None,
):
    """Expose tree intent and source actions without owning domain logic."""
    from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot

    class QmlLibraryInteractionBridge(QObject):
        state_changed = Signal()
        removalRequested = Signal()

        def __init__(self) -> None:
            super().__init__()
            self._removal_folder_id: int | None = None
            self._removal_path = ""
            self._removal_availability = ""
            self._removal_cached_sample_count = 0

        @Property(str, notify=state_changed)
        def selectedLibraryNodeId(self) -> str:
            return library_model.state.selected_node_id or ""

        @Property(bool, notify=state_changed)
        def canRemoveSelectedSource(self) -> bool:
            node = library_model.state.node(library_model.state.selected_node_id or "")
            return bool(
                node is not None
                and node.kind is LibraryNodeKind.REGISTERED_ROOT
                and node.folder_id is not None
            )

        @Property(str, notify=state_changed)
        def removalPath(self) -> str:
            return self._removal_path

        @Property(str, notify=state_changed)
        def removalAvailability(self) -> str:
            return self._removal_availability

        @Property(int, notify=state_changed)
        def removalCachedSampleCount(self) -> int:
            return self._removal_cached_sample_count

        @Slot(str)
        def selectLibraryNode(self, node_id: str) -> None:
            if library_model.selectNode(node_id):
                if on_selection is not None:
                    on_selection()
                self.state_changed.emit()

        @Slot(str)
        def retryLibraryNode(self, node_id: str) -> None:
            if library_model.retryNode(node_id):
                self.state_changed.emit()

        @Slot(str)
        def registerSourceUrl(self, url: str) -> None:
            candidate = QUrl(url)
            path = candidate.toLocalFile() if candidate.isLocalFile() else url
            if on_add_source is not None and on_add_source(path):
                self.state_changed.emit()

        @Slot()
        def prepareRemoveSource(self) -> None:
            node = library_model.state.node(library_model.state.selected_node_id or "")
            if (
                node is None
                or node.kind is not LibraryNodeKind.REGISTERED_ROOT
                or node.folder_id is None
                or on_prepare_remove is None
            ):
                return
            preview = on_prepare_remove(node.folder_id)
            if preview is None:
                return
            self._removal_folder_id = node.folder_id
            self._removal_path = str(preview.path)
            self._removal_availability = str(preview.availability)
            self._removal_cached_sample_count = int(preview.cached_sample_count)
            self.state_changed.emit()
            self.removalRequested.emit()

        @Slot()
        def confirmRemoveSource(self) -> None:
            folder_id = self._removal_folder_id
            if folder_id is None or on_confirm_remove is None:
                return
            if on_confirm_remove(folder_id):
                self._clear_removal()
                self.state_changed.emit()

        @Slot()
        def cancelRemoveSource(self) -> None:
            self._clear_removal()
            self.state_changed.emit()

        def _clear_removal(self) -> None:
            self._removal_folder_id = None
            self._removal_path = ""
            self._removal_availability = ""
            self._removal_cached_sample_count = 0

    return QmlLibraryInteractionBridge()

def _qml_engine(
    view_model: Screen1QmlViewModel,
    *,
    interaction_adapter: Screen1QmlInteractionAdapter | None = None,
    runtime_composition: Screen1QmlRuntimeComposition | None = None,
):
    QUrl, QGuiApplication, QQmlApplicationEngine = _load_qt_modules()
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlApplicationEngine()
    preview_player = None
    if interaction_adapter is None:
        from .workbench_controller import get_preview_start_ms
        from .workbench_preview import WorkbenchPreviewPlayer

        preview_player = WorkbenchPreviewPlayer()
        preview_db_path = (
            runtime_composition.library_db_path
            if runtime_composition is not None
            else workbench_library_db_path()
        )

        def preview_row(
            row: WorkbenchRow, *, start_ms: int | None = None
        ) -> object:
            if start_ms is None:
                start_ms = get_preview_start_ms(
                    row.path, library_db_path=preview_db_path
                )
            return preview_player.play(row.path, start_ms=start_ms)

        live_kit = LiveKitPresenter()
        adapter = Screen1QmlInteractionAdapter(
            view_model=view_model,
            harmony_controller=HarmonicMatchLibraryController(),
            on_preview_requested=preview_row,
            on_preview_stopped=preview_player.stop,
            live_kit=live_kit,
        )
        view_model.live_kit_groups = live_kit.groups
    else:
        adapter = interaction_adapter
        live_kit = getattr(interaction_adapter, "_live_kit", None)
    library_model = create_qt_library_tree_model(view_model.library_tree)

    def refresh_screen_model() -> None:
        screen_model.refresh()

    def refresh_browser_rows() -> None:
        screen_model.refresh_browser_rows()

    def refresh_browser_scope() -> None:
        screen_model.refresh_browser_scope()

    waveform_cache = BoundedLazyWaveformCache(
        capacity=48,
        loader=lambda path: compute_waveform_envelope(path, max_points=96),
    )
    waveform_loader = BoundedBackgroundWaveformLoader(
        cache=waveform_cache,
        loader=lambda path: compute_waveform_envelope(path, max_points=96),
        max_pending=14,
    )

    def request_waveforms(start: int, count: int) -> None:
        if count <= 0:
            return
        first = max(0, start)
        last = min(len(view_model.browser_rows), first + count)
        for row in view_model.browser_rows[first:last]:
            if row.waveform_envelope:
                continue
            waveform_loader.schedule(str(row.source_row.path))

    def request_harmony_waveforms(start: int, count: int) -> None:
        if count <= 0:
            return
        first = max(0, start)
        last = min(len(view_model.harmony_rows), first + count)
        for row in view_model.harmony_rows[first:last]:
            if row.waveform_envelope:
                continue
            waveform_loader.schedule(str(row.source_row.path))

    def drain_waveforms() -> None:
        if waveform_loader.drain_results() == 0:
            return
        changed = False
        for row in view_model.browser_rows:
            cached = waveform_cache.get(str(row.source_row.path))
            if cached is not None and cached.state == "ready":
                changed = view_model.set_browser_waveform(
                    str(row.source_row.path), cached.envelope
                ) or changed
        if changed:
            refresh_browser_rows()

    analysis_coordinator = None

    def apply_analysis_state(state: AnalysisUiState) -> None:
        view_model.set_analysis_state(state)
        refresh_screen_model()

    def dispatch_library_selection() -> None:
        if runtime_composition is None:
            return
        intent = library_model.state.selection_intent
        if intent is None:
            runtime_composition.clear_no_scope(
                "Library-Auswahl konnte nicht aufgelöst werden."
            )
        else:
            state = runtime_composition.dispatch_selection(intent)
            if analysis_coordinator is not None and state.error is None:
                try:
                    refresh_target = runtime_composition.refresh_target(intent.scope)
                except Exception:
                    refresh_target = None
                if refresh_target is not None:
                    analysis_coordinator.start(
                        refresh_target.folder_id,
                        str(refresh_target.normalized_path),
                    )
        _sync_runtime_browser_state(view_model, adapter, runtime_composition)
        request_waveforms(0, 20)
        refresh_browser_scope()
        bridge.refreshState()

    def finish_analysis(folder_id: int, _result: object) -> None:
        previous_selected = (
            runtime_composition.selected_node_id
            if runtime_composition is not None
            else None
        )
        library_model.replaceBranch("container:sample-sources")
        target_node_id = (
            runtime_composition.post_analysis_node_id(
                folder_id,
                previous_selected=previous_selected,
            )
            if runtime_composition is not None
            else f"root:{folder_id}"
        )
        if (
            target_node_id.startswith(f"folder:{folder_id}:")
            and library_model.state.node(f"root:{folder_id}") is not None
        ):
            library_model.state.fetch_children(f"root:{folder_id}")
        if library_model.selectNode(target_node_id):
            dispatch_library_selection()
        else:
            refresh_screen_model()

    def finish_remove(folder_id: int) -> None:
        if runtime_composition is None:
            return
        if runtime_composition.remove_source(folder_id):
            library_model.replaceBranch("container:sample-sources")
            library_model.clearSelection()
            dispatch_library_selection()

    def register_source(path: str) -> bool:
        if runtime_composition is None:
            return False
        registration = runtime_composition.register_source_for_analysis(Path(path))
        if registration is not None:
            library_model.replaceBranch("container:sample-sources")
            if library_model.state.selected_node_id is None:
                library_model.selectNode(f"root:{registration.folder_id}")
            dispatch_library_selection()
            if analysis_coordinator is not None:
                analysis_coordinator.start(
                    registration.folder_id,
                    str(registration.normalized_path),
                )
        else:
            _sync_runtime_browser_state(view_model, adapter, runtime_composition)
            refresh_browser_scope()
            bridge.refreshState()
        return registration is not None

    def prepare_remove(folder_id: int) -> object | None:
        if runtime_composition is None:
            return None
        return runtime_composition.preview_remove_source(folder_id)

    def confirm_remove(folder_id: int) -> bool:
        if runtime_composition is None:
            return False
        if analysis_coordinator is not None:
            return analysis_coordinator.remove(folder_id)
        return runtime_composition.remove_source(folder_id)

    def cancel_analysis() -> None:
        if analysis_coordinator is None:
            return
        if view_model.analysis_folder_id is not None:
            analysis_coordinator.cancel(view_model.analysis_folder_id)

    if runtime_composition is not None:
        analysis_coordinator = create_qt_analysis_coordinator(
            library_db_path=runtime_composition.library_db_path,
            on_state=apply_analysis_state,
            on_complete=finish_analysis,
            on_remove=finish_remove,
        )

    screen_model = _qml_screen_data_bridge(
        view_model,
        on_cancel_analysis=cancel_analysis,
    )
    bridge = _qml_interaction_bridge(
        adapter,
        on_state_changed=refresh_screen_model,
        on_waveform_request=request_waveforms,
        on_harmony_waveform_request=request_harmony_waveforms,
    )
    library_bridge = _qml_library_interaction_bridge(
        library_model,
        on_selection=dispatch_library_selection,
        on_add_source=register_source,
        on_prepare_remove=prepare_remove,
        on_confirm_remove=confirm_remove,
    )
    if runtime_composition is not None:
        library_model.selection_invalidated.connect(dispatch_library_selection)
    engine.rootContext().setContextProperty("screenModel", screen_model)
    engine.rootContext().setContextProperty("interactionModel", bridge)
    engine.rootContext().setContextProperty("libraryTreeModel", library_model)
    engine.rootContext().setContextProperty("libraryInteraction", library_bridge)
    if analysis_coordinator is not None:
        engine.rootContext().setContextProperty(
            "_screen1AnalysisCoordinator",
            analysis_coordinator,
        )
    engine.loadData(QML_SOURCE.encode("utf-8"), QUrl("qrc:/screen1.qml"))
    if not engine.rootObjects():
        raise RuntimeError("Qt Quick Screen-1 Renderer konnte keine QML-Oberfläche laden.")
    # Keep both Python objects alive for the complete Qt engine lifetime.
    engine._screen1_interaction_adapter = adapter
    engine._screen1_interaction_bridge = bridge
    engine._screen1_library_model = library_model
    engine._screen1_library_bridge = library_bridge
    engine._screen1_screen_model = screen_model
    engine._screen1_live_kit = live_kit
    engine._screen1_runtime_composition = runtime_composition
    engine._screen1_analysis_coordinator = analysis_coordinator
    engine._screen1_waveform_cache = waveform_cache
    engine._screen1_waveform_loader = waveform_loader
    engine._screen1_waveform_timer = None
    if preview_player is not None:
        engine._screen1_preview_player = preview_player
    from PySide6.QtCore import QTimer

    waveform_timer = QTimer()
    waveform_timer.setInterval(50)
    waveform_timer.timeout.connect(drain_waveforms)
    waveform_timer.start()
    engine._screen1_waveform_timer = waveform_timer
    request_waveforms(0, 20)
    app.aboutToQuit.connect(waveform_loader.close)
    if analysis_coordinator is not None:
        app.aboutToQuit.connect(analysis_coordinator.shutdown)
    return app, engine, engine.rootObjects()[0]


def _settle_qml_frame(app: object) -> None:
    """Wait for one rendered Qt Quick frame before a native client capture."""
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(200, loop.quit)
    loop.exec()
    app.processEvents()


def run_qml_screen1(*, state_id: str = "screen1-default-3panel") -> int:
    """Open the optional production Screen-1 renderer without changing Tk defaults."""
    composition = Screen1QmlRuntimeComposition(
        library_db_path=workbench_library_db_path(),
    )
    view_model = Screen1QmlViewModel(
        state_id=state_id,
        library_labels=(),
        browser_rows=(),
        selected_browser_index=-1,
        harmony_rows=(),
        live_kit_groups=_empty_live_kit_groups(),
        library_tree=composition.library_tree,
    )
    app, _engine, _window = _qml_engine(
        view_model,
        runtime_composition=composition,
    )
    try:
        return app.exec()
    finally:
        root_context = getattr(_engine, "rootContext", None)
        if callable(root_context):
            coordinator = root_context().contextProperty(
                "_screen1AnalysisCoordinator"
            )
        else:
            coordinator = getattr(_engine, "_screen1_analysis_coordinator", None)
        if coordinator is not None:
            coordinator.close()


__all__ = [
    "LiveKitPresenter",
    "QML_SOURCE",
    "QmlBrowserRow",
    "QmlLiveKitGroup",
    "QmlLiveKitSlot",
    "SCREEN1_QML_STATE_IDS",
    "Screen1QmlInteractionAdapter",
    "Screen1QmlViewModel",
    "qml_runtime_available",
    "run_qml_screen1",
]
