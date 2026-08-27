from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.context_analyze import ContextAnalyzeError, TrackAnalysisCacheResult
from src.track_context import (
    TRACK_CONTEXT_DOCUMENT_TYPE,
    TRACK_CONTEXT_SCHEMA_VERSION,
    TrackContextProfileError,
    analyze_track_context,
    build_track_context_profile,
)


def _track_map(*, key_status: str = "ok") -> dict[str, object]:
    key: dict[str, object] = {
        "status": key_status,
        "root": "A",
        "mode": "min",
        "key_conf": 0.82,
        "source_ref": "analyze",
    }
    if key_status == "partial":
        key.pop("mode")
        key["reason_code"] = "MODE_UNRESOLVED"

    return {
        "document_type": "sample_brain.track_map",
        "schema_version": "1.1.0",
        "source": {
            "original": {
                "file_name": "track.wav",
                "size_bytes": 1234,
                "hash": {"algorithm": "sha256", "value": "a" * 64},
                "audio_properties": {
                    "duration_sec": 120.0,
                    "sample_rate_hz": 44100,
                    "channels": 2,
                },
                "source_ref": "context_source",
                "path": r"C:\private\music\track.wav",
            }
        },
        "analysis": {
            "status": "ok",
            "musical": {
                "bpm": {
                    "status": "ok",
                    "value": 128.0,
                    "unit": "bpm",
                    "normalization": "none",
                    "source_ref": "analyze",
                },
                "key": key,
            },
            "audio_summary": {
                "loudness": {
                    "status": "ok",
                    "value": -13.4,
                    "unit": "dBFS",
                    "method": "global_rms",
                    "source_ref": "analyze",
                },
                "brightness": {
                    "status": "ok",
                    "value": 2840.0,
                    "unit": "Hz",
                    "method": "mean_spectral_centroid",
                    "source_ref": "analyze",
                },
            },
            "timeline": {
                "beats": {"status": "not_run"},
                "sections": {"status": "not_run"},
            },
        },
        "provenance": {
            "components": {
                "analyze": {
                    "component": "analyze",
                    "backend": {"name": "librosa", "version": "0.11.0"},
                }
            }
        },
    }


def test_build_track_context_profile_maps_existing_track_map_evidence() -> None:
    profile = build_track_context_profile(_track_map())

    assert profile["document_type"] == TRACK_CONTEXT_DOCUMENT_TYPE
    assert profile["schema_version"] == TRACK_CONTEXT_SCHEMA_VERSION
    assert profile["status"] == "partial"
    assert profile["bpm"]["value"] == pytest.approx(128.0)
    assert profile["bpm"]["source_ref"] == "track_map:/analysis/musical/bpm"
    assert profile["key"]["root"] == "A"
    assert profile["key"]["mode"] == "min"
    assert profile["key"]["key_conf"] == pytest.approx(0.82)


def test_key_mode_partial_status_is_preserved() -> None:
    profile = build_track_context_profile(_track_map(key_status="partial"))

    assert profile["key"]["status"] == "partial"
    assert profile["key"]["reason_code"] == "MODE_UNRESOLVED"
    assert "mode" not in profile["key"]


def test_energy_uses_global_loudness_but_stays_partial() -> None:
    profile = build_track_context_profile(_track_map())

    assert profile["energy"] == {
        "evidence": {"method": "global_rms", "unit": "dBFS"},
        "reason_code": "GLOBAL_LOUDNESS_ONLY",
        "source_ref": "track_map:/analysis/audio_summary/loudness",
        "status": "partial",
        "value": {"global_loudness_dbfs": -13.4},
    }


def test_spectrum_maps_existing_brightness_evidence() -> None:
    profile = build_track_context_profile(_track_map())

    assert profile["spectrum"]["status"] == "ok"
    assert profile["spectrum"]["value"] == {"brightness_hz": 2840.0}
    assert profile["spectrum"]["evidence"]["method"] == "mean_spectral_centroid"


def test_missing_optional_components_are_honest_no_result() -> None:
    profile = build_track_context_profile(_track_map())

    assert profile["groove"] == {
        "reason_code": "GROOVE_EVIDENCE_UNAVAILABLE",
        "status": "no_result",
    }
    assert profile["arrangement"] == {
        "reason_code": "ARRANGEMENT_EVIDENCE_UNAVAILABLE",
        "status": "no_result",
    }
    assert profile["desired_layers"] == {
        "reason_code": "DESIRED_LAYER_EVIDENCE_UNAVAILABLE",
        "status": "no_result",
    }


