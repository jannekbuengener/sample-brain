"""#1256 Appearance Settings UI — V2 controls on themeAuthority (test-first).

Settings controls must bind to themeAuthority intents only. No QML persistence
or color derivation. Closed children #1252–#1255/#1257 must not be reopened.
"""

from __future__ import annotations

from pathlib import Path

import pytest

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
    ui = prefs[prefs.index('objectName: "appearanceUiFontSpin"') :]
    ui = ui[: ui.index("Accessible.name")]
    assert "from: 12" in ui and "to: 18" in ui
    code = prefs[prefs.index('objectName: "appearanceCodeFontSpin"') :]
    code = code[: code.index("Accessible.name")]
    assert "from: 10" in code and "to: 18" in code


def test_appearance_density_is_static_compact_marker_not_a_control() -> None:
    """#696 frozen affordance keeps Density text; no second density selector."""
    prefs = _prefs_popover()
    assert "Density" in prefs
    assert "Compact" in prefs
    assert "densitySelector" not in prefs
    assert "setDensity" not in prefs


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


def test_set_motion_mode_off_syncs_interaction_adapter_playhead_seam(tmp_path: Path) -> None:
    """Appearance Motion Off must update #738 adapter without restart (#1256 B2)."""
    pytest.importorskip("PySide6")
    from src.workbench_qml import (
        Screen1QmlInteractionAdapter,
        Screen1QmlViewModel,
        _qml_theme_authority_bridge,
        _sync_interaction_motion_from_appearance,
    )
    from src.workbench_transport_ui import PreviewPlaybackSnapshot

    bridge = _qml_theme_authority_bridge(state_dir=tmp_path)
    view_model = Screen1QmlViewModel.baseline("screen1-default-3panel")
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        on_preview_requested=lambda *_a, **_k: None,
        on_preview_stopped=lambda: None,
        on_preview_snapshot=lambda: PreviewPlaybackSnapshot(
            playing=True,
            sample_path="C:/samples/kick.wav",
            position_ms=100,
            duration_ms=1000,
            progress=0.1,
            playback_instance_id=1,
        ),
    )
    adapter._preview_active = True  # noqa: SLF001
    adapter.set_waveform_motion_mode("on")
    assert adapter.waveform_motion_mode == "on"

    bridge.appearanceChanged.connect(
        lambda *_args: _sync_interaction_motion_from_appearance(adapter, bridge)
    )
    bridge.setMotionMode("off")
    assert bridge.motionEffective == "off"
    assert adapter.waveform_motion_mode == "off"
    assert adapter.preview_playback_snapshot() == PreviewPlaybackSnapshot.idle()


def test_set_mode_and_contrast_round_trip_via_theme_authority(tmp_path: Path) -> None:
    pytest.importorskip("PySide6")
    from src.workbench_qml import _qml_theme_authority_bridge

    bridge = _qml_theme_authority_bridge(state_dir=tmp_path)
    bridge.setMode("light")
    bridge.setContrast(42)
    assert bridge.modeRequested == "light"
    assert bridge.contrast == 42
    bridge.setSeparateLightDark(True)
    bridge.setUiFontSize(14)
    bridge.setCodeFontSize(12)
    assert bridge.separateLightDark is True
    assert bridge.uiFontSize == 14
    assert bridge.codeFontSize == 12
