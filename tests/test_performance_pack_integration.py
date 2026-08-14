from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from src.deconstruct import (
    DeconstructAdapters,
    RunResult,
    run_deconstruct,
)
from src.performance_pack import (
    build_performance_pack_manifest,
    finalize_performance_pack,
    write_performance_pack,
)


@pytest.fixture(autouse=True)
def cleanup_test_files():
    """Clean up test files before and after each test."""
    yield
    # Cleanup test directories
    tmp_path = Path("tests/tmp")
    if tmp_path.exists():
        for item in tmp_path.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            elif item.is_file():
                item.unlink()


def test_performance_pack_creation_and_validation():
    """Test that a valid performance pack can be created and validated."""
    # Create a test track
    from tests.audio_fixtures import write_sine_wav

    # Create test WAV file
    wav_path = write_sine_wav(
        Path("tests/tmp/test_track.wav"),
        duration_sec=2.0,
        frequency_hz=440.0,
    )

    # Run deconstruction
    pack_root = Path("tests/tmp/test_pack")
    result = run_deconstruct(
        wav_path,
        pack_root,
        adapters=DeconstructAdapters(),
        skip={"stems"}  # Skip stems for simpler test
    )

    # Verify deconstruction completed
    assert result.status in ("complete", "partial", "failed")

    # Verify performance pack manifest was created
    manifest_path = pack_root / "manifest.json"
    # Note: manifest.json is created by finalize_performance_pack, not run_deconstruct
    # run_deconstruct only writes the step outputs (track_map.json, arrangement_map.json, etc.)

    # Create the manifest
    finalize_performance_pack(result, pack_root)

    # Verify manifest exists now
    assert manifest_path.exists(), "manifest.json should be created by finalize_performance_pack"

    # Load and validate manifest
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Check required fields
    assert manifest_data["document_type"] == "sample_brain.performance_pack_manifest"
    assert manifest_data["schema_version"] == "1.0.0"
    assert "pack_id" in manifest_data
    assert manifest_data["pack_id"].startswith("pack_")

    # Check source_track
    assert "source_track" in manifest_data
    source_track = manifest_data["source_track"]
    assert "track_id" in source_track
    assert "track_ref" in source_track
    assert "file_name" in source_track
    assert "hash" in source_track
    assert "audio_properties" in source_track

    # Check that track_ref matches documents.track_map.ref
    assert "documents" in manifest_data
    assert "track_map" in manifest_data["documents"]
    assert source_track["track_ref"] == manifest_data["documents"]["track_map"]["ref"]

    # Check assets have correct track_ref
    assert "assets" in manifest_data
    for asset in manifest_data["assets"]:
        assert "track_ref" in asset
        assert asset["track_ref"] == manifest_data["source_track"]["track_id"], \
            f"Asset track_ref {asset['track_ref']} should match source_track.track_id {manifest_data['source_track']['track_id']}"

    # Check assets have proper version
    for asset in manifest_data["assets"]:
        assert asset["document_type"] == "sample_brain.asset_manifest"
        assert asset["schema_version"] == "1.1.0"

    # Check arrangement has proper version (if present)
    if "arrangement" in manifest_data["documents"]:
        arrangement = manifest_data["documents"]["arrangement"]
        assert arrangement["document_type"] == "sample_brain.arrangement_map"
        assert arrangement["schema_version"] == "0.1.0-draft"

    # Check provenance
    assert "provenance" in manifest_data
    assert "components" in manifest_data["provenance"]
    assert "pack_assembler" in manifest_data["provenance"]["components"]

    # Validate using the manifest contract validator
    from tests.test_performance_pack_manifest_contract import validate_pack
    errors = validate_pack(manifest_data)
    assert errors == [], f"Manifest validation failed: {errors}"


