from __future__ import annotations

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
