"""R&D Slice 3 (#680/#886): read-only catalog → #882 LibraryCandidate projection.

Quality labels
--------------
MEASURED: projected catalog fields, MFCC13 decode, deterministic candidate order.
HEURISTIC: same onset-window vs full-file feature mismatch as #882.
NOT YET CLAIMED: producer-quality match, drum-role identity, musical correctness.

Ranking math remains exclusively in ``gesture_library_ranking``.
See ``docs/GESTURE_CATALOG_ADAPTER_RND_SLICE3.md``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np

from . import config
from .gesture_analysis import GestureAnalysis
from .gesture_library_ranking import (
    ClusterRanking,
    LibraryCandidate,
    rank_gesture_library_candidates,
)

MFCC_DIM = 13
_MFCC_BYTES = MFCC_DIM * int(np.dtype(np.float32).itemsize)
ONESHOT_CLASS = "oneshot"

_SELECT_CANDIDATES = """
SELECT
    s.id AS sample_id,
    s.path AS path,
    f.class AS audio_class,
    f.loudness AS loudness,
    f.brightness AS brightness,
    f.mfcc_mean AS mfcc_mean
FROM samples s
LEFT JOIN features f ON f.sample_id = s.id
ORDER BY s.id ASC
"""


def load_gesture_library_candidates(
    catalog_path: Path | str | None = None,
) -> tuple[LibraryCandidate, ...]:
    """Project eligible oneshot feature rows into #882 ``LibraryCandidate`` values.

    Read-only and fail-soft: missing/unreadable/incompatible catalogs return ``()``.
    Invalid individual rows are skipped. Does not mutate the database.
    """
    db_path = _resolve_catalog_path(catalog_path)
    if db_path is None or not db_path.is_file():
        return ()

    try:
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    except sqlite3.Error:
        return ()

    try:
        if not _has_required_tables(conn):
            return ()
        try:
            rows = conn.execute(_SELECT_CANDIDATES).fetchall()
        except sqlite3.Error:
            return ()
    finally:
        conn.close()

    out: list[LibraryCandidate] = []
    for row in rows:
        candidate = _row_to_candidate(row)
        if candidate is not None:
            out.append(candidate)
    # ORDER BY s.id ASC already; sort again for semantic determinism.
    out.sort(key=lambda c: int(c.sample_id))
    return tuple(out)


def rank_gesture_against_catalog(
    analysis: GestureAnalysis,
    catalog_path: Path | str | None = None,
    *,
    top_n: int = 5,
) -> tuple[ClusterRanking, ...]:
    """Load catalog candidates and rank via the existing #882 seam only."""
    candidates = load_gesture_library_candidates(catalog_path)
    return rank_gesture_library_candidates(analysis, candidates, top_n=top_n)


def _resolve_catalog_path(catalog_path: Path | str | None) -> Path | None:
    try:
        if catalog_path is None:
            return Path(config.DB_PATH)
        resolved = Path(catalog_path).expanduser()
        if not resolved.is_absolute():
            resolved = (config.PROJECT_ROOT / resolved).resolve()
        else:
            resolved = resolved.resolve()
        return resolved
    except (OSError, TypeError, ValueError):
        return None


def _has_required_tables(conn: sqlite3.Connection) -> bool:
    try:
        names = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    except sqlite3.Error:
        return False
    return "samples" in names and "features" in names


def _row_to_candidate(row: sqlite3.Row | tuple) -> LibraryCandidate | None:
    try:
        sample_id_raw, path_raw, audio_class, loudness, brightness, mfcc_blob = row
    except (TypeError, ValueError):
        return None

    sample_id = _valid_sample_id(sample_id_raw)
    if sample_id is None:
        return None
    path = _valid_path(path_raw)
    if path is None:
        return None
    if not isinstance(audio_class, str) or audio_class != ONESHOT_CLASS:
        return None
    if not _is_finite_number(loudness) or not _is_finite_number(brightness):
        return None
    mfcc13 = _decode_mfcc13(mfcc_blob)
    if mfcc13 is None:
        return None
    return LibraryCandidate(
        sample_id=sample_id,
        path=path,
        audio_class=ONESHOT_CLASS,
        loudness=float(loudness),
        brightness=float(brightness),
        mfcc13=mfcc13,
    )


def _valid_sample_id(value: object) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        # Reject bool (subclass of int) and non-integers; no string coercion of paths.
        return None
    sid = int(value)
    if sid < 0:
        return None
    return str(sid)


def _valid_path(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    if value == "":
        return None
    return value


def _is_finite_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float, np.floating, np.integer)):
        return False
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError, OverflowError):
        return False


def _decode_mfcc13(blob: object) -> tuple[float, ...] | None:
    if blob is None or not isinstance(blob, (bytes, bytearray, memoryview)):
        return None
    raw = bytes(blob)
    if len(raw) != _MFCC_BYTES:
        return None
    try:
        decoded = np.frombuffer(raw, dtype=np.float32)
    except (TypeError, ValueError, BufferError):
        return None
    if decoded.shape != (MFCC_DIM,):
        return None
    if not np.isfinite(decoded).all():
        return None
    return tuple(float(x) for x in decoded)
