"""Windows UI helpers for Screen-1 acceptance.

Uses built-in .NET UIAutomation via a small PowerShell helper (no windows-mcp).
Mouse/keyboard/screenshot use ctypes only.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from .screen1_ui_acceptance_focus import FocusGuardError

if sys.platform != "win32":
    raise FocusGuardError("UIA backend requires Windows")

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.ReleaseDC.restype = ctypes.c_int
user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, ctypes.c_uint]
user32.PrintWindow.restype = wintypes.BOOL
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.SetCursorPos.restype = wintypes.BOOL
user32.mouse_event.argtypes = [
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.c_ulong,
]
user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_ulong]

_HELPER = Path(__file__).resolve().parents[1] / "tools" / "windows" / "screen1_ui_acceptance_uia.ps1"


def _run_uia(action: str, hwnd: int, name: str = "") -> str:
    if not _HELPER.is_file():
        raise FocusGuardError(f"missing UIA helper: {_HELPER}")
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(_HELPER),
            "-Action",
            action,
            "-Hwnd",
            str(int(hwnd)),
            "-Name",
            name,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()
        raise FocusGuardError(f"UIA {action} failed: {err}")
    return (completed.stdout or "").strip()


def element_exists(hwnd: int, name: str) -> bool:
    return _run_uia("exists", hwnd, name).lower() == "true"


def invoke_by_name(hwnd: int, name: str) -> None:
    _run_uia("invoke", hwnd, name)


def list_interactive_names(hwnd: int) -> list[str]:
    raw = _run_uia("names", hwnd, "")
    if not raw:
        return []
    return [line.strip() for line in raw.splitlines() if line.strip()]


def wait_until(predicate, *, timeout_sec: float, interval_sec: float = 0.25) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval_sec)
    return bool(predicate())


def send_escape() -> None:
    VK_ESCAPE = 0x1B
    KEYEVENTF_KEYUP = 0x0002
    user32.keybd_event(VK_ESCAPE, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(VK_ESCAPE, 0, KEYEVENTF_KEYUP, 0)


def click_screen(x: int, y: int) -> None:
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.05)
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def capture_window_bmp(hwnd: int, path: Path) -> None:
    import struct

    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise FocusGuardError("GetWindowRect failed for capture")
    width = int(rect.right - rect.left)
    height = int(rect.bottom - rect.top)
    if width <= 0 or height <= 0:
        raise FocusGuardError("invalid window size for capture")
    hdc_screen = user32.GetDC(0)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
    hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, width, height)
    gdi32.SelectObject(hdc_mem, hbmp)
    PW_RENDERFULLCONTENT = 0x00000002
    user32.PrintWindow(hwnd, hdc_mem, PW_RENDERFULLCONTENT)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", wintypes.LONG),
            ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    bi = BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.biWidth = width
    bi.biHeight = -height
    bi.biPlanes = 1
    bi.biBitCount = 24
    bi.biCompression = 0
    row_stride = ((width * 3 + 3) // 4) * 4
    image_size = row_stride * height
    buf = (ctypes.c_ubyte * image_size)()
    gdi32.GetDIBits(hdc_mem, hbmp, 0, height, ctypes.byref(buf), ctypes.byref(bi), 0)
    off_bits = 14 + ctypes.sizeof(BITMAPINFOHEADER)
    file_header = struct.pack("<2sIHHI", b"BM", off_bits + image_size, 0, 0, off_bits)
    info_header = struct.pack(
        "<IiiHHIIiiII",
        ctypes.sizeof(BITMAPINFOHEADER),
        width,
        -height,
        1,
        24,
        0,
        image_size,
        0,
        0,
        0,
        0,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(file_header)
        handle.write(info_header)
        handle.write(bytes(buf))
    gdi32.DeleteObject(hbmp)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(0, hdc_screen)


def region_mean_luma(path: Path, *, x_ratio0: float, x_ratio1: float) -> float:
    data = path.read_bytes()
    if data[0:2] != b"BM":
        raise FocusGuardError("not a BMP")
    offset = int.from_bytes(data[10:14], "little")
    width = int.from_bytes(data[18:22], "little", signed=True)
    height = abs(int.from_bytes(data[22:26], "little", signed=True))
    row_stride = ((width * 3 + 3) // 4) * 4
    x0 = max(0, min(width - 1, int(width * x_ratio0)))
    x1 = max(x0 + 1, min(width, int(width * x_ratio1)))
    total = 0
    count = 0
    for y in range(0, height, 2):
        row = offset + y * row_stride
        for x in range(x0, x1, 2):
            i = row + x * 3
            b, g, r = data[i], data[i + 1], data[i + 2]
            total += (r * 3 + g * 6 + b) // 10
            count += 1
    return (total / count) if count else 0.0


def dump_names_json(hwnd: int, path: Path) -> None:
    names = list_interactive_names(hwnd)
    path.write_text(json.dumps({"interactive_names": names}, indent=2) + "\n", encoding="utf-8")
