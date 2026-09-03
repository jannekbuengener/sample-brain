"""RED contracts for #510 virtualized waveform-first browser rows.

The production module is deliberately absent during this Phase-B run.  The
guard below keeps collection intact and turns that absence into a targeted RED
failure.  Once implemented, the assertions specify observable browser-row
behaviour using only synthetic ``WorkbenchRow`` values and fake loaders.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from pathlib import Path

import pytest

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
    ("scroll_offset_px", "expected_first", "expected_last"),
    [
        (0, 0, 11),
        (50_000, 2_498, 2_511),
        (99_800, 4_988, 4_999),
    ],
)
def test_virtual_viewport_returns_only_visible_rows_and_explicit_overscan(
    scroll_offset_px: int, expected_first: int, expected_last: int
):
    """Removing range limiting would turn a 5,000-row scroll into full rendering."""
    surface = _browser_surface()

    layout = _viewport(surface).layout(_rows(), scroll_offset_px=scroll_offset_px)

    assert layout.first_visible_index == expected_first + 2
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
