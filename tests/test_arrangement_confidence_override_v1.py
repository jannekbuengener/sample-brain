from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO_ROOT / "docs" / "arrangement_confidence_override_v1.json"

# Expected status values from the contract
EXPECTED_STATUSES = [
    "available",
    "uncertain",
    "unknown",
    "unavailable",
    "failed",
]

# Section roles from #238 vocabulary
SECTION_ROLES = {
    "intro",
    "groove",
    "build",
    "drop",
    "breakdown",
    "outro",
    "unknown",
}

# Boundary events from #238 vocabulary
BOUNDARY_EVENTS = {"drop_onset"}

ALL_ROLES_AND_EVENTS = SECTION_ROLES | BOUNDARY_EVENTS


def _load_contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def test_contract_has_required_header():
    """Contract has correct document type, schema version, and issue references."""
    contract = _load_contract()

    assert contract["document_type"] == "sample_brain.arrangement_confidence_override"
    assert contract["schema_version"] == "1.0.0"
    assert contract["issue"] == 241
    assert contract["parent_issue"] == 228
    assert contract["track_map_contract_issue"] == 232
    assert contract["role_vocabulary_issue"] == 238
    assert contract["signal_matrix_issue"] == 239
    assert contract["classifier_issue"] == 240
    assert contract["structure_v1_issue"] == 265


def test_status_model_defined():
    """Status model defines exactly the five required values with definitions."""
    contract = _load_contract()
    status_model = contract["status_model"]

    assert "values" in status_model
    assert "definitions" in status_model
    assert "rules" in status_model

    assert status_model["values"] == EXPECTED_STATUSES
    assert len(status_model["values"]) == 5

    # Each status has a definition
    for status in EXPECTED_STATUSES:
        assert status in status_model["definitions"]
        assert status_model["definitions"][status]  # non-empty


def test_unknown_is_first_class_normal_result():
    """Status 'unknown' is explicitly a first-class normal result, not an error."""
    contract = _load_contract()
    rules = contract["status_model"]["rules"]

    rules_text = " ".join(rules).lower()
    assert "unknown" in rules_text
    assert "first-class" in rules_text or "first class" in rules_text
    assert "not an error" in rules_text or "not error" in rules_text
    assert "dummy confidence" in rules_text or "no dummy" in rules_text


def test_status_rules_enforce_boundary_role_separation():
    """Status rules explicitly separate boundary and role uncertainty."""
    contract = _load_contract()
    rules = contract["status_model"]["rules"]

    rules_text = " ".join(rules).lower()
    assert "boundary" in rules_text
    assert "role" in rules_text
    assert "separate" in rules_text or "independent" in rules_text


def test_automatic_result_schema_complete():
    """Automatic result schema has all required fields and structure."""
    contract = _load_contract()
    auto = contract["automatic_result"]

    assert "fields" in auto
    assert "required" in auto
    assert "rules" in auto

    fields = auto["fields"]
    required = auto["required"]

    # Core required fields
    assert "role" in required
    assert "status" in required
    assert "evidence" in required
    assert "provenance" in required

    # Role field matches #238 vocabulary
    role_field = fields["role"]
    assert set(role_field["enum"]) == SECTION_ROLES
    assert "unknown" in role_field["enum"]

    # Event field matches #238 vocabulary
    event_field = fields["event"]
    assert set(event_field["enum"]) == BOUNDARY_EVENTS | {"null"}

    # Status references status model
    status_field = fields["status"]
    assert "$ref" in status_field or status_field.get("enum") == EXPECTED_STATUSES

    # Evidence structure
    evidence = fields["evidence"]
    assert evidence["type"] == "object"
    evidence_props = evidence["properties"]
    assert "positive_signals" in evidence_props
    assert "negative_signals" in evidence_props
    assert "missing_signals" in evidence_props
    assert "contradictory_signals" in evidence_props

    # Provenance structure
    provenance = fields["provenance"]
    assert provenance["type"] == "object"
    prov_props = provenance["properties"]
    assert prov_props["component"]["const"] == "arrangement_map"
    assert "timestamp_utc" in prov_props

    # Scores are optional
    scores = fields["scores"]
    assert scores["type"] == "object"
    score_props = scores["properties"]
    assert "role_score" in score_props
    assert "event_score" in score_props
    assert "boundary_quality" in score_props


