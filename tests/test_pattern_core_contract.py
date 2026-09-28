"""TEST_GATE / TEST_FREEZE — Minimal Pattern Core contract.

Canonical authority:
- docs/PRODUCT_WORKFLOW_CANON.md (build-order step 3)
- docs/PATTERN_CORE_CONTRACT.md
- docs/SESSION_OWNERSHIP_CONTRACT.md (completed prerequisite)
- src/session_grid.py (Fraction / TempoMap musical time)
- src/workbench_live_kit.py (LIVE_KIT_SLOT_MAPPING)

This file freezes the public seam ``src.pattern_core`` before any product
implementation. Expected baseline on current main: intentional RED until a
separate IMPLEMENTATION_GATE lands the module.

Forbidden in this slice (asserted below):
- NativeAudioEngine scheduling / schedule_voice_start
- Screen-2 / Channel Rack QML or Tk surfaces
- mixer / persistence ownership
"""

from __future__ import annotations

import ast
import importlib
import inspect
from dataclasses import fields
from fractions import Fraction
from pathlib import Path

import pytest

from src.session_grid import TempoMap
from src.workbench_live_kit import LIVE_KIT_SLOT_MAPPING


# --- Frozen channel ID contract (opaque; not label-slugified) -----------------

FROZEN_CHANNEL_ID_BY_LIVE_KIT_SLOT: dict[tuple[str, str], str] = {
    ("Kick + Bass", "Kick"): "ch_kick",
    ("Kick + Bass", "Bass"): "ch_bass",
    ("Drums", "Main Drum"): "ch_main_drum",
    ("Drums", "Closed Hat"): "ch_closed_hat",
    ("Drums", "Open Hat"): "ch_open_hat",
    ("Drums", "Percussion"): "ch_percussion",
    ("Drums", "Additional"): "ch_additional",
    ("Melodic", "Lead"): "ch_lead",
    ("Melodic", "Pad"): "ch_pad",
    ("Atmos / FX", "Atmos"): "ch_atmos",
    ("Atmos / FX", "FX"): "ch_fx",
}

REQUIRED_PUBLIC_SYMBOLS = (
    "CHANNEL_ID_BY_LIVE_KIT_SLOT",
    "channel_id_for_live_kit_slot",
    "Channel",
    "Trigger",
    "Pattern",
)

FORBIDDEN_PATTERN_CORE_SURFACE_TOKENS = (
    "NativeAudioEngine",
    "schedule_voice_start",
    "Screen2",
    "ChannelRack",
    "workbench_qml",
    "PySide6",
    "mixer",
    "sqlite",
    "CREATE TABLE",
)


def _pattern_core_or_fail():
    try:
        return importlib.import_module("src.pattern_core")
    except ModuleNotFoundError as exc:
        if exc.name in {"src.pattern_core", "pattern_core"} or (
            exc.name is not None and exc.name.endswith("pattern_core")
        ):
            pytest.fail(
                "MISSING_PRODUCTION_SURFACE: src.pattern_core "
                "(Pattern Core not implemented — expected RED until IMPLEMENTATION_GATE)"
            )
        raise


def _require_symbol(module, name: str):
    value = getattr(module, name, None)
    if value is None:
        pytest.fail(f"MISSING_PRODUCTION_SURFACE: src.pattern_core.{name}")
    return value


def _canonical_live_kit_slots() -> list[tuple[str, str]]:
    return [(group, slot) for group, slots in LIVE_KIT_SLOT_MAPPING for slot in slots]


# --- Public API --------------------------------------------------------------


def test_pattern_core_public_api_is_importable():
    module = _pattern_core_or_fail()
    for name in REQUIRED_PUBLIC_SYMBOLS:
        _require_symbol(module, name)


def test_every_live_kit_slot_has_one_stable_channel_id():
    module = _pattern_core_or_fail()
    mapping = _require_symbol(module, "CHANNEL_ID_BY_LIVE_KIT_SLOT")
    lookup = _require_symbol(module, "channel_id_for_live_kit_slot")

    expected_slots = _canonical_live_kit_slots()
    assert len(expected_slots) == 11

    # Exact coverage: no missing, no extra.
    mapping_keys = list(mapping.keys())
    assert mapping_keys == expected_slots
    assert set(mapping.keys()) == set(expected_slots)

    ids = [mapping[slot] for slot in expected_slots]
    assert len(ids) == len(set(ids))

    for group, slot in expected_slots:
        assert lookup(group, slot) == mapping[(group, slot)]
        assert isinstance(lookup(group, slot), str)


