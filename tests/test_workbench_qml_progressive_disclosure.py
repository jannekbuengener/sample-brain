"""#742 Post-analysis progressive disclosure contracts.

Browser materializes only after successful analysis / explicit analyzed Source
selection. Harmonic Match stays opt-in. Live Kit reveals only on Add-to-Kit.
Transient disclosure is never persisted.

Analysis loading visuals / blocking overlay ownership: #744
(`tests/test_workbench_qml_analysis_loading.py`).
"""

from __future__ import annotations

import importlib.util
import math
import time
from pathlib import Path

import pytest

from src.workbench_layout_solver import (
    CANONICAL_DEFAULT_RATIOS,
    HANDLE_WIDTH_PX,
    apply_divider_drag,
    load_layout_preferences,
    save_layout_preferences,
    solve_widths,
    visible_panel_ids,
)
from src.workbench_qml import QML_SOURCE, QmlHarmonyRow
from src.workbench_qml_runtime import Screen1QmlRuntimeComposition

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


def _wait_for_analysis(app, coordinator, folder_id, view_model, *, timeout_sec=90.0) -> bool:
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


def _select_first_root(composition, library_bridge, library_model, app) -> str:
    library_model.replaceBranch("container:sample-sources")
    app.processEvents()
    nodes = list(composition.library_tree.fetch_children("container:sample-sources"))
    assert nodes, "expected registered root"
    node_id = nodes[0].node_id
    library_bridge.selectLibraryNode(node_id)
    app.processEvents()
    return node_id


# --- Pure disclosure / layout contracts --------------------------------------


def test_runtime_live_kit_stays_hidden_until_reveal():
    composition = Screen1QmlRuntimeComposition()
    assert composition.live_kit_revealed is False
    assert composition.live_kit_materialized is False
    composition.reveal_live_kit()
    assert composition.live_kit_revealed is True
    assert composition.live_kit_materialized is False


def test_runtime_clear_no_scope_resets_live_kit_disclosure():
    composition = Screen1QmlRuntimeComposition()
    composition.reveal_live_kit()
    composition.clear_no_scope()
    assert composition.live_kit_revealed is False
    assert composition.live_kit_materialized is False


def test_visible_panels_browser_only_without_live_kit_reveal():
    assert visible_panel_ids(
        harmony_open=False,
        has_active_source=True,
        live_kit_visible=False,
    ) == ("library", "browser")
    assert visible_panel_ids(
        harmony_open=True,
        has_active_source=True,
        live_kit_visible=False,
    ) == ("library", "browser", "harmony")
    # #908: live_kit_visible no longer allocates a horizontal panel.
    assert visible_panel_ids(
        harmony_open=False,
        has_active_source=True,
        live_kit_visible=True,
    ) == ("library", "browser")


def test_visible_panels_exclude_collapsed_library():
    """#725+#742: collapsed Library must not reserve elastic width."""
    assert visible_panel_ids(
        harmony_open=False,
        has_active_source=True,
        library_visible=False,
        live_kit_visible=False,
    ) == ("browser",)
    assert visible_panel_ids(
        harmony_open=True,
        has_active_source=True,
        library_visible=False,
        live_kit_visible=False,
    ) == ("browser", "harmony")
    assert visible_panel_ids(
        harmony_open=False,
        has_active_source=True,
        library_visible=False,
        live_kit_visible=True,
    ) == ("browser",)


def test_collapsed_library_gives_browser_full_content_width():
    available = 1600.0
    solution = solve_widths(
        CANONICAL_DEFAULT_RATIOS,
        available_width=available,
        harmony_open=False,
        has_active_source=True,
        library_visible=False,
        live_kit_visible=False,
    )
    assert set(solution.widths) == {"browser"}
    assert abs(solution.widths["browser"] - available) < 1e-6
    assert solution.ratios == CANONICAL_DEFAULT_RATIOS


