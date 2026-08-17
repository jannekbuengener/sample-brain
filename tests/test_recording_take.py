from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from src.recording_take import (
    RECORDINGS_PLAYLIST_NAME,
    RecordingFinalizeError,
    RecordingFrameContext,
    finalize_recording_take,
)
from src.workbench_library import (
    get_playlist_by_name,
    list_playlist_sample_paths,
    list_playlists,
    load_sample_by_path,
)


def _context(*, channels: int = 1, frames: int = 256) -> RecordingFrameContext:
    return RecordingFrameContext(
        record_start_engine_frame=10_000,
        record_start_session_frame=20_000,
        record_end_engine_frame_exclusive=10_000 + frames,
        record_end_session_frame_exclusive=20_000 + frames,
        sample_rate=48_000,
        channels=channels,
    )


def _pcm(*, frames: int = 256, channels: int = 1) -> bytes:
    t = np.arange(frames, dtype=np.float32) / np.float32(48_000)
    mono = (0.25 * np.sin(2 * np.pi * 440.0 * t)).astype("<f4")
    if channels == 1:
        return mono.tobytes()
    stereo = np.column_stack((mono, mono * np.float32(0.5))).astype("<f4")
    return stereo.tobytes()


def test_complete_take_writes_float_wav_metadata_and_recordings_playlist(tmp_path):
    db_path = tmp_path / "workbench.sqlite"
    destination = tmp_path / "recordings" / "take_001.wav"
    context = _context()

    result = finalize_recording_take(
        _pcm(),
        captured_frames=256,
        context=context,
        destination=destination,
        db_path=db_path,
    )

    assert result.status == "complete"
    assert result.path == destination.resolve()
    assert result.metadata_path.exists()
    assert result.playlist_name == RECORDINGS_PLAYLIST_NAME
    assert result.playlist_assignment == "added"

    info = sf.info(destination)
    assert info.frames == 256
    assert info.samplerate == 48_000
    assert info.channels == 1
    assert info.subtype == "FLOAT"

    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert metadata == {
        "audio_ref": "take_001.wav",
        "captured_frames": 256,
        "channels": 1,
        "document_type": "sample_brain.recording_take",
        "record_end_engine_frame_exclusive": 10_256,
        "record_end_session_frame_exclusive": 20_256,
        "record_start_engine_frame": 10_000,
        "record_start_session_frame": 20_000,
        "sample_rate": 48_000,
        "schema_version": "1.0.0",
        "status": "complete",
    }
    assert str(tmp_path) not in result.metadata_path.read_text(encoding="utf-8")

    playlist = get_playlist_by_name(RECORDINGS_PLAYLIST_NAME, db_path=db_path)
    assert playlist is not None
    assert list_playlist_sample_paths(playlist.id, db_path=db_path) == [
        str(destination.resolve())
    ]

    cached = load_sample_by_path(destination, db_path=db_path)
    assert cached is not None
    assert cached.status == "pending"
    assert cached.analyzer_version == "recording_pending_analysis_v1"


def test_second_take_reuses_single_recordings_playlist(tmp_path):
    db_path = tmp_path / "workbench.sqlite"
    first = tmp_path / "recordings" / "take_001.wav"
    second = tmp_path / "recordings" / "take_002.wav"

    finalize_recording_take(
        _pcm(),
        captured_frames=256,
        context=_context(),
        destination=first,
        db_path=db_path,
    )
    finalize_recording_take(
        _pcm(),
        captured_frames=256,
        context=_context(),
        destination=second,
        db_path=db_path,
    )

    playlists = list_playlists(db_path=db_path)
    assert [playlist.name for playlist in playlists] == [RECORDINGS_PLAYLIST_NAME]
    assert list_playlist_sample_paths(playlists[0].id, db_path=db_path) == [
        str(first.resolve()),
        str(second.resolve()),
    ]


