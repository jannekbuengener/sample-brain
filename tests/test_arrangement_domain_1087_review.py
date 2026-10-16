"""Review regressions for PR #1136 / Issue #1087."""

from fractions import Fraction

import pytest

from src import arrangement_32_field_time as a32
from src import arrangement_domain as ad
from src import track_package as tp
from src.channel_rack import ChannelRackState
from src.pattern_core import Channel, Trigger
from tests.test_arrangement_domain_1087 import rack, tempo
from tests.test_track_package import _draft_with_sources, _repo_root, _write_source


@pytest.mark.parametrize("arrangement_payload", [[], 7, "opaque", True])
def test_save_preserves_explicit_opaque_arrangement_payload(
    tmp_path, arrangement_payload
):
    library = tmp_path / "library"
    library.mkdir()
    source = _write_source(library)
    package_root = tmp_path / "packages" / "pkg"
    package_root.parent.mkdir()
    base = _draft_with_sources(source, track_id="trk_opaque_arrangement")
    created = tp.create_track_package(
        tp.TrackPackageDraft(
            media_sources=base.media_sources,
            musical=base.musical,
            track_id=base.track_id,
            arrangement=arrangement_payload,
        ),
        package_root,
        repo_root=_repo_root(),
    )
    assert created.outcome == tp.OUTCOME_OPEN
    assert created.manifest is not None
    assert created.manifest.arrangement == arrangement_payload

    saved = tp.save_track_package_musical_state(
        package_root,
        created.manifest.musical,
        arrangement=created.manifest.arrangement,
    )

    assert saved.outcome == tp.OUTCOME_OPEN
    assert saved.manifest is not None
    assert saved.manifest.arrangement == arrangement_payload
    reopened = tp.open_track_package(package_root)
    assert reopened.manifest is not None
    assert reopened.manifest.arrangement == arrangement_payload


def test_set_track_rejects_unmapped_membership_without_mutation():
    base = rack()
    user = Channel("ch_user_review", None, None, "Drums/review.wav")
    user_pattern = a32.build_32_field_pattern(
        base.pattern.pattern_id,
        (*base.pattern.triggers, Trigger(user.channel_id, Fraction(8))),
    )
    state_rack = ChannelRackState(base.channels + (user,), user_pattern, 32)
    state = ad.ArrangementState.for_rack(state_rack)
    before = state.to_payload()

    with pytest.raises(ad.ArrangementError, match="migration_required"):
        state.set_track(user.channel_id, 0, False, state_rack, tempo())

    assert state.to_payload() == before
