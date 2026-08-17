"""Workbench control surface for one authoritative ``SessionTransport``."""

from __future__ import annotations

import threading
import warnings
from typing import Optional

from . import native_audio as _native_audio
from .session_grid import SessionTransport


def warn(msg: str, *args) -> None:
    warnings.warn(msg % args, RuntimeWarning, stacklevel=2)


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
        self._native_started = native_engine is not None  # assume injected engine already started
        self._last_native_engine_frame: int | None = None

        if native_engine is None:
            self._native_available = _native_audio.is_available()
            if self._native_available:
                try:
                    self._native_engine = _native_audio.NativeAudioEngine()
                except Exception as exc:  # pragma: no cover - machine specific
                    warn("Native audio engine init failed: %s", exc)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
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
            }
            return snap

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

    # ------------------------------------------------------------------ #
    # Engine lifecycle helpers
    # ------------------------------------------------------------------ #
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

    def ensure_engine_open(self) -> bool:
        """Ensure the owned native engine is opened. Returns True if engine is available and opened."""
        with self._lock:
            if not self._native_available or not self._native_owned:
                return False
            self._ensure_owned_native_open_unlocked()
            return self._native_opened

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

    # ------------------------------------------------------------------ #
    # Transport control
    # ------------------------------------------------------------------ #
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
                if hasattr(self._native_engine, "snapshot"):
                    try:
                        snapshot = self._native_engine.snapshot()
                        self._last_native_engine_frame = int(snapshot.engine_frame)
                    except Exception:
                        self._last_native_engine_frame = None
            except Exception as exc:  # pragma: no cover - machine specific
                warn("Native audio engine start failed: %s", exc)
                self._transport.stop()

    def stop(self) -> None:
        with self._lock:
            if self._native_engine is not None and self._native_available:
                try:
                    self._native_engine.stop()
                except Exception:
                    pass
                self._native_started = False
            self._transport.stop()

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _refresh_from_native_unlocked(self) -> None:
        # ... existing implementation
        pass

    def _effective_tempo_unlocked(self):
        # ... existing implementation
        pass

    # The rest of the class unchanged ...