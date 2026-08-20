from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from src.content_hash import compute_file_hash
from src.pond5_profile import resolve_pond5_profile
from src.pond5_readiness import (
    POND5_CSV_COLUMNS,
    build_pond5_bundle,
    render_pond5_csv,
    suggest_target_upload_filename,
    write_pond5_bundle,
)


def _write_audio(
    path: Path,
    *,
    sample_rate: int = 44100,
    channels: int = 2,
    subtype: str = "PCM_16",
    format: str = "WAV",
    duration_sec: float = 1.0,
) -> Path:
    frames = max(1, int(sample_rate * duration_sec))
    t = np.arange(frames, dtype=np.float32) / sample_rate
    mono = (0.05 * np.sin(2.0 * np.pi * 220.0 * t)).astype(np.float32)
    data = mono if channels == 1 else np.repeat(mono[:, None], channels, axis=1)
    sf.write(str(path), data, sample_rate, subtype=subtype, format=format)
    return path


def _track_map(path: Path, *, sample_rate: int = 44100, channels: int = 2, duration: float = 1.0) -> dict:
    return {
        "document_type": "sample_brain.track_map",
        "schema_version": "1.1.0",
        "source": {
            "original": {
                "file_name": path.name,
                "size_bytes": path.stat().st_size,
                "hash": compute_file_hash(path),
                "audio_properties": {
                    "duration_sec": duration,
                    "sample_rate_hz": sample_rate,
                    "channels": channels,
                },
            }
        },
        "analysis": {
            "musical": {
                "bpm": {
                    "status": "ok",
                    "value": 128.0,
                    "unit": "bpm",
                    "normalization": "none",
                    "source_ref": "analyze",
                }
            },
            "timeline": {},
        },
        "provenance": {"components": {"analyze": {"component": "analyze"}}},
    }


def _semantic(*terms: str) -> dict:
    fields = {
        "status": "partial" if terms else "not_run",
        "pace_character": {
            "status": "ok" if terms else "not_run",
            "value": terms[0] if terms else None,
            "source_ref": "rule_engine",
            "evidence_refs": ["track_map.analysis.musical.bpm"],
        },
    }
    if len(terms) > 1:
        fields["mood"] = {
            "status": "ok",
            "value": list(terms[1:]),
            "source_ref": "semantic_backend",
            "evidence_refs": ["semantic"],
        }
    return {
        "document_type": "sample_brain.stock_music_analysis",
        "schema_version": "1.0.0",
        "semantic": fields,
    }


def _profile(**rights_overrides: object) -> dict:
    config = {
        "pond5": {
            "contributor": {
                "composer": "Example Composer",
                "ipi": None,
                "pro": None,
                "publisher": None,
                "copyright_owner": "Example Owner",
            },
            "rights": {
                "ownership_authorized": True,
                "third_party_elements_cleared_for_resale": True,
                "cleared_for_sampling": False,
                **rights_overrides,
            },
            "listing": {"default_price_usd": 19.0},
        }
    }
    return resolve_pond5_profile(config)


def _bundle(path: Path, *, profile: dict | None = None, semantic: dict | None = None, listing: dict | None = None) -> dict:
    info = sf.info(str(path))
    return build_pond5_bundle(
        _track_map(path, sample_rate=int(info.samplerate), channels=int(info.channels), duration=float(info.frames) / info.samplerate),
        semantic or _semantic("upbeat", "energetic"),
        profile or _profile(),
        source_path=path,
        listing=listing,
    )


def _codes(bundle: dict) -> set[str]:
    return {
        item["rule_id"]
        for item in bundle["readiness"]["readiness"]["blocking"]
    }


def test_valid_synthetic_stereo_wav_is_ready(tmp_path: Path) -> None:
    source = _write_audio(tmp_path / "Track.wav")
    bundle = _bundle(source)
    assert bundle["readiness"]["readiness"]["status"] == "POND5_READY"
    assert _codes(bundle) == set()


