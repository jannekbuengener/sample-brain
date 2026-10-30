"""
#1320 Windows FL-gated input probe (throwaway).

Writes ONLY:
  %LOCALAPPDATA%\\sample-brain\\workflow-observer-probe\\windows-events.jsonl

Privacy:
  - Records only while FL Studio is the foreground process (plus FG/BG transitions).
  - Fail-closed keyboard: KEY_CMD identity only for modifier chords / F-keys /
    navigation / Escape/Delete/Backspace/Enter/Insert. Printable unmodified
    characters become TEXT_ENTRY with no character value.
  - No screenshots, clipboard, audio, mouse-move stream, or system-wide logging
    when FL is not foreground.
"""

from __future__ import annotations

import argparse
import atexit
import ctypes
import ctypes.wintypes as wintypes
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi

SPOOL_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local"),
    "sample-brain",
    "workflow-observer-probe",
)
WIN_EVENTS_PATH = os.path.join(SPOOL_DIR, "windows-events.jsonl")
META_PATH = os.path.join(SPOOL_DIR, "win-probe-meta.json")

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

# Virtual keys
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt
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

_seq = 0
_fl_foreground = False
_drag = None  # dict while drag active
_mouse_hook = None
_kb_hook = None
_stop = threading.Event()
_lock = threading.Lock()


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


LowLevelMouseProc = ctypes.WINFUNCTYPE(
    ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
)
LowLevelKeyboardProc = ctypes.WINFUNCTYPE(
    ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
)


def _ensure_spool():
    os.makedirs(SPOOL_DIR, exist_ok=True)


