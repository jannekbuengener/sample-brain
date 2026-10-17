"""PR #1154 review regressions; original C1 test freeze stays unchanged."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src import arrangement_domain as ad
from src import workbench_arrangement_qml as seam
from src.pattern_core import Channel
from tests.test_arrangement_domain_1087 import rack, tempo


def session():
    r = rack()
    return SimpleNamespace(
        channel_rack=SimpleNamespace(state=r),
        arrangement_state=ad.ArrangementState.for_rack(r),
        transport=SimpleNamespace(tempo_map=tempo()),
        set_arrangement_state=Mock(),
    )


def test_unmapped_remains_unresolved_outside_current_horizon():
    s = session()
    s.channel_rack.state = replace(
        s.channel_rack.state,
        channels=(*s.channel_rack.state.channels,
                  Channel("ch_user_review", None, None, "Drums/kick.wav")),
    )
    p = seam.project_arrangement_block_window(s, 19, 1)
    assert p.membership_status == "migration_required"
    assert p.blocks[0].status == "out_of_current_horizon"
    t = next(t for t in p.track_blocks if t.channel_id == "ch_user_review")
    assert t.group_id == "unmapped" and t.effective == "unresolved"
    s.set_arrangement_state.assert_not_called()


def test_oversized_window_rejected_before_any_domain_read(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("oversized request reached domain")
    monkeypatch.setattr(ad.ArrangementState, "block_status", forbidden)
    with pytest.raises(ValueError, match="block_window_too_large"):
        seam.project_arrangement_block_window(session(), 0, 10**9)


def test_resource_window_limit_is_explicit_and_not_musical_horizon():
    limit = seam.MAX_ARRANGEMENT_BLOCK_WINDOW
    s = session()
    assert len(seam.project_arrangement_block_window(s, 0, limit).blocks) == limit
    with pytest.raises(ValueError, match="block_window_too_large"):
        seam.project_arrangement_block_window(s, 0, limit + 1)
    # Paging is allowed independently of horizon: no clamp or musical rewrite.
    p = seam.project_arrangement_block_window(s, 1000, 1)
    assert p.blocks[0].block_index == 1000
    assert p.blocks[0].status == "out_of_current_horizon"
    s.set_arrangement_state.assert_not_called()
