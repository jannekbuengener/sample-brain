from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import sqlite_vec

from . import config
from .db import get_embedding_model_by_id, get_engine, text, upsert_vector_index_state
from .index import decode_embedding_blob, normalize_vectors
from .search_filters import sync_pred_type_tags
from .vec_availability import format_availability_message, probe_sqlite_vec

VEC_SAMPLE_CURRENT_TABLE = "vec_sample_current"
SQLITE_VEC_BACKEND = "sqlite-vec"


class VecIndexUnavailableError(RuntimeError):
    """Raised when sqlite-vec is required but cannot be loaded."""


@dataclass(frozen=True)
class VecRebuildResult:
    model_id: int
    embedding_dim: int
    sample_count: int
    source_fingerprint: str
    vec_table_name: str


def require_sqlite_vec() -> None:
    report = probe_sqlite_vec()
    if not report.available:
        raise VecIndexUnavailableError(format_availability_message(report))


def enable_vec_extension(conn: sqlite3.Connection) -> None:
    require_sqlite_vec()
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)


def open_vec_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or config.DB_PATH
    conn = sqlite3.connect(str(path))
    enable_vec_extension(conn)
    return conn


def compute_source_fingerprint(rows: list[tuple[int, str]]) -> str:
    sorted_rows = sorted(rows, key=lambda item: (item[0], item[1]))
    payload = "\n".join(
        f"{sample_id}:{source_hash}" for sample_id, source_hash in sorted_rows
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def load_current_embedding_rows(model_id: int) -> list[tuple[int, bytes, str, int]]:
    engine = get_engine()
    query = """
        SELECT e.sample_id, e.embedding, e.source_hash, m.embedding_dim
        FROM sample_embeddings e
        JOIN embedding_models m ON m.id = e.model_id
        JOIN samples s ON s.id = e.sample_id
        WHERE e.model_id = :model_id
          AND s.hash IS NOT NULL
          AND e.source_hash = s.hash
        ORDER BY e.sample_id
    """
    with engine.begin() as conn:
        rows = conn.execute(text(query), {"model_id": model_id}).fetchall()
    return [(row[0], row[1], row[2], row[3]) for row in rows]


def rebuild_vec0_cache(
    model_id: int,
    db_path: Path | None = None,
) -> VecRebuildResult:
    model = get_embedding_model_by_id(model_id)
    if model is None:
        raise ValueError(f"Unknown embedding model_id={model_id}")

    rows = load_current_embedding_rows(model_id)
    embedding_dim = model["embedding_dim"]
    fingerprint_rows = [(sample_id, source_hash) for sample_id, _, source_hash, _ in rows]
    source_fingerprint = compute_source_fingerprint(fingerprint_rows)

    conn = open_vec_connection(db_path)
    try:
        conn.execute(f"DROP TABLE IF EXISTS {VEC_SAMPLE_CURRENT_TABLE}")
        conn.execute(
            f"""
            CREATE VIRTUAL TABLE {VEC_SAMPLE_CURRENT_TABLE} USING vec0(
              embedding float[{embedding_dim}]
            )
            """
        )

        insert_sql = f"""
            INSERT INTO {VEC_SAMPLE_CURRENT_TABLE}(rowid, embedding)
            VALUES (?, ?)
        """
        for sample_id, blob, _source_hash, dim in rows:
            vector = decode_embedding_blob(blob, dim)
            normalized = normalize_vectors(vector.reshape(1, -1))[0]
            conn.execute(
                insert_sql,
                (sample_id, sqlite_vec.serialize_float32(normalized.astype(np.float32))),
            )

        conn.commit()
    finally:
        conn.close()

    rebuilt_at = datetime.now(timezone.utc).isoformat()
    upsert_vector_index_state(
        model_id=model_id,
        backend=SQLITE_VEC_BACKEND,
        embedding_dim=embedding_dim,
        sample_count=len(rows),
        vec_table_name=VEC_SAMPLE_CURRENT_TABLE,
        last_rebuild_at=rebuilt_at,
        source_fingerprint=source_fingerprint,
    )
    sync_pred_type_tags()

    return VecRebuildResult(
        model_id=model_id,
        embedding_dim=embedding_dim,
        sample_count=len(rows),
        source_fingerprint=source_fingerprint,
        vec_table_name=VEC_SAMPLE_CURRENT_TABLE,
    )
