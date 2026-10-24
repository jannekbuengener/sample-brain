"""The nested regression suites must own their interpreter and temporary roots."""

import inspect
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests import test_workbench_tempo_sync_grid as regression_suites


@pytest.mark.parametrize(
    ("name", "child_root_name"),
    [
        ("test_existing_preview_tests_pass", "preview-pytest"),
        ("test_session_grid_tests_pass", "session-grid-pytest"),
    ],
)
def test_nested_suite_owns_child_temp_root(
    name, child_root_name, tmp_path, monkeypatch
):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="passed", stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    parent_marker = tmp_path / "parent-owned.txt"
    parent_marker.write_text("preserve", encoding="utf-8")
    expected_child_root = tmp_path / child_root_name
    expected_child_root.mkdir()
    target = getattr(regression_suites, name)
    kwargs = {"tmp_path": tmp_path} if "tmp_path" in inspect.signature(target).parameters else {}
    target(**kwargs)

    assert len(calls) == 1
    command, options = calls[0]
    assert command[0] == sys.executable
    assert "--basetemp" in command
    child_root = Path(command[command.index("--basetemp") + 1])
    assert child_root == expected_child_root
    assert child_root.parent == tmp_path
    assert child_root != tmp_path
    assert options["cwd"] == str(Path(regression_suites.__file__).resolve().parents[1])
    assert parent_marker.read_text(encoding="utf-8") == "preserve"


def test_nested_child_uses_explicit_parent_root_for_session_provenance(tmp_path):
    child_root = tmp_path / "nested-provenance-pytest"
    child_root.mkdir()
    sentinel = tmp_path / "parent-sentinel.txt"
    sentinel.write_text("parent-owned", encoding="utf-8")

    result = regression_suites._run_nested_pytest(
        "tests/test_workbench_library_cleanup_guard.py::"
        "test_current_pytest_basetemp_roots_fixture_uses_public_pytest_api",
        child_root,
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert child_root != tmp_path
    assert child_root.parent == tmp_path
    assert sentinel.exists()
    assert sentinel.read_text(encoding="utf-8") == "parent-owned"
