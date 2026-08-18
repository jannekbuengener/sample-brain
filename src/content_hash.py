"""Versioned content-hash primitives for Sample Brain (#417).

New content identity uses SHA-256. SHA-1 remains available only for explicit
legacy compatibility so old manifests/cache/catalog rows can be read without
being silently reinterpreted.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterable

DEFAULT_CONTENT_HASH_ALGORITHM = "sha256"
LEGACY_CONTENT_HASH_ALGORITHM = "sha1"
SUPPORTED_CONTENT_HASH_ALGORITHMS = frozenset(
    {DEFAULT_CONTENT_HASH_ALGORITHM, LEGACY_CONTENT_HASH_ALGORITHM}
)
_HEX_RE = re.compile(r"^[0-9a-f]+$")
_EXPECTED_HEX_LENGTH = {"sha1": 40, "sha256": 64}


def _validate_algorithm(algorithm: str) -> str:
    normalized = str(algorithm).lower()
    if normalized not in SUPPORTED_CONTENT_HASH_ALGORITHMS:
        raise ValueError(f"unsupported content hash algorithm: {algorithm!r}")
    return normalized


def hash_record(algorithm: str, value: str) -> dict[str, str]:
    """Return a validated portable ``{algorithm, value}`` hash record."""
    algorithm = _validate_algorithm(algorithm)
    normalized_value = str(value).lower()
    expected_length = _EXPECTED_HEX_LENGTH[algorithm]
    if len(normalized_value) != expected_length or not _HEX_RE.fullmatch(normalized_value):
        raise ValueError(
            f"invalid {algorithm} digest: expected {expected_length} lowercase hex chars"
        )
    return {"algorithm": algorithm, "value": normalized_value}


def normalize_hash_record(record: object) -> dict[str, str]:
    """Validate an external algorithm-qualified hash record.

    Bare digest strings are deliberately rejected at new external boundaries.
    """
    if not isinstance(record, dict):
        raise ValueError("content hash must be an {algorithm, value} record")
    algorithm = record.get("algorithm")
    value = record.get("value")
    if not isinstance(algorithm, str) or not isinstance(value, str):
        raise ValueError("content hash requires string algorithm and value")
    return hash_record(algorithm, value)


def compute_file_hash(
    path: Path,
    *,
    algorithm: str = DEFAULT_CONTENT_HASH_ALGORITHM,
    blocksize: int = 65536,
) -> dict[str, str]:
    """Hash one file using an explicit allowlisted algorithm."""
    algorithm = _validate_algorithm(algorithm)
    hasher = hashlib.new(algorithm)
    with open(Path(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(blocksize), b""):
            hasher.update(chunk)
    return hash_record(algorithm, hasher.hexdigest())


def compute_file_hashes(
    path: Path,
    *,
    algorithms: Iterable[str] = (
        DEFAULT_CONTENT_HASH_ALGORITHM,
        LEGACY_CONTENT_HASH_ALGORITHM,
    ),
    blocksize: int = 65536,
) -> dict[str, dict[str, str]]:
    """Compute multiple content digests in one file pass."""
    normalized = tuple(dict.fromkeys(_validate_algorithm(a) for a in algorithms))
    if not normalized:
        raise ValueError("at least one content hash algorithm is required")
    hashers = {algorithm: hashlib.new(algorithm) for algorithm in normalized}
    with open(Path(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(blocksize), b""):
            for hasher in hashers.values():
                hasher.update(chunk)
    return {
        algorithm: hash_record(algorithm, hasher.hexdigest())
        for algorithm, hasher in hashers.items()
    }


def file_matches_hash(path: Path, expected: object) -> bool:
    """Verify a file against the algorithm declared by ``expected``."""
    record = normalize_hash_record(expected)
    return compute_file_hash(path, algorithm=record["algorithm"]) == record


__all__ = [
    "DEFAULT_CONTENT_HASH_ALGORITHM",
    "LEGACY_CONTENT_HASH_ALGORITHM",
    "SUPPORTED_CONTENT_HASH_ALGORITHMS",
    "hash_record",
    "normalize_hash_record",
    "compute_file_hash",
    "compute_file_hashes",
    "file_matches_hash",
]
