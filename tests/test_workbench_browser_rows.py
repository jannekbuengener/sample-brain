"""RED contracts for #510 virtualized waveform-first browser rows.

The production module is deliberately absent during this Phase-B run.  The
guard below keeps collection intact and turns that absence into a targeted RED
failure.  Once implemented, the assertions specify observable browser-row
behaviour using only synthetic ``WorkbenchRow`` values and fake loaders.
"""

from __future__ import annotations

import importlib
import threading
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest

from src import workbench
from src.workbench_controller import WorkbenchRow
from src.workbench import WorkbenchApp


def _row(index: int) -> WorkbenchRow:
    return WorkbenchRow(
        display_name=f"sample-{index:04d}",
        relative_path=f"synthetic/sample-{index:04d}.wav",
        path=str(Path("synthetic") / f"sample-{index:04d}.wav"),
        bpm=128.0,
        key="Am",
        key_conf=0.9,
        loudness=-12.0,
        brightness=1000.0,
        sample_class="one_shot",
        pred_type="Kick",
        status="ok",
        details={"duration_sec": "0.25"},
    )


def _rows(count: int = 5_000) -> list[WorkbenchRow]:
    return [_row(index) for index in range(count)]


def _browser_surface():
    """Return the future pure browser-row surface without a collection error."""
    try:
        return importlib.import_module("src.workbench_browser_rows")
    except ModuleNotFoundError as exc:
        if exc.name == "src.workbench_browser_rows":
            pytest.fail("MISSING_PRODUCTION_SURFACE: virtual browser row viewport")
        raise


def _viewport(surface):
    return surface.VirtualBrowserRowViewport(
        row_height_px=20,
        viewport_height_px=200,
        overscan_rows=2,
    )


def _interaction(
    surface,
    rows: list[WorkbenchRow],
    *,
    selected: list[WorkbenchRow],
    details: list[WorkbenchRow],
    previews: list[WorkbenchRow],
    clock_ns: Callable[[], int] | None = None,
):
    return surface.BrowserRowInteractionController(
        visible_rows=rows,
        viewport=_viewport(surface),
        select_row=selected.append,
        update_detail=details.append,
        dispatch_preview=previews.append,
        clock_ns=clock_ns,
    )


@pytest.mark.parametrize(
    ("scroll_offset_px", "expected_first_visible", "expected_first", "expected_last"),
    [
        (0, 0, 0, 11),
        (50_000, 2_500, 2_498, 2_511),
        (99_800, 4_990, 4_988, 4_999),
    ],
)
def test_virtual_viewport_returns_only_visible_rows_and_explicit_overscan(
    scroll_offset_px: int,
    expected_first_visible: int,
    expected_first: int,
    expected_last: int,
):
    """Removing range limiting would turn a 5,000-row scroll into full rendering."""
    surface = _browser_surface()

    layout = _viewport(surface).layout(_rows(), scroll_offset_px=scroll_offset_px)

    assert layout.first_visible_index == expected_first_visible
    assert layout.renderable_rows[0].row.display_name == _row(expected_first).display_name
    assert layout.renderable_rows[-1].row.display_name == _row(expected_last).display_name
    assert len(layout.renderable_rows) <= 14


def test_virtual_viewport_is_deterministic_for_an_empty_library():
    """An empty library must not manufacture a virtual row or a negative range."""
    surface = _browser_surface()

    layout = _viewport(surface).layout([], scroll_offset_px=0)

    assert layout.renderable_rows == ()
    assert layout.first_visible_index is None


def test_lazy_waveform_cache_hits_once_and_evicts_least_recent_path():
    """Removing path reuse or bounded eviction would cause repeat/full-library decode work."""
    surface = _browser_surface()
    load_calls: list[str] = []

    def loader(path: str) -> tuple[float, ...]:
        load_calls.append(path)
        return (0.0, 0.5, 1.0)

    cache = surface.BoundedLazyWaveformCache(capacity=2, loader=loader)

    assert cache.request("a.wav").state == "ready"
    assert cache.request("a.wav").state == "ready"
    assert cache.request("b.wav").state == "ready"
    assert cache.request("c.wav").state == "ready"
    assert cache.request("a.wav").state == "ready"

    assert load_calls == ["a.wav", "b.wav", "c.wav", "a.wav"]
    assert cache.paths() == ("c.wav", "a.wav")
    assert cache.size == 2


