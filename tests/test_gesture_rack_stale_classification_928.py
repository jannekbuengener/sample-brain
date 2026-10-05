"""Review-repair regression: typed stale classification for the Action seam.

Resolves two findings raised on PR #928.

1. The Action used a substring predicate to recognise the controller's stale
   ``expected_base_state`` rejection. ``apply_gesture_integration_plan`` assigns
   the new Rack state *before* invoking the musical-state observer, so a
   post-mutation observer ``ValueError`` whose message happened to contain
   ``stale`` or ``expected_base_state`` was mis-reported as a zero-mutation
   ``stale_base_state`` with ``applied_state=None`` — an unsafe retry signal.
   The Action now catches only the dedicated, pre-mutation
   ``StaleGestureRackIntegrationPlanError``.

2. The contract document still declared the lifecycle as ``TEST_FREEZE`` with
   the Action module "absent by design". The status is asserted in
   ``test_s4_contract_document_lifecycle_is_current``.

These are additive review-repair regressions. The frozen #925 acceptance file
(``tests/test_gesture_rack_headless_action_925.py``) is left untouched; only its
existing helpers are reused here.
"""

from __future__ import annotations

import ast
import dataclasses
from fractions import Fraction
from pathlib import Path
from unittest import mock

import pytest

from src.channel_rack import ChannelRackState
from src.gesture_rack_integration import GestureRackIntegrationPlan
from src.workbench_channel_rack import (
    ChannelRackController,
    GestureRackApplyPostMutationError,
    StaleGestureRackIntegrationPlanError,
)

# Reused helpers (repo convention: cross-test helper imports are established
# practice, see tests/test_program_chrome_slim_polish_880.py). Aliased to keep
# the two helper families distinguishable.
from tests.test_gesture_rack_controller_apply_921 import (
    _base_state as _plan_base_state,
)
from tests.test_gesture_rack_controller_apply_921 import (
    _controller as _plan_controller,
)
from tests.test_gesture_rack_controller_apply_921 import (
    _pattern as _plan_pattern,
)
from tests.test_gesture_rack_controller_apply_921 import (
    _plan as _build_plan,
)
from tests.test_gesture_rack_headless_action_925 import (
    _base_state as _action_base_state,
)
from tests.test_gesture_rack_headless_action_925 import (
    _call_action as _action_call,
)
from tests.test_gesture_rack_headless_action_925 import (
    _catalog_with_oneshots,
)
from tests.test_gesture_rack_headless_action_925 import (
    _controller as _action_controller,
)
from tests.test_gesture_rack_headless_action_925 import (
    _ok_analysis,
    _patch_analysis,
    _write_placeholder_wav,
)

_ACTION_MODULE = Path("src/gesture_rack_headless_action.py")
_RACK_MODULE = Path("src/workbench_channel_rack.py")
_CONTRACT_DOC = Path("docs/GESTURE_RACK_HEADLESS_ACTION_RND_SLICE10.md")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mutated_variant(base: ChannelRackState) -> ChannelRackState:
    """A different, still-valid Rack state (the 'moved elsewhere' case)."""
    return ChannelRackState(
        channels=base.channels,
        pattern=_plan_pattern(
            "moved-elsewhere",
            length=base.pattern.length_quarter_notes,
        ),
        step_count=base.step_count,
    )


def _apply_raw(
    controller: ChannelRackController,
    plan: GestureRackIntegrationPlan,
    *,
    feature_enabled: bool,
) -> ChannelRackState:
    return controller.apply_gesture_integration_plan(
        plan, feature_enabled=feature_enabled
    )


# ---------------------------------------------------------------------------
# S1. The typed exception is a real, exported, ValueError-compatible type
# ---------------------------------------------------------------------------


def test_s1_typed_stale_error_is_an_exported_valueerror_subclass() -> None:
    import src.workbench_channel_rack as rack_mod

    assert issubclass(StaleGestureRackIntegrationPlanError, ValueError)
    assert StaleGestureRackIntegrationPlanError is not ValueError
    assert "StaleGestureRackIntegrationPlanError" in rack_mod.__all__
    assert rack_mod.StaleGestureRackIntegrationPlanError is (
        StaleGestureRackIntegrationPlanError
    )


