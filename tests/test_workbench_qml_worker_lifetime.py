"""Engine teardown owns its waveform worker and polling timers (#1143)."""

import threading

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QGuiApplication
from shiboken6 import isValid

from src import workbench_qml as qml
from src.workbench_qml_spike import build_qml_view_model_from_fixture
from src.workbench_visual_acceptance import build_screen1_visual_fixture_v1


def _model():
    model = build_qml_view_model_from_fixture(
        build_screen1_visual_fixture_v1(), "screen1-default-3panel"
    )
    return model, qml.Screen1QmlInteractionAdapter(view_model=model)


@pytest.mark.parametrize("in_flight", [False, True])
def test_destroyed_engine_releases_worker_and_timers(monkeypatch, in_flight):
    started = threading.Event()
    release = threading.Event()

    def decode(*args, **kwargs):
        started.set()
        assert release.wait(5), "test must release its synthetic decode"
        return (0.0, 1.0)

    monkeypatch.setattr(qml, "compute_waveform_envelope", decode)
    model, adapter = _model()
    app, engine, window = qml._qml_engine(model, interaction_adapter=adapter)
    loader = engine._screen1_waveform_loader
    timers = (engine._screen1_waveform_timer, engine._screen1_channel_rack_timer)
    try:
        if in_flight:
            assert loader.schedule("synthetic-lifetime-probe")
            assert started.wait(2)
        window.close()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        assert not isValid(engine)
        assert QGuiApplication.instance() is app
        assert not loader.schedule("after-engine-destruction")
        assert all(not isValid(timer) for timer in timers)
        # Teardown must return even while decode is blocked, then exit on release.
        release.set()
        loader._worker.join(2)
        assert not loader._worker.is_alive()
    finally:
        release.set()
        for timer in timers:
            if isValid(timer):
                timer.stop()
        loader.close()
        loader._worker.join(2)
        if isValid(engine):
            window.close()
            engine.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def test_qml_load_failure_closes_created_waveform_worker(monkeypatch):
    loaders = []
    original = qml.BoundedBackgroundWaveformLoader

    def capture_loader(**kwargs):
        loader = original(**kwargs)
        loaders.append(loader)
        return loader

    monkeypatch.setattr(qml, "BoundedBackgroundWaveformLoader", capture_loader)
    monkeypatch.setattr(qml, "QML_SOURCE", "invalid QML source")
    model, adapter = _model()
    # Keep the singleton application alive independently of the failed builder.
    app = QGuiApplication.instance() or QGuiApplication([])
    try:
        with pytest.raises(RuntimeError, match="keine QML"):
            qml._qml_engine(model, interaction_adapter=adapter)
        assert len(loaders) == 1
        assert not loaders[0].schedule("after-failed-load")
        loaders[0]._worker.join(2)
        assert not loaders[0]._worker.is_alive()
    finally:
        for loader in loaders:
            loader.close()
            loader._worker.join(2)
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        assert QGuiApplication.instance() is app
