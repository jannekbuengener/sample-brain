from __future__ import annotations

import json
from pathlib import Path

import pytest
import soundfile as sf

from tests.audio_fixtures import write_sine_wav


def test_analyze_context_file_returns_portable_track_map(tmp_path: Path) -> None:
    from src.context_analyze import analyze_context_file

    source = write_sine_wav(
        tmp_path / "outside library.wav", duration_sec=2.0, frequency_hz=440.0
    )

    result = analyze_context_file(source)

    assert result["document_type"] == "sample_brain.track_map"
    assert result["schema_version"] == "1.1.0"
    assert result["source"]["original"]["file_name"] == "outside library.wav"
    assert "path" not in result["source"]["original"]
    assert str(tmp_path) not in json.dumps(result)
    assert result["timebase"] == {
        "audio_ref": "/source/original",
        "unit": "seconds",
        "origin_sec": 0.0,
    }
    assert result["analysis"]["requested_components"] == [
        "bpm",
        "key",
        "loudness",
        "brightness",
    ]
    assert result["analysis"]["timeline"]["beats"] == {
        "status": "not_run",
        "reason_code": "BEATS_NOT_REQUESTED",
    }
    assert (
        result["provenance"]["components"]["context_source"]["component"]
        == "context_source"
    )
    assert (
        result["provenance"]["components"]["analyze"]["configuration"]["working_audio"]
        == "temporary_canonical_wav"
    )


def test_analyze_context_file_supports_flac(tmp_path: Path) -> None:
    from src.context_analyze import analyze_context_file

    wav_path = write_sine_wav(
        tmp_path / "source.wav", duration_sec=2.0, frequency_hz=220.0
    )
    samples, sample_rate = sf.read(str(wav_path), dtype="float32")
    flac_path = tmp_path / "outside-library.flac"
    sf.write(str(flac_path), samples, sample_rate, format="FLAC")

    result = analyze_context_file(flac_path)

    assert result["source"]["original"]["file_name"] == "outside-library.flac"


@pytest.mark.parametrize(
    ("name", "expected_code"),
    [
        ("missing.wav", "FILE_NOT_FOUND"),
        ("directory", "NOT_A_FILE"),
        ("unsupported.txt", "UNSUPPORTED_AUDIO_FORMAT"),
        ("broken.wav", "AUDIO_LOAD_FAILED"),
    ],
)
def test_analyze_context_file_fails_closed_for_invalid_inputs(
    tmp_path: Path, name: str, expected_code: str
) -> None:
    from src.context_analyze import ContextAnalyzeError, analyze_context_file

    path = tmp_path / name
    if expected_code == "NOT_A_FILE":
        path.mkdir()
    elif expected_code == "UNSUPPORTED_AUDIO_FORMAT":
        path.write_text("not audio", encoding="utf-8")
    elif expected_code == "AUDIO_LOAD_FAILED":
        path.write_bytes(b"not a wav")

    with pytest.raises(ContextAnalyzeError) as exc_info:
        analyze_context_file(path)

    assert exc_info.value.code == expected_code


def test_analyze_context_file_uses_canonical_working_audio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.context_analyze as context_analyze

    source = write_sine_wav(
        tmp_path / "source.wav", duration_sec=2.0, frequency_hz=220.0
    )
    calls: list[Path] = []
    original_extract = context_analyze.extract_features

    def recording_extract(path: Path, *args, **kwargs):
        calls.append(path)
        return original_extract(path, *args, **kwargs)

    monkeypatch.setattr(context_analyze, "extract_features", recording_extract)

    context_analyze.analyze_context_file(source)

    assert len(calls) == 1
    assert calls[0].name == "canonical.wav"
    assert calls[0] != source


def test_analyze_context_file_is_deterministic_and_does_not_touch_db(
    tmp_path: Path,
) -> None:
    from src.context_analyze import analyze_context_file

    source = write_sine_wav(tmp_path / "tone.wav", duration_sec=2.0, frequency_hz=330.0)

    first = analyze_context_file(source)
    second = analyze_context_file(source)

    assert first == second
    assert not list(tmp_path.glob("*.db"))


def test_analyze_provenance_contains_parameter_fingerprint(
    tmp_path: Path,
) -> None:
    from src.context_analyze import analyze_context_file

    source = write_sine_wav(
        tmp_path / "tone.wav", duration_sec=2.0, frequency_hz=330.0
    )
    result = analyze_context_file(source)
    analyze_cfg = result["provenance"]["components"]["analyze"]["configuration"]
    assert "parameter_fingerprint" in analyze_cfg
    fp = analyze_cfg["parameter_fingerprint"]
    assert isinstance(fp, str)
    assert len(fp) == 64  # SHA-256 hex digest


def test_analyze_context_file_cached_miss_then_hit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.context_analyze import analyze_context_file_cached

    source = write_sine_wav(
        tmp_path / "tone.wav", duration_sec=2.0, frequency_hz=330.0
    )
    cache_dir = tmp_path / "cache"
    r1 = analyze_context_file_cached(source, cache_dir=cache_dir)
    assert r1.cache_status == "miss"
    assert (cache_dir / f"{r1.cache_key}.json").exists()
    # second identical run hits the cache
    r2 = analyze_context_file_cached(source, cache_dir=cache_dir)
    assert r2.cache_status == "hit"
    assert r1.track_map == r2.track_map


def test_analyze_context_file_cached_preserves_parameter_fingerprint(
    tmp_path: Path,
) -> None:
    from src.context_analyze import analyze_context_file_cached

    source = write_sine_wav(tmp_path / "tone.wav", duration_sec=2.0, frequency_hz=330.0)
    cache_dir = tmp_path / "cache"
    analyze_context_file_cached(source, cache_dir=cache_dir)
    r2 = analyze_context_file_cached(source, cache_dir=cache_dir)
    assert r2.cache_status == "hit"
    cfg = r2.track_map["provenance"]["components"]["analyze"]["configuration"]
    assert "parameter_fingerprint" in cfg
