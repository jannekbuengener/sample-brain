"""Pure contracts for virtualized waveform-first Workbench browser rows."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
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


class BoundedLazyWaveformCache:
    def __init__(self, *, capacity: int, loader: Callable[[str], Sequence[float]]) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._capacity = capacity
        self._loader = loader
        self._entries: OrderedDict[str, WaveformCacheResult] = OrderedDict()

    @property
    def size(self) -> int:
        return len(self._entries)

    def paths(self) -> tuple[str, ...]:
        return tuple(self._entries)

    def get(self, path: str) -> WaveformCacheResult | None:
        """Read a cached result without loading or changing LRU order."""
        return self._entries.get(path)

    def request(self, path: str) -> WaveformCacheResult:
        cached = self._entries.get(path)
        if cached is not None:
            self._entries.move_to_end(path)
            return cached
        try:
            result = WaveformCacheResult("ready", tuple(self._loader(path)))
        except Exception:
            result = WaveformCacheResult("placeholder", (), "load_failed")
        self._entries[path] = result
        self._entries.move_to_end(path)
        while len(self._entries) > self._capacity:
            self._entries.popitem(last=False)
        return result


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
