"""#1285 QML component coverage for inline/sticky Browser Loop handoff.

Authority: BrowserLoopOwner/Python owns Loop identity and phase. QML owns only
presentation state: visible owner index, inline-vs-sticky edge, and last truthful
edge memory. No delegate identity is product authority.
"""

from __future__ import annotations

import importlib.util
import time
from dataclasses import dataclass

import pytest

from src.browser_loop_playback import BrowserLoopExtent
from src.workbench_controller import WorkbenchRow
from src.workbench_qml import Screen1QmlInteractionAdapter, Screen1QmlViewModel, _qml_row

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("PySide6") is None,
    reason="PySide6 Qt Quick ist in dieser Testumgebung nicht installiert.",
)


def _wait_until(predicate, *, app, timeout_sec: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    app.processEvents()
    return bool(predicate())


def _row(index: int, *, owner: bool = False) -> WorkbenchRow:
    name = "owner-loop" if owner else f"row-{index:03d}"
    return WorkbenchRow(
        display_name=name,
        relative_path=f"sticky/{name}.wav",
        path=f"C:/sample-brain-synthetic/sticky/{name}.wav",
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


def _model(*, owner_index: int = 2, count: int = 60):
    rows = tuple(_row(i, owner=i == owner_index) for i in range(count))
    vm = Screen1QmlViewModel(
        state_id="screen1-default-3panel",
        library_labels=("Synthetic",),
        browser_rows=tuple(_qml_row(row) for row in rows),
        selected_browser_index=0,
        harmony_rows=(),
        live_kit_groups=(),
        browser_context="Synthetic",
    )
    vm.set_workspace_materialization(
        has_active_source=True,
        calm_canvas_visible=False,
        browser_materialized=True,
        live_kit_materialized=False,
    )
    vm.set_library_revealed(True)
    return vm, rows


@dataclass
class _LoopStub:
    owner_row: WorkbenchRow
    extent: BrowserLoopExtent
    reduced_capability_reason: str | None = None
    is_active: bool = True

    def current_source_phase_frame(self) -> int:
        return 250


def _loop(row: WorkbenchRow) -> _LoopStub:
    return _LoopStub(
        owner_row=row,
        extent=BrowserLoopExtent(100, 700, 2, (100, 400, 700)),
    )


def _named_items(root, name: str):
    found = []

    def walk(item):
        if item.objectName() == name:
            found.append(item)
        for child in item.childItems():
            walk(child)

    walk(root)
    return found


def _rendered_named_items(root, name: str):
    return [
        item
        for item in _named_items(root, name)
        if bool(item.property("visible")) and float(item.width()) > 0 and float(item.height()) > 0
    ]


def _cleanup(engine, window, app) -> None:
    window.close()
    app.processEvents()
    for name in ("_screen1_waveform_timer", "_screen1_browser_loop_timer"):
        timer = getattr(engine, name, None)
        if timer is not None:
            timer.stop()
    loader = getattr(engine, "_screen1_waveform_loader", None)
    if loader is not None:
        loader.close()


def test_owner_visible_scroll_top_and_return_are_strict_inline_xor_sticky():
    from PySide6.QtQuick import QQuickItem

    from src.workbench_qml_spike import _qml_engine, _settle_qml_frame

    vm, rows = _model(owner_index=2)
    adapter = Screen1QmlInteractionAdapter(view_model=vm)
    adapter.bind_browser_loop(_loop(rows[2]))
    app, engine, window = _qml_engine(vm, interaction_adapter=adapter)
    window.show()
    _settle_qml_frame(app)
    try:
        browser = window.findChild(QQuickItem, "browserList")
        sticky = window.findChild(QQuickItem, "browserLoopSticky")
        assert browser is not None and sticky is not None

        assert _wait_until(lambda: bool(browser.property("loopOwnerInlineVisible")), app=app)
        assert browser.property("loopStickyEdge") == "none"
        assert sticky.property("visible") is False
        assert len(_rendered_named_items(browser, "browserLoopInlineSurface")) == 1

        browser.setProperty("contentY", 600.0)
        assert _wait_until(lambda: browser.property("loopStickyEdge") == "top", app=app)
        assert browser.property("loopOwnerInlineVisible") is False
        assert sticky.property("visible") is True
        assert sticky.property("enabled") is False
        assert adapter.browser_loop_projection_snapshot().owner_path == str(rows[2].path)
        assert len(_rendered_named_items(browser, "browserLoopInlineSurface")) == 0

        browser.setProperty("contentY", 0.0)
        assert _wait_until(lambda: bool(browser.property("loopOwnerInlineVisible")), app=app)
        assert browser.property("loopStickyEdge") == "none"
        assert sticky.property("visible") is False
        assert len(_rendered_named_items(browser, "browserLoopInlineSurface")) == 1
    finally:
        _cleanup(engine, window, app)


def test_owner_below_viewport_uses_bottom_sticky_without_materializing_owner_delegate():
    from PySide6.QtQuick import QQuickItem

    from src.workbench_qml_spike import _qml_engine, _settle_qml_frame

    vm, rows = _model(owner_index=50)
    adapter = Screen1QmlInteractionAdapter(view_model=vm)
    adapter.bind_browser_loop(_loop(rows[50]))
    app, engine, window = _qml_engine(vm, interaction_adapter=adapter)
    window.show()
    _settle_qml_frame(app)
    try:
        browser = window.findChild(QQuickItem, "browserList")
        sticky = window.findChild(QQuickItem, "browserLoopSticky")
        assert browser is not None and sticky is not None
        assert _wait_until(lambda: browser.property("loopStickyEdge") == "bottom", app=app)
        assert browser.property("loopOwnerInlineVisible") is False
        assert sticky.property("visible") is True
        assert int(browser.property("loopOwnerVisibleIndex")) == 50
        assert adapter.browser_loop_projection_snapshot().owner_path == str(rows[50].path)
    finally:
        _cleanup(engine, window, app)


def test_search_hides_owner_but_sticky_persists_then_clearing_search_restores_inline_once():
    from PySide6.QtQuick import QQuickItem

    from src.workbench_qml_spike import _qml_engine, _settle_qml_frame

    vm, rows = _model(owner_index=2)
    adapter = Screen1QmlInteractionAdapter(view_model=vm)
    adapter.bind_browser_loop(_loop(rows[2]))
    app, engine, window = _qml_engine(vm, interaction_adapter=adapter)
    window.show()
    _settle_qml_frame(app)
    try:
        browser = window.findChild(QQuickItem, "browserList")
        search = window.findChild(QQuickItem, "browserSearch")
        sticky = window.findChild(QQuickItem, "browserLoopSticky")
        assert browser is not None and search is not None and sticky is not None
        assert _wait_until(lambda: bool(browser.property("loopOwnerInlineVisible")), app=app)

        search.setProperty("text", "row-050")
        assert _wait_until(lambda: int(browser.property("loopOwnerVisibleIndex")) == -1, app=app)
        assert browser.property("loopOwnerInlineVisible") is False
        assert browser.property("loopStickyEdge") in ("top", "bottom")
        assert sticky.property("visible") is True
        assert adapter.browser_loop_projection_snapshot().owner_path == str(rows[2].path)

        search.setProperty("text", "")
        assert _wait_until(lambda: bool(browser.property("loopOwnerInlineVisible")), app=app)
        assert browser.property("loopStickyEdge") == "none"
        assert sticky.property("visible") is False
        assert len(_rendered_named_items(browser, "browserLoopInlineSurface")) == 1
    finally:
        _cleanup(engine, window, app)


def test_rapid_boundary_crossing_never_exposes_inline_and_sticky_together():
    from PySide6.QtQuick import QQuickItem

    from src.workbench_qml_spike import _qml_engine, _settle_qml_frame

    vm, rows = _model(owner_index=30)
    adapter = Screen1QmlInteractionAdapter(view_model=vm)
    adapter.bind_browser_loop(_loop(rows[30]))
    app, engine, window = _qml_engine(vm, interaction_adapter=adapter)
    window.show()
    _settle_qml_frame(app)
    try:
        browser = window.findChild(QQuickItem, "browserList")
        sticky = window.findChild(QQuickItem, "browserLoopSticky")
        assert browser is not None and sticky is not None
        for y in (0.0, 500.0, 820.0, 1040.0, 820.0, 500.0, 0.0):
            browser.setProperty("contentY", y)
            _settle_qml_frame(app)
            app.processEvents()
            inline = bool(browser.property("loopOwnerInlineVisible"))
            sticky_visible = bool(sticky.property("visible"))
            assert inline != sticky_visible
    finally:
        _cleanup(engine, window, app)
