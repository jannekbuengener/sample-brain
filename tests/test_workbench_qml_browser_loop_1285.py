from __future__ import annotations

from dataclasses import fields

import pytest

from src.browser_loop_playback import BrowserLoopExtent, BrowserLoopResult
from src.workbench_controller import WorkbenchRow
from src import workbench_qml as qml


def _view_model() -> qml.Screen1QmlViewModel:
    return qml.Screen1QmlViewModel(
        state_id="screen1-default-3panel",
        library_labels=(),
        browser_rows=(),
        selected_browser_index=-1,
        harmony_rows=(),
        live_kit_groups=(),
    )


def _row(name: str = "Loop A", path: str = "C:/synthetic/loop-a.wav") -> WorkbenchRow:
    return WorkbenchRow(
        display_name=name,
        relative_path="synthetic/loop-a.wav",
        path=path,
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


class _LoopStub:
    def __init__(
        self,
        *,
        row: WorkbenchRow | None,
        extent: BrowserLoopExtent | None,
        phase: int | None,
        reason: str | None = None,
    ) -> None:
        self.owner_row = row
        self.extent = extent
        self._phase = phase
        self.reduced_capability_reason = reason

    @property
    def is_active(self) -> bool:
        return self.owner_row is not None and self.extent is not None

    def current_source_phase_frame(self) -> int | None:
        return self._phase


def _snapshot_type():
    assert hasattr(qml, "BrowserLoopProjectionSnapshot")
    return qml.BrowserLoopProjectionSnapshot


def test_1285_loop_projection_idle_is_empty_and_does_not_duplicate_sync() -> None:
    snapshot_type = _snapshot_type()
    adapter = qml.Screen1QmlInteractionAdapter(view_model=_view_model())

    snapshot = adapter.browser_loop_projection_snapshot()

    assert snapshot == snapshot_type.idle()
    assert snapshot.active is False
    assert snapshot.owner_path == ""
    assert snapshot.owner_name == ""
    assert snapshot.progress == 0.0
    assert snapshot.bar_count == 0
    assert snapshot.bar_positions == ()
    assert snapshot.reduced_capability_reason == ""
    assert snapshot.playback_available is False
    assert "sync_enabled" not in {field.name for field in fields(snapshot_type)}
    assert "syncEnabled" not in {field.name for field in fields(snapshot_type)}


def test_1285_loop_projection_derives_identity_grid_and_phase_from_owner() -> None:
    row = _row()
    extent = BrowserLoopExtent(
        source_start_frame=100,
        source_end_frame_exclusive=700,
        bar_count=2,
        downbeat_frames=(100, 300, 700),
    )
    adapter = qml.Screen1QmlInteractionAdapter(view_model=_view_model())
    adapter.bind_browser_loop(_LoopStub(row=row, extent=extent, phase=400))

    snapshot = adapter.browser_loop_projection_snapshot()

    assert snapshot.active is True
    assert snapshot.owner_path == str(row.path)
    assert snapshot.owner_name == row.display_name
    assert snapshot.bar_count == 2
    assert snapshot.bar_positions == pytest.approx((0.0, 1.0 / 3.0, 1.0))
    assert snapshot.progress == pytest.approx(0.5)
    assert snapshot.reduced_capability_reason == ""
    assert snapshot.playback_available is True


def test_1285_loop_projection_clamps_phase_to_half_open_unit_interval() -> None:
    row = _row()
    extent = BrowserLoopExtent(100, 700, 1, (100, 700))
    adapter = qml.Screen1QmlInteractionAdapter(view_model=_view_model())
    adapter.bind_browser_loop(_LoopStub(row=row, extent=extent, phase=900))

    snapshot = adapter.browser_loop_projection_snapshot()

    assert 0.0 <= snapshot.progress < 1.0


def test_1285_reduced_capability_preserves_owner_but_marks_playback_unavailable() -> None:
    row = _row()
    extent = BrowserLoopExtent(100, 700, 1, (100, 700))
    adapter = qml.Screen1QmlInteractionAdapter(view_model=_view_model())
    adapter.bind_browser_loop(
        _LoopStub(row=row, extent=extent, phase=250, reason="SYNC_NOT_SYNCABLE")
    )

    snapshot = adapter.browser_loop_projection_snapshot()

    assert snapshot.active is True
    assert snapshot.owner_path == str(row.path)
    assert snapshot.reduced_capability_reason == "SYNC_NOT_SYNCABLE"
    assert snapshot.playback_available is False


def test_1285_bridge_projects_one_snapshot_shape_and_context_owner_truth() -> None:
    pytest.importorskip("PySide6")
    row = _row()
    extent = BrowserLoopExtent(100, 700, 2, (100, 400, 700))
    adapter = qml.Screen1QmlInteractionAdapter(view_model=_view_model())
    adapter.bind_browser_loop(_LoopStub(row=row, extent=extent, phase=250))
    adapter._sample_context_target = row

    bridge = qml._qml_interaction_bridge(adapter)

    assert bridge.property("browserLoopActive") is True
    assert bridge.property("browserLoopOwnerPath") == str(row.path)
    assert bridge.property("browserLoopOwnerName") == row.display_name
    assert bridge.property("browserLoopProgress") == pytest.approx(0.25)
    assert bridge.property("browserLoopBarCount") == 2
    assert list(bridge.property("browserLoopBarPositions")) == pytest.approx([0.0, 0.5, 1.0])
    assert bridge.property("browserLoopReducedCapabilityReason") == ""
    assert bridge.property("browserLoopPlaybackAvailable") is True
    assert bridge.property("contextTargetIsLoopOwner") is True
    assert bridge.metaObject().indexOfProperty("syncEnabled") == -1


def test_1285_refresh_playback_projection_emits_one_state_change() -> None:
    pytest.importorskip("PySide6")
    row = _row()
    extent = BrowserLoopExtent(100, 700, 1, (100, 700))
    adapter = qml.Screen1QmlInteractionAdapter(view_model=_view_model())
    loop = _LoopStub(row=row, extent=extent, phase=250)
    adapter.bind_browser_loop(loop)
    bridge = qml._qml_interaction_bridge(adapter)
    emissions: list[None] = []
    bridge.state_changed.connect(lambda: emissions.append(None))

    bridge.refreshPlaybackProjection()

    assert len(emissions) == 1
    assert bridge.property("browserLoopProgress") == pytest.approx(0.25)


class _ToggleLoopStub(_LoopStub):
    def __init__(
        self,
        *,
        row: WorkbenchRow | None = None,
        reject_path: str | None = None,
    ) -> None:
        extent = BrowserLoopExtent(100, 700, 1, (100, 700)) if row is not None else None
        super().__init__(row=row, extent=extent, phase=250 if row is not None else None)
        self.reject_path = reject_path
        self.loop_on_calls: list[WorkbenchRow] = []
        self.loop_off_calls = 0

    def loop_on(self, row: WorkbenchRow) -> BrowserLoopResult:
        self.loop_on_calls.append(row)
        if self.reject_path is not None and str(row.path) == self.reject_path:
            return BrowserLoopResult(
                ok=False,
                message="LOOP unavailable: synthetic rejection.",
                reason_code="SYNTHETIC_REJECT",
            )
        self.owner_row = row
        self.extent = BrowserLoopExtent(100, 700, 1, (100, 700))
        self._phase = 100
        self.reduced_capability_reason = None
        return BrowserLoopResult(ok=True, owner_path=str(row.path), bar_count=1)

    def loop_off(self) -> BrowserLoopResult:
        self.loop_off_calls += 1
        self.owner_row = None
        self.extent = None
        self._phase = None
        self.reduced_capability_reason = None
        return BrowserLoopResult(ok=True, message="LOOP OFF")


def _context_view_model() -> tuple[qml.Screen1QmlViewModel, WorkbenchRow, WorkbenchRow]:
    row_a = _row("Loop A", "C:/synthetic/loop-a.wav")
    row_b = _row("Loop B", "C:/synthetic/loop-b.wav")
    vm = _view_model()
    vm.set_browser_state(
        rows=(row_a, row_b),
        selected_index=0,
        browser_context="test",
        error=None,
    )
    return vm, row_a, row_b


def test_1285_context_loop_toggle_turns_on_target_b_without_selection_or_preview_mutation() -> None:
    vm, _row_a, row_b = _context_view_model()
    previews: list[WorkbenchRow] = []
    loop = _ToggleLoopStub()
    adapter = qml.Screen1QmlInteractionAdapter(
        view_model=vm,
        on_preview_requested=lambda row, **_kwargs: previews.append(row),
    )
    adapter.bind_browser_loop(loop)
    adapter._preview_active = True

    adapter.open_sample_context(1)
    result = adapter.request_context_loop_toggle()

    assert result.ok is True
    assert loop.loop_on_calls == [row_b]
    assert loop.owner_row is row_b
    assert vm.selected_browser_index == 0
    assert previews == []
    assert adapter.preview_active is True
    assert adapter.sample_context_target is None
    assert adapter.browser_loop_context_status == ""


def test_1285_context_loop_toggle_turns_off_only_when_target_is_current_owner() -> None:
    vm, _row_a, row_b = _context_view_model()
    loop = _ToggleLoopStub(row=row_b)
    adapter = qml.Screen1QmlInteractionAdapter(view_model=vm)
    adapter.bind_browser_loop(loop)

    adapter.open_sample_context(1)
    result = adapter.request_context_loop_toggle()

    assert result.ok is True
    assert loop.loop_off_calls == 1
    assert loop.loop_on_calls == []
    assert loop.owner_row is None
    assert vm.selected_browser_index == 0
    assert adapter.sample_context_target is None


def test_1285_context_loop_toggle_rejection_preserves_old_owner_and_target_for_status() -> None:
    vm, row_a, row_b = _context_view_model()
    loop = _ToggleLoopStub(row=row_a, reject_path=str(row_b.path))
    adapter = qml.Screen1QmlInteractionAdapter(view_model=vm)
    adapter.bind_browser_loop(loop)

    adapter.open_sample_context(1)
    result = adapter.request_context_loop_toggle()

    assert result.ok is False
    assert loop.loop_on_calls == [row_b]
    assert loop.owner_row is row_a
    assert adapter.sample_context_target is row_b
    assert adapter.browser_loop_context_status == result.message
    assert adapter.browser_loop_projection_snapshot().owner_path == str(row_a.path)


def test_1285_context_loop_toggle_without_target_is_fail_closed_and_dispatches_nothing() -> None:
    vm, row_a, _row_b = _context_view_model()
    loop = _ToggleLoopStub(row=row_a)
    adapter = qml.Screen1QmlInteractionAdapter(view_model=vm)
    adapter.bind_browser_loop(loop)

    result = adapter.request_context_loop_toggle()

    assert result.ok is False
    assert result.reason_code == "NO_CONTEXT_TARGET"
    assert loop.loop_on_calls == []
    assert loop.loop_off_calls == 0
    assert loop.owner_row is row_a


def test_1285_bridge_context_loop_toggle_returns_success_and_projects_status() -> None:
    pytest.importorskip("PySide6")
    vm, _row_a, row_b = _context_view_model()
    loop = _ToggleLoopStub()
    adapter = qml.Screen1QmlInteractionAdapter(view_model=vm)
    adapter.bind_browser_loop(loop)
    adapter.open_sample_context(1)
    bridge = qml._qml_interaction_bridge(adapter)

    assert bridge.contextLoopToggle() is True
    assert loop.owner_row is row_b
    assert bridge.property("browserLoopContextStatus") == ""



def _browser_block() -> str:
    source = qml.QML_SOURCE
    start = source.index('objectName: "browserList"')
    end = source.index('objectName: "elasticHandleAfterBrowser"', start)
    return source[start:end]


def test_1285_inline_loop_owner_is_path_bound_and_materially_expands_only_owner_row() -> None:
    browser = _browser_block()
    assert "isLoopOwner" in browser
    assert "browserLoopOwnerPath" in browser
    assert 'modelData.path' in browser
    assert "property int loopOwnerRowHeight" in browser
    assert "height: browserRow.isLoopOwner ? browser.loopOwnerRowHeight : browser.rowHeight" in browser
    assert "height =" not in browser.split("delegate: Rectangle", 1)[1].split("RowLayout", 1)[0]


def test_1285_inline_loop_surface_is_nearly_full_width_and_recedes_ordinary_metadata() -> None:
    browser = _browser_block()
    assert 'objectName: "browserLoopInlineSurface"' in browser
    assert 'objectName: "browserLoopInlineWaveform"' in browser
    assert "anchors.left: parent.left" in browser
    assert "anchors.right: parent.right" in browser
    assert "browserLoopBarPositions" in browser
    assert "visible: !browserRow.isLoopOwner" in browser
    assert "bpmCell" in browser and "keyCell" in browser and "lengthCell" in browser and "typeCell" in browser
    inline_start = browser.index('objectName: "browserLoopInlineSurface"')
    inline_end = browser.index("RowLayout", inline_start)
    inline = browser[inline_start:inline_end]
    assert "BPM" not in inline and "KEY" not in inline and "LENGTH" not in inline and "TYPE" not in inline
    assert "Arrangement" not in inline and "Timeline" not in inline and "Pattern" not in inline


def test_1285_inline_loop_owner_does_not_use_ordinary_hover_scale_or_luminance() -> None:
    browser = _browser_block()
    assert "!browserRow.isLoopOwner && browser.hoveredWaveformIndex === index" in browser
    assert "!browserRow.isLoopOwner && browser.hoveredWaveformIndex >= 0" in browser



def test_1285_loop_playhead_uses_one_authoritative_shared_refresh_driver() -> None:
    source = qml.QML_SOURCE
    browser = _browser_block()
    assert source.count("FrameAnimation {") == 1
    assert "readonly property bool loopPlayheadArmed:" in source
    assert "window.interaction.browserLoopActive" in source
    assert "window.interaction.browserLoopPlaybackAvailable" in source
    assert 'window.waveformMotionMode !== "off"' in source
    assert "refreshPlaybackProjection()" in source
    assert 'objectName: "browserLoopInlinePlayhead"' in browser
    assert "window.interaction.browserLoopProgress" in browser
    assert "visible: window.loopPlayheadArmed" in browser


def test_1285_loop_grid_and_playhead_never_invent_phase_in_qml() -> None:
    browser = _browser_block()
    assert "browserLoopBarPositions" in browser
    assert "Date.now" not in browser
    assert "performance.now" not in browser
    assert "NumberAnimation" not in browser
    assert "Timer {" not in browser
    assert "browserLoopProgress +" not in browser
    assert "browserLoopProgress +=" not in browser
    assert "browserLoopProgress =" not in browser



def test_1285_sticky_is_one_non_actionable_viewport_child_and_not_a_second_owner() -> None:
    source = qml.QML_SOURCE
    viewport_start = source.index('objectName: "browserListViewport"')
    viewport_end = source.index('objectName: "elasticHandleAfterBrowser"', viewport_start)
    viewport = source[viewport_start:viewport_end]
    assert source.count('objectName: "browserLoopSticky"') == 1
    assert 'objectName: "browserLoopSticky"' in viewport
    assert "loopStickyEdge" in viewport
    assert "loopOwnerVisibleIndex" in viewport
    assert "loopOwnerInlineVisible" in viewport
    assert "enabled: false" in viewport
    sticky_start = viewport.index('objectName: "browserLoopSticky"')
    sticky = viewport[sticky_start:]
    assert "MouseArea" not in sticky
    assert "requestLoop" not in sticky
    assert "contextLoopToggle" not in sticky
    assert "browserLoopOwnerName" in sticky
    assert "browserLoopBarPositions" in sticky
    assert "browserLoopProgress" in sticky


def test_1285_owner_index_scan_is_not_on_frame_refresh_path() -> None:
    source = qml.QML_SOURCE
    browser = _browser_block()
    assert "function resolveLoopOwnerIndex()" in browser
    assert "function reconcileLoopPresentation()" in browser
    assert "onLoopOwnerPathProjectionChanged" in browser
    assert "onModelChanged" in browser
    frame_start = source.index("FrameAnimation {")
    frame_end = source.index("}", frame_start)
    frame = source[frame_start:frame_end]
    assert "resolveLoopOwnerIndex" not in frame
    assert "reconcileLoopPresentation" not in frame
