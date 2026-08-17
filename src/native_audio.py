"""
Native audio FFI binding for samplebrain_audio C++ core.

This module provides a thin ctypes wrapper around the native library.
The native library must be built separately and placed in the library search path.
"""

from __future__ import annotations

import ctypes
import math
import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Tuple

import numpy as np

# Load native library
def _find_library() -> Path:
    """Find the native library."""
    # Check common locations
    candidates = [
        Path(__file__).parent.parent.parent / "native" / "audio" / "build" / "lib" / "Release" / "samplebrain_audio.dll",
        Path(__file__).parent.parent.parent / "native" / "audio" / "build" / "bin" / "Release" / "samplebrain_audio.dll",
        Path(__file__).parent.parent / "native" / "audio" / "build" / "lib" / "Release" / "samplebrain_audio.dll",
        Path(__file__).parent.parent / "native" / "audio" / "build" / "bin" / "Release" / "samplebrain_audio.dll",
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
SB_ERR_BUFFER_TOO_SMALL = -10

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

# Sync mode constants (#324)
SB_SYNC_MODE_RATE_SYNC = 0      # Rate = master/source, pitch follows tempo (#323)
SB_SYNC_MODE_KEY_LOCK_SYNC = 1  # Tempo follows master, pitch preserved via Signalsmith (#324)

class SyncMode:
    RATE_SYNC = SB_SYNC_MODE_RATE_SYNC
    KEY_LOCK_SYNC = SB_SYNC_MODE_KEY_LOCK_SYNC

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
        ("sync_mode", ctypes.c_int),
        ("source_bpm", ctypes.c_float),
        ("master_bpm", ctypes.c_float),
    ]


class SbDeviceInfo(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_char * 256),
        ("id_hex", ctypes.c_char * 512),
        ("is_default", ctypes.c_int),
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
        ("voice_sync_modes", ctypes.c_int * SB_MAX_VOICES),
        ("voice_key_lock_active", ctypes.c_bool * SB_MAX_VOICES),
        ("voice_input_latency_frames", ctypes.c_int32 * SB_MAX_VOICES),
        ("voice_output_latency_frames", ctypes.c_int32 * SB_MAX_VOICES),
        ("voice_grid_compensation_frames", ctypes.c_int32 * SB_MAX_VOICES),
        ("callback_mean_us", ctypes.c_double),
        ("callback_p95_us", ctypes.c_double),
        ("callback_p99_us", ctypes.c_double),
        ("callback_max_us", ctypes.c_double),
        ("callback_p99_9_us", ctypes.c_double),
        ("underflow_count", ctypes.c_uint64),
        ("overflow_count", ctypes.c_uint64),
        ("xrun_count", ctypes.c_uint64),
        ("recording_dropped_frames", ctypes.c_uint64),
        ("recording_active", ctypes.c_bool),
        ("reserved", ctypes.c_uint64 * 8),
    ]


# Test API for #324 offline KeyLockVoice processing
class SbTestKeylockConfig(ctypes.Structure):
    _fields_ = [
        ("sample_rate", ctypes.c_int),
        ("channels", ctypes.c_int),
        ("sync_mode", ctypes.c_int),
        ("source_bpm", ctypes.c_float),
        ("master_bpm", ctypes.c_float),
        ("frequency_hz", ctypes.c_float),
        ("amplitude", ctypes.c_float),
    ]


