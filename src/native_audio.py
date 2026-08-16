"""
Native audio FFI binding for samplebrain_audio C++ core.

This module provides a thin ctypes wrapper around the native library.
The native library must be built separately and placed in the library search path.
"""

from __future__ import annotations

import ctypes
import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Tuple

# Load native library
def _find_library() -> Path:
    """Find the native library."""
    # Check common locations
    candidates = [
        Path(__file__).parent.parent.parent / "native" / "audio" / "build" / "lib" / "samplebrain_audio.dll",
        Path(__file__).parent.parent.parent / "native" / "audio" / "build" / "bin" / "samplebrain_audio.dll",
        Path(__file__).parent.parent / "native" / "audio" / "build" / "lib" / "samplebrain_audio.dll",
        Path(__file__).parent.parent / "native" / "audio" / "build" / "bin" / "samplebrain_audio.dll",
    ]

    if platform.system() == "Windows":
        for c in candidates:
            if c.exists():
                return c
        # Try system search
        return Path("samplebrain_audio.dll")
    else:
        # Linux/macOS
        for c in candidates:
            if c.exists():
                return c
        return Path("libsamplebrain_audio.so")

_lib_path = _find_library()
try:
    _lib = ctypes.CDLL(str(_lib_path))
except OSError:
    _lib = None
    import warnings
    warnings.warn(f"Could not load native library from {_lib_path}. Native audio unavailable.")


# Constants
SB_OK = 0
SB_ERR_INVALID_ARG = -1
SB_ERR_NOT_INITIALIZED = -2
SB_ERR_ALREADY_RUNNING = -3
SB_ERR_DEVICE_ERROR = -4
SB_ERR_OUT_OF_MEMORY = -5
SB_ERR_VOICE_NOT_FOUND = -6
SB_ERR_RECORDING_NOT_FOUND = -7
SB_ERR_INVALID_STATE = -8
SB_ERR_UNSUPPORTED = -9

SB_DEVICE_OK = 0
SB_DEVICE_LOST = 1
SB_DEVICE_RECOVERING = 2
SB_DEVICE_FAILED = 3

SB_VOICE_IDLE = 0
SB_VOICE_SCHEDULED = 1
SB_VOICE_PLAYING = 2
SB_VOICE_STOPPING = 3

SB_SOURCE_SYNTHETIC_CLICK = 0
SB_SOURCE_PCM_BUFFER = 1

SB_MAX_VOICES = 32
SB_MAX_RECORDINGS = 8


# C type definitions
sb_frame_t = ctypes.c_int64
sb_voice_id_t = ctypes.c_uint64
sb_recording_id_t = ctypes.c_uint64
sb_result_t = ctypes.c_int
sb_device_status_t = ctypes.c_int
sb_voice_state_t = ctypes.c_int

# Opaque handles
sb_engine_t = ctypes.c_void_p
sb_voice_t = ctypes.c_void_p
sb_recording_t = ctypes.c_void_p


# Structures
class SbSyntheticClickConfig(ctypes.Structure):
    _fields_ = [
        ("bpm", ctypes.c_double),
        ("frequency_hz", ctypes.c_float),
        ("duration_ms", ctypes.c_float),
        ("amplitude", ctypes.c_float),
    ]


class SbSourceDescriptor(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("synthetic_click", SbSyntheticClickConfig),
    ]


class SbEngineConfig(ctypes.Structure):
    _fields_ = [
        ("sample_rate", ctypes.c_uint32),
        ("buffer_frames", ctypes.c_uint32),
        ("output_channels", ctypes.c_uint32),
        ("input_channels", ctypes.c_uint32),
        ("output_device", ctypes.c_char_p),
        ("input_device", ctypes.c_char_p),
        ("user_data", ctypes.c_void_p),
    ]


class SbVoiceConfig(ctypes.Structure):
    _fields_ = [
        ("id", sb_voice_id_t),
        ("source", SbSourceDescriptor),
        ("initial_rate", ctypes.c_float),
        ("gain", ctypes.c_float),
    ]


