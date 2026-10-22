"""Fresh-process Windows regression for native device enumeration ownership."""

import subprocess
import sys
import textwrap

import pytest

from src import native_audio


_SMOKE = textwrap.dedent("""
    import ctypes
    import sys
    import time

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

    if sys.argv[1] == "lifecycle":
        engine = audio.NativeAudioEngine()
        try:
            engine.open(audio.EngineConfig())
            engine.start()
            voice_id = engine.create_voice(audio.VoiceConfig(id=1))
            engine.schedule_voice_start(voice_id, engine.snapshot().engine_frame + 512)
            time.sleep(0.05)
            engine.stop_voice(voice_id)
            engine.stop()
        finally:
            engine.close()
        for capture in (False, True):
            audio.NativeAudioEngine.enumerate_devices(capture)
    print("ok")
""")


@pytest.mark.skipif(sys.platform != "win32" or not native_audio.is_available(), reason="requires built Windows native audio DLL")
@pytest.mark.parametrize("scenario", ["enumeration", "lifecycle"])
def test_device_enumeration_fresh_processes(scenario):
    for _ in range(4):
        result = subprocess.run(
            [sys.executable, "-c", _SMOKE, scenario],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert result.returncode == 0, (result.returncode, result.stderr[-2000:])
        assert result.stdout.strip() == "ok"
