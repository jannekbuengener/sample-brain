"""Contract-plane validation for #1252 Appearance System V2 freeze.

Canonical authority:
- docs/WORKBENCH_APPEARANCE_V2_CONTRACT.md
- docs/assets/themes/appearance.v2.contract.json

This test pins documentation/schema only. It must not implement #1253 runtime
Theme Core V2, #1254 persistence migration, #1255 QML projection, or #1256 UI.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_MD = REPO_ROOT / "docs" / "WORKBENCH_APPEARANCE_V2_CONTRACT.md"
CONTRACT_JSON = REPO_ROOT / "docs" / "assets" / "themes" / "appearance.v2.contract.json"
PRESETS_V1_JSON = REPO_ROOT / "docs" / "assets" / "themes" / "presets.v1.json"


@pytest.fixture(scope="module")
def contract() -> dict:
    data = json.loads(CONTRACT_JSON.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


@pytest.fixture(scope="module")
def markdown() -> str:
    return CONTRACT_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def presets_v1() -> dict:
    return json.loads(PRESETS_V1_JSON.read_text(encoding="utf-8"))


def test_contract_files_exist() -> None:
    assert CONTRACT_MD.is_file()
    assert CONTRACT_JSON.is_file()


def test_contract_is_normative_not_runtime_serialization(contract: dict) -> None:
    assert contract["document_type"] == "sample_brain.workbench_appearance_v2_contract"
    assert contract["contract_schema_version"] == "1.0.0"
    assert contract["plane"] == "normative_contract_schema"
    assert contract["not_runtime_serialization"] is True
    assert contract["issue"] == 1252
    assert contract["parent_issue"] == 1251
    assert contract["runtime_implementation_owner_issue"] == 1253
    assert contract["persistence_owner_issue"] == 1254
    assert contract["qml_bridge_owner_issue"] == 1255
    assert contract["settings_ui_owner_issue"] == 1256
    assert contract["screen1_adoption_owner_issue"] == 1257
    assert contract["exit_marker"] == "APPEARANCE_V2_CONTRACT_FROZEN"


def test_state_defaults_bounds_and_profile_scope(contract: dict) -> None:
    state = contract["appearance_state"]
    assert state["mode"]["values"] == ["system", "light", "dark"]
    assert state["mode"]["default"] == "dark"  # #785 compatibility: no silent light-mode switch
    assert state["mode"]["system_unavailable_fallback"] == "dark"
    assert state["separateLightDark"]["default"] is False

    assert state["contrast"] == {"type": "integer", "minimum": 0, "maximum": 100, "default": 50, "step": 1}
    assert state["uiFontSize"] == {"unit": "logical_px", "type": "integer", "minimum": 12, "maximum": 18, "default": 14, "step": 1}
    assert state["codeFontSize"] == {"unit": "logical_px", "type": "integer", "minimum": 10, "maximum": 18, "default": 12, "step": 1}

    assert set(state["global_fields"]) == {
        "mode",
        "separateLightDark",
        "uiFontSize",
        "codeFontSize",
        "motionMode",
    }
    assert set(state["profile_fields"]) == {
        "themeRef",
        "background",
        "foreground",
        "accent",
        "contrast",
    }
    assert state["profile_resolution"]["shared_overrides_apply_to_both_schemes"] is True
    assert state["profile_resolution"]["per_mode_overrides_when_separated"] is True


def test_motion_reuses_existing_696_contract(contract: dict, markdown: str) -> None:
    motion = contract["motion"]
    assert motion["canonical_field"] == "motionMode"
    assert motion["values"] == ["system", "on", "reduced", "off"]
    assert motion["default"] == "on"
    assert motion["existing_696_values_preserved"] == ["on", "reduced", "off"]
    assert motion["system_resolution"]["reduce_motion_true"] == "reduced"
    assert motion["system_resolution"]["reduce_motion_false"] == "on"
    assert motion["system_resolution"]["unavailable"] == "on"
    assert "#696" in markdown
    assert "on | reduced | off" in markdown


def test_semantic_token_families_and_ownership_are_explicit(contract: dict) -> None:
    tokens = contract["semantic_tokens"]
    required = {
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
        "typography.ui",
        "typography.code",
        "motion.effective",
        "windowChrome.background",
        "windowChrome.foreground",
        "windowChrome.border",
    }
    assert required <= set(tokens)
    assert all(tokens[token]["owner"] for token in required)

    assert tokens["surface.canvas"]["owner"] == "background+foreground+contrast"
    assert tokens["text.primary"]["owner"] == "foreground"
    assert tokens["accent.base"]["owner"] == "accent"
    assert tokens["status.error"]["owner"] == "protected_status_palette"
    assert tokens["status.warning"]["owner"] == "protected_status_palette"
    assert tokens["status.success"]["owner"] == "protected_status_palette"
    assert tokens["status.info"]["owner"] == "protected_status_palette"


def test_neutral_contrast_preserves_785_blood_exactly(contract: dict, presets_v1: dict) -> None:
    compatibility = contract["theme_core_v1_compatibility"]
    assert compatibility["neutral_contrast"] == 50
    assert compatibility["preserve_v1_dark_defaults_exactly"] is True
    aliases = compatibility["legacy_token_aliases"]
    blood = presets_v1["presets"]["Blood"]
    expected = {**blood["base"], **blood["derived"]}

    neutral = contract["golden_cases"]["blood_dark_contrast_default"]["tokens"]
    for old_name, new_name in aliases.items():
        assert neutral[new_name].lower() == expected[old_name].lower(), (old_name, new_name)


def test_contrast_scope_anchors_and_golden_vectors(contract: dict) -> None:
    contrast = contract["contrast_model"]
    assert contrast["range"] == [0, 100]
    assert contrast["neutral"] == 50
    assert contrast["interpolation"] == "piecewise_linear_between_0_50_100_anchors"
    assert contrast["color_mix_space"] == "srgb_channel_linear_existing_mix_hex_rounding"
    assert contrast["must_not_modify"] == [
        "background",
        "foreground",
        "accent.base",
        "accent.hover",
        "accent.active",
        "accent.onAccent",
        "status.*",
        "protectedHighlight.*",
    ]

    low = contract["golden_cases"]["blood_dark_contrast_low"]
    default = contract["golden_cases"]["blood_dark_contrast_default"]
    high = contract["golden_cases"]["blood_dark_contrast_high"]
    assert [low["input"]["contrast"], default["input"]["contrast"], high["input"]["contrast"]] == [25, 50, 75]
    assert low["tokens"]["text.secondary"] == "#5f6164"
    assert default["tokens"]["text.secondary"] == "#6d6f72"
    assert high["tokens"]["text.secondary"] == "#7b7d80"
    assert low["tokens"]["surface.panel"] == "#101215"
    assert default["tokens"]["surface.panel"] == "#111316"
    assert high["tokens"]["surface.panel"] == "#141619"
    for case in (low, default, high):
        assert case["tokens"]["accent.base"] == "#8f0e24"
        assert case["tokens"]["status.error"] == contract["protected_status_palette"]["dark"]["error"]


def test_protected_status_palette_does_not_follow_accent(contract: dict) -> None:
    red = contract["golden_cases"]["protected_status_red_accent"]
    green = contract["golden_cases"]["protected_status_green_accent"]
    assert red["input"]["accent"] != green["input"]["accent"]
    assert red["tokens"]["accent.base"] != green["tokens"]["accent.base"]
    for token in ("status.error", "status.warning", "status.success", "status.info"):
        assert red["tokens"][token] == green["tokens"][token]
    assert contract["protected_highlights"]["must_never_alias_accent_implicitly"] is True


def test_profile_model_separated_and_unseparated(contract: dict) -> None:
    unseparated = contract["golden_cases"]["profiles_unseparated"]
    separated = contract["golden_cases"]["profiles_separated"]
    assert unseparated["input"]["separateLightDark"] is False
    assert unseparated["expected"]["custom_override_scope"] == "shared"
    assert unseparated["expected"]["dark_v1_values_preserved"] is True
    assert separated["input"]["separateLightDark"] is True
    assert separated["expected"]["custom_override_scope"] == "per_mode"
    assert separated["expected"]["light_and_dark_can_diverge"] is True
    assert contract["profile_model"]["v1_dark_variant_migration"] == "exact_preserve"
    assert contract["profile_model"]["missing_light_variant_fallback"]["background"] == "#f7f7f5"
    assert contract["profile_model"]["missing_light_variant_fallback"]["foreground"] == "#171719"


def test_ui_and_code_font_roles_are_independent(contract: dict) -> None:
    typography = contract["typography"]
    assert typography["ui"]["base_size"] == 14
    assert typography["ui"]["geometry_auto_scale"] is False
    assert typography["code"]["base_size"] == 12
    assert typography["code"]["independent_from_ui"] is True
    assert typography["ui"]["roles"]["caption"] == {"fontSize": 12, "lineHeight": 16}
    assert typography["ui"]["roles"]["standard"] == {"fontSize": 14, "lineHeight": 20}
    assert typography["ui"]["roles"]["content"] == {"fontSize": 16, "lineHeight": 26}
    assert typography["ui"]["roles"]["section"] == {"fontSize": 14, "lineHeight": 18, "weight": 500}

    case = contract["golden_cases"]["font_size_independence"]
    assert case["input"] == {"uiFontSize": 16, "codeFontSize": 11}
    assert case["expected"]["codeFontSize"] == 11
    assert case["expected"]["ui_geometry_auto_scaled"] is False


def test_accessibility_guards_are_frozen(contract: dict) -> None:
    guards = contract["accessibility_guards"]
    assert guards["text_primary_min_contrast_ratio"] == 4.5
    assert guards["focus_indicator_min_contrast_ratio"] == 3.0
    assert guards["invalid_custom_profile"] == "reject_commit_keep_last_valid_profile"
    assert guards["accent_on_accent"] == "choose_background_or_foreground_with_higher_wcag_contrast"
    assert guards["protected_status_not_recolored_by_contrast"] is True


def test_persistence_and_consumer_boundaries(contract: dict, markdown: str) -> None:
    persistence = contract["persistence_boundary"]
    assert persistence["owner_issue"] == 1254
    assert persistence["persist_user_intent_not_derived_tokens"] is True
    assert persistence["migrate_theme_core_v1"] is True
    assert persistence["no_second_qml_store"] is True

    consumers = contract["consumer_boundaries"]
    assert consumers["1205"] == "workspace_visual_target_consumer_not_redefined"
    assert consumers["1214"] == "native_window_chrome_consumer"
    assert consumers["1248"] == "library_visual_typography_contract_preserved_at_defaults"
    assert consumers["1249"] == "screen1_typography_contract_preserved_at_defaults"
    assert "#1205" in markdown
    assert "#1214" in markdown
    assert "#1248" in markdown
    assert "#1249" in markdown


def test_required_golden_cases_and_out_of_scope(contract: dict, markdown: str) -> None:
    required = {
        "blood_dark_contrast_default",
        "carbon_dark_contrast_default",
        "custom_dark_primitives",
        "blood_dark_contrast_low",
        "blood_dark_contrast_high",
        "protected_status_red_accent",
        "protected_status_green_accent",
        "profiles_unseparated",
        "profiles_separated",
        "font_size_independence",
    }
    assert required <= set(contract["golden_cases"])
    out = set(contract["hard_out_of_scope"])
    assert "runtime_theme_core_v2_implementation" in out
    assert "persistence_schema_migration_execution" in out
    assert "qml_settings_ui" in out
    assert "screen1_component_migration" in out
    assert "windows_dwm_implementation" in out
    assert "APPEARANCE_V2_CONTRACT_FROZEN" in markdown
