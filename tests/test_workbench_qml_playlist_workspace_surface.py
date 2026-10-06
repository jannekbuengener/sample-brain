"""Main All-Samples playlist reuses Clean-Start canvas background.

Owner GO slice (follow-up under delivered #691 authority):
reuse existing calm-canvas token ``theme.surfaceRoot`` for the main playlist
list-viewport only. Not a redesign, not a theme refactor.

Status: TEST_FREEZE
"""

from __future__ import annotations

import re

import pytest

from src.workbench_qml import QML_SOURCE


def _snippet_after(marker: str, span: int = 2200) -> str:
    idx = QML_SOURCE.index(marker)
    return QML_SOURCE[idx : idx + span]


def test_calm_canvas_and_playlist_viewport_share_surface_root_token() -> None:
    """Color source must be the existing Clean-Start canvas token — not a new HEX."""
    calm = _snippet_after('objectName: "calmCanvas"', 900)
    assert "color: theme.surfaceRoot" in calm

    assert 'objectName: "browserListViewport"' in QML_SOURCE
    viewport = _snippet_after('objectName: "browserListViewport"', 400)
    assert "color: theme.surfaceRoot" in viewport
    assert re.search(r'color:\s*"#', viewport) is None


def test_playlist_viewport_does_not_use_panel_family_fill() -> None:
    """List viewport must not keep the panel/browser fill that other panes use."""
    assert 'objectName: "browserListViewport"' in QML_SOURCE
    viewport = _snippet_after('objectName: "browserListViewport"', 400)
    assert "theme.surfacePanel" not in viewport
    assert "theme.surfaceBrowser" not in viewport
    assert "theme.surfaceHeader" not in viewport


def test_library_harmony_live_kit_remain_panel_surfaces() -> None:
    """Unchanged surfaces: Library, Harmonic Matches, Live Kit stay panel fills."""
    library = _snippet_after('objectName: "libraryPane"', 240)
    assert "color: theme.surfacePanel" in library

    harmony = _snippet_after('objectName: "harmonyPane"', 500)
    assert "color: theme.surfacePanel" in harmony

    # #954: panel surface remains on the Browser-scoped Drawer container
    # (compat liveKitPane is an Item); its geometry has more bindings now.
    bottom = _snippet_after('objectName: "bottomRackPane"', 1800)
    assert "color: theme.surfacePanel" in bottom


def test_browser_pane_chrome_keeps_panel_family_when_viewport_is_workspace() -> None:
    """Outer browser chrome may stay panel-family; only the list viewport moves."""
    browser_head = _snippet_after('objectName: "browserPane"', 220)
    # Pane chrome remains surfaceBrowser so Library/panel family is not remapped.
    assert "color: theme.surfaceBrowser" in browser_head
    assert 'objectName: "browserListViewport"' in QML_SOURCE
    assert 'objectName: "browserList"' in QML_SOURCE


def test_selected_row_still_uses_selection_surface() -> None:
    """Existing red selected-row presentation must remain exact."""
    delegate_idx = QML_SOURCE.index("delegate: Rectangle { id: browserRow;")
    delegate = QML_SOURCE[delegate_idx : delegate_idx + 500]
    assert "theme.selectionSurface" in delegate
    assert "theme.selectionBorder" in delegate
    assert (
        "index === window.screenData.selectedBrowserIndex ? theme.selectionSurface"
        in delegate
    )


def test_normal_rows_do_not_opaque_cover_playlist_workspace_surface() -> None:
    """Normal rows stay visually uniform: no opaque panel zebra over surfaceRoot."""
    delegate_idx = QML_SOURCE.index("delegate: Rectangle { id: browserRow;")
    delegate = QML_SOURCE[delegate_idx : delegate_idx + 500]
    # selection > hover > transparent (reveals reused Clean-Start fill).
    assert (
        'color: index === window.screenData.selectedBrowserIndex ? theme.selectionSurface '
        ': (rowSelection.containsMouse ? theme.surfaceElevated : "transparent")'
    ) in delegate
    assert 'index % 2 === 1 ? theme.surfacePanel' not in delegate


@pytest.mark.skipif(
    not __import__("src.workbench_qml", fromlist=["qml_runtime_available"]).qml_runtime_available(),
    reason="PySide6 unavailable",
)
def test_runtime_playlist_viewport_matches_calm_canvas_surface_root(tmp_path) -> None:
    """Runtime: browserListViewport color equals calmCanvas / Theme surfaceRoot."""
    from PySide6.QtGui import QColor
    from PySide6.QtQuick import QQuickItem

    from src import workbench_theme as theme_core
    from src.workbench_harmony import HarmonicMatchLibraryController
    from src.workbench_qml import Screen1QmlInteractionAdapter
    from src.workbench_qml_spike import (
        _qml_engine,
        _settle_qml_frame,
        build_qml_view_model_from_fixture,
    )
    from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1

    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(
        fixture,
        "screen1-harmonic-4panel",
    )
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        harmony_controller=HarmonicMatchLibraryController(
            finder=lambda *_a, **_k: ([], None)
        ),
    )
    app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    window.show()
    _settle_qml_frame(app)
    try:
        blood = theme_core.resolve_theme("Blood")
        expected = QColor(blood.as_dict()["surfaceWorkspace"])
        viewport = window.findChild(QQuickItem, "browserListViewport")
        assert viewport is not None
        color = viewport.property("color")
        assert color is not None
        assert QColor(color).name() == expected.name()

        library = window.findChild(QQuickItem, "libraryPane")
        harmony = window.findChild(QQuickItem, "harmonyPane")
        live_kit = window.findChild(QQuickItem, "liveKitPane")
        bottom = window.findChild(QQuickItem, "bottomRackPane")
        browser_pane = window.findChild(QQuickItem, "browserPane")
        assert library is not None and harmony is not None and live_kit is not None
        assert bottom is not None and browser_pane is not None
        panel = QColor(blood.surface)
        assert QColor(library.property("color")).name() == panel.name()
        assert QColor(harmony.property("color")).name() == panel.name()
        # #908: panel fill is on bottomRackPane; liveKitPane is a compat Item.
        assert QColor(bottom.property("color")).name() == panel.name()
        # Outer browser chrome stays panel-family; viewport alone is workspace.
        assert QColor(browser_pane.property("color")).name() == panel.name()
        assert QColor(browser_pane.property("color")).name() != expected.name()
    finally:
        window.close()
        app.processEvents()
        timer = getattr(engine, "_screen1_waveform_timer", None)
        if timer is not None:
            timer.stop()
        loader = getattr(engine, "_screen1_waveform_loader", None)
        if loader is not None:
            loader.close()
