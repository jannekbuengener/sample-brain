"""Appearance V2 Python authority (#1253).

Sole derivation owner for Appearance state resolution and semantic tokens.
Consumes #785 Theme Core primitives/helpers; does not persist derived tokens
(#1254) and does not project into QML (#1255).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from . import workbench_theme as theme
from .workbench_display_preferences import (
    MOTION_OFF,
    MOTION_ON,
    MOTION_REDUCED,
)

APPEARANCE_V2_EXIT = "APPEARANCE_V2_PYTHON_CORE_GREEN"

MODE_SYSTEM = "system"
MODE_LIGHT = "light"
MODE_DARK = "dark"
APPEARANCE_MODES = (MODE_SYSTEM, MODE_LIGHT, MODE_DARK)

MOTION_SYSTEM = "system"
APPEARANCE_MOTION_MODES = (MOTION_SYSTEM, MOTION_ON, MOTION_REDUCED, MOTION_OFF)

DEFAULT_MODE = MODE_DARK
DEFAULT_CONTRAST = 50
DEFAULT_UI_FONT_SIZE = 14
DEFAULT_CODE_FONT_SIZE = 12
DEFAULT_MOTION_MODE = MOTION_ON

CONTRAST_MIN = 0
CONTRAST_MAX = 100
UI_FONT_MIN = 12
UI_FONT_MAX = 18
CODE_FONT_MIN = 10
CODE_FONT_MAX = 18

LIGHT_FALLBACK_BACKGROUND = "#f7f7f5"
LIGHT_FALLBACK_FOREGROUND = "#171719"

PROTECTED_STATUS_PALETTE: dict[str, dict[str, str]] = {
    MODE_DARK: {
        "error": "#e06a74",
        "warning": "#d2a64f",
        "success": "#69ad82",
        "info": "#75a7c8",
    },
    MODE_LIGHT: {
        "error": "#a93245",
        "warning": "#8a5d12",
        "success": "#2f714c",
        "info": "#346f96",
    },
}

# #1248 Library product-semantic accents — never implicit Accent aliases.
PROTECTED_HIGHLIGHT_DEFAULTS: dict[str, str] = {
    "libraryAllSamplesAccent": "#93a8b8",
    "libraryCollectionsAccent": "#aa9e7b",
    "libraryFavoritesAccent": "#ad6267",
    "libraryRecordsAccent": "#9c91ae",
}

# Piecewise-linear Contrast anchors at (0, 50, 100).
_CONTRAST_ANCHORS: dict[str, tuple[float, float, float]] = {
    "text.secondary": (0.68, 0.55, 0.42),
    "text.muted": (0.78, 0.68, 0.58),
    "text.disabled": (0.86, 0.78, 0.70),
    "surface.canvas": (0.004, 0.008, 0.016),
    "surface.panel": (0.014, 0.028, 0.056),
    "surface.raised": (0.03, 0.06, 0.12),
    "surface.hover": (0.04, 0.075, 0.13),
    "surface.selected": (0.14, 0.22, 0.32),
    "border.subtle": (0.05, 0.10, 0.20),
    "border.default": (0.075, 0.15, 0.30),
    "border.strong": (0.10, 0.20, 0.40),
    "accent.subtle": (0.10, 0.16, 0.24),
}

_ACCENT_HOVER_RATIO = 0.12
_ACCENT_ACTIVE_RATIO = 0.20

_UI_TYPE_ROLES: dict[str, tuple[float, float, int | None]] = {
    # font_size, line_height, optional weight
    "caption": (12.0, 16.0, None),
    "standard": (14.0, 20.0, None),
    "content": (16.0, 26.0, None),
    "section": (14.0, 18.0, 500),
    "page": (24.0, 29.0, None),
}


@dataclass(frozen=True)
class AppearanceProfileInput:
    theme_ref: str | None = None
    background: str | None = None
    foreground: str | None = None
    accent: str | None = None
    contrast: int | None = None


@dataclass(frozen=True)
class AppearanceRequestedState:
    """User/persisted intent. Never contains derived semantic tokens."""

    mode: str = DEFAULT_MODE
    separate_light_dark: bool = False
    ui_font_size: int = DEFAULT_UI_FONT_SIZE
    code_font_size: int = DEFAULT_CODE_FONT_SIZE
    motion_mode: str = DEFAULT_MOTION_MODE
    shared: AppearanceProfileInput | None = None
    dark: AppearanceProfileInput | None = None
    light: AppearanceProfileInput | None = None


@dataclass(frozen=True)
class TypeRoleMetrics:
    font_size: float
    line_height: float
    weight: int | None = None


@dataclass(frozen=True)
class UiTypographyScale:
    caption: TypeRoleMetrics
    standard: TypeRoleMetrics
    content: TypeRoleMetrics
    section: TypeRoleMetrics
    page: TypeRoleMetrics

    def as_dict(self) -> dict[str, TypeRoleMetrics]:
        return {
            "caption": self.caption,
            "standard": self.standard,
            "content": self.content,
            "section": self.section,
            "page": self.page,
        }


@dataclass(frozen=True)
class TypographyResolved:
    ui: UiTypographyScale
    code: TypeRoleMetrics


@dataclass(frozen=True)
class AppearanceSemanticTokens:
    surface_canvas: str
    surface_panel: str
    surface_raised: str
    surface_hover: str
    surface_selected: str
    text_primary: str
    text_secondary: str
    text_muted: str
    text_disabled: str
    border_subtle: str
    border_default: str
    border_strong: str
    accent_base: str
    accent_hover: str
    accent_active: str
    accent_subtle: str
    accent_on_accent: str
    interaction_focus: str
    interaction_selection: str
    interaction_pressed: str
    interaction_disabled: str
    status_error: str
    status_warning: str
    status_success: str
    status_info: str
    window_chrome_background: str
    window_chrome_foreground: str
    window_chrome_border: str
    motion_effective: str
    protected_highlight: Mapping[str, str] = field(default_factory=dict)

    def as_flat_dict(self) -> dict[str, str]:
        out = {
            "surface.canvas": self.surface_canvas,
            "surface.panel": self.surface_panel,
            "surface.raised": self.surface_raised,
            "surface.hover": self.surface_hover,
            "surface.selected": self.surface_selected,
            "text.primary": self.text_primary,
            "text.secondary": self.text_secondary,
            "text.muted": self.text_muted,
            "text.disabled": self.text_disabled,
            "border.subtle": self.border_subtle,
            "border.default": self.border_default,
            "border.strong": self.border_strong,
            "accent.base": self.accent_base,
            "accent.hover": self.accent_hover,
            "accent.active": self.accent_active,
            "accent.subtle": self.accent_subtle,
            "accent.onAccent": self.accent_on_accent,
            "interaction.focus": self.interaction_focus,
            "interaction.selection": self.interaction_selection,
            "interaction.pressed": self.interaction_pressed,
            "interaction.disabled": self.interaction_disabled,
            "status.error": self.status_error,
            "status.warning": self.status_warning,
            "status.success": self.status_success,
            "status.info": self.status_info,
            "windowChrome.background": self.window_chrome_background,
            "windowChrome.foreground": self.window_chrome_foreground,
            "windowChrome.border": self.window_chrome_border,
            "motion.effective": self.motion_effective,
        }
        for key, value in self.protected_highlight.items():
            out[f"protectedHighlight.{key}"] = value
        return out


@dataclass(frozen=True)
class AppearanceResolvedSnapshot:
    """Immutable renderer-facing Appearance snapshot."""

    mode_requested: str
    resolved_scheme: str
    separate_light_dark: bool
    theme_ref: str
    background: str
    foreground: str
    accent: str
    contrast: int
    ui_font_size: int
    code_font_size: int
    motion_mode_requested: str
    motion_effective: str
    tokens: AppearanceSemanticTokens
    typography: TypographyResolved

    def legacy_theme_tokens(self) -> theme.ThemeTokens:
        """#785-compatible ThemeTokens projection at the resolved primitives."""
        return theme.ThemeTokens(
            accent=self.accent,
            background=self.background,
            foreground=self.foreground,
            textPrimary=self.tokens.text_primary,
            textSecondary=self.tokens.text_secondary,
            surfaceWorkspace=self.tokens.surface_canvas,
            surface=self.tokens.surface_panel,
            surfaceRaised=self.tokens.surface_raised,
            divider=self.tokens.border_subtle,
            hover=self.tokens.surface_hover,
            selected=self.tokens.surface_selected,
            focusRing=self.tokens.interaction_focus,
            name=self.theme_ref,
            base_preset=self.theme_ref if self.theme_ref in theme.PRESET_ORDER else theme.DEFAULT_PRESET_NAME,
        )


