from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


def _run_cli_with_blocked_pyside6(args: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    """Run CLI in a fresh subprocess with PySide6 blocked via meta_path."""
    test_script = """
import sys

class PySide6Blocker:
    def find_spec(self, fullname, path, target=None):
        if fullname == "PySide6" or fullname.startswith("PySide6."):
            raise ModuleNotFoundError("No module named '" + fullname + "'")
        return None

sys.meta_path.insert(0, PySide6Blocker())

# Remove any cached PySide6 modules
to_remove = [k for k in sys.modules if k == "PySide6" or k.startswith("PySide6.")]
for k in to_remove:
    sys.modules.pop(k, None)

from src.cli import main

sys.argv = ["src.cli"] + {args}
main()
"""
    test_script = test_script.format(args=args)

    proc_env = {**os.environ}
    if env:
        proc_env.update(env)
    # Ensure DB path is outside repo
    proc_env.setdefault("SAMPLE_BRAIN_DB_PATH", str(Path(tempfile.gettempdir()) / "sample-brain-test-cli.db"))

    python_exe = sys.executable
    result = subprocess.run(
        [python_exe, "-c", test_script],
        capture_output=True,
        text=True,
        env=proc_env,
        timeout=60,
    )
    return result


def test_explicit_qml_screen1_fails_cleanly_when_pyside6_unavailable():
    """Explicit --qml-screen1 must fail with actionable message, no traceback, no Tk fallback."""
    result = _run_cli_with_blocked_pyside6(["workbench", "--qml-screen1"])

    # Exit code must be 1
    assert result.returncode == 1, f"Expected exit code 1, got {result.returncode}"

    stderr = result.stderr
    stdout = result.stdout

    # Must NOT contain traceback
    assert "Traceback" not in stderr, f"stderr contains Traceback:\n{stderr}"
    assert "Traceback" not in stdout, f"stdout contains Traceback:\n{stdout}"

    # Must contain actionable error message
    assert "[ERROR]" in stderr, f"stderr missing [ERROR] prefix:\n{stderr}"
    assert "Qt Quick Screen-1 Renderer nicht verfügbar" in stderr, f"stderr missing QML unavailable message:\n{stderr}"
    assert "qtquick" in stderr.lower(), f"stderr missing qtquick install hint:\n{stderr}"
    assert ".[qtquick]" in stderr, f"stderr missing .[qtquick] install hint:\n{stderr}"

    # Must NOT start Tk workbench (no Tk imports in successful path)
    # We can't easily test Tk not started in subprocess, but the behavior
    # contract is verified by the in-process test below.


def test_explicit_qml_screen1_positive_path_when_runtime_available(monkeypatch):
    """When QML runtime is available, explicit --qml-screen1 should call run_qml_screen1 normally."""
    import types
    import sys

    calls = []

    qml = types.ModuleType("src.workbench_qml")

    def mock_run_qml_screen1(*, state_id: str = "screen1-default-3panel") -> int:
        calls.append(("run_qml_screen1", state_id))
        return 0

    qml.run_qml_screen1 = mock_run_qml_screen1
    qml.qml_runtime_available = lambda: True

    workbench = types.ModuleType("src.workbench")
    workbench.run_workbench = lambda: (_ for _ in ()).throw(AssertionError("Tk fallback must not be called"))
    workbench.run_visual_acceptance = lambda **_kwargs: None

    monkeypatch.setitem(sys.modules, "src.workbench_qml", qml)
    monkeypatch.setitem(sys.modules, "src.workbench", workbench)
    monkeypatch.setattr(sys, "argv", ["sample-brain", "workbench", "--qml-screen1"])

    from src.cli import main
    main()

    assert calls == [("run_qml_screen1", "screen1-default-3panel")]


def test_explicit_qml_screen1_unexpected_error_not_masked(monkeypatch):
    """Real runtime errors from run_qml_screen1 must not be masked as missing PySide6."""
    import types
    import sys

    qml = types.ModuleType("src.workbench_qml")
    qml.qml_runtime_available = lambda: True

    def failing_run(*, state_id: str) -> int:
        raise RuntimeError("QML failed to load: invalid QML")

    qml.run_qml_screen1 = failing_run

    workbench = types.ModuleType("src.workbench")
    workbench.run_workbench = lambda: (_ for _ in ()).throw(AssertionError("Tk fallback must not be called"))
    workbench.run_visual_acceptance = lambda **_kwargs: None

    monkeypatch.setitem(sys.modules, "src.workbench_qml", qml)
    monkeypatch.setitem(sys.modules, "src.workbench", workbench)
    monkeypatch.setattr(sys, "argv", ["sample-brain", "workbench", "--qml-screen1"])

    from src.cli import main

    with pytest.raises(RuntimeError, match="invalid QML"):
        main()