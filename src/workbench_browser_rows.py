"""Pure contracts for virtualized waveform-first Workbench browser rows."""

from __future__ import annotations

from queue import Empty, Queue
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from threading import Condition, Event, Thread
from time import monotonic_ns
from typing import Generic, TypeVar


RowT = TypeVar("RowT")


@dataclass(frozen=True)
class RenderableBrowserRow(Generic[RowT]):
    index: int
    row: RowT


@dataclass(frozen=True)
class VirtualBrowserRowLayout(Generic[RowT]):
    first_visible_index: int | None
    renderable_rows: tuple[RenderableBrowserRow[RowT], ...]


class VirtualBrowserRowViewport:
    def __init__(
        self, *, row_height_px: int, viewport_height_px: int, overscan_rows: int
    ) -> None:
        if row_height_px <= 0 or viewport_height_px <= 0 or overscan_rows < 0:
            raise ValueError("viewport dimensions must be positive and overscan non-negative")
        self.row_height_px = row_height_px
        self.viewport_height_px = viewport_height_px
        self.overscan_rows = overscan_rows

    @property
    def visible_row_count(self) -> int:
        return max(1, self.viewport_height_px // self.row_height_px)

    def layout(
        self, rows: Sequence[RowT], *, scroll_offset_px: int
    ) -> VirtualBrowserRowLayout[RowT]:
        if not rows:
            return VirtualBrowserRowLayout(None, ())
        max_index = len(rows) - 1
        first_visible = min(max(scroll_offset_px, 0) // self.row_height_px, max_index)
        start = max(first_visible - self.overscan_rows, 0)
        end = min(
            first_visible + self.visible_row_count + self.overscan_rows,
            len(rows),
        )
        return VirtualBrowserRowLayout(
            first_visible,
            tuple(RenderableBrowserRow(index, rows[index]) for index in range(start, end)),
        )


@dataclass(frozen=True)
class WaveformCacheResult:
    state: str
    envelope: tuple[float, ...]
    failure: str | None = None


CURRENT_VISIBLE = "current_visible"
BACKGROUND_ENRICHMENT = "background_enrichment"


def waveform_pump_decision(*, cached: WaveformCacheResult | None) -> str:
    """Skip terminal results already cached for the candidate identity."""
    if cached is not None and (
        cached.state == "ready"
        or (cached.state == "placeholder" and cached.failure)
    ):
        return "skip"
    return "schedule"


@dataclass(frozen=True)
class WaveformDecodeResult:
    path: str
    result: WaveformCacheResult
    priority: str
    generation: int
    source_size_bytes: int | None
    source_mtime_ns: int | None


@dataclass(frozen=True)
class _WaveformTask:
    path: str
    priority: str
    generation: int
    source_size_bytes: int | None
    source_mtime_ns: int | None

    @property
    def identity(self) -> tuple[str, int | None, int | None]:
        return (self.path, self.source_size_bytes, self.source_mtime_ns)


class BoundedLazyWaveformCache:
    def __init__(self, *, capacity: int, loader: Callable[[str], Sequence[float]]) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._capacity = capacity
        self._loader = loader
        self._entries: OrderedDict[
            str, tuple[WaveformCacheResult, int | None, int | None]
        ] = OrderedDict()

    @property
    def size(self) -> int:
        return len(self._entries)

    def paths(self) -> tuple[str, ...]:
        return tuple(self._entries)

    def get(
        self,
        path: str,
        *,
        source_size_bytes: int | None = None,
        source_mtime_ns: int | None = None,
        touch: bool = False,
    ) -> WaveformCacheResult | None:
        """Read one matching result and optionally mark it recently used."""
        cached = self._entries.get(path)
        if cached is None:
            return None
        result, cached_size, cached_mtime = cached
        if source_size_bytes is not None or source_mtime_ns is not None:
            if (
                cached_size != source_size_bytes
                or cached_mtime != source_mtime_ns
            ):
                return None
        if touch:
            self._entries.move_to_end(path)
        return result

    def request(self, path: str) -> WaveformCacheResult:
        cached = self.get(path, touch=True)
        if cached is not None:
            return cached
        try:
            result = WaveformCacheResult("ready", tuple(self._loader(path)))
        except Exception:
            result = WaveformCacheResult("placeholder", (), "load_failed")
        self._entries[path] = (result, None, None)
        self._entries.move_to_end(path)
        while len(self._entries) > self._capacity:
            self._entries.popitem(last=False)
        return result

    def put_result(
        self,
        path: str,
        result: WaveformCacheResult,
        *,
        source_size_bytes: int | None = None,
        source_mtime_ns: int | None = None,
    ) -> None:
        """Store a worker result from the UI thread while preserving the LRU bound."""
        self._entries[path] = (result, source_size_bytes, source_mtime_ns)
        self._entries.move_to_end(path)
        while len(self._entries) > self._capacity:
            self._entries.popitem(last=False)


class BoundedBackgroundWaveformLoader:
    """Bounded single-worker scheduler with foreground priority and generations."""

    def __init__(
        self,
        *,
        cache: BoundedLazyWaveformCache,
        loader: Callable[[str], Sequence[float]],
        max_pending: int,
        on_result: Callable[[WaveformDecodeResult], None] | None = None,
    ) -> None:
        if max_pending <= 0:
            raise ValueError("max_pending must be positive")
        self._cache = cache
        self._loader = loader
        self._max_pending = max_pending
        self._on_result = on_result
        self._results: Queue[WaveformDecodeResult] = Queue(maxsize=max_pending)
        self._visible_tasks: OrderedDict[
            tuple[str, int | None, int | None], _WaveformTask
        ] = OrderedDict()
        self._background_tasks: OrderedDict[
            tuple[str, int | None, int | None], _WaveformTask
        ] = OrderedDict()
        self._pending: OrderedDict[
            tuple[str, int | None, int | None], _WaveformTask
        ] = OrderedDict()
        self._tasks_ready = Condition()
        self._result_ready = Event()
        self._closed = Event()
        self._background_paused = False
        self._generation = 0
        self._worker = Thread(
            target=self._run, name="sample-brain-browser-waveform", daemon=True
        )
        self._worker.start()

    @property
    def pending_count(self) -> int:
        with self._tasks_ready:
            return len(self._pending)

    def pending_paths(self) -> tuple[str, ...]:
        with self._tasks_ready:
            return tuple(task.path for task in self._pending.values())

    @property
    def current_generation(self) -> int:
        with self._tasks_ready:
            return self._generation

    def pending_count_for(self, priority: str) -> int:
        with self._tasks_ready:
            return sum(task.priority == priority for task in self._pending.values())

    @property
    def available_capacity(self) -> int:
        with self._tasks_ready:
            return max(0, self._max_pending - len(self._pending))

    def advance_generation(self) -> int:
        """Own a new viewport and discard queued work from older viewports."""
        with self._tasks_ready:
            self._generation += 1
            stale = [
                identity
                for identity, task in self._visible_tasks.items()
                if task.generation < self._generation
            ]
            for identity in stale:
                self._visible_tasks.pop(identity, None)
                self._pending.pop(identity, None)
            self._tasks_ready.notify_all()
            return self._generation

    def set_background_paused(self, paused: bool) -> None:
        """Pause admission from the queued enrichment lane during interaction."""
        with self._tasks_ready:
            self._background_paused = bool(paused)
            self._tasks_ready.notify_all()

    def schedule(
        self,
        path: str,
        *,
        priority: str = CURRENT_VISIBLE,
        generation: int | None = None,
        source_size_bytes: int | None = None,
        source_mtime_ns: int | None = None,
    ) -> bool:
        """Queue one uncached path without waiting for its decode."""
        if priority not in {CURRENT_VISIBLE, BACKGROUND_ENRICHMENT}:
            raise ValueError("unknown waveform priority")
        with self._tasks_ready:
            owned_generation = self._generation if generation is None else int(generation)
            if priority == CURRENT_VISIBLE and owned_generation != self._generation:
                return False
            task = _WaveformTask(
                path=str(path),
                priority=priority,
                generation=owned_generation,
                source_size_bytes=source_size_bytes,
                source_mtime_ns=source_mtime_ns,
            )
            if (
                self._closed.is_set()
                or self._cache.get(
                    task.path,
                    source_size_bytes=source_size_bytes,
                    source_mtime_ns=source_mtime_ns,
                )
                is not None
            ):
                return False
            if task.identity in self._pending:
                if priority == CURRENT_VISIBLE and task.identity in self._background_tasks:
                    self._background_tasks.pop(task.identity, None)
                    self._pending[task.identity] = task
                    self._visible_tasks[task.identity] = task
                    self._tasks_ready.notify()
                    return True
                return False
            if len(self._pending) >= self._max_pending:
                if priority != CURRENT_VISIBLE or not self._background_tasks:
                    return False
                stale_identity, _stale = self._background_tasks.popitem(last=False)
                self._pending.pop(stale_identity, None)
            self._pending[task.identity] = task
            target = (
                self._visible_tasks
                if priority == CURRENT_VISIBLE
                else self._background_tasks
            )
            target[task.identity] = task
            self._tasks_ready.notify()
        return True

    def wait_for_result(self, *, timeout: float) -> bool:
        """Test/host seam: wait for a completed worker result without draining it."""
        return self._result_ready.wait(timeout=timeout) and not self._results.empty()

    def drain_results(self) -> int:
        """Apply completed plain-Python results on the calling/UI thread."""
        drained: list[WaveformDecodeResult] = []
        while True:
            try:
                drained.append(self._results.get_nowait())
            except Empty:
                break
        if self._results.empty():
            self._result_ready.clear()
        for completed in drained:
            self._cache.put_result(
                completed.path,
                completed.result,
                source_size_bytes=completed.source_size_bytes,
                source_mtime_ns=completed.source_mtime_ns,
            )
            if self._on_result is not None:
                self._on_result(completed)
            identity = (
                completed.path,
                completed.source_size_bytes,
                completed.source_mtime_ns,
            )
            with self._tasks_ready:
                self._pending.pop(identity, None)
        return len(drained)

    def close(self) -> None:
        """Stop accepting work without waiting for an in-flight file decode."""
        self._closed.set()
        with self._tasks_ready:
            queued_identities = tuple(self._visible_tasks) + tuple(
                self._background_tasks
            )
            self._visible_tasks.clear()
            self._background_tasks.clear()
            for identity in queued_identities:
                self._pending.pop(identity, None)
            self._tasks_ready.notify_all()

    def _run(self) -> None:
        while True:
            with self._tasks_ready:
                self._tasks_ready.wait_for(
                    lambda: self._closed.is_set()
                    or bool(self._visible_tasks)
                    or (bool(self._background_tasks) and not self._background_paused)
                )
                if self._closed.is_set():
                    return
                if self._visible_tasks:
                    _identity, task = self._visible_tasks.popitem(last=False)
                else:
                    _identity, task = self._background_tasks.popitem(last=False)
            try:
                result = WaveformCacheResult("ready", tuple(self._loader(task.path)))
            except Exception:
                result = WaveformCacheResult("placeholder", (), "load_failed")
            completed = WaveformDecodeResult(
                path=task.path,
                result=result,
                priority=task.priority,
                generation=task.generation,
                source_size_bytes=task.source_size_bytes,
                source_mtime_ns=task.source_mtime_ns,
            )
            self._results.put(completed)
            self._result_ready.set()


@dataclass(frozen=True)
class BrowserPreviewDispatchMetric:
    event_timestamp_ns: int
    dispatch_return_timestamp_ns: int
    event_to_dispatch_return_ms: float


@dataclass(frozen=True)
class BrowserRowInteractionOutcome:
    event_result: str | None
    selected_index: int
    scroll_offset_px: int
    dispatch_metric: BrowserPreviewDispatchMetric | None = None


class BrowserRowInteractionController(Generic[RowT]):
    def __init__(
        self,
        *,
        visible_rows: Sequence[RowT],
        viewport: VirtualBrowserRowViewport,
        select_row: Callable[[RowT], None],
        update_detail: Callable[[RowT], None],
        dispatch_preview: Callable[[RowT], object],
        clock_ns: Callable[[], int] | None = None,
    ) -> None:
        self.visible_rows = visible_rows
        self.viewport = viewport
        self._select_row = select_row
        self._update_detail = update_detail
        self._dispatch_preview = dispatch_preview
        self._clock_ns = clock_ns or monotonic_ns
        self._selected_index = 0
        self._scroll_offset_px = 0

    def set_selection(self, index: int) -> None:
        if self.visible_rows:
            self._selected_index = min(max(index, 0), len(self.visible_rows) - 1)

    def _scroll_selection_into_view(self) -> None:
        top = self._scroll_offset_px // self.viewport.row_height_px
        bottom = top + self.viewport.visible_row_count - 1
        if self._selected_index < top:
            self._scroll_offset_px = self._selected_index * self.viewport.row_height_px
        elif self._selected_index > bottom:
            self._scroll_offset_px = (
                (self._selected_index - self.viewport.visible_row_count + 1)
                * self.viewport.row_height_px
            )

    def _dispatch(self, index: int, *, event_timestamp_ns: int) -> BrowserRowInteractionOutcome:
        row = self.visible_rows[index]
        self._selected_index = index
        self._scroll_selection_into_view()
        self._select_row(row)
        self._update_detail(row)
        self._dispatch_preview(row)
        returned = self._clock_ns()
        return BrowserRowInteractionOutcome(
            "break",
            index,
            self._scroll_offset_px,
            BrowserPreviewDispatchMetric(
                event_timestamp_ns,
                returned,
                (returned - event_timestamp_ns) / 1_000_000,
            ),
        )

    def click_waveform(self, *, row_index: int, x_px: int) -> BrowserRowInteractionOutcome:
        del x_px
        if not self.visible_rows or not 0 <= row_index < len(self.visible_rows):
            return BrowserRowInteractionOutcome("break", self._selected_index, self._scroll_offset_px)
        return self._dispatch(row_index, event_timestamp_ns=self._clock_ns())

    def handle_browser_key(
        self, key: str, *, editable_focus: bool = False
    ) -> BrowserRowInteractionOutcome:
        if editable_focus:
            return BrowserRowInteractionOutcome(None, self._selected_index, self._scroll_offset_px)
        if not self.visible_rows:
            return BrowserRowInteractionOutcome("break", self._selected_index, self._scroll_offset_px)
        target = self._selected_index
        if key == "Down":
            target = min(target + 1, len(self.visible_rows) - 1)
        elif key == "Up":
            target = max(target - 1, 0)
        else:
            return BrowserRowInteractionOutcome(None, self._selected_index, self._scroll_offset_px)
        return self._dispatch(target, event_timestamp_ns=self._clock_ns())


@dataclass(frozen=True)
class PreparedBrowserTransitionReport:
    transition_count: int
    event_to_dispatch_return_ms: tuple[float, ...]
    acceptance_metric_name: str = "handler-entry_to_dispatch-return"


def measure_prepared_browser_transitions(
    *, transitions: int, dispatch: Callable[[int], BrowserRowInteractionOutcome]
) -> PreparedBrowserTransitionReport:
    if transitions < 0:
        raise ValueError("transitions must not be negative")
    measurements: list[float] = []
    for transition in range(transitions):
        outcome = dispatch(transition % 2)
        if outcome.dispatch_metric is not None:
            measurements.append(outcome.dispatch_metric.event_to_dispatch_return_ms)
    return PreparedBrowserTransitionReport(transitions, tuple(measurements))


def request_renderable_waveforms(
    layout: VirtualBrowserRowLayout[object], *, cache: BoundedLazyWaveformCache
) -> tuple[WaveformCacheResult, ...]:
    return tuple(cache.request(str(item.row.path)) for item in layout.renderable_rows)


def schedule_renderable_waveforms(
    layout: VirtualBrowserRowLayout[object], *, loader: BoundedBackgroundWaveformLoader
) -> tuple[str, ...]:
    """Schedule only the virtual viewport's bounded renderable paths."""
    return tuple(
        path
        for item in layout.renderable_rows
        if loader.schedule(path := str(item.row.path))
    )
