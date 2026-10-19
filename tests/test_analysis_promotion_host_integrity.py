"""Malformed/unavailable GitHub evidence cannot become candidate success."""

import pytest


@pytest.mark.parametrize(
    "method,args",
    [("main_sha", ()), ("snapshot", (7,)), ("verify_merge", (7, "a" * 40, "b" * 40))],
)
def test_malformed_host_evidence_is_infrastructure_failure(tmp_path, method, args):
    from src.analysis_promotion_host import GhHost, InfrastructureError

    host = GhHost("example/repo", tmp_path, runner=lambda argv: "{}")
    with pytest.raises(InfrastructureError):
        getattr(host, method)(*args)


@pytest.mark.parametrize(
    "text",
    [
        '{"input":"/workspace/raw/record.json"}',
        'source="/srv/data/private.json"',
        'path="C:\\Users\\private\\secret.txt"',
    ],
)
def test_embedded_host_paths_are_not_portable_candidate_content(text):
    from src.analysis_promotion import _content

    with pytest.raises(ValueError):
        _content(text)


def test_push_uses_frozen_commit_instead_of_mutable_local_branch(tmp_path):
    from src.analysis_promotion_host import GhHost

    calls = []

    class Repository:
        def head(self, branch):
            return "a" * 40

    host = GhHost(
        "example/repo", tmp_path, runner=lambda argv: calls.append(argv) or ""
    )
    host.push(Repository(), "promotion/frozen", "a" * 40)
    assert calls == [
        ["git", "push", "origin", f"{'a' * 40}:refs/heads/promotion/frozen"]
    ]
