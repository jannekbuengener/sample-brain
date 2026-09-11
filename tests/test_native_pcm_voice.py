"""Controlled Python FFI contracts for finite native PCM voices (#529)."""

import ctypes
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import pytest

from src import native_audio


def _engine_with_fake_create(create_callback):
    fake_lib = SimpleNamespace(sb_voice_create=Mock(side_effect=create_callback))
    engine = native_audio.NativeAudioEngine.__new__(native_audio.NativeAudioEngine)
    engine._engine = native_audio.sb_engine_t(123)
    return engine, fake_lib


def test_pcm_voice_ffi_passes_interleaved_float32_descriptor():
    captured = {}

    def fake_create(_engine, config_ptr, out_id_ptr):
        config = ctypes.cast(
            config_ptr, ctypes.POINTER(native_audio.SbVoiceConfig)
        ).contents
        pcm = config.source.pcm_buffer
        captured["type"] = config.source.type
        captured["frames"] = pcm.frame_count
        captured["channels"] = pcm.channels
        captured["samples"] = [
            pcm.data[index] for index in range(pcm.frame_count * pcm.channels)
        ]
        ctypes.cast(
            out_id_ptr, ctypes.POINTER(native_audio.sb_voice_id_t)
        ).contents.value = config.id
        return native_audio.SB_OK

    engine, fake_lib = _engine_with_fake_create(fake_create)
    samples = np.array([[0.25, -0.25], [0.5, -0.5]], dtype=np.float64)
    config = native_audio.VoiceConfig(
        id=41,
        source_type=native_audio.SB_SOURCE_PCM_BUFFER,
        pcm_buffer=native_audio.PcmBufferConfig(samples=samples, channels=2),
    )

    with patch.object(native_audio, "_lib", fake_lib):
        assert engine.create_voice(config) == 41

    assert captured == {
        "type": native_audio.SB_SOURCE_PCM_BUFFER,
        "frames": 2,
        "channels": 2,
        "samples": [0.25, -0.25, 0.5, -0.5],
    }
    fake_lib.sb_voice_create.assert_called_once()


@pytest.mark.parametrize(
    ("pcm_buffer", "message"),
    [
        (None, "pcm_buffer is required"),
        (native_audio.PcmBufferConfig(np.array([], dtype=np.float32), 1), "must not be empty"),
        (native_audio.PcmBufferConfig(np.array([0.0, np.nan], dtype=np.float32), 1), "finite"),
        (native_audio.PcmBufferConfig(np.array([0.0], dtype=np.float32), 0), "channels"),
        (native_audio.PcmBufferConfig(np.array([0.0, 1.0], dtype=np.float32), 3), "channels"),
        (native_audio.PcmBufferConfig(np.array([0.0, 1.0, 2.0], dtype=np.float32), 2), "divisible"),
    ],
)
def test_pcm_voice_python_validation_is_fail_closed(pcm_buffer, message):
    engine, fake_lib = _engine_with_fake_create(lambda *_args: native_audio.SB_OK)
    config = native_audio.VoiceConfig(
        id=42,
        source_type=native_audio.SB_SOURCE_PCM_BUFFER,
        pcm_buffer=pcm_buffer,
    )

    with patch.object(native_audio, "_lib", fake_lib):
        with pytest.raises(ValueError, match=message):
            engine.create_voice(config)

    fake_lib.sb_voice_create.assert_not_called()


def test_non_pcm_voice_rejects_inconsistent_pcm_descriptor():
    engine, fake_lib = _engine_with_fake_create(lambda *_args: native_audio.SB_OK)
    config = native_audio.VoiceConfig(
        id=43,
        source_type=native_audio.SB_SOURCE_SYNTHETIC_CLICK,
        pcm_buffer=native_audio.PcmBufferConfig(
            samples=np.array([0.25], dtype=np.float32), channels=1
        ),
    )

    with patch.object(native_audio, "_lib", fake_lib):
        with pytest.raises(ValueError, match="only valid for PCM"):
            engine.create_voice(config)

    fake_lib.sb_voice_create.assert_not_called()


def test_unknown_source_type_is_rejected_before_ffi_call():
    engine, fake_lib = _engine_with_fake_create(lambda *_args: native_audio.SB_OK)

    with patch.object(native_audio, "_lib", fake_lib):
        with pytest.raises(ValueError, match="source_type"):
            engine.create_voice(native_audio.VoiceConfig(id=44, source_type=999))

    fake_lib.sb_voice_create.assert_not_called()
