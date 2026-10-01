"""Screen-1 canonical color contract: Theme Core → themeAuthority → semantic tokens.

#785 migrates color truth from a hardcoded QML primitive palette to Theme Core
(`src/workbench_theme.py`) exposed as `themeAuthority`. Components bind only
`theme.<semantic>` (and optional thin window aliases).
"""

from __future__ import annotations

import re

from src import workbench_theme as theme_core
from src import workbench_qml

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
    "focusRing",
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


def _hex_values(text: str) -> list[str]:
    return [m.group(1).lower() for m in _HEX_RE.finditer(text)]


def _normalize_hex(value: str) -> str:
    raw = value.lower()
    if len(raw) == 4:  # #rgb
        return "#" + "".join(ch * 2 for ch in raw[1:])
    if len(raw) == 9:  # #aarrggbb → compare rgb only
        return "#" + raw[3:]
    return raw


def test_theme_facade_binds_required_semantics_to_theme_authority():
    theme = _extract_theme_block(workbench_qml.QML_SOURCE)
    for name in REQUIRED_SEMANTIC_NAMES:
        assert re.search(
            rf"readonly property color {name}:\s*themeAuthority\.",
            theme,
        ), f"missing themeAuthority binding for {name}"
    assert not _HEX_RE.search(theme), "theme facade must not hardcode HEX"


def test_qml_source_has_no_stray_hex_hardcodes():
    source = workbench_qml.QML_SOURCE
    theme = _extract_theme_block(source)
    outside = source.replace(theme, "", 1)
    stray = sorted({_normalize_hex(h) for h in _hex_values(outside)})
    assert stray == [], f"HEX outside themeAuthority-backed facade: {stray}"


def test_qml_components_prefer_semantic_theme_tokens():
    source = workbench_qml.QML_SOURCE
    theme = _extract_theme_block(source)
    outside = source.replace(theme, "", 1)
    for legacy in (
        'property color panel: "#',
        'property color accent: "#',
        'property color selectedRow: "#',
        'color: "#000000"',
        'color: "#0c0d0e"',
        'color: "#b1122b"',
        'color: "#8f0e24"',
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
        "theme.focusRing",
    ):
        assert needle in outside, f"missing semantic usage: {needle}"


def test_named_color_hardcodes_are_only_documented_exceptions():
    source = workbench_qml.QML_SOURCE
    theme = _extract_theme_block(source)
    outside = source.replace(theme, "", 1)
    found = {m.group(1).lower() for m in _NAMED_COLOR_RE.finditer(outside)}
    unexpected = sorted(found - NAMED_COLOR_EXCEPTIONS)
    assert unexpected == [], f"undocumented named color hardcodes: {unexpected}"


def test_functional_accent_default_is_blood_a_from_theme_core():
    blood = theme_core.resolve_theme("Blood")
    mapped = theme_core.theme_tokens_to_qml_semantics(blood)
    assert blood.accent.lower() == theme_core.BLOOD_A_ACCENT
    assert mapped["actionActive"].lower() == theme_core.BLOOD_A_ACCENT
    assert mapped["focusRing"].lower() == theme_core.BLOOD_A_ACCENT
    assert mapped["selectionBorder"].lower() == theme_core.BLOOD_A_ACCENT
    assert mapped["waveformActive"].lower() == theme_core.BLOOD_A_ACCENT
    # Legacy brighter hardcoded accent must not remain QML truth.
    assert '"#b1122b"' not in workbench_qml.QML_SOURCE
    source = workbench_qml.QML_SOURCE.casefold()
    for banned in ("#ff4500", "#00bfff", "#1e90ff", "#00ffff", "#ff00ff"):
        assert banned not in source


def test_theme_authority_is_single_runtime_color_owner():
    from pathlib import Path

    assert "themeAuthority" in _extract_theme_block(workbench_qml.QML_SOURCE)
    module = Path(workbench_qml.__file__).read_text(encoding="utf-8")
    assert "_qml_theme_authority_bridge" in module
    assert 'setContextProperty("themeAuthority"' in module
