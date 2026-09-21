"""Optional production Screen-1 Qt Quick shell.

This module owns only renderer-facing state, interaction routing, and Qt engine
startup. It can be imported without PySide6; fixture, evidence, and synthetic
probe orchestration deliberately live in :mod:`src.workbench_qml_spike`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .workbench_controller import WorkbenchRow
from .workbench_harmony import HarmonicMatchLibraryController
from .workbench_live_kit import LiveKitPresentationState, LiveKitState
from .workbench_library import workbench_library_db_path
from .workbench_library_navigation import LibraryNodeKind
from .workbench_qml_analysis import AnalysisUiState, create_qt_analysis_coordinator
from .workbench_qml_library import (
    WorkbenchLibraryTreeState,
    create_qt_library_tree_model,
)
from .workbench_qml_runtime import Screen1QmlRuntimeComposition

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
    waveform_pattern: str


@dataclass(frozen=True)
class QmlLiveKitSlot:
    name: str
    assignment: WorkbenchRow | None


@dataclass(frozen=True)
class QmlLiveKitGroup:
    name: str
    slots: tuple[QmlLiveKitSlot, ...]
    active: bool


def _row_details(row: WorkbenchRow) -> dict[str, object]:
    """Read the public renderer details attached to a Workbench row."""
    if row.details:
        return row.details
    if isinstance(row.error, dict):
        return row.error
    return {}


def _duration(row: WorkbenchRow) -> str:
    return str(_row_details(row).get("duration_sec", "—"))


def _pattern(row: WorkbenchRow) -> str:
    seed = int(_row_details(row).get("waveform_seed", "0"))
    patterns = ("▁▃▆▂▇▃▁", "▁▅▂▆▁▃▁", "▁▂▄▇▄▂▁", "▁▇▂▅▃▆▁")
    return patterns[seed % len(patterns)]


def _qml_row(row: WorkbenchRow) -> QmlBrowserRow:
    return QmlBrowserRow(
        source_row=row,
        display_name=row.display_name,
        sample_type=row.pred_type or "—",
        bpm="—" if row.bpm is None else f"{row.bpm:g}",
        key=row.key or "—",
        duration=_duration(row),
        waveform_pattern=_pattern(row),
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
        harmony_rows: tuple[QmlBrowserRow, ...],
        live_kit_groups: tuple[QmlLiveKitGroup, ...],
        on_browser_selected: Callable[[WorkbenchRow], None] | None = None,
        library_tree: WorkbenchLibraryTreeState | None = None,
        browser_context: str = "No library selected",
        browser_error: str | None = None,
    ) -> None:
        if state_id not in SCREEN1_QML_STATE_IDS:
            raise ValueError("Unbekannter Screen-1-QML-State.")
        self.state_id = state_id
        self.library_labels = library_labels
        self.browser_rows = browser_rows
        self.selected_browser_index = selected_browser_index
        self.harmony_rows = harmony_rows
        self.live_kit_groups = live_kit_groups
        self._on_browser_selected = on_browser_selected
        self.library_tree = library_tree or WorkbenchLibraryTreeState()
        self.browser_context = browser_context
        self.browser_error = browser_error
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
            "browserRows": [
                {
                    "name": row.display_name,
                    "type": row.sample_type,
                    "bpm": row.bpm,
                    "key": row.key,
                    "duration": row.duration,
                    "waveform": row.waveform_pattern,
                }
                for row in self.browser_rows
            ],
            "harmonyRows": [
                {"name": row.display_name, "type": row.sample_type, "key": row.key, "waveform": row.waveform_pattern}
                for row in self.harmony_rows
            ],
            "liveKitGroups": [
                {
                    "name": group.name,
                    "active": group.active,
                    "slots": [
                        {"name": slot.name, "assignment": slot.assignment.display_name if slot.assignment else "Empty"}
                        for slot in group.slots
                    ],
                }
                for group in self.live_kit_groups
            ],
        }


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
        liveKitGroupsChanged = Signal()
        panelCountChanged = Signal()

        @Property(list, notify=browserRowsChanged)
        def browserRows(self) -> list[dict[str, str]]:
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
        def harmonyRows(self) -> list[dict[str, str]]:
            return view_model.qml_context()["harmonyRows"]

        @Property(list, notify=liveKitGroupsChanged)
        def liveKitGroups(self) -> list[dict[str, object]]:
            return view_model.qml_context()["liveKitGroups"]

        @Property(int, notify=panelCountChanged)
        def panelCount(self) -> int:
            return view_model.panel_count

        @Slot()
        def refresh(self) -> None:
            self.browserRowsChanged.emit()
            self.selectedBrowserIndexChanged.emit()
            self.browserContextChanged.emit()
            self.errorMessageChanged.emit()
            self.analysisStatusChanged.emit()
            self.analysisProgressChanged.emit()
            self.analysisSourceChanged.emit()
            self.analysisErrorChanged.emit()
            self.harmonyRowsChanged.emit()
            self.liveKitGroupsChanged.emit()
            self.panelCountChanged.emit()

        @Slot()
        def cancelAnalysis(self) -> None:
            if on_cancel_analysis is not None:
                on_cancel_analysis()

    return QmlScreenDataBridge()


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
    ) -> None:
        self.view_model = view_model
        self.harmony_controller = harmony_controller
        self.harmonic_match_open = view_model.panel_count == 4

    @property
    def selected_browser_index(self) -> int:
        return self.view_model.selected_browser_index

    def select_row(self, index: int) -> WorkbenchRow:
        """Select exactly one authoritative row and dispatch its browse command."""
        return self.view_model.select_browser_index(index)

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
        return self.select_row(target)

    def toggle_harmonic_match(self) -> bool:
        """Open/close the existing harmony controller without mutating other state."""
        if self.harmonic_match_open:
            self.harmonic_match_open = False
            return False
        if not self.view_model.browser_rows:
            return False
        if not 0 <= self.view_model.selected_browser_index < len(self.view_model.browser_rows):
            return False
        if self.harmony_controller is not None:
            anchor = self.view_model.browser_rows[
                self.selected_browser_index
            ].source_row
            candidates = tuple(row.source_row for row in self.view_model.browser_rows)
            self.harmony_controller.set_anchor(anchor, candidates)
            self.view_model.harmony_rows = tuple(
                _qml_row(suggestion.row) for suggestion in self.harmony_controller.results
            )
        self.harmonic_match_open = True
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
                        Label { text: window.screenData.browserContext; color: window.textColor; font.pixelSize: 16 }
                        Label { visible: window.screenData.errorMessage.length > 0; text: window.screenData.errorMessage; color: window.accent; font.pixelSize: 11 }
                    }
                    Item { Layout.fillWidth: true }
                    Button {
                        objectName: "harmonicMatchButton"
                        text: window.interaction.harmonicMatchOpen ? "Close Harmonic Match" : "Harmonic Match"
                        onClicked: window.interaction.toggleHarmonicMatch()
                    }
                    TextField { objectName: "browserSearch"; placeholderText: "Search samples"; Layout.preferredWidth: 230; Layout.minimumWidth: 120 }
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
                RowLayout { Layout.fillWidth: true
                    Label { text: "WAVEFORM"; color: window.muted; Layout.preferredWidth: 44; font.pixelSize: 11 }
                    Label { text: "SAMPLE NAME"; color: window.muted; Layout.fillWidth: true; font.pixelSize: 11 }
                    Label { text: "BPM"; color: window.muted; Layout.preferredWidth: 42; font.pixelSize: 11 }
                    Label { text: "KEY"; color: window.muted; Layout.preferredWidth: 36; font.pixelSize: 11 }
                    Label { text: "LENGTH"; color: window.muted; Layout.preferredWidth: 55; font.pixelSize: 11 }
                }
                ListView { id: browser; objectName: "browserList"; Layout.fillWidth: true; Layout.fillHeight: true; model: window.screenData.browserRows; clip: true; reuseItems: true; focus: true
                    Keys.onPressed: function(event) {
                        if (event.key === Qt.Key_Down) { window.interaction.navigateBrowser(1); event.accepted = true }
                        else if (event.key === Qt.Key_Up) { window.interaction.navigateBrowser(-1); event.accepted = true }
                    }
                    delegate: Rectangle { width: browser.width; height: 58; color: index === window.interaction.selectedBrowserIndex ? "#211014" : "transparent"; border.color: index === window.interaction.selectedBrowserIndex ? window.accent : window.border
                        Component.onCompleted: window.browserDelegateCreations += 1
                        MouseArea { anchors.fill: parent; onClicked: { browser.forceActiveFocus(); window.interaction.selectRow(index) } }
                        RowLayout { anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12
                            Label { text: modelData.waveform; color: "#a7abb1"; Layout.preferredWidth: 190; font.pixelSize: 23 }
                            ColumnLayout { Layout.fillWidth: true
                                Label { text: modelData.name; color: window.textColor; font.pixelSize: 14 }
                                Label { text: modelData.type; color: window.muted; font.pixelSize: 11 }
                            }
                            Label { text: modelData.bpm; color: window.textColor; Layout.preferredWidth: 42 }
                            Label { text: modelData.key; color: window.textColor; Layout.preferredWidth: 36 }
                            Label { text: modelData.duration; color: window.textColor; Layout.preferredWidth: 55 }
                            Label { text: "+"; color: window.accent; font.pixelSize: 24 }
                        }
                    }
                }
            }
        }
        Rectangle { visible: window.interaction.harmonicMatchOpen; Layout.preferredWidth: visible ? 300 : 0; Layout.fillHeight: true; color: window.panel; border.color: window.border
            ColumnLayout { anchors.fill: parent; anchors.margins: 14
                Label { text: "Harmonic Matches"; color: window.textColor; font.pixelSize: 18; font.bold: true }
                Label { text: "Reference: TECH_BASS_01 · F#"; color: window.muted; font.pixelSize: 12 }
                ListView { Layout.fillWidth: true; Layout.fillHeight: true; model: window.screenData.harmonyRows; clip: true; reuseItems: true
                    delegate: Rectangle { width: parent.width; height: 64; color: "transparent"; border.color: window.border
                        RowLayout { anchors.fill: parent; anchors.margins: 9
                            Label { text: modelData.waveform; color: "#a7abb1"; font.pixelSize: 18 }
                            ColumnLayout { Layout.fillWidth: true
                                Label { text: modelData.name; color: window.textColor }
                                Label { text: modelData.type; color: window.muted; font.pixelSize: 11 }
                            }
                            Label { text: modelData.key; color: window.accent }
                        }
                    }
                }
            }
        }
        Rectangle { Layout.preferredWidth: 300; Layout.fillHeight: true; color: window.panel; border.color: window.border
            ColumnLayout { anchors.fill: parent; anchors.margins: 14
                Label { text: "LIVE KIT"; color: window.muted; font.pixelSize: 12 }
                Repeater { model: window.screenData.liveKitGroups
                    delegate: Rectangle { Layout.fillWidth: true; implicitHeight: modelData.active ? 212 : 52; color: "transparent"; border.color: modelData.active ? window.accent : window.border
                        ColumnLayout { anchors.fill: parent; anchors.margins: 10
                            Label { text: (index + 1) + "  " + modelData.name; color: window.textColor; font.pixelSize: 16 }
                            Repeater { model: modelData.active ? modelData.slots : []
                                delegate: RowLayout { Layout.fillWidth: true
                                    Label { text: modelData.name; color: window.textColor; Layout.fillWidth: true }
                                    Label { text: modelData.assignment; color: modelData.assignment === "Empty" ? window.muted : window.accent; font.pixelSize: 11 }
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
):
    """Expose the pure interaction adapter to QML only when Qt is installed."""
    from PySide6.QtCore import QObject, Property, Signal, Slot

    class QmlInteractionBridge(QObject):
        state_changed = Signal()

        def _refresh(self) -> None:
            if on_state_changed is not None:
                on_state_changed()
            self.state_changed.emit()

        @Property(int, notify=state_changed)
        def selectedBrowserIndex(self) -> int:
            return adapter.selected_browser_index

        @Property(bool, notify=state_changed)
        def harmonicMatchOpen(self) -> bool:
            return adapter.harmonic_match_open

        @Slot(int)
        def selectRow(self, index: int) -> None:
            adapter.select_row(index)
            self._refresh()

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
    adapter = interaction_adapter or Screen1QmlInteractionAdapter(
        view_model=view_model,
        harmony_controller=HarmonicMatchLibraryController(),
    )
    library_model = create_qt_library_tree_model(view_model.library_tree)

    def refresh_screen_model() -> None:
        screen_model.refresh()

    analysis_coordinator = None

    def apply_analysis_state(state: AnalysisUiState) -> None:
        view_model.set_analysis_state(state)
        refresh_screen_model()

    def dispatch_library_selection() -> None:
        if runtime_composition is None:
            return
        intent = library_model.state.selection_intent
        if intent is None:
            runtime_composition.clear_no_scope()
            view_model.set_browser_state(
                rows=(),
                selected_index=-1,
                browser_context="No library selected",
                error="Library-Auswahl konnte nicht aufgelöst werden.",
            )
        else:
            state = runtime_composition.dispatch_selection(intent)
            view_model.set_browser_state(
                rows=state.rows,
                selected_index=state.selected_index,
                browser_context=state.browser_context,
                error=state.error,
            )
        refresh_screen_model()

    def finish_analysis(folder_id: int, _result: object) -> None:
        library_model.replaceBranch("container:sample-sources")
        if library_model.selectNode(f"root:{folder_id}"):
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
            library_model.selectNode(f"root:{registration.folder_id}")
            dispatch_library_selection()
            if analysis_coordinator is not None:
                analysis_coordinator.start(
                    registration.folder_id,
                    str(registration.normalized_path),
                )
        refresh_screen_model()
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
    bridge = _qml_interaction_bridge(adapter, on_state_changed=refresh_screen_model)
    library_bridge = _qml_library_interaction_bridge(
        library_model,
        on_selection=dispatch_library_selection,
        on_add_source=register_source,
        on_prepare_remove=prepare_remove,
        on_confirm_remove=confirm_remove,
    )
    engine.rootContext().setContextProperty("screenModel", screen_model)
    engine.rootContext().setContextProperty("interactionModel", bridge)
    engine.rootContext().setContextProperty("libraryTreeModel", library_model)
    engine.rootContext().setContextProperty("libraryInteraction", library_bridge)
    engine.loadData(QML_SOURCE.encode("utf-8"), QUrl("qrc:/screen1.qml"))
    if not engine.rootObjects():
        raise RuntimeError("Qt Quick Screen-1 Renderer konnte keine QML-Oberfläche laden.")
    # Keep both Python objects alive for the complete Qt engine lifetime.
    engine._screen1_interaction_adapter = adapter
    engine._screen1_interaction_bridge = bridge
    engine._screen1_library_model = library_model
    engine._screen1_library_bridge = library_bridge
    engine._screen1_screen_model = screen_model
    engine._screen1_runtime_composition = runtime_composition
    engine._screen1_analysis_coordinator = analysis_coordinator
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
        coordinator = getattr(_engine, "_screen1_analysis_coordinator", None)
        if coordinator is not None:
            coordinator.close()


__all__ = [
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
