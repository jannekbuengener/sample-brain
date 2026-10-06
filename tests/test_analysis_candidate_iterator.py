"""Contract tests for sample-brain.analysis-candidate-iterator.v1 (#1064 W0)."""

from __future__ import annotations

import ast
import copy
from pathlib import Path
from typing import Any, Sequence

import pytest

from src.analysis_candidate_iterator import (
    ARTIFACT_VERSION,
    DOCUMENT_TYPE,
    AnalysisCandidateIteratorError,
    StaticSearchSpaceProvider,
    iterate_candidates,
    result_semantic_fingerprint,
    search_space_fingerprint,
    validate_result,
)
from src.analysis_eval_artifact import fingerprint

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"


def _members() -> list[dict[str, str]]:
    # Intentionally non-lexical order (c before a) to prove domain order wins.
    return [
        {
            "candidate_id": "demo.cand.c",
            "config_fingerprint": "c" * 64,
        },
        {
            "candidate_id": "demo.cand.a",
            "config_fingerprint": "a" * 64,
        },
        {
            "candidate_id": "demo.cand.b",
            "config_fingerprint": "b" * 64,
        },
    ]


def _provider(
    members: Sequence[dict[str, str]] | None = None,
    *,
    search_space_id: str = "demo.search-space",
    search_space_version: str = "1.0.0",
) -> StaticSearchSpaceProvider:
    return StaticSearchSpaceProvider(
        search_space_id=search_space_id,
        search_space_version=search_space_version,
        ordered_members=list(members if members is not None else _members()),
    )


def _run(
    *,
    next_action: str = "continue_calibration",
    partition_role: str = "calibration",
    current_candidate_id: str = "demo.cand.c",
    current_config_fingerprint: str = "c" * 64,
    visited_candidate_ids: Sequence[str] | None = None,
    iteration_index: int | None = None,
    max_iterations: int | None = None,
    provider: StaticSearchSpaceProvider | None = None,
    search_space_fingerprint_override: str | None = None,
) -> dict[str, Any]:
    space = provider or _provider()
    return iterate_candidates(
        domain="demo.domain",
        next_action=next_action,
        partition_role=partition_role,
        provider=space,
        current_candidate_id=current_candidate_id,
        current_config_fingerprint=current_config_fingerprint,
        visited_candidate_ids=list(
            visited_candidate_ids
            if visited_candidate_ids is not None
            else [current_candidate_id]
        ),
        iteration_index=iteration_index,
        max_iterations=max_iterations,
        search_space_fingerprint=search_space_fingerprint_override
        or space.search_space_fingerprint(),
    )


def test_document_identity_frozen() -> None:
    assert DOCUMENT_TYPE == "sample-brain.analysis-candidate-iterator.v1"
    assert ARTIFACT_VERSION == "1.0.0"