def _utc_from_wall_ns(wall_ns: int) -> str:
    sec = wall_ns / 1_000_000_000
    return datetime.fromtimestamp(sec, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _emit(event_type: str, props: dict | None = None) -> None:
    global _seq
    with _lock:
        _seq += 1
        wall_ns = time.time_ns()
        mono_ns = time.monotonic_ns()
        evt = {
            "schema": "sb.fl_workflow_signal_probe.v1",
            "seq": _seq,
            "t_mono_ns": mono_ns,
            "t_wall_ns": wall_ns,
            "t_utc": _utc_from_wall_ns(wall_ns),
            "source": "win",
            "type": event_type,
            "props": props or {},
        }
        line = json.dumps(evt, ensure_ascii=True, separators=(",", ":")) + "\n"
        with open(WIN_EVENTS_PATH, "a", encoding="utf-8") as fh:
            fh.write(line)


def _write_meta(extra: dict | None = None) -> None:
    meta = {
        "schema": "sb.fl_workflow_signal_probe.win_meta.v1",
        "spool_role": "windows-events.jsonl",
        "fl_foreground": _fl_foreground,
        "updated_t_wall_ns": time.time_ns(),
        "updated_t_utc": _utc_from_wall_ns(time.time_ns()),
    }
    if extra:
        meta.update(extra)
    with open(META_PATH, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)


def _foreground_process_name() -> str:
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""
    access = 0x0410  # QUERY_INFORMATION | VM_READ
    hproc = kernel32.OpenProcess(access, False, pid.value)
    if not hproc:
        access = 0x1000  # PROCESS_QUERY_LIMITED_INFORMATION
        hproc = kernel32.OpenProcess(access, False, pid.value)
    if not hproc:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(512)
        if psapi.GetModuleBaseNameW(hproc, None, buf, 512):
            return buf.value.lower()
        # Fallback QueryFullProcessImageNameW
        size = wintypes.DWORD(512)
        full = ctypes.create_unicode_buffer(512)
        if kernel32.QueryFullProcessImageNameW(hproc, 0, full, ctypes.byref(size)):
            return os.path.basename(full.value).lower()
        return ""
    finally:
        kernel32.CloseHandle(hproc)


def _is_fl_process(name: str) -> bool:
    if not name:
        return False
    n = name.lower()
    return any(tok in n for tok in FL_PROCESS_TOKENS)


def _poll_foreground_loop():
    global _fl_foreground
    while not _stop.is_set():
        try:
            name = _foreground_process_name()
            is_fl = _is_fl_process(name)
            if is_fl != _fl_foreground:
                prev = _fl_foreground
                _fl_foreground = is_fl
                _emit(
                    "FG",
                    {
                        "fl_foreground": is_fl,
                        "prev": prev,
                        "process": name if is_fl else ("redacted_non_fl" if name else ""),
                        "event": "FL_FOREGROUND" if is_fl else "FL_BACKGROUND",
                    },
                )
                _write_meta()
        except Exception as exc:
            _emit("PROBE_WARN", {"where": "foreground_poll", "error": type(exc).__name__})
        _stop.wait(0.15)


def _modifiers() -> dict:
    return {
        "ctrl": bool(user32.GetAsyncKeyState(VK_CONTROL) & 0x8000),
        "alt": bool(user32.GetAsyncKeyState(VK_MENU) & 0x8000),
        "shift": bool(user32.GetAsyncKeyState(VK_SHIFT) & 0x8000),
        "win": bool(
            (user32.GetAsyncKeyState(VK_LWIN) & 0x8000)
            or (user32.GetAsyncKeyState(VK_RWIN) & 0x8000)
        ),
    }


def _vk_name(vk: int) -> str:
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
    # Letter/digit identity only used when a modifier is held (KEY_CMD path).
    if 0x30 <= vk <= 0x39:
        return chr(vk)
    if 0x41 <= vk <= 0x5A:
        return chr(vk)
    return "VK_0x%02X" % vk


def _is_identity_key(vk: int) -> bool:
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


def _is_printable_unmodified(vk: int) -> bool:
    # Letters, digits, OEM printable-ish keys without modifiers → TEXT_ENTRY.
    if 0x30 <= vk <= 0x39:
        return True
    if 0x41 <= vk <= 0x5A:
        return True
    # Space and common OEM keys
    if vk in (0x20, 0xBA, 0xBB, 0xBC, 0xBD, 0xBE, 0xBF, 0xC0, 0xDB, 0xDC, 0xDD, 0xDE):
        return True
    return False


def _classify_key(vk: int) -> tuple[str, dict]:
    mods = _modifiers()
    any_mod = mods["ctrl"] or mods["alt"] or mods["win"]
    # Shift alone on a letter is still potentially typing; require ctrl/alt/win
    # OR identity-class keys for KEY_CMD. Shift+F-key / Shift+Nav still KEY_CMD.
    if _is_identity_key(vk):
        return "KEY_CMD", {"vk": vk, "key": _vk_name(vk), "mods": mods}
    if any_mod:
        # Modifier chord — store identity (may include letter shortcuts like Ctrl+Z).
        return "KEY_CMD", {"vk": vk, "key": _vk_name(vk), "mods": mods}
    if mods["shift"] and _is_identity_key(vk):
        return "KEY_CMD", {"vk": vk, "key": _vk_name(vk), "mods": mods}
    if _is_printable_unmodified(vk):
        # Fail-closed: no character value.
        return "TEXT_ENTRY", {"redacted": True, "mods": mods}
    # Unknown non-printable without mods — skip or classify as KEY_CMD without char.
    if vk in (VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN):
        return "KEY_MOD_ONLY", {"vk": vk, "mods": mods}
    return "KEY_OTHER", {"vk": vk, "key": _vk_name(vk), "mods": mods}


def _button_name(msg: int) -> str | None:
    return {
        WM_LBUTTONDOWN: "left_down",
        WM_LBUTTONUP: "left_up",
        WM_RBUTTONDOWN: "right_down",
        WM_RBUTTONUP: "right_up",
        WM_MBUTTONDOWN: "middle_down",
        WM_MBUTTONUP: "middle_up",
    }.get(int(msg))


def _on_mouse(nCode, wParam, lParam):
    global _drag
    try:
        if nCode == HC_ACTION:
            # Always allow FG detection path; only emit click/drag/wheel when FL fg.
            info = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            x, y = int(info.pt.x), int(info.pt.y)
            msg = int(wParam)
            if _fl_foreground:
                btn = _button_name(msg)
                if btn:
                    kind, phase = btn.split("_")
                    _emit(
                        "CLICK",
                        {
                            "button": kind,
                            "phase": phase,
                            "x": x,
                            "y": y,
                        },
                    )
                    if kind == "left" and phase == "down":
                        _drag = {
                            "start_x": x,
                            "start_y": y,
                            "start_wall_ns": time.time_ns(),
                            "start_mono_ns": time.monotonic_ns(),
                        }
                        _emit("DRAG", {"phase": "start", "x": x, "y": y})
                    elif kind == "left" and phase == "up" and _drag is not None:
                        dx = x - _drag["start_x"]
                        dy = y - _drag["start_y"]
                        dist = (dx * dx + dy * dy) ** 0.5
                        dur_ms = (time.monotonic_ns() - _drag["start_mono_ns"]) / 1_000_000.0
                        _emit(
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
                        _drag = None
                elif msg in (WM_MOUSEWHEEL, WM_MOUSEHWHEEL):
                    delta = ctypes.c_short(info.mouseData >> 16).value
                    _emit(
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
    return user32.CallNextHookEx(_mouse_hook, nCode, wParam, lParam)


def _on_keyboard(nCode, wParam, lParam):
    try:
        if nCode == HC_ACTION and _fl_foreground:
            msg = int(wParam)
            if msg in (WM_KEYDOWN, WM_SYSKEYDOWN):
                info = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                vk = int(info.vkCode)
                etype, props = _classify_key(vk)
                if etype == "KEY_MOD_ONLY":
                    return user32.CallNextHookEx(_kb_hook, nCode, wParam, lParam)
                if etype == "KEY_OTHER":
                    # Still fail-closed: do not store unknown as typed text content.
                    _emit("KEY_CMD", {**props, "class": "other_no_content"})
                else:
                    _emit(etype, props)
    except Exception:
        pass
    return user32.CallNextHookEx(_kb_hook, nCode, wParam, lParam)


_mouse_proc_ref = LowLevelMouseProc(_on_mouse)
_kb_proc_ref = LowLevelKeyboardProc(_on_keyboard)


def _install_hooks():
    global _mouse_hook, _kb_hook
    _mouse_hook = user32.SetWindowsHookExW(WH_MOUSE_LL, _mouse_proc_ref, None, 0)
    _kb_hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, _kb_proc_ref, None, 0)
    if not _mouse_hook or not _kb_hook:
        raise OSError("SetWindowsHookExW failed (mouse=%s kb=%s)" % (_mouse_hook, _kb_hook))


def _uninstall_hooks():
    global _mouse_hook, _kb_hook
    if _mouse_hook:
        user32.UnhookWindowsHookEx(_mouse_hook)
        _mouse_hook = None
    if _kb_hook:
        user32.UnhookWindowsHookEx(_kb_hook)
        _kb_hook = None


def main():
    parser = argparse.ArgumentParser(description="FL-gated Windows input probe (#1320)")
    parser.add_argument(
        "--duration-sec",
        type=float,
        default=0,
        help="Auto-stop after N seconds (0 = until Ctrl+C)",
    )
    parser.add_argument(
        "--marker",
        action="append",
        default=[],
        help="Emit CLOCK_MARKER with this name at startup (repeatable)",
    )
    args = parser.parse_args()

    _ensure_spool()
    _emit("PROBE_INIT", {"pid": os.getpid(), "argv": ["win_fl_input_probe.py"]})
    for m in args.marker or ["win_start"]:
        _emit("CLOCK_MARKER", {"marker": m, "pair_hint": "align_with_fl"})
    _write_meta({"status": "STARTING"})

    fg_thread = threading.Thread(target=_poll_foreground_loop, name="fg-poll", daemon=True)
    fg_thread.start()
    _install_hooks()
    _write_meta({"status": "RUNNING"})
    atexit.register(_uninstall_hooks)

    start = time.monotonic()
    try:
        while not _stop.is_set():
            # Need a message pump for low-level hooks.
            msg = wintypes.MSG()
            while user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            if args.duration_sec and (time.monotonic() - start) >= args.duration_sec:
                break
            time.sleep(0.01)
    except KeyboardInterrupt:
        pass
    finally:
        _stop.set()
        _uninstall_hooks()
        _emit("PROBE_DEINIT", {})
        _write_meta({"status": "STOPPED"})
        print("windows probe stopped; events ->", WIN_EVENTS_PATH)


if __name__ == "__main__":
    if sys.platform != "win32":
        print("This probe must run on Windows.", file=sys.stderr)
        sys.exit(2)
    main()
