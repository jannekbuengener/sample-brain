from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

import pytest

from src import jules_dispatch as jd
from src.jules_dispatch import (
    DispatchContext,
    JulesError,
    JulesHttpError,
    JulesTransportError,
    build_create_payload,
    build_prompt,
    get_activities,
    match_source,
    normalize_dispatch,
    redact,
    resolve_source,
    run_activities,
    run_approve,
    run_dispatch,
    run_message,
    run_status,
    validate_context,
)

SAMPLE_SOURCE = {
    "name": "sources/github/jannekbuengener/sample-brain",
    "githubRepo": {"owner": "jannekbuengener", "repo": "sample-brain"},
}


def _ctx(**overrides: Any) -> DispatchContext:
    base = dict(
        repo="jannekbuengener/sample-brain",
        issue_number=376,
        issue_url="https://github.com/jannekbuengener/sample-brain/issues/376",
        base_branch="main",
        base_sha="abc123",
        change_class="product_code",
        goal="Add a small helper module.",
        acceptance_criteria=["tests pass", "no private data leaked"],
        relevant_files=["src/cli.py"],
        known_facts=["src/cli.py is the entrypoint"],
        constraints=["only src/cli.py may change"],
        minimum_validation=["pytest -q"],
        allow_pr=False,
    )
    base.update(overrides)
    return DispatchContext.from_dict(base)


class FakeTransport:
    def __init__(
        self,
        api_key: Optional[str] = "dummy-key",
        sources: Optional[List[dict]] = None,
        session: Optional[dict] = None,
        activities_pages: Optional[List[dict]] = None,
        http_error: Optional[Tuple[int, str, str]] = None,
        transport_error: Optional[str] = None,
    ) -> None:
        self.api_key = api_key
        self.sources = sources if sources is not None else [SAMPLE_SOURCE]
        self.session = session or {
            "name": "sessions/abc",
            "state": "AWAITING_PLAN_APPROVAL",
        }
        self.activities_pages = activities_pages or [{"activities": []}]
        self.http_error = http_error
        self.transport_error = transport_error
        self.calls: List[Tuple[str, str, Optional[dict]]] = []

    def request(self, method: str, path: str, body: Optional[dict] = None) -> dict:
        self.calls.append((method, path, body))
        if self.http_error:
            raise JulesHttpError(*self.http_error)
        if self.transport_error:
            raise JulesTransportError(self.transport_error)
        if method == "GET" and path == "/sources":
            return {"sources": self.sources}
        if method == "POST" and path == "/sessions":
            return self.session
        if method == "GET" and path.startswith("/sessions/") and "/activities" in path:
            if self.activities_pages:
                return self.activities_pages.pop(0)
            return {"activities": []}
        if method == "GET" and path.startswith("/sessions/"):
            return self.session
        if method == "POST" and path.endswith(":approvePlan"):
            return {"state": "PLAN_APPROVED"}
        if method == "POST" and path.endswith(":sendMessage"):
            return {"ok": True}
        return {}


# 1. Prompt contains goal, acceptance, only relevant repo paths, no repo dump.
def test_prompt_contains_goal_acceptance_and_relevant_paths() -> None:
    ctx = _ctx(
        goal="Implement the envelope builder.",
        acceptance_criteria=["criterion one", "criterion two"],
        relevant_files=["src/cli.py", "src/config.py"],
    )
    prompt = build_prompt(ctx)
    assert "Implement the envelope builder." in prompt
    assert "criterion one" in prompt
    assert "criterion two" in prompt
    assert "src/cli.py" in prompt
    assert "src/config.py" in prompt
    # No private artifact markers, no absolute paths, bounded (no repo dump).
    assert "catalog.db" not in prompt
    assert "C:\\" not in prompt
    assert "/home/" not in prompt
    assert len(prompt) < 6000


