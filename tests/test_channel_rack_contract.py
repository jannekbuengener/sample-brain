"""TEST_GATE / TEST_FREEZE — Minimal Screen-2 Channel Rack core contract.

Canonical authority:
- docs/PRODUCT_WORKFLOW_CANON.md (build-order step 5 precursor: Python core)
- docs/SESSION_OWNERSHIP_CONTRACT.md
- docs/PATTERN_CORE_CONTRACT.md
- docs/SEQUENCER_PLAYBACK_CONTRACT.md
- src/workbench_session.py
- src/workbench_live_kit.py
- src/pattern_core.py
- src/sequencer_playback.py
- src/session_grid.py

This file freezes the public seam ``src.channel_rack`` before any product
implementation. Expected baseline on current main: intentional RED until a
separate IMPLEMENTATION_GATE lands the module.

v1 scope frozen here:
- Live Kit → 11 Channel rows (canonical LIVE_KIT_SLOT_MAPPING order)
- one Pattern (``screen2-main``), length Fraction(4, 1), 16 steps
- immutable toggle_step (position = step_index / 4 quarter notes)
- ONE_PATTERN_PASS via existing sequencer_playback (no duplicate scheduling)
- Python-owned musical state only — no QML / PySide6 / Screen-2 widgets

Forbidden in this slice (asserted below):
- Screen-2 QML / Tk visual surfaces
- arrangement / mixer / piano roll
- TransportAwarePreview audition routing
- continuous looping / multi-pattern banks
"""

from __future__ import annotations

import ast
import importlib
import inspect
from dataclasses import fields, is_dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.pattern_core import CHANNEL_ID_BY_LIVE_KIT_SLOT, Channel, Pattern, Trigger
from src.session_grid import TempoMap
from src.workbench_controller import WorkbenchRow
from src.workbench_live_kit import LIVE_KIT_SLOT_MAPPING, LiveKitState


REQUIRED_PUBLIC_SYMBOLS = (
    "ChannelRackState",
    "build_channel_rack_state",
    "toggle_step",
    "play_channel_rack_once",
)

DEFAULT_PATTERN_ID = "screen2-main"
EXPECTED_STEP_COUNT = 16
EXPECTED_PATTERN_LENGTH = Fraction(4, 1)
EXPECTED_CHANNEL_COUNT = 11

FORBIDDEN_CHANNEL_RACK_SURFACE_TOKENS = (
    "TransportAwarePreview",
    "WorkbenchPreviewPlayer",
    "Screen2View",
    "workbench_qml",
    "PySide6",
    "QtQuick",
    "arrangement",
    "piano_roll",
    "PianoRoll",
    "mixer",
    "send_bus",
    "insert_fx",
    "wall_clock",
    "loop_forever",
)


def _channel_rack_or_fail():
    try:
        return importlib.import_module("src.channel_rack")
    except ModuleNotFoundError as exc:
        if exc.name in {"src.channel_rack", "channel_rack"} or (
            exc.name is not None and exc.name.endswith("channel_rack")
        ):
            pytest.fail(
                "MISSING_PRODUCTION_SURFACE: src.channel_rack "
                "(Channel Rack core not implemented — expected RED until "
                "IMPLEMENTATION_GATE)"
            )
        raise


def _require_symbol(module, name: str):
    value = getattr(module, name, None)
    if value is None:
        pytest.fail(f"MISSING_PRODUCTION_SURFACE: src.channel_rack.{name}")
    return value


def _canonical_live_kit_slots() -> list[tuple[str, str]]:
    return [(group, slot) for group, slots in LIVE_KIT_SLOT_MAPPING for slot in slots]


def _synthetic_row(name: str, path: str) -> WorkbenchRow:
    return WorkbenchRow(
        display_name=name,
        relative_path=path,
        path=path,
        bpm=120.0,
        key="Cmaj",
        key_conf=0.9,
        loudness=-18.0,
        brightness=2400.0,
        sample_class="oneshot",
        pred_type="Kick",
        status="ok",
        details={"source": "synthetic"},
    )


def _empty_live_kit() -> LiveKitState:
    return LiveKitState()


def _live_kit_with_kick(path: str = "synthetic/kick_01.wav") -> LiveKitState:
    state = LiveKitState()
    state.assign("Kick + Bass", "Kick", _synthetic_row("kick_01", path))
    return state


def _build_state(module, live_kit: LiveKitState | None = None):
    build = _require_symbol(module, "build_channel_rack_state")
    return build(live_kit if live_kit is not None else _empty_live_kit())


# --- Public API --------------------------------------------------------------


