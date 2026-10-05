"""R&D Slice 10 (#680/#925): headless gesture audio → Rack plan/apply action.

Orchestrates existing Stages 1–7 and mutates only via
``ChannelRackController.apply_gesture_integration_plan`` (#921).

See ``docs/GESTURE_RACK_HEADLESS_ACTION_RND_SLICE10.md``.
"""

import dataclasses
import fractions
import pathlib

from .channel_rack import ChannelRackState
from .gesture_analysis import analyze_gesture_audio
from .gesture_catalog_adapter import load_gesture_library_candidates
from .gesture_library_ranking import rank_gesture_library_candidates
from .gesture_pattern_binding import (
    GesturePatternBindingPlan,
    plan_gesture_pattern_binding,
)
from .gesture_pattern_core_composition import compose_gesture_pattern_core
from .gesture_rack_integration import (
    GestureRackIntegrationPlan,
    plan_gesture_rack_integration,
)
from .gesture_timing_projection import project_gesture_timing
from .workbench_channel_rack import (
    ChannelRackController,
    StaleGestureRackIntegrationPlanError,
)


@dataclasses.dataclass(frozen=True)
class GestureRackHeadlessActionResult:
    """Immutable outcome of one headless prepare+apply attempt."""

    status: str
    unresolved_cluster_ids: tuple[int, ...]
    applied_state: ChannelRackState | None
    binding_plan: GesturePatternBindingPlan | None
    rack_plan: GestureRackIntegrationPlan | None
    analysis_status: str | None


def _result(
    *,
    status: str,
    unresolved_cluster_ids: tuple[int, ...] = (),
    applied_state: ChannelRackState | None = None,
    binding_plan: GesturePatternBindingPlan | None = None,
    rack_plan: GestureRackIntegrationPlan | None = None,
    analysis_status: str | None = None,
) -> GestureRackHeadlessActionResult:
    return GestureRackHeadlessActionResult(
        status=status,
        unresolved_cluster_ids=unresolved_cluster_ids,
        applied_state=applied_state,
        binding_plan=binding_plan,
        rack_plan=rack_plan,
        analysis_status=analysis_status,
    )


def prepare_and_apply_gesture_rack(
    audio_path: pathlib.Path | str,
    channel_rack: ChannelRackController,
    *,
    catalog_path: pathlib.Path | str,
    reference_bpm: int | float | str | fractions.Fraction,
    pattern_length_quarters: fractions.Fraction,
    selections: dict[int, str],
    pattern_id: str,
    allow_pattern_replacement: bool,
    feature_enabled: bool,
) -> GestureRackHeadlessActionResult:
    """Prepare gesture→Rack plan via existing seams; apply once when gated.

    Stages 1–7 are pure/plan/read-only. The sole musical mutation is
    ``channel_rack.apply_gesture_integration_plan``. Never calls
    ``ensure_state``, session store, or Feature Settings I/O.

    ``stale_base_state`` is reported only for the typed pre-mutation rejection
    ``StaleGestureRackIntegrationPlanError``. No generic ``ValueError`` is
    caught around apply, so a post-mutation observer failure propagates rather
    than being reported as a zero-mutation status.
    """
    analysis = analyze_gesture_audio(audio_path)
    if analysis.status != "ok":
        return _result(
            status="analysis_not_ok",
            analysis_status=analysis.status,
        )

    candidates = load_gesture_library_candidates(catalog_path)
    rankings = rank_gesture_library_candidates(analysis, candidates)
    timing = project_gesture_timing(analysis, reference_bpm)

    base_state = channel_rack.state
    if base_state is None:
        return _result(
            status="state_none",
            analysis_status=analysis.status,
        )

    binding_plan = plan_gesture_pattern_binding(
        timing,
        rankings,
        candidates,
        selections,
        [channel.channel_id for channel in base_state.channels],
        pattern_length_quarters=pattern_length_quarters,
    )
    if binding_plan.ready_for_pattern is not True:
        return _result(
            status="unresolved_selections",
            unresolved_cluster_ids=binding_plan.unresolved_cluster_ids,
            binding_plan=binding_plan,
            analysis_status=analysis.status,
        )

    composition = compose_gesture_pattern_core(
        binding_plan,
        pattern_id=pattern_id,
    )
    rack_plan = plan_gesture_rack_integration(
        base_state,
        composition,
        allow_pattern_replacement=allow_pattern_replacement,
    )
    if rack_plan.ready_for_apply is not True:
        return _result(
            status="not_ready_for_apply",
            binding_plan=binding_plan,
            rack_plan=rack_plan,
            analysis_status=analysis.status,
        )

    if feature_enabled is not True:
        return _result(
            status="feature_disabled",
            binding_plan=binding_plan,
            rack_plan=rack_plan,
            analysis_status=analysis.status,
        )

    try:
        applied = channel_rack.apply_gesture_integration_plan(
            rack_plan,
            feature_enabled=feature_enabled,
        )
    except StaleGestureRackIntegrationPlanError:
        # Typed, pre-mutation rejection only (#921 validates expected_base_state
        # before stop / state assignment / observer). Every other exception —
        # including observer failures raised after the Rack was already
        # replaced — propagates, so a mutation that happened is never reported
        # as a zero-mutation stale status.
        return _result(
            status="stale_base_state",
            binding_plan=binding_plan,
            rack_plan=rack_plan,
            analysis_status=analysis.status,
        )

    return _result(
        status="applied",
        applied_state=applied,
        binding_plan=binding_plan,
        rack_plan=rack_plan,
        analysis_status=analysis.status,
    )
