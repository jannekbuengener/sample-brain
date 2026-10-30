"""#1281: Edge immersion must not fog the initial Browser viewport."""

from __future__ import annotations

from src import workbench_qml


def test_edge_immersion_is_scroll_state_aware_not_always_on():
    source = workbench_qml.QML_SOURCE
    assert 'objectName: "browserEdgeImmersionTop"' in source
    assert 'objectName: "browserEdgeImmersionBottom"' in source
    # Initial/default first view must stay fully readable.
    assert "scrolledAwayFromTop" in source
    assert "browser.atYBeginning" in source
    # Bottom fog must not engage on the first viewport merely because content overflows.
    assert "moreContentBelow" in source
    assert "contentOverflows && scrolledAwayFromTop && moreContentBelow" in source
    # Top fog only after real scroll away from the top.
    assert "contentOverflows && scrolledAwayFromTop" in source
    # Keep owner-approved compact density — no rowHeight expansion workaround.
    assert "densityRowHeight" in source


def test_edge_immersion_still_exists_as_concept():
    source = workbench_qml.QML_SOURCE
    assert "browserEdgeImmersionTop" in source
    assert "browserEdgeImmersionBottom" in source
    assert "surfaceRoot" in source
