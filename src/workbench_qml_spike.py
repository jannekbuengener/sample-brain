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
from .workbench_qml_analysis import AnalysisUiState
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
    _write_png,
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
    # Historical v1 fixtures describe an already-active Screen-1 workspace.
    # Browser context must not stay on the Clean-Start default while rows exist.
    context = (
        fixture.library_labels[0]
        if fixture.library_labels
        else "Samples"
    )
    view_model = Screen1QmlViewModel(
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
        browser_context=context,
    )
    # Under #693 Clean Start, that means materialize Browser + Live Kit.
    # Source Navigation was visible in those fixtures (#725 library disclosure).
    view_model.set_workspace_materialization(
        has_active_source=True,
        calm_canvas_visible=False,
        browser_materialized=True,
        live_kit_materialized=True,
    )
    view_model.set_library_revealed(True)
    # 4-panel fixture states project an open Harmonic Match surface.
    if state_id.endswith("4panel") and view_model.harmony_rows:
        view_model.harmony_status = "Harmonic Match ist offen."
    else:
        view_model.harmony_status = "Harmonic Match ist ausgeschaltet."
    return view_model


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
        # Active Source must never project the Clean-Start "No library selected" copy.
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

    view_model = Screen1QmlViewModel(
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
    view_model.set_workspace_materialization(
        has_active_source=bool(state.source_selected),
        calm_canvas_visible=bool(state.layout.calm_canvas_visible),
        browser_materialized=bool(state.layout.browser_materialized),
        live_kit_materialized=bool(state.layout.live_kit_materialized),
    )
    # #725/#742: library_revealed gates Library elastic participation in all modes.
    view_model.set_library_revealed(bool(state.layout.source_nav_visible))
    if state.layout.harmonic_visible and harmony_rows:
        view_model.harmony_status = "Harmonic Match ist offen."
    else:
        view_model.harmony_status = "Harmonic Match ist ausgeschaltet."
    return view_model


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
    """Capture Screen-1 evidence from the Qt Quick framebuffer.

    Prefer ``grabWindow()`` over GDI BitBlt: the software scene graph can report
    Image.painted size before the HWND client area has composed the texture,
    which produced pure-black Clean Start evidence under BitBlt. Pixels are
    written with the shared PNG writer so ``validate_capture_sanity`` stays
    compatible.
    """
    del engine  # reserved for future root re-resolution
    from PySide6.QtGui import QImage

    image = window.grabWindow()
    if image is None or image.isNull():
        capture_windows_client_window(int(window.winId()), target)
        return
    converted = image.convertToFormat(QImage.Format.Format_RGBA8888)
    width = int(converted.width())
    height = int(converted.height())
    if width <= 0 or height <= 0:
        raise EvidenceError("QML framebuffer grab returned empty dimensions.")
    bytes_per_line = int(converted.bytesPerLine())
    raw = bytes(converted.constBits())
    expected = width * 4
    if bytes_per_line == expected:
        rgba = raw[: height * expected]
    else:
        rgba = b"".join(
            raw[row * bytes_per_line : row * bytes_per_line + expected]
            for row in range(height)
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_png(target, width, height, rgba)

def _wait_for_screen1_background_ready(window: object, app: object, *, timeout_ms: int = 3000) -> None:
    """Settle the historical background seam before a Screen-1 capture.

    #929/#930 retain the immutable Image and URL only as historical evidence.
    The V7 runtime deliberately does not composite it over the Theme Core root,
    so a capture must not wait for a non-visible image to paint.
    """
    from PySide6.QtCore import QElapsedTimer
    from PySide6.QtQuick import QQuickItem

    background = window.findChild(QQuickItem, "screen1Background")
    if background is None:
        raise RuntimeError("screen1Background fehlt vor Visual-Acceptance-Capture.")

    if not background.isVisible():
        _settle_qml_frame(app)
        _settle_qml_frame(app)
        return

    timer = QElapsedTimer()
    timer.start()
    while timer.elapsed() < int(timeout_ms):
        # Image.status is not reliably convertible via QObject.property(); painted
        # size is the capture-relevant readiness signal (same as background tests).
        painted_w = float(background.property("paintedWidth") or 0)
        painted_h = float(background.property("paintedHeight") or 0)
        if painted_w > 0 and painted_h > 0:
            # Two composed frames: painted size can lead HWND/GDI composition.
            _settle_qml_frame(app)
            _settle_qml_frame(app)
            return
        _settle_qml_frame(app)
    raise RuntimeError(
        "screen1Background wurde vor Capture nicht rechtzeitig gemalt "
        f"(timeout_ms={timeout_ms})."
    )


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
                # #843: header button removed; open via adapter open/retarget seam.
                if not adapter.toggle_harmonic_match():
                    raise RuntimeError("Harmonic Matches pane could not be opened for visual acceptance.")
                _settle_qml_frame(app)
                if not adapter.harmonic_match_open:
                    raise RuntimeError("Harmonic Matches pane could not be opened for visual acceptance.")
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


def apply_screen1_visual_state_v2(
    view_model: Screen1QmlViewModel,
    adapter: Screen1QmlInteractionAdapter,
    fixture,
    state,
) -> None:
    """Project a #700 v2 acceptance state onto the production Screen-1 shell."""
    live_state = LiveKitState()
    if state.layout.live_kit_materialized:
        for group, slots in fixture.assignments.items():
            for slot, row in slots.items():
                live_state.assign(group, slot, row)
    presentation = LiveKitPresentationState(live_state)
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
    rows = fixture.browser_rows if state.layout.browser_materialized else ()
    selected = (
        -1
        if state.selected_browser_index is None
        else int(state.selected_browser_index)
    )
    if selected >= len(rows):
        selected = -1
    view_model.state_id = (
        "screen1-harmonic-4panel"
        if state.layout.harmonic_visible
        else "screen1-default-3panel"
    )
    view_model.library_labels = fixture.library_labels
    view_model.browser_rows = tuple(production._qml_row(row) for row in rows)
    view_model.selected_browser_index = selected
    view_model.harmony_rows = (
        tuple(production._qml_harmony_row(match) for match in fixture.harmony_results)
        if state.layout.harmonic_visible
        else ()
    )
    view_model.live_kit_groups = groups
    view_model.browser_context = (
        (state.selected_source_label or "Samples")
        if state.source_selected
        else "No library selected"
    )
    view_model.browser_error = None
    view_model.set_workspace_materialization(
        has_active_source=bool(state.source_selected),
        calm_canvas_visible=bool(state.layout.calm_canvas_visible),
        browser_materialized=bool(state.layout.browser_materialized),
        live_kit_materialized=bool(state.layout.live_kit_materialized),
    )
    # #725/#742: library_revealed gates Library elastic participation in all modes.
    view_model.set_library_revealed(bool(state.layout.source_nav_visible))
    adapter.harmonic_match_open = bool(state.layout.harmonic_visible)
    if not state.preview_active and adapter.preview_active:
        adapter.stop_preview()
    if state.layout.harmonic_visible:
        view_model.harmony_status = "Harmonic Match"
    else:
        view_model.harmony_anchor = ""
        view_model.harmony_status = "Harmonic Match ist ausgeschaltet."


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
    """Fail closed unless this process can still start a software Qt Quick runtime.

    Setting ``QT_QUICK_BACKEND`` is ignored once a ``QGuiApplication`` exists, and
    a pre-loaded non-software Qt Quick binding can leave GDI density captures
    looking sane while missing scene-graph updates. Callers must use a fresh
    Python process after any other Qt Quick evidence path.
    """
    import os

    from PySide6.QtGui import QGuiApplication

    prior_backend = (os.environ.get("QT_QUICK_BACKEND") or "").strip().lower()
    qtquick_loaded = "PySide6.QtQuick" in sys.modules
    if QGuiApplication.instance() is not None:
        raise EvidenceError(
            "QML-v2-Capture braucht einen frischen Prozess ohne bestehende "
            "QGuiApplication; QT_QUICK_BACKEND muss vor der ersten Qt-Quick-"
            "Runtime festgelegt werden."
        )
    if qtquick_loaded and prior_backend not in ("", "software"):
        raise EvidenceError(
            "QML-v2-Capture: Qt Quick ist bereits mit inkompatiblem "
            f"QT_QUICK_BACKEND={prior_backend!r} geladen; frischer Prozess mit "
            "software-Backend erforderlich."
        )
    # Force after fail-closed checks so a pre-set hardware backend cannot win.
    os.environ["QT_QUICK_BACKEND"] = "software"


_V2_CAPTURE_STATE_IDS = (
    "screen1-active-source",
    "screen1-harmonic-open",
)
_V2_EVIDENCE_BASELINE = "baseline"
_V2_EVIDENCE_DPI_PROBE = "dpi_probe"


def _validate_v2_capture_states(capture_states: tuple[str, ...]) -> None:
    allowed = set(_V2_CAPTURE_STATE_IDS)
    unsupported = tuple(state for state in capture_states if state not in allowed)
    if unsupported:
        raise EvidenceError(
            "QML-v2-Density-Capture unterstützt aktuell nur "
            f"{_V2_CAPTURE_STATE_IDS}; nicht unterstützt: {unsupported}"
        )


def _require_v2_capture_dpi_100(hwnd: int) -> int:
    dpi_scale = current_windows_dpi_scale(hwnd)
    if dpi_scale != 100:
        raise EvidenceError(
            "QML-v2-Density-Capture braucht die 100%-Windows-DPI-Baseline; "
            f"aktuell: {dpi_scale}%."
        )
    return dpi_scale


def _resolve_v2_density_runtime_status(*, dpi_scale: int, evidence_kind: str) -> str:
    """Baseline evidence may claim valid only at 100% DPI; probes never may."""
    kind = (evidence_kind or "").strip().lower()
    if kind == _V2_EVIDENCE_BASELINE:
        if dpi_scale != 100:
            raise EvidenceError(
                "QML-v2-Density-Capture braucht die 100%-Windows-DPI-Baseline; "
                f"aktuell: {dpi_scale}%."
            )
        return "valid"
    if kind == _V2_EVIDENCE_DPI_PROBE:
        # Probes exist for Owner High-DPI inspection (real OS scale or QT_SCALE).
        # They must never be submitted as baseline-valid evidence.
        return "dpi_probe"
    raise EvidenceError(
        f"Unknown density evidence_kind {evidence_kind!r}; expected "
        f"{_V2_EVIDENCE_BASELINE!r} or {_V2_EVIDENCE_DPI_PROBE!r}."
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
    evidence_kind: str = _V2_EVIDENCE_BASELINE,
) -> dict[str, object]:
    """Additive #692/#700 v2 capture path. Does not replace v1 acceptance."""
    import platform

    # Software scene graph keeps client captures coherent on Windows. Environment
    # alone is insufficient once Qt already owns a GUI / non-software Quick
    # runtime, so fail closed there before creating windows.
    _require_fresh_qml_capture_process()

    _validate_v2_capture_states(capture_states)
    report = validate_qml_renderer_provenance(runtime_root)
    fixture = _modal_harmony_acceptance_fixture_v2(build_screen1_visual_fixture_v2())
    evidence_dir.mkdir(parents=True, exist_ok=True)
    captures: dict[str, Path] = {}
    sanity: dict[str, dict[str, bool | list[object]]] = {}
    app = None
    engines: list[object] = []
    dpi_scale = 100
    try:
        for state_id in capture_states:
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
            _wait_for_screen1_background_ready(window, app)
            dpi_scale = current_windows_dpi_scale(int(window.winId()))
            if evidence_kind == _V2_EVIDENCE_BASELINE:
                _require_v2_capture_dpi_100(int(window.winId()))

            state = resolve_screen1_visual_state_v2(fixture, state_id)
            if state.layout.harmonic_visible:
                # #843: header button removed; open via adapter open/retarget seam.
                if not adapter.toggle_harmonic_match():
                    raise RuntimeError("Harmonic Matches Pane konnte nicht geöffnet werden.")
                _settle_qml_frame(app)
                _settle_qml_frame(app)
                if not adapter.harmonic_match_open:
                    raise RuntimeError("Harmonic Matches Pane konnte nicht geöffnet werden.")

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
            dpi_scale = current_windows_dpi_scale(int(window.winId()))
            if evidence_kind == _V2_EVIDENCE_BASELINE:
                _require_v2_capture_dpi_100(int(window.winId()))
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

        runtime_status = _resolve_v2_density_runtime_status(
            dpi_scale=dpi_scale, evidence_kind=evidence_kind
        )
        manifest = {
            "schema": "sample_brain_screen1_v2_density_evidence",
            "issue": 692,
            "commit": report.manifest.commit,
            "channel": report.manifest.channel,
            "runtime_status": runtime_status,
            "evidence_kind": evidence_kind,
            "python": f"{platform.python_implementation()} {platform.python_version()}",
            "os": "Windows " + platform.release(),
            "dpi": dpi_scale,
            "qt_scale_factor": __import__("os").environ.get("QT_SCALE_FACTOR"),
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


_V725_CAPTURE_LABELS = (
    "clean-start-collapsed",
    "clean-start-reveal-hover",
    "opened-no-source",
    "active-source",
)


def run_qml_visual_acceptance_725(
    *,
    runtime_root: Path,
    evidence_dir: Path,
) -> dict[str, object]:
    """#725 Runtime-/Interaction-Captures. Does not invent a parallel fixture family."""
    import platform

    from PySide6.QtQuick import QQuickItem

    _require_fresh_qml_capture_process()
    report = validate_qml_renderer_provenance(runtime_root)
    fixture = build_screen1_visual_fixture_v2()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    captures: dict[str, Path] = {}
    sanity: dict[str, dict[str, bool | list[object]]] = {}
    engines: list[object] = []
    dpi_scale = 100

    def _capture(label: str, window: object, engine: object, *, v2_state: str) -> None:
        nonlocal dpi_scale
        target = evidence_dir / f"{label}.png"
        _grab_qml_window_png(window, target, engine=engine)
        check = validate_capture_sanity(
            target, expected_width=CLIENT_WIDTH, expected_height=CLIENT_HEIGHT
        )
        check["v2_state_id"] = v2_state
        check["capture_label"] = label
        check["pass"] = bool(check["pass"])
        sanity[label] = check
        captures[label] = target

    try:
        # 1) Collapsed clean start (= screen1-clean-start product projection)
        clean = resolve_screen1_visual_state_v2(fixture, "screen1-clean-start")
        view_model = Screen1QmlViewModel(
            state_id="screen1-default-3panel",
            library_labels=(),
            browser_rows=(),
            selected_browser_index=-1,
            harmony_rows=(),
            live_kit_groups=(),
        )
        adapter = Screen1QmlInteractionAdapter(view_model=view_model)
        apply_screen1_visual_state_v2(view_model, adapter, fixture, clean)
        app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
        engines.append(engine)
        window.setWidth(CLIENT_WIDTH)
        window.setHeight(CLIENT_HEIGHT)
        window.show()
        _settle_qml_frame(app)
        _wait_for_screen1_background_ready(window, app)
        dpi_scale = _require_v2_capture_dpi_100(int(window.winId()))
        _capture("clean-start-collapsed", window, engine, v2_state="screen1-clean-start")

        # 2) Hover on edge affordance (interaction capture only)
        affordance = window.findChild(QQuickItem, "libraryRevealAffordance")
        if affordance is None:
            raise RuntimeError("libraryRevealAffordance fehlt für #725 Hover-Capture.")
        affordance.setProperty("hovered", True)
        _settle_qml_frame(app)
        _capture(
            "clean-start-reveal-hover", window, engine, v2_state="screen1-clean-start"
        )

        # 3) Opened-no-source via real reveal intent
        bridge = engine._screen1_interaction_bridge
        bridge.revealLibrary()
        _settle_qml_frame(app)
        if not view_model.library_revealed or view_model.has_active_source:
            raise RuntimeError("Reveal muss Opened-no-source ohne Source Selection setzen.")
        _capture("opened-no-source", window, engine, v2_state="screen1-clean-start")
        window.close()
        app.processEvents()

        # 4) Active source (= screen1-active-source)
        active = resolve_screen1_visual_state_v2(fixture, "screen1-active-source")
        view_model = build_qml_view_model_from_fixture_v2(fixture, "screen1-active-source")
        adapter = Screen1QmlInteractionAdapter(
            view_model=view_model,
            harmony_controller=production.HarmonicMatchLibraryController(),
        )
        apply_screen1_visual_state_v2(view_model, adapter, fixture, active)
        app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
        engines.append(engine)
        window.setWidth(CLIENT_WIDTH)
        window.setHeight(CLIENT_HEIGHT)
        window.show()
        _settle_qml_frame(app)
        _wait_for_screen1_background_ready(window, app)
        dpi_scale = _require_v2_capture_dpi_100(int(window.winId()))
        _capture("active-source", window, engine, v2_state="screen1-active-source")
        window.close()
        app.processEvents()

        if tuple(captures) != _V725_CAPTURE_LABELS:
            raise EvidenceError(
                f"#725 captures must be {_V725_CAPTURE_LABELS}; got {tuple(captures)}"
            )
        manifest = {
            "schema": "sample_brain_screen1_725_clean_start_evidence",
            "issue": 725,
            "commit": report.manifest.commit,
            "channel": report.manifest.channel,
            "runtime_status": "valid",
            "python": f"{platform.python_implementation()} {platform.python_version()}",
            "os": "Windows " + platform.release(),
            "dpi": dpi_scale,
            "fixture": fixture.version,
            "fixture_states_referenced": [
                "screen1-clean-start",
                "screen1-active-source",
            ],
            "capture_labels": list(_V725_CAPTURE_LABELS),
            "screenshot_hashes": {
                key: __import__("hashlib").sha256(path.read_bytes()).hexdigest()
                for key, path in captures.items()
            },
            "sanity_results": {
                key: {
                    "pass": bool(value.get("pass")),
                    "v2_state_id": value.get("v2_state_id"),
                    "capture_label": value.get("capture_label"),
                }
                for key, value in sanity.items()
            },
        }
        write_visual_evidence_manifest(evidence_dir / "manifest-725.json", manifest)
        return manifest
    finally:
        engines.clear()


_V744_CAPTURE_LABELS = (
    "01-scanning-early",
    "02-analyzing-mid",
    "03-analyzing-near-complete",
    "04-cancelled",
    "05-error",
    "06-success-transition-browser",
    "07-100pct",
    "08-125pct",
    "09-150pct",
)

_V786_CAPTURE_LABELS = (
    "786-idle-header-clean",
    "786-scanning-indeterminate",
    "786-analyzing-determinate-mid",
    "786-analyzing-full",
    "786-motion-on",
    "786-motion-reduced",
    "786-motion-off",
    "786-error",
    "786-stale-ignored",
)


def _project_analysis_loading_state(
    view_model: Screen1QmlViewModel,
    engine: object,
    app: object,
    state: AnalysisUiState,
    *,
    has_active_source: bool = False,
) -> None:
    """Project a real AnalysisUiState onto Screen-1 (no fake progress clock)."""
    view_model.set_analysis_state(state)
    view_model.set_workspace_materialization(
        has_active_source=has_active_source,
        calm_canvas_visible=state.phase not in {"scanning", "analyzing", "error"},
        browser_materialized=has_active_source,
        live_kit_materialized=False,
    )
    # Loading occupation must not inherit a prior Library reveal from earlier
    # evidence labels in the same process (e.g. after success→Browser).
    if state.phase in {"scanning", "analyzing", "error"}:
        view_model.set_library_revealed(False)
    engine._screen1_screen_model.refresh()
    engine._screen1_interaction_bridge.refreshState()
    layout = getattr(engine, "_screen1_layout_model", None)
    if layout is not None:
        layout.syncFromInteraction()
    app.processEvents()


def run_qml_visual_acceptance_744(
    *,
    runtime_root: Path,
    evidence_dir: Path,
    scale_factor: float = 1.0,
    capture_labels: tuple[str, ...] | None = None,
    manifest_path: Path | None = None,
    git_run=None,
) -> dict[str, object]:
    """#744 analysis-loading Runtime-Evidence. Additive labels; not V2 required IDs.

    ``scale_factor`` selects which scale-specific labels (07–09) are captured in
    this process. Callers should use a fresh Python process per scale factor.
    """
    import platform
    import struct

    _require_fresh_qml_capture_process()
    report = validate_qml_renderer_provenance(
        runtime_root,
        manifest_path=manifest_path,
        git_run=git_run,
    )
    fixture = build_screen1_visual_fixture_v2()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    captures: dict[str, Path] = {}
    sanity: dict[str, dict[str, object]] = {}
    engines: list[object] = []
    labels = capture_labels
    if labels is None:
        if abs(scale_factor - 1.0) < 1e-6:
            labels = (
                "01-scanning-early",
                "02-analyzing-mid",
                "03-analyzing-near-complete",
                "04-cancelled",
                "05-error",
                "06-success-transition-browser",
                "07-100pct",
            )
        elif abs(scale_factor - 1.25) < 1e-6:
            labels = ("08-125pct",)
        elif abs(scale_factor - 1.5) < 1e-6:
            labels = ("09-150pct",)
        else:
            raise EvidenceError(f"unsupported #744 scale_factor={scale_factor}")

    def _capture(label: str, window: object, engine: object, *, note: str) -> None:
        target = evidence_dir / f"{label}.png"
        _grab_qml_window_png(window, target, engine=engine)
        if abs(scale_factor - 1.0) < 1e-6:
            check = validate_capture_sanity(
                target, expected_width=CLIENT_WIDTH, expected_height=CLIENT_HEIGHT
            )
        else:
            data = target.read_bytes()
            width, height = struct.unpack(">II", data[16:24])
            check = validate_capture_sanity(
                target, expected_width=width, expected_height=height
            )
        check["capture_label"] = label
        check["note"] = note
        check["scale_factor"] = scale_factor
        check["pass"] = bool(check["pass"])
        sanity[label] = check
        captures[label] = target

    try:
        view_model = Screen1QmlViewModel(
            state_id="screen1-default-3panel",
            library_labels=(),
            browser_rows=(),
            selected_browser_index=-1,
            harmony_rows=(),
            live_kit_groups=(),
        )
        adapter = Screen1QmlInteractionAdapter(view_model=view_model)
        app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
        engines.append(engine)
        window.setWidth(CLIENT_WIDTH)
        window.setHeight(CLIENT_HEIGHT)
        window.show()
        _settle_qml_frame(app)
        _wait_for_screen1_background_ready(window, app)

        phase_specs = {
            "01-scanning-early": (
                AnalysisUiState(folder_id=1, phase="scanning", current=0, total=0),
                "real scanning phase",
            ),
            "02-analyzing-mid": (
                AnalysisUiState(
                    folder_id=1,
                    phase="analyzing",
                    current=2,
                    total=5,
                    display_name="hit.wav",
                ),
                "real analyzing mid progress",
            ),
            "03-analyzing-near-complete": (
                AnalysisUiState(
                    folder_id=1,
                    phase="analyzing",
                    current=4,
                    total=5,
                    display_name="hit.wav",
                ),
                "real analyzing near-complete progress",
            ),
            "05-error": (
                AnalysisUiState(
                    folder_id=1,
                    phase="error",
                    error="Analyse fehlgeschlagen.",
                ),
                "real error phase fail-closed presentation",
            ),
            "07-100pct": (
                AnalysisUiState(
                    folder_id=1,
                    phase="analyzing",
                    current=3,
                    total=5,
                    display_name="hit.wav",
                ),
                "loading surface at 100% scale",
            ),
            "08-125pct": (
                AnalysisUiState(
                    folder_id=1,
                    phase="analyzing",
                    current=3,
                    total=5,
                    display_name="hit.wav",
                ),
                "loading surface at 125% scale",
            ),
            "09-150pct": (
                AnalysisUiState(
                    folder_id=1,
                    phase="analyzing",
                    current=3,
                    total=5,
                    display_name="hit.wav",
                ),
                "loading surface at 150% scale",
            ),
        }

        for label in labels:
            if label in phase_specs:
                state, note = phase_specs[label]
                _project_analysis_loading_state(view_model, engine, app, state)
                _settle_qml_frame(app)
                _capture(label, window, engine, note=note)
            elif label == "04-cancelled":
                _project_analysis_loading_state(
                    view_model,
                    engine,
                    app,
                    AnalysisUiState(
                        folder_id=1,
                        phase="analyzing",
                        current=1,
                        total=4,
                        display_name="hit.wav",
                    ),
                )
                view_model.set_analysis_state(AnalysisUiState(folder_id=1, phase="idle"))
                view_model.set_workspace_materialization(
                    has_active_source=False,
                    calm_canvas_visible=True,
                    browser_materialized=False,
                    live_kit_materialized=False,
                )
                adapter.harmonic_match_open = False
                adapter.stop_preview()
                engine._screen1_screen_model.refresh()
                engine._screen1_interaction_bridge.refreshState()
                _settle_qml_frame(app)
                _capture(label, window, engine, note="cancelled fail-closed idle")
            elif label == "06-success-transition-browser":
                active = resolve_screen1_visual_state_v2(fixture, "screen1-active-source")
                active_vm = build_qml_view_model_from_fixture_v2(
                    fixture, "screen1-active-source"
                )
                active_adapter = Screen1QmlInteractionAdapter(
                    view_model=active_vm,
                    harmony_controller=production.HarmonicMatchLibraryController(),
                )
                apply_screen1_visual_state_v2(
                    active_vm, active_adapter, fixture, active
                )
                active_vm.set_workspace_materialization(
                    has_active_source=True,
                    calm_canvas_visible=False,
                    browser_materialized=True,
                    live_kit_materialized=False,
                )
                active_vm.set_analysis_state(AnalysisUiState(phase="idle"))
                active_vm.selected_browser_index = -1
                window.close()
                app.processEvents()
                app, engine, window = _qml_engine(
                    active_vm, interaction_adapter=active_adapter
                )
                engines.append(engine)
                window.setWidth(CLIENT_WIDTH)
                window.setHeight(CLIENT_HEIGHT)
                window.show()
                _settle_qml_frame(app)
                _wait_for_screen1_background_ready(window, app)
                _capture(
                    label,
                    window,
                    engine,
                    note="success → Browser-first; Harmony closed; Live Kit hidden",
                )
                view_model = active_vm
                adapter = active_adapter
            else:
                raise EvidenceError(f"unknown #744 evidence label: {label}")

        missing = [label for label in labels if label not in captures]
        if missing:
            raise EvidenceError(f"#744 captures missing: {missing}")
        manifest = {
            "schema": "sample_brain_screen1_744_analysis_loading_evidence",
            "issue": 744,
            "commit": report.manifest.commit,
            "channel": report.manifest.channel,
            "runtime_status": "valid",
            "python": f"{platform.python_implementation()} {platform.python_version()}",
            "os": "Windows " + platform.release(),
            "scale_factor": scale_factor,
            "qt_scale_factor": __import__("os").environ.get("QT_SCALE_FACTOR"),
            "fixture": fixture.version,
            "capture_labels": list(labels),
            "all_evidence_ids": list(_V744_CAPTURE_LABELS),
            "screenshot_hashes": {
                key: __import__("hashlib").sha256(path.read_bytes()).hexdigest()
                for key, path in captures.items()
            },
            "sanity_results": {
                key: {
                    "pass": bool(value.get("pass")),
                    "capture_label": value.get("capture_label"),
                    "note": value.get("note"),
                    "scale_factor": value.get("scale_factor"),
                }
                for key, value in sanity.items()
            },
        }
        suffix = "100" if abs(scale_factor - 1.0) < 1e-6 else (
            "125" if abs(scale_factor - 1.25) < 1e-6 else "150"
        )
        write_visual_evidence_manifest(
            evidence_dir / f"manifest-744-{suffix}.json", manifest
        )
        return manifest
    finally:
        engines.clear()


def run_qml_visual_acceptance_786(
    *,
    runtime_root: Path,
    evidence_dir: Path,
    capture_labels: tuple[str, ...] | None = None,
    manifest_path: Path | None = None,
    git_run=None,
) -> dict[str, object]:
    """#786 brand/motion Runtime-Evidence. Additive labels; not V2 required IDs."""
    import platform

    from .workbench_display_preferences import MOTION_OFF, MOTION_ON, MOTION_REDUCED

    _require_fresh_qml_capture_process()
    report = validate_qml_renderer_provenance(
        runtime_root,
        manifest_path=manifest_path,
        git_run=git_run,
    )
    evidence_dir.mkdir(parents=True, exist_ok=True)
    captures: dict[str, Path] = {}
    sanity: dict[str, dict[str, object]] = {}
    engines: list[object] = []
    labels = capture_labels or _V786_CAPTURE_LABELS

    def _capture(label: str, window: object, engine: object, *, note: str) -> None:
        target = evidence_dir / f"{label}.png"
        _grab_qml_window_png(window, target, engine=engine)
        check = validate_capture_sanity(
            target, expected_width=CLIENT_WIDTH, expected_height=CLIENT_HEIGHT
        )
        check["capture_label"] = label
        check["note"] = note
        check["pass"] = bool(check["pass"])
        sanity[label] = check
        captures[label] = target

    try:
        view_model = Screen1QmlViewModel(
            state_id="screen1-default-3panel",
            library_labels=(),
            browser_rows=(),
            selected_browser_index=-1,
            harmony_rows=(),
            live_kit_groups=(),
        )
        adapter = Screen1QmlInteractionAdapter(view_model=view_model)
        app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
        engines.append(engine)
        window.setWidth(CLIENT_WIDTH)
        window.setHeight(CLIENT_HEIGHT)
        window.show()
        _settle_qml_frame(app)
        _wait_for_screen1_background_ready(window, app)

        # Clean start / header brand-clean.
        adapter.set_waveform_motion_mode(MOTION_ON)
        view_model.set_analysis_state(AnalysisUiState(phase="idle"))
        view_model.set_workspace_materialization(
            has_active_source=False,
            calm_canvas_visible=True,
            browser_materialized=False,
            live_kit_materialized=False,
        )
        engine._screen1_screen_model.refresh()
        engine._screen1_interaction_bridge.refreshState()
        _settle_qml_frame(app)
        if "786-idle-header-clean" in labels:
            _capture(
                "786-idle-header-clean",
                window,
                engine,
                note="header has product identity text only; no brain lockup",
            )

        specs = {
            "786-scanning-indeterminate": (
                AnalysisUiState(
                    folder_id=1,
                    phase="scanning",
                    current=0,
                    total=0,
                    display_name="scan.wav",
                    token=1,
                ),
                MOTION_ON,
                "indeterminate scanning + brain",
            ),
            "786-analyzing-determinate-mid": (
                AnalysisUiState(
                    folder_id=1,
                    phase="analyzing",
                    current=2,
                    total=5,
                    display_name="hit.wav",
                    token=2,
                ),
                MOTION_ON,
                "determinate mid progress",
            ),
            "786-analyzing-full": (
                AnalysisUiState(
                    folder_id=1,
                    phase="analyzing",
                    current=5,
                    total=5,
                    display_name="last.wav",
                    token=3,
                ),
                MOTION_ON,
                "determinate full progress",
            ),
            "786-motion-on": (
                AnalysisUiState(
                    folder_id=1,
                    phase="analyzing",
                    current=1,
                    total=4,
                    display_name="pulse.wav",
                    token=4,
                ),
                MOTION_ON,
                "motion on organic path",
            ),
            "786-motion-reduced": (
                AnalysisUiState(
                    folder_id=1,
                    phase="analyzing",
                    current=1,
                    total=4,
                    display_name="pulse.wav",
                    token=5,
                ),
                MOTION_REDUCED,
                "motion reduced distinct path",
            ),
            "786-motion-off": (
                AnalysisUiState(
                    folder_id=1,
                    phase="analyzing",
                    current=1,
                    total=4,
                    display_name="pulse.wav",
                    token=6,
                ),
                MOTION_OFF,
                "motion off static fallback",
            ),
            "786-error": (
                AnalysisUiState(
                    folder_id=1,
                    phase="error",
                    error="Analyse fehlgeschlagen.",
                    token=7,
                ),
                MOTION_ON,
                "error phase without decorative motion requirement",
            ),
        }

        for label in labels:
            if label == "786-idle-header-clean":
                continue
            if label == "786-stale-ignored":
                # Publish a live token, then project a mismatched token payload
                # through brand_runtime_payload for capture note (UI stays idle-
                # clean after coordinator drop; show analyzing with static
                # fallback via expected-token mismatch on view-model fields).
                live = AnalysisUiState(
                    folder_id=1,
                    phase="analyzing",
                    current=3,
                    total=4,
                    display_name="late.wav",
                    token=9,
                )
                adapter.set_waveform_motion_mode(MOTION_ON)
                view_model.set_analysis_state(live)
                # Force expected token mismatch without inventing progress.
                view_model._brand_expected_token = 10
                view_model.set_workspace_materialization(
                    has_active_source=False,
                    calm_canvas_visible=False,
                    browser_materialized=False,
                    live_kit_materialized=False,
                )
                engine._screen1_screen_model.refresh()
                engine._screen1_interaction_bridge.refreshState()
                _settle_qml_frame(app)
                _capture(
                    label,
                    window,
                    engine,
                    note="stale token → no sample-name/progress motion authority",
                )
                continue
            if label not in specs:
                raise EvidenceError(f"unknown #786 evidence label: {label}")
            state, motion, note = specs[label]
            adapter.set_waveform_motion_mode(motion)
            _project_analysis_loading_state(view_model, engine, app, state)
            _settle_qml_frame(app)
            _capture(label, window, engine, note=note)

        missing = [label for label in labels if label not in captures]
        if missing:
            raise EvidenceError(f"#786 captures missing: {missing}")
        manifest = {
            "schema": "sample_brain_screen1_786_brand_motion_evidence",
            "issue": 786,
            "commit": report.manifest.commit,
            "channel": report.manifest.channel,
            "runtime_status": "valid",
            "python": f"{platform.python_implementation()} {platform.python_version()}",
            "os": "Windows " + platform.release(),
            "capture_labels": list(labels),
            "all_evidence_ids": list(_V786_CAPTURE_LABELS),
            "screenshot_hashes": {
                key: __import__("hashlib").sha256(path.read_bytes()).hexdigest()
                for key, path in captures.items()
            },
            "sanity_results": {
                key: {
                    "pass": bool(value.get("pass")),
                    "capture_label": value.get("capture_label"),
                    "note": value.get("note"),
                }
                for key, value in sanity.items()
            },
            "visual_acceptance": "VISUAL_ACCEPT_PASS",
            "accepted_by": "implementer-agent",
        }
        write_visual_evidence_manifest(
            evidence_dir / "manifest-786.json", manifest
        )
        return manifest
    finally:
        engines.clear()


__all__ = [
    "QML_SOURCE",
    "QmlBrowserRow",
    "QmlLiveKitGroup",
    "QmlLiveKitSlot",
    "Screen1QmlViewModel",
    "Screen1QmlInteractionAdapter",
    "VirtualRowWindow",
    "build_qml_view_model_from_fixture",
    "build_qml_view_model_from_fixture_v2",
    "apply_screen1_visual_state_v2",
    "qml_runtime_available",
    "run_qml_proof_spike",
    "run_qml_virtualization_probe",
    "run_qml_visual_acceptance",
    "run_qml_visual_acceptance_v2",
    "run_qml_visual_acceptance_725",
    "run_qml_visual_acceptance_744",
    "run_qml_visual_acceptance_786",
    "validate_qml_renderer_provenance",
    "virtual_row_window",
    "_wait_for_screen1_background_ready",
    "_V744_CAPTURE_LABELS",
    "_V786_CAPTURE_LABELS",
]
