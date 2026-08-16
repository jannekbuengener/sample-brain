"""Thin adapter between Workbench UI and SessionTransport + NativeAudioEngine.

Responsibilities
----------------
* Hold a :class:`SessionTransport` as the authoritative session-time model.
* Optionally wrap a :class:`NativeAudioEngine` (lazy init, graceful fallback).
* Expose a stable snapshot dict that the Tkinter UI polls (~50 ms).
* Store the global ``SYNC`` boolean flag (rate-manipulation deferred to #323).
* Provide ``set_tempo()``, ``play()``, ``stop()``, ``seek()``, ``toggle_sync()``.

Design notes
------------
* No Python calls from a native audio callback. The adapter is driven by
  ``SessionTransport.advance()`` which is called from whatever context the
  native engine provides (or from simulated/integration tests).
* The :class:`NativeAudioEngine` is opened on first ``play()`` only; if the DLL
  is missing or the device cannot be opened, ``native_available`` is set to
  ``False`` and the adapter continues in preview-only mode.
* ``SessionTransport`` owns all musical‑time computation (TempoMap,
  frame↔quarter, bar/beat). The adapter never re‑implements that math.
* SYNC state is persisted in the adapter; actual playback‑rate change
  (``playback_rate = TEMPO / original_bpm``) is **not** done here — that
  belongs to #323.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Optional

import warnings

from src.session_grid import (
    SessionTransport,
    TempoMap,
    TimeSignature,
    MusicalPosition,
    compute_sync_playback_rate,
)
from src.native_audio import (
    NativeAudioEngine,
    is_available as _native_is_available,
    NativeAudioEngine as _NativeAudioEngine,
)
from src.native_audio import Snapshot as _NativeSnapshot

warn = logging.getLogger(__name__.partition(".")[2]).warning

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp_bpm(value: float) -> float:
    """Ensure BPM is positive; return clipped value if invalid."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 120.0  # default
    return max(v, 0.01)  # tiny positive floor; never exactly 0


# ---------------------------------------------------------------------------
# SYNC playback-rate logic
# ---------------------------------------------------------------------------