def test_channel_rack_public_api_is_importable():
    module = _channel_rack_or_fail()
    for name in REQUIRED_PUBLIC_SYMBOLS:
        _require_symbol(module, name)


def test_build_channel_rack_projects_all_11_canonical_live_kit_channels():
    module = _channel_rack_or_fail()
    ChannelRackState = _require_symbol(module, "ChannelRackState")

    state = _build_state(module)
    assert isinstance(state, ChannelRackState)
    assert is_dataclass(state) and state.__dataclass_params__.frozen
    field_names = {f.name for f in fields(ChannelRackState)}
    assert {"channels", "pattern", "step_count"} <= field_names

    assert len(state.channels) == EXPECTED_CHANNEL_COUNT
    assert all(isinstance(ch, Channel) for ch in state.channels)

    expected_ids = [
        CHANNEL_ID_BY_LIVE_KIT_SLOT[(group, slot)]
        for group, slot in _canonical_live_kit_slots()
    ]
    assert [ch.channel_id for ch in state.channels] == expected_ids
    assert len({ch.channel_id for ch in state.channels}) == EXPECTED_CHANNEL_COUNT


def test_channel_order_matches_live_kit_canonical_order():
    module = _channel_rack_or_fail()
    state = _build_state(module)

    expected = _canonical_live_kit_slots()
    assert len(state.channels) == len(expected)
    for channel, (group, slot) in zip(state.channels, expected, strict=True):
        assert channel.live_kit_group == group
        assert channel.live_kit_slot == slot
        assert channel.channel_id == CHANNEL_ID_BY_LIVE_KIT_SLOT[(group, slot)]


def test_assigned_live_kit_slot_becomes_channel_sample_path():
    module = _channel_rack_or_fail()
    path = "synthetic/kick_assigned.wav"
    state = _build_state(module, _live_kit_with_kick(path))

    kick = next(ch for ch in state.channels if ch.channel_id == "ch_kick")
    assert kick.sample_path == path
    # Projection only — Channel must not own PCM / audio payload fields.
    channel_fields = {f.name.lower() for f in fields(type(kick))}
    assert {"pcm", "audio", "samples", "buffer", "waveform"}.isdisjoint(channel_fields)


def test_empty_live_kit_slot_becomes_channel_with_none_sample_path():
    module = _channel_rack_or_fail()
    state = _build_state(module, _live_kit_with_kick())

    empty = [ch for ch in state.channels if ch.channel_id != "ch_kick"]
    assert len(empty) == 10
    assert all(ch.sample_path is None for ch in empty)


def test_default_pattern_is_four_quarter_notes_and_16_steps():
    module = _channel_rack_or_fail()
    state = _build_state(module)

    assert state.step_count == EXPECTED_STEP_COUNT
    assert isinstance(state.pattern, Pattern)
    assert state.pattern.pattern_id == DEFAULT_PATTERN_ID
    assert state.pattern.length_quarter_notes == EXPECTED_PATTERN_LENGTH
    assert type(state.pattern.length_quarter_notes) is Fraction
    assert state.pattern.triggers == ()


# --- toggle_step -------------------------------------------------------------


def test_toggle_empty_step_adds_exact_fraction_trigger():
    module = _channel_rack_or_fail()
    toggle = _require_symbol(module, "toggle_step")
    state = _build_state(module)

    next_state = toggle(state, "ch_kick", 0)
    assert next_state.pattern.triggers == (
        Trigger(channel_id="ch_kick", position=Fraction(0, 4)),
    )

    next_state = toggle(state, "ch_closed_hat", 3)
    assert next_state.pattern.triggers == (
        Trigger(channel_id="ch_closed_hat", position=Fraction(3, 4)),
    )

    next_state = toggle(state, "ch_fx", 15)
    assert next_state.pattern.triggers == (
        Trigger(channel_id="ch_fx", position=Fraction(15, 4)),
    )
    assert type(next_state.pattern.triggers[0].position) is Fraction


def test_toggle_active_step_removes_exact_trigger():
    module = _channel_rack_or_fail()
    toggle = _require_symbol(module, "toggle_step")
    state = _build_state(module)

    on = toggle(state, "ch_kick", 4)
    assert len(on.pattern.triggers) == 1
    off = toggle(on, "ch_kick", 4)
    assert off.pattern.triggers == ()


def test_toggle_is_reversible():
    module = _channel_rack_or_fail()
    toggle = _require_symbol(module, "toggle_step")
    state = _build_state(module)

    once = toggle(state, "ch_bass", 7)
    twice = toggle(once, "ch_bass", 7)
    thrice = toggle(twice, "ch_bass", 7)

    assert twice.pattern.triggers == state.pattern.triggers
    assert thrice.pattern.triggers == once.pattern.triggers


