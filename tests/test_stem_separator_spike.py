from __future__ import annotations

import sys
import os
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Test for core import isolation
def test_core_isolation_from_heavy_dependencies():
    # Ensure audio_separator and torch are NOT loaded when importing core modules
    to_unload = [mod for mod in sys.modules if "audio_separator" in mod or "torch" in mod]
    for mod in to_unload:
        sys.modules.pop(mod, None)

    # Import core CLI
    import src.cli
    import src.db

    # Assert that neither audio_separator nor torch were loaded
    loaded_heavy = [mod for mod in sys.modules if "audio_separator" in mod or "torch" in mod]
    assert not loaded_heavy, f"Heavy dependencies loaded by core: {loaded_heavy}"


def test_wrapper_uninstalled_returns_backend_unavailable(tmp_path):
    # If audio-separator package is not installed (mocked by putting None in sys.modules)
    with patch.dict(sys.modules, {"audio_separator": None}):
        # Import the wrapper locally inside the test
        from tools.stem_separator_spike import StemSeparatorProcessWrapper
        
        wrapper = StemSeparatorProcessWrapper()
        res = wrapper.separate_offline_fallback(
            input_path=tmp_path / "track.wav",
            model_filename="htdemucs.yaml",
            output_dir=tmp_path / "out",
            reason="BACKEND_UNAVAILABLE"
        )
        assert res["status"] == "not_run"
        assert res["reason_code"] == "BACKEND_UNAVAILABLE"
        assert "output" not in res


def test_subprocess_timeout_returns_failed_state(tmp_path):
    from tools.stem_separator_spike import StemSeparatorProcessWrapper
    wrapper = StemSeparatorProcessWrapper()

    # Mock subprocess.run to raise TimeoutExpired
    import subprocess
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["mock"], timeout=10.0)
        res = wrapper.separate_via_subprocess(
            input_path=tmp_path / "track.wav",
            track_ref="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
            working_audio_hash="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
            model_filename="htdemucs.yaml",
            weight_hash="a" * 64,
            weight_hash_algo="sha256",
            separation_fingerprint="fp_a1b2c3d4",
            output_dir=tmp_path / "out",
            timeout=1.0
        )
        cmd = mock_run.call_args.args[0]
        assert "--track-ref" in cmd and "--working-audio-hash" in cmd
        assert "--weight-hash" in cmd and "--weight-hash-algo" in cmd
        assert "--separation-fingerprint" in cmd
        assert res["status"] == "failed"
        assert res["error"]["code"] == "TIMEOUT"
        assert "timed out" in res["error"]["message"]


def test_subprocess_non_zero_exit_returns_failed_state(tmp_path):
    from tools.stem_separator_spike import StemSeparatorProcessWrapper
    wrapper = StemSeparatorProcessWrapper()

    # Mock subprocess.run to return exit code 1
    import subprocess
    mock_res = subprocess.CompletedProcess(args=["mock"], returncode=1, stdout="", stderr="Mock subprocess failure")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = mock_res
        res = wrapper.separate_via_subprocess(
            input_path=tmp_path / "track.wav",
            track_ref="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
            working_audio_hash="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
            model_filename="htdemucs.yaml",
            weight_hash="a" * 64,
            weight_hash_algo="sha256",
            separation_fingerprint="fp_a1b2c3d4",
            output_dir=tmp_path / "out"
        )
        cmd = mock_run.call_args.args[0]
        assert "--weight-hash" in cmd and "a" * 64 in cmd
        assert res["status"] == "failed"
        assert res["error"]["code"] == "SUBPROCESS_ERROR"
        assert "exit code 1" in res["error"]["message"]


