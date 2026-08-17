"""Tests for #322: Workbench TEMPO, SYNC and shared session grid."""
from __future__ import annotations

import inspect
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.session_grid import (
    INT64_MAX,
    INT64_MIN,
    SessionTransport,
    TempoMap,
    TempoSegment,
    TimeSignature,
    MusicalPosition,
    schedule_events_in_buffer,
)
from src.workbench import WorkbenchApp
from src.workbench_controller import WorkbenchRow, WorkbenchRowFilters
from src.workbench_transport_ui import (
    WorkbenchTransportUiController,
    format_transport_tempo_label,
)


# ─────────────────────────────────────────────────────────────────────────────
# Session Transport / TempoMap core contract tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("sample_rate", [44_100, 48_000])
@pytest.mark.parametrize("bpm", [120, 127, 127.5, 132])
def test_bar_boundaries_are_direct_and_drift_free_for_1000_bars(sample_rate, bpm):
    """Core #320 contract: bar boundaries derived directly from tempo segments."""
    tempo_map = TempoMap(sample_rate=sample_rate, bpm=bpm)
    exact_bpm = Fraction(str(bpm))

    for bar in range(1001):
        expected = round(Fraction(bar * 4 * 60 * sample_rate, 1) / exact_bpm)
        actual = tempo_map.bar_beat_to_frame(MusicalPosition(bar=bar, beat=0))
        assert actual == expected


def test_tempo_segments_preserve_past_grid_positions():
    """Core #320 contract: past tempo segments not modified by new changes."""
    tempo_map = TempoMap(sample_rate=48_000, bpm=128)
    past_frames = [
        0,
        100,
        tempo_map.bar_beat_to_frame(MusicalPosition(bar=4, beat=0)),
    ]
    before = {frame: tempo_map.frame_to_quarter_note(frame) for frame in past_frames}

    first = tempo_map.add_tempo_change_at_quarter(
        effective_quarter=Fraction(8 * 4, 1), bpm=132
    )
    second = tempo_map.add_tempo_change_at_quarter(
        effective_quarter=Fraction(16 * 4, 1), bpm=140
    )

    assert first.start_quarter == Fraction(32, 1)
    assert second.start_quarter == Fraction(64, 1)
    assert tempo_map.frame_to_bar_beat(first.start_frame) == MusicalPosition(8, 0)
    assert tempo_map.frame_to_bar_beat(second.start_frame) == MusicalPosition(16, 0)
    assert {frame: tempo_map.frame_to_quarter_note(frame) for frame in past_frames} == before


def test_stopped_tempo_change_is_immediate_at_current_session_frame():
    """Core #320: stopped transport → TEMPO change immediate at session_frame."""
    transport = SessionTransport(sample_rate=48_000, bpm=128)
    transport.seek(12_345)

    effective_frame = transport.set_tempo(132)

    assert effective_frame == 12_345
    assert transport.tempo_map.segments[-1].start_frame == 12_345
    assert transport.tempo_map.segments[-1].bpm == Fraction(132, 1)


def test_running_tempo_change_starts_at_next_bar_even_on_bar_boundary():
    """Core #320: running transport → TEMPO change at next bar boundary."""
    transport = SessionTransport(sample_rate=48_000, bpm=128)
    bar_one = transport.tempo_map.bar_beat_to_frame(MusicalPosition(1, 0))
    transport.seek(bar_one)
    transport.play()

    effective_frame = transport.set_tempo(132)

    expected = transport.tempo_map.bar_beat_to_frame(MusicalPosition(2, 0))
    assert effective_frame == expected
    assert transport.tempo_map.segments[-1].start_quarter == Fraction(8, 1)
    assert transport.tempo_map.frame_to_bar_beat(effective_frame) == MusicalPosition(2, 0)


