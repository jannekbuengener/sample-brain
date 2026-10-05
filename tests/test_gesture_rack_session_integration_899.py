"""Frozen acceptance for R&D Slice 7 — Rack/Session integration plan (#680 / #899).

Docs authority: docs/GESTURE_RACK_SESSION_INTEGRATION_RND_SLICE7.md

Synthetic fixtures only — no audio, no DB, no private catalogs, no QML.
"""

from __future__ import annotations

import ast
import copy
import importlib
import inspect
from fractions import Fraction
from pathlib import Path
from unittest import mock

import pytest

from src.channel_rack import ChannelRackState
from src.gesture_pattern_core_composition import GesturePatternCoreComposition
from src.pattern_core import Channel, Pattern, Trigger

# Import under test — RED until IMPLEMENTATION adds the module.
from src.gesture_rack_integration import (
    GestureRackIntegrationPlan,
    plan_gesture_rack_integration,
)

_MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "src" / "gesture_rack_integration.py"
)

_ALLOWED_IMPORT_ROOTS = frozenset(
    {
        "annotations",
        "__future__",
        "dataclasses",
        "fractions",
        "typing",
        "collections",
        "collections.abc",
        "channel_rack",
        "src.channel_rack",
        "gesture_pattern_core_composition",
        "src.gesture_pattern_core_composition",
        "pattern_core",
        "src.pattern_core",
    }
)

_BANNED_IMPORT_ROOTS = frozenset(
    {
        "workbench_channel_rack",
        "src.workbench_channel_rack",
        "workbench_session",
        "src.workbench_session",
        "workbench_session_store",
        "src.workbench_session_store",
        "workbench_qml",
        "src.workbench_qml",
        "gesture_pattern_binding",
        "src.gesture_pattern_binding",
        "gesture_catalog_adapter",
        "src.gesture_catalog_adapter",
        "gesture_library_ranking",
        "src.gesture_library_ranking",
        "gesture_timing_projection",
        "src.gesture_timing_projection",
        "gesture_analysis",
        "src.gesture_analysis",
        "sqlite3",
        "sqlalchemy",
        "db",
        "src.db",
        "librosa",
        "soundfile",
        "numpy",
        "torch",
    }
)

_BANNED_NAME_CALLS = frozenset(
    {
        "add_user_channel",
        "assign_user_channel_sample",
        "build_channel_rack_state",
        "restore_state",
        "allocate_user_channel_id",
        "play_channel_rack_once",
        "save_workbench_session_snapshot",
        "snapshot_from_musical_state",
    }
)


def _live_kit_channel(
    channel_id: str,
    group: str,
    slot: str,
    *,
    sample_path: str | None = "kit.wav",
) -> Channel:
    return Channel(
        channel_id=channel_id,
        live_kit_group=group,
        live_kit_slot=slot,
        sample_path=sample_path,
    )


def _user_channel(channel_id: str, *, sample_path: str = "user.wav") -> Channel:
    return Channel(
        channel_id=channel_id,
        live_kit_group=None,
        live_kit_slot=None,
        sample_path=sample_path,
    )


def _pattern(
    pattern_id: str,
    *,
    length: Fraction = Fraction(4, 1),
    triggers: tuple[Trigger, ...] = (),
) -> Pattern:
    return Pattern(
        pattern_id=pattern_id,
        length_quarter_notes=length,
        triggers=triggers,
    )


def _base_state(
    *,
    channels: tuple[Channel, ...] | None = None,
    pattern: Pattern | None = None,
    step_count: int = 16,
) -> ChannelRackState:
    if channels is None:
        channels = (
            _live_kit_channel("ch_kick", "Kick + Bass", "Kick"),
            _live_kit_channel("ch_bass", "Kick + Bass", "Bass", sample_path=None),
            _user_channel("ch_user_9", sample_path="existing.wav"),
        )
    if pattern is None:
        pattern = _pattern(
            "screen2-main",
            triggers=(
                Trigger(channel_id="ch_kick", position=Fraction(0, 4)),
                Trigger(channel_id="ch_kick", position=Fraction(4, 4)),
                Trigger(channel_id="ch_user_9", position=Fraction(2, 4)),
            ),
        )
    return ChannelRackState(
        channels=channels,
        pattern=pattern,
        step_count=step_count,
    )


