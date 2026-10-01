"""#785 Theme Core — FROZEN RED CONTRACT.

Status: TEST_FREEZE
Canon: docs/assets/themes/presets.v1.json, docs/assets/themes/README.md

These tests freeze Theme Core behaviour. Implementation must satisfy them
without softening assertions. Failures must come from missing product behaviour.

Scope: Python Theme Core + local persistence in workbench_state_dir family.
Out of scope: QML file edits (PR #792 / #780 may still be open).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from src import workbench_theme as theme


PRESET_ORDER = ("Blood", "Carbon", "Arctic", "Rose", "Forest")
BLOOD_A_ACCENT = "#8f0e24"
BLOOD_B_ACCENT = "#d4143a"
BLOOD_BACKGROUND = "#050506"
BLOOD_FOREGROUND = "#eceef1"

BASE_KEYS = frozenset({"accent", "background", "foreground"})
DERIVED_KEYS = frozenset(
    {
        "textPrimary",
        "textSecondary",
        "surface",
        "surfaceRaised",
        "divider",
        "hover",
        "selected",
        "focusRing",
    }
)
PERSIST_ALLOWED_KEYS = frozenset(
    {"schema", "schema_version", "name", "base_preset", "accent", "background", "foreground"}
)

# Theme Core token → existing QML semantic names (mapping helper only).
QML_SEMANTIC_EXPECTATIONS = {
    "surfaceRoot": "background",
    "surfaceHeader": "background",
    "surfaceBrowser": "surface",
    "surfacePanel": "surface",
    "surfaceElevated": "surfaceRaised",
    "borderSubtle": "divider",
    "dividerDefault": "divider",
    "textPrimary": "textPrimary",
    "textSecondary": "textSecondary",
    "textDisabled": "textSecondary",
    "actionActive": "accent",
    "selectionSurface": "selected",
    "selectionBorder": "accent",
    "waveformActive": "accent",
    "waveformDefault": "textSecondary",
    "focusRing": "focusRing",
    "hoverSurface": "hover",
}
TEXT_ON_ACTION = "#ffffff"


def _canon_presets() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    path = root / "docs" / "assets" / "themes" / "presets.v1.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_hex(value: str) -> str:
    token = str(value).strip().lower()
    if not token.startswith("#"):
        token = f"#{token}"
    return token


def _token_map(resolved: Any) -> dict[str, str]:
    if isinstance(resolved, Mapping):
        return {str(k): _normalize_hex(str(v)) for k, v in resolved.items()}
    if hasattr(resolved, "__dict__"):
        raw = {
            k: v
            for k, v in vars(resolved).items()
            if not k.startswith("_") and isinstance(v, str) and v.startswith("#")
        }
        if raw:
            return {str(k): _normalize_hex(str(v)) for k, v in raw.items()}
    for attr in ("tokens", "as_dict", "to_dict", "colors"):
        value = getattr(resolved, attr, None)
        if callable(value):
            value = value()
        if isinstance(value, Mapping):
            return {str(k): _normalize_hex(str(v)) for k, v in value.items()}
    pytest.fail(f"Theme resolve result is not a token mapping: {type(resolved)!r}")


# --- Preset catalogue --------------------------------------------------------


def test_preset_list_is_deterministic_from_canon() -> None:
    names = theme.list_presets()
    assert tuple(names) == PRESET_ORDER
    canon = _canon_presets()
    assert tuple(canon["presets"].keys()) == PRESET_ORDER


def test_blood_default_is_stage_a_not_blood_b() -> None:
    resolved = _token_map(theme.resolve_theme())
    assert resolved["accent"] == BLOOD_A_ACCENT
    assert resolved["background"] == BLOOD_BACKGROUND
    assert resolved["foreground"] == BLOOD_FOREGROUND
    assert resolved["accent"] != BLOOD_B_ACCENT

    blood = _token_map(theme.resolve_theme("Blood"))
    assert blood["accent"] == BLOOD_A_ACCENT
    assert blood["accent"] != BLOOD_B_ACCENT


def test_blood_b_is_comparison_only_not_silent_default() -> None:
    """Blood B accent must remain reachable as comparison, never as default."""
    default = _token_map(theme.resolve_theme())
    assert default["accent"] != BLOOD_B_ACCENT

    variants = theme.blood_variants()
    assert "A" in variants and "B" in variants
    assert _normalize_hex(variants["A"]["accent"]) == BLOOD_A_ACCENT
    assert _normalize_hex(variants["B"]["accent"]) == BLOOD_B_ACCENT
    assert theme.default_preset_name() == "Blood"
    assert _token_map(theme.resolve_theme(theme.default_preset_name()))["accent"] == BLOOD_A_ACCENT


def test_derived_tokens_match_canon_formulas_for_all_presets() -> None:
    canon = _canon_presets()
    for name in PRESET_ORDER:
        expected = canon["presets"][name]["derived"]
        base = canon["presets"][name]["base"]
        derived = theme.derive_tokens(base)
        derived_map = _token_map(derived) if not isinstance(derived, Mapping) else {
            k: _normalize_hex(str(v)) for k, v in derived.items()
        }
        for key in DERIVED_KEYS:
            assert derived_map[key] == _normalize_hex(expected[key]), f"{name}.{key}"

        resolved = _token_map(theme.resolve_theme(name))
        for key, value in base.items():
            assert resolved[key] == _normalize_hex(value)
        for key, value in expected.items():
            assert resolved[key] == _normalize_hex(value)


def test_mix_formula_is_deterministic() -> None:
    # mix(foreground, background, 0.45) for Blood → textSecondary #848587
    assert (
        _normalize_hex(theme.mix_hex("#eceef1", "#050506", 0.45)) == "#848587"
    )
    assert (
        _normalize_hex(theme.mix_hex("#050506", "#8f0e24", 0.22)) == "#23070d"
    )


# --- Persistence / custom themes --------------------------------------------


def test_persist_only_base_tokens_not_derived(tmp_path: Path) -> None:
    theme.create_custom_theme(
        name="Studio Blood",
        base_preset="Blood",
        accent="#a01028",
        background="#050506",
        foreground="#eceef1",
        state_dir=tmp_path,
    )
    path = theme.theme_preferences_path(state_dir=tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    customs = raw.get("custom_themes") or raw.get("customs") or {}
    assert "Studio Blood" in customs
    stored = customs["Studio Blood"]
    for key in DERIVED_KEYS:
        assert key not in stored
    assert set(stored) <= PERSIST_ALLOWED_KEYS | {"selected", "active"}
    for key in ("accent", "background", "foreground", "name", "base_preset"):
        assert key in stored
    # Reject attempts to persist derived tokens as free edits.
    theme.save_custom_theme(
        {
            "name": "Studio Blood",
            "base_preset": "Blood",
            "accent": "#a01028",
            "background": "#050506",
            "foreground": "#eceef1",
            "selected": "#ff0000",
            "textSecondary": "#112233",
        },
        state_dir=tmp_path,
    )
    reloaded = json.loads(path.read_text(encoding="utf-8"))
    customs2 = reloaded.get("custom_themes") or reloaded.get("customs") or {}
    stored2 = customs2["Studio Blood"]
    for key in DERIVED_KEYS:
        assert key not in stored2


def test_custom_theme_lifecycle_preserves_original_presets(tmp_path: Path) -> None:
    blood_before = _token_map(theme.resolve_theme("Blood"))

    theme.create_custom_theme(
        name="Night Desk",
        base_preset="Carbon",
        accent="#b0b8c0",
        state_dir=tmp_path,
    )
    theme.select_theme("Night Desk", state_dir=tmp_path)
    active = _token_map(theme.resolve_theme(state_dir=tmp_path))
    assert active["accent"] == "#b0b8c0"
    assert active["background"] == _token_map(theme.resolve_theme("Carbon"))["background"]

    theme.rename_custom_theme("Night Desk", "Night Desk II", state_dir=tmp_path)
    names = theme.list_custom_themes(state_dir=tmp_path)
    assert "Night Desk" not in names
    assert "Night Desk II" in names
    theme.select_theme("Night Desk II", state_dir=tmp_path)

    theme.save_custom_theme(
        {
            "name": "Night Desk II",
            "base_preset": "Carbon",
            "accent": "#c0c8d0",
            "background": "#050607",
            "foreground": "#eaecf0",
        },
        state_dir=tmp_path,
    )
    reloaded = _token_map(theme.resolve_theme(state_dir=tmp_path))
    assert reloaded["accent"] == "#c0c8d0"

    theme.reset_custom_theme("Night Desk II", state_dir=tmp_path)
    reset = _token_map(theme.resolve_theme(state_dir=tmp_path))
    carbon = _token_map(theme.resolve_theme("Carbon"))
    assert reset["accent"] == carbon["accent"]
    assert reset["background"] == carbon["background"]
    assert reset["foreground"] == carbon["foreground"]

    theme.delete_custom_theme("Night Desk II", state_dir=tmp_path)
    assert "Night Desk II" not in theme.list_custom_themes(state_dir=tmp_path)
    theme.select_theme("Blood", state_dir=tmp_path)

    blood_after = _token_map(theme.resolve_theme("Blood"))
    assert blood_after == blood_before


def test_corrupt_unknown_malformed_fail_closed_to_blood_a(tmp_path: Path) -> None:
    path = theme.theme_preferences_path(state_dir=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text("{not-json", encoding="utf-8")
    assert _token_map(theme.resolve_theme(state_dir=tmp_path))["accent"] == BLOOD_A_ACCENT

    path.write_text(json.dumps({"selected": "DoesNotExist"}), encoding="utf-8")
    assert _token_map(theme.resolve_theme(state_dir=tmp_path))["accent"] == BLOOD_A_ACCENT

    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "selected": "Broken",
                "custom_themes": {
                    "Broken": {
                        "name": "Broken",
                        "base_preset": "Blood",
                        "accent": "not-a-color",
                        "background": "#050506",
                        "foreground": "#eceef1",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    assert _token_map(theme.resolve_theme(state_dir=tmp_path))["accent"] == BLOOD_A_ACCENT

    path.write_text("null", encoding="utf-8")
    assert _token_map(theme.resolve_theme(state_dir=tmp_path))["accent"] == BLOOD_A_ACCENT

    assert _token_map(theme.resolve_theme("Nope"))["accent"] == BLOOD_A_ACCENT


def test_stored_payload_rejects_absolute_and_private_paths(tmp_path: Path) -> None:
    theme.create_custom_theme(
        name="Safe",
        base_preset="Arctic",
        state_dir=tmp_path,
    )
    theme.save_custom_theme(
        {
            "name": "Safe",
            "base_preset": "Arctic",
            "accent": "#6f9fbf",
            "background": "#050607",
            "foreground": "#e8edf2",
            "absolute_source_path": "C:/Users/secret/samples",
            "private_sample_path": "/home/user/private.wav",
            "path": "D:/Dev/Workspaces/Repos/sample-brain",
        },
        state_dir=tmp_path,
    )
    raw = json.loads(theme.theme_preferences_path(state_dir=tmp_path).read_text(encoding="utf-8"))
    blob = json.dumps(raw)
    assert "C:/Users" not in blob
    assert "/home/user" not in blob
    assert "D:/Dev" not in blob
    assert "absolute_source_path" not in blob
    assert "private_sample_path" not in blob


# --- QML semantic mapping (helper only; no QML edits) -----------------------


def test_theme_tokens_map_to_existing_qml_semantic_names() -> None:
    tokens = _token_map(theme.resolve_theme("Blood"))
    mapped = theme.theme_tokens_to_qml_semantics(tokens)
    assert isinstance(mapped, Mapping)
    for qml_name, source_key in QML_SEMANTIC_EXPECTATIONS.items():
        assert qml_name in mapped
        assert _normalize_hex(mapped[qml_name]) == tokens[source_key]
    assert _normalize_hex(mapped["textOnAction"]) == TEXT_ON_ACTION
    assert "textOnAction" not in tokens  # not a theme base/derived token
    # Mapping is pure: same input → same output; no side effects on presets.
    again = theme.theme_tokens_to_qml_semantics(tokens)
    assert again == mapped
    assert _token_map(theme.resolve_theme("Blood")) == tokens


def test_qml_semantic_map_covers_screen1_facade_without_persisting_text_on_action(
    tmp_path: Path,
) -> None:
    """Handoff gap: Parent QML facade needs hoverSurface + textOnAction from Core."""
    mapped = theme.theme_tokens_to_qml_semantics(theme.resolve_theme("Arctic"))
    assert "hoverSurface" in mapped
    assert _normalize_hex(mapped["hoverSurface"]) == _token_map(theme.resolve_theme("Arctic"))[
        "hover"
    ]
    assert _normalize_hex(mapped["textOnAction"]) == TEXT_ON_ACTION
    assert getattr(theme, "TEXT_ON_ACTION", None) is not None
    assert _normalize_hex(theme.TEXT_ON_ACTION) == TEXT_ON_ACTION

    theme.create_custom_theme(
        name="Arctic Desk",
        base_preset="Arctic",
        state_dir=tmp_path,
    )
    raw = json.loads(theme.theme_preferences_path(state_dir=tmp_path).read_text(encoding="utf-8"))
    stored = raw["custom_themes"]["Arctic Desk"]
    assert "textOnAction" not in stored
    assert "hoverSurface" not in stored
    assert "hover" not in stored
