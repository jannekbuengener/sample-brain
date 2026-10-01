"""#786 Brand/motion QML wiring on analysisWorkingSurface only.

Real AnalysisUiState + brand_runtime_payload. No fake progress timers.
Header stays brand-clean.
"""

from __future__ import annotations

import importlib.util
import time
from pathlib import Path

import pytest

from src.workbench_brand_motion import brand_runtime_payload
from src.workbench_qml import QML_SOURCE
from src.workbench_qml_analysis import AnalysisUiState

PY_SIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None


def test_qml_declares_786_analysis_brand_surface_only():
    assert "analysisBrandBrain" in QML_SOURCE
    assert "brandMotionLayer" in QML_SOURCE
    assert "brandRuntime" in QML_SOURCE
    assert "analysisBrandSampleName" in QML_SOURCE

    header_start = QML_SOURCE.index("id: screen1Header")
    header_end = QML_SOURCE.index("id: workspaceRow")
    header = QML_SOURCE[header_start:header_end]
    assert "analysisBrandBrain" not in header
    assert "brandMotionLayer" not in header
    assert "SAMPLE BRAIN" not in header
    assert "Frech aber im Flow" not in header

    surface_start = QML_SOURCE.index("id: analysisWorkingSurface")
    surface = QML_SOURCE[surface_start : surface_start + 12000]
    assert "analysisBrandBrain" in surface
    assert "brandMotionLayer" in surface
    # No fake progress clock / width Behavior on progress.
    assert "Timer {" not in surface
    assert "Behavior on width" not in surface
    assert "brandRuntime.progressKind" in surface
    assert "brandRuntime.progressRatio" in surface
    assert "brandRuntime.motionActive" in surface
    assert "brandRuntime.reducedMotion" in surface
    assert "brandRuntime.staticFallback" in surface


def test_progress_fill_uses_brand_runtime_not_local_invention():
    surface_start = QML_SOURCE.index("id: analysisWorkingSurface")
    surface = QML_SOURCE[surface_start : surface_start + 12000]
    assert "brandRuntime.progressKind" in surface
    assert "brandRuntime.progressRatio" in surface
    assert "brandRuntime.motionActive" in surface
    assert "brandRuntime.reducedMotion" in surface
    assert "brandRuntime.staticFallback" in surface
    fill_idx = surface.index("objectName: \"analysisProgressFill\"")
    fill_chunk = surface[fill_idx : fill_idx + 1200]
    assert "brandRuntime.progressKind" in fill_chunk
    assert "Timer" not in fill_chunk
    assert "Behavior on width" not in fill_chunk


def _project_analysis(*, view_model, engine, app, state: AnalysisUiState) -> None:
    view_model.set_analysis_state(state)
    view_model.set_workspace_materialization(
        has_active_source=False,
        calm_canvas_visible=state.phase not in {"scanning", "analyzing", "error"},
        browser_materialized=False,
        live_kit_materialized=False,
    )
    refresh = getattr(engine, "_screen1_refresh_brand_runtime", None)
    if callable(refresh):
        refresh()
    engine._screen1_screen_model.refresh()
    engine._screen1_interaction_bridge.refreshState()
    layout = getattr(engine, "_screen1_layout_model", None)
    if layout is not None:
        layout.syncFromInteraction()
    app.processEvents()


