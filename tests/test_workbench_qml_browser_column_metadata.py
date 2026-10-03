"""#850 Browser column metadata assignment — projection + header/delegate geometry.

Protects: Length shows only projected duration (or honest Missing-State);
Type shows only sample type; header and delegate share Type geometry so Type
never appears under the LENGTH header. No BPM/Key/analysis changes.
"""

from __future__ import annotations

import importlib.util
import re

import pytest

from src.workbench_controller import WorkbenchRow
from src.workbench_qml import QML_SOURCE, _qml_row

PY_SIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None

MISSING = "—"


def _row(
    *,
    name: str = "sample.wav",
    pred_type: str | None = "Loop",
    bpm: float | None = 128.0,
    key: str | None = "Am",
    details: dict | None = None,
) -> WorkbenchRow:
    return WorkbenchRow(
        display_name=name,
        relative_path=name,
        path=f"/synthetic/{name}",
        bpm=bpm,
        key=key,
        key_conf=0.9 if key else None,
        loudness=None,
        brightness=None,
        sample_class="loop" if pred_type == "Loop" else "one_shot",
        pred_type=pred_type,
        status="ok",
        details={} if details is None else details,
    )


def test_projection_maps_duration_and_type_separately_full_metadata():
    projected = _qml_row(_row(pred_type="Loop", details={"duration_sec": 2.5}))
    assert projected.duration == "2.50s"
    assert projected.sample_type == "Loop"
    assert projected.bpm == "128"
    assert projected.key == "Am"
    assert "Loop" not in projected.duration
    assert projected.duration != projected.sample_type


def test_projection_missing_duration_stays_missing_state_not_type():
    projected = _qml_row(_row(pred_type="OneShot", details={}))
    assert projected.duration == MISSING
    assert projected.sample_type == "OneShot"
    assert projected.duration != projected.sample_type


def test_projection_missing_type_stays_missing_state_not_duration():
    projected = _qml_row(_row(pred_type=None, details={"duration_sec": 1.25}))
    assert projected.duration == "1.25s"
    assert projected.sample_type == MISSING
    assert projected.sample_type != projected.duration


def test_qml_context_dict_keeps_duration_and_type_on_distinct_keys():
    from src.workbench_qml import Screen1QmlViewModel

    projected = _qml_row(_row(pred_type="Bass", details={"duration_sec": 3.0}))
    view_model = Screen1QmlViewModel.baseline("screen1-default-3panel")
    view_model._browser_rows_all = (projected,)
    view_model.browser_rows = (projected,)
    row = view_model.qml_context()["browserRows"][0]
    assert row["duration"] == "3.00s"
    assert row["type"] == "Bass"
    assert row["duration"] != row["type"]
    assert "Loop" not in str(row["duration"])


def _full_browser_column_header(source: str) -> str:
    marker = source.index('text: "SAMPLE NAME"')
    start = source.rfind("RowLayout { Layout.fillWidth: true", 0, marker)
    end = source.index("ListView { id: browser", marker)
    return source[start:end]


def _browser_delegate(source: str) -> str:
    start = source.index("delegate: Rectangle { id: browserRow")
    end = source.index('objectName: "elasticHandleAfterBrowser"')
    return source[start:end]


def test_header_and_delegate_share_type_column_after_length():
    """#850: TYPE header must exist with the same visibility/width as Type cell."""
    header = _full_browser_column_header(QML_SOURCE)
    delegate = _browser_delegate(QML_SOURCE)

    assert 'text: "LENGTH"' in header
    assert 'text: "TYPE"' in header
    assert header.index('text: "LENGTH"') < header.index('text: "TYPE"')

    assert "text: modelData.duration" in delegate
    assert "text: modelData.type" in delegate
    assert delegate.index("text: modelData.duration") < delegate.index(
        "text: modelData.type"
    )

    # Shared width role — not a one-sided magic number in the delegate only.
    assert "browserTypeColumnWidth" in header
    assert "browserTypeColumnWidth" in delegate
    assert re.search(r"property int browserTypeColumnWidth:\s*\d+", QML_SOURCE)

    # Same narrow-mode visibility gate so Type cannot desync header vs row.
    assert header.count("visible: !browserPane.browserNarrowColumns") >= 1
    type_cell = delegate[delegate.index('objectName: "browserTypeCell"') :][
        :320
    ]
    assert "visible: !browserPane.browserNarrowColumns" in type_cell
    assert "modelData.type" in type_cell


def test_length_cell_binds_duration_never_type():
    delegate = _browser_delegate(QML_SOURCE)
    length_idx = delegate.index('objectName: "browserLengthCell"')
    length_snippet = delegate[length_idx : length_idx + 320]
    assert "modelData.duration" in length_snippet
    assert "modelData.type" not in length_snippet

    type_idx = delegate.index('objectName: "browserTypeCell"')
    type_snippet = delegate[type_idx : type_idx + 320]
    assert "modelData.type" in type_snippet
    assert "modelData.duration" not in type_snippet


def test_header_length_and_type_object_names_present_for_geometry_checks():
    header = _full_browser_column_header(QML_SOURCE)
    assert 'objectName: "browserColumnHeader_length"' in header
    assert 'objectName: "browserColumnHeader_type"' in header


