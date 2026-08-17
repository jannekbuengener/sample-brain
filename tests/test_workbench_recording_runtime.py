#!/usr/bin/env python
"""Runtime tests for workbench recording (Issue #325).

Mock tests run everywhere (no native DLL needed).
Hardware tests are skipped when native audio engine is unavailable.
"""

from __future__ import annotations

import os
import tempfile
import time
import uuid
from pathlib import Path

import pytest

from src.workbench_transport_adapter import WorkbenchTransportAdapter
from src.workbench_controller import start_native_recording, stop_native_recording
from src.recording_take import finalize_native_recording
from src.native_audio import is_available, SB_DEVICE_OK
from src.workbench_recording_ui import WorkbenchRecordingUiController, RecordingState, attach_workbench_recording_ui


# ----------------------------------------------------------------------
# Fake engine used by pure-mock tests
# ----------------------------------------------------------------------
class FakeEngine:
    """Minimal fake engine returning controllable frames and snapshots."""
    def __init__(self, frames_to_return=100):
        self._opened = False
        self._started = False
        self._frames = 0
        self._frames_to_return = frames_to_return
        self.engine_frame = 0
        self.session_frame = 0

    def open(self, config):
        self._opened = True

    def start(self):
        self._started = True

    def is_available(self):
        return True

    def snapshot(self):
        class Snap:
            device_status = SB_DEVICE_OK
            recording_dropped_frames = 0
            engine_frame = 0
            sample_rate = 48000
        s = Snap()
        s.engine_frame = self.engine_frame
        return s

    def start_recording(self, engine_frame):
        self.engine_frame = engine_frame
        self._frames = 0
        return 1  # recording_id

    def stop_recording(self, recording_id):
        # simulate captured frames - stereo float32 = 2 channels * 4 bytes = 8 bytes per frame
        self._frames = self._frames_to_return
        self.engine_frame += self._frames_to_return
        # stereo float32: 2 channels * 4 bytes * frames
        return b"\x00" * (self._frames_to_return * 8), self._frames_to_return

    def close(self):
        pass


class FakeTransportAdapter:
    """Adapter wrapper around FakeEngine with snapshot support."""
    def __init__(self, fake_engine: FakeEngine):
        self._engine = fake_engine
        self._lock = None
        self._native_started = False

    def ensure_engine_running(self) -> bool:
        if not self._native_started:
            self._engine.start()
            self._native_started = True
        return True

    def get_snapshot(self):
        return {
            "engine_frame": self._engine.engine_frame,
            "session_frame": self._engine.session_frame,
        }

    def get_native_engine(self):
        return self._engine


# ----------------------------------------------------------------------
# Pure-mock tests (run on every CI, no native DLL required)
# ----------------------------------------------------------------------
def test_ensure_engine_running_idempotent():
    """ensure_engine_running() can be called twice without error."""
    fe = FakeEngine()
    fta = FakeTransportAdapter(fe)
    assert fta.ensure_engine_running() is True
    assert fta.ensure_engine_running() is True  # second call succeeds


def test_record_with_stopped_transport_creates_frames(tmp_path):
    """Record while transport stopped still yields frames via fake engine."""
    fe = FakeEngine(frames_to_return=50)
    fta = FakeTransportAdapter(fe)

    # ensure engine running (no musical transport)
    assert fta.ensure_engine_running()
    # transport not playing – session frame stays constant
    start_snap = fta.get_snapshot()
    start_engine = start_snap["engine_frame"]
    start_session = start_snap["session_frame"]

    rec_id = start_native_recording(fe, start_engine, start_session)
    assert rec_id == 1

    # advance fake time
    time.sleep(0.01)

    end_snap = fta.get_snapshot()
    take = stop_native_recording(
        fe,
        rec_id,
        start_engine,
        start_session,
        destination=str(tmp_path / "test_take.wav"),
        end_engine_frame=end_snap["engine_frame"],
        end_session_frame=end_snap["session_frame"],
    )
    assert take is not None
    assert take.captured_frames == 50
    assert Path(take.path).exists()


def test_exact_start_end_frames_from_snapshot(tmp_path):
    """Start/end frames come from snapshots, not computed."""
    fe = FakeEngine(frames_to_return=10)
    fta = FakeTransportAdapter(fe)

    fta.ensure_engine_running()
    start_snap = fta.get_snapshot()
    rec_id = start_native_recording(fe, start_snap["engine_frame"], start_snap["session_frame"])
    end_snap = fta.get_snapshot()
    take = stop_native_recording(
        fe,
        rec_id,
        start_snap["engine_frame"],
        start_snap["session_frame"],
        destination=str(tmp_path / "exact.wav"),
        end_engine_frame=end_snap["engine_frame"],
        end_session_frame=end_snap["session_frame"],
    )
    assert take.captured_frames == 10
    assert take.context.record_end_engine_frame_exclusive == end_snap["engine_frame"]
    assert take.context.record_end_session_frame_exclusive == end_snap["session_frame"]