# 2. JULES_API_KEY value never appears in prompt / stdout / stderr / result / exception.
def test_api_key_value_never_leaks() -> None:
    secret = "SUPERSECRETKEY123"
    # redact strips the value when explicitly provided.
    cleaned = redact(f"token={secret}", api_key=secret)
    assert secret not in cleaned

    transport = FakeTransport(api_key=secret)
    result = run_dispatch(transport, _ctx())
    out = json.dumps(result)
    assert secret not in out

    # Even if an HTTP error body contained the secret, it must not surface.
    leaking = FakeTransport(
        api_key=secret, http_error=(403, f"boom {secret}", "/sources")
    )
    err_result = run_dispatch(leaking, _ctx())
    assert err_result["error_code"] == "BLOCKED_AUTH"
    assert secret not in json.dumps(err_result)


# 3. Absolute Windows paths are blocked / redacted.
def test_windows_absolute_path_blocked_and_redacted() -> None:
    with pytest.raises(jd.ContextRejected):
        validate_context(_ctx(relevant_files=["C:\\Users\\me\\file.py"]))
    cleaned = redact("see C:\\Users\\me\\secret.txt here")
    assert "C:\\Users" not in cleaned
    assert "<REDACTED_PATH>" in cleaned


# 4. Absolute Unix / home paths are blocked / redacted.
def test_unix_absolute_path_blocked_and_redacted() -> None:
    with pytest.raises(jd.ContextRejected):
        validate_context(_ctx(relevant_files=["/home/me/file.py"]))
    cleaned = redact("path /home/me/x and /Users/me/y and /root/z")
    assert "/home/me" not in cleaned
    assert "/Users/me" not in cleaned
    assert "/root/z" not in cleaned
    assert "<REDACTED_PATH>" in cleaned


# 5. Source matching requires exactly jannekbuengener/sample-brain.
def test_source_matching_exact_only() -> None:
    sources = [
        {"githubRepo": {"owner": "jannekbuengener", "repo": "sample-brain-extra"}},
        {"githubRepo": {"owner": "other", "repo": "sample-brain"}},
        SAMPLE_SOURCE,
    ]
    assert match_source(sources) == "sources/github/jannekbuengener/sample-brain"

    transport = FakeTransport(sources=[{"githubRepo": {"owner": "x", "repo": "y"}}])
    with pytest.raises(JulesError) as exc:
        resolve_source(transport)
    assert exc.value.code == "BLOCKED_SOURCE_NOT_CONNECTED"

    blocked = FakeTransport(sources=[{"githubRepo": {"owner": "x", "repo": "y"}}])
    result = run_dispatch(blocked, _ctx())
    assert result["error_code"] == "BLOCKED_SOURCE_NOT_CONNECTED"


# 6. Create payload for a write task sets requirePlanApproval = true.
def test_write_task_requires_plan_approval() -> None:
    payload = build_create_payload(_ctx(change_class="product_code"), "src/x")
    assert payload["requirePlanApproval"] is True


# 7. No automatic approve after create.
def test_no_auto_approve_after_create() -> None:
    transport = FakeTransport()
    run_dispatch(transport, _ctx())
    approve_calls = [c for c in transport.calls if c[1].endswith(":approvePlan")]
    assert approve_calls == []


# 8. AUTO_CREATE_PR only set when allow_pr.
def test_auto_create_pr_only_when_allowed() -> None:
    with_pr = build_create_payload(_ctx(allow_pr=True), "src/x")
    assert with_pr["automationMode"] == "AUTO_CREATE_PR"

    without_pr = build_create_payload(_ctx(allow_pr=False), "src/x")
    assert "automationMode" not in without_pr


# 9. AWAITING_PLAN_APPROVAL is normalized correctly.
def test_awaiting_plan_approval_normalized() -> None:
    result = normalize_dispatch("AWAITING_PLAN_APPROVAL")
    assert result["dispatch_status"] == "AWAITING_PLAN_APPROVAL"

    transport = FakeTransport(
        session={"name": "sessions/abc", "state": "AWAITING_PLAN_APPROVAL"}
    )
    dispatched = run_dispatch(transport, _ctx())
    assert dispatched["dispatch_status"] == "AWAITING_PLAN_APPROVAL"


# 10. approvePlan uses the documented endpoint.
def test_approve_uses_documented_endpoint() -> None:
    transport = FakeTransport()
    run_approve(transport, "sessions/abc")
    assert any(
        c[0] == "POST" and c[1].endswith(":approvePlan") for c in transport.calls
    )


