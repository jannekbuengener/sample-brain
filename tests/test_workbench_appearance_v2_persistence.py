"""#1254 Appearance V2 preference persistence + v1 migration — FROZEN CONTRACT.

Status: TEST_FREEZE
Canon: docs/WORKBENCH_APPEARANCE_V2_CONTRACT.md, #1253 AppearanceRequestedState

Persistence owns user intent only. Derived semantic tokens are never stored.
QML / DWM / Settings UI are out of scope.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

import pytest

from src import workbench_appearance as appearance
from src import workbench_display_preferences as display
from src import workbench_theme as theme


DERIVED_TOKEN_KEYS = (
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
    "textPrimary",
    "textSecondary",
    "surfaceWorkspace",
    "surfaceRaised",
    "focusRing",
)

PRIVATE_PATH_MARKERS = (
    "C:/Users",
    "D:/Dev",
    "/home/user",
    "/Users/",
    "\\\\server",
)


def _raw(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_v1(
    tmp_path: Path,
    *,
    selected: str = "Blood",
    custom_themes: Mapping[str, Mapping[str, Any]] | None = None,
) -> Path:
    path = theme.theme_preferences_path(state_dir=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "schema": theme.THEME_PREFERENCES_SCHEMA,
        "schema_version": 1,
        "selected": selected,
        "custom_themes": dict(custom_themes or {}),
    }
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _profile_dict(profile: appearance.AppearanceProfileInput | None) -> dict[str, Any]:
    if profile is None:
        return {}
    return {
        "themeRef": profile.theme_ref,
        "background": profile.background,
        "foreground": profile.foreground,
        "accent": profile.accent,
        "contrast": profile.contrast,
    }


def _requested_dict(state: appearance.AppearanceRequestedState) -> dict[str, Any]:
    return {
        "mode": state.mode,
        "separateLightDark": state.separate_light_dark,
        "uiFontSize": state.ui_font_size,
        "codeFontSize": state.code_font_size,
        "motionMode": state.motion_mode,
        "shared": _profile_dict(state.shared),
        "dark": _profile_dict(state.dark),
        "light": _profile_dict(state.light),
    }


# --- Clean install / defaults -------------------------------------------------


def test_clean_install_no_preference_file_yields_canonical_defaults(tmp_path: Path) -> None:
    path = theme.theme_preferences_path(state_dir=tmp_path)
    assert not path.exists()
    loaded = theme.load_appearance_preferences(state_dir=tmp_path)
    assert _requested_dict(loaded) == _requested_dict(appearance.AppearanceRequestedState())
    assert not path.exists()  # load must not fabricate a file for missing prefs
    snapshot = appearance.resolve_appearance(loaded)
    assert snapshot.theme_ref == theme.DEFAULT_PRESET_NAME
    assert snapshot.mode_requested == appearance.DEFAULT_MODE
    assert snapshot.motion_mode_requested == appearance.DEFAULT_MOTION_MODE


# --- v1 migration ------------------------------------------------------------


def test_valid_v1_preset_migration_preserves_selection(tmp_path: Path) -> None:
    _write_v1(tmp_path, selected="Arctic")
    loaded = theme.load_appearance_preferences(state_dir=tmp_path)
    assert loaded.shared is not None
    assert loaded.shared.theme_ref == "Arctic"
    raw = _raw(theme.theme_preferences_path(state_dir=tmp_path))
    assert raw["schema_version"] == theme.THEME_PREFERENCES_SCHEMA_VERSION
    assert raw["selected"] == "Arctic"
    assert raw["appearance"]["selectedTheme"] == "Arctic"


def test_valid_v1_custom_theme_migration_preserves_name_and_colors(tmp_path: Path) -> None:
    custom = {
        "Night Desk": {
            "name": "Night Desk",
            "base_preset": "Carbon",
            "accent": "#b0b8c0",
            "background": "#050607",
            "foreground": "#eaecf0",
        }
    }
    _write_v1(tmp_path, selected="Night Desk", custom_themes=custom)
    loaded = theme.load_appearance_preferences(state_dir=tmp_path)
    customs = theme.list_custom_themes(state_dir=tmp_path)
    assert customs == ["Night Desk"]
    assert loaded.shared is not None
    assert loaded.shared.theme_ref == "Night Desk"
    assert loaded.shared.accent == "#b0b8c0"
    assert loaded.shared.background == "#050607"
    assert loaded.shared.foreground == "#eaecf0"
    raw = _raw(theme.theme_preferences_path(state_dir=tmp_path))
    stored = raw["custom_themes"]["Night Desk"]
    assert stored["name"] == "Night Desk"
    assert stored["accent"] == "#b0b8c0"
    assert stored["background"] == "#050607"
    assert stored["foreground"] == "#eaecf0"


def test_multiple_custom_themes_preserved_on_migration(tmp_path: Path) -> None:
    customs = {
        "Alpha": {
            "name": "Alpha",
            "base_preset": "Blood",
            "accent": "#aa1122",
            "background": "#010203",
            "foreground": "#eeeff0",
        },
        "Beta": {
            "name": "Beta",
            "base_preset": "Forest",
            "accent": "#228844",
            "background": "#020301",
            "foreground": "#f0eeea",
        },
    }
    _write_v1(tmp_path, selected="Beta", custom_themes=customs)
    theme.load_appearance_preferences(state_dir=tmp_path)
    assert theme.list_custom_themes(state_dir=tmp_path) == ["Alpha", "Beta"]
    raw = _raw(theme.theme_preferences_path(state_dir=tmp_path))
    assert set(raw["custom_themes"]) == {"Alpha", "Beta"}
    assert raw["selected"] == "Beta"


def test_missing_v2_fields_get_canonical_defaults_on_migration(tmp_path: Path) -> None:
    _write_v1(tmp_path, selected="Rose")
    loaded = theme.load_appearance_preferences(state_dir=tmp_path)
    assert loaded.mode == appearance.DEFAULT_MODE
    assert loaded.separate_light_dark is False
    assert loaded.ui_font_size == appearance.DEFAULT_UI_FONT_SIZE
    assert loaded.code_font_size == appearance.DEFAULT_CODE_FONT_SIZE
    assert loaded.motion_mode == appearance.DEFAULT_MOTION_MODE
    assert loaded.shared is not None
    assert loaded.shared.contrast in (None, appearance.DEFAULT_CONTRAST)


def test_v1_to_v2_migration_is_idempotent(tmp_path: Path) -> None:
    custom = {
        "Studio": {
            "name": "Studio",
            "base_preset": "Blood",
            "accent": "#a01028",
            "background": "#050506",
            "foreground": "#eceef1",
        }
    }
    _write_v1(tmp_path, selected="Studio", custom_themes=custom)
    first = theme.load_appearance_preferences(state_dir=tmp_path)
    first_raw = theme.theme_preferences_path(state_dir=tmp_path).read_text(encoding="utf-8")
    second = theme.load_appearance_preferences(state_dir=tmp_path)
    second_raw = theme.theme_preferences_path(state_dir=tmp_path).read_text(encoding="utf-8")
    assert _requested_dict(first) == _requested_dict(second)
    assert first_raw == second_raw


def test_v1_migration_seeds_motion_from_display_preferences_preserving_off(
    tmp_path: Path,
) -> None:
    display.save_display_preferences({"motion_mode": "off"}, state_dir=tmp_path)
    _write_v1(tmp_path, selected="Carbon")
    loaded = theme.load_appearance_preferences(state_dir=tmp_path)
    assert loaded.motion_mode == "off"
    # Existing #696 off must never become reduced/on.
    assert loaded.motion_mode not in {"reduced", "on", "system"}


# --- V2 roundtrips -----------------------------------------------------------


def test_v2_save_load_roundtrip_identical(tmp_path: Path) -> None:
    requested = appearance.AppearanceRequestedState(
        mode="light",
        separate_light_dark=False,
        ui_font_size=16,
        code_font_size=11,
        motion_mode="reduced",
        shared=appearance.AppearanceProfileInput(
            theme_ref="Forest",
            background="#101210",
            foreground="#e8ebe6",
            accent="#3a7a4a",
            contrast=62,
        ),
    )
    theme.save_appearance_preferences(requested, state_dir=tmp_path)
    loaded = theme.load_appearance_preferences(state_dir=tmp_path)
    assert _requested_dict(loaded) == _requested_dict(
        appearance.appearance_requested_from_mapping(_requested_dict(requested))
    )


@pytest.mark.parametrize(
    ("mode", "profile_attr"),
    [("light", "light"), ("dark", "dark")],
)
def test_light_dark_profile_roundtrip(tmp_path: Path, mode: str, profile_attr: str) -> None:
    dark = appearance.AppearanceProfileInput(
        theme_ref="Blood",
        background="#0b0d10",
        foreground="#e4e6ea",
        accent="#8f0e24",
        contrast=50,
    )
    light = appearance.AppearanceProfileInput(
        theme_ref="Arctic",
        background="#f7f7f5",
        foreground="#171719",
        accent="#6f9fbf",
        contrast=55,
    )
    requested = appearance.AppearanceRequestedState(
        mode=mode,
        separate_light_dark=True,
        dark=dark,
        light=light,
        motion_mode="on",
    )
    theme.save_appearance_preferences(requested, state_dir=tmp_path)
    loaded = theme.load_appearance_preferences(state_dir=tmp_path)
    assert loaded.separate_light_dark is True
    assert _profile_dict(getattr(loaded, profile_attr)) == _profile_dict(
        getattr(requested, profile_attr)
    )
    # Inactive profile must survive the roundtrip.
    other = "light" if profile_attr == "dark" else "dark"
    assert _profile_dict(getattr(loaded, other)) == _profile_dict(getattr(requested, other))


def test_separated_and_unseparated_profile_roundtrips(tmp_path: Path) -> None:
    shared = appearance.AppearanceProfileInput(theme_ref="Rose", contrast=40)
    theme.save_appearance_preferences(
        appearance.AppearanceRequestedState(separate_light_dark=False, shared=shared),
        state_dir=tmp_path,
    )
    unseparated = theme.load_appearance_preferences(state_dir=tmp_path)
    assert unseparated.separate_light_dark is False
    assert unseparated.shared is not None
    assert unseparated.shared.theme_ref == "Rose"

    theme.save_appearance_preferences(
        appearance.AppearanceRequestedState(
            separate_light_dark=True,
            dark=appearance.AppearanceProfileInput(theme_ref="Blood", contrast=50),
            light=appearance.AppearanceProfileInput(theme_ref="Arctic", contrast=60),
        ),
        state_dir=tmp_path,
    )
    separated = theme.load_appearance_preferences(state_dir=tmp_path)
    assert separated.separate_light_dark is True
    assert separated.dark is not None and separated.dark.theme_ref == "Blood"
    assert separated.light is not None and separated.light.theme_ref == "Arctic"


def test_contrast_and_font_size_roundtrips_are_independent(tmp_path: Path) -> None:
    requested = appearance.AppearanceRequestedState(
        ui_font_size=18,
        code_font_size=10,
        shared=appearance.AppearanceProfileInput(theme_ref="Blood", contrast=0),
    )
    theme.save_appearance_preferences(requested, state_dir=tmp_path)
    loaded = theme.load_appearance_preferences(state_dir=tmp_path)
    assert loaded.ui_font_size == 18
    assert loaded.code_font_size == 10
    assert loaded.shared is not None
    assert loaded.shared.contrast == 0

    requested2 = appearance.AppearanceRequestedState(
        ui_font_size=12,
        code_font_size=18,
        shared=appearance.AppearanceProfileInput(theme_ref="Blood", contrast=100),
    )
    theme.save_appearance_preferences(requested2, state_dir=tmp_path)
    loaded2 = theme.load_appearance_preferences(state_dir=tmp_path)
    assert loaded2.ui_font_size == 12
    assert loaded2.code_font_size == 18
    assert loaded2.shared is not None
    assert loaded2.shared.contrast == 100


@pytest.mark.parametrize("motion", ["on", "reduced", "off", "system"])
def test_motion_mode_roundtrip(tmp_path: Path, motion: str) -> None:
    theme.save_appearance_preferences(
        appearance.AppearanceRequestedState(motion_mode=motion),
        state_dir=tmp_path,
    )
    loaded = theme.load_appearance_preferences(state_dir=tmp_path)
    assert loaded.motion_mode == motion


def test_motion_off_never_rewritten_to_reduced_or_on(tmp_path: Path) -> None:
    theme.save_appearance_preferences(
        appearance.AppearanceRequestedState(motion_mode="off"),
        state_dir=tmp_path,
    )
    raw = _raw(theme.theme_preferences_path(state_dir=tmp_path))
    assert raw["appearance"]["motionMode"] == "off"
    loaded = theme.load_appearance_preferences(state_dir=tmp_path)
    assert loaded.motion_mode == "off"


# --- Corruption / future schema / privacy ------------------------------------


def test_corrupt_json_fails_closed_without_blocking_launch(tmp_path: Path) -> None:
    path = theme.theme_preferences_path(state_dir=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json", encoding="utf-8")
    loaded = theme.load_appearance_preferences(state_dir=tmp_path)
    assert _requested_dict(loaded) == _requested_dict(appearance.AppearanceRequestedState())
    # Corrupt source must remain for diagnostics / no silent rewrite claim.
    assert path.read_text(encoding="utf-8") == "{not-json"
    appearance.resolve_appearance(loaded)  # must not raise


def test_malformed_custom_theme_isolated_during_migration(tmp_path: Path) -> None:
    _write_v1(
        tmp_path,
        selected="Good",
        custom_themes={
            "Good": {
                "name": "Good",
                "base_preset": "Blood",
                "accent": "#8f0e24",
                "background": "#0b0d10",
                "foreground": "#e4e6ea",
            },
            "Broken": {
                "name": "Broken",
                "base_preset": "Blood",
                "accent": "not-a-color",
                "background": "#0b0d10",
                "foreground": "#e4e6ea",
            },
        },
    )
    loaded = theme.load_appearance_preferences(state_dir=tmp_path)
    assert "Good" in theme.list_custom_themes(state_dir=tmp_path)
    assert "Broken" not in theme.list_custom_themes(state_dir=tmp_path)
    assert loaded.shared is not None
    assert loaded.shared.theme_ref == "Good"


@pytest.mark.parametrize(
    "payload",
    [
        {"mode": "neon"},
        {"uiFontSize": 99},
        {"codeFontSize": 1},
        {"motionMode": "full-blast"},
        {"shared": {"contrast": 999}},
        {"shared": {"accent": "zz"}},
    ],
)
def test_invalid_fields_normalized_or_fail_closed(tmp_path: Path, payload: dict[str, Any]) -> None:
    base = appearance.AppearanceRequestedState(
        shared=appearance.AppearanceProfileInput(theme_ref="Blood")
    )
    theme.save_appearance_preferences(base, state_dir=tmp_path)
    path = theme.theme_preferences_path(state_dir=tmp_path)
    raw = _raw(path)
    raw["appearance"].update(payload)
    if "shared" in payload:
        raw["appearance"].setdefault("profiles", {})
        raw["appearance"]["profiles"]["shared"] = {
            **(raw["appearance"].get("profiles", {}).get("shared") or {}),
            **payload["shared"],
        }
        # Keep top-level mirror if present for either layout.
        raw["appearance"]["shared"] = raw["appearance"]["profiles"]["shared"]
    path.write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    loaded = theme.load_appearance_preferences(state_dir=tmp_path)
    # Must always produce a resolvable requested state.
    snapshot = appearance.resolve_appearance(loaded)
    assert snapshot.mode_requested in appearance.APPEARANCE_MODES
    assert snapshot.motion_mode_requested in appearance.APPEARANCE_MOTION_MODES


def test_unsupported_future_schema_leaves_original_intact(tmp_path: Path) -> None:
    path = theme.theme_preferences_path(state_dir=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    future = {
        "schema": theme.THEME_PREFERENCES_SCHEMA,
        "schema_version": 99,
        "selected": "KeepMe",
        "custom_themes": {
            "KeepMe": {
                "name": "KeepMe",
                "base_preset": "Blood",
                "accent": "#112233",
                "background": "#010101",
                "foreground": "#eeeeee",
            }
        },
        "appearance": {"mode": "light", "motionMode": "system"},
        "futureOnly": {"doNotTouch": True},
    }
    original = json.dumps(future, indent=2, sort_keys=True) + "\n"
    path.write_text(original, encoding="utf-8")
    loaded = theme.load_appearance_preferences(state_dir=tmp_path)
    assert _requested_dict(loaded) == _requested_dict(appearance.AppearanceRequestedState())
    assert path.read_text(encoding="utf-8") == original
    # Attempted save must not rewrite the unsupported source.
    theme.save_appearance_preferences(
        appearance.AppearanceRequestedState(mode="light"),
        state_dir=tmp_path,
    )
    assert path.read_text(encoding="utf-8") == original


def test_no_derived_semantic_or_window_chrome_tokens_persisted(tmp_path: Path) -> None:
    snap = appearance.resolve_appearance(
        appearance.AppearanceRequestedState(
            shared=appearance.AppearanceProfileInput(theme_ref="Blood", contrast=70)
        )
    )
    # Poison attempt: try to persist derived snapshot fields.
    theme.save_appearance_preferences(
        appearance.AppearanceRequestedState(
            shared=appearance.AppearanceProfileInput(
                theme_ref="Blood",
                background=snap.background,
                foreground=snap.foreground,
                accent=snap.accent,
                contrast=70,
            ),
            motion_mode="on",
        ),
        state_dir=tmp_path,
    )
    blob = theme.theme_preferences_path(state_dir=tmp_path).read_text(encoding="utf-8")
    for key in DERIVED_TOKEN_KEYS:
        assert key not in blob
    assert "windowChrome" not in blob
    assert "protectedHighlight" not in blob
    assert "motion.effective" not in blob


def test_no_absolute_or_private_path_leakage(tmp_path: Path) -> None:
    theme.save_appearance_preferences(
        appearance.AppearanceRequestedState(
            shared=appearance.AppearanceProfileInput(theme_ref="Blood")
        ),
        state_dir=tmp_path,
    )
    # Inject forbidden keys into on-disk payload via #785 custom save path.
    theme.create_custom_theme(
        name="Safe",
        base_preset="Blood",
        state_dir=tmp_path,
    )
    theme.save_custom_theme(
        {
            "name": "Safe",
            "base_preset": "Blood",
            "accent": "#8f0e24",
            "background": "#0b0d10",
            "foreground": "#e4e6ea",
            "absolute_source_path": "C:/Users/secret/samples",
            "private_sample_path": "/home/user/private.wav",
            "path": "D:/Dev/Workspaces/Repos/sample-brain",
        },
        state_dir=tmp_path,
    )
    blob = theme.theme_preferences_path(state_dir=tmp_path).read_text(encoding="utf-8")
    for marker in PRIVATE_PATH_MARKERS:
        assert marker not in blob
    assert "absolute_source_path" not in blob
    assert "private_sample_path" not in blob


def test_write_failure_leaves_previous_valid_file_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    theme.save_appearance_preferences(
        appearance.AppearanceRequestedState(
            shared=appearance.AppearanceProfileInput(theme_ref="Arctic"),
            motion_mode="reduced",
        ),
        state_dir=tmp_path,
    )
    path = theme.theme_preferences_path(state_dir=tmp_path)
    before = path.read_text(encoding="utf-8")

    def _boom(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", _boom)
    result = theme.save_appearance_preferences(
        appearance.AppearanceRequestedState(
            shared=appearance.AppearanceProfileInput(theme_ref="Forest"),
            motion_mode="off",
        ),
        state_dir=tmp_path,
    )
    assert result is None
    assert path.read_text(encoding="utf-8") == before
    loaded = theme.load_appearance_preferences(state_dir=tmp_path)
    assert loaded.shared is not None
    assert loaded.shared.theme_ref == "Arctic"
    assert loaded.motion_mode == "reduced"


def test_restart_after_migration_resolves_identical_appearance_state(tmp_path: Path) -> None:
    custom = {
        "Desk": {
            "name": "Desk",
            "base_preset": "Carbon",
            "accent": "#c0c8d0",
            "background": "#050607",
            "foreground": "#eaecf0",
        }
    }
    _write_v1(tmp_path, selected="Desk", custom_themes=custom)
    first_intent = theme.load_appearance_preferences(state_dir=tmp_path)
    first_snap = appearance.resolve_appearance(first_intent)
    # Simulate restart: new load from disk only.
    second_intent = theme.load_appearance_preferences(state_dir=tmp_path)
    second_snap = appearance.resolve_appearance(second_intent)
    assert _requested_dict(first_intent) == _requested_dict(second_intent)
    assert first_snap.background == second_snap.background
    assert first_snap.foreground == second_snap.foreground
    assert first_snap.accent == second_snap.accent
    assert first_snap.theme_ref == second_snap.theme_ref
    assert first_snap.tokens.as_flat_dict() == second_snap.tokens.as_flat_dict()


def test_existing_785_public_persistence_api_remains_compatible(tmp_path: Path) -> None:
    theme.create_custom_theme(
        name="Compat",
        base_preset="Rose",
        accent="#cc5577",
        state_dir=tmp_path,
    )
    theme.select_theme("Compat", state_dir=tmp_path)
    tokens = theme.resolve_theme(state_dir=tmp_path)
    assert tokens.accent == "#cc5577"
    assert "Compat" in theme.list_custom_themes(state_dir=tmp_path)
    # Appearance intent stays aligned with #785 selection.
    loaded = theme.load_appearance_preferences(state_dir=tmp_path)
    assert loaded.shared is not None
    assert loaded.shared.theme_ref == "Compat"


def test_schema_version_constant_is_v2() -> None:
    assert theme.THEME_PREFERENCES_SCHEMA_VERSION == 2
    assert getattr(theme, "APPEARANCE_V2_PREFERENCES_EXIT", None) == (
        "APPEARANCE_V2_PREFERENCES_MIGRATED"
    )