def test_pane_reveal_hide_does_not_drift_stored_ratios():
    ratios = dict(CANONICAL_DEFAULT_RATIOS)
    available = 1600.0
    browser_only = solve_widths(
        ratios,
        available_width=available,
        harmony_open=False,
        has_active_source=True,
        live_kit_visible=False,
    )
    with_kit = solve_widths(
        ratios,
        available_width=available,
        harmony_open=False,
        has_active_source=True,
        live_kit_visible=True,
    )
    with_harmony = solve_widths(
        ratios,
        available_width=available,
        harmony_open=True,
        has_active_source=True,
        live_kit_visible=True,
    )
    back_to_kit = solve_widths(
        with_harmony.ratios,
        available_width=available,
        harmony_open=False,
        has_active_source=True,
        live_kit_visible=True,
    )
    clean = solve_widths(
        back_to_kit.ratios,
        available_width=available,
        harmony_open=False,
        has_active_source=False,
        live_kit_visible=False,
    )
    assert browser_only.ratios == ratios
    assert with_kit.ratios == ratios
    assert with_harmony.ratios == ratios
    assert back_to_kit.ratios == ratios
    assert clean.ratios == ratios
    assert "livekit" not in browser_only.widths
    assert browser_only.widths["browser"] > 0
    # #908: live_kit_visible no longer adds a horizontal livekit width.
    assert "livekit" not in with_kit.widths
    assert with_kit.widths["browser"] > 0
    assert all(math.isfinite(w) and w > 0 for w in with_harmony.widths.values())
    assert "livekit" not in with_harmony.widths


def test_qml_declares_analysis_surface_and_live_kit_reveal_binding():
    assert "analysisWorkingSurface" in QML_SOURCE
    assert "liveKitRevealed" in QML_SOURCE
    assert "analysisCancelButton" in QML_SOURCE
    assert 'objectName: "bottomRackPane"' in QML_SOURCE
    assert "visible: window.interaction.hasActiveSource" in QML_SOURCE
    assert "bottomRackMaterialized" in QML_SOURCE


def test_disclosure_state_is_not_in_layout_preference_payload(tmp_path: Path):
    save_layout_preferences(CANONICAL_DEFAULT_RATIOS, state_dir=tmp_path)
    loaded = load_layout_preferences(state_dir=tmp_path)
    serialized = str(dict(loaded.ratios))
    assert "live_kit_revealed" not in serialized
    assert "liveKitRevealed" not in serialized


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_elastic_bridge_collapsed_library_browser_fills_width(tmp_path: Path):
    from src.workbench_qml_elastic import create_elastic_layout_bridge

    active = {"value": True}
    revealed = {"value": False}
    kit = {"value": False}
    bridge = create_elastic_layout_bridge(
        state_dir=tmp_path,
        harmony_open=lambda: False,
        has_active_source=lambda: active["value"],
        library_revealed=lambda: revealed["value"],
        live_kit_visible=lambda: kit["value"],
    )
    available = 1600.0
    bridge.setContentWidth(available)
    assert bridge.libraryWidth == 0.0
    assert bridge.liveKitWidth == 0.0
    assert bridge.harmonyWidth == 0.0
    assert abs(bridge.browserWidth - available) < 1.0

    revealed["value"] = True
    bridge.syncFromInteraction()
    assert bridge.libraryWidth > 0.0
    assert bridge.browserWidth > 0.0
    assert abs(bridge.libraryWidth + bridge.browserWidth + HANDLE_WIDTH_PX - available) < 1.0


def test_ratio_solver_drag_stable_across_live_kit_reveal_toggle():
    ratios = dict(CANONICAL_DEFAULT_RATIOS)
    available = 1600.0
    before = dict(ratios)
    after_reveal = apply_divider_drag(
        ratios,
        divider_after="library",
        delta_px=20.0,
        available_width=available,
        harmony_open=False,
        has_active_source=True,
        live_kit_visible=False,
    )
    after_hide = apply_divider_drag(
        after_reveal,
        divider_after="library",
        delta_px=-20.0,
        available_width=available,
        harmony_open=False,
        has_active_source=True,
        live_kit_visible=False,
    )
    assert set(after_hide) == set(before)
    assert abs(sum(after_hide.values()) - 1.0) < 1e-9
    assert all(math.isfinite(v) and v > 0 for v in after_hide.values())