class SbSnapshot(ctypes.Structure):
    _fields_ = [
        ("engine_frame", sb_frame_t),
        ("running", ctypes.c_bool),
        ("sample_rate", ctypes.c_uint32),
        ("buffer_frames", ctypes.c_uint32),
        ("device_status", sb_device_status_t),
        ("recovery_state", ctypes.c_uint32),
        ("active_voice_count", ctypes.c_uint32),
        ("total_voice_count", ctypes.c_uint32),
        ("voice_ids", sb_voice_id_t * SB_MAX_VOICES),
        ("voice_states", sb_voice_state_t * SB_MAX_VOICES),
        ("requested_start_frame", sb_frame_t * SB_MAX_VOICES),
        ("actual_start_frame", sb_frame_t * SB_MAX_VOICES),
        ("start_skew_frames", ctypes.c_int32 * SB_MAX_VOICES),
        ("voice_rates", ctypes.c_float * SB_MAX_VOICES),
        ("voice_gains", ctypes.c_float * SB_MAX_VOICES),
        ("callback_mean_us", ctypes.c_double),
        ("callback_p95_us", ctypes.c_double),
        ("callback_p99_us", ctypes.c_double),
        ("callback_max_us", ctypes.c_double),
        ("underflow_count", ctypes.c_uint64),
        ("overflow_count", ctypes.c_uint64),
        ("xrun_count", ctypes.c_uint64),
        ("recording_dropped_frames", ctypes.c_uint64),
        ("recording_active", ctypes.c_bool),
        ("reserved", ctypes.c_uint64 * 16),
    ]


# Function prototypes
if _lib:
    _lib.sb_engine_open.argtypes = [ctypes.POINTER(SbEngineConfig), ctypes.POINTER(sb_engine_t)]
    _lib.sb_engine_open.restype = sb_result_t

    _lib.sb_engine_start.argtypes = [sb_engine_t]
    _lib.sb_engine_start.restype = sb_result_t

    _lib.sb_engine_stop.argtypes = [sb_engine_t]
    _lib.sb_engine_stop.restype = sb_result_t

    _lib.sb_engine_close.argtypes = [sb_engine_t]
    _lib.sb_engine_close.restype = sb_result_t

    _lib.sb_voice_create.argtypes = [sb_engine_t, ctypes.POINTER(SbVoiceConfig), ctypes.POINTER(sb_voice_id_t)]
    _lib.sb_voice_create.restype = sb_result_t

    _lib.sb_voice_remove.argtypes = [sb_engine_t, sb_voice_id_t]
    _lib.sb_voice_remove.restype = sb_result_t

    _lib.sb_voice_schedule_start.argtypes = [sb_engine_t, sb_voice_id_t, sb_frame_t]
    _lib.sb_voice_schedule_start.restype = sb_result_t

    _lib.sb_voice_stop.argtypes = [sb_engine_t, sb_voice_id_t]
    _lib.sb_voice_stop.restype = sb_result_t

    _lib.sb_voice_set_rate.argtypes = [sb_engine_t, sb_voice_id_t, ctypes.c_float]
    _lib.sb_voice_set_rate.restype = sb_result_t

    _lib.sb_recording_start.argtypes = [sb_engine_t, ctypes.POINTER(sb_recording_id_t), sb_frame_t]
    _lib.sb_recording_start.restype = sb_result_t

    _lib.sb_recording_stop.argtypes = [sb_engine_t, sb_recording_id_t, ctypes.POINTER(ctypes.POINTER(ctypes.c_float)), ctypes.POINTER(ctypes.c_size_t)]
    _lib.sb_recording_stop.restype = sb_result_t

    _lib.sb_recording_free_buffer.argtypes = [ctypes.POINTER(ctypes.c_float)]
    _lib.sb_recording_free_buffer.restype = None

    _lib.sb_engine_snapshot.argtypes = [sb_engine_t, ctypes.POINTER(SbSnapshot)]
    _lib.sb_engine_snapshot.restype = sb_result_t


def _check_result(result: sb_result_t, operation: str) -> None:
    """Raise exception on error result."""
    if result != SB_OK:
        error_names = {
            SB_ERR_INVALID_ARG: "Invalid argument",
            SB_ERR_NOT_INITIALIZED: "Not initialized",
            SB_ERR_ALREADY_RUNNING: "Already running",
            SB_ERR_DEVICE_ERROR: "Device error",
            SB_ERR_OUT_OF_MEMORY: "Out of memory",
            SB_ERR_VOICE_NOT_FOUND: "Voice not found",
            SB_ERR_RECORDING_NOT_FOUND: "Recording not found",
            SB_ERR_INVALID_STATE: "Invalid state",
            SB_ERR_UNSUPPORTED: "Unsupported",
        }
        raise RuntimeError(f"{operation} failed: {error_names.get(result, f'Unknown error ({result})')}")


@dataclass
class EngineConfig:
    """Engine configuration."""
    sample_rate: int = 48000
    buffer_frames: int = 512
    output_channels: int = 2
    input_channels: int = 2
    output_device: Optional[str] = None
    input_device: Optional[str] = None


@dataclass
class VoiceConfig:
    """Voice configuration."""
    id: int
    source_type: int = SB_SOURCE_SYNTHETIC_CLICK
    bpm: float = 128.0
    frequency_hz: float = 800.0
    duration_ms: float = 5.0
    amplitude: float = 0.8
    initial_rate: float = 1.0
    gain: float = 1.0


