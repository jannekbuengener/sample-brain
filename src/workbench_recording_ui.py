"""Visible Workbench recording controls backed by the native audio engine.

Tkinter owns presentation while ``workbench_controller.py`` provides the shared
recording bridge. Quick Capture is wired here as well because this controller
already owns the authoritative native engine and transport snapshots.
"""

from __future__ import annotations

import time
import tkinter as tk
import uuid
from pathlib import Path
from tkinter import ttk
from typing import Any

from .native_audio import NativeAudioEngine, Snapshot, SB_DEVICE_OK, is_available
from .quick_issue_capture import QuickIssueCapture
from .workbench_controller import (
    start_native_recording,
    stop_native_recording,
    workbench_state_dir,
)
from .workbench_transport_adapter import WorkbenchTransportAdapter

RECORDING_POLL_MS = 100

STATUS_IDLE = "idle"
STATUS_RECORDING = "recording"
STATUS_FINALIZING = "finalizing"


class RecordingState:
    """Mutable state shared between UI and controller."""

    def __init__(self) -> None:
        self.status: str = STATUS_IDLE
        self.recording_id: int | None = None
        self.record_start_engine_frame: int = 0
        self.record_start_session_frame: int = 0
        self.last_snapshot: Snapshot | None = None


class WorkbenchRecordingUiController:
    """Attach RECORD/STOP and Quick Capture to an existing WorkbenchApp."""

    def __init__(
        self,
        app: Any,
        *,
        transport_adapter: "WorkbenchTransportAdapter | None" = None,
        db_path: Any = None,
    ) -> None:
        self.app = app
        self.transport_adapter = transport_adapter
        self.engine = (
            transport_adapter.get_native_engine()
            if transport_adapter is not None
            else None
        )
        self.db_path = db_path
        self.state = RecordingState()
        self._poll_id: Any = None
        self._closed = False
        self._quick_capture = QuickIssueCapture()
        self._quick_capture_recording = False

        self._build_controls()
        self._wire_quick_capture_button()
        self._schedule_poll()

    def _build_controls(self) -> None:
        if hasattr(self.app, "_view_bar") and self.app._view_bar is not None:
            parent = self.app._view_bar
            side = tk.TOP
            fill = tk.X
        else:
            parent = self.app._toolbar
            side = tk.BOTTOM
            fill = tk.X

        bar = ttk.Frame(parent, padding=(8, 4, 8, 4))
        bar.pack(side=side, fill=fill)
        self.app._recording_bar = bar

        self.state_var = tk.StringVar(value=f"Status: {STATUS_IDLE}")
        self.app._recording_state_var = self.state_var
        self.state_label = ttk.Label(bar, textvariable=self.state_var)
        self.state_label.pack(side=tk.LEFT)

        self.record_btn = ttk.Button(
            bar,
            text="Record",
            state=tk.NORMAL if self.engine is not None else tk.DISABLED,
            command=self._on_record,
        )
        self.app._recording_record_btn = self.record_btn
        self.record_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.stop_btn = ttk.Button(
            bar,
            text="Stop",
            state=tk.DISABLED,
            command=self._on_stop,
        )
        self.app._recording_stop_btn = self.stop_btn
        self.stop_btn.pack(side=tk.LEFT)

    def _wire_quick_capture_button(self) -> None:
        button = getattr(self.app, "_quick_capture_btn", None)
        if button is None:
            return
        button.configure(command=self._on_quick_capture_toggle)
        if self.engine is not None:
            button.state(["!disabled"])
        else:
            button.state(["disabled"])

    def _on_record(self) -> None:
        """Start normal native recording when user presses Record."""
        if self._closed or self._quick_capture_recording:
            return
        if self.state.status != STATUS_IDLE:
            return
        if self.engine is None:
            self.app._show_toast("Native audio engine not available")
            return
        if self.transport_adapter is None or not self.transport_adapter.ensure_engine_running():
            self.app._show_toast("Failed to start native audio engine")
            return

        snapshot = self.transport_adapter.get_snapshot()
        engine_frame = snapshot["engine_frame"]
        session_frame = snapshot["session_frame"]
        self.state.record_start_engine_frame = engine_frame
        self.state.record_start_session_frame = session_frame

        try:
            recording_id = start_native_recording(
                self.engine,
                engine_frame,
                session_frame,
            )
        except RuntimeError as exc:
            self.app._show_toast(str(exc))
            return

        self.state.recording_id = recording_id
        self.state.status = STATUS_RECORDING
        self._update_buttons()

    def _on_stop(self) -> None:
        """Stop normal recording and finalize the take."""
        if self._closed:
            return
        if self.state.status != STATUS_RECORDING or self.state.recording_id is None:
            return
        if self.transport_adapter is None:
            return

        self.state.status = STATUS_FINALIZING
        self._update_buttons()

        end_snapshot = self.transport_adapter.get_snapshot()
        end_engine_frame = end_snapshot["engine_frame"]
        end_session_frame = end_snapshot["session_frame"]
        start_session_frame = self.state.record_start_session_frame

        recordings_dir = workbench_state_dir() / "recordings"
        recordings_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        destination = recordings_dir / f"recording_{timestamp}_{unique_id}.wav"

        try:
            take = stop_native_recording(
                self.engine,
                self.state.recording_id,
                self.state.record_start_engine_frame,
                start_session_frame,
                end_engine_frame=end_engine_frame,
                end_session_frame=end_session_frame,
                destination=str(destination),
                db_path=self.db_path,
            )
        except RuntimeError:
            take = None

        self.state = RecordingState()
        self._update_buttons()

        if take is not None:
            self.app._show_toast(
                f"Take finalisiert: {take.status} "
                f"({take.context.record_end_engine_frame_exclusive - take.context.record_start_engine_frame} Frames)"
            )
        else:
            self.app._show_toast("Aufnahme abgebrochen - keine Frames erfasst.")

    def _on_quick_capture_toggle(self) -> None:
        """Start/stop the one-click voice-to-public-GitHub-issue flow."""
        if self._closed:
            return
        if self.engine is None or self.transport_adapter is None:
            self.app._set_status("Quick Capture: Native Audio nicht verfügbar.", tone="error")
            return

        if not self._quick_capture_recording:
            if self.state.status != STATUS_IDLE:
                self.app._set_status(
                    "Quick Capture ist während einer normalen Aufnahme nicht verfügbar.",
                    tone="error",
                )
                return
            if not self.transport_adapter.ensure_engine_running():
                self.app._set_status(
                    "Quick Capture: Native Audio konnte nicht gestartet werden.",
                    tone="error",
                )
                return
            snapshot = self.transport_adapter.get_snapshot()
            try:
                self._quick_capture.start_recording(
                    self.engine,
                    snapshot["engine_frame"],
                    snapshot["session_frame"],
                )
            except RuntimeError as exc:
                self.app._set_status(f"Quick Capture: {exc}", tone="error")
                return
            self._quick_capture_recording = True
            self._update_buttons()
            self.app._set_status(
                "Quick Capture: Aufnahme läuft - erneut klicken zum Stoppen.",
                tone="active",
            )
            return

        end_snapshot = self.transport_adapter.get_snapshot()
        self._quick_capture_recording = False
        result = self._quick_capture.process_recording(
            engine=self.engine,
            end_engine_frame=end_snapshot["engine_frame"],
            end_session_frame=end_snapshot["session_frame"],
        )
        self._update_buttons()

        issue = result.get("issue")
        if issue:
            self.app._set_status(
                f"Issue erstellt: #{issue['number']} ({issue['html_url']})",
                tone="success",
            )
        else:
            self.app._set_status(
                result.get("error") or "Quick Capture fehlgeschlagen.",
                tone="error",
            )

    def _update_buttons(self) -> None:
        """Update normal and Quick Capture button states."""
        normal_idle = self.state.status == STATUS_IDLE and not self._quick_capture_recording
        if self.state.status == STATUS_IDLE:
            self.state_var.set(f"Status: {STATUS_IDLE}")
            self.record_btn.config(
                state=tk.NORMAL if self.engine is not None and normal_idle else tk.DISABLED,
                text="Record",
            )
            self.stop_btn.config(state=tk.DISABLED)
        elif self.state.status == STATUS_RECORDING:
            self.state_var.set(f"Status: {STATUS_RECORDING}")
            self.record_btn.config(state=tk.DISABLED, text="Recording...")
            self.stop_btn.config(state=tk.NORMAL)
        elif self.state.status == STATUS_FINALIZING:
            self.state_var.set(f"Status: {STATUS_FINALIZING}")
            self.record_btn.config(state=tk.DISABLED, text="Finalizing...")
            self.stop_btn.config(state=tk.DISABLED)

        quick_button = getattr(self.app, "_quick_capture_btn", None)
        if quick_button is not None:
            if self.engine is None or self.state.status != STATUS_IDLE:
                quick_button.state(["disabled"])
            else:
                quick_button.state(["!disabled"])
            quick_button.configure(
                text="Mikrofon stoppen" if self._quick_capture_recording else "Mikrofon"
            )

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
                dev_status = (
                    "OK"
                    if snap.device_status == SB_DEVICE_OK
                    else f"Lost/Failed({snap.device_status})"
                )
                self.state_var.set(
                    f"Status: {self.state.status} "
                    f"(Device: {dev_status}, Dropped: {snap.recording_dropped_frames})"
                )
            except RuntimeError:
                pass
        self._schedule_poll()

    def close(self) -> None:
        """Clean up polling and stop owned recordings gently."""
        if self._closed:
            return
        self._closed = True
        if self._poll_id is not None:
            try:
                self.app.root.after_cancel(self._poll_id)
            except Exception:
                pass
            self._poll_id = None
        if self.state.recording_id is not None and self.engine is not None:
            try:
                self.engine.stop_recording(self.state.recording_id)
            except Exception:
                pass
        if self._quick_capture_recording and self.engine is not None:
            quick_id = getattr(self._quick_capture, "_recording_id", None)
            if quick_id is not None:
                try:
                    self.engine.stop_recording(quick_id)
                except Exception:
                    pass


def attach_workbench_recording_ui(
    app: Any,
    *,
    transport_adapter: "WorkbenchTransportAdapter | None" = None,
    db_path: Any = None,
) -> WorkbenchRecordingUiController:
    """Attach one recording controller using the shared native transport."""
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
