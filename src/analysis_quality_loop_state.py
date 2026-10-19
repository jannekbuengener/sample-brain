"""Sample Brain analysis quality-loop supervisor state store v1 (#1097).

Persistent portable supervisor state for the bounded CALIBRATION quality loop.
Owns fresh/validate/load/atomic-save + fingerprint only — not retry policy,
orchestration, decision, or iterator composition.

Reuses #956 helpers: ``canonical_json_dumps``, ``fingerprint``,
``assert_portable_value``. Host-supplied path only. Fail-closed on corrupt or
unsupported identity — never silent fresh reset.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.analysis_automation_decision import TUNABLE_PARTITION_ROLES
from src.analysis_eval_artifact import (
    AnalysisEvalArtifactError,
    assert_portable_value,
    canonical_json_dumps,
    fingerprint,
)

DOCUMENT_TYPE = "sample-brain.analysis-quality-loop-supervisor.v1"
ARTIFACT_VERSION = "1.0.0"
SCHEMA_VERSION = 1

LOOP_STATUSES: frozenset[str] = frozenset(
    {
        "ready",
        "held",
        "frozen",
        "stopped",
        "exhausted",
        "controlled_failure",
        "retry_exhausted",
    }
)

_STATE_FP_EXCLUDED: frozenset[str] = frozenset(
    {"generated_at", "state_fingerprint", "artifact_hash"}
)


class AnalysisQualityLoopStateError(ValueError):
    """Raised when supervisor state violates the v1 store contract."""


def _wrap_portable(exc: AnalysisEvalArtifactError) -> AnalysisQualityLoopStateError:
    return AnalysisQualityLoopStateError(str(exc))


def _require_text(value: object, field: str) -> str:
    if type(value) is not str or not value.strip():
        raise AnalysisQualityLoopStateError(f"{field} must be a non-empty string")
    return value.strip()


def _require_canonical_text(value: object, field: str) -> str:
    text = _require_text(value, field)
    if value != text:
        raise AnalysisQualityLoopStateError(f"{field} must be canonical")
    return text


def _require_hex_fingerprint(value: object, field: str) -> str:
    text = _require_canonical_text(value, field)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise AnalysisQualityLoopStateError(
            f"{field} must be a lowercase sha256 hex digest"
        )
    return text


def _require_non_negative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AnalysisQualityLoopStateError(f"{field} must be a non-negative int")
    if value < 0:
        raise AnalysisQualityLoopStateError(f"{field} must be a non-negative int")
    return value


def _require_positive_int(value: object, field: str) -> int:
    number = _require_non_negative_int(value, field)
    if number < 1:
        raise AnalysisQualityLoopStateError(f"{field} must be a positive int")
    return number


def _require_candidate(value: object, field: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise AnalysisQualityLoopStateError(f"{field} must be a mapping")
    candidate_id = _require_canonical_text(value.get("candidate_id"), f"{field}.candidate_id")
    config_fp = _require_hex_fingerprint(
        value.get("config_fingerprint"), f"{field}.config_fingerprint"
    )
    allowed = {"candidate_id", "config_fingerprint"}
    extra = set(value.keys()) - allowed
    if extra:
        raise AnalysisQualityLoopStateError(
            f"{field} has unsupported keys: {sorted(extra)}"
        )
    return {"candidate_id": candidate_id, "config_fingerprint": config_fp}


def _require_partition(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise AnalysisQualityLoopStateError("partition must be a mapping")
    partition_id = _require_canonical_text(
        value.get("partition_id"), "partition.partition_id"
    )
    role = _require_canonical_text(value.get("role"), "partition.role")
    if role not in TUNABLE_PARTITION_ROLES:
        raise AnalysisQualityLoopStateError(
            f"unsupported partition role for supervisor v1: {role!r}"
        )
    return {"partition_id": partition_id, "role": role}


def _require_retry(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AnalysisQualityLoopStateError("retry must be a mapping")
    budget_initial = _require_positive_int(
        value.get("budget_initial"), "retry.budget_initial"
    )
    budget_remaining = _require_non_negative_int(
        value.get("budget_remaining"), "retry.budget_remaining"
    )
    if budget_remaining > budget_initial:
        raise AnalysisQualityLoopStateError(
            "retry.budget_remaining cannot exceed retry.budget_initial"
        )
    consecutive = _require_non_negative_int(
        value.get("consecutive_failures"), "retry.consecutive_failures"
    )
    last_failure = value.get("last_failure_class")
    if last_failure is not None:
        last_failure = _require_canonical_text(
            last_failure, "retry.last_failure_class"
        )
    return {
        "budget_initial": budget_initial,
        "budget_remaining": budget_remaining,
        "consecutive_failures": consecutive,
        "last_failure_class": last_failure,
    }


def _optional_mapping(value: object, field: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise AnalysisQualityLoopStateError(f"{field} must be a mapping or null")
    return dict(value)


def state_semantic_payload(state: Mapping[str, Any]) -> dict[str, Any]:
    """Return the portable payload used for state fingerprinting."""
    return {
        key: value
        for key, value in state.items()
        if key not in _STATE_FP_EXCLUDED
    }


def state_semantic_fingerprint(state: Mapping[str, Any]) -> str:
    """Deterministic fingerprint of the portable supervisor state."""
    try:
        return fingerprint(state_semantic_payload(state))
    except AnalysisEvalArtifactError as exc:
        raise _wrap_portable(exc) from exc


def fresh_state(
    *,
    domain: str,
    partition_id: str,
    partition_role: str,
    baseline_candidate: Mapping[str, Any],
    active_candidate: Mapping[str, Any],
    search_space_id: str,
    search_space_version: str,
    search_space_fingerprint: str,
    visited_candidate_ids: Sequence[str] | None = None,
    retry_budget: int = 3,
    max_iterations: int | None = None,
    last_known_good: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic initial ``ready`` supervisor state."""
    domain_text = _require_canonical_text(domain, "domain")
    partition = _require_partition(
        {"partition_id": partition_id, "role": partition_role}
    )
    baseline = _require_candidate(baseline_candidate, "baseline_candidate")
    active = _require_candidate(active_candidate, "active_candidate")
    space_id = _require_canonical_text(search_space_id, "search_space_id")
    space_version = _require_canonical_text(
        search_space_version, "search_space_version"
    )
    space_fp = _require_hex_fingerprint(
        search_space_fingerprint, "search_space_fingerprint"
    )
    budget = _require_positive_int(retry_budget, "retry_budget")

    if visited_candidate_ids is None:
        visited = [active["candidate_id"]]
    else:
        if not isinstance(visited_candidate_ids, Sequence) or isinstance(
            visited_candidate_ids, (str, bytes)
        ):
            raise AnalysisQualityLoopStateError(
                "visited_candidate_ids must be a sequence"
            )
        visited = [
            _require_canonical_text(item, "visited_candidate_ids[]")
            for item in visited_candidate_ids
        ]
    if not visited:
        raise AnalysisQualityLoopStateError(
            "visited_candidate_ids must be non-empty for fresh state"
        )
    if active["candidate_id"] not in visited:
        raise AnalysisQualityLoopStateError(
            "active candidate must appear in visited_candidate_ids"
        )

    max_iter: int | None
    if max_iterations is None:
        max_iter = None
    else:
        max_iter = _require_positive_int(max_iterations, "max_iterations")

    known_good = (
        None
        if last_known_good is None
        else _require_candidate(last_known_good, "last_known_good")
    )

    state: dict[str, Any] = {
        "document_type": DOCUMENT_TYPE,
        "artifact_version": ARTIFACT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "domain": domain_text,
        "partition": partition,
        "baseline_candidate": baseline,
        "active_candidate": active,
        "last_known_good": known_good,
        "visited_candidate_ids": visited,
        "search_space_id": space_id,
        "search_space_version": space_version,
        "search_space_fingerprint": space_fp,
        "iteration_index": 0,
        "max_iterations": max_iter,
        "loop_status": "ready",
        "last_decision": None,
        "last_orchestration_ref": None,
        "last_iterator_ref": None,
        "history_refs": [],
        "retry": {
            "budget_initial": budget,
            "budget_remaining": budget,
            "consecutive_failures": 0,
            "last_failure_class": None,
        },
        "generation": 0,
        "production_authorized": False,
    }
    return validate_state(state)


