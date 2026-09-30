"""RED contracts for #692 — shared compact Browser / Harmonic density.

First implementation baseline: Rekordbox-like ``densityRowHeight == 30`` DIP
plus shared density tokens. Historical #603 geometry (66 / 58..72 / harmonic 72)
is superseded; behavior contracts (virtualization, preview, selection,
keyboard, add-to-kit) remain.

``30`` is the first HEAD baseline, not an immutable forever-lock. If Owner
Visual Acceptance later requires e.g. 28 or 32 DIP, that is an explicit product
adjustment: update the density token and this frozen assertion together. That
is not a test softening to force green.
"""

from __future__ import annotations

import re

from src.workbench_qml import QML_SOURCE

BROWSER_ROW_DELEGATE_MARKER = "delegate: Rectangle { id: browserRow"
HARMONIC_LIST_MARKER = 'objectName: "harmonicMatchList"'
BROWSER_ROW_DELEGATE_SPAN = 14000  # Favorite column grows the compact row; include divider + Add-to-Kit
HARMONIC_LIST_SPAN = 9000
_SHARED_DENSITY_ROLES = (
    "densityRowHeight",
    "densityVerticalInset",
    "densityHorizontalInset",
    "densityWaveformHeight",
    "densityRowSpacing",
    "densityDividerHeight",
    "densityActionHitTarget",
)


def _snippet(source: str, marker: str, span: int) -> str:
    index = source.index(marker)
    return source[index : index + span]


def _int_property(source: str, name: str) -> int:
    match = re.search(rf"property int {re.escape(name)}:\s*(\d+)", source)
    assert match is not None, f"window-Rolle {name} fehlt"
    return int(match.group(1))


def _harmonic_list_block(source: str) -> str:
    return _snippet(source, HARMONIC_LIST_MARKER, HARMONIC_LIST_SPAN)


def test_shared_density_roles_defined_once_with_compact_baseline():
    assert _int_property(QML_SOURCE, "densityRowHeight") == 30
    assert _int_property(QML_SOURCE, "densityVerticalInset") == 4
    assert _int_property(QML_SOURCE, "densityHorizontalInset") == 8
    assert _int_property(QML_SOURCE, "densityWaveformHeight") == 22
    assert _int_property(QML_SOURCE, "densityRowSpacing") == 8
    assert _int_property(QML_SOURCE, "densityDividerHeight") == 1
    assert _int_property(QML_SOURCE, "densityActionHitTarget") == 24
    for role in _SHARED_DENSITY_ROLES:
        assert QML_SOURCE.count(f"property int {role}:") == 1


def test_browser_and_harmonic_share_density_row_height_token():
    assert "property int rowHeight: window.densityRowHeight" in QML_SOURCE
    harmonic = _harmonic_list_block(QML_SOURCE)
    assert "height: window.densityRowHeight" in harmonic
    assert "height: 72" not in harmonic
    assert re.search(r"/\s*72\b", harmonic) is None
    assert "window.densityRowHeight" in harmonic
    # No independent second row-height truth.
    assert "property int browserRowHeight:" not in QML_SOURCE
    assert "property int harmonicRowHeight:" not in QML_SOURCE


def test_browser_delegate_uses_shared_density_roles():
    delegate = _snippet(QML_SOURCE, BROWSER_ROW_DELEGATE_MARKER, BROWSER_ROW_DELEGATE_SPAN)
    assert "window.densityHorizontalInset" in delegate
    assert "window.densityRowSpacing" in delegate
    assert "window.densityWaveformHeight" in delegate
    assert "window.densityDividerHeight" in delegate
    assert "window.densityActionHitTarget" in delegate
    # Single horizontal scan line — no stacked name/type ColumnLayout.
    assert "ColumnLayout { Layout.fillWidth: true" not in delegate
    assert "modelData.name" in delegate
    assert "modelData.type" in delegate
    assert "modelData.bpm" in delegate
    assert "modelData.key" in delegate
    assert "modelData.duration" in delegate


