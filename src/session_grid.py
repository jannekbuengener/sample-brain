from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable

INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1


TempoValue = int | float | str | Fraction


def _validate_int64(value: int, *, name: str = "frame") -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an int")
    if not INT64_MIN <= value <= INT64_MAX:
        raise OverflowError(f"{name} outside signed int64 range")
    return value


def _as_fraction(value: TempoValue, *, name: str) -> Fraction:
    if isinstance(value, Fraction):
        result = value
    elif isinstance(value, int) and not isinstance(value, bool):
        result = Fraction(value, 1)
    elif isinstance(value, str):
        result = Fraction(value)
    elif isinstance(value, float):
        # Decimal text preserves values such as 127.5 exactly and avoids carrying
        # binary-float representation noise into the musical grid.
        result = Fraction(str(value))
    else:
        raise TypeError(f"{name} must be int, float, str, or Fraction")
    return result


@dataclass(frozen=True)
class TimeSignature:
    numerator: int = 4
    denominator: int = 4

    def __post_init__(self) -> None:
        if (
            not isinstance(self.numerator, int)
            or isinstance(self.numerator, bool)
            or self.numerator <= 0
        ):
            raise ValueError("numerator must be a positive integer")
        if (
            not isinstance(self.denominator, int)
            or isinstance(self.denominator, bool)
            or self.denominator <= 0
            or self.denominator & (self.denominator - 1)
        ):
            raise ValueError("denominator must be a positive power of two")

    @property
    def quarter_notes_per_beat(self) -> Fraction:
        return Fraction(4, self.denominator)

    @property
    def quarter_notes_per_bar(self) -> Fraction:
        return self.numerator * self.quarter_notes_per_beat


@dataclass(frozen=True)
class MusicalPosition:
    """Zero-based bar/beat position with an exact fractional beat remainder."""

    bar: int
    beat: int
    beat_fraction: Fraction = Fraction(0, 1)

    def __post_init__(self) -> None:
        if not isinstance(self.bar, int) or isinstance(self.bar, bool) or self.bar < 0:
            raise ValueError("bar must be a non-negative integer")
        if (
            not isinstance(self.beat, int)
            or isinstance(self.beat, bool)
            or self.beat < 0
        ):
            raise ValueError("beat must be a non-negative integer")
        beat_fraction = _as_fraction(self.beat_fraction, name="beat_fraction")
        if not Fraction(0, 1) <= beat_fraction < Fraction(1, 1):
            raise ValueError("beat_fraction must be in [0, 1)")
        object.__setattr__(self, "beat_fraction", beat_fraction)


@dataclass(frozen=True)
class TempoSegment:
    """One exact musical-time anchor plus the tempo active from that point."""

    start_frame: int
    start_quarter: Fraction
    bpm: Fraction

    def __post_init__(self) -> None:
        _validate_int64(self.start_frame, name="start_frame")
        start_quarter = _as_fraction(self.start_quarter, name="start_quarter")
        bpm = _as_fraction(self.bpm, name="bpm")
        if start_quarter < 0:
            raise ValueError("start_quarter must be non-negative")
        if bpm <= 0:
            raise ValueError("bpm must be positive")
        object.__setattr__(self, "start_quarter", start_quarter)
        object.__setattr__(self, "bpm", bpm)


@dataclass(frozen=True)
class BufferScheduledEvent:
    event_frame: int
    offset: int

    def __post_init__(self) -> None:
        _validate_int64(self.event_frame, name="event_frame")
        if self.offset < 0:
            raise ValueError("offset must be non-negative")