def _composition(
    *,
    channels: tuple[Channel, ...] | None = None,
    pattern: Pattern | None = None,
) -> GesturePatternCoreComposition:
    if channels is None:
        channels = (_user_channel("ch_user_1", sample_path="gesture_a.wav"),)
    if pattern is None:
        pattern = _pattern(
            "gesture-pat-1",
            length=Fraction(8, 1),
            triggers=(
                Trigger(channel_id="ch_user_1", position=Fraction(0, 4)),
                Trigger(channel_id="ch_user_1", position=Fraction(1, 4)),
                Trigger(channel_id="ch_user_1", position=Fraction(1, 3)),
            ),
        )
    return GesturePatternCoreComposition(channels=channels, pattern=pattern)


def _plan(
    base: ChannelRackState | None = None,
    composition: GesturePatternCoreComposition | None = None,
    *,
    allow_pattern_replacement: bool = True,
) -> GestureRackIntegrationPlan:
    return plan_gesture_rack_integration(
        base if base is not None else _base_state(),
        composition if composition is not None else _composition(),
        allow_pattern_replacement=allow_pattern_replacement,
    )


def _source_text() -> str:
    return _MODULE_PATH.read_text(encoding="utf-8")


def _imported_module_names(mod) -> set[str]:
    path = Path(mod.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
                names.add(node.module)
    return names


def _called_names(mod) -> set[str]:
    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
    return names


# ---------------------------------------------------------------------------
# Happy path — channels / pattern / step_count
# ---------------------------------------------------------------------------


def test_base_channels_preserved_and_composition_channel_appended():
    base = _base_state()
    composition = _composition()
    plan = _plan(base, composition, allow_pattern_replacement=True)

    assert plan.target_channels[: len(base.channels)] == base.channels
    assert plan.target_channels[len(base.channels) :] == composition.channels
    assert plan.appended_channel_ids == ("ch_user_1",)


def test_multiple_composition_channels_preserve_composition_order():
    composition = _composition(
        channels=(
            _user_channel("ch_user_1", sample_path="a.wav"),
            _user_channel("ch_user_2", sample_path="b.wav"),
        ),
        pattern=_pattern(
            "gesture-pat-2",
            triggers=(
                Trigger(channel_id="ch_user_1", position=Fraction(0, 4)),
                Trigger(channel_id="ch_user_2", position=Fraction(1, 4)),
            ),
        ),
    )
    plan = _plan(_base_state(), composition, allow_pattern_replacement=True)
    assert plan.appended_channel_ids == ("ch_user_1", "ch_user_2")
    assert plan.target_channels[-2:] == composition.channels


def test_live_kit_seed_provenance_unchanged():
    base = _base_state()
    plan = _plan(base, allow_pattern_replacement=True)
    preserved = plan.target_channels[0]
    assert preserved.channel_id == "ch_kick"
    assert preserved.live_kit_group == "Kick + Bass"
    assert preserved.live_kit_slot == "Kick"
    assert preserved.sample_path == "kit.wav"
    assert preserved == base.channels[0]


def test_existing_user_channels_unchanged():
    base = _base_state()
    plan = _plan(base, allow_pattern_replacement=True)
    assert plan.target_channels[2] == base.channels[2]
    assert plan.target_channels[2].live_kit_group is None
    assert plan.target_channels[2].live_kit_slot is None


def test_target_pattern_equals_composition_pattern_exactly():
    composition = _composition()
    plan = _plan(_base_state(), composition, allow_pattern_replacement=True)
    assert plan.target_pattern == composition.pattern
    assert plan.target_pattern.pattern_id == "gesture-pat-1"
    assert plan.target_pattern.length_quarter_notes == Fraction(8, 1)
    assert plan.target_pattern.triggers == composition.pattern.triggers


def test_incumbent_triggers_not_merged_into_target_pattern():
    base = _base_state()
    composition = _composition()
    plan = _plan(base, composition, allow_pattern_replacement=True)
    for trigger in base.pattern.triggers:
        assert trigger not in plan.target_pattern.triggers
    assert plan.target_pattern.triggers == composition.pattern.triggers


def test_incumbent_pattern_length_does_not_influence_target_length():
    base = _base_state(
        pattern=_pattern("screen2-main", length=Fraction(4, 1), triggers=()),
    )
    composition = _composition(
        pattern=_pattern(
            "gesture-pat-1",
            length=Fraction(7, 2),
            triggers=(Trigger(channel_id="ch_user_1", position=Fraction(0, 1)),),
        )
    )
    plan = _plan(base, composition, allow_pattern_replacement=True)
    assert plan.target_pattern.length_quarter_notes == Fraction(7, 2)
    assert plan.target_pattern.length_quarter_notes != base.pattern.length_quarter_notes


def test_incumbent_pattern_id_does_not_overwrite_composition_pattern_id():
    base = _base_state()
    composition = _composition()
    plan = _plan(base, composition, allow_pattern_replacement=True)
    assert plan.target_pattern.pattern_id == composition.pattern.pattern_id
    assert plan.target_pattern.pattern_id != base.pattern.pattern_id
    assert plan.replaced_pattern_id == "gesture-pat-1"


def test_allow_pattern_replacement_true_may_be_ready():
    plan = _plan(allow_pattern_replacement=True)
    assert plan.ready_for_apply is True


def test_replacement_not_allowed_plan_not_ready_no_fallback_merge():
    base = _base_state()
    composition = _composition()
    plan = _plan(base, composition, allow_pattern_replacement=False)
    assert plan.ready_for_apply is False
    assert plan.target_pattern == composition.pattern
    assert plan.target_channels == base.channels + composition.channels
    for trigger in base.pattern.triggers:
        assert trigger not in plan.target_pattern.triggers


# ---------------------------------------------------------------------------
# Fail closed — collisions / no reallocation
# ---------------------------------------------------------------------------


def test_composition_channel_id_collision_with_base_fail_closed():
    base = _base_state()
    composition = _composition(
        channels=(_user_channel("ch_kick", sample_path="collide.wav"),),
        pattern=_pattern(
            "gesture-pat-x",
            triggers=(Trigger(channel_id="ch_kick", position=Fraction(0, 4)),),
        ),
    )
    with pytest.raises(ValueError, match="collision|already exist|duplicate"):
        _plan(base, composition, allow_pattern_replacement=True)


def test_duplicate_composition_ids_fail_closed():
    composition = GesturePatternCoreComposition(
        channels=(
            _user_channel("ch_user_1", sample_path="a.wav"),
            _user_channel("ch_user_1", sample_path="b.wav"),
        ),
        pattern=_pattern(
            "gesture-pat-x",
            triggers=(Trigger(channel_id="ch_user_1", position=Fraction(0, 4)),),
        ),
    )
    # ChannelRackState / Pattern membership may not catch composition dupes;
    # planner must reject independently. Composition type allows constructing
    # via object.__new__ bypass if frozen validation blocks duplicates — use
    # a minimal stand-in when GesturePatternCoreComposition construction fails.
    try:
        bad = composition
    except Exception:  # pragma: no cover - defensive
        bad = None
    if bad is None or len({c.channel_id for c in bad.channels}) == len(bad.channels):
        # Construct a composition-like object with duplicate IDs if dataclass
        # does not validate uniqueness (current #893 delta does not).
        bad = GesturePatternCoreComposition(
            channels=(
                _user_channel("ch_user_1", sample_path="a.wav"),
                _user_channel("ch_user_1", sample_path="b.wav"),
            ),
            pattern=_pattern(
                "gesture-pat-x",
                triggers=(Trigger(channel_id="ch_user_1", position=Fraction(0, 4)),),
            ),
        )
    with pytest.raises(ValueError, match="duplicate"):
        _plan(_base_state(), bad, allow_pattern_replacement=True)


def test_no_channel_reallocation_helper_used():
    mod = importlib.import_module("src.gesture_rack_integration")
    called = _called_names(mod)
    assert "allocate_user_channel_id" not in called
    source = _source_text()
    assert "allocate_user_channel_id" not in source


def test_no_path_based_channel_reuse():
    base = _base_state(
        channels=(
            _live_kit_channel("ch_kick", "Kick + Bass", "Kick", sample_path="same.wav"),
        ),
        pattern=_pattern("screen2-main", triggers=()),
    )
    composition = _composition(
        channels=(_user_channel("ch_user_1", sample_path="same.wav"),),
        pattern=_pattern(
            "gesture-pat-1",
            triggers=(Trigger(channel_id="ch_user_1", position=Fraction(0, 4)),),
        ),
    )
    plan = _plan(base, composition, allow_pattern_replacement=True)
    assert plan.target_channels[0].channel_id == "ch_kick"
    assert plan.target_channels[1].channel_id == "ch_user_1"
    assert plan.target_channels[0].sample_path == plan.target_channels[1].sample_path
    assert len(plan.target_channels) == 2


def test_no_live_kit_taxonomy_assignment_on_appended_channels():
    plan = _plan(allow_pattern_replacement=True)
    for channel_id in plan.appended_channel_ids:
        channel = next(c for c in plan.target_channels if c.channel_id == channel_id)
        assert channel.live_kit_group is None
        assert channel.live_kit_slot is None


def test_no_default_on_triggers_added():
    composition = _composition(
        channels=(_user_channel("ch_user_1", sample_path="g.wav"),),
        pattern=_pattern(
            "gesture-pat-1",
            triggers=(Trigger(channel_id="ch_user_1", position=Fraction(1, 3)),),
        ),
    )
    plan = _plan(_base_state(), composition, allow_pattern_replacement=True)
    assert plan.target_pattern.triggers == composition.pattern.triggers
    assert plan.replaced_trigger_count == 1
    # DEFAULT_ON would seed 16 steps for a sample-bearing channel.
    assert len(plan.target_pattern.triggers) != 16


# ---------------------------------------------------------------------------
# Timing / step_count / off-grid evidence
# ---------------------------------------------------------------------------


def test_exact_unquantized_fractions_preserved():
    positions = (Fraction(0, 4), Fraction(1, 3), Fraction(5, 7))
    composition = _composition(
        pattern=_pattern(
            "gesture-pat-1",
            length=Fraction(4, 1),
            triggers=tuple(
                Trigger(channel_id="ch_user_1", position=pos) for pos in positions
            ),
        )
    )
    plan = _plan(_base_state(), composition, allow_pattern_replacement=True)
    assert tuple(t.position for t in plan.target_pattern.triggers) == positions
    for position in (t.position for t in plan.target_pattern.triggers):
        assert type(position) is Fraction


def test_repeated_gesture_events_preserved():
    composition = _composition(
        pattern=_pattern(
            "gesture-pat-1",
            triggers=(
                Trigger(channel_id="ch_user_1", position=Fraction(1, 4)),
                Trigger(channel_id="ch_user_1", position=Fraction(1, 4)),
            ),
        )
    )
    # Pattern Core may normalize/dedupe equal (position, channel_id) — if construction
    # rejects or collapses, planner must still preserve whatever composition.pattern holds.
    plan = _plan(_base_state(), composition, allow_pattern_replacement=True)
    assert plan.target_pattern.triggers == composition.pattern.triggers


def test_target_step_count_equals_base_step_count():
    base = _base_state(step_count=16)
    composition = _composition(
        pattern=_pattern(
            "gesture-pat-1",
            length=Fraction(32, 1),
            triggers=(Trigger(channel_id="ch_user_1", position=Fraction(0, 4)),),
        )
    )
    plan = _plan(base, composition, allow_pattern_replacement=True)
    assert plan.target_step_count == 16
    assert plan.target_step_count == base.step_count


def test_canonical_sixteenth_positions_counted_as_on_grid():
    composition = _composition(
        pattern=_pattern(
            "gesture-pat-1",
            triggers=(
                Trigger(channel_id="ch_user_1", position=Fraction(0, 4)),
                Trigger(channel_id="ch_user_1", position=Fraction(1, 4)),
                Trigger(channel_id="ch_user_1", position=Fraction(15, 4)),
            ),
        )
    )
    plan = _plan(_base_state(step_count=16), composition, allow_pattern_replacement=True)
    assert plan.off_grid_event_count == 0


def test_non_sixteenth_fraction_positions_counted_as_off_grid():
    composition = _composition(
        pattern=_pattern(
            "gesture-pat-1",
            triggers=(
                Trigger(channel_id="ch_user_1", position=Fraction(0, 4)),  # on-grid
                Trigger(channel_id="ch_user_1", position=Fraction(1, 3)),  # off-grid
                Trigger(channel_id="ch_user_1", position=Fraction(5, 8)),  # off-grid
            ),
        )
    )
    plan = _plan(_base_state(step_count=16), composition, allow_pattern_replacement=True)
    assert plan.off_grid_event_count == 2


def test_off_grid_evidence_does_not_mutate_drop_or_snap_events():
    triggers = (
        Trigger(channel_id="ch_user_1", position=Fraction(1, 3)),
        Trigger(channel_id="ch_user_1", position=Fraction(5, 8)),
    )
    composition = _composition(
        pattern=_pattern("gesture-pat-1", triggers=triggers),
    )
    plan = _plan(_base_state(), composition, allow_pattern_replacement=True)
    assert plan.target_pattern.triggers == triggers
    assert plan.off_grid_event_count == 2
    assert plan.target_pattern.triggers[0].position == Fraction(1, 3)


# ---------------------------------------------------------------------------
# Immutability / determinism / stale-state binding
# ---------------------------------------------------------------------------


def test_input_base_state_unchanged():
    base = _base_state()
    before = copy.deepcopy(base)
    _plan(base, _composition(), allow_pattern_replacement=True)
    assert base == before


def test_input_composition_unchanged():
    composition = _composition()
    before = copy.deepcopy(composition)
    _plan(_base_state(), composition, allow_pattern_replacement=True)
    assert composition == before


def test_same_inputs_twice_equal_integration_plan():
    base = _base_state()
    composition = _composition()
    plan_a = _plan(base, composition, allow_pattern_replacement=True)
    plan_b = _plan(base, composition, allow_pattern_replacement=True)
    assert plan_a == plan_b


def test_plan_carries_exact_expected_base_state_guard():
    base = _base_state()
    plan = _plan(base, allow_pattern_replacement=True)
    assert plan.expected_base_state == base
    assert isinstance(plan.expected_base_state, ChannelRackState)


def test_stale_state_future_apply_rule_documented_in_contract():
    doc = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "GESTURE_RACK_SESSION_INTEGRATION_RND_SLICE7.md"
    ).read_text(encoding="utf-8")
    assert "expected_base_state" in doc
    assert "stale" in doc.lower()
    assert "compare-before-apply" in doc or "compare-before-apply" in doc.replace(
        " ", "-"
    )
    assert "fail closed" in doc.lower() or "fail-closed" in doc.lower()


