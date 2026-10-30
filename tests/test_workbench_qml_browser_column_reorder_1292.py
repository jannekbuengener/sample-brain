"""#1292 Browser column reorder + resize arbitration contracts."""

from __future__ import annotations

from src.workbench_qml import QML_SOURCE


DEFAULT_ORDER = '["waveform", "filename", "bpm", "favorite", "key", "length", "type"]'


def _header_block() -> str:
    start = QML_SOURCE.index("id: browserColumnHeaderHost")
    end = QML_SOURCE.index('objectName: "browserListViewport"', start)
    return QML_SOURCE[start:end]


def _ordinary_row_block() -> str:
    start = QML_SOURCE.index("GridLayout { id: rowBody")
    end = QML_SOURCE.index("// #846: permanent vertical column dividers removed", start)
    return QML_SOURCE[start:end]


def test_browser_has_one_runtime_column_order_authority():
    assert QML_SOURCE.count("property var browserColumnOrder:") == 1
    assert f"property var browserColumnOrder: {DEFAULT_ORDER}" in QML_SOURCE
    assert "function visibleBrowserColumnIndex(role)" in QML_SOURCE
    assert "function moveBrowserColumn(role, targetRole, after)" in QML_SOURCE


def test_header_and_rows_project_same_logical_column_order():
    header = _header_block()
    row = _ordinary_row_block()
    assert "GridLayout" in header
    assert "GridLayout" in row
    for role in ("waveform", "filename", "bpm", "favorite", "key", "length", "type"):
        token = f'Layout.column: browserPane.visibleBrowserColumnIndex("{role}")'
        assert token in header, f"header missing shared order projection for {role}"
        assert token in row, f"row missing shared order projection for {role}"


def test_browser_identity_header_is_dateiname_and_not_sample_name():
    header = _header_block()
    assert 'text: "WAVEFORM"' in header
    assert 'text: "DATEINAME"' in header
    assert 'text: "SAMPLE NAME"' not in header


def test_header_reorder_hit_areas_are_distinct_from_resize_boundaries():
    header = _header_block()
    assert "readonly property int browserColumnReorderThreshold: 8" in QML_SOURCE
    for role in ("waveform", "filename", "bpm", "favorite", "key", "length", "type"):
        assert f'objectName: "browserColumnReorder_{role}"' in header
    assert "browserColumnHeaderHost.beginColumnReorder" in header
    assert "browserColumnHeaderHost.updateColumnReorder" in header
    assert "browserColumnHeaderHost.endColumnReorder" in header
    assert "window.interaction.previewRow" not in header
    assert "window.interaction.toggleFavorite" not in header
    assert "window.interaction.contextAddToKit" not in header
    assert "window.interaction.contextHarmonicMatches" not in header
    assert "window.interaction.contextLoop" not in header


def _variant_list(value) -> list[str]:
    if hasattr(value, "toVariant"):
        value = value.toVariant()
    return [str(item) for item in value]


def _scene_point(item, x: float, y: float):
    from PySide6.QtCore import QPoint, QPointF

    point = item.mapToScene(QPointF(float(x), float(y)))
    return QPoint(round(point.x()), round(point.y()))


import importlib.util
import pytest

PY_SIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None


@pytest.fixture
def reorder_runtime():
    if not PY_SIDE6_AVAILABLE:
        pytest.skip("PySide6 ist nicht installiert")

    from PySide6.QtQuick import QQuickItem

    from src.workbench_harmony import HarmonicMatchLibraryController
    from src.workbench_qml import Screen1QmlInteractionAdapter, _qml_engine, _settle_qml_frame
    from src.workbench_qml_spike import build_qml_view_model_from_fixture
    from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1

    preview_calls: list[str] = []
    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(fixture, "screen1-default-3panel")
    view_model.set_library_revealed(True)
    view_model.set_workspace_materialization(
        has_active_source=True,
        calm_canvas_visible=False,
        browser_materialized=True,
        live_kit_materialized=False,
    )
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        harmony_controller=HarmonicMatchLibraryController(),
        on_preview_requested=lambda row: preview_calls.append(str(row.path)),
    )
    adapter.harmonic_match_open = False
    app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    window.setWidth(1600)
    window.setHeight(900)
    window.show()
    _settle_qml_frame(app)
    browser_pane = window.findChild(QQuickItem, "browserPane")
    assert browser_pane is not None

    def settle() -> None:
        app.processEvents()
        _settle_qml_frame(app)

    yield app, engine, window, browser_pane, view_model, preview_calls, settle
    window.close()
    app.processEvents()