class TempoMap:
    """Deterministic frame <-> musical-grid mapping.

    Grid positions are always derived directly from a tempo segment anchor using
    exact rational arithmetic. Rounded beat/bar frames are never fed back into
    the next grid calculation, so rounding cannot accumulate across the session.
    """

    def __init__(
        self,
        *,
        sample_rate: int,
        bpm: TempoValue = 120,
        time_signature: TimeSignature | None = None,
    ) -> None:
        if (
            not isinstance(sample_rate, int)
            or isinstance(sample_rate, bool)
            or sample_rate <= 0
        ):
            raise ValueError("sample_rate must be a positive integer")
        initial_bpm = _as_fraction(bpm, name="bpm")
        if initial_bpm <= 0:
            raise ValueError("bpm must be positive")

        self.sample_rate = sample_rate
        self.time_signature = time_signature or TimeSignature()
        self._segments: list[TempoSegment] = [
            TempoSegment(
                start_frame=0,
                start_quarter=Fraction(0, 1),
                bpm=initial_bpm,
            )
        ]

    @property
    def segments(self) -> tuple[TempoSegment, ...]:
        return tuple(self._segments)

    def _segment_for_frame(self, frame: int) -> TempoSegment:
        _validate_int64(frame)
        if frame < self._segments[0].start_frame:
            raise ValueError("frame precedes tempo map")
        starts = [segment.start_frame for segment in self._segments]
        return self._segments[bisect_right(starts, frame) - 1]

    def _segment_for_quarter(self, quarter_note: TempoValue) -> TempoSegment:
        quarter = _as_fraction(quarter_note, name="quarter_note")
        if quarter < self._segments[0].start_quarter:
            raise ValueError("quarter_note precedes tempo map")
        starts = [segment.start_quarter for segment in self._segments]
        return self._segments[bisect_right(starts, quarter) - 1]

    def frame_to_quarter_note(self, frame: int) -> Fraction:
        segment = self._segment_for_frame(frame)
        delta_frames = Fraction(frame - segment.start_frame, 1)
        return segment.start_quarter + (
            delta_frames * segment.bpm / Fraction(60 * self.sample_rate, 1)
        )

    def quarter_note_to_frame(self, quarter_note: TempoValue) -> int:
        quarter = _as_fraction(quarter_note, name="quarter_note")
        segment = self._segment_for_quarter(quarter)
        raw_frame = Fraction(segment.start_frame, 1) + (
            (quarter - segment.start_quarter)
            * Fraction(60 * self.sample_rate, 1)
            / segment.bpm
        )
        # Fraction.__round__ is exact and deterministic (nearest integer,
        # ties-to-even). The important contract is one direct rounding from the
        # segment anchor, never recursive rounding from a prior grid boundary.
        return _validate_int64(round(raw_frame))

    def _append_or_replace_segment(
        self,
        *,
        effective_frame: int,
        effective_quarter: Fraction,
        bpm: TempoValue,
    ) -> TempoSegment:
        next_bpm = _as_fraction(bpm, name="bpm")
        if next_bpm <= 0:
            raise ValueError("bpm must be positive")

        last = self._segments[-1]
        if effective_frame < last.start_frame:
            raise ValueError("tempo changes must be chronological")

        segment = TempoSegment(
            start_frame=effective_frame,
            start_quarter=effective_quarter,
            bpm=next_bpm,
        )
        if effective_frame == last.start_frame:
            if effective_quarter != last.start_quarter:
                raise ValueError("replacement tempo anchor must match current segment")
            self._segments[-1] = segment
        else:
            if effective_quarter <= last.start_quarter:
                raise ValueError("tempo segment quarter anchors must increase")
            self._segments.append(segment)
        return segment

    def add_tempo_change_at_frame(
        self, *, effective_frame: int, bpm: TempoValue
    ) -> TempoSegment:
        """Add an immediate tempo change at an arbitrary session frame.

        This is the stopped-transport path. The musical anchor is derived from
        the map that existed before the change so earlier positions stay intact.
        """

        _validate_int64(effective_frame, name="effective_frame")
        if effective_frame < self._segments[-1].start_frame:
            raise ValueError("tempo changes must be chronological")
        anchor_quarter = self.frame_to_quarter_note(effective_frame)
        return self._append_or_replace_segment(
            effective_frame=effective_frame,
            effective_quarter=anchor_quarter,
            bpm=bpm,
        )

    def add_tempo_change_at_quarter(
        self, *, effective_quarter: TempoValue, bpm: TempoValue
    ) -> TempoSegment:
        """Add a grid-anchored tempo change at an exact musical position."""

        quarter = _as_fraction(effective_quarter, name="effective_quarter")
        if quarter < self._segments[-1].start_quarter:
            raise ValueError("tempo changes must be chronological")
        effective_frame = self.quarter_note_to_frame(quarter)
        return self._append_or_replace_segment(
            effective_frame=effective_frame,
            effective_quarter=quarter,
            bpm=bpm,
        )

    def quarter_note_to_bar_beat(self, quarter_note: TempoValue) -> MusicalPosition:
        quarter = _as_fraction(quarter_note, name="quarter_note")
        if quarter < 0:
            raise ValueError("quarter_note must be non-negative")

        per_bar = self.time_signature.quarter_notes_per_bar
        per_beat = self.time_signature.quarter_notes_per_beat
        bar = int(quarter // per_bar)
        within_bar = quarter - bar * per_bar
        beat = int(within_bar // per_beat)
        beat_fraction = (within_bar - beat * per_beat) / per_beat
        return MusicalPosition(bar=bar, beat=beat, beat_fraction=beat_fraction)

    def bar_beat_to_quarter_note(self, position: MusicalPosition) -> Fraction:
        if not isinstance(position, MusicalPosition):
            raise TypeError("position must be MusicalPosition")
        if position.beat >= self.time_signature.numerator:
            raise ValueError("beat outside time signature")
        return (
            position.bar * self.time_signature.quarter_notes_per_bar
            + (position.beat + position.beat_fraction)
            * self.time_signature.quarter_notes_per_beat
        )

    def frame_to_bar_beat(self, frame: int) -> MusicalPosition:
        return self.quarter_note_to_bar_beat(self.frame_to_quarter_note(frame))

    def bar_beat_to_frame(self, position: MusicalPosition) -> int:
        return self.quarter_note_to_frame(self.bar_beat_to_quarter_note(position))

    def next_bar_start_quarter(self, frame: int) -> Fraction:
        quarter = self.frame_to_quarter_note(frame)
        per_bar = self.time_signature.quarter_notes_per_bar
        current_bar = int(quarter // per_bar)
        return Fraction(current_bar + 1, 1) * per_bar

    def next_bar_start_frame(self, frame: int) -> int:
        return self.quarter_note_to_frame(self.next_bar_start_quarter(frame))


class SessionTransport:
    """Small session transport that keeps engine and session time separate."""

    def __init__(
        self,
        *,
        sample_rate: int,
        bpm: TempoValue = 120,
        time_signature: TimeSignature | None = None,
    ) -> None:
        self.tempo_map = TempoMap(
            sample_rate=sample_rate,
            bpm=bpm,
            time_signature=time_signature,
        )
        self.engine_frame = 0
        self.session_frame = 0
        self.playing = False

    @property
    def sample_rate(self) -> int:
        return self.tempo_map.sample_rate

    def play(self) -> None:
        self.playing = True

    def stop(self) -> None:
        self.playing = False

    def seek(self, frame: int) -> None:
        _validate_int64(frame, name="session_frame")
        if frame < 0:
            raise ValueError("session_frame must be non-negative in v1")
        self.session_frame = frame

    def advance(self, engine_frames: int) -> None:
        if (
            not isinstance(engine_frames, int)
            or isinstance(engine_frames, bool)
            or engine_frames < 0
        ):
            raise ValueError("engine_frames must be a non-negative integer")
        self.engine_frame = _validate_int64(
            self.engine_frame + engine_frames, name="engine_frame"
        )
        if self.playing:
            self.session_frame = _validate_int64(
                self.session_frame + engine_frames, name="session_frame"
            )

    def set_tempo(self, bpm: TempoValue) -> int:
        if self.playing:
            effective_quarter = self.tempo_map.next_bar_start_quarter(
                self.session_frame
            )
            segment = self.tempo_map.add_tempo_change_at_quarter(
                effective_quarter=effective_quarter,
                bpm=bpm,
            )
        else:
            segment = self.tempo_map.add_tempo_change_at_frame(
                effective_frame=self.session_frame,
                bpm=bpm,
            )
        return segment.start_frame


def compute_sync_playback_rate(
    master_bpm: float,
    source_bpm: float,
    sync_enabled: bool,
) -> tuple[float, str]:
    """Compute the sync playback rate for a voice.

    Parameters
    ----------
    master_bpm : float
        The current session / master tempo in BPM.
    source_bpm : float
        The original BPM of the sample/voice.
    sync_enabled : bool
        Whether the global SYNC flag is active.

    Returns
    -------
    rate : float
        The playback rate to apply. Always >= 0. Returns 1.0 when
        sync is off or source BPM is invalid.
    status : str
        One of: ``"sync"``, ``"tempo_only"``, ``"not_syncable"``.
        Indicates whether the voice can be synchronised and why.
    """
    # --- Invalid or missing source BPM ---
    try:
        s_bpm = float(source_bpm)
    except (TypeError, ValueError):
        return 1.0, "not_syncable"
    if not s_bpm or s_bpm != s_bpm:  # includes 0 and NaN
        return 1.0, "not_syncable"

    # --- SYNC off → original speed ---
    if not sync_enabled:
        return 1.0, "sync"

    # --- SYNC on with valid source BPM ---
    rate = master_bpm / s_bpm

    # Clamp to reasonable range to avoid extreme rate jumps
    # (extreme rates are treated as not_syncable per #323 spec)
    if rate <= 0 or rate > 4.0 or rate < 0.25:
        return 1.0, "not_syncable"

    # Determine sync status kind
    # If rate is exactly 1.0 the sample already matches master tempo
    if rate == 1.0:
        return 1.0, "sync"

    return rate, "sync"


def schedule_events_in_buffer(
    *,
    buffer_start_frame: int,
    frame_count: int,
    event_frames: Iterable[int],
) -> tuple[BufferScheduledEvent, ...]:
    """Return absolute events and offsets for one half-open audio buffer."""

    _validate_int64(buffer_start_frame, name="buffer_start_frame")
    if (
        not isinstance(frame_count, int)
        or isinstance(frame_count, bool)
        or frame_count <= 0
    ):
        raise ValueError("frame_count must be a positive integer")

    buffer_end = buffer_start_frame + frame_count
    if buffer_end - 1 > INT64_MAX:
        raise OverflowError("buffer end outside signed int64 range")

    scheduled: list[BufferScheduledEvent] = []
    for event_frame in event_frames:
        _validate_int64(event_frame, name="event_frame")
        if buffer_start_frame <= event_frame < buffer_end:
            scheduled.append(
                BufferScheduledEvent(
                    event_frame=event_frame,
                    offset=event_frame - buffer_start_frame,
                )
            )
    return tuple(scheduled)
