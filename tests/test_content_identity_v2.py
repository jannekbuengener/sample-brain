from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

import src.config as config_module
import src.db as db_module
from src.content_hash import (
    DEFAULT_CONTENT_HASH_ALGORITHM,
    LEGACY_CONTENT_HASH_ALGORITHM,
    compute_file_hash,
    compute_file_hashes,
    hash_record,
)
from src.context_analyze import analyze_context_file
from src.performance_pack_import import _verify_audio_integrity
from src.scan import run_scan
from src.track_analysis_cache import (
    build_cache_entry,
    compute_cache_key,
    validate_cache_entry,
)
from tests.audio_fixtures import write_sine_wav


def test_content_hash_defaults_to_sha256_and_legacy_sha1_is_explicit(tmp_path: Path) -> None:
    path = tmp_path / "payload.bin"
    payload = b"sample-brain-content-identity-v2"
    path.write_bytes(payload)

    current = compute_file_hash(path)
    legacy = compute_file_hash(path, algorithm=LEGACY_CONTENT_HASH_ALGORITHM)
    both = compute_file_hashes(path, algorithms=("sha256", "sha1"))

    assert DEFAULT_CONTENT_HASH_ALGORITHM == "sha256"
    assert current == hash_record("sha256", hashlib.sha256(payload).hexdigest())
    assert legacy == hash_record("sha1", hashlib.sha1(payload).hexdigest())
    assert both["sha256"] == current
    assert both["sha1"] == legacy


def test_track_map_new_write_declares_sha256(tmp_path: Path) -> None:
    source = write_sine_wav(
        tmp_path / "tone.wav", duration_sec=0.5, frequency_hz=440.0
    )
    track_map = analyze_context_file(source)

    source_hash = track_map["source"]["original"]["hash"]
    assert source_hash["algorithm"] == "sha256"
    assert len(source_hash["value"]) == 64
    assert (
        track_map["provenance"]["components"]["context_source"]["configuration"][
            "hash_algorithm"
        ]
        == "sha256"
    )


