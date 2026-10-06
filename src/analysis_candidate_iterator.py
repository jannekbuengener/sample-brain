"""Sample Brain analysis candidate-iterator contract v1 (#1064 W0).

Single-shot bounded CALIBRATION candidate/config iterator:

    next_action + partition + domain search-space + iterator state
      → validate / partition firewall
      → deterministic next-candidate selection (domain declaration order)
      → portable iterator result (advance | freeze | stop | hold |
        controlled_failure | exhausted)

Reuses #956 fingerprint / portability helpers and #1043 next_action /
tunable-partition vocabulary. No ``import arvp``. No second decision schema.
No domain candidate definitions in the shared layer.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from src.analysis_automation_decision import (
    NEXT_ACTIONS,
    TUNABLE_PARTITION_ROLES,
    TUNING_NEXT_ACTIONS,
)
from src.analysis_eval_artifact import (
    AnalysisEvalArtifactError,
    assert_portable_value,
    fingerprint,
)

DOCUMENT_TYPE = "sample-brain.analysis-candidate-iterator.v1"
ARTIFACT_VERSION = "1.0.0"
PRODUCER_ID = "sample-brain.analysis-candidate-iterator"

IteratorEffect = str  # advance|freeze|stop|hold|controlled_failure|exhausted

ITERATOR_EFFECTS: frozenset[str] = frozenset(
    {
        "advance",
        "freeze",
        "stop",
        "hold",
        "controlled_failure",
        "exhausted",
    }
)

_RESULT_FP_EXCLUDED: frozenset[str] = frozenset(
    {"generated_at", "result_fingerprint", "artifact_hash"}
)

_TERMINAL_ACTION_EFFECT: Mapping[str, str] = {
    "freeze_candidate": "freeze",
    "keep_baseline_and_stop": "stop",
    "defer_for_evidence": "hold",
    "require_human_governance": "stop",
    "stop_controlled_failure": "controlled_failure",
}


class AnalysisCandidateIteratorError(ValueError):
    """Raised when an iterator request/result violates the v1 contract."""


def _wrap_portable(exc: AnalysisEvalArtifactError) -> AnalysisCandidateIteratorError:
    return AnalysisCandidateIteratorError(str(exc))


def _require_text(value: object, field: str) -> str:
    if type(value) is not str or not value.strip():
        raise AnalysisCandidateIteratorError(f"{field} must be a non-empty string")
    return value.strip()


def _require_hex_fingerprint(value: object, field: str) -> str:
    text = _require_text(value, field)
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise AnalysisCandidateIteratorError(
            f"{field} must be a lowercase sha256 hex digest"
        )
    return text


def _require_non_negative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AnalysisCandidateIteratorError(f"{field} must be a non-negative int")
    if value < 0:
        raise AnalysisCandidateIteratorError(f"{field} must be a non-negative int")
    return value


@runtime_checkable
class SearchSpaceProvider(Protocol):
    """Domain-owned finite ordered search-space provider Protocol."""

    @property
    def search_space_id(self) -> str: ...

    @property
    def search_space_version(self) -> str: ...

    def ordered_members(self) -> Sequence[Mapping[str, str]]: ...

    def search_space_fingerprint(self) -> str: ...


class StaticSearchSpaceProvider:
    """Test/host helper: freeze an ordered finite candidate/config declaration."""

    def __init__(
        self,
        *,
        search_space_id: str,
        search_space_version: str,
        ordered_members: Sequence[Mapping[str, str]],
    ) -> None:
        self._search_space_id = _require_text(search_space_id, "search_space_id")
        self._search_space_version = _require_text(
            search_space_version, "search_space_version"
        )
        self._ordered_members = _normalize_members(ordered_members)

    @property
    def search_space_id(self) -> str:
        return self._search_space_id

    @property
    def search_space_version(self) -> str:
        return self._search_space_version

    def ordered_members(self) -> list[dict[str, str]]:
        return [dict(item) for item in self._ordered_members]

    def search_space_fingerprint(self) -> str:
        return search_space_fingerprint(
            search_space_id=self._search_space_id,
            search_space_version=self._search_space_version,
            ordered_members=self._ordered_members,
        )


def search_space_fingerprint(
    *,
    search_space_id: str,
    search_space_version: str,
    ordered_members: Sequence[Mapping[str, str]],
) -> str:
    """Deterministic fingerprint over search-space identity + declaration order."""
    members = _normalize_members(ordered_members)
    try:
        return fingerprint(
            {
                "search_space_id": _require_text(search_space_id, "search_space_id"),
                "search_space_version": _require_text(
                    search_space_version, "search_space_version"
                ),
                "ordered_members": members,
            }
        )
    except AnalysisEvalArtifactError as exc:
        raise _wrap_portable(exc) from exc


# Alias so iterate_candidates' search_space_fingerprint parameter cannot shadow it.
_compute_search_space_fingerprint = search_space_fingerprint


def _normalize_members(
    ordered_members: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    if not isinstance(ordered_members, Sequence) or isinstance(
        ordered_members, (str, bytes)
    ):
        raise AnalysisCandidateIteratorError("ordered_members must be a sequence")
    if not ordered_members:
        raise AnalysisCandidateIteratorError("ordered_members must be non-empty")

    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, raw in enumerate(ordered_members):
        if not isinstance(raw, Mapping):
            raise AnalysisCandidateIteratorError(
                f"ordered_members[{index}] must be a mapping"
            )
        candidate_id = _require_text(raw.get("candidate_id"), "candidate_id")
        config_fp = _require_hex_fingerprint(
            raw.get("config_fingerprint"), "config_fingerprint"
        )
        if candidate_id in seen:
            raise AnalysisCandidateIteratorError(
                f"duplicate candidate_id in search space: {candidate_id!r}"
            )
        seen.add(candidate_id)
        normalized.append(
            {
                "candidate_id": candidate_id,
                "config_fingerprint": config_fp,
            }
        )
    return normalized


def _member_index(
    members: Sequence[Mapping[str, str]],
) -> dict[str, Mapping[str, str]]:
    return {str(item["candidate_id"]): item for item in members}


def _assert_partition_firewall(*, partition_role: str, next_action: str) -> None:
    if partition_role not in (
        "development",
        "calibration",
        "validation",
        "test",
        "external_check",
        "holdout",
    ):
        raise AnalysisCandidateIteratorError(
            f"unsupported partition role: {partition_role}"
        )
    if (
        next_action in TUNING_NEXT_ACTIONS
        and partition_role not in TUNABLE_PARTITION_ROLES
    ):
        raise AnalysisCandidateIteratorError(
            f"partition firewall: illegal next_action {next_action!r} "
            f"for non-tunable role {partition_role!r}"
        )


def map_iterator_effect(next_action: str) -> str:
    """Map a #1043 next_action onto iterator_effect (before advance/exhaustion)."""
    if next_action not in NEXT_ACTIONS:
        raise AnalysisCandidateIteratorError(f"unsupported next_action: {next_action}")
    if next_action == "continue_calibration":
        return "advance"
    effect = _TERMINAL_ACTION_EFFECT.get(next_action)
    if effect is None:
        raise AnalysisCandidateIteratorError(f"unsupported next_action: {next_action}")
    return effect


