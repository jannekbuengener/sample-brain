"""Screen-1 Theme Core (#785) + Appearance V2 seam (#1253/#1254).

Preset-based dark appearance tokens with local custom-theme persistence.
Derived tokens are computed from base accent/background/foreground only.
QML consumes mapped semantic colors through the Theme Authority bridge in
``workbench_qml`` — this module remains the #785 derivation/persistence owner.

Appearance V2 state resolution and full semantic token derivation live in
``workbench_appearance`` (#1253). This module owns versioned preference
persistence + v1→v2 migration (#1254). QML projection remains #1255.
Do not persist derived V2 tokens here.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .workbench_controller import workbench_state_dir

THEME_PREFERENCES_SCHEMA = "sample_brain.theme_preferences"
THEME_PREFERENCES_SCHEMA_VERSION = 2
THEME_PREFERENCES_SCHEMA_VERSION_V1 = 1
APPEARANCE_V2_PREFERENCES_EXIT = "APPEARANCE_V2_PREFERENCES_MIGRATED"
_THEME_PREFERENCES_FILENAME = "screen1_theme_preferences.json"

# Internal load statuses — never persisted.
_STATUS_MISSING = "missing"
_STATUS_V1 = "v1"
_STATUS_V2 = "v2"
_STATUS_CORRUPT = "corrupt"
_STATUS_UNSUPPORTED = "unsupported_future"

PRESET_ORDER = ("Blood", "Carbon", "Arctic", "Rose", "Forest")
DEFAULT_PRESET_NAME = "Blood"
BLOOD_A_ACCENT = "#8f0e24"
BLOOD_B_ACCENT = "#d4143a"

_BASE_KEYS = ("accent", "background", "foreground")
_DERIVED_KEYS = (
    "textPrimary",
    "textSecondary",
    "surfaceWorkspace",
    "surface",
    "surfaceRaised",
    "divider",
    "hover",
    "selected",
    "focusRing",
)

_FORBIDDEN_PERSIST_KEYS = frozenset(
    {
        "textPrimary",
        "textSecondary",
        "surfaceWorkspace",
        "surface",
        "surfaceRaised",
        "divider",
        "hover",
        "selected",
        "focusRing",
        "absolute_source_path",
        "private_sample_path",
        "path",
        "absolute_path",
        "machine_path",
    }
)

# Theme Core token → existing QML semantic names (helper only).
# Dark hierarchy: chrome=background, workspace=surfaceWorkspace, panels=surface.
_QML_SEMANTIC_MAP = {
    "surfaceRoot": "surfaceWorkspace",
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
    # #1248 Owner runtime correction: Library focus never follows Accent.
    "libraryFocusRing": "textSecondary",
    "hoverSurface": "hover",
}

# Fixed contrast for solid accent controls — not a persisted base token.
TEXT_ON_ACTION = "#ffffff"


@dataclass(frozen=True)
class ThemeBase:
    accent: str
    background: str
    foreground: str

    def as_dict(self) -> dict[str, str]:
        return {
            "accent": self.accent,
            "background": self.background,
            "foreground": self.foreground,
        }


@dataclass(frozen=True)
class ThemeTokens:
    accent: str
    background: str
    foreground: str
    textPrimary: str
    textSecondary: str
    surfaceWorkspace: str
    surface: str
    surfaceRaised: str
    divider: str
    hover: str
    selected: str
    focusRing: str
    name: str = DEFAULT_PRESET_NAME
    base_preset: str = DEFAULT_PRESET_NAME

    def as_dict(self) -> dict[str, str]:
        return {
            "accent": self.accent,
            "background": self.background,
            "foreground": self.foreground,
            "textPrimary": self.textPrimary,
            "textSecondary": self.textSecondary,
            "surfaceWorkspace": self.surfaceWorkspace,
            "surface": self.surface,
            "surfaceRaised": self.surfaceRaised,
            "divider": self.divider,
            "hover": self.hover,
            "selected": self.selected,
            "focusRing": self.focusRing,
        }


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def presets_canon_path() -> Path:
    return _repo_root() / "docs" / "assets" / "themes" / "presets.v1.json"


def _load_canon() -> dict[str, Any]:
    path = presets_canon_path()
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "presets" not in raw:
        raise ValueError("invalid theme presets canon")
    return raw


def _normalize_hex(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    token = value.strip().lower()
    if not token:
        return None
    if not token.startswith("#"):
        token = f"#{token}"
    if len(token) != 7:
        return None
    body = token[1:]
    try:
        int(body, 16)
    except ValueError:
        return None
    return f"#{body}"


def _parse_rgb(value: str) -> tuple[int, int, int]:
    normalized = _normalize_hex(value)
    if normalized is None:
        raise ValueError(f"invalid hex color: {value!r}")
    body = normalized[1:]
    return int(body[0:2], 16), int(body[2:4], 16), int(body[4:6], 16)


def _format_rgb(r: float, g: float, b: float) -> str:
    def _chan(v: float) -> int:
        # Banker's rounding matches presets.v1.json derived tables (e.g. 132.5 → 132).
        return max(0, min(255, int(round(v))))

    return f"#{_chan(r):02x}{_chan(g):02x}{_chan(b):02x}"


def mix_hex(color_a: str, color_b: str, amount: float) -> str:
    """Linear mix: result = a*(1-t) + b*t (matches presets.v1.json derivation)."""
    t = float(amount)
    ar, ag, ab = _parse_rgb(color_a)
    br, bg, bb = _parse_rgb(color_b)
    return _format_rgb(
        ar * (1.0 - t) + br * t,
        ag * (1.0 - t) + bg * t,
        ab * (1.0 - t) + bb * t,
    )


def _blood_a_base() -> ThemeBase:
    return ThemeBase(
        accent=BLOOD_A_ACCENT,
        # #1205 MagicPath calm near-black canvas: chrome #0b0d10 → workspace #0d0f12.
        background="#0b0d10",
        foreground="#e4e6ea",
    )


def _default_tokens(*, name: str = DEFAULT_PRESET_NAME, base_preset: str = DEFAULT_PRESET_NAME) -> ThemeTokens:
    return _tokens_from_base(_blood_a_base(), name=name, base_preset=base_preset)


def derive_tokens(base: Mapping[str, Any] | ThemeBase) -> dict[str, str]:
    if isinstance(base, ThemeBase):
        payload = base.as_dict()
    else:
        payload = dict(base)
    accent = _normalize_hex(payload.get("accent"))
    background = _normalize_hex(payload.get("background"))
    foreground = _normalize_hex(payload.get("foreground"))
    if accent is None or background is None or foreground is None:
        raise ValueError("invalid theme base tokens")
    return {
        "textPrimary": foreground,
        # Calmer secondary labels (cinematic noir typography restraint).
        "textSecondary": mix_hex(foreground, background, 0.55),
        # Barely raised ink workspace; panels stay subtly above — low UI mass.
        "surfaceWorkspace": mix_hex(background, foreground, 0.008),
        "surface": mix_hex(background, foreground, 0.028),
        "surfaceRaised": mix_hex(background, foreground, 0.06),
        "divider": mix_hex(background, foreground, 0.10),
        "hover": mix_hex(background, foreground, 0.075),
        "selected": mix_hex(background, accent, 0.22),
        "focusRing": accent,
    }


def _tokens_from_base(
    base: ThemeBase,
    *,
    name: str,
    base_preset: str,
) -> ThemeTokens:
    derived = derive_tokens(base)
    return ThemeTokens(
        accent=base.accent,
        background=base.background,
        foreground=base.foreground,
        textPrimary=derived["textPrimary"],
        textSecondary=derived["textSecondary"],
        surfaceWorkspace=derived["surfaceWorkspace"],
        surface=derived["surface"],
        surfaceRaised=derived["surfaceRaised"],
        divider=derived["divider"],
        hover=derived["hover"],
        selected=derived["selected"],
        focusRing=derived["focusRing"],
        name=name,
        base_preset=base_preset,
    )


def _base_from_preset_entry(entry: Mapping[str, Any]) -> ThemeBase | None:
    raw = entry.get("base")
    if not isinstance(raw, Mapping):
        return None
    accent = _normalize_hex(raw.get("accent"))
    background = _normalize_hex(raw.get("background"))
    foreground = _normalize_hex(raw.get("foreground"))
    if accent is None or background is None or foreground is None:
        return None
    return ThemeBase(accent=accent, background=background, foreground=foreground)


def list_presets() -> tuple[str, ...]:
    canon = _load_canon()
    names = tuple(str(name) for name in canon["presets"].keys())
    if names != PRESET_ORDER:
        # Canon is authoritative for values; order is frozen by product contract.
        ordered = tuple(name for name in PRESET_ORDER if name in canon["presets"])
        extras = tuple(name for name in names if name not in PRESET_ORDER)
        return ordered + extras
    return names


def default_preset_name() -> str:
    return DEFAULT_PRESET_NAME


def blood_variants() -> dict[str, dict[str, str]]:
    canon = _load_canon()
    blood = canon["presets"].get("Blood") or {}
    variants_raw = blood.get("blood_variants") or {}
    out: dict[str, dict[str, str]] = {}
    if isinstance(variants_raw, Mapping):
        for key, entry in variants_raw.items():
            if not isinstance(entry, Mapping):
                continue
            base = _base_from_preset_entry(entry)
            if base is None:
                continue
            out[str(key)] = base.as_dict()
    if "A" not in out:
        out["A"] = _blood_a_base().as_dict()
    if "B" not in out:
        out["B"] = ThemeBase(
            accent=BLOOD_B_ACCENT,
            background="#0b0d10",
            foreground="#e4e6ea",
        ).as_dict()
    return out


def theme_preferences_path(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    base = state_dir if state_dir is not None else workbench_state_dir(env=env)
    return Path(base) / _THEME_PREFERENCES_FILENAME


def _empty_store() -> dict[str, Any]:
    return {
        "schema": THEME_PREFERENCES_SCHEMA,
        "schema_version": THEME_PREFERENCES_SCHEMA_VERSION,
        "selected": DEFAULT_PRESET_NAME,
        "custom_themes": {},
        "appearance": _default_appearance_payload(selected=DEFAULT_PRESET_NAME),
        "_status": _STATUS_MISSING,
        "_writable": True,
    }


def _looks_like_filesystem_path(value: str) -> bool:
    if "://" in value and not value.startswith("root:"):
        return True
    if len(value) >= 3 and value[1] == ":" and value[2] in {"/", "\\"}:
        return True
    if value.startswith("\\\\") or value.startswith("/Users/") or value.startswith("/home/"):
        return True
    if value.startswith("D:/Dev") or value.startswith("C:/Users"):
        return True
    return False


def _sanitize_custom_entry(payload: Mapping[str, Any]) -> dict[str, str] | None:
    name = payload.get("name")
    base_preset = payload.get("base_preset")
    if not isinstance(name, str) or not name.strip():
        return None
    if not isinstance(base_preset, str) or base_preset not in PRESET_ORDER:
        return None
    accent = _normalize_hex(payload.get("accent"))
    background = _normalize_hex(payload.get("background"))
    foreground = _normalize_hex(payload.get("foreground"))
    if accent is None or background is None or foreground is None:
        return None
    cleaned_name = name.strip()
    if _looks_like_filesystem_path(cleaned_name):
        return None
    return {
        "name": cleaned_name,
        "base_preset": base_preset,
        "accent": accent,
        "background": background,
        "foreground": foreground,
    }


def _sanitize_customs(raw: Any) -> dict[str, dict[str, str]]:
    customs: dict[str, dict[str, str]] = {}
    if not isinstance(raw, Mapping):
        return customs
    for key, entry in raw.items():
        if not isinstance(key, str) or not isinstance(entry, Mapping):
            continue
        sanitized = _sanitize_custom_entry({**dict(entry), "name": entry.get("name", key)})
        if sanitized is None:
            continue
        for forbidden in _FORBIDDEN_PERSIST_KEYS:
            sanitized.pop(forbidden, None)
        customs[sanitized["name"]] = sanitized
    return customs


def _normalize_selected(selected: Any, customs: Mapping[str, Any]) -> str:
    if not isinstance(selected, str) or not selected.strip():
        return DEFAULT_PRESET_NAME
    cleaned = selected.strip()
    if cleaned in PRESET_ORDER or cleaned in customs:
        return cleaned
    return DEFAULT_PRESET_NAME


def _default_appearance_payload(*, selected: str) -> dict[str, Any]:
    return {
        "mode": "dark",
        "separateLightDark": False,
        "selectedTheme": selected,
        "uiFontSize": 14,
        "codeFontSize": 12,
        "motionMode": "on",
        "profiles": {
            "shared": {
                "themeRef": selected,
                "contrast": 50,
            }
        },
    }


def _profile_to_payload(profile: Any) -> dict[str, Any] | None:
    from .workbench_appearance import AppearanceProfileInput

    if not isinstance(profile, AppearanceProfileInput):
        return None
    out: dict[str, Any] = {}
    if isinstance(profile.theme_ref, str) and profile.theme_ref.strip():
        out["themeRef"] = profile.theme_ref.strip()
    for key, attr in (
        ("background", profile.background),
        ("foreground", profile.foreground),
        ("accent", profile.accent),
    ):
        normalized = _normalize_hex(attr) if isinstance(attr, str) else None
        if normalized is not None:
            out[key] = normalized
    if type(profile.contrast) is int:
        out["contrast"] = profile.contrast
    return out or None


def _appearance_payload_from_requested(
    requested: Any,
    *,
    selected: str,
) -> dict[str, Any]:
    from .workbench_appearance import AppearanceRequestedState

    if not isinstance(requested, AppearanceRequestedState):
        return _default_appearance_payload(selected=selected)

    profiles: dict[str, Any] = {}
    for name, profile in (
        ("shared", requested.shared),
        ("dark", requested.dark),
        ("light", requested.light),
    ):
        payload = _profile_to_payload(profile)
        if payload is not None:
            profiles[name] = payload
    if not profiles:
        profiles["shared"] = {"themeRef": selected, "contrast": 50}

    selected_theme = selected
    if requested.separate_light_dark:
        for candidate in (requested.dark, requested.light, requested.shared):
            if (
                candidate is not None
                and isinstance(candidate.theme_ref, str)
                and candidate.theme_ref.strip()
            ):
                selected_theme = candidate.theme_ref.strip()
                break
    elif requested.shared is not None and isinstance(requested.shared.theme_ref, str):
        cleaned = requested.shared.theme_ref.strip()
        if cleaned:
            selected_theme = cleaned

    return {
        "mode": requested.mode,
        "separateLightDark": bool(requested.separate_light_dark),
        "selectedTheme": selected_theme,
        "uiFontSize": requested.ui_font_size,
        "codeFontSize": requested.code_font_size,
        "motionMode": requested.motion_mode,
        "profiles": profiles,
    }


def _appearance_mapping_from_store_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Flatten persisted appearance section into appearance_requested_from_mapping shape."""
    profiles = payload.get("profiles")
    shared = payload.get("shared")
    dark = payload.get("dark")
    light = payload.get("light")
    if isinstance(profiles, Mapping):
        shared = profiles.get("shared", shared)
        dark = profiles.get("dark", dark)
        light = profiles.get("light", light)
    return {
        "mode": payload.get("mode"),
        "separateLightDark": payload.get("separateLightDark", False),
        "uiFontSize": payload.get("uiFontSize"),
        "codeFontSize": payload.get("codeFontSize"),
        "motionMode": payload.get("motionMode"),
        "shared": shared,
        "dark": dark,
        "light": light,
    }


