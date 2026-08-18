from sqlalchemy import create_engine, event, text
from pathlib import Path

from . import config
from .content_hash import (
    DEFAULT_CONTENT_HASH_ALGORITHM,
    LEGACY_CONTENT_HASH_ALGORITHM,
    hash_record,
)


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    """Enable SQLite foreign-key enforcement for every DB-API connection."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def get_engine():
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{config.DB_PATH}", future=True)
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    return engine


def init_db():
    engine = get_engine()
    with engine.begin() as conn:
        # samples. hash_algorithm is additive in #417; NULL on a pre-v2 row is
        # explicitly interpreted as the historical SHA-1 catalog contract.
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS samples (
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE NOT NULL,
            relpath TEXT,
            samplerate INT,
            channels INT,
            duration REAL,
            size_bytes INT,
            hash TEXT,
            hash_algorithm TEXT
        );
        """))
        sample_cols = conn.execute(text("PRAGMA table_info(samples)")).fetchall()
        sample_col_names = {column[1] for column in sample_cols}
        if "hash_algorithm" not in sample_col_names:
            conn.execute(text("ALTER TABLE samples ADD COLUMN hash_algorithm TEXT"))

        # features (mit pred_type!)
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS features (
            sample_id INTEGER PRIMARY KEY,
            bpm REAL,
            key TEXT,
            key_conf REAL,
            loudness REAL,
            brightness REAL,
            mfcc_mean BLOB,
            mfcc_std  BLOB,
            chroma_mean BLOB,
            chroma_std  BLOB,
            class TEXT,
            pred_type TEXT,
            quality_note TEXT,
            key_mode TEXT,
            key_mode_evidence TEXT,
            FOREIGN KEY(sample_id) REFERENCES samples(id)
        );
        """))
        feature_cols = conn.execute(text("PRAGMA table_info(features)")).fetchall()
        feature_col_names = {column[1] for column in feature_cols}
        for column_name in ("quality_note", "key_mode", "key_mode_evidence"):
            if column_name not in feature_col_names:
                conn.execute(text(f"ALTER TABLE features ADD COLUMN {column_name} TEXT"))

        # embedding models registry
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS embedding_models (
            id INTEGER PRIMARY KEY,
            provider TEXT NOT NULL,
            model_name TEXT NOT NULL,
            model_version TEXT,
            embedding_dim INTEGER NOT NULL,
            modality TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(provider, model_name, model_version, modality)
        );
        """))
        # sample embeddings (one per sample per model)
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS sample_embeddings (
            id INTEGER PRIMARY KEY,
            sample_id INTEGER NOT NULL,
            model_id INTEGER NOT NULL,
            embedding BLOB NOT NULL,
            embedding_format TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(sample_id) REFERENCES samples(id),
            FOREIGN KEY(model_id) REFERENCES embedding_models(id),
            UNIQUE(sample_id, model_id, source_hash)
        );
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sample_embeddings_sample_id ON sample_embeddings(sample_id);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sample_embeddings_model_id ON sample_embeddings(model_id);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sample_embeddings_source_hash ON sample_embeddings(source_hash);"))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS vector_index_state (
            id INTEGER PRIMARY KEY,
            model_id INTEGER NOT NULL,
            backend TEXT NOT NULL,
            vec_table_name TEXT,
            embedding_dim INTEGER NOT NULL,
            sample_count INTEGER NOT NULL,
            last_rebuild_at TEXT,
            source_fingerprint TEXT,
            FOREIGN KEY(model_id) REFERENCES embedding_models(id),
            UNIQUE(model_id, backend)
        );
        """))
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS sample_tags (
            id INTEGER PRIMARY KEY,
            sample_id INTEGER NOT NULL,
            tag TEXT NOT NULL,
            source TEXT NOT NULL,
            FOREIGN KEY(sample_id) REFERENCES samples(id),
            UNIQUE(sample_id, tag, source)
        );
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sample_tags_sample_id ON sample_tags(sample_id);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_sample_tags_tag ON sample_tags(tag);"))
    return engine


def upsert_embedding_model(
    provider: str,
    model_name: str,
    model_version: str | None,
    embedding_dim: int,
    modality: str,
) -> int:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
            INSERT OR IGNORE INTO embedding_models
                (provider, model_name, model_version, embedding_dim, modality)
            VALUES (:provider, :model_name, :model_version, :embedding_dim, :modality)
            """),
            {
                "provider": provider,
                "model_name": model_name,
                "model_version": model_version,
                "embedding_dim": embedding_dim,
                "modality": modality,
            },
        )
        row = conn.execute(
            text("""
            SELECT id FROM embedding_models
            WHERE provider = :provider
              AND model_name = :model_name
              AND (model_version = :model_version OR (model_version IS NULL AND :model_version IS NULL))
              AND modality = :modality
            """),
            {
                "provider": provider,
                "model_name": model_name,
                "model_version": model_version,
                "modality": modality,
            },
        ).fetchone()
    return row[0]


