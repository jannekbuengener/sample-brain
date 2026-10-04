"""#786 Brand / analysis motion QML runtime — FROZEN RED CONTRACT.

Integrates #795 Brand/Motion Core into Screen-1 analysis/loading QML.
Python owns analysis + projection truth; QML visualizes only.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

from src.workbench_brand_motion import (
    BRAND_CLAIM,
    SCREEN1_HEADER_PERMITS_PERMANENT_BRANDING,
    project_analysis_motion,
    resolve_brand_slots,
)
from src.workbench_display_preferences import MOTION_OFF, MOTION_ON, MOTION_REDUCED
from src.workbench_qml import QML_SOURCE
from src.workbench_qml_analysis import AnalysisUiState

PY_SIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None
REPO_ROOT = Path(__file__).resolve().parents[1]


def _header_block() -> str:
    start = QML_SOURCE.index('objectName: "screen1Header"')
    # Producer zone follows immediately after the left identity.
    end = QML_SOURCE.index('objectName: "headerNavZone"', start)
    return QML_SOURCE[start:end]


def _analysis_surface_block() -> str:
    start = QML_SOURCE.index("id: analysisWorkingSurface")
    end = QML_SOURCE.index("id: browserPane", start)
    return QML_SOURCE[start:end]


def test_screen1_header_forbids_permanent_brand_lockup() -> None:
    assert SCREEN1_HEADER_PERMITS_PERMANENT_BRANDING is False
    header = _header_block()
    assert "analysisBrandBrain" not in header
    assert "SAMPLE BRAIN" not in header
    assert BRAND_CLAIM not in header
    assert "sample_brain_logo_primary" not in header
    assert "splash_typography" not in header
    # Product identity text is allowed; brand lockup/logo are not.
    assert "Sample Brain" in header


def test_qml_declares_786_brand_motion_analysis_surface() -> None:
    surface = _analysis_surface_block()
    assert 'objectName: "analysisBrandBrain"' in surface
    assert 'objectName: "brandMotionLayer"' in surface
    assert 'objectName: "analysisBrandSampleName"' in surface
    assert "brandMotion" in surface or "screenData.brand" in surface
    # No invented progress clock.
    assert "Timer {" not in surface
    # Progress fill must stay non-animated (real current/total only).
    fill_idx = surface.index('objectName: "analysisProgressFill"')
    fill_chunk = surface[fill_idx : fill_idx + 700]
    assert "NumberAnimation" not in fill_chunk
    assert "Behavior on width" not in fill_chunk
    # Brand motion animations, if any, live only inside brandMotionLayer.
    motion_idx = surface.index('objectName: "brandMotionLayer"')
    # Find the brandMotionLayer item body roughly until analysisStatusLabel /
    # progress content continues — animations may appear only after that marker
    # and before the progress track when declared as a nested layer.
    assert "brandMotionLayer" in surface
    # Claim must not appear as permanent analysis chrome.
    assert BRAND_CLAIM not in surface


def test_qml_brand_motion_binds_python_projection_not_local_math() -> None:
    surface = _analysis_surface_block()
    # Determinate width must consume projected ratio / analysis totals — no
    # invented local percent literals beyond the indeterminate visual cue.
    assert "brandProgressKind" in QML_SOURCE
    assert "brandStaticFallback" in QML_SOURCE
    assert "brandMotionMode" in QML_SOURCE
    assert "brandReducedMotion" in QML_SOURCE
    assert "window.screenData.brandProgressKind" in surface
    assert "window.screenData.brandStaticFallback" in surface
    assert "window.screenData.brandReducedMotion" in surface
    assert "window.screenData.brandBrainUrl" in surface


def test_brand_runtime_payload_matches_core_projection() -> None:
    from src.workbench_brand_motion import brand_runtime_payload

    slots = resolve_brand_slots(repo_root=REPO_ROOT)
    state = AnalysisUiState(
        folder_id=3,
        phase="analyzing",
        current=2,
        total=4,
        display_name="kick.wav",
        token=9,
    )
    payload = brand_runtime_payload(
        state,
        MOTION_ON,
        expected_token=9,
        repo_root=REPO_ROOT,
    )
    projection = project_analysis_motion(state, MOTION_ON, expected_token=9)
    assert payload["phase"] == projection.phase
    assert payload["progressKind"] == projection.progress_kind
    assert payload["progressRatio"] == pytest.approx(projection.progress_ratio or -1.0)
    assert payload["sampleName"] == "kick.wav"
    assert payload["motionMode"] == MOTION_ON
    assert payload["motionActive"] is True
    assert payload["reducedMotion"] is False
    assert payload["staticFallback"] is False
    assert payload["stale"] is False
    assert payload["brainUrl"].startswith("file:")
    assert Path(slots["brain_symbol"].path).as_uri() == payload["brainUrl"]
    assert payload["headerPermitsPermanentBranding"] is False


def test_brand_runtime_payload_motion_modes_and_stale() -> None:
    from src.workbench_brand_motion import brand_runtime_payload

    state = AnalysisUiState(
        phase="scanning",
        current=0,
        total=0,
        display_name="scan.wav",
        token=2,
    )
    on = brand_runtime_payload(state, MOTION_ON, expected_token=2, repo_root=REPO_ROOT)
    assert on["progressKind"] == "indeterminate"
    assert on["progressRatio"] == pytest.approx(-1.0)
    assert on["motionActive"] is True
    assert on["staticFallback"] is False

    reduced = brand_runtime_payload(
        state, MOTION_REDUCED, expected_token=2, repo_root=REPO_ROOT
    )
    assert reduced["reducedMotion"] is True
    assert reduced["motionActive"] is True
    assert reduced["staticFallback"] is False

    off = brand_runtime_payload(state, MOTION_OFF, expected_token=2, repo_root=REPO_ROOT)
    assert off["staticFallback"] is True
    assert off["motionActive"] is False

    stale = brand_runtime_payload(
        AnalysisUiState(
            phase="analyzing",
            current=3,
            total=4,
            display_name="late.wav",
            token=1,
        ),
        MOTION_ON,
        expected_token=2,
        repo_root=REPO_ROOT,
    )
    assert stale["stale"] is True
    assert stale["sampleName"] == ""
    assert stale["progressKind"] == "none"
    assert stale["progressRatio"] == pytest.approx(-1.0)
    assert stale["staticFallback"] is True


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_runtime_exposes_brand_projection_and_brain_on_analysis_surface(
    tmp_path: Path,
) -> None:
    from PySide6.QtQuick import QQuickItem

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
        adapter = engine._screen1_interaction_adapter
        adapter.set_waveform_motion_mode(MOTION_ON)
        view_model.set_analysis_state(
            AnalysisUiState(
                folder_id=1,
                phase="analyzing",
                current=1,
                total=4,
                display_name="snare.wav",
                token=5,
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
        app.processEvents()

        surface = window.findChild(QQuickItem, "analysisWorkingSurface")
        brain = window.findChild(QQuickItem, "analysisBrandBrain")
        sample = window.findChild(QQuickItem, "analysisBrandSampleName")
        motion = window.findChild(QQuickItem, "brandMotionLayer")
        header = window.findChild(QQuickItem, "screen1Header")
        assert surface is not None and surface.isVisible()
        assert brain is not None and brain.isVisible()
        assert motion is not None
        assert sample is not None
        # Sample name visible from real display_name.
        sample_text = str(sample.property("text") or "")
        assert "snare.wav" in sample_text
        # Header must not host the brain brand image.
        assert header is not None
        header_brain = None
        for child in header.findChildren(QQuickItem, "analysisBrandBrain"):
            header_brain = child
        assert header_brain is None

        ctx = view_model.qml_context()
        assert ctx["brandProgressKind"] == "determinate"
        assert ctx["brandProgressRatio"] == pytest.approx(0.25)
        assert ctx["brandSampleName"] == "snare.wav"
        assert ctx["brandMotionMode"] == MOTION_ON
        assert ctx["brandStaticFallback"] is False
        assert str(ctx["brandBrainUrl"]).startswith("file:")
    finally:
        coordinator = getattr(engine, "_screen1_analysis_coordinator", None)
        if coordinator is not None:
            coordinator.shutdown()
        window.close()
        engine.deleteLater()
        app.processEvents()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_runtime_motion_off_static_fallback_and_reduced_path(tmp_path: Path) -> None:
    from PySide6.QtQuick import QQuickItem

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
        adapter = engine._screen1_interaction_adapter
        view_model.set_analysis_state(
            AnalysisUiState(
                folder_id=1,
                phase="scanning",
                current=0,
                total=0,
                display_name="scan.wav",
                token=1,
            )
        )
        view_model.set_workspace_materialization(
            has_active_source=False,
            calm_canvas_visible=False,
            browser_materialized=False,
            live_kit_materialized=False,
        )

        for mode, expect_static, expect_reduced in (
            (MOTION_OFF, True, False),
            (MOTION_REDUCED, False, True),
            (MOTION_ON, False, False),
        ):
            adapter.set_waveform_motion_mode(mode)
            engine._screen1_screen_model.refresh()
            engine._screen1_interaction_bridge.refreshState()
            app.processEvents()
            ctx = view_model.qml_context()
            assert ctx["brandMotionMode"] == mode
            assert ctx["brandStaticFallback"] is expect_static
            assert ctx["brandReducedMotion"] is expect_reduced
            assert ctx["brandProgressKind"] == "indeterminate"
            motion = window.findChild(QQuickItem, "brandMotionLayer")
            assert motion is not None
            # Distinct reduced vs full path encoded on the layer.
            assert bool(motion.property("reducedMotion")) is expect_reduced
            assert bool(motion.property("staticFallback")) is expect_static
    finally:
        coordinator = getattr(engine, "_screen1_analysis_coordinator", None)
        if coordinator is not None:
            coordinator.shutdown()
        window.close()
        engine.deleteLater()
        app.processEvents()


def test_existing_744_surface_still_forbids_fake_progress_timer() -> None:
    """#744/#786: no Timer-based fake progress; brand motion is gated separately."""
    surface = _analysis_surface_block()
    assert "Timer {" not in surface
    # Any NumberAnimation must sit inside brandMotionLayer, never on progress fill.
    for match in re.finditer(r"NumberAnimation\s*\{", surface):
        before = surface[: match.start()]
        assert before.rfind('objectName: "brandMotionLayer"') > before.rfind(
            'objectName: "analysisProgressFill"'
        ) or 'objectName: "brandMotionLayer"' in before[-800:]