def test_automatic_result_rules_preserve_history():
    """Automatic result rules prevent deletion/invisible replacement."""
    contract = _load_contract()
    rules = contract["automatic_result"]["rules"]

    rules_text = " ".join(rules).lower()
    assert "never deleted" in rules_text or "preserved" in rules_text
    assert "invisibly replaced" in rules_text or "not.*replace" in rules_text


def test_manual_override_schema_complete():
    """Manual override schema has all required fields with nullable metadata."""
    contract = _load_contract()
    override = contract["manual_override"]

    assert "fields" in override
    assert "required" in override
    assert "rules" in override

    fields = override["fields"]
    required = override["required"]

    # Only 'source' is required
    assert required == ["source"]

    # Source is fixed to 'manual'
    assert fields["source"]["const"] == "manual"

    # Role and event are optional (can override one or both)
    assert "role" in fields
    assert "event" in fields

    # Metadata fields are nullable
    for field_name in ["author", "timestamp_utc", "reason"]:
        field = fields[field_name]
        assert "null" in str(field.get("type", "")) or field.get("type") == [
            "string",
            "null",
        ]


def test_manual_override_rules():
    """Override rules enforce independence and non-destructive behavior."""
    contract = _load_contract()
    rules = contract["manual_override"]["rules"]

    rules_text = " ".join(rules).lower()
    assert "independently" in rules_text or "independent" in rules_text
    assert "not imply" in rules_text or "do not imply" in rules_text
    assert "nullable" in rules_text or "null" in rules_text
    assert "coexist" in rules_text or "preserved" in rules_text
    assert "unknown" in rules_text


def test_effective_value_policy_defined():
    """Effective value policy has clear resolution rules and examples."""
    contract = _load_contract()
    policy = contract["effective_value_policy"]

    assert "rules" in policy
    assert "examples" in policy

    rules = policy["rules"]
    rules_text = " ".join(rules).lower()
    assert "override" in rules_text
    assert "automatic" in rules_text
    assert "effective" in rules_text
    assert "derived view" in rules_text or "derived" in rules_text
    assert "preserved" in rules_text
    assert "independently" in rules_text
    assert "removing" in rules_text or "removal" in rules_text
    assert "re-analysis" in rules_text or "reanalysis" in rules_text


def test_effective_value_examples_cover_required_cases():
    """Examples cover all five required scenarios from the spec."""
    contract = _load_contract()
    examples = contract["effective_value_policy"]["examples"]

    # Check all five examples exist
    expected_examples = ["A", "B", "C", "D", "E"]
    for ex in expected_examples:
        assert ex in examples, f"Missing example {ex}"

    # A: secure boundary + unknown role
    ex_a = examples["A"]
    assert ex_a["automatic"]["role"] == "unknown"
    assert ex_a["override"] is None
    assert ex_a["effective"]["role"] == "unknown"

    # B: automatic groove + manual override to build
    ex_b = examples["B"]
    assert ex_b["automatic"]["role"] == "groove"
    assert ex_b["override"]["role"] == "build"
    assert ex_b["effective"]["role"] == "build"

    # C: automatic drop preserved, effective becomes manual groove
    ex_c = examples["C"]
    assert ex_c["automatic"]["role"] == "drop"
    assert ex_c["override"]["role"] == "groove"
    assert ex_c["effective"]["role"] == "groove"
    assert ex_c["effective"]["event"] == "drop_onset"

    # D: drop_onset event separate from section role
    ex_d = examples["D"]
    assert ex_d["automatic"]["event"] == "drop_onset"
    assert ex_d["override"]["event"] is None
    assert ex_d["effective"]["event"] is None
    assert ex_d["effective"]["role"] == "drop"

    # E: override removed -> automatic becomes effective again
    ex_e = examples["E"]
    assert ex_e["override_removed"] is True
    assert ex_e["effective"]["role"] == "build"


