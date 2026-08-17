"""Finalize captured PCM outside the realtime callback and register the take.

This module deliberately starts *after* the native callback/ringbuffer boundary.
It receives already-captured float32 PCM, writes/finalizes a WAV, persists exact
engine/session frame context in a portable sidecar, then reuses the existing
Workbench library/playlist layer.  It never performs file or SQLite I/O from an
audio callback.
"""

from __future__ import annotations

import json
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
RECORDING_METADATA_DOCUMENT_TYPE = "sample_brain.recording_take"
RECORDING_METADATA_SCHEMA_VERSION = "1.0.0"
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
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in values
        ):
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
    metadata_path: Path
    captured_frames: int
    context: RecordingFrameContext
    playlist_name: str = RECORDINGS_PLAYLIST_NAME
    playlist_assignment: Literal["added", "duplicate"] = "added"


def recording_metadata_path(audio_path: Path | str) -> Path:
    path = Path(audio_path)
    return path.with_suffix(".recording.json")


def _pcm_array(pcm_f32: bytes, *, captured_frames: int, channels: int) -> np.ndarray:
    if not isinstance(pcm_f32, (bytes, bytearray, memoryview)):
        raise RecordingFinalizeError("captured PCM must be bytes-like float32 data")
    if (
        not isinstance(captured_frames, int)
        or isinstance(captured_frames, bool)
        or captured_frames < 0
    ):
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
        raise RecordingFinalizeError(
            "recording destination already exists; original take will not be overwritten"
        )

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


def _metadata_payload(
    *,
    audio_path: Path,
    captured_frames: int,
    context: RecordingFrameContext,
    status: RecordingTakeStatus,
) -> dict[str, object]:
    return {
        "document_type": RECORDING_METADATA_DOCUMENT_TYPE,
        "schema_version": RECORDING_METADATA_SCHEMA_VERSION,
        "status": status,
        "audio_ref": audio_path.name,
        "captured_frames": captured_frames,
        "sample_rate": context.sample_rate,
        "channels": context.channels,
        "record_start_engine_frame": context.record_start_engine_frame,
        "record_start_session_frame": context.record_start_session_frame,
        "record_end_engine_frame_exclusive": context.record_end_engine_frame_exclusive,
        "record_end_session_frame_exclusive": context.record_end_session_frame_exclusive,
    }


def _write_atomic_metadata(path: Path, payload: dict[str, object]) -> None:
    if path.exists():
        raise RecordingFinalizeError(
            "recording metadata already exists; original take metadata will not be overwritten"
        )
    temp_path = path.with_name(f".{path.name}.part")
    try:
        temp_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temp_path, path)
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _register_recording(
    path: Path,
    *,
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
    """Finalize a valid take, persist timing evidence, then register it.

    File + portable sidecar are finalized before library/playlist mutation. If
    later DB registration fails, the already-valid original recording and its
    frame evidence are intentionally left on disk rather than deleted.
    """
    path = Path(destination).expanduser().resolve()
    metadata_path = recording_metadata_path(path)
    if metadata_path.exists():
        raise RecordingFinalizeError(
            "recording metadata already exists; refusing to overwrite take evidence"
        )

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
    payload = _metadata_payload(
        audio_path=path,
        captured_frames=captured_frames,
        context=context,
        status=take_status,
    )
    try:
        _write_atomic_metadata(metadata_path, payload)
    except Exception as exc:
        raise RecordingFinalizeError(
            f"recording WAV is valid but timing metadata finalization failed: {exc}"
        ) from exc

    try:
        assignment = _register_recording(
            path,
            take_status=take_status,
            db_path=db_path,
        )
    except Exception as exc:
        raise RecordingFinalizeError(
            f"recording WAV and metadata are valid but Workbench registration failed: {exc}"
        ) from exc

    return FinalizedRecordingTake(
        status=take_status,
        path=path,
        metadata_path=metadata_path,
        captured_frames=captured_frames,
        context=context,
        playlist_assignment=assignment,
    )


__all__ = [
    "FinalizedRecordingTake",
    "RECORDINGS_PLAYLIST_NAME",
    "RECORDING_METADATA_DOCUMENT_TYPE",
    "RECORDING_METADATA_SCHEMA_VERSION",
    "RecordingFinalizeError",
    "RecordingFrameContext",
    "finalize_recording_take",
    "recording_metadata_path",
]
