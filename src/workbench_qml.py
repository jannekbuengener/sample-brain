"""Optional production Qt Quick Workbench shell (Screen 1 + Screen 2).

This module owns only renderer-facing state, interaction routing, and Qt engine
startup. Musical truth for Screen 2 stays in ``ChannelRackController`` /
``channel_rack``. Fixture, evidence, and synthetic probe orchestration
deliberately live in :mod:`src.workbench_qml_spike`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import inspect
import math
import os
import sys
from pathlib import Path
from typing import Callable, Mapping

from .workbench_controller import WorkbenchRow, filter_workbench_rows
from .workbench_browser_rows import (
    BoundedBackgroundWaveformLoader,
    BoundedLazyWaveformCache,
)
from .workbench_harmony import (
    HarmonicMatchLibraryController,
    HarmonySuggestion,
    harmonic_match_key_for_row,
)
from .workbench_live_kit import LiveKitPresentationState, LiveKitState
from .workbench_live_kit_export import LiveKitExportResult, export_live_kit
from .workbench_library import (
    list_favorite_sample_paths,
    toggle_sample_favorite,
    workbench_library_db_path,
)
from .workbench_library_navigation import LibraryNodeKind, LibraryScopeKind
from .workbench_qml_analysis import AnalysisUiState, create_qt_analysis_coordinator
from .workbench_qml_library import (
    WorkbenchLibraryTreeState,
    create_qt_library_tree_model,
)
from .workbench_qml_runtime import Screen1BrowserState, Screen1QmlRuntimeComposition
from .workbench_qml_elastic import create_elastic_layout_bridge
from .workbench_qml_startup import (
    WorkspaceMode,
    load_startup_preset,
    resolve_launch_workspace,
)
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
    is_favorite: bool = False


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


def _path_in_favorites(path: str, favorites: set[str] | frozenset[str]) -> bool:
    if path in favorites:
        return True
    try:
        resolved = str(Path(path).expanduser().resolve())
    except OSError:
        return False
    return resolved in favorites


def _favorite_path_set(*, db_path: Path | None) -> set[str]:
    try:
        return set(list_favorite_sample_paths(db_path=db_path))
    except OSError:
        return set()


def _waveform_envelope(row: WorkbenchRow) -> tuple[float, ...]:
    raw = _row_details(row).get("waveform_envelope")
    if raw is None or isinstance(raw, (str, bytes)):
        return ()
    try:
        return tuple(max(0.0, min(1.0, float(value))) for value in raw)
    except (TypeError, ValueError):
        return ()


def _qml_row(row: WorkbenchRow, *, is_favorite: bool = False) -> QmlBrowserRow:
    return QmlBrowserRow(
        source_row=row,
        display_name=row.display_name,
        sample_type=row.pred_type or "—",
        bpm="—" if row.bpm is None else f"{row.bpm:g}",
        key=row.key or "—",
        duration=_duration(row),
        waveform_envelope=_waveform_envelope(row),
        is_favorite=bool(is_favorite),
    )


def format_selected_sample_context_hint(row: QmlBrowserRow | None) -> str:
    """Compact footer selection context from existing Browser row projection.

    Single formatter authority for ``Name · BPM · Key · Type``. Reuses projected
    missing-state tokens (``—``). Empty when there is no selected row.
    """
    if row is None:
        return ""
    return f"{row.display_name} · {row.bpm} · {row.key} · {row.sample_type}"


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
        self._browser_rows_all = browser_rows
        self._browser_search_query = ""
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
        self.analysis_token: int | None = None
        self._brand_expected_token: int | None = None
        self._brand_motion_mode = "on"
        # #693 Clean Start materialization (progressive disclosure)
        self.has_active_source = False
        self.calm_canvas_visible = True
        self.browser_materialized = False
        self.live_kit_materialized = False
        # #725 No-Source presentation only (collapsed by default).
        self.library_revealed = False

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

    @property
    def selected_sample_context_hint(self) -> str:
        """Footer SELECTION fallback from existing browser selection index."""
        index = self.selected_browser_index
        if not 0 <= index < len(self.browser_rows):
            return ""
        return format_selected_sample_context_hint(self.browser_rows[index])

    def set_browser_state(
        self,
        *,
        rows: tuple[WorkbenchRow, ...],
        selected_index: int,
        browser_context: str,
        error: str | None,
        favorite_paths: set[str] | frozenset[str] | None = None,
    ) -> None:
        favorites = favorite_paths or set()
        self._browser_rows_all = tuple(
            _qml_row(
                row,
                is_favorite=_path_in_favorites(str(row.path), favorites),
            )
            for row in rows
        )
        preferred_path: str | None = None
        if 0 <= selected_index < len(self._browser_rows_all):
            preferred_path = str(self._browser_rows_all[selected_index].source_row.path)
        self.browser_context = browser_context
        self.browser_error = error
        self._republish_browser_rows(preferred_path=preferred_path)

    def set_browser_favorite(self, path: str, *, is_favorite: bool) -> bool:
        """Project domain favorite state onto matching Browser rows."""
        changed = False
        updated_all: list[QmlBrowserRow] = []
        for row in self._browser_rows_all:
            if str(row.source_row.path) == path and row.is_favorite != is_favorite:
                row = replace(row, is_favorite=bool(is_favorite))
                changed = True
            updated_all.append(row)
        if not changed:
            return False
        preferred_path: str | None = None
        if 0 <= self.selected_browser_index < len(self.browser_rows):
            preferred_path = str(
                self.browser_rows[self.selected_browser_index].source_row.path
            )
        self._browser_rows_all = tuple(updated_all)
        self._republish_browser_rows(preferred_path=preferred_path)
        return True

    def set_browser_search_query(self, query: str) -> None:
        """Project text search into the visible Sample Browser (#758).

        Uses the existing ``filter_workbench_rows`` contract. Empty query restores
        the full current-scope list. Does not invent structured or semantic search.
        """
        self._browser_search_query = str(query or "")
        preferred_path: str | None = None
        if 0 <= self.selected_browser_index < len(self.browser_rows):
            preferred_path = str(self.browser_rows[self.selected_browser_index].source_row.path)
        self._republish_browser_rows(preferred_path=preferred_path)

    def _republish_browser_rows(self, *, preferred_path: str | None) -> None:
        source_rows = tuple(row.source_row for row in self._browser_rows_all)
        filtered = filter_workbench_rows(list(source_rows), self._browser_search_query)
        by_path = {str(row.source_row.path): row for row in self._browser_rows_all}
        self.browser_rows = tuple(
            by_path[str(row.path)] for row in filtered if str(row.path) in by_path
        )
        if preferred_path is None:
            self.selected_browser_index = -1
            return
        for index, row in enumerate(self.browser_rows):
            if str(row.source_row.path) == preferred_path:
                self.selected_browser_index = index
                return
        self.selected_browser_index = -1

    def set_workspace_materialization(
        self,
        *,
        has_active_source: bool,
        calm_canvas_visible: bool,
        browser_materialized: bool,
        live_kit_materialized: bool,
    ) -> None:
        self.has_active_source = bool(has_active_source)
        self.calm_canvas_visible = bool(calm_canvas_visible)
        self.browser_materialized = bool(browser_materialized)
        self.live_kit_materialized = bool(live_kit_materialized)

    def set_library_revealed(self, revealed: bool) -> None:
        """Set Library panel disclosure (#725). Transient; not ratio authority."""
        self.library_revealed = bool(revealed)

    def reveal_library(self) -> bool:
        """Reveal Library without Source selection / audition / harmony side effects."""
        if self.library_revealed:
            return False
        self.library_revealed = True
        return True

    def set_browser_waveform(self, path: str, envelope: tuple[float, ...]) -> bool:
        """Apply one cached waveform without changing browser selection."""
        changed = False
        updated_all: list[QmlBrowserRow] = []
        for row in self._browser_rows_all:
            if str(row.source_row.path) == path and row.waveform_envelope != envelope:
                row = replace(row, waveform_envelope=envelope)
                changed = True
            updated_all.append(row)
        if changed:
            preferred_path: str | None = None
            if 0 <= self.selected_browser_index < len(self.browser_rows):
                preferred_path = str(
                    self.browser_rows[self.selected_browser_index].source_row.path
                )
            self._browser_rows_all = tuple(updated_all)
            self._republish_browser_rows(preferred_path=preferred_path)
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
        self.analysis_token = state.token
        # Live published states define the expected job token for brand projection.
        self._brand_expected_token = state.token

    def set_brand_motion_mode(self, mode: str) -> str:
        from .workbench_display_preferences import normalize_motion_mode

        self._brand_motion_mode = normalize_motion_mode(mode)
        return self._brand_motion_mode

    def brand_runtime_context(self) -> dict[str, object]:
        """Project analysis evidence into QML brand/motion presentation fields."""
        from .workbench_brand_motion import brand_runtime_payload

        return brand_runtime_payload(
            AnalysisUiState(
                folder_id=self.analysis_folder_id,
                phase=self.analysis_status,  # type: ignore[arg-type]
                current=self.analysis_current,
                total=self.analysis_total,
                display_name=self.analysis_source,
                token=self.analysis_token,
                error=self.analysis_error,
            ),
            self._brand_motion_mode,
            expected_token=self._brand_expected_token,
        )

    def qml_context(self) -> dict[str, object]:
        brand = self.brand_runtime_context()
        return {
            "panelCount": self.panel_count,
            "selectedBrowserIndex": self.selected_browser_index,
            "selectedSampleContextHint": self.selected_sample_context_hint,
            "browserContext": self.browser_context,
            "errorMessage": self.browser_error or "",
            "analysisStatus": self.analysis_status,
            "analysisCurrent": self.analysis_current,
            "analysisTotal": self.analysis_total,
            "analysisSource": self.analysis_source,
            "analysisError": self.analysis_error or "",
            "brandBrainUrl": brand["brainUrl"],
            "brandProgressKind": brand["progressKind"],
            "brandProgressRatio": brand["progressRatio"],
            "brandSampleName": brand["sampleName"],
            "brandMotionMode": brand["motionMode"],
            "brandMotionActive": brand["motionActive"],
            "brandReducedMotion": brand["reducedMotion"],
            "brandStaticFallback": brand["staticFallback"],
            "brandStale": brand["stale"],
            "brandPhase": brand["phase"],
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
                    "favorite": bool(row.is_favorite),
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
    favorites = _favorite_path_set(db_path=adapter.library_db_path)
    view_model.set_browser_state(
        rows=state.rows,
        selected_index=state.selected_index,
        browser_context=state.browser_context,
        error=state.error,
        favorite_paths=favorites,
    )
    view_model.set_workspace_materialization(
        has_active_source=runtime_composition.has_active_source,
        calm_canvas_visible=not runtime_composition.has_active_source,
        browser_materialized=runtime_composition.browser_materialized,
        live_kit_materialized=runtime_composition.live_kit_materialized,
    )
    # #762: Active Source materialises Library with Browser (no Browser-only half).
    if runtime_composition.has_active_source:
        view_model.set_library_revealed(True)
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
        selectedSampleContextHintChanged = Signal()
        browserContextChanged = Signal()
        errorMessageChanged = Signal()
        analysisStatusChanged = Signal()
        analysisProgressChanged = Signal()
        analysisSourceChanged = Signal()
        analysisErrorChanged = Signal()
        brandMotionChanged = Signal()
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

        @Property(str, notify=selectedSampleContextHintChanged)
        def selectedSampleContextHint(self) -> str:
            return view_model.selected_sample_context_hint

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

        def _brand(self) -> dict[str, object]:
            return view_model.brand_runtime_context()

        @Property(str, notify=brandMotionChanged)
        def brandBrainUrl(self) -> str:
            return str(self._brand()["brainUrl"])

        @Property(str, notify=brandMotionChanged)
        def brandProgressKind(self) -> str:
            return str(self._brand()["progressKind"])

        @Property(float, notify=brandMotionChanged)
        def brandProgressRatio(self) -> float:
            return float(self._brand()["progressRatio"])

        @Property(str, notify=brandMotionChanged)
        def brandSampleName(self) -> str:
            return str(self._brand()["sampleName"])

        @Property(str, notify=brandMotionChanged)
        def brandMotionMode(self) -> str:
            return str(self._brand()["motionMode"])

        @Property(bool, notify=brandMotionChanged)
        def brandMotionActive(self) -> bool:
            return bool(self._brand()["motionActive"])

        @Property(bool, notify=brandMotionChanged)
        def brandReducedMotion(self) -> bool:
            return bool(self._brand()["reducedMotion"])

        @Property(bool, notify=brandMotionChanged)
        def brandStaticFallback(self) -> bool:
            return bool(self._brand()["staticFallback"])

        @Property(bool, notify=brandMotionChanged)
        def brandStale(self) -> bool:
            return bool(self._brand()["stale"])

        @Property(str, notify=brandMotionChanged)
        def brandPhase(self) -> str:
            return str(self._brand()["phase"])

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
            self.selectedSampleContextHintChanged.emit()
            self.browserContextChanged.emit()
            self.errorMessageChanged.emit()
            self.analysisStatusChanged.emit()
            self.analysisProgressChanged.emit()
            self.analysisSourceChanged.emit()
            self.analysisErrorChanged.emit()
            self.brandMotionChanged.emit()
            self.harmonyRowsChanged.emit()
            self.harmonyAnchorChanged.emit()
            self.harmonyStatusChanged.emit()
            self.liveKitGroupsChanged.emit()
            self.panelCountChanged.emit()

        @Slot()
        def refresh_browser_rows(self) -> None:
            self.browserRowsChanged.emit()
            self.selectedSampleContextHintChanged.emit()

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

    _HARMONIC_CLOSE_SELECTION_UNSET: object = object()

    def __init__(
        self,
        *,
        view_model: Screen1QmlViewModel,
        harmony_controller: HarmonicMatchLibraryController | None = None,
        on_preview_requested: Callable[[WorkbenchRow], object] | None = None,
        on_preview_stopped: Callable[[], object] | None = None,
        on_preview_released: Callable[[], object] | None = None,
        on_preview_snapshot: Callable[[], object] | None = None,
        on_add_to_kit_requested: Callable[[WorkbenchRow], object] | None = None,
        on_context_harmonic_match_requested: Callable[[WorkbenchRow], object] | None = None,
        live_kit: LiveKitPresenter | None = None,
        library_db_path: Path | None = None,
    ) -> None:
        self.view_model = view_model
        self.harmony_controller = harmony_controller
        self.harmonic_match_open = view_model.panel_count == 4
        # #845 session-transient presentation only — not domain / disclosure state.
        self.browser_collapsed = False
        self.live_kit_collapsed = False
        self._on_preview_requested = on_preview_requested
        self._preview_request_accepts_start_ms = _callback_accepts_start_ms(
            on_preview_requested
        )
        self._on_preview_stopped = on_preview_stopped
        self._on_preview_released = on_preview_released
        self._on_preview_snapshot = on_preview_snapshot
        self._on_add_to_kit_requested = on_add_to_kit_requested
        self._on_context_harmonic_match_requested = on_context_harmonic_match_requested
        self._on_sample_context_closed: Callable[[], object] | None = None
        self._live_kit = live_kit
        self._library_db_path = library_db_path
        self._pending_live_kit_row: WorkbenchRow | None = None
        self._sample_context_target: WorkbenchRow | None = None
        self._preview_active = False
        self._auditioning_live_kit_slot: tuple[str, str] | None = None
        self._live_kit_export_status = ""
        self._live_kit_export_ok: bool | None = None
        self._harmonic_match_context_fingerprint: tuple[object, ...] | None = None
        self._harmonic_match_selected_index = 0
        self._harmonic_match_scroll_y = 0.0
        self._harmonic_match_browser_scope: object | None = None
        self._harmonic_match_session_scope: object | None = None
        # Stable selected-row path recorded on #845 non-destructive Matches close
        # so reopen can restore a context-bound anchor unless selection identity changed.
        # Sentinel distinguishes "never closed" from "closed with no Browser selection"
        # (selected_index=-1 → path None), which is a valid unchanged identity (#843).
        self._harmonic_match_selection_path_at_close: object | None = (
            self._HARMONIC_CLOSE_SELECTION_UNSET
        )
        self._waveform_motion_mode = "on"
        self._gesture_rack_apply_enabled = False
        self._preview_playback_cache: object | None = None
        # Optional #742 disclosure owner (set by production engine wiring).
        self._runtime_composition: Screen1QmlRuntimeComposition | None = None
        self._install_browser_projection_invalidation()

    def _install_browser_projection_invalidation(self) -> None:
        """Clear context target before any visible Browser re-projection (#839)."""
        vm = self.view_model
        original_set_state = vm.set_browser_state
        original_set_search = vm.set_browser_search_query

        def set_browser_state(*args, **kwargs):
            self.close_sample_context()
            return original_set_state(*args, **kwargs)

        def set_browser_search_query(*args, **kwargs):
            self.close_sample_context()
            return original_set_search(*args, **kwargs)

        vm.set_browser_state = set_browser_state  # type: ignore[method-assign]
        vm.set_browser_search_query = set_browser_search_query  # type: ignore[method-assign]

    @property
    def sample_context_target(self) -> WorkbenchRow | None:
        return self._sample_context_target

    def open_sample_context(self, index: int) -> WorkbenchRow:
        """Resolve visible row index once into a stable context target (#839)."""
        if not 0 <= index < len(self.view_model.browser_rows):
            raise IndexError("Browser-Zeilenindex außerhalb des sichtbaren Modells.")
        row = self.view_model.browser_rows[index].source_row
        self._sample_context_target = row
        return row

    def close_sample_context(self) -> None:
        """Clear session-transient sample context target (#839)."""
        had_target = self._sample_context_target is not None
        self._sample_context_target = None
        if had_target and self._on_sample_context_closed is not None:
            self._on_sample_context_closed()

    def _request_add_to_kit_row(self, row: WorkbenchRow) -> WorkbenchRow:
        """Shared Add-to-Kit intent seam for index and context routes (#839)."""
        self._pending_live_kit_row = row
        self._reveal_live_kit_pane()
        if self._on_add_to_kit_requested is not None:
            self._on_add_to_kit_requested(row)
        return row

    def request_context_add_to_kit(self) -> WorkbenchRow:
        """Dispatch Add-to-Kit for the stored context target (not a stale index)."""
        target = self._sample_context_target
        if target is None:
            raise ValueError("No sample context target")
        result = self._request_add_to_kit_row(target)
        self.close_sample_context()
        return result

    def request_context_harmonic_matches(self) -> WorkbenchRow:
        """Open/retarget Harmonic Matches for the stored context target (#843).

        Production default (no callback): ``open_harmonic_matches_for_row``.
        An explicit callback remains an injection/override seam for harnesses.
        Never routes through ``toggle_harmonic_match``.
        """
        target = self._sample_context_target
        if target is None:
            raise ValueError("No sample context target")
        if self._on_context_harmonic_match_requested is not None:
            self._on_context_harmonic_match_requested(target)
        else:
            self.open_harmonic_matches_for_row(target)
        self.close_sample_context()
        return target

    def _reveal_live_kit_pane(self) -> None:
        """UI disclosure only — does not mutate Live-Kit domain assignments."""
        composition = self._runtime_composition
        if composition is None:
            return
        composition.reveal_live_kit()
        self.view_model.set_workspace_materialization(
            has_active_source=self.view_model.has_active_source,
            calm_canvas_visible=self.view_model.calm_canvas_visible,
            browser_materialized=self.view_model.browser_materialized,
            live_kit_materialized=composition.live_kit_materialized,
        )

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
    def waveform_motion_mode(self) -> str:
        return self._waveform_motion_mode

    def set_waveform_motion_mode(self, mode: str) -> str:
        """Presentation-only motion mode seam (On/Reduced/Off)."""
        from .workbench_display_preferences import normalize_motion_mode

        normalized = normalize_motion_mode(mode)
        self._waveform_motion_mode = normalized
        # Brand/analysis motion consumes the same display preference.
        if hasattr(self.view_model, "set_brand_motion_mode"):
            self.view_model.set_brand_motion_mode(normalized)
        return self._waveform_motion_mode

    @property
    def gesture_rack_apply_enabled(self) -> bool:
        """Functional #910 toggle — configuration only, not musical state."""
        return bool(self._gesture_rack_apply_enabled)

    def load_feature_settings(
        self,
        *,
        state_dir: Path | None = None,
        env: Mapping[str, str] | None = None,
    ):
        """Load canonical functional feature settings into the adapter.

        Returns the loaded ``WorkbenchFeatureSettings`` snapshot (not a
        success/flag boolean).
        """
        from .workbench_feature_settings import (
            WorkbenchFeatureSettings,
            load_workbench_feature_settings,
        )

        loaded = load_workbench_feature_settings(state_dir=state_dir, env=env)
        if not isinstance(loaded, WorkbenchFeatureSettings):
            loaded = WorkbenchFeatureSettings()
        self._gesture_rack_apply_enabled = bool(loaded.gesture_rack_apply_enabled)
        return loaded

    def set_gesture_rack_apply_enabled(
        self,
        enabled: bool,
        *,
        state_dir: Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> bool:
        """Persist gesture→Rack apply toggle via WorkbenchFeatureSettings only."""
        from .workbench_feature_settings import (
            WorkbenchFeatureSettings,
            save_workbench_feature_settings,
        )

        value = bool(enabled)
        if save_workbench_feature_settings(
            WorkbenchFeatureSettings(gesture_rack_apply_enabled=value),
            state_dir=state_dir,
            env=env,
        ):
            self._gesture_rack_apply_enabled = value
        else:
            self.load_feature_settings(state_dir=state_dir, env=env)
        return self._gesture_rack_apply_enabled

    def reset_layout_preferences(self) -> None:
        from .workbench_display_preferences import reset_layout

        reset_layout()

    def save_workspace_preset_action(self) -> None:
        from .workbench_display_preferences import save_workspace_preset
        from .workbench_layout_solver import CANONICAL_DEFAULT_RATIOS, load_layout_preferences

        loaded = load_layout_preferences()
        ratios = dict(loaded.ratios) if loaded.ratios else dict(CANONICAL_DEFAULT_RATIOS)
        save_workspace_preset(
            {
                "version": 1,
                "panel_ratios": ratios,
                "panel_visibility": {
                    "library": True,
                    "browser": True,
                    "harmony": bool(self.harmonic_match_open),
                    "livekit": True,
                },
                "density_mode": "compact",
                "motion_mode": self._waveform_motion_mode,
                "startup_source_node_id": None,
            }
        )

    def set_workspace_preset_as_startup(self) -> None:
        from .workbench_display_preferences import set_as_startup

        set_as_startup()

    def return_to_clean_start_action(self) -> None:
        """Clear transient workspace context; keep Sources/presets/display prefs."""
        from .workbench_display_preferences import return_to_clean_start

        self.close_sample_context()
        self.stop_preview()
        if self.harmonic_match_open:
            self.harmonic_match_open = False
        # #845 presentation flags are session-transient; never survive Clean Start.
        self.browser_collapsed = False
        self.live_kit_collapsed = False
        if self._runtime_composition is not None:
            self._runtime_composition.clear_no_scope()
        self.view_model.set_browser_state(
            rows=(),
            selected_index=-1,
            browser_context="No library selected",
            error=None,
        )
        self.view_model.set_workspace_materialization(
            has_active_source=False,
            calm_canvas_visible=True,
            browser_materialized=False,
            live_kit_materialized=False,
        )
        self.view_model.set_library_revealed(False)
        self.view_model.harmony_rows = ()
        self.view_model.harmony_anchor = ""
        self.view_model.harmony_status = "Harmonic Match ist ausgeschaltet."
        self._harmonic_match_selected_index = 0
        self._harmonic_match_scroll_y = 0.0
        self._auditioning_live_kit_slot = None
        self._pending_live_kit_row = None
        return_to_clean_start()

    def preview_playback_snapshot(self):
        """Return authoritative preview telemetry for playhead presentation."""
        from .workbench_transport_preview import PreviewPlaybackSnapshot

        if self._waveform_motion_mode == "off" or not self._preview_active:
            self._preview_playback_cache = PreviewPlaybackSnapshot.idle()
            return self._preview_playback_cache
        if self._on_preview_snapshot is None:
            self._preview_playback_cache = PreviewPlaybackSnapshot.idle()
            return self._preview_playback_cache
        snap = self._on_preview_snapshot()
        if snap is None:
            self._preview_playback_cache = PreviewPlaybackSnapshot.idle()
        else:
            self._preview_playback_cache = snap
        return self._preview_playback_cache

    def refresh_preview_playback(self):
        """Re-read authoritative preview telemetry (presentation driver only)."""
        return self.preview_playback_snapshot()

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
        self.preview_playback_snapshot()
        return row

    def stop_preview(self) -> bool:
        """Stop only an active preview and leave selection untouched."""
        if not self._preview_active:
            return False
        self._stop_preview_authoritative()
        self._clear_live_kit_audition_projection()
        self.preview_playback_snapshot()
        return True

    def quiet_audition(self) -> None:
        """Authoritative audition quiet for domain audio focus (#807 / #916).

        Always releases the shared preview voice and clears Live Kit audition
        projection, even when the adapter already believes preview is idle.
        Prefer ``on_preview_released`` (voice-only) so focus transfer does not
        tear down the shared session transport while Rack may still own playback.
        Falls back to ``on_preview_stopped`` when no release hook is wired.
        Does not resume later — callers must start a new explicit audition.
        """
        self._preview_active = False
        if self._on_preview_released is not None:
            self._on_preview_released()
        elif self._on_preview_stopped is not None:
            self._on_preview_stopped()
        self._clear_live_kit_audition_projection()
        self.preview_playback_snapshot()

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
            self.preview_playback_snapshot()
            return False
        self._preview_active = True
        self._auditioning_live_kit_slot = (group, slot)
        self.view_model.auditioning_live_kit_slot = self._auditioning_live_kit_slot
        self.preview_playback_snapshot()
        return True

    @property
    def library_db_path(self) -> Path | None:
        return self._library_db_path

    def toggle_favorite(self, index: int) -> bool:
        """Toggle #766 Favorite persistence and project the resulting flag."""
        row = self.view_model.browser_rows[index].source_row
        path = str(row.path)
        result = toggle_sample_favorite(path, db_path=self._library_db_path)
        composition = self._runtime_composition
        if (
            composition is not None
            and composition.browser_state.scope is not None
            and composition.browser_state.scope.kind is LibraryScopeKind.FAVORITES
        ):
            node_id = composition.selected_node_id or "scope:favorites"
            intent = composition.library_tree.select(node_id)
            if intent is not None:
                composition.dispatch_selection(intent)
                _sync_runtime_browser_state(self.view_model, self, composition)
                return result
        self.view_model.set_browser_favorite(path, is_favorite=result)
        # Keep resolved-path projection coherent when row.path is unresolved.
        try:
            resolved = str(Path(path).expanduser().resolve())
        except OSError:
            resolved = path
        if resolved != path:
            self.view_model.set_browser_favorite(resolved, is_favorite=result)
        return result

    def request_add_to_kit(self, index: int) -> WorkbenchRow:
        """Emit an Add-to-Kit intent without assigning the row.

        The row is remembered as the pending Live Kit target; the actual slot
        assignment happens only through :meth:`assign_live_kit_slot`.
        First Add-to-Kit also reveals the Live Kit pane (#742 disclosure).
        """
        row = self.view_model.browser_rows[index].source_row
        return self._request_add_to_kit_row(row)

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

    @property
    def live_kit_export_status(self) -> str:
        return self._live_kit_export_status

    @property
    def live_kit_export_ok(self) -> bool | None:
        return self._live_kit_export_ok

    def export_live_kit(self, destination_parent: Path | str) -> LiveKitExportResult:
        """Export the current Live Kit through the pure Python export service.

        Reads kit state only. Does not mutate assignments, presentation,
        browser selection, preview/audition, harmony, or transport.
        """
        if self._live_kit is None:
            result = LiveKitExportResult(
                ok=False,
                error_code="NO_LIVE_KIT",
                error_message="Live Kit ist nicht verfügbar. Export abgebrochen.",
            )
            self._live_kit_export_ok = False
            self._live_kit_export_status = result.error_message or ""
            return result
        result = export_live_kit(self._live_kit.state, destination_parent)
        self._live_kit_export_ok = result.ok
        if result.ok and result.export_path is not None:
            self._live_kit_export_status = f"Exportiert nach: {result.export_path}"
        else:
            self._live_kit_export_status = result.error_message or "Export fehlgeschlagen."
        return result

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
        return (
            row.path,
            harmonic_match_key_for_row(row),
            cls._harmonic_match_bpm_fingerprint(row.bpm),
            row.display_name,
        )

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

    def sync_visible_state_labels(self) -> bool:
        """Keep Browser/Harmony labels coherent with materialised workspace state.

        Prevents contradictory UI copy such as "No library selected" while the
        Browser is materialised, or "Harmonic Match ist ausgeschaltet." while
        the Harmony pane is open. Returns True when any label changed.
        """
        changed = False
        vm = self.view_model
        if vm.has_active_source and vm.browser_materialized:
            if not str(vm.browser_context or "").strip() or vm.browser_context == (
                "No library selected"
            ):
                if vm.library_labels:
                    vm.browser_context = str(vm.library_labels[0])
                else:
                    vm.browser_context = "Samples"
                changed = True
        if self.harmonic_match_open:
            if vm.harmony_status == "Harmonic Match ist ausgeschaltet.":
                vm.harmony_status = self.effective_harmony_status
                changed = True
        return changed

    def _project_harmonic_match(self, anchor: WorkbenchRow) -> None:
        if self.harmony_controller is None:
            self.view_model.harmony_status = (
                "Harmonic Match ist offen."
                if self.harmonic_match_open
                else "Harmonic Match ist ausgeschaltet."
            )
            return
        self.view_model.harmony_rows = tuple(_qml_harmony_row(item) for item in self.harmony_controller.results)
        anchor_key = harmonic_match_key_for_row(anchor) or "—"
        self.view_model.harmony_anchor = f"Reference: {anchor.display_name} · {anchor_key}"
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
        self.preview_playback_snapshot()
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
        return self._request_add_to_kit_row(row)

    def set_harmonic_match_scroll_y(self, value: float) -> None:
        if not self.harmonic_match_open:
            return
        self._harmonic_match_scroll_y = max(0.0, float(value))

    def _resolve_live_harmony_anchor(self) -> WorkbenchRow | None:
        """Resolve the open Matches session anchor against current Browser rows.

        Prefers the controller's live anchor identity so a context-opened
        Matches pane for B is not silently retargeted to selected A on
        same-scope refresh (#843). Falls back to the selected Browser row
        when no controller anchor is available (legacy toggle-open path).
        """
        preferred: WorkbenchRow | None = None
        if self.harmony_controller is not None and self.harmony_controller.anchor is not None:
            preferred = self.harmony_controller.anchor
            for qml_row in self.view_model.browser_rows:
                if str(qml_row.source_row.path) == str(preferred.path):
                    return qml_row.source_row
            return None
        index = int(self.view_model.selected_browser_index)
        if 0 <= index < len(self.view_model.browser_rows):
            return self.view_model.browser_rows[index].source_row
        return None

    def replace_browser_scope(self, scope: object) -> None:
        """Central hook after a successful browser-scope replacement.

        When *scope* differs from the scope the current harmonic-match session
        was computed against, the session is deterministically invalidated:
        the panel closes, old harmony rows stop being actionable, and the next
        open computes the new scope's anchor and candidate pool exactly once.
        Same-scope reloads keep the existing close/reopen reuse intact.
        """
        self.close_sample_context()
        self._harmonic_match_browser_scope = scope
        if scope is not None and scope == self._harmonic_match_session_scope:
            if not self.harmonic_match_open:
                return
            if not self.view_model.browser_rows:
                self._invalidate_harmonic_session()
                return
            anchor = self._resolve_live_harmony_anchor()
            if anchor is None:
                self._invalidate_harmonic_session()
                return
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

    def _close_harmonic_match_presentation(self) -> None:
        """Non-destructive Matches close — preserves rows/anchor/matching context.

        Shared by the existing Harmonic Match toggle and Browser presentation
        collapse (#845) so both paths keep one close semantics.
        """
        if not self.harmonic_match_open:
            return
        selected_path: str | None = None
        index = int(self.view_model.selected_browser_index)
        if 0 <= index < len(self.view_model.browser_rows):
            selected_path = str(self.view_model.browser_rows[index].source_row.path)
        self._harmonic_match_selection_path_at_close = selected_path
        self.harmonic_match_open = False
        self.view_model.state_id = "screen1-default-3panel"
        self.view_model.harmony_status = "Harmonic Match ist ausgeschaltet."

    def toggle_browser_collapsed(self) -> bool:
        """Toggle Browser presentation collapse without clearing domain state."""
        if self.browser_collapsed:
            self.browser_collapsed = False
            return False
        if self.harmonic_match_open:
            # Reuse the existing Harmony close contract (no second close path).
            self._close_harmonic_match_presentation()
        self.browser_collapsed = True
        return True

    def toggle_live_kit_collapsed(self) -> bool:
        """Toggle Live Kit presentation after materialization; never unmaterialize."""
        if not bool(self.view_model.live_kit_materialized):
            return False
        self.live_kit_collapsed = not self.live_kit_collapsed
        return bool(self.live_kit_collapsed)

    def open_harmonic_matches_for_row(self, row: WorkbenchRow) -> bool:
        """Open or retarget Harmonic Matches for an explicit row (#843).

        Semantically OPEN/RETARGET — never toggles the panel closed. Reuses the
        existing ``HarmonicMatchLibraryController`` (one controller, one result
        list, one anchor authority). Browser selection and preview are untouched.
        """
        # Matches ⊂ Browser — fail closed while Browser presentation is collapsed.
        if self.browser_collapsed:
            return False

        fingerprint = self._current_harmonic_match_fingerprint(row)
        same_context = fingerprint == self._harmonic_match_context_fingerprint
        rebound = self._rebind_harmonic_match_rows(row) if same_context else False
        if not same_context or not rebound:
            if self.harmony_controller is not None:
                self.harmony_controller.set_anchor(
                    row,
                    tuple(browser_row.source_row for browser_row in self.view_model.browser_rows),
                )
            self._harmonic_match_context_fingerprint = fingerprint
            self._harmonic_match_selected_index = 0
            self._harmonic_match_scroll_y = 0.0

        self._harmonic_match_session_scope = self._harmonic_match_browser_scope
        self.harmonic_match_open = True
        self._project_harmonic_match(row)
        self.view_model.state_id = "screen1-harmonic-4panel"
        return True

    def toggle_harmonic_match(self) -> bool:
        """Open/close Matches presentation; open path reuses open/retarget (#845)."""
        if self.harmonic_match_open:
            self._close_harmonic_match_presentation()
            return False
        if self.browser_collapsed:
            return False
        # After #845 non-destructive close: restore the preserved harmony session
        # when Browser selection identity did not change while collapsed. If the
        # user selected a different sample, treat toggle-open as selection-based.
        preserved = (
            self.harmony_controller is not None
            and self.harmony_controller.anchor is not None
            and self._harmonic_match_context_fingerprint is not None
        )
        current_selected_path: str | None = None
        index = int(self.view_model.selected_browser_index)
        if 0 <= index < len(self.view_model.browser_rows):
            current_selected_path = str(self.view_model.browser_rows[index].source_row.path)
        recorded_close = self._harmonic_match_selection_path_at_close
        selection_unchanged = (
            recorded_close is not self._HARMONIC_CLOSE_SELECTION_UNSET
            and current_selected_path == recorded_close
        )
        if preserved and selection_unchanged:
            restore_row = self.harmony_controller.anchor
            # Rebind preserved anchor to the current Browser WorkbenchRow by path.
            resolved: WorkbenchRow | None = None
            for qml_row in self.view_model.browser_rows:
                if str(qml_row.source_row.path) == str(restore_row.path):
                    resolved = qml_row.source_row
                    break
            if resolved is not None:
                return self.open_harmonic_matches_for_row(resolved)
            # Preserved anchor disappeared from Browser — drop stale session and
            # fall through to selection-based open (or empty fail-closed).
            self._harmonic_match_context_fingerprint = None
            self._harmonic_match_selection_path_at_close = (
                self._HARMONIC_CLOSE_SELECTION_UNSET
            )
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
        return self.open_harmonic_matches_for_row(anchor)


def qml_runtime_available() -> bool:
    try:
        import PySide6  # noqa: F401
    except ModuleNotFoundError:
        return False
    return True


SCREEN1_BACKGROUND_REFERENCE_RELATIVE = Path(
    "docs/assets/portfolio/references/screen1_background_reference.png"
)
SCREEN1_BACKGROUND_REFERENCE_SHA256 = (
    "2c799440a7b2c9d6e20e8163378ddcbecd29478d76ad8d7ee74835d3b60a47ae"
)


def screen1_background_reference_path() -> Path:
    """Return the canonical Screen-1 background reference path.

    Resolution order:
    1. PyInstaller extract root (`sys._MEIPASS`) when the PNG was packed as data
    2. Directory next to a frozen / distributable executable
    3. Repository root next to ``src/`` (editable / source runs)
    """
    relative = SCREEN1_BACKGROUND_REFERENCE_RELATIVE
    candidates: list[Path] = []

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / relative)

    frozen = bool(getattr(sys, "frozen", False))
    distributable = os.environ.get("SAMPLE_BRAIN_DISTRIBUTABLE", "").strip() in {
        "1",
        "true",
        "TRUE",
        "yes",
        "YES",
    }
    if frozen or distributable:
        candidates.append(Path(sys.executable).resolve().parent / relative)

    candidates.append(Path(__file__).resolve().parents[1] / relative)

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[-1]


def screen1_background_url() -> str:
    """Return a file URL for the canonical Screen-1 background reference."""
    return screen1_background_reference_path().resolve().as_uri()


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
    color: theme.surfaceHeader
    // Single QML call site for Harmonic Match toggle (#845 handles reuse this).
    function activateHarmonicMatchToggle() {
        window.interaction.toggleHarmonicMatch()
    }
    title: "Sample Brain"
    property var screenData: screenModel
    property var interaction: interactionModel
    property var channelRack: channelRackModel
    property var tempoSync: tempoSyncModel
    property var sessionPersistence: sessionPersistenceModel
    readonly property string activeScreen: channelRack.activeScreen
    // Screen-1 Theme Authority (#785): Theme Core owns colors; QML binds semantics.
    // No competing HEX palette here — see docs/assets/themes/ and workbench_theme.py.
    QtObject {
        id: theme
        readonly property color surfaceRoot: themeAuthority.surfaceRoot
        readonly property color surfaceHeader: themeAuthority.surfaceHeader
        readonly property color surfaceBrowser: themeAuthority.surfaceBrowser
        readonly property color surfacePanel: themeAuthority.surfacePanel
        readonly property color surfaceElevated: themeAuthority.surfaceElevated
        readonly property color borderSubtle: themeAuthority.borderSubtle
        readonly property color dividerDefault: themeAuthority.dividerDefault
        readonly property color textPrimary: themeAuthority.textPrimary
        readonly property color textSecondary: themeAuthority.textSecondary
        readonly property color textDisabled: themeAuthority.textDisabled
        readonly property color textOnAction: themeAuthority.textOnAction
        readonly property color waveformDefault: themeAuthority.waveformDefault
        readonly property color waveformActive: themeAuthority.waveformActive
        readonly property color selectionSurface: themeAuthority.selectionSurface
        readonly property color selectionBorder: themeAuthority.selectionBorder
        readonly property color actionActive: themeAuthority.actionActive
        readonly property color focusRing: themeAuthority.focusRing
        readonly property color hoverSurface: themeAuthority.hoverSurface
    }
    // #770 shared context-hint content seam (ephemeral UI state; placement is separate).
    QtObject {
        id: contextHintState
        objectName: "contextHintState"
        readonly property var descriptors: ({
            "library.scope.sources": { "label": "Sample Sources", "help": "analysierte Sample-Quellen" },
            "library.scope.all_samples": { "label": "All Samples", "help": "alle Samples im Workspace" },
            "library.scope.collections": { "label": "Collections", "help": "gespeicherte Sample-Sammlungen" },
            "library.scope.favorites": { "label": "Favorites", "help": "markierte Samples" },
            "library.scope.recordings": { "label": "Recordings", "help": "lokale Aufnahmen" },
            "library.add_source": { "label": "Add Source", "help": "lokalen Sample-Ordner hinzufügen" }
        })
        property string hoveredId: ""
        property string focusedId: ""
        property string activeId: ""
        property string activeLabel: ""
        property string activeHelp: ""
        // Hover/focus control descriptors win; else existing browser selection hint.
        readonly property string displayText: activeId.length > 0
            ? (activeLabel + " — " + activeHelp)
            : (window.screenData.selectedSampleContextHint || "")

        function resolveActiveId() {
            if (hoveredId.length > 0)
                return hoveredId
            if (focusedId.length > 0)
                return focusedId
            return ""
        }
        function applyDescriptor(id) {
            activeId = id
            if (id.length === 0 || descriptors[id] === undefined) {
                activeLabel = ""
                activeHelp = ""
                return
            }
            activeLabel = descriptors[id].label
            activeHelp = descriptors[id].help
        }
        function reconcile() {
            applyDescriptor(resolveActiveId())
        }
        function reportHover(id) {
            hoveredId = id
            reconcile()
        }
        function clearHover(id) {
            if (hoveredId === id)
                hoveredId = ""
            reconcile()
        }
        function reportFocus(id) {
            focusedId = id
            reconcile()
        }
        function clearFocus(id) {
            if (focusedId === id)
                focusedId = ""
            reconcile()
        }
        onHoveredIdChanged: reconcile()
        onFocusedIdChanged: reconcile()
    }
    // Thin aliases for runtime property reads / legacy window.* bindings.
    readonly property color panel: theme.surfacePanel
    readonly property color panelAlt: theme.surfaceElevated
    readonly property color textColor: theme.textPrimary
    readonly property color muted: theme.textSecondary
    readonly property color border: theme.borderSubtle
    readonly property color accent: theme.actionActive
    readonly property color divider: theme.dividerDefault
    readonly property color selectedRow: theme.selectionSurface
    readonly property color headerBg: theme.surfaceHeader
    readonly property color browserPaneBg: theme.surfaceBrowser
    readonly property color waveformMuted: theme.waveformDefault
    property int textTitle: 18
    property int textBody: 12
    property int textMeta: 11
    property int textCaption: 10
    // #692 shared compact density (logical px / DIP) — Browser + Harmonic Match.
    // densityRowHeight=30 is the first implementation baseline, not a forever-lock:
    // Owner Visual Acceptance may later retarget (e.g. 28/32) via explicit product
    // adjustment of this token together with the frozen #692 assertion.
    property int densityRowHeight: 30
    property int densityVerticalInset: 4
    property int densityHorizontalInset: 8
    property int densityWaveformHeight: 22
    property int densityRowSpacing: 8
    property int densityDividerHeight: 1
    property int densityActionHitTarget: 24
    property int browserWaveformWidth: 180
    property int browserWaveformMin: 140
    property int browserMetaColumnWidth: 48
    property int browserFavoriteColumnWidth: 28
    property int browserLengthColumnWidth: 62
    property int browserTypeColumnWidth: 72
    property int harmonicWaveformWidth: 72
    property int harmonicRelationColumnWidth: 72
    property int harmonicAddColumnWidth: 44
    property int browserDelegateCreations: 0
    // #738 playhead presentation seam (no Settings UI — #696 owns preferences).
    readonly property string waveformMotionMode: window.interaction.waveformMotionMode
    readonly property bool previewPlayheadArmed: window.interaction.previewPlaybackPlaying
        && window.waveformMotionMode !== "off"
        && window.interaction.previewPlayingPath !== ""

    FrameAnimation {
        id: previewPlaybackDriver
        running: window.previewPlayheadArmed
        onTriggered: window.interaction.refreshPreviewPlayback()
    }

    FolderDialog {
        id: addSourceDialog
        title: "Sample Source hinzufügen"
        onAccepted: libraryInteraction.registerSourceUrl(selectedFolder.toString())
    }

    FolderDialog {
        id: exportKitDialog
        title: "Live Kit exportieren"
        onAccepted: window.interaction.exportLiveKitUrl(selectedFolder.toString())
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

    // Canonical Screen-1 background: full original asset stretched to the
    // available content area. No crop, tint, blur, glow, or ambient overlays.
    Image {
        id: screen1Background
        objectName: "screen1Background"
        anchors.fill: parent
        z: -1
        source: screen1BackgroundUrl
        fillMode: Image.Stretch
        asynchronous: true
    }

    // #831 program footer band — scope left / context center / status right (#830 / #770).
    // Footer-context centering: true center layer on full footer width (not RowLayout leftover).
    // #880: slim status-bar footer (chosen ~22; not screenshot-pixel truth).
    // Global program chrome: keep the footer present on Screen 1 and Screen 2.
    // Dark surface hierarchy: footer paints chrome (surfaceHeader), not workspace root.
    footer: Item {
        id: programFooterBand
        objectName: "programFooterBand"
        height: 22
        Rectangle {
            anchors.fill: parent
            color: theme.surfaceHeader
            z: -1
        }
        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: 1
            color: theme.dividerDefault
            opacity: 0.28
            z: 3
        }
        // CENTER: geometrically centered on full footer midpoint (below hit zones).
        Item {
            id: footerContextCenterLayer
            objectName: "footerContextCenterLayer"
            anchors.fill: parent
            z: 0
            // Display-only: never intercept hover/pointer for left/right controls.
            enabled: false
            Label {
                id: contextHintDisplay
                objectName: "contextHintDisplay"
                readonly property real leftBound: libraryScopeBar.x + libraryScopeBar.width + 6
                readonly property real rightBound: footerStatusZone.x - 6
                readonly property real mid: parent.width / 2
                readonly property real maxHalf: Math.max(
                    0,
                    Math.min(mid - leftBound, rightBound - mid)
                )
                width: Math.min(implicitWidth, maxHalf * 2)
                x: mid - width / 2
                anchors.verticalCenter: parent.verticalCenter
                text: contextHintState.displayText
                color: theme.textSecondary
                font.pixelSize: window.textCaption
                opacity: text.length > 0 ? 1.0 : 0.0
                elide: Text.ElideRight
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                focus: false
                activeFocusOnTab: false
                Accessible.ignored: true
                Keys.forwardTo: []
            }
        }
        // RIGHT: existing status zone (may be empty/neutral; must not steal center).
        Item {
            id: footerStatusZone
            objectName: "footerStatusZone"
            anchors.right: parent.right
            anchors.rightMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            width: Math.max(1, footerStatusLabel.implicitWidth)
            height: parent.height
            z: 2
            Label {
                id: footerStatusLabel
                objectName: "footerStatusLabel"
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                text: ""
                color: theme.textSecondary
                font.pixelSize: window.textCaption
                opacity: text.length > 0 ? 1.0 : 0.0
                elide: Text.ElideRight
                focus: false
                activeFocusOnTab: false
                Accessible.ignored: true
            }
        }
        // LEFT: existing #837 scope utility.
        RowLayout {
            id: libraryScopeBar
            objectName: "libraryScopeBar"
            anchors.left: parent.left
            anchors.leftMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            height: parent.height
            spacing: 2
            z: 2
            property string mode: "sources"
            readonly property int controlSize: 18
            readonly property int iconPad: 3

                // Active = fine accent underline + ink tint; no filled toolbar chip.
                function scopeFill(active, hovered) {
                    if (hovered && !active)
                        return theme.hoverSurface
                    return "transparent"
                }
                function scopeStroke(active) {
                    return "transparent"
                }
                function scopeInk(active) {
                    return active ? theme.actionActive : theme.textSecondary
                }

                ToolButton {
                    id: sourcesScopeButton
                    objectName: "librarySourcesScopeButton"
                    text: ""
                    flat: true
                    checkable: true
                    checked: libraryScopeBar.mode === "sources"
                    Layout.preferredWidth: libraryScopeBar.controlSize
                    Layout.preferredHeight: libraryScopeBar.controlSize
                    onClicked: libraryScopeBar.mode = "sources"
                    Accessible.name: "Sample Sources"
                    onHoveredChanged: {
                        if (hovered)
                            contextHintState.reportHover("library.scope.sources")
                        else
                            contextHintState.clearHover("library.scope.sources")
                    }
                    onActiveFocusChanged: {
                        if (activeFocus)
                            contextHintState.reportFocus("library.scope.sources")
                        else
                            contextHintState.clearFocus("library.scope.sources")
                    }
                    background: Item {
                        Rectangle {
                            anchors.fill: parent
                            color: libraryScopeBar.scopeFill(sourcesScopeButton.checked, sourcesScopeButton.hovered)
                        }
                        Rectangle {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            height: 1
                            color: theme.actionActive
                            visible: sourcesScopeButton.checked
                            opacity: 0.9
                        }
                    }
                    contentItem: Item {
                        anchors.fill: parent
                        Canvas {
                            anchors.fill: parent
                            anchors.margins: libraryScopeBar.iconPad
                            onPaint: {
                                var ctx = getContext("2d")
                                ctx.reset()
                                ctx.strokeStyle = libraryScopeBar.scopeInk(sourcesScopeButton.checked)
                                ctx.lineWidth = 1
                                ctx.strokeRect(1, 4, width - 2, height - 6)
                                ctx.beginPath()
                                ctx.moveTo(1, 8)
                                ctx.lineTo(width - 1, 8)
                                ctx.stroke()
                            }
                            Component.onCompleted: requestPaint()
                            Connections {
                                target: sourcesScopeButton
                                function onCheckedChanged() { parent.requestPaint() }
                                function onHoveredChanged() { parent.requestPaint() }
                            }
                        }
                    }
                }
                ToolButton {
                    id: allSamplesScopeButton
                    objectName: "libraryAllSamplesScopeButton"
                    text: ""
                    flat: true
                    checkable: true
                    checked: libraryScopeBar.mode === "all"
                    Layout.preferredWidth: libraryScopeBar.controlSize
                    Layout.preferredHeight: libraryScopeBar.controlSize
                    onClicked: {
                        libraryScopeBar.mode = "all"
                        libraryInteraction.selectLibraryNode("scope:all-library")
                    }
                    Accessible.name: "All Samples"
                    onHoveredChanged: {
                        if (hovered)
                            contextHintState.reportHover("library.scope.all_samples")
                        else
                            contextHintState.clearHover("library.scope.all_samples")
                    }
                    onActiveFocusChanged: {
                        if (activeFocus)
                            contextHintState.reportFocus("library.scope.all_samples")
                        else
                            contextHintState.clearFocus("library.scope.all_samples")
                    }
                    background: Item {
                        Rectangle {
                            anchors.fill: parent
                            color: libraryScopeBar.scopeFill(allSamplesScopeButton.checked, allSamplesScopeButton.hovered)
                        }
                        Rectangle {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            height: 1
                            color: theme.actionActive
                            visible: allSamplesScopeButton.checked
                            opacity: 0.9
                        }
                    }
                    contentItem: Item {
                        anchors.fill: parent
                        Canvas {
                            anchors.fill: parent
                            anchors.margins: libraryScopeBar.iconPad
                            onPaint: {
                                var ctx = getContext("2d")
                                ctx.reset()
                                ctx.strokeStyle = libraryScopeBar.scopeInk(allSamplesScopeButton.checked)
                                ctx.lineWidth = 1
                                var y1 = height * 0.25
                                var y2 = height * 0.5
                                var y3 = height * 0.75
                                ctx.beginPath(); ctx.moveTo(0, y1); ctx.lineTo(width, y1); ctx.stroke()
                                ctx.beginPath(); ctx.moveTo(0, y2); ctx.lineTo(width, y2); ctx.stroke()
                                ctx.beginPath(); ctx.moveTo(0, y3); ctx.lineTo(width, y3); ctx.stroke()
                            }
                            Component.onCompleted: requestPaint()
                            Connections {
                                target: allSamplesScopeButton
                                function onCheckedChanged() { parent.requestPaint() }
                                function onHoveredChanged() { parent.requestPaint() }
                            }
                        }
                    }
                }
                ToolButton {
                    id: collectionsScopeButton
                    objectName: "libraryCollectionsScopeButton"
                    text: ""
                    flat: true
                    checkable: true
                    checked: libraryScopeBar.mode === "collections"
                    Layout.preferredWidth: libraryScopeBar.controlSize
                    Layout.preferredHeight: libraryScopeBar.controlSize
                    onClicked: libraryScopeBar.mode = "collections"
                    Accessible.name: "Collections"
                    onHoveredChanged: {
                        if (hovered)
                            contextHintState.reportHover("library.scope.collections")
                        else
                            contextHintState.clearHover("library.scope.collections")
                    }
                    onActiveFocusChanged: {
                        if (activeFocus)
                            contextHintState.reportFocus("library.scope.collections")
                        else
                            contextHintState.clearFocus("library.scope.collections")
                    }
                    background: Item {
                        Rectangle {
                            anchors.fill: parent
                            color: libraryScopeBar.scopeFill(collectionsScopeButton.checked, collectionsScopeButton.hovered)
                        }
                        Rectangle {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            height: 1
                            color: theme.actionActive
                            visible: collectionsScopeButton.checked
                            opacity: 0.9
                        }
                    }
                    contentItem: Item {
                        anchors.fill: parent
                        Canvas {
                            anchors.fill: parent
                            anchors.margins: libraryScopeBar.iconPad
                            onPaint: {
                                var ctx = getContext("2d")
                                ctx.reset()
                                ctx.strokeStyle = libraryScopeBar.scopeInk(collectionsScopeButton.checked)
                                ctx.lineWidth = 1
                                ctx.strokeRect(2, 1, width - 6, height - 6)
                                ctx.strokeRect(5, 4, width - 6, height - 6)
                            }
                            Component.onCompleted: requestPaint()
                            Connections {
                                target: collectionsScopeButton
                                function onCheckedChanged() { parent.requestPaint() }
                                function onHoveredChanged() { parent.requestPaint() }
                            }
                        }
                    }
                }
                ToolButton {
                    id: favoritesScopeButton
                    objectName: "libraryFavoritesScopeButton"
                    text: ""
                    flat: true
                    checkable: true
                    checked: libraryScopeBar.mode === "favorites"
                    Layout.preferredWidth: libraryScopeBar.controlSize
                    Layout.preferredHeight: libraryScopeBar.controlSize
                    onClicked: {
                        libraryScopeBar.mode = "favorites"
                        libraryInteraction.selectLibraryNode("scope:favorites")
                    }
                    Accessible.name: "Favorites"
                    onHoveredChanged: {
                        if (hovered)
                            contextHintState.reportHover("library.scope.favorites")
                        else
                            contextHintState.clearHover("library.scope.favorites")
                    }
                    onActiveFocusChanged: {
                        if (activeFocus)
                            contextHintState.reportFocus("library.scope.favorites")
                        else
                            contextHintState.clearFocus("library.scope.favorites")
                    }
                    background: Item {
                        Rectangle {
                            anchors.fill: parent
                            color: libraryScopeBar.scopeFill(favoritesScopeButton.checked, favoritesScopeButton.hovered)
                        }
                        Rectangle {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            height: 1
                            color: theme.actionActive
                            visible: favoritesScopeButton.checked
                            opacity: 0.9
                        }
                    }
                    contentItem: Item {
                        anchors.fill: parent
                        Canvas {
                            anchors.fill: parent
                            anchors.margins: libraryScopeBar.iconPad
                            onPaint: {
                                var ctx = getContext("2d")
                                ctx.reset()
                                ctx.strokeStyle = libraryScopeBar.scopeInk(favoritesScopeButton.checked)
                                ctx.fillStyle = libraryScopeBar.scopeInk(favoritesScopeButton.checked)
                                ctx.lineWidth = 1
                                var cx = width / 2
                                var cy = height / 2
                                var r = Math.min(width, height) / 2 - 0.5
                                ctx.beginPath()
                                for (var i = 0; i < 5; i++) {
                                var a = -Math.PI / 2 + i * 2 * Math.PI / 5
                                var x = cx + Math.cos(a) * r
                                var y = cy + Math.sin(a) * r
                                if (i === 0)
                                    ctx.moveTo(x, y)
                                else
                                    ctx.lineTo(x, y)
                                var b = a + Math.PI / 5
                                var ix = cx + Math.cos(b) * (r * 0.45)
                                var iy = cy + Math.sin(b) * (r * 0.45)
                                ctx.lineTo(ix, iy)
                                }
                                ctx.closePath()
                                if (favoritesScopeButton.checked)
                                ctx.fill()
                                else
                                ctx.stroke()
                            }
                            Component.onCompleted: requestPaint()
                            Connections {
                                target: favoritesScopeButton
                                function onCheckedChanged() { parent.requestPaint() }
                                function onHoveredChanged() { parent.requestPaint() }
                            }
                        }
                    }
                }

                ToolButton {
                    id: recordingsScopeButton
                    objectName: "libraryRecordingsScopeButton"
                    text: ""
                    flat: true
                    checkable: true
                    checked: libraryScopeBar.mode === "recordings"
                    Layout.preferredWidth: libraryScopeBar.controlSize
                    Layout.preferredHeight: libraryScopeBar.controlSize
                    onClicked: {
                        libraryScopeBar.mode = "recordings"
                        libraryInteraction.selectLibraryNode("scope:recordings")
                    }
                    Accessible.name: "Recordings"
                    onHoveredChanged: {
                        if (hovered)
                            contextHintState.reportHover("library.scope.recordings")
                        else
                            contextHintState.clearHover("library.scope.recordings")
                    }
                    onActiveFocusChanged: {
                        if (activeFocus)
                            contextHintState.reportFocus("library.scope.recordings")
                        else
                            contextHintState.clearFocus("library.scope.recordings")
                    }
                    background: Item {
                        Rectangle {
                            anchors.fill: parent
                            color: libraryScopeBar.scopeFill(recordingsScopeButton.checked, recordingsScopeButton.hovered)
                        }
                        Rectangle {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            height: 1
                            color: theme.actionActive
                            visible: recordingsScopeButton.checked
                            opacity: 0.9
                        }
                    }
                    contentItem: Item {
                        anchors.fill: parent
                        Canvas {
                            anchors.fill: parent
                            anchors.margins: libraryScopeBar.iconPad
                            onPaint: {
                                var ctx = getContext("2d")
                                ctx.reset()
                                ctx.strokeStyle = libraryScopeBar.scopeInk(recordingsScopeButton.checked)
                                ctx.lineWidth = 1
                                ctx.beginPath()
                                ctx.moveTo(1, height * 0.55)
                                ctx.lineTo(width * 0.25, height * 0.35)
                                ctx.lineTo(width * 0.45, height * 0.7)
                                ctx.lineTo(width * 0.7, height * 0.25)
                                ctx.lineTo(width - 1, height * 0.5)
                                ctx.stroke()
                                ctx.beginPath()
                                ctx.moveTo(width * 0.15, height - 2)
                                ctx.lineTo(width * 0.85, height - 2)
                                ctx.stroke()
                            }
                            Component.onCompleted: requestPaint()
                            Connections {
                                target: recordingsScopeButton
                                function onCheckedChanged() { parent.requestPaint() }
                                function onHoveredChanged() { parent.requestPaint() }
                            }
                        }
                    }
                }
        }
    }

    // #831 program chrome — identity left / navigation center / tempo zone right (#830).
    // #880: slim/premium header geometry (chosen ~30; not screenshot-pixel truth).
    header: Rectangle {
        id: screen1Header
        objectName: "screen1Header"
        height: 30
        color: theme.surfaceHeader
        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 1
            color: theme.dividerDefault
            opacity: 0.28
            z: 3
        }

        Item {
            id: headerLeftZone
            objectName: "headerLeftZone"
            anchors.left: parent.left
            anchors.leftMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            height: parent.height
            width: productIdentity.implicitWidth
            z: 2
            Label {
                id: productIdentity
                anchors.verticalCenter: parent.verticalCenter
                text: "Sample Brain"
                color: theme.textPrimary
                font.pixelSize: 12
                font.bold: false
            }
        }

        Item {
            id: headerNavZone
            objectName: "headerNavZone"
            // Three-zone geometry: occupy only the band between identity and
            // the right tempo/master zone so hit areas cannot overlap.
            readonly property real leftEdge: headerLeftZone.x + headerLeftZone.width + 12
            readonly property real rightEdge: headerTransportZone.x - 12
            x: leftEdge
            width: Math.max(0, rightEdge - leftEdge)
            anchors.verticalCenter: parent.verticalCenter
            height: parent.height
            clip: true
            z: 1
            RowLayout {
                id: headerNavRow
                objectName: "headerNavRow"
                // Keep labels window-centered when they fit; otherwise pack into the zone.
                readonly property real idealX: (screen1Header.width - implicitWidth) / 2 - parent.x
                x: Math.min(Math.max(0, idealX), Math.max(0, parent.width - width))
                anchors.verticalCenter: parent.verticalCenter
                width: Math.min(implicitWidth, parent.width)
                spacing: 2
                ToolButton {
                    id: programNavBrowser
                    objectName: "programNavBrowser"
                    text: "Browser"
                    flat: true
                    font.pixelSize: 10
                    padding: 0
                    leftPadding: 6
                    rightPadding: 6
                    topPadding: 0
                    bottomPadding: 0
                    implicitHeight: screen1Header.height
                    Layout.preferredHeight: screen1Header.height
                    readonly property bool navActive: window.activeScreen === "screen1"
                    background: Item {
                        implicitHeight: screen1Header.height
                        Rectangle {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            height: 1
                            color: theme.actionActive
                            visible: programNavBrowser.navActive
                            opacity: 0.85
                        }
                    }
                    contentItem: Text {
                        text: programNavBrowser.text
                        font: programNavBrowser.font
                        color: programNavBrowser.navActive ? theme.textPrimary : theme.textSecondary
                        opacity: programNavBrowser.navActive ? 1.0 : 0.72
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    onClicked: {
                        if (window.activeScreen === "screen2")
                            window.interaction.returnToScreen1()
                        if (window.interaction.browserCollapsed)
                            window.interaction.toggleBrowserCollapsed()
                    }
                }
                ToolButton {
                    id: programNavLiveKit
                    objectName: "programNavLiveKit"
                    text: "Live Kit"
                    flat: true
                    font.pixelSize: 10
                    padding: 0
                    leftPadding: 6
                    rightPadding: 6
                    topPadding: 0
                    bottomPadding: 0
                    implicitHeight: screen1Header.height
                    Layout.preferredHeight: screen1Header.height
                    enabled: window.interaction.liveKitRevealed
                    readonly property bool navActive: false
                    background: Item {
                        implicitHeight: screen1Header.height
                        Rectangle {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            height: 1
                            color: theme.actionActive
                            visible: programNavLiveKit.navActive
                            opacity: 0.85
                        }
                    }
                    contentItem: Text {
                        text: programNavLiveKit.text
                        font: programNavLiveKit.font
                        color: programNavLiveKit.enabled
                            ? (programNavLiveKit.navActive ? theme.textPrimary : theme.textSecondary)
                            : theme.textDisabled
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        opacity: programNavLiveKit.enabled
                            ? (programNavLiveKit.navActive ? 1.0 : 0.72)
                            : 0.4
                    }
                    onClicked: {
                        if (window.activeScreen === "screen2")
                            window.interaction.returnToScreen1()
                        if (window.interaction.liveKitCollapsed)
                            window.interaction.toggleLiveKitCollapsed()
                    }
                }
                ToolButton {
                    id: programNavStepSequencer
                    objectName: "programNavStepSequencer"
                    text: "Step Sequencer"
                    flat: true
                    font.pixelSize: 10
                    padding: 0
                    leftPadding: 6
                    rightPadding: 6
                    topPadding: 0
                    bottomPadding: 0
                    implicitHeight: screen1Header.height
                    Layout.preferredHeight: screen1Header.height
                    readonly property bool navActive: window.channelRack.bottomRackMaterialized
                    background: Item {
                        implicitHeight: screen1Header.height
                        Rectangle {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            height: 1
                            color: theme.actionActive
                            visible: programNavStepSequencer.navActive
                            opacity: 0.85
                        }
                    }
                    contentItem: Text {
                        text: programNavStepSequencer.text
                        font: programNavStepSequencer.font
                        color: programNavStepSequencer.navActive ? theme.textPrimary : theme.textSecondary
                        opacity: programNavStepSequencer.navActive ? 1.0 : 0.72
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    onClicked: {
                        // #908: materialize bottom Rack; no Screen-2 page navigation
                        window.interaction.openChannelRack()
                    }
                }
                ToolButton {
                    id: programNavArrangement
                    objectName: "programNavArrangement"
                    text: "Arrangement"
                    flat: true
                    font.pixelSize: 10
                    padding: 0
                    leftPadding: 6
                    rightPadding: 6
                    topPadding: 0
                    bottomPadding: 0
                    implicitHeight: screen1Header.height
                    Layout.preferredHeight: screen1Header.height
                    enabled: false
                    background: Item { implicitHeight: screen1Header.height }
                    contentItem: Text {
                        text: programNavArrangement.text
                        font: programNavArrangement.font
                        color: theme.textDisabled
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        opacity: 0.4
                    }
                }
            }
        }

        Item {
            id: headerTransportZone
            objectName: "headerTransportZone"
            anchors.right: parent.right
            anchors.rightMargin: 10
            anchors.verticalCenter: parent.verticalCenter
            height: parent.height
            // Reserve a usable nav band (~380px) for four destinations at min width.
            readonly property real maxWidth: Math.max(
                240,
                parent.width - headerLeftZone.width - 380 - 56
            )
            width: Math.min(headerTransportRow.implicitWidth, maxWidth)
            clip: true
            z: 2
            RowLayout {
                id: headerTransportRow
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                spacing: 2
                width: implicitWidth
            // #805: MASTER/GRID/SYNC project session tempo/SYNC authority only.
            // #880: compact tempo-zone group (no stretched utility widgets).
            Label { text: "MASTER"; color: theme.textSecondary; font.pixelSize: 9; Layout.alignment: Qt.AlignVCenter; opacity: 0.85 }
            Button {
                objectName: "tempoDownButton"
                text: "−"
                Accessible.name: "Tempo down"
                flat: true
                implicitWidth: 14
                implicitHeight: 18
                Layout.alignment: Qt.AlignVCenter
                contentItem: Text {
                    text: "−"
                    color: theme.textSecondary
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    font.pixelSize: 11
                }
                background: Item {}
                onClicked: window.tempoSync.adjustTempo(-1.0)
            }
            Label {
                objectName: "masterTempoValue"
                text: window.tempoSync.masterTempoText
                color: theme.textPrimary
                font.pixelSize: 12
                font.bold: false
                Layout.alignment: Qt.AlignVCenter
            }
            Button {
                objectName: "tempoUpButton"
                text: "+"
                Accessible.name: "Tempo up"
                flat: true
                implicitWidth: 14
                implicitHeight: 18
                Layout.alignment: Qt.AlignVCenter
                contentItem: Text {
                    text: "+"
                    color: theme.textSecondary
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    font.pixelSize: 11
                }
                background: Item {}
                onClicked: window.tempoSync.adjustTempo(1.0)
            }
            Label { text: "BPM"; color: theme.textSecondary; font.pixelSize: 9; Layout.alignment: Qt.AlignVCenter; opacity: 0.85 }
            Item { width: 6 }
            Label { text: "GRID"; color: theme.textSecondary; font.pixelSize: 9; Layout.alignment: Qt.AlignVCenter; opacity: 0.85 }
            Label {
                objectName: "gridValue"
                text: window.tempoSync.gridText
                color: theme.textPrimary
                font.pixelSize: 12
                font.bold: false
                Layout.alignment: Qt.AlignVCenter
            }
            Item { width: 6 }
            Label { text: "SYNC"; color: theme.textSecondary; font.pixelSize: 9; Layout.alignment: Qt.AlignVCenter; opacity: 0.85 }
            Rectangle {
                id: syncIndicator
                objectName: "syncIndicator"
                width: 28; height: 14; radius: 1
                color: window.tempoSync.syncEnabled ? theme.actionActive : "transparent"
                border.width: 1
                border.color: window.tempoSync.syncEnabled ? theme.actionActive : theme.borderSubtle
                Layout.alignment: Qt.AlignVCenter
                Accessible.name: "SYNC"
                Label {
                    objectName: "syncStateLabel"
                    anchors.centerIn: parent
                    text: window.tempoSync.syncEnabled ? "ON" : "OFF"
                    color: window.tempoSync.syncEnabled ? theme.textOnAction : theme.textSecondary
                    font.pixelSize: 8
                    font.bold: false
                }
                MouseArea {
                    // Expand hit area slightly beyond the slim visual chip.
                    anchors.fill: parent
                    anchors.margins: -3
                    cursorShape: Qt.PointingHandCursor
                    onClicked: window.tempoSync.toggleSync()
                }
            }
            Item { width: 4 }
            // #819: calm Python-owned persistence honesty (hidden when OK/fresh).
            Label {
                objectName: "sessionPersistenceStatusLabel"
                visible: window.sessionPersistence.attention
                text: window.sessionPersistence.statusLabel
                color: theme.textSecondary
                font.pixelSize: 9
                Layout.alignment: Qt.AlignVCenter
                // Secondary honesty may compact; critical tempo/SYNC controls stay.
                Layout.maximumWidth: screen1Header.width < 1200 ? 72 : 140
                elide: Text.ElideRight
                Accessible.name: "Session persistence status"
            }
            Item {
                width: window.sessionPersistence.attention ? 4 : 0
            }
            // #843: Harmonic Matches producer entry is the Sample Context Menu.
            // #845 collapse/reopen keeps activateHarmonicMatchToggle() as the sole helper.
            Item {
                Layout.preferredWidth: displayPreferencesOverflow.implicitWidth
                Layout.preferredHeight: displayPreferencesOverflow.implicitHeight
                ToolButton {
                    id: displayPreferencesOverflow
                    objectName: "displayPreferencesOverflow"
                    visible: window.activeScreen === "screen1"
                    text: "⋯"
                    flat: true
                    implicitWidth: 20
                    implicitHeight: 18
                    padding: 0
                    background: Item {}
                    contentItem: Text {
                        text: "⋯"
                        color: theme.textSecondary
                        opacity: 0.75
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        font.pixelSize: 12
                    }
                    onClicked: displayPreferencesPopover.open()
                    Accessible.name: "Display preferences"
                }
                Popup {
                    id: displayPreferencesPopover
                    objectName: "displayPreferencesPopover"
                    x: displayPreferencesOverflow.width - width
                    y: displayPreferencesOverflow.height + 6
                    width: 300
                    padding: 12
                    modal: false
                    focus: true
                    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
                    background: Rectangle {
                        color: theme.surfaceElevated
                        border.color: theme.borderSubtle
                        radius: 6
                    }
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 8
                        Label { text: "Appearance"; color: theme.textSecondary; font.pixelSize: 11 }
                        ComboBox {
                            id: themePresetSelector
                            objectName: "themePresetSelector"
                            Layout.fillWidth: true
                            model: themeAuthority.availableThemeNames
                            currentIndex: themeAuthority.selectedThemeIndex
                            onActivated: function(index) {
                                themeAuthority.selectTheme(themeAuthority.availableThemeNames[index])
                            }
                        }
                        Button {
                            id: themeCustomizeButton
                            objectName: "themeCustomizeButton"
                            Layout.fillWidth: true
                            text: themeAuthority.isCustom ? "Custom theme active" : "Customize from preset"
                            enabled: !themeAuthority.isCustom
                            onClicked: themeAuthority.customizeSelectedPreset()
                        }
                        Label {
                            visible: themeAuthority.isCustom
                            text: "Base: " + themeAuthority.basePresetName
                            color: theme.textSecondary
                            font.pixelSize: 11
                        }
                        GridLayout {
                            visible: themeAuthority.isCustom
                            columns: 2
                            columnSpacing: 8
                            rowSpacing: 6
                            Layout.fillWidth: true
                            Label { text: "Accent"; color: theme.textSecondary; font.pixelSize: 11 }
                            TextField {
                                id: themeAccentField
                                objectName: "themeAccentField"
                                Layout.fillWidth: true
                                text: themeAuthority.baseAccent
                                onAccepted: themeAuthority.setBaseAccent(text)
                                onActiveFocusChanged: if (!activeFocus) themeAuthority.setBaseAccent(text)
                            }
                            Label { text: "Background"; color: theme.textSecondary; font.pixelSize: 11 }
                            TextField {
                                id: themeBackgroundField
                                objectName: "themeBackgroundField"
                                Layout.fillWidth: true
                                text: themeAuthority.baseBackground
                                onAccepted: themeAuthority.setBaseBackground(text)
                                onActiveFocusChanged: if (!activeFocus) themeAuthority.setBaseBackground(text)
                            }
                            Label { text: "Foreground"; color: theme.textSecondary; font.pixelSize: 11 }
                            TextField {
                                id: themeForegroundField
                                objectName: "themeForegroundField"
                                Layout.fillWidth: true
                                text: themeAuthority.baseForeground
                                onAccepted: themeAuthority.setBaseForeground(text)
                                onActiveFocusChanged: if (!activeFocus) themeAuthority.setBaseForeground(text)
                            }
                        }
                        RowLayout {
                            visible: themeAuthority.isCustom
                            spacing: 6
                            Layout.fillWidth: true
                            Button {
                                objectName: "themeSaveCustomButton"
                                text: "Save"
                                onClicked: themeAuthority.saveCurrentCustom()
                            }
                            Button {
                                objectName: "themeResetCustomButton"
                                text: "Reset"
                                onClicked: themeAuthority.resetCurrentCustom()
                            }
                            Button {
                                objectName: "themeDeleteCustomButton"
                                text: "Delete"
                                onClicked: themeAuthority.deleteCurrentCustom()
                            }
                        }
                        TextField {
                            id: themeRenameField
                            objectName: "themeRenameField"
                            visible: themeAuthority.isCustom
                            Layout.fillWidth: true
                            placeholderText: "Rename custom…"
                            placeholderTextColor: theme.textSecondary
                            onAccepted: {
                                themeAuthority.renameCurrentCustom(text)
                                text = ""
                            }
                        }
                        Label { text: "Density"; color: theme.textSecondary; font.pixelSize: 11 }
                        Label { text: "Compact"; color: theme.textPrimary; font.pixelSize: 13 }
                        Label { text: "Motion"; color: theme.textSecondary; font.pixelSize: 11 }
                        RowLayout {
                            spacing: 6
                            Button {
                                text: "On"
                                checkable: true
                                checked: window.interaction.waveformMotionMode === "on"
                                onClicked: window.interaction.setWaveformMotionMode("on")
                            }
                            Button {
                                text: "Reduced"
                                checkable: true
                                checked: window.interaction.waveformMotionMode === "reduced"
                                onClicked: window.interaction.setWaveformMotionMode("reduced")
                            }
                            Button {
                                text: "Off"
                                checkable: true
                                checked: window.interaction.waveformMotionMode === "off"
                                onClicked: window.interaction.setWaveformMotionMode("off")
                            }
                        }
                        Label { text: "Functional"; color: theme.textSecondary; font.pixelSize: 11 }
                        Button {
                            id: gestureRackApplyToggle
                            objectName: "gestureRackApplyToggle"
                            Layout.fillWidth: true
                            text: "Gesture → Rack apply"
                            checkable: true
                            checked: window.interaction.gestureRackApplyEnabled
                            // Toggle from the Python-owned value so a broken
                            // CheckBox binding cannot leave UI ahead of disk.
                            onClicked: window.interaction.setGestureRackApplyEnabled(
                                !window.interaction.gestureRackApplyEnabled
                            )
                            Accessible.name: "Gesture Rack apply"
                        }
                        Button {
                            Layout.fillWidth: true
                            text: "Reset Layout"
                            onClicked: {
                                window.interaction.resetLayoutPreferences()
                                displayPreferencesPopover.close()
                            }
                        }
                        Button {
                            Layout.fillWidth: true
                            text: "Save Workspace Preset"
                            onClicked: {
                                window.interaction.saveWorkspacePreset()
                                displayPreferencesPopover.close()
                            }
                        }
                        Button {
                            Layout.fillWidth: true
                            text: "Set Preset as Startup"
                            onClicked: {
                                window.interaction.setWorkspacePresetAsStartup()
                                displayPreferencesPopover.close()
                            }
                        }
                        Button {
                            Layout.fillWidth: true
                            text: "Return to Clean Start"
                            onClicked: {
                                window.interaction.returnToCleanStart()
                                displayPreferencesPopover.close()
                            }
                        }
                    }
                }
            }
            }
        }
    }

    Row {
        id: workspaceRow
        objectName: "workspaceRow"
        anchors.fill: parent
        spacing: 0
        visible: window.activeScreen === "screen1"
        Keys.onPressed: function(event) {
            if (event.key === Qt.Key_Escape && window.interaction.previewActive) {
                window.interaction.stopPreview()
                event.accepted = true
            }
        }
        onWidthChanged: layoutModel.setContentWidth(width)
        Component.onCompleted: layoutModel.setContentWidth(width)

        Rectangle { id: libraryPane; objectName: "libraryPane"; width: layoutModel.libraryWidth; height: parent.height; visible: width > 0; color: theme.surfacePanel; border.color: theme.borderSubtle
            ColumnLayout { anchors.fill: parent; anchors.margins: 16
                RowLayout { id: libraryHeaderRow; Layout.fillWidth: true; spacing: 6
                    Label { text: "LIBRARY"; color: theme.textSecondary; font.pixelSize: 12; Layout.fillWidth: true }
                    // #895: secondary control chrome — dark/flat Theme Authority (no default white Button).
                    Button {
                        id: libraryAddSourceButton
                        objectName: "libraryAddSourceButton"
                        text: "Add Source"
                        flat: true
                        implicitHeight: 26
                        padding: 8
                        leftPadding: 10
                        rightPadding: 10
                        Accessible.name: "Add Source"
                        contentItem: Text {
                            text: libraryAddSourceButton.text
                            color: !libraryAddSourceButton.enabled ? theme.textDisabled
                                   : (libraryAddSourceButton.pressed ? theme.textPrimary
                                      : (libraryAddSourceButton.hovered || libraryAddSourceButton.activeFocus ? theme.textPrimary : theme.textSecondary))
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            font.pixelSize: 11
                            opacity: libraryAddSourceButton.enabled ? 1.0 : 0.45
                        }
                        background: Rectangle {
                            implicitHeight: 26
                            radius: 4
                            color: !libraryAddSourceButton.enabled ? "transparent"
                                   : (libraryAddSourceButton.pressed ? theme.surfaceElevated
                                      : (libraryAddSourceButton.hovered ? theme.hoverSurface : "transparent"))
                            border.width: 1
                            border.color: !libraryAddSourceButton.enabled ? theme.borderSubtle
                                          : (libraryAddSourceButton.activeFocus ? theme.focusRing
                                             : (libraryAddSourceButton.pressed ? theme.selectionBorder : theme.borderSubtle))
                            opacity: libraryAddSourceButton.enabled ? 1.0 : 0.4
                        }
                        onClicked: addSourceDialog.open()
                    }
                    Button {
                        id: libraryRemoveSourceButton
                        objectName: "libraryRemoveSourceButton"
                        visible: libraryInteraction.canRemoveSelectedSource
                        text: "Remove"
                        flat: true
                        implicitHeight: 26
                        padding: 8
                        leftPadding: 10
                        rightPadding: 10
                        Accessible.name: "Remove"
                        contentItem: Text {
                            text: libraryRemoveSourceButton.text
                            color: !libraryRemoveSourceButton.enabled ? theme.textDisabled
                                   : (libraryRemoveSourceButton.pressed ? theme.textPrimary
                                      : (libraryRemoveSourceButton.hovered || libraryRemoveSourceButton.activeFocus ? theme.textPrimary : theme.textSecondary))
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            font.pixelSize: 11
                            opacity: libraryRemoveSourceButton.enabled ? 1.0 : 0.45
                        }
                        background: Rectangle {
                            implicitHeight: 26
                            radius: 4
                            color: !libraryRemoveSourceButton.enabled ? "transparent"
                                   : (libraryRemoveSourceButton.pressed ? theme.surfaceElevated
                                      : (libraryRemoveSourceButton.hovered ? theme.hoverSurface : "transparent"))
                            border.width: 1
                            border.color: !libraryRemoveSourceButton.enabled ? theme.borderSubtle
                                          : (libraryRemoveSourceButton.activeFocus ? theme.focusRing
                                             : (libraryRemoveSourceButton.pressed ? theme.selectionBorder : theme.borderSubtle))
                            opacity: libraryRemoveSourceButton.enabled ? 1.0 : 0.4
                        }
                        onClicked: libraryInteraction.prepareRemoveSource()
                    }
                }
                Item {
                    id: libraryContentHost
                    objectName: "libraryContentHost"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                ListView {
                    id: collectionList
                    objectName: "libraryCollectionList"
                    visible: libraryScopeBar.mode === "collections"
                    anchors.fill: parent
                    clip: true
                    focus: visible
                    activeFocusOnTab: visible
                    spacing: 2
                    model: libraryInteraction.collectionEntries
                    delegate: Item {
                        id: collectionRow
                        width: collectionList.width
                        height: 30
                        property bool rowSelected: modelData.selected
                        property bool rowHovered: collectionHover.hovered
                        Rectangle {
                            anchors.fill: parent
                            radius: 4
                            color: collectionRow.rowSelected
                                   ? theme.selectionSurface
                                   : (collectionRow.rowHovered ? theme.surfaceElevated : "transparent")
                            border.width: collectionRow.rowSelected ? 1 : 0
                            border.color: collectionRow.rowSelected ? theme.selectionBorder : "transparent"
                        }
                        Label {
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.left: parent.left
                            anchors.leftMargin: 8
                            anchors.right: parent.right
                            anchors.rightMargin: 8
                            text: modelData.label
                            color: collectionRow.rowSelected ? theme.textPrimary : theme.textSecondary
                            font.pixelSize: 12
                            elide: Text.ElideRight
                        }
                        HoverHandler { id: collectionHover }
                        TapHandler {
                            onTapped: {
                                collectionList.forceActiveFocus()
                                libraryInteraction.selectLibraryNode(modelData.nodeId)
                            }
                        }
                        Accessible.name: modelData.label
                        Accessible.role: Accessible.ListItem
                    }
                    Label {
                        anchors.centerIn: parent
                        visible: collectionList.count === 0
                        text: "No collections"
                        color: theme.textSecondary
                        font.pixelSize: 11
                    }
                }
                TreeView {
                    id: libraryTree
                    objectName: "libraryTree"
                    visible: libraryScopeBar.mode === "sources"
                    enabled: libraryScopeBar.mode === "sources"
                    anchors.fill: parent
                    model: libraryTreeModel
                    clip: true
                    focus: libraryScopeBar.mode === "sources"
                    activeFocusOnTab: libraryScopeBar.mode === "sources"
                    boundsBehavior: Flickable.StopAtBounds
                    delegate: TreeViewDelegate {
                        id: libraryDelegate
                        implicitHeight: 34
                        indentation: 16
                        background: Rectangle {
                            color: libraryInteraction.selectedLibraryNodeId === model.nodeId ? theme.selectionSurface : "transparent"
                            border.color: libraryInteraction.selectedLibraryNodeId === model.nodeId ? theme.actionActive : "transparent"
                        }
                        contentItem: Item {
                            implicitHeight: 34
                            implicitWidth: libraryTree.width
                            property bool dropHover: false
                            TapHandler {
                                onTapped: {
                                    if (model.error) {
                                        libraryInteraction.retryLibraryNode(model.parentNodeId)
                                    } else if (model.selectable) {
                                        libraryScopeBar.mode = "sources"
                                        libraryTree.forceActiveFocus()
                                        libraryInteraction.selectLibraryNode(model.nodeId)
                                    }
                                }
                            }
                            DropArea {
                                anchors.fill: parent
                                keys: ["text/uri-list"]
                                onEntered: function(drag) {
                                    if (libraryInteraction.canAcceptSampleDrop(model.nodeId)) {
                                        drag.accept(Qt.CopyAction)
                                        parent.dropHover = true
                                    } else {
                                        drag.accepted = false
                                        parent.dropHover = false
                                    }
                                }
                                onExited: parent.dropHover = false
                                onDropped: function(drop) {
                                    parent.dropHover = false
                                    var urls = []
                                    for (var i = 0; i < drop.urls.length; i++)
                                        urls.push(drop.urls[i].toString())
                                    libraryInteraction.importDroppedUrls(model.nodeId, urls)
                                }
                            }
                            Rectangle {
                                anchors.fill: parent
                                visible: parent.dropHover
                                color: theme.selectionSurface
                                opacity: 0.55
                                z: -1
                            }
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 4
                                anchors.rightMargin: 8
                                Label {
                                    Layout.fillWidth: true
                                    text: model.loading ? "Loading…" : model.display
                                    color: model.availability === "offline" ? theme.textDisabled : theme.textPrimary
                                    opacity: model.error ? 0.72 : 1.0
                                    elide: Text.ElideRight
                                    font.pixelSize: 14
                                }
                                Label {
                                    visible: model.error
                                    text: "Retry"
                                    color: theme.textSecondary
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
        }
        // #742 geometry: libraryRevealAffordance is an overlay sibling of workspaceRow
        // (not a Row child). Horizontal anchors on Row-managed children disable the
        // Row positioner and collapse all pane x origins to 0.
        Item {
            id: handleAfterLibrary
            objectName: "elasticHandleAfterLibrary"
            visible: window.interaction.hasActiveSource && window.interaction.libraryRevealed
            width: visible ? layoutModel.handleWidth : 0
            height: parent.height
            Rectangle {
                anchors.horizontalCenter: parent.horizontalCenter
                width: 1
                height: parent.height
                color: theme.dividerDefault
            }
            MouseArea {
                // Wider hit target than the 6-DIP layout charge (contract).
                anchors.fill: parent
                anchors.leftMargin: -5
                anchors.rightMargin: -5
                cursorShape: Qt.SizeHorCursor
                property real lastGlobalX: 0
                onPressed: function(mouse) {
                    lastGlobalX = mapToItem(null, mouse.x, 0).x
                }
                onPositionChanged: function(mouse) {
                    if (!pressed)
                        return
                    var globalX = mapToItem(null, mouse.x, 0).x
                    layoutModel.applyDrag("library", globalX - lastGlobalX)
                    lastGlobalX = globalX
                }
                onReleased: layoutModel.endDrag()
            }
        }
        Rectangle {
            id: calmCanvas
            objectName: "calmCanvas"
            visible: !window.interaction.hasActiveSource
                     && window.screenData.analysisStatus !== "scanning"
                     && window.screenData.analysisStatus !== "analyzing"
                     && window.screenData.analysisStatus !== "error"
            width: visible ? Math.max(0, parent.width - libraryPane.width) : 0
            height: parent.height
            // Dark surface hierarchy: main workspace solid fill (not pure-black PNG bleed).
            // Background Image remains under panels; calm canvas paints Theme workspace only.
            color: theme.surfaceRoot
            ColumnLayout {
                anchors.centerIn: parent
                spacing: 10
                // #725 Owner Visual: primary First View CTA — "Add Source" above large +.
                // Branding stays in the header only (not Calm Canvas).
                Label {
                    objectName: "calmCanvasAddSourceLabel"
                    text: "Add Source"
                    color: theme.textSecondary
                    font.pixelSize: 15
                    horizontalAlignment: Text.AlignHCenter
                    Layout.alignment: Qt.AlignHCenter
                }
                Button {
                    id: calmCanvasAddSource
                    objectName: "calmCanvasAddSource"
                    text: "+"
                    flat: true
                    implicitWidth: 96
                    implicitHeight: 96
                    font.pixelSize: 64
                    Layout.alignment: Qt.AlignHCenter
                    Accessible.name: "Add Source"
                    ToolTip.visible: hovered
                    ToolTip.delay: 350
                    ToolTip.text: "Add Source"
                    onHoveredChanged: {
                        if (hovered)
                            contextHintState.reportHover("library.add_source")
                        else
                            contextHintState.clearHover("library.add_source")
                    }
                    onActiveFocusChanged: {
                        if (activeFocus)
                            contextHintState.reportFocus("library.add_source")
                        else
                            contextHintState.clearFocus("library.add_source")
                    }
                    contentItem: Item {
                        // Thin geometric plus — text "+" glyphs stay too heavy at this size.
                        readonly property int stroke: 2
                        readonly property int arm: Math.round(Math.min(width, height) * 0.38)
                        Rectangle {
                            anchors.centerIn: parent
                            width: parent.arm
                            height: parent.stroke
                            radius: 1
                            color: calmCanvasAddSource.hovered ? theme.textPrimary : theme.textSecondary
                        }
                        Rectangle {
                            anchors.centerIn: parent
                            width: parent.stroke
                            height: parent.arm
                            radius: 1
                            color: calmCanvasAddSource.hovered ? theme.textPrimary : theme.textSecondary
                        }
                    }
                    background: Rectangle {
                        radius: 10
                        color: calmCanvasAddSource.hovered ? theme.surfaceElevated : "transparent"
                        border.color: calmCanvasAddSource.hovered ? theme.borderSubtle : "transparent"
                        border.width: 1
                    }
                    onClicked: addSourceDialog.open()
                }
            }
        }
        Rectangle {
            // #744 analysis loading experience — deep blocking surface; real AnalysisUiState only.
            id: analysisWorkingSurface
            objectName: "analysisWorkingSurface"
            visible: !window.interaction.hasActiveSource
                     && (window.screenData.analysisStatus === "scanning"
                         || window.screenData.analysisStatus === "analyzing"
                         || window.screenData.analysisStatus === "error")
            width: visible ? Math.max(0, parent.width - libraryPane.width) : 0
            height: parent.height
            // Deep Sample-Brain working surface (no bright dialog chrome).
            // Solid theme fill only — Screen-1 background contract forbids
            // ambient fill transitions in QML_SOURCE.
            color: theme.surfaceRoot

            // Input ownership: blocker under status/progress/cancel (z below card).
            MouseArea {
                id: analysisWorkspaceBlocker
                objectName: "analysisWorkspaceBlocker"
                anchors.fill: parent
                z: 0
                acceptedButtons: Qt.AllButtons
                hoverEnabled: true
                onPressed: function(mouse) { mouse.accepted = true }
                onClicked: function(mouse) { mouse.accepted = true }
                onWheel: function(wheel) { wheel.accepted = true }
            }

            Rectangle {
                id: analysisStatusCard
                objectName: "analysisStatusCard"
                z: 1
                anchors.centerIn: parent
                width: Math.min(440, parent.width - 64)
                height: analysisStatusColumn.implicitHeight + 48
                radius: 10
                color: theme.surfacePanel
                border.color: theme.borderSubtle
                border.width: 1

                ColumnLayout {
                    id: analysisStatusColumn
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.margins: 24
                    spacing: 14

                    // #786 Brand motion layer — visualizes Python projection only.
                    Item {
                        id: brandMotionLayer
                        objectName: "brandMotionLayer"
                        Layout.alignment: Qt.AlignHCenter
                        Layout.preferredWidth: 96
                        Layout.preferredHeight: 96
                        property bool reducedMotion: window.screenData.brandReducedMotion
                        property bool staticFallback: window.screenData.brandStaticFallback
                        property bool motionActive: window.screenData.brandMotionActive
                        property string motionMode: window.screenData.brandMotionMode
                        property bool analysisBusy: window.screenData.analysisStatus === "scanning"
                                                    || window.screenData.analysisStatus === "analyzing"
                        property bool allowOrganicMotion: motionActive && !staticFallback && !reducedMotion
                                                          && analysisBusy && !window.screenData.brandStale
                        property bool allowReducedMotion: motionActive && reducedMotion && !staticFallback
                                                          && analysisBusy && !window.screenData.brandStale

                        Image {
                            id: analysisBrandBrain
                            objectName: "analysisBrandBrain"
                            anchors.centerIn: parent
                            width: 88
                            height: 88
                            source: window.screenData.brandBrainUrl
                            fillMode: Image.PreserveAspectFit
                            // Static fallback remains clearly visible.
                            opacity: brandMotionLayer.staticFallback ? 1.0
                                     : (brandMotionLayer.allowOrganicMotion ? brainBreathe.opacityValue : 0.92)
                            scale: brandMotionLayer.allowOrganicMotion ? brainBreathe.scaleValue : 1.0
                            Accessible.name: "Sample Brain analysis"
                        }

                        // Distinct reduced path: progress-tinted glow ring, no loop.
                        Rectangle {
                            anchors.centerIn: parent
                            width: 94
                            height: 94
                            radius: 47
                            visible: brandMotionLayer.allowReducedMotion
                            color: "transparent"
                            border.width: 2
                            border.color: theme.actionActive
                            opacity: window.screenData.brandProgressKind === "determinate"
                                     ? (0.25 + 0.55 * Math.max(0.0, Math.min(1.0, window.screenData.brandProgressRatio)))
                                     : 0.4
                        }

                        // Organic calm breathe — only while real analysis is busy + motion on.
                        QtObject {
                            id: brainBreathe
                            property real opacityValue: 0.88
                            property real scaleValue: 1.0
                        }
                        SequentialAnimation {
                            id: brandOrganicBreathe
                            running: brandMotionLayer.allowOrganicMotion
                            loops: Animation.Infinite
                            NumberAnimation {
                                target: brainBreathe
                                property: "opacityValue"
                                from: 0.82
                                to: 1.0
                                duration: 1600
                                easing.type: Easing.InOutSine
                            }
                            NumberAnimation {
                                target: brainBreathe
                                property: "opacityValue"
                                from: 1.0
                                to: 0.82
                                duration: 1600
                                easing.type: Easing.InOutSine
                            }
                        }
                        SequentialAnimation {
                            id: brandOrganicScale
                            running: brandMotionLayer.allowOrganicMotion
                            loops: Animation.Infinite
                            NumberAnimation {
                                target: brainBreathe
                                property: "scaleValue"
                                from: 0.98
                                to: 1.02
                                duration: 1800
                                easing.type: Easing.InOutSine
                            }
                            NumberAnimation {
                                target: brainBreathe
                                property: "scaleValue"
                                from: 1.02
                                to: 0.98
                                duration: 1800
                                easing.type: Easing.InOutSine
                            }
                        }
                    }

                    Label {
                        objectName: "analysisStatusLabel"
                        Layout.fillWidth: true
                        horizontalAlignment: Text.AlignHCenter
                        text: window.screenData.analysisStatus === "scanning" ? "Analysiere Quelle …" :
                              window.screenData.analysisStatus === "analyzing" ? "Analysiere " + window.screenData.analysisSource :
                              window.screenData.analysisStatus === "error" ? window.screenData.analysisError : ""
                        color: window.screenData.analysisStatus === "error" ? theme.actionActive : theme.textSecondary
                        font.pixelSize: 15
                        wrapMode: Text.Wrap
                    }

                    Label {
                        id: analysisBrandSampleName
                        objectName: "analysisBrandSampleName"
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignHCenter
                        horizontalAlignment: Text.AlignHCenter
                        visible: window.screenData.brandSampleName.length > 0
                                 && (window.screenData.analysisStatus === "scanning"
                                     || window.screenData.analysisStatus === "analyzing")
                                 && !window.screenData.brandStale
                        text: window.screenData.brandSampleName
                        color: theme.textPrimary
                        font.pixelSize: 12
                        elide: Text.ElideMiddle
                        opacity: brandMotionLayer.allowOrganicMotion ? 0.85 : 1.0
                    }

                    Label {
                        objectName: "analysisProgressCount"
                        Layout.alignment: Qt.AlignHCenter
                        visible: window.screenData.brandProgressKind === "determinate"
                                 && (window.screenData.analysisStatus === "scanning"
                                     || window.screenData.analysisStatus === "analyzing")
                        // Folder-level completed/total — not the in-flight sample ordinal.
                        text: window.screenData.analysisCurrent + " / " + window.screenData.analysisTotal + " Samples"
                        color: theme.textPrimary
                        font.pixelSize: 13
                    }

                    // Real progress only — bound to analysisCurrent/analysisTotal (no Timer).
                    Item {
                        objectName: "analysisProgressTrack"
                        Layout.alignment: Qt.AlignHCenter
                        Layout.preferredWidth: Math.min(280, parent.width)
                        Layout.preferredHeight: 6
                        visible: window.screenData.analysisStatus === "scanning"
                                 || window.screenData.analysisStatus === "analyzing"
                        Rectangle {
                            anchors.fill: parent
                            radius: 3
                            color: theme.surfaceElevated
                            border.color: theme.borderSubtle
                            border.width: 1
                        }
                        Rectangle {
                            id: analysisProgressFill
                            objectName: "analysisProgressFill"
                            anchors.left: parent.left
                            anchors.top: parent.top
                            anchors.bottom: parent.bottom
                            width: {
                                if (window.screenData.brandProgressKind === "indeterminate"
                                    || window.screenData.analysisTotal <= 0)
                                    return parent.width * 0.28
                                if (window.screenData.brandProgressKind === "none")
                                    return 0
                                var ratio = window.screenData.brandProgressRatio
                                if (ratio < 0.0)
                                    ratio = Math.min(
                                        1.0,
                                        Math.max(0.0, window.screenData.analysisCurrent / Math.max(1, window.screenData.analysisTotal))
                                    )
                                return parent.width * Math.min(1.0, Math.max(0.0, ratio))
                            }
                            radius: 3
                            color: theme.actionActive
                            opacity: window.screenData.brandProgressKind === "indeterminate"
                                     || window.screenData.analysisTotal <= 0 ? 0.45 : 0.85
                        }
                    }

                    Button {
                        id: analysisCancelButton
                        objectName: "analysisCancelButton"
                        Layout.alignment: Qt.AlignHCenter
                        visible: window.screenData.analysisStatus === "scanning"
                                 || window.screenData.analysisStatus === "analyzing"
                        text: "Cancel"
                        flat: true
                        contentItem: Text {
                            text: analysisCancelButton.text
                            color: theme.textSecondary
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            font.pixelSize: 12
                        }
                        background: Rectangle {
                            implicitWidth: 88
                            implicitHeight: 28
                            radius: 6
                            color: analysisCancelButton.hovered ? theme.surfaceElevated : "transparent"
                            border.color: analysisCancelButton.hovered ? theme.borderSubtle : "transparent"
                            border.width: 1
                        }
                        onClicked: window.screenData.cancelAnalysis()
                    }
                }
            }
        }
        Column {
            id: rightWorkspaceColumn
            objectName: "rightWorkspaceColumn"
            width: Math.max(0, parent.width - libraryPane.width - handleAfterLibrary.width)
            height: parent.height
            spacing: 0

            Row {
                id: upperWorkspaceRow
                objectName: "upperWorkspaceRow"
                width: parent.width
                readonly property bool bottomExpanded: window.channelRack.bottomRackMaterialized
                        || (window.interaction.liveKitRevealed && !window.interaction.liveKitCollapsed)
                height: bottomExpanded
                        ? parent.height * (1.0 - Math.max(window.channelRack.bottomRackHeightRatio, 0.24))
                        : Math.max(0, parent.height - window.channelRack.bottomRackHeightPx)
                spacing: 0
            Rectangle { id: browserPane; objectName: "browserPane"; visible: window.interaction.hasActiveSource && !window.interaction.browserCollapsed; width: visible ? layoutModel.browserWidth : 0; height: parent.height; color: theme.surfaceBrowser; border.color: theme.borderSubtle
                function openSampleContextMenu(index, localX, localY) {
                    window.interaction.openSampleContext(index)
                    sampleContextMenu.focusedAction = 0
                    sampleContextMenu.x = Math.max(8, Math.min(localX, Math.max(8, width - 220)))
                    sampleContextMenu.y = Math.max(8, Math.min(localY, Math.max(8, height - 96)))
                    sampleContextMenu.open()
                    sampleContextMenu.forceActiveFocus()
                }
                Popup {
                    id: sampleContextMenu
                    objectName: "sampleContextMenu"
                    // Theme: theme.selectionSurface / theme.textPrimary / theme.focusRing
                    property string actionAddLabel: "Add to Kit"
                    property string actionHarmonicLabel: "Harmonic Matches"
                    width: 208
                    padding: 6
                    modal: false
                    focus: true
                    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
                    property int focusedAction: 0
                    background: Rectangle {
                        color: theme.selectionSurface
                        border.color: theme.selectionBorder
                        border.width: 1
                        radius: 6
                    }
                    onClosed: {
                        window.interaction.closeSampleContext()
                        browser.forceActiveFocus()
                    }
                    Connections {
                        target: window.interaction
                        function onSampleContextClosed() {
                            if (sampleContextMenu.visible)
                                sampleContextMenu.close()
                        }
                    }
                    function activateFocused() {
                        if (focusedAction === 0)
                            window.interaction.contextAddToKit()
                        else
                            window.interaction.contextHarmonicMatches()
                        close()
                    }
                    Column {
                        width: parent.width
                        spacing: 2
                        Rectangle {
                            id: contextAddToKitItem
                            width: parent.width
                            height: 32
                            radius: 4
                            color: sampleContextMenu.focusedAction === 0 || contextAddHover.containsMouse ? theme.surfaceElevated : "transparent"
                            border.width: sampleContextMenu.focusedAction === 0 ? 1 : 0
                            border.color: theme.focusRing
                            // Invokable control for AT / Windows UIA (InvokePattern).
                            Accessible.role: Accessible.Button
                            Accessible.name: sampleContextMenu.actionAddLabel
                            Accessible.onPressAction: {
                                sampleContextMenu.focusedAction = 0
                                sampleContextMenu.activateFocused()
                            }
                            Label {
                                anchors.fill: parent
                                anchors.leftMargin: 10
                                anchors.rightMargin: 10
                                text: sampleContextMenu.actionAddLabel
                                color: theme.textPrimary
                                verticalAlignment: Text.AlignVCenter
                                font.pixelSize: window.textBody
                                Accessible.ignored: true
                            }
                            MouseArea {
                                id: contextAddHover
                                anchors.fill: parent
                                hoverEnabled: true
                                onClicked: {
                                    sampleContextMenu.focusedAction = 0
                                    sampleContextMenu.activateFocused()
                                }
                                onEntered: sampleContextMenu.focusedAction = 0
                            }
                        }
                        Rectangle {
                            width: parent.width
                            height: 1
                            color: theme.dividerDefault
                            opacity: 0.7
                            Accessible.ignored: true
                        }
                        Rectangle {
                            id: contextHarmonicItem
                            objectName: "contextHarmonicItem"
                            width: parent.width
                            height: 32
                            radius: 4
                            color: sampleContextMenu.focusedAction === 1 || contextHarmonicHover.containsMouse ? theme.surfaceElevated : "transparent"
                            border.width: sampleContextMenu.focusedAction === 1 ? 1 : 0
                            border.color: theme.focusRing
                            // #843 sole producer entry must be UIA-invokable after header button removal.
                            Accessible.role: Accessible.Button
                            Accessible.name: sampleContextMenu.actionHarmonicLabel
                            Accessible.onPressAction: {
                                sampleContextMenu.focusedAction = 1
                                sampleContextMenu.activateFocused()
                            }
                            Label {
                                anchors.fill: parent
                                anchors.leftMargin: 10
                                anchors.rightMargin: 10
                                text: sampleContextMenu.actionHarmonicLabel
                                color: theme.textSecondary
                                verticalAlignment: Text.AlignVCenter
                                font.pixelSize: window.textBody
                                Accessible.ignored: true
                            }
                            MouseArea {
                                id: contextHarmonicHover
                                anchors.fill: parent
                                hoverEnabled: true
                                onClicked: {
                                    sampleContextMenu.focusedAction = 1
                                    sampleContextMenu.activateFocused()
                                }
                                onEntered: sampleContextMenu.focusedAction = 1
                            }
                        }
                    }
                    Keys.onPressed: function(event) {
                        if (event.key === Qt.Key_Down) {
                            focusedAction = Math.min(1, focusedAction + 1)
                            event.accepted = true
                        } else if (event.key === Qt.Key_Up) {
                            focusedAction = Math.max(0, focusedAction - 1)
                            event.accepted = true
                        } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
                            activateFocused()
                            event.accepted = true
                        } else if (event.key === Qt.Key_Escape) {
                            close()
                            event.accepted = true
                        }
                    }
                }
                // #845 OPEN collapse handle — left mid-edge of Browser so it does not
                // share the right residual with harmonyCollapseAffordance.
                Item {
                    id: browserCollapseHandle
                    objectName: "browserCollapseHandle"
                    z: 30
                    width: 14
                    height: 56
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    visible: browserPane.visible
                    activeFocusOnTab: visible
                    Accessible.role: Accessible.Button
                    Accessible.name: "Collapse Browser"
                    Accessible.onPressAction: window.interaction.toggleBrowserCollapsed()
                    property bool hovered: false
                    Rectangle {
                        anchors.fill: parent
                        radius: 3
                        color: browserCollapseHandle.hovered ? theme.surfaceElevated : "transparent"
                        opacity: browserCollapseHandle.hovered ? 0.92 : 0.45
                        border.width: browserCollapseHandle.activeFocus ? 1 : 0
                        border.color: theme.selectionBorder
                    }
                    Text {
                        anchors.centerIn: parent
                        text: "‹"
                        color: theme.textSecondary
                        opacity: browserCollapseHandle.hovered || browserCollapseHandle.activeFocus ? 1.0 : 0.55
                        font.pixelSize: 14
                        Accessible.ignored: true
                    }
                    MouseArea {
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onEntered: browserCollapseHandle.hovered = true
                        onExited: browserCollapseHandle.hovered = false
                        onClicked: {
                            browserCollapseHandle.forceActiveFocus()
                            window.interaction.toggleBrowserCollapsed()
                        }
                    }
                    Keys.onReturnPressed: window.interaction.toggleBrowserCollapsed()
                    Keys.onEnterPressed: window.interaction.toggleBrowserCollapsed()
                    Keys.onPressed: function(event) {
                        if (event.key === Qt.Key_Space) {
                            window.interaction.toggleBrowserCollapsed()
                            event.accepted = true
                        }
                    }
                }
                // #692 owner-visual repair: preserve required scan columns when the
                // workspace is narrow. Type is optional; sample identity is not.
                property bool browserNarrowColumns: width < 700
                // #780 Browser column resize — browserPane is the SINGLE owner of
                // column width truth. Runtime overrides (-1 = responsive default)
                // fold into the same effectiveBrowser* bindings the header row and
                // the list delegate already share, so there is no competing
                // geometry truth. Independent of panel resize (layoutModel).
                readonly property int browserWaveformMax: 360
                readonly property int browserMetaColumnMin: 40
                readonly property int browserMetaColumnMax: 96
                readonly property int browserFavoriteColumnMin: 24
                readonly property int browserFavoriteColumnMax: 48
                readonly property int browserLengthColumnMin: 52
                readonly property int browserLengthColumnMax: 120
                readonly property int browserColumnHandlePadding: 6
                property int waveformUserWidth: -1
                property int metaUserWidth: -1
                property int favoriteUserWidth: -1
                property int lengthUserWidth: -1
                function _clampColumn(value, lo, hi) { return Math.max(lo, Math.min(hi, Math.round(value))) }
                // Wide mode: user override wins when set (>= 0). Narrow mode (#692):
                // always keep responsive defaults so a prior wide-mode drag cannot
                // defeat the compact column budget when the pane shrinks below 700.
                function _resolveColumn(user, dflt, lo, hi) { return _clampColumn((browserNarrowColumns || user < 0) ? dflt : user, lo, hi) }
                function resizeColumn(role, deltaPx) {
                    if (role === "waveform")
                        waveformUserWidth = _clampColumn(effectiveBrowserWaveformWidth + deltaPx, window.browserWaveformMin, browserWaveformMax)
                    else if (role === "meta")
                        metaUserWidth = _clampColumn(effectiveBrowserMetaColumnWidth + deltaPx, browserMetaColumnMin, browserMetaColumnMax)
                    else if (role === "favorite")
                        favoriteUserWidth = _clampColumn(effectiveBrowserFavoriteColumnWidth + deltaPx, browserFavoriteColumnMin, browserFavoriteColumnMax)
                    else if (role === "length")
                        lengthUserWidth = _clampColumn(effectiveBrowserLengthColumnWidth + deltaPx, browserLengthColumnMin, browserLengthColumnMax)
                }
                property int effectiveBrowserWaveformWidth: _resolveColumn(waveformUserWidth, browserNarrowColumns ? window.browserWaveformMin : window.browserWaveformWidth, window.browserWaveformMin, browserWaveformMax)
                property int effectiveBrowserMetaColumnWidth: _resolveColumn(metaUserWidth, browserNarrowColumns ? browserMetaColumnMin : window.browserMetaColumnWidth, browserMetaColumnMin, browserMetaColumnMax)
                property int effectiveBrowserFavoriteColumnWidth: _resolveColumn(favoriteUserWidth, browserNarrowColumns ? browserFavoriteColumnMin : window.browserFavoriteColumnWidth, browserFavoriteColumnMin, browserFavoriteColumnMax)
                property int effectiveBrowserLengthColumnWidth: _resolveColumn(lengthUserWidth, browserNarrowColumns ? browserLengthColumnMin : window.browserLengthColumnWidth, browserLengthColumnMin, browserLengthColumnMax)
                ColumnLayout { anchors.fill: parent; anchors.margins: 18; spacing: 10
                    RowLayout { Layout.fillWidth: true
                        ColumnLayout { Layout.fillWidth: true; spacing: 2
                            Label { text: window.screenData.browserContext; color: theme.textPrimary; font.pixelSize: window.textTitle; font.bold: true }
                            Label { text: window.screenData.browserRows.length + " samples"; color: theme.textSecondary; font.pixelSize: window.textCaption }
                            Label { visible: window.screenData.errorMessage.length > 0; text: window.screenData.errorMessage; color: theme.actionActive; font.pixelSize: 11 }
                        }
                        Item { Layout.fillWidth: true }
                        TextField {
                            // #895: slim dark-native search — quiet fill, low-contrast border, calm placeholder.
                            objectName: "browserSearch"
                            placeholderText: "Search samples"
                            placeholderTextColor: theme.textSecondary
                            color: theme.textPrimary
                            selectedTextColor: theme.textOnAction
                            selectionColor: theme.actionActive
                            Layout.preferredWidth: 230
                            Layout.minimumWidth: 120
                            Layout.preferredHeight: 28
                            font.pixelSize: 12
                            leftPadding: 10
                            rightPadding: 10
                            topPadding: 4
                            bottomPadding: 4
                            background: Rectangle {
                                radius: 4
                                border.width: 1
                                border.color: parent.activeFocus ? theme.focusRing : theme.borderSubtle
                                color: parent.activeFocus ? theme.hoverSurface : (parent.hovered ? theme.hoverSurface : "transparent")
                            }
                            onTextChanged: window.interaction.setBrowserSearch(text)
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
                            color: window.screenData.analysisStatus === "error" ? theme.actionActive : theme.textSecondary
                            font.pixelSize: 11
                        }
                        Label {
                            visible: window.screenData.analysisTotal > 0
                            text: window.screenData.analysisCurrent + " / " + window.screenData.analysisTotal + " Samples"
                            color: theme.textPrimary
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
                    Item {
                        id: browserColumnHeaderHost
                        Layout.fillWidth: true
                        Layout.preferredHeight: browserColumnHeaderRow.implicitHeight
                        // #846: RowLayout owns shared column widths; resize surfaces are
                        // edge children of each header cell (valid Qt anchors; not new
                        // RowLayout columns / preferredWidth consumers).
                        RowLayout {
                            id: browserColumnHeaderRow
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.leftMargin: window.densityHorizontalInset
                            anchors.rightMargin: window.densityHorizontalInset
                            spacing: window.densityRowSpacing
                            Item {
                                id: browserHeaderWaveform
                                Layout.preferredWidth: browserPane.effectiveBrowserWaveformWidth
                                Layout.minimumWidth: browserPane.effectiveBrowserWaveformWidth
                                Layout.fillHeight: true
                                // #846 ephemeral overlay: MouseArea root keeps resizeColumn +
                                // theme tokens inside frozen assertion windows.
                                MouseArea { id: browserColumnResizeWaveform; objectName: "browserColumnResize_waveform"; property color _h: theme.surfaceElevated; property color _f: theme.focusRing; property bool handleVisible: containsMouse || pressed || activeFocus; z: 8; width: 2+2*browserPane.browserColumnHandlePadding; height: Math.max(18, parent.height); anchors.right: parent.right; anchors.rightMargin: -browserPane.browserColumnHandlePadding; anchors.verticalCenter: parent.verticalCenter; hoverEnabled: true; preventStealing: true; cursorShape: Qt.SizeHorCursor; activeFocusOnTab: true; Accessible.name: "Resize waveform"; property real lastX: 0; onPressed: function(m) { lastX = mapToItem(null, m.x, 0).x; m.accepted = true }; onPositionChanged: function(m) { if (!pressed) return; var g = mapToItem(null, m.x, 0).x; browserPane.resizeColumn("waveform", g - lastX); lastX = g }; Keys.onUpPressed: function(e) { browser.forceActiveFocus(); window.interaction.navigateBrowser(-1); e.accepted = true }; Keys.onDownPressed: function(e) { browser.forceActiveFocus(); window.interaction.navigateBrowser(1); e.accepted = true }; Keys.onEscapePressed: function(e) { browser.forceActiveFocus(); window.interaction.stopPreview(); e.accepted = true }; Rectangle { anchors.centerIn: parent; width: 2; height: parent.height - 4; radius: 1; color: parent.activeFocus ? parent._f : parent._h; opacity: parent.handleVisible ? 0.95 : 0; border.width: parent.activeFocus ? 1 : 0; border.color: parent._f } }
                            }
                            Label { text: "SAMPLE NAME"; color: theme.textSecondary; Layout.fillWidth: true; Layout.minimumWidth: browserPane.browserNarrowColumns ? 96 : 120; font.pixelSize: window.textCaption; font.bold: true }
                            Label {
                                id: browserHeaderBpm
                                text: "BPM"
                                color: theme.textSecondary
                                Layout.preferredWidth: browserPane.effectiveBrowserMetaColumnWidth
                                horizontalAlignment: Text.AlignRight
                                font.pixelSize: window.textCaption
                                font.bold: true
                                MouseArea { id: browserColumnResizeMeta; objectName: "browserColumnResize_meta"; property color _h: theme.surfaceElevated; property color _f: theme.focusRing; property bool handleVisible: containsMouse || pressed || activeFocus; z: 8; width: 2+2*browserPane.browserColumnHandlePadding; height: Math.max(18, parent.height); anchors.right: parent.right; anchors.rightMargin: -browserPane.browserColumnHandlePadding; anchors.verticalCenter: parent.verticalCenter; hoverEnabled: true; preventStealing: true; cursorShape: Qt.SizeHorCursor; activeFocusOnTab: true; Accessible.name: "Resize BPM"; property real lastX: 0; onPressed: function(m) { lastX = mapToItem(null, m.x, 0).x; m.accepted = true }; onPositionChanged: function(m) { if (!pressed) return; var g = mapToItem(null, m.x, 0).x; browserPane.resizeColumn("meta", g - lastX); lastX = g }; Keys.onUpPressed: function(e) { browser.forceActiveFocus(); window.interaction.navigateBrowser(-1); e.accepted = true }; Keys.onDownPressed: function(e) { browser.forceActiveFocus(); window.interaction.navigateBrowser(1); e.accepted = true }; Keys.onEscapePressed: function(e) { browser.forceActiveFocus(); window.interaction.stopPreview(); e.accepted = true }; Rectangle { anchors.centerIn: parent; width: 2; height: parent.height - 4; radius: 1; color: parent.activeFocus ? parent._f : parent._h; opacity: parent.handleVisible ? 0.95 : 0; border.width: parent.activeFocus ? 1 : 0; border.color: parent._f } }
                            }
                            Label {
                                id: browserHeaderFavorite
                                text: "FAV"
                                color: theme.textSecondary
                                Layout.preferredWidth: browserPane.effectiveBrowserFavoriteColumnWidth
                                horizontalAlignment: Text.AlignHCenter
                                font.pixelSize: window.textCaption
                                font.bold: true
                                MouseArea { id: browserColumnResizeFavorite; objectName: "browserColumnResize_favorite"; property color _h: theme.surfaceElevated; property color _f: theme.focusRing; property bool handleVisible: containsMouse || pressed || activeFocus; z: 8; width: 2+2*browserPane.browserColumnHandlePadding; height: Math.max(18, parent.height); anchors.right: parent.right; anchors.rightMargin: -browserPane.browserColumnHandlePadding; anchors.verticalCenter: parent.verticalCenter; hoverEnabled: true; preventStealing: true; cursorShape: Qt.SizeHorCursor; activeFocusOnTab: true; Accessible.name: "Resize favorite"; property real lastX: 0; onPressed: function(m) { lastX = mapToItem(null, m.x, 0).x; m.accepted = true }; onPositionChanged: function(m) { if (!pressed) return; var g = mapToItem(null, m.x, 0).x; browserPane.resizeColumn("favorite", g - lastX); lastX = g }; Keys.onUpPressed: function(e) { browser.forceActiveFocus(); window.interaction.navigateBrowser(-1); e.accepted = true }; Keys.onDownPressed: function(e) { browser.forceActiveFocus(); window.interaction.navigateBrowser(1); e.accepted = true }; Keys.onEscapePressed: function(e) { browser.forceActiveFocus(); window.interaction.stopPreview(); e.accepted = true }; Rectangle { anchors.centerIn: parent; width: 2; height: parent.height - 4; radius: 1; color: parent.activeFocus ? parent._f : parent._h; opacity: parent.handleVisible ? 0.95 : 0; border.width: parent.activeFocus ? 1 : 0; border.color: parent._f } }
                            }
                            Label { text: "KEY"; color: theme.textSecondary; Layout.preferredWidth: browserPane.effectiveBrowserMetaColumnWidth; horizontalAlignment: Text.AlignRight; font.pixelSize: window.textCaption; font.bold: true }
                            Label {
                                id: browserHeaderLength
                                objectName: "browserColumnHeader_length"
                                text: "LENGTH"
                                color: theme.textSecondary
                                Layout.preferredWidth: browserPane.effectiveBrowserLengthColumnWidth
                                horizontalAlignment: Text.AlignRight
                                font.pixelSize: window.textCaption
                                font.bold: true
                                MouseArea { id: browserColumnResizeLength; objectName: "browserColumnResize_length"; property color _h: theme.surfaceElevated; property color _f: theme.focusRing; property bool handleVisible: containsMouse || pressed || activeFocus; z: 8; width: 2+2*browserPane.browserColumnHandlePadding; height: Math.max(18, parent.height); anchors.right: parent.right; anchors.rightMargin: -browserPane.browserColumnHandlePadding; anchors.verticalCenter: parent.verticalCenter; hoverEnabled: true; preventStealing: true; cursorShape: Qt.SizeHorCursor; activeFocusOnTab: true; Accessible.name: "Resize length"; property real lastX: 0; onPressed: function(m) { lastX = mapToItem(null, m.x, 0).x; m.accepted = true }; onPositionChanged: function(m) { if (!pressed) return; var g = mapToItem(null, m.x, 0).x; browserPane.resizeColumn("length", g - lastX); lastX = g }; Keys.onUpPressed: function(e) { browser.forceActiveFocus(); window.interaction.navigateBrowser(-1); e.accepted = true }; Keys.onDownPressed: function(e) { browser.forceActiveFocus(); window.interaction.navigateBrowser(1); e.accepted = true }; Keys.onEscapePressed: function(e) { browser.forceActiveFocus(); window.interaction.stopPreview(); e.accepted = true }; Rectangle { anchors.centerIn: parent; width: 2; height: parent.height - 4; radius: 1; color: parent.activeFocus ? parent._f : parent._h; opacity: parent.handleVisible ? 0.95 : 0; border.width: parent.activeFocus ? 1 : 0; border.color: parent._f } }
                            }
                            // Issue 850: Type header shares visibility + width with the Type value cell so
                            // Length never visually hosts Type labels under a shifted trailing geometry.
                            Label { objectName: "browserColumnHeader_type"; visible: !browserPane.browserNarrowColumns; text: "TYPE"; color: theme.textSecondary; Layout.preferredWidth: window.browserTypeColumnWidth; Layout.maximumWidth: 88; horizontalAlignment: Text.AlignLeft; font.pixelSize: window.textCaption; font.bold: true }
                        }
                    }
                    // All Samples list-viewport reuses Clean-Start canvas fill (theme.surfaceRoot).
                    // Outer browserPane chrome stays surfaceBrowser; Library/Harmony/Live Kit unchanged.
                    Rectangle {
                        id: browserListViewport
                        objectName: "browserListViewport"
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        color: theme.surfaceRoot
                        ListView { id: browser; objectName: "browserList"; anchors.fill: parent; model: window.screenData.browserRows; clip: true; reuseItems: true; focus: true; property int rowHeight: window.densityRowHeight; implicitHeight: window.densityRowHeight * 2
                        function requestVisibleWaveforms() {
                            if (rowHeight <= 0 || height <= 0)
                                return
                            window.interaction.requestWaveforms(
                                Math.max(0, Math.floor(contentY / rowHeight)),
                                Math.ceil(height / rowHeight) + 2
                            )
                        }
                        Component.onCompleted: Qt.callLater(requestVisibleWaveforms)
                        onContentYChanged: requestVisibleWaveforms()
                        onHeightChanged: requestVisibleWaveforms()
                        onModelChanged: Qt.callLater(requestVisibleWaveforms)
                        Keys.onPressed: function(event) {
                            if (event.key === Qt.Key_Down) { window.interaction.navigateBrowser(1); event.accepted = true }
                            else if (event.key === Qt.Key_Up) { window.interaction.navigateBrowser(-1); event.accepted = true }
                            else if (event.key === Qt.Key_Escape) { window.interaction.stopPreview(); event.accepted = true }
                            else if (event.key === Qt.Key_Menu || (event.key === Qt.Key_F10 && (event.modifiers & Qt.ShiftModifier))) {
                                if (window.screenData.selectedBrowserIndex >= 0) {
                                    browserPane.openSampleContextMenu(window.screenData.selectedBrowserIndex, browser.width * 0.35, browser.mapToItem(browserPane, 0, browser.height * 0.25).y)
                                    event.accepted = true
                                }
                            }
                        }
                        delegate: Rectangle { id: browserRow; width: browser.width; height: browser.rowHeight; color: index === window.screenData.selectedBrowserIndex ? theme.selectionSurface : (rowSelection.containsMouse ? theme.surfaceElevated : "transparent"); border.width: index === window.screenData.selectedBrowserIndex ? 1 : 0; border.color: theme.selectionBorder
                            Component.onCompleted: window.browserDelegateCreations += 1
                            property string outboundUrl: window.interaction.outboundFileUrl(index)
                            Drag.active: rowSelection.dragActive
                            Drag.dragType: Drag.Automatic
                            Drag.supportedActions: Qt.CopyAction
                            Drag.mimeData: browserRow.outboundUrl.length > 0 ? { "text/uri-list": browserRow.outboundUrl } : {}
                            Drag.onDragFinished: rowSelection.dragActive = false
                            MouseArea {
                                id: rowSelection
                                anchors.fill: parent
                                z: 0
                                hoverEnabled: true
                                acceptedButtons: Qt.LeftButton | Qt.RightButton
                                property bool dragActive: false
                                property real pressX: 0
                                property real pressY: 0
                                onPressed: function(mouse) {
                                    if (mouse.button === Qt.RightButton)
                                        return
                                    dragActive = false
                                    pressX = mouse.x
                                    pressY = mouse.y
                                    browserRow.outboundUrl = window.interaction.outboundFileUrl(index)
                                }
                                onPositionChanged: function(mouse) {
                                    if (!pressed || dragActive)
                                        return
                                    if (browserRow.outboundUrl.length === 0)
                                        return
                                    if (Math.abs(mouse.x - pressX) < 8 && Math.abs(mouse.y - pressY) < 8)
                                        return
                                    dragActive = true
                                }
                                onClicked: function(mouse) {
                                    if (mouse.button === Qt.RightButton) {
                                        var local = mapToItem(browserPane, mouse.x, mouse.y)
                                        browserPane.openSampleContextMenu(index, local.x, local.y)
                                        return
                                    }
                                    if (dragActive)
                                        return
                                    browser.forceActiveFocus()
                                    window.interaction.selectRow(index)
                                }
                            }
                            RowLayout { id: rowBody; anchors.fill: parent; anchors.leftMargin: window.densityHorizontalInset; anchors.rightMargin: window.densityHorizontalInset; anchors.topMargin: window.densityVerticalInset; anchors.bottomMargin: window.densityVerticalInset; spacing: window.densityRowSpacing; z: 1
                                Item { id: waveformSurface; objectName: "browserWaveformSurface"; Layout.preferredWidth: browserPane.effectiveBrowserWaveformWidth; Layout.minimumWidth: browserPane.effectiveBrowserWaveformWidth; Layout.preferredHeight: window.densityWaveformHeight; Layout.maximumHeight: window.densityWaveformHeight
                                    Canvas { id: waveformCanvas; anchors.fill: parent; property var envelope: modelData.waveform
                                        property bool waveformSelected: index === window.screenData.selectedBrowserIndex
                                        onEnvelopeChanged: requestPaint()
                                        onWaveformSelectedChanged: requestPaint()
                                        onPaint: {
                                            var context = getContext("2d")
                                            context.clearRect(0, 0, width, height)
                                            context.strokeStyle = waveformSelected ? theme.waveformActive : theme.waveformDefault
                                            context.lineWidth = 1.2
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
                                                    var amplitude = Math.max(1, height * 0.42 * value)
                                                    context.moveTo(x, center - amplitude)
                                                    context.lineTo(x, center + amplitude)
                                                }
                                            }
                                            context.stroke()
                                        }
                                    }
                                    Rectangle {
                                        id: browserPreviewPlayhead
                                        objectName: "previewPlayhead"
                                        width: 2
                                        height: parent ? parent.height : 0
                                        color: theme.textPrimary
                                        z: 3
                                        visible: window.previewPlayheadArmed && parent
                                            && (("" + modelData.path) === ("" + window.interaction.previewPlayingPath))
                                        x: {
                                            if (!parent)
                                                return 0
                                            var span = Math.max(0, parent.width - width)
                                            return Math.round(Math.max(0, Math.min(1, window.interaction.previewProgress)) * span)
                                        }
                                    }
                                    MouseArea { anchors.fill: parent; z: 2; onClicked: { browser.forceActiveFocus(); window.interaction.previewRow(index) } }
                                }
                                Label { text: modelData.name; color: theme.textPrimary; font.pixelSize: window.textBody; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true; Layout.minimumWidth: browserPane.browserNarrowColumns ? 96 : 120; verticalAlignment: Text.AlignVCenter }
                                Label { id: bpmCell; text: modelData.bpm; color: theme.textSecondary; Layout.preferredWidth: browserPane.effectiveBrowserMetaColumnWidth; horizontalAlignment: Text.AlignRight; verticalAlignment: Text.AlignVCenter; font.pixelSize: window.textMeta }
                                Item {
                                    id: favoriteCell
                                    objectName: "browserFavoriteButton"
                                    Layout.preferredWidth: browserPane.effectiveBrowserFavoriteColumnWidth
                                    Layout.preferredHeight: Math.min(window.densityActionHitTarget, window.densityRowHeight - 2 * window.densityVerticalInset)
                                    Layout.maximumHeight: window.densityRowHeight - 2 * window.densityVerticalInset
                                    Label {
                                        anchors.fill: parent
                                        text: modelData.favorite ? "★" : "☆"
                                        color: modelData.favorite ? theme.actionActive : theme.textSecondary
                                        horizontalAlignment: Text.AlignHCenter
                                        verticalAlignment: Text.AlignVCenter
                                        font.pixelSize: window.textMeta
                                    }
                                    MouseArea {
                                        anchors.fill: parent
                                        onClicked: {
                                            browser.forceActiveFocus()
                                            window.interaction.toggleFavorite(index)
                                        }
                                    }
                                }
                                Label { id: keyCell; text: modelData.key; color: theme.textSecondary; Layout.preferredWidth: browserPane.effectiveBrowserMetaColumnWidth; horizontalAlignment: Text.AlignRight; verticalAlignment: Text.AlignVCenter; font.pixelSize: window.textMeta }
                                Label { id: lengthCell; objectName: "browserLengthCell"; text: modelData.duration; color: theme.textSecondary; Layout.preferredWidth: browserPane.effectiveBrowserLengthColumnWidth; horizontalAlignment: Text.AlignRight; verticalAlignment: Text.AlignVCenter; font.pixelSize: window.textMeta; elide: Text.ElideRight; clip: true }
                                Label { id: typeCell; objectName: "browserTypeCell"; visible: !browserPane.browserNarrowColumns; text: modelData.type; color: theme.textSecondary; font.pixelSize: window.textCaption; elide: Text.ElideRight; Layout.preferredWidth: window.browserTypeColumnWidth; Layout.maximumWidth: 88; verticalAlignment: Text.AlignVCenter }
                            }
                            // #846: permanent vertical column dividers removed. Column resize
                            // lives on header overlays; rows keep horizontal chrome only.
                            Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: window.densityDividerHeight; color: theme.dividerDefault; opacity: index === window.screenData.selectedBrowserIndex ? 0.35 : 0.8 }
                        }
                    }
                    }
                }
            }
            Item {
                id: handleAfterBrowser
                objectName: "elasticHandleAfterBrowser"
                visible: window.interaction.hasActiveSource
                         && !window.interaction.browserCollapsed
                         && window.interaction.harmonicMatchOpen
                width: visible ? layoutModel.handleWidth : 0
                height: parent.height
                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: 1
                    height: parent.height
                    color: theme.dividerDefault
                }
                MouseArea {
                    // Wider hit target than the 6-DIP layout charge. Expand into the
                    // Browser always; expand right only when Harmony occupies space.
                    anchors.fill: parent
                    anchors.leftMargin: -5
                    anchors.rightMargin: window.interaction.harmonicMatchOpen ? -5 : 0
                    cursorShape: Qt.SizeHorCursor
                    property real lastGlobalX: 0
                    onPressed: function(mouse) {
                        lastGlobalX = mapToItem(null, mouse.x, 0).x
                    }
                    onPositionChanged: function(mouse) {
                        if (!pressed)
                            return
                        var globalX = mapToItem(null, mouse.x, 0).x
                        layoutModel.applyDrag("browser", globalX - lastGlobalX)
                        lastGlobalX = globalX
                    }
                    onReleased: layoutModel.endDrag()
                }
            }
            Rectangle {
                id: harmonyPane
                objectName: "harmonyPane"
                // Stay layout-participating; width 0 when closed (model-driven).
                opacity: window.interaction.harmonicMatchOpen ? 1 : 0
                enabled: window.interaction.harmonicMatchOpen
                width: layoutModel.harmonyWidth
                height: parent.height
                color: theme.surfacePanel
                border.color: theme.borderSubtle
                // Pane-root name for UIA title evidence; keep distinct from the
                // context-menu Button so FindFirst prefers the invokable action
                // while the menu is open (browser subtree precedes this pane).
                Accessible.name: window.interaction.harmonicMatchOpen ? "Harmonic Matches" : ""
                // #845 OPEN collapse handle — pane-local; only when Matches are open.
                Item {
                    id: harmonyCollapseHandle
                    objectName: "harmonyCollapseHandle"
                    z: 30
                    width: 14
                    height: 56
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    visible: window.interaction.harmonicMatchOpen && !window.interaction.browserCollapsed
                    activeFocusOnTab: visible
                    Accessible.role: Accessible.Button
                    Accessible.name: "Collapse Harmonic Matches"
                    Accessible.onPressAction: window.activateHarmonicMatchToggle()
                    property bool hovered: false
                    Rectangle {
                        anchors.fill: parent
                        radius: 3
                        color: harmonyCollapseHandle.hovered ? theme.surfaceElevated : "transparent"
                        opacity: harmonyCollapseHandle.hovered ? 0.92 : 0.45
                        border.width: harmonyCollapseHandle.activeFocus ? 1 : 0
                        border.color: theme.selectionBorder
                    }
                    Text {
                        anchors.centerIn: parent
                        text: "‹"
                        color: theme.textSecondary
                        opacity: harmonyCollapseHandle.hovered || harmonyCollapseHandle.activeFocus ? 1.0 : 0.55
                        font.pixelSize: 14
                        Accessible.ignored: true
                    }
                    MouseArea {
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onEntered: harmonyCollapseHandle.hovered = true
                        onExited: harmonyCollapseHandle.hovered = false
                        onClicked: {
                            harmonyCollapseHandle.forceActiveFocus()
                            window.activateHarmonicMatchToggle()
                        }
                    }
                    Keys.onReturnPressed: window.activateHarmonicMatchToggle()
                    Keys.onEnterPressed: window.activateHarmonicMatchToggle()
                    Keys.onPressed: function(event) {
                        if (event.key === Qt.Key_Space) {
                            window.activateHarmonicMatchToggle()
                            event.accepted = true
                        }
                    }
                }
                property bool harmonyOpen: window.interaction.harmonicMatchOpen
                onHarmonyOpenChanged: {
                    layoutModel.syncFromInteraction()
                    if (harmonyOpen) {
                        // #843: do not auto-steal keyboard focus onto results on open.
                        // Matches remains Tab-/click-focusable; Browser keeps a sensible flow.
                        Qt.callLater(function() {
                            if (window.interaction.harmonyScrollY > 0) {
                                harmonicMatchList.contentY = window.interaction.harmonyScrollY
                            }
                            window.interaction.requestHarmonyWaveforms(
                                Math.max(0, Math.floor(harmonicMatchList.contentY / window.densityRowHeight)),
                                Math.ceil(harmonicMatchList.height / window.densityRowHeight) + 2
                            )
                        })
                    } else {
                        browser.forceActiveFocus()
                    }
                }
                ColumnLayout { anchors.fill: parent; anchors.margins: 14
                    Label {
                        text: "Harmonic Matches"
                        color: theme.textPrimary
                        font.pixelSize: 18
                        font.bold: true
                        Accessible.ignored: true
                    }
                    Label { text: window.screenData.harmonyAnchor; color: theme.textSecondary; font.pixelSize: 12 }
                    Label { text: window.screenData.harmonyStatus; color: theme.textSecondary; font.pixelSize: 11; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    ListView { id: harmonicMatchList; objectName: "harmonicMatchList"; Layout.fillWidth: true; Layout.fillHeight: true; model: window.screenData.harmonyRows; clip: true; reuseItems: true; focus: false; activeFocusOnTab: window.interaction.harmonicMatchOpen
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
                                Math.max(0, Math.floor(contentY / window.densityRowHeight)),
                                Math.ceil(height / window.densityRowHeight) + 2
                            )
                        }
                        onHeightChanged: {
                            if (visible) {
                                window.interaction.requestHarmonyWaveforms(
                                    Math.max(0, Math.floor(contentY / window.densityRowHeight)),
                                    Math.ceil(height / window.densityRowHeight) + 2
                                )
                            }
                        }
                        // #895: harmonic rows share Browser language — selected/hover surfaces, divider only.
                        delegate: Rectangle {
                            id: harmonyRow
                            width: parent.width
                            height: window.densityRowHeight
                            color: index === window.interaction.selectedHarmonyIndex ? theme.selectionSurface
                                   : (harmonyRowHover.containsMouse ? theme.surfaceElevated : "transparent")
                            border.width: index === window.interaction.selectedHarmonyIndex ? 1 : 0
                            border.color: index === window.interaction.selectedHarmonyIndex ? theme.selectionBorder : "transparent"
                            MouseArea {
                                id: harmonyRowHover
                                anchors.fill: parent
                                z: 0
                                hoverEnabled: true
                                onClicked: { harmonicMatchList.forceActiveFocus(); window.interaction.selectHarmonyRow(index) }
                            }
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: window.densityHorizontalInset
                                anchors.rightMargin: window.densityHorizontalInset
                                anchors.topMargin: window.densityVerticalInset
                                anchors.bottomMargin: window.densityVerticalInset
                                spacing: window.densityRowSpacing
                                z: 1
                                Item {
                                    Layout.preferredWidth: window.harmonicWaveformWidth
                                    Layout.preferredHeight: window.densityWaveformHeight
                                    Layout.maximumHeight: window.densityWaveformHeight
                                    Canvas {
                                        id: harmonyWaveformCanvas
                                        anchors.fill: parent
                                        property var envelope: modelData.waveform
                                        onEnvelopeChanged: requestPaint()
                                        onPaint: {
                                            var context = getContext("2d")
                                            context.clearRect(0, 0, width, height)
                                            context.strokeStyle = theme.waveformDefault
                                            context.lineWidth = 1.2
                                            context.beginPath()
                                            var points = envelope || []
                                            var center = height / 2
                                            var step = points.length > 0 ? width / points.length : width
                                            if (points.length === 0) { context.moveTo(0, center); context.lineTo(width, center) }
                                            for (var point = 0; point < points.length; point++) {
                                                var value = Math.max(0, Math.min(1, Number(points[point]) || 0))
                                                var x = Math.min(width, point * step + step / 2)
                                                var amplitude = Math.max(1, height * 0.38 * value)
                                                context.moveTo(x, center - amplitude)
                                                context.lineTo(x, center + amplitude)
                                            }
                                            context.stroke()
                                        }
                                    }
                                    Rectangle {
                                        objectName: "previewPlayhead"
                                        width: 2
                                        height: parent ? parent.height : 0
                                        color: theme.textPrimary
                                        z: 3
                                        visible: window.previewPlayheadArmed && parent
                                            && (("" + modelData.path) === ("" + window.interaction.previewPlayingPath))
                                        x: {
                                            if (!parent)
                                                return 0
                                            var span = Math.max(0, parent.width - width)
                                            return Math.round(Math.max(0, Math.min(1, window.interaction.previewProgress)) * span)
                                        }
                                    }
                                    MouseArea { anchors.fill: parent; z: 2; onClicked: { harmonicMatchList.forceActiveFocus(); window.interaction.previewHarmonyRow(index) } }
                                }
                                Label { text: modelData.name; color: theme.textPrimary; font.pixelSize: window.textBody; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true; Layout.minimumWidth: 64; verticalAlignment: Text.AlignVCenter }
                                Label { text: modelData.key; color: theme.actionActive; font.pixelSize: window.textMeta; verticalAlignment: Text.AlignVCenter }
                                Label {
                                    text: modelData.relation + " · " + modelData.fit
                                    color: theme.textSecondary
                                    font.pixelSize: window.textCaption
                                    elide: Text.ElideRight
                                    Layout.preferredWidth: window.harmonicRelationColumnWidth
                                    Layout.maximumWidth: window.harmonicRelationColumnWidth
                                    verticalAlignment: Text.AlignVCenter
                                }
                                Rectangle {
                                    id: harmonyAddAction
                                    Layout.preferredWidth: window.harmonicAddColumnWidth
                                    Layout.preferredHeight: Math.min(window.densityActionHitTarget, window.densityRowHeight - 2 * window.densityVerticalInset)
                                    Layout.maximumHeight: window.densityRowHeight - 2 * window.densityVerticalInset
                                    radius: 3
                                    color: harmonyAddMouse.containsMouse ? theme.hoverSurface : "transparent"
                                    border.width: harmonyAddMouse.containsMouse ? 1 : 0
                                    border.color: theme.borderSubtle
                                    Label {
                                        anchors.fill: parent
                                        text: "+ Add"
                                        color: harmonyAddMouse.containsMouse ? theme.textPrimary : theme.textSecondary
                                        font.pixelSize: window.textCaption
                                        horizontalAlignment: Text.AlignRight
                                        verticalAlignment: Text.AlignVCenter
                                        rightPadding: 4
                                    }
                                    MouseArea {
                                        id: harmonyAddMouse
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        onClicked: { harmonicMatchList.forceActiveFocus(); window.interaction.addHarmonyToKit(index) }
                                    }
                                }
                            }
                            Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: window.densityDividerHeight; color: theme.dividerDefault; opacity: 0.8 }
                        }
                    }
                }
            }
            }

            Rectangle {
                id: bottomRackPane
                objectName: "bottomRackPane"
                width: parent.width
                readonly property bool bottomExpanded: window.channelRack.bottomRackMaterialized
                        || (window.interaction.liveKitRevealed && !window.interaction.liveKitCollapsed)
                height: bottomExpanded
                        ? parent.height * Math.max(window.channelRack.bottomRackHeightRatio, 0.24)
                        : window.channelRack.bottomRackHeightPx
                color: theme.surfacePanel
                border.color: theme.borderSubtle
                visible: window.interaction.hasActiveSource
                         || window.channelRack.bottomRackMaterialized
                // Compat objectName: historical Live Kit findChild probes (#845/#895 harnesses).
                // Content lives under liveKitPane so findChild tree walks still resolve slots/headers.
                Item {
                    id: liveKitPane
                    objectName: "liveKitPane"
                    anchors.fill: parent
                    visible: parent.visible
                // #845 OPEN collapse handle — pane-local mid-edge; click/activate only.
                Item {
                    id: liveKitCollapseHandle
                    objectName: "liveKitCollapseHandle"
                    z: 30
                    width: 14
                    height: 56
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    visible: false
                    activeFocusOnTab: visible
                    Accessible.role: Accessible.Button
                    Accessible.name: "Collapse Live Kit"
                    Accessible.onPressAction: window.interaction.toggleLiveKitCollapsed()
                    property bool hovered: false
                    Rectangle {
                        anchors.fill: parent
                        radius: 3
                        color: liveKitCollapseHandle.hovered ? theme.surfaceElevated : "transparent"
                        opacity: liveKitCollapseHandle.hovered ? 0.92 : 0.45
                        border.width: liveKitCollapseHandle.activeFocus ? 1 : 0
                        border.color: theme.selectionBorder
                    }
                    Text {
                        anchors.centerIn: parent
                        text: "›"
                        color: theme.textSecondary
                        opacity: liveKitCollapseHandle.hovered || liveKitCollapseHandle.activeFocus ? 1.0 : 0.55
                        font.pixelSize: 14
                    }
                    MouseArea {
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onEntered: liveKitCollapseHandle.hovered = true
                        onExited: liveKitCollapseHandle.hovered = false
                        onClicked: {
                            liveKitCollapseHandle.forceActiveFocus()
                            window.interaction.toggleLiveKitCollapsed()
                        }
                    }
                    Keys.onReturnPressed: window.interaction.toggleLiveKitCollapsed()
                    Keys.onEnterPressed: window.interaction.toggleLiveKitCollapsed()
                    Keys.onPressed: function(event) {
                        if (event.key === Qt.Key_Space) {
                            window.interaction.toggleLiveKitCollapsed()
                            event.accepted = true
                        }
                    }
                }
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: bottomRackPane.bottomExpanded ? 14 : 8
                    spacing: 8
                    RowLayout {
                        visible: bottomRackPane.bottomExpanded
                        Layout.fillWidth: true
                        Label { text: "LIVE KIT"; color: theme.textSecondary; font.pixelSize: 12; Layout.fillWidth: true }
                        Label { text: window.screenData.liveKitAssignedCount + " / " + window.screenData.liveKitTotalSlotCount; color: theme.textSecondary; font.pixelSize: 11 }
                        Button {
                            id: liveKitExportButton
                            objectName: "liveKitExportButton"
                            text: "Export Kit"
                            flat: true
                            implicitHeight: 26
                            padding: 8
                            leftPadding: 10
                            rightPadding: 10
                            Accessible.name: "Export Kit"
                            contentItem: Text {
                                text: liveKitExportButton.text
                                color: !liveKitExportButton.enabled ? theme.textDisabled
                                       : (liveKitExportButton.pressed ? theme.textPrimary
                                          : (liveKitExportButton.hovered || liveKitExportButton.activeFocus ? theme.textPrimary : theme.textSecondary))
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                                font.pixelSize: 11
                                opacity: liveKitExportButton.enabled ? 1.0 : 0.45
                            }
                            background: Rectangle {
                                implicitHeight: 26
                                radius: 4
                                color: !liveKitExportButton.enabled ? "transparent"
                                       : (liveKitExportButton.pressed ? theme.surfaceElevated
                                          : (liveKitExportButton.hovered ? theme.hoverSurface : "transparent"))
                                border.width: 1
                                border.color: !liveKitExportButton.enabled ? theme.borderSubtle
                                              : (liveKitExportButton.activeFocus ? theme.focusRing
                                                 : (liveKitExportButton.pressed ? theme.selectionBorder : theme.borderSubtle))
                                opacity: liveKitExportButton.enabled ? 1.0 : 0.4
                            }
                            onClicked: exportKitDialog.open()
                        }
                    }
                    Label {
                        id: liveKitExportStatus
                        objectName: "liveKitExportStatus"
                        visible: bottomRackPane.bottomExpanded
                                 && window.interaction.liveKitExportStatus.length > 0
                        Layout.fillWidth: true
                        text: window.interaction.liveKitExportStatus
                        color: window.interaction.liveKitExportOk ? theme.textSecondary : theme.actionActive
                        font.pixelSize: 11
                        wrapMode: Text.Wrap
                    }
                    Rectangle {
                        id: liveKitPendingBanner
                        objectName: "liveKitPendingBanner"
                        visible: bottomRackPane.bottomExpanded
                                 && window.interaction.liveKitPendingAdd !== ""
                        Layout.fillWidth: true
                        Layout.preferredHeight: 30
                        radius: 4
                        color: theme.selectionSurface
                        border.color: theme.selectionBorder
                        focus: visible
                        onVisibleChanged: if (visible) forceActiveFocus()
                        Keys.onEscapePressed: window.interaction.escapeLiveKitContext()
                        Label {
                            anchors.fill: parent
                            anchors.leftMargin: 8
                            anchors.rightMargin: 8
                            text: "Add " + window.interaction.liveKitPendingAdd + " · Slot + · Esc"
                            color: theme.textPrimary
                            font.pixelSize: 11
                            verticalAlignment: Text.AlignVCenter
                            elide: Text.ElideRight
                        }
                    }
                    Column {
                        visible: bottomRackPane.bottomExpanded
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignTop
                        spacing: 0
                        Repeater { model: window.screenData.liveKitGroups
                            // #895: quieter group chrome — no idle box; fine border only when active/hover.
                            delegate: Rectangle {
                                property int kitGroupIndex: index
                                property bool groupHovered: liveKitGroupHeader.containsMouse
                                width: bottomRackPane.width - 28
                                height: 44 + (modelData.active ? modelData.slots.length * 26 + 14 : 0)
                                radius: 4
                                color: modelData.active ? theme.hoverSurface
                                       : (groupHovered ? theme.hoverSurface : "transparent")
                                border.width: (modelData.active || groupHovered) ? 1 : 0
                                border.color: modelData.active ? theme.selectionBorder : theme.borderSubtle
                                ColumnLayout { anchors.fill: parent; spacing: 0
                                    Item { Layout.fillWidth: true; Layout.preferredHeight: 44; Layout.leftMargin: 12; Layout.rightMargin: 10
                                        RowLayout { anchors.fill: parent; spacing: 6
                                            Label { text: (index + 1) + "  "; color: modelData.active ? theme.actionActive : theme.textSecondary; font.pixelSize: 12; font.bold: true; opacity: modelData.active ? 1.0 : 0.85 }
                                            Label { text: modelData.name; color: theme.textPrimary; font.pixelSize: 13; font.bold: modelData.active; elide: Text.ElideRight; Layout.fillWidth: true }
                                            Label { text: modelData.active ? "▾" : "▸"; color: modelData.active ? theme.textPrimary : theme.textSecondary; font.pixelSize: 11; opacity: 0.85 }
                                        }
                                        MouseArea {
                                            id: liveKitGroupHeader
                                            objectName: "liveKitGroupHeader" + index
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            // onPressed (not onClicked): toggle before release so a
                                            // collapsing group cannot slide a neighbor under the
                                            // pointer and accidental-expand it (#743 disclosure).
                                            onPressed: window.interaction.toggleLiveKitGroup(kitGroupIndex)
                                        }
                                    }
                                ColumnLayout { visible: modelData.active; Layout.fillWidth: true; Layout.leftMargin: 12; Layout.rightMargin: 10; Layout.topMargin: 2
                                    Repeater { model: modelData.active ? modelData.slots : []
                                        delegate: Item {
                                            objectName: "liveKitSlot" + kitGroupIndex + "_" + index
                                            Layout.fillWidth: true
                                            Layout.preferredHeight: 26
                                            // Renderer-only intent: derived from the authoritative
                                            // pending-Add property plus the read-only slot projection.
                                            // Keeps no second Live-Kit target state.
                                            property bool hasPendingAdd: window.interaction.liveKitPendingAdd !== ""
                                            property bool isAssigned: modelData.assigned
                                            property bool isEmpty: !modelData.assigned
                                            property bool showReplaceAffordance: modelData.assigned && !hasPendingAdd
                                            property bool showAddAffordance: !modelData.assigned || hasPendingAdd
                                            Rectangle {
                                                id: slotAuditionBackdrop
                                                anchors.fill: parent
                                                radius: 3
                                                visible: modelData.auditioning
                                                color: theme.selectionSurface
                                                border.color: theme.selectionBorder
                                            }
                                            MouseArea {
                                                id: slotAuditionMouse
                                                objectName: "slotAuditionMouse"
                                                anchors.fill: parent
                                                hoverEnabled: true
                                                enabled: modelData.assigned
                                                onClicked: window.interaction.auditionLiveKitSlot(kitGroupIndex, index)
                                            }
                                            RowLayout { anchors.fill: parent; spacing: 6
                                                Item { Layout.preferredWidth: 14; Layout.preferredHeight: 26
                                                    Label {
                                                        anchors.centerIn: parent
                                                        text: modelData.assigned ? "▶" : ""
                                                        color: slotAuditionMouse.containsMouse && window.interaction.liveKitPendingAdd === "" ? theme.actionActive : (modelData.auditioning ? theme.actionActive : theme.textSecondary)
                                                        font.pixelSize: 10
                                                    }
                                                }
                                                Label { text: modelData.name; color: theme.textSecondary; font.pixelSize: 11; Layout.fillWidth: true; elide: Text.ElideRight }
                                                Label { text: modelData.assignment; color: modelData.auditioning ? theme.actionActive : (modelData.assigned ? theme.textPrimary : theme.textSecondary); font.pixelSize: 11; elide: Text.ElideRight }
                                                Rectangle {
                                                    // #895: quieter slot affordance — fine border, accent only when pending/active.
                                                    id: slotAction
                                                    Layout.preferredHeight: 22
                                                    radius: 3
                                                    Layout.preferredWidth: showReplaceAffordance ? 52 : 22
                                                    color: hasPendingAdd ? theme.selectionSurface
                                                           : (slotActionMouse.containsMouse ? theme.hoverSurface
                                                              : (showReplaceAffordance ? theme.hoverSurface : "transparent"))
                                                    border.width: hasPendingAdd || showReplaceAffordance || slotActionMouse.containsMouse ? 1 : 0
                                                    border.color: hasPendingAdd ? theme.actionActive
                                                                  : (showReplaceAffordance || slotActionMouse.containsMouse ? theme.borderSubtle : "transparent")
                                                    Label {
                                                        anchors.centerIn: parent
                                                        objectName: "slotActionLabel" + kitGroupIndex + "_" + index
                                                        text: hasPendingAdd ? "+" : (showReplaceAffordance ? "↻" : "+")
                                                        color: hasPendingAdd ? theme.actionActive : (slotActionMouse.containsMouse ? theme.textPrimary : theme.textSecondary)
                                                        font.pixelSize: showReplaceAffordance ? 14 : 13
                                                    }
                                                }
                                            }
                                            MouseArea {
                                                id: slotActionMouse
                                                objectName: "slotActionMouse" + kitGroupIndex + "_" + index
                                                x: slotAction.x
                                                y: slotAction.y
                                                width: slotAction.width
                                                height: slotAction.height
                                                hoverEnabled: true
                                                z: 1
                                                onClicked: window.interaction.addLiveKitSlot(kitGroupIndex, index)
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    }

                    Label {
                        visible: window.channelRack.bottomRackMaterialized
                        text: "RACK"
                        color: theme.textSecondary
                        font.pixelSize: 12
                        Layout.fillWidth: true
                    }
                    RowLayout {
                        visible: window.channelRack.bottomRackMaterialized
                        Layout.fillWidth: true
                        spacing: 8
                        Button {
                            id: bottomRackPlayButton
                            objectName: "bottomRackPlayButton"
                            text: window.channelRack.playing ? "Playing…" : "Play"
                            enabled: !window.channelRack.playing
                            onClicked: window.channelRack.play()
                        }
                        Button {
                            id: bottomRackStopButton
                            objectName: "bottomRackStopButton"
                            text: "Stop"
                            enabled: window.channelRack.playing
                            onClicked: window.channelRack.stop()
                        }
                        Item { Layout.fillWidth: true }
                    }
                    ListView {
                        id: bottomRackStepList
                        objectName: "bottomRackStepList"
                        visible: window.channelRack.bottomRackMaterialized
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.min(180, contentHeight)
                        clip: true
                        model: window.channelRack.groups
                        spacing: 6
                        delegate: Column {
                            width: bottomRackStepList.width
                            spacing: 4
                            Label {
                                text: modelData.name
                                color: theme.textSecondary
                                font.pixelSize: 11
                            }
                            Repeater {
                                model: modelData.rows
                                delegate: RowLayout {
                                    id: bottomRackRow
                                    width: bottomRackStepList.width
                                    spacing: 4
                                    readonly property var rowData: modelData
                                    Label {
                                        Layout.preferredWidth: 140
                                        text: rowData.display_name + (rowData.sample_label ? (" · " + rowData.sample_label) : "")
                                        color: theme.textPrimary
                                        font.pixelSize: 11
                                        elide: Text.ElideRight
                                    }
                                    Label {
                                        visible: rowData.row_kind === "loop_identity"
                                        text: "Loop identity"
                                        color: theme.textSecondary
                                        font.pixelSize: 10
                                    }
                                    Repeater {
                                        model: rowData.step_grid_enabled ? rowData.steps : []
                                        delegate: Rectangle {
                                            width: 16
                                            height: 16
                                            radius: 2
                                            color: modelData ? theme.actionActive : theme.surfaceElevated
                                            border.color: theme.borderSubtle
                                            opacity: modelData ? 0.95 : 0.55
                                            MouseArea {
                                                anchors.fill: parent
                                                onClicked: window.channelRack.toggleStep(bottomRackRow.rowData.channel_id, index)
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    Label {
                        visible: !bottomRackPane.bottomExpanded
                        text: "Live Kit / Rack"
                        color: theme.textSecondary
                        font.pixelSize: 11
                        opacity: 0.7
                        Layout.fillWidth: true
                    }
                    Item { Layout.fillHeight: true }
                }
                }
            }
        }

    }

    Item {
        id: channelRackScreen
        objectName: "channelRackScreen"
        anchors.fill: parent
        // #908: legacy Screen-2 page retired from product UX
        visible: false
        focus: visible
        activeFocusOnTab: true
        Keys.onPressed: function(event) {
            if (!visible) return
            if (event.key === Qt.Key_Escape) {
                window.interaction.returnToScreen1()
                event.accepted = true
            } else if (event.key === Qt.Key_Space) {
                if (window.channelRack.playing) window.channelRack.stop()
                else window.channelRack.play()
                event.accepted = true
            }
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 18
            spacing: 12

            RowLayout {
                Layout.fillWidth: true
                spacing: 12
                Label {
                    text: "Channel Rack"
                    color: theme.textPrimary
                    font.pixelSize: 20
                    font.bold: true
                }
                Label {
                    text: "Pattern " + window.channelRack.patternId
                    color: theme.textSecondary
                    font.pixelSize: 12
                }
                Item { Layout.fillWidth: true }
                Button {
                    id: channelRackPlayButton
                    objectName: "channelRackPlayButton"
                    text: "Play Pattern"
                    enabled: !window.channelRack.playing
                    onClicked: window.channelRack.play()
                }
                Button {
                    id: channelRackStopButton
                    objectName: "channelRackStopButton"
                    text: "Stop Pattern"
                    enabled: window.channelRack.playing
                    onClicked: window.channelRack.stop()
                }
                Button {
                    id: addUserChannelButton
                    objectName: "addUserChannelButton"
                    text: "+ Channel"
                    onClicked: window.channelRack.addUserChannel()
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 0
                Item { Layout.preferredWidth: 220 }
                Repeater {
                    model: window.channelRack.stepMarkers
                    delegate: Item {
                        Layout.preferredWidth: 28
                        Layout.preferredHeight: 18
                        Rectangle {
                            anchors.horizontalCenter: parent.horizontalCenter
                            width: 2
                            height: parent.height
                            color: modelData.bar_boundary ? theme.actionActive : (modelData.beat_boundary ? theme.borderSubtle : "transparent")
                        }
                        Label {
                            anchors.centerIn: parent
                            text: modelData.beat_boundary ? (index + 1) : ""
                            color: theme.textSecondary
                            font.pixelSize: 9
                        }
                    }
                }
            }

            ListView {
                id: channelRackStepGrid
                objectName: "channelRackStepGrid"
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                spacing: 10
                model: window.channelRack.groups
                boundsBehavior: Flickable.StopAtBounds
                delegate: ColumnLayout {
                    width: channelRackStepGrid.width
                    spacing: 4
                    Label {
                        text: modelData.name
                        color: theme.textSecondary
                        font.pixelSize: 11
                        font.bold: true
                    }
                    Repeater {
                        model: modelData.rows
                        delegate: RowLayout {
                            id: channelRow
                            Layout.fillWidth: true
                            spacing: 8
                            property string channelId: modelData.channel_id
                            property var stepStates: modelData.steps
                            property string displayName: modelData.display_name
                            property string sampleLabel: modelData.sample_label
                            ColumnLayout {
                                Layout.preferredWidth: 212
                                spacing: 2
                                Label {
                                    text: channelRow.displayName
                                    color: theme.textPrimary
                                    font.pixelSize: 12
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                Label {
                                    text: channelRow.sampleLabel !== "" ? channelRow.sampleLabel : "empty"
                                    color: theme.textSecondary
                                    font.pixelSize: 10
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                Label {
                                    text: channelRow.channelId
                                    color: theme.textDisabled
                                    font.pixelSize: 9
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                Loader {
                                    active: Boolean(modelData.is_user_channel)
                                    sourceComponent: Component {
                                        Button {
                                            id: assignSelectedSampleButton
                                            objectName: "assignSelectedSampleButton_" + modelData.channel_id
                                            enabled: window.channelRack.hasSelectedSample
                                            text: "Assign selected"
                                            flat: true
                                            padding: 0
                                            topPadding: 0
                                            bottomPadding: 0
                                            leftPadding: 0
                                            rightPadding: 0
                                            font.pixelSize: 10
                                            onClicked: window.channelRack.assignSelectedSample(channelRow.channelId)
                                            contentItem: Label {
                                                text: assignSelectedSampleButton.text
                                                color: assignSelectedSampleButton.enabled ? theme.textSecondary : theme.textDisabled
                                                font.pixelSize: 10
                                                elide: Text.ElideRight
                                            }
                                            background: Item {}
                                        }
                                    }
                                }
                            }
                            Repeater {
                                model: channelRow.stepStates
                                delegate: Rectangle {
                                    width: 26
                                    height: 26
                                    radius: 3
                                    property bool stepOn: modelData
                                    color: stepOn ? theme.actionActive : theme.surfaceElevated
                                    border.color: {
                                        var marker = window.channelRack.stepMarkers[index]
                                        if (marker && marker.bar_boundary) return theme.actionActive
                                        if (marker && marker.beat_boundary) return theme.borderSubtle
                                        return theme.dividerDefault
                                    }
                                    border.width: 1
                                    opacity: stepOn ? 1.0 : 0.72
                                    MouseArea {
                                        anchors.fill: parent
                                        onClicked: window.channelRack.toggleStep(channelRow.channelId, index)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    Item {
        id: libraryRevealAffordance
        objectName: "libraryRevealAffordance"
        // #725/#742 subtle edge reveal — overlay, not a workspaceRow child.
        // Row must own horizontal pane geometry; this Item anchors to the
        // ApplicationWindow content item instead.
        z: 20
        visible: window.activeScreen === "screen1" && !window.interaction.libraryRevealed
        width: 18
        height: parent.height
        anchors.left: parent.left
        property bool hovered: false
        Rectangle {
            anchors.fill: parent
            color: libraryRevealAffordance.hovered ? theme.surfaceElevated : "transparent"
            opacity: libraryRevealAffordance.hovered ? 0.92 : 0.55
        }
        Text {
            anchors.centerIn: parent
            text: "›"
            color: theme.textSecondary
            opacity: libraryRevealAffordance.hovered ? 1.0 : 0.55
            font.pixelSize: 16
        }
        MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onEntered: libraryRevealAffordance.hovered = true
            onExited: libraryRevealAffordance.hovered = false
            onClicked: window.interaction.revealLibrary()
        }
    }

    // #845 COLLAPSED reopen affordances — overlay siblings, not zero-width pane children.
    Item {
        id: browserCollapseAffordance
        objectName: "browserCollapseAffordance"
        z: 21
        width: 18
        height: 72
        visible: window.activeScreen === "screen1"
                 && window.interaction.hasActiveSource
                 && window.interaction.browserCollapsed
        // Overlay the Library trailing edge. When Browser+Live Kit are both
        // collapsed the solver gives Library the full width — an after-width
        // x would leave the reopen control off-screen.
        x: workspaceRow.x + Math.max(0, layoutModel.libraryWidth - width - 2)
        y: workspaceRow.y + Math.max(0, (workspaceRow.height - height) / 2)
           - (window.interaction.liveKitCollapsed ? 44 : 0)
        activeFocusOnTab: visible
        Accessible.role: Accessible.Button
        Accessible.name: "Expand Browser"
        Accessible.onPressAction: window.interaction.toggleBrowserCollapsed()
        property bool hovered: false
        Rectangle {
            anchors.fill: parent
            radius: 3
            // Collapsed reopen must stay discoverable without hover (#845).
            color: theme.surfaceElevated
            opacity: browserCollapseAffordance.hovered || browserCollapseAffordance.activeFocus ? 0.95 : 0.72
            border.width: browserCollapseAffordance.activeFocus ? 1 : 0
            border.color: theme.selectionBorder
        }
        Text {
            anchors.centerIn: parent
            text: "›"
            color: theme.textSecondary
            opacity: browserCollapseAffordance.hovered || browserCollapseAffordance.activeFocus ? 1.0 : 0.85
            font.pixelSize: 16
        }
        MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onEntered: browserCollapseAffordance.hovered = true
            onExited: browserCollapseAffordance.hovered = false
            onClicked: {
                browserCollapseAffordance.forceActiveFocus()
                window.interaction.toggleBrowserCollapsed()
            }
        }
        Keys.onReturnPressed: window.interaction.toggleBrowserCollapsed()
        Keys.onEnterPressed: window.interaction.toggleBrowserCollapsed()
        Keys.onPressed: function(event) {
            if (event.key === Qt.Key_Space) {
                window.interaction.toggleBrowserCollapsed()
                event.accepted = true
            }
        }
    }

    Item {
        id: harmonyCollapseAffordance
        objectName: "harmonyCollapseAffordance"
        z: 21
        width: 18
        height: 72
        // Only while Browser is OPEN — never create Browser COLLAPSED + Matches OPEN.
        visible: window.activeScreen === "screen1"
                 && window.interaction.hasActiveSource
                 && !window.interaction.browserCollapsed
                 && !window.interaction.harmonicMatchOpen
        x: workspaceRow.x + layoutModel.libraryWidth
           + ((window.interaction.libraryRevealed && layoutModel.libraryWidth > 0)
              ? layoutModel.handleWidth : 0)
           + layoutModel.browserWidth - width
        y: workspaceRow.y + Math.max(0, (workspaceRow.height - height) / 2)
        activeFocusOnTab: visible
        Accessible.role: Accessible.Button
        Accessible.name: "Expand Harmonic Matches"
        Accessible.onPressAction: window.activateHarmonicMatchToggle()
        property bool hovered: false
        Rectangle {
            anchors.fill: parent
            radius: 3
            color: theme.surfaceElevated
            opacity: harmonyCollapseAffordance.hovered || harmonyCollapseAffordance.activeFocus ? 0.95 : 0.72
            border.width: harmonyCollapseAffordance.activeFocus ? 1 : 0
            border.color: theme.selectionBorder
        }
        Text {
            anchors.centerIn: parent
            text: "›"
            color: theme.textSecondary
            opacity: harmonyCollapseAffordance.hovered || harmonyCollapseAffordance.activeFocus ? 1.0 : 0.85
            font.pixelSize: 16
            Accessible.ignored: true
        }
        MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onEntered: harmonyCollapseAffordance.hovered = true
            onExited: harmonyCollapseAffordance.hovered = false
            onClicked: {
                harmonyCollapseAffordance.forceActiveFocus()
                window.activateHarmonicMatchToggle()
            }
        }
        Keys.onReturnPressed: window.activateHarmonicMatchToggle()
        Keys.onEnterPressed: window.activateHarmonicMatchToggle()
        Keys.onPressed: function(event) {
            if (event.key === Qt.Key_Space) {
                window.activateHarmonicMatchToggle()
                event.accepted = true
            }
        }
    }

    Item {
        id: liveKitCollapseAffordance
        objectName: "liveKitCollapseAffordance"
        z: 21
        width: 18
        height: 72
        visible: window.activeScreen === "screen1"
                 && window.interaction.hasActiveSource
                 && window.interaction.liveKitRevealed
                 && window.interaction.liveKitCollapsed
        x: workspaceRow.x + workspaceRow.width - width
        y: workspaceRow.y + Math.max(0, (workspaceRow.height - height) / 2)
           + (window.interaction.browserCollapsed ? 44 : 0)
        activeFocusOnTab: visible
        Accessible.role: Accessible.Button
        Accessible.name: "Expand Live Kit"
        Accessible.onPressAction: window.interaction.toggleLiveKitCollapsed()
        property bool hovered: false
        Rectangle {
            anchors.fill: parent
            radius: 3
            color: theme.surfaceElevated
            opacity: liveKitCollapseAffordance.hovered || liveKitCollapseAffordance.activeFocus ? 0.95 : 0.72
            border.width: liveKitCollapseAffordance.activeFocus ? 1 : 0
            border.color: theme.selectionBorder
        }
        Text {
            anchors.centerIn: parent
            text: "‹"
            color: theme.textSecondary
            opacity: liveKitCollapseAffordance.hovered || liveKitCollapseAffordance.activeFocus ? 1.0 : 0.85
            font.pixelSize: 16
        }
        MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onEntered: liveKitCollapseAffordance.hovered = true
            onExited: liveKitCollapseAffordance.hovered = false
            onClicked: {
                liveKitCollapseAffordance.forceActiveFocus()
                window.interaction.toggleLiveKitCollapsed()
            }
        }
        Keys.onReturnPressed: window.interaction.toggleLiveKitCollapsed()
        Keys.onEnterPressed: window.interaction.toggleLiveKitCollapsed()
        Keys.onPressed: function(event) {
            if (event.key === Qt.Key_Space) {
                window.interaction.toggleLiveKitCollapsed()
                event.accepted = true
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
    on_browser_rows_changed: Callable[[], None] | None = None,
    on_waveform_request: Callable[[int, int], None] | None = None,
    on_harmony_waveform_request: Callable[[int, int], None] | None = None,
    on_open_channel_rack: Callable[[], None] | None = None,
    on_return_to_screen1: Callable[[], None] | None = None,
):
    """Expose the pure interaction adapter to QML only when Qt is installed."""
    from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot

    class QmlInteractionBridge(QObject):
        state_changed = Signal()
        addToKitIntent = Signal(str)
        sampleContextClosed = Signal()

        def __init__(self) -> None:
            super().__init__()
            adapter._on_sample_context_closed = self._emit_sample_context_closed

        def _emit_sample_context_closed(self) -> None:
            self.sampleContextClosed.emit()

        def _refresh(self) -> None:
            adapter.sync_visible_state_labels()
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
        def browserCollapsed(self) -> bool:
            return bool(adapter.browser_collapsed)

        @Property(bool, notify=state_changed)
        def liveKitCollapsed(self) -> bool:
            return bool(adapter.live_kit_collapsed)

        @Property(bool, notify=state_changed)
        def hasActiveSource(self) -> bool:
            return adapter.view_model.has_active_source

        @Property(bool, notify=state_changed)
        def liveKitRevealed(self) -> bool:
            return bool(adapter.view_model.live_kit_materialized)

        @Property(bool, notify=state_changed)
        def libraryRevealed(self) -> bool:
            return bool(adapter.view_model.library_revealed)

        @Slot()
        def revealLibrary(self) -> None:
            if adapter.view_model.reveal_library():
                self._refresh()

        @Property(bool, notify=state_changed)
        def previewActive(self) -> bool:
            return adapter.preview_active

        @Property(str, notify=state_changed)
        def previewPlayingPath(self) -> str:
            snap = adapter.preview_playback_snapshot()
            return str(getattr(snap, "sample_path", "") or "")

        @Property(float, notify=state_changed)
        def previewProgress(self) -> float:
            snap = adapter.preview_playback_snapshot()
            return float(getattr(snap, "progress", 0.0) or 0.0)

        @Property(bool, notify=state_changed)
        def previewPlaybackPlaying(self) -> bool:
            snap = adapter.preview_playback_snapshot()
            return bool(getattr(snap, "playing", False))

        @Property(int, notify=state_changed)
        def previewPlaybackId(self) -> int:
            snap = adapter.preview_playback_snapshot()
            return int(getattr(snap, "playback_instance_id", 0) or 0)

        @Property(str, notify=state_changed)
        def waveformMotionMode(self) -> str:
            return adapter.waveform_motion_mode

        @Slot(str)
        def setWaveformMotionMode(self, mode: str) -> None:
            from .workbench_display_preferences import save_display_preferences

            adapter.set_waveform_motion_mode(mode)
            try:
                save_display_preferences(
                    {
                        "density_mode": "compact",
                        "motion_mode": adapter.waveform_motion_mode,
                    }
                )
            except OSError:
                pass
            self._refresh()

        @Property(bool, notify=state_changed)
        def gestureRackApplyEnabled(self) -> bool:
            return adapter.gesture_rack_apply_enabled

        @Slot(bool)
        def setGestureRackApplyEnabled(self, enabled: bool) -> None:
            adapter.set_gesture_rack_apply_enabled(bool(enabled))
            self._refresh()

        @Slot()
        def resetLayoutPreferences(self) -> None:
            adapter.reset_layout_preferences()
            self._refresh()

        @Slot()
        def saveWorkspacePreset(self) -> None:
            adapter.save_workspace_preset_action()
            self._refresh()

        @Slot()
        def setWorkspacePresetAsStartup(self) -> None:
            adapter.set_workspace_preset_as_startup()
            self._refresh()

        @Slot()
        def returnToCleanStart(self) -> None:
            adapter.return_to_clean_start_action()
            self._refresh()

        @Slot()
        def refreshPreviewPlayback(self) -> None:
            adapter.refresh_preview_playback()
            self.state_changed.emit()

        @Property(str, notify=state_changed)
        def liveKitExportStatus(self) -> str:
            return adapter.live_kit_export_status

        @Property(bool, notify=state_changed)
        def liveKitExportOk(self) -> bool:
            return bool(adapter.live_kit_export_ok)

        @Slot(str)
        def exportLiveKitUrl(self, url: str) -> None:
            candidate = QUrl(url)
            path = candidate.toLocalFile() if candidate.isLocalFile() else url
            adapter.export_live_kit(path)
            self._refresh()

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

        @Slot(str)
        def setBrowserSearch(self, query: str) -> None:
            adapter.view_model.set_browser_search_query(query)
            if on_browser_rows_changed is not None:
                on_browser_rows_changed()
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
        def openSampleContext(self, index: int) -> None:
            adapter.open_sample_context(index)
            self._refresh()

        @Slot()
        def closeSampleContext(self) -> None:
            adapter.close_sample_context()
            self._refresh()

        @Slot()
        def contextAddToKit(self) -> None:
            if adapter.sample_context_target is None:
                return
            row = adapter.request_context_add_to_kit()
            self.addToKitIntent.emit(row.relative_path or str(row.path))
            self._refresh()

        @Slot()
        def contextHarmonicMatches(self) -> None:
            if adapter.sample_context_target is None:
                return
            adapter.request_context_harmonic_matches()
            self._refresh()

        @Slot(int)
        def toggleFavorite(self, index: int) -> None:
            adapter.toggle_favorite(index)
            if on_browser_rows_changed is not None:
                on_browser_rows_changed()
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

        @Slot(int, result=str)
        def outboundFileUrl(self, index: int) -> str:
            """Expose the existing original sample as a standard local file URL."""
            from .workbench_sample_dnd import outbound_local_file_url

            if not 0 <= index < len(adapter.view_model.browser_rows):
                return ""
            path = adapter.view_model.browser_rows[index].source_row.path
            return outbound_local_file_url(path) or ""

        @Slot()
        def toggleHarmonicMatch(self) -> None:
            adapter.toggle_harmonic_match()
            self._refresh()

        @Slot()
        def toggleBrowserCollapsed(self) -> None:
            adapter.toggle_browser_collapsed()
            self._refresh()

        @Slot()
        def toggleLiveKitCollapsed(self) -> None:
            adapter.toggle_live_kit_collapsed()
            self._refresh()

        @Slot()
        def openChannelRack(self) -> None:
            if on_open_channel_rack is not None:
                on_open_channel_rack()
            # Refresh interaction/screen projection after audio-focus quiet (#807)
            # so previewActive / Live Kit audition chrome cannot stay stale.
            self._refresh()

        @Slot()
        def returnToScreen1(self) -> None:
            if on_return_to_screen1 is not None:
                on_return_to_screen1()
            self._refresh()

    return QmlInteractionBridge()


def _qml_transport_bridge(transport):
    """Thin QML projection/commands for session MASTER/GRID/SYNC (#805).

    ``WorkbenchTransportAdapter`` (or compose-owned session transport) remains
    the sole tempo/SYNC authority. QML never stores a second BPM or SYNC flag.
    When ``transport`` is ``None`` (injected Screen-1 harnesses), project
    fail-closed defaults and no-op commands — do not invent an adapter.
    """
    from PySide6.QtCore import QObject, Property, Signal, Slot

    from .workbench_transport_ui import DEFAULT_TEMPO_BPM

    class QmlTransportBridge(QObject):
        state_changed = Signal()

        def __init__(self) -> None:
            super().__init__()
            self._transport = transport
            self._master_tempo = float(DEFAULT_TEMPO_BPM)
            self._master_tempo_text = f"{self._master_tempo:g}"
            self._grid_text = "4/4"
            self._sync_enabled = False
            self._sync_from_transport()

        def _sync_from_transport(self) -> None:
            if self._transport is None:
                self._master_tempo = float(DEFAULT_TEMPO_BPM)
                self._master_tempo_text = f"{self._master_tempo:g}"
                self._grid_text = "4/4"
                self._sync_enabled = False
                return
            tempo = float(self._transport.get_current_tempo())
            self._master_tempo = tempo
            self._master_tempo_text = f"{tempo:g}"
            signature = self._transport.tempo_map.time_signature
            self._grid_text = f"{signature.numerator}/{signature.denominator}"
            self._sync_enabled = bool(self._transport.is_sync_enabled())

        @Slot()
        def refresh(self) -> None:
            self._sync_from_transport()
            self.state_changed.emit()

        @Property(float, notify=state_changed)
        def masterTempo(self) -> float:
            return self._master_tempo

        @Property(str, notify=state_changed)
        def masterTempoText(self) -> str:
            return self._master_tempo_text

        @Property(str, notify=state_changed)
        def gridText(self) -> str:
            return self._grid_text

        @Property(bool, notify=state_changed)
        def syncEnabled(self) -> bool:
            return self._sync_enabled

        @Slot(float)
        def adjustTempo(self, delta_bpm: float) -> None:
            if self._transport is None:
                return
            # User MASTER deltas use resume intent (pending target if scheduled).
            base = float(self._transport.get_resume_master_bpm())
            target = max(1.0, base + float(delta_bpm))
            self._transport.set_tempo(target)
            self.refresh()

        @Slot(result=bool)
        def toggleSync(self) -> bool:
            if self._transport is None:
                return False
            enabled = bool(self._transport.toggle_sync())
            self.refresh()
            return enabled

    return QmlTransportBridge()


def _qml_session_persistence_bridge(session):
    """Thin QML projection of Python-owned persistence honesty status (#819).

    ``WorkbenchSession.persistence_status`` remains the sole authority. QML
    never invents restore/autosave outcomes or stores a second status machine.
    When ``session`` is ``None`` (injected Screen-1 harnesses), project
    ``fresh_missing`` with no attention chrome.
    """
    from PySide6.QtCore import QObject, Property, Signal, Slot

    from .workbench_session_store import (
        PERSISTENCE_STATUS_AUTOSAVE_FAILED,
        PERSISTENCE_STATUS_FRESH_MISSING,
        PERSISTENCE_STATUS_REJECTED_CORRUPT,
        PERSISTENCE_STATUS_REJECTED_SCHEMA,
        PERSISTENCE_STATUS_REJECTED_SEMANTIC,
        persistence_status_label,
    )

    _ATTENTION = frozenset(
        {
            PERSISTENCE_STATUS_REJECTED_CORRUPT,
            PERSISTENCE_STATUS_REJECTED_SCHEMA,
            PERSISTENCE_STATUS_REJECTED_SEMANTIC,
            PERSISTENCE_STATUS_AUTOSAVE_FAILED,
        }
    )

    class QmlSessionPersistenceBridge(QObject):
        state_changed = Signal()

        def __init__(self) -> None:
            super().__init__()
            self._session = session
            if session is not None:
                add = getattr(session, "add_persistence_status_listener", None)
                if callable(add):
                    add(self.refresh)

        def _status_code(self) -> str:
            if self._session is None:
                return PERSISTENCE_STATUS_FRESH_MISSING
            return str(getattr(self._session, "persistence_status", PERSISTENCE_STATUS_FRESH_MISSING))

        @Slot()
        def refresh(self) -> None:
            self.state_changed.emit()

        @Property(str, notify=state_changed)
        def statusCode(self) -> str:
            return self._status_code()

        @Property(str, notify=state_changed)
        def statusLabel(self) -> str:
            return persistence_status_label(self._status_code())

        @Property(bool, notify=state_changed)
        def attention(self) -> bool:
            return self._status_code() in _ATTENTION

    return QmlSessionPersistenceBridge()


def _qml_channel_rack_bridge(
    controller,
    *,
    resolve_selected_sample_path=None,
):
    """Expose Channel Rack projection + commands; Python remains musical SoT.

    ``controller`` may be ``None`` when ``_qml_engine`` is driven with an
    injected ``interaction_adapter`` (Screen-1 harnesses). Screen-2 commands
    then fail closed — Channel Rack must use compose-owned session transport
    (#678), never a second invented owner.

    ``resolve_selected_sample_path`` optionally reads the existing Screen-1
    browser selection (no second selection store). Missing/invalid selection
    fail-softs without mutating rack state (#808).
    """
    from PySide6.QtCore import QObject, Property, Signal, Slot

    class QmlChannelRackBridge(QObject):
        state_changed = Signal()

        def __init__(self) -> None:
            super().__init__()
            self._groups: list[dict] = []
            self._step_markers: list[dict] = []
            self._step_count = 16
            self._pattern_id = ""
            self._active_screen = "screen1"
            self._playing = False
            self._has_selected_sample = False
            self._bottom_rack_materialized = False
            self._bottom_rack_height_ratio = 0.0
            self._bottom_rack_height_px = 32
            self._product_surface = "bottom_rack"
            self._sync_from_controller()

        def _resolved_selected_path(self) -> str | None:
            if resolve_selected_sample_path is None:
                return None
            try:
                path = resolve_selected_sample_path()
            except Exception:
                return None
            if path is None:
                return None
            text = str(path).strip()
            return text or None

        def _sync_from_controller(self) -> None:
            if controller is None:
                self._groups = []
                self._step_markers = []
                self._step_count = 16
                self._pattern_id = ""
                self._active_screen = "screen1"
                self._playing = False
                self._has_selected_sample = False
                self._bottom_rack_materialized = False
                self._bottom_rack_height_ratio = 0.0
                self._bottom_rack_height_px = 32
                self._product_surface = "bottom_rack"
                return
            projection = controller.projection()
            self._groups = list(projection.get("groups") or [])
            self._step_markers = list(projection.get("step_markers") or [])
            self._step_count = int(projection.get("step_count") or 16)
            self._pattern_id = str(projection.get("pattern_id") or "")
            self._active_screen = controller.active_screen
            self._playing = bool(controller.is_playing)
            self._has_selected_sample = self._resolved_selected_path() is not None
            self._bottom_rack_materialized = bool(
                projection.get("bottom_rack_materialized")
            )
            self._bottom_rack_height_ratio = float(
                projection.get("bottom_rack_height_ratio") or 0.0
            )
            self._bottom_rack_height_px = int(
                projection.get("bottom_rack_height_px") or 32
            )
            self._product_surface = str(
                projection.get("product_surface") or "bottom_rack"
            )

        def refresh(self) -> None:
            self._sync_from_controller()
            self.state_changed.emit()

        @Property(str, notify=state_changed)
        def activeScreen(self) -> str:
            return self._active_screen

        @Property(bool, notify=state_changed)
        def playing(self) -> bool:
            return self._playing

        @Property(bool, notify=state_changed)
        def hasSelectedSample(self) -> bool:
            return self._has_selected_sample

        @Property(int, notify=state_changed)
        def stepCount(self) -> int:
            return self._step_count

        @Property(str, notify=state_changed)
        def patternId(self) -> str:
            return self._pattern_id

        @Property("QVariantList", notify=state_changed)
        def groups(self) -> list:
            return self._groups

        @Property("QVariantList", notify=state_changed)
        def stepMarkers(self) -> list:
            return self._step_markers

        @Property(bool, notify=state_changed)
        def bottomRackMaterialized(self) -> bool:
            return self._bottom_rack_materialized

        @Property(float, notify=state_changed)
        def bottomRackHeightRatio(self) -> float:
            return self._bottom_rack_height_ratio

        @Property(int, notify=state_changed)
        def bottomRackHeightPx(self) -> int:
            return self._bottom_rack_height_px

        @Property(str, notify=state_changed)
        def productSurface(self) -> str:
            return self._product_surface

        @Slot()
        def openChannelRack(self) -> None:
            """#908: materialize bottom Rack without Screen-2 navigation."""
            if controller is None:
                return
            controller.ensure_state()
            self.refresh()

        @Slot()
        def returnToScreen1(self) -> None:
            if controller is None:
                return
            controller.leave_screen2()
            self.refresh()

        @Slot(str, int)
        def toggleStep(self, channel_id: str, step_index: int) -> None:
            if controller is None:
                return
            controller.toggle_step(channel_id, int(step_index))
            self.refresh()

        @Slot()
        def addUserChannel(self) -> None:
            if controller is None:
                return
            controller.add_user_channel()
            self.refresh()

        @Slot(str)
        def assignSelectedSample(self, channel_id: str) -> None:
            """Assign current Screen-1 browser selection to a user channel (#808)."""
            if controller is None:
                return
            path = self._resolved_selected_path()
            if path is None:
                # Fail-soft: no valid selection → no musical mutation.
                self.refresh()
                return
            try:
                controller.assign_user_channel_sample(str(channel_id), path)
            except (RuntimeError, TypeError, ValueError):
                # Fail-soft at the QML intent boundary; Python core stays authoritative.
                self.refresh()
                return
            self.refresh()

        @Slot()
        def play(self) -> None:
            if controller is None:
                return
            try:
                controller.play()
            except RuntimeError:
                # Fail soft in the Qt slot: keep UI not-playing when native
                # engine/transport is unavailable.
                self._playing = False
                self._active_screen = controller.active_screen
                self.state_changed.emit()
                return
            self.refresh()

        @Slot()
        def stop(self) -> None:
            if controller is None:
                return
            controller.stop()
            self.refresh()

        @Slot()
        def tickPlayback(self) -> None:
            if controller is None:
                return
            controller.tick_playback()
            self._playing = bool(controller.is_playing)
            self._active_screen = controller.active_screen
            self.state_changed.emit()

    return QmlChannelRackBridge()


def _qml_library_interaction_bridge(
    library_model,
    *,
    on_selection: Callable[[], None] | None = None,
    on_add_source: Callable[[str], bool] | None = None,
    on_prepare_remove: Callable[[int], object | None] | None = None,
    on_confirm_remove: Callable[[int], bool] | None = None,
    on_can_accept_drop: Callable[[str], bool] | None = None,
    on_import_drop: Callable[[str, list[str]], bool] | None = None,
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

        @Property("QVariantList", notify=state_changed)
        def collectionEntries(self) -> list[dict[str, object]]:
            state = library_model.state
            state.fetch_children("container:collections")
            return [
                {
                    "nodeId": node.node_id,
                    "label": node.label,
                    "selected": state.selected_node_id == node.node_id,
                }
                for node in state.visible_children("container:collections")
                if node.kind is LibraryNodeKind.COLLECTION
            ]

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

        @Slot(str, result=bool)
        def canAcceptSampleDrop(self, node_id: str) -> bool:
            if on_can_accept_drop is None:
                return False
            try:
                return bool(on_can_accept_drop(node_id))
            except Exception:
                return False

        @Slot(str, "QVariantList", result=bool)
        def importDroppedUrls(self, node_id: str, urls) -> bool:
            if on_import_drop is None:
                return False
            normalized: list[str] = []
            for item in list(urls or []):
                text = str(item)
                if hasattr(item, "toString"):
                    try:
                        text = str(item.toString())
                    except Exception:
                        text = str(item)
                if text:
                    normalized.append(text)
            try:
                return bool(on_import_drop(str(node_id), normalized))
            except Exception:
                return False

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


def _qml_theme_authority_bridge(
    *,
    state_dir: Path | None = None,
    env: dict[str, str] | None = None,
):
    """Expose Theme Core (#785) as the sole Screen-1 color authority for QML."""
    from PySide6.QtCore import QObject, Property, Signal, Slot

    from . import workbench_theme as theme_mod

    class QmlThemeAuthorityBridge(QObject):
        themeChanged = Signal()

        def __init__(self) -> None:
            super().__init__()
            self._state_dir = state_dir
            self._env = env
            self._tokens = theme_mod.resolve_theme(state_dir=state_dir, env=env)
            self._semantics = theme_mod.theme_tokens_to_qml_semantics(self._tokens)
            self._draft_accent = self._tokens.accent
            self._draft_background = self._tokens.background
            self._draft_foreground = self._tokens.foreground
            self._draft_name = self._tokens.name

        def _reload(self, tokens: theme_mod.ThemeTokens | None = None) -> None:
            self._tokens = tokens or theme_mod.resolve_theme(
                state_dir=self._state_dir,
                env=self._env,
            )
            self._semantics = theme_mod.theme_tokens_to_qml_semantics(self._tokens)
            self._draft_accent = self._tokens.accent
            self._draft_background = self._tokens.background
            self._draft_foreground = self._tokens.foreground
            self._draft_name = self._tokens.name
            self.themeChanged.emit()

        def _preview_from_draft(self) -> None:
            accent = theme_mod._normalize_hex(self._draft_accent)
            background = theme_mod._normalize_hex(self._draft_background)
            foreground = theme_mod._normalize_hex(self._draft_foreground)
            if accent is None or background is None or foreground is None:
                return
            base = theme_mod.ThemeBase(
                accent=accent,
                background=background,
                foreground=foreground,
            )
            preview = theme_mod._tokens_from_base(
                base,
                name=self._draft_name,
                base_preset=self._tokens.base_preset,
            )
            self._semantics = theme_mod.theme_tokens_to_qml_semantics(preview)
            self.themeChanged.emit()

        def _color(self, key: str) -> str:
            return str(self._semantics.get(key) or theme_mod.TEXT_ON_ACTION)

        def _available_names(self) -> list[str]:
            customs = theme_mod.list_custom_themes(
                state_dir=self._state_dir,
                env=self._env,
            )
            return list(theme_mod.list_presets()) + customs

        @Property(str, notify=themeChanged)
        def selectedThemeName(self) -> str:
            return self._tokens.name

        @Property(str, notify=themeChanged)
        def basePresetName(self) -> str:
            return self._tokens.base_preset

        @Property(bool, notify=themeChanged)
        def isCustom(self) -> bool:
            return self._tokens.name not in theme_mod.PRESET_ORDER

        @Property(list, notify=themeChanged)
        def availableThemeNames(self) -> list[str]:
            return self._available_names()

        @Property(list, notify=themeChanged)
        def customThemeNames(self) -> list[str]:
            return theme_mod.list_custom_themes(
                state_dir=self._state_dir,
                env=self._env,
            )

        @Property(int, notify=themeChanged)
        def selectedThemeIndex(self) -> int:
            names = self._available_names()
            try:
                return names.index(self._tokens.name)
            except ValueError:
                return 0

        @Property(str, notify=themeChanged)
        def baseAccent(self) -> str:
            return self._draft_accent

        @Property(str, notify=themeChanged)
        def baseBackground(self) -> str:
            return self._draft_background

        @Property(str, notify=themeChanged)
        def baseForeground(self) -> str:
            return self._draft_foreground

        @Property(str, notify=themeChanged)
        def surfaceRoot(self) -> str:
            return self._color("surfaceRoot")

        @Property(str, notify=themeChanged)
        def surfaceHeader(self) -> str:
            return self._color("surfaceHeader")

        @Property(str, notify=themeChanged)
        def surfaceBrowser(self) -> str:
            return self._color("surfaceBrowser")

        @Property(str, notify=themeChanged)
        def surfacePanel(self) -> str:
            return self._color("surfacePanel")

        @Property(str, notify=themeChanged)
        def surfaceElevated(self) -> str:
            return self._color("surfaceElevated")

        @Property(str, notify=themeChanged)
        def borderSubtle(self) -> str:
            return self._color("borderSubtle")

        @Property(str, notify=themeChanged)
        def dividerDefault(self) -> str:
            return self._color("dividerDefault")

        @Property(str, notify=themeChanged)
        def textPrimary(self) -> str:
            return self._color("textPrimary")

        @Property(str, notify=themeChanged)
        def textSecondary(self) -> str:
            return self._color("textSecondary")

        @Property(str, notify=themeChanged)
        def textDisabled(self) -> str:
            return self._color("textDisabled")

        @Property(str, notify=themeChanged)
        def textOnAction(self) -> str:
            return self._color("textOnAction")

        @Property(str, notify=themeChanged)
        def waveformDefault(self) -> str:
            return self._color("waveformDefault")

        @Property(str, notify=themeChanged)
        def waveformActive(self) -> str:
            return self._color("waveformActive")

        @Property(str, notify=themeChanged)
        def selectionSurface(self) -> str:
            return self._color("selectionSurface")

        @Property(str, notify=themeChanged)
        def selectionBorder(self) -> str:
            return self._color("selectionBorder")

        @Property(str, notify=themeChanged)
        def actionActive(self) -> str:
            return self._color("actionActive")

        @Property(str, notify=themeChanged)
        def focusRing(self) -> str:
            return self._color("focusRing")

        @Property(str, notify=themeChanged)
        def hoverSurface(self) -> str:
            return self._color("hoverSurface")

        @Slot(str)
        def selectTheme(self, name: str) -> None:
            tokens = theme_mod.select_theme(
                str(name),
                state_dir=self._state_dir,
                env=self._env,
            )
            self._reload(tokens)

        @Slot()
        def customizeSelectedPreset(self) -> None:
            base_preset = (
                self._tokens.name
                if self._tokens.name in theme_mod.PRESET_ORDER
                else self._tokens.base_preset
            )
            if base_preset not in theme_mod.PRESET_ORDER:
                base_preset = theme_mod.DEFAULT_PRESET_NAME
            existing = set(theme_mod.PRESET_ORDER) | set(
                theme_mod.list_custom_themes(state_dir=self._state_dir, env=self._env)
            )
            name = f"{base_preset} Custom"
            suffix = 2
            while name in existing:
                name = f"{base_preset} Custom {suffix}"
                suffix += 1
            theme_mod.create_custom_theme(
                name=name,
                base_preset=base_preset,
                accent=self._draft_accent,
                background=self._draft_background,
                foreground=self._draft_foreground,
                state_dir=self._state_dir,
                env=self._env,
            )
            tokens = theme_mod.select_theme(
                name,
                state_dir=self._state_dir,
                env=self._env,
            )
            self._reload(tokens)

        @Slot(str, str)
        def createCustomFromPreset(self, base_preset: str, name: str) -> None:
            theme_mod.create_custom_theme(
                name=str(name),
                base_preset=str(base_preset),
                state_dir=self._state_dir,
                env=self._env,
            )
            tokens = theme_mod.select_theme(
                str(name),
                state_dir=self._state_dir,
                env=self._env,
            )
            self._reload(tokens)

        @Slot(str)
        def setBaseAccent(self, value: str) -> None:
            normalized = theme_mod._normalize_hex(value)
            if normalized is None:
                return
            self._draft_accent = normalized
            self._preview_from_draft()

        @Slot(str)
        def setBaseBackground(self, value: str) -> None:
            normalized = theme_mod._normalize_hex(value)
            if normalized is None:
                return
            self._draft_background = normalized
            self._preview_from_draft()

        @Slot(str)
        def setBaseForeground(self, value: str) -> None:
            normalized = theme_mod._normalize_hex(value)
            if normalized is None:
                return
            self._draft_foreground = normalized
            self._preview_from_draft()

        @Slot()
        def saveCurrentCustom(self) -> None:
            if self._tokens.name in theme_mod.PRESET_ORDER:
                return
            theme_mod.save_custom_theme(
                {
                    "name": self._tokens.name,
                    "base_preset": self._tokens.base_preset,
                    "accent": self._draft_accent,
                    "background": self._draft_background,
                    "foreground": self._draft_foreground,
                },
                state_dir=self._state_dir,
                env=self._env,
            )
            tokens = theme_mod.select_theme(
                self._tokens.name,
                state_dir=self._state_dir,
                env=self._env,
            )
            self._reload(tokens)

        @Slot(str)
        def renameCurrentCustom(self, new_name: str) -> None:
            if self._tokens.name in theme_mod.PRESET_ORDER:
                return
            old = self._tokens.name
            theme_mod.rename_custom_theme(
                old,
                str(new_name),
                state_dir=self._state_dir,
                env=self._env,
            )
            tokens = theme_mod.resolve_theme(
                str(new_name).strip(),
                state_dir=self._state_dir,
                env=self._env,
            )
            self._reload(tokens)

        @Slot()
        def deleteCurrentCustom(self) -> None:
            if self._tokens.name in theme_mod.PRESET_ORDER:
                return
            theme_mod.delete_custom_theme(
                self._tokens.name,
                state_dir=self._state_dir,
                env=self._env,
            )
            self._reload()

        @Slot()
        def resetCurrentCustom(self) -> None:
            if self._tokens.name in theme_mod.PRESET_ORDER:
                return
            tokens = theme_mod.reset_custom_theme(
                self._tokens.name,
                state_dir=self._state_dir,
                env=self._env,
            )
            self._reload(tokens)

    return QmlThemeAuthorityBridge()


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
    channel_rack_controller = None
    session_transport = None
    session = None
    if interaction_adapter is None:
        from .workbench_session import compose_workbench_session

        library_db_path = None
        if runtime_composition is not None:
            library_db_path = getattr(runtime_composition, "library_db_path", None)
        session = compose_workbench_session(library_db_path=library_db_path)
        preview_player = session.audition
        live_kit = session.live_kit_presenter
        adapter = session.qml_interaction_adapter
        channel_rack_controller = session.channel_rack
        session_transport = session.transport
        # Keep the caller-provided view_model as the renderer surface while
        # reusing the session-owned kit + TransportAwarePreview audition.
        adapter.view_model = view_model
        view_model.live_kit_groups = live_kit.groups
        view_model.auditioning_live_kit_slot = adapter.auditioning_live_kit_slot
    else:
        # Injected-adapter harnesses keep Screen-1 surfaces only. Screen-2
        # Channel Rack must reuse compose-owned session transport (#678) —
        # do not invent a second WorkbenchTransportAdapter here.
        adapter = interaction_adapter
        live_kit = getattr(interaction_adapter, "_live_kit", None)
        channel_rack_controller = None
        session_transport = None
        session = None
    try:
        from .workbench_display_preferences import load_display_preferences

        adapter.set_waveform_motion_mode(load_display_preferences().motion_mode)
    except Exception:
        pass
    try:
        adapter.load_feature_settings()
    except Exception:
        pass
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
    # Last viewport ranges — drain re-requests so max_pending saturation
    # still fills the full compact visible window without raising the bound.
    browser_waveform_viewport = [0, 0]
    harmony_waveform_viewport = [0, 0]

    def request_waveforms(start: int, count: int) -> None:
        if count <= 0:
            return
        first = max(0, start)
        last = min(len(view_model.browser_rows), first + count)
        browser_waveform_viewport[0] = first
        browser_waveform_viewport[1] = max(0, last - first)
        for row in view_model.browser_rows[first:last]:
            if row.waveform_envelope:
                continue
            waveform_loader.schedule(str(row.source_row.path))

    def request_harmony_waveforms(start: int, count: int) -> None:
        if count <= 0:
            return
        first = max(0, start)
        last = min(len(view_model.harmony_rows), first + count)
        harmony_waveform_viewport[0] = first
        harmony_waveform_viewport[1] = max(0, last - first)
        for row in view_model.harmony_rows[first:last]:
            if row.waveform_envelope:
                continue
            waveform_loader.schedule(str(row.source_row.path))

    def request_visible_browser_waveforms_from_window() -> None:
        """Python-side viewport seed after model refresh; QML owns scroll/resize."""
        try:
            from PySide6.QtQuick import QQuickItem
        except Exception:
            return
        roots = engine.rootObjects()
        if not roots:
            return
        root = roots[0]
        browser = root.findChild(QQuickItem, "browserList")
        if browser is None:
            return
        row_height = int(root.property("densityRowHeight") or 0)
        height = float(browser.property("height") or 0.0)
        content_y = float(browser.property("contentY") or 0.0)
        if row_height <= 0 or height <= 0:
            return
        start = max(0, int(content_y // row_height))
        count = int(math.ceil(height / row_height)) + 2
        request_waveforms(start, count)

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
        # Freeing pending slots must continue filling the current viewport.
        if browser_waveform_viewport[1] > 0:
            request_waveforms(browser_waveform_viewport[0], browser_waveform_viewport[1])
        if harmony_waveform_viewport[1] > 0:
            request_harmony_waveforms(
                harmony_waveform_viewport[0], harmony_waveform_viewport[1]
            )

    analysis_coordinator = None
    layout_model = None
    bridge = None  # assigned below; closures resolve at call time

    def apply_analysis_state(state: AnalysisUiState) -> None:
        view_model.set_analysis_state(state)
        if state.phase in {"scanning", "analyzing"}:
            # #742: hide working panes while analysis runs; keep technical identity.
            view_model.set_workspace_materialization(
                has_active_source=False,
                calm_canvas_visible=False,
                browser_materialized=False,
                live_kit_materialized=False,
            )
            if runtime_composition is not None:
                runtime_composition.clear_live_kit_disclosure()
        elif state.phase in {"cancelled", "error"}:
            _analysis_fail_closed(state)
        refresh_screen_model()
        if layout_model is not None:
            layout_model.syncFromInteraction()
        if bridge is not None:
            bridge.refreshState()

    def _analysis_fail_closed(state: AnalysisUiState) -> None:
        """Cancel/failure must not leave half-materialized working panes."""
        if runtime_composition is not None:
            runtime_composition.clear_no_scope()
        view_model.set_browser_state(
            rows=(),
            selected_index=-1,
            browser_context="No library selected",
            error=None,
        )
        view_model.set_workspace_materialization(
            has_active_source=False,
            calm_canvas_visible=True,
            browser_materialized=False,
            live_kit_materialized=False,
        )
        if state.phase == "cancelled":
            # Analysis UI ends after cancel (#742).
            view_model.set_analysis_state(
                AnalysisUiState(
                    folder_id=state.folder_id,
                    folder_path=state.folder_path,
                    token=state.token,
                    phase="idle",
                )
            )
        adapter.harmonic_match_open = False
        # #845 presentation flags must not sticky-survive analysis fail-closed.
        adapter.browser_collapsed = False
        adapter.live_kit_collapsed = False
        adapter.stop_preview()

    def dispatch_library_selection() -> None:
        if runtime_composition is None:
            return
        intent = library_model.state.selection_intent
        if intent is None:
            runtime_composition.clear_no_scope(
                "Library-Auswahl konnte nicht aufgelöst werden."
            )
            _sync_runtime_browser_state(view_model, adapter, runtime_composition)
            request_visible_browser_waveforms_from_window()
            refresh_browser_scope()
            bridge.refreshState()
            return

        refresh_target = None
        if analysis_coordinator is not None:
            try:
                refresh_target = runtime_composition.refresh_target(intent.scope)
            except Exception:
                refresh_target = None
        if refresh_target is not None and analysis_coordinator is not None:
            # #742 Option B: keep technical Source identity, defer visible panes.
            runtime_composition.dispatch_selection(intent)
            runtime_composition.clear_live_kit_disclosure()
            view_model.set_browser_state(
                rows=(),
                selected_index=-1,
                browser_context="Analysiere Quelle …",
                error=None,
            )
            view_model.set_workspace_materialization(
                has_active_source=False,
                calm_canvas_visible=False,
                browser_materialized=False,
                live_kit_materialized=False,
            )
            adapter.replace_browser_scope(intent.scope)
            analysis_coordinator.start(
                refresh_target.folder_id,
                str(refresh_target.normalized_path),
            )
            refresh_browser_scope()
            bridge.refreshState()
            layout_model.syncFromInteraction()
            return

        runtime_composition.dispatch_selection(intent)
        _sync_runtime_browser_state(view_model, adapter, runtime_composition)
        request_visible_browser_waveforms_from_window()
        refresh_browser_scope()
        bridge.refreshState()
        layout_model.syncFromInteraction()

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
            # Keep Qt item index in sync with navigation state (#836).
            library_model.ensureChildren(f"root:{folder_id}")
        # #742: Live Kit stays hidden after success; Browser materializes via sync.
        if runtime_composition is not None:
            runtime_composition.clear_live_kit_disclosure()
        if library_model.selectNode(target_node_id):
            # Force immediate materialization of analyzed source (no refresh loop).
            intent = library_model.state.selection_intent
            if intent is not None and runtime_composition is not None:
                runtime_composition.dispatch_selection(intent)
                _sync_runtime_browser_state(view_model, adapter, runtime_composition)
                request_visible_browser_waveforms_from_window()
                refresh_browser_scope()
                bridge.refreshState()
                layout_model.syncFromInteraction()
            else:
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
            # #742: technical registration + analysis first; activate after success.
            runtime_composition.clear_no_scope()
            view_model.set_browser_state(
                rows=(),
                selected_index=-1,
                browser_context="No library selected",
                error=None,
            )
            view_model.set_workspace_materialization(
                has_active_source=False,
                calm_canvas_visible=False,
                browser_materialized=False,
                live_kit_materialized=False,
            )
            if analysis_coordinator is not None:
                analysis_coordinator.start(
                    registration.folder_id,
                    str(registration.normalized_path),
                )
            refresh_browser_scope()
            bridge.refreshState()
            layout_model.syncFromInteraction()
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

    inbound_import_token = {"value": 0}
    inbound_import_workers: list[object] = []
    # token -> Library selection captured when the import job started
    inbound_import_selection_at_start: dict[int, str | None] = {}

    def _prune_inbound_import_workers() -> None:
        alive: list[object] = []
        for thread in inbound_import_workers:
            try:
                if hasattr(thread, "isRunning") and bool(thread.isRunning()):
                    alive.append(thread)
            except RuntimeError:
                # Qt C++ object already deleted via deleteLater.
                continue
        inbound_import_workers[:] = alive

    def can_accept_drop(node_id: str) -> bool:
        if runtime_composition is None:
            return False
        from .workbench_sample_dnd import can_accept_sample_drop

        return can_accept_sample_drop(
            node_id,
            library_db_path=runtime_composition.library_db_path,
        )

    def finish_inbound_import(token: int, node_id: str, result_obj: object) -> None:
        if token != inbound_import_token["value"]:
            inbound_import_selection_at_start.pop(token, None)
            return
        from .workbench_sample_dnd import ImportAnalyzeResult, format_inbound_status

        if not isinstance(result_obj, ImportAnalyzeResult):
            inbound_import_selection_at_start.pop(token, None)
            return
        # Captured at import start; kept for job hygiene / future diagnostics.
        inbound_import_selection_at_start.pop(token, None)
        status = format_inbound_status(result_obj)
        show_status = bool(
            result_obj.import_result.skipped_conflict
            or result_obj.import_result.failed
            or result_obj.import_result.error_code
            or result_obj.import_result.imported
        )
        current_selected = library_model.state.selected_node_id
        # Stale completion must not overwrite a newer Library selection (#768).
        selection_still_on_destination = current_selected == node_id
        # Never auto-audition newly imported samples; preserve focus semantics.
        if (
            result_obj.should_refresh_browser
            and selection_still_on_destination
            and library_model.selectNode(node_id)
        ):
            intent = library_model.state.selection_intent
            if intent is not None and runtime_composition is not None:
                runtime_composition.dispatch_selection(intent)
                if show_status and status:
                    state = runtime_composition.browser_state
                    runtime_composition.browser_state = Screen1BrowserState(
                        rows=state.rows,
                        selected_index=state.selected_index,
                        browser_context=state.browser_context,
                        scope=state.scope,
                        error=status,
                    )
                _sync_runtime_browser_state(view_model, adapter, runtime_composition)
                request_visible_browser_waveforms_from_window()
                refresh_browser_scope()
                bridge.refreshState()
                layout_model.syncFromInteraction()
                return
        if show_status and status:
            view_model.set_browser_state(
                rows=tuple(row.source_row for row in view_model.browser_rows),
                selected_index=view_model.selected_browser_index,
                browser_context=view_model.browser_context,
                error=status,
            )
            refresh_browser_scope()
            bridge.refreshState()

    def start_inbound_import(node_id: str, urls: list[str]) -> bool:
        if runtime_composition is None:
            return False
        from .workbench_sample_dnd import (
            import_and_analyze_dropped_files,
            resolve_drop_destination,
        )

        resolution = resolve_drop_destination(
            node_id,
            library_db_path=runtime_composition.library_db_path,
        )
        if not resolution.ok:
            message = resolution.error_message or "Drop-Ziel abgelehnt."
            view_model.set_browser_state(
                rows=tuple(row.source_row for row in view_model.browser_rows),
                selected_index=view_model.selected_browser_index,
                browser_context=view_model.browser_context,
                error=message,
            )
            refresh_browser_scope()
            bridge.refreshState()
            return False

        _prune_inbound_import_workers()
        inbound_import_token["value"] += 1
        token = inbound_import_token["value"]
        inbound_import_selection_at_start[token] = library_model.state.selected_node_id
        library_db_path = runtime_composition.library_db_path

        try:
            from PySide6.QtCore import QObject, QThread, Signal, Slot
        except ModuleNotFoundError:
            result = import_and_analyze_dropped_files(
                urls,
                destination_node_id=node_id,
                library_db_path=library_db_path,
            )
            finish_inbound_import(token, node_id, result)
            return bool(result.import_result.imported)

        class _InboundImportWorker(QObject):
            completed = Signal(int, str, object)
            failed = Signal(int, str, str)

            def __init__(self, job_token: int, dest_node: str, file_urls: list[str]) -> None:
                super().__init__()
                self._token = job_token
                self._node_id = dest_node
                self._urls = list(file_urls)

            @Slot()
            def run(self) -> None:
                try:
                    result = import_and_analyze_dropped_files(
                        self._urls,
                        destination_node_id=self._node_id,
                        library_db_path=library_db_path,
                    )
                except Exception as exc:
                    self.failed.emit(self._token, self._node_id, str(exc))
                else:
                    self.completed.emit(self._token, self._node_id, result)

        thread = QThread()
        worker = _InboundImportWorker(token, node_id, urls)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)

        def _on_completed(job_token: int, dest_node: str, result_obj: object) -> None:
            finish_inbound_import(job_token, dest_node, result_obj)
            thread.quit()
            _prune_inbound_import_workers()

        def _on_failed(job_token: int, dest_node: str, message: str) -> None:
            inbound_import_selection_at_start.pop(job_token, None)
            if job_token == inbound_import_token["value"]:
                view_model.set_browser_state(
                    rows=tuple(row.source_row for row in view_model.browser_rows),
                    selected_index=view_model.selected_browser_index,
                    browser_context=view_model.browser_context,
                    error=message or "Import fehlgeschlagen.",
                )
                refresh_browser_scope()
                bridge.refreshState()
            thread.quit()
            _prune_inbound_import_workers()

        worker.completed.connect(_on_completed)
        worker.failed.connect(_on_failed)
        worker.completed.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        inbound_import_workers.append(thread)
        thread.start()
        # Bounded status without invented percentages.
        view_model.set_browser_state(
            rows=tuple(row.source_row for row in view_model.browser_rows),
            selected_index=view_model.selected_browser_index,
            browser_context=view_model.browser_context,
            error="Importiere und analysiere Drop…",
        )
        refresh_browser_scope()
        bridge.refreshState()
        return True

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
    layout_model = create_elastic_layout_bridge(
        harmony_open=lambda: bool(adapter.harmonic_match_open),
        has_active_source=lambda: bool(adapter.view_model.has_active_source),
        library_revealed=lambda: bool(adapter.view_model.library_revealed),
        # #845: presentation collapse is orthogonal to progressive disclosure.
        live_kit_visible=lambda: (
            bool(adapter.view_model.live_kit_materialized)
            and not bool(adapter.live_kit_collapsed)
        ),
        browser_visible=lambda: not bool(adapter.browser_collapsed),
    )

    def on_interaction_state_changed() -> None:
        refresh_screen_model()
        # Recompute widths before QML reacts to state_changed so RowLayout
        # never sees a 3-panel width set with a third handle visible.
        layout_model.syncFromInteraction()
        # #908: Live Kit mutations materialize/reconcile bottom Rack projection.
        rack_bridge = getattr(engine, "_screen1_channel_rack_bridge", None)
        if rack_bridge is not None:
            rack_bridge.refresh()

    channel_rack_bridge = _qml_channel_rack_bridge(
        channel_rack_controller,
        resolve_selected_sample_path=lambda: (
            str(
                adapter.view_model.browser_rows[
                    adapter.view_model.selected_browser_index
                ].source_row.path
            )
            if (
                0
                <= int(adapter.view_model.selected_browser_index)
                < len(adapter.view_model.browser_rows)
            )
            else None
        ),
    )
    transport_bridge = _qml_transport_bridge(session_transport)
    persistence_bridge = _qml_session_persistence_bridge(session)

    def open_channel_rack() -> None:
        # #908: materialize bottom Rack via ensure_state; quiet audition through
        # session focus claim only when playback is requested — not for open.
        if session is not None:
            session.channel_rack.ensure_state()
            channel_rack_bridge.refresh()
            return
        channel_rack_bridge.openChannelRack()

    def return_to_screen1() -> None:
        if session is not None:
            session.return_to_screen1()
            channel_rack_bridge.refresh()
            return
        channel_rack_bridge.returnToScreen1()

    bridge = _qml_interaction_bridge(
        adapter,
        on_state_changed=on_interaction_state_changed,
        on_browser_rows_changed=refresh_browser_rows,
        on_waveform_request=request_waveforms,
        on_harmony_waveform_request=request_harmony_waveforms,
        on_open_channel_rack=open_channel_rack,
        on_return_to_screen1=return_to_screen1,
    )
    adapter._runtime_composition = runtime_composition
    engine._screen1_analysis_fail_closed = lambda: _analysis_fail_closed(
        AnalysisUiState(phase="error", error=view_model.analysis_error)
    )
    library_bridge = _qml_library_interaction_bridge(
        library_model,
        on_selection=dispatch_library_selection,
        on_add_source=register_source,
        on_prepare_remove=prepare_remove,
        on_confirm_remove=confirm_remove,
        on_can_accept_drop=can_accept_drop,
        on_import_drop=start_inbound_import,
    )
    if runtime_composition is not None:
        library_model.selection_invalidated.connect(dispatch_library_selection)
    engine.rootContext().setContextProperty("screenModel", screen_model)
    engine.rootContext().setContextProperty("interactionModel", bridge)
    engine.rootContext().setContextProperty("layoutModel", layout_model)
    engine.rootContext().setContextProperty("libraryTreeModel", library_model)
    engine.rootContext().setContextProperty("libraryInteraction", library_bridge)
    engine.rootContext().setContextProperty("channelRackModel", channel_rack_bridge)
    engine.rootContext().setContextProperty("tempoSyncModel", transport_bridge)
    engine.rootContext().setContextProperty(
        "sessionPersistenceModel", persistence_bridge
    )
    engine._screen1_session_persistence_bridge = persistence_bridge
    theme_authority = _qml_theme_authority_bridge()
    engine.rootContext().setContextProperty("themeAuthority", theme_authority)
    engine.rootContext().setContextProperty(
        "screen1BackgroundUrl",
        screen1_background_url(),
    )
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
    engine._screen1_layout_model = layout_model
    engine._screen1_library_model = library_model
    engine._screen1_library_bridge = library_bridge
    engine._screen1_screen_model = screen_model
    engine._screen1_theme_authority = theme_authority
    engine._screen1_live_kit = live_kit
    engine._screen1_session = session
    engine._screen1_channel_rack = channel_rack_controller
    engine._screen1_channel_rack_bridge = channel_rack_bridge
    engine._screen1_transport = session_transport
    engine._screen1_transport_bridge = transport_bridge
    engine._screen1_runtime_composition = runtime_composition
    engine._screen1_analysis_coordinator = analysis_coordinator
    engine._screen1_finish_inbound_import = finish_inbound_import
    engine._screen1_inbound_import_token = inbound_import_token
    engine._screen1_inbound_import_selection_at_start = (
        inbound_import_selection_at_start
    )
    engine._screen1_inbound_import_workers = inbound_import_workers
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

    channel_rack_timer = QTimer()
    channel_rack_timer.setInterval(20)

    def _tick_channel_rack() -> None:
        if channel_rack_bridge.playing:
            channel_rack_bridge.tickPlayback()
        else:
            channel_rack_timer.stop()

    channel_rack_timer.timeout.connect(_tick_channel_rack)
    channel_rack_bridge.state_changed.connect(
        lambda: channel_rack_timer.start()
        if channel_rack_bridge.playing
        else channel_rack_timer.stop()
    )
    engine._screen1_channel_rack_timer = channel_rack_timer
    request_visible_browser_waveforms_from_window()
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


def apply_clean_start_launch(
    view_model: Screen1QmlViewModel,
    runtime_composition: Screen1QmlRuntimeComposition,
    *,
    state_dir: Path | None = None,
    env=None,
    source_available: Callable[[str], bool] | None = None,
) -> WorkspaceMode:
    """Apply First-use Clean Start or Returning Workspace for normal launch.

    Reuses persisted library Sources (#762). Never restores sample selection,
    preview, harmony, Live Kit disclosure, or scroll. Missing/offline preferred
    Sources fall through to the next available persisted Source without deleting
    registration.
    """
    from .workbench_controller import get_workbench_library_folders
    from .workbench_library_navigation import LibraryAvailability

    loaded = load_startup_preset(state_dir=state_dir, env=env)

    def _ensure_source_children() -> None:
        tree = runtime_composition.library_tree
        tree.fetch_children("container:sample-sources")

    def _default_available(node_id: str) -> bool:
        _ensure_source_children()
        tree = runtime_composition.library_tree
        node = tree.node(node_id)
        if node is None:
            return False
        if not node.selectable:
            return False
        availability = getattr(node, "availability", None)
        if availability is LibraryAvailability.OFFLINE:
            return False
        if availability is LibraryAvailability.ERROR:
            return False
        return True

    _ensure_source_children()
    persisted_ids: list[str] = []
    for folder in get_workbench_library_folders(
        library_db_path=runtime_composition.library_db_path
    ):
        node_id = f"root:{folder.id}"
        persisted_ids.append(node_id)
    # Keep library order (last_opened_at) as the deterministic fallback authority.
    # Tree display order may sort by label; returning policy must not.

    launch = resolve_launch_workspace(
        preset=loaded.preset,
        source_available=source_available or _default_available,
        persisted_source_node_ids=persisted_ids,
    )
    view_model.state_id = "screen1-default-3panel"
    runtime_composition.clear_no_scope()
    runtime_composition.clear_live_kit_disclosure()
    view_model.set_browser_state(
        rows=(),
        selected_index=-1,
        browser_context="No library selected",
        error=None,
    )
    view_model.set_workspace_materialization(
        has_active_source=False,
        calm_canvas_visible=True,
        browser_materialized=False,
        live_kit_materialized=False,
    )
    view_model.set_library_revealed(False)
    view_model.harmony_rows = ()
    view_model.harmony_anchor = ""
    view_model.harmony_status = "Harmonic Match ist ausgeschaltet."

    if launch.mode is WorkspaceMode.ACTIVE_SOURCE and launch.source_node_id:
        intent = runtime_composition.library_tree.select(launch.source_node_id)
        if intent is not None:
            runtime_composition.dispatch_selection(intent)
            if runtime_composition.has_active_source:
                state = runtime_composition.browser_state
                view_model.set_browser_state(
                    rows=state.rows,
                    selected_index=-1,
                    browser_context=state.browser_context,
                    error=state.error,
                    favorite_paths=_favorite_path_set(
                        db_path=getattr(runtime_composition, "library_db_path", None)
                    ),
                )
                view_model.set_workspace_materialization(
                    has_active_source=True,
                    calm_canvas_visible=False,
                    browser_materialized=True,
                    live_kit_materialized=False,
                )
                # #762: Active Source materialises Library + Browser together.
                view_model.set_library_revealed(True)
                return WorkspaceMode.ACTIVE_SOURCE
            # Offline/unloadable scope: keep registration, stay Clean Start.
            runtime_composition.clear_no_scope()
        # Missing/unselectable Source: remain Clean Start (fail soft).
    return WorkspaceMode.CLEAN_START


def run_qml_screen1(*, state_id: str = "screen1-default-3panel") -> int:
    """Open the optional production Screen-1 renderer without changing Tk defaults."""
    composition = Screen1QmlRuntimeComposition(
        library_db_path=workbench_library_db_path(),
    )
    # Compose exactly one WorkbenchSession inside ``_qml_engine`` (default
    # branch) so the established ``view_model`` + ``runtime_composition`` call
    # shape stays intact for test seams and production alike.
    view_model = Screen1QmlViewModel(
        state_id=state_id,
        library_labels=(),
        browser_rows=(),
        selected_browser_index=-1,
        harmony_rows=(),
        live_kit_groups=(),
    )
    view_model.library_tree = composition.library_tree
    apply_clean_start_launch(view_model, composition)
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
    "SCREEN1_BACKGROUND_REFERENCE_RELATIVE",
    "SCREEN1_BACKGROUND_REFERENCE_SHA256",
    "SCREEN1_QML_STATE_IDS",
    "Screen1QmlInteractionAdapter",
    "Screen1QmlViewModel",
    "apply_clean_start_launch",
    "qml_runtime_available",
    "run_qml_screen1",
    "screen1_background_reference_path",
    "screen1_background_url",
]
