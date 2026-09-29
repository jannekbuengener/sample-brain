"""#695 waveform rendering research spike — contract and classification tests."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QUICK_BACKEND", "software")

from src.workbench_waveform_research import (
    MOTION_OFF,
    MOTION_ON,
    RENDERER_CACHED,
    RENDERER_CANVAS,
    RENDERER_QSG,
    RENDERER_SHAPE,
    RENDERERS,
    build_envelopes,
    classify_from_results,
    synthetic_envelope,
)


def test_synthetic_envelope_is_deterministic_and_bounded() -> None:
    a = synthetic_envelope(7)
    b = synthetic_envelope(7)
    assert a == b
    assert len(a) == 96
    assert all(0.0 <= v <= 1.0 for v in a)
    assert synthetic_envelope(7) != synthetic_envelope(8)


def test_build_envelopes_count() -> None:
    envs = build_envelopes(12)
    assert len(envs) == 12
    assert len(envs[0]) == 96


def test_classify_hybrid_when_cached_matches_canvas() -> None:
    results = [
        {
            "renderer": RENDERER_CANVAS,
            "motion_mode": MOTION_OFF,
            "scroll_ms": 100.0,
            "active_motion_frame_ms": 0.0,
        },
        {
            "renderer": RENDERER_CACHED,
            "motion_mode": MOTION_OFF,
            "scroll_ms": 95.0,
            "active_motion_frame_ms": 0.0,
        },
        {
            "renderer": RENDERER_SHAPE,
            "motion_mode": MOTION_OFF,
            "scroll_ms": 180.0,
            "active_motion_frame_ms": 0.0,
        },
        {
            "renderer": RENDERER_QSG,
            "motion_mode": MOTION_OFF,
            "scroll_ms": 90.0,
            "active_motion_frame_ms": 0.0,
        },
        {
            "renderer": RENDERER_CANVAS,
            "motion_mode": MOTION_ON,
            "scroll_ms": 110.0,
            "active_motion_frame_ms": 2.0,
        },
        {
            "renderer": RENDERER_CACHED,
            "motion_mode": MOTION_ON,
            "scroll_ms": 100.0,
            "active_motion_frame_ms": 1.5,
        },
        {
            "renderer": RENDERER_SHAPE,
            "motion_mode": MOTION_ON,
            "scroll_ms": 200.0,
            "active_motion_frame_ms": 8.0,
        },
        {
            "renderer": RENDERER_QSG,
            "motion_mode": MOTION_ON,
            "scroll_ms": 95.0,
            "active_motion_frame_ms": 1.2,
        },
    ]
    fifty = [
        {"renderer": RENDERER_CANVAS, "virtualized": True},
        {"renderer": RENDERER_CACHED, "virtualized": True},
        {"renderer": RENDERER_QSG, "virtualized": True},
    ]
    assert classify_from_results(results, fifty) == "HYBRID_RENDERER"


def test_classify_qsg_only_on_clear_win() -> None:
    results = [
        {
            "renderer": RENDERER_CANVAS,
            "motion_mode": MOTION_OFF,
            "scroll_ms": 100.0,
            "active_motion_frame_ms": 0.0,
        },
        {
            "renderer": RENDERER_CACHED,
            "motion_mode": MOTION_OFF,
            "scroll_ms": 100.0,
            "active_motion_frame_ms": 0.0,
        },
        {
            "renderer": RENDERER_SHAPE,
            "motion_mode": MOTION_OFF,
            "scroll_ms": 150.0,
            "active_motion_frame_ms": 0.0,
        },
        {
            "renderer": RENDERER_QSG,
            "motion_mode": MOTION_OFF,
            "scroll_ms": 50.0,
            "active_motion_frame_ms": 0.0,
        },
    ]
    fifty = [{"renderer": RENDERER_QSG, "virtualized": True}]
    assert classify_from_results(results, fifty) == "MOVE_TO_SCENE_GRAPH_GEOMETRY"


def test_classify_inconclusive_without_scroll() -> None:
    assert (
        classify_from_results([], [])
        == "INCONCLUSIVE — missing baseline scroll timings"
    )


def test_canvas_benchmark_virtualizes_in_subprocess() -> None:
    pytest.importorskip("PySide6.QtQuick")
    repo = Path(__file__).resolve().parents[1]
    script = (
        "import os, json;"
        "os.environ['QT_QUICK_BACKEND']='software';"
        "from src.workbench_waveform_research import run_renderer_benchmark;"
        "r=run_renderer_benchmark(renderer='canvas', row_count=120, "
        "window_size=(1280,720), motion_mode='off');"
        "print(json.dumps({'virtualized': r.virtualized, "
        "'delegate_creations': r.delegate_creations, "
        "'pooled_timers_active': r.pooled_timers_active, "
        "'scroll_ms': r.scroll_ms}))"
    )
    env = os.environ.copy()
    env["QT_QUICK_BACKEND"] = "software"
    env["PYTHONPATH"] = str(repo)
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(repo),
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    import json

    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    assert payload["virtualized"] is True
    assert payload["delegate_creations"] < 120
    assert payload["delegate_creations"] > 0
    assert payload["pooled_timers_active"] == 0
    assert payload["scroll_ms"] >= 0.0


@pytest.mark.parametrize("renderer", RENDERERS)
def test_renderer_benchmark_subprocess_isolates_qt(renderer: str) -> None:
    """Each renderer runs in a fresh process to avoid Windows Qt COM teardown noise."""
    pytest.importorskip("PySide6.QtQuick")
    repo = Path(__file__).resolve().parents[1]
    script = (
        "import os, json;"
        "os.environ['QT_QUICK_BACKEND']='software';"
        "from src.workbench_waveform_research import run_renderer_benchmark;"
        f"r=run_renderer_benchmark(renderer={renderer!r}, row_count=100, "
        "window_size=(1280,720), motion_mode='off');"
        "print(json.dumps({'virtualized': r.virtualized, "
        "'delegate_creations': r.delegate_creations, "
        "'pooled_timers_active': r.pooled_timers_active}))"
    )
    env = os.environ.copy()
    env["QT_QUICK_BACKEND"] = "software"
    env["PYTHONPATH"] = str(repo)
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(repo),
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    import json

    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    assert payload["virtualized"] is True
    assert payload["delegate_creations"] < 100
    assert payload["pooled_timers_active"] == 0


def test_research_module_does_not_touch_production_qml_source() -> None:
    """Guard: #695 must not rewrite production QML_SOURCE."""
    research = Path(__file__).resolve().parents[1] / "src" / "workbench_waveform_research.py"
    production = Path(__file__).resolve().parents[1] / "src" / "workbench_qml.py"
    text = research.read_text(encoding="utf-8")
    assert "production QML" in text or "not production" in text.lower()
    assert "QML_SOURCE =" not in text
    prod = production.read_text(encoding="utf-8")
    assert "QML_SOURCE" in prod
