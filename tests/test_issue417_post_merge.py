from __future__ import annotations

import hashlib

from src.content_hash import hash_record
from src.track_analysis_cache import compute_cache_key


def _historical_pre_417_cache_key(source_sha1: str) -> str:
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


def test_legacy_sha1_forms_reproduce_historical_cache_key_but_sha256_does_not() -> None:
    legacy = "1" * 40
    current = hash_record("sha256", "2" * 64)
    common = {
        "bpm_normalization": "none",
        "backend_name": "librosa",
        "backend_version": "0.11.0",
        "sample_brain_version": "0.1.0",
    }
    expected = _historical_pre_417_cache_key(legacy)

    assert compute_cache_key(source_content_hash=legacy, **common) == expected
    assert (
        compute_cache_key(
            source_content_hash=hash_record("sha1", legacy),
            **common,
        )
        == expected
    )
    assert compute_cache_key(source_content_hash=current, **common) != expected