def validate_state(state: Mapping[str, Any]) -> dict[str, Any]:
    """Validate supervisor state and attach/verify ``state_fingerprint``."""
    if not isinstance(state, Mapping):
        raise AnalysisQualityLoopStateError("state must be a mapping")

    if state.get("document_type") != DOCUMENT_TYPE:
        raise AnalysisQualityLoopStateError(
            f"unsupported document_type: {state.get('document_type')!r}"
        )
    if state.get("artifact_version") != ARTIFACT_VERSION:
        raise AnalysisQualityLoopStateError(
            f"unsupported artifact_version: {state.get('artifact_version')!r}"
        )
    if state.get("schema_version") != SCHEMA_VERSION:
        raise AnalysisQualityLoopStateError(
            f"unsupported schema_version: {state.get('schema_version')!r}"
        )

    copy_state = dict(state)
    if "running" in copy_state:
        raise AnalysisQualityLoopStateError(
            "persisted supervisor state must not include running"
        )

    domain = _require_canonical_text(copy_state.get("domain"), "domain")
    partition = _require_partition(copy_state.get("partition"))
    baseline = _require_candidate(
        copy_state.get("baseline_candidate"), "baseline_candidate"
    )
    active = _require_candidate(
        copy_state.get("active_candidate"), "active_candidate"
    )
    known_good_raw = copy_state.get("last_known_good")
    known_good = (
        None
        if known_good_raw is None
        else _require_candidate(known_good_raw, "last_known_good")
    )

    visited_raw = copy_state.get("visited_candidate_ids")
    if not isinstance(visited_raw, Sequence) or isinstance(
        visited_raw, (str, bytes)
    ):
        raise AnalysisQualityLoopStateError(
            "visited_candidate_ids must be a sequence"
        )
    visited = [
        _require_canonical_text(item, "visited_candidate_ids[]")
        for item in visited_raw
    ]
    if active["candidate_id"] not in visited:
        raise AnalysisQualityLoopStateError(
            "active candidate must appear in visited_candidate_ids"
        )

    space_id = _require_canonical_text(
        copy_state.get("search_space_id"), "search_space_id"
    )
    space_version = _require_canonical_text(
        copy_state.get("search_space_version"), "search_space_version"
    )
    space_fp = _require_hex_fingerprint(
        copy_state.get("search_space_fingerprint"), "search_space_fingerprint"
    )
    iteration_index = _require_non_negative_int(
        copy_state.get("iteration_index"), "iteration_index"
    )
    max_iterations = copy_state.get("max_iterations")
    if max_iterations is not None:
        max_iterations = _require_positive_int(max_iterations, "max_iterations")

    loop_status = _require_canonical_text(
        copy_state.get("loop_status"), "loop_status"
    )
    if loop_status not in LOOP_STATUSES:
        raise AnalysisQualityLoopStateError(
            f"unsupported loop_status: {loop_status!r}"
        )

    last_decision = _optional_mapping(
        copy_state.get("last_decision"), "last_decision"
    )
    last_orch = _optional_mapping(
        copy_state.get("last_orchestration_ref"), "last_orchestration_ref"
    )
    last_iter = _optional_mapping(
        copy_state.get("last_iterator_ref"), "last_iterator_ref"
    )
    if last_orch is not None:
        _require_hex_fingerprint(
            last_orch.get("outcome_fingerprint"),
            "last_orchestration_ref.outcome_fingerprint",
        )
    if last_decision is not None:
        _require_canonical_text(
            last_decision.get("next_action"), "last_decision.next_action"
        )
        _require_canonical_text(
            last_decision.get("decision_status"), "last_decision.decision_status"
        )
        token = last_decision.get("decision_token")
        if token is not None:
            _require_canonical_text(token, "last_decision.decision_token")
        dec_fp = last_decision.get("decision_fingerprint")
        if dec_fp is not None:
            _require_hex_fingerprint(dec_fp, "last_decision.decision_fingerprint")

    history_raw = copy_state.get("history_refs", [])
    if history_raw is None:
        history_raw = []
    if not isinstance(history_raw, Sequence) or isinstance(
        history_raw, (str, bytes)
    ):
        raise AnalysisQualityLoopStateError("history_refs must be a sequence")
    history_refs: list[Any] = []
    for index, item in enumerate(history_raw):
        if isinstance(item, str):
            history_refs.append(
                _require_hex_fingerprint(item, f"history_refs[{index}]")
            )
        elif isinstance(item, Mapping):
            try:
                assert_portable_value(item, field=f"history_refs[{index}]")
            except AnalysisEvalArtifactError as exc:
                raise _wrap_portable(exc) from exc
            history_refs.append(dict(item))
        else:
            raise AnalysisQualityLoopStateError(
                f"history_refs[{index}] must be a fingerprint or portable mapping"
            )

    retry = _require_retry(copy_state.get("retry"))
    generation = _require_non_negative_int(
        copy_state.get("generation"), "generation"
    )
    if copy_state.get("production_authorized") is not False:
        raise AnalysisQualityLoopStateError(
            "production_authorized must be false"
        )

    normalized: dict[str, Any] = {
        "document_type": DOCUMENT_TYPE,
        "artifact_version": ARTIFACT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "domain": domain,
        "partition": partition,
        "baseline_candidate": baseline,
        "active_candidate": active,
        "last_known_good": known_good,
        "visited_candidate_ids": visited,
        "search_space_id": space_id,
        "search_space_version": space_version,
        "search_space_fingerprint": space_fp,
        "iteration_index": iteration_index,
        "max_iterations": max_iterations,
        "loop_status": loop_status,
        "last_decision": last_decision,
        "last_orchestration_ref": last_orch,
        "last_iterator_ref": last_iter,
        "history_refs": history_refs,
        "retry": retry,
        "generation": generation,
        "production_authorized": False,
    }

    try:
        assert_portable_value(normalized, field="state")
        canonical_json_dumps(normalized)
    except AnalysisEvalArtifactError as exc:
        raise _wrap_portable(exc) from exc

    expected_fp = state_semantic_fingerprint(normalized)
    attached = copy_state.get("state_fingerprint")
    if attached is None:
        normalized["state_fingerprint"] = expected_fp
    else:
        attached_fp = _require_hex_fingerprint(attached, "state_fingerprint")
        if attached_fp != expected_fp:
            raise AnalysisQualityLoopStateError(
                "state_fingerprint does not match semantic payload"
            )
        normalized["state_fingerprint"] = attached_fp

    return json.loads(canonical_json_dumps(normalized))


