"""#1080 Slice A TEST_FREEZE — gated Arrangement shell + read-only projection.

Canonical authority:
- docs/PRODUCT_WORKFLOW_CANON.md (#1075/#1076/#1077)
- docs/PROGRAM_CHROME_CONTRACT.md
- docs/ARRANGEMENT_32_FIELD_TIME_CONTRACT.md (#1083/#1086)
- docs/SESSION_OWNERSHIP_CONTRACT.md (#678/#809)
- docs/design/1079-arrangement-visual-gate/DESIGN_CONTRACT.md (Direction B)
- src/workbench_session.py (#1078 projection-mode owner)
- src/arrangement_32_field_time.py (#1086 single Pattern truth)
- src/workbench_feature_settings.py (`arrangement_mode_enabled` gate)

Slice A scope (frozen): gated Arrangement shell, read-only 32-field/8-bar
Pattern projection, Edit↔Arrangement transition + return. QML owns
projection/presentation only. Python (`WorkbenchSession`) stays the single
projection-mode owner; the single Pattern truth stays in `channel_rack`.

Explicitly out of scope for Slice A (later slices): Step/block/mask/marker
mutation, zoom/pan/timeline, end marker, Live surface, any QML-owned mode
state, Pattern copy, or QML-only feature flag.

Frozen gates (do not weaken during implementation):
1. feature OFF => no Arrangement route/scene/shortcut; Edit stays functional;
2. EDIT default projection (complete, inert 32-field geometry);
3. successful #1078 entry => exactly one Arrangement surface + same active
   track/session identity;
4. exactly 32 sequencer fields projected;
5. 8 bars x 4 fields grouping;
6. no active Step => quiet upper stage projection;
7. first active Step => active upper stage projection (projection only);
8. no second Pattern owner (identity projection, no truth copy, no mutation
   seams);
9. return to Edit preserves active track/Kit/Pattern/Arrangement state;
10. entry keeps playback parked; the Arrangement stage owns focus and carries
    no audition wiring;
11. no separate Step Sequencer top-level mode; pure projection/return
    performs no serialization.

FREEZE_CORRECTIONS (explicit, pre-merge; gate semantics unchanged):
- Pattern preservation across entry asserts *equality*, matching the frozen
  #1078 contract (entry's media rebase legitimately rebuilds the rack state
  object) instead of object identity.
- Runtime delegate counting uses the visual ``childItems()`` walk — the
  established Workbench pattern; ``findChildren`` does not reach Repeater
  delegates under a Loader.
- Chrome vocabulary canon (`test_production_shell_owns_the_shared_renderer_
  and_minimal_chrome`) forbids the literal Edit-mode word in ``QML_SOURCE``:
  the entry slot is ``enterArrangement()`` and the return routes through the
  Browser nav (the Edit destination) as ``returnToBrowser()``; the stage
  itself is a fully non-interactive read-only projection.
"""

from __future__ import annotations

import importlib
import importlib.util
import re
from dataclasses import replace
from fractions import Fraction
from types import SimpleNamespace

import pytest

from src import track_package as tp
from src import workbench_session as ws
from src.arrangement_32_field_time import (
    TOTAL_FIELDS,
    build_32_field_channel_rack_state,
    build_32_field_pattern,
)
from src.channel_rack import ChannelRackState
from src.pattern_core import Trigger
from src.workbench_feature_settings import (
    WorkbenchFeatureSettings,
    save_workbench_feature_settings,
)
from src.workbench_qml import QML_SOURCE
from src.workbench_session_store import active_track_pointer_path
from tests.audio_fixtures import write_sine_wav
from tests.test_active_track_persistence_1098 import _row

PY_SIDE6_AVAILABLE = importlib.util.find_spec("PySide6") is not None


# --- production-surface helpers (#678 pattern) --------------------------------


def _projection_module_or_fail():
    try:
        return importlib.import_module("src.workbench_arrangement_qml")
    except ModuleNotFoundError as exc:
        if exc.name is not None and exc.name.endswith("workbench_arrangement_qml"):
            pytest.fail(
                "MISSING_PRODUCTION_SURFACE: src.workbench_arrangement_qml "
                "(#1080 Slice A Arrangement QML projection seam not implemented)"
            )
        raise


def _project(session):
    module = _projection_module_or_fail()
    return module.project_arrangement_for_qml(session)