def _normalize_hex(value: Any) -> str | None:
    return theme._normalize_hex(value)  # noqa: SLF001 — shared Theme Core normalizer


def _clamp_int(value: Any, *, minimum: int, maximum: int, default: int) -> int:
    if type(value) is bool or value is None:
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if number < minimum or number > maximum:
        return default
    return number


def _normalize_mode(value: Any) -> str:
    token = str(value or "").strip().lower()
    if token in APPEARANCE_MODES:
        return token
    return DEFAULT_MODE


def _normalize_motion_mode(value: Any) -> str:
    token = str(value or "").strip().lower()
    if token == "full":
        return MOTION_ON
    if token in APPEARANCE_MOTION_MODES:
        return token
    return DEFAULT_MOTION_MODE


def _normalize_scheme(value: Any) -> str | None:
    token = str(value or "").strip().lower()
    if token in {MODE_LIGHT, MODE_DARK}:
        return token
    return None


def contrast_mix_amount(anchors: tuple[float, float, float], contrast: int) -> float:
    """Piecewise-linear mix amount through Contrast anchors at 0 / 50 / 100."""
    low, mid, high = anchors
    c = max(CONTRAST_MIN, min(CONTRAST_MAX, int(contrast)))
    if c <= 50:
        t = c / 50.0
        return low * (1.0 - t) + mid * t
    t = (c - 50) / 50.0
    return mid * (1.0 - t) + high * t