def test_lazy_waveform_cache_converts_loader_errors_to_a_placeholder_state():
    """Letting a decode exception escape would break the Tk event/UI contract."""
    surface = _browser_surface()

    def broken_loader(_path: str):
        raise OSError("synthetic corrupt waveform")

    result = surface.BoundedLazyWaveformCache(
        capacity=1, loader=broken_loader
    ).request("broken.wav")

    assert result.state == "placeholder"
    assert result.envelope == ()
    assert result.failure == "load_failed"


def test_waveform_click_resolves_the_exact_virtual_row_selects_updates_detail_and_dispatches_once():
    """A wrong hit-test index or a duplicate dispatch audibly auditions the wrong sample."""
    surface = _browser_surface()
    rows = _rows(20)
    selected: list[WorkbenchRow] = []
    details: list[WorkbenchRow] = []
    previews: list[WorkbenchRow] = []
    browser = _interaction(
        surface, rows, selected=selected, details=details, previews=previews
    )

    outcome = browser.click_waveform(row_index=7, x_px=40)

    assert outcome.event_result == "break"
    assert selected == [rows[7]]
    assert details == [rows[7]]
    assert previews == [rows[7]]


def test_keyboard_navigation_scrolls_the_selected_row_into_the_virtual_viewport_and_auditions_once():
    """Dropping scroll reconciliation or dispatching twice breaks tack-to-tack browsing."""
    surface = _browser_surface()
    rows = _rows(20)
    selected: list[WorkbenchRow] = []
    details: list[WorkbenchRow] = []
    previews: list[WorkbenchRow] = []
    browser = _interaction(
        surface, rows, selected=selected, details=details, previews=previews
    )
    browser.set_selection(9)

    outcome = browser.handle_browser_key("Down")

    assert outcome.event_result == "break"
    assert outcome.selected_index == 10
    assert outcome.scroll_offset_px == 20
    assert selected[-1] is rows[10]
    assert details[-1] is rows[10]
    assert previews == [rows[10]]


@pytest.mark.parametrize(
    ("selected_index", "key", "expected_index"),
    [(0, "Up", 0), (19, "Down", 19)],
)
def test_keyboard_navigation_has_deterministic_upper_and_lower_edges(
    selected_index: int, key: str, expected_index: int
):
    """Boundary underflow/overflow must not change row identity or emit an extra preview."""
    surface = _browser_surface()
    rows = _rows(20)
    selected: list[WorkbenchRow] = []
    details: list[WorkbenchRow] = []
    previews: list[WorkbenchRow] = []
    browser = _interaction(
        surface, rows, selected=selected, details=details, previews=previews
    )
    browser.set_selection(selected_index)

    outcome = browser.handle_browser_key(key)

    assert outcome.selected_index == expected_index
    assert previews == [rows[expected_index]]


def test_editable_focus_leaves_arrow_keys_native_without_selection_or_audition():
    """A root-like arrow router would steal search/editing input and falsely preview."""
    surface = _browser_surface()
    rows = _rows(2)
    selected: list[WorkbenchRow] = []
    details: list[WorkbenchRow] = []
    previews: list[WorkbenchRow] = []
    browser = _interaction(
        surface, rows, selected=selected, details=details, previews=previews
    )
    browser.set_selection(0)

    outcome = browser.handle_browser_key("Down", editable_focus=True)

    assert outcome.event_result is None
    assert outcome.selected_index == 0
    assert selected == []
    assert details == []
    assert previews == []


def test_escape_reuses_the_slice1_preview_router_without_a_second_browser_stop_path():
    """Replacing the authoritative Slice-1 router could stop idle preview or double-stop."""
    stops: list[str] = []

    active_result = WorkbenchApp._route_browser_escape(
        object(), preview_is_active=True, stop_preview=lambda: stops.append("stop")
    )
    idle_result = WorkbenchApp._route_browser_escape(
        object(), preview_is_active=False, stop_preview=lambda: stops.append("idle")
    )

    assert active_result == "break"
    assert idle_result is None
    assert stops == ["stop"]