def _seed_motion_from_display(
    *,
    state_dir: Path | None,
    env: Mapping[str, str] | None,
) -> str:
    try:
        from .workbench_display_preferences import load_display_preferences

        prefs = load_display_preferences(state_dir=state_dir, env=env)
        mode = str(getattr(prefs, "motion_mode", "on") or "on").strip().lower()
        if mode in {"on", "reduced", "off"}:
            return mode
    except Exception:
        pass
    return "on"


def _reconcile_motion_mode(
    stored: Any,
    *,
    state_dir: Path | None,
    env: Mapping[str, str] | None,
) -> str:
    """Keep Appearance motion aligned with #696 for concrete values.

    ``system`` stays Appearance-owned (display prefs cannot express it).
    When a concrete display-preferences file exists, that owner wins for
    ``on|reduced|off`` so a later #696/QML motion change is not undone by an
    Appearance reload/save. Missing display prefs leave the Appearance value.
    """
    token = str(stored or "").strip().lower()
    if token == "system":
        return "system"
    try:
        from .workbench_display_preferences import (
            display_preferences_path,
            load_display_preferences,
        )

        if display_preferences_path(state_dir=state_dir, env=env).is_file():
            prefs = load_display_preferences(state_dir=state_dir, env=env)
            display_motion = str(getattr(prefs, "motion_mode", "") or "").strip().lower()
            if display_motion in {"on", "reduced", "off"}:
                return display_motion
    except Exception:
        pass
    if token in {"on", "reduced", "off"}:
        return token
    return _seed_motion_from_display(state_dir=state_dir, env=env)


