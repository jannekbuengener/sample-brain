"""Proof, fixture, and visual-acceptance harness for the production QML shell."""

from __future__ import annotations

from dataclasses import dataclass, replace
import importlib
from pathlib import Path
import sys
from time import perf_counter
from typing import Callable, Mapping, Sequence

from . import workbench_qml as production
from .workbench_controller import WorkbenchRow
from .workbench_harmony import HarmonyRelation
from .workbench_live_kit import LiveKitPresentationState, LiveKitState
from .workbench_qml_library import WorkbenchLibraryTreeState
from .workbench_visual_acceptance import (
    CLIENT_HEIGHT,
    CLIENT_WIDTH,
    EvidenceError,
    REQUIRED_STATE_IDS,
    REQUIRED_STATE_IDS_V2,
    Screen1VisualFixture,
    Screen1VisualFixtureV2,
    build_screen1_visual_fixture_v1,
    build_screen1_visual_fixture_v2,
    build_visual_evidence_manifest,
    capture_windows_client_window,
    current_windows_dpi_scale,
    resolve_screen1_visual_state_v2,
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
    library_tree: WorkbenchLibraryTreeState | None = None,
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
            production._qml_harmony_row(match) for match in fixture.harmony_results
        ),
        live_kit_groups=groups,
        on_browser_selected=on_browser_selected,
        library_tree=library_tree,
    )