def test_s1b_typed_stale_error_keeps_the_legacy_message() -> None:
    """Message text is preserved so #921 string assertions stay valid."""
    err = StaleGestureRackIntegrationPlanError("stale x: expected_base_state")
    assert "expected_base_state" in str(err)


# ---------------------------------------------------------------------------
# S2. The controller raises the typed error ONLY for expected_base_state drift
# ---------------------------------------------------------------------------


def test_s2_expected_base_state_mismatch_raises_typed_error() -> None:
    base = _plan_base_state()
    plan = _build_plan(base)
    assert plan.ready_for_apply is True

    controller = _plan_controller(state=_mutated_variant(base))
    with pytest.raises(StaleGestureRackIntegrationPlanError):
        _apply_raw(controller, plan, feature_enabled=True)


def test_s2b_matching_base_state_applies_normally() -> None:
    base = _plan_base_state()
    plan = _build_plan(base)
    controller = _plan_controller(state=base)

    applied = _apply_raw(controller, plan, feature_enabled=True)
    assert applied == ChannelRackState(
        channels=plan.target_channels,
        pattern=plan.target_pattern,
        step_count=plan.target_step_count,
    )


@pytest.mark.parametrize(
    ("case", "kwargs", "plan_mutator"),
    [
        ("feature_disabled", {"feature_enabled": False}, None),
        (
            "short_target_pattern",
            {"feature_enabled": True},
            lambda p: dataclasses.replace(
                p,
                target_pattern=_plan_pattern("short", length=Fraction(2, 1)),
            ),
        ),
    ],
)
def test_s2c_other_validation_failures_stay_plain_valueerror(
    case: str,
    kwargs: dict,
    plan_mutator,
) -> None:
    """Non-stale #921 rejections must NOT be reported as typed stale."""
    base = _plan_base_state()
    plan = _build_plan(base)
    if plan_mutator is not None:
        plan = plan_mutator(plan)
    controller = _plan_controller(state=base)

    with pytest.raises(ValueError) as excinfo:
        _apply_raw(controller, plan, **kwargs)

    assert not isinstance(excinfo.value, StaleGestureRackIntegrationPlanError), case
    assert "expected_base_state" not in str(excinfo.value), case


def test_s2d_not_ready_plan_stays_plain_valueerror() -> None:
    base = _plan_base_state()
    plan = dataclasses.replace(_build_plan(base), ready_for_apply=False)
    controller = _plan_controller(state=base)

    with pytest.raises(ValueError) as excinfo:
        _apply_raw(controller, plan, feature_enabled=True)

    assert not isinstance(excinfo.value, StaleGestureRackIntegrationPlanError)


# ---------------------------------------------------------------------------
# S3. Action: typed pre-mutation reject -> stale_base_state, zero side effects
# ---------------------------------------------------------------------------


def test_s3_action_maps_typed_stale_to_status_with_zero_side_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    _patch_analysis(monkeypatch, _ok_analysis(cluster_ids=(0,)))

    observers: list[str] = []
    base = _action_base_state()
    controller = _action_controller(
        state=base,
        on_musical_state_changed=lambda: observers.append("obs"),
    )
    before = controller.state

    with mock.patch.object(
        controller,
        "apply_gesture_integration_plan",
        side_effect=StaleGestureRackIntegrationPlanError(
            "stale GestureRackIntegrationPlan: "
            "controller state does not match expected_base_state"
        ),
    ):
        result = _action_call(
            audio_path=audio,
            channel_rack=controller,
            catalog_path=catalog,
            selections={0: "101"},
            feature_enabled=True,
        )

    assert result.status == "stale_base_state"
    assert result.applied_state is None
    assert observers == []
    assert controller.state == before


# ---------------------------------------------------------------------------
# S4. Action: a non-stale ValueError from apply must propagate
# ---------------------------------------------------------------------------


