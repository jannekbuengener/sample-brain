"""Proof, fixture, and visual-acceptance harness for the production QML shell."""

from __future__ import annotations

from dataclasses import dataclass
import importlib
from pathlib import Path
import sys
from time import perf_counter
from typing import Callable, Mapping, Sequence

from . import workbench_qml as production
from .workbench_controller import WorkbenchRow
from .workbench_live_kit import LiveKitPresentationState, LiveKitState
from .workbench_visual_acceptance import (
    CLIENT_HEIGHT,
    CLIENT_WIDTH,
    EvidenceError,
    REQUIRED_STATE_IDS,
    Screen1VisualFixture,
    build_screen1_visual_fixture_v1,
    build_visual_evidence_manifest,
    capture_windows_client_window,
    current_windows_dpi_scale,
    validate_capture_sanity,
    validate_runtime_for_visual_acceptance,
    write_visual_evidence_manifest,
)

QML_SOURCE = production.QML_SOURCE
QmlBrowserRow = production.QmlBrowserRow
QmlLiveKitGroup = production.QmlLiveKitGroup
QmlLiveKitSlot = production.QmlLiveKitSlot
Screen1QmlInteractionAdapter = production.Screen1QmlInteractionAdapter
Screen1QmlViewModel = production.Screen1QmlViewModel
_qml_engine = production._qml_engine
_settle_qml_frame = production._settle_qml_frame
qml_runtime_available = production.qml_runtime_available


@dataclass(frozen=True)
class VirtualRowWindow:
    """Bounded synthetic-row hand-off used only by the virtualization probe."""

    rows: tuple[QmlBrowserRow, ...]
    first_index: int
    last_index: int
    total_rows: int


def build_qml_view_model_from_fixture(
    fixture: Screen1VisualFixture,
    state_id: str,
    *,
    on_browser_selected: Callable[[WorkbenchRow], None] | None = None,
) -> Screen1QmlViewModel:
    """Map the public #538 fixture onto the production renderer types."""
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
    return Screen1QmlViewModel(
        state_id=state_id,
        library_labels=fixture.library_labels,
        browser_rows=tuple(production._qml_row(row) for row in fixture.browser_rows),
        selected_browser_index=fixture.selected_browser_index,
        harmony_rows=tuple(
            production._qml_row(match.row) for match in fixture.harmony_results
        ),
        live_kit_groups=groups,
        on_browser_selected=on_browser_selected,
    )


def run_qml_proof_spike(*, state_id: str = "screen1-default-3panel") -> int:
    fixture = build_screen1_visual_fixture_v1()
    app, _engine, _window = _qml_engine(build_qml_view_model_from_fixture(fixture, state_id))
    return app.exec()


def virtual_row_window(
    rows: Sequence[WorkbenchRow],
    *,
    selected_index: int,
    visible_rows: int,
    cache_buffer_rows: int,
) -> VirtualRowWindow:
    if not rows:
        return VirtualRowWindow((), 0, -1, 0)
    if visible_rows <= 0 or cache_buffer_rows < 0:
        raise ValueError("Ungültige Virtualisierungsparameter.")
    selected_index = max(0, min(selected_index, len(rows) - 1))
    start = max(0, selected_index - visible_rows + 1 - cache_buffer_rows)
    end = min(len(rows), selected_index + 1 + cache_buffer_rows)
    return VirtualRowWindow(
        rows=tuple(production._qml_row(row) for row in rows[start:end]),
        first_index=start,
        last_index=end - 1,
        total_rows=len(rows),
    )


def run_qml_virtualization_probe(*, row_count: int = 50_000) -> dict[str, object]:
    """Measure the production shell with synthetic rows only."""
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
    baseline = build_qml_view_model_from_fixture(fixture, "screen1-default-3panel")
    view_model = Screen1QmlViewModel(
        state_id=baseline.state_id,
        library_labels=baseline.library_labels,
        browser_rows=tuple(production._qml_row(row) for row in rows),
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
        raise RuntimeError("Qt Quick Screen-1 Renderer findet die Browser-ListView nicht.")
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
    """Fail closed unless the production shell comes from the validated runtime."""
    from .runtime_provenance import evaluate_runtime

    root = Path(runtime_root).resolve()
    actual_executable = Path(executable or sys.executable).resolve()
    paths = dict(module_paths) if module_paths is not None else {
        "src.cli": _module_file("src.cli"),
        "src.workbench": _module_file("src.workbench"),
        "src.workbench_qml": _module_file("src.workbench_qml"),
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
        "src.workbench_qml",
        "src.workbench_visual_acceptance",
    ):
        module_path = paths.get(module_name)
        if module_path is None or not _is_within(module_path, root):
            raise EvidenceError(
                f"{module_name} stammt nicht aus dem Runtime-Root; Capture wird blockiert."
            )
    return report


def run_qml_visual_acceptance(*, runtime_root: Path, evidence_dir: Path) -> dict[str, object]:
    """Capture the #538 fixture states through the production QML shell."""
    import platform

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
                build_qml_view_model_from_fixture(fixture, state_id)
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
                build_qml_view_model_from_fixture(fixture, state_id).panel_count
                == (4 if state_id.endswith("4panel") else 3)
            )
            check["pass"] = bool(check["pass"] and check["panel_structure"])
            sanity[state_id] = check
            captures[state_id] = target
            window.close()
            app.processEvents()
        if app is None:
            raise RuntimeError("Qt Quick Screen-1 Renderer konnte keine Capture-Instanz starten.")
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
    "Screen1QmlInteractionAdapter",
    "Screen1QmlViewModel",
    "VirtualRowWindow",
    "build_qml_view_model_from_fixture",
    "qml_runtime_available",
    "run_qml_proof_spike",
    "run_qml_virtualization_probe",
    "run_qml_visual_acceptance",
    "validate_qml_renderer_provenance",
    "virtual_row_window",
]