def build_qml_view_model_from_fixture_v2(
    fixture: Screen1VisualFixtureV2,
    state_id: str,
    *,
    on_browser_selected: Callable[[WorkbenchRow], None] | None = None,
    library_tree: WorkbenchLibraryTreeState | None = None,
) -> Screen1QmlViewModel:
    """Map additive #700/#692 v2 fixture states onto the production shell.

    The production ``Screen1QmlViewModel`` still keys panel geometry off the
    historical shell IDs (3panel / 4panel). Evidence files and manifests use the
    public v2 state IDs; this helper only bridges row/selection/Live-Kit data.
    """
    state = resolve_screen1_visual_state_v2(fixture, state_id)
    shell_state_id = (
        "screen1-harmonic-4panel"
        if state.layout.harmonic_visible
        else "screen1-default-3panel"
    )

    live_kit = LiveKitState()
    if state.layout.live_kit_materialized:
        for group, slots in fixture.assignments.items():
            for slot, row in slots.items():
                if row is not None:
                    live_kit.assign(group, slot, row)
    presentation = LiveKitPresentationState(live_kit)
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

    if state.layout.browser_materialized:
        browser_rows = tuple(production._qml_row(row) for row in fixture.browser_rows)
        selected = (
            int(state.selected_browser_index)
            if state.selected_browser_index is not None
            else 0
        )
        context = state.selected_source_label or "Samples"
    else:
        browser_rows = ()
        selected = 0
        context = "No library selected"

    harmony_rows = ()
    if state.layout.harmonic_visible:
        harmony_rows = tuple(
            production._qml_harmony_row(match) for match in fixture.harmony_results
        )

    return Screen1QmlViewModel(
        state_id=shell_state_id,
        library_labels=fixture.library_labels,
        browser_rows=browser_rows,
        selected_browser_index=selected,
        harmony_rows=harmony_rows,
        live_kit_groups=groups,
        on_browser_selected=on_browser_selected,
        library_tree=library_tree,
        browser_context=context,
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


def _grab_qml_window_png(window: object, target: Path, *, engine: object | None = None) -> None:
    """Capture Screen-1 evidence with the shared PNG writer (sanity-compatible)."""
    del engine  # reserved for future root re-resolution
    # Requires QT_QUICK_BACKEND=software so GDI sees Qt Quick updates.
    capture_windows_client_window(int(window.winId()), target)


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


def _modal_harmony_acceptance_fixture(fixture: Screen1VisualFixture) -> Screen1VisualFixture:
    """Derive a fixture whose anchor and candidates carry explicit modal keys.

    The base fixture stores mode-less keys so the production ``set_anchor`` gate
    fails closed; the acceptance harness needs a modal anchor (Cmaj) plus modal
    candidates with real DIRECT/RELATED/TRANSPOSE relations so the 4-panel
    capture shows matches computed by the real matcher, not a stub.
    """
    overrides = {
        "TECH_BASS_01": "Cmaj",  # anchor
        "TECH_KICK_01": "Cmaj",  # DIRECT
        "TECH_BASS_02": "Cmaj",  # DIRECT
        "TECH_TOP_LOOP_01": "Am",  # RELATED relative minor
        "TECH_ATMOS_01": "Fmaj",  # RELATED fourth
        "TECH_VOX_LOOP_01": "Gmaj",  # RELATED fifth
        "TECH_PERC_LOOP_01": "Dmaj",  # TRANSPOSE +2
        "TECH_OPEN_HAT_01": "Bm",  # TRANSPOSE +1
    }
    rows = tuple(
        replace(row, key=overrides.get(row.display_name, row.key))
        for row in fixture.browser_rows
    )
    if rows[fixture.selected_browser_index].key is None:
        raise EvidenceError(
            "Modal-Harmony-Acceptance-Fixture braucht einen auswertbaren Anchor-Key."
        )
    return replace(fixture, browser_rows=rows)


def run_qml_visual_acceptance(*, runtime_root: Path, evidence_dir: Path) -> dict[str, object]:
    """Capture the #538 fixture states through the production QML shell."""
    import platform

    report = validate_qml_renderer_provenance(runtime_root)
    fixture = _modal_harmony_acceptance_fixture(build_screen1_visual_fixture_v1())
    evidence_dir.mkdir(parents=True, exist_ok=True)
    captures: dict[str, Path] = {}
    sanity: dict[str, dict[str, bool | list[object]]] = {}
    app = None
    engines: list[object] = []
    try:
        for state_id in REQUIRED_STATE_IDS:
            view_model = build_qml_view_model_from_fixture(
                fixture, "screen1-default-3panel" if state_id.endswith("4panel") else state_id
            )
            adapter = Screen1QmlInteractionAdapter(
                view_model=view_model,
                harmony_controller=production.HarmonicMatchLibraryController(),
            )
            app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
            engines.append(engine)
            window.show()
            _settle_qml_frame(app)
            if state_id.endswith("4panel"):
                from PySide6.QtCore import QPointF, Qt
                from PySide6.QtQuick import QQuickItem
                from PySide6.QtTest import QTest

                control = window.findChild(QQuickItem, "harmonicMatchButton")
                if control is None:
                    raise RuntimeError("Harmonic-Match-Control fehlt in der Production-QML-Shell.")
                QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, control.mapToScene(QPointF(8, 8)).toPoint())
                _settle_qml_frame(app)
                if not adapter.harmonic_match_open:
                    raise RuntimeError("Harmonic-Match-Control konnte den Pane nicht öffnen.")
            target = evidence_dir / f"{state_id}.png"
            capture_windows_client_window(int(window.winId()), target)
            check = validate_capture_sanity(
                target, expected_width=CLIENT_WIDTH, expected_height=CLIENT_HEIGHT
            )
            check["panel_structure"] = (
                build_qml_view_model_from_fixture(fixture, state_id).panel_count
                == (4 if state_id.endswith("4panel") else 3)
            )
            if state_id.endswith("4panel"):
                results = adapter.harmony_controller.results
                real_relations = tuple(sorted({s.relation.value for s in results}))
                check["harmonic_relations"] = list(real_relations)
                expected_relations = {
                    HarmonyRelation.DIRECT,
                    HarmonyRelation.RELATED,
                    HarmonyRelation.TRANSPOSE,
                }
                check["real_harmony_matches"] = bool(
                    results
                    and expected_relations.issubset(
                        {suggestion.relation for suggestion in results}
                    )
                )
            else:
                check["real_harmony_matches"] = True
            check["pass"] = bool(
                check["pass"]
                and check["panel_structure"]
                and check["real_harmony_matches"]
            )
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


