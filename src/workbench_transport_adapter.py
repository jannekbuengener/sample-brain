"""Thin control adapter between the Workbench and the shared session transport.

The adapter owns no musical clock. :class:`SessionTransport` remains the only
session-time authority. This module translates Workbench control changes into
transport state and, when explicit native voice ids are registered, into native
playback-rate changes.

When the native engine is available, its integer ``engine_frame`` snapshot is
the realtime clock source. GUI polling may sample that value, but wall-clock
elapsed time is never accumulated into musical position.
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

    ``native_engine`` is an optional already-created engine handle. When the
    adapter creates the native engine itself, it also owns open/close lifecycle.
    An injected engine is treated as caller-managed and is only started/stopped.
    """

    def __init__(
        self,
        *,
        sample_rate: int = 48_000,
        initial_bpm: float = 132.0,
        transport: Optional[SessionTransport] = None,
        native_engine: object | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._transport = transport or SessionTransport(
            sample_rate=sample_rate,
            bpm=initial_bpm,
        )
        self._sample_rate = self._transport.sample_rate

        self._native_engine: object | None = native_engine
        self._native_owned = native_engine is None
        self._native_opened = native_engine is not None
        self._native_available = native_engine is not None
        self._last_native_engine_frame: int | None = None
        self._native_started = False

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
        self._keylock_enabled = False
        self._source_bpm: float | None = None
        self._current_rate = 1.0
        self._sync_status = "sync"

        # --- Authoritative source playhead for HÄFTIG (#327) -----------------
        # ``_source_frame`` is integrated piecewise from the actual engine/session
        # delta at the rate that was in effect during each interval. It is NEVER
        # derived as ``session_frame * current_rate`` (that would retroactively
        # apply one rate to the whole history). ``None`` means "no valid anchor"
        # -> HÄFTIG must fail closed.
        self._source_ref: str | None = None
        self._source_start_frame: int = 0
        self._source_frame: int | None = None

        self._pending_tempo: float | None = None
        self._pending_tempo_frame: int | None = None

        self._voice_source_bpms: dict[int, float | None] = {}
        self._voice_sync_states: dict[int, tuple[float, str]] = {}

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

    def _ensure_owned_native_open_unlocked(self) -> None:
        if (
            self._native_engine is None
            or not self._native_available
            or not self._native_owned
            or self._native_opened
        ):
            return
        self._native_engine.open(
            _native_audio.EngineConfig(sample_rate=self._sample_rate)
        )
        self._native_opened = True
        self._last_native_engine_frame = 0

    def ensure_engine_running(self) -> bool:
        """Ensure the owned native engine is opened AND running (started).
        Does NOT start the musical transport if it was stopped - only starts the audio engine callback.
        Idempotent: if engine already started, returns True without calling start() again.
        Returns True if engine is available and running."""
        with self._lock:
            if not self._native_available or not self._native_owned:
                return False
            self._ensure_owned_native_open_unlocked()
            if not self._native_opened:
                return False
            if self._native_started:
                return True
            # Start the engine callback without starting musical transport
            try:
                self._native_engine.start()
                self._native_started = True
                return True
            except Exception as exc:  # pragma: no cover - machine specific
                warn("Native audio engine start failed: %s", exc)
                return False

    def _apply_native_rate_unlocked(self, voice_id: int, rate: float) -> None:
        if self._native_engine is None or not self._native_available:
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

    def _refresh_from_native_unlocked(self) -> None:
        """Advance SessionTransport only from an observed native frame delta."""
        engine = self._native_engine
        if engine is None or not self._native_available or not hasattr(engine, "snapshot"):
            return
        if self._native_owned and not self._native_opened:
            return
        try:
            native_snapshot = engine.snapshot()
        except Exception as exc:  # pragma: no cover - device specific
            warn("Native snapshot failed: %s", exc)
            self._native_available = False
            self._transport.stop()
            return

        native_frame = int(native_snapshot.engine_frame)
        if native_frame < 0:
            return

        if self._last_native_engine_frame is None:
            delta = max(0, native_frame - self._transport.engine_frame)
        elif native_frame >= self._last_native_engine_frame:
            delta = native_frame - self._last_native_engine_frame
        else:
            # Device/engine reset: establish a new baseline; never invent a
            # negative session jump.
            delta = 0
        self._last_native_engine_frame = native_frame

        if delta:
            before_tempo = self._effective_tempo_unlocked()
            self._transport.advance(delta)
            after_tempo = self._effective_tempo_unlocked()
            self._sync_pending_from_map_unlocked()
            if after_tempo != before_tempo:
                self._update_sync_rates_unlocked()
            self._advance_source_frame_unlocked(delta)

        if not bool(getattr(native_snapshot, "running", True)) and self._transport.playing:
            self._transport.stop()

    def _advance_source_frame_unlocked(self, engine_frames: int) -> None:
        """Honestly integrate the authoritative source playhead.

        Accumulates the per-interval engine delta at the rate that was in effect
        during that interval. This is piecewise integration from an explicit
        anchor — it never applies one current rate to the whole history. When the
        rate is undefined (SYNC on without a known source BPM) the anchor is
        invalidated: the source position becomes unknowable, so HÄFTIG must fail
        closed rather than guess.
        """
        if self._source_frame is None or engine_frames == 0:
            return
        if self._sync_enabled and self._source_bpm is None:
            self._source_frame = None
            return
        rate, _status = _compute_sync_rate(
            self._effective_tempo_unlocked(),
            self._source_bpm,
            self._sync_enabled,
        )
        self._source_frame += int(round(engine_frames * rate))

    def get_haeftig_trigger_context(
        self, source_ref: str
    ) -> tuple[int, int] | None:
        """Return ``(trigger_source_frame, trigger_session_frame)`` for HÄFTIG.

        Fail closed (``None``) when the audible position does not map
        unambiguously to a single nominal source frame: no anchor, source
        mismatch, polyphony, or an undefined sync rate. ``KEY_LOCK_SYNC`` is
        intentionally not discriminated — it shares ``RATE_SYNC``'s frame mapping.
        """
        with self._lock:
            if self._source_frame is None:
                return None
            normalized = str(Path(str(source_ref).strip()).expanduser().resolve())
            if not self._source_ref or normalized != self._source_ref:
                return None
            if len(self._voice_source_bpms) > 1:
                return None
            if self._sync_enabled and self._source_bpm is None:
                return None
            return (int(self._source_frame), int(self._transport.session_frame))

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def play(self) -> None:
        """Start the authoritative transport only when a native clock starts.

        The legacy preview may still play when native audio is unavailable, but
        that fallback has no sample-accurate engine clock.  In that situation
        the transport stays stopped instead of exposing a frozen/fake running
        clock to the UI.
        """
        with self._lock:
            if self._native_engine is None or not self._native_available:
                self._transport.stop()
                return
            try:
                self._ensure_owned_native_open_unlocked()
                self._native_engine.start()
                self._native_started = True
                self._transport.play()
                self._source_frame = self._source_start_frame
                if hasattr(self._native_engine, "snapshot"):
                    try:
                        snapshot = self._native_engine.snapshot()
                        self._last_native_engine_frame = int(snapshot.engine_frame)
                    except Exception:
                        self._last_native_engine_frame = None
            except Exception as exc:  # pragma: no cover - device specific
                warn("Native engine start failed: %s", exc)
                self._native_available = False
                self._transport.stop()

    def stop(self) -> None:
        with self._lock:
            self._transport.stop()
            self._native_started = False
            # Invalidate the authoritative source playhead: after a stop there is
            # no honest anchor until the next play/seek. HÄFTIG must fail closed.
            self._source_frame = None
            if self._native_engine is not None and self._native_available:
                if not self._native_owned or self._native_opened:
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
            self._refresh_from_native_unlocked()
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
            self._refresh_from_native_unlocked()
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

    def set_keylock_mode(self, enabled: bool) -> None:
        """#324: Enable/disable Key-Lock (pitch-preserving) SYNC for native voices.

        Key-Lock keeps the tempo ratio handled by the native DSP path
        (Signalsmith time-stretch) while the playback RATE value stays the
        same as Rate Sync. This is a state holder for the Workbench UI; the
        per-voice sync mode is forwarded to the native engine on voice creation
        and rate updates.
        """
        with self._lock:
            self._keylock_enabled = bool(enabled)

    def is_keylock_enabled(self) -> bool:
        with self._lock:
            return self._keylock_enabled

    def set_source_bpm(
        self,
        bpm: float | None,
        *,
        source_ref: str | None = None,
        source_start_frame: int = 0,
    ) -> None:
        """Set BPM for the current Workbench source snapshot.

        This compatibility method does not guess a native voice id. Use
        ``set_voice_source_bpm`` when a real native voice is known.

        ``source_ref`` / ``source_start_frame`` establish the single source
        context used by the authoritative HÄFTIG source playhead (#327). They do
        not retroactively alter an already-integrated playhead; the start offset
        only takes effect on the next ``play`` / ``seek`` anchor.
        """
        with self._lock:
            if source_ref is not None:
                text = str(source_ref).strip()
                self._source_ref = (
                    str(Path(text).expanduser().resolve()) if text else None
                )
            if isinstance(source_start_frame, int) and not isinstance(
                source_start_frame, bool
            ):
                self._source_start_frame = source_start_frame
            self._source_bpm = bpm
            self._update_sync_rates_unlocked()

    def set_source_start_frame(self, start_frame: int) -> None:
        """Set the source-frame offset applied on the next play/seek anchor."""
        if not isinstance(start_frame, int) or isinstance(start_frame, bool):
            raise ValueError("source start frame must be a non-negative integer")
        if start_frame < 0:
            raise ValueError("source start frame must be non-negative")
        with self._lock:
            self._source_start_frame = start_frame

    def get_source_frame(self) -> int | None:
        """Return the authoritative source playhead, or None when not anchored."""
        with self._lock:
            return self._source_frame

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

    def seek(self, frame: int, *, source_frame: int | None = None) -> None:
        with self._lock:
            self._transport.seek(frame)
            self._sync_pending_from_map_unlocked()
            self._update_sync_rates_unlocked()
            if source_frame is not None:
                # Explicit, unambiguous anchor: the engine jumped to a known source
                # position. Establish a fresh, unique anchor.
                self._source_frame = int(source_frame)
            else:
                # Seek without a known source position: we cannot honestly map the
                # new playhead to a nominal source frame, so invalidate the anchor
                # and let HÄFTIG fail closed until the next explicit anchor.
                self._source_frame = None

    def get_session_frame(self) -> int:
        with self._lock:
            self._refresh_from_native_unlocked()
            return self._transport.session_frame

    def get_engine_frame(self) -> int:
        with self._lock:
            self._refresh_from_native_unlocked()
            return self._transport.engine_frame

    def advance(self, frames: int) -> None:
        """Explicit simulation/test hook; production UI uses native snapshots."""
        with self._lock:
            before_tempo = self._effective_tempo_unlocked()
            self._transport.advance(frames)
            after_tempo = self._effective_tempo_unlocked()
            self._sync_pending_from_map_unlocked()
            if after_tempo != before_tempo:
                self._update_sync_rates_unlocked()
            self._advance_source_frame_unlocked(frames)

    # ------------------------------------------------------------------
    # UI snapshot
    # ------------------------------------------------------------------

    def get_snapshot(self) -> dict[str, object]:
        with self._lock:
            self._refresh_from_native_unlocked()
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
                "native_available": self._native_available,
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
            self._native_started = False
            engine = self._native_engine
            if engine is None:
                return
            try:
                if self._native_available and (not self._native_owned or self._native_opened):
                    try:
                        engine.stop()
                    except Exception:
                        pass
                if self._native_owned and self._native_opened:
                    engine.close()
            except Exception:  # pragma: no cover - native/device specific
                pass
            finally:
                if self._native_owned:
                    self._native_engine = None
                self._native_available = False
                self._native_opened = False