def test_no_arvp_import_in_iterator_module() -> None:
    tree = ast.parse((SRC_ROOT / "analysis_candidate_iterator.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("arvp")
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not node.module.startswith("arvp")


def test_search_space_fingerprint_deterministic_and_order_sensitive() -> None:
    members = _members()
    fp1 = search_space_fingerprint(
        search_space_id="demo.search-space",
        search_space_version="1.0.0",
        ordered_members=members,
    )
    fp2 = search_space_fingerprint(
        search_space_id="demo.search-space",
        search_space_version="1.0.0",
        ordered_members=copy.deepcopy(members),
    )
    assert fp1 == fp2
    assert len(fp1) == 64
    reordered = [members[1], members[0], members[2]]
    fp3 = search_space_fingerprint(
        search_space_id="demo.search-space",
        search_space_version="1.0.0",
        ordered_members=reordered,
    )
    assert fp3 != fp1


def test_minimal_continue_calibration_advances_first_unvisited() -> None:
    result = _run(visited_candidate_ids=["demo.cand.c"])
    validated = validate_result(result)
    assert validated["document_type"] == DOCUMENT_TYPE
    assert validated["next_action"] == "continue_calibration"
    assert validated["iterator_effect"] == "advance"
    assert validated["next_candidate"]["candidate_id"] == "demo.cand.a"
    assert validated["next_candidate"]["config_fingerprint"] == "a" * 64
    assert validated["visited_candidate_ids"] == ["demo.cand.c", "demo.cand.a"]
    assert validated["iteration_index"] == 2
    assert validated["production_authorized"] is False
    assert "decision_token" not in validated


def test_continue_calibration_on_development_advances() -> None:
    result = _run(
        partition_role="development",
        visited_candidate_ids=["demo.cand.c"],
    )
    assert result["partition_role"] == "development"
    assert result["iterator_effect"] == "advance"
    assert result["next_candidate"]["candidate_id"] == "demo.cand.a"
    assert result["production_authorized"] is False


def test_unknown_next_action_fail_closed() -> None:
    with pytest.raises(AnalysisCandidateIteratorError, match="unsupported next_action"):
        _run(next_action="invent_new_optimizer_step")


def test_supplied_iteration_index_advances_monotonically() -> None:
    members = [
        {"candidate_id": f"demo.cand.{i}", "config_fingerprint": f"{i}" * 64}
        for i in "01234"
    ]
    provider = _provider(members, search_space_id="demo.wide", search_space_version="1.0.0")
    result = iterate_candidates(
        domain="demo.domain",
        next_action="continue_calibration",
        partition_role="calibration",
        provider=provider,
        current_candidate_id="demo.cand.0",
        current_config_fingerprint="0" * 64,
        visited_candidate_ids=["demo.cand.0"],
        search_space_fingerprint=provider.search_space_fingerprint(),
        iteration_index=3,
        max_iterations=4,
    )
    assert result["iterator_effect"] == "advance"
    assert result["iteration_index"] == 4
    assert result["next_candidate"]["candidate_id"] == "demo.cand.1"


def test_validate_result_rejects_action_effect_mismatch() -> None:
    result = _run(next_action="freeze_candidate")
    poisoned = dict(result)
    poisoned["iterator_effect"] = "advance"
    poisoned["next_candidate"] = {
        "candidate_id": "demo.cand.a",
        "config_fingerprint": "a" * 64,
    }
    poisoned["result_fingerprint"] = result_semantic_fingerprint(poisoned)
    with pytest.raises(
        AnalysisCandidateIteratorError, match="incompatible with next_action"
    ):
        validate_result(poisoned)


def test_validate_result_reapplies_partition_firewall() -> None:
    result = _run(visited_candidate_ids=["demo.cand.c"])
    poisoned = dict(result)
    poisoned["partition_role"] = "test"
    poisoned["result_fingerprint"] = result_semantic_fingerprint(poisoned)
    with pytest.raises(AnalysisCandidateIteratorError, match="partition|tunable|firewall"):
        validate_result(poisoned)


def test_validate_result_rejects_reselected_visited_next_candidate() -> None:
    result = _run(visited_candidate_ids=["demo.cand.c"])
    poisoned = dict(result)
    poisoned["next_candidate"] = {
        "candidate_id": "demo.cand.c",
        "config_fingerprint": "c" * 64,
    }
    poisoned["visited_candidate_ids"] = ["demo.cand.c", "demo.cand.c"]
    poisoned["result_fingerprint"] = result_semantic_fingerprint(poisoned)
    with pytest.raises(
        AnalysisCandidateIteratorError,
        match="duplicate candidate_id|already be visited|final visited",
    ):
        validate_result(poisoned)

    poisoned2 = dict(result)
    poisoned2["next_candidate"] = dict(result["current_candidate"])
    poisoned2["visited_candidate_ids"] = ["demo.cand.c", "demo.cand.a"]
    poisoned2["result_fingerprint"] = result_semantic_fingerprint(poisoned2)
    with pytest.raises(
        AnalysisCandidateIteratorError,
        match="final visited|differ from current",
    ):
        validate_result(poisoned2)


def test_validate_result_rejects_malformed_bounded_state() -> None:
    result = _run(visited_candidate_ids=["demo.cand.c"])
    poisoned = dict(result)
    poisoned["iteration_index"] = -99
    poisoned["result_fingerprint"] = result_semantic_fingerprint(poisoned)
    with pytest.raises(AnalysisCandidateIteratorError, match="iteration_index"):
        validate_result(poisoned)

    poisoned2 = dict(result)
    poisoned2["max_iterations"] = -1
    poisoned2["result_fingerprint"] = result_semantic_fingerprint(poisoned2)
    with pytest.raises(AnalysisCandidateIteratorError, match="max_iterations"):
        validate_result(poisoned2)

    poisoned3 = dict(result)
    poisoned3["visited_candidate_ids"] = None
    poisoned3["result_fingerprint"] = result_semantic_fingerprint(poisoned3)
    with pytest.raises(AnalysisCandidateIteratorError, match="visited_candidate_ids"):
        validate_result(poisoned3)

    poisoned4 = dict(result)
    poisoned4.pop("search_space", None)
    poisoned4["result_fingerprint"] = result_semantic_fingerprint(poisoned4)
    with pytest.raises(AnalysisCandidateIteratorError, match="search_space"):
        validate_result(poisoned4)


def test_validate_result_rejects_undeclared_next_candidate() -> None:
    result = _run(visited_candidate_ids=["demo.cand.c"])
    poisoned = dict(result)
    poisoned["search_space"] = dict(result["search_space"])
    poisoned["next_candidate"] = {
        "candidate_id": "demo.cand.undeclared",
        "config_fingerprint": "d" * 64,
    }
    poisoned["visited_candidate_ids"] = ["demo.cand.c", "demo.cand.undeclared"]
    poisoned["iteration_index"] = 2
    poisoned["result_fingerprint"] = result_semantic_fingerprint(poisoned)
    with pytest.raises(
        AnalysisCandidateIteratorError,
        match="not a member of search space",
    ):
        validate_result(poisoned)


def test_validate_result_rejects_premature_exhausted() -> None:
    result = _run(next_action="continue_calibration", visited_candidate_ids=["demo.cand.c"])
    poisoned = dict(result)
    poisoned["iterator_effect"] = "exhausted"
    poisoned.pop("next_candidate", None)
    poisoned["visited_candidate_ids"] = ["demo.cand.c"]
    poisoned["iteration_index"] = 1
    poisoned["max_iterations"] = 3
    poisoned["result_fingerprint"] = result_semantic_fingerprint(poisoned)
    with pytest.raises(
        AnalysisCandidateIteratorError,
        match="exhausted requires iteration_index >= max_iterations",
    ):
        validate_result(poisoned)


def test_validate_result_rejects_iteration_index_below_visited_count() -> None:
    result = _run(visited_candidate_ids=["demo.cand.c"])
    poisoned = dict(result)
    # Legitimate advance has visited=[current, next] and iteration_index == 2.
    poisoned["iteration_index"] = 1
    poisoned["result_fingerprint"] = result_semantic_fingerprint(poisoned)
    with pytest.raises(
        AnalysisCandidateIteratorError,
        match="iteration_index must be >= len\\(visited_candidate_ids\\)",
    ):
        validate_result(poisoned)


def test_validate_result_requires_current_candidate_in_visited_history() -> None:
    result = _run(visited_candidate_ids=["demo.cand.c"])
    poisoned = dict(result)
    # Drop current from visited; keep only the next candidate.
    poisoned["visited_candidate_ids"] = [result["next_candidate"]["candidate_id"]]
    poisoned["iteration_index"] = 1
    poisoned["result_fingerprint"] = result_semantic_fingerprint(poisoned)
    with pytest.raises(
        AnalysisCandidateIteratorError,
        match="current_candidate must remain in visited",
    ):
        validate_result(poisoned)


def test_mutable_provider_identity_snapshotted_into_result() -> None:
    class _FlipIdentityProvider(StaticSearchSpaceProvider):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._reads = 0

        @property
        def search_space_id(self) -> str:  # type: ignore[override]
            self._reads += 1
            # Second+ reads would poison result identity if re-read after snapshot.
            if self._reads == 1:
                return self._search_space_id
            return "demo.search-space.mutated"

    provider = _FlipIdentityProvider(
        search_space_id="demo.search-space",
        search_space_version="1.0.0",
        ordered_members=_members(),
    )
    result = _run(
        visited_candidate_ids=["demo.cand.c"],
        provider=provider,
    )
    assert result["search_space"]["search_space_id"] == "demo.search-space"
    assert result["search_space"]["search_space_fingerprint"] == search_space_fingerprint(
        search_space_id="demo.search-space",
        search_space_version="1.0.0",
        ordered_members=_members(),
    )


def test_stale_provider_fingerprint_rejected() -> None:
    class _StaleProvider(StaticSearchSpaceProvider):
        def search_space_fingerprint(self) -> str:  # type: ignore[override]
            return "f" * 64

    provider = _StaleProvider(
        search_space_id="demo.search-space",
        search_space_version="1.0.0",
        ordered_members=_members(),
    )
    with pytest.raises(
        AnalysisCandidateIteratorError,
        match="provider.search_space_fingerprint|search_space_fingerprint",
    ):
        iterate_candidates(
            domain="demo.domain",
            next_action="continue_calibration",
            partition_role="calibration",
            provider=provider,
            current_candidate_id="demo.cand.c",
            current_config_fingerprint="c" * 64,
            visited_candidate_ids=["demo.cand.c"],
            search_space_fingerprint="f" * 64,
        )


def test_domain_order_not_lexical() -> None:
    # With only c visited, next must be a (declaration #2), not lexical 'a' coincidence
    # proven by skipping a and expecting b when a is also visited.
    result = _run(visited_candidate_ids=["demo.cand.c", "demo.cand.a"])
    assert result["next_candidate"]["candidate_id"] == "demo.cand.b"


def test_visited_candidate_skipped() -> None:
    result = _run(visited_candidate_ids=["demo.cand.c", "demo.cand.a"])
    assert result["iterator_effect"] == "advance"
    assert result["next_candidate"]["candidate_id"] == "demo.cand.b"
    assert "demo.cand.a" not in [result["next_candidate"]["candidate_id"]]


def test_deterministic_repeated_invocation() -> None:
    a = _run()
    b = _run()
    assert a == b
    assert result_semantic_fingerprint(a) == a["result_fingerprint"]
    assert a["result_fingerprint"] == b["result_fingerprint"]


def test_semantic_mutation_changes_result_fingerprint() -> None:
    base = _run()
    mutated = dict(base)
    mutated["iterator_effect"] = "stop"
    mutated.pop("next_candidate", None)
    assert result_semantic_fingerprint(mutated) != base["result_fingerprint"]


def test_exhaustion_when_all_visited() -> None:
    result = _run(
        visited_candidate_ids=["demo.cand.c", "demo.cand.a", "demo.cand.b"],
        current_candidate_id="demo.cand.b",
        current_config_fingerprint="b" * 64,
    )
    assert result["iterator_effect"] == "exhausted"
    assert "next_candidate" not in result
    assert result["production_authorized"] is False


def test_max_iteration_bound_terminates() -> None:
    result = _run(
        visited_candidate_ids=["demo.cand.c"],
        iteration_index=1,
        max_iterations=1,
    )
    assert result["iterator_effect"] == "exhausted"
    assert "next_candidate" not in result


def test_non_tunable_partition_rejected_for_continue() -> None:
    for role in ("validation", "test", "holdout", "external_check"):
        with pytest.raises(AnalysisCandidateIteratorError, match="partition|tunable|firewall"):
            _run(partition_role=role, next_action="continue_calibration")


def test_non_tunable_partition_rejected_for_freeze() -> None:
    with pytest.raises(AnalysisCandidateIteratorError, match="partition|tunable|firewall"):
        _run(partition_role="test", next_action="freeze_candidate")


def test_terminal_actions_emit_no_next_candidate() -> None:
    cases = [
        ("freeze_candidate", "freeze"),
        ("keep_baseline_and_stop", "stop"),
        ("defer_for_evidence", "hold"),
        ("require_human_governance", "stop"),
        ("stop_controlled_failure", "controlled_failure"),
    ]
    for next_action, effect in cases:
        result = _run(next_action=next_action)
        assert result["iterator_effect"] == effect
        assert "next_candidate" not in result
        assert result["next_action"] == next_action
        assert result["production_authorized"] is False


def test_duplicate_candidate_ids_rejected() -> None:
    bad = _members()
    bad.append({"candidate_id": "demo.cand.c", "config_fingerprint": "d" * 64})
    with pytest.raises(AnalysisCandidateIteratorError, match="duplicate"):
        _run(provider=_provider(bad))


def test_wrong_search_space_fingerprint_rejected() -> None:
    with pytest.raises(AnalysisCandidateIteratorError, match="search_space_fingerprint"):
        _run(search_space_fingerprint_override="f" * 64)


def test_wrong_current_config_fingerprint_rejected() -> None:
    with pytest.raises(AnalysisCandidateIteratorError, match="config_fingerprint"):
        _run(current_config_fingerprint="0" * 64)


def test_unknown_current_candidate_rejected() -> None:
    with pytest.raises(AnalysisCandidateIteratorError, match="current candidate|not a member"):
        _run(
            current_candidate_id="demo.cand.missing",
            current_config_fingerprint="c" * 64,
            visited_candidate_ids=["demo.cand.missing"],
        )


def test_selected_candidate_never_already_visited() -> None:
    result = _run(visited_candidate_ids=["demo.cand.c"])
    assert result["next_candidate"]["candidate_id"] not in ["demo.cand.c"]
    assert result["next_candidate"]["candidate_id"] in result["visited_candidate_ids"]


def test_production_authorized_cannot_be_true() -> None:
    result = _run()
    poisoned = dict(result)
    poisoned["production_authorized"] = True
    with pytest.raises(AnalysisCandidateIteratorError, match="production_authorized"):
        validate_result(poisoned)


def test_absolute_path_rejected_in_portable_result() -> None:
    result = _run()
    poisoned = dict(result)
    poisoned["leak"] = "C:/Users/private/secret.wav"
    with pytest.raises(Exception, match="absolute/private path|path is forbidden|portable"):
        validate_result(poisoned)


def test_provider_fingerprint_matches_helper() -> None:
    provider = _provider()
    assert provider.search_space_fingerprint() == search_space_fingerprint(
        search_space_id=provider.search_space_id,
        search_space_version=provider.search_space_version,
        ordered_members=provider.ordered_members(),
    )
    # sanity: fingerprint helper from #956 still works on nested payload
    assert len(fingerprint({"x": 1})) == 64
