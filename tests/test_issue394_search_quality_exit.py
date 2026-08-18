from __future__ import annotations

from types import SimpleNamespace
import sys

import pytest

from src import benchmark_search_quality, cli


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


def _run_search_quality_cli(monkeypatch: pytest.MonkeyPatch, result) -> None:
    monkeypatch.setattr(cli, "_resolve_profile_or_exit", lambda args: {})
    monkeypatch.setattr(cli, "_apply_runtime_db_path", lambda config: None)
    monkeypatch.setattr(
        benchmark_search_quality,
        "run_search_quality_benchmark",
        lambda *args, **kwargs: result,
    )
    monkeypatch.setattr(
        benchmark_search_quality,
        "print_search_quality_report",
        lambda result: None,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["sample-brain", "benchmark", "search-quality"],
    )
    cli.main()


def test_tier_a_gate_failure_is_hard_failure(monkeypatch: pytest.MonkeyPatch):
    result = _result(
        tier="A",
        checks={"mean_precision_at_5": False, "must_recall_queries": True},
    )

    with pytest.raises(SystemExit) as exc_info:
        _run_search_quality_cli(monkeypatch, result)

    assert exc_info.value.code == 1


def test_tier_a_success_is_success(monkeypatch: pytest.MonkeyPatch):
    result = _result(
        tier="A",
        checks={"mean_precision_at_5": True, "must_recall_queries": True},
    )

    assert _run_search_quality_cli(monkeypatch, result) is None


def test_tier_b_quality_failure_is_informational(monkeypatch: pytest.MonkeyPatch):
    result = _result(
        tier="B",
        checks={
            "mean_precision_at_5": False,
            "must_recall_queries": False,
            "filter_compliance": False,
        },
    )

    assert _run_search_quality_cli(monkeypatch, result) is None


def test_tier_b_query_error_is_hard_failure(monkeypatch: pytest.MonkeyPatch):
    result = _result(
        tier="B",
        checks={"mean_precision_at_5": True, "must_recall_queries": True},
        errors=("query evaluation failed",),
    )

    with pytest.raises(SystemExit) as exc_info:
        _run_search_quality_cli(monkeypatch, result)

    assert exc_info.value.code == 1
