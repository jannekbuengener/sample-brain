"""QML projection + bridge contracts for #694 elastic layout.

Canon: docs/WORKBENCH_ELASTIC_LAYOUT.md
Contract 11: Browser keyboard / Search focus / Esc remain intact.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from src.workbench_layout_solver import (
    CANONICAL_DEFAULT_RATIOS,
    HANDLE_WIDTH_PX,
    load_layout_preferences,
)
from src.workbench_qml import QML_SOURCE
from src.workbench_qml_elastic import create_elastic_layout_bridge

PY_SIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None


def test_qml_projects_layout_model_widths_and_handles():
    assert "layoutModel.setContentWidth(width)" in QML_SOURCE
    assert "width: layoutModel.libraryWidth" in QML_SOURCE
    assert "layoutModel.browserWidth" in QML_SOURCE
    assert "layoutModel.harmonyWidth" in QML_SOURCE
    # #908: liveKitWidth remains on the Python elastic bridge (always 0).
    assert 'objectName: "elasticHandleAfterLibrary"' in QML_SOURCE
    assert 'objectName: "elasticHandleAfterBrowser"' in QML_SOURCE
    assert 'objectName: "harmonyPane"' in QML_SOURCE
    assert 'objectName: "bottomRackPane"' in QML_SOURCE
    assert 'objectName: "rightWorkspaceColumn"' in QML_SOURCE
    # Horizontal handle after Harmony retired with horizontal Live Kit (#908).
    assert 'objectName: "elasticHandleAfterHarmony"' not in QML_SOURCE
    assert 'layoutModel.applyDrag("library"' in QML_SOURCE
    assert 'layoutModel.applyDrag("browser"' in QML_SOURCE
    assert "layoutModel.endDrag()" in QML_SOURCE
    assert "layoutModel.syncFromInteraction()" in QML_SOURCE
    # Hit target wider than the 6-DIP layout charge (visual strip stays thin).
    assert "anchors.leftMargin: -5" in QML_SOURCE
    assert "anchors.rightMargin: window.interaction.harmonicMatchOpen ? -5 : 0" in QML_SOURCE


def test_qml_keeps_browser_search_and_escape_handlers():
    assert 'objectName: "browserSearch"' in QML_SOURCE
    assert "Qt.Key_Escape" in QML_SOURCE
    assert "Keys.onUpPressed" in QML_SOURCE
    assert "Keys.onDownPressed" in QML_SOURCE


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_elastic_bridge_inactive_on_clean_start(tmp_path: Path):
    active = {"value": False}
    harmony = {"value": False}
    revealed = {"value": False}
    bridge = create_elastic_layout_bridge(
        state_dir=tmp_path,
        harmony_open=lambda: harmony["value"],
        has_active_source=lambda: active["value"],
        library_revealed=lambda: revealed["value"],
    )
    bridge.setContentWidth(1600.0)
    assert bridge.libraryWidth == 0.0
    assert bridge.browserWidth == 0.0
    assert bridge.harmonyWidth == 0.0
    assert bridge.liveKitWidth == 0.0
    before = dict(bridge.current_ratios())
    bridge.applyDrag("library", 40.0)
    assert bridge.libraryWidth == 0.0
    assert dict(bridge.current_ratios()) == before

    revealed["value"] = True
    bridge.syncFromInteraction()
    assert bridge.libraryWidth == 300.0
    assert bridge.browserWidth == 0.0
    assert dict(bridge.current_ratios()) == before


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_elastic_bridge_reveal_does_not_persist_ratios(tmp_path: Path):
    from src.workbench_layout_solver import load_layout_preferences

    active = {"value": False}
    revealed = {"value": False}
    bridge = create_elastic_layout_bridge(
        state_dir=tmp_path,
        harmony_open=lambda: False,
        has_active_source=lambda: active["value"],
        library_revealed=lambda: revealed["value"],
    )
    before = dict(bridge.current_ratios())
    revealed["value"] = True
    bridge.syncFromInteraction()
    bridge.endDrag()
    loaded = load_layout_preferences(state_dir=tmp_path)
    assert dict(loaded.ratios) == before
    assert bridge.libraryWidth == 300.0


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_elastic_bridge_solves_3_and_4_panel_and_persists(tmp_path: Path):
    active = {"value": True}
    harmony = {"value": False}
    bridge = create_elastic_layout_bridge(
        state_dir=tmp_path,
        harmony_open=lambda: harmony["value"],
        has_active_source=lambda: active["value"],
    )
    available = 1600.0
    bridge.setContentWidth(available)
    # #908: horizontal solve is library + browser (+ harmony); Live Kit is vertical.
    widths_2 = (
        bridge.libraryWidth
        + bridge.browserWidth
        + 1 * HANDLE_WIDTH_PX
    )
    assert abs(widths_2 - available) < 1.0
    assert bridge.harmonyWidth == 0.0
    assert bridge.liveKitWidth == 0.0

    before = dict(bridge.current_ratios())
    bridge.applyDrag("library", 30.0)
    after_drag = dict(bridge.current_ratios())
    assert after_drag["library"] > before["library"]
    bridge.endDrag()

    loaded = load_layout_preferences(state_dir=tmp_path)
    assert loaded.persistable is True
    assert abs(loaded.ratios["library"] - after_drag["library"]) < 1e-9

    harmony["value"] = True
    bridge.syncFromInteraction()
    widths_3 = (
        bridge.libraryWidth
        + bridge.browserWidth
        + bridge.harmonyWidth
        + bridge.liveKitWidth
        + 2 * HANDLE_WIDTH_PX
    )
    assert abs(widths_3 - available) < 1.0
    assert bridge.harmonyWidth > 0.0
    assert bridge.liveKitWidth == 0.0


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_qml_runtime_elastic_handles_and_esc_search_intact():
    from PySide6.QtCore import QObject, Qt
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest

    from src.workbench_harmony import HarmonicMatchLibraryController
    from src.workbench_qml import Screen1QmlInteractionAdapter
    from src.workbench_qml_spike import (
        _qml_engine,
        _settle_qml_frame,
        build_qml_view_model_from_fixture,
    )
    from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1

    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(fixture, "screen1-default-3panel")
    interaction_adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        harmony_controller=HarmonicMatchLibraryController(),
    )
    app, engine, window = _qml_engine(
        view_model,
        interaction_adapter=interaction_adapter,
    )
    window.show()
    _settle_qml_frame(app)
    try:
        assert getattr(engine, "_screen1_layout_model", None) is not None
        library = window.findChild(QQuickItem, "libraryPane")
        browser = window.findChild(QQuickItem, "browserPane")
        live_kit = window.findChild(QQuickItem, "liveKitPane")
        bottom = window.findChild(QQuickItem, "bottomRackPane")
        handle_lib = window.findChild(QQuickItem, "elasticHandleAfterLibrary")
        handle_browser = window.findChild(QQuickItem, "elasticHandleAfterBrowser")
        handle_harmony = window.findChild(QQuickItem, "elasticHandleAfterHarmony")
        search = window.findChild(QObject, "browserSearch")
        assert all(
            item is not None
            for item in (library, browser, live_kit, bottom, handle_lib, handle_browser, search)
        )
        assert handle_lib.isVisible()
        # #908: browser/harmony handle only when Harmonic Matches is open.
        assert not handle_browser.isVisible()
        assert handle_harmony is None
        assert library.width() > 0
        assert browser.width() > 0
        # Compat liveKitPane fills bottom band; horizontal width comes from column.
        assert live_kit.width() > 0
        assert bottom.height() > 0

        search.forceActiveFocus()
        selected_before = view_model.selected_browser_index
        QTest.keyClick(window, Qt.Key_Down)
        app.processEvents()
        assert view_model.selected_browser_index == selected_before

        browser_list = window.findChild(QQuickItem, "browserList")
        assert browser_list is not None
        browser_list.forceActiveFocus()
        QTest.keyClick(window, Qt.Key_Escape)
        app.processEvents()
        assert window.property("interaction").property("previewActive") is False

        layout_model = engine._screen1_layout_model
        assert interaction_adapter.toggle_harmonic_match() is True
        engine._screen1_interaction_bridge.refreshState()
        app.processEvents()
        assert window.property("interaction").property("harmonicMatchOpen") is True
        assert layout_model.harmonyWidth > 0
        harmony = window.findChild(QQuickItem, "harmonyPane")
        assert harmony is not None and harmony.opacity() > 0.0 and harmony.width() > 0
        assert handle_browser.isVisible()
        workspace = window.findChild(QQuickItem, "workspaceRow")
        right = window.findChild(QQuickItem, "rightWorkspaceColumn")
        assert workspace is not None and right is not None
        # Horizontal: Library + handle + right column.
        assert abs(
            library.width()
            + handle_lib.width()
            + right.width()
            - workspace.width()
        ) < 2.0
        # Upper row: browser + handle + harmony fills right column width.
        assert abs(
            browser.width()
            + handle_browser.width()
            + harmony.width()
            - right.width()
        ) < 2.0
    finally:
        window.close()
        app.processEvents()
        timer = getattr(engine, "_screen1_waveform_timer", None)
        if timer is not None:
            timer.stop()
        loader = getattr(engine, "_screen1_waveform_loader", None)
        if loader is not None:
            loader.close()
        engine.deleteLater()
        app.processEvents()


def test_canonical_defaults_exported_for_qml_bridge():
    assert abs(sum(CANONICAL_DEFAULT_RATIOS.values()) - 1.0) < 1e-12
