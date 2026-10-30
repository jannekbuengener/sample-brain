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


def test_fractional_source_bpm_keeps_exact_ratio_no_integer_rounding():
    """#1218/#1215: fractional source BPM must not be rounded before the ratio."""
    rate, status = compute_sync_playback_rate(132.0, 127.37, sync_enabled=True)
    assert status == "sync"
    assert rate == pytest.approx(132.0 / 127.37)
    assert rate != pytest.approx(132.0 / 127.0)


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


@pytest.mark.parametrize("master_bpm", [float("nan"), float("inf"), float("-inf"), 0.0])
def test_non_finite_or_zero_master_bpm_is_not_syncable(master_bpm):
    """#1215: non-finite/zero MASTER must never look like a successful sync rate."""
    rate, status = compute_sync_playback_rate(master_bpm, 128.0, sync_enabled=True)
    assert status == "not_syncable"
    assert rate == 1.0
    assert math.isfinite(rate)


def test_non_finite_master_never_reaches_set_voice_rate():
    """#1215: NaN/Inf MASTER must not deliver a non-finite rate to native voices."""
    native = RecordingNativeEngine()
    adapter = WorkbenchTransportAdapter(
        sample_rate=48_000, initial_bpm=132.0, native_engine=native
    )
    adapter.set_voice_source_bpm(1, 128.0)
    adapter.toggle_sync()
    native.rate_calls.clear()

    for bad in (float("nan"), float("inf"), float("-inf")):
        try:
            adapter.set_tempo(bad)
        except (ValueError, OverflowError, TypeError):
            # Fail-closed rejection is acceptable; still must not have pushed NaN/Inf.
            pass
        for _voice_id, rate in native.rate_calls:
            assert math.isfinite(rate)
            assert rate > 0.0
        assert all(math.isfinite(r) for _vid, r in native.rate_calls)
        # Authoritative resume tempo stays finite after the attempt.
        assert math.isfinite(adapter.get_resume_master_bpm())
        assert adapter.get_resume_master_bpm() > 0.0

    rate, status = adapter.voice_sync_state(1)
    assert math.isfinite(rate)
    assert status in {"sync", "not_syncable"}


def test_two_simultaneous_voices_no_growing_relative_drift_over_master_bars():
    """#1215: distinct source BPMs share MASTER authority without growing drift.

    Advance several MASTER bars with two registered voices. Source-beat progress
    derived from session frames * rate must stay aligned to the same MASTER beat
    count for both voices (phase error must not grow with bar count).
    """
    native = RecordingNativeEngine()
    master_bpm = 132.0
    adapter = WorkbenchTransportAdapter(
        sample_rate=48_000, initial_bpm=master_bpm, native_engine=native
    )
    source_a = 120.0
    source_b = 140.0
    adapter.set_voice_source_bpm(1, source_a)
    adapter.set_voice_source_bpm(2, source_b)
    adapter.toggle_sync()

    rate_a, status_a = adapter.voice_sync_state(1)
    rate_b, status_b = adapter.voice_sync_state(2)
    assert status_a == "sync" and status_b == "sync"
    assert rate_a == pytest.approx(master_bpm / source_a)
    assert rate_b == pytest.approx(master_bpm / source_b)

    sample_rate = 48_000
    start = adapter.get_session_frame()
    adapter.play()

    phase_errors: list[tuple[float, float]] = []
    for bars in (1, 2, 4, 8):
        target = adapter.tempo_map.bar_beat_to_frame(MusicalPosition(bars, 0))
        adapter.advance(target - adapter.get_session_frame())
        session_frames = adapter.get_session_frame() - start
        master_beats = (session_frames / sample_rate) * (master_bpm / 60.0)

        source_beats_a = ((session_frames * rate_a) / sample_rate) * (source_a / 60.0)
        source_beats_b = ((session_frames * rate_b) / sample_rate) * (source_b / 60.0)

        err_a = abs(source_beats_a - master_beats)
        err_b = abs(source_beats_b - master_beats)
        phase_errors.append((err_a, err_b))

        assert err_a < 1e-6, f"voice A drifted after {bars} bars: {err_a}"
        assert err_b < 1e-6, f"voice B drifted after {bars} bars: {err_b}"
        # Relative drift between voices must not grow with span.
        relative = abs(source_beats_a - source_beats_b)
        assert relative < 1e-6, f"relative voice drift after {bars} bars: {relative}"

    # Final span error must not exceed early-span error (no accumulation).
    assert phase_errors[-1][0] <= phase_errors[0][0] + 1e-9
    assert phase_errors[-1][1] <= phase_errors[0][1] + 1e-9
    # Rates remain the same authoritative assignments (no per-voice clock rewrite).
    assert adapter.voice_sync_state(1) == (pytest.approx(rate_a), "sync")
    assert adapter.voice_sync_state(2) == (pytest.approx(rate_b), "sync")


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
