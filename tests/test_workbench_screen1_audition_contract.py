"""RED contracts for Screen 1 browser-local sample auditioning (#503).

These tests deliberately exercise the smallest app-facing interaction seam that
Phase C must provide.  They use no Tk root or audio device: a browser row is a
``WorkbenchRow`` and preview calls are recorded by a fake.
"""

from __future__ import annotations

from pathlib import Path
from types import MethodType, SimpleNamespace

import pytest

from src.workbench import WorkbenchApp
from src.workbench_controller import WorkbenchRow
from src.workbench_preview import PreviewResult


def _row(name: str) -> WorkbenchRow:
    return WorkbenchRow(
        display_name=name,
        relative_path=f"{name}.wav",
        path=str(Path("synthetic") / f"{name}.wav"),
        bpm=128.0,
        key="Am",
        key_conf=0.9,
        loudness=-12.0,
        brightness=1000.0,
        sample_class="one_shot",
        pred_type="Kick",
        status="ok",
    )


def _bare_browser_app(rows: list[WorkbenchRow]) -> WorkbenchApp:
    """Build only the pre-existing state needed by selection contracts."""
    app = WorkbenchApp.__new__(WorkbenchApp)
    app._visible_rows = rows
    app._busy = False
    return app


@pytest.mark.parametrize(
    ("direction", "selected", "expected"),
    [
        ("next", 0, 1),
        ("previous", 1, 0),
        ("previous", 0, 0),
        ("next", 2, 2),
    ],
)
def test_browser_navigation_uses_visible_order_and_has_deterministic_edges(
    direction: str, selected: int, expected: int
):
    """Navigation is based on the filtered/sorted visible rows, never source indices."""
    app = _bare_browser_app(
        [_row("filtered_b"), _row("filtered_a"), _row("filtered_c")]
    )

    target = app._resolve_visible_browser_row(selected, direction=direction)

    assert target is app._visible_rows[expected]


def test_browser_navigation_empty_visible_rows_has_no_preview_target():
    app = _bare_browser_app([])

    assert app._resolve_visible_browser_row(0, direction="next") is None


def test_browser_down_selects_next_visible_row_consumes_and_previews_once():
    app = _bare_browser_app([_row("a"), _row("b")])
    previews: list[str] = []

    outcome = app._route_browser_navigation_key(
        direction="next",
        selected_index=0,
        preview=lambda row: previews.append(row.display_name),
    )

    assert outcome.selected_index == 1
    assert outcome.event_result == "break"
    assert previews == ["b"]


def test_editable_focus_leaves_down_native_and_does_not_preview():
    app = _bare_browser_app([_row("a"), _row("b")])
    previews: list[str] = []

    outcome = app._route_browser_navigation_key(
        direction="next",
        selected_index=0,
        editable_focus=True,
        preview=lambda row: previews.append(row.display_name),
    )

    assert outcome.event_result is None
    assert outcome.selected_index == 0
    assert previews == []


def test_browser_waveform_click_auditions_the_clicked_row_without_detail_play_button():
    app = _bare_browser_app([_row("a"), _row("b")])
    previews: list[str] = []

    app._audition_browser_waveform_row(
        app._visible_rows[1], lambda row: previews.append(row.display_name)
    )

    assert previews == ["b"]


def test_selection_a_to_b_requests_one_preview_replacement_without_app_stop():
    """Contract correction: replacement belongs to the preview owner, not the UI."""
    a, b = _row("a"), _row("b")
    app = _bare_browser_app([a, b])
    calls: list[tuple[str, str]] = []
    app._tree = SimpleNamespace(selection=lambda: ("1",))
    app._preview = SimpleNamespace(current_path=Path(a.path).resolve())
    app._stop_preview = lambda: calls.append(("unexpected_stop", "a"))
    app._set_detail = MethodType(
        lambda self, row: setattr(self, "_detail_row", row), app
    )
    app._play_preview = lambda: calls.append(("play", app._detail_row.display_name))

    app._on_select()

    assert calls == [("play", "b")]


def test_escape_stops_only_an_active_preview_and_consumes_that_browser_event():
    app = _bare_browser_app([_row("a")])
    stops: list[str] = []

    active_result = app._route_browser_escape(
        preview_is_active=True,
        stop_preview=lambda: stops.append("stop"),
    )
    idle_result = app._route_browser_escape(
        preview_is_active=False,
        stop_preview=lambda: stops.append("unexpected"),
    )

    assert active_result == "break"
    assert idle_result is None
    assert stops == ["stop"]


def test_browser_audition_exposes_event_to_dispatch_return_timing_only():
    app = _bare_browser_app([_row("a")])

    metric = app._measure_browser_preview_dispatch(
        event_timestamp_ns=1_000_000_000,
        dispatch=lambda: PreviewResult(ok=True),
        clock_ns=lambda: 1_012_000_000,
    )

    assert metric.event_timestamp_ns == 1_000_000_000
    assert metric.dispatch_return_timestamp_ns == 1_012_000_000
    assert metric.event_to_dispatch_return_ms == 12.0
    assert not hasattr(metric, "speaker_started_timestamp_ns")


def test_browser_arrow_keys_are_not_new_root_global_shortcuts():
    source = Path("src/workbench.py").read_text(encoding="utf-8")

    assert 'root.bind("<Up>"' not in source
    assert 'root.bind("<Down>"' not in source
