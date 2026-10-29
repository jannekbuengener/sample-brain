"""Native Windows title-bar theme adapter (#1214).

Consumes Appearance V2 ``windowChrome.*`` tokens from the #1255 bridge and
applies them through DWM window attributes. Fail-soft on unsupported platforms
or attributes. Never owns a second palette and never blocks launch.
"""

from __future__ import annotations

import sys
from typing import Any, Callable

NATIVE_WINDOW_CHROME_EXIT = "NATIVE_WINDOW_CHROME_THEME_LIVE"

# DwmSetWindowAttribute attribute indices (Windows 10/11 caption theming).
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_BORDER_COLOR = 34
DWMWA_CAPTION_COLOR = 35
DWMWA_TEXT_COLOR = 36

DwmSetter = Callable[[int, int, int], None]


def is_supported() -> bool:
    """True only on Windows; DWM availability is probed at apply time."""
    return sys.platform == "win32"


def hex_to_colorref(value: str | None) -> int | None:
    """Convert ``#RRGGBB`` to a Win32 COLORREF (``0x00BBGGRR``)."""
    if not isinstance(value, str):
        return None
    token = value.strip()
    if len(token) != 7 or not token.startswith("#"):
        return None
    try:
        red = int(token[1:3], 16)
        green = int(token[3:5], 16)
        blue = int(token[5:7], 16)
    except ValueError:
        return None
    return int(red) | (int(green) << 8) | (int(blue) << 16)


def _relative_luminance(hex_color: str) -> float:
    colorref_ready = hex_to_colorref(hex_color)
    if colorref_ready is None:
        return 0.0
    red = colorref_ready & 0xFF
    green = (colorref_ready >> 8) & 0xFF
    blue = (colorref_ready >> 16) & 0xFF

    def _channel(raw: int) -> float:
        c = raw / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * _channel(red) + 0.7152 * _channel(green) + 0.0722 * _channel(blue)


def is_dark_chrome_background(hex_color: str) -> bool:
    """Prefer immersive dark mode when caption background is dark."""
    return _relative_luminance(hex_color) < 0.45


def _default_dwm_setter(hwnd: int, attribute: int, value: int) -> None:
    import ctypes

    dwmapi = ctypes.WinDLL("dwmapi")
    data = ctypes.c_int(int(value))
    result = int(
        dwmapi.DwmSetWindowAttribute(
            int(hwnd),
            int(attribute),
            ctypes.byref(data),
            ctypes.sizeof(data),
        )
    )
    if result != 0:
        raise OSError(f"DwmSetWindowAttribute({attribute}) failed: {result}")


def _resolve_hwnd(window: Any) -> int:
    try:
        raw = window.winId()
    except Exception:
        return 0
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def apply_window_chrome(
    window: Any,
    *,
    background: str,
    foreground: str,
    border: str,
    dwm_setter: DwmSetter | None = None,
) -> bool:
    """Apply caption/text/border colors to a native window. Fail-soft."""
    if not is_supported():
        return False
    hwnd = _resolve_hwnd(window)
    if hwnd <= 0:
        return False

    caption = hex_to_colorref(background)
    text = hex_to_colorref(foreground)
    edge = hex_to_colorref(border)
    if caption is None or text is None or edge is None:
        return False

    setter = dwm_setter or _default_dwm_setter
    dark_mode = 1 if is_dark_chrome_background(background) else 0
    applied_any = False
    for attribute, value in (
        (DWMWA_USE_IMMERSIVE_DARK_MODE, dark_mode),
        (DWMWA_CAPTION_COLOR, caption),
        (DWMWA_TEXT_COLOR, text),
        (DWMWA_BORDER_COLOR, edge),
    ):
        try:
            setter(hwnd, attribute, value)
            applied_any = True
        except Exception:
            # Unsupported attribute / older Windows build — continue fail-soft.
            continue
    return applied_any


def _chrome_from_authority(theme_authority: Any) -> tuple[str, str, str] | None:
    try:
        background = str(theme_authority.windowChromeBackground)
        foreground = str(theme_authority.windowChromeForeground)
        border = str(theme_authority.windowChromeBorder)
    except Exception:
        return None
    if not background or not foreground or not border:
        return None
    return background, foreground, border


def wire_theme_authority(window: Any, theme_authority: Any) -> Any | None:
    """Apply current chrome tokens and re-apply on ``appearanceChanged``.

    Returns a small keep-alive handle (or ``None`` when unsupported). Exceptions
    never escape — launch must remain fail-soft.
    """
    if not is_supported() or window is None or theme_authority is None:
        return None

    def _apply_current(_generation: int = 0) -> None:
        tokens = _chrome_from_authority(theme_authority)
        if tokens is None:
            return
        background, foreground, border = tokens
        try:
            apply_window_chrome(
                window,
                background=background,
                foreground=foreground,
                border=border,
            )
        except Exception:
            return

    try:
        _apply_current(0)
        signal = getattr(theme_authority, "appearanceChanged", None)
        if signal is not None and hasattr(signal, "connect"):
            signal.connect(_apply_current)
        return {"window": window, "authority": theme_authority, "apply": _apply_current}
    except Exception:
        return None


__all__ = [
    "DWMWA_BORDER_COLOR",
    "DWMWA_CAPTION_COLOR",
    "DWMWA_TEXT_COLOR",
    "DWMWA_USE_IMMERSIVE_DARK_MODE",
    "NATIVE_WINDOW_CHROME_EXIT",
    "apply_window_chrome",
    "hex_to_colorref",
    "is_dark_chrome_background",
    "is_supported",
    "wire_theme_authority",
]