def _scene_x(item) -> float:
    return float(item.mapToScene(item.boundingRect().topLeft()).x())


def _visual_named(root, name: str):
    """Find a QQuickItem by objectName in the visual child tree (ListView-safe)."""
    if root is None:
        return None
    if root.objectName() == name:
        return root
    for child in root.childItems():
        found = _visual_named(child, name)
        if found is not None:
            return found
    return None


def _first_browser_row(browser_list):
    content = browser_list.property("contentItem")
    if content is None:
        return None
    for child in content.childItems():
        if _visual_named(child, "browserLengthCell") is not None:
            return child
    return None


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_runtime_length_and_type_columns_align_with_headers_wide_and_harmony():
    """Geometric proof: LENGTH/TYPE headers align with their value cells."""
    from PySide6.QtQuick import QQuickItem

    from src.workbench_qml import (
        Screen1QmlInteractionAdapter,
        Screen1QmlViewModel,
        _qml_engine,
    )

    full = _qml_row(_row(name="loop_full.wav", pred_type="Loop", details={"duration_sec": 2.5}))
    missing_duration = _qml_row(
        _row(name="loop_nodur.wav", pred_type="OneShot", details={})
    )
    missing_type = _qml_row(
        _row(name="typed.wav", pred_type=None, details={"duration_sec": 1.0})
    )
    rows = (full, missing_duration, missing_type)
    view_model = Screen1QmlViewModel.baseline("screen1-default-3panel")
    view_model._browser_rows_all = rows
    view_model.browser_rows = rows
    view_model.selected_browser_index = 0
    view_model.set_workspace_materialization(
        has_active_source=True,
        calm_canvas_visible=False,
        browser_materialized=True,
        live_kit_materialized=True,
    )
    adapter = Screen1QmlInteractionAdapter(view_model=view_model)
    app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    window.resize(1600, 900)
    window.show()
    for _ in range(40):
        app.processEvents()
    try:
        bridge = engine._screen1_interaction_bridge
        browser_pane = window.findChild(QQuickItem, "browserPane")
        browser_list = window.findChild(QQuickItem, "browserList")
        assert bridge is not None
        assert browser_pane is not None and browser_pane.isVisible()
        assert browser_list is not None

        def _assert_wide_alignment() -> None:
            for _ in range(20):
                app.processEvents()
            length_header = window.findChild(QQuickItem, "browserColumnHeader_length")
            type_header = window.findChild(QQuickItem, "browserColumnHeader_type")
            row = _first_browser_row(browser_list)
            assert row is not None
            length_cell = _visual_named(row, "browserLengthCell")
            type_cell = _visual_named(row, "browserTypeCell")
            assert length_header is not None and length_cell is not None
            assert type_header is not None and type_cell is not None
            assert type_header.isVisible()
            assert type_cell.isVisible()
            # Shared trailing structure: Length→Type gap matches header↔row.
            header_gap = float(type_header.x()) - float(length_header.x())
            cell_gap = float(type_cell.x()) - float(length_cell.x())
            assert abs(header_gap - cell_gap) <= 2.0
            # Same-parent local geometry (scene X can skew via ListView chrome).
            assert float(length_cell.x()) + float(length_cell.width()) <= float(
                type_cell.x()
            ) + 2.0
            # Absolute scene X may differ by ListView scrollbar reserve; keep tight.
            assert abs(_scene_x(length_header) - _scene_x(length_cell)) <= 20.0
            assert abs(_scene_x(type_header) - _scene_x(type_cell)) <= 20.0
            assert str(length_cell.property("text")) == "2.50s"
            assert str(type_cell.property("text")) == "Loop"
            assert str(length_cell.property("text")) != str(type_cell.property("text"))

        assert adapter.harmonic_match_open is False
        assert float(browser_pane.width()) >= 700
        _assert_wide_alignment()

        # Harmonic open must not swap Length/Type assignment.
        bridge.toggleHarmonicMatch()
        for _ in range(40):
            app.processEvents()
        assert adapter.harmonic_match_open is True
        if float(browser_pane.width()) >= 700:
            _assert_wide_alignment()
        else:
            type_header = window.findChild(QQuickItem, "browserColumnHeader_type")
            row = _first_browser_row(browser_list)
            type_cell = _visual_named(row, "browserTypeCell") if row else None
            assert type_header is None or not type_header.isVisible()
            assert type_cell is None or not type_cell.isVisible()
            length_header = window.findChild(QQuickItem, "browserColumnHeader_length")
            length_cell = _visual_named(row, "browserLengthCell") if row else None
            assert length_header is not None and length_cell is not None
            assert abs(_scene_x(length_header) - _scene_x(length_cell)) <= 20.0
            assert str(length_cell.property("text")) == "2.50s"

        # Model still keeps honest Missing-State / type separation under harmony.
        payload = view_model.qml_context()["browserRows"]
        assert payload[1]["duration"] == MISSING
        assert payload[1]["type"] == "OneShot"
        assert payload[2]["duration"] == "1.00s"
        assert payload[2]["type"] == MISSING
    finally:
        transport = getattr(engine, "_screen1_transport", None)
        if transport is not None:
            transport.close()
        window.close()
        engine.deleteLater()
        app.processEvents()
