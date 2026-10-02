"""Visible Workbench MASTER/GRID/SYNC controls backed by the shared transport.

This module is intentionally small: Tkinter owns presentation, while
``WorkbenchTransportAdapter`` remains the single session-time/control bridge.
The GUI poll only reads snapshots; it never advances time from wall-clock data.

Tk-free audition/preview types live in :mod:`workbench_transport_preview` and
are re-exported here for legacy import compatibility (#760).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import tkinter as tk
from tkinter import ttk

from .session_grid import TimeSignature
from .workbench_transport_adapter import DEFAULT_TEMPO_BPM, WorkbenchTransportAdapter
from .workbench_transport_preview import (
    PreviewPlaybackSnapshot,
    TransportAwarePreview,
    _load_native_pcm,
    _row_is_one_shot,
)
from .workbench_waveform import read_audio_duration_ms

TRANSPORT_POLL_MS = 50


def format_transport_tempo_label(bpm: float) -> str:
    """Return the exact user-facing MASTER tempo label."""
    value = float(bpm)
    rendered = f"{value:g}"
    return f"MASTER {rendered} BPM"


def format_transport_grid_label(time_signature: TimeSignature) -> str:
    """Return the canonical time-signature presentation for the transport bar."""
    return f"GRID {time_signature.numerator}/{time_signature.denominator}"


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
        header_controls = getattr(self.app, "_shell_header_controls", None)
        if header_controls is None:
            bar = ttk_api.Frame(self.app.root, padding=(12, 0, 12, 6))
            # Keep the standalone controller seam used by focused tests and
            # hosts that do not expose the converged Screen-1 header.
            bar.pack(fill=tk_api.X, before=self.app._body)
        else:
            bar = ttk_api.Frame(header_controls, style="Header.TFrame")
            bar.pack(side=tk_api.RIGHT)
        self.app._transport_bar = bar

        initial = self.transport.get_snapshot()
        self.tempo_var = tk_api.StringVar(
            value=format_transport_tempo_label(initial["current_tempo"])
        )
        self.app._tempo_var = self.tempo_var
        self.tempo_label = ttk_api.Label(bar, textvariable=self.tempo_var)
        self.tempo_label.pack(side=tk_api.LEFT, padx=(0, 8))
        self.app._tempo_label = self.tempo_label

        self.tempo_down = ttk_api.Button(
            bar,
            text="−",
            command=lambda: self.adjust_tempo(-1.0),
        )
        self.tempo_down.pack(side=tk_api.LEFT, padx=(0, 4))
        self.tempo_up = ttk_api.Button(
            bar,
            text="+",
            command=lambda: self.adjust_tempo(1.0),
        )
        self.tempo_up.pack(side=tk_api.LEFT, padx=(0, 12))

        self.grid_var = tk_api.StringVar(
            value=format_transport_grid_label(self.transport.tempo_map.time_signature)
        )
        self.app._grid_var = self.grid_var
        self.grid_label = ttk_api.Label(bar, textvariable=self.grid_var)
        self.grid_label.pack(side=tk_api.LEFT, padx=(0, 12))
        self.app._grid_label = self.grid_label

        self.sync_var = tk_api.BooleanVar(value=bool(initial["sync_enabled"]))
        self.app._sync_var = self.sync_var
        self.sync_control = ttk_api.Button(
            bar,
            text="SYNC",
            style=self._sync_style(bool(initial["sync_enabled"])),
            command=self.toggle_sync_control,
        )
        self.sync_control.pack(side=tk_api.LEFT)
        self.app._sync_control = self.sync_control

    def adjust_tempo(self, delta_bpm: float) -> int:
        # User MASTER deltas use resume intent (pending target if scheduled).
        base = float(self.transport.get_resume_master_bpm())
        target = max(1.0, base + float(delta_bpm))
        effective_frame = self.transport.set_tempo(target)
        self.refresh_snapshot()
        return effective_frame

    @staticmethod
    def _sync_style(sync_enabled: bool) -> str:
        return "SyncActive.TButton" if sync_enabled else "SyncInactive.TButton"

    def _set_sync_presentation(self, sync_enabled: bool) -> None:
        self.sync_var.set(sync_enabled)
        self.sync_control.configure(style=self._sync_style(sync_enabled))

    def toggle_sync_control(self) -> bool:
        """Toggle the authoritative transport state once and present its result."""
        actual = self.transport.toggle_sync()
        self._set_sync_presentation(actual)
        return actual

    def apply_sync_control(self) -> bool:
        """Compatibility alias for callers of the former checkbox callback."""
        return self.toggle_sync_control()

    def set_source_bpm(
        self,
        bpm: float | None,
        *,
        source_ref: str | None = None,
        source_start_frame: int = 0,
    ) -> None:
        self.transport.set_source_bpm(
            bpm,
            source_ref=source_ref,
            source_start_frame=source_start_frame,
        )

    def refresh_snapshot(self) -> dict[str, object]:
        snapshot = self.transport.get_snapshot()
        self.app._transport_snapshot = snapshot
        self.tempo_var.set(format_transport_tempo_label(snapshot["current_tempo"]))
        self.grid_var.set(
            format_transport_grid_label(self.transport.tempo_map.time_signature)
        )
        self._set_sync_presentation(bool(snapshot["sync_enabled"]))
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
    "PreviewPlaybackSnapshot",
    "TransportAwarePreview",
    "WorkbenchTransportUiController",
    "_load_native_pcm",
    "_row_is_one_shot",
    "attach_workbench_transport_ui",
    "format_transport_grid_label",
    "format_transport_tempo_label",
    "read_audio_duration_ms",
]
