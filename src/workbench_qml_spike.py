"""Compatibility harness for the accepted QML proof and visual acceptance.

The production renderer lives in :mod:`src.workbench_qml`. This module keeps
the established proof CLI and test imports while deliberately owning no shell.
"""

from .workbench_qml import (
    QML_SOURCE,
    QmlBrowserRow,
    QmlLiveKitGroup,
    QmlLiveKitSlot,
    Screen1QmlInteractionAdapter,
    Screen1QmlViewModel,
    VirtualRowWindow,
    _qml_engine,
    _settle_qml_frame,
    qml_runtime_available,
    run_qml_screen1,
    run_qml_virtualization_probe,
    run_qml_visual_acceptance,
    validate_qml_renderer_provenance,
    virtual_row_window,
)

run_qml_proof_spike = run_qml_screen1

__all__ = [
    "QML_SOURCE",
    "QmlBrowserRow",
    "QmlLiveKitGroup",
    "QmlLiveKitSlot",
    "Screen1QmlInteractionAdapter",
    "Screen1QmlViewModel",
    "VirtualRowWindow",
    "qml_runtime_available",
    "run_qml_proof_spike",
    "run_qml_virtualization_probe",
    "run_qml_visual_acceptance",
    "validate_qml_renderer_provenance",
    "virtual_row_window",
]
