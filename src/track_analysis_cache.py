"""Specialized, local, regenerable cache for expensive Track-Analyse-Ergebnisse.

Issue #237. This is a *small, specialized* cache for Track-Analyse results only.

Design constraints (see docs/TRACK_ANALYSIS_CACHE_V1.md):
* Local, regenerable, outside the repo by default. No fachlicher Source-of-Truth.
* No global cache framework, no SQLite, no cloud, no new dependency.
* Cache key = SHA-256 over canonical deterministic JSON (sorted keys, no timestamps,
  no absolute paths).
* On a cache hit the *expensive* analysis values are reused; the current source file
  is re-probed so the returned Track Map still reflects the current file name and
  audio properties.
* Never serialize private/absolute paths into the cache entry or the Track Map.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

from .analyze import KEY_ANALYSIS_CONTRACT_VERSION
from .canon_audio import CANONICAL_CHANNELS, CANONICAL_SAMPLE_RATE
from .config import ANALYZE_HOP_LENGTH, ANALYZE_SR
from .content_hash import LEGACY_CONTENT_HASH_ALGORITHM, normalize_hash_record

# Bumped for #212: the analyzer now also emits a separate major/minor mode. Old
# cached analysis results (without the key-analysis contract in their fingerprint)
# must not be reused as current analyzer hits.
TRACK_ANALYSIS_CACHE_CONTRACT_VERSION = 2
CACHE_ENTRY_DOCUMENT_TYPE = "sample_brain.track_analysis_cache_entry"
CACHE_ENTRY_SCHEMA_VERSION = "1.0.0"
SCHEMA_MAJOR = 1

CACHE_DIR_ENV = "SAMPLE_BRAIN_TRACK_CACHE_DIR"
CACHE_SUBDIR = ("sample-brain", "track-analysis")


def get_cache_dir(cli_override: Optional[Path] = None) -> Path:
    """Resolve the cache directory.

    Precedence: CLI override > environment variable > platform default.
    The platform default is always user-local and outside the repository.
    """
    if cli_override is not None:
        return Path(cli_override).expanduser().resolve()
    env_value = os.environ.get(CACHE_DIR_ENV)
    if env_value:
        return Path(env_value).expanduser().resolve()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        xdg = os.environ.get("XDG_CACHE_HOME")
        base = Path(xdg) if xdg else Path.home() / ".cache"
    return (base / CACHE_SUBDIR[0] / CACHE_SUBDIR[1]).resolve()


def _canonical_json(obj: Any) -> str:
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _analysis_fingerprint_doc(
    *,
    bpm_normalization: str,
    backend_name: str,
    backend_version: str,
    sample_brain_version: str,
    model_identity: Optional[dict],
    key_analysis_contract_version: str | int = KEY_ANALYSIS_CONTRACT_VERSION,
) -> dict:
    return {
        "component": "analyze",
        "contract_version": TRACK_ANALYSIS_CACHE_CONTRACT_VERSION,
        "sample_brain_version": sample_brain_version,
        "backend": {"name": backend_name, "version": backend_version},
        "config": {
            "bpm_normalization": bpm_normalization,
            "canonical_sample_rate_hz": CANONICAL_SAMPLE_RATE,
            "canonical_channels": CANONICAL_CHANNELS,
            "analyze_sr": ANALYZE_SR,
            "analyze_hop_length": ANALYZE_HOP_LENGTH,
            "key_analysis_contract_version": key_analysis_contract_version,
        },
        "model_identity": model_identity,
    }


def compute_analysis_fingerprint(
    *,
    bpm_normalization: str,
    backend_name: str,
    backend_version: str,
    sample_brain_version: str,
    model_identity: Optional[dict] = None,
    key_analysis_contract_version: str | int = KEY_ANALYSIS_CONTRACT_VERSION,
) -> str:
    """Deterministic SHA-256 of the effective analyzer parameters + identity."""
    doc = _analysis_fingerprint_doc(
        bpm_normalization=bpm_normalization,
        backend_name=backend_name,
        backend_version=backend_version,
        sample_brain_version=sample_brain_version,
        model_identity=model_identity,
        key_analysis_contract_version=key_analysis_contract_version,
    )
    return hashlib.sha256(_canonical_json(doc).encode("utf-8")).hexdigest()


def _source_hash_record(source_content_hash: object) -> dict[str, str]:
    """Normalize current records while preserving the pre-#417 string API.

    Historical callers passed a bare SHA-1 value. Keeping this compatibility
    layer reproduces the exact legacy cache key so on-touch migration can still
    find old entries. New code passes an explicit ``{algorithm, value}`` record.
    """
    if isinstance(source_content_hash, dict):
        return normalize_hash_record(source_content_hash)
    if isinstance(source_content_hash, str):
        return {
            "algorithm": LEGACY_CONTENT_HASH_ALGORITHM,
            "value": source_content_hash,
        }
    raise ValueError("source_content_hash must be a hash record or legacy string")


def compute_cache_key(
    *,
    source_content_hash: object,
    bpm_normalization: str,
    backend_name: str,
    backend_version: str,
    sample_brain_version: str,
    model_identity: Optional[dict] = None,
    key_analysis_contract_version: str | int = KEY_ANALYSIS_CONTRACT_VERSION,
) -> str:
    """Deterministic SHA-256 cache key including algorithm-qualified content."""
    doc = _analysis_fingerprint_doc(
        bpm_normalization=bpm_normalization,
        backend_name=backend_name,
        backend_version=backend_version,
        sample_brain_version=sample_brain_version,
        model_identity=model_identity,
        key_analysis_contract_version=key_analysis_contract_version,
    )
    doc["source_content_hash"] = _source_hash_record(source_content_hash)
    return hashlib.sha256(_canonical_json(doc).encode("utf-8")).hexdigest()


def build_cache_entry(
    *,
    cache_key: str,
    source_content_hash: object,
    analysis_fingerprint: str,
    track_map: dict,
    provenance_component: dict,
    quality: dict,
) -> dict:
    """Build a cache entry document (never stores private/absolute paths)."""
    return {
        "document_type": CACHE_ENTRY_DOCUMENT_TYPE,
        "schema_version": CACHE_ENTRY_SCHEMA_VERSION,
        "cache_key": cache_key,
        "source_content_hash": _source_hash_record(source_content_hash),
        "analysis_fingerprint": analysis_fingerprint,
        "track_map": track_map,
        "provenance_component": provenance_component,
        "quality": quality,
    }


def _entry_path(cache_dir: Path, cache_key: str) -> Path:
    return cache_dir / f"{cache_key}.json"


def read_cache_entry(cache_dir: Path, cache_key: str) -> Optional[dict]:
    """Read and structurally validate a cache entry from disk."""
    path = _entry_path(cache_dir, cache_key)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            entry = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(entry, dict):
        return None
    if entry.get("document_type") != CACHE_ENTRY_DOCUMENT_TYPE:
        return None
    try:
        major = int(str(entry.get("schema_version", "0.0.0")).split(".")[0])
    except (ValueError, AttributeError, TypeError):
        return None
    if major != SCHEMA_MAJOR:
        return None
    if entry.get("cache_key") != cache_key:
        return None
    required = (
        "source_content_hash",
        "analysis_fingerprint",
        "track_map",
        "provenance_component",
        "quality",
    )
    if not all(k in entry for k in required):
        return None
    return entry


def validate_cache_entry(
    entry: dict,
    *,
    expected_cache_key: str,
    expected_source_hash: object,
    expected_analysis_fingerprint: str,
) -> bool:
    """Deep validation of a structurally valid entry against current expectations."""
    if not isinstance(entry, dict):
        return False
    if entry.get("cache_key") != expected_cache_key:
        return False
    try:
        expected_record = _source_hash_record(expected_source_hash)
    except ValueError:
        return False
    if entry.get("source_content_hash") != expected_record:
        return False
    if entry.get("analysis_fingerprint") != expected_analysis_fingerprint:
        return False
    return True


def write_cache_entry(cache_dir: Path, cache_key: str, entry: dict) -> None:
    """Atomically write a cache entry (temp file + flush + os.replace)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _entry_path(cache_dir, cache_key)
    fd, tmp_name = tempfile.mkstemp(dir=str(cache_dir), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(_canonical_json(entry))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


__all__ = [
    "TRACK_ANALYSIS_CACHE_CONTRACT_VERSION",
    "CACHE_ENTRY_DOCUMENT_TYPE",
    "CACHE_ENTRY_SCHEMA_VERSION",
    "CACHE_DIR_ENV",
    "get_cache_dir",
    "compute_analysis_fingerprint",
    "compute_cache_key",
    "build_cache_entry",
    "read_cache_entry",
    "validate_cache_entry",
    "write_cache_entry",
]