def test_plan_type_is_frozen_dataclass():
    plan = _plan(allow_pattern_replacement=True)
    assert isinstance(plan, GestureRackIntegrationPlan)
    with pytest.raises(Exception):
        plan.ready_for_apply = False  # type: ignore[misc]


def test_target_channel_set_satisfies_trigger_membership():
    plan = _plan(allow_pattern_replacement=True)
    known = {c.channel_id for c in plan.target_channels}
    for trigger in plan.target_pattern.triggers:
        assert trigger.channel_id in known


# ---------------------------------------------------------------------------
# AST / import / no mutation side-effect surfaces
# ---------------------------------------------------------------------------


def test_module_import_allowlist_and_banlist():
    mod = importlib.import_module("src.gesture_rack_integration")
    imported = _imported_module_names(mod)
    banned_hits = imported & _BANNED_IMPORT_ROOTS
    assert not banned_hits, f"banned imports present: {sorted(banned_hits)}"
    # Relative imports appear as module names without src. prefix.
    unexpected = {
        name
        for name in imported
        if name not in _ALLOWED_IMPORT_ROOTS
        and not name.startswith("src.")
        and name
        not in {
            "channel_rack",
            "gesture_pattern_core_composition",
            "pattern_core",
        }
    }
    # Allow only known roots; ignore nested relative package fragments already checked.
    for name in sorted(unexpected):
        root = name.split(".")[0]
        assert root in _ALLOWED_IMPORT_ROOTS or name in _ALLOWED_IMPORT_ROOTS, (
            f"unexpected import root: {name}"
        )


