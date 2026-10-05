"""#895 secondary control / panel chrome — TEST_FREEZE contracts.

Presentation-only: Add Source, Remove, Search, Live Kit slot/card chrome, and
Harmonic secondary row chrome must share the dark slim Theme Authority language.
Layout/IA/behavior stay unchanged. Do not overfit fragile full-Button source
blobs; bind objectNames + theme tokens + runtime semantics.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

from src.workbench_qml import QML_SOURCE

PY_SIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None

# Bright utility-widget fills that must not appear as control backgrounds.
_FORBIDDEN_BRIGHT_FILLS = (
    '"#ffffff"',
    '"#fff"',
    '"white"',
    '"#f0f0f0"',
    '"#e0e0e0"',
    '"#dddddd"',
    '"#cccccc"',
)


def _library_header_block() -> str:
    pane = QML_SOURCE.split('objectName: "libraryPane"', 1)[1]
    header = pane.split("id: libraryHeaderRow", 1)[1]
    return header.split('objectName: "libraryContentHost"', 1)[0]


def _browser_search_block() -> str:
    start = QML_SOURCE.index('objectName: "browserSearch"')
    # Capture the TextField including its custom background / text bindings.
    return QML_SOURCE[start : start + 1600]


def _live_kit_block() -> str:
    return QML_SOURCE.split('objectName: "liveKitPane"', 1)[1].split(
        'objectName: "channelRackScreen"', 1
    )[0]


def _harmony_list_block() -> str:
    return QML_SOURCE.split('objectName: "harmonicMatchList"', 1)[1].split(
        'objectName: "elasticHandleAfterHarmony"', 1
    )[0]


def _extract_named_control(source: str, object_name: str, *, window: int = 2400) -> str:
    marker = f'objectName: "{object_name}"'
    assert marker in source, f"missing {object_name}"
    start = source.index(marker)
    # Walk backward to the owning Button/TextField/Rectangle keyword.
    head = source.rfind("\n", 0, start)
    return source[max(0, head) : start + window]


# --- Visual / theme contracts (source-level, non-fragile) ---------------------


def test_library_add_remove_use_named_theme_bound_secondary_chrome() -> None:
    header = _library_header_block()
    add = _extract_named_control(header, "libraryAddSourceButton")
    remove = _extract_named_control(header, "libraryRemoveSourceButton")

    for block, label in ((add, "Add Source"), (remove, "Remove")):
        assert f'text: "{label}"' in block or f"text: '{label}'" in block
        assert "flat: true" in block
        assert "contentItem: Text" in block
        assert "background: Rectangle" in block
        assert "theme.textSecondary" in block or "theme.textPrimary" in block
        assert "theme.borderSubtle" in block
        assert "theme.focusRing" in block or "theme.selectionBorder" in block
        assert "theme.hoverSurface" in block or "theme.surfaceElevated" in block
        for bright in _FORBIDDEN_BRIGHT_FILLS:
            assert bright not in block.lower() and bright not in block

    assert "addSourceDialog.open()" in add
    assert "libraryInteraction.prepareRemoveSource()" in remove
    assert "libraryInteraction.canRemoveSelectedSource" in remove


def test_browser_search_is_dark_theme_native_field() -> None:
    block = _browser_search_block()
    assert "placeholderText: \"Search samples\"" in block
    assert "placeholderTextColor: theme.textSecondary" in block
    assert "color: theme.textPrimary" in block
    assert "background: Rectangle" in block
    assert "theme.borderSubtle" in block
    assert "theme.focusRing" in block
    # Quiet fill — not a bright form slab; allow transparent or hoverSurface.
    assert (
        'color: "transparent"' in block
        or "theme.hoverSurface" in block
        or "theme.surfaceElevated" in block
        or "theme.surfacePanel" in block
    )
    assert "onTextChanged: window.interaction.setBrowserSearch(text)" in block
    for bright in _FORBIDDEN_BRIGHT_FILLS:
        assert bright not in block


def test_live_kit_group_chrome_is_light_not_heavy_card() -> None:
    live = _live_kit_block()
    # Heavy default card mass from pre-#895 (radius 6 + elevated fill always).
    # Active may still lift quietly; inactive must stay transparent/low mass.
    group_delegate = live.split("Repeater { model: window.screenData.liveKitGroups", 1)[1]
    group_rect = group_delegate.split("delegate: Rectangle", 1)[1][:1600]
    assert "radius: 4" in group_rect or "radius: 3" in group_rect
    assert "radius: 6" not in group_rect
    # Quiet active lift (hoverSurface) or elevated; inactive stays transparent.
    assert '"transparent"' in group_rect
    assert "theme.hoverSurface" in group_rect or "theme.surfaceElevated" in group_rect
    assert "theme.borderSubtle" in group_rect
    # Active border may use accent sparingly; quiet selectionBorder is also fine.
    assert "theme.actionActive" in group_rect or "theme.selectionBorder" in group_rect
    # Export Kit shares secondary chrome language.
    export = _extract_named_control(live, "liveKitExportButton", window=2400)
    assert "flat: true" in export
    assert "background: Rectangle" in export or "background: Item" in export
    assert "theme." in export


def test_harmonic_row_chrome_shares_browser_language() -> None:
    harmony = _harmony_list_block()
    # Rows: selected/hover via theme surfaces; no always-on heavy box border.
    assert "theme.surfaceElevated" in harmony or "theme.selectionSurface" in harmony
    assert "theme.dividerDefault" in harmony
    assert "+ Add" in harmony
    assert "theme.textSecondary" in harmony
    assert "window.interaction.addHarmonyToKit" in harmony
    # Avoid permanent bright/boxed border on every row.
    delegate = harmony.split("delegate: Rectangle", 1)[1][:700]
    assert 'border.color: theme.borderSubtle' not in delegate.split("\n", 1)[0]
    # Matching logic hooks unchanged.
    assert "selectHarmonyRow" in harmony
    assert "previewHarmonyRow" in harmony


def test_secondary_controls_have_hover_pressed_focus_disabled_presentation() -> None:
    header = _library_header_block()
    add = _extract_named_control(header, "libraryAddSourceButton", window=1800)
    # State language present on Add Source (shared by Remove via same pattern).
    assert "hovered" in add
    assert "pressed" in add or "down" in add
    assert "activeFocus" in add
    assert "enabled" in add or "opacity" in add
    search = _browser_search_block()
    assert "activeFocus" in search


def test_no_second_qml_palette_in_polished_controls() -> None:
    chunks = (
        _library_header_block(),
        _browser_search_block(),
        _live_kit_block()[:4000],
        _harmony_list_block()[:2500],
    )
    hex_re = re.compile(r'"#(?:[0-9a-fA-F]{3,8})"')
    for chunk in chunks:
        found = hex_re.findall(chunk)
        assert found == [], f"hardcoded HEX in secondary chrome: {found}"


def test_docs_gate_documents_895_secondary_control_contract() -> None:
    acceptance = Path("docs/WORKBENCH_VISUAL_ACCEPTANCE.md").read_text(encoding="utf-8")
    assert "Secondary control and panel chrome (#895)" in acceptance
    assert "895-browser-library-controls" in acceptance
    assert "READY_FOR_OWNER_VISUAL_REVIEW" in acceptance
    themes = Path("docs/assets/themes/README.md").read_text(encoding="utf-8")
    assert "Secondary control chrome (#895)" in themes
    assert "hoverSurface" in themes


# --- Behavior regression (must stay green through presentation polish) --------


def test_add_remove_action_wiring_unchanged() -> None:
    header = _library_header_block()
    assert "addSourceDialog.open()" in header
    assert "libraryInteraction.prepareRemoveSource()" in header
    assert "canRemoveSelectedSource" in header
    # Calm-canvas Add Source path remains (First View) — not this polish target,
    # but must not be deleted as collateral.
    assert 'objectName: "calmCanvasAddSource"' in QML_SOURCE


def test_pattern_bars_song_untouched_by_895_markers() -> None:
    # #895 must not reopen Pattern/Bars/Song chrome.
    assert "Pattern/Bars/Song" not in _library_header_block()
    # Channel Rack screen still exists as separate surface.
    assert 'objectName: "channelRackScreen"' in QML_SOURCE


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_runtime_library_add_remove_are_dark_not_default_white() -> None:
    from PySide6.QtGui import QColor
    from PySide6.QtQuick import QQuickItem

    from tests.test_program_chrome_qml_831 import _build_screen1_window

    app, engine, window, _adapter, settle = _build_screen1_window()
    try:
        window.setWidth(1600)
        window.setHeight(900)
        settle(app)
        settle(app)

        add = window.findChild(QQuickItem, "libraryAddSourceButton")
        assert add is not None
        assert str(add.property("text")) == "Add Source"
        assert bool(add.property("flat")) is True

        bg = add.property("background")
        assert bg is not None
        color = bg.property("color")
        assert isinstance(color, QColor)
        # Dark / transparent baseline — not a bright default Button slab.
        assert color.alphaF() < 0.35 or (
            color.redF() < 0.35 and color.greenF() < 0.35 and color.blueF() < 0.35
        ), f"Add Source background too bright: {color.name(QColor.HexArgb)}"

        search = window.findChild(QQuickItem, "browserSearch")
        assert search is not None
        search_color = search.property("color")
        assert isinstance(search_color, QColor)
        # Text ink must be light-on-dark (high luma), not dark default on white field.
        assert (
            0.2126 * search_color.redF()
            + 0.7152 * search_color.greenF()
            + 0.0722 * search_color.blueF()
        ) > 0.45

        search_bg = search.property("background")
        assert search_bg is not None
        sbg = search_bg.property("color")
        assert isinstance(sbg, QColor)
        assert sbg.alphaF() < 0.55 or (
            sbg.redF() < 0.35 and sbg.greenF() < 0.35 and sbg.blueF() < 0.35
        ), f"Search background too bright: {sbg.name(QColor.HexArgb)}"
    finally:
        window.close()
        app.processEvents()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_runtime_search_focus_and_filter_behavior_unchanged() -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtQuick import QQuickItem

    from src.workbench_controller import WorkbenchRow
    from tests.test_program_chrome_qml_831 import _build_screen1_window

    app, engine, window, adapter, settle = _build_screen1_window()
    try:
        window.setWidth(1600)
        window.setHeight(900)
        settle(app)

        vm = adapter.view_model
        vm.set_browser_state(
            rows=(
                WorkbenchRow(
                    display_name="alpha kick",
                    relative_path="alpha kick",
                    path="/tmp/alpha_kick.wav",
                    bpm=120.0,
                    key="Cmaj",
                    key_conf=0.9,
                    loudness=None,
                    brightness=None,
                    sample_class="one_shot",
                    pred_type="Kick",
                    status="ok",
                    details={},
                ),
                WorkbenchRow(
                    display_name="beta snare",
                    relative_path="beta snare",
                    path="/tmp/beta_snare.wav",
                    bpm=120.0,
                    key="Amin",
                    key_conf=0.9,
                    loudness=None,
                    brightness=None,
                    sample_class="one_shot",
                    pred_type="Snare",
                    status="ok",
                    details={},
                ),
            ),
            selected_index=0,
            browser_context="All Samples",
            error=None,
        )
        settle(app)

        search = window.findChild(QQuickItem, "browserSearch")
        assert search is not None
        search.forceActiveFocus()
        settle(app)
        assert bool(search.hasActiveFocus())

        search.setProperty("text", "alpha")
        settle(app)
        assert len(vm.browser_rows) == 1
        assert vm.browser_rows[0].source_row.display_name == "alpha kick"

        # Clear via view-model search contract (same path setBrowserSearch uses).
        vm.set_browser_search_query("")
        settle(app)
        assert len(vm.browser_rows) == 2
        assert bool(search.hasActiveFocus()) or search.property("activeFocusOnTab") is not False
        _ = Qt  # keep import used for future key events
    finally:
        window.close()
        app.processEvents()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_runtime_live_kit_and_harmonic_interactions_unchanged() -> None:
    from PySide6.QtQuick import QQuickItem

    from tests.test_program_chrome_qml_831 import _build_screen1_window

    app, engine, window, adapter, settle = _build_screen1_window()
    try:
        window.setWidth(1600)
        window.setHeight(900)
        settle(app)

        # Live Kit present in fixture 3-panel; collapse toggle remains.
        live = window.findChild(QQuickItem, "liveKitPane")
        assert live is not None
        assert callable(getattr(adapter, "toggle_live_kit_group", None)) or callable(
            getattr(adapter, "toggleLiveKitGroup", None)
        ) or "toggleLiveKitGroup" in QML_SOURCE

        before_open = bool(adapter.harmonic_match_open)
        adapter.toggle_harmonic_match()
        settle(app)
        assert bool(adapter.harmonic_match_open) is (not before_open)
        harmony = window.findChild(QQuickItem, "harmonyPane")
        assert harmony is not None
        adapter.toggle_harmonic_match()
        settle(app)
        assert bool(adapter.harmonic_match_open) is before_open
    finally:
        window.close()
        app.processEvents()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_runtime_880_885_894_chrome_regressions_still_hold() -> None:
    """Slim header/footer + centered footer context + dark hierarchy still bind."""
    from PySide6.QtQuick import QQuickItem

    from src import workbench_theme as theme
    from tests.test_program_chrome_qml_831 import _build_screen1_window

    app, engine, window, _adapter, settle = _build_screen1_window()
    try:
        window.setWidth(1600)
        window.setHeight(900)
        settle(app)

        header = window.findChild(QQuickItem, "screen1Header")
        footer = window.findChild(QQuickItem, "programFooterBand")
        assert header is not None and footer is not None
        assert 26.0 <= float(header.height()) <= 34.0
        assert 18.0 <= float(footer.height()) <= 26.0

        center = window.findChild(QQuickItem, "footerContextCenterLayer")
        assert center is not None

        # Theme Authority hierarchy still exposed on facade.
        blood = theme.resolve_theme("Blood")
        assert blood.background.lower() != blood.as_dict()["surfaceWorkspace"].lower()
        assert blood.as_dict()["surfaceWorkspace"].lower() != blood.surface.lower()
    finally:
        window.close()
        app.processEvents()