@dataclass
class Snapshot:
    """Engine snapshot with metrics."""
    engine_frame: int
    running: bool
    sample_rate: int
    buffer_frames: int
    device_status: int
    recovery_state: int
    active_voice_count: int
    total_voice_count: int
    voice_ids: List[int]
    voice_states: List[int]
    requested_start_frame: List[int]
    actual_start_frame: List[int]
    start_skew_frames: List[int]
    voice_rates: List[float]
    voice_gains: List[float]
    callback_mean_us: float
    callback_p95_us: float
    callback_p99_us: float
    callback_max_us: float
    underflow_count: int
    overflow_count: int
    xrun_count: int
    recording_dropped_frames: int
    recording_active: bool

    @classmethod
    def from_c_snapshot(cls, c_snap: SbSnapshot) -> "Snapshot":
        return cls(
            engine_frame=c_snap.engine_frame,
            running=c_snap.running,
            sample_rate=c_snap.sample_rate,
            buffer_frames=c_snap.buffer_frames,
            device_status=c_snap.device_status,
            recovery_state=c_snap.recovery_state,
            active_voice_count=c_snap.active_voice_count,
            total_voice_count=c_snap.total_voice_count,
            voice_ids=[c_snap.voice_ids[i] for i in range(SB_MAX_VOICES)],
            voice_states=[c_snap.voice_states[i] for i in range(SB_MAX_VOICES)],
            requested_start_frame=[c_snap.requested_start_frame[i] for i in range(SB_MAX_VOICES)],
            actual_start_frame=[c_snap.actual_start_frame[i] for i in range(SB_MAX_VOICES)],
            start_skew_frames=[c_snap.start_skew_frames[i] for i in range(SB_MAX_VOICES)],
            voice_rates=[c_snap.voice_rates[i] for i in range(SB_MAX_VOICES)],
            voice_gains=[c_snap.voice_gains[i] for i in range(SB_MAX_VOICES)],
            callback_mean_us=c_snap.callback_mean_us,
            callback_p95_us=c_snap.callback_p95_us,
            callback_p99_us=c_snap.callback_p99_us,
            callback_max_us=c_snap.callback_max_us,
            underflow_count=c_snap.underflow_count,
            overflow_count=c_snap.overflow_count,
            xrun_count=c_snap.xrun_count,
            recording_dropped_frames=c_snap.recording_dropped_frames,
            recording_active=c_snap.recording_active,
        )


