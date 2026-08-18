from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src import jules_dispatch as jd


def _ctx(**overrides: Any) -> jd.DispatchContext:
    data = dict(
        repo="jannekbuengener/sample-brain",
        issue_number=424,
        issue_url="https://github.com/jannekbuengener/sample-brain/issues/424",
        base_branch="main",
        base_sha="abc123",
        change_class="product_code",
        goal="Validate dispatch containment.",
        acceptance_criteria=["validation is fail closed"],
        relevant_files=["src/jules_dispatch.py"],
        known_facts=["Sample Brain checkout is authoritative"],
        constraints=["Sample Brain only"],
        minimum_validation=["pytest"],
        allow_pr=False,
    )
    data.update(overrides)
    return jd.DispatchContext.from_dict(data)


class NoNetworkTransport:
    api_key = "dummy-key"

    def request(self, method: str, path: str, body=None):  # pragma: no cover - must not run
        raise AssertionError("validation must block before transport")


def test_wrong_repo_root_is_rejected_without_leaking_private_path(tmp_path: Path) -> None:
    private_root = tmp_path / "private-checkout-name"
    private_root.mkdir()

    with pytest.raises(jd.ContextRejected) as exc:
        jd.validate_context(_ctx(), repo_root=str(private_root))

    message = str(exc.value)
    assert str(private_root) not in message
    assert "private-checkout-name" not in message


def test_backslash_parent_traversal_is_rejected_without_echoing_value() -> None:
    private_value = r"..\private-parent\file.py"

    with pytest.raises(jd.ContextRejected) as exc:
        jd.validate_context(_ctx(relevant_files=[private_value]))

    assert private_value not in str(exc.value)
    assert "private-parent" not in str(exc.value)


def test_absolute_path_rejection_does_not_echo_private_value() -> None:
    private_value = r"C:\Users\private-user\secret.py"

    with pytest.raises(jd.ContextRejected) as exc:
        jd.validate_context(_ctx(relevant_files=[private_value]))

    assert private_value not in str(exc.value)
    assert "private-user" not in str(exc.value)


def test_run_dispatch_returns_safe_blocked_result_for_invalid_root(tmp_path: Path) -> None:
    private_root = tmp_path / "wrong-root"
    private_root.mkdir()

    result = jd.run_dispatch(NoNetworkTransport(), _ctx(), repo_root=str(private_root))

    assert result["dispatch_status"] == "BLOCKED"
    assert result["error_code"] == "BLOCKED"
    serialized = json.dumps(result)
    assert str(private_root) not in serialized
    assert "wrong-root" not in serialized


def test_symlink_escape_is_rejected_after_filesystem_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    link = root / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable on this host")

    monkeypatch.setattr(jd, "_canonical_repo_root", lambda: root.resolve())

    with pytest.raises(jd.ContextRejected):
        jd.validate_context(_ctx(relevant_files=["link/future.py"]), repo_root=str(root))


def test_nonexistent_repo_relative_path_remains_allowed() -> None:
    root = Path(jd.__file__).resolve().parents[1]
    jd.validate_context(
        _ctx(relevant_files=["future/not-created-yet.py"]), repo_root=str(root)
    )
