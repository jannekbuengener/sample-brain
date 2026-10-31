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
import math
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Optional

from src import native_audio as _native_audio
from src.session_grid import SessionTransport, compute_sync_playback_rate

warn = logging.getLogger(__name__.partition(".")[2]).warning

DEFAULT_TEMPO_BPM = 132.0

# Import WASAPI meter deps before any native engine open can CoInitialize the
# thread apartment (#1352). Late imports after ma_device_init can raise
# RPC_E_CHANGED_MODE and would otherwise disable measurable_output.
_METER_IMPORT_ERROR: str | None
try:
    from ctypes import POINTER as _METER_POINTER
    from ctypes import cast as _METER_CAST

    from comtypes import CLSCTX_ALL as _METER_CLSCTX_ALL
    from comtypes import CoCreateInstance as _METER_CoCreateInstance
    from pycaw.api.endpointvolume import IAudioMeterInformation as _METER_Iface
    from pycaw.api.mmdeviceapi import IMMDeviceEnumerator as _METER_IMMDevEnum
    from pycaw.constants import CLSID_MMDeviceEnumerator as _METER_CLSID

    _METER_IMPORT_ERROR = None
except Exception as _meter_exc:  # pragma: no cover - optional host dependency
    _METER_IMPORT_ERROR = str(_meter_exc)
    _METER_POINTER = None  # type: ignore[assignment]
    _METER_CAST = None  # type: ignore[assignment]
    _METER_CLSCTX_ALL = None  # type: ignore[assignment]
    _METER_CoCreateInstance = None  # type: ignore[assignment]
    _METER_Iface = None  # type: ignore[assignment]
    _METER_IMMDevEnum = None  # type: ignore[assignment]
    _METER_CLSID = None  # type: ignore[assignment]


