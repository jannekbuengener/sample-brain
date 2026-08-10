from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VOCAB_PATH = REPO_ROOT / "docs" / "arrangement_role_vocabulary_v1.json"

REQUIRED_SECTION_ROLES = {
    "intro",
    "groove",
    "build",
    "drop",
    "breakdown",
    "outro",
    "unknown",
}

REQUIRED_EVENTS = {
    "drop_onset",
}

REQUIRED_SECTION_ROLE_FIELDS = {
    "name",
    "definition",
    "musical_function",
    "typical_position",
    "positive_signals",
    "negative_signals",
    "typical_confusions",
    "allowed_neighbors",
    "must_not_derive",
}

REQUIRED_EVENT_FIELDS = {
    "name",
    "definition",
    "musical_meaning",
    "positive_signals",
    "negative_signals",
    "relation_to_section_roles",
}

REQUIRED_DEFERRED_FIELDS = {
    "term",
    "decision",
    "reasoning",
    "modeling_alternative",
    "future",
}

REQUIRED_UNKNOWN_POLICY_FIELDS = {
    "status",
    "conditions",
    "outcome",
    "no_dummy_confidence",
    "manual_override",
}

REQUIRED_LAYER_SEPARATION_FIELDS = {
    "neutral_boundary_layer",
    "arrangement_role_layer",
    "confidence_override_layer",
    "rules",
}


def _load_vocab() -> dict:
    return json.loads(VOCAB_PATH.read_text(encoding="utf-8"))


def test_vocabulary_has_contract_header():
    vocab = _load_vocab()

    assert vocab["document_type"] == "sample_brain.arrangement_role_vocabulary"
    assert vocab["schema_version"] == "1.0.0"
    assert vocab["issue"] == 238
    assert vocab["parent_issue"] == 228
    assert vocab["track_map_contract_issue"] == 232
    assert vocab["signal_matrix_issue"] == 239
    assert vocab["structure_v1_issue"] == 265
    assert vocab["confidence_contract_issue"] == 241
    assert vocab["classifier_issue"] == 240


def test_exactly_seven_core_section_roles():
    vocab = _load_vocab()
    section_roles = {role["name"] for role in vocab["section_roles"]}

    assert section_roles == REQUIRED_SECTION_ROLES
    assert len(vocab["section_roles"]) == 7


def test_unknown_is_present_and_first_class():
    vocab = _load_vocab()
    unknown_role = next(r for r in vocab["section_roles"] if r["name"] == "unknown")

    assert unknown_role["name"] == "unknown"
    assert "valid" in unknown_role["definition"].lower()
    assert (
        "normal" in unknown_role["definition"].lower()
        or "first" in unknown_role["musical_function"].lower()
    )


def test_drop_onset_is_event_not_section_role():
    vocab = _load_vocab()

    # drop_onset NOT in section roles
    section_role_names = {role["name"] for role in vocab["section_roles"]}
    assert "drop_onset" not in section_role_names

    # drop_onset IN boundary events
    event_names = {event["name"] for event in vocab["boundary_events"]}
    assert event_names == REQUIRED_EVENTS
    assert len(vocab["boundary_events"]) == 1

    drop_onset = vocab["boundary_events"][0]
    assert drop_onset["name"] == "drop_onset"
    assert "not a section role" in drop_onset["relation_to_section_roles"].lower()


def test_drop_and_drop_onset_are_distinct():
    vocab = _load_vocab()

    drop_role = next(r for r in vocab["section_roles"] if r["name"] == "drop")
    drop_onset = vocab["boundary_events"][0]

    # drop role must_not_derive explicitly states the distinction
    assert "drop_onset is the entry event" in drop_role["must_not_derive"]
    assert "drop is the section" in drop_role["must_not_derive"]

    # drop_onset event relation_to_section_roles states the distinction
    assert "not a section role" in drop_onset["relation_to_section_roles"].lower()
    assert (
        "section after this boundary is drop" in drop_onset["relation_to_section_roles"]
    )


def test_transition_decision_explicit_and_not_enforced():
    vocab = _load_vocab()

    deferred = vocab["deferred_terms"]
    assert len(deferred) == 1
    assert deferred[0]["term"] == "transition"
    assert "not a core section role" in deferred[0]["decision"].lower()
    assert "transition" not in {r["name"] for r in vocab["section_roles"]}
    assert "transition" not in {e["name"] for e in vocab["boundary_events"]}


def test_no_genre_subtypes_as_roles():
    vocab = _load_vocab()
    all_names = {r["name"] for r in vocab["section_roles"]} | {
        e["name"] for e in vocab["boundary_events"]
    }

    # Check no underscore genre sub-typing
    for name in all_names:
        assert (
            "_" not in name or name == "drop_onset"
        ), f"Genre sub-type detected: {name}"


def test_unknown_policy_fully_defined():
    vocab = _load_vocab()
    policy = vocab["unknown_policy"]

    assert REQUIRED_UNKNOWN_POLICY_FIELDS <= set(policy.keys())
    assert policy["status"] == "first_class_normal_result"
    assert policy["no_dummy_confidence"] is True
    assert len(policy["conditions"]) >= 4
    assert "missing" in " ".join(policy["conditions"]).lower()
    assert "contradictory" in " ".join(policy["conditions"]).lower()
    assert "weak" in " ".join(policy["conditions"]).lower()
    assert (
        "outside" in " ".join(policy["conditions"]).lower()
        or "vocabulary" in " ".join(policy["conditions"]).lower()
    )