def test_optional_existing_evidence_is_consumed_without_new_analysis() -> None:
    optional = {
        "groove": {
            "status": "ok",
            "value": {"grid": "4/4", "swing": 0.0},
            "evidence": {"beat_grid_ref": "/analysis/timeline/beats"},
        },
        "arrangement": {
            "status": "partial",
            "value": [{"role": "drop", "start_sec": 32.0}],
            "reason_code": "PARTIAL_SECTION_COVERAGE",
        },
        "desired_layers": ["atmos_fx", "vocal"],
    }

    profile = build_track_context_profile(_track_map(), optional)

    assert profile["groove"]["status"] == "ok"
    assert profile["groove"]["source_ref"] == "optional_evidence:groove"
    assert profile["arrangement"]["status"] == "partial"
    assert profile["desired_layers"]["value"] == ["atmos_fx", "vocal"]
    assert profile["desired_layers"]["source_ref"] == "optional_evidence:desired_layers"


def test_profile_does_not_serialize_absolute_source_path() -> None:
    profile = build_track_context_profile(_track_map())
    serialized = json.dumps(profile, sort_keys=True)

    assert r"C:\\private\\music" not in serialized
    assert "path" not in profile["source"]["original"]
    assert profile["source"]["original"]["file_name"] == "track.wav"


@pytest.mark.parametrize(
    "absolute_path",
    [
        r"D:\private\arrangement.json",
        "/home/user/private/arrangement.json",
        "/source/private.wav",
    ],
)
def test_optional_evidence_with_absolute_path_fails_closed(
    absolute_path: str,
) -> None:
    with pytest.raises(TrackContextProfileError) as exc_info:
        build_track_context_profile(
            _track_map(),
            {"arrangement": {"status": "ok", "artifact": absolute_path}},
        )

    assert exc_info.value.code == "NON_PORTABLE_EVIDENCE"


def test_canonical_json_pointer_is_not_mistaken_for_private_path() -> None:
    profile = build_track_context_profile(
        _track_map(),
        {
            "groove": {
                "status": "ok",
                "evidence": {"source_ref": "/analysis/timeline/beats"},
            }
        },
    )

    assert profile["groove"]["status"] == "ok"
    assert profile["groove"]["evidence"]["source_ref"] == "/analysis/timeline/beats"


def test_serialization_is_deterministic_for_equivalent_evidence_order() -> None:
    first = build_track_context_profile(
        _track_map(),
        {"groove": {"status": "ok", "value": {"z": 2, "a": 1}}},
    )
    second = build_track_context_profile(
        _track_map(),
        {"groove": {"value": {"a": 1, "z": 2}, "status": "ok"}},
    )

    assert json.dumps(first, sort_keys=False) == json.dumps(second, sort_keys=False)


def test_malformed_track_map_fails_closed() -> None:
    with pytest.raises(TrackContextProfileError) as exc_info:
        build_track_context_profile({"document_type": "sample_brain.track_map"})

    assert exc_info.value.code == "INVALID_TRACK_MAP"


def test_analyze_track_context_delegates_to_cached_context_analyzer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_cached(path: Path, **kwargs: object) -> TrackAnalysisCacheResult:
        calls.append({"path": path, **kwargs})
        return TrackAnalysisCacheResult(
            track_map=_track_map(),
            cache_status="hit",
            cache_key="cache-key",
        )

    monkeypatch.setattr("src.track_context.analyze_context_file_cached", fake_cached)

    profile = analyze_track_context(
        Path("relative-track.wav"),
        bpm_normalization="dj",
        cache_dir=Path("relative-cache"),
    )

    assert profile["document_type"] == TRACK_CONTEXT_DOCUMENT_TYPE
    assert profile["provenance"]["context_analysis_cache"] == {
        "cache_key": "cache-key",
        "status": "hit",
    }
    assert calls == [
        {
            "path": Path("relative-track.wav"),
            "bpm_normalization": "dj",
            "cache_dir": Path("relative-cache"),
            "enabled": True,
        }
    ]


def test_analyzer_failure_propagates_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_cached(path: Path, **kwargs: object) -> TrackAnalysisCacheResult:
        raise ContextAnalyzeError("AUDIO_LOAD_FAILED", "Audio file could not be read.")

    monkeypatch.setattr("src.track_context.analyze_context_file_cached", fail_cached)

    with pytest.raises(ContextAnalyzeError) as exc_info:
        analyze_track_context(Path("missing.wav"))

    assert exc_info.value.code == "AUDIO_LOAD_FAILED"
