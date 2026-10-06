"""Contract tests for sample-brain.analysis-eval.v1 (#956)."""

from __future__ import annotations

import ast
import json
import math
from pathlib import Path

import pytest

from src.analysis_eval_artifact import (
    ARVP_METRIC_DEFINITION_VERSION,
    ARVP_METRIC_VALUE_VERSION,
    ARVP_OBSERVATION_VERSION,
    ARTIFACT_VERSION,
    DOCUMENT_TYPE,
    AnalysisEvalArtifactError,
    aq1_tempo_fixture,
    aq5_ranking_fixture,
    assert_portable_value,
    build_candidate,
    build_observation,
    build_record,
    canonical_json_dumps,
    fingerprint,
    map_artifact_to_arvp_observations,
    map_status_to_arvp,
    metric_definitions_from_artifact,
    serialize_artifact,
    validate_artifact,
)

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"


def test_document_identity_frozen() -> None:
    art = aq1_tempo_fixture()
    assert art["document_type"] == DOCUMENT_TYPE == "sample-brain.analysis-eval.v1"
    assert art["artifact_version"] == ARTIFACT_VERSION == "1.0.0"


def test_status_vocabulary_coverage() -> None:
    statuses = {
        obs["status"]
        for art in (aq1_tempo_fixture(), aq5_ranking_fixture())
        for record in art["records"]
        for obs in record["observations"]
    }
    # measured / unknown from AQ1; controlled_failure / not_applicable from AQ5
    assert "measured" in statuses
    assert "unknown" in statuses
    assert "controlled_failure" in statuses
    assert "not_applicable" in statuses
    # excluded via eligibility
    assert any(
        r["eligibility"]["status"] == "excluded" for r in aq1_tempo_fixture()["records"]
    )


def test_never_coerce_missing_to_zero() -> None:
    with pytest.raises(AnalysisEvalArtifactError, match="must not carry a numeric value"):
        build_observation(
            observation_id="x.unknown",
            metric_id="bpm.value",
            status="unknown",
            value=0,
            unit="bpm",
            direction="neutral",
        )
    with pytest.raises(AnalysisEvalArtifactError, match="finite numeric value"):
        build_observation(
            observation_id="x.measured",
            metric_id="bpm.value",
            status="measured",
            value=None,
            unit="bpm",
            direction="neutral",
        )


def test_reject_non_finite_measured_value() -> None:
    with pytest.raises(AnalysisEvalArtifactError):
        build_observation(
            observation_id="x.nan",
            metric_id="bpm.value",
            status="measured",
            value=float("nan"),
            unit="bpm",
            direction="minimize",
        )


def test_canonical_serialization_deterministic() -> None:
    art = aq1_tempo_fixture()
    a = serialize_artifact(art)
    b = serialize_artifact(json.loads(a))
    assert a == b
    assert '"document_type"' in a
    # allow_nan=False path: injecting NaN must fail
    dirty = json.loads(a)
    dirty["records"][0]["ground_truth"]["bpm"] = float("nan")
    with pytest.raises(AnalysisEvalArtifactError):
        serialize_artifact(dirty)


def test_privacy_rejection_absolute_path_and_username() -> None:
    with pytest.raises(AnalysisEvalArtifactError, match="absolute/private path"):
        assert_portable_value({"id": r"C:\Users\janne\private\kick.wav"}, field="x")
    with pytest.raises(AnalysisEvalArtifactError, match="sensitive key"):
        assert_portable_value({"username": "janne"}, field="x")
    with pytest.raises(AnalysisEvalArtifactError, match="absolute/private path"):
        build_candidate(
            candidate_id="bad",
            implementation_id="src.analyze",
            revision="x",
            configuration={"work_dir": "/home/janne/samples"},
        )


