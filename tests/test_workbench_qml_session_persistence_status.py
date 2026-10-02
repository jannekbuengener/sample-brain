"""TEST_GATE / TEST_FREEZE — QML projects Python persistence status (#819).

Thin projection only: QML must not invent a second status state machine.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")


def test_qml_persistence_bridge_projects_python_owned_status(tmp_path: Path) -> None:
    from src.workbench_qml import _qml_session_persistence_bridge
    from src.workbench_session import compose_workbench_session
    from src.workbench_session_store import PERSISTENCE_STATUS_FRESH_MISSING

    session = compose_workbench_session(state_dir=tmp_path)
    try:
        bridge = _qml_session_persistence_bridge(session)
        assert bridge.statusCode == PERSISTENCE_STATUS_FRESH_MISSING
        assert bridge.attention is False
        assert "\\" not in bridge.statusLabel
        assert "C:" not in bridge.statusLabel
        assert "D:" not in bridge.statusLabel
        assert "Traceback" not in bridge.statusLabel
    finally:
        session.transport.close()


def test_qml_persistence_bridge_projects_rejected_corrupt(tmp_path: Path) -> None:
    from src.workbench_qml import _qml_session_persistence_bridge
    from src.workbench_session import compose_workbench_session
    from src.workbench_session_store import (
        PERSISTENCE_STATUS_REJECTED_CORRUPT,
        workbench_session_path,
    )

    path = workbench_session_path(state_dir=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json", encoding="utf-8")

    session = compose_workbench_session(state_dir=tmp_path)
    try:
        bridge = _qml_session_persistence_bridge(session)
        assert bridge.statusCode == PERSISTENCE_STATUS_REJECTED_CORRUPT
        assert bridge.attention is True
        assert bridge.statusLabel
        assert str(tmp_path) not in bridge.statusLabel
    finally:
        session.transport.close()


def test_qml_persistence_bridge_refresh_after_autosave_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src import workbench_session_store as store_mod
    from src.workbench_controller import WorkbenchRow
    from src.workbench_qml import _qml_session_persistence_bridge
    from src.workbench_session import compose_workbench_session
    from src.workbench_session_store import (
        PERSISTENCE_STATUS_AUTOSAVE_FAILED,
        PERSISTENCE_STATUS_RESTORED_OK,
        workbench_session_path,
    )

    kick = str(tmp_path / "kick.wav")
    Path(kick).write_bytes(b"RIFF")
    a = compose_workbench_session(state_dir=tmp_path)
    a.live_kit.assign(
        "Kick + Bass",
        "Kick",
        WorkbenchRow(
            display_name="kick.wav",
            relative_path="kick.wav",
            path=kick,
            bpm=None,
            key=None,
            key_conf=None,
            loudness=None,
            brightness=None,
            sample_class=None,
            pred_type=None,
            status="ok",
            details={},
        ),
    )
    a.transport.close()

    session = compose_workbench_session(state_dir=tmp_path)
    bridge = _qml_session_persistence_bridge(session)
    assert bridge.statusCode == PERSISTENCE_STATUS_RESTORED_OK
    assert bridge.attention is False

    def boom(src, dst):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(store_mod.os, "replace", boom)
    session.live_kit.assign(
        "Melodic",
        "Pad",
        WorkbenchRow(
            display_name="pad.wav",
            relative_path="pad.wav",
            path=str(tmp_path / "pad.wav"),
            bpm=None,
            key=None,
            key_conf=None,
            loudness=None,
            brightness=None,
            sample_class=None,
            pred_type=None,
            status="ok",
            details={},
        ),
    )
    bridge.refresh()
    assert session.persistence_status == PERSISTENCE_STATUS_AUTOSAVE_FAILED
    assert bridge.statusCode == PERSISTENCE_STATUS_AUTOSAVE_FAILED
    assert bridge.attention is True
    data = json.loads(
        workbench_session_path(state_dir=tmp_path).read_text(encoding="utf-8")
    )
    assert data["live_kit"]["Kick + Bass"]["Kick"]["path"] == kick
    session.transport.close()


def test_qml_engine_retains_persistence_bridge_on_injected_adapter_path() -> None:
    """Injected-adapter harnesses must keep sessionPersistenceModel reachable."""
    from src.workbench_qml import (
        Screen1QmlInteractionAdapter,
        Screen1QmlViewModel,
        _qml_engine,
        _settle_qml_frame,
    )

    view_model = Screen1QmlViewModel.baseline("screen1-default-3panel")
    adapter = Screen1QmlInteractionAdapter(view_model=view_model)
    app, engine, window = _qml_engine(view_model, interaction_adapter=adapter)
    window.show()
    _settle_qml_frame(app)
    try:
        bridge = engine.rootContext().contextProperty("sessionPersistenceModel")
        retained = getattr(engine, "_screen1_session_persistence_bridge", None)
        assert bridge is not None
        assert retained is bridge
        assert bridge.statusCode == "fresh_missing"
        assert bridge.attention is False
    finally:
        window.close()
        engine.deleteLater()


def test_qml_runtime_persistence_status_label_calm_attention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Agent visual evidence: calm header label visible only for non-OK status."""
    from PySide6.QtQuick import QQuickItem

    from src.workbench_qml import Screen1QmlViewModel, _qml_engine, _settle_qml_frame
    from src.workbench_session_store import (
        PERSISTENCE_STATUS_REJECTED_CORRUPT,
        WORKBENCH_SESSION_FILENAME,
        persistence_status_label,
    )

    state_dir = tmp_path / "wb_state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / WORKBENCH_SESSION_FILENAME).write_text("{not-json", encoding="utf-8")
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(state_dir))

    view_model = Screen1QmlViewModel.baseline("screen1-default-3panel")
    app, engine, window = _qml_engine(view_model)
    window.show()
    _settle_qml_frame(app)
    try:
        bridge = engine.rootContext().contextProperty("sessionPersistenceModel")
        assert bridge is not None
        assert bridge.statusCode == PERSISTENCE_STATUS_REJECTED_CORRUPT
        assert bridge.attention is True
        label = window.findChild(QQuickItem, "sessionPersistenceStatusLabel")
        assert label is not None
        assert bool(label.property("visible")) is True
        assert str(label.property("text")) == persistence_status_label(
            PERSISTENCE_STATUS_REJECTED_CORRUPT
        )
        assert str(tmp_path) not in str(label.property("text"))
        # No redesign tokens: secondary text size stays compact header chrome.
        assert int(label.property("font").pixelSize()) <= 12
    finally:
        transport = getattr(engine, "_screen1_transport", None)
        if transport is not None:
            transport.close()
        window.close()
        engine.deleteLater()
