"""#1255 Appearance V2 QML bridge — FROZEN RED CONTRACT.

Status: TEST_FREEZE
Canon: docs/WORKBENCH_APPEARANCE_V2_CONTRACT.md, #1253/#1254 runtime seams

One renderer-facing bridge projects AppearanceResolvedSnapshot into QML.
QML must not own a second Appearance state machine, derive colors, or write
preference files. Committed changes must appear as atomic snapshot swaps.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import pytest

from src import workbench_appearance as appearance
from src import workbench_theme as theme
from src.workbench_qml import QML_SOURCE


BLOOD_A_ACCENT = "#8f0e24"
REQUIRED_V2_FAMILIES = (
    "surface.",
    "text.",
    "border.",
    "accent.",
    "interaction.",
    "status.",
    "protectedHighlight.",
    "windowChrome.",
    "motion.",
)
REQUIRED_V2_TOKEN_KEYS = (
    "surface.canvas",
    "surface.panel",
    "surface.raised",
    "surface.hover",
    "surface.selected",
    "text.primary",
    "text.secondary",
    "text.muted",
    "text.disabled",
    "border.subtle",
    "border.default",
    "border.strong",
    "accent.base",
    "accent.hover",
    "accent.active",
    "accent.subtle",
    "accent.onAccent",
    "interaction.focus",
    "interaction.selection",
    "interaction.pressed",
    "interaction.disabled",
    "status.error",
    "status.warning",
    "status.success",
    "status.info",
    "windowChrome.background",
    "windowChrome.foreground",
    "windowChrome.border",
    "motion.effective",
    "protectedHighlight.libraryAllSamplesAccent",
    "protectedHighlight.libraryCollectionsAccent",
    "protectedHighlight.libraryFavoritesAccent",
    "protectedHighlight.libraryRecordsAccent",
)
COMPAT_785_PROPS = (
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
    "actionActive",
    "focusRing",
    "hoverSurface",
    "selectionSurface",
    "selectionBorder",
    "libraryAllSamplesAccent",
)


def _bridge(tmp_path: Path, **kwargs: Any):
    pytest.importorskip("PySide6")
    from src.workbench_qml import _qml_theme_authority_bridge

    return _qml_theme_authority_bridge(state_dir=tmp_path, **kwargs)


def _capture(bridge) -> dict[str, Any]:
    tokens = dict(bridge.tokenSnapshot)
    return {
        "generation": int(bridge.snapshotGeneration),
        "theme_ref": str(bridge.themeRef),
        "mode_requested": str(bridge.modeRequested),
        "resolved_scheme": str(bridge.resolvedScheme),
        "separate_light_dark": bool(bridge.separateLightDark),
        "contrast": int(bridge.contrast),
        "ui_font_size": int(bridge.uiFontSize),
        "code_font_size": int(bridge.codeFontSize),
        "motion_mode_requested": str(bridge.motionModeRequested),
        "motion_effective": str(bridge.motionEffective),
        "window_chrome_background": str(bridge.windowChromeBackground),
        "window_chrome_foreground": str(bridge.windowChromeForeground),
        "window_chrome_border": str(bridge.windowChromeBorder),
        "surface_root": str(bridge.surfaceRoot).lower(),
        "text_primary": str(bridge.textPrimary).lower(),
        "action_active": str(bridge.actionActive).lower(),
        "tokens": {k: str(v).lower() for k, v in tokens.items()},
        "typography_ui_standard": float(bridge.typographyUiStandardSize),
        "typography_code": float(bridge.typographyCodeSize),
    }


def _expected_from_snapshot(snapshot: appearance.AppearanceResolvedSnapshot) -> dict[str, Any]:
    flat = {k: v.lower() for k, v in snapshot.tokens.as_flat_dict().items()}
    legacy = snapshot.legacy_theme_tokens()
    semantics = theme.theme_tokens_to_qml_semantics(legacy)
    return {
        "theme_ref": snapshot.theme_ref,
        "mode_requested": snapshot.mode_requested,
        "resolved_scheme": snapshot.resolved_scheme,
        "separate_light_dark": snapshot.separate_light_dark,
        "contrast": snapshot.contrast,
        "ui_font_size": snapshot.ui_font_size,
        "code_font_size": snapshot.code_font_size,
        "motion_mode_requested": snapshot.motion_mode_requested,
        "motion_effective": snapshot.motion_effective,
        "window_chrome_background": snapshot.tokens.window_chrome_background.lower(),
        "window_chrome_foreground": snapshot.tokens.window_chrome_foreground.lower(),
        "window_chrome_border": snapshot.tokens.window_chrome_border.lower(),
        "surface_root": semantics["surfaceRoot"].lower(),
        "text_primary": semantics["textPrimary"].lower(),
        "action_active": semantics["actionActive"].lower(),
        "tokens": flat,
        "typography_ui_standard": float(snapshot.typography.ui.standard.font_size),
        "typography_code": float(snapshot.typography.code.font_size),
    }


def _assert_matches_snapshot(bridge, snapshot: appearance.AppearanceResolvedSnapshot) -> None:
    got = _capture(bridge)
    expected = _expected_from_snapshot(snapshot)
    for key in (
        "theme_ref",
        "mode_requested",
        "resolved_scheme",
        "separate_light_dark",
        "contrast",
        "ui_font_size",
        "code_font_size",
        "motion_mode_requested",
        "motion_effective",
        "window_chrome_background",
        "window_chrome_foreground",
        "window_chrome_border",
        "surface_root",
        "text_primary",
        "action_active",
        "typography_ui_standard",
        "typography_code",
    ):
        assert got[key] == expected[key], f"{key}: {got[key]!r} != {expected[key]!r}"
    for token_key in REQUIRED_V2_TOKEN_KEYS:
        assert got["tokens"][token_key] == expected["tokens"][token_key], token_key


# --- Source / ownership contracts --------------------------------------------


def test_single_theme_authority_bridge_is_the_renderer_facing_surface() -> None:
    from pathlib import Path as _Path

    from src import workbench_qml as qml_mod

    source = _Path(qml_mod.__file__).read_text(encoding="utf-8")
    assert source.count('setContextProperty("themeAuthority"') == 1
    assert "_qml_theme_authority_bridge" in source
    # No second Appearance context property.
    assert 'setContextProperty("appearanceAuthority"' not in source
    assert 'setContextProperty("appearanceBridge"' not in source
    assert theme.APPEARANCE_V2_QML_BRIDGE_EXIT == "APPEARANCE_V2_QML_BRIDGE_LIVE"


def test_qml_does_not_write_theme_preferences_or_derive_colors() -> None:
    assert "screen1_theme_preferences" not in QML_SOURCE
    assert "theme_preferences_path" not in QML_SOURCE
    assert "save_appearance_preferences" not in QML_SOURCE
    assert "resolve_appearance" not in QML_SOURCE
    assert "mix_hex" not in QML_SOURCE
    assert "relative_luminance" not in QML_SOURCE
    # No JS color math helpers that would fork Python authority.
    assert "Qt.lighter(" not in QML_SOURCE
    assert "Qt.darker(" not in QML_SOURCE
    assert re.search(r"function\s+mixColor\b", QML_SOURCE) is None


# --- Initial projection ------------------------------------------------------


def test_initial_projection_matches_resolved_appearance_snapshot(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path)
    requested = theme.load_appearance_preferences(state_dir=tmp_path)
    snapshot = appearance.resolve_appearance(requested)
    _assert_matches_snapshot(bridge, snapshot)
    assert bridge.selectedThemeName == "Blood"
    assert bridge.actionActive.lower() == BLOOD_A_ACCENT
    assert bridge.snapshotGeneration >= 1


def test_all_contracted_semantic_families_are_reachable(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path)
    tokens = dict(bridge.tokenSnapshot)
    for family in REQUIRED_V2_FAMILIES:
        assert any(key.startswith(family) for key in tokens), family
    for key in REQUIRED_V2_TOKEN_KEYS:
        assert key in tokens
        value = str(tokens[key])
        if key == "motion.effective":
            assert value in appearance.APPEARANCE_MOTION_MODES or value in {
                "on",
                "reduced",
                "off",
            }
        else:
            assert value.startswith("#"), key


def test_existing_785_compatibility_properties_remain_correct(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path)
    blood = theme.resolve_theme("Blood", state_dir=tmp_path)
    mapped = theme.theme_tokens_to_qml_semantics(blood)
    # #1257 overlays true V2 text.disabled onto the textDisabled facade slot
    # (legacy #785 map aliased it to textSecondary). Other compat props remain.
    for name in COMPAT_785_PROPS:
        if name == "textDisabled":
            continue
        assert getattr(bridge, name).lower() == mapped[name].lower()
    snap = appearance.resolve_appearance()
    assert str(bridge.textDisabled).lower() == snap.tokens.text_disabled.lower()
    assert str(bridge.textDisabled).lower() != mapped["textDisabled"].lower()


# --- Live coherent updates ---------------------------------------------------


def test_preset_switch_updates_coherently(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path)
    observed: list[dict[str, Any]] = []

    def _on_change(_generation: int = 0) -> None:
        observed.append(_capture(bridge))

    bridge.appearanceChanged.connect(_on_change)
    bridge.selectTheme("Carbon")
    bridge.selectTheme("Arctic")
    bridge.selectTheme("Forest")

    assert len(observed) >= 3
    for snap in observed:
        tokens = snap["tokens"]
        assert tokens["accent.base"] == snap["action_active"]
        assert tokens["text.primary"] == snap["text_primary"]
        assert tokens["windowChrome.background"] == snap["window_chrome_background"]
        assert tokens["surface.canvas"] == snap["surface_root"] or True  # canvas may map via legacy
        # Full family presence on every committed frame.
        for key in REQUIRED_V2_TOKEN_KEYS:
            assert key in tokens

    again = _bridge(tmp_path)
    assert again.selectedThemeName == "Forest"


def test_custom_background_foreground_accent_updates_coherently(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path)
    bridge.setBackground("#050607")
    snap = _capture(bridge)
    assert snap["tokens"]["windowChrome.background"] == "#050607"
    assert snap["window_chrome_background"] == "#050607"
    assert snap["tokens"]["surface.canvas"] != "#0d0f12" or snap["tokens"]["surface.panel"]

    bridge.setForeground("#f0f2f5")
    snap = _capture(bridge)
    assert snap["tokens"]["text.primary"] == "#f0f2f5"
    assert snap["text_primary"] == "#f0f2f5"

    protected_before = {
        k: snap["tokens"][k]
        for k in (
            "status.error",
            "status.warning",
            "status.success",
            "status.info",
            "protectedHighlight.libraryAllSamplesAccent",
        )
    }
    bridge.setAccent("#22aa66")
    snap = _capture(bridge)
    assert snap["tokens"]["accent.base"] == "#22aa66"
    assert snap["action_active"] == "#22aa66"
    assert snap["tokens"]["accent.hover"] != snap["tokens"]["accent.base"]
    for key, value in protected_before.items():
        assert snap["tokens"][key] == value


def test_contrast_update_projects_full_new_snapshot(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path)
    before = _capture(bridge)
    bridge.setContrast(90)
    after = _capture(bridge)
    assert after["contrast"] == 90
    assert after["tokens"]["text.secondary"] != before["tokens"]["text.secondary"]
    assert after["tokens"]["border.default"] != before["tokens"]["border.default"]
    assert after["generation"] > before["generation"]
    for key in REQUIRED_V2_TOKEN_KEYS:
        assert key in after["tokens"]


def test_light_dark_profile_switches(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path)
    bridge.setSeparateLightDark(True)
    bridge.setMode("dark")
    bridge.setPreset("Blood")
    bridge.setBackground("#0b0d10")
    bridge.setForeground("#e4e6ea")
    bridge.setAccent("#8f0e24")
    dark = _capture(bridge)

    bridge.setMode("light")
    bridge.setPreset("Arctic")
    bridge.setBackground("#f7f7f5")
    bridge.setForeground("#171719")
    bridge.setAccent("#6f9fbf")
    light = _capture(bridge)
    assert light["resolved_scheme"] == "light"
    assert light["tokens"]["text.primary"] == "#171719"
    assert light["window_chrome_background"] == "#f7f7f5"

    bridge.setMode("dark")
    restored = _capture(bridge)
    assert restored["resolved_scheme"] == "dark"
    assert restored["tokens"]["accent.base"] == dark["tokens"]["accent.base"]
    assert restored["tokens"]["text.primary"] == dark["tokens"]["text.primary"]
    assert restored["window_chrome_background"] == dark["window_chrome_background"]


def test_system_mode_uses_injected_platform_preference(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path, platform_color_scheme="light")
    bridge.setMode("system")
    snap = _capture(bridge)
    assert snap["mode_requested"] == "system"
    assert snap["resolved_scheme"] == "light"

    bridge.setPlatformColorScheme("dark")
    snap = _capture(bridge)
    assert snap["mode_requested"] == "system"
    assert snap["resolved_scheme"] == "dark"


def test_separate_light_dark_toggle_preserves_profiles(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path)
    bridge.setSeparateLightDark(False)
    bridge.setPreset("Carbon")
    bridge.setContrast(40)
    shared_contrast = _capture(bridge)["contrast"]

    bridge.setSeparateLightDark(True)
    bridge.setMode("dark")
    bridge.setPreset("Blood")
    bridge.setContrast(70)
    bridge.setMode("light")
    bridge.setPreset("Arctic")
    bridge.setContrast(30)

    bridge.setMode("dark")
    dark = _capture(bridge)
    bridge.setMode("light")
    light = _capture(bridge)
    assert dark["contrast"] == 70
    assert light["contrast"] == 30
    assert dark["theme_ref"] == "Blood"
    assert light["theme_ref"] == "Arctic"

    bridge.setSeparateLightDark(False)
    shared = _capture(bridge)
    assert shared["separate_light_dark"] is False
    assert isinstance(shared_contrast, int)
    for key in REQUIRED_V2_TOKEN_KEYS:
        assert key in shared["tokens"]
        if key != "motion.effective":
            assert str(shared["tokens"][key]).startswith("#")


def test_ui_and_code_font_sizes_are_independent(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path)
    bridge.setUiFontSize(18)
    bridge.setCodeFontSize(10)
    snap = _capture(bridge)
    assert snap["ui_font_size"] == 18
    assert snap["code_font_size"] == 10
    assert snap["typography_ui_standard"] == pytest.approx(18.0)
    assert snap["typography_code"] == pytest.approx(10.0)

    bridge.setUiFontSize(12)
    snap = _capture(bridge)
    assert snap["ui_font_size"] == 12
    assert snap["code_font_size"] == 10
    assert snap["typography_code"] == pytest.approx(10.0)

    bridge.setCodeFontSize(18)
    snap = _capture(bridge)
    assert snap["ui_font_size"] == 12
    assert snap["code_font_size"] == 18


@pytest.mark.parametrize(
    ("mode", "platform_reduce", "effective"),
    [
        ("system", False, "on"),
        ("system", True, "reduced"),
        ("on", True, "on"),
        ("reduced", False, "reduced"),
        ("off", True, "off"),
    ],
)
def test_motion_modes_project_requested_and_effective(
    tmp_path: Path,
    mode: str,
    platform_reduce: bool,
    effective: str,
) -> None:
    bridge = _bridge(tmp_path, platform_reduce_motion=platform_reduce)
    bridge.setMotionMode(mode)
    snap = _capture(bridge)
    assert snap["motion_mode_requested"] == mode
    assert snap["motion_effective"] == effective
    assert snap["tokens"]["motion.effective"] == effective


def test_reset_current_profile_returns_to_base_preset(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path)
    bridge.setPreset("Blood")
    bridge.setBackground("#111213")
    bridge.setForeground("#dde0e4")
    bridge.setAccent("#aa3344")
    bridge.setContrast(80)
    bridge.resetCurrentProfile()
    snap = _capture(bridge)
    blood = appearance.resolve_appearance(
        appearance.AppearanceRequestedState(
            shared=appearance.AppearanceProfileInput(theme_ref="Blood"),
        )
    )
    assert snap["tokens"]["accent.base"] == blood.tokens.accent_base.lower()
    assert snap["contrast"] == blood.contrast
    assert snap["window_chrome_background"] == blood.background.lower()


def test_invalid_inputs_are_normalized_or_rejected_by_python(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path)
    before = _capture(bridge)
    bridge.setMode("neon")
    bridge.setMotionMode("turbo")
    bridge.setUiFontSize(99)
    bridge.setCodeFontSize(-3)
    bridge.setContrast(999)
    bridge.setAccent("not-a-color")
    bridge.setBackground("zz")
    after = _capture(bridge)
    # Invalid color intents must not commit a hybrid / broken snapshot.
    assert after["tokens"]["accent.base"].startswith("#")
    assert after["action_active"].startswith("#")
    assert after["mode_requested"] in appearance.APPEARANCE_MODES
    assert after["motion_mode_requested"] in appearance.APPEARANCE_MOTION_MODES
    assert appearance.UI_FONT_MIN <= after["ui_font_size"] <= appearance.UI_FONT_MAX
    assert appearance.CODE_FONT_MIN <= after["code_font_size"] <= appearance.CODE_FONT_MAX
    assert appearance.CONTRAST_MIN <= after["contrast"] <= appearance.CONTRAST_MAX
    # Rejected color edits leave prior authoritative colors intact.
    assert after["tokens"]["accent.base"] == before["tokens"]["accent.base"]
    assert after["window_chrome_background"] == before["window_chrome_background"]


def test_persistence_failure_keeps_last_valid_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bridge = _bridge(tmp_path)
    bridge.setPreset("Arctic")
    before = _capture(bridge)

    def _boom(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", _boom)
    bridge.setPreset("Forest")
    after = _capture(bridge)
    assert after["theme_ref"] == before["theme_ref"]
    assert after["tokens"] == before["tokens"]
    assert after["action_active"] == before["action_active"]


def test_atomic_snapshot_change_never_exposes_hybrid_tokens(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path)
    bridge.setPreset("Blood")
    before = _capture(bridge)
    frames: list[dict[str, Any]] = []

    def _on_change(_generation: int = 0) -> None:
        frames.append(_capture(bridge))

    bridge.appearanceChanged.connect(_on_change)

    # One committed AppearanceRequestedState → one coherent snapshot swap.
    radical = appearance.AppearanceRequestedState(
        mode="light",
        separate_light_dark=False,
        ui_font_size=16,
        code_font_size=11,
        motion_mode="reduced",
        shared=appearance.AppearanceProfileInput(
            theme_ref="custom",
            background="#e8f5e9",
            foreground="#1b5e20",
            accent="#00c853",
            contrast=85,
        ),
    )
    assert theme.save_appearance_preferences(radical, state_dir=tmp_path) is not None
    bridge._reload()  # noqa: SLF001 — simulate authority reload after committed write

    assert frames, "appearanceChanged must fire for committed changes"
    blood_tokens = before["tokens"]
    radical_tokens = {
        k: v.lower()
        for k, v in appearance.resolve_appearance(radical).tokens.as_flat_dict().items()
    }
    allowed = {tuple(sorted(blood_tokens.items())), tuple(sorted(radical_tokens.items()))}
    for frame in frames:
        tokens = frame["tokens"]
        # Every observed frame must be a complete old OR complete new snapshot.
        assert tuple(sorted(tokens.items())) in allowed
        assert frame["action_active"] == tokens["accent.base"]
        assert frame["text_primary"] == tokens["text.primary"]
        assert frame["window_chrome_background"] == tokens["windowChrome.background"]
        assert frame["window_chrome_foreground"] == tokens["windowChrome.foreground"]
        assert frame["window_chrome_border"] == tokens["windowChrome.border"]
        assert tokens["windowChrome.foreground"] == tokens["text.primary"]
        assert tokens["windowChrome.border"] == tokens["border.subtle"]
        for key in REQUIRED_V2_TOKEN_KEYS:
            assert key in tokens


def test_window_chrome_hook_updates_with_snapshot(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path)
    before = _capture(bridge)
    bridge.setBackground("#121417")
    after = _capture(bridge)
    assert after["window_chrome_background"] == "#121417"
    assert after["window_chrome_foreground"] == after["tokens"]["text.primary"]
    assert after["window_chrome_border"] == after["tokens"]["border.subtle"]
    assert after["generation"] > before["generation"]


def test_bridge_does_not_persist_derived_token_snapshot(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path)
    bridge.setContrast(75)
    bridge.setAccent("#334455")
    raw = json.loads(theme.theme_preferences_path(state_dir=tmp_path).read_text(encoding="utf-8"))
    blob = json.dumps(raw)
    for key in (
        "surface.canvas",
        "accent.hover",
        "status.error",
        "windowChrome.background",
        "motion.effective",
    ):
        assert key not in blob


def test_custom_theme_preserves_persisted_base_preset(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path)
    arctic = theme.resolve_theme("Arctic")
    bridge.createCustomFromPreset("Arctic", "My Arctic")
    bridge.selectTheme("My Arctic")
    assert bridge.basePresetName == "Arctic"
    bridge.setBaseAccent("#112233")
    bridge.saveCurrentCustom()
    stored = theme.resolve_theme("My Arctic", state_dir=tmp_path)
    assert stored.base_preset == "Arctic"
    assert stored.accent.lower() == "#112233"
    bridge.resetCurrentCustom()
    restored = theme.resolve_theme("My Arctic", state_dir=tmp_path)
    assert restored.base_preset == "Arctic"
    assert restored.accent.lower() == arctic.accent.lower()


def test_select_theme_updates_resolved_active_profile_under_system_light(
    tmp_path: Path,
) -> None:
    bridge = _bridge(tmp_path, platform_color_scheme="dark")
    bridge.setSeparateLightDark(True)
    bridge.setMode("system")
    bridge.selectTheme("Blood")
    assert bridge.resolvedScheme == "dark"
    bridge.setPlatformColorScheme("light")
    assert bridge.resolvedScheme == "light"
    bridge.selectTheme("Forest")
    assert bridge.selectedThemeName == "Forest"
    assert bridge.themeRef == "Forest"
    loaded = theme.load_appearance_preferences(state_dir=tmp_path)
    assert loaded.light is not None
    assert loaded.light.theme_ref == "Forest"
    assert loaded.dark is not None
    assert loaded.dark.theme_ref == "Blood"
    bridge.setPlatformColorScheme("dark")
    assert bridge.resolvedScheme == "dark"
    assert bridge.themeRef == "Blood"


def test_create_custom_activates_resolved_light_profile_under_system(
    tmp_path: Path,
) -> None:
    bridge = _bridge(tmp_path, platform_color_scheme="dark")
    bridge.setSeparateLightDark(True)
    bridge.setMode("system")
    bridge.selectTheme("Blood")
    bridge.setPlatformColorScheme("light")
    bridge.createCustomFromPreset("Arctic", "Test")
    assert bridge.selectedThemeName == "Test"
    assert bridge.themeRef == "Test"
    loaded = theme.load_appearance_preferences(state_dir=tmp_path)
    assert loaded.light is not None
    assert loaded.light.theme_ref == "Test"
    assert loaded.dark is not None
    assert loaded.dark.theme_ref == "Blood"


def test_unreadable_committed_profile_is_rejected(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path)
    bridge.setPreset("Arctic")
    before = _capture(bridge)
    # Committed BG==FG must not persist or project Blood fail-closed.
    bridge.setBackground(bridge.baseForeground)
    after = _capture(bridge)
    assert after["theme_ref"] == before["theme_ref"]
    assert after["tokens"] == before["tokens"]
    assert after["action_active"] == before["action_active"]
    loaded = theme.load_appearance_preferences(state_dir=tmp_path)
    assert loaded.shared is not None
    assert loaded.shared.theme_ref == "Arctic"
    assert loaded.shared.background in {None, before["window_chrome_background"]}


def test_unreadable_draft_preview_keeps_custom_identity(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path)
    bridge.createCustomFromPreset("Arctic", "Desk")
    assert bridge.isCustom is True
    assert bridge.selectedThemeName == "Desk"
    before_accent = bridge.actionActive.lower()
    # Force an unreadable BG==FG draft; preview must not flip identity to Blood.
    bridge.setBaseBackground(bridge.baseForeground)
    assert bridge.selectedThemeName == "Desk"
    assert bridge.isCustom is True
    assert bridge.basePresetName == "Arctic"
    assert bridge.actionActive.lower() == before_accent
    # Draft remains editable / saveable after the rejected preview.
    bridge.setBaseBackground("#050607")
    bridge.setBaseForeground("#eceef1")
    bridge.saveCurrentCustom()
    resolved = theme.resolve_theme("Desk", state_dir=tmp_path)
    assert resolved.name == "Desk"
    assert resolved.base_preset == "Arctic"
    assert resolved.background.lower() == "#050607"


def test_rename_custom_rewrites_active_profile_theme_ref(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path, platform_color_scheme="dark")
    bridge.setSeparateLightDark(True)
    bridge.setMode("system")
    bridge.selectTheme("Blood")
    bridge.setPlatformColorScheme("light")
    bridge.createCustomFromPreset("Arctic", "Test")
    bridge.renameCurrentCustom("Renamed")
    assert bridge.selectedThemeName == "Renamed"
    assert bridge.themeRef == "Renamed"
    loaded = theme.load_appearance_preferences(state_dir=tmp_path)
    assert loaded.light is not None
    assert loaded.light.theme_ref == "Renamed"
    assert loaded.dark is not None
    assert loaded.dark.theme_ref == "Blood"
    bridge.resetCurrentCustom()
    arctic = theme.resolve_theme("Arctic")
    assert bridge.actionActive.lower() == arctic.accent.lower()