def test_toggle_preserves_unrelated_triggers():
    module = _channel_rack_or_fail()
    toggle = _require_symbol(module, "toggle_step")
    state = _build_state(module)

    with_kick = toggle(state, "ch_kick", 0)
    with_hat = toggle(with_kick, "ch_closed_hat", 2)
    toggled_kick_off = toggle(with_hat, "ch_kick", 0)

    assert toggled_kick_off.pattern.triggers == (
        Trigger(channel_id="ch_closed_hat", position=Fraction(2, 4)),
    )
    assert with_hat.pattern.pattern_id == DEFAULT_PATTERN_ID
    assert with_hat.pattern.length_quarter_notes == EXPECTED_PATTERN_LENGTH
    assert with_hat.channels == state.channels
    assert with_hat.step_count == state.step_count


def test_toggle_returns_new_immutable_state_without_mutating_input():
    module = _channel_rack_or_fail()
    toggle = _require_symbol(module, "toggle_step")
    ChannelRackState = _require_symbol(module, "ChannelRackState")
    state = _build_state(module)
    original_triggers = state.pattern.triggers

    next_state = toggle(state, "ch_lead", 1)

    assert next_state is not state
    assert isinstance(next_state, ChannelRackState)
    assert is_dataclass(next_state) and next_state.__dataclass_params__.frozen
    assert state.pattern.triggers == original_triggers
    assert state.pattern.triggers == ()
    assert next_state.pattern.triggers == (
        Trigger(channel_id="ch_lead", position=Fraction(1, 4)),
    )
    # Pattern Core immutability: original Pattern object identity preserved.
    assert next_state.pattern is not state.pattern

    with pytest.raises(Exception):
        next_state.step_count = 8  # type: ignore[misc]


def test_toggle_rejects_unknown_channel_id():
    module = _channel_rack_or_fail()
    toggle = _require_symbol(module, "toggle_step")
    state = _build_state(module)

    with pytest.raises((ValueError, KeyError)):
        toggle(state, "ch_snare", 0)
    with pytest.raises((ValueError, KeyError)):
        toggle(state, "Kick", 0)


def test_toggle_rejects_step_below_zero():
    module = _channel_rack_or_fail()
    toggle = _require_symbol(module, "toggle_step")
    state = _build_state(module)

    with pytest.raises((ValueError, IndexError)):
        toggle(state, "ch_kick", -1)


def test_toggle_rejects_step_16_or_greater():
    module = _channel_rack_or_fail()
    toggle = _require_symbol(module, "toggle_step")
    state = _build_state(module)

    with pytest.raises((ValueError, IndexError)):
        toggle(state, "ch_kick", 16)
    with pytest.raises((ValueError, IndexError)):
        toggle(state, "ch_kick", 99)


def test_toggle_rejects_bool_step_index():
    """Bool is a subclass of int; step index must fail closed."""
    module = _channel_rack_or_fail()
    toggle = _require_symbol(module, "toggle_step")
    state = _build_state(module)

    with pytest.raises((TypeError, ValueError)):
        toggle(state, "ch_kick", True)  # type: ignore[arg-type]
    with pytest.raises((TypeError, ValueError)):
        toggle(state, "ch_kick", False)  # type: ignore[arg-type]


def test_same_step_across_multiple_channels_remains_polyphonic_and_deterministic():
    module = _channel_rack_or_fail()
    toggle = _require_symbol(module, "toggle_step")
    state = _build_state(module)

    # Same step index on three channels → three independent triggers at Fraction(2, 4).
    state = toggle(state, "ch_pad", 2)
    state = toggle(state, "ch_kick", 2)
    state = toggle(state, "ch_lead", 2)

    assert len(state.pattern.triggers) == 3
    positions = [t.position for t in state.pattern.triggers]
    assert positions == [Fraction(2, 4), Fraction(2, 4), Fraction(2, 4)]
    # Pattern Core sort: (position, channel_id) ascending.
    assert [t.channel_id for t in state.pattern.triggers] == [
        "ch_kick",
        "ch_lead",
        "ch_pad",
    ]


# --- Playback / architecture guards -----------------------------------------