def test_boundary_vs_role_uncertainty_separation():
    """Boundary vs role uncertainty section enforces strict separation."""
    contract = _load_contract()
    sep = contract["boundary_vs_role_uncertainty"]

    assert "rules" in sep
    rules = sep["rules"]
    rules_text = " ".join(rules).lower()

    assert "structurev1" in rules_text
    assert "arrangement map" in rules_text
    assert "never emits roles" in rules_text
    assert "never moves neutral boundaries" in rules_text
    assert "drop_onset" in rules_text
    assert "references" in rules_text and "does not create" in rules_text
    assert "universal confidence" in rules_text or "single universal" in rules_text


def test_score_confidence_policy_no_universal_confidence():
    """Score policy explicitly forbids invented universal confidence."""
    contract = _load_contract()
    policy = contract["score_confidence_policy"]

    assert "rules" in policy
    rules = policy["rules"]
    rules_text = " ".join(rules).lower()

    assert "no universal" in rules_text or "universal.*confidence" in rules_text
    assert "optional" in rules_text
    assert "explicitly defined" in rules_text
    assert "omitted" in rules_text or "omit" in rules_text
    assert "placeholder" in rules_text or "dummy" in rules_text
    assert "combined" in rules_text or "never combined" in rules_text
    assert "evidence_completeness" in rules_text


def test_versioning_defined():
    """Versioning section defines major/minor/patch triggers."""
    contract = _load_contract()
    versioning = contract["versioning"]

    assert versioning["schema_version"] == "1.0.0"
    assert versioning["document_type"] == "sample_brain.arrangement_confidence_override"
    assert "major_increments" in versioning
    assert "minor_increments" in versioning
    assert "patch_increments" in versioning
    assert len(versioning["major_increments"]) >= 3
    assert len(versioning["minor_increments"]) >= 2
    assert len(versioning["patch_increments"]) >= 2


def test_acceptance_mapping_complete():
    """Acceptance mapping covers all #241 criteria."""
    contract = _load_contract()
    mapping = contract["acceptance_mapping"]

    expected_keys = [
        "status_model_defined",
        "unknown_first_class",
        "automatic_vs_manual_separated",
        "effective_value_policy",
        "boundary_role_separation",
        "no_universal_confidence",
        "machine_readable_contract",
        "compatible_with_238_239_240_265",
    ]
    for key in expected_keys:
        assert key in mapping, f"Missing acceptance mapping: {key}"


def test_contract_compatible_with_role_vocabulary():
    """Contract enums match #238 vocabulary exactly."""
    contract = _load_contract()

    # Role enum in automatic_result matches #238 section roles
    auto_role_enum = set(contract["automatic_result"]["fields"]["role"]["enum"])
    assert auto_role_enum == SECTION_ROLES

    # Role enum in manual_override matches #238 section roles
    override_role_enum = set(contract["manual_override"]["fields"]["role"]["enum"])
    assert override_role_enum == SECTION_ROLES | {"null"}

    # Event enum matches #238 boundary events
    auto_event_enum = set(contract["automatic_result"]["fields"]["event"]["enum"])
    assert auto_event_enum == BOUNDARY_EVENTS | {"null"}

    override_event_enum = set(contract["manual_override"]["fields"]["event"]["enum"])
    assert override_event_enum == BOUNDARY_EVENTS | {"null"}


