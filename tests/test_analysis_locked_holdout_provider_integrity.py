"""Reader-only validation and malformed policy regression contracts."""

import pytest

from tests.test_analysis_locked_holdout import frozen, transition  # noqa: F401
from tests.test_analysis_locked_holdout_provider import POLICY, provider_call


def test_s7_provider_reader_never_builds_decision(frozen, monkeypatch):
    from src.analysis_promotion import load_promotion_source

    result = transition(**provider_call(frozen))["result"]

    def forbidden(*args, **kwargs):
        pytest.fail("reader recomputed decision or policy")

    monkeypatch.setattr("src.analysis_locked_holdout.build_decision", forbidden)
    monkeypatch.setattr("src.analysis_orchestration_run.build_decision", forbidden)
    monkeypatch.setattr("src.analysis_locked_holdout.run_orchestration", forbidden)
    assert load_promotion_source(frozen["state_path"]) == result


@pytest.mark.parametrize(
    "field,value",
    [
        ("gate_verdict", []),
        ("gate_verdict", {}),
        ("decision_token", ""),
        ("next_action", ""),
        ("decision_token", []),
        ("next_action", {}),
    ],
)
def test_malformed_provider_policy_is_controlled_and_not_retried(frozen, field, value):
    calls = []

    def decide(context):
        calls.append(1)
        return dict(POLICY, **{field: value})

    args = provider_call(frozen, decide)
    with pytest.raises(ValueError):
        transition(**args)
    with pytest.raises(ValueError, match="claim|uncertain"):
        transition(**args)
    assert calls == [1]
