"""Browser chrome contracts — #603 behavior + #692 compact density.

#603 still owns search chrome, column alignment, typography hierarchy,
intent/keyboard/virtualization behavior. The historical density gate
``58 <= browserRowHeight <= 72`` is superseded by #692: shared
``densityRowHeight == 30`` DIP is the first compact baseline (not an immutable
forever-lock — Owner Visual Acceptance may later retarget e.g. 28/32 DIP via
explicit product adjustment of token + frozen assertion together).

These are reproducible QML layout invariants over ``QML_SOURCE``, not
pixel tests. They run without PySide6.
"""

from __future__ import annotations

import re

from src.workbench_qml import QML_SOURCE

# Hex color literals in QML (not issue markers like "#846").
_HEX_COLOR_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b")

BROWSER_ROW_DELEGATE_MARKER = "delegate: Rectangle { id: browserRow"
# Span the full row delegate (through the bottom horizontal divider) but stop
# before the panel resize handle, so panel-resize (layoutModel) code never leaks
# into delegate assertions. Derive the span from elasticHandleAfterBrowser.
BROWSER_ROW_DELEGATE_SPAN = (
    QML_SOURCE.index('objectName: "elasticHandleAfterBrowser"')
    - QML_SOURCE.index(BROWSER_ROW_DELEGATE_MARKER)
)
SEARCH_MARKER = 'objectName: "browserSearch"'
COLUMN_HEADER_MARKER = 'text: "SAMPLE NAME"'

# Shared density + browser column spec. Used by header AND / OR both list delegates.
_SHARED_DENSITY_ROLES = (
    "densityRowHeight",
    "densityVerticalInset",
    "densityHorizontalInset",
    "densityWaveformHeight",
    "densityRowSpacing",
    "densityDividerHeight",
    "densityActionHitTarget",
)

# Browser-specific column widths stay browser-local but shared between header + row.
_SHARED_BROWSER_COLUMN_ROLES = (
    "browserWaveformWidth",
    "browserWaveformMin",
    "browserMetaColumnWidth",
    "browserFavoriteColumnWidth",
    "browserLengthColumnWidth",
    "browserAddColumnWidth",
)

