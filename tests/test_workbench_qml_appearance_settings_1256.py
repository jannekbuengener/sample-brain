"""#1256 Appearance Settings UI — V2 controls on themeAuthority (test-first).

Settings controls must bind to themeAuthority intents only. No QML persistence
or color derivation. Closed children #1252–#1255/#1257 must not be reopened.
"""

from __future__ import annotations

from pathlib import Path

from src.workbench_qml import QML_SOURCE


def _prefs_popover() -> str:
    start = QML_SOURCE.index('objectName: "displayPreferencesPopover"')
    end = QML_SOURCE.index("workspaceRow", start)
    return QML_SOURCE[start:end]


def test_appearance_mode_control_wires_theme_authority_set_mode() -> None:
    prefs = _prefs_popover()
    assert 'objectName: "appearanceModeSelector"' in prefs
    assert "themeAuthority.setMode" in prefs
    assert "themeAuthority.modeRequested" in prefs
    for mode in ("system", "light", "dark"):
        assert mode in prefs


def test_appearance_contrast_control_wires_theme_authority_set_contrast() -> None:
    prefs = _prefs_popover()
    assert 'objectName: "appearanceContrastControl"' in prefs
    assert "themeAuthority.setContrast" in prefs
    assert "themeAuthority.contrast" in prefs


def test_appearance_font_controls_wire_theme_authority() -> None:
    prefs = _prefs_popover()
    assert 'objectName: "appearanceUiFontSpin"' in prefs
    assert 'objectName: "appearanceCodeFontSpin"' in prefs
    assert "themeAuthority.setUiFontSize" in prefs
    assert "themeAuthority.setCodeFontSize" in prefs
    assert "themeAuthority.uiFontSize" in prefs
    assert "themeAuthority.codeFontSize" in prefs


def test_appearance_motion_control_uses_theme_authority_four_way() -> None:
    prefs = _prefs_popover()
    assert 'objectName: "appearanceMotionSelector"' in prefs
    assert "themeAuthority.setMotionMode" in prefs
    assert "themeAuthority.motionModeRequested" in prefs
    for mode in ("system", "on", "reduced", "off"):
        assert mode in prefs
    motion_block_start = prefs.index('objectName: "appearanceMotionSelector"')
    motion_window = prefs[motion_block_start : motion_block_start + 600]
    assert "setWaveformMotionMode" not in motion_window


def test_appearance_separate_light_dark_toggle_wires_theme_authority() -> None:
    prefs = _prefs_popover()
    assert 'objectName: "appearanceSeparateLightDarkSwitch"' in prefs
    assert "themeAuthority.setSeparateLightDark" in prefs
    assert "themeAuthority.separateLightDark" in prefs


def test_appearance_settings_ui_has_no_local_persistence_or_derivation() -> None:
    prefs = _prefs_popover()
    forbidden = (
        "screen1_theme_preferences",
        "save_appearance_preferences",
        "load_appearance_preferences",
        "resolve_appearance",
        "Qt.rgba(",
        "Qt.darker(",
        "Qt.lighter(",
    )
    for token in forbidden:
        assert token not in prefs, f"settings UI must not contain {token}"


def test_mode_contrast_slice_does_not_claim_full_1256_exit_in_product_code() -> None:
    """Marker is reserved for full #1256 close-out, not intermediate slices."""
    qml = Path(__file__).resolve().parents[1] / "src" / "workbench_qml.py"
    body = qml.read_text(encoding="utf-8")
    assert "APPEARANCE_SETTINGS_V2_WORKING" not in body
