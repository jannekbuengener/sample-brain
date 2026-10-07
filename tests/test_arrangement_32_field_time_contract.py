"""Contract-slice validation for #1083 32-field / 8-bar time freeze.

Canonical authority:
- docs/ARRANGEMENT_32_FIELD_TIME_CONTRACT.md
- docs/arrangement_32_field_time_v1.json

These tests pin only the normative contract plane. They must not implement
Pattern/Channel Rack runtime, migration execution, loop playback, or a second
persistence store. Runtime vectors remain #1086.
"""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import pytest

from src.session_grid import TempoMap

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_MD = REPO_ROOT / "docs" / "ARRANGEMENT_32_FIELD_TIME_CONTRACT.md"
CONTRACT_JSON = REPO_ROOT / "docs" / "arrangement_32_field_time_v1.json"

REPRESENTATIVE_FIELDS = (0, 3, 4, 7, 8, 15, 16, 31)
BAR_START_FIELDS = (0, 4, 8, 12, 16, 20, 24, 28)

FORBIDDEN_MIGRATION_TOKENS = (
    "index_times_two",
    "index_times_any_factor",
    "blind_trigger_copy_as_32_fields",
    "spread_16_steps_across_32_fields",
    "replicate_pattern_eight_times",
    "silent_fractional_trigger_rounding",
    "silent_reinterpret_canonical_default_on_as_32_field_grid",
)

REQUIRED_FAIL_CLOSED_IDS = (
    "field_index_negative",
    "field_index_ge_32",
    "malformed_field_type",
    "trigger_at_or_outside_cycle_end_in_one_cycle_truth",
    "invalid_pattern_length",
    "unknown_or_malformed_legacy_step_count",
    "legacy_trigger_outside_old_pattern_bounds",
    "ambiguous_legacy_mapping",
    "corrupt_persistence_payload",
    "user_added_unknown_legacy_state",
    "sixty_four_field_state",
)