def test_s4_action_propagates_unrelated_valueerror_from_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pre-mutation, non-stale ValueError is not converted into a status."""
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    _patch_analysis(monkeypatch, _ok_analysis(cluster_ids=(0,)))

    base = _action_base_state()
    controller = _action_controller(state=base)

    with mock.patch.object(
        controller,
        "apply_gesture_integration_plan",
        side_effect=ValueError("unrelated apply failure"),
    ):
        with pytest.raises(ValueError, match="unrelated apply failure"):
            _action_call(
                audio_path=audio,
                channel_rack=controller,
                catalog_path=catalog,
                selections={0: "101"},
                feature_enabled=True,
            )


# ---------------------------------------------------------------------------
# S5. The original bug: post-mutation observer ValueError must propagate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "observer_message",
    [
        "observer failed: stale state",
        "observer failed: expected_base_state mismatch",
        "stale / expected_base_state",
    ],
)
def test_s5_post_mutation_observer_valueerror_propagates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    observer_message: str,
) -> None:
    """A post-mutation failure is never reported as a zero-mutation status.

    ``apply_gesture_integration_plan`` assigns ``self._state = target`` and only
    then calls the observer. If that observer raises a ``ValueError`` carrying
    stale-flavoured words, the controller wraps it as
    ``GestureRackApplyPostMutationError`` and the Action must let it escape
    rather than return ``stale_base_state`` with ``applied_state=None`` (which
    would invite an unsafe retry against an already-mutated Rack).
    """
    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    _patch_analysis(monkeypatch, _ok_analysis(cluster_ids=(0,)))

    notified: list[str] = []

    def _explode() -> None:
        notified.append("obs")
        raise ValueError(observer_message)

    base = _action_base_state()
    controller = _action_controller(
        state=base,
        on_musical_state_changed=_explode,
    )

    with pytest.raises(GestureRackApplyPostMutationError) as excinfo:
        _action_call(
            audio_path=audio,
            channel_rack=controller,
            catalog_path=catalog,
            selections={0: "101"},
            feature_enabled=True,
        )

    # Reached (and passed) the mutation point, and the failure escaped.
    assert notified == ["obs"]
    assert not isinstance(excinfo.value, StaleGestureRackIntegrationPlanError)
    # The original observer error is preserved as the cause.
    assert isinstance(excinfo.value.__cause__, ValueError)
    assert str(excinfo.value.__cause__) == observer_message
    # The Rack really was mutated, which is exactly why this must not be
    # reported as a zero-mutation stale rejection.
    assert controller.state is not None
    assert controller.state != base


# ---------------------------------------------------------------------------
# S6. Static guards against reintroducing message-based classification
# ---------------------------------------------------------------------------


def test_s5b_observer_raising_the_typed_stale_error_still_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stale error raised *by the observer* must not map to stale_base_state.

    The observer may itself trigger a nested apply whose validation rejects.
    That exception is raised after the outer apply already replaced the state,
    so the controller must wrap it and the Action must let it escape.
    """

    audio = _write_placeholder_wav(tmp_path / "gesture.wav")
    catalog = _catalog_with_oneshots(tmp_path)
    _patch_analysis(monkeypatch, _ok_analysis(cluster_ids=(0,)))

    notified: list[str] = []

    def _nested_stale() -> None:
        notified.append("obs")
        raise StaleGestureRackIntegrationPlanError(
            "stale GestureRackIntegrationPlan: "
            "nested apply found expected_base_state mismatch"
        )

    base = _action_base_state()
    controller = _action_controller(
        state=base,
        on_musical_state_changed=_nested_stale,
    )

    with pytest.raises(GestureRackApplyPostMutationError) as excinfo:
        _action_call(
            audio_path=audio,
            channel_rack=controller,
            catalog_path=catalog,
            selections={0: "101"},
            feature_enabled=True,
        )

    assert notified == ["obs"]
    # Provenance preserved: the typed stale error is the cause, not the type
    # the Action maps to a status.
    assert isinstance(excinfo.value.__cause__, StaleGestureRackIntegrationPlanError)
    assert not isinstance(excinfo.value, StaleGestureRackIntegrationPlanError)
    # And the outer Rack really was mutated.
    assert controller.state is not None
    assert controller.state != base


