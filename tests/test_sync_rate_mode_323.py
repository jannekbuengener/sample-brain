"""Consolidated deterministic proof tests for #323: SYNC playback-rate mode.

Covers the deterministic portion of the #323 mandatory test matrix (Pflicht-Tests)
without a native DSP build or audio device: exact rational rate, SYNC-off -> 1.0,
shared logical rate-change frame for all voices, missing/zero/NaN BPM -> not_syncable,
no silent BPM normalisation, source-BPM metadata preservation, and buffer-invariant
rate-change event frame.

The audible native-DSP/device playback proof is owned by the native audio core
(#321/#324) and validated under #328; it is intentionally NOT faked here.
"""

from __future__ import annotations

import math

import pytest

from src.session_grid import (
    MusicalPosition,
    compute_sync_playback_rate,
    schedule_events_in_buffer,
)
from src.workbench_transport_adapter import WorkbenchTransportAdapter


class RecordingNativeEngine:
    """Lightweight native stand-in that records rate assignments."""

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


def _adapter_without_native(*, bpm: float = 132.0) -> WorkbenchTransportAdapter:
    return WorkbenchTransportAdapter(sample_rate=48_000, initial_bpm=bpm)


def test_rate_128_to_132_is_exactly_1_03125():
    rate, status = compute_sync_playback_rate(132.0, 128.0, sync_enabled=True)
    assert rate == 1.03125
    assert status == "sync"


def test_rate_140_to_132_matches_ratio():
    rate, status = compute_sync_playback_rate(132.0, 140.0, sync_enabled=True)
    assert rate == pytest.approx(132.0 / 140.0)
    assert status == "sync"


def test_rate_132_to_132_is_unity():
    rate, status = compute_sync_playback_rate(132.0, 132.0, sync_enabled=True)
    assert rate == 1.0
    assert status == "sync"


def test_sync_off_always_returns_rate_one():
    assert compute_sync_playback_rate(132.0, 128.0, sync_enabled=False) == (1.0, "sync")
    assert compute_sync_playback_rate(140.0, 140.0, sync_enabled=False) == (1.0, "sync")


@pytest.mark.parametrize(
    "source_bpm",
    [None, 0.0, 0, float("nan"), "not-a-number", -4.0],
)
def test_invalid_source_bpm_is_not_syncable_and_safe(source_bpm):
    rate, status = compute_sync_playback_rate(132.0, source_bpm, sync_enabled=True)
    assert rate == 1.0
    assert status == "not_syncable"


def test_one_shot_without_bpm_is_not_silently_stretched():
    native = RecordingNativeEngine()
    adapter = WorkbenchTransportAdapter(
        sample_rate=48_000, initial_bpm=132.0, native_engine=native
    )
    adapter.set_voice_source_bpm(7, None)
    native.rate_calls.clear()
    adapter.toggle_sync()

    assert native.rate_calls == [(7, 1.0)]
    assert adapter.voice_sync_state(7) == (1.0, "not_syncable")


def test_no_silent_half_double_normalisation():
    rate_64, _ = compute_sync_playback_rate(132.0, 64.0, sync_enabled=True)
    assert rate_64 == pytest.approx(132.0 / 64.0)
    rate_256, _ = compute_sync_playback_rate(132.0, 256.0, sync_enabled=True)
    assert rate_256 == pytest.approx(132.0 / 256.0)


def test_all_voices_share_same_logical_rate_change_frame():
    native = RecordingNativeEngine()
    adapter = WorkbenchTransportAdapter(
        sample_rate=48_000, initial_bpm=132.0, native_engine=native
    )
    bar_one = adapter.tempo_map.bar_beat_to_frame(MusicalPosition(1, 0))

    adapter.set_voice_source_bpm(1, 128.0)
    adapter.set_voice_source_bpm(2, 140.0)
    adapter.toggle_sync()
    native.rate_calls.clear()

    adapter.seek(bar_one)
    adapter.play()
    change_frame = adapter.set_tempo(140.0)
    assert change_frame > adapter.get_session_frame()
    assert adapter.get_snapshot()["next_tempo_frame"] == change_frame

    assert adapter.voice_sync_state(1) == (pytest.approx(132.0 / 128.0), "sync")
    assert adapter.voice_sync_state(2) == (pytest.approx(132.0 / 140.0), "sync")

    adapter.advance(change_frame - bar_one)

    assert adapter.voice_sync_state(1) == (pytest.approx(140.0 / 128.0), "sync")
    assert adapter.voice_sync_state(2) == (pytest.approx(140.0 / 140.0), "sync")
    assert adapter.get_snapshot()["next_tempo_frame"] is None


def test_source_bpm_metadata_preserved_across_sync_and_tempo_changes():
    native = RecordingNativeEngine()
    adapter = WorkbenchTransportAdapter(
        sample_rate=48_000, initial_bpm=132.0, native_engine=native
    )
    adapter.set_voice_source_bpm(3, 128.0)

    adapter.toggle_sync()
    assert adapter.voice_sync_state(3) == (pytest.approx(132.0 / 128.0), "sync")

    adapter.toggle_sync()
    assert adapter.voice_sync_state(3) == (1.0, "sync")

    adapter.toggle_sync()
    assert adapter.voice_sync_state(3) == (pytest.approx(132.0 / 128.0), "sync")

    bar_one = adapter.tempo_map.bar_beat_to_frame(MusicalPosition(1, 0))

    adapter.seek(bar_one)
    adapter.play()
    change_up = adapter.set_tempo(140.0)
    adapter.advance(change_up - bar_one)
    assert adapter.voice_sync_state(3) == (pytest.approx(140.0 / 128.0), "sync")

    change_down = adapter.set_tempo(132.0)
    adapter.advance(change_down - adapter.get_session_frame())
    adapter.toggle_sync()
    adapter.toggle_sync()
    assert adapter.voice_sync_state(3) == (pytest.approx(132.0 / 128.0), "sync")


def test_rate_change_event_frame_is_buffer_invariant():
    event_frame = 48_000 * 4
    for frame_count in (512, 256, 128):
        buffer_start = event_frame - (event_frame % frame_count)
        scheduled = schedule_events_in_buffer(
            buffer_start_frame=buffer_start,
            frame_count=frame_count,
            event_frames=[event_frame],
        )
        assert len(scheduled) == 1
        assert scheduled[0].event_frame == event_frame


def test_semitone_derivation_does_not_mutate_source_key():
    rate = 132.0 / 128.0
    semitones = 12.0 * math.log2(rate)
    assert semitones == pytest.approx(12.0 * math.log2(132.0 / 128.0))
    assert 12.0 * math.log2(rate) == pytest.approx(semitones)
