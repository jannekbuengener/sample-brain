"""Fresh-process Windows regression for native device enumeration ownership."""

import subprocess
import sys
import textwrap
import ctypes
from types import SimpleNamespace

import pytest

from src import native_audio


_SMOKE = textwrap.dedent("""
    import ctypes

    from src import native_audio as audio

    assert audio.is_available()
    for _ in range(16):
        for capture in (False, True):
            devices = (audio.SbDeviceInfo * 32)()
            count = ctypes.c_uint32()
            assert audio._lib.sb_enumerate_devices(int(capture), devices, 32, ctypes.byref(count)) == audio.SB_OK
            assert count.value <= 32
            for i in range(count.value):
                name_bytes = ctypes.string_at(ctypes.addressof(devices[i]) + audio.SbDeviceInfo.name.offset, 256)
                assert b"\\0" in name_bytes
                assert devices[i].is_default in (0, 1)
            actual = audio.NativeAudioEngine.enumerate_devices(capture)
            assert len(actual) <= 32
            assert all(isinstance(item["name"], str) and "\\0" not in item["name"] for item in actual)
            assert all(isinstance(item["id_hex"], str) for item in actual)
            assert all(isinstance(item["is_default"], bool) for item in actual)

    print("ok")
""")


def test_python_device_projection_preserves_default_flag(monkeypatch):
    def enumerate_devices(_capture, devices, _capacity, out_count):
        devices[0].name = b"Default playback"
        devices[0].id_hex = b"01"
        devices[0].is_default = 1
        devices[1].name = b"Other playback"
        devices[1].id_hex = b"02"
        devices[1].is_default = 0
        ctypes.cast(out_count, ctypes.POINTER(ctypes.c_uint32))[0] = 2
        return native_audio.SB_OK

    monkeypatch.setattr(native_audio, "_lib", SimpleNamespace(sb_enumerate_devices=enumerate_devices))
    assert native_audio.NativeAudioEngine.enumerate_devices(False) == [
        {"name": "Default playback", "id_hex": "01", "is_default": True},
        {"name": "Other playback", "id_hex": "02", "is_default": False},
    ]


@pytest.mark.skipif(sys.platform != "win32" or not native_audio.is_available(), reason="requires built Windows native audio DLL")
def test_device_enumeration_fresh_processes():
    for _ in range(8):
        result = subprocess.run(
            [sys.executable, "-c", _SMOKE],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert result.returncode == 0, (result.returncode, result.stderr[-2000:])
        assert result.stdout.strip() == "ok"
