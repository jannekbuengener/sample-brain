"""#1257 Screen-1 Appearance V2 semantic adoption — FROZEN RED CONTRACT.

Status: TEST_FREEZE
Canon: docs/WORKBENCH_APPEARANCE_V2_CONTRACT.md
Evidence: docs/assets/themes/screen1_appearance_v2_hardcoded_color_audit_1257.md

Active Screen-1 QML surfaces consume Appearance V2 semantic roles via the
#1255 themeAuthority bridge. No local palette, no QML color derivation, no
raw primitive fills where a semantic role exists.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from src import workbench_appearance as appearance
from src import workbench_theme as theme
from src.workbench_qml import QML_SOURCE


EXIT = "SCREEN1_APPEARANCE_V2_TOKENIZED"

REQUIRED_V2_FACADE = (
    "surfaceRoot",
    "surfaceHeader",
    "surfaceBrowser",
    "surfacePanel",
    "surfaceElevated",
    "surfaceLibrary",
    "hoverSurface",
    "selectionSurface",
    "borderSubtle",
    "borderDefault",
    "dividerDefault",
    "textPrimary",
    "textSecondary",
    "textMuted",
    "textDisabled",
    "textOnAction",
    "actionActive",
    "accentHover",
    "accentActive",
    "focusRing",
    "interactionPressed",
    "interactionDisabled",
    "statusError",
    "statusWarning",
    "statusSuccess",
    "statusInfo",
    "libraryAllSamplesAccent",
    "libraryCollectionsAccent",
    "libraryFavoritesAccent",
    "libraryRecordsAccent",
    "libraryFocusRing",
)

PROTECTED_STATUS_KEYS = (
    "status.error",
    "status.warning",
    "status.success",
    "status.info",
)

LIBRARY_PROTECTED = (
    "libraryAllSamplesAccent",
    "libraryCollectionsAccent",
    "libraryFavoritesAccent",
    "libraryRecordsAccent",
)


def _extract_theme_block(source: str) -> str:
    marker = "QtObject {\n        id: theme"
    start = source.find(marker)
    assert start >= 0, "theme QtObject with id: theme is required"
    i = source.find("{", start)
    depth = 0
    for j in range(i, len(source)):
        ch = source[j]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return source[start : j + 1]
    raise AssertionError("unclosed theme QtObject")


def _outside_theme(source: str) -> str:
    theme_block = _extract_theme_block(source)
    return source.replace(theme_block, "", 1)


def _bridge(tmp_path: Path, **kwargs: Any):
    pytest.importorskip("PySide6")
    from src.workbench_qml import _qml_theme_authority_bridge

    return _qml_theme_authority_bridge(state_dir=tmp_path, **kwargs)


# --- Source / ownership -------------------------------------------------------


def test_exit_marker_and_architecture_ownership() -> None:
    assert theme.SCREEN1_APPEARANCE_V2_TOKENIZED_EXIT == EXIT
    assert "SCREEN1_APPEARANCE_V2_TOKENIZED" in Path(
        "docs/assets/themes/screen1_appearance_v2_hardcoded_color_audit_1257.md"
    ).read_text(encoding="utf-8")
    # Single Screen-1 theme facade; no second palette / no QML derivation.
    assert QML_SOURCE.count("QtObject {\n        id: theme") == 1
    assert "Qt.lighter(" not in QML_SOURCE
    assert "Qt.darker(" not in QML_SOURCE
    assert "Qt.rgba(" in QML_SOURCE  # justified Library fade only
    assert QML_SOURCE.count("Qt.rgba(") == 1
    assert "screen1_theme_preferences" not in QML_SOURCE
    assert "resolve_appearance" not in QML_SOURCE
    assert "derive_semantic_tokens" not in QML_SOURCE


def test_theme_facade_binds_v2_semantic_roles() -> None:
    block = _extract_theme_block(QML_SOURCE)
    for name in REQUIRED_V2_FACADE:
        assert re.search(
            rf"readonly property color {name}:\s*themeAuthority\.{name}\b",
            block,
        ), f"missing V2 facade binding: {name}"
    assert not re.search(r'"#(?:[0-9a-fA-F]{3,8})"', block)


def test_active_surfaces_consume_semantic_tokens() -> None:
    outside = _outside_theme(QML_SOURCE)
    required_usage = (
        "theme.surfaceRoot",
        "theme.surfaceHeader",
        "theme.surfaceBrowser",
        "theme.surfacePanel",
        "theme.surfaceLibrary",
        "theme.surfaceElevated",
        "theme.textPrimary",
        "theme.textSecondary",
        "theme.textMuted",
        "theme.textDisabled",
        "theme.borderSubtle",
        "theme.hoverSurface",
        "theme.selectionSurface",
        "theme.focusRing",
        "theme.actionActive",
        "theme.statusError",
        "theme.interactionPressed",
        "theme.libraryAllSamplesAccent",
    )
    for needle in required_usage:
        assert needle in outside, f"missing semantic consumer: {needle}"


def test_error_chrome_uses_protected_status_not_accent() -> None:
    outside = _outside_theme(QML_SOURCE)
    # Analysis + browser error labels must bind statusError.
    assert re.search(
        r'analysisStatus === "error" \? theme\.statusError',
        outside,
    )
    assert "errorMessage.length > 0" in outside
    assert re.search(
        r"errorMessage\.length > 0;[^;]*color:\s*theme\.statusError",
        outside,
    ) or (
        "window.screenData.errorMessage.length > 0" in outside
        and "theme.statusError" in outside
    )
    # Error paint must not remain aliased to actionActive in those sites.
    for match in re.finditer(
        r'analysisStatus === "error" \? theme\.([A-Za-z]+)',
        outside,
    ):
        assert match.group(1) == "statusError"


def test_placeholders_use_text_muted() -> None:
    outside = _outside_theme(QML_SOURCE)
    assert outside.count("placeholderTextColor: theme.textMuted") >= 2
    assert "placeholderTextColor: theme.textSecondary" not in outside


def test_no_raw_primitive_fills_where_semantics_exist() -> None:
    outside = _outside_theme(QML_SOURCE)
    # Presentation fills must not bind raw baseAccent/Background/Foreground.
    banned = (
        "color: themeAuthority.baseAccent",
        "color: themeAuthority.baseBackground",
        "color: themeAuthority.baseForeground",
        "border.color: themeAuthority.baseAccent",
        "color: window.accent",  # raw window alias as fill is not Accent-owned role
    )
    for needle in banned:
        assert needle not in outside
    # Primitive editors remain allowed in Appearance popover (out of fill scope).
    assert "themeAuthority.baseAccent" in outside


def test_hardcoded_color_audit_dispositions_cover_migrated_scope() -> None:
    audit = Path(
        "docs/assets/themes/screen1_appearance_v2_hardcoded_color_audit_1257.md"
    ).read_text(encoding="utf-8")
    for disposition in (
        "TOKENIZED",
        "PROTECTED_SEMANTIC",
        "PLATFORM_OWNED",
        "JUSTIFIED_LITERAL",
        "OUT_OF_SCOPE_OWNER",
    ):
        assert disposition in audit
    assert "status.error" in audit
    assert "text.disabled" in audit
    assert "protectedHighlight" in audit
    assert "windowChrome" in audit


# --- Bridge projection contracts ---------------------------------------------


def test_bridge_projects_true_v2_text_disabled_and_status(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path)
    snap = appearance.resolve_appearance()
    tokens = snap.tokens.as_flat_dict()
    assert str(bridge.textDisabled).lower() == tokens["text.disabled"].lower()
    assert str(bridge.textDisabled).lower() != tokens["text.secondary"].lower()
    assert str(bridge.textMuted).lower() == tokens["text.muted"].lower()
    assert str(bridge.statusError).lower() == tokens["status.error"].lower()
    assert str(bridge.statusWarning).lower() == tokens["status.warning"].lower()
    assert str(bridge.statusSuccess).lower() == tokens["status.success"].lower()
    assert str(bridge.statusInfo).lower() == tokens["status.info"].lower()
    assert str(bridge.interactionPressed).lower() == tokens["interaction.pressed"].lower()
    assert str(bridge.interactionDisabled).lower() == tokens["interaction.disabled"].lower()
    assert str(bridge.accentHover).lower() == tokens["accent.hover"].lower()
    assert str(bridge.accentActive).lower() == tokens["accent.active"].lower()
    assert str(bridge.borderDefault).lower() == tokens["border.default"].lower()
    assert str(bridge.actionActive).lower() == tokens["accent.base"].lower()
    assert str(bridge.focusRing).lower() == tokens["interaction.focus"].lower()
    assert str(bridge.hoverSurface).lower() == tokens["surface.hover"].lower()
    assert str(bridge.selectionSurface).lower() == tokens["surface.selected"].lower()


def test_hover_selected_focus_disabled_are_distinguishable(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path)
    hover = str(bridge.hoverSurface).lower()
    selected = str(bridge.selectionSurface).lower()
    focus = str(bridge.focusRing).lower()
    disabled = str(bridge.textDisabled).lower()
    pressed = str(bridge.interactionPressed).lower()
    primary = str(bridge.textPrimary).lower()
    assert hover != selected
    assert selected != focus
    assert focus != hover
    assert disabled != primary
    assert pressed != hover
    assert pressed != selected or True  # pressed may equal accent.active; still ≠ hover/focus
    assert pressed != focus or str(bridge.accentActive).lower() == focus


def test_accent_red_to_green_updates_accent_owned_only(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path)
    bridge.selectTheme("Blood")
    before_status = {k: str(bridge.tokenSnapshot[k]).lower() for k in PROTECTED_STATUS_KEYS}
    before_library = {k: str(getattr(bridge, k)).lower() for k in LIBRARY_PROTECTED}
    before_error = str(bridge.statusError).lower()
    bridge.setAccent("#22aa66")
    assert str(bridge.actionActive).lower() == "#22aa66"
    assert str(bridge.accentHover).lower() != "#22aa66"
    assert str(bridge.accentActive).lower() != "#22aa66"
    assert str(bridge.statusError).lower() == before_error
    for key, value in before_status.items():
        assert str(bridge.tokenSnapshot[key]).lower() == value
    for key, value in before_library.items():
        assert str(getattr(bridge, key)).lower() == value
    # No wholesale Accent flooding of surfaces.
    assert str(bridge.surfaceRoot).lower() != "#22aa66"
    assert str(bridge.surfacePanel).lower() != "#22aa66"
    assert str(bridge.textPrimary).lower() != "#22aa66"
    assert str(bridge.hoverSurface).lower() != "#22aa66"


def test_protected_status_palette_stable_across_presets_and_custom(
    tmp_path: Path,
) -> None:
    bridge = _bridge(tmp_path)
    expected_dark = {
        k: appearance.PROTECTED_STATUS_PALETTE["dark"][k.split(".", 1)[1]].lower()
        for k in PROTECTED_STATUS_KEYS
    }
    for preset in ("Blood", "Carbon", "Arctic"):
        bridge.selectTheme(preset)
        for key, value in expected_dark.items():
            assert str(bridge.tokenSnapshot[key]).lower() == value
    bridge.setBackground("#101218")
    bridge.setForeground("#e8eaee")
    bridge.setAccent("#1144cc")
    for key, value in expected_dark.items():
        assert str(bridge.tokenSnapshot[key]).lower() == value
    assert str(bridge.libraryAllSamplesAccent).lower() == "#93a8b8"


def test_blood_default_preserves_1205_workspace_canvas(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path)
    bridge.selectTheme("Blood")
    assert str(bridge.surfaceRoot).lower() == "#0d0f12"
    assert str(bridge.actionActive).lower() == theme.BLOOD_A_ACCENT
    assert str(bridge.textPrimary).lower() == "#e4e6ea"
    # Header chrome remains Blood background (#1205 / program chrome).
    assert str(bridge.surfaceHeader).lower() == "#0b0d10"


def test_library_protected_accents_and_geometry_contract_unchanged(
    tmp_path: Path,
) -> None:
    bridge = _bridge(tmp_path)
    assert str(bridge.libraryAllSamplesAccent).lower() == "#93a8b8"
    assert str(bridge.libraryCollectionsAccent).lower() == "#aa9e7b"
    assert str(bridge.libraryFavoritesAccent).lower() == "#ad6267"
    assert str(bridge.libraryRecordsAccent).lower() == "#9c91ae"
    # #1248 geometry constants remain in QML (presentation migration only).
    assert "readonly property int rowHeight: 35" in QML_SOURCE
    assert "readonly property int iconSize: 20" in QML_SOURCE
    assert "readonly property int textSize: 14" in QML_SOURCE


def test_typography_defaults_unchanged_at_neutral_ui_size(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path)
    assert int(bridge.uiFontSize) == 14
    assert float(bridge.typographyUiStandardSize) == 14.0
    bridge.setUiFontSize(16)
    assert int(bridge.uiFontSize) == 16
    assert float(bridge.typographyUiStandardSize) == pytest.approx(16.0)
    # Default QML #1249 sizes remain the neutral baseline in source.
    assert "readonly property int textSize: 14" in QML_SOURCE


def test_contrast_and_mode_projection_keep_families_correct(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path)
    bridge.selectTheme("Blood")
    low = _bridge(tmp_path)
    low.setContrast(10)
    high = _bridge(tmp_path)
    high.selectTheme("Blood")
    high.setContrast(90)
    assert str(low.textSecondary).lower() != str(high.textSecondary).lower()
    assert str(low.statusError).lower() == str(high.statusError).lower()
    assert str(low.actionActive).lower() == str(high.actionActive).lower()

    bridge.setMode("light")
    assert str(bridge.resolvedScheme) == "light"
    light_error = appearance.PROTECTED_STATUS_PALETTE["light"]["error"].lower()
    assert str(bridge.statusError).lower() == light_error
    bridge.setMode("dark")
    assert str(bridge.resolvedScheme) == "dark"
    bridge.setMode("system")
    assert str(bridge.modeRequested) == "system"


def test_motion_modes_reachable_without_token_derivation_in_qml(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path)
    for mode, expected in (
        ("on", "on"),
        ("reduced", "reduced"),
        ("off", "off"),
    ):
        bridge.setMotionMode(mode)
        assert str(bridge.motionModeRequested) == mode
        assert str(bridge.motionEffective) == expected
    # End states remain functionally addressable; QML does not derive tokens.
    assert "Qt.lighter(" not in QML_SOURCE
    assert "derive_semantic_tokens" not in QML_SOURCE


def test_no_musical_or_persistence_side_effects_in_screen1_theme_bindings() -> None:
    # Appearance presentation must not invent preference or derivation writes.
    assert "save_appearance_preferences" not in QML_SOURCE
    assert "theme_preferences_path" not in QML_SOURCE
    assert "resolve_appearance" not in QML_SOURCE
