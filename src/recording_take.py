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


def finalize_native_recording(
    engine: NativeAudioEngine,
    recording_id: int,
    record_start_engine_frame: int,
    record_start_session_frame: int,
    destination: Path | str,
    db_path: Path | None = None,
) -> Optional[FinalizedRecordingTake]:
    """Finalize a native recording with proper device-lost handling.

    Workflow (corrections #1-#4 from Issue #325):
    1. Capture snapshot BEFORE stop_recording to get device_status and
       recording_dropped_frames (after stop, the recording instance is removed
       from the native core and snapshot values may reset).
    2. Call stop_recording -- truth is simply frames > 0 or frames == 0
       (no has_data()/reset_ringbuffer Python logic needed).
    3. If frames > 0: rescue the take, finalize as ``interrupted`` when
       device was lost/failed, otherwise ``complete``.
       ``finalize_recording_take`` already registers the take in the
       ``Recordings`` playlist (correction #4 -- no double ``add_sample_to_playlist``).
    4. If frames == 0: no take is created.

    The native Ringbuffer discards excess frames on overflow and counts them
    in ``recording_dropped_frames`` (correction #1 -- not "drop-oldest").

    Args:
        engine: Active native audio engine instance.
        recording_id: Recording ID returned by ``engine.start_recording()``.
        record_start_engine_frame: Engine frame when recording started.
        record_start_session_frame: Session frame when recording started.
        destination: Path (or "workbench://...") where the .wav should be written.
        db_path: Optional path to the workbench library SQLite DB.

    Returns:
        ``FinalizedRecordingTake`` when a take was rescued, or ``None`` when
        no frames were captured (frames == 0).
    """
    # 1. Capture snapshot BEFORE stop_recording (correction #3).
    #    After stop, the recording instance is removed from the native core,
    #    and snapshot().recording_dropped_frames may already be 0 / stale.
    snap: Snapshot = engine.snapshot()
    device_status = snap.device_status
    dropped_frames = snap.recording_dropped_frames
    end_engine_frame = snap.engine_frame

    # 2. Stop recording (correction #2: truth is frames > 0 or == 0).
    pcm_data, frames = engine.stop_recording(recording_id)

    # 3. If frames > 0, we can rescue the take (correction #1).
    if frames > 0:
        # Build context with exact frame positions.
        # Session frame end: increment by captured frame count (mirrors existing test convention).
        end_session_frame = record_start_session_frame + frames

        context = RecordingFrameContext(
            record_start_engine_frame=record_start_engine_frame,
            record_start_session_frame=record_start_session_frame,
            record_end_engine_frame_exclusive=end_engine_frame,
            record_end_session_frame_exclusive=end_session_frame,
            sample_rate=snap.sample_rate,
            channels=2,  # stereo native default; adjust if config differs
        )

        # Finalize the take. finalize_recording_take already registers in
        # "Recordings" playlist (correction #4).
        # Treat dropped frames > 0 as interrupted (correction #1: ringbuffer counts drops)
        interrupted = (device_status not in (SB_DEVICE_OK,)) or (dropped_frames > 0)
        take = finalize_recording_take(
            pcm_data,
            captured_frames=frames,
            context=context,
            destination=destination,
            interrupted=interrupted,
            db_path=db_path,
        )
        return take

    # 4. frames == 0 â†’ no take created.
    return None


__all__ = [
    "FinalizedRecordingTake",
    "RECORDINGS_PLAYLIST_NAME",
    "RECORDING_METADATA_DOCUMENT_TYPE",
    "RECORDING_METADATA_SCHEMA_VERSION",
    "RecordingFinalizeError",
    "RecordingFrameContext",
    "finalize_recording_take",
    "finalize_native_recording",
    "recording_metadata_path",
]