def result_semantic_payload(result: Mapping[str, Any]) -> dict[str, Any]:
    """Return the portable payload used for result fingerprinting."""
    return {
        key: value
        for key, value in result.items()
        if key not in _RESULT_FP_EXCLUDED
    }


def result_semantic_fingerprint(result: Mapping[str, Any]) -> str:
    """Deterministic fingerprint of the portable iterator result."""
    try:
        return fingerprint(result_semantic_payload(result))
    except AnalysisEvalArtifactError as exc:
        raise _wrap_portable(exc) from exc


def validate_result(result: Mapping[str, Any]) -> dict[str, Any]:
    """Validate iterator result invariants; return a plain dict copy."""
    if not isinstance(result, Mapping):
        raise AnalysisCandidateIteratorError("result must be a mapping")
    if result.get("document_type") != DOCUMENT_TYPE:
        raise AnalysisCandidateIteratorError(
            f"document_type must be {DOCUMENT_TYPE!r}"
        )
    if result.get("artifact_version") != ARTIFACT_VERSION:
        raise AnalysisCandidateIteratorError(
            f"artifact_version must be {ARTIFACT_VERSION!r}"
        )
    if result.get("production_authorized") is not False:
        raise AnalysisCandidateIteratorError("production_authorized must be false")
    if result.get("iterator_effect") not in ITERATOR_EFFECTS:
        raise AnalysisCandidateIteratorError(
            f"unsupported iterator_effect: {result.get('iterator_effect')!r}"
        )
    next_action = _require_text(result.get("next_action"), "next_action")
    if next_action not in NEXT_ACTIONS:
        raise AnalysisCandidateIteratorError(f"unsupported next_action: {next_action}")
    partition_role = _require_text(result.get("partition_role"), "partition_role")
    _assert_partition_firewall(
        partition_role=partition_role, next_action=next_action
    )
    _require_text(result.get("domain"), "domain")

    if "decision_token" in result or "gate_verdict" in result:
        raise AnalysisCandidateIteratorError(
            "iterator result must not hoist decision_token/gate_verdict"
        )

    effect = str(result["iterator_effect"])
    if next_action == "continue_calibration":
        if effect not in {"advance", "exhausted"}:
            raise AnalysisCandidateIteratorError(
                "continue_calibration requires iterator_effect advance|exhausted"
            )
    else:
        expected_effect = _TERMINAL_ACTION_EFFECT.get(next_action)
        if expected_effect is None or effect != expected_effect:
            raise AnalysisCandidateIteratorError(
                f"iterator_effect {effect!r} is incompatible with next_action "
                f"{next_action!r}"
            )

    search_space = result.get("search_space")
    if not isinstance(search_space, Mapping):
        raise AnalysisCandidateIteratorError("search_space must be a mapping")
    space_id = _require_text(
        search_space.get("search_space_id"), "search_space.search_space_id"
    )
    space_version = _require_text(
        search_space.get("search_space_version"), "search_space.search_space_version"
    )
    recorded_space_fp = _require_hex_fingerprint(
        search_space.get("search_space_fingerprint"),
        "search_space.search_space_fingerprint",
    )
    declared_members = _normalize_members(search_space.get("ordered_members"))
    expected_space_fp = _compute_search_space_fingerprint(
        search_space_id=space_id,
        search_space_version=space_version,
        ordered_members=declared_members,
    )
    if recorded_space_fp != expected_space_fp:
        raise AnalysisCandidateIteratorError(
            "search_space.search_space_fingerprint does not match ordered_members"
        )
    by_id = _member_index(declared_members)

    current_candidate = result.get("current_candidate")
    if not isinstance(current_candidate, Mapping):
        raise AnalysisCandidateIteratorError("current_candidate must be a mapping")
    current_id = _require_text(
        current_candidate.get("candidate_id"), "current_candidate.candidate_id"
    )
    current_fp = _require_hex_fingerprint(
        current_candidate.get("config_fingerprint"),
        "current_candidate.config_fingerprint",
    )
    current_member = by_id.get(current_id)
    if current_member is None:
        raise AnalysisCandidateIteratorError(
            f"current candidate is not a member of search space: {current_id!r}"
        )
    if current_member["config_fingerprint"] != current_fp:
        raise AnalysisCandidateIteratorError(
            "current config_fingerprint does not match search-space declaration"
        )

    visited = result.get("visited_candidate_ids")
    if not isinstance(visited, list) or isinstance(visited, (str, bytes)):
        raise AnalysisCandidateIteratorError(
            "visited_candidate_ids must be a list of candidate ids"
        )
    seen_visited: set[str] = set()
    normalized_visited: list[str] = []
    for index, raw_id in enumerate(visited):
        candidate_id = _require_text(raw_id, f"visited_candidate_ids[{index}]")
        if candidate_id not in by_id:
            raise AnalysisCandidateIteratorError(
                f"visited candidate is not a member of search space: {candidate_id!r}"
            )
        if candidate_id in seen_visited:
            raise AnalysisCandidateIteratorError(
                f"duplicate candidate_id in visited set: {candidate_id!r}"
            )
        seen_visited.add(candidate_id)
        normalized_visited.append(candidate_id)

    iteration_index = _require_non_negative_int(
        result.get("iteration_index"), "iteration_index"
    )
    max_iterations = _require_non_negative_int(
        result.get("max_iterations"), "max_iterations"
    )
    if max_iterations < 1:
        raise AnalysisCandidateIteratorError("max_iterations must be >= 1")
    if max_iterations > len(declared_members):
        raise AnalysisCandidateIteratorError(
            "max_iterations cannot exceed search-space size"
        )
    if iteration_index < len(normalized_visited):
        raise AnalysisCandidateIteratorError(
            "iteration_index must be >= len(visited_candidate_ids)"
        )
    if iteration_index > max_iterations and effect == "advance":
        raise AnalysisCandidateIteratorError(
            "advance iteration_index cannot exceed max_iterations"
        )
    if effect == "exhausted" and iteration_index < max_iterations:
        raise AnalysisCandidateIteratorError(
            "exhausted requires iteration_index >= max_iterations"
        )

    if current_id not in normalized_visited:
        raise AnalysisCandidateIteratorError(
            "current_candidate must remain in visited_candidate_ids"
        )

    if effect == "advance":
        next_candidate = result.get("next_candidate")
        if not isinstance(next_candidate, Mapping):
            raise AnalysisCandidateIteratorError(
                "advance requires next_candidate mapping"
            )
        next_id = _require_text(
            next_candidate.get("candidate_id"), "next_candidate.candidate_id"
        )
        next_fp = _require_hex_fingerprint(
            next_candidate.get("config_fingerprint"),
            "next_candidate.config_fingerprint",
        )
        next_member = by_id.get(next_id)
        if next_member is None:
            raise AnalysisCandidateIteratorError(
                f"next candidate is not a member of search space: {next_id!r}"
            )
        if next_member["config_fingerprint"] != next_fp:
            raise AnalysisCandidateIteratorError(
                "next config_fingerprint does not match search-space declaration"
            )
        if not normalized_visited or normalized_visited[-1] != next_id:
            raise AnalysisCandidateIteratorError(
                "advance next_candidate must be the final visited_candidate_ids entry"
            )
        if next_id in normalized_visited[:-1]:
            raise AnalysisCandidateIteratorError(
                "advance next_candidate must not already be visited"
            )
        if next_id == current_id:
            raise AnalysisCandidateIteratorError(
                "advance next_candidate must differ from current_candidate"
            )
        if current_id not in normalized_visited[:-1]:
            raise AnalysisCandidateIteratorError(
                "advance current_candidate must remain in visited history"
            )
    elif "next_candidate" in result:
        raise AnalysisCandidateIteratorError(
            f"{effect} must not include next_candidate"
        )

    try:
        assert_portable_value(result, field="result")
    except AnalysisEvalArtifactError as exc:
        raise _wrap_portable(exc) from exc

    expected_fp = result_semantic_fingerprint(result)
    if result.get("result_fingerprint") != expected_fp:
        raise AnalysisCandidateIteratorError(
            "result_fingerprint does not match semantic payload"
        )

    return dict(result)


