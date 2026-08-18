from pathlib import Path

from .content_hash import DEFAULT_CONTENT_HASH_ALGORITHM, compute_file_hash


def file_hash(
    path: Path,
    blocksize: int = 65536,
    *,
    algorithm: str = DEFAULT_CONTENT_HASH_ALGORITHM,
) -> str:
    """Return the content digest value for ``path``.

    New callers default to SHA-256. Legacy SHA-1 must be requested explicitly
    with ``algorithm="sha1"``. External/persisted contracts should carry the
    algorithm alongside this value rather than serializing a bare digest.
    """
    return compute_file_hash(
        Path(path), algorithm=algorithm, blocksize=blocksize
    )["value"]
