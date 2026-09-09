"""Optional production Screen-1 Qt Quick shell.

This module owns only renderer-facing state, interaction routing, and Qt engine
startup. It can be imported without PySide6; fixture, evidence, and synthetic
probe orchestration deliberately live in :mod:`src.workbench_qml_spike`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .workbench_controller import WorkbenchRow
from .workbench_harmony import HarmonicMatchLibraryController

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

    def qml_context(self) -> dict[str, object]:
        return {
            "panelCount": self.panel_count,
            "libraryLabels": list(self.library_labels),
            "selectedBrowserIndex": self.selected_browser_index,
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
        if not browser_has_focus:
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
        Rectangle { Layout.preferredWidth: 282; Layout.fillHeight: true; color: window.panel; border.color: window.border
            ColumnLayout { anchors.fill: parent; anchors.margins: 16
                Label { text: "LIBRARY"; color: window.muted; font.pixelSize: 12 }
                Repeater { model: window.screenData.libraryLabels
                    delegate: Label { text: "⌁  " + modelData; color: index === 2 ? window.accent : window.textColor; font.pixelSize: 15; Layout.topMargin: 10 }
                }
                Item { Layout.fillHeight: true }
                Label { text: "COLLECTIONS"; color: window.muted; font.pixelSize: 12 }
                Label { text: "All Samples\nMy Kits\nFavorites"; color: window.textColor; lineHeight: 1.8; font.pixelSize: 14 }
            }
        }
        Rectangle { Layout.fillWidth: true; Layout.fillHeight: true; color: "#0a0b0c"; border.color: window.border
            ColumnLayout { anchors.fill: parent; anchors.margins: 18; spacing: 10
                RowLayout { Layout.fillWidth: true
                    Label { text: "Samples  ›  Techno"; color: window.textColor; font.pixelSize: 16 }
                    Item { Layout.fillWidth: true }
                    Button {
                        objectName: "harmonicMatchButton"
                        text: window.interaction.harmonicMatchOpen ? "Close Harmonic Match" : "Harmonic Match"
                        onClicked: window.interaction.toggleHarmonicMatch()
                    }
                    TextField { objectName: "browserSearch"; placeholderText: "Search samples"; Layout.preferredWidth: 230 }
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


def _qml_interaction_bridge(adapter: Screen1QmlInteractionAdapter):
    """Expose the pure interaction adapter to QML only when Qt is installed."""
    from PySide6.QtCore import QObject, Property, Signal, Slot

    class QmlInteractionBridge(QObject):
        state_changed = Signal()

        @Property(int, notify=state_changed)
        def selectedBrowserIndex(self) -> int:
            return adapter.selected_browser_index

        @Property(bool, notify=state_changed)
        def harmonicMatchOpen(self) -> bool:
            return adapter.harmonic_match_open

        @Slot(int)
        def selectRow(self, index: int) -> None:
            adapter.select_row(index)
            self.state_changed.emit()

        @Slot(int)
        def navigateBrowser(self, step: int) -> None:
            direction = "next" if step > 0 else "previous"
            adapter.navigate_browser(direction, browser_has_focus=True)
            self.state_changed.emit()

        @Slot()
        def toggleHarmonicMatch(self) -> None:
            adapter.toggle_harmonic_match()
            self.state_changed.emit()

    return QmlInteractionBridge()


def _qml_engine(
    view_model: Screen1QmlViewModel,
    *,
    interaction_adapter: Screen1QmlInteractionAdapter | None = None,
):
    QUrl, QGuiApplication, QQmlApplicationEngine = _load_qt_modules()
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlApplicationEngine()
    adapter = interaction_adapter or Screen1QmlInteractionAdapter(
        view_model=view_model,
        harmony_controller=HarmonicMatchLibraryController(),
    )
    bridge = _qml_interaction_bridge(adapter)
    engine.rootContext().setContextProperty("screenModel", view_model.qml_context())
    engine.rootContext().setContextProperty("interactionModel", bridge)
    engine.loadData(QML_SOURCE.encode("utf-8"), QUrl("qrc:/screen1.qml"))
    if not engine.rootObjects():
        raise RuntimeError("Qt Quick Screen-1 Renderer konnte keine QML-Oberfläche laden.")
    # Keep both Python objects alive for the complete Qt engine lifetime.
    engine._screen1_interaction_adapter = adapter
    engine._screen1_interaction_bridge = bridge
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
    app, _engine, _window = _qml_engine(Screen1QmlViewModel.baseline(state_id))
    return app.exec()


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
