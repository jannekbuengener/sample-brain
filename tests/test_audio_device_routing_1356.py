"""#1356 / #1346 — selected output must equal persisted/resolved/opened route.

Regression: sticky preferred-device persistence must not allow the UI to claim
OS default / Steinberg while the transport still opens a different device (ASUS).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import src.workbench_transport_adapter as adapter_module
from src.audio_device_authority import (
    AudioDeviceRoute,
    resolve_audio_output_route,
)
from src.workbench_audio_output import (
    WorkbenchAudioOutputSettings,
    load_workbench_audio_output_settings,
    save_workbench_audio_output_settings,
)
from src.workbench_qml import Screen1QmlInteractionAdapter, Screen1QmlViewModel


_ASUS_ID = "aa" * 256
_STEIN_ID = "bb" * 256


def _devices():
    return [
        {"id_hex": _ASUS_ID, "name": "4 - ASUS VP247 (AMD High Definition Audio Device)", "is_default": False},
        {"id_hex": _STEIN_ID, "name": "Line (Steinberg CI1)", "is_default": True},
    ]


class RecordingOpenEngine:
    def __init__(self) -> None:
        self.open_calls: list[object] = []
        self.started = False
        self.closed = False
        self.stopped = False
        self._opened_output_device: str | None = None
        self._opened_output_name: str = ""

    def open(self, config) -> None:
        self.open_calls.append(config)
        self._opened_output_device = getattr(config, "output_device", None)
        # Mirror native name echo for Device Truth tests.
        if self._opened_output_device == _STEIN_ID:
            self._opened_output_name = "Line (Steinberg CI1)"
        elif self._opened_output_device == _ASUS_ID:
            self._opened_output_name = "4 - ASUS VP247 (AMD High Definition Audio Device)"
        else:
            self._opened_output_name = ""

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True

    def snapshot(self):
        return SimpleNamespace(
            engine_frame=0,
            running=self.started,
            sample_rate=48000,
            buffer_frames=256,
            device_status=0,
            xrun_count=0,
            underflow_count=0,
            overflow_count=0,
        )

    @property
    def opened_output_device_id(self) -> str | None:
        return self._opened_output_device

    @property
    def opened_output_device_name(self) -> str:
        return self._opened_output_name


def _adapter_vm() -> Screen1QmlInteractionAdapter:
    view_model = Screen1QmlViewModel(
        state_id="screen1-default-3panel",
        library_labels=(),
        browser_rows=(),
        selected_browser_index=-1,
        harmony_rows=(),
        live_kit_groups=(),
    )
    return Screen1QmlInteractionAdapter(view_model=view_model)


def test_ui_must_not_claim_system_default_when_preferred_id_missing(tmp_path, monkeypatch):
    """UI lie that made Steinberg/OS-default appear selected while ASUS stayed active."""
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    save_workbench_audio_output_settings(
        WorkbenchAudioOutputSettings(
            preferred_output_device_id=_ASUS_ID,
            preferred_output_device_name="4 - ASUS VP247 (AMD High Definition Audio Device)",
        )
    )
    monkeypatch.setattr("src.native_audio.is_available", lambda: True)
    monkeypatch.setattr(
        "src.native_audio.NativeAudioEngine.enumerate_devices",
        # ASUS missing from live enumeration — preferred id still persisted
        lambda capture=False: [
            {
                "id_hex": _STEIN_ID,
                "name": "Line (Steinberg CI1)",
                "is_default": True,
            }
        ],
    )
    adapter = _adapter_vm()
    devices = adapter.list_audio_output_devices()
    preferred = adapter.preferred_audio_output_device_id()
    index = adapter.preferred_audio_output_device_index(devices)

    assert preferred == _ASUS_ID
    assert index != 0, "must not report System default while a preferred id remains active"
    selected = devices[index]
    assert "ASUS" in str(selected.get("name") or "")
    assert selected.get("unavailable") is True


def test_system_default_entry_names_resolved_os_default_device(monkeypatch):
    adapter = _adapter_vm()
    monkeypatch.setattr(
        "src.native_audio.is_available",
        lambda: True,
    )
    monkeypatch.setattr(
        "src.native_audio.NativeAudioEngine.enumerate_devices",
        lambda capture=False: _devices(),
    )
    devices = adapter.list_audio_output_devices()
    assert devices[0]["id"] == ""
    assert "Steinberg" in str(devices[0]["name"])
    assert devices[0].get("resolved_default_id") == _STEIN_ID


def test_selecting_steinberg_replaces_sticky_asus_preference(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    save_workbench_audio_output_settings(
        WorkbenchAudioOutputSettings(
            preferred_output_device_id=_ASUS_ID,
            preferred_output_device_name="ASUS VP247",
        )
    )
    engines: list[RecordingOpenEngine] = []

    class _Factory:
        @staticmethod
        def enumerate_devices(capture: bool = False):
            return _devices()

        def __call__(self) -> RecordingOpenEngine:
            engine = RecordingOpenEngine()
            engines.append(engine)
            return engine

    monkeypatch.setattr(adapter_module._native_audio, "is_available", lambda: True)
    monkeypatch.setattr(adapter_module._native_audio, "NativeAudioEngine", _Factory())
    transport = adapter_module.WorkbenchTransportAdapter(sample_rate=48_000)
    assert transport.ensure_engine_running() is True
    assert engines[0].open_calls[0].output_device == _ASUS_ID

    interaction = _adapter_vm()
    applied = interaction.set_preferred_audio_output_device(
        _STEIN_ID,
        "Line (Steinberg CI1)",
        transport=transport,
    )
    assert applied == _STEIN_ID
    loaded = load_workbench_audio_output_settings()
    assert loaded.preferred_output_device_id == _STEIN_ID
    assert loaded.preferred_output_device_name == "Line (Steinberg CI1)"
    assert len(engines) == 2
    assert engines[1].open_calls[0].output_device == _STEIN_ID
    route = transport.audio_output_route()
    assert route.requested_device_id == _STEIN_ID
    assert route.opened_device_id == _STEIN_ID
    assert route.ui_matches_opened is True


def test_resolve_route_detects_requested_vs_opened_divergence():
    route = resolve_audio_output_route(
        preferred_id=_STEIN_ID,
        preferred_name="Line (Steinberg CI1)",
        enumerated=_devices(),
        opened_device_id=_ASUS_ID,
    )
    assert isinstance(route, AudioDeviceRoute)
    assert route.requested_device_id == _STEIN_ID
    assert route.resolved_device_id == _STEIN_ID
    assert route.opened_device_id == _ASUS_ID
    assert route.ui_matches_opened is False
    assert route.divergence == "opened_mismatch"


def test_fresh_adapter_restart_preserves_steinberg_selection(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    save_workbench_audio_output_settings(
        WorkbenchAudioOutputSettings(
            preferred_output_device_id=_STEIN_ID,
            preferred_output_device_name="Line (Steinberg CI1)",
        )
    )
    engines: list[RecordingOpenEngine] = []

    def _factory() -> RecordingOpenEngine:
        engine = RecordingOpenEngine()
        engines.append(engine)
        return engine

    monkeypatch.setattr(adapter_module._native_audio, "is_available", lambda: True)
    monkeypatch.setattr(adapter_module._native_audio, "NativeAudioEngine", _factory)
    first = adapter_module.WorkbenchTransportAdapter(sample_rate=48_000)
    assert first.ensure_engine_running() is True
    first.stop()

    second = adapter_module.WorkbenchTransportAdapter(sample_rate=48_000)
    assert second.ensure_engine_running() is True
    assert engines[-1].open_calls[0].output_device == _STEIN_ID
    assert second.audio_output_route().opened_device_id == _STEIN_ID


def test_display_preferences_combo_resyncs_current_index():
    from src import workbench_qml

    source = workbench_qml.QML_SOURCE
    assert 'objectName: "audioOutputDeviceCombo"' in source
    assert "preferredAudioOutputDeviceIndex" in source
    # Binding-only currentIndex is insufficient; must re-assert after model changes.
    assert "audioOutputDeviceCombo.currentIndex =" in source or "resyncAudioOutputCombo" in source


def test_audio_system_defaults_to_sample_brain_audio(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    from src.workbench_audio_output import (
        AUDIO_SYSTEM_SAMPLE_BRAIN_AUDIO,
        WorkbenchAudioOutputSettings,
        load_workbench_audio_output_settings,
        save_workbench_audio_output_settings,
    )

    assert save_workbench_audio_output_settings(
        WorkbenchAudioOutputSettings(
            preferred_output_device_id=_STEIN_ID,
            preferred_output_device_name="Line (Steinberg CI1)",
        )
    )
    loaded = load_workbench_audio_output_settings()
    assert loaded.audio_system == AUDIO_SYSTEM_SAMPLE_BRAIN_AUDIO
    # Legacy schema-1 files without audio_system still load as Sample Brain Audio.
    path = tmp_path / "workbench_audio_output.json"
    path.write_text(
        '{"schema_version": 1, "preferred_output_device_id": "", "preferred_output_device_name": ""}\n',
        encoding="utf-8",
    )
    legacy = load_workbench_audio_output_settings()
    assert legacy.audio_system == AUDIO_SYSTEM_SAMPLE_BRAIN_AUDIO


def test_routing_evidence_exposes_required_inspectable_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    engines: list[RecordingOpenEngine] = []

    class _Factory:
        @staticmethod
        def enumerate_devices(capture: bool = False):
            return _devices()

        def __call__(self) -> RecordingOpenEngine:
            engine = RecordingOpenEngine()
            engines.append(engine)
            return engine

    monkeypatch.setattr(adapter_module._native_audio, "is_available", lambda: True)
    monkeypatch.setattr(adapter_module._native_audio, "NativeAudioEngine", _Factory())
    save_workbench_audio_output_settings(
        WorkbenchAudioOutputSettings(
            preferred_output_device_id=_STEIN_ID,
            preferred_output_device_name="Line (Steinberg CI1)",
        )
    )
    transport = adapter_module.WorkbenchTransportAdapter(sample_rate=48_000)
    assert transport.ensure_engine_running() is True
    evidence = transport.audio_routing_evidence()
    for key in (
        "audio_system",
        "requested_device",
        "resolved_device",
        "opened_backend",
        "opened_device",
        "sample_rate",
        "buffer_size",
        "device_status",
        "engine_running",
        "measurable_output",
    ):
        assert key in evidence
    assert evidence["audio_system"] == "sample_brain_audio"
    assert evidence["opened_backend"] == "wasapi"
    assert evidence["requested_device"] == _STEIN_ID
    assert evidence["opened_device"] == _STEIN_ID
    assert evidence["requested_device_id"] == _STEIN_ID
    assert evidence["opened_device_id"] == _STEIN_ID
    assert evidence["opened_device_name"] == "Line (Steinberg CI1)"
    assert evidence["sample_rate"] == 48000
    assert evidence["buffer_size"] == 256
    assert evidence["engine_running"] is True
    assert evidence["ui_matches_opened"] is True


def test_native_opened_output_device_matches_requested_when_available():
    from src import native_audio

    if not native_audio.is_available():
        pytest.skip("native audio DLL unavailable")
    if not hasattr(native_audio._lib, "sb_engine_get_opened_output_device"):
        pytest.skip("opened-device API missing from DLL")
    devices = native_audio.NativeAudioEngine.enumerate_devices(False)
    if not devices:
        pytest.skip("no playback devices")
    target = devices[0]
    engine = native_audio.NativeAudioEngine()
    engine.open(
        native_audio.EngineConfig(
            sample_rate=48000,
            buffer_frames=256,
            output_channels=2,
            input_channels=0,
            output_device=target["id_hex"],
        )
    )
    try:
        assert engine.opened_output_device_id == target["id_hex"]
        assert engine.opened_output_device_name
        if hasattr(native_audio._lib, "sb_engine_get_opened_backend"):
            assert engine.opened_backend == "wasapi"
    finally:
        engine.close()