def test_new_row_handlers_measure_work_before_preview_dispatch_return():
    """Starting the timer after hit-testing/detail work would hide handler latency."""
    surface = _browser_surface()
    rows = _rows(2)
    selected: list[WorkbenchRow] = []
    details: list[WorkbenchRow] = []
    previews: list[WorkbenchRow] = []
    ticks = iter((1_000_000_000, 1_012_000_000))
    browser = _interaction(
        surface,
        rows,
        selected=selected,
        details=details,
        previews=previews,
        clock_ns=lambda: next(ticks),
    )

    metric = browser.click_waveform(row_index=1, x_px=40).dispatch_metric

    assert metric.event_timestamp_ns == 1_000_000_000
    assert metric.dispatch_return_timestamp_ns == 1_012_000_000
    assert metric.event_to_dispatch_return_ms == 12.0
    assert previews == [rows[1]]


def test_performance_acceptance_seam_records_forty_prepared_transitions_without_claiming_dac_latency():
    """Removing the seam would make the future 40-transition p95 gate untestable."""
    surface = _browser_surface()
    rows = _rows(2)
    selected: list[WorkbenchRow] = []
    details: list[WorkbenchRow] = []
    previews: list[WorkbenchRow] = []
    browser = _interaction(
        surface, rows, selected=selected, details=details, previews=previews
    )

    report = surface.measure_prepared_browser_transitions(
        transitions=40,
        dispatch=lambda index: browser.click_waveform(row_index=index, x_px=40),
    )

    assert report.transition_count == 40
    assert len(report.event_to_dispatch_return_ms) == 40
    assert report.acceptance_metric_name == "handler-entry_to_dispatch-return"
    assert not hasattr(report, "speaker_latency_ms")


def test_viewport_updates_request_waveforms_only_for_renderable_rows_never_the_full_library():
    """A synchronous all-library envelope loop would freeze scroll and key interaction."""
    surface = _browser_surface()
    rows = _rows()
    load_calls: list[str] = []
    cache = surface.BoundedLazyWaveformCache(
        capacity=32,
        loader=lambda path: load_calls.append(path) or (0.0, 1.0),
    )

    layout = _viewport(surface).layout(rows, scroll_offset_px=50_000)
    surface.request_renderable_waveforms(layout, cache=cache)

    renderable_paths = {item.row.path for item in layout.renderable_rows}
    assert set(load_calls) == renderable_paths
    assert len(load_calls) <= 14
    assert len(load_calls) < len(rows)


class _CanvasDouble:
    def __init__(self, *, width: int = 200):
        self.width = width
        self.calls: list[object] = []

    def canvasy(self, y: int) -> int:
        self.calls.append("hit-test")
        return y

    def winfo_width(self) -> int:
        return self.width

    def focus_set(self) -> None:
        self.calls.append("focus")

    def yview(self, *args: str) -> None:
        self.calls.append(("yview", args))


def _canvas_app(rows: list[WorkbenchRow]) -> WorkbenchApp:
    app = WorkbenchApp.__new__(WorkbenchApp)
    app._visible_rows = rows
    app._busy = False
    app._browser_canvas = _CanvasDouble()
    app._browser_row_height_px = 20
    app._tree = SimpleNamespace(selection_set=lambda _index: None)
    app._skip_next_browser_selection_preview = None
    app._render_browser_rows = lambda: None
    return app


def test_canvas_click_starts_timing_at_handler_entry_before_hit_test_and_selection(monkeypatch):
    app = _canvas_app([_row(1)])
    events: list[object] = []
    app._browser_canvas.calls = events
    app._tree = SimpleNamespace(selection_set=lambda _index: events.append("select"))
    monkeypatch.setattr(workbench, "monotonic_ns", lambda: events.append("clock") or 123)
    app._audition_browser_row = lambda row, *, event_timestamp_ns: events.append(
        ("audition", row.display_name, event_timestamp_ns)
    )

    app._on_browser_canvas_click(SimpleNamespace(x=10, y=0))

    assert events[:5] == [
        "clock",
        "hit-test",
        "focus",
        "select",
        ("audition", "sample-0001", 123),
    ]


