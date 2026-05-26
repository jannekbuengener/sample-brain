from sqlalchemy import create_engine, text
from pathlib import Path
from .config import DB_PATH, DATA_DIR

def get_engine():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{DB_PATH}", future=True)

def init_db():
    engine = get_engine()
    with engine.begin() as conn:
        # samples
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS samples (
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE NOT NULL,
            relpath TEXT,
            samplerate INT,
            channels INT,
            duration REAL,
            size_bytes INT,
            hash TEXT
        );
        """))
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
            FOREIGN KEY(sample_id) REFERENCES samples(id)
        );
        """))
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
