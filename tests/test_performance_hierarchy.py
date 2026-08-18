from __future__ import annotations

import numpy as np
import pytest

from src.live_profile import LiveLayout, LiveLayoutConfig
from src.performance_hierarchy import (
    DEFAULT_DRUM_ELEMENTS,
    ElementCandidate,
    HierarchicalLiveLayout,
    REASON_EVIDENCE_UNSUPPORTED,
    REASON_MISSING_AUDIO,
    STATUS_NO_RESULT,
    STATUS_OK,
    build_drums_element_layer,
)


def _candidate(value: float, *, supported: bool = True, source_ref: str = "sep://drums/kick"):
    return ElementCandidate(
        audio=np.full(16, value, dtype=np.float32),
        source_kind="hierarchical_separator",
        source_ref=source_ref,
        evidence_supported=supported,
        technical_stems=("drums",),
        provenance=("stage1:drums", "stage2:drum-elements"),
    )


def _top_level() -> LiveLayout:
    return LiveLayout(config=LiveLayoutConfig(), source_track_ref="track:test")


def test_detail_layer_is_hidden_in_default_layout_and_revealed_explicitly():
    layer = build_drums_element_layer(
        {
            "kick": _candidate(0.1),
            "snare_clap": _candidate(0.2, source_ref="sep://drums/snare"),
        }
    )
    layout = HierarchicalLiveLayout(top_level=_top_level(), detail_layers={"drums": layer})

    compact = layout.as_dict()
    assert "elements" not in compact["detail_layers"][0]
    assert compact["detail_layers"][0] == {
        "parent_group": "drums",
        "hidden_by_default": True,
        "available_count": 2,
        "has_detail": True,
    }

    revealed = layout.reveal_group("drums")
    assert revealed is not None
    assert [e["element"] for e in revealed["elements"]] == list(DEFAULT_DRUM_ELEMENTS)
    assert [e["status"] for e in revealed["elements"][:2]] == [STATUS_OK, STATUS_OK]


def test_unsupported_or_missing_elements_fail_closed_as_no_result():
    layer = build_drums_element_layer(
        {
            "kick": _candidate(0.1, supported=False),
            "snare_clap": ElementCandidate(
                audio=None,
                source_kind="hierarchical_separator",
                source_ref="sep://drums/snare",
                evidence_supported=True,
            ),
        }
    )

    by_name = {e.element: e for e in layer.elements}
    assert by_name["kick"].status == STATUS_NO_RESULT
    assert by_name["kick"].reason_code == REASON_EVIDENCE_UNSUPPORTED
    assert by_name["snare_clap"].status == STATUS_NO_RESULT
    assert by_name["snare_clap"].reason_code == REASON_MISSING_AUDIO
    assert by_name["hi_hats"].status == STATUS_NO_RESULT
    assert by_name["hi_hats"].reason_code == REASON_MISSING_AUDIO


def test_parent_group_rebuild_uses_only_evidenced_enabled_children():
    layer = build_drums_element_layer(
        {
            "kick": _candidate(0.1),
            "snare_clap": _candidate(0.2, source_ref="sep://drums/snare"),
            "hi_hats": _candidate(0.3, supported=False, source_ref="sep://drums/hats"),
        }
    )
    layout = HierarchicalLiveLayout(top_level=_top_level(), detail_layers={"drums": layer})

    rebuilt = layout.rebuild_group_audio("drums")
    assert rebuilt is not None
    np.testing.assert_allclose(rebuilt, np.full(16, 0.3, dtype=np.float32))

    kick_only = layout.rebuild_group_audio("drums", enabled=["kick"])
    assert kick_only is not None
    np.testing.assert_allclose(kick_only, np.full(16, 0.1, dtype=np.float32))

    assert layout.rebuild_group_audio("drums", enabled=["hi_hats"]) is None


def test_rebuild_fails_closed_when_child_lengths_disagree():
    layer = build_drums_element_layer(
        {
            "kick": _candidate(0.1),
            "snare_clap": ElementCandidate(
                audio=np.full(8, 0.2, dtype=np.float32),
                source_kind="hierarchical_separator",
                source_ref="sep://drums/snare",
                evidence_supported=True,
            ),
        }
    )

    with pytest.raises(ValueError, match="lengths do not match"):
        layer.rebuild_parent_audio()


def test_no_detail_is_revealed_when_nothing_is_evidenced():
    layer = build_drums_element_layer({"kick": _candidate(0.1, supported=False)})
    layout = HierarchicalLiveLayout(top_level=_top_level(), detail_layers={"drums": layer})

    assert layer.available_elements == []
    assert layout.reveal_group("drums") is None
    assert layout.as_dict()["detail_layers"][0]["has_detail"] is False