def test_stem_manifest_mapping_fields(tmp_path):
    # This tests the serialization mapping functionality directly
    from tools.stem_separator_spike import (
        WEIGHT_USAGE_RESEARCH_ONLY,
        map_stem_to_manifest,
    )

    source_properties = {
        "sample_rate_hz": 44100,
        "channels": 2,
        "n_samples": 88200,
        "duration_sec": 2.0
    }
    output_properties = {
        "sample_rate_hz": 44100,
        "channels": 2,
        "n_samples": 88200,
        "duration_sec": 2.0
    }

    # Real, test-supplied weight hash (NOT the debunked fake long hash).
    model_identity = {
        "family": "htdemucs",
        "name": "htdemucs",
        "checkpoint": "955717e8",
        "weight_hash": {"algorithm": "sha256", "value": "a" * 64},
        "code_license": "MIT",
        "weight_license": WEIGHT_USAGE_RESEARCH_ONLY,
    }

    manifest = map_stem_to_manifest(
        stem_id="stem_drums_test",
        stem_kind="drums",
        track_ref="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
        source_hash="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
        source_properties=source_properties,
        file_ref="drums.wav",
        output_hash="ee55ff6677889900aabbcceedff1122334455667",
        output_properties=output_properties,
        model_identity=model_identity,
        backend_version="0.44.5"
    )

    # Let's run it through the official validation to prove 100% compliance!
    from tests.test_stem_manifest_contract import validate_stem_manifest
    errors = validate_stem_manifest(manifest)
    assert errors == [], f"Validation failed: {errors}"

    # Also assert specific contract guarantees
    assert manifest["document_type"] == "sample_brain.stem_manifest"
    assert manifest["schema_version"] == "1.0.0"
    assert manifest["stem_kind"] == "drums"
    assert manifest["status"] == "ok"
    assert manifest["source"]["origin_sample"] == 0
    assert manifest["provenance"]["component"] == "stem_separator"
    assert manifest["provenance"]["model"]["family"] == "htdemucs"
    assert manifest["provenance"]["model"]["code_license"] == "MIT"
    # #247: research-only weight usage, never asserted as commercial grant.
    assert manifest["provenance"]["model"]["weight_license"] == WEIGHT_USAGE_RESEARCH_ONLY
    # The debunked fake long hash must never appear.
    assert "f7e0c4bcba3fe64a92cfc3b6ef3bcb9c04573f0d" not in json.dumps(manifest)
    assert manifest["output"]["file_ref"] == "drums.wav"


def test_invalid_track_ref_filename_fallback_raises():
    from tools.stem_separator_spike import (
        WEIGHT_USAGE_RESEARCH_ONLY,
        map_stem_to_manifest,
    )

    model_identity = {
        "family": "htdemucs",
        "name": "htdemucs",
        "checkpoint": "955717e8",
        "weight_hash": {"algorithm": "sha256", "value": "a" * 64},
        "code_license": "MIT",
        "weight_license": WEIGHT_USAGE_RESEARCH_ONLY,
    }

    # Passing raw filename instead of a content hash should be rejected or handled appropriately
    # The contract requires: track_ref must be a portable track ID, not a path or filename fallback.
    # So we must ensure that filename fallbacks are explicitly rejected or validated.
    with pytest.raises(ValueError, match="track_ref must be a portable track ID"):
        map_stem_to_manifest(
            stem_id="stem_drums_test",
            stem_kind="drums",
            track_ref="my_track.wav", # INVALID fallback
            source_hash="a1b2",
            source_properties={"sample_rate_hz": 44100, "channels": 2, "n_samples": 88200},
            file_ref="drums.wav",
            output_hash="ee55",
            output_properties={"sample_rate_hz": 44100, "channels": 2, "n_samples": 88200},
            model_identity=model_identity,
            backend_version="0.44.5"
        )


def test_map_stem_to_manifest_rejects_missing_weight_hash():
    from tools.stem_separator_spike import map_stem_to_manifest

    model_identity = {
        "family": "htdemucs",
        "name": "htdemucs",
        "checkpoint": "955717e8",
        "weight_hash": None,  # incomplete identity
        "code_license": "MIT",
        "weight_license": "RESEARCH_ONLY / COMMERCIAL_USE_NOT_GRANTED",
    }
    with pytest.raises(ValueError, match="weight_hash"):
        map_stem_to_manifest(
            stem_id="stem_drums_test",
            stem_kind="drums",
            track_ref="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
            source_hash="a1b2",
            source_properties={"sample_rate_hz": 44100, "channels": 2, "n_samples": 88200},
            file_ref="drums.wav",
            output_hash="ee55",
            output_properties={"sample_rate_hz": 44100, "channels": 2, "n_samples": 88200},
            model_identity=model_identity,
            backend_version="0.44.5"
        )