def test_play_channel_rack_once_reuses_sequencer_public_seam(monkeypatch):
    module = _channel_rack_or_fail()
    play = _require_symbol(module, "play_channel_rack_once")
    toggle = _require_symbol(module, "toggle_step")

    import src.sequencer_playback as sequencer

    plan_calls: list[dict[str, Any]] = []
    schedule_calls: list[dict[str, Any]] = []
    sentinel_planned = (
        sequencer.ScheduledTrigger(
            channel_id="ch_kick",
            sample_path="synthetic/kick_01.wav",
            position=Fraction(0, 1),
            engine_frame=1000,
        ),
    )
    sentinel_result = sequencer.PlaybackScheduleResult(
        scheduled_voice_ids=(7,),
        scheduled_count=1,
        skipped_missing_source_count=0,
        skipped_voice_limit_count=0,
        skipped_engine_error_count=0,
    )

    def fake_plan(**kwargs):
        plan_calls.append(kwargs)
        return sentinel_planned

    def fake_schedule(**kwargs):
        schedule_calls.append(kwargs)
        return sentinel_result

    monkeypatch.setattr(sequencer, "plan_pattern_once", fake_plan)
    monkeypatch.setattr(sequencer, "schedule_pattern_once", fake_schedule)
    # Also patch names bound into channel_rack if imported via ``from … import``.
    if hasattr(module, "plan_pattern_once"):
        monkeypatch.setattr(module, "plan_pattern_once", fake_plan)
    if hasattr(module, "schedule_pattern_once"):
        monkeypatch.setattr(module, "schedule_pattern_once", fake_schedule)

    live_kit = _live_kit_with_kick()
    state = toggle(_build_state(module, live_kit), "ch_kick", 0)
    tempo_map = TempoMap(sample_rate=48_000, bpm=120)
    engine = MagicMock(name="native_engine")

    result = play(
        state,
        tempo_map=tempo_map,
        pattern_start_quarter=Fraction(0, 1),
        pattern_start_engine_frame=1000,
        engine=engine,
        pcm_for_path=lambda _path: None,
        allocate_voice_id=lambda: 1,
    )

    assert plan_calls, "play_channel_rack_once must call plan_pattern_once"
    assert schedule_calls, "play_channel_rack_once must call schedule_pattern_once"
    assert schedule_calls[0].get("planned_triggers") is sentinel_planned
    assert result is sentinel_result

    source = Path(inspect.getsourcefile(module) or "").read_text(encoding="utf-8")
    assert "plan_pattern_once" in source
    assert "schedule_pattern_once" in source
    # Must not re-implement frame conversion locally.
    assert "quarter_note_to_frame" not in source


def test_channel_rack_does_not_route_through_transport_aware_preview():
    module = _channel_rack_or_fail()
    play = _require_symbol(module, "play_channel_rack_once")

    source = Path(inspect.getsourcefile(module) or "").read_text(encoding="utf-8")
    assert "TransportAwarePreview" not in source
    assert "WorkbenchPreviewPlayer" not in source

    sig = inspect.signature(play)
    assert "preview" not in sig.parameters
    assert "audition" not in sig.parameters
    assert "engine" in sig.parameters


def test_channel_rack_slice_contains_no_arrangement_mixer_or_piano_roll_surface():
    module = _channel_rack_or_fail()
    source_path = Path(inspect.getsourcefile(module) or "")
    assert source_path.is_file()
    source = source_path.read_text(encoding="utf-8")

    for token in (
        "arrangement",
        "piano_roll",
        "PianoRoll",
        "mixer",
        "send_bus",
        "insert_fx",
    ):
        assert token not in source, f"forbidden Screen-2 surface token: {token}"

    tree = ast.parse(source)
    defined = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    for forbidden in (
        "ArrangementView",
        "MixerStrip",
        "PianoRoll",
        "Screen2View",
    ):
        assert forbidden not in defined

    public = {name for name in dir(module) if not name.startswith("_")}
    for forbidden in (
        "play_arrangement",
        "open_mixer",
        "open_piano_roll",
        "loop_pattern_forever",
    ):
        assert forbidden not in public


def test_channel_rack_core_contains_no_qml_or_pyside_dependency():
    module = _channel_rack_or_fail()
    source_path = Path(inspect.getsourcefile(module) or "")
    assert source_path.is_file()
    source = source_path.read_text(encoding="utf-8")

    for token in ("PySide6", "QtQuick", "workbench_qml", "Screen2View"):
        assert token not in source, f"forbidden QML/UI dependency token: {token}"

    tree = ast.parse(source)
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module.split(".")[0])

    assert "PySide6" not in imported_modules
    assert "PyQt6" not in imported_modules
    assert "PyQt5" not in imported_modules

    for token in FORBIDDEN_CHANNEL_RACK_SURFACE_TOKENS:
        assert token not in source, f"forbidden channel rack surface token: {token}"