@pytest.fixture
def draft(tmp_path):
    session = ws.compose_workbench_session(state_dir=tmp_path / "state")
    source = tmp_path / "kick.wav"
    write_sine_wav(source, duration_sec=0.05, frequency_hz=60)
    session.live_kit.assign("Kick + Bass", "Kick", _row(source))
    session.channel_rack.restore_state(
        build_32_field_channel_rack_state(session.live_kit)
    )
    yield session, tmp_path / "track", source
    session.transport.close()


def _enable(session):
    settings = replace(WorkbenchFeatureSettings(), arrangement_mode_enabled=True)
    assert save_workbench_feature_settings(settings, state_dir=session._state_dir)


def _rack_with_active_fields(session, field_indexes):
    base = build_32_field_channel_rack_state(session.live_kit)
    rack = ChannelRackState(
        channels=base.channels,
        pattern=build_32_field_pattern(
            base.pattern.pattern_id,
            tuple(
                Trigger(channel_id="ch_kick", position=Fraction(int(i), 1))
                for i in field_indexes
            ),
        ),
        step_count=TOTAL_FIELDS,
    )
    session.channel_rack.restore_state(rack)
    return rack


def _flat_fields(projection):
    return [field for bar in projection.bars for field in bar.fields]


# --- gates 1-2: feature OFF / EDIT default -----------------------------------


def test_gate_1_feature_off_keeps_edit_without_route_or_authority(draft):
    s, root, _ = draft
    rack_before = s.channel_rack.state
    result = s.enter_arrangement_from_edit(package_root=root)
    assert result.outcome == "feature_disabled"
    assert not result.ok
    assert s.projection_mode == "EDIT"
    assert s.active_track_id is None
    assert s.channel_rack.state is rack_before
    assert not root.exists()
    projection = _project(s)
    assert projection.projection_mode == "EDIT"
    assert projection.any_active_step is False


def test_gate_2_edit_default_projection_is_complete_and_inert(tmp_path):
    s = ws.compose_workbench_session(state_dir=tmp_path / "state")
    try:
        projection = _project(s)
        assert projection.projection_mode == "EDIT"
        assert projection.active_track_id is None
        assert projection.pattern_id == ""
        assert projection.field_count == 32
        assert projection.bar_count == 8
        assert projection.fields_per_bar == 4
        assert len(projection.bars) == 8
        fields = _flat_fields(projection)
        assert [f.index for f in fields] == list(range(32))
        assert all(not f.active for f in fields)
        assert projection.any_active_step is False
        # Fail-closed mode vocabulary: an unknown projection mode is
        # rejected, never silently reinterpreted by the projection seam.
        bogus = SimpleNamespace(
            projection_mode="LIVE", channel_rack=None, active_track_id=None
        )
        with pytest.raises(ValueError):
            _project(bogus)
    finally:
        s.transport.close()


# --- gates 4-8: frozen 32-field projection geometry ---------------------------


def test_gates_4_5_exactly_32_fields_in_8_bars_of_four(draft):
    s, _, _ = draft
    projection = _project(s)
    assert projection.pattern_id == s.channel_rack.state.pattern.pattern_id
    for k, bar in enumerate(projection.bars):
        assert bar.index == k
        assert [f.index for f in bar.fields] == [
            4 * k,
            4 * k + 1,
            4 * k + 2,
            4 * k + 3,
        ]
        for i, field in enumerate(bar.fields):
            assert field.bar_index == k
            assert field.index_in_bar == i
    assert len(_flat_fields(projection)) == 32
    assert projection.field_count == 32
    assert projection.bar_count == 8
    assert projection.fields_per_bar == 4


def test_gate_6_upper_projection_quiet_before_first_active_step(draft):
    s, _, _ = draft
    projection = _project(s)
    assert all(not f.active for f in _flat_fields(projection))
    assert projection.any_active_step is False


def test_gates_7_8_first_active_step_activates_projection_without_copy(draft):
    s, _, _ = draft
    rack = _rack_with_active_fields(s, (5, 31))
    projection = _project(s)
    assert [f.index for f in _flat_fields(projection) if f.active] == [5, 31]
    assert projection.any_active_step is True
    # Gate 8: identity projection only — no copied Pattern truth.
    assert not hasattr(projection, "pattern")
    assert not hasattr(projection, "triggers")
    assert s.channel_rack.state.pattern is rack.pattern
    assert projection.pattern_id == rack.pattern.pattern_id


