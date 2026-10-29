"""#1253 Appearance V2 Python Core — FROZEN CONTRACT TESTS.

Canon:
- docs/WORKBENCH_APPEARANCE_V2_CONTRACT.md
- docs/assets/themes/appearance.v2.contract.json

Status: TEST_FREEZE before #1253 implementation.
These tests pin runtime derivation/state resolution. Do not weaken assertions
to fit incomplete code. Persistence (#1254) and QML (#1255) are out of scope.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import workbench_appearance as appearance
from src import workbench_theme as theme

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_JSON = REPO_ROOT / "docs" / "assets" / "themes" / "appearance.v2.contract.json"


@pytest.fixture(scope="module")
def contract() -> dict:
    return json.loads(CONTRACT_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def golden(contract: dict) -> dict:
    return contract["golden_cases"]


def _tokens(snapshot: appearance.AppearanceResolvedSnapshot) -> dict[str, str]:
    return dict(snapshot.tokens.as_flat_dict())


# ---------------------------------------------------------------------------
# Default Blood / #1205 / protected / typography / motion / windowChrome
# ---------------------------------------------------------------------------


def test_blood_dark_contrast_default_matches_785_and_1205(golden: dict) -> None:
    case = golden["blood_dark_contrast_default"]
    snapshot = appearance.resolve_appearance(
        appearance.AppearanceRequestedState(
            mode="dark",
            shared=appearance.AppearanceProfileInput(
                theme_ref="Blood",
                background=case["input"]["background"],
                foreground=case["input"]["foreground"],
                accent=case["input"]["accent"],
                contrast=50,
            ),
        )
    )
    tokens = _tokens(snapshot)
    for key, expected in case["tokens"].items():
        assert tokens[key] == expected, f"{key}: {tokens[key]} != {expected}"

    assert snapshot.resolved_scheme == "dark"
    assert snapshot.background == "#0b0d10"
    assert tokens["surface.canvas"] == "#0d0f12"  # #1205 workspace target
    assert tokens["windowChrome.background"] == snapshot.background
    assert tokens["windowChrome.foreground"] == tokens["text.primary"]
    assert tokens["windowChrome.border"] == tokens["border.subtle"]
    assert snapshot.typography.ui.standard.font_size == 14.0
    assert snapshot.typography.code.font_size == 12.0
    assert snapshot.motion_effective == "on"

    # #785 compatibility aliases at neutral contrast
    legacy = theme.derive_tokens(
        {
            "accent": case["input"]["accent"],
            "background": case["input"]["background"],
            "foreground": case["input"]["foreground"],
        }
    )
    assert tokens["text.primary"] == legacy["textPrimary"]
    assert tokens["text.secondary"] == legacy["textSecondary"]
    assert tokens["surface.canvas"] == legacy["surfaceWorkspace"]
    assert tokens["surface.panel"] == legacy["surface"]
    assert tokens["surface.raised"] == legacy["surfaceRaised"]
    assert tokens["border.subtle"] == legacy["divider"]
    assert tokens["surface.hover"] == legacy["hover"]
    assert tokens["surface.selected"] == legacy["selected"]
    assert tokens["interaction.focus"] == legacy["focusRing"]


def test_carbon_preset_is_representable_without_blood_assumptions(golden: dict) -> None:
    case = golden["carbon_dark_contrast_default"]
    snapshot = appearance.resolve_appearance(
        appearance.AppearanceRequestedState(
            mode="dark",
            shared=appearance.AppearanceProfileInput(
                theme_ref="Carbon",
                background=case["input"]["background"],
                foreground=case["input"]["foreground"],
                accent=case["input"]["accent"],
                contrast=50,
            ),
        )
    )
    tokens = _tokens(snapshot)
    for key, expected in case["tokens"].items():
        assert tokens[key] == expected, f"{key}: {tokens[key]} != {expected}"
    assert tokens["surface.canvas"] != "#0d0f12"
    assert tokens["accent.base"] == "#a8b0b8"


def test_custom_dark_primitives_derive_deterministically(golden: dict) -> None:
    case = golden["custom_dark_primitives"]
    payload = appearance.AppearanceRequestedState(
        mode="dark",
        shared=appearance.AppearanceProfileInput(
            theme_ref="custom",
            background=case["input"]["background"],
            foreground=case["input"]["foreground"],
            accent=case["input"]["accent"],
            contrast=50,
        ),
    )
    first = _tokens(appearance.resolve_appearance(payload))
    second = _tokens(appearance.resolve_appearance(payload))
    assert first == second
    for key, expected in case["tokens"].items():
        assert first[key] == expected, f"{key}: {first[key]} != {expected}"
    # Protected status must not become accent-owned
    assert first["status.error"] != first["accent.base"]
    assert first["status.success"] != first["accent.base"]


def test_custom_light_theme_uses_same_authority() -> None:
    snapshot = appearance.resolve_appearance(
        appearance.AppearanceRequestedState(
            mode="light",
            shared=appearance.AppearanceProfileInput(
                theme_ref="custom",
                background="#f7f7f5",
                foreground="#171719",
                accent="#3f7ee8",
                contrast=50,
            ),
        )
    )
    tokens = _tokens(snapshot)
    assert snapshot.resolved_scheme == "light"
    assert tokens["text.primary"] == "#171719"
    assert tokens["accent.base"] == "#3f7ee8"
    assert tokens["status.error"] == "#a93245"
    assert tokens["status.warning"] == "#8a5d12"
    assert tokens["status.success"] == "#2f714c"
    assert tokens["status.info"] == "#346f96"
    # Surfaces remain hierarchical (not flattened to the same background)
    assert tokens["surface.canvas"] != tokens["surface.panel"]
    assert tokens["surface.panel"] != tokens["surface.raised"]
    assert tokens["windowChrome.background"] == snapshot.background


def test_accent_red_to_green_keeps_protected_status_stable(golden: dict) -> None:
    red = appearance.resolve_appearance(
        appearance.AppearanceRequestedState(
            mode="dark",
            shared=appearance.AppearanceProfileInput(
                background=golden["protected_status_red_accent"]["input"]["background"],
                foreground=golden["protected_status_red_accent"]["input"]["foreground"],
                accent=golden["protected_status_red_accent"]["input"]["accent"],
                contrast=50,
            ),
        )
    )
    green = appearance.resolve_appearance(
        appearance.AppearanceRequestedState(
            mode="dark",
            shared=appearance.AppearanceProfileInput(
                background=golden["protected_status_green_accent"]["input"]["background"],
                foreground=golden["protected_status_green_accent"]["input"]["foreground"],
                accent=golden["protected_status_green_accent"]["input"]["accent"],
                contrast=50,
            ),
        )
    )
    red_tokens = _tokens(red)
    green_tokens = _tokens(green)
    assert red_tokens["accent.base"] == "#ff3030"
    assert green_tokens["accent.base"] == "#30c060"
    for key in ("status.error", "status.warning", "status.success", "status.info"):
        assert red_tokens[key] == green_tokens[key]
        assert red_tokens[key] == golden["protected_status_red_accent"]["tokens"][key]
    # Accent-owned families must change
    assert red_tokens["accent.hover"] != green_tokens["accent.hover"]
    assert red_tokens["accent.active"] != green_tokens["accent.active"]
    assert red_tokens["surface.selected"] != green_tokens["surface.selected"]
    # Product protected highlights stay Accent-independent
    assert red.tokens.protected_highlight["libraryAllSamplesAccent"] == green.tokens.protected_highlight["libraryAllSamplesAccent"]
    assert red.tokens.protected_highlight["libraryAllSamplesAccent"] != red_tokens["accent.base"]


# ---------------------------------------------------------------------------
# Contrast
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case_name",
    ("blood_dark_contrast_low", "blood_dark_contrast_default", "blood_dark_contrast_high"),
)
def test_blood_contrast_golden_vectors(golden: dict, case_name: str) -> None:
    case = golden[case_name]
    snapshot = appearance.resolve_appearance(
        appearance.AppearanceRequestedState(
            mode="dark",
            shared=appearance.AppearanceProfileInput(
                theme_ref="Blood",
                background=case["input"]["background"],
                foreground=case["input"]["foreground"],
                accent=case["input"]["accent"],
                contrast=case["input"]["contrast"],
            ),
        )
    )
    tokens = _tokens(snapshot)
    for key, expected in case["tokens"].items():
        assert tokens[key] == expected, f"{case_name} {key}: {tokens[key]} != {expected}"


def test_contrast_only_affects_allowed_families(golden: dict) -> None:
    low = _tokens(
        appearance.resolve_appearance(
            appearance.AppearanceRequestedState(
                mode="dark",
                shared=appearance.AppearanceProfileInput(
                    theme_ref="Blood",
                    background="#0b0d10",
                    foreground="#e4e6ea",
                    accent="#8f0e24",
                    contrast=25,
                ),
            )
        )
    )
    high = _tokens(
        appearance.resolve_appearance(
            appearance.AppearanceRequestedState(
                mode="dark",
                shared=appearance.AppearanceProfileInput(
                    theme_ref="Blood",
                    background="#0b0d10",
                    foreground="#e4e6ea",
                    accent="#8f0e24",
                    contrast=75,
                ),
            )
        )
    )
    # Primitives and protected families must not move
    for key in (
        "accent.base",
        "accent.hover",
        "accent.active",
        "accent.onAccent",
        "status.error",
        "status.warning",
        "status.success",
        "status.info",
    ):
        assert low[key] == high[key]
    # Allowed families must move
    assert low["text.secondary"] != high["text.secondary"]
    assert low["surface.panel"] != high["surface.panel"]
    assert low["border.subtle"] != high["border.subtle"]
    assert low["accent.subtle"] != high["accent.subtle"]


def test_invalid_contrast_fails_closed_to_default() -> None:
    snapshot = appearance.resolve_appearance(
        appearance.AppearanceRequestedState(
            mode="dark",
            shared=appearance.AppearanceProfileInput(
                theme_ref="Blood",
                contrast=999,
            ),
        )
    )
    assert snapshot.contrast == 50
    assert _tokens(snapshot)["surface.canvas"] == "#0d0f12"


# ---------------------------------------------------------------------------
# Typography / Motion / Profiles / Mode
# ---------------------------------------------------------------------------


def test_ui_and_code_font_sizes_are_independent(golden: dict) -> None:
    case = golden["font_size_independence"]["input"]
    snapshot = appearance.resolve_appearance(
        appearance.AppearanceRequestedState(
            mode="dark",
            ui_font_size=case["uiFontSize"],
            code_font_size=case["codeFontSize"],
            shared=appearance.AppearanceProfileInput(theme_ref="Blood"),
        )
    )
    assert snapshot.ui_font_size == 16
    assert snapshot.code_font_size == 11
    assert snapshot.typography.ui.standard.font_size == 16.0
    assert snapshot.typography.code.font_size == 11.0
    assert snapshot.typography.code.line_height == 16.5  # 11 * 1.5

    only_ui = appearance.resolve_appearance(
        appearance.AppearanceRequestedState(
            mode="dark",
            ui_font_size=18,
            code_font_size=12,
            shared=appearance.AppearanceProfileInput(theme_ref="Blood"),
        )
    )
    only_code = appearance.resolve_appearance(
        appearance.AppearanceRequestedState(
            mode="dark",
            ui_font_size=14,
            code_font_size=18,
            shared=appearance.AppearanceProfileInput(theme_ref="Blood"),
        )
    )
    assert only_ui.code_font_size == 12
    assert only_code.ui_font_size == 14
    assert only_ui.typography.ui.standard.font_size != only_code.typography.ui.standard.font_size
    assert only_ui.typography.code.font_size != only_code.typography.code.font_size


@pytest.mark.parametrize(
    ("motion_mode", "platform_reduce_motion", "expected"),
    [
        ("on", True, "on"),
        ("reduced", False, "reduced"),
        ("off", True, "off"),
        ("system", True, "reduced"),
        ("system", False, "on"),
        ("system", None, "on"),
    ],
)
def test_motion_resolution_matches_696_compatibility(
    motion_mode: str,
    platform_reduce_motion: bool | None,
    expected: str,
) -> None:
    snapshot = appearance.resolve_appearance(
        appearance.AppearanceRequestedState(
            mode="dark",
            motion_mode=motion_mode,
            shared=appearance.AppearanceProfileInput(theme_ref="Blood"),
        ),
        platform_reduce_motion=platform_reduce_motion,
    )
    assert snapshot.motion_mode_requested == motion_mode
    assert snapshot.motion_effective == expected
    assert snapshot.tokens.motion_effective == expected


def test_system_and_explicit_mode_resolution_is_injectable() -> None:
    dark = appearance.resolve_appearance(
        appearance.AppearanceRequestedState(
            mode="system",
            shared=appearance.AppearanceProfileInput(theme_ref="Blood"),
        ),
        platform_color_scheme="dark",
    )
    light = appearance.resolve_appearance(
        appearance.AppearanceRequestedState(
            mode="system",
            shared=appearance.AppearanceProfileInput(theme_ref="Blood"),
        ),
        platform_color_scheme="light",
    )
    unavailable = appearance.resolve_appearance(
        appearance.AppearanceRequestedState(
            mode="system",
            shared=appearance.AppearanceProfileInput(theme_ref="Blood"),
        ),
        platform_color_scheme=None,
    )
    assert dark.resolved_scheme == "dark"
    assert light.resolved_scheme == "light"
    assert unavailable.resolved_scheme == "dark"
    assert light.background == "#f7f7f5"
    assert light.foreground == "#171719"
    assert light.accent == "#8f0e24"


def test_separate_light_dark_profiles_preserve_inactive_state() -> None:
    requested = appearance.AppearanceRequestedState(
        mode="dark",
        separate_light_dark=True,
        dark=appearance.AppearanceProfileInput(
            theme_ref="Blood",
            contrast=60,
            accent="#8f0e24",
        ),
        light=appearance.AppearanceProfileInput(
            theme_ref="Blood",
            background="#f7f7f5",
            foreground="#171719",
            accent="#8f0e24",
            contrast=45,
        ),
    )
    dark_snap = appearance.resolve_appearance(requested)
    light_snap = appearance.resolve_appearance(
        appearance.AppearanceRequestedState(
            mode="light",
            separate_light_dark=True,
            dark=requested.dark,
            light=requested.light,
        )
    )
    assert dark_snap.contrast == 60
    assert light_snap.contrast == 45
    assert light_snap.background == "#f7f7f5"
    assert dark_snap.background == "#0b0d10"
    # Switching mode must not mutate the inactive profile inputs
    assert requested.dark is not None and requested.dark.contrast == 60
    assert requested.light is not None and requested.light.contrast == 45


def test_unseparated_shared_overrides_apply_to_both_schemes() -> None:
    requested = appearance.AppearanceRequestedState(
        mode="dark",
        separate_light_dark=False,
        shared=appearance.AppearanceProfileInput(
            theme_ref="Blood",
            accent="#3f7ee8",
            contrast=50,
        ),
    )
    dark_snap = appearance.resolve_appearance(requested)
    light_snap = appearance.resolve_appearance(
        appearance.AppearanceRequestedState(
            mode="light",
            separate_light_dark=False,
            shared=requested.shared,
        )
    )
    assert dark_snap.accent == "#3f7ee8"
    assert light_snap.accent == "#3f7ee8"
    assert light_snap.background == "#f7f7f5"


def test_focus_and_selection_have_explicit_ownership() -> None:
    snapshot = appearance.resolve_appearance(
        appearance.AppearanceRequestedState(
            mode="dark",
            shared=appearance.AppearanceProfileInput(
                theme_ref="Blood",
                background="#0b0d10",
                foreground="#e4e6ea",
                accent="#8f0e24",
                contrast=50,
            ),
        )
    )
    tokens = _tokens(snapshot)
    assert tokens["interaction.focus"] == tokens["accent.base"]
    assert tokens["interaction.selection"] == tokens["surface.selected"]
    assert tokens["interaction.pressed"] == tokens["accent.active"]
    # Changing accent moves focus; protected status stays put
    other = appearance.resolve_appearance(
        appearance.AppearanceRequestedState(
            mode="dark",
            shared=appearance.AppearanceProfileInput(
                theme_ref="Blood",
                background="#0b0d10",
                foreground="#e4e6ea",
                accent="#30c060",
                contrast=50,
            ),
        )
    )
    other_tokens = _tokens(other)
    assert other_tokens["interaction.focus"] == "#30c060"
    assert other_tokens["status.error"] == tokens["status.error"]


# ---------------------------------------------------------------------------
# Invalid inputs fail closed
# ---------------------------------------------------------------------------


def test_invalid_inputs_fail_closed_to_contract_defaults() -> None:
    snapshot = appearance.resolve_appearance(
        appearance.AppearanceRequestedState(
            mode="neon",  # type: ignore[arg-type]
            separate_light_dark=False,
            ui_font_size=99,
            code_font_size=-3,
            motion_mode="teleport",
            shared=appearance.AppearanceProfileInput(
                theme_ref="Blood",
                background="not-a-color",
                foreground="#gg0000",
                accent="",
                contrast=-10,
            ),
        ),
        platform_color_scheme="banana",
        platform_reduce_motion=None,
    )
    assert snapshot.mode_requested in {"dark", "system", "light"}
    # invalid mode → dark default
    assert snapshot.resolved_scheme == "dark"
    assert snapshot.ui_font_size == 14
    assert snapshot.code_font_size == 12
    assert snapshot.motion_effective == "on"
    assert snapshot.contrast == 50
    assert snapshot.background == "#0b0d10"
    assert snapshot.foreground == "#e4e6ea"
    assert snapshot.accent == "#8f0e24"
    tokens = _tokens(snapshot)
    assert tokens["surface.canvas"] == "#0d0f12"
    assert "nan" not in tokens["text.secondary"].lower()


def test_resolve_appearance_does_not_read_os_at_import_or_call_without_injection() -> None:
    # Pure path: no platform preference → deterministic dark/on fallbacks.
    snap_a = appearance.resolve_appearance(
        appearance.AppearanceRequestedState(mode="system", motion_mode="system")
    )
    snap_b = appearance.resolve_appearance(
        appearance.AppearanceRequestedState(mode="system", motion_mode="system")
    )
    assert snap_a.resolved_scheme == "dark"
    assert snap_a.motion_effective == "on"
    assert _tokens(snap_a) == _tokens(snap_b)


def test_legacy_theme_helpers_remain_compatible() -> None:
    blood = theme.resolve_theme("Blood", state_dir=Path("."))
    assert blood.background == "#0b0d10"
    assert blood.surfaceWorkspace == "#0d0f12"
    assert blood.accent == "#8f0e24"
    semantics = theme.theme_tokens_to_qml_semantics(blood)
    assert semantics["surfaceRoot"] == "#0d0f12"
    assert semantics["libraryAllSamplesAccent"] == "#93a8b8"
