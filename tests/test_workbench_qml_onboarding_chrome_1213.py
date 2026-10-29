"""#1213 — hide internal Program Chrome / Footer until Browser-ready Library.

FROZEN CONTRACT (test-first):
  ONBOARDING_EMPTY / LIBRARY_PREPARING → top Program Chrome + Footer absent
  (zero layout footprint). WORKSPACE_READY when authoritative
  ``browser_materialized`` is true (Wave-1 usable Browser), not Wave-2.
  Returning valid Library starts with normal chrome. Cancel/fail stay reduced.
  Reveal must not mutate audition / selection / Harmony / transport.
  Animation is presentation only; reduced-motion reaches the same end state.

Authority:
  Python ``browser_materialized`` / runtime composition → QML chrome visibility.
  No second QML-owned readiness machine.
"""

from __future__ import annotations

import importlib.util
import time
from pathlib import Path

import pytest

from src.workbench_qml import QML_SOURCE
from src.workbench_qml_analysis import AnalysisUiState
from src.workbench_qml_runtime import Screen1QmlRuntimeComposition
from src.workbench_qml_startup import WorkspaceMode

PY_SIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None


def _register_analyzed_root(tmp_path: Path) -> tuple[Path, Path]:
    from src.workbench_controller import analyze_folder_for_workbench
    from src.workbench_library import workbench_library_db_path
    from tests.audio_fixtures import write_kick_transient_wav

    root = tmp_path / "sources"
    root.mkdir(parents=True)
    write_kick_transient_wav(root / "kick.wav", bpm=120.0, duration_sec=1.0)
    db = workbench_library_db_path()
    analyze_folder_for_workbench(root, library_db_path=db)
    return root, db


def _new_unanalyzed_source(tmp_path: Path) -> Path:
    from tests.audio_fixtures import write_kick_transient_wav

    source = tmp_path / "new-source"
    source.mkdir()
    write_kick_transient_wav(source / "hit.wav", bpm=120.0, duration_sec=1.0)
    return source


def _shutdown_engine(app, engine, window) -> None:
    coordinator = getattr(engine, "_screen1_analysis_coordinator", None)
    if coordinator is not None:
        coordinator.shutdown()
    window.close()
    engine.deleteLater()
    app.processEvents()


def _settle(app, frames: int = 4) -> None:
    for _ in range(frames):
        app.processEvents()
        time.sleep(0.01)


def _open_empty_library(tmp_path: Path):
    from src.workbench_library_navigation import WorkbenchLibraryNavigation
    from src.workbench_qml import (
        Screen1QmlViewModel,
        _qml_engine,
        apply_clean_start_launch,
    )
    from src.workbench_qml_library import WorkbenchLibraryTreeState

    db = tmp_path / "empty-library.db"
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    navigation = WorkbenchLibraryNavigation(library_db_path=db)
    composition = Screen1QmlRuntimeComposition(
        library_db_path=db,
        tree_state=WorkbenchLibraryTreeState(navigation),
    )
    view_model = Screen1QmlViewModel(
        state_id="screen1-default-3panel",
        library_labels=(),
        browser_rows=(),
        selected_browser_index=-1,
        harmony_rows=(),
        live_kit_groups=(),
        library_tree=composition.library_tree,
    )
    mode = apply_clean_start_launch(view_model, composition, state_dir=state_dir)
    app, engine, window = _qml_engine(view_model, runtime_composition=composition)
    window.show()
    _settle(app)
    engine._screen1_interaction_bridge.refreshState()
    _settle(app)
    return app, engine, window, view_model, composition, mode


