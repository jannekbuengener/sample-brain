"""#1080 C2c1 review regressions (P1/P2 findings on PR #1161).

Frozen regression contract for the four C2c1 review findings:

1. P1 - workbench_qml.py:7616 uses ``Fraction`` without importing it from
   ``fractions``; every horizontal pan would raise ``NameError``.
2. P1 - the Ctrl+wheel zoom direction in the arrangement timeline QML is
   inverted: wheel up (positive ``angleDelta.y``) must zoom in, wheel down
   (negative) must zoom out.
3. P2 - ``SessionTransport.set_tempo`` replaces/mutates the TempoMap, but the
   arrangement viewport is initialized once and never rebased, so after a
   master tempo change the timeline projects a stale 3-minute / 10-minute
   window.
4. P2 - timeline marker geometry is hardcoded in QML (20 QN block length, 4
   px per QN); canonical block length is 64 QN from domain authority and the
   pixel scale must come from the renderer-facing projection instead.
"""

import copy
import re
from fractions import Fraction
from pathlib import Path

import pytest

from src import workbench_arrangement_qml as seam
from src.arrangement_32_field_time import ARRANGEMENT_BLOCK_LENGTH_QUARTER_NOTES
from src.session_grid import TempoMap
from src.workbench_qml import QML_SOURCE  # noqa: E402
from tests.test_arrangement_domain_1087 import tempo
from tests.test_workbench_arrangement_qml_1080_c1 import session as c1_session  # noqa: F401
from tests.test_workbench_arrangement_qml_1080_c2c1 import session as c2c1_session  # noqa: F401


CANONICAL_BLOCK_LENGTH_QN = int(ARRANGEMENT_BLOCK_LENGTH_QUARTER_NOTES)


@pytest.fixture
def session(c2c1_session):
    return copy.deepcopy(c2c1_session)


@pytest.fixture
def tempo_map():
    return tempo()


# --- helpers ------------------------------------------------------------------ #

def _wheel_block() -> str:
    """QML block of the arrangement Ctrl+wheel / horizontal-wheel handler."""
    start = QML_SOURCE.index("// C2c1: Ctrl + Mouse Wheel = zoom")
    end = QML_SOURCE.index("// Direction B (#1079)", start)
    return QML_SOURCE[start:end]


def _wheel_zoom_branches() -> tuple[str, str]:
    """(call for wheel *down* ``y < 0``, call for wheel *up* ``else``)."""
    block = _wheel_block()
    cond_pos = block.index("wheel.angleDelta.y")
    else_pos = block.index("\nelse", cond_pos)
    down_call = re.search(r"window\.arrangement\.(zoomIn|zoomOut)", block[cond_pos:else_pos])
    tail = block[else_pos:]
    up_call = re.search(r"window\.arrangement\.(zoomIn|zoomOut)", tail)
    assert down_call is not None, "no zoom call in the y < 0 branch"
    assert up_call is not None, "no zoom call after else in the wheel handler"
    return down_call.group(1), up_call.group(1)


def _marker_geometry_block() -> str:
    """QML block of the timeline viewport marker geometry."""
    start = QML_SOURCE.index('objectName: "timelineViewport"')
    end = QML_SOURCE.index("Direction B", start)
    return QML_SOURCE[start:end]


def _marker_x_expression() -> str:
    for line in _marker_geometry_block().splitlines():
        if "x:" in line and "viewportStartQn" in line:
            return line
    return ""


def _marker_width_expression() -> str:
    for line in _marker_geometry_block().splitlines():
        if "width:" in line and "blockIndex" not in line:
            return line
    return ""


def _python_source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "workbench_qml.py").read_text("utf-8")


def _refresh_body() -> str:
    source = _python_source()
    start = source.index("def _refresh")
    end = source.index("def ", start + 10)
    return source[start:end]


def _seconds(qn: Fraction, tempo_map: TempoMap) -> float:
    return tempo_map.quarter_note_to_frame(qn) / tempo_map.sample_rate


# --- Finding 1: Fraction import (P1, workbench_qml.py panHorizontal) ---------- #

def test_workbench_qml_imports_fraction_from_fractions():
    source = _python_source()
    assert "from fractions import Fraction" in source


def test_workbench_qml_module_exposes_fraction():
    import src.workbench_qml as workbench_qml

    assert workbench_qml.Fraction is Fraction


def test_pan_horizontal_slot_converts_delta_to_fraction():
    source = _python_source()
    refresh_boundaries = re.finditer(r"def\s+z(oomIn|oomOut|panHorizontal)", source)
    names = [m.group(0) for m in refresh_boundaries]
    assert names, "zoom/pan slots missing in workbench_qml.py"
    pan_slot_start = source.index("def panHorizontal")
    pan_slot = source[pan_slot_start:pan_slot_start + 400]
    assert "Fraction(" in pan_slot


# --- Finding 2: wheel zoom direction (P1, QML) -------------------------------- #

def test_ctrl_wheel_down_zooms_out_in_qml():
    """Principle: wheel down (negative angleDelta.y) must zoom OUT."""
    down_call, _ = _wheel_zoom_branches()
    assert down_call == "zoomOut"


def test_ctrl_wheel_up_zooms_in_in_qml():
    """Principle: wheel up (positive angleDelta.y) must zoom IN."""
    _, up_call = _wheel_zoom_branches()
    assert up_call == "zoomIn"


def test_wheel_handler_still_routes_horizontal_pan_without_ctrl():
    """Regression: non-Ctrl horizontal wheel keeps calling panHorizontal."""
    block = _wheel_block()
    assert "panHorizontal(-wheel.angleDelta.x)" in block