# --- gates 3, 9, 10, 11 (seam): transition/return ownership --------------------


def test_gates_3_9_owner_transition_and_return_preserve_state(draft):
    s, root, _ = draft
    _enable(s)
    owners = (s.live_kit, s.channel_rack, s.transport, s.audition)
    pattern = s.channel_rack.state.pattern
    assert s.enter_arrangement_from_edit(package_root=root).ok
    projection = _project(s)
    assert projection.projection_mode == "ARRANGEMENT"
    assert projection.active_track_id == s.active_track_id
    assert projection.pattern_id == pattern.pattern_id
    # Entry's media rebase rebuilds the rack state object (#1078 frozen
    # contract asserts pattern equality, not object identity).
    assert s.channel_rack.state.pattern == pattern
    pointer = active_track_pointer_path(state_dir=s._state_dir)
    pointer_before = pointer.read_bytes()
    manifest_before = (root / tp.TRACK_PACKAGE_FILENAME).read_bytes()
    s.return_to_edit()
    returned = _project(s)
    assert returned.projection_mode == "EDIT"
    assert returned.active_track_id == s.active_track_id
    assert s.arrangement_state is not None
    assert s.channel_rack.state.pattern == pattern
    assert (s.live_kit, s.channel_rack, s.transport, s.audition) == owners
    # Gate 11 (seam part): a pure projection return serializes nothing.
    assert (root / tp.TRACK_PACKAGE_FILENAME).read_bytes() == manifest_before
    assert pointer.read_bytes() == pointer_before


def test_gate_10_entry_keeps_playback_parked_and_audition_quiet(draft):
    s, root, _ = draft
    _enable(s)
    assert not s.transport.playing
    assert not s.channel_rack.is_playing
    assert not s.audition.playback_snapshot().playing
    assert s.enter_arrangement_from_edit(package_root=root).ok
    assert _project(s).projection_mode == "ARRANGEMENT"
    assert not s.transport.playing
    assert not s.channel_rack.is_playing
    assert not s.audition.playback_snapshot().playing


# --- QML string contracts (no Qt required) ------------------------------------


def _arrangement_shell_region() -> str:
    """Gated Loader through the last stage chrome marker."""
    start = QML_SOURCE.index('objectName: "arrangementStageLoader"')
    anchor = QML_SOURCE.index('objectName: "arrangementTrackIdentity"', start)
    return QML_SOURCE[
        start : anchor + len('objectName: "arrangementTrackIdentity"')
    ]


def _program_nav_browser_block() -> str:
    return QML_SOURCE.split('objectName: "programNavBrowser"', 1)[1].split(
        'objectName: "programNavStepSequencer"', 1
    )[0]


def _program_nav_arrangement_block() -> str:
    return QML_SOURCE.split('objectName: "programNavArrangement"', 1)[1].split(
        'objectName: "headerTransportZone"', 1
    )[0]


def _program_nav_step_sequencer_block() -> str:
    return QML_SOURCE.split('objectName: "programNavStepSequencer"', 1)[1].split(
        'objectName: "programNavArrangement"', 1
    )[0]


def test_gates_1_3_qml_scene_exists_only_behind_gated_loader():
    region = _arrangement_shell_region()
    assert 'active: window.arrangement.projectionMode === "ARRANGEMENT"' in region
    assert QML_SOURCE.count('objectName: "arrangementStage"') == 1
    assert 'objectName: "arrangementStage"' in region
    # QML never owns or writes the projection mode or the feature gate.
    assert re.search(r"projectionMode\s*=[^=]", QML_SOURCE) is None
    assert re.search(r"arrangementModeEnabled\s*=[^=]", QML_SOURCE) is None
    assert "setArrangementModeEnabled" not in QML_SOURCE
    assert QML_SOURCE.count("property var arrangement: arrangementModel") == 1


def test_gates_1_3_qml_route_is_gated_owner_command():
    nav = _program_nav_arrangement_block()
    assert "enabled: window.arrangement.arrangementModeEnabled" in nav
    assert "onClicked: window.arrangement.enterArrangement()" in nav
    assert (
        'readonly property bool navActive: window.arrangement.projectionMode '
        '=== "ARRANGEMENT"' in nav
    )
    # Gate 9 (string part): the return routes through the Browser nav (the
    # Edit destination) and the same #1078 state owner — the chrome
    # vocabulary canon keeps the literal mode word out of QML_SOURCE.
    browser_nav = _program_nav_browser_block()
    assert "window.arrangement.returnToBrowser()" in browser_nav
    assert 'window.arrangement.projectionMode === "ARRANGEMENT"' in browser_nav