# Function prototypes
if _lib:
    _lib.sb_engine_open.argtypes = [ctypes.POINTER(SbEngineConfig), ctypes.POINTER(sb_engine_t)]
    _lib.sb_engine_open.restype = sb_result_t

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

    _lib.sb_voice_set_sync_mode.argtypes = [sb_engine_t, sb_voice_id_t, ctypes.c_int]
    _lib.sb_voice_set_sync_mode.restype = sb_result_t

    _lib.sb_voice_set_source_bpm.argtypes = [sb_engine_t, sb_voice_id_t, ctypes.c_float]
    _lib.sb_voice_set_source_bpm.restype = sb_result_t

    _lib.sb_voice_set_master_bpm.argtypes = [sb_engine_t, sb_voice_id_t, ctypes.c_float]
    _lib.sb_voice_set_master_bpm.restype = sb_result_t

    _lib.sb_recording_start.argtypes = [sb_engine_t, ctypes.POINTER(sb_recording_id_t), sb_frame_t]
    _lib.sb_recording_start.restype = sb_result_t

    _lib.sb_recording_stop.argtypes = [sb_engine_t, sb_recording_id_t, ctypes.POINTER(ctypes.POINTER(ctypes.c_float)), ctypes.POINTER(ctypes.c_size_t)]
    _lib.sb_recording_stop.restype = sb_result_t

    _lib.sb_recording_free_buffer.argtypes = [ctypes.POINTER(ctypes.c_float)]
    _lib.sb_recording_free_buffer.restype = None

    _lib.sb_engine_snapshot.argtypes = [sb_engine_t, ctypes.POINTER(SbSnapshot)]
    _lib.sb_engine_snapshot.restype = sb_result_t

    # Engine version
    _lib.sb_engine_version.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
    _lib.sb_engine_version.restype = sb_result_t

    # Device enumeration
    _lib.sb_enumerate_devices.argtypes = [ctypes.c_int, ctypes.POINTER(SbDeviceInfo), ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32)]
    _lib.sb_enumerate_devices.restype = sb_result_t

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

    # #324 Key-Lock voice control
    _lib.sb_voice_set_sync_mode.argtypes = [sb_engine_t, sb_voice_id_t, ctypes.c_int]
    _lib.sb_voice_set_sync_mode.restype = sb_result_t

    _lib.sb_voice_set_source_bpm.argtypes = [sb_engine_t, sb_voice_id_t, ctypes.c_float]
    _lib.sb_voice_set_source_bpm.restype = sb_result_t

    _lib.sb_voice_set_master_bpm.argtypes = [sb_engine_t, sb_voice_id_t, ctypes.c_float]
    _lib.sb_voice_set_master_bpm.restype = sb_result_t

    _lib.sb_recording_start.argtypes = [sb_engine_t, ctypes.POINTER(sb_recording_id_t), sb_frame_t]
    _lib.sb_recording_start.restype = sb_result_t

    _lib.sb_recording_stop.argtypes = [sb_engine_t, sb_recording_id_t, ctypes.POINTER(ctypes.POINTER(ctypes.c_float)), ctypes.POINTER(ctypes.c_size_t)]
    _lib.sb_recording_stop.restype = sb_result_t

    _lib.sb_recording_free_buffer.argtypes = [ctypes.POINTER(ctypes.c_float)]
    _lib.sb_recording_free_buffer.restype = None

    _lib.sb_engine_snapshot.argtypes = [sb_engine_t, ctypes.POINTER(SbSnapshot)]
    _lib.sb_engine_snapshot.restype = sb_result_t

    # #324 Test API: Offline KeyLockVoice processing
    _lib.sb_test_keylock_process.argtypes = [
        ctypes.POINTER(SbTestKeylockConfig),
        ctypes.POINTER(ctypes.c_float),
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_float),
        ctypes.c_size_t,
    ]
    _lib.sb_test_keylock_process.restype = ctypes.c_int

    _lib.sb_test_keylock_get_latency.argtypes = [
        ctypes.POINTER(SbTestKeylockConfig),
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_int),
    ]
    _lib.sb_test_keylock_get_latency.restype = ctypes.c_int


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
    # #324 Key-Lock extensions
    sync_mode: int = SB_SYNC_MODE_RATE_SYNC
    source_bpm: float = 128.0
    master_bpm: float = 132.0


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
    # #324 Key-Lock extensions
    voice_sync_modes: List[int]
    voice_key_lock_active: List[bool]
    voice_input_latency_frames: List[int]
    voice_output_latency_frames: List[int]
    voice_grid_compensation_frames: List[int]
    callback_mean_us: float
    callback_p95_us: float
    callback_p99_us: float
    callback_max_us: float
    callback_p99_9_us: float
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
            voice_sync_modes=[c_snap.voice_sync_modes[i] for i in range(SB_MAX_VOICES)],
            voice_key_lock_active=[bool(c_snap.voice_key_lock_active[i]) for i in range(SB_MAX_VOICES)],
            voice_input_latency_frames=[c_snap.voice_input_latency_frames[i] for i in range(SB_MAX_VOICES)],
            voice_output_latency_frames=[c_snap.voice_output_latency_frames[i] for i in range(SB_MAX_VOICES)],
            voice_grid_compensation_frames=[c_snap.voice_grid_compensation_frames[i] for i in range(SB_MAX_VOICES)],
            callback_mean_us=c_snap.callback_mean_us,
            callback_p95_us=c_snap.callback_p95_us,
            callback_p99_us=c_snap.callback_p99_us,
            callback_max_us=c_snap.callback_max_us,
            callback_p99_9_us=c_snap.callback_p99_9_us,
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

    def get_version(self) -> str:
        """Get the native engine build version."""
        if not self._engine:
            raise RuntimeError("Engine not open")
        buf = ctypes.create_string_buffer(256)
        _check_result(_lib.sb_engine_version(buf, len(buf)), "get_version")
        return buf.value.decode()

    @staticmethod
    def enumerate_devices(capture: bool = False) -> List[dict]:
        """Enumerate audio devices."""
        if not _lib:
            raise RuntimeError("Native library not loaded")
        max_count = 32
        devices = (SbDeviceInfo * max_count)()
        count = ctypes.c_uint32()
        _check_result(_lib.sb_enumerate_devices(1 if capture else 0, devices, max_count, ctypes.byref(count)), "enumerate_devices")
        result = []
        for i in range(count.value):
            d = devices[i]
            result.append({
                "name": d.name.decode().rstrip('\x00'),
                "id_hex": d.id_hex.decode().rstrip('\x00'),
                "is_default": bool(d.is_default),
            })
        return result

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
            sync_mode=config.sync_mode,
            source_bpm=config.source_bpm,
            master_bpm=config.master_bpm,
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

    def set_voice_sync_mode(self, voice_id: int, sync_mode: int) -> None:
        """Set voice sync mode (SB_SYNC_MODE_RATE_SYNC or SB_SYNC_MODE_KEY_LOCK_SYNC)."""
        if not self._engine:
            raise RuntimeError("Engine not open")
        _check_result(_lib.sb_voice_set_sync_mode(self._engine, voice_id, sync_mode), "set_voice_sync_mode")

    def set_voice_source_bpm(self, voice_id: int, source_bpm: float) -> None:
        """Set voice source BPM for sync calculations."""
        if not self._engine:
            raise RuntimeError("Engine not open")
        _check_result(_lib.sb_voice_set_source_bpm(self._engine, voice_id, source_bpm), "set_voice_source_bpm")

    def set_voice_master_bpm(self, voice_id: int, master_bpm: float) -> None:
        """Set voice master BPM for sync calculations."""
        if not self._engine:
            raise RuntimeError("Engine not open")
        _check_result(_lib.sb_voice_set_master_bpm(self._engine, voice_id, master_bpm), "set_voice_master_bpm")

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