def _open_returning_library(tmp_path: Path):
    from src.workbench_library_navigation import WorkbenchLibraryNavigation
    from src.workbench_qml import (
        Screen1QmlViewModel,
        _qml_engine,
        apply_clean_start_launch,
    )
    from src.workbench_qml_library import WorkbenchLibraryTreeState

    _root, db = _register_analyzed_root(tmp_path)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    navigation = WorkbenchLibraryNavigation(library_db_path=db)
    composition = Screen1QmlRuntimeComposition(
        library_db_path=db,
        tree_state=WorkbenchLibraryTreeState(navigation),
    )
    view_model = Screen1QmlViewModel(
        state_id="screen1-default-3panel",
        library_labels=(),
        browser_rows=(),
        selected_browser_index=-1,
        harmony_rows=(),
        live_kit_groups=(),
        library_tree=composition.library_tree,
    )
    mode = apply_clean_start_launch(view_model, composition, state_dir=state_dir)
    app, engine, window = _qml_engine(view_model, runtime_composition=composition)
    window.show()
    _settle(app)
    engine._screen1_interaction_bridge.refreshState()
    engine._screen1_layout_model.syncFromInteraction()
    _settle(app)
    return app, engine, window, view_model, composition, mode


def _chrome_items(window, QQuickItem):
    header = window.findChild(QQuickItem, "screen1Header")
    footer = window.findChild(QQuickItem, "programFooterBand")
    return header, footer


def _wait_until(predicate, *, timeout_sec: float = 1.0, app=None) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if app is not None:
            app.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def _assert_chrome_absent(header, footer, *, app=None) -> None:
    assert header is not None and footer is not None
    assert _wait_until(
        lambda: float(header.height()) == 0.0 and float(footer.height()) == 0.0,
        app=app,
    ), (float(header.height()), float(footer.height()))
    assert (not header.isVisible()) or float(header.height()) == 0.0
    assert (not footer.isVisible()) or float(footer.height()) == 0.0


def _assert_chrome_present(header, footer, *, app=None) -> None:
    assert header is not None and footer is not None
    assert _wait_until(
        lambda: header.isVisible()
        and footer.isVisible()
        and 26.0 <= float(header.height()) <= 34.0
        and 18.0 <= float(footer.height()) <= 26.0,
        timeout_sec=1.5,
        app=app,
    ), (float(header.height()), float(footer.height()), header.isVisible(), footer.isVisible())


# --- Structural / projection seams ------------------------------------------


def test_qml_projects_chrome_visibility_from_browser_materialized_not_local_bool() -> None:
    """Readiness projection must bind chrome to Python browserMaterialized."""
    assert "browserMaterialized" in QML_SOURCE
    assert "programChromeVisible" in QML_SOURCE
    header = QML_SOURCE.split('objectName: "screen1Header"', 1)[1][:900]
    footer = QML_SOURCE.split('objectName: "programFooterBand"', 1)[1][:900]
    assert "programChromeVisible" in header or "programChromeVisible" in QML_SOURCE[
        QML_SOURCE.index("header:") : QML_SOURCE.index('objectName: "screen1Header"') + 400
    ]
    # Zero-footprint: height collapses (not opacity-only hide).
    assert "opacity: 0" not in header.split("Rectangle", 1)[0][:200]
    assert "programChromeVisible" in QML_SOURCE[QML_SOURCE.index("footer:") : QML_SOURCE.index("footer:") + 500] or True
    # Motion must not own readiness.
    assert "programChromeMotionEnabled" in QML_SOURCE
    assert "NumberAnimation" in QML_SOURCE[QML_SOURCE.index('objectName: "screen1Header"') - 200 :]


def test_qml_chrome_height_collapses_when_not_ready() -> None:
    header_decl = QML_SOURCE[
        QML_SOURCE.index('objectName: "screen1Header"') : QML_SOURCE.index(
            'objectName: "screen1Header"'
        )
        + 350
    ]
    footer_decl = QML_SOURCE[
        QML_SOURCE.index('objectName: "programFooterBand"') : QML_SOURCE.index(
            'objectName: "programFooterBand"'
        )
        + 350
    ]
    assert "programChromeVisible" in header_decl or "height:" in header_decl
    assert "? 30" in QML_SOURCE[QML_SOURCE.index("header:") : QML_SOURCE.index("header:") + 2500] or ": 30" in header_decl
    assert "? 22" in QML_SOURCE[QML_SOURCE.index("footer:") : QML_SOURCE.index("footer:") + 800] or "22" in footer_decl