@pytest.fixture(scope="module")
def contract() -> dict:
    data = json.loads(CONTRACT_JSON.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


@pytest.fixture(scope="module")
def markdown() -> str:
    return CONTRACT_MD.read_text(encoding="utf-8")


def test_contract_files_exist() -> None:
    assert CONTRACT_MD.is_file()
    assert CONTRACT_JSON.is_file()


def test_json_is_normative_contract_plane_not_runtime(contract: dict) -> None:
    assert contract["document_type"] == "sample_brain.arrangement_32_field_time_contract"
    assert contract["plane"] == "normative_contract_schema"
    assert contract["not_runtime_serialization"] is True
    assert contract["runtime_implementation_owner_issue"] == 1086
    assert contract["issue"] == 1083
    assert contract["exit_marker"] == "ARRANGEMENT_32_FIELD_TIME_CONTRACT_FROZEN"
    assert contract["consumes_persistence_owner_issue"] == 1082
    assert contract["arrangement_model_consumer_issue"] == 1084


def test_markdown_exit_marker_and_plane(markdown: str) -> None:
    assert "ARRANGEMENT_32_FIELD_TIME_CONTRACT_FROZEN" in markdown
    assert "not_runtime_serialization" in markdown or "not** runtime serialization" in markdown.lower() or "is **not** runtime serialization" in markdown
    assert "#1086" in markdown
    assert "TempoMap" in markdown


def test_time_signature_4_4(contract: dict, markdown: str) -> None:
    ts = contract["time_signature"]
    assert ts["numerator"] == 4
    assert ts["denominator"] == 4
    assert ts["quarter_notes_per_bar"] == 4
    assert "4/4" in markdown


def test_fields_bars_totals(contract: dict) -> None:
    assert contract["fields_per_bar"] == 4
    assert contract["bars_per_cycle"] == 8
    assert contract["total_fields"] == 32
    assert contract["quarter_notes_per_field"] == 1
    assert contract["cycle_length_quarter_notes"] == 32
    assert contract["sixty_four_fields_in_v1"] is False
    assert (
        contract["fields_per_bar"] * contract["bars_per_cycle"]
        == contract["total_fields"]
    )
    assert (
        contract["quarter_notes_per_field"] * contract["total_fields"]
        == contract["cycle_length_quarter_notes"]
    )


def test_field_mapping_0_through_31(contract: dict) -> None:
    mapping = contract["field_mapping"]
    assert mapping["rule"] == "field_i_equals_quarter_note_position_i"
    assert mapping["index_range_inclusive"] == [0, 31]
    positions = mapping["positions_quarter_notes"]
    assert len(positions) == 32
    for i in range(32):
        assert positions[str(i)] == str(i)


def test_representative_field_boundaries(contract: dict) -> None:
    bounds = contract["representative_boundaries"]
    for field in REPRESENTATIVE_FIELDS:
        key = f"field_{field}"
        assert bounds[key]["quarter_note"] == str(field)
        assert bounds[key]["bar_index_zero_based"] == field // 4
        assert bounds[key]["field_in_bar"] == field % 4
    assert bounds["field_31"]["inside_cycle"] is True
    cycle = bounds["cycle_boundary_bar9_start"]
    assert cycle["quarter_note"] == "32"
    assert cycle["belongs_to_next_cycle"] is True
    assert cycle["not_a_field_in_cycle"] is True


def test_four_field_bar_boundaries(contract: dict) -> None:
    bars = contract["bar_boundaries"]
    assert bars["fields_per_bar"] == 4
    assert bars["bar_starts_field_indexes"] == list(BAR_START_FIELDS)
    assert bars["bar_starts_quarter_notes"] == [str(i) for i in BAR_START_FIELDS]


def test_cycle_boundary_qn_32_and_no_field_32(contract: dict) -> None:
    loop = contract["loop_interval_semantics"]
    assert loop["cycle_half_open_interval_quarter_notes"] == "[0, 32)"
    assert loop["boundary_quarter_note"] == "32"
    assert loop["boundary_belongs_to_next_cycle"] is True
    assert loop["field_31_is_last_in_cycle"] is True
    assert loop["no_field_index_32_inside_cycle"] is True
    assert loop["no_double_fire_at_cycle_boundary"] is True
    assert "N*32" in loop["scheduling_invariant"]
    assert loop["runtime_verification_owner_issue"] == 1086
    assert "32" not in contract["field_mapping"]["positions_quarter_notes"]


def test_arrangement_16_bar_projection_same_pattern_id(contract: dict) -> None:
    proj = contract["arrangement_repetition_projection"]
    assert proj["block_bars"] == 16
    assert proj["block_length_quarter_notes"] == 64
    assert proj["pattern_identity_count"] == 1
    assert proj["no_second_copied_pattern_state"] is True
    assert proj["no_sixty_four_field_persistence"] is True
    assert proj["no_qml_mirror_state"] is True
    assert proj["step_mutation_affects_all_projections"] is True
    assert proj["consumer_issue"] == 1084
    cycles = proj["cycles"]
    assert len(cycles) == 2
    assert cycles[0]["absolute_quarter_offset"] == "0"
    assert cycles[0]["field_n_maps_to_quarter"] == "n"
    assert cycles[1]["absolute_quarter_offset"] == "32"
    assert cycles[1]["field_n_maps_to_quarter"] == "32 + n"
    assert cycles[0]["bars_one_based"] == [1, 8]
    assert cycles[1]["bars_one_based"] == [9, 16]


def test_sixty_four_field_state_forbidden(contract: dict, markdown: str) -> None:
    assert contract["sixty_four_fields_in_v1"] is False
    assert contract["arrangement_repetition_projection"]["no_sixty_four_field_persistence"] is True
    fail_ids = {item["id"] for item in contract["fail_closed_cases"]}
    assert "sixty_four_field_state" in fail_ids
    assert "64" in markdown or "sixty_four" in markdown.lower() or "64-field" in markdown


def test_tempo_map_authority_and_forbidden_clocks(contract: dict, markdown: str) -> None:
    auth = contract["tempo_map_authority"]
    assert auth["sole_tempo_to_frame_authority"] == "TempoMap"
    assert auth["module"] == "src/session_grid.py"
    assert auth["scheduling_chain"] == [
        "field_index",
        "exact_quarter_note_position",
        "TempoMap.quarter_note_to_frame",
        "engine_frame",
    ]
    forbidden = set(auth["forbidden_authorities"])
    assert "field_to_hardcoded_milliseconds" in forbidden
    assert "BeatGrid_as_pattern_clock" in forbidden
    assert auth["beat_grid_role"] == "analysis_edit_evidence_only_not_pattern_clock"
    tempo = auth["tempo_change_policy"]
    assert tempo["stored_musical_positions_unchanged"] is True
    assert tempo["future_frame_mapping_via_TempoMap"] is True
    assert tempo["no_rewrite_mutation_of_pattern_positions"] is True
    assert "BeatGrid" in markdown
    assert "TempoMap" in markdown


def test_representative_tempomap_frames_match_live_authority(contract: dict) -> None:
    auth = contract["tempo_map_authority"]
    assert auth["canonical_workbench_sample_rate_hz"] == 48000
    for entry in auth["representative_frame_mappings"]:
        sample_rate = entry["sample_rate_hz"]
        bpm = entry["bpm"]
        tempo_map = TempoMap(sample_rate=sample_rate, bpm=bpm)
        for qn_text, expected_frame in entry["quarter_note_to_frame"].items():
            qn = Fraction(qn_text)
            assert tempo_map.quarter_note_to_frame(qn) == expected_frame


def test_legacy_migration_policy_explicit(contract: dict, markdown: str) -> None:
    legacy = contract["legacy_migration"]
    forbidden = set(legacy["forbidden_without_proof"])
    for token in FORBIDDEN_MIGRATION_TOKENS:
        assert token in forbidden
    outcomes = legacy["outcomes"]
    assert "migrated_empty" in outcomes
    assert "migrated_field_aligned" in outcomes
    assert "migration_required" in outcomes
    assert "migration_hold" in outcomes
    assert "reject_fail_closed" in outcomes
    assert legacy["canonical_default_on_v1_classification"] == "migration_required"
    evidence = legacy["canonical_default_on_v1_evidence"]
    assert evidence["field_aligned_count"] == 4
    assert evidence["off_grid_count"] == 12
    assert evidence["lossy_if_forced_to_integer_fields"] is True
    assert evidence["auto_expand_to_32_default_on_forbidden"] is True
    assert "migration_required" in markdown
    assert "migration_hold" in markdown
    assert "index × 2" in markdown or "index_times_two" in json.dumps(contract)


def test_default_on_legacy_and_new_initialization_explicit(
    contract: dict, markdown: str
) -> None:
    default_on = contract["default_on_migration"]
    historical = default_on["historical_persisted_or_in_memory_default_on_v1"]
    assert historical["classification"] == "migration_required"
    assert historical["must_not_become_32_triggers_automatically"] is True
    fresh = default_on["new_initialization_under_32_field_semantics"]
    assert fresh["inherits_legacy_16_step_default_on_policy"] is False
    assert fresh["oneshot_seed_policy"] == "empty_triggers"
    assert fresh["loops"] == "empty_triggers"
    assert fresh["ambiguous_classification"] == "empty_triggers"
    assert fresh["empty_channels"] == "empty_triggers"
    assert fresh["user_added_channels"] == "empty_triggers_until_user_sets_fields"
    assert fresh["manually_edited_all_off_patterns"] == "remain_empty_no_phantom_reseed"
    assert fresh["no_phantom_triggers"] is True
    assert "phantom" in markdown.lower()
    assert "DEFAULT_ON" in markdown


def test_unsupported_legacy_fail_closed_or_hold(contract: dict) -> None:
    fail_cases = {item["id"]: item for item in contract["fail_closed_cases"]}
    for required_id in REQUIRED_FAIL_CLOSED_IDS:
        assert required_id in fail_cases
    assert fail_cases["legacy_trigger_outside_old_pattern_bounds"]["outcome"] == (
        "migration_hold"
    )
    assert fail_cases["user_added_unknown_legacy_state"]["outcome"] == "migration_hold"
    assert fail_cases["corrupt_persistence_payload"]["outcome"] == "reject_fail_closed"
    assert fail_cases["unknown_or_malformed_legacy_step_count"]["outcome"] == (
        "reject_fail_closed"
    )
    ambiguous = fail_cases["ambiguous_legacy_mapping"]["outcome"]
    assert "migration_required" in ambiguous or "migration_hold" in ambiguous


def test_no_second_persistence_owner(contract: dict, markdown: str) -> None:
    boundary = contract["persistence_boundary"]
    assert boundary["time_truth_owner_issue"] == 1083
    assert boundary["track_package_persistence_owner_issue"] == 1082
    assert boundary["runtime_schema_implementation_owner_issue"] == 1086
    assert boundary["no_second_persistence_store"] is True
    required = set(boundary["must_persist_concepts"])
    assert "pattern_identity" in required
    assert "exact_musical_trigger_positions" in required
    assert "thirty_two_field_eight_bar_semantic_version" in required
    assert "migration_state_when_necessary" in required
    forbidden = set(boundary["must_not_persist"])
    assert "sixty_four_field_view_as_truth" in forbidden
    assert "duplicated_second_half_pattern_state" in forbidden
    assert "qml_bar_cache_as_musical_truth" in forbidden
    assert "second store" in markdown.lower() or "second persistence" in markdown.lower()


def test_cross_contract_ownership_1084_and_1086(contract: dict, markdown: str) -> None:
    cross = contract["cross_contract_boundaries"]
    assert "1084" in cross
    assert "1086" in cross
    assert "1082" in cross
    assert "Consumes" in cross["1084"] or "consumes" in cross["1084"].lower()
    assert "runtime" in cross["1086"].lower()
    assert contract["arrangement_model_consumer_issue"] == 1084
    assert contract["runtime_implementation_owner_issue"] == 1086
    assert "#1084" in markdown
    assert "#1086" in markdown


def test_live_legacy_seams_match_channel_rack_constants(contract: dict) -> None:
    from src.channel_rack import DEFAULT_PATTERN_LENGTH, DEFAULT_STEP_COUNT

    rack = contract["live_legacy_seams"]["channel_rack_v1"]
    assert rack["DEFAULT_STEP_COUNT"] == DEFAULT_STEP_COUNT == 16
    assert rack["DEFAULT_PATTERN_LENGTH_QUARTER_NOTES"] == str(
        int(DEFAULT_PATTERN_LENGTH)
    )
    assert rack["must_not_silently_reinterpret_as_32_field"] is True
    assert DEFAULT_PATTERN_LENGTH == Fraction(4, 1)


def test_required_later_runtime_vectors_owned_by_1086(contract: dict) -> None:
    vectors = contract["required_later_runtime_vectors"]
    assert len(vectors) >= 10
    assert all(item["owner_issue"] == 1086 for item in vectors)
    names = {item["name"] for item in vectors}
    assert "no_double_fire_at_8_bar_loop_wrap" in names
    assert "legacy_16_step_fixture_follows_frozen_migration_outcome" in names


def test_hard_out_of_scope_excludes_runtime_modules(contract: dict, markdown: str) -> None:
    out = set(contract["hard_out_of_scope"])
    for token in (
        "runtime_pattern_core_changes",
        "runtime_channel_rack_changes",
        "runtime_session_grid_changes",
        "runtime_sequencer_playback_changes",
        "runtime_workbench_session_store_changes",
        "qml",
        "arrangement_masks_groups_markers",
        "sixty_four_field_sequencer",
    ):
        assert token in out
    assert "pattern_core.py" in markdown
    assert "channel_rack.py" in markdown


def test_field_math_helpers_agree_with_contract(contract: dict) -> None:
    """Pure math mirror of the freeze — not a runtime implementation."""

    total = contract["total_fields"]
    qn_per_field = contract["quarter_notes_per_field"]
    fields_per_bar = contract["fields_per_bar"]
    cycle_qn = contract["cycle_length_quarter_notes"]

    for field in range(total):
        qn = field * qn_per_field
        assert qn == field
        assert 0 <= qn < cycle_qn
        assert field // fields_per_bar == int(Fraction(qn, 4))
    assert total * qn_per_field == cycle_qn
    # second Arrangement half offset
    for field in range(total):
        assert field + cycle_qn == 32 + field
