"""#692 P2 — Browser waveform requests follow the compact visible viewport.

Harmony already drives ``requestHarmonyWaveforms`` from ``contentY`` / height.
Browser must do the same for ``requestWaveforms`` so 30-DIP density does not
leave initially visible or scrolled rows as flat placeholders under the
bounded loader (``max_pending=14``).
"""

from __future__ import annotations

import importlib.util
import inspect
import math
import re

import pytest

from src.workbench_controller import WorkbenchRow
from src.workbench_qml import QML_SOURCE, _qml_row
from src import workbench_qml as workbench_qml_mod


BROWSER_LIST_MARKER = 'objectName: "browserList"'
HARMONIC_LIST_MARKER = 'objectName: "harmonicMatchList"'
PREFETCH_MARGIN = 2


def _snippet(source: str, marker: str, span: int) -> str:
    index = source.index(marker)
    return source[index : index + span]


def _browser_list_block(source: str) -> str:
    # Through the closing of the Browser ListView, before Harmonic pane.
    start = source.index(BROWSER_LIST_MARKER)
    end = source.index('objectName: "elasticHandleAfterBrowser"', start)
    return source[start:end]


def _harmonic_list_block(source: str) -> str:
    return _snippet(source, HARMONIC_LIST_MARKER, 2500)


def test_browser_listview_requests_waveforms_from_actual_visible_geometry():
    browser = _browser_list_block(QML_SOURCE)
    harmonic = _harmonic_list_block(QML_SOURCE)

    assert "onContentYChanged" in browser
    assert "onHeightChanged" in browser
    assert "onContentHeightChanged" in browser
    assert "requestWaveforms(" in browser
    assert "indexAt(" in browser
    assert "waveformFirstVisibleIndex" in browser
    assert "waveformLastVisibleIndex" in browser
    assert "Math.floor(contentY / rowHeight)" not in browser
    assert "Math.ceil(height / rowHeight)" not in browser
    assert f"waveformPrefetchMargin: {PREFETCH_MARGIN}" in browser

    # Harmonic remains virtualized; Browser now needs geometry-aware discovery
    # because #1285 introduces one variable-height inline owner row.
    assert "requestHarmonyWaveforms(" in harmonic
    assert "onContentYChanged" in harmonic
    assert "onHeightChanged" in harmonic


def test_browser_waveform_seed_is_not_rigid_zero_to_twenty_product_assumption():
    engine_src = inspect.getsource(workbench_qml_mod._qml_engine)
    assert "request_waveforms(0, 20)" not in engine_src
    assert re.search(r"request_waveforms\(\s*0\s*,\s*20\s*\)", engine_src) is None


def test_browser_virtualization_and_interaction_contracts_stay_green():
    browser = _browser_list_block(QML_SOURCE)
    assert "reuseItems: true" in browser
    assert "previewRow(index)" in QML_SOURCE
    assert "selectRow(index)" in QML_SOURCE
    assert 'objectName: "browserSearch"' in QML_SOURCE
    assert (
        'else if (event.key === Qt.Key_Escape) '
        '{ window.interaction.escapeLiveKitContext(); event.accepted = true }'
    ) in browser


def test_bounded_loader_defaults_remain_unchanged_in_engine():
    engine_src = inspect.getsource(workbench_qml_mod._qml_engine)
    assert "max_pending=14" in engine_src
    assert "capacity=48" in engine_src


def _blank_qml_rows(count: int):
    rows = []
    for index in range(count):
        row = WorkbenchRow(
            display_name=f"row-{index:03d}",
            relative_path=f"viewport/{index:03d}.wav",
            path=f"C:/sample-brain-synthetic/viewport/{index:03d}.wav",
            bpm=120.0,
            key="Am",
            key_conf=1.0,
            loudness=None,
            brightness=None,
            sample_class=None,
            pred_type="loop",
            status="ok",
            details={},
        )
        rows.append(_qml_row(row))
    return tuple(rows)


