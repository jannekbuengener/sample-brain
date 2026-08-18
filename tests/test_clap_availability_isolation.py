from __future__ import annotations

import subprocess
from types import SimpleNamespace

from src import embed


def test_clap_available_uses_child_python_process(monkeypatch) -> None:
    calls: list[tuple[list[str], dict]] = []

    def fake_run(args, **kwargs):
        calls.append((list(args), dict(kwargs)))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(embed.subprocess, "run", fake_run, raising=False)

    assert embed._clap_available() is True
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] == embed.sys.executable
    assert args[1] == "-c"
    assert "import torch" in args[2]
    assert "import transformers" in args[2]
    assert kwargs["timeout"] > 0
    assert kwargs["stdout"] is subprocess.DEVNULL
    assert kwargs["stderr"] is subprocess.DEVNULL


def test_clap_available_returns_false_for_fatal_child_exit(monkeypatch) -> None:
    monkeypatch.setattr(
        embed.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=3221225477),
        raising=False,
    )

    assert embed._clap_available() is False


def test_clap_available_returns_false_for_probe_timeout(monkeypatch) -> None:
    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="python", timeout=10)

    monkeypatch.setattr(embed.subprocess, "run", timeout, raising=False)

    assert embed._clap_available() is False
