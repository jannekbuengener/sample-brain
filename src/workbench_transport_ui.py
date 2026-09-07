"""Visible Workbench MASTER/GRID/SYNC controls backed by the shared transport.

This module is intentionally small: Tkinter owns presentation, while
``WorkbenchTransportAdapter`` remains the single session-time/control bridge.
The GUI poll only reads snapshots; it never advances time from wall-clock data.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

import numpy as np
import soundfile as sf

from . import native_audio
from .session_grid import TimeSignature, compute_sync_playback_rate
from .workbench_controller import WorkbenchRow
from .workbench_preview import PreviewResult
from .workbench_transport_adapter import WorkbenchTransportAdapter

TRANSPORT_POLL_MS = 50
DEFAULT_TEMPO_BPM = 132.0

PcmLoadFn = Callable[..., tuple[np.ndarray, int]]


def format_transport_tempo_label(bpm: float) -> str:
    """Return the exact user-facing MASTER tempo label."""
    value = float(bpm)
    rendered = f"{value:g}"
    return f"MASTER {rendered} BPM"


def format_transport_grid_label(time_signature: TimeSignature) -> str:
    """Return the canonical time-signature presentation for the transport bar."""
    return f"GRID {time_signature.numerator}/{time_signature.denominator}"


def _load_native_pcm(
    path: Path,
    *,
    sample_rate: int,
    start_ms: int,
) -> tuple[np.ndarray, int]:
    """Decode immutable source audio to finite PCM at the engine sample rate."""
    data, source_rate = sf.read(
        str(path),
        dtype="float32",
        always_2d=True,
    )
    if data.size == 0:
        raise ValueError("Audio enthält keine Samples.")
    if data.shape[1] > 2:
        data = np.mean(data, axis=1, keepdims=True, dtype=np.float32)
    if int(source_rate) != int(sample_rate):
        import librosa

        data = librosa.resample(
            data.T,
            orig_sr=int(source_rate),
            target_sr=int(sample_rate),
            axis=-1,
        ).T
    start_frame = int(max(0, int(start_ms)) * int(sample_rate) / 1_000)
    if start_frame >= data.shape[0]:
        raise ValueError("Startposition liegt außerhalb der Audiodatei.")
    pcm = np.ascontiguousarray(data[start_frame:], dtype=np.float32)
    return pcm, int(pcm.shape[1])


def _row_is_one_shot(row: WorkbenchRow) -> bool:
    value = (
        str(row.pred_type or row.sample_class or "")
        .strip()
        .lower()
        .replace("-", "_")
    )
    return value in {"one_shot", "oneshot"}


class TransportAwarePreview:
    """Single Workbench playback owner for Browser, Live Kit, and legacy regions.

    Row audition decodes caller-owned audio before it reaches the native PCM
    voice seam delivered by #529. Both Browser and Live Kit schedule immediately
    at the current authoritative native engine frame. This is deliberately the
    same non-quantized rule for both callers; GRID and musical position remain
    owned by the injected :class:`SessionTransport`.
    """

    def __init__(
        self,
        preview: Any,
        transport: WorkbenchTransportAdapter,
        *,
        pcm_load_fn: PcmLoadFn | None = None,
    ) -> None:
        self._preview = preview
        self._transport = transport
        self._pcm_load_fn = pcm_load_fn or _load_native_pcm
        self._active_voice_id: int | None = None
        self._native_current_path: Path | None = None
        self._next_voice_id = 1

    @property
    def current_path(self):
        return self._native_current_path or self._preview.current_path

    @property
    def active_voice_id(self) -> int | None:
        return self._active_voice_id

    @property
    def transport(self) -> WorkbenchTransportAdapter:
        return self._transport

    @property
    def grid_time_signature(self) -> TimeSignature:
        return self._transport.tempo_map.time_signature

    def _stop_native_voice(self) -> bool:
        voice_id = self._active_voice_id
        if voice_id is None:
            return True
        engine = self._transport.get_native_engine()
        if engine is not None:
            try:
                engine.stop_voice(voice_id)
                engine.remove_voice(voice_id)
            except Exception:
                return False
        self._transport.unregister_voice(voice_id)
        self._active_voice_id = None
        self._native_current_path = None
        return True

    def _play_legacy(self, method_name: str, *args: Any, **kwargs: Any):
        if not self._stop_native_voice():
            return PreviewResult(
                ok=False,
                message="Aktive native Wiedergabe konnte nicht ersetzt werden.",
            )
        result = getattr(self._preview, method_name)(*args, **kwargs)
        if getattr(result, "ok", False):
            self._transport.play()
        return result

    def play(self, *args: Any, **kwargs: Any):
        return self._play_legacy("play", *args, **kwargs)

    def play_region(self, *args: Any, **kwargs: Any):
        return self._play_legacy("play_region", *args, **kwargs)

    def play_frame_region(self, *args: Any, **kwargs: Any):
        return self._play_legacy("play_frame_region", *args, **kwargs)

    def play_region_loop(self, *args: Any, **kwargs: Any):
        return self._play_legacy("play_region_loop", *args, **kwargs)

    def play_frame_region_loop(self, *args: Any, **kwargs: Any):
        return self._play_legacy("play_frame_region_loop", *args, **kwargs)

    def play_row(self, row: WorkbenchRow, *, start_ms: int = 0) -> PreviewResult:
        """Audition exactly one row through the shared native/fallback owner."""
        path = Path(row.path).resolve()
        one_shot = _row_is_one_shot(row)
        source_bpm = None if one_shot else row.bpm
        sync_enabled = self._transport.is_sync_enabled()
        master_bpm = self._transport.get_current_tempo()
        rate, sync_status = compute_sync_playback_rate(
            master_bpm,
            source_bpm,
            sync_enabled,
        )
        if sync_enabled and not one_shot and sync_status != "sync":
            return PreviewResult(
                ok=False,
                message="SYNC nicht möglich: keine gültige Source-BPM.",
            )

        if not self._transport.is_native_available():
            if sync_enabled and not one_shot:
                return PreviewResult(
                    ok=False,
                    message="SYNC nicht möglich: nativer PCM-Playback-Pfad fehlt.",
                )
            return self.play(path, start_ms=start_ms)

        try:
            pcm, channels = self._pcm_load_fn(
                path,
                sample_rate=self._transport.tempo_map.sample_rate,
                start_ms=start_ms,
            )
        except Exception as exc:
            return PreviewResult(ok=False, message=f"Audio konnte nicht geladen werden: {exc}")

        if not self._transport.ensure_engine_running():
            return PreviewResult(
                ok=False,
                message="Nativer PCM-Playback-Pfad konnte nicht gestartet werden.",
            )

        engine = self._transport.get_native_engine()
        if engine is None:
            return PreviewResult(ok=False, message="Nativer PCM-Playback-Pfad fehlt.")

        self._preview.stop()
        if not self._stop_native_voice():
            return PreviewResult(
                ok=False,
                message="Aktive native Wiedergabe konnte nicht ersetzt werden.",
            )
        voice_id = self._next_voice_id
        self._next_voice_id += 1
        created_id = voice_id
        try:
            created_id = engine.create_voice(
                native_audio.VoiceConfig(
                    id=voice_id,
                    source_type=native_audio.SB_SOURCE_PCM_BUFFER,
                    pcm_buffer=native_audio.PcmBufferConfig(
                        samples=pcm,
                        channels=channels,
                    ),
                    initial_rate=rate,
                    sync_mode=native_audio.SB_SYNC_MODE_RATE_SYNC,
                    source_bpm=float(source_bpm) if source_bpm is not None else 0.0,
                    master_bpm=master_bpm,
                )
            )
            self._transport.set_source_bpm(
                source_bpm,
                source_ref=str(path),
                source_start_frame=int(max(0, int(start_ms)) * self._transport.tempo_map.sample_rate / 1_000),
            )
            self._transport.set_voice_source_bpm(created_id, source_bpm)
            start_frame = self._transport.get_engine_frame()
            engine.schedule_voice_start(created_id, start_frame)
            self._active_voice_id = created_id
            self._native_current_path = path
            self._transport.play()
        except Exception as exc:
            if self._active_voice_id == created_id:
                self._stop_native_voice()
            else:
                self._transport.unregister_voice(created_id)
                try:
                    engine.remove_voice(created_id)
                except Exception:
                    pass
            self._transport.stop()
            return PreviewResult(ok=False, message=f"Wiedergabe fehlgeschlagen: {exc}")
        return PreviewResult(ok=True)

    def stop(self) -> None:
        self._stop_native_voice()
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
    "format_transport_grid_label",
    "format_transport_tempo_label",
]