def _srgb_channel_to_linear(channel: int) -> float:
    c = channel / 255.0
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    r, g, b = theme._parse_rgb(hex_color)  # noqa: SLF001
    return (
        0.2126 * _srgb_channel_to_linear(r)
        + 0.7152 * _srgb_channel_to_linear(g)
        + 0.0722 * _srgb_channel_to_linear(b)
    )


def contrast_ratio(color_a: str, color_b: str) -> float:
    lum_a = relative_luminance(color_a)
    lum_b = relative_luminance(color_b)
    lighter = max(lum_a, lum_b)
    darker = min(lum_a, lum_b)
    return (lighter + 0.05) / (darker + 0.05)


def resolve_on_accent(*, accent: str, background: str, foreground: str) -> str:
    """Pick readable on-accent ink.

    Prefer solid white when it meets the primary readability floor (matches
    Theme Core TEXT_ON_ACTION / Blood golden). Otherwise choose the better of
    Background/Foreground by WCAG contrast against Accent.
    """
    white = theme.TEXT_ON_ACTION
    if contrast_ratio(white, accent) >= 4.5:
        return white
    if contrast_ratio(foreground, accent) >= contrast_ratio(background, accent):
        return foreground
    return background


def resolve_focus_ring(*, accent: str, background: str, foreground: str) -> str:
    """Accent-owned focus ring.

    #785 / #1252 golden cases pin ``interaction.focus`` to the Accent primitive.
    Accessibility repair must never mutate ``accent.base``; ring geometry/style
    remains the consumer's duty when Accent-to-adjacent contrast is tight
    (Blood default is ~2:1 by design and still Accent-owned).

    ``background`` / ``foreground`` are part of the stable seam for a future
    derived-only repair path and are intentionally unused today.
    """
    _ = (background, foreground)
    return accent


