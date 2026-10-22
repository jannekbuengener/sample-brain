"""Fresh-process Windows regression for native device enumeration ownership."""

import subprocess
import sys
import textwrap

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
            expected = []
            for i in range(count.value):
                name_bytes = ctypes.string_at(ctypes.addressof(devices[i]) + audio.SbDeviceInfo.name.offset, 256)
                assert b"\\0" in name_bytes
                assert devices[i].is_default in (0, 1)
                expected.append((devices[i].name.decode(), bool(devices[i].is_default)))
            actual = audio.NativeAudioEngine.enumerate_devices(capture)
            assert [(item["name"], item["is_default"]) for item in actual] == expected
            assert all(isinstance(item["id_hex"], str) for item in actual)

    print("ok")
""")


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
