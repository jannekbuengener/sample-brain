"""R&D Slice 4 (#680/#888): source-relative gesture seconds → exact quarter notes.

Maps measured ``GestureAnalysis`` onset times into pattern-local quarter-note
``Fraction`` positions under an explicit caller ``reference_bpm``.

Does not create Pattern / Channel / Trigger objects, infer BPM, snap timing, or
read session/global tempo. See ``docs/GESTURE_TIMING_PROJECTION_RND_SLICE4.md``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction

from .gesture_analysis import GestureAnalysis, GestureEvent

_ALLOWED_EMPTY_STATUSES = frozenset({"empty", "too_short", "unreadable"})
_ALLOWED_STATUSES = frozenset({"ok"}) | _ALLOWED_EMPTY_STATUSES


@dataclass(frozen=True)
class ProjectedGestureEvent:
    """One source onset projected into an exact quarter-note position."""

    source_onset_sec: float
    quarter_position: Fraction
    cluster_id: int


@dataclass(frozen=True)
class GestureTimingProjection:
    """Immutable timing projection for one gesture analysis + reference BPM."""

    events: tuple[ProjectedGestureEvent, ...]
    reference_bpm: Fraction
    projected_duration_quarters: Fraction


def _coerce_reference_bpm(reference_bpm: object) -> Fraction:
    """Coerce public BPM inputs; reject bool before int; require finite then > 0."""
    if isinstance(reference_bpm, bool):
        raise TypeError("reference_bpm must be int, float, str, or Fraction")
    if isinstance(reference_bpm, Fraction):
        bpm = reference_bpm
    elif isinstance(reference_bpm, int):
        bpm = Fraction(reference_bpm, 1)
    elif isinstance(reference_bpm, str):
        try:
            bpm = Fraction(reference_bpm)
        except (ValueError, ZeroDivisionError) as exc:
            raise ValueError(f"reference_bpm string is malformed: {reference_bpm!r}") from exc
    elif isinstance(reference_bpm, float):
        if not math.isfinite(reference_bpm):
            raise ValueError("reference_bpm must be finite")
        bpm = Fraction(str(reference_bpm))
    else:
        raise TypeError("reference_bpm must be int, float, str, or Fraction")
    if bpm <= 0:
        raise ValueError("reference_bpm must be positive")
    return bpm


def _require_non_negative_finite_seconds(value: object, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a real number")
    seconds = float(value)
    if not math.isfinite(seconds):
        raise ValueError(f"{name} must be finite")
    if seconds < 0.0:
        raise ValueError(f"{name} must be >= 0")
    return seconds


def _seconds_to_quarters(seconds: float, bpm: Fraction) -> Fraction:
    """Strategy A: Fraction(str(seconds)) * bpm / 60."""
    return Fraction(str(seconds)) * bpm / Fraction(60, 1)


def _validate_sample_rate(sample_rate: object) -> int:
    if isinstance(sample_rate, bool) or not isinstance(sample_rate, int):
        raise TypeError("sample_rate must be a positive int")
    if sample_rate <= 0:
        raise ValueError("sample_rate must be a positive int")
    return sample_rate


def _validate_analysis_structure(analysis: GestureAnalysis) -> tuple[float, str]:
    if not isinstance(analysis, GestureAnalysis):
        raise TypeError("analysis must be a GestureAnalysis")
    _validate_sample_rate(analysis.sample_rate)
    duration_sec = _require_non_negative_finite_seconds(
        analysis.duration_sec, name="duration_sec"
    )
    status = analysis.status
    if not isinstance(status, str) or status not in _ALLOWED_STATUSES:
        raise ValueError(f"unsupported analysis status: {status!r}")
    events = analysis.events
    if not isinstance(events, tuple):
        raise TypeError("analysis.events must be a tuple")
    if status == "ok":
        if not events:
            raise ValueError("status 'ok' requires at least one event")
    elif events:
        raise ValueError(f"status {status!r} must not contain events")
    return duration_sec, status


def _validate_event_onset(
    event: GestureEvent,
    *,
    duration_sec: float,
    previous_onset: float | None,
) -> float:
    if not isinstance(event, GestureEvent):
        raise TypeError("analysis.events entries must be GestureEvent")
    onset = _require_non_negative_finite_seconds(
        event.onset_time_sec, name="onset_time_sec"
    )
    if onset > duration_sec:
        raise ValueError("onset_time_sec must be <= duration_sec")
    if previous_onset is not None and onset <= previous_onset:
        raise ValueError("onset_time_sec must be strictly increasing")
    if not isinstance(event.cluster_id, int) or isinstance(event.cluster_id, bool):
        raise TypeError("cluster_id must be an int")
    return onset


def project_gesture_timing(
    analysis: GestureAnalysis,
    reference_bpm: int | float | str | Fraction,
) -> GestureTimingProjection:
    """Project source-relative gesture seconds into exact quarter-note Fractions.

    ``reference_bpm`` is the sole tempo authority for this call. Source ``t=0``
    maps to quarter ``0`` (leading silence preserved; no first-onset shift).
    Mapping uses exact Strategy A: ``Fraction(str(sec)) * bpm / 60``.
    """
    bpm = _coerce_reference_bpm(reference_bpm)
    duration_sec, _status = _validate_analysis_structure(analysis)

    projected_events: list[ProjectedGestureEvent] = []
    previous_onset: float | None = None
    for event in analysis.events:
        onset = _validate_event_onset(
            event, duration_sec=duration_sec, previous_onset=previous_onset
        )
        projected_events.append(
            ProjectedGestureEvent(
                source_onset_sec=onset,
                quarter_position=_seconds_to_quarters(onset, bpm),
                cluster_id=int(event.cluster_id),
            )
        )
        previous_onset = onset

    return GestureTimingProjection(
        events=tuple(projected_events),
        reference_bpm=bpm,
        projected_duration_quarters=_seconds_to_quarters(duration_sec, bpm),
    )