def test_runtime_subthreshold_header_drag_does_not_reorder(reorder_runtime):
    from PySide6.QtCore import Qt
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest

    _app, _engine, window, pane, _vm, preview_calls, settle = reorder_runtime
    drag = window.findChild(QQuickItem, "browserColumnReorder_bpm")
    assert drag is not None
    before = _variant_list(pane.property("browserColumnOrder"))
    start = _scene_point(drag, max(1.0, drag.width() / 2.0), max(1.0, drag.height() / 2.0))
    end = start + type(start)(4, 0)
    QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
    QTest.mouseMove(window, end, delay=10)
    QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, end)
    settle()
    assert _variant_list(pane.property("browserColumnOrder")) == before
    assert preview_calls == []


def test_runtime_header_body_drag_reorders_shared_authority(reorder_runtime):
    from PySide6.QtCore import Qt
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest

    _app, _engine, window, pane, vm, preview_calls, settle = reorder_runtime
    drag = window.findChild(QQuickItem, "browserColumnReorder_bpm")
    filename = window.findChild(QQuickItem, "browserColumnHeader_filename")
    assert drag is not None and filename is not None
    selected_before = vm.selected_browser_index
    start = _scene_point(drag, max(1.0, drag.width() / 2.0), max(1.0, drag.height() / 2.0))
    target = _scene_point(filename, 2.0, max(1.0, filename.height() / 2.0))
    QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
    QTest.mouseMove(window, target, delay=20)
    QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, target)
    settle()
    order = _variant_list(pane.property("browserColumnOrder"))
    assert order.index("bpm") < order.index("filename")
    assert vm.selected_browser_index == selected_before
    assert preview_calls == []


def test_runtime_separator_drag_resizes_without_reordering(reorder_runtime):
    from PySide6.QtCore import Qt
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest

    _app, _engine, window, pane, _vm, preview_calls, settle = reorder_runtime
    resize = window.findChild(QQuickItem, "browserColumnResize_bpm")
    header = window.findChild(QQuickItem, "browserColumnHeader_bpm")
    assert resize is not None and header is not None
    before_order = _variant_list(pane.property("browserColumnOrder"))
    before_width = float(header.width())
    start = _scene_point(resize, resize.width() / 2.0, resize.height() / 2.0)
    target = start + type(start)(12, 0)
    QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, start)
    QTest.mouseMove(window, target, delay=20)
    QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, target)
    settle()
    assert _variant_list(pane.property("browserColumnOrder")) == before_order
    assert float(header.width()) > before_width
    assert preview_calls == []


def _invoke_move(pane, role: str, target: str, after: bool) -> None:
    from PySide6.QtCore import Q_ARG, QMetaObject, Qt

    ok = QMetaObject.invokeMethod(
        pane,
        "moveBrowserColumn",
        Qt.DirectConnection,
        Q_ARG("QVariant", role),
        Q_ARG("QVariant", target),
        Q_ARG("QVariant", after),
    )
    assert ok, f"moveBrowserColumn({role!r}, {target!r}, {after!r}) failed"


def _invoke_resize(pane, role: str, delta: float) -> None:
    from PySide6.QtCore import Q_ARG, QMetaObject, Qt

    ok = QMetaObject.invokeMethod(
        pane,
        "resizeColumn",
        Qt.DirectConnection,
        Q_ARG("QVariant", role),
        Q_ARG("QVariant", delta),
    )
    assert ok, f"resizeColumn({role!r}, {delta!r}) failed"


