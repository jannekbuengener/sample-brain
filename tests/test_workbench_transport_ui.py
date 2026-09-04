from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from src.session_grid import TimeSignature
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
    def __init__(self, *, time_signature: TimeSignature | None = None) -> None:
        self.tempo = 132.0
        self.sync = False
        self.playing = False
        self.source_bpm = None
        self.closed = False
        self.play_calls = 0
        self.stop_calls = 0
        self.get_snapshot_calls = 0
        self.set_tempo_calls: list[float] = []
        self.is_sync_enabled_calls = 0
        self.toggle_sync_calls = 0
        self.tempo_map = SimpleNamespace(
            time_signature=time_signature or TimeSignature()
        )

    def get_snapshot(self):
        self.get_snapshot_calls += 1
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
        self.set_tempo_calls.append(float(bpm))
        self.tempo = float(bpm)
        return 123

    def is_sync_enabled(self) -> bool:
        self.is_sync_enabled_calls += 1
        return self.sync

    def toggle_sync(self) -> bool:
        self.toggle_sync_calls += 1
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
        _body=object(),
        _view_bar=object(),
        _preview=FakePreview(),
    )


def _grid_header_text(app: Any) -> str:
    grid_var = getattr(app, "_grid_var", None)
    if grid_var is None:
        pytest.fail("MISSING_PRODUCTION_SURFACE: grid header presentation")
    return grid_var.get()


def test_tempo_label_contract_is_exact():
    assert format_transport_tempo_label(132) == "MASTER 132 BPM"
    assert format_transport_tempo_label(127.5) == "MASTER 127.5 BPM"


def test_controller_initially_exposes_master_and_existing_transport_controls():
    app = _fake_app()
    transport = FakeTransport()

    controller = WorkbenchTransportUiController(
        app,
        transport=transport,
        ui_apis=_fake_ui_apis(),
    )

    assert app._tempo_var.get() == "MASTER 132 BPM"
    assert app._tempo_label.kwargs["textvariable"] is app._tempo_var
    assert app._sync_control.kwargs["text"] == "SYNC"
    assert app._sync_control.kwargs["variable"] is app._sync_var
    assert "Master Tempo" not in app._tempo_var.get()
    assert app._transport_bar.pack_kwargs["before"] is app._body
    assert app.root.after_calls[0][0] == 50
    assert app._transport_snapshot["current_tempo"] == 132.0

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
    assert transport.set_tempo_calls == [133.0]
    assert transport.tempo == 133.0
    assert app._tempo_var.get() == "MASTER 133 BPM"

    assert controller.tempo_down.invoke() == 123
    assert transport.set_tempo_calls == [133.0, 132.0]
    assert transport.tempo == 132.0
    assert app._tempo_var.get() == "MASTER 132 BPM"

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
    assert transport.is_sync_enabled_calls == 2
    assert transport.toggle_sync_calls == 2

    controller.close()


def test_controller_exposes_default_grid_from_canonical_time_signature():
    app = _fake_app()
    controller = WorkbenchTransportUiController(
        app,
        transport=FakeTransport(time_signature=TimeSignature(4, 4)),
        ui_apis=_fake_ui_apis(),
    )

    assert _grid_header_text(app) == "GRID 4/4"

    controller.close()


def test_grid_header_is_derived_from_injected_canonical_time_signature():
    app = _fake_app()
    controller = WorkbenchTransportUiController(
        app,
        transport=FakeTransport(time_signature=TimeSignature(3, 4)),
        ui_apis=_fake_ui_apis(),
    )

    assert _grid_header_text(app) == "GRID 3/4"

    controller.close()


def test_refresh_snapshot_reads_current_canonical_time_signature():
    app = _fake_app()
    transport = FakeTransport(time_signature=TimeSignature(4, 4))
    controller = WorkbenchTransportUiController(
        app,
        transport=transport,
        ui_apis=_fake_ui_apis(),
    )
    transport.get_snapshot_calls = 0
    transport.sync = True
    transport.tempo_map.time_signature = TimeSignature(3, 4)

    controller.refresh_snapshot()

    assert transport.get_snapshot_calls == 1
    assert app._sync_var.get() is True
    assert _grid_header_text(app) == "GRID 3/4"

    controller.close()


def test_compact_transport_bar_exposes_master_grid_and_sync():
    app = _fake_app()
    controller = WorkbenchTransportUiController(
        app,
        transport=FakeTransport(),
        ui_apis=_fake_ui_apis(),
    )

    assert app._tempo_label.parent is app._transport_bar
    assert _grid_header_text(app) == "GRID 4/4"
    assert app._sync_control.parent is app._transport_bar

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
