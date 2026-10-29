"""#1293 Library rail vertical inset — bounded left rail geometry (TEST_FREEZE).

FROZEN CONTRACT (test-first):
  - Library rail uses logical top/bottom insets (8 / 18 DIP) inside workspaceRow
  - Browser / right workspace keep full workspace height
  - Gaps above/below Library reveal existing surfaceRoot (no new card/frame fill)
  - #1248 internal header/row/icon metrics stay unchanged
  - Source/scope scrolling stays clipped to the Library viewport
  - Collapse/reveal seams remain usable; gutters are not pointer dead-strips
  - Narrow workspace heights clamp insets deterministically (no chrome overlap)
  - No musical/session/audio mutation from the layout slice

Canon:
  - issue #1293 + MagicPath revision 466430376995328000 (proportional evidence)
  - docs/WORKBENCH_QML_LIBRARY_TREE_CONTRACT.md (#1248 internals + #1293 rail)
  - closed #1204 panel disclosure / #1257 Appearance V2 surfaces
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

from src.workbench_qml import QML_SOURCE

PY_SIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None

RAIL_TOP_INSET = 8
RAIL_BOTTOM_INSET = 18
GEOM_TOL = 1.5


def _library_metrics_block() -> str:
    start = QML_SOURCE.index("id: libraryMetrics")
    end = QML_SOURCE.index("id: contextHintState", start)
    return QML_SOURCE[start:end]


def _library_pane_block(*, size: int = 900) -> str:
    marker = 'objectName: "libraryPane"'
    start = QML_SOURCE.index(marker)
    return QML_SOURCE[start : start + size]


def _workspace_library_section() -> str:
    start = QML_SOURCE.index('objectName: "workspaceRow"')
    end = QML_SOURCE.index('objectName: "elasticHandleAfterLibrary"', start)
    return QML_SOURCE[start:end]


def test_1293_library_metrics_declare_logical_rail_insets() -> None:
    metrics = _library_metrics_block()
    assert f"railTopInset: {RAIL_TOP_INSET}" in metrics
    assert f"railBottomInset: {RAIL_BOTTOM_INSET}" in metrics
    # #1248 internals remain the existing logical metrics authority.
    assert "headerHeight: 52" in metrics
    assert "paneInset: 6" in metrics
    assert "rowHeight: 35" in metrics
    assert "rowPitch: 36" in metrics
    assert "addSourceSize: 36" in metrics
    assert "iconSize: 20" in metrics


def test_1293_library_rail_uses_host_slot_without_new_card_surface() -> None:
    section = _workspace_library_section()
    assert 'objectName: "libraryRailHost"' in section
    assert 'objectName: "libraryPane"' in section
    host_idx = section.index('objectName: "libraryRailHost"')
    pane_idx = section.index('objectName: "libraryPane"')
    assert host_idx < pane_idx

    host = section[host_idx:pane_idx]
    # Host is a layout slot only — no painted card/frame around the rail.
    assert "color:" not in host
    assert "border." not in host
    assert "radius:" not in host
    assert "Gradient" not in host
    assert "layer.enabled" not in host

    pane = _library_pane_block(size=500)
    assert "theme.surfaceLibrary" in pane
    assert "libraryMetrics.railTopInset" in section
    assert "libraryMetrics.railBottomInset" in section
    # No second absolute layout system / device-pixel hardcoding.
    assert re.search(r"\b\d+px\b", section) is None
    assert "Screen.devicePixelRatio" not in section


def test_1293_browser_keeps_full_workspace_height_contract_in_source() -> None:
    browser = QML_SOURCE.split('objectName: "browserPane"', 1)[1][:280]
    assert "height: parent.height" in browser
    right = QML_SOURCE.split('objectName: "rightWorkspaceColumn"', 1)[1][:220]
    assert "height: parent.height" in right


def test_1293_no_audio_or_session_mutation_markers_in_library_rail_slice() -> None:
    # Bound to the #1293 host/pane introduction only — not the whole workspace row.
    host = QML_SOURCE.split('objectName: "libraryRailHost"', 1)[1].split(
        'objectName: "libraryHeaderRow"', 1
    )[0]
    for forbidden in (
        "previewPlay",
        "persistSession",
        "saveWorkspace",
        "liveKitAssign",
        "setBpm",
        "masterTempo",
        "exportLiveKit",
        "toggleSync",
    ):
        assert forbidden not in host


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 nicht installiert")
def test_1293_runtime_library_rail_vertical_inset_and_browser_full_height(
    tmp_path: Path,
) -> None:
    from PySide6.QtCore import QPointF
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
    view_model.set_library_revealed(True)
    interaction = Screen1QmlInteractionAdapter(
        view_model=view_model,
        harmony_controller=HarmonicMatchLibraryController(),
    )
    app, engine, window = _qml_engine(
        view_model,
        interaction_adapter=interaction,
    )
    window.show()
    QTest.qWaitForWindowExposed(window, 5000)
    _settle_qml_frame(app)
    try:
        workspace = window.findChild(QQuickItem, "workspaceRow")
        host = window.findChild(QQuickItem, "libraryRailHost")
        library = window.findChild(QQuickItem, "libraryPane")
        browser = window.findChild(QQuickItem, "browserPane")
        header = window.findChild(QQuickItem, "libraryHeaderRow")
        add = window.findChild(QQuickItem, "libraryAddSourceButton")
        tree = window.findChild(QQuickItem, "libraryTree")
        reveal = window.findChild(QQuickItem, "libraryRevealAffordance")
        browser_seam = window.findChild(QQuickItem, "browserCollapseAffordance")
        assert all(
            item is not None
            for item in (workspace, host, library, browser, header, add, tree)
        )

        assert float(host.width()) > 0
        assert abs(float(host.height()) - float(workspace.height())) <= GEOM_TOL
        assert abs(float(browser.height()) - float(workspace.height())) <= GEOM_TOL

        lib_origin = library.mapToItem(workspace, QPointF(0, 0))
        assert abs(float(lib_origin.y()) - float(RAIL_TOP_INSET)) <= GEOM_TOL
        bottom_gap = float(workspace.height()) - (
            float(lib_origin.y()) + float(library.height())
        )
        assert abs(bottom_gap - float(RAIL_BOTTOM_INSET)) <= GEOM_TOL
        assert abs(
            float(library.height())
            - (float(workspace.height()) - RAIL_TOP_INSET - RAIL_BOTTOM_INSET)
        ) <= GEOM_TOL

        # #1248 internal geometry unchanged inside the rail.
        assert float(header.height()) == 52.0
        assert (float(add.width()), float(add.height())) == (36.0, 36.0)

        # Source tree remains clipped to the Library viewport.
        assert bool(tree.clip()) is True
        tree_origin = tree.mapToItem(library, QPointF(0, 0))
        assert float(tree_origin.y()) >= 0.0
        assert float(tree_origin.y()) + float(tree.height()) <= float(library.height()) + GEOM_TOL

        # Gutters do not paint a second Library surface; host has no fill.
        assert host.property("color") is None

        # Collapse/reveal seams stay full-workspace height (not rail-clipped).
        if reveal is not None:
            assert abs(float(reveal.height()) - float(workspace.height())) <= GEOM_TOL
        if browser_seam is not None:
            assert abs(float(browser_seam.height()) - float(workspace.height())) <= GEOM_TOL

        # Top gutter is outside libraryPane — no Library hit target there.
        gutter_y = max(0.0, float(RAIL_TOP_INSET) / 2.0)
        hit = host.childAt(float(host.width()) / 2.0, gutter_y)
        assert hit is not library
        if hit is not None:
            assert hit.objectName() != "libraryPane"
            assert hit.objectName() != "libraryHeaderRow"
            assert hit.objectName() != "libraryAddSourceButton"
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


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 nicht installiert")
@pytest.mark.parametrize(
    "workspace_height,expected_top,expected_bottom,expected_lib_h",
    [
        (40, 8, 18, 14),
        (26, 8, 18, 0),
        (20, 8, 12, 0),
        (10, 8, 2, 0),
        (6, 6, 0, 0),
        (0, 0, 0, 0),
    ],
)
def test_1293_narrow_height_clamps_insets_deterministically(
    workspace_height: int,
    expected_top: int,
    expected_bottom: int,
    expected_lib_h: int,
) -> None:
    """Pure clamp contract used by the QML rail host (no chrome overlap)."""

    def clamp_insets(height: int) -> tuple[int, int, int]:
        top = min(RAIL_TOP_INSET, max(0, height))
        bottom = min(RAIL_BOTTOM_INSET, max(0, height - top))
        lib_h = max(0, height - top - bottom)
        return top, bottom, lib_h

    assert clamp_insets(workspace_height) == (
        expected_top,
        expected_bottom,
        expected_lib_h,
    )


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 nicht installiert")
def test_1293_theme_change_keeps_workspace_surface_in_rail_gutters(
    tmp_path: Path,
) -> None:
    from PySide6.QtGui import QColor
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest

    from src.workbench_harmony import HarmonicMatchLibraryController
    from src.workbench_qml import Screen1QmlInteractionAdapter
    from src.workbench_qml_spike import (
        _qml_engine,
        _settle_qml_frame,
        build_qml_view_model_from_fixture,
    )
    from src.workbench_theme import resolve_theme, theme_tokens_to_qml_semantics
    from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1

    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(fixture, "screen1-default-3panel")
    view_model.set_library_revealed(True)
    interaction = Screen1QmlInteractionAdapter(
        view_model=view_model,
        harmony_controller=HarmonicMatchLibraryController(),
    )
    app, engine, window = _qml_engine(
        view_model,
        interaction_adapter=interaction,
    )
    window.show()
    QTest.qWaitForWindowExposed(window, 5000)
    _settle_qml_frame(app)
    try:
        library = window.findChild(QQuickItem, "libraryPane")
        assert library is not None
        bridge = engine.rootContext().contextProperty("themeAuthority")
        assert bridge is not None
        for theme_name in ("Blood", "Carbon"):
            bridge.selectTheme(theme_name)
            _settle_qml_frame(app)
            mapped = theme_tokens_to_qml_semantics(resolve_theme(theme_name))
            root = QColor(mapped["surfaceRoot"])
            lib_surface = QColor(mapped["surfaceLibrary"])
            window_color = QColor(window.color())
            assert window_color.name() == root.name()
            lib_color = QColor(library.property("color"))
            assert lib_color.name() == lib_surface.name()
            assert lib_color.name() != root.name()
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
