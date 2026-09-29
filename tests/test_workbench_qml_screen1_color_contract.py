"""Screen-1 canonical color contract: primitives → semantic tokens → no stray HEX."""

from __future__ import annotations

import re

from src import workbench_qml

# Canonical primitive HEX values (lowercase). Keep in sync with docs + theme block.
CANONICAL_PRIMITIVES: frozenset[str] = frozenset(
    {
        "#000000",  # neutral000
        "#050506",  # neutral050
        "#0a0b0c",  # neutral075
        "#0c0d0e",  # neutral100
        "#141516",  # neutral150
        "#222426",  # neutral250
        "#eceef1",  # contentPrimary
        "#8b9098",  # contentSecondary / contentDisabled
        "#ffffff",  # contentOnAction
        "#6d737c",  # waveformNeutral
        "#b1122b",  # accentPrimary
        "#1a1012",  # accentSurface
    }
)

# Named QML colors allowed outside the theme primitive block.
NAMED_COLOR_EXCEPTIONS: frozenset[str] = frozenset({"transparent"})

REQUIRED_PRIMITIVE_NAMES: tuple[str, ...] = (
    "neutral000",
    "neutral050",
    "neutral075",
    "neutral100",
    "neutral150",
    "neutral250",
    "contentPrimary",
    "contentSecondary",
    "contentDisabled",
    "contentOnAction",
    "waveformNeutral",
    "accentPrimary",
    "accentSurface",
)

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
)

# Only quoted QML color literals; avoids matching issue refs like #692 in comments.
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
    if len(raw) == 9:  # #aarrggbb → compare rgb only for allowlist membership
        return "#" + raw[3:]
    return raw


def test_theme_defines_required_primitives_and_semantic_tokens():
    source = workbench_qml.QML_SOURCE
    theme = _extract_theme_block(source)
    for name in REQUIRED_PRIMITIVE_NAMES:
        assert re.search(
            rf"readonly property color {name}:\s*\"#[0-9a-fA-F]{{6}}\"",
            theme,
        ), f"missing primitive {name}"
    for name in REQUIRED_SEMANTIC_NAMES:
        assert re.search(
            rf"readonly property color {name}:\s*[a-zA-Z][a-zA-Z0-9]*",
            theme,
        ), f"missing semantic token {name}"
        # Semantic tokens must reference primitives/tokens, not raw HEX.
        assert not re.search(
            rf"readonly property color {name}:\s*\"#",
            theme,
        ), f"semantic token {name} must not hardcode HEX"


def test_theme_primitives_match_canonical_hex_set():
    theme = _extract_theme_block(workbench_qml.QML_SOURCE)
    # Only lines that assign HEX literals are primitives.
    primitive_hex = {
        _normalize_hex(m.group(1))
        for m in re.finditer(
            r'readonly property color \w+:\s*"(#[0-9a-fA-F]{3,8})"',
            theme,
        )
    }
    assert primitive_hex == CANONICAL_PRIMITIVES


def test_qml_source_has_no_unknown_or_stray_hex_hardcodes():
    source = workbench_qml.QML_SOURCE
    theme = _extract_theme_block(source)
    all_hex = {_normalize_hex(h) for h in _hex_values(source)}
    unknown = sorted(all_hex - CANONICAL_PRIMITIVES)
    assert unknown == [], f"unknown Screen-1 HEX hardcodes: {unknown}"

    outside = source.replace(theme, "", 1)
    stray = sorted({_normalize_hex(h) for h in _hex_values(outside)})
    assert stray == [], f"HEX outside theme primitive block: {stray}"


def test_qml_components_prefer_semantic_theme_tokens():
    source = workbench_qml.QML_SOURCE
    theme = _extract_theme_block(source)
    outside = source.replace(theme, "", 1)
    # Components should not reintroduce the old flat HEX property literals.
    for legacy in (
        'property color panel: "#',
        'property color accent: "#',
        'property color selectedRow: "#',
        'color: "#000000"',
        'color: "#0c0d0e"',
        'color: "#b1122b"',
    ):
        assert legacy not in outside

    # Spot-check key semantic bindings exist in component tree.
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
    ):
        assert needle in outside, f"missing semantic usage: {needle}"


def test_named_color_hardcodes_are_only_documented_exceptions():
    source = workbench_qml.QML_SOURCE
    theme = _extract_theme_block(source)
    outside = source.replace(theme, "", 1)
    found = {m.group(1).lower() for m in _NAMED_COLOR_RE.finditer(outside)}
    # "white" must go through theme.textOnAction; only transparent is allowed.
    unexpected = sorted(found - NAMED_COLOR_EXCEPTIONS)
    assert unexpected == [], f"undocumented named color hardcodes: {unexpected}"


def test_functional_accent_remains_single_blood_red():
    theme = _extract_theme_block(workbench_qml.QML_SOURCE)
    assert 'accentPrimary: "#b1122b"' in theme
    assert 'actionActive: accentPrimary' in theme
    assert 'waveformActive: accentPrimary' in theme
    assert 'selectionBorder: accentPrimary' in theme
    # No second decorative red / orange / blue brand accents in Screen-1 QML.
    source = workbench_qml.QML_SOURCE.casefold()
    for banned in ("#ff4500", "#00bfff", "#1e90ff", "#00ffff", "#ff00ff"):
        assert banned not in source


def test_canonical_primitive_list_is_small_and_documented():
    # Guard against palette sprawl in the contract itself.
    assert len(CANONICAL_PRIMITIVES) <= 14
    assert "#b1122b" in CANONICAL_PRIMITIVES
    assert "#1a1012" in CANONICAL_PRIMITIVES
    # neutrals without consumers must not sneak into the allowlist.
    assert "#1a1b1d" not in CANONICAL_PRIMITIVES  # unused neutral200