def test_harmonic_delegate_uses_shared_density_roles():
    harmonic = _harmonic_list_block(QML_SOURCE)
    assert "window.densityHorizontalInset" in harmonic or "window.densityVerticalInset" in harmonic
    assert "window.densityRowHeight" in harmonic
    assert "window.densityWaveformHeight" in harmonic
    assert "modelData.name" in harmonic
    assert "modelData.key" in harmonic
    assert "modelData.relation" in harmonic
    assert "modelData.fit" in harmonic
    assert "addHarmonyToKit(index)" in harmonic
    # Compact: relation/fit must not force a second tall ColumnLayout stack.
    assert "ColumnLayout { Layout.fillWidth: true" not in harmonic


def test_virtualization_reuse_items_preserved_on_both_lists():
    assert QML_SOURCE.count("reuseItems: true") == 2
    assert 'objectName: "browserList"' in QML_SOURCE
    assert HARMONIC_LIST_MARKER in QML_SOURCE


def test_interaction_contracts_preserved_under_compact_density():
    assert "previewRow(index)" in QML_SOURCE
    assert "previewHarmonyRow(index)" in QML_SOURCE
    assert "selectRow(index)" in QML_SOURCE
    assert "selectHarmonyRow(index)" in QML_SOURCE
    assert "navigateBrowser(1)" in QML_SOURCE
    assert "navigateBrowser(-1)" in QML_SOURCE
    assert "navigateHarmony(1)" in QML_SOURCE
    assert "navigateHarmony(-1)" in QML_SOURCE
    assert "stopPreview()" in QML_SOURCE
    assert "addToKit(index)" in QML_SOURCE
    assert "addHarmonyToKit(index)" in QML_SOURCE
    assert 'text: "Play"' not in QML_SOURCE
    assert 'text: "▶"' not in QML_SOURCE
    assert 'objectName: "browserSearch"' in QML_SOURCE
    # Keyboard nav is owned by the browser ListView, not the search field.
    # Span covers viewport waveform hooks + Keys handlers.
    browser_keys = _snippet(QML_SOURCE, 'objectName: "browserList"', 1800)
    assert "Keys.onPressed" in browser_keys
    assert "navigateBrowser" in browser_keys


def test_owner_visual_repair_preserves_required_browser_columns_at_narrow_width():
    assert "property bool browserNarrowColumns: width < 700" in QML_SOURCE
    assert "property int effectiveBrowserWaveformWidth: browserNarrowColumns ? window.browserWaveformMin : window.browserWaveformWidth" in QML_SOURCE
    assert "property int effectiveBrowserMetaColumnWidth: browserNarrowColumns ? 40 : window.browserMetaColumnWidth" in QML_SOURCE
    assert "property int effectiveBrowserLengthColumnWidth: browserNarrowColumns ? 52 : window.browserLengthColumnWidth" in QML_SOURCE
    assert "property int effectiveBrowserAddColumnWidth: browserNarrowColumns ? 56 : window.browserAddColumnWidth" in QML_SOURCE

    delegate = _snippet(QML_SOURCE, BROWSER_ROW_DELEGATE_MARKER, BROWSER_ROW_DELEGATE_SPAN)
    assert "visible: !browserPane.browserNarrowColumns" in delegate
    assert "Layout.minimumWidth: browserPane.browserNarrowColumns ? 96 : 120" in delegate
    assert 'text: browserPane.browserNarrowColumns ? "+ Add" : "+ Add to Kit"' in delegate
    assert "browserPane.effectiveBrowserMetaColumnWidth" in delegate
    assert "browserPane.effectiveBrowserLengthColumnWidth" in delegate
    assert "browserPane.effectiveBrowserAddColumnWidth" in delegate


def test_harmonic_compact_columns_preserve_sample_identity():
    assert _int_property(QML_SOURCE, "harmonicWaveformWidth") == 72
    assert _int_property(QML_SOURCE, "harmonicRelationColumnWidth") == 72
    assert _int_property(QML_SOURCE, "harmonicAddColumnWidth") == 44
    harmonic = _harmonic_list_block(QML_SOURCE)
    assert "Layout.minimumWidth: 64" in harmonic
    assert "window.harmonicWaveformWidth" in harmonic
    assert "window.harmonicRelationColumnWidth" in harmonic
    assert "window.harmonicAddColumnWidth" in harmonic