def test_real_stock_music_analysis_shape_is_consumed(tmp_path: Path) -> None:
    from src.stock_music_analysis import produce_stock_music_analysis

    source = _write_audio(tmp_path / "Track.wav")
    track_map = _track_map(source)
    semantic = produce_stock_music_analysis(track_map)
    bundle = build_pond5_bundle(
        track_map,
        semantic,
        _profile(),
        source_path=source,
    )
    assert bundle["readiness"]["readiness"]["status"] == "POND5_READY"
    assert "upbeat" in bundle["csv_row"]["Keywords"]


def test_source_identity_mismatch_holds(tmp_path: Path) -> None:
    source = _write_audio(tmp_path / "Track.wav")
    track_map = _track_map(source)
    track_map["source"]["original"]["hash"] = {
        "algorithm": "sha256",
        "value": "0" * 64,
    }
    bundle = build_pond5_bundle(
        track_map,
        _semantic("upbeat"),
        _profile(),
        source_path=source,
    )
    assert "SOURCE_IDENTITY_MISMATCH" in _codes(bundle)


def test_mono_holds(tmp_path: Path) -> None:
    source = _write_audio(tmp_path / "Track.wav", channels=1)
    assert "AUDIO_NOT_STEREO" in _codes(_bundle(source))


def test_unsupported_sample_rate_holds(tmp_path: Path) -> None:
    source = _write_audio(tmp_path / "Track.wav", sample_rate=32000)
    assert "AUDIO_SAMPLE_RATE_UNSUPPORTED" in _codes(_bundle(source))


def test_flac_holds_as_unsupported_submission_format(tmp_path: Path) -> None:
    source = _write_audio(tmp_path / "Track.flac", format="FLAC")
    assert "AUDIO_FORMAT_UNSUPPORTED" in _codes(_bundle(source))


def test_aiff_is_supported(tmp_path: Path) -> None:
    source = _write_audio(tmp_path / "Track.aiff", format="AIFF")
    assert "AUDIO_FORMAT_UNSUPPORTED" not in _codes(_bundle(source))


def test_invalid_source_filename_gets_safe_target_without_mutation(tmp_path: Path) -> None:
    source = _write_audio(tmp_path / "Mÿ Track-name!.wav")
    before = source.read_bytes()
    bundle = _bundle(source)
    suggested = bundle["metadata"]["listing"]["target_upload_filename"]["value"]
    assert suggested == "My_Track_name.wav"
    assert source.exists()
    assert source.read_bytes() == before
    assert "TARGET_FILENAME_SUGGESTED" in {
        item["rule_id"] for item in bundle["readiness"]["readiness"]["warnings"]
    }


def test_missing_composer_holds(tmp_path: Path) -> None:
    source = _write_audio(tmp_path / "Track.wav")
    config = {
        "pond5": {
            "contributor": {"composer": None, "copyright_owner": "Owner"},
            "rights": {
                "ownership_authorized": True,
                "third_party_elements_cleared_for_resale": True,
                "cleared_for_sampling": False,
            },
        }
    }
    assert "COMPOSER_MISSING" in _codes(_bundle(source, profile=resolve_pond5_profile(config)))


def test_unset_sampling_policy_holds(tmp_path: Path) -> None:
    source = _write_audio(tmp_path / "Track.wav")
    assert "SAMPLING_POLICY_UNSET" in _codes(_bundle(source, profile=_profile(cleared_for_sampling=None)))


def test_missing_or_denied_legal_assertion_holds(tmp_path: Path) -> None:
    source = _write_audio(tmp_path / "Track.wav")
    assert "OWNERSHIP_AUTHORIZATION_UNRESOLVED" in _codes(_bundle(source, profile=_profile(ownership_authorized=None)))
    assert "THIRD_PARTY_CLEARANCE_DENIED" in _codes(_bundle(source, profile=_profile(third_party_elements_cleared_for_resale=False)))


def test_semantic_evidence_insufficient_holds(tmp_path: Path) -> None:
    source = _write_audio(tmp_path / "Track.wav")
    assert "SEMANTIC_EVIDENCE_INSUFFICIENT" in _codes(_bundle(source, semantic=_semantic()))


def test_overlong_title_and_prohibited_reference_fail_validation(tmp_path: Path) -> None:
    source = _write_audio(tmp_path / "Track.wav")
    long_listing = {
        "title": "x" * 81,
        "description": "Sounds like Daft Punk for a Spotify campaign",
        "keywords": ["music", "upbeat"],
    }
    codes = _codes(_bundle(source, listing=long_listing))
    assert "TITLE_INVALID" in codes
    assert "DESCRIPTION_INVALID" in codes


