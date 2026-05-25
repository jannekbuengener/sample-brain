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
