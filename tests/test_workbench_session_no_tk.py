"""#760 QML/session path must work when tkinter is unavailable.

Runs in a subprocess so blocked-tkinter / module purges cannot poison
other tests' class identities (TEST_FREEZE ownership isinstance checks).
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_no_tk_script(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
        env={
            **dict(**{k: v for k, v in __import__("os").environ.items()}),
            "PYTHONPATH": str(REPO_ROOT),
        },
    )


def test_compose_workbench_session_without_tkinter() -> None:
    script = """
    import sys
    import types

    blocked = types.ModuleType("tkinter")

    def _fail(_name):
        raise ModuleNotFoundError("No module named 'tkinter'")

    blocked.__getattr__ = _fail  # type: ignore[attr-defined]
    sys.modules["tkinter"] = blocked
    sys.modules["tkinter.ttk"] = blocked

    from src.workbench_session import compose_workbench_session

    session = compose_workbench_session(include_tk_workbench=False)
    assert session.tk_workbench is None
    assert session.audition is not None
    assert session.qml_interaction_adapter is not None
    snap = session.audition.playback_snapshot()
    assert snap.playing is False
    print("OK_COMPOSE")
    """
    result = _run_no_tk_script(script)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "OK_COMPOSE" in result.stdout


def test_preview_telemetry_import_without_tkinter() -> None:
    script = """
    import importlib
    import sys
    import types

    blocked = types.ModuleType("tkinter")

    def _fail(_name):
        raise ModuleNotFoundError("No module named 'tkinter'")

    blocked.__getattr__ = _fail  # type: ignore[attr-defined]
    sys.modules["tkinter"] = blocked
    sys.modules["tkinter.ttk"] = blocked

    preview_mod = importlib.import_module("src.workbench_transport_preview")
    assert hasattr(preview_mod, "TransportAwarePreview")
    assert hasattr(preview_mod, "PreviewPlaybackSnapshot")
    idle = preview_mod.PreviewPlaybackSnapshot.idle()
    assert idle.progress == 0.0

    try:
        importlib.import_module("src.workbench_transport_ui")
    except ModuleNotFoundError as exc:
        assert "tkinter" in str(exc)
    else:
        raise AssertionError("workbench_transport_ui should require tkinter")
    print("OK_PREVIEW")
    """
    result = _run_no_tk_script(script)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "OK_PREVIEW" in result.stdout