def _compute_sync_rate(
    master_bpm: float,
    source_bpm: float,
    sync_enabled: bool,
) -> tuple[float, str]:
    """Compute the sync playback rate for a voice.

    Parameters
    ----------
    master_bpm : float
        The current session / master tempo in BPM.
    source_bpm : float
        The original BPM of the sample/voice.
    sync_enabled : bool
        Whether the global SYNC flag is active.

    Returns
    -------
    rate : float
        The playback rate to apply. Always >= 0. Returns 1.0 when
        sync is off or source BPM is invalid.
    status : str
        One of: ``"sync"``, ``"tempo_only"``, ``"not_syncable"``.
        Indicates whether the voice can be synchronised and why.
    """
    # --- Invalid or missing source BPM ---
    try:
        s_bpm = float(source_bpm)
    except (TypeError, ValueError):
        return 1.0, "not_syncable"
    if not s_bpm or s_bpm != s_bpm:  # includes 0 and NaN
        return 1.0, "not_syncable"

    # --- SYNC off → original speed ---
    if not sync_enabled:
        return 1.0, "sync"

    # --- SYNC on with valid source BPM ---
    rate = master_bpm / s_bpm

    # Clamp to reasonable range to avoid extreme rate jumps
    # (extreme rates are treated as not_syncable per #323 spec)
    if rate <= 0 or rate > 4.0 or rate < 0.25:
        return 1.0, "not_syncable"

    # Determine sync status kind
    # If rate is exactly 1.0 the sample already matches master tempo
    if rate == 1.0:
        return 1.0, "sync"

    return rate, "sync"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class WorkbenchTransportAdapter:
    """Adapter bridging the Workbench UI and the session‑transport stack.

    Parameters
    ----------
    sample_rate:
        Audio sample rate in Hz. Pull from the existing native config if
        available; otherwise use the default from :class:`SessionTransport`.
    initial_bpm:
        Initial tempo in BPM. Default 132 per the #322 product example.
    transport:
        Optional pre‑created :class:`SessionTransport` instance. If ``None``
        a new one is created internally.
    """

    def __init__(
        self,
        *,
        sample_rate: int = 48000,
        initial_bpm: float = 132.0,
        transport: Optional[SessionTransport] = None,
    ) -> None:
        self._lock = threading.Lock()

        # --- SessionTransport (authoritative session-time model) ---
        if transport is not None:
            self._transport = transport
        else:
            self._transport = SessionTransport(
                sample_rate=sample_rate,
                bpm=initial_bpm,
            )

        # --- Sample rate from transport (authoritative, not hard‑coded) ---
        self._sample_rate = self._transport.sample_rate

        # --- Optional NativeAudioEngine (lazy, fallback) ---
        self._native_engine: Optional[_NativeAudioEngine] = None
        self._native_available = _native_is_available()
        if self._native_available:
            try:
                self._native_engine = _NativeAudioEngine()
                warn("Native audio engine initialised successfully.")
            except Exception as exc:  # pylint: disable=broad-except
                warn(f"Native audio engine init failed: {exc}")
                self._native_engine = None
                self._native_available = False
        else:
            warn("Native audio engine not available on this platform/config.")

        # --- Internal state ---
        self._sync_enabled = False  # Global SYNC flag; #323 will use it
        self._pending_tempo: Optional[float] = None  # Tempo change awaiting effect
        self._pending_rate: float = 1.0  # Sync playback rate awaiting effect
        self._source_bpm: Optional[float] = None  # Original BPM of the current voice/sample
        self._sync_status: str = "sync"  # Current sync status kind

        # --- Exposed attributes via properties (tests / UI read-only access) ---
        # These delegate to the underlying SessionTransport so they always
        # reflect the current transport state.

        # --- Periodic UI poll (Tkinter root.after) ---
        self._poll_id: Optional[str] = None  # token for root.after cancel

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def play(self) -> None:
        """Start (or resume) session playback.

        If a native engine is available it is started; otherwise the
        preview‑only mode continues (existing WorkbenchPreviewPlayer path).
        """
        with self._lock:
            self._transport.playing = True
            if self._native_engine is not None:
                try:
                    self._native_engine.start()
                except Exception as exc:  # pylint: disable=broad-except
                    warn(f"Native engine start failed: {exc}")
            # If native unavailable we stay in preview mode — no crash.

    def stop(self) -> None:
        """Stop session playback.

        Engine is stopped; session_frame is preserved. Native engine is
        stopped if running.
        """
        with self._lock:
            self._transport.playing = False
            if self._native_engine is not None:
                try:
                    self._native_engine.stop()
                except Exception as exc:  # pylint: disable=broad-except
                    warn(f"Native engine stop failed: {exc}")

    def pause(self) -> None:
        """Alias for stop — kept for readability in UI code."""
        self.stop()

    # ------------------------------------------------------------------
    # Tempo control
    # ------------------------------------------------------------------

    def set_tempo(self, bpm: float) -> int:
        """Set the global tempo.

        If the transport is *stopped* the change is immediate at
        ``session_frame`` (per #320 contract).
        If the transport is *playing* the change takes effect at the next
        bar boundary.

        Returns
        -------
        int
            The ``session_frame`` at which the new tempo segment starts.
        """
        bpm = _clamp_bpm(bpm)
        with self._lock:
            if self._transport.playing:
                # --- running transport → effective at next bar ---
                effective_quarter = self._transport.tempo_map.next_bar_start_quarter(
                    self._transport.session_frame
                )
                segment = self._transport.tempo_map.add_tempo_change_at_quarter(
                    effective_quarter=effective_quarter,
                    bpm=bpm,
                )
                self._pending_tempo = bpm
                return segment.start_frame
            else:
                # --- stopped transport → immediate ---
                segment = self._transport.tempo_map.add_tempo_change_at_frame(
                    effective_frame=self._transport.session_frame,
                    bpm=bpm,
                )
                self._pending_tempo = bpm
                return segment.start_frame

    def get_current_tempo(self) -> float:
        """Return the currently effective BPM (may differ from pending if playing)."""
        with self._lock:
            if self._transport.playing and self._pending_tempo is not None:
                # During a running tempo change the "effective" tempo transitions
                # over the bar boundary; return the target for display.
                return float(self._pending_tempo)
            return float(self._transport.tempo_map.segments[-1].bpm)

    # ------------------------------------------------------------------
    # SYNC control
    # ------------------------------------------------------------------

    def toggle_sync(self) -> bool:
        """Toggle the global SYNC flag.

        Returns
        -------
        bool
            The new SYNC state after the toggle.
        """
        with self._lock:
            self._sync_enabled = not self._sync_enabled
            return self._sync_enabled

    def is_sync_enabled(self) -> bool:
        """Return the current SYNC state."""
        with self._lock:
            return self._sync_enabled

    # ------------------------------------------------------------------
    # SYNC playback-rate control
    # ------------------------------------------------------------------

    def set_source_bpm(self, bpm: float) -> None:
        """Set the original BPM of the current voice/sample.

        This BPM is used as the denominator in the sync rate calculation:
        ``rate = session_tempo / source_bpm``.

        Parameters
        ----------
        bpm : float
            The original BPM of the sample. Use ``None`` or ``0`` to indicate
            that the BPM is unknown / the sample is not synchronisable.
        """
        with self._lock:
            self._source_bpm = bpm
            # Recompute rate immediately when source BPM changes
            self._update_sync_rate()

    def toggle_sync(self) -> bool:
        """Toggle the global SYNC flag and recompute the playback rate.

        Returns
        -------
        bool
            The new SYNC state after the toggle.
        """
        with self._lock:
            self._sync_enabled = not self._sync_enabled
            self._update_sync_rate()
            return self._sync_enabled

    def _update_sync_rate(self) -> None:
        """Recompute and apply the sync playback rate.

        This is called whenever ``_sync_enabled`` or ``_source_bpm`` changes.
        The rate is derived from the current session tempo and the source BPM.
        If the native audio engine is available the rate is forwarded to the
        voice via ``set_voice_rate``; otherwise the internal pending rate is
        stored for later application.
        """
        with self._lock:
            master_bpm = float(self._transport.tempo_map.segments[-1].bpm)
            rate, status = _compute_sync_rate(master_bpm, self._source_bpm, self._sync_enabled)
            self._pending_rate = rate
            self._sync_status = status

            # Apply to native voice if available
            if self._native_engine is not None:
                try:
                    self._native_engine.set_voice_rate(0, rate)  # voice 0 as default
                except Exception as exc:  # pylint: disable=broad-except
                    warn(f"Failed to set native voice rate: {exc}")

    # ------------------------------------------------------------------
    # Session position
    # ------------------------------------------------------------------

    def seek(self, frame: int) -> None:
        """Set the session frame (musical position) independently of engine time.

        Parameters
        ----------
        frame : int
            Zero‑based session frame. Must be non‑negative.
        """
        with self._lock:
            if frame < 0:
                raise ValueError("session_frame must be non‑negative in v1")
            self._transport.session_frame = frame
            # When seeking, reset any pending tempo transition so the new
            # position is anchored cleanly.
            self._pending_tempo = None

    def get_session_frame(self) -> int:
        """Return the current session frame."""
        with self._lock:
            return self._transport.session_frame

    def get_engine_frame(self) -> int:
        """Return the current engine frame (audio‑clock position)."""
        with self._lock:
            return self._transport.engine_frame

    def advance(self, frames: int) -> None:
        """Advance the engine frame by ``frames`` (called from native callback or simulation)."""
        with self._lock:
            self._transport.advance(frames)
            # When advancing, reset pending tempo so position stays anchored
            self._pending_tempo = None

    # ------------------------------------------------------------------
    # Snapshot for UI polling
    # ------------------------------------------------------------------

    def get_snapshot(self) -> dict:
        """Return a read‑only snapshot the Tkinter UI can poll (~50 ms).

        The snapshot is **pure data** — no native‑thread coupling, no
        accumulated wall‑clock time. The GUI timer merely displays what the
        transport reports; it never adds ``elapsed_gui_ms`` on top.

        Returns
        -------
        dict with keys
            * ``engine_frame``   (int)
            * ``session_frame``  (int)
            * ``playing``        (bool)
            * ``current_tempo``  (float)   BPM
            * ``sync_enabled``   (bool)
            * ``sync_rate``      (float | None)  computed playback rate, if applicable
            * ``sync_status``    (str | None)    "sync", "tempo_only", "not_syncable"
            * ``bar``            (int)     current bar, derived from session_frame
            * ``beat``           (int)     current beat, derived from session_frame
            * ``next_tempo_bpm`` (float | None)  pending tempo change, if any
        """
        with self._lock:
            snap = {
                "engine_frame": self._transport.engine_frame,
                "session_frame": self._transport.session_frame,
                "playing": self._transport.playing,
                "current_tempo": self.get_current_tempo(),
                "sync_enabled": self._sync_enabled,
                "sync_rate": self._pending_rate if self._sync_enabled else None,
                "sync_status": self._sync_status if self._sync_enabled else None,
            }

            # Derive bar/beat from the SessionTransport/TempoMap — this is the
            # authoritative musical position, NOT a GUI‑accumulated clock.
            try:
                pos = self._transport.tempo_map.frame_to_bar_beat(
                    self._transport.session_frame
                )
                snap["bar"] = pos.bar
                snap["beat"] = pos.beat
            except Exception:
                snap["bar"] = 0
                snap["beat"] = 0

            # Pending tempo change, if any (None when stopped or no change scheduled)
            snap["next_tempo_bpm"] = (
                float(self._pending_tempo) if self._pending_tempo is not None else None
            )

            return snap

    # ------------------------------------------------------------------
    # Native engine access (for advanced use / #323)
    # ------------------------------------------------------------------

    def get_native_engine(self):
        """Return the native engine instance, or ``None`` if unavailable.

        Callers must not issue Python audio‑thread calls through this handle.
        """
        with self._lock:
            return self._native_engine

    def is_native_available(self) -> bool:
        """Return True when the native audio DLL / device is available."""
        with self._lock:
            return self._native_available

    # ------------------------------------------------------------------
    # Adapter introspection (tests / debugging)
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"WorkbenchTransportAdapter("
            f"sample_rate={self._sample_rate}, "
            f"bpm={self.get_current_tempo():.1f}, "
            f"sync={self._sync_enabled}, "
            f"native={self._native_available})"
        )

    @property
    def native_available(self) -> bool:
        """Return True when the native audio DLL / device is available."""
        with self._lock:
            return self._native_available

    @property
    def playing(self) -> bool:
        """Return the current playing state."""
        with self._lock:
            return self._transport.playing

    @property
    def tempo_map(self):
        """Return the underlying TempoMap (read-only)."""
        with self._lock:
            return self._transport.tempo_map

    @property
    def session_frame(self) -> int:
        """Return the current session frame."""
        with self._lock:
            return self._transport.session_frame

    @property
    def engine_frame(self) -> int:
        """Return the current engine frame."""
        with self._lock:
            return self._transport.engine_frame

    def close(self) -> None:
        """Clean up the native engine if it was opened."""
        with self._lock:
            if self._native_engine is not None:
                try:
                    self._native_engine.close()
                except Exception:  # pylint: disable=broad-except
                    pass
                self._native_engine = None
                self._native_available = False