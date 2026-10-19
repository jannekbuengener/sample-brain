"""Additional S7 acceptance guards; original frozen tests remain untouched."""

import json
from pathlib import Path

import pytest

from tests.test_analysis_locked_holdout import frozen  # noqa: F401
from tests.test_analysis_promotion import run, seal, setup  # noqa: F401


def test_first_auth_failure_is_durable_and_resumable(setup):
    setup["host"].error = "auth unavailable"
    first = run(setup)
    assert first["status"] == "infrastructure_hold"
    assert setup["provider"].calls == 0
    assert not setup["worktree_root"].exists()
    setup["host"].error = None
    assert run(setup)["status"] == "merged"


def test_source_evidence_changed_during_validation_prevents_push(setup):
    original = setup["provider"].validate_candidate

    def changed(worktree, contract):
        original(worktree, contract)
        path = Path(setup["source_state_path"])
        result_path = path.with_name(path.name + ".locked-result.json")
        value = json.loads(result_path.read_text())
        value["result_fingerprint"] = "f" * 64
        result_path.write_text(json.dumps(value))
        return True

    setup["provider"].validate_candidate = changed
    assert run(setup)["status"] == "controlled_failure"
    assert setup["host"].pushes == setup["host"].merges == 0


def test_provider_receives_a_copy_of_semantic_inputs(setup):
    original = setup["provider"].materialize

    def changed(inputs):
        payload = original(inputs)
        inputs["mode"] = "changed"
        return payload

    setup["provider"].materialize = changed
    setup["host"].checks[0]["state"] = "PENDING"
    assert run(setup)["status"] == "hold"
    assert setup["manifest"]["materializer"]["inputs"] == {"mode": "frozen"}
    assert run(setup)["status"] == "hold"
    assert setup["provider"].calls == 1


@pytest.mark.parametrize(
    "private",
    [
        "knowledge/SHARED.WORKING.MEMORY.md",
        "config/.env.json",
        "knowledge/logs/event.json",
    ],
)
def test_private_memory_and_credentials_paths_rejected(setup, private):
    old = setup["manifest"]["allowed_paths"][0]
    setup["manifest"]["allowed_paths"] = [private]
    setup["manifest"]["changes"] = {private: setup["manifest"]["changes"][old]}
    seal(setup["manifest"])
    with pytest.raises(ValueError):
        run(setup)
    assert setup["provider"].calls == 0


def test_lock_prevents_concurrent_attempt_writer(setup):
    setup["host"].checks[0]["state"] = "PENDING"
    run(setup)
    directory = next(setup["attempt_root"].glob("*"))
    lock = directory / "execution.lock"
    lock.write_text("other active execution")
    with pytest.raises(ValueError, match="lock|executing"):
        run(setup)
    assert lock.read_text() == "other active execution"
    assert setup["host"].creates == 1