def test_scrollbar_command_delegates_and_rerenders_virtual_rows():
    app = _canvas_app([_row(1)])
    renders: list[str] = []
    app._render_browser_rows = lambda: renders.append("render")

    handler = getattr(app, "_on_browser_scrollbar", None)
    assert handler is not None, "missing virtual scrollbar rerender seam"
    handler("moveto", "0.5")

    assert app._browser_canvas.calls == [("yview", ("moveto", "0.5"))]
    assert renders == ["render"]


def test_canvas_add_hit_area_reuses_playlist_dialog_without_preview_dispatch():
    app = _canvas_app([_row(1)])
    opened: list[WorkbenchRow] = []
    previews: list[WorkbenchRow] = []
    app._open_add_to_playlist_dialog = opened.append
    app._audition_browser_row = lambda row, **_kwargs: previews.append(row)

    result = app._on_browser_canvas_click(SimpleNamespace(x=190, y=0))

    assert result == "break"
    assert opened == [app._visible_rows[0]]
    assert previews == []


def test_valid_canvas_waveform_click_sets_focus_and_auditions_once():
    app = _canvas_app([_row(1)])
    previews: list[WorkbenchRow] = []
    app._audition_browser_row = lambda row, **_kwargs: previews.append(row)

    app._on_browser_canvas_click(SimpleNamespace(x=10, y=0))

    assert app._browser_canvas.calls.count("focus") == 1
    assert previews == [app._visible_rows[0]]


def test_visible_canvas_sort_action_reuses_existing_sort_callback_and_rerenders():
    app = _canvas_app([_row(2), _row(1)])
    calls: list[str] = []
    app._on_sort_column = calls.append

    action = getattr(app, "_on_browser_sort_column", None)
    assert action is not None, "missing visible canvas sort action"
    action("name")

    assert calls == ["name"]


def test_clear_playlist_rerenders_empty_canvas_state():
    app = _canvas_app([_row(1)])
    app._rows = list(app._visible_rows)
    app._tree = SimpleNamespace(get_children=lambda: ("0",), delete=lambda *_ids: None)
    app._stop_preview = lambda: None
    app._filter_var = SimpleNamespace(set=lambda _value: None)
    app._reset_structured_filters = lambda: None
    app._update_sort_headings = lambda: None
    app._clear_similar_suggestions = lambda: None
    app._set_detail = lambda _row: None
    renders: list[str] = []
    app._render_browser_rows = lambda: renders.append("render")

    app._clear_playlist()

    assert app._visible_rows == []
    assert renders == ["render"]


def test_background_waveform_schedule_returns_before_decode_completes_and_uses_a_worker_thread():
    """A blocking decode must never run on the UI caller that schedules it."""
    surface = _browser_surface()
    decode_started = threading.Event()
    release_decode = threading.Event()
    decoded_on: list[int] = []
    ui_thread_id = threading.get_ident()
    cache = surface.BoundedLazyWaveformCache(capacity=48, loader=lambda _path: ())

    def blocking_loader(_path: str) -> tuple[float, ...]:
        decoded_on.append(threading.get_ident())
        decode_started.set()
        assert release_decode.wait(timeout=1)
        return (0.25, 0.75)

    loader = surface.BoundedBackgroundWaveformLoader(
        cache=cache, loader=blocking_loader, max_pending=2
    )
    try:
        assert loader.schedule("a.wav") is True
        assert decode_started.wait(timeout=1)
        assert cache.get("a.wav") is None
        assert decoded_on == [decoded_on[0]]
        assert decoded_on[0] != ui_thread_id

        release_decode.set()
        assert loader.wait_for_result(timeout=1)
        assert loader.drain_results() == 1
        assert cache.get("a.wav").state == "ready"
    finally:
        release_decode.set()
        loader.close()


