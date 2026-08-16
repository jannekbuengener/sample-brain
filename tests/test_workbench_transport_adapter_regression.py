from __future__ import annotations

import threading

import pytest

import src.workbench_transport_adapter as adapter_module
from src.session_grid import MusicalPosition


class RecordingNativeEngine:
    def __init__(self) -> None:
        self.rate_calls: list[tuple[int, float]] = []

    def set_voice_rate(self, voice_id: int, rate: float) -> None:
        self.rate_calls.append((voice_id, rate))

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def close(self) -> None:
        return None


def _run_without_deadlock(callable_) -> None:
    error: list[BaseException] = []

    def worker() -> None:
        try:
            callable_()
        except BaseException as exc:  # pragma: no cover - surfaced below
            error.append(exc)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(timeout=1.0)
    assert not thread.is_alive(), "adapter call deadlocked"
    if error:
        raise error[0]


def _adapter_without_native(monkeypatch: pytest.MonkeyPatch, *, bpm: float = 132.0):
    monkeypatch.setattr(adapter_module._native_audio, "is_available", lambda: False)
    return adapter_module.WorkbenchTransportAdapter(
        sample_rate=48_000,
        initial_bpm=bpm,
    )


def test_set_source_bpm_toggle_sync_and_snapshot_do_not_deadlock(monkeypatch):
    adapter = _adapter_without_native(monkeypatch, bpm=128.0)

    _run_without_deadlock(lambda: adapter.set_source_bpm(128.0))
    _run_without_deadlock(adapter.toggle_sync)

    snapshot: dict[str, object] = {}
    _run_without_deadlock(lambda: snapshot.update(adapter.get_snapshot()))

    assert snapshot["sync_enabled"] is True
    assert snapshot["sync_rate"] == pytest.approx(1.0)
    assert snapshot["sync_status"] == "sync"


def test_running_tempo_label_stays_effective_until_scheduled_bar(monkeypatch):
    adapter = _adapter_without_native(monkeypatch, bpm=128.0)
    bar_one = adapter.tempo_map.bar_beat_to_frame(MusicalPosition(1, 0))
    adapter.seek(bar_one)
    adapter.play()

    effective_frame = adapter.set_tempo(132.0)
    before = adapter.get_snapshot()

    assert effective_frame == adapter.tempo_map.bar_beat_to_frame(MusicalPosition(2, 0))
    assert before["current_tempo"] == pytest.approx(128.0)
    assert before["next_tempo_bpm"] == pytest.approx(132.0)

    adapter.advance(effective_frame - bar_one)
    after = adapter.get_snapshot()

    assert after["current_tempo"] == pytest.approx(132.0)
    assert after["next_tempo_bpm"] is None


def test_registered_voices_receive_individual_rates_from_same_master_tempo():
    native = RecordingNativeEngine()
    adapter = adapter_module.WorkbenchTransportAdapter(
        sample_rate=48_000,
        initial_bpm=132.0,
        native_engine=native,
    )

    adapter.set_voice_source_bpm(11, 128.0)
    adapter.set_voice_source_bpm(22, 140.0)
    native.rate_calls.clear()

    adapter.toggle_sync()

    assert native.rate_calls == [
        (11, pytest.approx(132.0 / 128.0)),
        (22, pytest.approx(132.0 / 140.0)),
    ]

    native.rate_calls.clear()
    adapter.toggle_sync()
    assert native.rate_calls == [(11, 1.0), (22, 1.0)]


def test_missing_voice_bpm_is_not_silently_stretched():
    native = RecordingNativeEngine()
    adapter = adapter_module.WorkbenchTransportAdapter(
        sample_rate=48_000,
        initial_bpm=132.0,
        native_engine=native,
    )

    adapter.set_voice_source_bpm(7, None)
    native.rate_calls.clear()
    adapter.toggle_sync()

    assert native.rate_calls == [(7, 1.0)]
    assert adapter.voice_sync_state(7) == (1.0, "not_syncable")


def test_adapter_has_one_toggle_sync_definition():
    source = adapter_module.Path(adapter_module.__file__).read_text(encoding="utf-8")
    assert source.count("    def toggle_sync(") == 1