def test_no_banned_mutation_helper_calls_in_module_ast():
    mod = importlib.import_module("src.gesture_rack_integration")
    called = _called_names(mod)
    banned = called & _BANNED_NAME_CALLS
    assert not banned, f"banned calls present: {sorted(banned)}"


def test_planner_does_not_reference_controller_private_state():
    source = _source_text()
    assert "._state" not in source
    assert "ChannelRackController" not in source
    assert "restore_state" not in source


def test_planner_public_seam_signature():
    sig = inspect.signature(plan_gesture_rack_integration)
    params = list(sig.parameters.values())
    assert params[0].name == "base_state"
    assert params[1].name == "composition"
    assert "allow_pattern_replacement" in sig.parameters
    assert sig.parameters["allow_pattern_replacement"].kind is inspect.Parameter.KEYWORD_ONLY


def test_no_channel_rack_mutation_helpers_invoked_at_runtime():
    with (
        mock.patch("src.channel_rack.add_user_channel") as add_user,
        mock.patch("src.channel_rack.assign_user_channel_sample") as assign,
        mock.patch("src.channel_rack.build_channel_rack_state") as build,
    ):
        _plan(allow_pattern_replacement=True)
    add_user.assert_not_called()
    assign.assert_not_called()
    build.assert_not_called()


def test_contract_doc_forbids_owner_file_mutation():
    doc = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "GESTURE_RACK_SESSION_INTEGRATION_RND_SLICE7.md"
    ).read_text(encoding="utf-8")
    for path in (
        "workbench_channel_rack.py",
        "workbench_session.py",
        "workbench_session_store.py",
        "workbench_qml.py",
    ):
        assert path in doc
    assert "NO RACK STATE MUTATION IN THIS SLICE" in doc
    assert "EXPLICIT_RACK_REPLACEMENT_PLAN_VIABLE" in doc


def test_replaced_trigger_count_matches_composition_triggers():
    composition = _composition()
    plan = _plan(_base_state(), composition, allow_pattern_replacement=True)
    assert plan.replaced_trigger_count == len(composition.pattern.triggers)


def test_allow_pattern_replacement_must_be_exact_true():
    plan = plan_gesture_rack_integration(
        _base_state(),
        _composition(),
        allow_pattern_replacement=1,  # type: ignore[arg-type]
    )
    assert plan.ready_for_apply is False