class KeyLockVoice:
    """Python wrapper for offline KeyLockVoice processing using native Signalsmith.
    
    This wrapper provides offline processing through the native KeyLockVoice C++ class,
    which uses Signalsmith Stretch for pitch-preserving time-stretch (#324).
    
    Usage:
        kv = KeyLockVoice(48000, 128.0, 132.0, SyncMode.KEY_LOCK_SYNC)
        result = kv.process(input_buffer, num_frames)
    """
    
    def __init__(self, sample_rate: int, source_bpm: float, master_bpm: float,
                 sync_mode: int = SB_SYNC_MODE_KEY_LOCK_SYNC,
                 frequency_hz: float = 800.0, amplitude: float = 0.8,
                 channels: int = 1):
        if not _lib:
            raise RuntimeError("Native library not loaded")
        self._sample_rate = sample_rate
        self._channels = channels
        self._sync_mode = sync_mode
        self._source_bpm = source_bpm
        self._master_bpm = master_bpm
        self._frequency_hz = frequency_hz
        self._amplitude = amplitude
        self._tempo_ratio = master_bpm / source_bpm if source_bpm > 0 else 1.0
    
    def process(self, num_frames: int) -> Tuple[bytes, int]:
        """Process audio through KeyLockVoice offline.

        Generates a synthetic click at the source BPM interval, processes it
        through the configured sync mode, and returns the output as bytes.

        Args:
            num_frames: Number of output frames to generate

        Returns:
            Tuple of (audio_bytes, frames_processed)
        """
        if not _lib:
            raise RuntimeError("Native library not loaded")

        config = SbTestKeylockConfig(
            sample_rate=self._sample_rate,
            channels=self._channels,
            sync_mode=self._sync_mode,
            source_bpm=self._source_bpm,
            master_bpm=self._master_bpm,
            frequency_hz=self._frequency_hz,
            amplitude=self._amplitude,
        )

        # Generate input buffer: synthetic clicks at source BPM
        input_duration_sec = 4.0  # Generate 4 seconds of source
        input_frames = int(input_duration_sec * self._sample_rate)
        input_buffer = (ctypes.c_float * input_frames)()

        # Generate synthetic clicks
        interval_sec = 60.0 / self._source_bpm
        click_interval = int(interval_sec * self._sample_rate)
        click_duration_ms = 5.0
        click_samples = max(1, int(click_duration_ms / 1000.0 * self._sample_rate))

        for frame in range(0, input_frames, click_interval):
            for i in range(click_samples):
                t = float(i) / self._sample_rate
                envelope = 1.0 - t / (click_duration_ms / 1000.0)
                if envelope <= 0:
                    break
                envelope = max(0.0, envelope * envelope)
                val = self._amplitude * math.sin(2 * math.pi * self._frequency_hz * t) * envelope
                if frame + i < input_frames:
                    input_buffer[frame + i] += val

        output_frames_expected = int(num_frames)
        output_buffer = (ctypes.c_float * (output_frames_expected * self._channels))()

        frames_written = int(_lib.sb_test_keylock_process(
            ctypes.byref(config),
            input_buffer,
            input_frames,
            output_buffer,
            output_frames_expected
        ))

        if frames_written < 0:
            raise RuntimeError("KeyLockVoice processing failed")

        # Convert output to bytes
        num_samples = frames_written * self._channels
        data = ctypes.string_at(output_buffer, num_samples * ctypes.sizeof(ctypes.c_float))
        return data, frames_written

    def process_audio(self, input_signal: np.ndarray) -> Tuple[np.ndarray, dict]:
        """Process external audio signal through KeyLockVoice offline.

        This is the preferred method for testing pitch preservation, as it
        processes the actual input signal through the native KeyLockVoice
        (with Signalsmith for Key-Lock mode) rather than synthetic clicks.

        Args:
            input_signal: 1D numpy array of float32 audio samples

        Returns:
            Tuple of (processed_signal, metadata_dict)
        """
        if not _lib:
            raise RuntimeError("Native library not loaded")

        input_frames = len(input_signal)
        # Ensure float32
        if input_signal.dtype != np.float32:
            input_signal = input_signal.astype(np.float32)

        config = SbTestKeylockConfig(
            sample_rate=self._sample_rate,
            channels=self._channels,
            sync_mode=self._sync_mode,
            source_bpm=self._source_bpm,
            master_bpm=self._master_bpm,
            frequency_hz=self._frequency_hz,
            amplitude=self._amplitude,
        )

        # Calculate expected output frames (time-stretched by tempo ratio)
        ratio = self._master_bpm / self._source_bpm if self._source_bpm > 0 else 1.0
        expected_output_frames = max(1, int(input_frames / ratio))

        input_buffer = input_signal.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
        output_buffer = (ctypes.c_float * (expected_output_frames * self._channels))()

        frames_written = int(_lib.sb_test_keylock_process(
            ctypes.byref(config),
            input_buffer,
            input_frames,
            output_buffer,
            expected_output_frames
        ))

        if frames_written < 0:
            raise RuntimeError("KeyLockVoice processing failed")

        processed = np.ctypeslib.as_array(output_buffer[:frames_written * self._channels]).copy()
        processed = processed.reshape(-1, self._channels)[:, 0]  # mono

        in_lat, out_lat, grid_comp = self.get_latency()

        metadata = {
            "input_latency_frames": in_lat,
            "output_latency_frames": out_lat,
            "grid_compensation_frames": grid_comp,
            "tempo_ratio": ratio,
            "input_frames": input_frames,
            "output_frames": frames_written,
            "source_bpm": self._source_bpm,
            "master_bpm": self._master_bpm,
            "sync_mode": self._sync_mode,
            "key_lock_active": self.is_key_lock_active(),
            "input_frequency_hz": self._frequency_hz,
        }

        return processed, metadata
    
    def get_latency(self) -> Tuple[int, int, int]:
        """Get latency values from the native KeyLockVoice.
        
        Returns:
            Tuple of (input_latency_frames, output_latency_frames, grid_compensation_frames)
        """
        if not _lib:
            raise RuntimeError("Native library not loaded")
        
        config = SbTestKeylockConfig(
            sample_rate=self._sample_rate,
            channels=self._channels,
            sync_mode=self._sync_mode,
            source_bpm=self._source_bpm,
            master_bpm=self._master_bpm,
            frequency_hz=self._frequency_hz,
            amplitude=self._amplitude,
        )
        
        in_lat = ctypes.c_int()
        out_lat = ctypes.c_int()
        grid_comp = ctypes.c_int()
        
        result = _lib.sb_test_keylock_get_latency(
            ctypes.byref(config),
            ctypes.byref(in_lat),
            ctypes.byref(out_lat),
            ctypes.byref(grid_comp)
        )
        
        if result != SB_OK:
            return (0, 0, 0)
        
        return (in_lat.value, out_lat.value, grid_comp.value)
    
    def is_key_lock_active(self) -> bool:
        """Check if key-lock mode is active (Signalsmith initialized)."""
        return self._sync_mode == SB_SYNC_MODE_KEY_LOCK_SYNC
    
    @property
    def tempo_ratio(self) -> float:
        """Get the tempo ratio (master_bpm / source_bpm)."""
        return self._tempo_ratio


