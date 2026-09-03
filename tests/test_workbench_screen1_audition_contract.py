"""RED contracts for Screen 1 browser-local sample auditioning (#503).

These tests deliberately exercise the smallest app-facing interaction seam that
Phase C must provide.  They use no Tk root or audio device: a browser row is a
``WorkbenchRow`` and preview calls are recorded by a fake.
"""

from __future__ import annotations

from pathlib import Path
from types import MethodType, SimpleNamespace

import pytest

from src import workbench
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


def test_browser_navigation_carries_handler_entry_time_through_detail_work(
    monkeypatch,
):
    app = _bare_browser_app([_row("a"), _row("b")])
    app._tree = SimpleNamespace(
        selection=lambda: ("0",),
        selection_set=lambda _target: None,
        see=lambda _target: None,
    )
    app._skip_next_browser_selection_preview = None
    clock = {"now": 1_000_000_000}
    elapsed_ms: list[float] = []
    monkeypatch.setattr(workbench, "monotonic_ns", lambda: clock["now"])
    app._set_detail = lambda _row: clock.update(now=1_012_000_000)
    app._play_preview = lambda: None
    app._measure_browser_preview_dispatch = lambda **kwargs: elapsed_ms.append(
        (clock["now"] - kwargs["event_timestamp_ns"]) / 1_000_000
    )

    assert app._on_browser_navigation("next", SimpleNamespace()) == "break"

    assert elapsed_ms == [12.0]


def test_selection_carries_handler_entry_time_through_detail_work(monkeypatch):
    app = _bare_browser_app([_row("a")])
    app._tree = SimpleNamespace(selection=lambda: ("0",))
    app._preview = SimpleNamespace(current_path=None)
    app._skip_next_browser_selection_preview = None
    captured: list[int] = []
    monkeypatch.setattr(workbench, "monotonic_ns", lambda: 2_000_000_000)
    app._set_detail = lambda _row: setattr(app, "_detail_updated", True)
    app._play_preview = lambda: None
    app._measure_browser_preview_dispatch = lambda **kwargs: captured.append(
        kwargs["event_timestamp_ns"]
    )

    app._on_select()

    assert app._detail_updated is True
    assert captured == [2_000_000_000]


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


def test_waveform_click_carries_handler_entry_time_to_preview_dispatch(monkeypatch):
    row = _row("a")
    app = _bare_browser_app([row])
    app._detail_row = row
    app._loop_edit_mode_var = SimpleNamespace(get=lambda: False)
    app._attack_edit_mode_var = SimpleNamespace(get=lambda: False)
    app._set_status = lambda *_args, **_kwargs: None
    app._play_preview = lambda: None
    captured: list[int] = []
    monkeypatch.setattr(workbench, "monotonic_ns", lambda: 3_000_000_000)
    app._measure_browser_preview_dispatch = lambda **kwargs: captured.append(
        kwargs["event_timestamp_ns"]
    )

    app._on_waveform_click(SimpleNamespace(state=0, x=0))

    assert captured == [3_000_000_000]


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


def test_tree_double_click_does_not_dispatch_after_selection_already_auditioned():
    app = _bare_browser_app([_row("a")])
    calls: list[str] = []
    app._tree = SimpleNamespace(selection=lambda: ("0",))
    app._preview = SimpleNamespace(current_path=None)
    app._skip_next_browser_selection_preview = None
    app._set_detail = lambda _row: None
    app._play_preview = lambda: calls.append("play")
    app._measure_browser_preview_dispatch = lambda **kwargs: kwargs["dispatch"]()

    app._on_select()
    app._on_tree_double_click()

    assert calls == ["play"]


def test_browser_edge_navigation_does_not_leave_stale_selection_suppression():
    row = _row("a")
    app = _bare_browser_app([row])
    app._tree = SimpleNamespace(
        selection=lambda: ("0",),
        selection_set=lambda _target: None,
        see=lambda _target: None,
    )
    app._skip_next_browser_selection_preview = None
    app._audition_browser_row = lambda *_args, **_kwargs: None

    assert app._on_browser_navigation("previous", SimpleNamespace()) == "break"

    assert app._skip_next_browser_selection_preview is None


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