def test_duplicate_or_invalid_keywords_fail(tmp_path: Path) -> None:
    source = _write_audio(tmp_path / "Track.wav")
    listing = {"title": "Upbeat Music", "description": "Clean production.", "keywords": ["music", "music", "bad keyword"]}
    assert "KEYWORDS_INSUFFICIENT" in _codes(_bundle(source, listing=listing))


def test_csv_uses_only_proven_columns_and_escapes_utf8() -> None:
    row = {
        "OriginalFilename": "Track.wav",
        "Title": 'Bright, "Quoted" Music',
        "Description": "A café-ready description",
        "Keywords": "music,bright",
        "Copyright": "Owner",
        "Price": 19.0,
        "Composer": "must-not-leak",
    }
    rendered = render_pond5_csv(row)
    parsed = list(csv.DictReader(io.StringIO(rendered)))
    assert tuple(parsed[0].keys()) == POND5_CSV_COLUMNS
    assert parsed[0]["Title"] == 'Bright, "Quoted" Music'
    assert parsed[0]["Description"] == "A café-ready description"
    assert "Composer" not in rendered.splitlines()[0]


def test_non_csv_manual_fields_remain_in_metadata(tmp_path: Path) -> None:
    source = _write_audio(tmp_path / "Track.wav")
    bundle = _bundle(source)
    metadata = bundle["metadata"]
    assert metadata["contributor"]["composer"]["value"] == "Example Composer"
    assert metadata["rights"]["cleared_for_sampling"]["value"] is False
    assert metadata["platform"]["non_csv_submission"]["composer"] == "ui/manual|unknown"
    assert set(bundle["csv_row"]) == set(POND5_CSV_COLUMNS)


def test_platform_snapshot_has_required_per_field_contract(tmp_path: Path) -> None:
    source = _write_audio(tmp_path / "Track.wav")
    fields = _bundle(source)["readiness"]["platform"]["fields"]
    for name in ("audio", "OriginalFilename", "title", "keywords", "composer", "cleared_for_sampling", "rights_assertions"):
        record = fields[name]
        assert set(("required", "rules", "csv_supported", "primary_source_url", "snapshot_date")) <= set(record)


def test_explicit_denial_is_blocking_but_not_missing(tmp_path: Path) -> None:
    source = _write_audio(tmp_path / "Track.wav")
    bundle = _bundle(
        source,
        profile=_profile(third_party_elements_cleared_for_resale=False),
    )
    readiness = bundle["readiness"]["readiness"]
    assert "THIRD_PARTY_CLEARANCE_DENIED" in {
        item["rule_id"] for item in readiness["blocking"]
    }
    assert "THIRD_PARTY_CLEARANCE_DENIED" not in {
        item["rule_id"] for item in readiness["missing"]
    }


def test_same_inputs_produce_stable_portable_bundle(tmp_path: Path) -> None:
    source = _write_audio(tmp_path / "Track.wav")
    first = _bundle(source)
    second = _bundle(source)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    serialized = json.dumps(first)
    assert str(tmp_path) not in serialized
    assert "file://" not in serialized


def test_writer_emits_exact_bundle_files(tmp_path: Path) -> None:
    source = _write_audio(tmp_path / "Track.wav")
    bundle = _bundle(source)
    out = tmp_path / "out"
    write_pond5_bundle(bundle, out)
    assert sorted(path.name for path in out.iterdir()) == ["pond5.csv", "pond5_metadata.json", "pond5_readiness.json"]
    readiness = json.loads((out / "pond5_readiness.json").read_text(encoding="utf-8"))
    assert readiness["document_type"] == "sample_brain.pond5_readiness"
    assert readiness["readiness"]["status"] == "POND5_READY"


def test_target_filename_suggestion_is_deterministic() -> None:
    assert suggest_target_upload_filename("Hello world-track!.wav") == "Hello_world_track.wav"
    assert suggest_target_upload_filename("---.flac") == "pond5_track.wav"
