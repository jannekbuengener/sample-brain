"""#1209: stop→restart must rebase transport engine_frame onto native clock.

Regression for intermittent packaged Browser silence: after audition stop the
native engine restarts at frame 0 while SessionTransport kept the pre-stop
engine_frame. play_row then scheduled voices in the native future → SCHEDULED
forever / silence while PreviewResult.ok stayed True.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

import src.workbench_transport_adapter as adapter_module
from src.workbench_controller import WorkbenchRow
from src.workbench_preview import WorkbenchPreviewPlayer
from src.workbench_transport_preview import TransportAwarePreview


class RestartClockEngine:
    """Native stand-in: start() resets engine_frame to 0 (miniaudio contract)."""

    def __init__(self) -> None:
        self.open_calls: list[object] = []
        self.started = False
        self._frame = 0
        self.start_count = 0
        self.schedule_calls: list[tuple[int, int]] = []
        self.voices: dict[int, int] = {}

    def open(self, config) -> None:
        self.open_calls.append(config)

    def start(self) -> None:
        self.start_count += 1
        self._frame = 0
        self.started = True

    def stop(self) -> None:
        self.started = False

    def close(self) -> None:
        return None

    def snapshot(self):
        return SimpleNamespace(
            engine_frame=self._frame,
            running=self.started,
            device_status=0,
            recovery_state=0,
            voice_states=[2 if self.voices else 0] + [0] * 31,
        )

    def create_voice(self, config) -> int:
        vid = int(config.id)
        self.voices[vid] = 1
        return vid

    def schedule_voice_start(self, voice_id: int, engine_frame: int) -> None:
        self.schedule_calls.append((int(voice_id), int(engine_frame)))
        self._frame = max(self._frame, 0)

    def remove_voice(self, voice_id: int) -> None:
        self.voices.pop(int(voice_id), None)

    def stop_voice(self, voice_id: int) -> None:
        self.voices.pop(int(voice_id), None)

    def set_voice_rate(self, voice_id: int, rate: float) -> None:
        return None

    def advance(self, frames: int) -> None:
        if self.started:
            self._frame += int(frames)


def test_ensure_engine_running_after_stop_rebases_engine_frame(monkeypatch):
    engine = RestartClockEngine()
    monkeypatch.setattr(adapter_module._native_audio, "is_available", lambda: True)
    monkeypatch.setattr(
        adapter_module._native_audio,
        "NativeAudioEngine",
        lambda: engine,
    )
    adapter = adapter_module.WorkbenchTransportAdapter(sample_rate=48_000)
    assert adapter.ensure_engine_running() is True
    adapter.play()
    adapter.advance(48_000)
    session_before = adapter.get_session_frame()
    assert session_before == 48_000
    assert adapter.get_engine_frame() == 48_000

    adapter.stop()
    assert engine.started is False

    # Native start resets to 0; transport must rebase — not keep 48000.
    assert adapter.ensure_engine_running() is True
    assert engine.start_count >= 2
    assert adapter.get_engine_frame() == 0
    assert adapter.get_session_frame() == session_before


def test_second_play_row_schedules_on_rebased_native_clock(monkeypatch, tmp_path):
    engine = RestartClockEngine()
    monkeypatch.setattr(adapter_module._native_audio, "is_available", lambda: True)
    monkeypatch.setattr(
        adapter_module._native_audio,
        "NativeAudioEngine",
        lambda: engine,
    )

    wav = tmp_path / "tone.wav"
    import soundfile as sf

    sr = 48_000
    t = np.arange(sr) / sr
    sf.write(str(wav), (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32), sr)

    adapter = adapter_module.WorkbenchTransportAdapter(sample_rate=sr)
    preview = TransportAwarePreview(WorkbenchPreviewPlayer(), adapter)

    row = WorkbenchRow(
        display_name="tone",
        relative_path=wav.name,
        path=str(wav),
        bpm=None,
        key=None,
        key_conf=None,
        loudness=None,
        brightness=None,
        sample_class="OneShot",
        pred_type="OneShot",
        status="ok",
    )

    assert preview.play_row(row).ok
    assert engine.schedule_calls
    first_sched = engine.schedule_calls[-1][1]
    assert first_sched == 0

    # Simulate audible progress on both clocks, then explicit audition stop.
    engine.advance(12_800)
    adapter.advance(12_800)
    preview.stop()

    assert preview.play_row(row).ok
    second_sched = engine.schedule_calls[-1][1]
    # Must not schedule at stale pre-stop transport frame (12800).
    assert second_sched == 0, (
        f"second audition scheduled at {second_sched}, expected rebased 0 "
        "(stale transport clock would leave the voice SCHEDULED/silent)"
    )