def test_gates_4_7_8_10_qml_stage_projects_read_only_32_field_pattern():
    region = _arrangement_shell_region()
    assert 'objectName: "arrangementUpperStage"' in region
    assert "window.arrangement.anyActiveStep" in region
    assert 'objectName: "arrangementSequencer"' in region
    assert "model: window.arrangement.bars" in region
    assert 'objectName: "arrangementBar"' in region
    assert 'objectName: "arrangementField"' in region
    # Read-only: no mutation, audition, or persistence seams in the stage.
    for forbidden in (
        "toggleStep",
        "addUserChannel",
        "assignSelectedSample",
        "previewRow",
        "stopPreview",
        "previewHarmonyRow",
        "sessionPersistence",
        "saveWorkspacePreset",
    ):
        assert forbidden not in region
    # The stage is a fully non-interactive read-only projection; the return
    # route lives in the Browser nav, not in stage-owned command controls.
    assert region.count("onClicked") == 0
    # Input integrity: the read-only stage blocks pointer events from
    # falling through into the covered Edit workspace beneath it (no
    # invisible mutation or audition through the overlay).
    assert "MouseArea {" in region
    assert (
        "acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton"
        in region
    )
    # Focus ownership: claim focus once on activation, return deterministic
    # Browser focus on every deactivation path.
    assert "onLoaded: item.forceActiveFocus()" in region
    assert "browser.forceActiveFocus()" in region


def test_gate_11_qml_step_sequencer_stays_no_top_level_mode():
    seq = _program_nav_step_sequencer_block()
    assert "enabled: false" in seq
    assert "onClicked" not in seq
    assert QML_SOURCE.count('text: "Step Sequencer"') == 1


# --- runtime gates (PySide6) ----------------------------------------------------


def _build_production_window():
    from src.workbench_qml_spike import (
        _qml_engine,
        _settle_qml_frame,
        build_qml_view_model_from_fixture,
    )
    from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1

    fixture = build_screen1_visual_fixture_v1()
    view_model = build_qml_view_model_from_fixture(fixture, "screen1-default-3panel")
    view_model.set_library_revealed(True)
    view_model.set_workspace_materialization(
        has_active_source=True,
        calm_canvas_visible=False,
        browser_materialized=True,
        live_kit_materialized=True,
    )
    app, engine, window = _qml_engine(view_model)
    window.show()
    _settle_qml_frame(app)
    return app, engine, window, _settle_qml_frame


def _visual_items_named(root, name):
    """Collect items by objectName via the visual tree (repo pattern).

    Repeater delegates are not reachable through the QObject ``findChildren``
    chain; established Workbench tests therefore walk ``childItems()``.
    """
    found = []
    to_visit = [root]
    while to_visit:
        current = to_visit.pop()
        if current.objectName() == name:
            found.append(current)
        to_visit.extend(current.childItems())
    return found


def _click_item(window, item, settle, app) -> None:
    from PySide6.QtCore import QPointF

    center = item.mapToItem(
        window.contentItem(), QPointF(item.width() / 2, item.height() / 2)
    )
    _click_point(window, center, settle, app)


def _click_point(window, point, settle, app) -> None:
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QMouseEvent

    for action in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        event = QMouseEvent(
            action,
            point,
            window.mapToGlobal(point.toPoint()),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        app.sendEvent(window, event)
        settle(app)


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_gate_1_runtime_feature_off_edit_functional_without_scene(
    tmp_path, monkeypatch
):
    from PySide6.QtQuick import QQuickItem

    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path / "state"))
    app, engine, window, settle = _build_production_window()
    session = engine._screen1_session
    try:
        bridge = engine.rootContext().contextProperty("arrangementModel")
        assert bridge is not None
        assert bridge.projectionMode == "EDIT"
        assert bridge.arrangementModeEnabled is False
        assert window.findChild(QQuickItem, "arrangementStage") is None
        nav = window.findChild(QQuickItem, "programNavArrangement")
        assert nav is not None
        assert nav.property("enabled") is False
        # Edit stays fully functional with the route off.
        assert window.property("activeScreen") == "screen1"
        browser = window.findChild(QQuickItem, "browserList")
        assert browser is not None and browser.isVisible()
        # Gate 11 (runtime part): Step Sequencer stays a non-mode.
        seq = window.findChild(QQuickItem, "programNavStepSequencer")
        assert seq is not None and seq.property("enabled") is False
    finally:
        window.close()
        app.processEvents()
        if session is not None:
            session.transport.close()


