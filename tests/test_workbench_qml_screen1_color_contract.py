"""Screen-1 color contract: Theme Core via themeAuthority → semantic tokens → components.

#785: QML must not invent a second HEX palette. Semantic roles bind from
themeAuthority (mapped by workbench_theme.theme_tokens_to_qml_semantics).
"""

from __future__ import annotations

import re

from src import workbench_qml
from src import workbench_theme as theme

NAMED_COLOR_EXCEPTIONS: frozenset[str] = frozenset({"transparent"})

REQUIRED_SEMANTIC_NAMES: tuple[str, ...] = (
    "surfaceRoot",
    "surfaceHeader",
    "surfaceBrowser",
    "surfacePanel",
    "surfaceElevated",
    "borderSubtle",
    "dividerDefault",
    "textPrimary",
    "textSecondary",
    "textDisabled",
    "textOnAction",
    "waveformDefault",
    "waveformActive",
    "selectionSurface",
    "selectionBorder",
    "actionActive",
    "hoverSurface",
)

_HEX_RE = re.compile(r'"(#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8}))"')
_NAMED_COLOR_RE = re.compile(
    r'(?:color|border\.color|strokeStyle|placeholderTextColor)\s*:\s*"([a-zA-Z]+)"'
)


def _extract_theme_block(source: str) -> str:
    marker = "QtObject {\n        id: theme"
    start = source.find(marker)
    assert start >= 0, "theme QtObject with id: theme is required in QML_SOURCE"
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
    raise AssertionError("unclosed theme QtObject in QML_SOURCE")


def test_theme_semantic_tokens_bind_theme_authority():
    source = workbench_qml.QML_SOURCE
    theme_block = _extract_theme_block(source)
    assert "themeAuthority" in source
    for name in REQUIRED_SEMANTIC_NAMES:
        assert re.search(
            rf"readonly property color {name}:\s*themeAuthority\.{name}",
            theme_block,
        ), f"missing themeAuthority binding for {name}"
        assert not re.search(
            rf"readonly property color {name}:\s*\"#",
            theme_block,
        ), f"semantic token {name} must not hardcode HEX"


def test_qml_source_has_no_hex_hardcodes():
    source = workbench_qml.QML_SOURCE
    found = sorted({m.group(1).lower() for m in _HEX_RE.finditer(source)})
    assert found == [], f"HEX hardcodes remain in QML_SOURCE: {found}"


def test_qml_components_prefer_semantic_theme_tokens():
    source = workbench_qml.QML_SOURCE
    theme_block = _extract_theme_block(source)
    outside = source.replace(theme_block, "", 1)
    for legacy in (
        'property color panel: "#',
        'property color accent: "#',
        'property color selectedRow: "#',
        'color: "#000000"',
        'color: "#0c0d0e"',
        'color: "#b1122b"',
    ):
        assert legacy not in outside

    for needle in (
        "theme.surfaceRoot",
        "theme.surfaceHeader",
        "theme.surfaceBrowser",
        "theme.surfacePanel",
        "theme.surfaceElevated",
        "theme.borderSubtle",
        "theme.dividerDefault",
        "theme.textPrimary",
        "theme.textSecondary",
        "theme.actionActive",
        "theme.selectionSurface",
        "theme.selectionBorder",
        "theme.waveformDefault",
        "theme.waveformActive",
        "theme.hoverSurface",
    ):
        assert needle in outside, f"missing semantic usage: {needle}"


def test_named_color_hardcodes_are_only_documented_exceptions():
    source = workbench_qml.QML_SOURCE
    theme_block = _extract_theme_block(source)
    outside = source.replace(theme_block, "", 1)
    found = {m.group(1).lower() for m in _NAMED_COLOR_RE.finditer(outside)}
    unexpected = sorted(found - NAMED_COLOR_EXCEPTIONS)
    assert unexpected == [], f"undocumented named color hardcodes: {unexpected}"


def test_theme_core_mapping_covers_required_qml_semantics():
    mapped = theme.theme_tokens_to_qml_semantics(theme.resolve_theme("Blood"))
    for name in REQUIRED_SEMANTIC_NAMES:
        assert name in mapped, f"Theme Core map missing {name}"
        assert mapped[name].startswith("#")
    assert mapped["textOnAction"].lower() == "#ffffff"


def test_functional_accent_comes_from_theme_core_not_legacy_hardcode():
    source = workbench_qml.QML_SOURCE.casefold()
    for banned in ("#ff4500", "#00bfff", "#1e90ff", "#00ffff", "#ff00ff"):
        assert banned not in source
    # Legacy fixed Blood HEX must not reappear as QML truth (#785 Theme Core).
    assert '#b1122b' not in source
    blood = theme.theme_tokens_to_qml_semantics(theme.resolve_theme("Blood"))
    assert blood["actionActive"].lower() == theme.resolve_theme("Blood").accent.lower()
