from fractions import Fraction

import pytest

from src.session_grid import (
    INT64_MAX,
    INT64_MIN,
    MusicalPosition,
    SessionTransport,
    TempoMap,
    TempoSegment,
    TimeSignature,
    schedule_events_in_buffer,
)


@pytest.mark.parametrize("sample_rate", [44_100, 48_000])
@pytest.mark.parametrize("bpm", [120, 127, 127.5, 132])
def test_bar_boundaries_are_direct_and_drift_free_for_1000_bars(sample_rate, bpm):
    tempo_map = TempoMap(sample_rate=sample_rate, bpm=bpm)
    exact_bpm = Fraction(str(bpm))

    for bar in range(1001):
        expected = round(Fraction(bar * 4 * 60 * sample_rate, 1) / exact_bpm)
        actual = tempo_map.bar_beat_to_frame(MusicalPosition(bar=bar, beat=0))
        assert actual == expected


def test_tempo_segments_preserve_past_grid_positions():
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
    transport = SessionTransport(sample_rate=48_000, bpm=128)
    transport.seek(12_345)

    effective_frame = transport.set_tempo(132)

    assert effective_frame == 12_345
    assert transport.tempo_map.segments[-1].start_frame == 12_345
    assert transport.tempo_map.segments[-1].bpm == Fraction(132, 1)


def test_running_tempo_change_starts_at_next_bar_even_on_bar_boundary():
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
    tempo_map = TempoMap(sample_rate=44_100, bpm=127.5)

    for bar in (0, 1, 7, 64, 1000):
        for beat in range(4):
            position = MusicalPosition(bar=bar, beat=beat)
            frame = tempo_map.bar_beat_to_frame(position)
            assert tempo_map.quarter_note_to_frame(
                tempo_map.bar_beat_to_quarter_note(position)
            ) == frame


def test_time_signature_is_explicit_and_defaults_to_four_four():
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