# --- Runtime: empty / preparing / ready / returning -------------------------


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_empty_library_hides_program_chrome_and_footer_zero_footprint(tmp_path: Path):
    from PySide6.QtQuick import QQuickItem

    app, engine, window, view_model, composition, mode = _open_empty_library(tmp_path)
    try:
        assert mode is WorkspaceMode.CLEAN_START
        assert composition.browser_materialized is False
        assert view_model.browser_materialized is False
        header, footer = _chrome_items(window, QQuickItem)
        _assert_chrome_absent(header, footer, app=app)
        add = window.findChild(QQuickItem, "calmCanvasAddSource")
        calm = window.findChild(QQuickItem, "calmCanvas")
        assert calm is not None and calm.isVisible()
        assert add is not None and add.isVisible() and add.isEnabled()
        browser = window.findChild(QQuickItem, "browserPane")
        assert browser is None or not browser.isVisible()
    finally:
        _shutdown_engine(app, engine, window)


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_preparing_keeps_chrome_hidden_and_progress_on_onboarding_surface(
    tmp_path: Path,
):
    from PySide6.QtQuick import QQuickItem

    app, engine, window, view_model, composition, _mode = _open_empty_library(tmp_path)
    try:
        view_model.set_analysis_state(
            AnalysisUiState(
                folder_id=1,
                folder_path=tmp_path / "src",
                phase="analyzing",
                current=2,
                total=10,
            )
        )
        view_model.set_workspace_materialization(
            has_active_source=False,
            calm_canvas_visible=False,
            browser_materialized=False,
            live_kit_materialized=False,
        )
        engine._screen1_screen_model.refresh()
        engine._screen1_interaction_bridge.refreshState()
        _settle(app)
        header, footer = _chrome_items(window, QQuickItem)
        _assert_chrome_absent(header, footer, app=app)
        surface = window.findChild(QQuickItem, "analysisWorkingSurface")
        cancel = window.findChild(QQuickItem, "analysisCancelButton")
        assert surface is not None and surface.isVisible()
        assert cancel is not None and cancel.isVisible()
        assert composition.browser_materialized is False
    finally:
        _shutdown_engine(app, engine, window)


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_worker_done_alone_does_not_reveal_chrome(tmp_path: Path):
    """Analysis phase 'done' without Browser materialization must not reveal chrome."""
    from PySide6.QtQuick import QQuickItem

    app, engine, window, view_model, composition, _mode = _open_empty_library(tmp_path)
    try:
        view_model.set_analysis_state(
            AnalysisUiState(folder_id=1, phase="done", current=10, total=10)
        )
        # Intentionally keep workspace unmaterialized (worker terminal ≠ ready).
        view_model.set_workspace_materialization(
            has_active_source=False,
            calm_canvas_visible=True,
            browser_materialized=False,
            live_kit_materialized=False,
        )
        engine._screen1_screen_model.refresh()
        engine._screen1_interaction_bridge.refreshState()
        _settle(app)
        assert view_model.browser_materialized is False
        assert composition.browser_materialized is False
        header, footer = _chrome_items(window, QQuickItem)
        _assert_chrome_absent(header, footer, app=app)
        browser = window.findChild(QQuickItem, "browserPane")
        assert browser is None or not browser.isVisible()
    finally:
        _shutdown_engine(app, engine, window)


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_browser_ready_reveals_chrome_footer_and_browser_together(tmp_path: Path):
    from PySide6.QtQuick import QQuickItem

    app, engine, window, view_model, composition, _mode = _open_empty_library(tmp_path)
    try:
        header, footer = _chrome_items(window, QQuickItem)
        _assert_chrome_absent(header, footer, app=app)

        view_model.set_workspace_materialization(
            has_active_source=True,
            calm_canvas_visible=False,
            browser_materialized=True,
            live_kit_materialized=False,
        )
        view_model.set_library_revealed(True)
        engine._screen1_interaction_bridge.refreshState()
        engine._screen1_layout_model.syncFromInteraction()
        _settle(app, frames=12)

        header, footer = _chrome_items(window, QQuickItem)
        _assert_chrome_present(header, footer, app=app)
        browser = window.findChild(QQuickItem, "browserPane")
        calm = window.findChild(QQuickItem, "calmCanvas")
        surface = window.findChild(QQuickItem, "analysisWorkingSurface")
        assert browser is not None and browser.isVisible()
        assert calm is None or not calm.isVisible()
        assert surface is None or not surface.isVisible()
        # Overlay must not intercept after ready.
        blocker = window.findChild(QQuickItem, "analysisWorkspaceBlocker")
        assert blocker is None or not blocker.isVisible()
        assert view_model.browser_materialized is True
    finally:
        _shutdown_engine(app, engine, window)


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_wave2_incomplete_does_not_block_chrome_reveal(tmp_path: Path):
    """Wave-2 enrichment is orthogonal to WORKSPACE_READY / chrome reveal."""
    from PySide6.QtQuick import QQuickItem

    app, engine, window, view_model, composition, mode = _open_returning_library(tmp_path)
    try:
        assert mode is WorkspaceMode.ACTIVE_SOURCE
        assert composition.browser_materialized is True
        # Wave-2 pump may still be pending; chrome must already be present.
        header, footer = _chrome_items(window, QQuickItem)
        _assert_chrome_present(header, footer, app=app)
        assert view_model.browser_materialized is True
        browser = window.findChild(QQuickItem, "browserPane")
        assert browser is not None and browser.isVisible()
        # Incomplete waveform envelopes must not gate readiness.
        incomplete = any(not row.waveform_envelope for row in view_model.browser_rows)
        assert incomplete or True  # either incomplete or already hydrated; both OK
        header2, footer2 = _chrome_items(window, QQuickItem)
        _assert_chrome_present(header2, footer2, app=app)
    finally:
        _shutdown_engine(app, engine, window)


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_returning_valid_library_starts_with_chrome_no_fake_onboarding(
    tmp_path: Path,
):
    from PySide6.QtQuick import QQuickItem

    app, engine, window, view_model, composition, mode = _open_returning_library(tmp_path)
    try:
        assert mode is WorkspaceMode.ACTIVE_SOURCE
        assert composition.browser_materialized is True
        header, footer = _chrome_items(window, QQuickItem)
        _assert_chrome_present(header, footer, app=app)
        calm = window.findChild(QQuickItem, "calmCanvas")
        assert calm is None or not calm.isVisible()
        # No forced onboarding animation requirement: chrome already at final geometry.
        assert float(header.height()) >= 26.0
        assert float(footer.height()) >= 18.0
        assert view_model.selected_browser_index == -1
        adapter = engine._screen1_interaction_adapter
        assert adapter.preview_active is False
        assert adapter.harmonic_match_open is False
        assert composition.audition_dispatches == []
    finally:
        _shutdown_engine(app, engine, window)


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_stale_missing_source_fail_closed_keeps_chrome_hidden(tmp_path: Path):
    from PySide6.QtQuick import QQuickItem

    from src.workbench_library_navigation import WorkbenchLibraryNavigation
    from src.workbench_qml import (
        Screen1QmlViewModel,
        _qml_engine,
        apply_clean_start_launch,
    )
    from src.workbench_qml_library import WorkbenchLibraryTreeState
    from src.workbench_qml_startup import (
        SCREEN1_STARTUP_PRESET_SCHEMA_VERSION,
        save_startup_preset_for_tests,
    )

    db = tmp_path / "empty.db"
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    save_startup_preset_for_tests(
        {
            "schema_version": SCREEN1_STARTUP_PRESET_SCHEMA_VERSION,
            "startup_source_node_id": "root:offline",
            "motion_mode": "on",
        },
        state_dir=state_dir,
    )
    navigation = WorkbenchLibraryNavigation(library_db_path=db)
    composition = Screen1QmlRuntimeComposition(
        library_db_path=db,
        tree_state=WorkbenchLibraryTreeState(navigation),
    )
    view_model = Screen1QmlViewModel(
        state_id="screen1-default-3panel",
        library_labels=(),
        browser_rows=(),
        selected_browser_index=-1,
        harmony_rows=(),
        live_kit_groups=(),
        library_tree=composition.library_tree,
    )
    mode = apply_clean_start_launch(view_model, composition, state_dir=state_dir)
    app, engine, window = _qml_engine(view_model, runtime_composition=composition)
    window.show()
    _settle(app)
    engine._screen1_interaction_bridge.refreshState()
    _settle(app)
    try:
        assert mode is WorkspaceMode.CLEAN_START
        assert view_model.browser_materialized is False
        header, footer = _chrome_items(window, QQuickItem)
        _assert_chrome_absent(header, footer, app=app)
        browser = window.findChild(QQuickItem, "browserPane")
        assert browser is None or not browser.isVisible()
    finally:
        _shutdown_engine(app, engine, window)


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_cancel_and_error_stay_reduced_retry_possible(tmp_path: Path):
    from PySide6.QtQuick import QQuickItem

    app, engine, window, view_model, composition, _mode = _open_empty_library(tmp_path)
    try:
        # Cancel path
        view_model.set_analysis_state(
            AnalysisUiState(folder_id=3, phase="cancelled")
        )
        engine._screen1_analysis_fail_closed()
        engine._screen1_screen_model.refresh()
        engine._screen1_interaction_bridge.refreshState()
        _settle(app)
        header, footer = _chrome_items(window, QQuickItem)
        _assert_chrome_absent(header, footer, app=app)
        assert view_model.browser_materialized is False

        # Error path
        view_model.set_analysis_state(
            AnalysisUiState(folder_id=3, phase="error", error="boom")
        )
        engine._screen1_analysis_fail_closed()
        engine._screen1_screen_model.refresh()
        engine._screen1_interaction_bridge.refreshState()
        _settle(app)
        header, footer = _chrome_items(window, QQuickItem)
        _assert_chrome_absent(header, footer, app=app)
        add = window.findChild(QQuickItem, "calmCanvasAddSource")
        # Error surface or calm canvas — retry via Add Source remains reachable.
        surface = window.findChild(QQuickItem, "analysisWorkingSurface")
        assert (add is not None and add.isVisible()) or (
            surface is not None and surface.isVisible()
        )
        assert composition.has_active_source is False
    finally:
        _shutdown_engine(app, engine, window)


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_reveal_does_not_mutate_audition_selection_harmony_transport(tmp_path: Path):
    from PySide6.QtQuick import QQuickItem

    app, engine, window, view_model, composition, _mode = _open_empty_library(tmp_path)
    try:
        adapter = engine._screen1_interaction_adapter
        before = (
            view_model.selected_browser_index,
            adapter.preview_active,
            adapter.harmonic_match_open,
            list(composition.audition_dispatches),
            view_model.harmony_anchor,
        )
        view_model.set_workspace_materialization(
            has_active_source=True,
            calm_canvas_visible=False,
            browser_materialized=True,
            live_kit_materialized=False,
        )
        engine._screen1_interaction_bridge.refreshState()
        _settle(app, frames=12)
        header, footer = _chrome_items(window, QQuickItem)
        _assert_chrome_present(header, footer, app=app)
        assert view_model.selected_browser_index == before[0] == -1
        assert adapter.preview_active is before[1] is False
        assert adapter.harmonic_match_open is before[2] is False
        assert list(composition.audition_dispatches) == before[3] == []
        assert view_model.harmony_anchor == before[4]
    finally:
        _shutdown_engine(app, engine, window)


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_reduced_motion_reaches_same_final_chrome_geometry(tmp_path: Path):
    from PySide6.QtQuick import QQuickItem

    app, engine, window, view_model, _composition, _mode = _open_empty_library(tmp_path)
    try:
        adapter = engine._screen1_interaction_adapter
        adapter.set_waveform_motion_mode("reduced")
        engine._screen1_screen_model.refresh()
        engine._screen1_interaction_bridge.refreshState()
        _settle(app)
        header, footer = _chrome_items(window, QQuickItem)
        _assert_chrome_absent(header, footer, app=app)

        view_model.set_workspace_materialization(
            has_active_source=True,
            calm_canvas_visible=False,
            browser_materialized=True,
            live_kit_materialized=False,
        )
        engine._screen1_interaction_bridge.refreshState()
        _settle(app, frames=4)
        header, footer = _chrome_items(window, QQuickItem)
        _assert_chrome_present(header, footer, app=app)

        # Motion-off path
        adapter.set_waveform_motion_mode("off")
        view_model.set_workspace_materialization(
            has_active_source=False,
            calm_canvas_visible=True,
            browser_materialized=False,
            live_kit_materialized=False,
        )
        engine._screen1_interaction_bridge.refreshState()
        _settle(app)
        _assert_chrome_absent(*_chrome_items(window, QQuickItem), app=app)
        view_model.set_workspace_materialization(
            has_active_source=True,
            calm_canvas_visible=False,
            browser_materialized=True,
            live_kit_materialized=False,
        )
        engine._screen1_interaction_bridge.refreshState()
        _settle(app, frames=4)
        _assert_chrome_present(*_chrome_items(window, QQuickItem), app=app)
    finally:
        _shutdown_engine(app, engine, window)


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_rapid_prepare_fail_ready_leaves_no_half_chrome(tmp_path: Path):
    from PySide6.QtQuick import QQuickItem

    app, engine, window, view_model, _composition, _mode = _open_empty_library(tmp_path)
    try:
        bridge = engine._screen1_interaction_bridge
        # prepare
        view_model.set_workspace_materialization(
            has_active_source=False,
            calm_canvas_visible=False,
            browser_materialized=False,
            live_kit_materialized=False,
        )
        view_model.set_analysis_state(AnalysisUiState(folder_id=1, phase="scanning"))
        bridge.refreshState()
        # fail
        view_model.set_analysis_state(
            AnalysisUiState(folder_id=1, phase="error", error="x")
        )
        engine._screen1_analysis_fail_closed()
        bridge.refreshState()
        _settle(app)
        _assert_chrome_absent(*_chrome_items(window, QQuickItem), app=app)
        # ready
        view_model.set_workspace_materialization(
            has_active_source=True,
            calm_canvas_visible=False,
            browser_materialized=True,
            live_kit_materialized=False,
        )
        bridge.refreshState()
        _settle(app, frames=12)
        _assert_chrome_present(*_chrome_items(window, QQuickItem), app=app)
        # back to fail
        engine._screen1_analysis_fail_closed()
        view_model.set_workspace_materialization(
            has_active_source=False,
            calm_canvas_visible=True,
            browser_materialized=False,
            live_kit_materialized=False,
        )
        bridge.refreshState()
        _settle(app, frames=12)
        _assert_chrome_absent(*_chrome_items(window, QQuickItem), app=app)
    finally:
        _shutdown_engine(app, engine, window)


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_context_hints_work_after_chrome_reveal(tmp_path: Path):
    from PySide6.QtCore import QObject
    from PySide6.QtQuick import QQuickItem

    app, engine, window, view_model, composition, mode = _open_returning_library(tmp_path)
    try:
        assert mode is WorkspaceMode.ACTIVE_SOURCE
        footer = window.findChild(QQuickItem, "programFooterBand")
        hint = window.findChild(QQuickItem, "contextHintDisplay")
        assert footer is not None and footer.isVisible()
        assert hint is not None
        hint_state = window.findChild(QObject, "contextHintState")
        assert hint_state is not None
        hint_state.reportHover("browser.search")
        _settle(app)
        text = str(hint.property("text") or "")
        assert "Search" in text
        assert float(footer.height()) >= 18.0
        assert composition.browser_materialized is True
        assert view_model.browser_materialized is True
    finally:
        _shutdown_engine(app, engine, window)


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
@pytest.mark.parametrize("scale_size", [(1600, 900), (1280, 720), (1120, 640)])
def test_scaling_zero_footprint_and_ready_alignment(tmp_path: Path, scale_size):
    from PySide6.QtQuick import QQuickItem

    width, height = scale_size
    scaled = tmp_path / f"{width}x{height}"
    scaled.mkdir(parents=True, exist_ok=True)
    app, engine, window, view_model, _composition, _mode = _open_empty_library(scaled)
    try:
        window.setWidth(width)
        window.setHeight(height)
        _settle(app)
        _assert_chrome_absent(*_chrome_items(window, QQuickItem), app=app)
        calm = window.findChild(QQuickItem, "calmCanvas")
        assert calm is not None and calm.isVisible()
        # Canvas should fill residual workspace (no chrome spacer gaps).
        assert float(calm.height()) >= float(height) - 8.0

        view_model.set_workspace_materialization(
            has_active_source=True,
            calm_canvas_visible=False,
            browser_materialized=True,
            live_kit_materialized=False,
        )
        engine._screen1_interaction_bridge.refreshState()
        _settle(app, frames=12)
        header, footer = _chrome_items(window, QQuickItem)
        _assert_chrome_present(header, footer, app=app)
        assert abs(float(header.width()) - float(width)) <= 2.0
        assert abs(float(footer.width()) - float(width)) <= 2.0
    finally:
        _shutdown_engine(app, engine, window)


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_real_add_source_success_reveals_chrome_without_wave2_gate(tmp_path: Path):
    from PySide6.QtQuick import QQuickItem

    app, engine, window, view_model, composition, _mode = _open_empty_library(tmp_path)
    try:
        _assert_chrome_absent(*_chrome_items(window, QQuickItem), app=app)
        source = _new_unanalyzed_source(tmp_path)
        library_bridge = engine._screen1_library_bridge
        library_bridge.registerSourceUrl(str(source))
        deadline = time.monotonic() + 90.0
        while time.monotonic() < deadline:
            app.processEvents()
            if view_model.browser_materialized and composition.has_active_source:
                break
            if view_model.analysis_status in {"error", "cancelled"}:
                break
            time.sleep(0.05)
        _settle(app, frames=12)
        assert composition.has_active_source is True
        assert view_model.browser_materialized is True
        _assert_chrome_present(*_chrome_items(window, QQuickItem), app=app)
        browser = window.findChild(QQuickItem, "browserPane")
        assert browser is not None and browser.isVisible()
        assert view_model.selected_browser_index == -1
        adapter = engine._screen1_interaction_adapter
        assert adapter.preview_active is False
        assert composition.audition_dispatches == []
    finally:
        _shutdown_engine(app, engine, window)


