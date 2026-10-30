"""FL-gated Windows input capture — evolved from #1320 probe."""

from __future__ import annotations

import ctypes
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

if sys.platform == "win32":
    import ctypes.wintypes as wintypes
else:  # pragma: no cover
    wintypes = None  # type: ignore

WH_MOUSE_LL = 14
WH_KEYBOARD_LL = 13
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_MOUSEWHEEL = 0x020A
WM_MOUSEHWHEEL = 0x020E
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
HC_ACTION = 0

VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_ESCAPE = 0x1B
VK_DELETE = 0x2E
VK_BACK = 0x08
VK_RETURN = 0x0D
VK_INSERT = 0x2D
VK_TAB = 0x09
VK_LEFT = 0x25
VK_UP = 0x26
VK_RIGHT = 0x27
VK_DOWN = 0x28
VK_HOME = 0x24
VK_END = 0x23
VK_PRIOR = 0x21
VK_NEXT = 0x22
VK_F1 = 0x70
VK_F12 = 0x7B

FL_PROCESS_TOKENS = ("fl64.exe", "fl.exe", "fl studio", "flstudio")


class WindowsCapture:
    """Low-level hooks writing privacy-safe events to windows-events.jsonl."""

    def __init__(
        self,
        spool_path: Path,
        *,
        on_fg_change: Callable[[bool], None] | None = None,
    ) -> None:
        if sys.platform != "win32":
            raise RuntimeError("WindowsCapture requires win32")
        self.spool_path = Path(spool_path)
        self.on_fg_change = on_fg_change
        self._seq = 0
        self._fl_foreground = False
        self._drag = None
        self._mouse_hook = None
        self._kb_hook = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._user32 = ctypes.windll.user32
        self._kernel32 = ctypes.windll.kernel32
        self._psapi = ctypes.windll.psapi
        self._last_event_wall_ns: int | None = None

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        class MSLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [
                ("pt", POINT),
                ("mouseData", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
            ]

        class KBDLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [
                ("vkCode", wintypes.DWORD),
                ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
            ]

        self._POINT = POINT
        self._MSLLHOOKSTRUCT = MSLLHOOKSTRUCT
        self._KBDLLHOOKSTRUCT = KBDLLHOOKSTRUCT
        LowLevelMouseProc = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
        )
        LowLevelKeyboardProc = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
        )
        self._mouse_proc_ref = LowLevelMouseProc(self._on_mouse)
        self._kb_proc_ref = LowLevelKeyboardProc(self._on_keyboard)
        # Pointer-sized Win32 signatures — untyped CallNextHookEx truncates lParam on x64.
        self._user32.CallNextHookEx.argtypes = [
            wintypes.HHOOK,
            ctypes.c_int,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        self._user32.CallNextHookEx.restype = ctypes.c_long
        self._user32.SetWindowsHookExW.argtypes = [
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.HINSTANCE,
            wintypes.DWORD,
        ]
        self._user32.SetWindowsHookExW.restype = wintypes.HHOOK
        self._user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
        self._user32.UnhookWindowsHookEx.restype = wintypes.BOOL

    @property
    def fl_foreground(self) -> bool:
        return self._fl_foreground

    @property
    def last_event_wall_ns(self) -> int | None:
        return self._last_event_wall_ns

    def _utc_from_wall_ns(self, wall_ns: int) -> str:
        sec = wall_ns / 1_000_000_000
        return datetime.fromtimestamp(sec, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    def _emit(self, event_type: str, props: dict | None = None) -> None:
        with self._lock:
            self._seq += 1
            wall_ns = time.time_ns()
            mono_ns = time.monotonic_ns()
            evt = {
                "schema": "sb.fl_workflow_recorder.event.v1",
                "seq": self._seq,
                "t_mono_ns": mono_ns,
                "t_wall_ns": wall_ns,
                "t_utc": self._utc_from_wall_ns(wall_ns),
                "source": "win",
                "type": event_type,
                "props": props or {},
            }
            line = json.dumps(evt, ensure_ascii=True, separators=(",", ":")) + "\n"
            self.spool_path.parent.mkdir(parents=True, exist_ok=True)
            with self.spool_path.open("a", encoding="utf-8") as fh:
                fh.write(line)
            self._last_event_wall_ns = wall_ns

    def _foreground_process_name(self) -> str:
        hwnd = self._user32.GetForegroundWindow()
        if not hwnd:
            return ""
        pid = wintypes.DWORD()
        self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return ""
        access = 0x0410
        hproc = self._kernel32.OpenProcess(access, False, pid.value)
        if not hproc:
            hproc = self._kernel32.OpenProcess(0x1000, False, pid.value)
        if not hproc:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(512)
            if self._psapi.GetModuleBaseNameW(hproc, None, buf, 512):
                return buf.value.lower()
            size = wintypes.DWORD(512)
            full = ctypes.create_unicode_buffer(512)
            if self._kernel32.QueryFullProcessImageNameW(hproc, 0, full, ctypes.byref(size)):
                return os.path.basename(full.value).lower()
            return ""
        finally:
            self._kernel32.CloseHandle(hproc)

    def _is_fl_process(self, name: str) -> bool:
        if not name:
            return False
        n = name.lower()
        return any(tok in n for tok in FL_PROCESS_TOKENS)

    def _poll_foreground_loop(self) -> None:
        while not self._stop.is_set():
            try:
                name = self._foreground_process_name()
                is_fl = self._is_fl_process(name)
                if is_fl != self._fl_foreground:
                    prev = self._fl_foreground
                    self._fl_foreground = is_fl
                    self._emit(
                        "FG",
                        {
                            "fl_foreground": is_fl,
                            "prev": prev,
                            "process": name if is_fl else ("redacted_non_fl" if name else ""),
                            "event": "FL_FOREGROUND" if is_fl else "FL_BACKGROUND",
                        },
                    )
                    if self.on_fg_change:
                        try:
                            self.on_fg_change(is_fl)
                        except Exception:
                            pass
            except Exception as exc:
                self._emit("PROBE_WARN", {"where": "foreground_poll", "error": type(exc).__name__})
            self._stop.wait(0.15)

    def _modifiers(self) -> dict:
        return {
            "ctrl": bool(self._user32.GetAsyncKeyState(VK_CONTROL) & 0x8000),
            "alt": bool(self._user32.GetAsyncKeyState(VK_MENU) & 0x8000),
            "shift": bool(self._user32.GetAsyncKeyState(VK_SHIFT) & 0x8000),
            "win": bool(
                (self._user32.GetAsyncKeyState(VK_LWIN) & 0x8000)
                or (self._user32.GetAsyncKeyState(VK_RWIN) & 0x8000)
            ),
        }

    def _vk_name(self, vk: int) -> str:
        special = {
            VK_ESCAPE: "Escape",
            VK_DELETE: "Delete",
            VK_BACK: "Backspace",
            VK_RETURN: "Enter",
            VK_INSERT: "Insert",
            VK_TAB: "Tab",
            VK_LEFT: "Left",
            VK_UP: "Up",
            VK_RIGHT: "Right",
            VK_DOWN: "Down",
            VK_HOME: "Home",
            VK_END: "End",
            VK_PRIOR: "PageUp",
            VK_NEXT: "PageDown",
        }
        if vk in special:
            return special[vk]
        if VK_F1 <= vk <= VK_F12:
            return "F%d" % (vk - VK_F1 + 1)
        if 0x30 <= vk <= 0x39:
            return chr(vk)
        if 0x41 <= vk <= 0x5A:
            return chr(vk)
        return "VK_0x%02X" % vk

    def _is_identity_key(self, vk: int) -> bool:
        if vk in (
            VK_ESCAPE,
            VK_DELETE,
            VK_BACK,
            VK_RETURN,
            VK_INSERT,
            VK_TAB,
            VK_LEFT,
            VK_UP,
            VK_RIGHT,
            VK_DOWN,
            VK_HOME,
            VK_END,
            VK_PRIOR,
            VK_NEXT,
        ):
            return True
        if VK_F1 <= vk <= VK_F12:
            return True
        return False

    def _is_printable_unmodified(self, vk: int) -> bool:
        if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
            return True
        # Numeric keypad digits / decimal (printable when Num Lock on).
        if 0x60 <= vk <= 0x69 or vk == 0x6E:
            return True
        if vk in (0x20, 0xBA, 0xBB, 0xBC, 0xBD, 0xBE, 0xBF, 0xC0, 0xDB, 0xDC, 0xDD, 0xDE):
            return True
        return False

    def _classify_key(self, vk: int) -> tuple[str, dict]:
        mods = self._modifiers()
        any_mod = mods["ctrl"] or mods["alt"] or mods["win"]
        if self._is_identity_key(vk):
            return "KEY_CMD", {"vk": vk, "key": self._vk_name(vk), "mods": mods}
        if any_mod:
            return "KEY_CMD", {"vk": vk, "key": self._vk_name(vk), "mods": mods}
        if self._is_printable_unmodified(vk):
            return "TEXT_ENTRY", {"redacted": True, "mods": mods}
        if vk in (VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN):
            return "KEY_MOD_ONLY", {"vk": vk, "mods": mods}
        return "KEY_OTHER", {"vk": vk, "key": self._vk_name(vk), "mods": mods}

    def _button_name(self, msg: int) -> str | None:
        return {
            WM_LBUTTONDOWN: "left_down",
            WM_LBUTTONUP: "left_up",
            WM_RBUTTONDOWN: "right_down",
            WM_RBUTTONUP: "right_up",
            WM_MBUTTONDOWN: "middle_down",
            WM_MBUTTONUP: "middle_up",
        }.get(int(msg))

    def _fl_foreground_now(self) -> bool:
        """Revalidate live foreground ownership (do not trust the 150ms poll cache alone)."""
        try:
            return self._is_fl_process(self._foreground_process_name())
        except Exception:
            return False

    def _on_mouse(self, nCode, wParam, lParam):
        try:
            if nCode == HC_ACTION and self._fl_foreground_now():
                info = ctypes.cast(lParam, ctypes.POINTER(self._MSLLHOOKSTRUCT)).contents
                x, y = int(info.pt.x), int(info.pt.y)
                msg = int(wParam)
                btn = self._button_name(msg)
                if btn:
                    kind, phase = btn.split("_")
                    self._emit("CLICK", {"button": kind, "phase": phase, "x": x, "y": y})
                    if kind == "left" and phase == "down":
                        self._drag = {
                            "start_x": x,
                            "start_y": y,
                            "start_mono_ns": time.monotonic_ns(),
                        }
                        self._emit("DRAG", {"phase": "start", "x": x, "y": y})
                    elif kind == "left" and phase == "up" and self._drag is not None:
                        dx = x - self._drag["start_x"]
                        dy = y - self._drag["start_y"]
                        dist = (dx * dx + dy * dy) ** 0.5
                        dur_ms = (time.monotonic_ns() - self._drag["start_mono_ns"]) / 1_000_000.0
                        self._emit(
                            "DRAG",
                            {
                                "phase": "end",
                                "x": x,
                                "y": y,
                                "dx": dx,
                                "dy": dy,
                                "distance_px": round(dist, 2),
                                "duration_ms": round(dur_ms, 2),
                            },
                        )
                        self._drag = None
                elif msg in (WM_MOUSEWHEEL, WM_MOUSEHWHEEL):
                    delta = ctypes.c_short(info.mouseData >> 16).value
                    self._emit(
                        "WHEEL",
                        {
                            "delta": int(delta),
                            "horizontal": msg == WM_MOUSEHWHEEL,
                            "x": x,
                            "y": y,
                        },
                    )
        except Exception:
            pass
        return self._user32.CallNextHookEx(self._mouse_hook, nCode, wParam, lParam)

    def _on_keyboard(self, nCode, wParam, lParam):
        try:
            if nCode == HC_ACTION and self._fl_foreground_now():
                msg = int(wParam)
                if msg in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    info = ctypes.cast(lParam, ctypes.POINTER(self._KBDLLHOOKSTRUCT)).contents
                    vk = int(info.vkCode)
                    etype, props = self._classify_key(vk)
                    if etype == "KEY_MOD_ONLY":
                        return self._user32.CallNextHookEx(self._kb_hook, nCode, wParam, lParam)
                    if etype == "KEY_OTHER":
                        self._emit("KEY_CMD", {**props, "class": "other_no_content"})
                    else:
                        self._emit(etype, props)
        except Exception:
            pass
        return self._user32.CallNextHookEx(self._kb_hook, nCode, wParam, lParam)

    def start(self) -> None:
        self.spool_path.parent.mkdir(parents=True, exist_ok=True)
        self._emit("RECORDER_INIT", {"pid": os.getpid(), "component": "windows_capture"})
        self._emit("CLOCK_MARKER", {"marker": "win_start", "pair_hint": "align_with_fl"})
        self._thread = threading.Thread(target=self._run, name="win-capture", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        fg = threading.Thread(target=self._poll_foreground_loop, name="fg-poll", daemon=True)
        fg.start()
        self._mouse_hook = self._user32.SetWindowsHookExW(
            WH_MOUSE_LL, self._mouse_proc_ref, None, 0
        )
        self._kb_hook = self._user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._kb_proc_ref, None, 0
        )
        try:
            while not self._stop.is_set():
                msg = wintypes.MSG()
                while self._user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1):
                    self._user32.TranslateMessage(ctypes.byref(msg))
                    self._user32.DispatchMessageW(ctypes.byref(msg))
                time.sleep(0.01)
        finally:
            self._uninstall_hooks()
            self._emit("RECORDER_DEINIT", {"component": "windows_capture"})

    def _uninstall_hooks(self) -> None:
        if self._mouse_hook:
            self._user32.UnhookWindowsHookEx(self._mouse_hook)
            self._mouse_hook = None
        if self._kb_hook:
            self._user32.UnhookWindowsHookEx(self._kb_hook)
            self._kb_hook = None

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        self._uninstall_hooks()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