# --- QML runtime progressive disclosure --------------------------------------


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_add_source_analysis_hides_working_panes_until_success(tmp_path: Path):
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
        library_bridge = engine._screen1_library_bridge
        adapter = engine._screen1_interaction_adapter
        coordinator = engine._screen1_analysis_coordinator

        library_bridge.registerSourceUrl(str(source))
        app.processEvents()

        assert view_model.analysis_status in {"scanning", "analyzing"}
        assert composition.has_active_source is False
        assert view_model.browser_materialized is False
        assert view_model.live_kit_materialized is False
        assert adapter.harmonic_match_open is False
        assert adapter.preview_active is False
        assert view_model.selected_browser_index == -1

        browser = window.findChild(QQuickItem, "browserPane")
        live_kit = window.findChild(QQuickItem, "liveKitPane")
        bottom = window.findChild(QQuickItem, "bottomRackPane")
        analysis_surface = window.findChild(QQuickItem, "analysisWorkingSurface")
        cancel = window.findChild(QQuickItem, "analysisCancelButton")
        assert browser is not None and not browser.isVisible()
        assert live_kit is not None and not live_kit.isVisible()
        assert bottom is not None and not bottom.isVisible()
        assert analysis_surface is not None and analysis_surface.isVisible()
        assert cancel is not None and cancel.isVisible()

        folder_id = view_model.analysis_folder_id
        assert folder_id is not None
        assert _wait_for_analysis(app, coordinator, folder_id, view_model)
        app.processEvents()

        assert composition.has_active_source is True
        assert library_bridge.selectedLibraryNodeId == f"root:{folder_id}"
        assert view_model.browser_materialized is True
        assert view_model.selected_browser_index == -1
        assert adapter.preview_active is False
        assert adapter.harmonic_match_open is False
        assert composition.live_kit_revealed is False
        assert view_model.live_kit_materialized is False
        assert browser.isVisible()
        # #908: calm bottom strip is present once a source is active (empty Rack).
        assert live_kit.isVisible()
        assert bottom.isVisible()
        assert bottom.height() <= 40
        analysis_surface = window.findChild(QQuickItem, "analysisWorkingSurface")
        assert analysis_surface is None or not analysis_surface.isVisible()
    finally:
        _shutdown_engine(app, engine, window)


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_browser_and_harmony_add_to_kit_reveal_live_kit(tmp_path: Path):
    from PySide6.QtQuick import QQuickItem

    from src.workbench_library_navigation import WorkbenchLibraryNavigation
    from src.workbench_qml import (
        Screen1QmlViewModel,
        _qml_engine,
        apply_clean_start_launch,
    )
    from src.workbench_qml_library import WorkbenchLibraryTreeState

    _root, db = _register_analyzed_root(tmp_path)
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
    apply_clean_start_launch(view_model, composition)
    app, engine, window = _qml_engine(view_model, runtime_composition=composition)
    window.show()
    try:
        adapter = engine._screen1_interaction_adapter
        library_bridge = engine._screen1_library_bridge
        library_model = engine._screen1_library_model

        _select_first_root(composition, library_bridge, library_model, app)

        browser = window.findChild(QQuickItem, "browserPane")
        live_kit = window.findChild(QQuickItem, "liveKitPane")
        bottom = window.findChild(QQuickItem, "bottomRackPane")
        assert composition.has_active_source is True
        assert browser is not None and browser.isVisible()
        assert live_kit is not None and live_kit.isVisible()
        assert bottom is not None and bottom.isVisible()
        empty_height = bottom.height()
        assert empty_height <= 40
        assert composition.live_kit_revealed is False
        assert len(view_model.browser_rows) >= 1

        adapter.request_add_to_kit(0)
        engine._screen1_interaction_bridge.refreshState()
        app.processEvents()
        assert composition.live_kit_revealed is True
        assert view_model.live_kit_materialized is True
        assert live_kit.isVisible()
        # Occupied one-shot assignment expands the bottom Rack band.
        rack = engine.rootContext().contextProperty("channelRackModel")
        if rack is not None:
            rack.refresh()
            app.processEvents()
        assert bottom.height() >= empty_height

        composition.clear_live_kit_disclosure()
        view_model.set_workspace_materialization(
            has_active_source=True,
            calm_canvas_visible=False,
            browser_materialized=True,
            live_kit_materialized=False,
        )
        engine._screen1_interaction_bridge.refreshState()
        app.processEvents()
        # #908: strip remains while source is active; disclosure flag alone does not hide it.
        assert live_kit.isVisible()
        assert bottom.isVisible()

        adapter.select_row(0)
        assert adapter.toggle_harmonic_match() is True
        assert adapter.harmonic_match_open is True
        src_row = view_model.browser_rows[0].source_row
        view_model.harmony_rows = (
            QmlHarmonyRow(
                source_row=src_row,
                display_name=src_row.display_name,
                sample_type=view_model.browser_rows[0].sample_type,
                key=view_model.browser_rows[0].key,
                waveform_envelope=(),
                fit="exact",
                relation="same",
                explanation="test",
            ),
        )
        engine._screen1_screen_model.refresh()
        adapter.request_add_harmonic_match_to_kit(0)
        engine._screen1_interaction_bridge.refreshState()
        app.processEvents()
        assert composition.live_kit_revealed is True
        assert live_kit.isVisible()
    finally:
        _shutdown_engine(app, engine, window)


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_analysis_cancel_fail_closed(tmp_path: Path):
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
        library_bridge = engine._screen1_library_bridge
        adapter = engine._screen1_interaction_adapter
        screen_model = engine._screen1_screen_model

        library_bridge.registerSourceUrl(str(source))
        app.processEvents()
        assert view_model.analysis_folder_id is not None
        assert view_model.analysis_status in {"scanning", "analyzing"}

        screen_model.cancelAnalysis()
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            app.processEvents()
            if view_model.analysis_status in {"idle", "cancelled", "error"}:
                break
            time.sleep(0.05)
        app.processEvents()

        browser = window.findChild(QQuickItem, "browserPane")
        live_kit = window.findChild(QQuickItem, "liveKitPane")
        assert composition.has_active_source is False
        assert view_model.browser_materialized is False
        assert view_model.live_kit_materialized is False
        assert adapter.harmonic_match_open is False
        assert adapter.preview_active is False
        assert view_model.selected_browser_index == -1
        assert browser is not None and not browser.isVisible()
        assert live_kit is not None and not live_kit.isVisible()
        assert view_model.analysis_status == "idle"
    finally:
        _shutdown_engine(app, engine, window)


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_analysis_failure_fail_closed(tmp_path: Path):
    from PySide6.QtQuick import QQuickItem

    from src.workbench_library_navigation import WorkbenchLibraryNavigation
    from src.workbench_qml import Screen1QmlViewModel, _qml_engine
    from src.workbench_qml_analysis import AnalysisUiState
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
        fail_closed = engine._screen1_analysis_fail_closed
        view_model.set_analysis_state(
            AnalysisUiState(folder_id=1, phase="error", error="Analyse fehlgeschlagen.")
        )
        fail_closed()
        engine._screen1_interaction_bridge.refreshState()
        app.processEvents()

        browser = window.findChild(QQuickItem, "browserPane")
        live_kit = window.findChild(QQuickItem, "liveKitPane")
        assert composition.has_active_source is False
        assert view_model.browser_materialized is False
        assert view_model.live_kit_materialized is False
        assert browser is not None and not browser.isVisible()
        assert live_kit is not None and not live_kit.isVisible()
    finally:
        _shutdown_engine(app, engine, window)


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_return_to_clean_start_resets_live_kit_disclosure(tmp_path: Path):
    from PySide6.QtQuick import QQuickItem

    from src.workbench_library_navigation import WorkbenchLibraryNavigation
    from src.workbench_qml import (
        Screen1QmlViewModel,
        _qml_engine,
        apply_clean_start_launch,
    )
    from src.workbench_qml_library import WorkbenchLibraryTreeState

    root, db = _register_analyzed_root(tmp_path)
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
    apply_clean_start_launch(view_model, composition)
    app, engine, window = _qml_engine(view_model, runtime_composition=composition)
    window.show()
    try:
        adapter = engine._screen1_interaction_adapter
        library_bridge = engine._screen1_library_bridge
        library_model = engine._screen1_library_model

        _select_first_root(composition, library_bridge, library_model, app)
        adapter.request_add_to_kit(0)
        assert composition.live_kit_revealed is True

        adapter.return_to_clean_start_action()
        engine._screen1_interaction_bridge.refreshState()
        app.processEvents()

        assert composition.live_kit_revealed is False
        assert composition.has_active_source is False
        assert view_model.browser_materialized is False
        assert view_model.live_kit_materialized is False
        browser = window.findChild(QQuickItem, "browserPane")
        live_kit = window.findChild(QQuickItem, "liveKitPane")
        assert browser is not None and not browser.isVisible()
        assert live_kit is not None and not live_kit.isVisible()
        assert root.exists()
    finally:
        _shutdown_engine(app, engine, window)
