from __future__ import annotations

import sys
import types

import pytest


def test_production_shell_owns_the_shared_renderer_and_minimal_chrome():
    from src import workbench_qml, workbench_qml_spike

    assert workbench_qml_spike.QML_SOURCE is workbench_qml.QML_SOURCE
    assert "Sample Brain" in workbench_qml.QML_SOURCE
    for required in ("MASTER", "GRID", "SYNC"):
        assert required in workbench_qml.QML_SOURCE
    for forbidden in ("proof spike", "LIVE KIT READY", "Tools", "Ansicht", "Edit"):
        assert forbidden not in workbench_qml.QML_SOURCE


def test_explicit_production_qml_start_never_falls_back_to_tk(monkeypatch):
    from src import cli

    tk_started: list[bool] = []
    qml = types.ModuleType("src.workbench_qml")

    def unavailable(*, state_id: str) -> int:
        raise RuntimeError("Qt Quick Production Renderer nicht verfügbar")

    qml.run_qml_screen1 = unavailable
    workbench = types.ModuleType("src.workbench")
    workbench.run_workbench = lambda: tk_started.append(True)
    workbench.run_visual_acceptance = lambda **_kwargs: None
    monkeypatch.setitem(sys.modules, "src.workbench_qml", qml)
    monkeypatch.setitem(sys.modules, "src.workbench", workbench)
    monkeypatch.setattr(sys, "argv", ["sample-brain", "workbench", "--qml-screen1"])

    with pytest.raises(RuntimeError, match="Production Renderer"):
        cli.main()

    assert tk_started == []


def test_production_and_proof_flags_are_mutually_exclusive(monkeypatch):
    from src import cli

    monkeypatch.setattr(
        sys,
        "argv",
        ["sample-brain", "workbench", "--qml-screen1", "--qml-proof-spike"],
    )

    with pytest.raises(SystemExit) as error:
        cli.main()

    assert error.value.code == 2