def test_stopped_session_stays_frozen(tmp_path):
    """When transport stopped, session frame does not advance."""
    fe = FakeEngine(frames_to_return=20)
    fta = FakeTransportAdapter(fe)
    # transport NOT playing – session_frame stays 0
    fta.ensure_engine_running()
    start_snap = fta.get_snapshot()
    assert start_snap["session_frame"] == 0
    rec_id = start_native_recording(fe, start_snap["engine_frame"], start_snap["session_frame"])
    end_snap = fta.get_snapshot()
    take = stop_native_recording(
        fe,
        rec_id,
        start_snap["engine_frame"],
        start_snap["session_frame"],
        destination=str(tmp_path / "frozen.wav"),
        end_engine_frame=end_snap["engine_frame"],
        end_session_frame=end_snap["session_frame"],
    )
    assert take.context.record_end_session_frame_exclusive == 0


def test_two_rapid_takes_different_files(tmp_path):
    """Two rapid takes produce distinct WAV files generated by UI naming."""
    fe = FakeEngine(frames_to_return=5)
    fta = FakeTransportAdapter(fe)
    fta.ensure_engine_running()

    # First take
    snap1 = fta.get_snapshot()
    rec1 = start_native_recording(fe, snap1["engine_frame"], snap1["session_frame"])
    end1 = fta.get_snapshot()
    take1 = stop_native_recording(
        fe, rec1, snap1["engine_frame"], snap1["session_frame"],
        destination=str(tmp_path / "ignored1.wav"),
        end_engine_frame=end1["engine_frame"],
        end_session_frame=end1["session_frame"],
    )

    # Second take – different file name automatically (UI would add uuid)
    snap2 = fta.get_snapshot()
    rec2 = start_native_recording(fe, snap2["engine_frame"], snap2["session_frame"])
    end2 = fta.get_snapshot()
    take2 = stop_native_recording(
        fe, rec2, snap2["engine_frame"], snap2["session_frame"],
        destination=str(tmp_path / "ignored2.wav"),
        end_engine_frame=end2["engine_frame"],
        end_session_frame=end2["session_frame"],
    )
    assert take1.path != take2.path
    assert Path(take1.path).exists()
    assert Path(take2.path).exists()


def test_zero_frames_no_take(tmp_path):
    """If engine returns 0 frames, finalize_native_recording returns None."""
    fe = FakeEngine(frames_to_return=0)
    fta = FakeTransportAdapter(fe)
    fta.ensure_engine_running()
    start_snap = fta.get_snapshot()
    rec_id = start_native_recording(fe, start_snap["engine_frame"], start_snap["session_frame"])
    end_snap = fta.get_snapshot()
    take = stop_native_recording(
        fe, rec_id, start_snap["engine_frame"], start_snap["session_frame"],
        destination=str(tmp_path / "zero.wav"),
        end_engine_frame=end_snap["engine_frame"],
        end_session_frame=end_snap["session_frame"],
    )
    assert take is None


def test_engine_already_running_record_works(tmp_path):
    """If engine already started (playback), record still works."""
    fe = FakeEngine(frames_to_return=7)
    fta = FakeTransportAdapter(fe)
    # simulate engine already started
    fe.start()
    # ensure_engine_running should be idempotent
    assert fta.ensure_engine_running()
    start_snap = fta.get_snapshot()
    rec_id = start_native_recording(fe, start_snap["engine_frame"], start_snap["session_frame"])
    end_snap = fta.get_snapshot()
    take = stop_native_recording(
        fe, rec_id, start_snap["engine_frame"], start_snap["session_frame"],
        destination=str(tmp_path / "running.wav"),
        end_engine_frame=end_snap["engine_frame"],
        end_session_frame=end_snap["session_frame"],
    )
    assert take is not None
    assert take.captured_frames == 7


# ----------------------------------------------------------------------
# Hardware tests (run only when native DLL present)
# ----------------------------------------------------------------------
@pytest.mark.skipif(not is_available(), reason="Native audio DLL not present")
def test_hw_ensure_engine_running():
    adapter = WorkbenchTransportAdapter(initial_bpm=120.0)
    assert adapter.ensure_engine_running()
    # second call should not fail
    assert adapter.ensure_engine_running()
    adapter._native_engine.close()


@pytest.mark.skipif(not is_available(), reason="Native audio DLL not present")
def test_hw_record_stop_cycle(tmp_path):
    adapter = WorkbenchTransportAdapter(initial_bpm=120.0)
    adapter.ensure_engine_running()
    start = adapter.get_snapshot()
    engine = adapter.get_native_engine()
    rec_id = start_native_recording(engine, start["engine_frame"], start["session_frame"])
    time.sleep(0.05)
    end = adapter.get_snapshot()
    take = stop_native_recording(
        engine, rec_id, start["engine_frame"], start["session_frame"],
        destination=str(tmp_path / "hw_take.wav"),
        end_engine_frame=end["engine_frame"],
        end_session_frame=end["session_frame"],
    )
    assert take is not None
    assert take.captured_frames > 0
    adapter._native_engine.close()


# ----------------------------------------------------------------------
if __name__ == "__main__":
    pytest.main([__file__, "-v"])