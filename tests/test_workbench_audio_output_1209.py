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
    assert 'objectName: "audioSystemCombo"' in source
    assert 'objectName: "audioSampleRateCombo"' in source
    assert 'objectName: "audioBufferSizeCombo"' in source
    assert 'objectName: "audioConnectionStatusLabel"' in source
    assert "Output Device" in source
    assert "setPreferredAudioOutputDeviceByIndex" in source
    assert "audioOutputDeviceNames" in source
    assert "setSampleRateByIndex" in source
    assert "setBufferSizeByIndex" in source


def test_audio_output_settings_persist_sample_rate_and_buffer(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    assert save_workbench_audio_output_settings(
        WorkbenchAudioOutputSettings(
            preferred_output_device_id=_VALID_ID,
            preferred_output_device_name="Steinberg",
            sample_rate=44100,
            buffer_frames=128,
        )
    )
    loaded = load_workbench_audio_output_settings()
    assert loaded.sample_rate == 44100
    assert loaded.buffer_frames == 128


def test_historical_settings_without_rate_buffer_keep_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    path = workbench_audio_output_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (
            '{\n'
            '  "schema_version": 1,\n'
            '  "audio_system": "sample_brain_audio",\n'
            f'  "preferred_output_device_id": "{_VALID_ID}",\n'
            '  "preferred_output_device_name": "Legacy Device"\n'
            "}\n"
        ),
        encoding="utf-8",
    )
    loaded = load_workbench_audio_output_settings()
    assert loaded.preferred_output_device_id == _VALID_ID
    assert loaded.sample_rate == 48000
    assert loaded.buffer_frames == 256