def _sync_motion_to_display(
    motion_mode: str,
    *,
    state_dir: Path | None,
    env: Mapping[str, str] | None,
) -> None:
    """Keep #696 display prefs aligned for concrete motion values (not system)."""
    token = str(motion_mode or "").strip().lower()
    if token not in {"on", "reduced", "off"}:
        return
    try:
        from .workbench_display_preferences import (
            load_display_preferences,
            save_display_preferences,
        )

        current = load_display_preferences(state_dir=state_dir, env=env)
        save_display_preferences(
            {
                "density_mode": current.density_mode,
                "motion_mode": token,
            },
            state_dir=state_dir,
            env=env,
        )
    except Exception:
        # Cosmetic sync must never block Appearance persistence.
        return


def _migrate_v1_to_v2(
    raw: Mapping[str, Any],
    *,
    state_dir: Path | None,
    env: Mapping[str, str] | None,
) -> dict[str, Any]:
    customs = _sanitize_customs(raw.get("custom_themes"))
    selected = _normalize_selected(raw.get("selected"), customs)
    shared: dict[str, Any] = {"themeRef": selected, "contrast": 50}
    if selected in customs:
        entry = customs[selected]
        shared = {
            "themeRef": selected,
            "accent": entry["accent"],
            "background": entry["background"],
            "foreground": entry["foreground"],
            "contrast": 50,
        }
    appearance_payload = {
        "mode": "dark",
        "separateLightDark": False,
        "selectedTheme": selected,
        "uiFontSize": 14,
        "codeFontSize": 12,
        "motionMode": _seed_motion_from_display(state_dir=state_dir, env=env),
        "profiles": {"shared": shared},
    }
    return {
        "schema": THEME_PREFERENCES_SCHEMA,
        "schema_version": THEME_PREFERENCES_SCHEMA_VERSION,
        "selected": selected,
        "custom_themes": customs,
        "appearance": appearance_payload,
        "_status": _STATUS_V1,
        "_writable": True,
    }