def test_engine_and_session_frames_are_separate_transport_coordinates():
    """Core #320: engine_frame and session_frame stay separate unless playing."""
    transport = SessionTransport(sample_rate=44_100, bpm=120)

    transport.advance(256)
    assert transport.engine_frame == 256
    assert transport.session_frame == 0

    transport.play()
    transport.advance(128)
    assert transport.engine_frame == 384
    assert transport.session_frame == 128

    transport.stop()
    transport.seek(4_096)
    transport.advance(64)
    assert transport.engine_frame == 448
    assert transport.session_frame == 4_096


def test_frame_quarter_and_bar_beat_round_trip_on_grid_boundaries():
    """Core #320: round-trip frame → quarter → bar/beat → frame is deterministic."""
    tempo_map = TempoMap(sample_rate=44_100, bpm=127.5)

    for bar in (0, 1, 7, 64, 1000):
        for beat in range(4):
            position = MusicalPosition(bar=bar, beat=beat)
            frame = tempo_map.bar_beat_to_frame(position)
            assert tempo_map.quarter_note_to_frame(
                tempo_map.bar_beat_to_quarter_note(position)
            ) == frame


def test_time_signature_is_explicit_and_defaults_to_four_four():
    """Core #320: TimeSignature defaults to 4/4; non-power-of-2 denominators rejected."""
    default = TimeSignature()
    six_eight = TimeSignature(6, 8)

    assert default.quarter_notes_per_beat == Fraction(1, 1)
    assert default.quarter_notes_per_bar == Fraction(4, 1)
    assert six_eight.quarter_notes_per_beat == Fraction(1, 2)
    assert six_eight.quarter_notes_per_bar == Fraction(3, 1)

    with pytest.raises(ValueError, match="power of two"):
        TimeSignature(4, 3)


def _collect_scheduled_event_frames(event_frames, *, buffer_size, end_frame):
    found = []
    buffer_start = 0
    while buffer_start < end_frame:
        found.extend(
            event.event_frame
            for event in schedule_events_in_buffer(
                buffer_start_frame=buffer_start,
                frame_count=buffer_size,
                event_frames=event_frames,
            )
        )
        buffer_start += buffer_size
    return found


def test_absolute_event_frames_do_not_depend_on_audio_buffer_size():
    tempo_map = TempoMap(sample_rate=48_000, bpm=132)
    event_frames = [
        tempo_map.bar_beat_to_frame(MusicalPosition(bar=bar, beat=beat))
        for bar in range(2)
        for beat in range(4)
    ]
    end_frame = event_frames[-1] + 1

    for buffer_size in (64, 128, 257, 512):
        assert _collect_scheduled_event_frames(
            event_frames, buffer_size=buffer_size, end_frame=end_frame
        ) == event_frames


def test_buffer_scheduler_uses_half_open_frame_range():
    events = schedule_events_in_buffer(
        buffer_start_frame=128,
        frame_count=128,
        event_frames=[127, 128, 255, 256],
    )

    assert [(event.event_frame, event.offset) for event in events] == [
        (128, 0),
        (255, 127),
    ]


def test_signed_int64_frame_limits_are_enforced():
    TempoSegment(start_frame=INT64_MIN, start_quarter=0, bpm=120)
    TempoSegment(start_frame=INT64_MAX, start_quarter=0, bpm=120)

    with pytest.raises(OverflowError, match="signed int64"):
        TempoSegment(start_frame=INT64_MIN - 1, start_quarter=0, bpm=120)
    with pytest.raises(OverflowError, match="signed int64"):
        TempoSegment(start_frame=INT64_MAX + 1, start_quarter=0, bpm=120)
    with pytest.raises(OverflowError, match="buffer end"):
        schedule_events_in_buffer(
            buffer_start_frame=INT64_MAX, frame_count=2, event_frames=[]
        )