def get_embedding_model(
    provider: str,
    model_name: str,
    model_version: str | None,
    modality: str,
) -> dict | None:
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("""
            SELECT id, provider, model_name, model_version, embedding_dim, modality, created_at
            FROM embedding_models
            WHERE provider = :provider
              AND model_name = :model_name
              AND (model_version = :model_version OR (model_version IS NULL AND :model_version IS NULL))
              AND modality = :modality
            """),
            {
                "provider": provider,
                "model_name": model_name,
                "model_version": model_version,
                "modality": modality,
            },
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "provider": row[1],
        "model_name": row[2],
        "model_version": row[3],
        "embedding_dim": row[4],
        "modality": row[5],
        "created_at": row[6],
    }


def get_embedding_model_by_id(model_id: int) -> dict | None:
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("""
            SELECT id, provider, model_name, model_version, embedding_dim, modality, created_at
            FROM embedding_models
            WHERE id = :model_id
            """),
            {"model_id": model_id},
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "provider": row[1],
        "model_name": row[2],
        "model_version": row[3],
        "embedding_dim": row[4],
        "modality": row[5],
        "created_at": row[6],
    }


def insert_sample_embedding(
    sample_id: int,
    model_id: int,
    embedding: bytes,
    embedding_format: str,
    source_hash: str,
) -> int:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
            INSERT OR IGNORE INTO sample_embeddings
                (sample_id, model_id, embedding, embedding_format, source_hash)
            VALUES (:sample_id, :model_id, :embedding, :embedding_format, :source_hash)
            """),
            {
                "sample_id": sample_id,
                "model_id": model_id,
                "embedding": embedding,
                "embedding_format": embedding_format,
                "source_hash": source_hash,
            },
        )
        row = conn.execute(
            text("""
            SELECT id FROM sample_embeddings
            WHERE sample_id = :sample_id
              AND model_id = :model_id
              AND source_hash = :source_hash
            """),
            {
                "sample_id": sample_id,
                "model_id": model_id,
                "source_hash": source_hash,
            },
        ).fetchone()
    return row[0]


def iter_pending_samples(model_id: int, limit: int | None = None) -> list[tuple[int, str, str]]:
    if limit is not None and limit <= 0:
        return []
    engine = get_engine()
    query = """
        SELECT s.id, s.path, s.hash
        FROM samples s
        WHERE s.hash IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM sample_embeddings e
              WHERE e.sample_id = s.id
                AND e.model_id = :model_id
                AND e.source_hash = s.hash
          )
        ORDER BY s.id
    """
    if limit is not None:
        query += "\n        LIMIT :limit"
    with engine.begin() as conn:
        params: dict = {"model_id": model_id}
        if limit is not None:
            params["limit"] = limit
        rows = conn.execute(text(query), params).fetchall()
    return [(row[0], row[1], row[2]) for row in rows]


def sample_embedding_exists(sample_id: int, model_id: int, source_hash: str) -> bool:
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("""
            SELECT 1 FROM sample_embeddings
            WHERE sample_id = :sample_id
              AND model_id = :model_id
              AND source_hash = :source_hash
            """),
            {
                "sample_id": sample_id,
                "model_id": model_id,
                "source_hash": source_hash,
            },
        ).fetchone()
    return row is not None


def upsert_vector_index_state(
    model_id: int,
    backend: str,
    embedding_dim: int,
    sample_count: int,
    *,
    vec_table_name: str | None = None,
    last_rebuild_at: str | None = None,
    source_fingerprint: str | None = None,
) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
            INSERT INTO vector_index_state (
                model_id, backend, vec_table_name, embedding_dim, sample_count,
                last_rebuild_at, source_fingerprint
            ) VALUES (
                :model_id, :backend, :vec_table_name, :embedding_dim, :sample_count,
                :last_rebuild_at, :source_fingerprint
            )
            ON CONFLICT(model_id, backend) DO UPDATE SET
                vec_table_name = excluded.vec_table_name,
                embedding_dim = excluded.embedding_dim,
                sample_count = excluded.sample_count,
                last_rebuild_at = excluded.last_rebuild_at,
                source_fingerprint = excluded.source_fingerprint
            """),
            {
                "model_id": model_id,
                "backend": backend,
                "vec_table_name": vec_table_name,
                "embedding_dim": embedding_dim,
                "sample_count": sample_count,
                "last_rebuild_at": last_rebuild_at,
                "source_fingerprint": source_fingerprint,
            },
        )