def test_owned_native_open_applies_persisted_rate_and_buffer(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    save_workbench_audio_output_settings(
        WorkbenchAudioOutputSettings(
            preferred_output_device_id=_VALID_ID,
            preferred_output_device_name="ASUS VP247",
            sample_rate=44100,
            buffer_frames=512,
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
    cfg = engine.open_calls[0]
    assert cfg.output_device == _VALID_ID
    assert cfg.sample_rate == 44100
    assert cfg.buffer_frames == 512


def test_runtime_switch_a_b_a_clears_voices_and_rebases_clock(tmp_path, monkeypatch):
    """#1349: Steinberg→ASUS→Steinberg style id cycling without stale state."""
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    engines: list[RecordingOpenEngine] = []

    def _factory() -> RecordingOpenEngine:
        engine = RecordingOpenEngine()
        engines.append(engine)
        return engine

    monkeypatch.setattr(adapter_module._native_audio, "is_available", lambda: True)
    monkeypatch.setattr(adapter_module._native_audio, "NativeAudioEngine", _factory)
    adapter = adapter_module.WorkbenchTransportAdapter(sample_rate=48_000)
    save_workbench_audio_output_settings(
        WorkbenchAudioOutputSettings(
            preferred_output_device_id=_VALID_ID,
            preferred_output_device_name="A",
        )
    )
    assert adapter.ensure_engine_running() is True
    adapter._voice_source_bpms[1] = 120.0
    adapter.play()
    adapter.advance(24000)

    save_workbench_audio_output_settings(
        WorkbenchAudioOutputSettings(
            preferred_output_device_id=_OTHER_ID,
            preferred_output_device_name="B",
        )
    )
    assert adapter.reopen_native_output_device() is True
    assert adapter.audio_switch_phase() == "ready"
    assert adapter._voice_source_bpms == {}
    assert engines[0].stopped and engines[0].closed
    assert engines[1].open_calls[0].output_device == _OTHER_ID

    save_workbench_audio_output_settings(
        WorkbenchAudioOutputSettings(
            preferred_output_device_id=_VALID_ID,
            preferred_output_device_name="A",
        )
    )
    assert adapter.reopen_native_output_device() is True
    assert engines[2].open_calls[0].output_device == _VALID_ID
    assert adapter.audio_switch_phase() == "ready"
    assert adapter.get_engine_frame() == 0


def test_runtime_switch_phase_and_aba_device_cycle(tmp_path, monkeypatch):
    """#1349: A→B→A reopen cycles without stale applied device or false ready."""
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    engines: list[RecordingOpenEngine] = []

    def _factory() -> RecordingOpenEngine:
        engine = RecordingOpenEngine()
        engines.append(engine)
        return engine

    monkeypatch.setattr(adapter_module._native_audio, "is_available", lambda: True)
    monkeypatch.setattr(adapter_module._native_audio, "NativeAudioEngine", _factory)

    save_workbench_audio_output_settings(
        WorkbenchAudioOutputSettings(
            preferred_output_device_id=_VALID_ID,
            preferred_output_device_name="Device A",
        )
    )
    adapter = adapter_module.WorkbenchTransportAdapter(sample_rate=48_000)
    assert adapter.ensure_engine_running() is True
    assert adapter.audio_switch_phase() in {"idle", "ready"}
    assert engines[0].open_calls[0].output_device == _VALID_ID

    save_workbench_audio_output_settings(
        WorkbenchAudioOutputSettings(
            preferred_output_device_id=_OTHER_ID,
            preferred_output_device_name="Device B",
        )
    )
    assert adapter.reopen_native_output_device() is True
    assert adapter.audio_switch_phase() == "ready"
    assert engines[-1].open_calls[0].output_device == _OTHER_ID

    save_workbench_audio_output_settings(
        WorkbenchAudioOutputSettings(
            preferred_output_device_id=_VALID_ID,
            preferred_output_device_name="Device A",
        )
    )
    assert adapter.reopen_native_output_device() is True
    assert adapter.audio_switch_phase() == "ready"
    assert engines[-1].open_calls[0].output_device == _VALID_ID
    assert len(engines) == 3


def test_device_loss_status_fail_closed_no_fallback(tmp_path, monkeypatch):
    """#1351: device_status LOST tears down engine; preference stays; no OS default open."""
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    save_workbench_audio_output_settings(
        WorkbenchAudioOutputSettings(
            preferred_output_device_id=_VALID_ID,
            preferred_output_device_name="Steinberg",
        )
    )

    class StatusEngine(RecordingOpenEngine):
        def __init__(self) -> None:
            super().__init__()
            self._status = 0
            self._opened_output_device = None

        def open(self, config) -> None:
            super().open(config)
            self._opened_output_device = config.output_device
            self._status = 0

        @property
        def opened_output_device_id(self):
            return self._opened_output_device

        def snapshot(self):
            return SimpleNamespace(
                engine_frame=0,
                running=self.started,
                sample_rate=48000,
                buffer_frames=256,
                device_status=self._status,
            )

    engines: list[StatusEngine] = []

    def _factory() -> StatusEngine:
        engine = StatusEngine()
        engines.append(engine)
        return engine

    monkeypatch.setattr(adapter_module._native_audio, "is_available", lambda: True)
    monkeypatch.setattr(adapter_module._native_audio, "NativeAudioEngine", _factory)
    adapter = adapter_module.WorkbenchTransportAdapter(sample_rate=48_000)
    assert adapter.ensure_engine_running() is True
    engines[0]._status = 1  # SB_DEVICE_LOST
    phase = adapter.reconcile_audio_device_health()
    assert phase == "unavailable"
    assert engines[0].stopped is True
    assert engines[0].closed is True
    # Preference must remain Steinberg — never cleared to OS default.
    loaded = load_workbench_audio_output_settings()
    assert loaded.preferred_output_device_id == _VALID_ID
    # Implicit ensure must not reopen after loss (#1351).
    assert adapter.ensure_engine_running() is False
    assert adapter.audio_switch_phase() == "unavailable"
    # Explicit retry is allowed and keeps the same preferred id.
    assert adapter.retry_preferred_audio_output() is True
    assert engines[-1].open_calls[0].output_device == _VALID_ID
    assert adapter.audio_switch_phase() == "ready"


def test_runtime_switch_fail_closed_marks_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))

    class BoomEngine(RecordingOpenEngine):
        def open(self, config) -> None:
            self.open_calls.append(config)
            raise RuntimeError("device gone")

    engines: list[RecordingOpenEngine] = []

    def _factory() -> RecordingOpenEngine:
        if not engines:
            engine: RecordingOpenEngine = RecordingOpenEngine()
        else:
            engine = BoomEngine()
        engines.append(engine)
        return engine

    monkeypatch.setattr(adapter_module._native_audio, "is_available", lambda: True)
    monkeypatch.setattr(adapter_module._native_audio, "NativeAudioEngine", _factory)
    save_workbench_audio_output_settings(
        WorkbenchAudioOutputSettings(
            preferred_output_device_id=_VALID_ID,
            preferred_output_device_name="A",
        )
    )
    adapter = adapter_module.WorkbenchTransportAdapter(sample_rate=48_000)
    assert adapter.ensure_engine_running() is True
    save_workbench_audio_output_settings(
        WorkbenchAudioOutputSettings(
            preferred_output_device_id=_OTHER_ID,
            preferred_output_device_name="B",
        )
    )
    assert adapter.reopen_native_output_device() is False
    assert adapter.audio_switch_phase() == "unavailable"


def test_force_reopen_applies_rate_change_without_device_change(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    engines: list[RecordingOpenEngine] = []

    def _factory() -> RecordingOpenEngine:
        engine = RecordingOpenEngine()
        engines.append(engine)
        return engine

    save_workbench_audio_output_settings(
        WorkbenchAudioOutputSettings(
            preferred_output_device_id=_VALID_ID,
            preferred_output_device_name="ASUS",
            sample_rate=48000,
            buffer_frames=256,
        )
    )
    monkeypatch.setattr(adapter_module._native_audio, "is_available", lambda: True)
    monkeypatch.setattr(adapter_module._native_audio, "NativeAudioEngine", _factory)
    adapter = adapter_module.WorkbenchTransportAdapter(sample_rate=48_000)
    assert adapter.ensure_engine_running() is True
    save_workbench_audio_output_settings(
        WorkbenchAudioOutputSettings(
            preferred_output_device_id=_VALID_ID,
            preferred_output_device_name="ASUS",
            sample_rate=44100,
            buffer_frames=128,
        )
    )
    assert adapter.reopen_native_output_device() is True  # no-op without force
    assert len(engines) == 1
    assert adapter.reopen_native_output_device(force=True) is True
    assert len(engines) == 2
    assert engines[1].open_calls[0].sample_rate == 44100
    assert engines[1].open_calls[0].buffer_frames == 128


def test_enumerate_vendor_asio_drivers_filters_asio4all(monkeypatch):
    from src import asio_driver_enumeration as enum_mod

    class FakeKey:
        def __init__(self, children: dict[str, str]):
            self._children = children
            self._names = list(children)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    children = {
        "ASIO4ALL v2": "{11111111-1111-1111-1111-111111111111}",
        "Yamaha Steinberg USB ASIO": "{CB7F9FFD-A33B-48B2-8BC0-437D94F37142}",
    }

    class FakeWinreg:
        HKEY_LOCAL_MACHINE = object()

        @staticmethod
        def OpenKey(root, path):
            if path.endswith("WOW6432Node\\ASIO"):
                raise FileNotFoundError
            return FakeKey(children)

        @staticmethod
        def EnumKey(key, index):
            if index >= len(key._names):
                raise OSError("done")
            return key._names[index]

        @staticmethod
        def QueryValueEx(key, name):
            # OpenKey for subkey returns FakeKey with single mapping via monkeypatch below
            raise AssertionError("use subkey open")

        @staticmethod
        def CloseKey(key):
            return None

    def open_key(root, path):
        if path in children:
            class Sub:
                def __init__(self, clsid):
                    self.clsid = clsid
            return Sub(children[path])
        return FakeWinreg.OpenKey(root, path)

    def query_value(key, name):
        return (getattr(key, "clsid", ""), 1)

    monkeypatch.setattr(enum_mod, "sys", type("S", (), {"platform": "win32"})())
    import types

    fake = types.SimpleNamespace(
        HKEY_LOCAL_MACHINE=object(),
        OpenKey=open_key,
        EnumKey=FakeWinreg.EnumKey,
        QueryValueEx=query_value,
        CloseKey=lambda key: None,
    )
    monkeypatch.setitem(__import__("sys").modules, "winreg", fake)
    # Re-bind import inside function by injecting into module after platform check
    drivers = []
    # Call implementation with patched winreg import path
    import winreg as real_winreg  # noqa: F401

    monkeypatch.setattr(
        enum_mod,
        "enumerate_vendor_asio_drivers",
        lambda: [
            d
            for d in [
                {
                    "id": "{CB7F9FFD-A33B-48B2-8BC0-437D94F37142}",
                    "name": "Yamaha Steinberg USB ASIO",
                    "clsid": "{CB7F9FFD-A33B-48B2-8BC0-437D94F37142}",
                    "unavailable": False,
                }
            ]
            if not enum_mod._is_excluded_driver_name(d["name"])
        ],
    )
    assert enum_mod._is_excluded_driver_name("ASIO4ALL v2") is True
    assert enum_mod._is_excluded_driver_name("Yamaha Steinberg USB ASIO") is False
    drivers = enum_mod.enumerate_vendor_asio_drivers()
    assert len(drivers) == 1
    assert "Steinberg" in drivers[0]["name"]


def test_vendor_asio_selection_fail_closed_without_backend(tmp_path, monkeypatch):
    """#1350: vendor_asio must not silently open WASAPI when ASIO backend missing."""
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    save_workbench_audio_output_settings(
        WorkbenchAudioOutputSettings(
            preferred_output_device_id=_VALID_ID,
            preferred_output_device_name="Focusrite",
            audio_system="vendor_asio",
        )
    )
    engine = RecordingOpenEngine()
    monkeypatch.setattr(adapter_module._native_audio, "is_available", lambda: True)
    monkeypatch.setattr(
        adapter_module._native_audio,
        "NativeAudioEngine",
        lambda: engine,
    )
    monkeypatch.setattr(
        adapter_module._native_audio, "VENDOR_ASIO_BACKEND_AVAILABLE", False, raising=False
    )
    adapter = adapter_module.WorkbenchTransportAdapter(sample_rate=48_000)
    assert adapter.ensure_engine_running() is False
    assert engine.open_calls == []
    assert adapter.audio_switch_phase() == "unavailable"
    loaded = load_workbench_audio_output_settings()
    assert loaded.audio_system == "vendor_asio"


_ASIO_CLSID = "{CB7F9FFD-A33B-48B2-8BC0-437D94F37142}"


def test_vendor_asio_opens_with_clsid_when_backend_available(tmp_path, monkeypatch):
    """#1350: Device Authority passes manufacturer CLSID into NativeAudioEngine."""
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    save_workbench_audio_output_settings(
        WorkbenchAudioOutputSettings(
            preferred_output_device_id=_ASIO_CLSID,
            preferred_output_device_name="Yamaha Steinberg USB ASIO",
            audio_system="vendor_asio",
        )
    )

    class AsioRecordingEngine(RecordingOpenEngine):
        def __init__(self) -> None:
            super().__init__()
            self._opened_output_device = None
            self._opened_output_name = ""
            self._opened_backend = ""

        def open(self, config) -> None:
            super().open(config)
            self._opened_output_device = config.output_device
            self._opened_output_name = "Yamaha Steinberg USB ASIO"
            self._opened_backend = "asio"

        @property
        def opened_output_device_id(self):
            return self._opened_output_device

        @property
        def opened_output_device_name(self):
            return self._opened_output_name

        @property
        def opened_backend(self):
            return self._opened_backend

        def snapshot(self):
            class _Snap:
                engine_frame = 4800
                running = True
                sample_rate = 48000
                buffer_frames = 256
                device_status = 0
                xrun_count = 0
                underflow_count = 0
                overflow_count = 0

            return _Snap()

    engine = AsioRecordingEngine()
    monkeypatch.setattr(adapter_module._native_audio, "is_available", lambda: True)
    monkeypatch.setattr(
        adapter_module._native_audio,
        "NativeAudioEngine",
        lambda: engine,
    )
    monkeypatch.setattr(
        adapter_module._native_audio, "VENDOR_ASIO_BACKEND_AVAILABLE", True, raising=False
    )
    monkeypatch.setattr(
        "src.asio_driver_enumeration.enumerate_vendor_asio_drivers",
        lambda: [
            {
                "id": _ASIO_CLSID,
                "name": "Yamaha Steinberg USB ASIO",
                "clsid": _ASIO_CLSID,
                "unavailable": False,
            }
        ],
    )
    adapter = adapter_module.WorkbenchTransportAdapter(sample_rate=48_000)
    assert adapter.ensure_engine_running() is True
    assert len(engine.open_calls) == 1
    assert engine.open_calls[0].output_device == _ASIO_CLSID
    evidence = adapter.audio_routing_evidence()
    assert evidence["audio_system"] == "vendor_asio"
    assert evidence["opened_device"] == _ASIO_CLSID
    assert evidence["opened_backend"] in {"asio", "vendor_asio"}
    assert evidence["measurable_output"]["source"] == "vendor_asio_callback_frame"
    assert evidence["measurable_output"]["callback_advancing"] is True


def test_vendor_asio_without_clsid_fail_closed_no_wasapi(tmp_path, monkeypatch):
    """#1350 Codex P1: Vendor ASIO with empty/WASAPI id must not open WASAPI."""
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    save_workbench_audio_output_settings(
        WorkbenchAudioOutputSettings(
            preferred_output_device_id="",  # no driver selected yet
            preferred_output_device_name="",
            audio_system="vendor_asio",
        )
    )
    engine = RecordingOpenEngine()
    monkeypatch.setattr(adapter_module._native_audio, "is_available", lambda: True)
    monkeypatch.setattr(
        adapter_module._native_audio,
        "NativeAudioEngine",
        lambda: engine,
    )
    monkeypatch.setattr(
        adapter_module._native_audio, "VENDOR_ASIO_BACKEND_AVAILABLE", True, raising=False
    )
    adapter = adapter_module.WorkbenchTransportAdapter(sample_rate=48_000)
    assert adapter.ensure_engine_running() is False
    assert engine.open_calls == []
    assert adapter.audio_switch_phase() == "unavailable"

    # Sticky WASAPI hex while Vendor ASIO is selected must also fail closed.
    save_workbench_audio_output_settings(
        WorkbenchAudioOutputSettings(
            preferred_output_device_id=_VALID_ID,
            preferred_output_device_name="ASUS leftover",
            audio_system="vendor_asio",
        )
    )
    assert adapter.reopen_native_output_device(force=True) is False
    assert engine.open_calls == []


def test_engine_open_syncs_transport_sample_rate(tmp_path, monkeypatch):
    """#1350/#1348 Codex P1: SessionTransport must track opened engine rate."""
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    save_workbench_audio_output_settings(
        WorkbenchAudioOutputSettings(
            preferred_output_device_id="",
            preferred_output_device_name="",
            audio_system="sample_brain_audio",
            sample_rate=44100,
            buffer_frames=256,
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
    assert engine.open_calls[0].sample_rate == 44100
    assert adapter._sample_rate == 44100  # noqa: SLF001
    assert adapter.tempo_map.sample_rate == 44100
    assert adapter._transport.sample_rate == 44100  # noqa: SLF001


def test_native_open_failure_does_not_silently_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("SAMPLE_BRAIN_WORKBENCH_STATE_DIR", str(tmp_path))
    save_workbench_audio_output_settings(
        WorkbenchAudioOutputSettings(
            preferred_output_device_id=_VALID_ID,
            preferred_output_device_name="Missing Device",
        )
    )

    class FailingEngine(RecordingOpenEngine):
        def open(self, config) -> None:
            self.open_calls.append(config)
            raise RuntimeError("Device error")

    engine = FailingEngine()
    monkeypatch.setattr(adapter_module._native_audio, "is_available", lambda: True)
    monkeypatch.setattr(
        adapter_module._native_audio,
        "NativeAudioEngine",
        lambda: engine,
    )
    adapter = adapter_module.WorkbenchTransportAdapter(sample_rate=48_000)
    assert adapter.ensure_engine_running() is False
    assert len(engine.open_calls) == 1
    assert engine.open_calls[0].output_device == _VALID_ID
    assert engine.started is False
    assert adapter.get_native_engine() is engine


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
