"""Contract-slice validation for #1224 Live Kit portable export freeze.

Canonical authority:
- docs/LIVE_KIT_EXPORT_V1_CONTRACT.md
- docs/live_kit_export_v1.json

These tests pin only the normative contract plane. They must not rewrite the
#728 exporter, implement track-package create, or claim #1221 runtime acceptance.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_MD = REPO_ROOT / "docs" / "LIVE_KIT_EXPORT_V1_CONTRACT.md"
CONTRACT_JSON = REPO_ROOT / "docs" / "live_kit_export_v1.json"
CANON_INDEX = REPO_ROOT / "docs" / "CANON_INDEX.md"

REQUIRED_LAYOUT_COMPONENTS = ("manifest.json", "audio/")
REQUIRED_TOP_LEVEL = ("schema_version", "kit_type", "export_type", "groups")
REQUIRED_SLOT_FIELDS = ("group", "slot", "assigned", "display_name", "audio_path")
OPTIONAL_METADATA = ("bpm", "key", "pred_type", "sample_class", "duration_sec")
REQUIRED_STAGES = (
    "snapshot_live_kit_state",
    "evaluate_eligibility",
    "create_sibling_staging_directory_same_filesystem",
    "copy_required_assigned_media_byte_identical",
    "ensure_group_folders_exist",
    "write_manifest_json",
    "validate_staged_tree_against_manifest",
    "commit_staging_to_final_root",
    "report_success_with_final_path",
)
REQUIRED_ELIGIBILITY_IDS = (
    "empty_kit",
    "sparse_kit",
    "source_missing",
    "source_not_file",
    "source_unreadable",
    "source_reuse_multi_slot",
    "duplicate_basenames",
    "internal_collision",
    "catalog_stale_but_readable",
    "unknown_metadata",
    "destination_invalid",
    "destination_not_writable",
    "output_exists",
    "export_failed",
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
    assert contract["document_type"] == "sample_brain.live_kit_export_v1_contract"
    assert contract["plane"] == "normative_contract_schema"
    assert contract["not_runtime_serialization"] is True
    assert contract["issue"] == 1224
    assert 1221 in contract["parent_issues"]
    assert 728 in contract["historical_evidence_issues"]
    assert contract["exit_marker"] == "LIVE_KIT_EXPORT_V1_CONTRACT_FROZEN"
    assert contract["kit_type"] == "sample_brain_live_kit"
    assert contract["export_type"] == "local_folder"
    assert "sample_brain_track_package" in contract["distinct_from_package_kinds"]


def test_markdown_exit_marker_and_plane_distinction(markdown: str) -> None:
    assert "LIVE_KIT_EXPORT_V1_CONTRACT_FROZEN" in markdown
    assert "normative contract" in markdown.lower()
    assert "not_runtime_serialization" in markdown or "not** the runtime" in markdown.lower()
    assert "Sample Brain Live Kit" in markdown
    assert "manifest.json" in markdown


def test_bundle_layout_v1(contract: dict, markdown: str) -> None:
    layout = contract["bundle_layout_v1"]
    assert layout["root_directory_name"] == "Sample Brain Live Kit"
    assert layout["manifest_filename"] == "manifest.json"
    assert layout["media_directory"] == "audio/"
    assert layout["human_readable_readme_included"] is False
    for item in REQUIRED_LAYOUT_COMPONENTS:
        assert item in layout["required_components"]
        assert item in markdown
    assert "Excluded" in markdown or "excluded" in markdown


def test_schema_version_and_required_fields(contract: dict, markdown: str) -> None:
    policy = contract["schema_version_policy"]
    assert policy["v1_value"] == 1
    assert policy["unsupported_future_version_fail_closed"] is True
    assert contract["required_manifest_top_level_fields"] == list(REQUIRED_TOP_LEVEL)
    assert contract["required_slot_fields"] == list(REQUIRED_SLOT_FIELDS)
    assert contract["optional_resolved_metadata_fields"] == list(OPTIONAL_METADATA)
    for token in REQUIRED_TOP_LEVEL:
        assert token in markdown
    for token in OPTIONAL_METADATA:
        assert token in markdown


def test_media_semantics_copy_per_slot(contract: dict, markdown: str) -> None:
    media = contract["media_semantics"]
    assert media["source_reuse_policy"] == "COPY_PER_SLOT"
    assert media["library_sources_unchanged"] is True
    assert media["missing_media_prevents_false_success"] is True
    assert media["no_dependency_on_original_library_path_after_success"] is True
    assert "COPY_PER_SLOT" in markdown
    assert "byte" in markdown.lower() or "copies" in markdown.lower()


def test_metadata_authority_resolved_consumer_only(contract: dict, markdown: str) -> None:
    meta = contract["metadata_authority"]
    assert meta["export_plane"] == "resolved_product_consumer_metadata"
    assert meta["forbid_export_raw_analyzer_features_as_resolved_truth"] is True
    assert meta["forbid_reparse_filename_path_claims_at_export"] is True
    assert meta["path_metadata_authority_issue"] == 1203
    assert meta["unknown_remains_unknown"] is True
    assert meta["no_fabricated_confidence"] is True
    assert meta["portable_manifest_embeds_raw_provenance_block"] is False
    assert "1203" in markdown
    assert "resolved" in markdown.lower()
    assert "features.*" in markdown or "raw analyzer" in markdown.lower()


def test_eligibility_vectors_complete(contract: dict, markdown: str) -> None:
    assert contract["eligibility_status_vocabulary"] == ["EXPORTABLE", "NOT_EXPORTABLE"]
    vectors = {item["id"]: item for item in contract["eligibility_vectors"]}
    assert set(vectors) == set(REQUIRED_ELIGIBILITY_IDS)
    assert vectors["empty_kit"]["exportable"] is False
    assert vectors["empty_kit"]["status"] == "EMPTY_KIT"
    assert vectors["sparse_kit"]["exportable"] is True
    assert vectors["source_missing"]["status"] == "SOURCE_MISSING"
    assert vectors["source_reuse_multi_slot"]["exportable"] is True
    assert vectors["unknown_metadata"]["exportable"] is True
    assert vectors["output_exists"]["status"] == "OUTPUT_EXISTS"
    assert "EMPTY_KIT" in markdown
    assert "EXPORTABLE" in markdown
    assert "NOT_EXPORTABLE" in markdown


def test_integrity_structural_only(contract: dict, markdown: str) -> None:
    integrity = contract["integrity"]
    assert integrity["mode"] == "structural_only"
    assert integrity["content_hashes_required"] is False
    assert integrity["signing_subsystem_forbidden_for_v1"] is True
    assert "structural" in markdown.lower()
    assert "hash" in markdown.lower()


def test_export_transaction_and_atomicity(contract: dict, markdown: str) -> None:
    assert contract["export_transaction_stages"] == list(REQUIRED_STAGES)
    atomicity = contract["atomicity"]
    assert atomicity["partial_output_never_reports_success"] is True
    assert atomicity["no_half_valid_visible_final_folder"] is True
    assert atomicity["library_sources_unchanged"] is True
    assert atomicity["never_delete_foreign_destination_files_as_cleanup"] is True
    assert "staging" in markdown.lower()
    assert "partial" in markdown.lower()


def test_reference_confinement_and_destination(contract: dict, markdown: str) -> None:
    rules = contract["reference_confinement"]
    assert rules["media_refs_package_relative"] is True
    assert rules["media_under_audio_dir_only"] is True
    assert rules["forbid_absolute_windows_paths"] is True
    assert rules["forbid_sqlite_db_dependency"] is True
    assert rules["forbid_credentials_operator_metadata"] is True
    assert rules["reject_outcome"] == "path_escape_rejected"
    dest = contract["destination_eligibility"]
    assert dest["must_not_be_inside_repository_checkout"] is True
    assert "absolute" in markdown.lower()
    assert "DATA_AND_ARTIFACT_POLICY" in markdown or "repository checkout" in markdown.lower()


def test_reuse_seams_forbid_second_architecture(contract: dict, markdown: str) -> None:
    reuse = contract["reuse_seams"]
    assert reuse["historical_728_module"] == "src/workbench_live_kit_export.py"
    assert reuse["forbid_second_packaging_architecture"] is True
    track = reuse["track_package_1082_1085"]
    assert track["may_share_staging_validation_confinement_patterns"] is True
    assert track["commands_remain_distinct"] is True
    assert track["layouts_remain_distinct"] is True
    assert track["must_not_activate_durable_track"] is True
    assert "728" in markdown
    assert "1082" in markdown
    assert "second" in markdown.lower() or "distinct" in markdown.lower()


def test_identity_no_required_kit_or_sample_id(contract: dict, markdown: str) -> None:
    identity = contract["identity"]
    assert identity["portable_kit_id_required"] is False
    assert identity["catalog_sample_id_required"] is False
    assert identity["full_canonical_slot_map_always_present"] is True
    assert identity["domain_keys_not_display_labels"] is True
    assert "kit_id" in markdown.lower() or "sample_id" in markdown.lower()


def test_field_and_eligibility_tables_present_in_markdown(markdown: str) -> None:
    assert "FIELD/PATH" in markdown
    assert "SOURCE AUTHORITY" in markdown
    assert "UNKNOWN SEMANTICS" in markdown
    assert "PORTABILITY RULE" in markdown
    assert "INPUT CONDITION" in markdown
    assert "EXPORTABLE?" in markdown
    assert "PARTIAL OUTPUT POLICY" in markdown


def test_canon_index_registers_contract() -> None:
    text = CANON_INDEX.read_text(encoding="utf-8")
    assert "LIVE_KIT_EXPORT_V1_CONTRACT" in text or "live_kit_export_v1" in text
    assert "1224" in text
