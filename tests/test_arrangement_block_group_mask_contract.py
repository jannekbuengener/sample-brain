"""Contract-slice validation for #1084 Arrangement block/group/mask freeze.

Canonical authority:
- docs/ARRANGEMENT_BLOCK_GROUP_MASK_CONTRACT.md
- docs/arrangement_block_group_mask_v1.json

These tests pin only the normative contract plane. They must not implement
Arrangement runtime, QML, render export, or a second persistence store.
Runtime vectors remain #1087.
"""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import pytest

from src.pattern_core import CHANNEL_ID_BY_LIVE_KIT_SLOT, USER_CHANNEL_ID_PREFIX
from src.session_grid import TempoMap

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_MD = REPO_ROOT / "docs" / "ARRANGEMENT_BLOCK_GROUP_MASK_CONTRACT.md"
CONTRACT_JSON = REPO_ROOT / "docs" / "arrangement_block_group_mask_v1.json"

STABLE_GROUP_IDS = (
    "pg_baseline",
    "pg_drums",
    "pg_melodic_atmos_fx",
    "pg_vocals",
)

CANONICAL_MAPPING = {
    "pg_baseline": ["ch_kick", "ch_bass"],
    "pg_drums": [
        "ch_main_drum",
        "ch_closed_hat",
        "ch_open_hat",
        "ch_percussion",
        "ch_additional",
    ],
    "pg_melodic_atmos_fx": ["ch_lead", "ch_pad", "ch_atmos", "ch_fx"],
    "pg_vocals": [],
}

REQUIRED_FAIL_CLOSED_IDS = (
    "invalid_block_index",
    "unknown_group_id",
    "unknown_channel_id_for_mask_ops",
    "unknown_pattern_id",
    "corrupt_mask_payload",
    "unmapped_membership_dependent_op",
    "marker_not_bar_snapped",
    "marker_mapped_gt_600s",
    "missing_end_marker",
    "zero_duration_marker",
    "unresolved_musical_membership",
    "block_out_of_current_horizon",
)

REQUIRED_RUNTIME_VECTOR_NAMES = (
    "first_block_defaults_on_without_persisted_entry",
    "later_block_defaults_on",
    "group_off_persists_restore",
    "track_off_persists_restore",
    "group_off_then_on_preserves_track_off",
    "expand_collapse_changes_no_musical_state",
    "invalid_block_index_mutates_nothing",
    "invalid_group_id_mutates_nothing",
    "invalid_channel_id_mutates_nothing",
    "canonical_legacy_grouping_migrates_by_channel_id",
    "no_vocals_old_state_restores_valid",
    "unknown_user_channel_not_lost_or_remapped",
    "legal_marker_round_trip",
    "marker_after_tempo_change_keeps_qn",
    "marker_mapped_gt_600s_becomes_ineligible",
    "absent_marker_prevents_complete_render",
    "corrupt_masks_fail_closed",
    "identical_state_serializes_deterministically",
    "unmapped_populated_channel_effective_unresolved",
    "unmapped_populated_blocks_complete_render",
    "missing_marker_block_index_still_structurally_valid",
    "horizon_from_block_start_via_tempo_map",
    "tempo_change_out_of_horizon_keeps_masks",
)

RENDER_ELIGIBILITY_REQUIREMENTS = (
    "end_marker_present",
    "marker_structurally_valid",
    "marker_bar_snapped",
    "song_duration_gt_0",
    "tempo_map_duration_lte_600s",
    "arrangement_contract_state_valid",
    "no_unresolved_musically_relevant_presentation_membership",
    "no_other_fail_closed_mask_or_identity_inconsistency",
)


def _seconds_for_quarter(tempo_map: TempoMap, quarter_note: Fraction) -> float:
    frame = tempo_map.quarter_note_to_frame(quarter_note)
    return frame / float(tempo_map.sample_rate)


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
    assert contract["document_type"] == "sample_brain.arrangement_block_group_mask_contract"
    assert contract["plane"] == "normative_contract_schema"
    assert contract["not_runtime_serialization"] is True
    assert contract["runtime_implementation_owner_issue"] == 1087
    assert contract["qml_projection_owner_issue"] == 1080
    assert contract["issue"] == 1084
    assert contract["consumes_time_contract_issue"] == 1083
    assert contract["consumes_persistence_owner_issue"] == 1082
    assert contract["exit_marker"] == "ARRANGEMENT_BLOCK_GROUP_MASK_CONTRACT_FROZEN"