def test_classify_native_import_blocked_from_policy_message():
    from tools.stem_separator_spike import (
        NATIVE_IMPORT_BLOCKED,
        classify_native_import_failure,
    )

    err = classify_native_import_failure(
        "DLL load failed while importing _helperlib: "
        "Eine Anwendungssteuerungsrichtlinie hat diese Datei blockiert."
    )
    assert err is not None
    assert err["code"] == NATIVE_IMPORT_BLOCKED
    assert err.get("retryable") is False
    # Stable message must not echo absolute paths from the triggering text.
    assert ":" not in err["message"] or "Windows" in err["message"]
    assert "D:\\" not in err["message"]
    assert "/Users/" not in err["message"]
    assert "_helperlib" in err["message"] or "native" in err["message"].lower()


def test_classify_native_import_blocked_english_application_control():
    from tools.stem_separator_spike import (
        NATIVE_IMPORT_BLOCKED,
        classify_native_import_failure,
    )

    err = classify_native_import_failure(
        ImportError(
            "DLL load failed while importing _helperlib: "
            "An application control policy has blocked this file."
        )
    )
    assert err is not None
    assert err["code"] == NATIVE_IMPORT_BLOCKED


def test_classify_native_import_ignores_unrelated_errors():
    from tools.stem_separator_spike import classify_native_import_failure

    assert classify_native_import_failure("CUDA out of memory") is None
    assert classify_native_import_failure(ValueError("bad shape")) is None
    assert classify_native_import_failure(None) is None


def test_empty_stem_outputs_stay_empty_when_no_native_block(tmp_path, monkeypatch, capsys):
    """EMPTY_STEM_OUTPUT remains only for genuine empty outputs after separation."""
    import argparse
    import tools.stem_separator_spike as spike

    class _FakeSep:
        def __init__(self, **_kwargs):
            pass

        def load_model(self, model_filename=None):
            return None

        def separate(self, *_args, **_kwargs):
            return []

    monkeypatch.setattr(
        spike,
        "resolve_known_model_identity",
        lambda *_a, **_k: {
            "family": "htdemucs",
            "name": "htdemucs",
            "checkpoint": "955717e8",
            "code_license": "MIT",
            "weight_license": spike.WEIGHT_USAGE_RESEARCH_ONLY,
        },
    )
    monkeypatch.setitem(
        sys.modules,
        "audio_separator",
        MagicMock(),
    )
    monkeypatch.setitem(
        sys.modules,
        "audio_separator.separator",
        MagicMock(Separator=_FakeSep),
    )
    monkeypatch.setattr(spike, "probe_native_import_block", lambda: None)
    monkeypatch.setattr(
        spike,
        "get_backend_version",
        lambda: "0.44.5",
    )

    inp = tmp_path / "in.wav"
    inp.write_bytes(b"RIFF")
    out = tmp_path / "out"
    out.mkdir()

    # soundfile.info for source probe
    fake_info = MagicMock(samplerate=44100, channels=1, frames=100, duration=0.01)
    monkeypatch.setitem(sys.modules, "soundfile", MagicMock(info=lambda *_a, **_k: fake_info))

    args = argparse.Namespace(
        input=str(inp),
        output_dir=str(out),
        model="htdemucs.yaml",
        track_ref="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2",
        working_audio_hash="b" * 64,
        separation_fingerprint="fp_test",
        weight_hash="a" * 64,
        weight_hash_algo="sha256",
        model_cache_dir=None,
    )
    spike.cli_separate(args)
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert "error" not in payload or payload.get("error") is None
    for kind in ("drums", "bass", "vocals", "other"):
        assert payload["stems"][kind]["reason_code"] == "EMPTY_STEM_OUTPUT"