def test_channel_ids_are_explicit_stable_contract_not_label_slugification():
    module = _pattern_core_or_fail()
    mapping = _require_symbol(module, "CHANNEL_ID_BY_LIVE_KIT_SLOT")
    lookup = _require_symbol(module, "channel_id_for_live_kit_slot")

    assert dict(mapping) == FROZEN_CHANNEL_ID_BY_LIVE_KIT_SLOT

    # Stable contract values — not runtime slugification of display text.
    for (group, slot), channel_id in FROZEN_CHANNEL_ID_BY_LIVE_KIT_SLOT.items():
        assert lookup(group, slot) == channel_id
        slug_candidate = slot.lower().replace(" ", "_").replace("+", "").replace("/", "")
        # Opaque IDs may resemble words but must equal the frozen table, not a
        # derived slug of the current label alone (e.g. "Closed Hat" → closed_hat).
        assert channel_id == FROZEN_CHANNEL_ID_BY_LIVE_KIT_SLOT[(group, slot)]
        if slot == "Closed Hat":
            assert channel_id == "ch_closed_hat"
            assert channel_id != slug_candidate
            # Table ID may coincide with ch_+underscore_slug; reject a different
            # naive transform (spaces stripped, no underscore) instead.
            assert channel_id != f"ch_{slot.lower().replace(' ', '')}"


def test_channel_id_lookup_fails_closed_for_unknown_slot():
    module = _pattern_core_or_fail()
    lookup = _require_symbol(module, "channel_id_for_live_kit_slot")

    with pytest.raises((ValueError, KeyError)):
        lookup("Drums", "Snare")
    with pytest.raises((ValueError, KeyError)):
        lookup("Unknown Group", "Kick")
    with pytest.raises((ValueError, KeyError)):
        lookup("Kick + Bass", "kick")  # case-sensitive display keys


def test_channel_references_sample_path_without_owning_audio():
    module = _pattern_core_or_fail()
    Channel = _require_symbol(module, "Channel")

    with_path = Channel(
        channel_id="ch_kick",
        live_kit_group="Kick + Bass",
        live_kit_slot="Kick",
        sample_path="synthetic/kick_01.wav",
    )
    empty = Channel(
        channel_id="ch_kick",
        live_kit_group="Kick + Bass",
        live_kit_slot="Kick",
        sample_path=None,
    )

    assert with_path.sample_path == "synthetic/kick_01.wav"
    assert empty.sample_path is None

    # TEST_GATE_DEFECT_REPAIR: use public dataclasses.fields() — iterating
    # ``__dataclass_fields__`` yields names (str), not Field objects.
    field_names = {f.name for f in fields(Channel)}
    # Minimal contract: no PCM / audio payload ownership on Channel.
    forbidden_audio_fields = {
        "pcm",
        "audio",
        "samples",
        "buffer",
        "waveform",
        "frames",
        "audio_bytes",
    }
    assert forbidden_audio_fields.isdisjoint({name.lower() for name in field_names})


def test_channel_rejects_mismatched_channel_id_and_live_kit_slot():
    module = _pattern_core_or_fail()
    Channel = _require_symbol(module, "Channel")

    with pytest.raises((ValueError, TypeError)):
        Channel(
            channel_id="ch_kick",
            live_kit_group="Drums",
            live_kit_slot="Open Hat",
            sample_path=None,
        )


def test_trigger_uses_exact_fractional_quarter_note_position():
    module = _pattern_core_or_fail()
    Trigger = _require_symbol(module, "Trigger")

    position = Fraction(3, 2)
    trigger = Trigger(channel_id="ch_closed_hat", position=position)

    assert trigger.position == Fraction(3, 2)
    assert isinstance(trigger.position, Fraction)
    assert type(trigger.position) is Fraction
    assert trigger.position.numerator == 3
    assert trigger.position.denominator == 2


def test_trigger_rejects_negative_position():
    module = _pattern_core_or_fail()
    Trigger = _require_symbol(module, "Trigger")

    with pytest.raises((ValueError, TypeError)):
        Trigger(channel_id="ch_kick", position=Fraction(-1, 4))


def test_trigger_accepts_opaque_non_live_kit_channel_id():
    """#681: Trigger identity is opaque; membership is rack-context validated."""
    module = _pattern_core_or_fail()
    Trigger = _require_symbol(module, "Trigger")

    trigger = Trigger(channel_id="ch_user_1", position=Fraction(0, 1))
    assert trigger.channel_id == "ch_user_1"


def test_trigger_rejects_empty_channel_id():
    module = _pattern_core_or_fail()
    Trigger = _require_symbol(module, "Trigger")

    with pytest.raises((ValueError, TypeError)):
        Trigger(channel_id="", position=Fraction(0, 1))


def test_pattern_requires_positive_length():
    module = _pattern_core_or_fail()
    Pattern = _require_symbol(module, "Pattern")

    with pytest.raises((ValueError, TypeError)):
        Pattern(pattern_id="pat_a", length_quarter_notes=Fraction(0, 1), triggers=())
    with pytest.raises((ValueError, TypeError)):
        Pattern(pattern_id="pat_a", length_quarter_notes=Fraction(-4, 1), triggers=())


def test_pattern_rejects_trigger_at_or_after_exclusive_end():
    module = _pattern_core_or_fail()
    Pattern = _require_symbol(module, "Pattern")
    Trigger = _require_symbol(module, "Trigger")

    length = Fraction(4, 1)
    at_end = Trigger(channel_id="ch_kick", position=length)
    beyond = Trigger(channel_id="ch_kick", position=length + Fraction(1, 4))

    with pytest.raises((ValueError, TypeError)):
        Pattern(pattern_id="pat_a", length_quarter_notes=length, triggers=[at_end])
    with pytest.raises((ValueError, TypeError)):
        Pattern(pattern_id="pat_a", length_quarter_notes=length, triggers=[beyond])


