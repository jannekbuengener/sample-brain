"""#1073 import-cycle guard for the internal Sample drag seam.

``workbench_qml`` -> ``workbench_internal_sample_dnd`` -> ``live_kits_registry``
-> ``workbench_session`` -> ``workbench_qml`` formed a runtime import cycle.
The fix keeps ``live_kits_registry``'s ``WorkbenchSession`` import inside a
``TYPE_CHECKING`` block so the registry no longer pulls the session (and thus
``workbench_qml``) back in at import time.

These run in fresh interpreters so partially-initialized modules from the
pytest process cannot mask a real cycle.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_imports(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
        env={**dict(os.environ), "PYTHONPATH": str(REPO_ROOT)},
    )


def _assert_clean(result: subprocess.CompletedProcess[str], token: str) -> None:
    assert result.returncode == 0, (
        f"import failed (rc={result.returncode})\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert token in result.stdout


def test_workbench_qml_imports_without_cycle() -> None:
    script = """
    import src.workbench_qml  # noqa: F401
    print("OK_QML")
    """
    _assert_clean(_run_imports(script), "OK_QML")


def test_live_kits_registry_imports_directly() -> None:
    script = """
    from src.live_kits_registry import LiveKitPackageRow
    assert LiveKitPackageRow is not None
    print("OK_REGISTRY")
    """
    _assert_clean(_run_imports(script), "OK_REGISTRY")


def test_live_kits_registry_does_not_pull_workbench_session_at_runtime() -> None:
    script = """
    import sys
    import src.live_kits_registry  # noqa: F401
    assert "src.workbench_session" not in sys.modules, (
        "live_kits_registry must not import workbench_session at runtime; "
        "the WorkbenchSession import must stay inside TYPE_CHECKING"
    )
    print("OK_NO_SESSION")
    """
    _assert_clean(_run_imports(script), "OK_NO_SESSION")


def test_internal_sample_contract_imports_independently() -> None:
    script = """
    import src.workbench_internal_sample_dnd as mod
    assert hasattr(mod, "apply_internal_sample_drop")
    assert hasattr(mod, "InternalSampleDropSession")
    print("OK_CONTRACT")
    """
    _assert_clean(_run_imports(script), "OK_CONTRACT")


def test_cycle_order_live_kits_first_then_contract_then_qml() -> None:
    script = """
    import src.live_kits_registry  # noqa: F401
    import src.workbench_internal_sample_dnd  # noqa: F401
    import src.workbench_qml  # noqa: F401
    import src.workbench_session  # noqa: F401
    print("OK_CYCLE_FORWARD")
    """
    _assert_clean(_run_imports(script), "OK_CYCLE_FORWARD")


def test_cycle_order_qml_first_then_live_kits() -> None:
    script = """
    import src.workbench_qml  # noqa: F401
    import src.live_kits_registry  # noqa: F401
    import src.workbench_session  # noqa: F401
    print("OK_CYCLE_REVERSE")
    """
    _assert_clean(_run_imports(script), "OK_CYCLE_REVERSE")
