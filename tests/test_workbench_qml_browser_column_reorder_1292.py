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
    assert 'text: "DATEINAME"' in header
    assert 'text: "SAMPLE NAME"' not in header
