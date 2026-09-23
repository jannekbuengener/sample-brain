"""RED contracts for #603 — QML Browser chrome + density convergence.

Freezes the next #543 browser slice on top of the #591 row baseline:

- integrated search chrome (no default-widget look, focus accent, themed box);
- honest sample count derived from ``browserRows.length`` runtime data;
- shared column spec used identically by the column header and the row delegate
  (exact alignment, no duplicated magic margins);
- bounded typography roles with stable hierarchy (title/body/meta/caption);
- row density / waveform / divider invariants;
- preserved intent + keyboard + virtualization contracts from #591/#583/#564.

These are reproducible QML layout invariants over ``QML_SOURCE``, not
pixel tests. They run without PySide6.
"""

from __future__ import annotations

import re

from src.workbench_qml import QML_SOURCE

BROWSER_ROW_DELEGATE_MARKER = "delegate: Rectangle { id: browserRow"
BROWSER_ROW_DELEGATE_SPAN = 6200  # bis inkl. Row-Trennlinie (Bottom-Divider), endet vor dem Harmonic-Panel
SEARCH_MARKER = 'objectName: "browserSearch"'
COLUMN_HEADER_MARKER = 'text: "SAMPLE NAME"'

# Shared column spec introduced by this slice. Used by header AND delegate.
_SHARED_COLUMN_ROLES = (
    "browserRowHeight",
    "browserRowInset",
    "browserRowSpacing",
    "browserWaveformWidth",
    "browserWaveformMin",
    "browserMetaColumnWidth",
    "browserLengthColumnWidth",
    "browserAddColumnWidth",
)


def _snippet(source: str, marker: str, span: int) -> str:
    index = source.index(marker)
    return source[index : index + span]


def _int_property(source: str, name: str) -> int:
    match = re.search(rf"property int {re.escape(name)}:\s*(\d+)", source)
    assert match is not None, f"window-Rolle {name} fehlt"
    return int(match.group(1))


def _column_header_layout(source: str) -> str:
    marker = source.index(COLUMN_HEADER_MARKER)
    start = source.rfind("RowLayout { Layout.fillWidth: true", 0, marker)
    assert start != -1, "Spalten-Header-RowLayout fehlt"
    return source[start:marker]


def test_browser_search_field_is_visually_integrated():
    search = _snippet(QML_SOURCE, SEARCH_MARKER, 900)
    assert QML_SOURCE.count(SEARCH_MARKER) == 1
    assert 'placeholderText: "Search samples"' in search
    assert "background: Rectangle" in search
    assert "placeholderTextColor: window.muted" in search
    assert "activeFocus ? window.accent" in search


def test_browser_header_composes_context_title_scope_count_and_error():
    title_snippet = _snippet(QML_SOURCE, "text: window.screenData.browserContext", 300)
    assert "font.pixelSize: window.textTitle" in title_snippet
    assert "font.bold: true" in title_snippet
    assert 'window.screenData.browserRows.length + " samples"' in QML_SOURCE
    assert "errorMessage.length > 0" in QML_SOURCE


def test_browser_column_spec_is_shared_between_header_and_rows():
    for role in _SHARED_COLUMN_ROLES:
        assert QML_SOURCE.count(f"window.{role}") >= 2, (
            f"Column-Spec {role} wird nicht von Header UND Delegate geteilt"
        )
    assert QML_SOURCE.count("anchors.leftMargin: window.browserRowInset") == 2
    assert QML_SOURCE.count("anchors.rightMargin: window.browserRowInset") == 2

    header = _column_header_layout(QML_SOURCE)
    assert "anchors.leftMargin: window.browserRowInset" in header
    assert "anchors.rightMargin: window.browserRowInset" in header

    delegate = _snippet(QML_SOURCE, BROWSER_ROW_DELEGATE_MARKER, BROWSER_ROW_DELEGATE_SPAN)
    for magic in ("anchors.leftMargin: 12", "anchors.rightMargin: 12", "Layout.preferredWidth: 180"):
        assert magic not in delegate, f"magische Breite/Margin in Browser-Row verblieben: {magic}"


def test_browser_typography_roles_are_bounded_and_assigned():
    assert 16 <= _int_property(QML_SOURCE, "textTitle") <= 20
    assert 13 <= _int_property(QML_SOURCE, "textBody") <= 16
    assert 12 <= _int_property(QML_SOURCE, "textMeta") <= 14
    assert 10 <= _int_property(QML_SOURCE, "textCaption") <= 12

    delegate = _snippet(QML_SOURCE, BROWSER_ROW_DELEGATE_MARKER, BROWSER_ROW_DELEGATE_SPAN)
    assert "font.pixelSize: window.textBody" in delegate  # Sample-Name
    assert "font.pixelSize: window.textCaption" in delegate  # Sample-Typ
    assert QML_SOURCE.count("font.pixelSize: window.textMeta") >= 3  # BPM/Key/Length


def test_browser_density_waveform_and_divider_invariants():
    row_height = _int_property(QML_SOURCE, "browserRowHeight")
    assert 58 <= row_height <= 72
    assert _int_property(QML_SOURCE, "browserWaveformMin") >= 140

    delegate = _snippet(QML_SOURCE, BROWSER_ROW_DELEGATE_MARKER, BROWSER_ROW_DELEGATE_SPAN)
    assert "height: browser.rowHeight" in delegate
    assert "Layout.preferredWidth: window.browserWaveformWidth" in delegate
    assert delegate.count("anchors.bottom: parent.bottom; height: 1") == 1
    assert "color: window.divider" in delegate


def test_browser_shared_column_spec_uses_single_definition_each():
    for role in _SHARED_COLUMN_ROLES:
        assert QML_SOURCE.count(f"property int {role}:") == 1
    assert QML_SOURCE.count("property color divider:") == 1


def test_browser_intent_keyboard_and_virtualization_contracts_preserved():
    assert QML_SOURCE.count("previewRow(index)") == 1
    assert QML_SOURCE.count("addToKit(index)") == 1
    # stopPreview() gehört zwei Flächen: Browser-Escape UND Harmonic-Panel (vorbestehend).
    assert 'else if (event.key === Qt.Key_Escape) { window.interaction.stopPreview(); event.accepted = true }' in QML_SOURCE
    assert "Keys.onEscapePressed: window.interaction.stopPreview()" in QML_SOURCE
    assert QML_SOURCE.count('objectName: "harmonicMatchButton"') == 1
    assert QML_SOURCE.count("toggleHarmonicMatch()") == 1
    assert 'text: "Play"' not in QML_SOURCE
    assert 'text: "▶"' not in QML_SOURCE
    assert "reuseItems: true" in QML_SOURCE
    assert "Component.onCompleted: window.browserDelegateCreations += 1" in QML_SOURCE
    assert "navigateBrowser(1)" in QML_SOURCE
    assert "navigateBrowser(-1)" in QML_SOURCE
    assert QML_SOURCE.count('objectName: "browserList"') == 1