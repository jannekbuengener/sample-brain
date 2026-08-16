from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from src.workbench_transport_ui import (
    TransportAwarePreview,
    WorkbenchTransportUiController,
    _UiApis,
    format_transport_tempo_label,
)


class FakeVar:
    def __init__(self, value: Any = None) -> None:
        self.value = value

    def get(self):
        return self.value

    def set(self, value: Any) -> None:
        self.value = value


class FakeWidget:
    def __init__(self, parent=None, **kwargs) -> None:
        self.parent = parent
        self.kwargs = kwargs
        self.pack_kwargs: dict[str, Any] = {}

    def pack(self, **kwargs) -> None:
        self.pack_kwargs = kwargs


class FakeFrame(FakeWidget):
    pass


class FakeLabel(FakeWidget):
    pass


class FakeButton(FakeWidget):
    def invoke(self):
        return self.kwargs["command"]()


class FakeCheckbutton(FakeButton):
    pass


class FakeRoot:
    def __init__(self) -> None:
        self.after_calls: list[tuple[int, Any]] = []
        self.cancelled: list[Any] = []

    def after(self, delay: int, callback):
        token = f"after-{len(self.after_calls) + 1}"
        self.after_calls.append((delay, callback))
        return token

    def after_cancel(self, token) -> None:
        self.cancelled.append(token)


class FakeTransport:
    def __init__(self) -> None:
        self.tempo = 132.0
        self.sync = False
        self.playing = False
        self.source_bpm = None
        self.closed = False
        self.play_calls = 0
        self.stop_calls = 0

    def get_snapshot(self):
        return {
            "engine_frame": 0,
            "session_frame": 0,
            "playing": self.playing,
            "current_tempo": self.tempo,
            "sync_enabled": self.sync,
            "sync_rate": None,
            "sync_status": None,
            "next_tempo_bpm": None,
            "next_tempo_frame": None,
            "native_available": False,
            "bar": 0,
            "beat": 0,
        }

    def set_tempo(self, bpm: float) -> int:
        self.tempo = float(bpm)
        return 123

    def is_sync_enabled(self) -> bool:
        return self.sync

    def toggle_sync(self) -> bool:
        self.sync = not self.sync
        return self.sync

    def set_source_bpm(self, bpm) -> None:
        self.source_bpm = bpm

    def play(self) -> None:
        self.play_calls += 1
        self.playing = True

    def stop(self) -> None:
        self.stop_calls += 1
        self.playing = False

    def close(self) -> None:
        self.closed = True


@dataclass
class FakePreviewResult:
    ok: bool


class FakePreview:
    def __init__(self) -> None:
        self.current_path = None
        self.stop_calls = 0

    def play(self, path, **_kwargs):
        self.current_path = path
        return FakePreviewResult(ok=True)

    def play_region(self, path, **_kwargs):
        self.current_path = path
        return FakePreviewResult(ok=True)

    def play_region_loop(self, path, **_kwargs):
        self.current_path = path
        return FakePreviewResult(ok=True)

    def stop(self) -> None:
        self.current_path = None
        self.stop_calls += 1


def _fake_ui_apis() -> _UiApis:
    tk_api = SimpleNamespace(
        X="x",
        LEFT="left",
        StringVar=FakeVar,
        BooleanVar=FakeVar,
    )
    ttk_api = SimpleNamespace(
        Frame=FakeFrame,
        Label=FakeLabel,
        Button=FakeButton,
        Checkbutton=FakeCheckbutton,
    )
    return _UiApis(tk=tk_api, ttk=ttk_api)


def _fake_app():
    return SimpleNamespace(
        root=FakeRoot(),
        _view_bar=object(),
        _preview=FakePreview(),
    )


def test_tempo_label_contract_is_exact():
    assert format_transport_tempo_label(132) == "TEMPO: 132 BPM"
    assert format_transport_tempo_label(127.5) == "TEMPO: 127.5 BPM"


def test_controller_builds_real_tempo_and_sync_controls():
    app = _fake_app()
    transport = FakeTransport()

    controller = WorkbenchTransportUiController(
        app,
        transport=transport,
        ui_apis=_fake_ui_apis(),
    )

    assert app._tempo_var.get() == "TEMPO: 132 BPM"
    assert app._tempo_label.kwargs["textvariable"] is app._tempo_var
    assert app._sync_control.kwargs["text"] == "SYNC"
    assert app._sync_control.kwargs["variable"] is app._sync_var
    assert "Master Tempo" not in app._tempo_var.get()
    assert app._transport_bar.pack_kwargs["before"] is app._view_bar
    assert app.root.after_calls[0][0] == 50

    controller.close()


def test_tempo_buttons_change_the_shared_transport_and_refresh_label():
    app = _fake_app()
    transport = FakeTransport()
    controller = WorkbenchTransportUiController(
        app,
        transport=transport,
        ui_apis=_fake_ui_apis(),
    )

    assert controller.tempo_up.invoke() == 123
    assert transport.tempo == 133.0
    assert app._tempo_var.get() == "TEMPO: 133 BPM"

    assert controller.tempo_down.invoke() == 123
    assert transport.tempo == 132.0
    assert app._tempo_var.get() == "TEMPO: 132 BPM"

    controller.close()


def test_sync_control_updates_the_single_transport_state():
    app = _fake_app()
    transport = FakeTransport()
    controller = WorkbenchTransportUiController(
        app,
        transport=transport,
        ui_apis=_fake_ui_apis(),
    )

    app._sync_var.set(True)
    assert app._sync_control.invoke() is True
    assert transport.sync is True

    app._sync_var.set(False)
    assert app._sync_control.invoke() is False
    assert transport.sync is False

    controller.close()


def test_preview_play_stop_share_the_transport_lifecycle():
    preview = FakePreview()
    transport = FakeTransport()
    wrapped = TransportAwarePreview(preview, transport)

    result = wrapped.play("synthetic.wav")
    assert result.ok is True
    assert transport.play_calls == 1
    assert transport.playing is True

    wrapped.stop()
    assert preview.stop_calls == 1
    assert transport.stop_calls == 1
    assert transport.playing is False


def test_controller_close_cancels_poll_and_closes_transport():
    app = _fake_app()
    transport = FakeTransport()
    controller = WorkbenchTransportUiController(
        app,
        transport=transport,
        ui_apis=_fake_ui_apis(),
    )
    token = controller._poll_id

    controller.close()

    assert app.root.cancelled == [token]
    assert transport.closed is True
