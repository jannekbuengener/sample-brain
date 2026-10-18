"""Exact review regressions for PR #1177; no original frozen test changes."""

import json

from tests.test_analysis_locked_holdout import frozen  # noqa: F401
from tests.test_analysis_promotion import run, setup  # noqa: F401


def test_effective_rules_include_later_pages(tmp_path):
    from src.analysis_promotion_host import GhHost

    calls = []
    first = [{"type": "deletion"}]
    second = [
        {
            "type": "required_status_checks",
            "parameters": {
                "required_status_checks": [
                    {"context": "later-page", "integration_id": 15368}
                ]
            },
        },
        {
            "type": "pull_request",
            "parameters": {
                "required_approving_review_count": 0,
                "allowed_merge_methods": ["squash"],
            },
        },
    ]

    def runner(argv):
        calls.append(argv)
        return json.dumps(first) + "\n" + json.dumps(second)

    host = GhHost("example/repo", tmp_path, runner=runner)
    assert host.policy()["required_checks"] == [{"name": "later-page", "app_id": 15368}]
    assert "--paginate" in calls[0]


def test_lost_merge_with_delayed_merge_sha_remains_resumable(setup):
    from src.analysis_promotion_host import InfrastructureError

    host = setup["host"]
    merge = host.merge

    def lost(*args):
        merge(*args)
        raise InfrastructureError("lost merge response")

    host.merge = lost
    assert run(setup)["status"] == "infrastructure_hold"
    exact_sha = host.pr["merge_sha"]
    host.pr["merge_sha"] = None
    pending = run(setup)
    assert pending["status"] == "hold"
    assert pending["phase"] == "merging"
    assert pending["reason"] == "merge_verification_required"
    host.pr["merge_sha"] = exact_sha
    assert run(setup)["status"] == "merged"
    assert host.merges == host.creates == 1


def test_completed_merge_recovers_after_temporary_verification_hold(setup):
    host = setup["host"]
    assert run(setup)["status"] == "merged"
    host.verified = False
    assert run(setup)["status"] == "hold"
    host.verified = True
    restored = run(setup)
    assert restored["status"] == "merged"
    assert restored["repository_merge_eligible"] is True
    assert host.merges == 1