def _round_half(value: float) -> float:
    return round(value * 2.0) / 2.0


def resolve_typography(*, ui_font_size: int, code_font_size: int) -> TypographyResolved:
    ui_scale = float(ui_font_size) / float(DEFAULT_UI_FONT_SIZE)
    ui_roles: dict[str, TypeRoleMetrics] = {}
    for name, (size, line, weight) in _UI_TYPE_ROLES.items():
        ui_roles[name] = TypeRoleMetrics(
            font_size=_round_half(size * ui_scale),
            line_height=_round_half(line * ui_scale),
            weight=weight,
        )
    code = TypeRoleMetrics(
        font_size=float(code_font_size),
        line_height=_round_half(float(code_font_size) * 1.5),
    )
    return TypographyResolved(
        ui=UiTypographyScale(
            caption=ui_roles["caption"],
            standard=ui_roles["standard"],
            content=ui_roles["content"],
            section=ui_roles["section"],
            page=ui_roles["page"],
        ),
        code=code,
    )


def resolve_motion_effective(
    motion_mode: str,
    *,
    platform_reduce_motion: bool | None = None,
) -> str:
    requested = _normalize_motion_mode(motion_mode)
    if requested != MOTION_SYSTEM:
        return requested
    if platform_reduce_motion is True:
        return MOTION_REDUCED
    # false or unavailable → on (#1252 / #696)
    return MOTION_ON


def resolve_scheme(
    mode: str,
    *,
    platform_color_scheme: str | None = None,
) -> str:
    requested = _normalize_mode(mode)
    if requested == MODE_LIGHT:
        return MODE_LIGHT
    if requested == MODE_DARK:
        return MODE_DARK
    platform = _normalize_scheme(platform_color_scheme)
    if platform is None:
        return MODE_DARK
    return platform


def _preset_base_or_blood(theme_ref: str | None) -> tuple[str, theme.ThemeBase]:
    name = theme_ref if isinstance(theme_ref, str) and theme_ref.strip() else theme.DEFAULT_PRESET_NAME
    cleaned = name.strip()
    if cleaned in theme.PRESET_ORDER:
        base = theme._preset_base(cleaned)  # noqa: SLF001
        if base is not None:
            return cleaned, base
    return theme.DEFAULT_PRESET_NAME, theme._blood_a_base()  # noqa: SLF001


def _scheme_variant_base(theme_ref: str, scheme: str) -> theme.ThemeBase:
    _, dark_base = _preset_base_or_blood(theme_ref)
    if scheme == MODE_DARK:
        return dark_base
    # Missing light variant → V2 neutral-light fallback with theme Accent.
    return theme.ThemeBase(
        accent=dark_base.accent,
        background=LIGHT_FALLBACK_BACKGROUND,
        foreground=LIGHT_FALLBACK_FOREGROUND,
    )


def _apply_profile_overrides(
    base: theme.ThemeBase,
    profile: AppearanceProfileInput | None,
) -> tuple[theme.ThemeBase, int]:
    contrast = DEFAULT_CONTRAST
    if profile is None:
        return base, contrast
    accent = _normalize_hex(profile.accent) if profile.accent is not None else base.accent
    background = _normalize_hex(profile.background) if profile.background is not None else base.background
    foreground = _normalize_hex(profile.foreground) if profile.foreground is not None else base.foreground
    if accent is None:
        accent = base.accent
    if background is None:
        background = base.background
    if foreground is None:
        foreground = base.foreground
    contrast = _clamp_int(
        profile.contrast if profile.contrast is not None else DEFAULT_CONTRAST,
        minimum=CONTRAST_MIN,
        maximum=CONTRAST_MAX,
        default=DEFAULT_CONTRAST,
    )
    return theme.ThemeBase(accent=accent, background=background, foreground=foreground), contrast


