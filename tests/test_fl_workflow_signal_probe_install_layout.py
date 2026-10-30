"""Guard #1320 install_fl_script.ps1 source layout (no FL required)."""

from __future__ import annotations

from pathlib import Path


def test_install_script_resolves_device_script_under_device_folder():
    probe = Path("tools/fl_workflow_signal_probe")
    script = (probe / "install_fl_script.ps1").read_text(encoding="utf-8")
    device = probe / "SBWorkflowSignalProbe" / "device_SBWorkflowSignalProbe.py"
    assert device.is_file(), "device script must live under SBWorkflowSignalProbe/"
    assert "device_SBWorkflowSignalProbe.py" in script
    # Must not copy from probe root (that path does not exist).
    assert 'Join-Path $ProbeSrc "device_SBWorkflowSignalProbe.py"' not in script
    assert "Join-Path $ProbeSrc $DeviceName" in script or "$DeviceSrc" in script
    assert "Missing device script" in script
