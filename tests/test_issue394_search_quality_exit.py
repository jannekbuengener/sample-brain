from __future__ import annotations

from types import SimpleNamespace

from src.cli import search_quality_exit_code


def _result(
    *,
    tier: str,
    checks: dict[str, bool],
    errors: tuple[str | None, ...] = (),
):
    return SimpleNamespace(
        tier=tier,
        query_results=tuple(SimpleNamespace(error=error) for error in errors),
        threshold_pass=lambda: checks,
    )


def test_tier_a_gate_failure_is_hard_failure():
    result = _result(
        tier="A",
        checks={"mean_precision_at_5": False, "must_recall_queries": True},
    )

    assert search_quality_exit_code(result) == 1


def test_tier_a_success_is_success():
    result = _result(
        tier="A",
        checks={"mean_precision_at_5": True, "must_recall_queries": True},
    )

    assert search_quality_exit_code(result) == 0


def test_tier_b_quality_failure_is_informational():
    result = _result(
        tier="B",
        checks={
            "mean_precision_at_5": False,
            "must_recall_queries": False,
            "filter_compliance": False,
        },
    )

    assert search_quality_exit_code(result) == 0


def test_tier_b_query_error_is_hard_failure():
    result = _result(
        tier="B",
        checks={"mean_precision_at_5": True, "must_recall_queries": True},
        errors=("query evaluation failed",),
    )

    assert search_quality_exit_code(result) == 1


def test_unknown_tier_fails_closed():
    result = _result(
        tier="unknown",
        checks={"mean_precision_at_5": True, "must_recall_queries": True},
    )

    assert search_quality_exit_code(result) == 1