def test_two_domain_proof_not_tempo_only() -> None:
    aq1 = aq1_tempo_fixture()
    aq5 = aq5_ranking_fixture()
    assert aq1["records"][0]["domain"] == "aq1.tempo"
    assert aq5["records"][0]["domain"] == "aq5.ranking"
    aq1_payload_kinds = {
        type(obs.get("payload")).__name__
        for rec in aq1["records"]
        for obs in rec["observations"]
    }
    aq5_obs = aq5["records"][0]["observations"][0]
    assert isinstance(aq5_obs["payload"], dict)
    assert "ranked_ids" in aq5_obs["payload"]
    assert "scores" in aq5_obs["payload"]
    # Structural difference: ranking payload list vs scalar-only AQ1 measured value
    assert aq1["records"][0]["observations"][0]["payload"] is None
    assert isinstance(aq5_obs["payload"]["ranked_ids"], list)
    assert aq1_payload_kinds  # smoke


def test_arvp_status_mapping() -> None:
    assert map_status_to_arvp("measured") == "measured"
    assert map_status_to_arvp("unknown") == "unknown"
    assert map_status_to_arvp("not_applicable") == "not_applicable"
    assert map_status_to_arvp("controlled_failure") == "unknown"
    assert map_status_to_arvp("excluded") is None


def test_arvp_observation_field_shape() -> None:
    art = aq5_ranking_fixture()
    mapped = map_artifact_to_arvp_observations(art)
    assert mapped, "expected at least one mapped observation"
    # controlled_failure → unknown without value; measured has value; N/A has no value
    by_id = {item["observation_id"]: item for item in mapped}
    measured = by_id["aq5-query-001.overlap_at_3"]
    assert measured["contract_version"] == ARVP_OBSERVATION_VERSION
    assert measured["metric"]["contract_version"] == ARVP_METRIC_VALUE_VERSION
    assert measured["metric"]["status"] == "measured"
    assert math.isclose(float(measured["metric"]["value"]), 0.6666666666666666)
    assert "candidate_fingerprint" in measured
    assert "partition_fingerprint" in measured
    assert measured["partition_id"] == "validation-smoke"

    failure = by_id["aq5-query-001.backend_unavailable"]
    assert failure["metric"]["status"] == "unknown"
    assert "value" not in failure["metric"]

    na = by_id["aq5-query-001.not_applicable_metric"]
    assert na["metric"]["status"] == "not_applicable"
    assert "value" not in na["metric"]


def test_excluded_records_omit_arvp_observations() -> None:
    art = aq1_tempo_fixture()
    mapped = map_artifact_to_arvp_observations(art)
    assert all("excluded" not in item["observation_id"] for item in mapped)
    assert not any(
        item["observation_id"].startswith("aq1-rec-excluded") for item in mapped
    )


def test_metric_definition_shape_matches_arvp_v1() -> None:
    defs = metric_definitions_from_artifact(aq1_tempo_fixture())
    assert defs
    for item in defs:
        assert set(item) == {
            "contract_version",
            "direction",
            "metric_id",
            "required",
            "unit",
        }
        assert item["contract_version"] == ARVP_METRIC_DEFINITION_VERSION
        assert item["direction"] in {"maximize", "minimize", "neutral"}


def test_no_arvp_import_in_public_module() -> None:
    path = SRC_ROOT / "analysis_eval_artifact.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("arvp"), alias.name
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert not mod.startswith("arvp"), mod


def test_fingerprint_stable() -> None:
    cfg = {"a": 1, "b": [2, 3]}
    assert fingerprint(cfg) == fingerprint({"b": [2, 3], "a": 1})
    assert len(fingerprint(cfg)) == 64


def test_validate_rejects_path_in_record_id_area() -> None:
    art = aq1_tempo_fixture()
    art["records"][0]["ground_truth"]["note"] = "/Users/private/kick.wav"
    with pytest.raises(AnalysisEvalArtifactError, match="absolute/private path"):
        validate_artifact(art)


def test_canonical_json_roundtrip_fixtures() -> None:
    for factory in (aq1_tempo_fixture, aq5_ranking_fixture):
        art = factory()
        text = serialize_artifact(art)
        again = serialize_artifact(json.loads(text))
        assert text == again
        # Compact separators + sorted keys
        assert ", " not in text
        assert canonical_json_dumps({"z": 1, "a": 2}) == '{"a":2,"z":1}'