def _expected_range(*, content_y: float, height: float, row_height: int) -> tuple[int, int]:
    start = max(0, int(math.floor(content_y / row_height)))
    count = int(math.ceil(height / row_height)) + PREFETCH_MARGIN
    return start, count


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="PySide6 Qt Quick ist in dieser Testumgebung nicht installiert.",
)
def test_compact_viewport_requests_full_visible_browser_waveform_range(monkeypatch):
    from PySide6.QtQuick import QQuickItem

    from src.workbench_harmony import HarmonicMatchLibraryController
    from src.workbench_qml_spike import (
        Screen1QmlInteractionAdapter,
        _qml_engine,
        _settle_qml_frame,
        build_qml_view_model_from_fixture,
    )
    from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1

    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(fixture, "screen1-default-3panel")
    blank_rows = _blank_qml_rows(48)
    view_model.browser_rows = blank_rows
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        harmony_controller=HarmonicMatchLibraryController(),
    )

    requested: list[tuple[int, int]] = []
    real_request = None

    def tracking_request(start: int, count: int) -> None:
        requested.append((start, count))
        assert real_request is not None
        real_request(start, count)

    original_bridge = workbench_qml_mod._qml_interaction_bridge

    def wrapped_bridge(*args, **kwargs):
        nonlocal real_request
        on_waveform_request = kwargs.get("on_waveform_request")
        real_request = on_waveform_request

        def tracked(start: int, count: int) -> None:
            tracking_request(start, count)

        kwargs = dict(kwargs)
        kwargs["on_waveform_request"] = tracked
        return original_bridge(*args, **kwargs)

    monkeypatch.setattr(workbench_qml_mod, "_qml_interaction_bridge", wrapped_bridge)

    app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    window.show()
    _settle_qml_frame(app)
    try:
        browser = window.findChild(QQuickItem, "browserList")
        assert browser is not None
        row_height = int(window.property("densityRowHeight"))
        assert row_height == 30
        height = float(browser.property("height"))
        content_y = float(browser.property("contentY") or 0.0)
        assert height > row_height * 10

        expected_start = int(browser.property("waveformFirstVisibleIndex"))
        expected_last = int(browser.property("waveformLastVisibleIndex"))
        expected_count = min(len(blank_rows), expected_last + 1 + PREFETCH_MARGIN) - expected_start
        assert expected_count > 20, "compact viewport must exceed legacy 0..20 seed"

        assert requested, "Browser viewport must request waveforms after layout"
        latest_start, latest_count = requested[-1]
        assert latest_start == expected_start
        assert latest_count == expected_count

        loader = engine._screen1_waveform_loader
        assert loader._max_pending == 14
        # Bounded queue: first fill saturates at max_pending, not full viewport.
        assert loader.pending_count <= 14
    finally:
        window.close()
        app.processEvents()
        timer = getattr(engine, "_screen1_waveform_timer", None)
        if timer is not None:
            timer.stop()
        loader = getattr(engine, "_screen1_waveform_loader", None)
        if loader is not None:
            loader.close()


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="PySide6 Qt Quick ist in dieser Testumgebung nicht installiert.",
)
def test_browser_scroll_and_resize_update_waveform_request_range(monkeypatch):
    from PySide6.QtQuick import QQuickItem

    from src.workbench_harmony import HarmonicMatchLibraryController
    from src.workbench_qml_spike import (
        Screen1QmlInteractionAdapter,
        _qml_engine,
        _settle_qml_frame,
        build_qml_view_model_from_fixture,
    )
    from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1

    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(fixture, "screen1-default-3panel")
    view_model.browser_rows = _blank_qml_rows(60)
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        harmony_controller=HarmonicMatchLibraryController(),
    )

    requested: list[tuple[int, int]] = []
    original_bridge = workbench_qml_mod._qml_interaction_bridge

    def wrapped_bridge(*args, **kwargs):
        on_waveform_request = kwargs.get("on_waveform_request")

        def tracked(start: int, count: int) -> None:
            requested.append((start, count))
            if on_waveform_request is not None:
                on_waveform_request(start, count)

        kwargs = dict(kwargs)
        kwargs["on_waveform_request"] = tracked
        return original_bridge(*args, **kwargs)

    monkeypatch.setattr(workbench_qml_mod, "_qml_interaction_bridge", wrapped_bridge)

    app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    window.show()
    _settle_qml_frame(app)
    try:
        browser = window.findChild(QQuickItem, "browserList")
        assert browser is not None
        row_height = int(window.property("densityRowHeight"))

        browser.setProperty("contentY", float(row_height * 10))
        app.processEvents()
        _settle_qml_frame(app)
        height = float(browser.property("height"))
        content_y = float(browser.property("contentY"))
        scroll_start = int(browser.property("waveformFirstVisibleIndex"))
        scroll_last = int(browser.property("waveformLastVisibleIndex"))
        scroll_count = min(60, scroll_last + 1 + PREFETCH_MARGIN) - scroll_start
        assert requested[-1] == (scroll_start, scroll_count)
        assert scroll_start >= 10

        original_height = height
        window.setProperty("height", 640)
        app.processEvents()
        _settle_qml_frame(app)
        new_height = float(browser.property("height"))
        assert new_height < original_height
        content_y = float(browser.property("contentY"))
        resize_start = int(browser.property("waveformFirstVisibleIndex"))
        resize_last = int(browser.property("waveformLastVisibleIndex"))
        resize_count = min(60, resize_last + 1 + PREFETCH_MARGIN) - resize_start
        assert requested[-1] == (resize_start, resize_count)
        assert resize_count < scroll_count
    finally:
        window.close()
        app.processEvents()
        timer = getattr(engine, "_screen1_waveform_timer", None)
        if timer is not None:
            timer.stop()
        loader = getattr(engine, "_screen1_waveform_loader", None)
        if loader is not None:
            loader.close()


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="PySide6 Qt Quick ist in dieser Testumgebung nicht installiert.",
)
def test_browser_drain_rerequests_visible_range_under_bounded_pending(monkeypatch):
    """max_pending stays 14; drain frees slots and viewport re-request fills the rest."""
    from PySide6.QtQuick import QQuickItem

    from src.workbench_harmony import HarmonicMatchLibraryController
    from src.workbench_qml_spike import (
        Screen1QmlInteractionAdapter,
        _qml_engine,
        _settle_qml_frame,
        build_qml_view_model_from_fixture,
    )
    from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1

    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(fixture, "screen1-default-3panel")
    view_model.browser_rows = _blank_qml_rows(40)
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        harmony_controller=HarmonicMatchLibraryController(),
    )

    # Fast deterministic envelopes — no audio I/O.
    monkeypatch.setattr(
        workbench_qml_mod,
        "compute_waveform_envelope",
        lambda path, max_points=96: tuple(
            0.25 for _ in range(max(8, int(max_points) // 4))
        ),
    )

    app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    window.show()
    _settle_qml_frame(app)
    try:
        browser = window.findChild(QQuickItem, "browserList")
        assert browser is not None
        row_height = int(window.property("densityRowHeight"))
        height = float(browser.property("height"))
        start, count = _expected_range(
            content_y=float(browser.property("contentY") or 0.0),
            height=height,
            row_height=row_height,
        )
        visible_end = min(len(view_model.browser_rows), start + count)
        assert visible_end - start > 14

        loader = engine._screen1_waveform_loader
        deadline = 80
        for _ in range(deadline):
            if loader.wait_for_result(timeout=0.05):
                pass
            app.processEvents()
            ready = sum(
                1
                for row in view_model.browser_rows[start:visible_end]
                if row.waveform_envelope
            )
            if ready >= visible_end - start:
                break
        ready = sum(
            1
            for row in view_model.browser_rows[start:visible_end]
            if row.waveform_envelope
        )
        assert ready == visible_end - start
        assert loader._max_pending == 14
    finally:
        window.close()
        app.processEvents()
        timer = getattr(engine, "_screen1_waveform_timer", None)
        if timer is not None:
            timer.stop()
        loader = getattr(engine, "_screen1_waveform_loader", None)
        if loader is not None:
            loader.close()


@pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="PySide6 Qt Quick ist in dieser Testumgebung nicht installiert.",
)
def test_variable_height_loop_owner_uses_actual_visible_geometry_not_fixed_row_math(monkeypatch):
    from types import SimpleNamespace

    from PySide6.QtQuick import QQuickItem

    from src.browser_loop_playback import BrowserLoopExtent
    from src.workbench_harmony import HarmonicMatchLibraryController
    from src.workbench_qml_spike import (
        Screen1QmlInteractionAdapter,
        _qml_engine,
        _settle_qml_frame,
        build_qml_view_model_from_fixture,
    )
    from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1

    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(fixture, "screen1-default-3panel")
    blank_rows = _blank_qml_rows(60)
    view_model.browser_rows = blank_rows
    owner = blank_rows[2].source_row
    loop = SimpleNamespace(
        owner_row=owner,
        extent=BrowserLoopExtent(100, 700, 2, (100, 400, 700)),
        is_active=True,
        reduced_capability_reason=None,
        current_source_phase_frame=lambda: 250,
    )
    adapter = Screen1QmlInteractionAdapter(
        view_model=view_model,
        harmony_controller=HarmonicMatchLibraryController(),
    )
    adapter.bind_browser_loop(loop)

    requested: list[tuple[int, int]] = []
    original_bridge = workbench_qml_mod._qml_interaction_bridge

    def wrapped_bridge(*args, **kwargs):
        on_waveform_request = kwargs.get("on_waveform_request")

        def tracked(start: int, count: int) -> None:
            requested.append((start, count))
            if on_waveform_request is not None:
                on_waveform_request(start, count)

        kwargs = dict(kwargs)
        kwargs["on_waveform_request"] = tracked
        return original_bridge(*args, **kwargs)

    monkeypatch.setattr(workbench_qml_mod, "_qml_interaction_bridge", wrapped_bridge)

    app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    window.show()
    _settle_qml_frame(app)
    try:
        browser = window.findChild(QQuickItem, "browserList")
        assert browser is not None
        normal_height = int(window.property("densityRowHeight"))
        assert int(browser.property("loopOwnerRowHeight")) > normal_height * 2

        browser.setProperty("contentY", 180.0)
        app.processEvents()
        _settle_qml_frame(app)

        content_y = float(browser.property("contentY"))
        first = int(browser.property("waveformFirstVisibleIndex"))
        last = int(browser.property("waveformLastVisibleIndex"))
        assert first >= 0 and last >= first
        assert first != int(math.floor(content_y / normal_height))

        expected_count = min(60, last + 1 + PREFETCH_MARGIN) - first
        assert requested[-1] == (first, expected_count)
    finally:
        window.close()
        app.processEvents()
        timer = getattr(engine, "_screen1_waveform_timer", None)
        if timer is not None:
            timer.stop()
        loader = getattr(engine, "_screen1_waveform_loader", None)
        if loader is not None:
            loader.close()