def _active_profile(
    requested: AppearanceRequestedState,
    *,
    scheme: str,
) -> AppearanceProfileInput | None:
    if requested.separate_light_dark:
        return requested.dark if scheme == MODE_DARK else requested.light
    return requested.shared


def _theme_ref_from_profile(profile: AppearanceProfileInput | None) -> str:
    if profile is None or not profile.theme_ref:
        return theme.DEFAULT_PRESET_NAME
    cleaned = str(profile.theme_ref).strip()
    if not cleaned:
        return theme.DEFAULT_PRESET_NAME
    return cleaned


def derive_semantic_tokens(
    *,
    background: str,
    foreground: str,
    accent: str,
    contrast: int = DEFAULT_CONTRAST,
    scheme: str = MODE_DARK,
    motion_effective: str = MOTION_ON,
) -> AppearanceSemanticTokens:
    """Pure deterministic semantic token derivation from Appearance primitives."""
    bg = _normalize_hex(background)
    fg = _normalize_hex(foreground)
    ac = _normalize_hex(accent)
    if bg is None or fg is None or ac is None:
        blood = theme._blood_a_base()  # noqa: SLF001
        bg = blood.background
        fg = blood.foreground
        ac = blood.accent
    c = _clamp_int(contrast, minimum=CONTRAST_MIN, maximum=CONTRAST_MAX, default=DEFAULT_CONTRAST)
    resolved_scheme = MODE_LIGHT if scheme == MODE_LIGHT else MODE_DARK

    text_primary = fg
    text_secondary = theme.mix_hex(fg, bg, contrast_mix_amount(_CONTRAST_ANCHORS["text.secondary"], c))
    text_muted = theme.mix_hex(fg, bg, contrast_mix_amount(_CONTRAST_ANCHORS["text.muted"], c))
    text_disabled = theme.mix_hex(fg, bg, contrast_mix_amount(_CONTRAST_ANCHORS["text.disabled"], c))

    surface_canvas = theme.mix_hex(bg, fg, contrast_mix_amount(_CONTRAST_ANCHORS["surface.canvas"], c))
    surface_panel = theme.mix_hex(bg, fg, contrast_mix_amount(_CONTRAST_ANCHORS["surface.panel"], c))
    surface_raised = theme.mix_hex(bg, fg, contrast_mix_amount(_CONTRAST_ANCHORS["surface.raised"], c))
    surface_hover = theme.mix_hex(bg, fg, contrast_mix_amount(_CONTRAST_ANCHORS["surface.hover"], c))
    surface_selected = theme.mix_hex(bg, ac, contrast_mix_amount(_CONTRAST_ANCHORS["surface.selected"], c))

    border_subtle = theme.mix_hex(bg, fg, contrast_mix_amount(_CONTRAST_ANCHORS["border.subtle"], c))
    border_default = theme.mix_hex(bg, fg, contrast_mix_amount(_CONTRAST_ANCHORS["border.default"], c))
    border_strong = theme.mix_hex(bg, fg, contrast_mix_amount(_CONTRAST_ANCHORS["border.strong"], c))

    accent_base = ac
    accent_hover = theme.mix_hex(ac, fg, _ACCENT_HOVER_RATIO)
    accent_active = theme.mix_hex(ac, fg, _ACCENT_ACTIVE_RATIO)
    accent_subtle = theme.mix_hex(bg, ac, contrast_mix_amount(_CONTRAST_ANCHORS["accent.subtle"], c))
    accent_on_accent = resolve_on_accent(accent=ac, background=bg, foreground=fg)

    interaction_focus = resolve_focus_ring(accent=ac, background=bg, foreground=fg)
    interaction_selection = surface_selected
    interaction_pressed = accent_active
    interaction_disabled = text_disabled

    status = PROTECTED_STATUS_PALETTE[resolved_scheme]

    return AppearanceSemanticTokens(
        surface_canvas=surface_canvas,
        surface_panel=surface_panel,
        surface_raised=surface_raised,
        surface_hover=surface_hover,
        surface_selected=surface_selected,
        text_primary=text_primary,
        text_secondary=text_secondary,
        text_muted=text_muted,
        text_disabled=text_disabled,
        border_subtle=border_subtle,
        border_default=border_default,
        border_strong=border_strong,
        accent_base=accent_base,
        accent_hover=accent_hover,
        accent_active=accent_active,
        accent_subtle=accent_subtle,
        accent_on_accent=accent_on_accent,
        interaction_focus=interaction_focus,
        interaction_selection=interaction_selection,
        interaction_pressed=interaction_pressed,
        interaction_disabled=interaction_disabled,
        status_error=status["error"],
        status_warning=status["warning"],
        status_success=status["success"],
        status_info=status["info"],
        window_chrome_background=bg,
        window_chrome_foreground=text_primary,
        window_chrome_border=border_subtle,
        motion_effective=motion_effective if motion_effective in {MOTION_ON, MOTION_REDUCED, MOTION_OFF} else MOTION_ON,
        protected_highlight=dict(PROTECTED_HIGHLIGHT_DEFAULTS),
    )


