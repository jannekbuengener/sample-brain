"""Visible Workbench RECORD/STOP controls backed by the native audio engine.

This module is intentionally small: Tkinter owns presentation, while
``workbench_controller.py`` provides the single session recording bridge.
The GUI poll only reads snapshots; it never advances time from wall-clock data.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from .native_audio import NativeAudioEngine, is_available, Snapshot, SB_DEVICE_OK
from .workbench_controller import start_native_recording, stop_native_recording
from .workbench_transport_adapter import WorkbenchTransportAdapter
from pathlib import Path
from .workbench_controller import workbench_state_dir

RECORDING_POLL_MS = 100

STATUS_IDLE = "idle"
STATUS_RECORDING = "recording"
STATUS_FINALIZING = "finalizing"


class RecordingState:
    """Mutable state shared between UI and controller."""

    def __init__(self) -> None:
        self.status: str = STATUS_IDLE  # idle | recording | finalizing
        self.recording_id: int | None = None
        self.record_start_engine_frame: int = 0
        self.record_start_session_frame: int = 0
        self.last_snapshot: Snapshot | None = None


class WorkbenchRecordingUiController:
    """Attach the exact RECORD/STOP controls to an existing WorkbenchApp."""

    def __init__(
        self,
        app: Any,
        *,
        transport_adapter: "WorkbenchTransportAdapter | None" = None,
        db_path: Any = None,
    ) -> None:
        self.app = app
        # Get the shared engine from the transport adapter
        self.engine = None
        if transport_adapter is not None:
            self.engine = transport_adapter.get_native_engine()
        self.db_path = db_path
        self.state = RecordingState()
        self._poll_id: Any = None
        self._closed = False

        self._build_controls()
        self._schedule_poll()

    def _build_controls(self) -> None:
        tk_api = tk
        ttk_api = ttk

        # Choose a bar location: try the view bar right of the toolbar,
        # otherwise add a compact bar below the toolbar.
        # We insert after the view bar if it exists, else after the toolbar.
        if hasattr(self.app, "_view_bar") and self.app._view_bar is not None:
            parent = self.app._view_bar
            side = tk_api.TOP
            fill = tk_api.X
        else:
            parent = self.app._toolbar
            side = tk_api.BOTTOM
            fill = tk_api.X

        bar = ttk_api.Frame(parent, padding=(8, 4, 8, 4))
        bar.pack(side=side, fill=fill)
        self.app._recording_bar = bar

        # State label
        self.state_var = tk_api.StringVar(value=f"Status: {STATUS_IDLE}")
        self.app._recording_state_var = self.state_var
        self.state_label = ttk_api.Label(bar, textvariable=self.state_var)
        self.state_label.pack(side=tk_api.LEFT)

        # Record button â€” enabled only when engine is available and not already recording
        self.record_btn = ttk_api.Button(
            bar,
            text="Record",
            state=tk_api.NORMAL if self.engine is not None else tk_api.DISABLED,
            command=self._on_record,
        )
        self.app._recording_record_btn = self.record_btn
        self.record_btn.pack(side=tk_api.LEFT, padx=(0, 8))

        # Stop button â€” initially hidden; shown during recording / finalizing
        self.stop_btn = ttk_api.Button(
            bar,
            text="Stop",
            state=tk_api.DISABLED,
            command=self._on_stop,
        )
        self.app._recording_stop_btn = self.stop_btn
        self.stop_btn.pack(side=tk_api.LEFT)

    def _on_record(self) -> None:
        """Start native recording when user presses Record."""
        if self._closed:
            return
        if self.state.status != STATUS_IDLE:
            return
        if self.engine is None:
            self.app._show_toast("Native audio engine not available")
            return

        # Ensure the shared engine is opened before taking snapshots
        if not self.app._transport_adapter.ensure_engine_open():
            self.app._show_toast("Failed to open native audio engine")
            return

        # Get real frames from transport adapter snapshot
        snapshot = self.app._transport_adapter.get_snapshot()
        engine_frame = snapshot["engine_frame"]
        session_frame = snapshot["session_frame"]
        self.state.record_start_engine_frame = engine_frame
        self.state.record_start_session_frame = session_frame
        
        # Start the native recording; returns a recording ID.
        try:
            recording_id = start_native_recording(
                self.engine,
                engine_frame,
                session_frame,
            )
        except RuntimeError as exc:
            # Engine not open or other error â€“ stay idle.
            self.app._show_toast(str(exc))
            return

        self.state.recording_id = recording_id
        self.state.status = STATUS_RECORDING
        self._update_buttons()

    def _on_stop(self) -> None:
        """Stop native recording and finalize the take when user presses Stop."""
        if self.state.status != STATUS_RECORDING or self.state.recording_id is None:
            return

        self.state.status = STATUS_FINALIZING
        self._update_buttons()

        # Stop recording and rescue the take if frames > 0.
        # Correction #3 from Issue #325: snapshot already captured before stop,
        # but we can get a fresh end-frame from the engine state if needed.
        # Correction #2: truth is simply frames > 0 or == 0.
        # Correction #1: native ringbuffer already counts dropped frames.
        # Correction #4: finalize_recording_take() already registers in "Recordings".

        # Use stored start session frame (not current)
        start_session_frame = self.state.record_start_session_frame
        
        # Generate proper .wav destination path under workbench state folder
        recordings_dir = workbench_state_dir() / "recordings"
        recordings_dir.mkdir(parents=True, exist_ok=True)
        import time
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        destination = recordings_dir / f"recording_{timestamp}.wav"
        
        try:
            take = stop_native_recording(
                self.engine,
                self.state.recording_id,
                self.state.record_start_engine_frame,
                start_session_frame,
                destination=str(destination),
                db_path=self.db_path,
            )
        except RuntimeError as exc:
            # Device lost / engine error â€“ try to rescue whatever we can.
            take = None

        # Reset recording state.
        self.state = RecordingState()
        self.state.status = STATUS_IDLE
        self._update_buttons()

        # Optional: show a toast with the result.
        if take is not None:
            # Take was rescued (even if device was lost, as long as frames > 0).
            self.app._show_toast(
                f"Take finalisiert: {take.status} ({take.context.record_end_engine_frame_exclusive - take.context.record_start_engine_frame} Frames)"
            )
        else:
            # frames == 0 â†’ no take created (no fake complete).
            self.app._show_toast("Aufnahme abgebrochen â€“ keine Frames erfasst.")

    def _update_buttons(self) -> None:
        """Update button states based on recording state."""
        if self.state.status == STATUS_IDLE:
            self.state_var.set(f"Status: {STATUS_IDLE}")
            self.record_btn.config(state=tk.NORMAL if self.engine is not None else tk.DISABLED)
            self.stop_btn.config(state=tk.DISABLED)
            self.record_btn.config(text="Record")
        elif self.state.status == STATUS_RECORDING:
            self.state_var.set(f"Status: {STATUS_RECORDING}")
            self.record_btn.config(state=tk.DISABLED, text="Recording...")
            self.stop_btn.config(state=tk.NORMAL)
        elif self.state.status == STATUS_FINALIZING:
            self.state_var.set(f"Status: {STATUS_FINALIZING}")
            self.record_btn.config(state=tk.DISABLED, text="Finalizing...")
            self.stop_btn.config(state=tk.DISABLED)

    def _schedule_poll(self) -> None:
        if self._closed:
            return
        self._poll_id = self.app.root.after(RECORDING_POLL_MS, self._poll)

    def _poll(self) -> None:
        """Periodically refresh UI state from engine snapshot."""
        if self._closed:
            return
        if self.engine is not None and self.state.status == STATUS_RECORDING:
            try:
                snap: Snapshot = self.engine.snapshot()
                self.state.last_snapshot = snap
                # Update status label with device info.
                dev_status = "OK" if snap.device_status == SB_DEVICE_OK else f"Lost/Failed({snap.device_status})"
                self.state_var.set(
                    f"Status: {self.state.status} (Device: {dev_status}, Dropped: {snap.recording_dropped_frames})"
                )
            except RuntimeError:
                pass
        self._schedule_poll()

    def close(self) -> None:
        """Clean up polling and release resources."""
        if self._closed:
            return
        self._closed = True
        if self._poll_id is not None:
            try:
                self.app.root.after_cancel(self._poll_id)
            except Exception:
                pass
            self._poll_id = None
        # Optionally stop any active recording gently.
        if self.state.recording_id is not None and self.engine is not None:
            try:
                self.engine.stop_recording(self.state.recording_id)
            except Exception:
                pass


def attach_workbench_recording_ui(
    app: Any,
    *,
    transport_adapter: "WorkbenchTransportAdapter | None" = None,
    db_path: Any = None,
) -> WorkbenchRecordingUiController:
    """Attach one RECORD/STOP controller to ``app`` and return it.
    
    The transport_adapter provides the shared NativeAudioEngine and real-time
    frame snapshots (engine_frame, session_frame) for recording.
    """
    return WorkbenchRecordingUiController(
        app,
        transport_adapter=transport_adapter,
        db_path=db_path,
    )


__all__ = [
    "RecordingState",
    "WorkbenchRecordingUiController",
    "attach_workbench_recording_ui",
    "STATUS_IDLE",
    "STATUS_RECORDING",
    "STATUS_FINALIZING",
]