def load_state(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Load and validate supervisor state from a host-supplied path.

    Corrupt or unsupported content fails closed. Never silently returns fresh
    state.
    """
    state_path = Path(path)
    try:
        raw = state_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise AnalysisQualityLoopStateError(
            f"failed to read supervisor state: {exc}"
        ) from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AnalysisQualityLoopStateError(
            f"corrupt supervisor state: invalid JSON ({exc})"
        ) from exc
    if not isinstance(payload, Mapping):
        raise AnalysisQualityLoopStateError(
            "corrupt supervisor state: root must be a mapping"
        )
    try:
        return validate_state(payload)
    except AnalysisQualityLoopStateError:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise AnalysisQualityLoopStateError(
            f"corrupt supervisor state: {exc}"
        ) from exc


def save_state_atomic(
    path: str | os.PathLike[str], state: Mapping[str, Any]
) -> dict[str, Any]:
    """Atomically persist validated supervisor state to a host-supplied path.

    Sequence: mkstemp in the destination directory → write → flush → fsync →
    ``os.replace``.
    """
    validated = validate_state(state)
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_dumps(validated)
    fd: int | None = None
    tmp_name: str | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{dest.name}.",
            suffix=".tmp",
            dir=str(dest.parent),
        )
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            fd = None  # ownership transferred to file object
            handle.write(payload)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, dest)
        tmp_name = None
    except AnalysisQualityLoopStateError:
        raise
    except OSError as exc:
        raise AnalysisQualityLoopStateError(
            f"atomic supervisor state write failed: {exc}"
        ) from exc
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if tmp_name is not None:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
    return validated


__all__ = [
    "ARTIFACT_VERSION",
    "DOCUMENT_TYPE",
    "LOOP_STATUSES",
    "SCHEMA_VERSION",
    "AnalysisQualityLoopStateError",
    "fresh_state",
    "load_state",
    "save_state_atomic",
    "state_semantic_fingerprint",
    "state_semantic_payload",
    "validate_state",
]