def _parse_v2_store(
    raw: Mapping[str, Any],
    *,
    state_dir: Path | None,
    env: Mapping[str, str] | None,
) -> dict[str, Any]:
    customs = _sanitize_customs(raw.get("custom_themes"))
    appearance_raw = raw.get("appearance")
    if not isinstance(appearance_raw, Mapping):
        appearance_raw = {}
    selected_theme = appearance_raw.get("selectedTheme", raw.get("selected", DEFAULT_PRESET_NAME))
    selected = _normalize_selected(selected_theme, customs)
    if "selected" in raw:
        selected = _normalize_selected(raw.get("selected"), customs)

    mapping = _appearance_mapping_from_store_payload(appearance_raw)
    mapping["motionMode"] = _reconcile_motion_mode(
        mapping.get("motionMode"),
        state_dir=state_dir,
        env=env,
    )

    # Ensure themeRef mirrors selected when profiles omit it.
    profiles = appearance_raw.get("profiles")
    if not isinstance(profiles, Mapping) or not profiles:
        shared = mapping.get("shared")
        if not isinstance(shared, Mapping) or not shared.get("themeRef"):
            mapping["shared"] = {
                "themeRef": selected,
                "contrast": 50,
                **(dict(shared) if isinstance(shared, Mapping) else {}),
            }

    from .workbench_appearance import appearance_requested_from_mapping

    requested = appearance_requested_from_mapping(mapping)
    appearance_payload = _appearance_payload_from_requested(requested, selected=selected)
    # Preserve selectedTheme from disk when valid.
    if isinstance(selected_theme, str) and selected_theme.strip():
        cleaned = selected_theme.strip()
        if cleaned in PRESET_ORDER or cleaned in customs:
            appearance_payload["selectedTheme"] = cleaned
            selected = cleaned

    return {
        "schema": THEME_PREFERENCES_SCHEMA,
        "schema_version": THEME_PREFERENCES_SCHEMA_VERSION,
        "selected": selected,
        "custom_themes": customs,
        "appearance": appearance_payload,
        "_status": _STATUS_V2,
        "_writable": True,
    }


def _read_store(*, state_dir: Path | None, env: Mapping[str, str] | None) -> dict[str, Any]:
    path = theme_preferences_path(state_dir=state_dir, env=env)
    if not path.is_file():
        return _empty_store()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        store = _empty_store()
        store["_status"] = _STATUS_CORRUPT
        # Explicit saves may replace corrupt JSON; load must not auto-rewrite.
        store["_writable"] = True
        store["_preserve_on_load"] = True
        return store
    if not isinstance(raw, dict):
        store = _empty_store()
        store["_status"] = _STATUS_CORRUPT
        store["_writable"] = True
        store["_preserve_on_load"] = True
        return store

    version = raw.get("schema_version")
    if type(version) is not int:
        store = _empty_store()
        store["_status"] = _STATUS_CORRUPT
        store["_writable"] = True
        store["_preserve_on_load"] = True
        return store
    if version > THEME_PREFERENCES_SCHEMA_VERSION:
        store = _empty_store()
        store["_status"] = _STATUS_UNSUPPORTED
        store["_writable"] = False
        return store
    if version == THEME_PREFERENCES_SCHEMA_VERSION_V1:
        migrated = _migrate_v1_to_v2(raw, state_dir=state_dir, env=env)
        # Persist migrated V2 when source is writable (deterministic upgrade).
        _write_store(migrated, state_dir=state_dir, env=env)
        return migrated
    if version != THEME_PREFERENCES_SCHEMA_VERSION:
        # Older/unknown below current that is not v1 → fail closed.
        store = _empty_store()
        store["_status"] = _STATUS_CORRUPT
        store["_writable"] = True
        store["_preserve_on_load"] = True
        return store
    return _parse_v2_store(raw, state_dir=state_dir, env=env)


