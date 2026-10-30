"""FL Studio process detection (Windows-focused, fail-soft elsewhere)."""

from __future__ import annotations

import sys
from dataclasses import dataclass


FL_IMAGE_NAMES = frozenset({"fl64.exe", "fl.exe"})


@dataclass(frozen=True)
class FlProcessInfo:
    alive: bool
    pid: int | None = None
    image: str | None = None


def find_fl_process() -> FlProcessInfo:
    if sys.platform != "win32":
        return FlProcessInfo(alive=False)
    try:
        import ctypes
        from ctypes import wintypes

        # Prefer CreateToolhelp32Snapshot for no extra deps.
        TH32CS_SNAPPROCESS = 0x00000002

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260),
            ]

        kernel32 = ctypes.windll.kernel32
        snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snap == wintypes.HANDLE(-1).value:
            return FlProcessInfo(alive=False)
        try:
            entry = PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            if not kernel32.Process32FirstW(snap, ctypes.byref(entry)):
                return FlProcessInfo(alive=False)
            while True:
                name = (entry.szExeFile or "").lower()
                if name in FL_IMAGE_NAMES:
                    return FlProcessInfo(alive=True, pid=int(entry.th32ProcessID), image=name)
                if not kernel32.Process32NextW(snap, ctypes.byref(entry)):
                    break
        finally:
            kernel32.CloseHandle(snap)
    except Exception:
        return FlProcessInfo(alive=False)
    return FlProcessInfo(alive=False)
