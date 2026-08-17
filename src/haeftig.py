"""Deterministic 16-bar HÄFTIG selection on an authoritative source grid.

HÄFTIG is a source-content marker.  It never derives bar boundaries from BPM,
seconds, GUI timers, session tempo, or playback mode.  Callers must provide a
reliable ordered source-downbeat sequence as integer source frames.
"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from typing import Literal, Sequence

HAEFTIG_REGION_TYPE = "HÄFTIG"
HAEFTIG_BAR_COUNT = 16

HaeftigSelectionStatus = Literal["ok", "unavailable"]
HaeftigUnavailableReason = Literal[
    "GRID_UNRELIABLE",
    "INVALID_GRID",
    "INVALID_TRIGGER",
    "INVALID_SOURCE_REF",
    "TRIGGER_OUT_OF_RANGE",
    "INSUFFICIENT_BARS",
]


@dataclass(frozen=True)
class HaeftigRegion:
    """One source-stable HÄFTIG region using half-open frame boundaries."""

    region_type: Literal["HÄFTIG"]
    source_ref: str
    source_start_frame: int
    source_end_frame_exclusive: int
    source_start_bar_index: int
    source_end_bar_index_exclusive: int
    trigger_source_frame: int
    trigger_session_frame: int | None = None
    grid_source_ref: str | None = None

    def __post_init__(self) -> None:
        if self.region_type != HAEFTIG_REGION_TYPE:
            raise ValueError("HÄFTIG is the only supported manual region type")
        if not self.source_ref.strip():
            raise ValueError("source_ref must be non-empty")
        if self.source_start_frame < 0:
            raise ValueError("source_start_frame must be non-negative")
        if self.source_end_frame_exclusive <= self.source_start_frame:
            raise ValueError("source_end_frame_exclusive must be after start")
        if self.source_start_bar_index < 0:
            raise ValueError("source_start_bar_index must be non-negative")
        if (
            self.source_end_bar_index_exclusive - self.source_start_bar_index
            != HAEFTIG_BAR_COUNT
        ):
            raise ValueError("HÄFTIG must contain exactly 16 source bars")

    @property
    def frame_count(self) -> int:
        return self.source_end_frame_exclusive - self.source_start_frame

    @property
    def identity(self) -> tuple[str, int, int, str]:
        """Stable dedupe identity; trigger context is intentionally excluded."""
        return (
            self.source_ref,
            self.source_start_frame,
            self.source_end_frame_exclusive,
            self.region_type,
        )


@dataclass(frozen=True)
class HaeftigSelection:
    status: HaeftigSelectionStatus
    region: HaeftigRegion | None = None
    reason_code: HaeftigUnavailableReason | None = None

    def __post_init__(self) -> None:
        if self.status == "ok":
            if self.region is None or self.reason_code is not None:
                raise ValueError("ok selection requires region and no reason_code")
        elif self.region is not None or self.reason_code is None:
            raise ValueError("unavailable selection requires reason_code and no region")


def _unavailable(reason: HaeftigUnavailableReason) -> HaeftigSelection:
    return HaeftigSelection(status="unavailable", reason_code=reason)


def _valid_frame(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _normalize_downbeats(values: Sequence[int]) -> tuple[int, ...] | None:
    frames = tuple(values)
    if not frames:
        return ()
    if any(not _valid_frame(frame) for frame in frames):
        return None
    if any(right <= left for left, right in zip(frames, frames[1:])):
        return None
    return frames


def select_haeftig_region(
    *,
    downbeat_frames: Sequence[int],
    trigger_source_frame: int,
    source_ref: str,
    grid_reliable: bool,
    trigger_session_frame: int | None = None,
    grid_source_ref: str | None = None,
) -> HaeftigSelection:
    """Select the exact 16 source bars ending at the trigger's context boundary.

    Exact-downbeat case:
        trigger == downbeat[j] -> [downbeat[j-16], downbeat[j])

    Mid-bar case:
        downbeat[j] < trigger < downbeat[j+1]
        -> [downbeat[j-15], downbeat[j+1])

    Both cases are the same index operation: choose the first downbeat greater
    than or equal to the trigger as the exclusive end boundary, then step back
    exactly 16 source-bar intervals.
    """
    if not grid_reliable:
        return _unavailable("GRID_UNRELIABLE")
    if not isinstance(source_ref, str) or not source_ref.strip():
        return _unavailable("INVALID_SOURCE_REF")
    if not _valid_frame(trigger_source_frame):
        return _unavailable("INVALID_TRIGGER")
    if trigger_session_frame is not None and not _valid_frame(trigger_session_frame):
        return _unavailable("INVALID_TRIGGER")

    downbeats = _normalize_downbeats(downbeat_frames)
    if downbeats is None:
        return _unavailable("INVALID_GRID")
    if not downbeats:
        return _unavailable("GRID_UNRELIABLE")
    if trigger_source_frame < downbeats[0] or trigger_source_frame > downbeats[-1]:
        return _unavailable("TRIGGER_OUT_OF_RANGE")

    end_bar_index = bisect_left(downbeats, trigger_source_frame)
    if end_bar_index >= len(downbeats):
        return _unavailable("TRIGGER_OUT_OF_RANGE")
    if end_bar_index < HAEFTIG_BAR_COUNT:
        return _unavailable("INSUFFICIENT_BARS")

    start_bar_index = end_bar_index - HAEFTIG_BAR_COUNT
    region = HaeftigRegion(
        region_type=HAEFTIG_REGION_TYPE,
        source_ref=source_ref,
        source_start_frame=downbeats[start_bar_index],
        source_end_frame_exclusive=downbeats[end_bar_index],
        source_start_bar_index=start_bar_index,
        source_end_bar_index_exclusive=end_bar_index,
        trigger_source_frame=trigger_source_frame,
        trigger_session_frame=trigger_session_frame,
        grid_source_ref=grid_source_ref,
    )
    return HaeftigSelection(status="ok", region=region)


def add_haeftig_region(
    existing: Sequence[HaeftigRegion],
    candidate: HaeftigRegion,
) -> tuple[tuple[HaeftigRegion, ...], bool]:
    """Append a new region unless its source-boundary identity already exists.

    Overlap is intentionally allowed. Only an identical source/start/end/type
    region is deduplicated.
    """
    current = tuple(existing)
    if any(region.identity == candidate.identity for region in current):
        return current, False
    return (*current, candidate), True


__all__ = [
    "HAEFTIG_BAR_COUNT",
    "HAEFTIG_REGION_TYPE",
    "HaeftigRegion",
    "HaeftigSelection",
    "add_haeftig_region",
    "select_haeftig_region",
]