def _scene_x(item) -> float:
    from PySide6.QtCore import QPointF

    return float(item.mapToScene(QPointF(0.0, 0.0)).x())


def _find_visual_item(root, object_name: str):
    if root.objectName() == object_name:
        return root
    for child in root.childItems():
        found = _find_visual_item(child, object_name)
        if found is not None:
            return found
    return None


def test_runtime_reorder_moves_header_and_row_cells_together_with_role_width(reorder_runtime):
    from PySide6.QtQuick import QQuickItem

    _app, _engine, window, pane, _vm, preview_calls, settle = reorder_runtime
    header_bpm = _find_visual_item(pane, "browserColumnHeader_bpm")
    header_filename = _find_visual_item(pane, "browserColumnHeader_filename")
    row_bpm = _find_visual_item(pane, "browserBpmCell")
    row_filename = _find_visual_item(pane, "browserFilenameCell")
    assert all(item is not None for item in (header_bpm, header_filename, row_bpm, row_filename))

    _invoke_resize(pane, "bpm", 18)
    settle()
    resized_width = float(header_bpm.width())
    assert float(row_bpm.width()) == pytest.approx(resized_width, abs=1.0)

    _invoke_move(pane, "bpm", "filename", False)
    settle()
    assert _scene_x(header_bpm) < _scene_x(header_filename)
    assert _scene_x(row_bpm) < _scene_x(row_filename)
    assert _scene_x(row_bpm) == pytest.approx(_scene_x(header_bpm), abs=1.5)
    assert float(header_bpm.width()) == pytest.approx(resized_width, abs=1.0)
    assert float(row_bpm.width()) == pytest.approx(resized_width, abs=1.0)
    assert preview_calls == []


def test_runtime_repeated_reorder_resize_cycles_are_drift_free(reorder_runtime):
    from PySide6.QtQuick import QQuickItem

    _app, _engine, window, pane, _vm, preview_calls, settle = reorder_runtime
    header_bpm = window.findChild(QQuickItem, "browserColumnHeader_bpm")
    assert header_bpm is not None
    initial_width = float(header_bpm.width())

    expected_order = None
    for _ in range(6):
        _invoke_move(pane, "bpm", "key", True)
        settle()
        _invoke_resize(pane, "bpm", 10)
        settle()
        _invoke_resize(pane, "bpm", -10)
        settle()
        _invoke_move(pane, "bpm", "filename", False)
        settle()
        current = _variant_list(pane.property("browserColumnOrder"))
        if expected_order is None:
            expected_order = current
        assert current == expected_order
        assert float(header_bpm.width()) == pytest.approx(initial_width, abs=1.0)

    assert len(expected_order or []) == 7
    assert len(set(expected_order or [])) == 7
    assert preview_calls == []


def test_runtime_narrow_mode_hides_type_without_corrupting_full_order(reorder_runtime):
    from PySide6.QtQuick import QQuickItem

    _app, _engine, window, pane, _vm, preview_calls, settle = reorder_runtime
    type_header = _find_visual_item(pane, "browserColumnHeader_type")
    assert type_header is not None

    # The current 3-panel runtime clamps browserPane above 700 DIP even at the
    # minimum window width. Exercise the canonical narrow projection seam
    # directly instead of pretending the outer layout can reach it here.
    pane.setProperty("browserNarrowColumns", True)
    settle()
    assert bool(pane.property("browserNarrowColumns"))
    assert not bool(type_header.isVisible())

    _invoke_move(pane, "bpm", "filename", False)
    settle()
    narrow_order = _variant_list(pane.property("browserColumnOrder"))
    assert len(narrow_order) == 7
    assert narrow_order.count("type") == 1
    assert pane.property("browserVisibleColumnCount") == 6

    pane.setProperty("browserNarrowColumns", False)
    settle()
    assert not bool(pane.property("browserNarrowColumns"))
    assert bool(type_header.isVisible())
    assert _variant_list(pane.property("browserColumnOrder")) == narrow_order
    assert pane.property("browserVisibleColumnCount") == 7
    assert preview_calls == []