def create_keylock_voice(sample_rate: int = 48000, source_bpm: float = 128.0,
                         master_bpm: float = 132.0, sync_mode: int = SB_SYNC_MODE_KEY_LOCK_SYNC,
                         frequency_hz: float = 800.0, amplitude: float = 0.8,
                         channels: int = 1) -> Optional[KeyLockVoice]:
    """Create a KeyLockVoice instance for offline processing.
    
    Returns None if native library is not available.
    """
    if not is_available():
        return None
    return KeyLockVoice(sample_rate, source_bpm, master_bpm, sync_mode,
                       frequency_hz, amplitude, channels)


def process_with_keylock(input_signal: np.ndarray, sample_rate: int,
                         source_bpm: float, master_bpm: float,
                         sync_mode: int = SB_SYNC_MODE_KEY_LOCK_SYNC,
                         frequency_hz: float = 440.0, amplitude: float = 0.8) -> Tuple[np.ndarray, dict]:
    """Process audio through native KeyLockVoice offline.
    
    This function generates synthetic clicks at the source BPM interval, processes
    them through the native KeyLockVoice (with Signalsmith for Key-Lock mode or
    simple rate change for Rate-Sync mode), and returns the processed audio.
    
    Args:
        input_signal: Source audio signal (used for determining duration/frequency)
        sample_rate: Audio sample rate
        source_bpm: Source tempo in BPM
        master_bpm: Master tempo in BPM
        sync_mode: SB_SYNC_MODE_RATE_SYNC or SB_SYNC_MODE_KEY_LOCK_SYNC
        frequency_hz: Click frequency for synthetic source
        amplitude: Click amplitude
        
    Returns:
        Tuple of (processed_signal as float32 numpy array, metadata dict with
                  latency values and processing info)
    """
    if not is_available():
        raise RuntimeError("Native audio not available")
    
    kv = create_keylock_voice(
        sample_rate=sample_rate,
        source_bpm=source_bpm,
        master_bpm=master_bpm,
        channels=1,
        sync_mode=sync_mode,
        frequency_hz=frequency_hz,
        amplitude=amplitude
    )
    
    if kv is None:
        raise RuntimeError("Failed to create KeyLockVoice")
    
    # Get latency info
    in_lat, out_lat, grid_comp = kv.get_latency()
    
    # Determine output frame count based on tempo ratio
    ratio = master_bpm / source_bpm
    input_frames = len(input_signal)
    output_frames = int(input_frames / ratio)  # Time-stretched output
    
    # Process through native KeyLockVoice
    processed_data, frames_processed = kv.process(output_frames)
    
    # Convert to numpy array
    processed_signal = np.frombuffer(processed_data, dtype=np.float32)
    
    metadata = {
        "input_latency_frames": in_lat,
        "output_latency_frames": out_lat,
        "grid_compensation_frames": grid_comp,
        "tempo_ratio": ratio,
        "input_frames": input_frames,
        "output_frames": frames_processed,
        "source_bpm": source_bpm,
        "master_bpm": master_bpm,
        "sync_mode": sync_mode,
        "key_lock_active": kv.is_key_lock_active(),
        "input_frequency_hz": frequency_hz,
    }
    
    return processed_signal, metadata


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