# --- Finding 3: tempo change rebase (P2, viewport seam + bridge) -------------- #

def rebase_viewport_for_tempo_change(
    viewport,
    previous_tempo_map: TempoMap,
    current_tempo_map: TempoMap,
):
    """Seam contract: rebase a viewport after a master tempo change.

    Presentation continuity: the visible *wall-clock* window is preserved
    (same seconds range), the musical start anchor stays where it was, and
    zoom level is untouched. Horizon/visibility clamp to the current tempo.
    """
    return seam.rebase_viewport_for_tempo_change(
        viewport, previous_tempo_map, current_tempo_map
    )


def test_rebase_preserves_wall_clock_window(session, tempo_map):
    vp = seam.viewport_for_initial_view(tempo_map)
    old_seconds_visible = _seconds(vp.visible_duration_qn, tempo_map)

    slow = tempo(60)
    rebased = rebase_viewport_for_tempo_change(vp, tempo_map, slow)

    assert _seconds(rebased.visible_duration_qn, slow) == pytest.approx(
        old_seconds_visible, rel=0.05
    )


def test_rebase_keeps_musical_start_position(session, tempo_map):
    vp = seam.viewport_for_initial_view(tempo_map)
    panned = seam.pan(vp, Fraction(512))
    assert panned.start_quarter_note == Fraction(512)

    rebased = rebase_viewport_for_tempo_change(panned, tempo_map, tempo(60))

    assert rebased.start_quarter_note == Fraction(512)


def test_rebase_clamps_start_into_new_horizon(session, tempo_map):
    vp = seam.viewport_for_initial_view(tempo_map)
    panned = seam.pan(vp, Fraction(2000))
    rebased = rebase_viewport_for_tempo_change(panned, tempo_map, tempo(60))

    assert rebased.start_quarter_note >= Fraction(0)
    assert rebased.start_quarter_note + rebased.visible_duration_qn <= rebased.logical_horizon_qn


def test_rebase_zoom_level_unchanged(session, tempo_map):
    vp = seam.viewport_for_initial_view(tempo_map)
    rebased = rebase_viewport_for_tempo_change(vp, tempo_map, tempo(60))
    assert rebased.zoom_level == vp.zoom_level


def test_rebase_result_still_pan_and_zoom_valid(session, tempo_map):
    vp = seam.viewport_for_initial_view(tempo_map)
    slow = tempo(60)
    rebased = rebase_viewport_for_tempo_change(vp, tempo_map, slow)
    panned = seam.pan(rebased, Fraction(100))
    zoomed = seam.zoom_out(rebased, Fraction(100), slow)
    assert panned.start_quarter_note >= Fraction(0)
    assert panned.start_quarter_note + panned.visible_duration_qn <= panned.logical_horizon_qn
    assert zoomed.visible_duration_qn <= zoomed.logical_horizon_qn


def test_bridge_refresh_rebases_on_tempo_map_change():
    source = _python_source()
    refresh = _refresh_body()
    assert "tempo_map is not self._tempo_map" in refresh
    assert "rebase_viewport_for_tempo_change" in source


# --- Finding 4: marker geometry from authority (P2, QML + bridge) ------------- #

def test_arrangement_block_length_canonical_is_64_qn():
    assert CANONICAL_BLOCK_LENGTH_QN == 64


def test_marker_x_expression_has_no_hardcoded_block_length():
    geom = _marker_geometry_block()
    assert "blockIndex * 20" not in geom


def test_marker_x_expression_references_authority_geometry():
    x_expr = _marker_x_expression()
    width_expr = _marker_width_expression()
    assert x_expr, "marker x expression missing from timeline viewport QML"
    assert width_expr, "marker width expression missing from timeline viewport QML"
    # Geometry must come from Python-owned bridge properties, not literals.
    assert "arrangementBlockLengthQn" in x_expr
    assert "viewportStartQn" in x_expr
    # px scale must be derived, not the hardcoded "* 2 * 2" = 4 px per QN.
    assert "2 * 2" not in x_expr and "* 20" not in x_expr
    assert "arrangementBlockLengthQn" in width_expr
    # Pixel scale belongs to the bridge-visible projection.
    assert "timelineViewport.width" in x_expr
    assert "viewportVisibleQn" in x_expr


def test_bridge_exposes_viewport_visible_qn_property():
    source = _python_source()
    assert "arrangementBlockLengthQn" in source
    assert "viewportVisibleQn" in source


def test_bridge_block_length_comes_from_domain_authority():
    source = _python_source()
    assert "ARRANGEMENT_BLOCK_LENGTH_QUARTER_NOTES" in source


def test_tempo_map_replacement_updates_viewport_projection(session, tempo_map):
    """End-to-end seam contract: after a tempo replacement, projection of the
    interleaved session reparts the same wall-clock slice from the new map."""
    vp = seam.viewport_for_initial_view(tempo_map)
    window_before = seam.project_visible_blocks(session, vp)
    assert window_before.blocks

    session.transport.tempo_map = tempo(60)
    rebased = rebase_viewport_for_tempo_change(vp, tempo_map, session.transport.tempo_map)
    window_after = seam.project_visible_blocks(session, rebased)
    assert window_after.blocks

    # The projected wall-clock slice stays approximately the same window.
    before_seconds = _seconds(window_before.blocks[0].start_quarter_note, tempo_map)
    after_seconds = _seconds(
        window_after.blocks[0].start_quarter_note, session.transport.tempo_map
    )
    assert after_seconds == pytest.approx(before_seconds, rel=0.05)
