"""Visible Workbench TEMPO/SYNC controls backed by the shared transport.

This module is intentionally small: Tkinter owns presentation, while
``WorkbenchTransportAdapter`` remains the single session-time/control bridge.
The GUI poll only reads snapshots; it never advances time from wall-clock data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import tkinter as tk
from tkinter import ttk

from .workbench_transport_adapter import WorkbenchTransportAdapter

TRANSPORT_POLL_MS = 50
DEFAULT_TEMPO_BPM = 132.0


def format_transport_tempo_label(bpm: float) -> str:
    """Return the exact user-facing TEMPO label."""
    value = float(bpm)
    rendered = f"{value:g}"
    return f"TEMPO: {rendered} BPM"


class TransportAwarePreview:
    """Keep the existing preview player while sharing Play/Stop with transport."""

    def __init__(self, preview: Any, transport: WorkbenchTransportAdapter) -> None:
        self._preview = preview
        self._transport = transport

    @property
    def current_path(self):
        return self._preview.current_path

    def play(self, *args: Any, **kwargs: Any):
        result = self._preview.play(*args, **kwargs)
        if getattr(result, "ok", False):
            self._transport.play()
        return result

    def play_region(self, *args: Any, **kwargs: Any):
        result = self._preview.play_region(*args, **kwargs)
        if getattr(result, "ok", False):
            self._transport.play()
        return result

    def play_region_loop(self, *args: Any, **kwargs: Any):
        result = self._preview.play_region_loop(*args, **kwargs)
        if getattr(result, "ok", False):
            self._transport.play()
        return result

    def stop(self) -> None:
        self._preview.stop()
        self._transport.stop()

    def __getattr__(self, name: str):
        return getattr(self._preview, name)


@dataclass
class _UiApis:
    tk: Any = tk
    ttk: Any = ttk


class WorkbenchTransportUiController:
    """Attach the exact TEMPO/SYNC controls to an existing WorkbenchApp."""

    def __init__(
        self,
        app: Any,
        *,
        transport: WorkbenchTransportAdapter | None = None,
        ui_apis: _UiApis | None = None,
    ) -> None:
        self.app = app
        self.transport = transport or WorkbenchTransportAdapter(
            initial_bpm=DEFAULT_TEMPO_BPM
        )
        self.ui = ui_apis or _UiApis()
        self._poll_id: Any = None
        self._closed = False

        # Preserve the proven preview fallback, but make its Play/Stop lifecycle
        # drive the same SessionTransport used by TEMPO and SYNC.
        app._preview = TransportAwarePreview(app._preview, self.transport)
        app._transport_adapter = self.transport

        self._build_controls()
        self.refresh_snapshot()
        self._schedule_poll()

    def _build_controls(self) -> None:
        tk_api = self.ui.tk
        ttk_api = self.ui.ttk
        bar = ttk_api.Frame(self.app.root, padding=(12, 0, 12, 6))
        # Controls are part of the main Workbench surface and stay above the
        # optional view toolbar.
        bar.pack(fill=tk_api.X, before=self.app._view_bar)
        self.app._transport_bar = bar

        initial = self.transport.get_snapshot()
        self.tempo_var = tk_api.StringVar(
            value=format_transport_tempo_label(initial["current_tempo"])
        )
        self.app._tempo_var = self.tempo_var
        self.tempo_label = ttk_api.Label(bar, textvariable=self.tempo_var)
        self.tempo_label.pack(side=tk_api.LEFT, padx=(0, 8))
        self.app._tempo_label = self.tempo_label

        self.tempo_down = ttk_api.Button(bar, text="−", command=lambda: self.adjust_tempo(-1.0))
        self.tempo_down.pack(side=tk_api.LEFT, padx=(0, 4))
        self.tempo_up = ttk_api.Button(bar, text="+", command=lambda: self.adjust_tempo(1.0))
        self.tempo_up.pack(side=tk_api.LEFT, padx=(0, 12))

        self.sync_var = tk_api.BooleanVar(value=bool(initial["sync_enabled"]))
        self.app._sync_var = self.sync_var
        self.sync_control = ttk_api.Checkbutton(
            bar,
            text="SYNC",
            variable=self.sync_var,
            command=self.apply_sync_control,
        )
        self.sync_control.pack(side=tk_api.LEFT)
        self.app._sync_control = self.sync_control

    def adjust_tempo(self, delta_bpm: float) -> int:
        snapshot = self.transport.get_snapshot()
        current = float(snapshot["current_tempo"])
        target = max(1.0, current + float(delta_bpm))
        effective_frame = self.transport.set_tempo(target)
        self.refresh_snapshot()
        return effective_frame

    def apply_sync_control(self) -> bool:
        desired = bool(self.sync_var.get())
        actual = self.transport.is_sync_enabled()
        if desired != actual:
            actual = self.transport.toggle_sync()
        self.sync_var.set(actual)
        return actual

    def set_source_bpm(self, bpm: float | None) -> None:
        self.transport.set_source_bpm(bpm)

    def refresh_snapshot(self) -> dict[str, object]:
        snapshot = self.transport.get_snapshot()
        self.tempo_var.set(format_transport_tempo_label(snapshot["current_tempo"]))
        self.sync_var.set(bool(snapshot["sync_enabled"]))
        return snapshot

    def _schedule_poll(self) -> None:
        if self._closed:
            return
        self._poll_id = self.app.root.after(TRANSPORT_POLL_MS, self._poll)

    def _poll(self) -> None:
        if self._closed:
            return
        self.refresh_snapshot()
        self._schedule_poll()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._poll_id is not None:
            try:
                self.app.root.after_cancel(self._poll_id)
            except Exception:
                pass
            self._poll_id = None
        self.transport.close()


def attach_workbench_transport_ui(
    app: Any,
    *,
    transport: WorkbenchTransportAdapter | None = None,
    ui_apis: _UiApis | None = None,
) -> WorkbenchTransportUiController:
    """Attach one TEMPO/SYNC controller to ``app`` and return it."""
    return WorkbenchTransportUiController(
        app,
        transport=transport,
        ui_apis=ui_apis,
    )


__all__ = [
    "DEFAULT_TEMPO_BPM",
    "TRANSPORT_POLL_MS",
    "TransportAwarePreview",
    "WorkbenchTransportUiController",
    "attach_workbench_transport_ui",
    "format_transport_tempo_label",
]
