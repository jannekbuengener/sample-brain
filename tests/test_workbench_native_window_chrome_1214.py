"""#1214 Native Windows title-bar theme inheritance — FROZEN RED CONTRACT.

Status: TEST_FREEZE
Canon: #1214 issue acceptance, #1255 windowChrome.* hook

Native caption consumes Appearance windowChrome tokens via a small fail-soft
platform adapter. No frameless QML caption. No second Windows-only palette.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from src import workbench_appearance as appearance
from src import workbench_native_window_chrome as chrome
from src import workbench_theme as theme
from src.workbench_qml import QML_SOURCE


# DWM attribute ids (Windows 11 caption theming surface).
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_BORDER_COLOR = 34
DWMWA_CAPTION_COLOR = 35
DWMWA_TEXT_COLOR = 36


class _FakeWindow:
    def __init__(self, hwnd: int = 0x1234) -> None:
        self._hwnd = hwnd

    def winId(self) -> int:
        return self._hwnd


class _FakeAuthority:
    def __init__(self) -> None:
        self.windowChromeBackground = "#0b0d10"
        self.windowChromeForeground = "#e4e6ea"
        self.windowChromeBorder = "#23262c"
        self._handlers: list[Any] = []

        class _Signal:
            def __init__(self, outer: "_FakeAuthority") -> None:
                self._outer = outer

            def connect(self, handler: Any) -> None:
                self._outer._handlers.append(handler)

        self.appearanceChanged = _Signal(self)

    def emit(self, generation: int = 1) -> None:
        for handler in list(self._handlers):
            handler(generation)


def test_module_import_does_not_require_win32() -> None:
    assert chrome.NATIVE_WINDOW_CHROME_EXIT == "NATIVE_WINDOW_CHROME_THEME_LIVE"
    assert callable(chrome.apply_window_chrome)
    assert callable(chrome.wire_theme_authority)


def test_hex_to_colorref_is_bbggrr() -> None:
    assert chrome.hex_to_colorref("#0b0d10") == 0x00100D0B
    assert chrome.hex_to_colorref("#e4e6ea") == 0x00EAE6E4
    assert chrome.hex_to_colorref("not-a-color") is None
    assert chrome.hex_to_colorref("#8f0e24") == 0x00240E8F


def test_non_windows_platform_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chrome.sys, "platform", "linux")
    assert chrome.is_supported() is False
    calls: list[tuple[Any, ...]] = []

    def _setter(*args: Any) -> None:
        calls.append(args)

    ok = chrome.apply_window_chrome(
        _FakeWindow(),
        background="#0b0d10",
        foreground="#e4e6ea",
        border="#23262c",
        dwm_setter=_setter,
    )
    assert ok is False
    assert calls == []


def test_missing_hwnd_fails_soft(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chrome.sys, "platform", "win32")
    ok = chrome.apply_window_chrome(
        _FakeWindow(hwnd=0),
        background="#0b0d10",
        foreground="#e4e6ea",
        border="#23262c",
    )
    assert ok is False


def test_apply_sets_caption_text_border_and_dark_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chrome.sys, "platform", "win32")
    recorded: list[tuple[int, int, int]] = []

    def _setter(hwnd: int, attribute: int, value: int) -> None:
        recorded.append((hwnd, attribute, value))

    ok = chrome.apply_window_chrome(
        _FakeWindow(0xABC),
        background="#0b0d10",
        foreground="#e4e6ea",
        border="#23262c",
        dwm_setter=_setter,
    )
    assert ok is True
    attrs = {attribute: value for _hwnd, attribute, value in recorded}
    assert attrs[DWMWA_CAPTION_COLOR] == chrome.hex_to_colorref("#0b0d10")
    assert attrs[DWMWA_TEXT_COLOR] == chrome.hex_to_colorref("#e4e6ea")
    assert attrs[DWMWA_BORDER_COLOR] == chrome.hex_to_colorref("#23262c")
    assert attrs[DWMWA_USE_IMMERSIVE_DARK_MODE] == 1
    assert all(hwnd == 0xABC for hwnd, _a, _v in recorded)


def test_light_chrome_disables_immersive_dark_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chrome.sys, "platform", "win32")
    recorded: dict[int, int] = {}

    def _setter(_hwnd: int, attribute: int, value: int) -> None:
        recorded[attribute] = value

    ok = chrome.apply_window_chrome(
        _FakeWindow(),
        background="#f7f7f5",
        foreground="#171719",
        border="#d8d8d4",
        dwm_setter=_setter,
    )
    assert ok is True
    assert recorded[DWMWA_USE_IMMERSIVE_DARK_MODE] == 0
    assert recorded[DWMWA_CAPTION_COLOR] == chrome.hex_to_colorref("#f7f7f5")


def test_dwm_attribute_errors_fail_soft(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chrome.sys, "platform", "win32")

    def _setter(_hwnd: int, attribute: int, _value: int) -> None:
        if attribute == DWMWA_CAPTION_COLOR:
            raise OSError("unsupported attribute")

    # Partial support must not raise into the launch path.
    ok = chrome.apply_window_chrome(
        _FakeWindow(),
        background="#0b0d10",
        foreground="#e4e6ea",
        border="#23262c",
        dwm_setter=_setter,
    )
    assert ok is True  # at least immersive dark / remaining attrs may succeed


def test_window_chrome_tokens_come_from_appearance_not_accent() -> None:
    snapshot = appearance.resolve_appearance(
        appearance.AppearanceRequestedState(
            shared=appearance.AppearanceProfileInput(theme_ref="Blood"),
        )
    )
    tokens = snapshot.tokens.as_flat_dict()
    assert tokens["windowChrome.background"] == snapshot.background
    assert tokens["windowChrome.foreground"] == tokens["text.primary"]
    assert tokens["windowChrome.border"] == tokens["border.subtle"]
    assert tokens["windowChrome.background"] != snapshot.accent
    assert tokens["windowChrome.background"].lower() != "#8f0e24"


def test_wire_applies_initial_and_live_appearance_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chrome.sys, "platform", "win32")
    applied: list[tuple[str, str, str]] = []

    def _apply(window: Any, *, background: str, foreground: str, border: str, **_kwargs: Any) -> bool:
        del window
        applied.append((background.lower(), foreground.lower(), border.lower()))
        return True

    monkeypatch.setattr(chrome, "apply_window_chrome", _apply)
    authority = _FakeAuthority()
    handle = chrome.wire_theme_authority(_FakeWindow(), authority)
    assert handle is not None
    assert applied == [("#0b0d10", "#e4e6ea", "#23262c")]

    authority.windowChromeBackground = "#121417"
    authority.windowChromeForeground = "#f0f2f5"
    authority.windowChromeBorder = "#33363c"
    authority.emit(2)
    assert applied[-1] == ("#121417", "#f0f2f5", "#33363c")


def test_wire_uses_bridge_window_chrome_properties(tmp_path: Path) -> None:
    pytest.importorskip("PySide6")
    from src.workbench_qml import _qml_theme_authority_bridge

    bridge = _qml_theme_authority_bridge(state_dir=tmp_path)
    snap = appearance.resolve_appearance(theme.load_appearance_preferences(state_dir=tmp_path))
    assert bridge.windowChromeBackground.lower() == snap.tokens.window_chrome_background.lower()
    assert bridge.windowChromeForeground.lower() == snap.tokens.window_chrome_foreground.lower()
    assert bridge.windowChromeBorder.lower() == snap.tokens.window_chrome_border.lower()

    bridge.selectTheme("Carbon")
    carbon = appearance.resolve_appearance(theme.load_appearance_preferences(state_dir=tmp_path))
    assert bridge.windowChromeBackground.lower() == carbon.tokens.window_chrome_background.lower()
    assert bridge.windowChromeBackground.lower() != snap.tokens.window_chrome_background.lower()


def test_qml_engine_wires_native_chrome_adapter() -> None:
    from pathlib import Path as _Path

    from src import workbench_qml as qml_mod

    source = _Path(qml_mod.__file__).read_text(encoding="utf-8")
    assert "workbench_native_window_chrome" in source
    assert "wire_theme_authority" in source
    # QML must not own Win32/DWM styling.
    assert "DwmSetWindowAttribute" not in QML_SOURCE
    assert "DWMWA_" not in QML_SOURCE
    assert "winId(" not in QML_SOURCE


def test_preset_switch_updates_chrome_tokens_without_accent_flood(tmp_path: Path) -> None:
    pytest.importorskip("PySide6")
    from src.workbench_qml import _qml_theme_authority_bridge

    bridge = _qml_theme_authority_bridge(state_dir=tmp_path)
    for name in ("Blood", "Carbon", "Arctic"):
        bridge.selectTheme(name)
        assert bridge.windowChromeBackground.startswith("#")
        assert bridge.windowChromeForeground.startswith("#")
        assert bridge.windowChromeBorder.startswith("#")
        assert bridge.windowChromeBackground.lower() != bridge.actionActive.lower()


@pytest.mark.skipif(sys.platform != "win32", reason="live HWND probe is Windows-only")
def test_live_hwnd_apply_does_not_raise() -> None:
    pytest.importorskip("PySide6")
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQuick import QQuickWindow

    app = QGuiApplication.instance() or QGuiApplication([])
    window = QQuickWindow()
    window.setTitle("Sample Brain chrome probe")
    window.resize(320, 200)
    window.show()
    app.processEvents()
    try:
        ok = chrome.apply_window_chrome(
            window,
            background="#0b0d10",
            foreground="#e4e6ea",
            border="#23262c",
        )
        # Supported Windows builds return True; older builds may fail soft.
        assert ok in {True, False}
    finally:
        window.close()
        app.processEvents()