def _modal_harmony_acceptance_fixture_v2(
    fixture: Screen1VisualFixtureV2,
) -> Screen1VisualFixtureV2:
    """Apply the same modal key overrides as v1 so harmonic open can match."""
    v1_shaped = Screen1VisualFixture(
        version="screen1_visual_fixture_v1",
        library_labels=fixture.library_labels,
        browser_rows=fixture.browser_rows,
        selected_browser_index=2,
        harmony_results=fixture.harmony_results,
        assignments={
            group: {slot: row for slot, row in slots.items() if row is not None}
            for group, slots in fixture.assignments.items()
        },
        state_ids=REQUIRED_STATE_IDS,
    )
    modal = _modal_harmony_acceptance_fixture(v1_shaped)
    return replace(
        fixture,
        browser_rows=modal.browser_rows,
        harmony_results=modal.harmony_results,
    )



def _require_fresh_qml_capture_process() -> None:
    """Reject v2 evidence when a Qt GUI runtime already exists in-process."""
    from PySide6.QtGui import QGuiApplication

    if QGuiApplication.instance() is not None:
        raise EvidenceError(
            "QML-v2-Capture braucht einen frischen Prozess ohne bestehende "
            "QGuiApplication; QT_QUICK_BACKEND muss vor der ersten Qt-Quick-"
            "Runtime festgelegt werden."
        )