def _atomic_write_json(path: Path, body: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(body, indent=2, sort_keys=True, allow_nan=False) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _apply_selection_to_profile(
    profile: Mapping[str, Any] | None,
    selected: str,
    customs: Any,
) -> dict[str, Any]:
    """Copy a profile and point it at ``selected``, materializing custom colors."""
    out = dict(profile or {})
    out["themeRef"] = selected
    if isinstance(customs, Mapping) and selected in customs:
        entry = customs[selected]
        if isinstance(entry, Mapping):
            for key in ("accent", "background", "foreground"):
                value = _normalize_hex(entry.get(key))
                if value is not None:
                    out[key] = value
    else:
        for key in ("accent", "background", "foreground"):
            out.pop(key, None)
    out.setdefault("contrast", 50)
    return out


def _sync_appearance_selection(store: dict[str, Any], selected: str) -> None:
    """Keep Appearance intent aligned with #785 selected/custom theme changes."""
    appearance = store.get("appearance")
    if not isinstance(appearance, Mapping):
        appearance = _default_appearance_payload(selected=selected)
    else:
        appearance = dict(appearance)
    appearance["selectedTheme"] = selected
    profiles = appearance.get("profiles")
    if not isinstance(profiles, Mapping):
        profiles = {}
    else:
        profiles = dict(profiles)
    customs = store.get("custom_themes") or {}
    profiles["shared"] = _apply_selection_to_profile(
        profiles.get("shared"), selected, customs
    )
    # When Light/Dark are separated, resolve_appearance ignores shared — update
    # the active scheme profile and leave the inactive one untouched.
    if bool(appearance.get("separateLightDark")):
        mode = str(appearance.get("mode") or "dark").strip().lower()
        # Fail-closed: system (and unknown) map to dark, matching #1253 defaults.
        active_key = "light" if mode == "light" else "dark"
        profiles[active_key] = _apply_selection_to_profile(
            profiles.get(active_key), selected, customs
        )
    appearance["profiles"] = profiles
    store["appearance"] = appearance


def _hydrate_profile_custom_colors(
    profile: Any,
    customs: Mapping[str, Any],
) -> Any:
    """Fill missing BG/FG/Accent from a named custom themeRef; keep explicit overrides."""
    if not isinstance(profile, Mapping):
        return profile
    out = dict(profile)
    ref = out.get("themeRef")
    if not isinstance(ref, str) or not ref.strip():
        return out
    cleaned = ref.strip()
    if cleaned not in customs:
        return out
    entry = customs[cleaned]
    if not isinstance(entry, Mapping):
        return out
    for key in ("accent", "background", "foreground"):
        if out.get(key) is not None:
            continue
        value = _normalize_hex(entry.get(key))
        if value is not None:
            out[key] = value
    return out


def _hydrate_appearance_custom_colors(
    mapping: dict[str, Any],
    customs: Mapping[str, Any],
) -> dict[str, Any]:
    """Materialize named custom palettes into Appearance profiles on load."""
    hydrated = dict(mapping)
    for key in ("shared", "dark", "light"):
        hydrated[key] = _hydrate_profile_custom_colors(hydrated.get(key), customs)
    return hydrated


def _write_store(
    store: Mapping[str, Any],
    *,
    state_dir: Path | None,
    env: Mapping[str, str] | None,
) -> Path | None:
    if store.get("_writable") is False:
        return None
    path = theme_preferences_path(state_dir=state_dir, env=env)
    # Re-check live disk for unsupported future schema before overwrite.
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            existing = None
        if isinstance(existing, dict):
            version = existing.get("schema_version")
            if type(version) is int and version > THEME_PREFERENCES_SCHEMA_VERSION:
                return None

    selected = _normalize_selected(store.get("selected"), store.get("custom_themes") or {})
    cleaned_customs = _sanitize_customs(store.get("custom_themes"))
    appearance = store.get("appearance")
    if not isinstance(appearance, Mapping):
        appearance = _default_appearance_payload(selected=selected)
    else:
        appearance = dict(appearance)
        appearance["selectedTheme"] = appearance.get("selectedTheme") or selected
        # Drop any derived-token leakage from appearance payloads.
        for forbidden in _FORBIDDEN_PERSIST_KEYS:
            appearance.pop(forbidden, None)
        profiles = appearance.get("profiles")
        if isinstance(profiles, Mapping):
            cleaned_profiles: dict[str, Any] = {}
            for name, entry in profiles.items():
                if not isinstance(entry, Mapping):
                    continue
                cleaned_entry = {
                    key: value
                    for key, value in dict(entry).items()
                    if key in {"themeRef", "background", "foreground", "accent", "contrast"}
                }
                if "background" in cleaned_entry:
                    cleaned_entry["background"] = _normalize_hex(cleaned_entry["background"])
                if "foreground" in cleaned_entry:
                    cleaned_entry["foreground"] = _normalize_hex(cleaned_entry["foreground"])
                if "accent" in cleaned_entry:
                    cleaned_entry["accent"] = _normalize_hex(cleaned_entry["accent"])
                for color_key in ("background", "foreground", "accent"):
                    if cleaned_entry.get(color_key) is None:
                        cleaned_entry.pop(color_key, None)
                cleaned_profiles[str(name)] = cleaned_entry
            appearance["profiles"] = cleaned_profiles

    body = {
        "schema": THEME_PREFERENCES_SCHEMA,
        "schema_version": THEME_PREFERENCES_SCHEMA_VERSION,
        "selected": selected,
        "custom_themes": cleaned_customs,
        "appearance": appearance,
    }
    try:
        _atomic_write_json(path, body)
    except OSError:
        return None
    return path


def _require_write(
    store: Mapping[str, Any],
    *,
    state_dir: Path | None,
    env: Mapping[str, str] | None,
) -> Path:
    path = _write_store(store, state_dir=state_dir, env=env)
    if path is None:
        raise OSError("theme preferences write refused or failed")
    return path


def load_appearance_preferences(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Any:
    """Load versioned Appearance user intent (#1254). Never raises for cosmetic faults."""
    from .workbench_appearance import (
        AppearanceRequestedState,
        appearance_requested_from_mapping,
    )

    store = _read_store(state_dir=state_dir, env=env)
    status = store.get("_status")
    if status in {_STATUS_MISSING, _STATUS_CORRUPT, _STATUS_UNSUPPORTED}:
        return AppearanceRequestedState()
    appearance_payload = store.get("appearance")
    if not isinstance(appearance_payload, Mapping):
        return AppearanceRequestedState()
    customs = store.get("custom_themes") or {}
    if not isinstance(customs, Mapping):
        customs = {}
    mapping = _hydrate_appearance_custom_colors(
        _appearance_mapping_from_store_payload(appearance_payload),
        customs,
    )
    return appearance_requested_from_mapping(mapping)


def save_appearance_preferences(
    requested: Any,
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path | None:
    """Persist Appearance user intent only. Returns None when the write is refused."""
    from .workbench_appearance import AppearanceRequestedState, appearance_requested_from_mapping

    if not isinstance(requested, AppearanceRequestedState):
        requested = AppearanceRequestedState()
    # Canonical normalize through the same #1253 adapter used on load.
    requested = appearance_requested_from_mapping(
        {
            "mode": requested.mode,
            "separateLightDark": requested.separate_light_dark,
            "uiFontSize": requested.ui_font_size,
            "codeFontSize": requested.code_font_size,
            "motionMode": requested.motion_mode,
            "shared": _profile_to_payload(requested.shared),
            "dark": _profile_to_payload(requested.dark),
            "light": _profile_to_payload(requested.light),
        }
    )

    store = _read_store(state_dir=state_dir, env=env)
    if store.get("_writable") is False:
        return None

    selected = DEFAULT_PRESET_NAME
    if requested.separate_light_dark:
        for candidate in (requested.dark, requested.light, requested.shared):
            if candidate is not None and isinstance(candidate.theme_ref, str) and candidate.theme_ref.strip():
                selected = candidate.theme_ref.strip()
                break
    elif requested.shared is not None and isinstance(requested.shared.theme_ref, str):
        cleaned = requested.shared.theme_ref.strip()
        if cleaned:
            selected = cleaned
    customs = dict(store.get("custom_themes") or {})
    selected = _normalize_selected(selected, customs)
    store["selected"] = selected
    store["custom_themes"] = customs
    store["appearance"] = _appearance_payload_from_requested(requested, selected=selected)
    path = _write_store(store, state_dir=state_dir, env=env)
    if path is not None:
        _sync_motion_to_display(requested.motion_mode, state_dir=state_dir, env=env)
    return path


def _preset_base(name: str) -> ThemeBase | None:
    if name not in PRESET_ORDER:
        return None
    try:
        canon = _load_canon()
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    entry = canon.get("presets", {}).get(name)
    if not isinstance(entry, Mapping):
        return None
    return _base_from_preset_entry(entry)


def resolve_theme(
    name: str | None = None,
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> ThemeTokens:
    """Resolve a preset, custom theme, or active selection. Fail-closed to Blood A."""
    store = _read_store(state_dir=state_dir, env=env)
    target = name if name is not None else str(store.get("selected") or DEFAULT_PRESET_NAME)

    if target in PRESET_ORDER:
        base = _preset_base(target)
        if base is None:
            return _default_tokens()
        # Blood always resolves to stage A primary_candidate base from canon.
        return _tokens_from_base(base, name=target, base_preset=target)

    customs = store.get("custom_themes") or {}
    if isinstance(customs, Mapping) and target in customs:
        entry = customs[target]
        sanitized = _sanitize_custom_entry(entry) if isinstance(entry, Mapping) else None
        if sanitized is None:
            return _default_tokens()
        base = ThemeBase(
            accent=sanitized["accent"],
            background=sanitized["background"],
            foreground=sanitized["foreground"],
        )
        return _tokens_from_base(
            base,
            name=sanitized["name"],
            base_preset=sanitized["base_preset"],
        )

    return _default_tokens()


def list_custom_themes(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> list[str]:
    store = _read_store(state_dir=state_dir, env=env)
    customs = store.get("custom_themes") or {}
    if not isinstance(customs, Mapping):
        return []
    return sorted(str(name) for name in customs.keys())


def create_custom_theme(
    *,
    name: str,
    base_preset: str,
    accent: str | None = None,
    background: str | None = None,
    foreground: str | None = None,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> ThemeTokens:
    if base_preset not in PRESET_ORDER:
        raise ValueError(f"unknown base preset: {base_preset!r}")
    cleaned_name = str(name).strip()
    if not cleaned_name or _looks_like_filesystem_path(cleaned_name):
        raise ValueError("invalid custom theme name")
    if cleaned_name in PRESET_ORDER:
        raise ValueError("custom theme name collides with preset")

    preset_base = _preset_base(base_preset)
    if preset_base is None:
        preset_base = _blood_a_base()
        base_preset = DEFAULT_PRESET_NAME

    resolved_accent = _normalize_hex(accent) if accent is not None else preset_base.accent
    resolved_background = (
        _normalize_hex(background) if background is not None else preset_base.background
    )
    resolved_foreground = (
        _normalize_hex(foreground) if foreground is not None else preset_base.foreground
    )
    if resolved_accent is None or resolved_background is None or resolved_foreground is None:
        raise ValueError("invalid custom theme base colors")

    store = _read_store(state_dir=state_dir, env=env)
    customs = dict(store.get("custom_themes") or {})
    customs[cleaned_name] = {
        "name": cleaned_name,
        "base_preset": base_preset,
        "accent": resolved_accent,
        "background": resolved_background,
        "foreground": resolved_foreground,
    }
    store["custom_themes"] = customs
    if store.get("selected") == cleaned_name:
        _sync_appearance_selection(store, cleaned_name)
    _require_write(store, state_dir=state_dir, env=env)
    return resolve_theme(cleaned_name, state_dir=state_dir, env=env)


def save_custom_theme(
    payload: Mapping[str, Any],
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    sanitized = _sanitize_custom_entry(payload)
    if sanitized is None:
        raise ValueError("invalid custom theme payload")
    if sanitized["name"] in PRESET_ORDER:
        raise ValueError("cannot overwrite built-in preset")
    store = _read_store(state_dir=state_dir, env=env)
    customs = dict(store.get("custom_themes") or {})
    # Drop forbidden / derived keys by reconstruction only.
    customs[sanitized["name"]] = sanitized
    store["custom_themes"] = customs
    if store.get("selected") == sanitized["name"]:
        _sync_appearance_selection(store, sanitized["name"])
    return _require_write(store, state_dir=state_dir, env=env)


def rename_custom_theme(
    old_name: str,
    new_name: str,
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> None:
    store = _read_store(state_dir=state_dir, env=env)
    customs = dict(store.get("custom_themes") or {})
    if old_name not in customs:
        raise ValueError(f"unknown custom theme: {old_name!r}")
    cleaned_new = str(new_name).strip()
    if not cleaned_new or _looks_like_filesystem_path(cleaned_new):
        raise ValueError("invalid custom theme name")
    if cleaned_new in PRESET_ORDER:
        raise ValueError("custom theme name collides with preset")
    if cleaned_new in customs and cleaned_new != old_name:
        raise ValueError(f"custom theme already exists: {cleaned_new!r}")
    entry = dict(customs.pop(old_name))
    entry["name"] = cleaned_new
    customs[cleaned_new] = entry
    store["custom_themes"] = customs
    if store.get("selected") == old_name:
        store["selected"] = cleaned_new
        _sync_appearance_selection(store, cleaned_new)
    _require_write(store, state_dir=state_dir, env=env)


def select_theme(
    name: str,
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> ThemeTokens:
    store = _read_store(state_dir=state_dir, env=env)
    customs = store.get("custom_themes") or {}
    if name not in PRESET_ORDER and not (isinstance(customs, Mapping) and name in customs):
        # Fail closed: keep Blood selected.
        store["selected"] = DEFAULT_PRESET_NAME
        _sync_appearance_selection(store, DEFAULT_PRESET_NAME)
        _require_write(store, state_dir=state_dir, env=env)
        return resolve_theme(DEFAULT_PRESET_NAME, state_dir=state_dir, env=env)
    store["selected"] = name
    _sync_appearance_selection(store, name)
    _require_write(store, state_dir=state_dir, env=env)
    return resolve_theme(name, state_dir=state_dir, env=env)


def delete_custom_theme(
    name: str,
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> None:
    if name in PRESET_ORDER:
        raise ValueError("cannot delete built-in preset")
    store = _read_store(state_dir=state_dir, env=env)
    customs = dict(store.get("custom_themes") or {})
    customs.pop(name, None)
    if store.get("selected") == name:
        store["selected"] = DEFAULT_PRESET_NAME
        _sync_appearance_selection(store, DEFAULT_PRESET_NAME)
    store["custom_themes"] = customs
    _require_write(store, state_dir=state_dir, env=env)


def reset_custom_theme(
    name: str,
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> ThemeTokens:
    store = _read_store(state_dir=state_dir, env=env)
    customs = dict(store.get("custom_themes") or {})
    if name not in customs:
        raise ValueError(f"unknown custom theme: {name!r}")
    entry = customs[name]
    base_preset = str(entry.get("base_preset") or DEFAULT_PRESET_NAME)
    preset_base = _preset_base(base_preset) or _blood_a_base()
    customs[name] = {
        "name": name,
        "base_preset": base_preset if base_preset in PRESET_ORDER else DEFAULT_PRESET_NAME,
        "accent": preset_base.accent,
        "background": preset_base.background,
        "foreground": preset_base.foreground,
    }
    store["custom_themes"] = customs
    if store.get("selected") == name:
        _sync_appearance_selection(store, name)
    _require_write(store, state_dir=state_dir, env=env)
    return resolve_theme(name, state_dir=state_dir, env=env)


def theme_tokens_to_qml_semantics(tokens: Mapping[str, Any] | ThemeTokens) -> dict[str, str]:
    """Pure mapping from Theme Core tokens to existing QML semantic color names."""
    if isinstance(tokens, ThemeTokens):
        source = tokens.as_dict()
    else:
        source = {str(k): str(v) for k, v in tokens.items()}
    out: dict[str, str] = {}
    for qml_name, token_key in _QML_SEMANTIC_MAP.items():
        value = source.get(token_key)
        normalized = _normalize_hex(value) if value is not None else None
        if normalized is None:
            continue
        out[qml_name] = normalized
    # #1248: Library-only semantic seam, no persisted/derived schema expansion.
    # Per-channel fractions project the approved #15171a reference between the
    # current Blood chrome (#0b0d10, #1205) and foreground (#e4e6ea).
    # Other presets/custom bases retain that relative surface hierarchy.
    background = _normalize_hex(source.get("background"))
    foreground = _normalize_hex(source.get("foreground"))
    if background and foreground:
        fractions = (10 / 217, 10 / 217, 10 / 218)
        channels = []
        for offset, fraction in zip((1, 3, 5), fractions):
            low = int(background[offset:offset + 2], 16)
            high = int(foreground[offset:offset + 2], 16)
            channels.append(round(low + (high - low) * fraction))
        out["surfaceLibrary"] = "#" + "".join(f"{value:02x}" for value in channels)
    out.update({
        "libraryAllSamplesAccent": "#93a8b8",
        "libraryCollectionsAccent": "#aa9e7b",
        "libraryFavoritesAccent": "#ad6267",
        "libraryRecordsAccent": "#9c91ae",
    })
    out.setdefault("textOnAction", TEXT_ON_ACTION)
    return out


APPEARANCE_V2_QML_BRIDGE_EXIT = "APPEARANCE_V2_QML_BRIDGE_LIVE"
SCREEN1_APPEARANCE_V2_TOKENIZED_EXIT = "SCREEN1_APPEARANCE_V2_TOKENIZED"

# #1257: overlay true V2 roles onto the #785 camelCase facade. Keeps legacy
# surface/text/accent compat names while correcting aliases that blocked
# protected status, muted/disabled text, and interaction pressed semantics.
_V2_SEMANTIC_OVERLAY_KEYS: tuple[tuple[str, str], ...] = (
    ("textDisabled", "text.disabled"),
    ("textMuted", "text.muted"),
    ("textOnAction", "accent.onAccent"),
    ("statusError", "status.error"),
    ("statusWarning", "status.warning"),
    ("statusSuccess", "status.success"),
    ("statusInfo", "status.info"),
    ("accentHover", "accent.hover"),
    ("accentActive", "accent.active"),
    ("accentSubtle", "accent.subtle"),
    ("interactionPressed", "interaction.pressed"),
    ("interactionDisabled", "interaction.disabled"),
    ("interactionSelection", "interaction.selection"),
    ("borderDefault", "border.default"),
    ("borderStrong", "border.strong"),
)


def project_appearance_snapshot_for_qml(snapshot: Any) -> dict[str, Any]:
    """Project an AppearanceResolvedSnapshot into one renderer-facing payload (#1255/#1257).

    Returns a coherent dict with #785 compatibility semantics plus exact V2
    flat token keys. Callers must swap the whole payload atomically.
    """
    from . import workbench_appearance as appearance_mod

    if not isinstance(snapshot, appearance_mod.AppearanceResolvedSnapshot):
        raise TypeError("snapshot must be AppearanceResolvedSnapshot")

    legacy = snapshot.legacy_theme_tokens()
    semantics = theme_tokens_to_qml_semantics(legacy)
    # Prefer authoritative protected highlights from the V2 snapshot.
    for key, value in snapshot.tokens.protected_highlight.items():
        normalized = _normalize_hex(value)
        if normalized is not None:
            semantics[str(key)] = normalized

    flat_tokens = dict(snapshot.tokens.as_flat_dict())
    # #1257 Screen-1 adoption: project true V2 roles into the facade.
    for qml_name, token_key in _V2_SEMANTIC_OVERLAY_KEYS:
        normalized = _normalize_hex(flat_tokens.get(token_key))
        if normalized is not None:
            semantics[qml_name] = normalized

    return {
        "legacy_tokens": legacy,
        "semantics": semantics,
        "tokens": flat_tokens,
        "theme_ref": snapshot.theme_ref,
        "mode_requested": snapshot.mode_requested,
        "resolved_scheme": snapshot.resolved_scheme,
        "separate_light_dark": bool(snapshot.separate_light_dark),
        "background": snapshot.background,
        "foreground": snapshot.foreground,
        "accent": snapshot.accent,
        "contrast": int(snapshot.contrast),
        "ui_font_size": int(snapshot.ui_font_size),
        "code_font_size": int(snapshot.code_font_size),
        "motion_mode_requested": snapshot.motion_mode_requested,
        "motion_effective": snapshot.motion_effective,
        "window_chrome_background": snapshot.tokens.window_chrome_background,
        "window_chrome_foreground": snapshot.tokens.window_chrome_foreground,
        "window_chrome_border": snapshot.tokens.window_chrome_border,
        "typography_ui_standard_size": float(snapshot.typography.ui.standard.font_size),
        "typography_code_size": float(snapshot.typography.code.font_size),
        "typography": snapshot.typography,
    }


_APPEARANCE_V2_EXPORTS = frozenset(
    {
        "APPEARANCE_V2_EXIT",
        "AppearanceProfileInput",
        "AppearanceRequestedState",
        "AppearanceResolvedSnapshot",
        "derive_semantic_tokens",
        "resolve_appearance",
    }
)


def __getattr__(name: str) -> Any:
    """Lazy Appearance V2 seam — avoids import cycles with workbench_appearance."""
    if name in _APPEARANCE_V2_EXPORTS:
        from . import workbench_appearance as _appearance

        return getattr(_appearance, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "APPEARANCE_V2_EXIT",
    "APPEARANCE_V2_PREFERENCES_EXIT",
    "APPEARANCE_V2_QML_BRIDGE_EXIT",
    "SCREEN1_APPEARANCE_V2_TOKENIZED_EXIT",
    "AppearanceProfileInput",
    "AppearanceRequestedState",
    "AppearanceResolvedSnapshot",
    "BLOOD_A_ACCENT",
    "BLOOD_B_ACCENT",
    "DEFAULT_PRESET_NAME",
    "PRESET_ORDER",
    "TEXT_ON_ACTION",
    "THEME_PREFERENCES_SCHEMA",
    "THEME_PREFERENCES_SCHEMA_VERSION",
    "THEME_PREFERENCES_SCHEMA_VERSION_V1",
    "ThemeBase",
    "ThemeTokens",
    "blood_variants",
    "create_custom_theme",
    "default_preset_name",
    "delete_custom_theme",
    "derive_semantic_tokens",
    "derive_tokens",
    "list_custom_themes",
    "list_presets",
    "load_appearance_preferences",
    "mix_hex",
    "presets_canon_path",
    "project_appearance_snapshot_for_qml",
    "rename_custom_theme",
    "reset_custom_theme",
    "resolve_appearance",
    "resolve_theme",
    "save_appearance_preferences",
    "save_custom_theme",
    "select_theme",
    "theme_preferences_path",
    "theme_tokens_to_qml_semantics",
]
