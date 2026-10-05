"""Tk-free shared audition/preview transport for QML and Tk Workbench (#760).

Owns only the presentation-agnostic preview telemetry and audition owner used by
Screen-1 QML and the legacy Tk transport UI. Tk widgets stay in
``workbench_transport_ui``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np

from . import native_audio
from .native_pcm_decode import decode_native_pcm
from .session_grid import TimeSignature, compute_sync_playback_rate
from .workbench_controller import WorkbenchRow
from .workbench_preview import PreviewResult
from .workbench_transport_adapter import WorkbenchTransportAdapter
from .workbench_waveform import read_audio_duration_ms

PcmLoadFn = Callable[..., tuple[np.ndarray, int]]


@dataclass(frozen=True)
class PreviewPlaybackSnapshot:
    """Read-only preview telemetry for Screen-1 playhead presentation (#738).

    Position is engine/transport-backed. Legacy OS playback cannot invent
    progress and must return :meth:`idle`.
    """

    playing: bool
    sample_path: str
    position_ms: int
    duration_ms: int
    progress: float
    playback_instance_id: int

    @classmethod
    def idle(cls) -> "PreviewPlaybackSnapshot":
        return cls(
            playing=False,
            sample_path="",
            position_ms=0,
            duration_ms=0,
            progress=0.0,
            playback_instance_id=0,
        )


def _load_native_pcm(
    path: Path,
    *,
    sample_rate: int,
    start_ms: int,
) -> tuple[np.ndarray, int]:
    """Decode immutable source audio to finite PCM at the engine sample rate."""
    return decode_native_pcm(path, sample_rate=sample_rate, start_ms=start_ms)


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
        on_before_shared_transport_stop: Callable[[], None] | None = None,
    ) -> None:
        self._preview = preview
        self._transport = transport
        self._pcm_load_fn = pcm_load_fn or _load_native_pcm
        self._on_before_shared_transport_stop = on_before_shared_transport_stop
        self._active_voice_id: int | None = None
        self._native_current_path: Path | None = None
        self._native_identity_path: str = ""
        self._native_duration_ms: int = 0
        self._next_voice_id = 1

    def set_before_shared_transport_stop(
        self, callback: Callable[[], None] | None
    ) -> None:
        """Bind session policy before shared transport teardown (#916)."""
        self._on_before_shared_transport_stop = callback

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

    def _clear_native_audition_state(self) -> None:
        self._active_voice_id = None
        self._native_current_path = None
        self._native_identity_path = ""
        self._native_duration_ms = 0

    def _stop_native_voice(self) -> bool:
        voice_id = self._active_voice_id
        if voice_id is None:
            self._clear_native_audition_state()
            return True
        engine = self._transport.get_native_engine()
        if engine is not None:
            try:
                engine.stop_voice(voice_id)
                engine.remove_voice(voice_id)
            except Exception:
                return False
        self._transport.unregister_voice(voice_id)
        self._clear_native_audition_state()
        return True

    def _voice_state(self, voice_id: int) -> int | None:
        engine = self._transport.get_native_engine()
        if engine is None or not hasattr(engine, "snapshot"):
            return None
        try:
            snapshot = engine.snapshot()
        except Exception:
            return None
        ids = list(getattr(snapshot, "voice_ids", []) or [])
        states = list(getattr(snapshot, "voice_states", []) or [])
        for index, candidate in enumerate(ids):
            if int(candidate) != int(voice_id):
                continue
            if index >= len(states):
                return None
            return int(states[index])
        return None

    def playback_snapshot(self) -> PreviewPlaybackSnapshot:
        """Return engine-backed preview progress, or idle when unavailable."""
        voice_id = self._active_voice_id
        path = self._native_current_path
        identity = self._native_identity_path or (str(path) if path is not None else "")
        duration_ms = int(self._native_duration_ms)
        if voice_id is None or path is None or duration_ms <= 0:
            return PreviewPlaybackSnapshot.idle()
        if not self._transport.is_native_available():
            return PreviewPlaybackSnapshot.idle()

        # Refresh transport from the native engine clock before reading position.
        self._transport.get_session_frame()
        state = self._voice_state(voice_id)
        if state not in (
            native_audio.SB_VOICE_SCHEDULED,
            native_audio.SB_VOICE_PLAYING,
        ):
            return PreviewPlaybackSnapshot.idle()

        source_frame = self._transport.get_source_frame()
        if source_frame is None:
            return PreviewPlaybackSnapshot.idle()
        sample_rate = int(self._transport.tempo_map.sample_rate)
        if sample_rate <= 0:
            return PreviewPlaybackSnapshot.idle()
        position_ms = max(0, int(round(source_frame * 1000.0 / sample_rate)))
        progress = min(1.0, max(0.0, position_ms / float(duration_ms)))
        return PreviewPlaybackSnapshot(
            playing=True,
            sample_path=identity,
            position_ms=position_ms,
            duration_ms=duration_ms,
            progress=float(progress),
            playback_instance_id=int(voice_id),
        )

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
        identity_path = str(row.path)
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
            self._native_identity_path = identity_path
            duration = read_audio_duration_ms(path)
            self._native_duration_ms = int(duration) if duration is not None else 0
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

    def release_voice(self) -> None:
        """Stop audition voice + legacy preview without shared transport stop (#916).

        Used for focus transfer when Rack playback owns the shared transport.
        Does not call ``WorkbenchTransportAdapter.stop()``.
        """
        self._stop_native_voice()
        self._preview.stop()

    def stop(self) -> None:
        """Explicit audition stop: release voice, then shared transport.

        When a session policy is bound, it may stop Rack playback first so
        ``channel_rack.is_playing`` cannot remain True against a stopped
        shared transport (#916 stop invariant).
        """
        self.release_voice()
        if self._on_before_shared_transport_stop is not None:
            self._on_before_shared_transport_stop()
        self._transport.stop()

    def __getattr__(self, name: str):
        return getattr(self._preview, name)


__all__ = [
    "PreviewPlaybackSnapshot",
    "TransportAwarePreview",
]
