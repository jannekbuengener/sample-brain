from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = REPO_ROOT / "docs" / "arrangement_signal_matrix_v1.json"

ALLOWED_ROLES_AND_EVENTS = {
    "intro",
    "groove",
    "build",
    "drop",
    "breakdown",
    "outro",
    "unknown",
    "drop_onset",
}

REQUIRED_SIGNAL_FIELDS = {
    "name",
    "group",
    "meaning",
    "source_calculation",
    "aggregation",
    "normalization",
    "role_positive",
    "role_negative",
    "boundary_detection",
    "role_scoring",
    "mvp_level",
    "required_track_map_fields",
    "provenance",
    "missing_signal_behavior",
}

REQUIRED_GROUPS = {
    "energy_loudness",
    "low_end",
    "onsets",
    "rhythmic_stability",
    "timbre_changes",
    "spectral_changes",
    "self_similarity",
    "recurrence",
    "novelty",
    "before_after_differences",
    "multi_bar_trends",
    "beat_downbeat_reference",
    "neutral_section_boundaries",
    "drum_bass_activity",
    "missing_data",
}


def _load_matrix() -> dict:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def test_arrangement_signal_matrix_has_contract_header():
    matrix = _load_matrix()

    assert matrix["document_type"] == "sample_brain.arrangement_signal_matrix"
    assert matrix["schema_version"] == 1
    assert matrix["issue"] == 239
    assert matrix["parent_issue"] == 228
    assert matrix["track_map_contract_issue"] == 232
    assert matrix["structure_v1_issue"] == 265


def test_role_vocabulary_matches_issue_238_draft():
    matrix = _load_matrix()
    vocabulary = matrix["role_vocabulary"]

    assert vocabulary["source_issue"] == 238
    assert vocabulary["status"] == "draft_from_open_issue"
    assert set(vocabulary["section_roles"]) == {
        "intro",
        "groove",
        "build",
        "drop",
        "breakdown",
        "outro",
        "unknown",
    }
    assert vocabulary["boundary_events"] == ["drop_onset"]
    assert "transition" in vocabulary["deferred_terms"]


def test_every_signal_declares_required_contract_fields():
    matrix = _load_matrix()
    signals = matrix["signals"]

    assert signals
    for signal in signals:
        assert REQUIRED_SIGNAL_FIELDS <= set(signal)
        assert signal["name"]
        assert signal["group"]
        assert signal["meaning"]
        assert signal["source_calculation"]
        assert signal["aggregation"]
        assert signal["normalization"]
        assert isinstance(signal["role_positive"], list)
        assert isinstance(signal["role_negative"], list)
        assert isinstance(signal["boundary_detection"], bool)
        assert isinstance(signal["role_scoring"], bool)
        assert signal["mvp_level"] in {"mvp", "optional"}
        assert signal["required_track_map_fields"]
        assert signal["provenance"]
        assert signal["missing_signal_behavior"]


def test_signal_groups_cover_issue_239_scope():
    matrix = _load_matrix()
    groups = {signal["group"] for signal in matrix["signals"]}

    assert REQUIRED_GROUPS <= groups


def test_role_summary_declares_positive_and_negative_signals_per_role():
    matrix = _load_matrix()
    signal_names = {signal["name"] for signal in matrix["signals"]}
    summary = matrix["role_signal_summary"]

    assert set(summary) == ALLOWED_ROLES_AND_EVENTS
    for role_or_event, mapping in summary.items():
        assert mapping["positive_signals"], role_or_event
        assert mapping["negative_signals"], role_or_event
        assert set(mapping["positive_signals"]) <= signal_names
        assert set(mapping["negative_signals"]) <= signal_names


def test_role_summary_matches_inverse_signal_view():
    matrix = _load_matrix()
    signals = matrix["signals"]
    summary = matrix["role_signal_summary"]

    for role_or_event, mapping in summary.items():
        inverse_positive = {
            signal["name"]
            for signal in signals
            if role_or_event in signal["role_positive"]
        }
        inverse_negative = {
            signal["name"]
            for signal in signals
            if role_or_event in signal["role_negative"]
        }
        assert set(mapping["positive_signals"]) == inverse_positive
        assert set(mapping["negative_signals"]) == inverse_negative


def test_role_references_are_from_allowed_vocabulary():
    matrix = _load_matrix()

    for signal in matrix["signals"]:
        referenced = set(signal["role_positive"]) | set(signal["role_negative"])
        assert referenced <= ALLOWED_ROLES_AND_EVENTS


def test_mvp_and_optional_signals_are_separated():
    matrix = _load_matrix()
    by_name = {signal["name"]: signal for signal in matrix["signals"]}

    assert set(matrix["structure_v1_mvp_minimum"]) <= set(by_name)
    assert all(
        by_name[name]["mvp_level"] == "mvp"
        for name in matrix["structure_v1_mvp_minimum"]
    )
    assert by_name["stem_drum_activity"]["mvp_level"] == "optional"
    assert by_name["stem_bass_activity"]["mvp_level"] == "optional"
    assert by_name["semantic_role_hint"]["mvp_level"] == "optional"
    assert by_name["stem_drum_activity"]["boundary_detection"] is False
    assert by_name["stem_bass_activity"]["boundary_detection"] is False
    assert by_name["semantic_role_hint"]["boundary_detection"] is False


def test_boundary_and_role_layers_remain_explicitly_separated():
    matrix = _load_matrix()
    policy_text = " ".join(matrix["separation_policy"]["forbidden"])

    assert "StructureV1 must not emit" in policy_text
    assert "drop_onset" in policy_text
    assert "universal Techno thresholds" in " ".join(
        matrix["normalization_policy"]["forbidden"]
    )
    assert any(
        signal["boundary_detection"] and signal["role_scoring"]
        for signal in matrix["signals"]
        if signal["mvp_level"] == "mvp"
    )
    assert all(
        "missing" in signal["missing_signal_behavior"].lower()
        or "nullable" in signal["missing_signal_behavior"].lower()
        or "not_run" in signal["missing_signal_behavior"]
        or "failed" in signal["missing_signal_behavior"]
        or "no_result" in signal["missing_signal_behavior"]
        for signal in matrix["signals"]
    )