def test_markdown_exit_marker_and_owners(markdown: str) -> None:
    assert "ARRANGEMENT_BLOCK_GROUP_MASK_CONTRACT_FROZEN" in markdown
    assert "not_runtime_serialization" in markdown
    assert "#1087" in markdown
    assert "#1080" in markdown
    assert "#1083" in markdown
    assert "#1082" in markdown


# --- 1-2: block = 16 bars / 64 qn ---


def test_block_is_16_bars_and_64_qn(contract: dict, markdown: str) -> None:
    block = contract["block_model"]
    assert block["block_bars"] == 16
    assert block["block_length_quarter_notes"] == 64
    assert "16 bars" in markdown
    assert "64" in markdown


# --- 3-4: two references to one Pattern; no copied second Pattern ---


def test_two_projections_one_pattern_no_copy(contract: dict) -> None:
    block = contract["block_model"]
    assert block["pattern_identity_count_per_initial_block"] == 1
    assert block["no_copied_second_pattern_state"] is True
    assert block["no_sixty_four_field_pattern_state"] is True
    projections = block["pattern_projections_per_block"]
    assert len(projections) == 2
    assert projections[0]["absolute_quarter_offset"] == "0"
    assert projections[1]["absolute_quarter_offset"] == "32"


def test_consumes_1083_not_redefines(contract: dict) -> None:
    consumed = contract["consumed_time_contract"]
    assert consumed["issue"] == 1083
    assert consumed["no_second_time_authority"] is True
    assert consumed["pattern_fields"] == 32
    assert consumed["pattern_bars"] == 8
    assert "1083" in contract["cross_contract_boundaries"]
    assert any("1083" in item for item in contract["hard_out_of_scope"])


# --- 5: deterministic block index ---


def test_deterministic_block_index(contract: dict) -> None:
    identity = contract["block_identity"]
    assert identity["kind"] == "zero_based_deterministic_block_index"
    assert identity["field_name"] == "block_index"
    assert identity["minimum"] == 0
    assert identity["no_random_block_uuids_in_v1"] is True
    assert identity["not_display_name_based"] is True
    assert identity["viewport_zoom_does_not_create_or_delete_blocks"] is True


# --- 6: default-on without infinite materialization ---


def test_default_on_sparse_no_infinite_materialization(contract: dict) -> None:
    sparse = contract["default_on_sparse_model"]
    assert sparse["default_block_enabled"] is True
    assert sparse["default_group_enabled"] is True
    assert sparse["default_track_enabled"] is True
    assert sparse["persist_only_explicit_exceptions"] is True
    assert sparse["no_infinite_enabled_true_list"] is True
    assert set(sparse["persisted_exception_collections"]) == {
        "disabled_blocks",
        "disabled_group_blocks",
        "disabled_track_blocks",
    }
    assert sparse["unmapped_membership_is_not_a_mask_entry"] is True
    assert contract["block_identity"]["no_infinite_materialization"] is True


# --- 7-8: four stable groups; labels != IDs ---


def test_four_stable_presentation_groups(contract: dict) -> None:
    groups = contract["presentation_groups"]
    assert groups["count"] == 4
    ids = [g["group_id"] for g in groups["groups"]]
    labels = [g["display_label"] for g in groups["groups"]]
    assert ids == list(STABLE_GROUP_IDS)
    assert labels == ["Baseline", "Drums", "Melodic / Atmos / FX", "Vocals"]
    assert groups["ids_not_slugified_from_display_labels"] is True
    assert groups["display_labels_are_projection_metadata_only"] is True
    assert "pg_baseline" != "Baseline"
    assert groups["no_fifth_visible_product_group_in_v1"] is True


# --- 9-11: canonical mapping, empty vocals, no invented vocals ---


def test_canonical_channel_to_group_mapping(contract: dict) -> None:
    mapping = contract["canonical_channel_to_group_mapping"]["mapping"]
    assert mapping == CANONICAL_MAPPING
    live_ids = set(CHANNEL_ID_BY_LIVE_KIT_SLOT.values())
    contracted = {cid for ids in mapping.values() for cid in ids}
    assert contracted == live_ids
    assert mapping["pg_vocals"] == []
    assert contract["canonical_channel_to_group_mapping"]["empty_vocals_valid"] is True
    assert contract["canonical_channel_to_group_mapping"]["no_invented_vocal_channels"] is True


