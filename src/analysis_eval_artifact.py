"""Sample Brain analysis-eval artifact v1 (#956).

Portable envelope + structural ARVP #7 mapping helpers.
No runtime ``import arvp``.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Literal, Mapping, Sequence

DOCUMENT_TYPE = "sample-brain.analysis-eval.v1"
ARTIFACT_VERSION = "1.0.0"
PRODUCER_ID = "sample-brain.analysis-eval"

ObservationStatus = Literal[
    "measured",
    "unknown",
    "not_applicable",
    "controlled_failure",
    "excluded",
]
PartitionRole = Literal[
    "development",
    "calibration",
    "validation",
    "test",
    "external_check",
]
MetricDirection = Literal["maximize", "minimize", "neutral"]

OBSERVATION_STATUSES: frozenset[str] = frozenset(
    {
        "measured",
        "unknown",
        "not_applicable",
        "controlled_failure",
        "excluded",
    }
)
PARTITION_ROLES: frozenset[str] = frozenset(
    {
        "development",
        "calibration",
        "validation",
        "test",
        "external_check",
    }
)
METRIC_DIRECTIONS: frozenset[str] = frozenset({"maximize", "minimize", "neutral"})

# ARVP #7 contract version tokens (structural compatibility; no import).
ARVP_METRIC_DEFINITION_VERSION = "arvp.metric-definition.v1"
ARVP_METRIC_CONTRACT_VERSION = "arvp.metric-contract.v1"
ARVP_METRIC_VALUE_VERSION = "arvp.metric-value.v1"
ARVP_OBSERVATION_VERSION = "arvp.observation.v1"

_METRIC_ID_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_OBSERVATION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_PRIVATE_PATH = re.compile(
    r"(?:^[A-Za-z]:[\\/]|^\\\\|^/(?:home|Users|root|mnt|Volumes|tmp)/)",
    re.IGNORECASE,
)
_SECRET_VALUE = re.compile(r"(?i)(?:api[_-]?key|token|secret)\s*[:=]\s*\S+")
_SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "audio_path",
        "device_id",
        "device_name",
        "file_path",
        "host",
        "hostname",
        "machine",
        "machine_name",
        "sample_path",
        "secret",
        "token",
        "user",
        "user_name",
        "username",
    }
)

# SB status → ARVP MetricValueStatus (controlled_failure collapses to unknown).
ARVP_STATUS_MAP: dict[str, str | None] = {
    "measured": "measured",
    "unknown": "unknown",
    "not_applicable": "not_applicable",
    "controlled_failure": "unknown",
    "excluded": None,  # no ARVP Observation
}


class AnalysisEvalArtifactError(ValueError):
    """Raised when an analysis-eval artifact violates the v1 contract."""


def canonical_json_dumps(value: Any) -> str:
    """Deterministic JSON with fail-closed non-finite handling."""
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise AnalysisEvalArtifactError(f"canonical serialization failed: {exc}") from exc


def fingerprint(value: Any) -> str:
    """SHA-256 hex of canonical JSON bytes."""
    return hashlib.sha256(canonical_json_dumps(value).encode("utf-8")).hexdigest()


def _require_text(value: object, field: str) -> str:
    if type(value) is not str or not value.strip():
        raise AnalysisEvalArtifactError(f"{field} must be a non-empty string")
    return value.strip()


def _require_metric_id(value: object) -> str:
    text = _require_text(value, "metric_id")
    if _METRIC_ID_RE.fullmatch(text) is None:
        raise AnalysisEvalArtifactError(
            "metric_id must match ^[a-z][a-z0-9_.-]{0,63}$"
        )
    return text


def _require_observation_id(value: object) -> str:
    text = _require_text(value, "observation_id")
    if _OBSERVATION_ID_RE.fullmatch(text) is None:
        raise AnalysisEvalArtifactError(
            "observation_id must match ^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
        )
    return text


def _is_finite_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(value)


def assert_portable_value(value: Any, *, field: str = "root") -> None:
    """Reject absolute paths, secrets, sensitive keys, and non-JSON-safe objects."""
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, str):
        if _PRIVATE_PATH.search(value):
            raise AnalysisEvalArtifactError(
                f"{field}: absolute/private path is forbidden"
            )
        if _SECRET_VALUE.search(value):
            raise AnalysisEvalArtifactError(f"{field}: secret-like value is forbidden")
        return
    if isinstance(value, (int, float)):
        if isinstance(value, bool):
            return
        if not math.isfinite(value):
            raise AnalysisEvalArtifactError(f"{field}: non-finite number is forbidden")
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise AnalysisEvalArtifactError(f"{field}: mapping keys must be str")
            if key.lower() in _SENSITIVE_KEYS:
                raise AnalysisEvalArtifactError(
                    f"{field}.{key}: sensitive key is forbidden"
                )
            assert_portable_value(child, field=f"{field}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            assert_portable_value(child, field=f"{field}[{index}]")
        return
    raise AnalysisEvalArtifactError(
        f"{field}: unsupported type {type(value).__name__} for portable artifact"
    )


def build_candidate(
    *,
    candidate_id: str,
    implementation_id: str,
    revision: str,
    configuration: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a portable candidate identity with config fingerprint."""
    config = dict(configuration)
    assert_portable_value(config, field="candidate.configuration")
    return {
        "candidate_id": _require_text(candidate_id, "candidate_id"),
        "implementation_id": _require_text(implementation_id, "implementation_id"),
        "revision": _require_text(revision, "revision"),
        "configuration": config,
        "config_fingerprint": fingerprint(config),
    }