def resolve_appearance(
    requested: AppearanceRequestedState | None = None,
    *,
    platform_color_scheme: str | None = None,
    platform_reduce_motion: bool | None = None,
) -> AppearanceResolvedSnapshot:
    """Resolve requested Appearance intent into an immutable semantic snapshot.

    Platform preferences are injectable for tests. Missing/invalid platform
    values fail closed to dark / motion-on. No OS APIs are read here.
    """
    state = requested if requested is not None else AppearanceRequestedState()

    mode_requested = _normalize_mode(state.mode)
    separate = bool(state.separate_light_dark)
    ui_font_size = _clamp_int(
        state.ui_font_size,
        minimum=UI_FONT_MIN,
        maximum=UI_FONT_MAX,
        default=DEFAULT_UI_FONT_SIZE,
    )
    code_font_size = _clamp_int(
        state.code_font_size,
        minimum=CODE_FONT_MIN,
        maximum=CODE_FONT_MAX,
        default=DEFAULT_CODE_FONT_SIZE,
    )
    motion_requested = _normalize_motion_mode(state.motion_mode)
    motion_effective = resolve_motion_effective(
        motion_requested,
        platform_reduce_motion=platform_reduce_motion,
    )
    scheme = resolve_scheme(mode_requested, platform_color_scheme=platform_color_scheme)

    profile = _active_profile(state, scheme=scheme)
    theme_ref = _theme_ref_from_profile(profile)
    # When shared/custom theme_ref is a preset name, use it; otherwise Blood.
    if profile is not None and profile.theme_ref:
        candidate = str(profile.theme_ref).strip()
        if candidate in theme.PRESET_ORDER:
            theme_ref = candidate
        elif candidate.lower() == "custom":
            theme_ref = "custom"
        else:
            theme_ref = candidate if candidate else theme.DEFAULT_PRESET_NAME

    variant = _scheme_variant_base(
        theme_ref if theme_ref in theme.PRESET_ORDER else theme.DEFAULT_PRESET_NAME,
        scheme,
    )
    primitives, contrast = _apply_profile_overrides(variant, profile)

    # Accessibility: reject unreadable primary text by failing closed to last
    # valid Blood defaults for the active scheme (no silent primitive rewrite
    # of a partially valid custom triplet — replace the whole profile).
    if contrast_ratio(primitives.foreground, primitives.background) < 4.5:
        fallback_variant = _scheme_variant_base(theme.DEFAULT_PRESET_NAME, scheme)
        primitives, contrast = fallback_variant, DEFAULT_CONTRAST
        theme_ref = theme.DEFAULT_PRESET_NAME

    tokens = derive_semantic_tokens(
        background=primitives.background,
        foreground=primitives.foreground,
        accent=primitives.accent,
        contrast=contrast,
        scheme=scheme,
        motion_effective=motion_effective,
    )
    typography = resolve_typography(ui_font_size=ui_font_size, code_font_size=code_font_size)

    return AppearanceResolvedSnapshot(
        mode_requested=mode_requested,
        resolved_scheme=scheme,
        separate_light_dark=separate,
        theme_ref=theme_ref,
        background=primitives.background,
        foreground=primitives.foreground,
        accent=primitives.accent,
        contrast=contrast,
        ui_font_size=ui_font_size,
        code_font_size=code_font_size,
        motion_mode_requested=motion_requested,
        motion_effective=motion_effective,
        tokens=tokens,
        typography=typography,
    )