# --- 12, 27-30: unknown/user channel + unmapped policy ---


def test_unknown_user_channel_preserved_unmapped(contract: dict) -> None:
    policy = contract["unknown_user_channel_policy"]
    assert policy["presentation_membership"] == "unmapped"
    assert policy["membership_resolution"] == "migration_required"
    assert policy["arrangement_membership_resolved"] is False
    assert policy["preserve_channel_id"] is True
    assert policy["preserve_assignment"] is True
    assert policy["preserve_trigger_pattern_state"] is True
    assert policy["no_heuristic_grouping_from"] == [
        "filename",
        "display_label",
        "folder_name",
        "sample_class",
    ]
    assert contract["canonical_channel_to_group_mapping"]["user_channel_id_prefix"] == (
        USER_CHANNEL_ID_PREFIX
    )


def test_unmapped_does_not_silently_receive_group(contract: dict, markdown: str) -> None:
    policy = contract["unknown_user_channel_policy"]
    assert policy["unmapped_is_not_silent_playback_fallback"] is True
    assert set(policy["must_not_silently_assign_to"]) == set(STABLE_GROUP_IDS)
    assert policy["must_not_invent_group_enabled_true_as_surrogate"] is True
    assert policy["must_not_silent_mute_as_successful_migration"] is True
    assert "unmapped" in markdown
    assert "silent" in markdown.lower() or "not silently" in markdown.lower()


def test_unmapped_survives_migration_unchanged_contract(contract: dict) -> None:
    policy = contract["unknown_user_channel_policy"]
    assert policy["preserve_track_owned_musical_state"] is True
    assert policy["separate_from_mask_state"] is True
    mig = contract["migration_reconciliation"]
    assert mig["unknown_channels_not_guessed"] is True
    assert mig["unknown_legacy_labels_do_not_lose_assignment"] is True


def test_unmapped_makes_membership_dependent_state_unresolved(contract: dict) -> None:
    policy = contract["unknown_user_channel_policy"]
    assert policy["arrangement_membership_resolved"] is False
    assert policy["membership_dependent_operations_fail_closed_until_resolved"] is True
    eff = contract["effective_playback"]
    assert eff["unmapped_effective"] == "unresolved"
    assert eff["unmapped_must_not_pretend_true_or_false"] is True
    assert eff["resolved_channels_only"] is True


def test_unresolved_membership_prevents_complete_render(contract: dict) -> None:
    render = contract["render_eligibility"]
    assert render["unmapped_populated_channel_blocks_complete_render"] is True
    assert (
        "no_unresolved_musically_relevant_presentation_membership"
        in render["render_eligible_true_requires_all_of"]
    )
    fail_ids = {item["id"] for item in contract["fail_closed_outcomes"]}
    assert "unresolved_musical_membership" in fail_ids


# --- 13-15: masks separate, AND precedence, group OFF→ON preserves track ---


def test_group_and_track_masks_separate_with_and_precedence(contract: dict) -> None:
    eff = contract["effective_playback"]
    formula = eff["resolved_formula"]
    assert "block_enabled" in formula
    assert "group_enabled" in formula
    assert "track_enabled" in formula
    assert "AND" in formula
    assert eff["group_toggle_does_not_mutate_track_mask"] is True
    assert eff["track_toggle_does_not_mutate_group_mask"] is True
    assert eff["group_off_then_on_preserves_disabled_tracks"] is True


# --- 16: expand/collapse no musical mutation ---


def test_expand_collapse_zero_musical_mutation(contract: dict) -> None:
    expand = contract["expand_collapse"]
    assert expand["presentation_only"] is True
    assert expand["zero_musical_mutation"] is True
    assert expand["not_musical_domain_truth"] is True
    for key in (
        "group_mask",
        "track_mask",
        "pattern",
        "arrangement",
        "playback_truth",
    ):
        assert key in expand["does_not_change"]


# --- 17: bounded sparse serialization ---


def test_bounded_sparse_serialization(contract: dict) -> None:
    sparse = contract["default_on_sparse_model"]
    assert sparse["deterministic_serialization"] is True
    assert sparse["stable_sort_order_required"] is True
    assert sparse["viewport_open_close_zoom_does_not_mutate_musical_state"] is True