def test_legacy_catalog_upgrade_marks_old_rows_as_sha1_without_rehash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    legacy_value = "a" * 40
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE samples (
                    id INTEGER PRIMARY KEY,
                    path TEXT UNIQUE NOT NULL,
                    relpath TEXT,
                    samplerate INT,
                    channels INT,
                    duration REAL,
                    size_bytes INT,
                    hash TEXT
                )
                """
            )
        )
        conn.execute(
            text("INSERT INTO samples(path, hash) VALUES (:path, :hash)"),
            {"path": "legacy.wav", "hash": legacy_value},
        )

    monkeypatch.setenv("SAMPLE_BRAIN_DB_PATH", str(db_path))
    config_module.DB_PATH = db_path
    db_module.init_db()

    with db_module.get_engine().begin() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(samples)"))}
        row = conn.execute(
            text("SELECT hash, hash_algorithm FROM samples WHERE path='legacy.wav'")
        ).fetchone()

    assert "hash_algorithm" in cols
    assert row == (legacy_value, None)
    identity = db_module.find_sample_identity_by_path("legacy.wav")
    assert identity == (1, hash_record("sha1", legacy_value))


def test_new_scan_writes_sha256_algorithm_to_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "catalog.db"
    samples_dir = tmp_path / "samples"
    write_sine_wav(samples_dir / "tone.wav", duration_sec=0.25, frequency_hz=220.0)

    monkeypatch.setenv("SAMPLE_BRAIN_DB_PATH", str(db_path))
    config_module.DB_PATH = db_path
    db_module.init_db()
    run_scan(custom_roots=[samples_dir], limit=1)

    with db_module.get_engine().begin() as conn:
        row = conn.execute(
            text("SELECT hash, hash_algorithm FROM samples ORDER BY id LIMIT 1")
        ).fetchone()

    assert row is not None
    assert row[1] == "sha256"
    assert len(row[0]) == 64


def test_pack_integrity_verifies_the_declared_hash_algorithm(tmp_path: Path) -> None:
    wav = write_sine_wav(tmp_path / "tone.wav", duration_sec=0.25, frequency_hz=330.0)
    import soundfile as sf

    with sf.SoundFile(str(wav)) as audio:
        props = {
            "sample_rate_hz": int(audio.samplerate),
            "channels": int(audio.channels),
            "n_samples": int(len(audio)),
        }

    sha1 = compute_file_hash(wav, algorithm="sha1")
    sha256 = compute_file_hash(wav, algorithm="sha256")

    legacy_result = _verify_audio_integrity(
        wav, expected_hash=sha1, expected_props=props, audio_kind="ASSET"
    )
    current_result = _verify_audio_integrity(
        wav, expected_hash=sha256, expected_props=props, audio_kind="ASSET"
    )

    assert legacy_result["hash"] == sha1["value"]
    assert legacy_result["hash_algorithm"] == "sha1"
    assert current_result["hash"] == sha256["value"]
    assert current_result["hash_algorithm"] == "sha256"


def test_track_analysis_cache_distinguishes_algorithms_and_reads_legacy_record() -> None:
    sha1 = hash_record("sha1", "1" * 40)
    sha256 = hash_record("sha256", "2" * 64)
    common = {
        "bpm_normalization": "none",
        "backend_name": "librosa",
        "backend_version": "0.11.0",
        "sample_brain_version": "0.1.0",
    }

    legacy_key = compute_cache_key(source_content_hash=sha1, **common)
    current_key = compute_cache_key(source_content_hash=sha256, **common)
    assert legacy_key != current_key

    entry = build_cache_entry(
        cache_key=legacy_key,
        source_content_hash=sha1,
        analysis_fingerprint="analysis-v1",
        track_map={"document_type": "sample_brain.track_map"},
        provenance_component={},
        quality={},
    )
    assert entry["source_content_hash"] == sha1
    assert validate_cache_entry(
        entry,
        expected_cache_key=legacy_key,
        expected_source_hash=sha1,
        expected_analysis_fingerprint="analysis-v1",
    )
    assert not validate_cache_entry(
        entry,
        expected_cache_key=legacy_key,
        expected_source_hash=sha256,
        expected_analysis_fingerprint="analysis-v1",
    )


def test_asset_analysis_validates_declared_sha1_and_sha256_and_rejects_malformed(tmp_path: Path) -> None:
    from src.asset_analysis import reanalyze_rendered_output

    wav = write_sine_wav(tmp_path / "asset.wav", duration_sec=0.25, frequency_hz=440.0)
    sha1 = compute_file_hash(wav, algorithm="sha1")
    sha256 = compute_file_hash(wav, algorithm="sha256")
    props = {"sample_rate_hz": 44100, "channels": 1, "n_samples": 11025}

    # 1. Declared SHA-256 succeeds
    out_sha256 = {
        "file_ref": "asset.wav",
        "hash": sha256,
        "audio_properties": props,
    }
    res_sha256 = reanalyze_rendered_output(out_sha256, tmp_path)
    assert res_sha256.status in ("ok", "partial")
    assert res_sha256.analysis["analyzed_output"]["hash"] == sha256

    # 2. Declared legacy SHA-1 succeeds
    out_sha1 = {
        "file_ref": "asset.wav",
        "hash": sha1,
        "audio_properties": props,
    }
    res_sha1 = reanalyze_rendered_output(out_sha1, tmp_path)
    assert res_sha1.status in ("ok", "partial")
    assert res_sha1.analysis["analyzed_output"]["hash"] == sha1

    # 3. Unknown algorithm fails closed
    out_unknown = {
        "file_ref": "asset.wav",
        "hash": {"algorithm": "md5", "value": "a" * 32},
        "audio_properties": props,
    }
    res_unknown = reanalyze_rendered_output(out_unknown, tmp_path)
    assert res_unknown.status == "failed"
    assert res_unknown.error["code"] == "RENDERED_ASSET_HASH_MISMATCH"

    # 4. Malformed hash length fails closed
    out_malformed = {
        "file_ref": "asset.wav",
        "hash": {"algorithm": "sha256", "value": "a" * 40},
        "audio_properties": props,
    }
    res_malformed = reanalyze_rendered_output(out_malformed, tmp_path)
    assert res_malformed.status == "failed"
    assert res_malformed.error["code"] == "RENDERED_ASSET_HASH_MISMATCH"


def test_stem_spike_audio_manifest_hash_sha256_and_weight_hash_semantics(tmp_path: Path) -> None:
    from tools.stem_separator_spike import map_stem_to_manifest

    source_hash = "a" * 64
    output_hash = "b" * 64
    weight_hash = {"algorithm": "sha256", "value": "c" * 64}
    model_identity = {
        "family": "htdemucs",
        "name": "htdemucs",
        "checkpoint": "955717e8",
        "weight_hash": weight_hash,
        "code_license": "MIT",
        "weight_license": "UNKNOWN_UNVERIFIED",
    }
    props = {"sample_rate_hz": 44100, "channels": 1, "n_samples": 44100}

    manifest = map_stem_to_manifest(
        stem_id="stem_drums_test",
        stem_kind="drums",
        track_ref="track_1234567890abcdef",
        source_hash=source_hash,
        source_properties=props,
        file_ref="drums.wav",
        output_hash=output_hash,
        output_properties=props,
        model_identity=model_identity,
        backend_version="0.44.5",
    )

    assert manifest["source"]["hash"]["algorithm"] == "sha256"
    assert manifest["source"]["hash"]["value"] == source_hash
    assert manifest["output"]["hash"]["algorithm"] == "sha256"
    assert manifest["output"]["hash"]["value"] == output_hash
    assert manifest["provenance"]["model"]["weight_hash"] == weight_hash
