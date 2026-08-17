"""Finalize captured PCM outside the realtime callback and register the take.

This module deliberately starts *after* the native callback/ringbuffer boundary.
It receives already-captured float32 PCM, writes/finalizes a WAV, then reuses the
existing Workbench library/playlist layer.  It never performs file or SQLite I/O
from an audio callback.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import soundfile as sf

from .workbench_controller import WorkbenchRow
from .workbench_library import (
    add_sample_to_playlist,
    get_or_create_playlist,
    normalize_display_name,
    upsert_folder,
    upsert_sample,
)

RECORDINGS_PLAYLIST_NAME = "Recordings"
RecordingTakeStatus = Literal["complete", "interrupted"]


class RecordingFinalizeError(RuntimeError):
    """Raised when a captured take cannot be safely finalized."""


@dataclass(frozen=True)
class RecordingFrameContext:
    record_start_engine_frame: int
    record_start_session_frame: int
    record_end_engine_frame_exclusive: int
    record_end_session_frame_exclusive: int
    sample_rate: int
    channels: int

    def __post_init__(self) -> None:
        values = (
            self.record_start_engine_frame,
            self.record_start_session_frame,
            self.record_end_engine_frame_exclusive,
            self.record_end_session_frame_exclusive,
        )
        if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in values):
            raise ValueError("recording frame positions must be non-negative integers")
        if self.record_end_engine_frame_exclusive < self.record_start_engine_frame:
            raise ValueError("record_end_engine_frame_exclusive precedes start")
        if self.record_end_session_frame_exclusive < self.record_start_session_frame:
            raise ValueError("record_end_session_frame_exclusive precedes start")
        if not isinstance(self.sample_rate, int) or self.sample_rate <= 0:
            raise ValueError("sample_rate must be a positive integer")
        if not isinstance(self.channels, int) or self.channels <= 0:
            raise ValueError("channels must be a positive integer")


@dataclass(frozen=True)
class FinalizedRecordingTake:
    status: RecordingTakeStatus
    path: Path
    captured_frames: int
    context: RecordingFrameContext
    playlist_name: str = RECORDINGS_PLAYLIST_NAME
    playlist_assignment: Literal["added", "duplicate"] = "added"


def _pcm_array(pcm_f32: bytes, *, captured_frames: int, channels: int) -> np.ndarray:
    if not isinstance(pcm_f32, (bytes, bytearray, memoryview)):
        raise RecordingFinalizeError("captured PCM must be bytes-like float32 data")
    if not isinstance(captured_frames, int) or isinstance(captured_frames, bool) or captured_frames < 0:
        raise RecordingFinalizeError("captured_frames must be a non-negative integer")

    expected_samples = captured_frames * channels
    expected_bytes = expected_samples * np.dtype("<f4").itemsize
    payload = bytes(pcm_f32)
    if len(payload) != expected_bytes:
        raise RecordingFinalizeError(
            f"captured PCM byte length mismatch: expected {expected_bytes}, got {len(payload)}"
        )

    samples = np.frombuffer(payload, dtype="<f4")
    if samples.size != expected_samples:
        raise RecordingFinalizeError("captured PCM sample count mismatch")
    if not np.isfinite(samples).all():
        raise RecordingFinalizeError("captured PCM contains non-finite values")

    if channels == 1:
        return samples
    return samples.reshape(captured_frames, channels)


def _write_atomic_float_wav(
    destination: Path,
    samples: np.ndarray,
    *,
    sample_rate: int,
    channels: int,
    captured_frames: int,
) -> None:
    if destination.suffix.lower() != ".wav":
        raise RecordingFinalizeError("recording destination must use .wav")
    if destination.exists():
        raise RecordingFinalizeError("recording destination already exists; original take will not be overwritten")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.with_name(f".{destination.stem}.part.wav")
    if temp_path.exists():
        temp_path.unlink()

    try:
        sf.write(temp_path, samples, sample_rate, format="WAV", subtype="FLOAT")
        info = sf.info(temp_path)
        if info.frames != captured_frames:
            raise RecordingFinalizeError(
                f"finalized WAV frame mismatch: expected {captured_frames}, got {info.frames}"
            )
        if info.samplerate != sample_rate:
            raise RecordingFinalizeError("finalized WAV sample-rate mismatch")
        if info.channels != channels:
            raise RecordingFinalizeError("finalized WAV channel-count mismatch")
        os.replace(temp_path, destination)
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _register_recording(
    path: Path,
    *,
    context: RecordingFrameContext,
    take_status: RecordingTakeStatus,
    db_path: Path | None,
) -> Literal["added", "duplicate"]:
    stat = path.stat()
    folder_id = upsert_folder(path.parent, db_path=db_path)
    row = WorkbenchRow(
        display_name=normalize_display_name(path.name),
        relative_path=path.name,
        path=str(path),
        bpm=None,
        key=None,
        key_conf=None,
        loudness=None,
        brightness=None,
        sample_class=None,
        pred_type=None,
        status="pending",
        details={
            "recording_status": take_status,
            "record_start_engine_frame": context.record_start_engine_frame,
            "record_start_session_frame": context.record_start_session_frame,
            "record_end_engine_frame_exclusive": context.record_end_engine_frame_exclusive,
            "record_end_session_frame_exclusive": context.record_end_session_frame_exclusive,
            "samplerate": context.sample_rate,
            "channels": context.channels,
            "tags": ["recording"],
        },
    )
    upsert_sample(
        folder_id,
        row,
        size_bytes=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        db_path=db_path,
        analyzer_version="recording_pending_analysis_v1",
    )
    playlist = get_or_create_playlist(RECORDINGS_PLAYLIST_NAME, db_path=db_path)
    return add_sample_to_playlist(playlist.id, path, db_path=db_path)


def finalize_recording_take(
    pcm_f32: bytes,
    *,
    captured_frames: int,
    context: RecordingFrameContext,
    destination: Path | str,
    interrupted: bool = False,
    db_path: Path | None = None,
) -> FinalizedRecordingTake:
    """Write a valid take then register it in the existing ``Recordings`` playlist.

    The file is finalized before any library/playlist mutation.  If later DB
    registration fails, the already-valid original recording is intentionally
    left on disk rather than deleted.
    """
    path = Path(destination).expanduser().resolve()
    samples = _pcm_array(
        pcm_f32,
        captured_frames=captured_frames,
        channels=context.channels,
    )
    _write_atomic_float_wav(
        path,
        samples,
        sample_rate=context.sample_rate,
        channels=context.channels,
        captured_frames=captured_frames,
    )

    take_status: RecordingTakeStatus = "interrupted" if interrupted else "complete"
    try:
        assignment = _register_recording(
            path,
            context=context,
            take_status=take_status,
            db_path=db_path,
        )
    except Exception as exc:
        raise RecordingFinalizeError(
            f"recording WAV is valid but Workbench registration failed: {exc}"
        ) from exc

    return FinalizedRecordingTake(
        status=take_status,
        path=path,
        captured_frames=captured_frames,
        context=context,
        playlist_assignment=assignment,
    )


__all__ = [
    "FinalizedRecordingTake",
    "RECORDINGS_PLAYLIST_NAME",
    "RecordingFinalizeError",
    "RecordingFrameContext",
    "finalize_recording_take",
]
