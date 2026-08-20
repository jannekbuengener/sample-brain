from __future__ import annotations

import json

import pytest

from src import jules_dispatch as jd
from src.jules_dispatch import DispatchContext, build_create_payload, create_session


def _ctx(**overrides) -> DispatchContext:
    data = dict(
        repo="jannekbuengener/sample-brain",
        issue_number=999,
        issue_url="https://github.com/jannekbuengener/sample-brain/issues/999",
        base_branch="main",
        base_sha="abc123",
        change_class="product_code",
        goal=r"Inspect C:\Users\me\private\track.wav and TOKEN=top-secret",
        acceptance_criteria=[r"Do not expose /home/me/private/sample.wav"],
        relevant_files=["src/cli.py"],
        known_facts=[r"local cache is D:\Private\cache"],
        constraints=["keep API_KEY=another-secret private"],
        minimum_validation=["python -m pytest -q"],
        allow_pr=False,
    )
    data.update(overrides)
    return DispatchContext(**data)


class _CaptureTransport:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.body = None

    def request(self, method: str, path: str, body=None):
        assert method == "POST"
        assert path == "/sessions"
        self.body = body
        return {"name": "sessions/1", "state": "QUEUED"}


class _NoNetworkTransport:
    api_key = "dummy-key"

    def __init__(self) -> None:
        self.calls = 0

    def request(self, method: str, path: str, body=None):
        self.calls += 1
        raise AssertionError("sensitive outbound content must block before transport")


class _SafeDispatchTransport:
    api_key = "dummy-key"

    def __init__(self) -> None:
        self.calls = []

    def request(self, method: str, path: str, body=None):
        self.calls.append((method, path, body))
        if method == "GET" and path == "/sources":
            return {
                "sources": [
                    {
                        "name": "sources/github/jannekbuengener/sample-brain",
                        "githubRepo": {
                            "owner": "jannekbuengener",
                            "repo": "sample-brain",
                        },
                    }
                ]
            }
        if method == "POST" and path == "/sessions":
            return {"name": "sessions/1", "state": "QUEUED"}
        raise AssertionError(f"unexpected transport call: {method} {path}")


def test_build_create_payload_redacts_paths_and_secret_assignments() -> None:
    payload = build_create_payload(_ctx(), "sources/sample-brain")
    prompt = payload["prompt"]

    assert "C:\\Users" not in prompt
    assert "/home/me" not in prompt
    assert "D:\\Private" not in prompt
    assert "top-secret" not in prompt
    assert "another-secret" not in prompt
    assert "<REDACTED_PATH>" in prompt
    assert "<REDACTED_SECRET>" in prompt


def test_create_session_redacts_bare_configured_api_key_from_prompt() -> None:
    api_key = "jules-live-key-value-123"
    transport = _CaptureTransport(api_key)
    ctx = _ctx(goal=f"Use this exact value only for diagnosis: {api_key}")

    create_session(transport, ctx, "sources/sample-brain")

    assert transport.body is not None
    prompt = transport.body["prompt"]
    assert api_key not in prompt
    assert "<REDACTED_SECRET>" in prompt


@pytest.mark.parametrize(
    "sensitive_value",
    [
        "password=hunter2",
        "Authorization: Bearer " + "ghp_" + "A" * 36,
        "Bearer " + "eyJhbGciOiJIUzI1NiJ9" + ".payload.signature",
        "github_token=" + "github_pat_" + "A" * 30,
        "AWS_ACCESS_KEY_ID=" + "AKIA" + "A" * 16,
        "GOOGLE_API_KEY=" + "AIza" + "A" * 35,
    ],
)
def test_build_create_payload_cleans_known_credential_patterns(
    sensitive_value: str,
) -> None:
    payload = build_create_payload(_ctx(goal=f"Handle {sensitive_value}"), "sources/x")
    prompt = payload["prompt"]

    assert sensitive_value not in prompt
    assert "<REDACTED_SECRET>" in prompt


def test_build_create_payload_redacts_windows_path_with_spaces() -> None:
    private_path = r"C:\Users\Jannek Doe\private.wav"

    prompt = build_create_payload(
        _ctx(goal=f"Inspect {private_path}"), "sources/x"
    )["prompt"]

    assert private_path not in prompt
    assert "Jannek Doe" not in prompt
    assert "private.wav" not in prompt
    assert "<REDACTED_PATH>" in prompt


def test_unredactable_sensitive_content_fails_closed_deterministically() -> None:
    private_key_marker = "-----BEGIN " + "PRIVATE KEY-----"

    with pytest.raises(jd.JulesError) as exc:
        build_create_payload(
            _ctx(goal=f"Use {private_key_marker}"), "sources/x"
        )

    assert exc.value.code == "BLOCKED_SENSITIVE_OUTBOUND"
    assert private_key_marker not in str(exc.value)


def test_run_dispatch_blocks_sensitive_content_before_any_transport() -> None:
    private_key_marker = "-----BEGIN " + "PRIVATE KEY-----"
    transport = _NoNetworkTransport()

    result = jd.run_dispatch(
        transport,
        _ctx(goal=f"Use {private_key_marker}"),
    )

    assert result["dispatch_status"] == "BLOCKED"
    assert result["error_code"] == "BLOCKED_SENSITIVE_OUTBOUND"
    assert transport.calls == 0
    assert private_key_marker not in json.dumps(result)


def test_run_message_blocks_sensitive_content_before_any_transport() -> None:
    private_key_marker = "-----BEGIN " + "PRIVATE KEY-----"
    transport = _NoNetworkTransport()

    result = jd.run_message(transport, "sessions/1", private_key_marker)

    assert result["dispatch_status"] == "BLOCKED"
    assert result["error_code"] == "BLOCKED_SENSITIVE_OUTBOUND"
    assert transport.calls == 0


def test_safe_prompt_still_dispatches_normally() -> None:
    transport = _SafeDispatchTransport()
    ctx = _ctx(
        goal="Implement a bounded repository change.",
        acceptance_criteria=["Focused tests pass."],
        known_facts=["The repository contract is authoritative."],
        constraints=["Keep the change scoped."],
    )

    result = jd.run_dispatch(transport, ctx)

    assert result["dispatch_status"] == "CREATED"
    assert [call[:2] for call in transport.calls] == [
        ("GET", "/sources"),
        ("POST", "/sessions"),
    ]


def test_prompt_does_not_make_unproven_safety_claims() -> None:
    prompt = jd.build_prompt(
        _ctx(
            goal="Implement a bounded repository change.",
            acceptance_criteria=["Focused tests pass."],
            known_facts=["The repository contract is authoritative."],
            constraints=["Keep the change scoped."],
        )
    )

    assert "no secret values are present in this task" not in prompt
    assert "no private local paths are referenced" not in prompt