def _shutdown(app, engine, window) -> None:
    coordinator = getattr(engine, "_screen1_analysis_coordinator", None)
    if coordinator is not None:
        coordinator.shutdown()
    window.close()
    engine.deleteLater()
    app.processEvents()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_analysis_surface_binds_brand_payload_and_motion_modes(
    tmp_path: Path, monkeypatch
):
    from PySide6.QtQuick import QQuickItem

    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path / "state"))
    from src.workbench_library_navigation import WorkbenchLibraryNavigation
    from src.workbench_qml import Screen1QmlViewModel, _qml_engine
    from src.workbench_qml_library import WorkbenchLibraryTreeState
    from src.workbench_qml_runtime import Screen1QmlRuntimeComposition

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
        brand = engine.rootContext().contextProperty("brandRuntime")
        assert brand is not None
        adapter = engine._screen1_interaction_adapter

        _project_analysis(
            view_model=view_model,
            engine=engine,
            app=app,
            state=AnalysisUiState(
                folder_id=1,
                phase="analyzing",
                current=2,
                total=5,
                display_name="kick.wav",
                token=7,
            ),
        )
        expected = brand_runtime_payload(
            AnalysisUiState(
                folder_id=1,
                phase="analyzing",
                current=2,
                total=5,
                display_name="kick.wav",
                token=7,
            ),
            "on",
            expected_token=7,
        )
        assert brand.progressKind == expected["progressKind"]
        assert abs(float(brand.progressRatio) - float(expected["progressRatio"])) < 1e-6
        assert brand.sampleName == "kick.wav"
        assert brand.motionActive is True
        assert brand.headerPermitsPermanentBranding is False

        brain = window.findChild(QQuickItem, "analysisBrandBrain")
        motion = window.findChild(QQuickItem, "brandMotionLayer")
        surface = window.findChild(QQuickItem, "analysisWorkingSurface")
        assert surface is not None and surface.isVisible()
        assert brain is not None and brain.isVisible()
        assert motion is not None

        adapter.set_waveform_motion_mode("reduced")
        _project_analysis(
            view_model=view_model,
            engine=engine,
            app=app,
            state=AnalysisUiState(
                folder_id=1,
                phase="analyzing",
                current=2,
                total=5,
                display_name="kick.wav",
                token=7,
            ),
        )
        assert brand.reducedMotion is True
        assert brand.motionActive is True
        assert brand.staticFallback is False

        adapter.set_waveform_motion_mode("off")
        _project_analysis(
            view_model=view_model,
            engine=engine,
            app=app,
            state=AnalysisUiState(
                folder_id=1,
                phase="analyzing",
                current=2,
                total=5,
                display_name="kick.wav",
                token=7,
            ),
        )
        assert brand.motionMode == "off"
        assert brand.motionActive is False
        assert brand.staticFallback is True
        assert brain.isVisible()  # static high-quality brain still present

        # Stale token must not drive sample-name / progress motion.
        _project_analysis(
            view_model=view_model,
            engine=engine,
            app=app,
            state=AnalysisUiState(
                folder_id=1,
                phase="analyzing",
                current=4,
                total=5,
                display_name="stale.wav",
                token=99,
            ),
        )
        refresh = getattr(engine, "_screen1_refresh_brand_runtime", None)
        if callable(refresh):
            refresh(expected_token=7)
            app.processEvents()
        assert brand.stale is True
        assert brand.sampleName == ""
        assert brand.motionActive is False
    finally:
        _shutdown(app, engine, window)


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_indeterminate_scanning_has_no_fake_percent(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path / "state"))
    from src.workbench_library_navigation import WorkbenchLibraryNavigation
    from src.workbench_qml import Screen1QmlViewModel, _qml_engine
    from src.workbench_qml_library import WorkbenchLibraryTreeState
    from src.workbench_qml_runtime import Screen1QmlRuntimeComposition

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
    try:
        brand = engine.rootContext().contextProperty("brandRuntime")
        _project_analysis(
            view_model=view_model,
            engine=engine,
            app=app,
            state=AnalysisUiState(folder_id=1, phase="scanning", current=0, total=0),
        )
        assert brand.progressKind == "indeterminate"
        assert float(brand.progressRatio) < 0.0
        # Give the UI a brief moment; progress must not invent a climbing ratio.
        deadline = time.monotonic() + 0.2
        while time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.02)
            assert float(brand.progressRatio) < 0.0
            assert brand.progressKind == "indeterminate"
    finally:
        _shutdown(app, engine, window)
