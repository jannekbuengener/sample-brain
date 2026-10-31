"""C2d review regression: track rows must expose all three mask layers to QML."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.workbench_qml import _qml_arrangement_bridge
from tests.test_workbench_arrangement_qml_1080_c1 import session as c1_session  # noqa: F401


def test_track_block_dict_exposes_global_group_and_track_mask_truth(c1_session):
    pytest.importorskip("PySide6")
    c1_session.projection_mode = "ARRANGEMENT"
    bridge = _qml_arrangement_bridge(
        c1_session, SimpleNamespace(arrangement_mode_enabled=True)
    )
    bridge.refresh()
    assert bridge.toggleArrangementGroupExpanded("pg_baseline") == "toggled"
    bridge.refresh()

    baseline = next(r for r in bridge.groupRows if r["groupId"] == "pg_baseline")
    track = baseline["trackRows"][0]
    block = next(b for b in track["blocks"] if b["blockIndex"] == 0)

    # QML renders distinct GLOBAL / GROUP / TRACK status text. The bridge must
    # expose each authority layer explicitly rather than relying on undefined
    # QVariant keys that collapse every row to "GLOBAL OFF".
    assert block["blockEnabled"] is True
    assert block["groupEnabled"] is True
    assert block["trackEnabled"] is True

    assert bridge.toggleArrangementTrackBlock(track["channelId"], 0) == "mutated"
    bridge.refresh()
    baseline = next(r for r in bridge.groupRows if r["groupId"] == "pg_baseline")
    track = next(r for r in baseline["trackRows"] if r["channelId"] == track["channelId"])
    block = next(b for b in track["blocks"] if b["blockIndex"] == 0)
    assert block["blockEnabled"] is True
    assert block["groupEnabled"] is True
    assert block["trackEnabled"] is False