# #767 default Browser scan order markers for row delegate.
_BROWSER_ROW_ORDER_MARKERS = (
    'objectName: "browserWaveformSurface"',
    "text: modelData.name",
    "text: modelData.bpm",
    'objectName: "browserFavoriteButton"',
    "text: modelData.key",
    "text: modelData.duration",
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


def _full_browser_column_header(source: str) -> str:
    """Header RowLayout through the trailing Add-column spacer (before ListView)."""
    marker = source.index(COLUMN_HEADER_MARKER)
    start = source.rfind("RowLayout { Layout.fillWidth: true", 0, marker)
    assert start != -1, "Spalten-Header-RowLayout fehlt"
    end = source.index("ListView { id: browser", marker)
    return source[start:end]


def test_browser_search_field_is_visually_integrated():
    search = _snippet(QML_SOURCE, SEARCH_MARKER, 900)
    assert QML_SOURCE.count(SEARCH_MARKER) == 1
    assert 'placeholderText: "Search samples"' in search
    assert "background: Rectangle" in search
    assert "placeholderTextColor: theme.textSecondary" in search
    assert "activeFocus ? theme.focusRing" in search
    assert "activeFocus ? theme.actionActive" not in search


def test_browser_header_composes_context_title_scope_count_and_error():
    title_snippet = _snippet(QML_SOURCE, "text: window.screenData.browserContext", 300)
    assert "font.pixelSize: window.textTitle" in title_snippet
    assert "font.bold: true" in title_snippet
    assert 'window.screenData.browserRows.length + " samples"' in QML_SOURCE
    assert "errorMessage.length > 0" in QML_SOURCE


def test_browser_column_spec_is_shared_between_header_and_rows():
    for role in _SHARED_BROWSER_COLUMN_ROLES:
        assert QML_SOURCE.count(f"property int {role}:") == 1

    for role in (
        "effectiveBrowserWaveformWidth",
        "effectiveBrowserMetaColumnWidth",
        "effectiveBrowserFavoriteColumnWidth",
        "effectiveBrowserLengthColumnWidth",
        "effectiveBrowserAddColumnWidth",
    ):
        assert QML_SOURCE.count(f"browserPane.{role}") >= 2, (
            f"Responsive Column-Spec {role} wird nicht von Header UND Delegate geteilt"
        )
    assert QML_SOURCE.count("anchors.leftMargin: window.densityHorizontalInset") >= 2
    assert QML_SOURCE.count("anchors.rightMargin: window.densityHorizontalInset") >= 2

    header = _column_header_layout(QML_SOURCE)
    assert "anchors.leftMargin: window.densityHorizontalInset" in header
    assert "anchors.rightMargin: window.densityHorizontalInset" in header
    assert "spacing: window.densityRowSpacing" in header

    delegate = _snippet(QML_SOURCE, BROWSER_ROW_DELEGATE_MARKER, BROWSER_ROW_DELEGATE_SPAN)
    for magic in ("anchors.leftMargin: 12", "anchors.rightMargin: 12", "Layout.preferredWidth: 180"):
        assert magic not in delegate, f"magische Breite/Margin in Browser-Row verblieben: {magic}"


def test_browser_typography_roles_are_bounded_and_assigned():
    """Compact #692 typography — fit a single 30-DIP horizontal scan line."""
    assert 16 <= _int_property(QML_SOURCE, "textTitle") <= 20
    assert 11 <= _int_property(QML_SOURCE, "textBody") <= 13
    assert 10 <= _int_property(QML_SOURCE, "textMeta") <= 12
    assert 9 <= _int_property(QML_SOURCE, "textCaption") <= 11

    delegate = _snippet(QML_SOURCE, BROWSER_ROW_DELEGATE_MARKER, BROWSER_ROW_DELEGATE_SPAN)
    assert "font.pixelSize: window.textBody" in delegate  # Sample-Name
    assert "font.pixelSize: window.textCaption" in delegate  # Sample-Typ (inline)
    assert QML_SOURCE.count("font.pixelSize: window.textMeta") >= 3  # BPM/Key/Length


def test_browser_meta_fields_use_secondary_text_weight():
    """ROW_CHROME_TYPOGRAPHY_WEIGHT — BPM/Key/Length secondary to Sample Name.

    Color weight only; density tokens and meta pixel sizes stay frozen.
    Harmonic Match Key keeps intentional ``actionActive`` accent.
    """
    delegate = _snippet(QML_SOURCE, BROWSER_ROW_DELEGATE_MARKER, BROWSER_ROW_DELEGATE_SPAN)
    assert 'text: modelData.name; color: theme.textPrimary' in delegate
    assert 'text: modelData.bpm; color: theme.textSecondary' in delegate
    assert 'text: modelData.key; color: theme.textSecondary' in delegate
    assert 'text: modelData.duration; color: theme.textSecondary' in delegate
    assert 'text: modelData.bpm; color: theme.textPrimary' not in delegate
    assert 'text: modelData.key; color: theme.textPrimary' not in delegate
    assert 'text: modelData.duration; color: theme.textPrimary' not in delegate

    harmonic = _snippet(QML_SOURCE, 'objectName: "harmonicMatchList"', 9000)
    assert 'text: modelData.key; color: theme.actionActive' in harmonic
    assert 'text: modelData.key; color: theme.textSecondary' not in harmonic

    assert _int_property(QML_SOURCE, "densityRowHeight") == 30
    assert _int_property(QML_SOURCE, "textMeta") == 11
    assert _int_property(QML_SOURCE, "textBody") == 12


def test_browser_density_waveform_and_divider_invariants():
    """#692 supersedes historical 58..72 browserRowHeight density."""
    assert _int_property(QML_SOURCE, "densityRowHeight") == 30
    assert _int_property(QML_SOURCE, "browserWaveformMin") >= 140
    assert "property int browserRowHeight:" not in QML_SOURCE

    delegate = _snippet(QML_SOURCE, BROWSER_ROW_DELEGATE_MARKER, BROWSER_ROW_DELEGATE_SPAN)
    assert "height: browser.rowHeight" in delegate
    assert "property int rowHeight: window.densityRowHeight" in QML_SOURCE
    assert "Layout.preferredWidth: browserPane.effectiveBrowserWaveformWidth" in delegate
    assert "height: window.densityDividerHeight" in delegate
    assert "color: theme.dividerDefault" in delegate


def test_browser_alternating_row_shading_preserves_state_priority():
    """#781: selection > hover > subtle odd/even base shading."""
    delegate = _snippet(QML_SOURCE, BROWSER_ROW_DELEGATE_MARKER, BROWSER_ROW_DELEGATE_SPAN)
    expected = (
        'color: index === window.screenData.selectedBrowserIndex ? theme.selectionSurface '
        ': (rowSelection.containsMouse ? theme.surfaceElevated '
        ': (index % 2 === 1 ? theme.surfacePanel : "transparent"))'
    )
    assert expected in delegate
    assert "reuseItems: true" in QML_SOURCE


def test_browser_shared_column_spec_uses_single_definition_each():
    for role in _SHARED_DENSITY_ROLES + _SHARED_BROWSER_COLUMN_ROLES:
        assert QML_SOURCE.count(f"property int {role}:") == 1
    assert QML_SOURCE.count("property color divider:") == 1


def test_browser_intent_keyboard_and_virtualization_contracts_preserved():
    assert QML_SOURCE.count("previewRow(index)") == 1
    assert QML_SOURCE.count("addToKit(index)") == 1
    assert QML_SOURCE.count("toggleFavorite(index)") == 1
    # stopPreview() gehört zwei Flächen: Browser-Escape UND Harmonic-Panel (vorbestehend).
    assert 'else if (event.key === Qt.Key_Escape) { window.interaction.stopPreview(); event.accepted = true }' in QML_SOURCE
    assert "Keys.onEscapePressed: window.interaction.stopPreview()" in QML_SOURCE
    assert QML_SOURCE.count('objectName: "harmonicMatchButton"') == 1
    assert QML_SOURCE.count("toggleHarmonicMatch()") == 1
    assert 'text: "Play"' not in QML_SOURCE
    assert 'text: "▶"' not in QML_SOURCE
    assert QML_SOURCE.count("reuseItems: true") == 2
    assert "Component.onCompleted: window.browserDelegateCreations += 1" in QML_SOURCE
    assert "navigateBrowser(1)" in QML_SOURCE
    assert "navigateBrowser(-1)" in QML_SOURCE
    assert QML_SOURCE.count('objectName: "browserList"') == 1


def _ordered_marker_positions(source: str, markers: tuple[str, ...]) -> list[int]:
    positions: list[int] = []
    cursor = 0
    for marker in markers:
        index = source.index(marker, cursor)
        positions.append(index)
        cursor = index + len(marker)
    return positions


def test_browser_default_column_order_matches_767_contract():
    """Waveform → Sample Name → BPM → Favorite → Key → Length."""
    header = _full_browser_column_header(QML_SOURCE)
    # Header uses width placeholders then labels; verify label order + waveform slot first.
    assert header.index("effectiveBrowserWaveformWidth") < header.index('text: "SAMPLE NAME"')
    assert header.index('text: "SAMPLE NAME"') < header.index('text: "BPM"')
    assert header.index('text: "BPM"') < header.index('text: "FAV"')
    assert header.index('text: "FAV"') < header.index('text: "KEY"')
    assert header.index('text: "KEY"') < header.index('text: "LENGTH"')

    delegate = _snippet(QML_SOURCE, BROWSER_ROW_DELEGATE_MARKER, BROWSER_ROW_DELEGATE_SPAN)
    positions = _ordered_marker_positions(delegate, _BROWSER_ROW_ORDER_MARKERS)
    assert positions == sorted(positions)


def test_browser_favorite_column_is_present_and_not_a_rating():
    delegate = _snippet(QML_SOURCE, BROWSER_ROW_DELEGATE_MARKER, BROWSER_ROW_DELEGATE_SPAN)
    assert 'objectName: "browserFavoriteButton"' in delegate
    assert "modelData.favorite" in delegate
    assert "toggleFavorite(index)" in delegate
    # No 1–5 rating chrome.
    assert "rating" not in delegate.lower()
    assert "★★★★★" not in QML_SOURCE
    assert _int_property(QML_SOURCE, "browserFavoriteColumnWidth") <= 32
    assert _int_property(QML_SOURCE, "browserFavoriteColumnWidth") >= 20


def test_browser_sample_name_is_flexible_and_meta_columns_align():
    header = _full_browser_column_header(QML_SOURCE)
    delegate = _snippet(QML_SOURCE, BROWSER_ROW_DELEGATE_MARKER, BROWSER_ROW_DELEGATE_SPAN)
    assert 'text: "SAMPLE NAME"; color: theme.textSecondary; Layout.fillWidth: true' in header
    assert "text: modelData.name; color: theme.textPrimary" in delegate
    assert "Layout.fillWidth: true" in delegate
    for role in (
        "effectiveBrowserMetaColumnWidth",
        "effectiveBrowserFavoriteColumnWidth",
        "effectiveBrowserLengthColumnWidth",
    ):
        assert f"Layout.preferredWidth: browserPane.{role}" in header
        assert f"Layout.preferredWidth: browserPane.{role}" in delegate


def test_browser_sample_type_does_not_displace_default_column_order():
    delegate = _snippet(QML_SOURCE, BROWSER_ROW_DELEGATE_MARKER, BROWSER_ROW_DELEGATE_SPAN)
    type_pos = delegate.index("text: modelData.type")
    # Type may remain secondary after Length, never between Name and Length primary order.
    assert type_pos > delegate.index("text: modelData.duration")
    assert type_pos > delegate.index('objectName: "browserFavoriteButton"')


def test_browser_add_to_kit_remains_available_without_owning_scan_path():
    delegate = _snippet(QML_SOURCE, BROWSER_ROW_DELEGATE_MARKER, BROWSER_ROW_DELEGATE_SPAN)
    add_pos = delegate.index("window.interaction.addToKit(index)")
    assert add_pos > delegate.index("text: modelData.duration")
    assert '"+ Add to Kit"' in delegate
    assert "effectiveBrowserAddColumnWidth" in delegate


def test_browser_density_tokens_unchanged_by_767():
    assert _int_property(QML_SOURCE, "densityRowHeight") == 30
    assert _int_property(QML_SOURCE, "densityVerticalInset") == 4
    assert _int_property(QML_SOURCE, "densityHorizontalInset") == 8
    assert _int_property(QML_SOURCE, "densityWaveformHeight") == 22
    assert _int_property(QML_SOURCE, "densityRowSpacing") == 8
    assert _int_property(QML_SOURCE, "densityDividerHeight") == 1
    assert _int_property(QML_SOURCE, "densityActionHitTarget") == 24


# ---------------------------------------------------------------------------
# #846 — header-owned ephemeral column resize (supersedes #780 presentation)
# ---------------------------------------------------------------------------

_HEADER_RESIZE_OBJECTNAMES = (
    'objectName: "browserColumnResize_waveform"',
    'objectName: "browserColumnResize_meta"',
    'objectName: "browserColumnResize_favorite"',
    'objectName: "browserColumnResize_length"',
)
_LEGACY_ROW_COLUMN_DIVIDER_OBJECTNAMES = (
    'objectName: "browserColumnDivider_waveform"',
    'objectName: "browserColumnDivider_bpm"',
    'objectName: "browserColumnDivider_favorite"',
    'objectName: "browserColumnDivider_key"',
    'objectName: "browserColumnDivider_length"',
)
_INTERACTIVE_HEADER_RESIZE_COUNT = 4
_META_RESIZE_CALL = 'browserPane.resizeColumn("meta"'


def _browser_delegate_full(source: str) -> str:
    """Delegate body from its marker up to (not into) the panel resize handle.

    Robust to delegate growth: always covers the full row delegate incl. the
    bottom horizontal divider, and always stops before ``elasticHandleAfterBrowser``
    so panel-resize (``layoutModel``) code never leaks into delegate assertions.
    """
    start = source.index(BROWSER_ROW_DELEGATE_MARKER)
    end = source.index('objectName: "elasticHandleAfterBrowser"', start)
    return source[start:end]


def _browser_header_block(source: str) -> str:
    """Header label row through ListView start (column header chrome only)."""
    # The Browser header RowLayout that carries SAMPLE NAME / BPM / … labels.
    marker = 'Label { text: "SAMPLE NAME"'
    start = source.index(marker)
    # Walk backward to the enclosing RowLayout opening for this header strip.
    row_start = source.rfind("RowLayout", 0, start)
    end = source.index('objectName: "browserList"', start)
    return source[row_start:end]


def _header_resize_window(source: str, object_name: str, span: int = 900) -> str:
    token = f'objectName: "{object_name}"'
    idx = source.index(token)
    return source[idx : idx + span]


def test_browser_rows_have_no_permanent_vertical_column_dividers():
    """#846: row delegates must not paint permanent vertical column dividers."""
    delegate = _browser_delegate_full(QML_SOURCE)
    for name in _LEGACY_ROW_COLUMN_DIVIDER_OBJECTNAMES:
        assert name not in delegate, f"legacy vertical column divider still present: {name}"
    # Horizontal row chrome may still use dividerDefault / densityDividerHeight.
    assert "height: window.densityDividerHeight" in delegate
    assert "color: theme.dividerDefault" in delegate


def test_browser_rows_have_no_column_resize_mouse_areas():
    """#846: column resize MouseAreas leave the virtualized row delegate."""
    delegate = _browser_delegate_full(QML_SOURCE)
    assert "cursorShape: Qt.SizeHorCursor" not in delegate
    assert "browserPane.resizeColumn(" not in delegate
    assert "columnResizeWaveform" not in delegate
    assert "columnResizeBpm" not in delegate
    assert "columnResizeFavorite" not in delegate
    assert "columnResizeLength" not in delegate


def test_browser_column_resize_lives_in_header_overlays():
    """#846: exactly four header-owned resize overlays; not RowLayout width consumers."""
    header = _browser_header_block(QML_SOURCE)
    for name in _HEADER_RESIZE_OBJECTNAMES:
        assert name in header, f"missing header resize surface {name}"
        assert QML_SOURCE.count(name) == 1
    # Overlay geometry: anchored to the right cell edge; must not declare
    # Layout.preferredWidth/minimumWidth on the resize Item itself.
    for object_name in (
        "browserColumnResize_waveform",
        "browserColumnResize_meta",
        "browserColumnResize_favorite",
        "browserColumnResize_length",
    ):
        window = _header_resize_window(QML_SOURCE, object_name)
        assert "anchors.right" in window
        assert "Layout.preferredWidth" not in window
        assert "Layout.minimumWidth" not in window
        assert "cursorShape: Qt.SizeHorCursor" in window
        assert "preventStealing: true" in window
        assert "browserPane.resizeColumn(" in window


def test_browser_column_resize_ephemeral_hover_focus_drag_states():
    """#846: handle visible on hover / focus-visible / drag; quiet otherwise."""
    for object_name in (
        "browserColumnResize_waveform",
        "browserColumnResize_meta",
        "browserColumnResize_favorite",
        "browserColumnResize_length",
    ):
        window = _header_resize_window(QML_SOURCE, object_name, span=1200)
        assert "hovered" in window or "containsMouse" in window
        assert "activeFocus" in window
        assert "pressed" in window
        # Focus chrome uses Theme focus semantic — not a local HEX.
        assert "theme.focusRing" in window or "theme.selectionBorder" in window
        # Hover/elevated chrome uses an existing semantic surface token.
        assert (
            "theme.surfaceElevated" in window
            or "theme.borderSubtle" in window
            or "theme.textSecondary" in window
        )
        assert _HEX_COLOR_RE.search(window) is None
        # No faux keyboard resize / splitter semantics.
        assert "Keys.onPressed" not in window
        assert "Keys.onReturnPressed" not in window
        assert "Keys.onSpacePressed" not in window
        assert "Accessible.role" not in window
        assert "Splitter" not in window
        assert "activeFocusOnTab: true" in window or "activeFocusOnTab: visible" in window


def test_browser_column_width_state_has_exactly_one_owner():
    """#780/#846: browserPane remains the only writer of column width truth."""
    assert QML_SOURCE.count("function resizeColumn(") == 1
    for prop in (
        "waveformUserWidth",
        "metaUserWidth",
        "favoriteUserWidth",
        "lengthUserWidth",
    ):
        assert QML_SOURCE.count(f"property int {prop}:") == 1
    # Header surfaces are the only resizeColumn call sites (four interactive roles).
    assert (
        QML_SOURCE.count("browserPane.resizeColumn(") == _INTERACTIVE_HEADER_RESIZE_COUNT
    )
    assert QML_SOURCE.count(_META_RESIZE_CALL) == 1
    meta_window = _header_resize_window(QML_SOURCE, "browserColumnResize_meta")
    assert _META_RESIZE_CALL in meta_window
    # Key / Type / Add never gain resize writers.
    assert 'objectName: "browserColumnResize_key"' not in QML_SOURCE
    assert 'objectName: "browserColumnResize_type"' not in QML_SOURCE
    assert 'resizeColumn("type"' not in QML_SOURCE
    delegate = _browser_delegate_full(QML_SOURCE)
    assert "property int effectiveBrowser" not in delegate
    assert "layoutModel.applyDrag" not in delegate


def test_browser_column_resize_hit_target_wider_than_visible_handle():
    """#846: hit-area padding stays larger than the quiet visible handle."""
    padding = _int_property(QML_SOURCE, "browserColumnHandlePadding")
    assert padding >= 4
    for object_name in (
        "browserColumnResize_waveform",
        "browserColumnResize_meta",
        "browserColumnResize_favorite",
        "browserColumnResize_length",
    ):
        window = _header_resize_window(QML_SOURCE, object_name)
        assert "browserColumnHandlePadding" in window or "leftMargin" in window
        assert "anchors.leftMargin" in window or "width:" in window


def test_browser_column_resize_ignores_user_overrides_when_narrow():
    """#780/#692: narrow mode keeps responsive defaults over runtime overrides."""
    assert "function _resolveColumn(" in QML_SOURCE
    # Narrow must short-circuit user overrides (browserNarrowColumns || user < 0).
    assert (
        "(browserNarrowColumns || user < 0) ? dflt : user" in QML_SOURCE
        or "(browserNarrowColumns || user < 0)? dflt : user" in QML_SOURCE
    )
    # Narrow responsive defaults still feed _resolveColumn / effective* widths.
    assert (
        "browserNarrowColumns ? window.browserWaveformMin : window.browserWaveformWidth"
        in QML_SOURCE
    )
    assert (
        "browserNarrowColumns ? browserMetaColumnMin : window.browserMetaColumnWidth"
        in QML_SOURCE
    )
    assert (
        "browserNarrowColumns ? browserLengthColumnMin : window.browserLengthColumnWidth"
        in QML_SOURCE
    )


def test_browser_column_resize_minimums_are_deterministic():
    """#780: usable, deterministic min/max per resizable column."""
    waveform_min = _int_property(QML_SOURCE, "browserWaveformMin")
    waveform_max = _int_property(QML_SOURCE, "browserWaveformMax")
    assert waveform_min >= 140
    assert waveform_max > waveform_min
    meta_min = _int_property(QML_SOURCE, "browserMetaColumnMin")
    meta_max = _int_property(QML_SOURCE, "browserMetaColumnMax")
    # Contract mins equal narrow-mode fallbacks (#692 / #780 table).
    assert meta_min == 40
    assert meta_max == 96
    fav_min = _int_property(QML_SOURCE, "browserFavoriteColumnMin")
    fav_max = _int_property(QML_SOURCE, "browserFavoriteColumnMax")
    assert fav_min == 24
    assert fav_max == 48
    length_min = _int_property(QML_SOURCE, "browserLengthColumnMin")
    length_max = _int_property(QML_SOURCE, "browserLengthColumnMax")
    assert length_min == 52
    assert length_max == 120


def test_browser_column_resize_reuses_shared_header_row_geometry():
    """#780/#846: header + delegate keep reading one shared effective geometry."""
    for role in (
        "effectiveBrowserWaveformWidth",
        "effectiveBrowserMetaColumnWidth",
        "effectiveBrowserFavoriteColumnWidth",
        "effectiveBrowserLengthColumnWidth",
    ):
        assert QML_SOURCE.count(f"property int {role}:") == 1
        assert QML_SOURCE.count(f"browserPane.{role}") >= 2
    # Virtualization and existing row intents remain intact alongside resize.
    assert QML_SOURCE.count("reuseItems: true") == 2
    assert QML_SOURCE.count("previewRow(index)") == 1
    assert QML_SOURCE.count("addToKit(index)") == 1
    assert QML_SOURCE.count("toggleFavorite(index)") == 1
    # Horizontal row divider / alternating shading remain (#781 / density).
    delegate = _browser_delegate_full(QML_SOURCE)
    assert "height: window.densityDividerHeight" in delegate
    assert "index % 2 === 1 ? theme.surfacePanel" in QML_SOURCE


def test_browser_column_resize_does_not_collide_with_panel_collapse_845():
    """#846 must not put SizeHorCursor / applyDrag on #845 collapse handles."""
    assert 'objectName: "browserCollapseHandle"' in QML_SOURCE
    assert 'objectName: "browserCollapseAffordance"' in QML_SOURCE
    for handle in (
        "browserCollapseHandle",
        "harmonyCollapseHandle",
        "liveKitCollapseHandle",
    ):
        idx = QML_SOURCE.index(f'objectName: "{handle}"')
        window = QML_SOURCE[idx : idx + 1200]
        assert "SizeHorCursor" not in window
        assert "layoutModel.applyDrag" not in window
        assert "browserPane.resizeColumn" not in window
