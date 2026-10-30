from __future__ import annotations

from dataclasses import fields

import pytest

from src.browser_loop_playback import BrowserLoopExtent
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
