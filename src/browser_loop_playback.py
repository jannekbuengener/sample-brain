"""Persistent Browser Loop playback role (#1284).

Owns exactly one Loop owner on the shared Workbench transport. Transient
Browser audition remains :class:`TransportAwarePreview`. Musical time authority
stays on :class:`SessionTransport` / :class:`TempoMap`; this module never
introduces a Browser-private clock.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np

from . import native_audio
from .native_pcm_decode import decode_native_pcm
from .session_grid import MusicalPosition, compute_sync_playback_rate
from .workbench_controller import WorkbenchRow
from .workbench_editing import (
    audio_source_frame_info,
    load_source_downbeats,
    source_edit_grid_from_details,
)
from .workbench_transport_adapter import WorkbenchTransportAdapter

DECLICK_FRAMES = 32

PcmSpanLoadFn = Callable[..., tuple[np.ndarray, int]]


@dataclass(frozen=True)
class BrowserLoopExtent:
    """Reliable musical Loop span from real downbeats ``d[0..k]``."""

    source_start_frame: int
    source_end_frame_exclusive: int
    bar_count: int
    downbeat_frames: tuple[int, ...]


@dataclass(frozen=True)
class BrowserLoopResult:
    ok: bool
    message: str = ""
    owner_path: str | None = None
    bar_count: int | None = None
    reason_code: str | None = None


@dataclass(frozen=True)
class _PreparedLoop:
    row: WorkbenchRow
    extent: BrowserLoopExtent
    pcm: np.ndarray
    channels: int
    source_bpm: float | None


def browser_loop_extent_from_downbeats(
    downbeat_frames: Sequence[int],
) -> BrowserLoopExtent | None:
    """Return full reliable span or ``None`` when Loop is unavailable.

    Requires at least two strictly increasing non-negative integer frames.
    ``bar_count = len(d) - 1`` with ``end_exclusive = d[-1]``.
    """
    if not isinstance(downbeat_frames, Sequence) or isinstance(downbeat_frames, (str, bytes)):
        return None
    frames: list[int] = []
    previous: int | None = None
    for raw in downbeat_frames:
        if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
            return None
        if previous is not None and raw <= previous:
            return None
        frames.append(int(raw))
        previous = int(raw)
    if len(frames) < 2:
        return None
    return BrowserLoopExtent(
        source_start_frame=frames[0],
        source_end_frame_exclusive=frames[-1],
        bar_count=len(frames) - 1,
        downbeat_frames=tuple(frames),
    )


def map_comparison_phase_to_source_frame(
    *,
    master_bar: int,
    master_beat: int,
    master_beat_fraction: Fraction | float,
    beats_per_bar: int,
    loop_bar_count: int,
    audition_bar_count: int,
    downbeat_frames: Sequence[int],
) -> int:
    """Map MASTER comparison phase into a source frame inside ``downbeat_frames``.

    ``comparison_bar = master_bar % L``; ``source_bar = comparison_bar % A``.
    Fractional within-bar phase interpolates between the two real downbeats of
    that source bar.
    """
    if loop_bar_count <= 0 or audition_bar_count <= 0:
        raise ValueError("bar counts must be positive")
    if beats_per_bar <= 0:
        raise ValueError("beats_per_bar must be positive")
    downbeats = tuple(int(v) for v in downbeat_frames)
    if len(downbeats) < audition_bar_count + 1:
        raise ValueError("downbeat_frames must cover audition_bar_count bars")

    comparison_bar = int(master_bar) % int(loop_bar_count)
    source_bar = comparison_bar % int(audition_bar_count)
    frac = Fraction(master_beat_fraction)
    within = (Fraction(int(master_beat), 1) + frac) / Fraction(int(beats_per_bar), 1)
    if within < 0:
        within = Fraction(0, 1)
    if within >= 1:
        within = Fraction(1, 1) - Fraction(1, 10_000_000)

    start = downbeats[source_bar]
    end = downbeats[source_bar + 1]
    span = end - start
    offset = int(round(Fraction(span, 1) * within))
    frame = start + offset
    if frame >= end:
        frame = end - 1
    return max(start, frame)


def _scale_source_frame_to_engine(
    source_frame: int, *, source_rate: int, engine_rate: int
) -> int:
    """Map a source/analysis frame index into decoded engine-rate PCM frames."""
    if source_rate <= 0 or engine_rate <= 0:
        raise ValueError("sample rates must be positive")
    if source_rate == engine_rate:
        return int(source_frame)
    return int(round(int(source_frame) * float(engine_rate) / float(source_rate)))


def _load_pcm_span(
    path: Path,
    *,
    sample_rate: int,
    start_frame: int,
    end_frame_exclusive: int,
) -> tuple[np.ndarray, int]:
    """Decode then slice a half-open source-frame span at the engine rate.

    Downbeat indices are in the file's source/analysis timebase; convert them
    into decoded PCM frames when ``sample_rate`` differs from the source rate.
    """
    try:
        _total, source_rate = audio_source_frame_info(path)
    except Exception:
        source_rate = int(sample_rate)
    engine_start = _scale_source_frame_to_engine(
        int(start_frame), source_rate=source_rate, engine_rate=int(sample_rate)
    )
    engine_end = _scale_source_frame_to_engine(
        int(end_frame_exclusive), source_rate=source_rate, engine_rate=int(sample_rate)
    )
    pcm, channels = decode_native_pcm(path, sample_rate=sample_rate, start_ms=0)
    start = max(0, int(engine_start))
    end = max(start + 1, int(engine_end))
    if start >= pcm.shape[0]:
        raise ValueError("Loop start liegt außerhalb der Audiodatei.")
    end = min(end, int(pcm.shape[0]))
    if end <= start:
        raise ValueError("Loop-Span ist leer.")
    return np.ascontiguousarray(pcm[start:end], dtype=np.float32), int(channels)


def extent_from_row(row: WorkbenchRow) -> BrowserLoopExtent | None:
    """Resolve Loop extent from ``WorkbenchRow.details`` downbeats only."""
    details: Mapping[str, object]
    raw = getattr(row, "details", None)
    if isinstance(raw, Mapping):
        details = raw
    else:
        details = {}
    frames, ok, _ref = load_source_downbeats(row.path, details=details)
    if not ok:
        grid = source_edit_grid_from_details(details)
        frames = tuple(grid.bar_frames)
    return browser_loop_extent_from_downbeats(frames)


class BrowserLoopOwner:
    """Exactly one persistent Browser Loop role on a shared transport."""

    def __init__(
        self,
        transport: WorkbenchTransportAdapter,
        *,
        pcm_load_fn: PcmSpanLoadFn | None = None,
        allocate_voice_id: Callable[[], int] | None = None,
    ) -> None:
        self._transport = transport
        self._pcm_load_fn = pcm_load_fn or _load_pcm_span
        self._allocate_voice_id = allocate_voice_id
        self._next_voice_id = 10_000
        self._owner_row: WorkbenchRow | None = None
        self._extent: BrowserLoopExtent | None = None
        self._pcm: np.ndarray | None = None
        self._pcm_channels: int = 1
        self._source_bpm: float | None = None
        self._active_voice_ids: list[int] = []
        self._sounding_voice_id: int | None = None
        self._scheduled_voice_id: int | None = None
        self._next_cycle_index: int = 0
        self._cycle_anchor_engine_frame: int | None = None
        self._cycle_duration_frames: int | None = None
        self._first_cycle_duration_frames: int | None = None
        self._source_phase_frame: int = 0
        self._reduced_capability_reason: str | None = None
        self._pcm_start_offset: int = 0  # one-shot sliced PCM for next create_voice
        self._phase_entry_pcm_offset: int = 0  # retained for source-phase tracking

    @property
    def is_active(self) -> bool:
        return self._owner_row is not None and self._extent is not None

    @property
    def owner_row(self) -> WorkbenchRow | None:
        return self._owner_row

    @property
    def extent(self) -> BrowserLoopExtent | None:
        return self._extent

    @property
    def active_voice_ids(self) -> tuple[int, ...]:
        return tuple(self._active_voice_ids)

    @property
    def reduced_capability_reason(self) -> str | None:
        return self._reduced_capability_reason

    def declick_frames(self) -> int:
        return DECLICK_FRAMES

    def current_source_phase_frame(self) -> int | None:
        if not self.is_active:
            return None
        return int(self._source_phase_frame)

    def comparison_cycle_frames(self) -> int | None:
        if self._extent is None:
            return None
        if not self._transport.is_sync_enabled():
            if self._pcm is None:
                return None
            return int(self._pcm.shape[0])
        return self._master_bars_to_frames(self._extent.bar_count)

    def validate_row(self, row: WorkbenchRow) -> BrowserLoopResult:
        extent = extent_from_row(row)
        if extent is None:
            return BrowserLoopResult(
                ok=False,
                message="LOOP unavailable: no reliable downbeat span.",
                reason_code="NO_DOWNBEATS",
            )
        if not self._transport.is_native_available():
            return BrowserLoopResult(
                ok=False,
                message="LOOP unavailable: native audio missing.",
                reason_code="NATIVE_UNAVAILABLE",
            )
        sync_enabled = self._transport.is_sync_enabled()
        source_bpm = row.bpm
        rate, status = compute_sync_playback_rate(
            self._transport.get_current_tempo(),
            source_bpm if source_bpm is not None else float("nan"),
            sync_enabled,
        )
        if sync_enabled and status != "sync":
            return BrowserLoopResult(
                ok=False,
                message="SYNC Loop unavailable: invalid or missing source BPM.",
                reason_code="SYNC_NOT_SYNCABLE",
            )
        return BrowserLoopResult(
            ok=True,
            owner_path=str(row.path),
            bar_count=extent.bar_count,
        )

    def loop_on(self, row: WorkbenchRow) -> BrowserLoopResult:
        """Validate/prepare first; only then replace any existing owner atomically."""
        prepared = self._prepare(row)
        if isinstance(prepared, BrowserLoopResult):
            return prepared
        data = prepared
        self._stop_loop_voices()
        self._owner_row = data.row
        self._extent = data.extent
        self._pcm = data.pcm
        self._pcm_channels = data.channels
        self._source_bpm = data.source_bpm
        self._reduced_capability_reason = None
        self._pcm_start_offset = 0
        self._source_phase_frame = int(self._extent.source_start_frame)
        self._next_cycle_index = 0
        self._cycle_anchor_engine_frame = None
        self._cycle_duration_frames = self._compute_cycle_duration()
        self._first_cycle_duration_frames = None
        if not self._transport.ensure_engine_running():
            self._clear_owner_state()
            return BrowserLoopResult(
                ok=False,
                message="LOOP unavailable: native engine failed to start.",
                reason_code="NATIVE_UNAVAILABLE",
            )
        self._transport.play()
        # SYNC ON mid-cycle: enter at current MASTER comparison phase (not source 0).
        if self._transport.is_sync_enabled():
            self._arm_phase_entry_at_current_master()
        self.tick()
        return BrowserLoopResult(
            ok=True,
            owner_path=str(row.path),
            bar_count=self._extent.bar_count if self._extent else None,
        )

    def loop_off(self) -> BrowserLoopResult:
        self._stop_loop_voices()
        self._clear_owner_state()
        return BrowserLoopResult(ok=True, message="LOOP OFF")

    def tick(self, *, engine_frame: int | None = None) -> None:
        if not self.is_active or self._pcm is None or self._extent is None:
            return
        if self._reduced_capability_reason is not None:
            return
        engine = self._transport.get_native_engine()
        if engine is None:
            return
        if engine_frame is None:
            engine_frame = int(self._transport.get_engine_frame())
        else:
            engine_frame = int(engine_frame)

        if self._cycle_duration_frames is None or self._cycle_duration_frames <= 0:
            self._cycle_duration_frames = self._compute_cycle_duration()
        steady = int(self._cycle_duration_frames or 0)
        if steady <= 0:
            return
        if self._first_cycle_duration_frames is None:
            self._first_cycle_duration_frames = steady

        if self._cycle_anchor_engine_frame is None:
            if self._transport.is_sync_enabled() and self._pcm_start_offset <= 0:
                # Align to comparison-cycle start only when entering at phase 0.
                self._cycle_anchor_engine_frame = self._sync_cycle_anchor(engine_frame)
            else:
                self._cycle_anchor_engine_frame = engine_frame
            self._next_cycle_index = 0

        # Reclaim finished sounding voice once a newer one is past its start.
        self._reclaim_finished(engine_frame)

        # Schedule current + next cycle within a small lookahead.
        lookahead = steady
        while True:
            start = self._cycle_start_engine_frame(self._next_cycle_index)
            cycle_len = self._cycle_duration_for_index(self._next_cycle_index)
            if start > engine_frame + lookahead:
                break
            if start + cycle_len <= engine_frame and self._next_cycle_index > 0:
                self._next_cycle_index += 1
                continue
            if self._scheduled_voice_id is not None and start > engine_frame:
                break
            self._schedule_cycle_voice(engine, start_engine_frame=start)
            self._next_cycle_index += 1
            if start >= engine_frame:
                # Keep one future voice scheduled.
                if self._scheduled_voice_id is not None:
                    break

        # Track nominal source phase for ON→OFF continuity (extent-relative).
        if self._cycle_anchor_engine_frame is not None and steady > 0:
            self._source_phase_frame = self._estimate_source_phase(engine_frame)

    def on_sync_changed(self, *, enabled: bool) -> None:
        if not self.is_active or self._extent is None or self._pcm is None:
            return
        if enabled:
            rate, status = compute_sync_playback_rate(
                self._transport.get_current_tempo(),
                self._source_bpm if self._source_bpm is not None else float("nan"),
                True,
            )
            if status != "sync":
                self._fail_closed_audio("SYNC_NOT_SYNCABLE")
                return
            # OFF→ON: re-anchor at current MASTER comparison phase.
            try:
                engine_frame = int(self._transport.get_engine_frame())
            except Exception:
                engine_frame = 0
            native = self._transport.get_native_engine()
            if native is not None and hasattr(native, "snapshot"):
                try:
                    engine_frame = int(native.snapshot().engine_frame)
                except Exception:
                    pass
            self._stop_loop_voices()
            self._arm_phase_entry_at_current_master(engine_frame=engine_frame)
            self._reduced_capability_reason = None
            self.tick(engine_frame=engine_frame)
            return

        # ON→OFF: keep current source phase; continue at rate 1.0.
        phase = self.current_source_phase_frame()
        engine_frame = int(self._transport.get_engine_frame())
        if phase is not None:
            self._source_phase_frame = phase
            # Convert retained source phase into engine-rate PCM offset.
            try:
                _total, source_rate = audio_source_frame_info(self._owner_row.path)
            except Exception:
                source_rate = int(self._transport.tempo_map.sample_rate)
            engine_rate = int(self._transport.tempo_map.sample_rate)
            mapped_engine = _scale_source_frame_to_engine(
                int(phase), source_rate=source_rate, engine_rate=engine_rate
            )
            start_engine = _scale_source_frame_to_engine(
                int(self._extent.source_start_frame),
                source_rate=source_rate,
                engine_rate=engine_rate,
            )
            offset = max(0, mapped_engine - start_engine)
            self._pcm_start_offset = offset
            self._phase_entry_pcm_offset = offset
        self._stop_loop_voices()
        self._cycle_anchor_engine_frame = engine_frame
        self._next_cycle_index = 0
        self._cycle_duration_frames = self._compute_cycle_duration()
        # Shortened first pass until remainder ends, then full source cycles.
        pcm_len = int(self._pcm.shape[0]) if self._pcm is not None else 0
        remaining_pcm = max(1, pcm_len - int(self._phase_entry_pcm_offset))
        rate = self._current_rate()
        self._first_cycle_duration_frames = max(
            1, int(math.ceil(remaining_pcm / max(rate, 1e-9)))
        )
        self._reduced_capability_reason = None
        self.tick(engine_frame=engine_frame)

    def on_master_bpm_changed(self) -> None:
        if not self.is_active or not self._transport.is_sync_enabled():
            return
        if self._reduced_capability_reason is not None:
            return
        rate, status = compute_sync_playback_rate(
            self._transport.get_current_tempo(),
            self._source_bpm if self._source_bpm is not None else float("nan"),
            True,
        )
        if status != "sync":
            self._fail_closed_audio("SYNC_NOT_SYNCABLE")
            return
        engine = self._transport.get_native_engine()
        if engine is None:
            return
        for voice_id in list(self._active_voice_ids):
            try:
                engine.set_voice_rate(voice_id, rate)
            except Exception:
                continue
        # Reconcile queued cycle boundaries against the updated TempoMap.
        self._reschedule_after_tempo_change()

    def comparison_source_frame_for_row(
        self, row: WorkbenchRow, *, session_frame: int | None = None
    ) -> int | None:
        if not self.is_active or self._extent is None:
            return None
        if not self._transport.is_sync_enabled():
            return None
        audition_extent = extent_from_row(row)
        if audition_extent is None:
            return None
        if session_frame is None:
            session_frame = int(self._transport.get_session_frame())
        pos = self._transport.tempo_map.frame_to_bar_beat(int(session_frame))
        beats_per_bar = int(self._transport.tempo_map.time_signature.numerator)
        try:
            return map_comparison_phase_to_source_frame(
                master_bar=int(pos.bar),
                master_beat=int(pos.beat),
                master_beat_fraction=pos.beat_fraction,
                beats_per_bar=beats_per_bar,
                loop_bar_count=int(self._extent.bar_count),
                audition_bar_count=int(audition_extent.bar_count),
                downbeat_frames=audition_extent.downbeat_frames,
            )
        except ValueError:
            return None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _prepare(self, row: WorkbenchRow) -> BrowserLoopResult | _PreparedLoop:
        base = self.validate_row(row)
        if not base.ok:
            return base
        extent = extent_from_row(row)
        assert extent is not None
        try:
            pcm, channels = self._pcm_load_fn(
                Path(row.path),
                sample_rate=int(self._transport.tempo_map.sample_rate),
                start_frame=extent.source_start_frame,
                end_frame_exclusive=extent.source_end_frame_exclusive,
            )
        except Exception as exc:
            return BrowserLoopResult(
                ok=False,
                message=f"LOOP prepare failed: {exc}",
                reason_code="PCM_LOAD_FAILED",
            )
        if pcm.size == 0:
            return BrowserLoopResult(
                ok=False,
                message="LOOP prepare failed: empty PCM span.",
                reason_code="PCM_LOAD_FAILED",
            )
        return _PreparedLoop(
            row=row,
            extent=extent,
            pcm=pcm,
            channels=channels,
            source_bpm=row.bpm,
        )

    def _clear_owner_state(self) -> None:
        self._owner_row = None
        self._extent = None
        self._pcm = None
        self._pcm_channels = 1
        self._source_bpm = None
        self._active_voice_ids = []
        self._sounding_voice_id = None
        self._scheduled_voice_id = None
        self._next_cycle_index = 0
        self._cycle_anchor_engine_frame = None
        self._cycle_duration_frames = None
        self._first_cycle_duration_frames = None
        self._source_phase_frame = 0
        self._pcm_start_offset = 0
        self._phase_entry_pcm_offset = 0
        self._reduced_capability_reason = None

    def _arm_phase_entry_at_current_master(
        self, *, engine_frame: int | None = None
    ) -> None:
        """Enter at current MASTER comparison phase with a shortened first cycle."""
        assert self._extent is not None
        session_frame = int(self._transport.get_session_frame())
        if engine_frame is None:
            try:
                engine_frame = int(self._transport.get_engine_frame())
            except Exception:
                engine_frame = 0
            native = self._transport.get_native_engine()
            if native is not None and hasattr(native, "snapshot"):
                try:
                    engine_frame = int(native.snapshot().engine_frame)
                except Exception:
                    pass
        mapped = self._map_session_to_extent_frame(session_frame)
        # Map comparison phase into engine-rate PCM offset within the Loop span.
        # Extent downbeats are source-timebase; PCM buffer is already engine-rate.
        try:
            _total, source_rate = audio_source_frame_info(self._owner_row.path)
        except Exception:
            source_rate = int(self._transport.tempo_map.sample_rate)
        engine_rate = int(self._transport.tempo_map.sample_rate)
        mapped_engine = _scale_source_frame_to_engine(
            mapped, source_rate=source_rate, engine_rate=engine_rate
        )
        start_engine = _scale_source_frame_to_engine(
            int(self._extent.source_start_frame),
            source_rate=source_rate,
            engine_rate=engine_rate,
        )
        offset = max(0, mapped_engine - start_engine)
        self._pcm_start_offset = offset
        self._phase_entry_pcm_offset = offset
        self._source_phase_frame = mapped
        steady = self._compute_cycle_duration()
        self._cycle_duration_frames = steady
        # Remaining MASTER comparison-cycle frames until the next L-bar boundary.
        pos = self._transport.tempo_map.frame_to_bar_beat(session_frame)
        l_bars = int(self._extent.bar_count)
        cycle_start_bar = (int(pos.bar) // l_bars) * l_bars
        cycle_start_session = self._transport.tempo_map.bar_beat_to_frame(
            MusicalPosition(bar=cycle_start_bar, beat=0)
        )
        into = max(0, int(session_frame) - int(cycle_start_session))
        remaining = max(1, int(steady) - int(into))
        self._first_cycle_duration_frames = remaining
        self._cycle_anchor_engine_frame = int(engine_frame)
        self._next_cycle_index = 0

    def _cycle_duration_for_index(self, index: int) -> int:
        steady = int(self._cycle_duration_frames or 0)
        first = int(self._first_cycle_duration_frames or steady)
        if index <= 0:
            return max(1, first)
        return max(1, steady)

    def _cycle_start_engine_frame(self, index: int) -> int:
        anchor = int(self._cycle_anchor_engine_frame or 0)
        if index <= 0:
            return anchor
        first = self._cycle_duration_for_index(0)
        steady = self._cycle_duration_for_index(1)
        return anchor + first + (index - 1) * steady

    def _estimate_source_phase(self, engine_frame: int) -> int:
        assert self._extent is not None
        assert self._pcm is not None
        anchor = int(self._cycle_anchor_engine_frame or 0)
        elapsed = max(0, int(engine_frame) - anchor)
        first = self._cycle_duration_for_index(0)
        steady = self._cycle_duration_for_index(1)
        if elapsed < first:
            into = elapsed
            pcm_offset = int(self._phase_entry_pcm_offset)
        else:
            into = (elapsed - first) % steady
            pcm_offset = 0
        rate = self._current_rate()
        pcm_pos = int(round(into * rate)) + pcm_offset
        pcm_len = int(self._pcm.shape[0])
        if pcm_len > 0:
            pcm_pos %= pcm_len
        return int(self._extent.source_start_frame) + pcm_pos

    def _fail_closed_audio(self, reason: str) -> None:
        self._stop_loop_voices()
        self._reduced_capability_reason = reason
        self._cycle_anchor_engine_frame = None
        self._cycle_duration_frames = None
        self._next_cycle_index = 0

    def _current_rate(self) -> float:
        rate, _status = compute_sync_playback_rate(
            self._transport.get_current_tempo(),
            self._source_bpm if self._source_bpm is not None else float("nan"),
            self._transport.is_sync_enabled(),
        )
        return float(rate)

    def _compute_cycle_duration(self) -> int:
        if self._extent is None or self._pcm is None:
            return 0
        if self._transport.is_sync_enabled():
            return max(1, self._master_bars_to_frames(self._extent.bar_count))
        rate = self._current_rate()
        return max(1, int(math.ceil(int(self._pcm.shape[0]) / rate)))

    def _master_bars_to_frames(self, bar_count: int) -> int:
        tempo_map = self._transport.tempo_map
        start = tempo_map.bar_beat_to_frame(MusicalPosition(bar=0, beat=0))
        end = tempo_map.bar_beat_to_frame(MusicalPosition(bar=int(bar_count), beat=0))
        return max(1, int(end) - int(start))

    def _sync_cycle_anchor(self, engine_frame: int) -> int:
        """Align cycle index 0 to the start of the current comparison cycle."""
        assert self._extent is not None
        session_frame = int(self._transport.get_session_frame())
        pos = self._transport.tempo_map.frame_to_bar_beat(session_frame)
        l_bars = int(self._extent.bar_count)
        cycle_start_bar = (int(pos.bar) // l_bars) * l_bars
        cycle_start_session = self._transport.tempo_map.bar_beat_to_frame(
            MusicalPosition(bar=cycle_start_bar, beat=0)
        )
        # Map session→engine by assuming they share the same relative origin
        # while transport is playing; prefer engine_frame for scheduling.
        delta = session_frame - cycle_start_session
        return int(engine_frame) - int(max(0, delta))

    def _map_session_to_extent_frame(self, session_frame: int) -> int:
        assert self._extent is not None
        pos = self._transport.tempo_map.frame_to_bar_beat(int(session_frame))
        beats_per_bar = int(self._transport.tempo_map.time_signature.numerator)
        return map_comparison_phase_to_source_frame(
            master_bar=int(pos.bar),
            master_beat=int(pos.beat),
            master_beat_fraction=pos.beat_fraction,
            beats_per_bar=beats_per_bar,
            loop_bar_count=int(self._extent.bar_count),
            audition_bar_count=int(self._extent.bar_count),
            downbeat_frames=self._extent.downbeat_frames,
        )

    def _alloc_voice_id(self) -> int:
        if self._allocate_voice_id is not None:
            return int(self._allocate_voice_id())
        voice_id = self._next_voice_id
        self._next_voice_id += 1
        return voice_id

    def _pcm_for_schedule(self) -> tuple[np.ndarray, int]:
        assert self._pcm is not None
        if self._pcm_start_offset <= 0:
            return self._pcm, self._pcm_channels
        offset = min(int(self._pcm_start_offset), int(self._pcm.shape[0]) - 1)
        # One-shot entry buffer from phase; subsequent cycles use full span.
        sliced = np.ascontiguousarray(self._pcm[offset:], dtype=np.float32)
        return sliced, self._pcm_channels

    def _reschedule_after_tempo_change(self) -> None:
        """Drop queued future voices and rebuild cycle lengths from the live map."""
        if not self.is_active or self._extent is None:
            return
        engine_frame = int(self._transport.get_engine_frame())
        # Stop only non-sounding scheduled voices; keep the current audible pass.
        engine = self._transport.get_native_engine()
        scheduled = self._scheduled_voice_id
        if scheduled is not None and scheduled != self._sounding_voice_id:
            if engine is not None:
                try:
                    engine.stop_voice(scheduled)
                    engine.remove_voice(scheduled)
                except Exception:
                    pass
            self._transport.unregister_voice(scheduled)
            self._active_voice_ids = [
                v for v in self._active_voice_ids if v != scheduled
            ]
            self._scheduled_voice_id = None
        steady = self._compute_cycle_duration()
        self._cycle_duration_frames = steady
        # Remaining time in the current comparison cycle under the new tempo.
        session_frame = int(self._transport.get_session_frame())
        pos = self._transport.tempo_map.frame_to_bar_beat(session_frame)
        l_bars = int(self._extent.bar_count)
        cycle_start_bar = (int(pos.bar) // l_bars) * l_bars
        next_boundary_bar = cycle_start_bar + l_bars
        next_boundary_session = self._transport.tempo_map.bar_beat_to_frame(
            MusicalPosition(bar=next_boundary_bar, beat=0)
        )
        remaining_session = max(1, int(next_boundary_session) - int(session_frame))
        self._first_cycle_duration_frames = remaining_session
        self._cycle_anchor_engine_frame = engine_frame
        self._next_cycle_index = 0
        self._pcm_start_offset = 0
        # Keep phase_entry offset for continuity until the remainder finishes.
        self.tick(engine_frame=engine_frame)

    def _schedule_cycle_voice(self, engine: Any, *, start_engine_frame: int) -> None:
        assert self._pcm is not None
        assert self._extent is not None
        rate = self._current_rate()
        voice_id = self._alloc_voice_id()
        # First voice after phase entry may use offset PCM; later cycles full.
        if self._next_cycle_index == 0 and self._pcm_start_offset > 0:
            pcm, channels = self._pcm_for_schedule()
            self._pcm_start_offset = 0  # slice flag only; phase_entry offset retained
        else:
            pcm, channels = self._pcm, self._pcm_channels
        try:
            created = engine.create_voice(
                native_audio.VoiceConfig(
                    id=voice_id,
                    source_type=native_audio.SB_SOURCE_PCM_BUFFER,
                    pcm_buffer=native_audio.PcmBufferConfig(
                        samples=pcm,
                        channels=channels,
                    ),
                    initial_rate=rate,
                    sync_mode=native_audio.SB_SYNC_MODE_RATE_SYNC,
                    source_bpm=float(self._source_bpm)
                    if self._source_bpm is not None
                    else 0.0,
                    master_bpm=float(self._transport.get_current_tempo()),
                )
            )
            self._transport.set_voice_source_bpm(created, self._source_bpm)
            engine.schedule_voice_start(created, int(start_engine_frame))
        except Exception:
            try:
                engine.remove_voice(voice_id)
            except Exception:
                pass
            self._transport.unregister_voice(voice_id)
            return
        self._active_voice_ids.append(int(created))
        if self._sounding_voice_id is None:
            self._sounding_voice_id = int(created)
        else:
            self._scheduled_voice_id = int(created)

    def _reclaim_finished(self, engine_frame: int) -> None:
        engine = self._transport.get_native_engine()
        if engine is None or self._cycle_duration_frames is None:
            return
        if (
            self._scheduled_voice_id is None
            or self._sounding_voice_id is None
            or self._scheduled_voice_id == self._sounding_voice_id
            or self._cycle_anchor_engine_frame is None
            or len(self._active_voice_ids) < 2
        ):
            return
        newer_start = self._cycle_start_engine_frame(max(0, self._next_cycle_index - 1))
        if engine_frame < newer_start + DECLICK_FRAMES:
            return
        older = self._sounding_voice_id
        try:
            engine.stop_voice(older)
            engine.remove_voice(older)
        except Exception:
            pass
        self._transport.unregister_voice(older)
        self._active_voice_ids = [v for v in self._active_voice_ids if v != older]
        self._sounding_voice_id = self._scheduled_voice_id
        self._scheduled_voice_id = None

    def _stop_loop_voices(self) -> None:
        engine = self._transport.get_native_engine()
        for voice_id in list(self._active_voice_ids):
            if engine is not None:
                try:
                    engine.stop_voice(voice_id)
                    engine.remove_voice(voice_id)
                except Exception:
                    pass
            self._transport.unregister_voice(voice_id)
        self._active_voice_ids = []
        self._sounding_voice_id = None
        self._scheduled_voice_id = None


__all__ = [
    "BrowserLoopExtent",
    "BrowserLoopOwner",
    "BrowserLoopResult",
    "DECLICK_FRAMES",
    "browser_loop_extent_from_downbeats",
    "extent_from_row",
    "map_comparison_phase_to_source_frame",
]