class NativeAudioEngine:
    """Python wrapper for native audio engine."""

    def __init__(self):
        if not _lib:
            raise RuntimeError("Native library not loaded")
        self._engine: Optional[sb_engine_t] = None

    def open(self, config: EngineConfig) -> None:
        """Open the audio engine."""
        c_config = SbEngineConfig(
            sample_rate=config.sample_rate,
            buffer_frames=config.buffer_frames,
            output_channels=config.output_channels,
            input_channels=config.input_channels,
            output_device=config.output_device.encode() if config.output_device else None,
            input_device=config.input_device.encode() if config.input_device else None,
            user_data=None,
        )
        engine = sb_engine_t()
        _check_result(_lib.sb_engine_open(ctypes.byref(c_config), ctypes.byref(engine)), "open")
        self._engine = engine

    def start(self) -> None:
        """Start the audio engine."""
        if not self._engine:
            raise RuntimeError("Engine not open")
        _check_result(_lib.sb_engine_start(self._engine), "start")

    def stop(self) -> None:
        """Stop the audio engine."""
        if not self._engine:
            raise RuntimeError("Engine not open")
        _check_result(_lib.sb_engine_stop(self._engine), "stop")

    def close(self) -> None:
        """Close the audio engine."""
        if not self._engine:
            raise RuntimeError("Engine not open")
        _check_result(_lib.sb_engine_close(self._engine), "close")
        self._engine = None

    def create_voice(self, config: VoiceConfig) -> int:
        """Create a voice."""
        if not self._engine:
            raise RuntimeError("Engine not open")

        click_config = SbSyntheticClickConfig(
            bpm=config.bpm,
            frequency_hz=config.frequency_hz,
            duration_ms=config.duration_ms,
            amplitude=config.amplitude,
        )
        source = SbSourceDescriptor(type=config.source_type, synthetic_click=click_config)
        vconfig = SbVoiceConfig(
            id=config.id,
            source=source,
            initial_rate=config.initial_rate,
            gain=config.gain,
        )
        voice_id = sb_voice_id_t()
        _check_result(_lib.sb_voice_create(self._engine, ctypes.byref(vconfig), ctypes.byref(voice_id)), "create_voice")
        return voice_id.value

    def remove_voice(self, voice_id: int) -> None:
        """Remove a voice."""
        if not self._engine:
            raise RuntimeError("Engine not open")
        _check_result(_lib.sb_voice_remove(self._engine, voice_id), "remove_voice")

    def schedule_voice_start(self, voice_id: int, engine_frame: int) -> None:
        """Schedule voice to start at exact engine frame."""
        if not self._engine:
            raise RuntimeError("Engine not open")
        _check_result(_lib.sb_voice_schedule_start(self._engine, voice_id, engine_frame), "schedule_voice_start")

    def stop_voice(self, voice_id: int) -> None:
        """Stop a voice."""
        if not self._engine:
            raise RuntimeError("Engine not open")
        _check_result(_lib.sb_voice_stop(self._engine, voice_id), "stop_voice")

    def set_voice_rate(self, voice_id: int, rate: float) -> None:
        """Set voice playback rate."""
        if not self._engine:
            raise RuntimeError("Engine not open")
        _check_result(_lib.sb_voice_set_rate(self._engine, voice_id, rate), "set_voice_rate")

    def start_recording(self, engine_frame: int) -> int:
        """Start recording at engine frame."""
        if not self._engine:
            raise RuntimeError("Engine not open")
        rec_id = sb_recording_id_t()
        _check_result(_lib.sb_recording_start(self._engine, ctypes.byref(rec_id), engine_frame), "start_recording")
        return rec_id.value

    def stop_recording(self, recording_id: int) -> Tuple[bytes, int]:
        """Stop recording and return audio data."""
        if not self._engine:
            raise RuntimeError("Engine not open")
        buffer_ptr = ctypes.POINTER(ctypes.c_float)()
        frames = ctypes.c_size_t()
        _check_result(_lib.sb_recording_stop(self._engine, recording_id, ctypes.byref(buffer_ptr), ctypes.byref(frames)), "stop_recording")

        # Convert to bytes
        num_samples = frames.value * 2  # stereo
        data = ctypes.string_at(buffer_ptr, num_samples * ctypes.sizeof(ctypes.c_float))
        _lib.sb_recording_free_buffer(buffer_ptr)
        return data, frames.value

    def snapshot(self) -> Snapshot:
        """Get engine snapshot."""
        if not self._engine:
            raise RuntimeError("Engine not open")
        snap = SbSnapshot()
        _check_result(_lib.sb_engine_snapshot(self._engine, ctypes.byref(snap)), "snapshot")
        return Snapshot.from_c_snapshot(snap)

    def __enter__(self) -> "NativeAudioEngine":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._engine:
            try:
                self.stop()
            except Exception:
                pass
            try:
                self.close()
            except Exception:
                pass


def is_available() -> bool:
    """Check if native audio is available."""
    return _lib is not None


# Convenience function for quick testing
def run_sync_test(
    sample_rate: int = 48000,
    buffer_frames: int = 512,
    duration_sec: float = 2.0,
) -> Snapshot:
    """Run a quick sync test with two click tracks."""
    engine = NativeAudioEngine()
    try:
        engine.open(EngineConfig(sample_rate=sample_rate, buffer_frames=buffer_frames))
        engine.start()

        # Voice A: 128 BPM -> 132 BPM
        engine.create_voice(VoiceConfig(
            id=1,
            bpm=128.0,
            initial_rate=132.0 / 128.0,
        ))

        # Voice B: 140 BPM -> 132 BPM
        engine.create_voice(VoiceConfig(
            id=2,
            bpm=140.0,
            initial_rate=132.0 / 140.0,
        ))

        # Schedule both at same frame
        import time
        time.sleep(0.1)
        snap = engine.snapshot()
        start_frame = snap.engine_frame + int(0.5 * sample_rate)

        engine.schedule_voice_start(1, start_frame)
        engine.schedule_voice_start(2, start_frame)

        # Wait for playback
        time.sleep(duration_sec)

        return engine.snapshot()
    finally:
        engine.close()


if __name__ == "__main__":
    # Quick self-test
    if not is_available():
        print("Native audio not available")
        sys.exit(1)

    print("Running native audio sync test...")
    snap = run_sync_test()
    print(f"Engine frame: {snap.engine_frame}")
    print(f"Active voices: {snap.active_voice_count}")
    print(f"Voice 1 skew: {snap.start_skew_frames[0]} frames")
    print(f"Voice 2 skew: {snap.start_skew_frames[1]} frames")
    print(f"Callback mean: {snap.callback_mean_us:.2f} us")
    print(f"Callback max: {snap.callback_max_us:.2f} us")
    print(f"Xruns: {snap.xrun_count}")
    print("Test complete")