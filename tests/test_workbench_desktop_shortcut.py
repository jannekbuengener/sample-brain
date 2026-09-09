from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WIN_TOOLS = ROOT / "tools" / "windows"


def test_windows_helper_scripts_exist():
    assert (WIN_TOOLS / "start_workbench.cmd").is_file()
    assert (WIN_TOOLS / "create_workbench_desktop_shortcut.ps1").is_file()
    assert (WIN_TOOLS / "README.md").is_file()


def test_legacy_start_workbench_cmd_routes_to_verified_runtime_only():
    content = (WIN_TOOLS / "start_workbench.cmd").read_text(encoding="utf-8")
    assert "%LOCALAPPDATA%\\SampleBrain\\runtime" in content
    assert "start_runtime_workbench.cmd" in content
    assert "src.cli workbench" not in content
    assert "set \"PY=python\"" not in content
    assert not re.search(r"[A-Za-z]:\\", content)


def test_legacy_shortcut_helper_targets_existing_verified_runtime():
    content = (WIN_TOOLS / "create_workbench_desktop_shortcut.ps1").read_text(encoding="utf-8")
    assert "SampleBrain\\runtime" in content
    assert "create_runtime_workbench_shortcut.ps1" in content
    assert "start_workbench.cmd" not in content
    assert not re.search(r"[A-Za-z]:\\", content)


def test_runtime_launcher_requires_its_own_venv_and_checks_provenance():
    content = (WIN_TOOLS / "start_runtime_workbench.cmd").read_text(encoding="utf-8")
    assert ".venv\\Scripts\\python.exe" in content
    assert "set \"PY=python\"" not in content
    assert "src.runtime_provenance --check" in content
    assert "src.cli workbench" in content


def test_runtime_shortcut_is_separate_from_the_legacy_shortcut():
    content = (WIN_TOOLS / "create_runtime_workbench_shortcut.ps1").read_text(
        encoding="utf-8"
    )
    assert "Sample Brain Runtime Workbench.lnk" in content
    assert "start_runtime_workbench.cmd" in content
    assert "create_workbench_desktop_shortcut" not in content


def test_runtime_installer_uses_detached_staging_without_developer_cleanup():
    content = (WIN_TOOLS / "install_runtime_workbench.ps1").read_text(encoding="utf-8")
    assert "worktree add --detach" in content
    assert "worktree move" in content
    assert "git clean" not in content
    assert "git reset" not in content