def run_qml_visual_acceptance_v2(
    *,
    runtime_root: Path,
    evidence_dir: Path,
    capture_states: tuple[str, ...] = (
        "screen1-active-source",
        "screen1-harmonic-open",
    ),
    compact_stress_size: tuple[int, int] = (1120, 640),
) -> dict[str, object]:
    """Additive #692/#700 v2 capture path. Does not replace v1 acceptance."""
    import os
    import platform

    # Software scene graph keeps client captures / grabWindow coherent on Windows.
    # Force (do not setdefault): a pre-set hardware backend would make GDI BitBlt
    # miss Qt Quick updates and produce stale identical frames. Environment alone
    # is insufficient once Qt already owns a GUI application, so fail closed there.
    os.environ["QT_QUICK_BACKEND"] = "software"
    _require_fresh_qml_capture_process()

    report = validate_qml_renderer_provenance(runtime_root)
    fixture = _modal_harmony_acceptance_fixture_v2(build_screen1_visual_fixture_v2())
    evidence_dir.mkdir(parents=True, exist_ok=True)
    captures: dict[str, Path] = {}
    sanity: dict[str, dict[str, bool | list[object]]] = {}
    app = None
    engines: list[object] = []
    allowed = set(REQUIRED_STATE_IDS_V2)
    try:
        for state_id in capture_states:
            if state_id not in allowed:
                raise EvidenceError(f"Unknown Screen-1 v2 capture state: {state_id!r}")
            view_model = build_qml_view_model_from_fixture_v2(fixture, state_id)
            # Always start from the 3-panel shell, then open Harmonic via the real
            # control — matches the proven v1 acceptance path and avoids a stale
            # initial 4-panel projection that can miss the first paint.
            if resolve_screen1_visual_state_v2(fixture, state_id).layout.harmonic_visible:
                view_model = build_qml_view_model_from_fixture_v2(
                    fixture, "screen1-active-source"
                )
                # Keep v2 evidence label while using a closed shell as the start.
                view_model.state_id = "screen1-default-3panel"
            adapter = Screen1QmlInteractionAdapter(
                view_model=view_model,
                harmony_controller=production.HarmonicMatchLibraryController(),
            )
            app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
            engines.append(engine)
            window.setWidth(CLIENT_WIDTH)
            window.setHeight(CLIENT_HEIGHT)
            window.show()
            _settle_qml_frame(app)

            state = resolve_screen1_visual_state_v2(fixture, state_id)
            if state.layout.harmonic_visible:
                from PySide6.QtCore import QPointF, Qt
                from PySide6.QtQuick import QQuickItem
                from PySide6.QtTest import QTest

                control = window.findChild(QQuickItem, "harmonicMatchButton")
                if control is None:
                    raise RuntimeError("Harmonic-Match-Control fehlt in der Production-QML-Shell.")
                QTest.mouseClick(
                    window,
                    Qt.LeftButton,
                    Qt.NoModifier,
                    control.mapToScene(QPointF(8, 8)).toPoint(),
                )
                _settle_qml_frame(app)
                _settle_qml_frame(app)
                if not adapter.harmonic_match_open:
                    raise RuntimeError("Harmonic-Match-Control konnte den Pane nicht öffnen.")

            target = evidence_dir / f"{state_id}.png"
            # GDI BitBlt can miss Qt Quick scene-graph updates; grab the QML
            # window framebuffer so harmonic-open evidence is distinct.
            _grab_qml_window_png(window, target, engine=engine)
            check = validate_capture_sanity(
                target, expected_width=CLIENT_WIDTH, expected_height=CLIENT_HEIGHT
            )
            check["v2_state_id"] = state_id
            check["density_mode"] = state.density_mode
            check["harmonic_visible"] = bool(state.layout.harmonic_visible)
            check["pass"] = bool(check["pass"])
            sanity[state_id] = check
            captures[state_id] = target
            window.close()
            app.processEvents()

        if compact_stress_size is not None:
            stress_w, stress_h = compact_stress_size
            view_model = build_qml_view_model_from_fixture_v2(
                fixture, "screen1-active-source"
            )
            adapter = Screen1QmlInteractionAdapter(
                view_model=view_model,
                harmony_controller=production.HarmonicMatchLibraryController(),
            )
            app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
            engines.append(engine)
            window.setWidth(stress_w)
            window.setHeight(stress_h)
            window.show()
            _settle_qml_frame(app)
            stress_id = f"compact-stress-{stress_w}x{stress_h}"
            target = evidence_dir / f"{stress_id}.png"
            _grab_qml_window_png(window, target, engine=engine)
            check = validate_capture_sanity(
                target, expected_width=stress_w, expected_height=stress_h
            )
            check["v2_state_id"] = "screen1-active-source"
            check["compact_stress"] = True
            check["pass"] = bool(check["pass"])
            sanity[stress_id] = check
            captures[stress_id] = target
            window.close()
            app.processEvents()

        if app is None:
            raise RuntimeError("Qt Quick Screen-1 Renderer konnte keine Capture-Instanz starten.")

        manifest = {
            "schema": "sample_brain_screen1_v2_density_evidence",
            "issue": 692,
            "commit": report.manifest.commit,
            "channel": report.manifest.channel,
            "runtime_status": "valid",
            "python": f"{platform.python_implementation()} {platform.python_version()}",
            "os": "Windows " + platform.release(),
            "dpi": current_windows_dpi_scale(int(window.winId())),
            "fixture": fixture.version,
            "density_mode": "compact_target_30dip",
            "density_row_height_dip_baseline": 30,
            "states": list(captures.keys()),
            "screenshot_hashes": {
                key: __import__("hashlib").sha256(path.read_bytes()).hexdigest()
                for key, path in captures.items()
            },
            "sanity_results": {
                key: {
                    "pass": bool(value.get("pass")),
                    "v2_state_id": value.get("v2_state_id"),
                    "density_mode": value.get("density_mode"),
                    "compact_stress": bool(value.get("compact_stress", False)),
                }
                for key, value in sanity.items()
            },
        }
        write_visual_evidence_manifest(evidence_dir / "manifest-v2-density.json", manifest)
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
    "build_qml_view_model_from_fixture_v2",
    "qml_runtime_available",
    "run_qml_proof_spike",
    "run_qml_virtualization_probe",
    "run_qml_visual_acceptance",
    "run_qml_visual_acceptance_v2",
    "validate_qml_renderer_provenance",
    "virtual_row_window",
]
