"""Windows focus guard for Sample Brain Screen-1 UI acceptance (ctypes only)."""

from __future__ import annotations

import ctypes
import subprocess
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
# Use -1 so the DWORD bit-pattern 0xFFFFFFFF never overflows signed c_int paths.
ASFW_ANY = -1


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
    hwnd = int(user32.FindWindowW(None, title) or 0)
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


def process_parent_pid(pid: int) -> int:
    """Return parent pid for pid via CIM (no Toolhelp ctypes structures)."""
    _require_win32()
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}').ParentProcessId",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    raw = (completed.stdout or "").strip()
    if not raw:
        return 0
    try:
        return int(raw)
    except ValueError:
        return 0


def pid_in_process_tree(candidate_pid: int, root_pid: int) -> bool:
    """True if candidate is root or a descendant (parent-chain reaches root)."""
    candidate = int(candidate_pid)
    root = int(root_pid)
    if candidate == 0 or root == 0:
        return False
    if candidate == root:
        return True
    seen: set[int] = set()
    cur = candidate
    while cur and cur not in seen:
        if cur == root:
            return True
        seen.add(cur)
        cur = process_parent_pid(cur)
    return False


def terminate_process_tree(root_pid: int) -> None:
    """Best-effort terminate root and descendants via taskkill /T."""
    _require_win32()
    root = int(root_pid)
    if root <= 0:
        return
    subprocess.run(
        ["taskkill", "/PID", str(root), "/T", "/F"],
        capture_output=True,
        text=True,
        check=False,
    )


def is_foreground(hwnd: int) -> bool:
    """True only when GetForegroundWindow() equals hwnd."""
    _require_win32()
    return foreground_owned(int(hwnd), foreground_hwnd())


def foreground_owned(target_hwnd: int, current_foreground: int) -> bool:
    """Pure foreground claim check (unit-testable without Win32)."""
    return int(target_hwnd) != 0 and int(current_foreground) == int(target_hwnd)


def ensure_foreground(hwnd: int, *, timeout_sec: float = 5.0) -> bool:
    """Bring hwnd to foreground. Returns True only if GetForegroundWindow()==hwnd."""
    _require_win32()
    target = wintypes.HWND(int(hwnd))
    if not user32.IsWindow(target):
        raise FocusGuardError(f"invalid hwnd: {hwnd}")
    if user32.IsIconic(target):
        user32.ShowWindow(target, SW_RESTORE)
    else:
        user32.ShowWindow(target, SW_SHOW)

    # Avoid AttachThreadInput (can overflow/fail against protected hosts like IDEs).
    # Alt key pulse is a common, local-only way to satisfy foreground lock rules.
    VK_MENU = 0x12
    KEYEVENTF_KEYUP = 0x0002
    try:
        user32.AllowSetForegroundWindow(ASFW_ANY)
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            user32.keybd_event(VK_MENU, 0, 0, 0)
            user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
            user32.BringWindowToTop(target)
            user32.SetForegroundWindow(target)
            time.sleep(0.12)
            if is_foreground(int(hwnd)):
                return True
    except (OverflowError, ctypes.ArgumentError) as exc:
        raise FocusGuardError(f"foreground win32 overflow: {exc}") from exc

    # Fail-closed: shown/restored without owning foreground is not enough for
    # keyboard, coordinate click, or visual-fallback acceptance steps.
    return False


def require_sample_brain_foreground(
    title: str = "Sample Brain",
    *,
    expected_pid: int | None = None,
    starter_pid: int | None = None,
    timeout_sec: float = 5.0,
) -> WindowInfo:
    info = find_window_by_title(title)
    if info is None:
        raise FocusGuardError(f"window not found: {title!r}")
    if expected_pid is not None and info.pid != int(expected_pid):
        # Allow venv launcher → system python child ownership when starter_pid set.
        if starter_pid is None or not pid_in_process_tree(info.pid, int(starter_pid)):
            raise FocusGuardError(
                f"window pid mismatch: hwnd={info.hwnd} pid={info.pid} "
                f"expected_pid={expected_pid} starter_pid={starter_pid}"
            )
    if not ensure_foreground(info.hwnd, timeout_sec=timeout_sec):
        raise FocusGuardError(
            "failed to foreground window: "
            f"{title!r} hwnd={info.hwnd} foreground={foreground_hwnd()}"
        )
    refreshed = find_window_by_title(title)
    if refreshed is None:
        raise FocusGuardError(f"window disappeared: {title!r}")
    if expected_pid is not None and refreshed.pid != int(expected_pid):
        if starter_pid is None or not pid_in_process_tree(refreshed.pid, int(starter_pid)):
            raise FocusGuardError(
                f"window pid mismatch after focus: pid={refreshed.pid} "
                f"expected_pid={expected_pid} starter_pid={starter_pid}"
            )
    if not is_foreground(refreshed.hwnd):
        raise FocusGuardError(
            f"foreground lost after focus: hwnd={refreshed.hwnd} foreground={foreground_hwnd()}"
        )
    return refreshed