@pytest.mark.skipif(not PY_SIDE6_AVAILABLE, reason="PySide6 ist nicht installiert")
def test_gates_3_9_10_runtime_owner_route_single_surface_and_return(
    tmp_path, monkeypatch
):
    from PySide6.QtQuick import QQuickItem

    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path / "state"))
    app, engine, window, settle = _build_production_window()
    session = engine._screen1_session
    try:
        bridge = engine.rootContext().contextProperty("arrangementModel")
        assert bridge is not None
        source = tmp_path / "kick.wav"
        write_sine_wav(source, duration_sec=0.05, frequency_hz=60)
        session.live_kit.assign("Kick + Bass", "Kick", _row(source))
        session.channel_rack.restore_state(
            build_32_field_channel_rack_state(session.live_kit)
        )
        _enable(session)
        engine._screen1_interaction_adapter.load_feature_settings()
        bridge.refresh()
        assert bridge.arrangementModeEnabled is True
        assert bridge.projectionMode == "EDIT"
        assert window.findChild(QQuickItem, "arrangementStage") is None

        # First entry through the Python #1078 seam (Slice A QML owns no
        # package-destination chooser); return, then re-enter via the
        # product route.
        assert session.enter_arrangement_from_edit(
            package_root=tmp_path / "track"
        ).ok
        track_id = session.active_track_id
        session.return_to_edit()
        bridge.refresh()
        owners = (
            session.live_kit,
            session.channel_rack,
            session.transport,
            session.audition,
        )

        nav = window.findChild(QQuickItem, "programNavArrangement")
        assert nav.property("enabled") is True
        _click_item(window, nav, settle, app)
        settle(app)
        assert bridge.projectionMode == "ARRANGEMENT"
        stage = window.findChild(QQuickItem, "arrangementStage")
        assert stage is not None and stage.isVisible()
        assert len(_visual_items_named(stage, "arrangementBar")) == 8
        assert len(_visual_items_named(stage, "arrangementField")) == 32
        assert bridge.activeTrackId == track_id
        assert bridge.anyActiveStep is False
        # Gate 10 (runtime part): entering keeps playback parked.
        assert not session.channel_rack.is_playing
        assert not session.transport.playing
        assert (
            session.live_kit,
            session.channel_rack,
            session.transport,
            session.audition,
        ) == owners
        # Gate 10 (runtime part): pointer input cannot fall through the
        # read-only stage into the covered Edit workspace — clicking a
        # covered Browser row must not change Edit selection state.
        from PySide6.QtCore import QPointF

        vm = engine._screen1_interaction_adapter.view_model
        selected_before = vm.selected_browser_index
        browser = window.findChild(QQuickItem, "browserList")
        assert browser is not None
        row_height = float(window.property("densityRowHeight"))
        row_point = browser.mapToItem(
            window.contentItem(), QPointF(browser.width() / 2, row_height / 2)
        )
        _click_point(window, row_point, settle, app)
        settle(app)
        assert vm.selected_browser_index == selected_before
        assert engine._screen1_interaction_adapter.preview_active is False

        # Return through the Browser nav (the Edit destination) and the
        # same #1078 state owner.
        browser_nav = window.findChild(QQuickItem, "programNavBrowser")
        assert browser_nav is not None
        _click_item(window, browser_nav, settle, app)
        settle(app)
        assert bridge.projectionMode == "EDIT"
        assert window.findChild(QQuickItem, "arrangementStage") is None
        browser = window.findChild(QQuickItem, "browserList")
        assert browser is not None and browser.isVisible()
        assert browser.hasActiveFocus()
        assert session.projection_mode == "EDIT"
        assert session.active_track_id == track_id
        assert session.arrangement_state is not None
        seq = window.findChild(QQuickItem, "programNavStepSequencer")
        assert seq.property("enabled") is False
    finally:
        window.close()
        app.processEvents()
        if session is not None:
            session.transport.close()