def test_no_dummy_confidence_for_unknown():
    """Contract explicitly states unknown needs no dummy confidence."""
    contract = _load_contract()

    # Check in status model rules
    status_rules_text = " ".join(contract["status_model"]["rules"]).lower()
    assert "dummy confidence" in status_rules_text or "no dummy" in status_rules_text

    # Check in score policy
    score_rules_text = " ".join(contract["score_confidence_policy"]["rules"]).lower()
    assert "dummy" in score_rules_text or "placeholder" in score_rules_text

    # Check in unknown policy reference
    assert "unknown" in status_rules_text


def test_automatic_result_preserved_when_override_set():
    """Contract rules ensure automatic result stays when override exists."""
    contract = _load_contract()
    auto_rules = " ".join(contract["automatic_result"]["rules"]).lower()
    override_rules = " ".join(contract["manual_override"]["rules"]).lower()
    effective_rules = " ".join(contract["effective_value_policy"]["rules"]).lower()

    assert "preserved" in auto_rules or "never deleted" in auto_rules
    assert "coexist" in override_rules or "preserved" in override_rules
    assert "preserved" in effective_rules


def test_override_removal_fallback():
    """Contract specifies override removal falls back to automatic without re-analysis."""
    contract = _load_contract()
    effective_rules = " ".join(contract["effective_value_policy"]["rules"]).lower()

    assert "removing" in effective_rules or "removal" in effective_rules
    assert (
        "re-analysis" in effective_rules
        or "reanalysis" in effective_rules
        or "re-analy" in effective_rules
    )


def test_boundary_and_role_status_independent():
    """Status model enforces boundary and role status independence."""
    contract = _load_contract()
    status_rules = " ".join(contract["status_model"]["rules"]).lower()

    assert "independent" in status_rules or "separate" in status_rules


def test_drop_and_drop_onset_different_layers():
    """Contract treats drop (role) and drop_onset (event) on different layers."""
    contract = _load_contract()

    # Automatic result has separate role and event fields
    auto_fields = contract["automatic_result"]["fields"]
    assert "role" in auto_fields
    assert "event" in auto_fields

    # Manual override has separate role and event fields
    override_fields = contract["manual_override"]["fields"]
    assert "role" in override_fields
    assert "event" in override_fields

    # Effective value policy has independent resolution
    effective_rules = " ".join(contract["effective_value_policy"]["rules"]).lower()
    assert "independently" in effective_rules


def test_override_metadata_nullable():
    """Override author/timestamp/reason are nullable, no fake values."""
    contract = _load_contract()
    override_fields = contract["manual_override"]["fields"]

    for field_name in ["author", "timestamp_utc", "reason"]:
        field = override_fields[field_name]
        # Check nullable type
        type_str = str(field.get("type", ""))
        assert "null" in type_str, f"Field {field_name} not nullable: {type_str}"

    # Check rules mention nullable
    override_rules = " ".join(contract["manual_override"]["rules"]).lower()
    assert "nullable" in override_rules or "null" in override_rules


def test_no_universal_confidence_enforced():
    """Contract enforces no universal confidence field."""
    contract = _load_contract()

    # Check score policy
    score_rules = " ".join(contract["score_confidence_policy"]["rules"]).lower()
    assert "no universal" in score_rules or "universal.*confidence" in score_rules

    # Check automatic result scores are optional and per-level
    auto_scores = contract["automatic_result"]["fields"]["scores"]["properties"]
    assert "role_score" in auto_scores
    assert "event_score" in auto_scores
    assert "boundary_quality" in auto_scores
    # No generic 'confidence' field
    assert "confidence" not in auto_scores


def test_versioning_explicit():
    """Versioning is clearly defined with schema version in header."""
    contract = _load_contract()

    assert contract["schema_version"] == "1.0.0"
    assert contract["document_type"] == "sample_brain.arrangement_confidence_override"
    assert "versioning" in contract
    versioning = contract["versioning"]
    assert versioning["schema_version"] == "1.0.0"


def test_json_schema_valid():
    """Contract JSON is valid and loadable."""
    contract = _load_contract()
    # If we get here, JSON is valid
    assert isinstance(contract, dict)
    assert len(contract) > 10  # substantial contract
