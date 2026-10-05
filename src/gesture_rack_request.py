"""R&D Slice 11 (#680/#931): session-bound gesture Rack request seam.

Binds a live Workbench session context to the delivered Slice-10 headless
action and to the existing Stage 1 / Stage 3 evidence seams. Distance is not
confidence: this module adds no match-quality claim.

The seam performs no Rack mutation. It never materializes Rack state, never
reads or writes the Feature Settings file, and never resolves the catalog
path. See ``docs/GESTURE_RACK_REQUEST_RND_SLICE11.md``.
"""

import collections.abc
import dataclasses
import pathlib
import typing

from .gesture_analysis import analyze_gesture_audio
from .gesture_catalog_adapter import rank_gesture_against_catalog
from .gesture_library_ranking import ClusterRanking
from .gesture_rack_headless_action import (
    GestureRackHeadlessActionResult,
    prepare_and_apply_gesture_rack,
)


class LiveGestureRackContext(typing.Protocol):
    """Narrow structural live context (WorkbenchSession satisfies it).

    Declared structurally so the seam never imports the session module.
    """

    @property
    def channel_rack(self) -> object:
        """Controller exposing public ``state`` and the Slice-10 apply seam."""

    @property
    def transport(self) -> object:
        """Tempo owner exposing the public ``get_current_tempo()`` seam."""


class WorkbenchFeatureSettingsLike(typing.Protocol):
    """Already-loaded settings provider; no settings file I/O in the seam."""

    @property
    def gesture_rack_apply_enabled(self) -> bool:
        """Injected #910 flag value; the caller owns the Settings file."""


@dataclasses.dataclass(frozen=True)
class GestureRackCandidateProposal:
    """Evidence-only Top-N proposal. No selection, no mutation, no session."""

    status: str = ""
    analysis_status: str | None = None
    cluster_rankings: tuple[ClusterRanking, ...] = ()


@dataclasses.dataclass(frozen=True)
class GestureRackRequestResult:
    """Thin Slice-11 envelope around the verbatim Slice-10 result."""

    status: str = ""
    action_result: GestureRackHeadlessActionResult | None = None


def propose_gesture_rack_candidates(
    audio_path: pathlib.Path | str,
    *,
    catalog_path: pathlib.Path | str,
    top_n: int = 5,
) -> GestureRackCandidateProposal:
    """Rank gesture clusters against an explicit catalog and return evidence.

    Fails closed with ``analysis_not_ok`` and no catalog read when Stage 1 is
    not ok. Otherwise delegates load-then-rank to the existing adapter seam,
    so ``top_n`` validation and all ranking math stay owned by #882/#886.
    """
    analysis = analyze_gesture_audio(audio_path)
    if analysis.status != "ok":
        return GestureRackCandidateProposal(
            status="analysis_not_ok",
            analysis_status=analysis.status,
            cluster_rankings=(),
        )

    cluster_rankings = rank_gesture_against_catalog(
        analysis,
        catalog_path,
        top_n=top_n,
    )
    return GestureRackCandidateProposal(
        status="ok",
        analysis_status=analysis.status,
        cluster_rankings=cluster_rankings,
    )


def submit_gesture_rack_request(
    audio_path: pathlib.Path | str,
    live_context: LiveGestureRackContext,
    *,
    catalog_path: pathlib.Path | str,
    selections: collections.abc.Mapping[int, str],
    pattern_id: str,
    allow_pattern_replacement: bool,
    feature_enabled: bool | WorkbenchFeatureSettingsLike,
) -> GestureRackRequestResult:
    """Bind a live session context to the Slice-10 headless action once.

    Derives only ``reference_bpm`` and ``pattern_length_quarters`` from the
    live context; every caller-authoritative input is forwarded unchanged.
    Fails closed with ``state_none`` before any delegation when public Rack
    state is absent, so Rack materialization is never implicit.
    """
    channel_rack = live_context.channel_rack
    state = channel_rack.state
    if state is None:
        return GestureRackRequestResult(status="state_none", action_result=None)

    reference_bpm = live_context.transport.get_current_tempo()
    pattern_length_quarters = state.pattern.length_quarter_notes
    resolved_feature_enabled = (
        feature_enabled
        if isinstance(feature_enabled, bool)
        else feature_enabled.gesture_rack_apply_enabled
    )

    action_result = prepare_and_apply_gesture_rack(
        audio_path,
        channel_rack,
        catalog_path=catalog_path,
        reference_bpm=reference_bpm,
        pattern_length_quarters=pattern_length_quarters,
        selections=selections,
        pattern_id=pattern_id,
        allow_pattern_replacement=allow_pattern_replacement,
        feature_enabled=resolved_feature_enabled,
    )
    return GestureRackRequestResult(status="submitted", action_result=action_result)