"""Window placement helpers for deterministic Workbench startup."""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

WorkArea = tuple[int, int, int, int]


def centered_window_position(
    available_geometry: Any,
    window_width: int,
    window_height: int,
) -> tuple[int, int]:
    """Center a window in available screen geometry without assuming (0, 0)."""
    x = int(available_geometry.x())
    y = int(available_geometry.y())
    width = int(available_geometry.width())
    height = int(available_geometry.height())
    offset_x = max(0, (width - int(window_width)) // 2)
    offset_y = max(0, (height - int(window_height)) // 2)
    return x + offset_x, y + offset_y


def centered_work_area_position(
    work_area: WorkArea,
    window_width: int,
    window_height: int,
) -> tuple[int, int]:
    """Center a window inside an ``(x, y, width, height)`` desktop work area."""
    x, y, width, height = work_area
    offset_x = max(0, (int(width) - int(window_width)) // 2)
    offset_y = max(0, (int(height) - int(window_height)) // 2)
    return int(x) + offset_x, int(y) + offset_y


def windows_primary_work_area() -> WorkArea | None:
    """Return the Windows primary-monitor work area without creating another UI."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        rect = wintypes.RECT()
        spi_getworkarea = 0x0030
        ok = ctypes.windll.user32.SystemParametersInfoW(  # type: ignore[attr-defined]
            spi_getworkarea,
            0,
            ctypes.byref(rect),
            0,
        )
        width = int(rect.right - rect.left)
        height = int(rect.bottom - rect.top)
        if not ok or width <= 0 or height <= 0:
            return None
        return int(rect.left), int(rect.top), width, height
    except (AttributeError, OSError):
        return None


def show_tk_window_on_primary_screen(
    root: Any,
    *,
    primary_work_area: WorkArea | None = None,
    work_area_provider: Callable[[], WorkArea | None] = windows_primary_work_area,
) -> bool:
    """Position a withdrawn Tk root on the primary display, then reveal it once."""
    positioned = False
    try:
        work_area = primary_work_area or work_area_provider()
        if work_area is not None:
            root.update_idletasks()
            min_width, min_height = root.minsize()
            width = max(1, int(root.winfo_reqwidth()), int(min_width))
            height = max(1, int(root.winfo_reqheight()), int(min_height))
            x, y = centered_work_area_position(work_area, width, height)
            root.geometry(f"{x:+d}{y:+d}")
            positioned = True
    except Exception:
        positioned = False

    root.deiconify()
    return positioned


def show_window_on_primary_screen(app: Any, window: Any) -> bool:
    """Place ``window`` on the current OS primary screen, then show it once.

    Placement is deliberately fail-soft: if Qt cannot expose usable primary-screen
    geometry during startup, normal window-manager placement remains available.
    """
    positioned = False
    try:
        primary_screen = app.primaryScreen()
        if primary_screen is not None:
            geometry = primary_screen.availableGeometry()
            x, y = centered_window_position(
                geometry,
                int(window.width()),
                int(window.height()),
            )
            window.setScreen(primary_screen)
            window.setPosition(x, y)
            positioned = True
    except Exception:
        positioned = False

    window.show()
    return positioned