# --- 18: marker bar snap ---


def test_end_marker_bar_snap_qn_multiple_of_4(contract: dict) -> None:
    marker = contract["end_marker"]
    assert marker["snap_rule"] == "end_marker_qn % 4 == 0"
    assert marker["representation"] == "musical_quarter_note_position"
    assert marker["not_milliseconds"] is True
    assert marker["not_pixel_position"] is True
    assert contract["consumed_time_contract"]["quarter_notes_per_bar"] == 4


# --- 19: marker musical position survives tempo change ---


def test_marker_qn_survives_tempo_change(contract: dict) -> None:
    tempo = contract["end_marker"]["tempo_change"]
    assert tempo["end_marker_qn_unchanged"] is True
    assert tempo["wall_clock_via_tempo_map"] is True
    assert tempo["no_auto_musical_move"] is True
    assert tempo["no_silent_clamp"] is True


# --- 20: >600s render-ineligible, no auto move ---


def test_marker_over_cap_ineligible_no_auto_move(contract: dict) -> None:
    over = contract["end_marker"]["tempo_change"]["when_mapped_duration_gt_600s"]
    assert over["persist_qn_unchanged"] is True
    assert over["marker_status"] == "invalid/out_of_range"
    assert over["render_eligible"] is False
    assert contract["ten_minute_cap"]["hard_cap_seconds"] == 600
    assert contract["ten_minute_cap"]["evaluation_authority"] == "TempoMap"
    assert contract["ten_minute_cap"]["not_ui_based"] is True


# --- 21-22: missing / zero-duration marker ---


def test_missing_and_zero_duration_marker_render_ineligible(contract: dict) -> None:
    render = contract["render_eligibility"]
    assert render["missing_marker_render_eligible"] is False
    assert "song_duration_gt_0" in render["render_eligible_true_requires_all_of"]
    assert contract["end_marker"]["zero_duration_not_successful_complete_render"] is True
    fail_ids = {item["id"] for item in contract["fail_closed_outcomes"]}
    assert "missing_end_marker" in fail_ids
    assert "zero_duration_marker" in fail_ids


# --- 23: invalid IDs fail closed ---


def test_invalid_ids_fail_closed(contract: dict) -> None:
    fail_ids = {item["id"] for item in contract["fail_closed_outcomes"]}
    for required in REQUIRED_FAIL_CLOSED_IDS:
        assert required in fail_ids
    assert contract["block_identity"]["invalid_negative_or_non_integer_fail_closed"] is True


# --- 24: no #1083/#1082 ownership duplication ---


def test_no_time_or_persistence_authority_duplication(contract: dict, markdown: str) -> None:
    assert contract["consumes_time_contract_issue"] == 1083
    assert contract["consumes_persistence_owner_issue"] == 1082
    assert contract["persistence_ownership"]["no_second_store"] is True
    assert contract["persistence_ownership"]["track_package_opaque_key"] == "arrangement"
    assert set(contract["persistence_ownership"]["store_owner_issues"]) == {1082, 1085}
    assert "second" in markdown.lower() or "No second store" in markdown
    boundaries = contract["cross_contract_boundaries"]
    assert "1083" in boundaries
    assert "1082" in boundaries


# --- 25-26: named runtime / QML owners ---


def test_named_runtime_and_qml_owners(contract: dict, markdown: str) -> None:
    assert contract["runtime_implementation_owner_issue"] == 1087
    assert contract["qml_projection_owner_issue"] == 1080
    assert contract["cross_contract_boundaries"]["1087"]
    assert contract["cross_contract_boundaries"]["1080"]
    assert "#1087" in markdown
    assert "#1080" in markdown


# --- 31-32: structural block validity independent of marker ---


def test_structural_block_validity_independent_of_marker(contract: dict, markdown: str) -> None:
    structural = contract["block_structural_validity"]
    assert structural["independent_of_end_marker_presence"] is True
    assert structural["missing_end_marker_does_not_invalidate_block_index"] is True
    assert "exact_integer" in structural["valid_when"]
    assert "not_bool" in structural["valid_when"]
    assert "greater_than_or_equal_to_0" in structural["valid_when"]
    assert "structurally valid" in markdown.lower() or "Structural validity" in markdown