def build_observation(
    *,
    observation_id: str,
    metric_id: str,
    status: str,
    unit: str,
    direction: str,
    value: float | int | None = None,
    payload: Mapping[str, Any] | None = None,
    failure_code: str | None = None,
) -> dict[str, Any]:
    """Build one observation dict under the SB status vocabulary."""
    if status not in OBSERVATION_STATUSES:
        raise AnalysisEvalArtifactError(f"unsupported observation status: {status}")
    if direction not in METRIC_DIRECTIONS:
        raise AnalysisEvalArtifactError(f"unsupported metric direction: {direction}")
    obs: dict[str, Any] = {
        "observation_id": _require_observation_id(observation_id),
        "metric_id": _require_metric_id(metric_id),
        "status": status,
        "unit": _require_text(unit, "unit"),
        "direction": direction,
        "value": None,
        "payload": None,
    }
    if status == "measured":
        if value is None or not _is_finite_number(value):
            raise AnalysisEvalArtifactError(
                "measured observations require a finite numeric value"
            )
        obs["value"] = value
    else:
        if value is not None:
            raise AnalysisEvalArtifactError(
                f"{status} observations must not carry a numeric value "
                "(never coerce missing/invalid to zero)"
            )
    if payload is not None:
        assert_portable_value(payload, field="observation.payload")
        obs["payload"] = dict(payload)
    if failure_code is not None:
        if status != "controlled_failure":
            raise AnalysisEvalArtifactError(
                "failure_code is only valid for controlled_failure"
            )
        obs["failure_code"] = _require_text(failure_code, "failure_code")
    return obs