def test_background_waveform_loader_drains_failure_as_placeholder_without_tk_work():
    """Worker exceptions become main-thread cache placeholders, not UI exceptions."""
    surface = _browser_surface()
    cache = surface.BoundedLazyWaveformCache(capacity=48, loader=lambda _path: ())

    def broken_loader(_path: str) -> tuple[float, ...]:
        raise OSError("synthetic corrupt waveform")

    loader = surface.BoundedBackgroundWaveformLoader(
        cache=cache, loader=broken_loader, max_pending=2
    )
    try:
        assert loader.schedule("broken.wav") is True
        assert loader.wait_for_result(timeout=1)
        assert loader.drain_results() == 1
        result = cache.get("broken.wav")
        assert result is not None
        assert result.state == "placeholder"
        assert result.failure == "load_failed"
    finally:
        loader.close()


def test_background_waveform_loader_deduplicates_and_bounds_rapid_renderable_scheduling():
    """Rapid scrolling must not create duplicate or unbounded decode work."""
    surface = _browser_surface()
    decode_started = threading.Event()
    release_decode = threading.Event()
    release_second_decode = threading.Event()
    calls: list[str] = []
    cache = surface.BoundedLazyWaveformCache(capacity=48, loader=lambda _path: ())

    def blocking_loader(path: str) -> tuple[float, ...]:
        calls.append(path)
        decode_started.set()
        assert release_decode.wait(timeout=1)
        if path == "b.wav":
            assert release_second_decode.wait(timeout=1)
        return (1.0,)

    loader = surface.BoundedBackgroundWaveformLoader(
        cache=cache, loader=blocking_loader, max_pending=2
    )
    try:
        assert loader.schedule("a.wav") is True
        assert decode_started.wait(timeout=1)
        assert loader.schedule("a.wav") is False
        assert loader.schedule("b.wav") is True
        assert loader.schedule("c.wav") is False
        assert loader.pending_paths() == ("a.wav", "b.wav")
        assert loader.pending_count == 2

        release_decode.set()
        assert loader.wait_for_result(timeout=1)
        assert loader.drain_results() == 1
        release_second_decode.set()
        assert loader.wait_for_result(timeout=1)
        assert loader.drain_results() == 1
        assert calls == ["a.wav", "b.wav"]
        assert loader.pending_count == 0
    finally:
        release_decode.set()
        release_second_decode.set()
        loader.close()


def test_background_waveform_scheduler_accepts_only_renderable_viewport_paths():
    """The UI scheduling seam must not turn a 5,000-row layout into preload work."""
    surface = _browser_surface()
    rows = _rows()
    cache = surface.BoundedLazyWaveformCache(capacity=48, loader=lambda _path: ())
    loader = surface.BoundedBackgroundWaveformLoader(
        cache=cache, loader=lambda _path: (0.0, 1.0), max_pending=14
    )
    try:
        layout = _viewport(surface).layout(rows, scroll_offset_px=50_000)
        scheduled = surface.schedule_renderable_waveforms(layout, loader=loader)

        assert set(scheduled) == {item.row.path for item in layout.renderable_rows}
        assert len(scheduled) <= 14
        assert len(scheduled) < len(rows)
    finally:
        loader.close()


def test_browser_render_schedule_seam_returns_before_a_blocking_decode_finishes():
    """The Tk render path must only enqueue viewport work, never await audio I/O."""
    surface = _browser_surface()
    decode_started = threading.Event()
    release_decode = threading.Event()
    cache = surface.BoundedLazyWaveformCache(capacity=48, loader=lambda _path: ())

    def blocking_loader(_path: str) -> tuple[float, ...]:
        decode_started.set()
        assert release_decode.wait(timeout=1)
        return (0.5,)

    loader = surface.BoundedBackgroundWaveformLoader(
        cache=cache, loader=blocking_loader, max_pending=14
    )
    app = WorkbenchApp.__new__(WorkbenchApp)
    app._browser_waveform_loader = loader
    app._browser_waveform_drain_scheduled = False
    after_calls: list[int] = []
    app.root = SimpleNamespace(after=lambda milliseconds, _callback: after_calls.append(milliseconds))
    layout = _viewport(surface).layout(_rows(), scroll_offset_px=50_000)
    try:
        app._schedule_browser_waveforms(layout)

        assert decode_started.wait(timeout=1)
        assert after_calls == [25]
        assert cache.get(layout.renderable_rows[0].row.path) is None
    finally:
        release_decode.set()
        loader.close()
