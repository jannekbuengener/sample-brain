"""#744 Source analysis loading experience contracts.

Blocking loading surface over the Screen-1 working area while scanning/analyzing.
Real AnalysisUiState only — no fake progress. Cancel stays above the input blocker.
"""

from __future__ import annotations

import importlib.util
import time
from pathlib import Path

import pytest

from src.workbench_qml import QML_SOURCE
from src.workbench_qml_analysis import AnalysisUiState
from src.workbench_qml_runtime import Screen1QmlRuntimeComposition

PY_SIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None


def _new_unanalyzed_source(tmp_path: Path) -> Path:
    from tests.audio_fixtures import write_kick_transient_wav

    source = tmp_path / "new-source"
    source.mkdir()
    write_kick_transient_wav(source / "hit.wav", bpm=120.0, duration_sec=1.0)
    return source


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


def _wait_for_analysis(app, view_model, *, timeout_sec=90.0) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        app.processEvents()
        status = str(getattr(view_model, "analysis_status", "") or "")
        if status in {"done", "idle"} and len(view_model.browser_rows) > 0:
            return True
        if status in {"error", "cancelled"}:
            return False
        time.sleep(0.05)
    return False


def _shutdown_engine(app, engine, window) -> None:
    coordinator = getattr(engine, "_screen1_analysis_coordinator", None)
    if coordinator is not None:
        coordinator.shutdown()
    window.close()
    engine.deleteLater()
    app.processEvents()


def _project_analysis(
    *,
    view_model,
    engine,
    app,
    state: AnalysisUiState,
    has_active_source: bool = False,
) -> None:
    view_model.set_analysis_state(state)
    view_model.set_workspace_materialization(
        has_active_source=has_active_source,
        calm_canvas_visible=state.phase not in {"scanning", "analyzing", "error"},
        browser_materialized=has_active_source,
        live_kit_materialized=False,
    )
    engine._screen1_screen_model.refresh()
    engine._screen1_interaction_bridge.refreshState()
    layout = getattr(engine, "_screen1_layout_model", None)
    if layout is not None:
        layout.syncFromInteraction()
    app.processEvents()