def iterate_candidates(
    *,
    domain: str,
    next_action: str,
    partition_role: str,
    provider: SearchSpaceProvider,
    current_candidate_id: str,
    current_config_fingerprint: str,
    visited_candidate_ids: Sequence[str],
    search_space_fingerprint: str,
    iteration_index: int | None = None,
    max_iterations: int | None = None,
) -> dict[str, Any]:
    """Execute one deterministic bounded iterator step (no loop / no scheduler)."""
    domain_text = _require_text(domain, "domain")
    action = _require_text(next_action, "next_action")
    role = _require_text(partition_role, "partition_role")
    if action not in NEXT_ACTIONS:
        raise AnalysisCandidateIteratorError(f"unsupported next_action: {action}")

    _assert_partition_firewall(partition_role=role, next_action=action)

    if not isinstance(provider, SearchSpaceProvider):
        raise AnalysisCandidateIteratorError(
            "provider must implement SearchSpaceProvider"
        )

    members = _normalize_members(provider.ordered_members())
    by_id = _member_index(members)
    # Snapshot provider identity once so fingerprint and result describe the
    # same search space even if a mutable provider changes later.
    space_id = _require_text(provider.search_space_id, "provider.search_space_id")
    space_version = _require_text(
        provider.search_space_version, "provider.search_space_version"
    )
    # Bind fingerprint to the normalized members used for selection, not only
    # to whatever digest a custom provider method claims.
    expected_space_fp = _compute_search_space_fingerprint(
        search_space_id=space_id,
        search_space_version=space_version,
        ordered_members=members,
    )
    provider_claimed_fp = _require_hex_fingerprint(
        provider.search_space_fingerprint(), "provider.search_space_fingerprint"
    )
    if provider_claimed_fp != expected_space_fp:
        raise AnalysisCandidateIteratorError(
            "provider.search_space_fingerprint does not match ordered members"
        )
    provided_space_fp = _require_hex_fingerprint(
        search_space_fingerprint, "search_space_fingerprint"
    )
    if provided_space_fp != expected_space_fp:
        raise AnalysisCandidateIteratorError(
            "search_space_fingerprint does not match provider declaration"
        )

    current_id = _require_text(current_candidate_id, "current_candidate_id")
    current_fp = _require_hex_fingerprint(
        current_config_fingerprint, "current_config_fingerprint"
    )
    current_member = by_id.get(current_id)
    if current_member is None:
        raise AnalysisCandidateIteratorError(
            f"current candidate is not a member of search space: {current_id!r}"
        )
    if current_member["config_fingerprint"] != current_fp:
        raise AnalysisCandidateIteratorError(
            "current config_fingerprint does not match search-space declaration"
        )

    if not isinstance(visited_candidate_ids, Sequence) or isinstance(
        visited_candidate_ids, (str, bytes)
    ):
        raise AnalysisCandidateIteratorError("visited_candidate_ids must be a sequence")

    visited: list[str] = []
    seen_visited: set[str] = set()
    for raw_id in visited_candidate_ids:
        candidate_id = _require_text(raw_id, "visited_candidate_ids[]")
        if candidate_id not in by_id:
            raise AnalysisCandidateIteratorError(
                f"visited candidate is not a member of search space: {candidate_id!r}"
            )
        if candidate_id in seen_visited:
            raise AnalysisCandidateIteratorError(
                f"duplicate candidate_id in visited set: {candidate_id!r}"
            )
        seen_visited.add(candidate_id)
        visited.append(candidate_id)

    # Current is always treated as already attempted for selection.
    if current_id not in seen_visited:
        visited.append(current_id)
        seen_visited.add(current_id)

    space_size = len(members)
    resolved_max = (
        space_size if max_iterations is None else _require_non_negative_int(
            max_iterations, "max_iterations"
        )
    )
    if resolved_max < 1:
        raise AnalysisCandidateIteratorError("max_iterations must be >= 1")
    if resolved_max > space_size:
        # Cap at finite space size — never invent room beyond the declaration.
        resolved_max = space_size

    resolved_index = (
        len(visited)
        if iteration_index is None
        else _require_non_negative_int(iteration_index, "iteration_index")
    )
    if iteration_index is not None and resolved_index < len(visited):
        # Caller-supplied index must not under-count proven attempts.
        raise AnalysisCandidateIteratorError(
            "iteration_index must be >= len(visited_candidate_ids)"
        )

    effect = map_iterator_effect(action)
    next_candidate: dict[str, str] | None = None
    result_visited = list(visited)
    result_index = resolved_index

    if action == "continue_calibration":
        if resolved_index >= resolved_max:
            effect = "exhausted"
        else:
            selected: Mapping[str, str] | None = None
            for member in members:
                if member["candidate_id"] not in seen_visited:
                    selected = member
                    break
            if selected is None:
                effect = "exhausted"
            else:
                effect = "advance"
                next_candidate = {
                    "candidate_id": str(selected["candidate_id"]),
                    "config_fingerprint": str(selected["config_fingerprint"]),
                }
                result_visited = [*visited, next_candidate["candidate_id"]]
                # Advance the caller's monotonic counter; do not reset to len(visited).
                result_index = resolved_index + 1

    result: dict[str, Any] = {
        "document_type": DOCUMENT_TYPE,
        "artifact_version": ARTIFACT_VERSION,
        "producer_id": PRODUCER_ID,
        "domain": domain_text,
        "partition_role": role,
        "next_action": action,
        "iterator_effect": effect,
        "search_space": {
            "search_space_id": space_id,
            "search_space_version": space_version,
            "search_space_fingerprint": expected_space_fp,
            "ordered_members": [dict(item) for item in members],
        },
        "current_candidate": {
            "candidate_id": current_id,
            "config_fingerprint": current_fp,
        },
        "visited_candidate_ids": result_visited,
        "iteration_index": result_index,
        "max_iterations": resolved_max,
        "production_authorized": False,
    }
    if next_candidate is not None:
        result["next_candidate"] = next_candidate

    try:
        assert_portable_value(result, field="result")
    except AnalysisEvalArtifactError as exc:
        raise _wrap_portable(exc) from exc

    result["result_fingerprint"] = result_semantic_fingerprint(result)
    return validate_result(result)
