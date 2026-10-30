"""Optional production Qt Quick Workbench shell (Screen 1 + Screen 2).

This module owns only renderer-facing state, interaction routing, and Qt engine
startup. Musical truth for Screen 2 stays in ``ChannelRackController`` /
``channel_rack``. Fixture, evidence, and synthetic probe orchestration
deliberately live in :mod:`src.workbench_qml_spike`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction
import inspect
import json
import math
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .workbench_controller import WorkbenchRow, filter_workbench_rows
from .workbench_browser_rows import (
    BACKGROUND_ENRICHMENT,
    CURRENT_VISIBLE,
    BoundedBackgroundWaveformLoader,
    BoundedLazyWaveformCache,
    WaveformCacheResult,
    WaveformDecodeResult,
    waveform_pump_decision,
)
from .workbench_harmony import (
    HarmonicMatchLibraryController,
    HarmonySuggestion,
    harmonic_match_key_for_row,
)
from .workbench_live_kit import (
    LiveKitPresentationState,
    LiveKitState,
    live_kit_group_display_name,
    live_kit_slot_display_name,
)
from .workbench_live_kit_edit import (
    LIVE_KIT_HUD_MODE_HIDDEN,
    LIVE_KIT_HUD_MODE_MANUAL,
    LIVE_KIT_HUD_MODE_TRANSIENT,
    LIVE_KIT_HUD_TRANSIENT_MS,
    edit_docking_materialization_for_live_kit,
    try_save_live_kit_visibility_preference,
    visible_live_kit_slot_keys,
)
from .workbench_internal_sample_dnd import (
    KIND_INTERNAL_SAMPLE,
    InternalSampleDropIntent,
    InternalSampleDropResult,
    InternalSampleDropSession,
    LiveKitAssignmentTarget,
    apply_internal_sample_drop,
    descriptor_from_row,
    list_visible_live_kit_targets,
    parse_internal_sample_descriptor,
)
from .workbench_live_kit_export import LiveKitExportResult, export_live_kit
from .workbench_library import (
    WAVEFORM_POINT_BUDGET,
    WaveformEnrichmentCandidate,
    list_favorite_sample_paths,
    list_waveform_enrichment_candidates,
    load_valid_waveform_artifacts,
    store_waveform_artifact,
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
from .workbench_editing import audio_source_frame_info
from .workbench_native_window_chrome import wire_theme_authority
from .workbench_window_placement import show_window_on_primary_screen

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
class BrowserLoopProjectionSnapshot:
    """Read-only projection of the Python-owned persistent Browser Loop (#1285)."""

    active: bool
    owner_path: str
    owner_name: str
    progress: float
    bar_count: int
    bar_positions: tuple[float, ...]
    reduced_capability_reason: str
    playback_available: bool
    waveform_aligned: bool
    waveform_start_ratio: float
    waveform_end_ratio: float

    @classmethod
    def idle(cls) -> "BrowserLoopProjectionSnapshot":
        return cls(
            active=False,
            owner_path="",
            owner_name="",
            progress=0.0,
            bar_count=0,
            bar_positions=(),
            reduced_capability_reason="",
            playback_available=False,
            waveform_aligned=False,
            waveform_start_ratio=0.0,
            waveform_end_ratio=1.0,
        )


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

    def reproject(self) -> None:
        """Rebuild the renderer projection from the canonical kit state.

        The frozen #1072 drop contract mutates ``LiveKitState`` directly rather
        than routing through :meth:`assign`; this re-derives the renderer-only
        group shape so an accepted drop is visible immediately (audition /
        remove / replace controls included) without a second kit truth.
        """
        self._groups = self._project()

    def clear_slot(self, group: str, slot: str, *, notify: bool = True) -> bool:
        cleared = self._state.clear_slot(group, slot, notify=notify)
        if cleared:
            self._groups = self._project()
        return cleared


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
    if not favorites:
        return False
    return os.path.normcase(os.path.normpath(path)) in favorites


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


def _waveform_fingerprint(row: WorkbenchRow) -> tuple[int, int] | None:
    details = _row_details(row)
    try:
        size_bytes = int(details["source_size_bytes"])
        mtime_ns = int(details["source_mtime_ns"])
    except (KeyError, TypeError, ValueError):
        return None
    if size_bytes < 0 or mtime_ns < 0:
        return None
    return size_bytes, mtime_ns


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
        favorites = {
            os.path.normcase(os.path.normpath(path))
            for path in (favorite_paths or ())
        }
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
        else:
            updated_visible: list[QmlBrowserRow] = []
            for row in self.browser_rows:
                if str(row.source_row.path) == path and row.waveform_envelope != envelope:
                    row = replace(row, waveform_envelope=envelope)
                    changed = True
                updated_visible.append(row)
            if changed:
                self.browser_rows = tuple(updated_visible)
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
                    "displayName": live_kit_group_display_name(group.name),
                    "active": group.active,
                    "slots": [
                        {
                            "name": slot.name,
                            "displayName": live_kit_slot_display_name(
                                group.name, slot.name
                            ),
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
        # #1077 / #954 / #1207: Live Kit HUD overlay. Default hidden; production
        # wiring may apply a persisted *manual* visibility preference after
        # construction. Musical assignments never force a HUD open on their own.
        self._live_kit_drawer_open = False
        self._live_kit_auto_disclosure_consumed = False
        # #1207 presentation ownership: hidden | transient | manual.
        self._live_kit_hud_mode = LIVE_KIT_HUD_MODE_HIDDEN
        self._live_kit_hud_generation = 0
        self._live_kit_last_feedback_sample = ""
        self._live_kit_last_feedback_group = ""
        self._live_kit_last_feedback_slot = ""
        self._live_kit_last_feedback_mutation = ""
        # Session UI height authority: 0 = auto (row-derived); otherwise clamped px.
        self._live_kit_user_height_px = 0
        # Session desired visibility (None until first *manual* open/close).
        # Transient Add feedback must not claim restart reopen authority (#1207).
        # Persistence is best-effort; restore must not reopen against an
        # in-session close.
        self._live_kit_visibility_desired: bool | None = None
        # Compatibility projection for older bridge consumers.  It mirrors the
        # overlay state and must not become a second presentation authority.
        self.live_kit_collapsed = True
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
        self._browser_loop: Any | None = None
        self._browser_loop_waveform_window_cache: tuple[tuple[str, int, int], tuple[bool, float, float]] | None = None
        self._browser_loop_context_status = ""
        self._on_browser_loop_started: Callable[[], object] | None = None
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
        # #1121 projection only: #1070 remains the single layout/lock owner.
        self._workspace_panel_docking_enabled = False
        self._edit_docking_state: object | None = None
        # #1072/#1123 internal Sample DnD state
        self._internal_sample_dnd_enabled = False
        self._internal_sample_drop_session: "InternalSampleDropSession | None" = None
        # #1080 Slice A: canonical #1076 Arrangement feature gate (route only).
        self._arrangement_mode_enabled = False
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

    @property
    def browser_loop_context_status(self) -> str:
        return self._browser_loop_context_status

    def open_sample_context(self, index: int) -> WorkbenchRow:
        """Resolve visible row index once into a stable context target (#839)."""
        if not 0 <= index < len(self.view_model.browser_rows):
            raise IndexError("Browser-Zeilenindex außerhalb des sichtbaren Modells.")
        row = self.view_model.browser_rows[index].source_row
        self._sample_context_target = row
        self._browser_loop_context_status = ""
        return row

    def close_sample_context(self) -> None:
        """Clear session-transient sample context target (#839)."""
        had_target = self._sample_context_target is not None
        self._sample_context_target = None
        self._browser_loop_context_status = ""
        if had_target and self._on_sample_context_closed is not None:
            self._on_sample_context_closed()

    def _request_add_to_kit_row(self, row: WorkbenchRow) -> WorkbenchRow:
        """Shared Add-to-Kit intent seam for index and context routes (#839).

        #742/#1077: Add-to-Kit materializes Live Kit disclosure. Pending-add
        expands chooser geometry without forcing drawer_open, so a manual
        close (#954) remains respected on later assignments. Visibility
        predicates still treat pending-add as presentation-open for #1070/#1072.
        """
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

    def bind_browser_loop(self, browser_loop: Any) -> None:
        """Bind the session-owned persistent Browser Loop role (#1284)."""
        self._browser_loop = browser_loop

    def browser_loop_projection_snapshot(self) -> BrowserLoopProjectionSnapshot:
        """Derive immutable renderer telemetry from the authoritative Loop owner."""
        owner = self._browser_loop
        if owner is None:
            return BrowserLoopProjectionSnapshot.idle()
        row = getattr(owner, "owner_row", None)
        extent = getattr(owner, "extent", None)
        if row is None or extent is None:
            return BrowserLoopProjectionSnapshot.idle()

        start = int(getattr(extent, "source_start_frame", 0))
        end = int(getattr(extent, "source_end_frame_exclusive", start))
        span = max(0, end - start)
        downbeats = tuple(int(frame) for frame in getattr(extent, "downbeat_frames", ()) or ())
        if span > 0:
            bar_positions = tuple(
                min(1.0, max(0.0, (frame - start) / float(span))) for frame in downbeats
            )
        else:
            bar_positions = ()

        phase = owner.current_source_phase_frame()
        if phase is None or span <= 0:
            progress = 0.0
        else:
            raw_progress = (int(phase) - start) / float(span)
            progress = min(math.nextafter(1.0, 0.0), max(0.0, raw_progress))

        reason = str(getattr(owner, "reduced_capability_reason", None) or "")
        active = bool(getattr(owner, "is_active", True))
        waveform_key = (str(row.path), start, end)
        cached_window = self._browser_loop_waveform_window_cache
        if cached_window is None or cached_window[0] != waveform_key:
            try:
                total_frames, _source_rate = audio_source_frame_info(Path(row.path))
                total = int(total_frames)
            except Exception:
                total = 0
            aligned = bool(total > 0 and 0 <= start < end <= total)
            if aligned:
                waveform_window = (True, start / float(total), end / float(total))
            else:
                waveform_window = (False, 0.0, 1.0)
            self._browser_loop_waveform_window_cache = (waveform_key, waveform_window)
        else:
            waveform_window = cached_window[1]
        waveform_aligned, waveform_start_ratio, waveform_end_ratio = waveform_window
        return BrowserLoopProjectionSnapshot(
            active=active,
            owner_path=str(row.path),
            owner_name=str(row.display_name),
            progress=float(progress),
            bar_count=int(getattr(extent, "bar_count", 0) or 0),
            bar_positions=bar_positions,
            reduced_capability_reason=reason,
            playback_available=bool(active and not reason),
            waveform_aligned=bool(waveform_aligned),
            waveform_start_ratio=float(waveform_start_ratio),
            waveform_end_ratio=float(waveform_end_ratio),
        )

    def refresh_browser_loop_projection(self) -> BrowserLoopProjectionSnapshot:
        """Re-read authoritative Loop telemetry for presentation."""
        return self.browser_loop_projection_snapshot()

    def set_on_browser_loop_started(self, callback: Callable[[], object] | None) -> None:
        """Optional hook to start the recurring Loop scheduler timer (#1284)."""
        self._on_browser_loop_started = callback

    def request_loop_on_for_row(self, row: WorkbenchRow) -> Any:
        """Canonical Loop ON seam for a concrete resolved ``WorkbenchRow`` (#1284)."""
        if self._browser_loop is None:
            raise RuntimeError("Browser Loop runtime is not bound")
        result = self._browser_loop.loop_on(row)
        if getattr(result, "ok", False) and self._on_browser_loop_started is not None:
            self._on_browser_loop_started()
        return result

    def request_loop_off(self) -> Any:
        """Clear the persistent Loop role only (#1284)."""
        if self._browser_loop is None:
            raise RuntimeError("Browser Loop runtime is not bound")
        return self._browser_loop.loop_off()

    def request_context_loop_on(self) -> WorkbenchRow:
        """LOOP ON for ``sample_context_target`` without re-resolving an index (#1284)."""
        target = self._sample_context_target
        if target is None:
            raise ValueError("No sample context target")
        result = self.request_loop_on_for_row(target)
        if not getattr(result, "ok", False):
            raise ValueError(getattr(result, "message", "LOOP ON rejected"))
        self.close_sample_context()
        return target

    def request_context_loop_off(self) -> None:
        """LOOP OFF via context menu; clears Loop role only (#1284)."""
        self.request_loop_off()
        self.close_sample_context()

    def request_context_loop_toggle(self) -> Any:
        """Toggle Loop for the stable context target without consulting QML identity."""
        from .browser_loop_playback import BrowserLoopResult

        target = self._sample_context_target
        if target is None:
            result = BrowserLoopResult(
                ok=False,
                message="LOOP unavailable: no sample context target.",
                reason_code="NO_CONTEXT_TARGET",
            )
            self._browser_loop_context_status = result.message
            return result

        snapshot = self.browser_loop_projection_snapshot()
        if snapshot.active and snapshot.owner_path == str(target.path):
            result = self.request_loop_off()
        else:
            result = self.request_loop_on_for_row(target)

        if getattr(result, "ok", False):
            self._browser_loop_context_status = ""
            self.close_sample_context()
        else:
            self._browser_loop_context_status = str(
                getattr(result, "message", "")
                or getattr(result, "reason_code", "LOOP unavailable")
            )
        return result

    def _reveal_live_kit_pane(self) -> None:
        """UI disclosure only — does not mutate Live-Kit domain assignments."""
        composition = self._runtime_composition
        if composition is None:
            return
        composition.reveal_live_kit()
        live_kit_mat = bool(composition.live_kit_materialized)
        if not live_kit_mat and self.view_model.live_kit_materialized:
            # Preserve already-materialized session/harness when composition
            # has no active Source yet (injected adapters / scope recovery).
            live_kit_mat = True
        self.view_model.set_workspace_materialization(
            has_active_source=self.view_model.has_active_source,
            calm_canvas_visible=self.view_model.calm_canvas_visible,
            browser_materialized=self.view_model.browser_materialized,
            live_kit_materialized=live_kit_mat,
        )

    @property
    def internal_sample_dnd_enabled(self) -> bool:
        """Feature gate for internal Sample drag-and-drop onto Live Kit targets."""
        return self._internal_sample_dnd_enabled

    def internal_sample_drag_enabled(self) -> bool:
        """Return whether internal Sample DnD is enabled (feature gate)."""
        return self._internal_sample_dnd_enabled

    def _internal_sample_features(self):
        """Canonical feature snapshot read by the frozen #1072 contract.

        The contract only inspects ``internal_sample_dnd_enabled``; reuse the
        canonical settings type instead of a second flag object.
        """
        from .workbench_feature_settings import WorkbenchFeatureSettings

        return WorkbenchFeatureSettings(
            internal_sample_dnd_enabled=bool(self._internal_sample_dnd_enabled)
        )

    def _internal_sample_projected_rows(self, source_surface: str) -> tuple:
        if source_surface == "browser":
            return tuple(self.view_model.browser_rows)
        if source_surface == "harmony":
            return tuple(self.view_model.harmony_rows)
        return ()

    def _internal_sample_source_row(self, row_index: int, source_surface: str):
        rows = self._internal_sample_projected_rows(source_surface)
        if not isinstance(row_index, int) or isinstance(row_index, bool):
            return None
        if not 0 <= row_index < len(rows):
            return None
        return rows[row_index].source_row

    def _internal_sample_catalog(self) -> tuple:
        """Visible Browser/Harmony catalog for #1072 resolution.

        Dedupes only genuine re-projections of the *same underlying sample*
        (identical absolute path), so a sample visible on both surfaces is
        handed to the contract once and does not become a self-inflicted
        ambiguity. Distinct underlying samples that merely share a normalized
        ``relative_path`` are kept separate, letting the authoritative resolver
        fail closed with ``ambiguous_sample`` instead of silently assigning the
        wrong sample.
        """
        seen: set[str] = set()
        catalog: list = []
        for projected in (
            *self.view_model.browser_rows,
            *self.view_model.harmony_rows,
        ):
            row = projected.source_row
            identity = self._internal_sample_row_identity(row)
            if identity is not None and identity in seen:
                continue
            if identity is not None:
                seen.add(identity)
            catalog.append(row)
        return tuple(catalog)

    @staticmethod
    def _internal_sample_row_identity(row: object) -> str | None:
        """Underlying-sample identity (normalized absolute path) or ``None``.

        ``None`` when no stable path is available, so unidentified rows are
        never collapsed together and cannot hide an ambiguity.
        """
        raw = getattr(row, "path", None)
        if not isinstance(raw, str):
            return None
        text = raw.strip()
        if not text:
            return None
        return os.path.normcase(os.path.normpath(text))

    def _internal_sample_visible_slot_keys(self) -> tuple[tuple[str, str], ...]:
        """Authoritative visible (group, slot) keys (#1072/#1073).

        Reuses :meth:`visible_live_kit_slot_keys` so internal Sample drops honour
        the same effective visibility as every other Live Kit path: the pending
        Add-to-Kit chooser (#954) can open the slots while the drawer preference
        stays closed, and a collapsed Browser host (#1077) advertises none.
        """
        return self.visible_live_kit_slot_keys()

    def _internal_sample_drop_session_owner(self) -> InternalSampleDropSession:
        """One replay session per adapter lifecycle — never per drop."""
        session = self._internal_sample_drop_session
        if session is None:
            session = InternalSampleDropSession()
            self._internal_sample_drop_session = session
        return session

    def build_internal_sample_descriptor(
        self, row_index: int, source_surface: str
    ) -> dict | None:
        """Map a visible Browser/Harmony row onto the #1072 descriptor contract.

        Returns the QML-safe transport projection, or ``None`` fail-closed when
        the feature is off, the index/surface is invalid, or the contract
        rejects the row identity.
        """
        if not self._internal_sample_dnd_enabled:
            return None
        row = self._internal_sample_source_row(row_index, source_surface)
        if row is None:
            return None
        descriptor = descriptor_from_row(
            row,
            source_surface=source_surface,
            features=self._internal_sample_features(),
        )
        if descriptor is None:
            return None
        return descriptor.as_transport_dict()

    def visible_live_kit_drop_targets(self) -> list:
        """Serialized #1072 visible Live Kit targets for the current projection."""
        if not self._internal_sample_dnd_enabled:
            return []
        targets = list_visible_live_kit_targets(
            features=self._internal_sample_features(),
            live_kit_materialized=bool(self.view_model.live_kit_materialized),
            visible_slot_keys=self._internal_sample_visible_slot_keys(),
        )
        return [
            {
                "kind": target.kind,
                "group": target.group,
                "slot": target.slot,
                "visible": target.visible,
            }
            for target in targets
        ]

    def apply_internal_sample_drop(
        self,
        relative_path: str,
        source_surface: str,
        group: str,
        slot: str,
        delivery_id: str,
    ) -> dict:
        """Map structured QML drop args onto the #1072 descriptor contract.

        Retained for the structured adapter surface; the transported payload
        path (:meth:`apply_internal_sample_drop_payload`) is authoritative.
        """
        return self.apply_internal_sample_drop_payload(
            {
                "kind": KIND_INTERNAL_SAMPLE,
                "relative_path": relative_path,
                "source_surface": source_surface,
            },
            group,
            slot,
            delivery_id,
        )

    def apply_internal_sample_drop_payload(
        self,
        descriptor_payload: Any,
        group: str,
        slot: str,
        delivery_id: str,
    ) -> dict:
        """Validate the *full* transported descriptor and route one drop.

        Python stays authoritative for descriptor identity: a foreign or
        malformed payload (for example a ``panel_move`` docking descriptor)
        fails closed through :func:`parse_internal_sample_descriptor` and never
        reaches the kit. On an accepted mutation the renderer projection is
        rebuilt from the canonical kit state immediately.
        """
        if not self._internal_sample_dnd_enabled:
            return {"accepted": False, "mutation": None, "reason": "feature_disabled"}
        if self._live_kit is None:
            return {"accepted": False, "mutation": None, "reason": "no_live_kit"}
        descriptor = parse_internal_sample_descriptor(descriptor_payload)
        if descriptor is None:
            return {"accepted": False, "mutation": None, "reason": "invalid_descriptor"}
        intent = InternalSampleDropIntent(
            descriptor=descriptor,
            target=LiveKitAssignmentTarget(group=str(group), slot=str(slot)),
            delivery_id=str(delivery_id),
        )
        result = apply_internal_sample_drop(
            intent,
            kit=self._live_kit.state,
            catalog=self._internal_sample_catalog(),
            features=self._internal_sample_features(),
            live_kit_materialized=bool(self.view_model.live_kit_materialized),
            visible_slot_keys=self._internal_sample_visible_slot_keys(),
            session=self._internal_sample_drop_session_owner(),
        )
        if result.accepted and result.mutation is not None:
            # The #1072 contract mutates LiveKitState directly; re-project the
            # canonical state so the new slot (audition/remove/replace) is
            # visible immediately instead of only after an unrelated toggle.
            self._live_kit.reproject()
            self._sync_live_kit_projection()
            # A replaced/cleared destination slot must drop its audition
            # projection, mirroring assign_live_kit_slot/remove_live_kit_slot, so
            # the newly assigned sample is never shown as the auditioning one
            # while the preview owner may still be playing the previous sample.
            if self._auditioning_live_kit_slot == (str(group), str(slot)):
                self._clear_live_kit_audition_projection()
            assigned = self._live_kit.state.assignment_for(str(group), str(slot))
            sample_name = (
                assigned.display_name if assigned is not None else descriptor.relative_path
            )
            mutation = "replace" if result.mutation == "replace" else "add"
            if result.mutation == "clear":
                mutation = "remove"
            self._record_live_kit_feedback(
                sample_name=str(sample_name or ""),
                group=str(group),
                slot=str(slot),
                mutation=mutation,
            )
            if mutation != "remove":
                self._present_live_kit_after_mutation()
        return self._project_internal_sample_drop_result(result)

    @staticmethod
    def _project_internal_sample_drop_result(
        result: InternalSampleDropResult,
    ) -> dict:
        projected = {
            "accepted": bool(result.accepted),
            "mutation": result.mutation,
            "reason": result.reason,
        }
        if result.evidence is not None:
            projected["evidence"] = result.evidence
        return projected

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

    @property
    def workspace_panel_docking_enabled(self) -> bool:
        """Project the canonical functional #1070 docking feature flag."""
        return bool(self._workspace_panel_docking_enabled)

    @property
    def arrangement_mode_enabled(self) -> bool:
        """Project the canonical #1076/#1080 Arrangement feature gate.

        Route visibility only: eligibility and the transition itself stay
        owned by ``WorkbenchSession`` (#1078); the session re-checks the
        canonical settings before any mode change.
        """
        return bool(self._arrangement_mode_enabled)

    def load_workspace_layout_state(
        self,
        *,
        state_dir: Path | None = None,
        env: Mapping[str, str] | None = None,
    ):
        """Load the Python-owned #1070 topology/lock snapshot fail-closed."""
        from .workbench_edit_docking import (
            DEFAULT_EDIT_DOCKING_STATE,
            load_edit_docking_state,
        )

        try:
            loaded = load_edit_docking_state(state_dir=state_dir, env=env)
        except OSError:
            loaded = DEFAULT_EDIT_DOCKING_STATE
        self._edit_docking_state = loaded
        return loaded

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
        self._workspace_panel_docking_enabled = bool(
            loaded.workspace_panel_docking_enabled
        )
        self._internal_sample_dnd_enabled = bool(loaded.internal_sample_dnd_enabled)
        self._arrangement_mode_enabled = bool(loaded.arrangement_mode_enabled)
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
            load_workbench_feature_settings,
            replace_workbench_feature_settings,
            save_workbench_feature_settings,
        )

        value = bool(enabled)
        current = load_workbench_feature_settings(state_dir=state_dir, env=env)
        updated = replace_workbench_feature_settings(
            current,
            gesture_rack_apply_enabled=value,
        )
        if save_workbench_feature_settings(
            updated,
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
        overwrites exactly the explicit target slot. Successful mutation opens
        transient Kit HUD feedback (#1207) unless the HUD is already manual.
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
            occupied = self._live_kit.state.assignment_for(group, slot) is not None
            self._live_kit.assign(group, slot, row)
        except ValueError:
            return False
        self._pending_live_kit_row = None
        self._sync_live_kit_projection()
        if self._auditioning_live_kit_slot == (group, slot):
            self._clear_live_kit_audition_projection()
        self._record_live_kit_feedback(
            sample_name=row.display_name,
            group=group,
            slot=slot,
            mutation="replace" if occupied else "add",
        )
        self._present_live_kit_after_mutation()
        self._close_harmonic_match_presentation()
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

    @property
    def live_kit_drawer_open(self) -> bool:
        """Whether the #1207 Kit HUD overlay is visibly open."""
        return self._live_kit_drawer_open

    @property
    def live_kit_auto_disclosure_consumed(self) -> bool:
        """Whether this session has consumed automatic Add feedback at least once."""
        return self._live_kit_auto_disclosure_consumed

    @property
    def live_kit_hud_mode(self) -> str:
        """Presentation ownership: hidden | transient | manual (#1207)."""
        return self._live_kit_hud_mode

    @property
    def live_kit_hud_generation(self) -> int:
        """Monotonic token so stale transient timers cannot close a newer HUD."""
        return int(self._live_kit_hud_generation)

    @property
    def live_kit_transient_ms(self) -> int:
        return int(LIVE_KIT_HUD_TRANSIENT_MS)

    @property
    def live_kit_last_feedback_sample(self) -> str:
        return self._live_kit_last_feedback_sample

    @property
    def live_kit_last_feedback_group(self) -> str:
        return self._live_kit_last_feedback_group

    @property
    def live_kit_last_feedback_slot(self) -> str:
        return self._live_kit_last_feedback_slot

    @property
    def live_kit_last_feedback_mutation(self) -> str:
        return self._live_kit_last_feedback_mutation

    def _record_live_kit_feedback(
        self,
        *,
        sample_name: str,
        group: str,
        slot: str,
        mutation: str,
    ) -> None:
        """Store authoritative mutation context for HUD projection only."""
        self._live_kit_last_feedback_sample = str(sample_name or "")
        self._live_kit_last_feedback_group = str(group or "")
        self._live_kit_last_feedback_slot = str(slot or "")
        self._live_kit_last_feedback_mutation = str(mutation or "")

    def _present_live_kit_after_mutation(self) -> None:
        """Open or refresh Kit HUD after a successful canonical mutation.

        Manual ownership stays manual (no auto-dismiss). Otherwise open/refresh
        transient feedback without claiming restart reopen preference (#1207).
        """
        self._reveal_live_kit_pane()
        self._live_kit_auto_disclosure_consumed = True
        self._live_kit_drawer_open = True
        self.live_kit_collapsed = False
        if self._live_kit_hud_mode == LIVE_KIT_HUD_MODE_MANUAL:
            return
        self._live_kit_hud_mode = LIVE_KIT_HUD_MODE_TRANSIENT
        self._live_kit_hud_generation += 1

    def open_live_kit_manual(self) -> bool:
        """Deliberate user open — persistent until explicit close (#1207)."""
        has_assignments = self._live_kit is not None and any(
            self._live_kit.state.assignment_for(group, slot) is not None
            for group in self._live_kit.state.groups()
            for slot in self._live_kit.state.slots_for(group)
        )
        if not bool(self.view_model.live_kit_materialized) and not has_assignments:
            return False
        self._live_kit_hud_mode = LIVE_KIT_HUD_MODE_MANUAL
        self._live_kit_drawer_open = True
        self.live_kit_collapsed = False
        self._live_kit_hud_generation += 1
        self._reveal_live_kit_pane()
        self._live_kit_visibility_desired = True
        try_save_live_kit_visibility_preference(True)
        return True

    def close_live_kit_presentation(self) -> bool:
        """Hide Kit HUD without mutating musical kit state (#1207)."""
        was_open = bool(self._live_kit_drawer_open) or (
            self._live_kit_hud_mode != LIVE_KIT_HUD_MODE_HIDDEN
        )
        self._pending_live_kit_row = None
        self._live_kit_hud_mode = LIVE_KIT_HUD_MODE_HIDDEN
        self._live_kit_drawer_open = False
        self.live_kit_collapsed = True
        self._live_kit_hud_generation += 1
        self._live_kit_visibility_desired = False
        try_save_live_kit_visibility_preference(False)
        return was_open

    def dismiss_live_kit_transient(self, generation: int) -> bool:
        """Timer-owned close: only while still transient with matching generation."""
        try:
            gen = int(generation)
        except (TypeError, ValueError):
            return False
        if self._live_kit_hud_mode != LIVE_KIT_HUD_MODE_TRANSIENT:
            return False
        if gen != self._live_kit_hud_generation:
            return False
        self._live_kit_hud_mode = LIVE_KIT_HUD_MODE_HIDDEN
        self._live_kit_drawer_open = False
        self.live_kit_collapsed = True
        # Transient dismiss must not rewrite manual reopen preference.
        return True

    def escape_live_kit_context(self) -> bool:
        """Deterministic Esc: cancel pending Add, else close HUD presentation.

        Never clears musical kit assignments.
        """
        if self._pending_live_kit_row is not None:
            self.cancel_live_kit_add()
            return True
        if self._live_kit_drawer_open or self._live_kit_hud_mode != LIVE_KIT_HUD_MODE_HIDDEN:
            self.close_live_kit_presentation()
            return True
        return False

    def toggle_live_kit_drawer(self) -> bool:
        """Toggle the HUD without changing musical assignments or Harmony."""
        if self._live_kit_drawer_open or self._live_kit_hud_mode != LIVE_KIT_HUD_MODE_HIDDEN:
            self.close_live_kit_presentation()
            return False
        return self.open_live_kit_manual()

    def toggle_live_kit_collapsed(self) -> bool:
        """Compatibility shim for the retired permanent bottom-band control."""
        return self.toggle_live_kit_drawer()

    def apply_live_kit_visibility_preference(self) -> bool:
        """Cold start always closes Live Kit (#1123); ignore disk open preference.

        Manual session toggle still persists preference writes and drives
        in-session restore via ``_live_kit_visibility_desired``. Transient Add
        feedback never claims that reopen authority (#1207).
        """
        self._live_kit_visibility_desired = False
        self._live_kit_hud_mode = LIVE_KIT_HUD_MODE_HIDDEN
        self._live_kit_drawer_open = False
        self.live_kit_collapsed = True
        return False

    def restore_live_kit_after_active_source(self) -> bool:
        """Rematerialize Live Kit after a valid active Source is restored.

        Uses the in-session *manual* desired visibility when known so a
        fail-soft preference write cannot reopen against an explicit session
        close. Disk ``live_kit_visible=true`` alone is not restart reopen
        authority (#1123). Transient Add feedback is not restored.
        """
        desired = self._live_kit_visibility_desired
        if desired is None:
            desired = False
            self._live_kit_visibility_desired = False
        if desired:
            self._live_kit_hud_mode = LIVE_KIT_HUD_MODE_MANUAL
            self._live_kit_drawer_open = True
            self.live_kit_collapsed = False
            self._reveal_live_kit_pane()
            return self.live_kit_is_visible()
        if self._live_kit_drawer_open and self._live_kit_hud_mode == LIVE_KIT_HUD_MODE_MANUAL:
            self._reveal_live_kit_pane()
            return self.live_kit_is_visible()
        self._live_kit_hud_mode = LIVE_KIT_HUD_MODE_HIDDEN
        self._live_kit_drawer_open = False
        self.live_kit_collapsed = True
        return False

    def suspend_live_kit_for_analysis(self) -> None:
        """Close presentation while analysis owns the surface (#742 / #1077)."""
        composition = self._runtime_composition
        if composition is not None:
            composition.clear_live_kit_disclosure()
        self._live_kit_hud_mode = LIVE_KIT_HUD_MODE_HIDDEN
        self._live_kit_drawer_open = False
        self.live_kit_collapsed = True
        self.view_model.set_workspace_materialization(
            has_active_source=self.view_model.has_active_source,
            calm_canvas_visible=self.view_model.calm_canvas_visible,
            browser_materialized=self.view_model.browser_materialized,
            live_kit_materialized=False,
        )

    @property
    def live_kit_user_height_px(self) -> int:
        """User-controlled Live Kit height; 0 means auto row-derived height."""
        return int(self._live_kit_user_height_px)

    def set_live_kit_user_height_px(self, height_px: int, *, max_px: int = 0) -> int:
        """Clamp session Live Kit height. Kit state untouched.

        ``0`` restores auto height only when ``max_px`` is unset (explicit reset).
        Drag paths pass ``max_px > 0`` and therefore clamp underflow to the
        compact minimum instead of jumping back to auto/40% height.
        """
        try:
            raw = int(height_px)
        except (TypeError, ValueError):
            raw = 0
        minimum = 120
        if raw <= 0:
            if int(max_px) > 0:
                raw = minimum
            else:
                self._live_kit_user_height_px = 0
                return 0
        ceiling = int(max_px) if int(max_px) > 0 else 10_000
        self._live_kit_user_height_px = max(minimum, min(raw, ceiling))
        return int(self._live_kit_user_height_px)

    def live_kit_is_visible(self) -> bool:
        """True when Live Kit is materialized and presentation-open.

        Presentation-open includes the pending Add-to-Kit chooser even when the
        drawer preference stays closed (#954), matching QML ``bottomExpanded``.
        Effective visibility also requires the Browser host not to be collapsed
        (#1077): a zero-width Browser must not advertise #1072 Live Kit drops.
        """
        if self.browser_collapsed:
            return False
        presentation_open = bool(self._live_kit_drawer_open) or (
            self._pending_live_kit_row is not None
        )
        return bool(self.view_model.live_kit_materialized) and presentation_open

    def visible_live_kit_slot_keys(self) -> tuple[tuple[str, str], ...]:
        """#1072 target keys — empty while hidden or when no group is expanded."""
        if not self.live_kit_is_visible():
            return ()
        expanded: tuple[str, ...] = ()
        if self._live_kit is not None:
            expanded = tuple(
                group
                for group in self._live_kit.state.groups()
                if not self._live_kit.presentation.is_collapsed(group)
            )
        return visible_live_kit_slot_keys(
            live_kit_visible=True,
            expanded_groups=expanded,
        )

    def edit_docking_materialization(
        self,
        *,
        library: bool = True,
        browser: bool | None = None,
        harmony: bool | None = None,
    ) -> object:
        """#1070 materialization driven by visible Live Kit state."""
        browser_flag = (
            (bool(self.view_model.has_active_source) and not self.browser_collapsed)
            if browser is None
            else bool(browser)
        )
        harmony_flag = (
            bool(self.harmonic_match_open) if harmony is None else bool(harmony)
        )
        return edit_docking_materialization_for_live_kit(
            self.live_kit_is_visible(),
            library=library,
            browser=browser_flag,
            harmony=harmony_flag,
        )

    def remove_live_kit_slot(self, group: str, slot: str) -> bool:
        """Remove one assignment through clear_slot; no second mutation truth."""
        if self._live_kit is None:
            return False
        prior = None
        try:
            prior = self._live_kit.state.assignment_for(group, slot)
            cleared = self._live_kit.clear_slot(group, slot)
        except ValueError:
            return False
        if not cleared:
            return False
        self._sync_live_kit_projection()
        if self._auditioning_live_kit_slot == (group, slot):
            self._clear_live_kit_audition_projection()
        sample_name = prior.display_name if prior is not None else ""
        self._record_live_kit_feedback(
            sample_name=sample_name,
            group=group,
            slot=slot,
            mutation="remove",
        )
        # Remove updates an already-open HUD live; it does not auto-open.
        if self._live_kit_hud_mode in (
            LIVE_KIT_HUD_MODE_MANUAL,
            LIVE_KIT_HUD_MODE_TRANSIENT,
        ):
            self._live_kit_drawer_open = True
            self.live_kit_collapsed = False
        return True

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
    """Return a file URL for the canonical Screen-1 background reference.

    The historical reference PNG is V7-rejected evidence and is no longer
    packed into frozen builds; the invisible seam must not bind a dead URL.
    """
    path = screen1_background_reference_path().resolve()
    if not path.is_file():
        return ""
    return path.as_uri()


QML_SOURCE = r'''
import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

ApplicationWindow {
    id: window
    // Python assigns the current OS primary screen before first paint (#1231).
    visible: false
    width: 1600; height: 900
    minimumWidth: 1120; minimumHeight: 640
    // #1205: ApplicationWindow fills the Screen-1 canvas authority so residual
    // collapse/empty gaps cannot flash chrome/header black underneath panels.
    color: theme.surfaceRoot
    // Single QML call site for Harmonic Match toggle (#1204 disclosure reuses this).
    function activateHarmonicMatchToggle() {
        window.interaction.toggleHarmonicMatch()
    }
    // #1204 unified hairline panel disclosure — true horizontal collapsible panels only.
    // Visible seam ~1 DIP; hit area ~8 DIP; chevron only on hover/focus. Not used by Live Kit.
    component PanelDisclosureSeam: Item {
        id: disclosureRoot
        property string accessibleLabel: ""
        property string chevronText: "‹"
        property bool seamActive: true
        property var activateAction: function() {}
        // #1210: optional stable hint id; geometry/toggle authority stays with the seam.
        property string hintId: ""
        property int hitWidth: 8
        property bool hovered: false
        readonly property bool disclosed: hovered || activeFocus

        width: hitWidth
        visible: seamActive
        activeFocusOnTab: visible
        Accessible.role: Accessible.Button
        Accessible.name: accessibleLabel
        Accessible.onPressAction: disclosureRoot.activateAction()

        Rectangle {
            anchors.fill: parent
            color: theme.hoverSurface
            opacity: disclosureRoot.disclosed ? 0.35 : 0.0
        }
        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            width: 1
            height: parent.height
            color: theme.dividerDefault
            opacity: disclosureRoot.disclosed ? 0.95 : 0.28
            z: 1
        }
        Text {
            anchors.centerIn: parent
            z: 2
            text: disclosureRoot.chevronText
            color: theme.textSecondary
            font.pixelSize: 12
            opacity: disclosureRoot.disclosed ? 1.0 : 0.0
            Accessible.ignored: true
        }
        MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onEntered: disclosureRoot.hovered = true
            onExited: disclosureRoot.hovered = false
            onClicked: {
                disclosureRoot.forceActiveFocus()
                disclosureRoot.activateAction()
            }
        }
        Keys.onReturnPressed: disclosureRoot.activateAction()
        Keys.onEnterPressed: disclosureRoot.activateAction()
        Keys.onPressed: function(event) {
            if (event.key === Qt.Key_Space) {
                disclosureRoot.activateAction()
                event.accepted = true
            }
        }
        // #1210 hint routing after keyboard activation so frozen #845 windows keep Keys.*
        onHoveredChanged: {
            if (hintId.length === 0)
                return
            if (hovered)
                contextHintState.reportHover(hintId)
            else
                contextHintState.clearHover(hintId)
        }
        onActiveFocusChanged: {
            if (hintId.length === 0)
                return
            if (activeFocus && visible)
                contextHintState.reportFocus(hintId)
            else
                contextHintState.clearFocus(hintId)
        }
        // Collapse/reveal can hide this seam while it still holds keyboard focus.
        onVisibleChanged: {
            if (hintId.length === 0)
                return
            if (!visible) {
                contextHintState.clearHover(hintId)
                contextHintState.clearFocus(hintId)
            } else if (activeFocus) {
                contextHintState.reportFocus(hintId)
            }
        }
    }
    title: "Sample Brain"
    property var screenData: screenModel
    property var interaction: interactionModel
    property var channelRack: channelRackModel
    property var tempoSync: tempoSyncModel
    property var sessionPersistence: sessionPersistenceModel
    property var arrangement: arrangementModel
    readonly property string activeScreen: channelRack.activeScreen
    // #1213: project Python Browser readiness → internal chrome visibility.
    // Authority remains browser_materialized (Wave-1 usable Library); Wave-2
    // enrichment must not gate reveal. Animation is presentation only.
    readonly property bool programChromeVisible: window.interaction.browserMaterialized
    readonly property bool programChromeMotionEnabled:
        !window.screenData.brandReducedMotion
        && window.screenData.brandMotionMode !== "off"
    // Screen-1 Theme / Appearance Authority (#785 + #1255 + #1257):
    // Python AppearanceResolvedSnapshot is the sole truth; QML binds semantics.
    // No competing HEX palette / no QML-owned Appearance state machine.
    QtObject {
        id: theme
        readonly property color surfaceRoot: themeAuthority.surfaceRoot
        readonly property color surfaceHeader: themeAuthority.surfaceHeader
        readonly property color surfaceBrowser: themeAuthority.surfaceBrowser
        readonly property color surfacePanel: themeAuthority.surfacePanel
        readonly property color surfaceLibrary: themeAuthority.surfaceLibrary
        readonly property color libraryAllSamplesAccent: themeAuthority.libraryAllSamplesAccent
        readonly property color libraryCollectionsAccent: themeAuthority.libraryCollectionsAccent
        readonly property color libraryFavoritesAccent: themeAuthority.libraryFavoritesAccent
        readonly property color libraryRecordsAccent: themeAuthority.libraryRecordsAccent
        readonly property color surfaceElevated: themeAuthority.surfaceElevated
        readonly property color borderSubtle: themeAuthority.borderSubtle
        readonly property color borderDefault: themeAuthority.borderDefault
        readonly property color borderStrong: themeAuthority.borderStrong
        readonly property color dividerDefault: themeAuthority.dividerDefault
        readonly property color textPrimary: themeAuthority.textPrimary
        readonly property color textSecondary: themeAuthority.textSecondary
        readonly property color textMuted: themeAuthority.textMuted
        readonly property color textDisabled: themeAuthority.textDisabled
        readonly property color textOnAction: themeAuthority.textOnAction
        readonly property color waveformDefault: themeAuthority.waveformDefault
        readonly property color waveformActive: themeAuthority.waveformActive
        readonly property color selectionSurface: themeAuthority.selectionSurface
        readonly property color selectionBorder: themeAuthority.selectionBorder
        readonly property color actionActive: themeAuthority.actionActive
        readonly property color accentHover: themeAuthority.accentHover
        readonly property color accentActive: themeAuthority.accentActive
        readonly property color accentSubtle: themeAuthority.accentSubtle
        readonly property color focusRing: themeAuthority.focusRing
        readonly property color libraryFocusRing: themeAuthority.libraryFocusRing
        readonly property color hoverSurface: themeAuthority.hoverSurface
        readonly property color interactionPressed: themeAuthority.interactionPressed
        readonly property color interactionDisabled: themeAuthority.interactionDisabled
        readonly property color interactionSelection: themeAuthority.interactionSelection
        readonly property color statusError: themeAuthority.statusError
        readonly property color statusWarning: themeAuthority.statusWarning
        readonly property color statusSuccess: themeAuthority.statusSuccess
        readonly property color statusInfo: themeAuthority.statusInfo
    }
    // #1248 logical UI geometry, local to the Library presentation.
    // #1293 rail vertical insets are Library presentation spacing (logical DIP),
    // not duplicated Program Chrome / footer heights.
    QtObject {
        id: libraryMetrics
        readonly property int headerHeight: 52
        readonly property int addSourceSize: 36
        readonly property int rowHeight: 35
        readonly property int rowPitch: 36
        readonly property int paneInset: 6
        readonly property int contentPadding: 10
        readonly property int iconSize: 20
        readonly property int iconLabelGap: 6
        readonly property int textSize: 14
        readonly property int textLineHeight: 20
        readonly property int sectionGap: 20
        readonly property int sectionHeight: 36
        readonly property int sectionLineHeight: 18
        readonly property int sourceGap: 4
        readonly property int sourceRowHeight: 36
        readonly property int labelFadeWidth: 24
        // MagicPath rev 466430376995328000 — proportional visual evidence as DIP.
        readonly property int railTopInset: 8
        readonly property int railBottomInset: 18
    }
    // #770 shared context-hint content seam (ephemeral UI state; placement is separate).
    QtObject {
        id: contextHintState
        objectName: "contextHintState"
        readonly property var descriptors: ({
            "library.scope.sources": { "label": "YOUR SOURCES", "help": "registrierte Sample-Quellen" },
            "library.scope.all_samples": { "label": "All Samples", "help": "alle Samples im Workspace" },
            "library.scope.collections": { "label": "Collections", "help": "gespeicherte Sample-Sammlungen" },
            "library.scope.favorites": { "label": "Favorites", "help": "markierte Samples" },
            "library.scope.recordings": { "label": "Records", "help": "lokale Aufnahmen" },
            "library.add_source": { "label": "Add Source", "help": "lokalen Sample-Ordner hinzufügen" },
            "library.source": { "label": "Source", "help": "Sample-Quelle auswählen" },
            "library.source_actions": { "label": "Source actions", "help": "Quelle verwalten oder entfernen" },
            "browser.search": { "label": "Search", "help": "Samples im Browser filtern" },
            "browser.sample_row": { "label": "Sample", "help": "Sample auswählen oder Kontextmenü öffnen" },
            "browser.audition": { "label": "Audition", "help": "Sample-Vorschau abspielen" },
            "browser.favorite": { "label": "Favorite", "help": "Sample als Favorit markieren" },
            "browser.resize.waveform": { "label": "Resize waveform", "help": "Waveform-Spalte in der Breite anpassen" },
            "browser.resize.bpm": { "label": "Resize BPM", "help": "BPM-Spalte in der Breite anpassen" },
            "browser.resize.favorite": { "label": "Resize favorite", "help": "Favoriten-Spalte in der Breite anpassen" },
            "browser.resize.key": { "label": "Resize Key", "help": "Key-Spalte in der Breite anpassen" },
            "browser.resize.length": { "label": "Resize length", "help": "Length-Spalte in der Breite anpassen" },
            "browser.resize.type": { "label": "Resize Type", "help": "Type-Spalte in der Breite anpassen" },
            "browser.context.add_to_kit": { "label": "Add to Kit", "help": "ausgewähltes Sample zum Live Kit hinzufügen" },
            "browser.context.harmonic_matches": { "label": "Harmonic Matches", "help": "harmonische Treffer für das Sample öffnen" },
            "panel.browser.collapse": { "label": "Collapse Browser", "help": "Browser-Panel einklappen" },
            "panel.browser.expand": { "label": "Expand Browser", "help": "Browser-Panel wieder einblenden" },
            "panel.harmony.collapse": { "label": "Collapse Harmonic Matches", "help": "Harmonic-Matches-Panel einklappen" },
            "panel.harmony.expand": { "label": "Expand Harmonic Matches", "help": "Harmonic-Matches-Panel einblenden" },
            "panel.library.reveal": { "label": "Reveal Library", "help": "Library-Panel wieder einblenden" },
            "kit.hud.reveal": { "label": "Kit", "help": "Live Kit HUD manuell öffnen" },
            "kit.hud.hide": { "label": "Hide Kit", "help": "Live Kit HUD schließen" }
        })
        property string hoveredId: ""
        property string focusedId: ""
        property string activeId: ""
        property string activeLabel: ""
        property string activeHelp: ""
        // Hover > Focus > existing browser selection hint (#1210).
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
    // #1285: Loop phase remains Python-owned; QML only asks for fresh projection.
    readonly property bool loopPlayheadArmed: window.interaction.browserLoopActive
        && window.interaction.browserLoopPlaybackAvailable
        && window.waveformMotionMode !== "off"
    readonly property bool playbackPresentationArmed: window.previewPlayheadArmed || window.loopPlayheadArmed

    FrameAnimation {
        id: playbackProjectionDriver
        running: window.playbackPresentationArmed
        onTriggered: window.interaction.refreshPlaybackProjection()
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

    Menu {
        id: librarySourceContextMenu
        objectName: "librarySourceContextMenu"
        MenuItem {
            text: "Remove Source"
            onTriggered: removeSourceDialog.open()
        }
    }

    Connections {
        target: libraryInteraction
        function onRemovalRequested() { removeSourceDialog.open() }
    }

    // Historical Screen-1 reference: retain the named evidence/URL seam, but
    // never composite the opaque asset over the V7 Theme Core root chrome.
    Image {
        id: screen1Background
        objectName: "screen1Background"
        anchors.fill: parent
        z: -1
        visible: false
        source: screen1BackgroundUrl
        fillMode: Image.Stretch
        asynchronous: true
    }

    // #831 program footer band — context center / status right (#830 / #770).
    // Footer-context centering: true center layer on full footer width (not RowLayout leftover).
    // #880: slim status-bar footer (chosen ~22; not screenshot-pixel truth).
    // Global program chrome: keep the footer present on Screen 1 and Screen 2
    // once #1213 workspace readiness is reached (zero footprint before that).
    // Dark surface hierarchy: footer paints chrome (surfaceHeader), not workspace root.
    footer: Item {
        id: programFooterBand
        objectName: "programFooterBand"
        height: window.programChromeVisible ? 22 : 0
        implicitHeight: height
        visible: height > 0
        clip: true
        // Animate enter only; cancel/fail must snap closed (no half chrome).
        Behavior on height {
            enabled: window.programChromeMotionEnabled && window.programChromeVisible
            NumberAnimation { duration: 240; easing.type: Easing.OutCubic }
        }
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
                readonly property real leftBound: 8
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
    }
    // #831 program chrome — identity left / navigation center / tempo zone right (#830).
    // #880: slim/premium header geometry (chosen ~30; not screenshot-pixel truth).
    // #1213: collapse to zero layout footprint until Browser-ready; restrained
    // height reveal (enter from top) when motion is enabled.
    header: Rectangle {
        id: screen1Header
        objectName: "screen1Header"
        height: window.programChromeVisible ? 30 : 0
        implicitHeight: height
        visible: height > 0
        clip: true
        color: theme.surfaceHeader
        // Animate enter only; cancel/fail must snap closed (no half chrome).
        Behavior on height {
            enabled: window.programChromeMotionEnabled && window.programChromeVisible
            NumberAnimation { duration: 240; easing.type: Easing.OutCubic }
        }
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
                    id: programNavEdit
                    objectName: "programNavEdit"
                    text: "Edit"
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
                               && window.arrangement.projectionMode === "EDIT"
                    background: Item {
                        implicitHeight: screen1Header.height
                        Rectangle {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            height: 1
                            color: theme.actionActive
                            visible: programNavEdit.navActive
                            opacity: 0.85
                        }
                    }
                    contentItem: Text {
                        text: programNavEdit.text
                        font: programNavEdit.font
                        color: programNavEdit.navActive ? theme.textPrimary : theme.textSecondary
                        opacity: programNavEdit.navActive ? 1.0 : 0.72
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    // #1080 Slice A: while the Arrangement shell owns
                    // projection, the Edit route returns through the same
                    // #1078 state owner and retains Browser reveal intent.
                    onClicked: {
                        if (window.arrangement.projectionMode === "ARRANGEMENT") {
                            window.arrangement.returnToBrowser()
                            return
                        }
                        if (window.activeScreen === "screen2")
                            window.interaction.returnToScreen1()
                        if (window.interaction.browserCollapsed)
                            window.interaction.toggleBrowserCollapsed()
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
                    // #1080/#1076: route visibility follows the canonical
                    // feature gate; eligibility and the transition itself
                    // stay owned by the #1078 session state owner.
                    readonly property bool navActive: window.arrangement.projectionMode === "ARRANGEMENT"
                    enabled: window.arrangement.arrangementModeEnabled
                    background: Item { implicitHeight: screen1Header.height }
                    contentItem: Text {
                        text: programNavArrangement.text
                        font: programNavArrangement.font
                        color: !programNavArrangement.enabled ? theme.textDisabled
                               : (programNavArrangement.navActive ? theme.textPrimary : theme.textSecondary)
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        opacity: programNavArrangement.enabled ? (programNavArrangement.navActive ? 1.0 : 0.9) : 0.4
                    }
                    onClicked: window.arrangement.enterArrangement()
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
            // Reserve a usable nav band (~380px) for two top-level destinations at min width.
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
            // #805/#1216: MASTER/SYNC project session tempo/SYNC authority only.
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
            Button {
                id: syncButton
                objectName: "syncButton"
                text: "SYNC"
                implicitWidth: 42
                implicitHeight: 18
                flat: true
                padding: 2
                Layout.alignment: Qt.AlignVCenter
                Accessible.name: "SYNC"
                Accessible.description: window.tempoSync.syncEnabled ? "SYNC enabled" : "SYNC disabled"
                background: Rectangle {
                    objectName: "syncButtonBackground"
                    radius: 2
                    color: window.tempoSync.syncEnabled ? theme.actionActive : "transparent"
                    border.width: 1
                    border.color: window.tempoSync.syncEnabled ? theme.actionActive : theme.borderSubtle
                }
                contentItem: Text {
                    text: syncButton.text
                    color: window.tempoSync.syncEnabled ? theme.textOnAction : theme.textSecondary
                    font.pixelSize: 9
                    font.bold: false
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                onClicked: window.tempoSync.toggleSync()
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
                            placeholderTextColor: theme.textMuted
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
            // #1207: Esc stops preview and closes Kit HUD presentation (never kit state).
            // Popup/Menu CloseOnEscape still wins while a popup holds focus.
            if (event.key === Qt.Key_Escape) {
                var hadPreview = window.interaction.previewActive
                var hudOpen = window.interaction.liveKitDrawerOpen
                        || window.interaction.liveKitPendingAdd !== ""
                window.interaction.escapeLiveKitContext()
                if (hadPreview || hudOpen)
                    event.accepted = true
            }
        }
        onWidthChanged: layoutModel.setContentWidth(width)
        Component.onCompleted: layoutModel.setContentWidth(width)

        // #1293: Library is a bounded left rail. Host keeps full workspace-row
        // height for elastic width ownership; painted pane is vertically inset so
        // gaps reveal theme.surfaceRoot. Host is unpainted (no card/frame).
        Item {
            id: libraryRailHost
            objectName: "libraryRailHost"
            width: layoutModel.libraryWidth
            height: parent.height
            visible: width > 0
            readonly property int topInset: Math.min(libraryMetrics.railTopInset, Math.max(0, height))
            readonly property int bottomInset: Math.min(
                libraryMetrics.railBottomInset,
                Math.max(0, height - topInset)
            )
            Rectangle {
                id: libraryPane
                objectName: "libraryPane"
                color: theme.surfaceLibrary
                border.color: theme.borderSubtle
                anchors.left: parent.left
                anchors.right: parent.right
                y: libraryRailHost.topInset
                height: Math.max(0, libraryRailHost.height - libraryRailHost.topInset - libraryRailHost.bottomInset)
                visible: width > 0 && height > 0
                clip: true
            ColumnLayout { anchors.fill: parent; anchors.leftMargin: libraryMetrics.paneInset; anchors.rightMargin: libraryMetrics.paneInset; spacing: 0
                RowLayout {
                    id: libraryHeaderRow
                    objectName: "libraryHeaderRow"
                    Layout.fillWidth: true
                    Layout.minimumHeight: libraryMetrics.headerHeight
                    Layout.maximumHeight: libraryMetrics.headerHeight
                    Layout.leftMargin: libraryMetrics.contentPadding
                    spacing: 0
                    Label { objectName: "libraryTitleLabel"; text: "LIBRARY"; color: theme.textSecondary; font.pixelSize: libraryMetrics.textSize; Layout.fillWidth: true }
                    Item { Layout.fillWidth: true }
                    Button {
                        id: libraryAddSourceButton
                        objectName: "libraryAddSourceButton"
                        text: "+"
                        flat: true
                        Layout.minimumWidth: libraryMetrics.addSourceSize
                        Layout.maximumWidth: libraryMetrics.addSourceSize
                        Layout.minimumHeight: libraryMetrics.addSourceSize
                        Layout.maximumHeight: libraryMetrics.addSourceSize
                        implicitHeight: libraryMetrics.addSourceSize
                        padding: 0
                        leftPadding: 0
                        rightPadding: 0
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
                            implicitHeight: libraryMetrics.addSourceSize
                            radius: 4
                            color: !libraryAddSourceButton.enabled ? "transparent"
                                   : (libraryAddSourceButton.pressed ? theme.surfaceElevated
                                      : (libraryAddSourceButton.hovered ? theme.hoverSurface : "transparent"))
                            border.width: 1
                            border.color: !libraryAddSourceButton.enabled ? theme.borderSubtle
                                          : (libraryAddSourceButton.activeFocus ? theme.libraryFocusRing
                                             : (libraryAddSourceButton.pressed ? theme.interactionPressed : theme.borderSubtle))
                            opacity: libraryAddSourceButton.enabled ? 1.0 : 0.4
                        }
                        onClicked: addSourceDialog.open()
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
                    }
                }
                // #1201: existing Python-owned Library scope routes stay compact and local.
                ColumnLayout {
                    id: libraryScopeBar
                    objectName: "libraryScopeBar"
                    Layout.fillWidth: true
                    spacing: libraryMetrics.rowPitch - libraryMetrics.rowHeight
                    z: 2

                    function scopeFill(active, hovered) {
                        if (hovered && !active)
                            return theme.hoverSurface
                        return "transparent"
                    }
                    function scopeInk(active, categoryAccent) {
                        return active ? categoryAccent : theme.textSecondary
                    }
                            ToolButton {
                                id: allSamplesScopeButton
                                readonly property color categoryAccent: theme.libraryAllSamplesAccent
                                objectName: "libraryAllSamplesScopeButton"
                                text: "All Samples"
                                flat: true
                                readonly property bool scopeActive: libraryInteraction.activeLibrarySection === "all"
                                Layout.fillWidth: true
                                Layout.minimumHeight: libraryMetrics.rowHeight
                                Layout.maximumHeight: libraryMetrics.rowHeight
                                onClicked: {
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
                                background: Rectangle {
                                    anchors.fill: parent
                                    radius: 8
                                    color: libraryScopeBar.scopeFill(allSamplesScopeButton.scopeActive, allSamplesScopeButton.hovered)
                                    border.width: allSamplesScopeButton.visualFocus ? 1 : 0
                                    border.color: theme.libraryFocusRing
                                }
                                contentItem: Item {
                                    anchors.fill: parent
                                    Text {
                                        anchors.left: parent.left
                                        anchors.leftMargin: libraryMetrics.contentPadding + libraryMetrics.iconSize + libraryMetrics.iconLabelGap
                                        anchors.right: parent.right
                                        anchors.rightMargin: libraryMetrics.contentPadding
                                        anchors.verticalCenter: parent.verticalCenter
                                        height: libraryMetrics.textLineHeight
                                        lineHeightMode: Text.FixedHeight
                                        lineHeight: libraryMetrics.textLineHeight
                                        elide: Text.ElideRight
                                        text: allSamplesScopeButton.text
                                        color: libraryScopeBar.scopeInk(allSamplesScopeButton.scopeActive, allSamplesScopeButton.categoryAccent)
                                        horizontalAlignment: Text.AlignLeft
                                        verticalAlignment: Text.AlignVCenter
                                        font.pixelSize: libraryMetrics.textSize
                                        font.weight: Font.Normal
                                    }
                                    Canvas {
                                        anchors.left: parent.left
                                        anchors.leftMargin: libraryMetrics.contentPadding
                                        anchors.verticalCenter: parent.verticalCenter
                                        width: libraryMetrics.iconSize
                                        height: libraryMetrics.iconSize
                                        onPaint: {
                                            var ctx = getContext("2d")
                                            ctx.reset()
                                            ctx.strokeStyle = allSamplesScopeButton.categoryAccent
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
                                            function onScopeActiveChanged() { parent.requestPaint() }
                                            function onHoveredChanged() { parent.requestPaint() }
                                            function onCategoryAccentChanged() { parent.requestPaint() }
                                        }
                                    }
                                }
                            }
                            ToolButton {
                                id: collectionsScopeButton
                                readonly property color categoryAccent: theme.libraryCollectionsAccent
                                objectName: "libraryCollectionsScopeButton"
                                text: "Collections"
                                flat: true
                                readonly property bool scopeActive: libraryInteraction.activeLibrarySection === "collections"
                                Layout.fillWidth: true
                                Layout.minimumHeight: libraryMetrics.rowHeight
                                Layout.maximumHeight: libraryMetrics.rowHeight
                                onClicked: libraryInteraction.showLibrarySection("collections")
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
                                background: Rectangle {
                                    anchors.fill: parent
                                    radius: 8
                                    color: libraryScopeBar.scopeFill(collectionsScopeButton.scopeActive, collectionsScopeButton.hovered)
                                    border.width: collectionsScopeButton.visualFocus ? 1 : 0
                                    border.color: theme.libraryFocusRing
                                }
                                contentItem: Item {
                                    anchors.fill: parent
                                    Text {
                                        anchors.left: parent.left
                                        anchors.leftMargin: libraryMetrics.contentPadding + libraryMetrics.iconSize + libraryMetrics.iconLabelGap
                                        anchors.right: parent.right
                                        anchors.rightMargin: libraryMetrics.contentPadding
                                        anchors.verticalCenter: parent.verticalCenter
                                        height: libraryMetrics.textLineHeight
                                        lineHeightMode: Text.FixedHeight
                                        lineHeight: libraryMetrics.textLineHeight
                                        elide: Text.ElideRight
                                        text: collectionsScopeButton.text
                                        color: libraryScopeBar.scopeInk(collectionsScopeButton.scopeActive, collectionsScopeButton.categoryAccent)
                                        horizontalAlignment: Text.AlignLeft
                                        verticalAlignment: Text.AlignVCenter
                                        font.pixelSize: libraryMetrics.textSize
                                        font.weight: Font.Normal
                                    }
                                    Canvas {
                                        anchors.left: parent.left
                                        anchors.leftMargin: libraryMetrics.contentPadding
                                        anchors.verticalCenter: parent.verticalCenter
                                        width: libraryMetrics.iconSize
                                        height: libraryMetrics.iconSize
                                        onPaint: {
                                            var ctx = getContext("2d")
                                            ctx.reset()
                                            ctx.strokeStyle = collectionsScopeButton.categoryAccent
                                            ctx.lineWidth = 1
                                            ctx.strokeRect(2, 1, width - 6, height - 6)
                                            ctx.strokeRect(5, 4, width - 6, height - 6)
                                        }
                                        Component.onCompleted: requestPaint()
                                        Connections {
                                            target: collectionsScopeButton
                                            function onScopeActiveChanged() { parent.requestPaint() }
                                            function onHoveredChanged() { parent.requestPaint() }
                                            function onCategoryAccentChanged() { parent.requestPaint() }
                                        }
                                    }
                                }
                            }
                            ToolButton {
                                id: favoritesScopeButton
                                readonly property color categoryAccent: theme.libraryFavoritesAccent
                                objectName: "libraryFavoritesScopeButton"
                                text: "Favorites"
                                flat: true
                                readonly property bool scopeActive: libraryInteraction.activeLibrarySection === "favorites"
                                Layout.fillWidth: true
                                Layout.minimumHeight: libraryMetrics.rowHeight
                                Layout.maximumHeight: libraryMetrics.rowHeight
                                onClicked: {
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
                                background: Rectangle {
                                    anchors.fill: parent
                                    radius: 8
                                    color: libraryScopeBar.scopeFill(favoritesScopeButton.scopeActive, favoritesScopeButton.hovered)
                                    border.width: favoritesScopeButton.visualFocus ? 1 : 0
                                    border.color: theme.libraryFocusRing
                                }
                                contentItem: Item {
                                    anchors.fill: parent
                                    Text {
                                        anchors.left: parent.left
                                        anchors.leftMargin: libraryMetrics.contentPadding + libraryMetrics.iconSize + libraryMetrics.iconLabelGap
                                        anchors.right: parent.right
                                        anchors.rightMargin: libraryMetrics.contentPadding
                                        anchors.verticalCenter: parent.verticalCenter
                                        height: libraryMetrics.textLineHeight
                                        lineHeightMode: Text.FixedHeight
                                        lineHeight: libraryMetrics.textLineHeight
                                        elide: Text.ElideRight
                                        text: favoritesScopeButton.text
                                        color: libraryScopeBar.scopeInk(favoritesScopeButton.scopeActive, favoritesScopeButton.categoryAccent)
                                        horizontalAlignment: Text.AlignLeft
                                        verticalAlignment: Text.AlignVCenter
                                        font.pixelSize: libraryMetrics.textSize
                                        font.weight: Font.Normal
                                    }
                                    Canvas {
                                        anchors.left: parent.left
                                        anchors.leftMargin: libraryMetrics.contentPadding
                                        anchors.verticalCenter: parent.verticalCenter
                                        width: libraryMetrics.iconSize
                                        height: libraryMetrics.iconSize
                                        onPaint: {
                                            var ctx = getContext("2d")
                                            ctx.reset()
                                            ctx.strokeStyle = favoritesScopeButton.categoryAccent
                                            ctx.fillStyle = favoritesScopeButton.categoryAccent
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
                                            if (favoritesScopeButton.scopeActive)
                                            ctx.fill()
                                            else
                                            ctx.stroke()
                                        }
                                        Component.onCompleted: requestPaint()
                                        Connections {
                                            target: favoritesScopeButton
                                            function onScopeActiveChanged() { parent.requestPaint() }
                                            function onHoveredChanged() { parent.requestPaint() }
                                            function onCategoryAccentChanged() { parent.requestPaint() }
                                        }
                                    }
                                }
                            }

                            ToolButton {
                                id: recordingsScopeButton
                                readonly property color categoryAccent: theme.libraryRecordsAccent
                                objectName: "libraryRecordingsScopeButton"
                                text: "Records"
                                flat: true
                                readonly property bool scopeActive: libraryInteraction.activeLibrarySection === "recordings"
                                Layout.fillWidth: true
                                Layout.minimumHeight: libraryMetrics.rowHeight
                                Layout.maximumHeight: libraryMetrics.rowHeight
                                onClicked: {
                                    libraryInteraction.selectLibraryNode("scope:recordings")
                                }
                                Accessible.name: "Records"
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
                                background: Rectangle {
                                    anchors.fill: parent
                                    radius: 8
                                    color: libraryScopeBar.scopeFill(recordingsScopeButton.scopeActive, recordingsScopeButton.hovered)
                                    border.width: recordingsScopeButton.visualFocus ? 1 : 0
                                    border.color: theme.libraryFocusRing
                                }
                                contentItem: Item {
                                    anchors.fill: parent
                                    Text {
                                        anchors.left: parent.left
                                        anchors.leftMargin: libraryMetrics.contentPadding + libraryMetrics.iconSize + libraryMetrics.iconLabelGap
                                        anchors.right: parent.right
                                        anchors.rightMargin: libraryMetrics.contentPadding
                                        anchors.verticalCenter: parent.verticalCenter
                                        height: libraryMetrics.textLineHeight
                                        lineHeightMode: Text.FixedHeight
                                        lineHeight: libraryMetrics.textLineHeight
                                        elide: Text.ElideRight
                                        text: recordingsScopeButton.text
                                        color: libraryScopeBar.scopeInk(recordingsScopeButton.scopeActive, recordingsScopeButton.categoryAccent)
                                        horizontalAlignment: Text.AlignLeft
                                        verticalAlignment: Text.AlignVCenter
                                        font.pixelSize: libraryMetrics.textSize
                                        font.weight: Font.Normal
                                    }
                                    Canvas {
                                        anchors.left: parent.left
                                        anchors.leftMargin: libraryMetrics.contentPadding
                                        anchors.verticalCenter: parent.verticalCenter
                                        width: libraryMetrics.iconSize
                                        height: libraryMetrics.iconSize
                                        onPaint: {
                                            var ctx = getContext("2d")
                                            ctx.reset()
                                            ctx.strokeStyle = recordingsScopeButton.categoryAccent
                                            ctx.lineWidth = 1
                                            ctx.beginPath()
                                            ctx.arc(width / 2, height / 2, width * 0.38, 0, 2 * Math.PI)
                                            ctx.stroke()
                                            ctx.beginPath()
                                            ctx.arc(width / 2, height / 2, width * 0.10, 0, 2 * Math.PI)
                                            ctx.stroke()
                                        }
                                        Component.onCompleted: requestPaint()
                                        Connections {
                                            target: recordingsScopeButton
                                            function onScopeActiveChanged() { parent.requestPaint() }
                                            function onHoveredChanged() { parent.requestPaint() }
                                            function onCategoryAccentChanged() { parent.requestPaint() }
                                        }
                                    }
                                }
                            }
                    }
                ColumnLayout {
                    id: libraryContentHost
                    objectName: "libraryContentHost"
                    Layout.topMargin: libraryMetrics.sectionGap
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: 0
                ListView {
                    id: collectionList
                    objectName: "libraryCollectionList"
                    visible: libraryInteraction.activeLibrarySection === "collections"
                    Layout.fillWidth: true
                    Layout.preferredHeight: visible ? Math.min(Math.max(contentHeight, 36), Math.max(36, libraryContentHost.height * 0.35)) : 0
                    Layout.maximumHeight: visible ? Math.max(36, libraryContentHost.height * 0.35) : 0
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
                Label {
                    objectName: "librarySourcesHeading"
                    text: "YOUR SOURCES"
                    color: theme.textSecondary
                    font.pixelSize: libraryMetrics.textSize
                    font.weight: Font.Medium
                    lineHeightMode: Text.FixedHeight
                    lineHeight: libraryMetrics.sectionLineHeight
                    verticalAlignment: Text.AlignVCenter
                    Layout.minimumHeight: libraryMetrics.sectionHeight
                    Layout.maximumHeight: libraryMetrics.sectionHeight
                    Layout.leftMargin: libraryMetrics.contentPadding
                    Layout.fillWidth: true
                }
                TreeView {
                    id: libraryTree
                    objectName: "libraryTree"
                    property bool keyboardFocusVisible: false
                    onActiveFocusChanged: keyboardFocusVisible = activeFocus
                    Layout.topMargin: libraryMetrics.sourceGap
                    visible: true
                    enabled: true
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    model: libraryTreeModel
                    // Native keyboard-current only; Python selectedLibraryNodeId
                    // remains the sole source/navigation selection authority.
                    selectionModel: ItemSelectionModel {}
                    selectionBehavior: TableView.SelectionDisabled
                    columnWidthProvider: function(column) { return libraryTree.width }
                    rootIndex: libraryTreeModel.presentationRootIndex()
                    clip: true
                    focus: false
                    activeFocusOnTab: true
                    boundsBehavior: Flickable.StopAtBounds
                    delegate: TreeViewDelegate {
                        id: libraryDelegate
                        Accessible.name: model.display
                        palette.text: libraryInteraction.selectedLibraryNodeId === model.nodeId ? theme.actionActive : theme.textSecondary
                        palette.windowText: palette.text
                        implicitHeight: libraryMetrics.sourceRowHeight
                        indentation: 16
                        background: Rectangle {
                            color: libraryInteraction.selectedLibraryNodeId === model.nodeId ? "transparent"
                                   : (libraryDelegate.hovered ? theme.hoverSurface : "transparent")
                            border.width: libraryDelegate.current && libraryTree.activeFocus
                                          && libraryTree.keyboardFocusVisible ? 1 : 0
                            border.color: theme.libraryFocusRing
                        }
                        contentItem: Item {
                            implicitHeight: libraryMetrics.sourceRowHeight
                            implicitWidth: libraryTree.width
                            property bool dropHover: false
                            HoverHandler {
                                id: sourceRowHover
                                onHoveredChanged: {
                                    if (hovered)
                                        contextHintState.reportHover("library.source")
                                    else
                                        contextHintState.clearHover("library.source")
                                }
                            }
                            TapHandler {
                                id: sourceRowTap
                                // The action button owns intentional clicks in
                                // its right-hand hit area; do not also select
                                // or audition the source row.
                                enabled: !sourceActionsButton.hovered && !sourceActionsButton.activeFocus
                                onTapped: {
                                    if (model.error) {
                                        libraryInteraction.retryLibraryNode(model.parentNodeId)
                                    } else if (model.selectable) {
                                        libraryInteraction.showLibrarySection("sources")
                                        libraryTree.forceActiveFocus()
                                        libraryTree.keyboardFocusVisible = false
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
                                Item {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: libraryMetrics.textLineHeight
                                    clip: true
                                    Label {
                                        id: sourceLabel
                                        objectName: "librarySourceLabel"
                                        anchors.fill: parent
                                        text: model.loading ? "Loading…" : model.display
                                        color: libraryInteraction.selectedLibraryNodeId === model.nodeId ? theme.actionActive
                                               : (model.availability === "offline" ? theme.textDisabled : theme.textPrimary)
                                        opacity: model.error ? 0.72 : 1.0
                                        font.pixelSize: libraryMetrics.textSize
                                        font.weight: Font.Normal
                                        lineHeightMode: Text.FixedHeight
                                        lineHeight: libraryMetrics.textLineHeight
                                        verticalAlignment: Text.AlignVCenter
                                    }
                                    Rectangle {
                                        objectName: "librarySourceLabelFade"
                                        anchors.right: parent.right
                                        height: parent.height
                                        width: libraryMetrics.labelFadeWidth
                                        visible: sourceLabel.implicitWidth > sourceLabel.width
                                        gradient: Gradient {
                                            orientation: Gradient.Horizontal
                                            GradientStop { position: 0; color: Qt.rgba(theme.surfaceLibrary.r, theme.surfaceLibrary.g, theme.surfaceLibrary.b, 0) }
                                            GradientStop { position: 1; color: libraryInteraction.selectedLibraryNodeId !== model.nodeId && libraryDelegate.hovered ? theme.hoverSurface : theme.surfaceLibrary }
                                        }
                                    }
                                }
                                Label {
                                    visible: model.error
                                    text: "Retry"
                                    color: theme.textSecondary
                                    font.pixelSize: 11
                                }
                                    ToolButton {
                                    id: sourceActionsButton
                                    objectName: "librarySourceActionsButton"
                                    visible: model.kind === "registered_root"
                                             && (sourceRowHover.hovered
                                                 || (libraryDelegate.current && libraryTree.activeFocus)
                                                 || activeFocus)
                                             && libraryInteraction.canRemoveSource(model.nodeId)
                                    text: "…"
                                    flat: true
                                    activeFocusOnTab: visible
                                    implicitWidth: 28
                                    implicitHeight: 28
                                    Accessible.name: "Source actions"
                                    ToolTip.visible: hovered
                                    ToolTip.text: "Source actions"
                                    onHoveredChanged: {
                                        if (hovered)
                                            contextHintState.reportHover("library.source_actions")
                                        else {
                                            contextHintState.clearHover("library.source_actions")
                                            if (sourceRowHover.hovered)
                                                contextHintState.reportHover("library.source")
                                        }
                                    }
                                    onActiveFocusChanged: {
                                        if (activeFocus)
                                            contextHintState.reportFocus("library.source_actions")
                                        else
                                            contextHintState.clearFocus("library.source_actions")
                                    }
                                    onClicked: {
                                        if (libraryInteraction.prepareRemoveSourceForNode(model.nodeId))
                                            librarySourceContextMenu.open()
                                    }
                                    contentItem: Text {
                                        text: sourceActionsButton.text
                                        color: sourceActionsButton.activeFocus || sourceActionsButton.hovered
                                               ? theme.textPrimary : theme.textSecondary
                                        horizontalAlignment: Text.AlignHCenter
                                        verticalAlignment: Text.AlignVCenter
                                        font.pixelSize: 16
                                    }
                                    background: Rectangle {
                                        radius: 4
                                        color: sourceActionsButton.activeFocus
                                               ? theme.surfaceElevated
                                               : (sourceActionsButton.hovered ? theme.hoverSurface : "transparent")
                                        border.width: sourceActionsButton.activeFocus ? 1 : 0
                                        border.color: theme.libraryFocusRing
                                    }
                                }
                            }
                        }
                    }
                    Keys.onPressed: function(event) {
                        libraryTree.keyboardFocusVisible = true
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
        }
        // #742 geometry: libraryRevealAffordance is an overlay sibling of workspaceRow
        // (not a Row child). Horizontal anchors on Row-managed children disable the
        // Row positioner and collapse all pane x origins to 0.
        Item {
            id: handleAfterLibrary
            objectName: "elasticHandleAfterLibrary"
            // Resize only while Browser is an elastic neighbour. When Browser is
            // collapsed (#1204), residual workspace owns the freed width and the
            // disclosure seam (not this drag handle) is the reopen intent.
            visible: window.interaction.hasActiveSource
                     && window.interaction.libraryRevealed
                     && !window.interaction.browserCollapsed
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
                        color: window.screenData.analysisStatus === "error" ? theme.statusError : theme.textSecondary
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
        Item {
            id: rightWorkspaceColumn
            objectName: "rightWorkspaceColumn"
            width: Math.max(0, parent.width - libraryPane.width - handleAfterLibrary.width)
            height: parent.height

            Row {
                id: upperWorkspaceRow
                objectName: "upperWorkspaceRow"
                width: parent.width
                height: parent.height
                spacing: 0
            Rectangle { id: browserPane; objectName: "browserPane"; visible: window.interaction.hasActiveSource && !window.interaction.browserCollapsed; width: visible ? layoutModel.browserWidth : 0; height: parent.height; color: theme.surfaceBrowser; border.color: theme.borderSubtle
                function openSampleContextMenu(index, localX, localY) {
                    window.interaction.openSampleContext(index)
                    sampleContextMenu.focusedAction = 0
                    var menuWidth = Math.max(1, sampleContextMenu.width)
                    var menuHeight = Math.max(1, sampleContextMenu.implicitHeight)
                    sampleContextMenu.x = Math.max(8, Math.min(localX, Math.max(8, width - menuWidth - 8)))
                    sampleContextMenu.y = Math.max(8, Math.min(localY, Math.max(8, height - menuHeight - 8)))
                    sampleContextMenu.open()
                    contextMenuContent.forceActiveFocus()
                }
                Popup {
                    id: sampleContextMenu
                    objectName: "sampleContextMenu"
                    // Theme: theme.selectionSurface / theme.textPrimary / theme.focusRing
                    property string actionAddLabel: "Add to Kit"
                    property string actionHarmonicLabel: "Harmonic Matches"
                    property string actionLoopLabel: window.interaction.contextTargetIsLoopOwner ? "LOOP OFF" : "LOOP ON"
                    width: 208
                    padding: 6
                    implicitHeight: contextMenuContent.implicitHeight + 2 * padding
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
                    function contextActionHintId(actionIndex) {
                        if (actionIndex === 0)
                            return "browser.context.add_to_kit"
                        if (actionIndex === 1)
                            return "browser.context.harmonic_matches"
                        return "browser.context.loop"
                    }
                    function syncContextActionFocusHint() {
                        var hintIds = [
                            "browser.context.add_to_kit",
                            "browser.context.harmonic_matches",
                            "browser.context.loop"
                        ]
                        for (var hintIndex = 0; hintIndex < hintIds.length; hintIndex++)
                            contextHintState.clearFocus(hintIds[hintIndex])
                        if (visible)
                            contextHintState.reportFocus(contextActionHintId(focusedAction))
                    }
                    onOpened: syncContextActionFocusHint()
                    onFocusedActionChanged: syncContextActionFocusHint()
                    onClosed: {
                        window.interaction.closeSampleContext()
                        contextHintState.clearHover("browser.context.add_to_kit")
                        contextHintState.clearHover("browser.context.harmonic_matches")
                        contextHintState.clearHover("browser.context.loop")
                        contextHintState.clearFocus("browser.context.add_to_kit")
                        contextHintState.clearFocus("browser.context.harmonic_matches")
                        contextHintState.clearFocus("browser.context.loop")
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
                        if (focusedAction === 0) {
                            window.interaction.contextAddToKit()
                            return
                        }
                        if (focusedAction === 1) {
                            window.interaction.contextHarmonicMatches()
                            return
                        }
                        window.interaction.contextLoopToggle()
                    }
                    Column {
                        id: contextMenuContent
                        width: parent.width
                        spacing: 2
                        focus: true
                        Keys.onPressed: function(event) {
                            if (event.key === Qt.Key_Down) {
                                sampleContextMenu.focusedAction = Math.min(2, sampleContextMenu.focusedAction + 1)
                                event.accepted = true
                            } else if (event.key === Qt.Key_Up) {
                                sampleContextMenu.focusedAction = Math.max(0, sampleContextMenu.focusedAction - 1)
                                event.accepted = true
                            } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
                                sampleContextMenu.activateFocused()
                                event.accepted = true
                            } else if (event.key === Qt.Key_Escape) {
                                sampleContextMenu.close()
                                event.accepted = true
                            }
                        }
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
                                onEntered: {
                                    sampleContextMenu.focusedAction = 0
                                    contextHintState.reportHover("browser.context.add_to_kit")
                                }
                                onExited: contextHintState.clearHover("browser.context.add_to_kit")
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
                                onEntered: {
                                    sampleContextMenu.focusedAction = 1
                                    contextHintState.reportHover("browser.context.harmonic_matches")
                                }
                                onExited: contextHintState.clearHover("browser.context.harmonic_matches")
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
                            id: contextLoopItem
                            objectName: "contextLoopItem"
                            width: parent.width
                            height: 32
                            radius: 4
                            color: sampleContextMenu.focusedAction === 2 || contextLoopHover.containsMouse ? theme.surfaceElevated : "transparent"
                            border.width: sampleContextMenu.focusedAction === 2 ? 1 : 0
                            border.color: theme.focusRing
                            Accessible.role: Accessible.Button
                            Accessible.name: sampleContextMenu.actionLoopLabel
                            Accessible.onPressAction: {
                                sampleContextMenu.focusedAction = 2
                                sampleContextMenu.activateFocused()
                            }
                            Label {
                                anchors.fill: parent
                                anchors.leftMargin: 10
                                anchors.rightMargin: 10
                                text: sampleContextMenu.actionLoopLabel
                                color: theme.textPrimary
                                verticalAlignment: Text.AlignVCenter
                                font.pixelSize: window.textBody
                                Accessible.ignored: true
                            }
                            MouseArea {
                                id: contextLoopHover
                                anchors.fill: parent
                                hoverEnabled: true
                                onClicked: {
                                    sampleContextMenu.focusedAction = 2
                                    sampleContextMenu.activateFocused()
                                }
                                onEntered: {
                                    sampleContextMenu.focusedAction = 2
                                    contextHintState.reportHover("browser.context.loop")
                                }
                                onExited: contextHintState.clearHover("browser.context.loop")
                            }
                        }
                        Label {
                            id: contextLoopStatus
                            objectName: "contextLoopStatus"
                            width: parent.width
                            visible: window.interaction.browserLoopContextStatus.length > 0
                            height: visible ? implicitHeight : 0
                            text: window.interaction.browserLoopContextStatus
                            color: theme.statusError
                            font.pixelSize: window.textCaption
                            wrapMode: Text.Wrap
                            leftPadding: 10
                            rightPadding: 10
                            topPadding: 5
                            bottomPadding: 5
                            Accessible.name: text
                        }
                    }
                }
                // #1204 OPEN disclosure — Browser collapses into its own leading edge.
                PanelDisclosureSeam {
                    id: browserCollapseHandle
                    objectName: "browserCollapseHandle"
                    z: 30
                    anchors.left: parent.left
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    seamActive: browserPane.visible
                    accessibleLabel: "Collapse Browser"
                    hintId: "panel.browser.collapse"
                    chevronText: "‹"
                    activateAction: function() { window.interaction.toggleBrowserCollapsed() }
                }
                // #692 owner-visual repair: preserve required scan columns when the
                // workspace is narrow. Type is optional; sample identity is not.
                property bool browserNarrowColumns: width < 700
                // #1211 Browser column resize — browserPane is the SINGLE owner of
                // column width truth. One user override per resizable column folds
                // into one effectiveBrowser* width shared by header + delegates.
                // Independent of panel resize / #1204 disclosure (layoutModel).
                readonly property int browserWaveformMax: 360
                readonly property int browserBpmColumnMin: 40
                readonly property int browserBpmColumnMax: 96
                readonly property int browserFavoriteColumnMin: 24
                readonly property int browserFavoriteColumnMax: 48
                readonly property int browserKeyColumnMin: 40
                readonly property int browserKeyColumnMax: 96
                readonly property int browserLengthColumnMin: 52
                readonly property int browserLengthColumnMax: 120
                readonly property int browserTypeColumnMin: 48
                readonly property int browserTypeColumnMax: 88
                readonly property int browserColumnHandlePadding: 6
                readonly property int browserColumnReorderThreshold: 8
                // #1292 runtime-only presentation order. Logical identities own widths;
                // visual index never becomes width or product-state authority.
                property var browserColumnOrder: ["waveform", "filename", "bpm", "favorite", "key", "length", "type"]
                readonly property int browserVisibleColumnCount: browserNarrowColumns ? browserColumnOrder.length - 1 : browserColumnOrder.length
                function visibleBrowserColumnIndex(role) {
                    var visibleIndex = 0
                    for (var orderIndex = 0; orderIndex < browserColumnOrder.length; orderIndex++) {
                        var currentRole = browserColumnOrder[orderIndex]
                        if (browserNarrowColumns && currentRole === "type")
                            continue
                        if (currentRole === role)
                            return visibleIndex
                        visibleIndex += 1
                    }
                    return -1
                }
                function moveBrowserColumn(role, targetRole, after) {
                    if (role === targetRole)
                        return
                    var order = browserColumnOrder.slice(0)
                    var fromIndex = order.indexOf(role)
                    if (fromIndex < 0 || order.indexOf(targetRole) < 0)
                        return
                    order.splice(fromIndex, 1)
                    var targetIndex = order.indexOf(targetRole)
                    order.splice(targetIndex + (after ? 1 : 0), 0, role)
                    browserColumnOrder = order
                }
                property int waveformUserWidth: -1
                property int bpmUserWidth: -1
                property int favoriteUserWidth: -1
                property int keyUserWidth: -1
                property int lengthUserWidth: -1
                property int typeUserWidth: -1
                function _clampColumn(value, lo, hi) { return Math.max(lo, Math.min(hi, Math.round(value))) }
                // Wide mode: user override wins when set (>= 0). Narrow mode (#692):
                // always keep responsive defaults so a prior wide-mode drag cannot
                // defeat the compact column budget when the pane shrinks below 700.
                // Overrides are ignored (not wiped) while narrow.
                function _resolveColumn(user, dflt, lo, hi) { return _clampColumn((browserNarrowColumns || user < 0) ? dflt : user, lo, hi) }
                function resizeColumn(role, deltaPx) {
                    if (role === "waveform")
                        waveformUserWidth = _clampColumn(effectiveBrowserWaveformWidth + deltaPx, window.browserWaveformMin, browserWaveformMax)
                    else if (role === "bpm")
                        bpmUserWidth = _clampColumn(effectiveBrowserBpmColumnWidth + deltaPx, browserBpmColumnMin, browserBpmColumnMax)
                    else if (role === "favorite")
                        favoriteUserWidth = _clampColumn(effectiveBrowserFavoriteColumnWidth + deltaPx, browserFavoriteColumnMin, browserFavoriteColumnMax)
                    else if (role === "key")
                        keyUserWidth = _clampColumn(effectiveBrowserKeyColumnWidth + deltaPx, browserKeyColumnMin, browserKeyColumnMax)
                    else if (role === "length")
                        lengthUserWidth = _clampColumn(effectiveBrowserLengthColumnWidth + deltaPx, browserLengthColumnMin, browserLengthColumnMax)
                    else if (role === "type")
                        typeUserWidth = _clampColumn(effectiveBrowserTypeColumnWidth + deltaPx, browserTypeColumnMin, browserTypeColumnMax)
                }
                property int effectiveBrowserWaveformWidth: _resolveColumn(waveformUserWidth, browserNarrowColumns ? window.browserWaveformMin : window.browserWaveformWidth, window.browserWaveformMin, browserWaveformMax)
                property int effectiveBrowserBpmColumnWidth: _resolveColumn(bpmUserWidth, browserNarrowColumns ? browserBpmColumnMin : window.browserMetaColumnWidth, browserBpmColumnMin, browserBpmColumnMax)
                property int effectiveBrowserFavoriteColumnWidth: _resolveColumn(favoriteUserWidth, browserNarrowColumns ? browserFavoriteColumnMin : window.browserFavoriteColumnWidth, browserFavoriteColumnMin, browserFavoriteColumnMax)
                property int effectiveBrowserKeyColumnWidth: _resolveColumn(keyUserWidth, browserNarrowColumns ? browserKeyColumnMin : window.browserMetaColumnWidth, browserKeyColumnMin, browserKeyColumnMax)
                property int effectiveBrowserLengthColumnWidth: _resolveColumn(lengthUserWidth, browserNarrowColumns ? browserLengthColumnMin : window.browserLengthColumnWidth, browserLengthColumnMin, browserLengthColumnMax)
                property int effectiveBrowserTypeColumnWidth: _resolveColumn(typeUserWidth, browserNarrowColumns ? browserTypeColumnMin : window.browserTypeColumnWidth, browserTypeColumnMin, browserTypeColumnMax)
                ColumnLayout { anchors.fill: parent; anchors.margins: 18; spacing: 10
                    RowLayout { Layout.fillWidth: true
                        ColumnLayout { Layout.fillWidth: true; spacing: 2
                            Label { text: window.screenData.browserContext; color: theme.textPrimary; font.pixelSize: window.textTitle; font.bold: true }
                            Label { text: window.screenData.browserRows.length + " samples"; color: theme.textSecondary; font.pixelSize: window.textCaption }
                            Label { visible: window.screenData.errorMessage.length > 0; text: window.screenData.errorMessage; color: theme.statusError; font.pixelSize: 11 }
                        }
                        Item { Layout.fillWidth: true }
                        TextField {
                            // #895: slim dark-native search — quiet fill, low-contrast border, calm placeholder.
                            objectName: "browserSearch"
                            placeholderText: "Search samples"
                            placeholderTextColor: theme.textMuted
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
                            // #1210: hover/focus are presentation-only; text mutation stays on onTextChanged.
                            onHoveredChanged: {
                                if (hovered)
                                    contextHintState.reportHover("browser.search")
                                else
                                    contextHintState.clearHover("browser.search")
                            }
                            onActiveFocusChanged: {
                                if (activeFocus)
                                    contextHintState.reportFocus("browser.search")
                                else
                                    contextHintState.clearFocus("browser.search")
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
                            color: window.screenData.analysisStatus === "error" ? theme.statusError : theme.textSecondary
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
                        property string activeReorderRole: ""
                        property real reorderPressSceneX: 0
                        property bool reorderThresholdPassed: false
                        function _headerItemForRole(role) {
                            if (role === "waveform") return browserHeaderWaveform
                            if (role === "filename") return browserHeaderFilename
                            if (role === "bpm") return browserHeaderBpm
                            if (role === "favorite") return browserHeaderFavorite
                            if (role === "key") return browserHeaderKey
                            if (role === "length") return browserHeaderLength
                            if (role === "type") return browserHeaderType
                            return null
                        }
                        function _visibleHeaderRoles() {
                            var roles = []
                            for (var i = 0; i < browserPane.browserColumnOrder.length; i++) {
                                var role = browserPane.browserColumnOrder[i]
                                if (browserPane.browserNarrowColumns && role === "type")
                                    continue
                                roles.push(role)
                            }
                            return roles
                        }
                        function beginColumnReorder(role, sceneX) {
                            activeReorderRole = role
                            reorderPressSceneX = sceneX
                            reorderThresholdPassed = false
                        }
                        function updateColumnReorder(role, sceneX) {
                            if (activeReorderRole !== role)
                                return
                            if (!reorderThresholdPassed) {
                                if (Math.abs(sceneX - reorderPressSceneX) < browserPane.browserColumnReorderThreshold)
                                    return
                                reorderThresholdPassed = true
                            }
                            var roles = _visibleHeaderRoles()
                            var targetRole = role
                            var after = false
                            for (var i = 0; i < roles.length; i++) {
                                var candidate = roles[i]
                                if (candidate === role)
                                    continue
                                var item = _headerItemForRole(candidate)
                                if (item === null || !item.visible)
                                    continue
                                var center = item.mapToItem(null, item.width / 2, 0).x
                                if (sceneX < center) {
                                    targetRole = candidate
                                    after = false
                                    break
                                }
                                targetRole = candidate
                                after = true
                            }
                            browserPane.moveBrowserColumn(role, targetRole, after)
                        }
                        function endColumnReorder(role) {
                            if (activeReorderRole !== role)
                                return
                            activeReorderRole = ""
                            reorderThresholdPassed = false
                        }
                        // #846/#1292: one shared GridLayout projects canonical logical
                        // column order; resize surfaces remain header-cell edge children.
                        GridLayout {
                            id: browserColumnHeaderRow
                            columns: browserPane.browserVisibleColumnCount
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.leftMargin: window.densityHorizontalInset
                            anchors.rightMargin: window.densityHorizontalInset
                            columnSpacing: window.densityRowSpacing
                            rowSpacing: 0
                            Item {
                                id: browserHeaderWaveform
                                objectName: "browserColumnHeader_waveform"
                                Layout.column: browserPane.visibleBrowserColumnIndex("waveform")
                                Layout.preferredWidth: browserPane.effectiveBrowserWaveformWidth
                                Layout.minimumWidth: browserPane.effectiveBrowserWaveformWidth
                                Layout.fillHeight: true
                                Label { anchors.fill: parent; text: "WAVEFORM"; color: theme.textSecondary; font.pixelSize: window.textCaption; font.bold: true; verticalAlignment: Text.AlignVCenter; z: 1 }
                                // #846 ephemeral overlay: MouseArea root keeps resizeColumn +
                                // theme tokens inside frozen assertion windows.
                                MouseArea { id: browserColumnReorderWaveform; objectName: "browserColumnReorder_waveform"; property string columnRole: "waveform"; z: 4; anchors.fill: parent; anchors.rightMargin: browserPane.browserColumnHandlePadding + 2; preventStealing: true; cursorShape: Qt.OpenHandCursor; onPressed: function(m) { var g = mapToItem(null, m.x, 0).x; browserColumnHeaderHost.beginColumnReorder(columnRole, g); m.accepted = true }; onPositionChanged: function(m) { if (!pressed) return; var g = mapToItem(null, m.x, 0).x; browserColumnHeaderHost.updateColumnReorder(columnRole, g) }; onReleased: browserColumnHeaderHost.endColumnReorder(columnRole); onCanceled: browserColumnHeaderHost.endColumnReorder(columnRole) }
                                MouseArea { id: browserColumnResizeWaveform; objectName: "browserColumnResize_waveform"; property color _h: theme.surfaceElevated; property color _f: theme.focusRing; property bool handleVisible: containsMouse || pressed || activeFocus; z: 8; width: 2+2*browserPane.browserColumnHandlePadding; height: Math.max(18, parent.height); anchors.right: parent.right; anchors.rightMargin: -browserPane.browserColumnHandlePadding; anchors.verticalCenter: parent.verticalCenter; hoverEnabled: true; preventStealing: true; cursorShape: Qt.SizeHorCursor; activeFocusOnTab: true; Accessible.name: "Resize waveform"; onEntered: contextHintState.reportHover("browser.resize.waveform"); onExited: contextHintState.clearHover("browser.resize.waveform"); onActiveFocusChanged: activeFocus ? contextHintState.reportFocus("browser.resize.waveform") : contextHintState.clearFocus("browser.resize.waveform"); property real lastX: 0; onPressed: function(m) { lastX = mapToItem(null, m.x, 0).x; m.accepted = true }; onPositionChanged: function(m) { if (!pressed) return; var g = mapToItem(null, m.x, 0).x; browserPane.resizeColumn("waveform", g - lastX); lastX = g }; Keys.onUpPressed: function(e) { browser.forceActiveFocus(); window.interaction.navigateBrowser(-1); e.accepted = true }; Keys.onDownPressed: function(e) { browser.forceActiveFocus(); window.interaction.navigateBrowser(1); e.accepted = true }; Keys.onEscapePressed: function(e) { browser.forceActiveFocus(); window.interaction.stopPreview(); e.accepted = true }; Rectangle { anchors.centerIn: parent; width: 2; height: parent.height - 4; radius: 1; color: parent.activeFocus ? parent._f : parent._h; opacity: parent.handleVisible ? 0.95 : 0; border.width: parent.activeFocus ? 1 : 0; border.color: parent._f } }
                            }
                            Label { id: browserHeaderFilename; objectName: "browserColumnHeader_filename"; text: "DATEINAME"; color: theme.textSecondary; Layout.column: browserPane.visibleBrowserColumnIndex("filename"); Layout.fillWidth: true; Layout.minimumWidth: browserPane.browserNarrowColumns ? 96 : 120; font.pixelSize: window.textCaption; font.bold: true
                                MouseArea { id: browserColumnReorderFilename; objectName: "browserColumnReorder_filename"; property string columnRole: "filename"; z: 4; anchors.fill: parent; anchors.rightMargin: 0; preventStealing: true; cursorShape: Qt.OpenHandCursor; onPressed: function(m) { var g = mapToItem(null, m.x, 0).x; browserColumnHeaderHost.beginColumnReorder(columnRole, g); m.accepted = true }; onPositionChanged: function(m) { if (!pressed) return; var g = mapToItem(null, m.x, 0).x; browserColumnHeaderHost.updateColumnReorder(columnRole, g) }; onReleased: browserColumnHeaderHost.endColumnReorder(columnRole); onCanceled: browserColumnHeaderHost.endColumnReorder(columnRole) }
                            }
                            Label {
                                id: browserHeaderBpm
                                objectName: "browserColumnHeader_bpm"
                                text: "BPM"
                                color: theme.textSecondary
                                Layout.column: browserPane.visibleBrowserColumnIndex("bpm")
                                Layout.preferredWidth: browserPane.effectiveBrowserBpmColumnWidth
                                horizontalAlignment: Text.AlignRight
                                font.pixelSize: window.textCaption
                                font.bold: true
                                MouseArea { id: browserColumnReorderBpm; objectName: "browserColumnReorder_bpm"; property string columnRole: "bpm"; z: 4; anchors.fill: parent; anchors.rightMargin: browserPane.browserColumnHandlePadding + 2; preventStealing: true; cursorShape: Qt.OpenHandCursor; onPressed: function(m) { var g = mapToItem(null, m.x, 0).x; browserColumnHeaderHost.beginColumnReorder(columnRole, g); m.accepted = true }; onPositionChanged: function(m) { if (!pressed) return; var g = mapToItem(null, m.x, 0).x; browserColumnHeaderHost.updateColumnReorder(columnRole, g) }; onReleased: browserColumnHeaderHost.endColumnReorder(columnRole); onCanceled: browserColumnHeaderHost.endColumnReorder(columnRole) }
                                MouseArea { id: browserColumnResizeBpm; objectName: "browserColumnResize_bpm"; property color _h: theme.surfaceElevated; property color _f: theme.focusRing; property bool handleVisible: containsMouse || pressed || activeFocus; z: 8; width: 2+2*browserPane.browserColumnHandlePadding; height: Math.max(18, parent.height); anchors.right: parent.right; anchors.rightMargin: -browserPane.browserColumnHandlePadding; anchors.verticalCenter: parent.verticalCenter; hoverEnabled: true; preventStealing: true; cursorShape: Qt.SizeHorCursor; activeFocusOnTab: true; Accessible.name: "Resize BPM"; onEntered: contextHintState.reportHover("browser.resize.bpm"); onExited: contextHintState.clearHover("browser.resize.bpm"); onActiveFocusChanged: activeFocus ? contextHintState.reportFocus("browser.resize.bpm") : contextHintState.clearFocus("browser.resize.bpm"); property real lastX: 0; onPressed: function(m) { lastX = mapToItem(null, m.x, 0).x; m.accepted = true }; onPositionChanged: function(m) { if (!pressed) return; var g = mapToItem(null, m.x, 0).x; browserPane.resizeColumn("bpm", g - lastX); lastX = g }; Keys.onUpPressed: function(e) { browser.forceActiveFocus(); window.interaction.navigateBrowser(-1); e.accepted = true }; Keys.onDownPressed: function(e) { browser.forceActiveFocus(); window.interaction.navigateBrowser(1); e.accepted = true }; Keys.onEscapePressed: function(e) { browser.forceActiveFocus(); window.interaction.stopPreview(); e.accepted = true }; Rectangle { anchors.centerIn: parent; width: 2; height: parent.height - 4; radius: 1; color: parent.activeFocus ? parent._f : parent._h; opacity: parent.handleVisible ? 0.95 : 0; border.width: parent.activeFocus ? 1 : 0; border.color: parent._f } }
                            }
                            Label {
                                id: browserHeaderFavorite
                                objectName: "browserColumnHeader_favorite"
                                text: "FAV"
                                color: theme.textSecondary
                                Layout.column: browserPane.visibleBrowserColumnIndex("favorite")
                                Layout.preferredWidth: browserPane.effectiveBrowserFavoriteColumnWidth
                                horizontalAlignment: Text.AlignHCenter
                                font.pixelSize: window.textCaption
                                font.bold: true
                                MouseArea { id: browserColumnReorderFavorite; objectName: "browserColumnReorder_favorite"; property string columnRole: "favorite"; z: 4; anchors.fill: parent; anchors.rightMargin: browserPane.browserColumnHandlePadding + 2; preventStealing: true; cursorShape: Qt.OpenHandCursor; onPressed: function(m) { var g = mapToItem(null, m.x, 0).x; browserColumnHeaderHost.beginColumnReorder(columnRole, g); m.accepted = true }; onPositionChanged: function(m) { if (!pressed) return; var g = mapToItem(null, m.x, 0).x; browserColumnHeaderHost.updateColumnReorder(columnRole, g) }; onReleased: browserColumnHeaderHost.endColumnReorder(columnRole); onCanceled: browserColumnHeaderHost.endColumnReorder(columnRole) }
                                MouseArea { id: browserColumnResizeFavorite; objectName: "browserColumnResize_favorite"; property color _h: theme.surfaceElevated; property color _f: theme.focusRing; property bool handleVisible: containsMouse || pressed || activeFocus; z: 8; width: 2+2*browserPane.browserColumnHandlePadding; height: Math.max(18, parent.height); anchors.right: parent.right; anchors.rightMargin: -browserPane.browserColumnHandlePadding; anchors.verticalCenter: parent.verticalCenter; hoverEnabled: true; preventStealing: true; cursorShape: Qt.SizeHorCursor; activeFocusOnTab: true; Accessible.name: "Resize favorite"; onEntered: contextHintState.reportHover("browser.resize.favorite"); onExited: contextHintState.clearHover("browser.resize.favorite"); onActiveFocusChanged: activeFocus ? contextHintState.reportFocus("browser.resize.favorite") : contextHintState.clearFocus("browser.resize.favorite"); property real lastX: 0; onPressed: function(m) { lastX = mapToItem(null, m.x, 0).x; m.accepted = true }; onPositionChanged: function(m) { if (!pressed) return; var g = mapToItem(null, m.x, 0).x; browserPane.resizeColumn("favorite", g - lastX); lastX = g }; Keys.onUpPressed: function(e) { browser.forceActiveFocus(); window.interaction.navigateBrowser(-1); e.accepted = true }; Keys.onDownPressed: function(e) { browser.forceActiveFocus(); window.interaction.navigateBrowser(1); e.accepted = true }; Keys.onEscapePressed: function(e) { browser.forceActiveFocus(); window.interaction.stopPreview(); e.accepted = true }; Rectangle { anchors.centerIn: parent; width: 2; height: parent.height - 4; radius: 1; color: parent.activeFocus ? parent._f : parent._h; opacity: parent.handleVisible ? 0.95 : 0; border.width: parent.activeFocus ? 1 : 0; border.color: parent._f } }
                            }
                            Label {
                                id: browserHeaderKey
                                objectName: "browserColumnHeader_key"
                                text: "KEY"
                                color: theme.textSecondary
                                Layout.column: browserPane.visibleBrowserColumnIndex("key")
                                Layout.preferredWidth: browserPane.effectiveBrowserKeyColumnWidth
                                horizontalAlignment: Text.AlignRight
                                font.pixelSize: window.textCaption
                                font.bold: true
                                MouseArea { id: browserColumnReorderKey; objectName: "browserColumnReorder_key"; property string columnRole: "key"; z: 4; anchors.fill: parent; anchors.rightMargin: browserPane.browserColumnHandlePadding + 2; preventStealing: true; cursorShape: Qt.OpenHandCursor; onPressed: function(m) { var g = mapToItem(null, m.x, 0).x; browserColumnHeaderHost.beginColumnReorder(columnRole, g); m.accepted = true }; onPositionChanged: function(m) { if (!pressed) return; var g = mapToItem(null, m.x, 0).x; browserColumnHeaderHost.updateColumnReorder(columnRole, g) }; onReleased: browserColumnHeaderHost.endColumnReorder(columnRole); onCanceled: browserColumnHeaderHost.endColumnReorder(columnRole) }
                                MouseArea { id: browserColumnResizeKey; objectName: "browserColumnResize_key"; property color _h: theme.surfaceElevated; property color _f: theme.focusRing; property bool handleVisible: containsMouse || pressed || activeFocus; z: 8; width: 2+2*browserPane.browserColumnHandlePadding; height: Math.max(18, parent.height); anchors.right: parent.right; anchors.rightMargin: -browserPane.browserColumnHandlePadding; anchors.verticalCenter: parent.verticalCenter; hoverEnabled: true; preventStealing: true; cursorShape: Qt.SizeHorCursor; activeFocusOnTab: true; Accessible.name: "Resize key"; onEntered: contextHintState.reportHover("browser.resize.key"); onExited: contextHintState.clearHover("browser.resize.key"); onActiveFocusChanged: activeFocus ? contextHintState.reportFocus("browser.resize.key") : contextHintState.clearFocus("browser.resize.key"); property real lastX: 0; onPressed: function(m) { lastX = mapToItem(null, m.x, 0).x; m.accepted = true }; onPositionChanged: function(m) { if (!pressed) return; var g = mapToItem(null, m.x, 0).x; browserPane.resizeColumn("key", g - lastX); lastX = g }; Keys.onUpPressed: function(e) { browser.forceActiveFocus(); window.interaction.navigateBrowser(-1); e.accepted = true }; Keys.onDownPressed: function(e) { browser.forceActiveFocus(); window.interaction.navigateBrowser(1); e.accepted = true }; Keys.onEscapePressed: function(e) { browser.forceActiveFocus(); window.interaction.stopPreview(); e.accepted = true }; Rectangle { anchors.centerIn: parent; width: 2; height: parent.height - 4; radius: 1; color: parent.activeFocus ? parent._f : parent._h; opacity: parent.handleVisible ? 0.95 : 0; border.width: parent.activeFocus ? 1 : 0; border.color: parent._f } }
                            }
                            Label {
                                id: browserHeaderLength
                                objectName: "browserColumnHeader_length"
                                text: "LENGTH"
                                color: theme.textSecondary
                                Layout.column: browserPane.visibleBrowserColumnIndex("length")
                                Layout.preferredWidth: browserPane.effectiveBrowserLengthColumnWidth
                                horizontalAlignment: Text.AlignRight
                                font.pixelSize: window.textCaption
                                font.bold: true
                                MouseArea { id: browserColumnReorderLength; objectName: "browserColumnReorder_length"; property string columnRole: "length"; z: 4; anchors.fill: parent; anchors.rightMargin: browserPane.browserColumnHandlePadding + 2; preventStealing: true; cursorShape: Qt.OpenHandCursor; onPressed: function(m) { var g = mapToItem(null, m.x, 0).x; browserColumnHeaderHost.beginColumnReorder(columnRole, g); m.accepted = true }; onPositionChanged: function(m) { if (!pressed) return; var g = mapToItem(null, m.x, 0).x; browserColumnHeaderHost.updateColumnReorder(columnRole, g) }; onReleased: browserColumnHeaderHost.endColumnReorder(columnRole); onCanceled: browserColumnHeaderHost.endColumnReorder(columnRole) }
                                MouseArea { id: browserColumnResizeLength; objectName: "browserColumnResize_length"; property color _h: theme.surfaceElevated; property color _f: theme.focusRing; property bool handleVisible: containsMouse || pressed || activeFocus; z: 8; width: 2+2*browserPane.browserColumnHandlePadding; height: Math.max(18, parent.height); anchors.right: parent.right; anchors.rightMargin: -browserPane.browserColumnHandlePadding; anchors.verticalCenter: parent.verticalCenter; hoverEnabled: true; preventStealing: true; cursorShape: Qt.SizeHorCursor; activeFocusOnTab: true; Accessible.name: "Resize length"; onEntered: contextHintState.reportHover("browser.resize.length"); onExited: contextHintState.clearHover("browser.resize.length"); onActiveFocusChanged: activeFocus ? contextHintState.reportFocus("browser.resize.length") : contextHintState.clearFocus("browser.resize.length"); property real lastX: 0; onPressed: function(m) { lastX = mapToItem(null, m.x, 0).x; m.accepted = true }; onPositionChanged: function(m) { if (!pressed) return; var g = mapToItem(null, m.x, 0).x; browserPane.resizeColumn("length", g - lastX); lastX = g }; Keys.onUpPressed: function(e) { browser.forceActiveFocus(); window.interaction.navigateBrowser(-1); e.accepted = true }; Keys.onDownPressed: function(e) { browser.forceActiveFocus(); window.interaction.navigateBrowser(1); e.accepted = true }; Keys.onEscapePressed: function(e) { browser.forceActiveFocus(); window.interaction.stopPreview(); e.accepted = true }; Rectangle { anchors.centerIn: parent; width: 2; height: parent.height - 4; radius: 1; color: parent.activeFocus ? parent._f : parent._h; opacity: parent.handleVisible ? 0.95 : 0; border.width: parent.activeFocus ? 1 : 0; border.color: parent._f } }
                            }
                            // Issue 850: Type header shares visibility + width with the Type value cell so
                            // Length never visually hosts Type labels under a shifted trailing geometry.
                            Label {
                                id: browserHeaderType
                                objectName: "browserColumnHeader_type"
                                visible: !browserPane.browserNarrowColumns
                                text: "TYPE"
                                color: theme.textSecondary
                                Layout.column: browserPane.visibleBrowserColumnIndex("type")
                                Layout.preferredWidth: browserPane.effectiveBrowserTypeColumnWidth
                                horizontalAlignment: Text.AlignLeft
                                font.pixelSize: window.textCaption
                                font.bold: true
                                MouseArea { id: browserColumnReorderType; objectName: "browserColumnReorder_type"; property string columnRole: "type"; z: 4; anchors.fill: parent; anchors.rightMargin: browserPane.browserColumnHandlePadding + 2; preventStealing: true; cursorShape: Qt.OpenHandCursor; onPressed: function(m) { var g = mapToItem(null, m.x, 0).x; browserColumnHeaderHost.beginColumnReorder(columnRole, g); m.accepted = true }; onPositionChanged: function(m) { if (!pressed) return; var g = mapToItem(null, m.x, 0).x; browserColumnHeaderHost.updateColumnReorder(columnRole, g) }; onReleased: browserColumnHeaderHost.endColumnReorder(columnRole); onCanceled: browserColumnHeaderHost.endColumnReorder(columnRole) }
                                MouseArea { id: browserColumnResizeType; objectName: "browserColumnResize_type"; property color _h: theme.surfaceElevated; property color _f: theme.focusRing; property bool handleVisible: containsMouse || pressed || activeFocus; z: 8; width: 2+2*browserPane.browserColumnHandlePadding; height: Math.max(18, parent.height); anchors.right: parent.right; anchors.rightMargin: -browserPane.browserColumnHandlePadding; anchors.verticalCenter: parent.verticalCenter; hoverEnabled: true; preventStealing: true; cursorShape: Qt.SizeHorCursor; activeFocusOnTab: true; Accessible.name: "Resize type"; onEntered: contextHintState.reportHover("browser.resize.type"); onExited: contextHintState.clearHover("browser.resize.type"); onActiveFocusChanged: activeFocus ? contextHintState.reportFocus("browser.resize.type") : contextHintState.clearFocus("browser.resize.type"); property real lastX: 0; onPressed: function(m) { lastX = mapToItem(null, m.x, 0).x; m.accepted = true }; onPositionChanged: function(m) { if (!pressed) return; var g = mapToItem(null, m.x, 0).x; browserPane.resizeColumn("type", g - lastX); lastX = g }; Keys.onUpPressed: function(e) { browser.forceActiveFocus(); window.interaction.navigateBrowser(-1); e.accepted = true }; Keys.onDownPressed: function(e) { browser.forceActiveFocus(); window.interaction.navigateBrowser(1); e.accepted = true }; Keys.onEscapePressed: function(e) { browser.forceActiveFocus(); window.interaction.stopPreview(); e.accepted = true }; Rectangle { anchors.centerIn: parent; width: 2; height: parent.height - 4; radius: 1; color: parent.activeFocus ? parent._f : parent._h; opacity: parent.handleVisible ? 0.95 : 0; border.width: parent.activeFocus ? 1 : 0; border.color: parent._f } }
                            }
                        }
                    }
                    // #1281: settle timer lives on the pane (not inside browserList) so playhead
                    // contracts stay free of per-list Timer clutter; presentation-only.
                    Timer {
                        id: browserHoverSettleTimer
                        objectName: "browserHoverSettleTimer"
                        interval: 120
                        repeat: false
                        onTriggered: browser.hoverScrollSuppressing = false
                    }
                    // All Samples list-viewport reuses Clean-Start canvas fill (theme.surfaceRoot).
                    // Outer browserPane chrome stays surfaceBrowser; Library/Harmony/Live Kit unchanged.
                    Rectangle {
                        id: browserListViewport
                        objectName: "browserListViewport"
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        color: theme.surfaceRoot
                        ListView {
                        id: browser
                        objectName: "browserList"
                        anchors.fill: parent
                        model: window.screenData.browserRows
                        clip: true
                        reuseItems: true
                        focus: true
                        property int rowHeight: window.densityRowHeight
                        // #1285: one owner row expands in-place; ordinary Browser rows keep compact density.
                        property int loopOwnerRowHeight: 112
                        property int waveformPrefetchMargin: 2
                        // #1285 presentation-only handoff state. Product owner identity stays in Python.
                        property string loopOwnerPathProjection: window.interaction.browserLoopOwnerPath
                        property int loopOwnerVisibleIndex: -1
                        property bool loopOwnerInlineVisible: false
                        property string loopStickyEdge: "none"
                        property string loopStickyEdgeMemory: "bottom"
                        implicitHeight: window.densityRowHeight * 2
                        // #1281: presentation-only waveform hover (not product state).
                        property int hoveredWaveformIndex: -1
                        property bool hoverScrollSuppressing: false
                        readonly property bool hoverGeometryAllowed: !window.screenData.brandReducedMotion
                        readonly property real waveformHoverScalePrimary: 1.024
                        readonly property real waveformHoverScaleNeighbour: 1.007
                        property int hoverSettleMs: 120
                        function setHoveredWaveform(i) { hoveredWaveformIndex = i }
                        function clearHoveredWaveform(i) { if (hoveredWaveformIndex === i) hoveredWaveformIndex = -1 }
                        function resolveLoopOwnerIndex() {
                            if (!window.interaction.browserLoopActive || loopOwnerPathProjection.length === 0) {
                                loopOwnerVisibleIndex = -1
                                loopOwnerInlineVisible = false
                                loopStickyEdge = "none"
                                return
                            }
                            var rows = window.screenData.browserRows
                            var resolved = -1
                            for (var ownerIndex = 0; ownerIndex < rows.length; ownerIndex++) {
                                if (("" + rows[ownerIndex].path) === ("" + loopOwnerPathProjection)) {
                                    resolved = ownerIndex
                                    break
                                }
                            }
                            loopOwnerVisibleIndex = resolved
                            reconcileLoopPresentation()
                        }
                        function reconcileLoopPresentation() {
                            if (!window.interaction.browserLoopActive || loopOwnerPathProjection.length === 0) {
                                loopOwnerInlineVisible = false
                                loopStickyEdge = "none"
                                return
                            }
                            if (loopOwnerVisibleIndex < 0) {
                                loopOwnerInlineVisible = false
                                loopStickyEdge = loopStickyEdgeMemory === "none" ? "bottom" : loopStickyEdgeMemory
                                return
                            }
                            var first = visibleIndexNear(1, 1)
                            var last = visibleIndexNear(Math.max(1, height - 2), -1)
                            if (first >= 0 && loopOwnerVisibleIndex < first) {
                                loopOwnerInlineVisible = false
                                loopStickyEdge = "top"
                                loopStickyEdgeMemory = "top"
                                return
                            }
                            if (last >= 0 && loopOwnerVisibleIndex > last) {
                                loopOwnerInlineVisible = false
                                loopStickyEdge = "bottom"
                                loopStickyEdgeMemory = "bottom"
                                return
                            }
                            var ownerItem = itemAtIndex(loopOwnerVisibleIndex)
                            if (ownerItem !== null) {
                                var mapped = ownerItem.mapToItem(browser, 0, 0)
                                var ownerTop = mapped.y
                                var ownerBottom = ownerTop + ownerItem.height
                                if (ownerBottom <= 0) {
                                    loopOwnerInlineVisible = false
                                    loopStickyEdge = "top"
                                    loopStickyEdgeMemory = "top"
                                    return
                                }
                                if (ownerTop >= height) {
                                    loopOwnerInlineVisible = false
                                    loopStickyEdge = "bottom"
                                    loopStickyEdgeMemory = "bottom"
                                    return
                                }
                                loopOwnerInlineVisible = true
                                loopStickyEdge = "none"
                                loopStickyEdgeMemory = (ownerTop + ownerBottom) / 2 < height / 2 ? "top" : "bottom"
                                return
                            }
                            // Delegate may be between pool/reuse frames. Fail closed to one Sticky.
                            loopOwnerInlineVisible = false
                            if (first >= 0 && loopOwnerVisibleIndex <= first)
                                loopStickyEdgeMemory = "top"
                            else if (last >= 0 && loopOwnerVisibleIndex >= last)
                                loopStickyEdgeMemory = "bottom"
                            loopStickyEdge = loopStickyEdgeMemory === "none" ? "bottom" : loopStickyEdgeMemory
                        }
                        onLoopOwnerPathProjectionChanged: Qt.callLater(resolveLoopOwnerIndex)
                        onMovementStarted: { hoverScrollSuppressing = true; browserHoverSettleTimer.stop() }
                        onMovementEnded: browserHoverSettleTimer.restart()
                        onFlickStarted: { hoverScrollSuppressing = true; browserHoverSettleTimer.stop() }
                        onFlickEnded: browserHoverSettleTimer.restart()
                        function visibleIndexNear(viewportY, direction) {
                            if (width <= 0 || height <= 0 || window.screenData.browserRows.length <= 0)
                                return -1
                            var baseY = contentY + Math.max(0, Math.min(height - 1, viewportY))
                            var probeX = Math.max(1, width * 0.5)
                            var stride = Math.max(1, Math.floor(rowHeight / 4))
                            var budget = Math.max(rowHeight, 32)
                            for (var delta = 0; delta <= budget; delta += stride) {
                                var found = indexAt(probeX, baseY + direction * delta)
                                if (found >= 0)
                                    return found
                            }
                            return indexAt(probeX, contentY + height * 0.5)
                        }
                        // Cached presentation diagnostics; recomputed from actual delegate geometry.
                        property int waveformFirstVisibleIndex: -1
                        property int waveformLastVisibleIndex: -1
                        function requestVisibleWaveforms() {
                            var first = visibleIndexNear(1, 1)
                            if (first < 0)
                                return
                            var last = visibleIndexNear(Math.max(1, height - 2), -1)
                            if (last < first)
                                last = first
                            waveformFirstVisibleIndex = first
                            waveformLastVisibleIndex = last
                            var endExclusive = Math.min(
                                window.screenData.browserRows.length,
                                last + 1 + waveformPrefetchMargin
                            )
                            window.interaction.requestWaveforms(first, Math.max(1, endExclusive - first))
                        }
                        Component.onCompleted: Qt.callLater(function() {
                            requestVisibleWaveforms()
                            resolveLoopOwnerIndex()
                        })
                        onContentYChanged: {
                            requestVisibleWaveforms()
                            reconcileLoopPresentation()
                        }
                        onHeightChanged: {
                            requestVisibleWaveforms()
                            reconcileLoopPresentation()
                        }
                        onContentHeightChanged: Qt.callLater(function() {
                            requestVisibleWaveforms()
                            reconcileLoopPresentation()
                        })
                        onModelChanged: Qt.callLater(function() {
                            requestVisibleWaveforms()
                            resolveLoopOwnerIndex()
                        })
                        Keys.onPressed: function(event) {
                            if (event.key === Qt.Key_Down) { window.interaction.navigateBrowser(1); event.accepted = true }
                            else if (event.key === Qt.Key_Up) { window.interaction.navigateBrowser(-1); event.accepted = true }
                            else if (event.key === Qt.Key_Escape) { window.interaction.escapeLiveKitContext(); event.accepted = true }
                            else if (event.key === Qt.Key_Menu || (event.key === Qt.Key_F10 && (event.modifiers & Qt.ShiftModifier))) {
                                if (window.screenData.selectedBrowserIndex >= 0) {
                                    browserPane.openSampleContextMenu(window.screenData.selectedBrowserIndex, browser.width * 0.35, browser.mapToItem(browserPane, 0, browser.height * 0.25).y)
                                    event.accepted = true
                                }
                            }
                        }
                        delegate: Rectangle {
                            id: browserRow
                            width: browser.width
                            readonly property bool isLoopOwner: window.interaction.browserLoopActive
                                && (("" + modelData.path) === ("" + window.interaction.browserLoopOwnerPath))
                            height: browserRow.isLoopOwner ? browser.loopOwnerRowHeight : browser.rowHeight
                            color: index === window.screenData.selectedBrowserIndex ? theme.selectionSurface : "transparent"
                            border.width: index === window.screenData.selectedBrowserIndex ? 1 : 0
                            border.color: theme.selectionBorder
                            // #1281/#1285: pooled delegates keep no live presentation residue.
                            property int logicalIndex: index
                            property bool presentationPooled: false
                            Component.onCompleted: {
                                window.browserDelegateCreations += 1
                                Qt.callLater(browser.reconcileLoopPresentation)
                            }
                            property string outboundUrl: window.interaction.outboundFileUrl(index)
                            // #1073: internal Sample payload from the frozen #1072 descriptor.
                            property string internalSampleDescriptor: window.interaction.internalSampleDragEnabled ? window.interaction.requestInternalSampleDragDescriptor(index, "browser") : ""
                            // One delivery id per drag (minted at drag start) so a repeated
                            // delivery of the same drag is idempotent, not a second mutation.
                            property string internalDeliveryId: ""
                            Drag.active: rowSelection.dragActive
                            Drag.dragType: Drag.Automatic
                            Drag.supportedActions: Qt.CopyAction
                            Drag.keys: {
                                var k = []
                                if (browserRow.internalSampleDescriptor.length > 0)
                                    k.push("application/x-sample-brain-internal-sample")
                                if (browserRow.outboundUrl.length > 0)
                                    k.push("text/uri-list")
                                return k
                            }
                            Drag.mimeData: {
                                var payload = {}
                                if (browserRow.internalSampleDescriptor.length > 0)
                                    payload["application/x-sample-brain-internal-sample"] = browserRow.internalSampleDescriptor
                                if (browserRow.internalDeliveryId.length > 0)
                                    payload["application/x-sample-brain-internal-delivery"] = browserRow.internalDeliveryId
                                if (browserRow.outboundUrl.length > 0)
                                    payload["text/uri-list"] = browserRow.outboundUrl
                                return payload
                            }
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
                                    browserRow.internalDeliveryId = ""
                                    pressX = mouse.x
                                    pressY = mouse.y
                                    browserRow.outboundUrl = window.interaction.outboundFileUrl(index)
                                }
                                onPositionChanged: function(mouse) {
                                    if (!pressed || dragActive)
                                        return
                                    if (browserRow.outboundUrl.length === 0 && browserRow.internalSampleDescriptor.length === 0)
                                        return
                                    if (Math.abs(mouse.x - pressX) < 8 && Math.abs(mouse.y - pressY) < 8)
                                        return
                                    var fresh = window.interaction.requestInternalSampleDragDescriptor(index, "browser")
                                    browserRow.internalSampleDescriptor = fresh
                                    if (browserRow.internalSampleDescriptor.length > 0 && browserRow.internalDeliveryId.length === 0) {
                                        browserRow.internalDeliveryId = window.interaction.beginInternalSampleDrag()
                                    } else if (browserRow.internalSampleDescriptor.length === 0) {
                                        // No internal payload; clear any stale delivery if present
                                        browserRow.internalDeliveryId = ""
                                    }
                                    // Activate drag if we have any valid payload for this drag
                                    if (browserRow.internalSampleDescriptor.length > 0 || browserRow.outboundUrl.length > 0) {
                                        dragActive = true
                                    }
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
                                    if (browserRow.isLoopOwner)
                                        window.interaction.previewRow(index)
                                    else
                                        window.interaction.selectRow(index)
                                }
                                // #1210: stable row-family hint (no row identity); leave restores selection context.
                                // #1281: row pointer drives waveform-hover index only (presentation).
                                onEntered: {
                                    contextHintState.reportHover("browser.sample_row")
                                    browser.setHoveredWaveform(index)
                                }
                                onExited: {
                                    contextHintState.clearHover("browser.sample_row")
                                    browser.clearHoveredWaveform(index)
                                }
                            }
                            ListView.onPooled: {
                                presentationPooled = true
                                // Virtualized reuse must not keep stale hover/Loop presentation.
                                if (rowSelection.containsMouse)
                                    contextHintState.clearHover("browser.sample_row")
                                if (waveformHover.containsMouse)
                                    contextHintState.clearHover("browser.audition")
                                if (favoriteMouseArea.containsMouse)
                                    contextHintState.clearHover("browser.favorite")
                                browser.clearHoveredWaveform(browserRow.logicalIndex)
                                Qt.callLater(browser.reconcileLoopPresentation)
                            }
                            ListView.onReused: {
                                presentationPooled = false
                                browserRow.logicalIndex = index
                                Qt.callLater(browser.reconcileLoopPresentation)
                            }
                            Item {
                                id: loopInlineSurface
                                objectName: "browserLoopInlineSurface"
                                visible: !browserRow.presentationPooled
                                    && browserRow.width > 0
                                    && browserRow.height > 0
                                    && browserRow.isLoopOwner
                                    && browser.loopOwnerInlineVisible
                                    && browser.loopOwnerVisibleIndex === index
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.bottom: parent.bottom
                                anchors.leftMargin: window.densityHorizontalInset
                                anchors.rightMargin: window.densityHorizontalInset
                                anchors.topMargin: 8
                                anchors.bottomMargin: 8
                                z: 2
                                Item {
                                    id: loopInlineWaveform
                                    objectName: "browserLoopInlineWaveform"
                                    anchors.fill: parent
                                    Canvas {
                                        id: loopInlineWaveformCanvas
                                        anchors.fill: parent
                                        property var envelope: modelData.waveform
                                        property bool waveformAligned: window.interaction.browserLoopWaveformAligned
                                        property real waveformStartRatio: window.interaction.browserLoopWaveformStartRatio
                                        property real waveformEndRatio: window.interaction.browserLoopWaveformEndRatio
                                        onEnvelopeChanged: requestPaint()
                                        onWaveformAlignedChanged: requestPaint()
                                        onWaveformStartRatioChanged: requestPaint()
                                        onWaveformEndRatioChanged: requestPaint()
                                        onPaint: {
                                            var context = getContext("2d")
                                            context.clearRect(0, 0, width, height)
                                            if (!waveformAligned)
                                                return
                                            context.strokeStyle = theme.waveformActive
                                            context.lineWidth = 1.4
                                            context.beginPath()
                                            var points = envelope || []
                                            var center = height / 2
                                            if (points.length === 0) {
                                                context.moveTo(0, center)
                                                context.lineTo(width, center)
                                            } else {
                                                var startIndex = Math.max(0, Math.min(points.length - 1, Math.floor(waveformStartRatio * points.length)))
                                                var endIndex = Math.max(startIndex + 1, Math.min(points.length, Math.ceil(waveformEndRatio * points.length)))
                                                var visibleCount = Math.max(1, endIndex - startIndex)
                                                var step = width / visibleCount
                                                for (var point = startIndex; point < endIndex; point++) {
                                                    var value = Math.max(0, Math.min(1, Number(points[point]) || 0))
                                                    var localPoint = point - startIndex
                                                    var x = Math.min(width, localPoint * step + step / 2)
                                                    var amplitude = Math.max(1, height * 0.38 * value)
                                                    context.moveTo(x, center - amplitude)
                                                    context.lineTo(x, center + amplitude)
                                                }
                                            }
                                            context.stroke()
                                        }
                                    }
                                    Repeater {
                                        model: window.interaction.browserLoopBarPositions
                                        Rectangle {
                                            width: 1
                                            height: loopInlineWaveform.height
                                            x: Math.round(Math.max(0, Math.min(1, Number(modelData) || 0)) * Math.max(0, loopInlineWaveform.width - width))
                                            color: theme.dividerDefault
                                            opacity: 0.42
                                        }
                                    }
                                    Rectangle {
                                        id: loopInlinePlayhead
                                        objectName: "browserLoopInlinePlayhead"
                                        width: 2
                                        height: parent.height
                                        color: theme.textPrimary
                                        opacity: 0.9
                                        visible: window.loopPlayheadArmed
                                        x: Math.round(
                                            Math.max(0, Math.min(1, window.interaction.browserLoopProgress))
                                            * Math.max(0, parent.width - width)
                                        )
                                    }
                                }
                                Label {
                                    anchors.left: parent.left
                                    anchors.top: parent.top
                                    anchors.leftMargin: 8
                                    anchors.topMargin: 5
                                    text: modelData.name
                                    color: theme.textPrimary
                                    opacity: 0.88
                                    font.pixelSize: window.textBody
                                    elide: Text.ElideRight
                                    width: Math.max(80, parent.width - 96)
                                }
                                Label {
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    anchors.rightMargin: 8
                                    anchors.topMargin: 5
                                    text: "LOOP"
                                    color: theme.actionActive
                                    opacity: 0.78
                                    font.pixelSize: window.textCaption
                                }
                            }
                            GridLayout { id: rowBody; visible: !browserRow.isLoopOwner; columns: browserPane.browserVisibleColumnCount; anchors.fill: parent; anchors.leftMargin: window.densityHorizontalInset; anchors.rightMargin: window.densityHorizontalInset; anchors.topMargin: window.densityVerticalInset; anchors.bottomMargin: window.densityVerticalInset; columnSpacing: window.densityRowSpacing; rowSpacing: 0; z: 1
                                Item { id: waveformSurface; objectName: "browserWaveformSurface"; Layout.column: browserPane.visibleBrowserColumnIndex("waveform"); Layout.preferredWidth: browserPane.effectiveBrowserWaveformWidth; Layout.minimumWidth: browserPane.effectiveBrowserWaveformWidth; Layout.preferredHeight: window.densityWaveformHeight; Layout.maximumHeight: window.densityWaveformHeight
                                    // #1281: transform/presentation only — layout height stays densityWaveformHeight.
                                    property int rowIndex: index
                                    readonly property bool isPrimaryHover: !browserRow.isLoopOwner && browser.hoveredWaveformIndex === index
                                    readonly property bool isNeighbourHover: !browserRow.isLoopOwner && browser.hoveredWaveformIndex >= 0 && Math.abs(index - browser.hoveredWaveformIndex) === 1
                                    readonly property string waveformHoverRole: isPrimaryHover ? "primary" : (isNeighbourHover ? "neighbour" : "none")
                                    readonly property bool waveformHoverLuminanceActive: isPrimaryHover || isNeighbourHover
                                    readonly property real waveformHoverScale: {
                                        if (!isPrimaryHover && !isNeighbourHover)
                                            return 1.0
                                        if (browser.hoverScrollSuppressing || !browser.hoverGeometryAllowed)
                                            return 1.0
                                        return isPrimaryHover ? browser.waveformHoverScalePrimary : browser.waveformHoverScaleNeighbour
                                    }
                                    readonly property real waveformHoverLiftY: {
                                        if (waveformHoverScale === 1.0)
                                            return 0
                                        return isPrimaryHover ? -2 : -1
                                    }
                                    transform: [
                                        Scale {
                                            origin.x: waveformSurface.width / 2
                                            origin.y: waveformSurface.height / 2
                                            xScale: waveformSurface.waveformHoverScale
                                            yScale: waveformSurface.waveformHoverScale
                                        },
                                        Translate { y: waveformSurface.waveformHoverLiftY }
                                    ]
                                    Rectangle {
                                        anchors.fill: parent
                                        radius: 5
                                        z: -1
                                        visible: waveformSurface.waveformHoverLuminanceActive && !browser.hoverScrollSuppressing
                                        color: theme.hoverSurface
                                        opacity: waveformSurface.isPrimaryHover ? 0.55 : 0.28
                                    }
                                    Canvas { id: waveformCanvas; anchors.fill: parent; property var envelope: modelData.waveform
                                        property bool waveformSelected: index === window.screenData.selectedBrowserIndex
                                        property string hoverRole: waveformSurface.waveformHoverRole
                                        property bool scrollQuiet: browser.hoverScrollSuppressing
                                        onEnvelopeChanged: requestPaint()
                                        onWaveformSelectedChanged: requestPaint()
                                        onHoverRoleChanged: requestPaint()
                                        onScrollQuietChanged: requestPaint()
                                        onPaint: {
                                            var context = getContext("2d")
                                            context.clearRect(0, 0, width, height)
                                            // Keep selected ternary for paint contracts; hover only retints non-selected.
                                            var stroke = waveformSelected ? theme.waveformActive : theme.waveformDefault
                                            if (!waveformSelected && hoverRole === "primary" && !scrollQuiet)
                                                stroke = theme.textSecondary
                                            else if (!waveformSelected && hoverRole === "neighbour" && !scrollQuiet)
                                                stroke = theme.textMuted
                                            else if (!waveformSelected && (hoverRole === "primary" || hoverRole === "neighbour"))
                                                stroke = theme.waveformDefault
                                            context.strokeStyle = stroke
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
                                    MouseArea {
                                        id: waveformHover
                                        anchors.fill: parent
                                        z: 2
                                        hoverEnabled: true
                                        onEntered: {
                                            contextHintState.reportHover("browser.audition")
                                        }
                                        onExited: {
                                            contextHintState.clearHover("browser.audition")
                                            if (rowSelection.containsMouse)
                                                contextHintState.reportHover("browser.sample_row")
                                        }
                                        onClicked: { browser.forceActiveFocus(); window.interaction.previewRow(index) }
                                    }
                                }
                                Label { id: filenameCell; objectName: "browserFilenameCell"; text: modelData.name; color: theme.textPrimary; font.pixelSize: window.textBody; font.bold: true; elide: Text.ElideRight; Layout.column: browserPane.visibleBrowserColumnIndex("filename"); Layout.fillWidth: true; Layout.minimumWidth: browserPane.browserNarrowColumns ? 96 : 120; verticalAlignment: Text.AlignVCenter }
                                Label { id: bpmCell; objectName: "browserBpmCell"; text: modelData.bpm; color: theme.textSecondary; Layout.column: browserPane.visibleBrowserColumnIndex("bpm"); Layout.preferredWidth: browserPane.effectiveBrowserBpmColumnWidth; horizontalAlignment: Text.AlignRight; verticalAlignment: Text.AlignVCenter; font.pixelSize: window.textMeta }
                                Item {
                                    id: favoriteCell
                                    objectName: "browserFavoriteButton"
                                    Layout.column: browserPane.visibleBrowserColumnIndex("favorite")
                                    Layout.preferredWidth: browserPane.effectiveBrowserFavoriteColumnWidth
                                    Layout.preferredHeight: Math.min(window.densityActionHitTarget, window.densityRowHeight - 2 * window.densityVerticalInset)
                                    Layout.maximumHeight: window.densityRowHeight - 2 * window.densityVerticalInset
                                    Accessible.role: Accessible.Button
                                    Accessible.name: modelData.favorite ? "Remove from Favorites" : "Add to Favorites"
                                    Accessible.onPressAction: favoriteMouseArea.clicked(null)
                                    Label {
                                        anchors.fill: parent
                                        text: modelData.favorite ? "★" : "☆"
                                        color: modelData.favorite ? theme.actionActive : theme.textSecondary
                                        horizontalAlignment: Text.AlignHCenter
                                        verticalAlignment: Text.AlignVCenter
                                        font.pixelSize: window.textMeta
                                    }
                                    MouseArea {
                                        id: favoriteMouseArea
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        onEntered: contextHintState.reportHover("browser.favorite")
                                        onExited: {
                                            contextHintState.clearHover("browser.favorite")
                                            if (rowSelection.containsMouse)
                                                contextHintState.reportHover("browser.sample_row")
                                        }
                                        onClicked: {
                                            browser.forceActiveFocus()
                                            window.interaction.toggleFavorite(index)
                                        }
                                    }
                                }
                                Label { id: keyCell; objectName: "browserKeyCell"; text: modelData.key; color: theme.textSecondary; Layout.column: browserPane.visibleBrowserColumnIndex("key"); Layout.preferredWidth: browserPane.effectiveBrowserKeyColumnWidth; horizontalAlignment: Text.AlignRight; verticalAlignment: Text.AlignVCenter; font.pixelSize: window.textMeta }
                                Label { id: lengthCell; objectName: "browserLengthCell"; text: modelData.duration; color: theme.textSecondary; Layout.column: browserPane.visibleBrowserColumnIndex("length"); Layout.preferredWidth: browserPane.effectiveBrowserLengthColumnWidth; horizontalAlignment: Text.AlignRight; verticalAlignment: Text.AlignVCenter; font.pixelSize: window.textMeta; elide: Text.ElideRight; clip: true }
                                Label { id: typeCell; objectName: "browserTypeCell"; visible: !browserPane.browserNarrowColumns; text: modelData.type; color: theme.textSecondary; font.pixelSize: window.textCaption; elide: Text.ElideRight; Layout.column: browserPane.visibleBrowserColumnIndex("type"); Layout.preferredWidth: browserPane.effectiveBrowserTypeColumnWidth; verticalAlignment: Text.AlignVCenter }
                            }
                            // #846: permanent vertical column dividers removed. Column resize
                            // lives on header overlays; rows keep horizontal chrome only.
                            Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: window.densityDividerHeight; color: theme.dividerDefault; opacity: index === window.screenData.selectedBrowserIndex ? 0.35 : 0.8 }
                        }
                    }
                        Item {
                            id: browserLoopSticky
                            objectName: "browserLoopSticky"
                            width: parent.width
                            height: 44
                            x: 0
                            y: browser.loopStickyEdge === "top" ? 0 : Math.max(0, parent.height - height)
                            z: 22
                            enabled: false
                            visible: window.interaction.browserLoopActive && browser.loopStickyEdge !== "none"
                            Rectangle {
                                anchors.fill: parent
                                color: theme.surfaceRoot
                                opacity: 0.96
                                border.width: 1
                                border.color: theme.selectionBorder
                            }
                            Label {
                                anchors.left: parent.left
                                anchors.leftMargin: 10
                                anchors.verticalCenter: parent.verticalCenter
                                width: Math.min(180, parent.width * 0.28)
                                text: window.interaction.browserLoopOwnerName
                                color: theme.textPrimary
                                font.pixelSize: window.textCaption
                                elide: Text.ElideRight
                            }
                            Label {
                                anchors.left: parent.left
                                anchors.leftMargin: Math.min(196, parent.width * 0.30)
                                anchors.verticalCenter: parent.verticalCenter
                                text: "LOOP"
                                color: theme.actionActive
                                opacity: 0.76
                                font.pixelSize: window.textCaption
                            }
                            Item {
                                id: browserLoopStickyGrid
                                anchors.left: parent.left
                                anchors.leftMargin: Math.min(250, parent.width * 0.38)
                                anchors.right: parent.right
                                anchors.rightMargin: 10
                                anchors.top: parent.top
                                anchors.topMargin: 7
                                anchors.bottom: parent.bottom
                                anchors.bottomMargin: 7
                                Repeater {
                                    model: window.interaction.browserLoopBarPositions
                                    Rectangle {
                                        width: 1
                                        height: browserLoopStickyGrid.height
                                        x: Math.round(Math.max(0, Math.min(1, Number(modelData) || 0)) * Math.max(0, browserLoopStickyGrid.width - width))
                                        color: theme.dividerDefault
                                        opacity: 0.38
                                    }
                                }
                                Rectangle {
                                    width: 2
                                    height: parent.height
                                    color: theme.textPrimary
                                    opacity: 0.82
                                    visible: window.loopPlayheadArmed
                                    x: Math.round(
                                        Math.max(0, Math.min(1, window.interaction.browserLoopProgress))
                                        * Math.max(0, parent.width - width)
                                    )
                                }
                            }
                        }
                        // #1281: short dark edge immersion on sample viewport only (not search/header).
                        // Stacked surfaceRoot bands approximate the MagicPath edge mask (no shader path).
                        Item {
                            id: browserEdgeImmersionTop
                            objectName: "browserEdgeImmersionTop"
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            height: 32
                            z: 20
                            enabled: false
                            Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; height: 10; color: theme.surfaceRoot; opacity: 0.92 }
                            Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.topMargin: 10; height: 10; color: theme.surfaceRoot; opacity: 0.55 }
                            Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.topMargin: 20; height: 12; color: theme.surfaceRoot; opacity: 0.22 }
                        }
                        Item {
                            id: browserEdgeImmersionBottom
                            objectName: "browserEdgeImmersionBottom"
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            height: 32
                            z: 20
                            enabled: false
                            Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.bottomMargin: 20; height: 12; color: theme.surfaceRoot; opacity: 0.22 }
                            Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.bottomMargin: 10; height: 10; color: theme.surfaceRoot; opacity: 0.55 }
                            Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 10; color: theme.surfaceRoot; opacity: 0.92 }
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
                // #1204 OPEN disclosure — Matches collapse toward Browser (Matches ⊂ Browser).
                PanelDisclosureSeam {
                    id: harmonyCollapseHandle
                    objectName: "harmonyCollapseHandle"
                    z: 30
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    seamActive: window.interaction.harmonicMatchOpen && !window.interaction.browserCollapsed
                    accessibleLabel: "Collapse Harmonic Matches"
                    hintId: "panel.harmony.collapse"
                    chevronText: "›"
                    activateAction: function() { window.activateHarmonicMatchToggle() }
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
                        Keys.onEscapePressed: window.interaction.escapeLiveKitContext()
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
                            // #1073: one delivery id per drag (repeated delivery = idempotent).
                            property string internalDeliveryId: ""
                            Drag.active: harmonyRowHover.dragActive
                            Drag.dragType: Drag.Automatic
                            Drag.supportedActions: Qt.CopyAction
                            Drag.keys: window.interaction.internalSampleDragEnabled ? ["application/x-sample-brain-internal-sample"] : []
                            function _freshInternalDescriptor(hi) {
                                return window.interaction.internalSampleDragEnabled ? window.interaction.requestInternalSampleDragDescriptor(hi, "harmony") : ""
                            }
                            Drag.mimeData: window.interaction.internalSampleDragEnabled ? { "application/x-sample-brain-internal-sample": harmonyRow._freshInternalDescriptor(index), "application/x-sample-brain-internal-delivery": harmonyRow.internalDeliveryId } : {}
                            Drag.onDragFinished: harmonyRowHover.dragActive = false
                            MouseArea {
                                id: harmonyRowHover
                                anchors.fill: parent
                                z: 0
                                hoverEnabled: true
                                property bool dragActive: false
                                property real pressX: 0
                                property real pressY: 0
                                onPressed: function(mouse) { dragActive = false; harmonyRow.internalDeliveryId = ""; pressX = mouse.x; pressY = mouse.y }
                                onPositionChanged: function(mouse) {
                                    if (window.interaction.internalSampleDragEnabled && pressed && !dragActive && (Math.abs(mouse.x - pressX) >= 8 || Math.abs(mouse.y - pressY) >= 8)) {
                                        if (harmonyRow.internalDeliveryId.length === 0) harmonyRow.internalDeliveryId = window.interaction.beginInternalSampleDrag()
                                        dragActive = true
                                    }
                                }
                                onClicked: { if (dragActive) return; harmonicMatchList.forceActiveFocus(); window.interaction.selectHarmonyRow(index) }
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
                // Compat objectName: historical harnesses (#845/#908/#954).
                // #1077: classic Live Kit tool only — no Rack/step co-host.
                // #1207: upper-right Kit HUD overlay; height 0 / invisible when closed
                // (zero permanent layout footprint; does not resize Browser).
                objectName: "bottomRackPane"
                readonly property int kitHudMargin: 10
                // Wide enough for #1123 readable cards (min 200) + Replace/Remove row chrome.
                readonly property int kitHudMaxWidth: 440
                x: upperWorkspaceRow.x + browserPane.x
                   + Math.max(0, browserPane.width - width) - kitHudMargin
                y: kitHudMargin
                z: 20
                // Collapse Browser → zero host width; never keep a 240px orphan HUD.
                width: (!window.interaction.browserCollapsed && browserPane.width > 0)
                       ? Math.min(
                             kitHudMaxWidth,
                             Math.max(220, browserPane.width - kitHudMargin * 2)
                         )
                       : 0
                property bool liveKitDrawerOpen: window.interaction.liveKitDrawerOpen
                readonly property bool kitHudExpanded: liveKitDrawerOpen
                        || window.interaction.liveKitPendingAdd !== ""
                // Compat alias — historical tests assert bottomExpanded.
                readonly property bool bottomExpanded: kitHudExpanded
                // #1123/#1207: wrap to fewer columns rather than squeeze slot controls.
                // Assigned slot rows need ~172px for labels + audition + Replace/Remove.
                readonly property int groupCardMinWidth: 200
                readonly property int groupCardSpacing: 8
                readonly property int groupCardWidth: {
                    var avail = Math.max(0, width - 28)
                    var gaps = groupCardSpacing * 3
                    var ideal = (avail - gaps) / 4
                    return Math.max(groupCardMinWidth, Math.min(220, ideal))
                }
                readonly property int groupFlowRows: {
                    var groups = window.screenData.liveKitGroups
                    var avail = Math.max(0, width - 28)
                    var perRow = Math.max(
                        1,
                        Math.floor((avail + groupCardSpacing) / (groupCardWidth + groupCardSpacing))
                    )
                    return Math.max(1, Math.ceil(groups.length / perRow))
                }
                readonly property int expandedSlotCount: {
                    var expandedSlots = 0
                    var groups = window.screenData.liveKitGroups
                    for (var gi = 0; gi < groups.length; gi++) {
                        if (groups[gi].active)
                            expandedSlots += groups[gi].slots.length
                    }
                    return expandedSlots
                }
                readonly property int requestedHeight: 72 + groupFlowRows * 44 + expandedSlotCount * 26
                readonly property int maximumHeight: Math.round(parent.height * 0.45)
                readonly property int autoHeight: Math.min(requestedHeight, maximumHeight)
                readonly property int userHeightPx: window.interaction.liveKitUserHeightPx
                height: kitHudExpanded
                        ? (userHeightPx > 0
                           ? Math.min(Math.max(120, userHeightPx), maximumHeight)
                           : autoHeight)
                        : 0
                radius: 6
                color: theme.surfacePanel
                border.color: theme.borderSubtle
                border.width: kitHudExpanded ? 1 : 0
                // Require materialization so drawer flags alone cannot desync QML
                // from #1070/#1072 after analysis disclosure clears.
                visible: window.activeScreen === "screen1"
                         && window.interaction.hasActiveSource
                         && window.interaction.liveKitRevealed
                         && !window.interaction.browserCollapsed
                         && kitHudExpanded
                // #1207: generation-token transient dismiss — never closes manual mode.
                Timer {
                    id: liveKitTransientTimer
                    objectName: "liveKitTransientTimer"
                    interval: window.interaction.liveKitTransientMs
                    repeat: false
                    running: false
                    property int armedGeneration: -1
                    function armForGeneration(gen) {
                        armedGeneration = gen
                        restart()
                    }
                    onTriggered: {
                        window.interaction.dismissLiveKitTransient(armedGeneration)
                    }
                }
                property int hudGenerationMirror: window.interaction.liveKitHudGeneration
                property string hudModeMirror: window.interaction.liveKitHudMode
                onHudGenerationMirrorChanged: {
                    if (hudModeMirror === "transient")
                        liveKitTransientTimer.armForGeneration(hudGenerationMirror)
                    else
                        liveKitTransientTimer.stop()
                }
                onHudModeMirrorChanged: {
                    if (hudModeMirror === "transient")
                        liveKitTransientTimer.armForGeneration(hudGenerationMirror)
                    else
                        liveKitTransientTimer.stop()
                }
                // Compat objectName: historical Live Kit findChild probes (#845/#895 harnesses).
                // Content lives under liveKitPane so findChild tree walks still resolve slots/headers.
                Item {
                    id: liveKitOverlayDrawer
                    objectName: "liveKitOverlayDrawer"
                    anchors.fill: parent
                    clip: true
                Item {
                    id: liveKitPane
                    objectName: "liveKitPane"
                    anchors.fill: parent
                    visible: parent.visible
                // #1077 optional resize — separate from collapse / docking / sample drag.
                MouseArea {
                    id: liveKitResizeHandle
                    objectName: "liveKitResizeHandle"
                    z: 40
                    height: 6
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    visible: bottomRackPane.kitHudExpanded
                             && window.interaction.liveKitHudMode === "manual"
                    cursorShape: Qt.SizeVerCursor
                    preventStealing: true
                    property real dragStartY: 0
                    property int dragStartHeight: 0
                    onPressed: function(mouse) {
                        dragStartY = mapToItem(null, 0, mouse.y).y
                        dragStartHeight = bottomRackPane.height
                        mouse.accepted = true
                    }
                    onPositionChanged: function(mouse) {
                        if (!pressed)
                            return
                        var globalY = mapToItem(null, 0, mouse.y).y
                        var delta = globalY - dragStartY
                        window.interaction.setLiveKitUserHeightPx(
                            dragStartHeight + delta,
                            bottomRackPane.maximumHeight
                        )
                    }
                    Accessible.name: "Resize Live Kit"
                }
                // #1204: Live Kit is drawer/HUD — no generic horizontal panel disclosure.
                Flickable {
                    id: liveKitDrawerScroll
                    objectName: "liveKitDrawerScroll"
                    anchors.fill: parent
                    clip: true
                    contentWidth: width
                    contentHeight: drawerContent.implicitHeight + 28
                    flickableDirection: Flickable.VerticalFlick
                    boundsBehavior: Flickable.StopAtBounds
                ColumnLayout {
                    id: drawerContent
                    x: 14
                    y: 14
                    width: Math.max(0, parent.width - 28)
                    spacing: 8
                    RowLayout {
                        visible: bottomRackPane.kitHudExpanded
                        Layout.fillWidth: true
                        Label { text: "LIVE KIT"; color: theme.textSecondary; font.pixelSize: 12; Layout.fillWidth: true }
                        Label { text: window.screenData.liveKitAssignedCount + " / " + window.screenData.liveKitTotalSlotCount; color: theme.textSecondary; font.pixelSize: 11 }
                        Button {
                            id: liveKitDrawerHideButton
                            objectName: "liveKitDrawerHideButton"
                            text: "Hide"
                            flat: true
                            implicitHeight: 26
                            padding: 8
                            leftPadding: 10
                            rightPadding: 10
                            Accessible.name: "Hide Live Kit"
                            hoverEnabled: true
                            onHoveredChanged: liveKitDrawerHideButton.hovered
                                ? contextHintState.reportHover("kit.hud.hide")
                                : contextHintState.clearHover("kit.hud.hide")
                            onActiveFocusChanged: activeFocus
                                ? contextHintState.reportFocus("kit.hud.hide")
                                : contextHintState.clearFocus("kit.hud.hide")
                            contentItem: Text {
                                text: liveKitDrawerHideButton.text
                                color: liveKitDrawerHideButton.pressed ? theme.textPrimary
                                       : (liveKitDrawerHideButton.hovered || liveKitDrawerHideButton.activeFocus ? theme.textPrimary : theme.textSecondary)
                                horizontalAlignment: Text.AlignHCenter
                                verticalAlignment: Text.AlignVCenter
                                font.pixelSize: 11
                            }
                            background: Rectangle {
                                implicitHeight: 26
                                radius: 4
                                color: liveKitDrawerHideButton.pressed ? theme.surfaceElevated
                                       : (liveKitDrawerHideButton.hovered ? theme.hoverSurface : "transparent")
                                border.width: 1
                                border.color: liveKitDrawerHideButton.activeFocus ? theme.focusRing
                                              : (liveKitDrawerHideButton.pressed ? theme.interactionPressed : theme.borderSubtle)
                            }
                            onClicked: window.interaction.toggleLiveKitDrawer()
                        }
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
                                                 : (liveKitExportButton.pressed ? theme.interactionPressed : theme.borderSubtle))
                                opacity: liveKitExportButton.enabled ? 1.0 : 0.4
                            }
                            onClicked: exportKitDialog.open()
                        }
                    }
                    Label {
                        id: liveKitExportStatus
                        objectName: "liveKitExportStatus"
                        visible: bottomRackPane.kitHudExpanded
                                 && window.interaction.liveKitExportStatus.length > 0
                        Layout.fillWidth: true
                        text: window.interaction.liveKitExportStatus
                        color: window.interaction.liveKitExportOk ? theme.textSecondary : theme.statusError
                        font.pixelSize: 11
                        wrapMode: Text.Wrap
                    }
                    Label {
                        id: liveKitHudFeedback
                        objectName: "liveKitHudFeedback"
                        visible: bottomRackPane.kitHudExpanded
                                 && window.interaction.liveKitLastFeedbackSample.length > 0
                                 && window.interaction.liveKitPendingAdd === ""
                        Layout.fillWidth: true
                        text: {
                            var mut = window.interaction.liveKitLastFeedbackMutation
                            var sample = window.interaction.liveKitLastFeedbackSample
                            var group = window.interaction.liveKitLastFeedbackGroup
                            var slot = window.interaction.liveKitLastFeedbackSlot
                            var verb = mut === "replace" ? "Replaced" : (mut === "remove" ? "Removed" : "Added")
                            var target = (group.length > 0 && slot.length > 0) ? (group + " · " + slot) : ""
                            return target.length > 0 ? (verb + " " + sample + " → " + target) : (verb + " " + sample)
                        }
                        color: theme.textSecondary
                        font.pixelSize: 11
                        elide: Text.ElideRight
                    }
                    Rectangle {
                        id: liveKitPendingBanner
                        objectName: "liveKitPendingBanner"
                        visible: bottomRackPane.kitHudExpanded
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
                    Flow {
                        // #1123: top-level kit groups as compact horizontal cards (wrap).
                        // #1077: classic kit slots while Live Kit is visible; closed height 0.
                        id: liveKitGroupsFlow
                        objectName: "liveKitGroupsFlow"
                        visible: bottomRackPane.bottomExpanded
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignTop
                        spacing: bottomRackPane.groupCardSpacing
                        width: Math.max(0, parent.width)
                        Repeater { model: window.screenData.liveKitGroups
                            // Calm dark compact card; Blood-A accent only when active/selected.
                            delegate: Rectangle {
                                property int kitGroupIndex: index
                                property bool groupHovered: liveKitGroupHeader.containsMouse
                                width: bottomRackPane.groupCardWidth
                                height: 40 + (modelData.active ? modelData.slots.length * 26 + 10 : 0)
                                radius: 4
                                color: modelData.active ? theme.hoverSurface
                                       : (groupHovered ? theme.hoverSurface : "transparent")
                                opacity: modelData.active ? 1.0 : 0.92
                                border.width: (modelData.active || groupHovered) ? 1 : 0
                                border.color: modelData.active ? theme.actionActive
                                              : theme.borderSubtle
                                ColumnLayout { anchors.fill: parent; anchors.margins: 0; spacing: 0
                                    Item { Layout.fillWidth: true; Layout.preferredHeight: 40; Layout.leftMargin: 10; Layout.rightMargin: 8
                                        RowLayout { anchors.fill: parent; spacing: 4
                                            Label { text: modelData.displayName; color: theme.textPrimary; font.pixelSize: 12; font.bold: modelData.active; elide: Text.ElideRight; Layout.fillWidth: true }
                                            Label { text: modelData.active ? "▾" : "▸"; color: modelData.active ? theme.actionActive : theme.textSecondary; font.pixelSize: 11; opacity: 0.85 }
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
                                ColumnLayout { visible: modelData.active; Layout.fillWidth: true; Layout.leftMargin: 8; Layout.rightMargin: 8; Layout.topMargin: 0; Layout.bottomMargin: 6
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
                                            property bool showRemoveAffordance: modelData.assigned && !hasPendingAdd
                                            property bool showAddAffordance: !modelData.assigned || hasPendingAdd
                                            // #1073: visible Live Kit slot accepts the internal Sample
                                            // MIME only; Python owns eligibility, Add/Replace, replay.
                                            DropArea {
                                                objectName: "internalSampleDropArea" + kitGroupIndex + "_" + index
                                                anchors.fill: parent
                                                z: 2
                                                enabled: window.interaction.internalSampleDragEnabled
                                                keys: ["application/x-sample-brain-internal-sample", "application/x-sample-brain-internal-delivery"]
                                                onEntered: function(drag) { drag.accept(Qt.CopyAction) }
                                                onDropped: function(drop) {
                                                    var descriptor = drop.getDataAsString("application/x-sample-brain-internal-sample")
                                                    var deliveryId = drop.getDataAsString("application/x-sample-brain-internal-delivery")
                                                    window.interaction.applyInternalSampleDropAtSlot(kitGroupIndex, index, descriptor, deliveryId)
                                                }
                                            }
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
                                            RowLayout { anchors.fill: parent; spacing: 4
                                                Item { Layout.preferredWidth: 12; Layout.preferredHeight: 26
                                                    Label {
                                                        anchors.centerIn: parent
                                                        text: modelData.assigned ? "▶" : ""
                                                        color: slotAuditionMouse.containsMouse && window.interaction.liveKitPendingAdd === "" ? theme.actionActive : (modelData.auditioning ? theme.actionActive : theme.textSecondary)
                                                        font.pixelSize: 10
                                                    }
                                                }
                                                Label { text: modelData.displayName; color: theme.textSecondary; font.pixelSize: 11; Layout.fillWidth: true; Layout.minimumWidth: 48; elide: Text.ElideRight }
                                                Label { text: modelData.assignment; color: modelData.auditioning ? theme.actionActive : (modelData.assigned ? theme.textPrimary : theme.textSecondary); font.pixelSize: 10; Layout.fillWidth: true; Layout.minimumWidth: 40; elide: Text.ElideRight }
                                                Rectangle {
                                                    // #895: quieter slot affordance — fine border, accent only when pending/active.
                                                    id: slotAction
                                                    Layout.preferredHeight: 20
                                                    radius: 3
                                                    Layout.preferredWidth: showReplaceAffordance ? 36 : 20
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
                                                        font.pixelSize: showReplaceAffordance ? 13 : 12
                                                    }
                                                }
                                                Rectangle {
                                                    id: slotRemoveAction
                                                    objectName: "slotRemoveAction" + kitGroupIndex + "_" + index
                                                    Layout.preferredHeight: 20
                                                    Layout.preferredWidth: 20
                                                    radius: 3
                                                    visible: showRemoveAffordance
                                                    color: slotRemoveMouse.containsMouse ? theme.hoverSurface : "transparent"
                                                    border.width: slotRemoveMouse.containsMouse ? 1 : 0
                                                    border.color: theme.borderSubtle
                                                    Label {
                                                        anchors.centerIn: parent
                                                        text: "×"
                                                        color: slotRemoveMouse.containsMouse ? theme.textPrimary : theme.textSecondary
                                                        font.pixelSize: 12
                                                    }
                                                    MouseArea {
                                                        id: slotRemoveMouse
                                                        anchors.fill: parent
                                                        hoverEnabled: true
                                                        z: 1
                                                        onClicked: window.interaction.removeLiveKitSlot(kitGroupIndex, index)
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
                }
                }
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

    // #725/#742 Library reveal — overlay, not a workspaceRow child.
    // Same #1204 hairline disclosure style; reveal state authority stays #725.
    PanelDisclosureSeam {
        id: libraryRevealAffordance
        objectName: "libraryRevealAffordance"
        z: 20
        anchors.left: parent.left
        anchors.top: workspaceRow.top
        anchors.bottom: workspaceRow.bottom
        seamActive: window.activeScreen === "screen1" && !window.interaction.libraryRevealed
        accessibleLabel: "Reveal Library"
        hintId: "panel.library.reveal"
        chevronText: "›"
        activateAction: function() { window.interaction.revealLibrary() }
    }

    // #1204 COLLAPSED reopen — quiet hairline at Library trailing / residual boundary.
    PanelDisclosureSeam {
        id: browserCollapseAffordance
        objectName: "browserCollapseAffordance"
        z: 21
        x: workspaceRow.x + Math.max(0, layoutModel.libraryWidth - width)
        y: workspaceRow.y
        height: workspaceRow.height
        seamActive: window.activeScreen === "screen1"
                    && window.interaction.hasActiveSource
                    && window.interaction.browserCollapsed
        accessibleLabel: "Expand Browser"
        hintId: "panel.browser.expand"
        chevronText: "›"
        activateAction: function() { window.interaction.toggleBrowserCollapsed() }
    }

    PanelDisclosureSeam {
        id: harmonyCollapseAffordance
        objectName: "harmonyCollapseAffordance"
        z: 21
        // Only while Browser is OPEN — never create Browser COLLAPSED + Matches OPEN.
        x: workspaceRow.x + layoutModel.libraryWidth
           + ((window.interaction.libraryRevealed && layoutModel.libraryWidth > 0
               && !window.interaction.browserCollapsed)
              ? layoutModel.handleWidth : 0)
           + layoutModel.browserWidth - width
        y: workspaceRow.y
        height: workspaceRow.height
        seamActive: window.activeScreen === "screen1"
                    && window.interaction.hasActiveSource
                    && !window.interaction.browserCollapsed
                    && !window.interaction.harmonicMatchOpen
        accessibleLabel: "Expand Harmonic Matches"
        hintId: "panel.harmony.expand"
        chevronText: "›"
        activateAction: function() { window.activateHarmonicMatchToggle() }
    }

    // #1077/#1207: workspace-scoped Kit HUD reopen — kit tool, not upper mode nav.
        ToolButton {
            id: editLiveKitRevealControl
            objectName: "editLiveKitRevealControl"
            z: 22
            text: "Kit " + window.screenData.liveKitAssignedCount + "/" + window.screenData.liveKitTotalSlotCount
            Accessible.name: "Reveal Live Kit tool"
            flat: true
            font.pixelSize: 11
            padding: 6
            leftPadding: 10
            rightPadding: 10
            // Summon only on Screen-1 while the HUD is currently hidden and
            // may be shown via the presentation owner (not first materialization).
        readonly property bool canReveal: window.interaction.liveKitRevealed
                || window.screenData.liveKitAssignedCount > 0
        visible: window.activeScreen === "screen1"
                 && window.interaction.hasActiveSource
                 && window.interaction.browserMaterialized
                 && canReveal
                 && !window.interaction.browserCollapsed
                 && !window.interaction.liveKitDrawerOpen
                 && window.interaction.liveKitPendingAdd === ""
        enabled: visible
        anchors.right: workspaceRow.right
        anchors.top: workspaceRow.top
        anchors.rightMargin: 12
        anchors.topMargin: 10
        implicitHeight: 28
        background: Rectangle {
            implicitHeight: 28
            radius: 3
            color: theme.surfaceElevated
            opacity: editLiveKitRevealControl.hovered || editLiveKitRevealControl.activeFocus ? 0.95 : 0.82
            border.width: editLiveKitRevealControl.activeFocus ? 1 : 0
            border.color: theme.selectionBorder
        }
        contentItem: Text {
            text: editLiveKitRevealControl.text
            font: editLiveKitRevealControl.font
            color: theme.textSecondary
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            opacity: 0.9
        }
        hoverEnabled: true
        onHoveredChanged: editLiveKitRevealControl.hovered
            ? contextHintState.reportHover("kit.hud.reveal")
            : contextHintState.clearHover("kit.hud.reveal")
        onActiveFocusChanged: activeFocus
            ? contextHintState.reportFocus("kit.hud.reveal")
            : contextHintState.clearFocus("kit.hud.reveal")
        onClicked: window.interaction.toggleLiveKitDrawer()
    }

    // #1080 Slice A: gated Arrangement shell — read-only projection surface.
    // The scene exists only while the #1078 state owner reports "ARRANGEMENT";
    // a disabled feature gate can never materialize an Arrangement scene.
    // Step Sequencer is part of Arrangement (no separate top-level mode); QML
    // owns projection/presentation only — no Pattern truth copy in this stage.
    Loader {
        id: arrangementStageLoader
        objectName: "arrangementStageLoader"
        anchors.fill: parent
        z: 60
        active: window.arrangement.projectionMode === "ARRANGEMENT"
        onLoaded: item.forceActiveFocus()
        // Deterministic Browser focus restoration on every deactivation path.
        onActiveChanged: {
            if (!active && window.activeScreen === "screen1")
                browser.forceActiveFocus()
        }
        sourceComponent: arrangementStageComponent
    }

    Component {
        id: arrangementStageComponent

        Item {
            id: arrangementStage
            objectName: "arrangementStage"
            anchors.fill: parent
            // #1080 Slice B: fixed channel-name column so every sequencer
            // row's 32-field grid aligns on one precise device geometry.
            readonly property int channelNameColumnWidth: 96
            // C2b: indent for track rows under parent group
            readonly property int trackRowIndent: 24

            // #1080: this input layer keeps pointer events that miss the
            // sequencer's field hit targets from reaching the workspace
            // beneath the stage (no invisible mutation or audition). The
            // Slice B field cells sit above it and own the only stage click
            // intent; this blocker itself carries no command.
            MouseArea {
                anchors.fill: parent
                acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
                // C2c1: Ctrl + Mouse Wheel = zoom; Wheel without Ctrl = no-op.
                // Horizontal wheel (no Ctrl) = pan.
                onWheel: {
                    if (wheel.modifiers & Qt.ControlModifier) {
                        if (wheel.angleDelta.y < 0)
                            window.arrangement.zoomOut()
else
                            window.arrangement.zoomIn()
                        wheel.accepted = true
                    } else if (Math.abs(wheel.angleDelta.x) > 0) {
                        window.arrangement.panHorizontal(-wheel.angleDelta.x)
                        wheel.accepted = true
                    }
                }
            }

            // Direction B (#1079): subtle 2.5D black stage — solid surface
            // hierarchy and hairlines from Theme Authority tokens only.
            Rectangle {
                anchors.fill: parent
                color: theme.surfaceRoot
            }

            // Upper song/Arrangement stage: quiet before the first active
            // Step; a single action hairline once any canonical Step is set.
            Rectangle {
                id: arrangementUpperStage
                objectName: "arrangementUpperStage"
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.bottom: arrangementSequencer.top
                anchors.bottomMargin: 12
                color: theme.surfacePanel
                border.width: 1
                border.color: window.arrangement.anyActiveStep
                               ? theme.actionActive : theme.borderSubtle
                // C2c1: Timeline viewport — horizontal scale with block alignment,
                // subtle bar/block seams. Pure presentation, no musical truth.
                Item {
                    id: timelineViewport
                    objectName: "timelineViewport"
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    height: 40

                    // Horizontal time scale line
                    Rectangle {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        height: 1
                        color: theme.borderSubtle
                    }

                    // Block position markers — derived from viewport block range
                    Repeater {
                        model: window.arrangement.groupRows.length > 0
                            ? window.arrangement.groupRows[0].blocks : []
                        Rectangle {
                            x: (modelData.blockIndex * window.arrangement.arrangementBlockLengthQn - window.arrangement.viewportStartQn) * (timelineViewport.width / window.arrangement.viewportVisibleQn)
                            width: window.arrangement.arrangementBlockLengthQn * (timelineViewport.width / window.arrangement.viewportVisibleQn)
                            height: 24
                            color: "transparent"
                            border.width: 1
                            border.color: theme.borderSubtle
                            opacity: 0.15
                            Label {
                                anchors.centerIn: parent
                                text: modelData.blockIndex
                                color: theme.textSecondary
                                font.pixelSize: 9
                                opacity: 0.6
                            }
                        }
                    }
                    // Marker geometry follows Direction B bridge bindings (C2c1 review F4).
                }

                Column {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 36
                    spacing: 2
                    Repeater {
                        model: window.arrangement.groupRows
                        Item {
                            id: arrangementGroupRow
                            objectName: "arrangementGroupRow"
                            readonly property var row: modelData
                            readonly property string groupId: row.groupId
                            readonly property bool expanded: row.expanded
                            width: parent.width
                            // Height depends on expansion: collapsed=64, expanded=64 + trackRows *48
                            height: expanded ? (64 + (row.trackRows ? row.trackRows.length : 0) *48) : 64

                            // Parent group header
                            Rectangle {
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                height: 64
                                color: theme.surfacePanel
                                border.width: 1
                                border.color: theme.borderSubtle
                                Row {
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.leftMargin: 14
                                    anchors.rightMargin: 14
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 8

                                    // Expand/collapse affordance
                                    Rectangle {
                                        id: expandControl
                                        objectName: "arrangementExpandControl"
                                        width: 24
                                        height: 24
                                        radius: 2
                                        color: theme.surfaceElevated
                                        border.width: 1
                                        border.color: theme.borderSubtle
                                        activeFocusOnTab: true
                                        Accessible.role: Accessible.Button
                                        Accessible.name: expanded ? "Collapse " + arrangementGroupRow.row.displayName : "Expand " + arrangementGroupRow.row.displayName
                                        Accessible.description: "Toggle group visibility"
                                        Accessible.onPressAction: {
                                            window.arrangement.toggleArrangementGroupExpanded(arrangementGroupRow.groupId)
                                        }
                                        Keys.onSpacePressed: function(event) {
                                            window.arrangement.toggleArrangementGroupExpanded(arrangementGroupRow.groupId)
                                            event.accepted = true
                                        }
                                        // Chevron indicator
                                        Canvas {
                                            anchors.centerIn: parent
                                            width: 12
                                            height: 12
                                            onPaint: {
                                                var ctx = getContext("2d")
                                                ctx.strokeStyle = theme.textPrimary
                                                ctx.lineWidth = 2
                                                ctx.beginPath()
                                                if (expanded) {
                                                    // Up chevron
                                                    ctx.moveTo(2, 8)
                                                    ctx.lineTo(6, 4)
                                                    ctx.lineTo(10, 8)
                                                } else {
                                                    // Down chevron
                                                    ctx.moveTo(2, 4)
                                                    ctx.lineTo(6, 8)
                                                    ctx.lineTo(10, 4)
                                                }
                                                ctx.stroke()
                                            }
                                        }
                                        MouseArea {
                                            anchors.fill: parent
                                            acceptedButtons: Qt.LeftButton
                                            onClicked: window.arrangement.toggleArrangementGroupExpanded(arrangementGroupRow.groupId)
                                        }
                                    }

                                    Label {
                                        anchors.verticalCenter: parent.verticalCenter
                                        width: 160
                                        text: arrangementGroupRow.row.displayName
                                        color: theme.textSecondary
                                        font.pixelSize: 12
                                        elide: Text.ElideRight
                                    }
                                    Row {
                                        anchors.left: expandControl.right
                                        anchors.leftMargin: 8
                                        anchors.right: parent.right
                                        anchors.rightMargin: 14
                                        anchors.verticalCenter: parent.verticalCenter
                                        spacing: 8
                                        Repeater {
                                            model: arrangementGroupRow.row.blocks
                                            Rectangle {
                                                id: arrangementGroupBlock
                                                objectName: "arrangementGroupBlock"
                                                readonly property var cell: modelData
                                                readonly property string groupId: arrangementGroupRow.groupId
                                                readonly property int blockIndex: cell.blockIndex
                                                readonly property bool effectiveOn: cell.available
                                                enabled: cell.interactive
                                                width: (parent.width - 8 * (arrangementGroupRow.row.blocks.length - 1)) / arrangementGroupRow.row.blocks.length
                                                height: 42
                                                color: effectiveOn ? theme.surfaceElevated : theme.surfaceRoot
                                                border.width: activeFocus ? 2 : 1
                                                border.color: activeFocus ? theme.actionActive : theme.borderSubtle
                                                activeFocusOnTab: cell.interactive
                                                Accessible.role: Accessible.Button
                                                Accessible.name: arrangementGroupRow.row.displayName + " · " + blockIndex + " · " + blockState.text
                                                Accessible.description: "16 bars"
                                                Accessible.onPressAction: {
                                                    if (cell.interactive)
                                                        window.arrangement.toggleArrangementGroupBlock(arrangementGroupRow.groupId, arrangementGroupBlock.blockIndex)
                                                }
                                                Keys.onSpacePressed: function(event) {
                                                    if (cell.interactive) {
                                                        window.arrangement.toggleArrangementGroupBlock(arrangementGroupRow.groupId, arrangementGroupBlock.blockIndex)
                                                        event.accepted = true
                                                    }
                                                }
                                                Label {
                                                    id: blockState
                                                    anchors.centerIn: parent
                                                    text: cell.status !== "eligible" ? "—"
                                                          : !cell.blockEnabled ? "GLOBAL OFF"
                                                          : cell.groupEnabled ? "ON" : "OFF"
                                                    color: effectiveOn ? theme.textPrimary : theme.textSecondary
                                                    font.pixelSize: 10
                                                }
                                                MouseArea {
                                                    anchors.fill: parent
                                                    enabled: arrangementGroupBlock.cell.interactive
                                                    acceptedButtons: Qt.LeftButton
                                                    onClicked: window.arrangement.toggleArrangementGroupBlock(arrangementGroupRow.groupId, arrangementGroupBlock.blockIndex)
                                                }
                                            }
                                        }
                                    }
                                }
                            }

                            // C2b: Track rows for expanded group
                            Item {
                                id: arrangementTrackRows
                                anchors.left: parent.left
                                anchors.leftMargin: arrangementStage.trackRowIndent
                                anchors.right: parent.right
                                anchors.rightMargin: 14
                                anchors.top: parent.top
                                anchors.topMargin: 64
                                height: expanded ? (row.trackRows ? row.trackRows.length : 0) *48 : 0
                                visible: expanded && row.trackRows && row.trackRows.length > 0
                                Column {
                                    spacing: 4
                                    Repeater {
                                        model: expanded ? (row.trackRows || []) : []
                                        Item {
                                            id: arrangementTrackRow
                                            objectName: "arrangementTrackRow"
                                            readonly property var track: modelData
                                            readonly property string channelId: track.channelId
                                            width: parent.width
                                            height: 48

                                            Row {
                                                id: arrangementTrackRowLayout
                                                anchors.fill: parent
                                                spacing: 8

                                                Label {
                                                    objectName: "arrangementTrackRowName"
                                                    anchors.verticalCenter: parent.verticalCenter
                                                    text: track.displayName
                                                    color: theme.textSecondary
                                                    font.pixelSize: 10
                                                    width: arrangementStage.channelNameColumnWidth - arrangementStage.trackRowIndent
                                                    horizontalAlignment: Text.AlignRight
                                                    elide: Text.ElideRight
                                                    opacity: 0.8
                                                }

                                                Row {
                                                    id: arrangementTrackBlocksRow
                                                    anchors.left: parent.left
                                                    anchors.right: parent.right
                                                    spacing: 8
                                                    Repeater {
                                                        model: track.blocks
                                                        Rectangle {
                                                            id: arrangementTrackBlock
                                                            objectName: "arrangementTrackBlock"
                                                            readonly property var cell: modelData
                                                            readonly property string channelId: arrangementTrackRow.channelId
                                                            readonly property int blockIndex: cell.blockIndex
                                                            readonly property bool effectiveOn: cell.available && cell.effective === true
                                                            enabled: cell.interactive
                                                            width: (parent.width - 8 * (track.blocks.length - 1)) / track.blocks.length
                                                            height: 36
                                                            color: effectiveOn ? theme.surfaceElevated : theme.surfaceRoot
                                                            border.width: activeFocus ? 2 : 1
                                                            border.color: activeFocus ? theme.actionActive : (cell.effective === "unresolved" ? theme.dividerDefault : theme.borderSubtle)
                                                            radius: 2
                                                            activeFocusOnTab: cell.interactive
                                                            Accessible.role: Accessible.Button
                                                            Accessible.name: track.displayName + " · " + blockIndex + " · " + trackBlockState.text
                                                            Accessible.description: "Track block"
                                                            Accessible.onPressAction: {
                                                                if (cell.interactive)
                                                                    window.arrangement.toggleArrangementTrackBlock(arrangementTrackRow.channelId, arrangementTrackBlock.blockIndex)
                                                            }
                                                            Keys.onSpacePressed: function(event) {
                                                                if (cell.interactive) {
                                                                    window.arrangement.toggleArrangementTrackBlock(arrangementTrackRow.channelId, arrangementTrackBlock.blockIndex)
                                                                    event.accepted = true
                                                                }
                                                            }
                                                            Label {
                                                                id: trackBlockState
                                                                anchors.centerIn: parent
                                                                text: cell.effective === "unresolved" ? "?"
                                                                      : cell.effective === "out_of_current_horizon" ? "—"
                                                                      : !cell.blockEnabled ? "GLOBAL OFF"
                                                                      : cell.groupEnabled ? (cell.trackEnabled ? "ON" : "OFF") : "GROUP OFF"
                                                                color: effectiveOn ? theme.textPrimary : theme.textDisabled
                                                                font.pixelSize: 9
                                                            }
                                                            MouseArea {
                                                                anchors.fill: parent
                                                                enabled: arrangementTrackBlock.cell.interactive
                                                                acceptedButtons: Qt.LeftButton
                                                                onClicked: window.arrangement.toggleArrangementTrackBlock(arrangementTrackRow.channelId, arrangementTrackBlock.blockIndex)
                                                            }
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // Bottom-center primary sequencer: exactly 32 fields across 8
            // bars, four fields per bar (#1083/#1086). The aggregate row is
            // the unchanged Slice A read-only cycle projection; below it the
            // Slice B channel rows project each channel's own 32 fields.
            // Only Python-authority one-shot rows carry click hit targets.
            Item {
                id: arrangementSequencer
                objectName: "arrangementSequencer"
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 14
                width: arrangementSequencerLayout.implicitWidth
                height: arrangementSequencerLayout.implicitHeight

                Column {
                    id: arrangementSequencerLayout
                    spacing: 5

                    // Aggregate cycle row — unchanged read-only geometry,
                    // indented by the name column so its 8×4 grid aligns
                    // exactly with the channel rows' grids below.
                    Row {
                        id: arrangementSequencerRow
                        spacing: 8

                        Item {
                            width: arrangementStage.channelNameColumnWidth
                            height: 1
                        }

                        Row {
                            id: arrangementSequencerBars
                            spacing: 10

                            Repeater {
                                model: window.arrangement.bars

                                Item {
                                    id: arrangementBar
                                    objectName: "arrangementBar"
                                    readonly property var bar: modelData
                                    width: arrangementBarRow.implicitWidth
                                    height: arrangementBarRow.implicitHeight

                                    Row {
                                        id: arrangementBarRow
                                        spacing: 3

                                        Repeater {
                                            model: arrangementBar.bar.fields

                                            Rectangle {
                                                id: arrangementField
                                                objectName: "arrangementField"
                                                width: 18
                                                height: 18
                                                radius: 2
                                                color: modelData.active
                                                       ? theme.selectionSurface
                                                       : theme.surfaceElevated
                                                border.width: 1
                                                border.color: modelData.active
                                                              ? theme.selectionBorder
                                                              : theme.borderSubtle
                                                opacity: modelData.active ? 1.0 : 0.85
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // #1080 Slice B: channel-aware rows. Each row projects
                    // one channel's 32 fields; only rows the Python
                    // projection marked point-trigger-safe offer the click
                    // intent. Loop/ambiguous channels stay visible identity
                    // rows without editable trigger cells.
                    Repeater {
                        model: window.arrangement.channelRows

                        Item {
                            id: arrangementChannelRow
                            objectName: "arrangementChannelRow"
                            readonly property var row: modelData
                            readonly property string channelId: modelData.channelId
                            readonly property bool stepGridEnabled: modelData.stepGridEnabled
                            width: arrangementChannelRowLayout.implicitWidth
                            height: arrangementChannelRowLayout.implicitHeight

                            Row {
                                id: arrangementChannelRowLayout
                                spacing: 8

                                Label {
                                    objectName: "arrangementChannelRowName"
                                    text: arrangementChannelRow.row.displayName
                                    color: arrangementChannelRow.stepGridEnabled
                                           ? theme.textPrimary
                                           : theme.textSecondary
                                    font.pixelSize: 10
                                    width: arrangementStage.channelNameColumnWidth
                                    horizontalAlignment: Text.AlignRight
                                    elide: Text.ElideRight
                                    anchors.verticalCenter: parent.verticalCenter
                                    opacity: arrangementChannelRow.stepGridEnabled ? 0.9 : 0.6
                                }

                                Row {
                                    id: arrangementChannelFieldsRow
                                    spacing: 10

                                    Repeater {
                                        model: arrangementChannelRow.row.bars

                                        Item {
                                            id: arrangementChannelBar
                                            objectName: "arrangementChannelBar"
                                            readonly property var bar: modelData
                                            width: arrangementChannelBarRow.implicitWidth
                                            height: arrangementChannelBarRow.implicitHeight

                                            Row {
                                                id: arrangementChannelBarRow
                                                spacing: 3

                                                Repeater {
                                                    model: arrangementChannelBar.bar.fields

                                                    Rectangle {
                                                        id: arrangementChannelField
                                                        objectName: "arrangementChannelField"
                                                        readonly property var fieldCell: modelData
                                                        readonly property int fieldIndex: modelData.index
                                                        width: 18
                                                        height: 18
                                                        // Active state is form + contrast
                                                        // plus restrained accent — never
                                                        // color alone: square active cells,
                                                        // rounded quiet ones.
                                                        radius: fieldCell.active ? 0 : 2
                                                        color: fieldCell.active
                                                               ? theme.selectionSurface
                                                               : (arrangementChannelRow.stepGridEnabled
                                                                  ? theme.surfaceElevated
                                                                  : theme.surfacePanel)
                                                        border.width: fieldCell.active ? 1 : (arrangementChannelRow.stepGridEnabled ? 1 : 0)
                                                        border.color: fieldCell.active
                                                                      ? theme.selectionBorder
                                                                      : (arrangementChannelRow.stepGridEnabled
                                                                         ? theme.borderSubtle
                                                                         : theme.dividerDefault)
                                                        opacity: fieldCell.active ? 1.0 : (arrangementChannelRow.stepGridEnabled ? 0.9 : 0.45)

                                                        // One click = one intent to the Python
                                                        // seam; QML owns no quarter-note math
                                                        // and no local pattern truth.
                                                        MouseArea {
                                                            anchors.fill: parent
                                                            enabled: arrangementChannelRow.stepGridEnabled
                                                            acceptedButtons: Qt.LeftButton
                                                            onClicked: window.arrangement.toggleArrangementField(arrangementChannelRow.channelId, arrangementChannelField.fieldIndex)
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                // C2c2: Python-owned end-marker projection. The marker reads
                // a normalized position from the bridge; QML owns no musical
                // truth and renders dimmed unless projection says eligible.
                Item {
                    id: arrangementEndMarker
                    objectName: "arrangementEndMarker"
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    x: window.arrangement.endMarkerNormalizedPosition * parent.width
                    width: 2
                    visible: window.arrangement.endMarkerVisible
                    opacity: window.arrangement.endMarkerRenderEligible ? 1.0 : 0.4

                    Rectangle {
                        anchors.fill: parent
                        color: theme.actionActive
                        opacity: 0.35
                    }

                    Rectangle {
                        id: arrangementEndMarkerHandle
                        objectName: "arrangementEndMarkerHandle"
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.top: parent.top
                        width: 10
                        height: 10
                        radius: 2
                        color: theme.actionActive
                        Accessible.role: Accessible.Indicator
                        Accessible.name: "endMarker END"
                    }

                    Label {
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.top: parent.top
                        anchors.topMargin: 12
                        text: "END"
                        color: theme.textSecondary
                        font.pixelSize: 8
                    }
                }
            }

            // Stage chrome: Arrangement identity and active track identity.
            // The clear return lives in the Browser nav route through the
            // same #1078 state owner — the stage itself stays a fully
            // non-interactive read-only projection.
            Row {
                id: arrangementStageHeader
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.margins: 10
                spacing: 8

                Label {
                    text: "Arrangement"
                    color: theme.textSecondary
                    font.pixelSize: 10
                    anchors.verticalCenter: parent.verticalCenter
                    opacity: 0.85
                }
                Label {
                    objectName: "arrangementTrackIdentity"
                    text: window.arrangement.activeTrackId
                    visible: window.arrangement.activeTrackId.length > 0
                    color: theme.textSecondary
                    font.pixelSize: 10
                    anchors.verticalCenter: parent.verticalCenter
                    opacity: 0.7
                }
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
    tempo_map_provider: Callable[[], object] | None = None,
    on_tempo_map_replaced: Callable[[], None] | None = None,
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
            self._browser_loop_snapshot = adapter.browser_loop_projection_snapshot()
            # C2c1 review F3: observe tempo-map replacement from the layout side.
            self._tempo_map = tempo_map_provider() if tempo_map_provider is not None else None

        def _emit_sample_context_closed(self) -> None:
            self.sampleContextClosed.emit()

        def _refresh(self) -> None:
            adapter.sync_visible_state_labels()
            self._browser_loop_snapshot = adapter.refresh_browser_loop_projection()
            if on_state_changed is not None:
                on_state_changed()
            if tempo_map_provider is not None:
                tempo_map = tempo_map_provider()
                if tempo_map is not self._tempo_map:
                    self._tempo_map = tempo_map
                    if on_tempo_map_replaced is not None:
                        on_tempo_map_replaced()
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
        def liveKitDrawerOpen(self) -> bool:
            return adapter.live_kit_drawer_open

        @Property(str, notify=state_changed)
        def liveKitHudMode(self) -> str:
            return adapter.live_kit_hud_mode

        @Property(int, notify=state_changed)
        def liveKitHudGeneration(self) -> int:
            return int(adapter.live_kit_hud_generation)

        @Property(int, notify=state_changed)
        def liveKitTransientMs(self) -> int:
            return int(adapter.live_kit_transient_ms)

        @Property(str, notify=state_changed)
        def liveKitLastFeedbackSample(self) -> str:
            return adapter.live_kit_last_feedback_sample

        @Property(str, notify=state_changed)
        def liveKitLastFeedbackGroup(self) -> str:
            return adapter.live_kit_last_feedback_group

        @Property(str, notify=state_changed)
        def liveKitLastFeedbackSlot(self) -> str:
            return adapter.live_kit_last_feedback_slot

        @Property(str, notify=state_changed)
        def liveKitLastFeedbackMutation(self) -> str:
            return adapter.live_kit_last_feedback_mutation

        @Slot(int, result=bool)
        def dismissLiveKitTransient(self, generation: int) -> bool:
            closed = adapter.dismiss_live_kit_transient(int(generation))
            if closed:
                self._refresh()
            return bool(closed)

        @Property(int, notify=state_changed)
        def liveKitUserHeightPx(self) -> int:
            return int(adapter.live_kit_user_height_px)

        @Slot(int, int)
        def setLiveKitUserHeightPx(self, height_px: int, max_px: int = 0) -> None:
            adapter.set_live_kit_user_height_px(int(height_px), max_px=int(max_px))
            self._refresh()

        @Property(bool, notify=state_changed)
        def liveKitAutoDisclosureConsumed(self) -> bool:
            return adapter.live_kit_auto_disclosure_consumed

        @Property(bool, notify=state_changed)
        def hasActiveSource(self) -> bool:
            return adapter.view_model.has_active_source

        @Property(bool, notify=state_changed)
        def browserMaterialized(self) -> bool:
            """#1213 readiness projection: Wave-1 Browser usable → workspace chrome."""
            return bool(adapter.view_model.browser_materialized)

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

        @Property(bool, notify=state_changed)
        def browserLoopActive(self) -> bool:
            return bool(self._browser_loop_snapshot.active)

        @Property(str, notify=state_changed)
        def browserLoopOwnerPath(self) -> str:
            return self._browser_loop_snapshot.owner_path

        @Property(str, notify=state_changed)
        def browserLoopOwnerName(self) -> str:
            return self._browser_loop_snapshot.owner_name

        @Property(float, notify=state_changed)
        def browserLoopProgress(self) -> float:
            return float(self._browser_loop_snapshot.progress)

        @Property(int, notify=state_changed)
        def browserLoopBarCount(self) -> int:
            return int(self._browser_loop_snapshot.bar_count)

        @Property(list, notify=state_changed)
        def browserLoopBarPositions(self) -> list[float]:
            return list(self._browser_loop_snapshot.bar_positions)

        @Property(str, notify=state_changed)
        def browserLoopReducedCapabilityReason(self) -> str:
            return self._browser_loop_snapshot.reduced_capability_reason

        @Property(bool, notify=state_changed)
        def browserLoopPlaybackAvailable(self) -> bool:
            return bool(self._browser_loop_snapshot.playback_available)

        @Property(bool, notify=state_changed)
        def browserLoopWaveformAligned(self) -> bool:
            return bool(self._browser_loop_snapshot.waveform_aligned)

        @Property(float, notify=state_changed)
        def browserLoopWaveformStartRatio(self) -> float:
            return float(self._browser_loop_snapshot.waveform_start_ratio)

        @Property(float, notify=state_changed)
        def browserLoopWaveformEndRatio(self) -> float:
            return float(self._browser_loop_snapshot.waveform_end_ratio)

        @Property(bool, notify=state_changed)
        def contextTargetIsLoopOwner(self) -> bool:
            target = adapter.sample_context_target
            if target is None or not self._browser_loop_snapshot.active:
                return False
            return str(target.path) == self._browser_loop_snapshot.owner_path

        @Property(str, notify=state_changed)
        def browserLoopContextStatus(self) -> str:
            return adapter.browser_loop_context_status

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

        @Property(bool, notify=state_changed)
        def workspacePanelDockingEnabled(self) -> bool:
            return adapter.workspace_panel_docking_enabled

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
        def refreshPlaybackProjection(self) -> None:
            adapter.refresh_preview_playback()
            self._browser_loop_snapshot = adapter.refresh_browser_loop_projection()
            self.state_changed.emit()

        @Slot()
        def refreshPreviewPlayback(self) -> None:
            self.refreshPlaybackProjection()

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

        @Slot(result=bool)
        def contextLoopToggle(self) -> bool:
            result = adapter.request_context_loop_toggle()
            self._browser_loop_snapshot = adapter.refresh_browser_loop_projection()
            self.state_changed.emit()
            return bool(getattr(result, "ok", False))

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
        def removeLiveKitSlot(self, group_index: int, slot_index: int) -> None:
            target = self._live_kit_slot_target(group_index, slot_index)
            if target is None:
                return
            if adapter.remove_live_kit_slot(*target):
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
            """Coherent Esc for pending-add banner or open Kit HUD (#1207).

            Playback must never keep running because the focused banner
            consumed the event: stop preview first, then cancel pending Add
            or close HUD presentation only. Never clears musical kit state.
            """
            adapter.stop_preview()
            adapter.escape_live_kit_context()
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

        @Property(bool, notify=state_changed)
        def internalSampleDragEnabled(self) -> bool:
            return adapter.internal_sample_drag_enabled()

        @Slot(int, str, result=str)
        def requestInternalSampleDragDescriptor(
            self, row_index: int, source_surface: str
        ) -> str:
            descriptor = adapter.build_internal_sample_descriptor(
                row_index, source_surface
            )
            if descriptor is None:
                return ""
            return json.dumps(descriptor)

        @Slot(result="QVariantList")
        def requestVisibleLiveKitDropTargets(self) -> list:
            return adapter.visible_live_kit_drop_targets()

        @Slot(str, str, str, str, str, result="QVariantMap")
        def applyInternalSampleDrop(
            self,
            relative_path: str,
            source_surface: str,
            group: str,
            slot: str,
            delivery_id: str,
        ) -> dict:
            result = adapter.apply_internal_sample_drop(
                relative_path, source_surface, group, slot, delivery_id
            )
            self._refresh()
            return result

        @Slot(result=str)
        def beginInternalSampleDrag(self) -> str:
            """Mint exactly one delivery id for a fresh internal Sample drag.

            QML calls this once at drag start and transports the id to the drop,
            so a duplicated delivery of the SAME drag collapses to
            ``duplicate_delivery`` instead of mutating the kit a second time.
            """
            return f"qml-drag-{uuid.uuid4().hex}"

        @Slot(int, int, str, str, result="QVariantMap")
        def applyInternalSampleDropAtSlot(
            self,
            group_index: int,
            slot_index: int,
            descriptor_json: str,
            delivery_id: str,
        ) -> dict:
            """QML drop entry: resolve (group, slot) and validate the full payload.

            The renderer supplies only indices plus the carried #1072 descriptor
            and its drag delivery id; Python stays authoritative for descriptor
            validation, target eligibility, Add/Replace, projection, and replay.
            """
            target = self._live_kit_slot_target(group_index, slot_index)
            if target is None:
                return {"accepted": False, "mutation": None, "reason": "invalid_target"}
            try:
                payload = json.loads(descriptor_json)
            except (TypeError, ValueError):
                payload = None
            delivery = delivery_id.strip() if isinstance(delivery_id, str) else ""
            result = adapter.apply_internal_sample_drop_payload(
                payload, target[0], target[1], delivery
            )
            self._refresh()
            return result

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
        def toggleLiveKitDrawer(self) -> None:
            adapter.toggle_live_kit_drawer()
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


def _qml_arrangement_bridge(session, adapter):
    """#1080 Arrangement bridge — projection + #1078 mode + Slice B field intent.

    ``WorkbenchSession`` stays the single projection-mode owner; the bridge
    only re-projects after command slots. The Slice B field click sends only
    ``channel_id`` + ``field_index`` to the Python interaction seam
    (:func:`workbench_arrangement_qml.request_arrangement_field_toggle`);
    QML owns no quarter-note math and no pattern truth. After every command
    the projection is re-derived from Python truth. No Pattern/track copy, no
    persistence, no playback authority. Inert (EDIT, no route) for injected
    harness adapters without a composed session.
    """
    from PySide6.QtCore import QObject, Property, Signal, Slot

    from .workbench_arrangement_qml import (
        project_arrangement_for_qml,
        request_arrangement_field_toggle,
        project_arrangement_block_window,
        project_visible_blocks,
        viewport_for_initial_view,
        zoom_in,
        zoom_out,
        pan,
        rebase_viewport_for_tempo_change,
        project_end_marker,
        request_end_marker_set,
        request_end_marker_clear,
        request_end_marker_nudge,
        preview_end_marker_snap,
        ARRANGEMENT_BLOCK_LENGTH_QUARTER_NOTES,
        ArrangementViewportState,
    )
    from . import workbench_arrangement_qml as arrangement_seam

    # Presentation budget only; replace with the later viewport request.
    visible_start_block = 0
    visible_block_count = 6

    def _field_dict(field) -> dict[str, object]:
        return {
            "index": int(field.index),
            "barIndex": int(field.bar_index),
            "indexInBar": int(field.index_in_bar),
            "active": bool(field.active),
        }

    def _track_block_dict(block: arrangement_seam.ArrangementQmlTrackBlock) -> dict[str, object]:
        # Track blocks don't have 'available' field directly; derive from enabled and effective
        eff = block.effective
        is_eligible = eff is True
        is_unresolved = eff == "unresolved"
        is_ooh = eff == "out_of_current_horizon"
        is_unavailable = is_unresolved or is_ooh
        available = bool(block.enabled) and not is_unavailable
        interactive = available and is_eligible
        status = eff if isinstance(eff, str) else ("eligible" if eff else "off")
        return {
            "blockIndex": int(block.block_index),
            "status": status,
            "trackEnabled": bool(block.enabled),
            "available": available,
            "interactive": interactive,
            "effective": block.effective,
        }

    def _track_row_dict(row: arrangement_seam.ArrangementQmlTrackRow) -> dict[str, object]:
        return {
            "channelId": row.channel_id,
            "displayName": row.display_name,
            "groupId": row.group_id,
            "blocks": [_track_block_dict(b) for b in row.blocks],
        }

    class QmlArrangementBridge(QObject):
        state_changed = Signal()

        def __init__(self) -> None:
            super().__init__()
            self._projection_mode = "EDIT"
            self._arrangement_mode_enabled = False
            self._active_track_id = ""
            self._pattern_id = ""
            self._field_count = 32
            self._bar_count = 8
            self._fields_per_bar = 4
            self._bars: list = []
            self._channel_rows: list = []
            self._group_rows: list = []
            # C2b: expand/collapse is presentation-only state
            self._expanded_groups: set[str] = set()
            # C2c1: viewport / zoom / pan presentation state
            self._tempo_map = None
            self._viewport: ArrangementViewportState | None = None
            self._any_active_step = False
            self._last_entry_outcome = ""
            self._last_entry_message = ""
            self._last_field_toggle_outcome = ""
            # C2c2: end-marker projection state (Python-owned)
            self._end_marker_exists = False
            self._end_marker_qn = 0.0
            self._end_marker_visible = False
            self._end_marker_render_eligible = False
            self._end_marker_normalized = 0.0
            self._refresh()

        def _refresh(self) -> None:
            self._arrangement_mode_enabled = bool(
                getattr(adapter, "arrangement_mode_enabled", False)
            )
            try:
                projection = project_arrangement_for_qml(session)
            except (TypeError, ValueError):
                # Fail-soft projection: keep the last owner-reported state.
                self.state_changed.emit()
                return
            self._projection_mode = projection.projection_mode
            self._active_track_id = projection.active_track_id or ""
            self._pattern_id = projection.pattern_id
            self._field_count = int(projection.field_count)
            self._bar_count = int(projection.bar_count)
            self._fields_per_bar = int(projection.fields_per_bar)
            self._any_active_step = bool(projection.any_active_step)
            self._bars = [
                {
                    "index": int(bar.index),
                    "fields": [_field_dict(field) for field in bar.fields],
                }
                for bar in projection.bars
            ]
            self._channel_rows = [
                {
                    "channelId": str(row.channel_id),
                    "displayName": str(row.display_name),
                    "rowKind": str(row.row_kind),
                    "stepGridEnabled": bool(row.step_grid_enabled),
                    "fields": [_field_dict(field) for field in row.fields],
                    "bars": [
                        {
                            "index": int(bar.index),
                            "fields": [_field_dict(field) for field in bar.fields],
                        }
                        for bar in row.bars
                    ],
                }
                for row in projection.channel_rows
            ]
            # C2c2: end-marker projection defaults (fail-closed per refresh)
            self._end_marker_exists = False
            self._end_marker_qn = 0.0
            self._end_marker_visible = False
            self._end_marker_render_eligible = False
            self._end_marker_normalized = 0.0
            self._group_rows = []
            if self._arrangement_mode_enabled and self._projection_mode == "ARRANGEMENT":
                try:
                    # C2c1: Use tempo map from session transport
                    tempo_map = getattr(session.transport, "tempo_map", None)
                    if tempo_map is not None:
                        if tempo_map is not self._tempo_map:
                            if (
                                self._viewport is not None
                                and self._tempo_map is not None
                            ):
                                # C2c1 review F3: rebase the same wall-clock
                                # slice onto the replaced tempo map before
                                # the new projection runs.
                                self._viewport = rebase_viewport_for_tempo_change(
                                    self._viewport, self._tempo_map, tempo_map
                                )
                            self._tempo_map = tempo_map
                        if self._viewport is None:
                            self._viewport = viewport_for_initial_view(tempo_map)
                        window = project_visible_blocks(session, self._viewport)
                    else:
                        window = arrangement_seam.project_arrangement_block_window(
                            session, visible_start_block, visible_block_count
                        )
                    # C2c2: Python-owned end-marker projection. The marker
                    # never mutates; projection failure degrades to defaults
                    # without poisoning the block-group build below.
                    try:
                        marker = project_end_marker(session, self._viewport)
                        self._end_marker_exists = bool(marker.exists)
                        self._end_marker_qn = (
                            float(marker.quarter_note)
                            if marker.quarter_note is not None
                            else 0.0
                        )
                        self._end_marker_visible = bool(marker.visible)
                        self._end_marker_render_eligible = bool(
                            marker.render_eligible
                        )
                        self._end_marker_normalized = (
                            float(marker.normalized_position)
                            if marker.normalized_position is not None
                            else 0.0
                        )
                    except (TypeError, ValueError, AttributeError):
                        pass  # fail-closed: defaults retained, groups unaffected
                    blocks = {b.block_index: b for b in window.blocks}
                    track_rows_by_group = getattr(window, "track_rows_by_group", {})
                    self._group_rows = [
                        {
                            "groupId": group.group_id,
                            "displayName": group.display_name,
                            "expanded": group.group_id in self._expanded_groups,
                            "blocks": [
                                {
                                    "blockIndex": cell.block_index,
                                    "status": blocks[cell.block_index].status,
                                    "blockEnabled": blocks[cell.block_index].enabled,
                                    "groupEnabled": cell.enabled,
                                    "available": cell.available,
                                    # Group OFF is reversible; global OFF and
                                    # ineligible blocks cannot accept input.
                                    "interactive": blocks[cell.block_index].status == "eligible"
                                    and blocks[cell.block_index].enabled,
                                }
                                for cell in window.group_blocks
                                if cell.group_id == group.group_id
                            ],
                            # C2b: track rows only when expanded
                            "trackRows": [
                                _track_row_dict(tr)
                                for tr in track_rows_by_group.get(group.group_id, ())
                            ] if group.group_id in self._expanded_groups else [],
                        }
                        for group in window.groups
                    ]
                except (TypeError, ValueError, AttributeError):
                    pass  # missing/corrupt authority projects no block controls
            self.state_changed.emit()

        @Slot()
        def refresh(self) -> None:
            self._refresh()

        @Slot()
        def enterArrangement(self) -> None:
            """#1078 transition intent — eligibility stays Python-owned."""
            if session is None:
                return
            result = session.enter_arrangement_from_edit()
            self._last_entry_outcome = str(getattr(result, "outcome", "") or "")
            self._last_entry_message = str(getattr(result, "message", "") or "")
            self._refresh()

        @Slot()
        def returnToBrowser(self) -> None:
            """Return to the Browser workspace through the #1078 state owner.

            Chrome vocabulary canon keeps the literal mode word out of
            QML_SOURCE; the Browser nav route is the Edit destination.
            """
            if session is None:
                return
            session.return_to_edit()
            self._last_entry_outcome = ""
            self._last_entry_message = ""
            self._refresh()

        @Slot(str, int, result=str)
        def toggleArrangementField(self, channel_id: str, field_index: int) -> str:
            """One click = one Python-owned field mutation intent (#1080 Slice B).

            QML sends only the channel identity and the projected field
            index; the seam owns editability and the #1086 quarter-note
            mapping. Visual feedback is derived exclusively from the new
            Python projection after the command.
            """
            if session is None:
                self._last_field_toggle_outcome = "fail_closed"
                self._refresh()
                return self._last_field_toggle_outcome
            result = request_arrangement_field_toggle(
                session, str(channel_id), int(field_index)
            )
            self._last_field_toggle_outcome = str(result.outcome)
            self._refresh()
            return self._last_field_toggle_outcome

        @Property(str, notify=state_changed)
        def projectionMode(self) -> str:
            return self._projection_mode

        @Property("QVariantList", notify=state_changed)
        def groupRows(self) -> list:
            return self._group_rows

        @Slot(str, int, result=str)
        def toggleArrangementGroupBlock(self, group_id: str, block_index: int) -> str:
            # Revalidate current authority before dispatch, including stale
            # pointer targets after a feature/tempo/global-mask change.
            self._refresh()
            cell = next((cell for row in self._group_rows
                         if row["groupId"] == group_id
                         for cell in row["blocks"]
                         if cell["blockIndex"] == block_index), None)
            if cell is None or not cell["interactive"]:
                return "unavailable"
            result = arrangement_seam.request_arrangement_group_toggle(
                session, group_id, block_index
            )
            self._refresh()
            return str(result.outcome)

        @Slot(str, result=str)
        def toggleArrangementGroupExpanded(self, group_id: str) -> str:
            """C2b: Expand/collapse is presentation-only — no musical mutation, no save."""
            if group_id in self._expanded_groups:
                self._expanded_groups.discard(group_id)
            else:
                self._expanded_groups.add(group_id)
            self._refresh()
            return "toggled"

        @Slot(str, int, result=str)
        def toggleArrangementTrackBlock(self, channel_id: str, block_index: int) -> str:
            """C2b: Track block toggle routes to Python track-mask intent."""
            # Revalidate current authority before dispatch
            self._refresh()
            # Find the track block to check if interactive
            track_cell = None
            for row in self._group_rows:
                for tr in row.get("trackRows", []):
                    if tr["channelId"] == channel_id:
                        for block in tr["blocks"]:
                            if block["blockIndex"] == block_index:
                                track_cell = block
                                break
                        break
                if track_cell:
                    break
            if track_cell is None or not track_cell["interactive"]:
                return "unavailable"
            result = arrangement_seam.request_arrangement_track_toggle(
                session, channel_id, block_index
            )
            self._refresh()
            return str(result.outcome)

        @Slot(result=str)
        def zoomIn(self) -> str:
            """C2c1: Zoom in (Ctrl+Wheel Up). Reduces visible duration."""
            if self._viewport is None or self._tempo_map is None:
                return "fail_closed"
            self._viewport = zoom_in(
                self._viewport, self._viewport.start_quarter_note + self._viewport.visible_duration_qn / 2, self._tempo_map
            )
            self._refresh()
            return "zoomed"

        @Slot(result=str)
        def zoomOut(self) -> str:
            """C2c1: Zoom out (Ctrl+Wheel Down). Increases visible duration."""
            if self._viewport is None or self._tempo_map is None:
                return "fail_closed"
            self._viewport = zoom_out(
                self._viewport, self._viewport.start_quarter_note + self._viewport.visible_duration_qn / 2, self._tempo_map
            )
            self._refresh()
            return "zoomed"

        @Slot(float, result=str)
        def panHorizontal(self, delta_qn: float) -> str:
            """C2c1: Horizontal pan. Changes only viewport start."""
            if self._viewport is None:
                return "fail_closed"
            self._viewport = pan(self._viewport, Fraction(str(delta_qn)))
            self._refresh()
            return "panned"

        @Slot(float, result=str)
        def requestEndMarkerSet(self, quarter_note: float) -> str:
            """C2c2: One Python-owned end-marker set intent.

            QML sends only the quarter-note position; the domain owns
            snap semantics and the horizon decision. Visual feedback is
            derived exclusively from the new Python projection.
            """
            if session is None or self._viewport is None:
                return "fail_closed"
            result = request_end_marker_set(
                session, Fraction(str(float(quarter_note)))
            )
            self._refresh()
            return str(result.status)

        @Slot(int, result=str)
        def requestEndMarkerNudge(self, direction: int) -> str:
            """C2c2: One Python-owned end-marker nudge intent."""
            if session is None or self._viewport is None:
                return "fail_closed"
            result = request_end_marker_nudge(session, direction)
            self._refresh()
            return str(result.status)

        @Slot(result=str)
        def requestEndMarkerClear(self) -> str:
            """C2c2: One Python-owned end-marker clear intent."""
            if session is None:
                return "fail_closed"
            result = request_end_marker_clear(session)
            self._refresh()
            return str(result.status)

        @Slot(float, result=float)
        def previewEndMarkerSnap(self, quarter_note: float) -> float:
            """C2c2: Snap preview without mutating; -1.0 means unprojected."""
            if session is None:
                return -1.0
            snapped = preview_end_marker_snap(
                session, Fraction(str(float(quarter_note)))
            )
            if snapped is None:
                return -1.0
            return float(snapped)

        @Property(float, notify=state_changed)
        def viewportStartQn(self) -> float:
            """Viewport start position in quarter notes."""
            if self._viewport is None:
                return 0.0
            return float(self._viewport.start_quarter_note)

        @Property(float, notify=state_changed)
        def viewportVisibleDurationQn(self) -> float:
            """Visible duration in quarter notes."""
            if self._viewport is None:
                return 0.0
            return float(self._viewport.visible_duration_qn)

        @Property(float, notify=state_changed)
        def arrangementBlockLengthQn(self) -> float:
            """C2c1 review F4: authority-defined block length in quarter notes."""
            return float(ARRANGEMENT_BLOCK_LENGTH_QUARTER_NOTES)

        @Property(float, notify=state_changed)
        def viewportVisibleQn(self) -> float:
            """C2c1 review F4: visible duration used by marker geometry."""
            if self._viewport is None:
                return 0.0
            return float(self._viewport.visible_duration_qn)

        @Property(float, notify=state_changed)
        def viewportZoomLevel(self) -> float:
            """Current zoom level."""
            if self._viewport is None:
                return 1.0
            return self._viewport.zoom_level

        @Property(float, notify=state_changed)
        def viewportLogicalHorizonQn(self) -> float:
            """Logical horizon in quarter notes (10-minute domain max)."""
            if self._viewport is None:
                return 0.0
            return float(self._viewport.logical_horizon_qn)

        # C2c2: Python-owned end-marker projection surface.
        @Property(float, notify=state_changed)
        def endMarkerQn(self) -> float:
            return 0.0 if self._end_marker_qn is None else float(self._end_marker_qn)

        @Property(bool, notify=state_changed)
        def endMarkerVisible(self) -> bool:
            return self._end_marker_visible

        @Property(bool, notify=state_changed)
        def endMarkerRenderEligible(self) -> bool:
            return self._end_marker_render_eligible

        @Property(float, notify=state_changed)
        def endMarkerNormalizedPosition(self) -> float:
            return 0.0 if self._end_marker_normalized is None else float(self._end_marker_normalized)

        @Property(bool, notify=state_changed)
        def arrangementModeEnabled(self) -> bool:
            return self._arrangement_mode_enabled

        @Property(str, notify=state_changed)
        def activeTrackId(self) -> str:
            return self._active_track_id

        @Property(str, notify=state_changed)
        def patternId(self) -> str:
            return self._pattern_id

        @Property(int, notify=state_changed)
        def fieldCount(self) -> int:
            return self._field_count

        @Property(int, notify=state_changed)
        def barCount(self) -> int:
            return self._bar_count

        @Property(int, notify=state_changed)
        def fieldsPerBar(self) -> int:
            return self._fields_per_bar

        @Property("QVariantList", notify=state_changed)
        def bars(self) -> list:
            return self._bars

        @Property("QVariantList", notify=state_changed)
        def channelRows(self) -> list:
            return self._channel_rows

        @Property(bool, notify=state_changed)
        def anyActiveStep(self) -> bool:
            return self._any_active_step

        @Property(str, notify=state_changed)
        def lastEntryOutcome(self) -> str:
            return self._last_entry_outcome

        @Property(str, notify=state_changed)
        def lastEntryMessage(self) -> str:
            return self._last_entry_message

        @Property(str, notify=state_changed)
        def lastFieldToggleOutcome(self) -> str:
            return self._last_field_toggle_outcome

    return QmlArrangementBridge()


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

        @Property(str, notify=state_changed)
        def activeLibrarySection(self) -> str:
            return library_model.state.active_section

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

        @Slot(str, result=bool)
        def showLibrarySection(self, section: str) -> bool:
            if not library_model.state.show_section(str(section)):
                return False
            self.state_changed.emit()
            return True

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
            if self._prepare_removal_for_node(
                library_model.state.selected_node_id or ""
            ):
                self.removalRequested.emit()

        @Slot(str, result=bool)
        def canRemoveSource(self, node_id: str) -> bool:
            node = library_model.state.node(str(node_id))
            return bool(
                node is not None
                and node.kind is LibraryNodeKind.REGISTERED_ROOT
                and node.folder_id is not None
                and on_prepare_remove is not None
            )

        @Slot(str, result=bool)
        def prepareRemoveSourceForNode(self, node_id: str) -> bool:
            return self._prepare_removal_for_node(str(node_id))

        def _removal_preview_for_node(self, node_id: str):
            node = library_model.state.node(node_id)
            if (
                node is None
                or node.kind is not LibraryNodeKind.REGISTERED_ROOT
                or node.folder_id is None
                or on_prepare_remove is None
            ):
                return None
            try:
                return on_prepare_remove(node.folder_id)
            except Exception:
                return None

        def _prepare_removal_for_node(self, node_id: str) -> bool:
            node = library_model.state.node(node_id)
            preview = self._removal_preview_for_node(node_id)
            if node is None or preview is None:
                return False
            self._removal_folder_id = node.folder_id
            self._removal_path = str(preview.path)
            self._removal_availability = str(preview.availability)
            self._removal_cached_sample_count = int(preview.cached_sample_count)
            self.state_changed.emit()
            return True

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
    platform_color_scheme: str | None = None,
    platform_reduce_motion: bool | None = None,
):
    """Sole Screen-1 Appearance / Theme authority bridge for QML (#785 + #1255).

    Projects one coherent AppearanceResolvedSnapshot into semantic QML properties.
    QML sends typed intents; Python owns resolution and #1254 persistence.
    """
    from dataclasses import replace

    from PySide6.QtCore import Property, QObject, Signal, Slot

    from . import workbench_appearance as appearance_mod
    from . import workbench_theme as theme_mod

    class QmlThemeAuthorityBridge(QObject):
        themeChanged = Signal()
        appearanceChanged = Signal(int)

        def __init__(self) -> None:
            super().__init__()
            self._state_dir = state_dir
            self._env = env
            self._platform_color_scheme = platform_color_scheme
            self._platform_reduce_motion = platform_reduce_motion
            self._generation = 0
            self._requested = appearance_mod.AppearanceRequestedState()
            self._snapshot = appearance_mod.resolve_appearance(self._requested)
            self._projection: dict[str, object] = {}
            self._tokens = self._snapshot.legacy_theme_tokens()
            self._semantics: dict[str, str] = {}
            self._v2_tokens: dict[str, str] = {}
            self._draft_accent = self._snapshot.accent
            self._draft_background = self._snapshot.background
            self._draft_foreground = self._snapshot.foreground
            self._draft_name = self._snapshot.theme_ref
            self._reload()

        def _resolve(
            self, requested: appearance_mod.AppearanceRequestedState
        ) -> appearance_mod.AppearanceResolvedSnapshot:
            return appearance_mod.resolve_appearance(
                requested,
                platform_color_scheme=self._platform_color_scheme,
                platform_reduce_motion=self._platform_reduce_motion,
            )

        def _legacy_with_persisted_base_preset(
            self, legacy: theme_mod.ThemeTokens
        ) -> theme_mod.ThemeTokens:
            """Keep custom-theme base_preset metadata from #785 store (#1255)."""
            if legacy.name in theme_mod.PRESET_ORDER:
                return legacy
            meta = theme_mod.resolve_theme(
                legacy.name,
                state_dir=self._state_dir,
                env=self._env,
            )
            if meta.name != legacy.name:
                return legacy
            if meta.base_preset == legacy.base_preset:
                return legacy
            return replace(legacy, base_preset=meta.base_preset)

        def _apply_snapshot(
            self,
            snapshot: appearance_mod.AppearanceResolvedSnapshot,
            *,
            requested: appearance_mod.AppearanceRequestedState | None = None,
            emit: bool = True,
        ) -> None:
            projection = theme_mod.project_appearance_snapshot_for_qml(snapshot)
            legacy = self._legacy_with_persisted_base_preset(
                projection["legacy_tokens"]  # type: ignore[arg-type]
            )
            projection["legacy_tokens"] = legacy
            # Atomic local swap: readers always see one coherent generation.
            self._snapshot = snapshot
            if requested is not None:
                self._requested = requested
            self._projection = projection
            self._tokens = legacy
            self._semantics = dict(projection["semantics"])  # type: ignore[arg-type]
            self._v2_tokens = dict(projection["tokens"])  # type: ignore[arg-type]
            self._draft_accent = str(projection["accent"])
            self._draft_background = str(projection["background"])
            self._draft_foreground = str(projection["foreground"])
            self._draft_name = str(projection["theme_ref"])
            self._generation += 1
            if emit:
                self.themeChanged.emit()
                self.appearanceChanged.emit(self._generation)

        def _reload(self, tokens: theme_mod.ThemeTokens | None = None) -> None:
            del tokens  # Appearance authority reloads from persisted intent.
            requested = theme_mod.load_appearance_preferences(
                state_dir=self._state_dir,
                env=self._env,
            )
            snapshot = self._resolve(requested)
            self._apply_snapshot(snapshot, requested=requested)

        def _intended_primary_pair(
            self, requested: appearance_mod.AppearanceRequestedState
        ) -> tuple[str, str] | None:
            """Return intended (foreground, background) for the active profile."""
            profile = self._active_profile(requested)
            scheme = self._active_scheme(requested)
            theme_ref = (
                profile.theme_ref
                if profile is not None and isinstance(profile.theme_ref, str) and profile.theme_ref.strip()
                else theme_mod.DEFAULT_PRESET_NAME
            )
            cleaned = theme_ref.strip()
            base_name = (
                cleaned if cleaned in theme_mod.PRESET_ORDER else theme_mod.DEFAULT_PRESET_NAME
            )
            if scheme == appearance_mod.MODE_LIGHT:
                background = appearance_mod.LIGHT_FALLBACK_BACKGROUND
                foreground = appearance_mod.LIGHT_FALLBACK_FOREGROUND
            else:
                base_tokens = theme_mod.resolve_theme(
                    base_name, state_dir=self._state_dir, env=self._env
                )
                background = base_tokens.background
                foreground = base_tokens.foreground
            if profile is not None:
                if profile.background is not None:
                    background = profile.background
                if profile.foreground is not None:
                    foreground = profile.foreground
            bg = theme_mod._normalize_hex(background)
            fg = theme_mod._normalize_hex(foreground)
            if bg is None or fg is None:
                return None
            return fg, bg

        def _profile_primary_unreadable(
            self, requested: appearance_mod.AppearanceRequestedState
        ) -> bool:
            pair = self._intended_primary_pair(requested)
            if pair is None:
                return False
            foreground, background = pair
            return appearance_mod.contrast_ratio(foreground, background) < 4.5

        def _commit_requested(
            self, requested: appearance_mod.AppearanceRequestedState
        ) -> bool:
            # Contract: reject unreadable profiles on commit; keep last valid state.
            if self._profile_primary_unreadable(requested):
                return False
            path = theme_mod.save_appearance_preferences(
                requested,
                state_dir=self._state_dir,
                env=self._env,
            )
            if path is None:
                return False
            loaded = theme_mod.load_appearance_preferences(
                state_dir=self._state_dir,
                env=self._env,
            )
            snapshot = self._resolve(loaded)
            self._apply_snapshot(snapshot, requested=loaded)
            return True

        def _active_scheme(
            self, requested: appearance_mod.AppearanceRequestedState
        ) -> str:
            return appearance_mod.resolve_scheme(
                requested.mode,
                platform_color_scheme=self._platform_color_scheme,
            )

        def _active_profile(
            self, requested: appearance_mod.AppearanceRequestedState
        ) -> appearance_mod.AppearanceProfileInput | None:
            if requested.separate_light_dark:
                scheme = self._active_scheme(requested)
                return requested.dark if scheme == appearance_mod.MODE_DARK else requested.light
            return requested.shared

        def _put_active_profile(
            self,
            requested: appearance_mod.AppearanceRequestedState,
            profile: appearance_mod.AppearanceProfileInput | None,
        ) -> appearance_mod.AppearanceRequestedState:
            if requested.separate_light_dark:
                scheme = self._active_scheme(requested)
                if scheme == appearance_mod.MODE_LIGHT:
                    return replace(requested, light=profile)
                return replace(requested, dark=profile)
            return replace(requested, shared=profile)

        def _profile_with(
            self,
            profile: appearance_mod.AppearanceProfileInput | None,
            *,
            theme_ref: str | None = None,
            background: str | None = None,
            foreground: str | None = None,
            accent: str | None = None,
            contrast: int | None = None,
            clear_overrides: bool = False,
        ) -> appearance_mod.AppearanceProfileInput:
            base = profile or appearance_mod.AppearanceProfileInput()
            if clear_overrides:
                return appearance_mod.AppearanceProfileInput(
                    theme_ref=theme_ref if theme_ref is not None else base.theme_ref,
                )
            return appearance_mod.AppearanceProfileInput(
                theme_ref=base.theme_ref if theme_ref is None else theme_ref,
                background=base.background if background is None else background,
                foreground=base.foreground if foreground is None else foreground,
                accent=base.accent if accent is None else accent,
                contrast=base.contrast if contrast is None else contrast,
            )

        def _selection_profile_for(
            self,
            selected: str,
            *,
            previous: appearance_mod.AppearanceProfileInput | None,
        ) -> appearance_mod.AppearanceProfileInput:
            """Point the active profile at ``selected`` with #785 selection semantics."""
            contrast = (
                previous.contrast
                if previous is not None and previous.contrast is not None
                else appearance_mod.DEFAULT_CONTRAST
            )
            if selected in theme_mod.PRESET_ORDER:
                return appearance_mod.AppearanceProfileInput(
                    theme_ref=selected,
                    contrast=contrast,
                )
            meta = theme_mod.resolve_theme(
                selected,
                state_dir=self._state_dir,
                env=self._env,
            )
            if meta.name != selected:
                return appearance_mod.AppearanceProfileInput(
                    theme_ref=theme_mod.DEFAULT_PRESET_NAME,
                    contrast=contrast,
                )
            return appearance_mod.AppearanceProfileInput(
                theme_ref=selected,
                background=meta.background,
                foreground=meta.foreground,
                accent=meta.accent,
                contrast=contrast,
            )

        def _commit_theme_selection(self, name: str) -> bool:
            cleaned = str(name).strip()
            if not cleaned:
                return False
            available = set(self._available_names())
            if cleaned not in available:
                cleaned = theme_mod.DEFAULT_PRESET_NAME
            requested = self._requested
            profile = self._selection_profile_for(
                cleaned,
                previous=self._active_profile(requested),
            )
            return self._commit_requested(self._put_active_profile(requested, profile))

        def _rewrite_theme_refs(
            self,
            requested: appearance_mod.AppearanceRequestedState,
            *,
            old_name: str,
            new_name: str | None,
        ) -> appearance_mod.AppearanceRequestedState:
            """Rewrite profile themeRef values after custom rename/delete."""

            def _one(
                profile: appearance_mod.AppearanceProfileInput | None,
            ) -> appearance_mod.AppearanceProfileInput | None:
                if profile is None or profile.theme_ref != old_name:
                    return profile
                if new_name is None:
                    return appearance_mod.AppearanceProfileInput(
                        theme_ref=theme_mod.DEFAULT_PRESET_NAME,
                        contrast=profile.contrast,
                    )
                return replace(profile, theme_ref=new_name)

            return replace(
                requested,
                shared=_one(requested.shared),
                dark=_one(requested.dark),
                light=_one(requested.light),
            )

        def _preview_from_draft(self) -> None:
            accent = theme_mod._normalize_hex(self._draft_accent)
            background = theme_mod._normalize_hex(self._draft_background)
            foreground = theme_mod._normalize_hex(self._draft_foreground)
            if accent is None or background is None or foreground is None:
                return
            # Reject unreadable drafts instead of projecting #1253's Blood
            # fail-closed identity over the in-progress custom theme.
            if appearance_mod.contrast_ratio(foreground, background) < 4.5:
                return
            preview = appearance_mod.resolve_appearance(
                appearance_mod.AppearanceRequestedState(
                    mode=self._requested.mode,
                    separate_light_dark=False,
                    ui_font_size=self._requested.ui_font_size,
                    code_font_size=self._requested.code_font_size,
                    motion_mode=self._requested.motion_mode,
                    shared=appearance_mod.AppearanceProfileInput(
                        theme_ref=self._draft_name,
                        background=background,
                        foreground=foreground,
                        accent=accent,
                        contrast=self._snapshot.contrast,
                    ),
                ),
                platform_color_scheme=self._platform_color_scheme,
                platform_reduce_motion=self._platform_reduce_motion,
            )
            identity_name = self._tokens.name
            identity_base = self._tokens.base_preset
            # Keep custom identity even if resolve unexpectedly fail-closes.
            if (
                identity_name not in theme_mod.PRESET_ORDER
                and preview.theme_ref != identity_name
            ):
                return
            # Draft preview is ephemeral: project without persistence.
            self._apply_snapshot(preview, requested=self._requested)
            # Restore editable draft + custom identity after snapshot apply.
            self._draft_accent = accent
            self._draft_background = background
            self._draft_foreground = foreground
            self._draft_name = identity_name
            self._tokens = replace(
                self._tokens,
                name=identity_name,
                base_preset=identity_base,
            )

        def _color(self, key: str) -> str:
            return str(self._semantics.get(key) or theme_mod.TEXT_ON_ACTION)

        def _available_names(self) -> list[str]:
            customs = theme_mod.list_custom_themes(
                state_dir=self._state_dir,
                env=self._env,
            )
            return list(theme_mod.list_presets()) + customs

        @Property(int, notify=appearanceChanged)
        def snapshotGeneration(self) -> int:
            return self._generation

        @Property("QVariantMap", notify=appearanceChanged)
        def tokenSnapshot(self) -> dict:
            return dict(self._v2_tokens)

        @Property(str, notify=appearanceChanged)
        def themeRef(self) -> str:
            return str(self._projection.get("theme_ref") or self._snapshot.theme_ref)

        @Property(str, notify=appearanceChanged)
        def modeRequested(self) -> str:
            return str(self._projection.get("mode_requested") or self._snapshot.mode_requested)

        @Property(str, notify=appearanceChanged)
        def resolvedScheme(self) -> str:
            return str(
                self._projection.get("resolved_scheme") or self._snapshot.resolved_scheme
            )

        @Property(bool, notify=appearanceChanged)
        def separateLightDark(self) -> bool:
            return bool(
                self._projection.get(
                    "separate_light_dark", self._snapshot.separate_light_dark
                )
            )

        @Property(int, notify=appearanceChanged)
        def contrast(self) -> int:
            return int(self._projection.get("contrast", self._snapshot.contrast))

        @Property(int, notify=appearanceChanged)
        def uiFontSize(self) -> int:
            return int(self._projection.get("ui_font_size", self._snapshot.ui_font_size))

        @Property(int, notify=appearanceChanged)
        def codeFontSize(self) -> int:
            return int(
                self._projection.get("code_font_size", self._snapshot.code_font_size)
            )

        @Property(str, notify=appearanceChanged)
        def motionModeRequested(self) -> str:
            return str(
                self._projection.get("motion_mode_requested")
                or self._snapshot.motion_mode_requested
            )

        @Property(str, notify=appearanceChanged)
        def motionEffective(self) -> str:
            return str(
                self._projection.get("motion_effective") or self._snapshot.motion_effective
            )

        @Property(str, notify=appearanceChanged)
        def windowChromeBackground(self) -> str:
            return str(
                self._projection.get("window_chrome_background")
                or self._snapshot.tokens.window_chrome_background
            )

        @Property(str, notify=appearanceChanged)
        def windowChromeForeground(self) -> str:
            return str(
                self._projection.get("window_chrome_foreground")
                or self._snapshot.tokens.window_chrome_foreground
            )

        @Property(str, notify=appearanceChanged)
        def windowChromeBorder(self) -> str:
            return str(
                self._projection.get("window_chrome_border")
                or self._snapshot.tokens.window_chrome_border
            )

        @Property(float, notify=appearanceChanged)
        def typographyUiStandardSize(self) -> float:
            return float(
                self._projection.get(
                    "typography_ui_standard_size",
                    self._snapshot.typography.ui.standard.font_size,
                )
            )

        @Property(float, notify=appearanceChanged)
        def typographyCodeSize(self) -> float:
            return float(
                self._projection.get(
                    "typography_code_size",
                    self._snapshot.typography.code.font_size,
                )
            )

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
        def libraryFocusRing(self) -> str:
            return self._color("libraryFocusRing")

        @Property(str, notify=themeChanged)
        def surfaceLibrary(self) -> str:
            return self._color("surfaceLibrary")

        @Property(str, notify=themeChanged)
        def libraryAllSamplesAccent(self) -> str:
            return self._color("libraryAllSamplesAccent")

        @Property(str, notify=themeChanged)
        def libraryCollectionsAccent(self) -> str:
            return self._color("libraryCollectionsAccent")

        @Property(str, notify=themeChanged)
        def libraryFavoritesAccent(self) -> str:
            return self._color("libraryFavoritesAccent")

        @Property(str, notify=themeChanged)
        def libraryRecordsAccent(self) -> str:
            return self._color("libraryRecordsAccent")

        @Property(str, notify=themeChanged)
        def surfaceElevated(self) -> str:
            return self._color("surfaceElevated")

        @Property(str, notify=themeChanged)
        def borderSubtle(self) -> str:
            return self._color("borderSubtle")

        @Property(str, notify=themeChanged)
        def borderDefault(self) -> str:
            return self._color("borderDefault")

        @Property(str, notify=themeChanged)
        def borderStrong(self) -> str:
            return self._color("borderStrong")

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
        def textMuted(self) -> str:
            return self._color("textMuted")

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
        def accentHover(self) -> str:
            return self._color("accentHover")

        @Property(str, notify=themeChanged)
        def accentActive(self) -> str:
            return self._color("accentActive")

        @Property(str, notify=themeChanged)
        def accentSubtle(self) -> str:
            return self._color("accentSubtle")

        @Property(str, notify=themeChanged)
        def focusRing(self) -> str:
            return self._color("focusRing")

        @Property(str, notify=themeChanged)
        def hoverSurface(self) -> str:
            return self._color("hoverSurface")

        @Property(str, notify=themeChanged)
        def interactionPressed(self) -> str:
            return self._color("interactionPressed")

        @Property(str, notify=themeChanged)
        def interactionDisabled(self) -> str:
            return self._color("interactionDisabled")

        @Property(str, notify=themeChanged)
        def interactionSelection(self) -> str:
            return self._color("interactionSelection")

        @Property(str, notify=themeChanged)
        def statusError(self) -> str:
            return self._color("statusError")

        @Property(str, notify=themeChanged)
        def statusWarning(self) -> str:
            return self._color("statusWarning")

        @Property(str, notify=themeChanged)
        def statusSuccess(self) -> str:
            return self._color("statusSuccess")

        @Property(str, notify=themeChanged)
        def statusInfo(self) -> str:
            return self._color("statusInfo")

        @Slot(str)
        def selectTheme(self, name: str) -> None:
            # Platform-aware active profile (not #785 system→dark sync heuristic).
            self._commit_theme_selection(name)

        @Slot(str)
        def setPreset(self, name: str) -> None:
            self._commit_theme_selection(name)

        @Slot(str)
        def setMode(self, mode: str) -> None:
            self._commit_requested(replace(self._requested, mode=str(mode)))

        @Slot(bool)
        def setSeparateLightDark(self, enabled: bool) -> None:
            requested = self._requested
            flag = bool(enabled)
            if flag and not requested.separate_light_dark:
                shared = requested.shared or appearance_mod.AppearanceProfileInput(
                    theme_ref=self._snapshot.theme_ref,
                    background=self._snapshot.background,
                    foreground=self._snapshot.foreground,
                    accent=self._snapshot.accent,
                    contrast=self._snapshot.contrast,
                )
                dark = requested.dark or shared
                light = requested.light or shared
                requested = replace(
                    requested,
                    separate_light_dark=True,
                    shared=shared,
                    dark=dark,
                    light=light,
                )
            else:
                requested = replace(requested, separate_light_dark=flag)
            self._commit_requested(requested)

        @Slot(str)
        def setBackground(self, value: str) -> None:
            normalized = theme_mod._normalize_hex(value)
            if normalized is None:
                return
            requested = self._requested
            profile = self._profile_with(
                self._active_profile(requested),
                background=normalized,
            )
            self._commit_requested(self._put_active_profile(requested, profile))

        @Slot(str)
        def setForeground(self, value: str) -> None:
            normalized = theme_mod._normalize_hex(value)
            if normalized is None:
                return
            requested = self._requested
            profile = self._profile_with(
                self._active_profile(requested),
                foreground=normalized,
            )
            self._commit_requested(self._put_active_profile(requested, profile))

        @Slot(str)
        def setAccent(self, value: str) -> None:
            normalized = theme_mod._normalize_hex(value)
            if normalized is None:
                return
            requested = self._requested
            profile = self._profile_with(
                self._active_profile(requested),
                accent=normalized,
            )
            self._commit_requested(self._put_active_profile(requested, profile))

        @Slot(int)
        def setContrast(self, value: int) -> None:
            requested = self._requested
            profile = self._profile_with(
                self._active_profile(requested),
                contrast=int(value),
            )
            self._commit_requested(self._put_active_profile(requested, profile))

        @Slot(int)
        def setUiFontSize(self, value: int) -> None:
            self._commit_requested(replace(self._requested, ui_font_size=int(value)))

        @Slot(int)
        def setCodeFontSize(self, value: int) -> None:
            self._commit_requested(replace(self._requested, code_font_size=int(value)))

        @Slot(str)
        def setMotionMode(self, mode: str) -> None:
            self._commit_requested(replace(self._requested, motion_mode=str(mode)))

        @Slot()
        def resetCurrentProfile(self) -> None:
            requested = self._requested
            active = self._active_profile(requested)
            theme_ref = (
                active.theme_ref
                if active is not None and active.theme_ref
                else self._snapshot.theme_ref
            )
            if not theme_ref or theme_ref == "custom":
                theme_ref = theme_mod.DEFAULT_PRESET_NAME
            profile = appearance_mod.AppearanceProfileInput(theme_ref=theme_ref)
            self._commit_requested(self._put_active_profile(requested, profile))

        @Slot(str)
        def setPlatformColorScheme(self, scheme: str) -> None:
            token = str(scheme or "").strip().lower()
            self._platform_color_scheme = token if token in {"light", "dark"} else None
            snapshot = self._resolve(self._requested)
            self._apply_snapshot(snapshot, requested=self._requested)

        @Slot(bool)
        def setPlatformReduceMotion(self, enabled: bool) -> None:
            self._platform_reduce_motion = bool(enabled)
            snapshot = self._resolve(self._requested)
            self._apply_snapshot(snapshot, requested=self._requested)

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
            self._commit_theme_selection(name)

        @Slot(str, str)
        def createCustomFromPreset(self, base_preset: str, name: str) -> None:
            theme_mod.create_custom_theme(
                name=str(name),
                base_preset=str(base_preset),
                state_dir=self._state_dir,
                env=self._env,
            )
            self._commit_theme_selection(str(name))

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
            name = self._tokens.name
            theme_mod.save_custom_theme(
                {
                    "name": name,
                    "base_preset": self._tokens.base_preset,
                    "accent": self._draft_accent,
                    "background": self._draft_background,
                    "foreground": self._draft_foreground,
                },
                state_dir=self._state_dir,
                env=self._env,
            )
            self._commit_theme_selection(name)

        @Slot(str)
        def renameCurrentCustom(self, new_name: str) -> None:
            if self._tokens.name in theme_mod.PRESET_ORDER:
                return
            old = self._tokens.name
            cleaned = str(new_name).strip()
            if not cleaned:
                return
            theme_mod.rename_custom_theme(
                old,
                cleaned,
                state_dir=self._state_dir,
                env=self._env,
            )
            rewritten = self._rewrite_theme_refs(
                self._requested,
                old_name=old,
                new_name=cleaned,
            )
            self._commit_requested(rewritten)

        @Slot()
        def deleteCurrentCustom(self) -> None:
            if self._tokens.name in theme_mod.PRESET_ORDER:
                return
            old = self._tokens.name
            theme_mod.delete_custom_theme(
                old,
                state_dir=self._state_dir,
                env=self._env,
            )
            rewritten = self._rewrite_theme_refs(
                self._requested,
                old_name=old,
                new_name=None,
            )
            self._commit_requested(rewritten)

        @Slot()
        def resetCurrentCustom(self) -> None:
            if self._tokens.name in theme_mod.PRESET_ORDER:
                return
            name = self._tokens.name
            theme_mod.reset_custom_theme(
                name,
                state_dir=self._state_dir,
                env=self._env,
            )
            self._commit_theme_selection(name)

    return QmlThemeAuthorityBridge()


def _hydrate_waveform_rows(
    view_model: Screen1QmlViewModel,
    rows: tuple[QmlBrowserRow | QmlHarmonyRow, ...],
    *,
    waveform_cache: BoundedLazyWaveformCache,
    library_db_path: Path,
) -> set[str]:
    """Project valid memory or persisted artifacts into one model update."""
    changed_paths: set[str] = set()
    persisted_requests: dict[str, tuple[int, int]] = {}
    for row in rows:
        if row.waveform_envelope:
            continue
        path = str(row.source_row.path)
        fingerprint = _waveform_fingerprint(row.source_row)
        cached = waveform_cache.get(
            path,
            source_size_bytes=fingerprint[0] if fingerprint else None,
            source_mtime_ns=fingerprint[1] if fingerprint else None,
            touch=True,
        )
        if cached is not None:
            if cached.state == "ready":
                if cached.envelope and view_model.set_browser_waveform(path, cached.envelope):
                    changed_paths.add(path)
                continue
            if cached.state == "placeholder" and cached.failure:
                continue
        if fingerprint is not None:
            persisted_requests[path] = fingerprint
    if persisted_requests:
        try:
            persisted = load_valid_waveform_artifacts(
                persisted_requests, db_path=library_db_path
            )
        except Exception:
            persisted = {}
        for path, envelope in persisted.items():
            size_bytes, mtime_ns = persisted_requests[path]
            waveform_cache.put_result(
                path,
                WaveformCacheResult("ready", envelope),
                source_size_bytes=size_bytes,
                source_mtime_ns=mtime_ns,
            )
            if view_model.set_browser_waveform(path, envelope):
                changed_paths.add(path)
    return changed_paths


def _hydrate_harmony_waveform_rows(
    view_model: Screen1QmlViewModel,
    rows: tuple[QmlHarmonyRow, ...],
    *,
    waveform_cache: BoundedLazyWaveformCache,
    library_db_path: Path,
    notify_harmony_rows: Callable[[], None],
) -> set[str]:
    """Notify QML when memory or persisted hydration changes harmony rows."""
    hydrated = _hydrate_waveform_rows(
        view_model,
        rows,
        waveform_cache=waveform_cache,
        library_db_path=library_db_path,
    )
    if hydrated:
        notify_harmony_rows()
    return hydrated


def _apply_cached_waveform_to_model(
    view_model: Screen1QmlViewModel,
    path: str,
    envelope: tuple[float, ...],
    *,
    notify_harmony_rows: Callable[[], None],
) -> bool:
    """Apply a decoded cache result and notify its harmony projection."""
    harmony_before = view_model.harmony_rows
    changed = view_model.set_browser_waveform(path, envelope)
    if view_model.harmony_rows != harmony_before:
        notify_harmony_rows()
    return changed


def _project_ready_cached_waveforms(
    view_model: Screen1QmlViewModel,
    waveform_cache: BoundedLazyWaveformCache,
    *,
    notify_harmony_rows: Callable[[], None],
) -> bool:
    """Project only cache results that differ from the published row."""
    changed = False
    for row in (*view_model.browser_rows, *view_model.harmony_rows):
        fingerprint = _waveform_fingerprint(row.source_row)
        path = str(row.source_row.path)
        cached = waveform_cache.get(
            path,
            source_size_bytes=fingerprint[0] if fingerprint else None,
            source_mtime_ns=fingerprint[1] if fingerprint else None,
            touch=True,
        )
        if (
            cached is not None
            and cached.state == "ready"
            and row.waveform_envelope != cached.envelope
        ):
            changed = _apply_cached_waveform_to_model(
                view_model,
                path,
                cached.envelope,
                notify_harmony_rows=notify_harmony_rows,
            ) or changed
    return changed


def _schedule_wave2_candidates(
    candidates: Sequence[WaveformEnrichmentCandidate],
    *,
    waveform_cache: BoundedLazyWaveformCache,
    waveform_loader: BoundedBackgroundWaveformLoader,
    cursor: int,
) -> int:
    """Advance past terminal cache results; retain cursor on admission failure."""
    for candidate in candidates:
        cached = waveform_cache.get(
            candidate.path,
            source_size_bytes=candidate.source_size_bytes,
            source_mtime_ns=candidate.source_mtime_ns,
        )
        if waveform_pump_decision(cached=cached) == "skip":
            cursor = candidate.sample_id
            continue
        if not waveform_loader.schedule(
            candidate.path,
            priority=BACKGROUND_ENRICHMENT,
            generation=waveform_loader.current_generation,
            source_size_bytes=candidate.source_size_bytes,
            source_mtime_ns=candidate.source_mtime_ns,
        ):
            break
        cursor = candidate.sample_id
    return cursor


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
        adapter.load_workspace_layout_state()
    except Exception:
        # Functional/docking presentation is fail-closed; Workbench startup continues.
        pass
    library_model = create_qt_library_tree_model(view_model.library_tree)

    def refresh_screen_model() -> None:
        screen_model.refresh()

    def refresh_browser_rows() -> None:
        screen_model.refresh_browser_rows()

    def refresh_browser_scope() -> None:
        screen_model.refresh_browser_scope()

    # In test environments, disable the background waveform loader to avoid
    # COM threading issues (0x8001010d) on Windows when running under pytest.
    if os.environ.get("SAMPLE_BRAIN_TEST_NO_WAVEFORM_LOADER") == "1":
        waveform_cache = None
        waveform_loader = None
    else:
        def persist_waveform_result(completed: WaveformDecodeResult) -> None:
            if (
                completed.result.state != "ready"
                or not completed.result.envelope
                or completed.source_size_bytes is None
                or completed.source_mtime_ns is None
            ):
                return
            try:
                store_waveform_artifact(
                    completed.path,
                    source_size_bytes=completed.source_size_bytes,
                    source_mtime_ns=completed.source_mtime_ns,
                    envelope=completed.result.envelope,
                    db_path=adapter.library_db_path,
                )
            except Exception:
                # Optional enrichment must never break Browser interaction.
                return

        waveform_cache = BoundedLazyWaveformCache(
            capacity=48,
            loader=lambda path: compute_waveform_envelope(
                path, max_points=WAVEFORM_POINT_BUDGET
            ),
        )
        waveform_loader = BoundedBackgroundWaveformLoader(
            cache=waveform_cache,
            loader=lambda path: compute_waveform_envelope(
                path, max_points=WAVEFORM_POINT_BUDGET
            ),
            max_pending=14,
            on_result=persist_waveform_result,
        )
        # Engines may be destroyed while the shared application keeps running.
        engine.destroyed.connect(waveform_loader.close)
        app.aboutToQuit.connect(waveform_loader.close)
    # Last viewport ranges — drain re-requests so max_pending saturation
    # still fills the full compact visible window without raising the bound.
    browser_waveform_viewport = [0, 0]
    harmony_waveform_viewport = [0, 0]
    wave2_cursor = [0]
    wave2_exhausted = [False]

    def begin_waveform_scope() -> None:
        if waveform_loader is not None:
            waveform_loader.advance_generation()
        wave2_cursor[0] = 0
        wave2_exhausted[0] = False

    def hydrate_waveform_rows(
        rows: tuple[QmlBrowserRow | QmlHarmonyRow, ...],
    ) -> set[str]:
        if waveform_cache is None:
            return set()
        return _hydrate_waveform_rows(
            view_model,
            rows,
            waveform_cache=waveform_cache,
            library_db_path=adapter.library_db_path,
        )

    def hydrate_harmony_waveform_rows(
        rows: tuple[QmlHarmonyRow, ...],
    ) -> set[str]:
        if waveform_cache is None:
            return set()
        return _hydrate_harmony_waveform_rows(
            view_model,
            rows,
            waveform_cache=waveform_cache,
            library_db_path=adapter.library_db_path,
            notify_harmony_rows=screen_model.harmonyRowsChanged.emit,
        )

    def pump_wave2() -> None:
        if (
            waveform_loader is None
            or wave2_exhausted[0]
            or runtime_composition is None
            or not runtime_composition.browser_materialized
            or getattr(adapter, "_preview_active", False)
            or waveform_loader.pending_count_for(CURRENT_VISIBLE) > 0
        ):
            return
        available = waveform_loader.available_capacity
        if available <= 0:
            return
        try:
            page = list_waveform_enrichment_candidates(
                db_path=adapter.library_db_path,
                after_sample_id=wave2_cursor[0],
                limit=available,
            )
        except Exception:
            wave2_exhausted[0] = True
            return
        cursor = wave2_cursor[0]
        if page.candidates:
            cursor = _schedule_wave2_candidates(
                page.candidates,
                waveform_cache=waveform_cache,
                waveform_loader=waveform_loader,
                cursor=cursor,
            )
        if not page.candidates or cursor == page.candidates[-1].sample_id:
            cursor = page.scanned_through_sample_id
            wave2_exhausted[0] = page.exhausted
        wave2_cursor[0] = cursor

    def request_waveforms(start: int, count: int) -> None:
        if count <= 0 or waveform_loader is None:
            return
        first = max(0, start)
        last = min(len(view_model.browser_rows), first + count)
        browser_waveform_viewport[0] = first
        browser_waveform_viewport[1] = max(0, last - first)
        rows = view_model.browser_rows[first:last]
        hydrated = hydrate_waveform_rows(rows)
        if hydrated:
            refresh_browser_rows()
        for row in rows:
            path = str(row.source_row.path)
            if row.waveform_envelope or path in hydrated:
                continue
            fingerprint = _waveform_fingerprint(row.source_row)
            waveform_loader.schedule(
                path,
                priority=CURRENT_VISIBLE,
                generation=waveform_loader.current_generation,
                source_size_bytes=fingerprint[0] if fingerprint else None,
                source_mtime_ns=fingerprint[1] if fingerprint else None,
            )
        pump_wave2()

    def request_harmony_waveforms(start: int, count: int) -> None:
        if count <= 0 or waveform_loader is None:
            return
        first = max(0, start)
        last = min(len(view_model.harmony_rows), first + count)
        harmony_waveform_viewport[0] = first
        harmony_waveform_viewport[1] = max(0, last - first)
        rows = view_model.harmony_rows[first:last]
        hydrated = hydrate_harmony_waveform_rows(rows)
        for row in rows:
            path = str(row.source_row.path)
            if row.waveform_envelope or path in hydrated:
                continue
            fingerprint = _waveform_fingerprint(row.source_row)
            waveform_loader.schedule(
                path,
                priority=CURRENT_VISIBLE,
                generation=waveform_loader.current_generation,
                source_size_bytes=fingerprint[0] if fingerprint else None,
                source_mtime_ns=fingerprint[1] if fingerprint else None,
            )

    def request_visible_browser_waveforms_from_window() -> None:
        """Python-side viewport seed after model refresh; QML owns scroll/resize."""
        if waveform_loader is None:
            return
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
        if waveform_loader is None or waveform_cache is None:
            return
        waveform_loader.drain_results()
        changed = _project_ready_cached_waveforms(
            view_model,
            waveform_cache,
            notify_harmony_rows=screen_model.harmonyRowsChanged.emit,
        )
        if changed:
            refresh_browser_rows()
        # Freeing pending slots must continue filling the current viewport.
        if browser_waveform_viewport[1] > 0:
            request_waveforms(browser_waveform_viewport[0], browser_waveform_viewport[1])
        if harmony_waveform_viewport[1] > 0:
            request_harmony_waveforms(
                harmony_waveform_viewport[0], harmony_waveform_viewport[1]
            )
        pump_wave2()

    analysis_coordinator = None
    layout_model = None
    bridge = None  # assigned below; closures resolve at call time

    def apply_analysis_state(state: AnalysisUiState) -> None:
        view_model.set_analysis_state(state)
        if state.phase in {"scanning", "analyzing"}:
            # #742: hide working panes while analysis runs; keep technical identity.
            # #1077: also close Live Kit presentation so drawer flags cannot desync.
            view_model.set_workspace_materialization(
                has_active_source=False,
                calm_canvas_visible=False,
                browser_materialized=False,
                live_kit_materialized=False,
            )
            adapter.suspend_live_kit_for_analysis()
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
        begin_waveform_scope()
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
            adapter.suspend_live_kit_for_analysis()
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
        # #1077: rematerialize after scope recovery (not only post-analysis).
        adapter.restore_live_kit_after_active_source()
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
        target_node_id = (
            runtime_composition.post_analysis_node_id(
                folder_id,
                previous_selected=previous_selected,
            )
            if runtime_composition is not None
            else f"root:{folder_id}"
        )
        target_node = library_model.state.node(target_node_id)
        target_relative_path = (
            target_node.relative_path
            if target_node is not None
            and target_node.kind is LibraryNodeKind.SUBFOLDER
            and target_node.folder_id == folder_id
            else None
        )
        library_model.replaceBranch("container:sample-sources")
        root_node_id = f"root:{folder_id}"
        if target_relative_path:
            parent_node_id = root_node_id
            parent_relative_path = ""
            for part in Path(target_relative_path).parts:
                library_model.ensureChildren(parent_node_id)
                parent_relative_path = os.path.join(parent_relative_path, part)
                child_node = next(
                    (
                        node
                        for node in library_model.state.visible_children(parent_node_id)
                        if node.kind is LibraryNodeKind.SUBFOLDER
                        and os.path.normcase(node.relative_path or "")
                        == os.path.normcase(parent_relative_path)
                    ),
                    None,
                )
                if child_node is None:
                    target_node_id = root_node_id
                    break
                target_node_id = child_node.node_id
                parent_node_id = child_node.node_id
        elif target_node_id.startswith(f"folder:{folder_id}:"):
            target_node_id = root_node_id
        # #742 default: Live Kit stays hidden after success unless #1077 preference
        # asks to rematerialize through the canonical reveal seam.
        if runtime_composition is not None:
            runtime_composition.clear_live_kit_disclosure()
        if library_model.selectNode(target_node_id):
            # Force immediate materialization of analyzed source (no refresh loop).
            intent = library_model.state.selection_intent
            if intent is not None and runtime_composition is not None:
                begin_waveform_scope()
                runtime_composition.dispatch_selection(intent)
                _sync_runtime_browser_state(view_model, adapter, runtime_composition)
                request_visible_browser_waveforms_from_window()
                refresh_browser_scope()
                adapter.restore_live_kit_after_active_source()
                bridge.refreshState()
                layout_model.syncFromInteraction()
            else:
                dispatch_library_selection()
                adapter.restore_live_kit_after_active_source()
                bridge.refreshState()
                layout_model.syncFromInteraction()
        else:
            adapter.restore_live_kit_after_active_source()
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
        # #1204: presentation collapse is orthogonal to progressive disclosure.
        live_kit_visible=lambda: (
            bool(adapter.view_model.live_kit_materialized)
            and not bool(adapter.live_kit_collapsed)
        ),
        browser_visible=lambda: not bool(adapter.browser_collapsed),
    )

    def on_interaction_state_changed() -> None:
        if waveform_loader is not None:
            waveform_loader.set_background_paused(adapter.preview_active)
        refresh_screen_model()
        # Recompute widths before QML reacts to state_changed so RowLayout
        # never sees a 3-panel width set with a third handle visible.
        layout_model.syncFromInteraction()
        # #908: Live Kit mutations materialize/reconcile bottom Rack projection.
        rack_bridge = getattr(engine, "_screen1_channel_rack_bridge", None)
        if rack_bridge is not None:
            rack_bridge.refresh()
        if not adapter.preview_active:
            pump_wave2()

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
    arrangement_bridge = _qml_arrangement_bridge(session, adapter)
    transport_bridge.state_changed.connect(arrangement_bridge.refresh)

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

    def refresh_browser_projection() -> None:
        begin_waveform_scope()
        refresh_browser_rows()

    bridge = _qml_interaction_bridge(
        adapter,
        on_state_changed=on_interaction_state_changed,
        on_browser_rows_changed=refresh_browser_projection,
        on_waveform_request=request_waveforms,
        on_harmony_waveform_request=request_harmony_waveforms,
        on_open_channel_rack=open_channel_rack,
        on_return_to_screen1=return_to_screen1,
        # C2c1 review F3: reconnect the arrangement viewport when the session
        # replaces the transport's tempo map (ADR C2c1 rebase seam).
        tempo_map_provider=(
            (lambda: getattr(session.transport, "tempo_map", None))
            if session is not None
            else None
        ),
        on_tempo_map_replaced=arrangement_bridge.refresh,
    )
    # #1285: capability/SYNC changes must refresh Loop availability even when
    # the animation driver is stopped because playback is currently unavailable.
    transport_bridge.state_changed.connect(bridge.refreshPlaybackProjection)
    adapter._runtime_composition = runtime_composition
    # #1077: restore workspace visibility preference only for production-composed
    # adapters. Injected harness adapters own their presentation state.
    if interaction_adapter is None:
        adapter.apply_live_kit_visibility_preference()
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
    engine.rootContext().setContextProperty("arrangementModel", arrangement_bridge)
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
    native_chrome = None
    try:
        engine.loadData(QML_SOURCE.encode("utf-8"), QUrl("qrc:/screen1.qml"))
        root_objects = engine.rootObjects()
        if not root_objects:
            raise RuntimeError("Qt Quick Screen-1 Renderer konnte keine QML-Oberfläche laden.")
        root_window = root_objects[0]
        show_window_on_primary_screen(app, root_window)
        # #1214: native caption inherits Appearance windowChrome.* (fail-soft).
        native_chrome = wire_theme_authority(root_window, theme_authority)
    except BaseException:
        if waveform_loader is not None:
            waveform_loader.close()
        engine.deleteLater()
        raise
    # Keep both Python objects alive for the complete Qt engine lifetime.
    engine._screen1_interaction_adapter = adapter
    engine._screen1_interaction_bridge = bridge
    engine._screen1_layout_model = layout_model
    engine._screen1_library_model = library_model
    engine._screen1_library_bridge = library_bridge
    engine._screen1_screen_model = screen_model
    engine._screen1_theme_authority = theme_authority
    engine._screen1_native_window_chrome = native_chrome
    engine._screen1_live_kit = live_kit
    engine._screen1_session = session
    engine._screen1_channel_rack = channel_rack_controller
    engine._screen1_channel_rack_bridge = channel_rack_bridge
    engine._screen1_arrangement_bridge = arrangement_bridge
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

    waveform_timer = QTimer(engine)
    waveform_timer.setInterval(50)
    waveform_timer.timeout.connect(drain_waveforms)
    waveform_timer.start()
    engine._screen1_waveform_timer = waveform_timer

    channel_rack_timer = QTimer(engine)
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

    # #1284: recurring native-frame Loop scheduling (not tempo/SYNC observers alone).
    browser_loop_timer = QTimer(engine)
    browser_loop_timer.setInterval(20)

    def _tick_browser_loop() -> None:
        sess = getattr(engine, "_screen1_session", None)
        if sess is None or not getattr(sess, "browser_loop", None):
            browser_loop_timer.stop()
            return
        if sess.browser_loop.is_active:
            sess.tick_browser_loop()
        else:
            browser_loop_timer.stop()

    browser_loop_timer.timeout.connect(_tick_browser_loop)
    engine._screen1_browser_loop_timer = browser_loop_timer

    def _ensure_browser_loop_timer() -> None:
        sess = getattr(engine, "_screen1_session", None)
        if sess is not None and sess.browser_loop.is_active:
            if not browser_loop_timer.isActive():
                browser_loop_timer.start()

    engine._screen1_ensure_browser_loop_timer = _ensure_browser_loop_timer
    if hasattr(adapter, "set_on_browser_loop_started"):
        adapter.set_on_browser_loop_started(_ensure_browser_loop_timer)
    # Kick once so an already-active Loop (session restore) starts ticking.
    _ensure_browser_loop_timer()
    request_visible_browser_waveforms_from_window()
    if analysis_coordinator is not None:
        app.aboutToQuit.connect(analysis_coordinator.shutdown)
    return app, engine, root_window


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