def get_vector_index_state(model_id: int, backend: str) -> dict | None:
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("""
            SELECT id, model_id, backend, vec_table_name, embedding_dim, sample_count,
                   last_rebuild_at, source_fingerprint
            FROM vector_index_state
            WHERE model_id = :model_id AND backend = :backend
            """),
            {"model_id": model_id, "backend": backend},
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "model_id": row[1],
        "backend": row[2],
        "vec_table_name": row[3],
        "embedding_dim": row[4],
        "sample_count": row[5],
        "last_rebuild_at": row[6],
        "source_fingerprint": row[7],
    }


def replace_sample_tags(sample_id: int, tags: list[tuple[str, str]]) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM sample_tags WHERE sample_id = :sample_id"),
            {"sample_id": sample_id},
        )
        for tag, source in tags:
            conn.execute(
                text("""
                INSERT OR IGNORE INTO sample_tags (sample_id, tag, source)
                VALUES (:sample_id, :tag, :source)
                """),
                {"sample_id": sample_id, "tag": tag, "source": source},
            )


def list_sample_tags(sample_id: int | None = None) -> list[dict]:
    engine = get_engine()
    query = """
        SELECT id, sample_id, tag, source
        FROM sample_tags
    """
    params: dict = {}
    if sample_id is not None:
        query += " WHERE sample_id = :sample_id"
        params["sample_id"] = sample_id
    query += " ORDER BY sample_id, tag, source"
    with engine.begin() as conn:
        rows = conn.execute(text(query), params).fetchall()
    return [
        {"id": row[0], "sample_id": row[1], "tag": row[2], "source": row[3]}
        for row in rows
    ]


def upsert_sample_tag(sample_id: int, tag: str, source: str) -> None:
    """Add a sample tag idempotently (INSERT OR IGNORE on the unique triplet)."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
            INSERT OR IGNORE INTO sample_tags (sample_id, tag, source)
            VALUES (:sample_id, :tag, :source)
            """),
            {"sample_id": sample_id, "tag": tag, "source": source},
        )


def find_sample_by_path(path: str) -> tuple[int, str] | None:
    """Backward-compatible return of ``(id, bare_hash_value)``."""
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT id, hash FROM samples WHERE path = :path"),
            {"path": str(path)},
        ).fetchone()
    if row is None:
        return None
    return int(row[0]), row[1]


def find_sample_identity_by_path(path: str) -> tuple[int, dict[str, str]] | None:
    """Return an algorithm-qualified catalog content identity.

    ``NULL`` algorithm is the explicit legacy pre-#417 catalog state and is
    therefore interpreted as SHA-1 without mutating or rehashing the row.
    """
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT id, hash, hash_algorithm FROM samples WHERE path = :path"),
            {"path": str(path)},
        ).fetchone()
    if row is None or row[1] is None:
        return None
    algorithm = row[2] or LEGACY_CONTENT_HASH_ALGORITHM
    return int(row[0]), hash_record(algorithm, row[1])


