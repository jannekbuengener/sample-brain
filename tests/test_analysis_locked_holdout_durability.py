"""#1174 review regressions: metadata barriers and exact decision versions."""

import pytest

from src.analysis_automation_decision import (
    aq1_scalar_decision_fixture,
    decision_semantic_fingerprint,
    validate_decision,
)
from tests.test_analysis_locked_holdout import frozen, transition  # noqa: F401


def test_legacy_action_cannot_claim_handoff_version():
    decision = aq1_scalar_decision_fixture()
    decision["artifact_version"] = "1.1.0"
    decision["decision_fingerprint"] = decision_semantic_fingerprint(decision)
    with pytest.raises(ValueError, match="version"):
        validate_decision(decision)


def test_claim_metadata_barrier_failure_prevents_dispatch(frozen, monkeypatch):
    import src.analysis_locked_holdout as locked

    def fail(path):
        raise OSError("metadata sync failed")

    monkeypatch.setattr(locked, "_sync_entry", fail)
    monkeypatch.setattr(locked, "run_orchestration", lambda **kw: pytest.fail("dispatched before durable claim"))
    with pytest.raises(OSError, match="metadata sync failed"):
        transition(**frozen)


def test_result_metadata_barrier_failure_never_reports_commit(frozen, monkeypatch):
    import src.analysis_locked_holdout as locked

    original = locked._sync_entry

    def fail_result(path):
        if path.name.endswith("locked-result.json"):
            raise OSError("result metadata sync failed")
        original(path)

    monkeypatch.setattr(locked, "_sync_entry", fail_result)
    with pytest.raises(OSError, match="result metadata sync failed"):
        transition(**frozen)
    monkeypatch.setattr(locked, "run_orchestration", lambda **kw: pytest.fail("reran"))
    with pytest.raises(OSError, match="result metadata sync failed"):
        transition(**frozen)
    monkeypatch.setattr(locked, "_sync_entry", original)
    assert transition(**frozen)["already_committed"] is True
