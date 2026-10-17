"""The nested regression suites must own their interpreter and temporary roots."""

import inspect
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests import test_workbench_tempo_sync_grid as regression_suites


@pytest.mark.parametrize(
    "name",
    ["test_existing_preview_tests_pass", "test_session_grid_tests_pass"],
)
def test_nested_suite_owns_child_temp_root(name, tmp_path, monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="passed", stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    parent_marker = tmp_path / "parent-owned.txt"
    parent_marker.write_text("preserve", encoding="utf-8")
    target = getattr(regression_suites, name)
    kwargs = {"tmp_path": tmp_path} if "tmp_path" in inspect.signature(target).parameters else {}
    target(**kwargs)

    assert len(calls) == 1
    command, options = calls[0]
    assert command[0] == sys.executable
    assert "--basetemp" in command
    child_root = Path(command[command.index("--basetemp") + 1])
    assert child_root.parent == tmp_path
    assert child_root != tmp_path
    assert options["cwd"] == str(Path(regression_suites.__file__).resolve().parents[1])
    assert parent_marker.read_text(encoding="utf-8") == "preserve"