# 11. sendMessage sanitizes text.
def test_send_message_sanitizes_text() -> None:
    transport = FakeTransport()
    run_message(transport, "sessions/abc", "KEY=topsecret C:\\Users\\me\\x")
    msg_calls = [c for c in transport.calls if c[1].endswith(":sendMessage")]
    assert len(msg_calls) == 1
    body = msg_calls[0][2]
    assert "topsecret" not in json.dumps(body)
    assert "C:\\Users" not in json.dumps(body)


# 12. Activities pagination works.
def test_activities_pagination() -> None:
    pages = [
        {
            "activities": [{"type": "progressUpdated"}],
            "nextPageToken": "page2",
        },
        {"activities": [{"type": "planGenerated", "planId": "plans/1"}]},
    ]
    transport = FakeTransport(activities_pages=pages)
    activities = get_activities(transport, "sessions/abc")
    assert len(activities) == 2
    assert activities[1]["planId"] == "plans/1"
    # Two GETs: first page (with token) then second page.
    get_calls = [c for c in transport.calls if c[0] == "GET"]
    assert len(get_calls) == 2


# 13. HTTP 401 / 403 -> BLOCKED_AUTH.
@pytest.mark.parametrize("status", [401, 403])
def test_http_401_403_blocked_auth(status: int) -> None:
    transport = FakeTransport(http_error=(status, "no", "/sources"))
    result = run_dispatch(transport, _ctx())
    assert result["error_code"] == "BLOCKED_AUTH"


# 14. HTTP 429 -> BLOCKED_RATE_LIMIT.
def test_http_429_rate_limit() -> None:
    transport = FakeTransport(http_error=(429, "slow", "/sources"))
    result = run_dispatch(transport, _ctx())
    assert result["error_code"] == "BLOCKED_RATE_LIMIT"


# 15. Timeout / 5xx -> no fake-green.
def test_timeout_and_5xx_no_fake_green() -> None:
    # No session yet: 5xx -> BLOCKED_REMOTE.
    transport = FakeTransport(http_error=(500, "x", "/sessions"))
    result = run_dispatch(transport, _ctx())
    assert result["error_code"] == "BLOCKED_REMOTE"
    assert result["dispatch_status"] != "RESULT_READY"

    # Existing session with timeout -> PARTIAL (not false green).
    timed_out = FakeTransport(transport_error="timed out")
    status_result = run_status(timed_out, "sessions/abc")
    assert status_result["dispatch_status"] == "PARTIAL"
    assert status_result["dispatch_status"] != "RESULT_READY"


# 16. Unknown API state -> PARTIAL_PROTOCOL_DRIFT.
def test_unknown_state_protocol_drift() -> None:
    transport = FakeTransport(
        session={"name": "sessions/abc", "state": "WEIRD_STATE"}
    )
    result = run_dispatch(transport, _ctx())
    assert result["dispatch_status"] == "PARTIAL_PROTOCOL_DRIFT"
    assert result["error_code"] == "PARTIAL_PROTOCOL_DRIFT"


# 17. COMPLETED + PullRequest -> RESULT_READY, never DONE / MERGED.
def test_completed_with_pr_is_result_ready() -> None:
    session = {
        "name": "sessions/abc",
        "state": "COMPLETED",
        "pullRequest": {"url": "https://github.com/x/y/pull/9"},
    }
    transport = FakeTransport(session=session)
    result = run_status(transport, "sessions/abc")
    assert result["dispatch_status"] == "RESULT_READY"
    assert "DONE" not in result["dispatch_status"]
    assert "MERGED" not in result["dispatch_status"]
    assert result["pull_request_url"] == "https://github.com/x/y/pull/9"


# 18. No merge / issue-close code exists in the runtime helper.
def test_no_merge_or_issue_close_code() -> None:
    source = jd.__file__ or "src/jules_dispatch.py"
    with open(source, "r", encoding="utf-8") as fh:
        text = fh.read().lower()
    forbidden = ["merge", "close", "merged", "closed"]
    for token in forbidden:
        assert token not in text, f"forbidden token present in helper: {token}"
