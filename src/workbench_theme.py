"""Screen-1 Theme Core (#785).

Preset-based dark appearance tokens with local custom-theme persistence.
Derived tokens are computed from base accent/background/foreground only.
QML consumes mapped semantic colors through the Theme Authority bridge in
``workbench_qml`` — this module remains the sole derivation/persistence owner.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import struct
import zlib
from pathlib import Path
from typing import Any, Mapping

from .workbench_controller import workbench_state_dir

# Soft-ellipse atmosphere overlays (runtime cache; not preference persistence).
_ATMOSPHERE_SIZE = 256
_ATMOSPHERE_CACHE_DIRNAME = "theme_atmosphere"
# Subliminal depth only — overlay must not read as a visible glow effect.
ATMOSPHERE_OVERLAY_OPACITY = 0.40

THEME_PREFERENCES_SCHEMA = "sample_brain.theme_preferences"
THEME_PREFERENCES_SCHEMA_VERSION = 1
_THEME_PREFERENCES_FILENAME = "screen1_theme_preferences.json"

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
        # Superdesign cinematic-noir deep-black floor (#000000) → ink short of pure black.
        background="#020203",
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
            background="#020203",
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


def _read_store(*, state_dir: Path | None, env: Mapping[str, str] | None) -> dict[str, Any]:
    path = theme_preferences_path(state_dir=state_dir, env=env)
    if not path.is_file():
        return _empty_store()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return _empty_store()
    if not isinstance(raw, dict):
        return _empty_store()
    version = raw.get("schema_version")
    if type(version) is not int or version != THEME_PREFERENCES_SCHEMA_VERSION:
        # Unknown/legacy schema → fail closed, but still attempt salvage of customs
        # only when version matches; otherwise empty.
        if type(version) is not int:
            return _empty_store()
        return _empty_store()

    customs_raw = raw.get("custom_themes")
    customs: dict[str, dict[str, str]] = {}
    if isinstance(customs_raw, Mapping):
        for key, entry in customs_raw.items():
            if not isinstance(key, str) or not isinstance(entry, Mapping):
                continue
            sanitized = _sanitize_custom_entry({**dict(entry), "name": entry.get("name", key)})
            if sanitized is None:
                continue
            customs[sanitized["name"]] = sanitized

    selected = raw.get("selected", DEFAULT_PRESET_NAME)
    if not isinstance(selected, str) or not selected.strip():
        selected = DEFAULT_PRESET_NAME
    else:
        selected = selected.strip()
        if selected not in PRESET_ORDER and selected not in customs:
            selected = DEFAULT_PRESET_NAME

    return {
        "schema": THEME_PREFERENCES_SCHEMA,
        "schema_version": THEME_PREFERENCES_SCHEMA_VERSION,
        "selected": selected,
        "custom_themes": customs,
    }


def _write_store(
    store: Mapping[str, Any],
    *,
    state_dir: Path | None,
    env: Mapping[str, str] | None,
) -> Path:
    path = theme_preferences_path(state_dir=state_dir, env=env)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "schema": THEME_PREFERENCES_SCHEMA,
        "schema_version": THEME_PREFERENCES_SCHEMA_VERSION,
        "selected": store.get("selected", DEFAULT_PRESET_NAME),
        "custom_themes": store.get("custom_themes", {}),
    }
    # Strip any forbidden keys that may have leaked into customs.
    cleaned_customs: dict[str, dict[str, str]] = {}
    for name, entry in dict(body["custom_themes"]).items():
        if not isinstance(entry, Mapping):
            continue
        sanitized = _sanitize_custom_entry(entry)
        if sanitized is None:
            continue
        for forbidden in _FORBIDDEN_PERSIST_KEYS:
            sanitized.pop(forbidden, None)
        cleaned_customs[sanitized["name"]] = sanitized
    body["custom_themes"] = cleaned_customs
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
    _write_store(store, state_dir=state_dir, env=env)
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
    return _write_store(store, state_dir=state_dir, env=env)


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
    if store.get("selected") == old_name:
        store["selected"] = cleaned_new
    store["custom_themes"] = customs
    _write_store(store, state_dir=state_dir, env=env)


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
        _write_store(store, state_dir=state_dir, env=env)
        return resolve_theme(DEFAULT_PRESET_NAME, state_dir=state_dir, env=env)
    store["selected"] = name
    _write_store(store, state_dir=state_dir, env=env)
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
    store["custom_themes"] = customs
    _write_store(store, state_dir=state_dir, env=env)


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
    _write_store(store, state_dir=state_dir, env=env)
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
    out.setdefault("textOnAction", TEXT_ON_ACTION)
    return out


def atmosphere_stop_colors(
    tokens: Mapping[str, Any] | ThemeTokens,
) -> dict[str, dict[str, str]]:
    """Derive soft-ellipse stop colors from Theme bases (our combo only)."""
    if isinstance(tokens, ThemeTokens):
        source = tokens.as_dict()
    else:
        source = {str(k): str(v) for k, v in tokens.items()}
    accent = _normalize_hex(source.get("accent"))
    background = _normalize_hex(source.get("background"))
    foreground = _normalize_hex(source.get("foreground"))
    workspace = _normalize_hex(source.get("surfaceWorkspace"))
    panel = _normalize_hex(source.get("surface"))
    if None in (accent, background, foreground, workspace, panel):
        raise ValueError("invalid theme tokens for atmosphere stops")
    assert accent and background and foreground and workspace and panel
    # Subliminal noir depth only — Owner rejects visible warm glow ovals.
    return {
        "workspace": {
            "core": mix_hex(mix_hex(workspace, accent, 0.015), foreground, 0.003),
            "mid": workspace,
            "edge": mix_hex(workspace, background, 0.65),
        },
        "panel": {
            "core": mix_hex(mix_hex(panel, accent, 0.012), foreground, 0.002),
            "mid": panel,
            "edge": mix_hex(panel, background, 0.50),
        },
    }


def _lerp_channel(a: int, b: int, t: float) -> int:
    return max(0, min(255, int(round(a + (b - a) * t))))


def _lerp_rgb(
    color_a: tuple[int, int, int],
    color_b: tuple[int, int, int],
    t: float,
) -> tuple[int, int, int]:
    return (
        _lerp_channel(color_a[0], color_b[0], t),
        _lerp_channel(color_a[1], color_b[1], t),
        _lerp_channel(color_a[2], color_b[2], t),
    )


def _sample_atmosphere_stops(
    *,
    core: tuple[int, int, int],
    mid: tuple[int, int, int],
    edge: tuple[int, int, int],
    t: float,
) -> tuple[int, int, int]:
    """Map Superdesign-style 0/0.55/1.0 elliptical stops into RGB."""
    u = max(0.0, min(1.0, float(t)))
    if u <= 0.55:
        local = u / 0.55
        return _lerp_rgb(core, mid, local)
    local = (u - 0.55) / 0.45
    return _lerp_rgb(mid, edge, local)


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def render_atmosphere_ellipse_png(
    *,
    core: str,
    mid: str,
    edge: str,
    width: int = _ATMOSPHERE_SIZE,
    height: int = _ATMOSPHERE_SIZE,
) -> bytes:
    """Render a soft elliptical noir atmosphere PNG (stdlib only; no QML Gradient)."""
    w = max(8, int(width))
    h = max(8, int(height))
    core_rgb = _parse_rgb(core)
    mid_rgb = _parse_rgb(mid)
    edge_rgb = _parse_rgb(edge)
    cx = (w - 1) * 0.5
    cy = (h - 1) * 0.5
    # Slightly wide ellipse so stretched workspace panes keep cinematic falloff.
    rx = max(1.0, w * 0.58)
    ry = max(1.0, h * 0.52)
    rows: list[bytes] = []
    for y in range(h):
        row = bytearray()
        row.append(0)  # filter None
        for x in range(w):
            nx = (x - cx) / rx
            ny = (y - cy) / ry
            dist = (nx * nx + ny * ny) ** 0.5
            r, g, b = _sample_atmosphere_stops(
                core=core_rgb,
                mid=mid_rgb,
                edge=edge_rgb,
                t=dist,
            )
            row.extend((r, g, b, 255))
        rows.append(bytes(row))
    raw = b"".join(rows)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    return b"".join(
        (
            b"\x89PNG\r\n\x1a\n",
            _png_chunk(b"IHDR", ihdr),
            _png_chunk(b"IDAT", zlib.compress(raw, 9)),
            _png_chunk(b"IEND", b""),
        )
    )


def atmosphere_cache_dir(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
    cache_dir: Path | None = None,
) -> Path:
    if cache_dir is not None:
        return Path(cache_dir)
    base = state_dir if state_dir is not None else workbench_state_dir(env=env)
    return Path(base) / _ATMOSPHERE_CACHE_DIRNAME


def ensure_atmosphere_overlays(
    tokens: Mapping[str, Any] | ThemeTokens,
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
    cache_dir: Path | None = None,
) -> dict[str, Path]:
    """Write/reuse Theme-owned atmosphere PNGs for workspace + panel roles."""
    stops = atmosphere_stop_colors(tokens)
    out_dir = atmosphere_cache_dir(state_dir=state_dir, env=env, cache_dir=cache_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for role in ("workspace", "panel"):
        role_stops = stops[role]
        stem = (
            f"noir_{role}_"
            f"{role_stops['core'][1:]}_{role_stops['mid'][1:]}_{role_stops['edge'][1:]}"
        )
        path = out_dir / f"{stem}.png"
        if not path.is_file():
            path.write_bytes(
                render_atmosphere_ellipse_png(
                    core=role_stops["core"],
                    mid=role_stops["mid"],
                    edge=role_stops["edge"],
                )
            )
        paths[role] = path
    return paths


__all__ = [
    "ATMOSPHERE_OVERLAY_OPACITY",
    "BLOOD_A_ACCENT",
    "BLOOD_B_ACCENT",
    "DEFAULT_PRESET_NAME",
    "PRESET_ORDER",
    "TEXT_ON_ACTION",
    "THEME_PREFERENCES_SCHEMA",
    "THEME_PREFERENCES_SCHEMA_VERSION",
    "ThemeBase",
    "ThemeTokens",
    "atmosphere_cache_dir",
    "atmosphere_stop_colors",
    "blood_variants",
    "create_custom_theme",
    "default_preset_name",
    "delete_custom_theme",
    "derive_tokens",
    "ensure_atmosphere_overlays",
    "list_custom_themes",
    "list_presets",
    "mix_hex",
    "presets_canon_path",
    "rename_custom_theme",
    "render_atmosphere_ellipse_png",
    "reset_custom_theme",
    "resolve_theme",
    "save_custom_theme",
    "select_theme",
    "theme_preferences_path",
    "theme_tokens_to_qml_semantics",
]