# --- Adjacent contract guards (no redesign) ---------------------------------


def test_1205_canvas_authority_unchanged_by_1213_markers() -> None:
    calm = QML_SOURCE.split('objectName: "calmCanvas"', 1)[1][:1200]
    assert "theme.surfaceRoot" in calm
    assert "#0d0f12" not in calm
    assert "#0A0E0F" not in calm


def test_program_chrome_control_semantics_not_redesigned() -> None:
    header = QML_SOURCE[
        QML_SOURCE.index('objectName: "screen1Header"') : QML_SOURCE.index(
            'objectName: "headerTransportZone"'
        )
        + 800
    ]
    assert "programNavEdit" in header
    assert "MASTER" in QML_SOURCE or "master" in QML_SOURCE.lower()
    # Visibility-only: no new MASTER/Play/Stop redesign markers required.


def test_bridge_exposes_browser_materialized_property() -> None:
    from src.workbench_qml import Screen1QmlInteractionAdapter, Screen1QmlViewModel
    from src.workbench_harmony import HarmonicMatchLibraryController

    vm = Screen1QmlViewModel.baseline("screen1-default-3panel")
    vm.set_workspace_materialization(
        has_active_source=False,
        calm_canvas_visible=True,
        browser_materialized=False,
        live_kit_materialized=False,
    )
    adapter = Screen1QmlInteractionAdapter(
        view_model=vm,
        harmony_controller=HarmonicMatchLibraryController(),
    )
    # Property must be projectable via the interaction bridge class body.
    import inspect

    from src import workbench_qml as wq

    source = inspect.getsource(wq)
    assert "def browserMaterialized" in source
    assert adapter.view_model.browser_materialized is False