def _clamp_bpm(value: float) -> float:
    """Return a positive finite BPM suitable for the transport control."""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 120.0
    if not math.isfinite(parsed) or parsed <= 0:
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
        initial_bpm: float = DEFAULT_TEMPO_BPM,
        initial_sync_enabled: bool = False,
        transport: Optional[SessionTransport] = None,
        native_engine: object | None = None,
    ) -> None:
        if type(initial_sync_enabled) is not bool:
            raise TypeError("initial_sync_enabled must be an exact bool")
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
        # Set by stop() when the native device was actually stopped. Next start
        # must rebase transport.engine_frame onto the restarted native epoch
        # (#1209). First-ever start must NOT wipe a pre-play engine_frame.
        self._rebase_engine_clock_on_next_start = False
        self._preferred_output_device_applied: str | None = None
        # #1349: coarse non-RT switch phase for honest UI status projection.
        self._audio_switch_phase: str = "idle"
        # #1351: after device loss, block ensure_engine_running until explicit retry.
        self._audio_output_requires_explicit_retry: bool = False

        if native_engine is None:
            self._native_available = _native_audio.is_available()
            if self._native_available:
                try:
                    self._native_engine = _native_audio.NativeAudioEngine()
                except Exception as exc:  # pragma: no cover - machine specific
                    warn("Native audio engine init failed: %s", exc)
                    self._native_engine = None
                    self._native_available = False

        self._sync_enabled = initial_sync_enabled
        self._keylock_enabled = False
        self._source_bpm: float | None = None
        self._current_rate = 1.0
        self._sync_status = "sync"
        self._on_session_clock_changed: Callable[[], None] | None = None

        # --- Authoritative source playhead for HÄFTIG (#327) -----------------
        # ``_source_frame`` is integrated piecewise from the actual engine/session
        # delta at the rate that was in effect during each interval. It is NEVER
        # derived as ``session_frame * current_rate`` (that would retroactively
        # apply one rate to the whole history). ``None`` means "no valid anchor"
        # -> HÄFTIG must fail closed.
        self._source_ref: str | None = None
        self._source_start_frame: int = 0
        self._source_frame: int | None = None
        # Fractional source-frame remainder. Integration accumulates the exact
        # (rate * frames) product here and only the whole part is promoted to
        # ``_source_frame``; the remainder is carried forward. This is fixed-point
        # accumulation, so there is no per-callback ``round(...)`` drift.
        self._source_frac: float = 0.0

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

    def _load_audio_output_settings_unlocked(self):
        """Best-effort load of persisted audio output preferences."""
        try:
            from .workbench_audio_output import load_workbench_audio_output_settings

            return load_workbench_audio_output_settings()
        except Exception as exc:  # pragma: no cover - preference IO is best-effort
            warn("Audio output preference load failed: %s", exc)
            return None

    def _preferred_output_device_id_unlocked(self) -> str | None:
        """Return persisted preferred render device id, or None for OS default."""
        settings = self._load_audio_output_settings_unlocked()
        if settings is None:
            return None
        device_id = str(getattr(settings, "preferred_output_device_id", "") or "").strip()
        if not device_id:
            return None
        audio_system = str(getattr(settings, "audio_system", "") or "sample_brain_audio")
        # WASAPI ids are 512-hex; ASIO driver tokens are CLSID/name strings (#1350).
        if audio_system != "vendor_asio" and len(device_id) != 512:
            warn(
                "Ignoring invalid preferred_output_device_id length=%s",
                len(device_id),
            )
            return None
        return device_id

    def _engine_open_config_unlocked(self, output_device: str | None):
        """Build EngineConfig from persisted Sample Brain Audio preferences (#1348)."""
        settings = self._load_audio_output_settings_unlocked()
        sample_rate = int(self._sample_rate)
        buffer_frames = 256
        if settings is not None:
            try:
                sample_rate = int(getattr(settings, "sample_rate", sample_rate) or sample_rate)
            except (TypeError, ValueError):
                sample_rate = int(self._sample_rate)
            try:
                buffer_frames = int(getattr(settings, "buffer_frames", buffer_frames) or buffer_frames)
            except (TypeError, ValueError):
                buffer_frames = 256
            self._sample_rate = sample_rate
        return _native_audio.EngineConfig(
            sample_rate=sample_rate,
            buffer_frames=buffer_frames,
            output_device=output_device,
            # Audition/transport clock is playback-only. Opening duplex
            # capture-by-default can interfere with other Windows sessions.
            input_channels=0,
        )

    def _audio_system_unlocked(self) -> str:
        settings = self._load_audio_output_settings_unlocked()
        if settings is None:
            return "sample_brain_audio"
        return str(getattr(settings, "audio_system", "") or "sample_brain_audio").strip() or (
            "sample_brain_audio"
        )

    def _vendor_asio_backend_available(self) -> bool:
        """True only when NativeAudioEngine exposes a real vendor-ASIO path (#1350)."""
        # Product rule: no ASIO4ALL / no second engine. Native COM IASIO host
        # opens manufacturer drivers under the same NativeAudioEngine authority.
        return bool(getattr(_native_audio, "VENDOR_ASIO_BACKEND_AVAILABLE", False))

    def _ensure_owned_native_open_unlocked(self) -> None:
        if (
            self._native_engine is None
            or not self._native_available
            or not self._native_owned
            or self._native_opened
        ):
            return
        audio_system = self._audio_system_unlocked()
        if audio_system == "vendor_asio" and not self._vendor_asio_backend_available():
            # Never silently open WASAPI while ASIO is the persisted product choice.
            warn(
                "Vendor ASIO selected but native ASIO backend is unavailable; "
                "fail-closed (no WASAPI substitute)"
            )
            self._native_opened = False
            self._preferred_output_device_applied = None
            self._audio_switch_phase = "unavailable"
            self._audio_output_requires_explicit_retry = True
            return
        output_device = self._preferred_output_device_id_unlocked()
        # Prefer failing closed over silently opening a different physical device
        # when the configured endpoint is missing (#1345/#1351).
        try:
            self._native_engine.open(self._engine_open_config_unlocked(output_device))
        except Exception as exc:
            warn(
                "Native audio open refused for preferred device (no silent fallback): %s",
                exc,
            )
            self._native_opened = False
            self._preferred_output_device_applied = None
            return
        self._native_opened = True
        self._last_native_engine_frame = 0
        self._preferred_output_device_applied = output_device

    def audio_switch_phase(self) -> str:
        """Return idle|switching|ready|unavailable for preferences status (#1349)."""
        with self._lock:
            return str(getattr(self, "_audio_switch_phase", "idle") or "idle")

    def _fail_closed_device_loss_unlocked(self, reason: str) -> None:
        """Tear down owned engine without opening any other physical device (#1351)."""
        warn("Audio device fail-closed (%s); no silent physical fallback", reason)
        engine = self._native_engine
        try:
            if self._native_started and engine is not None and hasattr(engine, "stop"):
                engine.stop()
        except Exception as exc:  # pragma: no cover - device specific
            warn("Native stop after device loss failed: %s", exc)
        try:
            if self._native_opened and engine is not None and hasattr(engine, "close"):
                engine.close()
        except Exception as exc:  # pragma: no cover - device specific
            warn("Native close after device loss failed: %s", exc)
        self._native_opened = False
        self._native_started = False
        self._last_native_engine_frame = None
        self._preferred_output_device_applied = None
        self._voice_source_bpms.clear()
        self._voice_sync_states.clear()
        self._audio_switch_phase = "unavailable"
        self._audio_output_requires_explicit_retry = True
        # Recreate a clean handle so a later explicit retry can open the
        # persisted preference — never an implicit alternate endpoint.
        if self._native_owned and self._native_available:
            try:
                self._native_engine = _native_audio.NativeAudioEngine()
            except Exception as exc:  # pragma: no cover - machine specific
                warn("Native engine recreate after device loss failed: %s", exc)
                self._native_engine = None
                self._native_available = False

    def reconcile_audio_device_health(self) -> str:
        """Poll native device_status / route truth and fail-closed on loss (#1351).

        Returns the resulting switch phase. Never silently opens another device.
        """
        with self._lock:
            if self._audio_switch_phase == "switching":
                return "switching"
            engine = self._native_engine
            status = 0
            if (
                engine is not None
                and self._native_opened
                and hasattr(engine, "snapshot")
            ):
                try:
                    status = int(getattr(engine.snapshot(), "device_status", 0) or 0)
                except Exception as exc:  # pragma: no cover - device specific
                    warn("Device health snapshot failed: %s", exc)
                    status = 3  # SB_DEVICE_FAILED
            # SB_DEVICE_LOST=1, RECOVERING=2, FAILED=3 — treat auto-recover as
            # untrusted (miniaudio may have rerouted to a different endpoint).
            if status in (1, 2, 3):
                self._fail_closed_device_loss_unlocked(f"device_status={status}")
                return self._audio_switch_phase

            preferred = self._preferred_output_device_id_unlocked()
            if preferred and self._native_opened and engine is not None:
                opened = getattr(engine, "opened_output_device_id", None)
                if opened and opened != preferred:
                    self._fail_closed_device_loss_unlocked("opened_mismatch")
                    return self._audio_switch_phase
                # Preferred disappeared from live enumeration while still persisted.
                # Vendor ASIO identities are CLSIDs from the ASIO registry, not
                # WASAPI endpoint hex ids (#1350).
                audio_system = self._audio_system_unlocked()
                try:
                    if audio_system == "vendor_asio":
                        from .asio_driver_enumeration import enumerate_vendor_asio_drivers

                        enumerated = list(enumerate_vendor_asio_drivers() or [])
                        live_ids = {
                            str(item.get("clsid") or item.get("id") or "")
                            for item in enumerated
                        }
                    else:
                        enumerated = list(
                            _native_audio.NativeAudioEngine.enumerate_devices(False)
                            or []
                        )
                        live_ids = {
                            str(item.get("id_hex") or item.get("id") or "")
                            for item in enumerated
                        }
                except Exception:
                    live_ids = set()
                if preferred not in live_ids:
                    self._fail_closed_device_loss_unlocked("preferred_unavailable")
                    return self._audio_switch_phase

            if self._native_started and self._native_opened:
                self._audio_switch_phase = "ready"
            elif self._audio_switch_phase != "unavailable":
                self._audio_switch_phase = (
                    "ready" if self._native_started else self._audio_switch_phase
                )
            return self._audio_switch_phase

    def retry_preferred_audio_output(self) -> bool:
        """Explicit recovery attempt: reopen persisted preference only (#1351)."""
        with self._lock:
            self._audio_output_requires_explicit_retry = False
        return self.reopen_native_output_device(force=True)

    def reopen_native_output_device(self, *, force: bool = False) -> bool:
        """Close/reopen owned native engine so a new preferred device takes effect.

        V1 transition (#1349): controlled stop → close → resolve → open → start →
        verify. No musical auto-resume. Callers must release active audition
        voices before reopen so ownership cannot point at destroyed native voices.

        Pass ``force=True`` when sample-rate/buffer preferences change but the
        device id stays the same (#1348).
        """
        with self._lock:
            if (
                not self._native_available
                or self._native_engine is None
                or not self._native_owned
            ):
                self._audio_switch_phase = "unavailable"
                return False
            desired = self._preferred_output_device_id_unlocked()
            applied = getattr(self, "_preferred_output_device_applied", None)
            if self._native_opened and desired == applied and not force:
                self._audio_switch_phase = "ready" if self._native_started else "idle"
                return True
            self._audio_switch_phase = "switching"
            self._audio_output_requires_explicit_retry = False
            # Drop voice registrations tied to the destroyed engine.
            self._voice_source_bpms.clear()
            self._voice_sync_states.clear()
            # Tear down owned engine so next ensure_engine_running reopens with preference.
            try:
                if self._native_started and hasattr(self._native_engine, "stop"):
                    self._native_engine.stop()
            except Exception as exc:  # pragma: no cover - device specific
                warn("Native engine stop before device reopen failed: %s", exc)
            try:
                if self._native_opened and hasattr(self._native_engine, "close"):
                    self._native_engine.close()
            except Exception as exc:  # pragma: no cover - device specific
                warn("Native engine close before device reopen failed: %s", exc)
            self._native_opened = False
            self._native_started = False
            self._last_native_engine_frame = None
            self._preferred_output_device_applied = None
            # Recreate engine handle for a clean open contract.
            try:
                self._native_engine = _native_audio.NativeAudioEngine()
            except Exception as exc:  # pragma: no cover - machine specific
                warn("Native audio engine recreate failed: %s", exc)
                self._native_engine = None
                self._native_available = False
                self._audio_switch_phase = "unavailable"
                self._audio_output_requires_explicit_retry = True
                return False
            if not self.ensure_engine_running():
                self._audio_switch_phase = "unavailable"
                self._audio_output_requires_explicit_retry = True
                return False
            # Rebase scheduling clock onto the replacement native epoch while
            # preserving musical session position.
            native_frame = 0
            if hasattr(self._native_engine, "snapshot"):
                try:
                    native_frame = int(self._native_engine.snapshot().engine_frame)
                except Exception as exc:  # pragma: no cover - device specific
                    warn("Native snapshot after device reopen failed: %s", exc)
                    native_frame = 0
            if native_frame < 0:
                native_frame = 0
            self._transport.engine_frame = native_frame
            self._last_native_engine_frame = native_frame
            # Verify opened identity matches the resolved preference when explicit.
            opened = None
            if hasattr(self._native_engine, "opened_output_device_id"):
                opened = getattr(self._native_engine, "opened_output_device_id")
            if desired and opened and opened != desired:
                warn(
                    "Device switch opened mismatch (fail-closed): desired=%s opened=%s",
                    desired[:32] if desired else desired,
                    str(opened)[:32],
                )
                try:
                    if self._native_started:
                        self._native_engine.stop()
                    if self._native_opened:
                        self._native_engine.close()
                except Exception:
                    pass
                self._native_opened = False
                self._native_started = False
                self._preferred_output_device_applied = None
                self._audio_switch_phase = "unavailable"
                return False
            self._audio_switch_phase = "ready"
            return True

    def _rebase_transport_engine_frame_unlocked(self) -> None:
        """Align SessionTransport.engine_frame to the live native clock.

        Native ``start()`` resets ``engine_frame`` to 0. Audition schedules voices
        via ``get_engine_frame()``; if the transport clock still holds a pre-stop
        value, voices stay SCHEDULED in the native future and produce silence
        while ``PreviewResult.ok`` remains True (#1209).
        Musical ``session_frame`` is preserved.
        """
        native_frame = 0
        engine = self._native_engine
        if engine is not None and hasattr(engine, "snapshot"):
            try:
                native_frame = int(engine.snapshot().engine_frame)
            except Exception as exc:  # pragma: no cover - device specific
                warn("Native snapshot after engine start failed: %s", exc)
                native_frame = 0
        if native_frame < 0:
            native_frame = 0
        self._transport.engine_frame = native_frame
        self._last_native_engine_frame = native_frame

    def ensure_engine_running(self) -> bool:
        """Ensure the owned native engine is opened AND running (started).
        Does NOT start the musical transport if it was stopped - only starts the audio engine callback.
        Idempotent: if engine already started, returns True without calling start() again.
        Returns True if engine is available and running."""
        with self._lock:
            if not self._native_available or self._native_engine is None:
                self._audio_switch_phase = "unavailable"
                return False
            if self._audio_output_requires_explicit_retry:
                self._audio_switch_phase = "unavailable"
                return False
            if self._native_owned:
                self._ensure_owned_native_open_unlocked()
            if not self._native_opened:
                if self._audio_switch_phase != "switching":
                    self._audio_switch_phase = "unavailable"
                return False
            if self._native_started:
                if self._audio_switch_phase != "switching":
                    self._audio_switch_phase = "ready"
                return True
            # Start the engine callback without starting musical transport
            try:
                self._native_engine.start()
                self._native_started = True
                if self._rebase_engine_clock_on_next_start:
                    # Native start after stop resets the device clock.
                    self._rebase_transport_engine_frame_unlocked()
                    self._rebase_engine_clock_on_next_start = False
                if self._audio_switch_phase != "switching":
                    self._audio_switch_phase = "ready"
                return True
            except Exception as exc:  # pragma: no cover - machine specific
                warn("Native audio engine start failed: %s", exc)
                self._audio_switch_phase = "unavailable"
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
            before_session = self._transport.session_frame
            self._transport.advance(delta)
            after_tempo = self._effective_tempo_unlocked()
            self._sync_pending_from_map_unlocked()
            if after_tempo != before_tempo:
                self._update_sync_rates_unlocked()
            # Integrate the authoritative source playhead over the ACTUAL session
            # progress that just occurred, not the raw engine delta. If the
            # transport was stopped (engine running, no audition), session did not
            # advance and the source playhead must stay put.
            session_delta = self._transport.session_frame - before_session
            if session_delta:
                self._advance_source_frame_unlocked(session_delta)

        if not bool(getattr(native_snapshot, "running", True)) and self._transport.playing:
            self._transport.stop()

    def _advance_source_frame_unlocked(self, session_frames: int) -> None:
        """Honestly integrate the authoritative source playhead.

        ``session_frames`` is the session delta that ACTUALLY elapsed. The delta is
        split at every tempo segment boundary it crosses, and each sub-range is
        integrated at the rate that was genuinely in effect there. This is
        piecewise integration from an explicit anchor — a later tempo/SYNC/BPM
        change never retroactively touches already-integrated frames, because the
        history is only ever extended, never recomputed from ``session * rate``.

        When the rate is undefined (SYNC on without a known source BPM) the anchor
        is invalidated: the source position becomes unknowable, so HÄFTIG must
        fail closed rather than guess.
        """
        if self._source_frame is None or session_frames <= 0:
            return
        if self._sync_enabled and self._source_bpm is None:
            self._source_frame = None
            self._source_frac = 0.0
            return

        start = self._transport.session_frame - session_frames
        end = self._transport.session_frame

        # Collect every tempo boundary strictly inside (start, end]. Each boundary
        # starts a new segment whose rate applies only to the frames after it.
        boundaries = sorted(
            seg.start_frame
            for seg in self._transport.tempo_map.segments
            if start < seg.start_frame <= end
        )
        cursor = start
        for boundary in boundaries:
            self._integrate_source_segment_unlocked(cursor, boundary)
            cursor = boundary
        self._integrate_source_segment_unlocked(cursor, end)

    def _integrate_source_segment_unlocked(self, seg_start: int, seg_end: int) -> None:
        """Integrate one tempo-homogeneous session sub-range into the anchor."""
        frames = seg_end - seg_start
        if frames <= 0:
            return
        segment = self._transport.tempo_map._segment_for_frame(seg_start)
        rate, _status = _compute_sync_rate(
            float(segment.bpm),
            self._source_bpm,
            self._sync_enabled,
        )
        # Fixed-point accumulation: carry the fractional remainder forward so the
        # integral is exact across calls and callbacks (no per-step rounding).
        self._source_frac += frames * rate
        whole = int(math.floor(self._source_frac))
        self._source_frame += whole
        self._source_frac -= whole

    def get_haeftig_trigger_context(
        self, source_ref: str
    ) -> tuple[int, int] | None:
        """Return ``(trigger_source_frame, trigger_session_frame)`` for HÄFTIG.

        Fail closed (``None``) when the audible position does not map
        unambiguously to a single nominal source frame: no anchor, source
        mismatch, polyphony, or an undefined sync rate. ``KEY_LOCK_SYNC`` is
        intentionally not discriminated — it shares ``RATE_SYNC``'s frame mapping.

        The native clock is refreshed first so the returned position reflects the
        live playhead rather than the last UI poll.
        """
        with self._lock:
            self._refresh_from_native_unlocked()
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
                if not self._native_started:
                    self._native_engine.start()
                    self._native_started = True
                    if self._rebase_engine_clock_on_next_start:
                        self._rebase_transport_engine_frame_unlocked()
                        self._rebase_engine_clock_on_next_start = False
                self._transport.play()
                # Preserve a previously established explicit seek anchor. Only
                # fall back to the configured source-start offset when nothing
                # has been anchored yet (e.g. a plain play without a prior seek).
                if self._source_frame is None:
                    self._source_frame = self._source_start_frame
                    self._source_frac = 0.0
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
            was_started = self._native_started
            self._native_started = False
            # Invalidate the authoritative source playhead: after a stop there is
            # no honest anchor until the next play/seek. HÄFTIG must fail closed.
            self._source_frame = None
            if self._native_engine is not None and self._native_available:
                if not self._native_owned or self._native_opened:
                    try:
                        self._native_engine.stop()
                        # Device clock will reset on the next start(); schedule
                        # clock must follow or re-audition stays silent (#1209).
                        if was_started:
                            self._rebase_engine_clock_on_next_start = True
                    except Exception as exc:  # pragma: no cover - device specific
                        warn("Native engine stop failed: %s", exc)
                        self._native_available = False
                        if was_started:
                            self._rebase_engine_clock_on_next_start = True

    def pause(self) -> None:
        self.stop()

    # ------------------------------------------------------------------
    # Tempo
    # ------------------------------------------------------------------

    def set_on_session_clock_changed(
        self, callback: Callable[[], None] | None
    ) -> None:
        """Bind or clear post-mutation observer for MASTER/SYNC persistence (#818).

        Callbacks fire only after the transport lock is released so callers may
        safely snapshot / autosave without IO under the lock.
        """
        with self._lock:
            self._on_session_clock_changed = callback

    def _resume_master_bpm_unlocked(self) -> float:
        if self._pending_tempo is not None:
            return float(self._pending_tempo)
        return self._effective_tempo_unlocked()

    def get_resume_master_bpm(self) -> float:
        """Latest user-requested MASTER: pending target if any, else current."""
        with self._lock:
            self._refresh_from_native_unlocked()
            return self._resume_master_bpm_unlocked()

    def set_tempo(self, bpm: float) -> int:
        bpm = _clamp_bpm(bpm)
        with self._lock:
            self._refresh_from_native_unlocked()
            before = self._resume_master_bpm_unlocked()
            effective_frame = self._transport.set_tempo(bpm)
            if effective_frame > self._transport.session_frame:
                self._pending_tempo = bpm
                self._pending_tempo_frame = effective_frame
            else:
                self._pending_tempo = None
                self._pending_tempo_frame = None
                self._update_sync_rates_unlocked()
            after = self._resume_master_bpm_unlocked()
            changed = after != before
            callback = self._on_session_clock_changed
        if changed and callback is not None:
            callback()
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
            # Close out any engine/session progress accumulated so far at the
            # CURRENT rate before the sync mode changes, so already-elapsed
            # frames are never re-rated by the new mode.
            self._refresh_from_native_unlocked()
            self._sync_enabled = not self._sync_enabled
            self._update_sync_rates_unlocked()
            enabled = self._sync_enabled
            callback = self._on_session_clock_changed
        if callback is not None:
            callback()
        return enabled

    def set_sync_enabled(self, enabled: bool) -> bool:
        """Deterministic SYNC setter for restore and Python callers (#818).

        Exact bool contract. No-op when the value is already identical. Uses the
        same native rate reconciliation as :meth:`toggle_sync`.
        """
        if type(enabled) is not bool:
            raise TypeError("enabled must be an exact bool")
        with self._lock:
            if self._sync_enabled is enabled:
                return enabled
            self._refresh_from_native_unlocked()
            self._sync_enabled = enabled
            self._update_sync_rates_unlocked()
            callback = self._on_session_clock_changed
        if callback is not None:
            callback()
        return enabled

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
                new_ref = (
                    str(Path(text).expanduser().resolve()) if text else None
                )
                # Switching to a different source invalidates the old playhead:
                # the anchor belongs to the previous source and must not carry over.
                if self._source_ref is not None and new_ref != self._source_ref:
                    self._source_frame = None
                    self._source_frac = 0.0
                self._source_ref = new_ref
            if isinstance(source_start_frame, int) and not isinstance(
                source_start_frame, bool
            ):
                self._source_start_frame = source_start_frame
            # Close out any engine/session progress accumulated so far at the
            # CURRENT source BPM before it changes, so already-elapsed frames are
            # never re-rated by the new BPM.
            self._refresh_from_native_unlocked()
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
                self._source_frac = 0.0
            else:
                # Seek without a known source position: we cannot honestly map the
                # new playhead to a nominal source frame, so invalidate the anchor
                # and let HÄFTIG fail closed until the next explicit anchor.
                self._source_frame = None
                self._source_frac = 0.0

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
            before_session = self._transport.session_frame
            self._transport.advance(frames)
            after_tempo = self._effective_tempo_unlocked()
            self._sync_pending_from_map_unlocked()
            if after_tempo != before_tempo:
                self._update_sync_rates_unlocked()
            session_delta = self._transport.session_frame - before_session
            if session_delta:
                self._advance_source_frame_unlocked(session_delta)

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

    def audio_output_route(self):
        """Return requested/resolved/opened route snapshot (#1346/#1356)."""
        from .audio_device_authority import resolve_audio_output_route
        from .workbench_audio_output import load_workbench_audio_output_settings

        with self._lock:
            settings = load_workbench_audio_output_settings()
            preferred_id = str(settings.preferred_output_device_id or "")
            preferred_name = str(settings.preferred_output_device_name or "")
            settings_audio_system = str(
                getattr(settings, "audio_system", "") or "sample_brain_audio"
            ).strip() or "sample_brain_audio"
            enumerated: list[dict] = []
            try:
                if settings_audio_system == "vendor_asio":
                    from .asio_driver_enumeration import enumerate_vendor_asio_drivers

                    enumerated = [
                        {
                            "id": str(item.get("clsid") or item.get("id") or ""),
                            "id_hex": str(item.get("clsid") or item.get("id") or ""),
                            "name": str(item.get("name") or ""),
                            "is_default": False,
                        }
                        for item in (enumerate_vendor_asio_drivers() or [])
                    ]
                elif self._native_available:
                    enumerated = list(
                        _native_audio.NativeAudioEngine.enumerate_devices(False) or []
                    )
            except Exception as exc:  # pragma: no cover - machine specific
                warn("Audio device enumeration for route snapshot failed: %s", exc)
            opened = getattr(self, "_preferred_output_device_applied", None)
            opened_name = ""
            opened_backend = ""
            engine = self._native_engine
            if engine is not None and hasattr(engine, "opened_output_device_id"):
                opened = getattr(engine, "opened_output_device_id")
            if engine is not None and hasattr(engine, "opened_output_device_name"):
                opened_name = str(getattr(engine, "opened_output_device_name") or "")
            if engine is not None and hasattr(engine, "opened_backend"):
                opened_backend = str(getattr(engine, "opened_backend") or "")
            if not opened_backend:
                opened_backend = (
                    "wasapi"
                    if settings_audio_system == "sample_brain_audio"
                    else settings_audio_system
                )
            return resolve_audio_output_route(
                preferred_id=preferred_id,
                preferred_name=preferred_name,
                enumerated=enumerated,
                opened_device_id=opened,
                opened_device_name=opened_name,
                audio_system=settings_audio_system,
                opened_backend=opened_backend,
            )

    def audio_routing_evidence(self) -> dict[str, object]:
        """Agent-readable routing evidence for #1346/#1352 (no RT callback I/O)."""
        # Health reconcile runs outside the evidence lock body via its own lock.
        phase = self.reconcile_audio_device_health()
        with self._lock:
            route = self.audio_output_route()
            evidence: dict[str, object] = route.as_dict()
            # Canonical inspectable aliases from the #1345 contract.
            evidence["requested_device"] = route.requested_device_id or route.requested_device_name
            evidence["resolved_device"] = route.resolved_device_id or route.resolved_device_name
            evidence["opened_device"] = route.opened_device_id or route.opened_device_name
            evidence.update(
                {
                    "sample_rate": int(self._sample_rate),
                    "buffer_size": None,
                    "device_status": None,
                    "engine_running": bool(self._native_started),
                    "measurable_output": None,
                    "switch_phase": str(phase or getattr(self, "_audio_switch_phase", "idle") or "idle"),
                }
            )
            engine = self._native_engine
            if engine is not None and hasattr(engine, "snapshot"):
                try:
                    snap = engine.snapshot()
                    evidence["sample_rate"] = int(
                        getattr(snap, "sample_rate", self._sample_rate) or self._sample_rate
                    )
                    evidence["buffer_size"] = int(getattr(snap, "buffer_frames", 0) or 0)
                    evidence["device_status"] = int(getattr(snap, "device_status", 0) or 0)
                    evidence["engine_running"] = bool(
                        getattr(snap, "running", self._native_started)
                    )
                    evidence["engine_frame"] = int(getattr(snap, "engine_frame", 0) or 0)
                    evidence["xrun_count"] = int(getattr(snap, "xrun_count", 0) or 0)
                    evidence["underflow_count"] = int(
                        getattr(snap, "underflow_count", 0) or 0
                    )
                    evidence["overflow_count"] = int(
                        getattr(snap, "overflow_count", 0) or 0
                    )
                except Exception as exc:  # pragma: no cover - device specific
                    warn("Audio routing evidence snapshot failed: %s", exc)
            # #1352: non-RT, best-effort process-local WASAPI session peak on the
            # opened endpoint. Never runs inside the audio callback.
            evidence["measurable_output"] = self._measure_opened_output_peak_unlocked(
                route.opened_device_id
            )
            return evidence

    def _measure_opened_output_peak_unlocked(self, opened_device_id: str | None):
        """Return endpoint peak for the opened device, or None.

        Meter COM deps are imported at module load (before native open) to avoid
        RPC_E_CHANGED_MODE. Endpoint meters are coarse (all sessions); PID-scoped
        session meters remain an external agent verification tool (#1352).
        """
        device_id = str(opened_device_id or "").strip()
        if not device_id:
            return None
        # Vendor ASIO bypasses the Windows audio engine; WASAPI endpoint meters
        # cannot observe the stream. Prove callback progress instead (#1350/#1352).
        if device_id.startswith("{") and device_id.endswith("}"):
            if not self._native_started:
                return {
                    "peak": None,
                    "sessions_active": 0,
                    "source": "vendor_asio_engine_stopped",
                    "engine_frame": 0,
                }
            engine = self._native_engine
            frame = 0
            try:
                if engine is not None and hasattr(engine, "snapshot"):
                    frame = int(getattr(engine.snapshot(), "engine_frame", 0) or 0)
                elif engine is not None and hasattr(engine, "get_frame"):
                    frame = int(engine.get_frame())
            except Exception as exc:  # pragma: no cover - device specific
                warn("vendor ASIO measurable_output frame probe failed: %s", exc)
                frame = -1
            return {
                "peak": None,
                "sessions_active": None,
                "source": "vendor_asio_callback_frame",
                "engine_frame": frame,
                "callback_advancing": frame > 0,
            }
        if len(device_id) != 512:
            return None
        if not self._native_started:
            return {"peak": 0.0, "sessions_active": 0, "source": "engine_stopped"}
        if _METER_IMPORT_ERROR or _METER_CoCreateInstance is None or _METER_Iface is None:
            return None
        try:
            wasapi_id = (
                bytes.fromhex(device_id).decode("utf-16-le", errors="ignore").split("\x00")[0]
            )
            enumerator = _METER_CoCreateInstance(
                _METER_CLSID, _METER_IMMDevEnum, _METER_CLSCTX_ALL
            )
            device = enumerator.GetDevice(wasapi_id)
            iface = device.Activate(_METER_Iface._iid_, _METER_CLSCTX_ALL, None)
            meter = _METER_CAST(iface, _METER_POINTER(_METER_Iface))
            return {
                "peak": float(meter.GetPeakValue()),
                "sessions_active": None,
                "source": "wasapi_endpoint_meter_coarse",
            }
        except Exception as exc:  # pragma: no cover - host/COM specific
            warn("measurable_output probe failed: %s", exc)
            return None

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