# --- 33-34: horizon from block_start; overlapping final block allowed ---


def test_horizon_eligibility_from_block_start_via_tempo_map(contract: dict) -> None:
    horizon = contract["block_horizon_eligibility"]
    assert horizon["hard_cap_seconds"] == 600
    assert horizon["authority"] == "TempoMap"
    assert horizon["rule"] == "TempoMap(block_start_qn) < 600 seconds"
    assert horizon["block_start_qn"] == "block_index * 64"
    assert horizon["final_block_may_overlap_cap"] is True
    assert horizon["full_block_end_need_not_be_within_600s"] is True
    assert horizon["not_ui_viewport"] is True

    # Evidence mirror: at 120 BPM, block whose start is just under 600s is eligible
    # even when block end exceeds 600s.
    tempo_map = TempoMap(sample_rate=48000, bpm=120)
    # 120 BPM => 2 qn/sec => 600s => 1200 qn. Last start < 1200 with step 64:
    # block_index = 18 => start 1152 qn => 576s < 600; end 1216 qn => 608s > 600.
    block_index = 18
    start_qn = Fraction(block_index * 64, 1)
    end_qn = Fraction((block_index + 1) * 64, 1)
    start_s = _seconds_for_quarter(tempo_map, start_qn)
    end_s = _seconds_for_quarter(tempo_map, end_qn)
    assert start_s < 600
    assert end_s > 600


def test_overlapping_final_block_allowed_when_start_under_cap(contract: dict) -> None:
    assert contract["block_horizon_eligibility"]["final_block_may_overlap_cap"] is True
    assert (
        contract["block_horizon_eligibility"]["full_block_end_need_not_be_within_600s"]
        is True
    )


# --- 35-36: tempo change out_of_horizon keeps masks; never rewrites indices ---


def test_tempo_change_out_of_horizon_keeps_masks_no_rewrite(contract: dict) -> None:
    after = contract["persisted_state_after_tempo_change"]
    assert after["masks_and_overrides_not_deleted"] is True
    assert after["not_auto_moved"] is True
    assert after["not_clamped"] is True
    assert after["block_indices_not_rewritten"] is True
    assert after["eligibility_status_when_start_maps_ge_600s"] == "out_of_current_horizon"
    assert after["musical_intent_stable"] is True


# --- render eligibility completeness ---


def test_render_eligibility_predicate_complete(contract: dict) -> None:
    render = contract["render_eligibility"]
    assert render["predicate_only_no_render_format"] is True
    assert set(render["render_eligible_true_requires_all_of"]) == set(
        RENDER_ELIGIBILITY_REQUIREMENTS
    )


# --- migration ---


def test_migration_by_channel_id_non_destructive(contract: dict) -> None:
    mig = contract["migration_reconciliation"]
    assert mig["by_stable_channel_id"] is True
    assert mig["not_by_visible_group_name"] is True
    assert mig["no_destructive_rename_migration"] is True
    assert mig["legacy_kick_bass_to_pg_baseline"] is True
    assert mig["legacy_drums_ids_to_pg_drums"] is True
    assert mig["legacy_lead_pad_atmos_fx_to_pg_melodic_atmos_fx"] is True
    assert mig["legacy_without_vocals_remains_valid"] is True
    assert mig["empty_vocals_valid"] is True


# --- #1087 vectors present ---


def test_required_1087_runtime_vectors_named(contract: dict) -> None:
    vectors = contract["required_runtime_validation_vectors_1087"]
    names = [v["name"] for v in vectors]
    for required in REQUIRED_RUNTIME_VECTOR_NAMES:
        assert required in names
    assert len(vectors) >= 18


def test_hard_out_of_scope_pins_runtime_and_qml(contract: dict) -> None:
    out = set(contract["hard_out_of_scope"])
    assert "src_runtime_implementation" in out
    assert "qml_projection_1080" in out
    assert "final_vocals_slot_distribution" in out
    assert "midi" in out
    assert "live" in out


def test_markdown_and_json_share_exit_and_core_terms(markdown: str, contract: dict) -> None:
    assert contract["exit_marker"] in markdown
    assert "pg_baseline" in markdown
    assert "unresolved" in markdown
    assert "out_of_current_horizon" in markdown
    assert "disabled_blocks" in markdown
    assert "end_marker_qn" in markdown
