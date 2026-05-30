from __future__ import annotations
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text

from src.db import iter_pending_samples


@pytest.fixture
def in_memory_db():
    engine = create_engine("sqlite://", future=True)
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE samples (
                id INTEGER PRIMARY KEY,
                path TEXT UNIQUE NOT NULL,
                hash TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE embedding_models (
                id INTEGER PRIMARY KEY,
                provider TEXT NOT NULL,
                model_name TEXT NOT NULL,
                model_version TEXT,
                embedding_dim INTEGER NOT NULL,
                modality TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE sample_embeddings (
                id INTEGER PRIMARY KEY,
                sample_id INTEGER NOT NULL,
                model_id INTEGER NOT NULL,
                embedding BLOB NOT NULL,
                embedding_format TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                FOREIGN KEY(sample_id) REFERENCES samples(id),
                FOREIGN KEY(model_id) REFERENCES embedding_models(id),
                UNIQUE(sample_id, model_id, source_hash)
            )
        """))
        conn.execute(text("""
            INSERT INTO samples (id, path, hash) VALUES
                (1, '/samples/kick.wav', 'abc123'),
                (2, '/samples/snare.wav', 'def456'),
                (3, '/samples/hihat.wav', 'ghi789'),
                (4, '/samples/clap.wav', 'jkl012'),
                (5, '/samples/no_hash.wav', NULL)
        """))
        conn.execute(text("""
            INSERT INTO embedding_models (id, provider, model_name, model_version, embedding_dim, modality)
            VALUES (1, 'laion', 'clap', '1.0', 512, 'audio+text')
        """))
        conn.execute(text("""
            INSERT INTO sample_embeddings (id, sample_id, model_id, embedding, embedding_format, source_hash)
            VALUES (1, 1, 1, X'0000', 'numpy-blob', 'abc123')
        """))
    yield engine


def _patch_engine(engine):
    return patch("src.db.get_engine", return_value=engine)


class TestIterPendingSamples:
    def test_returns_pending_when_no_embedding_exists(self, in_memory_db):
        with _patch_engine(in_memory_db):
            result = iter_pending_samples(model_id=1)
        assert len(result) == 3
        assert result[0] == (2, "/samples/snare.wav", "def456")

    def test_skips_sample_with_current_embedding(self, in_memory_db):
        with _patch_engine(in_memory_db):
            result = iter_pending_samples(model_id=1)
        ids = [r[0] for r in result]
        assert 1 not in ids

    def test_returns_sample_with_stale_embedding(self, in_memory_db):
        engine = in_memory_db
        with engine.begin() as conn:
            conn.execute(text(
                "UPDATE samples SET hash = 'newhash' WHERE id = 1"
            ))
        with _patch_engine(engine):
            result = iter_pending_samples(model_id=1)
        ids = [r[0] for r in result]
        assert 1 in ids

    def test_skips_samples_with_null_hash(self, in_memory_db):
        with _patch_engine(in_memory_db):
            result = iter_pending_samples(model_id=1)
        ids = [r[0] for r in result]
        assert 5 not in ids

    def test_limit_restricts_results(self, in_memory_db):
        with _patch_engine(in_memory_db):
            result = iter_pending_samples(model_id=1, limit=1)
        assert len(result) == 1

    def test_limit_zero_returns_empty(self, in_memory_db):
        with _patch_engine(in_memory_db):
            result = iter_pending_samples(model_id=1, limit=0)
        assert result == []

    def test_limit_negative_returns_empty(self, in_memory_db):
        with _patch_engine(in_memory_db):
            result = iter_pending_samples(model_id=1, limit=-1)
        assert result == []

    def test_returns_correct_tuple_order(self, in_memory_db):
        with _patch_engine(in_memory_db):
            result = iter_pending_samples(model_id=1, limit=1)
        row = result[0]
        assert len(row) == 3
        sid, path, shash = row
        assert isinstance(sid, int)
        assert isinstance(path, str)
        assert isinstance(shash, str)