def test_qml_declares_744_loading_surface_structure():
    assert "analysisWorkingSurface" in QML_SOURCE
    assert "analysisWorkspaceBlocker" in QML_SOURCE
    assert "analysisStatusCard" in QML_SOURCE
    assert "analysisCancelButton" in QML_SOURCE
    assert "analysisProgressTrack" in QML_SOURCE
    assert "analysisProgressFill" in QML_SOURCE
    assert '" Samples"' in QML_SOURCE or "+ \" Samples\"" in QML_SOURCE
    # Blocker must be declared before status card so Cancel stays clickable.
    blocker_idx = QML_SOURCE.index("objectName: \"analysisWorkspaceBlocker\"")
    card_idx = QML_SOURCE.index("objectName: \"analysisStatusCard\"")
    cancel_idx = QML_SOURCE.index("objectName: \"analysisCancelButton\"")
    assert blocker_idx < card_idx < cancel_idx
    # No fake progress clock in the loading surface.
    surface_start = QML_SOURCE.index("id: analysisWorkingSurface")
    surface_chunk = QML_SOURCE[surface_start : surface_start + 4500]
    assert "Timer {" not in surface_chunk
    assert "NumberAnimation" not in surface_chunk


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_scanning_and_analyzing_show_blocking_overlay(tmp_path: Path):
    from PySide6.QtQuick import QQuickItem

    from src.workbench_library_navigation import WorkbenchLibraryNavigation
    from src.workbench_qml import Screen1QmlViewModel, _qml_engine
    from src.workbench_qml_library import WorkbenchLibraryTreeState

    db = tmp_path / "library.db"
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
    app, engine, window = _qml_engine(view_model, runtime_composition=composition)
    window.show()
    try:
        for phase, current, total in (
            ("scanning", 0, 0),
            ("analyzing", 2, 5),
        ):
            _project_analysis(
                view_model=view_model,
                engine=engine,
                app=app,
                state=AnalysisUiState(
                    folder_id=1,
                    phase=phase,
                    current=current,
                    total=total,
                    display_name="hit.wav",
                ),
            )
            surface = window.findChild(QQuickItem, "analysisWorkingSurface")
            blocker = window.findChild(QQuickItem, "analysisWorkspaceBlocker")
            card = window.findChild(QQuickItem, "analysisStatusCard")
            cancel = window.findChild(QQuickItem, "analysisCancelButton")
            browser = window.findChild(QQuickItem, "browserPane")
            live_kit = window.findChild(QQuickItem, "liveKitPane")
            harmony = window.findChild(QQuickItem, "harmonyPane")
            assert surface is not None and surface.isVisible()
            assert blocker is not None and blocker.isVisible()
            assert card is not None and card.isVisible()
            assert cancel is not None and cancel.isVisible()
            assert browser is not None and not browser.isVisible()
            assert live_kit is not None and not live_kit.isVisible()
            assert harmony is not None
            assert float(harmony.width()) == 0 or float(harmony.opacity()) == 0
            assert engine._screen1_interaction_adapter.harmonic_match_open is False
            assert view_model.selected_browser_index == -1
            assert engine._screen1_interaction_adapter.preview_active is False
            assert composition.live_kit_revealed is False
            assert float(blocker.z()) < float(card.z())
    finally:
        _shutdown_engine(app, engine, window)


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_blocker_blocks_workspace_but_cancel_remains_clickable(tmp_path: Path):
    from PySide6.QtCore import Qt
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest

    from src.workbench_library_navigation import WorkbenchLibraryNavigation
    from src.workbench_qml import Screen1QmlViewModel, _qml_engine
    from src.workbench_qml_library import WorkbenchLibraryTreeState

    db = tmp_path / "library.db"
    source = _new_unanalyzed_source(tmp_path)
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
    app, engine, window = _qml_engine(view_model, runtime_composition=composition)
    window.show()
    try:
        library_bridge = engine._screen1_library_bridge
        adapter = engine._screen1_interaction_adapter
        screen_model = engine._screen1_screen_model

        library_bridge.registerSourceUrl(str(source))
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            app.processEvents()
            if view_model.analysis_status in {"scanning", "analyzing"}:
                break
            time.sleep(0.05)
        assert view_model.analysis_status in {"scanning", "analyzing"}

        surface = window.findChild(QQuickItem, "analysisWorkingSurface")
        blocker = window.findChild(QQuickItem, "analysisWorkspaceBlocker")
        cancel = window.findChild(QQuickItem, "analysisCancelButton")
        calm_add = window.findChild(QQuickItem, "calmCanvasAddSource")
        assert surface is not None and surface.isVisible()
        assert blocker is not None and blocker.isVisible()
        assert cancel is not None and cancel.isVisible()
        assert calm_add is None or not calm_add.isVisible()

        # Click empty deep surface (blocker region away from centered card).
        corner = surface.mapToScene(surface.boundingRect().topLeft()).toPoint()
        corner.setX(corner.x() + 8)
        corner.setY(corner.y() + 8)
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, corner)
        app.processEvents()
        assert view_model.analysis_status in {"scanning", "analyzing"}
        assert composition.has_active_source is False
        assert adapter.preview_active is False

        QTest.mouseClick(
            window,
            Qt.LeftButton,
            Qt.NoModifier,
            cancel.mapToScene(cancel.boundingRect().center()).toPoint(),
        )
        cancel_deadline = time.monotonic() + 30.0
        while time.monotonic() < cancel_deadline:
            app.processEvents()
            if view_model.analysis_status in {"idle", "cancelled", "error"}:
                break
            time.sleep(0.05)
        app.processEvents()

        assert view_model.analysis_status == "idle"
        assert composition.has_active_source is False
        assert view_model.browser_materialized is False
        assert view_model.live_kit_materialized is False
        assert adapter.harmonic_match_open is False
        assert adapter.preview_active is False
        assert view_model.selected_browser_index == -1
        surface_after = window.findChild(QQuickItem, "analysisWorkingSurface")
        assert surface_after is None or not surface_after.isVisible()
        # Ensure cancel path was the intentional QML slot, not a side effect.
        assert callable(getattr(screen_model, "cancelAnalysis", None))
    finally:
        _shutdown_engine(app, engine, window)


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_error_surface_fail_closed_without_cancel_or_panes(tmp_path: Path):
    from PySide6.QtQuick import QQuickItem

    from src.workbench_library_navigation import WorkbenchLibraryNavigation
    from src.workbench_qml import Screen1QmlViewModel, _qml_engine
    from src.workbench_qml_library import WorkbenchLibraryTreeState

    db = tmp_path / "library.db"
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
    app, engine, window = _qml_engine(view_model, runtime_composition=composition)
    window.show()
    try:
        # Real AnalysisUiState error phase (not a synthetic progress clock).
        view_model.set_analysis_state(
            AnalysisUiState(folder_id=9, phase="error", error="Analyse fehlgeschlagen.")
        )
        engine._screen1_analysis_fail_closed()
        engine._screen1_screen_model.refresh()
        engine._screen1_interaction_bridge.refreshState()
        app.processEvents()

        surface = window.findChild(QQuickItem, "analysisWorkingSurface")
        cancel = window.findChild(QQuickItem, "analysisCancelButton")
        browser = window.findChild(QQuickItem, "browserPane")
        live_kit = window.findChild(QQuickItem, "liveKitPane")
        harmony = window.findChild(QQuickItem, "harmonyPane")
        assert view_model.analysis_status == "error"
        assert view_model.analysis_error == "Analyse fehlgeschlagen."
        assert surface is not None and surface.isVisible()
        assert cancel is None or not cancel.isVisible()
        assert browser is not None and not browser.isVisible()
        assert live_kit is not None and not live_kit.isVisible()
        assert harmony is not None
        assert float(harmony.width()) == 0 or float(harmony.opacity()) == 0
        assert engine._screen1_interaction_adapter.harmonic_match_open is False
        assert composition.has_active_source is False
        assert view_model.selected_browser_index == -1
        assert engine._screen1_interaction_adapter.preview_active is False
    finally:
        _shutdown_engine(app, engine, window)


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_success_exits_overlay_browser_first_no_auto_actions(tmp_path: Path):
    from PySide6.QtQuick import QQuickItem

    from src.workbench_library_navigation import WorkbenchLibraryNavigation
    from src.workbench_qml import Screen1QmlViewModel, _qml_engine
    from src.workbench_qml_library import WorkbenchLibraryTreeState

    db = tmp_path / "library.db"
    source = _new_unanalyzed_source(tmp_path)
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
    app, engine, window = _qml_engine(view_model, runtime_composition=composition)
    window.show()
    try:
        adapter = engine._screen1_interaction_adapter
        library_bridge = engine._screen1_library_bridge
        library_bridge.registerSourceUrl(str(source))
        app.processEvents()
        assert view_model.analysis_status in {"scanning", "analyzing"}
        assert _wait_for_analysis(app, view_model)
        app.processEvents()

        surface = window.findChild(QQuickItem, "analysisWorkingSurface")
        browser = window.findChild(QQuickItem, "browserPane")
        live_kit = window.findChild(QQuickItem, "liveKitPane")
        harmony = window.findChild(QQuickItem, "harmonyPane")
        assert surface is None or not surface.isVisible()
        assert composition.has_active_source is True
        assert view_model.browser_materialized is True
        assert browser is not None and browser.isVisible()
        assert composition.live_kit_revealed is False
        assert view_model.live_kit_materialized is False
        assert live_kit is not None and not live_kit.isVisible()
        assert adapter.harmonic_match_open is False
        assert harmony is not None
        assert float(harmony.width()) == 0 or float(harmony.opacity()) == 0
        assert view_model.selected_browser_index == -1
        assert adapter.preview_active is False
        assert composition.audition_dispatches == []
    finally:
        _shutdown_engine(app, engine, window)


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_real_progress_projection_not_fake_timer(tmp_path: Path):
    from PySide6.QtQuick import QQuickItem

    from src.workbench_library_navigation import WorkbenchLibraryNavigation
    from src.workbench_qml import Screen1QmlViewModel, _qml_engine
    from src.workbench_qml_library import WorkbenchLibraryTreeState

    db = tmp_path / "library.db"
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
    app, engine, window = _qml_engine(view_model, runtime_composition=composition)
    window.show()
    try:
        _project_analysis(
            view_model=view_model,
            engine=engine,
            app=app,
            state=AnalysisUiState(
                folder_id=3,
                phase="analyzing",
                current=3,
                total=4,
                display_name="near.wav",
            ),
        )
        fill = window.findChild(QQuickItem, "analysisProgressFill")
        track = window.findChild(QQuickItem, "analysisProgressTrack")
        assert track is not None and track.isVisible()
        assert fill is not None and fill.isVisible()
        assert view_model.analysis_current == 3
        assert view_model.analysis_total == 4
        # Width fraction must track real current/total (allow layout settle).
        track_w = float(track.width())
        fill_w = float(fill.width())
        assert track_w > 0
        assert abs(fill_w / track_w - 0.75) < 0.08
    finally:
        _shutdown_engine(app, engine, window)
