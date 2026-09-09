"""Optional Qt Quick proof-of-fidelity surface for Screen 1.

This module deliberately owns presentation only.  It can be imported without
PySide6 so the established CLI and Tk workbench stay dependency-compatible.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib
from pathlib import Path
import sys
from time import perf_counter
from typing import Callable, Mapping, Sequence

from .workbench_controller import WorkbenchRow
from .workbench_harmony import HarmonicMatchLibraryController
from .workbench_live_kit import LiveKitPresentationState, LiveKitState
from .workbench_visual_acceptance import (
    EvidenceError,
    REQUIRED_STATE_IDS,
    Screen1VisualFixture,
    build_screen1_visual_fixture_v1,
)


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


@dataclass(frozen=True)
class VirtualRowWindow:
    """Bounded data hand-off; QML remains responsible for delegate recycling."""

    rows: tuple[QmlBrowserRow, ...]
    first_index: int
    last_index: int
    total_rows: int


def _row_details(row: WorkbenchRow) -> dict[str, object]:
    """Read the current row contract and the public fixture's legacy payload."""
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
        if state_id not in REQUIRED_STATE_IDS:
            raise ValueError("Unbekannter Screen-1-Acceptance-State.")
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
    def from_fixture(
        cls,
        fixture: Screen1VisualFixture,
        state_id: str,
        *,
        on_browser_selected: Callable[[WorkbenchRow], None] | None = None,
    ) -> "Screen1QmlViewModel":
        state = LiveKitState()
        for group, slots in fixture.assignments.items():
            for slot, row in slots.items():
                state.assign(group, slot, row)
        presentation = LiveKitPresentationState(state)
        groups = tuple(
            QmlLiveKitGroup(
                name=group.name,
                slots=tuple(
                    QmlLiveKitSlot(slot.name, slot.assignment) for slot in group.slots
                ),
                active=not presentation.is_collapsed(group.name),
            )
            for group in presentation.visible_structure()
        )
        return cls(
            state_id=state_id,
            library_labels=fixture.library_labels,
            browser_rows=tuple(_qml_row(row) for row in fixture.browser_rows),
            selected_browser_index=fixture.selected_browser_index,
            harmony_rows=tuple(_qml_row(match.row) for match in fixture.harmony_results),
            live_kit_groups=groups,
            on_browser_selected=on_browser_selected,
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


def virtual_row_window(
    rows: Sequence[WorkbenchRow],
    *,
    selected_index: int,
    visible_rows: int,
    cache_buffer_rows: int,
) -> VirtualRowWindow:
    """Return only a bounded row range centred on the selected item."""
    if not rows:
        return VirtualRowWindow((), 0, -1, 0)
    if visible_rows <= 0 or cache_buffer_rows < 0:
        raise ValueError("Ungültige Virtualisierungsparameter.")
    selected_index = max(0, min(selected_index, len(rows) - 1))
    start = max(0, selected_index - visible_rows + 1 - cache_buffer_rows)
    end = min(len(rows), selected_index + 1 + cache_buffer_rows)
    return VirtualRowWindow(
        rows=tuple(_qml_row(row) for row in rows[start:end]),
        first_index=start,
        last_index=end - 1,
        total_rows=len(rows),
    )


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
    title: "Sample Brain — Qt Quick proof spike"
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
                Rectangle { Layout.fillWidth: true; height: 46; color: window.accent
                    Label { anchors.centerIn: parent; text: "LIVE KIT READY"; color: "white"; font.bold: true }
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
            "Qt Quick Proof Spike benötigt die optionale Abhängigkeit: pip install -e '.[qtquick]'"
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
    engine.loadData(QML_SOURCE.encode("utf-8"), QUrl("qrc:/screen1-qml-spike.qml"))
    if not engine.rootObjects():
        raise RuntimeError("Qt Quick Proof Spike konnte keine QML-Oberfläche laden.")
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


def run_qml_proof_spike(*, state_id: str = "screen1-default-3panel") -> int:
    """Open the opt-in QML renderer without touching the Tk launcher."""
    from .workbench_visual_acceptance import build_screen1_visual_fixture_v1

    fixture = build_screen1_visual_fixture_v1()
    app, _engine, _window = _qml_engine(Screen1QmlViewModel.from_fixture(fixture, state_id))
    return app.exec()


def run_qml_virtualization_probe(*, row_count: int = 50_000) -> dict[str, object]:
    """Measure the optional QML ListView with synthetic, non-audio rows only."""
    if row_count <= 0:
        raise ValueError("row_count muss positiv sein.")
    rows = tuple(
        WorkbenchRow(
            display_name=f"SYNTH_{index:05d}",
            relative_path=f"fixture/SYNTH_{index:05d}.wav",
            path=f"fixture/SYNTH_{index:05d}.wav",
            bpm=132.0,
            key=None,
            key_conf=None,
            loudness=None,
            brightness=None,
            sample_class="one_shot",
            pred_type="Kick",
            status="ok",
        )
        for index in range(row_count)
    )
    fixture = build_screen1_visual_fixture_v1()
    baseline = Screen1QmlViewModel.from_fixture(
        fixture, "screen1-default-3panel"
    )
    view_model = Screen1QmlViewModel(
        state_id=baseline.state_id,
        library_labels=baseline.library_labels,
        browser_rows=tuple(_qml_row(row) for row in rows),
        selected_browser_index=0,
        harmony_rows=baseline.harmony_rows,
        live_kit_groups=baseline.live_kit_groups,
    )
    start = perf_counter()
    app, _engine, window = _qml_engine(view_model)
    app.processEvents()
    initial_ms = (perf_counter() - start) * 1000
    from PySide6.QtCore import QObject

    browser = window.findChild(QObject, "browserList")
    if browser is None:
        raise RuntimeError("Qt Quick Proof Spike findet die Browser-ListView nicht.")
    scroll_start = perf_counter()
    browser.setProperty(
        "contentY",
        max(0, float(browser.property("contentHeight")) - float(browser.property("height"))),
    )
    app.processEvents()
    scroll_ms = (perf_counter() - scroll_start) * 1000
    created = int(window.property("browserDelegateCreations"))
    window.close()
    return {
        "row_count": row_count,
        "initial_display_ms": round(initial_ms, 3),
        "scroll_ms": round(scroll_ms, 3),
        "delegate_creations": created,
        "virtualized": created < row_count,
    }


def _module_file(module_name: str) -> Path:
    module = importlib.import_module(module_name)
    location = getattr(module, "__file__", None)
    if location is None:
        raise EvidenceError(f"Import-Provenance für {module_name} fehlt.")
    return Path(location).resolve()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def validate_qml_renderer_provenance(
    runtime_root: Path,
    *,
    manifest_path: Path | None = None,
    executable: Path | None = None,
    module_paths: Mapping[str, Path] | None = None,
    git_run=None,
):
    """Fail closed unless this QML process is the validated runtime build."""
    from .runtime_provenance import evaluate_runtime
    from .workbench_visual_acceptance import (
        validate_runtime_for_visual_acceptance,
    )

    root = Path(runtime_root).resolve()
    actual_executable = Path(executable or sys.executable).resolve()
    paths = dict(module_paths) if module_paths is not None else {
        "src.cli": _module_file("src.cli"),
        "src.workbench": _module_file("src.workbench"),
        "src.workbench_qml_spike": _module_file("src.workbench_qml_spike"),
        "src.workbench_visual_acceptance": _module_file(
            "src.workbench_visual_acceptance"
        ),
    }
    report = evaluate_runtime(
        root,
        manifest_path=manifest_path,
        executable=actual_executable,
        module_paths=paths,
        git_run=git_run,
    )
    validate_runtime_for_visual_acceptance(report)
    if not _is_within(actual_executable, root / ".venv"):
        raise EvidenceError(
            "QML-Renderer-Interpreter liegt nicht unter Runtime-.venv; Capture wird blockiert."
        )
    for module_name in (
        "src.cli",
        "src.workbench_qml_spike",
        "src.workbench_visual_acceptance",
    ):
        module_path = paths.get(module_name)
        if module_path is None or not _is_within(module_path, root):
            raise EvidenceError(
                f"{module_name} stammt nicht aus dem Runtime-Root; Capture wird blockiert."
            )
    return report


def run_qml_visual_acceptance(*, runtime_root: Path, evidence_dir: Path) -> dict[str, object]:
    """Capture the two #538 states from the opt-in QML renderer."""
    import platform

    from .workbench_visual_acceptance import (
        CLIENT_HEIGHT,
        CLIENT_WIDTH,
        build_screen1_visual_fixture_v1,
        build_visual_evidence_manifest,
        capture_windows_client_window,
        current_windows_dpi_scale,
        validate_capture_sanity,
        write_visual_evidence_manifest,
    )

    report = validate_qml_renderer_provenance(runtime_root)
    fixture = build_screen1_visual_fixture_v1()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    captures: dict[str, Path] = {}
    sanity: dict[str, dict[str, bool]] = {}
    app = None
    engines: list[object] = []
    try:
        for state_id in REQUIRED_STATE_IDS:
            app, engine, window = _qml_engine(
                Screen1QmlViewModel.from_fixture(fixture, state_id)
            )
            engines.append(engine)
            window.show()
            _settle_qml_frame(app)
            target = evidence_dir / f"{state_id}.png"
            capture_windows_client_window(int(window.winId()), target)
            check = validate_capture_sanity(
                target, expected_width=CLIENT_WIDTH, expected_height=CLIENT_HEIGHT
            )
            check["panel_structure"] = (
                Screen1QmlViewModel.from_fixture(fixture, state_id).panel_count
                == (4 if state_id.endswith("4panel") else 3)
            )
            check["pass"] = bool(check["pass"] and check["panel_structure"])
            sanity[state_id] = check
            captures[state_id] = target
            window.close()
            app.processEvents()
        if app is None:
            raise RuntimeError("Qt Quick Proof Spike konnte keine Capture-Instanz starten.")
        manifest = build_visual_evidence_manifest(
            runtime_report=report,
            fixture=fixture,
            captures=captures,
            os_name="Windows " + platform.release(),
            dpi_scale=current_windows_dpi_scale(int(window.winId())),
            client_width=CLIENT_WIDTH,
            client_height=CLIENT_HEIGHT,
            sanity_results=sanity,
        )
        write_visual_evidence_manifest(evidence_dir / "manifest.json", manifest)
        return manifest
    finally:
        engines.clear()


__all__ = [
    "QML_SOURCE",
    "QmlBrowserRow",
    "QmlLiveKitGroup",
    "QmlLiveKitSlot",
    "Screen1QmlViewModel",
    "VirtualRowWindow",
    "qml_runtime_available",
    "run_qml_proof_spike",
    "run_qml_visual_acceptance",
    "run_qml_virtualization_probe",
    "validate_qml_renderer_provenance",
    "virtual_row_window",
]
