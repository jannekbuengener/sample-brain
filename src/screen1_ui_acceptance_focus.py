"""Windows focus guard for Sample Brain Screen-1 UI acceptance (ctypes only)."""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass


user32 = ctypes.WinDLL("user32", use_last_error=True) if sys.platform == "win32" else None
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True) if sys.platform == "win32" else None

if user32 is not None and kernel32 is not None:
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsIconic.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.BringWindowToTop.argtypes = [wintypes.HWND]
    user32.BringWindowToTop.restype = wintypes.BOOL
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    user32.AttachThreadInput.restype = wintypes.BOOL
    user32.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
    user32.AllowSetForegroundWindow.restype = wintypes.BOOL
    kernel32.GetCurrentThreadId.argtypes = []
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD

SW_RESTORE = 9
SW_SHOW = 5
ASFW_ANY = 0xFFFFFFFF


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    title: str
    pid: int
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)


class FocusGuardError(RuntimeError):
    pass


def _require_win32() -> None:
    if user32 is None or kernel32 is None:
        raise FocusGuardError("focus guard requires Windows")


def window_title(hwnd: int) -> str:
    _require_win32()
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def find_window_by_title(title: str) -> WindowInfo | None:
    _require_win32()
    hwnd = int(user32.FindWindowW(None, title))
    if not hwnd or not user32.IsWindow(hwnd):
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise FocusGuardError("GetWindowRect failed")
    return WindowInfo(
        hwnd=hwnd,
        title=window_title(hwnd) or title,
        pid=int(pid.value),
        left=int(rect.left),
        top=int(rect.top),
        right=int(rect.right),
        bottom=int(rect.bottom),
    )


def foreground_hwnd() -> int:
    _require_win32()
    return int(user32.GetForegroundWindow() or 0)


def ensure_foreground(hwnd: int, *, timeout_sec: float = 5.0) -> bool:
    """Bring hwnd to foreground. Returns True if focused or at least shown/restored."""
    _require_win32()
    if not user32.IsWindow(hwnd):
        raise FocusGuardError(f"invalid hwnd: {hwnd}")
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    else:
        user32.ShowWindow(hwnd, SW_SHOW)

    user32.AllowSetForegroundWindow(ASFW_ANY)
    target_tid = int(user32.GetWindowThreadProcessId(hwnd, None) or 0)
    current_tid = int(kernel32.GetCurrentThreadId() or 0)
    foreground = user32.GetForegroundWindow()
    foreground_tid = (
        int(user32.GetWindowThreadProcessId(foreground, None) or 0) if foreground else 0
    )

    attached_fg = False
    attached_target = False
    try:
        if foreground_tid and foreground_tid != current_tid:
            attached_fg = bool(user32.AttachThreadInput(current_tid, foreground_tid, True))
        if target_tid and target_tid != current_tid:
            attached_target = bool(user32.AttachThreadInput(current_tid, target_tid, True))
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            time.sleep(0.12)
            if foreground_hwnd() == int(hwnd):
                return True
    finally:
        if attached_target and target_tid:
            user32.AttachThreadInput(current_tid, target_tid, False)
        if attached_fg and foreground_tid:
            user32.AttachThreadInput(current_tid, foreground_tid, False)

    # Windows may deny foreground ownership to automated callers; continuing is
    # acceptable when the window is present and not minimized.
    return bool(user32.IsWindow(hwnd) and not user32.IsIconic(hwnd))


def require_sample_brain_foreground(
    title: str = "Sample Brain", *, timeout_sec: float = 5.0
) -> WindowInfo:
    info = find_window_by_title(title)
    if info is None:
        raise FocusGuardError(f"window not found: {title!r}")
    if not ensure_foreground(info.hwnd, timeout_sec=timeout_sec):
        raise FocusGuardError(f"failed to foreground window: {title!r}")
    refreshed = find_window_by_title(title)
    if refreshed is None:
        raise FocusGuardError(f"window disappeared: {title!r}")
    return refreshed