def test_pattern_accepts_trigger_immediately_before_end():
    module = _pattern_core_or_fail()
    Pattern = _require_symbol(module, "Pattern")
    Trigger = _require_symbol(module, "Trigger")

    length = Fraction(4, 1)
    just_before = Trigger(channel_id="ch_kick", position=length - Fraction(1, 16))
    pattern = Pattern(
        pattern_id="pat_a",
        length_quarter_notes=length,
        triggers=[just_before],
    )

    assert len(pattern.triggers) == 1
    assert pattern.triggers[0].position == Fraction(63, 16)
    assert pattern.triggers[0].position < pattern.length_quarter_notes


def test_pattern_normalizes_triggers_into_deterministic_musical_order():
    module = _pattern_core_or_fail()
    Pattern = _require_symbol(module, "Pattern")
    Trigger = _require_symbol(module, "Trigger")

    # Scrambled input order; same-position pair must still order deterministically.
    t_late = Trigger(channel_id="ch_kick", position=Fraction(2, 1))
    t_early = Trigger(channel_id="ch_bass", position=Fraction(1, 4))
    t_same_b = Trigger(channel_id="ch_pad", position=Fraction(1, 1))
    t_same_a = Trigger(channel_id="ch_lead", position=Fraction(1, 1))

    pattern = Pattern(
        pattern_id="pat_order",
        length_quarter_notes=Fraction(8, 1),
        triggers=[t_late, t_same_b, t_early, t_same_a],
    )

    ordered = list(pattern.triggers)
    assert [t.position for t in ordered] == [
        Fraction(1, 4),
        Fraction(1, 1),
        Fraction(1, 1),
        Fraction(2, 1),
    ]
    # Primary key: position. Secondary key: channel_id ascending (stable tie-break).
    same_pos = [t for t in ordered if t.position == Fraction(1, 1)]
    assert [t.channel_id for t in same_pos] == ["ch_lead", "ch_pad"]


def test_pattern_core_reuses_session_grid_musical_units():
    module = _pattern_core_or_fail()
    Pattern = _require_symbol(module, "Pattern")
    Trigger = _require_symbol(module, "Trigger")

    tempo_map = TempoMap(sample_rate=48_000, bpm=120)
    positions = [Fraction(0, 1), Fraction(1, 1), Fraction(5, 2), Fraction(15, 4)]
    triggers = [
        Trigger(channel_id="ch_kick", position=pos) for pos in positions
    ]
    pattern = Pattern(
        pattern_id="pat_tempo",
        length_quarter_notes=Fraction(16, 1),
        triggers=triggers,
    )

    for trigger in pattern.triggers:
        frame = tempo_map.quarter_note_to_frame(trigger.position)
        round_trip = tempo_map.frame_to_quarter_note(frame)
        # Exact on integer-frame grid points for these quarters at 120 BPM / 48k.
        assert round_trip == trigger.position
        assert isinstance(trigger.position, Fraction)

    # Pattern Core must not introduce an independent ms/tick authority on Trigger.
    assert not hasattr(trigger, "start_ms")
    assert not hasattr(trigger, "tick")
    assert not hasattr(trigger, "ppq")


def test_pattern_core_slice_contains_no_sequencer_or_screen2_surface():
    module = _pattern_core_or_fail()
    source_path = Path(inspect.getsourcefile(module) or "")
    assert source_path.is_file(), "src.pattern_core must resolve to a source file"
    source = source_path.read_text(encoding="utf-8")

    for token in FORBIDDEN_PATTERN_CORE_SURFACE_TOKENS:
        assert token not in source, f"forbidden Pattern Core surface token: {token}"

    tree = ast.parse(source)
    defined_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    for forbidden in (
        "schedule_voice_start",
        "NativeAudioEngine",
        "ChannelRack",
        "Screen2View",
    ):
        assert forbidden not in defined_names

    # Public seam remains the frozen minimal set — no sequencer orchestration API.
    public_names = {name for name in dir(module) if not name.startswith("_")}
    for forbidden in (
        "schedule_voice_start",
        "NativeAudioEngine",
        "play_pattern",
        "run_sequencer",
    ):
        assert forbidden not in public_names


def test_trigger_rejects_bool_as_musical_position():
    """Bool is a subclass of int in Python; Fraction authority must fail closed."""
    module = _pattern_core_or_fail()
    Trigger = _require_symbol(module, "Trigger")

    with pytest.raises((TypeError, ValueError)):
        Trigger(channel_id="ch_kick", position=True)  # type: ignore[arg-type]


def test_pattern_requires_non_empty_pattern_id():
    module = _pattern_core_or_fail()
    Pattern = _require_symbol(module, "Pattern")

    with pytest.raises((ValueError, TypeError)):
        Pattern(pattern_id="", length_quarter_notes=Fraction(4, 1), triggers=())
