"""Concrete gh boundary: exact head, app identity, pagination, safe errors."""

import json
import subprocess

import pytest


def test_merge_command_has_expected_head_without_bypass(tmp_path):
    from src.analysis_promotion_host import GhHost

    calls = []

    def runner(args):
        calls.append(args)
        return ""

    host = GhHost("example/repo", tmp_path, runner=runner)
    host.merge(7, "a" * 40, "squash")
    command = calls[0]
    assert command[:3] == ["gh", "pr", "merge"]
    assert command[command.index("--match-head-commit") + 1] == "a" * 40
    assert "--squash" in command
    assert "--admin" not in command
    assert "--auto" not in command


def test_live_rules_preserve_integration_identity_and_reject_unknown(tmp_path):
    from src.analysis_promotion_host import GhHost, InfrastructureError

    rules = [
        {
            "type": "required_status_checks",
            "parameters": {
                "required_status_checks": [{"context": "test", "integration_id": 15368}]
            },
        },
        {
            "type": "pull_request",
            "parameters": {
                "required_approving_review_count": 1,
                "allowed_merge_methods": ["squash"],
            },
        },
    ]
    host = GhHost("example/repo", tmp_path, runner=lambda args: json.dumps(rules))
    assert host.policy() == {
        "required_checks": [{"name": "test", "app_id": 15368}],
        "merge_methods": ["squash"],
        "required_approvals": 1,
    }
    rules.append({"type": "unknown_future_rule"})
    with pytest.raises(InfrastructureError):
        host.policy()


def test_auth_or_network_failures_are_typed_and_do_not_leak_output(tmp_path):
    from src.analysis_promotion_host import GhHost, InfrastructureError

    def runner(args):
        raise subprocess.CalledProcessError(
            1, args, output="token=private", stderr="C:/private"
        )

    host = GhHost("example/repo", tmp_path, runner=runner)
    with pytest.raises(InfrastructureError) as exc:
        host.main_sha()
    assert "private" not in str(exc.value)


def test_paginated_check_and_feedback_snapshot_is_exact_head(tmp_path):
    from src.analysis_promotion_host import GhHost

    head = "a" * 40
    calls = []

    def runner(args):
        calls.append(args)
        endpoint = args[2]
        if endpoint == "graphql":
            return json.dumps(
                {
                    "data": {
                        "repository": {
                            "pullRequest": {
                                "reviewThreads": {
                                    "nodes": [],
                                    "pageInfo": {
                                        "hasNextPage": False,
                                        "endCursor": None,
                                    },
                                }
                            }
                        }
                    }
                }
            )
        if endpoint.endswith("/pulls/7"):
            return json.dumps(
                {
                    "number": 7,
                    "state": "open",
                    "draft": False,
                    "mergeable": True,
                    "mergeable_state": "clean",
                    "merged": False,
                    "merge_commit_sha": None,
                    "head": {
                        "sha": head,
                        "ref": "promotion/one",
                        "repo": {"full_name": "example/repo"},
                    },
                    "base": {"ref": "main", "repo": {"full_name": "example/repo"}},
                }
            )
        if "check-runs" in endpoint:
            return json.dumps(
                [
                    {
                        "check_runs": [
                            {
                                "name": "one",
                                "head_sha": head,
                                "status": "completed",
                                "conclusion": "success",
                                "app": {"id": 15368},
                            }
                        ]
                    },
                    {
                        "check_runs": [
                            {
                                "name": "two",
                                "head_sha": head,
                                "status": "in_progress",
                                "conclusion": None,
                                "app": {"id": 15368},
                            }
                        ]
                    },
                ]
            )
        if endpoint.endswith("/issues/7/comments?per_page=100"):
            return json.dumps(
                [
                    [{"id": 1, "body": "first", "updated_at": "t1"}],
                    [{"id": 2, "body": "second", "updated_at": "t2"}],
                ]
            )
        return json.dumps([[]])

    host = GhHost("example/repo", tmp_path, runner=runner)
    result = host.snapshot(7)
    assert result["head_sha"] == head
    assert result["mergeable"] is True
    assert [c["state"] for c in result["checks"]] == ["SUCCESS", "PENDING"]
    assert [c["id"] for c in result["feedback"]] == ["issue:1", "issue:2"]
    assert any("--paginate" in c and "--slurp" in c for c in calls)


@pytest.mark.parametrize(
    "conclusion,expected",
    [
        ("success", "SUCCESS"),
        ("failure", "FAILED"),
        ("cancelled", "CANCELLED"),
        ("skipped", "UNKNOWN"),
        (None, "UNKNOWN"),
    ],
)
def test_check_conclusions_fail_closed(conclusion, expected):
    from src.analysis_promotion_host import check_state

    assert check_state("completed", conclusion) == expected
    assert check_state("queued", conclusion) == "PENDING"


def test_bounded_pr_creation_uses_caller_supplied_neutral_title_and_body(tmp_path):
    from src.analysis_promotion_host import GhHost

    calls = []

    def runner(args):
        calls.append(args)
        return ""

    host = GhHost("example/repo", tmp_path, runner=runner)
    head = "a" * 40
    base = "b" * 40
    host.find_pr = lambda branch: {
        "number": 8,
        "head_sha": head,
        "branch": branch,
        "base": "main",
        "repository_id": "example/repo",
    }

    result = host.create_bounded_pr(
        "recovery/one",
        head,
        base,
        title="Forward repair invalid analysis promotion",
        body="Bounded S8 forward repair.",
    )

    command = calls[0]
    assert command[:3] == ["gh", "pr", "create"]
    assert (
        command[command.index("--title") + 1]
        == "Forward repair invalid analysis promotion"
    )
    assert command[command.index("--body") + 1] == "Bounded S8 forward repair."
    assert "--admin" not in command
    assert result["number"] == 8