def build_record(
    *,
    record_id: str,
    domain: str,
    eligibility: Mapping[str, Any],
    ground_truth: Mapping[str, Any] | None = None,
    observations: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build one record with eligibility and observations."""
    elig = dict(eligibility)
    status = elig.get("status")
    if status not in {"eligible", "excluded"}:
        raise AnalysisEvalArtifactError(
            "eligibility.status must be eligible or excluded"
        )
    if status == "excluded" and not str(elig.get("reason") or "").strip():
        raise AnalysisEvalArtifactError("excluded eligibility requires reason")
    assert_portable_value(elig, field="eligibility")
    gt = dict(ground_truth or {})
    assert_portable_value(gt, field="ground_truth")
    obs_list = [dict(item) for item in (observations or ())]
    if status == "excluded" and obs_list:
        raise AnalysisEvalArtifactError(
            "excluded records must not carry ARVP-bound observations"
        )
    for item in obs_list:
        # Re-validate via builder to enforce status/value rules.
        build_observation(
            observation_id=item["observation_id"],
            metric_id=item["metric_id"],
            status=item["status"],
            unit=item["unit"],
            direction=item["direction"],
            value=item.get("value"),
            payload=item.get("payload"),
            failure_code=item.get("failure_code"),
        )
    return {
        "record_id": _require_text(record_id, "record_id"),
        "domain": _require_text(domain, "domain"),
        "eligibility": elig,
        "ground_truth": gt,
        "observations": obs_list,
    }


def build_artifact(
    *,
    benchmark_id: str,
    dataset_id: str,
    dataset_member_ids: Sequence[str],
    partition_id: str,
    partition_role: str,
    candidate: Mapping[str, Any],
    source_benchmark_version: str,
    run_id: str,
    records: Sequence[Mapping[str, Any]],
    source_origin: str = "synthetic-public",
) -> dict[str, Any]:
    """Assemble a complete analysis-eval v1 artifact."""
    if partition_role not in PARTITION_ROLES:
        raise AnalysisEvalArtifactError(f"unsupported partition role: {partition_role}")
    members = [_require_text(item, "dataset_member_ids[]") for item in dataset_member_ids]
    dataset_fp = fingerprint({"dataset_id": dataset_id, "members": sorted(members)})
    cand = dict(candidate)
    for key in (
        "candidate_id",
        "implementation_id",
        "revision",
        "configuration",
        "config_fingerprint",
    ):
        if key not in cand:
            raise AnalysisEvalArtifactError(f"candidate missing {key}")
    assert_portable_value(cand, field="candidate")
    artifact = {
        "document_type": DOCUMENT_TYPE,
        "artifact_version": ARTIFACT_VERSION,
        "benchmark": {
            "benchmark_id": _require_text(benchmark_id, "benchmark_id"),
            "dataset_id": _require_text(dataset_id, "dataset_id"),
            "dataset_content_fingerprint": dataset_fp,
        },
        "partition": {
            "partition_id": _require_text(partition_id, "partition_id"),
            "role": partition_role,
        },
        "candidate": cand,
        "provenance": {
            "source_benchmark": {
                "benchmark_id": _require_text(benchmark_id, "benchmark_id"),
                "benchmark_version": _require_text(
                    source_benchmark_version, "source_benchmark_version"
                ),
                "origin": _require_text(source_origin, "source_origin"),
            },
            "run": {
                "run_id": _require_text(run_id, "run_id"),
                "producer": PRODUCER_ID,
                "producer_version": ARTIFACT_VERSION,
            },
        },
        "records": [dict(record) for record in records],
    }
    validate_artifact(artifact)
    return artifact


def validate_artifact(artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Validate envelope invariants and portability; return a plain dict copy."""
    if not isinstance(artifact, Mapping):
        raise AnalysisEvalArtifactError("artifact must be a mapping")
    if artifact.get("document_type") != DOCUMENT_TYPE:
        raise AnalysisEvalArtifactError(
            f"document_type must be {DOCUMENT_TYPE!r}"
        )
    if artifact.get("artifact_version") != ARTIFACT_VERSION:
        raise AnalysisEvalArtifactError(
            f"artifact_version must be {ARTIFACT_VERSION!r}"
        )
    assert_portable_value(artifact, field="artifact")
    # Force canonical serialization (rejects NaN even if somehow present).
    canonical_json_dumps(dict(artifact))
    partition = artifact.get("partition")
    if not isinstance(partition, Mapping) or partition.get("role") not in PARTITION_ROLES:
        raise AnalysisEvalArtifactError("partition.role invalid")
    records = artifact.get("records")
    if not isinstance(records, list):
        raise AnalysisEvalArtifactError("records must be a list")
    seen_obs: set[str] = set()
    for record in records:
        if not isinstance(record, Mapping):
            raise AnalysisEvalArtifactError("record must be a mapping")
        elig = record.get("eligibility")
        if not isinstance(elig, Mapping):
            raise AnalysisEvalArtifactError("record.eligibility must be a mapping")
        elig_status = elig.get("status")
        observations = record.get("observations")
        if not isinstance(observations, list):
            raise AnalysisEvalArtifactError("record.observations must be a list")
        if elig_status == "excluded" and observations:
            raise AnalysisEvalArtifactError(
                "excluded records must not carry observations"
            )
        for obs in observations:
            if not isinstance(obs, Mapping):
                raise AnalysisEvalArtifactError("observation must be a mapping")
            status = obs.get("status")
            if status not in OBSERVATION_STATUSES:
                raise AnalysisEvalArtifactError(f"bad observation status: {status}")
            oid = _require_observation_id(obs.get("observation_id"))
            if oid in seen_obs:
                raise AnalysisEvalArtifactError(f"duplicate observation_id: {oid}")
            seen_obs.add(oid)
            _require_metric_id(obs.get("metric_id"))
            if obs.get("direction") not in METRIC_DIRECTIONS:
                raise AnalysisEvalArtifactError("observation.direction invalid")
            value = obs.get("value")
            if status == "measured":
                if value is None or not _is_finite_number(value):
                    raise AnalysisEvalArtifactError(
                        "measured observation requires finite value"
                    )
            elif value is not None:
                raise AnalysisEvalArtifactError(
                    f"{status} observation must not carry a numeric value"
                )
    return json.loads(canonical_json_dumps(dict(artifact)))


def serialize_artifact(artifact: Mapping[str, Any]) -> str:
    """Return canonical JSON for a validated artifact."""
    validated = validate_artifact(artifact)
    return canonical_json_dumps(validated)


def map_status_to_arvp(status: str) -> str | None:
    """Map SB observation status to ARVP MetricValueStatus or None if omitted."""
    if status not in ARVP_STATUS_MAP:
        raise AnalysisEvalArtifactError(f"unsupported status for ARVP mapping: {status}")
    return ARVP_STATUS_MAP[status]


def metric_definitions_from_artifact(
    artifact: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Derive unique ARVP MetricDefinition-shaped dicts from artifact observations."""
    validated = validate_artifact(artifact)
    defs: dict[str, dict[str, Any]] = {}
    for record in validated["records"]:
        for obs in record["observations"]:
            if obs["status"] == "excluded":
                continue
            mid = obs["metric_id"]
            if mid in defs:
                existing = defs[mid]
                if (
                    existing["unit"] != obs["unit"]
                    or existing["direction"] != obs["direction"]
                ):
                    raise AnalysisEvalArtifactError(
                        f"conflicting metric definition for {mid}"
                    )
                continue
            defs[mid] = {
                "contract_version": ARVP_METRIC_DEFINITION_VERSION,
                "metric_id": mid,
                "direction": obs["direction"],
                "unit": obs["unit"],
                "required": False,
            }
    return [defs[key] for key in sorted(defs)]


def metric_contract_fingerprint(definitions: Sequence[Mapping[str, Any]]) -> str:
    """Fingerprint matching ARVP MetricContract.to_dict shape (sorted by metric_id)."""
    payload = {
        "contract_version": ARVP_METRIC_CONTRACT_VERSION,
        "definitions": [dict(item) for item in sorted(definitions, key=lambda d: d["metric_id"])],
    }
    return fingerprint(payload)


def map_observation_to_arvp_dict(
    *,
    artifact: Mapping[str, Any],
    record: Mapping[str, Any],
    observation: Mapping[str, Any],
    candidate_fingerprint: str,
    partition_fingerprint: str,
    metric_contract_fp: str,
) -> dict[str, Any] | None:
    """Map one SB observation to an ARVP Observation ``to_dict``-compatible shape.

    Returns ``None`` when the observation/record must not enter ARVP (excluded).
    Pure structural mapping — does not import arvp.
    """
    validated_artifact = validate_artifact(artifact)
    _ = validated_artifact  # envelope already checked
    elig = record.get("eligibility") or {}
    if elig.get("status") == "excluded":
        return None
    arvp_status = map_status_to_arvp(str(observation["status"]))
    if arvp_status is None:
        return None
    metric: dict[str, Any] = {
        "contract_version": ARVP_METRIC_VALUE_VERSION,
        "metric_contract_fingerprint": metric_contract_fp,
        "metric_id": observation["metric_id"],
        "status": arvp_status,
    }
    if arvp_status == "measured":
        metric["value"] = observation["value"]
    return {
        "candidate_fingerprint": candidate_fingerprint,
        "contract_version": ARVP_OBSERVATION_VERSION,
        "metric": metric,
        "observation_id": observation["observation_id"],
        "partition_fingerprint": partition_fingerprint,
        "partition_id": artifact["partition"]["partition_id"],
    }


def map_artifact_to_arvp_observations(
    artifact: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Map all eligible SB observations to ARVP Observation-shaped dicts."""
    validated = validate_artifact(artifact)
    definitions = metric_definitions_from_artifact(validated)
    contract_fp = metric_contract_fingerprint(definitions) if definitions else ""
    candidate_fp = fingerprint(
        {
            "candidate_id": validated["candidate"]["candidate_id"],
            "configuration": validated["candidate"]["configuration"],
            "contract_version": "arvp.candidate.v1",
            "implementation_id": validated["candidate"]["implementation_id"],
            "revision": validated["candidate"]["revision"],
        }
    )
    partition_fp = fingerprint(
        {
            "content_identity": {
                "dataset_id": validated["benchmark"]["dataset_id"],
                "dataset_content_fingerprint": validated["benchmark"][
                    "dataset_content_fingerprint"
                ],
            },
            "contract_version": "arvp.evaluation-partition.v1",
            "partition_id": validated["partition"]["partition_id"],
            "role": validated["partition"]["role"],
        }
    )
    mapped: list[dict[str, Any]] = []
    for record in validated["records"]:
        for obs in record["observations"]:
            item = map_observation_to_arvp_dict(
                artifact=validated,
                record=record,
                observation=obs,
                candidate_fingerprint=candidate_fp,
                partition_fingerprint=partition_fp,
                metric_contract_fp=contract_fp,
            )
            if item is not None:
                mapped.append(item)
    return mapped


def aq1_tempo_fixture() -> dict[str, Any]:
    """Synthetic AQ1-style scalar/timing proof fixture."""
    candidate = build_candidate(
        candidate_id="sample-brain.analyze.bpm.baseline",
        implementation_id="src.analyze",
        revision="contract-fixture",
        configuration={"domain": "aq1.tempo", "profile": "baseline"},
    )
    records = [
        build_record(
            record_id="aq1-rec-001",
            domain="aq1.tempo",
            eligibility={"status": "eligible"},
            ground_truth={"bpm": 120.0},
            observations=[
                build_observation(
                    observation_id="aq1-rec-001.bpm.abs_error",
                    metric_id="bpm.abs_error",
                    status="measured",
                    value=0.5,
                    unit="bpm",
                    direction="minimize",
                ),
                build_observation(
                    observation_id="aq1-rec-001.bpm.missing",
                    metric_id="bpm.confidence",
                    status="unknown",
                    unit="ratio",
                    direction="maximize",
                ),
            ],
        ),
        build_record(
            record_id="aq1-rec-excluded",
            domain="aq1.tempo",
            eligibility={"status": "excluded", "reason": "duration_below_min"},
            ground_truth={},
            observations=[],
        ),
    ]
    return build_artifact(
        benchmark_id="synthetic.aq1.tempo.smoke",
        dataset_id="synthetic.aq1.tempo.v1",
        dataset_member_ids=["aq1-rec-001", "aq1-rec-excluded"],
        partition_id="validation-smoke",
        partition_role="validation",
        candidate=candidate,
        source_benchmark_version="1.0.0",
        run_id="run-aq1-synthetic-001",
        records=records,
    )


def aq5_ranking_fixture() -> dict[str, Any]:
    """Synthetic AQ5-style event/ranking proof fixture."""
    candidate = build_candidate(
        candidate_id="sample-brain.search.ranking.baseline",
        implementation_id="src.search",
        revision="contract-fixture",
        configuration={"domain": "aq5.ranking", "topk": 3},
    )
    records = [
        build_record(
            record_id="aq5-query-001",
            domain="aq5.ranking",
            eligibility={"status": "eligible"},
            ground_truth={"relevant_ids": ["hit-a", "hit-c"]},
            observations=[
                build_observation(
                    observation_id="aq5-query-001.overlap_at_3",
                    metric_id="ranking.overlap_at_k",
                    status="measured",
                    value=0.6666666666666666,
                    unit="ratio",
                    direction="maximize",
                    payload={
                        "k": 3,
                        "ranked_ids": ["hit-a", "hit-b", "hit-c"],
                        "scores": [0.91, 0.44, 0.33],
                    },
                ),
                build_observation(
                    observation_id="aq5-query-001.backend_unavailable",
                    metric_id="ranking.backend_latency_ms",
                    status="controlled_failure",
                    unit="ms",
                    direction="minimize",
                    failure_code="optional_backend_unavailable",
                ),
                build_observation(
                    observation_id="aq5-query-001.not_applicable_metric",
                    metric_id="ranking.harmonic_bonus",
                    status="not_applicable",
                    unit="ratio",
                    direction="maximize",
                ),
            ],
        )
    ]
    return build_artifact(
        benchmark_id="synthetic.aq5.ranking.smoke",
        dataset_id="synthetic.aq5.ranking.v1",
        dataset_member_ids=["aq5-query-001"],
        partition_id="validation-smoke",
        partition_role="validation",
        candidate=candidate,
        source_benchmark_version="1.0.0",
        run_id="run-aq5-synthetic-001",
        records=records,
    )