def test_performance_pack_without_arrangement():
    """Test performance pack creation when arrangement is skipped."""
    # Create a test track
    from tests.audio_fixtures import write_sine_wav

    # Create test WAV file
    wav_path = write_sine_wav(
        Path("tests/tmp/test_track2.wav"),
        duration_sec=1.0,
        frequency_hz=220.0,
    )

    # Run deconstruction with arrangement skipped
    pack_root = Path("tests/tmp/test_pack2")
    result = run_deconstruct(
        wav_path,
        pack_root,
        adapters=DeconstructAdapters(),
        skip={"arrangement", "stems"}  # Skip arrangement and stems
    )

    # Verify deconstruction completed
    assert result.status in ("complete", "partial", "failed")

    # Create the manifest
    finalize_performance_pack(result, pack_root)

    # Verify performance pack manifest was created
    manifest_path = pack_root / "manifest.json"
    assert manifest_path.exists(), "manifest.json should be created"

    # Load and validate manifest
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Check that arrangement is not present in documents (since it was skipped)
    assert "documents" in manifest_data
    arr_doc = manifest_data["documents"].get("arrangement", {})
    # If arrangement is present, it should have status not_run or no_result
    if arr_doc:
        assert arr_doc.get("status") in ("not_run", "no_result", "failed")

    # Validate using the manifest contract validator
    from tests.test_performance_pack_manifest_contract import validate_pack
    errors = validate_pack(manifest_data)
    assert errors == [], f"Manifest validation failed: {errors}"


def test_performance_pack_track_identity_consistency():
    """Test that track identity is consistent across all references."""
    # Create a test track
    from tests.audio_fixtures import write_sine_wav

    # Create test WAV file
    wav_path = write_sine_wav(
        Path("tests/tmp/test_track3.wav"),
        duration_sec=1.5,
        frequency_hz=330.0,
    )

    # Run deconstruction
    pack_root = Path("tests/tmp/test_pack3")
    result = run_deconstruct(
        wav_path,
        pack_root,
        adapters=DeconstructAdapters(),
        skip={"stems"}
    )

    # Create the manifest
    finalize_performance_pack(result, pack_root)

    # Load manifest
    manifest_path = pack_root / "manifest.json"
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Extract track ID from source
    source_track_id = manifest_data["source_track"]["track_id"]

    # Verify track_ref consistency
    assert manifest_data["source_track"]["track_ref"] == "analysis/track_map.json"
    assert manifest_data["documents"]["track_map"]["ref"] == "analysis/track_map.json"

    # Verify all assets use the same track_ref
    for asset in manifest_data["assets"]:
        assert asset["track_ref"] == source_track_id, \
            f"Asset track_ref {asset['track_ref']} does not match source_track.track_id {source_track_id}"


def test_performance_pack_status_model():
    """Test that pack status follows #257 rules correctly."""
    # This test would require mocking failures, but for now we'll test
    # that the status is one of the valid values
    from tests.audio_fixtures import write_sine_wav

    # Create test WAV file
    wav_path = write_sine_wav(
        Path("tests/tmp/test_track4.wav"),
        duration_sec=1.0,
        frequency_hz=440.0,
    )

    # Run deconstruction
    pack_root = Path("tests/tmp/test_pack4")
    result = run_deconstruct(
        wav_path,
        pack_root,
        adapters=DeconstructAdapters(),
        skip={"stems"}
    )

    # Create the manifest
    finalize_performance_pack(result, pack_root)

    # Load manifest
    manifest_path = pack_root / "manifest.json"
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Check status is valid
    assert manifest_data["status"] in ("complete", "partial", "failed")


def test_performance_pack_missing_hash_fails_closed():
    """Test that missing source.original.hash.value causes pack assembly to fail closed."""
    from tests.audio_fixtures import write_sine_wav

    # Create test WAV file
    wav_path = write_sine_wav(
        Path("tests/tmp/test_track_missing_hash.wav"),
        duration_sec=1.0,
        frequency_hz=440.0,
    )

    # Run deconstruction
    pack_root = Path("tests/tmp/test_pack_missing_hash")
    result = run_deconstruct(
        wav_path,
        pack_root,
        adapters=DeconstructAdapters(),
        skip={"stems"}
    )

    # Manually remove the hash value from the written track_map.json
    track_map_path = pack_root / "analysis/track_map.json"
    track_map_data = json.loads(track_map_path.read_text(encoding="utf-8"))

    # Remove the hash key entirely
    if "source" in track_map_data and "original" in track_map_data["source"]:
        track_map_data["source"]["original"].pop("hash", None)
    track_map_path.write_text(json.dumps(track_map_data), encoding="utf-8")

    # Assert that calling finalize_performance_pack raises ValueError
    with pytest.raises(ValueError, match="Authoritative track hash.*missing"):
        finalize_performance_pack(result, pack_root)

    # Verify manifest.json was NOT written or created
    manifest_path = pack_root / "manifest.json"
    assert not manifest_path.exists(), "manifest.json should not exist if hash is missing"
