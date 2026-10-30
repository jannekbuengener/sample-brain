"""#1209: Browser audition must open playback-only, not duplex-by-default."""

from __future__ import annotations

from types import SimpleNamespace

import src.workbench_transport_adapter as adapter_module
from src.native_audio import EngineConfig


class RecordingOpenEngine:
    def __init__(self) -> None:
        self.open_calls: list[EngineConfig] = []
        self.started = False

    def open(self, config: EngineConfig) -> None:
        self.open_calls.append(config)

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        return None

    def close(self) -> None:
        return None

    def snapshot(self):
        return SimpleNamespace(engine_frame=0, running=self.started)


def test_transport_opens_native_engine_with_zero_input_channels(monkeypatch):
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
    assert engine.open_calls[0].input_channels == 0
    assert engine.open_calls[0].output_channels == 2


def test_engine_config_defaults_to_playback_only():
    cfg = EngineConfig()
    assert cfg.input_channels == 0


def test_native_engine_cpp_selects_playback_when_input_channels_zero():
    from pathlib import Path

    engine_cpp = Path(__file__).resolve().parents[1] / "native" / "audio" / "src" / "engine.cpp"
    text = engine_cpp.read_text(encoding="utf-8")
    assert "ma_device_type_playback" in text
    assert "ma_device_type_duplex" in text
    assert "input_channels > 0" in text
    # Must not unconditionally force duplex for every open.
    assert "ma_device_config_init(ma_device_type_duplex)" not in text
    assert "ma_device_config_init(device_type)" in text