def find_sample_id_by_hash(
    content_hash: str,
    *,
    hash_algorithm: str | None = None,
) -> int | None:
    """Return the smallest sample id sharing an algorithm-qualified identity.

    Callers that omit ``hash_algorithm`` retain the historical value-only lookup.
    New provenance/dedupe paths must pass the algorithm explicitly.
    """
    engine = get_engine()
    with engine.begin() as conn:
        if hash_algorithm is None:
            row = conn.execute(
                text("SELECT id FROM samples WHERE hash = :h ORDER BY id ASC LIMIT 1"),
                {"h": content_hash},
            ).fetchone()
        else:
            row = conn.execute(
                text("""
                    SELECT id FROM samples
                    WHERE hash = :h
                      AND COALESCE(hash_algorithm, :legacy) = :algorithm
                    ORDER BY id ASC
                    LIMIT 1
                """),
                {
                    "h": content_hash,
                    "algorithm": hash_algorithm,
                    "legacy": LEGACY_CONTENT_HASH_ALGORITHM,
                },
            ).fetchone()
    if row is None:
        return None
    return int(row[0])


def insert_sample(
    path: str,
    relpath: str | None,
    samplerate: int | None,
    channels: int | None,
    duration: float | None,
    size_bytes: int,
    content_hash: str,
    content_hash_algorithm: str = DEFAULT_CONTENT_HASH_ALGORITHM,
) -> int:
    """Insert a new sample row (plain INSERT; path is UNIQUE)."""
    identity = hash_record(content_hash_algorithm, content_hash)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text("""
            INSERT INTO samples (
                path, relpath, samplerate, channels, duration, size_bytes, hash,
                hash_algorithm
            )
            VALUES (
                :path, :relpath, :sr, :ch, :dur, :size_bytes, :hash,
                :hash_algorithm
            )
            """),
            dict(
                path=str(path),
                relpath=relpath,
                sr=samplerate,
                ch=channels,
                dur=duration,
                size_bytes=size_bytes,
                hash=identity["value"],
                hash_algorithm=identity["algorithm"],
            ),
        )
        row = conn.execute(
            text("SELECT id FROM samples WHERE path = :path"),
            {"path": str(path)},
        ).fetchone()
    return int(row[0])


def load_sample_paths(sample_ids: list[int]) -> dict[int, str]:
    if not sample_ids:
        return {}

    engine = get_engine()
    placeholders = ", ".join(f":id_{index}" for index in range(len(sample_ids)))
    params = {f"id_{index}": sample_id for index, sample_id in enumerate(sample_ids)}
    query = f"""
        SELECT id, path
        FROM samples
        WHERE id IN ({placeholders})
    """
    with engine.begin() as conn:
        rows = conn.execute(text(query), params).fetchall()

    return {row[0]: row[1] for row in rows}


def ensure_features_pred_type_column() -> None:
    engine = get_engine()
    with engine.begin() as conn:
        cols = conn.execute(text("PRAGMA table_info(features)")).fetchall()
        names = {column[1] for column in cols}
        if "pred_type" not in names:
            conn.execute(text("ALTER TABLE features ADD COLUMN pred_type TEXT"))


def load_hybrid_metadata(sample_ids: list[int]) -> dict[int, "HybridMetadata"]:
    from .hybrid_rank import HybridMetadata

    if not sample_ids:
        return {}

    ensure_features_pred_type_column()
    engine = get_engine()
    placeholders = ", ".join(f":id_{index}" for index in range(len(sample_ids)))
    params = {f"id_{index}": sample_id for index, sample_id in enumerate(sample_ids)}
    query = f"""
        SELECT sample_id, bpm, key, pred_type, class
        FROM features
        WHERE sample_id IN ({placeholders})
    """
    with engine.begin() as conn:
        rows = conn.execute(text(query), params).fetchall()

    return {
        row[0]: HybridMetadata(
            sample_id=row[0],
            bpm=row[1],
            key=row[2],
            pred_type=row[3],
            audio_class=row[4],
        )
        for row in rows
    }
