from __future__ import annotations

import importlib

from src.workbench_qml import QML_SOURCE


def _placement_module():
    try:
        return importlib.import_module("src.workbench_window_placement")
    except ModuleNotFoundError:
        return None


class FakeRect:
    def __init__(self, x: int, y: int, width: int, height: int) -> None:
        self._x = x
        self._y = y
        self._width = width
        self._height = height

    def x(self) -> int:
        return self._x

    def y(self) -> int:
        return self._y

    def width(self) -> int:
        return self._width

    def height(self) -> int:
        return self._height


class FakeScreen:
    def __init__(self, geometry: FakeRect, *, fail_geometry: bool = False) -> None:
        self.geometry = geometry
        self.fail_geometry = fail_geometry

    def availableGeometry(self) -> FakeRect:
        if self.fail_geometry:
            raise RuntimeError("screen geometry unavailable")
        return self.geometry


class FakeApp:
    def __init__(self, screen: FakeScreen | None) -> None:
        self.screen = screen

    def primaryScreen(self) -> FakeScreen | None:
        return self.screen


class FakeWindow:
    def __init__(self, width: int = 1600, height: int = 900) -> None:
        self._width = width
        self._height = height
        self.screen = None
        self.position = None
        self.show_calls = 0

    def width(self) -> int:
        return self._width

    def height(self) -> int:
        return self._height

    def setScreen(self, screen: FakeScreen) -> None:
        self.screen = screen

    def setPosition(self, x: int, y: int) -> None:
        self.position = (x, y)

    def show(self) -> None:
        self.show_calls += 1


def test_qml_root_starts_hidden_until_primary_screen_placement():
    root = QML_SOURCE.split("ApplicationWindow {", 1)[1].split("color:", 1)[0]
    assert "visible: false" in root
    assert "visible: true" not in root


def test_centered_position_supports_offset_and_negative_primary_coordinates():
    module = _placement_module()
    assert module is not None, "primary-display placement module must exist"
    centered = module.centered_window_position

    assert centered(FakeRect(0, 0, 1920, 1080), 1600, 900) == (160, 90)
    assert centered(FakeRect(1920, 0, 2560, 1440), 1600, 900) == (2400, 270)
    assert centered(FakeRect(-1920, 0, 1920, 1080), 1600, 900) == (-1760, 90)
    assert centered(FakeRect(0, -1080, 1920, 1080), 1600, 900) == (160, -990)
    assert centered(FakeRect(-1280, 0, 1280, 720), 1600, 900) == (-1280, 0)


def test_show_window_on_primary_screen_assigns_positions_and_shows_once():
    module = _placement_module()
    assert module is not None, "primary-display placement module must exist"
    screen = FakeScreen(FakeRect(-1920, 0, 1920, 1080))
    app = FakeApp(screen)
    window = FakeWindow()

    assert module.show_window_on_primary_screen(app, window) is True
    assert window.screen is screen
    assert window.position == (-1760, 90)
    assert window.show_calls == 1


def test_show_window_on_primary_screen_fails_soft_without_primary_screen():
    module = _placement_module()
    assert module is not None, "primary-display placement module must exist"
    window = FakeWindow()

    assert module.show_window_on_primary_screen(FakeApp(None), window) is False
    assert window.screen is None
    assert window.position is None
    assert window.show_calls == 1


def test_show_window_on_primary_screen_fails_soft_when_geometry_is_unavailable():
    module = _placement_module()
    assert module is not None, "primary-display placement module must exist"
    screen = FakeScreen(FakeRect(0, 0, 1920, 1080), fail_geometry=True)
    window = FakeWindow()

    assert module.show_window_on_primary_screen(FakeApp(screen), window) is False
    assert window.position is None
    assert window.show_calls == 1


class FakeTkRoot:
    def __init__(
        self,
        width: int = 1200,
        height: int = 700,
        min_width: int = 0,
        min_height: int = 0,
    ) -> None:
        self._width = width
        self._height = height
        self._min_width = min_width
        self._min_height = min_height
        self.geometry_calls: list[str] = []
        self.withdraw_calls = 0
        self.deiconify_calls = 0
        self.mainloop_calls = 0

    def withdraw(self) -> None:
        self.withdraw_calls += 1

    def update_idletasks(self) -> None:
        return None

    def winfo_reqwidth(self) -> int:
        return self._width

    def winfo_reqheight(self) -> int:
        return self._height

    def minsize(self) -> tuple[int, int]:
        return self._min_width, self._min_height

    def geometry(self, value: str) -> None:
        self.geometry_calls.append(value)

    def deiconify(self) -> None:
        self.deiconify_calls += 1

    def mainloop(self) -> None:
        self.mainloop_calls += 1


def test_show_tk_window_on_windows_primary_screen_centers_and_handles_negative_coordinates():
    module = _placement_module()
    assert module is not None
    positive = FakeTkRoot()
    negative = FakeTkRoot()

    assert module.show_tk_window_on_windows_primary_screen(
        positive, primary_work_area=(1920, 0, 1920, 1032)
    ) is True
    assert positive.geometry_calls == ["+2280+166"]
    assert positive.deiconify_calls == 1

    assert module.show_tk_window_on_windows_primary_screen(
        negative, primary_work_area=(-1920, 0, 1920, 1032)
    ) is True
    assert negative.geometry_calls == ["-1560+166"]
    assert negative.deiconify_calls == 1


def test_show_tk_window_uses_effective_minimum_size_when_withdrawn():
    module = _placement_module()
    assert module is not None
    root = FakeTkRoot(width=200, height=200, min_width=1120, min_height=640)

    assert module.show_tk_window_on_windows_primary_screen(
        root, primary_work_area=(0, 0, 1920, 1032)
    ) is True
    assert root.geometry_calls == ["+400+196"]
    assert root.deiconify_calls == 1


def test_show_tk_window_on_windows_primary_screen_fails_soft_without_work_area():
    module = _placement_module()
    assert module is not None
    root = FakeTkRoot()

    assert module.show_tk_window_on_windows_primary_screen(
        root, primary_work_area=None, work_area_provider=lambda: None
    ) is False
    assert root.geometry_calls == []
    assert root.deiconify_calls == 1


def test_default_run_workbench_withdraws_before_init_then_places_before_mainloop(monkeypatch):
    from src import workbench

    root = FakeTkRoot()
    events: list[str] = []

    def make_root():
        events.append("create")
        return root

    original_withdraw = root.withdraw
    original_mainloop = root.mainloop

    def withdraw() -> None:
        events.append("withdraw")
        original_withdraw()

    def mainloop() -> None:
        events.append("mainloop")
        original_mainloop()

    root.withdraw = withdraw  # type: ignore[method-assign]
    root.mainloop = mainloop  # type: ignore[method-assign]
    monkeypatch.setattr(workbench.tk, "Tk", make_root)
    monkeypatch.setattr(workbench, "WorkbenchApp", lambda _root: events.append("app"))
    monkeypatch.setattr(
        workbench,
        "show_tk_window_on_windows_primary_screen",
        lambda _root: events.append("place") or True,
        raising=False,
    )

    workbench.run_workbench()

    assert events == ["create", "withdraw", "app", "place", "mainloop"]
    assert root.withdraw_calls == 1
    assert root.mainloop_calls == 1
