from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WIN_TOOLS = ROOT / "tools" / "windows"


def test_windows_helper_scripts_exist():
    assert (WIN_TOOLS / "start_workbench.cmd").is_file()
    assert (WIN_TOOLS / "create_workbench_desktop_shortcut.ps1").is_file()
    assert (WIN_TOOLS / "README.md").is_file()


def test_start_workbench_cmd_has_no_hardcoded_absolute_paths():
    content = (WIN_TOOLS / "start_workbench.cmd").read_text(encoding="utf-8")
    assert ".venv\\Scripts\\python.exe" in content
    assert "src.cli workbench" in content
    assert not re.search(r"[A-Za-z]:\\", content)


def test_create_shortcut_ps1_resolves_repo_relative():
    content = (WIN_TOOLS / "create_workbench_desktop_shortcut.ps1").read_text(encoding="utf-8")
    assert "Sample Brain Workbench.lnk" in content
    assert "start_workbench.cmd" in content
    assert "Start Sample Brain Local Workbench" in content
    assert "GetFolderPath('Desktop')" in content
    assert not re.search(r"[A-Za-z]:\\", content)
