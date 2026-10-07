"""Contract-slice validation for #1082 track package ownership freeze.

Canonical authority:
- docs/TRACK_PACKAGE_OWNERSHIP_CONTRACT.md
- docs/track_package_ownership_v1.json

These tests pin only the normative contract plane. They must not simulate
runtime portability, implement package migration, Browser behavior, symlink
support, or track persistence. Vectors 1-15 are expected-result specifications
for later #1085 runtime acceptance tests.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_MD = REPO_ROOT / "docs" / "TRACK_PACKAGE_OWNERSHIP_CONTRACT.md"
CONTRACT_JSON = REPO_ROOT / "docs" / "track_package_ownership_v1.json"

REQUIRED_LIFECYCLE_CODES = (
    "draft",
    "package_creating",
    "ready",
    "open",
    "missing_media",
    "corrupt_or_unsupported",
    "migration_required",
    "migration_failed",
    "destination_unavailable",
    "copy_interrupted",
    "write_failed",
    "path_escape_rejected",
)

REQUIRED_CREATE_STAGES = (
    "validate_destination_package_root_eligibility",
    "validate_draft_eligibility",
    "create_sibling_staging_directory_same_filesystem",
    "copy_required_media_only",
    "validate_copied_media",
    "write_versioned_package_data",
    "validate_complete_package_integrity",
    "commit_complete_package_to_final_location",
    "bind_active_durable_track",
)

REQUIRED_GLOBAL = (
    "registered_sample_sources",
    "catalog_analysis_state",
    "browser_organization",
    "collections",
    "general_app_workspace_preferences",
    "regenerable_caches",
)

REQUIRED_TRACK = (
    "live_kit_assignment_identity_state",
    "pattern_channel_rack_musical_state",
    "track_musical_clock_resume_fields",
    "package_manifest_schema_version",
    "relative_media_references",
)

CROSS_CONTRACT_OWNERS = {
    "1083": 1083,
    "1084": 1084,
    "1078": 1078,
    "1085": 1085,
}


@pytest.fixture(scope="module")
def contract() -> dict:
    raw = CONTRACT_JSON.read_text(encoding="utf-8")
    data = json.loads(raw)
    assert isinstance(data, dict)
    return data


@pytest.fixture(scope="module")
def markdown() -> str:
    return CONTRACT_MD.read_text(encoding="utf-8")


def test_contract_files_exist() -> None:
    assert CONTRACT_MD.is_file()
    assert CONTRACT_JSON.is_file()


def test_json_is_normative_contract_plane_not_runtime(contract: dict) -> None:
    assert contract["document_type"] == "sample_brain.track_package_ownership_contract"
    assert contract["plane"] == "normative_contract_schema"
    assert contract["not_runtime_serialization"] is True
    assert contract["runtime_serialization_owner_issue"] == 1085
    assert contract["issue"] == 1082
    assert contract["exit_marker"] == "TRACK_PACKAGE_OWNERSHIP_CONTRACT_FROZEN"
    assert contract["package_kind"] == "sample_brain_track_package"
    assert "sample_brain_live_kit" in contract["distinct_from_package_kinds"]
    assert contract["future_runtime_entrypoint_filename"] == "track_package.json"


def test_markdown_exit_marker_and_plane_distinction(markdown: str) -> None:
    assert "TRACK_PACKAGE_OWNERSHIP_CONTRACT_FROZEN" in markdown
    assert "normative contract schema" in markdown.lower()
    assert "future runtime serialization" in markdown.lower()
    assert "track_package.json" in markdown
    assert "OPEN_PRODUCT_GATE" in markdown


def test_package_layout_v1(contract: dict, markdown: str) -> None:
    layout = contract["package_layout_v1"]
    assert "track_package.json" in layout["required_components"]
    assert "media/" in layout["required_components"]
    assert "track_package.json" in markdown
    assert "media/" in markdown


def test_track_id_guardrail_does_not_prescribe_uuid_hex(contract: dict, markdown: str) -> None:
    track_id = contract["track_id"]
    assert track_id["stable"] is True
    assert track_id["opaque"] is True
    assert track_id["not_derived_from_display_name"] is True
    assert track_id["not_derived_from_filesystem_path"] is True
    assert track_id["package_local_durable"] is True
    assert track_id["must_survive_serialize_restore_relocate"] is True
    assert track_id["must_not_contain_private_machine_information"] is True
    assert track_id["generation_encoding_prescribed_here"] is False
    assert track_id["uuid_hex_not_frozen"] is True
    assert track_id["generation_encoding_owner"] == 1085
    # Guard: markdown must not freeze UUID hex as the required generation strategy.
    assert not re.search(r"(?i)track_id[^\n]{0,80}\bmust\b[^\n]{0,40}uuid", markdown)
    assert "opaque" in markdown.lower()
    assert "UUID-hex track-id generator" in markdown or "uuid_hex_not_frozen" in json.dumps(
        contract
    )


def test_ownership_partitions_disjoint_and_complete(contract: dict) -> None:
    ownership = contract["ownership"]
    global_owned = set(ownership["global_system_owned"])
    track_owned = set(ownership["track_owned_after_package_commit"])
    assert ownership["partitions_must_be_disjoint"] is True
    assert ownership["no_second_musical_state_authority"] is True
    assert global_owned.isdisjoint(track_owned)
    for item in REQUIRED_GLOBAL:
        assert item in global_owned
    for item in REQUIRED_TRACK:
        assert item in track_owned


def test_reference_confinement_rules(contract: dict, markdown: str) -> None:
    rules = contract["reference_confinement"]
    assert rules["media_refs_package_relative"] is True
    assert rules["media_under_media_dir_only"] is True
    assert rules["forbid_absolute_windows_paths"] is True
    assert rules["forbid_unc_paths"] is True
    assert rules["forbid_file_uri"] is True
    assert rules["forbid_dot_dot_segments"] is True
    assert rules["forbid_root_escape"] is True
    assert rules["forbid_symlink_reparse_escape_outside_package_root"] is True
    assert rules["reject_outcome"] == "path_escape_rejected"
    assert "path_escape_rejected" in markdown


def test_create_transaction_stages(contract: dict) -> None:
    stages = contract["create_transaction_stages"]
    assert stages == list(REQUIRED_CREATE_STAGES)
    failure = contract["create_failure_before_commit"]
    assert failure["no_half_valid_visible_package"] is True
    assert failure["draft_remains_usable"] is True
    assert failure["no_false_saved_status"] is True
    assert failure["retry_allowed"] is True
    assert failure["sources_unchanged"] is True
    assert failure["never_delete_foreign_files_as_cleanup"] is True
    assert failure["large_copy_not_on_realtime_audio_path"] is True


def test_lifecycle_outcomes_complete_and_separated_from_persistence_status(
    contract: dict, markdown: str
) -> None:
    codes = contract["lifecycle_outcome_codes"]
    assert codes == list(REQUIRED_LIFECYCLE_CODES)
    assert len(codes) == len(set(codes))
    rel = contract["persistence_status_relationship"]
    assert rel["vocabularies_must_not_be_merged"] is True
    assert "PERSISTENCE_STATUS" in rel["PERSISTENCE_STATUS_star_owner"] or (
        rel["PERSISTENCE_STATUS_star_owner"] == "src/workbench_session_store.py"
    )
    for code in REQUIRED_LIFECYCLE_CODES:
        assert code in markdown


def test_legacy_migration_non_destructive(contract: dict, markdown: str) -> None:
    legacy = contract["legacy_migration"]
    assert legacy["legacy_filename"] == "workbench_session.json"
    assert legacy["supported_schema_versions"] == [1, 2]
    assert legacy["detection_outcome"] == "migration_required"
    assert legacy["auto_create_on_boot"] is False
    assert legacy["claim_must_be_explicit_and_deterministic"] is True
    assert legacy["no_silent_deletion"] is True
    assert legacy["no_silent_overwrite"] is True
    assert legacy["failure_leaves_legacy_recoverable"] is True
    assert legacy["missing_media_truthful"] is True
    assert legacy["successful_create_rewrites_absolute_refs_to_package_relative"] is True
    assert legacy["destructive_migration_forbidden"] is True
    assert "workbench_session.json" in markdown
    assert "non-destructive" in markdown.lower() or "Non-destructive" in markdown


def test_draft_loss_and_browser_and_write_honesty(contract: dict) -> None:
    draft = contract["draft_loss"]
    assert draft["unsaved_draft_must_not_silently_disappear"] is True
    assert draft["product_close_must_detect_draft_loss"] is True
    assert draft["dont_show_again_suppresses_only_draft_loss_warning"] is True
    assert draft["package_switch_must_not_silently_discard_non_exported_draft"] is True
    assert draft["exact_ux_copy_placement"] == "OPEN_PRODUCT_GATE"

    browser = contract["browser_registration"]
    assert browser["registration_is_not_activation"] is True
    assert browser["package_row_is_not_sample_row"] is True
    assert browser["explicit_open_binds_active_track"] is True
    assert browser["repeated_registration_or_open_deterministic"] is True
    assert browser["no_multi_track_live_semantics"] is True

    write = contract["write_honesty_post_create"]
    assert write["single_python_persistence_authority"] is True
    assert write["never_false_success"] is True
    assert write["no_qml_owned_persistence"] is True
    assert write["write_failure_observable_code"] == "write_failed"
    assert write["runtime_owner_issue"] == 1085


def test_validation_vectors_1_to_15_complete_and_unique(contract: dict) -> None:
    vectors = contract["validation_vectors"]
    assert len(vectors) == 15
    ids = [v["id"] for v in vectors]
    assert ids == list(range(1, 16))
    names = [v["name"] for v in vectors]
    assert len(names) == len(set(names))
    allowed = set(REQUIRED_LIFECYCLE_CODES)
    for vector in vectors:
        outcomes = vector["expected_outcome_codes"]
        assert outcomes, f"vector {vector['id']} needs expected outcomes"
        assert set(outcomes) <= allowed, (
            f"vector {vector['id']} has unknown codes: {set(outcomes) - allowed}"
        )


def test_vectors_1_and_2_explicit_open_require_open(contract: dict) -> None:
    for vector_id in (1, 2):
        vector = next(v for v in contract["validation_vectors"] if v["id"] == vector_id)
        assert vector["expected_outcome_codes"] == ["open"], vector


def test_vector_11_successful_legacy_claim_binds_open(contract: dict) -> None:
    vector = next(v for v in contract["validation_vectors"] if v["id"] == 11)
    assert vector["expected_outcome_codes"] == ["open"]


def test_vector_14_restart_restores_open_active_track(contract: dict) -> None:
    vector = next(v for v in contract["validation_vectors"] if v["id"] == 14)
    assert vector["expected_outcome_codes"] == ["open"]


def test_vector_12_splits_detection_from_missing_media_claim(contract: dict) -> None:
    vector = next(v for v in contract["validation_vectors"] if v["id"] == 12)
    ops = {item["op"]: item for item in vector["operations"]}
    assert ops["detect_supported_legacy_with_missing_media"]["expected_outcome_codes"] == [
        "migration_required"
    ]
    assert ops["attempt_claim_legacy_with_missing_media"]["expected_outcome_codes"] == [
        "missing_media"
    ]
    per_op_union: set[str] = set()
    for item in vector["operations"]:
        per_op_union.update(item["expected_outcome_codes"])
    assert set(vector["expected_outcome_codes"]) == per_op_union
    assert "migration_failed" not in per_op_union


def test_vector_7_repeated_ops_have_deterministic_per_operation_outcomes(
    contract: dict,
) -> None:
    vector = next(v for v in contract["validation_vectors"] if v["id"] == 7)
    ops = {item["op"]: item for item in vector["operations"]}
    assert ops["repeated_create_at_existing_package_root"]["expected_outcome_codes"] == [
        "destination_unavailable"
    ]
    assert ops["repeated_open_same_package"]["expected_outcome_codes"] == ["open"]
    assert set(ops["repeated_register_same_package_root"]["expected_outcome_codes"]) == {
        "ready",
        "open",
    }
    conflict = ops["register_conflict_different_package_same_key"]
    assert set(conflict["expected_outcome_codes"]) <= {"ready", "open"}
    assert "reject" in conflict["notes"].lower() or "fail closed" in conflict["notes"].lower()
    # Top-level union must equal the per-op union (no leftover ambiguous codes).
    per_op_union: set[str] = set()
    for item in vector["operations"]:
        per_op_union.update(item["expected_outcome_codes"])
    assert set(vector["expected_outcome_codes"]) == per_op_union
    assert "draft" not in per_op_union


def test_cross_contract_boundaries(contract: dict, markdown: str) -> None:
    boundaries = contract["cross_contract_boundaries"]
    expected_snippets = {
        "1083": "32-field",
        "1084": "Arrangement",
        "1078": "transition",
        "1085": "runtime",
    }
    for key, issue in CROSS_CONTRACT_OWNERS.items():
        text = boundaries[key]
        assert isinstance(text, str) and text.strip(), f"missing boundary text for {key}"
        assert str(issue) in text or f"#{issue}" in markdown
        needle = expected_snippets[key].lower()
        assert needle in text.lower(), f"boundary {key} missing owner cue {needle!r}: {text!r}"
        assert f"#{issue}" in markdown
    reserved = contract["reserved_extension_ownership"]
    assert reserved["arrangement"]["owner_issue"] == 1084
    assert reserved["arrangement"]["semantics_defined_here"] is False
    assert reserved["midi"]["semantics_defined_here"] is False
    assert "1085" in boundaries
    assert boundaries["1085"].lower().find("runtime") >= 0


def test_demo_export_remains_distinct(contract: dict, markdown: str) -> None:
    demo = contract["demo_export_vs_track_package"]
    assert demo["commands_remain_distinct"] is True
    assert demo["demo_export_kit"]["activates_durable_track"] is False
    assert demo["create_track_package"]["activates_durable_track"] is True
    assert "Export Kit" in markdown
    assert "728" in markdown


def test_no_private_absolute_fixture_paths_in_contract_artifacts(
    contract: dict, markdown: str
) -> None:
    blob = json.dumps(contract) + "\n" + markdown
    # Reject private machine-local path fixtures (mentions of forbidden shapes as
    # rules are allowed; concrete user home / env assignments are not).
    assert not re.search(r"(?i)[A-Z]:\\Users\\", blob)
    assert "C:\\Users" not in blob
    assert "/Users/" not in blob
    assert "SAMPLE_BRAIN_DB_PATH=" not in blob
    assert not re.search(r"(?i)file:///[A-Za-z]:", blob)


def test_hard_out_of_scope_preserves_runtime_boundaries(contract: dict) -> None:
    out = set(contract["hard_out_of_scope"])
    for item in (
        "qml",
        "arrangement_ui",
        "pattern_timing_1083",
        "arrangement_block_mask_implementation_1084",
        "runtime_persistence_1085",
        "browser_runtime",
        "multi_track_live",
    ):
        assert item in out
