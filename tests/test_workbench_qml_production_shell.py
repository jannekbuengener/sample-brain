from __future__ import annotations

import sys
import types
from pathlib import Path

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


def test_production_shell_has_no_fixture_or_acceptance_orchestration():
    from src import workbench_qml

    source = Path(workbench_qml.__file__).read_text(encoding="utf-8")

    assert "workbench_visual_acceptance" not in source
    for harness_name in (
        "run_qml_visual_acceptance",
        "run_qml_virtualization_probe",
        "validate_qml_renderer_provenance",
    ):
        assert not hasattr(workbench_qml, harness_name)


def test_spike_harness_owns_fixture_and_acceptance_operations():
    from src import workbench_qml, workbench_qml_spike

    for harness_name in (
        "run_qml_proof_spike",
        "run_qml_visual_acceptance",
        "run_qml_visual_acceptance_v2",
        "run_qml_visual_acceptance_725",
        "run_qml_visual_acceptance_744",
        "run_qml_virtualization_probe",
        "validate_qml_renderer_provenance",
        "build_qml_view_model_from_fixture_v2",
    ):
        assert hasattr(workbench_qml_spike, harness_name)
    assert workbench_qml_spike.QML_SOURCE is workbench_qml.QML_SOURCE


def _install_fake_qgui(monkeypatch, *, instance):
    qtgui = types.ModuleType("PySide6.QtGui")
    qtgui.QGuiApplication = types.SimpleNamespace(instance=lambda: instance)
    pyside6 = types.ModuleType("PySide6")
    pyside6.__path__ = []
    pyside6.QtGui = qtgui
    monkeypatch.setitem(sys.modules, "PySide6", pyside6)
    monkeypatch.setitem(sys.modules, "PySide6.QtGui", qtgui)


def test_v2_capture_fails_closed_when_qguiapplication_already_exists(monkeypatch):
    from src import workbench_qml_spike
    from src.workbench_visual_acceptance import EvidenceError

    _install_fake_qgui(monkeypatch, instance=object())
    with pytest.raises(EvidenceError, match="frischen Prozess"):
        workbench_qml_spike._require_fresh_qml_capture_process()


def test_v2_capture_allows_fresh_process_before_qt_runtime(monkeypatch):
    from src import workbench_qml_spike
    import os

    _install_fake_qgui(monkeypatch, instance=None)
    monkeypatch.delenv("QT_QUICK_BACKEND", raising=False)
    sys.modules.pop("PySide6.QtQuick", None)
    workbench_qml_spike._require_fresh_qml_capture_process()
    assert os.environ.get("QT_QUICK_BACKEND") == "software"


def test_v2_capture_rejects_preloaded_nonssoftware_qtquick(monkeypatch):
    from src import workbench_qml_spike
    from src.workbench_visual_acceptance import EvidenceError

    _install_fake_qgui(monkeypatch, instance=None)
    monkeypatch.setenv("QT_QUICK_BACKEND", "rhi")
    monkeypatch.setitem(sys.modules, "PySide6.QtQuick", types.ModuleType("PySide6.QtQuick"))
    with pytest.raises(EvidenceError, match="inkompatiblem"):
        workbench_qml_spike._require_fresh_qml_capture_process()


def test_v2_capture_rejects_unimplemented_fixture_states():
    from src import workbench_qml_spike
    from src.workbench_visual_acceptance import EvidenceError

    workbench_qml_spike._validate_v2_capture_states(
        ("screen1-active-source", "screen1-harmonic-open")
    )
    for unsupported in ("screen1-clean-start", "screen1-elastic-resized"):
        with pytest.raises(EvidenceError, match="nicht unterstützt"):
            workbench_qml_spike._validate_v2_capture_states((unsupported,))


def test_v2_capture_requires_100_percent_windows_dpi(monkeypatch):
    from src import workbench_qml_spike
    from src.workbench_visual_acceptance import EvidenceError

    monkeypatch.setattr(
        workbench_qml_spike,
        "current_windows_dpi_scale",
        lambda _hwnd: 125,
    )
    with pytest.raises(EvidenceError, match="100%-Windows-DPI-Baseline"):
        workbench_qml_spike._require_v2_capture_dpi_100(123)

    monkeypatch.setattr(
        workbench_qml_spike,
        "current_windows_dpi_scale",
        lambda _hwnd: 100,
    )
    assert workbench_qml_spike._require_v2_capture_dpi_100(123) == 100


def test_v2_density_baseline_runtime_status_never_valid_off_100():
    from src import workbench_qml_spike
    from src.workbench_visual_acceptance import EvidenceError

    assert (
        workbench_qml_spike._resolve_v2_density_runtime_status(
            dpi_scale=100, evidence_kind="baseline"
        )
        == "valid"
    )
    with pytest.raises(EvidenceError, match="100%-Windows-DPI-Baseline"):
        workbench_qml_spike._resolve_v2_density_runtime_status(
            dpi_scale=125, evidence_kind="baseline"
        )


def test_v2_density_dpi_probe_runtime_status_is_not_valid():
    from src import workbench_qml_spike

    for dpi in (100, 125, 150):
        status = workbench_qml_spike._resolve_v2_density_runtime_status(
            dpi_scale=dpi, evidence_kind="dpi_probe"
        )
        assert status == "dpi_probe"
        assert status != "valid"