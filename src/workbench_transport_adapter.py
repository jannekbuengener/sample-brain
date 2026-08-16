"""Thin control adapter between the Workbench and the shared session transport.

The adapter owns no musical clock. :class:`SessionTransport` remains the only
session-time authority.  This module only translates Workbench control changes
into transport state and, when explicit native voice ids are registered, into
native playback-rate changes.

The native audio callback never calls Python through this adapter.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Optional

from src import native_audio as _native_audio
from src.session_grid import SessionTransport, compute_sync_playback_rate

warn = logging.getLogger(__name__.partition(".")[2]).warning


def _clamp_bpm(value: float) -> float:
    """Return a positive BPM suitable for the transport control."""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 120.0
    return max(parsed, 0.01)


def _compute_sync_rate(
    master_bpm: float,
    source_bpm: float | None,
    sync_enabled: bool,
) -> tuple[float, str]:
    """Compatibility helper backed by the canonical #323 rate function."""
    return compute_sync_playback_rate(master_bpm, source_bpm, sync_enabled)


class WorkbenchTransportAdapter:
    """Workbench control surface for one authoritative ``SessionTransport``.

    ``native_engine`` is an optional already-created engine handle.  It exists
    mainly so callers that own native voice lifecycle can attach that engine
    without the adapter inventing voice ids.  When omitted, the historical
    best-effort native discovery/fallback behavior is preserved.
    """

    def __init__(
        self,
        *,
        sample_rate: int = 48_000,
        initial_bpm: float = 132.0,
        transport: Optional[SessionTransport] = None,
        native_engine: object | None = None,
    ) -> None:
        # Some public operations legitimately compose private helpers while the
        # state is locked.  RLock makes that composition explicit and prevents
        # the self-deadlocks present in the original #323 adapter.
        self._lock = threading.RLock()
        self._transport = transport or SessionTransport(
            sample_rate=sample_rate,
            bpm=initial_bpm,
        )
        self._sample_rate = self._transport.sample_rate

        self._native_engine: object | None = native_engine
        self._native_available = native_engine is not None
        if native_engine is None:
            self._native_available = _native_audio.is_available()
            if self._native_available:
                try:
                    self._native_engine = _native_audio.NativeAudioEngine()
                except Exception as exc:  # pragma: no cover - machine specific
                    warn("Native audio engine init failed: %s", exc)
                    self._native_engine = None
                    self._native_available = False

        self._sync_enabled = False
        self._source_bpm: float | None = None
        self._current_rate = 1.0
        self._sync_status = "sync"

        # A running tempo change is scheduled on the shared transport.  Keep
        # the target separate from the *currently effective* tempo shown to UI.
        self._pending_tempo: float | None = None
        self._pending_tempo_frame: int | None = None

        # Native rate changes are only sent to real, explicit voice ids.  The
        # old code silently used voice id 0, which was not a valid contract.
        self._voice_source_bpms: dict[int, float | None] = {}
        self._voice_sync_states: dict[int, tuple[float, str]] = {}

        self._poll_id: str | None = None

    # ------------------------------------------------------------------
    # Internal state helpers
    # ------------------------------------------------------------------

    def _effective_tempo_unlocked(self) -> float:
        frame = self._transport.session_frame
        effective = self._transport.tempo_map.segments[0]
        for segment in self._transport.tempo_map.segments:
            if segment.start_frame > frame:
                break
            effective = segment
        return float(effective.bpm)

    def _sync_pending_from_map_unlocked(self) -> None:
        frame = self._transport.session_frame
        future = [
            segment
            for segment in self._transport.tempo_map.segments
            if segment.start_frame > frame
        ]
        if future:
            self._pending_tempo = float(future[0].bpm)
            self._pending_tempo_frame = future[0].start_frame
        else:
            self._pending_tempo = None
            self._pending_tempo_frame = None

    def _apply_native_rate_unlocked(self, voice_id: int, rate: float) -> None:
        if self._native_engine is None:
            return
        try:
            self._native_engine.set_voice_rate(voice_id, rate)
        except Exception as exc:  # pragma: no cover - native/device specific
            warn("Failed to set native voice %s rate: %s", voice_id, exc)

    def _update_sync_rates_unlocked(self) -> None:
        master_bpm = self._effective_tempo_unlocked()
        self._current_rate, self._sync_status = _compute_sync_rate(
            master_bpm,
            self._source_bpm,
            self._sync_enabled,
        )

        states: dict[int, tuple[float, str]] = {}
        for voice_id in sorted(self._voice_source_bpms):
            rate, status = _compute_sync_rate(
                master_bpm,
                self._voice_source_bpms[voice_id],
                self._sync_enabled,
            )
            states[voice_id] = (rate, status)
            self._apply_native_rate_unlocked(voice_id, rate)
        self._voice_sync_states = states

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def play(self) -> None:
        with self._lock:
            self._transport.play()
            if self._native_engine is not None:
                try:
                    self._native_engine.start()
                except Exception as exc:  # pragma: no cover - device specific
                    # Native failure must degrade honestly instead of pretending
                    # that the realtime path is still available.
                    warn("Native engine start failed: %s", exc)
                    self._native_available = False

    def stop(self) -> None:
        with self._lock:
            self._transport.stop()
            if self._native_engine is not None:
                try:
                    self._native_engine.stop()
                except Exception as exc:  # pragma: no cover - device specific
                    warn("Native engine stop failed: %s", exc)
                    self._native_available = False

    def pause(self) -> None:
        self.stop()

    # ------------------------------------------------------------------
    # Tempo
    # ------------------------------------------------------------------

    def set_tempo(self, bpm: float) -> int:
        bpm = _clamp_bpm(bpm)
        with self._lock:
            effective_frame = self._transport.set_tempo(bpm)
            if effective_frame > self._transport.session_frame:
                self._pending_tempo = bpm
                self._pending_tempo_frame = effective_frame
            else:
                self._pending_tempo = None
                self._pending_tempo_frame = None
                self._update_sync_rates_unlocked()
            return effective_frame

    def get_current_tempo(self) -> float:
        """Return the tempo effective *now*, never a future scheduled target."""
        with self._lock:
            return self._effective_tempo_unlocked()

    # ------------------------------------------------------------------
    # Global SYNC and per-voice source BPM
    # ------------------------------------------------------------------

    def toggle_sync(self) -> bool:
        with self._lock:
            self._sync_enabled = not self._sync_enabled
            self._update_sync_rates_unlocked()
            return self._sync_enabled

    def is_sync_enabled(self) -> bool:
        with self._lock:
            return self._sync_enabled

    def set_source_bpm(self, bpm: float | None) -> None:
        """Set BPM for the current Workbench source snapshot.

        This compatibility method does not guess a native voice id.  Use
        ``set_voice_source_bpm`` when a real native voice is known.
        """
        with self._lock:
            self._source_bpm = bpm
            self._update_sync_rates_unlocked()

    def set_voice_source_bpm(self, voice_id: int, bpm: float | None) -> None:
        """Register/update one explicit native voice and its source BPM."""
        if not isinstance(voice_id, int) or isinstance(voice_id, bool) or voice_id < 0:
            raise ValueError("voice_id must be a non-negative integer")
        with self._lock:
            self._voice_source_bpms[voice_id] = bpm
            master_bpm = self._effective_tempo_unlocked()
            rate, status = _compute_sync_rate(master_bpm, bpm, self._sync_enabled)
            self._voice_sync_states[voice_id] = (rate, status)
            self._apply_native_rate_unlocked(voice_id, rate)

    def unregister_voice(self, voice_id: int) -> None:
        with self._lock:
            self._voice_source_bpms.pop(voice_id, None)
            self._voice_sync_states.pop(voice_id, None)

    def voice_sync_state(self, voice_id: int) -> tuple[float, str] | None:
        with self._lock:
            return self._voice_sync_states.get(voice_id)

    # ------------------------------------------------------------------
    # Session position
    # ------------------------------------------------------------------

    def seek(self, frame: int) -> None:
        with self._lock:
            self._transport.seek(frame)
            self._sync_pending_from_map_unlocked()
            self._update_sync_rates_unlocked()

    def get_session_frame(self) -> int:
        with self._lock:
            return self._transport.session_frame

    def get_engine_frame(self) -> int:
        with self._lock:
            return self._transport.engine_frame

    def advance(self, frames: int) -> None:
        with self._lock:
            before_tempo = self._effective_tempo_unlocked()
            self._transport.advance(frames)
            after_tempo = self._effective_tempo_unlocked()
            self._sync_pending_from_map_unlocked()
            if after_tempo != before_tempo:
                self._update_sync_rates_unlocked()

    # ------------------------------------------------------------------
    # UI snapshot
    # ------------------------------------------------------------------

    def get_snapshot(self) -> dict[str, object]:
        with self._lock:
            current_tempo = self._effective_tempo_unlocked()
            snap: dict[str, object] = {
                "engine_frame": self._transport.engine_frame,
                "session_frame": self._transport.session_frame,
                "playing": self._transport.playing,
                "current_tempo": current_tempo,
                "sync_enabled": self._sync_enabled,
                "sync_rate": self._current_rate if self._sync_enabled else None,
                "sync_status": self._sync_status if self._sync_enabled else None,
                "next_tempo_bpm": self._pending_tempo,
                "next_tempo_frame": self._pending_tempo_frame,
            }
            try:
                position = self._transport.tempo_map.frame_to_bar_beat(
                    self._transport.session_frame
                )
                snap["bar"] = position.bar
                snap["beat"] = position.beat
            except Exception:
                snap["bar"] = 0
                snap["beat"] = 0
            return snap

    # ------------------------------------------------------------------
    # Native access and introspection
    # ------------------------------------------------------------------

    def get_native_engine(self):
        with self._lock:
            return self._native_engine

    def is_native_available(self) -> bool:
        with self._lock:
            return self._native_available

    @property
    def native_available(self) -> bool:
        return self.is_native_available()

    @property
    def playing(self) -> bool:
        with self._lock:
            return self._transport.playing

    @property
    def tempo_map(self):
        with self._lock:
            return self._transport.tempo_map

    @property
    def session_frame(self) -> int:
        return self.get_session_frame()

    @property
    def engine_frame(self) -> int:
        return self.get_engine_frame()

    def __repr__(self) -> str:
        with self._lock:
            return (
                "WorkbenchTransportAdapter("
                f"sample_rate={self._sample_rate}, "
                f"bpm={self._effective_tempo_unlocked():.1f}, "
                f"sync={self._sync_enabled}, "
                f"native={self._native_available})"
            )

    def close(self) -> None:
        with self._lock:
            if self._native_engine is not None:
                try:
                    self._native_engine.close()
                except Exception:  # pragma: no cover - native/device specific
                    pass
                self._native_engine = None
                self._native_available = False
