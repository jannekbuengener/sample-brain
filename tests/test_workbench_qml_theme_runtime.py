"""#785 Screen-1 QML Theme Authority runtime — FROZEN RED CONTRACT.

Status: TEST_FREEZE
Canon: docs/assets/themes/presets.v1.json, src/workbench_theme.py

Theme Core (#796) is the sole color authority. QML consumes semantic tokens via
a single themeAuthority bridge; components must not keep a second hardcoded
palette as truth. Display Preferences hosts Appearance without a second
settings persistence store (theme prefs stay in workbench_theme store).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src import workbench_theme as theme
from src.workbench_qml import QML_SOURCE


BLOOD_A_ACCENT = "#8f0e24"
REQUIRED_QML_SEMANTICS = (
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


def _extract_theme_block(source: str) -> str:
    marker = "QtObject {\n        id: theme"
    start = source.find(marker)
    assert start >= 0, "theme QtObject with id: theme is required"
    i = source.find("{", start)
    depth = 0
    for j in range(i, len(source)):
        if source[j] == "{":
            depth += 1
        elif source[j] == "}":
            depth -= 1
            if depth == 0:
                return source[start : j + 1]
    raise AssertionError("unclosed theme QtObject")


def _prefs_popover() -> str:
    start = QML_SOURCE.index('objectName: "displayPreferencesPopover"')
    end = QML_SOURCE.index("workspaceRow", start)
    return QML_SOURCE[start:end]


# --- Source contract ---------------------------------------------------------


def test_qml_theme_facade_binds_only_to_theme_authority() -> None:
    block = _extract_theme_block(QML_SOURCE)
    assert "themeAuthority" in block
    for name in REQUIRED_QML_SEMANTICS:
        assert re.search(
            rf"readonly property color {name}:\s*themeAuthority\.",
            block,
        ), f"semantic {name} must bind themeAuthority"
    # No competing primitive HEX palette inside the theme facade.
    assert not _HEX_RE.search(block), "theme facade must not hardcode HEX"

    outside = QML_SOURCE.replace(block, "", 1)
    stray = sorted({m.group(1).lower() for m in _HEX_RE.finditer(outside)})
    assert stray == [], f"HEX outside themeAuthority-backed facade: {stray}"


def test_qml_wires_theme_authority_context_and_appearance_ui() -> None:
    from pathlib import Path

    from src import workbench_qml as qml_mod

    source = Path(qml_mod.__file__).read_text(encoding="utf-8")
    assert 'setContextProperty("themeAuthority"' in source
    assert "_qml_theme_authority_bridge" in source

    prefs = _prefs_popover()
    assert "Appearance" in prefs
    assert 'objectName: "themePresetSelector"' in prefs
    assert 'objectName: "themeCustomizeButton"' in prefs
    assert "themeAuthority.selectTheme" in prefs


def test_legacy_hardcoded_blood_b_accent_is_not_default_truth() -> None:
    """Old #b1122b primitive palette must not remain Screen-1 color truth."""
    assert '"#b1122b"' not in QML_SOURCE
    assert '"#1a1012"' not in QML_SOURCE
    blood = theme.resolve_theme("Blood")
    assert blood.accent.lower() == BLOOD_A_ACCENT
    mapped = theme.theme_tokens_to_qml_semantics(blood)
    assert mapped["actionActive"].lower() == BLOOD_A_ACCENT


# --- Bridge behaviour --------------------------------------------------------


def test_theme_authority_bridge_defaults_to_blood_a(tmp_path: Path) -> None:
    from src.workbench_qml import _qml_theme_authority_bridge

    bridge = _qml_theme_authority_bridge(state_dir=tmp_path)
    assert bridge.selectedThemeName == "Blood"
    assert bridge.actionActive.lower() == BLOOD_A_ACCENT
    assert bridge.surfaceRoot.lower() == "#050506"
    assert bridge.textPrimary.lower() == "#eceef1"
    assert bridge.focusRing.lower() == BLOOD_A_ACCENT
    assert bridge.textOnAction.lower() == "#ffffff"


def test_theme_authority_bridge_switches_presets_and_persists(tmp_path: Path) -> None:
    from src.workbench_qml import _qml_theme_authority_bridge

    bridge = _qml_theme_authority_bridge(state_dir=tmp_path)
    carbon = theme.resolve_theme("Carbon")
    bridge.selectTheme("Carbon")
    assert bridge.selectedThemeName == "Carbon"
    assert bridge.actionActive.lower() == carbon.accent.lower()
    assert bridge.surfaceRoot.lower() == carbon.background.lower()

    again = _qml_theme_authority_bridge(state_dir=tmp_path)
    assert again.selectedThemeName == "Carbon"
    assert again.actionActive.lower() == carbon.accent.lower()


def test_theme_authority_bridge_custom_lifecycle(tmp_path: Path) -> None:
    from src.workbench_qml import _qml_theme_authority_bridge

    bridge = _qml_theme_authority_bridge(state_dir=tmp_path)
    bridge.createCustomFromPreset("Blood", "My Blood")
    assert "My Blood" in list(bridge.customThemeNames)
    bridge.selectTheme("My Blood")
    bridge.setBaseAccent("#aa1122")
    bridge.setBaseBackground("#050506")
    bridge.setBaseForeground("#eceef1")
    bridge.saveCurrentCustom()
    resolved = theme.resolve_theme("My Blood", state_dir=tmp_path)
    assert resolved.accent.lower() == "#aa1122"

    bridge.renameCurrentCustom("Renamed Blood")
    assert theme.resolve_theme(None, state_dir=tmp_path).name == "Renamed Blood"

    bridge.resetCurrentCustom()
    assert theme.resolve_theme("Renamed Blood", state_dir=tmp_path).accent.lower() == BLOOD_A_ACCENT

    bridge.deleteCurrentCustom()
    assert "Renamed Blood" not in theme.list_custom_themes(state_dir=tmp_path)
    assert theme.resolve_theme(None, state_dir=tmp_path).name == "Blood"


def test_theme_authority_bridge_corrupt_prefs_fail_closed_to_blood_a(tmp_path: Path) -> None:
    from src.workbench_qml import _qml_theme_authority_bridge

    path = theme.theme_preferences_path(state_dir=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json", encoding="utf-8")
    bridge = _qml_theme_authority_bridge(state_dir=tmp_path)
    assert bridge.selectedThemeName == "Blood"
    assert bridge.actionActive.lower() == BLOOD_A_ACCENT


def test_column_resize_contract_survives_theme_wiring() -> None:
    """#792 must not regress while wiring Theme Authority."""
    assert 'browserPane.resizeColumn(' in QML_SOURCE
    assert "theme.dividerDefault" in QML_SOURCE
    assert "#780 Browser column resize" in QML_SOURCE
