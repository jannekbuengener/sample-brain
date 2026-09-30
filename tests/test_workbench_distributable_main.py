from __future__ import annotations

from pathlib import Path

import pytest

from src import workbench_qml
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


def test_screen1_background_prefers_meipass_over_repo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Frozen PyInstaller layout: _MEIPASS copy wins without a repo checkout."""
    relative = workbench_qml.SCREEN1_BACKGROUND_REFERENCE_RELATIVE
    meipass = tmp_path / "_internal"
    packed = meipass / relative
    packed.parent.mkdir(parents=True)
    payload = b"fake-screen1-background-bytes"
    packed.write_bytes(payload)

    monkeypatch.setattr(workbench_qml.sys, "_MEIPASS", str(meipass), raising=False)
    monkeypatch.setattr(workbench_qml.sys, "frozen", True, raising=False)

    resolved = workbench_qml.screen1_background_reference_path()
    assert resolved == packed
    assert resolved.read_bytes() == payload


def test_screen1_background_falls_back_to_exe_dir_when_meipass_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    relative = workbench_qml.SCREEN1_BACKGROUND_REFERENCE_RELATIVE
    exe_dir = tmp_path / "SampleBrain"
    packed = exe_dir / relative
    packed.parent.mkdir(parents=True)
    packed.write_bytes(b"exe-dir-background")

    fake_exe = exe_dir / "SampleBrain.exe"
    fake_exe.write_bytes(b"")

    monkeypatch.delattr(workbench_qml.sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(workbench_qml.sys, "frozen", True, raising=False)
    monkeypatch.setattr(workbench_qml.sys, "executable", str(fake_exe))
    monkeypatch.setenv("SAMPLE_BRAIN_DISTRIBUTABLE", "1")

    resolved = workbench_qml.screen1_background_reference_path()
    assert resolved == packed


def test_screen1_background_repo_path_unchanged_for_source_runs() -> None:
    """Editable installs keep the canonical repo asset path."""
    expected = (
        Path(workbench_qml.__file__).resolve().parents[1]
        / workbench_qml.SCREEN1_BACKGROUND_REFERENCE_RELATIVE
    )
    assert workbench_qml.screen1_background_reference_path() == expected
    assert expected.is_file()
