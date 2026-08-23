"""Tests for Pond5 readiness bundle generator and validator (#451)."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from src.pond5_prepare import (
    POND5_METADATA_DOCUMENT_TYPE,
    POND5_READINESS_DOCUMENT_TYPE,
    evaluate_pond5_readiness,
    export_pond5_csv,
    generate_pond5_listing,
    prepare_pond5_bundle,
    probe_submission_technical,
    suggest_target_upload_filename,
)
from tests.audio_fixtures import write_sine_wav


def _valid_config() -> dict[str, object]:
    return {
        "pond5": {
            "contributor": {
                "composer": "Jannek Bungener",
                "ipi": "00123456789",
                "pro": "BMI",
                "publisher": "SampleBrain Music",
                "copyright_owner": "Jannek Bungener",
            },
            "rights": {
                "ownership_authorized": True,
                "third_party_elements_cleared_for_resale": True,
                "cleared_for_sampling": False,
            },
            "listing": {
                "default_price_usd": 49.0,
            },
        }
    }


def test_suggest_target_upload_filename():
    assert suggest_target_upload_filename("My Track - 01 (Final).wav") == "My_Track_01_Final.wav"
    assert suggest_target_upload_filename("cool---track.aiff") == "cool_track.aiff"
    assert suggest_target_upload_filename("____.wav") == "track.wav"


def write_stereo_sine_wav(path: Path, *, duration_sec: float = 2.0, sr: int = 44100, channels: int = 2) -> Path:
    import numpy as np
    import soundfile as sf
    path.parent.mkdir(parents=True, exist_ok=True)
    sample_count = max(1, int(sr * duration_sec))
    t = np.linspace(0.0, duration_sec, sample_count, endpoint=False, dtype=np.float32)
    wave_mono = 0.5 * np.sin(2.0 * np.pi * 440.0 * t)
    if channels == 1:
        wave_out = wave_mono
    else:
        wave_out = np.column_stack([wave_mono] * channels)
    sf.write(path, wave_out.astype(np.float32), sr, subtype="PCM_16")
    return path


def test_synthetic_stereo_wav_pass(tmp_path: Path):
    wav_path = tmp_path / "test_stereo_44k.wav"
    write_stereo_sine_wav(wav_path, duration_sec=2.0, sr=44100, channels=2)

    overrides = {
        "listing": {
            "keywords": ["ambient", "electronic"],
        }
    }

    output_dir = tmp_path / "bundle_out"
    doc = prepare_pond5_bundle(
        wav_path, output_dir, _valid_config(), per_track_overrides=overrides
    )

    assert doc["document_type"] == POND5_READINESS_DOCUMENT_TYPE
    assert doc["readiness"]["status"] == "POND5_READY"

    # Verify generated bundle files
    assert (output_dir / "pond5_metadata.json").is_file()
    assert (output_dir / "pond5_readiness.json").is_file()
    assert (output_dir / "pond5.csv").is_file()

    metadata = json.loads((output_dir / "pond5_metadata.json").read_text(encoding="utf-8"))
    assert metadata["document_type"] == POND5_METADATA_DOCUMENT_TYPE
    assert metadata["submission_channel"] == "ui/manual"

    # CSV checks
    with open(output_dir / "pond5.csv", mode="r", encoding="utf-8") as f:
        reader = list(csv.reader(f))
        assert reader[0] == ["OriginalFilename", "Title", "Description", "Keywords", "Copyright", "Price"]
        assert reader[1][0] == "test_stereo_44k.wav"
        assert reader[1][4] == "Jannek Bungener"
        assert reader[1][5] == "49.00"


def test_mono_wav_hold(tmp_path: Path):
    wav_path = tmp_path / "test_mono.wav"
    write_stereo_sine_wav(wav_path, duration_sec=2.0, sr=44100, channels=1)

    output_dir = tmp_path / "bundle_out"
    doc = prepare_pond5_bundle(wav_path, output_dir, _valid_config())

    assert doc["readiness"]["status"] == "HOLD"
    blocking = [b["rule_id"] for b in doc["readiness"]["blocking"]]
    assert "TECHNICAL_FAILURE" in blocking


def test_unsupported_sample_rate_hold(tmp_path: Path):
    wav_path = tmp_path / "test_22k.wav"
    write_stereo_sine_wav(wav_path, duration_sec=2.0, sr=22050, channels=2)

    output_dir = tmp_path / "bundle_out"
    doc = prepare_pond5_bundle(wav_path, output_dir, _valid_config())

    assert doc["readiness"]["status"] == "HOLD"
    blocking = [b["rule_id"] for b in doc["readiness"]["blocking"]]
    assert "TECHNICAL_FAILURE" in blocking


def test_missing_composer_hold(tmp_path: Path):
    wav_path = tmp_path / "test_stereo.wav"
    write_stereo_sine_wav(wav_path, duration_sec=2.0, sr=44100, channels=2)

    cfg = _valid_config()
    cfg["pond5"]["contributor"]["composer"] = None

    output_dir = tmp_path / "bundle_out"
    doc = prepare_pond5_bundle(wav_path, output_dir, cfg)

    assert doc["readiness"]["status"] == "HOLD"
    blocking = [b["rule_id"] for b in doc["readiness"]["blocking"]]
    assert "COMPOSER_MISSING" in blocking


def test_unset_sampling_hold(tmp_path: Path):
    wav_path = tmp_path / "test_stereo.wav"
    write_stereo_sine_wav(wav_path, duration_sec=2.0, sr=44100, channels=2)

    cfg = _valid_config()
    cfg["pond5"]["rights"]["cleared_for_sampling"] = None

    output_dir = tmp_path / "bundle_out"
    doc = prepare_pond5_bundle(wav_path, output_dir, cfg)

    assert doc["readiness"]["status"] == "HOLD"
    blocking = [b["rule_id"] for b in doc["readiness"]["blocking"]]
    assert "SAMPLING_UNSET" in blocking


def test_missing_legal_assertion_hold(tmp_path: Path):
    wav_path = tmp_path / "test_stereo.wav"
    write_stereo_sine_wav(wav_path, duration_sec=2.0, sr=44100, channels=2)

    cfg = _valid_config()
    cfg["pond5"]["rights"]["ownership_authorized"] = False

    output_dir = tmp_path / "bundle_out"
    doc = prepare_pond5_bundle(wav_path, output_dir, cfg)

    assert doc["readiness"]["status"] == "HOLD"
    blocking = [b["rule_id"] for b in doc["readiness"]["blocking"]]
    assert "RIGHTS_DENIED" in blocking


def test_title_over_80_invalid_hold(tmp_path: Path):
    wav_path = tmp_path / "test_stereo.wav"
    write_stereo_sine_wav(wav_path, duration_sec=2.0, sr=44100, channels=2)

    overrides = {
        "listing": {
            "title": "A" * 81,
        }
    }

    output_dir = tmp_path / "bundle_out"
    doc = prepare_pond5_bundle(
        wav_path, output_dir, _valid_config(), per_track_overrides=overrides
    )

    assert doc["readiness"]["status"] == "HOLD"
    blocking = [b["rule_id"] for b in doc["readiness"]["blocking"]]
    assert "LISTING_INVALID" in blocking


def test_artist_brand_leakage_invalid_hold(tmp_path: Path):
    wav_path = tmp_path / "test_stereo.wav"
    write_stereo_sine_wav(wav_path, duration_sec=2.0, sr=44100, channels=2)

    overrides = {
        "listing": {
            "title": "Epic Track in the style of Hans Zimmer",
        }
    }

    output_dir = tmp_path / "bundle_out"
    doc = prepare_pond5_bundle(
        wav_path, output_dir, _valid_config(), per_track_overrides=overrides
    )

    assert doc["readiness"]["status"] == "HOLD"
    blocking = [b["rule_id"] for b in doc["readiness"]["blocking"]]
    assert "LISTING_INVALID" in blocking


def test_csv_utf8_escaping_and_columns(tmp_path: Path):
    csv_path = tmp_path / "test_out.csv"
    listing = {
        "target_upload_filename": {"value": 'track_with_"quotes"_,and_commas.wav'},
        "title": {"value": 'Cool, "Epic" Track'},
        "description": {"value": 'A track with\nnewline and "quotes"'},
        "keywords": {"items": ["ambient", "dark", "epic"]},
        "copyright": {"value": "Jannek & Co."},
        "price": {"value": 29.99},
    }

    export_pond5_csv(listing, csv_path)

    with open(csv_path, "r", encoding="utf-8") as f:
        content = f.read()
        assert "OriginalFilename,Title,Description,Keywords,Copyright,Price" in content
        assert 'track_with_"quotes"_,and_commas.wav' in content or 'track_with_""quotes""_' in content

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = list(csv.reader(f))
        assert len(reader) == 2
        assert reader[0] == ["OriginalFilename", "Title", "Description", "Keywords", "Copyright", "Price"]
        assert reader[1][1] == 'Cool, "Epic" Track'
        assert reader[1][5] == "29.99"


def test_non_csv_values_retained_in_metadata(tmp_path: Path):
    wav_path = tmp_path / "test_stereo.wav"
    write_stereo_sine_wav(wav_path, duration_sec=2.0, sr=44100, channels=2)

    output_dir = tmp_path / "bundle_out"
    doc = prepare_pond5_bundle(wav_path, output_dir, _valid_config())

    assert doc["contributor"]["composer"]["value"] == "Jannek Bungener"
    assert doc["contributor"]["pro"]["value"] == "BMI"
    assert doc["contributor"]["publisher"]["value"] == "SampleBrain Music"
    assert doc["rights"]["cleared_for_sampling"]["value"] is False


def test_no_private_paths_serialized(tmp_path: Path):
    wav_path = tmp_path / "secret_folder" / "private_track.wav"
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    write_stereo_sine_wav(wav_path, duration_sec=2.0, sr=44100, channels=2)

    output_dir = tmp_path / "bundle_out"
    prepare_pond5_bundle(wav_path, output_dir, _valid_config())

    raw_json = (output_dir / "pond5_metadata.json").read_text(encoding="utf-8")
    assert str(tmp_path) not in raw_json
    assert "/secret_folder/" not in raw_json
    assert "private_track.wav" in raw_json
