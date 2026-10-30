"""#1209 preferred audition output device preference + transport wiring."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import src.workbench_transport_adapter as adapter_module
from src.workbench_audio_output import (
    WorkbenchAudioOutputSettings,
    load_workbench_audio_output_settings,
    save_workbench_audio_output_settings,
    workbench_audio_output_path,
)


_VALID_ID = "ab" * 256  # 512 hex chars — native id_hex contract
_OTHER_ID = "cd" * 256


class RecordingOpenEngine:
    def __init__(self) -> None:
        self.open_calls: list[object] = []
        self.started = False
        self.closed = False
        self.stopped = False

    def open(self, config) -> None:
        self.open_calls.append(config)

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True

    def snapshot(self):
        return SimpleNamespace(engine_frame=0, running=self.started)


def test_audio_output_settings_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    assert save_workbench_audio_output_settings(
        WorkbenchAudioOutputSettings(
            preferred_output_device_id=_VALID_ID,
            preferred_output_device_name="ASUS VP247",
        )
    )
    path = workbench_audio_output_path()
    assert path.is_file()
    loaded = load_workbench_audio_output_settings()
    assert loaded.preferred_output_device_id == _VALID_ID
    assert loaded.preferred_output_device_name == "ASUS VP247"


def test_audio_output_settings_reject_nul_and_bad_schema(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    assert not save_workbench_audio_output_settings(
        WorkbenchAudioOutputSettings(
            preferred_output_device_id="bad\x00id",
            preferred_output_device_name="x",
        )
    )
    path = workbench_audio_output_path()
    path.write_text('{"schema_version": 99, "preferred_output_device_id": "x"}\n', encoding="utf-8")
    loaded = load_workbench_audio_output_settings()
    assert loaded.preferred_output_device_id == ""


def test_owned_native_open_passes_preferred_output_device(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    save_workbench_audio_output_settings(
        WorkbenchAudioOutputSettings(
            preferred_output_device_id=_VALID_ID,
            preferred_output_device_name="ASUS VP247",
        )
    )
    engine = RecordingOpenEngine()
    monkeypatch.setattr(adapter_module._native_audio, "is_available", lambda: True)
    monkeypatch.setattr(
        adapter_module._native_audio,
        "NativeAudioEngine",
        lambda: engine,
    )
    adapter = adapter_module.WorkbenchTransportAdapter(sample_rate=48_000)
    assert adapter.ensure_engine_running() is True
    assert len(engine.open_calls) == 1
    assert engine.open_calls[0].output_device == _VALID_ID
    assert engine.started is True


def test_owned_native_open_uses_os_default_when_preference_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    engine = RecordingOpenEngine()
    monkeypatch.setattr(adapter_module._native_audio, "is_available", lambda: True)
    monkeypatch.setattr(
        adapter_module._native_audio,
        "NativeAudioEngine",
        lambda: engine,
    )
    adapter = adapter_module.WorkbenchTransportAdapter(sample_rate=48_000)
    assert adapter.ensure_engine_running() is True
    assert engine.open_calls[0].output_device is None


def test_reopen_native_output_device_applies_new_preference(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    engines: list[RecordingOpenEngine] = []

    def _factory() -> RecordingOpenEngine:
        engine = RecordingOpenEngine()
        engines.append(engine)
        return engine

    monkeypatch.setattr(adapter_module._native_audio, "is_available", lambda: True)
    monkeypatch.setattr(adapter_module._native_audio, "NativeAudioEngine", _factory)
    adapter = adapter_module.WorkbenchTransportAdapter(sample_rate=48_000)
    assert adapter.ensure_engine_running() is True
    assert engines[0].open_calls[0].output_device is None

    save_workbench_audio_output_settings(
        WorkbenchAudioOutputSettings(
            preferred_output_device_id=_OTHER_ID,
            preferred_output_device_name="Other",
        )
    )
    assert adapter.reopen_native_output_device() is True
    assert engines[0].stopped is True
    assert engines[0].closed is True
    assert len(engines) == 2
    assert engines[1].open_calls[0].output_device == _OTHER_ID


def test_reopen_rebases_engine_frame_while_preserving_session(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    engines: list[RecordingOpenEngine] = []

    def _factory() -> RecordingOpenEngine:
        engine = RecordingOpenEngine()
        engines.append(engine)
        return engine

    monkeypatch.setattr(adapter_module._native_audio, "is_available", lambda: True)
    monkeypatch.setattr(adapter_module._native_audio, "NativeAudioEngine", _factory)
    adapter = adapter_module.WorkbenchTransportAdapter(sample_rate=48_000)
    assert adapter.ensure_engine_running() is True
    adapter.play()
    adapter.advance(48000)
    preserved_session = adapter.get_session_frame()
    assert preserved_session == 48000
    assert adapter.get_engine_frame() == 48000

    save_workbench_audio_output_settings(
        WorkbenchAudioOutputSettings(
            preferred_output_device_id=_VALID_ID,
            preferred_output_device_name="ASUS",
        )
    )
    assert adapter.reopen_native_output_device() is True
    assert adapter.get_session_frame() == preserved_session
    assert adapter.get_engine_frame() == 0


def test_stop_native_voice_clears_stale_ownership_after_engine_gone():
    from src.workbench_preview import WorkbenchPreviewPlayer
    from src.workbench_transport_preview import TransportAwarePreview

    class GoneEngine:
        def stop_voice(self, _voice_id: int) -> None:
            raise RuntimeError("voice gone")

        def remove_voice(self, _voice_id: int) -> None:
            raise RuntimeError("voice gone")

    transport = SimpleNamespace(
        get_native_engine=lambda: GoneEngine(),
        unregister_voice=lambda _voice_id: None,
        is_native_available=lambda: True,
        ensure_engine_running=lambda: True,
        is_sync_enabled=lambda: False,
        get_current_tempo=lambda: 120.0,
        tempo_map=SimpleNamespace(sample_rate=48000),
        set_source_bpm=lambda *a, **k: None,
        set_voice_source_bpm=lambda *a, **k: None,
        get_engine_frame=lambda: 0,
        play=lambda: None,
        stop=lambda: None,
    )
    preview = TransportAwarePreview(WorkbenchPreviewPlayer(), transport)  # type: ignore[arg-type]
    preview._active_voice_id = 7
    preview._native_current_path = SimpleNamespace()
    assert preview._stop_native_voice() is True
    assert preview.active_voice_id is None


def test_interaction_adapter_set_preferred_reopens_transport(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    from src.workbench_qml import Screen1QmlInteractionAdapter, Screen1QmlViewModel

    reopen_calls: list[bool] = []

    class FakeTransport:
        def reopen_native_output_device(self) -> bool:
            reopen_calls.append(True)
            return True

    view_model = Screen1QmlViewModel(
        state_id="screen1-default-3panel",
        library_labels=(),
        browser_rows=(),
        selected_browser_index=-1,
        harmony_rows=(),
        live_kit_groups=(),
    )
    adapter = Screen1QmlInteractionAdapter(view_model=view_model)
    quiet_calls: list[bool] = []
    adapter.quiet_audition = lambda: quiet_calls.append(True)  # type: ignore[method-assign]
    applied = adapter.set_preferred_audio_output_device(
        _VALID_ID,
        "ASUS VP247",
        transport=FakeTransport(),
    )
    assert applied == _VALID_ID
    assert quiet_calls == [True]
    assert reopen_calls == [True]
    loaded = load_workbench_audio_output_settings()
    assert loaded.preferred_output_device_id == _VALID_ID
    assert adapter.preferred_audio_output_device_name() == "ASUS VP247"


def test_display_preferences_qml_exposes_audition_output_combo():
    from src import workbench_qml

    source = workbench_qml.QML_SOURCE
    assert 'objectName: "audioOutputDeviceCombo"' in source
    assert "Audition output" in source
    assert "setPreferredAudioOutputDeviceByIndex" in source
    assert "audioOutputDeviceNames" in source


def test_invalid_preferred_id_length_is_ignored_on_open(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    save_workbench_audio_output_settings(
        WorkbenchAudioOutputSettings(
            preferred_output_device_id="too-short",
            preferred_output_device_name="bad",
        )
    )
    engine = RecordingOpenEngine()
    monkeypatch.setattr(adapter_module._native_audio, "is_available", lambda: True)
    monkeypatch.setattr(
        adapter_module._native_audio,
        "NativeAudioEngine",
        lambda: engine,
    )
    adapter = adapter_module.WorkbenchTransportAdapter(sample_rate=48_000)
    assert adapter.ensure_engine_running() is True
    assert engine.open_calls[0].output_device is None