def test_native_import_block_does_not_use_empty_stem_output(tmp_path, monkeypatch, capsys):
    """Policy/native import failures must not collapse into EMPTY_STEM_OUTPUT."""
    import argparse
    import tools.stem_separator_spike as spike

    class _FakeSep:
        def __init__(self, **_kwargs):
            pass

        def load_model(self, model_filename=None):
            return None

        def separate(self, *_args, **_kwargs):
            return []

    monkeypatch.setattr(
        spike,
        "resolve_known_model_identity",
        lambda *_a, **_k: {
            "family": "htdemucs",
            "name": "htdemucs",
            "checkpoint": "955717e8",
            "code_license": "MIT",
            "weight_license": spike.WEIGHT_USAGE_RESEARCH_ONLY,
        },
    )
    monkeypatch.setitem(sys.modules, "audio_separator", MagicMock())
    monkeypatch.setitem(
        sys.modules,
        "audio_separator.separator",
        MagicMock(Separator=_FakeSep),
    )
    blocked = {
        "code": spike.NATIVE_IMPORT_BLOCKED,
        "message": (
            "A required native extension import was blocked by the host "
            "(for example Numba _helperlib under Windows application control)."
        ),
        "retryable": False,
    }
    monkeypatch.setattr(spike, "probe_native_import_block", lambda: blocked)
    monkeypatch.setattr(spike, "get_backend_version", lambda: "0.44.5")

    inp = tmp_path / "in.wav"
    inp.write_bytes(b"RIFF")
    out = tmp_path / "out"
    out.mkdir()
    fake_info = MagicMock(samplerate=44100, channels=1, frames=100, duration=0.01)
    monkeypatch.setitem(sys.modules, "soundfile", MagicMock(info=lambda *_a, **_k: fake_info))

    args = argparse.Namespace(
        input=str(inp),
        output_dir=str(out),
        model="htdemucs.yaml",
        track_ref="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2",
        working_audio_hash="b" * 64,
        separation_fingerprint="fp_test",
        weight_hash="a" * 64,
        weight_hash_algo="sha256",
        model_cache_dir=None,
    )
    spike.cli_separate(args)
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert payload["error"]["code"] == spike.NATIVE_IMPORT_BLOCKED
    assert "EMPTY_STEM_OUTPUT" not in json.dumps(payload)
    assert "D:\\" not in json.dumps(payload)
    assert "/Users/" not in json.dumps(payload)


def test_raised_native_import_classified_instead_of_launch_failure(
    tmp_path, monkeypatch, capsys
):
    import argparse
    import tools.stem_separator_spike as spike

    class _BoomSep:
        def __init__(self, **_kwargs):
            pass

        def load_model(self, model_filename=None):
            return None

        def separate(self, *_args, **_kwargs):
            raise ImportError(
                "DLL load failed while importing _helperlib: "
                "An application control policy has blocked this file. "
                r"C:\Users\private\path\_helperlib.pyd"
            )

    monkeypatch.setattr(
        spike,
        "resolve_known_model_identity",
        lambda *_a, **_k: {
            "family": "htdemucs",
            "name": "htdemucs",
            "checkpoint": "955717e8",
            "code_license": "MIT",
            "weight_license": spike.WEIGHT_USAGE_RESEARCH_ONLY,
        },
    )
    monkeypatch.setitem(sys.modules, "audio_separator", MagicMock())
    monkeypatch.setitem(
        sys.modules,
        "audio_separator.separator",
        MagicMock(Separator=_BoomSep),
    )

    args = argparse.Namespace(
        input=str(tmp_path / "in.wav"),
        output_dir=str(tmp_path / "out"),
        model="htdemucs.yaml",
        track_ref="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2",
        working_audio_hash="b" * 64,
        separation_fingerprint="fp_test",
        weight_hash="a" * 64,
        weight_hash_algo="sha256",
        model_cache_dir=None,
    )
    (tmp_path / "out").mkdir()
    (tmp_path / "in.wav").write_bytes(b"RIFF")
    spike.cli_separate(args)
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert payload["error"]["code"] == spike.NATIVE_IMPORT_BLOCKED
    assert payload["error"]["code"] != "LAUNCH_FAILURE"
    dumped = json.dumps(payload)
    assert r"C:\Users\private" not in dumped
    assert "EMPTY_STEM_OUTPUT" not in dumped