class _TestNativeClock:
    """Small explicit native-clock double; it never replaces DSP behavior."""

    def __init__(self) -> None:
        self.engine_frame = 0
        self.running = False

    def start(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False

    def close(self) -> None:
        return None

    def set_voice_rate(self, _voice_id: int, _rate: float) -> None:
        return None

    def snapshot(self):
        return SimpleNamespace(engine_frame=self.engine_frame, running=self.running)


# ─────────────────────────────────────────────────────────────────────────────
# #322-specific: Workbench Transport Adapter contract
# ─────────────────────────────────────────────────────────────────────────────


def test_adapter_tempo_bpm_display_format():
    assert format_transport_tempo_label(132.0) == "TEMPO: 132 BPM"
    assert format_transport_tempo_label(127.5) == "TEMPO: 127.5 BPM"


def test_adapter_sync_toggle_changes_state():
    from unittest.mock import patch
    from src.workbench_transport_adapter import WorkbenchTransportAdapter

    with patch("src.native_audio.is_available", return_value=False):
        adapter = WorkbenchTransportAdapter(sample_rate=48_000, initial_bpm=132.0)
        assert adapter.is_sync_enabled() is False
        assert adapter.toggle_sync() is True
        assert adapter.is_sync_enabled() is True
        assert adapter.toggle_sync() is False
        assert adapter.is_sync_enabled() is False


def test_adapter_stopped_tempo_immediate():
    from src.workbench_transport_adapter import WorkbenchTransportAdapter

    adapter = WorkbenchTransportAdapter(sample_rate=48_000, initial_bpm=128.0)
    adapter.seek(12_345)

    effective_frame = adapter.set_tempo(132.0)

    assert effective_frame == 12_345
    assert adapter.tempo_map.segments[-1].start_frame == 12_345
    assert adapter.tempo_map.segments[-1].bpm == 132.0


def test_adapter_running_tempo_next_bar():
    from src.workbench_transport_adapter import WorkbenchTransportAdapter

    adapter = WorkbenchTransportAdapter(
        sample_rate=48_000,
        initial_bpm=128.0,
        native_engine=_TestNativeClock(),
    )
    bar_one = adapter.tempo_map.bar_beat_to_frame(MusicalPosition(1, 0))
    adapter.seek(bar_one)
    adapter.play()

    effective_frame = adapter.set_tempo(132.0)

    expected = adapter.tempo_map.bar_beat_to_frame(MusicalPosition(2, 0))
    assert effective_frame == expected


def test_adapter_engine_and_session_frames_separate():
    from src.workbench_transport_adapter import WorkbenchTransportAdapter

    native = _TestNativeClock()
    adapter = WorkbenchTransportAdapter(
        sample_rate=48_000,
        initial_bpm=120.0,
        native_engine=native,
    )

    adapter.advance(256)
    assert adapter.engine_frame == 256
    assert adapter.session_frame == 0

    adapter.play()
    adapter.advance(128)
    assert adapter.engine_frame == 384
    assert adapter.session_frame == 128

    adapter.stop()
    adapter.seek(4_096)
    adapter.advance(64)
    assert adapter.engine_frame == 448
    assert adapter.session_frame == 4_096


def test_adapter_grid_position_from_snapshot():
    from src.workbench_transport_adapter import WorkbenchTransportAdapter

    adapter = WorkbenchTransportAdapter(sample_rate=48_000, initial_bpm=132.0)
    adapter.seek(12_345)

    snapshot = adapter.get_snapshot()
    position = adapter.tempo_map.frame_to_bar_beat(snapshot["session_frame"])
    assert snapshot["session_frame"] == 12_345
    assert snapshot["bar"] == position.bar
    assert snapshot["beat"] == position.beat


def test_adapter_multiple_voices_share_session_transport():
    from src.workbench_transport_adapter import WorkbenchTransportAdapter

    transport = SessionTransport(sample_rate=48_000, bpm=132.0)
    adapter_a = WorkbenchTransportAdapter(
        sample_rate=48_000, initial_bpm=132.0, transport=transport
    )
    adapter_b = WorkbenchTransportAdapter(
        sample_rate=48_000, initial_bpm=132.0, transport=transport
    )

    assert adapter_a.tempo_map is adapter_b.tempo_map
    assert adapter_a.session_frame == adapter_b.session_frame


def test_adapter_preserves_existing_workbench_filters():
    from src.workbench_controller import (
        apply_workbench_filters,
        format_workbench_active_filter_summary,
        WorkbenchRowFilters,
    )

    rows = [
        WorkbenchRow(
            display_name="kick",
            relative_path="kick.wav",
            path="/tmp/kick.wav",
            bpm=132.0,
            key="C",
            key_conf=0.8,
            loudness=-10.0,
            brightness=50.0,
            sample_class="oneshot",
            pred_type="Kick",
            status="ok",
            details={},
        ),
        WorkbenchRow(
            display_name="pad",
            relative_path="pad.wav",
            path="/tmp/pad.wav",
            bpm=90.0,
            key="Am",
            key_conf=0.7,
            loudness=-12.0,
            brightness=40.0,
            sample_class="loop",
            pred_type="Pad",
            status="ok",
            details={},
        ),
    ]

    filtered = apply_workbench_filters(rows, "kick")
    assert len(filtered) == 1
    assert filtered[0].display_name == "kick"

    filtered = apply_workbench_filters(
        rows,
        "",
        WorkbenchRowFilters(min_bpm=100.0, max_bpm=150.0),
    )
    assert len(filtered) == 1
    assert filtered[0].display_name == "kick"

    assert format_workbench_active_filter_summary("", None) == ""


# ─────────────────────────────────────────────────────────────────────────────
# #322: Native fallback / preview path preserved
# ─────────────────────────────────────────────────────────────────────────────


def test_adapter_native_unavailable_graceful_fallback():
    from unittest.mock import patch
    from src.workbench_transport_adapter import WorkbenchTransportAdapter

    with patch("src.native_audio.is_available", return_value=False):
        adapter = WorkbenchTransportAdapter(sample_rate=48_000, initial_bpm=132.0)
        assert adapter.native_available is False
        adapter.play()
        snapshot = adapter.get_snapshot()
        assert snapshot["native_available"] is False
        assert snapshot["playing"] is False
        assert snapshot["engine_frame"] == 0
        assert snapshot["session_frame"] == 0


def test_adapter_seek_preserves_session_frame():
    from src.workbench_transport_adapter import WorkbenchTransportAdapter

    adapter = WorkbenchTransportAdapter(sample_rate=48_000, initial_bpm=120.0)

    adapter.seek(4_096)
    assert adapter.session_frame == 4_096
    assert adapter.engine_frame == 0

    adapter.advance(256)
    assert adapter.engine_frame == 256
    assert adapter.session_frame == 4_096


def test_adapter_tempo_change_while_stopped():
    from src.workbench_transport_adapter import WorkbenchTransportAdapter

    adapter = WorkbenchTransportAdapter(sample_rate=48_000, initial_bpm=128.0)
    adapter.seek(0)

    frame = adapter.set_tempo(140.0)

    assert frame == 0
    assert adapter.tempo_map.segments[-1].bpm == 140.0


def test_adapter_tempo_change_while_playing():
    from src.workbench_transport_adapter import WorkbenchTransportAdapter

    adapter = WorkbenchTransportAdapter(
        sample_rate=48_000,
        initial_bpm=128.0,
        native_engine=_TestNativeClock(),
    )
    adapter.play()
    adapter.seek(adapter.tempo_map.bar_beat_to_frame(MusicalPosition(1, 0)))

    frame = adapter.set_tempo(132.0)

    expected = adapter.tempo_map.bar_beat_to_frame(MusicalPosition(2, 0))
    assert frame == expected


def test_ui_contains_exact_tempo_bpm_string():
    init_source = inspect.getsource(WorkbenchApp.__init__)
    build_source = inspect.getsource(WorkbenchTransportUiController._build_controls)

    assert "attach_workbench_transport_ui(self)" in init_source
    assert "textvariable=self.tempo_var" in build_source
    assert format_transport_tempo_label(132.0) == "TEMPO: 132 BPM"


def test_ui_contains_exact_sync_control():
    build_source = inspect.getsource(WorkbenchTransportUiController._build_controls)

    assert 'text="SYNC"' in build_source
    assert "variable=self.sync_var" in build_source
    assert "command=self.apply_sync_control" in build_source


def test_no_second_main_tempo_label():
    build_source = inspect.getsource(WorkbenchTransportUiController._build_controls)
    formatter_source = inspect.getsource(format_transport_tempo_label)

    assert "Master Tempo" not in build_source
    assert "Master Tempo" not in formatter_source
    assert 'return f"TEMPO: {rendered} BPM"' in formatter_source


def test_existing_workbench_smoke_tests_pass():
    import subprocess

    result = subprocess.run(
        ["python", "-m", "src.cli", "--help"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert result.returncode == 0
    assert "workbench" in result.stdout


def test_existing_preview_tests_pass():
    import subprocess

    result = subprocess.run(
        ["python", "-m", "pytest", "tests/test_workbench_preview.py", "-q"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert result.returncode == 0, f"Preview tests failed: {result.stdout}"


def test_session_grid_tests_pass():
    import subprocess

    result = subprocess.run(
        ["python", "-m", "pytest", "tests/test_session_grid.py", "-q"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert result.returncode == 0, f"Session grid tests failed: {result.stdout}"


# ─────────────────────────────────────────────────────────────────────────────
# #323: SYNC playback-rate mode tests
# ─────────────────────────────────────────────────────────────────────────────


def test_compute_sync_rate_128_to_132():
    from src.session_grid import compute_sync_playback_rate

    rate, status = compute_sync_playback_rate(132.0, 128.0, sync_enabled=True)
    assert rate == 1.03125
    assert status == "sync"


def test_compute_sync_rate_140_to_132():
    from src.session_grid import compute_sync_playback_rate

    rate, status = compute_sync_playback_rate(132.0, 140.0, sync_enabled=True)
    assert abs(rate - 132 / 140) < 1e-9
    assert status == "sync"


def test_compute_sync_rate_132_to_132():
    from src.session_grid import compute_sync_playback_rate

    rate, status = compute_sync_playback_rate(132.0, 132.0, sync_enabled=True)
    assert rate == 1.0
    assert status == "sync"


def test_compute_sync_rate_sync_off():
    from src.session_grid import compute_sync_playback_rate

    rate, status = compute_sync_playback_rate(132.0, 128.0, sync_enabled=False)
    assert rate == 1.0
    assert status == "sync"


def test_compute_sync_rate_invalid_bpm_none():
    from src.session_grid import compute_sync_playback_rate

    rate, status = compute_sync_playback_rate(132.0, None, sync_enabled=True)
    assert rate == 1.0
    assert status == "not_syncable"


def test_compute_sync_rate_invalid_bpm_zero():
    from src.session_grid import compute_sync_playback_rate

    rate, status = compute_sync_playback_rate(132.0, 0, sync_enabled=True)
    assert rate == 1.0
    assert status == "not_syncable"


def test_compute_sync_rate_invalid_bpm_nan():
    from src.session_grid import compute_sync_playback_rate

    rate, status = compute_sync_playback_rate(132.0, float("nan"), sync_enabled=True)
    assert rate == 1.0
    assert status == "not_syncable"


def test_compute_sync_rate_invalid_bpm_negative():
    from src.session_grid import compute_sync_playback_rate

    rate, status = compute_sync_playback_rate(132.0, -128.0, sync_enabled=True)
    assert rate == 1.0
    assert status == "not_syncable"


def test_compute_sync_rate_extreme_rate():
    from src.session_grid import compute_sync_playback_rate

    rate, status = compute_sync_playback_rate(132.0, 32.0, sync_enabled=True)
    assert rate == 1.0
    assert status == "not_syncable"

    rate2, status2 = compute_sync_playback_rate(132.0, 529.0, sync_enabled=True)
    assert rate2 == 1.0
    assert status2 == "not_syncable"