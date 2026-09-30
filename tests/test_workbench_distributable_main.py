from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.workbench_distributable_main import (
    _DB_ENV,
    _STATE_ENV,
    apply_windows_distributable_defaults,
)


def test_windows_defaults_set_localappdata_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    local = tmp_path / "Local"
    env = {"LOCALAPPDATA": str(local)}
    monkeypatch.setattr("src.workbench_distributable_main.sys.platform", "win32")

    state = apply_windows_distributable_defaults(env=env)

    assert state == local / "SampleBrain" / "state"
    assert env[_STATE_ENV] == str(state)
    assert env[_DB_ENV] == str(state / "catalog.db")
    assert state.is_dir()


def test_windows_defaults_preserve_existing_state_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    override = tmp_path / "custom-state"
    env = {
        "LOCALAPPDATA": str(tmp_path / "Local"),
        _STATE_ENV: str(override),
    }
    monkeypatch.setattr("src.workbench_distributable_main.sys.platform", "win32")

    state = apply_windows_distributable_defaults(env=env)

    assert Path(env[_STATE_ENV]).resolve() == override.resolve()
    assert env[_DB_ENV] == str(Path(env[_STATE_ENV]) / "catalog.db")


def test_windows_defaults_preserve_existing_db_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    local = tmp_path / "Local"
    db = tmp_path / "elsewhere" / "app.db"
    env = {"LOCALAPPDATA": str(local), _DB_ENV: str(db)}
    monkeypatch.setattr("src.workbench_distributable_main.sys.platform", "win32")

    apply_windows_distributable_defaults(env=env)

    assert env[_DB_ENV] == str(db)
    assert env[_STATE_ENV] == str(local / "SampleBrain" / "state")


def test_non_windows_defaults_are_noop(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env = {"LOCALAPPDATA": str(tmp_path / "Local")}
    monkeypatch.setattr("src.workbench_distributable_main.sys.platform", "linux")

    assert apply_windows_distributable_defaults(env=env) is None
    assert _STATE_ENV not in env
    assert _DB_ENV not in env