def test_interrupted_take_is_kept_when_valid_and_marked_truthfully(tmp_path):
    db_path = tmp_path / "workbench.sqlite"
    destination = tmp_path / "recordings" / "interrupted.wav"

    result = finalize_recording_take(
        _pcm(frames=128),
        captured_frames=128,
        context=_context(frames=128),
        destination=destination,
        interrupted=True,
        db_path=db_path,
    )

    assert result.status == "interrupted"
    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert metadata["status"] == "interrupted"
    assert sf.info(destination).frames == 128
    playlist = get_playlist_by_name(RECORDINGS_PLAYLIST_NAME, db_path=db_path)
    assert playlist is not None
    assert str(destination.resolve()) in list_playlist_sample_paths(
        playlist.id, db_path=db_path
    )


def test_stereo_float32_capture_preserves_channels_and_frame_count(tmp_path):
    destination = tmp_path / "recordings" / "stereo.wav"

    finalize_recording_take(
        _pcm(frames=96, channels=2),
        captured_frames=96,
        context=_context(frames=96, channels=2),
        destination=destination,
        db_path=tmp_path / "workbench.sqlite",
    )

    info = sf.info(destination)
    assert info.frames == 96
    assert info.channels == 2
    assert info.samplerate == 48_000
    data, sample_rate = sf.read(destination, dtype="float32", always_2d=True)
    assert sample_rate == 48_000
    assert data.shape == (96, 2)


def test_bad_pcm_length_fails_before_file_or_playlist_mutation(tmp_path):
    destination = tmp_path / "recordings" / "bad.wav"
    db_path = tmp_path / "workbench.sqlite"

    with pytest.raises(RecordingFinalizeError, match="byte length mismatch"):
        finalize_recording_take(
            b"\x00" * 12,
            captured_frames=256,
            context=_context(),
            destination=destination,
            db_path=db_path,
        )

    assert not destination.exists()
    assert not destination.with_suffix(".recording.json").exists()
    assert get_playlist_by_name(RECORDINGS_PLAYLIST_NAME, db_path=db_path) is None


def test_non_finite_pcm_is_rejected(tmp_path):
    values = np.zeros(32, dtype="<f4")
    values[5] = np.nan

    with pytest.raises(RecordingFinalizeError, match="non-finite"):
        finalize_recording_take(
            values.tobytes(),
            captured_frames=32,
            context=_context(frames=32),
            destination=tmp_path / "recordings" / "nan.wav",
            db_path=tmp_path / "workbench.sqlite",
        )


def test_existing_take_is_never_overwritten(tmp_path):
    destination = tmp_path / "recordings" / "take.wav"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"ORIGINAL")

    with pytest.raises(RecordingFinalizeError, match="already exists"):
        finalize_recording_take(
            _pcm(),
            captured_frames=256,
            context=_context(),
            destination=destination,
            db_path=tmp_path / "workbench.sqlite",
        )

    assert destination.read_bytes() == b"ORIGINAL"


def test_existing_metadata_is_never_overwritten(tmp_path):
    destination = tmp_path / "recordings" / "take.wav"
    metadata = destination.with_suffix(".recording.json")
    metadata.parent.mkdir(parents=True)
    metadata.write_text("ORIGINAL-METADATA", encoding="utf-8")

    with pytest.raises(RecordingFinalizeError, match="metadata already exists"):
        finalize_recording_take(
            _pcm(),
            captured_frames=256,
            context=_context(),
            destination=destination,
            db_path=tmp_path / "workbench.sqlite",
        )

    assert not destination.exists()
    assert metadata.read_text(encoding="utf-8") == "ORIGINAL-METADATA"


def test_frame_context_rejects_invalid_boundaries():
    with pytest.raises(ValueError, match="precedes start"):
        RecordingFrameContext(
            record_start_engine_frame=100,
            record_start_session_frame=200,
            record_end_engine_frame_exclusive=99,
            record_end_session_frame_exclusive=201,
            sample_rate=48_000,
            channels=1,
        )