def appearance_requested_from_mapping(payload: Mapping[str, Any] | None) -> AppearanceRequestedState:
    """Fail-closed adapter for future #1254 persistence payloads."""
    if not isinstance(payload, Mapping):
        return AppearanceRequestedState()

    def _profile(raw: Any) -> AppearanceProfileInput | None:
        if not isinstance(raw, Mapping):
            return None
        return AppearanceProfileInput(
            theme_ref=str(raw["themeRef"]).strip() if isinstance(raw.get("themeRef"), str) else None,
            background=raw.get("background") if isinstance(raw.get("background"), str) else None,
            foreground=raw.get("foreground") if isinstance(raw.get("foreground"), str) else None,
            accent=raw.get("accent") if isinstance(raw.get("accent"), str) else None,
            contrast=raw.get("contrast") if type(raw.get("contrast")) is int else None,
        )

    return AppearanceRequestedState(
        mode=_normalize_mode(payload.get("mode")),
        separate_light_dark=bool(payload.get("separateLightDark", False)),
        ui_font_size=_clamp_int(
            payload.get("uiFontSize", DEFAULT_UI_FONT_SIZE),
            minimum=UI_FONT_MIN,
            maximum=UI_FONT_MAX,
            default=DEFAULT_UI_FONT_SIZE,
        ),
        code_font_size=_clamp_int(
            payload.get("codeFontSize", DEFAULT_CODE_FONT_SIZE),
            minimum=CODE_FONT_MIN,
            maximum=CODE_FONT_MAX,
            default=DEFAULT_CODE_FONT_SIZE,
        ),
        motion_mode=_normalize_motion_mode(payload.get("motionMode", DEFAULT_MOTION_MODE)),
        shared=_profile(payload.get("shared")),
        dark=_profile(payload.get("dark")),
        light=_profile(payload.get("light")),
    )


__all__ = [
    "APPEARANCE_MOTION_MODES",
    "APPEARANCE_MODES",
    "APPEARANCE_V2_EXIT",
    "AppearanceProfileInput",
    "AppearanceRequestedState",
    "AppearanceResolvedSnapshot",
    "AppearanceSemanticTokens",
    "CODE_FONT_MAX",
    "CODE_FONT_MIN",
    "CONTRAST_MAX",
    "CONTRAST_MIN",
    "DEFAULT_CODE_FONT_SIZE",
    "DEFAULT_CONTRAST",
    "DEFAULT_MODE",
    "DEFAULT_MOTION_MODE",
    "DEFAULT_UI_FONT_SIZE",
    "LIGHT_FALLBACK_BACKGROUND",
    "LIGHT_FALLBACK_FOREGROUND",
    "MODE_DARK",
    "MODE_LIGHT",
    "MODE_SYSTEM",
    "MOTION_SYSTEM",
    "PROTECTED_HIGHLIGHT_DEFAULTS",
    "PROTECTED_STATUS_PALETTE",
    "TypeRoleMetrics",
    "TypographyResolved",
    "UiTypographyScale",
    "UI_FONT_MAX",
    "UI_FONT_MIN",
    "appearance_requested_from_mapping",
    "contrast_mix_amount",
    "contrast_ratio",
    "derive_semantic_tokens",
    "relative_luminance",
    "resolve_appearance",
    "resolve_focus_ring",
    "resolve_motion_effective",
    "resolve_on_accent",
    "resolve_scheme",
    "resolve_typography",
]
