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
    return engine