def test_layer_separation_explicit():
    vocab = _load_vocab()
    layers = vocab["layer_separation"]

    assert REQUIRED_LAYER_SEPARATION_FIELDS <= set(layers.keys())

    # Neutral boundary layer rules
    neutral = layers["neutral_boundary_layer"]
    forbidden = neutral["must_not_emit"]
    for role in REQUIRED_SECTION_ROLES:
        assert role in forbidden
    assert "drop_onset" in forbidden
    assert "transition" in forbidden

    # Arrangement role layer
    role_layer = layers["arrangement_role_layer"]
    assert "neutral sections" in role_layer["consumes"].lower()
    assert "role signals" in role_layer["consumes"].lower()

    # Rules array has key separation rules
    rules_text = " ".join(layers["rules"]).lower()
    assert "boundary confidence and role confidence stay separate" in rules_text
    assert "strong neutral boundary can still have role unknown" in rules_text
    assert "strong role hint must not create a boundary" in rules_text
    assert "structurev1 never emits roles or events" in rules_text
    assert "arrangement map never moves neutral boundaries" in rules_text
    assert "drop_onset references a neutral boundary position" in rules_text
    assert "does not create one" in rules_text
    assert "drop section can exist without a drop_onset" in rules_text
    assert "drop_onset event can exist without a following drop role" in rules_text


def test_section_roles_have_complete_fields():
    vocab = _load_vocab()

    for role in vocab["section_roles"]:
        assert REQUIRED_SECTION_ROLE_FIELDS <= set(
            role.keys()
        ), f"Missing fields in {role['name']}"
        assert role["name"]
        assert role["definition"]
        assert role["musical_function"]
        assert role["typical_position"]
        assert isinstance(role["positive_signals"], list)
        assert isinstance(role["negative_signals"], list)
        assert isinstance(role["typical_confusions"], list)
        assert isinstance(role["allowed_neighbors"], list)
        assert role["must_not_derive"]
        # Verify positive/negative signals reference known signal names from #239
        # (We don't validate against #239 here to avoid cross-file coupling in tests)


def test_events_have_complete_fields():
    vocab = _load_vocab()

    for event in vocab["boundary_events"]:
        assert REQUIRED_EVENT_FIELDS <= set(
            event.keys()
        ), f"Missing fields in event {event.get('name', '?')}"
        assert event["name"]
        assert event["definition"]
        assert event["musical_meaning"]
        assert isinstance(event["positive_signals"], list)
        assert isinstance(event["negative_signals"], list)
        assert event["relation_to_section_roles"]


def test_deferred_terms_complete():
    vocab = _load_vocab()

    for term in vocab["deferred_terms"]:
        assert REQUIRED_DEFERRED_FIELDS <= set(
            term.keys()
        ), f"Missing fields in deferred term {term.get('term', '?')}"
        assert term["term"]
        assert term["decision"]
        assert term["reasoning"]
        assert term["modeling_alternative"]
        assert term["future"]


def test_signal_reference_structure():
    vocab = _load_vocab()
    signals = vocab["signal_reference"]

    assert signals["source"] == "Arrangement Signal Matrix v1 (#239)"
    assert signals["normalization"] == "track_relative_only"
    assert (
        "universal TechNo thresholds" in " ".join(signals["forbidden"]).lower()
        or "universal techno thresholds" in " ".join(signals["forbidden"]).lower()
    )
    assert "track percentile" in " ".join(signals["allowed_normalization"]).lower()

    # All 7 roles + drop_onset have signal groups
    role_groups = signals["role_signal_groups"]
    expected = REQUIRED_SECTION_ROLES | REQUIRED_EVENTS
    assert set(role_groups.keys()) == expected

    for role_name, group in role_groups.items():
        assert "positive" in group
        assert "negative" in group
        assert isinstance(group["positive"], list)
        assert isinstance(group["negative"], list)
        assert len(group["positive"]) > 0
        assert len(group["negative"]) > 0


def test_non_goals_listed():
    vocab = _load_vocab()
    non_goals = vocab["non_goals_v1"]

    assert isinstance(non_goals, list)
    assert len(non_goals) >= 6
    non_goals_text = " ".join(non_goals).lower()
    assert "classification rules" in non_goals_text
    assert "boundary detection" in non_goals_text
    assert "clap" in non_goals_text
    assert "genre sub-typing" in non_goals_text or "sub-typing" in non_goals_text
    assert "transition" in non_goals_text
    assert "confidence" in non_goals_text
    assert "asset generation" in non_goals_text or "asset" in non_goals_text


def test_acceptance_mapping_present():
    vocab = _load_vocab()
    mapping = vocab["acceptance_mapping"]

    assert "role_vocabulary_documented" in mapping
    assert "section_roles_and_boundary_events_separated" in mapping
    assert "drop_and_drop_onset_distinguished" in mapping
    assert "unknown_fully_defined" in mapping
    assert "transition_decision_explicit" in mapping
    assert "contract_usable_for_239_240" in mapping


def test_versioning_info_present():
    vocab = _load_vocab()

    # Schema version in header
    assert vocab["schema_version"] == "1.0.0"
    assert vocab["document_type"] == "sample_brain.arrangement_role_vocabulary"

    # The JSON doesn't have a separate versioning section but the header contains it
    # and the markdown documents versioning policy