def test_s5c_post_mutation_wrapper_is_not_a_valueerror() -> None:
    """The wrapper must be distinguishable from a pre-mutation rejection."""
    assert issubclass(GestureRackApplyPostMutationError, RuntimeError)
    assert not issubclass(GestureRackApplyPostMutationError, ValueError)
    assert not issubclass(
        StaleGestureRackIntegrationPlanError, GestureRackApplyPostMutationError
    )


def test_s5d_observer_wrapper_preserves_cause_for_arbitrary_errors() -> None:
    base = _action_base_state()
    plan = _build_plan(base)
    controller = _plan_controller(
        state=base,
        on_musical_state_changed=lambda: (_ for _ in ()).throw(
            RuntimeError("observer boom")
        ),
    )

    with pytest.raises(GestureRackApplyPostMutationError) as excinfo:
        _apply_raw(controller, plan, feature_enabled=True)

    assert isinstance(excinfo.value.__cause__, RuntimeError)
    assert "observer boom" in str(excinfo.value)
    assert "observer boom" in str(excinfo.value.__cause__)


def test_s6_action_catches_no_bare_value_error() -> None:
    source = _ACTION_MODULE.read_text(encoding="utf-8")
    tree = ast.parse(source)

    caught: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            names: list[str] = []
            exc = node.type
            if isinstance(exc, ast.Name):
                names.append(exc.id)
            elif isinstance(exc, ast.Tuple):
                names.extend(
                    e.id for e in exc.elts if isinstance(e, ast.Name)
                )
            elif exc is None:
                names.append("<bare except>")
            caught.extend(names)

    assert "ValueError" not in caught
    assert "<bare except>" not in caught
    assert "StaleGestureRackIntegrationPlanError" in caught


def test_s6b_action_has_no_message_based_stale_helper() -> None:
    source = _ACTION_MODULE.read_text(encoding="utf-8")
    assert "_is_stale_base_state_error" not in source
    # The old predicate matched on these substrings; they must not drive
    # classification anywhere in the Action module.
    assert '"stale" in' not in source
    assert '"expected_base_state" in' not in source


def test_s6c_stale_branch_raises_the_typed_error() -> None:
    source = _RACK_MODULE.read_text(encoding="utf-8")
    tree = ast.parse(source)

    typed_raises = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Raise)
        and isinstance(node.exc, ast.Call)
        and isinstance(node.exc.func, ast.Name)
        and node.exc.func.id == "StaleGestureRackIntegrationPlanError"
    ]
    assert len(typed_raises) == 1, "typed stale error must have exactly one raise site"

    # The post-mutation observer must be guarded, so no observer exception can
    # escape as the typed stale error.
    post_mutation_raises = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Raise)
        and isinstance(node.exc, ast.Call)
        and isinstance(node.exc.func, ast.Name)
        and node.exc.func.id == "GestureRackApplyPostMutationError"
    ]
    assert len(post_mutation_raises) == 1, (
        "observer failure must be wrapped exactly once, after the state "
        "assignment"
    )


# ---------------------------------------------------------------------------
# S7. Contract document lifecycle is current, not frozen
# ---------------------------------------------------------------------------


def test_s7_contract_document_lifecycle_is_current() -> None:
    doc = _CONTRACT_DOC.read_text(encoding="utf-8")
    head = doc.split("\n", 40)[0:40]

    assert "**Status:** `IMPLEMENTED`" in doc
    assert "not yet merged" in doc

    # The freeze-time wording is retained only as explicitly historical text.
    for chunk in head:
        if "TEST_FREEZE" in chunk and "absent" in chunk:
            assert "Historical" in chunk or "historical" in chunk, chunk

    # No live claim that the module is still missing.
    assert "Action module absent by design" not in doc
    assert "missing piece is this Action seam only" not in doc
