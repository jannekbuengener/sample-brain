from __future__ import annotations

import hashlib
from pathlib import Path

from src.content_hash import compute_file_hash, hash_record
from src.track_analysis_cache import compute_cache_key
from tests.audio_fixtures import write_sine_wav


def _pre_417_cache_key(source_sha1: str) -> str:
    """Reproduce the historical pre-#417 cache-key JSON shape exactly."""
    import src.track_analysis_cache as tac

    doc = tac._analysis_fingerprint_doc(
        bpm_normalization="none",
        backend_name="librosa",
        backend_version="0.11.0",
        sample_brain_version="0.1.0",
        model_identity=None,
    )
    doc["source_content_hash"] = source_sha1
    return hashlib.sha256(tac._canonical_json(doc).encode("utf-8")).hexdigest()


def test_legacy_sha1_record_reproduces_pre_417_cache_key() -> None:
    legacy = "1" * 40
    common = {
        "bpm_normalization": "none",
        "backend_name": "librosa",
        "backend_version": "0.11.0",
        "sample_brain_version": "0.1.0",
    }
    expected = _pre_417_cache_key(legacy)

    assert compute_cache_key(source_content_hash=legacy, **common) == expected
    assert (
        compute_cache_key(
            source_content_hash=hash_record("sha1", legacy),
            **common,
        )
        == expected
    )


def test_asset_analysis_rejects_well_formed_wrong_digest(tmp_path: Path) -> None:
    from src.asset_analysis import ERR_HASH_MISMATCH, reanalyze_rendered_output

    wav = write_sine_wav(
        tmp_path / "asset.wav", duration_sec=0.25, frequency_hz=440.0
    )
    actual = compute_file_hash(wav)
    wrong_value = ("0" if actual["value"][0] != "0" else "1") + actual["value"][1:]
    output = {
        "file_ref": "asset.wav",
        "hash": {"algorithm": "sha256", "value": wrong_value},
        "audio_properties": {
            "sample_rate_hz": 44100,
            "channels": 1,
            "n_samples": 11025,
        },
    }

    result = reanalyze_rendered_output(output, tmp_path)
    assert result.status == "failed"
    assert result.error is not None
    assert result.error["code"] == ERR_HASH_MISMATCH


def test_sha256_canonical_examples_use_64_hex_values() -> None:
    import re

    for path in (Path("docs/TRACK_MAP_V1.md"), Path("docs/STEM_MANIFEST_V1.md")):
        text = path.read_text(encoding="utf-8")
        invalid = re.search(
            r'"algorithm"\s*:\s*"sha256"\s*,\s*"value"\s*:\s*"[0-9a-f]{40}"',
            text,
            re.IGNORECASE,
        )
        assert invalid is None, f"{path} still relabels a 40-char SHA-1 value as SHA-256"


def test_performance_pack_canon_documents_hash_migration() -> None:
    text = Path("docs/PERFORMANCE_PACK_MANIFEST_V1.md").read_text(encoding="utf-8").lower()
    assert "sha-256" in text
    assert "sha-1" in text
    assert "legacy" in text
